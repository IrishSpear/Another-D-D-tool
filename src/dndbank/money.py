"""Helpers for working with monetary values in gold pieces."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Union

AmountLike = Union[Decimal, int, float, str]


_TWO_PLACES = Decimal("0.01")


def to_decimal(value: AmountLike) -> Decimal:
    """Convert a loose gold piece value into a two-decimal Decimal."""

    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, float)):
        result = Decimal(str(value))
    elif isinstance(value, str):
        result = Decimal(value)
    else:
        raise TypeError(f"Unsupported amount type: {type(value)!r}")

    return result.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def require_positive(value: Decimal, *, allow_zero: bool = False) -> None:
    """Ensure an amount is positive (or optionally zero)."""

    if allow_zero:
        if value < Decimal("0"):
            raise ValueError("Amount must be zero or greater.")
    else:
        if value <= Decimal("0"):
            raise ValueError("Amount must be greater than zero.")


def format_gp(value: AmountLike) -> str:
    """Render a gold piece amount as a string."""

    dec_value = to_decimal(value)
    normalized = dec_value.quantize(_TWO_PLACES)
    return f"{normalized} gp"
