from backend.models import SignalStatus
from backend.validators.duplicate import validate_duplicate

SHA = "3f1c9a0b7e2d4856a1b0c3d2e4f5061728394a5b6c7d8e9f0a1b2c3d4e5f6071"


def test_unseen_passes():
    signal = validate_duplicate(SHA, set())

    assert signal.type == "DUPLICATE_DOCUMENT"
    assert signal.status is SignalStatus.PASS


def test_seen_fails():
    signal = validate_duplicate(SHA, {SHA})

    assert signal.status is SignalStatus.FAIL
    assert "DUPLICATE_DOCUMENT" in signal.detail


def test_seen_set_not_mutated():
    seen = {"abc"}

    validate_duplicate(SHA, seen)
    validate_duplicate("abc", seen)

    assert seen == {"abc"}
