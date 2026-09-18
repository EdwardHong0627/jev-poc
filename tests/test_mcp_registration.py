"""Tests for the MCP registration registry and canonical entries."""

from __future__ import annotations

import pytest

from jev_bot.mcp_registration import (
    HARNESSES,
    JEV_GIT_URL,
    REGISTRY,
    ScopeSpec,
    Scopes,
    canonical_entry,
    registration_target,
)


# ── Module-level constants ──────────────────────────────────────────

def test_registry_is_dict():
    assert isinstance(REGISTRY, dict)


def test_registry_contains_four_harnesses():
    assert set(REGISTRY) == {"claude-code", "opencode", "oh-my-pi", "pi"}


def test_all_harnesses_have_scopes():
    for harness, entry in REGISTRY.items():
        assert entry.scopes is not None
        assert isinstance(entry.scopes.project, ScopeSpec)
        assert isinstance(entry.scopes.user, ScopeSpec)


# ── registration_target ────────────────────────────────────────────

class TestRegistrationTarget:
    def test_rejects_unrecognized_harness(self) -> None:
        with pytest.raises(ValueError, match="not a recognized MCP harness"):
            registration_target("unknown-harness")

    def test_rejects_blank_harness(self) -> None:
        with pytest.raises(ValueError, match="not a recognized MCP harness"):
            registration_target("")

    def test_returns_scope_for_claude_code(self) -> None:
        scope = registration_target("claude-code")
        assert isinstance(scope, Scopes)

    def test_returns_scope_for_opencode(self) -> None:
        scope = registration_target("opencode")
        assert isinstance(scope, Scopes)

    def test_returns_scope_for_oh_my_pi(self) -> None:
        scope = registration_target("oh-my-pi")
        assert isinstance(scope, Scopes)

    def test_returns_scope_for_pi(self) -> None:
        scope = registration_target("pi")
        assert isinstance(scope, Scopes)


# ── Claude Code canonical entry ─────────────────────────────────────

class TestClaudeCodeEntry:
    """Canonical entry for Claude Code."""

    @pytest.fixture()
    def entry(self) -> dict:
        return canonical_entry("claude-code")

    def test_is_dict(self, entry: dict) -> None:
        assert isinstance(entry, dict)

    def test_type_is_stdio(self, entry: dict) -> None:
        assert entry["type"] == "stdio"

    def test_command_is_uv(self, entry: dict) -> None:
        assert entry["command"] == "uvx"

    def test_args_include_from(self, entry: dict) -> None:
        assert "--from" in entry["args"]

    def test_args_include_jev_mcp(self, entry: dict) -> None:
        assert "jev-mcp" in entry["args"]

    def test_git_url_is_constant(self, entry: dict) -> None:
        assert any("git+" in arg for arg in entry["args"])

    def test_no_token_or_endpoint(self, entry: dict) -> None:
        """No credential or endpoint information in the entry."""
        keys_flat = set()
        for v in entry.values():
            if isinstance(v, list):
                keys_flat.update(v)
            elif isinstance(v, str):
                keys_flat.update(v.split())
        assert not any(kw in keys_flat for kw in ["token", "api_key", "endpoint", "url"])

    def test_path_has_no_path_tokens(self, entry: dict) -> None:
        """Ensure the JSON structure itself has no path/token/endpoint."""
        assert isinstance(entry.get("args"), list)
        assert entry["command"] == "uvx"


class TestClaudeCodePathKeys:
    """Test the path key shape for Claude Code."""

    def test_has_project_path(self) -> None:
        spec = REGISTRY["claude-code"]
        assert spec.scopes.project.path_key.endswith(".mcp.json")

    def test_has_user_path(self) -> None:
        spec = REGISTRY["claude-code"]
        assert spec.scopes.user.path_key.endswith(".claude.json")


# ── OpenCode canonical entry ───────────────────────────────────────

class TestOpenCodeEntry:
    """Canonical entry for OpenCode."""

    @pytest.fixture()
    def entry(self) -> dict:
        return canonical_entry("opencode")

    def test_is_dict(self, entry: dict) -> None:
        assert isinstance(entry, dict)

    def test_type_is_local(self, entry: dict) -> None:
        assert entry["type"] == "local"

    def test_command_is_list(self, entry: dict) -> None:
        assert isinstance(entry["command"], list)
        assert entry["command"][0] == "uvx"

    def test_args_include_from(self, entry: dict) -> None:
        assert "--from" in entry["command"]

    def test_args_include_jev_mcp(self, entry: dict) -> None:
        assert "jev-mcp" in entry["command"]

    def test_no_token_or_endpoint(self) -> None:
        entry = canonical_entry("opencode")
        combined = " ".join(str(v) for v in entry.get("command", []))
        assert not any(kw in combined.lower() for kw in ["token", "api_key", "endpoint"])


