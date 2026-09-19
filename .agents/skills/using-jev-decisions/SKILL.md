# Using JEV Decisions

Use when the agent faces a material choice with two or more viable options that have real trade-offs (architecture, provider, rollout strategy, approach). Call MCP `jev_decide` with a bounded, secret-free `state`, up to 8 named questions, and one crisp `instructions` per question.

## Transport note

This is an **OpenRouter adapter** (`~typesafe/jev-latest` via OpenRouter's `/api/alpha/decisions` endpoint). It is NOT the TypeSafe SDK transport (`/v1/systemone`). The server pins the model identifier and rejects any caller-provided `model` field. Authentication uses `JEV_API_TOKEN` against OpenRouter, not a TypeSafe credentials store.

## When to call JEV

- **≥ 2 materially different options** with genuine trade-offs (provider, framework, architecture, rollback plan).
- Multiple questions can be answered in a single call (up to 8).

## When NOT to call JEV

- **Factual retrieval** (look up an API, read docs, check a version).
- **Generation / drafting** (write a doc, compose text, create content).
- **Single direct operation** (rename a file, move a block, create a test).
- **One-option confirmation** (the choice is already determined by constraints).
- **Urgent safety** (stop, escalate; do not deliberate via the model).

## Calling `jev_decide`

Send an MCP tool call with exactly this shape (no `model` field):

```
{
  "state": "Concise context: constraints, deadline, team size, facts — no secrets.",
  "questions": {
    "questionKey": {
      "type": "choice | score | noul",
      "instructions": "One crisp question.",
      "criteria": { ... }  // REQUIRED for choice/score; ABSENT for noul
    }
  }
}
```

### `type: "choice"` — pick one option

- `criteria` is a **closed map** of 2–16 option keys to plain-language descriptions.
- Option keys are stable identifiers (e.g. `stripe`, `ssr`, `spa_widget`).
- Result: `{ "type": "choice", "choice": "<key>", "probabilities": { "<key>": 0.72, ... }, "confidence": <float in [0,1]> }`.

### `type: "score"` — rate against rubrics

- `criteria` is an **ordered array** of 2–16 rubric strings (not a map).
- Result: `{ "type": "score", "score": <float>, "confidence": <float in [0,1]>, ...extra metadata }`.

### `type: "noul"` — assess novelty

- **NO** `criteria` field — only `type` and `instructions`.
- Result: `{ "type": "noul", "noul": <float in [0,1]>, ...confidence is optional }`.

### State formatting

- Start with raw facts, constraints, deadline, team capacity.
- No secrets, credentials, tokens, or internal API keys.
- Cap: 8 000 characters.
- State accepts structured JSON (objects and arrays) in addition to plain strings.

### Question naming

- Use stable snake/camel identifiers: `paymentProvider`, `frontendApproach`.
- 1–8 questions per call, each with one `type` and one `instructions`.

## Interpreting results

- `choice` + `probabilities` is a **recommendation**, not a mandate.
- Use the `confidence` value to gauge whether the decision warrants human review.
- **Confidence-gated routing:** when confidence is low or probabilities are close (≈ tie, diff < 0.2), use engineering judgment and **record why** you picked the one with more signal.
- `score` and `noul` inform but do not decide alone; weigh against your domain knowledge.
- `noul` results may include `confidence`; when absent, treat the value as informational only.

## Self-check before calling

1. Do I have **≥ 2 viable options** with real trade-offs? (If no → don't call.)
2. Is `state` bounded, factual, and secret-free?
3. Does every `choice` question have a **closed criteria map** (2–16 entries)?
4. Does every `score` question have an **ordered criteria array** (2–16 items)?
5. Does every `noul` question have **no `criteria`** at all?
6. Are there **no `model` fields** anywhere in the payload?
7. Are there **no more than 8 questions** in the map?

## Common mistakes (and how to fix them)

| Mistake | Why it fails | Fix |
|---------|-------------|-----|
| `criteria` as a map for a `score` question | Score expects an ordered array, not a key-value map | Use `"criteria": ["rubric1", "rubric2"]` |
| `criteria` missing from a `choice` question | Choice requires a closed criteria map with 2+ entries | Add `"criteria": {"opt1": "desc", "opt2": "desc"}` |
| `criteria` present on a `noul` question | Noul has no criteria — it is instructions-only | Remove `criteria` entirely |
| Only one option in a `choice` criteria map | Must have 2–16 entries | Add the alternative option |
| Including a `model` field | The server pins model to `~typesafe/jev-latest` | Remove it from top-level and per-question |
| Using JEV for factual lookup | Not a decision — just look it up | Call search / docs instead |
| Using JEV for a single direct operation | Rename, move, create = deterministic | Do the operation directly |
| Treating recommendation as a command | Low confidence or close probabilities need human judgment | Use confidence-gated routing |

## Batch independent questions

Questions that do not share constraints can be answered in a single MCP call (up to 8). This reduces round-trips while keeping each question focused on one decision dimension.

## Pressure example: architecture decision (correct)

**Scenario:** Under time pressure, the team must pick a payment provider. Two options exist with real trade-offs.

### ❌ Invalid baseline payload (baseline failure mode)

```json
{
  "question": "Which provider?",
  "criteria": ["stripe", "adyen"],
  "context": "Need to integrate payments quickly."
}
```

Three errors:
1. `question` — must be a `questions` map of keyed entries, not a string.
2. `criteria` as an array — `choice` requires a closed map of key→description, not a flat list.
3. `context` — state belongs at the top level as `state`, not inside questions.

### ✅ Valid payload under pressure

```json
{
  "state": "Two-week deadline, team of 3, must keep PCI scope minimal. Checkout latency target p95 < 1s.",
  "questions": {
    "provider": {
      "type": "choice",
      "instructions": "Which payment provider should we integrate?",
      "criteria": {
        "stripe": "Hosted checkout and webhooks; fastest integration, per-transaction fees.",
        "adyen": "Full acquiring stack; more control, longer integration and heavier compliance."
      }
    }
  }
}
```

### ✅ Valid payload: multi-question, mixed types

```json
{
  "state": "Checkout latency p95 is 2.4s. Team of 3, two-week deadline, must keep PCI scope minimal.",
  "questions": {
    "provider": {
      "type": "choice",
      "instructions": "Which payment provider should we integrate?",
      "criteria": {
        "stripe": "Hosted checkout and webhooks; fastest integration, per-transaction fees.",
        "adyen": "Full acquiring stack; more control, longer integration and heavier compliance."
      }
    },
    "readiness": {
      "type": "score",
      "instructions": "How ready is the checkout flow for launch?",
      "criteria": [
        "No errors on the happy path.",
        "p95 under 1s on staging.",
        "Fraud rates below 0.5%."
      ]
    },
    "novelty": {
      "type": "noul",
      "instructions": "How novel is the proposed retry approach?"
    }
  }
}
```
