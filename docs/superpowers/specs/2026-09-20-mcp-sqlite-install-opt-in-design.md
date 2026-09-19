# MCP SQLite Install Opt-In Design

## Purpose

Extend `jev install` so installation explicitly asks whether successful `jev_decide` requests and shaped responses should be recorded in SQLite. The benchmark-oriented default is audit-first: pressing Enter enables recording. The same preference must be controllable non-interactively and must flow as a `db_enable: bool = True` argument through the installer and MCP-registration APIs.

The existing MCP server persistence implementation remains authoritative: `jev-mcp --sqlite-db ABSOLUTE_PATH` creates the `investigations` table and records one row after each successful invocation. Failed validation, API, response-shaping, and storage operations remain unrecorded.

## Scope

Change:

- `jev_bot/cli.py` — install prompt and explicit enable/disable flags;
- `jev_bot/installer.py` — `db_enable=True` propagation, database-path resolution, project `.gitignore` handling, and user data-directory preparation;
- `jev_bot/mcp_registration.py` — dynamic canonical entries, managed-variant classification, enable/disable migration, and all four harness formats;
- installer, CLI, MCP-registration, and lifecycle tests;
- README installation and investigation-logging documentation.

Do not change:

- SQLite schema;
- `Recorder` write semantics;
- `jev_decide` request/response models;
- credentials or endpoint configuration;
- database query UI, retention, encryption, or redaction behavior.

## User Experience

### Interactive install

When neither database flag is supplied, interactive `jev install` asks after credential readiness and before installer mutation:

```text
Record successful JEV requests and responses in SQLite? [Y/n]
```

Precede or accompany the prompt with a concise warning:

```text
SQLite recording stores request state, questions, and shaped responses verbatim.
```

Pressing Enter selects `True`. Explicit `n` selects `False`.

### Explicit flags

Expose one paired Typer option:

```text
--db-enable / --no-db-enable
```

The CLI parameter is tri-state (`bool | None`) so it can distinguish an explicit choice from an omitted flag:

- `True` — enable without prompting;
- `False` — disable without prompting;
- `None` in an interactive terminal — prompt, defaulting to `True`;
- `None` in a non-interactive terminal — use `True` without prompting.

The audit-first non-interactive default is intentional for this benchmark workflow. Automation that must avoid local request/response storage uses `--no-db-enable`.

The prompt must not appear when either explicit flag is supplied. Credential failure still aborts before the logging prompt or any installation mutation.

## API Contract

Add `db_enable: bool = True` to the installer APIs that own scope/path resolution:

```python
install(..., db_enable: bool = True) -> Path
install_with_report(..., db_enable: bool = True) -> tuple[Path, RegistrationResult]
install_server(..., db_enable: bool = True, sqlite_db_path: Path | None = None) -> RegistrationResult
canonical_entry(..., db_enable: bool = False, sqlite_db_path: Path | None = None) -> dict
```

`install()` forwards the value unchanged to `install_with_report()`, which resolves/prepares the database destination and forwards it to `install_server()`.

`install_server()` can be called directly with its existing project/user scope arguments. When `db_enable=True` and `sqlite_db_path=None`, it resolves the approved project or user-scope path itself. An explicit `sqlite_db_path` must be absolute and overrides only that resolution step. This keeps existing bare `install_server(...)` calls usable under the new audit-first default.

`canonical_entry()` is a pure low-level transformation and remains backward-compatible by defaulting `db_enable=False`. When disabled, it returns the existing launcher unchanged. When enabled, it requires an absolute `sqlite_db_path`; a missing or relative path raises `ValueError`. It appends:

```text
--sqlite-db ABSOLUTE_PATH
```

It never reads environment variables or touches the filesystem.

## Database Path Resolution

### Project scope

For `project_root`, use:

```text
<resolved-project-root>/SQLITE_DB
```

The path passed to MCP configuration must be absolute.

The installer idempotently ensures a standalone `SQLITE_DB` ignore rule in `<project_root>/.gitignore` when recording is enabled:

- create `.gitignore` when absent;
- append exactly one `SQLITE_DB` line when not already covered by an exact active rule;
- do not duplicate the rule;
- preserve all existing bytes and line endings except for the required separating newline;
- reject a symlinked `.gitignore` or symlinked ancestry before mutation.

Disabling recording does not remove an existing ignore rule or delete an existing database.

### User scope

For `user_home`, resolve:

```text
$XDG_DATA_HOME/jev-poc/SQLITE_DB
```

when `XDG_DATA_HOME` is set to an absolute path. Otherwise use:

```text
<resolved-user-home>/.local/share/jev-poc/SQLITE_DB
```

Create the `jev-poc` parent directory before registration with permissions no broader than `0700`. Reject relative `XDG_DATA_HOME`, symlinked targets, and non-directory conflicts.

### Disabled mode

When `db_enable=False`, no database directory or `.gitignore` mutation occurs and generated MCP launcher arguments omit both SQLite arguments.

## MCP Registration

### Harness formats

For Claude Code, Oh My Pi, and Pi, append the pair to the canonical `args` list.

For OpenCode, append the pair to its array-form `command` list.

All other transport fields remain unchanged.

### Managed variants

Recognize these as JEV-owned registrations independently of the currently desired preference:

1. the exact base launcher without SQLite arguments;
2. the exact base launcher followed only by `--sqlite-db` and one absolute path.

Add a pure managed-entry parser/helper that returns one of:

- unmanaged/foreign;
- managed-disabled;
- managed-enabled plus its absolute SQLite path.

