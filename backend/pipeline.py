"""Raw extraction -> canonical Prescription.

Deterministic only: no network, no model calls. The extractor's raw values,
reads and evidence are copied verbatim and never overwritten; this module
adds signals, candidates, normalized values, decisions and exceptions, then
routes the prescription. It never assigns APPROVED.
"""

import re
from collections.abc import Callable
from datetime import UTC, datetime

from backend.extraction.raw import PatientIdentity, RawPrescriptionExtraction
from backend.models import (
    CRITICAL_FIELDS,
    FieldDecision,
    FieldResult,
    Prescription,
    PrescriptionStatus,
    RxException,
    Signal,
    SignalStatus,
    SourceQuality,
)
from backend.normalization import normalize_sig, render_sig
from backend.policy import FieldRoute, evaluate_field, route_prescription
from backend.policy.router import latest_signals
from backend.references.catalog import lookup_all
from backend.references.strengths import drug_base_key, normalize_strength
from backend.validators import (
    validate_duplicate,
    validate_marketed_strength,
    validate_npi,
    validate_patient_identity,
    validate_quantity,
    validate_sig_tokens,
)
from backend.validators.cross_pass import validate_cross_pass
from backend.validators.lasa import validate_lasa
from backend.validators.quantity import format_quantity, implied_quantity
from backend.validators.reference import validate_reference
from backend.validators.strength_ambiguity import validate_strength_collision
from backend.validators.required_fields import check_required

Clock = Callable[[], str]

HUMAN_ACTION = "HUMAN_SELECTION_OR_CLARIFICATION"
DOCUMENT_FIELD = "document"
# Exceptions whose condition depends on another field's value. Only these are
# cleared or re-typed automatically when a dependency changes.
DEPENDENCY_DRIVEN_TYPES = frozenset({"POSSIBLE_QUANTITY_CONFLICT", "INVALID_STRENGTH"})

_WS_RE = re.compile(r"\s+")
# Pads write counts as "#30"; the "#" is a number sign, not part of the value.
_QUANTITY_RE = re.compile(r"^#?\s*(\d+(?:\.\d+)?)\s*([A-Za-z]+)?$")
_INT_RE = re.compile(r"^\d+$")
# Drug first: strength checks read the drug's evaluated state.
_EVALUATION_PRIORITY = {"drug": 0}


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def process(
    raw: RawPrescriptionExtraction,
    seen_hashes: set[str],
    sha256: str,
    clock: Clock = utc_now,
) -> Prescription:
    """Does not mutate `seen_hashes`; the caller records the hash."""
    fields = {name: _from_raw(rf) for name, rf in raw.fields.items()}
    for name in sorted(CRITICAL_FIELDS - fields.keys()):
        fields[name] = FieldResult(source_quality=SourceQuality.UNREADABLE, decision=FieldDecision.MISSING)

    source = {**raw.source, "sha256": sha256}
    untrusted_text = getattr(raw, "untrusted_text", None)
    if untrusted_text is not None:
        # Non-field document text (e.g. an injected instruction), kept for PRISM/UI.
        # Evidence only: nothing in the pipeline or policy reads it.
        source["untrusted_text"] = list(untrusted_text)

    rx = Prescription(
        prescription_id=raw.prescription_id,
        status=PrescriptionStatus.PROCESSING,
        source=source,
        fields=fields,
        exceptions=[],
        clarifications=[],
        approved_by=None,
        audit_events=[],
    )
    append_event(rx, clock, "SYSTEM", "DOCUMENT_RECEIVED")
    append_event(rx, clock, "AI", "FIELDS_EXTRACTED")
    # PRISM evidence is audit-only: it never touches status, decisions or exceptions.
    for prism_event in getattr(raw, "prism_events", None) or []:
        append_event(rx, clock, "PRISM", prism_event["event"], detail=prism_event.get("detail"))

    duplicate = validate_duplicate(sha256, seen_hashes)
    if duplicate.status is SignalStatus.FAIL:
        _create_exception(
            rx,
            clock,
            type="DUPLICATE_DOCUMENT",
            field=DOCUMENT_FIELD,
            reason="This document has already been received; reject the duplicate.",
            source_evidence={"sha256": sha256, "detail": duplicate.detail},
            candidate_values=[],
            required_action="REJECT",
        )

    revalidate(rx, clock, patient_identity=raw.patient_identity)
    return rx


