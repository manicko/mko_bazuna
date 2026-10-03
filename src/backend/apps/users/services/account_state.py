"""
Account state service for Mko Bazuna.

Distinguishes ban vs delete vs publish-restriction, plus the operator
``is_active`` kill-switch and the consent-withdrawal flags. Six independent
flags. Used by both web dashboard and bot for account state checking.

This module is also the single home of the queryset-level account-state
predicate, :func:`account_state_q` (finding ``06-PII-104``). It is a *pure
function returning a* ``Q`` value: it is never installed on a manager, so it
cannot silently filter ``User.objects``. That matters because
``AccountStateMiddleware._resolve_user`` does ``User.objects.get(chat_id=...)``
and treats a miss as an unregistered, fail-open identity — a default-manager
filter would invert the deny gates this predicate exists to enforce.

Import-cycle hazard (future): this module's transitive import closure already
reaches ``apps.search.services.cache`` through
``apps/users/services/__init__.py`` -> ``deletion`` ->
``bump_search_cache_version``. The alert path (``apps.search``) consuming this
declaration therefore depends on ``apps/search/services/__init__.py`` staying
import-free; a submodule import added there would close the loop and break the
whole alert path. A fresh-interpreter probe in the tests is the tripwire.
"""

import logging
from typing import NamedTuple

from django.db.models import Q

from apps.users.models import User

logger = logging.getLogger(__name__)


class AccountState(NamedTuple):
    """Account state flags for access control.

    ``is_active`` is listed first (plan 19, ``B-1``): ``account_state_q()``
    declares it last, but the Python rule reads naturally with the
    access-control flags first. ``account_state_q()`` carries five of these six
    flags and omits the orthogonal ``ads_auto_publish`` publishing restriction
    (see that function's docstring).
    """

    is_active: bool
    is_banned: bool
    is_deleted: bool
    is_declined: bool
    ads_auto_publish: bool
    consent_revoked: bool


def get_account_state(user: User) -> AccountState:
    """
    Get account state flags for a user.

    Returns a tuple of the six account state flags:
    - is_active: Operator kill-switch (plan 18), blocks bot interaction
    - is_banned: Admin action, blocks login/publish, PII retained
    - is_deleted: GDPR consent withdrawal, telegram_id nulled
    - is_declined: User declined consent (browse-only mode)
    - ads_auto_publish: Publishing restriction, not linked to ban/delete
    - consent_revoked: Consent withdrawn (data erasing)

    Args:
        user: User instance to check.

    Returns:
        AccountState named tuple with all flags.
    """
    return AccountState(
        is_active=user.is_active,
        is_banned=user.is_banned,
        is_deleted=user.is_deleted,
        is_declined=user.is_declined,
        ads_auto_publish=user.ads_auto_publish,
        consent_revoked=user.consent_revoked_at is not None,
    )


def account_state_q(prefix: str = "") -> Q:
    """The single account-state consent rule, as a filterable ``Q``.

    ``prefix`` is the ORM lookup prefix from the calling queryset to ``User``:
    ``""`` on a ``User`` queryset, ``"user__"`` on a model that reaches the
    owner through its ``user`` FK (e.g. ``SavedSearch``, ``Ad``).

    Returns a new ``Q`` value on every call. ``Q`` is immutable and
    ``Q.__and__`` returns a new object, so callers may compose it with their
    own filters without mutating the declaration or a sibling call's result.

    Mirrors ``get_account_state()``'s access-control flags — including
    ``is_active``, which the predicate gained in plan 19 ``B-1``. The one
    deliberate omission remains ``ads_auto_publish``: it is a publishing
    restriction orthogonal to whether an account may receive messages (rule
    5), so it is not a term here. The five conjuncts are ``is_deleted``,
    ``consent_revoked_at``, ``is_declined``, ``is_banned`` and ``is_active``;
    the full rationale is in the phase-06 plan, finding ``06-PII-104``.
    """
    return Q(
        **{
            f"{prefix}is_deleted": False,
            f"{prefix}is_declined": False,
            f"{prefix}is_banned": False,
            f"{prefix}consent_revoked_at__isnull": True,
            f"{prefix}is_active": True,
        }
    )


def can_publish_ad(user: User) -> bool:
    """
    Check if user can publish new ads.

    A user can publish ads only if:
    - NOT banned (admin action)
    - NOT deleted (GDPR withdrawal)
    - ads_auto_publish is True (publishing restriction)

    Args:
        user: User instance to check.

    Returns:
        True if user can publish new ads, False otherwise.
    """
    state = get_account_state(user)

    if state.is_banned:
        logger.info("User %s cannot publish: banned", user.id)
        return False

    if state.is_deleted:
        logger.info("User %s cannot publish: deleted", user.id)
        return False

    if not state.ads_auto_publish:
        logger.info("User %s cannot publish: ads_auto_publish=False", user.id)
        return False

    return True


def can_login(user: User) -> bool:
    """
    Check if user can login.

    A user can login only if NOT deactivated, NOT banned and NOT declined
    consent. Note: Deleted users have telegram_id nulled, so they cannot login
    anyway.

    ``is_active`` was added in plan 19 (``B-1``) so the shared predicate agrees
    with Django's own ``ModelBackend.user_can_authenticate``. ``consent.py``'s
    ``login_status`` view calls this **before** its view-local ``is_active``
    guard and returns the same uniform ``410`` either way, so the web
    rejection status is unchanged — only which branch logs it.

    Args:
        user: User instance to check.

    Returns:
        True if user can login, False otherwise.
    """
    state = get_account_state(user)

    if not state.is_active:
        logger.info("User %s cannot login: deactivated", user.id)
        return False

    if state.is_banned:
        logger.info("User %s cannot login: banned", user.id)
        return False

    if state.is_declined:
        logger.info("User %s cannot login: declined consent", user.id)
        return False

    return True


def get_state_badge(user: User) -> str:
    """
    Get state badge text for dashboard display.

    Returns a human-readable badge for the user's account state.
    Multiple states are separated by commas.

    Args:
        user: User instance to get badge for.

    Returns:
        Badge text string (e.g., "banned", "deleted", "restricted", or empty string).

    Deliberately NO ``is_active`` badge (plan 19, ``B-1``): the badge composes
    hardcoded English fragments, ``UserAdmin.list_display`` does not use it, and
    a deactivated user cannot reach their own dashboard because ``ModelBackend``
    revokes the web session on the next request. A badge would therefore be
    unreachable by its subject and shown only to staff through a surface that
    does not call this function.
    """
    state = get_account_state(user)
    badges = []

    if state.is_banned:
        badges.append("banned")
    if state.is_deleted:
        badges.append("deleted")
    if state.is_declined:
        badges.append("declined")
    if not state.ads_auto_publish:
        badges.append("restricted")

    return ", ".join(badges)
