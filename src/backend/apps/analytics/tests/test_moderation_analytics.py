"""
Unit tests for ModerationAnalytics service functions (TASK_058).

Tests cover get_moderation_stats, get_pending_queue_size,
get_moderator_performance, and get_rejection_reasons.
Uses ``django.test.TestCase`` for DB-backed assertions.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.ads.models import Ad
from apps.analytics.models import AnalyticsEvent
from apps.analytics.services.moderation_analytics import (
    get_moderation_stats,
    get_moderator_performance,
    get_pending_queue_size,
    get_rejection_reasons,
)
from apps.categories.models import Category
from apps.core.enums import AdSource, AdStatus, AnalyticsEventType, ModeratorActionType
from apps.locations.models import City
from apps.moderation.models import ModeratorActionLog
from apps.users.models import User

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_moderator(telegram_id: int = 990020001, **overrides: object) -> User:
    """Create a User representing a moderator for analytics tests."""
    defaults: dict = {
        "telegram_id": telegram_id,
        "chat_id": telegram_id,
        "username": None,
        "password": "x",
    }
    defaults.update(overrides)
    return User.objects.create(**defaults)  # type: ignore[arg-type]


def _make_seller(telegram_id: int = 990020101, **overrides: object) -> User:
    """Create a User representing a seller for analytics tests."""
    defaults: dict = {
        "telegram_id": telegram_id,
        "chat_id": telegram_id,
        "username": None,
        "password": "x",
    }
    defaults.update(overrides)
    return User.objects.create(**defaults)  # type: ignore[arg-type]


def _make_category(slug: str = "mod-cat") -> Category:
    """Create a Category with sensible defaults."""
    return Category.objects.create(
        name="Mod Category",
        slug=slug,
    )


def _make_city(slug: str = "mod-city") -> City:
    """Create a City with sensible defaults."""
    return City.objects.create(
        country_code="ME",
        name="Mod City",
        region="Mod Region",
        slug=slug,
    )


def _make_ad(
    user: User,
    category: Category,
    city: City,
    *,
    title: str = "Mod Ad",
    status: AdStatus = AdStatus.PUBLISHED,
    **overrides: object,
) -> Ad:
    """Create an Ad with sensible defaults for moderation analytics tests."""
    defaults: dict = {
        "user": user,
        "title": title,
        "description": "Moderation analytics test description",
        "category": category,
        "city": city,
        "category_name": category.name,
        "status": status,
        "source": AdSource.TELEGRAM,
    }
    defaults.update(overrides)
    return Ad.objects.create(**defaults)  # type: ignore[arg-type]


def _make_moderation_event(
    ad: Ad,
    event_type: AnalyticsEventType,
    *,
    timestamp: timezone.datetime | None = None,
) -> AnalyticsEvent:
    """Create an AnalyticsEvent for moderation actions."""
    return AnalyticsEvent.objects.create(
        event_type=event_type,
        ad=ad,
        timestamp=timestamp or timezone.now(),
    )


def _make_action_log(
    ad: Ad,
    user: User,
    reason: str,
    action_type: ModeratorActionType = ModeratorActionType.REJECT,
    *,
    created_at: timezone.datetime | None = None,
) -> ModeratorActionLog:
    """Create a ModeratorActionLog entry for rejection reason tests."""
    return ModeratorActionLog.objects.create(
        ad=ad,
        user=user,
        action_type=action_type,
        reason=reason,
        created_at=created_at or timezone.now(),
    )


# ---------------------------------------------------------------------------
# Tests: get_moderation_stats
# ---------------------------------------------------------------------------


class TestGetModerationStats(TestCase):
    """Tests for aggregating moderation statistics."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create shared fixtures with a mix of moderation events."""
        cls.category = _make_category()
        cls.city = _make_city()
        cls.seller = _make_seller(telegram_id=990020201)
        cls.moderator = _make_moderator(telegram_id=990020202)

        now = timezone.now()

        # --- Ad A: approved ---
        cls.ad_approved = _make_ad(
            cls.seller,
            cls.category,
            cls.city,
            title="Approved Ad",
            status=AdStatus.PUBLISHED,
            published_by=cls.moderator,
            published_at=now - timedelta(hours=4),
            created_at=now - timedelta(hours=8),
        )
        _make_moderation_event(
            cls.ad_approved,
            AnalyticsEventType.MODERATION_APPROVED,
            timestamp=now - timedelta(hours=4),
        )

        # --- Ad B: rejected ---
        cls.ad_rejected = _make_ad(
            cls.seller,
            cls.category,
            cls.city,
            title="Rejected Ad",
            status=AdStatus.REJECTED,
            moderated_by=cls.moderator,
            rejected_at=now - timedelta(hours=2),
            created_at=now - timedelta(hours=6),
        )
        _make_moderation_event(
            cls.ad_rejected,
            AnalyticsEventType.MODERATION_REJECTED,
            timestamp=now - timedelta(hours=2),
        )

        # --- Ad C: flagged ---
        cls.ad_flagged = _make_ad(
            cls.seller,
            cls.category,
            cls.city,
            title="Flagged Ad",
            status=AdStatus.ON_MODERATION,
        )
        _make_moderation_event(
            cls.ad_flagged,
            AnalyticsEventType.MODERATION_FLAGGED,
            timestamp=now - timedelta(hours=1),
        )

        # --- Noise: non-moderation event ---
        _make_moderation_event(
            cls.ad_approved,
            AnalyticsEventType.AD_VIEWED,
            timestamp=now - timedelta(hours=1),
        )

        # --- Old event beyond default 30-day window ---
        _make_moderation_event(
            _make_ad(
                cls.seller,
                cls.category,
                cls.city,
                title="Old Ad",
                status=AdStatus.PUBLISHED,
                published_by=cls.moderator,
            ),
            AnalyticsEventType.MODERATION_APPROVED,
            timestamp=now - timedelta(days=60),
        )

    def test_returns_correct_counts(self) -> None:
        """get_moderation_stats returns correct approved/rejected/flagged counts."""
        stats = get_moderation_stats()
        self.assertEqual(stats["approved"], 1)
        self.assertEqual(stats["rejected"], 1)
        self.assertEqual(stats["flagged"], 1)

    def test_avg_time_to_moderate_computed(self) -> None:
        """avg_time_to_moderate is computed from ad creation to event timestamp."""
        stats = get_moderation_stats()
        # Approved ad: created_at = now-8h, event = now-4h => 4 hours = 4.0
        assert stats["avg_time_to_moderate"] is not None
        self.assertAlmostEqual(stats["avg_time_to_moderate"], 4.0, places=1)

    def test_days_parameter_filters_results(self) -> None:
        """A short time window excludes older events."""
        stats = get_moderation_stats(days=1)
        # All events are within the last 8 hours, so 1 day should include them
        self.assertEqual(stats["approved"], 1)
        self.assertEqual(stats["rejected"], 1)
        self.assertEqual(stats["flagged"], 1)

    def test_days_parameter_excludes_old_events(self) -> None:
        """Events older than the days parameter are excluded."""
        stats = get_moderation_stats(days=40)
        # Old approved event at 60 days should be excluded
        self.assertEqual(stats["approved"], 1)

    def test_no_events_returns_zeros(self) -> None:
        """When no moderation events exist, all counts are zero."""
        stats = get_moderation_stats(days=0)
        self.assertEqual(stats["approved"], 0)
        self.assertEqual(stats["rejected"], 0)
        self.assertEqual(stats["flagged"], 0)
        self.assertIsNone(stats["avg_time_to_moderate"])


