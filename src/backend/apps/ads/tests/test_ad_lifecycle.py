"""
Ad lifecycle transition tests (AD-001).

Tests the Ad.transition_to() state machine directly, including:
- Transition matrix validation (valid and invalid transitions)
- ON_MODERATION_FAILED -> REJECTED (new matrix edge)
- ARCHIVED -> REJECTED (forbidden)

All tests use the real ORM against PostgreSQL.
"""

from __future__ import annotations

import pytest

from apps.core.enums import AdStatus
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Tests: transition_to validation (existing — kept as-is)
# ---------------------------------------------------------------------------


class TestTransitionValidation:
    """Direct transition_to validation (not via auto_moderate)."""

    def test_invalid_transition_raises_error(self, seller, category, city):
        """DRAFT -> PUBLISHED (skipping ON_MODERATION) raises ValueError."""
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
        with pytest.raises(ValueError, match="Invalid transition"):
            ad.transition_to(AdStatus.PUBLISHED)

    def test_terminal_state_blocks_transition(self, seller, category, city):
        """DELETED is a terminal state; no transitions allowed from it."""
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
        ad.transition_to(AdStatus.DELETED)
        ad.refresh_from_db()
        assert ad.status == AdStatus.DELETED

        # Attempting any transition from DELETED should raise
        with pytest.raises(ValueError, match="Cannot transition from DELETED"):
            ad.transition_to(AdStatus.PUBLISHED)

    def test_valid_draft_to_on_moderation_succeeds(self, seller, category, city):
        """DRAFT -> ON_MODERATION is a valid transition."""
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
        ad.transition_to(AdStatus.ON_MODERATION)
        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION


# ---------------------------------------------------------------------------
# Tests: transition_to matrix edges (new)
# ---------------------------------------------------------------------------


class TestTransitionMatrixEdges:
    """Additional transition_to matrix coverage (AD-001 fix)."""

    def test_transition_to_reject_from_moderation_failed_succeeds(
        self, seller, category, city
    ):
        """ON_MODERATION_FAILED -> REJECTED is allowed (new matrix edge)."""
        ad = create_test_ad(
            seller, category, city, status=AdStatus.ON_MODERATION_FAILED
        )
        ad.transition_to(AdStatus.REJECTED)
        ad.refresh_from_db()

        assert ad.status == AdStatus.REJECTED
        assert ad.rejected_at is not None
        # moderation_failed_at must be cleared (mutually exclusive)
        assert ad.moderation_failed_at is None

    def test_transition_to_reject_from_archived_raises(self, seller, category, city):
        """ARCHIVED -> REJECTED raises ValueError (not in matrix)."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ARCHIVED)

        with pytest.raises(ValueError, match="Invalid transition"):
            ad.transition_to(AdStatus.REJECTED)

        ad.refresh_from_db()
        assert ad.status == AdStatus.ARCHIVED


# ---------------------------------------------------------------------------
# Tests: DRAFT creation defaults (mirrors bot-only TestDraftCreation)
# ---------------------------------------------------------------------------


class TestDraftCreationDefaults:
    """DRAFT status invariants: no publish timestamps (AD-001 parity)."""

    def test_create_draft_sets_initial_status(self, seller, category, city):
        """A newly created ad has DRAFT status."""
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
        assert ad.status == AdStatus.DRAFT

    def test_create_draft_has_no_publish_timestamps(self, seller, category, city):
        """A draft ad has no published_at or original_published_at."""
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
        ad.refresh_from_db()
        assert ad.published_at is None
        assert ad.original_published_at is None


# ---------------------------------------------------------------------------
# Tests: original_published_at immutability (mirrors bot TestOriginalPublishedAtImmutability)
# ---------------------------------------------------------------------------


class TestOriginalPublishedAtImmutability:
    """original_published_at must never change after first publish (AD-001 parity)."""

    def test_original_published_at_immutable_on_re_publish(
        self, seller, category, city
    ):
        """original_published_at survives a PUBLISHED -> ARCHIVED -> PUBLISHED cycle."""
        # DRAFT -> ON_MODERATION -> PUBLISHED -> ARCHIVED -> PUBLISHED
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
        ad.transition_to(AdStatus.ON_MODERATION)
        ad.refresh_from_db()
        ad.transition_to(AdStatus.PUBLISHED)
        ad.refresh_from_db()
        first = ad.original_published_at

        ad.transition_to(AdStatus.ARCHIVED)
        ad.refresh_from_db()
        ad.transition_to(AdStatus.PUBLISHED)
        ad.refresh_from_db()

        assert ad.original_published_at == first
        assert ad.published_at > first

    def test_original_published_at_immutable_on_second_moderation_cycle(
        self, seller, category, city
    ):
        """original_published_at survives DRAFT->ON_MODERATION->PUBLISHED->ARCHIVED->ON_MODERATION->PUBLISHED."""
        # Full cycle DRAFT -> ON_MODERATION -> PUBLISHED -> ARCHIVED -> ON_MODER -> PUBLISHED
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
        ad.transition_to(AdStatus.ON_MODERATION)
        ad.refresh_from_db()
        ad.transition_to(AdStatus.PUBLISHED)
        ad.refresh_from_db()
        first = ad.original_published_at

        ad.transition_to(AdStatus.ARCHIVED)
        ad.refresh_from_db()
        ad.transition_to(AdStatus.ON_MODERATION)
        ad.refresh_from_db()
        ad.transition_to(AdStatus.PUBLISHED)
        ad.refresh_from_db()

        assert ad.original_published_at == first
        assert ad.published_at > first


# ---------------------------------------------------------------------------
# Tests: published_at updates on every PUBLISHED transition
# ---------------------------------------------------------------------------


class TestPublishedAtUpdates:
    """published_at is updated on every PUBLISHED transition (AD-001 parity)."""

    def test_published_at_updates_on_re_publish(self, seller, category, city):
        """published_at is refreshed on each PUBLISHED transition."""
        # DRAFT -> ON_MODERATION -> PUBLISHED -> ARCHIVED -> PUBLISHED
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
        ad.transition_to(AdStatus.ON_MODERATION)
        ad.refresh_from_db()
        ad.transition_to(AdStatus.PUBLISHED)
        ad.refresh_from_db()
        first = ad.published_at

        ad.transition_to(AdStatus.ARCHIVED)
        ad.refresh_from_db()
        ad.transition_to(AdStatus.PUBLISHED)
        ad.refresh_from_db()

        assert ad.published_at > first
