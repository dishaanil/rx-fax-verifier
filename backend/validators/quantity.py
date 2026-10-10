"""Quantity / SIG arithmetic (DESIGN.md §11).

`dose` is dispensing units per administration (tablets, capsules, mL) —
never medication strength. Returns None whenever the arithmetic is not
deterministic. Never alters the stated quantity.

Callers resolve `days` as: explicit days_supply if parseable, else
NormalizedSig.days, else skip.
"""

import math

from backend.models import Signal, SignalStatus
from backend.references.sig_vocabulary import FREQUENCY_PER_DAY

SIGNAL_TYPE = "QUANTITY_SIG"

_COUNT_UNITS = {"TAB", "CAP"}
_UNIT_ALIASES = {
    "tab": "TAB", "tabs": "TAB", "tablet": "TAB", "tablets": "TAB",
    "cap": "CAP", "caps": "CAP", "capsule": "CAP", "capsules": "CAP",
    "ml": "ML",
}


def validate_quantity(
    dose: float | None,
    dose_unit: str | None,
    frequency_token: str | None,
    days: int | None,
    stated_qty: float | None,
    quantity_unit: str | None = None,
    as_needed: bool = False,
) -> Signal | None:
    if as_needed or stated_qty is None:
        return None
    expected = implied_quantity(dose, frequency_token, days)
    if expected is None:
        return None
    if not _units_compatible(dose_unit, quantity_unit):
        return None

    implied_text = format_quantity(expected, dose_unit)
    stated_text = format_quantity(stated_qty, dose_unit)
    if math.isclose(expected, stated_qty):
        return Signal(
            type=SIGNAL_TYPE,
            status=SignalStatus.PASS,
            detail=f"Directions imply {implied_text}; prescription states {stated_text}.",
        )
    return Signal(
        type=SIGNAL_TYPE,
        status=SignalStatus.FAIL,
        detail=f"Directions imply {implied_text} but prescription states {stated_text}.",
    )


def implied_quantity(dose: float | None, frequency_token: str | None, days: int | None) -> float | None:
    """dose x frequency/day x days, or None when any input is missing or unsupported."""
    per_day = FREQUENCY_PER_DAY.get(frequency_token) if frequency_token else None
    if dose is None or days is None or per_day is None:
        return None
    return dose * per_day * days


def format_quantity(value: float, dose_unit: str | None = None) -> str:
    """'90', '2.5', or '300 mL' for volume doses."""
    number = str(int(value)) if float(value).is_integer() else f"{value:g}"
    return f"{number} mL" if dose_unit == "ML" else number


def _units_compatible(dose_unit: str | None, quantity_unit: str | None) -> bool:
    if dose_unit is None:
        return False
    if quantity_unit is None:
        # A bare count or volume is read in the dose's own unit.
        return True
    canonical = _UNIT_ALIASES.get(quantity_unit.strip().lower())
    if canonical is None:
        return False
    if dose_unit in _COUNT_UNITS:
        return canonical == dose_unit
    return canonical == "ML" and dose_unit == "ML"
