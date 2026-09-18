"""Behavior tests for the JEV contract model slice."""

from __future__ import annotations

import math
import pytest

from jev_bot.errors import DecisionsError
from jev_bot.models import (
    ChoiceQuestion,
    ChoiceResult,
    JEVRequest,
    JEVResponse,
    NoulQuestion,
    NoulResult,
    ScoreQuestion,
    ScoreResult,
)


# ── existing behaviour (must still pass) ──────────────────────────


def test_request_payload_matches_exact_contract() -> None:
    body = JEVRequest(
        state="hello",
        model="test-model",
        questions={
            "q1": ChoiceQuestion(
                instructions="Pick the best",
                criteria={"a": "Option A", "b": "Option B"},
            )
        },
    ).to_dict()

    assert body["model"] == "test-model"
    assert body["state"] == "hello"
    assert body["questions"]["q1"]["type"] == "choice"
    assert body["questions"]["q1"]["instructions"] == "Pick the best"
    assert body["questions"]["q1"]["criteria"] == {"a": "Option A", "b": "Option B"}


def test_response_parses_choice_and_probabilities() -> None:
    payload = {
        "answers": {
            "ui_choice": {
                "type": "choice",
                "choice": "chainlit",
                "probabilities": {"chainlit": 0.7, "gradio": 0.3},
                "confidence": 0.8,
            }
        }
    }

    response = JEVResponse.from_dict(payload)

    assert response.answers["ui_choice"].choice == "chainlit"
    assert response.answers["ui_choice"].probabilities == {"chainlit": 0.7, "gradio": 0.3}


def test_response_rejects_missing_answer_key() -> None:
    """Accessing an absent answer key raises KeyError."""
    response = JEVResponse.from_dict({
        "answers": {"other": {"type": "score", "score": 1.0, "confidence": 0.5}}
    })
    with pytest.raises(KeyError):
        _ = response.answers["framework"]


def test_response_rejects_nonstring_choice() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict(
            {"answers": {"q1": {"type": "choice", "choice": 42, "probabilities": {"a": 1.0}, "confidence": 0.5}}}
        )


def test_response_rejects_missing_probabilities() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({"answers": {"q1": {"type": "choice", "choice": "gradio", "confidence": 0.5}}})


def test_response_rejects_nonnumeric_probabilities() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict(
            {"answers": {"q1": {"type": "choice", "choice": "gradio", "probabilities": {"gradio": "high"}, "confidence": 0.5}}}
        )


def test_response_rejects_probability_that_cannot_be_converted_to_float() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict(
            {"answers": {"q1": {"type": "choice", "choice": "gradio", "probabilities": {"gradio": 10**400}, "confidence": 0.5}}}
        )


def test_response_rejects_nan_probability() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict(
            {"answers": {"q1": {"type": "choice", "choice": "gradio", "probabilities": {"gradio": float("nan")}, "confidence": 0.5}}}
        )


def test_response_rejects_positive_infinity_probability() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict(
            {"answers": {"q1": {"type": "choice", "choice": "gradio", "probabilities": {"gradio": float("inf")}, "confidence": 0.5}}}
        )


def test_response_rejects_negative_infinity_probability() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict(
            {"answers": {"q1": {"type": "choice", "choice": "gradio", "probabilities": {"gradio": float("-inf")}, "confidence": 0.5}}}
        )


def test_request_serializes_mixed_question_types_exactly() -> None:
    body = JEVRequest(
        state="hello",
        model="test-model",
        questions={
            "framework": ChoiceQuestion(
                instructions="Which framework?",
                criteria={"a": "A", "b": "B"},
            ),
            "quality": ScoreQuestion(
                instructions="Rate it", criteria=["clarity", "depth"]
            ),
            "risk": NoulQuestion(instructions="How risky?"),
        },
    ).to_dict()

    assert body["questions"]["framework"] == {
        "type": "choice",
        "instructions": "Which framework?",
        "criteria": {"a": "A", "b": "B"},
    }
    assert body["questions"]["quality"] == {
        "type": "score",
        "instructions": "Rate it",
        "criteria": ["clarity", "depth"],
    }
    assert body["questions"]["risk"] == {"type": "noul", "instructions": "How risky?"}


