"""Smoke + purity tests for the ``/api/v1/`` URL-only aggregator.

Covers two guarantees established by task S0.2:

1. **Mount smoke.** ``/api/v1/<arbitrary>`` resolves to 404 (no route exists)
   and never leaks an exception as a 500. ``/api/v1/ads/`` (S1.3) and
   ``/api/v1/search/`` (S1.4) are now live routes and are deliberately NOT in
   the arbitrary-path list.
2. **Aggregator purity.** ``apps/api/urls.py`` performs no non-django imports —
   it must import only ``django.*`` / stdlib modules so the aggregator can never
   drag a view, service or model (and thus a new import cycle) into the graph.
   This guard must keep holding as later stages append ``include()`` lines.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest
from django.test import Client

from apps.api import urls as api_urls

# Arbitrary paths that currently have no route registered under /api/v1/.
# ``/api/v1/ads/`` (S1.3) and ``/api/v1/search/`` (S1.4) are excluded: they are
# shipped routes.
ARBITRARY_PATHS = [
    "/api/v1/",
    "/api/v1/ads/1/",
    "/api/v1/does-not-exist/",
    "/api/v1/deeply/nested/unknown/path/",
]


@pytest.mark.django_db
def test_mount_unknown_paths_return_404() -> None:
    """Every arbitrary ``/api/v1/...`` path returns 404, never a 500."""
    client = Client()
    for path in ARBITRARY_PATHS:
        response = client.get(path)
        assert response.status_code == 404, (
            f"GET {path} expected 404 (no routes mounted yet), "
            f"got {response.status_code}"
        )


def test_aggregator_source_performs_no_non_django_imports() -> None:
    """``apps/api/urls.py`` imports only ``django.*`` / stdlib modules."""
    source_path = Path(api_urls.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))

    imported_modules = _collect_imported_modules(tree)
    for module_name in imported_modules:
        assert _is_django_or_stdlib(module_name), (
            f"apps/api/urls.py imports '{module_name}', which is neither a "
            "django.* module nor stdlib; the URL-only aggregator may not import "
            "views, services or models."
        )


def _collect_imported_modules(tree: ast.AST) -> set[str]:
    """Return the absolute module names named by every import in ``tree``."""
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            # ``level > 0`` is a relative import; resolve it against this package.
            if node.level:
                modules.add(_resolve_relative(node))
            elif node.module:
                modules.add(node.module)
    return modules


def _resolve_relative(node: ast.ImportFrom) -> str:
    """Resolve a relative ``ImportFrom`` node to its absolute dotted name."""
    package_parts = api_urls.__name__.split(".")[: -node.level]
    relative = ".".join(package_parts)
    if node.module:
        return f"{relative}.{node.module}" if relative else node.module
    return relative


def _is_django_or_stdlib(module_name: str) -> bool:
    """Return True for ``django.*`` modules and top-level stdlib modules."""
    top_level = module_name.split(".", 1)[0]
    if top_level == "django":
        return True
    return top_level in sys.stdlib_module_names
