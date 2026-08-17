"""
TrustCalculator service for computing and persisting seller trust scores.

Calculates trust scores from multiple factors (activity, quality, response rate)
and maps the total score to a TrustLevel for badge display.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apps.ads.models import Ad
from apps.analytics.services.trust_analytics import record_trust_event
from apps.core.enums import AdStatus, AnalyticsEventType, TrustLevel
from apps.trust.models import SellerTrustScore

if TYPE_CHECKING:
    from apps.users.models import User

logger = logging.getLogger(__name__)


class TrustCalculator:
    """Calculate and persist trust scores for sellers."""

    # Weights for each scoring component.
    _ACTIVITY_MAX = 40
    _QUALITY_MAX = 30
    _RESPONSE_MAX = 30
    _SCORE_TOTAL = _ACTIVITY_MAX + _QUALITY_MAX + _RESPONSE_MAX  # 100

    # Points per active ad for activity score.
    _ACTIVITY_POINTS_PER_AD = 5

    # Thresholds for trust level mapping.
    _PRO_THRESHOLD = 86
    _TRUSTED_THRESHOLD = 61
    _VERIFIED_THRESHOLD = 31

    def calculate_and_save(self, user: User) -> SellerTrustScore:
        """Calculate trust score and persist to SellerTrustScore model.

        Args:
            user: The seller user to compute score for.

        Returns:
            The created or updated SellerTrustScore instance.
        """
        activity_score = self._calculate_activity_score(user)
        quality_score = self._calculate_quality_score(user)
        response_score = self._calculate_response_score(user)

        total = activity_score + quality_score + int(response_score)
        level = self._get_trust_level(total, user)

        trust_score, created = SellerTrustScore.objects.get_or_create(
            user=user,
            defaults={
                "trust_level": level,
                "score": total,
                "ad_count_lifetime": self._count_lifetime_ads(user),
                "ad_count_active": self._count_active_ads(user),
                "rejection_rate": self._calculate_rejection_rate(user),
                "contact_response_rate": response_score,
            },
        )
        if created:
            logger.info("Created trust score for user %s", user.id)
        else:
            trust_score.trust_level = level
            trust_score.score = total
            trust_score.ad_count_lifetime = self._count_lifetime_ads(user)
            trust_score.ad_count_active = self._count_active_ads(user)
            trust_score.rejection_rate = self._calculate_rejection_rate(user)
            trust_score.contact_response_rate = response_score
            trust_score.save(
                update_fields=[
                    "trust_level",
                    "score",
                    "ad_count_lifetime",
                    "ad_count_active",
                    "rejection_rate",
                    "contact_response_rate",
                ]
            )
            logger.info("Updated trust score for user %s", user.id)
        record_trust_event(user.id, AnalyticsEventType.TRUST_LEVEL_UPDATED)

        return trust_score

    def _calculate_activity_score(self, user: User) -> int:
        """Calculate activity score based on active (published) ads.

        Each published ad contributes ACTIVITY_POINTS_PER_AD points,
        capped at ACTIVITY_MAX.

        Args:
            user: The seller user.

        Returns:
            Activity score in range 0-ACTIVITY_MAX.
        """
        active_count = Ad.objects.filter(
            user=user,
            status=AdStatus.PUBLISHED,
        ).count()
        return min(active_count * self._ACTIVITY_POINTS_PER_AD, self._ACTIVITY_MAX)

    def _calculate_quality_score(self, user: User) -> int:
        """Calculate quality score based on moderation outcomes.

        Higher rejection/loss rate yields lower quality score.
        Only non-draft ads are considered.

        Args:
            user: The seller user.

        Returns:
            Quality score in range 0-QUALITY_MAX.
        """
        total = Ad.objects.filter(user=user).exclude(status=AdStatus.DRAFT).count()
        rejected = Ad.objects.filter(
            user=user,
            status__in=[AdStatus.REJECTED, AdStatus.ON_MODERATION_FAILED],
        ).count()
        if total == 0:
            return 0
        return int((1 - rejected / total) * self._QUALITY_MAX)

    def _calculate_response_score(self, user: User) -> float:
        """Calculate response score based on contact response rate.

        Ratio of CONTACT_RESPONSE events to total CONTACT_INITIATED events,
        scaled to RESPONSE_MAX.

        Args:
            user: The seller user.

        Returns:
            Response score in range 0.0-RESPONSE_MAX.
        """
        from apps.analytics.models import AnalyticsEvent

        total_contacts = AnalyticsEvent.objects.filter(
            event_type=AnalyticsEventType.CONTACT_INITIATED,
        ).count()

        if total_contacts == 0:
            return 0.0

        responses = AnalyticsEvent.objects.filter(
            user_id=user.id,
            event_type=AnalyticsEventType.CONTACT_RESPONSE,
        ).count()

        return round((responses / total_contacts) * self._RESPONSE_MAX, 2)

    def _calculate_rejection_rate(self, user: User) -> float:
        """Calculate rejection rate percentage for persistence.

        Args:
            user: The seller user.

        Returns:
            Rejection rate as a float percentage (0.0-100.0).
        """
        total = Ad.objects.filter(user=user).exclude(status=AdStatus.DRAFT).count()
        rejected = Ad.objects.filter(
            user=user,
            status__in=[AdStatus.REJECTED, AdStatus.ON_MODERATION_FAILED],
        ).count()
        if total == 0:
            return 0.0
        return round((rejected / total) * 100, 2)

    def _count_lifetime_ads(self, user: User) -> int:
        """Count all non-draft ads for lifetime metric.

        Args:
            user: The seller user.

        Returns:
            Total non-draft ad count.
        """
        return Ad.objects.filter(user=user).exclude(status=AdStatus.DRAFT).count()

    def _count_active_ads(self, user: User) -> int:
        """Count currently published ads for active metric.

        Args:
            user: The seller user.

        Returns:
            Published ad count.
        """
        return Ad.objects.filter(
            user=user,
            status=AdStatus.PUBLISHED,
        ).count()

    def _get_trust_level(self, score: int, user: User) -> TrustLevel:
        """Determine trust level based on score and seller attributes.

        Mapping:
            score >= PRO_THRESHOLD (86): PRO
            score >= TRUSTED_THRESHOLD (61): TRUSTED
            score >= VERIFIED_THRESHOLD (31): VERIFIED
            otherwise: UNVERIFIED

        Verified sellers (admin verification or Telegram Premium) are
        guaranteed at least VERIFIED level.

        Args:
            score: Total trust score (0-SCORE_TOTAL).
            user: The seller user (used for verification/premium checks).

        Returns:
            The computed TrustLevel value.
        """
        if score >= self._PRO_THRESHOLD:
            return TrustLevel.PRO
        if score >= self._TRUSTED_THRESHOLD:
            return TrustLevel.TRUSTED
        if score >= self._VERIFIED_THRESHOLD:
            return TrustLevel.VERIFIED

        # Floor to VERIFIED if seller has admin verification or Telegram Premium.
        has_verification = hasattr(user, "verification") and bool(
            user.verification.verified_by_admin  # type: ignore[union-attr]
        )
        has_premium = getattr(user, "telegram_premium", False)

        if has_verification or has_premium:
            return TrustLevel.VERIFIED

        return TrustLevel.UNVERIFIED
