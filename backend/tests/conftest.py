import json
from pathlib import Path

import pytest

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "rx_037.json"


@pytest.fixture
def rx_037() -> dict:
    with FIXTURE_PATH.open() as f:
        return json.load(f)


def fixed_clock() -> str:
    return "2026-10-10T14:00:00Z"


def processed(pid: str, seen: set[str] | None = None, sha: str | None = None):
    """Run a stub raw fixture through the pipeline with a fixed clock."""
    from backend.extraction import StubExtractor
    from backend.pipeline import process

    raw = StubExtractor().extract(f"{pid}.png", pid)
    return process(raw, seen or set(), sha or f"sha-{pid}", clock=fixed_clock)


def raw_fixture(pid: str):
    from backend.extraction import StubExtractor

    return StubExtractor().extract(f"{pid}.png", pid)
