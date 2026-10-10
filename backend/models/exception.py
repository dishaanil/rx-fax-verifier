from typing import Any

from pydantic import Field

from backend.models.base import ContractModel


class RxException(ContractModel):
    exception_id: str
    type: str
    field: str
    severity: str
    reason: str
    source_evidence: dict[str, Any] | None = None
    candidate_values: list[str] = Field(default_factory=list)
    required_action: str
