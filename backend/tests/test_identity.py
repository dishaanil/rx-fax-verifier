import pytest

from backend.models import SignalStatus
from backend.validators.identity import validate_patient_identity


def test_identical_names_pass():
    signal = validate_patient_identity("James Peterson", "James Peterson", [])

    assert signal.type == "PATIENT_IDENTITY"
    assert signal.status is SignalStatus.PASS


@pytest.mark.parametrize("block", ["james peterson", "  JAMES   Peterson ", "James\tPeterson"])
def test_spacing_and_case_differences_pass(block):
    assert validate_patient_identity("James Peterson", block, []).status is SignalStatus.PASS


@pytest.mark.parametrize(("header", "block"), [("Jane Miller", "John Miller"), ("James Peterson", "James Petersen")])
def test_different_names_fail(header, block):
    assert validate_patient_identity(header, block, []).status is SignalStatus.FAIL


@pytest.mark.parametrize(("header", "block"), [(None, "James Peterson"), ("James Peterson", None), (None, None)])
def test_single_name_source_passes(header, block):
    assert validate_patient_identity(header, block, []).status is SignalStatus.PASS


def test_matching_dob_values_pass():
    assert validate_patient_identity("A B", "A B", ["1960-01-02", " 1960-01-02 "]).status is SignalStatus.PASS


def test_conflicting_dob_values_fail():
    signal = validate_patient_identity("A B", "A B", ["1960-01-02", "1961-01-02"])

    assert signal.status is SignalStatus.FAIL
    assert "1960-01-02" in signal.detail and "1961-01-02" in signal.detail


def test_empty_dob_values_ignored():
    assert validate_patient_identity("A B", "A B", ["1960-01-02", "", "  "]).status is SignalStatus.PASS
