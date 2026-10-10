from backend.models.base import ContractModel
from backend.models.enums import SignalStatus


class Signal(ContractModel):
    type: str
    status: SignalStatus
    detail: str | None = None
