import pytest

from backend.models import (
    CRITICAL_FIELDS,
    Evidence,
    FieldDecision,
    FieldResult,
    Prescription,
    PrescriptionStatus,
    RxException,
    Signal,
    SignalStatus,
    SourceQuality,
)
from backend.policy import evaluate_field, route_field, route_prescription


def _field(value="x", quality=SourceQuality.CLEAR, signals=(), evidence=Evidence(page=1, bbox=None), decision=FieldDecision.EXTRACTED):
    return FieldResult(
        raw_value=value,
        source_quality=quality,
        evidence=evidence,
        signals=[Signal(type=t, status=s) for t, s in signals],
        decision=decision,
    )


F, P, W, A = SignalStatus.FAIL, SignalStatus.PASS, SignalStatus.WARNING, SignalStatus.AMBIGUOUS


@pytest.mark.parametrize(
    ("name", "kwargs", "decision", "exception_type"),
    [
        ("drug", {"value": None}, FieldDecision.MISSING, "MISSING_FIELD"),
        ("sig", {"value": "  "}, FieldDecision.MISSING, "MISSING_FIELD"),
        ("patient", {"signals": [("PATIENT_IDENTITY", F)]}, FieldDecision.REVIEW_REQUIRED, "PATIENT_IDENTITY_CONFLICT"),
        ("drug", {"signals": [("CROSS_PASS", F)]}, FieldDecision.REVIEW_REQUIRED, "AMBIGUOUS_DRUG"),
        ("strength", {"signals": [("CROSS_PASS", F)]}, FieldDecision.REVIEW_REQUIRED, "AMBIGUOUS_STRENGTH"),
        ("drug", {"signals": [("LASA", F)]}, FieldDecision.REVIEW_REQUIRED, "AMBIGUOUS_DRUG"),
        ("drug", {"signals": [("RXNORM", A)]}, FieldDecision.REVIEW_REQUIRED, "AMBIGUOUS_DRUG"),
        ("drug", {"signals": [("RXNORM", W)]}, FieldDecision.REVIEW_REQUIRED, "UNVERIFIED_DRUG"),
        ("strength", {"signals": [("MARKETED_STRENGTH", F)]}, FieldDecision.INVALID, "INVALID_STRENGTH"),
        ("sig", {"signals": [("SIG_VOCABULARY", F)]}, FieldDecision.REVIEW_REQUIRED, "UNSUPPORTED_SIG"),
        ("quantity", {"signals": [("QUANTITY_SIG", F)]}, FieldDecision.REVIEW_REQUIRED, "POSSIBLE_QUANTITY_CONFLICT"),
        ("prescriber", {"quality": SourceQuality.UNREADABLE}, FieldDecision.REVIEW_REQUIRED, "UNREADABLE_SOURCE"),
        ("prescriber", {"evidence": None}, FieldDecision.REVIEW_REQUIRED, "MISSING_EVIDENCE"),
        ("prescriber", {"evidence": Evidence(page=None, bbox=(1, 2, 3, 4))}, FieldDecision.REVIEW_REQUIRED, "MISSING_EVIDENCE"),
        ("prescriber", {}, FieldDecision.VERIFIED, None),
    ],
)
def test_critical_rules(name, kwargs, decision, exception_type):
    route = evaluate_field(name, _field(**kwargs))

    assert route.decision is decision
    assert route.exception_type == exception_type
    assert route.reason and "%" not in route.reason


def test_route_field_returns_decision_and_reason():
    decision, reason = route_field("prescriber", _field())

    assert decision is FieldDecision.VERIFIED
    assert isinstance(reason, str)


def test_precedence_first_rule_wins():
    field = _field(signals=[("QUANTITY_SIG", F), ("CROSS_PASS", F), ("PATIENT_IDENTITY", F)])

    assert evaluate_field("drug", field).exception_type == "PATIENT_IDENTITY_CONFLICT"


def test_missing_beats_unreadable():
    route = evaluate_field("drug", _field(value=None, quality=SourceQuality.UNREADABLE))

    assert route.decision is FieldDecision.MISSING


def test_reference_gap_on_strength_is_not_blocking_or_invalid():
    route = evaluate_field("strength", _field(signals=[("RXNORM", W), ("MARKETED_STRENGTH", W)]))

    assert route.decision is FieldDecision.VERIFIED


