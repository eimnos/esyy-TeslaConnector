from src.afore_reader import AforeSnapshot
from src.solar_tesla_controller_dry_run import (
    ControllerState,
    GuardrailSettings,
    build_controller_decision_row,
    evaluate_simulated_decision,
    insert_controller_decision_best_effort,
)
from src.supabase_sink import SupabaseSinkError


def make_settings() -> GuardrailSettings:
    return GuardrailSettings(
        start_threshold_w=1600.0,
        stop_threshold_w=900.0,
        min_amps=6,
        max_amps=16,
        grid_voltage=230.0,
        min_delta_amps=2,
        start_confirm_cycles=2,
        stop_confirm_cycles=2,
        cooldown_cycles=2,
    )


def make_snapshot() -> AforeSnapshot:
    return AforeSnapshot(
        timestamp_utc="2026-04-30T12:00:00Z",
        pv_power_w=4200.0,
        load_power_w=2500.0,
        grid_power_raw_w=-1700.0,
        grid_sign_mode="import_positive",
        grid_sign_assumed_mode="import_positive",
        grid_sign_unknown=False,
        grid_import_w=0.0,
        grid_export_w=1700.0,
    )


def test_start_requires_confirm_cycles() -> None:
    settings = make_settings()
    state = ControllerState(
        simulated_current_amps=0,
        consecutive_above_start=0,
        consecutive_below_stop=0,
        last_decision_cycle=None,
    )

    decision_1, state_1 = evaluate_simulated_decision(
        cycle=1,
        export_w=2000.0,
        current_amps=0,
        state=state,
        settings=settings,
    )
    assert decision_1.action == "NO_ACTION"
    assert "WAIT_START_CONFIRM" in decision_1.reason
    assert state_1.consecutive_above_start == 1

    decision_2, state_2 = evaluate_simulated_decision(
        cycle=2,
        export_w=2000.0,
        current_amps=0,
        state=state_1,
        settings=settings,
    )
    assert decision_2.action == "START_CHARGE"
    assert decision_2.current_amps_after >= settings.min_amps
    assert state_2.last_decision_cycle == 2


def test_stop_requires_confirm_cycles() -> None:
    settings = make_settings()
    state = ControllerState(
        simulated_current_amps=8,
        consecutive_above_start=0,
        consecutive_below_stop=0,
        last_decision_cycle=None,
    )

    decision_1, state_1 = evaluate_simulated_decision(
        cycle=10,
        export_w=100.0,
        current_amps=8,
        state=state,
        settings=settings,
    )
    assert decision_1.action == "NO_ACTION"
    assert "WAIT_STOP_CONFIRM" in decision_1.reason
    assert state_1.consecutive_below_stop == 1

    decision_2, state_2 = evaluate_simulated_decision(
        cycle=11,
        export_w=100.0,
        current_amps=8,
        state=state_1,
        settings=settings,
    )
    assert decision_2.action == "STOP_CHARGE"
    assert decision_2.current_amps_after == 0
    assert state_2.last_decision_cycle == 11


def test_set_amps_respects_cooldown() -> None:
    settings = make_settings()
    state = ControllerState(
        simulated_current_amps=8,
        consecutive_above_start=0,
        consecutive_below_stop=0,
        last_decision_cycle=20,
    )

    decision, next_state = evaluate_simulated_decision(
        cycle=21,
        export_w=3000.0,
        current_amps=8,
        state=state,
        settings=settings,
    )
    assert decision.action == "NO_ACTION"
    assert decision.cooldown_active is True
    assert "COOLDOWN_ACTIVE" in decision.reason
    assert next_state.last_decision_cycle == 20


def test_build_controller_decision_row_contains_simulated_fields() -> None:
    snapshot = make_snapshot()
    decision = evaluate_simulated_decision(
        cycle=4,
        export_w=1700.0,
        current_amps=0,
        state=ControllerState(
            simulated_current_amps=0,
            consecutive_above_start=1,
            consecutive_below_stop=0,
            last_decision_cycle=None,
        ),
        settings=make_settings(),
    )[0]

    row = build_controller_decision_row(
        sample_timestamp="2026-04-30T12:00:00Z",
        cycle=4,
        snapshot=snapshot,
        decision=decision,
        reason="SIMULATED_ONLY",
    )

    assert row["simulated"] is True
    assert row["grid_power_w"] == -1700.0
    assert row["export_w"] == 1700.0
    assert row["import_w"] == 0.0
    assert row["load_power_w"] == 2500.0
    assert row["pv_power_w"] == 4200.0
    assert row["reason"] == "SIMULATED_ONLY"


class _FallbackSink:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.first_call = True

    def insert_controller_decision(self, row: dict) -> None:
        self.calls.append(dict(row))
        if self.first_call:
            self.first_call = False
            raise SupabaseSinkError(
                "Supabase write failed on controller_decisions with status 400: "
                "{\"code\":\"PGRST204\",\"message\":\"Could not find the "
                "'reason' column of 'controller_decisions' in the schema cache\"}"
            )


def test_insert_controller_decision_best_effort_fallback() -> None:
    sink = _FallbackSink()
    error = insert_controller_decision_best_effort(
        sink=sink,  # type: ignore[arg-type]
        row={"sample_timestamp": "2026-04-30T12:00:00Z", "reason": "x", "action": "NO_ACTION"},
    )

    assert error is not None
    assert error.startswith("warning:")
    assert len(sink.calls) == 2
    assert "reason" in sink.calls[0]
    assert "reason" not in sink.calls[1]
