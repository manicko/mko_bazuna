"""
View-layer tests for the catalog filter and sort behavior (Plan 26).

Covers the new buyer-facing filter dimensions and sort improvements:
- ``listing_purpose`` single-select filter (F4) in both ``/`` (listings) and ``/search/``
- ``features`` multi-select AND filter (F5)
- Combining ``q`` + ``listing_purpose`` + ``features`` via AND
- ``NULLS LAST`` for ``price_asc`` / ``price_desc`` on ``price_normalized_eur``
- Relevance tiebreaker (``-rank, -published_at, -id``) for FTS results

These use the real Django test client so the full filter → sort → paginate →
render pipeline is exercised (including the filter-form template).
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from django.test import Client
from django.utils import timezone


from apps.ads.models import Ad
from apps.core.enums import AdSort, AdStatus
from apps.lookups.models import LookupGroup, LookupItem

from conftest import create_test_ad, create_test_ads_bulk

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def purpose_lookup() -> dict[str, LookupItem]:
    """Create the ``listing_purpose`` group with sell/rent items."""
    group = LookupGroup.objects.create(code="listing_purpose", is_system=True)
    sell = LookupItem.objects.create(
        group=group,
        slug="sell",
        name_i18n={"ru": "Продажа", "en": "Sell"},
        is_active=True,
    )
    rent = LookupItem.objects.create(
        group=group,
        slug="rent",
        name_i18n={"ru": "Аренда", "en": "Rent"},
        is_active=True,
    )
    return {"sell": sell, "rent": rent}


@pytest.fixture
def feature_lookup() -> dict[str, LookupItem]:
    """Create the ``listing_feature`` group with genuine multi-select features.

    ``new``/``used`` are intentionally absent: they live in the
    ``listing_condition`` group (see ``condition_lookup``) and are excluded
    from the feature multi-select (Spec 12 / REQ-12.3).
    """
    group = LookupGroup.objects.create(code="listing_feature", is_system=True)
    delivery = LookupItem.objects.create(
        group=group,
        slug="delivery",
        name_i18n={"ru": "Доставка", "en": "Delivery"},
        is_active=True,
    )
    negotiable = LookupItem.objects.create(
        group=group,
        slug="negotiable",
        name_i18n={"ru": "Торг уместен", "en": "Negotiable"},
        is_active=True,
    )
    return {"delivery": delivery, "negotiable": negotiable}


@pytest.fixture
def condition_lookup() -> dict[str, LookupItem]:
    """Create the ``listing_condition`` group with new/used items."""
    group = LookupGroup.objects.create(code="listing_condition", is_system=True)
    new = LookupItem.objects.create(
        group=group,
        slug="new",
        name_i18n={"ru": "Новый", "en": "New"},
        is_active=True,
    )
    used = LookupItem.objects.create(
        group=group,
        slug="used",
        name_i18n={"ru": "Б/У", "en": "Used"},
        is_active=True,
    )
    return {"new": new, "used": used}


class TestListingPurposeFilter:
    """``?listing_purpose=<slug>`` narrows both listings and search (F4)."""

    def test_listings_filters_by_purpose(
        self, seller, category, city, purpose_lookup
    ) -> None:
        ad_sell = create_test_ad(
            seller,
            category,
            city,
            title="For sale",
            listing_purpose=purpose_lookup["sell"],
            status=AdStatus.PUBLISHED,
        )
        ad_rent = create_test_ad(
            seller,
            category,
            city,
            title="For rent",
            listing_purpose=purpose_lookup["rent"],
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/?listing_purpose=sell")

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        assert ad_sell.id in ids
        assert ad_rent.id not in ids

    def test_search_filters_by_purpose(
        self, seller, category, city, purpose_lookup
    ) -> None:
        ad_sell = create_test_ad(
            seller,
            category,
            city,
            title="For sale",
            listing_purpose=purpose_lookup["sell"],
            status=AdStatus.PUBLISHED,
        )
        ad_rent = create_test_ad(
            seller,
            category,
            city,
            title="For rent",
            listing_purpose=purpose_lookup["rent"],
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/search/?listing_purpose=sell")

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        assert ad_sell.id in ids
        assert ad_rent.id not in ids


class TestListingConditionFilter:
    """``?condition=<slug>`` single-select exact match for the new/used dimension.

    Mirrors ``TestListingPurposeFilter``: condition is a dedicated single-select
    dimension (Spec 12 / PO-4), never part of the ``features`` multi-select.
    """

    def test_listings_filters_by_condition(
        self, seller, category, city, condition_lookup
    ) -> None:
        ad_new = create_test_ad(
            seller,
            category,
            city,
            title="Brand new",
            listing_condition=condition_lookup["new"],
            status=AdStatus.PUBLISHED,
        )
        ad_used = create_test_ad(
            seller,
            category,
            city,
            title="Used good",
            listing_condition=condition_lookup["used"],
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/?condition=new")

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        assert ad_new.id in ids
        assert ad_used.id not in ids

    def test_search_filters_by_condition(
        self, seller, category, city, condition_lookup
    ) -> None:
        ad_new = create_test_ad(
            seller,
            category,
            city,
            title="Brand new",
            listing_condition=condition_lookup["new"],
            status=AdStatus.PUBLISHED,
        )
        ad_used = create_test_ad(
            seller,
            category,
            city,
            title="Used good",
            listing_condition=condition_lookup["used"],
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/search/?condition=used")

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        assert ad_used.id in ids
        assert ad_new.id not in ids

    def test_condition_filter_excludes_ads_without_condition(
        self, seller, category, city, condition_lookup
    ) -> None:
        ad_new = create_test_ad(
            seller,
            category,
            city,
            title="Brand new",
            listing_condition=condition_lookup["new"],
            status=AdStatus.PUBLISHED,
        )
        ad_unconditioned = create_test_ad(
            seller,
            category,
            city,
            title="No condition set",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/?condition=new")

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        assert ad_new.id in ids
        assert ad_unconditioned.id not in ids

    def test_condition_filter_empty_shows_all(
        self, seller, category, city, condition_lookup
    ) -> None:
        ad_new = create_test_ad(
            seller,
            category,
            city,
            title="Brand new",
            listing_condition=condition_lookup["new"],
            status=AdStatus.PUBLISHED,
        )
        ad_used = create_test_ad(
            seller,
            category,
            city,
            title="Used good",
            listing_condition=condition_lookup["used"],
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/")

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        assert ad_new.id in ids
        assert ad_used.id in ids


class TestFeaturesFilter:
    """``?features=...`` multi-select AND semantics (F5)."""

    def _seed_ads(self, seller, category, city, feature_lookup) -> tuple[Ad, Ad, Ad]:
        ad_both = create_test_ad(
            seller,
            category,
            city,
            title="Ad with both features",
            status=AdStatus.PUBLISHED,
        )
        ad_both.features.add(feature_lookup["delivery"], feature_lookup["negotiable"])
        ad_delivery_only = create_test_ad(
            seller,
            category,
            city,
            title="Ad with only delivery",
            status=AdStatus.PUBLISHED,
        )
        ad_delivery_only.features.add(feature_lookup["delivery"])
        ad_none = create_test_ad(
            seller,
            category,
            city,
            title="Ad with no features",
            status=AdStatus.PUBLISHED,
        )
        return ad_both, ad_delivery_only, ad_none

    def test_all_selected_features_required(
        self, seller, category, city, feature_lookup
    ) -> None:
        ad_both, ad_delivery_only, ad_none = self._seed_ads(
            seller, category, city, feature_lookup
        )

        client = Client()
        response = client.get("/search/?features=delivery&features=negotiable")

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        # AND semantics: an ad matches only if it has ALL selected features,
        # so ad_both (delivery + negotiable) is included while the single-feature
        # and featureless ads are excluded.
        assert ad_both.id in ids
        assert ad_delivery_only.id not in ids
        assert ad_none.id not in ids

    def test_ads_missing_any_selected_feature_excluded(
        self, seller, category, city, feature_lookup
    ) -> None:
        ad_both, ad_delivery_only, ad_none = self._seed_ads(
            seller, category, city, feature_lookup
        )

        client = Client()
        response = client.get("/search/?features=delivery&features=negotiable")

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        assert ad_delivery_only.id not in ids
        assert ad_none.id not in ids

    def test_single_feature_filter_matches_all_with_that_feature(
        self, seller, category, city, feature_lookup
    ) -> None:
        ad_both, ad_delivery_only, ad_none = self._seed_ads(
            seller, category, city, feature_lookup
        )

        client = Client()
        response = client.get("/search/?features=delivery")

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        assert ad_both.id in ids
        assert ad_delivery_only.id in ids
        assert ad_none.id not in ids


class TestFilterAndSearchCombine:
    """``q`` + ``listing_purpose`` + ``features`` combine via AND."""

    def test_q_purpose_and_feature_combine(
        self, seller, category, city, purpose_lookup, feature_lookup
    ) -> None:
        ad_match = create_test_ad(
            seller,
            category,
            city,
            title="Продам красный телефон",
            listing_purpose=purpose_lookup["sell"],
            status=AdStatus.PUBLISHED,
        )
        ad_match.features.add(feature_lookup["delivery"])
        # Same text + purpose but missing the feature -> must be excluded.
        create_test_ad(
            seller,
            category,
            city,
            title="Продам красный телефон",
            listing_purpose=purpose_lookup["sell"],
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get(
            "/search/?q=красный телефон&listing_purpose=sell&features=delivery"
        )

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        assert ad_match.id in ids
        assert len(ids) == 1


class TestPriceNullSort:
    """``price_asc``/``price_desc`` place NULL ``price_normalized_eur`` last."""

    def test_price_asc_places_nulls_last(
        self, seller, category, city
    ) -> None:
        priced = create_test_ad(
            seller, category, city, title="Priced", price=100,
            status=AdStatus.PUBLISHED,
        )
        null = create_test_ad(
            seller, category, city, title="No price", price=None,
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get(f"/?sort={AdSort.PRICE_LOW}")

        assert response.status_code == 200
        ids = list(a.id for a in response.context["page_obj"])
        assert null.id in ids and priced.id in ids
        assert ids[-1] == null.id

    def test_price_desc_places_nulls_last(
        self, seller, category, city
    ) -> None:
        priced = create_test_ad(
            seller, category, city, title="Priced", price=100,
            status=AdStatus.PUBLISHED,
        )
        null = create_test_ad(
            seller, category, city, title="No price", price=None,
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get(f"/?sort={AdSort.PRICE_HIGH}")

        assert response.status_code == 200
        ids = list(a.id for a in response.context["page_obj"])
        assert null.id in ids and priced.id in ids
        assert ids[-1] == null.id


class TestRelevanceTiebreaker:
    """FTS results order by ``-rank, -published_at, -id``."""

    def test_rank_tie_breaks_by_published_at(
        self, seller, category, city
    ) -> None:
        now = timezone.now()
        ad_older = create_test_ad(
            seller,
            category,
            city,
            title="Продам красный телефон",
            status=AdStatus.PUBLISHED,
            published_at=now - timedelta(days=1),
        )
        ad_newer = create_test_ad(
            seller,
            category,
            city,
            title="Продам красный телефон",
            status=AdStatus.PUBLISHED,
            published_at=now,
        )

        client = Client()
        response = client.get("/search/?q=красный телефон")

        assert response.status_code == 200
        ids = list(a.id for a in response.context["page_obj"])
        assert ad_newer.id in ids and ad_older.id in ids
        assert ids.index(ad_newer.id) < ids.index(ad_older.id)


class TestFilterUrlReset:
    """Verify that filter URL state is reset/replaced, not accumulated (Plan 29).

    Covers spec §5 acceptance criteria:
    - AC-1: form submission produces URL with only active filters (no accumulation)
    - AC-2: chip removal updates browser URL
    - AC-3: "Clear all filters" updates URL
    - AC-4: pagination links update URL
    """

    # ------------------------------------------------------------------ #
    # Static template-source assertions (no DB needed)
    # ------------------------------------------------------------------ #

    def test_form_uses_request_path_not_empty(self) -> None:
        """``filter_form.html`` must use ``hx-get="{{ request.path }}"``, not ``hx-get=""``."""
        path = Path("src/backend/templates/ads/partials/filter_form.html").resolve()
        content = path.read_text(encoding="utf-8")
        assert 'hx-get="{{ request.path }}' in content
        assert 'hx-get=""' not in content

    def test_all_htmx_links_have_push_url(self) -> None:
        """Every ``hx-get`` link in ``ad_list.html`` must also carry ``hx-push-url="true"``."""
        path = Path("src/backend/templates/ads/partials/ad_list.html").resolve()
        content = path.read_text(encoding="utf-8")
        assert content.count("hx-get=") == 9
        assert content.count('hx-push-url="true"') == 9

    def test_clear_all_filters_has_push_url(self) -> None:
        """The "Clear all filters" link has ``hx-push-url="true"`` and path ``?page=1``."""
        path = Path("src/backend/templates/ads/partials/ad_list.html").resolve()
        content = path.read_text(encoding="utf-8")
        assert 'hx-push-url="true"' in content
        assert 'hx-get="?page=1' in content

    # ------------------------------------------------------------------ #
    # Integration tests — HTMX rendered output
    # ------------------------------------------------------------------ #

    def test_form_renders_path_only_hx_get(
        self, seller, category, city
    ) -> None:
        """HTMX request to ``/`` renders the form with ``hx-get="/"`` (path only)."""
        create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        response = client.get(
            "/?features=delivery",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'hx-get="/"' in content
        assert 'hx-get="/?features=delivery' not in content

    def test_chip_link_has_push_url_in_rendered_output(
        self, seller, category, city, feature_lookup
    ) -> None:
        """Feature chip removal links in the rendered output carry ``hx-push-url="true"``."""
        ad = create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED
        )
        ad.features.add(feature_lookup["delivery"])
        client = Client()
        response = client.get(
            "/?features=delivery",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'hx-push-url="true"' in content

    def test_pagination_links_have_push_url_in_rendered_output(
        self, seller, category, city
    ) -> None:
        """Pagination links in the rendered output carry ``hx-push-url="true"``."""
        create_test_ads_bulk(
            seller, category, city, count=25,
            status=AdStatus.PUBLISHED,
        )
        client = Client()
        # Use Accept-Language en so the middleware activates English, making
        # the ``{% trans "Page navigation" %}`` assertion deterministic.
        response = client.get("/", headers={"HX-Request": "true", "Accept-Language": "en"})
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'hx-push-url="true"' in content
        assert "Page navigation" in content

    # ------------------------------------------------------------------ #
    # Behavioral test — no parameter accumulation
    # ------------------------------------------------------------------ #

    def test_form_submission_does_not_accumulate_params(
        self, seller, category, city, feature_lookup
    ) -> None:
        """Requesting only ``features=delivery`` returns only delivery ads.

        An ad with only the ``new`` feature is excluded, proving unchecked params
        from a prior URL are not re-introduced. (Single-select behaviour is
        identical under AND/OR — only multi-select semantics changed.)
        """
        ad_delivery = create_test_ad(
            seller, category, city,
            title="Delivery only",
            status=AdStatus.PUBLISHED,
        )
        ad_delivery.features.add(feature_lookup["delivery"])

        ad_negotiable = create_test_ad(
            seller, category, city,
            title="Negotiable only",
            status=AdStatus.PUBLISHED,
        )
        ad_negotiable.features.add(feature_lookup["negotiable"])

        client = Client()
        response = client.get("/?features=delivery")
        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        assert ad_delivery.id in ids
        assert ad_negotiable.id not in ids
