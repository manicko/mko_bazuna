"""
Tests for process_preview — original_language detection from Telegram user locale.

Verifies that the ad's ``original_language`` is derived from
``message.from_user.language_code`` via ``LanguageLocale.from_code``, with a
fallback to ``BOSNIAN`` when the code is missing or unsupported.

The full ``process_preview`` → ``submit_ad`` → ``auto_moderate``
pipeline is exercised against the real PostgreSQL ORM.  ``translate_all_languages``
is mocked to avoid hitting the Google Translate API.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async

from apps.users.models import User

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
    pytest.mark.concurrent,
]
pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))

# Telegram user_id for mock-only (non-DB) photo pipeline tests.
# References the bot-conftest seller ID range (900000100), not the
# root-conftest range (900000001).
_TEST_SELLER_ID = 900000100


@pytest.fixture
def seller_id(seller: User) -> int:
    """Return the ID of the shared bot-conftest seller fixture (telegram_id 900000100)."""
    return seller.id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_message(language_code: str | None) -> MagicMock:
    """Build a mock Telegram message for the preview/confirm step."""
    user_mock = MagicMock()
    user_mock.language_code = language_code
    message = MagicMock()
    message.text = "confirm"
    message.from_user = user_mock
    message.answer = AsyncMock()
    return message


def _build_state(data: dict) -> MagicMock:
    """Build a mock FSMContext backed by the given state data."""
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data)
    state.clear = AsyncMock()
    return state


async def _mock_translate(text: str, target_locales: list[str]) -> dict[str, str]:
    """Return deterministic translations without hitting the real API."""
    return {loc: f"{text}-{loc}" for loc in target_locales}


def _build_photo_message(file_size: int | None = 1024) -> MagicMock:
    """Build a mock Telegram message containing a single photo upload.

    Args:
        file_size: The ``PhotoSize.file_size`` value to set on the mock photo.
            Defaults to 1024 (within the 2 MB limit) so existing tests proceed
            past the pre-check. Pass ``None`` to simulate Telegram omitting
            the field, or an int above the limit to trigger rejection.
    """
    photo_item = MagicMock()
    photo_item.file_id = "test_file_id"
    photo_item.file_size = file_size
    message = MagicMock()
    message.text = None
    message.photo = [photo_item]
    message.answer = AsyncMock()
    message.bot = MagicMock()
    return message


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProcessPreviewLanguageDetection:
    """Tests for original_language detection in process_preview."""

    @pytest.mark.asyncio
    async def test_original_language_detected_from_user(
        self, seller_id: int, permissive_criteria: None
    ) -> None:
        """Ad original_language is set from the Telegram user's language_code."""
        from telegram_bot.handlers.ad_create import process_preview
        from telegram_bot.services.ad_data import create_draft_ad

        ad = await create_draft_ad(user_id=seller_id)

        state = _build_state(
            {
                "ad_id": ad.id,
                "title": "Valid Title",
                "description": "Valid description text for the ad.",
                "price_amount": 100,
                "price_currency": "EUR",
                "photos": [],
                "user_id": seller_id,
            }
        )

        message = _build_message("en-US")

        with patch(
            "telegram_bot.handlers.ad_create.submit.translate_all_languages",
            _mock_translate,
        ):
            await process_preview(message, state)

        from apps.ads.models import Ad

        saved = await sync_to_async(Ad.objects.get)(id=ad.id)
        assert saved.original_language == "en"

    @pytest.mark.asyncio
    async def test_original_language_falls_back_to_bosnian(
        self, seller_id: int, permissive_criteria: None
    ) -> None:
        """Ad original_language falls back to BOSNIAN when language_code is None."""
        from telegram_bot.handlers.ad_create import process_preview
        from telegram_bot.services.ad_data import create_draft_ad

        ad = await create_draft_ad(user_id=seller_id)

        state = _build_state(
            {
                "ad_id": ad.id,
                "title": "Valid Title",
                "description": "Valid description text for the ad.",
                "price_amount": 100,
                "price_currency": "EUR",
                "photos": [],
                "user_id": seller_id,
            }
        )

        message = _build_message(None)

        with patch(
            "telegram_bot.handlers.ad_create.submit.translate_all_languages",
            _mock_translate,
        ):
            await process_preview(message, state)

        from apps.ads.models import Ad

        saved = await sync_to_async(Ad.objects.get)(id=ad.id)
        assert saved.original_language == "bs"


