# Harness MCP Registration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing `jev install` and `jev uninstall` commands install and remove the JEV skill plus a narrowly-owned portable MCP registration for Claude Code, OpenCode, Oh My Pi, and Pi.

**Architecture:** Keep harness-specific paths and JSON nesting declarative in a new pure registration module. The installer remains the lifecycle coordinator: it validates explicit scope, preflights the skill and config changes, calls pure registration operations, and preserves the existing path return. Each registration starts a package-installed `jev-mcp` console command through `uvx`, never embedding credentials or checkout-specific paths.

**Tech Stack:** Python 3.12, dataclasses, `json`, `tempfile`, `os.replace`, Typer, pytest, setuptools console scripts, uv/uvx.

---

## File structure

| File | Responsibility |
| --- | --- |
| `jev_bot/mcp_registration.py` | Declarative harness registry, canonical entries, strict JSON preflight, atomic merge/removal, ownership outcomes. No Typer or environment/token handling. |
| `jev_bot/installer.py` | Existing skill lifecycle plus ordered calls to MCP registration; explicit-scope validation remains centralized here. |
| `jev_bot/cli.py` | Updated install/uninstall help and output; maps typed registration conflicts to user-facing errors. |
| `jev_mcp/server.py` | Existing `main()` remains the package console target; no transport behavior changes. |
| `pyproject.toml` | Exposes `jev-mcp = "jev_mcp.server:main"`. |
| `tests/test_mcp_registration.py` | Behavior coverage for every registry row, safe JSON operations, ownership, and refusal boundaries. |
| `tests/test_installer.py` | End-to-end domain integration of skill and MCP registration. |
| `tests/test_cli.py` | CLI surface/output and conflict behavior. |
| `README.md` | Documents that install/uninstall manage MCP registration, launcher distribution, environment requirements, and Pi extension prerequisite. |

## Canonical registration contract

All entries use this launcher without `cwd`, token, endpoint, or absolute executable path:

```python
MCP_LAUNCHER_COMMAND = "uvx"
MCP_LAUNCHER_ARGS = (
    "--from",
    "git+https://github.com/EdwardHong0627/jev-poc.git",
    "jev-mcp",
)
```

| Harness | Project path | User path | JSON server path | Canonical entry |
| --- | --- | --- | --- | --- |
| `claude-code` | `.mcp.json` | `.claude.json` | `mcpServers.jev` | `{ "type": "stdio", "command": "uvx", "args": [...] }` |
| `opencode` | `opencode.json` | `.config/opencode/opencode.json` | `mcp.servers.jev` | `{ "type": "local", "command": ["uvx", ...] }` |
| `oh-my-pi` | `.omp/mcp.json` | `.omp/agent/mcp.json` | `mcpServers.jev` | `{ "type": "stdio", "command": "uvx", "args": [...] }` |
| `pi` | `.pi/mcp.json` | `.pi/agent/mcp.json` | `mcpServers.jev` | `{ "transport": "stdio", "command": "uvx", "args": [...], "lifecycle": "lazy" }` |

`pi` requires `pi install npm:pi-mcp-extension`; the JEV installer does not install that third-party extension.

## Chunk 1: Pure registration domain

### Task 1: Define registry and canonical entries

**Files:**
- Create: `jev_bot/mcp_registration.py`
- Test: `tests/test_mcp_registration.py`

- [ ] **Step 1: Write failing registry tests**

```python
@pytest.mark.parametrize(
    ("harness", "project_suffix", "user_suffix", "server_path"),
    [
        ("claude-code", ".mcp.json", ".claude.json", ("mcpServers", "jev")),
        ("opencode", "opencode.json", ".config/opencode/opencode.json", ("mcp", "servers", "jev")),
        ("oh-my-pi", ".omp/mcp.json", ".omp/agent/mcp.json", ("mcpServers", "jev")),
        ("pi", ".pi/mcp.json", ".pi/agent/mcp.json", ("mcpServers", "jev")),
    ],
)
def test_registration_target_uses_native_scope(...):
    target = registration_target(harness, project_root=project)
    assert target.path == project / project_suffix
    assert target.server_path == server_path
```

Also assert every canonical entry invokes `uvx --from git+https://github.com/EdwardHong0627/jev-poc.git jev-mcp`, has no token-like key/value, and matches its harness schema.

- [ ] **Step 2: Run the registry tests and observe failure**

Run: `uv run python -m pytest tests/test_mcp_registration.py -q`

Expected: FAIL because `jev_bot.mcp_registration` does not exist.

