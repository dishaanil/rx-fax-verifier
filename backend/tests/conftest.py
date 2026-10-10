import json
from pathlib import Path

import pytest

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "rx_037.json"


@pytest.fixture
def rx_037() -> dict:
    with FIXTURE_PATH.open() as f:
        return json.load(f)
