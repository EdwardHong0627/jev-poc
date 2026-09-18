# SQLite MCP Investigation Logging Design

## 1. Goal

Provide an optional SQLite-backed investigation log for the JEV MCP server. When explicitly enabled via the `--sqlite-db PATH` CLI flag, every **successful** `jev_decide` invocation is persisted as a single JSON row containing a UTC timestamp, the validated request, and the shaped response. The log serves as an append-only audit trail; there is no query UI, retention policy, or encryption.

**Non-goals:**
- No logging of failed, rejected, or timed-out invocations.
- No query interface, CLI subcommand, or REST endpoint for reading the log.
- No retention, pruning, vacuuming, or size limit enforcement.
- No encryption, access controls, or credential storage within the log file.
- No background flusher, WAL autovacuum, or checkpoint mechanism beyond explicit close.

## 2. Activation

### 2.1 CLI flag

The MCP server's `main()` entry point accepts an **optional** `--sqlite-db` flag:

```text
python -m jev_mcp.server --sqlite-db /path/to/investigations.db
```

- When **omitted** (default), the server operates identically to current behaviour: no logging, no database file, no `sqlite3` import.
- When **present**, the value is a file-system path resolved relative to the current working directory (absolute or relative). The path is validated at startup (see §4.2) and used for the lifetime of the process.

### 2.2 Dependency

`sqlite3` is a Python standard-library module — no new third-party runtime dependencies are introduced.

## 3. Activation path & startup

When `--sqlite-db` is supplied:

1. **Path validation.** Resolve the path (the exact string as provided — no home-directory tilde expansion is performed). Validate:
   - The path string is non-blank.
   - The parent directory exists and is a directory.
   - No symlink walk is performed on the parent; if the parent itself is a symlink the server continues (the responsibility of the caller to control).
   - On failure: print a redacted error to stderr and exit with status 1, *without* creating or touching any file.
2. **Database initialisation.** Open the database with `sqlite3.connect(path, check_same_thread=False)` and immediately issue:
   ```sql
   CREATE TABLE IF NOT EXISTS investigations (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       timestamp TEXT NOT NULL,
       request TEXT NOT NULL,
       response TEXT NOT NULL
   )
   ```
   The `IF NOT EXISTS` guard makes the server safe to start against a pre-existing database file created by a previous run (e.g. after a crash).
3. **Recorder creation.** Construct the `Recorder` component, passing the `sqlite3.Connection` object.
4. **Continue startup.** The rest of the server lifecycle proceeds identically to the non-logged mode.

Startup failure modes and their severity:

| Condition | Action |
|---|---|
| Parent directory does not exist | Print error to stderr, exit 1, no file created. |
| `CREATE TABLE` fails (e.g. `SQLITE_BUSY` when opening + writing) | Print redacted error to stderr, exit 1. |
| Any other `sqlite3` exception during setup | Print redacted error to stderr, exit 1. |

### 3.1 Shutdown

On process exit (normal or via `Ctrl-C`):

1. Close the `sqlite3.Connection` (which flushes and closes the file).
2. The existing `DecisionsClient.close()` lifecycle continues after the database close.

No WAL checkpoint or `PRAGMA wal_checkpoint(FULL)` is required; `connection.close()` is sufficient to ensure durability on POSIX systems with journal mode `delete` (the default). The connection is closed only after the server transport exits.

## 4. Recorder component

### 4.1 Design

`Recorder` is a small, synchronous, stateless helper:

```python
class Recorder:
    def __init__(self, connection: sqlite3.Connection) -> None: ...
    def log(self, timestamp: str, request: str, response: str) -> None: ...
```

- `connection` is the `sqlite3.Connection` object (thread-affinity controlled via `check_same_thread=False` — see §5.2).
- `log()` performs a single `INSERT` on the `investigations` table within a context-managed transaction.

### 4.2 Schema

| Column | Type | Constraint | Description |
|---|---|---|---|
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Monotonically increasing row identifier. Not logged to any external system. |
| `timestamp` | `TEXT` | `NOT NULL` | ISO 8601 UTC timestamp: `datetime.now(timezone.utc).isoformat()` produces e.g. `"2026-09-19T12:34:56.789000+00:00"`. |
| `request` | `TEXT` | `NOT NULL` | The **validated** request dict, serialized with `json.dumps(value, separators=(',', ':'), ensure_ascii=False, sort_keys=True)`. |
| `response` | `TEXT` | `NOT NULL` | The **shaped** response dict (`{"answers": ...}`), serialized with `json.dumps(value, separators=(',', ':'), ensure_ascii=False, sort_keys=True)`. |

No other columns, indexes, or triggers exist.

### 4.3 JSON fidelity

Every call to `Recorder.log()` serialises request and response dicts with the **same** call:

```python
json.dumps(value, separators=(',', ':'), ensure_ascii=False, sort_keys=True)
```

