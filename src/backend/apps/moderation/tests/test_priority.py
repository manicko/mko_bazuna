"""
Unit tests for PriorityCalculator moderation triage service (TASK_044).

Tests cover content scoring, user history assessment, priority level mapping,
escalation detection, and confidence score estimation.
Uses ``django.test.TestCase`` for DB-backed assertions.

Requires a working PostgreSQL database per project spec.
"""

from __future__ import annotations


from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.ads.models import Ad
from apps.categories.models import Category
from apps.core.enums import AdPriorityLevel, AdSource, AdStatus
from apps.locations.models import City
from apps.moderation.models import ModerationCriteria
from apps.moderation.services.priority_calculator import PriorityCalculator
from apps.users.models import User

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_user(telegram_id: int = 990030001, **overrides: object) -> User:
    """Create a User with sensible defaults for priority tests."""
    defaults: dict = {
        "telegram_id": telegram_id,
        "chat_id": telegram_id,
        "username": None,
        "password": "x",
    }
    defaults.update(overrides)
    return User.objects.create(**defaults)  # type: ignore[arg-type]


def _make_category(slug: str = "priority-test-cat") -> Category:
    """Create a Category with sensible defaults."""
    return Category.objects.create(
        name="Priority Test Category",
        slug=slug,
    )


def _make_city(slug: str = "priority-test-city") -> City:
    """Create a City with sensible defaults."""
    return City.objects.create(
        country_code="ME",
        name="Priority Test City",
        region="Priority Test Region",
        slug=slug,
    )


def _make_ad(
    user: User,
    category: Category,
    city: City,
    *,
    title: str = "Priority Test Ad",
    description: str = "Priority test description",
    status: AdStatus = AdStatus.ON_MODERATION,
    **overrides: object,
) -> Ad:
    """Create an Ad with sensible defaults for priority tests."""
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
    # Set status-specific timestamps to satisfy Ad check constraints
    # (e.g. ck_ads_rejected_at_if_rejected). ``auto_now_add`` ignores the
    # constructor value for created_at, so callers backdate via .update().
    if status == AdStatus.REJECTED and "rejected_at" not in defaults:
        defaults["rejected_at"] = timezone.now()
    elif status == AdStatus.ON_MODERATION_FAILED and "moderation_failed_at" not in defaults:
        defaults["moderation_failed_at"] = timezone.now()
    elif status == AdStatus.PUBLISHED and "published_at" not in defaults:
        defaults["published_at"] = timezone.now()
    defaults.update(overrides)
    return Ad.objects.create(**defaults)  # type: ignore[arg-type]


