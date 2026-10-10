from typing import Protocol

from backend.extraction.raw import RawPrescriptionExtraction


class ExtractionError(Exception):
    """The document could not be turned into a raw extraction."""


class ExtractionProvider(Protocol):
    def extract(self, path: str, prescription_id: str) -> RawPrescriptionExtraction: ...
