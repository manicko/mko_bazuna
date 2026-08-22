"""
Tests for PriorityCalculator moderation triage service (TASK_044).

Covers content scoring, user history assessment, priority level mapping,
escalation detection, and confidence score via the **public** ``calculate_priority``
API only (no private-method coupling).

Migrated from ``django.test.TestCase`` to pytest-django (``@pytest.mark.django_db``)
per the test-optimization plan.  Uses the canonical root-conftest fixtures
(``seller``, ``category``, ``city``) and ``create_test_ad`` helper instead of
local duplicates.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.ads.models import Ad
from apps.core.enums import AdPriorityLevel, AdStatus
from apps.moderation.models import ModerationCriteria
from apps.moderation.services.priority_calculator import PriorityCalculator
from apps.moderation.services.priority import PriorityService

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _banned_words_setup(*words: str) -> None:
    """Seed ModerationCriteria singleton with the given banned words."""
    criteria = ModerationCriteria.get_singleton()
    criteria.banned_words = list(words)
    criteria.save()


@pytest.fixture
def calculator() -> PriorityCalculator:
    """A fresh PriorityCalculator instance (no state to reset)."""
    return PriorityCalculator()


# ---------------------------------------------------------------------------
# Tests: banned-word content scoring
# ---------------------------------------------------------------------------


class TestPriorityCalculator:
    """Tests for PriorityCalculator.calculate_priority (public API)."""

    def test_banned_word_in_title(self, calculator, seller, category, city) -> None:
        """One banned word in title → content score 20, flag 'banned_word'."""
        _banned_words_setup("spam", "scam", "cheap")
        ad = create_test_ad(
            seller,
            category,
            city,
            title="Spam offer for you",
            description="Normal description",
        )

        result = calculator.calculate_priority(ad)

        assert "banned_word" in result["flags"]
        assert result["base_score"] == 20  # max(20, 0)

    def test_banned_word_in_description(self, calculator, seller, category, city) -> None:
        """One banned word in description → content score 20."""
        _banned_words_setup("scam", "fake")
        ad = create_test_ad(
            seller,
            category,
            city,
            title="Genuine item",
            description="This is not a scam at all",
        )

        result = calculator.calculate_priority(ad)

        assert "banned_word" in result["flags"]
        assert result["base_score"] == 20

    def test_banned_word_case_insensitive(
        self, calculator, seller, category, city
    ) -> None:
        """Banned word matching is case-insensitive."""
        _banned_words_setup("scam")
        ad = create_test_ad(
            seller,
            category,
            city,
            title="SCAM ALERT",
            description="buy now",
        )

        result = calculator.calculate_priority(ad)

        assert "banned_word" in result["flags"]
        assert result["base_score"] == 20

    def test_banned_word_multiple_capped_at_100(
        self, calculator, seller, category, city
    ) -> None:
        """5 banned words → 100 (capped), priority_level HIGH."""
        _banned_words_setup("spam", "scam", "cheap", "fake", "counterfeit")
        ad = create_test_ad(
            seller,
            category,
            city,
            title="spam scam cheap",
            description="fake counterfeit offer",
        )

        result = calculator.calculate_priority(ad)

        assert result["base_score"] == 100
        assert result["priority_level"] == AdPriorityLevel.HIGH.value

    def test_no_banned_words_zero_score(
        self, calculator, seller, category, city
    ) -> None:
        """No matching banned words → no flag, score 0."""
        _banned_words_setup("spam", "scam")
        ad = create_test_ad(
            seller,
            category,
            city,
            title="Clean ad title",
            description="Clean description content",
        )

        result = calculator.calculate_priority(ad)

        assert "banned_word" not in result["flags"]
        assert result["base_score"] == 0

    def test_empty_banned_words_list_zero_score(
        self, calculator, seller, category, city
    ) -> None:
        """Empty banned words list → no flag."""
        _banned_words_setup()
        ad = create_test_ad(
            seller,
            category,
            city,
            title="Spammy title",
            description="Scam description",
        )

        result = calculator.calculate_priority(ad)

        assert "banned_word" not in result["flags"]
        assert result["base_score"] == 0


# ---------------------------------------------------------------------------
# Tests: user-history scoring
# ---------------------------------------------------------------------------


class TestUserHistoryScoring:
    """Tests for PriorityCalculator user-score component."""

    def test_many_ads_user_score_bonus(
        self, calculator, seller, category, city
    ) -> None:
        """User with >50 ads receives +15 user score."""
        _banned_words_setup()
        for i in range(51):
            create_test_ad(
                seller,
                category,
                city,
                title=f"Ad {i}",
                description=f"Description {i}",
                status=AdStatus.PUBLISHED,
            )

        ad = create_test_ad(
            seller,
            category,
            city,
            title="New ad",
            description="New description",
        )

        result = calculator.calculate_priority(ad)

        assert result["base_score"] == 15  # max(0, 15)

    def test_repeat_offender_flag(
        self, calculator, seller, category, city
    ) -> None:
        """>3 rejections in 7 days → +25 user score, flag 'repeat_offender'."""
        _banned_words_setup()
        now = timezone.now()
        for i in range(4):
            create_test_ad(
                seller,
                category,
                city,
                title=f"Rejected Ad {i}",
                description=f"Rejected description {i}",
                status=AdStatus.REJECTED,
                created_at=now - timedelta(hours=i),
            )

        ad = create_test_ad(
            seller,
            category,
            city,
            title="New ad",
            description="New description",
        )

        result = calculator.calculate_priority(ad)

        assert "repeat_offender" in result["flags"]
        assert result["base_score"] == 25  # max(0, 25)

    def test_rejections_outside_window_no_bonus(
        self, calculator, seller, category, city
    ) -> None:
        """Rejections older than 7 days do NOT trigger repeat_offender."""
        _banned_words_setup()
        old = timezone.now() - timedelta(days=10)
        old_ids: list[int] = []
        for i in range(4):
            a = create_test_ad(
                seller,
                category,
                city,
                title=f"Old Rejected {i}",
                description=f"Old description {i}",
                status=AdStatus.REJECTED,
            )
            old_ids.append(a.id)
        Ad.objects.filter(id__in=old_ids).update(created_at=old)

        ad = create_test_ad(
            seller,
            category,
            city,
            title="New ad",
            description="New description",
        )

        result = calculator.calculate_priority(ad)

        assert "repeat_offender" not in result["flags"]
        assert result["base_score"] == 0  # max(0, 0)

    def test_below_ad_threshold_no_bonus(
        self, calculator, seller, category, city
    ) -> None:
        """User with ≤50 ads gets no bonus from ad count."""
        _banned_words_setup()
        for i in range(49):
            create_test_ad(
                seller,
                category,
                city,
                title=f"Ad {i}",
                description=f"Description {i}",
                status=AdStatus.PUBLISHED,
            )

        ad = create_test_ad(
            seller,
            category,
            city,
            title="New ad",
            description="New description",
        )

        result = calculator.calculate_priority(ad)

        assert result["base_score"] == 0

    def test_combined_bonus(
        self, calculator, seller, category, city
    ) -> None:
        """Both >50 ads and repeat offender stack for combined user score of 40."""
        _banned_words_setup()
        now = timezone.now()
        for i in range(4):
            create_test_ad(
                seller,
                category,
                city,
                title=f"Rejected Ad {i}",
                description=f"Rejected description {i}",
                status=AdStatus.REJECTED,
                created_at=now - timedelta(hours=i),
            )
        for i in range(51):
            create_test_ad(
                seller,
                category,
                city,
                title=f"Ad {i}",
                description=f"Description {i}",
                status=AdStatus.PUBLISHED,
            )

        ad = create_test_ad(
            seller,
            category,
            city,
            title="New ad",
            description="New description",
        )

        result = calculator.calculate_priority(ad)

        assert result["base_score"] == 40  # max(0, 40)
        assert "repeat_offender" in result["flags"]


# ---------------------------------------------------------------------------
# Tests: score→level boundary mapping (public API, G-09 + G-10)
# ---------------------------------------------------------------------------


class TestPriorityLevelBoundaries:
    """Verify score→level mapping through the public ``calculate_priority`` API.

    The content score increments in steps of 20 (banned-word count × 20, capped
    at 100).  Combined with max(content, user_score), the achievable scores at
    or near the LOW/MEDIUM/HIGH thresholds (50, 80) are: 0, 20, 40, 60, 80, 100.
    """

    def test_score_zero_maps_to_low(self, calculator, seller, category, city) -> None:
        """Score 0 (no banned words, no user history) → LOW."""
        _banned_words_setup()
        ad = create_test_ad(seller, category, city, title="Clean", description="Clean")
        result = calculator.calculate_priority(ad)
        assert result["base_score"] == 0
        assert result["priority_level"] == AdPriorityLevel.LOW.value

    def test_score_40_below_medium_threshold_maps_to_low(
        self, calculator, seller, category, city
    ) -> None:
        """Score 40 (2 banned words) → LOW (below the 50 threshold)."""
        _banned_words_setup("spam", "scam")
        ad = create_test_ad(
            seller, category, city, title="spam scam", description="desc"
        )
        result = calculator.calculate_priority(ad)
        assert result["base_score"] == 40
        assert result["priority_level"] == AdPriorityLevel.LOW.value

    def test_score_60_maps_to_medium(
        self, calculator, seller, category, city
    ) -> None:
        """Score 60 (3 banned words) → MEDIUM (at or above the 50 threshold)."""
        _banned_words_setup("spam", "scam", "cheap")
        ad = create_test_ad(
            seller, category, city, title="spam scam cheap", description="desc"
        )
        result = calculator.calculate_priority(ad)
        assert result["base_score"] == 60
        assert result["priority_level"] == AdPriorityLevel.MEDIUM.value

    def test_score_80_maps_to_high(self, calculator, seller, category, city) -> None:
        """Score 80 (4 banned words) → HIGH (at or above the 80 threshold)."""
        _banned_words_setup("spam", "scam", "cheap", "fake")
        ad = create_test_ad(
            seller, category, city, title="spam scam cheap fake", description="desc"
        )
        result = calculator.calculate_priority(ad)
        assert result["base_score"] == 80
        assert result["priority_level"] == AdPriorityLevel.HIGH.value

    def test_score_100_maps_to_high(
        self, calculator, seller, category, city
    ) -> None:
        """Score 100 (5+ banned words, capped) → HIGH."""
        _banned_words_setup("spam", "scam", "cheap", "fake", "counterfeit")
        ad = create_test_ad(
            seller,
            category,
            city,
            title="spam scam cheap fake counterfeit",
            description="desc",
        )
        result = calculator.calculate_priority(ad)
        assert result["base_score"] == 100
        assert result["priority_level"] == AdPriorityLevel.HIGH.value


# ---------------------------------------------------------------------------
# Tests: escalation_required
# ---------------------------------------------------------------------------


class TestEscalationRequired:
    """Tests for the ``escalation_required`` flag in the public API."""

    def test_escalation_when_flag_count_reaches_three(
        self, calculator, seller, category, city
    ) -> None:
        """Escalation is required when len(flags) >= 3."""
        now = timezone.now()
        for i in range(4):
            create_test_ad(
                seller,
                category,
                city,
                title=f"Rejected {i}",
                description=f"Rejected description {i}",
                status=AdStatus.REJECTED,
                created_at=now - timedelta(hours=i),
            )

        _banned_words_setup("spam", "scam", "cheap")
        ad = create_test_ad(
            seller,
            category,
            city,
            title="spam scam cheap offer",
            description="spam scam cheap offer description",
        )

        result = calculator.calculate_priority(ad)

        # Flags: 3× "banned_word" + 1× "repeat_offender" = 4 flags >= 3
        assert result["escalation_required"] is True
        assert len(result["flags"]) >= 3

    def test_no_escalation_when_low_score_and_few_flags(
        self, calculator, seller, category, city
    ) -> None:
        """Escalation is not required when score < 80 and flags < 3."""
        _banned_words_setup()
        ad = create_test_ad(
            seller, category, city, title="Clean", description="Clean"
        )

        result = calculator.calculate_priority(ad)

        assert result["escalation_required"] is False
        assert result["base_score"] == 0
        assert len(result["flags"]) == 0

    def test_escalation_or_logic(
        self, calculator, seller, category, city
    ) -> None:
        """Escalation condition uses OR — 2 banned words (score 40, 2 flags) → not required."""
        _banned_words_setup("spam", "scam")
        ad = create_test_ad(
            seller, category, city, title="spam scam", description="spam scam"
        )

        result = calculator.calculate_priority(ad)

        # Content: 40, User: 0, total: 40, flags: 2
        # 40 < 80 AND 2 < 3 → escalation_required = False
        assert result["escalation_required"] is False
        assert len(result["flags"]) == 2


# ---------------------------------------------------------------------------
# Tests: confidence score (public API, G-09)
# ---------------------------------------------------------------------------


class TestConfidenceScore:
    """Tests for the ``confidence_score`` field in ``calculate_priority`` return dict."""

    def test_confidence_score_is_0_7_placeholder(self, calculator, seller, category, city) -> None:
        """Confidence score is 0.7 (placeholder for future ML) via calculate_priority."""
        _banned_words_setup()
        ad = create_test_ad(
            seller, category, city, title="Any title", description="Any description"
        )

        result = calculator.calculate_priority(ad)

        assert result["confidence_score"] == 0.7

    def test_confidence_score_is_constant_across_states(
        self, calculator, seller, category, city
    ) -> None:
        """Confidence score is always 0.7 regardless of ad content/state."""
        _banned_words_setup("spam", "scam", "cheap", "fake", "counterfeit")
        ad = create_test_ad(
            seller,
            category,
            city,
            title="spam scam cheap fake counterfeit",
            description="desc",
        )

        result = calculator.calculate_priority(ad)

        assert result["confidence_score"] == 0.7


# ---------------------------------------------------------------------------
# Tests: PriorityService persisted boundary levels (G-10)
# ---------------------------------------------------------------------------


class TestPriorityServiceBoundaries:
    """Persist ``AdModerationPriority`` rows via ``calculate_and_save`` and
    verify the ``priority_level`` column at achievable score boundaries.

    The scoring system produces discrete values (multiples of 20 for content
    score).  These tests verify the persisted ``priority_level`` matches the
    ``calculate_priority`` return value at each boundary.
    """

    @pytest.mark.parametrize(
        ("banned_count", "expected_score", "expected_level"),
        [
            (0, 0, AdPriorityLevel.LOW),
            (1, 20, AdPriorityLevel.LOW),
            (2, 40, AdPriorityLevel.LOW),
            (3, 60, AdPriorityLevel.MEDIUM),
            (4, 80, AdPriorityLevel.HIGH),
            (5, 100, AdPriorityLevel.HIGH),
        ],
    )
    def test_persisted_priority_level_at_boundaries(
        self,
        banned_count: int,
        expected_score: int,
        expected_level: AdPriorityLevel,
        seller,
        category,
        city,
    ) -> None:
        """``calculate_and_save`` persists the correct ``priority_level`` for each score."""
        words = ["spam", "scam", "cheap", "fake", "counterfeit", "extra1"]
        _banned_words_setup(*words[:banned_count])

        title = " ".join(words[:banned_count])
        ad = create_test_ad(seller, category, city, title=title, description="desc")

        service = PriorityService()
        priority = service.calculate_and_save(ad)

        assert priority.base_score == expected_score
        assert priority.priority_level == expected_level.value

    def test_persisted_priority_updated_on_recalculate(
        self, seller, category, city
    ) -> None:
        """Calling ``calculate_and_save`` twice updates the existing row (not a duplicate)."""
        _banned_words_setup()
        ad = create_test_ad(seller, category, city, title="Clean", description="Clean")

        service = PriorityService()
        first = service.calculate_and_save(ad)

        # Now add banned words and recalculate.
        _banned_words_setup("spam")
        create_test_ad(seller, category, city, title="spam", description="x")  # bump user's ad count
        ad.title = "spam"
        ad.save(update_fields=["title"])
        second = service.calculate_and_save(ad)

        assert first.id == second.id
        assert second.base_score == 20
