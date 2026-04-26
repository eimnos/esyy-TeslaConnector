"""Scan Afore/Solarman registers in blocks and store values into CSV."""

from __future__ import annotations

import argparse
import csv
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from pysolarmanv5 import PySolarmanV5
except ImportError as exc:  # pragma: no cover - runtime dependency check
    PySolarmanV5 = None  # type: ignore[assignment]
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None

try:
    from src.config import AppConfig, load_config
except ModuleNotFoundError:  # Allows `python src/scan_afore_registers.py`
    from config import AppConfig, load_config  # type: ignore[no-redef]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan holding registers on the Afore Solarman collector."
    )
    parser.add_argument("--start", type=int, default=0, help="Scan start register (inclusive).")
    parser.add_argument("--end", type=int, default=500, help="Scan end register (inclusive).")
    parser.add_argument("--block-size", type=int, default=50, help="Registers per read block.")
    parser.add_argument(
        "--output",
        default="data/afore_scan.csv",
        help="Output CSV path (default: data/afore_scan.csv).",
    )
    return parser.parse_args()


def create_client(config: AppConfig) -> Any:
    if PySolarmanV5 is None:
        raise RuntimeError(
            "pysolarmanv5 is not installed. Run: pip install -r requirements.txt"
        ) from IMPORT_ERROR
    return PySolarmanV5(
        config.collector_ip,
        config.collector_serial,
        port=config.collector_port,
        mb_slave_id=1,
        verbose=False,
    )


def close_client(client: Any) -> None:
    disconnect = getattr(client, "disconnect", None)
    if callable(disconnect):
        disconnect()
        return

    close = getattr(client, "close", None)
    if callable(close):
        close()


def block_ranges(start: int, end: int, block_size: int) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    current = start
    while current <= end:
        count = min(block_size, end - current + 1)
        ranges.append((current, count))
        current += block_size
    return ranges


def main() -> int:
    args = parse_args()

    if args.start < 0 or args.end < args.start:
        print("Invalid range: ensure 0 <= start <= end.", file=sys.stderr)
        return 2
    if args.block_size <= 0:
        print("Invalid --block-size: must be > 0.", file=sys.stderr)
        return 2

    try:
        config = load_config()
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ranges = block_ranges(args.start, args.end, args.block_size)
    total_blocks = len(ranges)
    total_rows = 0

    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["timestamp", "register", "value"])

        try:
            client = create_client(config)
        except Exception as exc:
            print(f"Connection setup failed: {exc}", file=sys.stderr)
            return 1

        try:
            for idx, (block_start, block_count) in enumerate(ranges, start=1):
                block_end = block_start + block_count - 1
                print(f"[{idx}/{total_blocks}] Reading registers {block_start}..{block_end}")

                try:
                    values = client.read_holding_registers(block_start, block_count)
                    if not isinstance(values, (list, tuple)):
                        raise TypeError(
                            f"Unexpected response type {type(values)} for block {block_start}..{block_end}"
                        )

                    now = datetime.now(timezone.utc).isoformat()
                    for offset, value in enumerate(values):
                        writer.writerow([now, block_start + offset, value])
                        total_rows += 1
                except (socket.timeout, TimeoutError):
                    print(
                        f"  ! Timeout on block {block_start}..{block_end}. Continuing.",
                        file=sys.stderr,
                    )
                except (ConnectionError, OSError) as exc:
                    print(
                        f"  ! Network error on block {block_start}..{block_end}: {exc}. Continuing.",
                        file=sys.stderr,
                    )
                except Exception as exc:  # pragma: no cover - runtime device behavior
                    print(
                        f"  ! Read/protocol error on block {block_start}..{block_end}: {exc}. Continuing.",
                        file=sys.stderr,
                    )
        finally:
            close_client(client)

    print(f"Scan completed. CSV rows written: {total_rows}")
    print(f"Output file: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
