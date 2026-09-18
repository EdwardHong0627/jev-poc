"""Typed error for JEV Decisions API failures."""

from __future__ import annotations


class DecisionsError(Exception):
    """Raised when the Decisions API returns a malformed payload or fails."""
