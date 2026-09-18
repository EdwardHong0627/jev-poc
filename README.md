# JEV PoC

Typed decisions over the JEV Decisions API.

## Setup

`JEV_API_TOKEN` is required in the environment. Set it before running; the
program exits with a configuration error when it is missing.

`JEV_ENDPOINT` is optional. When unset, the default endpoint is used. When set,
it must be an HTTPS URL on `openrouter.ai` without userinfo, otherwise startup
fails with a configuration error.

## Install with uvx

`uvx` runs the `jev` console entry point from a freshly isolated environment,
so no local package installation is required:

```sh
uvx --from git+https://github.com/EdwardHong0627/jev-poc.git jev --help
```

## Console CLI

A Typer-based CLI provides skill installation, removal, and config management:

```sh
# Install the JEV skill into a harness destination
jev install <harness> --project <path>
jev install <harness> --user <path>

# Remove a previously installed skill
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
