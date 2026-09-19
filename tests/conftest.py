"""Shared fixtures for CLI tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _set_test_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide a JEV_API_TOKEN for every test so install does not block."""
    monkeypatch.setenv("JEV_API_TOKEN", "test-token-for-tests")
