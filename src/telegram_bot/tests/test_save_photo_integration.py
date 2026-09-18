"""
Integration test for the ``submit_ad`` thumbnail pipeline (G-07).

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
from apps.currencies.enums import CurrencyCode
from apps.locations.models import City

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
    pytest.mark.concurrent,
]
pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))


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
        from apps.ads.services.submission import SubmitAdInput, submit_ad
        from telegram_bot.services.ad_data import create_draft_ad

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
            passed, errors = await sync_to_async(submit_ad)(
                SubmitAdInput(
                    ad_id=ad.id,
                    title_ru="Title",
                    desc_ru="Description",
                    category_id=category.id,
                    city_id=city.id,
                    price_amount=100,
                    price_currency=CurrencyCode.EUR,
                    photos=photos,
                    user_id=user.id,
                )
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
        from apps.ads.services.submission import SubmitAdInput, submit_ad
        from telegram_bot.services.ad_data import create_draft_ad

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
            passed, errors = await sync_to_async(submit_ad)(
                SubmitAdInput(
                    ad_id=ad.id,
                    title_ru="Title",
                    desc_ru="Description",
                    category_id=category.id,
                    city_id=city.id,
                    price_amount=100,
                    price_currency=CurrencyCode.EUR,
                    photos=photos,
                    user_id=user.id,
                )
            )

        assert passed is True
        ad_image = await sync_to_async(AdImage.objects.get)(ad=ad)
        assert ad_image.thumbnail_small is None
        assert ad_image.thumbnail_medium is None
        assert ad_image.thumbnail_large is None


class TestSubmitAdStagingMove:
    """submit_ad promotes staging files to permanent storage before the TX.

    Files written by ``save_photo`` to ``MEDIA_ROOT/staging/`` must be moved
    to permanent storage by ``submit_ad`` *before* the ``transaction.atomic()``
    block, so that AdImage rows reference permanent keys (never staging keys).
    On TX rollback, the permanent files become unreferenced orphans — the
    normal orphan sweep reclaims them.
    """

    @pytest.mark.asyncio
    async def test_submit_ad_moves_staging_to_permanent(
        self, user, tmp_path
    ) -> None:
        """Staging files (original + thumbnails) are moved to permanent MEDIA_ROOT;
        AdImage rows reference permanent keys."""
        from apps.ads.models import AdImage
        from apps.ads.services.submission import SubmitAdInput, submit_ad
        from apps.currencies.enums import CurrencyCode
        from apps.media.services.filesystem import STAGING_PREFIX
        from telegram_bot.services.ad_data import create_draft_ad

        media_root = tmp_path

        with override_settings(MEDIA_ROOT=str(media_root)):
            ad = await create_draft_ad(user_id=user.id)

            photo_bytes = _make_test_image(800, 600)
            storage_key = f"{STAGING_PREFIX}photo.jpg"
            staging_dir = media_root / STAGING_PREFIX
            staging_dir.mkdir(parents=True, exist_ok=True)
            (staging_dir / "photo.jpg").write_bytes(photo_bytes)

            photos = [
                {
                    "storage_key": storage_key,
                    "telegram_file_id": "AgADBQ",
                    "position": 0,
                }
            ]

            with patch(
                "apps.moderation.services.auto_moderation.auto_moderate",
                return_value=True,
            ):
                passed, errors = await sync_to_async(submit_ad)(
                    SubmitAdInput(
                        ad_id=ad.id,
                        title_ru="Title",
                        desc_ru="Description",
                        category_id=None,
                        city_id=None,
                        price_amount=100,
                        price_currency=CurrencyCode.EUR,
                        photos=photos,
                        user_id=user.id,
                    )
                )

            assert passed is True
            assert errors == []

            # Original moved from staging/ to permanent
            assert (media_root / "photo.jpg").is_file(), (
                "original not moved to permanent"
            )
            assert not (media_root / STAGING_PREFIX / "photo.jpg").exists(), (
                "staging original still exists after move"
            )

            # All thumbnail variants also moved from staging/ to permanent
            for suffix in ("small", "medium", "large"):
                assert (media_root / f"photo-{suffix}.jpg").is_file(), (
                    f"thumbnail {suffix} not moved to permanent"
                )
                assert not (
                    media_root / STAGING_PREFIX / f"photo-{suffix}.jpg"
                ).exists(), (
                    f"staging thumbnail {suffix} still exists after move"
                )

            # AdImage references permanent keys (not staging)
            ad_image = await sync_to_async(AdImage.objects.get)(ad=ad)
            assert ad_image.image == "photo.jpg"
            assert not ad_image.image.startswith(STAGING_PREFIX)
            assert ad_image.thumbnail_small == "photo-small.jpg"
            assert ad_image.thumbnail_medium == "photo-medium.jpg"
            assert ad_image.thumbnail_large == "photo-large.jpg"

    @pytest.mark.asyncio
    async def test_submit_ad_rollback_leaves_permanent_orphans(
        self, user, tmp_path
    ) -> None:
        """On TX rollback, permanent files are left as unreferenced orphans.

        ``move_staging_to_permanent`` runs before ``transaction.atomic()``;
        if the TX rolls back (e.g. auto_moderate raises), the permanent files
        are already on disk but no AdImage rows were created.  The normal
        orphan sweep would reclaim them.
        """
        from apps.ads.models import AdImage
        from apps.ads.services.submission import SubmitAdInput, submit_ad
        from apps.core.enums import AdStatus
        from apps.currencies.enums import CurrencyCode
        from apps.media.services.filesystem import STAGING_PREFIX
        from telegram_bot.services.ad_data import create_draft_ad

        media_root = tmp_path

        with override_settings(MEDIA_ROOT=str(media_root)):
            ad = await create_draft_ad(user_id=user.id)

            photo_bytes = _make_test_image(800, 600)
            storage_key = f"{STAGING_PREFIX}photo.jpg"
            staging_dir = media_root / STAGING_PREFIX
            staging_dir.mkdir(parents=True, exist_ok=True)
            (staging_dir / "photo.jpg").write_bytes(photo_bytes)

            photos = [
                {
                    "storage_key": storage_key,
                    "telegram_file_id": "AgADBQ",
                    "position": 0,
                }
            ]

            with patch(
                "apps.moderation.services.auto_moderation.auto_moderate",
                side_effect=RuntimeError("simulated moderation failure"),
            ):
                with pytest.raises(RuntimeError, match="simulated moderation failure"):
                    await sync_to_async(submit_ad)(
                        SubmitAdInput(
                            ad_id=ad.id,
                            title_ru="Title",
                            desc_ru="Description",
                            category_id=None,
                            city_id=None,
                            price_amount=100,
                            price_currency=CurrencyCode.EUR,
                            photos=photos,
                            user_id=user.id,
                        )
                    )

            # Permanent files exist on disk (moved before TX, TX rolled back)
            assert (media_root / "photo.jpg").is_file(), (
                "permanent original should exist after rollback"
            )
            assert not (media_root / STAGING_PREFIX / "photo.jpg").exists(), (
                "staging original should have been moved before TX rollback"
            )

            # Thumbnail files also moved to permanent (orphans after rollback)
            for suffix in ("small", "medium", "large"):
                assert (media_root / f"photo-{suffix}.jpg").is_file(), (
                    f"permanent thumbnail {suffix} should exist after rollback"
                )

            # No AdImage rows created (TX rolled back)
            count = await sync_to_async(
                lambda: AdImage.objects.filter(ad=ad).count()
            )()
            assert count == 0, "AdImage rows should not exist after rollback"

            # Ad stays DRAFT (status transition was inside the TX)
            await sync_to_async(ad.refresh_from_db)()
            assert ad.status == "DRAFT" or ad.status == AdStatus.DRAFT
