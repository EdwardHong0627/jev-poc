"""Tests for ChoiceQuestion and generic multi-answer parsing."""

from __future__ import annotations

import pytest

from jev_bot.errors import DecisionsError
from jev_bot.models import (
    Answer,
    ChoiceQuestion,
    ChoiceResult,
    JEVRequest,
    JEVResponse,
    NoulQuestion,
    NoulResult,
    ScoreQuestion,
    ScoreResult,
)


# ---- ChoiceQuestion creation and validation ----

def test_choice_question_accepts_valid_criteria():
    """2 criteria is the minimum."""
    q = ChoiceQuestion(
        instructions="Pick the best database",
        criteria={
            "postgres": "PostgreSQL; robust, mature, ACID-compliant.",
            "sqlite": "SQLite; embedded, zero-config, simple.",
        },
    )
    assert q.type == "choice"
    assert q.instructions == "Pick the best database"
    assert q.criteria == {
        "postgres": "PostgreSQL; robust, mature, ACID-compliant.",
        "sqlite": "SQLite; embedded, zero-config, simple.",
    }


def test_choice_question_accepts_up_to_16_criteria():
    """16 criteria (the maximum) is accepted."""
    criteria = {
        f"option_{i}": f"Description for option {i}"
        for i in range(16)
    }
    q = ChoiceQuestion(
        instructions="Choose",
        criteria=criteria,
    )
    assert len(q.criteria) == 16


def test_choice_question_rejects_too_few_criteria():
    """Fewer than 2 criteria must raise."""
    with pytest.raises(DecisionsError):
        ChoiceQuestion(
            instructions="Pick",
            criteria={"single": "Only one option"},
        )


def test_choice_question_rejects_more_than_16_criteria():
    """More than 16 criteria must raise."""
    criteria = {f"option_{i}": f"Option {i}" for i in range(17)}
    with pytest.raises(DecisionsError):
        ChoiceQuestion(
            instructions="Choose",
            criteria=criteria,
        )


def test_choice_question_rejects_empty_criteria_keys():
    """Empty strings in criteria keys must raise."""
    with pytest.raises(DecisionsError):
        ChoiceQuestion(
            instructions="Pick",
            criteria={"valid": "A description", "": "Empty key"},
        )


def test_choice_question_rejects_non_string_criteria_keys():
    """Non-string entries in criteria keys must raise."""
    with pytest.raises(DecisionsError):
        ChoiceQuestion(
            instructions="Pick",
            criteria={"valid": "A description", 42: "Non-string key"},
        )


def test_choice_question_rejects_blank_criteria_keys():
    """Whitespace-only criteria keys must raise."""
    with pytest.raises(DecisionsError):
        ChoiceQuestion(
            instructions="Pick",
            criteria={"valid": "A description", "  ": "Blank key"},
        )


def test_choice_question_rejects_empty_criteria_values():
    """Empty strings in criteria values must raise."""
    with pytest.raises(DecisionsError):
        ChoiceQuestion(
            instructions="Pick",
            criteria={"valid": "A description", "other": ""},
        )


def test_choice_question_rejects_blank_criteria_values():
    """Whitespace-only criteria values must raise."""
    with pytest.raises(DecisionsError):
        ChoiceQuestion(
            instructions="Pick",
            criteria={"valid": "A description", "other": "   "},
        )


def test_choice_question_rejects_non_string_criteria_values():
    """Non-string entries in criteria values must raise."""
    with pytest.raises(DecisionsError):
        ChoiceQuestion(
            instructions="Pick",
            criteria={"valid": "A description", "other": 42},
        )


def test_choice_question_to_dict():
    """Serialize to dict."""
    q = ChoiceQuestion(
        instructions="Pick the best language",
        criteria={
            "python": "Python programming language.",
            "rust": "Rust systems programming language.",
            "go": "Go concurrent programming language.",
        },
    )
    d = q.to_dict()
    assert d == {
        "type": "choice",
        "instructions": "Pick the best language",
        "criteria": {
            "python": "Python programming language.",
            "rust": "Rust systems programming language.",
            "go": "Go concurrent programming language.",
        },
    }


# ---- Mixed question sets with ChoiceQuestion ----

