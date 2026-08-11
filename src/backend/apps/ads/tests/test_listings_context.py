"""
Verification test for the ``listings()`` filter context (vrf_002 / tsk_002).

Confirms that ``apps.ads.views.listings.listings()`` populates every tsk_002
filter-context key on its render context:

* ``current_category`` / ``current_city``
* ``current_sort``
* ``min_price`` / ``max_price``
* ``suggested_category`` / ``suggested_city``
* ``consent_shown``

No live database is required. The ORM lookups (``Ad``, ``Category``, ``City``)
are replaced with mocks and ``django.shortcuts.render`` is stubbed so the
context dict can be inspected without template rendering. The ad queryset is a
minimal, Paginator-compatible empty stub, so ``django.core.paginator.Paginator``
computes ``count=0`` entirely in memory (no PostgreSQL connection).
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse, HttpRequest
from django.test import RequestFactory, SimpleTestCase

from apps.ads.views.listings import listings as listings_view
from apps.core.enums import AdSort, AdStatus

# Canonical filter query from the vrf_002 spec.
_SPEC_QUERY = "category=electronics&city=kyiv&min_price=100&max_price=500&sort=price_asc"


class _EmptyQuerySet(list):
    """A Paginator-compatible, DB-free stand-in for an empty ad queryset.

    ``listings()`` chains ``filter`` / ``select_related`` / ``prefetch_related``
    / ``order_by`` and finally hands the result to
    ``django.core.paginator.Paginator``. This stub mimics that chainable
    interface on an empty list: every mutating call returns ``self``. Because
    it subclasses ``list``, Paginator's count resolution finds ``list.count`` to
    be a builtin and falls back to ``len()`` (0), building an empty first page
    without touching the database.
    """

    def filter(self, *args: object, **kwargs: object) -> _EmptyQuerySet:
        return self

    def select_related(self, *args: object, **kwargs: object) -> _EmptyQuerySet:
        return self

    def prefetch_related(self, *args: object, **kwargs: object) -> _EmptyQuerySet:
        return self

    def order_by(self, *args: object, **kwargs: object) -> _EmptyQuerySet:
        return self


class TestListingsFilterContext(SimpleTestCase):
    """vrf_002 — the tsk_002 filter context flows through ``listings()``."""

    def _run_listings(
        self,
        query_string: str,
        *,
        category_slug: str | None = None,
        city_slug: str | None = None,
    ) -> tuple[HttpResponse, dict[str, object]]:
        """Invoke ``listings()`` with all DB-touching dependencies mocked.

        ``Ad``, ``Category`` and ``City`` managers and ``render`` are patched in
        the view module. The mocked ``Ad`` queryset is an :class:`_EmptyQuerySet`
        and the taxonomy lookups return empty suggestion pools, so nothing in the
        view opens a database connection. ``render`` is stubbed to capture the
        context dict that would otherwise be passed to the template.
        """
        context_box: list[dict[str, object]] = []

        def fake_render(
            request: HttpRequest,
            template_name: str,
            context: dict[str, object] | None = None,
            **kwargs: object,
        ) -> HttpResponse:
            context_box.append(context if context is not None else {})
            return HttpResponse(status=200)

        with (
            patch("apps.ads.views.listings.Ad") as mock_ad,
            patch("apps.ads.views.listings.Category") as mock_category,
            patch("apps.ads.views.listings.City") as mock_city,
            patch("apps.ads.views.listings.render", side_effect=fake_render),
        ):
            mock_ad.objects.filter.return_value = _EmptyQuerySet()
            mock_category.objects.filter.return_value.values_list.return_value = []
            mock_city.objects.values_list.return_value = []

            factory = RequestFactory()
            url = f"/?{query_string}" if query_string else "/"
            request = factory.get(url)
            # Anonymous browser => is_consent_given(request) returns True.
            request.user = AnonymousUser()

            response = listings_view(
                request,
                category_slug=category_slug,
                city_slug=city_slug,
            )

        return response, context_box[0]

    # ── tsk_002 context keys (vrf_002) ──────────────────────────────────────

    def test_context_contains_all_tsk002_keys(self) -> None:
        """Every tsk_002 filter key is present in the render context."""
        _, context = self._run_listings(_SPEC_QUERY)

        expected_keys = {
            "current_category",
            "current_city",
            "current_sort",
            "min_price",
            "max_price",
            "suggested_category",
            "suggested_city",
            "consent_shown",
        }
        assert expected_keys <= set(context)

    def test_query_params_map_to_context_values(self) -> None:
        """GET filter params propagate to the matching context values.

        ``current_category`` / ``current_city`` mirror the URL *path* slugs
        (absent here, so ``None``); the ``category`` / ``city`` GET params only
        drive did-you-mean suggestions, which resolve to ``None`` against the
        empty mocked taxonomy.
        """
        _, context = self._run_listings(_SPEC_QUERY)

        assert context["current_category"] is None
        assert context["current_city"] is None
        assert context["current_sort"] == AdSort.PRICE_LOW
        assert context["min_price"] == "100"
        assert context["max_price"] == "500"
        assert context["suggested_category"] is None
        assert context["suggested_city"] is None

    def test_consent_shown_is_true_for_anonymous_browse(self) -> None:
        """Anonymous browsers get ``consent_shown=True`` (no consent banner)."""
        _, context = self._run_listings(_SPEC_QUERY)
        assert context["consent_shown"] is True

    def test_empty_queryset_marks_no_results_with_page_obj(self) -> None:
        """With no ads in the mocked queryset, ``has_results`` is False."""
        response, context = self._run_listings(_SPEC_QUERY)

        assert response.status_code == 200
        assert context["has_results"] is False
        assert "page_obj" in context

    def test_path_slugs_populate_current_category_and_city(self) -> None:
        """URL path slugs appear verbatim in ``current_category`` / ``current_city``.

        When the slugs resolve, the did-you-mean suggestions stay ``None`` and
        the default sort (``date_desc``) is applied.
        """
        response, context = self._run_listings(
            "",
            category_slug="electronics",
            city_slug="kyiv",
        )

        assert response.status_code == 200
        assert context["current_category"] == "electronics"
        assert context["current_city"] == "kyiv"
        assert context["current_sort"] == AdSort.DATE_NEW
        assert context["min_price"] is None
        assert context["max_price"] is None
        assert context["suggested_category"] is None
        assert context["suggested_city"] is None
        assert context["consent_shown"] is True
        assert context["has_results"] is False

    def test_view_hits_mocked_orm_and_renders_list_template(self) -> None:
        """``listings()`` queries the mocked ``Ad`` manager and renders list.html.

        Proves the test stays DB-free: the only ``Ad.objects.filter`` call is the
        initial ``status=PUBLISHED`` filter (subsequent chain calls run on the
        in-memory empty queryset), and the non-HTMX branch renders the listings
        template.
        """
        request = RequestFactory().get("/?category=electronics&city=kyiv")
        request.user = AnonymousUser()
        captured: dict[str, object] = {}

        def fake_render(
            request: HttpRequest,
            template_name: str,
            context: dict[str, object] | None = None,
            **kwargs: object,
        ) -> HttpResponse:
            captured["template_name"] = template_name
            captured["context"] = context if context is not None else {}
            return HttpResponse(status=200)

        with (
            patch("apps.ads.views.listings.Ad") as mock_ad,
            patch("apps.ads.views.listings.Category") as mock_category,
            patch("apps.ads.views.listings.City") as mock_city,
            patch("apps.ads.views.listings.render", side_effect=fake_render),
        ):
            mock_ad.objects.filter.return_value = _EmptyQuerySet()
            mock_category.objects.filter.return_value.values_list.return_value = []
            mock_city.objects.values_list.return_value = []

            response = listings_view(request)

        assert response.status_code == 200
        mock_ad.objects.filter.assert_called_once_with(status=AdStatus.PUBLISHED)
        assert captured["template_name"] == "ads/list.html"
        assert captured["context"] is not None
