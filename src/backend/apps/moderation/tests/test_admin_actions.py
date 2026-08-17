"""
Unit tests for moderation admin actions (AD-001).

Verifies that approve_ad, reject_ad, and soft_delete_ad route all status
changes through the state machine (transition_to / set_published /
set_rejected) instead of direct field assignment. Also validates the
transition matrix edges introduced by the fix: ON_MODERATION_FAILED ->
REJECTED, and that PUBLISHED/ARCHIVED -> REJECTED raises ValueError.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from apps.moderation.admin_actions import (
    approve_ad,
    reject_ad,
    soft_delete_ad,
)
from apps.users.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def seller() -> User:
    """Create a seller user for ad fixtures."""
    return User.objects.create(
        telegram_id=900000100,
        chat_id=900000100,
        password="x",
    )


@pytest.fixture
def category():
    """Create a leaf category for ad fixtures."""
    from apps.categories.models import Category

    return Category.objects.create(
        name="Test Category",
        slug="test-category",
    )


@pytest.fixture
def city():
    """Create a city for ad fixtures."""
    from apps.locations.models import City

    return City.objects.create(
        country_code="ME",
        name="Test City",
        region="Test Region",
        slug="test-city",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------



def _set_status_timestamp(data, now=None):
    """Auto-populate timestamp fields matching the ad status."""
    from django.utils import timezone
    from apps.core.enums import AdStatus
    if now is None:
        now = timezone.now()
    status = data.get("status")
    if status == AdStatus.PUBLISHED:
        data.setdefault("published_at", now)
        data.setdefault("original_published_at", now)
    elif status == AdStatus.ARCHIVED:
        data.setdefault("archived_at", now)
        data.setdefault("published_at", now)
        data.setdefault("original_published_at", now)
    elif status == AdStatus.REJECTED:
        data.setdefault("rejected_at", now)
    elif status == AdStatus.ON_MODERATION_FAILED:
        data.setdefault("moderation_failed_at", now)
    elif status == AdStatus.DELETED:
        data.setdefault("deleted_at", now)
    return data
def _make_ad(
    seller: User,
    category,
    city,
    *,
    status: AdStatus = AdStatus.DRAFT,
    **kwargs,
) -> Ad:
    """Create an Ad with the given status, setting the matching timestamp.

    Each terminal/lifecycle status that has a dedicated timestamp constraint
    requires that timestamp be populated on INSERT. This helper ensures test
    data is constraint-consistent.
    """
    defaults: dict = {
        "user": seller,
        "title": "Test Ad",
        "description": "Test description for moderation",
        "category": category,
        "city": city,
        "category_name": category.name,
        "status": status,
    }
    defaults.update(kwargs)

    now = timezone.now()
    if status == AdStatus.PUBLISHED:
        defaults.setdefault("published_at", now)
        defaults.setdefault("original_published_at", now)
    elif status == AdStatus.ARCHIVED:
        defaults.setdefault("archived_at", now)
        defaults.setdefault("published_at", now)
        defaults.setdefault("original_published_at", now)
    elif status == AdStatus.REJECTED:
        defaults.setdefault("rejected_at", now)
    elif status == AdStatus.ON_MODERATION_FAILED:
        defaults.setdefault("moderation_failed_at", now)
    elif status == AdStatus.DELETED:
        defaults.setdefault("deleted_at", now)

    return Ad.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Tests: approve_ad routing
# ---------------------------------------------------------------------------


class TestApproveAdRouting:
    """Verify approve_ad delegates to set_published, not direct assignment."""

    @patch("apps.moderation.admin_actions.set_published")
    def test_approve_ad_routes_through_set_published(self, mock_set_published, seller, category, city):
        """approve_ad calls set_published() instead of assigning fields directly."""
        ad = _make_ad(seller, category, city, status=AdStatus.ON_MODERATION)
        moderator = User.objects.create(telegram_id=900000204, chat_id=900000204, password="x")
        approve_ad(ad, moderator.id)

        mock_set_published.assert_called_once_with(ad, moderator_id=moderator.id)
        # The ad must NOT have been transitioned by the old code path
        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION

    def test_approve_ad_only_from_moderation(self, seller, category, city):
        """approve_ad is a no-op when the ad is not in ON_MODERATION."""
        ad = _make_ad(seller, category, city, status=AdStatus.DRAFT)
        moderator = User.objects.create(telegram_id=900000205, chat_id=900000205, password="x")
        with patch("apps.moderation.admin_actions.set_published") as mock_set:
            approve_ad(ad, moderator.id)
            mock_set.assert_not_called()

        ad.refresh_from_db()
        assert ad.status == AdStatus.DRAFT


# ---------------------------------------------------------------------------
# Tests: reject_ad routing and matrix
# ---------------------------------------------------------------------------


class TestRejectAdRouting:
    """Verify reject_ad delegates to set_rejected and respects the matrix."""

    @patch("apps.moderation.admin_actions.set_rejected")
    def test_reject_ad_routes_through_set_rejected(self, mock_set_rejected, seller, category, city):
        """reject_ad calls set_rejected() instead of assigning fields directly."""
        ad = _make_ad(seller, category, city, status=AdStatus.ON_MODERATION)
        moderator_id = seller.id + 100

        reject_ad(ad, moderator_id, "spam content")

        mock_set_rejected.assert_called_once_with(
            ad, moderator_id=moderator_id, reason="spam content"
        )
        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION

    def test_reject_ad_from_moderation_succeeds(self, seller, category, city):
        """reject_ad transitions ON_MODERATION -> REJECTED."""
        ad = _make_ad(seller, category, city, status=AdStatus.ON_MODERATION)
        moderator = User.objects.create(telegram_id=900000200, chat_id=900000200, password="x")
        reject_ad(ad, moderator.id, "policy violation")

        ad.refresh_from_db()
        assert ad.status == AdStatus.REJECTED
        assert ad.rejected_at is not None
        assert ad.moderated_by_id == moderator.id

    def test_reject_ad_from_moderation_failed_succeeds(self, seller, category, city):
        """reject_ad transitions ON_MODERATION_FAILED -> REJECTED (new matrix edge)."""
        ad = _make_ad(seller, category, city, status=AdStatus.ON_MODERATION_FAILED)
        moderator = User.objects.create(telegram_id=900000201, chat_id=900000201, password="x")
        reject_ad(ad, moderator.id, "manual review")

        ad.refresh_from_db()
        assert ad.status == AdStatus.REJECTED
        assert ad.rejected_at is not None
        assert ad.moderated_by_id == moderator.id
        # ON_MODERATION_FAILED timestamp must be cleared (mutually exclusive)
        assert ad.moderation_failed_at is None

    def test_reject_ad_from_published_raises(self, seller, category, city):
        """reject_ad on PUBLISHED raises ValueError (forbidden transition)."""
        ad = _make_ad(seller, category, city, status=AdStatus.PUBLISHED)
        moderator = User.objects.create(telegram_id=900000202, chat_id=900000202, password="x")
        with pytest.raises(ValueError, match="Invalid transition"):
            reject_ad(ad, moderator.id, "not allowed")

        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED

    def test_reject_ad_from_archived_raises(self, seller, category, city):
        """reject_ad on ARCHIVED raises ValueError (forbidden transition)."""
        ad = _make_ad(seller, category, city, status=AdStatus.ARCHIVED)
        moderator = User.objects.create(telegram_id=900000203, chat_id=900000203, password="x")
        with pytest.raises(ValueError, match="Invalid transition"):
            reject_ad(ad, moderator.id, "not allowed")

        ad.refresh_from_db()
        assert ad.status == AdStatus.ARCHIVED

    def test_reject_ad_already_rejected_noop(self, seller, category, city):
        """reject_ad on REJECTED is a no-op."""
        ad = _make_ad(seller, category, city, status=AdStatus.REJECTED)
        original_rejected_at = ad.rejected_at

        with patch("apps.moderation.admin_actions.set_rejected") as mock_set:
            reject_ad(ad, seller.id, "not allowed")
            mock_set.assert_not_called()

        ad.refresh_from_db()
        assert ad.status == AdStatus.REJECTED
        assert ad.rejected_at == original_rejected_at


# ---------------------------------------------------------------------------
# Tests: soft_delete_ad routing
# ---------------------------------------------------------------------------


class TestSoftDeleteAdRouting:
    """Verify soft_delete_ad routes through transition_to(DELETED)."""

    def test_soft_delete_ad_routes_through_transition_to(self, seller, category, city):
        """soft_delete_ad calls ad.transition_to(DELETED), not direct assignment."""
        ad = _make_ad(seller, category, city, status=AdStatus.DRAFT)
        moderator = User.objects.create(telegram_id=900000206, chat_id=900000206, password="x")

        with patch.object(Ad, "transition_to", wraps=ad.transition_to) as spy:
            soft_delete_ad(ad, moderator.id, "spam")
            spy.assert_called_once()
            # Verify the target status argument
            args, kwargs = spy.call_args
            assert args[0] == AdStatus.DELETED

        ad.refresh_from_db()
        assert ad.status == AdStatus.DELETED
        assert ad.deleted_at is not None

    @pytest.mark.parametrize("start_status", [AdStatus.DRAFT, AdStatus.ON_MODERATION])
    def test_soft_delete_any_active_state(self, seller, category, city, start_status):
        """soft_delete_ad transitions DRAFT/ON_MODERATION/PUBLISHED -> DELETED."""
        ad = _make_ad(seller, category, city, status=start_status)
        moderator = User.objects.create(telegram_id=900000207, chat_id=900000207, password="x")

        soft_delete_ad(ad, moderator.id, "policy violation")

        ad.refresh_from_db()
        assert ad.status == AdStatus.DELETED
        assert ad.deleted_at is not None
