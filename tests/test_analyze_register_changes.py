from pathlib import Path

from src.analyze_register_changes import (
    compare_scans,
    compare_signed32_pairs,
    decode_signed_int32,
    load_scan,
    parse_signed32_pairs,
)


def test_compare_scans_filters_and_sorts_by_abs_delta() -> None:
    left = {1: 10.0, 2: 100.0, 3: 200.0}
    right = {1: 10.0, 2: 140.0, 3: 170.0}

    rows = compare_scans(left, right, min_abs_delta=5.0)

    assert [row.register for row in rows] == [2, 3]
    assert rows[0].delta == 40.0
    assert rows[1].delta == -30.0


def test_load_scan_reads_register_and_value_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "scan.csv"
    csv_path.write_text(
        "timestamp,register,value\n"
        "2026-01-01T00:00:00Z,10,123\n"
        "2026-01-01T00:00:01Z,11,456\n",
        encoding="utf-8",
    )

    values = load_scan(csv_path)

    assert values == {10: 123.0, 11: 456.0}


def test_parse_signed32_pairs_accepts_list() -> None:
    assert parse_signed32_pairs("524-525,526-527,528-529") == [
        (524, 525),
        (526, 527),
        (528, 529),
    ]


def test_decode_signed_int32_supports_negative_values() -> None:
    assert decode_signed_int32(65535, 65480) == -56


def test_compare_signed32_pairs_returns_pair_delta() -> None:
    left = {524: 65535.0, 525: 65480.0}
    right = {524: 0.0, 525: 140.0}

    rows = compare_signed32_pairs(left, right, [(524, 525)])

    assert len(rows) == 1
    assert rows[0].label == "524-525"
    assert rows[0].left_value == -56
    assert rows[0].right_value == 140
    assert rows[0].delta == 196
