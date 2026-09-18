# JEV Conversational Bot — Design Spec

- **Date:** 2026-09-18
- **Status:** Approved
- **Surface:** Conversational bot (thin text chat loop over the JEV Decisions API)

## Context

The JEV Decisions API (OpenRouter) accepts a bounded snapshot of conversational
**state** and a set of narrow, framed **questions**, then returns, for each
question, a model-selected **choice** plus the full set of candidate
**probabilities** (a candidate-to-number mapping over the closed answer set).
This work wraps that API in a conversational front-end so a user can type
natural-language context and receive structured, comparable decisions in a
back-and-forth chat.

The single most important boundary: **JEV selects from the supplied criteria
based on state and does not generate the conversational text.** The model
returns structured selections and probabilities only; the surrounding natural
language ("Here's what I'd suggest…") is produced by the framework's UI/templating
layer, not by this package. This keeps the package focused on decisions and lets
any framework own the persona/voice.

The package contributes two fixed pieces:

1. **Framework criteria** — a static package configuration. The set of criteria,
   their keys, and their descriptions are authored once in the package (not by
   the user, not by the model) and sent verbatim on every request.
2. **`state`** — the bounded, framed chat context that changes each turn. The
   package derives this from the rolling history and sends it verbatim.

The framework that best fits those fixed criteria is itself selected once up front
via a single JEV `questions.framework` call.

## Goal

Provide a reusable package that maps bounded chat context to JEV `state`, calls
the Decisions API, and returns `answers.framework.{choice, probabilities}` for
presentation. A thin `main.py` drives a conversational loop over that package.

## Non-Goals

- Generating or polishing the natural-language conversational wrapper text.
- Inventing, scoring, or ranking criteria at request time — the framework
  criteria are a static package artifact; JEV only selects.
- Persisting chat history across sessions (history is bounded within a session
  only).
- Any particular framework: the framework is selected by the criteria above and
  must satisfy them.

## Architecture

Package-first. The conversational surface is a thin shell around `jev_bot`.

```
main.py                 Thin conversational loop. Reads input, prints output,
                        delegates all decisions to JevBot. Owns nothing but the
                        loop and framework glue.

jev_bot/
    __init__.py         Public surface: export JevBot, models.
    models.py           Typed JEV request/response models (see below).
    config.py           Environment-based configuration (endpoint + token).
    client.py           OpenRouter Decisions API client. Pure HTTP + typed
                        request/response mapping. No framework deps.
    service.py          Maps bounded chat context -> JEV state, invokes client,
                        returns the answered framework choice + probabilities.
                        The only place that knows chat context.
    state.py            (if needed) helpers to summarize bounded history into a
                        stable, framed `state` string.
```

### File Responsibilities

- **`models.py`** — dataclasses/pydantic models for the exact JEV contract:
  - `FrameworkQuestion(type: str, instructions: str, criteria: dict[str, str])`
  - `JEVRequest(model: str, state: str, questions: dict)`
  - `ChoiceResult(choice: Optional[str], probabilities: dict[str, float])`
  - `JEVResponse(answers: dict[str, ChoiceResult])`
- **`config.py`** — reads endpoint URL and API token from environment variables
  only. Token has no default; explicit failure if absent.
- **`client.py`** — builds the OpenRouter request body from `JEVRequest`,
  sends it, decodes the JSON into `JEVResponse`. Raises on non-2xx.
- **`service.py`** — `JevBot` class. Takes bounded chat history, derives the
  current `state`, calls `client.decide()`, returns the framework
  `ChoiceResult`. The `questions.framework` criteria are provided as static
  package configuration.
- **`main.py`** — framework loop. Forwards user text to `JevBot`, renders the
  returned framework `choice` + `probabilities`.

## Request & Response Data Flow

1. User types a message into the chat (context, criteria, or follow-up).
2. `main.py` forwards the raw text to `JevBot`.
3. `service.py` bounds the history (keep N most recent turns), frames it into the
   current `state` string, and calls `client.decide(request)`.
4. `client.py` POSTs the exact `JEVRequest` body to
   `https://openrouter.ai/api/alpha/decisions` over OpenRouter.
5. The API returns `JEVResponse`. The relevant key is `answers.framework`:
   - `answers.framework.choice` — the selected framework.
     `answers.framework.probabilities` — candidate-to-number mapping
     (candidate → 0..1 likelihood) covering the full candidate set and each
     alternative's likelihood.
