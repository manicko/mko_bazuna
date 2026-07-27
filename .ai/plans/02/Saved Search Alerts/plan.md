# Saved Search Alerts - Implementation Plan

**Date:** July 26, 2026  
**Phase:** Phase 2  
**Status:** Ready for Implementation  

---

## Overview

Saved Search Alerts allow users to save search queries and receive daily Telegram notifications when new ads matching their criteria are published. The system uses PostgreSQL FTS, advisory locks for idempotent delivery, and the existing bot/web infrastructure.

---

## Task Execution Order (Dependency DAG)

```
T4 (Analytics Enum) → T2 (AdvisoryLockId + App Registration)
                    ↓
T1 (Models)       → T3 (AlertQueryService) → T6 (Delivery Command)
                    ↓                            ↓
T5 (Bot Handler)  ──────────────────────────────┘
                    ↓
              T8 (Router Integration)

T7 (Templates) - Parallel, no code dependency
```

### Execution Sequence

| Task | Priority | Dependencies | Risk Level |
|------|----------|--------------|------------|
| T4 | 1 | None | Low |
| T2 | 1 | None | Low |
| T1 | 2 | T4, T2 | Medium |
| T3 | 3 | T1, search patterns | Medium |
| T6 | 4 | T1, T3 | Medium |
| T5 | 5 | T1 | Medium |
| T8 | 6 | T5 | Low |
| T7 | Parallel | None | Low |

---

## Task Specifications

### T1: SavedSearch & SavedSearchNotification Models

**File:** `src/backend/apps/search/models/saved_search.py`

**Dependencies:**
- `apps.users.models.User` (exists)
- `apps.ads.models.Ad` (exists)
- `apps.categories.models.Category` (exists)
- `apps.locations.models.City` (exists)

**Implementation:**

```python
# src/backend/apps/search/models/saved_search.py
"""Saved search models for alert notifications."""

from django.db import models


class SavedSearch(models.Model):
    """Saved search query for alert notifications."""

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="saved_searches",
        help_text="User who saved this search",
    )
    query = models.TextField(
        blank=True,
        null=True,
        help_text="FTS query string (translated to Russian if Bosnian input)",
    )
    city = models.ForeignKey(
        "locations.City",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="saved_searches",
        help_text="Optional city filter",
    )
    category = models.ForeignKey(
        "categories.Category",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="saved_searches",
        help_text="Optional category filter (includes descendants)",
    )
    min_price = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Minimum price filter in BAM",
    )
    max_price = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Maximum price filter in BAM",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive searches do not receive notifications",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this saved search was created",
    )

    class Meta:
        db_table = "saved_searches"
        indexes = [
            models.Index(
                name="IX_saved_searches_user_active",
                fields=["user_id", "is_active"],
            ),
        ]

    def __str__(self) -> str:
        return f"SavedSearch {self.id} for User {self.user_id}"


class SavedSearchNotification(models.Model):
    """
    Tracks delivered ad notifications to prevent duplicates.

    Unique constraint ensures each (saved_search, ad) pair is recorded only once.
    """

    saved_search = models.ForeignKey(
        SavedSearch,
        on_delete=models.CASCADE,
        related_name="notifications",
        help_text="The saved search this notification belongs to",
    )
    ad = models.ForeignKey(
        "ads.Ad",
        on_delete=models.CASCADE,
        related_name="saved_search_notifications",
        help_text="The ad that was sent in the notification",
    )
    sent_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this notification was sent",
    )

    class Meta:
        db_table = "saved_search_notifications"
        constraints = [
            models.UniqueConstraint(
                fields=["saved_search", "ad"],
                name="unique_saved_search_ad",
            ),
        ]
        indexes = [
            models.Index(
                name="IX_saved_search_notifications_search",
                fields=["saved_search_id"],
            ),
        ]

    def __str__(self) -> str:
        return f"Notification {self.id}: saved_search={self.saved_search_id}, ad={self.ad_id}"
```

**Models Init:** `src/backend/apps/search/models/__init__.py`

```python
from apps.search.models.saved_search import (
    SavedSearch,
    SavedSearchNotification,
)

__all__ = ["SavedSearch", "SavedSearchNotification"]
```

