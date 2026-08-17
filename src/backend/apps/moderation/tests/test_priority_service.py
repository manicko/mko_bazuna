"""
Integration tests for PriorityService, signal, queue view, and bulk API.

Tests cover:
- PriorityService: calculate_and_save, get_queued_ads, get_priority_counts
- Signal: automatic priority calculation on Ad post_save
- Queue view: authentication, filtering, empty state
- Bulk API: authentication, actions, error handling

Uses ``django.test.TestCase`` for DB-backed assertions.
"""

from __future__ import annotations

import json

from django.test import TestCase
from django.urls import reverse

from apps.ads.models import Ad
from apps.categories.models import Category
from apps.core.enums import (
    AdPriorityLevel,
    AdSource,
    AdStatus,
    BulkModerationAction,
    PriorityFilter,
)
from apps.locations.models import City
from apps.moderation.models import AdModerationPriority, ModerationCriteria
from apps.moderation.services.priority import PriorityService
from apps.users.models import User

# ---------------------------------------------------------------------------
# Test helpers (reuse pattern from test_priority.py)
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
    return User.objects.create(**defaults)  # type: ignore[arg-type]


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


def _set_status_timestamp(data, now=None):
    """Auto-populate timestamp fields matching the ad status."""
    from django.utils import timezone

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
    user: User,
    category: Category,
    city: City,
    *,
    title: str = "Svc Test Ad",
    description: str = "Svc test description",
    status: AdStatus = AdStatus.ON_MODERATION,
    **overrides: object,
) -> Ad:
    """Create an Ad with sensible defaults."""
    defaults: dict = {
        "user": user,
        "title": title,
        "description": description,
        "category": category,
        "city": city,
        "category_name": category.name,
        "status": status,
        "source": AdSource.TELEGRAM,
    }
    defaults.update(overrides)
    _set_status_timestamp(defaults)
    return Ad.objects.create(**defaults)  # type: ignore[arg-type]


def _banned_words_setup(*words: str) -> None:
    """Seed ModerationCriteria singleton with the given banned words."""
    criteria = ModerationCriteria.get_singleton()
    criteria.banned_words = list(words)
    criteria.save()


# ---------------------------------------------------------------------------
# PriorityService tests
# ---------------------------------------------------------------------------


