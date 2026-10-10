"""LASA signal (DESIGN.md §10 rule 4): flags look-alike risk only when the source is ambiguous.

FAIL iff (a) primary and secondary reads differ and form a LASA pair, or
(b) both members of one pair appear among reads + reference candidates, or
(c) source quality is not CLEAR and a read or candidate is a pair member.
A clean, agreeing, CLEAR read of a pair member is PASS.
"""

from backend.models import Read, Signal, SignalStatus, SourceQuality
from backend.references.lasa import contains_lasa_pair, is_lasa_member, is_lasa_pair

SIGNAL_TYPE = "LASA"


def validate_lasa(reads: list[Read], candidates: list[str], source_quality: SourceQuality) -> Signal:
    primary = next((r.value for r in reads if r.source == "primary" and r.value), None)
    secondary = next((r.value for r in reads if r.source == "secondary" and r.value), None)
    names = [r.value for r in reads if r.value] + list(candidates)

    if primary and secondary and is_lasa_pair(primary, secondary):
        return _fail("Reads disagree on a known look-alike pair.")
    if contains_lasa_pair(names):
        return _fail("Both members of a known look-alike pair are plausible.")
    if source_quality is not SourceQuality.CLEAR and any(is_lasa_member(n) for n in names):
        return _fail("Unclear source on a known look-alike drug name.")
    return Signal(type=SIGNAL_TYPE, status=SignalStatus.PASS, detail="No look-alike ambiguity.")


def _fail(detail: str) -> Signal:
    return Signal(type=SIGNAL_TYPE, status=SignalStatus.FAIL, detail=detail)