def test_request_serializes_choice_and_score_mixed():
    """A request can mix ChoiceQuestion with ScoreQuestion."""
    body = JEVRequest(
        state="context",
        model="test-model",
        questions={
            "ui_choice": ChoiceQuestion(
                instructions="Choose a UI framework",
                criteria={
                    "openwebui": "Open WebUI interface; ready-made chat experience.",
                    "chainlit": "Python-native conversational UI; fast to build.",
                    "gradio": "Rapid browser chatbot prototype; minimal setup.",
                },
            ),
            "performance": ScoreQuestion(
                instructions="Score performance",
                criteria=["speed", "memory"],
            ),
        },
    ).to_dict()

    assert body["questions"]["ui_choice"]["type"] == "choice"
    assert body["questions"]["ui_choice"]["criteria"] == {
        "openwebui": "Open WebUI interface; ready-made chat experience.",
        "chainlit": "Python-native conversational UI; fast to build.",
        "gradio": "Rapid browser chatbot prototype; minimal setup.",
    }
    assert body["questions"]["performance"]["type"] == "score"
    assert body["questions"]["performance"]["criteria"] == ["speed", "memory"]


# ---- Response parsing: arbitrary answer keys ----

def test_response_parses_generic_choice_answer():
    """A choice answer with any key (not just 'framework') is parsed."""
    response = JEVResponse.from_dict({
        "answers": {
            "ui_choice": {
                "type": "choice",
                "choice": "chainlit",
                "probabilities": {"chainlit": 0.6, "gradio": 0.4},
                "confidence": 0.85,
            }
        }
    })
    result = response.answers["ui_choice"]
    assert isinstance(result, ChoiceResult)
    assert result.choice == "chainlit"
    assert result.probabilities == {"chainlit": 0.6, "gradio": 0.4}


def test_response_parses_mixed_answer_types():
    """Response can contain choice, score, and noul answers together."""
    response = JEVResponse.from_dict({
        "answers": {
            "framework": {
                "type": "choice",
                "choice": "chainlit",
                "probabilities": {"chainlit": 0.7, "gradio": 0.3},
                "confidence": 0.92,
            },
            "quality": {
                "type": "score",
                "score": 8.5,
                "confidence": 0.80,
            },
            "risk": {
                "type": "noul",
                "noul": 0.25,
            },
            "db_choice": {
                "type": "choice",
                "choice": "postgres",
                "probabilities": {"postgres": 0.8, "sqlite": 0.2},
                "confidence": 0.88,
            },
        }
    })
    assert isinstance(response.answers["framework"], ChoiceResult)
    assert isinstance(response.answers["quality"], ScoreResult)
    assert isinstance(response.answers["risk"], NoulResult)  # noqa: F821
    assert isinstance(response.answers["db_choice"], ChoiceResult)


def test_response_accesses_arbitrary_choice_result():
    """Non-framework choice results are accessible without error."""
    response = JEVResponse.from_dict({
        "answers": {
            "db": {
                "type": "choice",
                "choice": "postgres",
                "probabilities": {"postgres": 0.9, "sqlite": 0.1},
                "confidence": 0.95,
            }
        }
    })
    result = response.answers["db"]
    assert isinstance(result, ChoiceResult)
    assert result.choice == "postgres"


# ---- Generic answer keys preserved ----

def test_response_preserves_arbitrary_answer_keys():
    """Any answer key in the response dict is preserved."""
    response = JEVResponse.from_dict({
        "answers": {
            "foo_bar": {
                "type": "score",
                "score": 42,
                "confidence": 0.75,
            },
            "baz_qux": {
                "type": "noul",
                "noul": 0.5,
            },
            "custom_choice": {
                "type": "choice",
                "choice": "yes",
                "probabilities": {"yes": 0.95, "no": 0.05},
                "confidence": 0.90,
            },
        }
    })
    assert "foo_bar" in response.answers
    assert "baz_qux" in response.answers
    assert "custom_choice" in response.answers
    assert response.answers["custom_choice"].choice == "yes"


# ---- Backwards compatibility: framework choiceQuestion defaults ----

def test_choice_type_is_choice():
    """ChoiceQuestion type is 'choice'."""
    q = ChoiceQuestion(instructions="pick", criteria={"a": "A", "b": "B"})
    assert q.type == "choice"


def test_score_type_remains_score():
    """ScoreQuestion type is 'score'."""
    q = ScoreQuestion(instructions="rate it", criteria=["a", "b"])
    assert q.type == "score"


# ---- ScoreQuestion validation ----

def test_score_question_accepts_2_criteria():
    """2 criteria (minimum) is accepted."""
    q = ScoreQuestion(
        instructions="Rate the code",
        criteria=["clarity", "depth"],
    )
    assert q.criteria == ["clarity", "depth"]


def test_score_question_accepts_16_criteria():
    """16 criteria (maximum) is accepted."""
    criteria = [f"rubric_{i}" for i in range(16)]
    q = ScoreQuestion(
        instructions="Score everything",
        criteria=criteria,
    )
    assert len(q.criteria) == 16


