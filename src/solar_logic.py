"""Pure functions for PV surplus and charging decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class ControlSettings:
    """Runtime settings required by the decision function."""

    grid_export_start_w: float
    grid_export_stop_w: float
    min_amps: int
    max_amps: int
    grid_voltage: float


def calculate_surplus_w(grid_power_w: float) -> float:
    """Convert grid power to PV surplus in watts.

    Convention:
    - negative `grid_power_w` means export to grid
    - positive `grid_power_w` means import from grid
    """

    return max(-grid_power_w, 0.0)


def calculate_target_amps(
    export_w: float, min_amps: int, max_amps: int, grid_voltage: float
) -> int:
    """Compute target charging current from available export power."""

    if export_w <= 0 or grid_voltage <= 0:
        return 0

    raw_target = int(export_w / grid_voltage)
    if raw_target < min_amps:
        return 0
    if raw_target > max_amps:
        return max_amps
    return raw_target


def should_update_amps(current_amps: int, target_amps: int, min_delta: int = 2) -> bool:
    """Return True only when amps change is meaningful."""

    return abs(target_amps - current_amps) >= min_delta


def _setting_value(settings: ControlSettings | Mapping[str, float], key: str) -> float:
    if isinstance(settings, Mapping):
        return float(settings[key])
    return float(getattr(settings, key))


def decide_charge_action(
    export_w: float, current_amps: int, settings: ControlSettings | Mapping[str, float]
) -> str:
    """Return one action: STOP_CHARGE, START_CHARGE, SET_AMPS, NO_ACTION."""

    start_threshold = _setting_value(settings, "grid_export_start_w")
    stop_threshold = _setting_value(settings, "grid_export_stop_w")
    min_amps = int(_setting_value(settings, "min_amps"))
    max_amps = int(_setting_value(settings, "max_amps"))
    grid_voltage = _setting_value(settings, "grid_voltage")

    target_amps = calculate_target_amps(export_w, min_amps, max_amps, grid_voltage)

    if current_amps <= 0:
        if export_w >= start_threshold and target_amps > 0:
            return "START_CHARGE"
        return "NO_ACTION"

    if export_w <= stop_threshold:
        return "STOP_CHARGE"

    if target_amps <= 0:
        return "STOP_CHARGE"

    if should_update_amps(current_amps, target_amps):
        return "SET_AMPS"

    return "NO_ACTION"
