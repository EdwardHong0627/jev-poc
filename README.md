# JEV PoC

Typed decisions over the JEV Decisions API.

## Setup

`JEV_API_TOKEN` is required in the environment. Set it before running; the
program exits with a configuration error when it is missing.

`JEV_ENDPOINT` is optional. When unset, the default endpoint is used. When set,
it must be an HTTPS URL on `openrouter.ai` without userinfo, otherwise startup
fails with a configuration error.

## Install with uvx

`uvx` runs the `jev` and `jev-mcp` console entry points from a freshly isolated
environment, so no local package installation is required:

```sh
uvx --from git+https://github.com/EdwardHong0627/jev-poc.git jev --help
uvx --from git+https://github.com/EdwardHong0627/jev-poc.git jev-mcp --help
```

## Console CLI

A Typer-based CLI provides skill installation, removal, config management, and
portable MCP server registration:

```sh
# Install the JEV skill and MCP registration into a harness destination
# (asks whether to record investigations in SQLite; Enter = yes)
jev install <harness> --project <path>
jev install <harness> --user <path>

# Override the recording preference non-interactively
jev install <harness> --project <path> --db-enable
jev install <harness> --project <path> --no-db-enable

# Remove a previously installed skill and MCP registration from a harness destination
jev uninstall <harness> --project <path>
jev uninstall <harness> --user <path>

# Manage configuration (stored at $XDG_CONFIG_HOME/jev-poc/config.json)
jev config list                        # show endpoint (token hidden)
jev config set token --stdin           # read token from stdin (no echo)
jev config set endpoint <URL>          # set API endpoint
jev config unset token                 # remove stored token
jev config unset endpoint              # remove stored endpoint
```

Valid harness names: `claude-code`, `opencode`, `oh-my-pi`, `pi`. Exactly one
of `--project` or `--user` is required for install/uninstall.

### First-install credential UX

When running `jev install`, the command checks for a JEV API token through the
same precedence chain as the runtime client: process environment (`JEV_API_TOKEN`),
project `.env`, then the secure user config store at
`$XDG_CONFIG_HOME/jev-poc/config.json`.

**When a token is already resolved** from any source, installation proceeds
without prompting for a token.

