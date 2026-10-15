"""The pharmacy agent's lines. Shared by the simulation and (as dynamic variables) the real agent.

The agent asks one open question and never suggests a value: "What strength
did you prescribe?", not "Is it 15 mg?". Suggesting the value we read would
invite the prescriber to agree with our misreading.
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


def question_for(field: str, label: str, context: dict[str, str]) -> str:
    drug = context.get("drug")
    # Only name the drug when it isn't the thing being asked about and was read cleanly.
    for_drug = f" for the {drug}" if drug and field != "drug" and "?" not in drug else ""
    template = _QUESTIONS.get(field, "Could you tell me the {label} you wrote?")
    return template.format(for_drug=for_drug, sig=context.get("sig", ""), label=label.lower())


def opening(request_patient: str, patient_dob: str | None) -> str:
    dob = f", date of birth {patient_dob}" if patient_dob else ""
    return (f"Hello, this is an automated assistant calling from {PHARMACY}. I'm an AI, and I'm calling to "
            f"clarify one detail on a faxed prescription for {request_patient}{dob}.")


def read_back(label: str, value: str) -> str:
    return f"Thank you. To confirm, the {label.lower()} is {value}. Is that correct?"


def closing(answered: bool) -> str:
    if answered:
        return "Thank you. The pharmacist will review this before anything is dispensed. Goodbye."
    return "Thank you. I'll let the pharmacist know, and they may call you back. Goodbye."
