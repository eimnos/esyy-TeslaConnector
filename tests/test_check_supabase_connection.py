from src.check_supabase_connection import run_connection_check
from src.config import AppConfig


def make_config(
    *,
    supabase_enabled: bool,
    supabase_url: str,
    supabase_service_role_key: str,
) -> AppConfig:
    return AppConfig(
        collector_ip="192.168.1.20",
        collector_port=8899,
        collector_serial=3544937241,
        poll_seconds=60,
        dry_run=True,
        grid_voltage=230.0,
        tesla_min_amps=6,
        tesla_max_amps=16,
        grid_export_start_w=1600.0,
        grid_export_stop_w=900.0,
        afore_pv_power_register=560,
        afore_grid_power_register_high=524,
        afore_grid_power_register_low=525,
        afore_grid_power_scale=1.0,
        afore_pv_power_scale=1.0,
        afore_grid_sign_mode="unknown",
        supabase_enabled=supabase_enabled,
        supabase_url=supabase_url,
        supabase_service_role_key=supabase_service_role_key,
    )


class FakeSink:
    def __init__(self, *_args, **_kwargs) -> None:
        self.fetch_calls: list[tuple[str, int]] = []
        self.inverter_inserts = 0
        self.decision_inserts = 0

    def fetch_rows(self, table: str, **kwargs):
        limit = int(kwargs.get("limit", 0))
        self.fetch_calls.append((table, limit))
        return [{"id": "1"}]

    def insert_inverter_sample(self, row):
        self.inverter_inserts += 1
        assert row["source"] == "connection_test"

    def insert_controller_decision(self, row):
        self.decision_inserts += 1
        assert row["action"] == "CONNECTION_TEST"

    def close(self):
        return None


def test_run_connection_check_disabled_is_non_blocking() -> None:
    config = make_config(
        supabase_enabled=False,
        supabase_url="",
        supabase_service_role_key="",
    )

    result = run_connection_check(
        config,
        insert_test_sample=False,
        show_limit=3,
        sink_factory=FakeSink,
    )

    assert result.success is True
    assert result.enabled is False


def test_run_connection_check_missing_config_fails_clearly() -> None:
    config = make_config(
        supabase_enabled=True,
        supabase_url="",
        supabase_service_role_key="",
    )

    result = run_connection_check(
        config,
        insert_test_sample=False,
        show_limit=3,
        sink_factory=FakeSink,
    )

    assert result.success is False
    assert "missing" in result.message.lower()


def test_run_connection_check_success_with_optional_insert() -> None:
    config = make_config(
        supabase_enabled=True,
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="service-role-key",
    )

    result = run_connection_check(
        config,
        insert_test_sample=True,
        show_limit=2,
        sink_factory=FakeSink,
    )

    assert result.success is True
    assert result.enabled is True
    assert result.inverter_rows == 1
    assert result.decision_rows == 1
    assert result.inserted_test_sample is True
