"""Read-only Tesla status script (no commands, no wake-up)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

try:
    from src.tesla_client import (
        TeslaApiError,
        TeslaApiResponseError,
        TeslaFleetClient,
        load_tesla_config,
    )
except ModuleNotFoundError:  # Allows `python src/tesla_readonly_status.py`
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
    return parser.parse_args()


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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

    timestamp_utc = datetime.now(timezone.utc).isoformat()
    snapshot = {
        "timestamp_utc": timestamp_utc,
        "vehicle_state": vehicle.get("state"),
        "battery_level": _as_float(charge_state.get("battery_level")),
        "charging_state": charge_state.get("charging_state"),
        "charge_amps": _as_float(charge_state.get("charge_amps")),
        "charge_limit_soc": _as_float(charge_state.get("charge_limit_soc")),
        "odometer_km": _as_float(vehicle_state_data.get("odometer")),
        "asleep_or_offline": bool(readonly_status.get("asleep_or_offline")),
        "skipped_vehicle_data": bool(readonly_status.get("skipped_vehicle_data")),
    }
    return snapshot


def print_snapshot(snapshot: Mapping[str, Any]) -> None:
    print(f"timestamp_utc : {snapshot.get('timestamp_utc')}")
    print(f"vehicle_state : {snapshot.get('vehicle_state')}")
    print(f"battery_level : {snapshot.get('battery_level')}")
    print(f"charging_state: {snapshot.get('charging_state')}")
    print(f"charge_amps   : {snapshot.get('charge_amps')}")
    print(f"charge_limit  : {snapshot.get('charge_limit_soc')}")
    print(f"odometer_km   : {snapshot.get('odometer_km')}")

    if snapshot.get("asleep_or_offline"):
        print("note          : vehicle asleep/offline -> vehicle_data skipped (no wake-up)")


def maybe_write_json(snapshot: Mapping[str, Any], output_json: str | None) -> None:
    if not output_json:
        return
    path = Path(output_json)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as json_file:
        json.dump(snapshot, json_file, ensure_ascii=False, indent=2)
    print(f"saved_json    : {path}")


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
            "For Wave 4 cost-aware mode prefer 600s when idle.",
            file=sys.stderr,
        )

    print("Tesla read-only mode active.")
    print(f"commands_enabled : {config.commands_enabled}")
    print(f"allow_wake_up    : {config.allow_wake_up}")
    print("safety           : no command endpoints and no wake-up calls")

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

            if not args.watch:
                break
            if max_iterations != 0 and cycle >= max_iterations:
                break
            time.sleep(poll_seconds)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
