# JEV MCP Service Design (stdio, `jev_decide`)

Date: 2026-09-18 · Status: Approved implementation record

## 1. Goal / Non-goals

**Goal:** expose generic JEV-backed decisions to repository agents over MCP stdio as a
single non-destructive tool, `jev_decide`, backed by the existing `Config` /
`DecisionsClient` security boundary. Support **multiple named questions** per
call (`choice` | `score` | `noul`) so agents can resolve several material options in one round trip.

**Non-goals:**
- No conversational bot state, history accumulation, or framework presets in the server.
- No destructive / side-effecting tools; exactly one tool: `jev_decide`.
- No arbitrary model override: server fixes model to `~typesafe/jev-latest`.
- No open-ended generation, factual lookup, or safety-critical handling via JEV.
- No new auth, persistence, logging of secrets, or network surface beyond the existing
  Decisions endpoint.

## 2. Files and boundaries

| Path | Role |
|---|---|
| `jev_mcp/server.py` | stdio lifecycle, tool registration, input validation, client wiring. New. |
| `jev_bot/models.py` (`JEVRequest`, `JEVResponse`) | Migration target: generic multi-question model. Changed (see §9). |
| `jev_bot/config.py` (`load_config`, `Config`) | Sole credential/endpoint source. Reused unchanged. |
| `jev_bot/client.py` (`DecisionsClient`) | Sole HTTP boundary. Reused unchanged. |
| `jev_bot/errors.py` (`DecisionsError`) | Error type mapped to MCP tool errors. Reused. |
| `pyproject.toml` | Add `mcp` runtime dependency; add `jev_mcp` to build `include`. Changed. |
| `.agents/skills/using-jev-decisions/SKILL.md` | Repository agent skill: when/how to call `jev_decide`. New. |
| `docs/superpowers/specs/2026-09-18-jev-mcp-service-design.md` | This spec. |

Boundary rule: the server MUST NOT read tokens directly from `os.environ`, accept
credentials as tool arguments, or construct HTTP requests by hand. Flow is strictly
`validate input → load_config() → DecisionsClient(config).decide(request) → shaped result`.

## 3. Runtime and stdio lifecycle

- Python MCP SDK v2, stdio transport (`mcp.server.stdio.stdio_server` or equivalent).
  `pyproject.toml` MUST declare the `mcp` runtime dependency and include the `jev_mcp`
  package in the build `include` list.
- Startup: `load_config()` once, then construct exactly one `DecisionsClient(config)`
  and reuse it for every tool call in the process; on `EnvironmentError`/`ValueError` (missing token, bad
  endpoint) fail fast with a redacted stderr message and non-zero exit. Never print the token.
- Shutdown: close the single startup-constructed `DecisionsClient` session; flush stderr; exit 0.
- Async bridge: execute the synchronous `DecisionsClient.decide()` with
  `await asyncio.to_thread(client.decide, request)` from the async MCP tool handler;
  never block the MCP event loop on `requests`.
- Concurrency: sequential tool calls in one process are sufficient; no shared mutable state
  between calls beyond the reusable HTTP session.
- Timeouts: reuse `DecisionsClient` 30s timeout; no retries in the server.

## 4. Tool contract: `jev_decide`

Exactly one tool. Non-destructive (read-only decision query). No annotations implying
side effects.

### 4.1 Request schema

```json
{
  "type": "object",
  "required": ["state", "questions"],
  "additionalProperties": false,
  "properties": {
    "state": { "type": "string", "minLength": 1, "maxLength": 8000 },
    "questions": {
      "type": "object",
      "minProperties": 1,
      "maxProperties": 8,
      "additionalProperties": {
        "type": "object",
        "required": ["type", "instructions"],
        "additionalProperties": false,
        "properties": {
          "type": { "enum": ["choice", "score", "noul"] },
          "instructions": { "type": "string", "minLength": 1, "maxLength": 2000 },
          "criteria": {
            "anyOf": [
              {
                "type": "object",
                "minProperties": 2,
                "maxProperties": 16,
                "additionalProperties": { "type": "string", "minLength": 1, "maxLength": 1000 }
              },
              {
                "type": "array",
                "minItems": 2,
                "maxItems": 16,
                "items": { "type": "string", "minLength": 1, "maxLength": 1000 }
              }
            ]
          }
        }
      }
    }
  }
}
```

