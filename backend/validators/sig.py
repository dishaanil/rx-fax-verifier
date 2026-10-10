"""SIG vocabulary check over the output of normalize_sig (DESIGN.md §11)."""

from backend.models import Signal, SignalStatus

SIGNAL_TYPE = "SIG_VOCABULARY"


def validate_sig_tokens(unknown: list[str]) -> Signal:
    if not unknown:
        return Signal(type=SIGNAL_TYPE, status=SignalStatus.PASS, detail="All tokens recognised.")
    return Signal(
        type=SIGNAL_TYPE,
        status=SignalStatus.FAIL,
        detail=f"Unsupported SIG token(s): {', '.join(unknown)}.",
    )
