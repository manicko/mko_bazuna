"""
Template tags for rendering trust badges.

Provides the ``render_trust_badge`` simple tag that renders the correct
badge template (verified / trusted / pro) based on the seller's trust level.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django import template
from django.template.loader import render_to_string

from apps.core.enums import TrustLevel
from apps.trust.models import SellerTrustScore

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

    # Unsaved user instances (e.g. ``User()`` in tests) have no PK, so they
    # cannot have a trust score and cannot be queried via a related filter.
    if user.pk is None:
        return ""

    # Read the related score from the attribute that the ORM actually
    # populates.  For a reverse ``OneToOneField`` (``related_name="trust_score"``)
    # ``prefetch_related("user__trust_score")`` caches the related object in the
    # forward descriptor's cache and exposes it via ``user.trust_score`` — it
    # does NOT populate ``user._prefetched_objects_cache`` (that cache is for
    # reverse *FK* / *M2M* prefetches).  Because ``RelatedObjectDoesNotExist``
    # subclasses ``AttributeError``, a ``getattr(user, "trust_score", None)``
    # swallows the "no related row" signal.  The only correct way to read the
    # descriptor is to catch that specific exception: a prefetched relation is
    # then served from cache with zero queries, and a genuinely absent score
    # (or an unprefetched user) is the only case that reaches the fallback
    # lookup below.
    #
    # ``prefetch_related("user__trust_score")`` is present on the listings,
    # search, favorites and ad-detail querysets, so the fallback is the
    # exception path, not the common one (13-PERF-004 validated 2026-09).
    try:
        trust_score = user.trust_score
    except SellerTrustScore.DoesNotExist:
        trust_score = None

    if trust_score is None:
        # No prefetched/cached relation.  It may be genuinely absent (a seller
        # with no score yet) or the caller may not prefetch — both reach the
        # single related lookup, which is retained for that unprefetched path
        # (the fallback is not a defect there; 13-PERF-004 validated 2026-09).
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