**When no token is found and stdin is a terminal**, the user is prompted once
with hidden input. After the token resolves, install then asks the recording
preference (see [Investigation logging](#investigation-logging-sqlite)):

```
$ jev install oh-my-pi --project /path/to/project
JEV API token: ··················
SQLite recording stores request state, questions, and shaped responses verbatim.
Record successful JEV requests and responses in SQLite? [Y/n]:
Installed: /path/to/project/.omp/skills/using-jev-decisions/SKILL.md
MCP config: /path/to/project/.omp/mcp.json
SQLite recording: enabled (/path/to/project/SQLITE_DB)
```

The verbatim-storage warning and the `[Y/n]` confirm appear only when the
recording flag is omitted in an interactive terminal — explicit
`--db-enable`/`--no-db-enable` and non-interactive installs print neither.

The interactively entered token is stored securely (mode `0600`) alongside the
default OpenRouter Decisions endpoint
(`https://openrouter.ai/api/alpha/decisions`). Blank input is rejected before
any skills or MCP configuration are written.

**When no token is found and stdin is not a terminal** (CI, piping, scripts),
the command fails immediately with guidance — no prompt appears and no
installation mutation occurs:

```
$ jev install oh-my-pi --project /path/to/project | cat
Error: no JEV API token found.

Set the JEV_API_TOKEN environment variable or run:
  jev config set token --stdin
to store a token before installing.
```

**Preventing the prompt in future sessions:**

```sh
# Set via environment (ephemeral — not persisted)
export JEV_API_TOKEN="sk-or-v1-..."

# Set via CLI (persisted securely to config.json)
jev config set token --stdin
```

The token is never written to harness configuration files or echoed to
standard output.

### What install does

Each `jev install` command performs three operations:

1. **Skill write** — copies the packaged `using-jev-decisions` SKILL.md into the
   harness's skill directory under the chosen root (project or user).

2. **MCP server registration** — writes (or migrates) the `jev` server entry in
   the harness's MCP configuration file using the portable `uvx` launcher. No
   secrets or checkout-specific references are embedded; the only absolute
   reference is the recording database path when SQLite recording is enabled.

3. **Recording preparation** (enabled by default) — ensures the SQLite
   destination is usable: for project scope, the resolved `<project>/SQLITE_DB`
   path is guarded and a `SQLITE_DB` rule is appended to the project
   `.gitignore` (idempotently); for user scope, the private data directory
   (`$XDG_DATA_HOME/jev-poc`, or `~/.local/share/jev-poc`) is created with mode
   `0700`. The database file itself is created by the MCP server on first run.

```
# Project-root example (Oh My Pi)
$ jev install oh-my-pi --project /path/to/project

# Writes:
#   /path/to/project/.omp/skills/using-jev-decisions/SKILL.md
#   /path/to/project/.omp/mcp.json  →  { "mcpServers": { "jev": { ... } } }
#   /path/to/project/.gitignore     →  appends "SQLITE_DB" (enabled installs)
```

The command reports the outcome on exactly three lines:

```
Installed: /path/to/project/.omp/skills/using-jev-decisions/SKILL.md
MCP config: /path/to/project/.omp/mcp.json
SQLite recording: enabled (/path/to/project/SQLITE_DB)
```

(or `SQLite recording: disabled.` when recording is off).

### Harness paths and MCP configuration shapes

| Harness | Skill path (project / user) | Config file (project / user) | JSON server path | Transport entry |
|---------|-----------------------------|------------------------------|------------------|-----------------|
| `claude-code` | `.claude/skills` / `.claude/skills` | `.mcp.json` / `.claude.json` | `mcpServers.jev` | `{ "type": "stdio", "command": "uvx", "args": ["--from", "git+https://github.com/EdwardHong0627/jev-poc.git", "jev-mcp"] }` |
| `opencode` | `.opencode/skills` / `.config/opencode/skills` | `opencode.json` / `.config/opencode/opencode.json` | `mcp.servers.jev` | `{ "type": "local", "command": ["uvx", "--from", "git+https://github.com/EdwardHong0627/jev-poc.git", "jev-mcp"] }` |
| `oh-my-pi` | `.omp/skills` / `.omp/agent/skills` | `.omp/mcp.json` / `.omp/agent/mcp.json` | `mcpServers.jev` | `{ "type": "stdio", "command": "uvx", "args": ["--from", "git+https://github.com/EdwardHong0627/jev-poc.git", "jev-mcp"] }` |
| `pi` | `.pi/skills` / `.pi/agent/skills` | `.pi/mcp.json` / `.pi/agent/mcp.json` | `mcpServers.jev` | `{ "transport": "stdio", "command": "uvx", "args": ["--from", "git+https://github.com/EdwardHong0627/jev-poc.git", "jev-mcp"], "lifecycle": "lazy" }` |

### MCP launcher

The portable launcher command is:

```sh
uvx --from git+https://github.com/EdwardHong0627/jev-poc.git jev-mcp
```

With recording enabled (the install default), the registered entry appends the
SQLite flag and the resolved absolute database path:

```sh
uvx --from git+https://github.com/EdwardHong0627/jev-poc.git jev-mcp --sqlite-db <ABSOLUTE_PATH>/SQLITE_DB
```

This invokes the `jev-mcp` console script from `jev_mcp.server.main()`. The MCP
server reads `JEV_API_TOKEN` and `JEV_ENDPOINT` from the harness process's
environment — no secrets are written to any harness config file by the
installer.

### --force flag

Pass `--force` to overwrite an existing skill file and replace a foreign JEV MCP
registration (a `jev` entry that is present but was not written by JEV — i.e.
neither the bare canonical launcher nor the canonical launcher followed only by
`--sqlite-db <absolute path>`). Without `--force`, install fails with an error
if the harness already contains a foreign `jev` entry.

Entries JEV owns migrate between recording modes freely: re-running
`jev install` with the opposite `--db-enable`/`--no-db-enable` (or answering
the prompt differently) updates the managed entry in place **without**
`--force`.

### Uninstall

`jev uninstall` removes both the skill and the owned MCP server entry — either
JEV-owned shape, with or without `--sqlite-db` — from the harness destination.
If the `jev` server entry was written by a different system or has been
modified, uninstall retains the foreign entry and prints a warning to stderr.

Uninstall never deletes recording history: the SQLite database, the private
user data directory, and the project `.gitignore` rule all remain in place.

### Reload / status

After install, the harness needs its MCP configuration reloaded. Reload commands
per harness:

| Harness | Reload command |
|---------|---------------|
| `claude-code` | `Ctrl+Shift+P` → "Reload Window" (VS Code) |
| `opencode` | Restart the process or send `Ctrl+R` |
| `oh-my-pi` | `/mcp reload` in the agent console |
| `pi` | `/mcp reload` in the agent console |

The Pi harness additionally requires `pi install npm:pi-mcp-extension` as a
one-time prerequisite; the JEV installer does not install this third-party
extension.

## Decision API

Every request builds a `JEVRequest` containing one to eight identifier-keyed
question entries. The `state` field carries arbitrary context (a string, JSON
object, or JSON array; up to 8 000 characters of string state).

Three question types are supported:

| Type       | Required fields                         | Result shape        |
|------------|----------------------------------------|---------------------|
| `choice`   | `instructions` + `criteria` (2–16 key→desc) | `choiceResult` with `choice`, `probabilities`, `confidence` |
| `score`    | `instructions` + `criteria` (2–16 strings) | `scoreResult` with `score`, `confidence`, `extra` |
| `noul`     | `instructions` (no `criteria`)              | `noulResult` with `noul`, optional `confidence` |

### Building a request

```python
from jev_bot.models import JEVRequest, ChoiceQuestion, ScoreQuestion, NoulQuestion

request = JEVRequest(
    state="Designing a new service.",
    questions={
        "architecture": ChoiceQuestion(
            instructions="Which architecture should we use?",
            criteria={
                "monolith": "Simple deployment and shared data model.",
                "modular_monolith": "Module boundaries without distributed operations.",
            },
        ),
        "quality": ScoreQuestion(
            instructions="Rate the design.",
            criteria=["clarity", "maintainability", "performance"],
        ),
        "risk": NoulQuestion(
            instructions="How risky is this?",
        ),
    },
)
```

The request serialises to a JSON payload with `model` (pinned to `~typesafe/jev-latest`
and not overridden by callers), `state`, and `questions`.

### Parsing the response

```python
from jev_bot.client import DecisionsClient

client = DecisionsClient(config)
response = client.decide(request)

# Per-answer access by question key:
choice_answer = response.answers["architecture"]   # ChoiceResult
score_answer = response.answers["quality"]          # ScoreResult
noul_answer = response.answers["risk"]              # NoulResult
```

Each answer type exposes a typed result:

- **ChoiceResult**: `choice`, `probabilities`, `confidence`
- **ScoreResult**: `score`, `confidence`, `extra`
- **NoulResult**: `noul`, optional `confidence`

The response also carries optional metadata: `model`, `id`, `usage`, `provider`.

## Transport

The client and MCP server communicate with the JEV Decisions engine via
OpenRouter (`~typesafe/jev-latest` endpoint). This is an OpenRouter adapter,
not the TypeSafe SDK transport (`/v1/systemone`). Model pinning is internal
and caller-provided `model` fields are rejected.

## MCP server

Run the local stdio server:

```sh
uv run python -m jev_mcp.server
```

It exposes one read-only tool, `jev_decide`. The process reads the same
`JEV_API_TOKEN` and optional `JEV_ENDPOINT` configuration as the CLI; keep
those values in the MCP host environment rather than tool arguments.

Tool input has this shape:

```json
{
  "state": "Bounded decision context without credentials.",
  "questions": {
    "architecture": {
      "type": "choice",
      "instructions": "Which architecture should we use?",
      "criteria": {
        "monolith": "Simple deployment and shared data model.",
        "modular_monolith": "Module boundaries without distributed operations."
      }
    }
  }
}
```

`questions` contains one to eight identifier-keyed entries. `choice` uses a
2–16-entry option-to-description map; `score` uses a 2–16-item ordered rubric
array; `noul` needs only `type` and `instructions`. The tool pins the JEV
model and rejects caller-provided `model` fields.

MCP output includes `type` and `confidence` on each answer entry.
`choice` results always include `confidence`; `score` results always include
`confidence`; `noul` results include `confidence` only when the API provides
it.

### Investigation logging (SQLite)

`jev install` configures recording for you. Audit-first defaults: interactive
installs ask `Record successful JEV requests and responses in SQLite? [Y/n]`
(Enter = yes) after the credential step; non-interactive installs default to
enabled with no prompt. `--db-enable` / `--no-db-enable` override the prompt
deterministically. The database path is derived from the install scope:

| Scope | Database path |
|-------|---------------|
| `--project` | `<resolved project root>/SQLITE_DB` (plus an idempotent `SQLITE_DB` rule appended to the project `.gitignore`) |
| `--user` | `$XDG_DATA_HOME/jev-poc/SQLITE_DB` when `XDG_DATA_HOME` is an absolute path, else `~/.local/share/jev-poc/SQLITE_DB` (the directory is created private, mode `0700`) |

A relative `XDG_DATA_HOME` is rejected (the generated MCP config must not
depend on the launcher's cwd), as are symlinked or conflicting destinations —
all before any mutation. Disabling never deletes historical data, and project
databases stay git-ignored. Only successful calls are recorded, so no failed
call's secrets can reach the database.

For a custom location outside the installer's scope rules, opt in manually by
adding `--sqlite-db` and an absolute database path to the JEV server's
configured argument list. For example, a local development registration is:

```json
{
  "mcpServers": {
    "jev": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "python",
        "-m",
        "jev_mcp.server",
        "--sqlite-db",
        "/absolute/path/jev-investigations.sqlite3"
      ]
    }
  }
}
```

The server creates the database and appends one row for every successful
`jev_decide` invocation, including a batch of questions. Each row contains an
offset-aware UTC timestamp, the validated request, and the shaped response.
Omit both arguments to disable persistence. Validation, API, response-shaping,
and storage failures are never recorded.
