"""
Account state service for Mko Bazuna.

Distinguishes ban vs delete vs publish-restriction. Three independent flags.
Used by both web dashboard and bot for account state checking.
"""

import logging
from typing import NamedTuple

from apps.users.models import User

logger = logging.getLogger(__name__)


class AccountState(NamedTuple):
    """Account state flags for access control."""

    is_banned: bool
    is_deleted: bool
    ads_auto_publish: bool
    consent_revoked: bool


def get_account_state(user: User) -> AccountState:
    """
    Get account state flags for a user.

    Returns a tuple of the three independent account state flags:
    - is_banned: Admin action, blocks login/publish, PII retained
    - is_deleted: GDPR consent withdrawal, telegram_id nulled
    - ads_auto_publish: Publishing restriction, not linked to ban/delete

    Args:
        user: User instance to check.

    Returns:
        AccountState named tuple with all flags.
    """
    return AccountState(
        is_banned=user.is_banned,
        is_deleted=user.is_deleted,
        ads_auto_publish=user.ads_auto_publish,
        consent_revoked=user.consent_revoked_at is not None,
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
        logger.info(f"User {user.telegram_id} cannot publish: banned")
        return False

    if state.is_deleted:
        logger.info(f"User {user.telegram_id} cannot publish: deleted")
        return False

    if not state.ads_auto_publish:
        logger.info(f"User {user.telegram_id} cannot publish: ads_auto_publish=False")
        return False

    return True


def can_login(user: User) -> bool:
    """
    Check if user can login.

    A user can login only if NOT banned.
    Note: Deleted users have telegram_id nulled, so they cannot login anyway.

    Args:
        user: User instance to check.

    Returns:
        True if user can login, False otherwise.
    """
    state = get_account_state(user)

    if state.is_banned:
        logger.info(f"User {user.telegram_id} cannot login: banned")
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
    if not state.ads_auto_publish:
        badges.append("restricted")

    return ", ".join(badges)