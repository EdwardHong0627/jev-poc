"""Bounded conversational JEV service."""
from __future__ import annotations

from typing import Any, Protocol

from jev_bot.models import ChoiceResult, JEVRequest


class _Client(Protocol):
    def decide(self, request: JEVRequest) -> Any: ...


class JevBot:
    def __init__(self, client: _Client, history_size: int = 5) -> None:
        if isinstance(history_size, bool) or not isinstance(history_size, int) or history_size < 1:
            raise ValueError("history_size must be a positive integer")
        self._client = client
        self._history_size = history_size
        self._history: list[str] = []

    def message(self, text: str) -> ChoiceResult:
        cleaned = text.strip() if isinstance(text, str) else ""
        if not cleaned:
            raise ValueError("message must not be blank")
        self._history.append(cleaned)
        self._history = self._history[-self._history_size :]
        request = JEVRequest(state="\n".join(self._history))
        return self._client.decide(request).framework

    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            close()
