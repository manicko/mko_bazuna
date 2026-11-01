"""
Service-tier tests for ``apps.ads.services.lifecycle`` (S4.1).

The HTML action flows (``ad_archive`` / ``ad_reactivate`` / ``ad_delete``) are
proven byte-identical by the untouched pre-existing suites
(``apps/ads/tests/test_edit.py`` — ``TestAdArchive``,
``TestAdReactivateDirect``, ``TestBannedSellerRelistNowRefused``,
``TestSellerWebStorageConsentGate`` — and ``apps/ads/tests/test_delete.py``).
This module covers the service itself, so a future API caller inherits the
same proofs:

- happy path per transition: resulting status, the timestamps
  ``Ad.transition_to`` / ``auto_moderate`` set, and the analytics rows the
  moderation pipeline records,
- precondition refusals: missing ad (``Http404``), non-owner
  (``PermissionDenied``), wrong status (silent no-op, row untouched),
- the reactivation rollback: a failing check leaves the ad ARCHIVED,
- the consent boundary: the service is gate-free (the gate is caller-side).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.exceptions import PermissionDenied
from django.http import Http404

from apps.ads.models import Ad
from apps.ads.services.lifecycle import (
    ArchiveResult,
    DeleteResult,
    ReactivateResult,
    archive_ad,
    delete_ad,
    reactivate_ad,
)
from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AdStatus, AnalyticsEventType
from conftest import create_test_ad, make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _event_types(ad: Ad) -> list[str]:
    """Analytics event types recorded for *ad*, as plain strings."""
    return list(
        AnalyticsEvent.objects.filter(ad_id=ad.id)
        .order_by("id")
        .values_list("event_type", flat=True)
    )


# ---------------------------------------------------------------------------
# archive_ad
# ---------------------------------------------------------------------------


class TestArchiveAd:
    """``archive_ad`` — ``PUBLISHED -> ARCHIVED`` with ownership + lock."""

    def test_published_ad_is_archived_with_archived_at(
        self, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        result = archive_ad(ad.id, seller.id)

        assert result == ArchiveResult(archived=True)
        ad.refresh_from_db()
        assert ad.status == AdStatus.ARCHIVED
        assert ad.archived_at is not None
        assert ad.published_at is not None  # untouched by the archive

    def test_archive_records_no_analytics_event(
        self, seller, category, city
    ) -> None:
        """Archiving is a bare transition — it emits no analytics row."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        archive_ad(ad.id, seller.id)

        assert _event_types(ad) == []

    @pytest.mark.parametrize(
        "status",
        [
            AdStatus.DRAFT,
            AdStatus.ON_MODERATION,
            AdStatus.REJECTED,
            AdStatus.ON_MODERATION_FAILED,
            AdStatus.ARCHIVED,
            AdStatus.DELETED,
        ],
    )
    def test_non_published_ad_is_silent_noop(
        self, seller, category, city, status
    ) -> None:
        ad = create_test_ad(seller, category, city, status=status)

        result = archive_ad(ad.id, seller.id)

        assert result == ArchiveResult(archived=False)
        ad.refresh_from_db()
        assert ad.status == status

    def test_non_owner_is_refused_and_ad_unchanged(
        self, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        other = make_user(910000101)

        with pytest.raises(PermissionDenied):
            archive_ad(ad.id, other.id)

        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED
        assert ad.archived_at is None

    def test_missing_ad_raises_http404(self, seller) -> None:
        with pytest.raises(Http404):
            archive_ad(999_999_999, seller.id)

    def test_consent_gate_is_caller_side(self, category, city) -> None:
        """The service never reads consent: a never-consented owner succeeds.

        The HTML view refuses such an owner before calling in
        (``TestSellerWebStorageConsentGate``); the service must not duplicate
        the gate, so API callers assert theirs at their own boundary.
        """
        owner = make_user(910000102, consent_given_at=None)
        ad = create_test_ad(owner, category, city, status=AdStatus.PUBLISHED)

        result = archive_ad(ad.id, owner.id)

        assert result.archived is True
        ad.refresh_from_db()
        assert ad.status == AdStatus.ARCHIVED


# ---------------------------------------------------------------------------
# reactivate_ad
# ---------------------------------------------------------------------------


class TestReactivateAd:
    """``reactivate_ad`` — ``ARCHIVED -> ON_MODERATION -> verdict``."""

    @pytest.fixture
    def archived_ad(self, seller, category, city) -> Ad:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        ad.transition_to(AdStatus.ARCHIVED)
        ad.refresh_from_db()
        assert ad.status == AdStatus.ARCHIVED
        return ad

    def test_passing_check_publishes_and_records_events(
        self, seller, archived_ad, permissive_criteria
    ) -> None:
        result = reactivate_ad(archived_ad.id, seller.id)

        assert result == ReactivateResult(attempted=True, passed=True)
        archived_ad.refresh_from_db()
        assert archived_ad.status == AdStatus.PUBLISHED
        assert archived_ad.archived_at is None  # cleared by -> ON_MODERATION
        assert archived_ad.published_at is not None
        # auto_moderate's pass path records exactly these two rows.
        assert _event_types(archived_ad) == [
            AnalyticsEventType.AD_PUBLISHED,
            AnalyticsEventType.MODERATION_APPROVED,
        ]

    def test_failing_check_commits_on_moderation_failed(
        self, seller, archived_ad, banning_criteria
    ) -> None:
        Ad.objects.filter(pk=archived_ad.pk).update(title="spam offer")

        result = reactivate_ad(archived_ad.id, seller.id)

        assert result == ReactivateResult(attempted=True, passed=False)
        archived_ad.refresh_from_db()
        assert archived_ad.status == AdStatus.ON_MODERATION_FAILED
        assert archived_ad.moderation_failed_at is not None
        assert archived_ad.archived_at is None
        assert _event_types(archived_ad) == [AnalyticsEventType.MODERATION_REJECTED]

    def test_check_error_rolls_back_to_archived(
        self, seller, archived_ad
    ) -> None:
        """A non-database failure of the check leaves the ad ARCHIVED."""
        with (
            patch(
                "apps.ads.services.lifecycle.auto_moderation.auto_moderate",
                side_effect=RuntimeError("boom"),
            ),
            pytest.raises(RuntimeError),
        ):
            reactivate_ad(archived_ad.id, seller.id)

        archived_ad.refresh_from_db()
        assert archived_ad.status == AdStatus.ARCHIVED
        assert archived_ad.archived_at is not None

    @pytest.mark.parametrize(
        "status",
        [
            AdStatus.DRAFT,
            AdStatus.ON_MODERATION,
            AdStatus.PUBLISHED,
            AdStatus.REJECTED,
            AdStatus.ON_MODERATION_FAILED,
            AdStatus.DELETED,
        ],
    )
    def test_non_archived_ad_is_silent_noop(
        self, seller, category, city, status
    ) -> None:
        ad = create_test_ad(seller, category, city, status=status)

        result = reactivate_ad(ad.id, seller.id)

        assert result == ReactivateResult(attempted=False, passed=None)
        ad.refresh_from_db()
        assert ad.status == status
        assert _event_types(ad) == []

    def test_non_owner_is_refused_and_ad_unchanged(
        self, seller, archived_ad, permissive_criteria
    ) -> None:
        other = make_user(910000103)

        with pytest.raises(PermissionDenied):
            reactivate_ad(archived_ad.id, other.id)

        archived_ad.refresh_from_db()
        assert archived_ad.status == AdStatus.ARCHIVED
        assert _event_types(archived_ad) == []

    def test_missing_ad_raises_http404(self, seller) -> None:
        with pytest.raises(Http404):
            reactivate_ad(999_999_999, seller.id)


# ---------------------------------------------------------------------------
# delete_ad
# ---------------------------------------------------------------------------


class TestDeleteAd:
    """``delete_ad`` — gate-free soft delete to DELETED."""

    @pytest.mark.parametrize(
        "status",
        [
            AdStatus.DRAFT,
            AdStatus.PUBLISHED,
            AdStatus.ARCHIVED,
            AdStatus.REJECTED,
            AdStatus.ON_MODERATION_FAILED,
        ],
    )
    def test_any_status_transitions_to_deleted(
        self, seller, category, city, status
    ) -> None:
        ad = create_test_ad(seller, category, city, status=status)

        result = delete_ad(ad.id, seller.id)

        assert result == DeleteResult(deleted=True)
        ad.refresh_from_db()
        assert ad.status == AdStatus.DELETED
        assert ad.deleted_at is not None

    def test_already_deleted_is_noop(self, seller, category, city) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.DELETED)
        deleted_at_before = ad.deleted_at

        result = delete_ad(ad.id, seller.id)

        assert result == DeleteResult(deleted=False)
        ad.refresh_from_db()
        assert ad.status == AdStatus.DELETED
        assert ad.deleted_at == deleted_at_before

    def test_non_owner_is_refused_and_ad_unchanged(
        self, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        other = make_user(910000104)

        with pytest.raises(PermissionDenied):
            delete_ad(ad.id, other.id)

        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED
        assert ad.deleted_at is None

    def test_missing_ad_raises_http404(self, seller) -> None:
        with pytest.raises(Http404):
            delete_ad(999_999_999, seller.id)

    def test_consent_gate_is_caller_side(self, category, city) -> None:
        """Delete is gate-free: a never-consented owner may delete its ad."""
        owner = make_user(910000105, consent_given_at=None)
        ad = create_test_ad(owner, category, city, status=AdStatus.PUBLISHED)

        result = delete_ad(ad.id, owner.id)

        assert result.deleted is True
        ad.refresh_from_db()
        assert ad.status == AdStatus.DELETED
