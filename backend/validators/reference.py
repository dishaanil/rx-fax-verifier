"""RXNORM-typed signal from the local catalog. A reference gap is a WARNING, never INVALID."""

from backend.models import Signal, SignalStatus
from backend.references.catalog import ReferenceResult

SIGNAL_TYPE = "RXNORM"


def validate_reference(result: ReferenceResult) -> Signal:
    if result.clear:
        return Signal(type=SIGNAL_TYPE, status=SignalStatus.PASS, detail="One exact reference match.")
    if not result.candidates:
        return Signal(type=SIGNAL_TYPE, status=SignalStatus.WARNING, detail="No local reference match.")
    if len(result.candidates) == 1:
        detail = "Only an approximate reference match; the source text does not match it exactly."
    else:
        detail = f"{len(result.candidates)} plausible reference candidates."
    return Signal(type=SIGNAL_TYPE, status=SignalStatus.AMBIGUOUS, detail=detail)
