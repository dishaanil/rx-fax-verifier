from backend.models.base import ContractModel


class Read(ContractModel):
    source: str
    value: str | None


class Evidence(ContractModel):
    page: int | None = None
    # JSON array [x0, y0, x1, y1]; dumps back to a list in mode="json".
    bbox: tuple[int, int, int, int] | None = None
