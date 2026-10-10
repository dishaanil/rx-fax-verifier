"""Approval-blocking fields (DESIGN.md §6). Fixed — do not extend."""

CRITICAL_FIELDS: frozenset[str] = frozenset(
    {
        "patient",
        "drug",
        "strength",
        "sig",
        "prescriber",
        "quantity",
    }
)
