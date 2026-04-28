from pathlib import Path

import pytest

from src.tesla_client import TeslaApiConfig
from src.tesla_commands import TeslaCommandBlockedError, TeslaCommandClient, set_charge_amps, start_charge


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
        json: dict,
        timeout: float,
    ) -> FakeResponse:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        if not self.responses:
            raise RuntimeError("No fake response queued")
        return self.responses.pop(0)

    def close(self) -> None:
        return None


def make_config(*, commands_enabled: bool, vehicle_id: str = "123456") -> TeslaApiConfig:
    return TeslaApiConfig(
        client_id="client",
        client_secret="secret",
        access_token="access-token-123",
        refresh_token="refresh-token-123",
        vehicle_id=vehicle_id,
        api_base_url="https://fleet-api.prd.eu.vn.cloud.tesla.com",
        readonly_poll_seconds=600,
        allow_wake_up=False,
        commands_enabled=commands_enabled,
        request_timeout_seconds=10.0,
    )


def test_commands_blocked_when_disabled(tmp_path: Path) -> None:
    session = FakeSession([])
    client = TeslaCommandClient(
        config=make_config(commands_enabled=False),
        session=session,
        calls_log_path=tmp_path / "tesla_commands.csv",
    )

    with pytest.raises(TeslaCommandBlockedError):
        start_charge(
            client,
            allow_command=True,
            dry_run=False,
            grid_status="confirmed",
        )

    assert len(session.calls) == 0


def test_dry_run_does_not_call_api(tmp_path: Path) -> None:
    session = FakeSession([])
    client = TeslaCommandClient(
        config=make_config(commands_enabled=True),
        session=session,
        calls_log_path=tmp_path / "tesla_commands.csv",
    )

    result = set_charge_amps(
        client,
        9,
        allow_command=True,
        dry_run=True,
        grid_status="confirmed",
    )

    assert result.executed is False
    assert result.dry_run is True
    assert len(session.calls) == 0


def test_error_when_vehicle_id_missing(tmp_path: Path) -> None:
    client = TeslaCommandClient(
        config=make_config(commands_enabled=True, vehicle_id=""),
        session=FakeSession([]),
        calls_log_path=tmp_path / "tesla_commands.csv",
    )

    with pytest.raises(ValueError, match="vehicle_id is required"):
        set_charge_amps(
            client,
            8,
            allow_command=True,
            dry_run=True,
            grid_status="confirmed",
        )


def test_set_charge_amps_payload_is_correct(tmp_path: Path) -> None:
    session = FakeSession([FakeResponse(200, {"response": {"result": True, "reason": ""}})])
    client = TeslaCommandClient(
        config=make_config(commands_enabled=True),
        session=session,
        calls_log_path=tmp_path / "tesla_commands.csv",
    )

    result = set_charge_amps(
        client,
        12,
        allow_command=True,
        dry_run=False,
        grid_status="confirmed",
    )

    assert result.executed is True
    assert len(session.calls) == 1
    assert session.calls[0]["method"] == "POST"
    assert session.calls[0]["url"].endswith("/api/1/vehicles/123456/command/set_charging_amps")
    assert session.calls[0]["json"] == {"charging_amps": 12}


def test_command_blocked_when_grid_status_not_confirmed(tmp_path: Path) -> None:
    session = FakeSession([])
    client = TeslaCommandClient(
        config=make_config(commands_enabled=True),
        session=session,
        calls_log_path=tmp_path / "tesla_commands.csv",
    )

    with pytest.raises(TeslaCommandBlockedError, match="grid power status"):
        set_charge_amps(
            client,
            10,
            allow_command=True,
            dry_run=False,
            grid_status="partial",
        )

    assert len(session.calls) == 0
