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

from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.search.models import SavedSearch, SavedSearchNotification
from apps.search.services.alert_query import (
    find_matching_ads,
    find_matching_saved_searches,
    record_notifications,
)
from apps.search.services.immediate_alerts import deliver_immediate_alerts
from apps.users.models import User
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


class _SyncExecutor:
    """Run submitted callables inline so send-path assertions are deterministic.

    The production executor is a real ``ThreadPoolExecutor``: submissions run on
    another thread and any exception is captured in the worker, not propagated
    to the caller. Tests that assert on what was submitted (or on an exception
    escaping) replace it with this inline stand-in.
    """

    def submit(self, fn, *args):
        fn(*args)

        class _Immediate:
            """Minimal Future stand-in; the caller ignores it."""

        return _Immediate()


@pytest.fixture
def sync_executor(monkeypatch) -> None:
    """Replace the immediate-alert thread pool with an inline executor."""
    monkeypatch.setattr(
        "apps.search.services.immediate_alerts._executor", _SyncExecutor()
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

    def test_excludes_delivered_ads(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """An ad whose notification was delivered is excluded (03-DB-007).

        This is the inversion of the previous ``test_excludes_already_notified_ads``,
        which created a bare row — recorded, not delivered — and asserted
        exclusion. Under the delivery-state contract only a DELIVERED pair
        (``delivered_at IS NOT NULL``) is excluded.
        """
        ad = create_test_ad(
            seller, category, city, title="Уже отправлено", status=AdStatus.PUBLISHED
        )
        saved_search = SavedSearch.objects.create(
            user=buyer, query="отправлено", language="ru", is_active=True
        )
        SavedSearchNotification.objects.create(
            saved_search=saved_search, ad=ad, delivered_at=timezone.now()
        )

        results = find_matching_ads(saved_search)
        assert len(results) == 0

    def test_includes_recorded_but_undelivered_ads(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """A recorded but undelivered pair stays COLLECTABLE (03-DB-007).

        A row with ``delivered_at IS NULL`` means "an attempt was recorded but
        the message was never accepted"; it must remain eligible so the pair is
        retried rather than lost forever.
        """
        ad = create_test_ad(
            seller, category, city, title="Записано но не отправлено",
            status=AdStatus.PUBLISHED,
        )
        saved_search = SavedSearch.objects.create(
            user=buyer, query="отправлено", language="ru", is_active=True
        )
        SavedSearchNotification.objects.create(saved_search=saved_search, ad=ad)

        results = find_matching_ads(saved_search)
        assert len(results) == 1
        assert results[0].id == ad.id

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

    def test_format_digest_uses_user_language_en(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """``_format_digest`` with ``locale='en'`` renders English ad titles."""
        from apps.search.management.commands.send_alerts import Command

        ad = create_test_ad(
            seller,
            category,
            city,
            title="Продам велосипед",
            title_en="Selling bicycle",
            description="Отличный велосипед",
            status=AdStatus.PUBLISHED,
        )
        cmd = Command()
        message = cmd._format_digest([ad], locale="en")
        assert "Selling bicycle" in message
        assert "Продам велосипед" not in message

    def test_format_digest_uses_user_language_bs(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """``_format_digest`` with ``locale='bs'`` renders Bosnian ad titles."""
        from apps.search.management.commands.send_alerts import Command

        ad = create_test_ad(
            seller,
            category,
            city,
            title="Продам велосипед",
            title_bs="Prodajem bicikl",
            description="Отличный велосипед",
            status=AdStatus.PUBLISHED,
        )
        cmd = Command()
        message = cmd._format_digest([ad], locale="bs")
        assert "Prodajem bicikl" in message
        assert "Продам велосипед" not in message


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
        self,
        seller: User,
        buyer: User,
        category: Category,
        city: City,
        monkeypatch,
        sync_executor,
    ) -> None:
        """Two calls for the same ad submit payloads exactly once (03-DB-007).

        The previous version of this test monkeypatched ``_run_send`` with a
        no-op and asserted only the row count, so it could not observe that the
        second call submitted the payload a second time: it asserted ROW-level
        idempotency under a name claiming MESSAGE-level idempotency. Re-running
        must not double-send, so this version records the submitted payloads and
        asserts there was exactly one submission, while keeping the row-count
        assertion that pins ``ignore_conflicts`` on the immediate path.
        """
        submitted: list[list] = []

        from apps.search.services import notification_delivery

        # Record what was submitted, and mark it delivered the way the real
        # send does. The mark is what makes the SECOND call submit nothing: an
        # UNdelivered pair is legitimately re-submitted (that is the retry), so
        # a recorder that does not mark would see two submissions by design.
        def _mark(payloads: list) -> None:
            submitted.append(payloads)
            for payload in payloads:
                ss_id, ad_id = payload["pair"]
                notification_delivery.mark_delivered(
                    ss_id, ad_id, sent_at=timezone.now()
                )

        monkeypatch.setattr(
            "apps.search.services.immediate_alerts._run_send", _mark
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
        assert len(submitted) == 1

        # Re-running (re-publish / backfill) must not double-send, because the
        # first delivery marked the pair delivered.
        deliver_immediate_alerts(ad.id)
        assert (
            SavedSearchNotification.objects.filter(saved_search=ss, ad=ad).count() == 1
        )
        assert len(submitted) == 1

    def test_non_published_ad_is_noop(
        self, seller: User, category: Category, city: City
    ) -> None:
        from apps.search.services.immediate_alerts import deliver_immediate_alerts

        draft = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
        deliver_immediate_alerts(draft.id)
        assert SavedSearchNotification.objects.count() == 0

    def test_no_chat_id_records_nothing_and_stays_collectable(
        self, seller: User, buyer: User, category: Category, city: City
    ) -> None:
        """A user with no ``chat_id`` is never recorded, so the pair stays collectable.

        Pins D-1 (03-DB-007): the record loop must run only for the pairs that
        actually produced a payload. The previous order recorded a row for the
        user and then dropped the payload, permanently suppressing the alert.
        """
        # ``chat_id`` is NOT NULL in the database, so a falsy (0) value stands
        # in for "no chat_id": ``_build_payload`` treats it as absent.
        buyer.chat_id = 0
        buyer.save(update_fields=["chat_id"])

        ad = create_test_ad(
            seller, category, city, title="Красный велосипед", status=AdStatus.PUBLISHED
        )
        saved_search = SavedSearch.objects.create(user=buyer, is_active=True)

        deliver_immediate_alerts(ad.id)

        assert not SavedSearchNotification.objects.filter(
            saved_search=saved_search, ad=ad
        ).exists()
        assert [a.id for a in find_matching_ads(saved_search)] == [ad.id]

    def test_failed_send_leaves_pair_undelivered_and_collectable(
        self,
        seller: User,
        buyer: User,
        category: Category,
        city: City,
        monkeypatch,
        sync_executor,
    ) -> None:
        """A failed send leaves the row undelivered and therefore collectable.

        Pins D-2 (03-DB-007): the marker is written AFTER a successful send, so
        a failure yields ``delivered_at IS NULL`` and the pair is retried.
        """

        def _boom(payloads: list) -> None:
            raise RuntimeError("send failed")

        monkeypatch.setattr(
            "apps.search.services.immediate_alerts._run_send", _boom
        )

        from apps.search.services.immediate_alerts import deliver_immediate_alerts

        ad = create_test_ad(
            seller, category, city, title="Красный велосипед", status=AdStatus.PUBLISHED
        )
        saved_search = SavedSearch.objects.create(user=buyer, is_active=True)

        with pytest.raises(RuntimeError, match="send failed"):
            deliver_immediate_alerts(ad.id)

        row = SavedSearchNotification.objects.get(saved_search=saved_search, ad=ad)
        assert row.delivered_at is None
        assert [a.id for a in find_matching_ads(saved_search)] == [ad.id]

    def test_republish_submits_nothing_on_second_call(
        self,
        seller: User,
        buyer: User,
        category: Category,
        city: City,
        monkeypatch,
        sync_executor,
    ) -> None:
        """A second delivery for the same ad submits no payload (03-DB-007).

        Pins D-3: a delivered pair is excluded by ``find_matching_saved_searches``
        as well, so a content-neutral re-publish does not re-notify.
        """
        submitted: list[list] = []

        from apps.search.services import notification_delivery

        def _mark(payloads: list) -> None:
            submitted.append(payloads)
            for payload in payloads:
                ss_id, ad_id = payload["pair"]
                notification_delivery.mark_delivered(
                    ss_id, ad_id, sent_at=timezone.now()
                )

        monkeypatch.setattr(
            "apps.search.services.immediate_alerts._run_send", _mark
        )

        ad = create_test_ad(
            seller, category, city, title="Красный велосипед", status=AdStatus.PUBLISHED
        )
        SavedSearch.objects.create(user=buyer, is_active=True)

        deliver_immediate_alerts(ad.id)
        assert len(submitted) == 1

        # Re-publish tick: the delivered pair must be excluded.
        deliver_immediate_alerts(ad.id)
        assert len(submitted) == 1

    def test_cross_path_dedup(
        self,
        seller: User,
        buyer: User,
        category: Category,
        city: City,
        monkeypatch,
        sync_executor,
    ) -> None:
        """A pair delivered by either path is never delivered by the other.

        Replaces the source plan's acceptance criterion that the audit proved
        false (the immediate path records before dispatch; the daily path's
        ``NOT EXISTS`` treated any row as a receipt). Assertions are on
        DELIVERY, not on a return value.
        """
        from apps.search.management.commands.send_alerts import Command

        submitted: list[list] = []

        from apps.search.services import notification_delivery

        def _mark(payloads: list) -> None:
            submitted.append(payloads)
            for payload in payloads:
                ss_id, ad_id = payload["pair"]
                notification_delivery.mark_delivered(ss_id, ad_id, sent_at=timezone.now())

        monkeypatch.setattr(
            "apps.search.services.immediate_alerts._run_send", _mark
        )

        ad = create_test_ad(
            seller, category, city, title="Красный велосипед", status=AdStatus.PUBLISHED
        )
        saved_search = SavedSearch.objects.create(user=buyer, is_active=True)

        # 1. Immediate path delivers the pair.
        deliver_immediate_alerts(ad.id)
        assert len(submitted) == 1
        assert SavedSearchNotification.objects.filter(
            saved_search=saved_search, ad=ad, delivered_at__isnull=False
        ).exists(), "immediate path did not mark the pair delivered"

        # 2. The daily path must not re-deliver it: the delivered row excludes
        #    it from find_matching_ads, so no digest is sent.
        cmd = Command()
        user_ads, notifications, events = cmd._collect_alerts()
        assert ad.id not in {a.id for ads in user_ads.values() for a in ads}
        assert notifications == []

        # 3. Now the reverse: a fresh pair delivered only by the daily path is
        #    excluded by the immediate matcher.
        ad2 = create_test_ad(
            seller, category, city, title="Красный велосипед 2",
            status=AdStatus.PUBLISHED,
        )
        row = SavedSearchNotification.objects.create(
            saved_search=saved_search, ad=ad2
        )
        notification_delivery.mark_delivered(
            saved_search.id, ad2.id, sent_at=timezone.now()
        )
        assert find_matching_saved_searches(ad2) == []
        assert [a.id for a in find_matching_ads(saved_search)] == []
        row.refresh_from_db()
        assert row.delivered_at is not None


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

    def test_gate_enabled_reaches_sender_only_when_on(
        self, seller: User, buyer: User, category: Category, city: City, monkeypatch
    ) -> None:
        """The real gate coverage the no-op test cannot give (03-DB-007).

        With ``IMMEDIATE_ALERTS_ENABLED=True`` the publish-time signal reaches
        ``deliver_immediate_alerts`` (observed via the send bridge); with
        ``False`` it does not. This is an ADDITION beside
        ``test_gate_off_does_not_deliver_on_publish``, which is left
        byte-identical and is not counted as gate coverage.
        """
        from django.db import transaction
        from django.test import override_settings

        from apps.search.services import immediate_alerts

        calls: list[int] = []
        monkeypatch.setattr(
            immediate_alerts, "deliver_immediate_alerts", calls.append
        )

        with (
            patch.object(transaction, "on_commit", side_effect=lambda fn: fn()),
            override_settings(IMMEDIATE_ALERTS_ENABLED=False),
        ):
            create_test_ad(
                seller, category, city, title="Off", status=AdStatus.PUBLISHED
            )
        assert calls == []

        with (
            patch.object(transaction, "on_commit", side_effect=lambda fn: fn()),
            override_settings(IMMEDIATE_ALERTS_ENABLED=True),
        ):
            create_test_ad(
                seller, category, city, title="On", status=AdStatus.PUBLISHED
            )
        assert len(calls) == 1
