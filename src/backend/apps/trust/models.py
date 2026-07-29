"""
SellerTrustScore and SellerVerification models for trust scoring.

Tracks seller trust levels, verification status, and performance metrics.
"""

from apps.core.enums import TrustLevel
from django.db import models


class SellerTrustScore(models.Model):
    """Per-seller trust scoring with performance metrics."""

    user = models.OneToOneField(
        "users.User",
        on_delete=models.CASCADE,
        related_name="trust_score",
    )
    trust_level = models.CharField(
        max_length=20,
        choices=[(level.value, level.value) for level in TrustLevel],
        default=TrustLevel.UNVERIFIED,
    )
    score = models.PositiveSmallIntegerField(default=0)
    ad_count_lifetime = models.PositiveIntegerField(default=0)
    ad_count_active = models.PositiveIntegerField(default=0)
    rejection_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    contact_response_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.0
    )
    last_calculated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "seller_trust_scores"


class SellerVerification(models.Model):
    """Seller verification status (admin and phone)."""

    user = models.OneToOneField(
        "users.User",
        on_delete=models.CASCADE,
        related_name="verification",
    )
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    verified_by_admin = models.BooleanField(default=False)
    verified_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "seller_verifications"