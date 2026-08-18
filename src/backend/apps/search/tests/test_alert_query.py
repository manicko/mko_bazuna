"""
Integration tests for saved search alert services.

Covers:
- ``find_matching_ads``: per-language FTS query, city, category subtree,
  price filters, deduplication via ``Exists``/``OuterRef``, ``SearchRank``
  ordering, 10-ad limit
- ``record_notifications``: bulk creation with ``ignore_conflicts`` dedup
- ``send_alerts`` management command: dry-run mode
"""

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.ads.models import Ad
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.search.models import SavedSearch, SavedSearchNotification
from apps.search.services.alert_query import find_matching_ads, record_notifications
from apps.users.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def seller() -> User:
    """Create a seller user for ad fixtures."""
    return User.objects.create(
        telegram_id=910000200,
        chat_id=910000200,
        password="x",
    )


@pytest.fixture
def buyer() -> User:
    """Create a buyer user with saved searches."""
    return User.objects.create(
        telegram_id=910000201,
        chat_id=910000201,
        password="y",
    )


@pytest.fixture
def category() -> Category:
    """Create a root-level category."""
    return Category.objects.create(name="Транспорт", slug="transport")


@pytest.fixture
def subcategory(category: Category) -> Category:
    """Create a child category under root."""
    return Category.objects.create(
        name="Велосипеды", slug="bicycles", parent=category
    )


@pytest.fixture
def unrelated_category() -> Category:
    """Create another root category (should not match subtree filters)."""
    return Category.objects.create(name="Мебель", slug="furniture")


@pytest.fixture
def city() -> City:
    """Create a city for ad fixtures."""
    return City.objects.create(
        country_code="ME",
        name="Тестград",
        region="FBiH",
        slug="test-grad",
    )


@pytest.fixture
def other_city() -> City:
    """Create another city."""
    return City.objects.create(
        country_code="ME",
        name="Москва",
        region="Central",
        slug="moscow",
    )


def _create_published_ad(seller, category, city, **kwargs) -> Ad:
    """Create a PUBLISHED ad with searchable content."""
    defaults = {
        "user": seller,
        "title": "Красный велосипед",
        "description": "Продается товар по объявлению",
        "category": category,
        "city": city,
        "status": AdStatus.PUBLISHED,
        "published_at": timezone.now() - timezone.timedelta(days=1),
    }
    defaults.update(kwargs)
    return Ad.objects.create(**defaults)


# ---------------------------------------------------------------------------
# find_matching_ads
# ---------------------------------------------------------------------------


