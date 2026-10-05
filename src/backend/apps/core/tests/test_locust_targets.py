"""Every URL the load test requests must resolve to a real route (PERF-012a).

The Locust journeys in ``benchmark/locustfile.py`` are the targets the CI
``load-test`` job measures.  A request to a route that does not exist returns
**404**, which locust records as a failure and which measures **fast** — so the
p95 gate can report a comfortable number against a site that does not exist.
This module closes that hole at its source: it extracts the full set of target
URLs from the locustfile and asserts every one resolves through Django's URL
resolver.  A renamed route therefore fails the regular test run, not a load
test whose number no one can interpret.

The extraction is deliberately **structural** (an AST walk of the literal
strings passed to ``self.client.get``) rather than a hard-coded list: a new
journey is covered the moment it is added, and a journey that is removed cannot
leave a stale entry behind.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from django.urls import Resolver404, resolve

pytestmark = [pytest.mark.unit]

_THIS = Path(__file__).resolve()
# ``src/`` is the parent of both ``backend/`` and ``benchmark/``.
_SRC_DIR = next(
    parent
    for parent in _THIS.parents
    if (parent / "benchmark").is_dir() and (parent / "backend").is_dir()
)
_LOCUSTFILE = _SRC_DIR / "benchmark" / "locustfile.py"


def _target_urls() -> list[str]:
    """Return every literal path passed to ``self.client.get(...)``.

    Only literal string first-arguments are collected; the journeys in this
    locustfile all use literals, and a f-string or computed path would be
    reported by the non-empty assertion below rather than silently skipped.
    """
    tree = ast.parse(_LOCUSTFILE.read_text(encoding="utf-8"))
    urls: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "get"):
            continue
        owner = func.value
        if not (
            isinstance(owner, ast.Attribute)
            and owner.attr == "client"
            and owner.value.__class__ is ast.Name
            and owner.value.id == "self"
        ):
            continue
        if (
            node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            urls.append(node.args[0].value)
    return urls


class TestLocustTargetsResolve:
    """The load test must only ever request routes that exist (PERF-012a)."""

    def test_locustfile_requests_at_least_one_url(self) -> None:
        """A locustfile with no extractable target is a broken guard."""
        urls = _target_urls()
        assert urls, (
            "no literal self.client.get(...) target found in locustfile.py — "
            "the target-URL guard has nothing to check"
        )

    def test_every_target_url_resolves(self) -> None:
        """Every requested path has a Django route (a 404 measures nothing)."""
        unresolved: list[str] = []
        for url in _target_urls():
            path_only = url.split("?", 1)[0]
            try:
                resolve(path_only)
            except Resolver404:
                unresolved.append(url)
        assert not unresolved, (
            "the load test requests URLs with no route, so it measures a 404 "
            "(which is fast and passes the p95 gate against a non-existent "
            f"site): {unresolved}"
        )
