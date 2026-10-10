"""Dependency-driven revalidation: an active exception never makes its field
immune to re-checking, but HUMAN_VERIFIED and pharmacist-marked UNREADABLE
fields are never reopened, and only dependency-driven exception types are
cleared or re-typed automatically."""

import pytest
from fastapi.testclient import TestClient

from backend.extraction import RawField
from backend.main import create_app
from backend.models import FieldDecision, FieldResult, PrescriptionStatus, SignalStatus, SourceQuality
from backend.pipeline import process, revalidate
from backend.review import ReviewService
from backend.storage import MemoryStore
from backend.tests.conftest import fixed_clock, processed, raw_fixture

UNSUPPORTED_SIG = "1 TAB PO TID XQZ"  # unsupported token; arithmetic still runs: 1 x 3 x 30 = 90


def crafted(pid, patient_identity=None, drop=(), **overrides):
    """A stub raw fixture with field values (and their reads) replaced in memory."""
    raw = raw_fixture(pid)
    fields = {k: v for k, v in raw.fields.items() if k not in drop}
    for name, change in overrides.items():
        if isinstance(change, str):
            change = {"raw_value": change, "reads": [r.model_copy(update={"value": change}) for r in fields[name].reads]}
        fields[name] = RawField.model_validate({**fields[name].model_dump(), **change})
    update = {"fields": fields}
    if patient_identity is not None:
        update["patient_identity"] = patient_identity
    return raw.model_copy(update=update)


def setup(raw):
    store = MemoryStore()
    rx = process(raw, set(), f"sha-{raw.prescription_id}", fixed_clock)
    store.save(rx)
    return store, ReviewService(store, clock=fixed_clock), rx


def exc(rx, exc_type):
    matches = [e for e in rx.exceptions if e.type == exc_type]
    assert len(matches) == 1, [e.type for e in rx.exceptions]
    return matches[0]


def latest(rx, field, signal_type):
    return [s for s in rx.fields[field].signals if s.type == signal_type][-1]


def events(rx):
    return [e["event"] for e in rx.audit_events]


@pytest.fixture
def sig_case():
    """Clean A with an unsupported SIG token: UNSUPPORTED_SIG + POSSIBLE_QUANTITY_CONFLICT (90 vs 30)."""
    store, review, rx = setup(crafted("rx_A", sig=UNSUPPORTED_SIG))
    assert [e.type for e in rx.exceptions] == ["UNSUPPORTED_SIG", "POSSIBLE_QUANTITY_CONFLICT"]
    assert exc(rx, "POSSIBLE_QUANTITY_CONFLICT").candidate_values == ["30", "90"]
    return store, review, rx


@pytest.fixture
def strength_case():
    """rx_D with 75 mg: marketed for neither hydroxyzine HCl nor hydralazine HCl -> INVALID_STRENGTH."""
    store, review, rx = setup(crafted("rx_D", strength="75 mg"))
    assert [e.type for e in rx.exceptions] == ["AMBIGUOUS_DRUG", "INVALID_STRENGTH"]
    return store, review, rx


# 1 -------------------------------------------------------------------------


def test_quantity_blocker_cleared_when_sig_corrected(sig_case):
    store, review, rx = sig_case
    qty_id = exc(rx, "POSSIBLE_QUANTITY_CONFLICT").exception_id

    rx = review.resolve(exc(rx, "UNSUPPORTED_SIG").exception_id, "CORRECT", "1 TAB PO QD")

    assert rx.exceptions == []
    assert rx.fields["quantity"].decision is FieldDecision.VERIFIED
    assert rx.fields["quantity"].raw_value == "30"
    statuses = [s.status for s in rx.fields["quantity"].signals if s.type == "QUANTITY_SIG"]
    assert statuses == [SignalStatus.FAIL, SignalStatus.PASS]
    assert {"event": "EXCEPTION_CLEARED", "exception_id": qty_id, "reason": "dependency resolved"}.items() <= next(
        e for e in rx.audit_events if e["event"] == "EXCEPTION_CLEARED"
    ).items()
    assert next(e for e in rx.audit_events if e["event"] == "EXCEPTION_CLEARED")["actor"] == "SYSTEM"
    assert rx.status is PrescriptionStatus.READY_FOR_VERIFICATION


# 2 -------------------------------------------------------------------------