Discriminated validation rules (before any network call, in order):
1. `state` must be a non-blank string after `strip()`; cap 8000 chars.
2. `questions`: 1–8 entries. Each key must be a stable snake/camel identifier:
   `^[A-Za-z][A-Za-z0-9_]{0,63}$`, unique as given (JSON object semantics).
3. Each question: `type` must be exactly one of `"choice"`, `"score"`, `"noul"`;
   `instructions` non-blank (cap 2000 chars). Per-type `criteria` rules:
   - `choice`: `criteria` REQUIRED, a closed map of 2–16 entries with
     non-blank string keys (option keys, same identifier rule recommended) and
     non-blank string descriptions (cap 1000 chars each). Answer carries
     `choice` (string) + `probabilities` (map of finite numbers).
   - `score`: `criteria` REQUIRED, an ordered array of 2–16 non-blank rubric
     strings (cap 1000 chars each). Answer carries a finite numeric `score`
     plus any API-provided score metadata passed through verbatim in `extra`.
   - `noul`: `criteria` MUST be absent. Answer carries a finite numeric `noul`
     in `[0, 1]`.
4. No `model` field is accepted from the caller: if the input contains `model` at the
   top level or inside any question, reject with an invalid-params tool error naming
   `model`. The server sets `model = "~typesafe/jev-latest"` unconditionally on the
   outbound `JEVRequest`; the model remains fixed by the server and is never
   caller-supplied.
5. Any validation failure → MCP tool error (invalid params), no HTTP call.

### 4.2 Valid request example

```json
{
  "state": "Checkout latency p95 is 2.4s. Team of 3, two-week deadline, must keep PCI scope minimal.",
  "questions": {
    "paymentProvider": {
      "type": "choice",
      "instructions": "Which payment provider should we integrate?",
      "criteria": {
        "stripe": "Hosted checkout and webhooks; fastest integration, per-transaction fees.",
        "adyen": "Full acquiring stack; more control, longer integration and heavier compliance."
      }
    },
    "frontendApproach": {
      "type": "choice",
      "instructions": "Which frontend approach for the hosted checkout page?",
      "criteria": {
        "ssr": "Server-rendered page; best first paint, more backend work.",
        "spa_widget": "Embedded JS widget; fastest to ship, heavier client bundle."
      }
    }
  }
}
```

### 4.3 Result schema

Return one entry per requested question key, echoing only validated keys. Each
answer is discriminated by its result field: `choice` (+ `probabilities`),
`score` (+ API-provided metadata), or `noul`:

```json
{
  "type": "object",
  "required": ["answers"],
  "additionalProperties": false,
  "properties": {
    "answers": {
      "type": "object",
      "additionalProperties": {
        "anyOf": [
          {
            "type": "object",
            "required": ["choice", "probabilities"],
            "additionalProperties": false,
            "properties": {
              "choice": { "type": "string" },
              "probabilities": {
                "type": "object",
                "additionalProperties": { "type": "number" }
              }
            }
          },
          {
            "type": "object",
            "required": ["score"],
            "properties": {
              "score": { "type": "number" }
            }
          },
          {
            "type": "object",
            "required": ["noul"],
            "additionalProperties": false,
            "properties": {
              "noul": { "type": "number", "minimum": 0, "maximum": 1 }
            }
          }
        ]
      }
    }
  }
}
```

Valid result example (for the request above):

