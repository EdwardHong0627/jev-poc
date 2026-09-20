"""Pure recording-path rules for SQLite investigation logging.

This module is a dependency leaf: it imports neither
``jev_bot.mcp_registration`` nor ``jev_bot.installer`` (both of which import
it), reads no filesystem state, and mutates nothing.  It returns the single
absolute ``SQLITE_DB`` path that the audit-first install default records
successful ``jev_decide`` requests and shaped responses into:

- project scope: ``<resolved project root>/SQLITE_DB``;
- user scope: ``$XDG_DATA_HOME/jev-poc/SQLITE_DB`` when ``XDG_DATA_HOME`` is
  set to an absolute path, otherwise
  ``<resolved user home>/.local/share/jev-poc/SQLITE_DB``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

# Filename of the SQLite investigation database used by every scope.
SQLITE_DB_FILENAME = "SQLITE_DB"

# Directory name owned by this project under the user data root.
USER_DATA_DIR_NAME = "jev-poc"

# XDG Base Directory environment variable consulted for user scope.
XDG_DATA_HOME_ENV = "XDG_DATA_HOME"

# Fallback data root (relative to the user home) when XDG_DATA_HOME is unset.
_DEFAULT_DATA_SUBPATH = (".local", "share")


def resolve_sqlite_db_path(
    *,
    project_root: Path | None = None,
    user_home: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Return the absolute SQLite investigation database path for one scope.

    Exactly one of *project_root* or *user_home* must be provided, mirroring
    the installer's scope contract.

    * ``project_root`` — resolves to ``<resolved project root>/SQLITE_DB``.
    * ``user_home`` — resolves to ``$XDG_DATA_HOME/jev-poc/SQLITE_DB`` when
      ``XDG_DATA_HOME`` names an absolute path, otherwise to
      ``<resolved user home>/.local/share/jev-poc/SQLITE_DB``.

    *environ* defaults to the process environment.  Pure function: nothing is
    created, read from, or symlink-resolved against the filesystem beyond the
    textual normalisation performed by :meth:`pathlib.Path.resolve`.

    Raises
    ------
    ValueError
        When both or neither scope root is given, or when ``XDG_DATA_HOME``
        is set to a relative path (a relative data root would make the
        generated MCP configuration depend on the launcher's cwd).
    """
    if project_root is not None and user_home is not None:
        raise ValueError(
            "Provide exactly one of project_root or user_home, not both"
        )
    if project_root is None and user_home is None:
        raise ValueError(
            "Exactly one of project_root or user_home must be provided"
        )

    if environ is None:
        environ = os.environ

    if project_root is not None:
        return Path(project_root).resolve() / SQLITE_DB_FILENAME

    home = Path(user_home).resolve()  # type: ignore[arg-type]
    xdg_raw = (environ.get(XDG_DATA_HOME_ENV) or "").strip()
    if xdg_raw:
        xdg = Path(xdg_raw)
        if not xdg.is_absolute():
            raise ValueError(
                f"{XDG_DATA_HOME_ENV} must be an absolute path when set, "
                f"got {xdg_raw!r}"
            )
        return xdg.resolve() / USER_DATA_DIR_NAME / SQLITE_DB_FILENAME
    return home.joinpath(*_DEFAULT_DATA_SUBPATH, USER_DATA_DIR_NAME, SQLITE_DB_FILENAME)
