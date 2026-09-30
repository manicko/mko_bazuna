"""Focused tests for the draft idle-timeout heartbeat (03-DB-003).

These pin the *mechanism* (one test per mechanism, not per handler — the
structural coverage of every handler is the job of
``test_ad_create_heartbeat_coverage.py``):

- the heartbeat helper is called on entry of a dialog handler;
- ``touch_draft`` is a 0-row no-op for a non-``DRAFT`` row, which is the second,
  independent guarantee that it can never resurrect or revert a published ad;
- a lock timeout (SQLSTATE 55P03) is swallowed, and any other
  ``OperationalError`` propagates;
- ``touch_staging_photos`` refreshes the mtime of a ``staging/`` file and
  tolerates a missing one.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import psycopg
import pytest
from django.db import OperationalError

from apps.core.enums import AdStatus
from apps.media.services.filesystem import STAGING_PREFIX
from conftest import create_test_ad

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
    pytest.mark.concurrent,
    pytest.mark.xdist_group("bot_concurrent"),
]


def _lock_timeout_error() -> OperationalError:
    """Build an ``OperationalError`` shaped like a real lock timeout (55P03)."""
    exc = OperationalError("canceling statement due to lock timeout")
    exc.__cause__ = psycopg.errors.LockNotAvailable(
        "canceling statement due to lock timeout"
    )
    return exc


def _build_state(data: dict) -> MagicMock:
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data)
    state.clear = AsyncMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    return state


# ---------------------------------------------------------------------------
# The heartbeat fires on dialog-handler entry
# ---------------------------------------------------------------------------


class TestHeartbeatFiresOnEntry:
    """A dialog handler's entry calls ``touch_draft`` with the FSM's ``ad_id``."""

    @pytest.mark.asyncio
    async def test_city_handler_touches_the_draft(self) -> None:
        """``process_city`` heartbeats with the ad id from the FSM state."""
        from telegram_bot.handlers.ad_create.city import process_city

        state = _build_state({"ad_id": 4242})
        message = MagicMock()
        message.text = "Podgorica"
        message.answer = AsyncMock()

        with (
            patch(
                "telegram_bot.handlers.ad_create.city.touch_draft",
                new=AsyncMock(),
            ) as mock_touch,
            patch(
                "telegram_bot.handlers.ad_create.city.get_city_by_name",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "telegram_bot.handlers.ad_create.city.get_all_cities",
                new=AsyncMock(return_value=[]),
            ),
        ):
            await process_city(message, state)

        mock_touch.assert_awaited_once_with(4242)

    @pytest.mark.asyncio
    async def test_no_ad_id_skips_the_heartbeat(self) -> None:
        """A dialog state with no ``ad_id`` does not heartbeat."""
        from telegram_bot.handlers.ad_create.text import process_title

        state = _build_state({"title": "x"})
        message = MagicMock()
        message.text = "A valid enough title"
        message.answer = AsyncMock()

        with patch(
            "telegram_bot.handlers.ad_create.text.touch_draft",
            new=AsyncMock(),
        ) as mock_touch:
            await process_title(message, state)

        mock_touch.assert_not_awaited()


# ---------------------------------------------------------------------------
# The status=DRAFT guard: a 0-row no-op for a non-DRAFT row
# ---------------------------------------------------------------------------


class TestHeartbeatStatusGuard:
    """``touch_draft`` updates only ``DRAFT`` rows — it can never touch a publish."""

    def test_published_ad_is_untouched(self, seller, category, city) -> None:
        """A PUBLISHED row's ``updated_at`` is not moved by the heartbeat."""
        from telegram_bot.services.ad_data.orm import touch_draft

        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        before = ad.updated_at

        asyncio.run(touch_draft(ad.id))

        ad.refresh_from_db()
        assert ad.updated_at == before
        assert ad.status == AdStatus.PUBLISHED

    def test_draft_ad_is_refreshed(self, seller, category, city) -> None:
        """A DRAFT row's ``updated_at`` is moved by the heartbeat."""
        from telegram_bot.services.ad_data.orm import touch_draft

        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
        before = ad.updated_at

        asyncio.run(touch_draft(ad.id))

        ad.refresh_from_db()
        assert ad.updated_at > before


# ---------------------------------------------------------------------------
# Fail-soft on a lock timeout
# ---------------------------------------------------------------------------


class TestHeartbeatFailSoft:
    """A transient lock timeout must never cost the seller their step."""

    def test_lock_timeout_is_swallowed(self) -> None:
        """SQLSTATE 55P03 is caught and logged, not raised."""
        from telegram_bot.services.ad_data import orm

        with patch.object(
            orm.Ad.objects,
            "filter",
            side_effect=_lock_timeout_error(),
        ):
            # Must not raise.
            asyncio.run(orm.touch_draft(1))

    def test_other_operational_error_propagates(self) -> None:
        """A non-lock ``OperationalError`` is re-raised."""
        from telegram_bot.services.ad_data import orm

        with patch.object(
            orm.Ad.objects,
            "filter",
            side_effect=OperationalError("connection refused"),
        ):
            with pytest.raises(OperationalError, match="connection refused"):
                asyncio.run(orm.touch_draft(1))


# ---------------------------------------------------------------------------
# The staging-file touch
# ---------------------------------------------------------------------------


class TestTouchStagingPhotos:
    """``touch_staging_photos`` refreshes staging/ mtimes and tolerates absence."""

    @pytest.mark.asyncio
    async def test_refreshes_mtime_and_skips_non_staging(self) -> None:
        """A staging/ file's mtime is refreshed; a permanent key is skipped."""
        from django.test import override_settings

        from telegram_bot.services.ad_data.media import touch_staging_photos

        with tempfile.TemporaryDirectory() as tmpdir:
            staging_key = f"{STAGING_PREFIX}abc.jpg"
            staging_path = Path(tmpdir) / staging_key
            staging_path.parent.mkdir(parents=True)
            staging_path.write_bytes(b"staging")

            # Back-date the mtime so the refresh is observable.
            old = os.path.getmtime(staging_path) - 3600
            os.utime(staging_path, (old, old))

            with override_settings(MEDIA_ROOT=tmpdir):
                await touch_staging_photos(
                    [
                        {"storage_key": staging_key},
                        {"storage_key": "permanent.jpg"},
                    ]
                )

            assert os.path.getmtime(staging_path) > old

    @pytest.mark.asyncio
    async def test_missing_file_is_tolerated(self) -> None:
        """A staging key whose file is already gone does not raise."""
        from django.test import override_settings

        from telegram_bot.services.ad_data.media import touch_staging_photos

        with tempfile.TemporaryDirectory() as tmpdir:
            with override_settings(MEDIA_ROOT=tmpdir):
                # Must not raise.
                await touch_staging_photos([{"storage_key": f"{STAGING_PREFIX}gone.jpg"}])
