"""
Template tags for rendering trust badges.

Provides the ``trust_badge`` inclusion tag that displays a seller's
trust level badge based on their SellerTrustScore.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apps.core.enums import TrustLevel
from apps.trust.models import SellerTrustScore
from django import template

if TYPE_CHECKING:
    from apps.users.models import User

logger = logging.getLogger(__name__)

register = template.Library()


@register.inclusion_tag("components/badges/verified_badge.html", takes_context=False)
def trust_badge(user: User) -> dict:
    """Render a trust badge for the given user based on their trust level.

    Looks up the user's ``SellerTrustScore`` and maps the ``trust_level``
    to the correct badge template:

    * ``UNVERIFIED`` — no badge rendered (returns an empty context).
    * ``VERIFIED``   — context populated for the verified badge template.
    * ``TRUSTED``    — context populated for the trusted badge template.
    * ``PRO``        — context populated for the pro badge template.

    When the trust score does not exist the tag safely returns an empty
    context so nothing is rendered.

    Args:
        user: The seller user to render a badge for.

    Returns:
        A template context dict, or an empty dict when no badge should
        be shown.
    """
    try:
        trust_score = SellerTrustScore.objects.get(user=user)
    except SellerTrustScore.DoesNotExist:
        logger.debug("No SellerTrustScore for user %s", user.id)
        return {}

    if trust_score.trust_level == TrustLevel.UNVERIFIED:
        return {}

    return {
        "trust_level": trust_score.trust_level,
    }
