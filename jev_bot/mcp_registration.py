"""Pure domain registry for MCP server canonical entries.

Defines the declarative mapping of harness identifiers to their
project/user configuration paths and the transport-agnostic JSON
structures used to launch the JEV MCP server.  Zero side-effects,
no Typer dependency, no filesystem or config-store coupling.
"""

from __future__ import annotations

from dataclasses import dataclass, field

JEV_GIT_URL = "git+https://github.com/EdwardHong0627/jev-poc.git"


@dataclass(frozen=True, slots=True)
class ScopeSpec:
    """Path keys for a single scope (project or user) of a harness."""

    path_key: str
    server_path: str  # basename of the "jev" server key within the config file


@dataclass(frozen=True, slots=True)
class HarnessSpec:
    """A harness's registration profile and its two scope path keys."""

    scopes: Scopes


@dataclass(frozen=True, slots=True)
class Scopes:
    """Named-access convenience over (project, user) path specs."""

    project: ScopeSpec
    user: ScopeSpec


# Canonical entries — one per harness.
# Each value is the JSON-like dict that appears under the "jev" key
# in the harness's MCP configuration file.
_CLAUDE_CODE_ENTRY: dict = {
    "type": "stdio",
    "command": "uvx",
    "args": ["--from", JEV_GIT_URL, "jev-mcp"],
}

_OPENCODE_ENTRY: dict = {
    "type": "local",
    "command": ["uvx", "--from", JEV_GIT_URL, "jev-mcp"],
}

_OH_MY_PI_ENTRY: dict = {
    "type": "stdio",
    "command": "uvx",
    "args": ["--from", JEV_GIT_URL, "jev-mcp"],
}

_PI_ENTRY: dict = {
    "transport": "stdio",
    "command": "uvx",
    "args": ["--from", JEV_GIT_URL, "jev-mcp"],
    "lifecycle": "lazy",
}

# ── Registry ─────────────────────────────────────────────────────────

HARNESSES: list[str] = [
    "claude-code",
    "opencode",
    "oh-my-pi",
    "pi",
]

REGISTRY: dict[str, HarnessSpec] = {
    "claude-code": HarnessSpec(
        scopes=Scopes(
            project=ScopeSpec(path_key=".mcp.json", server_path="jev"),
            user=ScopeSpec(path_key=".claude.json", server_path="jev"),
        ),
    ),
    "opencode": HarnessSpec(
        scopes=Scopes(
            project=ScopeSpec(path_key="opencode.json", server_path="jev"),
            user=ScopeSpec(path_key=".config/opencode/opencode.json", server_path="jev"),
        ),
    ),
    "oh-my-pi": HarnessSpec(
        scopes=Scopes(
            project=ScopeSpec(path_key=".omp/mcp.json", server_path="jev"),
            user=ScopeSpec(path_key=".omp/agent/mcp.json", server_path="jev"),
        ),
    ),
    "pi": HarnessSpec(
        scopes=Scopes(
            project=ScopeSpec(path_key=".pi/mcp.json", server_path="jev"),
            user=ScopeSpec(path_key=".pi/agent/mcp.json", server_path="jev"),
        ),
    ),
}

# Canonical entry lookup table (same keys as REGISTRY).
_CANONICAL_ENTRIES: dict[str, dict] = {
    "claude-code": _CLAUDE_CODE_ENTRY,
    "opencode": _OPENCODE_ENTRY,
    "oh-my-pi": _OH_MY_PI_ENTRY,
    "pi": _PI_ENTRY,
}


def registration_target(harness: str) -> Scopes:
    """Return the *Scopes* for *harness*.

    Raises ``ValueError`` when *harness* is not one of the four
    registered identifiers.
    """
    if harness not in REGISTRY:
        raise ValueError(
            f"'{harness}' is not a recognized MCP harness "
            f"(expected one of {list(REGISTRY)})"
        )
    return REGISTRY[harness].scopes


def canonical_entry(harness: str) -> dict:
    """Return the transport-specific JSON entry dict for *harness*.

    Raises ``ValueError`` when *harness* is not recognized.
    """
    if harness not in _CANONICAL_ENTRIES:
        raise ValueError(
            f"'{harness}' is not a recognized MCP harness "
            f"(expected one of {list(REGISTRY)})"
        )
    return _CANONICAL_ENTRIES[harness]
