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

from apps.users.models import User

logger = logging.getLogger(__name__)


class AccountStateMiddleware(BaseMiddleware):
    """
    Middleware that checks account state on every Telegram message.

    Enforces three independent account flags:
    - is_banned: Admin action, blocks all bot interactions
    - is_deleted: GDPR withdrawal, blocks all bot interactions (telegram_id nulled)
    - ads_auto_publish=False: Restricts /post command only

    For banned/deleted users: responds with rejection message and skips handler.
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

        telegram_id = message.from_user.id
        text = message.text or ""

        # Check if user is banned or deleted
        can_interact, state_reason = await self._check_user_state(telegram_id)
        if not can_interact:
            await message.answer(state_reason)
            return None

        # Check publish restriction for /post command
        if text.strip().lower() == "/post":
            can_publish, publish_reason = await self._check_publish_permission(telegram_id)
            if not can_publish:
                await message.answer(publish_reason)
                return None

        return await handler(event, data)

    async def _check_user_state(
        self, telegram_id: int
    ) -> tuple[bool, str]:
        """
        Check if user is banned or deleted.

        Args:
            telegram_id: Telegram user ID.

        Returns:
            Tuple of (can_interact, rejection_message).
        """
        try:
            user = await self._get_user(telegram_id)
        except User.DoesNotExist:
            return (True, "")  # User not registered yet

        if user.is_banned:
            return (False, "Your account is banned. Contact support for assistance.")

        if user.is_deleted:
            return (False, "Your account has been deleted.")

        return (True, "")

    async def _check_publish_permission(
        self, telegram_id: int
    ) -> tuple[bool, str]:
        """
        Check if user can publish ads (ads_auto_publish flag).

        Args:
            telegram_id: Telegram user ID.

        Returns:
            Tuple of (can_publish, rejection_message).
        """
        try:
            user = await self._get_user(telegram_id)
        except User.DoesNotExist:
            return (True, "")  # Will be handled by login check

        if not user.ads_auto_publish:
            return (
                False,
                "Your account has publishing restrictions. Contact support for assistance.",
            )

        return (True, "")

    @sync_to_async
    def _get_user(self, telegram_id: int) -> User:
        """
        Get user by telegram_id.

        Args:
            telegram_id: Telegram user ID.

        Returns:
            User instance.

        Raises:
            User.DoesNotExist if user not found.
        """
        return User.objects.get(telegram_id=telegram_id)