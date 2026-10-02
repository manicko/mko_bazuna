"""
Integration tests for PriorityService, signal, queue view, and bulk API.

Tests cover:
- PriorityService: calculate_and_save, get_queued_ads, get_priority_counts
- Signal: automatic priority calculation on Ad post_save
- Queue view: authentication, filtering, empty state
- Bulk API: authentication, actions, error handling
"""

from __future__ import annotations

import json
import logging
import threading
import time
from unittest.mock import patch

import pytest
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.urls import reverse

from apps.ads.models import Ad, AdImage
from apps.categories.models import Category
from apps.core.enums import (
    AdPriorityLevel,
    AdStatus,
    BulkModerationAction,
    BulkModerationError,
    PriorityFilter,
)
from apps.locations.models import City
from apps.moderation.models import AdModerationPriority, ModerationCriteria
from apps.moderation.services.priority import PriorityService
from apps.moderation.views.api_bulk import MAX_BULK_ACTIONS
from apps.users.models import User
from conftest import create_test_ad, make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_staff_user(telegram_id: int = 990030002) -> User:
    """Create a staff User for testing admin views."""
    return User.objects.create(
        telegram_id=telegram_id,
        chat_id=telegram_id,
        username="moderator",
        password="x",
        is_staff=True,
    )


def _make_category(slug: str = "svc-test-cat") -> Category:
    """Create a Category with sensible defaults."""
    return Category.objects.create(name="Svc Test Category", slug=slug)


def _make_city(slug: str = "svc-test-city") -> City:
    """Create a City with sensible defaults."""
    return City.objects.create(
        country_code="ME",
        name="Svc Test City",
        region="Svc Test Region",
        slug=slug,
    )


def _banned_words_setup(*words: str) -> None:
    """Seed ModerationCriteria singleton with the given banned words."""
    criteria = ModerationCriteria.get_singleton()
    criteria.banned_words = list(words)
    criteria.save()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def priority_seller(category, city):
    """Provide a seller with category/city for priority service tests."""
    return make_user(990030010)


# ---------------------------------------------------------------------------
# PriorityService tests
# ---------------------------------------------------------------------------