def test_response_parses_score_result() -> None:
    response = JEVResponse.from_dict({"answers": {"quality": {"type": "score", "score": 8.5, "confidence": 0.9}}})
    assert response.answers["quality"].score == 8.5


def test_response_parses_noul_result() -> None:
    response = JEVResponse.from_dict({"answers": {"risk": {"type": "noul", "noul": 0.25}}})
    assert response.answers["risk"].noul == 0.25


def test_response_rejects_nonfinite_score() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({"answers": {"quality": {"type": "score", "score": float("nan"), "confidence": 0.5}}})
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({"answers": {"quality": {"type": "score", "score": "high", "confidence": 0.5}}})


def test_response_rejects_bad_noul() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({"answers": {"risk": {"type": "noul", "noul": 1.5}}})
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({"answers": {"risk": {"type": "noul", "noul": "low"}}})
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({"answers": {"risk": {"type": "noul", "noul": float("nan")}}})


# ── NEW: state accepts JSON-compatible string / object / array ─────


def test_request_accepts_string_state() -> None:
    req = JEVRequest(state="hello world", model="m", questions={"q": NoulQuestion(instructions="Question")})
    assert req.state == "hello world"


def test_request_accepts_dict_state() -> None:
    req = JEVRequest(state={"key": "value", "nested": {"a": 1}}, model="m", questions={"q": NoulQuestion(instructions="Question")})
    assert req.state == {"key": "value", "nested": {"a": 1}}


def test_request_accepts_list_state() -> None:
    req = JEVRequest(state=["item1", "item2"], model="m", questions={"q": NoulQuestion(instructions="Question")})
    assert req.state == ["item1", "item2"]


def test_request_accepts_nested_json_state() -> None:
    req = JEVRequest(state={"list": [1, 2, 3], "null": None, "bool": True}, model="m", questions={"q": NoulQuestion(instructions="Question")})
    assert req.state == {"list": [1, 2, 3], "null": None, "bool": True}


def test_request_rejects_integer_state() -> None:
    with pytest.raises(DecisionsError):
        JEVRequest(state=42, model="m", questions={"q": NoulQuestion(instructions="Question")})


def test_request_rejects_float_state() -> None:
    with pytest.raises(DecisionsError):
        JEVRequest(state=3.14, model="m", questions={"q": NoulQuestion(instructions="Question")})


def test_request_rejects_bool_state() -> None:
    with pytest.raises(DecisionsError):
        JEVRequest(state=True, model="m", questions={"q": NoulQuestion(instructions="Question")})


def test_request_serializes_dict_state_in_payload() -> None:
    body = JEVRequest(state={"state": "value"}, model="m", questions={"q": NoulQuestion(instructions="Question")}).to_dict()
    assert body["state"] == {"state": "value"}


def test_request_serializes_list_state_in_payload() -> None:
    body = JEVRequest(state=[1, "two"], model="m", questions={"q": NoulQuestion(instructions="Question")}).to_dict()
    assert body["state"] == [1, "two"]


# ── NEW: NoulQuestion supports optional criteria (true/false descriptions) ─


def test_noul_question_without_criteria() -> None:
    q = NoulQuestion(instructions="How risky?")
    assert q.type == "noul"
    assert q.instructions == "How risky?"
    assert q.to_dict() == {"type": "noul", "instructions": "How risky?"}


def test_noul_question_with_criteria_dict() -> None:
    q = NoulQuestion(
        instructions="Rate risk",
        criteria={"low": "Low risk", "high": "High risk"},
    )
    assert q.type == "noul"
    assert q.criteria == {"low": "Low risk", "high": "High risk"}
    d = q.to_dict()
    assert d["type"] == "noul"
    assert d["criteria"] == {"low": "Low risk", "high": "High risk"}


def test_noul_question_rejects_empty_criteria() -> None:
    with pytest.raises(DecisionsError):
        NoulQuestion(instructions="rate", criteria={})


def test_noul_question_rejects_criteria_exceeding_max() -> None:
    with pytest.raises(DecisionsError):
        NoulQuestion(instructions="rate", criteria={str(i): f"desc{i}" for i in range(17)})


def test_noul_question_rejects_non_string_criteria_keys() -> None:
    with pytest.raises(DecisionsError):
        NoulQuestion(instructions="rate", criteria={1: "one"})


