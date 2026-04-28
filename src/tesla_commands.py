"""Protected Tesla command wrappers for Wave 9A readiness.

Safety guardrails:
- commands are blocked unless TESLA_COMMANDS_ENABLED=true;
- each command requires explicit per-call approval flag;
- commands are blocked when grid power status is not confirmed;
- dry-run mode is supported and enabled by default in callers;
- every attempt is logged.
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

try:
    from src.tesla_client import TeslaApiConfig, load_tesla_config
except ModuleNotFoundError:  # Allows `python src/tesla_commands.py`
    from tesla_client import TeslaApiConfig, load_tesla_config  # type: ignore[no-redef]

LOGGER = logging.getLogger(__name__)

_GRID_CONFIRMED = "confirmed"


class TeslaCommandError(Exception):
    """Base error for command wrappers."""


class TeslaCommandBlockedError(TeslaCommandError):
    """Raised when a command is blocked by safety guardrails."""


class TeslaCommandApiError(TeslaCommandError):
    """Raised when the command API call fails."""


@dataclass(frozen=True, slots=True)
class TeslaCommandResult:
    """Result for a command attempt."""

    command: str
    vehicle_id: str
    endpoint: str
    attempted_at_utc: str
    dry_run: bool
    executed: bool
    blocked: bool
    reason: str
    status_code: int | None = None
    response_payload: dict[str, Any] | None = None


class TeslaCommandClient:
    """Safety-first Tesla vehicle command client.

    This client is not wired into automatic controller loops.
    It is meant for explicit/manual command execution only.
    """

    def __init__(
        self,
        config: TeslaApiConfig,
        session: requests.Session | Any | None = None,
        calls_log_path: str | Path = "data/tesla_command_calls_log.csv",
    ) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.calls_log_path = Path(calls_log_path)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _log_attempt(
        self,
        *,
        command: str,
        vehicle_id: str,
        endpoint: str,
        allow_command: bool,
        dry_run: bool,
        grid_status: str,
        blocked: bool,
        executed: bool,
        reason: str,
        payload: dict[str, Any] | None,
        status_code: int | None,
        error: str,
    ) -> None:
        self.calls_log_path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not self.calls_log_path.exists()

        try:
            with self.calls_log_path.open("a", newline="", encoding="utf-8") as csv_file:
                writer = csv.writer(csv_file)
                if is_new:
                    writer.writerow(
                        [
                            "timestamp_utc",
                            "command",
                            "vehicle_id",
                            "endpoint",
                            "allow_command",
                            "commands_enabled",
                            "dry_run",
                            "grid_status",
                            "blocked",
                            "executed",
                            "status_code",
                            "reason",
                            "payload_json",
                            "error",
                        ]
                    )
                writer.writerow(
                    [
                        datetime.now(timezone.utc).isoformat(),
                        command,
                        vehicle_id,
                        endpoint,
                        str(allow_command).lower(),
                        str(self.config.commands_enabled).lower(),
                        str(dry_run).lower(),
                        grid_status,
                        str(blocked).lower(),
                        str(executed).lower(),
                        status_code if status_code is not None else "",
                        reason,
                        json.dumps(payload or {}, ensure_ascii=False),
                        error,
                    ]
                )
        except OSError as exc:
            LOGGER.warning("Unable to write Tesla command log: %s", exc)

    def _resolve_vehicle_id(self, vehicle_id: str | None) -> str:
        selected_vehicle_id = (vehicle_id or self.config.vehicle_id).strip()
        if not selected_vehicle_id:
            raise ValueError("vehicle_id is required for Tesla command calls")
        return selected_vehicle_id

    @staticmethod
    def _normalize_grid_status(grid_status: str | None) -> str:
        value = (grid_status or "unknown").strip().lower()
        if not value:
            return "unknown"
        return value

    def _blocked_result(
        self,
        *,
        command: str,
        vehicle_id: str,
        endpoint: str,
        allow_command: bool,
        dry_run: bool,
        grid_status: str,
        reason: str,
        payload: dict[str, Any] | None,
    ) -> TeslaCommandResult:
        self._log_attempt(
            command=command,
            vehicle_id=vehicle_id,
            endpoint=endpoint,
            allow_command=allow_command,
            dry_run=dry_run,
            grid_status=grid_status,
            blocked=True,
            executed=False,
            reason=reason,
            payload=payload,
            status_code=None,
            error=reason,
        )
        raise TeslaCommandBlockedError(reason)

    def _request_command(
        self,
        *,
        command: str,
        endpoint: str,
        payload: dict[str, Any],
        allow_command: bool,
        dry_run: bool,
        grid_status: str,
        vehicle_id: str,
    ) -> TeslaCommandResult:
        if not self.config.commands_enabled:
            return self._blocked_result(
                command=command,
                vehicle_id=vehicle_id,
                endpoint=endpoint,
                allow_command=allow_command,
                dry_run=dry_run,
                grid_status=grid_status,
                reason="TESLA_COMMANDS_ENABLED=false",
                payload=payload,
            )

        if not allow_command:
            return self._blocked_result(
                command=command,
                vehicle_id=vehicle_id,
                endpoint=endpoint,
                allow_command=allow_command,
                dry_run=dry_run,
                grid_status=grid_status,
                reason="allow_command flag not set",
                payload=payload,
            )

        if grid_status != _GRID_CONFIRMED:
            return self._blocked_result(
                command=command,
                vehicle_id=vehicle_id,
                endpoint=endpoint,
                allow_command=allow_command,
                dry_run=dry_run,
                grid_status=grid_status,
                reason=f"grid power status is {grid_status!r} (required: confirmed)",
                payload=payload,
            )

        if dry_run:
            reason = "dry-run: command not sent"
            self._log_attempt(
                command=command,
                vehicle_id=vehicle_id,
                endpoint=endpoint,
                allow_command=allow_command,
                dry_run=True,
                grid_status=grid_status,
                blocked=False,
                executed=False,
                reason=reason,
                payload=payload,
                status_code=None,
                error="",
            )
            return TeslaCommandResult(
                command=command,
                vehicle_id=vehicle_id,
                endpoint=endpoint,
                attempted_at_utc=datetime.now(timezone.utc).isoformat(),
                dry_run=True,
                executed=False,
                blocked=False,
                reason=reason,
                status_code=None,
                response_payload=None,
            )

        url = f"{self.config.api_base_url}{endpoint}"
        try:
            response = self.session.request(
                method="POST",
                url=url,
                headers=self._headers(),
                json=payload,
                timeout=self.config.request_timeout_seconds,
            )
        except requests.RequestException as exc:
            error_text = f"Tesla command request failed: {exc}"
            self._log_attempt(
                command=command,
                vehicle_id=vehicle_id,
                endpoint=endpoint,
                allow_command=allow_command,
                dry_run=False,
                grid_status=grid_status,
                blocked=False,
                executed=False,
                reason="network_error",
                payload=payload,
                status_code=None,
                error=error_text,
            )
            raise TeslaCommandApiError(error_text) from exc

        response_payload: dict[str, Any] | None = None
        if response.status_code >= 400:
            error_text = ""
            try:
                json_payload = response.json()
                if isinstance(json_payload, dict):
                    error_text = str(json_payload.get("error") or json_payload.get("message") or json_payload)
                else:
                    error_text = str(json_payload)
            except ValueError:
                error_text = getattr(response, "text", "")[:240]

            self._log_attempt(
                command=command,
                vehicle_id=vehicle_id,
                endpoint=endpoint,
                allow_command=allow_command,
                dry_run=False,
                grid_status=grid_status,
                blocked=False,
                executed=False,
                reason="api_error",
                payload=payload,
                status_code=response.status_code,
                error=error_text,
            )
            raise TeslaCommandApiError(
                f"Tesla command API error {response.status_code} on {command}: {error_text}"
            )

        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                raw_payload = parsed.get("response", parsed)
                if isinstance(raw_payload, dict):
                    response_payload = raw_payload
                else:
                    response_payload = {"value": raw_payload}
            else:
                response_payload = {"value": parsed}
        except ValueError:
            response_payload = None

        self._log_attempt(
            command=command,
            vehicle_id=vehicle_id,
            endpoint=endpoint,
            allow_command=allow_command,
            dry_run=False,
            grid_status=grid_status,
            blocked=False,
            executed=True,
            reason="executed",
            payload=payload,
            status_code=response.status_code,
            error="",
        )
        return TeslaCommandResult(
            command=command,
            vehicle_id=vehicle_id,
            endpoint=endpoint,
            attempted_at_utc=datetime.now(timezone.utc).isoformat(),
            dry_run=False,
            executed=True,
            blocked=False,
            reason="executed",
            status_code=response.status_code,
            response_payload=response_payload,
        )

    def set_charge_amps(
        self,
        amps: int,
        *,
        allow_command: bool,
        dry_run: bool = True,
        grid_status: str = "unknown",
        vehicle_id: str | None = None,
    ) -> TeslaCommandResult:
        if amps <= 0:
            raise ValueError(f"amps must be > 0, got: {amps}")

        normalized_grid_status = self._normalize_grid_status(grid_status)
        try:
            selected_vehicle_id = self._resolve_vehicle_id(vehicle_id)
        except ValueError as exc:
            self._log_attempt(
                command="set_charge_amps",
                vehicle_id=(vehicle_id or "").strip(),
                endpoint="N/A",
                allow_command=allow_command,
                dry_run=dry_run,
                grid_status=normalized_grid_status,
                blocked=True,
                executed=False,
                reason="missing_vehicle_id",
                payload={"charging_amps": int(amps)},
                status_code=None,
                error=str(exc),
            )
            raise

        endpoint = f"/api/1/vehicles/{selected_vehicle_id}/command/set_charging_amps"
        payload = {"charging_amps": int(amps)}
        return self._request_command(
            command="set_charge_amps",
            endpoint=endpoint,
            payload=payload,
            allow_command=allow_command,
            dry_run=dry_run,
            grid_status=normalized_grid_status,
            vehicle_id=selected_vehicle_id,
        )

    def start_charge(
        self,
        *,
        allow_command: bool,
        dry_run: bool = True,
        grid_status: str = "unknown",
        vehicle_id: str | None = None,
    ) -> TeslaCommandResult:
        normalized_grid_status = self._normalize_grid_status(grid_status)
        try:
            selected_vehicle_id = self._resolve_vehicle_id(vehicle_id)
        except ValueError as exc:
            self._log_attempt(
                command="start_charge",
                vehicle_id=(vehicle_id or "").strip(),
                endpoint="N/A",
                allow_command=allow_command,
                dry_run=dry_run,
                grid_status=normalized_grid_status,
                blocked=True,
                executed=False,
                reason="missing_vehicle_id",
                payload={},
                status_code=None,
                error=str(exc),
            )
            raise

        endpoint = f"/api/1/vehicles/{selected_vehicle_id}/command/charge_start"
        return self._request_command(
            command="start_charge",
            endpoint=endpoint,
            payload={},
            allow_command=allow_command,
            dry_run=dry_run,
            grid_status=normalized_grid_status,
            vehicle_id=selected_vehicle_id,
        )

    def stop_charge(
        self,
        *,
        allow_command: bool,
        dry_run: bool = True,
        grid_status: str = "unknown",
        vehicle_id: str | None = None,
    ) -> TeslaCommandResult:
        normalized_grid_status = self._normalize_grid_status(grid_status)
        try:
            selected_vehicle_id = self._resolve_vehicle_id(vehicle_id)
        except ValueError as exc:
            self._log_attempt(
                command="stop_charge",
                vehicle_id=(vehicle_id or "").strip(),
                endpoint="N/A",
                allow_command=allow_command,
                dry_run=dry_run,
                grid_status=normalized_grid_status,
                blocked=True,
                executed=False,
                reason="missing_vehicle_id",
                payload={},
                status_code=None,
                error=str(exc),
            )
            raise

        endpoint = f"/api/1/vehicles/{selected_vehicle_id}/command/charge_stop"
        return self._request_command(
            command="stop_charge",
            endpoint=endpoint,
            payload={},
            allow_command=allow_command,
            dry_run=dry_run,
            grid_status=normalized_grid_status,
            vehicle_id=selected_vehicle_id,
        )

    def close(self) -> None:
        close_method = getattr(self.session, "close", None)
        if callable(close_method):
            close_method()


def create_tesla_command_client(env_file: str | None = None) -> TeslaCommandClient:
    """Create command client from environment configuration."""

    config = load_tesla_config(env_file=env_file)
    return TeslaCommandClient(config=config)


def set_charge_amps(
    client: TeslaCommandClient,
    amps: int,
    *,
    allow_command: bool,
    dry_run: bool = True,
    grid_status: str = "unknown",
    vehicle_id: str | None = None,
) -> TeslaCommandResult:
    """Protected wrapper for `set_charging_amps` command."""

    return client.set_charge_amps(
        amps,
        allow_command=allow_command,
        dry_run=dry_run,
        grid_status=grid_status,
        vehicle_id=vehicle_id,
    )


def start_charge(
    client: TeslaCommandClient,
    *,
    allow_command: bool,
    dry_run: bool = True,
    grid_status: str = "unknown",
    vehicle_id: str | None = None,
) -> TeslaCommandResult:
    """Protected wrapper for `charge_start` command."""

    return client.start_charge(
        allow_command=allow_command,
        dry_run=dry_run,
        grid_status=grid_status,
        vehicle_id=vehicle_id,
    )


def stop_charge(
    client: TeslaCommandClient,
    *,
    allow_command: bool,
    dry_run: bool = True,
    grid_status: str = "unknown",
    vehicle_id: str | None = None,
) -> TeslaCommandResult:
    """Protected wrapper for `charge_stop` command."""

    return client.stop_charge(
        allow_command=allow_command,
        dry_run=dry_run,
        grid_status=grid_status,
        vehicle_id=vehicle_id,
    )
