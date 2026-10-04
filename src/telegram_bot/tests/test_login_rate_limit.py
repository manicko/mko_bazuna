"""
Unit tests for ``check_login_rate_limit`` (EXT-007).

Covers the per-user sliding-window login claim limiter using the real
LocMemCache (no DB rows) — mirrors the ``TestContactStartRateLimit`` idiom
in ``test_rate_limit_service.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import DEFAULT_CACHE_ALIAS, cache, caches
from django_redis.exceptions import ConnectionInterrupted

from telegram_bot.services.rate_limit import (
    LOGIN_RATE_LIMIT_REQUESTS,
    check_login_rate_limit,
)

pytestmark = [pytest.mark.unit]


class TestCheckLoginRateLimit:
    """Tests for ``check_login_rate_limit`` (EXT-007)."""

    @pytest.mark.asyncio
    async def test_check_login_rate_limit_allows_under_threshold(self) -> None:
        """First 10 login claims within the window are allowed."""
        for _ in range(LOGIN_RATE_LIMIT_REQUESTS):
            assert await check_login_rate_limit(123) is True

    @pytest.mark.asyncio
    async def test_check_login_rate_limit_blocks_over_threshold(self) -> None:
        """11th login claim within the window is rate-limited."""
        for _ in range(LOGIN_RATE_LIMIT_REQUESTS):
            assert await check_login_rate_limit(456) is True
        assert await check_login_rate_limit(456) is False

    @pytest.mark.asyncio
    async def test_check_login_rate_limit_resets_after_window(self) -> None:
        """After cache expiry, the user gets a fresh budget."""
        # Fill the budget to the limit.
        for _ in range(LOGIN_RATE_LIMIT_REQUESTS):
            assert await check_login_rate_limit(789) is True
        assert await check_login_rate_limit(789) is False

        # Simulate key expiry (cache timeout elapsed) by deleting the key.
        cache.delete("bot_login_rl:789")

        # Fresh budget available again.
        assert await check_login_rate_limit(789) is True

    @pytest.mark.asyncio
    async def test_check_login_rate_limit_fails_open_on_cache_outage(self) -> None:
        """A Redis outage allows the login claim rather than raising.

        The seam is the shared cache backend (``caches[DEFAULT_CACHE_ALIAS]``),
        not a module-level ``cache`` name. ``django.core.cache.cache`` is a
        single proxy over one backend, so every guard module's ``cache`` global
        is the same object; patching the backend is invariant to which module
        holds a reference and cannot be neutralised by the guard gaining, losing
        or duplicating a ``cache`` import.
        """
        outage = MagicMock()
        outage.add.side_effect = ConnectionInterrupted(None)

        with patch.object(caches[DEFAULT_CACHE_ALIAS], "add", outage.add):
            assert await check_login_rate_limit(123) is True
