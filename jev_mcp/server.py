"""Stdio MCP server exposing one generic ``jev_decide`` tool."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import threading
from typing import Any

from jev_bot.client import DecisionsClient
from jev_bot.config import Config, load_config
from jev_bot.errors import DecisionsError
from jev_bot.models import (
    ChoiceQuestion,
    ChoiceResult,
    JEVRequest,
    JEVResponse,
    NoulQuestion,
    NoulResult,
    Question,
    ScoreQuestion,
    ScoreResult,
)

# Pinned model identifier — no framework dependency.
MODEL_ID = "~typesafe/jev-latest"

from mcp.server.mcpserver import MCPServer

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_QUESTION_TYPES: set[str] = {"choice", "score", "noul"}
_KEY_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


def _validate_question_type(q: dict[str, Any], index: int) -> None:
    """Ensure *q* is a valid question dict: exactly one ``type`` key and correct fields."""
    if not isinstance(q, dict):
        raise DecisionsError(f"Question at index {index} must be an object")
    if "type" not in q:
        raise DecisionsError(
            f"Question at index {index} is missing required field 'type'"
        )
    qtype = q["type"]
    if qtype not in _QUESTION_TYPES:
        raise DecisionsError(
            f"Question at index {index}: unknown type {qtype!r}; "
            f"expected one of {sorted(_QUESTION_TYPES)}"
        )

    if qtype == "choice":
        _validate_choice_question(q, index)
    elif qtype == "score":
        _validate_score_question(q, index)
    else:  # noul
        _validate_noul_question(q, index)


def _validate_criteria_present(q: dict[str, Any], index: int, qtype: str) -> None:
    if "criteria" not in q:
        raise DecisionsError(
            f"Question at index {index}: type {qtype!r} requires a 'criteria' field"
        )

def _validate_choice_question(q: dict[str, Any], index: int) -> None:
    """Validate a choice question: requires 'criteria' (2-16 key→description)."""
    _validate_criteria_present(q, index, "choice")


def _validate_score_question(q: dict[str, Any], index: int) -> None:
    """Validate a score question: requires 'criteria' (2-16 strings)."""
    _validate_criteria_present(q, index, "score")


def _validate_noul_question(q: dict[str, Any], index: int) -> None:
    """Validate a noul question: no extra fields beyond type/instructions."""
    pass  # noul has no additional fields


def _known_question_fields(qtype: str) -> set[str]:
    """Return the set of fields accepted for a given question type."""
    if qtype == "choice":
        return {"type", "criteria", "instructions"}
    if qtype == "score":
        return {"type", "criteria", "instructions"}
    if qtype == "noul":
        return {"type", "instructions"}
    return set()  # unknown type: reject everything


def _redact_sensitive(text: str, config: Config) -> str:
    """Redact token, endpoint, and auth patterns from *text*."""
    redacted: str = text
    token = getattr(config, "token", "")
    endpoint = getattr(config, "endpoint", "")
    if token:
        redacted = redacted.replace(token, "[REDACTED]")
    if endpoint:
        redacted = redacted.replace(endpoint, "[REDACTED]")
        host = re.sub(r"^https?://", "", endpoint).split("/")[0]
        if host:
            redacted = redacted.replace(host, "[REDACTED]")
    redacted = re.sub(
        r"(?i)(token|authorization|bearer|password|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*\S+",
        r"\1=[REDACTED]",
        redacted,
    )
    return redacted[:300]


class Recorder:
    """Append successful MCP invocations to one SQLite database."""

    def __init__(self, connection: Any) -> None:
        self._connection: Any | None = connection
        self._lock = threading.Lock()

    def log(self, request: dict[str, Any], response: dict[str, Any]) -> None:
        request_json = json.dumps(
            request, separators=(",", ":"), ensure_ascii=False, sort_keys=True
        )
        response_json = json.dumps(
            response, separators=(",", ":"), ensure_ascii=False, sort_keys=True
        )
        with self._lock:
            if self._connection is None:
                raise RuntimeError("Recorder is closed")
            try:
                self._connection.execute(
                    "INSERT INTO investigations (timestamp, request, response) "
                    "VALUES (?, ?, ?)",
                    (datetime.now(timezone.utc).isoformat(), request_json, response_json),
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None


def _startup_sqlite(path: str) -> Recorder:
    database_path = Path(path)
    if not path.strip() or not database_path.parent.is_dir():
        raise ValueError("SQLite database parent directory does not exist")
    import sqlite3

    connection = sqlite3.connect(database_path, check_same_thread=False)
    try:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS investigations ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "timestamp TEXT NOT NULL, request TEXT NOT NULL, response TEXT NOT NULL)"
        )
        connection.commit()
    except Exception:
        connection.close()
        raise
    return Recorder(connection)


# ---------------------------------------------------------------------------
# Tool factory — builds the *jev_decide* tool function
# ---------------------------------------------------------------------------

def _build_decide_tool(
    client: DecisionsClient,
    config: Config | None = None,
    recorder: Recorder | None = None,
) -> Any:
    """Return the function that will be registered as the *jev_decide* tool."""
    if config is None:
        config = client._config  # noqa: SLF001

    async def jev_decide(
        state: str,
        questions: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Ask the JEV engine to decide given state and questions.

        *state* – free-text context (non-blank, ≤ 8 000 chars).
        *questions* – 1–8 question map keyed by name (regex
        ``^[A-Za-z][A-Za-z0-9_]{0,63}$``).  Each value is a dict with
        required non-blank ``instructions`` (≤ 2000 chars).
        ``criteria`` is required for ``choice`` (2–16 key→desc dict) and
        ``score`` (2–16 string list), but NOT for ``noul``:

        * ``choice`` – criteria dict of non-blank key→description pairs.
        * ``score`` – criteria list of non-blank strings.

        Noul questions accept no extra fields.

        Unknown fields (including ``model``) in the top-level questions
        map or within question dicts are rejected before the client call.

        Returns ``{"answers": ...}`` with a JSON-serialisable map from
        question name → result dict.
        """
        # --- Pre-validation (no HTTP) ---------------------------------------
        if not isinstance(state, str) or not state.strip():
            raise DecisionsError("state must be a non-blank string")
        if len(state) > 8000:
            raise DecisionsError("state exceeds 8000 characters")

        if not isinstance(questions, dict):
            raise DecisionsError("questions must be a map")
        if not 1 <= len(questions) <= 8:
            raise DecisionsError("questions must contain 1–8 items")

        typed_questions: dict[str, Question] = {}
        for idx, (name, q) in enumerate(questions.items()):
            if not isinstance(name, str) or not _KEY_PATTERN.match(name):
                raise DecisionsError(
                    f"Question name {name!r}: must match "
                    r"^[A-Za-z][A-Za-z0-9_]{0,63}$"
                )

            if not isinstance(q, dict):
                raise DecisionsError(f"Question {name!r} must be an object")

            # Reject unknown top-level keys in question dict (model, etc.)
            # First check known-question-type fields
            if "type" not in q:
                raise DecisionsError(
                    f"Question {name!r} is missing required field 'type'"
                )
            qtype = q["type"]
            if qtype not in _QUESTION_TYPES:
                raise DecisionsError(
                    f"Question {name!r}: unknown type {qtype!r}; "
                    f"expected one of {sorted(_QUESTION_TYPES)}"
                )

            known = _known_question_fields(qtype)
            # Include "instructions" since it's always required
            unknown = set(q.keys()) - known - {"instructions"}
            if unknown:
                raise DecisionsError(
                    f"Question {name!r}: unknown field(s) {sorted(unknown)}"
                )

            _validate_question_type(q, idx)

            # Validate 'instructions' is required, non-blank, ≤ 2000 chars
            if "instructions" not in q:
                raise DecisionsError(
                    f"Question {name!r} is missing required field 'instructions'"
                )
            instructions = q["instructions"]
            if not isinstance(instructions, str) or not instructions.strip():
                raise DecisionsError(
                    f"Question {name!r}: 'instructions' must be a non-blank string"
                )
            if len(instructions) > 2000:
                raise DecisionsError(
                    f"Question {name!r}: 'instructions' exceeds 2000 characters"
                )

            if qtype == "choice":
                criteria_raw = q["criteria"]
                if not isinstance(criteria_raw, dict):
                    raise DecisionsError(
                        f"Question {name!r}: 'criteria' must be an object"
                    )
                criteria: dict[str, str] = {}
                for k, v in criteria_raw.items():
                    if (
                        not isinstance(k, str)
                        or not k.strip()
                        or not isinstance(v, str)
                        or not v.strip()
                    ):
                        raise DecisionsError(
                            f"Question {name!r}: criteria entries "
                            "must be non-blank key→description"
                        )
                    criteria[k] = v
                if len(criteria) < 2 or len(criteria) > 16:
                    raise DecisionsError(
                        f"Question {name!r}: 'criteria' must have 2–16 entries"
                    )

                typed_questions[name] = ChoiceQuestion(
                    instructions=instructions,
                    criteria=criteria,
                )
            elif qtype == "score":
                criteria_raw = q["criteria"]
                if not isinstance(criteria_raw, list):
                    raise DecisionsError(
                        f"Question {name!r}: 'criteria' must be a list"
                    )
                criteria: list[str] = []
                for c in criteria_raw:
                    if not isinstance(c, str) or not c.strip():
                        raise DecisionsError(
                            f"Question {name!r}: criteria entries "
                            "must be non-blank strings"
                        )
                    criteria.append(c)
                if len(criteria) < 2 or len(criteria) > 16:
                    raise DecisionsError(
                        f"Question {name!r}: 'criteria' must have 2–16 entries"
                    )

                typed_questions[name] = ScoreQuestion(
                    instructions=instructions,
                    criteria=criteria,
                )
            else:  # noul
                typed_questions[name] = NoulQuestion(
                    instructions=instructions,
                )

        # --- Build request (uses model default) -----------------------------
        request = JEVRequest(
            state=state,
            model=MODEL_ID,
            questions=typed_questions,
        )

        # --- Execute via the client (sync in a worker thread) ---------------
        try:
            response = await asyncio.to_thread(client.decide, request)
        except DecisionsError as exc:
            raise DecisionsError(_redact_sensitive(str(exc), config)) from exc
        except Exception as exc:
            raise DecisionsError(_redact_sensitive(str(exc), config)) from exc

        # --- Shape result ---------------------------------------------------
        answers: dict[str, Any] = {}
        for name in typed_questions:
            result = response.answers.get(name)
            if result is None:
                raise DecisionsError(
                    f"Missing answer for question {name!r}"
                )
            if isinstance(result, ChoiceResult):
                entry: dict[str, Any] = {
                    "type": "choice",
                    "choice": result.choice,
                    "probabilities": dict(result.probabilities),
                    "confidence": result.confidence,
                }
                answers[name] = entry
            elif isinstance(result, ScoreResult):
                entry: dict[str, Any] = {
                    "type": "score",
                    "score": result.score,
                    "confidence": result.confidence,
                }
                if result.extra:
                    entry.update(dict(result.extra))
                answers[name] = entry
            elif isinstance(result, NoulResult):
                entry: dict[str, Any] = {
                    "type": "noul",
                    "noul": result.noul,
                }
                if result.confidence is not None:
                    entry["confidence"] = result.confidence
                answers[name] = entry
            else:
                raise DecisionsError(
                    f"Unexpected answer type for question {name!r}"
                )
        result = {"answers": answers}
        if recorder is not None:
            try:
                await asyncio.to_thread(recorder.log, request.to_dict(), result)
            except Exception as exc:
                raise DecisionsError(
                    f"[storage] Investigation log: "
                    f"{_redact_sensitive(f'{type(exc).__name__}: {exc}', config)}"
                ) from exc
        return result

    return jev_decide


