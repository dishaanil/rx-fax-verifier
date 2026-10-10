from backend.models import CRITICAL_FIELDS, SignalStatus
from backend.validators.required_fields import validate_required

COMPLETE = {
    "patient": "James Peterson",
    "drug": "hydroxyzine HCl",
    "strength": "25 mg",
    "sig": "1 TAB PO TID",
    "prescriber": "Dr. A. Whitfield",
    "quantity": "30",
}


def _by_status(signals, status):
    return [s for s in signals if s.status is status]


def test_complete_critical_set_all_pass():
    signals = validate_required(COMPLETE)

    assert len(signals) == len(CRITICAL_FIELDS)
    assert all(s.type == "REQUIRED_FIELD" for s in signals)
    assert all(s.status is SignalStatus.PASS for s in signals)


def test_absent_critical_fails():
    fields = {k: v for k, v in COMPLETE.items() if k != "quantity"}

    fails = _by_status(validate_required(fields), SignalStatus.FAIL)

    assert len(fails) == 1
    assert "quantity" in fails[0].detail


def test_none_critical_fails():
    fails = _by_status(validate_required({**COMPLETE, "drug": None}), SignalStatus.FAIL)

    assert len(fails) == 1
    assert "drug" in fails[0].detail


def test_blank_critical_fails():
    fails = _by_status(validate_required({**COMPLETE, "sig": "   "}), SignalStatus.FAIL)

    assert len(fails) == 1
    assert "sig" in fails[0].detail


def test_absent_optional_produces_nothing():
    signals = validate_required(COMPLETE)

    assert not any("days_supply" in s.detail for s in signals)
    assert not _by_status(signals, SignalStatus.WARNING)


def test_present_null_optional_warns():
    signals = validate_required({**COMPLETE, "signature_present": None})

    warnings = _by_status(signals, SignalStatus.WARNING)
    assert len(warnings) == 1
    assert "signature_present" in warnings[0].detail
    assert not _by_status(signals, SignalStatus.FAIL)


def test_present_optional_with_value_produces_nothing():
    signals = validate_required({**COMPLETE, "refills": "2"})

    assert len(signals) == len(CRITICAL_FIELDS)


def test_days_supply_is_optional():
    assert "days_supply" not in CRITICAL_FIELDS

    signals = validate_required({**COMPLETE, "days_supply": ""})

    assert not _by_status(signals, SignalStatus.FAIL)
    assert [s.status for s in signals if "days_supply" in s.detail] == [SignalStatus.WARNING]


def test_input_not_mutated():
    fields = {**COMPLETE, "refills": None}
    snapshot = dict(fields)

    validate_required(fields)

    assert fields == snapshot
