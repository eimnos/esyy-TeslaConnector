"""Read-only Tesla status script (no commands, no wake-up)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

try:
    from src.supabase_sink import SupabaseSink, SupabaseSinkConfig, SupabaseSinkError
    from src.tesla_client import (
        TeslaApiError,
        TeslaApiResponseError,
        TeslaFleetClient,
        load_tesla_config,
    )
except ModuleNotFoundError:  # Allows `python src/tesla_readonly_status.py`
    from supabase_sink import SupabaseSink, SupabaseSinkConfig, SupabaseSinkError  # type: ignore[no-redef]
    from tesla_client import (  # type: ignore[no-redef]
        TeslaApiError,
        TeslaApiResponseError,
        TeslaFleetClient,
        load_tesla_config,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read Tesla status in read-only mode (no wake-up, no commands)."
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Optional JSON output path (example: data/tesla_status_sample.json).",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Enable periodic polling using cost-aware interval.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1,
        help="Number of polling cycles in watch mode (0 = infinite).",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=None,
        help="Override polling interval seconds (default from TESLA_READONLY_POLL_SECONDS).",
    )
    parser.add_argument(
        "--insert-supabase",
        action="store_true",
        help="Best-effort insert into tesla_samples when SUPABASE_ENABLED=true.",
    )
    parser.add_argument(
        "--supabase-source",
        default="tesla_readonly_status",
        help="Source label stored in tesla_samples (default: tesla_readonly_status).",
    )
    return parser.parse_args()


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default


def create_optional_supabase_sink() -> tuple[SupabaseSink | None, str]:
    """Create Supabase sink only when explicitly enabled via env vars."""

    if not _parse_bool_env("SUPABASE_ENABLED", False):
        return None, "disabled"

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        return None, "missing_config"

    return (
        SupabaseSink(
            SupabaseSinkConfig(
                url=url,
                service_role_key=key,
            )
        ),
        "enabled",
    )


def build_status_snapshot(readonly_status: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize Tesla status payload for CLI output and optional JSON export."""

    vehicle = readonly_status.get("vehicle") or {}
    vehicle_data = readonly_status.get("vehicle_data") or {}
    charge_state = vehicle_data.get("charge_state") if isinstance(vehicle_data, dict) else None
    vehicle_state_data = (
        vehicle_data.get("vehicle_state") if isinstance(vehicle_data, dict) else None
    )

    charge_state = charge_state if isinstance(charge_state, dict) else {}
    vehicle_state_data = vehicle_state_data if isinstance(vehicle_state_data, dict) else {}

    vehicle_id = vehicle.get("id_s") or vehicle.get("id")
    timestamp_utc = datetime.now(timezone.utc).isoformat()
    snapshot = {
        "sample_timestamp": timestamp_utc,
        "timestamp_utc": timestamp_utc,
        "vehicle_id": str(vehicle_id) if vehicle_id is not None else None,
        "vehicle_state": vehicle.get("state"),
        "battery_level": _as_float(charge_state.get("battery_level")),
        "charging_state": charge_state.get("charging_state"),
        "charge_amps": _as_float(charge_state.get("charge_amps")),
        "charge_current_request": _as_float(charge_state.get("charge_current_request")),
        "charge_current_request_max": _as_float(charge_state.get("charge_current_request_max")),
        "charge_limit_soc": _as_float(charge_state.get("charge_limit_soc")),
        "odometer_km": _as_float(vehicle_state_data.get("odometer")),
        "energy_added_kwh": _as_float(charge_state.get("charge_energy_added")),
        "asleep_or_offline": bool(readonly_status.get("asleep_or_offline")),
        "skipped_vehicle_data": bool(readonly_status.get("skipped_vehicle_data")),
    }
    return snapshot


def build_tesla_sample_row(
    snapshot: Mapping[str, Any],
    *,
    source: str,
) -> dict[str, Any]:
    sample_timestamp = (
        snapshot.get("sample_timestamp")
        or snapshot.get("timestamp_utc")
        or datetime.now(timezone.utc).isoformat()
    )

    return {
        "sample_timestamp": sample_timestamp,
        "vehicle_id": snapshot.get("vehicle_id"),
        "vehicle_state": snapshot.get("vehicle_state"),
        "battery_level": snapshot.get("battery_level"),
        "charging_state": snapshot.get("charging_state"),
        "charge_amps": snapshot.get("charge_amps"),
        "charge_current_request": snapshot.get("charge_current_request"),
        "charge_current_request_max": snapshot.get("charge_current_request_max"),
        "charge_limit_soc": snapshot.get("charge_limit_soc"),
        "odometer_km": snapshot.get("odometer_km"),
        "energy_added_kwh": snapshot.get("energy_added_kwh"),
        "asleep_or_offline": bool(snapshot.get("asleep_or_offline")),
        "skipped_vehicle_data": bool(snapshot.get("skipped_vehicle_data")),
        "source": source,
    }


