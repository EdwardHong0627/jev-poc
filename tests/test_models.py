"""Behavior tests for the JEV contract model slice."""

from __future__ import annotations

import pytest

from jev_bot.errors import DecisionsError
from jev_bot.framework import (
    FRAMEWORK_CRITERIA,
    FRAMEWORK_INSTRUCTIONS,
    FRAMEWORK_TYPE,
    MODEL_ID,
)
from jev_bot.models import JEVRequest, JEVResponse


def test_request_payload_matches_exact_contract() -> None:
    body = JEVRequest(state="hello").to_dict()

    assert body["model"] == "~typesafe/jev-latest"
    assert body["model"] == MODEL_ID
    assert body["state"] == "hello"
    fw = body["questions"]["framework"]
    assert fw["type"] == "choice"
    assert fw["type"] == FRAMEWORK_TYPE
    assert fw["instructions"] == "Which framework should I follow?"
    assert fw["instructions"] == FRAMEWORK_INSTRUCTIONS
    assert fw["criteria"] == FRAMEWORK_CRITERIA
    assert set(fw["criteria"]) == {
        "custom",
        "openwebui",
        "chainlit",
        "gradio",
        "streamlit",
        "fastapi_react",
    }


def test_response_parses_choice_and_probabilities() -> None:
    payload = {
        "answers": {
            "framework": {
                "choice": "chainlit",
                "probabilities": {"chainlit": 0.7, "gradio": 0.3},
            }
        }
    }

    response = JEVResponse.from_dict(payload)

    assert response.framework.choice == "chainlit"
    assert response.framework.probabilities == {"chainlit": 0.7, "gradio": 0.3}


def test_response_rejects_missing_framework() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({"answers": {}})


def test_response_rejects_nonstring_choice() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict(
            {"answers": {"framework": {"choice": 42, "probabilities": {"a": 1.0}}}}
        )


def test_response_rejects_missing_probabilities() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict({"answers": {"framework": {"choice": "gradio"}}})


def test_response_rejects_nonnumeric_probabilities() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict(
            {"answers": {"framework": {"choice": "gradio", "probabilities": {"gradio": "high"}}}}
        )


def test_response_rejects_probability_that_cannot_be_converted_to_float() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict(
            {"answers": {"framework": {"choice": "gradio", "probabilities": {"gradio": 10**400}}}}
        )


def test_response_rejects_nan_probability() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict(
            {"answers": {"framework": {"choice": "gradio", "probabilities": {"gradio": float("nan")}}}}
        )


def test_response_rejects_positive_infinity_probability() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict(
            {"answers": {"framework": {"choice": "gradio", "probabilities": {"gradio": float("inf")}}}}
        )


def test_response_rejects_negative_infinity_probability() -> None:
    with pytest.raises(DecisionsError):
        JEVResponse.from_dict(
            {"answers": {"framework": {"choice": "gradio", "probabilities": {"gradio": float("-inf")}}}}
        )
