"""SIG normalization: free-text directions -> canonical tokens.

Runs before SIG validation. Prose is mapped to canonical abbreviations;
anything outside the closed vocabulary is preserved in `unknown`, never guessed.
"""

import re
from dataclasses import dataclass, field

from backend.references.sig_vocabulary import DOSE_UNITS, FREQUENCY_PER_DAY, SIG_VOCABULARY


@dataclass(frozen=True)
class NormalizedSig:
    tokens: list[str] = field(default_factory=list)
    dose: float | None = None
    dose_unit: str | None = None
    frequency_token: str | None = None
    days: int | None = None
    as_needed: bool = False
    unknown: list[str] = field(default_factory=list)


# Multi-word prose -> canonical token. Matched longest-first, case-insensitive.
_PHRASES: dict[str, str] = {
    "once daily": "QD",
    "every day": "QD",
    "twice daily": "BID",
    "three times daily": "TID",
    "four times daily": "QID",
    "at bedtime": "QHS",
    "every morning": "QAM",
    "by mouth": "PO",
    "as needed": "PRN",
    "every 4 hours": "Q4H",
    "every 6 hours": "Q6H",
    "every 8 hours": "Q8H",
    "every 12 hours": "Q12H",
}

# Single words -> canonical token (keys lowercase).
_WORDS: dict[str, str] = {
    "daily": "QD",
    "orally": "PO",
    "tablet": "TAB",
    "tablets": "TAB",
    "tab": "TAB",
    "tabs": "TAB",
    "capsule": "CAP",
    "capsules": "CAP",
    "cap": "CAP",
    "caps": "CAP",
    "ml": "ML",
}

# Filler and strength units: neither canonical nor flagged as unknown.
_IGNORABLE: frozenset[str] = frozenset({"take", "for", "day", "days", "mg", "mcg", "g"})

_PHRASE_RE = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in sorted(_PHRASES, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_DAYS_RE = re.compile(r"\bfor\s+(\d+)\s+days?\b", re.IGNORECASE)
# "10mL" -> "10 mL"; does not split tokens like Q12H (no word boundary before the digit).
_NUM_UNIT_RE = re.compile(r"\b(\d+(?:\.\d+)?)([a-z]+)\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)?$")
_PUNCT = ".,;:"


def normalize_sig(raw: str | None) -> NormalizedSig:
    if raw is None or not raw.strip():
        return NormalizedSig()

    text = raw
    days: int | None = None
    days_match = _DAYS_RE.search(text)
    if days_match:
        days = int(days_match.group(1))
        text = text[: days_match.start()] + " " + text[days_match.end() :]

    text = _PHRASE_RE.sub(lambda m: f" {_PHRASES[m.group(1).lower()]} ", text)
    text = _NUM_UNIT_RE.sub(r"\1 \2", text)

    tokens: list[str] = []
    unknown: list[str] = []
    for word in text.split():
        word = word.strip(_PUNCT)
        if not word:
            continue
        lower = word.lower()
        if _NUMBER_RE.match(word):
            tokens.append(word)
        elif lower in _WORDS:
            tokens.append(_WORDS[lower])
        elif word.upper() in SIG_VOCABULARY:
            tokens.append(word.upper())
        elif lower in _IGNORABLE:
            continue
        else:
            tokens.append(word)
            unknown.append(word)

    dose, dose_unit = _extract_dose(tokens)
    frequency_token = next((t for t in tokens if t in FREQUENCY_PER_DAY), None)

    return NormalizedSig(
        tokens=tokens,
        dose=dose,
        dose_unit=dose_unit,
        frequency_token=frequency_token,
        days=days,
        as_needed="PRN" in tokens,
        unknown=unknown,
    )


def _extract_dose(tokens: list[str]) -> tuple[float | None, str | None]:
    """First `<number> <dispensing unit>` pair, e.g. `1 TAB` or `10 ML`."""
    for number, unit in zip(tokens, tokens[1:]):
        if _NUMBER_RE.match(number) and unit in DOSE_UNITS:
            return float(number), unit
    return None, None
