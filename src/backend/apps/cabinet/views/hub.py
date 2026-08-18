"""
Cabinet hub + settings stub views (CAB-001).

The hub is a lightweight authenticated landing page (CR13) that lists the
cabinet sections. Settings is a stub (CR16) — full settings UI is out of
scope; language preference stays on the profile (D11).
"""

import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)


@login_required
def cabinet_hub(request: HttpRequest) -> HttpResponse:
    """Render the cabinet hub landing page."""
    return render(request, "cabinet/hub.html")


@login_required
def cabinet_settings(request: HttpRequest) -> HttpResponse:
    """Render the settings stub page (no full settings UI)."""
    return render(request, "cabinet/settings.html")