def revalidate(
    rx: Prescription,
    clock: Clock = utc_now,
    patient_identity: PatientIdentity | None = None,
) -> Prescription:
    """Re-run checks on every unresolved field, append new evidence, re-route,
    and reconcile each field's active exception with the current result; then
    route the prescription. Mutates and returns `rx`.

    Never touched: HUMAN_VERIFIED fields (never reopened) and fields a
    pharmacist marked UNREADABLE (awaiting clarification). Fields whose active
    exception is not dependency-driven only gain signals; the pending human
    decision owns them. Document-level exceptions are never touched."""
    active = {e.field: e for e in rx.exceptions if e.field in rx.fields}
    order = sorted(rx.fields, key=lambda n: _EVALUATION_PRIORITY.get(n, 1))
    for name in order:
        field = rx.fields[name]
        existing = active.get(name)
        if field.decision is FieldDecision.HUMAN_VERIFIED:
            continue
        if existing is not None and field.decision is FieldDecision.UNREADABLE:
            continue
        signals, candidates, normalized = _check_field(name, field, rx, patient_identity)
        _append_new(field, signals)
        if existing is not None and existing.type not in DEPENDENCY_DRIVEN_TYPES:
            continue
        field.candidates = _dedupe(field.candidates + candidates)
        field.normalized_value = normalized

        route = evaluate_field(name, field)
        field.decision = route.decision
        field.reason = route.reason
        # Active choices describe current evidence, not accumulated history.
        current = [] if route.decision is FieldDecision.MISSING else _dedupe(candidates)
        _reconcile_exception(rx, clock, name, field, existing, route, current)

    rx.status = route_prescription(rx)
    return rx


def field_value(field: FieldResult) -> str | None:
    """The value checks should use: a human resolution wins over the raw read."""
    if field.resolution is not None:
        return field.resolution.value
    return field.raw_value


def append_event(rx: Prescription, clock: Clock, actor: str, event: str, **extra: object) -> None:
    rx.audit_events.append({"ts": clock(), "actor": actor, "event": event, **extra})


# --- per-field checks -------------------------------------------------------


def _check_field(
    name: str,
    field: FieldResult,
    rx: Prescription,
    patient_identity: PatientIdentity | None,
) -> tuple[list[Signal], list[str], str | None]:
    """Returns (new signals, candidates, normalized_value). Pure with respect to `field`."""
    value = field_value(field)
    signals: list[Signal] = []
    required = check_required(name, value)
    if required is not None:
        signals.append(required)
    if _blank(value):
        return signals, [], None

    critical = name in CRITICAL_FIELDS
    if not critical and field.source_quality is SourceQuality.UNREADABLE:
        signals.append(
            Signal(type="REQUIRED_FIELD", status=SignalStatus.WARNING, detail=f"Optional field {name!r} is unreadable.")
        )
        return signals, [], None

    collapsed = _collapse(value)
    match name:
        case "patient":
            if patient_identity is not None:
                signals.append(
                    validate_patient_identity(
                        patient_identity.header_name, patient_identity.block_name, patient_identity.dob_values
                    )
                )
            return signals, [collapsed], collapsed
        case "drug":
            return _check_drug(field, value, signals)
        case "strength":
            return _check_strength(field, value, rx, signals)
        case "sig":
            sig = normalize_sig(value)
            signals.append(validate_sig_tokens(sig.unknown))
            rendered = render_sig(sig) if not sig.unknown else None
            return signals, [rendered] if rendered else [], rendered
        case "quantity":
            signal, implied = _check_quantity(value, rx)
            candidates = [collapsed]
            if signal is not None:
                signals.append(signal)
                if signal.status is SignalStatus.FAIL and implied:
                    candidates.append(implied)
            return signals, candidates, collapsed
        case "prescriber_identifier":
            signals.append(validate_npi(value.strip()))
            return signals, [collapsed], collapsed
        case _:
            return signals, [collapsed], collapsed


