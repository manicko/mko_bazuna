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

import pytest
from django.test import Client
from django.urls import reverse

from apps.categories.models import Category
from apps.core.enums import (
    AdPriorityLevel,
    AdStatus,
    BulkModerationAction,
    PriorityFilter,
)
from apps.locations.models import City
from apps.moderation.models import AdModerationPriority, ModerationCriteria
from apps.moderation.services.priority import PriorityService
from apps.users.models import User

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_user(telegram_id: int = 990030001, **overrides: object) -> User:
    """Create a User with sensible defaults."""
    defaults: dict = {
        "telegram_id": telegram_id,
        "chat_id": telegram_id,
        "username": None,
        "password": "x",
    }
    defaults.update(overrides)
    return User.objects.create(**defaults)


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
        country_code="ME", name="Svc Test City", region="Svc Test Region", slug=slug,
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
    return _make_user(telegram_id=990030010)


# ---------------------------------------------------------------------------
# PriorityService tests
# ---------------------------------------------------------------------------


class TestPriorityService:
    """Tests for PriorityService — calculate_and_save, get_queued_ads, get_priority_counts."""

    def test_calculate_and_save_creates_priority_record(self, category, city) -> None:
        """calculate_and_save creates a new AdModerationPriority record."""
        user = _make_user(telegram_id=990030010)
        ad = create_test_ad(user, category, city)
        service = PriorityService()

        result = service.calculate_and_save(ad)

        assert isinstance(result, AdModerationPriority)
        assert result.ad_id == ad.id
        assert result.priority_level == AdPriorityLevel.LOW.value
        assert result.base_score == 0

    def test_calculate_and_save_updates_existing_record(self, category, city) -> None:
        """calculate_and_save updates an existing record instead of creating duplicate."""
        user = _make_user(telegram_id=990030010)
        ad = create_test_ad(user, category, city)
        service = PriorityService()

        first = service.calculate_and_save(ad)
        second = service.calculate_and_save(ad)

        assert first.id == second.id

    def test_calculate_and_save_with_banned_words(self, category, city) -> None:
        """calculate_and_save correctly computes score with banned words."""
        _banned_words_setup("spam", "scam")
        user = _make_user(telegram_id=990030010)
        ad = create_test_ad(user, category, city, title="spam offer")
        service = PriorityService()

        result = service.calculate_and_save(ad)

        assert "banned_word" in result.flags
        assert result.base_score > 0

    def test_get_queued_ads_returns_moderation_ads(self, category, city) -> None:
        """get_queued_ads returns ads with ON_MODERATION status."""
        user = _make_user(telegram_id=990030010)
        ad = create_test_ad(user, category, city)
        service = PriorityService()
        service.calculate_and_save(ad)

        qs = service.get_queued_ads()

        assert ad in qs

    def test_get_queued_ads_excludes_published_ads(self, category, city) -> None:
        """get_queued_ads excludes published ads."""
        user = _make_user(telegram_id=990030010)
        ad = create_test_ad(user, category, city, status=AdStatus.PUBLISHED)
        service = PriorityService()
        service.calculate_and_save(ad)

        qs = service.get_queued_ads()

        assert ad not in qs

    def test_get_queued_ads_excludes_archived_ads(self, category, city) -> None:
        """get_queued_ads excludes archived ads."""
        user = _make_user(telegram_id=990030010)
        ad = create_test_ad(user, category, city, status=AdStatus.ARCHIVED)
        service = PriorityService()
        service.calculate_and_save(ad)

        qs = service.get_queued_ads()

        assert ad not in qs

    def test_get_queued_ads_filters_by_priority(self, category, city) -> None:
        """get_queued_ads filters by priority level when filter is provided."""
        _banned_words_setup("spam", "scam", "cheap", "fake", "counterfeit")
        user = _make_user(telegram_id=990030010)
        service = PriorityService()

        high_ad = create_test_ad(user, category, city, title="spam scam cheap fake counterfeit")
        service.calculate_and_save(high_ad)

        low_ad = create_test_ad(user, category, city, title="Clean title", description="Clean description")
        service.calculate_and_save(low_ad)

        high_qs = service.get_queued_ads(priority_filter=PriorityFilter.HIGH)
        low_qs = service.get_queued_ads(priority_filter=PriorityFilter.LOW)

        assert high_ad in high_qs
        assert low_ad not in high_qs
        assert low_ad in low_qs
        assert high_ad not in low_qs

    def test_get_queued_ads_priority_filter_none_returns_all(self, category, city) -> None:
        """get_queued_ads with priority_filter=None returns ads of every priority level."""
        _banned_words_setup("spam", "scam", "cheap", "fake", "counterfeit")
        user = _make_user(telegram_id=990030010)
        service = PriorityService()

        high_ad = create_test_ad(user, category, city, title="spam scam cheap fake counterfeit")
        service.calculate_and_save(high_ad)

        low_ad = create_test_ad(user, category, city, title="Clean title", description="Clean description")
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
        user = _make_user(telegram_id=990030010)
        service = PriorityService()

        high_ad = create_test_ad(user, category, city, title="spam scam cheap fake counterfeit")
        service.calculate_and_save(high_ad)

        low_ad = create_test_ad(user, category, city, title="Clean title", description="Clean description")
        service.calculate_and_save(low_ad)

        counts = service.get_priority_counts()

        assert counts["high"] == 1
        assert counts["low"] == 1
        assert counts["medium"] == 0

    def test_get_priority_counts_excludes_non_moderation_ads(self, category, city) -> None:
        """get_priority_counts excludes ads that are not in moderation status."""
        user = _make_user(telegram_id=990030010)
        ad = create_test_ad(user, category, city, title="spam scam cheap", status=AdStatus.PUBLISHED)
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
        user = _make_user(telegram_id=990030020)
        ad = create_test_ad(user, category, city)

        ad.refresh_from_db()
        assert hasattr(ad, "moderation_priority")
        assert ad.moderation_priority.priority_level == AdPriorityLevel.LOW.value

    def test_signal_does_not_create_priority_for_draft(self, category, city) -> None:
        """Signal does NOT create priority for DRAFT ads."""
        user = _make_user(telegram_id=990030020)
        ad = create_test_ad(user, category, city, status=AdStatus.DRAFT)

        ad.refresh_from_db()
        assert not hasattr(ad, "moderation_priority")

    def test_signal_does_not_create_priority_for_published(self, category, city) -> None:
        """Signal does NOT create priority for PUBLISHED ads."""
        user = _make_user(telegram_id=990030020)
        ad = create_test_ad(user, category, city, status=AdStatus.PUBLISHED)

        ad.refresh_from_db()
        assert not hasattr(ad, "moderation_priority")

    def test_signal_does_not_recalculate_existing_priority(self, category, city) -> None:
        """Signal does NOT recalculate priority if record already exists."""
        user = _make_user(telegram_id=990030020)
        ad = create_test_ad(user, category, city)
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
        self.user = _make_user(telegram_id=990030030)
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
        response = client.get(self.queue_url)
        assert response.status_code == 200
        assert b"No ads in the moderation queue" in response.content

    def test_queue_shows_ads(self, category, city) -> None:
        """Queue page shows ads in moderation."""
        ad = create_test_ad(self.user, category, city)
        PriorityService().calculate_and_save(ad)

        client = Client()
        client.force_login(self.staff_user)
        response = client.get(self.queue_url)

        assert response.status_code == 200
        assert str(ad.id).encode() in response.content
        assert ad.title.encode() in response.content

    def test_queue_filters_by_priority(self, category, city) -> None:
        """Queue page filters by priority parameter."""
        ad = create_test_ad(self.user, category, city, title="Low priority ad")
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

        high_ad = create_test_ad(self.user, category, city, title="spam scam cheap fake counterfeit")
        PriorityService().calculate_and_save(high_ad)

        low_ad = create_test_ad(self.user, category, city, title="Low priority ad")
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

        high_ad = create_test_ad(self.user, category, city, title="spam scam cheap fake counterfeit")
        PriorityService().calculate_and_save(high_ad)

        low_ad = create_test_ad(self.user, category, city, title="Low priority ad")
        PriorityService().calculate_and_save(low_ad)

        response = client.get(f"{self.queue_url}?priority=all")

        assert response.status_code == 200
        assert str(high_ad.id).encode() in response.content
        assert str(low_ad.id).encode() in response.content

    def test_priority_filter_invalid_value_defaults_to_all(self, category, city) -> None:
        """An unrecognized priority value falls back to showing all ads."""
        _banned_words_setup("spam", "scam", "cheap", "fake", "counterfeit")
        client = Client()
        client.force_login(self.staff_user)

        high_ad = create_test_ad(self.user, category, city, title="spam scam cheap fake counterfeit")
        PriorityService().calculate_and_save(high_ad)

        low_ad = create_test_ad(self.user, category, city, title="Low priority ad")
        PriorityService().calculate_and_save(low_ad)

        response = client.get(f"{self.queue_url}?priority=bogus")

        assert response.status_code == 200
        assert str(high_ad.id).encode() in response.content
        assert str(low_ad.id).encode() in response.content

    def test_queue_shows_priority_counts(self, category, city) -> None:
        """Queue page displays priority counts in the filter links."""
        ad = create_test_ad(self.user, category, city)
        PriorityService().calculate_and_save(ad)

        client = Client()
        client.force_login(self.staff_user)
        response = client.get(self.queue_url)

        # Should show total count = 1 (low)
        assert b"All (1)" in response.content


