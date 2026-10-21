"""The pharmacy agent's lines. Shared by the simulation and (as dynamic variables) the real agent.

The agent asks one open question and never suggests a value: "What strength
did you prescribe?", not "Is it 15 mg?". Suggesting the value we read would
invite the prescriber to agree with our misreading.

The exception is a quantity conflict: both numbers really are on the fax (one
written, one implied by the directions), so the agent states the mismatch.
Without it the prescriber has no reason to reconsider the quantity.
"""

PHARMACY = "RxBridge Pharmacy"

_LABELS = {
    "patient": "Patient name", "patient_dob": "Date of birth", "drug": "Drug", "strength": "Strength",
    "form": "Form", "sig": "Directions", "quantity": "Quantity", "days_supply": "Days supply",
    "refills": "Refills", "prescriber": "Prescriber", "prescriber_identifier": "NPI",
    "prescriber_phone": "Prescriber phone", "date_written": "Date written",
}


def field_label(field: str) -> str:
    return _LABELS.get(field, field.replace("_", " ").capitalize())


_QUESTIONS = {
    "drug": "Which medication did you prescribe? The drug name is hard to read on the fax.",
    "strength": "What strength did you prescribe{for_drug}?",
    "quantity": "What quantity should we dispense{for_drug}? The directions read \"{sig}\".",
    "sig": "What directions did you intend{for_drug}?",
    "prescriber_identifier": "Could you give me your NPI number? The one on the fax doesn't pass its check.",
    "patient": "Could you confirm the patient's full name?",
    "patient_dob": "Could you confirm the patient's date of birth?",
    "refills": "How many refills did you authorize{for_drug}?",
    "date_written": "What date did you write this prescription?",
}


def question_for(field: str, label: str, context: dict[str, str], conflict: tuple[str, str] | None = None) -> str:
    """`conflict` is (written, implied) for a quantity that doesn't match the directions."""
    drug = context.get("drug")
    # Only name the drug when it isn't the thing being asked about and was read cleanly.
    for_drug = f" for the {drug}" if drug and field != "drug" and "?" not in drug else ""
    sig = context.get("sig", "").rstrip(".")
    if field == "quantity" and conflict:
        written, implied = conflict
        directions = f'The directions, "{sig}", work out to' if sig else "The directions work out to"
        return (f"{directions} {implied}, but the fax says to dispense {written}. "
                f"What quantity did you intend{for_drug}?")
    template = _QUESTIONS.get(field, "Could you tell me the {label} you wrote?")
    return template.format(for_drug=for_drug, sig=sig, label=label.lower())


def opening(request_patient: str, patient_dob: str | None) -> str:
    dob = f", date of birth {patient_dob}" if patient_dob else ""
    return (f"Hello, this is an automated assistant calling from {PHARMACY}. I'm an AI, and I'm calling to "
            f"clarify one detail on a faxed prescription for {request_patient}{dob}.")


def noted(corrections) -> str:
    """Acknowledge corrections the prescriber volunteered; the pharmacist decides on them."""
    if not corrections:
        return ""
    items = " and ".join(f"the {field_label(c.field).lower()} is {c.value}" for c in corrections)
    return f"I've noted that {items}; the pharmacist will review that. "


def read_back(label: str, value: str) -> str:
    return f"Thank you. To confirm, the {label.lower()} is {value}. Is that correct?"


def closing(answered: bool) -> str:
    if answered:
        return "Thank you. The pharmacist will review this before anything is dispensed. Goodbye."
    return "Thank you. I'll let the pharmacist know, and they may call you back. Goodbye."