class TestOpenCodePathKeys:
    """Test the path key shape for OpenCode."""

    def test_has_project_path(self) -> None:
        spec = REGISTRY["opencode"]
        assert spec.scopes.project.path_key.endswith("opencode.json")

    def test_has_user_path(self) -> None:
        spec = REGISTRY["opencode"]
        assert spec.scopes.user.path_key.endswith("opencode.json")


# ── Oh My Pi canonical entry ───────────────────────────────────────

class TestOhMyPiEntry:
    """Canonical entry for Oh My Pi."""

    @pytest.fixture()
    def entry(self) -> dict:
        return canonical_entry("oh-my-pi")

    def test_is_dict(self, entry: dict) -> None:
        assert isinstance(entry, dict)

    def test_type_is_stdio(self, entry: dict) -> None:
        assert entry["type"] == "stdio"

    def test_command_is_uv(self, entry: dict) -> None:
        assert entry["command"] == "uvx"

    def test_args_include_from(self, entry: dict) -> None:
        assert "--from" in entry["args"]

    def test_args_include_jev_mcp(self, entry: dict) -> None:
        assert "jev-mcp" in entry["args"]


class TestOhMyPiPathKeys:
    """Test the path key shape for Oh My Pi."""

    def test_has_project_path(self) -> None:
        spec = REGISTRY["oh-my-pi"]
        assert spec.scopes.project.path_key == ".omp/mcp.json"

    def test_has_user_path(self) -> None:
        spec = REGISTRY["oh-my-pi"]
        assert spec.scopes.user.path_key == ".omp/agent/mcp.json"


# ── Pi canonical entry ────────────────────────────────────────────

class TestPiEntry:
    """Canonical entry for Pi."""

    @pytest.fixture()
    def entry(self) -> dict:
        return canonical_entry("pi")

    def test_is_dict(self, entry: dict) -> None:
        assert isinstance(entry, dict)

    def test_transport_is_stdio(self, entry: dict) -> None:
        assert entry["transport"] == "stdio"

    def test_command_is_uv(self, entry: dict) -> None:
        assert entry["command"] == "uvx"

    def test_args_include_from(self, entry: dict) -> None:
        assert "--from" in entry["args"]

    def test_args_include_jev_mcp(self, entry: dict) -> None:
        assert "jev-mcp" in entry["args"]

    def test_lifecycle_is_lazy(self, entry: dict) -> None:
        assert entry["lifecycle"] == "lazy"


class TestPiPathKeys:
    """Test the path key shape for Pi."""

    def test_has_project_path(self) -> None:
        spec = REGISTRY["pi"]
        assert spec.scopes.project.path_key == ".pi/mcp.json"

    def test_has_user_path(self) -> None:
        spec = REGISTRY["pi"]
        assert spec.scopes.user.path_key == ".pi/agent/mcp.json"


# ── HARNESSES constant ──────────────────────────────────────────────

def test_harnesses_is_list():
    assert isinstance(HARNESSES, list)


def test_harnesses_contains_all_four():
    assert set(HARNESSES) == {"claude-code", "opencode", "oh-my-pi", "pi"}


# ── Error handling ──────────────────────────────────────────────────

class TestErrors:
    def test_canonical_entry_rejects_unknown_harness(self) -> None:
        with pytest.raises(ValueError, match="not a recognized MCP harness"):
            canonical_entry("unknown")

    def test_canonical_entry_rejects_blank(self) -> None:
        with pytest.raises(ValueError, match="not a recognized MCP harness"):
            canonical_entry("")


class TestCanonicalEntryDefensiveCopy:
    """canonical_entry must return a copy so callers cannot mutate shared data."""

    def test_mutation_does_not_affect_later_lookup(self) -> None:
        entry1 = canonical_entry("claude-code")
        entry1["type"] = "spoofed"
        entry1["args"].append("corrupted")
        entry2 = canonical_entry("claude-code")
        assert entry2["type"] == "stdio"
        assert "corrupted" not in entry2["args"]

    def test_mutation_does_not_affect_other_harnesses(self) -> None:
        entry = canonical_entry("claude-code")
        entry["type"] = "spoofed"
        other = canonical_entry("opencode")
        assert other["type"] == "local"

    def test_canonical_entry_returns_new_dict_each_call(self) -> None:
        entry1 = canonical_entry("pi")
        entry2 = canonical_entry("pi")
        assert entry1 is not entry2