# ---------------------------------------------------------------------------
# Tests: get_pending_queue_size
# ---------------------------------------------------------------------------


class TestGetPendingQueueSize(TestCase):
    """Tests for counting ads awaiting moderation."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.category = _make_category("pending-cat")
        cls.city = _make_city("pending-city")
        cls.seller = _make_seller(telegram_id=990020301)

        # 2 ads on moderation
        _make_ad(
            cls.seller,
            cls.category,
            cls.city,
            title="Pending 1",
            status=AdStatus.ON_MODERATION,
        )
        _make_ad(
            cls.seller,
            cls.category,
            cls.city,
            title="Pending 2",
            status=AdStatus.ON_MODERATION,
        )

        # Noise: ads in other statuses
        _make_ad(
            cls.seller,
            cls.category,
            cls.city,
            title="Published",
            status=AdStatus.PUBLISHED,
        )
        _make_ad(
            cls.seller,
            cls.category,
            cls.city,
            title="Draft",
            status=AdStatus.DRAFT,
        )
        _make_ad(
            cls.seller,
            cls.category,
            cls.city,
            title="Rejected",
            status=AdStatus.REJECTED,
        )

    def test_returns_pending_count(self) -> None:
        """get_pending_queue_size counts only ON_MODERATION ads."""
        size = get_pending_queue_size()
        self.assertEqual(size, 2)

    def test_empty_queue_returns_zero(self) -> None:
        """When no ads are ON_MODERATION, returns 0."""
        # Delete pending ads to force an empty state
        Ad.objects.filter(status=AdStatus.ON_MODERATION).delete()
        size = get_pending_queue_size()
        self.assertEqual(size, 0)


# ---------------------------------------------------------------------------
# Tests: get_moderator_performance
# ---------------------------------------------------------------------------


class TestGetModeratorPerformance(TestCase):
    """Tests for calculating per-moderator performance metrics."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.category = _make_category("perf-cat")
        cls.city = _make_city("perf-city")
        cls.seller = _make_seller(telegram_id=990020401)

        now = timezone.now()

        # --- Moderator A: 2 approvals, 1 rejection ---
        cls.moderator_a = _make_moderator(telegram_id=990020402)

        # Approval 1
        _make_ad(
            cls.seller,
            cls.category,
            cls.city,
            title="A-Approval-1",
            status=AdStatus.PUBLISHED,
            published_by=cls.moderator_a,
            published_at=now - timedelta(hours=5),
            created_at=now - timedelta(hours=10),
        )
        # Approval 2
        _make_ad(
            cls.seller,
            cls.category,
            cls.city,
            title="A-Approval-2",
            status=AdStatus.PUBLISHED,
            published_by=cls.moderator_a,
            published_at=now - timedelta(hours=3),
            created_at=now - timedelta(hours=9),
        )
        # Rejection
        _make_ad(
            cls.seller,
            cls.category,
            cls.city,
            title="A-Rejection",
            status=AdStatus.REJECTED,
            moderated_by=cls.moderator_a,
            rejected_at=now - timedelta(hours=1),
            created_at=now - timedelta(hours=4),
        )

        # --- Moderator B: 1 approval ---
        cls.moderator_b = _make_moderator(telegram_id=990020403)
        _make_ad(
            cls.seller,
            cls.category,
            cls.city,
            title="B-Approval",
            status=AdStatus.PUBLISHED,
            published_by=cls.moderator_b,
            published_at=now - timedelta(hours=2),
            created_at=now - timedelta(hours=6),
        )

    def test_returns_all_moderators(self) -> None:
        """All moderators with actions in the window appear in results."""
        perf = get_moderator_performance()
        mod_ids = {p["moderator_id"] for p in perf}
        assert self.moderator_a.id is not None
        assert self.moderator_b.id is not None
        self.assertIn(self.moderator_a.id, mod_ids)
        self.assertIn(self.moderator_b.id, mod_ids)

    def test_action_counts_correct(self) -> None:
        """Actions are correctly summed (approvals + rejections)."""
        perf = get_moderator_performance()
        assert self.moderator_a.id is not None
        a_stats = next(p for p in perf if p["moderator_id"] == self.moderator_a.id)
        self.assertEqual(a_stats["actions_taken"], 3)

        assert self.moderator_b.id is not None
        b_stats = next(p for p in perf if p["moderator_id"] == self.moderator_b.id)
        self.assertEqual(b_stats["actions_taken"], 1)

    def test_sorted_by_actions_descending(self) -> None:
        """Result is sorted by actions_taken descending."""
        perf = get_moderator_performance()
        counts = [p["actions_taken"] for p in perf]
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_avg_time_hours_computed(self) -> None:
        """Average time per action is computed in hours."""
        perf = get_moderator_performance()
        assert self.moderator_b.id is not None
        b_stats = next(p for p in perf if p["moderator_id"] == self.moderator_b.id)
        # Approval: created_at = now-6h, published_at = now-2h => 4 hours
        assert b_stats["avg_time_hours"] is not None
        self.assertAlmostEqual(b_stats["avg_time_hours"], 4.0, places=1)

    def test_no_actions_returns_empty_list(self) -> None:
        """When no moderator actions exist, returns an empty list."""
        perf = get_moderator_performance(days=0)
        self.assertEqual(perf, [])

    def test_old_actions_excluded_by_days(self) -> None:
        """Actions older than the days parameter are excluded."""
        old_cat = _make_category("old-perf-cat")
        old_city = _make_city("old-perf-city")
        old_mod = _make_moderator(telegram_id=990020404)
        old_seller = _make_seller(telegram_id=990020405)
        now = timezone.now()

        _make_ad(
            old_seller,
            old_cat,
            old_city,
            title="Old Action",
            status=AdStatus.PUBLISHED,
            published_by=old_mod,
            published_at=now - timedelta(days=50),
            created_at=now - timedelta(days=55),
        )

        # 30-day window should exclude this 50-day-old action
        perf = get_moderator_performance(days=30)
        assert old_mod.id is not None
        mod_ids = {p["moderator_id"] for p in perf}
        self.assertNotIn(old_mod.id, mod_ids)


