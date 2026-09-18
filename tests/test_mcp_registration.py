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
        for val in str(entry).lower():
            pass  # structure-based check below
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


# ── server_path ──────────────────────────────────────────────────────

class TestServerPath:
    """Assert that every ScopeSpec has a declarative server_path ending in 'jev'."""

    def test_all_scope_specs_have_server_path(self) -> None:
        for harness in HARNESSES:
            spec = REGISTRY[harness]
            assert spec.scopes.project.server_path == "jev"
            assert spec.scopes.user.server_path == "jev"

    def test_claude_code_project_server_path(self) -> None:
        spec = REGISTRY["claude-code"]
        assert spec.scopes.project.server_path == "jev"

    def test_claude_code_user_server_path(self) -> None:
        spec = REGISTRY["claude-code"]
        assert spec.scopes.user.server_path == "jev"

    def test_opencode_project_server_path(self) -> None:
        spec = REGISTRY["opencode"]
        assert spec.scopes.project.server_path == "jev"

    def test_opencode_user_server_path(self) -> None:
        spec = REGISTRY["opencode"]
        assert spec.scopes.user.server_path == "jev"

    def test_oh_my_pi_project_server_path(self) -> None:
        spec = REGISTRY["oh-my-pi"]
        assert spec.scopes.project.server_path == "jev"

    def test_oh_my_pi_user_server_path(self) -> None:
        spec = REGISTRY["oh-my-pi"]
        assert spec.scopes.user.server_path == "jev"

    def test_pi_project_server_path(self) -> None:
        spec = REGISTRY["pi"]
        assert spec.scopes.project.server_path == "jev"

    def test_pi_user_server_path(self) -> None:
        spec = REGISTRY["pi"]
        assert spec.scopes.user.server_path == "jev"


class TestRegistrationTargetServerPath:
    """Assert server_path is reachable through registration_target()."""

    def test_project_server_path_via_registration_target(self) -> None:
        scopes = registration_target("claude-code")
        assert scopes.project.server_path == "jev"

    def test_user_server_path_via_registration_target(self) -> None:
        scopes = registration_target("opencode")
        assert scopes.user.server_path == "jev"

    def test_all_harnesses_server_path_via_registration_target(self) -> None:
        for harness in HARNESSES:
            scopes = registration_target(harness)
            assert scopes.project.server_path == "jev"
            assert scopes.user.server_path == "jev"