# ── Specific path-key assertions ────────────────────────────────────

class TestSpecificPathKeys:
    """Assert exact path-key values per harness."""

    def test_claude_code_project_path_key(self) -> None:
        spec = REGISTRY["claude-code"]
        assert spec.scopes.project.path_key == ".mcp.json"

    def test_claude_code_user_path_key(self) -> None:
        spec = REGISTRY["claude-code"]
        assert spec.scopes.user.path_key == ".claude.json"

    def test_opencode_project_path_key(self) -> None:
        spec = REGISTRY["opencode"]
        assert spec.scopes.project.path_key == "opencode.json"

    def test_opencode_user_path_key(self) -> None:
        spec = REGISTRY["opencode"]
        assert spec.scopes.user.path_key == ".config/opencode/opencode.json"

    def test_oh_my_pi_project_path_key(self) -> None:
        spec = REGISTRY["oh-my-pi"]
        assert spec.scopes.project.path_key == ".omp/mcp.json"

    def test_oh_my_pi_user_path_key(self) -> None:
        spec = REGISTRY["oh-my-pi"]
        assert spec.scopes.user.path_key == ".omp/agent/mcp.json"

    def test_pi_project_path_key(self) -> None:
        spec = REGISTRY["pi"]
        assert spec.scopes.project.path_key == ".pi/mcp.json"

    def test_pi_user_path_key(self) -> None:
        spec = REGISTRY["pi"]
        assert spec.scopes.user.path_key == ".pi/agent/mcp.json"


# ── JEV_GIT_URL constant ────────────────────────────────────────────

def test_git_url_is_correct_repository() -> None:
    assert JEV_GIT_URL == "git+https://github.com/EdwardHong0627/jev-poc.git"


def test_git_url_used_in_claude_code_entry() -> None:
    entry = canonical_entry("claude-code")
    assert JEV_GIT_URL in entry["args"]


def test_git_url_used_in_opencode_entry() -> None:
    entry = canonical_entry("opencode")
    assert JEV_GIT_URL in entry["command"]


def test_git_url_used_in_oh_my_pi_entry() -> None:
    entry = canonical_entry("oh-my-pi")
    assert JEV_GIT_URL in entry["args"]


def test_git_url_used_in_pi_entry() -> None:
    entry = canonical_entry("pi")
    assert JEV_GIT_URL in entry["args"]


# ── server_path (full dotted JSON paths) ──────────────────────────────

class TestServerPath:
    """Assert every ScopeSpec's server_path is the full dotted JSON path."""

    def test_claude_code_project_server_path(self) -> None:
        spec = REGISTRY["claude-code"]
        assert spec.scopes.project.server_path == "mcpServers.jev"

    def test_claude_code_user_server_path(self) -> None:
        spec = REGISTRY["claude-code"]
        assert spec.scopes.user.server_path == "mcpServers.jev"

    def test_opencode_project_server_path(self) -> None:
        spec = REGISTRY["opencode"]
        assert spec.scopes.project.server_path == "mcp.servers.jev"

    def test_opencode_user_server_path(self) -> None:
        spec = REGISTRY["opencode"]
        assert spec.scopes.user.server_path == "mcp.servers.jev"

    def test_oh_my_pi_project_server_path(self) -> None:
        spec = REGISTRY["oh-my-pi"]
        assert spec.scopes.project.server_path == "mcpServers.jev"

    def test_oh_my_pi_user_server_path(self) -> None:
        spec = REGISTRY["oh-my-pi"]
        assert spec.scopes.user.server_path == "mcpServers.jev"

    def test_pi_project_server_path(self) -> None:
        spec = REGISTRY["pi"]
        assert spec.scopes.project.server_path == "mcpServers.jev"

    def test_pi_user_server_path(self) -> None:
        spec = REGISTRY["pi"]
        assert spec.scopes.user.server_path == "mcpServers.jev"

    def test_all_scope_specs_have_server_path(self) -> None:
        for harness in HARNESSES:
            spec = REGISTRY[harness]
            assert spec.scopes.project.server_path.endswith(".jev")
            assert spec.scopes.user.server_path.endswith(".jev")

    def test_opencode_server_path_has_dots(self) -> None:
        """OpenCode uses dotted nesting: mcp.servers.jev."""
        spec = REGISTRY["opencode"]
        assert "." in spec.scopes.project.server_path
        assert "." in spec.scopes.user.server_path

    def test_flat_harnesses_single_key(self) -> None:
        """Claude, OMP, Pi use a single JSON key (no dotted nesting)."""
        for harness in ("claude-code", "oh-my-pi", "pi"):
            spec = REGISTRY[harness]
            key = spec.scopes.project.server_path
            # Flat: exactly two dot-separated parts: <camelCase>.jev
            parts = key.split(".")
            assert len(parts) == 2
            assert parts[-1] == "jev"
            # The key part (before .jev) must be all-caps camelCase, no internal dots
            assert parts[0].isalnum()

    def test_all_server_paths_end_in_jev(self) -> None:
        """Every harness's server_path must end in `.jev`."""
        for harness in HARNESSES:
            spec = REGISTRY[harness]
            assert spec.scopes.project.server_path.endswith(".jev")
            assert spec.scopes.user.server_path.endswith(".jev")


