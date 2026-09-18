"""Focused MCP-server tests: validation, shaping, redaction, lifecycle — no network."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from jev_bot.config import Config
from jev_bot.errors import DecisionsError
from jev_bot.models import JEVRequest, JEVResponse, NoulResult

# Pinned model identifier — matches jev_mcp.server.MODEL_ID.
MODEL_ID = "~typesafe/jev-latest"

from jev_mcp.server import (
    _build_decide_tool,
    _known_question_fields,
    _redact_sensitive,
    _validate_question_type,
)

# We deliberately DO NOT import DecisionsClient here — the contract uses the
# real jev_bot.client.DecisionsClient.  Tests inject a hand-crafted fake via
# the tool factory.


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


FAKE_CONFIG = Config(
    endpoint="https://openrouter.ai/api/alpha/decisions",
    token="fake-token",
)


class FakeClient:
    """Minimal fake that satisfies the tool factory without touching the real client."""

    def __init__(
        self,
        decide_returns: JEVResponse | None = None,
        decide_raises: Exception | None = None,
    ) -> None:
        self.decide_returns = decide_returns
        self.decide_raises = decide_raises
        self._closed = False

    def decide(self, request: JEVRequest) -> JEVResponse:
        if self.decide_raises:
            raise self.decide_raises
        return self.decide_returns if self.decide_returns else JEVResponse.from_dict({"answers": {"framework": {"choice": "chainlit", "probabilities": {"chainlit": 1.0}}}})

    def close(self) -> None:
        self._closed = True


def _make_fake(
    decide_returns: dict[str, Any] | None = None,
    decide_raises: Exception | None = None,
) -> FakeClient:
    """Build a fake client whose decide() returns a dict or raises."""
    response: JEVResponse | None = None
    if decide_returns is not None:
        response = JEVResponse.from_dict(decide_returns)
    return FakeClient(decide_returns=response, decide_raises=decide_raises)


def _run_tool(
    state: str,
    questions: dict[str, dict[str, Any]],
    client: FakeClient | None = None,
) -> dict[str, Any]:
    """Synchronous helper to call *jev_decide* (wraps async)."""
    if client is None:
        client = FakeClient()
    tool_fn = _build_decide_tool(client, FAKE_CONFIG)
    return asyncio.run(tool_fn(state=state, questions=questions))


# ===========================================================================
# 1. No pre-HTTP invalid calls — invalid inputs are rejected before client
# ===========================================================================


class TestPreHTTPValidation:
    """These errors are raised BEFORE any HTTP call."""

    def test_unknown_field_rejected(self) -> None:
        client = _make_fake()
        with pytest.raises(DecisionsError, match="unknown field"):
            _run_tool(
                "x",
                {"q": {"type": "noul", "instructions": "q", "extra": 42}},
                client,
            )

    def test_unknown_type_rejected(self) -> None:
        client = _make_fake()
        with pytest.raises(DecisionsError, match="unknown type"):
            _run_tool(
                "x",
                {"q": {"type": "typo", "instructions": "q"}},
                client,
            )

    def test_choice_missing_criteria_rejected(self) -> None:
        client = _make_fake()
        with pytest.raises(DecisionsError, match="type 'choice' requires a 'criteria' field"):
            _run_tool(
                "x",
                {"q": {"type": "choice", "instructions": "pick"}},
                client,
            )

    def test_choice_criteria_bad_type_rejected(self) -> None:
        client = _make_fake()
        with pytest.raises(DecisionsError, match="'criteria' must be an object"):
            _run_tool(
                "x",
                {"q": {"type": "choice", "instructions": "pick", "criteria": "not a dict"}},
                client,
            )

    def test_score_missing_criteria_rejected(self) -> None:
        client = _make_fake()
        with pytest.raises(DecisionsError, match="type 'score' requires a 'criteria' field"):
            _run_tool(
                "x",
                {"q": {"type": "score", "instructions": "rate"}},
                client,
            )

    def test_score_criteria_bad_type_rejected(self) -> None:
        client = _make_fake()
        with pytest.raises(DecisionsError, match="'criteria' must be a list"):
            _run_tool(
                "x",
                {"q": {"type": "score", "instructions": "rate", "criteria": "not a list"}},
                client,
            )

    def test_noul_unknown_field_rejected(self) -> None:
        client = _make_fake()
        with pytest.raises(DecisionsError, match="unknown field"):
            _run_tool(
                "x",
                {"q": {"type": "noul", "instructions": "q", "noul": 0.5}},
                client,
            )

    def test_noul_criteria_rejected(self) -> None:
        client = _make_fake()
        with pytest.raises(DecisionsError, match="unknown field"):
            _run_tool(
                "x",
                {"q": {"type": "noul", "instructions": "q", "criteria": {"x": "y"}}},
                client,
            )

    def test_question_missing_type_rejected(self) -> None:
        client = _make_fake()
        with pytest.raises(DecisionsError, match="missing required field 'type'"):
            _run_tool(
                "x",
                {"q": {"choice": "a"}},
                client,
            )

    def test_state_blank_rejected(self) -> None:
        client = _make_fake()
        with pytest.raises(DecisionsError, match="state must be"):
            _run_tool(
                "   ",
                {"q": {"type": "noul", "instructions": "q"}},
                client,
            )

    def test_state_too_long_rejected(self) -> None:
        client = _make_fake()
        with pytest.raises(DecisionsError, match="8000"):
            _run_tool(
                "x" * 8001,
                {"q": {"type": "noul", "instructions": "q"}},
                client,
            )

    def test_empty_questions_map_rejected(self) -> None:
        client = _make_fake()
        with pytest.raises(DecisionsError, match="1.*8"):
            _run_tool("ok", {}, client)

    def test_too_many_questions_rejected(self) -> None:
        client = _make_fake()
        with pytest.raises(DecisionsError, match="1.*8"):
            _run_tool(
                "ok",
                {f"q{i}": {"type": "noul", "instructions": f"Instruction {i}"} for i in range(9)},
                client,
            )

    def test_questions_not_a_dict_rejected(self) -> None:
        client = _make_fake()
        with pytest.raises(DecisionsError, match="questions must be a map"):
            _run_tool("ok", [{"type": "noul", "instructions": "q"}], client)  # type: ignore[arg-type]

    def test_instructions_blank_rejected(self) -> None:
        client = _make_fake()
        with pytest.raises(DecisionsError, match="'instructions' must be"):
            _run_tool(
                "ok",
                {"q": {"type": "noul", "instructions": "  "}},
                client,
            )

    def test_instructions_missing_rejected(self) -> None:
        client = _make_fake()
        with pytest.raises(DecisionsError, match="missing required field 'instructions'"):
            _run_tool(
                "ok",
                {"q": {"type": "noul"}},
                client,
            )

    def test_instructions_too_long_rejected(self) -> None:
        client = _make_fake()
        with pytest.raises(DecisionsError, match="2000"):
            _run_tool(
                "ok",
                {"q": {"type": "noul", "instructions": "x" * 2001}},
                client,
            )

    def test_invalid_question_name_rejected(self) -> None:
        client = _make_fake()
        with pytest.raises(DecisionsError, match="must match"):
            _run_tool(
                "ok",
                {"1bad": {"type": "noul", "instructions": "hi"}},
                client,
            )

    def test_model_field_rejected(self) -> None:
        """The 'model' key is not a known field and must be rejected."""
        client = _make_fake()
        with pytest.raises(DecisionsError, match="unknown field"):
            _run_tool(
                "decide",
                {"q": {"type": "noul", "instructions": "hi", "model": "other"}},
                client,
            )


# ===========================================================================
# 2. Mixed question result shaping
# ===========================================================================


class TestMixedQuestionShaping:
    def test_single_choice_question(self) -> None:
        client = _make_fake(
            decide_returns={
                "answers": {
                    "framework": {"type": "choice", "choice": "gradio", "probabilities": {"gradio": 0.7, "chainlit": 0.3}, "confidence": 0.7},
                }
            }
        )
        result = _run_tool(
            "choice time",
            {
                "framework": {
                    "type": "choice",
                    "instructions": "Which framework?",
                    "criteria": {"gradio": "Gradio UI", "chainlit": "Chainlit"},
                }
            },
            client,
        )
        assert result["answers"]["framework"]["choice"] == "gradio"
        assert result["answers"]["framework"]["probabilities"]["gradio"] == 0.7
        assert result["answers"]["framework"]["type"] == "choice"
        assert result["answers"]["framework"]["confidence"] == 0.7

    def test_single_score_question(self) -> None:
        client = _make_fake(
            decide_returns={"answers": {"quality": {"type": "score", "score": 8.5, "confidence": 0.8}}}
        )
        result = _run_tool(
            "score me",
            {
                "quality": {
                    "type": "score",
                    "instructions": "Rate quality",
                    "criteria": ["speed", "stability"],
                }
            },
            client,
        )
        assert result["answers"]["quality"]["score"] == 8.5

    def test_single_noul_question(self) -> None:
        client = _make_fake(
            decide_returns={"answers": {"risk": {"type": "noul", "noul": 0.25}}}
        )
        result = _run_tool(
            "rate risk",
            {
                "risk": {
                    "type": "noul",
                    "instructions": "How risky?",
                }
            },
            client,
        )
        assert result["answers"]["risk"]["noul"] == 0.25

    def test_mixed_choice_and_score(self) -> None:
        client = _make_fake(
            decide_returns={
                "answers": {
                    "framework": {"type": "choice", "choice": "chainlit", "probabilities": {"chainlit": 0.9}, "confidence": 0.9},
                    "quality": {"type": "score", "score": 4.0, "confidence": 0.7},
                }
            }
        )
        result = _run_tool(
            "mixed",
            {
                "framework": {
                    "type": "choice",
                    "instructions": "Pick framework",
                    "criteria": {"chainlit": "chainlit", "gradio": "gradio"},
                },
                "quality": {
                    "type": "score",
                    "instructions": "Rate quality",
                    "criteria": ["speed", "stability"],
                },
            },
            client,
        )
        assert result["answers"]["framework"]["choice"] == "chainlit"
        assert "score" in result["answers"]["quality"]
        assert result["answers"]["quality"]["score"] == 4.0

    def test_mixed_all_three_types(self) -> None:
        client = _make_fake(
            decide_returns={
                "answers": {
                    "which": {"type": "choice", "choice": "fastapi", "probabilities": {"fastapi": 0.5, "gradio": 0.5}, "confidence": 0.5},
                    "risk": {"type": "noul", "noul": 0.1},
                    "rating": {"type": "score", "score": 9.9, "details": "outstanding", "confidence": 0.95},
                }
            }
        )
        result = _run_tool(
            "all types",
            {
                "which": {
                    "type": "choice",
                    "instructions": "Pick which?",
                    "criteria": {"fastapi": "fastapi", "gradio": "gradio"},
                },
                "risk": {
                    "type": "noul",
                    "instructions": "How risky?",
                },
                "rating": {
                    "type": "score",
                    "instructions": "Rate rating",
                    "criteria": ["details", "notes"],
                },
            },
            client,
        )
        assert result["answers"]["which"]["choice"] == "fastapi"
        assert result["answers"]["risk"]["noul"] == 0.1
        assert result["answers"]["rating"]["score"] == 9.9
        assert result["answers"]["rating"]["details"] == "outstanding"

    def test_response_wrapped_in_answers_key(self) -> None:
        """Top-level response is always {"answers": {...}}."""
        client = _make_fake(
            decide_returns={"answers": {"q": {"type": "noul", "noul": 0.5}}}
        )
        result = _run_tool(
            "ok",
            {"q": {"type": "noul", "instructions": "q"}},
            client,
        )
        assert set(result.keys()) == {"answers"}


# ===========================================================================
# 3. Client error redaction — errors never leak tokens/endpoints
# ===========================================================================


class TestErrorRedaction:
    def test_decisions_error_redacts_token(self) -> None:
        client = _make_fake(
            decide_raises=DecisionsError("bad: token=fake-token here")
        )
        with pytest.raises(DecisionsError) as exc_info:
            _run_tool(
                "ok",
                {"q": {"type": "noul", "instructions": "q"}},
                client,
            )
        msg = str(exc_info.value)
        assert "fake-token" not in msg
        assert "[REDACTED]" in msg

    def test_decisions_error_redacts_endpoint(self) -> None:
        client = _make_fake(
            decide_raises=DecisionsError(
                "bad endpoint: https://openrouter.ai/api/alpha/decisions"
            )
        )
        with pytest.raises(DecisionsError) as exc_info:
            _run_tool(
                "ok",
                {"q": {"type": "noul", "instructions": "q"}},
                client,
            )
        msg = str(exc_info.value)
        assert "openrouter.ai" not in msg
        assert "[REDACTED]" in msg

    def test_decisions_error_redacts_bare_token_value(self) -> None:
        client = _make_fake(
            decide_raises=DecisionsError("bearer=fake-token leak")
        )
        with pytest.raises(DecisionsError) as exc_info:
            _run_tool(
                "ok",
                {"q": {"type": "noul", "instructions": "q"}},
                client,
            )
        msg = str(exc_info.value)
        assert "fake-token" not in msg

    def test_non_decisions_error_wrapped_and_redacted(self) -> None:
        class BrokenClient(FakeClient):
            def decide(self, request: JEVRequest) -> JEVResponse:
                raise ConnectionError("network down: fake-token leaked here")

            def close(self) -> None:
                pass

        client = BrokenClient()
        with pytest.raises(DecisionsError) as exc_info:
            _run_tool(
                "ok",
                {"q": {"type": "noul", "instructions": "q"}},
                client,
            )
        msg = str(exc_info.value)
        assert "fake-token" not in msg
        assert "[REDACTED]" in msg

    def test_redact_sensitive_on_config(self) -> None:
        text = "token=fake-token endpoint=https://openrouter.ai/api/alpha/decisions"
        redacted = _redact_sensitive(text, FAKE_CONFIG)
        assert "fake-token" not in redacted
        assert "openrouter.ai" not in redacted
        assert "[REDACTED]" in redacted


# ===========================================================================
# 4. Output shaping — no pre-built answer errors, only sanitized raises
# ===========================================================================


class TestOutputShaping:
    def test_score_extra_included(self) -> None:
        client = _make_fake(
            decide_returns={
                "answers": {"rating": {"type": "score", "score": 8.0, "note": "very good", "details": "solid", "confidence": 0.85}}
            }
        )
        result = _run_tool(
            "score extra",
            {
                "rating": {
                    "type": "score",
                    "instructions": "Rate rating",
                    "criteria": ["note", "details"],
                }
            },
            client,
        )
        assert result["answers"]["rating"]["score"] == 8.0
        assert result["answers"]["rating"]["note"] == "very good"
        assert result["answers"]["rating"]["details"] == "solid"

    def test_score_no_extra(self) -> None:
        client = _make_fake(
            decide_returns={"answers": {"q": {"type": "score", "score": 5.0, "confidence": 0.6}}}
        )
        result = _run_tool(
            "no extra",
            {"q": {"type": "score", "instructions": "Rate", "criteria": ["c1", "c2"]}},
            client,
        )
        assert result["answers"]["q"]["score"] == 5.0
        assert result["answers"]["q"]["type"] == "score"
        assert result["answers"]["q"]["confidence"] == 0.6
        assert set(result["answers"]["q"].keys()) == {"score", "type", "confidence"}

    def test_named_keys_preserved(self) -> None:
        """Answer keys match the question map keys."""
        client = _make_fake(
            decide_returns={
                "answers": {
                    "framework": {"type": "choice", "choice": "gradio", "probabilities": {"gradio": 1.0}, "confidence": 1.0},
                    "quality": {"type": "score", "score": 7.0, "confidence": 0.7},
                }
            }
        )
        result = _run_tool(
            "named",
            {
                "framework": {
                    "type": "choice",
                    "instructions": "Pick framework",
                    "criteria": {"gradio": "gradio", "chainlit": "chainlit"},
                },
                "quality": {
                    "type": "score",
                    "instructions": "Rate quality",
                    "criteria": ["speed", "stability"],
                },
            },
            client,
        )
        assert "framework" in result["answers"]
        assert "quality" in result["answers"]


# ===========================================================================
# 5. Malformed response errors — raise sanitized DecisionsError, never success
# ===========================================================================


class TestMalformedResponse:
    def test_missing_answer_raises_sanitized_error(self) -> None:
        """If the API omits an answer key, the tool raises a DecisionsError."""
        client = _make_fake(
            decide_returns={
                "answers": {"other": {"type": "noul", "noul": 0.5}}  # 'q' is missing
            }
        )
        with pytest.raises(DecisionsError, match="Missing answer"):
            _run_tool(
                "ok",
                {"q": {"type": "noul", "instructions": "q"}},
                client,
            )

    def test_unexpected_result_type_raises(self) -> None:
        """Unknown answer result types raise a DecisionsError."""
        # A dict with no recognized keys will cause _parse_answer to raise,
        # which propagates through the client. Let's simulate by returning a
        # response with a weird structure by having the client raise directly.
        client = _make_fake(
            decide_raises=DecisionsError("Malformed Decisions payload: 'answers.q' missing")
        )
        with pytest.raises(DecisionsError, match="Malformed"):
            _run_tool(
                "ok",
                {"q": {"type": "noul", "instructions": "q"}},
                client,
            )


# ===========================================================================
# 6. Question conversions — ChoiceQuestion, ScoreQuestion, NoulQuestion
# ===========================================================================


class TestQuestionConversions:
    def test_choice_question_with_criteria(self) -> None:
        """Choice question with explicit criteria."""
        client = _make_fake(
            decide_returns={
                "answers": {"framework": {"type": "choice", "choice": "fastapi", "probabilities": {"fastapi": 0.6, "gradio": 0.4}, "confidence": 0.6}}
            }
        )
        result = _run_tool(
            "criteria",
            {
                "framework": {
                    "type": "choice",
                    "instructions": "Which framework?",
                    "criteria": {"fastapi": "FastAPI backend", "gradio": "Gradio UI"},
                }
            },
            client,
        )
        assert result["answers"]["framework"]["choice"] == "fastapi"

    def test_score_question_with_criteria(self) -> None:
        """Score question with explicit ordered criteria list."""
        client = _make_fake(
            decide_returns={"answers": {"quality": {"type": "score", "score": 9.0, "confidence": 0.9}}}
        )
        result = _run_tool(
            "score criteria",
            {
                "quality": {
                    "type": "score",
                    "instructions": "Rate quality",
                    "criteria": ["performance", "reliability", "usability"],
                }
            },
            client,
        )
        assert result["answers"]["quality"]["score"] == 9.0

    def test_score_criteria_wrong_type_rejected(self) -> None:
        client = _make_fake()
        with pytest.raises(DecisionsError, match="criteria"):
            _run_tool(
                "bad",
                {
                    "q": {
                        "type": "score",
                        "instructions": "rate",
                        "criteria": {"not": "a list"},
                    }
                },
                client,
            )

    def test_noul_question_no_criteria(self) -> None:
        """Noul question: only instructions; no criteria."""
        client = _make_fake(
            decide_returns={"answers": {"risk": {"type": "noul", "noul": 0.3}}}
        )
        result = _run_tool(
            "noul only",
            {
                "risk": {
                    "type": "noul",
                    "instructions": "How risky?",
                }
            },
            client,
        )
        assert result["answers"]["risk"]["noul"] == 0.3

    def test_noul_criteria_rejected(self) -> None:
        """noul type does not accept 'criteria' field."""
        client = _make_fake()
        with pytest.raises(DecisionsError, match="unknown field"):
            _run_tool(
                "bad noul",
                {"q": {"type": "noul", "instructions": "q", "criteria": {"x": "y"}}},
                client,
            )

    def test_score_criteria_rejected_for_choice(self) -> None:
        """criteria on a choice question must be a dict, not a list."""
        client = _make_fake()
        with pytest.raises(DecisionsError, match="criteria"):
            _run_tool(
                "bad score criteria",
                {
                    "q": {
                        "type": "choice",
                        "instructions": "pick",
                        "criteria": ["not", "valid"],
                    }
                },
                client,
            )

    def test_choice_criteria_wrong_type_rejected(self) -> None:
        """criteria on choice must be a dict."""
        client = _make_fake()
        with pytest.raises(DecisionsError, match="criteria"):
            _run_tool(
                "bad",
                {
                    "q": {
                        "type": "choice",
                        "instructions": "pick",
                        "criteria": "not a dict",
                    }
                },
                client,
            )


# ===========================================================================
# 7. Async thread — decide is called via asyncio.to_thread
# ===========================================================================


class TestAsyncThread:
    def test_decide_runs_in_thread(self) -> None:
        """Verify decide() is executed in a separate thread."""
        import threading

        thread_names: list[str] = []

        class ThreadCheckingClient(FakeClient):
            def decide(self, request: JEVRequest) -> JEVResponse:
                thread_names.append(threading.current_thread().name)
                return JEVResponse.from_dict({"answers": {"q": {"type": "noul", "noul": 0.0}}})

            def close(self) -> None:
                pass

        client = ThreadCheckingClient()
        _run_tool(
            "test",
            {"q": {"type": "noul", "instructions": "q"}},
            client,
        )

        main_thread = threading.main_thread().name
        assert len(thread_names) == 1, f"Expected exactly one worker thread, got {thread_names}"
        assert thread_names[0] != main_thread, (
            f"Expected worker thread (not main '{main_thread}'), got: {thread_names}"
        )


# ===========================================================================
# 8. Client close lifecycle
# ===========================================================================


class TestClientCloseLifecycle:
    def test_close_called_on_fake(self) -> None:
        client = _make_fake()
        assert not client._closed
        client.close()
        assert client._closed

    def test_manually_created_client_closeable(self) -> None:
        from jev_mcp.server import DecisionsClient

        client = DecisionsClient(FAKE_CONFIG)
        assert hasattr(client, "close")
        client.close()  # no-op; just shouldn't raise


# ===========================================================================
# 9. Known question fields for each type
# ===========================================================================


class TestKnownQuestionFields:
    def test_choice_fields(self) -> None:
        assert _known_question_fields("choice") == {"type", "criteria", "instructions"}

    def test_score_fields(self) -> None:
        assert _known_question_fields("score") == {"type", "criteria", "instructions"}

    def test_noul_fields(self) -> None:
        assert _known_question_fields("noul") == {"type", "instructions"}

    def test_unknown_type_returns_empty(self) -> None:
        assert _known_question_fields("typo") == set()


# ===========================================================================
# 10. Only jev_decide tool — no mutation tools
# ===========================================================================


class TestToolRegistry:
    def test_only_one_tool_registered(self) -> None:
        from mcp.server.mcpserver import MCPServer

        server = MCPServer(name="jev", version="0.1.0")
        client = _make_fake()
        decide_fn = _build_decide_tool(client, FAKE_CONFIG)
        server.add_tool(decide_fn, name="jev_decide", title="jev_decide")

        async def _list():
            tools = await server.list_tools()
            return [t.name for t in tools]

        names = asyncio.run(_list())
        assert names == ["jev_decide"]

    def test_tool_is_read_only(self) -> None:
        client = _make_fake(
            decide_returns={"answers": {"q": {"type": "noul", "noul": 0.5}}}
        )
        r1 = _run_tool("first", {"q": {"type": "noul", "instructions": "q"}}, client)
        r2 = _run_tool("second", {"q": {"type": "noul", "instructions": "q"}}, client)
        assert r1["answers"]["q"]["noul"] == 0.5
        assert r2["answers"]["q"]["noul"] == 0.5


# ===========================================================================
# 11. No network — full integration test with fake client
# ===========================================================================


class TestNoNetwork:
    def test_fully_mocked_tool(self) -> None:
        """End-to-end through tool factory: fake client, no HTTP."""
        client = _make_fake(
            decide_returns={
                "answers": {
                    "which": {"type": "choice", "choice": "chainlit", "probabilities": {"chainlit": 0.6, "gradio": 0.4}, "confidence": 0.6},
                    "risk": {"type": "noul", "noul": 0.3},
                    "rating": {"type": "score", "score": 7.0, "note": "good", "confidence": 0.75},
                }
            }
        )
        result = _run_tool(
            "integrate all three",
            {
                "which": {
                    "type": "choice",
                    "instructions": "Which?",
                    "criteria": {"chainlit": "Chainlit", "gradio": "Gradio"},
                },
                "risk": {
                    "type": "noul",
                    "instructions": "How risky?",
                },
                "rating": {
                    "type": "score",
                    "instructions": "Rate rating",
                    "criteria": ["quality", "stability"],
                },
            },
            client,
        )
        assert result["answers"]["which"]["choice"] == "chainlit"
        assert result["answers"]["risk"]["noul"] == 0.3
        assert result["answers"]["rating"]["score"] == 7.0
        assert result["answers"]["rating"]["note"] == "good"

    def test_choice_with_criteria_accepted(self) -> None:
        client = _make_fake(
            decide_returns={"answers": {"q": {"type": "choice", "choice": "a", "probabilities": {"a": 1.0}, "confidence": 1.0}}}
        )
        result = _run_tool(
            "with criteria",
            {
                "q": {
                    "type": "choice",
                    "instructions": "Pick",
                    "criteria": {"a": "desc A", "b": "desc B"},
                }
            },
            client,
        )
        assert result["answers"]["q"]["choice"] == "a"

    def test_criteria_is_unknown_field_for_score_type(self) -> None:
        """criteria on a score question must be a list, not a dict."""
        client = _make_fake()
        with pytest.raises(DecisionsError, match="criteria"):
            _run_tool(
                "bad score",
                {
                    "q": {
                        "type": "score",
                        "instructions": "rate",
                        "criteria": {"x": "y"},
                    }
                },
                client,
            )

    def test_criteria_is_unknown_field_for_noul_type(self) -> None:
        client = _make_fake()
        with pytest.raises(DecisionsError, match="unknown field"):
            _run_tool(
                "bad noul",
                {"q": {"type": "noul", "instructions": "q", "criteria": {"x": "y"}}},
                client,
            )

    def test_non_dict_question_value_rejected(self) -> None:
        client = _make_fake()
        with pytest.raises(DecisionsError, match="must be an object"):
            _run_tool(
                "x",
                {"q": "not a dict"},
                client,
            )

    def test_default_model_not_overridable(self) -> None:
        """The JEVRequest always carries MODEL_ID; no caller field can change it."""

        class ModelCheckingClient(FakeClient):
            def decide(self, request: JEVRequest) -> JEVResponse:
                assert request.model == MODEL_ID
                return JEVResponse.from_dict(
                    {"answers": {"q": {"type": "choice", "choice": "a", "probabilities": {"a": 1.0}, "confidence": 1.0}}}
                )

            def close(self) -> None:
                pass

        client = ModelCheckingClient()
        _run_tool(
            "model check",
            {
                "q": {
                    "type": "choice",
                    "instructions": "Pick",
                    "criteria": {"a": "Option A", "b": "Option B"},
                }
            },
            client,
        )



# ===========================================================================
# 12. Output shaping — type and confidence fields
# ===========================================================================


class TestOutputTypeConfidence:
    def test_choice_includes_type(self) -> None:
        """Choice answers include 'type': 'choice'."""
        client = _make_fake(
            decide_returns={
                "answers": {
                    "fw": {"type": "choice", "choice": "gradio", "probabilities": {"gradio": 0.8}, "confidence": 0.85},
                }
            }
        )
        result = _run_tool(
            "type check",
            {
                "fw": {
                    "type": "choice",
                    "instructions": "Pick",
                    "criteria": {"gradio": "gradio", "chainlit": "chainlit"},
                }
            },
            client,
        )
        assert result["answers"]["fw"]["type"] == "choice"

    def test_choice_includes_confidence(self) -> None:
        """Choice answers include 'confidence' from the model response."""
        client = _make_fake(
            decide_returns={
                "answers": {
                    "fw": {"type": "choice", "choice": "gradio", "probabilities": {"gradio": 0.8}, "confidence": 0.85},
                }
            }
        )
        result = _run_tool(
            "confidence check",
            {
                "fw": {
                    "type": "choice",
                    "instructions": "Pick",
                    "criteria": {"gradio": "gradio", "chainlit": "chainlit"},
                }
            },
            client,
        )
        assert result["answers"]["fw"]["confidence"] == 0.85

    def test_score_includes_type(self) -> None:
        """Score answers include 'type': 'score'."""
        client = _make_fake(
            decide_returns={"answers": {"q": {"type": "score", "score": 5.0, "confidence": 0.6}}}
        )
        result = _run_tool(
            "type check",
            {"q": {"type": "score", "instructions": "Rate", "criteria": ["c1", "c2"]}},
            client,
        )
        assert result["answers"]["q"]["type"] == "score"

    def test_score_includes_confidence(self) -> None:
        """Score answers include 'confidence'."""
        client = _make_fake(
            decide_returns={"answers": {"q": {"type": "score", "score": 5.0, "confidence": 0.72}}}
        )
        result = _run_tool(
            "confidence check",
            {"q": {"type": "score", "instructions": "Rate", "criteria": ["c1", "c2"]}},
            client,
        )
        assert result["answers"]["q"]["confidence"] == 0.72

    def test_noul_includes_type(self) -> None:
        """Noul answers include 'type': 'noul'."""
        client = _make_fake(
            decide_returns={"answers": {"risk": {"type": "noul", "noul": 0.25}}}
        )
        result = _run_tool(
            "type check",
            {"risk": {"type": "noul", "instructions": "How risky?"}},
            client,
        )
        assert result["answers"]["risk"]["type"] == "noul"

    def test_noul_no_confidence_when_absent(self) -> None:
        """Noul answers do not include 'confidence' when the model omitted it."""
        client = _make_fake(
            decide_returns={"answers": {"risk": {"type": "noul", "noul": 0.25}}}
        )
        result = _run_tool(
            "no confidence",
            {"risk": {"type": "noul", "instructions": "How risky?"}},
            client,
        )
        assert "confidence" not in result["answers"]["risk"]

    def test_noul_confidence_included_when_present(self) -> None:
        """Noul answers include 'confidence' when the model provided it."""
        client = _make_fake(
            decide_returns={"answers": {"risk": {"type": "noul", "noul": 0.25, "confidence": 0.9}}}
        )
        result = _run_tool(
            "with confidence",
            {"risk": {"type": "noul", "instructions": "How risky?"}},
            client,
        )
        assert result["answers"]["risk"]["confidence"] == 0.9

    def test_all_types_include_type(self) -> None:
        """Every question type includes 'type' in the answer."""
        client = _make_fake(
            decide_returns={
                "answers": {
                    "which": {"type": "choice", "choice": "fastapi", "probabilities": {"fastapi": 0.5, "gradio": 0.5}, "confidence": 0.5},
                    "risk": {"type": "noul", "noul": 0.1},
                    "rating": {"type": "score", "score": 9.9, "details": "outstanding", "confidence": 0.95},
                }
            }
        )
        result = _run_tool(
            "all types",
            {
                "which": {
                    "type": "choice",
                    "instructions": "Pick which?",
                    "criteria": {"fastapi": "fastapi", "gradio": "gradio"},
                },
                "risk": {
                    "type": "noul",
                    "instructions": "How risky?",
                },
                "rating": {
                    "type": "score",
                    "instructions": "Rate rating",
                    "criteria": ["details", "notes"],
                },
            },
            client,
        )
        assert result["answers"]["which"]["type"] == "choice"
        assert result["answers"]["risk"]["type"] == "noul"
        assert result["answers"]["rating"]["type"] == "score"

    def test_existing_fields_preserved_with_type_confidence(self) -> None:
        """Adding type/confidence does not remove existing fields."""
        client = _make_fake(
            decide_returns={
                "answers": {
                    "fw": {"type": "choice", "choice": "fastapi", "probabilities": {"fastapi": 0.6, "gradio": 0.4}, "confidence": 0.6},
                    "rating": {"type": "score", "score": 8.0, "note": "very good", "details": "solid", "confidence": 0.85},
                    "risk": {"type": "noul", "noul": 0.3, "confidence": 0.8},
                }
            }
        )
        result = _run_tool(
            "preserve fields",
            {
                "fw": {
                    "type": "choice",
                    "instructions": "Pick",
                    "criteria": {"fastapi": "FastAPI", "gradio": "Gradio"},
                },
                "rating": {
                    "type": "score",
                    "instructions": "Rate",
                    "criteria": ["note", "details"],
                },
                "risk": {
                    "type": "noul",
                    "instructions": "Risk assessment",
                },
            },
            client,
        )
        assert result["answers"]["fw"]["choice"] == "fastapi"
        assert result["answers"]["fw"]["probabilities"]["fastapi"] == 0.6
        assert result["answers"]["fw"]["confidence"] == 0.6
        assert result["answers"]["fw"]["type"] == "choice"
        assert result["answers"]["rating"]["score"] == 8.0
        assert result["answers"]["rating"]["note"] == "very good"
        assert result["answers"]["rating"]["confidence"] == 0.85
        assert result["answers"]["rating"]["type"] == "score"
        assert result["answers"]["risk"]["noul"] == 0.3
        assert result["answers"]["risk"]["confidence"] == 0.8
        assert result["answers"]["risk"]["type"] == "noul"

    def test_score_without_extra_has_type_and_confidence(self) -> None:
        """Score with no extra fields still gets type + confidence."""
        client = _make_fake(
            decide_returns={"answers": {"q": {"type": "score", "score": 5.0, "confidence": 0.6}}}
        )
        result = _run_tool(
            "minimal score",
            {"q": {"type": "score", "instructions": "Rate", "criteria": ["c1", "c2"]}},
            client,
        )
        assert result["answers"]["q"]["type"] == "score"
        assert result["answers"]["q"]["confidence"] == 0.6
        assert result["answers"]["q"]["score"] == 5.0

