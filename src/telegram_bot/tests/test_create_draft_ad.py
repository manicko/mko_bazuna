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
    pytest.mark.slow,
    pytest.mark.integration,
    pytest.mark.concurrent,
]
pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))


class TestCreateDraftAd:
    """create_draft_ad persists a DRAFT Ad against the real ORM."""

    @pytest.mark.asyncio
    async def test_creates_draft_ad(self, user: object) -> None:
        """create_draft_ad creates an Ad with DRAFT status."""
        from telegram_bot.handlers.ad_create import create_draft_ad

        ad = await create_draft_ad(user_id=user.id)  # type: ignore[arg-type]

        assert ad.id is not None
        assert ad.user_id == user.id
        assert ad.status == AdStatus.DRAFT

    @pytest.mark.asyncio
    async def test_draft_persisted_in_database(self, user: object) -> None:
        """The created Ad is persisted in the database and queryable."""
        from telegram_bot.handlers.ad_create import create_draft_ad

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
        from telegram_bot.handlers.ad_create import create_draft_ad, delete_draft

        ad = await create_draft_ad(user_id=user.id)  # type: ignore[arg-type]
        ad_id = ad.id

        await delete_draft(ad_id)

        from apps.ads.models import Ad

        exists = await sync_to_async(Ad.objects.filter(id=ad_id).exists)()
        assert not exists

    @pytest.mark.asyncio
    async def test_delete_draft_missing_succeeds(self) -> None:
        """delete_draft succeeds silently for a non-existent ad ID."""
        from telegram_bot.handlers.ad_create import delete_draft

        # Should not raise
        await delete_draft(99999999)

    @pytest.mark.asyncio
    async def test_draft_default_status(self, user: object) -> None:
        """Newly created ad has DRAFT status by default."""
        from telegram_bot.handlers.ad_create import create_draft_ad

        ad = await create_draft_ad(user_id=user.id)  # type: ignore[arg-type]

        assert ad.status == AdStatus.DRAFT
        # Verify no other status is set
        assert ad.status != AdStatus.PUBLISHED
        assert ad.status != AdStatus.ON_MODERATION
