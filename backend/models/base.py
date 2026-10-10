from pydantic import BaseModel, ConfigDict


class ContractModel(BaseModel):
    """Base for contract models: unknown keys are rejected, never silently dropped."""

    model_config = ConfigDict(extra="forbid")
