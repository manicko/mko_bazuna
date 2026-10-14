"""
Tests for the ``contact_<ad_id>`` deep-link rate limiters (09-API-003).

The ``/start contact_<ad_id>`` branch (``handle_contact``) performs a seller
lookup, an ``AnalyticsEvent`` INSERT and an outbound ``send_message`` **to the
seller**. Before this change it carried no limiter at all: the ad id is a dense,
trivially enumerable integer, and ``AccountStateMiddleware`` admits DECLINE
(browse-only) accounts and unregistered ``chat_id`` s to the branch. Any account
could iterate ``contact_1..contact_N`` to flood every seller.

Two independent budgets now refuse **before** any side effect:

- per **buyer** (5 / 600 s), keyed on ``message.from_user.id``;
- per **seller** (20 / 3600 s), keyed on the resolved seller's primary key.

The red cases are behavioural, not "the symbol is missing": the branch had no
limiter, so the failing assertion is the *presence* of the side effects
(``bot.send_message`` called and an ``AnalyticsEvent`` row written). A test that
asserts a limiter's return value in isolation would pass vacuously against the
unrated code path.

Idiom mirrors ``test_contact_us.py``: a ``MagicMock`` message double with an
``AsyncMock`` ``answer``, the real ``LocMemCache`` limiter (cache isolation
provided by the bot conftest's autouse ``_clear_cache_between_tests`` fixture).
Bot tests cannot import the backend conftest, so the async ``seller`` /
``category`` / ``city`` fixtures from ``src/telegram_bot/tests/conftest.py`` are
used, plus the shared ``create_test_ad`` (imported from the backend conftest via
``pythonpath``).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from asgiref.sync import sync_to_async

from apps.ads.models import Ad
from apps.analytics.models import AnalyticsEvent
from apps.categories.models import Category
from apps.core.enums import AdStatus, AnalyticsEventType
from apps.locations.models import City
from apps.users.models import User
from conftest import create_test_ad
from telegram_bot.handlers.contact import (
    CONTACT_DEEP_LINK_RATE_LIMITED_MESSAGE,
    handle_contact,
)
from telegram_bot.services.rate_limit import (
    CONTACT_BUYER_RATE_LIMIT_REQUESTS,
    CONTACT_SELLER_RATE_LIMIT_REQUESTS,
    check_contact_deep_link_buyer_rate_limit,
    check_contact_seller_rate_limit,
)

# Base for synthetic buyer Telegram IDs used to exhaust the per-buyer budget.
# These IDs never correspond to real User rows — they are ``from_user.id``
# values passed to the rate limiter, not DB lookups.
_BUYER_ID_BASE = 800_000_000

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
    pytest.mark.concurrent,
]
pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))


# ---------------------------------------------------------------------------
# Doubles and helpers
# ---------------------------------------------------------------------------


def _mock_message(user_id: int, is_bot: bool = False) -> MagicMock:
    """Build a ``Message`` double for ``handle_contact``."""
    message = MagicMock()
    message.from_user = MagicMock()
    message.from_user.id = user_id
    message.from_user.is_bot = is_bot
    message.answer = AsyncMock()
    return message


def _mock_bot() -> MagicMock:
    """Build a ``Bot`` double whose outbound ``send_message`` is awaitable."""
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


async def _contact_event_count() -> int:
    """Return the number of persisted CONTACT_INITIATED analytics rows."""

    def _count() -> int:
        return AnalyticsEvent.objects.filter(
            event_type=AnalyticsEventType.CONTACT_INITIATED
        ).count()

    return await sync_to_async(_count)()


async def _make_ad(seller: User, category: Category, city: City) -> Ad:
    """Create a real PUBLISHED ad from the bot-suite fixtures."""
    return await sync_to_async(create_test_ad)(
        seller, category, city, status=AdStatus.PUBLISHED
    )


async def _make_declined_buyer(telegram_id: int) -> User:
    """Create a DECLINE (browse-only) buyer the middleware admits to this branch."""
    return await sync_to_async(User.objects.create)(
        telegram_id=telegram_id,
        chat_id=telegram_id,
        password="x",
        is_declined=True,
        ads_auto_publish=False,
    )


async def _exhaust_buyer_budget(buyer_telegram_id: int) -> None:
    """Consume the buyer's entire per-buyer contact deep-link budget."""
    for _ in range(CONTACT_BUYER_RATE_LIMIT_REQUESTS):
        assert await check_contact_deep_link_buyer_rate_limit(buyer_telegram_id)


