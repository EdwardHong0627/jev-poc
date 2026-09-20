# MCP SQLite Install Opt-In Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make JEV installation audit-first by asking whether to record successful MCP requests/responses, propagating `db_enable=True`, and generating safe SQLite-enabled MCP registrations for all harnesses.

**Architecture:** The CLI owns interaction and resolves omitted flags. The installer owns scope-aware database paths and project/user filesystem preparation. MCP registration remains pure for canonical-entry construction and recognizes both enabled and disabled JEV-owned variants; the MCP server Recorder remains unchanged.

**Tech Stack:** Python 3.12, Typer, pathlib, JSON MCP configs, stdlib SQLite, pytest, MCP SDK.

---

## Chunk 1: Dynamic MCP Registration

### Task 1: Add SQLite-aware canonical registration

**Files:**
- Create: `jev_bot/investigation_logging.py`
- Modify: `jev_bot/mcp_registration.py`
- Create: `tests/test_investigation_logging.py`
- Modify: `tests/test_mcp_registration.py`
- Modify: `tests/test_mcp_lifecycle.py`

- [ ] **Step 1: Add failing canonical-entry tests**

Cover all four harnesses:

```python
base = canonical_entry(harness)
enabled = canonical_entry(
    harness,
    db_enable=True,
    sqlite_db_path=Path("/tmp/jev/SQLITE_DB"),
)
```

Assert base is unchanged, enabled appends `--sqlite-db` and the absolute path to `args` or OpenCode's command array, and enabled mode rejects missing/relative paths. In `tests/test_investigation_logging.py`, add failing project/user/XDG path-resolution tests so the resolver exists before `install_server()` adopts its audit-first default.

- [ ] **Step 2: Run canonical tests and observe failure**

```bash
uv run --locked --extra dev python -m pytest tests/test_investigation_logging.py tests/test_mcp_registration.py -q
```

Expected: failures for unsupported keyword arguments and missing SQLite suffix.

- [ ] **Step 3: Implement pure path resolution and canonical-entry augmentation**

Create `jev_bot/investigation_logging.py` with a pure `resolve_sqlite_db_path(project_root, user_home, environ)` helper. It returns an absolute project `SQLITE_DB` path or absolute XDG/user fallback and rejects relative XDG paths. Both `mcp_registration.py` and `installer.py` import this module; it imports neither caller, preventing a cycle.

Add `db_enable=False` and `sqlite_db_path=None` to `canonical_entry()`. Deep-copy the base entry; append the known suffix to the correct launcher list. Validate absolute paths before mutation.

- [ ] **Step 4: Add failing managed-variant and compatibility lifecycle tests**

Test exact enabled entries as `EXISTS`, disabled↔enabled/path migrations as `REPLACED` without force, foreign extra args as protected, and uninstall of either managed variant. Update every existing bare `install_server(...)` assertion that expects the disabled base shape to pass `db_enable=False`; update audit-first default cases to compare with an enabled canonical entry at the resolved path. Cover existing absent, preserve-content, canonical-no-op, force-replace, and user-scope cases.

- [ ] **Step 5: Run lifecycle tests and observe failure**

```bash
uv run --locked --extra dev python -m pytest tests/test_mcp_lifecycle.py -q
```

Expected: enabled entries classify foreign or require force.

- [ ] **Step 6: Implement managed-entry parsing and migration**

Add a pure helper recognizing only the exact base launcher or exact base plus `--sqlite-db ABSOLUTE_PATH`. Make `classify_server_entry()` return `CANONICAL` for both. Make `install_server()` build the desired entry, compare exact values for `EXISTS`, and write alternate managed variants as `REPLACED`. Make uninstall remove either managed variant.

Add `db_enable=True` and optional explicit path to `install_server()`. When enabled with no explicit path, resolve project/user defaults through `jev_bot.investigation_logging.resolve_sqlite_db_path()`.

- [ ] **Step 7: Run focused registration tests**

```bash
uv run --locked --extra dev python -m pytest \
  tests/test_investigation_logging.py tests/test_mcp_registration.py tests/test_mcp_lifecycle.py -q
```

Expected: pass.

- [ ] **Step 8: Commit registration support**

```bash
git add jev_bot/investigation_logging.py jev_bot/mcp_registration.py tests/test_investigation_logging.py tests/test_mcp_registration.py tests/test_mcp_lifecycle.py
git commit -m "feat: generate SQLite-enabled MCP registrations"
```

## Chunk 2: Installer Paths and Preference Propagation

### Task 2: Add `db_enable=True` to installer APIs

**Files:**
- Modify: `jev_bot/investigation_logging.py`
- Modify: `jev_bot/installer.py`
- Modify: `tests/test_investigation_logging.py`
- Modify: `tests/test_installer.py`

- [ ] **Step 1: Write failing propagation/path tests**

Test:

