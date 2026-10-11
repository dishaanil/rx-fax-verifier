"""Plausible strength collision: a hotfix for common-mode model agreement.

Two vision models can misread the same degraded pixels the same way (a faxed
'75 mg' read as '25 mg' by both). CROSS_PASS then passes, and so does
MARKETED_STRENGTH when the misread is itself a marketed strength. This check
fails when another marketed strength of the same drug differs from the read
by a single visually confusable digit, so agreement alone cannot verify it.

This is a deterministic, pure heuristic over the local strength table. It
does NOT perform pixel-level image-quality analysis and must not be presented
as detecting source-image degradation.
"""

import re

from backend.models import Signal, SignalStatus
from backend.references.strengths import MARKETED_STRENGTHS, normalize_drug_name, normalize_strength

SIGNAL_TYPE = "PLAUSIBLE_STRENGTH_COLLISION"

# Deliberately narrow: digit pairs commonly confused in degraded print or
# handwriting. Pairs such as 1/2, 1/4 or 0/5 are left out so routine strengths
# (lisinopril 10 vs 20 mg, amoxicillin 250 vs 200 mg/5 mL) are not flagged.
CONFUSABLE_DIGITS: frozenset[frozenset[str]] = frozenset(
    frozenset(pair) for pair in ("27", "17", "38", "56", "68", "08")
)

# Canonical strengths from normalize_strength: '<amount> <unit>[/<amount> <unit>]'.
_CANONICAL_RE = re.compile(r"^(\d+(?:\.\d+)?) (mg|mcg|g)(/\d+(?:\.\d+)? ml)?$")


def is_confusable(a: str, b: str) -> bool:
    """True when two canonical strengths share unit and concentration structure
    and their amounts differ in exactly one position, by a confusable digit pair.
    '25 mg' vs '75 mg' is confusable; '25 mg' vs '250 mg', '25 mg' vs '75 mcg'
    and '25 mg' vs '75 mg/5 ml' are not."""
    ma, mb = _CANONICAL_RE.match(a), _CANONICAL_RE.match(b)
    if not ma or not mb:
        return False
    amount_a, unit_a, per_a = ma.groups()
    amount_b, unit_b, per_b = mb.groups()
    if unit_a != unit_b or per_a != per_b or len(amount_a) != len(amount_b):
        return False
    diffs = [(x, y) for x, y in zip(amount_a, amount_b, strict=True) if x != y]
    return len(diffs) == 1 and frozenset(diffs[0]) in CONFUSABLE_DIGITS


def validate_strength_collision(drug: str, strength: str) -> Signal:
    allowed = MARKETED_STRENGTHS.get(normalize_drug_name(drug))
    if allowed is None:
        return Signal(
            type=SIGNAL_TYPE,
            status=SignalStatus.WARNING,
            detail=f"No local strength reference for {drug.strip()}; collision not checked.",
        )

    canonical = normalize_strength(strength)
    if canonical is None:
        return Signal(
            type=SIGNAL_TYPE,
            status=SignalStatus.WARNING,
            detail=f"Strength {strength.strip()!r} is not a recognised numeric strength; collision not checked.",
        )
    if canonical not in allowed:
        # Not marketed: MARKETED_STRENGTH already fails it; nothing to collide with.
        return Signal(
            type=SIGNAL_TYPE,
            status=SignalStatus.WARNING,
            detail=f"{strength.strip()} is not a marketed strength; collision not checked.",
        )

    collisions = sorted(s for s in allowed if s != canonical and is_confusable(canonical, s))
    if collisions:
        return Signal(
            type=SIGNAL_TYPE,
            status=SignalStatus.FAIL,
            detail=f"{strength.strip()} is visually confusable with marketed {', '.join(collisions)}.",
        )
    return Signal(
        type=SIGNAL_TYPE,
        status=SignalStatus.PASS,
        detail=f"No marketed strength is visually confusable with {strength.strip()}.",
    )