# ---------------------------------------------------------------------------
# Server startup
# ---------------------------------------------------------------------------


def create_server(
    client: DecisionsClient | None = None,
    config: Config | None = None,
    recorder: Recorder | None = None,
) -> MCPServer:
    """Create an MCP server with a *jev_decide* tool.

    Production callers omit *client* / *config* so the server handles
    setup lifecycle internally.  Tests can inject a mock client.
    """
    server = MCPServer(
        name="jev",
        version="0.1.0",
        description="JEV Decisions engine via OpenRouter",
    )

    decisions_client: DecisionsClient
    should_close: bool
    effective_config: Config

    if client is not None:
        decisions_client = client
        effective_config = config if config is not None else client._config  # noqa: SLF001
        should_close = False
    else:
        effective_config = config if config is not None else load_config()
        decisions_client = DecisionsClient(effective_config)
        should_close = True

    decide_fn = _build_decide_tool(decisions_client, effective_config, recorder)
    server.add_tool(decide_fn, name="jev_decide", title="jev_decide")

    if should_close:
        # Wrap run() so client.close() fires after the transport exits.
        old_run = server.run

        def _run_with_shutdown(transport: str = "stdio", **kwargs: Any) -> None:
            try:
                old_run(transport, **kwargs)
            finally:
                if recorder is not None:
                    try:
                        recorder.close()
                    except Exception:
                        pass
                try:
                    decisions_client.close()
                except Exception:
                    pass
        server.run = _run_with_shutdown  # type: ignore[assignment]

    return server


def main() -> None:
    """Entry point: start the MCP stdio server."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite-db")
    args = parser.parse_args()
    try:
        recorder = _startup_sqlite(args.sqlite_db) if args.sqlite_db else None
    except Exception as exc:
        parser.error(f"SQLite investigation database unavailable: {exc}")
    create_server(recorder=recorder).run()


if __name__ == "__main__":
    main()
