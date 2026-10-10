import pytest

from backend.normalization import normalize_sig


def test_canonical_abbreviation_sig():
    sig = normalize_sig("1 TAB PO TID")

    assert sig.tokens == ["1", "TAB", "PO", "TID"]
    assert sig.dose == 1
    assert sig.dose_unit == "TAB"
    assert sig.frequency_token == "TID"
    assert sig.days is None
    assert sig.as_needed is False
    assert sig.unknown == []


def test_prose_sig_with_volume_and_days():
    sig = normalize_sig("Take 10 mL three times daily for 10 days")

    assert sig.dose == 10
    assert sig.dose_unit == "ML"
    assert sig.frequency_token == "TID"
    assert sig.days == 10
    assert sig.unknown == []


@pytest.mark.parametrize(
    ("raw", "token"),
    [
        ("1 tablet once daily", "QD"),
        ("1 tablet daily", "QD"),
        ("1 tablet every day", "QD"),
        ("1 tablet twice daily", "BID"),
        ("1 tablet three times daily", "TID"),
        ("1 tablet four times daily", "QID"),
        ("1 tablet at bedtime", "QHS"),
        ("1 tablet every morning", "QAM"),
        ("1 tablet every 4 hours", "Q4H"),
        ("1 tablet every 6 hours", "Q6H"),
        ("1 tablet every 8 hours", "Q8H"),
        ("1 tablet every 12 hours", "Q12H"),
    ],
)
def test_prose_frequency(raw, token):
    sig = normalize_sig(raw)

    assert sig.frequency_token == token
    assert sig.unknown == []


@pytest.mark.parametrize("raw", ["1 tab by mouth daily", "1 tab orally daily", "1 tab PO daily"])
def test_prose_route(raw):
    sig = normalize_sig(raw)

    assert "PO" in sig.tokens
    assert sig.unknown == []


def test_prose_is_case_insensitive():
    sig = normalize_sig("TAKE 1 TABLET BY MOUTH TWICE DAILY")

    assert sig.tokens == ["1", "TAB", "PO", "BID"]
    assert sig.unknown == []


def test_as_needed():
    sig = normalize_sig("Take 1 tablet by mouth every 6 hours as needed")

    assert sig.as_needed is True
    assert "PRN" in sig.tokens
    assert sig.frequency_token == "Q6H"
    assert sig.unknown == []


def test_prn_abbreviation():
    assert normalize_sig("1 tab PO q6h PRN").as_needed is True


@pytest.mark.parametrize(
    ("raw", "dose", "unit"),
    [
        ("1 TAB", 1.0, "TAB"),
        ("2 tablets", 2.0, "TAB"),
        ("0.5 TAB", 0.5, "TAB"),
        ("1 capsule", 1.0, "CAP"),
        ("2 caps", 2.0, "CAP"),
        ("10 mL", 10.0, "ML"),
        ("10mL", 10.0, "ML"),
        ("2.5 ml", 2.5, "ML"),
    ],
)
def test_dose_and_unit(raw, dose, unit):
    sig = normalize_sig(raw)

    assert sig.dose == dose
    assert sig.dose_unit == unit


def test_strength_is_not_a_dose():
    sig = normalize_sig("Take 25 mg by mouth daily")

    assert sig.dose is None
    assert sig.dose_unit is None
    assert sig.unknown == []


@pytest.mark.parametrize(("raw", "days"), [("1 tab PO QD for 30 days", 30), ("1 tab PO QD for 1 day", 1)])
def test_days_extraction(raw, days):
    assert normalize_sig(raw).days == days


def test_unsupported_token_is_preserved_not_guessed():
    sig = normalize_sig("1 tab XQZ")

    assert sig.unknown == ["XQZ"]
    assert sig.frequency_token is None


def test_filler_words_and_numerals_not_flagged():
    sig = normalize_sig("Take 1.5 tab for 5 days 20 mg 100 mcg 1 g")

    assert sig.unknown == []


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_empty_input(raw):
    sig = normalize_sig(raw)

    assert sig.tokens == []
    assert sig.unknown == []
    assert sig.dose is None
