"""Tests for the MCP registration registry and canonical entries."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from jev_bot.mcp_registration import (
    HARNESSES,
    JEV_GIT_URL,
    REGISTRY,
    SQLITE_DB_FLAG,
    ManagedVariant,
    ScopeSpec,
    Scopes,
    ServerEntryState,
    canonical_entry,
    classify_server_entry,
    parse_managed_entry,
    registration_target,
    write_config_atomic,
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


# ── SQLite opt-in: canonical entry suffix ───────────────────────────

# The pre-change hardcoded entry shapes.  The disabled default of
# canonical_entry() must remain byte-for-byte these entries.
_HISTORICAL_ENTRY: dict[str, dict] = {
    "claude-code": {
        "type": "stdio",
        "command": "uvx",
        "args": ["--from", JEV_GIT_URL, "jev-mcp"],
    },
    "opencode": {
        "type": "local",
        "command": ["uvx", "--from", JEV_GIT_URL, "jev-mcp"],
    },
    "oh-my-pi": {
        "type": "stdio",
        "command": "uvx",
        "args": ["--from", JEV_GIT_URL, "jev-mcp"],
    },
    "pi": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["--from", JEV_GIT_URL, "jev-mcp"],
        "lifecycle": "lazy",
    },
}

# Which field carries the launcher token list for each harness.
_LAUNCHER_KEYS: dict[str, str] = {
    "claude-code": "args",
    "opencode": "command",
    "oh-my-pi": "args",
    "pi": "args",
}

_SQLITE_DB_PATH = Path("/abs/SQLITE_DB")
_SQLITE_SUFFIX = [SQLITE_DB_FLAG, "/abs/SQLITE_DB"]


def _flat_values(entry: dict) -> list[str]:
    """Every scalar string reachable inside an entry dict."""
    tokens: list[str] = []
    for value in entry.values():
        if isinstance(value, list):
            tokens.extend(str(item) for item in value)
        elif isinstance(value, str):
            tokens.append(value)
    return tokens


class TestCanonicalEntrySqliteSuffix:
    """The disabled default is the historical entry; the enabled entry is that
    entry plus exactly ``["--sqlite-db", ABS_PATH]`` on the launcher list."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_disabled_default_equals_historical_entry(self, harness: str) -> None:
        expected = deepcopy(_HISTORICAL_ENTRY[harness])
        entry = canonical_entry(harness)
        assert entry == expected
        assert set(entry) == set(expected)

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_disabled_default_carries_no_sqlite_token(self, harness: str) -> None:
        entry = canonical_entry(harness)
        assert SQLITE_DB_FLAG not in _flat_values(entry)
        assert not any(SQLITE_DB_FLAG in tok for tok in _flat_values(entry))

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_explicit_disabled_equals_default(self, harness: str) -> None:
        default = canonical_entry(harness)
        explicit = canonical_entry(
            harness, db_enable=False, sqlite_db_path=None
        )
        assert explicit == default
        assert explicit == deepcopy(_HISTORICAL_ENTRY[harness])

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_enabled_is_disabled_plus_suffix(self, harness: str) -> None:
        disabled = canonical_entry(harness)
        enabled = canonical_entry(
            harness, db_enable=True, sqlite_db_path=_SQLITE_DB_PATH
        )
        launcher_key = _LAUNCHER_KEYS[harness]
        stripped = deepcopy(enabled)
        stripped[launcher_key] = enabled[launcher_key][:-2]
        assert stripped == disabled

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_suffix_appended_to_launcher_field(self, harness: str) -> None:
        launcher_key = _LAUNCHER_KEYS[harness]
        base = canonical_entry(harness)
        enabled = canonical_entry(
            harness, db_enable=True, sqlite_db_path=_SQLITE_DB_PATH
        )
        base_launcher = base[launcher_key]
        assert isinstance(base_launcher, list)
        if harness == "opencode":
            assert launcher_key == "command"
        else:
            assert launcher_key == "args"
        # The base launcher is preserved as a prefix of the enabled launcher.
        enabled_launcher = enabled[launcher_key]
        assert enabled_launcher[: len(base_launcher)] == base_launcher
        # The suffix is exactly the SQLite pair, appended to the launcher only.
        assert enabled_launcher[len(base_launcher):] == _SQLITE_SUFFIX
        for other_key, value in enabled.items():
            if other_key != launcher_key:
                assert value == base[other_key]

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_enabled_mutation_does_not_poison_later_lookups(self, harness: str) -> None:
        launcher_key = _LAUNCHER_KEYS[harness]
        enabled = canonical_entry(
            harness, db_enable=True, sqlite_db_path=_SQLITE_DB_PATH
        )
        enabled["type"] = "spoofed"
        enabled["transport"] = "spoofed"
        enabled[launcher_key].append("corrupted")

        # A fresh disabled lookup is clean: the historical shape, no suffix.
        fresh_disabled = canonical_entry(harness)
        assert fresh_disabled == deepcopy(_HISTORICAL_ENTRY[harness])
        assert SQLITE_DB_FLAG not in _flat_values(fresh_disabled)
        assert "corrupted" not in fresh_disabled[launcher_key]

        # A fresh enabled lookup is untouched by the mutation above.
        fresh_enabled = canonical_entry(
            harness, db_enable=True, sqlite_db_path=_SQLITE_DB_PATH
        )
        assert "corrupted" not in fresh_enabled[launcher_key]
        assert fresh_enabled[launcher_key][-2:] == _SQLITE_SUFFIX


