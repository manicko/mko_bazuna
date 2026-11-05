"""Service-tier ports of the retiring listings API matrix (block B3).

This module is the retained home of the business invariants that were asserted
only through the dying ``GET /api/v1/ads/`` JSON mirror
(``test_listings_api.py::TestExhaustiveFilterSortPageMatrix`` and
``::TestAudienceParity``). Every test drives
``ListingsQuery.build_queryset`` directly — the single pipeline the retained
HTML ``listings()`` and ``search()`` views share — and asserts on queryset id
sets, never on a JSON envelope.

Covers:
- category filter resolves the subtree (parent + child + grandchild ads match,
  a sibling-root control ad does not); an unknown slug applies no filter;
- EUR-normalized price bounds are inclusive at the bound
  (``min_price`` / ``max_price`` / combined);
- a PUBLISHED ad whose seller carries ONLY ``consent_revoked_at`` (or ONLY
  ``is_deleted``) is excluded by the shared account-state predicate;
- for every sort the union of pages 1-3 at ``per_page=10`` equals the full
  25-ad set exactly once.

D28 fix: unlike the retiring test, the page-union test carries NO outer
``@pytest.mark.parametrize("page", ...)`` — the unused parametrization made the
three-page loop re-run once per page value. Here it is one collected test per
sort, each looping pages 1-3 exactly once (4 collected rows).
"""

from __future__ import annotations

from typing import Any

import pytest
from django.core.paginator import Paginator
from django.utils import timezone

from apps.ads.models import Ad
from apps.ads.services.listings_query import ListingsQuery, ListingsQueryParams
from apps.categories.models import Category
from apps.core.enums import AdSort, AdStatus
from apps.locations.models import City
from conftest import create_test_ad, create_test_ads_bulk

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestListingsQueryCategoryFilter:
    """The category filter resolves the subtree; unknown slugs apply no filter."""

    def test_category_filter_includes_descendant_subtree(
        self, seller, category, city
    ) -> None:
        """Parent, child and grandchild ads all match; a sibling root does not."""
        child = Category.objects.create(
            name="Child", slug="listings-child-leaf", parent=category
        )
        grandchild = Category.objects.create(
            name="Grandchild", slug="listings-grandchild-leaf", parent=child
        )
        control_root = Category.objects.create(
            name="Control Root", slug="listings-control-root"
        )
        mine = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        in_child = create_test_ad(seller, child, city, status=AdStatus.PUBLISHED)
        in_grandchild = create_test_ad(
            seller, grandchild, city, status=AdStatus.PUBLISHED
        )
        outside = create_test_ad(seller, control_root, city, status=AdStatus.PUBLISHED)

        ads = ListingsQuery.build_queryset(
            ListingsQueryParams(category_slug=category.slug)
        )

        # Exact set: the subtree matches and nothing outside it leaks in.
        assert set(ads.values_list("id", flat=True)) == {
            mine.id,
            in_child.id,
            in_grandchild.id,
        }
        assert outside.id not in set(ads.values_list("id", flat=True))

    def test_unknown_category_slug_applies_no_filter(
        self, seller, category, city
    ) -> None:
        """An unresolvable slug (retiring shape ``does-not-exist``) filters nothing."""
        seeded = {
            create_test_ad(seller, category, city, status=AdStatus.PUBLISHED).id
            for _ in range(2)
        }

        ads = ListingsQuery.build_queryset(
            ListingsQueryParams(category_slug="does-not-exist")
        )

        assert seeded <= set(ads.values_list("id", flat=True))


