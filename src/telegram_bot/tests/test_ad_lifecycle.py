"""
Ad lifecycle transition tests (TST-002).

Tests the core DRAFT -> PUBLISHED and DRAFT -> ON_MODERATION_FAILED transitions
via the shared auto_moderate service, asserting immutability of original_published_at.

All tests use the real ORM with monkeypatched criteria to avoid DB cache coupling.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.ads.models import Ad, AdImage
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.moderation.services.auto_moderation import auto_moderate
from apps.users.models import User
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_draft_ad(seller: User, category: Category, city: City, **kwargs) -> Ad:
    """Create an Ad in DRAFT status with required FK fields."""
    defaults: dict = {
        "title": "Valid Title",
        "description": "Valid description text for the ad.",
        "status": AdStatus.DRAFT,
    }
    defaults.update(kwargs)
    return create_test_ad(seller, category, city, **defaults)


def _transition_to_moderation(ad: Ad) -> None:
    """Transition a DRAFT ad to ON_MODERATION."""
    ad.transition_to(AdStatus.ON_MODERATION)


def _publish_ad(ad: Ad) -> None:
    """Directly transition an ON_MODERATION ad to PUBLISHED (bypasses auto_moderate)."""
    ad.transition_to(AdStatus.PUBLISHED)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDraftCreation:
    """Ad creation in DRAFT status."""

    def test_create_draft_sets_initial_status(self, seller, category, city):
        """A newly created ad has DRAFT status."""
        ad = _make_draft_ad(seller, category, city)
        assert ad.status == AdStatus.DRAFT

    def test_create_draft_has_no_publish_timestamps(self, seller, category, city):
        """A draft ad has no published_at or original_published_at."""
        ad = _make_draft_ad(seller, category, city)
        ad.refresh_from_db()
        assert ad.published_at is None
        assert ad.original_published_at is None


class TestDraftToPublished:
    """DRAFT -> ON_MODERATION -> PUBLISHED via auto_moderate."""

    def test_auto_moderate_publishes_valid_ad(
        self, seller, category, city, permissive_criteria
    ):
        """A valid ad transitions DRAFT -> ON_MODERATION -> PUBLISHED via auto_moderate."""
        # Arrange: create draft ad and transition to ON_MODERATION
        ad = _make_draft_ad(seller, category, city)
        _transition_to_moderation(ad)
        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION

        # Act: run auto-moderation
        result = auto_moderate(ad)

        # Assert: ad is published
        assert result is True
        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED

    def test_auto_moderate_sets_published_at(
        self, seller, category, city, permissive_criteria
    ):
        """published_at is set on successful auto-moderation."""
        ad = _make_draft_ad(seller, category, city)
        _transition_to_moderation(ad)
        ad.refresh_from_db()

        auto_moderate(ad)
        ad.refresh_from_db()

        assert ad.published_at is not None

    def test_auto_moderate_sets_original_published_at_first_publish(
        self, seller, category, city, permissive_criteria
    ):
        """original_published_at is set on first publish via auto_moderate."""
        ad = _make_draft_ad(seller, category, city)
        _transition_to_moderation(ad)
        ad.refresh_from_db()

        auto_moderate(ad)
        ad.refresh_from_db()

        assert ad.original_published_at is not None
        # On first publish, both timestamps are equal
        assert ad.original_published_at == ad.published_at


class TestDraftToModerationFailed:
    """DRAFT -> ON_MODERATION -> ON_MODERATION_FAILED via auto_moderate."""

    def test_auto_moderate_fails_banned_word(
        self, seller, category, city, banning_criteria
    ):
        """Ad with banned word transitions to ON_MODERATION_FAILED."""
        ad = _make_draft_ad(seller, category, city, title="Spammy offer")
        _transition_to_moderation(ad)
        ad.refresh_from_db()

        result = auto_moderate(ad)

        assert result is False
        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION_FAILED

    def test_auto_moderate_fail_sets_moderation_failed_at(
        self, seller, category, city, banning_criteria
    ):
        """moderation_failed_at is set on failed auto-moderation."""
        ad = _make_draft_ad(seller, category, city, title="Spammy offer")
        _transition_to_moderation(ad)
        ad.refresh_from_db()

        auto_moderate(ad)
        ad.refresh_from_db()

        assert ad.moderation_failed_at is not None

    def test_auto_moderate_fail_does_not_set_publish_timestamps(
        self, seller, category, city, banning_criteria
    ):
        """Failed auto-moderation does NOT set published_at or original_published_at."""
        ad = _make_draft_ad(seller, category, city, title="Spammy offer")
        _transition_to_moderation(ad)
        ad.refresh_from_db()

        auto_moderate(ad)
        ad.refresh_from_db()

        assert ad.published_at is None
        assert ad.original_published_at is None


class TestOriginalPublishedAtImmutability:
    """original_published_at must never change after first publish."""

    def test_original_published_at_immutable_on_re_publish(
        self, seller, category, city, permissive_criteria
    ):
        """original_published_at stays the same on re-publish after archive."""
        ad = _make_draft_ad(seller, category, city)
        _transition_to_moderation(ad)
        ad.refresh_from_db()

        # First publish
        auto_moderate(ad)
        ad.refresh_from_db()
        original_first = ad.original_published_at

        # Archive the ad
        ad.transition_to(AdStatus.ARCHIVED)
        ad.refresh_from_db()
        assert ad.status == AdStatus.ARCHIVED

        # Re-publish from ARCHIVED
        ad.transition_to(AdStatus.PUBLISHED)
        ad.refresh_from_db()

        # original_published_at must be unchanged
        assert ad.original_published_at == original_first
        # published_at must have been updated
        assert ad.published_at > original_first

    def test_original_published_at_immutable_on_second_moderation_cycle(
        self, seller, category, city, permissive_criteria
    ):
        """original_published_at survives a full DRAFT->PUBLISHED->ARCHIVED->PUBLISHED cycle."""
        ad = _make_draft_ad(seller, category, city)
        _transition_to_moderation(ad)
        ad.refresh_from_db()

        # First publish
        auto_moderate(ad)
        ad.refresh_from_db()
        original_first = ad.original_published_at

        # Full cycle: ARCHIVED -> ON_MODERATION -> PUBLISHED
        ad.transition_to(AdStatus.ARCHIVED)
        ad.refresh_from_db()

        ad.transition_to(AdStatus.ON_MODERATION)
        ad.refresh_from_db()

        auto_moderate(ad)
        ad.refresh_from_db()

        # original_published_at must be unchanged
        assert ad.original_published_at == original_first
        # published_at must have been updated
        assert ad.published_at > original_first


class TestPublishedAtUpdates:
    """published_at is updated on every PUBLISHED transition."""

    def test_published_at_updates_on_re_publish(
        self, seller, category, city, permissive_criteria
    ):
        """published_at is refreshed on each PUBLISHED transition."""
        ad = _make_draft_ad(seller, category, city)
        _transition_to_moderation(ad)
        ad.refresh_from_db()

        # First publish
        auto_moderate(ad)
        ad.refresh_from_db()

        # Backdate the first publish's timestamps so the re-publish timestamp
        # is deterministically later — no wall-clock pause needed.
        now = timezone.now()
        Ad.objects.filter(pk=ad.pk).update(
            published_at=now - timedelta(seconds=10),
            original_published_at=now - timedelta(seconds=10),
        )
        ad.refresh_from_db()
        first_published = ad.published_at

        # Archive and re-publish
        ad.transition_to(AdStatus.ARCHIVED)
        ad.refresh_from_db()
        ad.transition_to(AdStatus.PUBLISHED)
        ad.refresh_from_db()

        assert ad.published_at > first_published


class TestTransitionValidation:
    """Direct transition_to validation (not via auto_moderate)."""

    def test_invalid_transition_raises_error(self, seller, category, city):
        """DRAFT -> PUBLISHED (skipping ON_MODERATION) raises ValueError."""
        ad = _make_draft_ad(seller, category, city)
        with pytest.raises(ValueError, match="Invalid transition"):
            ad.transition_to(AdStatus.PUBLISHED)

    def test_terminal_state_blocks_transition(self, seller, category, city):
        """DELETED is a terminal state; no transitions allowed from it."""
        ad = _make_draft_ad(seller, category, city)
        ad.transition_to(AdStatus.DELETED)
        ad.refresh_from_db()
        assert ad.status == AdStatus.DELETED

        # Attempting any transition from DELETED should raise
        with pytest.raises(ValueError, match="Cannot transition from DELETED"):
            ad.transition_to(AdStatus.PUBLISHED)

    def test_valid_draft_to_on_moderation_succeeds(self, seller, category, city):
        """DRAFT -> ON_MODERATION is a valid transition."""
        ad = _make_draft_ad(seller, category, city)
        ad.transition_to(AdStatus.ON_MODERATION)
        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION


class TestAutoModerateIntegration:
    """Integration-level tests for auto_moderate with real DB objects."""

    def test_auto_moderate_with_images_passes(
        self, seller, category, city, permissive_criteria
    ):
        """auto_moderate passes when ad has images and meets criteria."""
        ad = _make_draft_ad(seller, category, city)
        _transition_to_moderation(ad)
        ad.refresh_from_db()

        # Add an image (not strictly required since min_images=0, but test real path)
        AdImage.objects.create(ad=ad, image="test-key-001.jpg")

        result = auto_moderate(ad)
        assert result is True
        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED

    def test_auto_moderate_creates_analytics_event(
        self, seller, category, city, permissive_criteria
    ):
        """A successful auto_moderate creates an AnalyticsEvent."""
        from apps.analytics.models import AnalyticsEvent

        ad = _make_draft_ad(seller, category, city)
        _transition_to_moderation(ad)
        ad.refresh_from_db()

        auto_moderate(ad)

        event_count = AnalyticsEvent.objects.filter(
            user_id=ad.user_id,
        ).count()
        assert event_count >= 1

    def test_auto_moderate_fail_creates_moderation_log(
        self, seller, category, city, banning_criteria
    ):
        """A failed auto_moderate creates a ModeratorActionLog entry."""
        from apps.moderation.models import ModeratorActionLog

        ad = _make_draft_ad(seller, category, city, title="Spammy offer")
        _transition_to_moderation(ad)
        ad.refresh_from_db()

        auto_moderate(ad)

        log_count = ModeratorActionLog.objects.filter(
            ad_id=ad.id,
        ).count()
        assert log_count >= 1
