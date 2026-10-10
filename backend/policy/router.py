"""Deterministic routing policy (DESIGN.md §10). Precedence, never a weighted average.

Rules read the most recent signal of each type, so revalidation can append
new evidence without erasing history. Nothing here assigns APPROVED.
"""

from dataclasses import dataclass

from backend.models import (
    CRITICAL_FIELDS,
    FieldDecision,
    FieldResult,
    Prescription,
    PrescriptionStatus,
    Signal,
    SignalStatus,
    SourceQuality,
)

TERMINAL_STATUSES = frozenset({PrescriptionStatus.APPROVED, PrescriptionStatus.REJECTED})
RESOLVED_DECISIONS = frozenset({FieldDecision.VERIFIED, FieldDecision.HUMAN_VERIFIED})

# Fixed plain-English reasons. No scores.
REASON_MISSING = "No usable value for this critical field was found on the source."
REASON_IDENTITY = "Patient identity details on the document do not agree."
REASON_CROSS_PASS_LASA = "Two visual reads disagree and both correspond to plausible similar drug names."
REASON_CROSS_PASS = "Independent reads of this field disagree."
REASON_LASA = "The drug name is a known look-alike and the source does not settle which drug is meant."
REASON_REFERENCE_AMBIGUOUS = "More than one reference drug plausibly matches the source text."
REASON_REFERENCE_GAP = "The drug name could not be matched to the reference catalog, so its identity is not independently supported."
REASON_INVALID_STRENGTH = "This strength is not a marketed strength for this drug."
REASON_IDENTIFIER = "The prescriber identifier fails its checksum."
REASON_SIG = "The directions contain a term outside the supported vocabulary."
REASON_QUANTITY = "The quantity does not match what the directions and days supply imply."
REASON_UNREADABLE = "The source for this critical field is unreadable."
REASON_PARTIAL = "Part of the source for this critical field is illegible, so the value cannot be accepted as read."
REASON_NO_EVIDENCE = "No source location supports this value."
REASON_VERIFIED = "Read clearly and every check on it passed."
REASON_OPTIONAL_MISSING = "Optional field missing; shown as a warning and does not block approval."
REASON_OPTIONAL_UNREADABLE = "Optional field unreadable; shown as a warning and does not block approval."
REASON_OPTIONAL_PRESENT = "Read from the source."


@dataclass(frozen=True)
class FieldRoute:
    decision: FieldDecision
    reason: str
    # Set when the outcome is blocking; the pipeline raises an exception of this type.
    exception_type: str | None = None


def route_field(name: str, field: FieldResult) -> tuple[FieldDecision, str]:
    route = evaluate_field(name, field)
    return route.decision, route.reason


def evaluate_field(name: str, field: FieldResult) -> FieldRoute:
    if name in CRITICAL_FIELDS:
        return _evaluate_critical(name, field)
    return _evaluate_optional(field)


