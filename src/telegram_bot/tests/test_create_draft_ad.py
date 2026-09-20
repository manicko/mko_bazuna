"""
Tests for create_draft_ad — DRAFT persistence against real ORM.

Verifies that ``create_draft_ad`` creates an ``Ad`` row with ``DRAFT``
status, and that ``delete_draft`` removes it. These are the core
ORM-persistence primitives shared by the bot's ad creation FSM.
"""

import pytest
from asgiref.sync import sync_to_async

from apps.core.enums import AdStatus

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
    pytest.mark.concurrent,
]
pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))


class TestCreateDraftAd:
    """create_draft_ad persists a DRAFT Ad against the real ORM."""

    @pytest.mark.asyncio
    async def test_creates_draft_ad(self, user: object) -> None:
        """create_draft_ad creates an Ad with DRAFT status."""
        from telegram_bot.services.ad_data import create_draft_ad

        ad = await create_draft_ad(user_id=user.id)  # type: ignore[arg-type]

        assert ad.id is not None
        assert ad.user_id == user.id
        assert ad.status == AdStatus.DRAFT

    @pytest.mark.asyncio
    async def test_draft_persisted_in_database(self, user: object) -> None:
        """The created Ad is persisted in the database and queryable."""
        from telegram_bot.services.ad_data import create_draft_ad

        ad = await create_draft_ad(user_id=user.id)  # type: ignore[arg-type]

        # Verify it's persisted by querying from a fresh sync_to_async call
        from apps.ads.models import Ad

        get_ad = sync_to_async(Ad.objects.get)
        saved = await get_ad(id=ad.id)

        assert saved.status == AdStatus.DRAFT
        assert saved.user_id == user.id

    @pytest.mark.asyncio
    async def test_delete_draft_removes_ad(self, user: object) -> None:
        """delete_draft removes the draft Ad from the database."""
        from telegram_bot.services.ad_data import create_draft_ad, delete_draft

        ad = await create_draft_ad(user_id=user.id)  # type: ignore[arg-type]
        ad_id = ad.id

        await delete_draft(ad_id)

        from apps.ads.models import Ad

        exists = await sync_to_async(Ad.objects.filter(id=ad_id).exists)()
        assert not exists

    @pytest.mark.asyncio
    async def test_delete_draft_missing_succeeds(self) -> None:
        """delete_draft succeeds silently for a non-existent ad ID."""
        from telegram_bot.services.ad_data import delete_draft

        # Should not raise
        await delete_draft(99999999)

    @pytest.mark.asyncio
    async def test_draft_default_status(self, user: object) -> None:
        """Newly created ad has DRAFT status by default."""
        from telegram_bot.services.ad_data import create_draft_ad

        ad = await create_draft_ad(user_id=user.id)  # type: ignore[arg-type]

        assert ad.status == AdStatus.DRAFT
        # Verify no other status is set
        assert ad.status != AdStatus.PUBLISHED
        assert ad.status != AdStatus.ON_MODERATION

    @pytest.mark.asyncio
    async def test_create_draft_second_call_does_not_duplicate(
        self, user: object
    ) -> None:
        """Calling create_draft_ad twice leaves exactly one DRAFT for the user."""
        from telegram_bot.services.ad_data import create_draft_ad

        ad1 = await create_draft_ad(user_id=user.id)  # type: ignore[arg-type]
        ad2 = await create_draft_ad(user_id=user.id)  # type: ignore[arg-type]

        from apps.ads.models import Ad

        count = await sync_to_async(
            Ad.objects.filter(user_id=user.id, status=AdStatus.DRAFT).count
        )()

        assert count == 1
        assert ad2.status == AdStatus.DRAFT
        assert ad1.id != ad2.id


class TestCreateDraftAdCrashRecovery:
    """Crash-recovery tests for transaction.atomic() boundaries in ad_data.py.

    Verifies DB-001 and DB-002 fixes: when an exception is raised inside
    ``transaction.atomic()``, Django rolls back the savepoint, preserving
    DB rows and skipping post-commit filesystem deletion.
    """

    @pytest.mark.asyncio
    async def test_delete_draft_rollback_preserves_db_row_and_files(
        self, user: object
    ) -> None:
        """If ad.delete() raises inside transaction.atomic(), the DB row
        survives the rollback and delete_photo is NOT called (post-commit
        FS deletion is skipped)."""
        from unittest.mock import patch

        from apps.ads.models import Ad, AdImage
        from telegram_bot.services.ad_data import create_draft_ad, delete_draft

        ad = await create_draft_ad(user_id=user.id)  # type: ignore[arg-type]

        # Attach an AdImage with storage keys so delete_draft would collect them
        await sync_to_async(AdImage.objects.create)(
            ad=ad,
            image="crash-test-image.jpg",
            thumbnail_small="crash-test-image-small.jpg",
            thumbnail_medium="crash-test-image-medium.jpg",
            thumbnail_large="crash-test-image-large.jpg",
        )

        # Patch Ad.delete to raise — simulates crash inside transaction.atomic()
        with patch(
            "apps.ads.models.Ad.delete",
            side_effect=RuntimeError("simulated crash"),
        ):
            # Patch delete_photo to verify it is NOT called
            # (post-commit FS deletion is skipped on rollback)
            with patch("telegram_bot.services.ad_data.delete_photo") as mock_delete:
                with pytest.raises(RuntimeError, match="simulated crash"):
                    await delete_draft(ad.id)

        # DB row survived the rollback (ad.delete() was inside atomic, rolled back)
        exists = await sync_to_async(Ad.objects.filter(id=ad.id).exists)()
        assert exists, "Ad row should survive transaction rollback"

        # delete_photo was NOT called — FS deletion only happens post-commit
        assert mock_delete.call_count == 0, (
            "delete_photo should not be called when ad.delete() raises "
            "inside transaction.atomic()"
        )

    @pytest.mark.asyncio
    async def test_create_draft_atomic_rollback_preserves_existing_draft(
        self, user: object
    ) -> None:
        """If Ad.objects.create() raises after existing.delete(), the
        transaction.atomic() rollback preserves the old DRAFT row."""
        from unittest.mock import patch

        from apps.ads.models import Ad
        from telegram_bot.services.ad_data import create_draft_ad

        # Create initial DRAFT (without patch — real create)
        await create_draft_ad(user_id=user.id)  # type: ignore[arg-type]

        # Patch Ad.objects.create to raise RuntimeError on ALL calls.
        # RuntimeError is not caught by the IntegrityError fallback, so it
        # propagates out of transaction.atomic() and triggers rollback of
        # the preceding existing.delete().
        with patch(
            "apps.ads.models.Ad.objects.create",
            side_effect=RuntimeError("simulated create crash"),
        ):
            with pytest.raises(RuntimeError, match="simulated create crash"):
                await create_draft_ad(user_id=user.id)  # type: ignore[arg-type]

        # The original DRAFT row survives (rollback undid existing.delete())
        count = await sync_to_async(
            Ad.objects.filter(user_id=user.id, status=AdStatus.DRAFT).count
        )()
        assert count == 1, "Original DRAFT should survive transaction rollback"
