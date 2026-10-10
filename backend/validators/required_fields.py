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
        elif _is_empty(fields[name]):
            signals.append(_signal(SignalStatus.FAIL, f"Critical field {name!r} is empty."))
        else:
            signals.append(_signal(SignalStatus.PASS, f"Critical field {name!r} is present."))

    for name in sorted(fields.keys() - CRITICAL_FIELDS):
        if _is_empty(fields[name]):
            signals.append(_signal(SignalStatus.WARNING, f"Optional field {name!r} is missing or unreadable."))

    return signals


def _is_empty(value: object | None) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _signal(status: SignalStatus, detail: str) -> Signal:
    return Signal(type=SIGNAL_TYPE, status=status, detail=detail)
