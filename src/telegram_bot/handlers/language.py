"""
Language preference handler for the Telegram bot.

Provides a ``/language`` command that lets users choose their preferred UI
language (ru / bs / en). The choice is persisted on the ``User`` model's
``telegram_language`` field so that alert messages (AL-002) and other bot
output are rendered in the user's preferred language.
"""

import logging

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from asgiref.sync import sync_to_async

from apps.core.enums import LanguageLocale
from apps.users.models import User

logger = logging.getLogger(__name__)

router = Router()

# Callback prefix for language selection (callback_data="lang:<code>").
LANG_CALLBACK_PREFIX = "lang:"


@router.message(Command("language"))
async def cmd_language(message: types.Message, state: FSMContext) -> None:
    """Show an inline keyboard to pick the preferred language."""
    if not message.from_user:
        return

    data = await state.get_data()
    user_id = data.get("user_id")
    if not user_id:
        await message.answer(
            "Please login first with /start login_<token>"
        )
        return

    current_lang = await _get_user_language(user_id)
    keyboard = build_language_keyboard(current_lang)
    await message.answer(
        "Select your preferred language:",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith(LANG_CALLBACK_PREFIX))
async def handle_language_callback(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Persist the selected language for the current user."""
    if not callback.data:
        return

    lang_code = callback.data[len(LANG_CALLBACK_PREFIX):]
    try:
        locale = LanguageLocale(lang_code)
    except ValueError:
        await callback.answer("Unsupported language.", show_alert=True)
        return

    data = await state.get_data()
    user_id = data.get("user_id")
    if not user_id:
        await callback.answer("Please login first.", show_alert=True)
        return

    await _set_user_language(user_id, locale.value)

    keyboard = build_language_keyboard(locale.value)
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer(f"Language set to {locale.value}")


def build_language_keyboard(current: str = "") -> InlineKeyboardMarkup:
    """Build an inline keyboard with one button per supported language.

    The currently selected language shows a checkmark.
    """
    buttons: list[list[InlineKeyboardButton]] = []
    labels = {
        LanguageLocale.RUSSIAN.value: "🇷🇺 Русский",
        LanguageLocale.BOSNIAN.value: "🇧🇦 Bosanski",
        LanguageLocale.ENGLISH.value: "🇬🇧 English",
    }
    for locale in LanguageLocale:
        text = labels.get(locale.value, locale.value)
        if locale.value == current:
            text = f"✅ {text}"
        buttons.append([
            InlineKeyboardButton(
                text=text,
                callback_data=f"{LANG_CALLBACK_PREFIX}{locale.value}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@sync_to_async
def _get_user_language(user_id: int) -> str:
    """Read the stored telegram_language for a user."""
    return (
        User.objects.filter(id=user_id)
        .values_list("telegram_language", flat=True)
        .first()
    ) or LanguageLocale.RUSSIAN.value


@sync_to_async
def _set_user_language(user_id: int, lang_code: str) -> None:
    """Persist the selected language on the user row."""
    updated = User.objects.filter(id=user_id).update(
        telegram_language=lang_code
    )
    logger.info(
        "telegram_language updated for user %s to %s (rows=%d)",
        user_id,
        lang_code,
        updated,
    )
