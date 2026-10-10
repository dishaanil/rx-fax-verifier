"""Deterministic offline extractor: maps an upload's filename stem to
fixtures/raw_<stem>.json. No network, no model calls."""

import os
from pathlib import Path

from pydantic import ValidationError

from backend.extraction.interface import ExtractionError, ExtractionProvider
from backend.extraction.raw import RawPrescriptionExtraction

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"
STUB_IDS = ("rx_037", "rx_A", "rx_C", "rx_D", "rx_E", "rx_F")


class StubExtractor:
    def __init__(self, fixtures_dir: Path = FIXTURES_DIR) -> None:
        self.fixtures_dir = fixtures_dir

    def extract(self, path: str, prescription_id: str) -> RawPrescriptionExtraction:
        fixture = self.fixtures_dir / f"raw_{Path(path).stem}.json"
        if not fixture.is_file():
            raise ExtractionError(f"No stub extraction for {Path(path).name!r}.")
        try:
            raw = RawPrescriptionExtraction.model_validate_json(fixture.read_bytes())
        except ValidationError as exc:
            raise ExtractionError(f"Stub fixture {fixture.name} is not a valid extraction.") from exc
        return raw.model_copy(update={"prescription_id": prescription_id})


def get_extractor() -> ExtractionProvider:
    name = os.environ.get("RXBRIDGE_EXTRACTOR", "stub").strip().lower()
    if name == "stub":
        return StubExtractor()
    if name == "nicrron":
        # Lazy import: this branch must not depend on AI packages.
        from backend.extraction.nicrron import NicrronExtractor  # type: ignore[import-not-found]

        return NicrronExtractor()
    raise ValueError(f"Unknown RXBRIDGE_EXTRACTOR {name!r}; expected 'stub' or 'nicrron'.")
