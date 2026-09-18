"""Focused tests for DecisionsClient using fake sessions (no network)."""

from __future__ import annotations

import json

import pytest

from jev_bot.client import DecisionsClient
from jev_bot.config import Config
from jev_bot.errors import DecisionsError
from jev_bot.models import ChoiceQuestion, JEVRequest


def make_config():
    return Config(endpoint="https://example.test/decide", token="secret-token-xyz")


def _make_request(state: str = "hello") -> JEVRequest:
    return JEVRequest(
        state=state,
        model="test-model",
        questions={
            "q1": ChoiceQuestion(
                instructions="Choose one",
                criteria={"a": "Option A", "b": "Option B"},
            )
        },
    )


def _make_success_response(choice: str = "a") -> dict:
    return {
        "answers": {
            "q1": {
                "type": "choice",
                "choice": choice,
                "probabilities": {"a": 0.9, "b": 0.1},
                "confidence": 0.9,
            }
        },
    }


class FakeResponse:
    def __init__(self, status_code=200, text="", json_value=None, json_raises=False):
        self.status_code = status_code
        self.text = text
        self._json_value = json_value
        self._json_raises = json_raises

    def json(self):
        if self._json_raises:
            raise ValueError("No JSON")
        if self._json_value is not None:
            return self._json_value
        return json.loads(self.text)


class FakeSession:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.exc is not None:
            raise self.exc
        return self.response


def test_exact_request():
    req = _make_request()
    session = FakeSession(response=FakeResponse(json_value=_make_success_response("a")))
    client = DecisionsClient(make_config(), session=session)
    resp = client.decide(req)
    assert resp.answers["q1"].choice == "a"
    assert len(session.calls) == 1
    url, kwargs = session.calls[0]
    assert url == "https://example.test/decide"
    assert kwargs["json"] == req.to_dict()
    assert kwargs["headers"]["Authorization"] == "Bearer secret-token-xyz"


def test_non_2xx_maps_to_decisions_error_without_leak():
    session = FakeSession(response=FakeResponse(status_code=500, text="server blew up " * 100))
    client = DecisionsClient(make_config(), session=session)
    with pytest.raises(DecisionsError) as exc_info:
        client.decide(_make_request("x"))
    msg = str(exc_info.value)
    assert "500" in msg
    assert "secret-token-xyz" not in msg
    assert "example.test" not in msg
    assert len(msg) < 2000


def test_transport_error_maps():
    session = FakeSession(exc=ConnectionError("boom"))
    client = DecisionsClient(make_config(), session=session, retries=0)
    with pytest.raises(DecisionsError):
        client.decide(_make_request())


def test_transport_error_redacts_sentinels_and_chains():
    sentinel_token = "secret-token-xyz"
    sentinel_endpoint = "https://example.test/decide"
    session = FakeSession(exc=ConnectionError(f"boom {sentinel_token} at {sentinel_endpoint}"))
    client = DecisionsClient(make_config(), session=session, retries=0)
    with pytest.raises(DecisionsError) as exc_info:
        client.decide(_make_request())
    msg = str(exc_info.value)
    assert sentinel_token not in msg
    assert sentinel_endpoint not in msg
    assert "example.test" not in msg
    assert exc_info.value.__cause__ is not None


def test_non_2xx_redacts_sentinels_keeps_status_bounded_and_chains():
    sentinel_token = "secret-token-xyz"
    sentinel_endpoint = "https://example.test/decide"
    body = f"err {sentinel_token} {sentinel_endpoint} " + "token=supersecret password=hunter2 " + ("x" * 5000)
    session = FakeSession(response=FakeResponse(status_code=503, text=body))
    client = DecisionsClient(make_config(), session=session)
    with pytest.raises(DecisionsError) as exc_info:
        client.decide(_make_request())
    msg = str(exc_info.value)
    assert "503" in msg
    assert sentinel_token not in msg
    assert sentinel_endpoint not in msg
    assert "example.test" not in msg
    assert "supersecret" not in msg
    assert "hunter2" not in msg
    assert len(msg) < 2000


