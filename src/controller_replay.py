"""Wave 11A.2S synthetic surplus replay (no real device calls)."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    from src.solar_tesla_controller_dry_run import (
        ControllerState,
        GuardrailSettings,
        evaluate_simulated_decision,
    )
except ModuleNotFoundError:  # Allows `python src/controller_replay.py`
    from solar_tesla_controller_dry_run import (  # type: ignore[no-redef]
        ControllerState,
        GuardrailSettings,
        evaluate_simulated_decision,
    )


RESULT_COLUMNS = [
    "cycle",
    "scenario",
    "pv_power_w",
    "load_power_w",
    "grid_power_w",
    "import_w",
    "export_w",
    "current_amps_before",
    "target_amps",
    "action",
    "current_amps_after",
    "reason",
    "consecutive_above_start",
    "consecutive_below_stop",
    "cooldown_active",
    "notes",
]


@dataclass(frozen=True, slots=True)
class ReplayScenario:
    scenario: str
    pv_power_w: float
    load_power_w: float
    grid_power_w: float
    current_amps: int | None = None
    notes: str = ""

    @property
    def import_w(self) -> float:
        return max(self.grid_power_w, 0.0)

    @property
    def export_w(self) -> float:
        return max(-self.grid_power_w, 0.0)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay synthetic inverter scenarios against controller decision logic."
    )
    parser.add_argument(
        "--input-path",
        default="data/controller_replay_scenarios.csv",
        help="Input scenarios CSV path.",
    )
    parser.add_argument(
        "--output-path",
        default="data/controller_replay_results.csv",
        help="Output results CSV path.",
    )
    parser.add_argument("--grid-voltage", type=float, default=230.0)
    parser.add_argument("--min-amps", type=int, default=6)
    parser.add_argument("--max-amps", type=int, default=16)
    parser.add_argument("--start-threshold-w", type=float, default=1600.0)
    parser.add_argument("--stop-threshold-w", type=float, default=900.0)
    parser.add_argument("--min-delta-amps", type=int, default=2)
    parser.add_argument("--start-confirm-cycles", type=int, default=2)
    parser.add_argument("--stop-confirm-cycles", type=int, default=2)
    parser.add_argument("--cooldown-cycles", type=int, default=2)
    parser.add_argument("--initial-current-amps", type=int, default=0)
    return parser.parse_args(argv)


def _parse_float(field: str, raw_value: str, *, row_index: int) -> float:
    try:
        return float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid numeric value for {field!r} at row {row_index}: {raw_value!r}"
        ) from exc


def _parse_optional_int(raw_value: str, *, field: str, row_index: int) -> int | None:
    if raw_value is None or raw_value.strip() == "":
        return None
    try:
        value = int(float(raw_value))
    except ValueError as exc:
        raise ValueError(
            f"Invalid numeric value for {field!r} at row {row_index}: {raw_value!r}"
        ) from exc
    if value < 0:
        raise ValueError(f"{field!r} must be >= 0 at row {row_index}, got: {value}")
    return value


def load_scenarios_csv(path: Path) -> list[ReplayScenario]:
    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {path}")

    with path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        expected_columns = {"scenario", "pv_power_w", "load_power_w", "grid_power_w"}
        if reader.fieldnames is None:
            raise ValueError(f"Empty CSV: {path}")
        missing = expected_columns.difference(reader.fieldnames)
        if missing:
            missing_text = ", ".join(sorted(missing))
            raise ValueError(
                f"Missing required columns in {path}: {missing_text}"
            )

        scenarios: list[ReplayScenario] = []
        for row_index, row in enumerate(reader, start=2):
            scenario_name = (row.get("scenario") or "").strip() or f"row_{row_index}"
            pv_power_w = _parse_float("pv_power_w", row.get("pv_power_w", ""), row_index=row_index)
            load_power_w = _parse_float(
                "load_power_w", row.get("load_power_w", ""), row_index=row_index
            )
            grid_power_w = _parse_float(
                "grid_power_w", row.get("grid_power_w", ""), row_index=row_index
            )
            current_amps = _parse_optional_int(
                row.get("current_amps", ""),
                field="current_amps",
                row_index=row_index,
            )
            notes = (row.get("notes") or "").strip()
            scenarios.append(
                ReplayScenario(
                    scenario=scenario_name,
                    pv_power_w=pv_power_w,
                    load_power_w=load_power_w,
                    grid_power_w=grid_power_w,
                    current_amps=current_amps,
                    notes=notes,
                )
            )

    if not scenarios:
        raise ValueError(f"No scenario rows found in {path}")
    return scenarios


def build_guardrail_settings(args: argparse.Namespace) -> GuardrailSettings:
    if args.grid_voltage <= 0:
        raise ValueError("--grid-voltage must be > 0")
    if args.min_amps <= 0 or args.max_amps <= 0:
        raise ValueError("--min-amps and --max-amps must be > 0")
    if args.max_amps < args.min_amps:
        raise ValueError("--max-amps must be >= --min-amps")
    if args.stop_threshold_w < 0 or args.start_threshold_w < 0:
        raise ValueError("--start-threshold-w and --stop-threshold-w must be >= 0")
    if args.start_threshold_w < args.stop_threshold_w:
        raise ValueError("--start-threshold-w must be >= --stop-threshold-w")
    if args.min_delta_amps <= 0:
        raise ValueError("--min-delta-amps must be > 0")
    if args.start_confirm_cycles <= 0 or args.stop_confirm_cycles <= 0:
        raise ValueError("--start-confirm-cycles and --stop-confirm-cycles must be > 0")
    if args.cooldown_cycles < 0:
        raise ValueError("--cooldown-cycles must be >= 0")
    if args.initial_current_amps < 0:
        raise ValueError("--initial-current-amps must be >= 0")

    return GuardrailSettings(
        start_threshold_w=float(args.start_threshold_w),
        stop_threshold_w=float(args.stop_threshold_w),
        min_amps=int(args.min_amps),
        max_amps=int(args.max_amps),
        grid_voltage=float(args.grid_voltage),
        min_delta_amps=int(args.min_delta_amps),
        start_confirm_cycles=int(args.start_confirm_cycles),
        stop_confirm_cycles=int(args.stop_confirm_cycles),
        cooldown_cycles=int(args.cooldown_cycles),
    )


def replay_scenarios(
    scenarios: Iterable[ReplayScenario],
    *,
    guardrails: GuardrailSettings,
    initial_current_amps: int = 0,
) -> list[dict[str, Any]]:
    state = ControllerState(
        simulated_current_amps=max(0, int(initial_current_amps)),
        consecutive_above_start=0,
        consecutive_below_stop=0,
        last_decision_cycle=None,
    )
    results: list[dict[str, Any]] = []

    for cycle, scenario in enumerate(scenarios, start=1):
        current_amps_for_decision = (
            max(0, scenario.current_amps)
            if scenario.current_amps is not None
            else state.simulated_current_amps
        )
        decision, state = evaluate_simulated_decision(
            cycle=cycle,
            export_w=scenario.export_w,
            current_amps=current_amps_for_decision,
            state=state,
            settings=guardrails,
        )
        results.append(
            {
                "cycle": cycle,
                "scenario": scenario.scenario,
                "pv_power_w": f"{scenario.pv_power_w:.3f}",
                "load_power_w": f"{scenario.load_power_w:.3f}",
                "grid_power_w": f"{scenario.grid_power_w:.3f}",
                "import_w": f"{scenario.import_w:.3f}",
                "export_w": f"{scenario.export_w:.3f}",
                "current_amps_before": decision.current_amps_before,
                "target_amps": decision.target_amps,
                "action": decision.action,
                "current_amps_after": decision.current_amps_after,
                "reason": f"{decision.reason};SIMULATED_REPLAY",
                "consecutive_above_start": decision.consecutive_above_start,
                "consecutive_below_stop": decision.consecutive_below_stop,
                "cooldown_active": str(decision.cooldown_active).lower(),
                "notes": scenario.notes,
            }
        )
    return results


def write_results_csv(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    row_list = list(rows)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=RESULT_COLUMNS)
        writer.writeheader()
        for row in row_list:
            writer.writerow(row)
    return len(row_list)


def _print_summary(rows: list[dict[str, Any]]) -> None:
    action_counter = Counter(str(row.get("action", "UNKNOWN")) for row in rows)
    print(
        "Replay summary: "
        + ", ".join(f"{action}={count}" for action, count in sorted(action_counter.items()))
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        guardrails = build_guardrail_settings(args)
        scenarios = load_scenarios_csv(Path(args.input_path))
        results = replay_scenarios(
            scenarios,
            guardrails=guardrails,
            initial_current_amps=args.initial_current_amps,
        )
        written = write_results_csv(Path(args.output_path), results)
    except (ValueError, FileNotFoundError) as exc:
        print(f"Replay setup error: {exc}")
        return 2

    _print_summary(results)
    print(
        f"Replay completed: {written} cycles written to {args.output_path} "
        "(synthetic only, no Afore/Tesla commands)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
