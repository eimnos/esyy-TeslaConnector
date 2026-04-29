"""Wave 9E helpers for Afore/HA candidate register parsing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping


def parse_signed_int32(high_word: int | float, low_word: int | float) -> int:
    """Decode signed int32 from 2 words using explicit high/low order."""

    high = int(high_word) & 0xFFFF
    low = int(low_word) & 0xFFFF
    value = (high << 16) | low
    if value & 0x80000000:
        value -= 0x100000000
    return value


def parse_unsigned_int32(high_word: int | float, low_word: int | float) -> int:
    """Decode unsigned int32 from 2 words using explicit high/low order."""

    high = int(high_word) & 0xFFFF
    low = int(low_word) & 0xFFFF
    return (high << 16) | low


def parse_s32_order_ab(register_values: Mapping[int, float], register_a: int, register_b: int) -> int:
    """Interpret pair as [A=high, B=low]."""

    return parse_signed_int32(register_values[register_a], register_values[register_b])


def parse_s32_order_ba(register_values: Mapping[int, float], register_a: int, register_b: int) -> int:
    """Interpret pair as [B=high, A=low]."""

    return parse_signed_int32(register_values[register_b], register_values[register_a])


def parse_u32_order_ab(register_values: Mapping[int, float], register_a: int, register_b: int) -> int:
    """Interpret pair as [A=high, B=low]."""

    return parse_unsigned_int32(register_values[register_a], register_values[register_b])


def parse_u32_order_ba(register_values: Mapping[int, float], register_a: int, register_b: int) -> int:
    """Interpret pair as [B=high, A=low]."""

    return parse_unsigned_int32(register_values[register_b], register_values[register_a])


@dataclass(frozen=True, slots=True)
class HaCandidateSnapshot:
    """Decoded values for Wave 9E candidate registers."""

    timestamp_utc: str
    grid_power_535_536_ab_w: int
    grid_power_536_535_ba_w: int
    load_power_547_548_ab_w: int
    load_power_548_547_ba_w: int
    pv_total_553_554_ab_w: int
    pv_total_554_553_ba_w: int
    today_energy_export_1002_kwh: float
    today_energy_import_1003_kwh: float
    today_load_consumption_1004_kwh: float
    today_production_1007_1006_kwh: float
    total_production_1027_1026_kwh: float
    total_export_1019_1018_kwh: float
    total_import_1021_1020_kwh: float


def build_ha_candidate_snapshot(
    register_values: Mapping[int, float],
    timestamp_utc: str | None = None,
) -> HaCandidateSnapshot:
    """Build snapshot with both register orders for critical power pairs."""

    return HaCandidateSnapshot(
        timestamp_utc=timestamp_utc or datetime.now(timezone.utc).isoformat(),
        # Grid Active Power candidate
        grid_power_535_536_ab_w=parse_s32_order_ab(register_values, 535, 536),
        grid_power_536_535_ba_w=parse_s32_order_ba(register_values, 535, 536),
        # Load Power candidate
        load_power_547_548_ab_w=parse_s32_order_ab(register_values, 547, 548),
        load_power_548_547_ba_w=parse_s32_order_ba(register_values, 547, 548),
        # PV Total candidate
        pv_total_553_554_ab_w=parse_u32_order_ab(register_values, 553, 554),
        pv_total_554_553_ba_w=parse_u32_order_ba(register_values, 553, 554),
        # Energy meter block
        today_energy_export_1002_kwh=float(register_values[1002]) * 0.1,
        today_energy_import_1003_kwh=float(register_values[1003]) * 0.1,
        today_load_consumption_1004_kwh=float(register_values[1004]) * 0.1,
        today_production_1007_1006_kwh=float(
            parse_u32_order_ba(register_values, 1007, 1006)
        )
        * 0.1,
        total_production_1027_1026_kwh=float(
            parse_u32_order_ba(register_values, 1027, 1026)
        )
        * 0.1,
        total_export_1019_1018_kwh=float(
            parse_u32_order_ba(register_values, 1019, 1018)
        )
        * 0.1,
        total_import_1021_1020_kwh=float(
            parse_u32_order_ba(register_values, 1021, 1020)
        )
        * 0.1,
    )
