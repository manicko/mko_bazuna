"""Tests for the global staging byte budget in ``process_photos`` (07-MEDIA-007).

The photos step refuses an upload when the total bytes held in
``MEDIA_ROOT/staging/`` reach ``settings.MEDIA_STAGING_BYTE_BUDGET``.  These
tests cover the budget boundary, the placement (a refused upload never writes
bytes), the bounded cost (no staging-tree walk on the upload path), the
``override_settings`` contract, FSM coherence, and the component interaction
between the check and the ``staging_bytes_used`` reading.

No database is required: the download, rate limit and save steps are stubbed,
and the byte reading only touches the filesystem.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.test import override_settings
from PIL import Image

# Keep in sync with the bot test conftest seller range (used only as an FSM
# payload value here — nothing is persisted, so the exact id is irrelevant).
_TEST_SELLER_ID = 900000100


def _real_jpeg_bytes() -> bytes:
    """Return a minimal decodable JPEG so the real save path is exercised."""
    import io

    image = Image.new("RGB", (10, 10), "red")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def _build_state(data: dict) -> MagicMock:
    """Build a mock FSMContext backed by the given state data."""
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data)
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    return state


def _build_photo_message(file_size: int = 1024) -> MagicMock:
    """Build a mock Telegram message carrying a single in-limit photo."""
    photo_item = MagicMock()
    photo_item.file_id = "test_file_id"
    photo_item.file_size = file_size
    message = MagicMock()
    message.text = None
    message.photo = [photo_item]
    message.answer = AsyncMock()
    message.bot = MagicMock()
    return message


def _write_staging_file(media_root, name: str, size: int) -> None:
    """Write a staging file of exactly *size* bytes under *media_root*."""
    staging_dir = media_root / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / name).write_bytes(b"x" * size)


# ---------------------------------------------------------------------------
# Budget boundary
# ---------------------------------------------------------------------------


class TestStagingBudgetBoundary:
    """Under-budget uploads pass; at/over-budget uploads are refused."""

    @pytest.mark.asyncio
    async def test_upload_below_budget_is_accepted(self, tmp_path) -> None:
        """A staging total below the budget lets the upload through."""
        from telegram_bot.handlers.ad_create import process_photos

        _write_staging_file(tmp_path, "existing.jpg", 10)

        state = _build_state({"photos": [], "user_id": _TEST_SELLER_ID})
        message = _build_photo_message()

        with (
            override_settings(
                MEDIA_ROOT=str(tmp_path),
                MEDIA_STAGING_BYTE_BUDGET=1024,
            ),
            patch(
                "telegram_bot.handlers.ad_create.photos.check_upload_rate_limit",
                AsyncMock(return_value=True),
            ),
            patch(
                "telegram_bot.handlers.ad_create.photos.download_photo",
                new=AsyncMock(return_value=_real_jpeg_bytes()),
            ),
        ):
            await process_photos(message, state)

        # The upload was saved and the FSM recorded the new photo.
        state.update_data.assert_awaited_once()
        answer_text = message.answer.await_args[0][0]
        assert "Photo saved" in answer_text

    @pytest.mark.asyncio
    async def test_upload_at_budget_is_refused(self, tmp_path) -> None:
        """A staging total equal to the budget refuses the upload, writes nothing."""
        from telegram_bot.handlers.ad_create import process_photos

        budget = 1024
        _write_staging_file(tmp_path, "existing.jpg", budget)

        state = _build_state({"photos": [], "user_id": _TEST_SELLER_ID})
        message = _build_photo_message()

        with (
            override_settings(
                MEDIA_ROOT=str(tmp_path),
                MEDIA_STAGING_BYTE_BUDGET=budget,
            ),
            patch(
                "telegram_bot.handlers.ad_create.photos.check_upload_rate_limit",
                AsyncMock(return_value=True),
            ),
            patch(
                "telegram_bot.handlers.ad_create.photos.download_photo",
                new=AsyncMock(return_value=_real_jpeg_bytes()),
            ),
            patch(
                "telegram_bot.handlers.ad_create.photos.save_photo",
                new=AsyncMock(),
            ) as mock_save,
        ):
            await process_photos(message, state)

        # Refused with the user-visible message; save_photo never ran.
        mock_save.assert_not_awaited()
        answer_text = message.answer.await_args[0][0]
        assert "temporarily full" in answer_text.lower()

    @pytest.mark.asyncio
    async def test_upload_over_budget_is_refused_and_writes_no_file(
        self, tmp_path
    ) -> None:
        """Over the budget the refusal precedes save_photo, so no bytes land."""
        from telegram_bot.handlers.ad_create import process_photos

        _write_staging_file(tmp_path, "existing.jpg", 4096)

        state = _build_state({"photos": [], "user_id": _TEST_SELLER_ID})
        message = _build_photo_message()

        with (
            override_settings(
                MEDIA_ROOT=str(tmp_path),
                MEDIA_STAGING_BYTE_BUDGET=1024,
            ),
            patch(
                "telegram_bot.handlers.ad_create.photos.check_upload_rate_limit",
                AsyncMock(return_value=True),
            ),
            patch(
                "telegram_bot.handlers.ad_create.photos.download_photo",
                new=AsyncMock(return_value=_real_jpeg_bytes()),
            ),
            patch(
                "telegram_bot.handlers.ad_create.photos.save_photo",
                new=AsyncMock(),
            ) as mock_save,
        ):
            await process_photos(message, state)

        mock_save.assert_not_awaited()
        # Only the pre-existing file is in staging: no new bytes were written.
        staged = sorted((tmp_path / "staging").iterdir())
        assert [p.name for p in staged] == ["existing.jpg"]

    @pytest.mark.asyncio
    async def test_budget_is_not_hard_coded(self, tmp_path) -> None:
        """The refusal is driven by ``MEDIA_STAGING_BYTE_BUDGET``, not a literal.

        Staging holds only 20 bytes — far below the 2 GiB default — so a
        hard-coded limit would let the upload through.  Overriding the setting
        to 1 byte must flip the decision to a refusal, proving the check reads
        the configured budget.
        """
        from telegram_bot.handlers.ad_create import process_photos

        _write_staging_file(tmp_path, "existing.jpg", 20)

        state = _build_state({"photos": [], "user_id": _TEST_SELLER_ID})
        message = _build_photo_message()

        with (
            override_settings(
                MEDIA_ROOT=str(tmp_path),
                MEDIA_STAGING_BYTE_BUDGET=1,
            ),
            patch(
                "telegram_bot.handlers.ad_create.photos.check_upload_rate_limit",
                AsyncMock(return_value=True),
            ),
            patch(
                "telegram_bot.handlers.ad_create.photos.download_photo",
                new=AsyncMock(return_value=_real_jpeg_bytes()),
            ),
            patch(
                "telegram_bot.handlers.ad_create.photos.save_photo",
                new=AsyncMock(),
            ) as mock_save,
        ):
            await process_photos(message, state)

        mock_save.assert_not_awaited()
        answer_text = message.answer.await_args[0][0]
        assert "temporarily full" in answer_text.lower()


# ---------------------------------------------------------------------------
# Bounded cost
# ---------------------------------------------------------------------------


class TestStagingBudgetIsBounded:
    """The per-upload check must not walk the staging tree."""

    @pytest.mark.asyncio
    async def test_check_does_not_walk_the_staging_tree(self, tmp_path) -> None:
        """``os.walk`` is never invoked on the upload path (bounded control)."""
        from telegram_bot.handlers.ad_create import process_photos

        _write_staging_file(tmp_path, "existing.jpg", 10)

        state = _build_state({"photos": [], "user_id": _TEST_SELLER_ID})
        message = _build_photo_message()

        with (
            override_settings(
                MEDIA_ROOT=str(tmp_path),
                MEDIA_STAGING_BYTE_BUDGET=1024,
            ),
            patch(
                "telegram_bot.handlers.ad_create.photos.check_upload_rate_limit",
                AsyncMock(return_value=True),
            ),
            patch(
                "telegram_bot.handlers.ad_create.photos.download_photo",
                new=AsyncMock(return_value=_real_jpeg_bytes()),
            ),
            patch("os.walk", side_effect=AssertionError("os.walk must not run")),
        ):
            await process_photos(message, state)

        # Reaching here means os.walk was never called (it would have raised).
        state.update_data.assert_awaited_once()

    def test_reader_scans_only_the_top_level(self, tmp_path) -> None:
        """``staging_bytes_used`` uses a single top-level ``os.scandir``."""
        from telegram_bot.services.ad_data.media import staging_bytes_used

        _write_staging_file(tmp_path, "a.jpg", 100)
        _write_staging_file(tmp_path, "b.jpg", 250)
        # A nested subdirectory must be ignored by the top-level scan.
        nested = tmp_path / "staging" / "deep"
        nested.mkdir()
        (nested / "c.jpg").write_bytes(b"x" * 9999)

        scandir_calls: list[str] = []
        real_scandir = os.scandir

        def _recording_scandir(path):
            scandir_calls.append(str(path))
            return real_scandir(path)

        with (
            override_settings(MEDIA_ROOT=str(tmp_path)),
            patch("os.scandir", side_effect=_recording_scandir),
        ):
            total = staging_bytes_used()

        assert total == 350
        assert scandir_calls == [str(tmp_path / "staging")]

    def test_missing_staging_dir_reads_zero(self, tmp_path) -> None:
        """An absent staging directory (nothing in flight) reads as zero."""
        from telegram_bot.services.ad_data.media import staging_bytes_used

        with override_settings(MEDIA_ROOT=str(tmp_path)):
            assert staging_bytes_used() == 0


# ---------------------------------------------------------------------------
# FSM coherence on refusal
# ---------------------------------------------------------------------------


class TestStagingBudgetFsmCoherence:
    """A refused upload must not consume a photo slot or touch state."""

    @pytest.mark.asyncio
    async def test_refused_upload_leaves_fsm_untouched(self, tmp_path) -> None:
        """Refusal returns before ``state.update_data``; no slot is consumed."""
        from telegram_bot.handlers.ad_create import process_photos

        _write_staging_file(tmp_path, "existing.jpg", 4096)

        state = _build_state({"photos": [], "user_id": _TEST_SELLER_ID})
        message = _build_photo_message()

        with (
            override_settings(
                MEDIA_ROOT=str(tmp_path),
                MEDIA_STAGING_BYTE_BUDGET=1024,
            ),
            patch(
                "telegram_bot.handlers.ad_create.photos.check_upload_rate_limit",
                AsyncMock(return_value=True),
            ),
            patch(
                "telegram_bot.handlers.ad_create.photos.download_photo",
                new=AsyncMock(return_value=_real_jpeg_bytes()),
            ),
            patch(
                "telegram_bot.handlers.ad_create.photos.save_photo",
                new=AsyncMock(),
            ),
        ):
            await process_photos(message, state)

        # The FSM photo list is never rewritten, so the slot count is unchanged.
        state.update_data.assert_not_awaited()


# ---------------------------------------------------------------------------
# Component interaction: the consumed reading is the bounded scan
# ---------------------------------------------------------------------------


class TestStagingBudgetReadingSource:
    """The check consumes the ``staging_bytes_used`` figure, not its own scan."""

    @pytest.mark.asyncio
    async def test_check_consumes_staging_bytes_used(self, tmp_path) -> None:
        """The decision is driven by the value ``staging_bytes_used`` returns."""
        from telegram_bot.handlers.ad_create import process_photos

        state = _build_state({"photos": [], "user_id": _TEST_SELLER_ID})
        message = _build_photo_message()

        # Force the reading over budget even though staging is empty; if the
        # handler re-derived the total itself, it would let this through.
        with (
            override_settings(
                MEDIA_ROOT=str(tmp_path),
                MEDIA_STAGING_BYTE_BUDGET=1024,
            ),
            patch(
                "telegram_bot.handlers.ad_create.photos.staging_bytes_used",
                return_value=99999,
            ) as mock_reading,
            patch(
                "telegram_bot.handlers.ad_create.photos.check_upload_rate_limit",
                AsyncMock(return_value=True),
            ),
            patch(
                "telegram_bot.handlers.ad_create.photos.download_photo",
                new=AsyncMock(return_value=_real_jpeg_bytes()),
            ),
            patch(
                "telegram_bot.handlers.ad_create.photos.save_photo",
                new=AsyncMock(),
            ) as mock_save,
        ):
            await process_photos(message, state)

        mock_reading.assert_called_once()
        mock_save.assert_not_awaited()