class TestProcessPhotos:
    """Tests for process_photos — upload cap, rate limit, and done handling."""

    @pytest.mark.asyncio
    async def test_process_photos_rejects_after_five(self) -> None:
        """5 photos already in state — a new photo upload is rejected with the cap message."""
        from telegram_bot.handlers.ad_create import process_photos

        state = _build_state(
            {"photos": [{}, {}, {}, {}, {}], "user_id": _TEST_SELLER_ID}
        )
        message = _build_photo_message()

        with patch("telegram_bot.handlers.ad_create.photos.download_photo") as mock_download:
            await process_photos(message, state)

        mock_download.assert_not_called()
        message.answer.assert_awaited_once()
        answer_text = message.answer.await_args[0][0]
        assert "at most 5" in answer_text

    @pytest.mark.asyncio
    async def test_done_with_zero_photos_shows_correct_message(self) -> None:
        """'done' with 0 photos shows 'at least 1', not 'at most 5'."""
        from telegram_bot.handlers.ad_create import process_photos

        state = _build_state({"photos": [], "user_id": _TEST_SELLER_ID})
        message = _build_message(None)
        message.text = "done"

        await process_photos(message, state)

        message.answer.assert_awaited_once()
        answer_text = message.answer.await_args[0][0]
        assert "at least 1" in answer_text
        assert "at most 5" not in answer_text

    @pytest.mark.asyncio
    async def test_done_with_six_photos_shows_correct_message(self) -> None:
        """'done' with 6 photos shows 'at most 5', not 'at least 1'."""
        from telegram_bot.handlers.ad_create import process_photos

        state = _build_state({"photos": [{}] * 6, "user_id": _TEST_SELLER_ID})
        message = _build_message(None)
        message.text = "done"

        await process_photos(message, state)

        message.answer.assert_awaited_once()
        answer_text = message.answer.await_args[0][0]
        assert "at most 5" in answer_text
        assert "at least 1" not in answer_text

    @pytest.mark.asyncio
    async def test_process_photos_rate_limited(self, monkeypatch) -> None:
        """Rate-limited uploads are rejected before download_photo."""
        from telegram_bot.handlers.ad_create import process_photos

        monkeypatch.setattr(
            "telegram_bot.handlers.ad_create.photos.check_upload_rate_limit",
            AsyncMock(return_value=False),
        )

        state = _build_state({"photos": [], "user_id": _TEST_SELLER_ID})
        message = _build_photo_message()

        with patch("telegram_bot.handlers.ad_create.photos.download_photo") as mock_download:
            await process_photos(message, state)

        mock_download.assert_not_called()
        message.answer.assert_awaited_once()
        answer_text = message.answer.await_args[0][0]
        assert "too fast" in answer_text.lower()

    @pytest.mark.asyncio
    async def test_file_size_exceeds_limit_rejects_without_download(
        self, monkeypatch
    ) -> None:
        """PhotoSize with file_size > 2MB is rejected before download_photo is called."""
        from telegram_bot.handlers.ad_create import process_photos

        monkeypatch.setattr(
            "telegram_bot.handlers.ad_create.photos.check_upload_rate_limit",
            AsyncMock(return_value=True),
        )

        state = _build_state({"photos": [], "user_id": _TEST_SELLER_ID})
        message = _build_photo_message(file_size=3 * 1024 * 1024)

        with patch("telegram_bot.handlers.ad_create.photos.download_photo") as mock_download:
            await process_photos(message, state)

        mock_download.assert_not_called()
        message.answer.assert_awaited_once()
        answer_text = message.answer.await_args[0][0]
        assert "too large" in answer_text.lower()

    @pytest.mark.asyncio
    async def test_process_photos_integration_real_jpg(
        self, monkeypatch, tmp_path
    ) -> None:
        """Full download → validate → strip-EXIF save pipeline with a real JPEG.

        Stubs only the network-bound ``download_photo`` and the rate-limit
        check; the real ``validate_photo`` (PIL) and ``save_photo`` (strips
        EXIF, writes to ``MEDIA_ROOT/staging/``) run end-to-end and the saved
        file is re-opened with Pillow to confirm it remains a valid JPEG.
        """
        import io

        from django.test import override_settings
        from PIL import Image

        from telegram_bot.handlers.ad_create import process_photos

        # Build a minimal but real, decodable JPEG (50x50 red).
        image = Image.new("RGB", (50, 50), "red")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=95)
        jpeg_bytes = buffer.getvalue()

        monkeypatch.setattr(
            "telegram_bot.handlers.ad_create.photos.check_upload_rate_limit",
            AsyncMock(return_value=True),
        )

        state = _build_state({"photos": [], "user_id": _TEST_SELLER_ID})
        state.update_data = AsyncMock()
        message = _build_photo_message(file_size=1024)

        with (
            override_settings(MEDIA_ROOT=str(tmp_path)),
            patch(
                "telegram_bot.handlers.ad_create.photos.download_photo",
                new=AsyncMock(return_value=jpeg_bytes),
            ),
        ):
            await process_photos(message, state)

        # Bot responded with the "Photo saved" confirmation.
        message.answer.assert_awaited_once()
        answer_text = message.answer.await_args[0][0]
        assert "Photo saved" in answer_text

        # state.update_data received a photos list with a staging storage key.
        state.update_data.assert_awaited_once()
        saved_photos = state.update_data.await_args.kwargs["photos"]
        assert isinstance(saved_photos, list)
        assert len(saved_photos) == 1
        storage_key = saved_photos[0]["storage_key"]
        assert isinstance(storage_key, str)
        assert storage_key.startswith("staging/")
        assert storage_key.endswith(".jpg")

        # The stripped file was actually written to the staging directory.
        saved_path = tmp_path / storage_key
        assert saved_path.exists()

        # The persisted file is a valid, re-decodable JPEG.
        with Image.open(saved_path) as reopened:
            assert reopened.format == "JPEG"
            reopened.load()


