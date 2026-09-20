"""JEV installer — package-native skill installation for four harnesses.

Coordinates skill installation with MCP server registration and, for the
audit-first default (``db_enable=True``), SQLite investigation-recording
preparation: an absolute database path resolved per scope, a private
user data directory for user scope, and an idempotent ``SQLITE_DB``
``.gitignore`` rule for project scope.
"""

from __future__ import annotations

import importlib.resources
import os
import shutil
import stat
import tempfile
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Tuple

from jev_bot.investigation_logging import (
    SQLITE_DB_FILENAME,
    resolve_sqlite_db_path,
)
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
    db_enable: bool = True,
) -> Path:
    """Install the JEV skill and MCP registration into the *harness*'s destination.

    Preflights the MCP configuration and installs the skill plus a canonical
    ``jev`` MCP server entry.  A pre-existing foreign MCP entry raises a
    ``ValueError`` *before* any skill directory is created (unless *force* is
    ``True``, which replaces only that MCP entry).

    Exactly one of *project_root* or *user_home* must be provided.
    *project_root* targets the harness's project path only.
    *user_home* targets the harness's user path only.

    *db_enable* (audit-first default ``True``) records successful ``jev_decide``
    requests/responses: the MCP entry gains ``--sqlite-db`` at the scope-resolved
    absolute path, and the destination is prepared (project ``.gitignore`` rule /
    private user data directory) before any mutation.

    Returns
    -------
    Path
        The target ``SKILL.md`` path that was written.
    """
    skill_path, _result = install_with_report(
        harness, project_root=project_root, user_home=user_home,
        force=force, db_enable=db_enable,
    )
    return skill_path


