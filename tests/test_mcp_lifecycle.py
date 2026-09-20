"""Tests for MCP server lifecycle — classification, install, uninstall (Task 3).

Install defaults to the audit-first SQLite opt-in (``db_enable=True``): the
desired entry is the *enabled* canonical shape written at the scope-resolved
database path, and managed entries (disabled or enabled-at-another-path)
migrate in place without ``force``.  Tests mirror the implementation by
building expectations through :func:`resolve_sqlite_db_path` with the same
scope kwargs passed to ``install_server`` — never by hardcoding
symlink-resolved paths (macOS ``/var`` -> ``/private/var``).
"""

from __future__ import annotations

import json

import pytest
from pathlib import Path

from jev_bot.investigation_logging import resolve_sqlite_db_path
from jev_bot.mcp_registration import (
    HARNESSES,
    REGISTRY,
    RegistrationResult,
    RegistrationStatus,
    ServerEntryState,
    _get_nested,
    _del_nested,
    classify_server_entry,
    install_server,
    uninstall_server,
    canonical_entry,
    read_config,
    registration_target,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _fixture_project(tmp_path: Path, name: str) -> Path:
    """Create a named project directory."""
    d = tmp_path / name
    d.mkdir()
    return d


def _fixture_user_home(tmp_path: Path, name: str) -> Path:
    """Create a named user-home directory."""
    d = tmp_path / name
    d.mkdir()
    return d


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _expected_enabled(
    harness: str,
    *,
    project: Path | None = None,
    home: Path | None = None,
    xdg: Path | None = None,
) -> dict:
    """Build the entry ``install_server(harness, project_root=project|user_home=home)``
    must write under the audit-first default (``db_enable=True``).

    The expectation mirrors the implementation exactly: the enabled canonical
    entry at :func:`resolve_sqlite_db_path` for the same scope kwargs.  For
    user scope, *xdg* deterministically simulates ``XDG_DATA_HOME``; when it
    is ``None`` the resolver's fallback (``home/.local/share``) is expected,
    and the autouse fixture below guarantees ``XDG_DATA_HOME`` is unset so
    the process environment cannot leak in.
    """
    environ = {} if xdg is None else {"XDG_DATA_HOME": str(xdg)}
    db_path = resolve_sqlite_db_path(
        project_root=project, user_home=home, environ=environ
    )
    return canonical_entry(harness, db_enable=True, sqlite_db_path=db_path)


def _launcher_list(entry: dict) -> list[str]:
    """Return the list-form launcher field of an entry (args or opencode command)."""
    for key in ("args", "command"):
        value = entry.get(key)
        if isinstance(value, list):
            return value
    raise AssertionError(f"entry has no list-form launcher field: {entry!r}")


@pytest.fixture(autouse=True)
def _pin_xdg_data_home_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deterministically clear XDG_DATA_HOME for every test.

    ``install_server`` resolves the user-scope default through the process
    environment; dev machines may set XDG_DATA_HOME, so the audit-first
    default tests clear it here and expect the ``.local/share`` fallback.
    """
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)


# ── 1. Server-entry classification ──────────────────────────────────


class TestClassifyAbsent:
    """classify returns 'absent' when config file does not exist."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_config_file_missing(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        assert classify_server_entry(harness, config_path, stop_root=project) == ServerEntryState.ABSENT


class TestClassifyCanonical:
    """classify returns 'canonical' when a jev entry matches the harness spec."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        # Legacy disabled canonical (explicit opt-out shape) — still JEV-owned,
        # the classifier owns both managed variants, so still CANONICAL.
        canonical = canonical_entry(harness, db_enable=False)
        keys = scopes.server_path.split(".")
        # Build nested structure
        data: dict = {}
        cur = data
        for key in keys[:-1]:
            cur[key] = {}
            cur = cur[key]
        cur[keys[-1]] = canonical
        _write_json(config_path, data)
        assert classify_server_entry(harness, config_path, stop_root=project) == ServerEntryState.CANONICAL


class TestClassifyForeign:
    """classify returns 'foreign' when a jev entry exists but differs from canonical."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        # Write a non-canonical entry (different type)
        data: dict = {}
        cur = data
        for key in keys[:-1]:
            cur[key] = {}
            cur = cur[key]
        cur[keys[-1]] = {"type": "websocket", "url": "https://example.com"}
        _write_json(config_path, data)
        assert classify_server_entry(harness, config_path, stop_root=project) == ServerEntryState.FOREIGN


class TestClassifyUserScope:
    """Classify works for user-scope paths (e.g. .claude.json, .omp/agent/mcp.json)."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_user_scope(self, tmp_path: Path, harness: str) -> None:
        home = _fixture_user_home(tmp_path, harness)
        scopes = registration_target(harness).user
        config_path = home / scopes.path_key
        # Absent case — user scope file does not exist yet
        assert classify_server_entry(harness, config_path, stop_root=home) == ServerEntryState.ABSENT


# ── 2. Install ──────────────────────────────────────────────────────


class TestInstallAbsent:
    """Install writes the enabled canonical entry when the server entry is absent."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key

        result_path = install_server(harness, project_root=project)

        assert result_path.path == config_path
        assert config_path.exists()
        data = json.loads(config_path.read_text())
        entry = data
        for key in scopes.server_path.split("."):
            entry = entry[key]
        assert entry == _expected_enabled(harness, project=project)


class TestInstallAbsentCreatesParentDirs:
    """Install creates intermediate directories when the config file's parent does not exist."""

    @pytest.mark.parametrize("harness", ["oh-my-pi", "pi"])
    def test_deep_nested_scope(self, tmp_path: Path, harness: str) -> None:
        """Test harnesses with nested user paths like '.omp/agent/mcp.json'."""
        home = _fixture_user_home(tmp_path, harness)
        scopes = registration_target(harness).user
        config_path = home / scopes.path_key
        # Parent dir does NOT exist
        assert not config_path.parent.exists()

        result_path = install_server(harness, user_home=home)

        assert result_path.path == config_path
        assert config_path.parent.exists()
        assert config_path.exists()


class TestInstallAbsentPreservesExistingContent:
    """Install in ABSENT state must NOT overwrite existing sibling keys.

    Regression test: when the config file already exists with other content
    (but the jev key is absent), install must read the file, set only the jev
    nested key, and write back — preserving every other top-level key.
    """

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        # Config exists with top-level siblings but no jev key
        data: dict = {
            "plugins": {"foo": True},
            "someOtherServer": {"type": "stdio", "command": "echo hello"},
        }
        _write_json(config_path, data)

        install_server(harness, project_root=project)

        data_after = json.loads(config_path.read_text())
        # Siblings preserved
        assert data_after.get("plugins") == {"foo": True}
        assert data_after.get("someOtherServer") == {
            "type": "stdio",
            "command": "echo hello",
        }
        # jev key is now present and enabled at the resolved path
        entry = data_after
        for key in keys:
            entry = entry[key]
        assert entry == _expected_enabled(harness, project=project)

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_user_scope(self, tmp_path: Path, harness: str) -> None:
        home = _fixture_user_home(tmp_path, harness)
        scopes = registration_target(harness).user
        config_path = home / scopes.path_key
        keys = scopes.server_path.split(".")
        data: dict = {"plugins": {"bar": 42}}
        _write_json(config_path, data)

        install_server(harness, user_home=home)

        data_after = json.loads(config_path.read_text())
        assert data_after.get("plugins") == {"bar": 42}
        entry = data_after
        for key in keys:
            entry = entry[key]
        assert entry == _expected_enabled(harness, home=home)


class TestInstallCanonicalNoOp:
    """Install is a no-op when the entry already equals the desired entry,
    and migrates an older managed variant without force."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        """Seed the EXACT enabled-at-resolved entry → EXISTS, content unchanged."""
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        canonical = _expected_enabled(harness, project=project)
        data: dict = {}
        cur = data
        keys = scopes.server_path.split(".")
        for key in keys[:-1]:
            cur[key] = {}
            cur = cur[key]
        cur[keys[-1]] = canonical
        _write_json(config_path, data)

        result_path = install_server(harness, project_root=project)

        assert result_path.path == config_path
        # Content unchanged — still the enabled canonical entry
        data_after = json.loads(config_path.read_text())
        entry = data_after
        for key in keys:
            entry = entry[key]
        assert entry == canonical

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_managed_migration_without_force(self, tmp_path: Path, harness: str) -> None:
        """A legacy disabled managed entry migrates to enabled without force → REPLACED."""
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        # Seed the historical disabled shape (no --sqlite-db args).
        data: dict = {}
        cur = data
        for key in keys[:-1]:
            cur[key] = {}
            cur = cur[key]
        cur[keys[-1]] = canonical_entry(harness, db_enable=False)
        _write_json(config_path, data)

        result = install_server(harness, project_root=project)

        assert result.status is RegistrationStatus.REPLACED
        assert result.path == config_path
        data_after = json.loads(config_path.read_text())
        entry = data_after
        for key in keys:
            entry = entry[key]
        assert entry == _expected_enabled(harness, project=project)


class TestInstallForeignRefuses:
    """Install refuses to overwrite a foreign entry without force=True."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        data: dict = {}
        cur = data
        for key in keys[:-1]:
            cur[key] = {}
            cur = cur[key]
        cur[keys[-1]] = {"type": "websocket", "url": "https://evil.com"}
        _write_json(config_path, data)

        with pytest.raises(ValueError, match="Refusing to install"):
            install_server(harness, project_root=project)


class TestInstallForeignForce:
    """Install with force=True replaces only the jev key, preserving siblings."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        # Write a foreign jev entry plus a sibling entry
        data: dict = {}
        cur = data
        for key in keys[:-1]:
            cur[key] = {}
            cur = cur[key]
        cur[keys[-1]] = {"type": "websocket", "url": "https://foreign.com"}
        data["someOtherServer"] = {"type": "stdio", "command": "other"}
        _write_json(config_path, data)

        result_path = install_server(harness, project_root=project, force=True)

        assert result_path.path == config_path
        data_after = json.loads(config_path.read_text())
        # Sibling preserved
        assert data_after.get("someOtherServer") == {"type": "stdio", "command": "other"}
        # jev is now the enabled canonical entry
        entry = data_after
        for key in keys:
            entry = entry[key]
        assert entry == _expected_enabled(harness, project=project)


class TestInstallUserScope:
    """Install works for user-scope config paths."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_user_scope(self, tmp_path: Path, harness: str) -> None:
        home = _fixture_user_home(tmp_path, harness)
        scopes = registration_target(harness).user
        config_path = home / scopes.path_key

        result_path = install_server(harness, user_home=home)

        assert result_path.path == config_path
        assert config_path.exists()
        data_after = json.loads(config_path.read_text())
        entry = data_after
        for key in scopes.server_path.split("."):
            entry = entry[key]
        assert entry == _expected_enabled(harness, home=home)

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_user_scope_honours_xdg_data_home(self, tmp_path: Path, harness: str, monkeypatch: pytest.MonkeyPatch) -> None:
        """A set XDG_DATA_HOME redirects the enabled entry's database path."""
        home = _fixture_user_home(tmp_path, harness)
        xdg = tmp_path / f"{harness}-xdg"
        monkeypatch.setenv("XDG_DATA_HOME", str(xdg))
        scopes = registration_target(harness).user
        config_path = home / scopes.path_key

        install_server(harness, user_home=home)

        data_after = json.loads(config_path.read_text())
        entry = data_after
        for key in scopes.server_path.split("."):
            entry = entry[key]
        assert entry == _expected_enabled(harness, home=home, xdg=xdg)


class TestInstallInvalidHarness:
    """Install raises ValueError for unknown harnesses."""

    def test_project_scope(self, tmp_path: Path) -> None:
        project = _fixture_project(tmp_path, "unknown")
        with pytest.raises(ValueError, match="not a recognized"):
            install_server("bogus-harness", project_root=project)


class TestInstallScopeValidation:
    """Install requires exactly one of project_root or user_home."""

    def test_neither(self) -> None:
        with pytest.raises(ValueError, match="Exactly one"):
            install_server("claude-code")

    def test_both(self, tmp_path: Path) -> None:
        project = _fixture_project(tmp_path, "proj")
        home = _fixture_user_home(tmp_path, "home")
        with pytest.raises(ValueError, match="not both"):
            install_server("claude-code", project_root=project, user_home=home)


# ── 3. Uninstall ────────────────────────────────────────────────────


class TestUninstallCanonical:
    """Uninstall removes the canonical jev entry."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        # Legacy disabled managed variant — the classifier owns both shapes.
        canonical = canonical_entry(harness, db_enable=False)
        data: dict = {}
        cur = data
        keys = scopes.server_path.split(".")
        for key in keys[:-1]:
            cur[key] = {}
            cur = cur[key]
        cur[keys[-1]] = canonical
        _write_json(config_path, data)

        result_path = uninstall_server(harness, project_root=project)

        assert result_path.path == config_path
        data_after = read_config(config_path, stop_root=project)
        assert _get_nested(data_after, keys) is None

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_uninstall_removes_enabled_managed_variant(self, tmp_path: Path, harness: str) -> None:
        """The enabled (--sqlite-db) managed variant is removed too; the config
        file is retained and recording data is never touched."""
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        enabled = _expected_enabled(harness, project=project)
        db_path = resolve_sqlite_db_path(project_root=project)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.write_bytes(b"recording-data")
        data: dict = {}
        cur = data
        for key in keys[:-1]:
            cur[key] = {}
            cur = cur[key]
        cur[keys[-1]] = enabled
        _write_json(config_path, data)

        result = uninstall_server(harness, project_root=project)

        assert result.status is RegistrationStatus.REMOVED
        assert result.path == config_path
        data_after = read_config(config_path, stop_root=project)
        assert _get_nested(data_after, keys) is None
        assert config_path.exists()
        # Recording data survives the uninstall.
        assert db_path.read_bytes() == b"recording-data"


class TestUninstallRetainsEmptyConfig:
    """Uninstall retains the config file even when it becomes empty (Task 3 contract)."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        canonical = canonical_entry(harness, db_enable=False)
        keys = scopes.server_path.split(".")
        data: dict = {}
        cur = data
        for key in keys[:-1]:
            cur[key] = {}
            cur = cur[key]
        cur[keys[-1]] = canonical
        _write_json(config_path, data)

        uninstall_server(harness, project_root=project)

        # File is retained but empty
        assert config_path.exists()
        assert read_config(config_path, stop_root=project) == {}


class TestUninstallForeignNoMutation:
    """Uninstall does not mutate a foreign entry; returns the config path."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        data: dict = {}
        cur = data
        for key in keys[:-1]:
            cur[key] = {}
            cur = cur[key]
        cur[keys[-1]] = {"type": "websocket", "url": "https://foreign.com"}
        _write_json(config_path, data)

        result_path = uninstall_server(harness, project_root=project)

        assert result_path.path == config_path
        assert config_path.exists()
        # Foreign entry is still there
        data_after = read_config(config_path, stop_root=project)
        entry = data_after
        for key in keys:
            entry = entry[key]
        assert entry == {"type": "websocket", "url": "https://foreign.com"}

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_enabled_with_extra_args_is_foreign(self, tmp_path: Path, harness: str) -> None:
        """An enabled-looking launcher with extra tokens beyond the SQLite pair
        is FOREIGN and must not be removed."""
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        entry = _expected_enabled(harness, project=project)
        _launcher_list(entry).append("--verbose")
        data: dict = {}
        cur = data
        for key in keys[:-1]:
            cur[key] = {}
            cur = cur[key]
        cur[keys[-1]] = entry
        _write_json(config_path, data)

        result = uninstall_server(harness, project_root=project)

        assert result.status is RegistrationStatus.FOREIGN
        data_after = read_config(config_path, stop_root=project)
        assert _get_nested(data_after, keys) == entry

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_enabled_with_reordered_suffix_is_foreign(self, tmp_path: Path, harness: str) -> None:
        """`--sqlite-db` tokens reordered (flag after a stray token) is FOREIGN
        and must not be removed."""
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        entry = _expected_enabled(harness, project=project)
        launcher = _launcher_list(entry)
        # Swap the trailing [flag, path] pair into [path, flag] order.
        launcher[-2], launcher[-1] = launcher[-1], launcher[-2]
        data: dict = {}
        cur = data
        for key in keys[:-1]:
            cur[key] = {}
            cur = cur[key]
        cur[keys[-1]] = entry
        _write_json(config_path, data)

        result = uninstall_server(harness, project_root=project)

        assert result.status is RegistrationStatus.FOREIGN
        data_after = read_config(config_path, stop_root=project)
        assert _get_nested(data_after, keys) == entry


class TestUninstallAbsentNoOp:
    """Uninstall is a no-op when the jev entry is absent."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        assert not config_path.exists()

        result_path = uninstall_server(harness, project_root=project)

        assert result_path.path == config_path
        assert not config_path.exists()


class TestUninstallUserScope:
    """Uninstall works for user-scope config paths."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_user_scope(self, tmp_path: Path, harness: str) -> None:
        home = _fixture_user_home(tmp_path, harness)
        scopes = registration_target(harness).user
        config_path = home / scopes.path_key
        canonical = canonical_entry(harness, db_enable=False)
        keys = scopes.server_path.split(".")
        data: dict = {}
        cur = data
        for key in keys[:-1]:
            cur[key] = {}
            cur = cur[key]
        cur[keys[-1]] = canonical
        _write_json(config_path, data)

        result_path = uninstall_server(harness, user_home=home)

        assert result_path.path == config_path
        assert config_path.exists()  # still exists, just jev removed
        data_after = read_config(config_path, stop_root=home)
        assert _get_nested(data_after, keys) is None


class TestUninstallInvalidHarness:
    """Uninstall raises ValueError for unknown harnesses."""

    def test_project_scope(self, tmp_path: Path) -> None:
        project = _fixture_project(tmp_path, "unknown")
        with pytest.raises(ValueError, match="not a recognized"):
            uninstall_server("bogus-harness", project_root=project)


class TestUninstallScopeValidation:
    """Uninstall requires exactly one of project_root or user_home."""

    def test_neither(self) -> None:
        with pytest.raises(ValueError, match="Exactly one"):
            uninstall_server("claude-code")

    def test_both(self, tmp_path: Path) -> None:
        project = _fixture_project(tmp_path, "proj")
        home = _fixture_user_home(tmp_path, "home")
        with pytest.raises(ValueError, match="not both"):
            uninstall_server("claude-code", project_root=project, user_home=home)


# ── 3b. Malformed / non-dict server-path values ──────────────────────


class _BuildPath:
    """Helper to build nested dicts following a dotted server_path."""

    @staticmethod
    def set(data: dict, keys: list[str]) -> dict:
        """Set keys[-1] inside nested dicts along *keys*."""
        cur = data
        for key in keys[:-1]:
            cur.setdefault(key, {})
            cur = cur[key]
        # Set leaf at deepest level (for use in tests)
        return cur

    @staticmethod
    def set_leaf(data: dict, keys: list[str], value: object) -> None:
        """Set the leaf value at the deepest nested dict."""
        cur = data
        for key in keys[:-1]:
            cur.setdefault(key, {})
            cur = cur[key]
        cur[keys[-1]] = value


class TestMalformedNullLeaf:
    """A null (None) leaf at the jev position is classified FOREIGN."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        data: dict = {}
        _BuildPath.set_leaf(data, keys, None)  # null leaf
        _write_json(config_path, data)

        assert classify_server_entry(harness, config_path, stop_root=project) == ServerEntryState.FOREIGN


class TestMalformedStringLeaf:
    """A string leaf at the jev position is classified FOREIGN."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        data: dict = {}
        _BuildPath.set_leaf(data, keys, "not-a-dict")
        _write_json(config_path, data)

        assert classify_server_entry(harness, config_path, stop_root=project) == ServerEntryState.FOREIGN


class TestMalformedListLeaf:
    """A list leaf at the jev position is classified FOREIGN."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        data: dict = {}
        _BuildPath.set_leaf(data, keys, [1, 2, 3])
        _write_json(config_path, data)

        assert classify_server_entry(harness, config_path, stop_root=project) == ServerEntryState.FOREIGN


class TestMalformedNonDictIntermediate:
    """A non-dict value on an intermediate path key is classified FOREIGN."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        """For multi-key paths like 'mcp.servers.jev', corrupting
        an intermediate (e.g. 'mcp' = "bad") makes the whole path FOREIGN."""
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        if len(keys) <= 1:
            pytest.skip("single-key path; intermediate corruption not applicable")
        data: dict = {}
        # Set only the first key to a non-dict
        data[keys[0]] = "not-a-dict"
        _write_json(config_path, data)

        assert classify_server_entry(harness, config_path, stop_root=project) == ServerEntryState.FOREIGN


class TestInstallWithMalformedNull:
    """Normal install on null leaf preserves existing siblings, errors on jev replacement."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        data: dict = {}
        _BuildPath.set_leaf(data, keys, None)
        data["other"] = {"a": 1}
        _write_json(config_path, data)

        # classify says FOREIGN → normal install raises, does NOT mutate
        with pytest.raises(ValueError, match="Refusing to install"):
            install_server(harness, project_root=project)

        # Siblings intact
        assert read_config(config_path, stop_root=project).get("other") == {"a": 1}

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_force_replaces_only_jev(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        data: dict = {}
        _BuildPath.set_leaf(data, keys, None)
        data["sibling"] = {"b": 2}
        _write_json(config_path, data)

        install_server(harness, project_root=project, force=True)

        # jev is now the enabled canonical entry
        data_after = read_config(config_path, stop_root=project)
        entry = data_after
        for key in keys:
            entry = entry[key]
        assert entry == _expected_enabled(harness, project=project)
        # sibling preserved
        assert data_after.get("sibling") == {"b": 2}


class TestInstallWithMalformedStringLeaf:
    """Normal install on string leaf preserves siblings, errors on jev replacement."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        data: dict = {}
        _BuildPath.set_leaf(data, keys, "corrupted")
        data["keep"] = True
        _write_json(config_path, data)

        with pytest.raises(ValueError, match="Refusing to install"):
            install_server(harness, project_root=project)

        data_after = read_config(config_path, stop_root=project)
        assert data_after.get("keep") is True


class TestInstallWithMalformedListLeaf:
    """Normal install on list leaf preserves siblings, errors on jev replacement."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        data: dict = {}
        _BuildPath.set_leaf(data, keys, [1, 2])
        data["sibling"] = {"x": "y"}
        _write_json(config_path, data)

        with pytest.raises(ValueError, match="Refusing to install"):
            install_server(harness, project_root=project)

        data_after = read_config(config_path, stop_root=project)
        assert data_after.get("sibling") == {"x": "y"}

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_force_replaces_only_jev(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        data: dict = {}
        _BuildPath.set_leaf(data, keys, [1, 2])
        data["sibling"] = {"x": "y"}
        _write_json(config_path, data)

        install_server(harness, project_root=project, force=True)

        data_after = read_config(config_path, stop_root=project)
        entry = data_after
        for key in keys:
            entry = entry[key]
        assert entry == _expected_enabled(harness, project=project)
        assert data_after.get("sibling") == {"x": "y"}


class TestInstallWithMalformedNonDictIntermediate:
    """Normal install on non-dict intermediate preserves siblings, errors on jev replacement."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        if len(keys) <= 1:
            pytest.skip("single-key path")
        data: dict = {}
        data[keys[0]] = {}  # first level is a dict (to be traversable)
        data[keys[0]][keys[1]] = "corrupted"  # but the second key is non-dict
        data["sibling"] = {"z": 0}
        _write_json(config_path, data)

        with pytest.raises(ValueError, match="Refusing to install"):
            install_server(harness, project_root=project)

        data_after = read_config(config_path, stop_root=project)
        assert data_after.get("sibling") == {"z": 0}


class TestInstallWithMalformedNullForce:
    """Force install on null leaf replaces only jev, preserves siblings."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        data: dict = {}
        _BuildPath.set_leaf(data, keys, None)
        data["sibling"] = {"s": 1}
        _write_json(config_path, data)

        install_server(harness, project_root=project, force=True)

        data_after = read_config(config_path, stop_root=project)
        entry = data_after
        for key in keys:
            entry = entry[key]
        assert entry == _expected_enabled(harness, project=project)
        assert data_after.get("sibling") == {"s": 1}


# ── 4. Install ↔ Uninstall round-trip ──────────────────────────────


class TestInstallUninstallRoundTrip:
    """Install then uninstall returns to the original absent state."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key

        install_server(harness, project_root=project)
        assert classify_server_entry(harness, config_path, stop_root=project) == ServerEntryState.CANONICAL

        uninstall_server(harness, project_root=project)
        assert classify_server_entry(harness, config_path, stop_root=project) == ServerEntryState.ABSENT


class TestInstallUninstallUserRoundTrip:
    """Install then uninstall on user scope returns to absent."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_user_scope(self, tmp_path: Path, harness: str) -> None:
        home = _fixture_user_home(tmp_path, harness)
        scopes = registration_target(harness).user
        config_path = home / scopes.path_key

        install_server(harness, user_home=home)
        assert classify_server_entry(harness, config_path, stop_root=home) == ServerEntryState.CANONICAL

        uninstall_server(harness, user_home=home)
        assert classify_server_entry(harness, config_path, stop_root=home) == ServerEntryState.ABSENT


# ── 5. Stop-root boundary ──────────────────────────────────────────


class TestStopRootBoundary:
    """Config operations use explicit stop_root, not cwd or home."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_explicit_stop_root_project(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key

        install_server(harness, project_root=project)

        # Config was written to the explicit stop_root boundary
        assert config_path.exists()


# ── 6. Sibling server entries preserved ────────────────────────────


class TestSiblingPreservation:
    """Install/uninstall preserves sibling server entries in the config."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_siblings_preserved_after_install(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        data: dict = {}
        cur = data
        for key in keys[:-1]:
            cur[key] = {}
            cur = cur[key]
        cur[keys[-1]] = {"type": "websocket", "url": "https://foreign.com"}
        data["sibling"] = {"transport": "stdio", "command": "echo hello"}
        _write_json(config_path, data)

        install_server(harness, project_root=project, force=True)

        data_after = read_config(config_path, stop_root=project)
        assert data_after.get("sibling") == {"transport": "stdio", "command": "echo hello"}


# ── 7. Import hygiene ──────────────────────────────────────────────


class TestModuleImports:
    """Ensure Task 3 adds no new imports from banned modules."""

    def test_no_new_external_imports(self) -> None:
        """The module should only import from stdlib, not new 3rd-party deps."""
        import jev_bot.mcp_registration as mod
        # Verify the module doesn't import typer, requests, mcp, dotenv, etc.
        import inspect
        source_lines = inspect.getsource(mod)
        for banned in ["typer", "requests", "mcp", "dotenv"]:
            assert f"import {banned}" not in source_lines, (
                f"mcp_registration.py should not import {banned}"
            )


# ── 8. RegistrationResult — installer integration (Task 4) ──────────


class TestInstallServerReturnsResult:
    """install_server returns a RegistrationResult, not a bare Path."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope_created(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key

        result = install_server(harness, project_root=project)

        assert isinstance(result, RegistrationResult)
        assert result.path == config_path
        assert result.status is RegistrationStatus.CREATED


class TestInstallServerCanonicalReturnsResult:
    """Audit-first round-trip: disabled seed migrates (REPLACED), a repeat
    default install is a no-op (EXISTS), uninstall removes it (REMOVED)."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        # Seed the legacy disabled managed shape.
        data: dict = {}
        cur = data
        for key in keys[:-1]:
            cur[key] = {}
            cur = cur[key]
        cur[keys[-1]] = canonical_entry(harness, db_enable=False)
        _write_json(config_path, data)

        migrate = install_server(harness, project_root=project)
        assert migrate.status is RegistrationStatus.REPLACED
        assert migrate.path == config_path
        data_after = json.loads(config_path.read_text())
        assert _get_nested(data_after, keys) == _expected_enabled(harness, project=project)

        again = install_server(harness, project_root=project)
        assert again.status is RegistrationStatus.EXISTS
        assert again.path == config_path
        assert json.loads(config_path.read_text()) == data_after

        removed = uninstall_server(harness, project_root=project)
        assert removed.status is RegistrationStatus.REMOVED
        assert removed.path == config_path
        assert _get_nested(read_config(config_path, stop_root=project), keys) is None


class TestInstallServerDisabledOptOutReturnsResult:
    """db_enable=False still targets the historical disabled canonical shape."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")

        result = install_server(harness, project_root=project, db_enable=False)

        assert result.status is RegistrationStatus.CREATED
        data_after = read_config(config_path, stop_root=project)
        assert _get_nested(data_after, keys) == canonical_entry(harness, db_enable=False)


class TestInstallServerForeignForceReturnsResult:
    """install_server with force=True on a foreign entry returns REPLACED."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        data: dict = {}
        cur = data
        for key in keys[:-1]:
            cur[key] = {}
            cur = cur[key]
        cur[keys[-1]] = {"type": "websocket", "url": "https://foreign.com"}
        _write_json(config_path, data)

        result = install_server(harness, project_root=project, force=True)

        assert result.status is RegistrationStatus.REPLACED
        assert result.path == config_path
        data_after = read_config(config_path, stop_root=project)
        assert _get_nested(data_after, keys) == _expected_enabled(harness, project=project)


class TestUninstallServerCanonicalReturnsResult:
    """uninstall_server on a canonical entry returns REMOVED."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        canonical = canonical_entry(harness, db_enable=False)
        keys = scopes.server_path.split(".")
        data: dict = {}
        cur = data
        for key in keys[:-1]:
            cur[key] = {}
            cur = cur[key]
        cur[keys[-1]] = canonical
        _write_json(config_path, data)

        result = uninstall_server(harness, project_root=project)

        assert result.status is RegistrationStatus.REMOVED
        assert result.path == config_path


class TestUninstallServerAbsentReturnsResult:
    """uninstall_server on an absent entry returns ABSENT."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key

        result = uninstall_server(harness, project_root=project)

        assert result.status is RegistrationStatus.ABSENT
        assert result.path == config_path


class TestUninstallServerForeignReturnsResult:
    """uninstall_server on a foreign entry returns FOREIGN without mutation."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        keys = scopes.server_path.split(".")
        data: dict = {}
        cur = data
        for key in keys[:-1]:
            cur[key] = {}
            cur = cur[key]
        cur[keys[-1]] = {"type": "websocket", "url": "https://foreign.com"}
        _write_json(config_path, data)

        result = uninstall_server(harness, project_root=project)

        assert result.status is RegistrationStatus.FOREIGN
        assert result.path == config_path
        # Foreign content still intact — read the leaf key from the nested structure.
        data_after = read_config(config_path, stop_root=project)
        entry = data_after
        for k in keys:
            entry = entry[k]  # type: ignore[index]
        assert entry == {"type": "websocket", "url": "https://foreign.com"}