**Migrations:**
- Create `src/backend/apps/search/migrations/0002_saved_search_models.py` via `uv run python manage.py makemigrations search`
- Run `uv run python manage.py migrate` to apply

---

### T2: AdvisoryLockId Extension + App Registration

**File:** `src/backend/apps/core/enums.py`

**Changes:**
Add `ALERT_DELIVERY_TASK = 8` to `AdvisoryLockId` enum (first available ID after existing Phase 4/Phase 2 jobs):

```python
# In AdvisoryLockId enum - add after PURGE_REJECTED_ADS = 7
ALERT_DELIVERY_TASK = 8
```

**File:** `src/backend/apps/search/apps.py`

No changes needed - Django auto-discovers models from `apps/search/models/` directory.

---

### T3: AlertQueryService

**File:** `src/backend/apps/search/services/alert_query.py`

**Dependencies:**
- `apps.search.services.query_translator.translate_query_bs_to_ru` (exists)
- `apps.ads.models.Ad` (exists)
- `apps.core.enums.AdStatus` (exists)

**Implementation:**

```python
# src/backend/apps/search/services/alert_query.py
"""
Alert query service for matching new ads against saved searches.

Reuses FTS patterns from search.py with deduplication via SavedSearchNotification.
"""

import logging

from apps.core.enums import AdStatus
from apps.search.models.saved_search import SavedSearch, SavedSearchNotification
from apps.search.services.query_translator import translate_query_bs_to_ru
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import Exists, OuterRef

logger = logging.getLogger(__name__)


def find_matching_ads(saved_search: SavedSearch) -> list:
    """
    Find newly published ads matching a saved search.

    Applies FTS query, category subtree, city, and price filters.
    Excludes ads already notified via SavedSearchNotification.

    Args:
        saved_search: The SavedSearch to match against

    Returns:
        List of matching Ad objects (max 10 for digest)
    """
    from apps.ads.models import Ad

    ads = Ad.objects.filter(status=AdStatus.PUBLISHED).select_related("category", "city")

    # Apply city filter if specified
    if saved_search.city_id:
        ads = ads.filter(city_id=saved_search.city_id)

    # Apply category filter with subtree support
    if saved_search.category_id:
        try:
            category = saved_search.category
            descendant_ids = category.get_descendants(include_self=True).values_list(
                "id", flat=True
            )
            ads = ads.filter(category_id__in=descendant_ids)
        except Exception:
            # Category may have been deleted - return empty
            return []

    # Apply price range filters
    if saved_search.min_price is not None:
        ads = ads.filter(price__gte=saved_search.min_price)
    if saved_search.max_price is not None:
        ads = ads.filter(price__lte=saved_search.max_price)

    # Apply FTS query if specified
    if saved_search.query:
        translated_query = translate_query_bs_to_ru(saved_search.query)

        search_query = SearchQuery(
            translated_query, search_type="websearch", config="russian"
        )
        ads = ads.annotate(
            rank=SearchRank("search_vector", search_query)
        ).filter(search_vector=search_query).order_by("-rank")

    # Exclude ads already notified (deduplication)
    notified_ads = SavedSearchNotification.objects.filter(
        saved_search=saved_search,
        ad_id=OuterRef("pk"),
    )
    ads = ads.filter(~Exists(notified_ads))

    # Limit to 10 ads per digest message (Telegram message limit consideration)
    return list(ads[:10])


def record_notifications(saved_search: SavedSearch, ads: list) -> int:
    """
    Record notification delivery in bulk for efficiency.

    Uses bulk_create with ignore_conflicts for idempotent operation.

    Args:
        saved_search: The SavedSearch that was matched
        ads: List of ads that were sent

    Returns:
        Number of notifications recorded
    """
    from apps.ads.models import Ad

    notifications = [
        SavedSearchNotification(saved_search_id=saved_search.id, ad_id=ad.id if isinstance(ad, Ad) else ad)
        for ad in ads
    ]
    SavedSearchNotification.objects.bulk_create(
        notifications, ignore_conflicts=True
    )
    return len(ads)
```

