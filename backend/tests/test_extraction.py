import copy
import json

import pytest
from pydantic import ValidationError

from backend.extraction import (
    ExtractionError,
    RawField,
    RawPrescriptionExtraction,
    StubExtractor,
    get_extractor,
)
from backend.extraction.stub import FIXTURES_DIR, STUB_IDS
from backend.models import FieldResult, Prescription, SourceQuality

RAW_FIELD_KEYS = {"raw_value", "source_quality", "reads", "evidence"}
POLICY_KEYS = {"normalized_value", "signals", "candidates", "decision", "reason", "resolution"}


def _load(pid: str) -> dict:
    return json.loads((FIXTURES_DIR / f"raw_{pid}.json").read_text())


@pytest.mark.parametrize("pid", STUB_IDS)
def test_raw_fixture_parses(pid):
    raw = RawPrescriptionExtraction.model_validate(_load(pid))

    assert raw.prescription_id == pid
    assert {"patient", "drug", "strength", "sig", "prescriber", "quantity"} <= raw.fields.keys()


@pytest.mark.parametrize("pid", STUB_IDS)
def test_raw_fixture_contains_extraction_data_only(pid):
    data = _load(pid)

    assert not {"status", "exceptions", "clarifications", "approved_by", "audit_events"} & data.keys()
    assert "sha256" not in data["source"]
    for field in data["fields"].values():
        assert set(field) <= RAW_FIELD_KEYS
        assert not POLICY_KEYS & field.keys()


@pytest.mark.parametrize("pid", STUB_IDS)
def test_critical_raw_fields_carry_page_evidence(pid):
    raw = RawPrescriptionExtraction.model_validate(_load(pid))

    for name in ("patient", "drug", "strength", "sig", "prescriber", "quantity"):
        assert raw.fields[name].evidence.page is not None


def test_raw_models_ignore_unexpected_keys():
    data = _load("rx_A")
    data["model_version"] = "x"
    data["fields"]["drug"]["confidence"] = 0.99
    data["fields"]["drug"]["decision"] = "VERIFIED"
    data["patient_identity"]["guess"] = "same"

    raw = RawPrescriptionExtraction.model_validate(data)

    assert raw.fields["drug"].raw_value == "lisinopril"
    assert "decision" not in raw.fields["drug"].model_dump()


def test_raw_models_preserve_contract_keys():
    raw = RawPrescriptionExtraction.model_validate(_load("rx_037"))
    drug = raw.fields["drug"]

    assert set(RawField.model_fields) == RAW_FIELD_KEYS
    assert drug.raw_value == "hydroxy?ine HCl"
    assert drug.source_quality is SourceQuality.PARTIAL
    assert [r.value for r in drug.reads] == ["hydroxyzine HCl", "hydralazine HCl"]
    assert drug.evidence.bbox == (412, 288, 760, 324)
    assert raw.patient_identity.header_name == "James Peterson"


def test_raw_field_rejects_bad_source_quality():
    with pytest.raises(ValidationError):
        RawField.model_validate({"raw_value": "x", "source_quality": "PRETTY_SURE"})


def test_canonical_models_remain_strict(rx_037):
    data = copy.deepcopy(rx_037)
    data["fields"]["drug"]["confidence"] = 0.99
    with pytest.raises(ValidationError):
        Prescription.model_validate(data)

    with pytest.raises(ValidationError):
        FieldResult.model_validate({**rx_037["fields"]["patient"], "extra": 1})


def test_stub_maps_filename_stem_and_assigns_id():
    raw = StubExtractor().extract("/uploads/rx_C_2/rx_C.png", "rx_C_2")

    assert raw.prescription_id == "rx_C_2"
    assert raw.fields["quantity"].raw_value == "50 mL"


def test_stub_unknown_document_raises():
    with pytest.raises(ExtractionError):
        StubExtractor().extract("/uploads/x/unknown_fax.png", "unknown_fax")


def test_get_extractor_defaults_to_stub(monkeypatch):
    monkeypatch.delenv("RXBRIDGE_EXTRACTOR", raising=False)

    assert isinstance(get_extractor(), StubExtractor)


def test_get_extractor_rejects_unknown_name(monkeypatch):
    monkeypatch.setenv("RXBRIDGE_EXTRACTOR", "magic")

    with pytest.raises(ValueError):
        get_extractor()
