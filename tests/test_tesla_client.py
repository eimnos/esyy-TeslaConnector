from pathlib import Path

import pytest

from src.tesla_client import TeslaApiConfig, TeslaFleetClient, TeslaUnauthorizedError
from src.tesla_readonly_status import build_status_snapshot


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

    def request(self, method: str, url: str, headers: dict, params: dict | None, timeout: float):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "params": params,
                "timeout": timeout,
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
    )


def test_auth_header_bearer_is_sent(tmp_path: Path) -> None:
    session = FakeSession([FakeResponse(200, {"response": {"id_s": "123", "state": "online"}})])
    client = TeslaFleetClient(
        config=make_config(),
        session=session,
        calls_log_path=tmp_path / "tesla_calls.csv",
    )

    client.get_vehicle()

    assert len(session.calls) == 1
    assert session.calls[0]["headers"]["Authorization"] == "Bearer access-token-123"
    assert session.calls[0]["method"] == "GET"


def test_401_raises_unauthorized(tmp_path: Path) -> None:
    session = FakeSession([FakeResponse(401, {"error": "invalid_token"})])
    client = TeslaFleetClient(
        config=make_config(),
        session=session,
        calls_log_path=tmp_path / "tesla_calls.csv",
    )

    with pytest.raises(TeslaUnauthorizedError):
        client.get_vehicle()


def test_asleep_vehicle_skips_vehicle_data_and_no_wakeup(tmp_path: Path) -> None:
    session = FakeSession([FakeResponse(200, {"response": {"id_s": "123", "state": "asleep"}})])
    client = TeslaFleetClient(
        config=make_config(),
        session=session,
        calls_log_path=tmp_path / "tesla_calls.csv",
    )

    status = client.get_readonly_status()

    assert status["asleep_or_offline"] is True
    assert status["skipped_vehicle_data"] is True
    assert len(session.calls) == 1
    assert "/vehicle_data" not in session.calls[0]["url"]
    assert "wake" not in session.calls[0]["url"].lower()


def test_build_status_snapshot_parses_charge_state() -> None:
    readonly_status = {
        "vehicle": {"state": "online"},
        "vehicle_data": {
            "charge_state": {
                "battery_level": 72,
                "charging_state": "Charging",
                "charge_amps": 10,
                "charge_limit_soc": 80,
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
    assert snapshot["battery_level"] == 72.0
    assert snapshot["charging_state"] == "Charging"
    assert snapshot["charge_amps"] == 10.0
    assert snapshot["charge_limit_soc"] == 80.0
    assert snapshot["odometer_km"] == 45123.4
