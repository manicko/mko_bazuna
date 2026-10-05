"""
Cabinet Saved-Search management views (CAB-003).

Per-search list with enable/disable, edit, and delete. Disable only flips
``is_active`` (the search stays saved — D9); delete removes the row, so it
no longer fires alerts.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext as _
from pydantic import ValidationError

from apps.search.models import SavedSearch
from apps.search.schemas import SavedSearchInput

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
        filters = _parse_filters(request)
        if filters is None:
            # Error shape (ii): re-render the edit form with an error and the
            # submitted values preserved, and store nothing.
            logger.warning(
                "Refused invalid saved-search filters for search %s (10-CQ-004)",
                saved_search.pk,
            )
            return _render_edit_form(
                request,
                saved_search,
                error=_("Price must not be negative."),
            )
        _apply_filters(saved_search, filters, request.POST.get("query") or "")
        saved_search.language = request.LANGUAGE_CODE or saved_search.language
        saved_search.save(
            update_fields=[
                "query",
                "city",
                "category",
                "min_price",
                "max_price",
                "language",
                "updated_at",
            ]
        )
        return HttpResponseRedirect(reverse("cabinet:saved-searches"))

    return _render_edit_form(request, saved_search, error=None)


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


def _parse_filters(request: HttpRequest) -> SavedSearchInput | None:
    """Validate the posted filters through the shared boundary (10-CQ-004).

    Returns ``None`` when the DTO rejects the input (e.g. a negative price), so
    the caller re-renders the form instead of persisting.
    """
    try:
        return SavedSearchInput(
            city_id=request.POST.get("city_id"),
            category_id=request.POST.get("category_id"),
            min_price=request.POST.get("min_price"),
            max_price=request.POST.get("max_price"),
        )
    except ValidationError:
        return None


def _apply_filters(
    saved_search: SavedSearch, filters: SavedSearchInput, query: str
) -> None:
    """Copy the posted query + validated filters onto the saved search."""
    from apps.categories.models import Category
    from apps.locations.models import City

    saved_search.query = query.strip() or None

    saved_search.city = (
        City.objects.filter(pk=filters.city_id).first() if filters.city_id else None
    )
    saved_search.category = (
        Category.objects.filter(pk=filters.category_id).first()
        if filters.category_id
        else None
    )

    saved_search.min_price = filters.min_price
    saved_search.max_price = filters.max_price


def _render_edit_form(
    request: HttpRequest,
    saved_search: SavedSearch,
    error: str | None,
) -> HttpResponse:
    """Render the edit form, preferring posted values over the stored ones.

    On a POST the form shows what the user submitted (so a rejected value is
    not lost); on a GET it shows the saved search's current values.
    """
    if request.method == "POST":
        form_query = request.POST.get("query") or ""
        form_city_id = request.POST.get("city_id") or ""
        form_category_id = request.POST.get("category_id") or ""
        form_min_price = request.POST.get("min_price") or ""
        form_max_price = request.POST.get("max_price") or ""
    else:
        form_query = saved_search.query or ""
        form_city_id = saved_search.city_id or ""
        form_category_id = saved_search.category_id or ""
        form_min_price = (
            saved_search.min_price if saved_search.min_price is not None else ""
        )
        form_max_price = (
            saved_search.max_price if saved_search.max_price is not None else ""
        )

    return render(
        request,
        "cabinet/saved_search_edit.html",
        {
            "saved_search": saved_search,
            "cities": _cities(),
            "categories": _categories(),
            "form_query": form_query,
            "form_city_id": form_city_id,
            "form_category_id": form_category_id,
            "form_min_price": form_min_price,
            "form_max_price": form_max_price,
            "error": error,
        },
    )


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