def test_noul_question_rejects_blank_criteria_values() -> None:
    with pytest.raises(DecisionsError):
        NoulQuestion(instructions="rate", criteria={"key": ""})


# ── NEW: answer type field is required and validated ────────────────


def test_response_requires_answer_type() -> None:
    """An answer dict must contain a 'type' key."""
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({
            "answers": {"q1": {
                "choice": "chainlit",
                "probabilities": {"chainlit": 1.0},
            }}
        })


def test_response_rejects_wrong_type_value() -> None:
    """A 'type' field must be a string."""
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({
            "answers": {"q1": {
                "type": 123,
                "choice": "chainlit",
                "probabilities": {"chainlit": 1.0},
            }}
        })


def test_response_rejects_null_type() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({
            "answers": {"q1": {
                "type": None,
                "choice": "chainlit",
                "probabilities": {"chainlit": 1.0},
            }}
        })


def test_response_rejects_choice_without_type() -> None:
    """choice-only answer without 'type' is rejected."""
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({
            "answers": {"q1": {
                "choice": "chainlit",
                "probabilities": {"chainlit": 1.0},
            }}
        })


# ── NEW: confidence required/validated on choice/score (finite [0,1]) ─


def test_choice_requires_confidence() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({
            "answers": {"q1": {
                "type": "choice",
                "choice": "chainlit",
                "probabilities": {"chainlit": 1.0},
            }}
        })


def test_score_requires_confidence() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({
            "answers": {"quality": {
                "type": "score",
                "score": 8.5,
            }}
        })


def test_choice_accepts_confidence() -> None:
    response = JEVResponse.from_dict({
        "answers": {"q1": {
            "type": "choice",
            "choice": "chainlit",
            "probabilities": {"chainlit": 0.7, "gradio": 0.3},
            "confidence": 0.85,
        }}
    })
    assert response.answers["q1"].confidence == 0.85


def test_score_accepts_confidence() -> None:
    response = JEVResponse.from_dict({
        "answers": {"quality": {
            "type": "score",
            "score": 8.5,
            "confidence": 0.9,
        }}
    })
    assert response.answers["quality"].confidence == 0.9


def test_confidence_rejects_nan() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({
            "answers": {"q1": {
                "type": "choice",
                "choice": "chainlit",
                "probabilities": {"chainlit": 1.0},
                "confidence": float("nan"),
            }}
        })


def test_confidence_rejects_infinity() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({
            "answers": {"q1": {
                "type": "choice",
                "choice": "chainlit",
                "probabilities": {"chainlit": 1.0},
                "confidence": float("inf"),
            }}
        })


def test_confidence_rejects_negative() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({
            "answers": {"q1": {
                "type": "choice",
                "choice": "chainlit",
                "probabilities": {"chainlit": 1.0},
                "confidence": -0.1,
            }}
        })


def test_confidence_rejects_above_one() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({
            "answers": {"q1": {
                "type": "choice",
                "choice": "chainlit",
                "probabilities": {"chainlit": 1.0},
                "confidence": 1.01,
            }}
        })


def test_confidence_accepts_boundary_zero() -> None:
    response = JEVResponse.from_dict({
        "answers": {"q1": {
            "type": "choice",
            "choice": "chainlit",
            "probabilities": {"chainlit": 1.0},
            "confidence": 0.0,
        }}
    })
    assert response.answers["q1"].confidence == 0.0


def test_confidence_accepts_boundary_one() -> None:
    response = JEVResponse.from_dict({
        "answers": {"q1": {
            "type": "choice",
            "choice": "chainlit",
            "probabilities": {"chainlit": 1.0},
            "confidence": 1.0,
        }}
    })
    assert response.answers["q1"].confidence == 1.0


def test_confidence_rejects_non_numeric() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({
            "answers": {"q1": {
                "type": "choice",
                "choice": "chainlit",
                "probabilities": {"chainlit": 1.0},
                "confidence": "high",
            }}
        })


# ── NEW: top-level metadata (model, id, usage, provider) ───────────


