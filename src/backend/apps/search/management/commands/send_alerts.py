"""
Management command to send daily saved search alert notifications.

Runs once daily via cron. Uses advisory lock for idempotency.
Collects matching ads, records notifications and analytics events,
then sends consolidated digests to users via Telegram.
"""

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from apps.ads.templatetags.price_tags import format_price_value
from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AdvisoryLockId, AnalyticsEventType
from apps.core.utils.advisory_lock import advisory_lock
from apps.search.models import SavedSearch, SavedSearchNotification
from apps.search.services.alert_query import find_matching_ads
from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Send daily saved search alert notifications."""

    help = "Send daily Telegram alerts for matching saved searches"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            default=False,
            help="Print matching counts without sending messages",
        )

    def handle(self, *args, **options) -> None:
        """Execute alert delivery with advisory lock."""
        dry_run: bool = options["dry_run"]

        if dry_run:
            with advisory_lock(AdvisoryLockId.ALERT_DELIVERY_TASK, session=True):
                self._dry_run_check()
            return

        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
            with advisory_lock(AdvisoryLockId.ALERT_DELIVERY_TASK):
                user_ads, notifications_to_create, analytics_events = (
                    self._collect_alerts()
                )

                self._persist_alerts(notifications_to_create, analytics_events)

        # Send messages outside the transaction (network I/O)
        asyncio.run(self._send_user_digests(settings.BOT_TOKEN, user_ads))

    def _dry_run_check(self) -> None:
        """Log counts of users, saved searches, and potential matches."""
        active_searches = SavedSearch.objects.filter(is_active=True).select_related(
            "user"
        )
        user_count = (
            active_searches.values_list("user_id", flat=True).distinct().count()
        )
        search_count = active_searches.count()

        total_matches = 0
        for saved_search in active_searches:
            matches = find_matching_ads(saved_search)
            total_matches += len(matches)

        logger.info(
            "DRY RUN: Would process %d users, %d saved searches, %d total matches",
            user_count,
            search_count,
            total_matches,
        )

    def _collect_alerts(self) -> tuple[dict[int, list], list, list]:
        """Collect notification data for all active saved searches.

        Must be called inside a transaction with the advisory lock held.

        Returns:
            A tuple of (user_ads, notifications_to_create, analytics_events).
        """
        user_ads: dict[int, list] = {}
        notifications_to_create: list[SavedSearchNotification] = []
        analytics_events: list[AnalyticsEvent] = []

        for saved_search in SavedSearch.objects.filter(is_active=True).select_related(
            "user", "city", "category"
        ):
            matching_ads = find_matching_ads(saved_search)

            if not matching_ads:
                continue

            if saved_search.user_id not in user_ads:
                user_ads[saved_search.user_id] = []
            user_ads[saved_search.user_id].extend(matching_ads)

            notifications_to_create.extend(
                SavedSearchNotification(saved_search_id=saved_search.id, ad_id=ad.id)
                for ad in matching_ads
            )

            analytics_events.append(
                AnalyticsEvent(
                    event_type=AnalyticsEventType.SEARCH_ALERT_MATCHED,
                    user_id=saved_search.user_id,
                )
            )

        return user_ads, notifications_to_create, analytics_events

    def _persist_alerts(
        self,
        notifications_to_create: list[SavedSearchNotification],
        analytics_events: list[AnalyticsEvent],
    ) -> None:
        """Bulk-create notifications and analytics events.

        Must be called inside a transaction with the advisory lock held.
        """
        if notifications_to_create:
            SavedSearchNotification.objects.bulk_create(
                notifications_to_create, ignore_conflicts=True
            )

        if analytics_events:
            AnalyticsEvent.objects.bulk_create(analytics_events)

    async def _send_user_digests(
        self, bot_token: str, user_ads: dict[int, list]
    ) -> None:
        """Send consolidated digest messages to users."""
        from apps.users.models import User

        bot = Bot(token=bot_token)
        try:
            for user_id, ads in user_ads.items():
                try:
                    user = await User.objects.aget(id=user_id)
                except User.DoesNotExist:
                    logger.warning("User %d not found for alert delivery", user_id)
                    continue

                if not user.chat_id:
                    logger.warning(
                        "User %d has no chat_id - cannot send alert", user_id
                    )
                    continue

                unique_ads = list({ad.id: ad for ad in ads}.values())[:10]

                if not unique_ads:
                    continue

                message = self._format_digest(unique_ads)

                try:
                    await bot.send_message(
                        chat_id=user.chat_id,
                        text=message,
                        parse_mode="HTML",
                    )
                except (TelegramBadRequest, TelegramForbiddenError) as e:
                    logger.warning("Failed to send alert to user %d: %s", user_id, e)

            total_ads = sum(len(ads) for ads in user_ads.values())
            logger.info(
                "Sent alert digest for %d ads to %d users",
                total_ads,
                len(user_ads),
            )
        finally:
            await bot.session.close()

    def _format_digest(self, ads: list) -> str:
        """Format digest message for a user."""
        lines = [f"New ads matching your saved searches ({len(ads)} found):\n"]

        for ad in ads:
            price_str = (
                f" - {format_price_value(ad.price_amount, ad.price_currency)}"
                if ad.price_amount is not None
                else ""
            )
            lines.append(f"• {ad.title[:50]}\n  {price_str}\n")

        return "\n".join(lines)
