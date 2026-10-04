"""
View-layer tests for the search view (TST-004).

Covers:
- Only PUBLISHED ads appear in results (no DRAFT/ON_MODERATION/etc.)
- Descendant category expansion for single-word queries matching a category
- Pagination (24 per page, page parameter)

Previously shadowed as ``apps/search/tests.py`` (the ``tests/`` package with
``__init__.py`` took the ``tests`` module name, so ``tests.py`` was silently
skipped during pytest collection). Migrated here so the /search/ endpoint
coverage is exercised in CI alongside the autocomplete/alert tests.
"""

from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import Client

from apps.ads.models import Ad
from apps.ads.services.listings_query import (
    MAX_FEATURE_FILTER_SLUGS,
    ListingsQuery,
    ListingsQueryParams,
)
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.lookups.models import LookupGroup, LookupItem
from apps.search.services.cache import SEARCH_CACHE_MAX_HITS
from apps.users.models import User
from conftest import create_test_ad, create_test_ads_bulk

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _create_feature_group(count: int) -> dict[str, LookupItem]:
    """Create a ``listing_feature`` group of *count* items, keyed by slug.

    Local to this module — ``feature_lookup`` lives in the ads tests conftest
    and cannot be imported here. The count is chosen to exceed the DTO cap so
    the at-cap positive control is meaningful.
    """
    group = LookupGroup.objects.create(code="listing_feature", is_system=True)
    result: dict[str, LookupItem] = {}
    for i in range(count):
        slug = f"feat-{i}"
        result[slug] = LookupItem.objects.create(
            group=group, slug=slug, name_i18n={"ru": slug, "en": slug}, is_active=True
        )
    return result



# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def root_category() -> Category:
    """Create a root-level category."""
    return Category.objects.create(
        name="Транспорт",
        slug="transport",
    )


@pytest.fixture
def child_category(root_category: Category) -> Category:
    """Create a child category under root_category."""
    return Category.objects.create(
        name="Велосипеды",
        slug="bicycles",
        parent=root_category,
    )


@pytest.fixture
def grandchild_category(child_category: Category) -> Category:
    """Create a grandchild category under child_category."""
    return Category.objects.create(
        name="Горные велосипеды",
        slug="mountain-bikes",
        parent=child_category,
    )