---

### T4: AnalyticsEventType Extension

**File:** `src/backend/apps/core/enums.py`

**Changes:**
Add `SEARCH_ALERT_MATCHED` to `AnalyticsEventType`:

```python
class AnalyticsEventType(StrEnum):
    REGISTRATION_CREATED = "registration_created"
    AD_PUBLISHED = "ad_published"
    SEARCH_PERFORMED = "search_performed"
    CONTACT_INITIATED = "contact_initiated"
    SEARCH_ALERT_MATCHED = "search_alert_matched"
```

---

### T5: Bot Handler for /alerts Command

**File:** `src/telegram_bot/states.py`

Add `SavedSearchState` enum:

```python
class SavedSearchState(StrEnum):
    """FSM states for saved search management."""

    IDLE = "alerts_idle"
    QUERY = "alerts_query"
    CITY = "alerts_city"
    CATEGORY = "alerts_category"
    PRICE = "alerts_price"
    CONFIRM = "alerts_confirm"
```

**File:** `src/telegram_bot/handlers/alerts.py`

```python
# src/telegram_bot/handlers/alerts.py
"""
Saved search alerts handler for Telegram bot.

Allows users to save search queries and receive daily notifications.
"""

import logging

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup
from asgiref.sync import sync_to_async

from apps.search.models import SavedSearch
from telegram_bot.states import SavedSearchState

logger = logging.getLogger(__name__)

router = Router()


class AlertForm(StatesGroup):
    """FSM states for alert management."""

    query = SavedSearchState.QUERY
    city = SavedSearchState.CITY
    category = SavedSearchState.CATEGORY
    price = SavedSearchState.PRICE
    confirm = SavedSearchState.CONFIRM


@router.message(Command("alerts"))
async def cmd_alerts(message: types.Message, state: FSMContext) -> None:
    """
    List saved searches for alert management.

    No args: list active saved searches with toggle status.
    """
    if not message.from_user:
        return

    data = await state.get_data()
    user_id = data.get("user_id")

    if not user_id:
        await message.answer(
            "Please login first with /start login_<token>"
        )
        return

    saved_searches = await get_user_saved_searches(user_id)

    if not saved_searches:
        await message.answer(
            "You have no saved searches.\n"
            "Saved searches will appear here once created via the web interface."
        )
        return

    lines = ["Your saved searches:"]
    for i, ss in enumerate(saved_searches, 1):
        status = "✓" if ss.is_active else "✗"
        query_display = ss.query or "any"
        city_display = ss.city.name if ss.city else "any"
        cat_display = ss.category.name if ss.category else "any"

        price_display = "any"
        if ss.min_price or ss.max_price:
            parts = []
            if ss.min_price:
                parts.append(f"≥{ss.min_price}")
            if ss.max_price:
                parts.append(f"≤{ss.max_price}")
            price_display = " ".join(parts)

        lines.append(
            f"{i}. [{status}] {query_display[:30]}\n"
            f"   City: {city_display}, Category: {cat_display}, Price: {price_display}"
        )

    lines.append("\nReply with number to toggle, or /cancel to exit.")
    await message.answer("\n".join(lines))


@sync_to_async
def get_user_saved_searches(user_id: int) -> list[SavedSearch]:
    """Get all saved searches for a user, ordered by creation date."""
    return list(
        SavedSearch.objects.filter(user_id=user_id)
        .select_related("city", "category")
        .order_by("-created_at")
    )
```

**Handlers Init:** `src/telegram_bot/handlers/__init__.py`

Add export:
```python
from telegram_bot.handlers.alerts import router as alerts_router

__all__ = ["login_router", "ad_create_router", "alerts_router"]
```

---

### T6: AlertDeliveryCommand

**File:** `src/backend/apps/search/management/commands/send_alerts.py`

