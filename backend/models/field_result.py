"""FieldResult — the single per-field contract (DESIGN.md §7).

Contract rules (enforced by later slices, not here): raw_value is never
overwritten; validators append signals; verified critical fields retain
provenance; human corrections preserve earlier reads and signals; a
resolution triggers revalidation; AI never sets APPROVED.
"""

from pydantic import Field

from backend.models.base import ContractModel
from backend.models.enums import FieldDecision, SourceQuality
from backend.models.evidence import Evidence, Read
from backend.models.resolution import Resolution
from backend.models.signal import Signal


class FieldResult(ContractModel):
    raw_value: str | None = None
    normalized_value: str | None = None
    source_quality: SourceQuality

    reads: list[Read] = Field(default_factory=list)
    evidence: Evidence | None = None
    signals: list[Signal] = Field(default_factory=list)
    candidates: list[str] = Field(default_factory=list)

    decision: FieldDecision
    reason: str | None = None
    resolution: Resolution | None = None
