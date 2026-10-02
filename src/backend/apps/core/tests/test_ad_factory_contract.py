"""Contract test for the ``create_test_ad`` / ``create_test_ads_bulk`` factories.

VAL-002: ``ON_MODERATION`` is produced only *transiently* by production code
(``auto_moderate`` resolves it in the same transaction — pass becomes
``PUBLISHED``, fail becomes ``ON_MODERATION_FAILED``, raise rolls back). A test
that relies on the factory's default silently fabricates a state production
cannot durably hold, so the suite can never validate a fix that makes the state
real.

:func:`test_no_factory_call_relies_on_a_silent_default` walks the call graph of
both test packages and requires every ``create_test_ad`` / ``create_test_ads_bulk``
call to be *status-grounded* — it either passes a literal ``status=`` keyword,
or forwards ``**kwargs`` from an enclosing function that declares a ``status``
parameter or splats a dict containing a ``"status"`` key. A bare ``**``-splat
from a function that never mentions ``status`` fails.
"""

from __future__ import annotations

import ast

from django.conf import settings

_FACTORY_NAMES = frozenset({"create_test_ad", "create_test_ads_bulk"})
_PROJECT_ROOT = settings.BASE_DIR.parent
_CONFTEST = _PROJECT_ROOT / "src" / "backend" / "conftest.py"
_SEARCH_ROOTS = (
    _PROJECT_ROOT / "src" / "backend",
    _PROJECT_ROOT / "src" / "telegram_bot",
)


def _iter_test_modules():
    """Yield every ``*.py`` module under the searched roots, except conftest."""
    for root in _SEARCH_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if path == _CONFTEST:
                continue
            yield path


def _enclosing_function(
    tree: ast.AST,
) -> dict[int, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Map each node id to its innermost enclosing function definition."""
    enclosing: dict[int, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                enclosing.setdefault(id(child), node)
    return enclosing


def _declares_status(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True if *func* declares a ``status`` parameter (regular or kw-only)."""
    args = func.args
    names = {arg.arg for arg in (*args.args, *args.kwonlyargs, *args.posonlyargs)}
    return "status" in names


def _dict_literal_has_status(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True if *func* builds any dict literal containing a ``"status"`` key.

    Covers an inline ``**{...}`` splat and a named local that is later splatted
    (``defaults = {..., "status": ...}`` then ``**defaults``). ``.update()``
    calls are also inspected because a caller may merge a status in after the
    literal is created.
    """
    status_names: set[str] = set()
    for node in ast.walk(func):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        if isinstance(value, ast.Dict) and _dict_has_status_key(value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    status_names.add(target.id)

    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            if _call_splats_status_dict(node):
                return True
            if _call_updates_with_status(node, status_names):
                return True
        elif isinstance(node, ast.Dict) and _dict_has_status_key(node):
            return True
    return False


def _dict_has_status_key(node: ast.Dict) -> bool:
    """True if a dict literal has a constant ``"status"`` key."""
    return any(
        isinstance(key, ast.Constant) and key.value == "status" for key in node.keys
    )


def _call_splats_status_dict(node: ast.Call) -> bool:
    """True if the call splats an inline dict literal carrying ``"status"``."""
    for keyword in node.keywords:
        if keyword.arg is None and isinstance(keyword.value, ast.Dict):
            if _dict_has_status_key(keyword.value):
                return True
    return False


def _call_updates_with_status(node: ast.Call, status_names: set[str]) -> bool:
    """True if the call is ``<status-bearing local>.update(..., status=...)``."""
    if not (isinstance(node.func, ast.Attribute) and node.func.attr == "update"):
        return False
    if not (isinstance(node.func.value, ast.Name) and node.func.value.id in status_names):
        return False
    return any(
        (kw.arg == "status") or (kw.arg is None and isinstance(kw.value, ast.Dict))
        for kw in node.keywords
    )


def _factory_call_name(node: ast.Call) -> str | None:
    """Return the factory name for a call, or None if it is not a factory call."""
    if isinstance(node.func, ast.Name) and node.func.id in _FACTORY_NAMES:
        return node.func.id
    if isinstance(node.func, ast.Attribute) and node.func.attr in _FACTORY_NAMES:
        return node.func.attr
    return None


def _is_status_grounded(
    call: ast.Call,
    enclosing: ast.FunctionDef | ast.AsyncFunctionDef | None,
) -> bool:
    """True if the factory call cannot silently inherit an uncommittable default.

    A literal ``status=`` keyword always grounds the call. Otherwise the
    enclosing function must itself carry a ``status`` parameter or splat a
    dict containing a ``"status"`` key, so the forwarded value is reviewable.
    """
    if any(keyword.arg == "status" for keyword in call.keywords):
        return True
    if enclosing is None:
        return False
    return _declares_status(enclosing) or _dict_literal_has_status(enclosing)


def test_no_factory_call_relies_on_a_silent_default() -> None:
    """Every factory call is status-grounded (literal or reviewable wrapper)."""
    violations: list[str] = []
    for path in _iter_test_modules():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - a syntax error fails elsewhere
            continue
        enclosing = _enclosing_function(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _factory_call_name(node) is None:
                continue
            if not _is_status_grounded(node, enclosing.get(id(node))):
                rel = path.relative_to(_PROJECT_ROOT).as_posix()
                violations.append(f"{rel}:{node.lineno}")

    assert not violations, (
        "create_test_ad / create_test_ads_bulk called without a reviewable "
        "status. Pass status= explicitly, or give the wrapping helper an "
        "explicit status parameter / a splatted dict containing a 'status' "
        "key:\n  " + "\n  ".join(violations)
    )
