from src.supabase_sink import SupabaseSinkError
from src.tesla_readonly_status import (
    create_optional_supabase_sink,
    maybe_insert_supabase,
)


class FakeSink:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def insert_tesla_sample(self, row: dict) -> None:
        self.rows.append(row)


class FailingSink:
    def insert_tesla_sample(self, _row: dict) -> None:
        raise SupabaseSinkError("forced failure")


class FallbackSink:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.first_call = True

    def insert_tesla_sample(self, row: dict) -> None:
        self.calls.append(dict(row))
        if self.first_call:
            self.first_call = False
            raise SupabaseSinkError(
                "Supabase write failed on tesla_samples with status 400: "
                "{\"code\":\"PGRST204\",\"message\":\"Could not find the "
                "'charge_current_request' column of 'tesla_samples' in the schema cache\"}"
            )


def test_create_optional_supabase_sink_disabled(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_ENABLED", "false")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    sink, state = create_optional_supabase_sink()

    assert sink is None
    assert state == "disabled"


def test_create_optional_supabase_sink_missing_config(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_ENABLED", "true")
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")

    sink, state = create_optional_supabase_sink()

    assert sink is None
    assert state == "missing_config"


def test_maybe_insert_supabase_success() -> None:
    sink = FakeSink()
    snapshot = {
        "sample_timestamp": "2026-04-29T10:00:00Z",
        "vehicle_id": "123",
        "vehicle_state": "online",
    }

    error = maybe_insert_supabase(
        sink=sink,
        snapshot=snapshot,
        source="tesla_sync_readonly",
    )

    assert error is None
    assert len(sink.rows) == 1
    assert sink.rows[0]["vehicle_id"] == "123"
    assert sink.rows[0]["source"] == "tesla_sync_readonly"


def test_maybe_insert_supabase_returns_error_text() -> None:
    snapshot = {
        "sample_timestamp": "2026-04-29T10:00:00Z",
        "vehicle_id": "123",
    }

    error = maybe_insert_supabase(
        sink=FailingSink(),
        snapshot=snapshot,
        source="tesla_sync_readonly",
    )

    assert error is not None
    assert "forced failure" in error


def test_maybe_insert_supabase_fallback_on_missing_column() -> None:
    snapshot = {
        "sample_timestamp": "2026-04-29T10:00:00Z",
        "vehicle_id": "123",
        "charge_current_request": 7.0,
    }
    sink = FallbackSink()

    error = maybe_insert_supabase(
        sink=sink,
        snapshot=snapshot,
        source="tesla_sync_readonly",
    )

    assert error is not None
    assert error.startswith("warning:")
    assert len(sink.calls) == 2
    assert "charge_current_request" in sink.calls[0]
    assert "charge_current_request" not in sink.calls[1]
