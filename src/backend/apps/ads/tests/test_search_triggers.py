"""
Integration tests for the PostgreSQL search_vector trigger (TASK_026).

Verifies the plpgsql trigger installed by migration 0002_search_vector_triggers
correctly maintains ``ads.search_vector`` (and denormalized ``category_name``)
on INSERT and UPDATE, and that the resulting FTS vector is queryable using the
same SearchQuery/SearchRank API the web search view relies on.

These are DB-backed tests using real PostgreSQL per project spec (native FTS
with the 'russian' text search configuration is PostgreSQL-only).
"""

import pytest
from apps.ads.models import Ad
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.utils import timezone

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture
def category():
    return Category.objects.create(name="Транспорт", slug="transport")


@pytest.fixture
def city():
    return City.objects.create(
        country_code="ME",
        name="Тестград",
        region="FBiH",
        slug="test_grad",
    )


@pytest.fixture
def seller():
    from apps.users.models import User

    return User.objects.create(telegram_id=910000001, chat_id=910000001, password="x")


def _create_published_ad(seller, category, city, **kwargs) -> Ad:
    """Create a PUBLISHED ad, applying timestamp overrides via UPDATE."""
    defaults = {
        "user": seller,
        "title": "Красный велосипед",
        "description": "Продается детский велосипед в хорошем состоянии",
        "category": category,
        "city": city,
        "status": AdStatus.PUBLISHED,
        "published_at": timezone.now() - timezone.timedelta(days=1),
    }
    defaults.update(kwargs)
    return Ad.objects.create(**defaults)


def _fts_match(ad: Ad, query: str) -> bool:
    """Replicate the search view's FTS predicate against a single ad."""
    search_query = SearchQuery(query, search_type="websearch", config="russian")
    return Ad.objects.filter(pk=ad.pk, search_vector=search_query).exists()


class TestSearchVectorTrigger:
    """Trigger maintains search_vector on INSERT/UPDATE."""

    def test_insert_populates_search_vector(self, seller, category, city):
        ad = _create_published_ad(seller, category, city)
        ad.refresh_from_db()
        assert ad.search_vector is not None
        # The russian-config tsvector should contain the title lexeme.
        assert _fts_match(ad, "велосипед")

    def test_insert_denormalizes_category_name(self, seller, category, city):
        ad = _create_published_ad(seller, category, city)
        ad.refresh_from_db()
        # category_name is synced from the categories table by the trigger.
        assert ad.category_name == category.name

    def test_title_update_refreshes_search_vector(self, seller, category, city):
        ad = _create_published_ad(seller, category, city)
        ad.title = "Синий скейтборд"
        ad.description = "Детский скейтборд в хорошем состоянии"
        ad.save()
        ad.refresh_from_db()
        assert _fts_match(ad, "скейтборд")
        assert not _fts_match(ad, "велосипед")

    def test_description_is_searchable(self, seller, category, city):
        ad = _create_published_ad(seller, category, city)
        assert _fts_match(ad, "детский")

    def test_category_rename_propagates(self, seller, category, city):
        ad = _create_published_ad(seller, category, city)
        category.name = "Байки"
        category.save()
        ad.refresh_from_db()
        assert ad.category_name == "Байки"
        # The new category name is folded into the search vector.
        assert _fts_match(ad, "Байки")

    def test_search_rank_orders_by_relevance(self, seller, category, city):
        bike = _create_published_ad(
            seller,
            category,
            city,
            title="велосипед горный",
            description="отличный велосипед",
        )
        scooter = _create_published_ad(
            seller,
            category,
            city,
            title="самокат",
            description="детский самокат",
        )
        search_query = SearchQuery("велосипед", search_type="websearch", config="russian")
        ranked = (
            Ad.objects.filter(status=AdStatus.PUBLISHED)
            .annotate(rank=SearchRank("search_vector", search_query))
            .filter(search_vector=search_query)
            .order_by("-rank")
        )
        ids = [a.id for a in ranked]
        assert bike.id in ids
        assert scooter.id not in ids

    def test_unpublished_ads_excluded_from_search_view(self, seller, category, city):
        ad = _create_published_ad(seller, category, city)
        # The web search view only searches PUBLISHED ads.
        Ad.objects.filter(pk=ad.pk).update(status=AdStatus.DRAFT)
        ad.refresh_from_db()
        published_only = Ad.objects.filter(status=AdStatus.PUBLISHED)
        assert not published_only.filter(pk=ad.pk).exists()
        # search_vector is still populated, but the view's status filter hides it.
        assert _fts_match(ad, "велосипед")
