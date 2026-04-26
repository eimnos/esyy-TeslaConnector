"""Check Supabase connectivity and optional test inserts for Wave 5B."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

try:
    from src.config import AppConfig, load_config
    from src.supabase_sink import SupabaseSink, SupabaseSinkConfig, SupabaseSinkError
except ModuleNotFoundError:  # Allows `python src/check_supabase_connection.py`
    from config import AppConfig, load_config  # type: ignore[no-redef]
    from supabase_sink import SupabaseSink, SupabaseSinkConfig, SupabaseSinkError  # type: ignore[no-redef]


@dataclass(frozen=True, slots=True)
class ConnectionCheckResult:
    enabled: bool
    success: bool
    message: str
    inverter_rows: int = 0
    decision_rows: int = 0
    inserted_test_sample: bool = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Supabase connection and optional connection_test inserts."
    )
    parser.add_argument(
        "--insert-test-sample",
        action="store_true",
        help="Insert a test row with source/note='connection_test'.",
    )
    parser.add_argument(
        "--show-limit",
        type=int,
        default=3,
        help="How many recent rows to fetch for connectivity check (default: 3).",
    )
    return parser.parse_args()


def _build_test_inverter_row(sample_timestamp: str) -> dict[str, Any]:
    return {
        "sample_timestamp": sample_timestamp,
        "pv_power_w": 0.0,
        "grid_power_raw_w": 0.0,
        "grid_import_w": 0.0,
        "grid_export_w": 0.0,
        "grid_sign_mode": "unknown",
        "grid_sign_assumed_mode": "connection_test",
        "grid_sign_unknown": True,
        "cycle": -1,
        "source": "connection_test",
    }


def _build_test_decision_row(sample_timestamp: str) -> dict[str, Any]:
    return {
        "sample_timestamp": sample_timestamp,
        "cycle": -1,
        "export_w": 0.0,
        "current_amps_before": 0,
        "target_amps": 0,
        "action": "CONNECTION_TEST",
        "current_amps_after": 0,
        "note": "connection_test",
    }


def run_connection_check(
    config: AppConfig,
    *,
    insert_test_sample: bool,
    show_limit: int,
    sink_factory: Callable[[SupabaseSinkConfig], Any] = SupabaseSink,
) -> ConnectionCheckResult:
    """Run Supabase connectivity checks with optional test insert."""

    if not config.supabase_enabled:
        return ConnectionCheckResult(
            enabled=False,
            success=True,
            message="SUPABASE_ENABLED=false: skipping Supabase check.",
        )

    if not config.supabase_url or not config.supabase_service_role_key:
        return ConnectionCheckResult(
            enabled=True,
            success=False,
            message=(
                "Supabase enabled but SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY missing."
            ),
        )

    sink = sink_factory(
        SupabaseSinkConfig(
            url=config.supabase_url,
            service_role_key=config.supabase_service_role_key,
        )
    )
    inserted = False
    try:
        inverter_rows = sink.fetch_rows(
            SupabaseSink.TABLE_INVERTER_SAMPLES,
            select="id,sample_timestamp,source,created_at",
            order="created_at.desc",
            limit=show_limit,
        )
        decision_rows = sink.fetch_rows(
            SupabaseSink.TABLE_CONTROLLER_DECISIONS,
            select="id,sample_timestamp,action,note,created_at",
            order="created_at.desc",
            limit=show_limit,
        )

        if insert_test_sample:
            sample_timestamp = datetime.now(timezone.utc).isoformat()
            sink.insert_inverter_sample(_build_test_inverter_row(sample_timestamp))
            sink.insert_controller_decision(_build_test_decision_row(sample_timestamp))
            inserted = True

        return ConnectionCheckResult(
            enabled=True,
            success=True,
            message="Supabase connection check succeeded.",
            inverter_rows=len(inverter_rows),
            decision_rows=len(decision_rows),
            inserted_test_sample=inserted,
        )
    except SupabaseSinkError as exc:
        return ConnectionCheckResult(
            enabled=True,
            success=False,
            message=f"Supabase check failed: {exc}",
        )
    finally:
        close_method = getattr(sink, "close", None)
        if callable(close_method):
            close_method()


def main() -> int:
    args = parse_args()
    if args.show_limit <= 0:
        print("--show-limit must be > 0")
        return 2

    config = load_config()
    result = run_connection_check(
        config,
        insert_test_sample=args.insert_test_sample,
        show_limit=args.show_limit,
    )

    print(f"supabase_enabled      : {result.enabled}")
    print(f"success               : {result.success}")
    print(f"message               : {result.message}")

    if result.enabled and result.success:
        print(f"inverter_rows_checked : {result.inverter_rows}")
        print(f"decision_rows_checked : {result.decision_rows}")
        print(f"inserted_test_sample  : {result.inserted_test_sample}")

    if not result.success:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
