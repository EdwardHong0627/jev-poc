"""Decisions API client."""

from __future__ import annotations

import re
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from jev_bot.config import Config
from jev_bot.errors import DecisionsError
from jev_bot.models import JEVRequest, JEVResponse

_MAX_SNIPPET = 300
_DEFAULT_MAX_RETRIES = 1

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
    """Thin HTTP client for the Decisions API with bounded transient retry."""

    # Transient error status codes that warrant retry.
    _RETRYABLE_STATUS: set[int] = {408, 429, 500, 502, 503, 504}

    def __init__(self, config: Config, session: Any = None, retries: int = _DEFAULT_MAX_RETRIES):
        self._config = config
        self._retries = retries
        if session is not None:
            self._session = session
            self._owned = False
            self._using_injected = True
        else:
            self._session = requests.Session()
            self._owned = True
            self._using_injected = False

        if not self._using_injected:
            self._attach_retry_adapter()

    def _attach_retry_adapter(self) -> None:
        """Attach an HTTPAdapter with bounded retry for transient errors."""
        retry = Retry(
            total=self._retries,
            backoff_factor=0,  # no exponential backoff — we handle Retry-After ourselves
            status_forcelist=self._RETRYABLE_STATUS,
            allowed_methods=["POST"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

    def _should_retry_status(self, status: int) -> bool:
        """Return True if this status code is transient and worth retrying."""
        return status in self._RETRYABLE_STATUS

    def close(self) -> None:
        if getattr(self, "_owned", False):
            close = getattr(self._session, "close", None)
            if callable(close):
                close()

    def decide(self, request: JEVRequest) -> JEVResponse:
        last_error: DecisionsError | None = None
        last_status: int | None = None
        last_response: Any | None = None

        for attempt in range(1 + self._retries):
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
                # Connection error — transient, retry with backoff
                if attempt < self._retries:
                    last_error = DecisionsError("Decisions request failed")
                    last_error.__cause__ = error
                    time.sleep(0.1 * (2 ** attempt))
                    continue
                raise DecisionsError("Decisions request failed") from error

            status = getattr(response, "status_code", None)
            if not isinstance(status, int):
                raise DecisionsError("Decisions request failed: missing status code")

            if status in self._RETRYABLE_STATUS:
                last_status = status
                last_response = response
                if attempt < self._retries:
                    # Respect Retry-After header (seconds), cap at 5s.
                    retry_after = self._parse_retry_after(response)
                    time.sleep(min(retry_after, 5))
                    continue
                # Exhausted retries — fall through to error reporting below

            # Non-retryable or final attempt
            if not 200 <= status < 300:
                snippet = _redact(str(getattr(response, "text", "")), self._config)
                raise DecisionsError(
                    f"Decisions request failed with status {status}: {snippet}"
                )

            # Parse and return on success
            try:
                payload = response.json()
            except Exception as error:
                raise DecisionsError("Decisions response was not valid JSON") from error
            return JEVResponse.from_dict(payload)

        # Retry exhaustion — report the last error status
        snippet = _redact(str(getattr(last_response, "text", "")), self._config)
        raise DecisionsError(
            f"Decisions request failed after {1 + self._retries} attempts, "
            f"last status {last_status}: {snippet}"
        )

    @staticmethod
    def _parse_retry_after(response: Any) -> float:
        """Extract Retry-After header value in seconds, defaulting to 0."""
        headers = getattr(response, "headers", None)
        if headers is None:
            return 0.0
        raw = headers.get("Retry-After") or headers.get("retry-after")
        if raw is None:
            return 0.0
        try:
            return float(raw)
        except (ValueError, TypeError):
            return 0.0
