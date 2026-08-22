"""
Unit tests for ModerationAnalytics service functions (TASK_058).

Tests cover get_moderation_stats, get_pending_queue_size,
get_moderator_performance, and get_rejection_reasons.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
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
from apps.core.enums import AdStatus, AnalyticsEventType, ModeratorActionType
from apps.locations.models import City
from apps.moderation.models import ModeratorActionLog
from apps.users.models import User

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_user(telegram_id: int = 990020001, **overrides: object) -> User:
    """Create a User with sensible defaults for analytics tests."""
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
    return Category.objects.create(name="Mod Category", slug=slug)


def _make_city(slug: str = "mod-city") -> City:
    """Create a City with sensible defaults."""
    return City.objects.create(
        country_code="ME",
        name="Mod City",
        region="Mod Region",
        slug=slug,
    )


def _make_moderator(telegram_id: int = 990020001, **overrides: object) -> User:
    """Create a User representing a moderator for analytics tests."""
    return _make_user(telegram_id=telegram_id, **overrides)


def _make_seller(telegram_id: int = 990020101, **overrides: object) -> User:
    """Create a User representing a seller for analytics tests."""
    return _make_user(telegram_id=telegram_id, **overrides)


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
    """Create a ModeratorActionLog entry for rejection reason tests.

    ``created_at`` is backdated via ``QuerySet.update()`` when supplied, because
    the field is ``auto_now_add=True`` and a value passed to ``.create()`` would
    otherwise be silently overwritten with the current instant.
    """
    log = ModeratorActionLog.objects.create(
        ad=ad,
        user=user,
        action_type=action_type,
        reason=reason,
    )
    if created_at is not None:
        ModeratorActionLog.objects.filter(id=log.id).update(created_at=created_at)
        log.refresh_from_db()
    return log


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def moderation_stats_data():
    """Create shared fixtures for moderation stats tests."""
    category = _make_category()
    city = _make_city()
    seller = _make_seller(telegram_id=990020201)
    moderator = _make_moderator(telegram_id=990020202)

    now = timezone.now()

    # Ad A: approved
    ad_approved = create_test_ad(
        seller, category, city, title="Approved Ad",
        status=AdStatus.PUBLISHED,
        published_by=moderator,
        published_at=now - timedelta(hours=4),
    )
    Ad.objects.filter(id=ad_approved.id).update(created_at=now - timedelta(hours=8))
    ad_approved.refresh_from_db()
    _make_moderation_event(
        ad_approved, AnalyticsEventType.MODERATION_APPROVED,
        timestamp=now - timedelta(hours=4),
    )

    # Ad B: rejected
    ad_rejected = create_test_ad(
        seller, category, city, title="Rejected Ad",
        status=AdStatus.REJECTED,
        moderated_by=moderator,
        rejected_at=now - timedelta(hours=2),
    )
    Ad.objects.filter(id=ad_rejected.id).update(created_at=now - timedelta(hours=6))
    ad_rejected.refresh_from_db()
    _make_moderation_event(
        ad_rejected, AnalyticsEventType.MODERATION_REJECTED,
        timestamp=now - timedelta(hours=2),
    )

    # Ad C: flagged
    ad_flagged = create_test_ad(
        seller, category, city, title="Flagged Ad", status=AdStatus.ON_MODERATION,
    )
    _make_moderation_event(
        ad_flagged, AnalyticsEventType.MODERATION_FLAGGED,
        timestamp=now - timedelta(hours=1),
    )

    # Noise: non-moderation event
    _make_moderation_event(
        ad_approved, AnalyticsEventType.AD_VIEWED,
        timestamp=now - timedelta(hours=1),
    )

    # Noise: old event beyond default 30-day window
    _make_moderation_event(
        create_test_ad(
            seller, category, city, title="Old Ad",
            status=AdStatus.PUBLISHED, published_by=moderator,
        ),
        AnalyticsEventType.MODERATION_APPROVED,
        timestamp=now - timedelta(days=60),
    )

    return {
        "category": category, "city": city,
        "seller": seller, "moderator": moderator,
        "ad_approved": ad_approved, "ad_rejected": ad_rejected,
        "ad_flagged": ad_flagged,
    }


@pytest.fixture
def pending_queue_data(seller, category, city):
    """Create ads for pending queue size tests."""
    seller_local = _make_seller(telegram_id=990020301)

    # 2 ads on moderation
    create_test_ad(seller_local, category, city, title="Pending 1", status=AdStatus.ON_MODERATION)
    create_test_ad(seller_local, category, city, title="Pending 2", status=AdStatus.ON_MODERATION)

    # Noise: ads in other statuses
    create_test_ad(seller_local, category, city, title="Published", status=AdStatus.PUBLISHED)
    create_test_ad(seller_local, category, city, title="Draft", status=AdStatus.DRAFT)
    create_test_ad(seller_local, category, city, title="Rejected", status=AdStatus.REJECTED)

    return {"seller": seller_local, "category": category, "city": city}


@pytest.fixture
def moderator_performance_data():
    """Create ads and events for moderator performance tests."""
    category = _make_category("perf-cat")
    city = _make_city("perf-city")
    seller = _make_seller(telegram_id=990020401)

    now = timezone.now()

    mod_a = _make_moderator(telegram_id=990020402)
    mod_b = _make_moderator(telegram_id=990020403)

    # Moderator A: 2 approvals, 1 rejection
    ad = create_test_ad(seller, category, city, title="A-Approval-1",
                        status=AdStatus.PUBLISHED, published_by=mod_a,
                        published_at=now - timedelta(hours=5))
    Ad.objects.filter(id=ad.id).update(created_at=now - timedelta(hours=10))
    ad.refresh_from_db()
    ad = create_test_ad(seller, category, city, title="A-Approval-2",
                        status=AdStatus.PUBLISHED, published_by=mod_a,
                        published_at=now - timedelta(hours=3))
    Ad.objects.filter(id=ad.id).update(created_at=now - timedelta(hours=9))
    ad.refresh_from_db()
    ad = create_test_ad(seller, category, city, title="A-Rejection",
                        status=AdStatus.REJECTED, moderated_by=mod_a,
                        rejected_at=now - timedelta(hours=1))
    Ad.objects.filter(id=ad.id).update(created_at=now - timedelta(hours=4))
    ad.refresh_from_db()

    # Moderator B: 1 approval
    ad = create_test_ad(seller, category, city, title="B-Approval",
                        status=AdStatus.PUBLISHED, published_by=mod_b,
                        published_at=now - timedelta(hours=2))
    Ad.objects.filter(id=ad.id).update(created_at=now - timedelta(hours=6))
    ad.refresh_from_db()

    return {
        "category": category, "city": city,
        "seller": seller, "mod_a": mod_a, "mod_b": mod_b,
    }


@pytest.fixture
def rejection_reasons_data():
    """Create ads and action logs for rejection reasons tests."""
    category = _make_category("reject-cat")
    city = _make_city("reject-city")
    moderator = _make_moderator(telegram_id=990020501)
    seller = _make_seller(telegram_id=990020502)

    now = timezone.now()

    ad1 = create_test_ad(seller, category, city, title="Rej 1", status=AdStatus.REJECTED)
    ad2 = create_test_ad(seller, category, city, title="Rej 2", status=AdStatus.REJECTED)
    ad3 = create_test_ad(seller, category, city, title="Rej 3", status=AdStatus.REJECTED)
    ad4 = create_test_ad(seller, category, city, title="Rej 4", status=AdStatus.REJECTED)

    # 2x "spam", 1x "adult content", 1x "offensive"
    _make_action_log(ad1, moderator, "spam", created_at=now - timedelta(days=1))
    _make_action_log(ad2, moderator, "spam", created_at=now - timedelta(days=2))
    _make_action_log(ad3, moderator, "adult content", created_at=now - timedelta(days=5))
    _make_action_log(ad4, moderator, "offensive", created_at=now - timedelta(days=10))

    # Noise: non-REJECT action
    ad5 = create_test_ad(seller, category, city, title="Noise", status=AdStatus.REJECTED)
    _make_action_log(
        ad5, moderator, "ban reason",
        action_type=ModeratorActionType.BAN_ACCOUNT,
        created_at=now - timedelta(days=1),
    )

    # Noise: old reason beyond 30-day window
    ad6 = create_test_ad(seller, category, city, title="Old Rej", status=AdStatus.REJECTED)
    _make_action_log(
        ad6, moderator, "very old", created_at=now - timedelta(days=60),
    )

    return {"category": category, "city": city, "moderator": moderator, "seller": seller}


# ---------------------------------------------------------------------------
# Tests: get_moderation_stats
# ---------------------------------------------------------------------------


class TestGetModerationStats:
    """Tests for aggregating moderation statistics."""

    def test_returns_correct_counts(self, moderation_stats_data) -> None:
        """get_moderation_stats returns correct approved/rejected/flagged counts."""
        stats = get_moderation_stats()
        assert stats["approved"] == 1
        assert stats["rejected"] == 1
        assert stats["flagged"] == 1

    def test_avg_time_to_moderate_computed(self, moderation_stats_data) -> None:
        """avg_time_to_moderate is computed from ad creation to event timestamp."""
        stats = get_moderation_stats()
        # Approved ad: created_at = now-8h, event = now-4h => 4 hours = 4.0
        assert stats["avg_time_to_moderate"] is not None
        assert abs(stats["avg_time_to_moderate"] - 4.0) < 0.1

    def test_days_parameter_filters_results(self, moderation_stats_data) -> None:
        """A short time window excludes older events."""
        stats = get_moderation_stats(days=1)
        # All events are within the last 8 hours, so 1 day should include them
        assert stats["approved"] == 1
        assert stats["rejected"] == 1
        assert stats["flagged"] == 1

    def test_days_parameter_excludes_old_events(self, moderation_stats_data) -> None:
        """Events older than the days parameter are excluded."""
        stats = get_moderation_stats(days=40)
        # Old approved event at 60 days should be excluded
        assert stats["approved"] == 1

    def test_no_events_returns_zeros(self) -> None:
        """When no moderation events exist, all counts are zero."""
        stats = get_moderation_stats(days=0)
        assert stats["approved"] == 0
        assert stats["rejected"] == 0
        assert stats["flagged"] == 0
        assert stats["avg_time_to_moderate"] is None


# ---------------------------------------------------------------------------
# Tests: get_pending_queue_size
# ---------------------------------------------------------------------------


class TestGetPendingQueueSize:
    """Tests for counting ads awaiting moderation."""

    def test_returns_pending_count(self, pending_queue_data) -> None:
        """get_pending_queue_size counts only ON_MODERATION ads."""
        size = get_pending_queue_size()
        assert size == 2

    def test_empty_queue_returns_zero(self, pending_queue_data) -> None:
        """When no ads are ON_MODERATION, returns 0."""
        # Delete pending ads to force an empty state
        Ad.objects.filter(status=AdStatus.ON_MODERATION).delete()
        size = get_pending_queue_size()
        assert size == 0


# ---------------------------------------------------------------------------
# Tests: get_moderator_performance
# ---------------------------------------------------------------------------


class TestGetModeratorPerformance:
    """Tests for calculating per-moderator performance metrics."""

    def test_returns_all_moderators(self, moderator_performance_data) -> None:
        """All moderators with actions in the window appear in results."""
        perf = get_moderator_performance()
        mod_ids = {p["moderator_id"] for p in perf}
        assert moderator_performance_data["mod_a"].id is not None
        assert moderator_performance_data["mod_b"].id is not None
        assert moderator_performance_data["mod_a"].id in mod_ids
        assert moderator_performance_data["mod_b"].id in mod_ids

    def test_action_counts_correct(self, moderator_performance_data) -> None:
        """Actions are correctly summed (approvals + rejections)."""
        perf = get_moderator_performance()
        mod_a = moderator_performance_data["mod_a"]
        assert mod_a.id is not None
        a_stats = next(p for p in perf if p["moderator_id"] == mod_a.id)
        assert a_stats["actions_taken"] == 3

        mod_b = moderator_performance_data["mod_b"]
        assert mod_b.id is not None
        b_stats = next(p for p in perf if p["moderator_id"] == mod_b.id)
        assert b_stats["actions_taken"] == 1

    def test_sorted_by_actions_descending(self, moderator_performance_data) -> None:
        """Result is sorted by actions_taken descending."""
        perf = get_moderator_performance()
        counts = [p["actions_taken"] for p in perf]
        assert counts == sorted(counts, reverse=True)

    def test_avg_time_hours_computed(self, moderator_performance_data) -> None:
        """Average time per action is computed in hours."""
        perf = get_moderator_performance()
        mod_b = moderator_performance_data["mod_b"]
        assert mod_b.id is not None
        b_stats = next(p for p in perf if p["moderator_id"] == mod_b.id)
        # Approval: created_at = now-6h, published_at = now-2h => 4 hours
        assert b_stats["avg_time_hours"] is not None
        assert abs(b_stats["avg_time_hours"] - 4.0) < 0.1

    def test_no_actions_returns_empty_list(self) -> None:
        """When no moderator actions exist, returns an empty list."""
        perf = get_moderator_performance(days=0)
        assert perf == []

    def test_old_actions_excluded_by_days(self, moderator_performance_data) -> None:
        """Actions older than the days parameter are excluded."""
        old_cat = _make_category("old-perf-cat")
        old_city = _make_city("old-perf-city")
        old_mod = _make_moderator(telegram_id=990020404)
        old_seller = _make_seller(telegram_id=990020405)
        now = timezone.now()

        ad = create_test_ad(
            old_seller, old_cat, old_city, title="Old Action",
            status=AdStatus.PUBLISHED, published_by=old_mod,
            published_at=now - timedelta(days=50),
        )
        Ad.objects.filter(id=ad.id).update(created_at=now - timedelta(days=55))
        ad.refresh_from_db()

        # 30-day window should exclude this 50-day-old action
        perf = get_moderator_performance(days=30)
        assert old_mod.id is not None
        mod_ids = {p["moderator_id"] for p in perf}
        assert old_mod.id not in mod_ids


# ---------------------------------------------------------------------------
# Tests: get_rejection_reasons
# ---------------------------------------------------------------------------


class TestGetRejectionReasons:
    """Tests for aggregating rejection reasons."""

    def test_returns_reason_counts(self, rejection_reasons_data) -> None:
        """Rejection reasons are aggregated with correct counts."""
        reasons = get_rejection_reasons()
        assert reasons["spam"] == 2
        assert reasons["adult content"] == 1
        assert reasons["offensive"] == 1

    def test_excludes_non_reject_actions(self, rejection_reasons_data) -> None:
        """Non-REJECT actions (e.g. BAN_ACCOUNT) are not counted."""
        reasons = get_rejection_reasons()
        assert "ban reason" not in reasons

    def test_ordered_by_count_descending(self, rejection_reasons_data) -> None:
        """Results are sorted by count descending."""
        reasons = get_rejection_reasons()
        counts = list(reasons.values())
        assert counts == sorted(counts, reverse=True)

    def test_empty_when_no_rejections(self) -> None:
        """When no rejections exist, returns empty dict."""
        reasons = get_rejection_reasons(days=0)
        assert reasons == {}

    def test_days_parameter_excludes_old_reasons(self, rejection_reasons_data) -> None:
        """Reasons older than the days parameter are excluded."""
        reasons = get_rejection_reasons(days=40)
        # "very old" is at 60 days, so it should be excluded
        assert "very old" not in reasons
