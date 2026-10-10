"""Raw extraction contract — the seam between the extractor and the backend.

The extractor owns only raw_value, source_quality, reads and evidence.
Signals, candidates, decisions, exceptions, status and the document SHA-256
belong to the backend. Unlike the canonical models, raw models ignore
unexpected keys so a stray extractor key cannot crash intake.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.models import Evidence, Read, SourceQuality


class RawModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class RawField(RawModel):
    raw_value: str | None
    source_quality: SourceQuality
    reads: list[Read] = Field(default_factory=list)
    evidence: Evidence | None = None


class PatientIdentity(RawModel):
    header_name: str | None = None
    block_name: str | None = None
    dob_values: list[str] = Field(default_factory=list)


class RawPrescriptionExtraction(RawModel):
    """Expected field names: patient, patient_dob, drug, strength, form, sig,
    quantity, days_supply, refills, prescriber, prescriber_identifier,
    date_written, signature_present. Optional keys may be absent; the
    pipeline guarantees the six critical fields exist downstream."""

    prescription_id: str
    source: dict[str, Any] = Field(default_factory=dict)
    patient_identity: PatientIdentity | None = None
    fields: dict[str, RawField]
