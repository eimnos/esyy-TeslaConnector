"""Synchronize Tesla read-only snapshots into Supabase tesla_samples."""

from __future__ import annotations

import argparse
import sys
import time

try:
    from src.tesla_client import (
        TeslaApiError,
        TeslaApiResponseError,
        TeslaFleetClient,
        load_tesla_config,
    )
    from src.tesla_readonly_status import (
        build_status_snapshot,
        create_optional_supabase_sink,
        maybe_insert_supabase,
        maybe_write_json,
        print_snapshot,
    )
except ModuleNotFoundError:  # Allows `python src/tesla_sync_readonly.py`
    from tesla_client import (  # type: ignore[no-redef]
        TeslaApiError,
        TeslaApiResponseError,
        TeslaFleetClient,
        load_tesla_config,
    )
    from tesla_readonly_status import (  # type: ignore[no-redef]
        build_status_snapshot,
        create_optional_supabase_sink,
        maybe_insert_supabase,
        maybe_write_json,
        print_snapshot,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read Tesla status and best-effort sync rows into Supabase tesla_samples."
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
        "--output-json",
        default=None,
        help="Optional JSON output path (example: data/tesla_status_sample.json).",
    )
    parser.add_argument(
        "--source",
        default="tesla_sync_readonly",
        help="Source label stored in tesla_samples (default: tesla_sync_readonly).",
    )
    return parser.parse_args()


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

    sink, sink_state = create_optional_supabase_sink()
    if sink_state == "disabled":
        print("Supabase sync: disabled (SUPABASE_ENABLED=false).")
    elif sink_state == "missing_config":
        print(
            "Supabase sync: missing config (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY).",
            file=sys.stderr,
        )
    else:
        print("Supabase sync: enabled (best effort).")

    print("Tesla read-only sync active (no commands, no wake-up).")
    client = TeslaFleetClient(config=config)
    max_iterations = args.iterations if args.watch else 1
    cycle = 0
    try:
        while True:
            cycle += 1
            if max_iterations != 0 and cycle > max_iterations:
                break

            try:
                readonly_status = client.get_readonly_status()
                snapshot = build_status_snapshot(readonly_status)
            except (TeslaApiError, TeslaApiResponseError) as exc:
                print(f"Tesla read-only error: {exc}", file=sys.stderr)
                return 1

            print(f"\n--- Tesla Sync Snapshot #{cycle} ---")
            print_snapshot(snapshot)
            maybe_write_json(snapshot, args.output_json)

            sync_error = maybe_insert_supabase(
                sink=sink,
                snapshot=snapshot,
                source=args.source,
            )
            if sync_error:
                if sync_error.startswith("warning:"):
                    print(f"supabase_sync_warning: {sync_error}", file=sys.stderr)
                else:
                    print(f"supabase_sync_error: {sync_error}", file=sys.stderr)
            elif sink is not None:
                print("supabase_sync: ok")

            if not args.watch:
                break
            if max_iterations != 0 and cycle >= max_iterations:
                break
            time.sleep(poll_seconds)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        if sink is not None:
            sink.close()
        client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
