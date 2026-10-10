import pytest

from backend.models import SignalStatus
from backend.validators.identifier import validate_npi


def test_known_valid_npi_passes():
    signal = validate_npi("1234567893")

    assert signal.type == "IDENTIFIER_CHECKSUM"
    assert signal.status is SignalStatus.PASS


@pytest.mark.parametrize("last", [d for d in "0123456789" if d != "3"])
def test_changed_check_digit_fails(last):
    signal = validate_npi("123456789" + last)

    assert signal.type == "IDENTIFIER_CHECKSUM"
    assert signal.status is SignalStatus.FAIL


def test_single_misread_digit_fails():
    assert validate_npi("1234567393").status is SignalStatus.FAIL


@pytest.mark.parametrize("npi", ["", "123456789", "12345678930", "12345678a3", " 1234567893", "１２３４５６７８９３"])
def test_malformed_npi_fails(npi):
    assert validate_npi(npi).status is SignalStatus.FAIL
