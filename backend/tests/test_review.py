import pytest

from backend.models import FieldDecision, PrescriptionStatus, SignalStatus
from backend.review import ConflictError, DomainError, NotFoundError, ReviewService
from backend.storage import MemoryStore
from backend.tests.conftest import fixed_clock, processed


@pytest.fixture
def store():
    s = MemoryStore()
    for pid in ("rx_037", "rx_A", "rx_C", "rx_D", "rx_E"):
        s.save(processed(pid))
    return s


@pytest.fixture
def review(store):
    return ReviewService(store, clock=fixed_clock)


def _exc(store, pid, exc_type):
    return next(e for e in store.get(pid).exceptions if e.type == exc_type)


def test_full_approval_loop(store, review):
    with pytest.raises(ConflictError):
        review.approve("rx_037")

    review.resolve(_exc(store, "rx_037", "AMBIGUOUS_DRUG").exception_id, "SELECT_VALUE", "hydroxyzine HCl")
    assert store.get("rx_037").status is PrescriptionStatus.REVIEW_REQUIRED
    with pytest.raises(ConflictError):
        review.approve("rx_037")

    rx = review.resolve(_exc(store, "rx_037", "POSSIBLE_QUANTITY_CONFLICT").exception_id, "SELECT_VALUE", "90")
    assert rx.status is PrescriptionStatus.READY_FOR_VERIFICATION

    rx = review.approve("rx_037")
    assert rx.status is PrescriptionStatus.APPROVED
    assert rx.approved_by == "Demo Pharmacist"
    assert rx.audit_events[-1]["event"] == "PRESCRIPTION_APPROVED"
    assert store.get("rx_037").status is PrescriptionStatus.APPROVED


def test_human_resolution_preserves_history(store, review):
    before = store.get("rx_037").fields["drug"]
    exc = _exc(store, "rx_037", "AMBIGUOUS_DRUG")

    rx = review.resolve(exc.exception_id, "SELECT_VALUE", "hydralazine HCl")
    after = rx.fields["drug"]

    assert after.raw_value == before.raw_value == "hydroxy?ine HCl"
    assert after.reads == before.reads
    assert after.signals[: len(before.signals)] == before.signals
    assert after.candidates == before.candidates
    assert after.decision is FieldDecision.HUMAN_VERIFIED
    assert after.normalized_value == "hydralazine HCl"
    assert after.resolution.value == "hydralazine HCl"
    assert after.resolution.source == "PHARMACIST_SOURCE_REVIEW"
    assert after.resolution.confirmed_by == {"name": "Demo Pharmacist", "role": "PHARMACIST"}
    assert exc.exception_id not in [e.exception_id for e in rx.exceptions]
    assert rx.audit_events[-1] == {
        "ts": fixed_clock(), "actor": "PHARMACIST", "event": "EXCEPTION_RESOLVED",
        "exception_id": exc.exception_id, "action": "SELECT_VALUE",
    }


def test_select_value_must_be_a_candidate(store, review):
    exc = _exc(store, "rx_037", "AMBIGUOUS_DRUG")

    with pytest.raises(DomainError):
        review.resolve(exc.exception_id, "SELECT_VALUE", "lisinopril")
    assert exc.exception_id in [e.exception_id for e in store.get("rx_037").exceptions]


@pytest.mark.parametrize("value", [None, "", "   "])
def test_correct_requires_value(store, review, value):
    with pytest.raises(DomainError):
        review.resolve(_exc(store, "rx_037", "AMBIGUOUS_DRUG").exception_id, "CORRECT", value)


def test_unknown_action_is_domain_error(store, review):
    with pytest.raises(DomainError):
        review.resolve(_exc(store, "rx_037", "AMBIGUOUS_DRUG").exception_id, "APPROVE", None)


def test_missing_exception_not_found(review):
    with pytest.raises(NotFoundError):
        review.resolve("nope__exc_01", "CONFIRM")


