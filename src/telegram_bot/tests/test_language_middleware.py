"""
Tests for LanguageMiddleware.__call__ lifecycle (B26 GAP-3).

Previously only ``_resolve_user_language`` was covered. These tests verify the
full middleware contract: ``translation.activate`` wraps the handler dispatch,
``translation.deactivate`` runs in a ``finally`` block, and ``from_user is None``
falls back to ``settings.LANGUAGE_CODE``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext as _

from telegram_bot.middlewares.language import LanguageMiddleware

pytestmark = [pytest.mark.unit]


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
class TestLanguageMiddlewareCall:
    """Verify the full __call__ lifecycle: activate → handler → deactivate."""

    @pytest.mark.asyncio
    async def test_activates_user_locale_around_handler(self) -> None:
        """The user's language is active during handler dispatch, deactivated after."""
        from apps.users.models import User

        user = await sync_to_async(User.objects.create)(
            telegram_id=900000350,
            chat_id=900000350,
            username="middleware_user",
            telegram_language="ru",
        )
        try:
            middleware = LanguageMiddleware()

            captured_lang: list[str] = []

            async def handler(event, data):
                # Inside the handler, Russian should be active.
                captured_lang.append(translation.get_language())
                # gettext should resolve to Russian.
                assert _("Contact us") == "Связаться с нами"
                return "handler-result"

            event = MagicMock()
            event.from_user = MagicMock(id=user.telegram_id)

            result = await middleware(handler, event, {})

            assert result == "handler-result"
            assert captured_lang[0] == "ru"
        finally:
            await sync_to_async(user.delete)()

    @pytest.mark.asyncio
    async def test_deactivates_locale_after_handler(self) -> None:
        """The locale is restored (deactivated) after the handler returns."""
        from apps.users.models import User

        user = await sync_to_async(User.objects.create)(
            telegram_id=900000351,
            chat_id=900000351,
            username="deactivate_user",
            telegram_language="ru",
        )
        try:
            middleware = LanguageMiddleware()

            # Activate a different locale before the middleware runs.
            translation.activate("en")
            lang_before = translation.get_language()

            async def handler(event, data):
                return "ok"

            event = MagicMock()
            event.from_user = MagicMock(id=user.telegram_id)

            await middleware(handler, event, {})

            # After the middleware, the locale should be deactivated back.
            lang_after = translation.get_language()
            assert lang_before != "ru"  # we set en before
            assert lang_after == lang_before
        finally:
            await sync_to_async(user.delete)()
        # Restore clean state
        translation.deactivate()

    @pytest.mark.asyncio
    async def test_from_user_none_falls_back_to_settings(self) -> None:
        """When event has no from_user, the default LANGUAGE_CODE is used."""
        middleware = LanguageMiddleware()

        captured_lang: list[str] = []

        async def handler(event, data):
            captured_lang.append(translation.get_language())
            return "ok"

        event = MagicMock()
        event.from_user = None

        await middleware(handler, event, {})

        assert captured_lang[0] == settings.LANGUAGE_CODE

    @pytest.mark.asyncio
    async def test_handler_exception_still_deactivates(self) -> None:
        """If the handler raises, the finally block still deactivates the locale."""
        from apps.users.models import User

        user = await sync_to_async(User.objects.create)(
            telegram_id=900000352,
            chat_id=900000352,
            username="exception_user",
            telegram_language="ru",
        )
        try:
            middleware = LanguageMiddleware()

            class HandlerError(Exception):
                pass

            async def handler(event, data):
                assert translation.get_language() == "ru"
                raise HandlerError("handler failed")

            event = MagicMock()
            event.from_user = MagicMock(id=user.telegram_id)

            with pytest.raises(HandlerError):
                await middleware(handler, event, {})
        finally:
            await sync_to_async(user.delete)()
        translation.deactivate()

    @pytest.mark.asyncio
    async def test_unknown_user_falls_back_to_default(self) -> None:
        """A Telegram ID with no User row falls back to LANGUAGE_CODE."""
        middleware = LanguageMiddleware()

        captured_lang: list[str] = []

        async def handler(event, data):
            captured_lang.append(translation.get_language())
            return "ok"

        event = MagicMock()
        event.from_user = MagicMock(id=999_999_999)

        await middleware(handler, event, {})

        assert captured_lang[0] == settings.LANGUAGE_CODE
