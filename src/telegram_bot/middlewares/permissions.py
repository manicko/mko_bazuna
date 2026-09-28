"""
Bot permission middleware for Mko Bazuna.

Checks account state flags (is_banned, is_deleted, ads_auto_publish) on every message.
Prevents banned/deleted users from any interaction and restricts publishing for
users with ads_auto_publish=False.
"""

import logging
from typing import Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, TelegramObject, Update
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
    - is_declined: User declined consent, blocks posting but allows contact deep-links (browse-only)
    - consent_revoked: Consent withdrawn, blocks all bot interactions (data erasing)
    - ads_auto_publish=False: Restricts /post command only

    For banned/deleted/declined/withdrawn users: responds with rejection message and skips handler.
    For publish-restricted users: allows other commands but blocks /post.

    Resolution contract: the acting ``User`` is resolved exactly once per
    update, keyed on the stable ``chat_id`` (never ``telegram_id`` — see
    ``_resolve_user`` for the column rationale).  All three consumers — the
    interaction gate, the publish gate, and the FSM ``user_id`` backfill —
    share that one resolution.  An unregistered ``chat_id`` is a memoised
    absent state (``None``), not an error, and each consumer applies its own
    existing tolerance to it.  Any new consumer must take the resolved
    instance, must not re-query, and must not mutate or ``.save()`` it (the
    login path owns its own instance).
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

        # Resolve the acting user identity. For callback_query updates the
        # message is the bot-sent message carrying the inline keyboard, so
        # message.from_user is the bot's identity — the acting user is
        # callback_query.from_user. Fall back to message.from_user for plain
        # Message updates.
        if event.callback_query is not None:
            from_user = event.callback_query.from_user
        else:
            from_user = message.from_user

        if from_user is None:
            return await handler(event, data)

        chat_id = from_user.id
        text = message.text or ""

        # Lazy import to avoid any circular dependency with handlers.
        from telegram_bot.handlers.contact import classify_contact_deep_link

        # Classify contact deep-links — DECLINE users may contact (browse-only).
        # The contact R2 service (core/services/contact.py) re-enforces seller-side safety.
        callback_data = event.callback_query.data if event.callback_query else None
        is_contact_link = classify_contact_deep_link(text, callback_data) is not None

        # Resolve the acting user ONCE per update; every consumer below
        # shares this instance.  Keyed on the stable chat_id, never
        # telegram_id: see the class docstring for the column rationale.
        user = await self._resolve_user(chat_id)

        can_interact, state_reason = self._evaluate_user_state(
            user, is_contact_link=is_contact_link
        )
        if not can_interact:
            await message.answer(state_reason)
            return None

        # Check publish restriction for /post command
        if text.strip().lower() == "/post":
            can_publish, publish_reason = self._evaluate_publish_permission(user)
            if not can_publish:
                await message.answer(publish_reason)
                return None

        # Backfill user_id from ORM for restart recovery (AUT-001).
        # In production with RedisStorage, FSM state survives bot container restarts.
        # In dev/test with MemoryStorage (REDIS_URL empty), FSM state is cleared on
        # restart and handlers (ad_create, ad_copy, alerts, language) that gate on
        # state.get_data()["user_id"] would reject all users. The backfill
        # recovers the user reference by stable chat_id lookup so handlers work
        # transparently without code changes — serving as defense-in-depth even
        # when RedisStorage preserves state.
        state: FSMContext | None = data.get("state")
        if state is not None:
            fsm_data = await state.get_data()
            # ``user is None`` is the memoised absent state: an unregistered
            # chat_id gets no backfill and the handler's own gate rejects.
            if "user_id" not in fsm_data and user is not None:
                await state.update_data(user_id=user.id)

        return await handler(event, data)

    async def _check_user_state(
        self, chat_id: int, is_contact_link: bool = False
    ) -> tuple[bool, str]:
        """
        Resolve a chat_id and evaluate the interaction gate in one step.

        Convenience entry point for callers that hold only a chat_id (tests,
        and any future single-consumer path).  ``__call__`` does **not** use
        it — it resolves once and calls ``_evaluate_user_state`` so that the
        publish gate and the FSM backfill share the same instance.

        The signature is load-bearing: ``TestCheckUserStateMessages`` and
        ``TestCrossPredicateAgreement`` call ``_check_user_state(chat_id)``
        with a single positional argument.  Do not change it.

        Args:
            chat_id: Stable Telegram chat ID.
            is_contact_link: True if the current event is a contact deep-link
                (``/start contact_<ad_id>``, ``/start contact_us``, or the
                inline ``contact_us`` callback).  DECLINE users are allowed
                through contact deep-links only (browse-only consent).

        Returns:
            Tuple of (can_interact, rejection_message).
        """
        user = await self._resolve_user(chat_id)
        return self._evaluate_user_state(user, is_contact_link=is_contact_link)

    @sync_to_async
    def _resolve_user(self, chat_id: int) -> User | None:
        """
        Resolve the acting user by stable chat_id, once per update.

        Uses chat_id instead of telegram_id so that withdrawn/deleted users
        (whose telegram_id is nulled by GDPR erasure) are still found.
        ``telegram_id`` and ``chat_id`` can match different rows for a
        withdrawn user or an admin-created placeholder account, so the two
        columns are not interchangeable; the bot's account gate is keyed on
        chat_id by design (``test_backfill_uses_stable_chat_id``).

        A missing row is an ordinary, memoised outcome — ``None`` — not an
        exception.  Callers apply their own tolerance to ``None``; none of
        them re-queries.

        Args:
            chat_id: Stable Telegram chat ID (the acting user's Telegram ID).

        Returns:
            The User instance, or None if the chat_id is not registered.
        """
        try:
            return User.objects.get(chat_id=chat_id)
        except User.DoesNotExist:
            return None

    def _evaluate_user_state(
        self, user: User | None, *, is_contact_link: bool
    ) -> tuple[bool, str]:
        """
        Evaluate the interaction gate from an already-resolved user.

        Pure: no DB access, no mutation of ``user``.  Delegates flag reading
        to the shared ``get_account_state`` predicate so the bot and the web
        dashboard evaluate account-state flags from one source of truth.

        Args:
            user: The resolved acting user, or None if unregistered.
            is_contact_link: True if the current event is a contact deep-link
                (``/start contact_<ad_id>``, ``/start contact_us``, or the
                inline ``contact_us`` callback).  DECLINE users are allowed
                through contact deep-links only (browse-only consent).

        Returns:
            Tuple of (can_interact, rejection_message).  An unregistered user
            is fail-open: (True, "") — the handler's own gate rejects them.
        """
        if user is None:
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
            if is_contact_link:
                return (True, "")  # DECLINE = browse-only; contact deep-link is allowed
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

    def _evaluate_publish_permission(self, user: User | None) -> tuple[bool, str]:
        """
        Evaluate the /post publish gate from an already-resolved user.

        Pure: no DB access, no mutation of ``user``.

        Args:
            user: The resolved acting user, or None if unregistered.

        Returns:
            Tuple of (can_publish, rejection_message).  An unregistered user
            is fail-open: (True, "") — the login check handles them.
        """
        if user is None:
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
