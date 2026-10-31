"""
Tests for the JSON category-tree endpoint (``GET /api/v1/categories/``).

Covers the S1.6 contract:

- tree shape: parents with nested ``children``, active-only filtering at every
  level, stable ``name`` ordering, per-locale ``name`` resolution;
- anonymous access (PUB read);
- HTML parity: the JSON tree matches what the header menu renders for the same
  fixtures (root slugs/order + nested active children), proven browserlessly;
- the RFC 9457 ``rate_limited`` 429 problem on budget exhaustion.
"""

from __future__ import annotations

import pytest
from django.test import Client

from apps.categories.models import Category
from apps.core.utils.problem import (
    PROBLEM_CONTENT_TYPE,
    RETRY_AFTER_HEADER,
    TYPE_RATE_LIMITED,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

ENDPOINT = "/api/v1/categories/"


@pytest.fixture
def catalog() -> None:
    """Create a two-root tree with active/inactive children and a grandchild.

    - ``transport`` (root): active children ``bicycles``, ``cars`` (with an
      active grandchild ``spare-parts``) and an inactive ``old``; ordering is by
      ``name`` (``Велосипеды`` < ``Автомобили`` in the base ``name`` column is
      locale-independent — we assert against the rendered order below).
    - ``realty`` (root): a leaf root.
    - ``hidden`` (root, inactive): must never appear.
    """
    transport = Category.objects.create(
        name="Transport", slug="transport", name_i18n={"ru": "Транспорт"}
    )
    Category.objects.create(
        name="Bicycles",
        slug="bicycles",
        parent=transport,
        name_i18n={"ru": "Велосипеды"},
    )
    cars = Category.objects.create(
        name="Cars", slug="cars", parent=transport, name_i18n={"ru": "Автомобили"}
    )
    Category.objects.create(
        name="Spare parts",
        slug="spare-parts",
        parent=cars,
        name_i18n={"ru": "Запчасти"},
    )
    Category.objects.create(
        name="Old",
        slug="old",
        parent=transport,
        is_active=False,
        name_i18n={"ru": "Устаревшее"},
    )
    Category.objects.create(
        name="Realty", slug="realty", name_i18n={"ru": "Недвижимость"}
    )
    Category.objects.create(
        name="Hidden",
        slug="hidden",
        is_active=False,
        name_i18n={"ru": "Скрытая"},
    )


def _slugs(nodes: list[dict]) -> list[str]:
    """Return the ``slug`` values of a node list (order-preserving)."""
    return [node["slug"] for node in nodes]


class TestCategoryTreeShape:
    """The JSON tree exposes the active-only, name-ordered nested structure."""

    def test_anonymous_access_allowed(self, catalog: None) -> None:
        response = Client().get(ENDPOINT)
        assert response.status_code == 200
        assert response.headers.get("Content-Type") == "application/json"

    def test_top_level_is_active_roots_ordered_by_name(self, catalog: None) -> None:
        payload = Client().get(ENDPOINT).json()
        # Active roots only, ordered by ``name`` (locale-independent base column):
        # "Realty" < "Transport"; the inactive "Hidden" root is dropped.
        assert _slugs(payload["categories"]) == ["realty", "transport"]

    def test_children_are_active_only(self, catalog: None) -> None:
        payload = Client().get(ENDPOINT).json()
        transport = next(
            node for node in payload["categories"] if node["slug"] == "transport"
        )
        # ``old`` is inactive and excluded; children ordered by ``name``:
        # "Bicycles" < "Cars".
        assert _slugs(transport["children"]) == ["bicycles", "cars"]

    def test_grandchildren_are_nested(self, catalog: None) -> None:
        payload = Client().get(ENDPOINT).json()
        transport = next(
            node for node in payload["categories"] if node["slug"] == "transport"
        )
        cars = next(
            node for node in transport["children"] if node["slug"] == "cars"
        )
        assert _slugs(cars["children"]) == ["spare-parts"]
        # A leaf carries an empty children list (never a missing key).
        bicycles = next(
            node for node in transport["children"] if node["slug"] == "bicycles"
        )
        assert bicycles["children"] == []

    def test_orphan_under_inactive_parent_is_omitted(self) -> None:
        """An active child under an inactive parent is never reachable."""
        parent = Category.objects.create(
            name="Parent", slug="parent", is_active=False
        )
        Category.objects.create(name="Child", slug="child", parent=parent)
        payload = Client().get(ENDPOINT).json()
        assert _slugs(payload["categories"]) == []

    def test_per_locale_name_resolution(self, catalog: None) -> None:
        """``?lang`` resolves the localized ``name_i18n`` value."""
        payload = Client().get(f"{ENDPOINT}?lang=ru").json()
        transport = next(
            node for node in payload["categories"] if node["slug"] == "transport"
        )
        assert transport["name"] == "Транспорт"

    def test_name_falls_back_to_base_when_locale_absent(self, catalog: None) -> None:
        """A locale missing from ``name_i18n`` falls back to ``ru`` then name."""
        payload = Client().get(f"{ENDPOINT}?lang=en").json()
        transport = next(
            node for node in payload["categories"] if node["slug"] == "transport"
        )
        # ``name_i18n`` has only ``ru``; ``en`` falls back to ``ru`` value.
        assert transport["name"] == "Транспорт"


class TestHtmlParity:
    """The JSON tree matches the header menu's rendered structure."""

    def test_json_tree_matches_header_root_categories(self, catalog: None) -> None:
        """JSON root slugs equal the header's ``root_categories`` order."""
        from django.test import RequestFactory

        from apps.core.context_processors import header_context

        request = RequestFactory().get("/")
        request.LANGUAGE_CODE = "ru"
        html_roots = header_context(request)["root_categories"]

        payload = Client().get(f"{ENDPOINT}?lang=ru").json()
        assert _slugs(payload["categories"]) == [cat.slug for cat in html_roots]

    def test_json_children_match_header_submenu_nodes(self, catalog: None) -> None:
        """For every root, JSON children equal the submenu's active children."""
        from django.test import RequestFactory

        from apps.categories.views import category_submenu

        payload = Client().get(f"{ENDPOINT}?lang=ru").json()
        json_children = {
            node["slug"]: _slugs(node["children"]) for node in payload["categories"]
        }

        factory = RequestFactory()
        for root in Category.objects.root_nodes().filter(is_active=True):
            request = factory.get(f"/categories/{root.slug}/submenu/?lang=ru")
            request.LANGUAGE_CODE = "ru"
            response = category_submenu(request, root.slug)
            content = response.content.decode("utf-8")
            expected = list(
                root.get_children()
                .filter(is_active=True)
                .order_by("name")
                .values_list("slug", flat=True)
            )
            # Every expected active child slug renders in the HTML fragment...
            for slug in expected:
                assert f'data-category-slug="{slug}"' in content
            # ...and the JSON children list matches it exactly, in order.
            assert json_children[root.slug] == expected


class TestRateLimitProblem:
    """Exhausting ``API_PUBLIC_READ`` yields an RFC 9457 429 problem."""

    def test_over_budget_returns_rate_limited_problem(
        self, catalog: None, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "apps.categories.api_tree.rate_limit_check",
            lambda *a, **k: False,
        )
        response = Client().get(ENDPOINT)

        assert response.status_code == 429
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.headers.get(RETRY_AFTER_HEADER) == "60"
        payload = response.json()
        assert payload["type"] == TYPE_RATE_LIMITED
        assert payload["status"] == 429