- **Compact format:** `separators=(',', ':')` — no indentation, no trailing whitespace.
- **Unicode:** `ensure_ascii=False` — the raw Unicode from the request (`state`, `instructions`, criteria strings) is preserved without escape.
- **Deterministic ordering:** `sort_keys=True` — alphabetical key ordering guarantees byte-identical output for semantically equal requests/responses.
- **Round-trip guarantee:** `json.loads(serialized) == value` for every value that is JSON-serialisable (dict, str, float, int, bool, None, list). If `json.dumps` raises `TypeError`, the row is **not** written and an error is raised (§4.4).

### 4.4 No partial rows

A row is written only when the entire `INSERT` commits within the transaction. If serialisation fails or the `INSERT` fails for any reason:

- The row is **not** created.
- The failure is converted to a sanitized MCP error with a message starting with `"[storage]"` (see §6).
- **No successful response is returned** — the tool call fails with the sanitized error.

## 5. Integration with the MCP tool handler

### 5.1 Injection

The `Recorder` instance is injected through `create_server()`:

```python
def create_server(
    client: DecisionsClient | None = None,
    config: Config | None = None,
    recorder: Recorder | None = None,
) -> MCPServer: ...
```

When `recorder` is `None` (default, unconfigured), the tool handler omits the log step entirely. When `recorder` is provided, the handler performs the log step after success.

### 5.2 Placement in the tool handler

The log step is placed **after** the response is fully shaped and **before** the response is returned, so the row is committed (or an error raised) prior to returning success:

```
validate input
    → build JEVRequest
    → asyncio.to_thread(client.decide, request)   ← sync in worker thread
    → shape response into {"answers": ...}
    → if recorder: await asyncio.to_thread(recorder.log, utc_timestamp, request_json, response_json)
    → return {"answers": ...}
```

The recorder is called from the **async tool handler**, so it MUST be executed via `asyncio.to_thread()` to avoid blocking the MCP event loop. The recorder itself is synchronous — it issues the `INSERT` within a lock-guarded transaction.

### 5.3 Thread safety

- The `sqlite3.Connection` is opened **once** at startup with `check_same_thread=False` and guarded by a single `threading.Lock` shared by all `Recorder` instances.
- `Recorder.log()` acquires the lock, begins an explicit transaction (`BEGIN`), executes the `INSERT`, then either `COMMIT` or `ROLLBACK` within a `try/finally` block:

  ```python
  with self._lock:
      try:
          self._connection.execute(
              "INSERT INTO investigations (timestamp, request, response) VALUES (?, ?, ?)",
              (timestamp, request_json, response_json),
          )
          self._connection.commit()
      except Exception:
          self._connection.rollback()
          raise
  ```

- The lock serialises all concurrent log invocations across worker threads. No additional SQLite-level tuning is required because each `INSERT` is a single statement, and there are no `SELECT` or `UPDATE` queries.
- Should the `INSERT` raise `sqlite3.IntegrityError` (e.g. corrupted database), the error is caught, sanitised, and re-raised as a storage failure (§6).

### 5.4 No storage of failures

The log step is reached **only after** `client.decide()` returns successfully **and** the response is fully shaped. The following are **not** logged:

- Input validation failures (before `JEVRequest` construction).
- Transport errors from `client.decide()`.
- HTTP non-2xx, malformed JSON, or `DecisionsError` from the API.
- Shaping errors (unexpected answer types, missing keys).
- Any failure during the log step itself — these are handled as storage errors that prevent a successful response.

## 6. Storage error sanitization

When a storage error occurs (serialisation failure, `INSERT` failure, `IntegrityError`, etc.):

1. The error is caught within the tool handler.
2. A `DecisionsError` is raised with a message of the form:

   ```
   [storage] Investigation log: <sanitized description>
   ```

3. The sanitized description contains only:
   - The class name of the original exception (e.g. `sqlite3.OperationalError`).
   - A brief, non-crash-explaining phrase (e.g. `"disk full"` for `SQLITE_FULL`, `"locked"` for `SQLITE_BUSY`).
4. The error is **not** propagated verbatim — it is truncated to 200 characters and redacted per the existing redaction rules (no paths reveal sensitive directories, no raw SQL fragments).

Example:
- Original: `sqlite3.OperationalError: database disk image is malformed`
- Sanitised: `[storage] Investigation log: OperationalError: database disk image is malformed`
- Original: `sqlite3.OperationalError: disk full`
- Sanitised: `[storage] Investigation log: OperationalError: disk full`

**No successful response is returned.** The tool call fails with the sanitized error. The absence of a row in the database is the observable consequence of the failure.

## 7. Lifecycle and concurrency

### 7.1 Process lifetime

- The database connection is opened once at startup (when `--sqlite-db` is given) and closed once at shutdown.
- No re-opening, reconnecting, or migration logic exists.
- If the database file is deleted between invocations while the process is running, the next `INSERT` will raise an exception that is sanitised as a storage error.

### 7.2 Concurrent invocations

The MCP server handles tool calls sequentially on a single process (no inter-process concurrency). Within a single process, async tool handlers for `jev_decide` may be dispatched to multiple worker threads via `asyncio.to_thread()`. Concurrency is safe because:

