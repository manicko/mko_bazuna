"""
Consent views for Mko Bazuna.

Implements decision F/K consent states (zone R3):
- Accept: sets consent_given_at (covers all processing including bot)
- Decline (browse-only): sets ads_auto_publish=False, no deletion

Data flow disclosure — translation egress:
Ad title/description (on creation) and search queries (on lookup) are
sent to Google Translate via the `deep-translator` wrapper for language
normalization. This is a best-effort, non-identifying content transfer;
no user PII (telegram_id, username, IP) is included in the request.
See also section G in docs/01-spec/technical-specification.md.
"""

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from pydantic import ValidationError

from apps.core.enums import ConsentChoice
from apps.core.middleware.preferred_city import PREFERRED_CITY_COOKIE_NAME
from apps.core.utils.sanitize import mask_telegram_id
from apps.locations.models import City
from apps.users.models import LoginToken, User
from apps.users.schemas import ConsentSubmission
from apps.users.services import (
    can_login,
    decline_consent,
    give_consent,
    record_consent_action,
    withdraw_consent,
)
from apps.users.services.login_rate_limit import login_rate_limit_check

logger = logging.getLogger(__name__)

CONSENT_COOKIE_NAME = "consent_given"
CONSENT_ANALYTICS_COOKIE = "consent_analytics"
CONSENT_PREFERENCES_COOKIE = "consent_preferences"
CONSENT_TIMESTAMP_COOKIE = "consent_timestamp"
# 12 months (PO-05 / T-05). Browser-side expiry is the primary re-prompt
# mechanism; the context processor adds a server-side timestamp check (T-08).
CONSENT_COOKIE_MAX_AGE = 365 * 24 * 60 * 60


def _set_consent_cookie(
    response: HttpResponse,
    name: str,
    value: str,
) -> None:
    """Set a consent cookie with the standard secure attributes."""
    response.set_cookie(
        name,
        value,
        max_age=CONSENT_COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=True,
    )


def _set_consent_cookies(
    response: HttpResponse,
    choice: ConsentChoice,
    analytics: bool,
    preferences: bool,
) -> None:
    """Persist consent state + granular categories + timestamp cookies.

    All consent cookies use ``max_age=12 months``, ``httponly=True``,
    ``samesite="Lax"`` and ``secure=True`` (D-COOKIES).
    """
    _set_consent_cookie(response, CONSENT_COOKIE_NAME, choice.value)
    _set_consent_cookie(response, CONSENT_ANALYTICS_COOKIE, "true" if analytics else "false")
    _set_consent_cookie(response, CONSENT_PREFERENCES_COOKIE, "true" if preferences else "false")
    _set_consent_cookie(
        response,
        CONSENT_TIMESTAMP_COOKIE,
        str(int(timezone.now().timestamp())),
    )


def _parse_submission(request: HttpRequest) -> ConsentSubmission | None:
    """Parse and validate the consent form submission via the Pydantic DTO.

    Returns ``None`` when the posted data is absent or invalid (callers fall
    back to a safe default rather than erroring on a malformed consent post).
    """
    try:
        return ConsentSubmission.model_validate(request.POST.dict())
    except ValidationError:
        logger.warning("Invalid consent submission rejected")
        return None


@require_POST
def consent_accept(request: HttpRequest) -> HttpResponse:
    """
    Accept consent (decision F / T-05).

    Authenticated: calls ``give_consent`` (which also clears any prior decline
    state, D6) and redirects to the dashboard. Anonymous: sets the consent
    cookies only (no DB mutation) and redirects to the home page.

    Always sets the granular-category and timestamp cookies with secure flags.

    Args:
        request: HTTP request (authenticated or anonymous).

    Returns:
        Redirect to the dashboard (authenticated) or home page (anonymous).
    """
    submission = _parse_submission(request)
    analytics = (
        submission.analytics
        if submission and "analytics" in request.POST
        else True
    )
    preferences = (
        submission.preferences
        if submission and "preferences" in request.POST
        else True
    )
    user = request.user if request.user.is_authenticated else None

    if user is not None:
        give_consent(user)
        target: str = "ads:dashboard"
    else:
        target = "/"

    response = redirect(target)
    _set_consent_cookies(
        response,
        ConsentChoice.ACCEPTED,
        analytics,
        preferences,
    )
    record_consent_action(
        user=user,
        choice=ConsentChoice.ACCEPTED,
        categories={"analytics": analytics, "preferences": preferences},
        request=request,
        consent_version=submission.consent_version if submission else "1.0",
    )
    logger.info(f"User {getattr(user, 'id', 'anonymous')} accepted consent via web")
    return response


