"""
Ad favorites queryset service — annotate favorite state on ad listings.

Extracted from ``apps.ads.views.favorite`` (10-QLT-005) so that the shared
listings query service can depend on this annotation without inverting the
layering (service -> views). ``annotate_favorites`` is a pure queryset
annotation with no view/HTTP coupling: a correlated ``Exists`` subquery on
``AdFavorite`` that sets an ``is_favorited`` flag per ad.
"""

import logging

from django.db.models import Exists, OuterRef, QuerySet

from apps.ads.models import Ad, AdFavorite

logger = logging.getLogger(__name__)


def annotate_favorites(queryset: QuerySet[Ad], user_id: int | None) -> QuerySet[Ad]:
    """Annotate each Ad with an ``is_favorited`` flag for the current user.

    Uses a correlated ``Exists`` subquery on ``AdFavorite`` so cards render the
    correct initial heart state without per-card queries. Anonymous users
    (``user_id`` None) never match a favorite, so every ad is False.
    """
    favorite_exists = AdFavorite.objects.filter(
        ad_id=OuterRef("pk"),
        user_id=user_id,
    )
    return queryset.annotate(is_favorited=Exists(favorite_exists))