def _check_drug(field: FieldResult, value: str, signals: list[Signal]) -> tuple[list[Signal], list[str], str | None]:
    read_values = [r.value for r in field.reads if r.value]
    reference = lookup_all(_dedupe(read_values + [value]))
    cross = validate_cross_pass([drug_base_key(v) for v in read_values])
    ref = validate_reference(reference)
    lasa = validate_lasa(field.reads, list(reference.candidates), field.source_quality)
    signals += [cross, ref, lasa]

    read_keys = {drug_base_key(v) for v in read_values}
    candidates = _dedupe(read_values + [c for c in reference.candidates if drug_base_key(c) not in read_keys])
    # A missing secondary read (CROSS_PASS WARNING) alone does not withhold normalization.
    settled = reference.clear and cross.status is not SignalStatus.FAIL and lasa.status is SignalStatus.PASS
    normalized = reference.candidates[0] if settled else None
    return signals, candidates or [_collapse(value)], normalized


def _check_strength(
    field: FieldResult, value: str, rx: Prescription, signals: list[Signal]
) -> tuple[list[Signal], list[str], str | None]:
    read_values = [r.value for r in field.reads if r.value]
    cross = validate_cross_pass([normalize_strength(v) or _collapse(v).casefold() for v in read_values])
    signals += [cross, _marketed_strength(value, rx), _strength_collision(value, rx)]
    # Canonical spelling, so "15 mg" and "15mg" are offered once.
    candidates = _dedupe([normalize_strength(v) or _collapse(v) for v in read_values + [value]])
    return signals, candidates, None if cross.status is SignalStatus.FAIL else _collapse(value)


def _marketed_strength(strength: str, rx: Prescription) -> Signal:
    return _per_drug_strength_check(strength, rx, validate_marketed_strength, "MARKETED_STRENGTH", "Marketed-strength")


def _strength_collision(strength: str, rx: Prescription) -> Signal:
    return _per_drug_strength_check(strength, rx, validate_strength_collision, "PLAUSIBLE_STRENGTH_COLLISION", "Strength-collision")


def _per_drug_strength_check(
    strength: str, rx: Prescription, validate: Callable[[str, str], Signal], signal_type: str, label: str
) -> Signal:
    """Checked against every plausible drug. PASS/FAIL only when all candidates
    agree; otherwise WARNING, re-checked once the drug is resolved."""
    drug_names = _drug_context(rx)
    form_field = rx.fields.get("form")
    form = _collapse(field_value(form_field)) if form_field and not _blank(field_value(form_field)) else None
    if not drug_names:
        return Signal(type=signal_type, status=SignalStatus.WARNING, detail="Drug not established; strength not checked.")

    results = []
    for drug in drug_names:
        result = validate(f"{drug} {form}", strength) if form else None
        if result is None or result.status is SignalStatus.WARNING:
            result = validate(drug, strength)
        results.append(result)

    statuses = {r.status for r in results}
    if statuses == {SignalStatus.PASS} or statuses == {SignalStatus.FAIL}:
        return results[0]
    if len(results) == 1:
        return results[0]
    return Signal(
        type=signal_type,
        status=SignalStatus.WARNING,
        detail=f"{label} result depends on which drug candidate is meant.",
    )


def _drug_context(rx: Prescription) -> list[str]:
    drug = rx.fields.get("drug")
    if drug is None or _blank(field_value(drug)):
        return []
    if drug.resolution is not None:
        return [drug.resolution.value]
    if drug.normalized_value:
        return [drug.normalized_value]
    return list(drug.candidates)


def _check_quantity(value: str, rx: Prescription) -> tuple[Signal | None, str | None]:
    match = _QUANTITY_RE.match(_collapse(value))
    sig_field = rx.fields.get("sig")
    sig_value = field_value(sig_field) if sig_field else None
    if not match or _blank(sig_value):
        return None, None
    stated = float(match.group(1))
    quantity_unit = match.group(2)

    sig = normalize_sig(sig_value)
    days = _explicit_days(rx)
    if days is None:
        days = sig.days

    signal = validate_quantity(
        sig.dose, sig.dose_unit, sig.frequency_token, days, stated, quantity_unit, as_needed=sig.as_needed
    )
    implied = implied_quantity(sig.dose, sig.frequency_token, days)
    return signal, format_quantity(implied, sig.dose_unit) if implied is not None else None


