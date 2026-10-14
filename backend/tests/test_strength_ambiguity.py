"""PLAUSIBLE_STRENGTH_COLLISION: common-mode misread of a marketed strength (hotfix)."""

import pytest

from backend.models import FieldDecision, PrescriptionStatus, SignalStatus
from backend.policy import evaluate_field
from backend.review import ConflictError
from backend.tests.conftest import processed
from backend.tests.test_revalidation import crafted, exc, latest, setup
from backend.validators.strength_ambiguity import is_confusable, validate_strength_collision

# --- validator ---------------------------------------------------------------


def test_metoprolol_25_collides_with_75():
    signal = validate_strength_collision("metoprolol tartrate", "25 mg")

    assert signal.type == "PLAUSIBLE_STRENGTH_COLLISION"
    assert signal.status is SignalStatus.FAIL
    assert "75 mg" in signal.detail


@pytest.mark.parametrize(
    ("drug", "strength"),
    [
        ("lisinopril", "10 mg"),  # 20/30/40 differ by one digit, but not a confusable pair
        ("hydroxyzine HCl", "25 mg"),  # 10 and 50 are not single-digit neighbours
        ("sertraline", "50 mg"),
        ("amoxicillin suspension", "250 mg/5 mL"),  # 200 mg/5 mL: 5/0 is not a confusable pair
        ("metoprolol succinate", "25 mg"),  # salt is formulation-defining; 75 mg is tartrate only
    ],
)
def test_no_confusable_alternative_passes(drug, strength):
    assert validate_strength_collision(drug, strength).status is SignalStatus.PASS


def test_unknown_drug_is_warning():
    signal = validate_strength_collision("unobtainium", "25 mg")

    assert signal.status is SignalStatus.WARNING


@pytest.mark.parametrize("strength", ["2? mg", "twenty-five mg", "", "25"])
def test_unnormalizable_strength_is_warning(strength):
    assert validate_strength_collision("metoprolol tartrate", strength).status is SignalStatus.WARNING


def test_unmarketed_strength_is_left_to_marketed_strength_check():
    assert validate_strength_collision("metoprolol tartrate", "15 mg").status is SignalStatus.WARNING


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("25 mg", "75 mg", True),
        ("25 mcg", "75 mcg", True),
        ("125 mg/5 ml", "175 mg/5 ml", True),
        ("25 mg", "250 mg", False),  # different length: not a single-character slip
        ("2.5 mg", "25 mg", False),
        ("25 mg", "75 mcg", False),  # different unit
        ("25 mg", "75 mg/5 ml", False),  # plain vs concentration
        ("25 mg/5 ml", "75 mg/10 ml", False),  # different denominator
        ("25 mg", "35 mg", False),  # 2/3 is not a confusable pair
        ("25 mg", "78 mg", False),  # two differing digits
        ("25 mg", "25 mg", False),
        ("25 mg", "garbage", False),
    ],
)
def test_is_confusable(a, b, expected):
    assert is_confusable(a, b) is expected
    assert is_confusable(b, a) is expected


# --- pipeline + policy ---------------------------------------------------------


def common_mode_misread():
    """Both models agree on '25 mg' from a CLEAR source; the fax really said 75 mg."""
    return crafted("rx_A", drug="metoprolol tartrate", strength="25 mg")


def test_common_mode_misread_is_not_verified():
    store, review, rx = setup(common_mode_misread())
    strength = rx.fields["strength"]

    assert [r.value for r in strength.reads] == ["25 mg", "25 mg"]
    assert strength.source_quality.value == "CLEAR"
    assert latest(rx, "strength", "CROSS_PASS").status is SignalStatus.PASS
    assert latest(rx, "strength", "MARKETED_STRENGTH").status is SignalStatus.PASS
    assert latest(rx, "strength", "PLAUSIBLE_STRENGTH_COLLISION").status is SignalStatus.FAIL
    assert strength.decision is FieldDecision.REVIEW_REQUIRED
    assert strength.reason.startswith("Another marketed strength is visually confusable")
    assert [e.type for e in rx.exceptions] == ["AMBIGUOUS_STRENGTH"]
    # No alternative is auto-selected; the only candidate is what was read.
    assert exc(rx, "AMBIGUOUS_STRENGTH").candidate_values == ["25 mg"]
    assert strength.raw_value == "25 mg" and strength.resolution is None
    assert rx.status is PrescriptionStatus.REVIEW_REQUIRED
    assert rx.approved_by is None
    with pytest.raises(ConflictError):
        review.approve(rx.prescription_id)


