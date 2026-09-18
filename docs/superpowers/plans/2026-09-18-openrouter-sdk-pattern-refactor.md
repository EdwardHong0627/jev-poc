# OpenRouter SDK-Pattern Refactor Implementation Plan

**Goal:** Adopt TypeSafe SDK/cookbook typed-decision patterns while retaining the OpenRouter Decisions transport, API key, endpoint, and `~typesafe/jev-latest` model.

**Architecture:** Keep an explicit OpenRouter adapter because TypeSafe SDK hardcodes `/v1/systemone`, while OpenRouter supplies `/api/alpha/decisions`. Model the observed OpenRouter response as the SDK does: typed questions, structured JSON state, typed answers with confidence, and request usage metadata. Add bounded retries to the adapter; code remains responsible for confidence-gated action.

**Evidence:** Live OpenRouter response contained `model`, `answers`, `usage`, `id`, and `provider`; choice answers contained `type`, `choice`, `probabilities`, and `confidence`.

## Task 1: Typed SDK-compatible decision contract

**Files:** `jev_bot/models.py`, `tests/test_models.py`, `tests/test_public_api.py`, `jev_bot/__init__.py`

1. Write failing tests for object/array state serialization, `type` discrimination, optional Noul criteria, choice/score confidence validation, usage validation, and response metadata.
2. Run focused models tests; observe the expected failures.
3. Implement minimal typed contract: JSON-compatible state, SDK-compatible answer `type`/confidence, response `model`/usage/id/provider metadata, and strict malformed-payload errors. Preserve OpenRouter model id and legacy framework convenience.
4. Run focused tests green.

## Task 2: Resilient OpenRouter adapter

**Files:** `jev_bot/client.py`, `tests/test_client.py`

1. Write failing tests for retryable status/transport errors, non-retryable client errors, retry exhaustion, retry-after cap, and preserved response metadata.
2. Run focused client tests; observe RED.
3. Add a small explicit retry policy to the existing `requests` adapter. Keep the OpenRouter alpha endpoint, bearer JEV_API_TOKEN, 30-second per-attempt timeout, and sanitized errors. Retry only transient transport failures, 408, 429, and 5xx with bounded backoff.
4. Run focused client tests green.

## Task 3: Surface typed confidence through MCP and CLI

**Files:** `jev_mcp/server.py`, `tests/test_mcp_server.py`, `main.py`, `tests/test_main.py`

1. Write failing tests that MCP outputs answer `type` and `confidence` where OpenRouter provides it, preserves score metadata, and does not fabricate confidence. Add CLI test that renders confidence for framework answers when present.
2. Run focused MCP/CLI tests; observe RED.
3. Update the shape/render adapters only. They must consume the new models and retain their existing secret-safe error boundary.
4. Run focused tests green.

## Task 4: Align skill and user docs

**Files:** `.agents/skills/using-jev-decisions/SKILL.md`, `jev_bot/assets/using-jev-decisions/SKILL.md`, `README.md`

1. Update the canonical package skill and repository copy together: typed state may be object/array; results include confidence; agents must confidence-gate close choice/score decisions rather than treat the recommendation as a command. Preserve the OpenRouter model rule.
2. Update README transport description and examples: this is an OpenRouter adapter, not TypeSafe SDK; document bounded retries and response confidence.
3. Add parity/doc tests only for externally observable contract claims.

## Verification

Run focused suites after each task, then `uv run python -m pytest -q`. Exercise one OpenRouter decision using the configured token and assert only structural response keys/types; never print token, state, endpoint, or answer content.