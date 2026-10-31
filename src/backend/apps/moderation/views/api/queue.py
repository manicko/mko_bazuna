"""
JSON moderation-queue read endpoint — ``GET /api/v1/moderation/queue/``.

The read-only JSON mirror of :func:`apps.moderation.views.queue.moderation_queue`:
it consumes the **same** :class:`~apps.moderation.services.priority.PriorityService`
(``get_queued_ads`` + ``get_priority_counts``) and applies the **same**
``?priority=`` semantics — a :class:`~apps.core.enums.PriorityFilter` member, with
the ``ALL`` sentinel (and any missing / unknown value) mapping to **no** DB filter
— and answers with the standard pagination envelope instead of a rendered table.

The per-ad payload carries the fields the HTML queue row exposes (id, localized
title, owner ``telegram_id``, priority ``base_score`` and ``priority_level``)
plus the shared ad fields every JSON read surface exposes (D4). The queue is a
staff surface: ``staff_required_api_problem`` (the RFC 9457 ``/api/v1/`` variant
in ``apps/core/utils/api_auth.py``) refuses an anonymous request with a 401
problem, a non-staff request with a 403 problem, and a wrong method with a 405
problem — none carries a ``WWW-Authenticate`` challenge (09-API-010). The frozen
legacy ``staff_required_api`` is POST-only and is intentionally not used here.

Rate limiting mirrors the HTML queue view, which has **none** — the plan assigns
no budget namespace to this staff read, so no limiter is added here.
"""

import logging
from typing import Any, Final

from django.core.paginator import Paginator
from django.http import HttpRequest, JsonResponse

from apps.core.enums import PriorityFilter
from apps.core.utils.api_auth import staff_required_api_problem
from apps.moderation.services.priority import PriorityService

logger = logging.getLogger(__name__)

# The queue has no per-ad page size in the HTML view (a moderator table renders
# the whole filtered queryset). The JSON surface paginates for a bounded
# response; the default page size matches the listings/cabinet JSON reads so the
# envelope's ``per_page`` is predictable.
PER_PAGE: Final[int] = 24


@staff_required_api_problem
def queue_view(request: HttpRequest) -> JsonResponse:
    """Return a page of the moderation queue as a JSON envelope.

    Mirrors the HTML queue 1:1:

    - ``?priority=`` accepts the ``PriorityFilter`` members; ``all`` (the default)
      or a missing / unknown value maps to **no** filter, exactly as the HTML
      view's ``PriorityFilter`` parse does.
    - ``get_queued_ads`` returns the same priority-ordered queryset
      (``-base_score, -created_at``) the HTML table iterates.
    - ``get_priority_counts`` returns the same per-level counts the HTML filter
      links render.
    """
    raw_priority = request.GET.get("priority", PriorityFilter.ALL)
    try:
        selected = PriorityFilter(raw_priority)
    except ValueError:
        selected = PriorityFilter.ALL

    service = PriorityService()
    ads = service.get_queued_ads(
        priority_filter=None if selected is PriorityFilter.ALL else selected,
    )

    paginator = Paginator(ads, PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    return JsonResponse(
        {
            "page": page_obj.number,
            "per_page": PER_PAGE,
            "total_count": paginator.count,
            "results_truncated": False,
            "results": [_serialize_queued_ad(ad) for ad in page_obj.object_list],
            "has_next": page_obj.has_next(),
            "selected_priority": selected.value,
            "priority_counts": service.get_priority_counts(),
        }
    )


def _serialize_queued_ad(ad: Any) -> dict[str, Any]:
    """Serialize one queued ad into the stable JSON shape (D4).

    The moderation-specific keys (``base_score`` / ``priority_level``) are the
    ``ad.moderation_priority`` facts the HTML queue row renders; the remaining
    keys match ``apps.ads.views.api.listings._serialize_ad`` so every read
    surface exposes the same ad shape. Media is exposed as URLs only (never
    bytes, plan stance #26).
    """
    priority = getattr(ad, "moderation_priority", None)
    return {
        "id": ad.id,
        "title": ad.get_title(),
        "price": str(ad.price_amount) if ad.price_amount is not None else None,
        "currency": ad.price_currency,
        "city": _named(ad.city),
        "category": _named(ad.category),
        "status": ad.status,
        "created_at": ad.created_at.isoformat() if ad.created_at else None,
        "image_urls": [image.image_url for image in ad.images.all()],
        "telegram_id": ad.user.telegram_id,
        "base_score": priority.base_score if priority is not None else None,
        "priority_level": (
            priority.priority_level if priority is not None else None
        ),
        "absolute_url": ad.get_absolute_url(),
    }


def _named(obj: Any) -> dict[str, Any] | None:
    """Return ``{"slug", "name"}`` for an optional related object, else ``None``."""
    if obj is None:
        return None
    return {"slug": obj.slug, "name": str(obj.name)}
