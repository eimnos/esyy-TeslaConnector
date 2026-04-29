from src.config import AppConfig
from src.controller_loop_dry_run import (
    create_optional_supabase_sink,
    write_error_decision_to_supabase,
    write_success_to_supabase,
)


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
        grid_automation_enabled=False,
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


def test_create_optional_supabase_sink_disabled() -> None:
    config = make_config(
        supabase_enabled=False,
        supabase_url="",
        supabase_service_role_key="",
    )
    sink, state = create_optional_supabase_sink(config)
    assert sink is None
    assert state == "disabled"


def test_create_optional_supabase_sink_missing_config() -> None:
    config = make_config(
        supabase_enabled=True,
        supabase_url="",
        supabase_service_role_key="",
    )
    sink, state = create_optional_supabase_sink(config)
    assert sink is None
    assert state == "missing_config"


def test_create_optional_supabase_sink_enabled() -> None:
    config = make_config(
        supabase_enabled=True,
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="service-role-key",
    )
    sink, state = create_optional_supabase_sink(config)
    assert sink is not None
    assert state == "enabled"
    sink.close()


class FakeSink:
    def __init__(self) -> None:
        self.inverter_rows: list[dict] = []
        self.decision_rows: list[dict] = []

    def insert_inverter_sample(self, row: dict) -> None:
        self.inverter_rows.append(row)

    def insert_controller_decision(self, row: dict) -> None:
        self.decision_rows.append(row)


def test_write_success_to_supabase_writes_both_tables() -> None:
    sink = FakeSink()
    errors = write_success_to_supabase(
        sink=sink,  # type: ignore[arg-type]
        cycle=1,
        sample_timestamp="2026-01-01T00:00:00Z",
        pv_power_w=3200.0,
        grid_power_raw_w=-250.0,
        grid_sign_mode="unknown",
        grid_sign_assumed_mode="import_positive",
        grid_sign_unknown=True,
        grid_import_w=0.0,
        grid_export_w=250.0,
        current_amps_before=0,
        target_amps=8,
        action="START_CHARGE",
        current_amps_after=8,
        note="GRID_SIGN_UNKNOWN",
    )

    assert errors == []
    assert len(sink.inverter_rows) == 1
    assert len(sink.decision_rows) == 1
    assert sink.inverter_rows[0]["pv_power_w"] == 3200.0
    assert sink.decision_rows[0]["action"] == "START_CHARGE"


def test_write_error_decision_to_supabase_only_decision() -> None:
    sink = FakeSink()
    error = write_error_decision_to_supabase(
        sink=sink,  # type: ignore[arg-type]
        cycle=5,
        current_amps=6,
        error_text="RuntimeError: timeout",
    )

    assert error is None
    assert len(sink.inverter_rows) == 0
    assert len(sink.decision_rows) == 1
    assert sink.decision_rows[0]["action"] == "READ_ERROR"
