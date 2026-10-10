"""Required-field presence (DESIGN.md §6, §11).

Critical fields: one PASS/FAIL signal each. Optional fields: a WARNING only
when the key is present but null/blank; absent optional keys produce nothing.
Optional warnings never block readiness.
"""

from backend.models import CRITICAL_FIELDS, Signal, SignalStatus

SIGNAL_TYPE = "REQUIRED_FIELD"


def validate_required(fields: dict[str, object | None]) -> list[Signal]:
    signals: list[Signal] = []

    for name in sorted(CRITICAL_FIELDS):
        if name not in fields:
            signals.append(_signal(SignalStatus.FAIL, f"Critical field {name!r} is absent."))
        else:
            signals.append(check_required(name, fields[name]))

    for name in sorted(fields.keys() - CRITICAL_FIELDS):
        signal = check_required(name, fields[name])
        if signal is not None:
            signals.append(signal)

    return signals


def check_required(name: str, value: object | None) -> Signal | None:
    """Signal for one present field: PASS/FAIL if critical; WARNING or None if optional."""
    if name in CRITICAL_FIELDS:
        if _is_empty(value):
            return _signal(SignalStatus.FAIL, f"Critical field {name!r} is empty.")
        return _signal(SignalStatus.PASS, f"Critical field {name!r} is present.")
    if _is_empty(value):
        return _signal(SignalStatus.WARNING, f"Optional field {name!r} is missing or unreadable.")
    return None


def _is_empty(value: object | None) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _signal(status: SignalStatus, detail: str) -> Signal:
    return Signal(type=SIGNAL_TYPE, status=status, detail=detail)
