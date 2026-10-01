"""
Consent views for Mko Bazuna.

Implements decision F/K consent states (zone R3):
- Accept: sets consent_given_at (covers all processing including bot)
- Decline (browse-only): sets ads_auto_publish=False, no deletion

Data flow disclosure — translation egress:
Ad title/description (on creation) are sent to Google Translate via the Google Cloud
Translation API (direct httpx call) for language normalization at publication time.
This is a best-effort, non-identifying content transfer; no user PII (telegram_id,
username, IP) is included in the request. Buyer search queries are NOT sent to any
translation service — search runs per-language on pre-translated FTS vectors
(section G in docs/01-spec/technical-specification.md).
"""

import logging

from django.contrib.auth import login as auth_login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from pydantic import ValidationError

from apps.core.enums import ConsentChoice, ConsentVersion, CookieCategory
from apps.core.middleware.preferred_city import PREFERRED_CITY_COOKIE_NAME
from apps.core.services.contact_rate_limit import check_deep_link_render_rate_limit
from apps.core.services.site_config import get_bot_username
from apps.core.utils.sanitize import mask_telegram_id
from apps.locations.models import City
from apps.users.models import User
from apps.users.schemas import ConsentSubmission
from apps.users.services import (
    can_login,
    decline_consent,
    give_consent,
    record_consent_action,
    withdraw_consent,
)
from apps.users.services.login_rate_limit import login_rate_limit_check
from apps.users.services.login_token import (
    LOGIN_BROWSER_ID_COOKIE,
    LOGIN_BROWSER_ID_COOKIE_SECURE,
    ConsumeOutcome,
    consume_token,
    issue_token,
)

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
    _set_consent_cookie(
        response, CONSENT_ANALYTICS_COOKIE, "true" if analytics else "false"
    )
    _set_consent_cookie(
        response, CONSENT_PREFERENCES_COOKIE, "true" if preferences else "false"
    )
    _set_consent_cookie(
        response,
        CONSENT_TIMESTAMP_COOKIE,
        str(int(timezone.now().timestamp())),
    )
    # T-06c / ePrivacy: when preferences consent is revoked, clear the
    # preferred_city cookie so no personalization data outlives consent.
    if not preferences:
        response.delete_cookie(PREFERRED_CITY_COOKIE_NAME)


def _parse_submission(request: HttpRequest) -> ConsentSubmission | None:
    """Parse and validate the consent form submission via the Pydantic DTO.

    Returns ``None`` when the posted data is absent or invalid (callers fall
    back to a safe default rather than erroring on a malformed consent post).
    """
    try:
        # Strip the CSRF token (always present in the consent banner form) so
        # that extra="forbid" on ConsentSubmission does not reject every POST.
        data = {
            k: v
            for k, v in request.POST.dict().items()
            if k != "csrfmiddlewaretoken"
        }
        return ConsentSubmission.model_validate(data)
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
        submission.analytics if submission and "analytics" in request.POST else True
    )
    preferences = (
        submission.preferences if submission and "preferences" in request.POST else True
    )
    user = request.user if request.user.is_authenticated else None

    if user is not None and user.is_deleted:
        logger.warning("Soft-deleted user %s attempted consent accept -- rejected (WITHDRAW is terminal)", user.id)
        return HttpResponseForbidden()

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
        categories={
            CookieCategory.ANALYTICS: analytics,
            CookieCategory.PREFERENCES: preferences,
        },
        request=request,
        consent_version=submission.consent_version if submission else ConsentVersion.V1_0.value,
    )
    logger.info("User %s accepted consent via web", getattr(user, 'id', 'anonymous'))
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
        submission.preferences if submission and "preferences" in request.POST else True
    )
    user = request.user if request.user.is_authenticated else None

    if user is not None and user.is_deleted:
        logger.warning("Soft-deleted user %s attempted consent decline -- rejected (WITHDRAW is terminal)", user.id)
        return HttpResponseForbidden()

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
        categories={
            CookieCategory.ANALYTICS: analytics,
            CookieCategory.PREFERENCES: preferences,
        },
        request=request,
        consent_version=submission.consent_version if submission else ConsentVersion.V1_0.value,
    )
    logger.info("User %s declined consent via web", getattr(user, 'id', 'anonymous'))
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

    # AUT-002: flush the session on consent withdrawal so a withdrawn
    # (soft-deleted) identity cannot keep using seller features. This must
    # run after withdraw_consent() (DB commit) and before the redirect.
    logout(request)

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
        categories={CookieCategory.ANALYTICS: False, CookieCategory.PREFERENCES: False},
        request=request,
    )
    logger.info("User %s withdrew consent via web - soft-delete triggered", user.id)
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

    Generates a cryptographically random 32-char URL-safe token via
    ``issue_token``, which stores only its SHA-256 hash and owns the token
    lifecycle, then renders the deep-link
    https://t.me/<BOT_USERNAME>?start=login_<raw_token>.

    The raw token is never stored — only the hash is persisted.
    Token expires in 5 minutes.

    Args:
        request: HTTP request (anonymous or authenticated)

    Returns:
        Rendered login page with deep-link to Telegram bot
    """
    if not check_deep_link_render_rate_limit(request):
        logger.warning("Deep-link render rate limit exceeded (login_issue)")
        return HttpResponse(status=429)

    if not login_rate_limit_check(request):
        logger.warning("Rate limit exceeded for login_issue")
        return HttpResponse(status=429)

    issued = issue_token(browser_id=request.COOKIES.get(LOGIN_BROWSER_ID_COOKIE))

    bot_username = get_bot_username()

    logger.info("Issued login token hash=%s...", issued.token_hash[:8])

    response = render(
        request,
        "users/login_issue.html",
        {
            "bot_username": bot_username,
            "raw_token": issued.raw_token,
        },
    )
    # First-party essential cookie binding this token to this browser for the
    # duration of the two-phase handshake. No max_age: session-scoped, so it
    # cannot outlive the ≤300 s token. HttpOnly — essential security state, not
    # consent-gated, and therefore never cleared on decline.
    #
    # Both the name and ``secure`` come from the service's settings-resolved pair
    # (LOGIN_BROWSER_ID_COOKIE / LOGIN_BROWSER_ID_COOKIE_SECURE), never hardcoded
    # here. On a transport-secure origin the pair is ``__Host-login_browser_id`` +
    # ``Secure``; on a plain-HTTP origin it is ``login_browser_id`` + no ``Secure``.
    # Deriving both from one setting is what makes "``__Host-`` without ``Secure``"
    # — which every conformant user agent rejects, breaking login — unrepresentable.
    # ``secure`` is never ``request.is_secure()``: behind a misconfigured
    # SECURE_PROXY_SSL_HEADER that silently drops the prefix in production. The
    # ``__Host-`` contract additionally requires ``Path=/`` and forbids ``Domain``;
    # both are supplied here and pinned by the cookie-contract test.
    response.set_cookie(
        LOGIN_BROWSER_ID_COOKIE,
        issued.browser_id,
        httponly=True,
        samesite="Lax",
        secure=LOGIN_BROWSER_ID_COOKIE_SECURE,
        path="/",
    )
    return response


def _reconcile_preferred_city_on_login(request: HttpRequest, user: User) -> None:
    """Migrate a guest's ``preferred_city`` cookie into the account (AC-6).

    Decided to STAY in the view (ENT-005): it has no relationship to the token
    lifecycle, takes an ``HttpRequest``, and would force
    ``apps.locations.models`` and ``apps.core.middleware.preferred_city`` into
    the ``login_token`` service — both on its forbidden-import list.

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


