import pytest

from backend.models import Read, SignalStatus, SourceQuality
from backend.references.catalog import CATALOG, lookup, lookup_all
from backend.references.lasa import LASA_PAIRS, contains_lasa_pair, is_lasa_member, is_lasa_pair
from backend.validators.cross_pass import validate_cross_pass
from backend.validators.lasa import validate_lasa
from backend.validators.reference import validate_reference


def test_ten_frozen_lasa_pairs():
    assert len(LASA_PAIRS) == 10


@pytest.mark.parametrize(("a", "b"), [("hydroxyzine HCl", "hydralazine"), ("Klonopin", "clonidine"), ("tramadol", "trazodone")])
def test_is_lasa_pair(a, b):
    assert is_lasa_pair(a, b)
    assert is_lasa_pair(b, a)


@pytest.mark.parametrize(("a", "b"), [("hydroxyzine", "hydroxyzine HCl"), ("hydroxyzine", "prednisone"), ("lisinopril", "x")])
def test_not_lasa_pair(a, b):
    assert not is_lasa_pair(a, b)


def test_lasa_membership_and_containment():
    assert is_lasa_member("Hydroxyzine Hydrochloride")
    assert not is_lasa_member("lisinopril")
    assert contains_lasa_pair(["prednisone", "x", "prednisolone"])
    assert not contains_lasa_pair(["prednisone"])


def test_catalog_includes_strength_and_lasa_names():
    assert {"hydroxyzine", "hydralazine", "lisinopril", "amoxicillin", "klonopin"} <= CATALOG.keys()
    assert "metoprolol tartrate" in CATALOG and "metoprolol succinate" in CATALOG
    assert "metoprolol" not in CATALOG


def test_exact_lookup_and_salt_equivalence():
    assert lookup("hydroxyzine hydrochloride").candidates == ("hydroxyzine HCl",)
    assert lookup("  HYDROXYZINE   HCl").exact


def test_exact_lookup_does_not_fuzz_to_look_alike():
    match = lookup("prednisone")

    assert match.exact
    assert match.candidates == ("prednisone",)


def test_fuzzy_lookup_is_never_exact():
    match = lookup("hydroxy?ine HCl")

    assert not match.exact
    assert match.candidates == ("hydroxyzine HCl",)


def test_lookup_is_deterministic():
    assert lookup_all(["hydroxy?ine", "hydralazine"]) == lookup_all(["hydroxy?ine", "hydralazine"])


@pytest.mark.parametrize(
    ("names", "status"),
    [
        (["lisinopril"], SignalStatus.PASS),
        (["lisinopril", "Lisinopril"], SignalStatus.PASS),
        (["hydroxyzine HCl", "hydralazine HCl"], SignalStatus.AMBIGUOUS),
        (["lisinoprll"], SignalStatus.AMBIGUOUS),
        (["zzz unknown"], SignalStatus.WARNING),
    ],
)
def test_reference_signal(names, status):
    signal = validate_reference(lookup_all(names))

    assert signal.type == "RXNORM"
    assert signal.status is status


def _reads(*values):
    return [Read(source=s, value=v) for s, v in zip(("primary", "secondary"), values)]


def test_lasa_clean_agreeing_clear_member_passes():
    signal = validate_lasa(_reads("hydroxyzine HCl", "hydroxyzine HCl"), ["hydroxyzine HCl"], SourceQuality.CLEAR)

    assert signal.type == "LASA"
    assert signal.status is SignalStatus.PASS


def test_lasa_disagreeing_pair_fails():
    signal = validate_lasa(_reads("hydroxyzine HCl", "hydralazine HCl"), [], SourceQuality.CLEAR)

    assert signal.status is SignalStatus.FAIL


def test_lasa_both_members_among_candidates_fails():
    signal = validate_lasa(_reads("hydroxyzine"), ["hydroxyzine HCl", "hydralazine HCl"], SourceQuality.CLEAR)

    assert signal.status is SignalStatus.FAIL


def test_lasa_unclear_source_on_member_fails():
    assert validate_lasa(_reads("hydroxyzine"), [], SourceQuality.PARTIAL).status is SignalStatus.FAIL


def test_lasa_non_member_unclear_passes():
    assert validate_lasa(_reads("lisinopril"), [], SourceQuality.PARTIAL).status is SignalStatus.PASS


@pytest.mark.parametrize(
    ("keys", "status"),
    [(["a", "a"], SignalStatus.PASS), (["a", "b"], SignalStatus.FAIL), (["a"], SignalStatus.WARNING), (["a", None], SignalStatus.WARNING)],
)
def test_cross_pass(keys, status):
    signal = validate_cross_pass(keys)

    assert signal.type == "CROSS_PASS"
    assert signal.status is status
