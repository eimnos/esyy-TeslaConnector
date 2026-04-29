"""Wave 9E session to validate HA/Afore candidate registers."""

from __future__ import annotations

import argparse
import csv
import socket
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from pysolarmanv5 import PySolarmanV5
except ImportError as exc:  # pragma: no cover - runtime dependency check
    PySolarmanV5 = None  # type: ignore[assignment]
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None

try:
    from src.afore_ha_candidates import HaCandidateSnapshot, build_ha_candidate_snapshot
    from src.config import AppConfig, load_config
except ModuleNotFoundError:  # Allows `python src/ha_candidate_validation_session.py`
    from afore_ha_candidates import HaCandidateSnapshot, build_ha_candidate_snapshot  # type: ignore[no-redef]
    from config import AppConfig, load_config  # type: ignore[no-redef]


@dataclass(frozen=True, slots=True)
class PhaseConfig:
    name: str
    instruction: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Wave 9E validation on HA/Afore candidate register pairs."
    )
    parser.add_argument(
        "--samples-per-phase",
        type=int,
        default=12,
        help="Number of samples per phase (default: 12).",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=10,
        help="Delay between samples in seconds (default: 10).",
    )
    parser.add_argument(
        "--output-csv",
        default="data/ha_candidate_validation.csv",
        help="CSV report path (default: data/ha_candidate_validation.csv).",
    )
    parser.add_argument(
        "--output-md",
        default="docs/ha_candidate_validation.md",
        help="Markdown summary path (default: docs/ha_candidate_validation.md).",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Skip interactive prompts and app annotations.",
    )
    parser.add_argument(
        "--app-per-sample",
        action="store_true",
        help="Ask app grid/load/pv values for each sample (same-instant comparison).",
    )
    return parser.parse_args()


def _phase_plan() -> list[PhaseConfig]:
    return [
        PhaseConfig("baseline", "Casa in condizioni normali, senza carico artificiale."),
        PhaseConfig("load_on", "Accendere carico noto EV/forno/phon e attendere stabilizzazione."),
        PhaseConfig("load_off", "Spegnere carico aggiuntivo e attendere stabilizzazione."),
    ]


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


