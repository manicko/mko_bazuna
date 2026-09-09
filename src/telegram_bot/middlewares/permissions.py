"""
Bot permission middleware for Mko Bazuna.

Checks account state flags (is_banned, is_deleted, ads_auto_publish) on every message.
Prevents banned/deleted users from any interaction and restricts publishing for
users with ads_auto_publish=False.
"""

import logging
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, Message
from asgiref.sync import sync_to_async
from django.utils.translation import gettext as _

from apps.users.models import User
from apps.users.services.account_state import get_account_state

logger = logging.getLogger(__name__)


class AccountStateMiddleware(BaseMiddleware):
    """
    Middleware that checks account state on every Telegram message.

    Delegates flag evaluation to the shared ``get_account_state`` predicate
    (``apps.users.services.account_state``) so that bot and web dashboard
    share a single source of truth for account-state flags.

    Enforces four independent account flags:
    - is_banned: Admin action, blocks all bot interactions
    - is_deleted: GDPR withdrawal, blocks all bot interactions (telegram_id nulled)
    - is_declined: User declined consent, blocks all bot interactions (browse-only)
    - consent_revoked: Consent withdrawn, blocks all bot interactions (data erasing)
    - ads_auto_publish=False: Restricts /post command only

    For banned/deleted/declined/withdrawn users: responds with rejection message and skips handler.
    For publish-restricted users: allows other commands but blocks /post.
    """

    async def __call__(
        self,
        handler: Any,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """
        Process event and check account state.

        Args:
            handler: Next handler in chain.
            event: Telegram event (Update).
            data: Handler data dict.

        Returns:
            Handler result or None if blocked.
        """
        # Only process Update events
        if not isinstance(event, Update):
            return await handler(event, data)

        # Extract message from update (handle both message and callback_query)
        # Note: callback_query.message can be InaccessibleMessage, so we need to check
        message: Message | None = event.message
        if (
            event.callback_query is not None
            and event.callback_query.message is not None
        ):
            cb_msg = event.callback_query.message
            if isinstance(cb_msg, Message):
                message = cb_msg

        if message is None:
            return await handler(event, data)

        # Check if from_user exists
        if message.from_user is None:
            return await handler(event, data)

        chat_id = message.from_user.id
        text = message.text or ""

        # Check if user is banned, deleted, or has revoked consent
        can_interact, state_reason = await self._check_user_state(chat_id)
        if not can_interact:
            await message.answer(state_reason)
            return None

        # Check publish restriction for /post command
        if text.strip().lower() == "/post":
            can_publish, publish_reason = await self._check_publish_permission(chat_id)
            if not can_publish:
                await message.answer(publish_reason)
                return None

        return await handler(event, data)

    async def _check_user_state(self, chat_id: int) -> tuple[bool, str]:
        """
        Check if user is banned, deleted, declined, or has revoked consent.

        Delegates to the shared ``get_account_state`` predicate so that the
        bot and web dashboard evaluate account-state flags from one source of
        truth. Returns a state-specific denial message for each blocked state.

        Uses stable chat_id (never nullified) instead of telegram_id to ensure
        withdrawn/deleted users are properly blocked.

        Args:
            chat_id: Stable Telegram chat ID.

        Returns:
            Tuple of (can_interact, rejection_message).
        """
        try:
            user = await self._get_user(chat_id)
        except User.DoesNotExist:
            return (True, "")  # User not registered yet

        state = get_account_state(user)

        if state.is_banned:
            return (
                False,
                _("Your account is restricted. Contact support for assistance."),
            )

        if state.is_deleted:
            return (False, _("Your account has been deleted."))

        if state.is_declined:
            return (
                False,
                _(
                    "Consent declined: you can browse but cannot post. "
                    "Contact still works."
                ),
            )

        if state.consent_revoked:
            return (False, _("Consent withdrawn: your data is being erased."))

        return (True, "")

    async def _check_publish_permission(self, chat_id: int) -> tuple[bool, str]:
        """
        Check if user can publish ads (ads_auto_publish flag).

        Delegates to the shared ``get_account_state`` predicate for flag access.
        Uses stable chat_id lookup.

        Args:
            chat_id: Stable Telegram chat ID.

        Returns:
            Tuple of (can_publish, rejection_message).
        """
        try:
            user = await self._get_user(chat_id)
        except User.DoesNotExist:
            return (True, "")  # Will be handled by login check

        state = get_account_state(user)

        if not state.ads_auto_publish:
            return (
                False,
                _(
                    "Your account has publishing restrictions. Contact support for assistance."
                ),
            )

        return (True, "")

    @sync_to_async
    def _get_user(self, chat_id: int) -> User:
        """
        Get user by stable chat_id.

        Uses chat_id instead of telegram_id so that withdrawn/deleted users
        (whose telegram_id is nulled) are still found by the middleware.

        Args:
            chat_id: Stable Telegram chat ID.

        Returns:
            User instance.

        Raises:
            User.DoesNotExist if user not found.
        """
        return User.objects.get(chat_id=chat_id)
