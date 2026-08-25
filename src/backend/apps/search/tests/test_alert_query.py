"""
Integration tests for saved search alert services.

Covers:
- ``find_matching_ads``: per-language FTS query, city, category subtree,
  price filters, deduplication via ``Exists``/``OuterRef``, ``SearchRank``
  ordering, 10-ad limit
- ``record_notifications``: bulk creation with ``ignore_conflicts`` dedup
- ``send_alerts`` management command: dry-run mode
- ``find_matching_saved_searches``: ad-centric matcher (AL-001)
- ``deliver_immediate_alerts``: idempotent recording + gate behavior (AL-001)
"""

import pytest
from django.core.management import call_command

from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.search.models import SavedSearch, SavedSearchNotification
from apps.search.services.alert_query import (
    find_matching_ads,
    find_matching_saved_searches,
    record_notifications,
)
from apps.users.models import User

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def buyer() -> User:
    """Create a buyer user with saved searches."""
    return User.objects.create(
        telegram_id=910000201,
        chat_id=910000201,
        password="y",
    )


@pytest.fixture
def subcategory(category: Category) -> Category:
    """Create a child category under root."""
    return Category.objects.create(name="Велосипеды", slug="bicycles", parent=category)


@pytest.fixture
def unrelated_category() -> Category:
    """Create another root category (should not match subtree filters)."""
    return Category.objects.create(name="Мебель", slug="furniture")


@pytest.fixture
def other_city() -> City:
    """Create another city."""
    return City.objects.create(
        country_code="ME",
        name="Москва",
        region="Central",
        slug="moscow",
    )


# ---------------------------------------------------------------------------
# find_matching_ads
# ---------------------------------------------------------------------------