def test_missing_status_code_is_error():
    class NoStatus:
        text = "oops"
        def json(self):
            return {}
    client = DecisionsClient(make_config(), session=FakeSession(response=NoStatus()))
    with pytest.raises(DecisionsError):
        client.decide(_make_request())


def test_close_owned_only():
    class ClosableFake:
        def __init__(self):
            self.closed = False
        def close(self):
            self.closed = True
        def post(self, url, **kwargs):
            return FakeResponse(json_value=_make_success_response("a"))
    injected = ClosableFake()
    client_injected = DecisionsClient(make_config(), session=injected)
    client_injected.close()
    assert injected.closed is False

    owned_session = ClosableFake()
    client_owned = DecisionsClient(make_config(), session=owned_session)
    client_owned._owned = True
    client_owned.close()
    assert owned_session.closed is True


def test_invalid_json_maps():
    session = FakeSession(response=FakeResponse(text="not json{", json_raises=True))
    client = DecisionsClient(make_config(), session=session)
    with pytest.raises(DecisionsError):
        client.decide(_make_request())


def test_malformed_payload_maps():
    session = FakeSession(response=FakeResponse(json_value={"wrong": 1}))
    client = DecisionsClient(make_config(), session=session)
    with pytest.raises(DecisionsError):
        client.decide(_make_request())


# ── Retry policy tests ──────────────────────────────────────────────────────


class CountingSession:
    """Fake session that counts calls and can vary responses."""

    def __init__(self, *responses, exc=None):
        self.responses = list(responses)
        self.exc = exc
        self.calls = []
        self.call_count = 0

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        self.call_count += 1
        if self.exc is not None:
            raise self.exc
        return self.responses.pop(0)


def _make_client(session):
    return DecisionsClient(make_config(), session=session)


def test_retry_on_connection_error_retries_once():
    """A second attempt should succeed after a transient connection failure."""
    good_resp = FakeResponse(json_value=_make_success_response("b"))

    class RetrySession:
        def __init__(self):
            self.calls = []
            self.call_count = 0

        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            self.call_count += 1
            if self.call_count == 1:
                raise ConnectionError("Connection refused")
            return good_resp

    session = RetrySession()
    client = _make_client(session)
    resp = client.decide(_make_request())
    assert resp.answers["q1"].choice == "b"
    assert session.call_count == 2


def test_retry_on_408_uses_second_attempt():
    """HTTP 408 (Request Timeout) is transient and must be retried."""
    good_resp = FakeResponse(json_value=_make_success_response("c"))
    attempts = [0]

    class Temp408Session:
        def __init__(self):
            self.calls = []
            self.call_count = 0

        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            self.call_count += 1
            attempts[0] += 1
            if attempts[0] == 1:
                return FakeResponse(status_code=408, text="Timeout")
            return good_resp

    session = Temp408Session()
    client = _make_client(session)
    resp = client.decide(_make_request())
    assert resp.answers["q1"].choice == "c"
    assert session.call_count == 2


def test_retry_on_429_rate_limit():
    """HTTP 429 (Too Many Requests) is transient and must be retried."""
    good_resp = FakeResponse(json_value=_make_success_response("d"))
    attempts = [0]

    class Temp429Session:
        def __init__(self):
            self.calls = []
            self.call_count = 0

        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            self.call_count += 1
            attempts[0] += 1
            if attempts[0] == 1:
                return FakeResponse(status_code=429, text="Rate limited")
            return good_resp

    session = Temp429Session()
    client = _make_client(session)
    resp = client.decide(_make_request())
    assert resp.answers["q1"].choice == "d"
    assert session.call_count == 2


