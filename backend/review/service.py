"""Pharmacist review: exception resolution, revalidation, approval, rejection.

`ReviewService.approve` is the only application code that assigns
PrescriptionStatus.APPROVED. That is the pharmacist authority boundary.
"""

import re
from dataclasses import asdict
from enum import StrEnum
from pathlib import Path

from backend.calls import CallRequest, CallResult, to_e164
from backend.calls.script import field_label, question_for
from backend.models import FieldDecision, Prescription, PrescriptionStatus, Resolution, RxException
from backend.pipeline import Clock, append_event, field_value, raise_field_exception, revalidate, utc_now
from backend.policy.router import TERMINAL_STATUSES, route_prescription
from backend.storage import MemoryStore

DEMO_PHARMACIST = "Demo Pharmacist"
CONFIRMABLE_TYPES = frozenset({"POSSIBLE_QUANTITY_CONFLICT", "IDENTIFIER_INVALID", "INVALID_STRENGTH"})
# The prescriber said on a call that another value on the prescription is wrong.
PRESCRIBER_CORRECTION = "PRESCRIBER_CORRECTION"


class ReviewError(Exception):
    pass


class DomainError(ReviewError):
    """Bad action or value for this exception (HTTP 400)."""


class NotFoundError(ReviewError):
    """HTTP 404."""


class ConflictError(ReviewError):
    """Action not allowed in the prescription's current state (HTTP 409)."""


class Action(StrEnum):
    CONFIRM = "CONFIRM"
    CORRECT = "CORRECT"
    SELECT_VALUE = "SELECT_VALUE"
    MARK_UNREADABLE = "MARK_UNREADABLE"
    REQUEST_CLARIFICATION = "REQUEST_CLARIFICATION"
    # Apply the value the prescriber confirmed on a call. The pharmacist's choice, never automatic.
    USE_PRESCRIBER_ANSWER = "USE_PRESCRIBER_ANSWER"
    REJECT = "REJECT"