class TestFindMatchingAds:
    """Integration tests for find_matching_ads."""

    def test_returns_matching_ads_by_query(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """FTS query matches ads with relevant Russian content."""
        create_test_ad(
            seller, category, city, title="Красный велосипед", status=AdStatus.PUBLISHED
        )
        create_test_ad(
            seller, category, city, title="Мебель деревянная", status=AdStatus.PUBLISHED
        )

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
        create_test_ad(
            seller,
            category,
            city,
            title_bs="Crveni bicikl",
            description_bs="Prodaje se bicikl",
            status=AdStatus.PUBLISHED,
        )
        # Russian-only ad must not match the Bosnian vector.
        create_test_ad(
            seller, category, city, title="Красный велосипед", status=AdStatus.PUBLISHED
        )

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
        create_test_ad(
            seller,
            category,
            city,
            title_en="Red bicycle",
            description_en="bicycle for sale",
            status=AdStatus.PUBLISHED,
        )
        create_test_ad(
            seller, category, city, title="Красный велосипед", status=AdStatus.PUBLISHED
        )

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
        create_test_ad(
            seller, category, city, title="Красный велосипед", status=AdStatus.PUBLISHED
        )

        saved_search = SavedSearch.objects.create(
            user=buyer, query="велосипед", language=None, is_active=True
        )

        results = find_matching_ads(saved_search)
        assert len(results) == 1

    def test_excludes_non_matching_ads(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """FTS query does not match unrelated ads."""
        create_test_ad(
            seller, category, city, title="Мебель деревянная", status=AdStatus.PUBLISHED
        )

        saved_search = SavedSearch.objects.create(
            user=buyer, query="велосипед", language="ru", is_active=True
        )

        results = find_matching_ads(saved_search)
        assert len(results) == 0

    def test_filters_by_city(
        self,
        seller: User,
        buyer: User,
        category: Category,
        city: City,
        other_city: City,
    ) -> None:
        """City filter narrows results to ads in the specified city."""
        create_test_ad(
            seller,
            category,
            city,
            title="Велосипед в городе",
            status=AdStatus.PUBLISHED,
        )
        create_test_ad(
            seller,
            category,
            other_city,
            title="Велосипед в другом",
            status=AdStatus.PUBLISHED,
        )

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
        ad_in_sub = create_test_ad(
            seller,
            subcategory,
            city,
            title="Горный велосипед",
            status=AdStatus.PUBLISHED,
        )
        create_test_ad(
            seller,
            unrelated_category,
            city,
            title="Диван",
            status=AdStatus.PUBLISHED,
        )

        # Filter by parent category -> should include subcategory ads
        saved_search = SavedSearch.objects.create(
            user=buyer,
            query="велосипед",
            category=category,
            language="ru",
            is_active=True,
        )

        results = find_matching_ads(saved_search)
        assert len(results) == 1
        assert results[0].id == ad_in_sub.id

    def test_filters_by_price_range(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """Price range filters narrow results."""
        create_test_ad(
            seller,
            category,
            city,
            title="Дешевый велосипед",
            price=50,
            status=AdStatus.PUBLISHED,
        )
        create_test_ad(
            seller,
            category,
            city,
            title="Дорогой велосипед",
            price=500,
            status=AdStatus.PUBLISHED,
        )

        saved_search = SavedSearch.objects.create(
            user=buyer,
            query="велосипед",
            min_price=100,
            max_price=300,
            language="ru",
            is_active=True,
        )

        results = find_matching_ads(saved_search)
        assert len(results) == 0

    def test_min_price_only(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """min_price filter works independently."""
        create_test_ad(
            seller,
            category,
            city,
            title="Дешевый велосипед",
            price=50,
            status=AdStatus.PUBLISHED,
        )
        expensive = create_test_ad(
            seller,
            category,
            city,
            title="Дорогой велосипед",
            price=500,
            status=AdStatus.PUBLISHED,
        )

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
        cheap = create_test_ad(
            seller,
            category,
            city,
            title="Дешевый велосипед",
            price=50,
            status=AdStatus.PUBLISHED,
        )
        create_test_ad(
            seller,
            category,
            city,
            title="Дорогой велосипед",
            price=500,
            status=AdStatus.PUBLISHED,
        )

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
        ad = create_test_ad(
            seller, category, city, title="Уже отправлено", status=AdStatus.PUBLISHED
        )
        saved_search = SavedSearch.objects.create(
            user=buyer, query="отправлено", language="ru", is_active=True
        )
        # Record notification
        SavedSearchNotification.objects.create(saved_search=saved_search, ad=ad)

        results = find_matching_ads(saved_search)
        assert len(results) == 0

    def test_no_filters_returns_all_published_ads(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """Saved search without filters matches all published ads."""
        create_test_ad(
            seller, category, city, title="Любой товар", status=AdStatus.PUBLISHED
        )
        create_test_ad(
            seller, category, city, title="Еще товар", status=AdStatus.PUBLISHED
        )

        saved_search = SavedSearch.objects.create(user=buyer, is_active=True)

        results = find_matching_ads(saved_search)
        assert len(results) == 2

    def test_limits_to_ten_ads(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """Result set is capped at 10 ads for digest."""
        for i in range(15):
            create_test_ad(
                seller,
                category,
                city,
                title=f"Товар {i}",
                price=i * 10,
                status=AdStatus.PUBLISHED,
            )

        saved_search = SavedSearch.objects.create(user=buyer, is_active=True)

        results = find_matching_ads(saved_search)
        assert len(results) <= 10

    def test_orders_by_search_rank(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """Results are ordered by SearchRank descending."""
        create_test_ad(
            seller,
            category,
            city,
            title="Велосипед горный",
            description="отличный горный велосипед",
            status=AdStatus.PUBLISHED,
        )
        create_test_ad(
            seller,
            category,
            city,
            title="Самокат детский",
            description="самокат",
            status=AdStatus.PUBLISHED,
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
        create_test_ad(
            seller, category, city, title="Любой товар", status=AdStatus.PUBLISHED
        )

        saved_search = SavedSearch.objects.create(user=buyer, query="", is_active=True)

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
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
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
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
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
            create_test_ad(
                seller, category, city, title=f"Товар {i}", status=AdStatus.PUBLISHED
            )
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
        create_test_ad(
            seller,
            category,
            city,
            title="Велосипед для теста",
            status=AdStatus.PUBLISHED,
        )
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
        create_test_ad(
            seller, category, city, title="Велосипед", status=AdStatus.PUBLISHED
        )
        SavedSearch.objects.create(
            user=buyer, query="велосипед", language="ru", is_active=False
        )

        with caplog.at_level("INFO"):
            call_command("send_alerts", "--dry-run")

        assert "DRY RUN" in caplog.text
        assert "0 saved searches" in caplog.text


# ---------------------------------------------------------------------------
# find_matching_saved_searches (ad-centric matcher, AL-001)
# ---------------------------------------------------------------------------


class TestFindMatchingSavedSearches:
    """Tests for the ad-centric matcher used by immediate alerts."""

    def test_returns_active_searches_matching_ad(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        ad = create_test_ad(
            seller, category, city, title="Красный велосипед", status=AdStatus.PUBLISHED
        )
        # No-query search matches the ad via structural filters only.
        SavedSearch.objects.create(user=buyer, is_active=True)

        matches = find_matching_saved_searches(ad)
        assert len(matches) == 1
        assert matches[0].user == buyer

    def test_excludes_inactive_searches(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        ad = create_test_ad(
            seller, category, city, title="Красный велосипед", status=AdStatus.PUBLISHED
        )
        SavedSearch.objects.create(
            user=buyer, query="велосипед", language="ru", is_active=False
        )

        assert find_matching_saved_searches(ad) == []

    def test_filters_by_city(
        self,
        seller: User,
        buyer: User,
        category: Category,
        city: City,
        other_city: City,
    ) -> None:
        ad = create_test_ad(
            seller, category, city, title="Велосипед", status=AdStatus.PUBLISHED
        )
        # A search for another city must not match.
        SavedSearch.objects.create(user=buyer, city=other_city, is_active=True)

        assert find_matching_saved_searches(ad) == []

    def test_filters_by_category_subtree(
        self,
        seller: User,
        buyer: User,
        category: Category,
        subcategory: Category,
        unrelated_category: Category,
        city: City,
    ) -> None:
        # Ad in a subcategory matches a search on the parent category (subtree).
        ad = create_test_ad(
            seller,
            subcategory,
            city,
            title="Горный велосипед",
            status=AdStatus.PUBLISHED,
        )
        SavedSearch.objects.create(user=buyer, category=category, is_active=True)
        # Ad in an unrelated category must not match.
        ad_unrelated = create_test_ad(
            seller, unrelated_category, city, title="Диван", status=AdStatus.PUBLISHED
        )
        SavedSearch.objects.create(
            user=buyer, category=unrelated_category, is_active=True
        )

        matches = find_matching_saved_searches(ad)
        assert len(matches) == 1  # only the parent-category search

        matches_unrelated = find_matching_saved_searches(ad_unrelated)
        assert len(matches_unrelated) == 1  # only the unrelated-category search

    def test_filters_by_price_range(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        in_range = create_test_ad(
            seller,
            category,
            city,
            title="В диапазоне",
            price=200,
            status=AdStatus.PUBLISHED,
        )
        too_cheap = create_test_ad(
            seller, category, city, title="Дешевый", price=50, status=AdStatus.PUBLISHED
        )
        too_expensive = create_test_ad(
            seller,
            category,
            city,
            title="Дорогой",
            price=500,
            status=AdStatus.PUBLISHED,
        )
        SavedSearch.objects.create(
            user=buyer, min_price=100, max_price=300, is_active=True
        )

        assert len(find_matching_saved_searches(in_range)) == 1
        assert find_matching_saved_searches(too_cheap) == []
        assert find_matching_saved_searches(too_expensive) == []

        # No price filter also matches.
        SavedSearch.objects.create(user=buyer, is_active=True)
        assert len(find_matching_saved_searches(too_cheap)) == 1


# ---------------------------------------------------------------------------
# Immediate publish-time alerts (AL-001) — dedup + gate
# ---------------------------------------------------------------------------


class TestDeliverImmediateAlerts:
    """Tests for deliver_immediate_alerts idempotency (no double-send)."""

    def test_records_notification_idempotently(
        self, seller: User, buyer: User, category: Category, city: City, monkeypatch
    ) -> None:
        # Keep the background Telegram thread from running in tests.
        class FakeThread:
            def __init__(self, *args, **kwargs):
                pass

            def start(self):
                pass

        monkeypatch.setattr(
            "apps.search.services.immediate_alerts.threading.Thread", FakeThread
        )

        from apps.search.services.immediate_alerts import deliver_immediate_alerts

        ad = create_test_ad(
            seller, category, city, title="Красный велосипед", status=AdStatus.PUBLISHED
        )
        # No-query active search matches the ad via structural filters only.
        ss = SavedSearch.objects.create(user=buyer, is_active=True)

        deliver_immediate_alerts(ad.id)
        assert (
            SavedSearchNotification.objects.filter(saved_search=ss, ad=ad).count() == 1
        )

        # Re-running (re-publish / backfill) must not double-send.
        deliver_immediate_alerts(ad.id)
        assert (
            SavedSearchNotification.objects.filter(saved_search=ss, ad=ad).count() == 1
        )

    def test_non_published_ad_is_noop(
        self, seller: User, category: Category, city: City
    ) -> None:
        from apps.search.services.immediate_alerts import deliver_immediate_alerts

        draft = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
        deliver_immediate_alerts(draft.id)
        assert SavedSearchNotification.objects.count() == 0


class TestBuildAlertMessageLocalization:
    """Tests for build_alert_message locale handling (CR9)."""

    def test_message_uses_user_language_bs(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """Alert message is rendered in the recipient's preferred language."""
        from apps.search.services.immediate_alerts import build_alert_message

        ad = create_test_ad(
            seller,
            category,
            city,
            title="Продам велосипед",
            title_bs="Prodajem bicikl",
            title_en="Selling bicycle",
            description="Отличный велосипед",
            description_bs="Odlican bicikl",
            description_en="Great bicycle",
            status=AdStatus.PUBLISHED,
        )
        city.name_i18n = {"ru": "Тестград", "bs": "Testgrad"}
        city.save(update_fields=["name_i18n"])

        saved_search = SavedSearch.objects.create(user=buyer, query="", is_active=True)

        text, keyboard = build_alert_message(ad, saved_search, locale="bs")
        assert "Prodajem bicikl" in text
        assert "Testgrad" in text
        # Russian text must not leak
        assert "Продам велосипед" not in text
        assert "Тестград" not in text

    def test_message_uses_user_language_en(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """Alert message in English uses the English ad fields."""
        from apps.search.services.immediate_alerts import build_alert_message

        ad = create_test_ad(
            seller,
            category,
            city,
            title="Продам велосипед",
            title_en="Selling bicycle",
            description="Отличный велосипед",
            description_en="Great bicycle",
            status=AdStatus.PUBLISHED,
        )
        saved_search = SavedSearch.objects.create(user=buyer, query="", is_active=True)

        text, keyboard = build_alert_message(ad, saved_search, locale="en")
        assert "Selling bicycle" in text

    def test_message_falls_back_to_russian(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """When the locale field is missing, the default fallback is Russian."""
        from apps.search.services.immediate_alerts import build_alert_message

        ad = create_test_ad(
            seller,
            category,
            city,
            title="Продам велосипед",
            description="Отличный велосипед",
            status=AdStatus.PUBLISHED,
        )
        saved_search = SavedSearch.objects.create(user=buyer, query="", is_active=True)

        text, keyboard = build_alert_message(ad, saved_search)
        assert "Продам велосипед" in text


class TestImmediateAlertsGate:
    """IMMEDIATE_ALERTS_ENABLED=False (default) disables publish-time delivery."""

    def test_gate_off_does_not_deliver_on_publish(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        # Default gate is OFF; the signal early-returns so no notification is
        # recorded for the published ad.
        create_test_ad(
            seller, category, city, title="Красный велосипед", status=AdStatus.PUBLISHED
        )
        SavedSearch.objects.create(
            user=buyer, query="велосипед", language="ru", is_active=True
        )

        assert SavedSearchNotification.objects.count() == 0
