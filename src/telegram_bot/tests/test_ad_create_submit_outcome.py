"""Bot-level failure branch for ``process_preview`` (AD-016).

Before AD-016 the bot had no test at all for ``process_preview``'s failure
branch, and a gone draft was reported as a moderation failure and then
destroyed the dialog via ``state.clear()``.  These tests pin the fixed
behaviour:

- ``DRAFT_GONE`` does **not** clear the FSM state and **re-points** ``ad_id``
  at a fresh draft (the typed dialog is the only remaining copy);
- a genuine content failure still clears the state and renders the moderation
  message (the fix must not make the bot non-recoverable either way);
- the expired-draft reply is the already-shipped, already-translated string and
  does not blame the seller's content.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.core.enums import AdStatus

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
    pytest.mark.xdist_group("bot_concurrent"),
]


def _build_message(text: str = "confirm", language_code: str | None = "en-US"):
    user_mock = MagicMock()
    user_mock.language_code = language_code
    user_mock.id = 900000100
    user_mock.username = None
    user_mock.first_name = "Test"
    user_mock.last_name = "User"
    message = MagicMock()
    message.text = text
    message.from_user = user_mock
    message.answer = AsyncMock()
    return message


def _build_state(data: dict) -> MagicMock:
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data)
    state.clear = AsyncMock()
    state.update = AsyncMock()
    state.update_data = AsyncMock()
    return state


async def _mock_translate(text: str, target_locales: list[str]) -> dict[str, str]:
    return {loc: f"{text}-{loc}" for loc in target_locales}


class TestProcessPreviewOutcomes:
    """``process_preview`` branches on the named ``SubmitAdOutcome``."""

    @pytest.mark.asyncio
    async def test_draft_gone_repoints_state_to_a_fresh_draft(
        self, seller, category, city
    ) -> None:
        """``DRAFT_GONE`` keeps the FSM data and re-points ``ad_id``.

        The seller's preview dialog must survive a reaped/deleted draft: the
        handler creates a fresh DRAFT and updates ``ad_id`` so the next
        ``confirm`` targets a live row instead of looping against a dead one.
        """
        from telegram_bot.handlers.ad_create import process_preview

        data = {
            "ad_id": 999_999_999,  # absent → DRAFT_GONE
            "title": "Naslov oglasa",
            "description": "Opis oglasa dovoljne dužine za test.",
            "price_amount": 100,
            "price_currency": "EUR",
            "photos": [],
            "user_id": seller.id,
            "category_id": category.id,
            "city_id": city.id,
        }
        state = _build_state(data)
        message = _build_message()

        with patch(
            "telegram_bot.handlers.ad_create.submit.translate_all_languages",
            _mock_translate,
        ):
            await process_preview(message, state)

        state.clear.assert_not_awaited()
        state.update.assert_awaited_once()
        new_ad_id = state.update.await_args.args[0]["ad_id"]
        assert new_ad_id != 999_999_999

        from asgiref.sync import sync_to_async

        from apps.ads.models import Ad

        ad = await sync_to_async(Ad.objects.get)(id=new_ad_id)
        assert ad.status == AdStatus.DRAFT
        assert ad.user_id == seller.id

    @pytest.mark.asyncio
    async def test_draft_gone_reply_is_the_shipped_string_not_a_content_blame(
        self, seller, category, city
    ) -> None:
        """The expired reply is the shipped message and does not blame content."""
        from telegram_bot.handlers.ad_create import process_preview

        data = {
            "ad_id": 999_999_999,
            "title": "Naslov oglasa",
            "description": "Opis oglasa dovoljne dužine za test.",
            "price_amount": 100,
            "price_currency": "EUR",
            "photos": [],
            "user_id": seller.id,
            "category_id": category.id,
            "city_id": city.id,
        }
        state = _build_state(data)
        message = _build_message()

        with patch(
            "telegram_bot.handlers.ad_create.submit.translate_all_languages",
            _mock_translate,
        ):
            await process_preview(message, state)

        rendered = str(message.answer.await_args.args[0])
        assert rendered == (
            "Your draft expired and was deleted. Please start again with /post."
        )
        # It must not be the moderation blame, nor the raw service reason.
        assert "moderation" not in rendered.lower()
        assert "Ad not found" not in rendered

    @pytest.mark.asyncio
    async def test_moderation_failed_clears_state(
        self, seller, category, city
    ) -> None:
        """A genuine content failure still clears the state and blames content."""
        from apps.ads.services.submission import (
            SubmitAdOutcome,
            SubmitAdResult,
        )
        from telegram_bot.handlers.ad_create import process_preview

        data = {
            "ad_id": 1,
            "title": "Valid Title",
            "description": "Valid description text for the ad.",
            "price_amount": 100,
            "price_currency": "EUR",
            "photos": [],
            "user_id": seller.id,
            "category_id": category.id,
            "city_id": city.id,
        }
        state = _build_state(data)
        message = _build_message()

        with (
            patch(
                "telegram_bot.handlers.ad_create.submit.translate_all_languages",
                _mock_translate,
            ),
            patch(
                "telegram_bot.handlers.ad_create.submit.submit_ad",
                return_value=SubmitAdResult(
                    SubmitAdOutcome.MODERATION_FAILED, ["Banned word"]
                ),
            ),
        ):
            await process_preview(message, state)

        assert message.answer.await_args.args[0] == "Banned word"
        state.clear.assert_awaited()
        state.update.assert_not_awaited()


class TestExpiredDraftStringIsShipped:
    """The expired-draft condition reuses the existing, translated msgid."""

    def test_expired_msgid_has_ru_and_bs_translations(self) -> None:
        """``django.po`` carries non-empty ``ru``/``bs`` for the shipped string.

        Guards against authoring a *second* string for the same condition: the
        catalog must still hold exactly the one shipped msgid with both
        non-empty translations.
        """
        from pathlib import Path

        from django.conf import settings

        msgid = (
            "Your draft expired and was deleted. Please start again with /post."
        )
        locale_root = Path(settings.LOCALE_PATHS[0])
        assert locale_root.is_dir(), f"locale root not found: {locale_root}"

        translations = {
            "ru": "Черновик объявления истёк и был удалён. Пожалуйста, начните заново командой /post.",
            "bs": "Vaš nacrt oglasa je istekao i obrisan. Molimo ponovo pokrenite /post.",
        }
        for locale, expected in translations.items():
            po_path = locale_root / locale / "LC_MESSAGES" / "django.po"
            text = po_path.read_text(encoding="utf-8")
            assert f'msgid "{msgid}"' in text, f"missing msgid in {locale}"
            assert f'msgstr "{expected}"' in text, (
                f"missing non-empty {locale} translation for the shipped msgid"
            )

    def test_no_second_expired_string_exists(self) -> None:
        """Only one msgid mentions 'draft expired' across the catalogs."""
        from pathlib import Path

        from django.conf import settings

        locale_root = Path(settings.LOCALE_PATHS[0])
        for locale in ("ru", "bs", "en"):
            po_path = locale_root / locale / "LC_MESSAGES" / "django.po"
            text = po_path.read_text(encoding="utf-8")
            active_lines = [
                line
                for line in text.splitlines()
                if line.startswith("msgid ") and "draft expired" in line.lower()
            ]
            assert len(active_lines) == 1, (
                f"expected exactly one expired-draft msgid in {locale}, "
                f"found {len(active_lines)}"
            )
