"""Closed SIG vocabulary and frequency table (DESIGN.md §11).

Q12H is an extension beyond the §11 list, added for the backend slice.
"""

SIG_VOCABULARY: frozenset[str] = frozenset(
    {
        "PO", "PR", "SL", "IM", "IV",
        "BID", "TID", "QID", "QD", "QHS", "QAM",
        "PRN", "AC", "PC", "GTT",
        "TAB", "CAP",
        "Q4H", "Q6H", "Q8H", "Q12H",
    }
)

# Administrations per day.
FREQUENCY_PER_DAY: dict[str, int] = {
    "QD": 1,
    "BID": 2,
    "TID": 3,
    "QID": 4,
    "Q4H": 6,
    "Q6H": 4,
    "Q8H": 3,
    "Q12H": 2,
    "QHS": 1,
    "QAM": 1,
}

# Dispensing units an administered dose can be counted in.
DOSE_UNITS: frozenset[str] = frozenset({"TAB", "CAP", "ML"})
