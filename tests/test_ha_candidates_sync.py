from src.ha_candidates_sync import build_candidate_sample_rows, insert_rows_supabase
from src.supabase_sink import SupabaseSinkError


def _find_row(
    rows: list[dict[str, object]],
    *,
    register_name: str,
    register_order: str,
    scale: float,
) -> dict[str, object]:
    for row in rows:
        if (
            row["register_name"] == register_name
            and row["register_order"] == register_order
            and float(row["scale"]) == scale
        ):
            return row
    raise AssertionError(
        f"Row not found for register_name={register_name}, register_order={register_order}, scale={scale}"
    )


def test_build_candidate_rows_power_only() -> None:
    rows = build_candidate_sample_rows(
        {
            535: 0.0,
            536: 4700.0,
            547: 0.0,
            548: 3000.0,
            553: 0.0,
            554: 3500.0,
        },
        sample_timestamp="2026-04-29T12:00:00Z",
        include_energy_block=False,
    )

    assert len(rows) == 18
    grid_ab = _find_row(
        rows,
        register_name="grid_active_power",
        register_order="[535,536]",
        scale=1.0,
    )
    assert grid_ab["decoded_int32"] == 4700
    assert grid_ab["value_w"] == 4700.0

    pv_ba = _find_row(
        rows,
        register_name="pv_total_power",
        register_order="[554,553]",
        scale=0.1,
    )
    assert pv_ba["decoded_int32"] == 229376000
    assert pv_ba["value_w"] == 22937600.0


def test_build_candidate_rows_with_energy_block() -> None:
    rows = build_candidate_sample_rows(
        {
            535: 0.0,
            536: 4700.0,
            547: 0.0,
            548: 3000.0,
            553: 0.0,
            554: 3500.0,
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
        },
        sample_timestamp="2026-04-29T12:05:00Z",
        include_energy_block=True,
    )

    assert len(rows) == 29
    export_today = _find_row(
        rows,
        register_name="meter_today_export_energy",
        register_order="[1002]",
        scale=0.1,
    )
    assert export_today["value_w"] == 0.5


class _FailingSink:
    def __init__(self) -> None:
        self.inserted = 0

    def insert_afore_candidate_sample(self, row: dict[str, object]) -> None:
        self.inserted += 1
        if row["register_name"] == "load_power":
            raise SupabaseSinkError("forced failure")


def test_insert_rows_supabase_collects_errors() -> None:
    sink = _FailingSink()
    rows = [
        {"register_name": "grid_active_power"},
        {"register_name": "load_power"},
        {"register_name": "pv_total_power"},
    ]

    errors = insert_rows_supabase(sink, rows)  # type: ignore[arg-type]

    assert len(errors) == 1
    assert "forced failure" in errors[0]
    assert sink.inserted == 3
