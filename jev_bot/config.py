"""Environment-backed configuration for the JEV Decisions API."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


DEFAULT_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"


@dataclass(frozen=True)
class Config:
    """Validated configuration required to call the Decisions API."""

    endpoint: str
    token: str = field(repr=False)


def load_config() -> Config:
    """Load JEV configuration without providing a credential fallback."""
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
    token = os.environ.get("JEV_API_TOKEN", "").strip()
    if not token:
        raise EnvironmentError("JEV_API_TOKEN environment variable is required")

    endpoint = os.environ.get("JEV_ENDPOINT", "").strip() or DEFAULT_ENDPOINT
    _validate_endpoint(endpoint)
    return Config(endpoint=endpoint, token=token)


def _validate_endpoint(endpoint: str) -> None:
    """Accept only well-formed HTTPS openrouter.ai URLs without userinfo."""
    try:
        parts = urlsplit(endpoint)
    except ValueError as exc:
        raise ValueError(f"JEV_ENDPOINT is not a valid URL: {endpoint!r}") from exc
    if (
        parts.scheme != "https"
        or parts.hostname != "openrouter.ai"
        or parts.username is not None
        or parts.password is not None
        or "@" in parts.netloc
    ):
        raise ValueError(
            "JEV_ENDPOINT must be an HTTPS URL on openrouter.ai without userinfo"
        )