def test_quantity_exception_updated_in_place(sig_case):
    store, review, rx = sig_case
    qty_id = exc(rx, "POSSIBLE_QUANTITY_CONFLICT").exception_id

    rx = review.resolve(exc(rx, "UNSUPPORTED_SIG").exception_id, "CORRECT", "1 TAB PO BID")

    qty = exc(rx, "POSSIBLE_QUANTITY_CONFLICT")
    assert qty.exception_id == qty_id
    assert qty.candidate_values == ["30", "60"]
    assert latest(rx, "quantity", "QUANTITY_SIG").detail == "Directions imply 60 but prescription states 30."
    assert "EXCEPTION_UPDATED" in events(rx)
    assert "EXCEPTION_CLEARED" not in events(rx)
    assert rx.status is PrescriptionStatus.REVIEW_REQUIRED


# 3-5 -----------------------------------------------------------------------


def test_drug_correction_clears_stale_invalid_strength(strength_case):
    store, review, rx = strength_case

    rx = review.resolve(exc(rx, "AMBIGUOUS_DRUG").exception_id, "CORRECT", "metoprolol tartrate")

    assert rx.exceptions == []
    assert rx.fields["strength"].decision is FieldDecision.VERIFIED
    assert latest(rx, "strength", "MARKETED_STRENGTH").status is SignalStatus.PASS
    assert rx.status is PrescriptionStatus.READY_FOR_VERIFICATION


def test_still_invalid_strength_keeps_one_exception(strength_case):
    store, review, rx = strength_case
    strength_id = exc(rx, "INVALID_STRENGTH").exception_id

    rx = review.resolve(exc(rx, "AMBIGUOUS_DRUG").exception_id, "SELECT_VALUE", "hydralazine HCl")

    invalid = exc(rx, "INVALID_STRENGTH")
    assert invalid.exception_id == strength_id
    assert invalid.candidate_values == ["75 mg"]
    assert rx.fields["strength"].decision is FieldDecision.INVALID
    assert latest(rx, "strength", "MARKETED_STRENGTH").detail == "75 mg is not a marketed strength of hydralazine HCl."
    assert rx.status is PrescriptionStatus.REVIEW_REQUIRED


def test_reference_gap_does_not_stay_invalid(strength_case):
    store, review, rx = strength_case
    strength_id = exc(rx, "INVALID_STRENGTH").exception_id

    rx = review.resolve(exc(rx, "AMBIGUOUS_DRUG").exception_id, "CORRECT", "zzz unlisted drug")

    assert rx.fields["strength"].decision is not FieldDecision.INVALID
    assert latest(rx, "strength", "MARKETED_STRENGTH").status is SignalStatus.WARNING
    assert strength_id not in [e.exception_id for e in rx.exceptions]
    assert any(e.get("exception_id") == strength_id and e["event"] == "EXCEPTION_CLEARED" for e in rx.audit_events)


# 6-8 -----------------------------------------------------------------------


def test_mark_unreadable_is_not_overridden(sig_case):
    store, review, rx = sig_case
    qty_id = exc(rx, "POSSIBLE_QUANTITY_CONFLICT").exception_id
    review.resolve(qty_id, "MARK_UNREADABLE")

    rx = review.resolve(exc(store.get("rx_A"), "UNSUPPORTED_SIG").exception_id, "CORRECT", "1 TAB PO QD")

    assert rx.fields["quantity"].decision is FieldDecision.UNREADABLE
    assert [e.exception_id for e in rx.exceptions] == [qty_id]
    assert rx.clarifications == [{"exception_id": qty_id, "status": "REQUESTED"}]
    assert rx.status is PrescriptionStatus.AWAITING_CLARIFICATION
    assert "EXCEPTION_CLEARED" not in events(rx)


def test_clarification_withdrawn_when_blocker_disappears(sig_case):
    store, review, rx = sig_case
    qty_id = exc(rx, "POSSIBLE_QUANTITY_CONFLICT").exception_id
    assert review.resolve(qty_id, "REQUEST_CLARIFICATION").status is PrescriptionStatus.AWAITING_CLARIFICATION

    rx = review.resolve(exc(store.get("rx_A"), "UNSUPPORTED_SIG").exception_id, "CORRECT", "1 TAB PO QD")

    assert rx.exceptions == []
    assert rx.clarifications == [{"exception_id": qty_id, "status": "WITHDRAWN"}]
    assert rx.status is PrescriptionStatus.READY_FOR_VERIFICATION
    assert any(e["event"] == "EXCEPTION_CLEARED" and e["exception_id"] == qty_id for e in rx.audit_events)


