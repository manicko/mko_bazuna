"""
Unit tests for TrustCalculator trust scoring service (TASK_043).

Tests cover score calculation, verification bonuses, rejection rate impact,
and trust level mapping. Uses ``django.test.TestCase`` for DB-backed assertions.

Requires a working PostgreSQL database per project spec.
"""

from __future__ import annotations


from django.test import TestCase
from django.utils import timezone

from apps.ads.models import Ad
from apps.analytics.models import AnalyticsEvent
from apps.categories.models import Category
from apps.core.enums import AdSource, AdStatus, AnalyticsEventType, TrustLevel
from apps.locations.models import City
from apps.trust.models import SellerTrustScore, SellerVerification
from apps.trust.services.trust_calculator import TrustCalculator
from apps.users.models import User

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_user(telegram_id: int = 990010001, **overrides: object) -> User:
    """Create a User with sensible defaults for trust tests."""
    defaults: dict = {
        "telegram_id": telegram_id,
        "chat_id": telegram_id,
        "username": None,
        "password": "x",
    }
    defaults.update(overrides)
    return User.objects.create(**defaults)  # type: ignore[arg-type]


def _make_category(slug: str = "trust-test-cat") -> Category:
    """Create a Category with sensible defaults."""
    return Category.objects.create(
        name="Trust Test Category",
        slug=slug,
    )


def _make_city(slug: str = "trust-test-city") -> City:
    """Create a City with sensible defaults."""
    return City.objects.create(
        country_code="ME",
        name="Trust Test City",
        region="Trust Test Region",
        slug=slug,
    )


def _make_ad(
    user: User,
    category: Category,
    city: City,
    *,
    title: str = "Trust Test Ad",
    status: AdStatus = AdStatus.PUBLISHED,
    **overrides: object,
) -> Ad:
    """Create an Ad with sensible defaults for trust tests."""
    defaults: dict = {
        "user": user,
        "title": title,
        "description": "Trust test description",
        "category": category,
        "city": city,
        "category_name": category.name,
        "status": status,
        "source": AdSource.TELEGRAM,
    }
    # DB CheckConstraints require status-specific timestamps to be non-null
    now = timezone.now()
    if status == AdStatus.PUBLISHED:
        defaults["published_at"] = now
    elif status == AdStatus.REJECTED:
        defaults["rejected_at"] = now
    elif status == AdStatus.ON_MODERATION_FAILED:
        defaults["moderation_failed_at"] = now
    defaults.update(overrides)
    return Ad.objects.create(**defaults)  # type: ignore[arg-type]


def _make_verification(
    user: User, *, verified_by_admin: bool = False
) -> SellerVerification:
    """Create a SellerVerification for the given user."""
    return SellerVerification.objects.create(
        user=user,
        verified_by_admin=verified_by_admin,
    )


