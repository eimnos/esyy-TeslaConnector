"""Wave 11A full controller dry-run using Afore + Tesla read-only data."""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, TextIO

try:
    from src.afore_reader import AforeReader, AforeSnapshot
    from src.config import AppConfig, load_config
    from src.solar_logic import calculate_target_amps, should_update_amps
    from src.supabase_sink import SupabaseSink, SupabaseSinkConfig, SupabaseSinkError
    from src.tesla_client import (
        TeslaApiError,
        TeslaApiResponseError,
        TeslaFleetClient,
        load_tesla_config,
    )
    from src.tesla_readonly_status import build_status_snapshot
except ModuleNotFoundError:  # Allows `python src/solar_tesla_controller_dry_run.py`
    from afore_reader import AforeReader, AforeSnapshot  # type: ignore[no-redef]
    from config import AppConfig, load_config  # type: ignore[no-redef]
    from solar_logic import calculate_target_amps, should_update_amps  # type: ignore[no-redef]
    from supabase_sink import SupabaseSink, SupabaseSinkConfig, SupabaseSinkError  # type: ignore[no-redef]
    from tesla_client import (  # type: ignore[no-redef]
        TeslaApiError,
        TeslaApiResponseError,
        TeslaFleetClient,
        load_tesla_config,
    )
    from tesla_readonly_status import build_status_snapshot  # type: ignore[no-redef]


@dataclass(frozen=True, slots=True)
class GuardrailSettings:
    start_threshold_w: float
    stop_threshold_w: float
    min_amps: int
    max_amps: int
    grid_voltage: float
    min_delta_amps: int
    start_confirm_cycles: int
    stop_confirm_cycles: int
    cooldown_cycles: int


@dataclass(frozen=True, slots=True)
class ControllerState:
    simulated_current_amps: int
    consecutive_above_start: int
    consecutive_below_stop: int
    last_decision_cycle: int | None


@dataclass(frozen=True, slots=True)
class SimulatedDecision:
    action: str
    current_amps_before: int
    current_amps_after: int
    target_amps: int
    reason: str
    consecutive_above_start: int
    consecutive_below_stop: int
    cooldown_active: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Wave 11A dry-run controller with Afore + Tesla read-only telemetry."
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
        help="Override polling interval in seconds (default: POLL_SECONDS).",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="Optional hard cycle limit, useful for short smoke tests.",
    )
    parser.add_argument(
        "--initial-current-amps",
        type=int,
        default=0,
        help="Fallback simulated amps when Tesla read-only value is unavailable.",
    )
    parser.add_argument(
        "--min-delta-amps",
        type=int,
        default=2,
        help="Minimum amp delta required for SET_AMPS decision (default: 2).",
    )
    parser.add_argument(
        "--start-confirm-cycles",
        type=int,
        default=2,
        help="Required consecutive cycles above start threshold before START_CHARGE.",
    )
    parser.add_argument(
        "--stop-confirm-cycles",
        type=int,
        default=2,
        help="Required consecutive cycles below stop threshold before STOP_CHARGE.",
    )
    parser.add_argument(
        "--cooldown-cycles",
        type=int,
        default=2,
        help="Minimum cycles between two simulated decisions.",
    )
    parser.add_argument(
        "--log-path",
        default="data/solar_tesla_controller_dry_run_log.csv",
        help="CSV output path.",
    )
    parser.add_argument(
        "--disable-supabase",
        action="store_true",
        help="Skip Supabase writes even if SUPABASE_ENABLED=true.",
    )
    return parser.parse_args()


def cycles_from_duration(duration_minutes: float, interval_seconds: int) -> int | None:
    if duration_minutes < 0:
        raise ValueError("--duration-minutes must be >= 0")
    if duration_minutes == 0:
        return None
    total_seconds = duration_minutes * 60.0
    return max(1, int(math.ceil(total_seconds / interval_seconds)))


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
                "simulated",
                "grid_power_w",
                "export_w",
                "import_w",
                "load_power_w",
                "pv_power_w",
                "vehicle_state",
                "charging_state",
                "charge_current_request",
                "current_amps_before",
                "target_amps",
                "action",
                "current_amps_after",
                "reason",
            ]
        )
    return writer, csv_file


def create_optional_supabase_sink(
    config: AppConfig, *, disable_supabase: bool = False
) -> tuple[SupabaseSink | None, str]:
    if disable_supabase:
        return None, "forced_disabled"
    if not config.supabase_enabled:
        return None, "disabled"
    if not config.supabase_url or not config.supabase_service_role_key:
        return None, "missing_config"

    sink_config = SupabaseSinkConfig(
        url=config.supabase_url,
        service_role_key=config.supabase_service_role_key,
    )
    return SupabaseSink(sink_config), "enabled"


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _extract_tesla_amps(snapshot: Mapping[str, Any] | None) -> int | None:
    if not snapshot:
        return None
    value = snapshot.get("charge_current_request")
    amps = _to_int(value)
    if amps is not None:
        return max(amps, 0)
    return None


