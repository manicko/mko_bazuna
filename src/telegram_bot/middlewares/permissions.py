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
from telegram_bot.schemas.callbacks import BotCallbackPrefix
from telegram_bot.states import ContactUsState

logger = logging.getLogger(__name__)


def _is_login_deep_link(text: str) -> bool:
    """Whether ``text`` is a ``/start login_<token>`` deep-link.

    This is the narrowest correct recognition of the existing token-handshake
    shape: it reuses ``LOGIN_PATTERN`` (the very pattern ``handle_login_deep_link``
    matches), so the carve-out and the handler can never disagree about what a
    login deep-link is. A bare ``text.startswith("login_")`` would also swallow
    ``login_start``, ``login_email`` and ``login_help`` — widening the carve-out
    well beyond the token handshake and letting a declined user reach arguments
    the handler then refuses anyway.

    The pattern is imported lazily, mirroring the contact-classifier import in
    ``__call__``: importing ``telegram_bot.handlers`` at module import time would
    run the handlers package ``__init__`` and risk a middleware/handler cycle.

    The pattern is anchored to the ``login_<32-char-token>`` payload, so only a
    real deep-link argument matches. ``/start`` itself is not a login deep-link
    — it is handled by the handler's no-argument greeting branch.
    """
    args = text.split(maxsplit=1)
    if len(args) < 2:
        return False
    from telegram_bot.handlers.login import LOGIN_PATTERN

    return LOGIN_PATTERN.match(args[1]) is not None


