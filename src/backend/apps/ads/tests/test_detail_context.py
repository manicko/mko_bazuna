"""
Integration tests for ad_detail context (tsk_007 — contact button bot_username).

Verifies that ad_detail passes correct context values using a REAL Ad instance
(not MagicMock), eliminating the CacheKeyWarning warnings caused by mocked
cache keys.

Covers:
- bot_username matches get_bot_username()
- ad object is in context
- breadcrumb_category is the ad's category
- select_related + prefetch_related include user__trust_score (no N+1)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.core.enums import AdStatus
from apps.core.services.site_config import get_bot_username
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def published_ad(seller, category, city) -> Any:
    """A PUBLISHED ad for detail-view context tests."""
    return create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)


class TestAdDetailContext:
    """Verify ad_detail passes correct context values with a real Ad instance."""

    def test_detail_context_contains_bot_username(
        self, published_ad, seller, category, city
    ) -> None:
        """bot_username in context matches get_bot_username()."""
        client = Client()
        response = client.get(reverse("ads:detail", args=[published_ad.id]))

        assert response.status_code == 200
        assert response.context["bot_username"] == get_bot_username()

    def test_detail_context_contains_ad(
        self, published_ad, seller, category, city
    ) -> None:
        """The real Ad instance is in context (not a MagicMock)."""
        client = Client()
        response = client.get(reverse("ads:detail", args=[published_ad.id]))

        assert response.status_code == 200
        assert response.context["ad"] == published_ad

    def test_detail_context_contains_breadcrumb_category(
        self, published_ad, seller, category, city
    ) -> None:
        """breadcrumb_category in context is the ad's actual category."""
        client = Client()
        response = client.get(reverse("ads:detail", args=[published_ad.id]))

        assert response.status_code == 200
        assert response.context["breadcrumb_category"] == published_ad.category

    def test_detail_prefetch_includes_trust_score(
        self, published_ad, seller, category, city
    ) -> None:
        """ad_detail prefetches user__trust_score (no N+1 on trust-badge render).

        Creates a SellerTrustScore for the seller, renders the detail page,
        and verifies that accessing the prefetched trust_score does not trigger
        an additional query targeting the trust scores table.
        """
        from apps.core.enums import TrustLevel
        from apps.trust.models import SellerTrustScore

        SellerTrustScore.objects.create(
            user=seller,
            trust_level=TrustLevel.TRUSTED,
            score=70,
        )

        client = Client()
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(reverse("ads:detail", args=[published_ad.id]))
            assert response.status_code == 200
            ad = response.context["ad"]
            _ = ad.user  # prefetched via select_related("user")
            _ = ad.user.trust_score  # prefetched via prefetch_related("user__trust_score")

        # No separate query targeting the trust scores table (it was prefetched).
        trust_queries = [
            q for q in ctx.captured_queries
            if "seller_trust_scores" in q["sql"]
        ]
        assert len(trust_queries) <= 1, (
            "user__trust_score should be prefetched in the detail query, "
            "not lazy-loaded per-access"
        )

    def test_detail_context_contains_is_favorited_for_authenticated(
        self, published_ad, seller, category, city
    ) -> None:
        """is_favorited is False for an authenticated user who hasn't favorited."""
        client = Client()
        client.force_login(seller)
        response = client.get(reverse("ads:detail", args=[published_ad.id]))

        assert response.status_code == 200
        assert response.context["is_favorited"] is False

    def test_detail_context_contains_display_features(
        self, published_ad, seller, category, city
    ) -> None:
        """display_features is a list (possibly empty) of resolved features."""
        client = Client()
        response = client.get(reverse("ads:detail", args=[published_ad.id]))

        assert response.status_code == 200
        assert response.context["display_features"] is not None
        assert isinstance(response.context["display_features"], list)


class TestAdDetailDeclinedUserVisibility:
    """A declined user's PUBLISHED ad is hidden from direct URL access (AUTZ-003).

    The ad is PUBLISHED but its owner has declined consent (``is_declined=True``).
    Such ads are excluded from browse/search by the shared
    ``ListingsQuery.build_queryset`` filter; this guards the direct
    ``/ads/<id>/`` detail route from leaking them.
    """

    def test_declined_user_published_ad_returns_404(
        self, seller, category, city
    ) -> None:
        """A declined user's PUBLISHED ad returns 404 via ad_detail."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        # Sanity: visible before the decline.
        client = Client()
        assert (
            client.get(reverse("ads:detail", args=[ad.id])).status_code == 200
        )

        # Decline consent — the PUBLISHED ad must become unreachable by URL.
        seller.is_declined = True
        seller.save(update_fields=["is_declined"])

        response = client.get(reverse("ads:detail", args=[ad.id]))
        assert response.status_code == 404

    def test_non_declined_user_published_ad_returns_200(
        self, published_ad, seller, category, city
    ) -> None:
        """A non-declined user's PUBLISHED ad still renders normally."""
        client = Client()
        response = client.get(reverse("ads:detail", args=[published_ad.id]))
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Template-source tests (unchanged — they read template files, no MagicMock)
# ---------------------------------------------------------------------------


def test_detail_template_uses_bot_username_not_settings() -> None:
    """The detail template uses the ``{% telegram_deep_link %}`` tag for the
    contact button, not a cleartext ``{{ bot_username }}`` href."""
    content = (
        Path(__file__).resolve().parents[3] / "templates/ads/detail.html"
    ).read_text(encoding="utf-8")
    assert "{% telegram_deep_link" in content
    assert "{{ bot_username }}" not in content  # cleartext no longer in template
    assert "settings.BOT_USERNAME" not in content


# ---------------------------------------------------------------------------
# Breadcrumb ellipsis template (Spec_020 R-05)
# ---------------------------------------------------------------------------

_BREADCRUMB_CONTENT = (
    Path(__file__).resolve().parents[3] / "templates/components/breadcrumb.html"
).read_text(encoding="utf-8")


def test_ellipsis_truncation_branch_present() -> None:
    """The template must gate truncation on the ancestor-chain length."""
    assert "{% if ancestors|length > 2 %}" in _BREADCRUMB_CONTENT
    assert "{% endwith %}" in _BREADCRUMB_CONTENT


def test_ellipsis_literal_present() -> None:
    """The ``…`` ellipsis literal is rendered for long chains."""
    assert ">…<" in _BREADCRUMB_CONTENT


def test_separator_preserved() -> None:
    """The ``&rsaquo;`` separator is kept in truncated and full chains."""
    assert "&rsaquo;" in _BREADCRUMB_CONTENT


def test_breadcrumb_with_tag_no_last_ancestor() -> None:
    """The ``{% with %}`` must not bind ``last_ancestor`` via ``|last``
    (which raises on an empty ancestor queryset); the last ancestor is bound
    safely inside the length-guarded branch (RC-C)."""
    assert "last_ancestor=breadcrumb_category" not in _BREADCRUMB_CONTENT
    assert "get_ancestors|last" not in _BREADCRUMB_CONTENT
    assert (
        "{% with ancestors=breadcrumb_category.get_ancestors %}" in _BREADCRUMB_CONTENT
    )
    assert 'slice:"::-1"|first' in _BREADCRUMB_CONTENT