async def _exhaust_seller_budget_from_distinct_buyers(ad_id: int) -> None:
    """Drive ``CONTACT_SELLER_RATE_LIMIT_REQUESTS`` distinct buyers at one ad.

    Each buyer is a fresh ``from_user.id`` with its own untouched per-buyer
    budget, so only the per-seller cap can refuse the final trigger. This is the
    sequence that proves a per-buyer-only implementation is insufficient.
    """
    base = _BUYER_ID_BASE
    for offset in range(CONTACT_SELLER_RATE_LIMIT_REQUESTS):
        message = _mock_message(base + offset)
        bot = _mock_bot()
        assert await handle_contact(message, bot, ad_id) is True
        bot.send_message.assert_awaited_once()


# ---------------------------------------------------------------------------
# RED-1 — the per-buyer cap
# ---------------------------------------------------------------------------


class TestPerBuyerCap:
    """Exhausting one buyer's budget refuses the next trigger with no side effect."""

    @pytest.mark.asyncio
    async def test_red1_over_budget_sends_nothing_and_records_nothing(
        self, seller: User, category: Category, city: City
    ) -> None:
        """RED-1: the 6th trigger from one buyer is refused before any side effect.

        Before the fix this branch had no limiter, so ``send_message`` was
        awaited and a CONTACT_INITIATED row was inserted. Both assertions fail
        on the unrated code path.
        """
        ad = await _make_ad(seller, category, city)
        buyer_id = 700_000_001
        await _exhaust_buyer_budget(buyer_id)

        before = await _contact_event_count()
        message = _mock_message(buyer_id)
        bot = _mock_bot()

        result = await handle_contact(message, bot, ad.id)

        assert result is True
        bot.send_message.assert_not_awaited()
        assert await _contact_event_count() == before
        message.answer.assert_awaited_once()
        assert (
            message.answer.await_args.args[0]
            == CONTACT_DEEP_LINK_RATE_LIMITED_MESSAGE
        )

    @pytest.mark.asyncio
    async def test_under_budget_proceeds(
        self, seller: User, category: Category, city: City
    ) -> None:
        """A buyer within budget reaches the seller and records analytics."""
        ad = await _make_ad(seller, category, city)
        message = _mock_message(700_000_002)
        bot = _mock_bot()

        result = await handle_contact(message, bot, ad.id)

        assert result is True
        bot.send_message.assert_awaited_once()
        assert await _contact_event_count() == 1


# ---------------------------------------------------------------------------
# RED-2 — the per-seller cap, from DISTINCT buyers
# ---------------------------------------------------------------------------


class TestPerSellerCap:
    """The second guard exists: distinct buyers are refused at the seller's cap."""

    @pytest.mark.asyncio
    async def test_red2_distinct_buyers_refused_at_seller_cap(
        self, seller: User, category: Category, city: City
    ) -> None:
        """RED-2: the trigger past the seller cap sends nothing and records nothing.

        A per-buyer-only implementation passes RED-1 and fails here: each buyer
        here is a distinct account with a fresh per-buyer budget, so only the
        per-seller counter can refuse the final trigger.
        """
        ad = await _make_ad(seller, category, city)
        await _exhaust_seller_budget_from_distinct_buyers(ad.id)

        before = await _contact_event_count()
        over_cap_buyer = 800_000_999
        message = _mock_message(over_cap_buyer)
        bot = _mock_bot()

        result = await handle_contact(message, bot, ad.id)

        assert result is True
        bot.send_message.assert_not_awaited()
        assert await _contact_event_count() == before
        assert (
            message.answer.await_args.args[0]
            == CONTACT_DEEP_LINK_RATE_LIMITED_MESSAGE
        )


# ---------------------------------------------------------------------------
# Key independence between the two counters
# ---------------------------------------------------------------------------