class TestCanonicalEntryEnableValidation:
    """Enabling requires an absolute Path; a path without enabling is a bug."""

    def test_enable_without_path_raises(self) -> None:
        with pytest.raises(ValueError, match="sqlite_db_path"):
            canonical_entry("claude-code", db_enable=True)

    def test_enable_with_relative_path_raises(self) -> None:
        with pytest.raises(ValueError, match="absolute"):
            canonical_entry(
                "claude-code", db_enable=True, sqlite_db_path=Path("rel/SQLITE_DB")
            )

    def test_path_without_enable_raises(self) -> None:
        with pytest.raises(ValueError, match="requires db_enable=True"):
            canonical_entry(
                "claude-code", db_enable=False, sqlite_db_path=_SQLITE_DB_PATH
            )

    def test_path_without_enable_raises_by_default(self) -> None:
        with pytest.raises(ValueError, match="requires db_enable=True"):
            canonical_entry("opencode", sqlite_db_path=_SQLITE_DB_PATH)

    @pytest.mark.parametrize("harness", ["unknown", ""])
    def test_unknown_harness_still_raises_when_enabling(self, harness: str) -> None:
        with pytest.raises(ValueError, match="not a recognized MCP harness"):
            canonical_entry(
                harness, db_enable=True, sqlite_db_path=_SQLITE_DB_PATH
            )


# ── Managed-entry parsing ───────────────────────────────────────────


def _with_launcher(harness: str, launcher: list) -> dict:
    """The historical base entry with its launcher list replaced."""
    entry = deepcopy(_HISTORICAL_ENTRY[harness])
    entry[_LAUNCHER_KEYS[harness]] = launcher
    return entry


