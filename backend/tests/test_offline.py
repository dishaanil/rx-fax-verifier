"""Guard: the validator/normalization slice must not import network or AI clients."""

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
FORBIDDEN = {"socket", "http", "urllib", "requests", "httpx", "aiohttp", "anthropic", "openai"}


def test_no_network_imports():
    offenders = []
    for package in ("models", "normalization", "references", "validators"):
        for path in (BACKEND / package).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                else:
                    continue
                offenders += [f"{path.name}: {n}" for n in names if n.split(".")[0] in FORBIDDEN]

    assert offenders == []
