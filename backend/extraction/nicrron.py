"""NicrronExtractor: the real ExtractionProvider, selected with RXBRIDGE_EXTRACTOR=nicrron.

Imported lazily by backend.extraction.stub.get_extractor so the stub path
never needs the AI dependencies.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from backend.extraction.extractor import NicrronExtraction, extract
from backend.extraction.gateway import NicrronGateway, Tracer

_ROOT = Path(__file__).resolve().parents[2]


class NicrronExtractor:
    def __init__(self, tracer: Tracer | None = None, processed_dir: str | Path | None = None) -> None:
        load_dotenv(_ROOT / ".env")
        self.gateway = NicrronGateway(tracer=tracer)  # raises if the key/base URL is not configured
        self.processed_dir = processed_dir or os.environ.get("RXBRIDGE_PROCESSED_DIR")

    def extract(self, path: str, prescription_id: str) -> NicrronExtraction:
        return extract(path, prescription_id, gateway=self.gateway, processed_dir=self.processed_dir)