```json
{
  "answers": {
    "paymentProvider": {
      "choice": "stripe",
      "probabilities": { "stripe": 0.72, "adyen": 0.28 }
    },
    "frontendApproach": {
      "choice": "spa_widget",
      "probabilities": { "spa_widget": 0.61, "ssr": 0.39 }
    }
  }
}
```

Notes: `choice` SHOULD be one of the requested criteria keys but MUST be passed through
verbatim (server does not second-guess the model). Probabilities are passed through as
finite floats; non-finite or non-numeric values raise a tool error. `score` MUST be a
finite number; any additional score metadata fields are passed through verbatim in
`extra`. `noul` MUST be a finite number in `[0, 1]`; out-of-range or non-finite values
raise a tool error.

Mixed-types request example (one call, all three types):

```json
{
  "state": "Checkout latency p95 is 2.4s. Team of 3, two-week deadline.",
  "questions": {
    "paymentProvider": {
      "type": "choice",
      "instructions": "Which payment provider should we integrate?",
      "criteria": {
        "stripe": "Hosted checkout; fastest integration.",
        "adyen": "Full acquiring stack; longer integration."
      }
    },
    "readiness": {
      "type": "score",
      "instructions": "How ready is the checkout flow for launch?",
      "criteria": ["No errors on the happy path.", "p95 under 1s on staging."]
    },
    "novelty": {
      "type": "noul",
      "instructions": "How novel is the proposed retry approach?"
    }
  }
}
```

Corresponding mixed-types result:

```json
{
  "answers": {
    "paymentProvider": {
      "choice": "stripe",
      "probabilities": { "stripe": 0.72, "adyen": 0.28 }
    },
    "readiness": { "score": 7.5 },
    "novelty": { "noul": 0.42 }
  }
}
```

### 4.4 Error behavior

| Condition | Behavior |
|---|---|
| Invalid input (blank state, bad key, unknown `type`, choice map with <2 or empty criteria, score array with <2 or blank rubrics, `criteria` present on `noul` or missing where required, over limits) | Tool error, `Invalid params`-style message naming the offending field; no HTTP call. |
| Missing `JEV_API_TOKEN` / bad `JEV_ENDPOINT` | Tool error / startup failure; message only: `"JEV_API_TOKEN environment variable is required"` or endpoint message. Never echo values. |
| Transport / non-2xx / bad JSON / malformed payload | Propagate `DecisionsError` message verbatim as tool error (client already redacts token/endpoint/host and truncates to 300 chars). |
| Unknown question key in response / missing answers | Tool error `Malformed Decisions payload…`; do not fabricate answers. |

All error strings MUST be redacted: no token, no endpoint, no `Authorization` header,
no `password/secret/api[_-]?key` values (redaction is supplied by `DecisionsClient`'s
own error handling; the server MUST NOT reference a `DecisionsClient._redact` helper,
which does not exist).

## 5. Environment security constraints

- Credentials exclusively via `JEV_API_TOKEN` env (loaded by `load_config()`; `.env` via
  `load_dotenv` with `override=False`). Never accept tokens as tool args; never log them.
- `JEV_ENDPOINT` optional override; must remain an HTTPS `openrouter.ai` URL without
  userinfo (enforced by `config._validate_endpoint`). Reject otherwise.
- Outbound HTTPS only to the configured endpoint; `Authorization: Bearer <token>` header
  set only inside `DecisionsClient`.
- Error paths redact secrets and truncate snippets (300 chars). Server adds no logging of
  request bodies containing potential secrets beyond what is needed for validation errors
  (field names only, never values resembling credentials).
- Never expose credentials in tool schemas, descriptions, stdout results, or stderr logs.

## 6. MCP client registration

Stdio server entry point (example module path `jev_mcp.server:main`):

```json
{
  "mcpServers": {
    "jev": {
      "command": "uv",
      "args": ["run", "python", "-m", "jev_mcp.server"],
      "env": { "JEV_API_TOKEN": "${JEV_API_TOKEN}", "JEV_ENDPOINT": "${JEV_ENDPOINT}" }
    }
  }
}
```

