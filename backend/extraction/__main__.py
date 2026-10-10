"""Smoke test: python -m backend.extraction <fax.png> [prescription_id]"""

import sys
from pathlib import Path

from dotenv import load_dotenv

from backend.extraction import extract

load_dotenv()

path = Path(sys.argv[1])
rx_id = sys.argv[2] if len(sys.argv) > 2 else path.stem
print(extract(path, rx_id).model_dump_json(indent=2))
