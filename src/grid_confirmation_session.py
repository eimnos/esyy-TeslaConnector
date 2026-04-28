"""Guided manual session to confirm Grid Power sign convention.

Wave 9B goals:
- guide baseline / load ON / load OFF phases;
- optionally observe Tesla charging ON/OFF without sending commands;
- collect app/manual annotations and inverter samples;
- infer whether raw grid power sign is import_positive or export_positive;
- write CSV evidence and markdown summary report.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

try:
    from src.afore_reader import AforeReader
    from src.config import load_config
except ModuleNotFoundError:  # Allows `python src/grid_confirmation_session.py`
    from afore_reader import AforeReader  # type: ignore[no-redef]
    from config import load_config  # type: ignore[no-redef]


VALID_DIRECTIONS = {"import", "export", "balanced", "unknown"}


@dataclass(frozen=True, slots=True)
class PhaseConfig:
    name: str
    instruction: str
    required: bool


@dataclass(frozen=True, slots=True)
class PhaseSummary:
    phase: str
    app_direction: str
    app_grid_power_w: float | None
    phase_note: str
    sample_count: int
    ok_count: int
    error_count: int
    avg_pv_power_w: float | None
    avg_grid_raw_w: float | None
    avg_raw_sign: str


@dataclass(frozen=True, slots=True)
class GridInference:
    status: str
    recommended_sign_mode: str
    import_positive_score: int
    export_positive_score: int
    used_evidence_count: int
    reason: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Guided session to confirm Afore Grid Power sign direction."
    )
    parser.add_argument(
        "--samples-per-phase",
        type=int,
        default=12,
        help="Number of snapshots per phase (default: 12).",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=10,
        help="Delay between snapshots in each phase (default: 10).",
    )
    parser.add_argument(
        "--tolerance-w",
        type=float,
        default=120.0,
        help="Near-zero tolerance for direction inference (default: 120W).",
    )
    parser.add_argument(
        "--include-tesla-observation",
        action="store_true",
        help="Include optional Tesla charging ON/OFF observation phases (read-only, no commands).",
    )
    parser.add_argument(
        "--output-csv",
        default="data/grid_confirmation_report.csv",
        help="CSV output path (default: data/grid_confirmation_report.csv).",
    )
    parser.add_argument(
        "--output-md",
        default="docs/grid_confirmation.md",
        help="Markdown output path (default: docs/grid_confirmation.md).",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run without prompts. All app directions become 'unknown'. Useful for smoke tests.",
    )
    return parser.parse_args()


def _phase_plan(include_tesla_observation: bool) -> list[PhaseConfig]:
    phases = [
        PhaseConfig(
            name="baseline",
            instruction=(
                "Baseline: casa in condizioni normali, nessun carico artificiale "
                "aggiunto."
            ),
            required=True,
        ),
        PhaseConfig(
            name="load_on",
            instruction=(
                "Carico ON: accendere un carico noto ~1500-2000W per almeno 2 minuti."
            ),
            required=True,
        ),
        PhaseConfig(
            name="load_off",
            instruction=(
                "Carico OFF: spegnere il carico artificiale e attendere stabilizzazione."
            ),
            required=True,
        ),
    ]

    if include_tesla_observation:
        phases.extend(
            [
                PhaseConfig(
                    name="tesla_charging_on_observed",
                    instruction=(
                        "Tesla charging ON (solo osservazione): collegare/rilevare "
                        "eventuale carica Tesla senza inviare comandi API."
                    ),
                    required=False,
                ),
                PhaseConfig(
                    name="tesla_charging_off_observed",
                    instruction=(
                        "Tesla charging OFF (solo osservazione): scollegare/fermare "
                        "carica manualmente, nessun comando API."
                    ),
                    required=False,
                ),
            ]
        )

    return phases


def _normalize_direction(value: str) -> str:
    direction = value.strip().lower()
    if direction not in VALID_DIRECTIONS:
        raise ValueError(
            f"Invalid direction {value!r}. Allowed: import, export, balanced, unknown"
        )
    return direction


def _ask_direction(non_interactive: bool) -> str:
    if non_interactive:
        return "unknown"

    while True:
        raw = input(
            "Direzione rete da app inverter "
            "[import/export/balanced/unknown] (default unknown): "
        ).strip()
        if not raw:
            return "unknown"
        try:
            return _normalize_direction(raw)
        except ValueError as exc:
            print(str(exc))


def _ask_optional_float(prompt: str, non_interactive: bool) -> float | None:
    if non_interactive:
        return None

    while True:
        raw = input(prompt).strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            print("Valore non valido, inserire numero o lasciare vuoto.")


def _ask_text(prompt: str, non_interactive: bool) -> str:
    if non_interactive:
        return ""
    return input(prompt).strip()


def _raw_sign(value: float | None, tolerance_w: float) -> str:
    if value is None:
        return "n/a"
    if value > tolerance_w:
        return "positive"
    if value < -tolerance_w:
        return "negative"
    return "near_zero"


def _safe_avg(values: Iterable[float]) -> float | None:
    items = list(values)
    if not items:
        return None
    return sum(items) / float(len(items))


def _phase_score(avg_grid_raw_w: float, app_direction: str, tolerance_w: float) -> tuple[int, int]:
    if app_direction not in {"import", "export"}:
        return 0, 0

    if abs(avg_grid_raw_w) <= tolerance_w:
        return 0, 0

    if app_direction == "import":
        if avg_grid_raw_w > 0:
            return 1, 0
        return 0, 1

    # app_direction == "export"
    if avg_grid_raw_w < 0:
        return 1, 0
    return 0, 1


def infer_grid_sign_mode(
    summaries: Iterable[PhaseSummary],
    tolerance_w: float,
) -> GridInference:
    import_score = 0
    export_score = 0
    evidence_count = 0

    for summary in summaries:
        if summary.avg_grid_raw_w is None:
            continue
        i_score, e_score = _phase_score(
            avg_grid_raw_w=summary.avg_grid_raw_w,
            app_direction=summary.app_direction,
            tolerance_w=tolerance_w,
        )
        if i_score or e_score:
            evidence_count += 1
        import_score += i_score
        export_score += e_score

    if evidence_count == 0:
        return GridInference(
            status="partial",
            recommended_sign_mode="unknown",
            import_positive_score=import_score,
            export_positive_score=export_score,
            used_evidence_count=evidence_count,
            reason=(
                "Nessuna evidenza utile: servono annotazioni app import/export "
                "con delta raw oltre soglia."
            ),
        )

    if import_score == export_score:
        return GridInference(
            status="partial",
            recommended_sign_mode="unknown",
            import_positive_score=import_score,
            export_positive_score=export_score,
            used_evidence_count=evidence_count,
            reason="Evidenza in conflitto: import_positive ed export_positive a pari punteggio.",
        )

    if import_score > export_score:
        return GridInference(
            status="confirmed",
            recommended_sign_mode="import_positive",
            import_positive_score=import_score,
            export_positive_score=export_score,
            used_evidence_count=evidence_count,
            reason=(
                "Miglior allineamento con annotazioni app: import positivo, export negativo."
            ),
        )

    return GridInference(
        status="confirmed",
        recommended_sign_mode="export_positive",
        import_positive_score=import_score,
        export_positive_score=export_score,
        used_evidence_count=evidence_count,
        reason="Miglior allineamento con annotazioni app: export positivo, import negativo.",
    )


def collect_phase(
    *,
    reader: AforeReader,
    session_id: str,
    phase: PhaseConfig,
    samples_per_phase: int,
    interval_seconds: int,
    tolerance_w: float,
    app_direction: str,
    app_grid_power_w: float | None,
    phase_note: str,
) -> tuple[list[dict[str, str]], PhaseSummary]:
    rows: list[dict[str, str]] = []
    pv_values: list[float] = []
    grid_values: list[float] = []

    for sample_index in range(1, samples_per_phase + 1):
        sample_timestamp = datetime.now(timezone.utc).isoformat()
        try:
            snapshot = reader.read_snapshot()
            pv_power_w = snapshot.pv_power_w
            grid_raw_w = snapshot.grid_power_raw_w
            pv_values.append(pv_power_w)
            grid_values.append(grid_raw_w)
            error_text = ""
        except Exception as exc:
            pv_power_w = None
            grid_raw_w = None
            error_text = f"{type(exc).__name__}: {exc}"

        row = {
            "row_type": "sample",
            "session_id": session_id,
            "phase": phase.name,
            "sample_index": str(sample_index),
            "timestamp_utc": sample_timestamp,
            "pv_power_w": "" if pv_power_w is None else f"{pv_power_w:.3f}",
            "grid_power_raw_w": "" if grid_raw_w is None else f"{grid_raw_w:.3f}",
            "raw_sign": _raw_sign(grid_raw_w, tolerance_w),
            "app_grid_direction": app_direction,
            "app_grid_power_w": "" if app_grid_power_w is None else f"{app_grid_power_w:.3f}",
            "phase_note": phase_note,
            "read_error": error_text,
        }
        rows.append(row)

        print(
            f"[{phase.name} {sample_index:02d}/{samples_per_phase}] "
            f"pv={row['pv_power_w'] or 'n/a'}W "
            f"grid_raw={row['grid_power_raw_w'] or 'n/a'}W "
            f"sign={row['raw_sign']}"
            + (f" error={error_text}" if error_text else "")
        )

        if sample_index < samples_per_phase:
            time.sleep(interval_seconds)

    avg_pv = _safe_avg(pv_values)
    avg_grid = _safe_avg(grid_values)
    summary = PhaseSummary(
        phase=phase.name,
        app_direction=app_direction,
        app_grid_power_w=app_grid_power_w,
        phase_note=phase_note,
        sample_count=samples_per_phase,
        ok_count=len(pv_values),
        error_count=samples_per_phase - len(pv_values),
        avg_pv_power_w=avg_pv,
        avg_grid_raw_w=avg_grid,
        avg_raw_sign=_raw_sign(avg_grid, tolerance_w),
    )

    rows.append(
        {
            "row_type": "phase_summary",
            "session_id": session_id,
            "phase": phase.name,
            "sample_index": "",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "pv_power_w": "" if avg_pv is None else f"{avg_pv:.3f}",
            "grid_power_raw_w": "" if avg_grid is None else f"{avg_grid:.3f}",
            "raw_sign": summary.avg_raw_sign,
            "app_grid_direction": app_direction,
            "app_grid_power_w": "" if app_grid_power_w is None else f"{app_grid_power_w:.3f}",
            "phase_note": phase_note,
            "read_error": (
                f"ok={summary.ok_count};errors={summary.error_count};"
                f"samples={summary.sample_count}"
            ),
        }
    )
    return rows, summary


def write_csv_report(rows: list[dict[str, str]], output_csv: Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "row_type",
        "session_id",
        "phase",
        "sample_index",
        "timestamp_utc",
        "pv_power_w",
        "grid_power_raw_w",
        "raw_sign",
        "app_grid_direction",
        "app_grid_power_w",
        "phase_note",
        "read_error",
    ]
    with output_csv.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_markdown_report(
    *,
    session_id: str,
    summaries: list[PhaseSummary],
    inference: GridInference,
    output_csv: Path,
) -> str:
    lines: list[str] = []
    lines.append("# Grid Confirmation Session")
    lines.append("")
    lines.append(f"- Session UTC: `{session_id}`")
    lines.append(f"- Source CSV: `{output_csv}`")
    lines.append("")
    lines.append("## Phase Results")
    lines.append("")
    lines.append(
        "| Phase | App Direction | Avg PV (W) | Avg Grid Raw (W) | Raw Sign | "
        "Samples OK | Errors | Note |"
    )
    lines.append("| --- | --- | ---: | ---: | --- | ---: | ---: | --- |")

    for summary in summaries:
        lines.append(
            "| "
            f"{summary.phase} | "
            f"{summary.app_direction} | "
            f"{'' if summary.avg_pv_power_w is None else f'{summary.avg_pv_power_w:.1f}'} | "
            f"{'' if summary.avg_grid_raw_w is None else f'{summary.avg_grid_raw_w:.1f}'} | "
            f"{summary.avg_raw_sign} | "
            f"{summary.ok_count}/{summary.sample_count} | "
            f"{summary.error_count} | "
            f"{summary.phase_note or '-'} |"
        )

    lines.append("")
    lines.append("## Sign Inference")
    lines.append("")
    lines.append(f"- Status: `{inference.status}`")
    lines.append(f"- Recommended `AFORE_GRID_SIGN_MODE`: `{inference.recommended_sign_mode}`")
    lines.append(f"- Score import_positive: `{inference.import_positive_score}`")
    lines.append(f"- Score export_positive: `{inference.export_positive_score}`")
    lines.append(f"- Evidence phases used: `{inference.used_evidence_count}`")
    lines.append(f"- Reason: {inference.reason}")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- `import_positive` means raw grid > 0 is import, raw grid < 0 is export.")
    lines.append("- `export_positive` means raw grid > 0 is export, raw grid < 0 is import.")
    lines.append("- If status is `partial`, keep mapping as partial and collect another session.")
    lines.append("")
    lines.append("## Safety")
    lines.append("")
    lines.append("- No Tesla command is sent by this script.")
    lines.append("- Tesla ON/OFF phases are observational only.")
    return "\n".join(lines) + "\n"


def write_markdown_report(report_text: str, output_md: Path) -> None:
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(report_text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.samples_per_phase <= 0:
        print("--samples-per-phase must be > 0", file=sys.stderr)
        return 2
    if args.interval_seconds <= 0:
        print("--interval-seconds must be > 0", file=sys.stderr)
        return 2
    if args.tolerance_w < 0:
        print("--tolerance-w must be >= 0", file=sys.stderr)
        return 2

    try:
        config = load_config()
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    output_csv = Path(args.output_csv)
    output_md = Path(args.output_md)
    session_id = datetime.now(timezone.utc).isoformat()
    phase_plan = _phase_plan(args.include_tesla_observation)

    print("Wave 9B - Grid confirmation session")
    print(
        f"Collector {config.collector_ip}:{config.collector_port} "
        f"| grid regs {config.afore_grid_power_register_high}-{config.afore_grid_power_register_low}"
    )
    print(
        "Safety: no Tesla command endpoints are used. Tesla phases are observation-only."
    )

    reader = AforeReader(config)
    all_rows: list[dict[str, str]] = []
    phase_summaries: list[PhaseSummary] = []
    try:
        for phase in phase_plan:
            print("\n" + "=" * 72)
            print(f"PHASE: {phase.name}")
            print(phase.instruction)
            if not args.non_interactive:
                input("Premi INVIO quando pronto per iniziare questa fase...")

            app_direction = _ask_direction(args.non_interactive)
            app_grid_power_w = _ask_optional_float(
                "Valore rete da app inverter (W, opzionale): ",
                args.non_interactive,
            )
            phase_note = _ask_text("Note fase (opzionale): ", args.non_interactive)

            rows, summary = collect_phase(
                reader=reader,
                session_id=session_id,
                phase=phase,
                samples_per_phase=args.samples_per_phase,
                interval_seconds=args.interval_seconds,
                tolerance_w=args.tolerance_w,
                app_direction=app_direction,
                app_grid_power_w=app_grid_power_w,
                phase_note=phase_note,
            )
            all_rows.extend(rows)
            phase_summaries.append(summary)
    finally:
        reader.close()

    inference = infer_grid_sign_mode(phase_summaries, args.tolerance_w)
    all_rows.append(
        {
            "row_type": "session_summary",
            "session_id": session_id,
            "phase": "all",
            "sample_index": "",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "pv_power_w": "",
            "grid_power_raw_w": "",
            "raw_sign": "",
            "app_grid_direction": "",
            "app_grid_power_w": "",
            "phase_note": (
                f"status={inference.status};recommended={inference.recommended_sign_mode};"
                f"score_import_positive={inference.import_positive_score};"
                f"score_export_positive={inference.export_positive_score};"
                f"evidence={inference.used_evidence_count}"
            ),
            "read_error": inference.reason,
        }
    )

    write_csv_report(all_rows, output_csv=output_csv)
    report_text = build_markdown_report(
        session_id=session_id,
        summaries=phase_summaries,
        inference=inference,
        output_csv=output_csv,
    )
    write_markdown_report(report_text, output_md=output_md)

    print("\nSession completed.")
    print(f"CSV report: {output_csv}")
    print(f"Markdown report: {output_md}")
    print(f"Inference status: {inference.status}")
    print(f"Recommended AFORE_GRID_SIGN_MODE: {inference.recommended_sign_mode}")
    print(f"Reason: {inference.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