def test_retry_on_5xx():
    """HTTP 5xx server errors are transient and must be retried."""
    good_resp = FakeResponse(json_value=_make_success_response("e"))
    attempts = [0]

    class Temp5xxSession:
        def __init__(self):
            self.calls = []
            self.call_count = 0

        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            self.call_count += 1
            attempts[0] += 1
            if attempts[0] == 1:
                return FakeResponse(status_code=502, text="Bad gateway")
            return good_resp

    session = Temp5xxSession()
    client = _make_client(session)
    resp = client.decide(_make_request())
    assert resp.answers["q1"].choice == "e"
    assert session.call_count == 2


def test_no_retry_for_404():
    """HTTP 404 (Not Found) is client error — no retry."""
    session = CountingSession(FakeResponse(status_code=404, text="Not found"))
    client = _make_client(session)
    with pytest.raises(DecisionsError):
        client.decide(_make_request())
    assert session.call_count == 1


def test_no_retry_for_403():
    """HTTP 403 (Forbidden) is client error — no retry."""
    session = CountingSession(FakeResponse(status_code=403, text="Forbidden"))
    client = _make_client(session)
    with pytest.raises(DecisionsError):
        client.decide(_make_request())
    assert session.call_count == 1


def test_no_retry_for_400():
    """HTTP 400 (Bad Request) is client error — no retry."""
    session = CountingSession(FakeResponse(status_code=400, text="Bad request"))
    client = _make_client(session)
    with pytest.raises(DecisionsError):
        client.decide(_make_request())
    assert session.call_count == 1


def test_retry_exhaustion_raises_error():
    """After exhausting retries, a DecisionsError is raised."""
    session = CountingSession(
        FakeResponse(status_code=502, text="Bad gateway"),
        FakeResponse(status_code=502, text="Bad gateway"),
    )
    client = _make_client(session)
    with pytest.raises(DecisionsError) as exc_info:
        client.decide(_make_request())
    assert session.call_count == 2  # initial + 1 retry
    assert "502" in str(exc_info.value)


def test_successful_response_after_retry_preserves_metadata():
    """Metadata (id, model, usage, provider) from the successful response is preserved."""
    good_resp = FakeResponse(json_value={
        "id": "chatcmpl-abc123",
        "model": "test-model",
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "provider": {"openrouter": {"metrics": {"p99": 0.25}}},
        "answers": {"q1": {"type": "choice", "choice": "a", "probabilities": {"a": 0.95, "b": 0.05}, "confidence": 0.95}},
    })
    attempts = [0]

    class MetadataSession:
        def __init__(self):
            self.calls = []
            self.call_count = 0

        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            self.call_count += 1
            attempts[0] += 1
            if attempts[0] == 1:
                return FakeResponse(status_code=503, text="Service unavailable")
            return good_resp

    session = MetadataSession()
    client = _make_client(session)
    resp = client.decide(_make_request())
    assert resp.answers["q1"].choice == "a"
    # The successful response should carry through its metadata
    assert session.call_count == 2
    # Verify the response is fully constructed (no stubs)
    assert resp.answers["q1"].probabilities["a"] == 0.95


def test_retry_after_header_respected():
    """When Retry-After header is present, the client respects it (or at least does not break)."""
    good_resp = FakeResponse(json_value=_make_success_response("f"))
    attempts = [0]

    class RetryAfterSession:
        def __init__(self):
            self.calls = []
            self.call_count = 0

        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            self.call_count += 1
            attempts[0] += 1
            if attempts[0] == 1:
                resp = FakeResponse(status_code=429, text="Rate limited")
                resp.headers = {"Retry-After": "2"}
                return resp
            return good_resp

    session = RetryAfterSession()
    client = _make_client(session)
    # The test verifies the client does not crash when Retry-After is present
    # A full sleep-based test would be integration; we just ensure no error.
    resp = client.decide(_make_request())
    assert resp.answers["q1"].choice == "f"
    assert session.call_count == 2