def test_response_parses_model_field() -> None:
    response = JEVResponse.from_dict({
        "model": "test-model",
        "id": "dec_abc123",
        "answers": {"q1": {
            "type": "choice",
            "choice": "chainlit",
            "probabilities": {"chainlit": 1.0},
            "confidence": 0.9,
        }},
    })
    assert response.model == "test-model"


def test_response_parses_id_field() -> None:
    response = JEVResponse.from_dict({
        "id": "dec_xyz789",
        "answers": {"q1": {
            "type": "choice",
            "choice": "chainlit",
            "probabilities": {"chainlit": 1.0},
            "confidence": 0.9,
        }},
    })
    assert response.id == "dec_xyz789"


def test_response_parses_usage_field() -> None:
    response = JEVResponse.from_dict({
        "usage": {"prompt_tokens": 10, "completion_tokens": 50},
        "answers": {"q1": {
            "type": "choice",
            "choice": "chainlit",
            "probabilities": {"chainlit": 1.0},
            "confidence": 0.9,
        }},
    })
    assert response.usage == {"prompt_tokens": 10, "completion_tokens": 50}


def test_response_parses_provider_field() -> None:
    response = JEVResponse.from_dict({
        "provider": {"openrouter": {"id": "openai/gpt-4"}},
        "answers": {"q1": {
            "type": "choice",
            "choice": "chainlit",
            "probabilities": {"chainlit": 1.0},
            "confidence": 0.9,
        }},
    })
    assert response.provider == {"openrouter": {"id": "openai/gpt-4"}}


def test_response_parses_all_metadata_together() -> None:
    response = JEVResponse.from_dict({
        "model": "test-model",
        "id": "dec_001",
        "usage": {"prompt_tokens": 100, "completion_tokens": 200},
        "provider": {"openrouter": {}},
        "answers": {"q1": {
            "type": "choice",
            "choice": "chainlit",
            "probabilities": {"chainlit": 1.0},
            "confidence": 0.95,
        }},
    })
    assert response.model == "test-model"
    assert response.id == "dec_001"
    assert response.usage == {"prompt_tokens": 100, "completion_tokens": 200}
    assert response.provider == {"openrouter": {}}


def test_response_rejects_non_string_id() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({
            "id": 12345,
            "answers": {"q1": {
                "type": "choice",
                "choice": "chainlit",
                "probabilities": {"chainlit": 1.0},
                "confidence": 0.9,
            }},
        })


def test_response_rejects_non_dict_usage() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({
            "usage": "should be dict",
            "answers": {"q1": {
                "type": "choice",
                "choice": "chainlit",
                "probabilities": {"chainlit": 1.0},
                "confidence": 0.9,
            }},
        })


def test_response_rejects_non_dict_provider() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({
            "provider": 42,
            "answers": {"q1": {
                "type": "choice",
                "choice": "chainlit",
                "probabilities": {"chainlit": 1.0},
                "confidence": 0.9,
            }},
        })


def test_response_accepts_string_provider_from_openrouter() -> None:
    """OpenRouter returns provider as a string; this must be accepted."""
    response = JEVResponse.from_dict({
        "provider": "OpenRouter",
        "answers": {"q1": {
            "type": "choice",
            "choice": "chainlit",
            "probabilities": {"chainlit": 1.0},
            "confidence": 0.9,
        }},
    })
    assert response.provider == "OpenRouter"


def test_response_rejects_non_string_model() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({
            "model": 42,
            "answers": {"q1": {
                "type": "choice",
                "choice": "chainlit",
                "probabilities": {"chainlit": 1.0},
                "confidence": 0.9,
            }},
        })


# ── NEW: ChoiceResult / ScoreResult / NoulResult expose confidence ──


def test_choice_result_has_confidence_attr() -> None:
    response = JEVResponse.from_dict({
        "answers": {"q1": {
            "type": "choice",
            "choice": "chainlit",
            "probabilities": {"chainlit": 1.0},
            "confidence": 0.85,
        }}
    })
    assert isinstance(response.answers["q1"].confidence, float)


def test_score_result_has_confidence_attr() -> None:
    response = JEVResponse.from_dict({
        "answers": {"quality": {
            "type": "score",
            "score": 8.5,
            "confidence": 0.9,
        }}
    })
    assert isinstance(response.answers["quality"].confidence, float)


# ── NEW: NoulResult has optional confidence (noul type doesn't require it) ─


