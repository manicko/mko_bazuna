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
    """Return the user's preferred language, falling back to the temp store.

    Fallback chain:
    1. The persisted ``User.telegram_language`` (set via ``/language`` or the
       Telegram-reported language code at registration).
    2. The temporary anon-lang cache store, which honors an anonymous user's
       first-screen language choice before they register/login.
    3. ``settings.LANGUAGE_CODE``.

    This middleware identifies the user by ``from_user.id``, which is always a
    Telegram ID and therefore is what ``telegram_id`` refers to here.  Note that
    ``chat_id`` is the stable field used by ``AccountStateMiddleware``, but this
    middleware resolves the user via ``telegram_id`` (matching how the rest of
    the bot identifies users).
    """
    from apps.core.utils.cache import get_cached_anon_language
    from apps.users.models import User

    lang = (
        User.objects.filter(telegram_id=telegram_id)
        .values_list("telegram_language", flat=True)
        .first()
    )
    if lang:
        return lang
    cached = get_cached_anon_language(telegram_id)
    if cached:
        return cached
    return settings.LANGUAGE_CODE
