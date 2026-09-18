"""Public API surface: required exports importable from jev_bot."""

import jev_bot


def test_public_exports_importable():
    from jev_bot import ChoiceResult, Config, DecisionsClient, DecisionsError, JevBot

    assert Config is jev_bot.Config
    assert DecisionsClient is jev_bot.DecisionsClient
    assert JevBot is jev_bot.JevBot
    assert ChoiceResult is jev_bot.ChoiceResult
    assert DecisionsError is jev_bot.DecisionsError


def test_all_declares_public_exports():
    assert set(jev_bot.__all__) == {
        "Config",
        "DecisionsClient",
        "JevBot",
        "ChoiceResult",
        "DecisionsError",
    }
