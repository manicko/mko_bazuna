"""
Consent context processor for Mko Bazuna (T-04 / D3, D4, D5).

Computes ``consent_shown``, ``consent_analytics`` and ``consent_preferences``
for every template without per-view passing. Consent state is read from the
database for authenticated users and from cookies for anonymous visitors
(D3 — the ``consent_given`` cookie is now read back, not just written).

Also implements:
- D4: anonymous users see the banner until they act (cookie-based consent).
- T-08: 12-month re-prompt as defense-in-depth (server-side timestamp check).
- T-09: a ``?ref=preferences`` override that forces the banner to re-show when
  the user explicitly opens the cookie preference center.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

# Consent state that counts as "the user has acted" (banner hidden) for the
# backward-compatible ``consent_given`` cookie format transition (D-COOKIES):
# old value ``"true"`` and new value ``"accepted"`` both mean full acceptance.
_ACTED_COOKIE_VALUES = ("true", "accepted", "declined", "withdrawn")

# 12-month re-prompt window (PO-05 / T-08).
CONSENT_REPROMPT_DAYS = 365


def _is_expired(consent_timestamp: object) -> bool:
    """Return True when a consent timestamp is older than the re-prompt window."""
    try:
        age = timezone.now().timestamp() - float(consent_timestamp)
    except (TypeError, ValueError):
        return False
    return age >= timedelta(days=CONSENT_REPROMPT_DAYS).total_seconds()


def consent_state(request) -> dict[str, bool]:
    """Provide consent banner state to every template.

    - Authenticated: derived from ``User`` consent fields (DB source of truth).
    - Anonymous: derived from the ``consent_given`` / category cookies.

    Args:
        request: The current HTTP request.

    Returns:
        Dict with ``consent_shown``, ``consent_analytics`` and
        ``consent_preferences`` booleans.
    """
    user = getattr(request, "user", None)
    cookie = request.COOKIES.get("consent_given", "")

    consent_analytics = False
    consent_preferences = False

    if user is not None and user.is_authenticated:
        # Authenticated consent is DB-driven.
        consent_given_at = user.consent_given_at
        consent_shown = (
            consent_given_at is not None
            or user.is_declined
            or user.consent_revoked_at is not None
        )

        if consent_given_at is not None:
            # T-08: re-prompt if consent is older than 12 months.
            if timezone.now() - consent_given_at < timedelta(
                days=CONSENT_REPROMPT_DAYS
            ):
                consent_analytics = True
                consent_preferences = True
            else:
                consent_shown = False
    else:
        # Anonymous consent is cookie-driven.
        consent_shown = cookie in _ACTED_COOKIE_VALUES
        consent_analytics = request.COOKIES.get("consent_analytics") == "true"
        consent_preferences = request.COOKIES.get("consent_preferences") == "true"

        # Backward compatibility: the old ``consent_given=true`` cookie meant
        # full acceptance (both categories granted).
        if cookie == "true":
            consent_analytics = True
            consent_preferences = True

        # T-08: re-prompt when the consent_timestamp cookie is older than 12 months.
        consent_timestamp = request.COOKIES.get("consent_timestamp")
        if consent_timestamp and _is_expired(consent_timestamp):
            consent_shown = False

    # Soft-deleted users: banner is already guarded in templates.
    if user is not None and user.is_authenticated and user.is_deleted:
        consent_shown = True

    # T-09: the user explicitly requested the cookie preference center.
    if request.GET.get("ref") == "preferences":
        consent_shown = False

    return {
        "consent_shown": consent_shown,
        "consent_analytics": consent_analytics,
        "consent_preferences": consent_preferences,
    }
