"""Secure, persistent user configuration for the JEV Decisions API."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR_NAME = "jev-poc"
CONFIG_FILE_NAME = "config.json"
CONFIG_DIR_MODE = 0o700
CONFIG_FILE_MODE = 0o600


@dataclass(frozen=True)
class UserConfig:
    """A single token + endpoint pair stored persistently on disk."""

    token: str = field(repr=False)
    endpoint: str

    def __post_init__(self) -> None:
        from jev_bot.config import _validate_endpoint

        token = (self.token or "").strip()
        endpoint = (self.endpoint or "").strip()
        if not token:
            raise ValueError("token must be non-blank")
        if not endpoint:
            raise ValueError("endpoint must be non-blank")
        _validate_endpoint(endpoint)
        # Rebind to stripped values via object.__setattr__ (frozen).
        object.__setattr__(self, "token", token)
        object.__setattr__(self, "endpoint", endpoint)


def get_config_path() -> Path:
    """Return the canonical config file path ($XDG_CONFIG_HOME/jev-poc/config.json)."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if not xdg:
        home = os.path.expanduser("~")
        xdg = os.path.join(home, ".config")
    return Path(xdg) / CONFIG_DIR_NAME / CONFIG_FILE_NAME


def _ensure_secure_perms(path: Path) -> None:
    """Ensure the directory and file at *path* have 0700 / 0600 respectively."""
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    os.chmod(parent, CONFIG_DIR_MODE)
    if path.exists():
        os.chmod(path, CONFIG_FILE_MODE)


def write_user_config(config_dir: Path, user_config: UserConfig) -> Path:
    """Atomically write *user_config* to the given directory.

    Returns the resolved path to the written file.
    """
    config_path = config_dir / CONFIG_FILE_NAME
    _ensure_secure_perms(config_path)

    content = json.dumps(
        {"token": user_config.token, "endpoint": user_config.endpoint},
        indent=2,
    )
    with tempfile.NamedTemporaryFile(
        dir=str(config_path.parent),
        suffix=".tmp",
        mode="w",
        delete=False,
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    # Atomic rename
    os.replace(tmp_path, config_path)
    os.chmod(config_path, CONFIG_FILE_MODE)
    return config_path


def read_user_config(config_path: Path) -> UserConfig | None:
    """Read and validate a stored config, or *None* when absent / unparseable."""
    if not config_path.exists():
        return None
    try:
        raw = config_path.read_text()
        if not raw.strip():
            return None
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError):
        raise ValueError(
            f"jev-poc config at {config_path} is malformed — "
            "remove it or provide valid JSON with token + endpoint keys"
        ) from None

    if not isinstance(data, dict):
        raise ValueError(
            f"jev-poc config at {config_path} is malformed — "
            "expected a JSON object with token and endpoint keys"
        )

    try:
        return UserConfig(token=data["token"], endpoint=data["endpoint"])
    except KeyError as exc:
        raise ValueError(
            f"jev-poc config at {config_path} is missing required key: {exc}"
        ) from None
    except (TypeError, AttributeError) as exc:
        raise ValueError(
            f"jev-poc config at {config_path} is malformed — {exc}"
        ) from None


def remove_user_config(config_path: Path) -> None:
    """Remove the stored config file and an empty parent directory."""
    if config_path.exists():
        config_path.unlink()
    parent = config_path.parent
    try:
        parent.rmdir()
    except OSError:
        # Not empty or doesn't exist — leave it.
        pass
