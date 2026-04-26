from src.supabase_sink import SupabaseSink, SupabaseSinkConfig, SupabaseSinkError


class FakeResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
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
        return self.response

    def close(self) -> None:
        return None


def make_sink(session: FakeSession) -> SupabaseSink:
    return SupabaseSink(
        SupabaseSinkConfig(
            url="https://example.supabase.co",
            service_role_key="service-role-key",
            timeout_seconds=2.0,
        ),
        session=session,
    )


def test_insert_inverter_sample_uses_target_table() -> None:
    session = FakeSession(FakeResponse(status_code=201))
    sink = make_sink(session)

    sink.insert_inverter_sample({"sample_timestamp": "2026-01-01T00:00:00Z"})

    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://example.supabase.co/rest/v1/inverter_samples"
    assert call["headers"]["apikey"] == "service-role-key"
    assert call["headers"]["Authorization"] == "Bearer service-role-key"
    assert call["timeout"] == 2.0


def test_insert_controller_decision_uses_target_table() -> None:
    session = FakeSession(FakeResponse(status_code=201))
    sink = make_sink(session)

    sink.insert_controller_decision({"sample_timestamp": "2026-01-01T00:00:00Z"})

    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"] == "https://example.supabase.co/rest/v1/controller_decisions"


def test_insert_row_raises_on_http_error() -> None:
    session = FakeSession(FakeResponse(status_code=400, text="bad request"))
    sink = make_sink(session)

    try:
        sink.insert_tesla_sample({"sample_timestamp": "2026-01-01T00:00:00Z"})
    except SupabaseSinkError as exc:
        assert "status 400" in str(exc)
        assert "tesla_samples" in str(exc)
    else:
        raise AssertionError("Expected SupabaseSinkError for non-success response")
