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

import pytest
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.users.models import User
from django.test import Client

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


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
        response = client.get("/search/?q=велосипед")

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
        response = client.get("/search/?q=Транспорт")

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
        response = client.get("/search/?q=Транспорт")

        assert response.status_code == 200
        ads_in_page = list(response.context["page_obj"])
        # No published ads exist, so page should be empty
        assert len(ads_in_page) == 0


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
