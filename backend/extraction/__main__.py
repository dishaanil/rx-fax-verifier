"""Smoke test: python -m backend.extraction <fax.png> [prescription_id]"""

import sys
from pathlib import Path

from backend.extraction.nicrron import NicrronExtractor

path = Path(sys.argv[1])
rx_id = sys.argv[2] if len(sys.argv) > 2 else path.stem
print(NicrronExtractor().extract(str(path), rx_id).model_dump_json(indent=2))