# ---------------------------------------------------------------------------
# Bulk API tests
# ---------------------------------------------------------------------------


class TestBulkModerationActionView:
    """Tests for the bulk_moderation_action JSON API endpoint."""

    @pytest.fixture(autouse=True)
    def _setup(self, category, city):
        self.user = _make_user(telegram_id=990030040)
        self.staff_user = _make_staff_user(telegram_id=990030041)
        self.bulk_url = reverse("moderation:bulk_action")

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

    def test_requires_post_method(self) -> None:
        """GET request returns 405."""
        client = Client()
        client.force_login(self.staff_user)
        response = client.get(self.bulk_url)
        assert response.status_code == 405

    def test_bulk_approve(self, category, city) -> None:
        """Bulk approve action approves all selected ads."""
        ad1 = create_test_ad(self.user, category, city, title="Ad 1")
        ad2 = create_test_ad(self.user, category, city, title="Ad 2")

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
        ad1 = create_test_ad(self.user, category, city, title="Ad 1")
        ad2 = create_test_ad(self.user, category, city, title="Ad 2")

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
        ad = create_test_ad(self.user, category, city, title="Flagged ad")

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
        """Errors for individual items are reported without failing the whole batch."""
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

    def test_unknown_action_returns_400(self) -> None:
        """Unknown action type is rejected with 400 before any item is processed."""
        client = Client()
        client.force_login(self.staff_user)
        response = client.post(
            self.bulk_url,
            data=json.dumps({"action": "unknown", "selected_items": [1]}),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "Unknown action: unknown"

    # ── Finding 01: approve_ad enforces POST-only ─────────────────────────

    def test_approve_ad_get_returns_405(self, category, city) -> None:
        """GET to approve_ad endpoint returns 405 Method Not Allowed."""
        ad = create_test_ad(self.user, category, city)

        client = Client()
        client.force_login(self.staff_user)
        response = client.get(f"/moderation/approve/{ad.id}/")

        assert response.status_code == 405
        # Ad should remain in original status
        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION

    # ── Finding 02: bulk API guards against malformed JSON ─────────────────

    def test_malformed_json_body_returns_400(self) -> None:
        """POST with malformed JSON body returns 400 with error message."""
        client = Client()
        client.force_login(self.staff_user)
        response = client.post(
            self.bulk_url,
            data="not-json",
            content_type="application/json",
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "Invalid JSON in request body"

    def test_empty_body_returns_400(self) -> None:
        """POST with empty body returns 400 with error message."""
        client = Client()
        client.force_login(self.staff_user)
        response = client.post(
            self.bulk_url,
            data="",
            content_type="application/json",
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "Invalid JSON in request body"

    # ── Finding 14: bulk API sanitizes error messages ──────────────────────

    def test_error_messages_sanitized(self) -> None:
        """Error messages returned to client are sanitized, not raw exceptions."""
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
        assert data["errors"][0]["error"] == "Processing failed"
