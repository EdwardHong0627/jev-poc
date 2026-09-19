"""JEV installer — package-native skill installation for four harnesses.

Coordinates skill installation with MCP server registration.
"""

from __future__ import annotations

import importlib.resources
import shutil
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Tuple

from jev_bot.mcp_registration import (
    RegistrationResult,
    install_server,
    uninstall_server,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKILL_NAME = "using-jev-decisions"

# Mapping: harness_name -> (project_path_suffix, user_path_suffix).
# Each suffix is appended to the caller's chosen root (project root or home).
HARNESS_MAP: dict[str, tuple[str, str]] = {
    "claude-code": (".claude/skills", ".claude/skills"),
    "opencode": (".opencode/skills", ".config/opencode/skills"),
    "oh-my-pi": (".omp/skills", ".omp/agent/skills"),
    "pi": (".pi/skills", ".pi/agent/skills"),
}

VALID_HARNESSES = frozenset(HARNESS_MAP)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _skill_source() -> Traversable:
    """Return the packaged SKILL.md resource."""
    return importlib.resources.files("jev_bot.assets") / SKILL_NAME / "SKILL.md"


def _ensure_symlink_free(path: Path) -> None:
    """Raise ``RuntimeError`` if *path* exists and is a symlink."""
    if path.is_symlink():
        raise RuntimeError(f"Cannot proceed: {path} is a symlink")


def _build_path(root: Path, suffix: str) -> Path:
    """Append *suffix* (slash-separated) to *root*."""
    parts = [p for p in suffix.split("/") if p]
    cur = root
    for part in parts:
        cur = cur / part
    return cur


def _find_symlink_ancestry(target: Path, stop_root: Path) -> None:
    """Walk from *target* up to (but not including) *stop_root*,
    raising if any existing component is a symlink.

    stop_root is the harness-specific parent that must never be pruned.
    """
    cur = target
    visited: list[Path] = []
    while cur != stop_root and cur != cur.parent:
        if cur.exists():
            visited.append(cur)
        cur = cur.parent

    for component in reversed(visited):
        _ensure_symlink_free(component)


def _read_skill_bytes() -> bytes:
    """Read the packaged SKILL.md."""
    return _skill_source().read_bytes()


# ---------------------------------------------------------------------------
# Install / Uninstall
# ---------------------------------------------------------------------------


def install(
    harness: str,
    *,
    project_root: Path | None = None,
    user_home: Path | None = None,
    force: bool = False,
) -> Path:
    """Install the JEV skill and MCP registration into the *harness*'s destination.

    Preflights the MCP configuration and installs the skill plus a canonical
    ``jev`` MCP server entry.  A pre-existing foreign MCP entry raises a
    ``ValueError`` *before* any skill directory is created (unless *force* is
    ``True``, which replaces only that MCP entry).

    Exactly one of *project_root* or *user_home* must be provided.
    *project_root* targets the harness's project path only.
    *user_home* targets the harness's user path only.

    Returns
    -------
    Path
        The target ``SKILL.md`` path that was written.
    """
    skill_path, _result = install_with_report(
        harness, project_root=project_root, user_home=user_home, force=force,
    )
    return skill_path


def install_with_report(
    harness: str,
    *,
    project_root: Path | None = None,
    user_home: Path | None = None,
    force: bool = False,
) -> Tuple[Path, RegistrationResult]:
    """Install the JEV skill and MCP registration, returning the report.

    Preflights both the skill source and the skill target, then the MCP
    configuration, before any filesystem mutation.  A failure in either
    domain leaves **no partial state** (no skill directory, no MCP config
    change).

    Returns a ``(skill_path, registration_result)`` tuple where *registration_*
    *result* describes the MCP registration outcome.
    """
    if harness not in VALID_HARNESSES:
        raise ValueError(f"Unknown harness {harness!r}; expected one of {sorted(VALID_HARNESSES)}")

    if project_root is not None and user_home is not None:
        raise ValueError(
            "Provide exactly one of project_root or user_home, not both"
        )
    if project_root is None and user_home is None:
        raise ValueError(
            "Exactly one of project_root or user_home must be provided"
        )

    # Step 1: preflight skill source — must exist and be non-empty.
    src_bytes = _read_skill_bytes()
    if not src_bytes:
        raise FileNotFoundError(f"SKILL.md is empty in package")

    project_suffix, user_suffix = HARNESS_MAP[harness]

    if project_root is not None:
        skill_path = _build_path(project_root, project_suffix) / SKILL_NAME
        stop_root = project_root
    else:
        skill_path = _build_path(user_home, user_suffix) / SKILL_NAME
        stop_root = user_home

    # Step 2: preflight skill target — symlink checks, no mutation.
    _preflight_skill_for_install(skill_path, stop_root)

    # Step 3: preflight MCP config — raises ValueError for foreign entry
    # or malformed/symlinked config *before* we write anything.
    mcp_result = install_server(
        harness, project_root=project_root, user_home=user_home, force=force,
    )

    # Step 4: write the skill (safe — both domains preflighted).
    _install_one(skill_path, stop_root, src_bytes, force)
    return skill_path / "SKILL.md", mcp_result



def uninstall(
    harness: str,
    *,
    project_root: Path | None = None,
    user_home: Path | None = None,
) -> Path:
    """Remove the JEV skill and MCP registration from the *harness*'s destination.

    Preflights the MCP configuration and removes the skill plus a canonical
    ``jev`` MCP server entry.  Foreign MCP entries are reported but not mutated.

    Exactly one of *project_root* or *user_home* must be provided.
    *project_root* targets the harness's project path only.
    *user_home* targets the harness's user path only.

    Returns
    -------
    Path
        The target ``SKILL.md`` path that was removed.
    """
    skill_path, _result = uninstall_with_report(
        harness, project_root=project_root, user_home=user_home,
    )
    return skill_path


def uninstall_with_report(
    harness: str,
    *,
    project_root: Path | None = None,
    user_home: Path | None = None,
) -> Tuple[Path, RegistrationResult]:
    """Uninstall the JEV skill and MCP registration, returning the report.

    Preflights **both** the skill target and the MCP configuration before
    any mutation.  A failure in either domain leaves **no partial state**:
    no skill deletion and no MCP config mutation.

    Returns a ``(skill_path, registration_result)`` tuple where *registration_*
    *result* describes the MCP registration outcome.
    """
    if harness not in VALID_HARNESSES:
        raise ValueError(f"Unknown harness {harness!r}; expected one of {sorted(VALID_HARNESSES)}")

    if project_root is not None and user_home is not None:
        raise ValueError(
            "Provide exactly one of project_root or user_home, not both"
        )
    if project_root is None and user_home is None:
        raise ValueError(
            "Exactly one of project_root or user_home must be provided"
        )

    project_suffix, user_suffix = HARNESS_MAP[harness]
    stop_root = project_root if project_root is not None else user_home  # type: ignore[assignment]

    # Step 1: preflight skill target — symlink checks, no mutation.
    skill_target = _build_path(stop_root, project_suffix if project_root is not None else user_suffix) / SKILL_NAME
    _preflight_skill_for_uninstall(skill_target, stop_root)

    # Step 2: classify MCP config — raises on malformed/symlinked config.
    mcp_result = uninstall_server(
        harness, project_root=project_root, user_home=user_home,
    )

    # Step 3: safe to delete skill — both domains preflighted.
    _uninstall_one(skill_target, stop_root)
    return skill_target / "SKILL.md", mcp_result


# ---------------------------------------------------------------------------
# Install / Uninstall internals
# ---------------------------------------------------------------------------


def _preflight_skill_for_install(target: Path, stop_root: Path) -> None:
    """Raise if the skill target path has unsafe symlink ancestry.

    Read-only preflight: no files are created or modified.  Mirrors the
    symlink check that ``_install_one`` performs, extracted so it can be
    called **before** MCP config mutation.
    """
    # Check full symlink chain from target up to stop_root.
    _find_symlink_ancestry(target, stop_root)


def _preflight_skill_for_uninstall(target: Path, stop_root: Path) -> None:
    """Raise if the skill target or its symlink ancestry is unsafe.

    Read-only preflight: no files are deleted or modified.  Mirrors the
    symlink and structural checks that ``_uninstall_one`` performs,
    extracted so they can be called **before** MCP mutation.
    """
    if not target.exists():
        return

    # Check full symlink chain from target up to stop_root.
    _find_symlink_ancestry(target, stop_root)

    # Ensure SKILL.md is not itself a symlink.
    skill_md = target / "SKILL.md"
    if skill_md.is_symlink():
        raise RuntimeError(f"Cannot uninstall: {skill_md} is a symlink")


def _install_one(target: Path, stop_root: Path, content: bytes, force: bool) -> None:
    """Write *content* into ``<target>/SKILL.md``."""
    dest = target / "SKILL.md"

    # Check symlinks for every existing component from target up toward stop_root.
    _find_symlink_ancestry(target, stop_root)

    if target.exists():
        if not force:
            return  # already installed — idempotent
        # Force: remove old content first.
        _ensure_symlink_free(target)
        if target.is_dir():
            shutil.rmtree(target)
        elif target.is_file():
            target.unlink()

    target.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)


def _uninstall_one(target: Path, stop_root: Path) -> None:
    """Remove only SKILL.md inside *target* (the skill dir), prune empty parents up to *stop_root*.

    Checks the full symlink ancestry of *target* before removing anything.
    Only removes the SKILL.md file and the skill directory if it becomes empty.
    Prunes empty parent directories up to (but not including) *stop_root*.
    """
    if not target.exists():
        return

    # Check full symlink chain from target up to stop_root.
    _find_symlink_ancestry(target, stop_root)

    # Only remove SKILL.md inside the skill directory.
    skill_md = target / "SKILL.md"
    if skill_md.is_symlink():
        raise RuntimeError(f"Cannot uninstall: {skill_md} is a symlink")
    if skill_md.is_file():
        skill_md.unlink()

    # Remove the skill directory only if it is now empty.
    if target.is_dir() and not any(target.iterdir()):
        try:
            target.rmdir()
        except OSError:
            pass  # race condition: not empty anymore

    # Prune empty parents up to (but not including) stop_root.
    cur = target.parent
    while cur != stop_root and cur != cur.parent:
        try:
            cur.rmdir()
        except OSError:
            break  # not empty → stop
        cur = cur.parent