class TestPriorityService:
    """Tests for PriorityService — calculate_and_save, get_queued_ads, get_priority_counts."""

    def test_calculate_and_save_creates_priority_record(self, category, city) -> None:
        """calculate_and_save creates a new AdModerationPriority record."""
        user = make_user(990030010)
        ad = create_test_ad(user, category, city, status=AdStatus.ON_MODERATION)
        service = PriorityService()

        result = service.calculate_and_save(ad)

        assert isinstance(result, AdModerationPriority)
        assert result.ad_id == ad.id
        assert result.priority_level == AdPriorityLevel.LOW.value
        assert result.base_score == 0

    def test_calculate_and_save_updates_existing_record(self, category, city) -> None:
        """calculate_and_save updates an existing record instead of creating duplicate."""
        user = make_user(990030010)
        ad = create_test_ad(user, category, city, status=AdStatus.ON_MODERATION)
        service = PriorityService()

        first = service.calculate_and_save(ad)
        second = service.calculate_and_save(ad)

        assert first.id == second.id

    def test_calculate_and_save_with_banned_words(self, category, city) -> None:
        """calculate_and_save correctly computes score with banned words."""
        _banned_words_setup("spam", "scam")
        user = make_user(990030010)
        ad = create_test_ad(
            user, category, city, title="spam offer", status=AdStatus.ON_MODERATION
        )
        service = PriorityService()

        result = service.calculate_and_save(ad)

        assert "banned_word" in result.flags
        assert result.base_score > 0

    def test_get_queued_ads_returns_moderation_ads(self, category, city) -> None:
        """get_queued_ads returns ads in the approvable pair."""
        user = make_user(990030010)
        ad = create_test_ad(user, category, city, status=AdStatus.ON_MODERATION_FAILED)
        service = PriorityService()
        service.calculate_and_save(ad)

        qs = service.get_queued_ads()

        assert ad in qs

    def test_get_queued_ads_excludes_published_ads(self, category, city) -> None:
        """get_queued_ads excludes published ads."""
        user = make_user(990030010)
        ad = create_test_ad(user, category, city, status=AdStatus.PUBLISHED)
        service = PriorityService()
        service.calculate_and_save(ad)

        qs = service.get_queued_ads()

        assert ad not in qs

    def test_get_queued_ads_excludes_archived_ads(self, category, city) -> None:
        """get_queued_ads excludes archived ads."""
        user = make_user(990030010)
        ad = create_test_ad(user, category, city, status=AdStatus.ARCHIVED)
        service = PriorityService()
        service.calculate_and_save(ad)

        qs = service.get_queued_ads()

        assert ad not in qs

    def test_get_queued_ads_filters_by_priority(self, category, city) -> None:
        """get_queued_ads filters by priority level when filter is provided."""
        _banned_words_setup("spam", "scam", "cheap", "fake", "counterfeit")
        user = make_user(990030010)
        service = PriorityService()

        high_ad = create_test_ad(
            user,
            category,
            city,
            title="spam scam cheap fake counterfeit",
            status=AdStatus.ON_MODERATION_FAILED,
        )
        service.calculate_and_save(high_ad)

        low_ad = create_test_ad(
            user,
            category,
            city,
            title="Clean title",
            description="Clean description",
            status=AdStatus.ON_MODERATION_FAILED,
        )
        service.calculate_and_save(low_ad)

        high_qs = service.get_queued_ads(priority_filter=PriorityFilter.HIGH)
        low_qs = service.get_queued_ads(priority_filter=PriorityFilter.LOW)

        assert high_ad in high_qs
        assert low_ad not in high_qs
        assert low_ad in low_qs
        assert high_ad not in low_qs

    def test_get_queued_ads_priority_filter_none_returns_all(
        self, category, city
    ) -> None:
        """get_queued_ads with priority_filter=None returns ads of every priority level."""
        _banned_words_setup("spam", "scam", "cheap", "fake", "counterfeit")
        user = make_user(990030010)
        service = PriorityService()

        high_ad = create_test_ad(
            user,
            category,
            city,
            title="spam scam cheap fake counterfeit",
            status=AdStatus.ON_MODERATION_FAILED,
        )
        service.calculate_and_save(high_ad)

        low_ad = create_test_ad(
            user,
            category,
            city,
            title="Clean title",
            description="Clean description",
            status=AdStatus.ON_MODERATION_FAILED,
        )
        service.calculate_and_save(low_ad)

        qs = service.get_queued_ads(priority_filter=None)

        assert high_ad in qs
        assert low_ad in qs

    def test_get_priority_counts_returns_zero_for_empty(self) -> None:
        """get_priority_counts returns all zeros when no priorities exist."""
        service = PriorityService()
        counts = service.get_priority_counts()
        assert counts == {"high": 0, "medium": 0, "low": 0}

    def test_get_priority_counts_counts_correctly(self, category, city) -> None:
        """get_priority_counts returns correct counts per priority level."""
        _banned_words_setup("spam", "scam", "cheap", "fake", "counterfeit")
        user = make_user(990030010)
        service = PriorityService()

        high_ad = create_test_ad(
            user,
            category,
            city,
            title="spam scam cheap fake counterfeit",
            status=AdStatus.ON_MODERATION_FAILED,
        )
        service.calculate_and_save(high_ad)

        low_ad = create_test_ad(
            user,
            category,
            city,
            title="Clean title",
            description="Clean description",
            status=AdStatus.ON_MODERATION_FAILED,
        )
        service.calculate_and_save(low_ad)

        counts = service.get_priority_counts()

        assert counts["high"] == 1
        assert counts["low"] == 1
        assert counts["medium"] == 0

    def test_get_priority_counts_excludes_non_moderation_ads(
        self, category, city
    ) -> None:
        """get_priority_counts excludes ads that are not in moderation status."""
        user = make_user(990030010)
        ad = create_test_ad(
            user, category, city, title="spam scam cheap", status=AdStatus.PUBLISHED
        )
        service = PriorityService()
        service.calculate_and_save(ad)

        counts = service.get_priority_counts()
        assert counts == {"high": 0, "medium": 0, "low": 0}


# ---------------------------------------------------------------------------
# Signal tests
# ---------------------------------------------------------------------------