@require_POST
def consent_decline(request: HttpRequest) -> HttpResponse:
    """
    Decline consent (browse-only, decision K / T-05).

    Rejects non-essential analytics cookies (PO-02). Authenticated users are
    set to browse-only via ``decline_consent``. Anonymous users get the cookies
    only. No account deletion occurs.

    Args:
        request: HTTP request (authenticated or anonymous).

    Returns:
        Redirect to the dashboard (authenticated) or home page (anonymous).
    """
    submission = _parse_submission(request)
    analytics = False  # decline always rejects analytics
    preferences = (
        submission.preferences
        if submission and "preferences" in request.POST
        else True
    )
    user = request.user if request.user.is_authenticated else None

    if user is not None:
        decline_consent(user)
        target = "ads:dashboard"
    else:
        target = "/"

    response = redirect(target)
    _set_consent_cookies(
        response,
        ConsentChoice.DECLINED,
        analytics,
        preferences,
    )
    record_consent_action(
        user=user,
        choice=ConsentChoice.DECLINED,
        categories={"analytics": analytics, "preferences": preferences},
        request=request,
        consent_version=submission.consent_version if submission else "1.0",
    )
    logger.info(f"User {getattr(user, 'id', 'anonymous')} declined consent via web")
    return response


@login_required
@require_POST
def consent_withdraw(request: HttpRequest) -> HttpResponse:
    """
    Withdraw consent and trigger immediate soft-delete (decision F).

    Calls ``withdraw_consent`` which sets ``consent_revoked_at``, soft-deletes
    the user and their ads, and nullifies PII (telegram_id, username). Sets the
    consent cookies (withdrawn + all categories false) with secure flags.

    Withdrawal is an account-level action and therefore keeps ``@login_required``.

    Args:
        request: HTTP request (authenticated user required).

    Returns:
        Redirect to the dashboard.
    """
    user = request.user
    withdraw_consent(user)

    response = redirect("ads:dashboard")
    _set_consent_cookies(
        response,
        ConsentChoice.WITHDRAWN,
        analytics=False,
        preferences=False,
    )
    record_consent_action(
        user=user,
        choice=ConsentChoice.WITHDRAWN,
        categories={"analytics": False, "preferences": False},
        request=request,
    )
    logger.info(f"User {user.id} withdrew consent via web - soft-delete triggered")
    return response


def is_consent_given(request: HttpRequest) -> bool:
    """
    [Deprecated] Check if the user has acted on consent (banner hidden).

    This function is kept as a backward-compatible shim. Its logic now lives in
    ``apps.users.context_processors.consent_state``, which computes
    ``consent_shown`` for every template. Prefer the context processor.

    Args:
        request: HTTP request.

    Returns:
        ``True`` if the user has acted (banner hidden), ``False`` otherwise.
    """
    from apps.users.context_processors import consent_state

    return consent_state(request)["consent_shown"]


@never_cache
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
    if not login_rate_limit_check(request):
        logger.warning("Rate limit exceeded for login_issue")
        return HttpResponse(status=429)

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
            "raw_token": raw_token,
        },
    )


