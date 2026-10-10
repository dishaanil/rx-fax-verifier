from typing import Any

from backend.models.base import ContractModel


class Resolution(ContractModel):
    source: str
    value: str | None
    confirmed_by: dict[str, Any] | None = None
    evidence: dict[str, Any] | None = None
    approved_by: str | None = None
