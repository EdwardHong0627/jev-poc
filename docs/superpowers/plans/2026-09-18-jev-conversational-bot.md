# JEV Conversational Bot Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the direct JEV request with a secure, reusable `jev_bot` package and a small CLI conversation loop that returns a framework choice and probabilities.

**Architecture:** `jev_bot` owns the fixed framework question, typed request/response mapping, environment configuration, HTTP boundary, and bounded conversation state. `main.py` owns only terminal input/output. The package sends the exact OpenRouter Decisions payload from the approved design and never receives an API token as a function argument.

**Tech Stack:** Python 3.12, `requests`, `dataclasses`, pytest, `unittest.mock`, uv.

---

## Chunk 1: Package contract and HTTP boundary

### Task 1: Add test support and secure configuration

**Files:**
- Modify: `pyproject.toml:1-9`
- Modify: `.gitignore:1-10`
- Create: `tests/test_config.py`
- Create: `jev_bot/__init__.py`
- Create: `jev_bot/config.py`

- [ ] **Step 1: Add the failing configuration tests**

```python
import pytest

from jev_bot.config import DEFAULT_ENDPOINT, load_config


def test_load_config_rejects_missing_token(monkeypatch):
    monkeypatch.delenv("JEV_API_TOKEN", raising=False)

    with pytest.raises(EnvironmentError, match="JEV_API_TOKEN"):
        load_config()


def test_load_config_reads_token_and_default_endpoint(monkeypatch):
    monkeypatch.setenv("JEV_API_TOKEN", "test-token")
    monkeypatch.delenv("JEV_ENDPOINT", raising=False)

    config = load_config()

    assert config.token == "test-token"
    assert config.endpoint == DEFAULT_ENDPOINT


def test_load_config_honors_endpoint_override(monkeypatch):
    monkeypatch.setenv("JEV_API_TOKEN", "test-token")
    monkeypatch.setenv("JEV_ENDPOINT", "https://example.test/decisions")

    assert load_config().endpoint == "https://example.test/decisions"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`

Expected: FAIL because `jev_bot.config` does not exist.

- [ ] **Step 3: Add pytest and implement configuration**

Add pytest as a development dependency in `pyproject.toml`; do not add runtime dependencies. Add `.env` to `.gitignore`. Implement:

```python
@dataclass(frozen=True)
class Config:
    endpoint: str
    token: str

DEFAULT_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"

def load_config() -> Config: ...
```

`load_config()` reads `JEV_API_TOKEN`, raises `EnvironmentError` when it is absent or empty, and reads optional `JEV_ENDPOINT`. Do not add a token default, write an `.env` file, or log a token.

- [ ] **Step 4: Run the configuration test**

Run: `uv run pytest tests/test_config.py -v`

Expected: PASS with three tests.

- [ ] **Step 5: Commit the isolated configuration change**

```bash
git add pyproject.toml .gitignore jev_bot/__init__.py jev_bot/config.py tests/test_config.py
git commit -m "feat: add secure JEV configuration"
```

### Task 2: Define the exact JEV request and response models

**Files:**
- Create: `jev_bot/models.py`
- Create: `jev_bot/framework.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing contract tests**

```python
import pytest

from jev_bot.errors import DecisionsError
from jev_bot.framework import FRAMEWORK_QUESTION
from jev_bot.models import ChoiceResult, JEVRequest, JEVResponse


def test_request_serializes_exact_framework_choice():
    request = JEVRequest(state="User needs a quick internal prototype.")

    assert request.to_payload() == {
        "model": "~typesafe/jev-latest",
        "state": "User needs a quick internal prototype.",
        "questions": {"framework": FRAMEWORK_QUESTION.to_payload()},
    }


def test_response_extracts_framework_choice_and_probabilities():
    response = JEVResponse.from_payload({
        "answers": {"framework": {"choice": "gradio", "probabilities": {"gradio": 0.8, "custom": 0.2}}}
    })

    assert response.framework == ChoiceResult(
        choice="gradio", probabilities={"gradio": 0.8, "custom": 0.2}
    )

def test_response_rejects_missing_framework_answer():
    with pytest.raises(DecisionsError):
        JEVResponse.from_payload({"answers": {}})


def test_response_rejects_non_numeric_probability():
    with pytest.raises(DecisionsError):
        JEVResponse.from_payload({
            "answers": {"framework": {"choice": "gradio", "probabilities": {"gradio": "high"}}}
        })

