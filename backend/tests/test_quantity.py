import pytest

from backend.models import SignalStatus
from backend.normalization import normalize_sig
from backend.validators.quantity import validate_quantity


def test_count_match():
    signal = validate_quantity(1, "TAB", "TID", 30, 90)

    assert signal.type == "QUANTITY_SIG"
    assert signal.status is SignalStatus.PASS


def test_count_mismatch_names_both_values():
    signal = validate_quantity(1, "TAB", "TID", 30, 30)

    assert signal.status is SignalStatus.FAIL
    assert "90" in signal.detail
    assert "30" in signal.detail
    assert signal.detail == "Directions imply 90 but prescription states 30."


def test_capsule_count_match():
    assert validate_quantity(2, "CAP", "BID", 7, 28).status is SignalStatus.PASS


def test_ml_match():
    assert validate_quantity(10, "ML", "TID", 10, 300, "mL").status is SignalStatus.PASS


def test_ml_mismatch():
    signal = validate_quantity(10, "ML", "TID", 10, 50, "mL")

    assert signal.status is SignalStatus.FAIL
    assert "300" in signal.detail
    assert "50" in signal.detail


def test_float_dose():
    assert validate_quantity(0.5, "TAB", "BID", 30, 30).status is SignalStatus.PASS
    assert validate_quantity(0.5, "TAB", "BID", 30, 60).status is SignalStatus.FAIL


def test_q12h_is_twice_daily():
    assert validate_quantity(1, "TAB", "Q12H", 10, 20).status is SignalStatus.PASS


@pytest.mark.parametrize(
    "kwargs",
    [
        {"dose": None},
        {"frequency_token": None},
        {"frequency_token": "QOD"},
        {"days": None},
        {"stated_qty": None},
        {"dose_unit": None},
        {"as_needed": True},
    ],
)
def test_non_deterministic_inputs_skip(kwargs):
    args = {"dose": 1, "dose_unit": "TAB", "frequency_token": "TID", "days": 30, "stated_qty": 90}
    args.update(kwargs)

    assert validate_quantity(**args) is None


@pytest.mark.parametrize(
    ("dose_unit", "quantity_unit"),
    [("TAB", "mL"), ("ML", "tablets"), ("TAB", "CAP"), ("CAP", "TAB"), ("TAB", "mg"), ("ML", "g")],
)
def test_incompatible_units_skip(dose_unit, quantity_unit):
    assert validate_quantity(1, dose_unit, "TID", 30, 90, quantity_unit) is None


@pytest.mark.parametrize("quantity_unit", [None, "tablets", "TAB", "tab"])
def test_count_units_compatible(quantity_unit):
    assert validate_quantity(1, "TAB", "TID", 30, 90, quantity_unit).status is SignalStatus.PASS


def test_ml_with_no_quantity_unit_is_compatible():
    assert validate_quantity(5, "ML", "BID", 10, 100).status is SignalStatus.PASS


def test_fixture_rx_037_quantity_conflict(rx_037):
    """days_supply wins over SIG days; 1 TAB TID x 30 days = 90, stated 30."""
    fields = rx_037["fields"]
    sig = normalize_sig(fields["sig"]["raw_value"])
    days = int(fields["days_supply"]["normalized_value"])

    signal = validate_quantity(
        sig.dose,
        sig.dose_unit,
        sig.frequency_token,
        days,
        float(fields["quantity"]["normalized_value"]),
        as_needed=sig.as_needed,
    )

    assert signal.status is SignalStatus.FAIL
    assert "90" in signal.detail and "30" in signal.detail
