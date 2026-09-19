# JEV PoC

JEV PoC is a Python integration for OpenRouter's JEV Decisions endpoint. It provides typed choice, score, and noul decisions for a conversational CLI, a local stdio MCP server, and agent skills.

## Transport

This project uses an explicit OpenRouter adapter:

- Model: `~typesafe/jev-latest`
- Endpoint: `https://openrouter.ai/api/alpha/decisions`
- Authentication: `JEV_API_TOKEN`

It follows TypeSafe SDK decision patterns—typed questions, structured state, confidence-aware answers, and bounded retries—but does not use `typesafe-sdk`: that SDK targets the incompatible `/v1/systemone` API.

## Quick start

```sh
uv sync --extra dev
export JEV_API_TOKEN="..."
uv run python main.py
```

The conversational CLI accepts messages until `quit` or `exit`.

## Typed decisions

Every decision has a JSON-compatible `state` (string, object, or array) and a named map of questions:

- **Choice** selects one defined option and returns probabilities plus confidence.
- **Score** rates state against ordered criteria and returns a score plus confidence.
- **Noul** answers a yes/no question as a probability in `[0, 1]`.

Use confidence to decide whether a result needs review. A result is a recommendation, not an imperative.

## MCP server

Run the local stdio MCP server:

```sh
uv run python -m jev_mcp.server
```

It exposes one read-only tool: `jev_decide`. The server uses the same OpenRouter configuration as the CLI and pins the JEV model internally.

## Agent skill installation

The `jev` CLI installs the project-local decision skill for these harnesses:

- `claude-code`
- `opencode`
- `oh-my-pi`
- `pi`

```sh
jev install claude-code --project .
jev uninstall claude-code --project .
```

Use exactly one explicit scope: `--project <path>` or `--user`.

## Configuration

```sh
# Token enters through stdin and is never echoed.
printf '%s\n' "$JEV_API_TOKEN" | jev config set token --stdin

jev config set endpoint https://openrouter.ai/api/alpha/decisions
jev config list
jev config unset token
```

Persistent configuration is stored at `${XDG_CONFIG_HOME:-~/.config}/jev-poc/config.json`. Environment variables take precedence over persisted values.

## Safety

- Credentials are redacted from error output.
- Installer operations reject unsafe symlink paths.
- Uninstall removes only JEV's `SKILL.md`; it preserves unrelated files.
- Retries are limited to transient transport failures, `408`, `429`, and `5xx` responses.
