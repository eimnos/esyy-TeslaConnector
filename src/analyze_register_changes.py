"""Compare two Afore scan CSV files and show only changed registers."""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


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


@dataclass(frozen=True, slots=True)
class GridCandidate:
    """Candidate register/pair that might represent instantaneous grid power."""

    representation: str
    start_register: int
    end_register: int
    scale_label: str
    scale_factor: float
    target_w: float
    left_raw_value: int
    right_raw_value: int
    left_scaled_w: float
    right_scaled_w: float
    delta_scaled_w: float
    abs_delta_scaled_w: float
    match_error_w: float
    match_error_ratio: float
    is_tracking_candidate: bool

    @property
    def register_label(self) -> str:
        if self.start_register == self.end_register:
            return str(self.start_register)
        return f"{self.start_register}-{self.end_register}"


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
    parser.add_argument(
        "--find-grid-candidates",
        action="store_true",
        help="Run heuristic search for instantaneous grid-power candidate registers.",
    )
    parser.add_argument(
        "--candidate-targets",
        default="4700,470,47,47000",
        help=(
            "Comma-separated target watt values used for candidate matching "
            "(default: 4700,470,47,47000)."
        ),
    )
    parser.add_argument(
        "--candidate-max-error-ratio",
        type=float,
        default=0.25,
        help=(
            "Maximum relative error allowed for target matching "
            "(default: 0.25 = 25%)."
        ),
    )
    parser.add_argument(
        "--candidate-min-abs-delta-w",
        type=float,
        default=0.0,
        help="Ignore candidates whose |delta| in W is below this threshold.",
    )
    parser.add_argument(
        "--candidate-track-threshold-w",
        type=float,
        default=500.0,
        help=(
            "Threshold used only to flag whether candidate appears to track large load changes "
            "(default: 500W)."
        ),
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=200,
        help="Maximum number of candidate rows to keep/save (default: 200).",
    )
    parser.add_argument(
        "--candidate-output",
        default=None,
        help="Optional CSV output path for grid candidate analysis.",
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


def decode_unsigned_int32(high_word: float, low_word: float) -> int:
    high = int(high_word) & 0xFFFF
    low = int(low_word) & 0xFFFF
    return (high << 16) | low


def decode_signed_int16(word: float) -> int:
    value = int(word) & 0xFFFF
    if value & 0x8000:
        value -= 0x10000
    return value


def decode_unsigned_int16(word: float) -> int:
    return int(word) & 0xFFFF


def parse_candidate_targets(raw_targets: str) -> list[float]:
    values: list[float] = []
    for chunk in raw_targets.split(","):
        token = chunk.strip()
        if not token:
            continue
        try:
            value = float(token)
        except ValueError as exc:
            raise ValueError(
                f"Invalid candidate target {token!r}. Use numeric values separated by commas."
            ) from exc
        if value <= 0:
            raise ValueError(f"Invalid candidate target {token!r}. Value must be > 0.")
        values.append(value)

    if not values:
        raise ValueError("No valid candidate targets provided.")
    return values


def _iter_decoded_candidates(
    left: dict[int, float], right: dict[int, float]
) -> Iterable[tuple[str, int, int, int, int]]:
    shared = sorted(left.keys() & right.keys())
    shared_set = set(shared)

    for register in shared:
        left_word = left[register]
        right_word = right[register]
        yield (
            "uint16",
            register,
            register,
            decode_unsigned_int16(left_word),
            decode_unsigned_int16(right_word),
        )
        yield (
            "int16",
            register,
            register,
            decode_signed_int16(left_word),
            decode_signed_int16(right_word),
        )

    for register in shared:
        next_register = register + 1
        if next_register not in shared_set:
            continue

        left_first = left[register]
        left_second = left[next_register]
        right_first = right[register]
        right_second = right[next_register]

        # Big-endian: register is high word, next register is low word.
        yield (
            "uint32_be",
            register,
            next_register,
            decode_unsigned_int32(left_first, left_second),
            decode_unsigned_int32(right_first, right_second),
        )
        yield (
            "int32_be",
            register,
            next_register,
            decode_signed_int32(left_first, left_second),
            decode_signed_int32(right_first, right_second),
        )

        # Little-endian: register is low word, next register is high word.
        yield (
            "uint32_le",
            register,
            next_register,
            decode_unsigned_int32(left_second, left_first),
            decode_unsigned_int32(right_second, right_first),
        )
        yield (
            "int32_le",
            register,
            next_register,
            decode_signed_int32(left_second, left_first),
            decode_signed_int32(right_second, right_first),
        )


def find_grid_candidates(
    left: dict[int, float],
    right: dict[int, float],
    *,
    targets_w: list[float],
    max_error_ratio: float,
    min_abs_delta_w: float,
    track_threshold_w: float,
    limit: int,
) -> list[GridCandidate]:
    if max_error_ratio < 0:
        raise ValueError("max_error_ratio must be >= 0")
    if min_abs_delta_w < 0:
        raise ValueError("min_abs_delta_w must be >= 0")
    if track_threshold_w < 0:
        raise ValueError("track_threshold_w must be >= 0")
    if limit < 0:
        raise ValueError("limit must be >= 0")

    scale_options = [
        ("x1", 1.0),
        ("x10", 10.0),
        ("x100", 100.0),
        ("/10", 0.1),
        ("/100", 0.01),
    ]

    rows: list[GridCandidate] = []
    for representation, start, end, left_raw, right_raw in _iter_decoded_candidates(left, right):
        for scale_label, scale_factor in scale_options:
            left_scaled = float(left_raw) * scale_factor
            right_scaled = float(right_raw) * scale_factor
            delta_scaled = right_scaled - left_scaled
            abs_delta_scaled = abs(delta_scaled)
            if abs_delta_scaled < min_abs_delta_w:
                continue

            best_target = targets_w[0]
            best_error_w = abs(abs(right_scaled) - best_target)
            best_ratio = best_error_w / best_target
            for target in targets_w[1:]:
                error_w = abs(abs(right_scaled) - target)
                ratio = error_w / target
                if ratio < best_ratio:
                    best_target = target
                    best_error_w = error_w
                    best_ratio = ratio

            if best_ratio > max_error_ratio:
                continue

            rows.append(
                GridCandidate(
                    representation=representation,
                    start_register=start,
                    end_register=end,
                    scale_label=scale_label,
                    scale_factor=scale_factor,
                    target_w=best_target,
                    left_raw_value=left_raw,
                    right_raw_value=right_raw,
                    left_scaled_w=left_scaled,
                    right_scaled_w=right_scaled,
                    delta_scaled_w=delta_scaled,
                    abs_delta_scaled_w=abs_delta_scaled,
                    match_error_w=best_error_w,
                    match_error_ratio=best_ratio,
                    is_tracking_candidate=abs_delta_scaled >= track_threshold_w,
                )
            )

    rows.sort(
        key=lambda item: (
            0 if item.is_tracking_candidate else 1,
            item.match_error_ratio,
            -item.abs_delta_scaled_w,
            item.start_register,
            item.end_register,
            item.representation,
            item.scale_label,
        )
    )
    if limit == 0:
        return rows
    return rows[:limit]


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


def print_candidate_table(
    rows: list[GridCandidate], left_label: str, right_label: str, limit: int
) -> None:
    shown = rows if limit <= 0 else rows[:limit]
    left_header = left_label[:12]
    right_header = right_label[:12]

    print("\nGrid-power heuristic candidates")
    print(
        f"{'Reg':>9}  {'Type':>9}  {'Scale':>5}  {'TargetW':>8}  "
        f"{left_header:>12}  {right_header:>12}  {'DeltaW':>10}  {'Err%':>7}  {'Track':>6}"
    )
    print("-" * 100)
    for item in shown:
        print(
            f"{item.register_label:>9}  "
            f"{item.representation:>9}  "
            f"{item.scale_label:>5}  "
            f"{item.target_w:>8.1f}  "
            f"{item.left_scaled_w:>12.1f}  "
            f"{item.right_scaled_w:>12.1f}  "
            f"{item.delta_scaled_w:>10.1f}  "
            f"{item.match_error_ratio * 100.0:>6.1f}%  "
            f"{'yes' if item.is_tracking_candidate else 'no':>6}"
        )

    if limit > 0 and len(rows) > limit:
        print(f"... {len(rows) - limit} additional candidates not shown")


def save_candidate_output(rows: list[GridCandidate], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "register_label",
                "start_register",
                "end_register",
                "representation",
                "scale_label",
                "scale_factor",
                "target_w",
                "left_raw_value",
                "right_raw_value",
                "left_scaled_w",
                "right_scaled_w",
                "delta_scaled_w",
                "abs_delta_scaled_w",
                "match_error_w",
                "match_error_ratio",
                "is_tracking_candidate",
            ]
        )
        for item in rows:
            writer.writerow(
                [
                    item.register_label,
                    item.start_register,
                    item.end_register,
                    item.representation,
                    item.scale_label,
                    item.scale_factor,
                    item.target_w,
                    item.left_raw_value,
                    item.right_raw_value,
                    item.left_scaled_w,
                    item.right_scaled_w,
                    item.delta_scaled_w,
                    item.abs_delta_scaled_w,
                    item.match_error_w,
                    item.match_error_ratio,
                    str(item.is_tracking_candidate).lower(),
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
    if args.candidate_max_error_ratio < 0:
        print("--candidate-max-error-ratio must be >= 0", file=sys.stderr)
        return 2
    if args.candidate_min_abs_delta_w < 0:
        print("--candidate-min-abs-delta-w must be >= 0", file=sys.stderr)
        return 2
    if args.candidate_track_threshold_w < 0:
        print("--candidate-track-threshold-w must be >= 0", file=sys.stderr)
        return 2
    if args.candidate_limit < 0:
        print("--candidate-limit must be >= 0", file=sys.stderr)
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

    if args.find_grid_candidates or args.candidate_output:
        try:
            targets = parse_candidate_targets(args.candidate_targets)
            candidate_rows = find_grid_candidates(
                left_values,
                right_values,
                targets_w=targets,
                max_error_ratio=args.candidate_max_error_ratio,
                min_abs_delta_w=args.candidate_min_abs_delta_w,
                track_threshold_w=args.candidate_track_threshold_w,
                limit=args.candidate_limit,
            )
        except ValueError as exc:
            print(f"Input error: {exc}", file=sys.stderr)
            return 2

        if not candidate_rows:
            print("\nGrid-power heuristic candidates: no rows found with current filters.")
        else:
            print_candidate_table(
                candidate_rows,
                left_label=left_label,
                right_label=right_label,
                limit=args.limit,
            )

        if args.candidate_output:
            candidate_output_path = Path(args.candidate_output)
            save_candidate_output(candidate_rows, candidate_output_path)
            print(f"Saved grid candidate report to: {candidate_output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
