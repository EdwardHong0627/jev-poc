"""Decisions API client."""

from __future__ import annotations

import re
from typing import Any

import requests

from jev_bot.config import Config
from jev_bot.errors import DecisionsError
from jev_bot.models import JEVRequest, JEVResponse

_MAX_SNIPPET = 300

_SENSITIVE_PATTERN = re.compile(
    r"(?i)(token|authorization|bearer|password|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*\S+"
)


def _redact(text: str, config: Config) -> str:
    redacted = text
    token = getattr(config, "token", "")
    endpoint = getattr(config, "endpoint", "")
    if token:
        redacted = redacted.replace(token, "[REDACTED]")
    if endpoint:
        redacted = redacted.replace(endpoint, "[REDACTED]")
        # Also scrub bare host to avoid leaking endpoint via reflection.
        host = re.sub(r"^https?://", "", endpoint).split("/")[0]
        if host:
            redacted = redacted.replace(host, "[REDACTED]")
    redacted = _SENSITIVE_PATTERN.sub(r"\1=[REDACTED]", redacted)
    return redacted[:_MAX_SNIPPET]


class DecisionsClient:
    """Thin HTTP client for the Decisions API."""

    def __init__(self, config: Config, session: Any = None):
        self._config = config
        if session is not None:
            self._session = session
            self._owned = False
        else:
            self._session = requests.Session()
            self._owned = True

    def close(self) -> None:
        if getattr(self, "_owned", False):
            close = getattr(self._session, "close", None)
            if callable(close):
                close()

    def decide(self, request: JEVRequest) -> JEVResponse:
        try:
            response = self._session.post(
                self._config.endpoint,
                json=request.to_dict(),
                headers={"Authorization": f"Bearer {self._config.token}"},
                timeout=30,
            )
        except DecisionsError:
            raise
        except Exception as error:
            raise DecisionsError("Decisions request failed") from error
        status = getattr(response, "status_code", None)
        if not isinstance(status, int):
            raise DecisionsError("Decisions request failed: missing status code")
        if not 200 <= status < 300:
            snippet = _redact(str(getattr(response, "text", "")), self._config)
            raise DecisionsError(f"Decisions request failed with status {status}: {snippet}")
        try:
            payload = response.json()
        except Exception as error:
            raise DecisionsError("Decisions response was not valid JSON") from error
        return JEVResponse.from_dict(payload)
