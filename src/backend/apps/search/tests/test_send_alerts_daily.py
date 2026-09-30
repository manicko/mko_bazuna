"""
Integration tests for the send_alerts per-user digest cap and delivery outcome.

Covers:
  * ``_DIGEST_AD_LIMIT`` is applied at collection time so the notification
    rows and the rendered digest contain the same ads (the per-user cap, a
    *different* limit from the per-search 10-ad cap in ``find_matching_ads``).
  * ``CommandError`` is raised only when every attempted user failed, while a
    no-match day and a partially-failed day both exit 0.

``pytestmark`` is ``django_db``/``integration`` (not in ``test_send_alerts.py``,
which is ``unit``-marked — DB-backed tests there would break the marker's
meaning for every other test in it).

The ``CommandError`` -> non-zero exit -> marker-unchanged chain is pinned
end-to-end by ``test_scheduler_daily_marker.py`` (T2a/T1b) rather than composed
here, because composing it would need a real ``manage.py`` subprocess and a
live Telegram API.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramNetworkError
from django.core.management import CommandError, call_command

from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.search.management.commands.send_alerts import _DIGEST_AD_LIMIT
from apps.search.models import SavedSearch, SavedSearchNotification
from apps.search.services.alert_query import find_matching_ads
from apps.users.models import User
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_MODULE = "apps.search.management.commands.send_alerts"


class TestPerUserDigestCap:
    """The per-user digest cap is applied at collection time (not render time)."""

    def test_per_user_cap_is_applied_at_collection_time(
        self,
        seller: User,
        buyer: User,
        category: Category,
        city,
    ) -> None:
        """12 matching ads across two searches yield exactly _DIGEST_AD_LIMIT rows.

        Six PUBLISHED ads per category, two saved searches (one per category,
        no query, so FTS is avoided and the match sets are exactly 6 and 6).
        With the per-user cap of 10, the second-processed search contributes
        only 4 ads; the remaining 2 get no notification row and stay
        collectable by a later run.
        """
        cat_b = Category.objects.create(name="Мебель", slug="furniture-b6")

        cat_a_ads = [
            create_test_ad(
                seller, category, city,
                status=AdStatus.PUBLISHED,
                title=f"alpha ad {i}",
            )
            for i in range(6)
        ]
        cat_b_ads = [
            create_test_ad(
                seller, cat_b, city,
                status=AdStatus.PUBLISHED,
                title=f"beta ad {i}",
            )
            for i in range(6)
        ]

        search_a = SavedSearch.objects.create(user=buyer, category=category, is_active=True)
        search_b = SavedSearch.objects.create(user=buyer, category=cat_b, is_active=True)

        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock(return_value=None)
        mock_bot.session.close = AsyncMock()

        with (
            patch(f"{_MODULE}.Bot", return_value=mock_bot),
            patch.object(User.objects, "aget", new=AsyncMock(return_value=buyer)),
        ):
            call_command("send_alerts")

        # 1. Exactly the cap worth of notification rows.
        assert SavedSearchNotification.objects.count() == _DIGEST_AD_LIMIT

        # 2. The rendered message contains the title of every ad that has a
        #    notification row, and none of the ads that do not.
        notified_ids = set(
            SavedSearchNotification.objects.values_list("ad_id", flat=True)
        )
        all_ads = list(cat_a_ads) + list(cat_b_ads)
        notified_titles = {ad.title for ad in all_ads if ad.id in notified_ids}
        unmatched_titles = {ad.title for ad in all_ads if ad.id not in notified_ids}

        message = mock_bot.send_message.await_args_list[0].kwargs["text"]
        for title in notified_titles:
            assert title in message
        for title in unmatched_titles:
            assert title not in message

        # 3. The 2 unmatched ads have no notification row.
        for ad in all_ads:
            if ad.id not in notified_ids:
                assert not SavedSearchNotification.objects.filter(ad_id=ad.id).exists()

        # 4. The suppressed ads are still collectable by find_matching_ads —
        #    a later run can still deliver them.
        for search in (search_a, search_b):
            unmatched_in_search = {
                ad.id
                for ad in all_ads
                if ad.category_id == search.category_id and ad.id not in notified_ids
            }
            still_collectable = {ad.id for ad in find_matching_ads(search)}
            assert unmatched_in_search <= still_collectable


class TestDailyDigestMarksDelivered:
    """The daily digest marks its rows delivered after a successful send.

    This is the infinite-loop guard for the one-atomic-change rule (03-DB-007):
    if the daily matcher filters on ``delivered_at`` but the daily write never
    sets it, the same pair is collected every day forever.
    """

    def test_daily_digest_marks_delivered_after_send(
        self,
        seller: User,
        buyer: User,
        category: Category,
        city,
    ) -> None:
        """A successful digest send marks that user's rows delivered."""
        create_test_ad(seller, category, city, status=AdStatus.PUBLISHED, title="ad")
        saved_search = SavedSearch.objects.create(
            user=buyer, category=category, is_active=True
        )

        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock(return_value=None)
        mock_bot.session.close = AsyncMock()

        with (
            patch(f"{_MODULE}.Bot", return_value=mock_bot),
            patch.object(User.objects, "aget", new=AsyncMock(return_value=buyer)),
        ):
            call_command("send_alerts")

        rows = SavedSearchNotification.objects.filter(saved_search=saved_search)
        assert rows.count() == 1
        assert all(row.delivered_at is not None for row in rows)
        # And the pair is no longer collectable.
        assert find_matching_ads(saved_search) == []

    def test_daily_digest_leaves_rows_undelivered_on_failure(
        self,
        seller: User,
        buyer: User,
        category: Category,
        city,
    ) -> None:
        """A failed digest send leaves that user's rows undelivered (retryable)."""
        create_test_ad(seller, category, city, status=AdStatus.PUBLISHED, title="ad")
        saved_search = SavedSearch.objects.create(
            user=buyer, category=category, is_active=True
        )

        async def always_fail(chat_id, text, parse_mode) -> None:
            raise TelegramNetworkError(message="net", method=MagicMock())

        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock(side_effect=always_fail)
        mock_bot.session.close = AsyncMock()

        with (
            patch(f"{_MODULE}.Bot", return_value=mock_bot),
            patch(f"{_MODULE}.asyncio.sleep", new=AsyncMock()),
            patch.object(User.objects, "aget", new=AsyncMock(return_value=buyer)),
        ):
            with pytest.raises(CommandError):
                call_command("send_alerts")

        rows = SavedSearchNotification.objects.filter(saved_search=saved_search)
        assert rows.count() == 1
        assert all(row.delivered_at is None for row in rows)
        # The pair stays collectable so a later run can deliver it.
        assert [ad.id for ad in find_matching_ads(saved_search)] == [
            rows.get().ad_id
        ]


