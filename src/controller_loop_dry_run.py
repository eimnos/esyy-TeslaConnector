"""Wave 3 dry-run controller loop based on Afore candidate registers."""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

try:
    from src.afore_reader import AforeReader
    from src.config import AppConfig, load_config
    from src.solar_logic import ControlSettings, calculate_target_amps, decide_charge_action
    from src.supabase_sink import SupabaseSink, SupabaseSinkConfig, SupabaseSinkError
except ModuleNotFoundError:  # Allows `python src/controller_loop_dry_run.py`
    from afore_reader import AforeReader  # type: ignore[no-redef]
    from config import AppConfig, load_config  # type: ignore[no-redef]
    from solar_logic import (  # type: ignore[no-redef]
        ControlSettings,
        calculate_target_amps,
        decide_charge_action,
    )
    from supabase_sink import SupabaseSink, SupabaseSinkConfig, SupabaseSinkError  # type: ignore[no-redef]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a Wave 3 dry-run control loop without Tesla API calls."
    )
    parser.add_argument(
        "--duration-minutes",
        type=float,
        default=30.0,
        help="Loop duration in minutes. Use 0 for infinite loop. Default: 30.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=None,
        help="Override polling interval in seconds (default: POLL_SECONDS from .env).",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="Optional hard limit of cycles (useful for smoke tests).",
    )
    parser.add_argument(
        "--initial-current-amps",
        type=int,
        default=0,
        help="Simulated current charging amps at loop start.",
    )
    parser.add_argument(
        "--log-path",
        default="data/controller_dry_run_log.csv",
        help="CSV log output path.",
    )
    return parser.parse_args()


def ensure_csv_writer(log_path: Path) -> tuple[csv.writer, TextIO]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = log_path.exists()
    csv_file = log_path.open("a", newline="", encoding="utf-8")
    writer = csv.writer(csv_file)
    if not file_exists or log_path.stat().st_size == 0:
        writer.writerow(
            [
                "timestamp_utc",
                "cycle",
                "pv_power_w",
                "grid_power_raw_w",
                "grid_sign_mode",
                "grid_sign_assumed_mode",
                "grid_sign_unknown",
                "grid_import_w",
                "grid_export_w",
                "current_amps_before",
                "target_amps",
                "action",
                "current_amps_after",
                "note",
            ]
        )
    return writer, csv_file


def cycles_from_duration(duration_minutes: float, interval_seconds: int) -> int | None:
    if duration_minutes < 0:
        raise ValueError("--duration-minutes must be >= 0")
    if duration_minutes == 0:
        return None
    total_seconds = duration_minutes * 60.0
    return max(1, int(math.ceil(total_seconds / interval_seconds)))


def create_optional_supabase_sink(config: AppConfig) -> tuple[SupabaseSink | None, str]:
    """Create Supabase sink only when explicitly enabled and configured."""

    if not config.supabase_enabled:
        return None, "disabled"

    if not config.supabase_url or not config.supabase_service_role_key:
        return None, "missing_config"

    sink_config = SupabaseSinkConfig(
        url=config.supabase_url,
        service_role_key=config.supabase_service_role_key,
    )
    return SupabaseSink(sink_config), "enabled"


def build_supabase_row(
    cycle: int,
    pv_power_w: float | None,
    grid_power_raw_w: float | None,
    grid_sign_mode: str,
    grid_sign_assumed_mode: str | None,
    grid_sign_unknown: bool | None,
    grid_import_w: float | None,
    grid_export_w: float | None,
    current_amps_before: int,
    target_amps: int | None,
    action: str,
    current_amps_after: int,
    note: str,
) -> dict[str, object]:
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "cycle": cycle,
        "pv_power_w": pv_power_w,
        "grid_power_raw_w": grid_power_raw_w,
        "grid_sign_mode": grid_sign_mode,
        "grid_sign_assumed_mode": grid_sign_assumed_mode,
        "grid_sign_unknown": grid_sign_unknown,
        "grid_import_w": grid_import_w,
        "grid_export_w": grid_export_w,
        "current_amps_before": current_amps_before,
        "target_amps": target_amps,
        "action": action,
        "current_amps_after": current_amps_after,
        "note": note,
    }