# ---------------------------------------------------------------------------
# Tests: get_rejection_reasons
# ---------------------------------------------------------------------------


class TestGetRejectionReasons(TestCase):
    """Tests for aggregating rejection reasons."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.category = _make_category("reject-cat")
        cls.city = _make_city("reject-city")
        cls.moderator = _make_moderator(telegram_id=990020501)
        cls.seller = _make_seller(telegram_id=990020502)

        now = timezone.now()

        # --- Rejection reasons ---
        ad1 = _make_ad(
            cls.seller,
            cls.category,
            cls.city,
            title="Rej 1",
            status=AdStatus.REJECTED,
        )
        ad2 = _make_ad(
            cls.seller,
            cls.category,
            cls.city,
            title="Rej 2",
            status=AdStatus.REJECTED,
        )
        ad3 = _make_ad(
            cls.seller,
            cls.category,
            cls.city,
            title="Rej 3",
            status=AdStatus.REJECTED,
        )
        ad4 = _make_ad(
            cls.seller,
            cls.category,
            cls.city,
            title="Rej 4",
            status=AdStatus.REJECTED,
        )

        # 2x "spam", 1x "adult content", 1x "offensive"
        _make_action_log(ad1, cls.moderator, "spam", created_at=now - timedelta(days=1))
        _make_action_log(ad2, cls.moderator, "spam", created_at=now - timedelta(days=2))
        _make_action_log(ad3, cls.moderator, "adult content", created_at=now - timedelta(days=5))
        _make_action_log(ad4, cls.moderator, "offensive", created_at=now - timedelta(days=10))

        # --- Noise: non-REJECT action ---
        ad5 = _make_ad(
            cls.seller,
            cls.category,
            cls.city,
            title="Noise",
            status=AdStatus.REJECTED,
        )
        _make_action_log(
            ad5,
            cls.moderator,
            "ban reason",
            action_type=ModeratorActionType.BAN_ACCOUNT,
            created_at=now - timedelta(days=1),
        )

        # --- Old reason beyond 30-day window ---
        ad6 = _make_ad(
            cls.seller,
            cls.category,
            cls.city,
            title="Old Rej",
            status=AdStatus.REJECTED,
        )
        _make_action_log(
            ad6,
            cls.moderator,
            "very old",
            created_at=now - timedelta(days=60),
        )

    def test_returns_reason_counts(self) -> None:
        """Rejection reasons are aggregated with correct counts."""
        reasons = get_rejection_reasons()
        self.assertEqual(reasons["spam"], 2)
        self.assertEqual(reasons["adult content"], 1)
        self.assertEqual(reasons["offensive"], 1)

    def test_excludes_non_reject_actions(self) -> None:
        """Non-REJECT actions (e.g. BAN_ACCOUNT) are not counted."""
        reasons = get_rejection_reasons()
        self.assertNotIn("ban reason", reasons)

    def test_ordered_by_count_descending(self) -> None:
        """Results are sorted by count descending."""
        reasons = get_rejection_reasons()
        counts = list(reasons.values())
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_empty_when_no_rejections(self) -> None:
        """When no rejections exist, returns empty dict."""
        reasons = get_rejection_reasons(days=0)
        self.assertEqual(reasons, {})

    def test_days_parameter_excludes_old_reasons(self) -> None:
        """Reasons older than the days parameter are excluded."""
        reasons = get_rejection_reasons(days=40)
        # "very old" is at 60 days, so it should be excluded
        self.assertNotIn("very old", reasons)