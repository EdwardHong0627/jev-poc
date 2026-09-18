"""Behavior tests for JevBot (no network)."""
from __future__ import annotations

import pytest

from jev_bot.models import ChoiceResult, JEVRequest, JEVResponse
from jev_bot.service import JevBot


class FakeClient:
    def __init__(self, result: ChoiceResult | None = None):
        self.calls: list[JEVRequest] = []
        self.result = result or ChoiceResult(choice="a", probabilities={"a": 1.0})

    def decide(self, request):
        self.calls.append(request)
        return JEVResponse(answers={"framework": self.result})


def test_blank_rejected_without_client_call():
    client = FakeClient()
    bot = JevBot(client)
    for bad in ("", "   ", "\n\t "):
        with pytest.raises(ValueError):
            bot.message(bad)
    assert client.calls == []


def test_strips_outer_whitespace_and_single_call_state():
    client = FakeClient()
    bot = JevBot(client)
    bot.message("  hello  ")
    assert len(client.calls) == 1
    assert client.calls[0].state == "hello"
    assert isinstance(client.calls[0], JEVRequest)


def test_history_bounded_to_two_newest_chronological():
    client = FakeClient()
    bot = JevBot(client, history_size=2)
    bot.message("one")
    bot.message("two")
    bot.message("three")
    assert client.calls[-1].state == "two\nthree"


def test_returns_framework_result():
    expected = ChoiceResult(choice="x", probabilities={"x": 0.7})
    client = FakeClient(result=expected)
    bot = JevBot(client)
    assert bot.message("hi") == expected


def test_history_size_must_be_positive_int():
    with pytest.raises(ValueError):
        JevBot(FakeClient(), history_size=0)
    with pytest.raises(ValueError):
        JevBot(FakeClient(), history_size=-1)


def test_close_delegates_to_client():
    class ClosableClient(FakeClient):
        closed = False

        def close(self):
            self.closed = True

    client = ClosableClient()
    JevBot(client).close()

    assert client.closed
