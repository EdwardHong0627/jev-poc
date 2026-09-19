"""Tests for jev_bot.config_store — XDG config path, atomic persistence, validation."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from jev_bot.config import load_config
from jev_bot.config_store import (
    CONFIG_DIR_NAME,
    CONFIG_FILE_NAME,
    UserConfig,
    get_config_path,
    read_user_config,
    write_user_config,
    remove_user_config,
    CONFIG_DIR_MODE,
    CONFIG_FILE_MODE,
)


# ---------------------------------------------------------------------------
# XDG path fallback
# ---------------------------------------------------------------------------


class TestGetXConfigPath:
    def test_xdg_config_home_override(self, tmp_path, monkeypatch) -> None:
        custom = str(tmp_path / "my-config")
        monkeypatch.setenv("XDG_CONFIG_HOME", custom)
        result = get_config_path()
        assert result == Path(custom) / "jev-poc" / "config.json"

    def test_default_when_no_xdg(self, tmp_path, monkeypatch) -> None:
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        home = Path(tmp_path) / "home"
        monkeypatch.setattr(os.path, "expanduser", lambda x: str(home) if x == "~" else x)
        result = get_config_path()
        assert result == home / ".config" / "jev-poc" / "config.json"

    def test_config_dir_name_constant(self) -> None:
        assert CONFIG_DIR_NAME == "jev-poc"

    def test_config_file_name_constant(self) -> None:
        assert CONFIG_FILE_NAME == "config.json"


# ---------------------------------------------------------------------------
# Secure atomic persistence
# ---------------------------------------------------------------------------


class TestWriteUserConfig:
    def test_creates_directory_with_0700(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(os.path, "expanduser", lambda x: str(home) if x == "~" else x)
        path = get_config_path()

        write_user_config(path.parent, UserConfig(token="tok1", endpoint="https://openrouter.ai/api/alpha/decisions"))

        dir_stat = path.parent.stat()
        assert stat.S_IMODE(dir_stat.st_mode) == 0o700

    def test_creates_file_with_0600(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(os.path, "expanduser", lambda x: str(home) if x == "~" else x)
        path = get_config_path()

        write_user_config(path.parent, UserConfig(token="tok1", endpoint="https://openrouter.ai/api/alpha/decisions"))

        file_stat = path.stat()
        assert stat.S_IMODE(file_stat.st_mode) == 0o600

    def test_writes_valid_json(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(os.path, "expanduser", lambda x: str(home) if x == "~" else x)
        path = get_config_path()

        write_user_config(path.parent, UserConfig(token="my-token", endpoint="https://openrouter.ai/api/alpha/decisions"))

        data = json.loads(path.read_text())
        assert data["token"] == "my-token"
        assert data["endpoint"] == "https://openrouter.ai/api/alpha/decisions"

    def test_overwrites_existing_file(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(os.path, "expanduser", lambda x: str(home) if x == "~" else x)
        path = get_config_path()

        write_user_config(path.parent, UserConfig(token="first", endpoint="https://openrouter.ai/api/alpha/decisions"))
        write_user_config(path.parent, UserConfig(token="second", endpoint="https://openrouter.ai/api/alpha/decisions"))

        data = json.loads(path.read_text())
        assert data["token"] == "second"

    def test_atomic_write_via_tempfile(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(os.path, "expanduser", lambda x: str(home) if x == "~" else x)
        path = get_config_path()

        write_user_config(path.parent, UserConfig(token="tok", endpoint="https://openrouter.ai/api/alpha/decisions"))

        # Only the final file should exist (no lingering .tmp)
        remaining = list(path.parent.iterdir())
        assert len(remaining) == 1
        assert remaining[0] == path


# ---------------------------------------------------------------------------
# chmod on pre-existing paths (directory already exists with wrong perms)
# ---------------------------------------------------------------------------


class TestSecurePermissionsOnPreExistingPaths:
    def test_fixes_existing_dir_perms(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(os.path, "expanduser", lambda x: str(home) if x == "~" else x)
        config_dir = home / ".config" / "jev-poc"
        config_dir.mkdir(parents=True, mode=0o755)
        path = get_config_path()

        write_user_config(path.parent, UserConfig(token="tok", endpoint="https://openrouter.ai/api/alpha/decisions"))

        dir_stat = config_dir.stat()
        assert stat.S_IMODE(dir_stat.st_mode) == 0o700

    def test_fixes_existing_file_perms(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(os.path, "expanduser", lambda x: str(home) if x == "~" else x)
        config_dir = home / ".config" / "jev-poc"
        config_dir.mkdir(parents=True)
        path = get_config_path()
        path.write_text('{"token":"old","endpoint":"https://openrouter.ai/api/alpha/decisions"}')
        path.chmod(0o644)

        write_user_config(path.parent, UserConfig(token="new", endpoint="https://openrouter.ai/api/alpha/decisions"))

        file_stat = path.stat()
        assert stat.S_IMODE(file_stat.st_mode) == 0o600


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestUserConfigValidation:
    def test_valid_config(self) -> None:
        cfg = UserConfig(token="abc", endpoint="https://openrouter.ai/api/alpha/decisions")
        assert cfg.token == "abc"
        assert cfg.endpoint == "https://openrouter.ai/api/alpha/decisions"

    def test_empty_token_raises(self) -> None:
        with pytest.raises(ValueError, match="token"):
            UserConfig(token="", endpoint="https://openrouter.ai/api/alpha/decisions")

    def test_blank_token_raises(self) -> None:
        with pytest.raises(ValueError, match="token"):
            UserConfig(token="   ", endpoint="https://openrouter.ai/api/alpha/decisions")

    def test_empty_endpoint_raises(self) -> None:
        with pytest.raises(ValueError, match="endpoint"):
            UserConfig(token="abc", endpoint="")

    def test_blank_endpoint_raises(self) -> None:
        with pytest.raises(ValueError, match="endpoint"):
            UserConfig(token="abc", endpoint="   ")

    def test_http_endpoint_raises(self) -> None:
        with pytest.raises(ValueError, match="JEV_ENDPOINT"):
            UserConfig(token="abc", endpoint="http://openrouter.ai/api/alpha/decisions")

    def test_non_openrouter_endpoint_raises(self) -> None:
        with pytest.raises(ValueError, match="JEV_ENDPOINT"):
            UserConfig(token="abc", endpoint="https://example.test/api")

    def test_endpoint_with_userinfo_raises(self) -> None:
        with pytest.raises(ValueError, match="JEV_ENDPOINT"):
            UserConfig(token="abc", endpoint="https://user:pass@openrouter.ai/api")

    def test_malformed_endpoint_raises(self) -> None:
        with pytest.raises(ValueError, match="JEV_ENDPOINT"):
            UserConfig(token="abc", endpoint="not-a-url")

    def test_none_token_raises(self) -> None:
        with pytest.raises(ValueError, match="token"):
            UserConfig(token=None, endpoint="https://openrouter.ai/api/alpha/decisions")


# ---------------------------------------------------------------------------
# Safe malformed file errors
# ---------------------------------------------------------------------------


class TestReadUserConfigMalformed:
    def test_truncated_json_error(self, tmp_path) -> None:
        path = tmp_path / "config.json"
        path.write_text('{"token": "abc", "')
        with pytest.raises(ValueError, match="config"):
            read_user_config(path)

    def test_garbage_file_error(self, tmp_path) -> None:
        path = tmp_path / "config.json"
        path.write_text("not json at all!!!")
        with pytest.raises(ValueError, match="config"):
            read_user_config(path)

    def test_missing_file_returns_none(self, tmp_path) -> None:
        path = tmp_path / "config.json"
        assert read_user_config(path) is None

    def test_empty_file_returns_none(self, tmp_path) -> None:
        path = tmp_path / "config.json"
        path.write_text("")
        assert read_user_config(path) is None

    def test_valid_read(self, tmp_path) -> None:
        path = tmp_path / "config.json"
        path.write_text(json.dumps({"token": "stored", "endpoint": "https://openrouter.ai/api/alpha/decisions"}))
        result = read_user_config(path)
        assert isinstance(result, UserConfig)
        assert result.token == "stored"
        assert result.endpoint == "https://openrouter.ai/api/alpha/decisions"


# ---------------------------------------------------------------------------
# Unset empty file removal
# ---------------------------------------------------------------------------


class TestRemoveUserConfig:
    def test_removes_file(self, tmp_path) -> None:
        path = tmp_path / "config.json"
        path.write_text('{"token":"x","endpoint":"https://openrouter.ai/api/alpha/decisions"}')
        remove_user_config(path)
        assert not path.exists()

    def test_noop_when_missing(self, tmp_path) -> None:
        path = tmp_path / "config.json"
        remove_user_config(path)
        assert not path.exists()

    def test_cleans_empty_parent_dir(self, tmp_path) -> None:
        config_dir = tmp_path / "jev-poc"
        config_dir.mkdir()
        path = config_dir / "config.json"
        path.write_text('{"token":"x","endpoint":"https://openrouter.ai/api/alpha/decisions"}')
        remove_user_config(path)
        assert not config_dir.exists()

    def test_keeps_parent_with_other_files(self, tmp_path) -> None:
        config_dir = tmp_path / "jev-poc"
        config_dir.mkdir()
        path = config_dir / "config.json"
        path.write_text('{"token":"x","endpoint":"https://openrouter.ai/api/alpha/decisions"}')
        other = config_dir / "other.txt"
        other.write_text("stuff")
        remove_user_config(path)
        assert config_dir.exists()
        assert other.exists()


# ---------------------------------------------------------------------------
# Load precedence — env/dotenv ahead of store
# ---------------------------------------------------------------------------


class TestLoadPrecedence:
    def test_env_token_overrides_store(
        self, monkeypatch, tmp_path
    ) -> None:
        """Nonblank env token should shadow config_store."""
        monkeypatch.setenv("JEV_API_TOKEN", "env-token")

        config_dir = tmp_path / ".config" / "jev-poc"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "config.json"
        config_path.write_text(
            json.dumps({"token": "stored", "endpoint": "https://openrouter.ai/api/alpha/decisions"})
        )

        with patch("jev_bot.config.get_config_path", return_value=config_path):
            config = load_config()

        assert config.token == "env-token"

    def test_blank_env_falls_through_to_store(
        self, monkeypatch, tmp_path
    ) -> None:
        """Blank env token should fall through to config_store."""
        monkeypatch.setenv("JEV_API_TOKEN", "   ")

        config_dir = tmp_path / ".config" / "jev-poc"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "config.json"
        config_path.write_text(
            json.dumps({"token": "stored", "endpoint": "https://openrouter.ai/api/alpha/decisions"})
        )

        with patch("jev_bot.config.get_config_path", return_value=config_path):
            config = load_config()

        assert config.token == "stored"

    def test_no_store_no_env_raises(
        self, monkeypatch, tmp_path
    ) -> None:
        """Neither env nor store → error."""
        monkeypatch.delenv("JEV_API_TOKEN", raising=False)
        # Prevent dotenv from loading the project .env file
        monkeypatch.setattr(
            "jev_bot.config.load_dotenv",
            lambda **kwargs: None,
        )

        with patch("jev_bot.config.get_config_path", return_value=tmp_path / "nope.json"):
            with pytest.raises(EnvironmentError, match="JEV_API_TOKEN"):
                load_config()


# ---------------------------------------------------------------------------
# Malformed JSON — non-dict root / wrong value types → safe ValueError
# ---------------------------------------------------------------------------


class TestMalformedConfig:
    """Any valid JSON with wrong shape must produce a safe ValueError."""

    def test_list_root_raises(self, tmp_path) -> None:
        path = tmp_path / "config.json"
        path.write_text("[1, 2, 3]")
        with pytest.raises(ValueError, match="malformed"):
            read_user_config(path)

    def test_string_root_raises(self, tmp_path) -> None:
        path = tmp_path / "config.json"
        path.write_text('"hello"')
        with pytest.raises(ValueError, match="malformed"):
            read_user_config(path)

    def test_number_root_raises(self, tmp_path) -> None:
        path = tmp_path / "config.json"
        path.write_text("42")
        with pytest.raises(ValueError, match="malformed"):
            read_user_config(path)

    def test_null_root_raises(self, tmp_path) -> None:
        path = tmp_path / "config.json"
        path.write_text("null")
        with pytest.raises(ValueError, match="malformed"):
            read_user_config(path)

    def test_bool_root_raises(self, tmp_path) -> None:
        path = tmp_path / "config.json"
        path.write_text("true")
        with pytest.raises(ValueError, match="malformed"):
            read_user_config(path)

    def test_non_string_token_raises(self, tmp_path) -> None:
        path = tmp_path / "config.json"
        path.write_text(
            json.dumps(
                {"token": 123, "endpoint": "https://openrouter.ai/api/alpha/decisions"}
            )
        )
        with pytest.raises(ValueError, match="malformed"):
            read_user_config(path)

    def test_non_string_endpoint_raises(self, tmp_path) -> None:
        path = tmp_path / "config.json"
        path.write_text(
            json.dumps({"token": "abc", "endpoint": 456})
        )
        with pytest.raises(ValueError, match="malformed"):
            read_user_config(path)

    def test_non_string_both_raises(self, tmp_path) -> None:
        path = tmp_path / "config.json"
        path.write_text(json.dumps({"token": 123, "endpoint": 456}))
        with pytest.raises(ValueError, match="malformed"):
            read_user_config(path)