def _safe_mae(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / float(len(values))


def _close_client(client: Any) -> None:
    disconnect = getattr(client, "disconnect", None)
    if callable(disconnect):
        disconnect()
        return
    close = getattr(client, "close", None)
    if callable(close):
        close()


class HaCandidateReader:
    """Reads candidate register ranges for Wave 9E validation."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._client: Any | None = None

    def connect(self) -> None:
        if self._client is not None:
            return
        if PySolarmanV5 is None:
            raise RuntimeError(
                "pysolarmanv5 is not installed. Run: pip install -r requirements.txt"
            ) from IMPORT_ERROR
        self._client = PySolarmanV5(
            self._config.collector_ip,
            self._config.collector_serial,
            port=self._config.collector_port,
            mb_slave_id=1,
            verbose=False,
        )

    def close(self) -> None:
        if self._client is None:
            return
        _close_client(self._client)
        self._client = None

    def read_registers(self) -> dict[int, float]:
        if self._client is None:
            self.connect()
        assert self._client is not None

        # Power block candidates from T6 mapping / ha-solarman profile.
        power_block = self._client.read_input_registers(535, 26)  # 535..560
        # Meter block candidates.
        meter_block = self._client.read_input_registers(1002, 29)  # 1002..1030

        if not isinstance(power_block, (list, tuple)) or not isinstance(
            meter_block, (list, tuple)
        ):
            raise TypeError("Unexpected response type while reading candidate blocks.")

        data: dict[int, float] = {
            535 + idx: float(value) for idx, value in enumerate(power_block)
        }
        data.update({1002 + idx: float(value) for idx, value in enumerate(meter_block)})
        return data

    def read_snapshot(self) -> HaCandidateSnapshot:
        try:
            values = self.read_registers()
        except (socket.timeout, TimeoutError) as exc:
            self.close()
            raise RuntimeError("Timeout while reading HA/Afore candidate registers.") from exc
        except (ConnectionError, OSError) as exc:
            self.close()
            raise RuntimeError("Network error while reading HA/Afore candidate registers.") from exc
        except Exception:
            self.close()
            raise

        return build_ha_candidate_snapshot(values)


def write_markdown_summary(
    *,
    output_md: Path,
    rows: list[dict[str, str]],
    mae_grid_ab: float | None,
    mae_grid_ba: float | None,
    mae_load_ab: float | None,
    mae_load_ba: float | None,
) -> None:
    output_md.parent.mkdir(parents=True, exist_ok=True)

    samples = [row for row in rows if row["row_type"] == "sample"]
    app_grid_samples = [row for row in samples if row["app_grid_w"]]
    app_load_samples = [row for row in samples if row["app_load_w"]]

    grid_order = "unknown"
    if mae_grid_ab is not None and mae_grid_ba is not None:
        grid_order = "[535,536]" if mae_grid_ab < mae_grid_ba else "[536,535]"

    load_order = "unknown"
    if mae_load_ab is not None and mae_load_ba is not None:
        load_order = "[547,548]" if mae_load_ab < mae_load_ba else "[548,547]"

    lines = [
        "# Wave 9E - HA/Afore Candidate Validation",
        "",
        f"- Generated at: `{datetime.now(timezone.utc).isoformat()}`",
        f"- Sample rows: `{len(samples)}`",
        f"- Samples with app grid annotation: `{len(app_grid_samples)}`",
        f"- Samples with app load annotation: `{len(app_load_samples)}`",
        "",
        "## Order Comparison",
        "",
        f"- Grid MAE [535,536] (A=high,B=low): `{mae_grid_ab}`",
        f"- Grid MAE [536,535] (HA order): `{mae_grid_ba}`",
        f"- Grid best order by MAE: `{grid_order}`",
        "",
        f"- Load MAE [547,548] (A=high,B=low): `{mae_load_ab}`",
        f"- Load MAE [548,547] (HA order): `{mae_load_ba}`",
        f"- Load best order by MAE: `{load_order}`",
        "",
        "## Decision Rule",
        "",
        "- Mark Grid Power as `confirmed` only if app-matched MAE is consistently low and trend is coherent.",
        "- Otherwise keep status `candidate` or `rejected`.",
        "",
    ]

    output_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.samples_per_phase <= 0:
        print("--samples-per-phase must be > 0", file=sys.stderr)
        return 2
    if args.interval_seconds <= 0:
        print("--interval-seconds must be > 0", file=sys.stderr)
        return 2

    config = load_config()
    output_csv = Path(args.output_csv)
    output_md = Path(args.output_md)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "row_type",
        "phase",
        "sample_index",
        "timestamp_utc",
        "grid_power_535_536_ab_w",
        "grid_power_536_535_ba_w",
        "load_power_547_548_ab_w",
        "load_power_548_547_ba_w",
        "pv_total_553_554_ab_w",
        "pv_total_554_553_ba_w",
        "today_energy_export_1002_kwh",
        "today_energy_import_1003_kwh",
        "today_load_consumption_1004_kwh",
        "today_production_1007_1006_kwh",
        "total_production_1027_1026_kwh",
        "total_export_1019_1018_kwh",
        "total_import_1021_1020_kwh",
        "app_grid_w",
        "app_load_w",
        "app_pv_w",
        "grid_err_535_536_ab_w",
        "grid_err_536_535_ba_w",
        "load_err_547_548_ab_w",
        "load_err_548_547_ba_w",
        "pv_err_553_554_ab_w",
        "pv_err_554_553_ba_w",
        "read_error",
    ]

    reader = HaCandidateReader(config)
    rows: list[dict[str, str]] = []
    grid_errors_ab: list[float] = []
    grid_errors_ba: list[float] = []
    load_errors_ab: list[float] = []
    load_errors_ba: list[float] = []

    print("Wave 9E validation session started.")
    print("Safety: read-only inverter telemetry, no Tesla commands.")

    try:
        for phase in _phase_plan():
            print(f"\n=== PHASE {phase.name} ===")
            print(phase.instruction)
            if not args.non_interactive:
                input("Premi INVIO quando pronto...")

            phase_app_grid_w = None
            phase_app_load_w = None
            phase_app_pv_w = None
            if not args.app_per_sample:
                phase_app_grid_w = _ask_optional_float(
                    "Valore app Grid Power istantaneo (W, opzionale): ",
                    args.non_interactive,
                )
                phase_app_load_w = _ask_optional_float(
                    "Valore app Load Power istantaneo (W, opzionale): ",
                    args.non_interactive,
                )
                phase_app_pv_w = _ask_optional_float(
                    "Valore app PV Total Power istantaneo (W, opzionale): ",
                    args.non_interactive,
                )

            for idx in range(1, args.samples_per_phase + 1):
                timestamp_utc = datetime.now(timezone.utc).isoformat()
                if args.app_per_sample:
                    app_grid_w = _ask_optional_float(
                        "App Grid Power (W, invio=skip): ",
                        args.non_interactive,
                    )
                    app_load_w = _ask_optional_float(
                        "App Load Power (W, invio=skip): ",
                        args.non_interactive,
                    )
                    app_pv_w = _ask_optional_float(
                        "App PV Total Power (W, invio=skip): ",
                        args.non_interactive,
                    )
                else:
                    app_grid_w = phase_app_grid_w
                    app_load_w = phase_app_load_w
                    app_pv_w = phase_app_pv_w
                row = {
                    "row_type": "sample",
                    "phase": phase.name,
                    "sample_index": str(idx),
                    "timestamp_utc": timestamp_utc,
                    "app_grid_w": "" if app_grid_w is None else f"{app_grid_w:.3f}",
                    "app_load_w": "" if app_load_w is None else f"{app_load_w:.3f}",
                    "app_pv_w": "" if app_pv_w is None else f"{app_pv_w:.3f}",
                    "read_error": "",
                }

                try:
                    snapshot = reader.read_snapshot()
                    row.update(
                        {
                            "grid_power_535_536_ab_w": str(snapshot.grid_power_535_536_ab_w),
                            "grid_power_536_535_ba_w": str(snapshot.grid_power_536_535_ba_w),
                            "load_power_547_548_ab_w": str(snapshot.load_power_547_548_ab_w),
                            "load_power_548_547_ba_w": str(snapshot.load_power_548_547_ba_w),
                            "pv_total_553_554_ab_w": str(snapshot.pv_total_553_554_ab_w),
                            "pv_total_554_553_ba_w": str(snapshot.pv_total_554_553_ba_w),
                            "today_energy_export_1002_kwh": f"{snapshot.today_energy_export_1002_kwh:.3f}",
                            "today_energy_import_1003_kwh": f"{snapshot.today_energy_import_1003_kwh:.3f}",
                            "today_load_consumption_1004_kwh": f"{snapshot.today_load_consumption_1004_kwh:.3f}",
                            "today_production_1007_1006_kwh": f"{snapshot.today_production_1007_1006_kwh:.3f}",
                            "total_production_1027_1026_kwh": f"{snapshot.total_production_1027_1026_kwh:.3f}",
                            "total_export_1019_1018_kwh": f"{snapshot.total_export_1019_1018_kwh:.3f}",
                            "total_import_1021_1020_kwh": f"{snapshot.total_import_1021_1020_kwh:.3f}",
                        }
                    )

                    if app_grid_w is not None:
                        err_ab = abs(snapshot.grid_power_535_536_ab_w - app_grid_w)
                        err_ba = abs(snapshot.grid_power_536_535_ba_w - app_grid_w)
                        row["grid_err_535_536_ab_w"] = f"{err_ab:.3f}"
                        row["grid_err_536_535_ba_w"] = f"{err_ba:.3f}"
                        grid_errors_ab.append(err_ab)
                        grid_errors_ba.append(err_ba)
                    else:
                        row["grid_err_535_536_ab_w"] = ""
                        row["grid_err_536_535_ba_w"] = ""

                    if app_load_w is not None:
                        err_ab = abs(snapshot.load_power_547_548_ab_w - app_load_w)
                        err_ba = abs(snapshot.load_power_548_547_ba_w - app_load_w)
                        row["load_err_547_548_ab_w"] = f"{err_ab:.3f}"
                        row["load_err_548_547_ba_w"] = f"{err_ba:.3f}"
                        load_errors_ab.append(err_ab)
                        load_errors_ba.append(err_ba)
                    else:
                        row["load_err_547_548_ab_w"] = ""
                        row["load_err_548_547_ba_w"] = ""

                    if app_pv_w is not None:
                        row["pv_err_553_554_ab_w"] = f"{abs(snapshot.pv_total_553_554_ab_w - app_pv_w):.3f}"
                        row["pv_err_554_553_ba_w"] = f"{abs(snapshot.pv_total_554_553_ba_w - app_pv_w):.3f}"
                    else:
                        row["pv_err_553_554_ab_w"] = ""
                        row["pv_err_554_553_ba_w"] = ""

                    print(
                        f"[{phase.name} {idx:02d}/{args.samples_per_phase}] "
                        f"grid_ab={snapshot.grid_power_535_536_ab_w}W "
                        f"grid_ba={snapshot.grid_power_536_535_ba_w}W "
                        f"load_ab={snapshot.load_power_547_548_ab_w}W "
                        f"load_ba={snapshot.load_power_548_547_ba_w}W "
                        f"pv_ab={snapshot.pv_total_553_554_ab_w}W "
                        f"pv_ba={snapshot.pv_total_554_553_ba_w}W"
                    )
                except Exception as exc:
                    row.update(
                        {
                            "grid_power_535_536_ab_w": "",
                            "grid_power_536_535_ba_w": "",
                            "load_power_547_548_ab_w": "",
                            "load_power_548_547_ba_w": "",
                            "pv_total_553_554_ab_w": "",
                            "pv_total_554_553_ba_w": "",
                            "today_energy_export_1002_kwh": "",
                            "today_energy_import_1003_kwh": "",
                            "today_load_consumption_1004_kwh": "",
                            "today_production_1007_1006_kwh": "",
                            "total_production_1027_1026_kwh": "",
                            "total_export_1019_1018_kwh": "",
                            "total_import_1021_1020_kwh": "",
                            "grid_err_535_536_ab_w": "",
                            "grid_err_536_535_ba_w": "",
                            "load_err_547_548_ab_w": "",
                            "load_err_548_547_ba_w": "",
                            "pv_err_553_554_ab_w": "",
                            "pv_err_554_553_ba_w": "",
                            "read_error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    print(f"[{phase.name} {idx:02d}] read error: {exc}", file=sys.stderr)

                rows.append(row)
                if idx < args.samples_per_phase:
                    time.sleep(args.interval_seconds)
    finally:
        reader.close()

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    mae_grid_ab = _safe_mae(grid_errors_ab)
    mae_grid_ba = _safe_mae(grid_errors_ba)
    mae_load_ab = _safe_mae(load_errors_ab)
    mae_load_ba = _safe_mae(load_errors_ba)

    write_markdown_summary(
        output_md=output_md,
        rows=rows,
        mae_grid_ab=mae_grid_ab,
        mae_grid_ba=mae_grid_ba,
        mae_load_ab=mae_load_ab,
        mae_load_ba=mae_load_ba,
    )

    print("\nWave 9E session completed.")
    print(f"CSV report: {output_csv}")
    print(f"Markdown summary: {output_md}")
    print(f"Grid MAE [535,536]: {mae_grid_ab}")
    print(f"Grid MAE [536,535]: {mae_grid_ba}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