def install_with_report(
    harness: str,
    *,
    project_root: Path | None = None,
    user_home: Path | None = None,
    force: bool = False,
    db_enable: bool = True,
) -> Tuple[Path, RegistrationResult]:
    """Install the JEV skill and MCP registration, returning the report.

    Preflights the skill source, the skill target, and (when *db_enable*) the
    recording destination — all before any filesystem mutation.  A failure in
    any domain leaves **no partial state** (no skill directory, no MCP config
    change, no ``.gitignore`` or data-directory change).

    *db_enable* defaults to ``True`` (audit-first): the canonical MCP entry is
    written with ``--sqlite-db`` at the scope-resolved absolute database path.
    ``False`` preserves the historical disabled launcher byte-for-byte and never
    creates or deletes recording artifacts.

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

    # Step 3: resolve and preflight the recording destination — raises before
    # any mutation for relative XDG paths, symlinked or conflicting targets.
    plan: _RecordingPlan | None = None
    if db_enable:
        database_path = resolve_sqlite_db_path(
            project_root=project_root, user_home=user_home
        )
        plan = _preflight_recording(
            database_path, project_root=project_root, user_home=user_home
        )

    # Step 4: preflight + migrate MCP config — raises ValueError for a foreign
    # entry or malformed/symlinked config *before* we write the skill.
    mcp_result = install_server(
        harness,
        project_root=project_root,
        user_home=user_home,
        force=force,
        db_enable=db_enable,
        sqlite_db_path=plan.database_path if plan is not None else None,
    )

    # Step 5: write the skill (safe — all domains preflighted).
    _install_one(skill_path, stop_root, src_bytes, force)

    # Step 6: apply the prepared .gitignore rule / private data directory.
    if plan is not None:
        _apply_recording(plan)

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


class _RecordingPlan:
    """Validated recording destinations prepared before any mutation."""

    __slots__ = ("database_path", "gitignore_path", "gitignore_bytes", "data_dir")

    def __init__(
        self,
        database_path: Path,
        gitignore_path: Path | None = None,
        gitignore_bytes: bytes | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self.database_path = database_path
        self.gitignore_path = gitignore_path
        self.gitignore_bytes = gitignore_bytes
        self.data_dir = data_dir


def _ensure_no_symlink(path: Path, label: str) -> None:
    """Reject *path* itself being a symlink before it is created or written."""
    if path.is_symlink():
        raise RuntimeError(f"Cannot install: {label} is a symlink: {path}")


def _gitignore_update(existing: bytes | None) -> bytes | None:
    """Return new ``.gitignore`` bytes covering ``SQLITE_DB``, or ``None``.

    ``None`` means the exact active rule already exists — the file is then
    left byte-identical (idempotent, no duplicate rule).  Otherwise the
    original bytes and newline style are preserved and the rule is appended
    on its own final line.
    """
    rule = SQLITE_DB_FILENAME
    if existing is not None:
        text = existing.decode("utf-8")
        for line in text.splitlines():
            if line.strip() == rule:
                return None
        prefix = existing
        if not text.endswith(("\n", "\r")):
            prefix += b"\n"
        return prefix + rule.encode("utf-8") + b"\n"
    return rule.encode("utf-8") + b"\n"


def _preflight_recording(
    database_path: Path,
    *,
    project_root: Path | None,
    user_home: Path | None,
) -> _RecordingPlan:
    """Validate recording destinations before any install mutation occurs.

    Both scopes reject a symlinked or directory-shaped database path.
    Project scope additionally requires a non-symlink non-directory
    ``.gitignore`` (read now; the prepared update is written only after the
    skill installs).  User scope requires a symlink-free data directory
    (created, mode ``0700``, only after the skill installs) that is not a
    regular file.
    """
    _ensure_no_symlink(database_path, "SQLite database path")
    if database_path.is_dir():
        raise RuntimeError(
            f"Cannot install: SQLite database path is a directory: {database_path}"
        )

    if project_root is not None:
        gitignore = project_root / ".gitignore"
        _ensure_no_symlink(gitignore, "project .gitignore")
        if gitignore.is_dir():
            raise RuntimeError(
                f"Cannot install: {gitignore} is a directory, not a file"
            )
        existing = gitignore.read_bytes() if gitignore.is_file() else None
        return _RecordingPlan(
            database_path=database_path,
            gitignore_path=gitignore,
            gitignore_bytes=_gitignore_update(existing),
        )

    assert user_home is not None  # callers enforce exactly one scope
    data_dir = database_path.parent
    # Every existing component from the data directory up to (but excluding)
    # the user home must be a real directory or absent — never a symlink.
    _find_symlink_ancestry(data_dir, user_home)
    _ensure_no_symlink(data_dir, "user data directory")
    _ensure_dir_ancestry(data_dir, user_home)
    return _RecordingPlan(database_path=database_path, data_dir=data_dir)


def _ensure_dir_ancestry(data_dir: Path, user_home: Path) -> None:
    """Reject a data directory whose self-or-ancestor up to *user_home* is a file.

    ``Path.exists()``/``is_dir()`` swallow ``ENOTDIR`` (a regular file
    *ancestor* makes the child look absent), so the walk uses ``lstat``
    directly: ``NotADirectoryError`` or a non-directory mode at any existing
    component raises ``ValueError`` before any mutation occurs.
    """
    cur = data_dir
    while cur != user_home and cur != cur.parent:
        try:
            st = os.lstat(cur)
        except FileNotFoundError:
            cur = cur.parent
            continue
        except NotADirectoryError:
            raise ValueError(
                f"Cannot install: an ancestor of user data directory "
                f"{data_dir} is a regular file"
            )
        if not stat.S_ISDIR(st.st_mode):
            raise ValueError(
                f"Cannot install: user data directory {cur} is not a directory"
            )
        cur = cur.parent


def _apply_recording(plan: _RecordingPlan) -> None:
    """Apply the preflighted recording changes after the skill is installed."""
    if plan.gitignore_path is not None and plan.gitignore_bytes is not None:
        _write_bytes_atomic(plan.gitignore_path, plan.gitignore_bytes)
    if plan.data_dir is not None:
        _ensure_private_dir(plan.data_dir)


def _write_bytes_atomic(path: Path, content: bytes) -> None:
    """Atomically replace *path* with *content*, preserving its file mode."""
    _ensure_no_symlink(path, str(path))
    mode = (path.stat().st_mode & 0o777) if path.is_file() else 0o644
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _ensure_private_dir(path: Path) -> None:
    """Create *path* (parents included) and pin it to mode ``0700``."""
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)


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


