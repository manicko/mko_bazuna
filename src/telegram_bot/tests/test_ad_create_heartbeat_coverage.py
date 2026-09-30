"""AST coverage guard for the draft idle-timeout heartbeat (03-DB-003).

Every handler registered on an ``AdCreateForm.<state>`` must call
``touch_draft`` on entry, and every ``AdCreateForm`` state must have such a
handler.  A missed call site reaps a live seller draft — data loss — and is
**unobservable from behaviour**: a missing heartbeat is indistinguishable from a
seller who simply walked away, so no behavioural test can fail when a site is
missing.  The invariant therefore has to be asserted over the code's STRUCTURE.

This is the one test in the block permitted to assert over source shape (see the
block's ``architectural_constraints``).  It is scoped deliberately:

* it asserts a POSITIVE — every guarded handler contains a call to ``touch_draft``;
* and a TWO-WAY invariant — ``set(AdCreateForm states) == set(states seen on
  guarded handlers)``.  Without the second direction a brand-new state with no
  handler at all would be invisible to the guard.

Pure ``ast``: no database, no Django import, milliseconds to run.
"""

from __future__ import annotations

import ast
from pathlib import Path

_HANDLERS_DIR = Path(__file__).resolve().parents[1] / "handlers" / "ad_create"
_PACKAGE_INIT = _HANDLERS_DIR / "__init__.py"

# The heartbeat helper the guarded handlers must call.
_HEARTBEAT_CALL = "touch_draft"


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _ad_create_form_states() -> set[str]:
    """Return the ``AdCreateForm`` state attribute names, without importing Django.

    The states are declared as assignments in the ``AdCreateForm`` class body in
    ``handlers/ad_create/__init__.py`` (e.g. ``category = AdCreateState.CATEGORY``),
    so the class body's plain names are the state set.
    """
    states: set[str] = set()
    for node in _parse(_PACKAGE_INIT).body:
        if isinstance(node, ast.ClassDef) and node.name == "AdCreateForm":
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name):
                            states.add(target.id)
    return states


def _decorator_states(decorator: ast.expr) -> set[str]:
    """Return the ``AdCreateForm.<state>`` names referenced by a router decorator.

    Any ``@router.*(...)`` call the handler carries is inspected; each
    ``AdCreateForm.<state>`` attribute access it contains contributes that state.
    """
    states: set[str] = set()
    if not isinstance(decorator, ast.Call):
        return states
    func = decorator.func
    if not (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "router"
    ):
        return states
    for sub in ast.walk(decorator):
        if (
            isinstance(sub, ast.Attribute)
            and isinstance(sub.value, ast.Name)
            and sub.value.id == "AdCreateForm"
        ):
            states.add(sub.attr)
    return states


def _contains_heartbeat(func: ast.AST) -> bool:
    """True if *func* contains a call whose unparsed source names ``touch_draft``."""
    for sub in ast.walk(func):
        if isinstance(sub, ast.Call) and _HEARTBEAT_CALL in ast.unparse(sub):
            return True
    return False


def _collect_guarded_handlers() -> dict[str, tuple[str, set[str]]]:
    """Map handler name -> (filename, states) for every router-registered handler.

    A "guarded handler" is a module-level function carrying a ``router.*``
    decorator that references at least one ``AdCreateForm.<state>``.
    """
    handlers: dict[str, tuple[str, set[str]]] = {}
    for path in sorted(_HANDLERS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        for node in _parse(path).body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            states: set[str] = set()
            for decorator in node.decorator_list:
                states |= _decorator_states(decorator)
            if states:
                handlers[node.name] = (path.name, states)
    return handlers


def test_every_guarded_handler_calls_the_heartbeat() -> None:
    """Every router-registered ``AdCreateForm`` handler heartbeats on entry."""
    missing: list[str] = []
    for path in sorted(_HANDLERS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        for node in _parse(path).body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            states: set[str] = set()
            for decorator in node.decorator_list:
                states |= _decorator_states(decorator)
            if states and not _contains_heartbeat(node):
                missing.append(
                    f"{path.name}::{node.name} (states: {sorted(states)})"
                )
    assert not missing, (
        "Handlers registered on an AdCreateForm state must call "
        f"{_HEARTBEAT_CALL} on entry; missing heartbeat in: {missing}"
    )


def test_state_set_matches_guarded_handlers() -> None:
    """The two-way invariant: states == states seen on guarded handlers.

    The forward direction (handlers -> states) is covered by the test above.  The
    reverse direction (states -> handlers) is the one that catches a brand-new
    ``AdCreateForm`` state whose handler was never written — otherwise invisible
    to a handlers-only scan.
    """
    guarded = _collect_guarded_handlers()
    covered: set[str] = set()
    for _filename, states in guarded.values():
        covered |= states

    declared = _ad_create_form_states()

    assert declared == covered, (
        "AdCreateForm states and the states guarded by router handlers must "
        "match exactly.\n"
        f"  declared but unguarded: {sorted(declared - covered)}\n"
        f"  guarded but undeclared: {sorted(covered - declared)}"
    )