# ---------------------------------------------------------------------------
# Helpers for CR-001 / MED-001 regression tests (cancel-after-submit,
# delete_draft storage_keys)
# ---------------------------------------------------------------------------


def _make_test_image() -> bytes:
    """Create a minimal valid 800x600 RGB JPEG for thumbnail generation."""
    import io

    from PIL import Image

    image = Image.new("RGB", (800, 600), color=(64, 128, 192))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    buffer.seek(0)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# CR-001: Cancel after submit must not destroy ad media
# ---------------------------------------------------------------------------


class TestCancelAfterSubmit:
    """Tests for CR-001: /cancel after submit must protect submitted ad media.

    After ``submit_ad`` transitions a DRAFT ad to PUBLISHED, the FSM
    ``photos`` list is stale — photos have been promoted to AdImage rows.
    ``cmd_cancel`` must detect the non-DRAFT status via ``_get_ad_status``
    and skip both ``delete_photo`` and ``delete_draft``, so that media
    belonging to a submitted ad is never destroyed.
    """

    @pytest.mark.asyncio
    async def test_cancel_after_submit_preserves_files(
        self, seller_id: int, permissive_criteria: None, tmp_path
    ) -> None:
        """After submit to PUBLISHED, /cancel leaves files + AdImage rows intact."""
        from decimal import Decimal
        from pathlib import Path

        from django.test import override_settings

        from apps.ads.models import AdImage
        from apps.ads.services.submission import SubmitAdInput, submit_ad
        from apps.core.enums import AdStatus
        from apps.currencies.enums import CurrencyCode
        from apps.media.services.filesystem import generate_storage_key
        from telegram_bot.handlers.ad_create import cmd_cancel
        from telegram_bot.services.ad_data import create_draft_ad

        media_root = Path(str(tmp_path))

        with override_settings(MEDIA_ROOT=str(tmp_path)):
            # Create a DRAFT ad
            ad = await create_draft_ad(user_id=seller_id)

            # Write a real image so submit_ad can generate thumbnails
            storage_key = generate_storage_key()
            (media_root / storage_key).write_bytes(_make_test_image())

            photo = {
                "storage_key": storage_key,
                "telegram_file_id": "test_file_id",
                "position": 0,
            }

            # Submit — DRAFT -> ON_MODERATION -> PUBLISHED
            is_valid, errors = await sync_to_async(submit_ad)(
                SubmitAdInput(
                    ad_id=ad.id,
                    title_ru="Test Ad",
                    desc_ru="A valid test description for the ad.",
                    category_id=None,
                    city_id=None,
                    price_amount=Decimal("100"),
                    price_currency=CurrencyCode.EUR,
                    photos=[photo],
                    user_id=seller_id,
                    original_language="en",
                )
            )
            assert is_valid, f"submit_ad should pass moderation: {errors}"

            await sync_to_async(ad.refresh_from_db)()
            assert ad.status == AdStatus.PUBLISHED

            # AdImage + physical thumbnail files exist on disk
            ad_image = await sync_to_async(AdImage.objects.get)(ad=ad)
            for key in ad_image.storage_keys():
                assert (media_root / key).is_file(), f"File missing after submit: {key}"

            # Call /cancel — ad is PUBLISHED, cleanup must be skipped
            cancel_msg = MagicMock()
            cancel_msg.answer = AsyncMock()
            cancel_state = _build_state({"ad_id": ad.id})

            await cmd_cancel(cancel_msg, cancel_state)

            # AdImage row still exists (not deleted by cancel)
            assert (
                await sync_to_async(lambda: AdImage.objects.filter(ad=ad).count())()
                == 1
            )
            await sync_to_async(ad_image.refresh_from_db)()

            # All physical files still present on disk
            for key in ad_image.storage_keys():
                assert (media_root / key).is_file(), f"File deleted after cancel: {key}"

            # User was informed
            cancel_msg.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancel_after_submit_logs_skip(
        self,
        seller_id: int,
        permissive_criteria: None,
        tmp_path,
        caplog,
    ) -> None:
        """Non-DRAFT ad: cmd_cancel skips delete_photo and logs the skip."""
        import logging
        from decimal import Decimal
        from pathlib import Path

        from django.test import override_settings

        from apps.ads.services.submission import SubmitAdInput, submit_ad
        from apps.core.enums import AdStatus
        from apps.currencies.enums import CurrencyCode
        from apps.media.services.filesystem import generate_storage_key
        from telegram_bot.handlers.ad_create import cmd_cancel
        from telegram_bot.services.ad_data import create_draft_ad

        media_root = Path(str(tmp_path))

        with override_settings(MEDIA_ROOT=str(tmp_path)):
            ad = await create_draft_ad(user_id=seller_id)

            storage_key = generate_storage_key()
            (media_root / storage_key).write_bytes(_make_test_image())

            photo = {
                "storage_key": storage_key,
                "telegram_file_id": "test_file_id",
                "position": 0,
            }

            # Submit -> PUBLISHED
            is_valid, _ = await sync_to_async(submit_ad)(
                SubmitAdInput(
                    ad_id=ad.id,
                    title_ru="Test Ad",
                    desc_ru="A valid test description for the ad.",
                    category_id=None,
                    city_id=None,
                    price_amount=Decimal("100"),
                    price_currency=CurrencyCode.EUR,
                    photos=[photo],
                    user_id=seller_id,
                    original_language="en",
                )
            )
            assert is_valid

            await sync_to_async(ad.refresh_from_db)()
            assert ad.status != AdStatus.DRAFT

            # Patch delete_photo — it must NOT be called for a non-DRAFT ad
            with patch("telegram_bot.handlers.ad_create.entry.delete_photo") as mock_delete:
                caplog.set_level(
                    logging.INFO,
                    logger="telegram_bot.handlers.ad_create",
                )
                cancel_msg = MagicMock()
                cancel_msg.answer = AsyncMock()
                cancel_state = _build_state({"ad_id": ad.id})

                await cmd_cancel(cancel_msg, cancel_state)

            mock_delete.assert_not_called()
            cancel_msg.answer.assert_awaited_once()

            # Non-DRAFT path logs the skip
            assert "Cancel skipped" in caplog.text

    @pytest.mark.asyncio
    async def test_cancel_draft_deletes_staging_key(
        self, seller_id: int, tmp_path
    ) -> None:
        """cmd_cancel on a DRAFT ad deletes staging files from FSM state.

        When the seller aborts mid-flow, the staging keys stored in FSM state
        are deleted via ``delete_photo`` — which is path-agnostic and handles
        the ``staging/`` prefix.
        """
        from pathlib import Path

        from django.test import override_settings

        from apps.core.enums import AdStatus
        from apps.media.services.filesystem import STAGING_PREFIX
        from telegram_bot.handlers.ad_create import cmd_cancel
        from telegram_bot.services.ad_data import create_draft_ad

        media_root = Path(str(tmp_path))

        with override_settings(MEDIA_ROOT=str(tmp_path)):
            ad = await create_draft_ad(user_id=seller_id)
            assert ad.status == AdStatus.DRAFT

            # Create a staging file as if save_photo had written it
            staging_file = media_root / STAGING_PREFIX / "test-photo.jpg"
            staging_file.parent.mkdir(parents=True, exist_ok=True)
            staging_file.write_bytes(b"staging data")

            # FSM state with a staging key (as process_photos would store)
            cancel_state = _build_state(
                {
                    "ad_id": ad.id,
                    "photos": [
                        {
                            "storage_key": f"{STAGING_PREFIX}test-photo.jpg",
                            "telegram_file_id": "test_file_id",
                            "position": 0,
                        }
                    ],
                }
            )

            cancel_msg = MagicMock()
            cancel_msg.answer = AsyncMock()

            await cmd_cancel(cancel_msg, cancel_state)

            # Staging file was deleted by delete_photo
            assert not staging_file.exists(), (
                "staging file was not deleted by cmd_cancel"
            )

            # Ad was deleted from DB (delete_draft ran)
            from apps.ads.models import Ad

            assert not await sync_to_async(
                lambda: Ad.objects.filter(id=ad.id).exists()
            )()


