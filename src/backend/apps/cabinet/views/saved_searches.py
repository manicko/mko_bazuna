"""
Cabinet Saved-Search management views (CAB-003).

Per-search list with enable/disable, edit, and delete. Disable only flips
``is_active`` (the search stays saved — D9); delete removes the row, so it
no longer fires alerts.
"""

import logging

from apps.search.models import SavedSearch
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

logger = logging.getLogger(__name__)


def _user_search(request: HttpRequest, pk: int) -> SavedSearch:
    """Return a saved search scoped to the request user or 404."""
    return get_object_or_404(SavedSearch, pk=pk, user=request.user)


@login_required
def saved_searches_list(request: HttpRequest) -> HttpResponse:
    """List the user's saved searches ordered by creation (newest first)."""
    searches = (
        SavedSearch.objects.filter(user=request.user)
        .select_related("city", "category")
        .order_by("-created_at")
    )
    return render(
        request,
        "cabinet/saved_searches.html",
        {"saved_searches": searches},
    )


@login_required
def saved_search_toggle(request: HttpRequest, pk: int) -> HttpResponse:
    """Flip ``is_active`` (disable ≠ delete — D9), then return the row."""
    if request.method != "POST":
        return HttpResponse(status=405)
    saved_search = _user_search(request, pk)
    saved_search.is_active = not saved_search.is_active
    saved_search.save(update_fields=["is_active", "updated_at"])
    logger.info(
        "Saved search %s for user %s set active=%s",
        saved_search.pk,
        request.user.pk,
        saved_search.is_active,
    )
    return _render_row(request, saved_search)


@login_required
def saved_search_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit a saved search's filters (GET form / POST update)."""
    saved_search = _user_search(request, pk)

    if request.method == "POST":
        _apply_filters(request, saved_search)
        saved_search.language = request.LANGUAGE_CODE or saved_search.language
        saved_search.save(update_fields=[
            "query", "city", "category", "min_price", "max_price",
            "language", "updated_at",
        ])
        return HttpResponseRedirect(reverse("cabinet:saved-searches"))

    return render(
        request,
        "cabinet/saved_search_edit.html",
        {"saved_search": saved_search, "cities": _cities(), "categories": _categories()},
    )


@login_required
def saved_search_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete the saved search row (removal, distinct from disable — D9)."""
    if request.method != "POST":
        return HttpResponse(status=405)
    saved_search = _user_search(request, pk)
    logger.info(
        "Deleting saved search %s for user %s",
        saved_search.pk,
        request.user.pk,
    )
    saved_search.delete()
    # HTMX: return an empty body so the row is swapped out of the list.
    if request.headers.get("HX-Request"):
        return HttpResponse("")
    return HttpResponseRedirect(reverse("cabinet:saved-searches"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _apply_filters(request: HttpRequest, saved_search: SavedSearch) -> None:
    """Copy the posted query + optional filters onto the saved search."""
    from apps.categories.models import Category
    from apps.locations.models import City

    query = (request.POST.get("query") or "").strip()

    def _int_or_none(name: str) -> int | None:
        raw = (request.POST.get(name) or "").strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    saved_search.query = query or None

    city_id = _int_or_none("city_id")
    saved_search.city = City.objects.filter(pk=city_id).first() if city_id else None

    category_id = _int_or_none("category_id")
    saved_search.category = (
        Category.objects.filter(pk=category_id).first() if category_id else None
    )

    saved_search.min_price = _int_or_none("min_price")
    saved_search.max_price = _int_or_none("max_price")


def _cities():
    from apps.locations.models import City

    return City.objects.order_by("name")


def _categories():
    from apps.categories.models import Category

    return Category.objects.filter(is_active=True).order_by("name")


def _render_row(request: HttpRequest, saved_search: SavedSearch) -> HttpResponse:
    """Render a single saved-search row fragment (HTMX toggle target)."""
    return render(
        request,
        "cabinet/partials/saved_search_row.html",
        {"ss": saved_search},
    )
