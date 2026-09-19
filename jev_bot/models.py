"""Typed JEV request/response models for the exact Decisions contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import math

from jev_bot.errors import DecisionsError


@dataclass(frozen=True)
class ChoiceQuestion:
    instructions: str
    criteria: dict[str, str]
    type: str = "choice"

    def __post_init__(self) -> None:
        if not self.criteria or len(self.criteria) < 2 or len(self.criteria) > 16:
            raise DecisionsError("ChoiceQuestion requires between 2 and 16 criteria")
        for key, desc in self.criteria.items():
            if not isinstance(key, str) or not key.strip():
                raise DecisionsError("ChoiceQuestion criteria keys must be non-empty strings")
            if not isinstance(desc, str) or not desc.strip():
                raise DecisionsError("ChoiceQuestion criteria values must be non-empty strings")

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "instructions": self.instructions,
            "criteria": dict(self.criteria),
        }


@dataclass(frozen=True)
class ScoreQuestion:
    instructions: str
    criteria: list[str]
    type: str = "score"

    def __post_init__(self) -> None:
        if not self.criteria or len(self.criteria) < 2 or len(self.criteria) > 16:
            raise DecisionsError("ScoreQuestion requires between 2 and 16 criteria")
        if any(not isinstance(c, str) or not c.strip() for c in self.criteria):
            raise DecisionsError("ScoreQuestion criteria must be a non-empty list of non-blank strings")

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "instructions": self.instructions,
            "criteria": list(self.criteria),
        }


@dataclass(frozen=True)
class NoulQuestion:
    instructions: str
    type: str = "noul"

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "instructions": self.instructions}


Question = ChoiceQuestion | ScoreQuestion | NoulQuestion


@dataclass(frozen=True)
class JEVRequest:
    state: str | dict[str, Any] | list[Any]
    model: str
    questions: dict[str, Question] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Accept only string, dict, or list; reject bool/int/float/None.
        if isinstance(self.state, bool) or self.state is None:
            raise DecisionsError("JEVRequest state must be a non-blank string, dict, or list")
        if not isinstance(self.state, (str, dict, list)):
            raise DecisionsError("JEVRequest state must be a non-blank string, dict, or list")
        if isinstance(self.state, str):
            if not self.state.strip():
                raise DecisionsError("JEVRequest state must be a non-blank string")
            if len(self.state) > 8000:
                raise DecisionsError("JEVRequest state exceeds 8000 characters")
        # dict/list are accepted as-is.

        if not 1 <= len(self.questions) <= 8:
            raise DecisionsError("JEVRequest requires between 1 and 8 questions")
        _key_pattern = __import__("re").compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
        for name, q in self.questions.items():
            if not _key_pattern.match(name):
                raise DecisionsError(f"Invalid question key {name!r}")
            if not q.instructions.strip():
                raise DecisionsError(f"Question {name!r} instructions must be non-blank")
            if len(q.instructions) > 2000:
                raise DecisionsError(f"Question {name!r} instructions exceed 2000 characters")

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
    confidence: float


@dataclass(frozen=True)
class ScoreResult:
    score: float
    confidence: float
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NoulResult:
    noul: float
    confidence: float | None = None


Answer = ChoiceResult | ScoreResult | NoulResult


def _to_finite_float(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DecisionsError(f"Malformed Decisions payload: {label} must be numeric")
    try:
        converted = float(value)
    except OverflowError as error:
        raise DecisionsError(f"Malformed Decisions payload: {label} must be finite") from error
    if not math.isfinite(converted):
        raise DecisionsError(f"Malformed Decisions payload: {label} must be finite")
    return converted


def _to_confidence(value: Any, label: str) -> float:
    """Parse a confidence value: finite float in [0, 1]."""
    f = _to_finite_float(value, label)
    if not 0.0 <= f <= 1.0:
        raise DecisionsError(
            f"Malformed Decisions payload: {label} must be in [0, 1]"
        )
    return f


def _parse_choice(raw: dict[str, Any], name: str) -> ChoiceResult:
    choice = raw.get("choice")
    if not isinstance(choice, str):
        raise DecisionsError(
            f"Malformed Decisions payload: 'answers.{name}.choice' must be a string"
        )
    probs = raw.get("probabilities")
    if not isinstance(probs, dict):
        raise DecisionsError(
            f"Malformed Decisions payload: 'answers.{name}.probabilities' missing"
        )
    parsed: dict[str, float] = {}
    for key, value in probs.items():
        parsed[key] = _to_finite_float(value, f"probability for {key!r}")
    if "confidence" not in raw:
        raise DecisionsError(
            f"Malformed Decisions payload: 'answers.{name}.confidence' is required"
        )
    confidence = _to_confidence(raw["confidence"], f"'answers.{name}.confidence'")
    return ChoiceResult(choice=choice, probabilities=parsed, confidence=confidence)


def _parse_answer(name: str, raw: Any) -> Answer:
    if not isinstance(raw, dict):
        raise DecisionsError(f"Malformed Decisions payload: 'answers.{name}' missing")

    # Required 'type' field
    answer_type = raw.get("type")
    if not isinstance(answer_type, str):
        raise DecisionsError(
            f"Malformed Decisions payload: 'answers.{name}.type' must be a string"
        )

    if "choice" in raw:
        return _parse_choice(raw, name)
    if "score" in raw:
        if "confidence" not in raw:
            raise DecisionsError(
                f"Malformed Decisions payload: 'answers.{name}.confidence' is required"
            )
        score = _to_finite_float(raw["score"], f"'answers.{name}.score'")
        confidence = _to_confidence(raw["confidence"], f"'answers.{name}.confidence'")
        extra = {k: v for k, v in raw.items() if k not in ("score", "confidence", "type")}
        return ScoreResult(score=score, extra=extra, confidence=confidence)
    if "noul" in raw:
        noul = _to_finite_float(raw["noul"], f"'answers.{name}.noul'")
        if not 0.0 <= noul <= 1.0:
            raise DecisionsError(
                f"Malformed Decisions payload: 'answers.{name}.noul' must be in [0, 1]"
            )
        confidence: float | None = None
        if "confidence" in raw:
            confidence = _to_confidence(raw["confidence"], f"'answers.{name}.confidence'")
        return NoulResult(noul=noul, confidence=confidence)
    raise DecisionsError(f"Malformed Decisions payload: 'answers.{name}' has no known result")


@dataclass(frozen=True)
class JEVResponse:
    answers: dict[str, Answer]
    model: str | None = None
    id: str | None = None
    usage: dict[str, Any] | None = None
    provider: str | dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, payload: Any) -> "JEVResponse":
        if not isinstance(payload, dict):
            raise DecisionsError("Malformed Decisions payload: top-level object expected")
        answers = payload.get("answers")
        if not isinstance(answers, dict):
            raise DecisionsError("Malformed Decisions payload: 'answers' object expected")

        # Validate optional metadata fields
        model = payload.get("model")
        if model is not None and not isinstance(model, str):
            raise DecisionsError("Malformed Decisions payload: 'model' must be a string")

        id_val = payload.get("id")
        if id_val is not None and not isinstance(id_val, str):
            raise DecisionsError("Malformed Decisions payload: 'id' must be a string")

        usage = payload.get("usage")
        if usage is not None and not isinstance(usage, dict):
            raise DecisionsError("Malformed Decisions payload: 'usage' must be an object")

        provider = payload.get("provider")
        if provider is not None and not isinstance(provider, (str, dict)):
            raise DecisionsError("Malformed Decisions payload: 'provider' must be a string or object")

        return cls(
            model=model,
            id=id_val,
            usage=usage,
            provider=provider,
            answers={k: _parse_answer(k, v) for k, v in answers.items()},
        )
