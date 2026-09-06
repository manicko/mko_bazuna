"""
Tests for the Telegram bot rate-limit services.

Mirrors the ``TestRateLimitService`` idiom (apps/search/tests/test_autocomplete.py)
for the bot-side limiters.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from django.core.cache import cache

from telegram_bot.services.rate_limit import check_contact_start_rate_limit

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    cache.clear()
    yield
    cache.clear()


class TestContactStartRateLimit:
    """Tests for ``check_contact_start_rate_limit``."""

    def test_allows_under_limit(self) -> None:
        """First 5 contact-start triggers are allowed."""
        for _ in range(5):
            assert check_contact_start_rate_limit(123) is True

    def test_blocks_after_threshold(self) -> None:
        """6th contact-start trigger within the window is rate-limited."""
        for _ in range(5):
            assert check_contact_start_rate_limit(456) is True
        assert check_contact_start_rate_limit(456) is False

    def test_independent_per_user(self) -> None:
        """Rate-limit counters are isolated per Telegram user_id."""
        for _ in range(5):
            assert check_contact_start_rate_limit(789) is True
        # User 999 is unaffected by user 789's window.
        assert check_contact_start_rate_limit(999) is True

    def test_custom_limit_and_period(self) -> None:
        """limit/period kwargs override the defaults."""
        for _ in range(3):
            assert check_contact_start_rate_limit(111, limit=3, period=600) is True
        assert check_contact_start_rate_limit(111, limit=3, period=600) is False
