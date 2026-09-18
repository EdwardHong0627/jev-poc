"""Focused tests for DecisionsClient using fake sessions (no network)."""

from __future__ import annotations

import json

import pytest

from jev_bot.client import DecisionsClient
from jev_bot.config import Config
from jev_bot.errors import DecisionsError
from jev_bot.models import JEVRequest


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


def make_config():
    return Config(endpoint="https://example.test/decide", token="secret-token-xyz")


def test_exact_request():
    req = JEVRequest(state="hello")
    session = FakeSession(response=FakeResponse(json_value={
        "answers": {"framework": {"choice": "a", "probabilities": {"a": 0.9, "b": 0.1}}},
    }))
    client = DecisionsClient(make_config(), session=session)
    resp = client.decide(req)
    assert resp.framework.choice == "a"
    assert len(session.calls) == 1
    url, kwargs = session.calls[0]
    assert url == "https://example.test/decide"
    assert kwargs["json"] == req.to_dict()
    assert kwargs["headers"]["Authorization"] == "Bearer secret-token-xyz"


def test_non_2xx_maps_to_decisions_error_without_leak():
    session = FakeSession(response=FakeResponse(status_code=500, text="server blew up " * 100))
    client = DecisionsClient(make_config(), session=session)
    with pytest.raises(DecisionsError) as exc_info:
        client.decide(JEVRequest(state="x"))
    msg = str(exc_info.value)
    assert "500" in msg
    assert "secret-token-xyz" not in msg
    assert "example.test" not in msg
    assert len(msg) < 2000


def test_transport_error_maps():
    session = FakeSession(exc=ConnectionError("boom"))
    client = DecisionsClient(make_config(), session=session)
    with pytest.raises(DecisionsError):
        client.decide(JEVRequest(state="x"))


def test_transport_error_redacts_sentinels_and_chains():
    sentinel_token = "secret-token-xyz"
    sentinel_endpoint = "https://example.test/decide"
    session = FakeSession(exc=ConnectionError(f"boom {sentinel_token} at {sentinel_endpoint}"))
    client = DecisionsClient(make_config(), session=session)
    with pytest.raises(DecisionsError) as exc_info:
        client.decide(JEVRequest(state="x"))
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
        client.decide(JEVRequest(state="x"))
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
        client.decide(JEVRequest(state="x"))


def test_close_owned_only():
    class ClosableFake:
        def __init__(self):
            self.closed = False
        def close(self):
            self.closed = True
        def post(self, url, **kwargs):
            return FakeResponse(json_value={
                "answers": {"framework": {"choice": "a", "probabilities": {"a": 1.0}}},
            })
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
        client.decide(JEVRequest(state="x"))


def test_malformed_payload_maps():
    session = FakeSession(response=FakeResponse(json_value={"wrong": 1}))
    client = DecisionsClient(make_config(), session=session)
    with pytest.raises(DecisionsError):
        client.decide(JEVRequest(state="x"))