def _reconcile_preferred_city_on_login(request: HttpRequest, user: User) -> None:
    """Migrate a guest's ``preferred_city`` cookie into the account (AC-6).

    Runs immediately after ``auth_login``. If the just-authenticated user has no
    ``User.preferred_city`` and the ``preferred_city`` cookie references a
    currently-valid city, the preference is backfilled onto the account. If the
    user already has a preference, the DB value wins (it is never overwritten by
    the cookie). The cookie is always retained as the anonymous-session fallback.

    Args:
        request: The request carrying the ``preferred_city`` cookie.
        user: The just-authenticated user.
    """
    if user.preferred_city_id is not None:
        # DB preference already set — it wins; do not overwrite from the cookie.
        return

    cookie_slug = request.COOKIES.get(PREFERRED_CITY_COOKIE_NAME)
    if not cookie_slug or not City.objects.filter(slug=cookie_slug).exists():
        return

    try:
        user.preferred_city = City.objects.get(slug=cookie_slug)
        user.save(update_fields=["preferred_city"])
    except City.DoesNotExist:
        # The cookie referenced a city removed during this request; skip.
        logger.info("Skipping preferred-city backfill for unknown slug %r", cookie_slug)
        return

    logger.info(
        "Backfilled User %s preferred_city from cookie=%r", user.id, cookie_slug
    )


@never_cache
def login_status(request: HttpRequest) -> HttpResponse:
    """
    Poll login token status — atomically mark consumed if claimed.

    Phase 2 of the two-phase claim: if the bot has already set telegram_id
    (phase 1) and the token is still unconsumed and not expired, this view
    atomically sets consumed_at=now() to complete the claim, then establishes
    a web session (django.contrib.auth.login + session.cycle_key).

    Args:
        request: HTTP request with query param ?token=<raw_token>

    Returns:
        HttpResponse 200 — token consumed, session established (session cookie set)
        HttpResponse 204 — pending (bot has not claimed the token yet)
        HttpResponse 410 — gone (token invalid, expired, already consumed, or user banned)
    """
    raw_token = request.GET.get("token", "")
    if not raw_token:
        return HttpResponse(status=410)

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
        try:
            token = LoginToken.objects.get(token_hash=token_hash)
        except LoginToken.DoesNotExist:
            return HttpResponse(status=410)

        # Constant-time comparison (spec: spec-index.md:75, db-schema.md:86)
        if not hmac.compare_digest(token.token_hash, token_hash):
            return HttpResponse(status=410)

        # Token expired or already consumed — gone
        if token.expires_at <= timezone.now() or token.consumed_at is not None:
            return HttpResponse(status=410)

        # Bot has not claimed the token yet — keep polling
        if token.telegram_id is None:
            return HttpResponse(status=204)

        # Bot has claimed the token — atomically mark consumed (single UPDATE)
        # Optimistic concurrency: filter conditions ensure only an unclaimed,
        # unexpired token with matching telegram_id is touched.
        updated = LoginToken.objects.filter(
            token_hash=token_hash,
            telegram_id=token.telegram_id,
            consumed_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).update(consumed_at=timezone.now())

        if updated == 0:
            # Race condition — another request already consumed it
            return HttpResponse(status=410)

    logger.info(
        f"Login token {token_hash[:8]} consumed by telegram_id={mask_telegram_id(token.telegram_id)}"
    )

    # Look up the user by telegram_id
    try:
        user = User.objects.get(telegram_id=token.telegram_id)
    except User.DoesNotExist:
        logger.error(
            f"User not found for telegram_id={mask_telegram_id(token.telegram_id)}"
        )
        return HttpResponse(status=410)

    # Check if user is banned
    if not can_login(user):
        logger.warning(
            f"Login denied for telegram_id={mask_telegram_id(token.telegram_id)}: banned"
        )
        return HttpResponse(status=410)

    # Establish web session
    # auth_login() already calls cycle_key() for anonymous->authenticated transitions,
    # so an explicit cycle_key() here would be redundant.
    auth_login(request, user)

    # Migrate a guest's preferred-city cookie into the account (guest->registered).
    _reconcile_preferred_city_on_login(request, user)

    logger.info(
        f"Web session established for user {user.id} (telegram_id={mask_telegram_id(token.telegram_id)})"
    )

    return HttpResponse(status=200)
