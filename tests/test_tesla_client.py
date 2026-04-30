from pathlib import Path

import pytest

from src.tesla_client import (
    TeslaApiConfig,
    TeslaFleetClient,
    TeslaReauthorizationError,
    TeslaUnauthorizedError,
)
from src.tesla_token_manager import TeslaReauthorizationRequiredError
from src.tesla_readonly_status import build_status_snapshot, build_tesla_sample_row


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
        params: dict | None = None,
        timeout: float | None = None,
        verify: bool | None = None,
        data: dict | None = None,
        **_kwargs: dict,
    ):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "params": params,
                "timeout": timeout,
                "verify": verify,
                "data": data,
            }
        )
        if not self.responses:
            raise RuntimeError("No fake response queued")
        return self.responses.pop(0)

    def close(self) -> None:
        return None


def make_config() -> TeslaApiConfig:
    return TeslaApiConfig(
        client_id="client",
        client_secret="secret",
        access_token="access-token-123",
        refresh_token="refresh-token-123",
        vehicle_id="123456",
        api_base_url="https://fleet-api.prd.eu.vn.cloud.tesla.com",
        readonly_poll_seconds=600,
        allow_wake_up=False,
        commands_enabled=False,
        request_timeout_seconds=10.0,
        token_store_path="data/test_tesla_token_store.json",
    )


class FakeTokenManager:
    def __init__(self, *, access_token: str = "access-token-123") -> None:
        self.access_token = access_token
        self.refresh_calls = 0
        self.ensure_calls = 0

    def get_access_token(self) -> str:
        return self.access_token

    def ensure_fresh_access_token(self, *, leeway_seconds: int = 120) -> None:
        self.ensure_calls += 1
        return None

    def refresh_now(self):  # noqa: ANN201 - test double
        self.refresh_calls += 1
        return None

    def close(self) -> None:
        return None


class FakeFailingTokenManager(FakeTokenManager):
    def refresh_now(self):  # noqa: ANN201 - test double
        self.refresh_calls += 1
        raise TeslaReauthorizationRequiredError("Tesla re-authorization required")


def test_auth_header_bearer_is_sent(tmp_path: Path) -> None:
    session = FakeSession([FakeResponse(200, {"response": {"id_s": "123", "state": "online"}})])
    token_manager = FakeTokenManager(access_token="access-token-123")
    client = TeslaFleetClient(
        config=make_config(),
        session=session,
        calls_log_path=tmp_path / "tesla_calls.csv",
        token_manager=token_manager,
    )

    client.get_vehicle()

    assert len(session.calls) == 1
    assert session.calls[0]["headers"]["Authorization"] == "Bearer access-token-123"
    assert session.calls[0]["method"] == "GET"


def test_401_raises_unauthorized(tmp_path: Path) -> None:
    session = FakeSession([FakeResponse(401, {"error": "invalid_token"})])
    token_manager = FakeFailingTokenManager()
    client = TeslaFleetClient(
        config=make_config(),
        session=session,
        calls_log_path=tmp_path / "tesla_calls.csv",
        token_manager=token_manager,
    )

    with pytest.raises(TeslaUnauthorizedError):
        client.get_vehicle()


def test_asleep_vehicle_skips_vehicle_data_and_no_wakeup(tmp_path: Path) -> None:
    session = FakeSession([FakeResponse(200, {"response": {"id_s": "123", "state": "asleep"}})])
    token_manager = FakeTokenManager()
    client = TeslaFleetClient(
        config=make_config(),
        session=session,
        calls_log_path=tmp_path / "tesla_calls.csv",
        token_manager=token_manager,
    )

    status = client.get_readonly_status()

    assert status["asleep_or_offline"] is True
    assert status["skipped_vehicle_data"] is True
    assert len(session.calls) == 1
    assert "/vehicle_data" not in session.calls[0]["url"]
    assert "wake" not in session.calls[0]["url"].lower()