def test_response_rejects_non_string_choice():
    with pytest.raises(DecisionsError):
        JEVResponse.from_payload({
            "answers": {"framework": {"choice": 7, "probabilities": {"gradio": 1.0}}}
        })


def test_response_rejects_missing_probabilities():
    with pytest.raises(DecisionsError):
        JEVResponse.from_payload({
            "answers": {"framework": {"choice": "gradio"}}
        })
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_models.py -v`

Expected: FAIL because `jev_bot.framework` and `jev_bot.models` do not exist.

- [ ] **Step 3: Implement static question and dataclass validation**

Implement `FrameworkQuestion`, `JEVRequest`, `ChoiceResult`, and `JEVResponse` using `dataclasses`. `FRAMEWORK_QUESTION` must be immutable and serialize exactly as:

```python
{
    "type": "choice",
    "instructions": "Which framework should I follow?",
    "criteria": {
        "custom": "Custom application from scratch; maximum control, highest engineering cost.",
        "openwebui": "Open WebUI interface; ready-made chat experience, less control over workflow.",
        "chainlit": "Python-native conversational UI; fast to build a purpose-specific bot.",
        "gradio": "Rapid browser chatbot prototype; minimal setup, suitable for demos.",
        "streamlit": "Internal decision-support app with chat and forms; strong for business tools.",
        "fastapi_react": "FastAPI backend with a React frontend; production-oriented and fully customizable.",
    },
}
```

`JEVResponse.from_payload()` must reject an absent or malformed `answers.framework`, a non-string choice, missing probabilities, or non-numeric probability values. Put the typed exception in `jev_bot/errors.py` before importing it from models.

- [ ] **Step 4: Run the model tests**

Run: `uv run pytest tests/test_models.py -v`

Expected: PASS; the happy-path and all malformed-payload tests pass.

- [ ] **Step 5: Commit the contract**

```bash
git add jev_bot/errors.py jev_bot/framework.py jev_bot/models.py tests/test_models.py
git commit -m "feat: define typed JEV decision contract"
```

### Task 3: Implement a safe Decisions API client

**Files:**
- Create: `jev_bot/client.py`
- Create: `tests/test_client.py`

- [ ] **Step 1: Write failing HTTP-boundary tests**

Use a fake session with a recording `post()` method. Assert that `DecisionsClient(config, session).decide(JEVRequest("context"))` posts to `config.endpoint`, passes the exact `request.to_payload()` as JSON, sends the token only in the Authorization header, and returns the parsed `JEVResponse`. Add tests for a non-2xx status and non-JSON/malformed response. A non-2xx error retains its status and a bounded, token-sanitized response-body snippet for diagnostics; its public message must not include the token or endpoint.

- [ ] **Step 2: Run the client test to verify it fails**

Run: `uv run pytest tests/test_client.py -v`

Expected: FAIL because `DecisionsClient` does not exist.

- [ ] **Step 3: Implement the client**

```python
class DecisionsClient:
    def __init__(self, config: Config, session: requests.Session | None = None): ...
    def decide(self, request: JEVRequest) -> JEVResponse: ...
```

Use `requests.Session` when one is not injected. Call `post` with the configured absolute endpoint, `json=request.to_payload()`, and a bearer Authorization header. Convert `requests.RequestException`, non-2xx responses, invalid JSON, and model validation failures to typed errors. `DecisionsError` carries a status code and bounded, token-sanitized body snippet for non-2xx diagnostics; `main.py` alone converts every client error to a generic safe user message.

- [ ] **Step 4: Run the client tests**

Run: `uv run pytest tests/test_client.py -v`

Expected: PASS; no test makes a network request.

- [ ] **Step 5: Commit the client**

```bash
git add jev_bot/client.py tests/test_client.py
git commit -m "feat: add JEV decisions client"
```

---

### Security prerequisite: rotate the exposed credential

Before executing source changes, revoke the credential currently embedded in `main.py` through the OpenRouter account and create a replacement. The repository has no commits, so no history rewrite is needed. Do not paste either credential into a terminal transcript, test, plan, or repository file; set only the replacement in the process environment as `JEV_API_TOKEN`.

## Chunk 2: Stateful service, CLI cutover, and delivery

### Task 4: Build bounded conversational state

**Files:**
- Create: `jev_bot/service.py`
- Create: `tests/test_service.py`

- [ ] **Step 1: Write failing service tests**

Use a fake client returning `ChoiceResult("gradio", {"gradio": 1.0})`. Create `JevBot(client, history_size=2)`, send three messages, and assert the third request's `state` contains only the two most recent user messages in stable chronological order. Assert it always contains the exact static framework question. Assert an empty or whitespace-only message does not call the client and raises `ValueError`.

- [ ] **Step 2: Run the service test to verify it fails**

Run: `uv run pytest tests/test_service.py -v`

Expected: FAIL because `JevBot` does not exist.

- [ ] **Step 3: Implement the minimal service**

Implement `JevBot.message(text: str) -> ChoiceResult`. Normalize only outer whitespace, reject an empty result, append the message, retain the latest `history_size` turns, join them with a stable newline delimiter into `JEVRequest.state`, then delegate exactly once to `client.decide()` and return `response.framework`.

- [ ] **Step 4: Run the service tests**

Run: `uv run pytest tests/test_service.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the service**

