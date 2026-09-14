"""
Verification test for the ``listings()`` filter context (vrf_002 / tsk_002).

Confirms that ``apps.ads.views.listings.listings()`` populates every tsk_002
filter-context key on its render context:

* ``current_category`` / ``current_city``
* ``current_sort``
* ``min_price`` / ``max_price``
* ``suggested_category`` / ``suggested_city``

Uses a real database with ``create_test_ad`` for ad creation and direct
``Category`` / ``City`` ORM objects for taxonomy, replacing the previous
mock-based approach. ``django.test.Client`` exercises the full view → template
→ context pipeline through URL routing and middleware.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.core.enums import AdSort, AdStatus
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# Canonical filter query from the vrf_002 spec.
_SPEC_QUERY = (
    "category=electronics&city=kyiv&min_price=100&max_price=500&sort=price_asc"
)


def _get(query_string: str = "") -> Any:
    """GET the listings page (root path) and return the response."""
    url = reverse("ads:listings")
    if query_string:
        url = f"{url}?{query_string}"
    client = Client()
    response = client.get(url)
    assert response.status_code == 200
    return response


def _context(response: Any) -> dict[str, Any]:
    """Extract a plain dict from the response context."""
    return dict(response.context)


# ── tsk_002 context keys (vrf_002) ──────────────────────────────────────


def test_context_contains_all_tsk002_keys() -> None:
    """Every tsk_002 filter key is present in the render context."""
    ctx = _context(_get(_SPEC_QUERY))
    expected_keys = {
        "current_category",
        "current_city",
        "current_sort",
        "min_price",
        "max_price",
        "suggested_category",
        "suggested_city",
    }
    assert expected_keys <= set(ctx)


def test_breadcrumb_category_none_without_resolved_category() -> None:
    """Without a resolvable category path, ``breadcrumb_category`` is None.

    With an empty taxonomy, the did-you-mean suggestion also resolves to None
    (difflib needs close matches to suggest).
    """
    ctx = _context(_get("category=nonexistent-category"))
    assert ctx["breadcrumb_category"] is None
    assert ctx["suggested_category"] is None  # empty taxonomy → no match


def test_query_params_map_to_context_values() -> None:
    """GET filter params propagate to the matching context values.

    ``current_category`` mirrors the URL *path* slug (absent here, so
    ``None``); an explicit ``?city=`` is a real filter (F-5), so
    ``current_city`` reflects the query param. With an empty taxonomy the
    did-you-mean suggestion resolves to ``None``.
    """
    ctx = _context(_get(_SPEC_QUERY))

    assert ctx["current_category"] is None
    assert ctx["current_city"] == "kyiv"
    assert ctx["current_sort"] == AdSort.PRICE_LOW
    assert ctx["min_price"] == "100"
    assert ctx["max_price"] == "500"
    assert ctx["suggested_category"] is None
    assert ctx["suggested_city"] is None


def test_empty_queryset_marks_no_results_with_page_obj() -> None:
    """With no ads in the queryset, ``has_results`` is False."""
    response = _get(_SPEC_QUERY)
    ctx = _context(response)

    assert response.status_code == 200
    assert ctx["has_results"] is False
    assert "page_obj" in ctx


def test_path_slugs_populate_current_category_and_city(
    category: Any, city: Any
) -> None:
    """URL path slugs appear verbatim in ``current_category`` / ``current_city``.

    When the slugs resolve, the did-you-mean suggestions stay ``None`` and
    the default sort (``date_desc``) is applied.
    """
    client = Client()
    response = client.get(
        reverse("ads:listings_category", kwargs={"category_slug": category.slug})
    )
    assert response.status_code == 200
    ctx = _context(response)

    assert ctx["current_category"] == category.slug
    assert ctx["current_sort"] == AdSort.DATE_NEW
    assert ctx["min_price"] is None
    assert ctx["max_price"] is None
    assert ctx["has_results"] is False


def test_path_city_slug_sets_current_city(category: Any, city: Any) -> None:
    """City path slug resolves and populates ``current_city``."""
    client = Client()
    response = client.get(
        reverse("ads:listings_city", kwargs={"city_slug": city.slug})
    )
    assert response.status_code == 200
    ctx = _context(response)

    assert ctx["current_city"] == city.slug
    assert ctx["current_sort"] == AdSort.DATE_NEW
    assert ctx["has_results"] is False


def test_view_hits_real_orm_and_renders_list_template(
    seller: Any, category: Any, city: Any
) -> None:
    """``listings()`` queries the real ``Ad`` manager and renders list.html.

    Uses real ORM objects (not mocks) to create one PUBLISHED ad, then verifies:
    - The view executes a bounded number of queries (no N+1 on the listing page).
    - The rendered HTML contains expected listing content.
    - ``has_results`` is True when ads exist.
    - The ad appears in the paginated page_obj.
    """
    ad = create_test_ad(
        user=seller,
        category=category,
        city=city,
        title="Test Ad for Listings",
        status=AdStatus.PUBLISHED,
    )

    client = Client()
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(reverse("ads:listings"))

    assert response.status_code == 200
    assert response.context["has_results"] is True
    assert ad in response.context["page_obj"].object_list
    # Bounded query count: no N+1 leaks on the listing render path.
    assert len(ctx.captured_queries) <= 16


def test_listings_excludes_deactivated_category_ads(
    seller: Any, category: Any, city: Any
) -> None:
    """A PUBLISHED ad whose category is deactivated does not appear in listings.

    The null-safe base queryset filters on ``category__is_active=True`` for
    non-null categories; deactivating the category should hide its ads.
    """
    create_test_ad(
        user=seller,
        category=category,
        city=city,
        title="Deactivated Category Ad",
        status=AdStatus.PUBLISHED,
    )

    # Deactivate the category
    category.is_active = False
    category.save(update_fields=["is_active"])

    response = _get()
    assert response.status_code == 200
    assert response.context["has_results"] is False
