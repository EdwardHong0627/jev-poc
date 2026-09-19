# JEV Installer CLI Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a secure Typer `jev` CLI that installs the packaged JEV skill for four supported harnesses and manages user-level JEV configuration.

**Architecture:** `installer.py` owns target mapping and non-destructive filesystem operations. `config_store.py` owns XDG JSON persistence and permissions; `config.py` reads it only after environment and local dotenv sources. `cli.py` is a thin Typer adapter, backed by package resources rather than checkout-relative files.

**Tech Stack:** Python 3.12, Typer, stdlib `importlib.resources`/`json`/`os`, pytest.

---

## Chunk 1: Distributable skill installer

### Task 1: Package the canonical skill and installer domain

**Files:**
- Create: `jev_bot/assets/using-jev-decisions/SKILL.md`
- Create: `jev_bot/installer.py`
- Create: `tests/test_installer.py`
- Modify: `pyproject.toml`
- Test: `tests/test_installer.py`

- [ ] **Step 1: Write failing asset/install tests**

Cover byte-identical package and `.agents` skill content; target resolution for every `(harness, scope)` pair; idempotent install; foreign-content rejection; forced replacement; absent-file uninstall no-op; owned-file uninstall; preservation of unrelated sibling files; destination symlink refusal; and pruning empty parents without deleting the harness root.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `uv run python -m pytest tests/test_installer.py -v`
Expected: FAIL because `jev_bot.installer` and package asset do not exist.

- [ ] **Step 3: Add canonical asset and minimal installer**

Copy the approved skill to the packaged canonical path. Implement immutable harness definitions, `resolve_destination(harness, project_root | user_home)`, `install_skill`, and `uninstall_skill`. Use `importlib.resources.files` to read the asset. Reject invalid harnesses, invalid/missing project root, destination symlinks, and foreign content absent `force`. On uninstall, unlink only matching `SKILL.md`, remove only empty directories, and stop at harness root.

- [ ] **Step 4: Configure wheel package data**

Add Typer runtime dependency, a `jev = "jev_bot.cli:app"` console entry point, and `[tool.setuptools.package-data]` including `assets/**/*.md`.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `uv run python -m pytest tests/test_installer.py -v`
Expected: PASS.

## Chunk 2: Secure persistent configuration

### Task 2: Add user config storage and precedence

**Files:**
- Create: `jev_bot/config_store.py`
- Create: `tests/test_config_store.py`
- Modify: `jev_bot/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write failing storage and precedence tests**

Cover XDG path fallback, atomic write/read, only `token`/`endpoint` accepted, `0700` config directory and `0600` config file (including pre-existing permissive paths), empty-store file removal, malformed JSON rejection without content echo, endpoint validation, and nonblank environment/dotenv precedence over store. Confirm blank env falls through to stored value.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `uv run python -m pytest tests/test_config_store.py tests/test_config.py -v`
Expected: FAIL because the storage module and load precedence do not exist.

- [ ] **Step 3: Implement minimal secure store**

Use `${XDG_CONFIG_HOME:-~/.config}/jev-poc/config.json`. Create/chmod the directory to `0700`; write JSON through a same-directory temporary file, chmod to `0600`, and atomically replace. Validate keys and values before persistence. Surface safe errors without embedding content or token.

- [ ] **Step 4: Extend configuration loading**

Keep `load_dotenv(..., override=False)`. Resolve nonblank `JEV_API_TOKEN` and `JEV_ENDPOINT` from environment/dotenv first, then storage, then `DEFAULT_ENDPOINT` for endpoint. Preserve existing validation and redacted `Config` repr.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `uv run python -m pytest tests/test_config_store.py tests/test_config.py -v`
Expected: PASS.

## Chunk 3: Typer command surface

### Task 3: Add install, uninstall, and config commands

**Files:**
- Create: `jev_bot/cli.py`
- Create: `tests/test_cli.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing CLI tests**

Use `typer.testing.CliRunner` and isolated project/home/XDG paths. Assert `install` and `uninstall` require exactly one scope; every harness routes to the correct domain destination; overwrite failures are nonzero; `--force` works; `config set token --stdin` reads a nonblank token without echoing it and rejects blank stdin; endpoint set/list/unset behavior; list redacts token; invalid input is nonzero.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `uv run python -m pytest tests/test_cli.py -v`
Expected: FAIL because the Typer app does not exist.

- [ ] **Step 3: Implement minimal Typer app**

Create `app = typer.Typer(...)`; add top-level `install`/`uninstall` commands and a `config` sub-app. Convert domain/config errors to `typer.BadParameter` or `typer.Exit(1)` with safe messages. `config set token` accepts only `--stdin` and reads one stripped line. Do not make network calls.

- [ ] **Step 4: Document usage**

Add install/uninstall examples, each target name, explicit scope requirement, stdin token example, config precedence, and token-redaction guarantee to `README.md`.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `uv run python -m pytest tests/test_cli.py -v`
Expected: PASS.

## Chunk 4: End-to-end verification

### Task 4: Exercise the packaged command

**Files:**
- Modify: no production files expected

- [ ] **Step 1: Run relevant suites**

Run: `uv run python -m pytest tests/test_installer.py tests/test_config_store.py tests/test_config.py tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 2: Smoke test command surfaces in a temporary directory**

Run `uv run jev --help`, install then uninstall each target into isolated temporary project/user paths, and pipe a test token to `uv run jev config set token --stdin` with isolated `XDG_CONFIG_HOME`. Confirm `config list` reports token configured without printing it.

- [ ] **Step 3: Run the full suite**

Run: `uv run python -m pytest -v`
Expected: PASS.
