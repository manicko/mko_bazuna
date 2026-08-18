"""
Cabinet Search-History views (CAB-004).

Lists the authenticated user's recent DB-backed queries and provides a
clear action. Anonymous (session) history is not shown here and is never
merged into the account (D6/A6).
"""

import logging

from apps.search.models import SearchHistory
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse

logger = logging.getLogger(__name__)

# Cap the history list to a readable page.
_HISTORY_LIMIT = 100


@login_required
def search_history_list(request: HttpRequest) -> HttpResponse:
    """List the authenticated user's recent search queries."""
    entries = (
        SearchHistory.objects.filter(user=request.user)
        .order_by("-created_at")
        .values("query", "created_at")[:_HISTORY_LIMIT]
    )
    return render(
        request,
        "cabinet/search_history.html",
        {"history_entries": entries},
    )


@login_required
def search_history_clear(request: HttpRequest) -> HttpResponse:
    """Clear the authenticated user's search history."""
    if request.method != "POST":
        return HttpResponse(status=405)
    deleted, _ = SearchHistory.objects.filter(user=request.user).delete()
    logger.info("Cleared %d history entries for user %s", deleted, request.user.pk)
    return HttpResponseRedirect(reverse("cabinet:search-history"))
