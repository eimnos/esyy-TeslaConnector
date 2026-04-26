"""Dry-run controller loop without Tesla API calls."""

from __future__ import annotations

import argparse
import sys

try:
    from src.config import load_config
    from src.solar_logic import (
        ControlSettings,
        calculate_target_amps,
        decide_charge_action,
    )
except ModuleNotFoundError:  # Allows `python src/controller_dry_run.py`
    from config import load_config  # type: ignore[no-redef]
    from solar_logic import (  # type: ignore[no-redef]
        ControlSettings,
        calculate_target_amps,
        decide_charge_action,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local dry-run decisions without contacting Tesla APIs."
    )
    parser.add_argument(
        "--export-w",
        type=float,
        help="Single export value to simulate (watts). If omitted, built-in samples are used.",
    )
    parser.add_argument(
        "--current-amps",
        type=int,
        default=0,
        help="Current charging amps for the first decision cycle.",
    )
    return parser.parse_args()


def print_decision(export_w: float, current_amps: int, settings: ControlSettings) -> tuple[str, int]:
    target_amps = calculate_target_amps(
        export_w=export_w,
        min_amps=settings.min_amps,
        max_amps=settings.max_amps,
        grid_voltage=settings.grid_voltage,
    )
    action = decide_charge_action(export_w=export_w, current_amps=current_amps, settings=settings)

    print(
        f"export_w={export_w:7.1f}W | current_amps={current_amps:2d} | "
        f"target_amps={target_amps:2d} | action={action}"
    )
    return action, target_amps


def main() -> int:
    args = parse_args()
    try:
        config = load_config()
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    settings = ControlSettings(
        grid_export_start_w=config.grid_export_start_w,
        grid_export_stop_w=config.grid_export_stop_w,
        min_amps=config.tesla_min_amps,
        max_amps=config.tesla_max_amps,
        grid_voltage=config.grid_voltage,
    )

    current_amps = max(args.current_amps, 0)

    print("Dry run mode: Tesla API calls are disabled.")
    print(
        "Settings:"
        f" start={settings.grid_export_start_w}W,"
        f" stop={settings.grid_export_stop_w}W,"
        f" amps={settings.min_amps}-{settings.max_amps},"
        f" voltage={settings.grid_voltage}V"
    )

    export_samples = [args.export_w] if args.export_w is not None else [400, 950, 1650, 2600, 3800]

    for export_w in export_samples:
        action, target_amps = print_decision(export_w, current_amps, settings)

        if action in {"START_CHARGE", "SET_AMPS"}:
            current_amps = target_amps
        elif action == "STOP_CHARGE":
            current_amps = 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
