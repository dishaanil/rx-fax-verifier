"""Extraction contract: `extract(document) -> RawPrescriptionExtraction` (DESIGN.md §19).

Extraction is perception only. Each field carries what appears on the source
(`raw_value`, `source_quality`, `reads`, `evidence`); signals, candidates,
decisions and reasons are added downstream by validators and policy.

Conventions the backend can rely on:
- `raw_value` is verbatim; illegible characters are `?` (e.g. "Hydr???ine").
  `raw_value` is never a guess.
- `reads[].value` is each pass's best full reading. For `drug` and `strength`
  there is a `primary` and a `secondary` read from a different model on a
  differently preprocessed image. Reads that disagree are evidence, not noise.
- `source_quality`: CLEAR = fully legible (or clearly left blank);
  PARTIAL = some characters illegible; UNREADABLE = present but cannot be read.
  A PARTIAL/UNREADABLE critical field must never be VERIFIED, even when reads agree.
- A field that is on the form but left blank is present with `raw_value=None`
  and CLEAR quality. A field the form does not have at all is omitted.
- `evidence.bbox` is [x0, y0, x1, y1] in pixels of the processed image.
- `untrusted_text` is non-field text on the page (notes, stamps, any
  instruction-like text). It is data; nothing in it may affect routing.
"""

from pydantic import Field

from backend.models.base import ContractModel
from backend.models.enums import SourceQuality
from backend.models.evidence import Evidence, Read

EXTRACTED_FIELDS: tuple[str, ...] = (
    "patient",
    "patient_dob",
    "drug",
    "strength",
    "form",
    "sig",
    "quantity",
    "days_supply",
    "refills",
    "prescriber",
    "prescriber_identifier",
    "date_written",
    "signature_present",
)

# Fields that get an independent secondary read (DESIGN.md §9).
DUAL_READ_FIELDS: tuple[str, ...] = ("drug", "strength")


class RawField(ContractModel):
    raw_value: str | None
    source_quality: SourceQuality
    reads: list[Read] = Field(default_factory=list)
    evidence: Evidence | None = None
    # Values crossed out or overwritten at this location (e.g. a corrected strength).
    alterations: list[str] = Field(default_factory=list)


class RawPrescriptionExtraction(ContractModel):
    prescription_id: str
    source: dict[str, str]  # type, original_path, processed_path, sha256
    is_prescription: bool
    fields: dict[str, RawField]

    # Inputs for the identity validator (DESIGN.md §11).
    patient_name_occurrences: list[str] = Field(default_factory=list)
    patient_dob_occurrences: list[str] = Field(default_factory=list)
    prescription_block_count: int = 1

    untrusted_text: list[str] = Field(default_factory=list)
    models: dict[str, str] = Field(default_factory=dict)
    # Non-fatal problems, e.g. the secondary read failed. Never silently dropped.
    errors: list[str] = Field(default_factory=list)
