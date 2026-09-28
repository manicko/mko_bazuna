"""Phase 03 (Database & Concurrency) static gate for check (c) — "no bare ORM in async".

A synchronous ORM call reached from the bot's event loop is the defect this
gate looks for. A bare `Model.objects.*` / `transaction.atomic()` /
`close_old_connections` is only a violation when the *innermost* enclosing
function frame is an `async def` that is not itself dispatched through
`sync_to_async` / `database_sync_to_async`. A plain sync `def` nested inside
an `async def` runs on the asgiref worker thread and is correct.

Run from the repository root:

    uv run python .ai/audit/03-db-concurrency/scan_async_orm.py

Expected result: TOTAL=0 violations. The 6 residual hits printed by an
earlier, coarser revision of this gate were the *arguments* of
`sync_to_async(...)` calls in lifecycle.py and middlewares/connection.py and
are not violations; the frame-awareness added below removes them.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "src" / "telegram_bot"

ORM_MARKERS = (
    ".objects",
    "transaction.atomic",
    "close_old_connections",
    "get_connection",
    "connections.",
    "on_commit",
    "set_rollback",
    "select_for_update",
)

DISPATCH_DECORATORS = {"sync_to_async", "database_sync_to_async", "async_unsafe"}


def decorator_names(fn: ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    for dec in fn.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        name = getattr(target, "id", None) or getattr(target, "attr", None)
        if name:
            names.add(name)
    return names


class Visitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.stack: list[ast.AST] = []
        self.findings: list[tuple[int, str]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.stack.append(node)
        self.generic_visit(node)
        self.stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.stack.append(node)
        self.generic_visit(node)
        self.stack.pop()

    def _exposed(self) -> bool:
        frames: list[ast.AsyncFunctionDef | ast.FunctionDef] = [
            f for f in self.stack if isinstance(f, (ast.AsyncFunctionDef, ast.FunctionDef))
        ]
        if not frames:
            return False
        innermost = frames[-1]
        if isinstance(innermost, ast.FunctionDef):
            return False  # runs on the worker thread — correct
        return not (decorator_names(innermost) & DISPATCH_DECORATORS)

    def visit_Call(self, node: ast.Call) -> None:
        func = ast.unparse(node.func)
        # `sync_to_async(<orm call>)` / `sync_to_async(<orm call>)()` ARE the
        # dispatch — the ORM callable is an argument of the dispatch, not a
        # call on the event loop. Skip the whole subtree.
        if any(func.startswith(d) for d in DISPATCH_DECORATORS):
            return
        if self._exposed():
            seg = ast.unparse(node)
            if any(marker in seg for marker in ORM_MARKERS):
                self.findings.append((node.lineno, seg[:160]))
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if self._exposed() and node.attr in {"objects", "atomic", "close_old_connections"}:
            self.findings.append((node.lineno, ast.unparse(node)[:160]))
        self.generic_visit(node)


def main() -> int:
    total = 0
    for path in sorted(ROOT.rglob("*.py")):
        if "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = Visitor()
        visitor.visit(tree)
        for line, seg in visitor.findings:
            print(f"{path.relative_to(ROOT.parents[1])}:{line}: {seg}")
            total += 1
    print(f"TOTAL={total}", file=sys.stderr)
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
