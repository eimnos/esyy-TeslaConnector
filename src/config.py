"""Configuration loader for Esyy Tesla Connector."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Application settings loaded from environment variables."""

    collector_ip: str
    collector_port: int
    collector_serial: int
    poll_seconds: int
    dry_run: bool
    grid_voltage: float
    tesla_min_amps: int
    tesla_max_amps: int
    grid_export_start_w: float
    grid_export_stop_w: float
    grid_automation_enabled: bool
    afore_pv_power_register: int
    afore_grid_power_register_high: int
    afore_grid_power_register_low: int
    afore_grid_power_scale: float
    afore_pv_power_scale: float
    afore_grid_sign_mode: str
    supabase_enabled: bool
    supabase_url: str
    supabase_service_role_key: str


def _parse_int(name: str, default: int, minimum: int | None = None) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        value = default
    else:
        try:
            value = int(raw_value)
        except ValueError as exc:
            raise ValueError(f"{name} must be an integer, got: {raw_value!r}") from exc

    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got: {value}")
    return value


def _parse_float(name: str, default: float, minimum: float | None = None) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        value = default
    else:
        try:
            value = float(raw_value)
        except ValueError as exc:
            raise ValueError(f"{name} must be a number, got: {raw_value!r}") from exc

    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got: {value}")
    return value


def _parse_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default

    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value, got: {raw_value!r}")


def _parse_choice(name: str, default: str, allowed: set[str]) -> str:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        value = default
    else:
        value = raw_value.strip().lower()

    if value not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise ValueError(f"{name} must be one of: {allowed_text}. Got: {value!r}")
    return value


def load_config(env_file: str | None = None) -> AppConfig:
    """Load and validate configuration from `.env` + environment variables."""

    load_dotenv(dotenv_path=env_file, override=False)

    collector_ip = os.getenv("COLLECTOR_IP", "192.168.1.20").strip()
    if not collector_ip:
        raise ValueError("COLLECTOR_IP cannot be empty")

    config = AppConfig(
        collector_ip=collector_ip,
        collector_port=_parse_int("COLLECTOR_PORT", 8899, minimum=1),
        collector_serial=_parse_int("COLLECTOR_SERIAL", 0, minimum=1),
        poll_seconds=_parse_int("POLL_SECONDS", 60, minimum=1),
        dry_run=_parse_bool("DRY_RUN", True),
        grid_voltage=_parse_float("GRID_VOLTAGE", 230.0, minimum=1.0),
        tesla_min_amps=_parse_int("TESLA_MIN_AMPS", 6, minimum=1),
        tesla_max_amps=_parse_int("TESLA_MAX_AMPS", 16, minimum=1),
        grid_export_start_w=_parse_float("GRID_EXPORT_START_W", 1600.0, minimum=0.0),
        grid_export_stop_w=_parse_float("GRID_EXPORT_STOP_W", 900.0, minimum=0.0),
        grid_automation_enabled=_parse_bool("GRID_AUTOMATION_ENABLED", False),
        afore_pv_power_register=_parse_int("AFORE_PV_POWER_REGISTER", 560, minimum=0),
        afore_grid_power_register_high=_parse_int(
            "AFORE_GRID_POWER_REGISTER_HIGH", 535, minimum=0
        ),
        afore_grid_power_register_low=_parse_int(
            "AFORE_GRID_POWER_REGISTER_LOW", 536, minimum=0
        ),
        afore_grid_power_scale=_parse_float("AFORE_GRID_POWER_SCALE", 1.0, minimum=0.000001),
        afore_pv_power_scale=_parse_float("AFORE_PV_POWER_SCALE", 1.0, minimum=0.000001),
        afore_grid_sign_mode=_parse_choice(
            "AFORE_GRID_SIGN_MODE",
            "import_positive",
            {"unknown", "import_positive", "export_positive"},
        ),
        supabase_enabled=_parse_bool("SUPABASE_ENABLED", False),
        supabase_url=os.getenv("SUPABASE_URL", "").strip(),
        supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
    )

    if config.collector_port > 65535:
        raise ValueError(f"COLLECTOR_PORT must be <= 65535, got: {config.collector_port}")

    if config.tesla_max_amps < config.tesla_min_amps:
        raise ValueError(
            "TESLA_MAX_AMPS must be greater than or equal to TESLA_MIN_AMPS"
        )

    if config.grid_export_start_w < config.grid_export_stop_w:
        raise ValueError(
            "GRID_EXPORT_START_W should be >= GRID_EXPORT_STOP_W to preserve hysteresis"
        )

    if config.afore_grid_power_register_high == config.afore_grid_power_register_low:
        raise ValueError(
            "AFORE_GRID_POWER_REGISTER_HIGH and AFORE_GRID_POWER_REGISTER_LOW must be different"
        )

    return config