class TestCalculateAdPrioritySignal:
    """Tests for the calculate_ad_priority signal on Ad post_save."""

    def test_signal_creates_priority_on_moderation_status(self, category, city) -> None:
        """Signal creates AdModerationPriority when ad is saved with ON_MODERATION status."""
        user = make_user(990030020)
        ad = create_test_ad(user, category, city, status=AdStatus.ON_MODERATION)

        ad.refresh_from_db()
        assert hasattr(ad, "moderation_priority")
        assert ad.moderation_priority.priority_level == AdPriorityLevel.LOW.value

    def test_signal_does_not_create_priority_for_draft(self, category, city) -> None:
        """Signal does NOT create priority for DRAFT ads."""
        user = make_user(990030020)
        ad = create_test_ad(user, category, city, status=AdStatus.DRAFT)

        ad.refresh_from_db()
        assert not hasattr(ad, "moderation_priority")

    def test_signal_does_not_create_priority_for_published(
        self, category, city
    ) -> None:
        """Signal does NOT create priority for PUBLISHED ads."""
        user = make_user(990030020)
        ad = create_test_ad(user, category, city, status=AdStatus.PUBLISHED)

        ad.refresh_from_db()
        assert not hasattr(ad, "moderation_priority")

    def test_signal_does_not_recalculate_existing_priority(
        self, category, city
    ) -> None:
        """Signal does NOT recalculate priority if record already exists."""
        user = make_user(990030020)
        ad = create_test_ad(user, category, city, status=AdStatus.ON_MODERATION)
        ad.refresh_from_db()

        # Save the same ad again
        ad.title = "Updated title"
        ad.save()
        ad.refresh_from_db()

        assert hasattr(ad, "moderation_priority")


# ---------------------------------------------------------------------------
# Queue view tests
# ---------------------------------------------------------------------------


class TestModerationQueueView:
    """Tests for the moderation_queue view — auth, filtering, empty state."""

    @pytest.fixture(autouse=True)
    def _setup(self, category, city):
        self.user = make_user(990030030)
        self.staff_user = _make_staff_user(telegram_id=990030031)
        self.queue_url = reverse("moderation:queue")

    def test_requires_staff(self) -> None:
        """Non-staff user gets 404."""
        client = Client()
        client.force_login(self.user)
        response = client.get(self.queue_url)
        assert response.status_code == 404

    def test_requires_staff_unauthenticated(self) -> None:
        """Unauthenticated user gets 404 (redirected to login then 404)."""
        client = Client()
        response = client.get(self.queue_url)
        assert response.status_code in (302, 404)

    def test_staff_user_can_access(self) -> None:
        """Staff user can access the queue page."""
        client = Client()
        client.force_login(self.staff_user)
        response = client.get(self.queue_url)
        assert response.status_code == 200

    def test_empty_queue_shows_message(self) -> None:
        """Empty queue shows 'No ads' message."""
        client = Client()
        client.force_login(self.staff_user)
        response = client.get(self.queue_url + "?lang=ru")
        assert response.status_code == 200
        assert "Нет объявлений в очереди модерации".encode() in response.content

    def test_queue_shows_ads(self, category, city) -> None:
        """Queue page shows ads in the approvable pair."""
        ad = create_test_ad(
            self.user, category, city, status=AdStatus.ON_MODERATION_FAILED
        )
        PriorityService().calculate_and_save(ad)

        client = Client()
        client.force_login(self.staff_user)
        response = client.get(self.queue_url)

        assert response.status_code == 200
        assert str(ad.id).encode() in response.content
        assert ad.title.encode() in response.content

    def test_queue_filters_by_priority(self, category, city) -> None:
        """Queue page filters by priority parameter."""
        ad = create_test_ad(
            self.user,
            category,
            city,
            title="Low priority ad",
            status=AdStatus.ON_MODERATION_FAILED,
        )
        PriorityService().calculate_and_save(ad)

        client = Client()
        client.force_login(self.staff_user)

        # Filter by high — should not show low priority ad
        response = client.get(f"{self.queue_url}?priority=high")
        assert b"Low priority ad" not in response.content

        # Filter by low — should show it
        response = client.get(f"{self.queue_url}?priority=low")
        assert b"Low priority ad" in response.content

    def test_queue_priority_all_default(self, category, city) -> None:
        """Queue page with no priority param shows ads of every priority level."""
        _banned_words_setup("spam", "scam", "cheap", "fake", "counterfeit")
        client = Client()
        client.force_login(self.staff_user)

        high_ad = create_test_ad(
            self.user,
            category,
            city,
            title="spam scam cheap fake counterfeit",
            status=AdStatus.ON_MODERATION_FAILED,
        )
        PriorityService().calculate_and_save(high_ad)

        low_ad = create_test_ad(
            self.user,
            category,
            city,
            title="Low priority ad",
            status=AdStatus.ON_MODERATION_FAILED,
        )
        PriorityService().calculate_and_save(low_ad)

        response = client.get(self.queue_url)

        assert response.status_code == 200
        assert str(high_ad.id).encode() in response.content
        assert str(low_ad.id).encode() in response.content

    def test_queue_priority_all_explicit(self, category, city) -> None:
        """Queue page with ?priority=all shows ads of every priority level."""
        _banned_words_setup("spam", "scam", "cheap", "fake", "counterfeit")
        client = Client()
        client.force_login(self.staff_user)

        high_ad = create_test_ad(
            self.user,
            category,
            city,
            title="spam scam cheap fake counterfeit",
            status=AdStatus.ON_MODERATION_FAILED,
        )
        PriorityService().calculate_and_save(high_ad)

        low_ad = create_test_ad(
            self.user,
            category,
            city,
            title="Low priority ad",
            status=AdStatus.ON_MODERATION_FAILED,
        )
        PriorityService().calculate_and_save(low_ad)

        response = client.get(f"{self.queue_url}?priority=all")

        assert response.status_code == 200
        assert str(high_ad.id).encode() in response.content
        assert str(low_ad.id).encode() in response.content

    def test_priority_filter_invalid_value_defaults_to_all(
        self, category, city
    ) -> None:
        """An unrecognized priority value falls back to showing all ads."""
        _banned_words_setup("spam", "scam", "cheap", "fake", "counterfeit")
        client = Client()
        client.force_login(self.staff_user)

        high_ad = create_test_ad(
            self.user,
            category,
            city,
            title="spam scam cheap fake counterfeit",
            status=AdStatus.ON_MODERATION_FAILED,
        )
        PriorityService().calculate_and_save(high_ad)

        low_ad = create_test_ad(
            self.user,
            category,
            city,
            title="Low priority ad",
            status=AdStatus.ON_MODERATION_FAILED,
        )
        PriorityService().calculate_and_save(low_ad)

        response = client.get(f"{self.queue_url}?priority=bogus")

        assert response.status_code == 200
        assert str(high_ad.id).encode() in response.content
        assert str(low_ad.id).encode() in response.content

    def test_queue_shows_priority_counts(self, category, city) -> None:
        """Queue page displays priority counts in the filter links."""
        ad = create_test_ad(
            self.user, category, city, status=AdStatus.ON_MODERATION_FAILED
        )
        PriorityService().calculate_and_save(ad)

        client = Client()
        client.force_login(self.staff_user)
        response = client.get(self.queue_url + "?lang=ru")

        # Should show total count = 1 (low)
        assert "Все (1)".encode() in response.content


