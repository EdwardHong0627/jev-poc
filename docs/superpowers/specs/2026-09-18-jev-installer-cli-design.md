# JEV Installer CLI Design

## Goal

Provide a Typer-based `jev` command that installs the packaged JEV decision skill into a requested agent harness, removes only that installed skill, and securely persists user-level JEV configuration.

## Scope

The command supports exactly four harness names:

| Harness | Project skill path | User skill path |
| --- | --- | --- |
| `claude-code` | `<project>/.claude/skills/using-jev-decisions/SKILL.md` | `~/.claude/skills/using-jev-decisions/SKILL.md` |
| `opencode` | `<project>/.opencode/skills/using-jev-decisions/SKILL.md` | `~/.config/opencode/skills/using-jev-decisions/SKILL.md` |
| `oh-my-pi` | `<project>/.omp/skills/using-jev-decisions/SKILL.md` | `~/.omp/agent/skills/using-jev-decisions/SKILL.md` |
| `pi` | `<project>/.pi/skills/using-jev-decisions/SKILL.md` | `~/.pi/agent/skills/using-jev-decisions/SKILL.md` |

Each destination is the harness's documented native discovery location. Installation never modifies harness configuration files.

## Command contract

```text
jev install <harness> (--project <path> | --user) [--force]
jev uninstall <harness> (--project <path> | --user)
jev config set token --stdin
jev config set endpoint <https-url>
jev config list
jev config unset <token|endpoint>
```

Scope must be explicit. `--project` resolves to an existing directory; `--user` targets the documented user location. Both flags together and neither flag are usage errors.

`install` reads the canonical packaged `SKILL.md`, creates its parent directories, and writes a new file. If a destination exists with different bytes, it fails without mutation unless `--force` is supplied. Matching content is idempotent. `uninstall` is an idempotent no-op when the skill file is absent. Otherwise it deletes only the installed `SKILL.md`, removes its skill directory only when that directory is empty, and prunes only now-empty parent directories up to, but never including, the harness root. It never follows a destination symlink or deletes an unrelated file.

## Packaged skill asset

The canonical asset lives in a Python package resource so installed wheels work without source checkout files. Setuptools package-data explicitly includes `assets/**/*.md` in wheels. The repository-visible `.agents/skills/using-jev-decisions/SKILL.md` remains supported for local agents and is tested byte-for-byte against the packaged resource to prevent divergence.

## Configuration contract

User configuration is JSON at `${XDG_CONFIG_HOME:-~/.config}/jev-poc/config.json`. The directory is enforced to mode `0700`; the file is atomically written then enforced to mode `0600`. The JSON object supports only `token` and `endpoint` strings.

- `config set token --stdin` reads one non-empty token line from standard input; it is never accepted as an argument, echoed, or logged.
- `config set endpoint VALUE` reuses the existing endpoint validation.
- `config list` reports endpoint and token presence only; it never prints a token value.
- `config unset KEY` removes the key and deletes the config file when no values remain.
- Existing non-blank `JEV_API_TOKEN` and `JEV_ENDPOINT` environment variables override persisted configuration. Blank values are treated as absent. The persisted config supplies values only when non-blank environment and dotenv values are absent.

Malformed or unreadable user config is an actionable configuration error that contains neither file content nor secrets.

## Architecture

- `jev_bot/config_store.py`: file location, secure atomic persistence, validation boundary, and read/write/list/unset operations.
- `jev_bot/installer.py`: immutable harness-to-destination mapping plus install/uninstall behavior.
- `jev_bot/cli.py`: Typer application; parsing, exit behavior, and safe terminal presentation only.
- `jev_bot/assets/using-jev-decisions/SKILL.md`: packaged canonical skill asset.
- `config.py`: extends configuration loading with persisted user config at lower precedence.

The console script is named `jev`. Typer is the only added runtime dependency.

## Errors and security

Commands use non-zero exit status for validation, overwrite, and filesystem errors. Errors name the requested harness and safe path but never print token values. No command performs network I/O. The installer writes ordinary files only and refuses unsafe destination symlinks.

## Verification

Tests must cover all four harness destinations at project and user scopes, idempotent install, foreign-content overwrite protection, forced replacement, safe uninstall, config permissions and redaction, config precedence, endpoint validation, and packaged/repository skill parity. CLI smoke tests must exercise help, install, uninstall, and config subcommands using isolated temporary paths.