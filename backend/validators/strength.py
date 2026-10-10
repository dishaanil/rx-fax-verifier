"""Marketed-strength check (DESIGN.md §11): transcription fidelity, not clinical judgment."""

from backend.models import Signal, SignalStatus
from backend.references.strengths import MARKETED_STRENGTHS, normalize_drug_name, normalize_strength

SIGNAL_TYPE = "MARKETED_STRENGTH"


def validate_marketed_strength(drug: str, strength: str) -> Signal:
    allowed = MARKETED_STRENGTHS.get(normalize_drug_name(drug))
    if allowed is None:
        return Signal(
            type=SIGNAL_TYPE,
            status=SignalStatus.WARNING,
            detail=f"No local strength reference for {drug.strip()}; not checked.",
        )

    canonical = normalize_strength(strength)
    if canonical is None:
        return Signal(
            type=SIGNAL_TYPE,
            status=SignalStatus.WARNING,
            detail=f"Strength {strength.strip()!r} is not a recognised numeric strength; not checked.",
        )
    if canonical in allowed:
        return Signal(
            type=SIGNAL_TYPE,
            status=SignalStatus.PASS,
            detail=f"{strength.strip()} is a marketed strength.",
        )
    return Signal(
        type=SIGNAL_TYPE,
        status=SignalStatus.FAIL,
        detail=f"{strength.strip()} is not a marketed strength of {drug.strip()}.",
    )
