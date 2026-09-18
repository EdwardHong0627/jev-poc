"""Pure domain registry for MCP server canonical entries.

Defines the declarative mapping of harness identifiers to their
project/user configuration paths and the transport-agnostic JSON
structures used to launch the JEV MCP server.  Zero side-effects,
no Typer dependency, no filesystem or config-store coupling.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from copy import deepcopy

JEV_GIT_URL = "git+https://github.com/EdwardHong0627/jev-poc.git"


@dataclass(frozen=True, slots=True)
class ScopeSpec:
    """Path keys for a single scope (project or user) of a harness."""

    path_key: str
    server_path: str  # full dotted JSON path to the "jev" server entry


@dataclass(frozen=True, slots=True)
class HarnessSpec:
    """A harness's registration profile and its two scope path keys."""

    scopes: Scopes


@dataclass(frozen=True, slots=True)
class Scopes:
    """Named-access convenience over (project, user) path specs."""

    project: ScopeSpec
    user: ScopeSpec


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
            project=ScopeSpec(path_key=".mcp.json", server_path="mcpServers.jev"),
            user=ScopeSpec(path_key=".claude.json", server_path="mcpServers.jev"),
        ),
    ),
    "opencode": HarnessSpec(
        scopes=Scopes(
            project=ScopeSpec(path_key="opencode.json", server_path="mcp.servers.jev"),
            user=ScopeSpec(
                path_key=".config/opencode/opencode.json", server_path="mcp.servers.jev"
            ),
        ),
    ),
    "oh-my-pi": HarnessSpec(
        scopes=Scopes(
            project=ScopeSpec(path_key=".omp/mcp.json", server_path="mcpServers.jev"),
            user=ScopeSpec(path_key=".omp/agent/mcp.json", server_path="mcpServers.jev"),
        ),
    ),
    "pi": HarnessSpec(
        scopes=Scopes(
            project=ScopeSpec(path_key=".pi/mcp.json", server_path="mcpServers.jev"),
            user=ScopeSpec(path_key=".pi/agent/mcp.json", server_path="mcpServers.jev"),
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
    """Return a copy of the transport-specific JSON entry dict for *harness*.

    Raises ``ValueError`` when *harness* is not recognized.
    """
    if harness not in _CANONICAL_ENTRIES:
        raise ValueError(
            f"'{harness}' is not a recognized MCP harness "
            f"(expected one of {list(_CANONICAL_ENTRIES)})"
        )
    return deepcopy(_CANONICAL_ENTRIES[harness])


# ── Config read / write helpers (Task 2) ──────────────────────────────


def _find_symlink_ancestry(path: Path, stop_root: Path) -> None:
    """Walk from *path* up toward *stop_root*, raising if any existing
    component is a symlink.

    Mirrors the installer strategy: only inspect components that
    actually exist on disk, never walk past *stop_root*.
    """
    cur: Path = path
    visited: list[Path] = []
    while cur != stop_root and cur != cur.parent:
        if cur.exists():
            visited.append(cur)
        cur = cur.parent

    for component in reversed(visited):
        if component.is_symlink():
            raise ValueError(
                f"Refusing config path through symlink: {component}"
            )


def _reject_symlink(path: Path, stop_root: Path) -> None:
    """Refuse *path* or any ancestor (up to *stop_root*) that is a symlink.

    The walk stops at *stop_root* (which is considered trusted).
    """
    _find_symlink_ancestry(path, stop_root)
    if path.is_symlink():
        raise ValueError(
            f"Refusing config path: {path} is a symlink"
        )


def read_config(path: Path, *, stop_root: Path) -> dict:
    """Read and parse a JSON config file.

    *stop_root* is the trusted boundary (project root or user home); the
    symlink walk stops there and never reaches filesystem root.

    Returns an empty dict ``{}`` when the file does not exist.
    Raises ``ValueError`` when the file is malformed or the top-level
    JSON value is not an object.
    """
    _reject_symlink(path, stop_root)

    if not path.exists():
        return {}

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read config {path}: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Malformed JSON in {path}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"Config {path} must be a JSON object, got {type(data).__name__}"
        )

    return data


def write_config_atomic(path: Path, value: dict, *, stop_root: Path) -> None:
    """Write *value* as UTF-8 JSON to *path* atomically.

    Creates parent directories as needed.  Opens the temp file with
    ``os.fdopen``, calls ``json.dump``, ``fsync``, then
    ``os.replace`` (no pre-deletion of the target).

    *stop_root* is the trusted boundary; the symlink walk stops there.

    Raises ``ValueError`` if *path* or any ancestor (up to *stop_root*)
    is a symlink.
    """
    _reject_symlink(path, stop_root)

    parent = path.parent
    if parent and not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=str(parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(value, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, str(path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
