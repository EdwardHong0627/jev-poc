"""Secure conversational CLI for the JEV Decisions API."""

from __future__ import annotations

import sys

from jev_bot.client import DecisionsClient
from jev_bot.config import Config, load_config
from jev_bot.errors import DecisionsError
from jev_bot.models import ChoiceResult
from jev_bot.service import JevBot


def render_result(result: ChoiceResult) -> None:
    print(f"Selected: {result.choice}")
    for name, prob in sorted(result.probabilities.items(), key=lambda kv: kv[1], reverse=True):
        print(f"  {name}: {prob}")


def build_bot(config: Config) -> JevBot:
    client = DecisionsClient(config)
    return JevBot(client)


def main() -> int:
    try:
        config = load_config()
    except (EnvironmentError, ValueError):
        print("Configuration error.", file=sys.stderr)
        return 1

    bot = build_bot(config)
    print("JEV assistant. Type 'quit' or 'exit' to leave.")
    try:
        while True:
            try:
                text = input("> ")
            except EOFError:
                print()
                break
            if text.strip().lower() in ("quit", "exit"):
                break
            if not text.strip():
                continue
            try:
                result = bot.message(text)
            except DecisionsError:
                print("Could not get a decision: request failed.")
                continue
            render_result(result)
        return 0
    finally:
        close = getattr(bot, "close", None)
        if callable(close):
            close()


if __name__ == "__main__":
    raise SystemExit(main())