def _make_event(
    ad: Ad | None,
    event_type: AnalyticsEventType,
    *,
    user: User | None = None,
) -> AnalyticsEvent:
    """Create an AnalyticsEvent with sensible defaults."""
    return AnalyticsEvent.objects.create(
        event_type=event_type,
        ad=ad,
        user=user,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTrustCalculator(TestCase):
    """Comprehensive tests for TrustCalculator scoring algorithm."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create shared fixtures for all test methods."""
        cls.calculator = TrustCalculator()

        cls.category = _make_category()
        cls.city = _make_city()

        cls.user = _make_user(telegram_id=990010001)
        cls.verified_user = _make_user(
            telegram_id=990010002,
            username="verified_seller",
        )
        _make_verification(cls.verified_user, verified_by_admin=True)

        cls.premium_user = _make_user(
            telegram_id=990010003,
            telegram_premium=True,
        )

    # ── helpers ────────────────────────────────────────────────────────

    def _score(self, user: User) -> SellerTrustScore:
        """Convenience: calculate_and_save and return SellerTrustScore."""
        return self.calculator.calculate_and_save(user)

    # ── test_score_with_zero_ads ───────────────────────────────────────

    def test_score_with_zero_ads(self) -> None:
        """Seller with no ads receives minimum score and UNVERIFIED level."""
        empty_user = _make_user(telegram_id=990011001)
        score = self._score(empty_user)

        self.assertEqual(score.score, 0)
        self.assertEqual(score.ad_count_lifetime, 0)
        self.assertEqual(score.ad_count_active, 0)
        self.assertEqual(score.trust_level, TrustLevel.UNVERIFIED)
        self.assertEqual(float(score.rejection_rate), 0.0)
        self.assertEqual(float(score.contact_response_rate), 0.0)

    # ── test_score_with_published_ads ──────────────────────────────────

    def test_score_with_published_ads(self) -> None:
        """Each published ad contributes 5 activity points (quality score from non-rejected ads)."""
        user = _make_user(telegram_id=990012001)

        # Create 3 published ads → activity = 3 * 5 = 15
        for i in range(3):
            _make_ad(
                user,
                self.category,
                self.city,
                title=f"Published Ad {i}",
                status=AdStatus.PUBLISHED,
            )

        score = self._score(user)

        # 3 published ads on activity: 3 * 5 = 15
        # 3 non-draft, 0 rejected → quality: (1 - 0/3) * 30 = 30
        # total = 15 + 30 + 0 = 45
        self.assertEqual(score.score, 45)
        self.assertEqual(score.ad_count_lifetime, 3)
        self.assertEqual(score.ad_count_active, 3)
        self.assertEqual(score.trust_level, TrustLevel.VERIFIED)

    def test_score_caps_at_activity_max(self) -> None:
        """Activity score is capped at 40 (8+ published ads)."""
        user = _make_user(telegram_id=990013001)

        # Create 10 published ads → activity = min(10 * 5, 40) = 40
        for i in range(10):
            _make_ad(
                user,
                self.category,
                self.city,
                title=f"Bulk Ad {i}",
                status=AdStatus.PUBLISHED,
            )

        score = self._score(user)

        # activity: 40 (capped)
        # quality: (1 - 0/10) * 30 = 30
        # total = 40 + 30 + 0 = 70
        self.assertEqual(score.score, 70)
        self.assertEqual(score.ad_count_lifetime, 10)
        self.assertEqual(score.ad_count_active, 10)
        self.assertEqual(score.trust_level, TrustLevel.TRUSTED)

    # ── test_verification_bonus ────────────────────────────────────────

    def test_verification_bonus_admin(self) -> None:
        """Admin-verified seller with low score gets VERIFIED floor."""
        # User with 1 published ad and admin verification
        user = _make_user(telegram_id=990014001)
        _make_verification(user, verified_by_admin=True)

        _make_ad(
            user,
            self.category,
            self.city,
            title="Single Ad",
            status=AdStatus.PUBLISHED,
        )

        score = self._score(user)

        # activity: 1 * 5 = 5
        # quality: (1 - 0/1) * 30 = 30
        # total = 5 + 30 + 0 = 35 → naturally VERIFIED (>= 31)
        self.assertGreaterEqual(score.score, 31)
        self.assertEqual(score.trust_level, TrustLevel.VERIFIED)

    def test_verification_bonus_admin_floor(self) -> None:
        """Admin-verified seller with very low score still gets VERIFIED."""
        user = _make_user(telegram_id=990014002)
        _make_verification(user, verified_by_admin=True)

        # Create 1 published and 5 rejected ads to drive quality down
        _make_ad(
            user,
            self.category,
            self.city,
            title="Good Ad",
            status=AdStatus.PUBLISHED,
        )
        for i in range(5):
            _make_ad(
                user,
                self.category,
                self.city,
                title=f"Rejected Ad {i}",
                status=AdStatus.REJECTED,
            )

        score = self._score(user)

        # activity: 1 * 5 = 5
        # quality: (1 - 5/6) * 30 = (1 - 0.833) * 30 ≈ 5
        # total ≈ 10 → below VERIFIED threshold, but admin verification floors it
        self.assertLess(score.score, 31)
        self.assertEqual(score.trust_level, TrustLevel.VERIFIED)

    def test_verification_bonus_premium(self) -> None:
        """Telegram Premium seller with low score gets VERIFIED floor."""
        user = _make_user(
            telegram_id=990015001,
            telegram_premium=True,
        )

        # Create 1 published and 5 rejected ads to drive quality down
        _make_ad(
            user,
            self.category,
            self.city,
            title="Good Ad",
            status=AdStatus.PUBLISHED,
        )
        for i in range(5):
            _make_ad(
                user,
                self.category,
                self.city,
                title=f"Rejected Ad {i}",
                status=AdStatus.REJECTED,
            )

        score = self._score(user)

        self.assertLess(score.score, 31)
        self.assertEqual(score.trust_level, TrustLevel.VERIFIED)

    # ── test_rejection_penalty ─────────────────────────────────────────

    def test_rejection_penalty(self) -> None:
        """Rejected ads reduce quality score proportionally."""
        user = _make_user(telegram_id=990016001)

        # 2 published + 2 rejected = 4 non-draft ads
        for i in range(2):
            _make_ad(
                user,
                self.category,
                self.city,
                title=f"Published {i}",
                status=AdStatus.PUBLISHED,
            )
        for i in range(2):
            _make_ad(
                user,
                self.category,
                self.city,
                title=f"Rejected {i}",
                status=AdStatus.REJECTED,
            )

        # DRAFT ads should NOT be counted in quality calculation
        _make_ad(
            user,
            self.category,
            self.city,
            title="Draft Ad",
            status=AdStatus.DRAFT,
        )

        score = self._score(user)

        # activity: 2 * 5 = 10
        # quality: (1 - 2/4) * 30 = 15
        # total = 10 + 15 + 0 = 25
        self.assertEqual(score.score, 25)
        self.assertEqual(score.trust_level, TrustLevel.UNVERIFIED)

    def test_full_rejection_all_rejected(self) -> None:
        """Seller with all ads rejected gets quality score of zero."""
        user = _make_user(telegram_id=990017001)

        for i in range(3):
            _make_ad(
                user,
                self.category,
                self.city,
                title=f"Rejected {i}",
                status=AdStatus.REJECTED,
            )

        score = self._score(user)

        # activity: 0 (no published ads)
        # quality: (1 - 3/3) * 30 = 0
        # total = 0
        self.assertEqual(score.score, 0)
        self.assertEqual(score.rejection_rate, 100.0)

    def test_mixed_rejected_and_moderation_failed(self) -> None:
        """Both REJECTED and ON_MODERATION_FAILED count as rejected for quality."""
        user = _make_user(telegram_id=990018001)

        _make_ad(
            user,
            self.category,
            self.city,
            title="Published",
            status=AdStatus.PUBLISHED,
        )
        _make_ad(
            user,
            self.category,
            self.city,
            title="Failed Moderation",
            status=AdStatus.ON_MODERATION_FAILED,
        )

        score = self._score(user)

        # activity: 1 * 5 = 5
        # quality: (1 - 1/2) * 30 = 15
        # total = 20
        self.assertEqual(score.score, 20)

    # ── test_rejection_rate_persistence ────────────────────────────────

    def test_rejection_rate_persistence(self) -> None:
        """Rejection rate is persisted as a percentage in SellerTrustScore."""
        user = _make_user(telegram_id=990019001)

        # 3 published, 1 rejected, 1 moderation_failed = 5 non-draft, 2 rejected
        for i in range(3):
            _make_ad(
                user,
                self.category,
                self.city,
                title=f"Published {i}",
                status=AdStatus.PUBLISHED,
            )
        _make_ad(
            user,
            self.category,
            self.city,
            title="Rejected",
            status=AdStatus.REJECTED,
        )
        _make_ad(
            user,
            self.category,
            self.city,
            title="Failed",
            status=AdStatus.ON_MODERATION_FAILED,
        )

        score = self._score(user)

        # rejection rate: (2 / 5) * 100 = 40.0
        self.assertEqual(float(score.rejection_rate), 40.0)

    # ── test_trust_level_mapping ───────────────────────────────────────

    def test_trust_level_unverified(self) -> None:
        """Score below VERIFIED_THRESHOLD (31) maps to UNVERIFIED (without verification)."""
        user = _make_user(telegram_id=990020001)

        # Create 1 published, 5 rejected to keep score low
        _make_ad(
            user,
            self.category,
            self.city,
            title="Published",
            status=AdStatus.PUBLISHED,
        )
        for i in range(5):
            _make_ad(
                user,
                self.category,
                self.city,
                title=f"Rejected {i}",
                status=AdStatus.REJECTED,
            )

        score = self._score(user)

        self.assertLess(score.score, 31)
        self.assertEqual(score.trust_level, TrustLevel.UNVERIFIED)

    def test_trust_level_verified_threshold(self) -> None:
        """Score at VERIFIED_THRESHOLD (31) maps to VERIFIED."""
        user = _make_user(telegram_id=990021001)

        # Need score >= 31
        # 5 published → activity = 25
        # 3 published, 0 rejected → quality = 30
        # total = 25 + 30 = 55 (well above 31)
        # Let's be more precise: 3 published, 2 rejected (of 5 = 40% rejection)
        # quality = (1 - 2/5) * 30 = 18
        # activity = 3 * 5 = 15
        # total = 15 + 18 = 33

        for i in range(3):
            _make_ad(
                user,
                self.category,
                self.city,
                title=f"Published {i}",
                status=AdStatus.PUBLISHED,
            )
        for i in range(2):
            _make_ad(
                user,
                self.category,
                self.city,
                title=f"Rejected {i}",
                status=AdStatus.REJECTED,
            )

        score = self._score(user)

        self.assertEqual(score.trust_level, TrustLevel.VERIFIED)
        self.assertGreaterEqual(score.score, 31)
        self.assertLess(score.score, 61)

    def test_trust_level_trusted_threshold(self) -> None:
        """Score at TRUSTED_THRESHOLD (61) maps to TRUSTED."""
        user = _make_user(telegram_id=990022001)

        # Need score >= 61
        # 8 published → activity = 40 (capped)
        # 8 non-draft, 0 rejected → quality = 30
        # total = 70 (≥ 61, < 86)
        for i in range(8):
            _make_ad(
                user,
                self.category,
                self.city,
                title=f"Published {i}",
                status=AdStatus.PUBLISHED,
            )

        score = self._score(user)

        self.assertEqual(score.trust_level, TrustLevel.TRUSTED)
        self.assertGreaterEqual(score.score, 61)
        self.assertLess(score.score, 86)

    def test_trust_level_pro_threshold(self) -> None:
        """Score at PRO_THRESHOLD (86) maps to PRO."""
        user = _make_user(telegram_id=990023001)

        # Need score >= 86
        # 8 published → activity = 40
        # Need quality + response to fill the remaining ~46
        # Mock response score to push total over 86
        # With 8 published ads: activity=40, quality=30 → total=70
        # Need response of at least 16 to hit 86

        for i in range(8):
            _make_ad(
                user,
                self.category,
                self.city,
                title=f"Published {i}",
                status=AdStatus.PUBLISHED,
            )

        # Add a global contact-initiated event so response calc denominator > 0
        contact_init_ad = _make_ad(
            _make_user(telegram_id=990023099),
            self.category,
            self.city,
            title="Contact Trigger Ad",
            status=AdStatus.PUBLISHED,
        )
        _make_event(contact_init_ad, AnalyticsEventType.CONTACT_INITIATED)

        # Add user's own response → response = (1/1) * 30 = 30
        _make_event(None, AnalyticsEventType.CONTACT_RESPONSE, user=user)

        score = self._score(user)

        # total = 40 + 30 + int(30) = 100
        self.assertEqual(score.trust_level, TrustLevel.PRO)
        self.assertGreaterEqual(score.score, 86)

    # ── test_response_score ────────────────────────────────────────────

    def test_response_score_with_no_contacts(self) -> None:
        """Response score is 0 when there are no contact-initiated events."""
        user = _make_user(telegram_id=990024001)

        _make_ad(
            user,
            self.category,
            self.city,
            title="Standalone Ad",
            status=AdStatus.PUBLISHED,
        )

        score = self._score(user)

        # No CONTACT_INITIATED events → response = 0.0
        self.assertEqual(float(score.contact_response_rate), 0.0)

    def test_response_score_with_contacts(self) -> None:
        """Response score is proportional to user's responses vs total contacts."""
        user = _make_user(telegram_id=990025001)
        other_user = _make_user(telegram_id=990025099)

        # Create a shared ad to attach events to
        shared_ad = _make_ad(
            other_user,
            self.category,
            self.city,
            title="Shared Contact Ad",
            status=AdStatus.PUBLISHED,
        )

        # 3 total CONTACT_INITIATED events (global)
        for _ in range(3):
            _make_event(shared_ad, AnalyticsEventType.CONTACT_INITIATED)

        # User responds to 2 of them
        for _ in range(2):
            _make_event(None, AnalyticsEventType.CONTACT_RESPONSE, user=user)

        _make_ad(
            user,
            self.category,
            self.city,
            title="My Ad",
            status=AdStatus.PUBLISHED,
        )

        score = self._score(user)

        # response = (2 / 3) * 30 = 20.0
        self.assertEqual(float(score.contact_response_rate), 20.0)

    # ── test_calculate_and_save_idempotent ─────────────────────────────

    def test_calculate_and_save_updates_existing(self) -> None:
        """Calling calculate_and_save twice updates the existing row."""
        user = _make_user(telegram_id=990026001)

        # First call — no ads
        score1 = self._score(user)
        self.assertEqual(score1.score, 0)

        # Add ads and recalculate
        _make_ad(
            user,
            self.category,
            self.city,
            title="New Ad",
            status=AdStatus.PUBLISHED,
        )
        score2 = self._score(user)

        # Same row, updated values
        self.assertEqual(score1.pk, score2.pk)
        self.assertEqual(score2.score, 35)  # 5 + 30 + 0
        self.assertEqual(score2.ad_count_lifetime, 1)
        self.assertEqual(score2.ad_count_active, 1)

    # ── test_calculate_and_save_records_trust_event ────────────────────────

    def test_calculate_and_save_records_trust_event(self) -> None:
        """calculate_and_save records a TRUST_LEVEL_UPDATED analytics event."""
        user = _make_user(telegram_id=990027001)
        self._score(user)

        events = AnalyticsEvent.objects.filter(
            event_type=AnalyticsEventType.TRUST_LEVEL_UPDATED,
            user_id=user.id,
        )
        self.assertEqual(events.count(), 1)

    def test_calculate_and_save_records_on_update(self) -> None:
        """Calling calculate_and_save twice records two TRUST_LEVEL_UPDATED events."""
        user = _make_user(telegram_id=990028001)
        self._score(user)
        self._score(user)

        events = AnalyticsEvent.objects.filter(
            event_type=AnalyticsEventType.TRUST_LEVEL_UPDATED,
            user_id=user.id,
        )
        self.assertEqual(events.count(), 2)