@pytest.fixture
def other_category() -> Category:
    """Create a separate (non-descendant) category."""
    return Category.objects.create(
        name="Электроника",
        slug="electronics",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSearchViewPublishesFilter:
    """Search view returns only PUBLISHED ads (TST-004)."""

    def test_search_without_query_returns_only_published(
        self,
        seller: User,
        root_category: Category,
        other_category: Category,
        city: City,
    ) -> None:
        """No-query search returns only PUBLISHED ads, excluding DRAFT/ON_MODERATION/etc."""
        # Create one PUBLISHED ad and several non-PUBLISHED ads
        create_test_ad(
            seller, root_category, city, title="Published Ad", status=AdStatus.PUBLISHED
        )
        create_test_ad(
            seller, other_category, city, title="Draft Ad", status=AdStatus.DRAFT
        )
        create_test_ad(
            seller,
            root_category,
            city,
            title="Moderation Ad",
            status=AdStatus.ON_MODERATION,
        )
        create_test_ad(
            seller, other_category, city, title="Rejected Ad", status=AdStatus.REJECTED
        )
        create_test_ad(
            seller, root_category, city, title="Archived Ad", status=AdStatus.ARCHIVED
        )

        client = Client()
        response = client.get("/search/")

        assert response.status_code == 200
        # Only the PUBLISHED ad should be in the page
        ads_in_page = list(response.context["page_obj"])
        assert len(ads_in_page) == 1
        assert ads_in_page[0].title == "Published Ad"
        assert ads_in_page[0].status == AdStatus.PUBLISHED

    def test_search_with_query_returns_only_published(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """Search with query still filters to PUBLISHED ads only.

        A PUBLISHED and a DRAFT ad share the same title. The search view
        applies ``status=PUBLISHED`` before FTS, so the DRAFT ad must never
        appear in the response — verified directly via the view's ``page_obj``
        rather than a model-level count.
        """
        create_test_ad(
            seller,
            root_category,
            city,
            title="Красный велосипед",
            status=AdStatus.PUBLISHED,
        )
        create_test_ad(
            seller,
            root_category,
            city,
            title="Красный велосипед",
            status=AdStatus.DRAFT,
        )

        client = Client()
        response = client.get("/search/?q=велосипед&lang=ru")

        assert response.status_code == 200
        # The DRAFT ad must never appear in search results — only PUBLISHED
        # ads are returned, even when FTS would match the DRAFT's title.
        ads_in_page = list(response.context["page_obj"])
        assert all(a.status == AdStatus.PUBLISHED for a in ads_in_page)
        assert len(ads_in_page) == 1
        assert ads_in_page[0].status == AdStatus.PUBLISHED

    def test_empty_search_returns_all_published(
        self,
        seller: User,
        root_category: Category,
        other_category: Category,
        city: City,
    ) -> None:
        """No-query search returns all PUBLISHED ads regardless of category."""
        create_test_ad(
            seller,
            root_category,
            city,
            title="Transport Ad",
            status=AdStatus.PUBLISHED,
        )
        create_test_ad(
            seller,
            other_category,
            city,
            title="Electronics Ad",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/search/")

        assert response.status_code == 200
        ads_in_page = list(response.context["page_obj"])
        assert len(ads_in_page) == 2

    def test_search_excludes_deactivated_category_ads(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """A PUBLISHED ad whose category is deactivated does not appear in results.

        The null-safe base queryset filters on ``category__is_active=True`` for
        non-null categories, so deactivating the category should hide its ads.
        """
        create_test_ad(
            seller,
            root_category,
            city,
            title="Active Category Ad",
            status=AdStatus.PUBLISHED,
        )

        # Deactivate the category
        root_category.is_active = False
        root_category.save(update_fields=["is_active"])

        client = Client()
        response = client.get("/search/")

        assert response.status_code == 200
        ads_in_page = list(response.context["page_obj"])
        assert len(ads_in_page) == 0

    def test_search_includes_null_category_published(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """A PUBLISHED ad with ``category=None`` still appears in search results.

        The null-safe base queryset uses
        ``Q(category__isnull=True) | Q(category__is_active=True)`` so NULL-category
        ads are never silently dropped by an INNER JOIN.
        """
        ad = create_test_ad(
            seller,
            root_category,
            city,
            title="Null Category Ad",
            status=AdStatus.PUBLISHED,
        )
        # Detach the ad from its category to simulate a NULL-category PUBLISHED ad
        ad.category = None
        ad.save(update_fields=["category"])

        client = Client()
        response = client.get("/search/")

        assert response.status_code == 200
        ads_in_page = list(response.context["page_obj"])
        assert any(a.id == ad.id for a in ads_in_page)

    def test_features_over_cap_rejected_at_dto(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """A ``?features=`` list over the catalogue invariant is rejected (08-SRCH-001).

        The bound is enforced by ``ListingsQueryParams`` (the DTO), so the
        rejection happens before any queryset is built and surfaces as a 4xx —
        not a 500 and not an unbounded query.
        """
        over_cap = MAX_FEATURE_FILTER_SLUGS + 1
        query = "&".join(f"features=f{i}" for i in range(over_cap))

        client = Client()
        response = client.get(f"/search/?{query}")

        assert response.status_code == 400

    def test_features_at_cap_accepted_and_and_semantics_hold(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """A legal list at exactly the cap is accepted; AND-semantics hold.

        Selecting N distinct features requires an ad to carry all N. The list is
        built at exactly ``MAX_FEATURE_FILTER_SLUGS`` (not one over), so this is
        the positive control that the bound does not reject a legal set.
        """
        group = _create_feature_group(MAX_FEATURE_FILTER_SLUGS + 1)
        selected = [f"feat-{i}" for i in range(MAX_FEATURE_FILTER_SLUGS)]

        ad_all = create_test_ad(
            seller, root_category, city, title="All selected", status=AdStatus.PUBLISHED
        )
        ad_all.features.set([group[slug] for slug in selected])
        ad_partial = create_test_ad(
            seller, root_category, city, title="Partial", status=AdStatus.PUBLISHED
        )
        ad_partial.features.set([group[selected[0]]])

        query = "&".join(f"features={slug}" for slug in selected)
        client = Client()
        response = client.get(f"/search/?{query}")

        assert response.status_code == 200
        ids = {a.id for a in response.context["page_obj"]}
        assert ad_all.id in ids
        assert ad_partial.id not in ids


class TestSearchViewDeclinedConsent:
    """A consent-declined user's PUBLISHED ads are hidden from search and listings (SRH-001)."""

    def test_declined_user_published_ads_hidden_from_search(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """PUBLISHED ads of a declined user do not appear in /search/."""
        declined_ad = create_test_ad(
            seller,
            root_category,
            city,
            title="Объявление отклонённого пользователя",
            status=AdStatus.PUBLISHED,
        )

        # Sanity: the ad is visible before the decline.
        client = Client()
        response = client.get("/search/")
        assert declined_ad.id in {a.id for a in response.context["page_obj"]}

        # Decline consent — the user's PUBLISHED ads must disappear.
        seller.is_declined = True
        seller.save(update_fields=["is_declined"])

        response = client.get("/search/")
        assert response.status_code == 200
        assert declined_ad.id not in {a.id for a in response.context["page_obj"]}

    def test_declined_user_published_ads_hidden_from_listings(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """PUBLISHED ads of a declined user do not appear on the listings page."""
        declined_ad = create_test_ad(
            seller,
            root_category,
            city,
            title="Объявление в списке",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/")
        assert declined_ad.id in {a.id for a in response.context["page_obj"]}

        seller.is_declined = True
        seller.save(update_fields=["is_declined"])

        response = client.get("/")
        assert response.status_code == 200
        assert declined_ad.id not in {a.id for a in response.context["page_obj"]}

    def test_give_consent_restores_declined_ads_to_queryset(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """Restoring consent (is_declined=False) makes the user's ads visible again.

        Verified against the live queryset (``build_queryset``) rather than the
        cached search view: ``give_consent`` intentionally does not bump the
        search cache, so a warm cache entry persists until TTL expiry — the ad
        reappears via the live ``user__is_declined=False`` filter once results
        are (re)computed.
        """
        from apps.users.services.deletion import give_consent

        ad = create_test_ad(
            seller,
            root_category,
            city,
            title="Велосипед после согласия",
            status=AdStatus.PUBLISHED,
        )

        seller.is_declined = True
        seller.save(update_fields=["is_declined"])

        params = ListingsQueryParams()
        assert ad.id not in {a.id for a in ListingsQuery.build_queryset(params)}

        # give_consent clears is_declined -> live filter lets the ad reappear.
        give_consent(seller)
        seller.refresh_from_db()
        assert seller.is_declined is False

        assert ad.id in {a.id for a in ListingsQuery.build_queryset(params)}


class TestSearchViewDescendantCategories:
    """Single-word queries matching a category expand to the descendant subtree."""

    def test_category_match_expands_to_descendants(
        self,
        seller: User,
        root_category: Category,
        child_category: Category,
        grandchild_category: Category,
        other_category: Category,
        city: City,
    ) -> None:
        """A single-word query matching a category name returns ads from all descendants."""
        # Titles must contain the Russian word "Транспорт" so the per-language
        # FTS query (config=russian, vector=search_vector_ru) matches them.
        ad_root = create_test_ad(
            seller,
            root_category,
            city,
            title="Транспорт — продажа прицепа",
            status=AdStatus.PUBLISHED,
        )
        ad_child = create_test_ad(
            seller,
            child_category,
            city,
            title="Транспорт — детский велосипед",
            status=AdStatus.PUBLISHED,
        )
        ad_grandchild = create_test_ad(
            seller,
            grandchild_category,
            city,
            title="Транспорт — горный велосипед",
            status=AdStatus.PUBLISHED,
        )
        # Create ad in a non-descendant category (should NOT appear)
        create_test_ad(
            seller,
            other_category,
            city,
            title="Electronics ad",
            status=AdStatus.PUBLISHED,
        )

        # Also create a non-PUBLISHED ad in the descendant tree (should NOT appear)
        create_test_ad(
            seller,
            child_category,
            city,
            title="Draft child ad",
            status=AdStatus.DRAFT,
        )

        client = Client()
        # "Транспорт" matches the root category name — should expand to all descendants
        response = client.get("/search/?q=Транспорт&lang=ru")

        assert response.status_code == 200
        ads_in_page = list(response.context["page_obj"])
        ad_ids = {a.id for a in ads_in_page}

        # All 3 published descendant ads should appear
        assert ad_root.id in ad_ids
        assert ad_child.id in ad_ids
        assert ad_grandchild.id in ad_ids
        # Non-descendant ad should NOT appear
        assert not any("Electronics" in a.title for a in ads_in_page)
        # Draft ad should NOT appear
        assert not any("Draft" in a.title for a in ads_in_page)

    def test_single_word_category_match_rejects_non_published_descendants(
        self,
        seller: User,
        root_category: Category,
        child_category: Category,
        city: City,
    ) -> None:
        """Non-PUBLISHED descendant ads are excluded even when category matches."""
        # Create a non-PUBLISHED ad in the descendant tree
        create_test_ad(
            seller,
            child_category,
            city,
            title="Non-published descendant",
            status=AdStatus.ON_MODERATION,
        )

        client = Client()
        response = client.get("/search/?q=Транспорт&lang=ru")

        assert response.status_code == 200
        ads_in_page = list(response.context["page_obj"])
        # No published ads exist, so page should be empty
        assert len(ads_in_page) == 0

    def test_q_and_category_coexist(
        self,
        seller: User,
        root_category: Category,
        child_category: Category,
        other_category: Category,
        city: City,
    ) -> None:
        """GET /search/?q=<term>&category=<slug> filters by both FTS keyword
        AND category subtree (Spec 19 CR-1, Assumption A3).

        A two-word query is used to avoid the single-word fuzzy category match
        path (search.py L192-199), keeping the category filter as the sole
        subtree constraint alongside FTS.
        """
        ad_root = create_test_ad(
            seller,
            root_category,
            city,
            title="Продам красный телевизор",
            status=AdStatus.PUBLISHED,
        )
        ad_child = create_test_ad(
            seller,
            child_category,
            city,
            title="Продам красный телевизор",
            status=AdStatus.PUBLISHED,
        )
        # Same title, non-descendant category — excluded by ?category= filter
        create_test_ad(
            seller,
            other_category,
            city,
            title="Продам красный телевизор",
            status=AdStatus.PUBLISHED,
        )
        # Same category subtree, non-matching title — excluded by FTS
        ad_no_match = create_test_ad(
            seller,
            root_category,
            city,
            title="Синяя кофемашина",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get(
            f"/search/?q=красный+телевизор&category={root_category.slug}&lang=ru"
        )

        assert response.status_code == 200
        assert response.context["query"] == "красный телевизор"
        assert response.context["current_category"] == root_category.slug
        result_ids = {a.id for a in response.context["page_obj"]}
        assert ad_root.id in result_ids
        assert ad_child.id in result_ids  # descendant of root_category
        assert ad_no_match.id not in result_ids  # matched category but not FTS
        assert len(result_ids) == 2  # other_category ad excluded by category filter


class TestSearchViewCitySuggestion:
    """Search view provides did-you-mean city suggestions (Block 8 V5)."""

    def test_invalid_city_slug_suggests_similar(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """An invalid ``?city=`` slug triggers a did-you-mean suggestion via difflib."""
        # Create a city with slug "budva" so the typo "budav" has a close match.
        City.objects.create(
            country_code="ME",
            name="Будва",
            region="Coastal",
            slug="budva",
        )
        # Create an ad in the real city so the listing page has content
        create_test_ad(
            seller, root_category, city, title="Телефон", status=AdStatus.PUBLISHED
        )

        client = Client()
        # "budav" is a typo close to "budva" — difflib should suggest it
        response = client.get("/search/?city=budav")

        assert response.status_code == 200
        # The view should pass a suggestion to the template
        assert response.context["suggested_city"] is not None
        # The suggestion should be a valid city slug (not the raw typo)
        assert response.context["suggested_city"] != "budav"


class TestSearchViewPagination:
    """Search results are paginated (24 per page)."""

    def test_first_page_returns_24_ads(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """First page returns exactly 24 ads when there are 25+ published ads."""
        for i in range(25):
            create_test_ad(
                seller,
                root_category,
                city,
                title=f"Ad {i:03d}",
                status=AdStatus.PUBLISHED,
            )

        client = Client()
        response = client.get("/search/")

        assert response.status_code == 200
        page_obj = response.context["page_obj"]
        ads_in_page = list(page_obj)
        assert len(ads_in_page) == 24
        assert page_obj.has_next() is True
        assert page_obj.has_previous() is False
        assert page_obj.number == 1

    def test_second_page_returns_remaining_ads(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """Second page returns remaining ads when there are 25+ published ads."""
        for i in range(25):
            create_test_ad(
                seller,
                root_category,
                city,
                title=f"Ad {i:03d}",
                status=AdStatus.PUBLISHED,
            )

        client = Client()
        response = client.get("/search/?page=2")

        assert response.status_code == 200
        page_obj = response.context["page_obj"]
        ads_in_page = list(page_obj)
        assert len(ads_in_page) == 1
        assert page_obj.has_next() is False
        assert page_obj.has_previous() is True
        assert page_obj.number == 2

    def test_page_out_of_range_returns_last_page(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """Page number beyond the last page returns the last page."""
        for i in range(25):
            create_test_ad(
                seller,
                root_category,
                city,
                title=f"Ad {i:03d}",
                status=AdStatus.PUBLISHED,
            )

        client = Client()
        response = client.get("/search/?page=99")

        assert response.status_code == 200
        page_obj = response.context["page_obj"]
        assert page_obj.number == 2  # Last page

    def test_invalid_page_returns_first_page(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """Invalid page number returns the first page."""
        for i in range(5):
            create_test_ad(
                seller,
                root_category,
                city,
                title=f"Ad {i:03d}",
                status=AdStatus.PUBLISHED,
            )

        client = Client()
        response = client.get("/search/?page=abc")

        assert response.status_code == 200
        page_obj = response.context["page_obj"]
        assert page_obj.number == 1


class TestSearchViewInputRobustness:
    """Input-robustness tests for the /search/ FTS path (SRH-001, SRH-004).

    Guards the input boundary against hostile/malformed/oversized queries:
    previously a >200-char q caused a DataError -> HTTP 500 (public DoS).
    """

    def test_query_exceeding_max_length_returns_200(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """A q longer than 200 chars is truncated, not rejected with 500."""
        create_test_ad(
            seller,
            root_category,
            city,
            title="Транспорт",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/search/?q=" + "а" * 300 + "&lang=ru")

        assert response.status_code == 200

    def test_sql_injection_query_returns_200(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """A SQL-injection-style q returns 200 and leaves the DB intact."""
        create_test_ad(
            seller,
            root_category,
            city,
            title="Транспорт",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/search/?q=%27%3B%20DROP%20TABLE%20ads%3B%20--&lang=ru")

        assert response.status_code == 200
        # The ads table must still exist and contain the published ad
        assert Ad.objects.filter(title="Транспорт").exists()

    def test_homoglyph_and_control_chars_query_returns_200(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """A q with Cyrillic + zero-width + HTML-like payload returns 200."""
        create_test_ad(
            seller,
            root_category,
            city,
            title="Транспорт",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        # Cyrillic + zero-width space + HTML-like fragment
        response = client.get(
            "/search/?q=%D0%A2%D1%80%D0%B0%D0%BD%D1%81%D0%BF%D0%BE%D1%80%D1%82%u200B<script>&lang=ru"
        )

        assert response.status_code == 200

    def test_nul_byte_query_returns_200_with_control_chars_stripped(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """A NUL-bearing q is stripped at the input edge and searched cleaned.

        A literal 0x00 in ``q`` reaches psycopg unencoded and raises
        ``DataError`` (PostgreSQL text values cannot contain NUL), so the
        request was a hard 500 before 08-SRCH-006. The control character is
        percent-encoded (a literal ``\u0000`` in a URL string is NOT decoded by
        Django — the defect recorded as 08-NEW-03 and deliberately left alone in
        ``test_homoglyph_and_control_chars_query_returns_200``).

        Asserts 200 AND the literal context query with control characters
        removed — the ruling is that the CLEANED query is searched.
        """
        create_test_ad(
            seller,
            root_category,
            city,
            title="Транспорт",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/search/?q=ab%00cd&lang=ru")

        assert response.status_code == 200
        assert response.context["query"] == "abcd"

    def test_control_char_0x07_query_returns_200(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """The control: 0x07 already returned 200 and must keep doing so."""
        create_test_ad(
            seller,
            root_category,
            city,
            title="Транспорт",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/search/?q=%07abc&lang=ru")

        assert response.status_code == 200

    def test_legal_query_result_ids_unchanged_by_control_char_strip(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """POSITIVE CONTROL (Product Owner ruling 2026-10-03).

        A legal, control-character-free query must return the same ordered id
        list as an equivalent query carrying a stripped control character. If
        the two diverge, the strip is wrong and 08-SRCH-006 returns rather than
        amending the ruling. The comparison is within-run and on the *ordered*
        list, so it pins byte-identity without hard-coding a database sequence
        value.
        """
        create_test_ad(
            seller,
            root_category,
            city,
            title="Продам красный велосипед",
            status=AdStatus.PUBLISHED,
        )
        create_test_ad(
            seller,
            root_category,
            city,
            title="Синий велосипед",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        baseline = client.get("/search/?q=велосипед&lang=ru")
        cleaned = client.get("/search/?q=%07велосипед%07&lang=ru")

        assert baseline.status_code == 200
        assert cleaned.status_code == 200
        baseline_ids = [a.id for a in baseline.context["page_obj"]]
        cleaned_ids = [a.id for a in cleaned.context["page_obj"]]
        assert baseline_ids  # sanity: the legal query actually matched
        assert cleaned_ids == baseline_ids
        assert cleaned.context["query"] == "велосипед"


class TestSearchViewTotalCount:
    """Regression tests for true total_count vs 1000-row cache cap (SRH-002).

    After SRH-002 the dedicated FTS ``COUNT(*)`` is gated: it runs only at the
    ``SEARCH_CACHE_MAX_HITS`` cap boundary (or on the cold-miss-loser path),
    while on the common non-truncated path ``total_count`` comes from
    ``len(cached_ids)``. These tests verify that above the cap the true count
    is preserved via a ``COUNT(*)`` at the boundary (``results_truncated`` is
    ``True``), and that an exact-cap result set yields ``total_count == 1000``
    and is not marked truncated.
    """

    def test_total_count_exceeds_cap_when_many_matches(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """With >1000 matching ads, total_count is the true count, not 1000.

        Before B3, the cached ID list was sliced at ``SEARCH_CACHE_MAX_HITS``
        (1000) and ``total_count`` was derived from that slice, yielding 1000
        regardless of the true match count. The fix computes a separate
        ``COUNT(*)`` on the FTS-filtered queryset, so ``total_count`` is now
        the true count and ``results_truncated`` is ``True``.
        """
        num_ads = SEARCH_CACHE_MAX_HITS + 1  # 1001
        create_test_ads_bulk(
            seller,
            root_category,
            city,
            count=num_ads,
            title_prefix="Продам велосипед",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/search/?q=велосипед&lang=ru")

        assert response.status_code == 200
        # True count via COUNT(*) — not capped at SEARCH_CACHE_MAX_HITS
        assert response.context["total_count"] == num_ads
        assert response.context["total_count"] != SEARCH_CACHE_MAX_HITS
        # results_truncated must be True when count exceeds the cap
        assert response.context["results_truncated"] is True
        # Pagination still limits the visible page to PER_PAGE (24)
        page_ads = list(response.context["page_obj"])
        assert len(page_ads) == 24
        assert all(a.title.startswith("Продам велосипед") for a in page_ads)

    def test_total_count_at_cap_is_exact_and_not_truncated(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """With exactly SEARCH_CACHE_MAX_HITS matching ads, the count is exact
        and results are not marked truncated.

        The dedicated FTS COUNT(*) runs only at the cap boundary (SRH-002), so
        ``total_count`` equals the cache cap and ``results_truncated`` is False.
        """
        num_ads = SEARCH_CACHE_MAX_HITS  # exactly 1000
        create_test_ads_bulk(
            seller,
            root_category,
            city,
            count=num_ads,
            title_prefix="Продам велосипед",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/search/?q=велосипед&lang=ru")

        assert response.status_code == 200
        assert response.context["total_count"] == SEARCH_CACHE_MAX_HITS
        assert response.context["results_truncated"] is False

    def test_cold_miss_loser_reports_true_count(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """On a cold-miss loser (cache returns None, lock held), the fallback
        FTS queryset is reused to report the true count and truncation flag.

        Seeds >1000 matching ads and forces ``get_cached_search_ids`` to return
        None, so the view falls back to a direct FTS query and derives the count
        from that same queryset (SRH-002).
        """
        num_ads = SEARCH_CACHE_MAX_HITS + 1  # 1001
        create_test_ads_bulk(
            seller,
            root_category,
            city,
            count=num_ads,
            title_prefix="Продам велосипед",
            status=AdStatus.PUBLISHED,
        )

        # Force the cache service to return None (simulating cold miss + lock held)
        with patch("apps.search.views.search.get_cached_search_ids", return_value=None):
            client = Client()
            response = client.get("/search/?q=велосипед&lang=ru")

        assert response.status_code == 200
        # True count via the reused FTS queryset, not capped
        assert response.context["total_count"] == num_ads
        assert response.context["results_truncated"] is True


class TestSearchViewRateLimit:
    """The /search/ endpoint is rate-limited per-IP (SRH-006)."""

    @pytest.fixture(autouse=True)
    def _reset_rate_limit(self) -> None:
        """Clear the rate-limit cache before each test to prevent state bleed.

        The rate limiter keys on the client IP (127.0.0.1 in tests) and
        uses the ``search`` namespace, so an exhausted counter would reject
        every subsequent endpoint test with 429.
        """
        cache.clear()

    def test_search_returns_429_after_threshold(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """After exceeding the per-IP limit, /search/ returns HTTP 429."""
        create_test_ad(
            seller,
            root_category,
            city,
            title="Транспорт",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        # Make 30+ requests (the rate limit) to the search endpoint.
        for i in range(31):
            response = client.get("/search/?q=велосипед&lang=ru")
            if i < 30:
                assert response.status_code == 200, (
                    f"Request {i} should be allowed"
                )
            else:
                assert response.status_code == 429, (
                    f"Request {i} should be rate limited"
                )
                assert response.json()["error"] == "rate_limit"

    def test_search_and_autocomplete_use_independent_counters(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """Exhausting the search counter does not rate-limit autocomplete."""
        create_test_ad(
            seller,
            root_category,
            city,
            title="Транспорт",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        # Exhaust the search counter (30 requests).
        for _ in range(30):
            client.get("/search/?q=велосипед&lang=ru")
        # The 31st search is rejected...
        assert client.get("/search/?q=велосипед&lang=ru").status_code == 429

        # ...but autocomplete (a different namespace) still succeeds.
        response = client.get("/api/search/autocomplete", {"q": "вел"})
        assert response.status_code == 200