def _explicit_days(rx: Prescription) -> int | None:
    field = rx.fields.get("days_supply")
    value = field_value(field) if field else None
    if value is None or not _INT_RE.match(value.strip()):
        return None
    return int(value.strip())


# --- helpers ----------------------------------------------------------------


def _from_raw(rf) -> FieldResult:
    return FieldResult(
        raw_value=rf.raw_value,
        source_quality=rf.source_quality,
        reads=[r.model_copy() for r in rf.reads],
        evidence=rf.evidence.model_copy() if rf.evidence else None,
        decision=FieldDecision.EXTRACTED,
    )


def _reconcile_exception(
    rx: Prescription,
    clock: Clock,
    name: str,
    field: FieldResult,
    existing: RxException | None,
    route: FieldRoute,
    candidates: list[str],
) -> None:
    """Clear, update in place, or replace `existing` to match the current route."""
    if route.exception_type is None:
        if existing is not None:
            _clear_exception(rx, clock, existing, "dependency resolved")
        return

    current = {
        "reason": route.reason,
        "source_evidence": _source_evidence(field),
        "candidate_values": candidates,
        "required_action": HUMAN_ACTION,
    }
    if existing is not None and existing.type == route.exception_type:
        if any(getattr(existing, k) != v for k, v in current.items()):
            for k, v in current.items():
                setattr(existing, k, v)
            append_event(rx, clock, "SYSTEM", "EXCEPTION_UPDATED", exception_id=existing.exception_id)
        return
    if existing is not None:
        _clear_exception(rx, clock, existing, "blocking condition changed")
    _create_exception(rx, clock, type=route.exception_type, field=name, **current)


def _clear_exception(rx: Prescription, clock: Clock, exception: RxException, reason: str) -> None:
    rx.exceptions = [e for e in rx.exceptions if e.exception_id != exception.exception_id]
    for record in rx.clarifications:
        if record.get("exception_id") == exception.exception_id and record.get("status") == "REQUESTED":
            record["status"] = "WITHDRAWN"
    append_event(rx, clock, "SYSTEM", "EXCEPTION_CLEARED", exception_id=exception.exception_id, reason=reason)


def _create_exception(rx: Prescription, clock: Clock, **kwargs) -> RxException:
    n = _next_exception_number(rx)
    exception = RxException(exception_id=f"{rx.prescription_id}__exc_{n:02d}", severity="CRITICAL", **kwargs)
    rx.exceptions.append(exception)
    append_event(rx, clock, "SYSTEM", "EXCEPTION_CREATED", exception_id=exception.exception_id)
    return exception


def _next_exception_number(rx: Prescription) -> int:
    """1 + the highest suffix ever issued on this prescription, so a cleared id is never reused."""
    pattern = re.compile(rf"^{re.escape(rx.prescription_id)}__exc_(\d+)$")
    ids = [e.exception_id for e in rx.exceptions]
    ids += [e.get("exception_id") for e in rx.audit_events]
    ids += [c.get("exception_id") for c in rx.clarifications]
    numbers = [int(m.group(1)) for i in ids if isinstance(i, str) and (m := pattern.match(i))]
    return max(numbers, default=0) + 1


def _source_evidence(field: FieldResult) -> dict | None:
    if field.evidence is None:
        return None
    bbox = list(field.evidence.bbox) if field.evidence.bbox is not None else None
    return {"page": field.evidence.page, "bbox": bbox}


def _append_new(field: FieldResult, signals: list[Signal]) -> None:
    """Append-only: add a signal unless it repeats the latest one of its type."""
    for signal in signals:
        if latest_signals(field.signals).get(signal.type) != signal:
            field.signals.append(signal)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(v for v in values if v))


def _collapse(value: str) -> str:
    return _WS_RE.sub(" ", value.strip())


def _blank(value: str | None) -> bool:
    return value is None or not value.strip()