class ReviewService:
    def __init__(self, store: MemoryStore, clock: Clock = utc_now) -> None:
        self.store = store
        self.clock = clock

    def resolve(self, exception_id: str, action: str, value: str | None = None) -> Prescription:
        with self.store.lock:
            found = self.store.find_exception(exception_id)
            if found is None:
                raise NotFoundError(f"No active exception {exception_id!r}.")
            rx, exc = found
            if rx.status in TERMINAL_STATUSES:
                raise ConflictError(f"Prescription is {rx.status.value}; exceptions can no longer be resolved.")
            try:
                act = Action(action)
            except ValueError:
                raise DomainError(f"Unknown action {action!r}.") from None

            if exc.type == "DUPLICATE_DOCUMENT" and act is not Action.REJECT:
                raise DomainError("A duplicate document can only be resolved with REJECT.")

            match act:
                case Action.REJECT:
                    self._reject(rx)
                    self.store.save(rx)
                    return rx
                case Action.CONFIRM | Action.CORRECT | Action.SELECT_VALUE:
                    self._resolve_value(rx, exc, act, self._value_for(rx, exc, act, value))
                case Action.USE_PRESCRIBER_ANSWER:
                    call = self._answered_call(rx, exc)
                    call["applied"] = True
                    self._resolve_value(
                        rx, exc, act, call["answer"],
                        source="PRESCRIBER_PHONE_CLARIFICATION",
                        reason="Confirmed by the prescriber on a call; applied by the pharmacist.",
                        evidence={"call_id": call["call_id"], "simulated": call["simulated"], "summary": call["summary"]},
                    )
                case Action.MARK_UNREADABLE:
                    field = self._field(rx, exc)
                    field.decision = FieldDecision.UNREADABLE
                    field.reason = "Pharmacist marked the source unreadable; awaiting clarification."
                    self._request_clarification(rx, exc)
                case Action.REQUEST_CLARIFICATION:
                    self._request_clarification(rx, exc)

            revalidate(rx, self.clock)
            self.store.save(rx)
            return rx

    def start_call(self, exception_id: str, simulated: bool) -> tuple[Prescription, CallRequest]:
        """Record that the prescriber is being called about one exception. The caller runs separately;
        its result comes back through finish_call."""
        with self.store.lock:
            found = self.store.find_exception(exception_id)
            if found is None:
                raise NotFoundError(f"No active exception {exception_id!r}.")
            rx, exc = found
            if rx.status in TERMINAL_STATUSES:
                raise ConflictError(f"Prescription is {rx.status.value}; the prescriber can no longer be called.")
            if exc.field not in rx.fields:
                raise DomainError(f"{exc.type} can't be clarified by phone.")
            if any(c.get("exception_id") == exception_id and c.get("status") == "CALLING" for c in rx.clarifications):
                raise ConflictError("A call about this issue is already in progress.")
            number = _value(rx, "prescriber_phone")
            if to_e164(number) is None:
                raise DomainError("No usable prescriber phone number was read from the fax.")

            # Context the agent may mention: only values already verified, so a misread is never repeated.
            context = {k: v for k in ("drug", "strength", "sig")
                       if k != exc.field and _verified(rx, k) and (v := _value(rx, k))}
            label = field_label(exc.field)
            calls = sum(1 for c in rx.clarifications if c.get("channel") == "PHONE")
            request = CallRequest(
                call_id=f"{exception_id}__call_{calls + 1:02d}",
                prescription_id=rx.prescription_id,
                exception_id=exception_id,
                to_number=number,
                prescriber=_value(rx, "prescriber") or "the prescriber",
                patient=_value(rx, "patient") or "the patient",
                patient_dob=_value(rx, "patient_dob"),
                field=exc.field,
                field_label=label,
                question=question_for(exc.field, label, context, _quantity_conflict(rx, exc)),
                context=context,
                source_name=Path(rx.source.get("original_path") or "").stem or None,
                on_record={k: v for k in rx.fields if k != "signature_present" and (v := _value(rx, k))},
            )
            rx.clarifications.append({
                "exception_id": exception_id, "status": "CALLING", "channel": "PHONE", "call_id": request.call_id,
                "simulated": simulated, "to_number": number, "prescriber": request.prescriber,
                "field_label": label, "question": request.question, "started_at": self.clock(),
            })
            append_event(rx, self.clock, "PHARMACIST", "PRESCRIBER_CALL_STARTED", exception_id=exception_id,
                         call_id=request.call_id, simulated=simulated)
            rx.status = route_prescription(rx)
            self.store.save(rx)
            return rx, request

    def finish_call(self, prescription_id: str, call_id: str, result: CallResult) -> Prescription:
        """Record a call's outcome as evidence. Never resolves the exception: only the pharmacist does."""
        with self.store.lock:
            rx = self._get(prescription_id)
            record = next((c for c in rx.clarifications if c.get("call_id") == call_id), None)
            if record is None:
                raise NotFoundError(f"No call {call_id!r}.")
            record.update(
                status=result.outcome,
                answer=result.answer if result.outcome == "ANSWERED" else None,
                summary=result.summary,
                transcript=[asdict(t) for t in result.transcript],
                provider_call_id=result.provider_call_id,
                ended_at=self.clock(),
                corrections=self._raise_corrections(rx, record, result),
            )
            rx.audit_events.extend(result.prism_events)
            append_event(rx, self.clock, "SYSTEM", "PRESCRIBER_CALL_ENDED", exception_id=record["exception_id"],
                         call_id=call_id, outcome=result.outcome)
            rx.status = route_prescription(rx)
            self.store.save(rx)
            return rx

    def approve(self, prescription_id: str, approved_by: str = DEMO_PHARMACIST) -> Prescription:
        with self.store.lock:
            rx = self._get(prescription_id)
            if rx.status is not PrescriptionStatus.READY_FOR_VERIFICATION or rx.exceptions:
                raise ConflictError(f"Prescription is {rx.status.value}; only READY_FOR_VERIFICATION can be approved.")
            rx.status = PrescriptionStatus.APPROVED
            rx.approved_by = approved_by
            append_event(rx, self.clock, "PHARMACIST", "PRESCRIPTION_APPROVED", approved_by=approved_by)
            self.store.save(rx)
            return rx

    def reject(self, prescription_id: str) -> Prescription:
        with self.store.lock:
            rx = self._get(prescription_id)
            self._reject(rx)
            self.store.save(rx)
            return rx

    # --- internals ----------------------------------------------------------

    def _get(self, prescription_id: str) -> Prescription:
        rx = self.store.get(prescription_id)
        if rx is None:
            raise NotFoundError(f"No prescription {prescription_id!r}.")
        return rx

    def _reject(self, rx: Prescription) -> None:
        if rx.status is PrescriptionStatus.APPROVED:
            raise ConflictError("An approved prescription cannot be rejected.")
        if rx.status is PrescriptionStatus.REJECTED:
            return
        rx.status = PrescriptionStatus.REJECTED
        append_event(rx, self.clock, "PHARMACIST", "PRESCRIPTION_REJECTED")

    def _field(self, rx: Prescription, exc: RxException):
        field = rx.fields.get(exc.field)
        if field is None:
            raise DomainError(f"Exception {exc.exception_id!r} does not refer to a field.")
        return field

    def _value_for(self, rx: Prescription, exc: RxException, act: Action, value: str | None) -> str:
        field = self._field(rx, exc)
        if act is Action.SELECT_VALUE:
            if value is None or value not in exc.candidate_values:
                raise DomainError("SELECT_VALUE requires one of the exception's candidate values.")
            return value
        if act is Action.CORRECT:
            if value is None or not value.strip():
                raise DomainError("CORRECT requires a non-empty value.")
            return value.strip()
        # CONFIRM: the pharmacist keeps the value as written.
        if exc.type not in CONFIRMABLE_TYPES:
            raise DomainError(f"CONFIRM is not valid for {exc.type}; use SELECT_VALUE or CORRECT.")
        confirmed = field.normalized_value or field.raw_value or next(iter(field.candidates), None)
        if not confirmed:
            raise DomainError("There is no current value to confirm.")
        if "?" in confirmed:
            raise DomainError("The current value contains an unreadable character; use SELECT_VALUE or CORRECT.")
        return confirmed

    def _raise_corrections(self, rx: Prescription, call: dict, result: CallResult) -> list[dict]:
        """Each value the prescriber corrected becomes a pharmacist decision on that field; nothing is changed.
        Skipped: values that match what we have, fields with an open issue already, fields a pharmacist set."""
        asked = next((e.field for e in rx.exceptions if e.exception_id == call["exception_id"]), None)
        open_fields = {e.field for e in rx.exceptions}
        raised = []
        for correction in result.corrections:
            field = rx.fields.get(correction.field)
            current = _value(rx, correction.field)
            record = {"field": correction.field, "value": correction.value, "quote": correction.quote, "exception_id": None}
            if (rx.status in TERMINAL_STATUSES or field is None or correction.field == asked or correction.field in open_fields
                    or field.decision is FieldDecision.HUMAN_VERIFIED or _same(current, correction.value)):
                raised.append(record)
                continue
            label = field_label(correction.field).lower()
            said = f' ("{correction.quote}")' if correction.quote else ""
            exc = raise_field_exception(
                rx, self.clock, correction.field, PRESCRIBER_CORRECTION,
                f"On the call, {call['prescriber']} said the {label} is {correction.value}{said}; the fax reads {current}.",
                [current, correction.value] if current else [correction.value],
            )
            open_fields.add(correction.field)
            record["exception_id"] = exc.exception_id
            raised.append(record)
        return raised

    def _answered_call(self, rx: Prescription, exc: RxException) -> dict:
        answered = [c for c in rx.clarifications
                    if c.get("exception_id") == exc.exception_id and c.get("status") == "ANSWERED" and c.get("answer")]
        if not answered:
            raise DomainError("There is no answer from the prescriber to use for this issue.")
        return answered[-1]

    def _resolve_value(self, rx: Prescription, exc: RxException, act: Action, value: str,
                       source: str = "PHARMACIST_SOURCE_REVIEW",
                       reason: str = "Resolved by pharmacist review of the source.",
                       evidence: dict | None = None) -> None:
        field = self._field(rx, exc)
        # raw_value, reads, signals and candidates are preserved.
        field.resolution = Resolution(
            source=source,
            value=value,
            confirmed_by={"name": DEMO_PHARMACIST, "role": "PHARMACIST"},
            evidence=evidence,
            approved_by=DEMO_PHARMACIST,
        )
        field.normalized_value = value
        field.decision = FieldDecision.HUMAN_VERIFIED
        field.reason = reason

        rx.exceptions = [e for e in rx.exceptions if e.exception_id != exc.exception_id]
        for record in rx.clarifications:
            if record.get("exception_id") == exc.exception_id and record.get("status") == "REQUESTED":
                record["status"] = "RESOLVED"
        append_event(rx, self.clock, "PHARMACIST", "EXCEPTION_RESOLVED", exception_id=exc.exception_id, action=act.value)

    def _request_clarification(self, rx: Prescription, exc: RxException) -> None:
        if any(
            c.get("exception_id") == exc.exception_id and c.get("status") == "REQUESTED" for c in rx.clarifications
        ):
            return
        rx.clarifications.append({"exception_id": exc.exception_id, "status": "REQUESTED"})
        append_event(rx, self.clock, "PHARMACIST", "CLARIFICATION_REQUESTED", exception_id=exc.exception_id)


def _quantity_conflict(rx: Prescription, exc: RxException) -> tuple[str, str] | None:
    """(written, implied by the directions) for a quantity conflict, else None."""
    if exc.type != "POSSIBLE_QUANTITY_CONFLICT":
        return None
    written = rx.fields["quantity"].raw_value if "quantity" in rx.fields else None
    implied = next((c for c in exc.candidate_values if not _same(c, written)), None)
    return (written, implied) if written and implied else None


def _same(a: str | None, b: str | None) -> bool:
    """Equal ignoring case, spacing and punctuation ("11/06/1966" == "11-06-1966")."""
    key = lambda v: re.sub(r"[\W_]", "", (v or "").lower())  # noqa: E731
    return key(a) == key(b)


def _verified(rx: Prescription, name: str) -> bool:
    field = rx.fields.get(name)
    return field is not None and field.decision in (FieldDecision.VERIFIED, FieldDecision.HUMAN_VERIFIED)


def _value(rx: Prescription, name: str) -> str | None:
    field = rx.fields.get(name)
    value = (field.normalized_value or field_value(field)) if field else None
    return value.strip() if value and value.strip() else None
