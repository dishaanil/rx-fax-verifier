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
    if as_needed:
        return None
    if dose is None or days is None or stated_qty is None:
        return None
    per_day = FREQUENCY_PER_DAY.get(frequency_token) if frequency_token else None
    if per_day is None:
        return None
    if not _units_compatible(dose_unit, quantity_unit):
        return None

    expected = dose * per_day * days
    suffix = " mL" if dose_unit == "ML" else ""
    if math.isclose(expected, stated_qty):
        return Signal(
            type=SIGNAL_TYPE,
            status=SignalStatus.PASS,
            detail=f"Directions imply {_fmt(expected)}{suffix}; prescription states {_fmt(stated_qty)}{suffix}.",
        )
    return Signal(
        type=SIGNAL_TYPE,
        status=SignalStatus.FAIL,
        detail=f"Directions imply {_fmt(expected)}{suffix} but prescription states {_fmt(stated_qty)}{suffix}.",
    )


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


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"
