"""
Integration test for the ``update_ad_and_moderate`` thumbnail pipeline (G-07).

The bot's ad-finalisation path (``telegram_bot/handlers/ad_create.py``) reads
the uploaded photo from ``MEDIA_ROOT``, runs it through
``ThumbnailService.generate_thumbnails``, and stores the returned storage keys
on the ``AdImage`` row (``thumbnail_small`` / ``thumbnail_medium`` /
``thumbnail_large``).  On any generation error the handler sets all three
fields to ``None`` (the ``except Exception`` branch at lines 728-735).

These tests exercise the **real** ``ThumbnailService`` (Pillow) against a small
in-memory JPEG, mocking only ``auto_moderate`` so the ad is not flagged for
content and so the assertions are deterministic.  ``MEDIA_ROOT`` is overridden
to a per-test ``tmp_path`` so file I/O is isolated.

Lives under ``telegram_bot/tests/`` so it picks up that package's conftest
(async ``user`` fixture, ``sync_to_async`` worker-connection cleanup, and the
``django_db(transaction=True)`` marker required for cross-thread DB access).
"""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from django.test import override_settings
from PIL import Image

from apps.categories.models import Category
from apps.locations.models import City


pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.slow,
    pytest.mark.integration,
    pytest.mark.concurrent,
]


def _make_test_image(width: int = 800, height: int = 600) -> bytes:
    """Return minimal JPEG bytes decodable by Pillow."""
    image = Image.new("RGB", (width, height), color=(64, 128, 192))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    buffer.seek(0)
    return buffer.getvalue()


async def _make_category() -> Category:
    return await sync_to_async(Category.objects.create)(
        name="photo-test", slug="photo-test-ct"
    )


async def _make_city() -> City:
    return await sync_to_async(City.objects.create)(
        country_code="ME", name="PhotoCt", region="R", slug="photo-ct"
    )


class TestSavePhotoThumbnailsIntegration:
    """``generate_thumbnails`` results flow through to ``AdImage.thumbnail_*``."""

    @pytest.mark.asyncio
    async def test_thumbnails_populated_on_success(self, user, tmp_path) -> None:
        """Successful generation populates all three ``thumbnail_*`` fields."""
        from apps.ads.models import AdImage
        from telegram_bot.handlers.ad_create import (
            create_draft_ad,
            update_ad_and_moderate,
        )

        category = await _make_category()
        city = await _make_city()
        ad = await create_draft_ad(user_id=user.id)

        # Real, decodable JPEG at MEDIA_ROOT/<storage_key> (read by the handler).
        photo_bytes = _make_test_image(800, 600)
        storage_key = "photo.jpg"
        (tmp_path / storage_key).write_bytes(photo_bytes)

        photos = [
            {"storage_key": storage_key, "telegram_file_id": "AgADBQ", "position": 0}
        ]

        with (
            override_settings(MEDIA_ROOT=str(tmp_path)),
            patch(
                "apps.moderation.services.auto_moderation.auto_moderate",
                return_value=True,
            ),
        ):
            passed, errors = await update_ad_and_moderate(
                ad_id=ad.id,
                title_ru="Title",
                desc_ru="Description",
                category_id=category.id,
                city_id=city.id,
                price=100,
                photos=photos,
                user_id=user.id,
            )

        assert passed is True
        assert errors == []

        ad_image = await sync_to_async(AdImage.objects.get)(ad=ad)
        assert ad_image.thumbnail_small == "photo-small.jpg"
        assert ad_image.thumbnail_medium == "photo-medium.jpg"
        assert ad_image.thumbnail_large == "photo-large.jpg"

    @pytest.mark.asyncio
    async def test_thumbnails_null_on_generation_failure(self, user, tmp_path) -> None:
        """When ``generate_thumbnails`` raises, all three ``thumbnail_*`` stay null."""
        from apps.ads.models import AdImage
        from telegram_bot.handlers.ad_create import (
            create_draft_ad,
            update_ad_and_moderate,
        )

        category = await _make_category()
        city = await _make_city()
        ad = await create_draft_ad(user_id=user.id)

        photo_bytes = _make_test_image(800, 600)
        storage_key = "photo.jpg"
        (tmp_path / storage_key).write_bytes(photo_bytes)
        photos = [
            {"storage_key": storage_key, "telegram_file_id": "AgADBQ", "position": 0}
        ]

        with (
            override_settings(MEDIA_ROOT=str(tmp_path)),
            patch(
                "apps.moderation.services.auto_moderation.auto_moderate",
                return_value=True,
            ),
            patch(
                "apps.media.services.thumbnails.ThumbnailService.generate_thumbnails",
                side_effect=ValueError("corrupt input"),
            ),
        ):
            passed, errors = await update_ad_and_moderate(
                ad_id=ad.id,
                title_ru="Title",
                desc_ru="Description",
                category_id=category.id,
                city_id=city.id,
                price=100,
                photos=photos,
                user_id=user.id,
            )

        assert passed is True
        ad_image = await sync_to_async(AdImage.objects.get)(ad=ad)
        assert ad_image.thumbnail_small is None
        assert ad_image.thumbnail_medium is None
        assert ad_image.thumbnail_large is None
