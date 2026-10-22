from typing import Any

from pydantic import Field

from backend.models.base import ContractModel
from backend.models.enums import PrescriptionStatus
from backend.models.exception import RxException
from backend.models.field_result import FieldResult


class Prescription(ContractModel):
    prescription_id: str
    status: PrescriptionStatus

    source: dict[str, Any]

    fields: dict[str, FieldResult]
    exceptions: list[RxException] = Field(default_factory=list)

    clarifications: list[dict[str, Any]] = Field(default_factory=list)
    approved_by: str | None = None
    audit_events: list[dict[str, Any]] = Field(default_factory=list)
    # After approval: how it was filled (FILL / PARTIAL_FILL / ORDER / TRANSFER). Never affects approval.
    fulfillment: dict[str, Any] | None = None