# ---------------------------------------------------------------------------
# MED-001: delete_draft must clean up all storage_keys (image + thumbnails)
# ---------------------------------------------------------------------------


class TestDeleteDraftStorageKeys:
    """Tests for MED-001: delete_draft deletes all storage_keys.

    ``AdImage.storage_keys()`` returns the original image key plus all
    non-empty thumbnail keys (small, medium, large).  ``delete_draft``
    must call ``delete_photo`` for every key, not just ``img.image``.
    """

    @pytest.mark.asyncio
    async def test_delete_draft_uses_storage_keys(
        self, seller_id: int, tmp_path
    ) -> None:
        """delete_draft calls delete_photo for all storage_keys (img + 3 thumbs)."""

        from django.test import override_settings

        from apps.ads.models import Ad, AdImage
        from apps.media.services.filesystem import generate_storage_key
        from telegram_bot.services.ad_data import create_draft_ad, delete_draft

        ad = await create_draft_ad(user_id=seller_id)

        image_key = generate_storage_key()
        stem = image_key.rsplit(".jpg", 1)[0]
        thumb_small = f"{stem}-small.jpg"
        thumb_medium = f"{stem}-medium.jpg"
        thumb_large = f"{stem}-large.jpg"
        all_keys = [image_key, thumb_small, thumb_medium, thumb_large]

        # Create AdImage with all thumbnail fields populated
        with override_settings(MEDIA_ROOT=str(tmp_path)):
            await sync_to_async(AdImage.objects.create)(
                ad=ad,
                image=image_key,
                thumbnail_small=thumb_small,
                thumbnail_medium=thumb_medium,
                thumbnail_large=thumb_large,
            )

        # Patch delete_photo to spy on calls (avoid real filesystem deletion)
        with patch("telegram_bot.services.ad_data.delete_photo") as mock_delete:
            await delete_draft(ad.id)

        # delete_photo must be called for ALL 4 keys, not just img.image
        called_keys = [call.args[0] for call in mock_delete.call_args_list]
        assert len(called_keys) == 4
        assert sorted(called_keys) == sorted(all_keys)

        # Ad should be deleted from the database
        assert not await sync_to_async(lambda: Ad.objects.filter(id=ad.id).exists())()


