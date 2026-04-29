from src.afore_ha_candidates import (
    build_ha_candidate_snapshot,
    parse_s32_order_ab,
    parse_s32_order_ba,
    parse_signed_int32,
    parse_u32_order_ab,
    parse_u32_order_ba,
    parse_unsigned_int32,
)


def test_parse_signed_int32_positive() -> None:
    assert parse_signed_int32(0x0000, 0x0CE4) == 3300


def test_parse_signed_int32_negative() -> None:
    assert parse_signed_int32(0xFFFF, 0xFF9C) == -100


def test_parse_unsigned_int32() -> None:
    assert parse_unsigned_int32(0x0001, 0x0002) == 65538


def test_order_helpers_decode_different_word_orders() -> None:
    registers = {
        535: 0.0,
        536: 3300.0,
    }
    assert parse_s32_order_ab(registers, 535, 536) == 3300
    assert parse_s32_order_ba(registers, 535, 536) == 216268800


def test_build_ha_candidate_snapshot_parses_target_blocks() -> None:
    registers = {
        535: 0.0,
        536: 3250.0,
        547: 0.0,
        548: 3255.0,
        553: 0.0,
        554: 4000.0,
        1002: 5.0,
        1003: 10.0,
        1004: 15.0,
        1006: 0.0,
        1007: 100.0,
        1018: 0.0,
        1019: 200.0,
        1020: 0.0,
        1021: 300.0,
        1026: 0.0,
        1027: 400.0,
    }

    snapshot = build_ha_candidate_snapshot(registers)

    assert snapshot.grid_power_535_536_ab_w == 3250
    assert snapshot.load_power_547_548_ab_w == 3255
    assert snapshot.pv_total_553_554_ab_w == 4000
    assert snapshot.today_energy_export_1002_kwh == 0.5
    assert snapshot.today_energy_import_1003_kwh == 1.0
    assert snapshot.today_load_consumption_1004_kwh == 1.5
    assert snapshot.today_production_1007_1006_kwh == 10.0
    assert snapshot.total_export_1019_1018_kwh == 20.0
    assert snapshot.total_import_1021_1020_kwh == 30.0
    assert snapshot.total_production_1027_1026_kwh == 40.0


def test_unsigned_order_helpers() -> None:
    registers = {
        553: 0.0,
        554: 4096.0,
    }
    assert parse_u32_order_ab(registers, 553, 554) == 4096
    assert parse_u32_order_ba(registers, 553, 554) == 268435456