# ---------------------------------------------------------------------------
# Bulk API tests
# ---------------------------------------------------------------------------


class TestBulkModerationActionView:
    """Tests for the bulk_moderation_action JSON API endpoint."""

    @pytest.fixture(autouse=True)
    def _setup(self, category, city):
        self.user = make_user(990030040)
        self.staff_user = _make_staff_user(telegram_id=990030041)
        self.bulk_url = reverse("moderation:bulk_action")
        assert self.bulk_url == "/moderation/api/v1/bulk-action/"

    def test_requires_staff_forbidden(self) -> None:
        """Non-staff user gets 403."""
        client = Client()
        client.force_login(self.user)
        response = client.post(
            self.bulk_url,
            data=json.dumps(
                {"action": BulkModerationAction.APPROVE.value, "selected_items": []}
            ),
            content_type="application/json",
        )
        assert response.status_code == 403

    def test_unauthenticated_returns_401(self) -> None:
        """Anonymous POST gets 401 with a WWW-Authenticate challenge."""
        client = Client()
        response = client.post(
            self.bulk_url,
            data=json.dumps(
                {"action": BulkModerationAction.APPROVE.value, "selected_items": []}
            ),
            content_type="application/json",
        )
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"  # pyright: ignore[reportIndexIssue] - Django: django-stubs not installed; HttpResponse.headers untyped

    def test_requires_post_method(self) -> None:
        """GET request returns 405."""
        client = Client()
        client.force_login(self.staff_user)
        response = client.get(self.bulk_url)
        assert response.status_code == 405

    def test_bulk_approve(self, category, city) -> None:
        """Bulk approve action approves all selected ads."""
        ad1 = create_test_ad(
            self.user, category, city, title="Test Ad First", status=AdStatus.ON_MODERATION
        )
        ad2 = create_test_ad(
            self.user,
            category,
            city,
            title="Test Ad Second",
            status=AdStatus.ON_MODERATION,
        )
        AdImage.objects.create(ad=ad1, image="img1.jpg", position=0)
        AdImage.objects.create(ad=ad2, image="img2.jpg", position=0)

        client = Client()
        client.force_login(self.staff_user)
        response = client.post(
            self.bulk_url,
            data=json.dumps(
                {
                    "action": BulkModerationAction.APPROVE.value,
                    "selected_items": [ad1.id, ad2.id],
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["completed"] == 2
        assert data["errors"] == []

        # Verify ads are now published
        ad1.refresh_from_db()
        ad2.refresh_from_db()
        assert ad1.status == AdStatus.PUBLISHED
        assert ad2.status == AdStatus.PUBLISHED

    def test_bulk_reject(self, category, city) -> None:
        """Bulk reject action rejects all selected ads with reason."""
        ad1 = create_test_ad(
            self.user, category, city, title="Ad 1", status=AdStatus.ON_MODERATION
        )
        ad2 = create_test_ad(
            self.user, category, city, title="Ad 2", status=AdStatus.ON_MODERATION
        )

        client = Client()
        client.force_login(self.staff_user)
        response = client.post(
            self.bulk_url,
            data=json.dumps(
                {
                    "action": BulkModerationAction.REJECT.value,
                    "selected_items": [ad1.id, ad2.id],
                    "reason": "Duplicate content",
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["completed"] == 2
        assert data["errors"] == []

        # Verify ads are now rejected
        ad1.refresh_from_db()
        ad2.refresh_from_db()
        assert ad1.status == AdStatus.REJECTED
        assert ad2.status == AdStatus.REJECTED

    def test_bulk_flag(self, category, city) -> None:
        """Bulk flag action recalculates priority for selected ads."""
        ad = create_test_ad(
            self.user, category, city, title="Flagged ad", status=AdStatus.ON_MODERATION
        )

        client = Client()
        client.force_login(self.staff_user)
        response = client.post(
            self.bulk_url,
            data=json.dumps(
                {"action": BulkModerationAction.FLAG.value, "selected_items": [ad.id]}
            ),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["completed"] == 1

        # Verify priority record was created
        ad.refresh_from_db()
        assert hasattr(ad, "moderation_priority")

    def test_bulk_errors_reported(self, category, city) -> None:
        """Errors for individual items are reported without failing the whole batch.

        A missing id is a distinct, actionable failure class (05-AD-010): the
        per-id error says the ad was not found rather than a cause-free generic
        string. The response shape and HTTP 200 are unchanged.
        """
        client = Client()
        client.force_login(self.staff_user)
        response = client.post(
            self.bulk_url,
            data=json.dumps(
                {
                    "action": BulkModerationAction.APPROVE.value,
                    "selected_items": [99999],
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["completed"] == 0
        assert len(data["errors"]) == 1
        assert data["errors"][0]["id"] == 99999
        assert data["errors"][0]["error"] == BulkModerationError.AD_NOT_FOUND.value

    def test_unknown_action_returns_422(self) -> None:
        """Unknown action type is rejected with 422 before any item is processed."""
        client = Client()
        client.force_login(self.staff_user)
        response = client.post(
            self.bulk_url,
            data=json.dumps({"action": "unknown", "selected_items": [1]}),
            content_type="application/json",
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"] == "Invalid request body"

    # ── Finding 01: approve_ad enforces POST-only ─────────────────────────

    def test_approve_ad_get_returns_405(self, category, city) -> None:
        """GET to approve_ad endpoint returns 405 Method Not Allowed."""
        ad = create_test_ad(self.user, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(self.staff_user)
        response = client.get(f"/moderation/approve/{ad.id}/")

        assert response.status_code == 405
        # Ad should remain in original status
        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION

    # ── Finding 02: bulk API guards against malformed JSON ─────────────────

    def test_malformed_json_body_returns_422(self) -> None:
        """POST with malformed JSON body returns 422 with error message."""
        client = Client()
        client.force_login(self.staff_user)
        response = client.post(
            self.bulk_url,
            data="not-json",
            content_type="application/json",
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"] == "Invalid request body"

    def test_empty_body_returns_422(self) -> None:
        """POST with empty body returns 422 with error message."""
        client = Client()
        client.force_login(self.staff_user)
        response = client.post(
            self.bulk_url,
            data="",
            content_type="application/json",
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"] == "Invalid request body"

    def test_extra_key_returns_422(self) -> None:
        """POST with an unknown key is rejected by extra='forbid'."""
        client = Client()
        client.force_login(self.staff_user)
        response = client.post(
            self.bulk_url,
            data=json.dumps(
                {
                    "action": BulkModerationAction.APPROVE.value,
                    "selected_items": [],
                    "rogue": "x",
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"] == "Invalid request body"

    def test_selected_items_type_mismatch_returns_422(self) -> None:
        """POST with selected_items as a non-list is rejected by type validation."""
        client = Client()
        client.force_login(self.staff_user)
        response = client.post(
            self.bulk_url,
            data=json.dumps(
                {
                    "action": BulkModerationAction.APPROVE.value,
                    "selected_items": "not-a-list",
                    "reason": "",
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"] == "Invalid request body"

    def test_validation_error_includes_error_details(self) -> None:
        """422 response body includes structured Pydantic error list under 'errors'."""
        client = Client()
        client.force_login(self.staff_user)
        response = client.post(
            self.bulk_url,
            data=json.dumps(
                {
                    "action": "unknown",
                    "selected_items": [1],
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"] == "Invalid request body"
        assert "errors" in data
        assert isinstance(data["errors"], list)
        assert len(data["errors"]) > 0

    # ── Finding 14: bulk API sanitizes error messages ──────────────────────

    def test_error_messages_sanitized(self) -> None:
        """Error messages returned to client are sanitized, not raw exceptions.

        A missing ad yields the specific "not found" string (05-AD-010), which
        still carries no driver text, table/constraint name, ``DETAIL`` or
        ``CONTEXT``.
        """
        client = Client()
        client.force_login(self.staff_user)
        response = client.post(
            self.bulk_url,
            data=json.dumps(
                {
                    "action": BulkModerationAction.APPROVE.value,
                    "selected_items": [99999],
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["completed"] == 0
        assert len(data["errors"]) == 1
        assert data["errors"][0]["id"] == 99999
        assert data["errors"][0]["error"] == BulkModerationError.AD_NOT_FOUND.value
        lowered = data["errors"][0]["error"].lower()
        for forbidden in ("detail", "context", "select", "insert", "constraint"):
            assert forbidden not in lowered

    # ── Ext-003b: bulk API caps batch size at MAX_BULK_ACTIONS ────────────────

    def test_bulk_exceeds_max_actions_returns_400(self) -> None:
        """Batch exceeding MAX_BULK_ACTIONS is rejected with 400 before any DB write."""
        client = Client()
        client.force_login(self.staff_user)
        too_many = list(range(MAX_BULK_ACTIONS + 1))
        response = client.post(
            self.bulk_url,
            data=json.dumps(
                {
                    "action": BulkModerationAction.APPROVE.value,
                    "selected_items": too_many,
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == (
            f"selected_items exceeds maximum of {MAX_BULK_ACTIONS}"
        )
        # Rejected before the per-item loop: no DB writes occurred.
        assert "completed" not in data

    def test_bulk_at_max_actions_accepted(self) -> None:
        """Batch at exactly MAX_BULK_ACTIONS is accepted (not rejected by the cap)."""
        client = Client()
        client.force_login(self.staff_user)
        ids = list(range(MAX_BULK_ACTIONS))
        response = client.post(
            self.bulk_url,
            data=json.dumps(
                {
                    "action": BulkModerationAction.APPROVE.value,
                    "selected_items": ids,
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        # Fake IDs do not exist, so all fail individually; the key assertion is
        # that the cap did not reject the request (proceeded to per-item processing).
        assert data["completed"] == 0
        assert len(data["errors"]) == MAX_BULK_ACTIONS

    def test_unknown_version_returns_404(self) -> None:
        """POST to an unknown API version (/api/v2/) degrades to 404 (not 500)."""
        client = Client()
        client.force_login(self.staff_user)
        response = client.post(
            "/moderation/api/v2/bulk-action/",
            data=json.dumps(
                {"action": BulkModerationAction.APPROVE.value, "selected_items": [1]}
            ),
            content_type="application/json",
        )
        assert response.status_code == 404

    # ── 05-AD-010 (Q11): per-ad transaction, row lock, honest errors ───────

    def test_mixed_batch_partial_failure_contract(self, category, city) -> None:
        """A valid id and an invalid-status id in one batch: the valid ad is
        processed, the invalid one is reported with its own specific string,
        and the response is still 200 with an honest ``completed`` count.

        This is the test that proves the per-ad isolation: under a per-request
        ``atomic()`` the rejection's ``ValueError`` would poison the batch
        transaction and the next iteration would raise
        ``TransactionManagementError`` (a 500). Under the shipped per-ad
        ``atomic()`` both ids are handled independently.
        """
        valid_ad = create_test_ad(
            self.user, category, city, status=AdStatus.ON_MODERATION
        )
        invalid_ad = create_test_ad(
            self.user, category, city, status=AdStatus.ARCHIVED
        )

        client = Client()
        client.force_login(self.staff_user)
        response = client.post(
            self.bulk_url,
            data=json.dumps(
                {
                    "action": BulkModerationAction.REJECT.value,
                    "selected_items": [valid_ad.id, invalid_ad.id],
                    "reason": "policy violation",
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["completed"] == 1
        assert data["errors"] == [
            {"id": invalid_ad.id, "error": BulkModerationError.INVALID_TRANSITION.value}
        ]

        valid_ad.refresh_from_db()
        invalid_ad.refresh_from_db()
        assert valid_ad.status == AdStatus.REJECTED
        # The invalid ad was not touched by the refusal.
        assert invalid_ad.status == AdStatus.ARCHIVED

    def test_integrity_error_does_not_roll_back_prior_ads(self, category, city) -> None:
        """An ``IntegrityError`` while processing ad k leaves ad k untouched and
        does not roll back ads 1..k-1.

        ``reject_ad`` is patched so the *real* transition commits inside the
        per-ad ``atomic()``, then an ``IntegrityError`` is raised. The per-ad
        savepoint rolls ad k back while ad 1 (processed first) stays committed.
        Against the pre-fix loop (no per-ad transaction) ad k's transition
        survives in autocommit, so this assertion is red before the fix.
        """
        ads = [
            create_test_ad(self.user, category, city, status=AdStatus.ON_MODERATION),
            create_test_ad(self.user, category, city, status=AdStatus.ON_MODERATION),
            create_test_ad(self.user, category, city, status=AdStatus.ON_MODERATION),
        ]
        failing_ad = ads[1]

        from apps.moderation.views.api_bulk import reject_ad as view_reject_ad

        def _reject_then_fail(ad, moderator_id, reason):
            view_reject_ad(ad, moderator_id, reason)
            if ad.id == failing_ad.id:
                raise IntegrityError("simulated mid-record failure")

        client = Client()
        client.force_login(self.staff_user)
        with patch(
            "apps.moderation.views.api_bulk.reject_ad", side_effect=_reject_then_fail
        ):
            response = client.post(
                self.bulk_url,
                data=json.dumps(
                    {
                        "action": BulkModerationAction.REJECT.value,
                        "selected_items": [ads[0].id, failing_ad.id, ads[2].id],
                        "reason": "policy violation",
                    }
                ),
                content_type="application/json",
            )

        assert response.status_code == 200
        data = response.json()
        assert data["completed"] == 2
        assert data["errors"] == [
            {"id": failing_ad.id, "error": BulkModerationError.PROCESSING_FAILED.value}
        ]

        ads[0].refresh_from_db()
        failing_ad.refresh_from_db()
        ads[2].refresh_from_db()
        # Ads 1 and 3 (processed before/after the failure) committed.
        assert ads[0].status == AdStatus.REJECTED
        assert ads[2].status == AdStatus.REJECTED
        # The failing ad was rolled back by its own per-ad transaction.
        assert failing_ad.status == AdStatus.ON_MODERATION

    def test_invalid_transition_not_error_and_not_cause_free(
        self, category, city, caplog
    ) -> None:
        """A state-machine ``ValueError`` on ordinary user input is reported
        with a specific string and logged at WARNING, never ERROR.

        The returned string must not leak the exception text, the transition
        pair, the table/constraint name, ``DETAIL`` or ``CONTEXT``.
        """
        invalid_ad = create_test_ad(
            self.user, category, city, status=AdStatus.ARCHIVED
        )

        client = Client()
        client.force_login(self.staff_user)
        with caplog.at_level(logging.DEBUG):
            response = client.post(
                self.bulk_url,
                data=json.dumps(
                    {
                        "action": BulkModerationAction.REJECT.value,
                        "selected_items": [invalid_ad.id],
                        "reason": "policy violation",
                    }
                ),
                content_type="application/json",
            )

        assert response.status_code == 200
        data = response.json()
        assert data["completed"] == 0
        assert data["errors"] == [
            {"id": invalid_ad.id, "error": BulkModerationError.INVALID_TRANSITION.value}
        ]

        message = data["errors"][0]["error"]
        assert message == "Ad is not in a modifiable state"
        for forbidden in (
            "Invalid transition",
            "archived",
            "->",
            "DETAIL",
            "CONTEXT",
            "ads_ad",
            "constraint",
        ):
            assert forbidden not in message

        bulk_records = [r for r in caplog.records if "Bulk moderation" in r.message]
        assert bulk_records, "expected a WARNING log for the refused transition"
        assert all(r.levelno < logging.ERROR for r in bulk_records)

    def test_unexpected_exception_is_generic_and_loud(self, category, city, caplog) -> None:
        """A genuinely unexpected exception still yields a generic, non-leaking
        string AND an ERROR-level log — an infra failure is never a silent 200.
        """
        ad = create_test_ad(self.user, category, city, status=AdStatus.PUBLISHED)

        client = Client()
        client.force_login(self.staff_user)
        with (
            patch.object(
                PriorityService,
                "calculate_and_save",
                side_effect=RuntimeError("boom: relation secrets_table does not exist"),
            ),
            caplog.at_level(logging.DEBUG),
        ):
            response = client.post(
                self.bulk_url,
                data=json.dumps(
                    {
                        "action": BulkModerationAction.FLAG.value,
                        "selected_items": [ad.id],
                    }
                ),
                content_type="application/json",
            )

        assert response.status_code == 200
        data = response.json()
        assert data["completed"] == 0
        assert data["errors"] == [
            {"id": ad.id, "error": BulkModerationError.PROCESSING_FAILED.value}
        ]
        # The generic string must not carry the raw exception text.
        assert "secrets_table" not in data["errors"][0]["error"]
        assert "boom" not in data["errors"][0]["error"]

        bulk_records = [r for r in caplog.records if "Bulk moderation" in r.message]
        assert any(r.levelno >= logging.ERROR for r in bulk_records)

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.slow
    @pytest.mark.concurrent
    def test_row_lock_blocks_concurrent_writer(self, category, city) -> None:
        """``select_for_update()`` is issued per ad: a concurrent writer holding
        the row lock blocks the endpoint until the lock is released.

        Behavioural assertion (not a source substring): the main thread holds a
        ``FOR UPDATE`` lock on the target row; the endpoint POST must not
        complete while the lock is held, and must complete once it is released.
        """
        ad = create_test_ad(self.user, category, city, status=AdStatus.ON_MODERATION)
        ad_id = ad.id

        started = threading.Event()
        finished = threading.Event()
        status_code: dict[str, int] = {}
        errors: list[BaseException] = []

        def _post_bulk() -> None:
            started.set()
            try:
                thread_client = Client()
                thread_client.force_login(self.staff_user)
                resp = thread_client.post(
                    self.bulk_url,
                    data=json.dumps(
                        {
                            "action": BulkModerationAction.REJECT.value,
                            "selected_items": [ad_id],
                            "reason": "policy violation",
                        }
                    ),
                    content_type="application/json",
                )
                status_code["value"] = resp.status_code
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                finished.set()
                connection.close()

        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
            locked = Ad.objects.select_for_update().get(pk=ad_id)
            assert locked.id == ad_id

            thread = threading.Thread(target=_post_bulk)
            thread.start()
            assert started.wait(timeout=5), "Background POST did not start"

            # While the row lock is held the endpoint's FOR UPDATE must block.
            time.sleep(1.0)
            assert not finished.is_set(), (
                "Bulk POST completed before the row lock was released — "
                "select_for_update did not block the concurrent writer"
            )

        # Main transaction commits, releasing the lock; the POST must complete.
        assert finished.wait(timeout=10), (
            "Bulk POST did not complete after the lock was released"
        )
        thread.join(timeout=10)

        assert not errors, f"Background thread raised: {errors}"
        assert status_code.get("value") == 200
        ad.refresh_from_db()
        assert ad.status == AdStatus.REJECTED

    def test_flag_runs_inside_transaction_and_updates_priority(
        self, category, city
    ) -> None:
        """The FLAG branch now runs ``calculate_and_save`` inside the per-ad
        transaction, and still writes the priority record.

        The transactional proof: a ``calculate_and_save`` that writes then
        raises is rolled back by the per-ad ``atomic()`` — the record would
        survive if FLAG ran outside a transaction.
        """
        ad = create_test_ad(self.user, category, city, status=AdStatus.PUBLISHED)

        client = Client()
        client.force_login(self.staff_user)
        response = client.post(
            self.bulk_url,
            data=json.dumps(
                {"action": BulkModerationAction.FLAG.value, "selected_items": [ad.id]}
            ),
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json()["completed"] == 1
        assert AdModerationPriority.objects.filter(ad_id=ad.id).exists()

        # Transactional proof: write-then-raise must roll the write back.
        other_ad = create_test_ad(self.user, category, city, status=AdStatus.PUBLISHED)
        real_calculate = PriorityService.calculate_and_save

        def _write_then_fail(self_service, target_ad):
            real_calculate(self_service, target_ad)
            raise RuntimeError("simulated failure after write")

        with patch.object(PriorityService, "calculate_and_save", _write_then_fail):
            failed = client.post(
                self.bulk_url,
                data=json.dumps(
                    {
                        "action": BulkModerationAction.FLAG.value,
                        "selected_items": [other_ad.id],
                    }
                ),
                content_type="application/json",
            )

        assert failed.status_code == 200
        assert failed.json()["completed"] == 0
        assert not AdModerationPriority.objects.filter(ad_id=other_ad.id).exists()