class TestRegistrationTargetServerPath:
    """Assert server_path is reachable through registration_target()."""

    def test_project_server_path_via_registration_target(self) -> None:
        scopes = registration_target("claude-code")
        assert scopes.project.server_path == "mcpServers.jev"

    def test_user_server_path_via_registration_target(self) -> None:
        scopes = registration_target("opencode")
        assert scopes.user.server_path == "mcp.servers.jev"

    def test_all_harnesses_server_path_via_registration_target(self) -> None:
        for harness in HARNESSES:
            scopes = registration_target(harness)
            assert scopes.project.server_path.endswith(".jev")
            assert scopes.user.server_path.endswith(".jev")


class TestServerPathTupleComponents:
    """Assert server_path components split correctly."""

    def test_claude_code_flat_key(self) -> None:
        spec = REGISTRY["claude-code"]
        key = spec.scopes.project.server_path
        parts = key.split(".")
        assert parts[-1] == "jev"

    def test_opencode_nested_key(self) -> None:
        spec = REGISTRY["opencode"]
        key = spec.scopes.project.server_path
        parts = key.split(".")
        assert len(parts) == 3
        assert parts[-1] == "jev"
        assert parts[0] == "mcp"
        assert parts[1] == "servers"

    def test_oh_my_pi_flat_key(self) -> None:
        spec = REGISTRY["oh-my-pi"]
        key = spec.scopes.project.server_path
        parts = key.split(".")
        assert len(parts) == 2
        assert parts[0] == "mcpServers"
        assert parts[1] == "jev"

    def test_pi_flat_key(self) -> None:
        spec = REGISTRY["pi"]
        key = spec.scopes.project.server_path
        parts = key.split(".")
        assert len(parts) == 2
        assert parts[0] == "mcpServers"
        assert parts[1] == "jev"


# ── Task 2: read_config / write_config_atomic / symlink refusal ──────

class TestReadConfigMissing:
    """read_config returns {} when the file does not exist."""

    def test_returns_empty_dict(self, tmp_path) -> None:
        from jev_bot.mcp_registration import read_config

        missing = tmp_path / "no_such_file.json"
        stop_root = tmp_path
        result = read_config(missing, stop_root=stop_root)
        assert result == {}
        assert isinstance(result, dict)


class TestReadConfigValidJson:
    """read_config round-trips valid JSON objects through stop_root."""

    def test_roundtrip_single_key(self, tmp_path) -> None:
        from jev_bot.mcp_registration import read_config, write_config_atomic

        target = tmp_path / "config.json"
        stop_root = tmp_path
        original = {"mcpServers": {"jeo": {"type": "stdio"}}}
        write_config_atomic(target, original, stop_root=stop_root)
        result = read_config(target, stop_root=stop_root)
        assert result == original

    def test_preserves_nested_structure(self, tmp_path) -> None:
        from jev_bot.mcp_registration import read_config, write_config_atomic

        target = tmp_path / "nested.json"
        stop_root = tmp_path
        original = {
            "outer": {"inner": {"deep": 42, "list": [1, 2, 3]}},
            "top": "value",
        }
        write_config_atomic(target, original, stop_root=stop_root)
        result = read_config(target, stop_root=stop_root)
        assert result["outer"]["inner"]["deep"] == 42
        assert result["outer"]["inner"]["list"] == [1, 2, 3]
        assert result["top"] == "value"

    def test_roundtrip_empty_object(self, tmp_path) -> None:
        from jev_bot.mcp_registration import read_config, write_config_atomic

        target = tmp_path / "empty.json"
        stop_root = tmp_path
        original: dict = {}
        write_config_atomic(target, original, stop_root=stop_root)
        result = read_config(target, stop_root=stop_root)
        assert result == {}


