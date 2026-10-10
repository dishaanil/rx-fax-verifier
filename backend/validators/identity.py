"""Patient identity consistency (DESIGN.md §11). Exact comparison after
whitespace/case normalization only — no fuzzy matching, never merges."""

import re

from backend.models import Signal, SignalStatus

SIGNAL_TYPE = "PATIENT_IDENTITY"
_WS_RE = re.compile(r"\s+")


def validate_patient_identity(
    header_name: str | None,
    block_name: str | None,
    dob_values: list[str],
) -> Signal:
    header = _normalize_name(header_name)
    block = _normalize_name(block_name)
    if header and block and header != block:
        return Signal(
            type=SIGNAL_TYPE,
            status=SignalStatus.FAIL,
            detail=f"Header name {header_name.strip()!r} does not match prescription block name {block_name.strip()!r}.",
        )

    dobs = sorted({d.strip() for d in dob_values if d and d.strip()})
    if len(dobs) > 1:
        return Signal(
            type=SIGNAL_TYPE,
            status=SignalStatus.FAIL,
            detail=f"Conflicting dates of birth: {', '.join(dobs)}.",
        )

    return Signal(type=SIGNAL_TYPE, status=SignalStatus.PASS, detail="No patient identity conflict found.")


def _normalize_name(name: str | None) -> str:
    return _WS_RE.sub(" ", name.strip()).casefold() if name else ""
