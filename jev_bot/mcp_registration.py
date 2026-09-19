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
from enum import Enum, auto
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


# ── Task 3: server-path helpers ──────────────────────────────────────


def _split_server_path(server_path: str) -> list[str]:
    """Split a dotted server_path into its key components."""
    return server_path.split(".")


@dataclass
class _LookupResult:
    """Internal result type for nested-path lookups."""

    present: bool
    value: dict | None
    non_dict_at: int | None = None  # index where non-dict was found


def _lookup(data: dict, keys: list[str]) -> _LookupResult:
    """Walk *keys* inside *data*, returning a result indicating whether the
    path exists and is a dict at every component.

    ``present=True``, ``value=<dict>`` — all keys found, final value is a dict.
    ``present=True``, ``value=None``, ``non_dict_at=<i>`` — leaf at index *i* is
    non-dict (path reached the final key but value is not a dict).
    ``present=False``, ``non_dict_at=<i>`` — an intermediate at index *i* is
    non-dict, so traversal stops there.
    ``present=False``, ``non_dict_at=None`` — key chain is genuinely absent.
    """
    cur: object = data
    non_dict_at: int | None = None  # index where non-dict was found
    for i, key in enumerate(keys):
        if not isinstance(cur, dict) or key not in cur:
            return _LookupResult(
                present=False, value=None, non_dict_at=non_dict_at
            )
        cur = cur[key]
        if not isinstance(cur, dict):
            non_dict_at = i
            if i == len(keys) - 1:
                # Leaf is non-dict — definitely present but malformed.
                return _LookupResult(present=True, value=None, non_dict_at=i)
    if non_dict_at is not None:
        # Should not happen (loop already catches non-dict), but guard.
        return _LookupResult(present=True, value=None, non_dict_at=non_dict_at)
    return _LookupResult(present=True, value=cur)


# ── Registration outcomes ──────────────────────────────────────────


class RegistrationStatus(Enum):
    """Outcome of an install or uninstall operation."""

    CREATED = auto()
    EXISTS = auto()
    REPLACED = auto()
    REMOVED = auto()
    ABSENT = auto()
    FOREIGN = auto()


@dataclass(frozen=True)
class RegistrationResult:
    """Result of a registration operation.

    Attributes
    ----------
    path : Path
        The config file path that was read / written.
    status : RegistrationStatus
        One of ``CREATED``, ``EXISTS``, ``REPLACED``, ``REMOVED``,
        ``ABSENT``, or ``FOREIGN``.
    """

    path: Path
    status: RegistrationStatus


# Legacy name for _get_nested — returns None when path is absent or non-dict,
# dict value otherwise. Kept for test compatibility.
def _get_nested(data: dict, keys: list[str]) -> dict | None:
    """Walk *keys* inside *data*, returning ``None`` if any key is missing."""
    result = _lookup(data, keys)
    if not result.present:
        return None
    return result.value  # type: ignore[return-value]


def _set_nested(data: dict, keys: list[str], value: dict) -> None:
    """Set *value* inside *data* following *keys*, creating intermediates."""
    cur = data
    for key in keys[:-1]:
        if key not in cur or not isinstance(cur[key], dict):
            cur[key] = {}
        cur = cur[key]
    cur[keys[-1]] = value


def _del_nested(data: dict, keys: list[str]) -> None:
    """Delete the leaf key in *data* along *keys*, if present,
    pruning empty parent dicts on the way up."""
    cur: dict = data
    parents: list[tuple[dict, str]] = []
    for key in keys[:-1]:
        if not isinstance(cur, dict) or key not in cur:
            return
        parents.append((cur, key))
        cur = cur[key]
    if isinstance(cur, dict) and keys[-1] in cur:
        del cur[keys[-1]]
        # Prune empty dicts back up the chain
        for parent, key in reversed(parents):
            if parent[key] == {}:
                del parent[key]
            else:
                break


def _ensure_parent_dirs(path: Path, *, stop_root: Path) -> None:
    """Create parent directories for *path*, with stop_root validation."""
    parent = path.parent
    if parent and not parent.exists():
        _reject_symlink(parent, stop_root)
        parent.mkdir(parents=True, exist_ok=True)


# ── Classification ────────────────────────────────────────────────────


class ServerEntryState:
    """Classification outcome for a single server-path entry."""

    ABSENT = "absent"
    CANONICAL = "canonical"
    FOREIGN = "foreign"


def classify_server_entry(
    harness: str,
    config_path: Path,
    *,
    stop_root: Path,
) -> str:
    """Classify the state of *harness*'s ``jev`` server entry in *config_path*.

    Returns one of:
    - ``"absent"`` — no server config file or ``jev`` key missing
    - ``"canonical"`` — a ``jev`` entry matching the harness canonical spec
    - ``"foreign"`` — a ``jev`` entry present but not matching the canonical spec
    """
    scopes = registration_target(harness)
    canonical = canonical_entry(harness)
    keys = _split_server_path(scopes.project.server_path)

    config = read_config(config_path, stop_root=stop_root)
    result = _lookup(config, keys)

    if result.non_dict_at is not None:
        # Path exists at some level but hits a non-dict — FOREIGN.
        return ServerEntryState.FOREIGN
    if not result.present:
        # Key chain is genuinely absent.
        return ServerEntryState.ABSENT
    if result.value != canonical:
        # Present dict doesn't match canonical spec.
        return ServerEntryState.FOREIGN

    return ServerEntryState.CANONICAL