class TestParseManagedEntry:
    """parse_managed_entry owns exactly the base and base+SQLite-pair shapes."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_exact_disabled_is_managed(self, harness: str) -> None:
        parsed = parse_managed_entry(harness, canonical_entry(harness))
        assert parsed.variant is ManagedVariant.DISABLED
        assert parsed.sqlite_db_path is None

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_exact_enabled_is_managed_with_path(self, harness: str) -> None:
        entry = canonical_entry(
            harness, db_enable=True, sqlite_db_path=_SQLITE_DB_PATH
        )
        parsed = parse_managed_entry(harness, entry)
        assert parsed.variant is ManagedVariant.ENABLED
        assert parsed.sqlite_db_path == _SQLITE_DB_PATH

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_extra_token_is_foreign(self, harness: str) -> None:
        base = canonical_entry(harness)[_LAUNCHER_KEYS[harness]]
        entry = _with_launcher(harness, [*base, "--verbose"])
        assert parse_managed_entry(harness, entry).variant is ManagedVariant.FOREIGN

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_extra_token_after_sqlite_pair_is_foreign(self, harness: str) -> None:
        base = canonical_entry(harness)[_LAUNCHER_KEYS[harness]]
        entry = _with_launcher(harness, [*base, *_SQLITE_SUFFIX, "--verbose"])
        assert parse_managed_entry(harness, entry).variant is ManagedVariant.FOREIGN

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_sqlite_pair_reordered_into_launcher_is_foreign(
        self, harness: str
    ) -> None:
        """The flag inserted mid-launcher is not the owned trailing suffix."""
        base = canonical_entry(harness)[_LAUNCHER_KEYS[harness]]
        inserted = [*base[:-1], *[_SQLITE_SUFFIX[0], _SQLITE_SUFFIX[1]], base[-1]]
        entry = _with_launcher(harness, inserted)
        assert parse_managed_entry(harness, entry).variant is ManagedVariant.FOREIGN

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_relative_sqlite_path_is_foreign(self, harness: str) -> None:
        base = canonical_entry(harness)[_LAUNCHER_KEYS[harness]]
        entry = _with_launcher(harness, [*base, SQLITE_DB_FLAG, "rel/SQLITE_DB"])
        assert parse_managed_entry(harness, entry).variant is ManagedVariant.FOREIGN

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_flag_without_path_is_foreign(self, harness: str) -> None:
        base = canonical_entry(harness)[_LAUNCHER_KEYS[harness]]
        entry = _with_launcher(harness, [*base, SQLITE_DB_FLAG])
        assert parse_managed_entry(harness, entry).variant is ManagedVariant.FOREIGN

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_path_without_flag_is_foreign(self, harness: str) -> None:
        base = canonical_entry(harness)[_LAUNCHER_KEYS[harness]]
        entry = _with_launcher(harness, [*base, "/abs/SQLITE_DB"])
        assert parse_managed_entry(harness, entry).variant is ManagedVariant.FOREIGN

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_extra_unknown_key_is_foreign(self, harness: str) -> None:
        entry = canonical_entry(harness)
        entry["env"] = {"TOKEN": "x"}
        assert parse_managed_entry(harness, entry).variant is ManagedVariant.FOREIGN

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_different_transport_field_is_foreign(self, harness: str) -> None:
        entry = canonical_entry(harness)
        transport_key = "transport" if harness == "pi" else "type"
        entry[transport_key] = "sse"
        assert parse_managed_entry(harness, entry).variant is ManagedVariant.FOREIGN

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_non_dict_value_is_foreign(self, harness: str) -> None:
        base = canonical_entry(harness)
        assert (
            parse_managed_entry(harness, base[_LAUNCHER_KEYS[harness]]).variant
            is ManagedVariant.FOREIGN
        )
        assert parse_managed_entry(harness, "uvx").variant is ManagedVariant.FOREIGN
        assert parse_managed_entry(harness, None).variant is ManagedVariant.FOREIGN

    def test_unknown_harness_is_foreign_without_raising(self) -> None:
        for entry in (canonical_entry("claude-code"), canonical_entry("opencode")):
            parsed = parse_managed_entry("bogus-harness", entry)
            assert parsed.variant is ManagedVariant.FOREIGN
            assert parsed.sqlite_db_path is None


# ── classify_server_entry on managed variants ───────────────────────


def _seed_server_entry(project: Path, harness: str, entry: dict) -> Path:
    """Write *entry* at the harness's jev server path; return config path."""
    scopes = registration_target(harness).project
    config_path = project / scopes.path_key
    config_path.parent.mkdir(parents=True, exist_ok=True)
    keys = scopes.server_path.split(".")
    data: dict = {}
    cursor = data
    for key in keys[:-1]:
        cursor = cursor.setdefault(key, {})
    cursor[keys[-1]] = entry
    write_config_atomic(config_path, data, stop_root=project)
    return config_path


class TestClassifyServerEntryManagedVariants:
    """JEV owns both managed variants; anything else stays foreign."""

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_seeded_disabled_entry_is_canonical(self, tmp_path: Path, harness: str) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        config_path = _seed_server_entry(project, harness, canonical_entry(harness))
        assert (
            classify_server_entry(harness, config_path, stop_root=project)
            == ServerEntryState.CANONICAL
        )

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_seeded_enabled_entry_is_canonical(self, tmp_path: Path, harness: str) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        enabled = canonical_entry(
            harness, db_enable=True, sqlite_db_path=_SQLITE_DB_PATH
        )
        config_path = _seed_server_entry(project, harness, enabled)
        assert (
            classify_server_entry(harness, config_path, stop_root=project)
            == ServerEntryState.CANONICAL
        )

    @pytest.mark.parametrize("harness", HARNESSES)
    def test_enabled_with_extra_arg_is_foreign(self, tmp_path: Path, harness: str) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        launcher_key = _LAUNCHER_KEYS[harness]
        enabled = canonical_entry(
            harness, db_enable=True, sqlite_db_path=_SQLITE_DB_PATH
        )
        entry = canonical_entry(harness)
        entry[launcher_key] = [*enabled[launcher_key], "--verbose"]
        config_path = _seed_server_entry(project, harness, entry)
        assert (
            classify_server_entry(harness, config_path, stop_root=project)
            == ServerEntryState.FOREIGN
        )


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
