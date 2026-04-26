"""CLI utility to read a first block of Afore/Solarman holding registers."""

from __future__ import annotations

import argparse
import socket
import sys
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
except ModuleNotFoundError:  # Allows `python src/read_afore.py`
    from config import AppConfig, load_config  # type: ignore[no-redef]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read a block of registers from an Afore collector."
    )
    parser.add_argument("--start", type=int, default=0, help="First register index.")
    parser.add_argument("--count", type=int, default=100, help="Number of registers.")
    parser.add_argument(
        "--register-type",
        choices=("holding", "input"),
        default="holding",
        help="Register type to read (default: holding).",
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


def read_register_block(client: Any, start: int, count: int, register_type: str) -> list[int]:
    if register_type == "holding":
        return client.read_holding_registers(start, count)
    return client.read_input_registers(start, count)


def main() -> int:
    args = parse_args()
    if args.start < 0 or args.count <= 0:
        print("Invalid arguments: --start must be >= 0 and --count must be > 0.", file=sys.stderr)
        return 2

    try:
        config = load_config()
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        client = create_client(config)
    except Exception as exc:
        print(f"Connection setup failed: {exc}", file=sys.stderr)
        return 1

    try:
        values = read_register_block(client, args.start, args.count, args.register_type)
    except (socket.timeout, TimeoutError):
        print("Timeout while reading collector registers.", file=sys.stderr)
        return 1
    except (ConnectionError, OSError) as exc:
        print(f"Network error while reading collector: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - depends on runtime device behavior
        print(f"Protocol/runtime error while reading collector: {exc}", file=sys.stderr)
        return 1
    finally:
        close_client(client)

    if not isinstance(values, (list, tuple)):
        print(f"Unexpected response format: {type(values)}", file=sys.stderr)
        return 1

    print(
        f"Read {len(values)} {args.register_type} registers from "
        f"{config.collector_ip}:{config.collector_port}"
    )
    for index, value in enumerate(values):
        register = args.start + index
        print(f"[{register:05d}] {value}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