def print_snapshot(snapshot: Mapping[str, Any]) -> None:
    print(f"sample_timestamp      : {snapshot.get('sample_timestamp')}")
    print(f"vehicle_id            : {snapshot.get('vehicle_id')}")
    print(f"vehicle_state         : {snapshot.get('vehicle_state')}")
    print(f"battery_level         : {snapshot.get('battery_level')}")
    print(f"charging_state        : {snapshot.get('charging_state')}")
    print(f"charge_amps           : {snapshot.get('charge_amps')}")
    print(f"charge_current_req    : {snapshot.get('charge_current_request')}")
    print(f"charge_current_req_max: {snapshot.get('charge_current_request_max')}")
    print(f"charge_limit_soc      : {snapshot.get('charge_limit_soc')}")
    print(f"odometer_km           : {snapshot.get('odometer_km')}")
    print(f"energy_added_kwh      : {snapshot.get('energy_added_kwh')}")

    if snapshot.get("asleep_or_offline"):
        print("note                  : vehicle asleep/offline -> vehicle_data skipped (no wake-up)")


def maybe_write_json(snapshot: Mapping[str, Any], output_json: str | None) -> None:
    if not output_json:
        return
    path = Path(output_json)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as json_file:
        json.dump(snapshot, json_file, ensure_ascii=False, indent=2)
    print(f"saved_json            : {path}")


def maybe_insert_supabase(
    *,
    sink: SupabaseSink | None,
    snapshot: Mapping[str, Any],
    source: str,
) -> str | None:
    if sink is None:
        return None
    row = build_tesla_sample_row(snapshot, source=source)
    try:
        sink.insert_tesla_sample(row)
    except SupabaseSinkError as exc:
        error_text = str(exc)
        if "PGRST204" not in error_text:
            return error_text

        # Backward compatibility: insert with reduced columns when cloud schema
        # has not been updated yet. This keeps read-only monitoring non-blocking.
        reduced_row = dict(row)
        dropped_columns: list[str] = []
        while True:
            missing_prefix = "Could not find the '"
            missing_suffix = "' column of 'tesla_samples'"
            start = error_text.find(missing_prefix)
            end = error_text.find(missing_suffix)
            if start == -1 or end == -1:
                return error_text

            column_name = error_text[start + len(missing_prefix) : end]
            if not column_name or column_name not in reduced_row:
                return error_text

            reduced_row.pop(column_name, None)
            dropped_columns.append(column_name)
            try:
                sink.insert_tesla_sample(reduced_row)
                dropped = ", ".join(dropped_columns)
                return (
                    "warning: inserted tesla sample without columns "
                    f"[{dropped}] due to stale schema. Apply db/schema.sql on Supabase."
                )
            except SupabaseSinkError as retry_exc:
                error_text = str(retry_exc)
                if "PGRST204" not in error_text:
                    return error_text
    return None


def main() -> int:
    args = parse_args()
    if args.iterations < 0:
        print("--iterations must be >= 0", file=sys.stderr)
        return 2
    if args.poll_seconds is not None and args.poll_seconds <= 0:
        print("--poll-seconds must be > 0", file=sys.stderr)
        return 2

    try:
        config = load_tesla_config()
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    poll_seconds = args.poll_seconds or config.readonly_poll_seconds
    if args.watch and poll_seconds < 60:
        print(
            f"Warning: poll interval set to {poll_seconds}s. "
            "For cost-aware mode prefer >= 600s while idle.",
            file=sys.stderr,
        )

    print("Tesla read-only mode active.")
    print(f"commands_enabled      : {config.commands_enabled}")
    print(f"allow_wake_up         : {config.allow_wake_up}")
    print("safety                : no command endpoints and no wake-up calls")

    if config.commands_enabled:
        print(
            "Warning: TESLA_COMMANDS_ENABLED=true in env, but this script remains read-only.",
            file=sys.stderr,
        )
    if config.allow_wake_up:
        print(
            "Warning: TESLA_ALLOW_WAKE_UP=true in env, but this script never performs wake-up.",
            file=sys.stderr,
        )

    supabase_sink: SupabaseSink | None = None
    if args.insert_supabase:
        supabase_sink, supabase_state = create_optional_supabase_sink()
        if supabase_state == "disabled":
            print("Supabase insert       : disabled (SUPABASE_ENABLED=false)")
        elif supabase_state == "missing_config":
            print(
                "Supabase insert       : missing config (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY)",
                file=sys.stderr,
            )
        else:
            print("Supabase insert       : enabled (best effort)")

    client = TeslaFleetClient(config=config)
    max_iterations = args.iterations if args.watch else 1
    cycle = 0
    try:
        while True:
            cycle += 1
            if max_iterations != 0 and cycle > max_iterations:
                break
            try:
                status = client.get_readonly_status()
                snapshot = build_status_snapshot(status)
            except (TeslaApiError, TeslaApiResponseError) as exc:
                print(f"Tesla read-only error: {exc}", file=sys.stderr)
                return 1

            print(f"\n--- Tesla Read-Only Snapshot #{cycle} ---")
            print_snapshot(snapshot)
            maybe_write_json(snapshot, args.output_json)

            if args.insert_supabase:
                supabase_error = maybe_insert_supabase(
                    sink=supabase_sink,
                    snapshot=snapshot,
                    source=args.supabase_source,
                )
                if supabase_error:
                    if supabase_error.startswith("warning:"):
                        print(f"supabase_insert_warning: {supabase_error}", file=sys.stderr)
                    else:
                        print(f"supabase_insert_error : {supabase_error}", file=sys.stderr)
                elif supabase_sink is not None:
                    print("supabase_insert       : ok")

            if not args.watch:
                break
            if max_iterations != 0 and cycle >= max_iterations:
                break
            time.sleep(poll_seconds)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        if supabase_sink is not None:
            supabase_sink.close()
        client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
