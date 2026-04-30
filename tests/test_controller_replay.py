from __future__ import annotations

from pathlib import Path

import pytest

from src.controller_replay import (
    ReplayScenario,
    build_guardrail_settings,
    load_scenarios_csv,
    replay_scenarios,
    write_results_csv,
)


def _default_guardrails():
    args = type(
        "Args",
        (),
        {
            "grid_voltage": 230.0,
            "min_amps": 6,
            "max_amps": 16,
            "start_threshold_w": 1600.0,
            "stop_threshold_w": 900.0,
            "min_delta_amps": 2,
            "start_confirm_cycles": 2,
            "stop_confirm_cycles": 2,
            "cooldown_cycles": 2,
            "initial_current_amps": 0,
        },
    )()
    return build_guardrail_settings(args)


def _row_by_scenario(rows: list[dict[str, object]], scenario: str) -> dict[str, object]:
    for row in rows:
        if row["scenario"] == scenario:
            return row
    raise AssertionError(f"Scenario not found in replay results: {scenario}")


def test_load_scenarios_csv_from_fixture() -> None:
    fixture_path = Path("data/controller_replay_scenarios.csv")
    scenarios = load_scenarios_csv(fixture_path)

    assert len(scenarios) >= 10
    assert scenarios[0].scenario == "night_import"
    assert scenarios[0].export_w == 0.0
    assert scenarios[0].import_w == 450.0


def test_replay_fixture_covers_start_set_stop_and_limits() -> None:
    fixture_path = Path("data/controller_replay_scenarios.csv")
    scenarios = load_scenarios_csv(fixture_path)
    rows = replay_scenarios(
        scenarios,
        guardrails=_default_guardrails(),
        initial_current_amps=0,
    )

    assert len(rows) == len(scenarios)
    below_min = _row_by_scenario(rows, "surplus_below_min_amps")
    assert below_min["target_amps"] == 0
    assert below_min["action"] == "NO_ACTION"

    min_candidate = _row_by_scenario(rows, "surplus_min_amps_candidate")
    assert min_candidate["target_amps"] >= 6
    assert min_candidate["action"] == "NO_ACTION"
    assert "WAIT_START_THRESHOLD" in str(min_candidate["reason"])

    start_confirmed = _row_by_scenario(rows, "start_confirm_cycle_2")
    assert start_confirmed["action"] == "START_CHARGE"
    assert int(start_confirmed["current_amps_after"]) >= 6

    cooldown_block = _row_by_scenario(rows, "surplus_growth_cooldown")
    assert cooldown_block["action"] == "NO_ACTION"
    assert "COOLDOWN_ACTIVE" in str(cooldown_block["reason"])

    set_amps = _row_by_scenario(rows, "surplus_growth_set_amps")
    assert set_amps["action"] == "SET_AMPS"

    max_limited = _row_by_scenario(rows, "surplus_peak_set_max")
    assert max_limited["target_amps"] == 16

    stop_confirmed = _row_by_scenario(rows, "sustained_import_stop_1")
    assert stop_confirmed["action"] == "STOP_CHARGE"

    allowed_actions = {"NO_ACTION", "START_CHARGE", "SET_AMPS", "STOP_CHARGE"}
    assert {row["action"] for row in rows}.issubset(allowed_actions)


def test_replay_respects_min_delta() -> None:
    scenarios = [
        ReplayScenario(
            scenario="delta_small",
            pv_power_w=0.0,
            load_power_w=0.0,
            grid_power_w=-2530.0,  # 11A target at 230V
            current_amps=10,
            notes="difference should be 1A",
        ),
    ]
    rows = replay_scenarios(
        scenarios,
        guardrails=_default_guardrails(),
        initial_current_amps=10,
    )

    assert rows[0]["target_amps"] == 11
    assert rows[0]["action"] == "NO_ACTION"
    assert "DELTA_LT_MIN" in str(rows[0]["reason"])


def test_write_results_csv_creates_file(tmp_path: Path) -> None:
    rows = [
        {
            "cycle": 1,
            "scenario": "example",
            "pv_power_w": "0.000",
            "load_power_w": "500.000",
            "grid_power_w": "500.000",
            "import_w": "500.000",
            "export_w": "0.000",
            "current_amps_before": 0,
            "target_amps": 0,
            "action": "NO_ACTION",
            "current_amps_after": 0,
            "reason": "NO_ACTION;SIMULATED_REPLAY",
            "consecutive_above_start": 0,
            "consecutive_below_stop": 0,
            "cooldown_active": "false",
            "notes": "",
        }
    ]
    output_path = tmp_path / "controller_replay_results.csv"
    written = write_results_csv(output_path, rows)

    assert written == 1
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "scenario" in content
    assert "NO_ACTION" in content


def test_build_guardrails_validation_error() -> None:
    invalid_args = type(
        "Args",
        (),
        {
            "grid_voltage": 230.0,
            "min_amps": 6,
            "max_amps": 16,
            "start_threshold_w": 800.0,
            "stop_threshold_w": 900.0,
            "min_delta_amps": 2,
            "start_confirm_cycles": 2,
            "stop_confirm_cycles": 2,
            "cooldown_cycles": 2,
            "initial_current_amps": 0,
        },
    )()

    with pytest.raises(ValueError):
        build_guardrail_settings(invalid_args)
