"""Environment-backed configuration for the JEV Decisions API."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

from jev_bot.config_store import (
    UserConfig,
    get_config_path,
    read_user_config,
)

DEFAULT_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"


@dataclass(frozen=True)
class Config:
    """Validated configuration required to call the Decisions API."""

    endpoint: str
    token: str = field(repr=False)


def _load_token() -> str:
    """Return a non-blank token, falling through to the config store."""
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
    token = os.environ.get("JEV_API_TOKEN", "").strip()
    if token:
        return token

    config_path = get_config_path()
    user_config = read_user_config(config_path)
    if user_config is not None:
        return user_config.token

    raise EnvironmentError("JEV_API_TOKEN environment variable is required")


def _load_endpoint() -> str:
    """Return an endpoint, falling through to the config store when blank."""
    endpoint = os.environ.get("JEV_ENDPOINT", "").strip()
    if endpoint:
        _validate_endpoint(endpoint)
        return endpoint

    config_path = get_config_path()
    user_config = read_user_config(config_path)
    if user_config is not None:
        return user_config.endpoint

    return DEFAULT_ENDPOINT


def load_config() -> Config:
    """Load JEV configuration with env → store → default precedence."""
    token = _load_token()
    endpoint = _load_endpoint()
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
