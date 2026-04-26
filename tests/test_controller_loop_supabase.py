from src.config import AppConfig
from src.controller_loop_dry_run import create_optional_supabase_sink


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