- [ ] **Step 3: Implement minimal declarative registry**

Create frozen `RegistrationTarget`/`HarnessRegistration` dataclasses, constants for launcher command/args, `VALID_MCP_HARNESSES`, `registration_target()`, and `canonical_entry()`. Validate exactly one scope and unknown harness consistently with `installer.py`.

- [ ] **Step 4: Run focused registry tests**

Run: `uv run python -m pytest tests/test_mcp_registration.py -q`

Expected: PASS.

### Task 2: Add safe JSON preflight and atomic mutation

**Files:**
- Modify: `jev_bot/mcp_registration.py`
- Modify: `tests/test_mcp_registration.py`

- [ ] **Step 1: Write failing safety tests**

Cover missing config creation, unrelated top-level/server preservation, non-object JSON refusal, malformed JSON refusal, symlinked config refusal, and a same-directory replacement write. Assert preserved JSON values, not whitespace or implementation details.

- [ ] **Step 2: Run the safety tests and observe failure**

Run: `uv run python -m pytest tests/test_mcp_registration.py -q`

Expected: FAIL because configuration preflight/mutation is absent.

- [ ] **Step 3: Implement strict JSON helpers**

Implement:

```python
def read_config(path: Path) -> dict[str, Any]: ...
def write_config_atomic(path: Path, value: dict[str, Any]) -> None: ...
def ensure_symlink_free_path(path: Path, stop_root: Path) -> None: ...
```

`read_config` returns `{}` only for a missing file; it raises `ValueError` for malformed or non-object JSON. Every registration preflight refusal—including an existing symlink on the target ancestry—raises `ValueError` so the existing CLI error path reports a clean error. `write_config_atomic` first creates `path.parent`, writes a UTF-8 temporary file in that directory, flushes and `os.fsync`s it, then calls `os.replace`; it must not delete an existing file before replacement. Check every existing component from the target toward the selected explicit root for symlinks.

- [ ] **Step 4: Run focused safety tests**

Run: `uv run python -m pytest tests/test_mcp_registration.py -q`

Expected: PASS.

### Task 3: Add ownership-safe registration lifecycle

**Files:**
- Modify: `jev_bot/mcp_registration.py`
- Modify: `tests/test_mcp_registration.py`

- [ ] **Step 1: Write failing lifecycle tests**

Cover:
- classification of absent, structurally canonical, and foreign `jev` entries without mutation;
- absent entry becomes canonical;
- identical entry is a no-op;
- foreign entry raises without `force` and remains unchanged;
- `force=True` replaces only `jev`;
- removal deletes only a structurally equal canonical entry;
- removal retains a foreign/altered `jev` entry and reports `FOREIGN`;
- removal retains otherwise empty configuration files.

- [ ] **Step 2: Run lifecycle tests and observe failure**

Run: `uv run python -m pytest tests/test_mcp_registration.py -q`

Expected: FAIL because no lifecycle API exists.

- [ ] **Step 3: Implement narrow lifecycle API**

Implement an explicit outcome enum/dataclass, for example:

```python
class RegistrationStatus(Enum):
    CREATED = auto()
    EXISTS = auto()
    REPLACED = auto()
    REMOVED = auto()
    ABSENT = auto()
    FOREIGN = auto()

@dataclass(frozen=True)
class RegistrationResult:
    path: Path
    status: RegistrationStatus
```

Implement `classify_registration(target, config) -> RegistrationStatus` as a pure operation returning `ABSENT`, `EXISTS`, or `FOREIGN` before any write. `install_registration(..., force=False)` consumes a pre-classified safe target and returns `CREATED`/`EXISTS`/`REPLACED`; it raises `ValueError` for a foreign entry only before the installer writes its skill. `uninstall_registration(...)` returns `REMOVED`/`ABSENT`/`FOREIGN`, without deleting foreign state. Preserve only the exact server nesting required by the selected harness.

- [ ] **Step 4: Run focused lifecycle tests**

Run: `uv run python -m pytest tests/test_mcp_registration.py -q`

Expected: PASS.

## Chunk 2: Installer, CLI, and package integration

### Task 4: Coordinate skill and MCP registration in installer domain

**Files:**
- Modify: `jev_bot/installer.py`
- Modify: `tests/test_installer.py`

- [ ] **Step 1: Write failing installer integration tests**

For each harness and both explicit scopes, assert `install()` writes the native skill and the canonical MCP entry. Assert a pre-existing foreign MCP entry makes normal install fail without changing it or creating a new skill. Assert `force` replaces only that entry. Assert `uninstall()` removes the owned skill and owned registration while retaining unrelated config.

