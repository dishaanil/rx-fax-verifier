"""Static guards for the authority boundary and offline scope."""

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
APP_FILES = [p for p in BACKEND.rglob("*.py") if "tests" not in p.parts]


def _is_approved(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute) and node.attr == "APPROVED":
        return isinstance(node.value, ast.Name) and node.value.id == "PrescriptionStatus"
    return isinstance(node, ast.Constant) and node.value == "APPROVED"


class _StatusAssignments(ast.NodeVisitor):
    """Records (file, innermost enclosing function) for every `status` set to APPROVED."""

    def __init__(self, rel: str) -> None:
        self.rel = rel
        self.stack = ["<module>"]
        self.found: set[tuple[str, str]] = set()

    def _func(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _func

    def _hit(self):
        self.found.add((self.rel, self.stack[-1]))

    def visit_Assign(self, node):
        if _is_approved(node.value) and any(_is_status_target(t) for t in node.targets):
            self._hit()
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if node.value is not None and _is_approved(node.value) and _is_status_target(node.target):
            self._hit()
        self.generic_visit(node)

    def visit_keyword(self, node):
        if node.arg == "status" and _is_approved(node.value):
            self._hit()
        self.generic_visit(node)

    def visit_Dict(self, node):
        if any(isinstance(k, ast.Constant) and k.value == "status" and _is_approved(v) for k, v in zip(node.keys, node.values)):
            self._hit()
        self.generic_visit(node)


def _is_status_target(target: ast.AST) -> bool:
    return (isinstance(target, ast.Attribute) and target.attr == "status") or (
        isinstance(target, ast.Name) and target.id == "status"
    )


def _status_assignments() -> set[tuple[str, str]]:
    found = set()
    for path in APP_FILES:
        visitor = _StatusAssignments(path.relative_to(BACKEND).as_posix())
        visitor.visit(ast.parse(path.read_text()))
        found |= visitor.found
    return found


def test_approved_assigned_only_by_approval_service():
    assert _status_assignments() == {("review/service.py", "approve")}


def test_forbidden_modules_never_reference_approved():
    for rel in ("pipeline.py", "policy/router.py", "extraction/stub.py", "extraction/raw.py", "intake.py"):
        source = (BACKEND / rel).read_text()
        tree = ast.parse(source)
        assigns = [n for n in ast.walk(tree) if isinstance(n, (ast.Assign, ast.keyword)) and _is_approved(getattr(n, "value", None))]
        assert assigns == [], rel


def test_main_routes_delegate_approval():
    tree = ast.parse((BACKEND / "main.py").read_text())

    assert not any(_is_approved(n) for n in ast.walk(tree))


def test_no_network_or_ai_imports_anywhere():
    forbidden = {"socket", "urllib", "requests", "httpx", "aiohttp", "anthropic", "openai"}
    offenders = []
    for path in APP_FILES:
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            offenders += [f"{path.name}: {n}" for n in names if n.split(".")[0] in forbidden]
    assert offenders == []