```python
# src/backend/apps/search/management/commands/send_alerts.py
"""
Management command to send daily saved search alert notifications.

Runs once daily via cron. Uses advisory lock for idempotency.
"""

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbidden
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
        dry_run: bool = options["dry_run"]

        with advisory_lock(AdvisoryLockId.ALERT_DELIVERY_TASK):
            if dry_run:
                self._dry_run_check()
            else:
                self._send_alerts()

    def _dry_run_check(self) -> None:
        """Log counts of users, saved searches, and potential matches."""
        active_searches = SavedSearch.objects.filter(is_active=True).select_related("user")
        user_count = active_searches.values_list("user_id", flat=True).distinct().count()
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

    def _send_alerts(self) -> None:
        """Send alert notifications for all active saved searches."""
        bot_token = settings.BOT_TOKEN
        if not bot_token:
            logger.warning("BOT_TOKEN not set - skipping alert delivery")
            return

        # Collect notification data synchronously (inside transaction lock)
        user_ads: dict[int, list] = {}
        notifications_to_create: list[SavedSearchNotification] = []
        analytics_events: list[AnalyticsEvent] = []

        for saved_search in (
            SavedSearch.objects.filter(is_active=True)
            .select_related("user", "city", "category")
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

        # Bulk create notifications and analytics events
        if notifications_to_create:
            SavedSearchNotification.objects.bulk_create(
                notifications_to_create, ignore_conflicts=True
            )

        if analytics_events:
            AnalyticsEvent.objects.bulk_create(analytics_events)

        # Send messages asynchronously
        asyncio.run(self._send_user_digests(bot_token, user_ads))

    async def _send_user_digests(self, bot_token: str, user_ads: dict[int, list]) -> None:
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
                    logger.warning("User %d has no chat_id - cannot send alert", user_id)
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
                except (TelegramBadRequest, TelegramForbidden) as e:
                    logger.warning("Failed to send alert to user %d: %s", user_id, e)

            total_ads = sum(len(ads) for ads in user_ads.values())
            logger.info("Sent alert digest for %d ads to %d users", total_ads, len(user_ads))
        finally:
            await bot.session.close()

    def _format_digest(self, ads: list) -> str:
        """Format digest message for a user."""
        lines = [f"🔔 New ads matching your saved searches ({len(ads)} found):\n"]

        for ad in ads:
            price_str = f" - {ad.price} BAM" if ad.price else ""
            lines.append(
                f"• {ad.title[:50]}\n"
                f"  {price_str}\n"
            )

        return "\n".join(lines)
```

---

### T7: Modal Template for Web UI

**File:** `src/backend/templates/search/partials/save_search_modal.html`

```html
<!-- src/backend/templates/search/partials/save_search_modal.html -->
<!-- HTMX-compatible modal for saving search alerts -->

<div id="save-search-modal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
     hx-get="{% url 'search:list' %}"
     hx-trigger="htmx:afterRequest from #save-search-form"
     hx-target="#main-content">

    <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4">
        <h3 class="text-lg font-semibold mb-4">Save Search Alert</h3>

        <form id="save-search-form"
              hx-post="{% url 'search:save-search' %}"
              hx-swap="none"
              class="space-y-4">

            <!-- Query display (read-only) -->
            <div>
                <label class="block text-sm font-medium mb-1">Search Query</label>
                <input type="text" name="query" value="{{ query|default:'' }}"
                       class="w-full px-3 py-2 border rounded-lg bg-gray-50" readonly>
            </div>

            <!-- City filter -->
            <div>
                <label class="block text-sm font-medium mb-1">City (optional)</label>
                <select name="city_id" class="w-full px-3 py-2 border rounded-lg">
                    <option value="">Any city</option>
                    {% for city in cities %}
                    <option value="{{ city.id }}"
                            {% if selected_city == city.id %}selected{% endif %}>
                        {{ city.get_name }}
                    </option>
                    {% endfor %}
                </select>
            </div>

            <!-- Category filter -->
            <div>
                <label class="block text-sm font-medium mb-1">Category (optional)</label>
                <select name="category_id" class="w-full px-3 py-2 border rounded-lg">
                    <option value="">Any category</option>
                    {% for category in categories %}
                    <option value="{{ category.id }}"
                            {% if selected_category == category.id %}selected{% endif %}>
                        {{ category.get_name }}
                    </option>
                    {% endfor %}
                </select>
            </div>

            <!-- Price range -->
            <div class="grid grid-cols-2 gap-2">
                <div>
                    <label class="block text-sm font-medium mb-1">Min Price (BAM)</label>
                    <input type="number" name="min_price" value="{{ min_price|default:'' }}"
                           class="w-full px-3 py-2 border rounded-lg" placeholder="0" min="0">
                </div>
                <div>
                    <label class="block text-sm font-medium mb-1">Max Price (BAM)</label>
                    <input type="number" name="max_price" value="{{ max_price|default:'' }}"
                           class="w-full px-3 py-2 border rounded-lg" placeholder="999999" min="0">
                </div>
            </div>

            <div class="flex justify-end gap-2 pt-4">
                <button type="button"
                        _="on click remove #save-search-modal"
                        class="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg">
                    Cancel
                </button>
                <button type="submit"
                        class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                    Save Alert
                </button>
            </div>
        </form>
    </div>
</div>
```

