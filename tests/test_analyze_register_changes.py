from pathlib import Path

from src.analyze_register_changes import compare_scans, load_scan


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