def main() -> int:
    args = parse_args()

    try:
        config = load_config()
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    interval_seconds = args.interval_seconds or config.poll_seconds
    if interval_seconds <= 0:
        print("Invalid polling interval. Must be > 0 seconds.", file=sys.stderr)
        return 2
    if args.max_cycles is not None and args.max_cycles <= 0:
        print("--max-cycles must be > 0 when provided.", file=sys.stderr)
        return 2

    try:
        duration_cycles = cycles_from_duration(args.duration_minutes, interval_seconds)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    max_cycles = args.max_cycles
    if duration_cycles is not None:
        max_cycles = min(max_cycles, duration_cycles) if max_cycles is not None else duration_cycles

    settings = ControlSettings(
        grid_export_start_w=config.grid_export_start_w,
        grid_export_stop_w=config.grid_export_stop_w,
        min_amps=config.tesla_min_amps,
        max_amps=config.tesla_max_amps,
        grid_voltage=config.grid_voltage,
    )

    log_path = Path(args.log_path)
    writer, csv_file = ensure_csv_writer(log_path)
    reader = AforeReader(config)
    supabase_sink, supabase_state = create_optional_supabase_sink(config)

    print("Wave 3 dry-run controller started (no Tesla API calls).")
    print(
        f"poll_interval={interval_seconds}s | duration_minutes={args.duration_minutes} "
        f"| max_cycles={max_cycles if max_cycles is not None else 'infinite'}"
    )
    print(
        "Afore candidates:"
        f" PV r{config.afore_pv_power_register} (scale={config.afore_pv_power_scale}),"
        f" Grid r{config.afore_grid_power_register_high}-r{config.afore_grid_power_register_low}"
        f" (scale={config.afore_grid_power_scale}, sign_mode={config.afore_grid_sign_mode})"
    )

    if config.afore_grid_sign_mode == "unknown":
        print(
            "WARNING: AFORE_GRID_SIGN_MODE is 'unknown'. "
            "Controller uses provisional assumption 'import_positive'."
        )
    if supabase_state == "disabled":
        print("Supabase sink: disabled (SUPABASE_ENABLED=false).")
    elif supabase_state == "missing_config":
        print(
            "WARNING: SUPABASE_ENABLED=true but SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY missing. "
            "Continuing without Supabase writes."
        )
    else:
        print("Supabase sink: enabled (best effort, non-blocking).")

    current_amps = max(args.initial_current_amps, 0)
    cycle = 0

    try:
        while True:
            cycle += 1
            if max_cycles is not None and cycle > max_cycles:
                break

            cycle_started_at = time.time()
            note = ""
            try:
                snapshot = reader.read_snapshot()
                target_amps = calculate_target_amps(
                    export_w=snapshot.grid_export_w,
                    min_amps=settings.min_amps,
                    max_amps=settings.max_amps,
                    grid_voltage=settings.grid_voltage,
                )
                action = decide_charge_action(
                    export_w=snapshot.grid_export_w,
                    current_amps=current_amps,
                    settings=settings,
                )

                amps_before = current_amps
                if action in {"START_CHARGE", "SET_AMPS"}:
                    current_amps = target_amps
                elif action == "STOP_CHARGE":
                    current_amps = 0

                if snapshot.grid_sign_unknown:
                    note = (
                        "GRID_SIGN_UNKNOWN;"
                        f"ASSUMED_{snapshot.grid_sign_assumed_mode.upper()}"
                    )

                print(
                    f"[cycle {cycle:04d}] "
                    f"pv={snapshot.pv_power_w:7.1f}W "
                    f"grid_raw={snapshot.grid_power_raw_w:8.1f}W "
                    f"import={snapshot.grid_import_w:7.1f}W "
                    f"export={snapshot.grid_export_w:7.1f}W "
                    f"amps={amps_before:2d}->{target_amps:2d} "
                    f"action={action}"
                    + (f" note={note}" if note else "")
                )

                writer.writerow(
                    [
                        snapshot.timestamp_utc,
                        cycle,
                        f"{snapshot.pv_power_w:.3f}",
                        f"{snapshot.grid_power_raw_w:.3f}",
                        snapshot.grid_sign_mode,
                        snapshot.grid_sign_assumed_mode,
                        str(snapshot.grid_sign_unknown).lower(),
                        f"{snapshot.grid_import_w:.3f}",
                        f"{snapshot.grid_export_w:.3f}",
                        amps_before,
                        target_amps,
                        action,
                        current_amps,
                        note,
                    ]
                )
                csv_file.flush()

                if supabase_sink is not None:
                    row = build_supabase_row(
                        cycle=cycle,
                        pv_power_w=snapshot.pv_power_w,
                        grid_power_raw_w=snapshot.grid_power_raw_w,
                        grid_sign_mode=snapshot.grid_sign_mode,
                        grid_sign_assumed_mode=snapshot.grid_sign_assumed_mode,
                        grid_sign_unknown=snapshot.grid_sign_unknown,
                        grid_import_w=snapshot.grid_import_w,
                        grid_export_w=snapshot.grid_export_w,
                        current_amps_before=amps_before,
                        target_amps=target_amps,
                        action=action,
                        current_amps_after=current_amps,
                        note=note,
                    )
                    try:
                        supabase_sink.insert_row(row)
                    except SupabaseSinkError as exc:
                        print(
                            f"[cycle {cycle:04d}] supabase write skipped: {exc}",
                            file=sys.stderr,
                        )
            except Exception as exc:
                timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                error_text = f"{type(exc).__name__}: {exc}"
                print(f"[cycle {cycle:04d}] read error: {error_text}", file=sys.stderr)
                writer.writerow(
                    [
                        timestamp,
                        cycle,
                        "",
                        "",
                        config.afore_grid_sign_mode,
                        "",
                        "",
                        "",
                        "",
                        current_amps,
                        "",
                        "READ_ERROR",
                        current_amps,
                        error_text,
                    ]
                )
                csv_file.flush()

                if supabase_sink is not None:
                    row = build_supabase_row(
                        cycle=cycle,
                        pv_power_w=None,
                        grid_power_raw_w=None,
                        grid_sign_mode=config.afore_grid_sign_mode,
                        grid_sign_assumed_mode=None,
                        grid_sign_unknown=None,
                        grid_import_w=None,
                        grid_export_w=None,
                        current_amps_before=current_amps,
                        target_amps=None,
                        action="READ_ERROR",
                        current_amps_after=current_amps,
                        note=error_text,
                    )
                    try:
                        supabase_sink.insert_row(row)
                    except SupabaseSinkError as supa_exc:
                        print(
                            f"[cycle {cycle:04d}] supabase write skipped: {supa_exc}",
                            file=sys.stderr,
                        )

            elapsed = time.time() - cycle_started_at
            sleep_seconds = max(0.0, interval_seconds - elapsed)
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
    except KeyboardInterrupt:
        print("\nDry-run loop interrupted by user.")
    finally:
        reader.close()
        if supabase_sink is not None:
            supabase_sink.close()
        csv_file.close()

    print(f"Wave 3 dry-run completed. Log file: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
