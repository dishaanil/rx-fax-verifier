from backend.models import SignalStatus
from backend.normalization import normalize_sig
from backend.validators.sig import validate_sig_tokens


def test_abbreviated_sig_passes():
    signal = validate_sig_tokens(normalize_sig("1 TAB PO TID").unknown)

    assert signal.type == "SIG_VOCABULARY"
    assert signal.status is SignalStatus.PASS


def test_prose_sig_passes():
    assert validate_sig_tokens(normalize_sig("Take 10 mL three times daily for 10 days").unknown).status is SignalStatus.PASS


def test_unsupported_token_fails_and_is_named():
    signal = validate_sig_tokens(normalize_sig("1 tab XQZ").unknown)

    assert signal.status is SignalStatus.FAIL
    assert "XQZ" in signal.detail


def test_multiple_unsupported_tokens_all_named():
    signal = validate_sig_tokens(["XQZ", "QOD"])

    assert "XQZ" in signal.detail
    assert "QOD" in signal.detail


def test_numeric_dose_not_flagged():
    assert validate_sig_tokens(normalize_sig("2.5 mL PO BID").unknown).status is SignalStatus.PASS
