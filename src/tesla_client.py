"""Minimal Tesla Fleet API read-only client for Wave 4."""

from __future__ import annotations

import csv
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


class TeslaApiError(Exception):
    """Base Tesla API client error."""


class TeslaUnauthorizedError(TeslaApiError):
    """Raised when Tesla API returns 401 Unauthorized."""


class TeslaApiResponseError(TeslaApiError):
    """Raised when Tesla API returns non-success response."""


@dataclass(frozen=True, slots=True)
class TeslaApiConfig:
    """Configuration needed for read-only Tesla Fleet API access."""

    client_id: str
    client_secret: str
    access_token: str
    refresh_token: str
    vehicle_id: str
    api_base_url: str
    readonly_poll_seconds: int
    allow_wake_up: bool
    commands_enabled: bool
    request_timeout_seconds: float = 15.0


def _parse_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default

    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"{name} must be boolean-like, got: {raw!r}")


def _parse_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        value = default
    else:
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValueError(f"{name} must be an integer, got: {raw!r}") from exc

    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got: {value}")
    return value


def load_tesla_config(env_file: str | None = None) -> TeslaApiConfig:
    """Load Tesla read-only configuration from environment variables."""

    load_dotenv(dotenv_path=env_file, override=False)

    access_token = os.getenv("TESLA_ACCESS_TOKEN", "").strip()
    if not access_token:
        raise ValueError("TESLA_ACCESS_TOKEN is required for read-only status calls")

    api_base_url = os.getenv(
        "TESLA_API_BASE_URL", "https://fleet-api.prd.eu.vn.cloud.tesla.com"
    ).strip()
    if not api_base_url:
        raise ValueError("TESLA_API_BASE_URL cannot be empty")

    config = TeslaApiConfig(
        client_id=os.getenv("TESLA_CLIENT_ID", "").strip(),
        client_secret=os.getenv("TESLA_CLIENT_SECRET", "").strip(),
        access_token=access_token,
        refresh_token=os.getenv("TESLA_REFRESH_TOKEN", "").strip(),
        vehicle_id=os.getenv("TESLA_VEHICLE_ID", "").strip(),
        api_base_url=api_base_url.rstrip("/"),
        readonly_poll_seconds=_parse_int("TESLA_READONLY_POLL_SECONDS", 600, minimum=1),
        allow_wake_up=_parse_bool("TESLA_ALLOW_WAKE_UP", False),
        commands_enabled=_parse_bool("TESLA_COMMANDS_ENABLED", False),
    )
    return config


class TeslaFleetClient:
    """Read-only Tesla Fleet API client.

    Safety guarantees:
    - GET requests only
    - no wake-up endpoint calls
    - no command endpoints
    """

    def __init__(
        self,
        config: TeslaApiConfig,
        session: requests.Session | Any | None = None,
        calls_log_path: str | Path = "data/tesla_api_calls_log.csv",
    ) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.calls_log_path = Path(calls_log_path)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.access_token}",
            "Accept": "application/json",
        }

    def _log_call(
        self,
        method: str,
        path: str,
        status_code: int | None,
        elapsed_ms: int | None,
        ok: bool,
        error: str = "",
    ) -> None:
        self.calls_log_path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not self.calls_log_path.exists()
        with self.calls_log_path.open("a", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            if is_new:
                writer.writerow(
                    [
                        "timestamp_utc",
                        "method",
                        "path",
                        "status_code",
                        "elapsed_ms",
                        "ok",
                        "error",
                    ]
                )
            writer.writerow(
                [
                    datetime.now(timezone.utc).isoformat(),
                    method,
                    path,
                    status_code if status_code is not None else "",
                    elapsed_ms if elapsed_ms is not None else "",
                    str(ok).lower(),
                    error,
                ]
            )

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        if method.upper() != "GET":
            raise TeslaApiError("Read-only Tesla client allows only GET requests")

        url = f"{self.config.api_base_url}{path}"
        started_at = time.perf_counter()
        try:
            response = self.session.request(
                method="GET",
                url=url,
                headers=self._headers(),
                params=params,
                timeout=self.config.request_timeout_seconds,
            )
        except requests.RequestException as exc:
            elapsed = int((time.perf_counter() - started_at) * 1000)
            self._log_call("GET", path, None, elapsed, ok=False, error=str(exc))
            raise TeslaApiError(f"Tesla API request failed: {exc}") from exc

        elapsed = int((time.perf_counter() - started_at) * 1000)
        if response.status_code == 401:
            self._log_call(
                "GET",
                path,
                response.status_code,
                elapsed,
                ok=False,
                error="401 unauthorized",
            )
            raise TeslaUnauthorizedError("Tesla API unauthorized (401). Check access token.")

        if response.status_code >= 400:
            error_text = ""
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    error_text = str(payload.get("error") or payload.get("message") or payload)
                else:
                    error_text = str(payload)
            except ValueError:
                error_text = response.text[:200]

            self._log_call(
                "GET",
                path,
                response.status_code,
                elapsed,
                ok=False,
                error=error_text,
            )
            raise TeslaApiResponseError(
                f"Tesla API error {response.status_code} on {path}: {error_text}"
            )

        self._log_call("GET", path, response.status_code, elapsed, ok=True)
        try:
            payload = response.json()
        except ValueError as exc:
            raise TeslaApiResponseError("Tesla API returned non-JSON response") from exc

        if isinstance(payload, dict) and "response" in payload:
            return payload["response"]
        return payload

    def get_vehicle(self, vehicle_id: str | None = None) -> dict[str, Any]:
        selected_vehicle_id = (vehicle_id or self.config.vehicle_id).strip()
        if not selected_vehicle_id:
            raise ValueError("TESLA_VEHICLE_ID is required for vehicle status calls")
        data = self._request("GET", f"/api/1/vehicles/{selected_vehicle_id}")
        if not isinstance(data, dict):
            raise TeslaApiResponseError("Unexpected vehicle response format")
        return data

    def get_vehicle_data(self, vehicle_id: str | None = None) -> dict[str, Any]:
        selected_vehicle_id = (vehicle_id or self.config.vehicle_id).strip()
        if not selected_vehicle_id:
            raise ValueError("TESLA_VEHICLE_ID is required for vehicle status calls")
        data = self._request("GET", f"/api/1/vehicles/{selected_vehicle_id}/vehicle_data")
        if not isinstance(data, dict):
            raise TeslaApiResponseError("Unexpected vehicle_data response format")
        return data

    def get_readonly_status(self, vehicle_id: str | None = None) -> dict[str, Any]:
        """Read vehicle status without wake-up behavior.

        If the car is not online, the method intentionally skips `vehicle_data`.
        """

        vehicle = self.get_vehicle(vehicle_id)
        vehicle_state = str(vehicle.get("state", "unknown")).lower()

        if vehicle_state != "online":
            return {
                "vehicle": vehicle,
                "vehicle_data": None,
                "asleep_or_offline": True,
                "skipped_vehicle_data": True,
            }

        vehicle_data = self.get_vehicle_data(vehicle_id)
        return {
            "vehicle": vehicle,
            "vehicle_data": vehicle_data,
            "asleep_or_offline": False,
            "skipped_vehicle_data": False,
        }

    def close(self) -> None:
        close_method = getattr(self.session, "close", None)
        if callable(close_method):
            close_method()