def test_noul_result_without_confidence() -> None:
    response = JEVResponse.from_dict({
        "answers": {"risk": {
            "type": "noul",
            "noul": 0.25,
        }}
    })
    assert response.answers["risk"].noul == 0.25


def test_noul_result_with_confidence() -> None:
    response = JEVResponse.from_dict({
        "answers": {"risk": {
            "type": "noul",
            "noul": 0.25,
            "confidence": 0.7,
        }}
    })
    assert response.answers["risk"].noul == 0.25
    assert response.answers["risk"].confidence == 0.7


def test_noul_result_rejects_bad_confidence() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({
            "answers": {"risk": {
                "type": "noul",
                "noul": 0.25,
                "confidence": 2.0,
            }}
        })


# ── NEW: JEVResponse preserves optional metadata ───────────────────


def test_response_defaults_metadata_to_none_when_absent() -> None:
    response = JEVResponse.from_dict({
        "answers": {"q1": {
            "type": "choice",
            "choice": "chainlit",
            "probabilities": {"chainlit": 1.0},
            "confidence": 0.9,
        }},
    })
    assert response.model is None
    assert response.id is None
    assert response.usage is None
    assert response.provider is None


def test_jev_response_attributes() -> None:
    response = JEVResponse.from_dict({
        "model": "test-model",
        "id": "test-id",
        "usage": {"tokens": 10},
        "provider": {"name": "test"},
        "answers": {"q1": {
            "type": "choice",
            "choice": "chainlit",
            "probabilities": {"chainlit": 1.0},
            "confidence": 0.5,
        }},
    })
    assert response.model == "test-model"
    assert response.id == "test-id"
    assert response.usage == {"tokens": 10}
    assert response.provider == {"name": "test"}


# ── NEW: score result with confidence ──────────────────────────────


def test_score_result_extra_keeps_other_keys() -> None:
    response = JEVResponse.from_dict({
        "answers": {"quality": {
            "type": "score",
            "score": 8.5,
            "confidence": 0.9,
            "notes": "good",
        }}
    })
    assert response.answers["quality"].score == 8.5
    assert response.answers["quality"].extra == {"notes": "good"}


# ── NEW: confidence on choice probabilities still validated ────────


def test_choice_with_valid_confidence_and_probs() -> None:
    response = JEVResponse.from_dict({
        "answers": {"q1": {
            "type": "choice",
            "choice": "gradio",
            "probabilities": {"gradio": 0.6, "chainlit": 0.4},
            "confidence": 0.75,
        }}
    })
    assert response.answers["q1"].choice == "gradio"
    assert response.answers["q1"].confidence == 0.75
    assert response.answers["q1"].probabilities == {"gradio": 0.6, "chainlit": 0.4}


# ── NEW: JEVRequest model is required ──────────────────────────────


def test_request_requires_model() -> None:
    """model is a required field with no default."""
    with pytest.raises(TypeError):
        JEVRequest(state="hello")


def test_request_with_model() -> None:
    req = JEVRequest(state="hello", model="my-model", questions={"q": NoulQuestion(instructions="Question")})
    assert req.model == "my-model"


# ── NEW: Questions is non-empty and required ───────────────────────


def test_request_rejects_no_questions() -> None:
    """Zero questions must raise."""
    with pytest.raises(DecisionsError):
        JEVRequest(state="hello", model="m", questions={})


def test_request_rejects_0_questions() -> None:
    """Zero questions must raise (alias test)."""
    with pytest.raises(DecisionsError):
        JEVRequest(state="hello", model="m")


# ── Mixed answer types ─────────────────────────────────────────────


def test_response_parses_mixed_answer_types() -> None:
    """Response can contain choice, score, and noul answers together."""
    response = JEVResponse.from_dict({
        "answers": {
            "ui_choice": {
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
    assert isinstance(response.answers["ui_choice"], ChoiceResult)
    assert isinstance(response.answers["quality"], ScoreResult)
    assert isinstance(response.answers["risk"], NoulResult)  # noqa: F821
    assert isinstance(response.answers["db_choice"], ChoiceResult)


def test_response_preserves_arbitrary_answer_keys() -> None:
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


def test_response_accesses_arbitrary_choice_result() -> None:
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