# ── Install / Uninstall ──────────────────────────────────────────────


def install_server(
    harness: str,
    *,
    project_root: Path | None = None,
    user_home: Path | None = None,
    force: bool = False,
) -> RegistrationResult:
    """Install the JEV MCP server entry into the harness config.

    Classification-driven:

    - **Absent** — writes the canonical ``jev`` entry (new config file if
      needed).
    - **Canonical** — no-op; returns the config path unchanged.
    - **Foreign** — raises ``ValueError`` unless *force* is ``True``, in
      which case it replaces **only** the ``jev`` key with the canonical
      entry (preserving sibling server entries).

    Exactly one of *project_root* or *user_home* must be provided.

    Returns
    -------
    RegistrationResult
        The path to the config file and its operation status.
    """
    if harness not in REGISTRY:
        raise ValueError(
            f"'{harness}' is not a recognized MCP harness "
            f"(expected one of {list(REGISTRY)})"
        )

    if project_root is not None and user_home is not None:
        raise ValueError(
            "Provide exactly one of project_root or user_home, not both"
        )
    if project_root is None and user_home is None:
        raise ValueError(
            "Exactly one of project_root or user_home must be provided"
        )

    if project_root is not None:
        stop_root = project_root
        scopes = registration_target(harness).project
    else:
        stop_root = user_home
        scopes = registration_target(harness).user

    config_path = stop_root / scopes.path_key

    state = classify_server_entry(harness, config_path, stop_root=stop_root)

    if state == ServerEntryState.ABSENT:
        config: dict = {}
        if config_path.exists():
            config = read_config(config_path, stop_root=stop_root)
        _set_nested(config, _split_server_path(scopes.server_path), canonical_entry(harness))
        _ensure_parent_dirs(config_path, stop_root=stop_root)
        write_config_atomic(config_path, config, stop_root=stop_root)
        return RegistrationResult(path=config_path, status=RegistrationStatus.CREATED)

    elif state == ServerEntryState.CANONICAL:
        return RegistrationResult(path=config_path, status=RegistrationStatus.EXISTS)

    else:
        # FOREIGN
        if not force:
            raise ValueError(
                f"Refusing to install: '{scopes.server_path}' exists in "
                f"{config_path} but does not match the canonical entry. "
                f"Use force=True to replace."
            )
        config = read_config(config_path, stop_root=stop_root)
        _set_nested(config, _split_server_path(scopes.server_path), canonical_entry(harness))
        write_config_atomic(config_path, config, stop_root=stop_root)
        return RegistrationResult(path=config_path, status=RegistrationStatus.REPLACED)


def uninstall_server(
    harness: str,
    *,
    project_root: Path | None = None,
    user_home: Path | None = None,
) -> RegistrationResult:
    """Uninstall the JEV MCP server entry from the harness config.

    Classification-driven:

    - **Canonical** — removes the ``jev`` key and writes back the config.
      The empty config file is retained (no file deletion).
    - **Absent** — no-op; returns the config path.
    - **Foreign** — no mutation; returns the config path with no error.

    Exactly one of *project_root* or *user_home* must be provided.

    Returns
    -------
    RegistrationResult
        The path to the config file and its operation status.
    """
    if harness not in REGISTRY:
        raise ValueError(
            f"'{harness}' is not a recognized MCP harness "
            f"(expected one of {list(REGISTRY)})"
        )

    if project_root is not None and user_home is not None:
        raise ValueError(
            "Provide exactly one of project_root or user_home, not both"
        )
    if project_root is None and user_home is None:
        raise ValueError(
            "Exactly one of project_root or user_home must be provided"
        )

    if project_root is not None:
        stop_root = project_root
        scopes = registration_target(harness).project
    else:
        stop_root = user_home
        scopes = registration_target(harness).user

    config_path = stop_root / scopes.path_key

    state = classify_server_entry(harness, config_path, stop_root=stop_root)

    if state == ServerEntryState.CANONICAL:
        config = read_config(config_path, stop_root=stop_root)
        _del_nested(config, _split_server_path(scopes.server_path))
        # Write back regardless — even if empty, the file is retained.
        write_config_atomic(config_path, config, stop_root=stop_root)
        return RegistrationResult(path=config_path, status=RegistrationStatus.REMOVED)

    elif state == ServerEntryState.FOREIGN:
        return RegistrationResult(path=config_path, status=RegistrationStatus.FOREIGN)

    # absent → no-op
    return RegistrationResult(path=config_path, status=RegistrationStatus.ABSENT)
