"""
Template tags for rendering trust badges.

Provides the ``render_trust_badge`` simple tag that renders the correct
badge template (verified / trusted / pro) based on the seller's trust level.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apps.core.enums import TrustLevel
from apps.trust.models import SellerTrustScore
from django import template
from django.template.loader import render_to_string

if TYPE_CHECKING:
    from apps.users.models import User

logger = logging.getLogger(__name__)

register = template.Library()

BADGE_TEMPLATES: dict[TrustLevel, str] = {
    TrustLevel.VERIFIED: "components/badges/verified_badge.html",
    TrustLevel.TRUSTED: "components/badges/trusted_badge.html",
    TrustLevel.PRO: "components/badges/pro_badge.html",
}


@register.simple_tag(takes_context=True)
def render_trust_badge(context: template.Context, user: User) -> str:
    """Render a trust badge for the given user based on their trust level.

    Selects the correct badge template (verified / trusted / pro) from
    ``BADGE_TEMPLATES`` or returns an empty string when no badge should
    be shown (UNVERIFIED or no trust score exists).

    Usage in templates::

        {% load trust_tags %}
        {% render_trust_badge ad.user %}

    Args:
        context: Django template context (for request access).
        user: The seller user to render a badge for.

    Returns:
        Rendered badge HTML, or an empty string when no badge applies.
    """
    if not user or user.is_anonymous:
        return ""

    # Use prefetched trust_score (via prefetch_related("user__trust_score"))
    # to avoid an N+1 query per ad in the listings loop.
    trust_score = getattr(user, "trust_score", None)
    if trust_score is None:
        try:
            trust_score = SellerTrustScore.objects.get(user=user)
        except SellerTrustScore.DoesNotExist:
            logger.debug("No SellerTrustScore for user %s", user.id)
            return ""

    template_path = BADGE_TEMPLATES.get(trust_score.trust_level)
    if template_path is None:
        return ""

    return render_to_string(
        template_path,
        {"trust_level": trust_score.trust_level},
        request=context.get("request"),
    )