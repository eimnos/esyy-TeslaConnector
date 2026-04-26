"""Compare two Afore scan CSV files and show only changed registers."""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RegisterDelta:
    """Delta for one register between two scan files."""

    register: int
    left_value: float
    right_value: float

    @property
    def delta(self) -> float:
        return self.right_value - self.left_value

    @property
    def abs_delta(self) -> float:
        return abs(self.delta)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare two scan CSV files and list changed registers."
    )
    parser.add_argument("left_csv", help="Base scan CSV path.")
    parser.add_argument("right_csv", help="Comparison scan CSV path.")
    parser.add_argument(
        "--left-label",
        default=None,
        help="Optional label for left CSV (default: file name stem).",
    )
    parser.add_argument(
        "--right-label",
        default=None,
        help="Optional label for right CSV (default: file name stem).",
    )
    parser.add_argument(
        "--min-abs-delta",
        type=float,
        default=1.0,
        help="Filter out small changes with absolute delta below this threshold.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum rows to print in terminal.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional CSV output path for changed registers.",
    )
    return parser.parse_args()


def _parse_register(raw_value: str, row_number: int, path: Path) -> int:
    try:
        return int(float(raw_value))
    except ValueError as exc:
        raise ValueError(
            f"{path} row {row_number}: invalid register value {raw_value!r}"
        ) from exc


def _parse_numeric(raw_value: str, row_number: int, path: Path) -> float:
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{path} row {row_number}: invalid value {raw_value!r}") from exc


def load_scan(path: Path) -> dict[int, float]:
    """Load CSV values as register -> value mapping.

    If the same register appears multiple times, the last value wins.
    """

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    registers: dict[int, float] = {}
    with path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if not reader.fieldnames:
            raise ValueError(f"{path} has no CSV header")

        required = {"register", "value"}
        missing = required.difference(set(reader.fieldnames))
        if missing:
            raise ValueError(f"{path} is missing columns: {', '.join(sorted(missing))}")

        for row_index, row in enumerate(reader, start=2):
            register = _parse_register(row["register"], row_index, path)
            value = _parse_numeric(row["value"], row_index, path)
            registers[register] = value

    return registers


def compare_scans(
    left: dict[int, float], right: dict[int, float], min_abs_delta: float
) -> list[RegisterDelta]:
    shared_registers = left.keys() & right.keys()
    deltas = [
        RegisterDelta(
            register=register,
            left_value=left[register],
            right_value=right[register],
        )
        for register in shared_registers
    ]

    changed = [item for item in deltas if item.abs_delta >= min_abs_delta]
    changed.sort(key=lambda item: item.abs_delta, reverse=True)
    return changed


def format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.3f}"


def print_table(
    rows: list[RegisterDelta], left_label: str, right_label: str, limit: int
) -> None:
    shown = rows if limit <= 0 else rows[:limit]

    left_header = left_label[:16]
    right_header = right_label[:16]
    print(
        f"{'Register':>8}  {left_header:>16}  {right_header:>16}  {'Delta':>12}  {'|Delta|':>12}"
    )
    print("-" * 72)

    for item in shown:
        print(
            f"{item.register:8d}  "
            f"{format_number(item.left_value):>16}  "
            f"{format_number(item.right_value):>16}  "
            f"{format_number(item.delta):>12}  "
            f"{format_number(item.abs_delta):>12}"
        )

    if limit > 0 and len(rows) > limit:
        print(f"... {len(rows) - limit} additional changed registers not shown")


def save_output(rows: list[RegisterDelta], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            ["register", "left_value", "right_value", "delta", "abs_delta", "direction"]
        )
        for item in rows:
            direction = "UP" if item.delta > 0 else "DOWN"
            if item.delta == 0:
                direction = "UNCHANGED"
            writer.writerow(
                [
                    item.register,
                    item.left_value,
                    item.right_value,
                    item.delta,
                    item.abs_delta,
                    direction,
                ]
            )


def main() -> int:
    args = parse_args()
    if args.min_abs_delta < 0:
        print("--min-abs-delta must be >= 0", file=sys.stderr)
        return 2
    if args.limit < 0:
        print("--limit must be >= 0", file=sys.stderr)
        return 2

    left_path = Path(args.left_csv)
    right_path = Path(args.right_csv)

    left_label = args.left_label or left_path.stem
    right_label = args.right_label or right_path.stem

    try:
        left_values = load_scan(left_path)
        right_values = load_scan(right_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2

    changed = compare_scans(left_values, right_values, args.min_abs_delta)
    shared_count = len(left_values.keys() & right_values.keys())
    print(
        f"Compared '{left_path}' ({len(left_values)} regs) vs '{right_path}' ({len(right_values)} regs)"
    )
    print(f"Shared registers: {shared_count}")
    print(
        f"Changed registers (|delta| >= {args.min_abs_delta}): {len(changed)}"
    )

    if not changed:
        print("No changed registers found with the selected threshold.")
    else:
        print_table(changed, left_label=left_label, right_label=right_label, limit=args.limit)

    if args.output:
        output_path = Path(args.output)
        save_output(changed, output_path)
        print(f"Saved changed-register report to: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
