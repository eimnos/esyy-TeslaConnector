"""Wave 9F sync loop for HA/Afore candidate register values."""

from __future__ import annotations

import argparse
import csv
import socket
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from pysolarmanv5 import PySolarmanV5
except ImportError as exc:  # pragma: no cover - runtime dependency check
    PySolarmanV5 = None  # type: ignore[assignment]
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None

try:
    from src.afore_ha_candidates import parse_signed_int32, parse_unsigned_int32
    from src.config import AppConfig, load_config
    from src.supabase_sink import SupabaseSink, SupabaseSinkConfig, SupabaseSinkError
except ModuleNotFoundError:  # Allows `python src/ha_candidates_sync.py`
    from afore_ha_candidates import parse_signed_int32, parse_unsigned_int32  # type: ignore[no-redef]
    from config import AppConfig, load_config  # type: ignore[no-redef]
    from supabase_sink import SupabaseSink, SupabaseSinkConfig, SupabaseSinkError  # type: ignore[no-redef]


POWER_SCALES = (1.0, 0.1, 0.01)
SOURCE_NAME = "ha_candidate_sync"
CSV_COLUMNS = [
    "sample_timestamp",
    "cycle",
    "register_name",
    "register_address",
    "register_order",
    "raw_high",
    "raw_low",
    "decoded_int32",
    "scale",
    "value_w",
    "unit",
    "source",
    "notes",
]


@dataclass(frozen=True, slots=True)
class PairCandidate:
    register_name: str
    register_a: int
    register_b: int
    signed: bool
    unit: str
    notes: str
    scales: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class SingleCandidate:
    register_name: str
    register_address: int
    scale: float
    unit: str
    notes: str


PAIR_POWER_CANDIDATES: tuple[PairCandidate, ...] = (
    PairCandidate(
        register_name="grid_active_power",
        register_a=535,
        register_b=536,
        signed=True,
        unit="W",
        notes="candidate|unconfirmed|kind=power",
        scales=POWER_SCALES,
    ),
    PairCandidate(
        register_name="load_power",
        register_a=547,
        register_b=548,
        signed=True,
        unit="W",
        notes="candidate|unconfirmed|kind=power",
        scales=POWER_SCALES,
    ),
    PairCandidate(
        register_name="pv_total_power",
        register_a=553,
        register_b=554,
        signed=False,
        unit="W",
        notes="candidate|unconfirmed|kind=power",
        scales=POWER_SCALES,
    ),
)

ENERGY_SINGLE_CANDIDATES: tuple[SingleCandidate, ...] = (
    SingleCandidate(
        register_name="meter_today_export_energy",
        register_address=1002,
        scale=0.1,
        unit="kWh",
        notes="candidate|unconfirmed|kind=energy",
    ),
    SingleCandidate(
        register_name="meter_today_import_energy",
        register_address=1003,
        scale=0.1,
        unit="kWh",
        notes="candidate|unconfirmed|kind=energy",
    ),
    SingleCandidate(
        register_name="meter_today_load_consumption",
        register_address=1004,
        scale=0.1,
        unit="kWh",
        notes="candidate|unconfirmed|kind=energy",
    ),
)

