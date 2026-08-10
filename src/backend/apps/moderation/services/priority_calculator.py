"""
Priority calculator service for moderation queue triage.

Computes priority scores based on content and user history,
mapping scores to AdPriorityLevel enum values.
"""

import logging
from datetime import timedelta

from django.utils import timezone

from apps.ads.models import Ad
from apps.core.enums import AdPriorityLevel, AdStatus
from apps.moderation.models import ModerationCriteria

logger = logging.getLogger(__name__)


class PriorityCalculator:
    """Calculate priority scores for ads based on content and user history."""

    def calculate_priority(self, ad: Ad) -> dict:
        """Calculate comprehensive priority score for an ad.

        Returns dict with keys matching AdModerationPriority model fields
        for direct use in update_or_create defaults.
        """
        scores: list[int] = []
        flags: list[str] = []

        content_score = self._calculate_content_score(ad)
        scores.append(content_score["score"])
        flags.extend(content_score["flags"])

        user_score = self._calculate_user_score(ad)
        scores.append(user_score["score"])
        flags.extend(user_score["flags"])

        # Take the worst-case (highest) score across content and user-history
        # signals. Averaging would dilute a strong content signal (e.g. 5 banned
        # words → 100) to 50 when the user has no history, incorrectly lowering
        # priority for toxic new-user ads. max() ensures the highest-risk signal
        # dominates, consistent with the escalation_required logic below.
        total = max(scores) if scores else 0

        return {
            "base_score": total,
            "priority_level": self._get_priority_level(total).value,
            "flags": flags,
            "confidence_score": self._estimate_confidence(ad),
            "escalation_required": total >= 80 or len(flags) >= 3,
        }

    def _calculate_content_score(self, ad: Ad) -> dict:
        """Score based on content analysis — banned words and suspicious patterns."""
        criteria = ModerationCriteria.get_singleton()
        flags: list[str] = []
        score = 0

        if criteria.banned_words:
            combined = f"{ad.title} {ad.description}".lower()
            for word in criteria.banned_words:  # pyright: ignore[reportGeneralTypeIssues]
                if word.lower() in combined:
                    flags.append("banned_word")
                    score += 20

        return {"score": min(score, 100), "flags": flags}

    def _calculate_user_score(self, ad: Ad) -> dict:
        """Score based on user history — repeat offender status, recent rejections."""
        flags: list[str] = []
        score = 0

        user_ad_count = Ad.objects.filter(user=ad.user).count()
        if user_ad_count > 50:
            score += 15

        recent_failures = Ad.objects.filter(
            user=ad.user,
            status__in=[AdStatus.REJECTED, AdStatus.ON_MODERATION_FAILED],
            created_at__gte=timezone.now() - timedelta(days=7),
        ).count()

        if recent_failures > 3:
            flags.append("repeat_offender")
            score += 25

        return {"score": min(score, 100), "flags": flags}

    def _get_priority_level(self, score: int) -> AdPriorityLevel:
        """Map a 0-100 score to the corresponding priority level enum."""
        if score >= 80:
            return AdPriorityLevel.HIGH
        if score >= 50:
            return AdPriorityLevel.MEDIUM
        return AdPriorityLevel.LOW

    def _estimate_confidence(self, ad: Ad) -> float:
        """Estimate AI confidence in classification (placeholder for future ML)."""
        return 0.7