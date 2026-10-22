"""Call prescriber: the call is evidence for the pharmacist, never a resolution."""

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.calls import CallError, CallRequest, CallResult, Correction, Turn, to_e164
from backend.calls.charts import chart_for
from backend.calls.elevenlabs import ElevenLabsCaller
from backend.calls.script import question_for
from backend.calls.simulated import SimulatedCaller
from backend.extraction import RawField
from backend.main import create_app
from backend.models import FieldDecision, PrescriptionStatus
from backend.pipeline import process
from backend.review import ConflictError, DomainError, ReviewService
from backend.storage import MemoryStore
from backend.tests.conftest import fixed_clock, raw_fixture

BACKEND = Path(__file__).resolve().parents[1]
PHONE = "(718) 555-0177"


def _with_phone(pid="rx_037", phone=PHONE):
    raw = raw_fixture(pid)
    if phone is not None:
        field = raw.fields["prescriber"].model_copy(update={"raw_value": phone})
        raw = raw.model_copy(update={"fields": {**raw.fields, "prescriber_phone": RawField.model_validate(field.model_dump())}})
    return process(raw, set(), f"sha-{pid}", clock=fixed_clock)


@pytest.fixture
def store():
    s = MemoryStore()
    s.save(_with_phone())
    return s


@pytest.fixture
def review(store):
    return ReviewService(store, clock=fixed_clock)


def _exc(store, exc_type, pid="rx_037"):
    return next(e for e in store.get(pid).exceptions if e.type == exc_type)


def _answered(value="90"):
    return CallResult("ANSWERED", value, f"Prescriber confirmed {value}.",
                      [Turn("agent", "What quantity should we dispense?"), Turn("prescriber", f"{value}, please.")])


# --- script and helpers ---------------------------------------------------


def test_phone_field_is_optional_and_never_blocks():
    rx = _with_phone()
    assert rx.fields["prescriber_phone"].decision is FieldDecision.VERIFIED
    assert not any(e.field == "prescriber_phone" for e in rx.exceptions)


@pytest.mark.parametrize(("number", "e164"), [
    ("(718) 555-0177", "+17185550177"), ("1-718-555-0177", "+17185550177"), ("555-0177", None), (None, None),
])
def test_to_e164(number, e164):
    assert to_e164(number) == e164


def test_questions_are_open_and_never_suggest_the_value_read():
    question = question_for("strength", "Strength", {"drug": "Metoprolol tartrate", "strength": "15 mg"})
    assert question == "What strength did you prescribe for the Metoprolol tartrate?"
    assert "15" not in question
    # A drug with unreadable characters is never repeated to the prescriber.
    assert question_for("strength", "Strength", {"drug": "Hyd???ne HCl"}) == "What strength did you prescribe?"


def test_quantity_conflict_question_states_both_numbers():
    question = question_for("quantity", "Quantity", {"sig": "Take 10 mL by mouth three times daily for 10 days."},
                            conflict=("50 mL", "300 mL"))
    assert question == ('The directions, "Take 10 mL by mouth three times daily for 10 days", work out to 300 mL, '
                        "but the fax says to dispense 50 mL. What quantity did you intend?")
    # Other quantity questions stay open.
    assert "50" not in question_for("quantity", "Quantity", {"sig": "1 tab po tid"})


def test_demo_charts_hold_what_the_prescriber_wrote():
    assert chart_for("demo_B")["strength"] == "75 mg"
    assert chart_for("rx_unknown") is None and chart_for(None) is None


def test_demo_e_prescriber_knows_the_valid_npi():
    import json
    truth = {r["id"]: r for r in json.loads((BACKEND.parent / "fixtures/demo/truth.json").read_text())}
    assert chart_for("demo_E")["your NPI"] == truth["demo_E"]["valid_npi_before_corruption"]


def test_only_the_simulation_reads_demo_charts():
    """The ground truth is the simulated prescriber's knowledge, never RxBridge's."""
    importers = []
    for path in BACKEND.rglob("*.py"):
        if "tests" in path.parts or path.name in ("charts.py", "simulated.py"):
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith(("calls.charts", "calls.simulated")):
                importers.append(path.relative_to(BACKEND).as_posix())
    assert importers == ["calls/__init__.py"]  # lazily, inside get_caller()


# --- simulated caller -----------------------------------------------------