class TestPriorityService(TestCase):
    """Tests for PriorityService — calculate_and_save, get_queued_ads, get_priority_counts."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.service = PriorityService()
        cls.category = _make_category()
        cls.city = _make_city()
        cls.user = _make_user(telegram_id=990030010)

    # ── calculate_and_save ──────────────────────────────────────────────

    def test_calculate_and_save_creates_priority_record(self) -> None:
        """calculate_and_save creates a new AdModerationPriority record."""
        ad = _make_ad(self.user, self.category, self.city)

        result = self.service.calculate_and_save(ad)

        self.assertIsInstance(result, AdModerationPriority)
        self.assertEqual(result.ad_id, ad.id)
        self.assertEqual(result.priority_level, AdPriorityLevel.LOW.value)
        self.assertEqual(result.base_score, 0)

    def test_calculate_and_save_updates_existing_record(self) -> None:
        """calculate_and_save updates an existing record instead of creating duplicate."""
        ad = _make_ad(self.user, self.category, self.city)
        first = self.service.calculate_and_save(ad)

        # Second call should update, not create
        second = self.service.calculate_and_save(ad)

        self.assertEqual(first.id, second.id)

    def test_calculate_and_save_with_banned_words(self) -> None:
        """calculate_and_save correctly computes score with banned words."""
        _banned_words_setup("spam", "scam")
        ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="spam offer",
        )

        result = self.service.calculate_and_save(ad)

        self.assertIn("banned_word", result.flags)
        self.assertGreater(result.base_score, 0)

    # ── get_queued_ads ─────────────────────────────────────────────────

    def test_get_queued_ads_returns_moderation_ads(self) -> None:
        """get_queued_ads returns ads with ON_MODERATION status."""
        ad = _make_ad(self.user, self.category, self.city)
        self.service.calculate_and_save(ad)

        qs = self.service.get_queued_ads()

        self.assertIn(ad, qs)

    def test_get_queued_ads_excludes_published_ads(self) -> None:
        """get_queued_ads excludes published ads."""
        ad = _make_ad(
            self.user,
            self.category,
            self.city,
            status=AdStatus.PUBLISHED,
        )
        self.service.calculate_and_save(ad)

        qs = self.service.get_queued_ads()

        self.assertNotIn(ad, qs)

    def test_get_queued_ads_excludes_archived_ads(self) -> None:
        """get_queued_ads excludes archived ads."""
        ad = _make_ad(
            self.user,
            self.category,
            self.city,
            status=AdStatus.ARCHIVED,
        )
        self.service.calculate_and_save(ad)

        qs = self.service.get_queued_ads()

        self.assertNotIn(ad, qs)

    def test_get_queued_ads_filters_by_priority(self) -> None:
        """get_queued_ads filters by priority level when filter is provided."""
        _banned_words_setup("spam", "scam", "cheap", "fake", "counterfeit")
        high_ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="spam scam cheap fake counterfeit",
        )
        self.service.calculate_and_save(high_ad)

        low_ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="Clean title",
            description="Clean description",
        )
        self.service.calculate_and_save(low_ad)

        high_qs = self.service.get_queued_ads(priority_filter=PriorityFilter.HIGH)
        low_qs = self.service.get_queued_ads(priority_filter=PriorityFilter.LOW)

        self.assertIn(high_ad, high_qs)
        self.assertNotIn(low_ad, high_qs)
        self.assertIn(low_ad, low_qs)
        self.assertNotIn(high_ad, low_qs)

    def test_get_queued_ads_priority_filter_none_returns_all(self) -> None:
        """get_queued_ads with priority_filter=None returns ads of every priority level."""
        _banned_words_setup("spam", "scam", "cheap", "fake", "counterfeit")
        high_ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="spam scam cheap fake counterfeit",
        )
        self.service.calculate_and_save(high_ad)

        low_ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="Clean title",
            description="Clean description",
        )
        self.service.calculate_and_save(low_ad)

        qs = self.service.get_queued_ads(priority_filter=None)

        self.assertIn(high_ad, qs)
        self.assertIn(low_ad, qs)

    # ── get_priority_counts ────────────────────────────────────────────

    def test_get_priority_counts_returns_zero_for_empty(self) -> None:
        """get_priority_counts returns all zeros when no priorities exist."""
        counts = self.service.get_priority_counts()

        self.assertEqual(counts, {"high": 0, "medium": 0, "low": 0})

    def test_get_priority_counts_counts_correctly(self) -> None:
        """get_priority_counts returns correct counts per priority level."""
        _banned_words_setup("spam", "scam", "cheap", "fake", "counterfeit")
        high_ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="spam scam cheap fake counterfeit",
        )
        self.service.calculate_and_save(high_ad)

        low_ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="Clean title",
            description="Clean description",
        )
        self.service.calculate_and_save(low_ad)

        counts = self.service.get_priority_counts()

        self.assertEqual(counts["high"], 1)
        self.assertEqual(counts["low"], 1)
        self.assertEqual(counts["medium"], 0)

    def test_get_priority_counts_excludes_non_moderation_ads(self) -> None:
        """get_priority_counts excludes ads that are not in moderation status."""
        high_ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="spam scam cheap",
            status=AdStatus.PUBLISHED,
        )
        self.service.calculate_and_save(high_ad)

        counts = self.service.get_priority_counts()

        self.assertEqual(counts, {"high": 0, "medium": 0, "low": 0})


# ---------------------------------------------------------------------------
# Signal tests
# ---------------------------------------------------------------------------


class TestCalculateAdPrioritySignal(TestCase):
    """Tests for the calculate_ad_priority signal on Ad post_save."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.category = _make_category()
        cls.city = _make_city()
        cls.user = _make_user(telegram_id=990030020)

    def test_signal_creates_priority_on_moderation_status(self) -> None:
        """Signal creates AdModerationPriority when ad is saved with ON_MODERATION status."""
        ad = _make_ad(self.user, self.category, self.city)

        # Refresh from DB to get related objects
        ad.refresh_from_db()

        self.assertTrue(hasattr(ad, "moderation_priority"))
        self.assertEqual(
            ad.moderation_priority.priority_level, AdPriorityLevel.LOW.value
        )

    def test_signal_does_not_create_priority_for_draft(self) -> None:
        """Signal does NOT create priority for DRAFT ads."""
        ad = _make_ad(
            self.user,
            self.category,
            self.city,
            status=AdStatus.DRAFT,
        )

        ad.refresh_from_db()

        self.assertFalse(hasattr(ad, "moderation_priority"))

    def test_signal_does_not_create_priority_for_published(self) -> None:
        """Signal does NOT create priority for PUBLISHED ads."""
        ad = _make_ad(
            self.user,
            self.category,
            self.city,
            status=AdStatus.PUBLISHED,
        )

        ad.refresh_from_db()

        self.assertFalse(hasattr(ad, "moderation_priority"))

    def test_signal_does_not_recalculate_existing_priority(self) -> None:
        """Signal does NOT recalculate priority if record already exists."""
        ad = _make_ad(self.user, self.category, self.city)
        ad.refresh_from_db()

        # Save the same ad again
        ad.title = "Updated title"
        ad.save()
        ad.refresh_from_db()

        # Priority should still exist and be the same
        self.assertTrue(hasattr(ad, "moderation_priority"))