def test_pharmacist_resolves_collision_then_approves():
    store, review, rx = setup(common_mode_misread())

    rx = review.resolve(exc(rx, "AMBIGUOUS_STRENGTH").exception_id, "CORRECT", "75 mg")
    assert rx.fields["strength"].decision is FieldDecision.HUMAN_VERIFIED
    assert rx.status is PrescriptionStatus.READY_FOR_VERIFICATION
    assert rx.approved_by is None

    rx = review.approve(rx.prescription_id)
    assert rx.status is PrescriptionStatus.APPROVED


def test_ambiguous_drug_context_is_not_a_hard_strength_failure():
    """rx_037: hydroxy?ine -> hydroxyzine or hydralazine; 25 mg collides with neither,
    and an unresolved drug never turns the collision check into FAIL."""
    rx = processed("rx_037")

    assert latest(rx, "strength", "PLAUSIBLE_STRENGTH_COLLISION").status is not SignalStatus.FAIL
    assert all(e.field != "strength" for e in rx.exceptions)


def test_missing_drug_context_is_warning():
    store, review, rx = setup(crafted("rx_A", drop=("drug",), strength="25 mg"))

    assert latest(rx, "strength", "PLAUSIBLE_STRENGTH_COLLISION").status is SignalStatus.WARNING
    assert all(e.field != "strength" for e in rx.exceptions)


def test_clean_prescription_still_ready():
    rx = processed("rx_A")

    assert latest(rx, "strength", "PLAUSIBLE_STRENGTH_COLLISION").status is SignalStatus.PASS
    assert rx.status is PrescriptionStatus.READY_FOR_VERIFICATION


@pytest.mark.parametrize(
    ("pid", "status"),
    [
        ("rx_A", PrescriptionStatus.READY_FOR_VERIFICATION),
        ("rx_C", PrescriptionStatus.REVIEW_REQUIRED),
        ("rx_D", PrescriptionStatus.REVIEW_REQUIRED),
        ("rx_F", PrescriptionStatus.REVIEW_REQUIRED),
    ],
)
def test_demo_fixtures_unaffected(pid, status):
    rx = processed(pid)

    assert rx.status is status
    assert "AMBIGUOUS_STRENGTH" not in {e.type for e in rx.exceptions}
    assert latest(rx, "strength", "PLAUSIBLE_STRENGTH_COLLISION").status is not SignalStatus.FAIL


def test_router_ranks_collision_before_verified():
    rx = processed("rx_A")
    field = rx.fields["strength"].model_copy(deep=True)
    field.signals.append(
        field.signals[-1].model_copy(update={"type": "PLAUSIBLE_STRENGTH_COLLISION", "status": SignalStatus.FAIL})
    )

    route = evaluate_field("strength", field)
    assert route.decision is FieldDecision.REVIEW_REQUIRED
    assert route.exception_type == "AMBIGUOUS_STRENGTH"


def test_same_strength_spelled_differently_is_offered_once():
    # Demo B: primary "15 mg", secondary "100mg", verbatim "15mg" -> two options, not three.
    from backend.models import Read
    from backend.pipeline import process
    from backend.tests.conftest import fixed_clock

    raw = crafted("rx_A", strength={
        "raw_value": "15mg",
        "reads": [Read(source="primary", value="15 mg"), Read(source="secondary", value="100mg")],
    })
    rx = process(raw, set(), "sha-dedupe", fixed_clock)

    assert rx.fields["strength"].candidates == ["15 mg", "100 mg"]