---

### T8: Router Registration

**File:** `src/telegram_bot/main.py`

**Changes - line 45:**
```python
from telegram_bot.handlers import login_router, ad_create_router, alerts_router
```

**Changes - line 48:**
```python
dp.include_router(alerts_router)
```

---

## Pydantic Schemas (DTO Layer)

**File:** `src/telegram_bot/schemas/saved_search.py`

```python
# src/telegram_bot/schemas/saved_search.py
"""Pydantic v2 DTOs for saved search input validation."""

from typing import Annotated

from pydantic import BaseModel, Field


class SavedSearchQueryPayload(BaseModel):
    """Validated search query input."""

    query: Annotated[
        str | None,
        Field(max_length=200, description="Search query string"),
    ] = None


class SavedSearchPricePayload(BaseModel):
    """Validated price range input."""

    min_price: Annotated[
        int | None,
        Field(ge=0, le=1000000, description="Minimum price in BAM"),
    ] = None
    max_price: Annotated[
        int | None,
        Field(ge=0, le=1000000, description="Maximum price in BAM"),
    ] = None
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Telegram delivery failures | Catch `TelegramBadRequest`, `TelegramForbidden`; log and skip user |
| Duplicate notifications | `UniqueConstraint` on `(saved_search, ad)` + `ignore_conflicts=True` |
| Missing chat_id | Check `user.chat_id` before sending; log warning if missing |
| Query performance | Filter PUBLISHED ads only; use EXISTS subquery for notified check |
| Translation failures | Reuse existing `translate_query_bs_to_ru` with circuit-breaker |
| Concurrent runs | Advisory lock `ALERT_DELIVERY_TASK` prevents overlap |

---

## Verification Checklist

- [ ] `uv run python manage.py migrate` runs successfully
- [ ] `select_related` and `prefetch_related` prevent N+1 queries
- [ ] `SavedSearch` with `is_active=False` excluded from delivery
- [ ] Ads in `SavedSearchNotification` excluded from future matches
- [ ] Telegram handler fails gracefully if user has no `chat_id`
- [ ] Management command logs total sent count
- [ ] Modal template submits via HTMX to correct endpoint
- [ ] Advisory lock prevents concurrent command runs
- [ ] `SEARCH_ALERT_MATCHED` event recorded for each alert match

---

## File Summary

| Task | File Path |
|------|-----------|
| T1 | `src/backend/apps/search/models/__init__.py` |
| T1 | `src/backend/apps/search/models/saved_search.py` |
| T2 | `src/backend/apps/core/enums.py` (AdvisoryLockId) |
| T3 | `src/backend/apps/search/services/alert_query.py` |
| T4 | `src/backend/apps/core/enums.py` (AnalyticsEventType) |
| T5 | `src/telegram_bot/states.py` (SavedSearchState) |
| T5 | `src/telegram_bot/handlers/alerts.py` |
| T5 | `src/telegram_bot/handlers/__init__.py` |
| T6 | `src/backend/apps/search/management/commands/send_alerts.py` |
| T7 | `src/backend/templates/search/partials/save_search_modal.html` |
| T8 | `src/telegram_bot/main.py` |
| Schemas | `src/telegram_bot/schemas/saved_search.py` |