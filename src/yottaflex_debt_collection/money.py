"""Integer-cent money types and explicit decimal conversion helpers."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import NewType

MoneyCents = NewType("MoneyCents", int)


def as_cents(value: int) -> MoneyCents:
    """Validate an integer-cent value without accepting booleans or floats."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("money values must be integer cents")
    return MoneyCents(value)


def decimal_to_cents(value: Decimal | str) -> MoneyCents:
    """Convert a decimal currency amount to cents using half-up rounding."""
    if not isinstance(value, (Decimal, str)):
        raise TypeError("money conversion requires Decimal or str; float is not accepted")
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid decimal money amount: {value!r}") from exc
    if not amount.is_finite():
        raise ValueError("money amount must be finite")
    try:
        cents = (amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError(f"Money amount is outside the supported range: {value!r}") from exc
    return MoneyCents(int(cents))
