"""
JSON consent-accept / decline / withdraw endpoints (S3.3).

The write half of gap 20 (plan §2.4 row 20):
``POST /api/v1/consent/accept/`` · ``/decline/`` · ``/withdraw/``.

Each endpoint is the JSON sibling of the matching HTML view
(:mod:`apps.users.views.consent`) and consumes the **same** consent services —
:func:`apps.users.services.give_consent`, :func:`decline_consent`,
:func:`withdraw_consent` and :func:`apps.users.services.record_consent_action` —
so the resulting account state is identical to the HTML flow. No API-only
business predicate exists here.

**Cookie quartet stays HTML.** Unlike the HTML views, these endpoints set **no**
consent cookies: the plan keeps the ``consent_given`` / ``consent_analytics`` /
``consent_preferences`` / ``consent_timestamp`` cookie orchestration on the HTML
surface. The API is the machine contract, so it answers a compact consent-state
JSON document instead (documented in ``docs/01-spec/api-surface.md`` row 20).

**Accept / decline are anonymous-allowed** (HTML parity: their HTML views carry
no login gate and a no-session caller still records an audit row). Withdraw is
account-level and therefore session-only.

**Request body is optional and lenient.** The choice comes from the URL, so the
body only optionally refines the granular categories. An empty or malformed body
falls back to the HTML defaults (``analytics=True`` for accept / ``False`` for
decline, ``preferences=True``, ``ConsentVersion.V1_0``) — exactly as the HTML
view's ``_parse_submission`` swallows a missing/invalid form and proceeds with
defaults. There is therefore no 422 path.

**Rate limit first** (before any service call) on all three: the shared
``api_write`` namespace / ``RateLimitBudget.API_WRITE`` budget, answering a 429
``rate_limited`` problem with ``Retry-After``. The method gate is POST-only
(405 ``method_not_allowed`` problem with ``Allow: POST``); identity, where
required, is checked **before** the method (identical to the frozen decorator
ordering).

**Withdraw parity:** the HTML withdraw flow calls ``withdraw_consent`` and then
``logout(request)`` so the withdrawn identity cannot keep using seller features
(04-AUT-002). This endpoint performs both, in that order.
"""

import json
import logging
from http import HTTPStatus
from typing import Any, Final

from django.contrib.auth import logout
from django.http import HttpRequest, JsonResponse
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

from apps.core.enums import ConsentChoice, ConsentVersion, CookieCategory
from apps.core.utils.api_auth import TYPE_METHOD_NOT_ALLOWED, login_required_api
from apps.core.utils.problem import problem, rate_limited_problem
from apps.search.services.rate_limit import RateLimitBudget, rate_limit_check
from apps.users.services import (
    anonymized_client_ip,
    decline_consent,
    give_consent,
    record_consent_action,
    withdraw_consent,
)

logger = logging.getLogger(__name__)

# Stable ASCII ``type`` tokens (never translated).
TYPE_FORBIDDEN: Final[str] = "forbidden"

# English msgids (cataloged in ``ru``/``bs``/``en`` in the stage i18n batch).
_DETAIL_METHOD_NOT_ALLOWED: Final[str | Promise] = _("Method not allowed.")
_DETAIL_SOFT_DELETED: Final[str | Promise] = _(
    "Consent cannot be changed for a withdrawn account."
)

# The rate-limit namespace for every authenticated ``/api/v1/`` write. All
# writes share one key namespace (plan Q4/§2.3).
_RATE_LIMIT_NAMESPACE: Final[str] = "api_write"

# The only allowed method for these write endpoints.
_ALLOWED_METHODS: Final[tuple[str, ...]] = ("POST",)


def _method_not_allowed() -> JsonResponse:
    """Return the 405 problem document with an ``Allow: POST`` header."""
    response = problem(
        HTTPStatus.METHOD_NOT_ALLOWED,
        TYPE_METHOD_NOT_ALLOWED,
        _DETAIL_METHOD_NOT_ALLOWED,
    )
    response["Allow"] = ", ".join(_ALLOWED_METHODS)
    return response


def _rate_limited_response(request: HttpRequest) -> JsonResponse | None:
    """Charge the shared write budget; return a 429 problem when exhausted."""
    if not rate_limit_check(
        request,
        namespace=_RATE_LIMIT_NAMESPACE,
        budget=RateLimitBudget.API_WRITE,
    ):
        return rate_limited_problem(RateLimitBudget.API_WRITE)
    return None


def _optional_body(request: HttpRequest) -> dict[str, Any]:
    """Parse the optional JSON body, returning ``{}`` for an empty/invalid one.

    Mirrors the HTML ``_parse_submission`` fallback: a missing or malformed body
    is not an error (the choice comes from the URL), so the caller proceeds with
    the default category values.
    """
    if not request.body:
        return {}
    try:
        parsed = json.loads(request.body)
    except (ValueError, TypeError):
        logger.warning("Invalid consent API body rejected; falling back to defaults")
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _categories(parsed: dict[str, Any], *, analytics_default: bool) -> dict[CookieCategory, bool]:
    """Build the category map the consent audit row records.

    Analytics defaults to the HTML value for the action (``True`` for accept,
    ``False`` for decline) and may be overridden by the optional body;
    preferences defaults to ``True`` (both HTML flows default it to ``True``).
    """
    analytics = parsed.get("analytics")
    if not isinstance(analytics, bool):
        analytics = analytics_default
    preferences = parsed.get("preferences")
    if not isinstance(preferences, bool):
        preferences = True
    return {
        CookieCategory.ANALYTICS: analytics,
        CookieCategory.PREFERENCES: preferences,
    }