6. `service.py` extracts and returns `answers.framework` to `main.py`.
7. `main.py` / framework renders the framework selection. **JEV-provided content
   is `answers.framework`; the conversational sentence is framework-generated.**

Model: `~typesafe/jev-latest`.

### Exact JEV request body

```json
{
  "model": "~typesafe/jev-latest",
  "state": "<bounded, framed chat context for this turn>",
  "questions": {
    "framework": {
      "type": "choice",
      "instructions": "Which framework should I follow?",
      "criteria": {
        "custom": "Custom application from scratch; maximum control, highest engineering cost.",
        "openwebui": "Open WebUI interface; ready-made chat experience, less control over workflow.",
        "chainlit": "Python-native conversational UI; fast to build a purpose-specific bot.",
        "gradio": "Rapid browser chatbot prototype; minimal setup, suitable for demos.",
        "streamlit": "Internal decision-support app with chat and forms; strong for business tools.",
        "fastapi_react": "FastAPI backend with a React frontend; production-oriented and fully customizable."
      }
    }
  }
}
```

### Exact JEV answer envelope

```json
{
  "answers": {
    "framework": {
      "choice": "<selected framework>",
      "probabilities": {
        "<candidate>": <number>,
        ...
      }
    }
  }
}
```

## Environment / Credential Handling

- **`JEV_API_TOKEN`** — OpenRouter API key. Required. Never defaulting; read from
  the environment; never written to source, logs, or request bodies beyond the
  Authorization header.
- **`JEV_ENDPOINT`** — optional override of the Decisions endpoint; defaults to
  the absolute URL `https://openrouter.ai/api/alpha/decisions`.
- Config is read once at startup; missing token raises a clear `EnvironmentError`
  before the loop starts. Token is never exposed in responses or error text.

## Framework Criteria (static package configuration)

The `questions.framework.criteria` block is authored once in the package and sent
verbatim every request. It enumerates the closed candidate set JEV selects from:

| Key | Description |
|-----|-------------|
| `custom` | Custom application from scratch; maximum control, highest engineering cost. |
| `openwebui` | Open WebUI interface; ready-made chat experience, less control over workflow. |
| `chainlit` | Python-native conversational UI; fast to build a purpose-specific bot. |
| `gradio` | Rapid browser chatbot prototype; minimal setup, suitable for demos. |
| `streamlit` | Internal decision-support app with chat and forms; strong for business tools. |
| `fastapi_react` | FastAPI backend with a React frontend; production-oriented and fully customizable. |

## Validation & Error Behavior

- **Missing token:** clear error at startup before any chat input is accepted.
- **Network / transport error:** surface a generic message; never leak token or
  full URL path details to the user.
- **Non-2xx API response:** raise with status + body snippet; loop continues,
  presenting a safe message, not a stack trace.
- **Malformed API payload:** client decodes defensively; on schema mismatch,
  raise a typed `DecisionsError` — never return partial/unstructured data.
- **`answers.framework` missing or malformed:** raise `DecisionsError`; the loop
  continues, presenting a safe message, not a stack trace.
- **Token never** appears in responses, logs, or error strings.

## Test Approach (behavior-focused, no framework required)

- `config`: token absent → raises; token present + `JEV_ENDPOINT` override →
  correct endpoint value (`https://openrouter.ai/api/alpha/decisions` by default).
- `client`: the request body shape matches the exact JEV contract
  (`model`, `state`, `questions.framework` with `type`/`instructions`/`criteria`);
  non-2xx raises `DecisionsError`; valid JSON maps into `JEVResponse`
  (`answers.framework.choice` + `answers.framework.probabilities`).
- `service`: bounded history is trimmed to N turns before building the request;
  the emitted `questions.framework` payload is asserted exactly
  (`instructions`, `type: "choice"`, static criteria); the happy path returns
  `answers.framework` unchanged.
- `models`/`client` boundary: malformed payload raises, does not silently pass.
- `main`/framework glue: thin loop passes text through; rendering is asserted at
  the `answers.framework.choice` / `probabilities` level only, never at generated
  conversational text.

## Notes

- The default endpoint is the absolute URL `https://openrouter.ai/api/alpha/decisions`.
- Model: `~typesafe/jev-latest`.
- Framework criteria are static package configuration; only `state` varies per turn.