def test_human_verified_never_reopened(sig_case):
    store, review, rx = sig_case
    review.resolve(exc(rx, "POSSIBLE_QUANTITY_CONFLICT").exception_id, "CONFIRM")
    before = store.get("rx_A").fields["quantity"]

    # 1 x BID x 30 = 60 would disagree with the confirmed 30.
    rx = review.resolve(exc(store.get("rx_A"), "UNSUPPORTED_SIG").exception_id, "CORRECT", "1 TAB PO BID")

    assert rx.fields["quantity"] == before
    assert rx.fields["quantity"].decision is FieldDecision.HUMAN_VERIFIED
    assert "POSSIBLE_QUANTITY_CONFLICT" not in [e.type for e in rx.exceptions]
    assert rx.status is PrescriptionStatus.READY_FOR_VERIFICATION


# 9 -------------------------------------------------------------------------


def test_unchanged_quantity_exception_is_silent():
    store = MemoryStore()
    store.save(processed("rx_037"))
    review = ReviewService(store, clock=fixed_clock)
    before = store.get("rx_037")
    qty_before = exc(before, "POSSIBLE_QUANTITY_CONFLICT")
    assert qty_before.exception_id == "rx_037__exc_02"

    rx = review.resolve("rx_037__exc_01", "SELECT_VALUE", "hydroxyzine HCl")

    assert [e.model_dump() for e in rx.exceptions] == [qty_before.model_dump()]
    assert rx.fields["quantity"].signals == before.fields["quantity"].signals
    assert rx.audit_events == before.audit_events + [
        {"ts": fixed_clock(), "actor": "PHARMACIST", "event": "EXCEPTION_RESOLVED", "exception_id": "rx_037__exc_01", "action": "SELECT_VALUE"}
    ]


# Addendum A — ids are never reused ------------------------------------------


def test_cleared_exception_id_is_never_reissued(sig_case, tmp_path):
    store, review, rx = sig_case
    issued = {e.exception_id for e in rx.exceptions}
    assert issued == {"rx_A__exc_01", "rx_A__exc_02"}
    review.resolve("rx_A__exc_01", "CORRECT", "1 TAB PO QD")  # clears rx_A__exc_02
    assert store.get("rx_A").exceptions == []

    # Simulate a later dependency change (test-only mutation): 1 x QD x 60 = 60 vs stated 30.
    rx = store.get("rx_A")
    rx.fields["days_supply"].raw_value = "60"
    revalidate(rx, fixed_clock)
    store.save(rx)

    new = exc(rx, "POSSIBLE_QUANTITY_CONFLICT")
    assert new.exception_id == "rx_A__exc_03"
    assert new.exception_id not in issued
    assert new.candidate_values == ["30", "60"]

    with TestClient(create_app(store=store, upload_dir=tmp_path)) as client:
        assert client.post("/api/exceptions/rx_A__exc_02/resolve", json={"action": "CONFIRM"}).status_code == 404
        r = client.post("/api/exceptions/rx_A__exc_03/resolve", json={"action": "CONFIRM"})
    assert r.status_code == 200
    assert r.json()["fields"]["quantity"]["decision"] == "HUMAN_VERIFIED"
    assert r.json()["exceptions"] == []


# Addendum B — only dependency-driven types are auto-reconciled -------------


def _unreadable_prescriber():
    return {"source_quality": "UNREADABLE"}


def _identity_conflict():
    raw = raw_fixture("rx_A")
    return raw.patient_identity.model_copy(update={"block_name": "John Miller"})


LOCKED_CASES = {
    "AMBIGUOUS_DRUG": lambda: raw_fixture("rx_D"),
    "AMBIGUOUS_STRENGTH": lambda: crafted("rx_A", strength={"reads": [{"source": "primary", "value": "10 mg"}, {"source": "secondary", "value": "40 mg"}]}),
    "UNVERIFIED_DRUG": lambda: raw_fixture("rx_F"),
    "UNSUPPORTED_SIG": lambda: crafted("rx_A", sig=UNSUPPORTED_SIG, days_supply="", quantity="30"),
    "UNREADABLE_SOURCE": lambda: crafted("rx_A", prescriber=_unreadable_prescriber()),
    "MISSING_FIELD": lambda: crafted("rx_A", drop=("prescriber",)),
    "MISSING_EVIDENCE": lambda: crafted("rx_A", sig={"evidence": None}),
    "PATIENT_IDENTITY_CONFLICT": lambda: crafted("rx_A", patient_identity=_identity_conflict()),
    "IDENTIFIER_INVALID": lambda: raw_fixture("rx_E"),
}


