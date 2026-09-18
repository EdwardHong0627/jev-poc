"""Typed JEV request/response models for the exact Decisions contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import math

from jev_bot.errors import DecisionsError
from jev_bot.framework import (
    FRAMEWORK_CRITERIA,
    FRAMEWORK_INSTRUCTIONS,
    FRAMEWORK_TYPE,
    MODEL_ID,
)


@dataclass(frozen=True)
class FrameworkQuestion:
    type: str = FRAMEWORK_TYPE
    instructions: str = FRAMEWORK_INSTRUCTIONS
    criteria: dict[str, str] = field(default_factory=lambda: dict(FRAMEWORK_CRITERIA))

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "instructions": self.instructions,
            "criteria": dict(self.criteria),
        }


@dataclass(frozen=True)
class JEVRequest:
    state: str
    model: str = MODEL_ID
    questions: dict[str, FrameworkQuestion] = field(default_factory=lambda: {"framework": FrameworkQuestion()})

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "state": self.state,
            "questions": {k: v.to_dict() for k, v in self.questions.items()},
        }


@dataclass(frozen=True)
class ChoiceResult:
    choice: str
    probabilities: dict[str, float]


@dataclass(frozen=True)
class JEVResponse:
    answers: dict[str, ChoiceResult]

    @property
    def framework(self) -> ChoiceResult:
        return self.answers["framework"]

    @classmethod
    def from_dict(cls, payload: Any) -> "JEVResponse":
        if not isinstance(payload, dict):
            raise DecisionsError("Malformed Decisions payload: top-level object expected")
        answers = payload.get("answers")
        if not isinstance(answers, dict):
            raise DecisionsError("Malformed Decisions payload: 'answers' object expected")
        raw_fw = answers.get("framework")
        if not isinstance(raw_fw, dict):
            raise DecisionsError("Malformed Decisions payload: 'answers.framework' missing")
        choice = raw_fw.get("choice")
        if not isinstance(choice, str):
            raise DecisionsError("Malformed Decisions payload: 'answers.framework.choice' must be a string")
        probs = raw_fw.get("probabilities")
        if not isinstance(probs, dict):
            raise DecisionsError("Malformed Decisions payload: 'answers.framework.probabilities' missing")
        parsed: dict[str, float] = {}
        for key, value in probs.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise DecisionsError(
                    f"Malformed Decisions payload: probability for {key!r} must be numeric"
                )
            try:
                converted = float(value)
            except OverflowError as error:
                raise DecisionsError(
                    f"Malformed Decisions payload: probability for {key!r} must be finite"
                ) from error
            if not math.isfinite(converted):
                raise DecisionsError(
                    f"Malformed Decisions payload: probability for {key!r} must be finite"
                )
            parsed[key] = converted
        return cls(answers={"framework": ChoiceResult(choice=choice, probabilities=parsed)})
