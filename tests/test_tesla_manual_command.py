from types import SimpleNamespace

import pytest

from src.tesla_commands import TeslaCommandBlockedError
from src.tesla_manual_command import parse_args, run_command
import src.tesla_manual_command as manual


class DummyClient:
    def __init__(self, *, commands_enabled: bool = True, allow_wake_up: bool = False) -> None:
        self.config = SimpleNamespace(
            commands_enabled=commands_enabled,
            allow_wake_up=allow_wake_up,
        )
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_parse_args_requires_ack_flag() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--set-amps", "6"])


def test_run_command_set_amps_dry_run_calls_wrapper(monkeypatch) -> None:
    called: dict[str, object] = {}

    def fake_set_charge_amps(client, amps, *, allow_command, dry_run, grid_status, vehicle_id):
        called["client"] = client
        called["amps"] = amps
        called["allow_command"] = allow_command
        called["dry_run"] = dry_run
        called["grid_status"] = grid_status
        called["vehicle_id"] = vehicle_id
        return SimpleNamespace(
            executed=False,
            blocked=False,
            reason="dry-run: command not sent",
            status_code=None,
        )

    monkeypatch.setattr(manual, "set_charge_amps", fake_set_charge_amps)
    args = parse_args(
        [
            "--set-amps",
            "6",
            "--dry-run",
            "--i-understand-this-sends-real-command",
        ]
    )
    client = DummyClient(commands_enabled=True, allow_wake_up=False)

    exit_code = run_command(args, client)

    assert exit_code == 0
    assert called["client"] is client
    assert called["amps"] == 6
    assert called["allow_command"] is True
    assert called["dry_run"] is True
    assert called["grid_status"] == "confirmed"
    assert called["vehicle_id"] is None


def test_run_command_fails_when_wakeup_enabled(monkeypatch) -> None:
    called = {"set_amps": False}

    def fake_set_charge_amps(*_args, **_kwargs):
        called["set_amps"] = True
        return None

    monkeypatch.setattr(manual, "set_charge_amps", fake_set_charge_amps)
    args = parse_args(
        [
            "--set-amps",
            "6",
            "--dry-run",
            "--i-understand-this-sends-real-command",
        ]
    )
    client = DummyClient(commands_enabled=True, allow_wake_up=True)

    exit_code = run_command(args, client)

    assert exit_code == 2
    assert called["set_amps"] is False


def test_main_start_charge_uses_client_factory_and_closes(monkeypatch) -> None:
    client = DummyClient(commands_enabled=True, allow_wake_up=False)
    called = {"start": False}

    def fake_create_client():
        return client

    def fake_start_charge(
        _client,
        *,
        allow_command,
        dry_run,
        grid_status,
        vehicle_id,
    ):
        called["start"] = True
        assert _client is client
        assert allow_command is True
        assert dry_run is True
        assert grid_status == "confirmed"
        assert vehicle_id is None
        return SimpleNamespace(
            executed=False,
            blocked=False,
            reason="dry-run: command not sent",
            status_code=None,
        )

    monkeypatch.setattr(manual, "create_tesla_command_client", fake_create_client)
    monkeypatch.setattr(manual, "start_charge", fake_start_charge)

    exit_code = manual.main(
        [
            "--start-charge",
            "--dry-run",
            "--i-understand-this-sends-real-command",
        ]
    )

    assert exit_code == 0
    assert called["start"] is True
    assert client.closed is True


def test_main_returns_error_one_when_command_blocked(monkeypatch) -> None:
    client = DummyClient(commands_enabled=False, allow_wake_up=False)

    def fake_create_client():
        return client

    def fake_set_charge_amps(*_args, **_kwargs):
        raise TeslaCommandBlockedError("TESLA_COMMANDS_ENABLED=false")

    monkeypatch.setattr(manual, "create_tesla_command_client", fake_create_client)
    monkeypatch.setattr(manual, "set_charge_amps", fake_set_charge_amps)

    exit_code = manual.main(
        [
            "--set-amps",
            "6",
            "--dry-run",
            "--i-understand-this-sends-real-command",
        ]
    )

    assert exit_code == 1
    assert client.closed is True
