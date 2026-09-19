"""Tests for jev_bot.cli — Typer CliRunner surface."""

from __future__ import annotations

import json
import stat
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from jev_bot.cli import app
from jev_bot.config_store import get_config_path
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner():
    """Fresh CliRunner per test (no state leaking)."""
    return CliRunner()


@pytest.fixture()
def config_dir(tmp_path):
    """Return a temporary XDG_CONFIG_HOME under tmp_path."""
    d = tmp_path / "config"
    d.mkdir()
    return d


@pytest.fixture()
def config_path(config_dir, tmp_path):
    """Return the actual config file path ($XDG_CONFIG_HOME/jev-poc/config.json)."""
    d = config_dir / "jev-poc"
    d.mkdir()
    return d / "config.json"


@pytest.fixture(autouse=True)
def isolated_config(config_dir, monkeypatch):
    """Point XDG_CONFIG_HOME at tmp_path/config for every test."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir))
    return config_dir


@pytest.fixture()
def install_credential(monkeypatch):
    """Provide a JEV_API_TOKEN so install does not block credential check."""
    monkeypatch.setenv("JEV_API_TOKEN", "test-token-for-tests")
    return None


@pytest.fixture()
def fake_skill_dir(tmp_path):
    """Create a fake skill dir so uninstall has something to remove."""
    skill = tmp_path / "skills" / "using-jev-decisions"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# JEV skill\n")
    return skill


# ---------------------------------------------------------------------------
# 1. CLI entry point — top-level help
# ---------------------------------------------------------------------------


class TestEntryPoint:
    def test_app_has_config_subcommand(self, runner):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "config" in result.output

    def test_app_has_install_subcommand(self, runner):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "install" in result.output

    def test_app_has_uninstall_subcommand(self, runner):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "uninstall" in result.output


# ---------------------------------------------------------------------------
# 2. config list — no config file
# ---------------------------------------------------------------------------


class TestConfigListNoConfig:
    def test_no_config_file(self, runner, config_dir):
        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0
        assert "No config file found" in result.output


# ---------------------------------------------------------------------------
# 3. config list — config present
# ---------------------------------------------------------------------------


class TestConfigList:
    def test_reports_token_present_endpoint(self, runner, config_path):
        config_path.write_text(json.dumps({"token": "abc", "endpoint": "https://openrouter.ai/api/alpha/decisions"}), encoding="utf-8")
        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0
        assert "token: <present>" in result.output
        assert "https://openrouter.ai/api/alpha/decisions" in result.output


# ---------------------------------------------------------------------------
# 4. config set token — stdin nonblank
# ---------------------------------------------------------------------------


class TestConfigSetTokenStdin:
    def test_stores_token_from_stdin(self, runner, config_path):
        config_path.write_text(json.dumps({"token": "", "endpoint": "https://openrouter.ai/api/alpha/decisions"}), encoding="utf-8")
        result = runner.invoke(app, ["config", "set", "token", "--stdin"], input="mytoken123\n")
        assert result.exit_code == 0
        assert "updated" in result.output
        stored = json.loads(config_path.read_text(encoding="utf-8"))
        assert stored["token"] == "mytoken123"
        assert stored["endpoint"] == "https://openrouter.ai/api/alpha/decisions"

    def test_blank_stdin_rejected(self, runner, config_dir):
        result = runner.invoke(app, ["config", "set", "token", "--stdin"], input="\n")
        assert result.exit_code == 1
        assert "non-blank" in result.output or "Error" in result.output


class TestConfigSetTokenNoStdin:
    def test_positional_token_rejected(self, runner, config_dir):
        result = runner.invoke(app, ["config", "set", "token", "mytoken"])
        assert result.exit_code == 1
        assert "--stdin" in result.output


# ---------------------------------------------------------------------------
# 5. config set endpoint — valid / invalid
# ---------------------------------------------------------------------------


class TestConfigSetEndpoint:
    def test_valid_https_openrouter(self, runner, config_path):
        config_path.write_text(json.dumps({"token": "tok", "endpoint": ""}), encoding="utf-8")
        result = runner.invoke(
            app,
            ["config", "set", "endpoint", "https://openrouter.ai/api/alpha/decisions"],
        )
        assert result.exit_code == 0
        stored = json.loads(config_path.read_text(encoding="utf-8"))
        assert stored["endpoint"] == "https://openrouter.ai/api/alpha/decisions"

    def test_invalid_scheme_rejected(self, runner, config_dir):
        result = runner.invoke(
            app,
            ["config", "set", "endpoint", "http://openrouter.ai/api/decisions"],
        )
        assert result.exit_code == 1

    def test_invalid_host_rejected(self, runner, config_dir):
        result = runner.invoke(
            app,
            ["config", "set", "endpoint", "https://evil.com/api/decisions"],
        )
        assert result.exit_code == 1

    def test_missing_value_rejected(self, runner, config_dir):
        result = runner.invoke(app, ["config", "set", "endpoint"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# 6. config unset
# ---------------------------------------------------------------------------


class TestConfigUnset:
    def test_unset_token(self, runner, config_path):
        config_path.write_text(json.dumps({"token": "tok", "endpoint": "https://openrouter.ai/api/alpha/decisions"}), encoding="utf-8")
        result = runner.invoke(app, ["config", "unset", "token"])
        assert result.exit_code == 0
        assert "removed" in result.output or "was set" in result.output
        stored = json.loads(config_path.read_text(encoding="utf-8"))
        assert stored["token"] == ""

    def test_unset_endpoint(self, runner, config_path):
        config_path.write_text(json.dumps({"token": "tok", "endpoint": "https://openrouter.ai/api/alpha/decisions"}), encoding="utf-8")
        result = runner.invoke(app, ["config", "unset", "endpoint"])
        assert result.exit_code == 0
        stored = json.loads(config_path.read_text(encoding="utf-8"))
        assert stored["endpoint"] == ""

    def test_unset_no_config(self, runner, config_dir):
        result = runner.invoke(app, ["config", "unset", "token"])
        assert result.exit_code == 0
        assert "No existing config" in result.output


# ---------------------------------------------------------------------------
# 7. install — --project scope
# ---------------------------------------------------------------------------


class TestInstallProjectScope:
    def test_install_claude_code_project(self, runner, tmp_path, install_credential):
        project = tmp_path / "proj"
        project.mkdir()
        result = runner.invoke(app, ["install", "claude-code", "--project", str(project)])
        assert result.exit_code == 0, f"stdout={result.output} stderr={result.stderr}"
        assert "Installed:" in result.output
        assert str(project) in result.output
        skill_md = project / ".claude" / "skills" / "using-jev-decisions" / "SKILL.md"
        assert skill_md.is_file()

    def test_install_opencode_project(self, runner, tmp_path, install_credential):
        project = tmp_path / "proj"
        project.mkdir()
        result = runner.invoke(app, ["install", "opencode", "--project", str(project)])
        assert result.exit_code == 0
        skill_md = project / ".opencode" / "skills" / "using-jev-decisions" / "SKILL.md"
        assert skill_md.is_file()

    def test_install_oh_my_pi_project(self, runner, tmp_path, install_credential):
        project = tmp_path / "proj"
        project.mkdir()
        result = runner.invoke(app, ["install", "oh-my-pi", "--project", str(project)])
        assert result.exit_code == 0
        skill_md = project / ".omp" / "skills" / "using-jev-decisions" / "SKILL.md"
        assert skill_md.is_file()

    def test_install_pi_project(self, runner, tmp_path, install_credential):
        project = tmp_path / "proj"
        project.mkdir()
        result = runner.invoke(app, ["install", "pi", "--project", str(project)])
        assert result.exit_code == 0
        skill_md = project / ".pi" / "skills" / "using-jev-decisions" / "SKILL.md"
        assert skill_md.is_file()


# ---------------------------------------------------------------------------
# 8. install — --user scope
# ---------------------------------------------------------------------------


class TestInstallUserScope:
    def test_install_claude_code_user(self, runner, tmp_path, install_credential):
        home = tmp_path / "home"
        home.mkdir()
        result = runner.invoke(app, ["install", "claude-code", "--user", str(home)])
        assert result.exit_code == 0
        skill_md = home / ".claude" / "skills" / "using-jev-decisions" / "SKILL.md"
        assert skill_md.is_file()

    def test_install_opencode_user(self, runner, tmp_path, install_credential):
        home = tmp_path / "home"
        home.mkdir()
        result = runner.invoke(app, ["install", "opencode", "--user", str(home)])
        assert result.exit_code == 0
        skill_md = home / ".config" / "opencode" / "skills" / "using-jev-decisions" / "SKILL.md"
        assert skill_md.is_file()


# ---------------------------------------------------------------------------
# 9. install — force overwrite
# ---------------------------------------------------------------------------


class TestInstallForce:
    def test_force_overwrites_existing(self, runner, tmp_path, install_credential):
        project = tmp_path / "proj"
        project.mkdir()
        skill_dir = project / ".claude" / "skills" / "using-jev-decisions"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# old content\n")

        result = runner.invoke(app, ["install", "claude-code", "--project", str(project), "--force"])
        assert result.exit_code == 0
        content = (skill_dir / "SKILL.md").read_text()
        assert "JEV" in content


# ---------------------------------------------------------------------------
# 10. install — idempotent (second install no-op)
# ---------------------------------------------------------------------------


class TestInstallIdempotent:
    def test_second_install_succeeds(self, runner, tmp_path, install_credential):
        project = tmp_path / "proj"
        project.mkdir()
        result1 = runner.invoke(app, ["install", "claude-code", "--project", str(project)])
        assert result1.exit_code == 0
        result2 = runner.invoke(app, ["install", "claude-code", "--project", str(project)])
        assert result2.exit_code == 0


# ---------------------------------------------------------------------------
# 11. install — conflict (project + user)
# ---------------------------------------------------------------------------


class TestInstallConflict:
    def test_both_scopes_rejected(self, runner, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        home = tmp_path / "home"
        home.mkdir()
        result = runner.invoke(app, ["install", "claude-code", "--project", str(project), "--user", str(home)])
        assert result.exit_code == 1
        assert "exactly one" in result.output


# ---------------------------------------------------------------------------
# 12. install — no scope
# ---------------------------------------------------------------------------


class TestInstallNoScope:
    def test_no_scope_rejected(self, runner, tmp_path):
        result = runner.invoke(app, ["install", "claude-code"])
        assert result.exit_code == 1
        assert "exactly one" in result.output


# ---------------------------------------------------------------------------
# 13. uninstall — success
# ---------------------------------------------------------------------------


class TestUninstallSuccess:
    def test_uninstall_claude_code_project(self, runner, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        skill_md = project / ".claude" / "skills" / "using-jev-decisions" / "SKILL.md"
        skill_md.parent.mkdir(parents=True)
        skill_md.write_text("# JEV skill\n")

        result = runner.invoke(app, ["uninstall", "claude-code", "--project", str(project)])
        assert result.exit_code == 0
        assert not skill_md.exists()

    def test_uninstall_opencode_project(self, runner, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        skill_md = project / ".opencode" / "skills" / "using-jev-decisions" / "SKILL.md"
        skill_md.parent.mkdir(parents=True)
        skill_md.write_text("# JEV skill\n")

        result = runner.invoke(app, ["uninstall", "opencode", "--project", str(project)])
        assert result.exit_code == 0
        assert not skill_md.exists()


# ---------------------------------------------------------------------------
# 14. uninstall — scope isolation (user only removes user path)
# ---------------------------------------------------------------------------


class TestUninstallScopeIsolation:
    def test_user_uninstall_does_not_affect_project(self, runner, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        home = tmp_path / "home"
        home.mkdir()

        # Install to both scopes
        from jev_bot.installer import install as _install
        _install("claude-code", project_root=project, force=True)
        _install("claude-code", user_home=home, force=True)

        result = runner.invoke(app, ["uninstall", "claude-code", "--user", str(home)])
        assert result.exit_code == 0

        # Project path still has the skill
        assert (project / ".claude" / "skills" / "using-jev-decisions" / "SKILL.md").is_file()
        # User path no longer has it
        assert not (home / ".claude" / "skills" / "using-jev-decisions" / "SKILL.md").exists()


# ---------------------------------------------------------------------------
# 15. uninstall — both scopes rejected
# ---------------------------------------------------------------------------


class TestUninstallConflict:
    def test_both_scopes_rejected(self, runner, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        home = tmp_path / "home"
        home.mkdir()
        result = runner.invoke(app, ["uninstall", "claude-code", "--project", str(project), "--user", str(home)])
        assert result.exit_code == 1
        assert "exactly one" in result.output


# ---------------------------------------------------------------------------
# 16. uninstall — no scope rejected
# ---------------------------------------------------------------------------


class TestUninstallNoScope:
    def test_no_scope_rejected(self, runner, tmp_path):
        result = runner.invoke(app, ["uninstall", "claude-code"])
        assert result.exit_code == 1
        assert "exactly one" in result.output


# ---------------------------------------------------------------------------
# 17. unknown config key
# ---------------------------------------------------------------------------


class TestUnknownConfigKey:
    def test_unknown_set_key(self, runner):
        result = runner.invoke(app, ["config", "set", "foobar"])
        assert result.exit_code == 1

    def test_unknown_unset_key(self, runner, config_path):
        result = runner.invoke(app, ["config", "unset", "foobar"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# 18. installer domain — no Typer import pollution
# ---------------------------------------------------------------------------


class TestDomainPurity:
    def test_installer_has_no_typer(self):
        import jev_bot.installer as mod
        source = open(mod.__file__, encoding="utf-8").read()
        assert "typer" not in source

    def test_config_store_has_no_typer(self):
        import jev_bot.config_store as mod
        source = open(mod.__file__, encoding="utf-8").read()
        assert "typer" not in source


# ---------------------------------------------------------------------------
# 19. pyproject.toml declares jev-mcp console script
# ---------------------------------------------------------------------------


class TestMcpConsoleEntry:
    def test_pyproject_has_jevmcp_entry(self):
        """pyproject.toml must declare jev-mcp = jev_mcp.server:main."""
        import tomllib
        pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        scripts = data.get("project", {}).get("scripts", {})
        assert "jev-mcp" in scripts, (
            f"'jev-mcp' console script not found in pyproject.toml. "
            f"Found scripts: {list(scripts.keys())}"
        )
        assert scripts["jev-mcp"] == "jev_mcp.server:main"


# ---------------------------------------------------------------------------
# 20. CLI install help describes skill-plus-MCP behavior
# ---------------------------------------------------------------------------


class TestInstallHelpMcpDescription:
    def test_install_help_mentions_mcp_registration(self, runner):
        result = runner.invoke(app, ["install", "--help"])
        assert result.exit_code == 0
        assert "MCP registration" in result.output

    def test_install_help_mentions_skill(self, runner):
        result = runner.invoke(app, ["install", "--help"])
        assert result.exit_code == 0
        assert "skill" in result.output.lower()


# ---------------------------------------------------------------------------
# 21. CLI uninstall help describes skill-plus-MCP behavior
# ---------------------------------------------------------------------------


class TestUninstallHelpMcpDescription:
    def test_uninstall_help_mentions_mcp_registration(self, runner):
        result = runner.invoke(app, ["uninstall", "--help"])
        assert result.exit_code == 0
        assert "MCP registration" in result.output

    def test_uninstall_help_mentions_skill(self, runner):
        result = runner.invoke(app, ["uninstall", "--help"])
        assert result.exit_code == 0
        assert "skill" in result.output.lower()


# ---------------------------------------------------------------------------
# 22. CLI install output shows both skill and MCP config paths
# ---------------------------------------------------------------------------


class TestInstallOutputShowsBothPaths:
    def test_install_output_includes_mcp_config_path(self, runner, tmp_path, install_credential):
        project = tmp_path / "proj"
        project.mkdir()
        result = runner.invoke(app, ["install", "claude-code", "--project", str(project)])
        assert result.exit_code == 0, f"stdout={result.output} stderr={result.stderr}"
        # Verify skill path is present
        skill_expected = str(project / ".claude" / "skills" / "using-jev-decisions" / "SKILL.md")
        assert skill_expected in result.output, (
            f"Install output should include skill path {skill_expected!r}. Got: {result.output!r}"
        )
        # Verify MCP config path is present (.mcp.json for claude-code project scope)
        assert "MCP config:" in result.output
        assert ".mcp.json" in result.output

    def test_install_output_two_lines(self, runner, tmp_path, install_credential):
        project = tmp_path / "proj"
        project.mkdir()
        result = runner.invoke(app, ["install", "claude-code", "--project", str(project)])
        assert result.exit_code == 0
        lines = [l for l in result.output.strip().splitlines() if l.strip()]
        assert len(lines) == 2, f"Expected 2 output lines, got {len(lines)}: {lines!r}"


# ---------------------------------------------------------------------------
# 23. CLI uninstall output with FOREIGN registration shows warning
# ---------------------------------------------------------------------------


class TestUninstallForeignWarning:
    def test_uninstall_foreign_shows_warning_exact(self, runner, tmp_path):
        """When a foreign MCP entry exists, uninstall warns with exact wording."""
        import json
        project = tmp_path / "proj"
        project.mkdir()
        # Create fake skill dir
        skill_md = project / ".claude" / "skills" / "using-jev-decisions" / "SKILL.md"
        skill_md.parent.mkdir(parents=True)
        skill_md.write_text("# JEV skill\n")
        # Create a foreign MCP config — jev entry with different content
        config_path = project / ".mcp.json"
        config_path.write_text(json.dumps({
            "mcpServers": {
                "jev": {"command": "some-other-server", "description": "not jev"}
            }
        }), encoding="utf-8")

        result = runner.invoke(app, ["uninstall", "claude-code", "--project", str(project)])
        assert result.exit_code == 0, f"stdout={result.output} stderr={result.stderr}"
        # Skill was removed
        assert "Uninstalled:" in result.output
        assert "Uninstalled:" in result.output.splitlines()[0]
        # Foreign warning on stderr
        assert "Warning: foreign MCP registration retained." in result.stderr


# ---------------------------------------------------------------------------
# 24. CLI --force help clarifies replacing foreign JEV registration
# ---------------------------------------------------------------------------


class TestForceHelpMcp:
    def test_force_help_mentions_replace_foreign_mcp(self, runner):
        result = runner.invoke(app, ["install", "--help"])
        assert result.exit_code == 0
        # Typer renders help in a box-drawing table; strip box chars + whitespace
        import re
        cleaned = re.sub(r"[│╭╮╰──·●\s]+", " ", result.output)
        assert "replace a foreign JEV MCP registration" in cleaned


# ---------------------------------------------------------------------------
# 25. CLI uninstall_with_report result status present in output
# ---------------------------------------------------------------------------


class TestUninstallReportStatus:
    def test_uninstall_shows_registration_path(self, runner, tmp_path):
        """Uninstall output includes the MCP config path from the report."""
        project = tmp_path / "proj"
        project.mkdir()
        skill_md = project / ".claude" / "skills" / "using-jev-decisions" / "SKILL.md"
        skill_md.parent.mkdir(parents=True)
        skill_md.write_text("# JEV skill\n")

        result = runner.invoke(app, ["uninstall", "claude-code", "--project", str(project)])
        assert result.exit_code == 0, f"stdout={result.output} stderr={result.stderr}"
        # Verify config path is in output (uninstall removes skill + MCP config)
        assert "MCP config:" in result.output
        assert ".mcp.json" in result.output

    def test_uninstall_normal_status_no_stderr_warning(self, runner, tmp_path):
        """When MCP config is canonical (not foreign), no warning on stderr."""
        project = tmp_path / "proj"
        project.mkdir()
        skill_md = project / ".claude" / "skills" / "using-jev-decisions" / "SKILL.md"
        skill_md.parent.mkdir(parents=True)
        skill_md.write_text("# JEV skill\n")

        result = runner.invoke(app, ["uninstall", "claude-code", "--project", str(project)])
        assert result.exit_code == 0
        assert "Warning" not in result.stderr


# ---------------------------------------------------------------------------
# 26. install — credential readiness check
# ---------------------------------------------------------------------------


class TestInstallCredentialReadiness:
    """Credential readiness: check before mutation; prompt interactively; fail noninteractively."""

    def test_install_with_token_env_succeeds(self, runner, tmp_path):
        """Install succeeds when JEV_API_TOKEN is set."""
        project = tmp_path / "proj"
        project.mkdir()
        result = runner.invoke(
            app,
            ["install", "claude-code", "--project", str(project)],
            env={"JEV_API_TOKEN": "test-token"},
        )
        assert result.exit_code == 0, f"stdout={result.output} stderr={result.stderr}"
        assert "Installed:" in result.output

    def test_install_with_stored_token_succeeds(self, runner, tmp_path, config_path, install_credential, monkeypatch):
        """Install succeeds when token is stored in config (not env)."""
        project = tmp_path / "proj"
        project.mkdir()
        # Remove the env var fixture so we actually test the config-store path.
        monkeypatch.delenv("JEV_API_TOKEN", raising=False)
        config_path.write_text(
            json.dumps({
                "token": "stored-token",
                "endpoint": "https://openrouter.ai/api/alpha/decisions",
            }),
            encoding="utf-8",
        )
        result = runner.invoke(
            app,
            ["install", "claude-code", "--project", str(project)],
        )
        assert result.exit_code == 0, f"stdout={result.output} stderr={result.stderr}"
        assert "Installed:" in result.output

    def test_install_no_token_interactive_prompts(self, runner, tmp_path, config_path, install_credential, monkeypatch):
        """When no token exists and stdin is a TTY, install prompts and persists."""
        project = tmp_path / "proj"
        project.mkdir()
        # Remove the env var so load_config fails, triggering the prompt path
        monkeypatch.delenv("JEV_API_TOKEN", raising=False)
        monkeypatch.setattr("jev_bot.cli._force_interactive_for_testing", True)
        result = runner.invoke(
            app,
            ["install", "claude-code", "--project", str(project)],
            input="prompted-token\n",
        )
        assert result.exit_code == 0, f"stdout={result.output} stderr={result.stderr}"
        assert "Installed:" in result.output
        stored = json.loads(config_path.read_text(encoding="utf-8"))
        assert stored["token"] == "prompted-token"
        assert stored["endpoint"] == "https://openrouter.ai/api/alpha/decisions"

    def test_install_no_token_blank_stdin_rejected(self, runner, tmp_path, install_credential, monkeypatch):
        """Blank input during interactive prompt is rejected."""
        project = tmp_path / "proj"
        project.mkdir()
        monkeypatch.delenv("JEV_API_TOKEN", raising=False)
        monkeypatch.setattr("jev_bot.cli._force_interactive_for_testing", True)
        result = runner.invoke(
            app,
            ["install", "claude-code", "--project", str(project)],
            input="\n",
        )
        assert result.exit_code == 1
        # Typer re-prompts on blank input then aborts; either way, it's a failure
        assert "Aborted" in result.output or "non-blank" in result.output or "Error" in result.output.lower()

    def test_install_no_token_noninteractive_fails(self, runner, tmp_path, config_path, install_credential, monkeypatch):
        """Noninteractive stdin (no TTY) fails before mutation."""
        project = tmp_path / "proj"
        project.mkdir()
        monkeypatch.delenv("JEV_API_TOKEN", raising=False)
        # _force_interactive_for_testing is False by default (autouse fixture sets it)
        result = runner.invoke(
            app,
            ["install", "claude-code", "--project", str(project)],
            input=None,
        )
        assert result.exit_code == 1
        assert "JEV_API_TOKEN" in result.output or "config" in result.output.lower()
        skill_md = project / ".claude" / "skills" / "using-jev-decisions" / "SKILL.md"
        assert not skill_md.exists()
        assert not config_path.exists() or json.loads(config_path.read_text(encoding="utf-8")).get("token") != ""

    def test_install_no_token_no_output_token(self, runner, tmp_path, config_path, install_credential, monkeypatch):
        """Token value never appears in CLI output, even on success."""
        project = tmp_path / "proj"
        project.mkdir()
        monkeypatch.delenv("JEV_API_TOKEN", raising=False)
        monkeypatch.setattr("jev_bot.cli._force_interactive_for_testing", True)
        result = runner.invoke(
            app,
            ["install", "claude-code", "--project", str(project)],
            input="secret-token-value\n",
        )
        assert result.exit_code == 0
        assert "secret-token-value" not in result.output

    def test_install_output_no_token_exposure_interactive_fail(self, runner, tmp_path, install_credential, monkeypatch):
        """Token never exposed in failure output either."""
        project = tmp_path / "proj"
        project.mkdir()
        monkeypatch.delenv("JEV_API_TOKEN", raising=False)
        monkeypatch.setattr("jev_bot.cli._force_interactive_for_testing", True)
        result = runner.invoke(
            app,
            ["install", "claude-code", "--project", str(project)],
            input="\n",
        )
        assert "secret" not in result.output.lower() or "prompted" not in result.output