class TestKeyIndependence:
    """The per-buyer and per-seller counters do not share a namespace."""

    @pytest.mark.asyncio
    async def test_buyer_budget_does_not_consume_seller_budget(
        self, seller: User, category: Category, city: City
    ) -> None:
        """A buyer exhausting their own budget leaves the seller's budget intact.

        The over-budget trigger is refused by the per-buyer guard *before* the
        seller counter is touched, so another buyer's first trigger still passes.
        """
        ad = await _make_ad(seller, category, city)
        exhausted_buyer = 810_000_001
        await _exhaust_buyer_budget(exhausted_buyer)

        # The exhausted buyer is refused.
        refused = _mock_message(exhausted_buyer)
        refused_bot = _mock_bot()
        assert await handle_contact(refused, refused_bot, ad.id) is True
        refused_bot.send_message.assert_not_awaited()

        # A different buyer's first trigger against the same seller still passes:
        # the seller's budget was never decremented by the refused buyer.
        other = _mock_message(810_000_002)
        other_bot = _mock_bot()
        assert await handle_contact(other, other_bot, ad.id) is True
        other_bot.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_seller_guard_independent_of_contact_us_namespace(self) -> None:
        """Deep-link traffic never drains the contact_us support-desk budget.

        The ``contact_us`` namespace is ``bot_contact_rl``; the new per-buyer
        namespace is distinct, so exhausting the deep-link budget leaves the
        support desk's guard untouched.
        """
        from telegram_bot.services.rate_limit import check_contact_start_rate_limit

        buyer_id = 820_000_001
        await _exhaust_buyer_budget(buyer_id)

        # The same id's contact_us support-desk budget is still available.
        assert await check_contact_start_rate_limit(buyer_id) is True


# ---------------------------------------------------------------------------
# Failure-mode coverage: the DECLINE population the finding is about
# ---------------------------------------------------------------------------


class TestDeclinedAccountCovered:
    """A browse-only DECLINE account admitted to the branch is still refused."""

    @pytest.mark.asyncio
    async def test_declined_buyer_refused_at_cap(
        self, seller: User, category: Category, city: City
    ) -> None:
        """A DECLINE buyer reaching the branch is subject to the per-buyer cap.

        ``AccountStateMiddleware`` admits declined accounts to contact
        deep-links, so this population *can* reach ``handle_contact``. The
        handler does not consult account state, so the limiter covers them.
        """
        ad = await _make_ad(seller, category, city)
        declined = await _make_declined_buyer(830_000_001)
        await _exhaust_buyer_budget(declined.telegram_id)

        before = await _contact_event_count()
        message = _mock_message(declined.telegram_id)
        bot = _mock_bot()

        result = await handle_contact(message, bot, ad.id)

        assert result is True
        bot.send_message.assert_not_awaited()
        assert await _contact_event_count() == before


# ---------------------------------------------------------------------------
# Fail-open on a cache outage (shared ``cache_outage`` fixture from conftest)
#
# The ``cache_outage`` fixture patches the shared cache backend
# (``caches[DEFAULT_CACHE_ALIAS]``) so ``cache.add`` raises
# ``ConnectionInterrupted``.  It is the single source of truth for
# cache-outage simulation across all rate-limit test files (B27-2.2 /
# B28-11.4).
# ---------------------------------------------------------------------------


class TestNewGuardsFailOpen:
    """Both new guards allow the contact when the shared cache is unreachable."""

    @pytest.mark.asyncio
    async def test_buyer_guard_fails_open(self, cache_outage: object) -> None:
        """``check_contact_deep_link_buyer_rate_limit`` allows on cache outage."""
        assert await check_contact_deep_link_buyer_rate_limit(910_000_001) is True

    @pytest.mark.asyncio
    async def test_seller_guard_fails_open(self, cache_outage: object) -> None:
        """``check_contact_seller_rate_limit`` allows on cache outage."""
        assert await check_contact_seller_rate_limit(910_000_002) is True

    @pytest.mark.asyncio
    async def test_buyer_guard_under_outage_reaches_seller(
        self, seller: User, category: Category, city: City, cache_outage: object
    ) -> None:
        """A cache outage does not refuse a legitimate buyer (end-to-end)."""
        ad = await _make_ad(seller, category, city)
        message = _mock_message(910_000_003)
        bot = _mock_bot()

        assert await handle_contact(message, bot, ad.id) is True

        bot.send_message.assert_awaited_once()

