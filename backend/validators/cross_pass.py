"""CROSS_PASS: independent reads of drug/strength must agree. Pure; values are pre-normalized by the caller."""

from backend.models import Signal, SignalStatus

SIGNAL_TYPE = "CROSS_PASS"


def validate_cross_pass(read_keys: list[str | None]) -> Signal:
    """`read_keys` are comparable forms of each read (None for an empty read)."""
    present = [k for k in read_keys if k]
    if len(present) < 2:
        return Signal(type=SIGNAL_TYPE, status=SignalStatus.WARNING, detail="No secondary read to compare.")
    if len(set(present)) == 1:
        return Signal(type=SIGNAL_TYPE, status=SignalStatus.PASS, detail="Both reads agree.")
    return Signal(type=SIGNAL_TYPE, status=SignalStatus.FAIL, detail="Extraction reads disagree.")