def test_confirm_quantity_keeps_stated_value(store, review):
    exc = _exc(store, "rx_C", "POSSIBLE_QUANTITY_CONFLICT")

    rx = review.resolve(exc.exception_id, "CONFIRM")
    q = rx.fields["quantity"]

    assert q.raw_value == "50 mL"
    assert q.resolution.value == "50 mL"
    assert q.decision is FieldDecision.HUMAN_VERIFIED
    assert rx.exceptions == []
    assert "POSSIBLE_QUANTITY_CONFLICT" not in [e.type for e in rx.exceptions]
    assert rx.status is PrescriptionStatus.READY_FOR_VERIFICATION


def test_confirm_on_ambiguous_drug_is_rejected(store, review):
    exc = _exc(store, "rx_037", "AMBIGUOUS_DRUG")

    with pytest.raises(DomainError):
        review.resolve(exc.exception_id, "CONFIRM")
    assert exc.exception_id in [e.exception_id for e in store.get("rx_037").exceptions]


def test_confirm_value_with_question_mark_is_rejected(store, review):
    rx = store.get("rx_037")
    rx.fields["quantity"].normalized_value = "3?"
    store.save(rx)

    with pytest.raises(DomainError):
        review.resolve(_exc(store, "rx_037", "POSSIBLE_QUANTITY_CONFLICT").exception_id, "CONFIRM")


def test_confirm_identifier_invalid(store, review):
    rx = review.resolve(_exc(store, "rx_E", "IDENTIFIER_INVALID").exception_id, "CONFIRM")

    assert rx.fields["prescriber_identifier"].raw_value == "1234567894"
    assert rx.status is PrescriptionStatus.READY_FOR_VERIFICATION


def test_revalidation_does_not_reopen_resolved_field(store, review):
    rx = review.resolve(_exc(store, "rx_037", "POSSIBLE_QUANTITY_CONFLICT").exception_id, "CONFIRM")

    assert "POSSIBLE_QUANTITY_CONFLICT" not in [e.type for e in rx.exceptions]
    assert rx.fields["quantity"].decision is FieldDecision.HUMAN_VERIFIED
    assert rx.status is PrescriptionStatus.REVIEW_REQUIRED  # drug still open

    rx = review.resolve(_exc(store, "rx_037", "AMBIGUOUS_DRUG").exception_id, "SELECT_VALUE", "hydroxyzine HCl")
    assert rx.exceptions == []
    assert rx.fields["quantity"].decision is FieldDecision.HUMAN_VERIFIED
    assert rx.status is PrescriptionStatus.READY_FOR_VERIFICATION


def test_revalidation_rechecks_strength_against_resolved_drug(store, review):
    rx = store.get("rx_037")
    n_before = len(rx.fields["strength"].signals)

    rx = review.resolve(_exc(store, "rx_037", "AMBIGUOUS_DRUG").exception_id, "SELECT_VALUE", "hydralazine HCl")
    strength = rx.fields["strength"]

    assert len(strength.signals) >= n_before
    assert [s for s in strength.signals if s.type == "MARKETED_STRENGTH"][-1].status is SignalStatus.PASS
    assert strength.decision is FieldDecision.VERIFIED


def test_revalidation_can_raise_new_exception_for_unresolved_field(store, review):
    rx = store.get("rx_D")
    rx.fields["strength"].raw_value = "100 mg"  # marketed for hydralazine only
    rx.fields["strength"].reads = []
    store.save(rx)

    rx = review.resolve(_exc(store, "rx_D", "AMBIGUOUS_DRUG").exception_id, "SELECT_VALUE", "hydroxyzine HCl")

    assert [e.type for e in rx.exceptions] == ["INVALID_STRENGTH"]
    assert rx.exceptions[0].exception_id == "rx_D__exc_02"
    assert rx.fields["strength"].decision is FieldDecision.INVALID
    assert rx.status is PrescriptionStatus.REVIEW_REQUIRED


def test_clarification_lifecycle_with_other_blocker(store, review):
    exc = _exc(store, "rx_037", "AMBIGUOUS_DRUG")

    rx = review.resolve(exc.exception_id, "REQUEST_CLARIFICATION")
    assert rx.status is PrescriptionStatus.AWAITING_CLARIFICATION
    assert rx.clarifications == [{"exception_id": exc.exception_id, "status": "REQUESTED"}]
    assert rx.audit_events[-1]["event"] == "CLARIFICATION_REQUESTED"

    rx = review.resolve(exc.exception_id, "CORRECT", "hydroxyzine HCl")
    assert rx.clarifications == [{"exception_id": exc.exception_id, "status": "RESOLVED"}]
    assert exc.exception_id not in [e.exception_id for e in rx.exceptions]
    assert rx.status is PrescriptionStatus.REVIEW_REQUIRED  # quantity conflict remains


