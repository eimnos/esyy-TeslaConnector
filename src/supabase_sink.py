"""Optional Supabase writer for Wave 5 schema tables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import requests


class SupabaseSinkError(Exception):
    """Raised when a Supabase write operation fails."""


@dataclass(frozen=True, slots=True)
class SupabaseSinkConfig:
    """Supabase settings for REST writes."""

    url: str
    service_role_key: str
    timeout_seconds: float = 3.0


class SupabaseSink:
    """Small Supabase REST sink with short timeout.

    Designed to be optional and non-blocking for controller execution.
    """

    TABLE_INVERTER_SAMPLES = "inverter_samples"
    TABLE_TESLA_SAMPLES = "tesla_samples"
    TABLE_CONTROLLER_DECISIONS = "controller_decisions"
    TABLE_CONTROLLER_SETTINGS = "controller_settings"

    def __init__(
        self,
        config: SupabaseSinkConfig,
        session: requests.Session | Any | None = None,
    ) -> None:
        self.config = config
        self.session = session or requests.Session()

    def _headers(self) -> dict[str, str]:
        key = self.config.service_role_key
        return {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }

    def _endpoint(self, table: str) -> str:
        base = self.config.url.rstrip("/")
        return f"{base}/rest/v1/{table}"

    def _insert_row(self, table: str, row: Mapping[str, Any]) -> None:
        try:
            response = self.session.request(
                method="POST",
                url=self._endpoint(table),
                headers=self._headers(),
                json=dict(row),
                timeout=self.config.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise SupabaseSinkError(f"Supabase network error on {table}: {exc}") from exc

        if response.status_code not in {200, 201, 204}:
            error_text = response.text[:240] if hasattr(response, "text") else ""
            raise SupabaseSinkError(
                f"Supabase write failed on {table} with status {response.status_code}: {error_text}"
            )

    def fetch_rows(
        self,
        table: str,
        *,
        select: str = "*",
        order: str = "created_at.desc",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Fetch rows from a Supabase table via REST API."""

        try:
            response = self.session.request(
                method="GET",
                url=self._endpoint(table),
                headers=self._headers(),
                params={
                    "select": select,
                    "order": order,
                    "limit": str(limit),
                },
                timeout=self.config.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise SupabaseSinkError(f"Supabase network error on {table}: {exc}") from exc

        if response.status_code >= 400:
            error_text = response.text[:240] if hasattr(response, "text") else ""
            raise SupabaseSinkError(
                f"Supabase read failed on {table} with status {response.status_code}: {error_text}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise SupabaseSinkError(
                f"Supabase read on {table} returned non-JSON payload"
            ) from exc

        if not isinstance(payload, list):
            raise SupabaseSinkError(
                f"Supabase read on {table} returned unexpected type: {type(payload)}"
            )
        rows: list[dict[str, Any]] = []
        for item in payload:
            if isinstance(item, dict):
                rows.append(item)
        return rows

    def insert_inverter_sample(self, row: Mapping[str, Any]) -> None:
        """Insert one row into `inverter_samples`."""

        self._insert_row(self.TABLE_INVERTER_SAMPLES, row)

    def insert_tesla_sample(self, row: Mapping[str, Any]) -> None:
        """Insert one row into `tesla_samples`."""

        self._insert_row(self.TABLE_TESLA_SAMPLES, row)

    def insert_controller_decision(self, row: Mapping[str, Any]) -> None:
        """Insert one row into `controller_decisions`."""

        self._insert_row(self.TABLE_CONTROLLER_DECISIONS, row)

    def insert_controller_settings(self, row: Mapping[str, Any]) -> None:
        """Insert one row into `controller_settings`."""

        self._insert_row(self.TABLE_CONTROLLER_SETTINGS, row)

    def close(self) -> None:
        close_method = getattr(self.session, "close", None)
        if callable(close_method):
            close_method()
