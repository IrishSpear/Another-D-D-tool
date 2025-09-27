"""Custom error hierarchy for the DnDBank domain."""

from __future__ import annotations


class CharacterAlreadyExistsError(ValueError):
    """Raised when trying to register a duplicate adventurer."""


class CharacterNotFoundError(LookupError):
    """Raised when an unknown adventurer is requested."""


class InsufficientFundsError(RuntimeError):
    """Raised when an operation would drive an account negative."""