class TestDeleteDraftCrashRecovery:
    """Crash-recovery test for delete_draft's transaction.atomic() boundary (DB-001).

    When ad.delete() raises inside transaction.atomic(), the DB row survives
    the rollback and the AdImage storage-key files are NOT deleted (post-commit
    FS deletion is skipped).
    """

    @pytest.mark.asyncio
    async def test_delete_draft_files_preserved_on_db_rollback(
        self, seller_id: int, tmp_path
    ) -> None:
        """When ad.delete() raises inside transaction.atomic(), the Ad row
        survives and physical image files are preserved."""
        from django.test import override_settings

        from apps.ads.models import Ad, AdImage
        from apps.media.services.filesystem import generate_storage_key
        from telegram_bot.services.ad_data import create_draft_ad, delete_draft

        with override_settings(MEDIA_ROOT=str(tmp_path)):
            ad = await create_draft_ad(user_id=seller_id)

            image_key = generate_storage_key()
            stem = image_key.rsplit(".jpg", 1)[0]
            thumb_small = f"{stem}-small.jpg"
            thumb_medium = f"{stem}-medium.jpg"
            thumb_large = f"{stem}-large.jpg"
            all_keys = [image_key, thumb_small, thumb_medium, thumb_large]

            await sync_to_async(AdImage.objects.create)(
                ad=ad,
                image=image_key,
                thumbnail_small=thumb_small,
                thumbnail_medium=thumb_medium,
                thumbnail_large=thumb_large,
            )

            # Create real files on disk
            for key in all_keys:
                file_path = tmp_path / key
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_bytes(b"fake image data")

            # Patch Ad.delete to raise — simulates crash inside transaction.atomic()
            with patch(
                "apps.ads.models.Ad.delete",
                side_effect=RuntimeError("simulated crash"),
            ):
                # Patch delete_photo to prevent real deletion and track calls
                with patch("telegram_bot.services.ad_data.delete_photo") as mock_delete:
                    with pytest.raises(RuntimeError, match="simulated crash"):
                        await delete_draft(ad.id)

            # DB row survived the rollback
            exists = await sync_to_async(Ad.objects.filter(id=ad.id).exists)()
            assert exists, "Ad row should survive transaction rollback"

            # delete_photo was NOT called — FS deletion only happens post-commit
            assert mock_delete.call_count == 0, (
                "delete_photo should not be called when ad.delete() raises "
                "inside transaction.atomic()"
            )

            # Physical files are still on disk (delete_photo was not called)
            for key in all_keys:
                assert (tmp_path / key).exists(), (
                    f"File {key} should still exist on disk"
                )