```bash
git add jev_bot/service.py tests/test_service.py
git commit -m "feat: add bounded JEV conversation service"
```

### Task 5: Replace the direct request with the CLI loop

**Files:**
- Modify: `main.py:1-36`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write failing rendering and loop tests**

Test `render_result(ChoiceResult("gradio", {"gradio": 0.8, "custom": 0.2}))` returns a stable display with the selected choice followed by candidates in descending probability order. Patch `main.build_bot` with a fake factory that returns a fake bot; patch `input` to supply one message then `quit`; assert the loop renders the result and exits. Add a blank-input test that confirms the loop continues without calling the bot. Add a missing-config test that prints a safe configuration error to stderr and returns a nonzero exit status.

- [ ] **Step 2: Run the CLI test to verify it fails**

Run: `uv run pytest tests/test_main.py -v`

Expected: FAIL because the old one-shot request script has no rendering or loop functions.

- [ ] **Step 3: Implement clean cutover in `main.py`**

Remove the direct `requests.post` implementation and all literal credentials. Add `render_result(result: ChoiceResult) -> str`, `build_bot(config: Config) -> JevBot`, and `main() -> int`. `build_bot()` constructs `DecisionsClient(config)` then `JevBot(client)`. `main()` catches `EnvironmentError` from configuration, writes a generic configuration failure to stderr, and returns `1`; otherwise it skips blank input before calling the bot, accepts input until `quit`, and prints a safe generic API failure message for `DecisionsError`. Use `raise SystemExit(main())` under the module guard.

- [ ] **Step 4: Run the CLI test**

Run: `uv run pytest tests/test_main.py -v`

Expected: PASS without a live token or network.

- [ ] **Step 5: Commit the CLI cutover**

```bash
git add main.py tests/test_main.py
git commit -m "feat: add JEV conversational CLI"
```

### Task 6: Expose the package and document usage

**Files:**
- Modify: `jev_bot/__init__.py`
- Modify: `README.md:1`

- [ ] **Step 1: Write the failing public-import test**

Add a test that imports `Config`, `DecisionsClient`, `JevBot`, `ChoiceResult`, and `DecisionsError` from `jev_bot` and uses them without importing private modules.

- [ ] **Step 2: Run the public-import test to verify it fails**

Run: `uv run pytest tests/test_public_api.py -v`

Expected: FAIL because the package does not export its public surface.

- [ ] **Step 3: Export and document**

Set explicit `__all__` in `jev_bot/__init__.py`. Replace the empty README with: required `JEV_API_TOKEN`, optional `JEV_ENDPOINT`, `uv run python main.py`, the six available framework keys, and the fact that the output includes choice plus probabilities. Do not place a credential example in the README.

- [ ] **Step 4: Run focused and full verification**

Run: `uv run pytest tests/test_public_api.py -v && uv run pytest -q`

Expected: every focused and existing test passes; none requires a live token or network.

- [ ] **Step 5: Commit the package surface and documentation**

```bash
git add jev_bot/__init__.py README.md tests/test_public_api.py
git commit -m "docs: document JEV conversational bot"
```

## Acceptance

- `main.py` contains no direct HTTP request or credential; it is only the CLI boundary.
- `JEV_API_TOKEN` is required and is never logged, returned, stored in the repository, or accepted through chat input.
- Every request contains the exact fixed `questions.framework` choice question and uses bounded conversation history as `state`.
- The client returns `answers.framework.choice` and its full `probabilities` map, or raises a typed safe error.
- Tests verify observable configuration, payload, parsing, failure, state-boundary, and terminal behavior with no external network request.
