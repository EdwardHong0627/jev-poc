"""Tests for jev_bot.investigation_logging — pure SQLite recording-path rules.

The resolver is a pure leaf module: it reads only the explicit arguments and
the supplied environment mapping, performs no filesystem mutation, and returns
absolute database paths for exactly one scope.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jev_bot.investigation_logging import (
    SQLITE_DB_FILENAME,
    USER_DATA_DIR_NAME,
    resolve_sqlite_db_path,
)


# ── Constants ───────────────────────────────────────────────────────


class TestConstants:
    def test_database_filename(self) -> None:
        assert SQLITE_DB_FILENAME == "SQLITE_DB"

    def test_user_data_dir_name(self) -> None:
        assert USER_DATA_DIR_NAME == "jev-poc"


# ── Project scope ───────────────────────────────────────────────────


class TestProjectScope:
    def test_resolves_to_absolute_sqlite_db_child(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()

        resolved = resolve_sqlite_db_path(project_root=project, environ={})

        assert resolved == project.resolve() / "SQLITE_DB"
        assert resolved.is_absolute()

    def test_nonexistent_project_root_still_absolute(self, tmp_path: Path) -> None:
        """Resolution is pure — it never requires the project to exist."""
        project = tmp_path / "not-created-yet"

        resolved = resolve_sqlite_db_path(project_root=project, environ={})

        assert resolved.is_absolute()
        assert resolved.name == "SQLITE_DB"
        assert not project.exists()  # resolution created nothing

    def test_project_scope_ignores_xdg_data_home(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()

        resolved = resolve_sqlite_db_path(
            project_root=project,
            environ={"XDG_DATA_HOME": "/some/other/place"},
        )

        assert resolved == project.resolve() / "SQLITE_DB"

    def test_relative_project_root_is_made_absolute(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "rel-proj").mkdir()

        resolved = resolve_sqlite_db_path(project_root=Path("rel-proj"), environ={})

        assert resolved == (tmp_path / "rel-proj").resolve() / "SQLITE_DB"
        assert resolved.is_absolute()


# ── User scope ──────────────────────────────────────────────────────


class TestUserScope:
    def test_absolute_xdg_data_home_is_used(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        home.mkdir()
        xdg = tmp_path / "xdg-data"

        resolved = resolve_sqlite_db_path(
            user_home=home,
            environ={"XDG_DATA_HOME": str(xdg)},
        )

        assert resolved == xdg.resolve() / "jev-poc" / "SQLITE_DB"
        assert resolved.is_absolute()

    def test_fallback_to_local_share_when_unset(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        home.mkdir()

        resolved = resolve_sqlite_db_path(user_home=home, environ={})

        assert resolved == home.resolve() / ".local" / "share" / "jev-poc" / "SQLITE_DB"
        assert resolved.is_absolute()

    def test_fallback_when_xdg_blank_or_whitespace(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        home.mkdir()

        for blank in ("", "   "):
            resolved = resolve_sqlite_db_path(
                user_home=home,
                environ={"XDG_DATA_HOME": blank},
            )
            assert resolved == home.resolve() / ".local" / "share" / "jev-poc" / "SQLITE_DB"

    @pytest.mark.parametrize("relative", ["relative/data", ".", "..", "./x", "~/data"])
    def test_relative_xdg_data_home_rejected(self, tmp_path: Path, relative: str) -> None:
        home = tmp_path / "home"
        home.mkdir()

        with pytest.raises(ValueError, match="absolute"):
            resolve_sqlite_db_path(
                user_home=home,
                environ={"XDG_DATA_HOME": relative},
            )


# ── Scope validation / purity ───────────────────────────────────────


class TestScopeValidation:
    def test_neither_scope(self) -> None:
        with pytest.raises(ValueError, match="Exactly one"):
            resolve_sqlite_db_path()

    def test_both_scopes(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="not both"):
            resolve_sqlite_db_path(project_root=tmp_path, user_home=tmp_path)

    def test_environ_defaults_to_process_environment(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        home = tmp_path / "home"
        home.mkdir()
        xdg = tmp_path / "xdg-env"
        monkeypatch.setenv("XDG_DATA_HOME", str(xdg))

        resolved = resolve_sqlite_db_path(user_home=home)

        assert resolved == xdg / "jev-poc" / "SQLITE_DB"

    def test_resolver_creates_nothing_on_disk(self, tmp_path: Path) -> None:
        project = tmp_path / "fresh-project"

        resolve_sqlite_db_path(project_root=project, environ={})

        assert not project.exists()