def _is_cooldown_active(
    *, cycle: int, last_decision_cycle: int | None, cooldown_cycles: int
) -> bool:
    if last_decision_cycle is None:
        return False
    return (cycle - last_decision_cycle) < cooldown_cycles


def evaluate_simulated_decision(
    *,
    cycle: int,
    export_w: float,
    current_amps: int,
    state: ControllerState,
    settings: GuardrailSettings,
) -> tuple[SimulatedDecision, ControllerState]:
    target_amps = calculate_target_amps(
        export_w=export_w,
        min_amps=settings.min_amps,
        max_amps=settings.max_amps,
        grid_voltage=settings.grid_voltage,
    )
    current = max(0, int(current_amps))
    above = state.consecutive_above_start
    below = state.consecutive_below_stop
    last_decision_cycle = state.last_decision_cycle
    cooldown_active = _is_cooldown_active(
        cycle=cycle,
        last_decision_cycle=last_decision_cycle,
        cooldown_cycles=settings.cooldown_cycles,
    )
    action = "NO_ACTION"
    reason = "NO_ACTION"
    current_after = current

    if current <= 0:
        below = 0
        if export_w >= settings.start_threshold_w and target_amps > 0:
            above += 1
        else:
            above = 0

        if target_amps <= 0:
            reason = "TARGET_AMPS_ZERO"
        elif export_w < settings.start_threshold_w:
            reason = (
                f"WAIT_START_THRESHOLD({export_w:.1f}<{settings.start_threshold_w:.1f})"
            )
        elif above < settings.start_confirm_cycles:
            reason = f"WAIT_START_CONFIRM({above}/{settings.start_confirm_cycles})"
        elif cooldown_active:
            reason = "COOLDOWN_ACTIVE_FOR_START"
        else:
            action = "START_CHARGE"
            current_after = max(settings.min_amps, target_amps)
            reason = f"START_AFTER_CONFIRM({settings.start_confirm_cycles})"
            above = 0
            last_decision_cycle = cycle
    else:
        above = 0
        stop_condition = export_w <= settings.stop_threshold_w or target_amps <= 0
        if stop_condition:
            below += 1
        else:
            below = 0

        if stop_condition and below < settings.stop_confirm_cycles:
            reason = f"WAIT_STOP_CONFIRM({below}/{settings.stop_confirm_cycles})"
        elif stop_condition and below >= settings.stop_confirm_cycles:
            if cooldown_active:
                reason = "COOLDOWN_ACTIVE_FOR_STOP"
            else:
                action = "STOP_CHARGE"
                current_after = 0
                reason = f"STOP_AFTER_CONFIRM({settings.stop_confirm_cycles})"
                below = 0
                last_decision_cycle = cycle
        elif should_update_amps(current, target_amps, min_delta=settings.min_delta_amps):
            if cooldown_active:
                reason = "COOLDOWN_ACTIVE_FOR_SET_AMPS"
            else:
                action = "SET_AMPS"
                current_after = target_amps
                reason = (
                    f"SET_AMPS_DELTA({abs(target_amps - current)}>="
                    f"{settings.min_delta_amps})"
                )
                last_decision_cycle = cycle
        else:
            reason = f"DELTA_LT_MIN({settings.min_delta_amps})"

    decision = SimulatedDecision(
        action=action,
        current_amps_before=current,
        current_amps_after=current_after,
        target_amps=target_amps,
        reason=reason,
        consecutive_above_start=above,
        consecutive_below_stop=below,
        cooldown_active=cooldown_active,
    )
    next_state = ControllerState(
        simulated_current_amps=current_after if action != "NO_ACTION" else current,
        consecutive_above_start=above,
        consecutive_below_stop=below,
        last_decision_cycle=last_decision_cycle,
    )
    return decision, next_state


def _extract_missing_column(error_text: str, table: str) -> str | None:
    missing_prefix = "Could not find the '"
    missing_suffix = f"' column of '{table}'"
    start = error_text.find(missing_prefix)
    end = error_text.find(missing_suffix)
    if start == -1 or end == -1:
        return None
    return error_text[start + len(missing_prefix) : end] or None