def _banned_words_setup(*words: str) -> None:
    """Seed ModerationCriteria singleton with the given banned words."""
    criteria = ModerationCriteria.get_singleton()
    criteria.banned_words = list(words)
    criteria.save()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPriorityCalculator(TestCase):
    """Comprehensive tests for PriorityCalculator scoring algorithm."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create shared fixtures for all test methods."""
        cls.calculator = PriorityCalculator()

        cls.category = _make_category()
        cls.city = _make_city()

        cls.user = _make_user(telegram_id=990030001)

    # ── test_banned_word_detection ──────────────────────────────────────

    def test_banned_word_detection_in_title(self) -> None:
        """Banned word found in title adds 20 points and flags 'banned_word'."""
        _banned_words_setup("spam", "scam", "cheap")
        ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="Spam offer for you",
            description="Normal description",
        )

        result = self.calculator.calculate_priority(ad)

        self.assertIn("banned_word", result["flags"])
        # Content: 20 (1 banned word), User: 0 → max(20, 0) = 20
        self.assertEqual(result["base_score"], 20)

    def test_banned_word_detection_in_description(self) -> None:
        """Banned word found in description adds 20 points and flags 'banned_word'."""
        _banned_words_setup("scam", "fake")
        ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="Genuine item",
            description="This is not a scam at all",
        )

        result = self.calculator.calculate_priority(ad)

        self.assertIn("banned_word", result["flags"])
        # Content: 20 (1 banned word), User: 0 → max(20, 0) = 20
        self.assertEqual(result["base_score"], 20)

    def test_banned_word_case_insensitive(self) -> None:
        """Banned word matching is case-insensitive."""
        _banned_words_setup("scam")
        ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="SCAM ALERT",
            description="buy now",
        )

        result = self.calculator.calculate_priority(ad)

        self.assertIn("banned_word", result["flags"])
        # Content: 20 (1 banned word), User: 0 → max(20, 0) = 20
        self.assertEqual(result["base_score"], 20)

    def test_banned_word_multiple_words_increase_score(self) -> None:
        """Multiple banned words add 20 points each, capped at 100."""
        _banned_words_setup("spam", "scam", "cheap", "fake", "counterfeit")
        ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="spam scam cheap",
            description="fake counterfeit offer",
        )

        result = self.calculator.calculate_priority(ad)

        # Content: 100 (5 × 20, capped), User: 0 → max(100, 0) = 100
        self.assertEqual(result["base_score"], 100)
        self.assertEqual(result["priority_level"], AdPriorityLevel.HIGH.value)

    def test_banned_word_no_match_returns_zero(self) -> None:
        """No matching banned words yields no banned_word flag and 0 content score."""
        _banned_words_setup("spam", "scam")
        ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="Clean ad title",
            description="Clean description content",
        )

        result = self.calculator.calculate_priority(ad)

        self.assertNotIn("banned_word", result["flags"])
        self.assertEqual(result["base_score"], 0)

    def test_banned_word_empty_list_returns_zero(self) -> None:
        """Empty banned words list yields no banned_word flag."""
        _banned_words_setup()
        ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="Spammy title",
            description="Scam description",
        )

        result = self.calculator.calculate_priority(ad)

        self.assertNotIn("banned_word", result["flags"])
        self.assertEqual(result["base_score"], 0)

    # ── test_established_user_scoring ───────────────────────────────────

    def test_established_user_many_ads(self) -> None:
        """User with >50 ads receives +15 user score."""
        for i in range(51):
            _make_ad(
                self.user,
                self.category,
                self.city,
                title=f"Ad {i}",
                description=f"Description {i}",
                status=AdStatus.PUBLISHED,
            )

        ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="New ad",
            description="New description",
        )

        result = self.calculator.calculate_priority(ad)

        # Content: 0, User: 15 → max(0, 15) = 15
        self.assertEqual(result["base_score"], 15)

    def test_established_user_repeat_offender(self) -> None:
        """>3 rejections in 7 days adds 25 points and flags 'repeat_offender'."""
        now = timezone.now()
        for i in range(4):
            _make_ad(
                self.user,
                self.category,
                self.city,
                title=f"Rejected Ad {i}",
                description=f"Rejected description {i}",
                status=AdStatus.REJECTED,
                created_at=now - timedelta(hours=i),
            )

        ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="New ad",
            description="New description",
        )

        result = self.calculator.calculate_priority(ad)

        self.assertIn("repeat_offender", result["flags"])
        # Content: 0, User: 25 → max(0, 25) = 25
        self.assertEqual(result["base_score"], 25)

    def test_established_user_rejections_outside_window(self) -> None:
        """Rejections older than 7 days do NOT trigger repeat_offender."""
        old = timezone.now() - timedelta(days=10)
        old_rejected_ids: list[int] = []
        for i in range(4):
            ad = _make_ad(
                self.user,
                self.category,
                self.city,
                title=f"Old Rejected {i}",
                description=f"Old description {i}",
                status=AdStatus.REJECTED,
            )
            old_rejected_ids.append(ad.id)

        # auto_now_add=True silently ignores created_at passed to the constructor.
        # Backdate via QuerySet.update(), which bypasses save() and therefore
        # does not trigger auto_now / auto_now_add.
        Ad.objects.filter(id__in=old_rejected_ids).update(created_at=old)

        ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="New ad",
            description="New description",
        )

        result = self.calculator.calculate_priority(ad)

        self.assertNotIn("repeat_offender", result["flags"])
        # Content: 0, User: 0 (rejections > 7 days old) → max(0, 0) = 0
        self.assertEqual(result["base_score"], 0)

    def test_established_user_below_ad_threshold(self) -> None:
        """User with ≤50 ads gets no bonus from ad count."""
        # 49 published + 1 new ad being evaluated = 50 total.
        # Threshold is strict "> 50", so 50 ads -> no bonus.
        for i in range(49):
            _make_ad(
                self.user,
                self.category,
                self.city,
                title=f"Ad {i}",
                description=f"Description {i}",
                status=AdStatus.PUBLISHED,
            )

        ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="New ad",
            description="New description",
        )

        result = self.calculator.calculate_priority(ad)

        # Content: 0, User: 0 (≤50 ads, no recent rejections) → max(0, 0) = 0
        self.assertEqual(result["base_score"], 0)

    def test_established_user_combined_bonus(self) -> None:
        """Both >50 ads and repeat offender stack for combined user score of 40."""
        now = timezone.now()
        for i in range(4):
            _make_ad(
                self.user,
                self.category,
                self.city,
                title=f"Rejected Ad {i}",
                description=f"Rejected description {i}",
                status=AdStatus.REJECTED,
                created_at=now - timedelta(hours=i),
            )
        for i in range(51):
            _make_ad(
                self.user,
                self.category,
                self.city,
                title=f"Ad {i}",
                description=f"Description {i}",
                status=AdStatus.PUBLISHED,
            )

        ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="New ad",
            description="New description",
        )

        result = self.calculator.calculate_priority(ad)

        # Content: 0, User: 40 (15 + 25) → max(0, 40) = 40
        self.assertEqual(result["base_score"], 40)
        self.assertIn("repeat_offender", result["flags"])

    # ── test_priority_level_mapping ─────────────────────────────────────

    def test_priority_level_low_from_public_api(self) -> None:
        """Score < 50 maps to LOW priority level via calculate_priority."""
        _banned_words_setup()
        ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="Clean title",
            description="Clean description",
        )

        result = self.calculator.calculate_priority(ad)

        self.assertEqual(result["priority_level"], AdPriorityLevel.LOW.value)
        self.assertLess(result["base_score"], 50)

    def test_priority_level_medium_from_public_api(self) -> None:
        """Score 50-79 maps to MEDIUM priority level via calculate_priority."""
        now = timezone.now()
        for i in range(4):
            _make_ad(
                self.user,
                self.category,
                self.city,
                title=f"Rejected {i}",
                description=f"Rejected description {i}",
                status=AdStatus.REJECTED,
                created_at=now - timedelta(hours=i),
            )
        for i in range(51):
            _make_ad(
                self.user,
                self.category,
                self.city,
                title=f"Ad {i}",
                description=f"Description {i}",
                status=AdStatus.PUBLISHED,
            )

        # 3 banned words → content = 60; user = 40 → max(60, 40) = 60 → MEDIUM
        _banned_words_setup("spam", "scam", "cheap")
        ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="spam scam cheap title",
            description="spam scam cheap description",
        )

        result = self.calculator.calculate_priority(ad)

        self.assertEqual(result["base_score"], 60)
        self.assertEqual(result["priority_level"], AdPriorityLevel.MEDIUM.value)

    def test_priority_level_boundaries(self) -> None:
        """Verify score-to-level mapping at exact boundaries via _get_priority_level."""
        # 0-49 → LOW
        self.assertEqual(
            self.calculator._get_priority_level(0), AdPriorityLevel.LOW,
        )
        self.assertEqual(
            self.calculator._get_priority_level(49), AdPriorityLevel.LOW,
        )
        # 50-79 → MEDIUM
        self.assertEqual(
            self.calculator._get_priority_level(50), AdPriorityLevel.MEDIUM,
        )
        self.assertEqual(
            self.calculator._get_priority_level(79), AdPriorityLevel.MEDIUM,
        )
        # 80-100 → HIGH
        self.assertEqual(
            self.calculator._get_priority_level(80), AdPriorityLevel.HIGH,
        )
        self.assertEqual(
            self.calculator._get_priority_level(100), AdPriorityLevel.HIGH,
        )

    # ── test_escalation_required ────────────────────────────────────────

    def test_escalation_required_when_flag_count_reaches_three(self) -> None:
        """Escalation is required when len(flags) >= 3."""
        now = timezone.now()
        for i in range(4):
            _make_ad(
                self.user,
                self.category,
                self.city,
                title=f"Rejected {i}",
                description=f"Rejected description {i}",
                status=AdStatus.REJECTED,
                created_at=now - timedelta(hours=i),
            )

        _banned_words_setup("spam", "scam", "cheap")
        ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="spam scam cheap offer",
            description="spam scam cheap offer description",
        )

        result = self.calculator.calculate_priority(ad)

        # Flags: 3× "banned_word" + 1× "repeat_offender" = 4 flags >= 3
        self.assertTrue(result["escalation_required"])
        self.assertGreaterEqual(len(result["flags"]), 3)

    def test_escalation_not_required_when_low_score_and_few_flags(self) -> None:
        """Escalation is not required when score < 80 and flags < 3."""
        _banned_words_setup()
        ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="Clean title",
            description="Clean description",
        )

        result = self.calculator.calculate_priority(ad)

        self.assertFalse(result["escalation_required"])
        self.assertEqual(result["base_score"], 0)
        self.assertEqual(len(result["flags"]), 0)

    def test_escalation_flag_logic_is_or(self) -> None:
        """Escalation condition uses OR — either high score OR many flags triggers it."""
        # Create scenario with 2 banned words → flags = ["banned_word", "banned_word"] = 2
        _banned_words_setup("spam", "scam")
        ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="spam scam title",
            description="spam scam description",
        )

        result = self.calculator.calculate_priority(ad)

        # Content: 40, User: 0, total: 40, flags: 2
        # 40 < 80 AND 2 < 3 → escalation_required = False
        self.assertFalse(result["escalation_required"])
        self.assertEqual(len(result["flags"]), 2)

    # ── test_confidence_score_estimation ────────────────────────────────

    def test_confidence_score_default_in_public_api(self) -> None:
        """Confidence score is 0.7 (placeholder for future ML) via calculate_priority."""
        result = self.calculator.calculate_priority(
            _make_ad(
                self.user,
                self.category,
                self.city,
                title="Any title",
                description="Any description",
            ),
        )

        self.assertEqual(result["confidence_score"], 0.7)

    def test_confidence_score_direct_method(self) -> None:
        """_estimate_confidence returns 0.7 for any ad."""
        ad = _make_ad(
            self.user,
            self.category,
            self.city,
            title="Test",
            description="Test description",
        )
        confidence = self.calculator._estimate_confidence(ad)
        self.assertEqual(confidence, 0.7)