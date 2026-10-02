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

Also includes a concurrency test
(``test_transition_after_concurrent_hard_delete_raises``) verifying that
``transition_to`` raises ``Ad.DoesNotExist`` when a concurrent hard-delete
removes the row between fetch and refresh.
"""

from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.ads.models import Ad, AdImage
from apps.core.enums import AdStatus
from apps.users.models import User
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

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
# Reactivation clears archived_at (AD-011)
# ---------------------------------------------------------------------------


class TestReactivationClearsArchivedAt:
    """``ARCHIVED -> PUBLISHED`` must persist ``archived_at = None``."""

    def test_reactivation_clears_archived_at(self, seller: User, category, city) -> None:
        """Reactivating an archived ad stores a NULL ``archived_at``.

        ``ck_ads_archived_at_if_archived`` is one-directional
        (``~Q(status=ARCHIVED) | Q(archived_at__isnull=False)``): the database
        accepts a PUBLISHED row carrying a stale ``archived_at``, so there is
        no DB-level guard. This test is the guard — and it re-reads the row to
        prove the value reached the database; an in-memory assertion on
        ``ad.archived_at`` passes even when ``update_fields`` omits the field.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        ad.transition_to(AdStatus.ARCHIVED)
        ad.refresh_from_db()
        assert ad.archived_at is not None

        ad.transition_to(AdStatus.PUBLISHED)

        # A second, independent fetch — not refresh_from_db() on the same object.
        reloaded = Ad.objects.get(pk=ad.pk)
        assert reloaded.status == AdStatus.PUBLISHED
        assert reloaded.archived_at is None


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


def test_transition_after_concurrent_hard_delete_raises(seller, category, city):
    """DB-003: refresh_from_db in transition_to must raise DoesNotExist
    if a concurrent sweep hard-deleted the row between fetch and transition."""
    ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
    # Simulate a concurrent hard-delete sweep removing the row
    with transaction.atomic():  # type: ignore[reportGeneralTypeIssues]
        Ad.objects.filter(pk=ad.id).delete()
    # transition_to should now raise Ad.DoesNotExist via refresh_from_db
    with pytest.raises(Ad.DoesNotExist):
        ad.transition_to(AdStatus.ON_MODERATION)


# ---------------------------------------------------------------------------
# AdImage (ad, position) uniqueness (AD-014)
# ---------------------------------------------------------------------------


class TestAdImagePositionUniqueness:
    """``uq_ad_images_ad_position`` rejects duplicate positions within an ad.

    Contiguity is intentionally *not* enforced: positions may contain gaps
    (the shipped ``test_copy_ad_image_positions_preserved`` asserts ``[0, 2, 5]``
    survives a copy). Only exact duplicates on the same ad are illegal.
    """

    def test_duplicate_position_same_ad_raises(self, seller, category, city) -> None:
        """Two images for the same ad at the same position raise IntegrityError."""
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
        AdImage.objects.create(
            ad=ad, image=f"{uuid.uuid4().hex}.jpg", position=0
        )

        with pytest.raises(IntegrityError):
            with transaction.atomic():  # type: ignore[reportGeneralTypeIssues]
                AdImage.objects.create(
                    ad=ad, image=f"{uuid.uuid4().hex}.jpg", position=0
                )

    def test_same_position_different_ads_allowed(
        self, seller, user, category, city
    ) -> None:
        """Position is unique per ad, not globally: a different ad may reuse it."""
        ad_one = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        ad_two = create_test_ad(user, category, city, status=AdStatus.PUBLISHED)

        AdImage.objects.create(
            ad=ad_one, image=f"{uuid.uuid4().hex}.jpg", position=0
        )
        AdImage.objects.create(
            ad=ad_two, image=f"{uuid.uuid4().hex}.jpg", position=0
        )

        assert AdImage.objects.filter(position=0).count() == 2
