"""Read and normalize Afore candidate registers for Wave 3 dry-run control."""

from __future__ import annotations

import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

try:
    from pysolarmanv5 import PySolarmanV5
except ImportError as exc:  # pragma: no cover - runtime dependency check
    PySolarmanV5 = None  # type: ignore[assignment]
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None

try:
    from src.config import AppConfig
except ModuleNotFoundError:  # Allows `python src/afore_reader.py`
    from config import AppConfig  # type: ignore[no-redef]


@dataclass(frozen=True, slots=True)
class GridPowerNormalization:
    """Normalized import/export values from a raw grid power reading."""

    grid_power_raw_w: float
    grid_sign_mode: str
    grid_sign_assumed_mode: str
    grid_sign_unknown: bool
    grid_import_w: float
    grid_export_w: float


@dataclass(frozen=True, slots=True)
class AforeSnapshot:
    """Normalized inverter sample built from candidate Wave 3 registers."""

    timestamp_utc: str
    pv_power_w: float
    grid_power_raw_w: float
    grid_sign_mode: str
    grid_sign_assumed_mode: str
    grid_sign_unknown: bool
    grid_import_w: float
    grid_export_w: float


def parse_signed_int32(high_word: int | float, low_word: int | float) -> int:
    """Decode a signed int32 from 2 Modbus words (high, low)."""

    high = int(high_word) & 0xFFFF
    low = int(low_word) & 0xFFFF
    value = (high << 16) | low
    if value & 0x80000000:
        value -= 0x100000000
    return value


def normalize_grid_power(grid_power_raw_w: float, sign_mode: str) -> GridPowerNormalization:
    """Normalize import/export power based on sign convention mode."""

    mode = sign_mode.strip().lower()
    if mode not in {"unknown", "import_positive", "export_positive"}:
        raise ValueError(
            "sign_mode must be one of: unknown, import_positive, export_positive"
        )

    if mode == "import_positive":
        import_w = max(grid_power_raw_w, 0.0)
        export_w = max(-grid_power_raw_w, 0.0)
        assumed_mode = mode
        sign_unknown = False
    elif mode == "export_positive":
        import_w = max(-grid_power_raw_w, 0.0)
        export_w = max(grid_power_raw_w, 0.0)
        assumed_mode = mode
        sign_unknown = False
    else:
        # Conservative default for unknown sign mode:
        # treat positive as import and negative as export.
        import_w = max(grid_power_raw_w, 0.0)
        export_w = max(-grid_power_raw_w, 0.0)
        assumed_mode = "import_positive"
        sign_unknown = True

    return GridPowerNormalization(
        grid_power_raw_w=grid_power_raw_w,
        grid_sign_mode=mode,
        grid_sign_assumed_mode=assumed_mode,
        grid_sign_unknown=sign_unknown,
        grid_import_w=import_w,
        grid_export_w=export_w,
    )


def build_snapshot_from_registers(
    register_values: Mapping[int, float],
    config: AppConfig,
    timestamp_utc: str | None = None,
) -> AforeSnapshot:
    """Build a normalized snapshot from a register map and current config."""

    try:
        pv_raw = float(register_values[config.afore_pv_power_register])
        grid_high = register_values[config.afore_grid_power_register_high]
        grid_low = register_values[config.afore_grid_power_register_low]
    except KeyError as exc:
        raise KeyError(
            f"Missing expected register in scan data: {exc}. "
            "Check AFORE_* register configuration."
        ) from exc

    pv_power_w = pv_raw * config.afore_pv_power_scale
    grid_signed = parse_signed_int32(grid_high, grid_low)
    grid_power_raw_w = float(grid_signed) * config.afore_grid_power_scale
    grid_normalized = normalize_grid_power(grid_power_raw_w, config.afore_grid_sign_mode)

    return AforeSnapshot(
        timestamp_utc=timestamp_utc or datetime.now(timezone.utc).isoformat(),
        pv_power_w=pv_power_w,
        grid_power_raw_w=grid_normalized.grid_power_raw_w,
        grid_sign_mode=grid_normalized.grid_sign_mode,
        grid_sign_assumed_mode=grid_normalized.grid_sign_assumed_mode,
        grid_sign_unknown=grid_normalized.grid_sign_unknown,
        grid_import_w=grid_normalized.grid_import_w,
        grid_export_w=grid_normalized.grid_export_w,
    )


def _close_client(client: Any) -> None:
    disconnect = getattr(client, "disconnect", None)
    if callable(disconnect):
        disconnect()
        return

    close = getattr(client, "close", None)
    if callable(close):
        close()


class AforeReader:
    """Read candidate Afore metrics from Solarman collector input registers."""

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

    def _read_candidate_registers(self) -> dict[int, float]:
        if self._client is None:
            self.connect()
        assert self._client is not None

        min_register = min(
            self._config.afore_pv_power_register,
            self._config.afore_grid_power_register_high,
            self._config.afore_grid_power_register_low,
        )
        max_register = max(
            self._config.afore_pv_power_register,
            self._config.afore_grid_power_register_high,
            self._config.afore_grid_power_register_low,
        )
        count = max_register - min_register + 1

        values = self._client.read_input_registers(min_register, count)
        if not isinstance(values, (list, tuple)):
            raise TypeError(f"Unexpected register response type: {type(values)}")

        return {min_register + idx: float(value) for idx, value in enumerate(values)}

    def read_snapshot(self) -> AforeSnapshot:
        """Read and normalize one inverter snapshot."""

        try:
            registers = self._read_candidate_registers()
        except (socket.timeout, TimeoutError) as exc:
            self.close()
            raise RuntimeError("Timeout while reading Afore candidate registers") from exc
        except (ConnectionError, OSError) as exc:
            self.close()
            raise RuntimeError("Network error while reading Afore candidate registers") from exc
        except Exception:
            self.close()
            raise

        return build_snapshot_from_registers(registers, self._config)
