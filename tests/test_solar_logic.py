from src.solar_logic import (
    ControlSettings,
    calculate_surplus_w,
    calculate_target_amps,
    decide_charge_action,
    should_update_amps,
)


def test_export_negative_grid_generates_surplus() -> None:
    assert calculate_surplus_w(-1250) == 1250


def test_import_positive_grid_has_zero_surplus() -> None:
    assert calculate_surplus_w(800) == 0


def test_below_stop_threshold_requests_stop() -> None:
    settings = ControlSettings(
        grid_export_start_w=1600,
        grid_export_stop_w=900,
        min_amps=6,
        max_amps=16,
        grid_voltage=230,
    )
    assert decide_charge_action(export_w=700, current_amps=8, settings=settings) == "STOP_CHARGE"


def test_above_start_threshold_requests_start() -> None:
    settings = ControlSettings(
        grid_export_start_w=1600,
        grid_export_stop_w=900,
        min_amps=6,
        max_amps=16,
        grid_voltage=230,
    )
    assert decide_charge_action(export_w=2000, current_amps=0, settings=settings) == "START_CHARGE"


def test_target_amps_respects_min_limit() -> None:
    assert calculate_target_amps(export_w=1600, min_amps=6, max_amps=16, grid_voltage=230) == 6


def test_target_amps_respects_max_limit() -> None:
    assert calculate_target_amps(export_w=10000, min_amps=6, max_amps=16, grid_voltage=230) == 16


def test_no_update_when_delta_is_less_than_two() -> None:
    assert not should_update_amps(current_amps=11, target_amps=12, min_delta=2)