def test_score_question_rejects_1_criteria():
    """Fewer than 2 criteria must raise."""
    with pytest.raises(DecisionsError):
        ScoreQuestion(
            instructions="Rate",
            criteria=["single"],
        )


def test_score_question_rejects_17_criteria():
    """More than 16 criteria must raise."""
    criteria = [f"rubric_{i}" for i in range(17)]
    with pytest.raises(DecisionsError):
        ScoreQuestion(
            instructions="Score too many",
            criteria=criteria,
        )


def test_score_question_rejects_whitespace_rubric():
    """Whitespace-only rubric entries must raise."""
    with pytest.raises(DecisionsError):
        ScoreQuestion(
            instructions="Rate",
            criteria=["valid", "  "],
        )


def test_score_question_rejects_empty_rubric():
    """Empty rubric entries must raise."""
    with pytest.raises(DecisionsError):
        ScoreQuestion(
            instructions="Rate",
            criteria=["valid", ""],
        )


# ---- JEVRequest validation ----


def test_request_accepts_valid_state():
    """A non-blank state string is accepted."""
    req = JEVRequest(state="hello", model="test-model", questions={"q": NoulQuestion(instructions="Question")})
    assert req.state == "hello"


def test_request_rejects_blank_state():
    """Blank/whitespace-only state must raise."""
    with pytest.raises(DecisionsError):
        JEVRequest(state="   ", model="test-model", questions={"q": NoulQuestion(instructions="Question")})


def test_request_rejects_empty_state():
    """Empty state must raise."""
    with pytest.raises(DecisionsError):
        JEVRequest(state="", model="test-model", questions={"q": NoulQuestion(instructions="Question")})


def test_request_rejects_oversized_state():
    """State exceeding 8000 characters must raise."""
    with pytest.raises(DecisionsError):
        JEVRequest(state="x" * 8001, model="test-model", questions={"q": NoulQuestion(instructions="Question")})


def test_request_rejects_0_questions():
    """Zero questions must raise."""
    with pytest.raises(DecisionsError):
        JEVRequest(state="hello", model="test-model", questions={})


def test_request_accepts_8_questions():
    """8 questions (maximum) is accepted."""
    questions = {f"q{i}": NoulQuestion(instructions=f"Question {i}") for i in range(8)}
    req = JEVRequest(state="test", model="test-model", questions=questions)
    assert len(req.questions) == 8


def test_request_rejects_9_questions():
    """More than 8 questions must raise."""
    questions = {f"q{i}": NoulQuestion(instructions=f"Question {i}") for i in range(9)}
    with pytest.raises(DecisionsError):
        JEVRequest(state="test", model="test-model", questions=questions)


def test_request_rejects_invalid_question_key_with_space():
    """Question keys with spaces must raise."""
    with pytest.raises(DecisionsError):
        JEVRequest(
            state="hello",
            model="test-model",
            questions={"has space": NoulQuestion(instructions="bad key")},
        )


def test_request_rejects_invalid_question_key_starting_with_digit():
    """Question keys starting with a digit must raise."""
    with pytest.raises(DecisionsError):
        JEVRequest(
            state="hello",
            model="test-model",
            questions={"9x": NoulQuestion(instructions="bad key")},
        )


def test_request_rejects_question_with_blank_instructions():
    """Question with blank instructions must raise."""
    with pytest.raises(DecisionsError):
        JEVRequest(
            state="hello",
            model="test-model",
            questions={"good_key": NoulQuestion(instructions="")},
        )


def test_request_rejects_question_with_oversized_instructions():
    """Question with instructions exceeding 2000 characters must raise."""
    with pytest.raises(DecisionsError):
        JEVRequest(
            state="hello",
            model="test-model",
            questions={"good_key": NoulQuestion(instructions="x" * 2001)},
        )


def test_request_accepts_valid_question_keys():
    """Valid question keys (alphanumeric + underscore, starting with letter) are accepted."""
    req = JEVRequest(
        state="hello",
        model="test-model",
        questions={
            "framework": ChoiceQuestion(
                instructions="Choose a framework",
                criteria={"a": "A", "b": "B"},
            ),
            "q1_test": NoulQuestion(instructions="Question 1"),
            "q2": ScoreQuestion(instructions="Question 2", criteria=["a", "b"]),
            "a": NoulQuestion(instructions="Single char key"),
        },
    )
    assert set(req.questions.keys()) == {"framework", "q1_test", "q2", "a"}


# ---- NoulResult import check ----

def test_noul_result_is_available():
    """NoulResult should be importable from jev_bot.models."""
    from jev_bot.models import NoulResult
    r = NoulResult(noul=0.5)
    assert r.noul == 0.5
