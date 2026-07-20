"""
Consent views for Mko Bazuna.

Implements decision F/K consent states (zone R3):
- Accept: sets consent_given_at (covers all processing including bot)
- Decline (browse-only): sets ads_auto_publish=False, no deletion
"""

import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

from apps.users.services import decline_consent, give_consent

logger = logging.getLogger(__name__)


CONSENT_COOKIE_NAME = "consent_given"
CONSENT_COOKIE_MAX_AGE = 365 * 24 * 60 * 60  # 1 year


@login_required
def consent_accept(request: HttpRequest) -> HttpResponse:
    """
    Accept consent (decision F).

    Sets consent_given_at to now() for the user.
    Sets a cookie to persist the decision client-side.

    Args:
        request: HTTP request (authenticated user required)

    Returns:
        Redirect to dashboard or home page
    """
    user = request.user
    give_consent(user)

    response = redirect("ads:dashboard")
    response.set_cookie(
        CONSENT_COOKIE_NAME,
        "true",
        max_age=CONSENT_COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
    )
    logger.info(f"User {user.id} accepted consent via web")
    return response


@login_required
def consent_decline(request: HttpRequest) -> HttpResponse:
    """
    Decline consent (browse-only, decision K).

    Sets ads_auto_publish=False. Does NOT set consent_revoked_at.
    Does NOT trigger any deletion. Contact button continues to work.
    Sets a cookie to persist the decision client-side.

    Args:
        request: HTTP request (authenticated user required)

    Returns:
        Redirect to dashboard or home page
    """
    user = request.user
    decline_consent(user)

    response = redirect("ads:dashboard")
    response.set_cookie(
        CONSENT_COOKIE_NAME,
        "declined",
        max_age=CONSENT_COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
    )
    logger.info(f"User {user.id} declined consent via web - browse-only mode")
    return response


def is_consent_given(request: HttpRequest) -> bool:
    """
    Check if consent banner should be shown (has user acted?).

    For anonymous users: returns True (banner not shown - they can browse without consent).
    For authenticated users: returns True if user has acted (accepted or declined).

    Args:
        request: HTTP request

    Returns:
        True if user has acted on consent (banner hidden), False if banner should show.
    """
    if not request.user.is_authenticated:
        # Anonymous users can browse without consent - no banner needed
        return True

    user = request.user
    # User has acted if they accepted (consent_given_at set) or declined (ads_auto_publish=False)
    return user.consent_given_at is not None or not user.ads_auto_publish