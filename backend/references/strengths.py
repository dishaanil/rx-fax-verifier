"""Marketed-strength reference table (DESIGN.md §11).

Deterministic demo data, not a complete catalog. A drug missing from this
table is a reference gap (WARNING), never evidence of an invalid strength.
Formulation-defining salts stay distinct (metoprolol tartrate != succinate);
only HCl and hydrochloride are treated as equivalent.
"""

import re

_MARKETED_STRENGTHS_RAW: dict[str, list[str]] = {
    "metoprolol tartrate": ["25 mg", "37.5 mg", "50 mg", "75 mg", "100 mg"],
    "metoprolol succinate": ["25 mg", "50 mg", "100 mg", "200 mg"],
    "hydroxyzine HCl": ["10 mg", "25 mg", "50 mg"],
    "hydralazine HCl": ["10 mg", "25 mg", "50 mg", "100 mg"],
    "amoxicillin suspension": ["125 mg/5 mL", "200 mg/5 mL", "250 mg/5 mL", "400 mg/5 mL"],
    "atorvastatin": ["10 mg", "20 mg", "40 mg", "80 mg"],
    "simvastatin": ["5 mg", "10 mg", "20 mg", "40 mg", "80 mg"],
    "lisinopril": ["2.5 mg", "5 mg", "10 mg", "20 mg", "30 mg", "40 mg"],
    "amlodipine": ["2.5 mg", "5 mg", "10 mg"],
    "losartan potassium": ["25 mg", "50 mg", "100 mg"],
    "metformin HCl": ["500 mg", "850 mg", "1000 mg"],
    "sertraline": ["25 mg", "50 mg", "100 mg"],
    "trazodone HCl": ["50 mg", "100 mg", "150 mg", "300 mg"],
    "gabapentin": ["100 mg", "300 mg", "400 mg", "600 mg", "800 mg"],
    "prednisone": ["1 mg", "2.5 mg", "5 mg", "10 mg", "20 mg", "50 mg"],
    "levothyroxine": [
        "25 mcg", "50 mcg", "75 mcg", "88 mcg", "100 mcg", "112 mcg",
        "125 mcg", "137 mcg", "150 mcg", "175 mcg", "200 mcg", "300 mcg",
    ],
}

_WS_RE = re.compile(r"\s+")
_HYDROCHLORIDE_RE = re.compile(r"\bhydrochloride\b")
_STRENGTH_RE = re.compile(
    r"^(\d+(?:\.\d+)?)\s*(mg|mcg|g)(?:\s*/\s*(\d+(?:\.\d+)?)\s*(ml))?$"
)


def normalize_drug_name(name: str) -> str:
    key = _WS_RE.sub(" ", name.strip()).casefold()
    return _HYDROCHLORIDE_RE.sub("hcl", key)


def normalize_strength(strength: str) -> str | None:
    """Canonical form like '37.5 mg' or '125 mg/5 ml'; None if not a numeric strength."""
    match = _STRENGTH_RE.match(_WS_RE.sub(" ", strength.strip()).casefold())
    if not match:
        return None
    amount, unit, per_amount, per_unit = match.groups()
    canonical = f"{_number(amount)} {unit}"
    if per_amount:
        canonical += f"/{_number(per_amount)} {per_unit}"
    return canonical


def _number(text: str) -> str:
    return text.rstrip("0").rstrip(".") if "." in text else text.lstrip("0") or "0"


MARKETED_STRENGTHS: dict[str, frozenset[str]] = {
    normalize_drug_name(drug): frozenset(normalize_strength(s) for s in strengths)
    for drug, strengths in _MARKETED_STRENGTHS_RAW.items()
}

assert all(None not in s for s in MARKETED_STRENGTHS.values()), "unparseable reference strength"
