import pytest

from backend.models import SignalStatus
from backend.references.strengths import MARKETED_STRENGTHS
from backend.validators.strength import validate_marketed_strength


@pytest.mark.parametrize(
    ("drug", "strength", "status"),
    [
        ("metoprolol tartrate", "30 mg", SignalStatus.FAIL),
        ("atorvastatin", "30 mg", SignalStatus.FAIL),
        ("metoprolol tartrate", "75 mg", SignalStatus.PASS),
        ("metoprolol tartrate", "37.5 mg", SignalStatus.PASS),
        ("hydroxyzine HCl", "25 mg", SignalStatus.PASS),
        ("hydroxyzine hydrochloride", "25 mg", SignalStatus.PASS),
        ("hydralazine HCl", "100 mg", SignalStatus.PASS),
        ("hydroxyzine HCl", "100 mg", SignalStatus.FAIL),
        ("atorvastatin", "80 mg", SignalStatus.PASS),
        ("amoxicillin suspension", "250 mg/5 mL", SignalStatus.PASS),
        ("amoxicillin suspension", "300 mg/5 mL", SignalStatus.FAIL),
    ],
)
def test_marketed_strength(drug, strength, status):
    signal = validate_marketed_strength(drug, strength)

    assert signal.type == "MARKETED_STRENGTH"
    assert signal.status is status


@pytest.mark.parametrize(
    ("drug", "strength"),
    [
        ("  Hydroxyzine   HCL ", "25 mg"),
        ("HYDROXYZINE HYDROCHLORIDE", "25MG"),
        ("Metoprolol Tartrate", " 75  mg "),
        ("amoxicillin suspension", "250mg/5ml"),
        ("atorvastatin", "40.0 mg"),
    ],
)
def test_case_whitespace_and_salt_normalization(drug, strength):
    assert validate_marketed_strength(drug, strength).status is SignalStatus.PASS


def test_formulation_salts_stay_distinct():
    assert "metoprolol tartrate" in MARKETED_STRENGTHS
    assert "metoprolol succinate" in MARKETED_STRENGTHS
    assert "metoprolol" not in MARKETED_STRENGTHS
    # 37.5 mg exists for tartrate only.
    assert validate_marketed_strength("metoprolol succinate", "37.5 mg").status is SignalStatus.FAIL
    assert validate_marketed_strength("metoprolol", "25 mg").status is SignalStatus.WARNING


def test_unknown_drug_warns_not_fails():
    signal = validate_marketed_strength("zzz-unlisted-drug", "30 mg")

    assert signal.status is SignalStatus.WARNING


def test_non_numeric_strength_warns():
    assert validate_marketed_strength("atorvastatin", "two tablets").status is SignalStatus.WARNING


def test_reference_table_size():
    assert len(MARKETED_STRENGTHS) >= 15
