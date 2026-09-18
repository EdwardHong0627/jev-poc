"""Tests for MCP server lifecycle — classification, install, uninstall (Task 3)."""

from __future__ import annotations

import json

import pytest
from pathlib import Path

from jev_bot.mcp_registration import (
    HARNESSES,
    REGISTRY,
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
        canonical = canonical_entry(harness)
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
    """Install writes canonical entry when the server entry is absent."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key

        result_path = install_server(harness, project_root=project)

        assert result_path == config_path
        assert config_path.exists()
        data = json.loads(config_path.read_text())
        entry = data
        for key in scopes.server_path.split("."):
            entry = entry[key]
        assert entry == canonical_entry(harness)


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

        assert result_path == config_path
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
        # jev key is now present and canonical
        entry = data_after
        for key in keys:
            entry = entry[key]
        assert entry == canonical_entry(harness)

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
        assert entry == canonical_entry(harness)


class TestInstallCanonicalNoOp:
    """Install is a no-op when the server entry is already canonical."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        canonical = canonical_entry(harness)
        data: dict = {}
        cur = data
        keys = scopes.server_path.split(".")
        for key in keys[:-1]:
            cur[key] = {}
            cur = cur[key]
        cur[keys[-1]] = canonical
        _write_json(config_path, data)

        result_path = install_server(harness, project_root=project)

        assert result_path == config_path
        # Content unchanged — still canonical
        data_after = json.loads(config_path.read_text())
        entry = data_after
        for key in keys:
            entry = entry[key]
        assert entry == canonical


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

        assert result_path == config_path
        data_after = json.loads(config_path.read_text())
        # Sibling preserved
        assert data_after.get("someOtherServer") == {"type": "stdio", "command": "other"}
        # jev is now canonical
        entry = data_after
        for key in keys:
            entry = entry[key]
        assert entry == canonical_entry(harness)


class TestInstallUserScope:
    """Install works for user-scope config paths."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_user_scope(self, tmp_path: Path, harness: str) -> None:
        home = _fixture_user_home(tmp_path, harness)
        scopes = registration_target(harness).user
        config_path = home / scopes.path_key

        result_path = install_server(harness, user_home=home)

        assert result_path == config_path
        assert config_path.exists()


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
        canonical = canonical_entry(harness)
        data: dict = {}
        cur = data
        keys = scopes.server_path.split(".")
        for key in keys[:-1]:
            cur[key] = {}
            cur = cur[key]
        cur[keys[-1]] = canonical
        _write_json(config_path, data)

        result_path = uninstall_server(harness, project_root=project)

        assert result_path == config_path
        data_after = read_config(config_path, stop_root=project)
        assert _get_nested(data_after, keys) is None


class TestUninstallRetainsEmptyConfig:
    """Uninstall retains the config file even when it becomes empty (Task 3 contract)."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        canonical = canonical_entry(harness)
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

        assert result_path == config_path
        assert config_path.exists()
        # Foreign entry is still there
        data_after = read_config(config_path, stop_root=project)
        entry = data_after
        for key in keys:
            entry = entry[key]
        assert entry == {"type": "websocket", "url": "https://foreign.com"}


class TestUninstallAbsentNoOp:
    """Uninstall is a no-op when the jev entry is absent."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_project_scope(self, tmp_path: Path, harness: str) -> None:
        project = _fixture_project(tmp_path, harness)
        scopes = registration_target(harness).project
        config_path = project / scopes.path_key
        assert not config_path.exists()

        result_path = uninstall_server(harness, project_root=project)

        assert result_path == config_path
        assert not config_path.exists()


class TestUninstallUserScope:
    """Uninstall works for user-scope config paths."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_user_scope(self, tmp_path: Path, harness: str) -> None:
        home = _fixture_user_home(tmp_path, harness)
        scopes = registration_target(harness).user
        config_path = home / scopes.path_key
        canonical = canonical_entry(harness)
        keys = scopes.server_path.split(".")
        data: dict = {}
        cur = data
        for key in keys[:-1]:
            cur[key] = {}
            cur = cur[key]
        cur[keys[-1]] = canonical
        _write_json(config_path, data)

        result_path = uninstall_server(harness, user_home=home)

        assert result_path == config_path
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

        # jev is now canonical
        data_after = read_config(config_path, stop_root=project)
        entry = data_after
        for key in keys:
            entry = entry[key]
        assert entry == canonical_entry(harness)
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
        assert entry == canonical_entry(harness)
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
        assert entry == canonical_entry(harness)
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
        source = """\
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from jev_bot.mcp_registration import (
    ...
)
"""
        # Verify the module doesn't import typer, requests, mcp, dotenv, etc.
        import inspect
        source_lines = inspect.getsource(mod)
        for banned in ["typer", "requests", "mcp", "dotenv"]:
            assert f"import {banned}" not in source_lines, (
                f"mcp_registration.py should not import {banned}"
            )