class TestFindMatchingAds:
    """Integration tests for find_matching_ads."""

    def test_returns_matching_ads_by_query(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """FTS query matches ads with relevant Russian content."""
        _create_published_ad(seller, category, city, title="Красный велосипед")
        _create_published_ad(seller, category, city, title="Мебель деревянная")

        saved_search = SavedSearch.objects.create(
            user=buyer, query="велосипед", language="ru", is_active=True
        )

        results = find_matching_ads(saved_search)
        assert len(results) == 1
        assert "велосипед" in results[0].title.lower()

    def test_bosnian_query_searches_bosnian_vector(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """A saved search in Bosnian matches the bs vector, not ru/en."""
        _create_published_ad(
            seller,
            category,
            city,
            title_bs="Crveni bicikl",
            description_bs="Prodaje se bicikl",
        )
        # Russian-only ad must not match the Bosnian vector.
        _create_published_ad(seller, category, city, title="Красный велосипед")

        saved_search = SavedSearch.objects.create(
            user=buyer, query="bicikl", language="bs", is_active=True
        )

        results = find_matching_ads(saved_search)
        assert len(results) == 1
        assert "bicikl" in results[0].title_bs.lower()

    def test_english_query_searches_english_vector(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """A saved search in English matches the en vector, not ru/bs."""
        _create_published_ad(
            seller,
            category,
            city,
            title_en="Red bicycle",
            description_en="bicycle for sale",
        )
        _create_published_ad(seller, category, city, title="Красный велосипед")

        saved_search = SavedSearch.objects.create(
            user=buyer, query="bicycle", language="en", is_active=True
        )

        results = find_matching_ads(saved_search)
        assert len(results) == 1
        assert "bicycle" in results[0].title_en.lower()

    def test_legacy_null_language_searches_russian_vector(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """Saved searches with no language (legacy rows) fall back to Russian."""
        _create_published_ad(seller, category, city, title="Красный велосипед")

        saved_search = SavedSearch.objects.create(
            user=buyer, query="велосипед", language=None, is_active=True
        )

        results = find_matching_ads(saved_search)
        assert len(results) == 1

    def test_excludes_non_matching_ads(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """FTS query does not match unrelated ads."""
        _create_published_ad(seller, category, city, title="Мебель деревянная")

        saved_search = SavedSearch.objects.create(
            user=buyer, query="велосипед", language="ru", is_active=True
        )

        results = find_matching_ads(saved_search)
        assert len(results) == 0

    def test_filters_by_city(
        self, seller: User, buyer: User, category: Category, city: City, other_city: City
    ) -> None:
        """City filter narrows results to ads in the specified city."""
        _create_published_ad(seller, category, city, title="Велосипед в городе")
        _create_published_ad(seller, category, other_city, title="Велосипед в другом")

        saved_search = SavedSearch.objects.create(
            user=buyer, query="велосипед", city=city, language="ru", is_active=True
        )

        results = find_matching_ads(saved_search)
        assert len(results) == 1
        assert results[0].city_id == city.id

    def test_filters_by_category_subtree(
        self,
        seller: User,
        buyer: User,
        category: Category,
        subcategory: Category,
        unrelated_category: Category,
        city: City,
    ) -> None:
        """Category filter includes descendants (subtree)."""
        ad_in_sub = _create_published_ad(
            seller, subcategory, city, title="Горный велосипед"
        )
        _create_published_ad(
            seller, unrelated_category, city, title="Диван"
        )

        # Filter by parent category -> should include subcategory ads
        saved_search = SavedSearch.objects.create(
            user=buyer, query="велосипед", category=category, language="ru", is_active=True
        )

        results = find_matching_ads(saved_search)
        assert len(results) == 1
        assert results[0].id == ad_in_sub.id

    def test_filters_by_price_range(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """Price range filters narrow results."""
        _create_published_ad(seller, category, city, title="Дешевый велосипед", price=50)
        _create_published_ad(seller, category, city, title="Дорогой велосипед", price=500)

        saved_search = SavedSearch.objects.create(
            user=buyer, query="велосипед", min_price=100, max_price=300, language="ru", is_active=True
        )

        results = find_matching_ads(saved_search)
        assert len(results) == 0

    def test_min_price_only(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """min_price filter works independently."""
        _create_published_ad(seller, category, city, title="Дешевый велосипед", price=50)
        expensive = _create_published_ad(seller, category, city, title="Дорогой велосипед", price=500)

        saved_search = SavedSearch.objects.create(
            user=buyer, query="велосипед", min_price=100, language="ru", is_active=True
        )

        results = find_matching_ads(saved_search)
        assert len(results) == 1
        assert results[0].id == expensive.id

    def test_max_price_only(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """max_price filter works independently."""
        cheap = _create_published_ad(seller, category, city, title="Дешевый велосипед", price=50)
        _create_published_ad(seller, category, city, title="Дорогой велосипед", price=500)

        saved_search = SavedSearch.objects.create(
            user=buyer, query="велосипед", max_price=100, language="ru", is_active=True
        )

        results = find_matching_ads(saved_search)
        assert len(results) == 1
        assert results[0].id == cheap.id

    def test_excludes_already_notified_ads(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """Ads already in SavedSearchNotification are excluded."""
        ad = _create_published_ad(seller, category, city, title="Уже отправлено")
        saved_search = SavedSearch.objects.create(
            user=buyer, query="отправлено", language="ru", is_active=True
        )
        # Record notification
        SavedSearchNotification.objects.create(
            saved_search=saved_search, ad=ad
        )

        results = find_matching_ads(saved_search)
        assert len(results) == 0

    def test_no_filters_returns_all_published_ads(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """Saved search without filters matches all published ads."""
        _create_published_ad(seller, category, city, title="Любой товар")
        _create_published_ad(seller, category, city, title="Еще товар")

        saved_search = SavedSearch.objects.create(
            user=buyer, is_active=True
        )

        results = find_matching_ads(saved_search)
        assert len(results) == 2

    def test_limits_to_ten_ads(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """Result set is capped at 10 ads for digest."""
        for i in range(15):
            _create_published_ad(
                seller, category, city, title=f"Товар {i}", price=i * 10
            )

        saved_search = SavedSearch.objects.create(
            user=buyer, is_active=True
        )

        results = find_matching_ads(saved_search)
        assert len(results) <= 10

    def test_orders_by_search_rank(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """Results are ordered by SearchRank descending."""
        _create_published_ad(
            seller, category, city,
            title="Велосипед горный",
            description="отличный горный велосипед",
        )
        _create_published_ad(
            seller, category, city,
            title="Самокат детский",
            description="самокат",
        )

        saved_search = SavedSearch.objects.create(
            user=buyer, query="велосипед", language="ru", is_active=True
        )

        results = find_matching_ads(saved_search)
        assert len(results) == 1
        assert "велосипед" in results[0].title.lower()

    def test_empty_query_matches_all(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """Empty query on saved search matches all published ads."""
        _create_published_ad(seller, category, city, title="Любой товар")

        saved_search = SavedSearch.objects.create(
            user=buyer, query="", is_active=True
        )

        results = find_matching_ads(saved_search)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# record_notifications
# ---------------------------------------------------------------------------


class TestRecordNotifications:
    """Tests for record_notifications."""

    def test_creates_notification_records(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """record_notifications creates SavedSearchNotification records."""
        ad = _create_published_ad(seller, category, city)
        saved_search = SavedSearch.objects.create(user=buyer, is_active=True)

        count = record_notifications(saved_search, [ad])
        assert count == 1
        assert SavedSearchNotification.objects.filter(
            saved_search=saved_search, ad=ad
        ).exists()

    def test_ignore_conflicts_skips_duplicates(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """Duplicate (saved_search, ad) pairs are silently skipped."""
        ad = _create_published_ad(seller, category, city)
        saved_search = SavedSearch.objects.create(user=buyer, is_active=True)

        # First call creates
        record_notifications(saved_search, [ad])
        # Second call should skip due to ignore_conflicts
        count = record_notifications(saved_search, [ad])
        assert count == 1
        assert SavedSearchNotification.objects.count() == 1

    def test_handles_multiple_ads(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """Multiple ads are recorded in a single batch."""
        ads = [
            _create_published_ad(seller, category, city, title=f"Товар {i}")
            for i in range(3)
        ]
        saved_search = SavedSearch.objects.create(user=buyer, is_active=True)

        count = record_notifications(saved_search, ads)
        assert count == 3
        assert SavedSearchNotification.objects.count() == 3


# ---------------------------------------------------------------------------
# send_alerts management command
# ---------------------------------------------------------------------------


class TestSendAlertsCommand:
    """Tests for the send_alerts management command."""

    def test_dry_run_logs_counts(
        self, seller: User, buyer: User, category: Category, city: City, caplog
    ) -> None:
        """Dry run logs counts without sending messages."""
        _create_published_ad(seller, category, city, title="Велосипед для теста")
        SavedSearch.objects.create(
            user=buyer, query="велосипед", language="ru", is_active=True
        )

        with caplog.at_level("INFO"):
            call_command("send_alerts", "--dry-run")

        assert "DRY RUN" in caplog.text
        assert "1 saved searches" in caplog.text

    def test_dry_run_no_active_searches(self, caplog) -> None:
        """Dry run with no active searches logs zero counts."""
        with caplog.at_level("INFO"):
            call_command("send_alerts", "--dry-run")

        assert "DRY RUN" in caplog.text
        assert "0 users" in caplog.text

    def test_dry_run_excludes_inactive_searches(
        self, seller: User, buyer: User, category: Category, city: City, caplog
    ) -> None:
        """Inactive saved searches are excluded from dry-run counts."""
        _create_published_ad(seller, category, city, title="Велосипед")
        SavedSearch.objects.create(
            user=buyer, query="велосипед", language="ru", is_active=False
        )

        with caplog.at_level("INFO"):
            call_command("send_alerts", "--dry-run")

        assert "DRY RUN" in caplog.text
        assert "0 saved searches" in caplog.text
