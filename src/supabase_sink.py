"""Optional Supabase writer for Wave 5 preparation."""

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
    table: str = "controller_dry_run_samples"
    timeout_seconds: float = 3.0


class SupabaseSink:
    """Small Supabase REST sink with short timeout.

    Designed to be optional and non-blocking for controller execution.
    """

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

    def _endpoint(self) -> str:
        base = self.config.url.rstrip("/")
        return f"{base}/rest/v1/{self.config.table}"

    def insert_row(self, row: Mapping[str, Any]) -> None:
        """Insert one row into Supabase table via REST API."""

        try:
            response = self.session.request(
                method="POST",
                url=self._endpoint(),
                headers=self._headers(),
                json=dict(row),
                timeout=self.config.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise SupabaseSinkError(f"Supabase network error: {exc}") from exc

        if response.status_code not in {200, 201, 204}:
            error_text = response.text[:240] if hasattr(response, "text") else ""
            raise SupabaseSinkError(
                f"Supabase write failed with status {response.status_code}: {error_text}"
            )

    def close(self) -> None:
        close_method = getattr(self.session, "close", None)
        if callable(close_method):
            close_method()