ENERGY_PAIR_CANDIDATES: tuple[PairCandidate, ...] = (
    PairCandidate(
        register_name="meter_today_production_energy",
        register_a=1007,
        register_b=1006,
        signed=False,
        unit="kWh",
        notes="candidate|unconfirmed|kind=energy",
        scales=(0.1,),
    ),
    PairCandidate(
        register_name="meter_total_production_energy",
        register_a=1027,
        register_b=1026,
        signed=False,
        unit="kWh",
        notes="candidate|unconfirmed|kind=energy",
        scales=(0.1,),
    ),
    PairCandidate(
        register_name="meter_total_export_energy",
        register_a=1019,
        register_b=1018,
        signed=False,
        unit="kWh",
        notes="candidate|unconfirmed|kind=energy",
        scales=(0.1,),
    ),
    PairCandidate(
        register_name="meter_total_import_energy",
        register_a=1021,
        register_b=1020,
        signed=False,
        unit="kWh",
        notes="candidate|unconfirmed|kind=energy",
        scales=(0.1,),
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Wave 9F sync of HA/Afore candidate registers into Supabase."
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Enable periodic polling loop.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1,
        help="Number of cycles in watch mode (0 = infinite).",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=None,
        help="Override polling seconds (default: POLL_SECONDS from .env).",
    )
    parser.add_argument(
        "--log-path",
        default="data/ha_candidates_sync_log.csv",
        help="CSV output path (default: data/ha_candidates_sync_log.csv).",
    )
    parser.add_argument(
        "--include-energy-block",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include 1002+ meter candidates (default: true).",
    )
    parser.add_argument(
        "--disable-supabase",
        action="store_true",
        help="Skip Supabase writes even if SUPABASE_ENABLED=true.",
    )
    return parser.parse_args()


def create_optional_supabase_sink(
    config: AppConfig,
    *,
    disable_supabase: bool = False,
) -> tuple[SupabaseSink | None, str]:
    if disable_supabase:
        return None, "forced_disabled"
    if not config.supabase_enabled:
        return None, "disabled"
    if not config.supabase_url or not config.supabase_service_role_key:
        return None, "missing_config"
    sink_config = SupabaseSinkConfig(
        url=config.supabase_url,
        service_role_key=config.supabase_service_role_key,
    )
    return SupabaseSink(sink_config), "enabled"


def _close_client(client: Any) -> None:
    disconnect = getattr(client, "disconnect", None)
    if callable(disconnect):
        disconnect()
        return
    close = getattr(client, "close", None)
    if callable(close):
        close()


class HaCandidateSyncReader:
    """Read target input-register blocks used by HA/Afore candidates."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._client: Any | None = None

    def connect(self) -> None:
        if self._client is not None:
            return
        if PySolarmanV5 is None:
            raise RuntimeError(
                "pysolarmanv5 is not installed. Run: pip install -r requirements.txt"
            ) from IMPORT_ERROR
        self._client = PySolarmanV5(
            self._config.collector_ip,
            self._config.collector_serial,
            port=self._config.collector_port,
            mb_slave_id=1,
            verbose=False,
        )

    def close(self) -> None:
        if self._client is None:
            return
        _close_client(self._client)
        self._client = None

    def read_registers(self, *, include_energy_block: bool) -> dict[int, float]:
        if self._client is None:
            self.connect()
        assert self._client is not None

        try:
            power_block = self._client.read_input_registers(535, 26)  # 535..560
            if not isinstance(power_block, (list, tuple)):
                raise TypeError(
                    f"Unexpected response type for power block: {type(power_block)}"
                )
            values: dict[int, float] = {
                535 + index: float(raw) for index, raw in enumerate(power_block)
            }

            if include_energy_block:
                meter_block = self._client.read_input_registers(1002, 29)  # 1002..1030
                if not isinstance(meter_block, (list, tuple)):
                    raise TypeError(
                        f"Unexpected response type for meter block: {type(meter_block)}"
                    )
                values.update(
                    {1002 + index: float(raw) for index, raw in enumerate(meter_block)}
                )
        except (socket.timeout, TimeoutError) as exc:
            self.close()
            raise RuntimeError("Timeout while reading HA/Afore candidate registers.") from exc
        except (ConnectionError, OSError) as exc:
            self.close()
            raise RuntimeError("Network error while reading HA/Afore candidate registers.") from exc
        except Exception:
            self.close()
            raise

        return values


def _decode_pair(
    register_values: Mapping[int, float],
    *,
    register_a: int,
    register_b: int,
    order: str,
    signed: bool,
) -> tuple[int, int, int, int, int]:
    if order not in {"ab", "ba"}:
        raise ValueError(f"Unsupported order: {order}")

    if order == "ab":
        high_register = register_a
        low_register = register_b
    else:
        high_register = register_b
        low_register = register_a

    raw_high = int(register_values[high_register])
    raw_low = int(register_values[low_register])
    if signed:
        decoded = parse_signed_int32(raw_high, raw_low)
    else:
        decoded = parse_unsigned_int32(raw_high, raw_low)
    return decoded, high_register, low_register, raw_high, raw_low


def _pair_rows_for_candidate(
    register_values: Mapping[int, float],
    *,
    sample_timestamp: str,
    candidate: PairCandidate,
    orders: Iterable[str],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    decode_label = "s32" if candidate.signed else "u32"
    for order in orders:
        decoded, high_register, low_register, raw_high, raw_low = _decode_pair(
            register_values,
            register_a=candidate.register_a,
            register_b=candidate.register_b,
            order=order,
            signed=candidate.signed,
        )

        for scale in candidate.scales:
            rows.append(
                {
                    "sample_timestamp": sample_timestamp,
                    "register_name": candidate.register_name,
                    "register_address": f"{candidate.register_a}-{candidate.register_b}",
                    "register_order": f"[{high_register},{low_register}]",
                    "raw_high": raw_high,
                    "raw_low": raw_low,
                    "decoded_int32": decoded,
                    "scale": float(scale),
                    "value_w": float(decoded) * float(scale),
                    "unit": candidate.unit,
                    "source": SOURCE_NAME,
                    "notes": f"{candidate.notes}|decode={decode_label}",
                }
            )
    return rows


def _single_rows_for_candidate(
    register_values: Mapping[int, float],
    *,
    sample_timestamp: str,
    candidate: SingleCandidate,
) -> list[dict[str, object]]:
    raw_value = int(register_values[candidate.register_address])
    return [
        {
            "sample_timestamp": sample_timestamp,
            "register_name": candidate.register_name,
            "register_address": str(candidate.register_address),
            "register_order": f"[{candidate.register_address}]",
            "raw_high": raw_value,
            "raw_low": None,
            "decoded_int32": raw_value,
            "scale": float(candidate.scale),
            "value_w": float(raw_value) * float(candidate.scale),
            "unit": candidate.unit,
            "source": SOURCE_NAME,
            "notes": f"{candidate.notes}|decode=u16",
        }
    ]


def build_candidate_sample_rows(
    register_values: Mapping[int, float],
    *,
    sample_timestamp: str | None = None,
    include_energy_block: bool = True,
) -> list[dict[str, object]]:
    timestamp = sample_timestamp or datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, object]] = []

    for candidate in PAIR_POWER_CANDIDATES:
        rows.extend(
            _pair_rows_for_candidate(
                register_values,
                sample_timestamp=timestamp,
                candidate=candidate,
                orders=("ab", "ba"),
            )
        )

    if include_energy_block:
        for candidate in ENERGY_SINGLE_CANDIDATES:
            rows.extend(
                _single_rows_for_candidate(
                    register_values,
                    sample_timestamp=timestamp,
                    candidate=candidate,
                )
            )
        for candidate in ENERGY_PAIR_CANDIDATES:
            rows.extend(
                _pair_rows_for_candidate(
                    register_values,
                    sample_timestamp=timestamp,
                    candidate=candidate,
                    orders=("ab", "ba"),
                )
            )

    return rows


def ensure_csv_writer(log_path: Path) -> tuple[csv.DictWriter, Any]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = log_path.exists()
    csv_file = log_path.open("a", newline="", encoding="utf-8")
    writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
    if not file_exists or log_path.stat().st_size == 0:
        writer.writeheader()
    return writer, csv_file


def write_rows_to_csv(
    writer: csv.DictWriter,
    rows: list[dict[str, object]],
    *,
    cycle: int,
) -> None:
    for row in rows:
        csv_row = dict(row)
        csv_row["cycle"] = cycle
        writer.writerow(csv_row)


def insert_rows_supabase(
    sink: SupabaseSink | None,
    rows: Iterable[Mapping[str, object]],
) -> list[str]:
    if sink is None:
        return []

    errors: list[str] = []
    for row in rows:
        try:
            sink.insert_afore_candidate_sample(row)
        except SupabaseSinkError as exc:
            errors.append(str(exc))
    return errors


def _find_value(
    rows: list[Mapping[str, object]],
    *,
    register_name: str,
    register_order: str,
    scale: float,
) -> float | None:
    for row in rows:
        if (
            row.get("register_name") == register_name
            and row.get("register_order") == register_order
            and float(row.get("scale", 0.0)) == float(scale)
        ):
            value = row.get("value_w")
            try:
                return float(value) if value is not None else None
            except (TypeError, ValueError):
                return None
    return None


def _loop_limit(watch: bool, iterations: int) -> int:
    if not watch:
        return 1
    return iterations


def main() -> int:
    args = parse_args()
    if args.iterations < 0:
        print("--iterations must be >= 0", file=sys.stderr)
        return 2
    if args.poll_seconds is not None and args.poll_seconds <= 0:
        print("--poll-seconds must be > 0", file=sys.stderr)
        return 2

    try:
        config = load_config()
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    poll_seconds = args.poll_seconds or config.poll_seconds
    if args.watch and poll_seconds < 30:
        print(
            f"Warning: poll interval {poll_seconds}s may be too aggressive. "
            "For mapping keep 30-60s cadence.",
            file=sys.stderr,
        )

    sink, sink_state = create_optional_supabase_sink(
        config,
        disable_supabase=args.disable_supabase,
    )
    if sink_state == "enabled":
        print("Supabase sink: enabled (best effort).")
    elif sink_state == "disabled":
        print("Supabase sink: disabled (SUPABASE_ENABLED=false).")
    elif sink_state == "forced_disabled":
        print("Supabase sink: disabled via --disable-supabase.")
    else:
        print(
            "Supabase sink: missing config (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY).",
            file=sys.stderr,
        )

    writer, csv_file = ensure_csv_writer(Path(args.log_path))
    reader = HaCandidateSyncReader(config)
    print(
        "Wave 9F HA candidate sync started "
        "(read-only inverter scan, no Tesla commands, no automation)."
    )

    max_iterations = _loop_limit(args.watch, args.iterations)
    cycle = 0
    try:
        while True:
            cycle += 1
            if max_iterations != 0 and cycle > max_iterations:
                break

            started_at = time.time()
            try:
                register_values = reader.read_registers(
                    include_energy_block=args.include_energy_block
                )
                sample_timestamp = datetime.now(timezone.utc).isoformat()
                rows = build_candidate_sample_rows(
                    register_values,
                    sample_timestamp=sample_timestamp,
                    include_energy_block=args.include_energy_block,
                )
                write_rows_to_csv(writer, rows, cycle=cycle)
                csv_file.flush()

                supabase_errors = insert_rows_supabase(sink, rows)
                grid_ab = _find_value(
                    rows,
                    register_name="grid_active_power",
                    register_order="[535,536]",
                    scale=1.0,
                )
                grid_ba = _find_value(
                    rows,
                    register_name="grid_active_power",
                    register_order="[536,535]",
                    scale=1.0,
                )
                load_ab = _find_value(
                    rows,
                    register_name="load_power",
                    register_order="[547,548]",
                    scale=1.0,
                )
                load_ba = _find_value(
                    rows,
                    register_name="load_power",
                    register_order="[548,547]",
                    scale=1.0,
                )
                pv_ab = _find_value(
                    rows,
                    register_name="pv_total_power",
                    register_order="[553,554]",
                    scale=1.0,
                )
                pv_ba = _find_value(
                    rows,
                    register_name="pv_total_power",
                    register_order="[554,553]",
                    scale=1.0,
                )

                print(
                    f"[cycle {cycle:04d}] "
                    f"rows={len(rows)} "
                    f"grid_ab={grid_ab}W grid_ba={grid_ba}W "
                    f"load_ab={load_ab}W load_ba={load_ba}W "
                    f"pv_ab={pv_ab}W pv_ba={pv_ba}W"
                )
                if supabase_errors:
                    print(
                        f"[cycle {cycle:04d}] supabase errors={len(supabase_errors)} "
                        f"(first: {supabase_errors[0]})",
                        file=sys.stderr,
                    )
            except Exception as exc:
                print(
                    f"[cycle {cycle:04d}] sync error: {type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )

            if not args.watch:
                break
            if max_iterations != 0 and cycle >= max_iterations:
                break
            elapsed = time.time() - started_at
            sleep_seconds = max(0.0, poll_seconds - elapsed)
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        reader.close()
        if sink is not None:
            sink.close()
        csv_file.close()

    print(f"Wave 9F sync completed. Log file: {args.log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