def test_401_triggers_single_refresh_and_retry(tmp_path: Path) -> None:
    session = FakeSession(
        [
            FakeResponse(401, {"error": "invalid_token"}),
            FakeResponse(200, {"response": {"id_s": "123", "state": "online"}}),
        ]
    )
    token_manager = FakeTokenManager()
    client = TeslaFleetClient(
        config=make_config(),
        session=session,
        calls_log_path=tmp_path / "tesla_calls.csv",
        token_manager=token_manager,
    )

    vehicle = client.get_vehicle()

    assert vehicle["state"] == "online"
    assert token_manager.refresh_calls == 1
    assert len(session.calls) == 2


def test_401_after_refresh_raises_reauthorization(tmp_path: Path) -> None:
    session = FakeSession(
        [
            FakeResponse(401, {"error": "invalid_token"}),
            FakeResponse(401, {"error": "invalid_token"}),
        ]
    )
    token_manager = FakeTokenManager()
    client = TeslaFleetClient(
        config=make_config(),
        session=session,
        calls_log_path=tmp_path / "tesla_calls.csv",
        token_manager=token_manager,
    )

    with pytest.raises(TeslaReauthorizationError, match="Tesla re-authorization required"):
        client.get_vehicle()
    assert token_manager.refresh_calls == 1


def test_build_status_snapshot_parses_charge_state() -> None:
    readonly_status = {
        "vehicle": {"state": "online", "id_s": "929871615538817"},
        "vehicle_data": {
            "charge_state": {
                "battery_level": 72,
                "charging_state": "Charging",
                "charge_amps": 10,
                "charge_current_request": 8,
                "charge_current_request_max": 16,
                "charge_limit_soc": 80,
                "charge_energy_added": 3.5,
            },
            "vehicle_state": {
                "odometer": 45123.4,
            },
        },
        "asleep_or_offline": False,
        "skipped_vehicle_data": False,
    }

    snapshot = build_status_snapshot(readonly_status)

    assert snapshot["vehicle_state"] == "online"
    assert snapshot["vehicle_id"] == "929871615538817"
    assert snapshot["battery_level"] == 72.0
    assert snapshot["charging_state"] == "Charging"
    assert snapshot["charge_amps"] == 10.0
    assert snapshot["charge_current_request"] == 8.0
    assert snapshot["charge_current_request_max"] == 16.0
    assert snapshot["charge_limit_soc"] == 80.0
    assert snapshot["odometer_km"] == 45123.4
    assert snapshot["energy_added_kwh"] == 3.5


def test_build_tesla_sample_row_maps_required_columns() -> None:
    snapshot = {
        "sample_timestamp": "2026-04-29T00:00:00+00:00",
        "vehicle_id": "929871615538817",
        "vehicle_state": "online",
        "battery_level": 70.0,
        "charging_state": "Charging",
        "charge_amps": 5.0,
        "charge_current_request": 8.0,
        "charge_current_request_max": 16.0,
        "charge_limit_soc": 80.0,
        "odometer_km": 35180.68,
        "energy_added_kwh": 2.2,
        "asleep_or_offline": False,
        "skipped_vehicle_data": False,
    }

    row = build_tesla_sample_row(snapshot, source="tesla_sync_readonly")

    assert row["sample_timestamp"] == "2026-04-29T00:00:00+00:00"
    assert row["vehicle_id"] == "929871615538817"
    assert row["charge_current_request"] == 8.0
    assert row["charge_current_request_max"] == 16.0
    assert row["energy_added_kwh"] == 2.2
    assert row["source"] == "tesla_sync_readonly"


def test_call_log_does_not_include_bearer_token(tmp_path: Path) -> None:
    token_value = "access-token-123"
    session = FakeSession([FakeResponse(200, {"response": {"id_s": "123", "state": "online"}})])
    token_manager = FakeTokenManager(access_token=token_value)
    log_path = tmp_path / "tesla_calls.csv"
    client = TeslaFleetClient(
        config=make_config(),
        session=session,
        calls_log_path=log_path,
        token_manager=token_manager,
    )

    client.get_vehicle()
    log_content = log_path.read_text(encoding="utf-8")

    assert token_value not in log_content
