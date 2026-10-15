"""Demo prescriber charts for the SIMULATED call only.

The simulated prescriber needs to know what they actually prescribed, so it
reads the demo faxes' ground truth (fixtures/demo/truth.json). This is the
prescriber's knowledge, not RxBridge's: nothing in extraction, the pipeline or
review may import this module (test_calls.py checks).
"""

import json
from functools import cache
from pathlib import Path

TRUTH = Path(__file__).resolve().parents[2] / "fixtures" / "demo" / "truth.json"


@cache
def _records() -> dict[str, dict]:
    try:
        return {r["id"]: r for r in json.loads(TRUTH.read_text())}
    except (OSError, ValueError, KeyError):
        return {}


def chart_for(source_name: str | None) -> dict[str, str] | None:
    """What the prescriber of a demo fax knows, or None for any other upload."""
    record = _records().get(source_name or "")
    if record is None:
        return None
    med, pr, pt = record["medication"], record["prescriber"], record["patient"]
    quantity = record.get("quantity")
    return {
        "patient": pt["name"],
        "patient date of birth": pt["dob"],
        "drug": med["drug"],
        "strength": med["strength"],
        "form": med["form"],
        "directions": record["sig_as_written"],
        "quantity": quantity if isinstance(quantity, str) else f"{quantity} {med['form']}s",
        "refills": str(record.get("refills")),
        "date written": record["date_written"],
        # Demo E's fax has a corrupted digit; the prescriber knows their real NPI.
        "your NPI": record.get("valid_npi_before_corruption") or pr["npi"],
    }