def test_reference_gap_never_invalid():
    for name in CRITICAL_FIELDS:
        assert evaluate_field(name, _field(signals=[("RXNORM", W)])).decision is not FieldDecision.INVALID


def test_latest_signal_of_a_type_wins():
    field = _field(signals=[("QUANTITY_SIG", F), ("QUANTITY_SIG", P)])

    assert evaluate_field("quantity", field).decision is FieldDecision.VERIFIED


def test_page_without_bbox_is_sufficient_provenance():
    assert evaluate_field("patient", _field(evidence=Evidence(page=1, bbox=None))).decision is FieldDecision.VERIFIED


@pytest.mark.parametrize("name", sorted(CRITICAL_FIELDS))
@pytest.mark.parametrize("evidence", [None, Evidence(page=None, bbox=(1, 2, 3, 4))])
def test_critical_without_provenance_never_verified(name, evidence):
    assert evaluate_field(name, _field(evidence=evidence)).decision is not FieldDecision.VERIFIED


@pytest.mark.parametrize(
    ("kwargs", "decision", "blocking"),
    [
        ({"value": None}, FieldDecision.MISSING, False),
        ({"quality": SourceQuality.UNREADABLE}, FieldDecision.UNREADABLE, False),
        ({"evidence": None}, FieldDecision.VERIFIED, False),
        ({"signals": [("IDENTIFIER_CHECKSUM", F)]}, FieldDecision.REVIEW_REQUIRED, True),
        ({"signals": [("IDENTIFIER_CHECKSUM", P)]}, FieldDecision.VERIFIED, False),
    ],
)
def test_optional_field_semantics(kwargs, decision, blocking):
    route = evaluate_field("prescriber_identifier", _field(**kwargs))

    assert route.decision is decision
    assert (route.exception_type is not None) is blocking


def _rx(status=PrescriptionStatus.PROCESSING, decisions=None, exceptions=(), clarifications=()):
    decisions = decisions or {}
    return Prescription(
        prescription_id="rx",
        status=status,
        source={},
        fields={
            n: _field(decision=decisions.get(n, FieldDecision.VERIFIED)) for n in CRITICAL_FIELDS
        },
        exceptions=[
            RxException(exception_id=e, type="X", field="drug", severity="CRITICAL", reason="r", required_action="a")
            for e in exceptions
        ],
        clarifications=list(clarifications),
        approved_by=None,
        audit_events=[],
    )


def test_ready_requires_resolved_critical_and_no_blockers():
    assert route_prescription(_rx()) is PrescriptionStatus.READY_FOR_VERIFICATION
    assert route_prescription(_rx(decisions={"drug": FieldDecision.HUMAN_VERIFIED})) is PrescriptionStatus.READY_FOR_VERIFICATION


def test_active_blocker_prevents_ready_even_when_fields_verified():
    assert route_prescription(_rx(exceptions=["e1"])) is PrescriptionStatus.REVIEW_REQUIRED


def test_unresolved_critical_field_prevents_ready():
    assert route_prescription(_rx(decisions={"sig": FieldDecision.EXTRACTED})) is PrescriptionStatus.REVIEW_REQUIRED


def test_awaiting_clarification_only_for_active_exception():
    requested = [{"exception_id": "e1", "status": "REQUESTED"}]
    assert route_prescription(_rx(exceptions=["e1"], clarifications=requested)) is PrescriptionStatus.AWAITING_CLARIFICATION
    # Stale REQUESTED record for an exception that no longer exists does not hold the state.
    assert route_prescription(_rx(clarifications=requested)) is PrescriptionStatus.READY_FOR_VERIFICATION


def test_resolved_clarification_history_does_not_block():
    history = [{"exception_id": "e1", "status": "RESOLVED"}]

    assert route_prescription(_rx(clarifications=history)) is PrescriptionStatus.READY_FOR_VERIFICATION


@pytest.mark.parametrize(
    "status", [PrescriptionStatus.APPROVED, PrescriptionStatus.REJECTED, PrescriptionStatus.UNPROCESSABLE]
)
def test_terminal_and_unprocessable_not_overwritten(status):
    assert route_prescription(_rx(status=status, exceptions=["e1"])) is status


def test_router_never_produces_approved():
    for status in PrescriptionStatus:
        if status is PrescriptionStatus.APPROVED:
            continue
        assert route_prescription(_rx(status=status)) is not PrescriptionStatus.APPROVED
