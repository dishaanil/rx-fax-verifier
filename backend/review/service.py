"""Pharmacist review: exception resolution, revalidation, approval, rejection.

`ReviewService.approve` is the only application code that assigns
PrescriptionStatus.APPROVED. That is the pharmacist authority boundary.
"""

from enum import StrEnum

from backend.models import FieldDecision, Prescription, PrescriptionStatus, Resolution, RxException
from backend.pipeline import Clock, append_event, revalidate, utc_now
from backend.policy.router import TERMINAL_STATUSES
from backend.storage import MemoryStore

DEMO_PHARMACIST = "Demo Pharmacist"
CONFIRMABLE_TYPES = frozenset({"POSSIBLE_QUANTITY_CONFLICT", "IDENTIFIER_INVALID", "INVALID_STRENGTH"})


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

    def _resolve_value(self, rx: Prescription, exc: RxException, act: Action, value: str) -> None:
        field = self._field(rx, exc)
        # raw_value, reads, signals and candidates are preserved.
        field.resolution = Resolution(
            source="PHARMACIST_SOURCE_REVIEW",
            value=value,
            confirmed_by={"name": DEMO_PHARMACIST, "role": "PHARMACIST"},
            approved_by=DEMO_PHARMACIST,
        )
        field.normalized_value = value
        field.decision = FieldDecision.HUMAN_VERIFIED
        field.reason = "Resolved by pharmacist review of the source."

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
