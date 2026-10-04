"""
Unit tests for :func:`apps.core.utils.cache.bump_rate_limit_window` (09-API-002).

The helper is the single shared body of all seven request-path rate-limit
guards. These tests pin its three outcomes against a controlled cache:

- a healthy cache honours the threshold (``True`` up to and including ``limit``,
  ``False`` past it);
- a ``ValueError`` from ``cache.incr`` (the key expired between ``add`` and
  ``incr``) resets the counter to 1 and reports "allowed";
- ``ConnectionInterrupted`` and a bare ``redis.RedisError`` both fail open
  (report "allowed") instead of raising into the request path.

It lives in its own module — not appended to
``test_site_config_cache_failure.py`` — because it is a different contract
(the write path) and uses a different fake (the shared cache object).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import redis
from django_redis.exceptions import ConnectionInterrupted

from apps.core.utils.cache import bump_rate_limit_window

pytestmark = pytest.mark.unit

_KEY = "test_rl:1.2.3.4"


def _healthy_cache() -> MagicMock:
    """A minimal in-memory fake exposing the ``add``/``incr``/``set`` contract."""
    store: dict[str, int] = {}
    fake = MagicMock()

    def _add(key: str, value: int, timeout: int) -> bool:
        if key in store:
            return False
        store[key] = value
        return True

    def _incr(key: str) -> int:
        try:
            store[key] += 1
        except KeyError as exc:
            raise ValueError(f"key {key} not found") from exc
        return store[key]

    def _set(key: str, value: int, timeout: int) -> None:
        store[key] = value

    fake.add.side_effect = _add
    fake.incr.side_effect = _incr
    fake.set.side_effect = _set
    fake.store = store
    return fake


class TestHealthyCache:
    """A reachable cache enforces the window semantics unchanged."""

    def test_allows_up_to_limit_then_refuses(self) -> None:
        """``limit`` calls are allowed; the next one is refused."""
        fake = _healthy_cache()
        with patch("apps.core.utils.cache.cache", fake):
            for _ in range(3):
                assert bump_rate_limit_window(_KEY, limit=3, period=60) is True
            assert bump_rate_limit_window(_KEY, limit=3, period=60) is False

    def test_counter_matches_calls(self) -> None:
        """The cache holds one entry per call, incremented in place."""
        fake = _healthy_cache()
        with patch("apps.core.utils.cache.cache", fake):
            bump_rate_limit_window(_KEY, limit=3, period=60)
            bump_rate_limit_window(_KEY, limit=3, period=60)
        assert fake.store[_KEY] == 2


class TestValueErrorReset:
    """A ``ValueError`` from ``incr`` resets the window and allows the call."""

    def test_value_error_resets_to_one(self) -> None:
        """``cache.incr`` raising ``ValueError`` triggers ``cache.set(key, 1)``."""
        fake = MagicMock()
        fake.add.return_value = False
        fake.incr.side_effect = ValueError("missing key")

        with patch("apps.core.utils.cache.cache", fake):
            assert bump_rate_limit_window(_KEY, limit=5, period=600) is True

        fake.set.assert_called_once_with(_KEY, 1, timeout=600)


class TestCacheOutageFailsOpen:
    """An unreachable cache allows the caller rather than raising."""

    def test_connection_interrupted_fails_open(self) -> None:
        """``ConnectionInterrupted`` from ``add`` reports "allowed"."""
        fake = MagicMock()
        fake.add.side_effect = ConnectionInterrupted(None)

        with patch("apps.core.utils.cache.cache", fake):
            assert bump_rate_limit_window(_KEY, limit=5, period=600) is True

    def test_redis_error_fails_open(self) -> None:
        """A bare ``redis.RedisError`` from ``add`` reports "allowed"."""
        fake = MagicMock()
        fake.add.side_effect = redis.RedisError("redis down")

        with patch("apps.core.utils.cache.cache", fake):
            assert bump_rate_limit_window(_KEY, limit=5, period=600) is True
