"""Rounding helpers."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def round_to_5(amount: Decimal) -> int:
    """Round HALF UP to nearest 5. 88.6→90, 87→85, 87.5→90, 92.4→90."""
    if not isinstance(amount, Decimal):
        raise TypeError(f"round_to_5 requires Decimal, got {type(amount).__name__}")
    return int((amount / 5).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * 5)