@pytest.mark.parametrize("exc_type", sorted(LOCKED_CASES))
def test_non_dependency_exceptions_are_not_reconciled(exc_type):
    raw = LOCKED_CASES[exc_type]()
    rx = process(raw, set(), "h", fixed_clock)
    target = exc(rx, exc_type).model_dump()
    decision = rx.fields[target["field"]].decision

    # Unrelated change, then revalidate with full inputs.
    rx.fields["refills"] = FieldResult(raw_value="2", source_quality=SourceQuality.CLEAR, decision=FieldDecision.EXTRACTED)
    revalidate(rx, fixed_clock, patient_identity=raw.patient_identity)

    assert exc(rx, exc_type).model_dump() == target
    assert rx.fields[target["field"]].decision is decision
    assert "EXCEPTION_CLEARED" not in events(rx)


def test_locked_exception_survives_even_if_condition_disappears():
    rx = process(crafted("rx_A", sig=UNSUPPORTED_SIG, days_supply="", quantity="30"), set(), "h", fixed_clock)
    target = exc(rx, "UNSUPPORTED_SIG").model_dump()

    rx.fields["sig"].raw_value = "1 TAB PO QD"  # test-only: the pending human decision still owns this field
    revalidate(rx, fixed_clock)

    assert exc(rx, "UNSUPPORTED_SIG").model_dump() == target
    assert rx.fields["sig"].decision is FieldDecision.REVIEW_REQUIRED


def test_document_level_exception_untouched():
    rx = processed("rx_A", seen={"dup"}, sha="dup")
    dup = exc(rx, "DUPLICATE_DOCUMENT").model_dump()

    revalidate(rx, fixed_clock)

    assert exc(rx, "DUPLICATE_DOCUMENT").model_dump() == dup


# Addendum C — idempotence ---------------------------------------------------


@pytest.mark.parametrize("pid", ["rx_037", "rx_A", "rx_C", "rx_D", "rx_E", "rx_F"])
def test_revalidate_without_changes_is_idempotent(pid):
    rx = processed(pid)
    before = rx.model_dump(mode="json")

    revalidate(rx, fixed_clock)

    assert rx.model_dump(mode="json") == before


@pytest.mark.parametrize("pid", ["rx_037", "rx_A", "rx_C", "rx_D", "rx_E", "rx_F"])
def test_initial_processing_unchanged(pid):
    expected = {
        "rx_037": (PrescriptionStatus.REVIEW_REQUIRED, ["AMBIGUOUS_DRUG", "POSSIBLE_QUANTITY_CONFLICT"]),
        "rx_A": (PrescriptionStatus.READY_FOR_VERIFICATION, []),
        "rx_C": (PrescriptionStatus.REVIEW_REQUIRED, ["POSSIBLE_QUANTITY_CONFLICT"]),
        "rx_D": (PrescriptionStatus.REVIEW_REQUIRED, ["AMBIGUOUS_DRUG"]),
        "rx_E": (PrescriptionStatus.REVIEW_REQUIRED, ["IDENTIFIER_INVALID"]),
        "rx_F": (PrescriptionStatus.REVIEW_REQUIRED, ["UNVERIFIED_DRUG"]),
    }[pid]
    rx = processed(pid)

    assert (rx.status, [e.type for e in rx.exceptions]) == expected
    assert [e.exception_id for e in rx.exceptions] == [f"{pid}__exc_{i:02d}" for i in range(1, len(rx.exceptions) + 1)]


# 10 — API -------------------------------------------------------------------


def test_api_dependency_fix_clears_stale_exception(tmp_path):
    store = MemoryStore()
    store.save(process(crafted("rx_A", sig=UNSUPPORTED_SIG), set(), "h", fixed_clock))

    with TestClient(create_app(store=store, upload_dir=tmp_path)) as client:
        assert client.get("/api/prescriptions").json()[0]["unresolved_count"] == 2

        r = client.post("/api/exceptions/rx_A__exc_01/resolve", json={"action": "CORRECT", "value": "1 TAB PO QD"})
        assert r.status_code == 200
        body = r.json()
        assert body["exceptions"] == []
        assert body["status"] == "READY_FOR_VERIFICATION"
        assert body["fields"]["quantity"]["decision"] == "VERIFIED"

        queue = client.get("/api/prescriptions").json()
        assert queue[0]["unresolved_count"] == 0
        assert queue[0]["status"] == "READY_FOR_VERIFICATION"