- [ ] **Step 2: Run installer integration tests and observe failure**

Run: `uv run python -m pytest tests/test_installer.py -q`

Expected: FAIL because existing installer manages only `SKILL.md`.

- [ ] **Step 3: Implement ordered domain integration**

Preflight the skill target plus the complete MCP configuration and classify its `jev` entry before any write. A foreign registration without `force` must raise before a skill directory is created. After preflight, use current skill installation/removal helpers and non-raising registration write operations. Keep `install()`/`uninstall()` return values as the historical skill `Path`; add `install_with_report(...) -> tuple[Path, RegistrationResult]` and `uninstall_with_report(...) -> tuple[Path, RegistrationResult]`, then make the historical functions delegate to them and discard the report. Do not add retries, credentials, or global-home fallbacks.

- [ ] **Step 4: Run installer tests**

Run: `uv run python -m pytest tests/test_installer.py -q`

Expected: PASS.

### Task 5: Update CLI and expose portable MCP console command

**Files:**
- Modify: `pyproject.toml`
- Modify: `jev_bot/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing packaging/CLI tests**

Assert package metadata declares `jev-mcp = "jev_mcp.server:main"`. Assert CLI help describes skill-and-MCP behavior, successful install output includes both target paths, successful uninstall output indicates a retained foreign registration, and foreign install returns a nonzero exit with a precise error. Exercise `uninstall_with_report()` indirectly through CLI so the warning is based on the original `RegistrationResult`, not a second deletion attempt.

- [ ] **Step 2: Run CLI tests and observe failure**

Run: `uv run python -m pytest tests/test_cli.py -q`

Expected: FAIL because no package MCP entry and CLI has skill-only wording/output.

- [ ] **Step 3: Implement minimal command-surface changes**

Add the script entry. Have CLI call the report-returning installer helpers, display their original `RegistrationResult.path`, and report a `FOREIGN` uninstall status as a warning without changing unrelated exit semantics. Update `--force` help to state it replaces a foreign JEV registration as well as existing JEV skill content.

- [ ] **Step 4: Run CLI tests and non-blocking console-entry discovery**

Run:

```sh
uv run python -m pytest tests/test_cli.py -q
uv run python -c "import importlib.metadata as m; assert 'jev-mcp' in [entry.name for entry in m.entry_points(group='console_scripts')]"
```

Expected: tests pass and the installed package exposes `jev-mcp`; do not invoke the stdio server directly because it intentionally blocks waiting for an MCP client.

## Chunk 3: User documentation and end-to-end proof

### Task 6: Document install behavior and harness prerequisites

**Files:**
- Modify: `README.md`
- Test: `tests/test_cli.py` (existing behavioral CLI coverage only)

- [ ] **Step 1: Update README after tested implementation**

Replace skill-only wording with skill-plus-MCP registration. Document all accepted harness names, explicit scopes, the portable `uvx` launcher, credential inheritance, `/mcp reload` or equivalent harness refresh behavior, and Pi's `pi-mcp-extension` prerequisite. Do not document unreleased endpoints, tokens, or absolute paths.

- [ ] **Step 2: Review examples against generated canonical entries**

Use a small throwaway Python invocation of `canonical_entry()`/`registration_target()` to compare every documented path/shape to the implementation. Remove the throwaway script after use.

### Task 7: Run end-to-end verification

**Files:**
- Test: `tests/test_mcp_registration.py`
- Test: `tests/test_installer.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Run the feature-focused suites**

Run:

```sh
uv run python -m pytest tests/test_mcp_registration.py tests/test_installer.py tests/test_cli.py -q
```

Expected: PASS.

- [ ] **Step 2: Smoke-test a temporary OMP registration**

Create a temporary project directory, invoke:

```sh
uv run jev install oh-my-pi --project <temporary-project>
```

Parse `<temporary-project>/.omp/mcp.json`; assert it contains only the canonical `mcpServers.jev` registration and no token/endpoint. Invoke uninstall and assert the `jev` entry is removed while any seeded unrelated server remains.

- [ ] **Step 3: Run the full repository suite once**

Run: `uv run python -m pytest -q`

Expected: all tests pass.

- [ ] **Step 4: Commit the completed feature**

```sh
git add jev_bot/mcp_registration.py jev_bot/installer.py jev_bot/cli.py jev_mcp/server.py pyproject.toml tests/test_mcp_registration.py tests/test_installer.py tests/test_cli.py README.md
git commit -m "feat: register JEV MCP across harnesses"
```
