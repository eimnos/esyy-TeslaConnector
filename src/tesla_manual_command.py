"""Manual Tesla command runner for controlled Wave 10A smoke tests."""

from __future__ import annotations

import argparse
import sys

try:
    from src.tesla_commands import (
        TeslaCommandApiError,
        TeslaCommandBlockedError,
        TeslaCommandClient,
        create_tesla_command_client,
        set_charge_amps,
        start_charge,
        stop_charge,
    )
except ModuleNotFoundError:  # Allows `python src/tesla_manual_command.py`
    from tesla_commands import (  # type: ignore[no-redef]
        TeslaCommandApiError,
        TeslaCommandBlockedError,
        TeslaCommandClient,
        create_tesla_command_client,
        set_charge_amps,
        start_charge,
        stop_charge,
    )

ACK_FLAG = "--i-understand-this-sends-real-command"
DEFAULT_LOG_PATH = "data/tesla_command_calls_log.csv"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Manual-only Tesla command script. "
            "No automatic logic and no wake-up calls."
        )
    )
    command_group = parser.add_mutually_exclusive_group(required=True)
    command_group.add_argument(
        "--set-amps",
        type=int,
        help="Set charging amps to the provided integer value (example: 6).",
    )
    command_group.add_argument(
        "--start-charge",
        action="store_true",
        help="Send manual charge_start command.",
    )
    command_group.add_argument(
        "--stop-charge",
        action="store_true",
        help="Send manual charge_stop command.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not send API request. Still logs command attempt.",
    )
    parser.add_argument(
        "--vehicle-id",
        default=None,
        help="Optional vehicle id override. Defaults to TESLA_VEHICLE_ID from .env.",
    )
    parser.add_argument(
        "--grid-status",
        default="confirmed",
        choices=("confirmed", "partial", "unknown"),
        help=(
            "Grid mapping status guardrail (default: confirmed). "
            "Commands are blocked unless confirmed."
        ),
    )
    parser.add_argument(
        "--i-understand-this-sends-real-command",
        action="store_true",
        required=True,
        help="Mandatory explicit acknowledgement before any command attempt.",
    )
    return parser.parse_args(argv)


def _describe_command(args: argparse.Namespace) -> str:
    if args.set_amps is not None:
        return f"set_charge_amps({args.set_amps})"
    if args.start_charge:
        return "start_charge"
    return "stop_charge"


def run_command(args: argparse.Namespace, client: TeslaCommandClient) -> int:
    if args.set_amps is not None and args.set_amps <= 0:
        print("--set-amps must be > 0", file=sys.stderr)
        return 2

    if client.config.allow_wake_up:
        print(
            "Safety check failed: TESLA_ALLOW_WAKE_UP must be false for Wave 10A.",
            file=sys.stderr,
        )
        return 2

    dry_run = bool(args.dry_run)
    command_text = _describe_command(args)
    print("Tesla manual command mode active.")
    print(f"command              : {command_text}")
    print(f"dry_run              : {str(dry_run).lower()}")
    print(f"grid_status          : {args.grid_status}")
    print(f"commands_enabled_env : {str(client.config.commands_enabled).lower()}")
    print(f"allow_wake_up_env    : {str(client.config.allow_wake_up).lower()}")
    print(f"command_log          : {DEFAULT_LOG_PATH}")

    try:
        if args.set_amps is not None:
            result = set_charge_amps(
                client,
                args.set_amps,
                allow_command=True,
                dry_run=dry_run,
                grid_status=args.grid_status,
                vehicle_id=args.vehicle_id,
            )
        elif args.start_charge:
            result = start_charge(
                client,
                allow_command=True,
                dry_run=dry_run,
                grid_status=args.grid_status,
                vehicle_id=args.vehicle_id,
            )
        else:
            result = stop_charge(
                client,
                allow_command=True,
                dry_run=dry_run,
                grid_status=args.grid_status,
                vehicle_id=args.vehicle_id,
            )
    except TeslaCommandBlockedError as exc:
        print(f"Command blocked: {exc}", file=sys.stderr)
        print(f"Attempt logged to {DEFAULT_LOG_PATH}", file=sys.stderr)
        return 1
    except TeslaCommandApiError as exc:
        print(f"Tesla API command error: {exc}", file=sys.stderr)
        print(f"Attempt logged to {DEFAULT_LOG_PATH}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Validation error: {exc}", file=sys.stderr)
        return 2

    print("Command attempt completed.")
    print(f"result.executed      : {str(result.executed).lower()}")
    print(f"result.blocked       : {str(result.blocked).lower()}")
    print(f"result.reason        : {result.reason}")
    if result.status_code is not None:
        print(f"result.status_code   : {result.status_code}")
    print(f"Attempt logged to {DEFAULT_LOG_PATH}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    client: TeslaCommandClient | None = None
    try:
        client = create_tesla_command_client()
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Failed to initialize Tesla command client: {exc}", file=sys.stderr)
        return 1

    try:
        return run_command(args, client)
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