- A single `threading.Lock` serialises all calls to `Recorder.log()`, ensuring only one `INSERT` + `COMMIT`/`ROLLBACK` executes at a time.
- The `sqlite3.Connection` is opened with `check_same_thread=False`, but the lock is the authoritative concurrency guard.
- No additional application-level locking is required because each `INSERT` is a single statement and there are no `SELECT` or `UPDATE` queries.

### 7.3 Crash safety

On unclean shutdown (SIGKILL, OOM):

- SQLite's default `delete` journal mode provides crash safety: the uncommitted transaction is discarded on recovery.
- Because each `INSERT` is its own explicit transaction, at most one row may be lost (the one in-flight during the crash).
- No explicit `PRAGMA synchronous` tuning is performed (defaults to `FULL`).
- If a crash occurs mid-`INSERT`, the transaction is rolled back on recovery and no partial row is written (§4.4).

## 8. File location contract

- **No default path.** `--sqlite-db` is the *only* way to activate logging. Without the flag, no file is created, no directory is searched, and no XDG-style fallback is attempted.
- **Caller-resolved path.** The path is used exactly as provided. No tilde expansion, no environment variable interpolation, no canonicalisation beyond the startup validation check that the parent directory exists.
- **No read-back.** The server never reads from the database at any point — startup, runtime, or shutdown.

## 9. Testable acceptance criteria

| # | Criterion | Verification |
|---|-----------|--------------|
| 1 | Without `--sqlite-db`, no database file is created or touched. | Start server in test mode (or unit-test `main` with no flag); confirm no new file appears in CWD after shutdown. |
| 2 | With `--sqlite-db /tmp/test.db`, the `investigations` table is created on first connect. | Open the DB file with `sqlite3` CLI after server start; verify `CREATE TABLE` exists. |
| 3 | A successful `jev_decide` call writes exactly one row. | After one successful call, count rows: `SELECT COUNT(*) FROM investigations` returns `1`. |
| 4 | The row contains correct `timestamp`, `request`, and `response` columns. | Read the row and verify `timestamp` matches ISO 8601 UTC; `request` and `response` parse back as valid JSON. |
| 5 | JSON serialisation is deterministic (sorted keys, compact separators, no ASCII escaping). | Two identical calls produce byte-identical `request` and `response` columns. |
| 6 | Validation failures do not create rows. | Call with invalid input (blank `state`); verify row count is still 0. |
| 7 | API/client errors do not create rows. | Inject a failing fake client; call the tool; verify row count is still 0. |
| 8 | Storage errors fail the call and create no row. | Corrupt the database *after* the table exists; call the tool successfully (upstream succeeds); verify the call fails with a `[storage]` error and no row was written. |
| 9 | Parent-does-not-exist exits with error, no file created. | Start with `--sqlite-db /nonexistent/path/db.sqlite`; verify exit code 1 and no file at `/nonexistent`. |
| 10 | A database from a previous run is safe to reopen (`IF NOT EXISTS`). | Stop server after writing rows; restart with same `--sqlite-db` path; verify previous rows are still present and new writes append. |
| 11 | Shutdown closes the database cleanly. | Start with `--sqlite-db`; send SIGTERM; verify no `sqlite3.OperationalError` on shutdown. |
| 12 | `create_server(recorder=...)` accepts a `Recorder` instance and uses it. | Unit-test: inject a mock `Recorder`; call `jev_decide`; verify `recorder.log()` was called exactly once with correct arguments. |

## 10. Documentation updates

### 10.1 README.md

Add a subsection under **MCP server** (after the existing tool input/output description) describing the optional logging flag:

```markdown
### Investigation logging

The server can optionally log every successful investigation to an SQLite database:

```sh
uv run python -m jev_mcp.server --sqlite-db ./investigations.db
```

Each successful `jev_decide` call appends one row (timestamp, request, response).
Failed calls, validation errors, and storage errors are not logged.
The flag is optional — omit it for no logging.
```

### 10.2 Home.md (wiki)

Add a brief note in the MCP server section referencing the investigation log flag.

### 10.3 Spec directory

This file (`2026-09-19-sqlite-mcp-investigation-design.md`) is the sole spec. No companion implementation plan is required for this task.

## 11. File map

| Path | Role |
|---|---|
| `jev_mcp/server.py` | Add `--sqlite-db` arg to `main()`; add `recorder` param to `create_server()`; inject `Recorder.log()` in tool handler. |
| `jev_mcp/server.py` (new section) | `Recorder` class definition — one file, one component. |
| `docs/superpowers/specs/2026-09-19-sqlite-mcp-investigation-design.md` | This design spec. |
| `tests/test_mcp_server.py` | Tests for §§1–12 acceptance criteria above. New test class `TestSQLiteInvestigationLogging`. |
| `tests/test_mcp_server.py` | Mock recorder fixture; tests for path validation, crash safety, storage error sanitisation, and no-partial-rows. |
| `README.md` | Update MCP server section. |
| `docs/wiki/Home.md` | Brief mention in MCP section. |
