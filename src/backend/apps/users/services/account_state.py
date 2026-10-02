"""
Account state service for Mko Bazuna.

Distinguishes ban vs delete vs publish-restriction. Three independent flags.
Used by both web dashboard and bot for account state checking.

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
    """Account state flags for access control."""

    is_banned: bool
    is_deleted: bool
    is_declined: bool
    ads_auto_publish: bool
    consent_revoked: bool


def get_account_state(user: User) -> AccountState:
    """
    Get account state flags for a user.

    Returns a tuple of the three independent account state flags:
    - is_banned: Admin action, blocks login/publish, PII retained
    - is_deleted: GDPR consent withdrawal, telegram_id nulled
    - is_declined: User declined consent (browse-only mode)
    - ads_auto_publish: Publishing restriction, not linked to ban/delete

    Args:
        user: User instance to check.

    Returns:
        AccountState named tuple with all flags.
    """
    return AccountState(
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

    Mirrors ``get_account_state()`` except for ``is_active`` — see the honest
    limit documented on the queryset-level tests. The five conjuncts are
    ``is_deleted``, ``consent_revoked_at``, ``is_declined``, ``is_banned`` and
    ``is_active``; the full rationale is in the phase-06 plan, finding
    ``06-PII-104``.
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

    A user can login only if NOT banned and NOT declined consent.
    Note: Deleted users have telegram_id nulled, so they cannot login anyway.

    Args:
        user: User instance to check.

    Returns:
        True if user can login, False otherwise.
    """
    state = get_account_state(user)

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
