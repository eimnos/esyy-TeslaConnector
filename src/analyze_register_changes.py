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


@dataclass(frozen=True, slots=True)
class SignedPairDelta:
    """Delta for one signed int32 register pair between two scan files."""

    high_register: int
    low_register: int
    left_value: int
    right_value: int

    @property
    def label(self) -> str:
        return f"{self.high_register}-{self.low_register}"

    @property
    def delta(self) -> int:
        return self.right_value - self.left_value

    @property
    def abs_delta(self) -> int:
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
    parser.add_argument(
        "--signed32-pairs",
        default=None,
        help=(
            "Optional comma-separated register pairs for signed int32 parsing, "
            "example: 524-525,526-527,528-529"
        ),
    )
    parser.add_argument(
        "--pairs-output",
        default=None,
        help="Optional CSV output path for signed int32 pair deltas.",
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


def parse_signed32_pairs(raw_pairs: str) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for chunk in raw_pairs.split(","):
        token = chunk.strip()
        if not token:
            continue
        if "-" not in token:
            raise ValueError(
                f"Invalid pair token {token!r}. Use format high-low, e.g. 524-525"
            )
        left_raw, right_raw = token.split("-", maxsplit=1)
        try:
            high = int(left_raw.strip())
            low = int(right_raw.strip())
        except ValueError as exc:
            raise ValueError(
                f"Invalid pair token {token!r}. Register indexes must be integers."
            ) from exc
        if high < 0 or low < 0:
            raise ValueError(f"Invalid pair token {token!r}. Register indexes must be >= 0.")
        pairs.append((high, low))

    if not pairs:
        raise ValueError("No valid signed32 pairs provided.")
    return pairs


def decode_signed_int32(high_word: float, low_word: float) -> int:
    high = int(high_word) & 0xFFFF
    low = int(low_word) & 0xFFFF
    value = (high << 16) | low
    if value & 0x80000000:
        value -= 0x100000000
    return value


def compare_signed32_pairs(
    left: dict[int, float], right: dict[int, float], pairs: list[tuple[int, int]]
) -> list[SignedPairDelta]:
    rows: list[SignedPairDelta] = []
    for high, low in pairs:
        if high not in left or low not in left or high not in right or low not in right:
            continue
        left_value = decode_signed_int32(left[high], left[low])
        right_value = decode_signed_int32(right[high], right[low])
        rows.append(
            SignedPairDelta(
                high_register=high,
                low_register=low,
                left_value=left_value,
                right_value=right_value,
            )
        )
    rows.sort(key=lambda item: item.abs_delta, reverse=True)
    return rows


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


def print_pair_table(rows: list[SignedPairDelta], left_label: str, right_label: str) -> None:
    left_header = left_label[:16]
    right_header = right_label[:16]
    print("\nSigned int32 pair deltas")
    print(
        f"{'Pair':>10}  {left_header:>16}  {right_header:>16}  {'Delta':>12}  {'|Delta|':>12}"
    )
    print("-" * 74)
    for item in rows:
        print(
            f"{item.label:>10}  "
            f"{item.left_value:>16}  "
            f"{item.right_value:>16}  "
            f"{item.delta:>12}  "
            f"{item.abs_delta:>12}"
        )


def save_pair_output(rows: list[SignedPairDelta], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            ["pair", "high_register", "low_register", "left_value", "right_value", "delta", "abs_delta"]
        )
        for item in rows:
            writer.writerow(
                [
                    item.label,
                    item.high_register,
                    item.low_register,
                    item.left_value,
                    item.right_value,
                    item.delta,
                    item.abs_delta,
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

    if args.signed32_pairs:
        try:
            signed_pairs = parse_signed32_pairs(args.signed32_pairs)
        except ValueError as exc:
            print(f"Input error: {exc}", file=sys.stderr)
            return 2

        pair_rows = compare_signed32_pairs(left_values, right_values, signed_pairs)
        if not pair_rows:
            print("\nSigned int32 pair deltas: no complete pairs found in both files.")
        else:
            print_pair_table(pair_rows, left_label=left_label, right_label=right_label)
            if args.pairs_output:
                pairs_output_path = Path(args.pairs_output)
                save_pair_output(pair_rows, pairs_output_path)
                print(f"Saved signed32 pair report to: {pairs_output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
