"""Public API surface: required exports importable from jev_bot."""

import jev_bot


def test_public_exports_importable():
    from jev_bot import (
        ChoiceQuestion,
        ChoiceResult,
        Config,
        DecisionsClient,
        DecisionsError,
        JEVRequest,
        JEVResponse,
        NoulQuestion,
        NoulResult,
        ScoreQuestion,
        ScoreResult,
    )

    assert Config is jev_bot.Config
    assert DecisionsClient is jev_bot.DecisionsClient
    assert ChoiceQuestion is jev_bot.ChoiceQuestion
    assert ChoiceResult is jev_bot.ChoiceResult
    assert DecisionsError is jev_bot.DecisionsError
    assert ScoreQuestion is jev_bot.ScoreQuestion
    assert NoulQuestion is jev_bot.NoulQuestion
    assert ScoreResult is jev_bot.ScoreResult
    assert NoulResult is jev_bot.NoulResult
    assert JEVRequest is jev_bot.JEVRequest
    assert JEVResponse is jev_bot.JEVResponse


def test_all_declares_public_exports():
    assert set(jev_bot.__all__) == {
        "ChoiceQuestion",
        "Config",
        "DecisionsClient",
        "ChoiceResult",
        "ScoreQuestion",
        "NoulQuestion",
        "ScoreResult",
        "NoulResult",
        "DecisionsError",
        "JEVRequest",
        "JEVResponse",
    }