class FakeGateway:
    """Replays prescriber replies and analysis JSON in call order."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.steps = []
        self.tracer = None

    def call(self, step, prescription_id, model, messages, max_tokens=8000):
        self.steps.append(step)
        return self.replies.pop(0)


def _request(source_name="demo_B"):
    return CallRequest(call_id="c1", prescription_id="demo_B", exception_id="e1", to_number=PHONE,
                       prescriber="James Walker, DO", patient="Barney Mitchell", patient_dob="2000-10-20",
                       field="strength", field_label="Strength", question="What strength did you prescribe?",
                       context={}, source_name=source_name,
                       on_record={"patient_dob": "1-06-1966", "strength": "15 mg", "drug": "Metoprolol tartrate"})


def test_simulated_call_answered_after_read_back():
    gateway = FakeGateway([
        "It's 75 milligrams.",
        '{"value": "75 mg", "confirmed": false, "summary": "Prescriber stated 75 mg."}',
        "Yes, that's right.",
        '{"value": "75 mg", "confirmed": true, "summary": "Prescriber stated 75 mg and confirmed it."}',
    ])
    result = SimulatedCaller(gateway=gateway, model="m").place_call(_request())

    assert (result.outcome, result.answer) == ("ANSWERED", "75 mg")
    assert gateway.steps == ["simulate_prescriber", "analyze_call", "simulate_prescriber", "analyze_call"]
    assert [t.role for t in result.transcript] == ["agent", "prescriber", "agent", "prescriber", "agent"]
    assert "75 mg" in result.transcript[2].text  # read back before it counts


def test_simulated_call_keeps_corrections_to_other_fields():
    gateway = FakeGateway([
        "Quick correction, her date of birth is November 6, 1966. The strength is 75 mg.",
        '{"value": "75 mg", "confirmed": false, "summary": "s", "corrections": ['
        '{"field": "patient_dob", "value": "11-06-1966", "quote": "her date of birth is November 6, 1966"},'
        '{"field": "strength", "value": "75 mg", "quote": "75 mg"},'
        '{"field": "not_a_field", "value": "x", "quote": ""}]}',
        "Yes.",
        '{"value": "75 mg", "confirmed": true, "summary": "Confirmed 75 mg.", "corrections": ['
        '{"field": "patient_dob", "value": "11-06-1966", "quote": "her date of birth is November 6, 1966"}]}',
    ])
    result = SimulatedCaller(gateway=gateway, model="m").place_call(_request())

    # The asked field and unknown fields are dropped; the DOB correction is kept and acknowledged on the call.
    assert result.corrections == [Correction("patient_dob", "11-06-1966", "her date of birth is November 6, 1966")]
    assert "I've noted that the date of birth is 11-06-1966" in result.transcript[2].text


def test_simulated_call_unclear_when_prescriber_defers():
    gateway = FakeGateway([
        "I don't have the chart in front of me, I'll call you back.",
        '{"value": null, "confirmed": false, "summary": "Prescriber deferred and will call back."}',
    ])
    result = SimulatedCaller(gateway=gateway, model="m").place_call(_request(source_name=None))

    assert (result.outcome, result.answer) == ("UNCLEAR", None)
    assert result.summary == "Prescriber deferred and will call back."


def test_simulated_call_unclear_when_read_back_is_not_confirmed():
    gateway = FakeGateway([
        "75.", '{"value": "75 mg", "confirmed": false, "summary": "s"}',
        "No, wait, let me check.", '{"value": null, "confirmed": false, "summary": "Prescriber was unsure."}',
    ])
    assert SimulatedCaller(gateway=gateway, model="m").place_call(_request()).outcome == "UNCLEAR"


def test_simulated_call_model_failure_is_a_call_error():
    gateway = FakeGateway(["75 mg", "not json"])
    with pytest.raises(CallError):
        SimulatedCaller(gateway=gateway, model="m").place_call(_request())


# --- ElevenLabs caller (no network) ---------------------------------------


def test_elevenlabs_refuses_numbers_not_on_the_allowlist(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("no request may be sent")

    monkeypatch.setattr("backend.calls.elevenlabs.httpx.request", no_network)
    caller = ElevenLabsCaller("key", "agent", "phone", allowlist=frozenset({"+12015550100"}))
    with pytest.raises(CallError, match="not on RXBRIDGE_CALL_ALLOWLIST"):
        caller.place_call(_request())


def test_elevenlabs_needs_configuration(monkeypatch):
    for key in ("ELEVENLABS_API_KEY", "ELEVENLABS_AGENT_ID", "ELEVENLABS_PHONE_NUMBER_ID"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(CallError):
        ElevenLabsCaller.from_env()


def test_elevenlabs_result_needs_a_confirmed_value():
    conversation = {
        "status": "done",
        "transcript": [{"role": "agent", "message": "What strength?"}, {"role": "user", "message": "75 mg."}],
        "analysis": {"data_collection_results": {
            "clarified_value": {"value": "75 mg", "rationale": "Stated 75 mg."},
            "value_confirmed": {"value": True, "rationale": "Agreed on read-back."},
        }},
    }
    result = ElevenLabsCaller._result(conversation, "conv_1")
    assert (result.outcome, result.answer, result.transcript[1].role) == ("ANSWERED", "75 mg", "prescriber")

    assert result.corrections == []

    conversation["analysis"]["data_collection_results"]["prescriber_corrections"] = {
        "value": '[{"field": "patient_dob", "value": "11-06-1966", "quote": "November 6"}, {"bad": 1}]'}
    assert ElevenLabsCaller._result(conversation, "conv_1").corrections == [
        Correction("patient_dob", "11-06-1966", "November 6")]

    conversation["analysis"]["data_collection_results"]["value_confirmed"]["value"] = False
    assert ElevenLabsCaller._result(conversation, "conv_1").outcome == "UNCLEAR"
    assert ElevenLabsCaller._result({"status": "failed"}, "conv_1").outcome == "FAILED"


# --- review service -------------------------------------------------------


def test_call_needs_a_phone_number():
    store = MemoryStore()
    store.save(_with_phone(phone=None))
    review = ReviewService(store, clock=fixed_clock)
    with pytest.raises(DomainError, match="phone"):
        review.start_call(_exc(store, "POSSIBLE_QUANTITY_CONFLICT").exception_id, simulated=True)


def test_calling_waits_on_the_prescriber_and_blocks_a_second_call(store, review):
    exc = _exc(store, "POSSIBLE_QUANTITY_CONFLICT")
    rx, request = review.start_call(exc.exception_id, simulated=True)

    assert rx.status is PrescriptionStatus.AWAITING_CLARIFICATION
    assert request.to_number == PHONE
    assert rx.clarifications[-1]["status"] == "CALLING" and rx.clarifications[-1]["simulated"] is True
    with pytest.raises(ConflictError):
        review.start_call(exc.exception_id, simulated=True)


def test_call_about_a_quantity_conflict_names_the_mismatch(store, review):
    _, request = review.start_call(_exc(store, "POSSIBLE_QUANTITY_CONFLICT").exception_id, simulated=True)
    assert "work out to 90, but the fax says to dispense 30" in request.question


def test_question_never_names_an_unverified_drug(store, review):
    # rx_037's drug is ambiguous, so the quantity question must not name it.
    _, request = review.start_call(_exc(store, "POSSIBLE_QUANTITY_CONFLICT").exception_id, simulated=True)
    assert "drug" not in request.context
    assert "hydro" not in request.question.lower()


def test_answer_is_evidence_until_the_pharmacist_uses_it(store, review):
    exc = _exc(store, "POSSIBLE_QUANTITY_CONFLICT")
    _, request = review.start_call(exc.exception_id, simulated=True)
    rx = review.finish_call("rx_037", request.call_id, _answered("90"))

    assert rx.status is PrescriptionStatus.REVIEW_REQUIRED  # still the pharmacist's decision
    assert any(e.exception_id == exc.exception_id for e in rx.exceptions)
    assert rx.fields["quantity"].decision is not FieldDecision.HUMAN_VERIFIED
    call = rx.clarifications[-1]
    assert (call["status"], call["answer"]) == ("ANSWERED", "90")
    assert call["transcript"][1] == {"role": "prescriber", "text": "90, please."}

    rx = review.resolve(exc.exception_id, "USE_PRESCRIBER_ANSWER")
    field = rx.fields["quantity"]
    assert field.decision is FieldDecision.HUMAN_VERIFIED
    assert (field.resolution.source, field.resolution.value) == ("PRESCRIBER_PHONE_CLARIFICATION", "90")
    assert field.resolution.evidence["call_id"] == request.call_id
    assert field.resolution.confirmed_by == {"name": "Demo Pharmacist", "role": "PHARMACIST"}
    assert rx.clarifications[-1]["applied"] is True


def test_prescriber_correction_becomes_a_pharmacist_decision(store, review):
    exc = _exc(store, "POSSIBLE_QUANTITY_CONFLICT")
    _, request = review.start_call(exc.exception_id, simulated=True)
    assert request.on_record["patient"] == "James Peterson"

    result = _answered("90")
    result.corrections = [Correction("patient", "James Patterson", "it's Patterson, not Peterson")]
    rx = review.finish_call("rx_037", request.call_id, result)

    raised = next(e for e in rx.exceptions if e.type == "PRESCRIBER_CORRECTION")
    assert raised.field == "patient"
    assert raised.candidate_values == ["James Peterson", "James Patterson"]
    assert "Patterson" in raised.reason and "fax reads James Peterson" in raised.reason
    assert rx.fields["patient"].raw_value == "James Peterson"  # nothing changed, only flagged
    assert rx.fields["patient"].decision is FieldDecision.REVIEW_REQUIRED
    assert rx.clarifications[-1]["corrections"][0]["exception_id"] == raised.exception_id
    assert rx.status is PrescriptionStatus.REVIEW_REQUIRED

    # Applying the answer to the asked issue doesn't clear the correction: it needs its own decision.
    review.resolve(exc.exception_id, "USE_PRESCRIBER_ANSWER")
    review.resolve(_exc(store, "AMBIGUOUS_DRUG").exception_id, "SELECT_VALUE", "hydroxyzine HCl")
    with pytest.raises(ConflictError):
        review.approve("rx_037")
    rx = review.resolve(raised.exception_id, "SELECT_VALUE", "James Patterson")
    assert rx.fields["patient"].normalized_value == "James Patterson"
    assert rx.status is PrescriptionStatus.READY_FOR_VERIFICATION


@pytest.mark.parametrize("correction", [
    Correction("patient", "james  peterson", ""),          # same as the fax, ignoring case and spacing
    Correction("quantity", "120", ""),                      # the asked field: that's the answer, not a correction
    Correction("drug", "hydralazine HCl", ""),               # already has an open issue
    Correction("not_a_field", "x", ""),
])
def test_corrections_that_need_no_new_issue(store, review, correction):
    exc = _exc(store, "POSSIBLE_QUANTITY_CONFLICT")
    _, request = review.start_call(exc.exception_id, simulated=True)
    result = _answered("90")
    result.corrections = [correction]
    rx = review.finish_call("rx_037", request.call_id, result)

    assert not any(e.type == "PRESCRIBER_CORRECTION" for e in rx.exceptions)
    assert rx.clarifications[-1]["corrections"][0]["exception_id"] is None  # still recorded


def test_correction_after_rejection_is_recorded_not_raised(store, review):
    exc = _exc(store, "POSSIBLE_QUANTITY_CONFLICT")
    _, request = review.start_call(exc.exception_id, simulated=True)
    review.reject("rx_037")
    result = _answered("90")
    result.corrections = [Correction("patient", "James Patterson", "")]
    rx = review.finish_call("rx_037", request.call_id, result)

    assert rx.status is PrescriptionStatus.REJECTED
    assert not any(e.type == "PRESCRIBER_CORRECTION" for e in rx.exceptions)


@pytest.mark.parametrize("outcome", ["UNCLEAR", "FAILED"])
def test_unclear_call_hands_back_to_the_pharmacist(store, review, outcome):
    exc = _exc(store, "POSSIBLE_QUANTITY_CONFLICT")
    _, request = review.start_call(exc.exception_id, simulated=True)
    rx = review.finish_call("rx_037", request.call_id, CallResult(outcome, None, "Prescriber will call back."))

    assert rx.status is PrescriptionStatus.REVIEW_REQUIRED
    assert rx.clarifications[-1]["answer"] is None
    with pytest.raises(DomainError):
        review.resolve(exc.exception_id, "USE_PRESCRIBER_ANSWER")
    # The pharmacist can still decide themselves, or call again.
    review.start_call(exc.exception_id, simulated=True)


def test_no_call_after_rejection(store, review):
    exc = _exc(store, "POSSIBLE_QUANTITY_CONFLICT")
    review.reject("rx_037")
    with pytest.raises(ConflictError):
        review.start_call(exc.exception_id, simulated=True)


# --- API ------------------------------------------------------------------


class FakeCaller:
    name, simulated = "fake", True

    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def place_call(self, request):
        if self.error:
            raise self.error
        return self.result


@pytest.mark.parametrize(("caller", "status", "answer"), [
    (FakeCaller(result=_answered("90")), "ANSWERED", "90"),
    (FakeCaller(error=CallError("Line busy.")), "FAILED", None),
    (FakeCaller(error=RuntimeError("boom")), "FAILED", None),
])
def test_call_endpoint_records_the_outcome(store, tmp_path, monkeypatch, caller, status, answer):
    monkeypatch.delenv("RXBRIDGE_CALLER", raising=False)
    exc = _exc(store, "POSSIBLE_QUANTITY_CONFLICT")
    with TestClient(create_app(store=store, upload_dir=tmp_path, caller_factory=lambda: caller)) as client:
        started = client.post(f"/api/exceptions/{exc.exception_id}/call")
        assert started.status_code == 200, started.text
        assert started.json()["clarifications"][-1]["status"] == "CALLING"

        # TestClient runs background tasks before returning, so the call has ended.
        call = client.get("/api/prescriptions/rx_037").json()["clarifications"][-1]
    assert (call["status"], call["answer"]) == (status, answer)


def test_call_endpoint_errors(store, tmp_path):
    with TestClient(create_app(store=store, upload_dir=tmp_path, caller_factory=FakeCaller)) as client:
        assert client.post("/api/exceptions/nope/call").status_code == 404
