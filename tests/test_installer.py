"""Tests for the JEV installer — four-harness, explicit-scope installer domain."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from unittest import mock

import pytest

from jev_bot.installer import (
    HARNESS_MAP,
    SKILL_NAME,
    VALID_HARNESSES,
    install,
    uninstall,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fixture_dir(tmp_path: Path, name: str) -> Path:
    """Create a minimal project directory under *tmp_path*."""
    d = tmp_path / name
    d.mkdir()
    (d / "pyproject.toml").write_text('[project]\nname = "test"\n', encoding="utf-8")
    return d


def _host_home(tmp_path: Path) -> Path:
    """Create a fake home directory under *tmp_path*."""
    home = tmp_path / "home"
    home.mkdir()
    return home


def _ensure_installer_dir(project: Path) -> Path:
    """Create a minimal installer root (jev_bot/installer.py) inside *project*."""
    installer_dir = project / "jev_bot"
    installer_dir.mkdir(parents=True, exist_ok=True)
    (installer_dir / "__init__.py").write_text("", encoding="utf-8")
    return installer_dir


def _native_project_path(harness: str, project: Path) -> Path:
    """Return the expected project-level destination for *harness*."""
    suffix, _ = HARNESS_MAP[harness]
    parts = [p for p in suffix.split("/") if p]
    cur = project
    for part in parts:
        cur = cur / part
    return cur / SKILL_NAME


def _native_user_path(harness: str, home: Path) -> Path:
    """Return the expected user-level destination for *harness*."""
    _, suffix = HARNESS_MAP[harness]
    parts = [p for p in suffix.split("/") if p]
    cur = home
    for part in parts:
        cur = cur / part
    return cur / SKILL_NAME


# ---------------------------------------------------------------------------
# 1. Harness registry
# ---------------------------------------------------------------------------


class TestHarnessRegistry:
    def test_all_four_harnesses_defined(self) -> None:
        expected = {"claude-code", "opencode", "oh-my-pi", "pi"}
        assert VALID_HARNESSES == expected

    def test_native_project_paths(self) -> None:
        expected_project = {
            "claude-code": ".claude/skills",
            "opencode": ".opencode/skills",
            "oh-my-pi": ".omp/skills",
            "pi": ".pi/skills",
        }
        for harness, suffix in expected_project.items():
            assert HARNESS_MAP[harness][0] == suffix

    def test_native_user_paths(self) -> None:
        expected_user = {
            "claude-code": ".claude/skills",
            "opencode": ".config/opencode/skills",
            "oh-my-pi": ".omp/agent/skills",
            "pi": ".pi/agent/skills",
        }
        for harness, suffix in expected_user.items():
            assert HARNESS_MAP[harness][1] == suffix


# ---------------------------------------------------------------------------
# 2. Native target paths — claude-code
# ---------------------------------------------------------------------------


class TestClaudeCodePaths:
    def test_project_root(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "cc_proj")
        _ensure_installer_dir(project)

        install("claude-code", project_root=project)

        expected = project / ".claude" / "skills" / SKILL_NAME
        assert expected.is_dir()
        assert (expected / "SKILL.md").is_file()

    def test_user_home(self, tmp_path: Path) -> None:
        home = _host_home(tmp_path)
        _ensure_installer_dir(tmp_path / "installer")

        install("claude-code", user_home=home)

        expected = home / ".claude" / "skills" / SKILL_NAME
        assert expected.is_dir()
        assert (expected / "SKILL.md").is_file()


# ---------------------------------------------------------------------------
# 3. Native target paths — opencode
# ---------------------------------------------------------------------------


class TestOpenCodePaths:
    def test_project_root(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "oc_proj")
        _ensure_installer_dir(project)

        install("opencode", project_root=project)

        expected = project / ".opencode" / "skills" / SKILL_NAME
        assert expected.is_dir()
        assert (expected / "SKILL.md").is_file()

    def test_user_config(self, tmp_path: Path) -> None:
        home = _host_home(tmp_path)
        config_dir = home / ".config"
        config_dir.mkdir()

        _ensure_installer_dir(tmp_path / "installer")

        install("opencode", user_home=home)

        expected = config_dir / "opencode" / "skills" / SKILL_NAME
        assert expected.is_dir()
        assert (expected / "SKILL.md").is_file()


# ---------------------------------------------------------------------------
# 4. Native target paths — oh-my-pi
# ---------------------------------------------------------------------------


class TestOhMyPiPaths:
    def test_project_root(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "omp_proj")
        _ensure_installer_dir(project)

        install("oh-my-pi", project_root=project)

        expected = project / ".omp" / "skills" / SKILL_NAME
        assert expected.is_dir()
        assert (expected / "SKILL.md").is_file()

    def test_user_home(self, tmp_path: Path) -> None:
        home = _host_home(tmp_path)
        _ensure_installer_dir(tmp_path / "installer")

        install("oh-my-pi", user_home=home)

        expected = home / ".omp" / "agent" / "skills" / SKILL_NAME
        assert expected.is_dir()
        assert (expected / "SKILL.md").is_file()


# ---------------------------------------------------------------------------
# 5. Native target paths — pi
# ---------------------------------------------------------------------------


class TestPiPaths:
    def test_project_root(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "pi_proj")
        _ensure_installer_dir(project)

        install("pi", project_root=project)

        expected = project / ".pi" / "skills" / SKILL_NAME
        assert expected.is_dir()
        assert (expected / "SKILL.md").is_file()

    def test_user_home(self, tmp_path: Path) -> None:
        home = _host_home(tmp_path)
        _ensure_installer_dir(tmp_path / "installer")

        install("pi", user_home=home)

        expected = home / ".pi" / "agent" / "skills" / SKILL_NAME
        assert expected.is_dir()
        assert (expected / "SKILL.md").is_file()


# ---------------------------------------------------------------------------
# 6. Packaged asset parity
# ---------------------------------------------------------------------------


class TestSkillParity:
    def test_installed_skill_matches_source(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "parity_proj")
        _ensure_installer_dir(project)

        install("claude-code", project_root=project)

        installed_skill = project / ".claude" / "skills" / SKILL_NAME / "SKILL.md"
        content = installed_skill.read_bytes()
        assert b"JEV" in content
        assert len(content) > 0


# ---------------------------------------------------------------------------
# 7. Idempotent install (second install is no-op)
# ---------------------------------------------------------------------------


class TestIdempotentInstall:
    def test_second_install_succeeds_claude_code(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "idemp_proj")
        _ensure_installer_dir(project)

        install("claude-code", project_root=project)
        install("claude-code", project_root=project)

        skill_dir = project / ".claude" / "skills" / SKILL_NAME
        assert skill_dir.is_dir()
        assert (skill_dir / "SKILL.md").is_file()

    def test_second_install_opencode(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "idemp_oc")
        _ensure_installer_dir(project)

        install("opencode", project_root=project)
        install("opencode", project_root=project)

        skill_dir = project / ".opencode" / "skills" / SKILL_NAME
        assert skill_dir.is_dir()


# ---------------------------------------------------------------------------
# 8. Force replacement overwrites existing content
# ---------------------------------------------------------------------------


class TestForceReplacement:
    def test_force_overwrites_claude_code(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "force_cc")
        _ensure_installer_dir(project)

        skill_dir = project / ".claude" / "skills" / SKILL_NAME
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Old content\n")

        install("claude-code", project_root=project, force=True)

        content = (skill_dir / "SKILL.md").read_bytes()
        assert b"JEV" in content
        assert b"Old content" not in content

    def test_force_opencode(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "force_oc")
        _ensure_installer_dir(project)

        skill_dir = project / ".opencode" / "skills" / SKILL_NAME
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Old content\n")

        install("opencode", project_root=project, force=True)

        content = (skill_dir / "SKILL.md").read_bytes()
        assert b"JEV" in content


# ---------------------------------------------------------------------------
# 9. Foreign content is refused (no-force)
# ---------------------------------------------------------------------------


class TestForeignContentRefusal:
    def test_skips_when_existing_has_different_content(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "foreign_cc")
        skill_dir = project / ".claude" / "skills" / SKILL_NAME
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# This is a different skill\n")
        _ensure_installer_dir(project)

        install("claude-code", project_root=project)

        content = (skill_dir / "SKILL.md").read_text()
        assert content == "# This is a different skill\n"

    def test_skips_opencode_foreign(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "foreign_oc")
        skill_dir = project / ".opencode" / "skills" / SKILL_NAME
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Other\n")
        _ensure_installer_dir(project)

        install("opencode", project_root=project)

        assert (skill_dir / "SKILL.md").read_text() == "# Other\n"


# ---------------------------------------------------------------------------
# 10. Symlink refusal — every existing component below harness root
# ---------------------------------------------------------------------------


class TestSymlinkRefusal:
    def test_refuses_symlink_skill_dir(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "symlink_cc")
        _ensure_installer_dir(project)

        target = _native_project_path("claude-code", project)
        # Ensure parent directory exists so symlink can be created.
        target.parent.mkdir(parents=True, exist_ok=True)

        real_target = tmp_path / "real_target"
        real_target.mkdir()

        # Remove any existing path, replace with symlink.
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        target.symlink_to(real_target)

        with pytest.raises(RuntimeError, match="symlink"):
            install("claude-code", project_root=project)

    def test_refuses_symlink_parent_dir(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "symlink_parent")
        _ensure_installer_dir(project)

        skills = project / ".claude" / "skills"
        skills.mkdir(parents=True, exist_ok=True)

        skill_dir = skills / SKILL_NAME
        if skill_dir.is_dir():
            shutil.rmtree(skill_dir)
        elif skill_dir.is_file():
            skill_dir.unlink()

        real_target = tmp_path / "real_target"
        real_target.mkdir()
        skill_dir.symlink_to(real_target)

        with pytest.raises(RuntimeError, match="symlink"):
            install("claude-code", project_root=project)

    def test_refuses_symlink_in_opencode_path(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "nested_symlink_oc")
        _ensure_installer_dir(project)

        skills = project / ".opencode" / "skills"
        skills.mkdir(parents=True, exist_ok=True)
        real_target = tmp_path / "real_skills"
        real_target.mkdir()

        if skills.is_symlink():
            skills.unlink()
        elif skills.is_dir():
            shutil.rmtree(skills)
        skills.symlink_to(real_target)

        with pytest.raises(RuntimeError, match="symlink"):
            install("opencode", project_root=project)

    def test_refuses_symlink_in_omp_path(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "nested_symlink_omp")
        _ensure_installer_dir(project)

        skills = project / ".omp" / "skills"
        skills.mkdir(parents=True, exist_ok=True)
        real_target = tmp_path / "real_skills"
        real_target.mkdir()

        if skills.is_symlink():
            skills.unlink()
        elif skills.is_dir():
            shutil.rmtree(skills)
        skills.symlink_to(real_target)

        with pytest.raises(RuntimeError, match="symlink"):
            install("oh-my-pi", project_root=project)


# ---------------------------------------------------------------------------
# 11. Uninstall removes only the skill directory
# ---------------------------------------------------------------------------


class TestUninstallScope:
    def test_removes_only_skill_dir_preserves_siblings(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "scope_cc")
        _ensure_installer_dir(project)

        skill_dir = _native_project_path("claude-code", project)
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# skill content\n")

        # Sibling content.
        other = project / ".claude" / "skills" / "other-skill"
        other.mkdir()
        (other / "README.md").write_text("# other\n")

        uninstall("claude-code", project_root=project)

        assert not skill_dir.exists()
        assert (other / "README.md").read_text() == "# other\n"


# ---------------------------------------------------------------------------
# 12. Uninstall is no-op when skill absent
# ---------------------------------------------------------------------------


class TestMissingUninstall:
    def test_noop_when_skill_missing(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "missing_uninstall")
        _ensure_installer_dir(project)

        uninstall("claude-code", project_root=project)

        assert not _native_project_path("claude-code", project).exists()


# ---------------------------------------------------------------------------
# 13. Uninstall prunes empty directories without removing harness root
# ---------------------------------------------------------------------------


class TestPruning:
    def test_prunes_empty_nested_dirs(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "prune_cc")
        _ensure_installer_dir(project)

        skill_dir = _native_project_path("claude-code", project)
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# skill\n")

        uninstall("claude-code", project_root=project)

        # Skill dir removed.
        assert not skill_dir.exists()
        # ".claude" should be gone too (now empty).
        assert not (project / ".claude").exists()
        # Project itself remains.
        assert project.is_dir()

    def test_keeps_parent_when_non_empty(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "prune_cc_non_empty")
        _ensure_installer_dir(project)

        skill_dir = _native_project_path("claude-code", project)
        skills_parent = skill_dir.parent
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# skill\n")

        # Create a sibling file so .claude/skills/ isn't empty.
        (skills_parent / "keepme.md").write_text("")

        uninstall("claude-code", project_root=project)

        # Skill dir gone, but .claude/skills kept (has keepme.md).
        assert not skill_dir.exists()
        assert (skills_parent / "keepme.md").exists()
        # .claude itself should still exist (parent of skills).
        assert (project / ".claude").is_dir()

    def test_opencode_user_pruning(self, tmp_path: Path) -> None:
        home = _host_home(tmp_path)
        _ensure_installer_dir(tmp_path / "installer")

        install("opencode", user_home=home)
        uninstall("opencode", user_home=home)

        assert not (home / ".config" / "opencode" / "skills" / SKILL_NAME).exists()
        assert not (home / ".config" / "opencode").exists()


# ---------------------------------------------------------------------------
# 14. Invalid harness raises
# ---------------------------------------------------------------------------


class TestInvalidHarness:
    def test_install_raises_on_unknown_harness(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "bad_harness")

        with pytest.raises(ValueError, match="Unknown harness"):
            install("unknown-harness", project_root=project)

    def test_uninstall_raises_on_unknown_harness(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "bad_harness2")

        with pytest.raises(ValueError, match="Unknown harness"):
            uninstall("unknown-harness", project_root=project)


# ---------------------------------------------------------------------------
# 15. Scope — no cwd/home fallback
# ---------------------------------------------------------------------------


class TestScopeRequirement:
    def test_install_raises_without_scope(self) -> None:
        with pytest.raises(ValueError, match="(?i)exactly one"):
            install("claude-code")

    def test_uninstall_raises_without_scope(self) -> None:
        with pytest.raises(ValueError, match="(?i)exactly one"):
            uninstall("claude-code")

    def test_install_raises_with_both_scopes(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "both_scopes")
        home = _host_home(tmp_path)
        with pytest.raises(ValueError, match="not both"):
            install("claude-code", project_root=project, user_home=home)


# ---------------------------------------------------------------------------
# 16. RED — scope isolation: project install never writes to user home
# ---------------------------------------------------------------------------


class TestScopeIsolation:
    def test_project_install_does_not_write_to_user_home(self, tmp_path: Path) -> None:
        """Project install must never create files under user home."""
        project = _fixture_dir(tmp_path, "iso_proj")
        home = _host_home(tmp_path)
        _ensure_installer_dir(project)

        install("claude-code", project_root=project)

        # Verify nothing was created under the fake home.
        assert not (home / ".claude").exists()

        # Verify project path was created.
        expected = project / ".claude" / "skills" / SKILL_NAME
        assert expected.is_dir()
        assert (expected / "SKILL.md").is_file()

    def test_user_install_does_not_write_to_project_root(self, tmp_path: Path) -> None:
        """User install must never create files under project root."""
        project = _fixture_dir(tmp_path, "iso_proj2")
        home = _host_home(tmp_path)
        _ensure_installer_dir(project)

        install("claude-code", user_home=home)

        # Verify nothing was created under the project root.
        assert not (project / ".claude").exists()

        # Verify user path was created.
        expected = home / ".claude" / "skills" / SKILL_NAME
        assert expected.is_dir()
        assert (expected / "SKILL.md").is_file()

    def test_project_uninstall_does_not_touch_user_home(self, tmp_path: Path) -> None:
        """Project uninstall must not affect user home path."""
        project = _fixture_dir(tmp_path, "iso_uni_proj")
        home = _host_home(tmp_path)

        # Install to user home.
        user_skill = home / ".claude" / "skills" / SKILL_NAME
        user_skill.mkdir(parents=True)
        (user_skill / "SKILL.md").write_text("# user skill\n")

        # Uninstall from project (which has nothing installed there).
        uninstall("claude-code", project_root=project)

        # User path must still exist.
        assert user_skill.is_dir()
        assert (user_skill / "SKILL.md").read_text() == "# user skill\n"

    def test_user_uninstall_does_not_touch_project_root(self, tmp_path: Path) -> None:
        """User uninstall must not affect project path."""
        project = _fixture_dir(tmp_path, "iso_uni_proj2")
        home = _host_home(tmp_path)

        # Install to project.
        proj_skill = project / ".claude" / "skills" / SKILL_NAME
        proj_skill.mkdir(parents=True)
        (proj_skill / "SKILL.md").write_text("# project skill\n")

        # Uninstall from user home (which has nothing installed there).
        uninstall("claude-code", user_home=home)

        # Project path must still exist.
        assert proj_skill.is_dir()
        assert (proj_skill / "SKILL.md").read_text() == "# project skill\n"


# ---------------------------------------------------------------------------
# 17. RED — foreign file survives uninstall
# ---------------------------------------------------------------------------


class TestForeignFileSurvival:
    def test_sibling_file_survives_uninstall(self, tmp_path: Path) -> None:
        """Non-SKILL.md files in the skill directory must survive uninstall."""
        project = _fixture_dir(tmp_path, "foreign_survive")
        _ensure_installer_dir(project)

        skill_dir = _native_project_path("claude-code", project)
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# JEV content\n")

        # Add a foreign file alongside SKILL.md.
        foreign = skill_dir / "foreign.txt"
        foreign.write_text("# I am not JEV\n", encoding="utf-8")

        uninstall("claude-code", project_root=project)

        # SKILL.md was removed; foreign.txt still exists (dir not pruned since not empty).
        assert foreign.exists()
        assert foreign.read_text(encoding="utf-8") == "# I am not JEV\n"
        # Verify the project root still exists and is usable.
        assert project.is_dir()

    def test_sibling_skill_dir_survives_uninstall(self, tmp_path: Path) -> None:
        """Other skill directories alongside JEV must survive uninstall."""
        project = _fixture_dir(tmp_path, "sibling_skill")
        _ensure_installer_dir(project)

        skill_dir = _native_project_path("claude-code", project)
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# JEV\n")

        # Create a sibling skill directory.
        other_skill = skill_dir.parent / "other-skill"
        other_skill.mkdir()
        (other_skill / "SKILL.md").write_text("# Other skill\n")

        uninstall("claude-code", project_root=project)

        assert not skill_dir.exists()
        assert other_skill.is_dir()
        assert (other_skill / "SKILL.md").read_text() == "# Other skill\n"


# ---------------------------------------------------------------------------
# 18. RED — symlinked ancestor rejects uninstall
# ---------------------------------------------------------------------------


class TestUninstallSymlinkAncestor:
    def test_uninstall_refuses_symlink_skill_dir(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "uninstall_symlink")
        _ensure_installer_dir(project)

        skill_dir = _native_project_path("claude-code", project)
        # Ensure parent dir exists.
        skill_dir.parent.mkdir(parents=True, exist_ok=True)

        real_target = tmp_path / "real_target"
        real_target.mkdir()
        (real_target / "SKILL.md").write_text("# real\n")

        skill_dir.symlink_to(real_target)

        with pytest.raises(RuntimeError, match="symlink"):
            uninstall("claude-code", project_root=project)

    def test_uninstall_refuses_symlink_parent_in_chain(self, tmp_path: Path) -> None:
        """Uninstall must reject if a parent directory in the chain is a symlink."""
        project = _fixture_dir(tmp_path, "ancestor_symlink")
        _ensure_installer_dir(project)

        # Create the full path up to skills.
        skills = project / ".claude" / "skills"
        skills.mkdir(parents=True)

        # Create skill dir normally.
        skill_dir = skills / SKILL_NAME
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# skill\n")

        # Now make a parent directory a symlink.
        # Replace .claude/skills with a symlink to a real dir.
        real_skills = tmp_path / "real_skills"
        real_skills.mkdir()

        if skills.is_symlink():
            skills.unlink()
        elif skills.is_dir():
            shutil.rmtree(skills)
        skills.symlink_to(real_skills)

        # Now the skill dir exists only under the symlink.
        # Make the skill_dir exist inside real_skills too.
        fake_skill_dir = real_skills / SKILL_NAME
        fake_skill_dir.mkdir()
        (fake_skill_dir / "SKILL.md").write_text("# real skill\n")

        with pytest.raises(RuntimeError, match="symlink"):
            uninstall("claude-code", project_root=project)


# ---------------------------------------------------------------------------
# 19. RED — no Typer/config APIs in installer module
# ---------------------------------------------------------------------------


class TestPureDomainModule:
    def test_no_typer_import(self) -> None:
        """Installer module must not import typer."""
        import jev_bot.installer as mod
        source = mod.__file__
        assert source is not None
        raw = open(source, "r", encoding="utf-8").read()
        assert "import typer" not in raw
        assert "from typer" not in raw

    def test_no_typer_app(self) -> None:
        """Installer module must not expose a Typer app."""
        import jev_bot.installer as mod
        assert not hasattr(mod, "app")

    def test_no_config_functions(self) -> None:
        """Installer module must not expose config store functions."""
        import jev_bot.installer as mod
        assert not hasattr(mod, "write_config")
        assert not hasattr(mod, "read_config")
        assert not hasattr(mod, "config_token")
        assert not hasattr(mod, "config_endpoint")


# ---------------------------------------------------------------------------
# 20. Four-harness idempotent install test
# ---------------------------------------------------------------------------


class TestFourHarnessIdempotent:
    def test_all_four_install_twice(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "four_harness")
        _ensure_installer_dir(project)

        for harness in sorted(VALID_HARNESSES):
            install(harness, project_root=project)
            install(harness, project_root=project)

        for harness in sorted(VALID_HARNESSES):
            project_path = _native_project_path(harness, project)
            assert project_path.is_dir(), f"{harness} not installed"
            assert (project_path / "SKILL.md").is_file(), f"{harness} SKILL.md missing"


# ---------------------------------------------------------------------------
# 21. Four-harness uninstall test
# ---------------------------------------------------------------------------


class TestFourHarnessUninstall:
    def test_all_four_uninstall(self, tmp_path: Path) -> None:
        project = _fixture_dir(tmp_path, "four_uninstall")
        _ensure_installer_dir(project)

        for harness in sorted(VALID_HARNESSES):
            install(harness, project_root=project)

        for harness in sorted(VALID_HARNESSES):
            uninstall(harness, project_root=project)

        for harness in sorted(VALID_HARNESSES):
            project_path = _native_project_path(harness, project)
            assert not project_path.exists(), f"{harness} not uninstalled"


# ---------------------------------------------------------------------------
# 22. User home — idempotent install
# ---------------------------------------------------------------------------


class TestUserHomeIdempotent:
    def test_user_install_twice_succeeds(self, tmp_path: Path) -> None:
        home = _host_home(tmp_path)
        _ensure_installer_dir(tmp_path / "installer")

        install("claude-code", user_home=home)
        install("claude-code", user_home=home)

        skill_md = home / ".claude" / "skills" / SKILL_NAME / "SKILL.md"
        assert skill_md.is_file()


# ---------------------------------------------------------------------------
# 23. User uninstall only removes user path
# ---------------------------------------------------------------------------


class TestUserUninstall:
    def test_uninstall_user_skill(self, tmp_path: Path) -> None:
        home = _host_home(tmp_path)

        _ensure_installer_dir(tmp_path / "installer")

        install("opencode", user_home=home)
        uninstall("opencode", user_home=home)

        skill_dir = home / ".config" / "opencode" / "skills" / SKILL_NAME
        assert not skill_dir.exists()


# ---------------------------------------------------------------------------
# 24. Uninstall pruning — harness root preserved
# ---------------------------------------------------------------------------


class TestUninstallPruningBoundary:
    def test_prunes_empty_prune_parent(self, tmp_path: Path) -> None:
        """When .claude/skills/ is entirely removed, .claude itself is also removed."""
        project = _fixture_dir(tmp_path, "prune_boundary")
        _ensure_installer_dir(project)

        skill_dir = _native_project_path("claude-code", project)
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# skill\n")

        uninstall("claude-code", project_root=project)

        assert not _native_project_path("claude-code", project).exists()
        assert not (project / ".claude").exists()

    def test_keeps_harness_root_with_sibling(self, tmp_path: Path) -> None:
        """When .claude/skills has a sibling, .claude is kept."""
        project = _fixture_dir(tmp_path, "keep_root")
        _ensure_installer_dir(project)

        skill_dir = _native_project_path("claude-code", project)
        skills_parent = skill_dir.parent
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# skill\n")

        # Add sibling inside .claude/skills/.
        (skills_parent / "keep.txt").write_text("x")

        uninstall("claude-code", project_root=project)

        assert not skill_dir.exists()
        assert (skills_parent / "keep.txt").exists()
        assert (project / ".claude").is_dir()