def insert_controller_decision_best_effort(
    *,
    sink: SupabaseSink | None,
    row: Mapping[str, Any],
) -> str | None:
    if sink is None:
        return None

    payload = dict(row)
    try:
        sink.insert_controller_decision(payload)
        return None
    except SupabaseSinkError as exc:
        error_text = str(exc)
        if "PGRST204" not in error_text:
            return error_text

        dropped_columns: list[str] = []
        while True:
            missing_column = _extract_missing_column(error_text, "controller_decisions")
            if not missing_column or missing_column not in payload:
                return error_text
            payload.pop(missing_column, None)
            dropped_columns.append(missing_column)
            try:
                sink.insert_controller_decision(payload)
                return (
                    "warning: inserted controller decision without columns "
                    f"[{', '.join(dropped_columns)}] due to stale schema. "
                    "Apply db/schema.sql on Supabase."
                )
            except SupabaseSinkError as retry_exc:
                error_text = str(retry_exc)
                if "PGRST204" not in error_text:
                    return error_text


def build_controller_decision_row(
    *,
    sample_timestamp: str,
    cycle: int,
    snapshot: AforeSnapshot,
    decision: SimulatedDecision,
    reason: str,
) -> dict[str, Any]:
    return {
        "sample_timestamp": sample_timestamp,
        "cycle": cycle,
        "simulated": True,
        "grid_power_w": snapshot.grid_power_raw_w,
        "export_w": snapshot.grid_export_w,
        "import_w": snapshot.grid_import_w,
        "load_power_w": snapshot.load_power_w,
        "pv_power_w": snapshot.pv_power_w,
        "current_amps_before": decision.current_amps_before,
        "current_amps": decision.current_amps_before,
        "target_amps": decision.target_amps,
        "action": decision.action,
        "current_amps_after": decision.current_amps_after,
        "reason": reason,
        "note": reason,
    }


