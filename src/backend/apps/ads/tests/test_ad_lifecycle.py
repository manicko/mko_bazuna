"""
Ad lifecycle transition tests (AD-001).

Tests the Ad.transition_to() state machine directly, including:
- Transition matrix validation (valid and invalid transitions)
- ON_MODERATION_FAILED -> REJECTED (new matrix edge)
- ARCHIVED -> REJECTED (forbidden)
- CheckConstraints enforcing status-timestamp consistency

All tests use the real ORM against PostgreSQL.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils import timezone
import pytest

from apps.ads.models import Ad
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
# Tests: CheckConstraints (new)
# ---------------------------------------------------------------------------


class TestCheckConstraints:
    """Verify database-level CheckConstraints on the ads table."""

    def test_checkconstraint_published_requires_published_at(
        self, seller, category, city
    ):
        """Bulk-update to PUBLISHED without published_at raises IntegrityError."""
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)

        with pytest.raises(IntegrityError):
            with transaction.atomic():  # type: ignore[reportGeneralTypeIssues]
                Ad.objects.filter(id=ad.id).update(status=AdStatus.PUBLISHED)

        # Original row must be untouched (savepoint rollback)
        ad.refresh_from_db()
        assert ad.status == AdStatus.DRAFT

    def test_checkconstraint_archived_requires_archived_at(
        self, seller, category, city
    ):
        """Bulk-update to ARCHIVED without archived_at raises IntegrityError."""
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)

        with pytest.raises(IntegrityError):
            with transaction.atomic():  # type: ignore[reportGeneralTypeIssues]
                Ad.objects.filter(id=ad.id).update(status=AdStatus.ARCHIVED)

        ad.refresh_from_db()
        assert ad.status == AdStatus.DRAFT

    def test_checkconstraint_mutual_exclusivity(self, seller, category, city):
        """Setting both moderation_failed_at and rejected_at raises IntegrityError."""
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)

        with pytest.raises(IntegrityError):
            with transaction.atomic():  # type: ignore[reportGeneralTypeIssues]
                Ad.objects.filter(id=ad.id).update(
                    moderation_failed_at=timezone.now(),
                    rejected_at=timezone.now(),
                )

        ad.refresh_from_db()
        assert ad.moderation_failed_at is None
        assert ad.rejected_at is None