class TestDeliveryOutcome:
    """CommandError is raised only when every attempted user failed."""

    def test_all_users_failed_raises_command_error(
        self,
        seller: User,
        buyer: User,
        category: Category,
        city,
    ) -> None:
        """A single user whose delivery fails (original + retry) raises."""
        create_test_ad(seller, category, city, status=AdStatus.PUBLISHED, title="alert ad")
        SavedSearch.objects.create(user=buyer, category=category, is_active=True)

        async def always_fail(chat_id, text, parse_mode) -> None:
            raise TelegramNetworkError(message="net", method=MagicMock())

        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock(side_effect=always_fail)
        mock_bot.session.close = AsyncMock()

        with (
            patch(f"{_MODULE}.Bot", return_value=mock_bot),
            patch(f"{_MODULE}.asyncio.sleep", new=AsyncMock()),
            patch.object(User.objects, "aget", new=AsyncMock(return_value=buyer)),
        ):
            with pytest.raises(CommandError, match="all 1 users"):
                call_command("send_alerts")

    def test_no_matches_exits_zero(self) -> None:
        """No active saved searches -> call_command must not raise.

        Pins the ``users_attempted > 0`` guard: a no-match day exits 0 so the
        scheduler records the day as complete.
        """
        mock_bot = MagicMock()
        mock_bot.session.close = AsyncMock()

        with patch(f"{_MODULE}.Bot", return_value=mock_bot):
            call_command("send_alerts")  # must not raise

    def test_one_failed_user_does_not_raise(
        self,
        seller: User,
        buyer: User,
        category: Category,
        city,
    ) -> None:
        """One failing user + one succeeding user -> no raise (not any-failed)."""
        user2 = User.objects.create(
            telegram_id=910000002, chat_id=910000002, password="x"
        )
        create_test_ad(seller, category, city, status=AdStatus.PUBLISHED, title="alert ad 1")
        create_test_ad(seller, category, city, status=AdStatus.PUBLISHED, title="alert ad 2")
        SavedSearch.objects.create(user=buyer, category=category, is_active=True)
        SavedSearch.objects.create(user=user2, category=category, is_active=True)

        buyer_chat_id = buyer.chat_id

        async def fake_aget(id) -> User:
            return buyer if id == buyer.pk else user2

        async def fake_send_message(chat_id, text, parse_mode):
            if chat_id == buyer_chat_id:
                return None
            raise TelegramNetworkError(message="net", method=MagicMock())

        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock(side_effect=fake_send_message)
        mock_bot.session.close = AsyncMock()

        with (
            patch(f"{_MODULE}.Bot", return_value=mock_bot),
            patch(f"{_MODULE}.asyncio.sleep", new=AsyncMock()),
            patch.object(
                User.objects, "aget", new=AsyncMock(side_effect=fake_aget)
            ),
        ):
            call_command("send_alerts")  # must not raise