def main() -> int:
    args = parse_args()
    if args.interval_seconds is not None and args.interval_seconds <= 0:
        print("--interval-seconds must be > 0", file=sys.stderr)
        return 2
    if args.max_cycles is not None and args.max_cycles <= 0:
        print("--max-cycles must be > 0 when provided", file=sys.stderr)
        return 2
    if args.min_delta_amps <= 0:
        print("--min-delta-amps must be > 0", file=sys.stderr)
        return 2
    if args.start_confirm_cycles <= 0 or args.stop_confirm_cycles <= 0:
        print("--start-confirm-cycles and --stop-confirm-cycles must be > 0", file=sys.stderr)
        return 2
    if args.cooldown_cycles < 0:
        print("--cooldown-cycles must be >= 0", file=sys.stderr)
        return 2

    try:
        app_config = load_config()
        tesla_config = load_tesla_config()
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    interval_seconds = args.interval_seconds or app_config.poll_seconds
    try:
        duration_cycles = cycles_from_duration(args.duration_minutes, interval_seconds)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    max_cycles = args.max_cycles
    if duration_cycles is not None:
        max_cycles = min(max_cycles, duration_cycles) if max_cycles is not None else duration_cycles

    guardrails = GuardrailSettings(
        start_threshold_w=app_config.grid_export_start_w,
        stop_threshold_w=app_config.grid_export_stop_w,
        min_amps=app_config.tesla_min_amps,
        max_amps=app_config.tesla_max_amps,
        grid_voltage=app_config.grid_voltage,
        min_delta_amps=args.min_delta_amps,
        start_confirm_cycles=args.start_confirm_cycles,
        stop_confirm_cycles=args.stop_confirm_cycles,
        cooldown_cycles=args.cooldown_cycles,
    )

    supabase_sink, supabase_state = create_optional_supabase_sink(
        app_config, disable_supabase=args.disable_supabase
    )
    reader = AforeReader(app_config)
    tesla_client = TeslaFleetClient(tesla_config)
    log_writer, csv_file = ensure_csv_writer(Path(args.log_path))
    state = ControllerState(
        simulated_current_amps=max(0, args.initial_current_amps),
        consecutive_above_start=0,
        consecutive_below_stop=0,
        last_decision_cycle=None,
    )

    print("Wave 11A dry-run controller started (no Tesla commands).")
    print(
        f"poll_interval={interval_seconds}s | duration_minutes={args.duration_minutes} "
        f"| max_cycles={max_cycles if max_cycles is not None else 'infinite'}"
    )
    print(
        "Afore registers:"
        f" PV r{app_config.afore_pv_power_register},"
        f" Grid r{app_config.afore_grid_power_register_high}-{app_config.afore_grid_power_register_low},"
        f" Load r{app_config.afore_load_power_register_high}-{app_config.afore_load_power_register_low}"
    )
    if tesla_config.allow_wake_up:
        print(
            "WARNING: TESLA_ALLOW_WAKE_UP=true in env, but this script never performs wake-up.",
            file=sys.stderr,
        )
    if tesla_config.commands_enabled:
        print(
            "WARNING: TESLA_COMMANDS_ENABLED=true in env, but this script is simulation-only.",
            file=sys.stderr,
        )
    if not app_config.grid_automation_enabled:
        print(
            "GRID_AUTOMATION_ENABLED=false: safe simulation mode active (decisions are not sent)."
        )
    if supabase_state == "enabled":
        print("Supabase sink: enabled (best effort).")
    elif supabase_state == "disabled":
        print("Supabase sink: disabled (SUPABASE_ENABLED=false).")
    elif supabase_state == "forced_disabled":
        print("Supabase sink: disabled by --disable-supabase.")
    else:
        print(
            "Supabase sink: missing config (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY).",
            file=sys.stderr,
        )

    cycle = 0
    try:
        while True:
            cycle += 1
            if max_cycles is not None and cycle > max_cycles:
                break
            cycle_started_at = time.time()

            try:
                inverter = reader.read_snapshot()
                tesla_error = ""
                tesla_snapshot: Mapping[str, Any] | None = None
                try:
                    readonly_status = tesla_client.get_readonly_status()
                    tesla_snapshot = build_status_snapshot(readonly_status)
                except (TeslaApiError, TeslaApiResponseError) as exc:
                    tesla_error = f"{type(exc).__name__}: {exc}"

                tesla_current_amps = _extract_tesla_amps(tesla_snapshot)
                current_for_decision = (
                    tesla_current_amps
                    if tesla_current_amps is not None
                    else state.simulated_current_amps
                )
                decision, next_state = evaluate_simulated_decision(
                    cycle=cycle,
                    export_w=inverter.grid_export_w,
                    current_amps=current_for_decision,
                    state=state,
                    settings=guardrails,
                )

                reason_parts = [decision.reason]
                if tesla_snapshot is None:
                    reason_parts.append("TESLA_STATUS_UNAVAILABLE")
                else:
                    if tesla_snapshot.get("asleep_or_offline"):
                        reason_parts.append("TESLA_ASLEEP_OR_OFFLINE")
                if tesla_error:
                    reason_parts.append(f"TESLA_READ_ERROR={tesla_error}")
                reason_parts.append("SIMULATED_ONLY")
                final_reason = ";".join(reason_parts)

                vehicle_state = tesla_snapshot.get("vehicle_state") if tesla_snapshot else None
                charging_state = tesla_snapshot.get("charging_state") if tesla_snapshot else None
                charge_current_request = (
                    tesla_snapshot.get("charge_current_request") if tesla_snapshot else None
                )

                print(
                    f"[cycle {cycle:04d}] "
                    f"pv={inverter.pv_power_w:7.1f}W "
                    f"load={inverter.load_power_w:7.1f}W "
                    f"grid={inverter.grid_power_raw_w:8.1f}W "
                    f"import={inverter.grid_import_w:7.1f}W "
                    f"export={inverter.grid_export_w:7.1f}W "
                    f"amps={decision.current_amps_before:2d}->{decision.target_amps:2d} "
                    f"action={decision.action} reason={final_reason}"
                )

                log_writer.writerow(
                    [
                        inverter.timestamp_utc,
                        cycle,
                        "true",
                        f"{inverter.grid_power_raw_w:.3f}",
                        f"{inverter.grid_export_w:.3f}",
                        f"{inverter.grid_import_w:.3f}",
                        f"{inverter.load_power_w:.3f}",
                        f"{inverter.pv_power_w:.3f}",
                        vehicle_state if vehicle_state is not None else "",
                        charging_state if charging_state is not None else "",
                        charge_current_request if charge_current_request is not None else "",
                        decision.current_amps_before,
                        decision.target_amps,
                        decision.action,
                        decision.current_amps_after,
                        final_reason,
                    ]
                )
                csv_file.flush()

                row = build_controller_decision_row(
                    sample_timestamp=inverter.timestamp_utc,
                    cycle=cycle,
                    snapshot=inverter,
                    decision=decision,
                    reason=final_reason,
                )
                supabase_error = insert_controller_decision_best_effort(
                    sink=supabase_sink,
                    row=row,
                )
                if supabase_error:
                    print(
                        f"[cycle {cycle:04d}] supabase write skipped: {supabase_error}",
                        file=sys.stderr,
                    )

                state = next_state
            except Exception as exc:
                timestamp = datetime.now(timezone.utc).isoformat()
                error_text = f"{type(exc).__name__}: {exc}"
                print(f"[cycle {cycle:04d}] dry-run error: {error_text}", file=sys.stderr)
                log_writer.writerow(
                    [
                        timestamp,
                        cycle,
                        "true",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        state.simulated_current_amps,
                        "",
                        "NO_ACTION",
                        state.simulated_current_amps,
                        error_text,
                    ]
                )
                csv_file.flush()

            elapsed = time.time() - cycle_started_at
            sleep_seconds = max(0.0, interval_seconds - elapsed)
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        reader.close()
        tesla_client.close()
        if supabase_sink is not None:
            supabase_sink.close()
        csv_file.close()

    print(f"Wave 11A dry-run completed. Log file: {args.log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
