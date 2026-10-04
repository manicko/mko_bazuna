"""
Tests for the web deep-link render rate limiter (contact-us anti-spam, CR-10).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.http import HttpRequest
from django.test import Client
from django.urls import reverse
from django_redis.exceptions import ConnectionInterrupted

from apps.core.services.contact_rate_limit import check_deep_link_render_rate_limit

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the shared LocMemCache so per-IP rate-limit counters don't leak across tests."""
    cache.clear()
    yield
    cache.clear()


def _make_request(ip: str = "127.0.0.1") -> HttpRequest:
    request = HttpRequest()
    request.META["REMOTE_ADDR"] = ip
    return request


class TestDeepLinkRenderRateLimit:
    """Tests for ``check_deep_link_render_rate_limit``."""

    def test_allows_under_limit(self) -> None:
        """First 60 renders from the same IP are allowed."""
        for _ in range(60):
            assert check_deep_link_render_rate_limit(_make_request()) is True

    def test_blocks_after_threshold(self) -> None:
        """61st render within the 10-minute window is rate-limited."""
        for _ in range(60):
            check_deep_link_render_rate_limit(_make_request())
        assert check_deep_link_render_rate_limit(_make_request()) is False

    def test_independent_per_ip(self) -> None:
        """Exhausting one IP's budget does not affect a different IP."""
        for _ in range(60):
            check_deep_link_render_rate_limit(_make_request(ip="10.0.0.1"))
        # 10.0.0.2 is untouched
        assert check_deep_link_render_rate_limit(_make_request(ip="10.0.0.2")) is True

    def test_fails_open_on_cache_outage(self) -> None:
        """A cache outage allows the render instead of raising.

        The failing cache is applied at the guard module's own ``cache`` name
        while it exists, and at ``apps.core.utils.cache.cache`` once the guard
        delegates to the shared helper — so this single test is genuinely RED
        before the fail-open change and GREEN after it.
        """
        import apps.core.services.contact_rate_limit as guard_module

        mock_cache = MagicMock()
        mock_cache.add.side_effect = ConnectionInterrupted(None)

        target = (
            patch.object(guard_module, "cache", mock_cache)
            if hasattr(guard_module, "cache")
            else patch("apps.core.utils.cache.cache", mock_cache)
        )
        with target:
            assert check_deep_link_render_rate_limit(_make_request()) is True

    def test_untrusted_peer_ignores_x_forwarded_for(self) -> None:
        """An untrusted public peer keeps its own key; X-Forwarded-For is ignored.

        The peer gate in ``apps.core.utils.client_ip.get_client_ip`` reads the
        socket peer first and returns it without a header read when the peer is
        not loopback, private, or listed in ``TRUSTED_PROXY_NETWORKS``. A
        public peer that sets ``X-Forwarded-For`` therefore buckets under its own
        address (the old ``X-Forwarded-For``-wins rule is deliberately gone).

        Both addresses must be genuinely public: the TEST-NET ranges report
        ``is_private is True`` in Python 3.14, so a reserved spoofed value would
        be skipped by the forwarded-hop walk and the test would pass even with
        the gate removed — for the wrong reason.
        """
        request = HttpRequest()
        request.META["REMOTE_ADDR"] = "1.2.3.4"
        request.META["HTTP_X_FORWARDED_FOR"] = "8.8.8.8"
        # First call from the peer is allowed, on a fresh counter keyed by the
        # peer address, not the spoofed header value.
        assert check_deep_link_render_rate_limit(request) is True
        assert cache.get("telegram_dl_rl:1.2.3.4") == 1
        assert cache.get("telegram_dl_rl:8.8.8.8") is None

    def test_rate_limit_check_handles_cache_incr_value_error(self) -> None:
        """ValueError from cache.incr (race: key expired between add/incr) →
        counter reset to 1, returns True (graceful degradation)."""
        from unittest.mock import patch

        from apps.core.services.contact_rate_limit import (
            check_deep_link_render_rate_limit,
        )

        cache.clear()
        request = _make_request()

        # First call: cache.add succeeds (creates key, value=1)
        assert check_deep_link_render_rate_limit(request) is True

        # Second call: cache.add fails (key exists), cache.incr raises ValueError
        # (simulating the key expiring between add and incr)
        with patch(
            "apps.core.utils.cache.cache.incr",
            side_effect=ValueError("missing key"),
        ):
            result = check_deep_link_render_rate_limit(request)

        assert result is True
        # Counter was reset to 1 by the except ValueError branch
        assert cache.get("telegram_dl_rl:127.0.0.1") == 1


class TestDeepLinkRenderRateLimitView:
    """View-level 429 wiring for the deep-link render rate limiter."""

    def test_privacy_page_returns_429_when_rate_limited(self) -> None:
        """A pre-exhausted IP budget makes /privacy/ return 429."""
        # Pre-fill the counter to the limit for the test Client's IP.
        cache.set("telegram_dl_rl:127.0.0.1", 60, timeout=600)
        response = Client().get(reverse("core:privacy"))
        assert response.status_code == 429

    def test_ad_detail_returns_429_when_rate_limited(self) -> None:
        """A pre-exhausted IP budget makes the ad detail page return 429."""
        cache.set("telegram_dl_rl:127.0.0.1", 60, timeout=600)
        response = Client().get(reverse("ads:detail", args=[1]))
        assert response.status_code == 429

    def test_listings_returns_429_when_rate_limited_non_hx(self) -> None:
        """Full-page (non-HX) listings renders contact links → rate-limited."""
        cache.set("telegram_dl_rl:127.0.0.1", 60, timeout=600)
        response = Client().get(reverse("ads:listings"))
        assert response.status_code == 429

    def test_listings_not_rate_limited_when_hx_request(self) -> None:
        """HTMX partial renders no contact links → HX-exclusion (CR-10)."""
        cache.set("telegram_dl_rl:127.0.0.1", 60, timeout=600)
        response = Client().get(
            reverse("ads:listings"),
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200

    def test_login_issue_returns_429_when_rate_limited(self) -> None:
        """A pre-exhausted IP budget makes /login/issue/ return 429."""
        cache.set("telegram_dl_rl:127.0.0.1", 60, timeout=600)
        response = Client().get("/login/issue/")
        assert response.status_code == 429