def _consent_version(parsed: dict[str, Any]) -> str:
    """Return the requested consent version, defaulting to ``V1_0``."""
    valid = {v.value for v in ConsentVersion}
    version = parsed.get("consent_version")
    if isinstance(version, str) and version in valid:
        return version
    return ConsentVersion.V1_0.value


def _consent_state(user: Any, choice: ConsentChoice) -> dict[str, Any]:
    """Build the compact machine-state payload after a consent action.

    Fields are read straight from the mutated ``User`` (``None`` for an
    anonymous caller, which has no account state). Timestamps are ISO-8601
    strings or ``None``.
    """

    def _iso(value: Any) -> str | None:
        return value.isoformat() if value is not None else None

    return {
        "choice": choice.value,
        "authenticated": user is not None,
        "consent_given_at": _iso(getattr(user, "consent_given_at", None)),
        "consent_revoked_at": _iso(getattr(user, "consent_revoked_at", None)),
        "is_declined": bool(getattr(user, "is_declined", False)),
        "ads_auto_publish": bool(getattr(user, "ads_auto_publish", False)),
        "is_deleted": bool(getattr(user, "is_deleted", False)),
    }


def consent_action(request: HttpRequest, choice: ConsentChoice) -> JsonResponse:
    """Shared handler body for accept / decline (anonymous-allowed).

    Runs method gate → rate limit → optional body → service parity. A session
    caller gets the same account mutation as the HTML flow
    (``give_consent`` / ``decline_consent`` plus the audit row); an anonymous
    caller records the same anonymous audit row the HTML flow records and
    mutates nothing else. A soft-deleted (withdrawn) account is refused with a
    403 problem, mirroring the HTML 403 refusal (WITHDRAW is terminal).
    """
    if request.method not in _ALLOWED_METHODS:
        return _method_not_allowed()

    limited = _rate_limited_response(request)
    if limited is not None:
        return limited

    parsed = _optional_body(request)
    analytics_default = choice is ConsentChoice.ACCEPTED
    categories = _categories(parsed, analytics_default=analytics_default)
    version = _consent_version(parsed)

    user = request.user if request.user.is_authenticated else None

    if user is not None and user.is_deleted:
        # HTML refuses accept/decline for a soft-deleted identity (403):
        # WITHDRAW is terminal and consent must not be restored via the API.
        logger.warning(
            "Soft-deleted user %s attempted consent %s via API -- rejected",
            user.id,
            choice.value,
        )
        return problem(HTTPStatus.FORBIDDEN, TYPE_FORBIDDEN, _DETAIL_SOFT_DELETED)

    if user is not None:
        if choice is ConsentChoice.ACCEPTED:
            give_consent(user)
        else:
            decline_consent(user)

    record_consent_action(
        user=user,
        choice=choice,
        categories=categories,
        request=request,
        consent_version=version,
    )

    logger.info(
        "User %s performed consent %s via API", getattr(user, "id", "anonymous"), choice.value
    )
    return JsonResponse(_consent_state(user, choice))


def consent_accept_view(request: HttpRequest) -> JsonResponse:
    """``POST /api/v1/consent/accept/`` — accept consent (anonymous-allowed)."""
    return consent_action(request, ConsentChoice.ACCEPTED)


def consent_decline_view(request: HttpRequest) -> JsonResponse:
    """``POST /api/v1/consent/decline/`` — decline consent (anonymous-allowed)."""
    return consent_action(request, ConsentChoice.DECLINED)


@login_required_api
def consent_withdraw_view(request: HttpRequest) -> JsonResponse:
    """``POST /api/v1/consent/withdraw/`` — withdraw consent (session-only).

    ``login_required_api`` refuses an anonymous caller with a 401 problem first;
    the view then applies the POST gate and the shared write rate limit, calls
    the same :func:`withdraw_consent` service the HTML flow uses (audit row
    inside its transaction), and finally flushes the session with ``logout`` —
    the "withdraw still ``logout()``s" parity from plan row 20.
    """
    if request.method not in _ALLOWED_METHODS:
        return _method_not_allowed()

    limited = _rate_limited_response(request)
    if limited is not None:
        return limited

    user = request.user

    # The audit row commits inside ``withdraw_consent``'s transaction, so the
    # ``session_key`` passed here identifies the session that actually
    # authenticated the withdrawal rather than a post-flush value. Scalars are
    # passed (not the request) to keep the service free of ``django.http`` —
    # identical to the HTML withdraw view.
    withdraw_consent(
        user,
        ip_address=anonymized_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT"),
        session_key=request.session.session_key,
    )

    # 04-AUT-002: flush the session after the DB commit and before responding,
    # exactly as the HTML withdraw flow does, so a withdrawn identity cannot keep
    # using seller features.
    logout(request)

    # Re-read the mutated state: after ``withdraw_consent`` the in-memory user is
    # already updated, but ``_consent_state`` reads current field values.
    state = _consent_state(user, ConsentChoice.WITHDRAWN)
    state["session_flushed"] = True

    logger.info("User %s withdrew consent via API - soft-delete triggered", user.id)
    return JsonResponse(state)


__all__ = [
    "TYPE_FORBIDDEN",
    "consent_accept_view",
    "consent_action",
    "consent_decline_view",
    "consent_withdraw_view",
]