def _evaluate_critical(name: str, field: FieldResult) -> FieldRoute:
    latest = latest_signals(field.signals)

    def failed(signal_type: str, status: SignalStatus = SignalStatus.FAIL) -> bool:
        signal = latest.get(signal_type)
        return signal is not None and signal.status is status

    review = FieldDecision.REVIEW_REQUIRED

    # 1. Missing critical information.
    if _blank(field.raw_value):
        return FieldRoute(FieldDecision.MISSING, REASON_MISSING, "MISSING_FIELD")
    # 2. Patient identity conflict.
    if failed("PATIENT_IDENTITY"):
        return FieldRoute(review, REASON_IDENTITY, "PATIENT_IDENTITY_CONFLICT")
    # 3. Cross-pass disagreement.
    if failed("CROSS_PASS"):
        reason = REASON_CROSS_PASS_LASA if name == "drug" and failed("LASA") else REASON_CROSS_PASS
        return FieldRoute(review, reason, f"AMBIGUOUS_{name.upper()}")
    # 4. LASA ambiguity.
    if failed("LASA"):
        return FieldRoute(review, REASON_LASA, "AMBIGUOUS_DRUG")
    # 5. Reference ambiguity; for the drug, a reference gap also blocks.
    if failed("RXNORM", SignalStatus.AMBIGUOUS):
        return FieldRoute(review, REASON_REFERENCE_AMBIGUOUS, "AMBIGUOUS_DRUG")
    if name == "drug" and failed("RXNORM", SignalStatus.WARNING):
        return FieldRoute(review, REASON_REFERENCE_GAP, "UNVERIFIED_DRUG")
    # 6. Deterministic contradiction.
    deterministic = _deterministic_failure(latest)
    if deterministic is not None:
        return deterministic
    # 7. Cross-field contradiction.
    if failed("QUANTITY_SIG"):
        return FieldRoute(review, REASON_QUANTITY, "POSSIBLE_QUANTITY_CONFLICT")
    # 8. Critical source marked unreadable.
    if field.source_quality is SourceQuality.UNREADABLE:
        return FieldRoute(review, REASON_UNREADABLE, "UNREADABLE_SOURCE")
    # 8b. Critical source only partly legible: a plausible reading is not evidence.
    if field.source_quality is SourceQuality.PARTIAL:
        return FieldRoute(review, REASON_PARTIAL, "PARTIAL_SOURCE")
    # 9. Insufficient provenance (a page with no bbox is enough today).
    if field.evidence is None or field.evidence.page is None:
        return FieldRoute(review, REASON_NO_EVIDENCE, "MISSING_EVIDENCE")
    # 10. Evidence agrees.
    return FieldRoute(FieldDecision.VERIFIED, REASON_VERIFIED)


def _evaluate_optional(field: FieldResult) -> FieldRoute:
    """Absent/missing/unreadable optional fields never block; a present optional
    field that deterministically fails an integrity check does."""
    if _blank(field.raw_value):
        return FieldRoute(FieldDecision.MISSING, REASON_OPTIONAL_MISSING)
    if field.source_quality is SourceQuality.UNREADABLE:
        return FieldRoute(FieldDecision.UNREADABLE, REASON_OPTIONAL_UNREADABLE)
    deterministic = _deterministic_failure(latest_signals(field.signals))
    if deterministic is not None:
        return deterministic
    return FieldRoute(FieldDecision.VERIFIED, REASON_OPTIONAL_PRESENT)


def _deterministic_failure(latest: dict[str, Signal]) -> FieldRoute | None:
    def failed(signal_type: str) -> bool:
        signal = latest.get(signal_type)
        return signal is not None and signal.status is SignalStatus.FAIL

    if failed("MARKETED_STRENGTH"):
        return FieldRoute(FieldDecision.INVALID, REASON_INVALID_STRENGTH, "INVALID_STRENGTH")
    if failed("IDENTIFIER_CHECKSUM"):
        return FieldRoute(FieldDecision.REVIEW_REQUIRED, REASON_IDENTIFIER, "IDENTIFIER_INVALID")
    if failed("SIG_VOCABULARY"):
        return FieldRoute(FieldDecision.REVIEW_REQUIRED, REASON_SIG, "UNSUPPORTED_SIG")
    return None


def route_prescription(prescription: Prescription) -> PrescriptionStatus:
    """Readiness needs all six critical fields resolved AND no active blocking exception.
    Never returns APPROVED unless it already was; terminal and UNPROCESSABLE states are kept."""
    status = prescription.status
    if status in TERMINAL_STATUSES or status is PrescriptionStatus.UNPROCESSABLE:
        return status

    active = {e.exception_id for e in prescription.exceptions}
    if any(c.get("status") == "REQUESTED" and c.get("exception_id") in active for c in prescription.clarifications):
        return PrescriptionStatus.AWAITING_CLARIFICATION
    if active:
        return PrescriptionStatus.REVIEW_REQUIRED

    fields = prescription.fields
    if all(name in fields and fields[name].decision in RESOLVED_DECISIONS for name in CRITICAL_FIELDS):
        return PrescriptionStatus.READY_FOR_VERIFICATION
    return PrescriptionStatus.REVIEW_REQUIRED


def latest_signals(signals: list[Signal]) -> dict[str, Signal]:
    latest: dict[str, Signal] = {}
    for signal in signals:
        latest[signal.type] = signal
    return latest


def _blank(value: str | None) -> bool:
    return value is None or not value.strip()
