import copy

import pytest
from pydantic import ValidationError

from backend.models import (
    CRITICAL_FIELDS,
    FieldDecision,
    Prescription,
    PrescriptionStatus,
    SignalStatus,
    SourceQuality,
)


def test_fixture_parses(rx_037):
    rx = Prescription.model_validate(rx_037)

    assert rx.prescription_id == "rx_037"
    assert rx.status is PrescriptionStatus.REVIEW_REQUIRED
    assert rx.fields["drug"].source_quality is SourceQuality.PARTIAL
    assert rx.fields["drug"].decision is FieldDecision.REVIEW_REQUIRED
    assert rx.fields["drug"].signals[0].status is SignalStatus.FAIL
    assert rx.fields["drug"].evidence.bbox == (412, 288, 760, 324)
    assert [e.exception_id for e in rx.exceptions] == ["exc_01", "exc_02"]


def test_fixture_round_trips_exactly(rx_037):
    parsed = Prescription.model_validate(rx_037)
    dumped = parsed.model_dump(mode="json", exclude_none=False)

    assert dumped == rx_037


def test_fixture_contains_every_critical_field(rx_037):
    assert CRITICAL_FIELDS <= rx_037["fields"].keys()


def test_days_supply_present_but_not_critical(rx_037):
    assert "days_supply" in rx_037["fields"]
    assert "days_supply" not in CRITICAL_FIELDS


def test_critical_set_is_fixed():
    assert CRITICAL_FIELDS == {"patient", "drug", "strength", "sig", "prescriber", "quantity"}


def test_unknown_key_is_rejected(rx_037):
    data = copy.deepcopy(rx_037)
    data["fields"]["drug"]["confidence"] = 0.97

    with pytest.raises(ValidationError):
        Prescription.model_validate(data)


def test_unknown_enum_value_is_rejected(rx_037):
    data = copy.deepcopy(rx_037)
    data["status"] = "PROBABLY_FINE"

    with pytest.raises(ValidationError):
        Prescription.model_validate(data)