def test_clarification_lifecycle_to_ready(store, review):
    exc = _exc(store, "rx_D", "AMBIGUOUS_DRUG")

    assert review.resolve(exc.exception_id, "REQUEST_CLARIFICATION").status is PrescriptionStatus.AWAITING_CLARIFICATION
    rx = review.resolve(exc.exception_id, "CORRECT", "hydroxyzine HCl")

    assert rx.clarifications[0]["status"] == "RESOLVED"
    assert rx.status is PrescriptionStatus.READY_FOR_VERIFICATION


def test_mark_unreadable_awaits_clarification(store, review):
    exc = _exc(store, "rx_C", "POSSIBLE_QUANTITY_CONFLICT")

    rx = review.resolve(exc.exception_id, "MARK_UNREADABLE")

    assert rx.fields["quantity"].decision is FieldDecision.UNREADABLE
    assert rx.fields["quantity"].raw_value == "50 mL"
    assert rx.fields["quantity"].resolution is None
    assert exc.exception_id in [e.exception_id for e in rx.exceptions]
    assert rx.status is PrescriptionStatus.AWAITING_CLARIFICATION


def test_request_clarification_is_idempotent(store, review):
    exc = _exc(store, "rx_D", "AMBIGUOUS_DRUG")
    review.resolve(exc.exception_id, "REQUEST_CLARIFICATION")

    rx = review.resolve(exc.exception_id, "REQUEST_CLARIFICATION")

    assert len(rx.clarifications) == 1


def test_reject_and_terminal_states(store, review):
    exc = _exc(store, "rx_037", "AMBIGUOUS_DRUG")

    rx = review.reject("rx_037")
    assert rx.status is PrescriptionStatus.REJECTED
    assert rx.audit_events[-1]["event"] == "PRESCRIPTION_REJECTED"
    assert review.reject("rx_037").status is PrescriptionStatus.REJECTED  # idempotent
    with pytest.raises(ConflictError):
        review.resolve(exc.exception_id, "SELECT_VALUE", "hydroxyzine HCl")
    with pytest.raises(ConflictError):
        review.approve("rx_037")


def test_approved_is_terminal(store, review):
    review.approve("rx_A")

    with pytest.raises(ConflictError):
        review.reject("rx_A")
    assert store.get("rx_A").status is PrescriptionStatus.APPROVED


def test_resolve_on_approved_is_conflict(store, review):
    rx = review.resolve(_exc(store, "rx_C", "POSSIBLE_QUANTITY_CONFLICT").exception_id, "CONFIRM")
    review.approve("rx_C")
    # Seed a stale exception to prove the terminal check fires first.
    rx = store.get("rx_C")
    rx.exceptions = processed("rx_C").exceptions
    store.save(rx)

    with pytest.raises(ConflictError):
        review.resolve(rx.exceptions[0].exception_id, "CONFIRM")


def test_approve_unknown_prescription(review):
    with pytest.raises(NotFoundError):
        review.approve("nope")


@pytest.mark.parametrize("action", ["CONFIRM", "CORRECT", "SELECT_VALUE", "MARK_UNREADABLE", "REQUEST_CLARIFICATION"])
def test_duplicate_document_only_rejects(review, action):
    store = review.store
    store.save(processed("rx_A", seen={"dup"}, sha="dup").model_copy(update={"prescription_id": "rx_A_2"}))
    dup = store.get("rx_A_2").exceptions[0]

    with pytest.raises(DomainError):
        review.resolve(dup.exception_id, action, "x")
    with pytest.raises(ConflictError):
        review.approve("rx_A_2")


def test_duplicate_document_reject(store, review):
    store.save(processed("rx_A", seen={"dup"}, sha="dup"))
    dup = store.get("rx_A").exceptions[0]

    rx = review.resolve(dup.exception_id, "REJECT")

    assert rx.status is PrescriptionStatus.REJECTED
