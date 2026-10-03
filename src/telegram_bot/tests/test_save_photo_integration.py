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
        from apps.ads.services.submission import (
            SubmitAdInput,
            SubmitAdOutcome,
            submit_ad,
        )
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
            result = await sync_to_async(submit_ad)(
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

        assert result.outcome is SubmitAdOutcome.PUBLISHED
        assert result.errors == []

        ad_image = await sync_to_async(AdImage.objects.get)(ad=ad)
        assert ad_image.thumbnail_small == "photo-small.jpg"
        assert ad_image.thumbnail_medium == "photo-medium.jpg"
        assert ad_image.thumbnail_large == "photo-large.jpg"

    @pytest.mark.asyncio
    async def test_thumbnails_null_on_generation_failure(self, user, tmp_path) -> None:
        """When ``generate_thumbnails`` raises, all three ``thumbnail_*`` stay null."""
        from apps.ads.models import AdImage
        from apps.ads.services.submission import (
            SubmitAdInput,
            SubmitAdOutcome,
            submit_ad,
        )
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
            result = await sync_to_async(submit_ad)(
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

        assert result.outcome is SubmitAdOutcome.PUBLISHED
        ad_image = await sync_to_async(AdImage.objects.get)(ad=ad)
        assert ad_image.thumbnail_small is None
        assert ad_image.thumbnail_medium is None
        assert ad_image.thumbnail_large is None


class TestSubmitAdStagingMove:
    """submit_ad promotes staging files to permanent storage AFTER the TX commits.

    Files written by ``save_photo`` to ``MEDIA_ROOT/staging/`` are key-rewritten
    to their permanent form *before* the ``transaction.atomic()`` block (a pure,
    in-memory rewrite of ``SubmittedPhoto`` fields), but the physical move runs
    from a ``transaction.on_commit`` callback registered inside the atomic block.
    The file therefore stays in ``staging/`` — where the orphan sweep never looks
    — until its ``AdImage`` row has committed, which closes the window in which a
    concurrent sweep could classify a promoted-but-uncommitted file as an orphan.

    On TX rollback nothing was promoted, so the staged file simply remains in
    ``staging/`` and is reclaimed by the existing TTL (``_STAGING_TTL_SECONDS``).
    """

    @pytest.mark.asyncio
    async def test_submit_ad_moves_staging_to_permanent(
        self, user, tmp_path
    ) -> None:
        """Staging files (original + thumbnails) are moved to permanent MEDIA_ROOT;
        AdImage rows reference permanent keys.

        The class runs under ``django_db(transaction=True)``, so the
        ``transaction.on_commit`` promotion has already fired by the time
        ``submit_ad`` returns and every file-side assertion below holds.
        """
        from apps.ads.models import AdImage
        from apps.ads.services.submission import (
            SubmitAdInput,
            SubmitAdOutcome,
            submit_ad,
        )
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
                result = await sync_to_async(submit_ad)(
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

            assert result.outcome is SubmitAdOutcome.PUBLISHED
            assert result.errors == []

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
    async def test_files_are_not_promoted_before_the_row_commits(
        self, user, tmp_path
    ) -> None:
        """No file is visible in permanent storage while the TX is still open.

        Direct guard for finding 03-DB-005.  The promotion runs from an
        ``on_commit`` callback, so at the moment ``auto_moderate`` is invoked —
        from *inside* the still-open ``transaction.atomic()`` block — the staging
        original must still exist and the permanent ``photo.jpg`` must not exist
        yet.  The interleaving is forced with the ``auto_moderate`` hook, never
        with sleeps.

        ``auto_moderate`` is imported function-locally inside ``submit_ad``, so
        the only valid patch target is
        ``apps.moderation.services.auto_moderation.auto_moderate``.
        """
        from apps.ads.models import AdImage
        from apps.ads.services.submission import (
            SubmitAdInput,
            SubmitAdOutcome,
            submit_ad,
        )
        from apps.currencies.enums import CurrencyCode
        from apps.media.services.filesystem import STAGING_PREFIX
        from telegram_bot.services.ad_data import create_draft_ad

        media_root = tmp_path

        observed: dict[str, bool] = {}

        def inspect_filesystem(*_args, **_kwargs) -> bool:
            """Snapshot the filesystem from inside the open transaction."""
            observed["staging_exists"] = (media_root / STAGING_PREFIX / "photo.jpg").exists()
            observed["permanent_exists"] = (media_root / "photo.jpg").exists()
            return True

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
                side_effect=inspect_filesystem,
            ):
                result = await sync_to_async(submit_ad)(
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

            assert result.outcome is SubmitAdOutcome.PUBLISHED

            # The hook actually ran inside the TX.
            assert observed, "auto_moderate was never reached"

            # Pre-fix this FAILS: the file was promoted before the TX opened.
            assert observed["staging_exists"] is True, (
                "staging original vanished before the row committed"
            )
            assert observed["permanent_exists"] is False, (
                "photo.jpg became visible in permanent storage before the row "
                "committed — the 03-DB-005 window is open"
            )

            # And it did commit, so after submit_ad returns the file is promoted.
            assert (media_root / "photo.jpg").is_file()
            ad_image = await sync_to_async(AdImage.objects.get)(ad=ad)
            assert ad_image.image == "photo.jpg"

    @pytest.mark.asyncio
    async def test_dedup_survives_deferred_promotion(self, user, tmp_path) -> None:
        """Content dedup still works when the bytes are not at the row's key.

        Under deferred promotion ``AdImageService._compute_sha256(permanent_key)``
        finds nothing and returns ``""``; the existing ``if digest:`` guard would
        then silently disable dedup for every submission.  ``submit_ad`` therefore
        hashes the STAGED bytes and passes ``sha256=`` explicitly.  This control
        FAILS if that override is removed from the ``submit_ad`` call site: the
        stored digest would be empty and the second submission would create a
        second row.

        Deduplication is scoped **per ad** (07-MEDIA-002): the two submissions
        therefore target the **same** ad, not two different ads of one seller.
        The second submission re-arms the ad to ``DRAFT`` first — ``submit_ad``
        requires ``DRAFT -> ON_MODERATION``, and ``auto_moderate`` is patched so
        the ad is left in ``ON_MODERATION``, which is not a legal source state
        for a second transition (it would return ``INVALID_TRANSITION`` and the
        second photo would never reach ``create_or_skip`` at all, so the test
        would silently stop exercising dedup).  The two photos are placed at
        distinct ``position`` values (0, then 1) so a broken tripwire fails with
        the clean count assertion rather than ``IntegrityError`` from
        ``uq_ad_images_ad_position``.
        """
        from apps.ads.models import Ad, AdImage
        from apps.ads.services.submission import (
            SubmitAdInput,
            SubmitAdOutcome,
            submit_ad,
        )
        from apps.core.enums import AdStatus
        from apps.currencies.enums import CurrencyCode
        from apps.media.services.filesystem import STAGING_PREFIX
        from apps.media.services.hash_service import FileHashService
        from telegram_bot.services.ad_data import create_draft_ad

        media_root = tmp_path

        photo_bytes = _make_test_image(800, 600)
        digest_probe = media_root / "digest-probe.jpg"
        digest_probe.write_bytes(photo_bytes)
        expected_digest = FileHashService.calculate_sha256(str(digest_probe))

        with override_settings(MEDIA_ROOT=str(media_root)):
            ad = await create_draft_ad(user_id=user.id)

            def stage(key: str) -> str:
                storage_key = f"{STAGING_PREFIX}{key}"
                staging_dir = media_root / STAGING_PREFIX
                staging_dir.mkdir(parents=True, exist_ok=True)
                (staging_dir / key).write_bytes(photo_bytes)
                return storage_key

            def build_input(storage_key: str, position: int) -> SubmitAdInput:
                return SubmitAdInput(
                    ad_id=ad.id,
                    title_ru="Title",
                    desc_ru="Description",
                    category_id=None,
                    city_id=None,
                    price_amount=100,
                    price_currency=CurrencyCode.EUR,
                    photos=[
                        {
                            "storage_key": storage_key,
                            "telegram_file_id": "AgADBQ",
                            "position": position,
                        }
                    ],
                    user_id=user.id,
                )

            with patch(
                "apps.moderation.services.auto_moderation.auto_moderate",
                return_value=True,
            ):
                first_result = await sync_to_async(submit_ad)(
                    build_input(stage("first.jpg"), 0)
                )
                assert first_result.outcome is SubmitAdOutcome.PUBLISHED, (
                    first_result.errors
                )

                first_image = await sync_to_async(AdImage.objects.get)(ad=ad)

                # The digest is non-empty and equals the digest of the STAGED bytes.
                assert first_image.sha256 != "", "deferred promotion emptied the digest"
                assert first_image.sha256 == expected_digest

                # Re-arm the ad to DRAFT: submit_ad left it in ON_MODERATION and
                # a second DRAFT -> ON_MODERATION transition requires DRAFT as
                # the source state (see the docstring).
                await sync_to_async(
                    lambda: Ad.objects.filter(pk=ad.pk).update(status=AdStatus.DRAFT)
                )()

                second_result = await sync_to_async(submit_ad)(
                    build_input(stage("second.jpg"), 1)
                )
                assert second_result.outcome is SubmitAdOutcome.PUBLISHED, (
                    second_result.errors
                )

            # Identical bytes + same ad → same row, not a second row.
            rows = await sync_to_async(
                lambda: list(AdImage.objects.filter(ad=ad))
            )()
            assert len(rows) == 1, (
                "identical bytes to the same ad created a duplicate row — the "
                "sha256 override is missing or ineffective"
            )
            # The surviving row is the first one: the second submission was a
            # skip, not a silently-not-created row.
            assert rows[0].pk == first_image.pk

    @pytest.mark.asyncio
    async def test_submit_ad_rollback_leaves_files_in_staging(
        self, user, tmp_path
    ) -> None:
        """On TX rollback nothing was promoted, so files stay in staging/.

        This INVERTS the former ``test_submit_ad_rollback_leaves_permanent_orphans``,
        which asserted the defect: it expected the file to have been promoted
        *before* the TX and therefore left as a permanent orphan on rollback.
        Under the ``on_commit`` design the move never runs when the TX rolls
        back, so permanent ``photo.jpg`` does not exist, the staging original and
        its thumbnails still exist, no ``AdImage`` rows were created, and the ad
        stays DRAFT.  The staged file is reclaimed by the existing TTL.
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

            # Nothing reached permanent storage — the move is post-commit.
            assert not (media_root / "photo.jpg").exists(), (
                "permanent original must not exist after rollback"
            )
            for suffix in ("small", "medium", "large"):
                assert not (media_root / f"photo-{suffix}.jpg").exists(), (
                    f"permanent thumbnail {suffix} must not exist after rollback"
                )

            # The staged files remain, awaiting the existing TTL reclamation.
            assert (media_root / STAGING_PREFIX / "photo.jpg").is_file(), (
                "staging original should still exist after rollback"
            )
            for suffix in ("small", "medium", "large"):
                assert (
                    media_root / STAGING_PREFIX / f"photo-{suffix}.jpg"
                ).is_file(), f"staging thumbnail {suffix} should still exist"

            # No AdImage rows created (TX rolled back)
            count = await sync_to_async(
                lambda: AdImage.objects.filter(ad=ad).count()
            )()
            assert count == 0, "AdImage rows should not exist after rollback"

            # Ad stays DRAFT (status transition was inside the TX)
            await sync_to_async(ad.refresh_from_db)()
            assert ad.status == "DRAFT" or ad.status == AdStatus.DRAFT
