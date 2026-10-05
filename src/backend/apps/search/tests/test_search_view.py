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

import logging
import re
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from apps.ads.models import Ad
from apps.ads.services.listings_query import MAX_FEATURE_FILTER_SLUGS
from apps.categories.models import Category
from apps.core.enums import AdSort, AdStatus
from apps.core.utils.json_logging import RedactingJsonFormatter
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


def _create_lookup_item(group_code: str, slug: str) -> LookupItem:
    """Create one active lookup item in its group (local helper).

    ``purpose_lookup`` / ``condition_lookup`` / ``feature_lookup`` live in the
    ads tests conftest and are not importable from the search tests package.
    """
    group, _ = LookupGroup.objects.get_or_create(
        code=group_code, defaults={"is_system": True}
    )
    return LookupItem.objects.create(
        group=group,
        slug=slug,
        name_i18n={"ru": slug, "en": slug},
        is_active=True,
    )



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

    @pytest.mark.django_db(transaction=True)
    def test_give_consent_restores_declined_ads_to_queryset(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """Restoring consent makes the user's ads visible through the search VIEW.

        Drives the anonymous ``/search/`` endpoint with a **warm** cache: the
        page is loaded twice (the second request is a cache hit, proven by an
        unchanged ``get_search_version()``), consent is restored, and the ad must
        reappear on the next request with **no manual cache bump**. The assertion
        moved from ``ListingsQuery.build_queryset`` to the view because the whole
        defect — a stale cached result set — is invisible to a queryset-level
        check (08-SRCH-005). The old docstring claimed ``give_consent``
        intentionally does not bump the search cache; that claim documented the
        defect and is gone.
        """
        from apps.search.services.cache import get_search_version
        from apps.users.services.deletion import give_consent

        ad = create_test_ad(
            seller,
            root_category,
            city,
            title="Продам красный велосипед",
            status=AdStatus.PUBLISHED,
            published_at=timezone.now(),
        )

        seller.is_declined = True
        seller.save(update_fields=["is_declined"])

        client = Client()
        # Warm the cache with the declined (empty) result set.
        first = client.get("/search/?q=велосипед&lang=ru")
        assert ad.id not in {a.id for a in first.context["page_obj"]}

        version_after_first = get_search_version()
        second = client.get("/search/?q=велосипед&lang=ru")
        # The second request is a cache hit: the version did not move.
        assert get_search_version() == version_after_first
        assert ad.id not in {a.id for a in second.context["page_obj"]}

        # give_consent clears is_declined and invalidates the search cache.
        give_consent(seller)
        seller.refresh_from_db()
        assert seller.is_declined is False

        third = client.get("/search/?q=велосипед&lang=ru")
        assert ad.id in {a.id for a in third.context["page_obj"]}


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


class TestSearchViewAmbiguousCategoryName:
    """An ambiguous localised category display name scopes to no branch (08-VAL-003).

    ``Category.name`` has no uniqueness constraint and ``name_i18n`` is
    free-form, so two active categories can share a localised display name.
    Both resolution paths (``_fuzzy_category_match`` exact-name, and
    ``_fuzzy_match_by_name`` fuzzy) previously returned the first hit, scoping
    a single-word search to an arbitrary branch that may hold no matching ads.
    The fix returns no guess when two or more ids match, so the search covers
    the whole tree instead of an arbitrary subtree.

    The reproduction needs a clean schema and an asserted
    ``ads_search_vector_update`` trigger (08-VAL-003 method note): the autouse
    fixture re-asserts the trigger and clears stale rows before each test, so a
    leftover-row artefact cannot make a correct fix look broken.
    """

    @pytest.fixture(autouse=True)
    def _ensure_clean_fts_schema(self) -> None:
        """Wipe ads and re-assert the FTS trigger before the test body."""
        from django.core.management import call_command

        Ad.objects.all().delete()
        call_command("setup_search_triggers")

    def _ambiguous_categories(self) -> tuple[Category, Category]:
        """Two active root categories sharing the ru display name "Велосипеды"."""
        first = Category.objects.create(
            name="Велосипеды",
            slug="bicycles-alpha",
            name_i18n={"ru": "Велосипеды", "bs": "Bicikli", "en": "Bicycles"},
        )
        second = Category.objects.create(
            name="Детские велосипеды",
            slug="bicycles-beta",
            name_i18n={"ru": "Велосипеды", "bs": "Dječiji bicikli", "en": "Kids bikes"},
        )
        return first, second

    def test_ambiguous_exact_name_returns_whole_tree(
        self,
        seller: User,
        city: City,
    ) -> None:
        """Exact path: an ambiguous ru name does not narrow the search.

        Both ads are returned (no narrowing), not one and not zero.
        """
        first, second = self._ambiguous_categories()
        ad_first = create_test_ad(
            seller,
            first,
            city,
            title="Велосипеды объявление первое",
            status=AdStatus.PUBLISHED,
        )
        ad_second = create_test_ad(
            seller,
            second,
            city,
            title="Велосипеды объявление второе",
            status=AdStatus.PUBLISHED,
        )

        # "Велосипеды" is an EXACT localised-name match for both categories,
        # so this exercises the exact-name resolution path.
        response = Client().get("/search/?q=Велосипеды&lang=ru")

        assert response.status_code == 200
        result_ids = {a.id for a in response.context["page_obj"]}
        assert ad_first.id in result_ids
        assert ad_second.id in result_ids
        assert len(result_ids) == 2

    def test_ambiguous_fuzzy_name_returns_whole_tree(
        self,
        seller: User,
        city: City,
    ) -> None:
        """Fuzzy path: an ambiguous name reached by difflib does not narrow.

        The typo "Велосипед" does not equal either display name, so the exact
        path finds nothing and resolution falls to ``difflib`` — which matches
        the ambiguous "Велосипеды". The fix must return no guess there too.
        """
        first, second = self._ambiguous_categories()
        ad_first = create_test_ad(
            seller,
            first,
            city,
            title="Велосипеды объявление первое",
            status=AdStatus.PUBLISHED,
        )
        ad_second = create_test_ad(
            seller,
            second,
            city,
            title="Велосипеды объявление второе",
            status=AdStatus.PUBLISHED,
        )

        # "Велосипед" is a near-miss typo of the ambiguous "Велосипеды".
        response = Client().get("/search/?q=Велосипед&lang=ru")

        assert response.status_code == 200
        result_ids = {a.id for a in response.context["page_obj"]}
        assert ad_first.id in result_ids
        assert ad_second.id in result_ids
        assert len(result_ids) == 2

    def test_unambiguous_name_still_narrows(
        self,
        seller: User,
        city: City,
    ) -> None:
        """Control: distinct display names still narrow to the matching subtree.

        This is the assertion that stops an over-correction ("always no guess")
        from passing the ambiguity tests above.
        """
        bicycles = Category.objects.create(
            name="Велосипеды",
            slug="bicycles",
            name_i18n={"ru": "Велосипеды", "bs": "Bicikli", "en": "Bicycles"},
        )
        electronics = Category.objects.create(
            name="Электроника",
            slug="electronics",
            name_i18n={"ru": "Электроника", "bs": "Elektronika", "en": "Electronics"},
        )
        ad_bicycles = create_test_ad(
            seller,
            bicycles,
            city,
            title="Велосипеды объявление",
            status=AdStatus.PUBLISHED,
        )
        ad_electronics = create_test_ad(
            seller,
            electronics,
            city,
            title="Велосипеды объявление прочее",
            status=AdStatus.PUBLISHED,
        )

        response = Client().get("/search/?q=Велосипеды&lang=ru")

        assert response.status_code == 200
        result_ids = {a.id for a in response.context["page_obj"]}
        # The unambiguous name narrows to the bicycles subtree ...
        assert ad_bicycles.id in result_ids
        # ... so an ad in a different branch is excluded by the filter.
        assert ad_electronics.id not in result_ids


class TestSearchViewCategoryNarrowingSignal:
    """The single-word narrowing is signalled and undoable (08-SRCH-009, O8).

    Q8 was resolved 2026-10-03 (options b+c): the narrowing stays a hard filter
    and the results page signals it with an undo. O8 (coordinator ruling) added
    the real undo as a per-request opt-out (``?all_categories=1``) that leaves the
    default predicate byte-identical. These tests pin the signal, the real undo,
    the whole-tree+query-preserving behaviour, and the visibility guarantee that
    the undo must not widen.
    """

    def test_control_renders_and_undo_widens_to_whole_tree(
        self,
        seller: User,
        root_category: Category,
        child_category: Category,
        other_category: Category,
        city: City,
    ) -> None:
        """A one-word category match renders the control; its undo keeps q, drops the guess."""
        ad_narrowed = create_test_ad(
            seller,
            child_category,
            city,
            title="Транспорт — детский велосипед",
            status=AdStatus.PUBLISHED,
        )
        ad_other_branch = create_test_ad(
            seller,
            other_category,
            city,
            title="Транспорт — электроника",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/search/?q=Транспорт&min_price=10&lang=ru")

        assert response.status_code == 200
        # The narrowing happened: only the matching subtree is returned.
        narrowed_ids = {a.id for a in response.context["page_obj"]}
        assert ad_narrowed.id in narrowed_ids
        assert ad_other_branch.id not in narrowed_ids
        assert response.context["narrowed_category"] is not None

        # The control renders, naming the guessed category and offering the undo.
        # Under ?lang=ru the msgids resolve to the Russian catalogue, so assert
        # the translated strings (which also proves the ru msgstr is wired).
        html = response.content.decode()
        assert "Смотреть все объявления" in html
        assert root_category.name in html

        # Follow the undo link exactly as rendered: it keeps the buyer's query,
        # opts out of the guess, and preserves the other active filters.
        href_match = re.search(
            r'<a href="([^"]*)"[^>]*>Смотреть все объявления</a>', html
        )
        assert href_match, "undo link not found in rendered control"
        undo_href = href_match.group(1)
        assert "all_categories=1" in undo_href
        assert "q=" in undo_href
        assert "min_price=10" in undo_href

        undo = client.get(undo_href)
        assert undo.status_code == 200
        # The buyer's own query is preserved, not discarded.
        assert undo.context["query"] == "Транспорт"
        whole_tree_ids = {a.id for a in undo.context["page_obj"]}
        assert ad_narrowed.id in whole_tree_ids
        assert ad_other_branch.id in whole_tree_ids

    def test_control_does_not_widen_visibility(
        self,
        seller: User,
        root_category: Category,
        child_category: Category,
        other_category: Category,
        city: City,
    ) -> None:
        """The undo must not expose non-PUBLISHED or inactive-category ads.

        Asserted WITH the control rendered and by following its rendered href
        (which carries ``all_categories=1``), not a hand-built URL.
        """
        active_ad = create_test_ad(
            seller,
            child_category,
            city,
            title="Транспорт — детский велосипед",
            status=AdStatus.PUBLISHED,
        )
        draft_ad = create_test_ad(
            seller,
            child_category,
            city,
            title="Транспорт — черновик",
            status=AdStatus.DRAFT,
        )
        # An ad whose category is inactive must stay hidden.
        other_category.is_active = False
        other_category.save(update_fields=["is_active"])
        inactive_ad = create_test_ad(
            seller,
            other_category,
            city,
            title="Транспорт — неактивная категория",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/search/?q=Транспорт&lang=ru")

        assert response.status_code == 200
        html = response.content.decode()
        # The control is rendered ...
        assert "Смотреть все объявления" in html

        # ... and the undo target still applies the visibility predicate.
        href_match = re.search(
            r'<a href="([^"]*)"[^>]*>Смотреть все объявления</a>', html
        )
        assert href_match, "undo link not found in rendered control"
        undo = client.get(href_match.group(1))
        assert undo.status_code == 200
        whole_tree_ids = {a.id for a in undo.context["page_obj"]}
        assert active_ad.id in whole_tree_ids
        assert draft_ad.id not in whole_tree_ids
        assert inactive_ad.id not in whole_tree_ids

    def test_multi_word_query_renders_no_control(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """A two-word query applies no category narrowing and renders no control."""
        create_test_ad(
            seller,
            root_category,
            city,
            title="Транспорт красный",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/search/?q=Транспорт+красный&lang=ru")

        assert response.status_code == 200
        assert response.context["narrowed_category"] is None
        assert "Смотреть все объявления" not in response.content.decode()

    def test_all_categories_flag_returns_whole_tree_and_keeps_query(
        self,
        seller: User,
        root_category: Category,
        child_category: Category,
        other_category: Category,
        city: City,
    ) -> None:
        """The flag suppresses the narrowing and keeps the query (O8).

        With ``?all_categories=1`` a single-word query returns results from the
        whole tree and the buyer's query is preserved in the context.
        """
        ad_narrowed = create_test_ad(
            seller,
            child_category,
            city,
            title="Транспорт — детский велосипед",
            status=AdStatus.PUBLISHED,
        )
        ad_other_branch = create_test_ad(
            seller,
            other_category,
            city,
            title="Транспорт — электроника",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        # Default: the narrowing hides the other branch.
        narrowed = client.get("/search/?q=Транспорт&lang=ru")
        assert ad_other_branch.id not in {
            a.id for a in narrowed.context["page_obj"]
        }

        # Opt-out: the whole tree returns and the query is retained.
        response = client.get("/search/?q=Транспорт&all_categories=1&lang=ru")

        assert response.status_code == 200
        assert response.context["query"] == "Транспорт"
        # Nothing to undo when the guess did not apply.
        assert response.context["narrowed_category"] is None
        result_ids = {a.id for a in response.context["page_obj"]}
        assert ad_narrowed.id in result_ids
        assert ad_other_branch.id in result_ids

    def test_all_categories_flag_multi_word_is_unaffected(
        self,
        seller: User,
        root_category: Category,
        child_category: Category,
        city: City,
    ) -> None:
        """A multi-word query is unaffected by the flag (no narrowing either way)."""
        ad = create_test_ad(
            seller,
            child_category,
            city,
            title="Транспорт красный",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        without = client.get("/search/?q=Транспорт+красный&lang=ru")
        with_flag = client.get(
            "/search/?q=Транспорт+красный&all_categories=1&lang=ru"
        )

        assert with_flag.status_code == 200
        assert with_flag.context["narrowed_category"] is None
        assert ad.id in {a.id for a in with_flag.context["page_obj"]}
        # The flag changes nothing for a multi-word query.
        assert {a.id for a in without.context["page_obj"]} == {
            a.id for a in with_flag.context["page_obj"]
        }

    def test_all_categories_flag_preserves_every_other_filter(
        self,
        seller: User,
        root_category: Category,
        child_category: Category,
        other_category: Category,
        city: City,
    ) -> None:
        """The opt-out preserves all eight other active filters, not just min_price.

        The Validator noted the shipped test exercised only ``min_price``. This
        asserts city, sort, price range, purpose, condition and features all
        survive alongside the flag.
        """
        purpose = _create_lookup_item("listing_purpose", "sell")
        condition = _create_lookup_item("listing_condition", "new")
        feature = _create_lookup_item("listing_feature", "delivery")

        ad = create_test_ad(
            seller,
            child_category,
            city,
            title="Транспорт — детский велосипед",
            status=AdStatus.PUBLISHED,
            price=150,
            listing_purpose=purpose,
            listing_condition=condition,
        )
        ad.features.add(feature)
        # A same-query ad that must be excluded by the preserved city filter.
        ad_wrong_city = create_test_ad(
            seller,
            child_category,
            city=None,
            title="Транспорт — без города",
            status=AdStatus.PUBLISHED,
            listing_purpose=purpose,
            listing_condition=condition,
        )
        ad_wrong_city.features.add(feature)

        client = Client()
        params = {
            "q": "Транспорт",
            "all_categories": "1",
            "city": city.slug,
            "sort": AdSort.PRICE_LOW.value,
            "min_price": "10",
            "max_price": "200",
            "listing_purpose": purpose.slug,
            "condition": condition.slug,
            "features": feature.slug,
            "lang": "ru",
        }
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        response = client.get(f"/search/?{query_string}")

        assert response.status_code == 200
        ctx = response.context
        assert ctx["current_city"] == city.slug
        assert ctx["current_sort"] == AdSort.PRICE_LOW
        assert ctx["min_price"] == "10"
        assert ctx["max_price"] == "200"
        assert ctx["current_listing_purpose"] == purpose.slug
        assert ctx["current_condition"] == condition.slug
        assert list(ctx["current_features"]) == [feature.slug]

        result_ids = {a.id for a in ctx["page_obj"]}
        assert ad.id in result_ids
        # The city filter is preserved, so the same-query ad in no city is out.
        assert ad_wrong_city.id not in result_ids


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

    def test_lone_space_query_trims_to_browse_all(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """A lone-space q trims to empty and browses all (08-SRCH-006 follow-up).

        ``?q=+`` decodes to a single space, so this input is reachable by
        accident. The pre-fix line trimmed before slicing, so the empty query
        falls through to the unfiltered browse-all listing; the 08-SRCH-006
        rewrite dropped the trim as collateral and made this a zero-result.
        This test pins the restored (trim) behaviour.
        """
        create_test_ad(
            seller,
            root_category,
            city,
            title="Транспорт",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/search/?q=%20&lang=ru")

        assert response.status_code == 200
        assert response.context["query"] == ""
        assert response.context["page_obj"].paginator.count == 1

    def test_leading_and_trailing_space_query_is_trimmed(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """A q padded with spaces is trimmed to the bare term and still matches.

        ``?q=%20abc%20`` must search ``"abc"``, not ``" abc "``: the trim runs
        before the control-character strip and the slice, so the rendered context
        query is the trimmed value (08-SRCH-006 follow-up).
        """
        create_test_ad(
            seller,
            root_category,
            city,
            title="Продам abc велосипед",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/search/?q=%20abc%20&lang=ru")

        assert response.status_code == 200
        assert response.context["query"] == "abc"
        assert response.context["page_obj"].paginator.count == 1

    def test_trim_then_strip_control_chars_order(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """The control-character strip still runs BEFORE the trim (08-SRCH-006).

        ``?q=%20%00%20abc%00`` must yield ``"abc"``: the control-character strip
        removes both NULs first, ``.strip()`` then removes the surrounding spaces,
        and the slice leaves the bare term. If the trim ran first, a NUL adjacent
        to a space would shield that space (``" \\x00 abc\\x00".strip()`` keeps the
        leading space), and the context query would come out as ``" abc"`` — this
        test pins the working order.
        """
        create_test_ad(
            seller,
            root_category,
            city,
            title="Продам abc велосипед",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/search/?q=%20%00%20abc%00&lang=ru")

        assert response.status_code == 200
        assert response.context["query"] == "abc"
        assert response.context["page_obj"].paginator.count == 1

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


class TestSearchLogRedaction:
    """The zero-result search log line redacts PII (08-SRCH-002).

    ``search()`` logs on the zero-result branch only. Before this change the
    ``%s`` argument was ``sanitize_query_for_log(query)`` — a control-character
    stripper and 100-char truncator that is **not** a redactor — so a phone
    number, an e-mail address or a two-word capitalised name typed into ``q``
    reached the production JSONL sink verbatim. Rendering the captured
    ``LogRecord`` through the real ``RedactingJsonFormatter`` is the point: the
    argument is a lazily-formatted ``%s`` placeholder, so asserting on the call
    argument alone would not have caught the defect.
    """

    def test_zero_result_log_line_redacts_pii(
        self,
        seller: User,
        root_category: Category,
        city: City,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The formatted line contains none of the phone/e-mail/name."""
        create_test_ad(
            seller,
            root_category,
            city,
            title="Транспорт",
            status=AdStatus.PUBLISHED,
        )

        phone = "+38267123456"
        email = "person@example.com"
        name = "Ivan Petrov"
        query = f"{phone} {email} {name}"

        client = Client()
        with caplog.at_level(logging.INFO, logger="apps.search.views.search"):
            response = client.get("/search/", {"q": query, "lang": "ru"})

        assert response.status_code == 200
        assert response.context["has_results"] is False

        record = next(
            r
            for r in caplog.records
            if r.name == "apps.search.views.search" and r.levelno == logging.INFO
        )
        formatted = RedactingJsonFormatter().format(record)

        assert phone not in formatted
        assert email not in formatted
        assert name not in formatted

    def test_benign_zero_result_query_still_logs(
        self,
        seller: User,
        root_category: Category,
        city: City,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A query with no identifiers is still logged (triage is not lost)."""
        create_test_ad(
            seller,
            root_category,
            city,
            title="Транспорт",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        with caplog.at_level(logging.INFO, logger="apps.search.views.search"):
            response = client.get("/search/", {"q": "велосипед", "lang": "ru"})

        assert response.status_code == 200
        assert response.context["has_results"] is False

        record = next(
            r
            for r in caplog.records
            if r.name == "apps.search.views.search" and r.levelno == logging.INFO
        )
        # The formatter JSON-escapes non-ASCII, so assert on the rendered
        # message text rather than the escaped JSON byte sequence.
        assert "велосипед" in record.getMessage()
        assert "Empty search results for query" in RedactingJsonFormatter().format(record)


class TestSearchViewTotalCount:
    """Regression tests for the bounded display count vs the cache cap.

    After BLOCK 6 (13-PERF-006 #1 validated 2026-09) the dedicated FTS
    ``COUNT(*)`` is gone: the producer pushes ``[:SEARCH_CACHE_MAX_HITS]`` into
    SQL, so the at/over-cap path derives its count from that already-bounded,
    already-filtered list and never re-runs the FTS filter to count. The count
    on the truncated path is therefore the bounded list length; the *displayed*
    value for a truncated set is restated by BLOCK 7 under the Q9 ruling of
    2026-10-03 (``SEARCH_CACHE_MAX_HITS + 1``, never a true total that cannot be
    computed).
    """

    def test_total_count_exceeds_cap_when_many_matches(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """With >1000 matching ads, the count is the bounded list, not a recount.

        Before BLOCK 6, the cached ID list was sliced at
        ``SEARCH_CACHE_MAX_HITS`` and a second FTS ``COUNT(*)`` produced the true
        total. The cap is now pushed into the producer's SQL (13-PERF-006 #1),
        so the at/over-cap path consumes the bounded list: the count is the
        list length (the cap) and ``results_truncated`` is ``True``. No second
        FTS evaluation runs.
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
        # The bounded cached list drives the count at/over the cap.
        assert response.context["total_count"] == SEARCH_CACHE_MAX_HITS
        # results_truncated must be True when the result set reaches the cap
        assert response.context["results_truncated"] is True
        # Pagination still limits the visible page to PER_PAGE (24)
        page_ads = list(response.context["page_obj"])
        assert len(page_ads) == 24
        assert all(a.title.startswith("Продам велосипед") for a in page_ads)

    def test_total_count_at_cap_is_bounded_and_truncated(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """With exactly SEARCH_CACHE_MAX_HITS matching ads, the set is truncated.

        The producer's SQL ``LIMIT`` bounds the list at the cap, so a result set
        of exactly ``SEARCH_CACHE_MAX_HITS`` rows reaches the boundary
        (``results_truncated`` is ``True``): more rows may exist beyond the cap
        and the count is not recomputed to prove otherwise (13-PERF-006 #1).
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
        assert response.context["results_truncated"] is True

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


class TestSearchViewHasResultsMatchesRenderedRows:
    """``has_results`` comes from the same evaluation as the rendered rows.

    08-SRCH-015: on a warm cache, ``has_results`` was ``total_count > 0`` and
    ``total_count`` was ``len(cached_ids)`` — the cached id count, not the rows
    actually rendered. The rendered page is that id list re-filtered against the
    **live** predicate, so an ad that stopped matching between the cache write
    and the read drops out of ``page_obj`` while the count still includes it.
    With ``has_results`` derived from the count, ``ad_list.html`` rendered
    neither the cards branch nor the empty state: a blank results area at 200.
    These tests pin the derivation and the page-out-of-range control it must not
    confuse with a genuine empty result set.
    """

    def test_stale_cache_ad_mismatch_renders_empty_state(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """A warm cache whose ad no longer matches renders the empty state at 200.

        This is the exact stale-cache window BLOCKS 6/7 create: the ad is
        published (so the FTS producer matches it and the id list is cached),
        then a signal-free bulk ``.update()`` deactivates its category — taking
        it out of the live predicate **without** bumping the cache version — so
        the cached id list is served but the re-filtered query no longer returns
        the row. RED before the fix: the response rendered neither cards nor the
        empty state.
        """
        ad = create_test_ad(
            seller,
            root_category,
            city,
            title="Продам красный велосипед",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        # Warm the cache with the matching (non-empty) result set.
        first = client.get("/search/?q=велосипед&lang=ru")
        assert ad.id in {a.id for a in first.context["page_obj"]}
        assert first.context["has_results"] is True

        # Change the live predicate without a version bump. ``.update()`` fires
        # no signal, so the search content version stays put and the warmed id
        # list is served on the next read while the re-filtered page is empty.
        Category.objects.filter(pk=root_category.pk).update(is_active=False)

        second = client.get("/search/?q=велосипед&lang=ru")

        assert second.status_code == 200
        # The cached count still reports the stale hit...
        assert second.context["total_count"] == 1
        # ...but the page renders no rows, so the empty state must fire.
        assert list(second.context["page_obj"]) == []
        assert second.context["has_results"] is False
        # The request is ``?lang=ru``, so the empty-state copy renders in
        # Russian. Assert the stable msgid fragment (the query itself is
        # HTML-escaped in the copy).
        assert "Результаты не найдены" in second.content.decode()

    def test_healthy_warm_cache_renders_cards_and_same_total_count(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """A normal warm-cache search still renders cards and reports the count.

        The derivation must not suppress a legitimate result set: after warming
        the cache the second (cache-hit) request still renders the ad and
        ``total_count`` is unchanged.
        """
        ad = create_test_ad(
            seller,
            root_category,
            city,
            title="Продам красный велосипед",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        first = client.get("/search/?q=велосипед&lang=ru")
        second = client.get("/search/?q=велосипед&lang=ru")

        assert first.context["total_count"] == 1
        assert second.context["total_count"] == 1
        assert ad.id in {a.id for a in second.context["page_obj"]}
        assert second.context["has_results"] is True
        assert "Результаты не найдены" not in second.content.decode()

    def test_page_out_of_range_does_not_render_empty_state(
        self,
        seller: User,
        root_category: Category,
        city: City,
    ) -> None:
        """Page 2 of a 1-page result set renders the ad, not the empty state.

        ``Paginator.get_page`` resolves an out-of-range page to the last page,
        so ``page_obj`` is non-empty and the "no results at all" empty state
        must NOT fire. This is the control that keeps an out-of-range page from
        being mistaken for an empty result set.
        """
        ad = create_test_ad(
            seller,
            root_category,
            city,
            title="Продам красный велосипед",
            status=AdStatus.PUBLISHED,
        )

        client = Client()
        response = client.get("/search/?q=велосипед&lang=ru&page=2")
        assert response.status_code == 200
        assert ad.id in {a.id for a in response.context["page_obj"]}
        assert response.context["has_results"] is True
        assert "Результаты не найдены" not in response.content.decode()


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
