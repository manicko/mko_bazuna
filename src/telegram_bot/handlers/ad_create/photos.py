"""Photos-step FSM handler for the Telegram bot ad-creation flow.

Extracted verbatim from ``telegram_bot/handlers/ad_create/__init__.py``
(10-QLT-003 B15). Processes photo uploads with validation and rate limiting.
Shares the package-level ``router`` and ``AdCreateForm`` and imports
``show_preview`` directly from ``.preview`` to avoid a circular import through
the package init.
"""

from aiogram import types
from aiogram.fsm.context import FSMContext
from django.utils.translation import gettext as _

from apps.media.services.filesystem import generate_storage_key, validate_photo
from telegram_bot.handlers.ad_create import MAX_PHOTO_BYTES, AdCreateForm, router
from telegram_bot.schemas.message_payloads import PhotoCountPayload
from telegram_bot.services.ad_data import download_photo, save_photo
from telegram_bot.services.rate_limit import check_upload_rate_limit

from .preview import show_preview


@router.message(AdCreateForm.photos)
async def process_photos(message: types.Message, state: FSMContext) -> None:
    """Process photo uploads with validation."""

    data = await state.get_data()

    photos = data.get("photos", [])

    # Handle 'done' command

    if message.text and message.text.strip().lower() == "done":
        count = len(photos)

        try:
            PhotoCountPayload(photo_count=count)

        except Exception:
            if count == 0:
                await message.answer(_("Please send at least 1 photo before finishing."))
            else:
                await message.answer(
                    _("You can upload at most 5 photos (you have {count}).").format(
                        count=count
                    )
                )
            return

        await state.set_state(AdCreateForm.preview)

        await show_preview(message, data)

        return

    # Validate photo exists

    if not message.photo:
        await message.answer(_("Please send a photo (JPEG only) or 'done' to finish."))

        return

    # Get largest photo

    photo = message.photo[-1]

    # Enforce the hard cap before downloading — prevents unbounded uploads
    # and orphaned files beyond the 5-photo limit.
    if len(photos) >= 5:
        await message.answer(
            _("You already have {count} photos. You can upload at most 5 photos.").format(
                count=len(photos)
            )
        )
        return

    # Enforce per-seller upload burst limit (anti-abuse).
    user_id = data.get("user_id")
    if user_id is not None and not await check_upload_rate_limit(user_id):
        await message.answer(_("Uploading too fast, please wait a moment."))
        return

    # Pre-check Telegram-reported file_size before downloading to prevent
    # memory exhaustion from oversized uploads (MED-002). The post-download
    # validate_photo size check is retained as defense-in-depth.

    if photo.file_size is not None and photo.file_size > MAX_PHOTO_BYTES:
        await message.answer(_("Photo too large. Maximum size is approximately 2MB."))
        return

    # Download photo bytes for validation

    photo_bytes = await download_photo(photo.file_id, message.bot)

    if not photo_bytes:
        await message.answer(_("Failed to download photo. Try again."))

        return

    # Validate photo

    is_valid, error = validate_photo(photo_bytes)

    if not is_valid:
        await message.answer(_("Invalid: {error}").format(error=error))

        return

    # Store photo

    storage_key = await save_photo(generate_storage_key(), photo_bytes)

    # Save to state

    photos.append(
        {
            "storage_key": storage_key,
            "telegram_file_id": photo.file_id,
            "position": len(photos),
        }
    )

    await state.update_data(photos=photos)

    await message.answer(
        _("Photo saved ({count}/5).\nSend more or 'done' to finish.").format(
            count=len(photos)
        )
    )
