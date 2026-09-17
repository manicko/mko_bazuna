"""Per-user locale activation middleware for the Telegram bot (FQ-001).

Activates ``translation.activate(user.telegram_language)`` around handler
dispatch so that ``gettext`` calls in handlers render in the user's preferred
language.  Falls back to ``settings.LANGUAGE_CODE`` when the user record does
not exist (e.g. anonymous deep-link contact before login) or the event has no
``from_user`` (e.g. channel posts).

The active locale is thread-local, so ``deactivate()`` is called in a
``finally`` block to prevent locale leakage between updates on the same
asgiref worker thread.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import translation

logger = logging.getLogger(__name__)


class LanguageMiddleware(BaseMiddleware):
    """Activate the Telegram user's preferred language around handler dispatch.

    Registered as an update-level middleware via ``dp.update.middleware(...)``,
    the event is always an ``aiogram.types.Update`` at the update-level.  The
    middleware resolves ``event.from_user.id`` to the ``User.telegram_language``
    field (set via ``/language`` or the Telegram-reported language code at
    registration), calls ``translation.activate(lang)`` before the handler runs,
    and restores the previous locale in a ``finally`` block.

    Placement: must run **before** ``AccountStateMiddleware`` because the
    account-state denial messages are themselves ``_``-wrapped and must render
    in the user's locale.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user = getattr(event, "from_user", None)

        if from_user is None:
            lang = settings.LANGUAGE_CODE
        else:
            lang = await _resolve_user_language(from_user.id)

        translation.activate(lang)
        try:
            return await handler(event, data)
        finally:
            translation.deactivate()


@sync_to_async
def _resolve_user_language(telegram_id: int) -> str:
    """Return the user's ``telegram_language``, falling back to LANGUAGE_CODE.

    Looks up by ``telegram_id`` (the Telegram-reported user ID, never nullified
    on GDPR erasure unlike ``telegram_id`` — actually ``telegram_id`` IS
    nullified on withdrawal; ``chat_id`` is the stable field).  Uses
    ``telegram_id`` here because ``from_user.id`` is always a Telegram ID; if
    the user has withdrawn consent (``telegram_id IS NULL``) the lookup falls
    back to ``LANGUAGE_CODE``.
    """
    from apps.users.models import User

    lang = (
        User.objects.filter(telegram_id=telegram_id)
        .values_list("telegram_language", flat=True)
        .first()
    )
    return lang or settings.LANGUAGE_CODE
