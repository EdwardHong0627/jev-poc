"""JEV — console entry point built on top of installer + config_store."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from dataclasses import dataclass

from jev_bot.config_store import (
    UserConfig,
    get_config_path,
    read_user_config,
    write_user_config,
)
from jev_bot.installer import (
    install as _install,
    install_with_report,
    uninstall as _uninstall,
    uninstall_with_report,
)
from jev_bot.mcp_registration import RegistrationStatus

app = typer.Typer(
    help="JEV Decisions API — install/uninstall skills and manage config.",
    invoke_without_command=True,
)


@dataclass(frozen=True)
class _RawConfig:
    """Minimal dataclass for raw config fallback when UserConfig rejects empty values."""
    token: str = ""
    endpoint: str = ""


def _write_raw_json(config_dir: Path, data: dict) -> None:
    """Write raw JSON config (bypasses UserConfig validation)."""
    import json
    import os
    import tempfile

    config_path = config_dir / "config.json"
    config_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(config_dir, 0o700)

    content = json.dumps(data, indent=2)
    with tempfile.NamedTemporaryFile(
        dir=str(config_path.parent),
        suffix=".tmp",
        mode="w",
        delete=False,
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    os.replace(tmp_path, config_path)
    os.chmod(config_path, 0o600)


# ------------------------------------------------------------------ config

config_app = typer.Typer(help="Manage JEV configuration.")
app.add_typer(config_app, name="config")


@config_app.command(name="list")
def _config_list() -> None:
    """List current config values (token hidden, endpoint shown)."""
    config_path = get_config_path()
    if not config_path.exists():
        typer.echo("No config file found.")
        return
    user_config = read_user_config(config_path)
    if user_config is None:
        typer.echo("Config file is empty or malformed.")
        return
    typer.echo("token: <present>")
    typer.echo(f"endpoint: {user_config.endpoint}")


@config_app.command(name="set")
def _config_set(
    key: str = typer.Argument(
        ...,
        help="Configuration key to set ('token' or 'endpoint').",
    ),
    value: str | None = typer.Argument(
        default=None,
        help="Value to set. Use '--stdin' to read from standard input.",
    ),
    stdin: bool = typer.Option(
        False,
        "--stdin",
        help="Read value from standard input (single non-blank line).",
    ),
) -> None:
    """Set a configuration value.

    Examples::

        jev config set token --stdin
        jev config set endpoint https://openrouter.ai/api/alpha/decisions
    """
    config_path = get_config_path()
    existing = None
    if config_path.exists():
        try:
            existing = read_user_config(config_path)
        except ValueError:
            # Config is malformed (e.g. empty token/endpoint from a previous unset);
            # read raw as fallback.
            try:
                import json
                raw = json.loads(config_path.read_text())
                existing = _RawConfig(token=raw.get("token", ""), endpoint=raw.get("endpoint", ""))
            except (json.JSONDecodeError, OSError):
                existing = None

    if key == "token":
        if not stdin:
            typer.echo(
                "Error: token must be provided via --stdin to avoid echoing.", err=True,
            )
            raise SystemExit(1)
        raw_input = sys.stdin.readline().strip()
        if not raw_input:
            typer.echo("Error: token must be a non-blank line from stdin.", err=True)
            raise SystemExit(1)
        token_value = raw_input
        endpoint_value = existing.endpoint if existing else ""

    elif key == "endpoint":
        if value is None:
            typer.echo(
                "Error: endpoint value is required.", err=True,
            )
            raise SystemExit(1)
        try:
            from jev_bot.config import _validate_endpoint
            _validate_endpoint(value)
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise SystemExit(1)
        token_value = existing.token if existing else ""
        endpoint_value = value

    else:
        typer.echo(f"Error: unknown config key {key!r}.", err=True)
        raise SystemExit(1)

    # When both fields are non-blank, use proper UserConfig; otherwise write raw.
    if token_value and endpoint_value:
        try:
            cfg = UserConfig(token=token_value, endpoint=endpoint_value)
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise SystemExit(1)
        write_user_config(config_path.parent, cfg)
    else:
        _write_raw_json(config_path.parent, {"token": token_value, "endpoint": endpoint_value})
    typer.echo(f"Config {key} updated.")


@config_app.command()
def unset(
    key: str = typer.Argument(
        ...,
        help="Configuration key to unset ('token' or 'endpoint').",
    ),
) -> None:
    """Unset a configuration value."""
    valid_keys = {"token", "endpoint"}
    if key not in valid_keys:
        typer.echo(f"Error: unknown config key {key!r}.", err=True)
        raise SystemExit(1)

    config_path = get_config_path()
    existing = read_user_config(config_path) if config_path.exists() else None

    if existing is None:
        typer.echo(f"No existing config to unset for {key!r}.")
        return

    if key == "token":
        typer.echo("token: <was set>")
        data = {"token": "", "endpoint": existing.endpoint}
    else:  # endpoint
        typer.echo(f"endpoint: {existing.endpoint}")
        data = {"token": existing.token, "endpoint": ""}

    _write_raw_json(config_path.parent, data)
    typer.echo(f"Config {key} removed.")


# ----------------------------------------------------------- install / uninstall

@app.command()
def install(
    harness: str = typer.Argument(
        ...,
        help="Target harness name.",
    ),
    project_root: Path | None = typer.Option(
        None,
        "--project",
        "--project-root",
        help="Path to the project root (targets harness's project path only).",
        file_okay=False,
        dir_okay=True,
        exists=False,
    ),
    user_home: Path | None = typer.Option(
        None,
        "--user",
        "--user-home",
        help="Path to the user home directory (targets harness's user path only).",
        file_okay=False,
        dir_okay=True,
        exists=False,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Force overwrite of existing skill and replace a foreign JEV MCP registration.",
    ),
) -> None:
    """Install the JEV skill and MCP registration into a harness destination."""
    if project_root is None and user_home is None:
        typer.echo(
            "Error: exactly one of --project or --user is required.", err=True,
        )
        raise SystemExit(1)
    if project_root is not None and user_home is not None:
        typer.echo(
            "Error: provide exactly one of --project or --user, not both.", err=True,
        )
        raise SystemExit(1)

    try:
        skill_path, mcp_result = install_with_report(
            harness, project_root=project_root, user_home=user_home, force=force,
        )
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)

    typer.echo(f"Installed: {skill_path}")
    typer.echo(f"MCP config: {mcp_result.path}")


@app.command()
def uninstall(
    harness: str = typer.Argument(
        ...,
        help="Target harness name.",
    ),
    project_root: Path | None = typer.Option(
        None,
        "--project",
        "--project-root",
        help="Path to the project root (targets harness's project path only).",
        file_okay=False,
        dir_okay=True,
        exists=False,
    ),
    user_home: Path | None = typer.Option(
        None,
        "--user",
        "--user-home",
        help="Path to the user home directory (targets harness's user path only).",
        file_okay=False,
        dir_okay=True,
        exists=False,
    ),
) -> None:
    """Uninstall the JEV skill and MCP registration from a harness destination."""
    if project_root is None and user_home is None:
        typer.echo(
            "Error: exactly one of --project or --user is required.", err=True,
        )
        raise SystemExit(1)
    if project_root is not None and user_home is not None:
        typer.echo(
            "Error: provide exactly one of --project or --user, not both.", err=True,
        )
        raise SystemExit(1)

    try:
        skill_path, mcp_result = uninstall_with_report(
            harness, project_root=project_root, user_home=user_home,
        )
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)

    typer.echo(f"Uninstalled: {skill_path}")
    typer.echo(f"MCP config: {mcp_result.path}")
    if mcp_result.status is RegistrationStatus.FOREIGN:
        typer.echo("Warning: foreign MCP registration retained.", err=True)


if __name__ == "__main__":
    app()