class TestReadConfigMalformed:
    """read_config raises ValueError for malformed or non-object JSON."""

    def test_raises_on_array_json(self, tmp_path) -> None:
        from jev_bot.mcp_registration import read_config

        target = tmp_path / "array.json"
        stop_root = tmp_path
        target.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a JSON object"):
            read_config(target, stop_root=stop_root)

    def test_raises_on_string_json(self, tmp_path) -> None:
        from jev_bot.mcp_registration import read_config

        target = tmp_path / "string.json"
        stop_root = tmp_path
        target.write_text('"hello"', encoding="utf-8")
        with pytest.raises(ValueError, match="must be a JSON object"):
            read_config(target, stop_root=stop_root)

    def test_raises_on_number_json(self, tmp_path) -> None:
        from jev_bot.mcp_registration import read_config

        target = tmp_path / "number.json"
        stop_root = tmp_path
        target.write_text("42", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a JSON object"):
            read_config(target, stop_root=stop_root)

    def test_raises_on_null_json(self, tmp_path) -> None:
        from jev_bot.mcp_registration import read_config

        target = tmp_path / "null.json"
        stop_root = tmp_path
        target.write_text("null", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a JSON object"):
            read_config(target, stop_root=stop_root)

    def test_raises_on_invalid_json(self, tmp_path) -> None:
        from jev_bot.mcp_registration import read_config

        target = tmp_path / "invalid.json"
        stop_root = tmp_path
        target.write_text("{broken json!!!", encoding="utf-8")
        with pytest.raises(ValueError):
            read_config(target, stop_root=stop_root)


class TestWriteConfigAtomic:
    """write_config_atomic creates dirs, writes via fdopen+json.dump, and replaces atomically."""

    def test_creates_parent_directory(self, tmp_path) -> None:
        from jev_bot.mcp_registration import write_config_atomic

        target = tmp_path / "a" / "b" / "config.json"
        stop_root = tmp_path
        write_config_atomic(target, {"key": "val"}, stop_root=stop_root)
        assert target.exists()

    def test_uses_os_replace_not_pre_delete(self, tmp_path) -> None:
        """os.replace should NOT pre-delete the target."""
        import os
        from jev_bot.mcp_registration import write_config_atomic

        target = tmp_path / "existing.json"
        target.write_text("old content", encoding="utf-8")
        stop_root = tmp_path
        old_stat = target.stat()

        write_config_atomic(target, {"new": "data"}, stop_root=stop_root)

        # File should still exist
        assert target.exists()
        content = target.read_text(encoding="utf-8")
        assert '"new"' in content

    def test_is_utf8_encoded(self, tmp_path) -> None:
        from jev_bot.mcp_registration import write_config_atomic

        target = tmp_path / "utf8.json"
        stop_root = tmp_path
        write_config_atomic(target, {"emoji": "hello"}, stop_root=stop_root)
        content = target.read_text(encoding="utf-8")
        assert content  # non-empty

    def test_writes_valid_json(self, tmp_path) -> None:
        import json
        from jev_bot.mcp_registration import read_config, write_config_atomic

        target = tmp_path / "valid.json"
        stop_root = tmp_path
        write_config_atomic(target, {"check": True}, stop_root=stop_root)
        with open(target, "r", encoding="utf-8") as fh:
            parsed = json.load(fh)
        assert parsed == {"check": True}

    def test_uses_fdopen_not_raw_write(self, tmp_path) -> None:
        """write_config_atomic must use os.fdopen + json.dump (not os.write)."""
        import inspect
        from jev_bot.mcp_registration import write_config_atomic

        source = inspect.getsource(write_config_atomic)
        assert "os.fdopen" in source, "Must use os.fdopen for write"
        assert "json.dump" in source, "Must use json.dump for serialization"

    def test_fdopen_handles_unicode(self, tmp_path) -> None:
        """fdopen write handles full Unicode (emoji, CJK) without encode/decode roundtrip issues."""
        from jev_bot.mcp_registration import read_config, write_config_atomic

        target = tmp_path / "unicode.json"
        stop_root = tmp_path
        original = {"emoji": "😀", "cjk": "日本語", "arabic": "مرحبا"}
        write_config_atomic(target, original, stop_root=stop_root)
        result = read_config(target, stop_root=stop_root)
        assert result["emoji"] == "😀"
        assert result["cjk"] == "日本語"
        assert result["arabic"] == "مرحبا"


class TestSymlinkRefusal:
    """read_config and write_config_atomic refuse symlinked targets within stop_root."""

    def test_read_config_refuses_symlinked_file(self, tmp_path) -> None:
        from jev_bot.mcp_registration import read_config

        real = tmp_path / "real.json"
        real.write_text("{}", encoding="utf-8")
        link = tmp_path / "link.json"
        link.symlink_to(real)
        stop_root = tmp_path
        with pytest.raises(ValueError, match="symlink"):
            read_config(link, stop_root=stop_root)

    def test_read_config_refuses_symlinked_ancestor_within_root(self, tmp_path) -> None:
        from jev_bot.mcp_registration import read_config

        base = tmp_path / "realdir"
        base.mkdir()
        link_dir = tmp_path / "linkdir"
        link_dir.symlink_to(base)
        target = link_dir / "config.json"
        stop_root = tmp_path
        with pytest.raises(ValueError, match="symlink"):
            read_config(target, stop_root=stop_root)

    def test_write_config_refuses_symlinked_file(self, tmp_path) -> None:
        from jev_bot.mcp_registration import write_config_atomic

        real = tmp_path / "real.json"
        real.write_text("{}", encoding="utf-8")
        link = tmp_path / "link.json"
        link.symlink_to(real)
        stop_root = tmp_path
        with pytest.raises(ValueError, match="symlink"):
            write_config_atomic(link, {"boom": True}, stop_root=stop_root)

    def test_write_config_refuses_symlinked_ancestor_within_root(self, tmp_path) -> None:
        from jev_bot.mcp_registration import write_config_atomic

        base = tmp_path / "realdir"
        base.mkdir()
        link_dir = tmp_path / "linkdir"
        link_dir.symlink_to(base)
        target = link_dir / "config.json"
        stop_root = tmp_path
        with pytest.raises(ValueError, match="symlink"):
            write_config_atomic(target, {"boom": True}, stop_root=stop_root)


class TestStopRootBound:
    """stop_root limits the symlink walk — legitimate config under a deep
    tmp path works, symlink inside the allowed subtree is still caught."""

    def test_legitimate_deep_path_works(self, tmp_path) -> None:
        """A real nested config under tmp_path with tmp_path as stop_root."""
        from jev_bot.mcp_registration import read_config, write_config_atomic

        real = tmp_path / "a" / "b" / "c" / "config.json"
        stop_root = tmp_path
        write_config_atomic(real, {"ok": True}, stop_root=stop_root)
        result = read_config(real, stop_root=stop_root)
        assert result == {"ok": True}

    def test_symlink_target_outside_stop_root_is_not_accessed(self, tmp_path) -> None:
        """A symlink whose target lies outside stop_root must be refused."""
        from jev_bot.mcp_registration import read_config, write_config_atomic

        outside = tmp_path / "outside"
        outside.mkdir()
        safe_dir = tmp_path / "safe"
        safe_dir.mkdir()
        real_file = outside / "real.json"
        real_file.write_text("{}", encoding="utf-8")
        link = safe_dir / "link.json"
        link.symlink_to(real_file)
        stop_root = tmp_path
        with pytest.raises(ValueError, match="symlink"):
            read_config(link, stop_root=stop_root)

    def test_symlink_in_ancestor_inside_root_is_caught(self, tmp_path) -> None:
        """A symlinked parent dir inside stop_root must be refused."""
        from jev_bot.mcp_registration import read_config

        real_dir = tmp_path / "real_parent"
        real_dir.mkdir()
        link_parent = tmp_path / "fake_parent"
        link_parent.symlink_to(real_dir)
        config = link_parent / "config.json"
        stop_root = tmp_path
        with pytest.raises(ValueError, match="symlink"):
            read_config(config, stop_root=stop_root)