class TestListingsQueryPriceBounds:
    """Price bounds filter on the EUR-normalized price, inclusive at the bound."""

    @pytest.fixture
    def price_matrix(self, seller, category, city) -> dict[str, Ad]:
        """Seed the retiring matrix shape: 50 / 150 / 300 in city, 150 elsewhere."""
        other_city = City.objects.create(
            country_code="ME",
            name="Другиград",
            region="Central",
            slug="drugigrad",
        )
        cheap = create_test_ad(
            seller, category, city, title="Cheap", price=50, status=AdStatus.PUBLISHED
        )
        mid = create_test_ad(
            seller, category, city, title="Mid", price=150, status=AdStatus.PUBLISHED
        )
        expensive = create_test_ad(
            seller,
            category,
            city,
            title="Expensive",
            price=300,
            status=AdStatus.PUBLISHED,
        )
        elsewhere = create_test_ad(
            seller,
            category,
            other_city,
            title="Elsewhere",
            price=150,
            status=AdStatus.PUBLISHED,
        )
        return {
            "cheap": cheap,
            "mid": mid,
            "expensive": expensive,
            "elsewhere": elsewhere,
        }

    def _ids(self, **params: Any) -> set[int]:
        """Return the id set of the queryset built from *params*."""
        qs = ListingsQuery.build_queryset(ListingsQueryParams(**params))
        return set(qs.values_list("id", flat=True))

    def test_min_price_bound(self, price_matrix: dict[str, Ad]) -> None:
        """min_price=150 includes the 150-eur ads and excludes the 50-eur one."""
        ids = self._ids(min_price=150)

        assert ids == {price_matrix[k].id for k in ("mid", "expensive", "elsewhere")}
        assert price_matrix["cheap"].id not in ids

    def test_max_price_bound(self, price_matrix: dict[str, Ad]) -> None:
        """max_price=150 excludes the 300-eur ad (inclusive at the bound)."""
        ids = self._ids(max_price=150)

        assert ids == {price_matrix[k].id for k in ("cheap", "mid", "elsewhere")}
        assert price_matrix["expensive"].id not in ids

    def test_min_price_and_max_price_bounds_combined(
        self, price_matrix: dict[str, Ad]
    ) -> None:
        """min_price=100 + max_price=200 leaves only the two 150-eur ads."""
        ids = self._ids(min_price=100, max_price=200)

        assert ids == {price_matrix[k].id for k in ("mid", "elsewhere")}


class TestListingsQuerySellerAudienceStates:
    """The shared account-state predicate hides a blocked seller's inventory.

    The two states below are synthetic: the real withdrawal flow soft-deletes
    the user and nulls ``telegram_id``, so a PUBLISHED ad whose seller carries
    ONLY ``consent_revoked_at`` (or ONLY ``is_deleted``) never occurs in
    production. They still pin the individual conjuncts of
    ``account_state_q("user__")`` inside the listings queryset: each
    ``is_visible`` sanity check proves the flip — not some unrelated cause —
    is what hides the ad, and restoring the flag re-shows it.
    """

    def _visible(self, ad: Ad) -> bool:
        """Whether *ad* is in the shared listings queryset."""
        return (
            ListingsQuery.build_queryset(ListingsQueryParams())
            .filter(pk=ad.pk)
            .exists()
        )

    def test_withdrawn_consent_seller_ad_is_hidden(
        self, seller, category, city
    ) -> None:
        """A seller with only ``consent_revoked_at`` set loses listing visibility."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        assert self._visible(ad)  # sanity: visible before the flip

        seller.consent_revoked_at = timezone.now()
        seller.save(update_fields=["consent_revoked_at"])
        assert not self._visible(ad)

        # Isolated conjunct: restoring the flag re-shows the same ad.
        seller.consent_revoked_at = None
        seller.save(update_fields=["consent_revoked_at"])
        assert self._visible(ad)

    def test_deleted_seller_ad_is_hidden(self, seller, category, city) -> None:
        """A seller with only ``is_deleted=True`` set loses listing visibility."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        assert self._visible(ad)  # sanity: visible before the flip

        seller.is_deleted = True
        seller.save(update_fields=["is_deleted"])
        assert not self._visible(ad)

        seller.is_deleted = False
        seller.save(update_fields=["is_deleted"])
        assert self._visible(ad)


class TestListingsQueryPageUnion:
    """Pages 1-3 partition the full result set for every sort (no loss/dup)."""

    @pytest.mark.parametrize(
        "sort",
        [AdSort.DATE_NEW, AdSort.DATE_OLD, AdSort.PRICE_LOW, AdSort.PRICE_HIGH],
    )
    # D28 fix: the retiring test ALSO had an unused outer
    # @pytest.mark.parametrize("page", [1, 2, 3]). It is deliberately NOT
    # carried over: one collected test per sort, each looping pages 1-3 once.
    def test_three_page_union_no_duplicates_per_sort(
        self, seller, category, city, sort: AdSort
    ) -> None:
        """The union of three 10-per-page slices equals the 25-id set exactly."""
        ads = create_test_ads_bulk(
            seller, category, city, 25, status=AdStatus.PUBLISHED
        )
        all_ids = {a.id for a in ads}

        # Same pagination construction the retained view uses.
        qs = ListingsQuery.build_queryset(ListingsQueryParams(sort=sort))
        paginator = Paginator(qs, 10)
        assert paginator.count == 25

        seen: list[int] = []
        for page_number in (1, 2, 3):
            page = paginator.get_page(page_number)
            # 25 ads at 10/page -> pages hold 10, 10, 5.
            assert len(page.object_list) == (5 if page_number == 3 else 10)
            seen.extend(ad.id for ad in page.object_list)

        assert len(seen) == len(set(seen)) == 25
        assert set(seen) == all_ids