- `install()` and `install_with_report()` default to enabled;
- project path is resolved absolute `<project_root>/SQLITE_DB`;
- user path uses absolute `XDG_DATA_HOME/jev-poc/SQLITE_DB` or `user_home/.local/share/jev-poc/SQLITE_DB`;
- relative XDG data home fails;
- disabled mode creates no database directory or ignore rule;
- project `.gitignore` creation, append, idempotence, newline preservation, and symlink rejection.

Update existing disabled-shape assertions to pass `db_enable=False`; update audit-first assertions to compare against enabled canonical entries.

- [ ] **Step 2: Run installer tests and observe failure**

```bash
uv run --locked --extra dev python -m pytest tests/test_installer.py -q
```

- [ ] **Step 3: Implement path resolution and preflight helpers**

Add focused private helpers for project/user database paths, private user data-directory preparation, and atomic `.gitignore` updates. Reuse existing symlink-ancestry guards and atomic file patterns rather than adding a second safety convention.

- [ ] **Step 4: Propagate installer preference**

Add `db_enable: bool = True` to both installer APIs. Resolve/preflight the destination only when enabled, pass the absolute path to `install_server()`, and apply prepared filesystem changes without deleting existing DBs or ignore rules on disable.

- [ ] **Step 5: Run installer and registration tests**

```bash
uv run --locked --extra dev python -m pytest \
  tests/test_installer.py tests/test_mcp_registration.py tests/test_mcp_lifecycle.py -q
```

- [ ] **Step 6: Commit installer propagation**

```bash
git add jev_bot/investigation_logging.py jev_bot/installer.py tests/test_investigation_logging.py tests/test_installer.py
git commit -m "feat: propagate SQLite recording preference during install"
```

## Chunk 3: CLI Prompt and Documentation

### Task 3: Add audit-first install UX

**Files:**
- Modify: `jev_bot/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing CLI tests**

Cover interactive Enter=yes, explicit `n`, paired flags skipping prompt, non-interactive omitted=true, credential failure before logging prompt, third output line, and enabled/disabled status text.

- [ ] **Step 2: Run CLI tests and observe failure**

```bash
uv run --locked --extra dev python -m pytest tests/test_cli.py -q
```

- [ ] **Step 3: Implement tri-state CLI resolution**

Add `--db-enable/--no-db-enable` as `bool | None`. When omitted, prompt only in interactive mode with default `True`; use `True` directly in non-interactive mode. Display the verbatim-data warning before the prompt. Run credential readiness first. Pass the resolved boolean to `install_with_report()`.

- [ ] **Step 4: Print recording state**

After install, print enabled absolute path or disabled state as the third status line. Use the same path resolver as the installer so display and generated config cannot diverge.

- [ ] **Step 5: Update README**

Document prompt/default, paired flags, project/user locations, successful-only logging, privacy implications, and MCP reload/restart requirement.

- [ ] **Step 6: Run CLI tests**

```bash
uv run --locked --extra dev python -m pytest tests/test_cli.py -q
```

- [ ] **Step 7: Commit CLI UX**

```bash
git add jev_bot/cli.py tests/test_cli.py README.md
git commit -m "feat: ask for SQLite recording during MCP install"
```

## Chunk 4: End-to-End Verification

### Task 4: Verify generated configs and real recording

**Files:**
- Verify all changed source/tests/docs
- Do not commit temporary projects, databases, or scripts

- [ ] **Step 1: Run the full suite**

```bash
uv run --locked --extra dev python -m pytest
```

Expected: all tests pass.

- [ ] **Step 2: Exercise project-scope installation**

Use Typer's CLI or a temporary subprocess to install Oh My Pi into a temporary project with default recording. Assert:

- prompt defaults to yes;
- `.omp/mcp.json` contains the absolute `<temp-project>/SQLITE_DB` suffix;
- `.gitignore` contains one `SQLITE_DB` rule;
- disabled reinstall removes the suffix without deleting ignore rule or DB.

- [ ] **Step 3: Exercise user-scope installation**

Set a temporary absolute `XDG_DATA_HOME`; install with user scope; assert the generated MCP config uses `<xdg>/jev-poc/SQLITE_DB` and the parent directory mode is no broader than `0700`.

- [ ] **Step 4: Run one local MCP recording smoke**

Start `python -m jev_mcp.server --sqlite-db <generated-project-path>` through the MCP SDK using the working tree and a temporary credential environment. Call `jev_decide` once and assert one investigation row contains the expected question key/instructions and shaped response. Remove temporary data afterward.

- [ ] **Step 5: Independent specification review**

Have a fresh reviewer compare code/tests/docs against the approved spec. Fix every missing behavior and rerun affected tests until approved.

- [ ] **Step 6: Independent quality/security review**

Review config classification, path/symlink handling, prompt behavior, file permissions, secret handling, and test quality. Fix and rerun until approved.
