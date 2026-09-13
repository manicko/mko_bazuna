"""
Tests for the Telegram bot rate-limit services.

Mirrors the ``TestRateLimitService`` idiom (apps/search/tests/test_autocomplete.py)
for the bot-side limiters.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterator

import pytest
from django.core.cache import cache

from telegram_bot.services.rate_limit import (
    check_contact_start_rate_limit,
    check_upload_rate_limit,
)

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.integration,
    pytest.mark.asyncio,
]


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    cache.clear()
    yield
    cache.clear()


class TestContactStartRateLimit:
    """Tests for ``check_contact_start_rate_limit``."""

    async def test_allows_under_limit(self) -> None:
        """First 5 contact-start triggers are allowed."""
        for _ in range(5):
            assert await check_contact_start_rate_limit(123) is True

    async def test_blocks_after_threshold(self) -> None:
        """6th contact-start trigger within the window is rate-limited."""
        for _ in range(5):
            assert await check_contact_start_rate_limit(456) is True
        assert await check_contact_start_rate_limit(456) is False

    async def test_independent_per_user(self) -> None:
        """Rate-limit counters are isolated per Telegram user_id."""
        for _ in range(5):
            assert await check_contact_start_rate_limit(789) is True
        # User 999 is unaffected by user 789's window.
        assert await check_contact_start_rate_limit(999) is True

    async def test_custom_limit_and_period(self) -> None:
        """limit/period kwargs override the defaults."""
        for _ in range(3):
            assert await check_contact_start_rate_limit(111, limit=3, period=600) is True
        assert await check_contact_start_rate_limit(111, limit=3, period=600) is False


def test_rate_limit_functions_are_async_callable() -> None:
    """Both rate-limit functions are async (awaitable coroutine functions).

    Guards against regression: a future change must not accidentally make either
    function synchronous again, which would block the bot event loop on cache I/O.
    """
    assert inspect.iscoroutinefunction(check_upload_rate_limit)
    assert inspect.iscoroutinefunction(check_contact_start_rate_limit)
