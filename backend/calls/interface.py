"""What a prescriber call needs and what it returns, whoever places it."""

import re
from dataclasses import dataclass, field
from typing import Literal, Protocol

Outcome = Literal["ANSWERED", "UNCLEAR", "FAILED"]


class CallError(RuntimeError):
    """The call could not be placed or completed (recorded as FAILED, never raised to the pharmacist)."""


@dataclass(frozen=True)
class CallRequest:
    call_id: str
    prescription_id: str
    exception_id: str
    to_number: str
    prescriber: str
    patient: str
    patient_dob: str | None
    field: str
    field_label: str
    question: str
    # Other values read from the fax, for the agent's context (e.g. the drug when asking for the strength).
    context: dict[str, str]
    # Upload file stem; the simulation uses it to find the demo prescriber's chart.
    source_name: str | None = None


@dataclass(frozen=True)
class Turn:
    role: Literal["agent", "prescriber"]
    text: str


@dataclass
class CallResult:
    outcome: Outcome
    # The clarified value, exactly as the prescriber confirmed it; None unless ANSWERED.
    answer: str | None
    summary: str
    transcript: list[Turn] = field(default_factory=list)
    provider_call_id: str | None = None
    # PRISM audit events for the call's model calls (simulation only).
    prism_events: list[dict] = field(default_factory=list)


class Caller(Protocol):
    name: str
    simulated: bool

    def place_call(self, request: CallRequest) -> CallResult: ...


def to_e164(number: str | None) -> str | None:
    """'(718) 555-0177' -> '+17185550177'; None unless it is a 10-digit US number."""
    digits = re.sub(r"\D", "", number or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return f"+1{digits}" if len(digits) == 10 else None
