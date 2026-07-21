"""
Consent views for Mko Bazuna.

Implements decision F/K consent states (zone R3):
- Accept: sets consent_given_at (covers all processing including bot)
- Decline (browse-only): sets ads_auto_publish=False, no deletion
"""

import logging

from apps.users.services import decline_consent, give_consent
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
import hashlib
import secrets
from datetime import timedelta
from apps.users.models import LoginToken
from django.conf import settings
from django.shortcuts import render
from django.utils import timezone

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


def login_issue(request: HttpRequest) -> HttpResponse:
    """
    Issue a login token and render the Telegram deep-link.

    Generates a cryptographically random 32-char URL-safe token,
    stores only its SHA-256 hash, and renders the deep-link
    https://t.me/<BOT_USERNAME>?start=login_<raw_token>.

    The raw token is never stored — only the hash is persisted.
    Token expires in 5 minutes.

    Args:
        request: HTTP request (anonymous or authenticated)

    Returns:
        Rendered login page with deep-link to Telegram bot
    """
    raw_token = secrets.token_urlsafe(24)  # 32 URL-safe chars, matches bot regex `{32}`
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    LoginToken.objects.create(
        token_hash=token_hash,
        expires_at=timezone.now() + timedelta(minutes=5),
    )

    bot_username = settings.BOT_USERNAME
    deep_link = f"https://t.me/{bot_username}?start=login_{raw_token}"

    logger.info(f"Issued login token hash={token_hash[:8]}...")

    return render(
        request,
        "users/login_issue.html",
        {
            "deep_link": deep_link,
            "bot_username": bot_username,
        },
    )