Plain-`python` equivalent: `"command": "python", "args": ["-m", "jev_mcp.server"]`.
The server speaks MCP over stdio; clients discover the single `jev_decide` tool from the
`tools/list` response. No SSE/HTTP transport, no extra resources or prompts.

## 7. Repository agent skill

Path: `.agents/skills/using-jev-decisions/SKILL.md`. It MUST direct agents:

- **Call JEV whenever multiple material options exist** (the new policy): ≥2 viable
  approaches with real trade-offs (provider choice, architecture, rollout strategy).
  One tool call may carry up to 8 named questions.
- **Format rules:** bounded `state` (facts, constraints, deadline — no secrets);
  stable option keys (`stripe`, `ssr`, …); closed `criteria` map with one plain-language
  description per option; one crisp `instructions` question per entry; `type: "choice"`.
  `score` questions carry an ordered `criteria` array of ≥2 rubric strings;
  `noul` questions carry `instructions` only.
- **Do NOT use JEV for:** single-option execution confirmation (just do the work);
  open-ended generation or drafting; factual lookup (use search/docs); urgent safety
  handling (stop and escalate, do not deliberate via the model).
- Treat the result as a recommendation: `choice` + `probabilities`, `score` (+ metadata),
  or `noul` inform, not dictate;
  close probabilities (≈ tie) mean decide on engineering judgment and record why.

## 8. Test and evaluation strategy

Focused cases only (no project-wide runs required by this spec):

1. **Schema validation (no network):** blank `state`; zero / nine questions; bad key
   (`"has space"`, `"9x"`); `type: "open"`; choice criteria with 1 entry; blank criterion text;
   score criteria with 1 entry or a blank rubric; `criteria` on a `noul` question;
   oversized `state`/instructions — each rejected without HTTP.
2. **Model pinning:** stub transport captures outbound JSON; caller-supplied `model`
   (top-level or per-question) is rejected with an invalid-params tool error and no
   HTTP call. Absent `model`, assert `model == "~typesafe/jev-latest"` and
   multi-question keys pass through verbatim.
3. **Result shaping:** canned Decisions payload with 2 questions → both answers returned
   with `choice`/`probabilities`; mixed-types payload → `choice`/`probabilities`,
   finite `score` + metadata passthrough, and `noul` in `[0, 1]`; malformed payloads (missing `answers`, non-numeric or
   NaN probability, non-finite `score`, out-of-range `noul`) surface as tool errors. `JEVResponse` parsing tests cover arbitrary
   answer keys (not a fixed pair) using the existing per-answer validation.
4. **Security:** missing token → config error, no request; error text from non-2xx
   contains `[REDACTED]`, never the token/endpoint; endpoint with userinfo or non-HTTPS
   rejected at startup.
5. **Skill eval (manual):** two scripted scenarios — (a) genuine two-option decision
   produces a well-formed call; (b) single-option task and factual question produce no
   call. Reviewer checks trigger discipline and bounded-state formatting.

## 9. `jev_bot` model migration (generic multi-question JEV)

`JEVRequest` gains caller-supplied validated questions: a `questions` map of 1–8 named
questions of type `choice` (closed 2–16-entry `criteria` map), `score` (ordered
2–16-entry rubric array), or `noul` (`instructions` only), same identifier and
`instructions` rules as §4.1, while `model` stays server-fixed to `~typesafe/jev-latest` and is never taken
from the caller. `JEVResponse` parsing iterates arbitrary answer keys (not a fixed
question pair), applying the existing per-answer validation to each entry —
`choice`/`probabilities`, finite `score` + `extra` metadata passthrough, finite
`noul` in `[0, 1]` — and preserves the `framework` property for JevBot backwards compatibility
so existing JEV CLI behavior is unchanged.