`classify_server_entry()` uses that helper and returns `CANONICAL` for either managed variant. A registration with other extra arguments, reordered launcher tokens, a relative SQLite path, or unrelated fields remains `FOREIGN`.

`install_server()` separately builds the desired canonical entry and compares it with the existing managed entry:

- exact desired entry, including enabled path — no-op with `EXISTS`;
- alternate managed mode or managed path change — atomically write the desired entry without requiring `--force`, returning `REPLACED`;
- foreign entry — retain existing behavior: fail unless `--force`, then replace only the JEV entry;
- absent entry — create desired entry.

`uninstall_server()` removes either `CANONICAL` managed variant without needing the desired `db_enable` value. Foreign entries remain protected.

## Preflight and Mutation Order

The installer must retain the current no-partial-state intent:

1. validate harness/scope;
2. read packaged skill bytes;
3. preflight skill target;
4. resolve the SQLite path when enabled;
5. preflight user data directory or project `.gitignore` target and symlink ancestry;
6. preflight/classify the MCP config against the desired dynamic entry;
7. perform atomic MCP config write when needed;
8. install the skill;
9. apply the prepared `.gitignore` update or ensure the user data directory.

Any operation whose failure can be known before mutation must be checked during preflight. Atomic writers must be used for MCP JSON and `.gitignore`. Existing files and directories are never deleted when the preference changes.

If the repository's current installer architecture cannot guarantee rollback across all three destinations, the implementation must preserve the existing guarantees and ensure the new database-specific operations are preflighted before the first mutation; it must not claim stronger cross-file atomicity than it provides.

## Security and Privacy

- The prompt must state that request state, questions, and shaped responses are stored verbatim.
- API tokens and Authorization headers never enter the recorded request model and must not be added by this change.
- Database paths in generated configuration are absolute and may be visible to users with access to the harness config.
- Project-local `SQLITE_DB` is ignored to reduce accidental commits.
- User-scope data directories are private to the user where the platform permits.
- Existing database files are retained when recording is disabled or the MCP registration is uninstalled.

## Output and Documentation

On successful install, print the MCP config path as today. Also print one recording line:

Enabled:

```text
SQLite recording: enabled (<absolute-path>)
```

Disabled:

```text
SQLite recording: disabled
```

Update README examples for interactive install, `--db-enable`, `--no-db-enable`, project/user database locations, and the requirement to reload or restart an already-running harness after changing MCP argv.

## Testing

### CLI tests

- omitted flag in interactive mode prompts with default `True`;
- Enter enables recording;
- `n` disables recording;
- explicit enable/disable flags skip the prompt;
- omitted flag in non-interactive mode enables recording;
- credential failure occurs before the logging prompt;
- output prints enabled path or disabled state;
- update the existing `test_install_output_two_lines` contract to expect and assert the third SQLite-recording status line.

### Installer tests

- `db_enable=True` propagates through `install()` and `install_with_report()`;
- project path resolves to `<project_root>/SQLITE_DB`;
- user path honors absolute `XDG_DATA_HOME` and falls back to `user_home/.local/share/jev-poc/SQLITE_DB`;
- relative XDG paths and symlinked targets fail before mutation;
- project `.gitignore` creation/append/idempotence/newline preservation;
- disabled mode leaves `.gitignore` and user data directories untouched.
- update existing installer assertions that compare default installs with bare `canonical_entry(harness)`: tests for the legacy disabled shape must pass `db_enable=False`, while audit-first default tests must compare against `canonical_entry(harness, db_enable=True, sqlite_db_path=<resolved-path>)`;
- update canonical no-op tests so an exact enabled entry remains `EXISTS`, and a pre-existing disabled managed entry under the enabled default migrates to `REPLACED`.

### MCP registration tests

For all four harnesses:

- enabled canonical entry contains the exact SQLite suffix in the correct list;
- disabled entry remains byte-for-byte equivalent to the prior canonical entry;
- exact desired entry is `EXISTS`;
- managed enable→disable, disable→enable, and path changes update without force;
- foreign extra arguments remain protected;
- uninstall removes enabled and disabled managed variants;
- generated paths are absolute.
- update existing lifecycle assertions that assumed the disabled base entry on default install to either opt out explicitly or assert the enabled desired entry and its resolved path.

### Server tests

Existing Recorder tests remain authoritative. Add no duplicate server-storage tests unless a server contract changes.

### End-to-end smoke test

Install Oh My Pi into a temporary project with recording enabled and inspect the generated `.omp/mcp.json`. To exercise the working tree under review, start the local entry point (`python -m jev_mcp.server --sqlite-db <generated-path>`) rather than executing the generated `uvx --from git+...` launcher, which targets published remote HEAD. With a temporary credential environment, execute one successful `jev_decide` and assert one `investigations` row contains the validated question and shaped response. Repeat installation with `--no-db-enable` and assert the generated launcher omits SQLite arguments. A separate post-publication smoke test may execute the generated launcher verbatim.

## Acceptance Criteria

- Interactive install asks for recording preference and defaults to enabled.
- `db_enable=True` is the default across scope-aware installer APIs; the pure `canonical_entry()` builder remains disabled by default unless given an explicit absolute path.
- Explicit CLI flags deterministically override the prompt/default.
- Project and user-scope paths match the approved rules.
- All four harness configs receive correct argv shapes.
- Existing managed registrations migrate between modes without `--force`; foreign entries remain protected.
- Successful JEV calls are recorded only when enabled.
- Project-local databases are ignored, no secrets are persisted, and disabling never deletes historical data.
- Full existing test suite plus new focused tests pass.
