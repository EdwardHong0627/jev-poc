# MCP Install Credential UX Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prompt once for a hidden OpenRouter token during first-time interactive `jev install`, persist it securely with the default Decisions endpoint, and fail safely without prompting in non-interactive contexts.

**Architecture:** Add a small CLI-only credential readiness helper that uses the existing configuration loader precedence without changing pure installer/MCP-domain code. It prompts only after resolution fails, persists through `write_user_config`, then delegates to the existing report-aware install command. All credential readiness happens before any harness mutation.

**Tech Stack:** Python 3.12, Typer/Click prompt APIs, existing `jev_bot.config`, `jev_bot.config_store`, pytest `CliRunner`.

---

## Chunk 1: Credential readiness and CLI integration

### Task 1: Define failing install-credential behavior tests

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `jev_bot/cli.py`

- [ ] **Step 1: Write focused failing tests**

Cover observable behavior:

```python
def test_install_prompts_for_token_when_unresolved(...):
    result = runner.invoke(app, ["install", "oh-my-pi", "--project", str(project)], input="token\n")
    assert result.exit_code == 0
    stored = json.loads(config_path.read_text())
    assert stored == {
        "token": "token",
        "endpoint": "https://openrouter.ai/api/alpha/decisions",
    }
```

Also test: environment token skips prompt and does not create user config; valid stored config skips prompt; blank interactive input fails with neither skill nor MCP file; non-interactive unresolved install fails with guidance and neither file; persistence failure leaves neither harness file; command output never includes entered token.

- [ ] **Step 2: Run the new tests and observe failure**

Run: `uv run python -m pytest tests/test_cli.py -q`

Expected: FAIL because install currently proceeds without credential readiness or hidden prompting.

- [ ] **Step 3: Implement a CLI-only readiness helper**

Add a private helper in `jev_bot/cli.py`, for example:

```python
def _ensure_install_credentials() -> None:
    try:
        load_config()
        return
    except EnvironmentError:
        pass

    if not sys.stdin.isatty():
        raise ValueError(
            "OpenRouter token is required: set JEV_API_TOKEN or run "
            "`jev config set token --stdin` before installation."
        )

    token = typer.prompt("OpenRouter API token", hide_input=True).strip()
    if not token:
        raise ValueError("OpenRouter API token must be non-blank")
    write_user_config(
        get_config_path().parent,
        UserConfig(token=token, endpoint=DEFAULT_ENDPOINT),
    )
```

Use only existing config APIs. Preserve malformed-config errors rather than treating them as unresolved. Call the helper before `install_with_report`, so prompt rejection/persistence failure creates no harness state. Add a narrow helper for testable TTY detection if Typer’s runner cannot model it directly; do not add CLI flags.

- [ ] **Step 4: Run focused CLI tests**

Run: `uv run python -m pytest tests/test_cli.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```sh
git add jev_bot/cli.py tests/test_cli.py
git commit -m "feat: prompt for credentials during first MCP install"
```

## Chunk 2: Documentation and end-to-end proof

### Task 2: Document secure first-install behavior

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update installation documentation**

Document that interactive `jev install` asks once only when token resolution fails, stores token plus the default OpenRouter Decisions endpoint in secure user config, never writes credentials to harness config, and directs non-interactive users to `JEV_API_TOKEN` or `jev config set token --stdin`.

- [ ] **Step 2: Commit documentation**

```sh
git add README.md
git commit -m "docs: explain first-install credential prompt"
```

### Task 3: Verify end-to-end behavior

**Files:**
- Test: `tests/test_cli.py`

- [ ] **Step 1: Run focused suite**

Run: `uv run python -m pytest tests/test_cli.py -q`

Expected: PASS.

- [ ] **Step 2: Smoke-test interactive installation**

Use a temporary `XDG_CONFIG_HOME` and project root. Invoke `jev install oh-my-pi --project <project>` with a token supplied through hidden interactive input. Verify mode-`0600` user config contains the token/default endpoint and generated harness config contains no token or endpoint. Remove the temporary fixture afterward.

- [ ] **Step 3: Run full suite once**

Run: `uv run python -m pytest -q`

Expected: PASS.
