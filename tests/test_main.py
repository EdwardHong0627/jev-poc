"""Tests for the secure conversational CLI (main.py)."""

from __future__ import annotations

import pytest

from jev_bot.errors import DecisionsError
from jev_bot.models import ChoiceResult

import main


def make_result():
    return ChoiceResult(choice="openwebui", probabilities={"Customize": 0.2, "openwebui": 0.8})


def test_render_result_sorts_descending(capsys):
    main.render_result(make_result())
    out = capsys.readouterr().out
    assert "openwebui" in out
    assert out.index("openwebui: 0.8") < out.index("Customize: 0.2")


def test_main_missing_config(monkeypatch, capsys):
    monkeypatch.setattr(main, "load_config", lambda: (_ for _ in ()).throw(EnvironmentError("JEV_API_TOKEN environment variable is required")))
    assert main.main() == 1
    err = capsys.readouterr().err
    assert err == "Configuration error.\n"



def test_main_invalid_config_is_safe(monkeypatch, capsys):
    monkeypatch.setattr(
        main,
        "load_config",
        lambda: (_ for _ in ()).throw(ValueError("invalid endpoint: https://bad.example")),
    )

    assert main.main() == 1

    assert "https://bad.example" not in capsys.readouterr().err

def test_main_skips_blank_input(monkeypatch, capsys):
    bot_calls = []

    class FakeBot:
        def message(self, text):
            bot_calls.append(text)
            return make_result()

    monkeypatch.setattr(main, "build_bot", lambda config: FakeBot())
    monkeypatch.setattr(main, "load_config", lambda: object())
    inputs = iter(["   ", "quit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    assert main.main() == 0
    assert bot_calls == []


def test_main_message_then_quit(monkeypatch, capsys):
    class FakeBot:
        def message(self, text):
            assert text == "hello"
            return make_result()

    monkeypatch.setattr(main, "build_bot", lambda config: FakeBot())
    monkeypatch.setattr(main, "load_config", lambda: object())
    inputs = iter(["hello", "quit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    assert main.main() == 0
    out = capsys.readouterr().out
    assert "openwebui" in out


def test_main_decisions_error_safe_output(monkeypatch, capsys):
    class FakeBot:
        def message(self, text):
            raise DecisionsError("Decisions request failed with status 500: Bearer secret-token-xyz")

    monkeypatch.setattr(main, "build_bot", lambda config: FakeBot())
    monkeypatch.setattr(main, "load_config", lambda: object())
    inputs = iter(["hello", "quit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    assert main.main() == 0
    out = capsys.readouterr().out
    assert "secret-token-xyz" not in out
    assert "Could not get a decision" in out or "failed" in out.lower()


def test_main_closes_bot_on_exit(monkeypatch):
    class FakeBot:
        closed = False

        def close(self):
            self.closed = True

    bot = FakeBot()
    monkeypatch.setattr(main, "build_bot", lambda config: bot)
    monkeypatch.setattr(main, "load_config", lambda: object())
    inputs = iter(["quit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    assert main.main() == 0
    assert bot.closed
