# Plan: JEV MCP Service (`jev_decide`) + Repository Agent Skill

Date: 2026-09-18 · Spec: `docs/superpowers/specs/2026-09-18-jev-mcp-service-design.md`

## Required Header
- Goal: single non-destructive MCP stdio tool `jev_decide` resolving 1–8 named questions (`choice`|`score`|`noul`) per call, model pinned server-side to `~typesafe/jev-latest`, backed only by `load_config()` + `DecisionsClient.decide()`.
- Non-goals: no framework presets/history in server, no second tool, no caller `model`, no generation/factual/safety use, no new auth/persistence.
- Boundary rule: `validate → load_config() → DecisionsClient(config).decide(request) → shaped result`. Never read tokens from `os.environ` in server, never accept credentials as tool args, never hand-build HTTP.

## File Map
| File | Action |
|---|---|
| `jev_mcp/__init__.py` | NEW — package marker/exports |
| `jev_mcp/server.py` | NEW — stdio lifecycle, `jev_decide` registration/validation, `asyncio.to_thread` bridge, redacted errors |
| `jev_bot/models.py` (`JEVRequest`, `JEVResponse`) | EDIT — generic `questions` map (spec §9); keep `framework` property |
| `pyproject.toml` | EDIT — add `mcp` runtime dep; add `jev_mcp` to build `include` |
| `tests/test_jev_mcp_server.py` | NEW — validation, pinning, shaping, security tests |
| `tests/test_jev_models_generic.py` (or extend existing model tests) | EDIT/NEW — generic question/response parsing |
| `.agents/skills/using-jev-decisions/SKILL.md` | NEW — test-driven skill (baseline red → post-skill green) |
| `README.md` (MCP section only) | EDIT — stdio registration snippet + single-tool note |

## Chunk 1 — Models + Packaging (no network)
1. `jev_bot/models.py`: `JEVRequest` gains `questions: dict[str, Question]` (1–8 keys matching `^[A-Za-z][A-Za-z0-9_]{0,63}$`; `instructions` non-blank ≤2000; `model` field retained with default `~typesafe/jev-latest`, never caller-set via tool). `Question = ChoiceQuestion | FrameworkQuestion | ScoreQuestion | NoulQuestion` where NEW `ChoiceQuestion` (`type="choice"`: caller-supplied `instructions` + closed 2–16 non-blank criteria map, owns its criteria-count/blank validation) is the generic MCP choice shape; `FrameworkQuestion` keeps `type=FRAMEWORK_TYPE` (`"choice"`) with its `FRAMEWORK_INSTRUCTIONS`/`FRAMEWORK_CRITERIA` defaults unchanged for the legacy CLI; `score`→ordered 2–16 rubric array (owned by `ScoreQuestion`), `noul`→no criteria (owned by `NoulQuestion`). `JEVResponse` parses arbitrary named answers and retains its framework compatibility property.
2. `pyproject.toml`: add `mcp` (SDK v2) runtime dependency; add `jev_mcp` to `include`.
3. RED: add model tests — blank state/key, 0/9 questions, bad keys, `type:"open"`, 1-entry/blank `choice` criteria on `ChoiceQuestion`, 1-entry/blank score, criteria-on-noul, oversized state/instructions, default `model == "~typesafe/jev-latest"` when unset, malformed answers (missing `answers`, NaN/non-numeric prob, non-finite score, out-of-range noul). NOTE: caller-`model` rejection is NOT a model test — it is enforced only by the MCP input schema (`additionalProperties: false`, no `model` field) + tool validation (Chunk 2).
4. GREEN: implement; run `uv run pytest tests/test_jev_models_generic.py -q`.

## Chunk 2 — MCP Server (`jev_mcp/server.py`)
1. Startup: `load_config()` once → one `DecisionsClient(config)` reused; `EnvironmentError`/`ValueError` → generic redacted stderr (never echo endpoint/userinfo values) + non-zero exit. Config change (recommended, protects all callers): change `_validate_endpoint` to raise generic `ValueError("JEV_ENDPOINT is not a valid URL")` without interpolating the endpoint; server additionally scrubs/redacts any endpoint content before writing stderr. Shutdown: close client session, flush stderr, exit 0.
2. Register exactly one tool `jev_decide` with spec §4.1 schema; discriminated validation in order (state → keys → type/criteria → reject any caller `model` top-level or per-question); failures → invalid-params tool error, no HTTP.
3. Handler: `await asyncio.to_thread(client.decide, request)`; shape result per §4.3 (passthrough `choice` verbatim, finite checks, `score`+`extra`, `noul` range); malformed/unknown keys → `Malformed Decisions payload…`; propagate `DecisionsError` verbatim (client redacts); never reference `DecisionsClient._redact`.
4. RED→GREEN: `tests/test_jev_mcp_server.py` — stub `DecisionsClient.decide`: (a) all validation cases make zero HTTP calls (incl. `type:"choice"` 1-entry/blank criteria rejected by `ChoiceQuestion`); (b) caller-`model` (top-level or per-question) rejected by input schema/tool validation only, absent-`model` asserts server sets outbound `model == "~typesafe/jev-latest"` + keys verbatim; (c) 2-choice + mixed-type shaping; malformed payloads error; (d) missing token → generic redacted config error, redacted non-2xx text, bad endpoint (incl. userinfo) rejected with no endpoint/userinfo bytes on stderr. Run `uv run pytest tests/test_jev_mcp_server.py -q`.
5. Integration: stdio smoke — launch `uv run python -m jev_mcp.server`, `tools/list` shows only `jev_decide`, one stubbed `tools/call` returns shaped answers; then stop.

## Chunk 3 — Skill (test-driven) + Docs
1. Baseline RED (before writing skill): run 4 scripted prompts against an agent WITHOUT the skill — (a) two-option provider choice, (b) multi-question architecture call, (c) single-option task (must NOT call), (d) factual lookup (must NOT call). Record: mis-trigger or malformed calls expected.
2. Write `.agents/skills/using-jev-decisions/SKILL.md`: call JEV when ≥2 viable options with real trade-offs (up to 8 questions/call); format rules (bounded secret-free `state` ≤8000, stable keys, closed choice map, ordered score rubrics, noul instructions-only, one crisp `instructions` each); DO NOT use for single-option confirmation, generation/drafting, factual lookup, safety handling; treat result as recommendation, ties → engineering judgment + record why.
3. Post-skill GREEN: re-run same 4 scenarios WITH skill — (a)(b) well-formed calls, (c)(d) no call. Reviewer checks trigger discipline + bounded-state formatting.
4. Docs: README MCP section (`jev` stdio entry: `uv run python -m jev_mcp.server` + plain-python variant); public exports unchanged except `jev_mcp` package.
5. Security check: grep for token/endpoint leaks in schemas, stdout, stderr; confirm no `model` in tool schema, no `_redact` reference, no retries, 30s client timeout reused.

## Explicit Non-Goals
No token literals in plan/code/tests; no trivial always-pass smoke tests; no placeholders/stubs in shipped code; no unrelated refactors; no commits, no worktree/branch actions, no project-wide test/lint/format runs.
