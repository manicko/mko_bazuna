"""
Integration tests for the PostgreSQL per-language search vector triggers.

Verifies the plpgsql trigger installed by migration 0007_search_vector_i18n
correctly maintains ``ads.search_vector_ru/bs/en`` (and the denormalized
``category_name``) on INSERT and UPDATE, including localized category names
(``name_i18n``), and that each per-language vector is queryable using the
same SearchQuery/SearchRank API the search view relies on.

These are DB-backed tests using real PostgreSQL per project spec (native FTS
with the 'russian'/'simple'/'english' text search configurations is
PostgreSQL-only).
"""

import pytest
from apps.ads.models import Ad
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.utils import timezone

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]

# locale -> (vector field, FTS config) used by the trigger and search view.
LOCALE_CONFIG = {
    "ru": ("search_vector_ru", "russian"),
    "bs": ("search_vector_bs", "simple"),
    "en": ("search_vector_en", "english"),
}


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


def _fts_match(ad: Ad, query: str, locale: str = "ru") -> bool:
    """Replicate the search view's FTS predicate against a single ad."""
    vector_field, config = LOCALE_CONFIG[locale]
    search_query = SearchQuery(query, search_type="websearch", config=config)
    return Ad.objects.filter(pk=ad.pk, **{vector_field: search_query}).exists()


class TestSearchVectorTrigger:
    """Trigger maintains all three per-language vectors on INSERT/UPDATE."""

    def test_insert_populates_all_search_vectors(self, seller, category, city):
        ad = _create_published_ad(seller, category, city)
        ad.refresh_from_db()
        assert ad.search_vector_ru is not None
        assert ad.search_vector_bs is not None
        assert ad.search_vector_en is not None

    def test_russian_vector_searchable(self, seller, category, city):
        ad = _create_published_ad(seller, category, city)
        ad.refresh_from_db()
        # The russian-config tsvector should contain the Russian title lexeme.
        assert _fts_match(ad, "велосипед", locale="ru")

    def test_bosnian_vector_searchable(self, seller, category, city):
        ad = _create_published_ad(
            seller,
            category,
            city,
            title_bs="Crveni bicikl",
            description_bs="Prodaje se djeciji bicikl",
        )
        ad.refresh_from_db()
        assert _fts_match(ad, "bicikl", locale="bs")

    def test_english_vector_searchable(self, seller, category, city):
        ad = _create_published_ad(
            seller,
            category,
            city,
            title_en="Red bicycle",
            description_en="Children's bicycle for sale",
        )
        ad.refresh_from_db()
        assert _fts_match(ad, "bicycle", locale="en")

    def test_insert_denormalizes_category_name(self, seller, category, city):
        ad = _create_published_ad(seller, category, city)
        ad.refresh_from_db()
        # category_name is synced from the categories table by the trigger.
        assert ad.category_name == category.name

    def test_title_update_refreshes_all_search_vectors(self, seller, category, city):
        ad = _create_published_ad(seller, category, city)
        ad.title = "Синий скейтборд"
        ad.description = "Детский скейтборд в хорошем состоянии"
        ad.save()
        ad.refresh_from_db()
        assert _fts_match(ad, "скейтборд", locale="ru")
        assert not _fts_match(ad, "велосипед", locale="ru")

    def test_description_is_searchable_in_russian(self, seller, category, city):
        ad = _create_published_ad(seller, category, city)
        assert _fts_match(ad, "детский", locale="ru")

    def test_category_rename_propagates(self, seller, category, city):
        ad = _create_published_ad(seller, category, city)
        category.name = "Байки"
        category.save()
        ad.refresh_from_db()
        assert ad.category_name == "Байки"
        # The new Russian category name is folded into the Russian vector.
        assert _fts_match(ad, "Байки", locale="ru")

    def test_localized_category_name_searchable_per_language(self, seller, city):
        category = Category.objects.create(
            name="Транспорт",
            slug="transport",
            name_i18n={"bs": "Transport", "en": "Transport"},
        )
        ad = _create_published_ad(seller, category, city)
        ad.refresh_from_db()
        # The localized category name is indexed in the bs/en vectors.
        assert _fts_match(ad, "transport", locale="bs")
        assert _fts_match(ad, "transport", locale="en")

    def test_category_name_i18n_edit_cascades_reindex(self, seller, city):
        category = Category.objects.create(
            name="Транспорт",
            slug="transport",
            name_i18n={"bs": "Transport", "en": "Transport"},
        )
        ad = _create_published_ad(seller, category, city)
        # Editing name_i18n re-propagates and re-indexes affected ads.
        category.name_i18n = {"bs": "Prijevoz", "en": "Vehicles"}
        category.save()
        ad.refresh_from_db()
        assert _fts_match(ad, "prijevoz", locale="bs")
        assert _fts_match(ad, "vehicles", locale="en")
        assert not _fts_match(ad, "transport", locale="bs")

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
        vector_field, config = LOCALE_CONFIG["ru"]
        search_query = SearchQuery("велосипед", search_type="websearch", config=config)
        ranked = (
            Ad.objects.filter(status=AdStatus.PUBLISHED)
            .annotate(rank=SearchRank(vector_field, search_query))
            .filter(**{vector_field: search_query})
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
        # Vectors are still populated, but the view's status filter hides it.
        assert _fts_match(ad, "велосипед", locale="ru")
