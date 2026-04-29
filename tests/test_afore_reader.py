from src.afore_reader import (
    build_snapshot_from_registers,
    normalize_grid_power,
    parse_signed_int32,
)
from src.config import AppConfig


def make_config(grid_sign_mode: str = "unknown") -> AppConfig:
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
        afore_grid_sign_mode=grid_sign_mode,
        supabase_enabled=False,
        supabase_url="",
        supabase_service_role_key="",
    )


def test_parse_signed_int32_negative() -> None:
    assert parse_signed_int32(0xFFFF, 0xFF7C) == -132


def test_parse_signed_int32_positive() -> None:
    assert parse_signed_int32(0x0000, 0x00C8) == 200


def test_normalize_grid_power_import_positive_mode() -> None:
    normalized = normalize_grid_power(-250.0, "import_positive")
    assert normalized.grid_import_w == 0.0
    assert normalized.grid_export_w == 250.0
    assert not normalized.grid_sign_unknown


def test_normalize_grid_power_unknown_marks_flag() -> None:
    normalized = normalize_grid_power(200.0, "unknown")
    assert normalized.grid_import_w == 200.0
    assert normalized.grid_export_w == 0.0
    assert normalized.grid_sign_unknown
    assert normalized.grid_sign_assumed_mode == "import_positive"


def test_build_snapshot_from_registers_applies_scales_and_sign_mode() -> None:
    config = make_config(grid_sign_mode="export_positive")
    registers = {
        560: 3500,
        524: 0x0000,
        525: 0x0064,
    }
    snapshot = build_snapshot_from_registers(register_values=registers, config=config)
    assert snapshot.pv_power_w == 3500.0
    assert snapshot.grid_power_raw_w == 100.0
    assert snapshot.grid_import_w == 0.0
    assert snapshot.grid_export_w == 100.0
    assert snapshot.grid_sign_mode == "export_positive"
