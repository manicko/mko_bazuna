"""
Tests for the web deep-link render rate limiter (contact-us anti-spam, CR-10).
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.http import HttpRequest
from django.test import Client
from django.urls import reverse

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

    def test_x_forwarded_for_takes_precedence(self) -> None:
        """X-Forwarded-For (nginx) is preferred over REMOTE_ADDR."""
        request = HttpRequest()
        request.META["REMOTE_ADDR"] = "10.0.0.1"
        request.META["HTTP_X_FORWARDED_FOR"] = "203.0.113.5"
        # First call from the XFF IP is allowed (fresh counter).
        assert check_deep_link_render_rate_limit(request) is True


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
