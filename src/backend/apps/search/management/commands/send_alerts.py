"""
Management command to send daily saved search alert notifications.

Dispatched by the scheduler service on the first hourly tick at or after 08:00
UTC each calendar day — there is no cron entry in the containerised deployment.
Collects matching ads, records notifications and analytics events, then sends
consolidated digests to users via Telegram.

It takes a transaction-scoped advisory lock (``AdvisoryLockId.ALERT_DELIVERY_TASK``)
for **concurrency** control, not **repeat** protection; a second run against
unchanged data collects nothing anyway, because ``find_matching_ads`` excludes
already-notified pairs and the ``uq_saved_search_ad`` constraint makes the
insert idempotent.

Per-user delivery is capped at ``_DIGEST_AD_LIMIT`` (10), applied at
**collection** time so the notification rows and the rendered digest contain
the same ads; ads beyond the cap get no notification row, so a later run can
still deliver them.
"""

import asyncio
import logging
from typing import Final, cast

from aiogram import Bot
from aiogram.exceptions import (
    AiogramError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from django.conf import settings
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Exists, F, OuterRef, QuerySet
from django.utils import timezone
from django.utils.html import escape
from django.utils.translation import gettext as _, override as translation_override

from apps.ads.models import Ad
from apps.ads.templatetags.price_tags import format_price_value
from apps.analytics.models import AnalyticsEvent
from apps.categories.models import Category
from apps.core.enums import AdStatus, AdvisoryLockId, AnalyticsEventType, LanguageLocale
from apps.core.utils.advisory_lock import advisory_lock
from apps.search.models import SavedSearch, SavedSearchNotification
from apps.search.services.alert_query import find_matching_ads
from apps.search.services.notification_delivery import mark_delivered
from apps.users.services.account_state import account_state_q

logger = logging.getLogger(__name__)

# Capped backoff base (seconds) for transient retries (429/network/5xx).
_BACKOFF_BASE: Final[float] = 0.5

# Q8 single-sleep ceiling (seconds) for this path's one retry (09-VAL-009). There
# is exactly one retry and no loop here, so this is a ceiling on ONE sleep, not a
# total budget. It clamps the ``float(exc.retry_after)`` the bot mandates so the
# daily digest cannot be parked on an arbitrarily large Telegram ``retry_after``.
# 30.0 keeps the pinned ``retry_after=2`` fixture green and leaves ``_BACKOFF_BASE``
# (0.5) below the ceiling unchanged.
RETRY_AFTER_CEILING: Final[float] = 30.0

# Maximum unique ads rendered in a single user's daily digest. Applied at
# collection time so the notification set and the rendered set are the same set.
_DIGEST_AD_LIMIT: Final[int] = 10


def _group_key(saved_search: SavedSearch) -> tuple[str, str]:
    """Return the FTS-evaluation key for a saved search.

    ``find_matching_ads`` runs one FTS evaluation per saved search. The FTS
    evaluation depends only on the persisted ``language`` (which selects the
    vector column + text-search config) and the ``query`` text; every other
    filter it applies (city, category subtree, price range) is a structural
    filter layered on top of the shared evaluation. Two saved searches that
    share ``(language, query)`` therefore repeat the same FTS scan, and the
    group key is exactly that pair (13-PERF-005).
    """
    return (str(saved_search.language or ""), str(saved_search.query or ""))


def _evaluate_group_fts(language: str, query: str) -> QuerySet[Ad]:
    """Evaluate the shared FTS stage once for a ``(language, query)`` group.

    Mirrors the FTS stage of ``find_matching_ads`` (status + owner account-state
    + language-aware vector match + ``SearchRank`` ordering) without applying
    any per-search structural filter or the per-search ad cap. Returns an
    ordered queryset that each member then filters and caps independently.

    ``find_matching_ads`` itself is unchanged and remains the source of truth;
    this helper exists only so the repeated FTS scan can be shared across the
    members of one group, and its output is proven equivalent to
    ``find_matching_ads`` by the per-member composition (see
    ``_apply_member_filters``).
    """
    queryset: QuerySet[Ad] = (
        Ad.objects.filter(status=AdStatus.PUBLISHED)
        .filter(account_state_q("user__"))
        .select_related("category", "city")
    )
    if not query:
        return queryset

    locale = LanguageLocale.from_code(
        language,
        fallback=LanguageLocale.RUSSIAN,
    )
    vector_field = locale.fts_vector_field
    search_query = SearchQuery(
        query,
        search_type="websearch",
        config=locale.fts_config,
    )
    return (
        queryset.annotate(rank=SearchRank(F(vector_field), search_query))
        .filter(**{vector_field: search_query})
        .order_by("-rank")
    )


def _member_filter_signature(saved_search: SavedSearch) -> tuple:
    """Return the structural filters that distinguish members of one FTS group.

    Two members with the same signature would still differ in their per-search
    delivered-state dedup, so this is used only to bucket members, never to
    share a result set.
    """
    return (
        saved_search.city_id,
        saved_search.category_id,
        saved_search.min_price,
        saved_search.max_price,
    )


def _apply_member_filters(
    candidates: QuerySet[Ad], saved_search: SavedSearch
) -> list[Ad]:
    """Apply one member's structural filters, dedup and 10-ad cap.

    Reproduces the non-FTS stages of ``find_matching_ads`` for a single saved
    search over the group's shared, still-lazy candidate queryset: city,
    category subtree and price range, then the delivered-state ``NOT EXISTS``,
    then the per-search ``[:10]`` cap. Applied per member so two saved searches
    sharing a query but differing in a structural filter never share results,
    and so a member's cap is its own.
    """
    queryset = candidates

    if saved_search.city_id:
        queryset = queryset.filter(city_id=saved_search.city_id)

    if saved_search.category_id:
        category = saved_search.category
        if category is not None:
            descendant_ids: list[int] = list(
                Category.objects.get(pk=category.pk)
                .get_descendants(include_self=True)
                .values_list("pk", flat=True)
            )
            queryset = queryset.filter(category_id__in=descendant_ids)

    if saved_search.min_price is not None:
        queryset = queryset.filter(price_normalized_eur__gte=saved_search.min_price)
    if saved_search.max_price is not None:
        queryset = queryset.filter(price_normalized_eur__lte=saved_search.max_price)

    notified_ads = SavedSearchNotification.objects.filter(
        saved_search=saved_search,
        ad_id=OuterRef("pk"),
        delivered_at__isnull=False,
    )
    queryset = queryset.filter(~Exists(notified_ads))

    return cast(list[Ad], list(queryset[:10]))


def _select_digest_ads(bucket: list[Ad], matching_ads: list[Ad], limit: int) -> list[Ad]:
    """Return the ads from *matching_ads* that fit into *bucket* under *limit*.

    Deduplicates against what the user already has in *bucket* and stops once
    the per-user cap is reached. This is a *second, different* limit from the
    per-search 10-ad cap inside ``find_matching_ads``; that one bounds one
    saved search, this one bounds one user's whole digest.
    """
    known_ids = {ad.id for ad in bucket}
    selected: list[Ad] = []
    for ad in matching_ads:
        if len(bucket) + len(selected) >= limit:
            break
        if ad.id in known_ids:
            continue
        selected.append(ad)
    return selected


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
        """Execute alert delivery with advisory lock.

        Delivery state (03-DB-007): a ``SavedSearchNotification`` row is an
        ATTEMPT RECORD and ``delivered_at`` is the receipt. The receipt is
        written AFTER this day's digests are dispatched, once both the advisory
        lock and the transaction have closed — exactly where the send already
        runs, so the lock/transaction shape is unchanged — and only for the
        users whose digest Telegram accepted. A pair whose send failed (or whose
        user has no ``chat_id``) keeps ``delivered_at IS NULL`` and is
        re-collected by the next run, which is how a lost digest is retried
        instead of permanently suppressed.

        Moving the send inside the lock/transaction remains **wrong** — a
        mid-send crash would roll back the notification write and re-enable
        duplicate delivery, and it would widen the contention window against the
        lock-free ``deliver_immediate_alerts`` publish-time path.

        CommandError policy: raised only when every attempted user failed. A
        no-match day and a partially-failed day both exit 0.
        """
        dry_run: bool = options["dry_run"]

        if dry_run:
            with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
                with advisory_lock(AdvisoryLockId.ALERT_DELIVERY_TASK):
                    self._dry_run_check()
            return

        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
            with advisory_lock(AdvisoryLockId.ALERT_DELIVERY_TASK):
                user_ads, notifications_to_create, analytics_events = (
                    self._collect_alerts()
                )

                self._persist_alerts(notifications_to_create, analytics_events)

        # Send messages outside the transaction and outside the advisory lock
        # (network I/O). The delivery receipt is written after the digests are
        # dispatched, once both scopes have closed, so a failed digest leaves the
        # rows undelivered and retryable by the next run (03-DB-007). The mark is
        # a synchronous single statement on this connection — no lock, no
        # transaction — so it stays honest under any process.
        delivered_user_ids: set[int] = set()
        users_attempted = len(user_ads)
        users_sent = 0
        try:
            users_sent = asyncio.run(
                self._send_user_digests(
                    settings.BOT_TOKEN, user_ads, delivered_user_ids
                )
            )
        except AiogramError as exc:
            logger.error("Daily alert send failed: %s", exc)

        # Mark only the users whose digest was accepted by Telegram. A skipped
        # user (no chat_id) or a failed send is not in delivered_user_ids, so its
        # rows keep delivered_at IS NULL and stay collectable.
        for notification in notifications_to_create:
            if notification.saved_search.user_id not in delivered_user_ids:
                continue
            mark_delivered(
                notification.saved_search_id,
                notification.ad_id,
                sent_at=timezone.now(),
            )

        # A blanket AiogramError swallow exits 0, which lets the scheduler record
        # the day as complete even though nothing was delivered. Raise only when
        # every attempted user failed, so one dead chat_id cannot block the day's
        # marker while a total Telegram outage still blocks it.
        if users_attempted > 0 and users_sent == 0:
            raise CommandError(f"Alert delivery failed for all {users_attempted} users")

    def _dry_run_check(self) -> None:
        """Log counts of users, saved searches, and potential matches.

        Counts must reflect the account-state eligibility rule, so an operator's
        dry run does not promise messages that the real run would not send
        (06-PII-104).
        """
        active_searches = (
            SavedSearch.objects.filter(is_active=True)
            .filter(account_state_q("user__"))
            .select_related("user")
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

        The per-user digest cap (``_DIGEST_AD_LIMIT``) is applied **here**, at
        collection time, not in ``_send_user_digests``, so the notification rows
        and the rendered message contain the same ads. ``SEARCH_ALERT_MATCHED``
        now means "this search contributed at least one ad to the digest".
        Ads suppressed by the cap keep no notification row and stay collectable
        by a later run.

        Fairness note (known, accepted): the cap is applied in the iteration
        order of ``SavedSearch.objects.filter(is_active=True)``, which has no
        ``Meta.ordering``. A user with saved search A (10 matching ads) and
        saved search B (10 matching ads) therefore always receives A's ten and
        B's ten are deferred to a later run, regardless of which were published
        first or how relevant they are. This is deterministic in practice but
        not guaranteed by any ordering, and it is a fairness wart, not a bug:
        the suppressed ads carry no ``SavedSearchNotification`` row, so they
        are collected by the next run. Changing the policy (fair-share
        interleaving, or sorting by match rank across searches) is out of scope.

        The ``account_state_q("user__")`` filter excludes searches owned by a
        withdrawn, declined, banned or deactivated user, so this live daily
        path stops messaging identities the site and bot already gate
        (06-PII-104). It composes with ``is_active`` rather than replacing it.

        Grouping (13-PERF-005): the active searches are bucketed by distinct
        ``(language, query)`` and the shared FTS scan runs once per group
        (``_evaluate_group_fts``). Each member then applies its own structural
        filters, delivered-state dedup and per-search 10-ad cap
        (``_apply_member_filters``), so digest composition is identical to a
        per-search ``find_matching_ads`` call for the same data. ``find_matching_ads``
        is unchanged and still the source of truth for the non-FTS stages.

        Must be called inside a transaction with the advisory lock held.

        Returns:
            A tuple of (user_ads, notifications_to_create, analytics_events).
        """
        user_ads: dict[int, list] = {}
        notifications_to_create: list[SavedSearchNotification] = []
        analytics_events: list[AnalyticsEvent] = []

        active_searches = list(
            SavedSearch.objects.filter(is_active=True)
            .filter(account_state_q("user__"))
            .select_related("user", "city", "category")
        )

        # Group by distinct (language, query) so the FTS scan runs once per
        # group instead of once per saved search. The FTS evaluation depends
        # only on the persisted language and the query text; every other filter
        # is applied per member below, so digest composition is unchanged
        # (13-PERF-005).
        groups: dict[tuple[str, str], list[SavedSearch]] = {}
        for saved_search in active_searches:
            groups.setdefault(_group_key(saved_search), []).append(saved_search)

        logger.info(
            "Collecting alerts: %d active searches in %d distinct (language, query) groups",
            len(active_searches),
            len(groups),
        )

        for (language, query), members in groups.items():
            candidates = _evaluate_group_fts(language, query)
            for saved_search in members:
                matching_ads = _apply_member_filters(candidates, saved_search)
                if not matching_ads:
                    continue

                # Cap the per-user digest at collection time, so the
                # notification rows and the rendered message contain the SAME
                # ads. Previously a notification row was written for every
                # collected ad while the digest rendered only the first 10, so
                # the surplus was permanently suppressed by find_matching_ads'
                # NOT EXISTS with no record and no way to deliver it later.
                bucket = user_ads.setdefault(saved_search.user_id, [])
                selected_ads = _select_digest_ads(
                    bucket, matching_ads, _DIGEST_AD_LIMIT
                )
                if not selected_ads:
                    continue

                bucket.extend(selected_ads)
                notifications_to_create.extend(
                    SavedSearchNotification(saved_search=saved_search, ad=ad)
                    for ad in selected_ads
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
            # No constraint on analytics_events: eleven writers legitimately
            # duplicate (per ad-detail render, per search, per auto-moderation
            # attempt, per contact, seed bulk-creates). The scheduler's
            # run-level durable marker, not a row-level constraint, is the
            # dedupe mechanism. Do NOT add ignore_conflicts here: with no
            # conflict target it would silently swallow every constraint added
            # later, and test_contact.py asserts duplicates are kept.
            AnalyticsEvent.objects.bulk_create(analytics_events)

    async def _send_user_digests(
        self,
        bot_token: str,
        user_ads: dict[int, list],
        delivered_user_ids: set[int] | None = None,
    ) -> int:
        """Send consolidated digest messages; return users messaged.

        The caller owns the per-user cap, so the ``[:10]`` slice that used to
        live here is gone — each user's ``ads`` list is already the capped
        digest. The return value counts users whose message was accepted by
        Telegram (skipped and fully-failed users do not count) and is what
        ``handle()`` uses to decide whether the day's dispatch succeeded.

        Each user whose ``send_message`` (primary or retry) succeeds is added to
        ``delivered_user_ids``. A user with no ``chat_id`` is skipped BEFORE the
        send, so it is never added and its rows stay correctly unmarked and
        retryable (03-DB-007).
        """
        from apps.users.models import User

        bot = Bot(token=bot_token)
        sent_users = 0
        rendered_ads = 0
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

                unique_ads = list({ad.id: ad for ad in ads}.values())

                if not unique_ads:
                    continue

                locale = getattr(user, "telegram_language", None) or LanguageLocale.RUSSIAN.value
                message = self._format_digest(unique_ads, locale=locale)

                try:
                    await bot.send_message(
                        chat_id=user.chat_id,
                        text=message,
                        parse_mode="HTML",
                    )
                    rendered_ads += len(unique_ads)
                    sent_users += 1
                    if delivered_user_ids is not None:
                        delivered_user_ids.add(user_id)
                except (TelegramBadRequest, TelegramForbiddenError) as e:
                    logger.warning("Failed to send alert to user %d: %s", user_id, e)
                except (
                    TelegramRetryAfter,
                    TelegramServerError,
                    TelegramNetworkError,
                ) as e:
                    # Transient — retry once with capped backoff.
                    if isinstance(e, TelegramRetryAfter) and e.retry_after:
                        backoff: float = min(float(e.retry_after), RETRY_AFTER_CEILING)
                    else:
                        backoff = _BACKOFF_BASE
                    await asyncio.sleep(backoff)
                    try:
                        await bot.send_message(
                            chat_id=user.chat_id,
                            text=message,
                            parse_mode="HTML",
                        )
                        rendered_ads += len(unique_ads)
                        sent_users += 1
                        if delivered_user_ids is not None:
                            delivered_user_ids.add(user_id)
                    except AiogramError as retry_exc:
                        logger.warning(
                            "Alert retry failed to user %d: %s", user_id, retry_exc
                        )

            logger.info(
                "Alert digests sent: %d ads to %d users (%d users attempted)",
                rendered_ads,
                sent_users,
                len(user_ads),
            )
        finally:
            await bot.session.close()
        return sent_users

    def _format_digest(
        self, ads: list, locale: LanguageLocale = LanguageLocale.RUSSIAN
    ) -> str:
        """Format digest message for a user in their preferred locale.

        The message is sent with ``parse_mode="HTML"``, so the seller-controlled
        title is escaped with ``django.utils.html.escape`` (NOT the stdlib ``html``
        module, whose ``unescape`` in apps/core/services/translation.py *decodes*).
        Escaping is applied to the truncated title, after the 50-character slice,
        so the visible prefix length is unchanged for ordinary titles. The header
        and price are not seller-controlled and stay unescaped.
        """
        with translation_override(locale):
            lines = [
                _("New ads matching your saved searches ({count} found):\n").format(
                    count=len(ads)
                )
            ]
            for ad in ads:
                price_str = (
                    f" - {format_price_value(ad.price_amount, ad.price_currency)}"
                    if ad.price_amount is not None
                    else ""
                )
                title = escape(ad.get_title(locale)[:50])
                lines.append(f"• {title}\n  {price_str}\n")

            return "\n".join(lines)
