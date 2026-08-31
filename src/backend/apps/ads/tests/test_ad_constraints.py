"""
Comprehensive tests for Ad model ``CheckConstraint`` rules.

Covers all 6 ``CheckConstraint`` definitions in ``Ad.Meta``:
  1. ``ck_ads_published_at_if_published``
  2. ``ck_ads_archived_at_if_archived``
  3. ``ck_ads_rejected_at_if_rejected``
  4. ``ck_ads_moderation_failed_at_if_failed``
  5. ``ck_ads_deleted_at_if_deleted``
  6. ``ck_ads_failed_and_rejected_mutually_exclusive``

Each test creates a valid DRAFT ad, then uses ``Ad.objects.filter().update()``
inside ``transaction.atomic()`` to bypass model ``save()`` and trigger the
database-level constraint.  A rollback verifies the original row is untouched.

Complements the 3 constraint tests in ``test_ad_lifecycle.py`` with the
remaining 3 + additional mutual-exclusivity paths.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from apps.users.models import User

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]

# Maps an AdStatus to the timestamp field the DB constraint requires.
_STATUS_TIMESTAMP: dict[AdStatus, str] = {
    AdStatus.PUBLISHED: "published_at",
    AdStatus.ARCHIVED: "archived_at",
    AdStatus.REJECTED: "rejected_at",
    AdStatus.ON_MODERATION_FAILED: "moderation_failed_at",
    AdStatus.DELETED: "deleted_at",
}


# ---------------------------------------------------------------------------
# Individual status-timestamp constraints (G-01)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "timestamp_field"),
    list(_STATUS_TIMESTAMP.items()),
    ids=[s.value for s in _STATUS_TIMESTAMP],
)
class TestStatusTimestampConstraints:
    """Each lifecycle status with a dedicated timestamp is constraint-guarded."""

    def test_bulk_update_to_status_without_timestamp_raises(
        self,
        seller: User,
        category,
        city,
        status: AdStatus,
        timestamp_field: str,
    ) -> None:
        """Bulk-updating to *status* without its required timestamp raises IntegrityError."""
        ad = create_test_ad(
            seller, category, city, status=AdStatus.DRAFT, title=f"Draft for {status}"
        )

        update_data: dict[str, object] = {"status": status.value}
        # Clear any other timestamp that might be set, but NOT the one we're testing.
        for f in _STATUS_TIMESTAMP.values():
            if f != timestamp_field:
                update_data[f] = None

        with pytest.raises(IntegrityError):
            with transaction.atomic():  # type: ignore[reportGeneralTypeIssues]
                Ad.objects.filter(id=ad.id).update(**update_data)

        ad.refresh_from_db()
        assert ad.status == AdStatus.DRAFT
        assert getattr(ad, timestamp_field) is None

    def test_bulk_update_to_status_with_timestamp_succeeds(
        self,
        seller: User,
        category,
        city,
        status: AdStatus,
        timestamp_field: str,
    ) -> None:
        """Bulk-updating to *status* WITH the required timestamp succeeds."""
        ad = create_test_ad(
            seller, category, city, status=AdStatus.DRAFT, title=f"Draft for {status}"
        )

        update_data: dict[str, object] = {
            "status": status.value,
            timestamp_field: timezone.now(),
        }

        Ad.objects.filter(id=ad.id).update(**update_data)

        ad.refresh_from_db()
        assert ad.status == status
        assert getattr(ad, timestamp_field) is not None


# ---------------------------------------------------------------------------
# Mutual-exclusivity constraint (G-01)
# ---------------------------------------------------------------------------


class TestMutualExclusivityConstraint:
    """``ck_ads_failed_and_rejected_mutually_exclusive`` — only one may be set."""

    def test_set_both_failed_and_rejected_raises(
        self, seller: User, category, city
    ) -> None:
        """Setting both ``moderation_failed_at`` and ``rejected_at`` raises."""
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)

        now = timezone.now()
        with pytest.raises(IntegrityError):
            with transaction.atomic():  # type: ignore[reportGeneralTypeIssues]
                Ad.objects.filter(id=ad.id).update(
                    moderation_failed_at=now,
                    rejected_at=now,
                )

        ad.refresh_from_db()
        assert ad.moderation_failed_at is None
        assert ad.rejected_at is None

    def test_add_rejected_to_failed_raises(self, seller: User, category, city) -> None:
        """Adding ``rejected_at`` to a row already having ``moderation_failed_at`` raises."""
        ad = create_test_ad(
            seller, category, city, status=AdStatus.ON_MODERATION_FAILED
        )
        ad.refresh_from_db()
        assert ad.moderation_failed_at is not None

        with pytest.raises(IntegrityError):
            with transaction.atomic():  # type: ignore[reportGeneralTypeIssues]
                Ad.objects.filter(id=ad.id).update(rejected_at=timezone.now())

        ad.refresh_from_db()
        assert ad.rejected_at is None

    def test_add_failed_to_rejected_raises(self, seller: User, category, city) -> None:
        """Adding ``moderation_failed_at`` to a row already having ``rejected_at`` raises."""
        ad = create_test_ad(seller, category, city, status=AdStatus.REJECTED)
        ad.refresh_from_db()
        assert ad.rejected_at is not None

        with pytest.raises(IntegrityError):
            with transaction.atomic():  # type: ignore[reportGeneralTypeIssues]
                Ad.objects.filter(id=ad.id).update(moderation_failed_at=timezone.now())

        ad.refresh_from_db()
        assert ad.moderation_failed_at is None

    def test_only_failed_satisfies_constraint(
        self, seller: User, category, city
    ) -> None:
        """A row with only ``moderation_failed_at`` set (no ``rejected_at``) is valid."""
        ad = create_test_ad(
            seller, category, city, status=AdStatus.ON_MODERATION_FAILED
        )
        ad.refresh_from_db()
        assert ad.moderation_failed_at is not None
        assert ad.rejected_at is None

    def test_only_rejected_satisfies_constraint(
        self, seller: User, category, city
    ) -> None:
        """A row with only ``rejected_at`` set (no ``moderation_failed_at``) is valid."""
        ad = create_test_ad(seller, category, city, status=AdStatus.REJECTED)
        ad.refresh_from_db()
        assert ad.rejected_at is not None
        assert ad.moderation_failed_at is None