class AccountStateMiddleware(BaseMiddleware):
    """
    Middleware that checks account state on every Telegram message.

    Delegates flag evaluation to the shared ``get_account_state`` predicate
    (``apps.users.services.account_state``) so that bot and web dashboard
    share a single source of truth for account-state flags. That claim is now
    literal (plan 19, ``B-2``): the predicate carries ``is_active``, the field
    the bot middleware previously could not see.

    Enforces five independent account flags (plus the publish restriction):
    - is_active: Operator kill-switch (plan 18), blocks all bot interactions
      EXCEPT the support carve-out below
    - is_banned: Admin action, blocks all bot interactions
    - is_deleted: GDPR withdrawal, blocks all bot interactions (telegram_id nulled)
    - is_declined: User declined consent, blocks posting but allows contact and
      login deep-links (browse-only). A decline is reversible (06-PII-105), so the
      ``login_<token>`` handshake is the route back to the authenticated consent
      form that clears it.
    - consent_revoked: Consent withdrawn, blocks all bot interactions (data erasing)
    - ads_auto_publish=False: Restricts /post command only

    **Support carve-out for a deactivated user (plan 19, ``19-D2``/``19-D6``).**
    Unlike every other blocking flag, deactivation is recoverable by the user,
    so a deactivated account is allowed exactly three things: the
    **no-argument** ``/start`` greeting (which carries the "Contact support"
    button), the ``BotCallbackPrefix.SUPPORT_START`` callback, and free text
    while in the support-intake FSM state (``ContactUsState.AWAITING_MESSAGE``).
    Everything else — every other command, the whole ad-creation flow, and the
    ``contact_us`` / ``contact_<id>`` deep-links — is blocked. ``/start`` with
    any argument is blocked (``19-D6``): a stale ``login_<token>`` link cannot
    succeed anyway, so rendering its keyboard would only widen the carve-out.

    The carve-out is **state-based, not event-based** (``R-1``): the free-text
    step of the intake flow is ordinary text, so an event-type allowlist would
    let the user tap the button but never complete the ticket. It is granted
    only when deactivation is the account's *sole* blocking flag, so a
    deactivated-and-banned / erased account gets no restoration channel. The
    support message intake is rate-limited (5 per 600 s,
    ``telegram_bot.services.rate_limit``); this middleware adds no second limiter.

    For banned/deleted/declined/withdrawn users: responds with rejection
    message and skips handler. For a deactivated user outside the carve-out:
    responds with a deactivation message pointing at support. For
    publish-restricted users: allows other commands but blocks /post.

    Resolution contract: the acting ``User`` is resolved exactly once per
    update, keyed on the stable ``chat_id`` (never ``telegram_id`` — see
    ``_resolve_user`` for the column rationale).  All three consumers — the
    interaction gate, the publish gate, and the FSM ``user_id`` backfill —
    share that one resolution, and the deactivation carve-out reads the FSM
    state from the shared ``data`` dict rather than re-querying.  An
    unregistered ``chat_id`` is a memoised absent state (``None``), not an
    error, and each consumer applies its own existing tolerance to it.  Any new
    consumer must take the resolved instance, must not re-query, and must not
    mutate or ``.save()`` it (the login path owns its own instance).
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

        # A login deep-link is the route BACK from a decline (06-PII-105): it is
        # the existing LoginToken handshake, reachable at /login/issue/ ->
        # bot /start login_<token> -> /login/status/. Like the contact carve-out,
        # it applies to a declined user only; every other blocking flag still
        # refuses even a login deep-link.
        is_login_link = _is_login_deep_link(text)

        # Resolve the acting user ONCE per update; every consumer below
        # shares this instance.  Keyed on the stable chat_id, never
        # telegram_id: see the class docstring for the column rationale.
        user = await self._resolve_user(chat_id)

        # The support carve-out (plan 19, 19-D2) needs the FSM state. Read it
        # from the shared ``data`` dict — the same ``FSMContext`` the backfill
        # below uses — and only for a deactivated account, so a normal update
        # pays no extra storage round-trip and the carve-out never re-queries
        # the user.
        is_support_intake = False
        if user is not None and not user.is_active:
            is_support_intake = await self._is_in_support_intake(data)

        deactivation_carve_out = self._deactivated_carve_out(
            text=text,
            callback_data=callback_data,
            is_support_intake=is_support_intake,
        )

        can_interact, state_reason = self._evaluate_user_state(
            user,
            is_contact_link=is_contact_link,
            is_login_link=is_login_link,
            deactivation_carve_out=deactivation_carve_out,
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
        self,
        chat_id: int,
        is_contact_link: bool = False,
        deactivation_carve_out: bool = False,
        is_login_link: bool = False,
    ) -> tuple[bool, str]:
        """
        Resolve a chat_id and evaluate the interaction gate in one step.

        Convenience entry point for callers that hold only a chat_id (tests,
        and any future single-consumer path).  ``__call__`` does **not** use
        it — it resolves once and calls ``_evaluate_user_state`` so that the
        publish gate and the FSM backfill share the same instance.

        The signature's first parameter is load-bearing:
        ``TestCheckUserStateMessages`` and ``TestCrossPredicateAgreement`` call
        ``_check_user_state(chat_id)`` with a single positional argument.  Do
        not change it.  ``deactivation_carve_out`` and ``is_login_link``
        default to False, so those existing calls are unaffected and a
        deactivated user is blocked.

        Args:
            chat_id: Stable Telegram chat ID.
            is_contact_link: True if the current event is a contact deep-link
                (``/start contact_<ad_id>``, ``/start contact_us``, or the
                inline ``contact_us`` callback).  DECLINE users are allowed
                through contact deep-links only (browse-only consent).
            deactivation_carve_out: True if a deactivated user's update falls
                inside the support carve-out (no-arg ``/start``,
                ``SUPPORT_START`` callback, or support-intake free text).
            is_login_link: True if the current event is a ``/start
                login_<token>`` deep-link. DECLINE users are allowed through it
                (06-PII-105): it is the route back to the authenticated consent
                form that clears the decline.

        Returns:
            Tuple of (can_interact, rejection_message).
        """
        user = await self._resolve_user(chat_id)
        return self._evaluate_user_state(
            user,
            is_contact_link=is_contact_link,
            is_login_link=is_login_link,
            deactivation_carve_out=deactivation_carve_out,
        )

    async def _is_in_support_intake(self, data: dict[str, Any]) -> bool:
        """Whether the update is free text inside the support-intake FSM.

        Reads the FSM state from the shared ``data["state"]`` (never a fresh
        storage lookup) so the carve-out stays state-based (``R-1``) without
        re-querying the user. A missing ``state`` — or a storage backend that
        has no entry — is treated as "not in the flow".
        """
        state: FSMContext | None = data.get("state")
        if state is None:
            return False
        return await state.get_state() == ContactUsState.AWAITING_MESSAGE

    def _deactivated_carve_out(
        self,
        *,
        text: str,
        callback_data: str | None,
        is_support_intake: bool,
    ) -> bool:
        """Whether a deactivated user's update is inside the support carve-out.

        Exactly three shapes qualify (plan 19 §3): the ``SUPPORT_START``
        callback, ordinary free text in the support-intake state, and the
        **no-argument** ``/start`` greeting. ``/start <anything>`` is
        deliberately excluded (``19-D6``). Contact deep-links are excluded
        (``19-D2``). The intake carve-out admits **free text only** — a
        command (``/post``, ``/language``, …) typed while in the intake state
        is still blocked, so the carve-out never becomes a route to the
        ad-creation or any other command flow.
        """
        if callback_data == BotCallbackPrefix.SUPPORT_START:
            return True
        if (
            is_support_intake
            and callback_data is None
            and text.strip()
            and not text.lstrip().startswith("/")
        ):
            return True
        return text.strip().lower() == "/start"

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
        self,
        user: User | None,
        *,
        is_contact_link: bool,
        is_login_link: bool = False,
        deactivation_carve_out: bool = False,
    ) -> tuple[bool, str]:
        """
        Evaluate the interaction gate from an already-resolved user.

        Pure: no DB access, no mutation of ``user``.  Delegates flag reading
        to the shared ``get_account_state`` predicate so the bot and the web
        dashboard evaluate account-state flags from one source of truth.

        ``is_active`` is evaluated **first** (plan 19, ``B-2``): a deactivated
        account gets one clear answer, and its recovering support carve-out is
        unreachable when any other blocking flag is set.

        Args:
            user: The resolved acting user, or None if unregistered.
            is_contact_link: True if the current event is a contact deep-link
                (``/start contact_<ad_id>``, ``/start contact_us``, or the
                inline ``contact_us`` callback).  DECLINE users are allowed
                through contact deep-links only (browse-only consent).
            is_login_link: True if the current event is a ``/start
                login_<token>`` deep-link. DECLINE users are allowed through it
                (06-PII-105); every other blocking flag still refuses.
            deactivation_carve_out: True if a deactivated user's update is the
                no-arg ``/start`` / ``SUPPORT_START`` / support-intake free
                text. Ignored for a non-deactivated account.

        Returns:
            Tuple of (can_interact, rejection_message).  An unregistered user
            is fail-open: (True, "") — the handler's own gate rejects them.
        """
        if user is None:
            return (True, "")  # User not registered yet

        state = get_account_state(user)

        # Plan 19, 19-D2: a deactivated account is recoverable by the user, so
        # it is granted a support carve-out — but only when deactivation is its
        # SOLE blocking flag. A deactivated-and-banned / erased account gets no
        # restoration channel (the carve-out is unreachable for it).
        if not state.is_active:
            if (
                deactivation_carve_out
                and not state.is_banned
                and not state.is_deleted
                and not state.is_declined
                and not state.consent_revoked
            ):
                return (True, "")  # Support carve-out: restoration channel
            return (
                False,
                _(
                    "Your account is deactivated. To restore access, "
                    "contact support."
                ),
            )

        if state.is_banned:
            return (
                False,
                _("Your account is restricted. Contact support for assistance."),
            )

        if state.is_deleted:
            return (False, _("Your account has been deleted."))

        if state.is_declined:
            # DECLINE = browse-only. Two carve-outs are peers and both apply to
            # a declined user only: the contact deep-link (contact still works
            # while publishing does not) and the login deep-link, which is the
            # route BACK — the existing LoginToken handshake is how the
            # authenticated consent form that clears the decline is reached
            # (06-PII-105). Order is deliberate: neither is granted to a
            # banned/deleted/withdrawn account (this branch is after those).
            if is_contact_link or is_login_link:
                return (True, "")
            return (
                False,
                _(
                    "Consent declined: you can browse but cannot post. "
                    "You can change this from the site or by logging in here. "
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