@require_POST
@never_cache
def login_status(request: HttpRequest) -> HttpResponse:
    """
    Poll login token status — atomically mark consumed if claimed.

    Phase 2 of the two-phase claim: if the bot has already set telegram_id
    (phase 1) and the token is still unconsumed and not expired, this view
    atomically sets consumed_at=now() to complete the claim, then establishes
    a web session (django.contrib.auth.login + session.cycle_key).

    Args:
        request: HTTP request with POST body field ``token``.

    Returns:
        HttpResponse 200 — token consumed, session established (session cookie set)
        HttpResponse 204 — pending (bot has not claimed the token yet)
        HttpResponse 410 — gone (token invalid, expired, already consumed, user
            banned, account disabled, or the presented browser binding does not
            match the issuing one — ``UNBOUND``, which shares this status
            deliberately so the response is not an oracle for *which* cause)
    """
    raw_token = request.POST.get("token", "")
    if not raw_token:
        return HttpResponse(status=410)

    # The caller owns the transaction; the service owns the predicate.
    # consume_token opens no transaction of its own — the current outer
    # atomic() covers exactly the read and the guarded UPDATE, nothing after.
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        result = consume_token(
            raw_token,
            browser_id=request.COOKIES.get(LOGIN_BROWSER_ID_COOKIE),
        )

        if result.outcome is ConsumeOutcome.NOT_FOUND:
            return HttpResponse(status=410)
        if result.outcome is ConsumeOutcome.GONE:
            return HttpResponse(status=410)
        if result.outcome is ConsumeOutcome.PENDING:
            return HttpResponse(status=204)
        if result.outcome is ConsumeOutcome.UNBOUND:
            # The issuing browser's binding does not match. The token is NOT
            # burned (service side), so the legitimate holder can still redeem.
            # No telegram_id and no binding value in this line — only the
            # established token-hash correlation prefix.
            logger.warning(
                "Login token %s... refused: browser binding mismatch",
                result.token_hash[:8],
            )
            return HttpResponse(status=410)
        if result.outcome is ConsumeOutcome.LOST_RACE:
            return HttpResponse(status=410)
        # CONSUMED — the token is marked used; capture the identity for the
        # session-establishment steps that follow the transaction.
        token_hash = result.token_hash
        telegram_id = result.telegram_id

    logger.info(
        "Login token %s consumed by telegram_id=%s",
        token_hash[:8],
        mask_telegram_id(telegram_id),
    )

    # Look up the user by telegram_id
    try:
        user = User.objects.get(telegram_id=telegram_id)
    except User.DoesNotExist:
        logger.error(
            "User not found for telegram_id=%s",
            mask_telegram_id(telegram_id),
        )
        return HttpResponse(status=410)

    # Check if user is banned
    if not can_login(user):
        logger.warning(
            "Login denied for telegram_id=%s: banned",
            mask_telegram_id(telegram_id),
        )
        return HttpResponse(status=410)

    # Refuse a disabled account before the view's first session write.
    # auth_login() performs no is_active check, so without this guard the view
    # would hand out a session cookie whose identity Django discards on the next
    # request (ModelBackend.get_user returns None for an inactive user). This is
    # deliberately a view-local guard, not a term in can_login.
    if not user.is_active:
        logger.warning(
            "Login denied for telegram_id=%s: account disabled",
            mask_telegram_id(telegram_id),
        )
        return HttpResponse(status=410)

    # Establish web session
    # auth_login() already calls cycle_key() for anonymous->authenticated transitions,
    # so an explicit cycle_key() here would be redundant.
    auth_login(request, user)

    # Migrate a guest's preferred-city cookie into the account (guest->registered).
    _reconcile_preferred_city_on_login(request, user)

    logger.info(
        "Web session established for user %s (telegram_id=%s)",
        user.id,
        mask_telegram_id(telegram_id),
    )

    return HttpResponse(status=200)
