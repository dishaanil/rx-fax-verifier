"""Duplicate document detection (DESIGN.md §11). Caller owns `seen`; it is not mutated."""

from backend.models import Signal, SignalStatus

SIGNAL_TYPE = "DUPLICATE_DOCUMENT"


def validate_duplicate(sha256: str, seen: set[str]) -> Signal:
    if sha256 in seen:
        return Signal(
            type=SIGNAL_TYPE,
            status=SignalStatus.FAIL,
            detail=f"DUPLICATE_DOCUMENT: sha256 {sha256} has already been ingested.",
        )
    return Signal(type=SIGNAL_TYPE, status=SignalStatus.PASS, detail="Document not seen before.")
