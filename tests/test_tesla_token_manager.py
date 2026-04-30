import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.tesla_token_manager import (
    TeslaReauthorizationRequiredError,
    TeslaTokenManager,
    TeslaTokenRecord,
)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def request(
        self,
        method: str,
        url: str,
        headers: dict,
        data: dict | None = None,
        timeout: float | None = None,
        verify: bool | None = None,
        **_kwargs: dict,
    ) -> FakeResponse:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "data": data,
                "timeout": timeout,
                "verify": verify,
            }
        )
        if not self.responses:
            raise RuntimeError("No fake response queued")
        return self.responses.pop(0)

    def close(self) -> None:
        return None


def make_manager(tmp_path: Path, session: FakeSession) -> TeslaTokenManager:
    return TeslaTokenManager(
        client_id="client-id",
        client_secret="client-secret",
        access_token="access-token-old",
        refresh_token="refresh-token-old",
        auth_base_url="https://auth.tesla.com/oauth2/v3",
        store_path=tmp_path / "tesla_token_store.json",
        request_timeout_seconds=5.0,
        request_verify_tls=True,
        session=session,
    )


def test_refresh_saves_new_access_and_refresh_token(tmp_path: Path) -> None:
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "access_token": "access-token-new",
                    "refresh_token": "refresh-token-new",
                    "expires_in": 3600,
                },
            )
        ]
    )
    manager = make_manager(tmp_path, session)

    record = manager.refresh_now()
    stored = json.loads((tmp_path / "tesla_token_store.json").read_text(encoding="utf-8"))

    assert record.access_token == "access-token-new"
    assert record.refresh_token == "refresh-token-new"
    assert stored["access_token"] == "access-token-new"
    assert stored["refresh_token"] == "refresh-token-new"
    assert "expires_at" in stored and stored["expires_at"]
    assert session.calls[0]["method"] == "POST"
    assert session.calls[0]["url"] == "https://auth.tesla.com/oauth2/v3/token"


def test_refresh_missing_new_refresh_token_requires_reauthorization(tmp_path: Path) -> None:
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "access_token": "access-token-new",
                    # missing refresh_token should force re-auth because Tesla refresh token is single-use.
                },
            )
        ]
    )
    manager = make_manager(tmp_path, session)

    with pytest.raises(TeslaReauthorizationRequiredError, match="Tesla re-authorization required"):
        manager.refresh_now()


def test_ensure_fresh_access_token_refreshes_near_expiry(tmp_path: Path) -> None:
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "access_token": "access-token-new",
                    "refresh_token": "refresh-token-new",
                    "expires_in": 3600,
                },
            )
        ]
    )
    manager = make_manager(tmp_path, session)
    expired_time = datetime.now(timezone.utc) - timedelta(seconds=5)
    manager.save_record(
        TeslaTokenRecord(
            access_token="expired-access",
            refresh_token="refresh-token-old",
            expires_at=expired_time.isoformat(),
            updated_at=expired_time.isoformat(),
        )
    )

    manager.ensure_fresh_access_token(leeway_seconds=120)

    assert len(session.calls) == 1


def test_status_does_not_expose_token_values(tmp_path: Path) -> None:
    session = FakeSession([])
    manager = make_manager(tmp_path, session)

    status = manager.status()

    assert status["access_token_present"] is True
    assert status["refresh_token_present"] is True
    assert "access-token-old" not in str(status)
    assert "refresh-token-old" not in str(status)
