"""
Header child-existence N+1 guard (13-PERF-009 validated 2026-09).

The shared catalog header renders an "expand" button for every root category
that has children.  It used to call ``cat.get_children.exists`` per root in the
template, issuing one indexed ``SELECT 1 ... LIMIT 1`` **per non-leaf root**.
``header_context`` now annotates ``root_categories`` with a single correlated
``Exists``, so the header issues a constant number of child-existence queries
regardless of how many roots have children.

This is the tripwire: it renders the real header at a multi-root fixture and
counts the child-existence SELECTs.  Before the annotation the count scaled
with the root count (measured 10 for 5 non-leaf roots x 2 render sites);
after, it is bounded by a small constant.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.categories.models import Category

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# The header renders the root list twice (desktop dropdown + mobile
# off-canvas).  With the ``Exists`` annotation each render site reuses the
# annotated rows, so the total is a small constant, not ``roots x sites``.
_CHILD_EXISTENCE_BOUND = 1


def _make_roots(roots_with_children: int, leaf_roots: int) -> None:
    """Create non-leaf roots (each with one active child) and leaf roots."""
    for i in range(roots_with_children):
        root = Category.objects.create(name=f"Root {i}", slug=f"root-{i}")
        Category.objects.create(name=f"Child {i}", slug=f"child-{i}", parent=root)
    for i in range(leaf_roots):
        Category.objects.create(name=f"Leaf {i}", slug=f"leaf-{i}")


def _child_existence_queries(captured: list[dict[str, object]]) -> int:
    """Count SELECTs that probe ``categories`` for a parent's children."""
    count = 0
    for q in captured:
        sql = str(q["sql"])
        if "categories" not in sql:
            continue
        # ``get_children().exists()`` compiles to a LIMIT-1 SELECT on the
        # categories table filtered by parent_id; the annotated EXISTS
        # produces a single correlated subquery inside the root-list SELECT.
        if "SELECT 1" in sql and "LIMIT 1" in sql and "parent_id" in sql:
            count += 1
    return count


class TestHeaderChildExistenceQueryCount:
    """The header's child-existence probe is a constant, not per-root."""

    def test_query_count_constant_across_root_arity(self) -> None:
        _make_roots(roots_with_children=5, leaf_roots=2)

        with CaptureQueriesContext(connection) as ctx:
            response = Client().get(reverse("ads:listings"))

        assert response.status_code == 200
        assert _child_existence_queries(ctx.captured_queries) <= _CHILD_EXISTENCE_BOUND

    def test_query_count_does_not_scale_with_roots(self) -> None:
        """Doubling the non-leaf roots must not add child-existence queries."""
        _make_roots(roots_with_children=3, leaf_roots=1)
        with CaptureQueriesContext(connection) as small_ctx:
            Client().get(reverse("ads:listings"))
        small = _child_existence_queries(small_ctx.captured_queries)

        Category.objects.all().delete()
        _make_roots(roots_with_children=8, leaf_roots=1)
        with CaptureQueriesContext(connection) as large_ctx:
            Client().get(reverse("ads:listings"))
        large = _child_existence_queries(large_ctx.captured_queries)

        assert large <= small