# ---------------------------------------------------------------------------
# Queue view tests
# ---------------------------------------------------------------------------


class TestModerationQueueView(TestCase):
    """Tests for the moderation_queue view — auth, filtering, empty state."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.category = _make_category()
        cls.city = _make_city()
        cls.user = _make_user(telegram_id=990030030)
        cls.staff_user = _make_staff_user(telegram_id=990030031)
        cls.queue_url = reverse("moderation:queue")

    def test_requires_staff(self) -> None:
        """Non-staff user gets 404."""
        self.client.force_login(self.user)
        response = self.client.get(self.queue_url)
        self.assertEqual(response.status_code, 404)

    def test_requires_staff_unauthenticated(self) -> None:
        """Unauthenticated user gets 404 (redirected to login then 404)."""
        response = self.client.get(self.queue_url)
        # Django redirects to login, then staff check fails
        self.assertIn(response.status_code, (302, 404))

    def test_staff_user_can_access(self) -> None:
        """Staff user can access the queue page."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.queue_url)
        self.assertEqual(response.status_code, 200)

    def test_empty_queue_shows_message(self) -> None:
        """Empty queue shows 'No ads' message."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.queue_url)
        self.assertContains(response, "No ads in the moderation queue")

    def test_queue_shows_ads(self) -> None:
        """Queue page shows ads in moderation."""
        ad = _make_ad(self.user, self.category, self.city)
        PriorityService().calculate_and_save(ad)

        self.client.force_login(self.staff_user)
        response = self.client.get(self.queue_url)

        self.assertContains(response, str(ad.id))
        self.assertContains(response, ad.title)

    def test_queue_filters_by_priority(self) -> None:
        """Queue page filters by priority parameter."""
        ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="Low priority ad",
        )
        PriorityService().calculate_and_save(ad)

        self.client.force_login(self.staff_user)

        # Filter by high — should not show low priority ad
        response = self.client.get(f"{self.queue_url}?priority=high")
        self.assertNotContains(response, "Low priority ad")

        # Filter by low — should show it
        response = self.client.get(f"{self.queue_url}?priority=low")
        self.assertContains(response, "Low priority ad")

    def test_queue_priority_all_default(self) -> None:
        """Queue page with no priority param shows ads of every priority level."""
        _banned_words_setup("spam", "scam", "cheap", "fake", "counterfeit")
        high_ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="spam scam cheap fake counterfeit",
        )
        PriorityService().calculate_and_save(high_ad)

        low_ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="Low priority ad",
        )
        PriorityService().calculate_and_save(low_ad)

        self.client.force_login(self.staff_user)
        response = self.client.get(self.queue_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(high_ad.id))
        self.assertContains(response, str(low_ad.id))

    def test_queue_priority_all_explicit(self) -> None:
        """Queue page with ?priority=all shows ads of every priority level."""
        _banned_words_setup("spam", "scam", "cheap", "fake", "counterfeit")
        high_ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="spam scam cheap fake counterfeit",
        )
        PriorityService().calculate_and_save(high_ad)

        low_ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="Low priority ad",
        )
        PriorityService().calculate_and_save(low_ad)

        self.client.force_login(self.staff_user)
        response = self.client.get(f"{self.queue_url}?priority=all")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(high_ad.id))
        self.assertContains(response, str(low_ad.id))

    def test_priority_filter_invalid_value_defaults_to_all(self) -> None:
        """An unrecognized priority value falls back to showing all ads."""
        _banned_words_setup("spam", "scam", "cheap", "fake", "counterfeit")
        high_ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="spam scam cheap fake counterfeit",
        )
        PriorityService().calculate_and_save(high_ad)

        low_ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="Low priority ad",
        )
        PriorityService().calculate_and_save(low_ad)

        self.client.force_login(self.staff_user)
        response = self.client.get(f"{self.queue_url}?priority=bogus")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(high_ad.id))
        self.assertContains(response, str(low_ad.id))

    def test_queue_shows_priority_counts(self) -> None:
        """Queue page displays priority counts in the filter links."""
        ad = _make_ad(self.user, self.category, self.city)
        PriorityService().calculate_and_save(ad)

        self.client.force_login(self.staff_user)
        response = self.client.get(self.queue_url)

        # Should show total count = 1 (low)
        self.assertContains(response, "All (1)")


# ---------------------------------------------------------------------------
# Bulk API tests
# ---------------------------------------------------------------------------


class TestBulkModerationActionView(TestCase):
    """Tests for the bulk_moderation_action JSON API endpoint."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.category = _make_category()
        cls.city = _make_city()
        cls.user = _make_user(telegram_id=990030040)
        cls.staff_user = _make_staff_user(telegram_id=990030041)
        cls.bulk_url = reverse("moderation:bulk_action")

    def test_requires_staff_forbidden(self) -> None:
        """Non-staff user gets 403."""
        self.client.force_login(self.user)
        response = self.client.post(
            self.bulk_url,
            data=json.dumps(
                {"action": BulkModerationAction.APPROVE.value, "selected_items": []}
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_requires_post_method(self) -> None:
        """GET request returns 405."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.bulk_url)
        self.assertEqual(response.status_code, 405)

    def test_bulk_approve(self) -> None:
        """Bulk approve action approves all selected ads."""
        ad1 = _make_ad(self.user, self.category, self.city, title="Ad 1")
        ad2 = _make_ad(self.user, self.category, self.city, title="Ad 2")

        self.client.force_login(self.staff_user)
        response = self.client.post(
            self.bulk_url,
            data=json.dumps(
                {
                    "action": BulkModerationAction.APPROVE.value,
                    "selected_items": [ad1.id, ad2.id],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["completed"], 2)
        self.assertEqual(data["errors"], [])

        # Verify ads are now published
        ad1.refresh_from_db()
        ad2.refresh_from_db()
        self.assertEqual(ad1.status, AdStatus.PUBLISHED)
        self.assertEqual(ad2.status, AdStatus.PUBLISHED)

    def test_bulk_reject(self) -> None:
        """Bulk reject action rejects all selected ads with reason."""
        ad1 = _make_ad(self.user, self.category, self.city, title="Ad 1")
        ad2 = _make_ad(self.user, self.category, self.city, title="Ad 2")

        self.client.force_login(self.staff_user)
        response = self.client.post(
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

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["completed"], 2)
        self.assertEqual(data["errors"], [])

        # Verify ads are now rejected
        ad1.refresh_from_db()
        ad2.refresh_from_db()
        self.assertEqual(ad1.status, AdStatus.REJECTED)
        self.assertEqual(ad2.status, AdStatus.REJECTED)

    def test_bulk_flag(self) -> None:
        """Bulk flag action recalculates priority for selected ads."""
        ad = _make_ad(self.user, self.category, self.city, title="Flagged ad")

        self.client.force_login(self.staff_user)
        response = self.client.post(
            self.bulk_url,
            data=json.dumps(
                {"action": BulkModerationAction.FLAG.value, "selected_items": [ad.id]}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["completed"], 1)

        # Verify priority record was created
        ad.refresh_from_db()
        self.assertTrue(hasattr(ad, "moderation_priority"))

    def test_bulk_errors_reported(self) -> None:
        """Errors for individual items are reported without failing the whole batch."""
        self.client.force_login(self.staff_user)
        response = self.client.post(
            self.bulk_url,
            data=json.dumps(
                {
                    "action": BulkModerationAction.APPROVE.value,
                    "selected_items": [99999],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["completed"], 0)
        self.assertEqual(len(data["errors"]), 1)
        self.assertEqual(data["errors"][0]["id"], 99999)

    def test_unknown_action_returns_400(self) -> None:
        """Unknown action type is rejected with 400 before any item is processed."""
        self.client.force_login(self.staff_user)
        response = self.client.post(
            self.bulk_url,
            data=json.dumps({"action": "unknown", "selected_items": [1]}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "Unknown action: unknown")

    # ── Finding 01: approve_ad enforces POST-only ─────────────────────────

    def test_approve_ad_get_returns_405(self) -> None:
        """GET to approve_ad endpoint returns 405 Method Not Allowed."""
        ad = _make_ad(self.user, self.category, self.city)

        self.client.force_login(self.staff_user)
        response = self.client.get(f"/moderation/approve/{ad.id}/")

        self.assertEqual(response.status_code, 405)
        # Ad should remain in original status
        ad.refresh_from_db()
        self.assertEqual(ad.status, AdStatus.ON_MODERATION)

    # ── Finding 02: bulk API guards against malformed JSON ─────────────────

    def test_malformed_json_body_returns_400(self) -> None:
        """POST with malformed JSON body returns 400 with error message."""
        self.client.force_login(self.staff_user)
        response = self.client.post(
            self.bulk_url,
            data="not-json",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "Invalid JSON in request body")

    def test_empty_body_returns_400(self) -> None:
        """POST with empty body returns 400 with error message."""
        self.client.force_login(self.staff_user)
        response = self.client.post(
            self.bulk_url,
            data="",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "Invalid JSON in request body")

    # ── Finding 14: bulk API sanitizes error messages ──────────────────────

    def test_error_messages_sanitized(self) -> None:
        """Error messages returned to client are sanitized, not raw exceptions."""
        self.client.force_login(self.staff_user)
        response = self.client.post(
            self.bulk_url,
            data=json.dumps(
                {
                    "action": BulkModerationAction.APPROVE.value,
                    "selected_items": [99999],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["completed"], 0)
        self.assertEqual(len(data["errors"]), 1)
        self.assertEqual(data["errors"][0]["id"], 99999)
        self.assertEqual(data["errors"][0]["error"], "Processing failed")
