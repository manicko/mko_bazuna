"""POST-only logout view for Mko Bazuna (web sellers)."""

import logging

from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)


@require_POST
@never_cache
def logout_view(request: HttpRequest) -> HttpResponse:
    """Log out the current user and redirect to the configured logout target.

    POST + CSRF enforced (Django 5.0 removed GET-based logout to prevent
    logout CSRF). ``django.contrib.auth.logout`` flushes the session.
    """
    logout(request)
    logger.info("User logged out via web")
    return redirect(settings.LOGOUT_REDIRECT_URL)
