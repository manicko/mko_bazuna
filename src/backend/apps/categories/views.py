"""
Category views for Mko Bazuna.

Currently provides the HTMX ``category_submenu`` partial used by the header's
"All Categories" dropdown to lazy-load a category's children.
"""

import logging

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render

from apps.categories.cache import (
    SUBMENU_CACHE_LOCK_TTL,
    SUBMENU_CACHE_STALE_TTL,
    SUBMENU_CACHE_TTL,
    get_tree_version,
)
from apps.categories.models import Category
from apps.core.utils.swr_cache import get_with_stale_revalidate

logger = logging.getLogger(__name__)


def category_submenu(request: HttpRequest, slug: str) -> HttpResponse:
    """Return the HTMX partial submenu for a category's children.

    Renders the category's active children as an expandable nested list for the
    header's "All Categories" dropdown.     The fragment is cached keyed by
    ``category:submenu:<tree_version>:<slug>:<locale>`` so structural tree changes bump
    the cached version and invalidate stale fragments, and the locale segment
    prevents cross-language cache bleed.

    Returns 404 for an unknown or inactive category.

    Args:
        request: The incoming HTTP request.
        slug: The category slug whose children should be rendered.

    Returns:
        The rendered ``categories/partials/mega_submenu.html`` partial.
    """
    category = (
        Category.objects.filter(slug=slug, is_active=True)
        .select_related("parent")
        .first()
    )
    if category is None:
        raise Http404("Category not found")

    cache_key = f"category:submenu:{get_tree_version()}:{category.slug}:{request.LANGUAGE_CODE or 'ru'}"

    def _render_submenu_fragment() -> str:
        children = list(
            category.get_children().filter(is_active=True).order_by("name")
        )
        return render(
            request,
            "categories/partials/mega_submenu.html",
            {"category": category, "children": children},
        ).content.decode("utf-8")

    html = get_with_stale_revalidate(
        cache_key,
        _render_submenu_fragment,
        ttl=SUBMENU_CACHE_TTL,
        stale_ttl=SUBMENU_CACHE_STALE_TTL,
        lock_ttl=SUBMENU_CACHE_LOCK_TTL,
        default="",
    )
    return HttpResponse(html)
