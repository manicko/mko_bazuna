"""Tests for the ``GET /api/v1/ads/{id}/`` JSON detail endpoint (S1.5).

Browserless (``Client()``) coverage of the ad-detail read:

- **Audience matrix** — a published + visible ad answers 200 with the structured
  payload; a missing id and every audience-blocked cause (draft / unpublished,
  withdrawn-consent seller, banned seller, deleted seller, declined seller)
  answer the **identical** uniform 404 problem document (no existence leak).
- **Side-effect parity** — an API detail GET records ``AD_VIEWED`` exactly as an
  HTML detail GET does (same event, same seller attribution).
- **Session favorites state** — anonymous reads ``False``; a logged-in
  favorite reads ``True``; a logged-in non-favorite reads ``False`` (mirrors the
  HTML detail view).
- **Media URLs only** — the payload carries URL strings, never binary/base64.
- **429 problem** — an exhausted ``API_PUBLIC_READ`` namespace yields the RFC
  9457 ``rate_limited`` problem + ``Retry-After``.
- **Contact deep-link** — ``contact_url`` present only for a contactable seller
  and assembled from the shared bot username.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.ads.models import AdFavorite
from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AdStatus, AnalyticsEventType
from apps.core.services.site_config import get_bot_username
from apps.core.utils.problem import (
    PROBLEM_CONTENT_TYPE,
    RETRY_AFTER_HEADER,
    TYPE_RATE_LIMITED,
)
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

ENDPOINT = "/api/v1/ads/{ad_id}/"


def _url(ad_id: int) -> str:
    """Build the detail endpoint URL for *ad_id*."""
    return ENDPOINT.format(ad_id=ad_id)


def _get(ad_id: int, client: Client | None = None) -> Any:
    """GET the detail endpoint and assert a JSON/problem JSON content type."""
    response = (client or Client()).get(_url(ad_id))
    content_type = response.headers.get("Content-Type", "")
    assert content_type.startswith("application/")
    return response


class TestAudienceMatrix:
    """Published + visible → 200; every miss → one uniform 404 problem."""

    def test_published_visible_ad_returns_structured_payload(
        self, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        response = _get(ad.id)

        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == ad.id
        assert payload["title"] == "Test Ad"
        assert payload["description"] == "Test description"
        assert payload["city"]["slug"] == city.slug
        assert payload["category"]["slug"] == category.slug
        assert payload["status"] == AdStatus.PUBLISHED
        assert payload["absolute_url"] == ad.get_absolute_url()

    def test_missing_id_returns_uniform_404(
        self, seller, category, city
    ) -> None:
        response = _get(999999)

        assert response.status_code == 404
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        payload = response.json()
        assert payload["type"] == "not_found"
        assert payload["status"] == 404

    def test_all_404_causes_share_identical_shape(
        self, seller, category, city
    ) -> None:
        """Missing, draft, withdrawn and banned all answer the same document."""
        draft = create_test_ad(seller, category, city, status=AdStatus.DRAFT)

        withdrawn = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        seller.consent_revoked_at = timezone.now()
        seller.save(update_fields=["consent_revoked_at"])

        banned = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        shapes = []
        for ad_id in (999999, draft.id, withdrawn.id):
            response = _get(ad_id)
            assert response.status_code == 404
            assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
            shapes.append(response.json())

        # Now ban the seller and re-check the remaining ad.
        seller.consent_revoked_at = None
        seller.is_banned = True
        seller.save(update_fields=["consent_revoked_at", "is_banned"])
        banned_response = _get(banned.id)
        assert banned_response.status_code == 404
        shapes.append(banned_response.json())

        # Every 404 cause produced a byte-identical problem document.
        first = shapes[0]
        for shape in shapes[1:]:
            assert shape == first

    def test_deleted_seller_ad_returns_404(
        self, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        seller.is_deleted = True
        seller.save(update_fields=["is_deleted"])

        assert _get(ad.id).status_code == 404

    def test_declined_seller_ad_returns_404(
        self, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        seller.is_declined = True
        seller.save(update_fields=["is_declined"])

        assert _get(ad.id).status_code == 404

    def test_unpublished_statuses_return_404(
        self, seller, category, city
    ) -> None:
        for status in (AdStatus.ARCHIVED, AdStatus.ON_MODERATION_FAILED):
            ad = create_test_ad(seller, category, city, status=status)
            assert _get(ad.id).status_code == 404


class TestSideEffectParity:
    """An API detail GET records ``AD_VIEWED`` exactly as the HTML GET does."""

    def test_api_get_records_ad_viewed_like_html(
        self, seller, category, city
    ) -> None:
        html_ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        api_ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        Client().get(reverse("ads:detail", args=[html_ad.id]))
        _get(api_ad.id)

        html_events = AnalyticsEvent.objects.filter(
            event_type=AnalyticsEventType.AD_VIEWED, ad_id=html_ad.id
        )
        api_events = AnalyticsEvent.objects.filter(
            event_type=AnalyticsEventType.AD_VIEWED, ad_id=api_ad.id
        )
        assert html_events.count() == 1
        assert api_events.count() == 1

        # Same seller attribution on both sides.
        assert html_events.get().user_id == seller.id
        assert api_events.get().user_id == seller.id

    def test_404_does_not_record_event(self, seller, category, city) -> None:
        before = AnalyticsEvent.objects.filter(
            event_type=AnalyticsEventType.AD_VIEWED
        ).count()
        _get(999999)
        after = AnalyticsEvent.objects.filter(
            event_type=AnalyticsEventType.AD_VIEWED
        ).count()
        assert after == before


class TestFavoritesState:
    """The payload's ``is_favorited`` mirrors the HTML detail view semantics."""

    def test_anonymous_reads_false(self, seller, category, city) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        payload = _get(ad.id).json()
        assert payload["is_favorited"] is False

    def test_logged_in_with_favorite_reads_true(
        self, seller, user, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        AdFavorite.objects.create(ad=ad, user=user)

        client = Client()
        client.force_login(user)
        payload = _get(ad.id, client).json()
        assert payload["is_favorited"] is True

    def test_logged_in_without_favorite_reads_false(
        self, seller, user, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        client = Client()
        client.force_login(user)
        payload = _get(ad.id, client).json()
        assert payload["is_favorited"] is False


class TestMediaUrlsOnly:
    """The payload exposes media as URL strings only (never bytes/base64)."""

    def test_image_urls_are_url_strings(self, seller, category, city) -> None:
        from apps.ads.models import AdImage

        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        AdImage.objects.create(ad=ad, image="11111111-1111-4111-8111-111111111111.jpg")

        payload = _get(ad.id).json()
        assert payload["image_urls"]
        for image_url in payload["image_urls"]:
            assert isinstance(image_url, str)
            assert image_url.startswith("/media/")
            assert "base64" not in image_url


class TestContactDeepLink:
    """``contact_url`` is present only for a contactable seller."""

    def test_contactable_seller_gets_deep_link(
        self, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        payload = _get(ad.id).json()
        assert payload["contact_url"] == (
            f"https://t.me/{get_bot_username()}?start=contact_{ad.id}"
        )

    def test_seller_without_telegram_id_gets_null(
        self, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        seller.telegram_id = None
        seller.save(update_fields=["telegram_id"])

        # telegram_id None is also an audience-blocking account state? No: a
        # published ad whose seller merely lacks a telegram_id is still visible;
        # only the contact deep-link is withheld.
        payload = _get(ad.id).json()
        assert payload["contact_url"] is None

    def test_withdrawn_consent_seller_gets_null(
        self, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        seller.consent_revoked_at = timezone.now()
        seller.save(update_fields=["consent_revoked_at"])

        # The ad is audience-blocked for consent-revoked sellers, so the whole
        # detail read is a 404 rather than a payload with a null link.
        assert _get(ad.id).status_code == 404


class TestRateLimitProblem:
    """Exhausting ``API_PUBLIC_READ`` yields the RFC 9457 429 problem."""

    def test_over_budget_returns_rate_limited_problem(
        self, seller, category, city, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "apps.ads.views.api.detail.rate_limit_check",
            lambda *a, **k: False,
        )
        response = Client().get(_url(1))

        assert response.status_code == 429
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.headers.get(RETRY_AFTER_HEADER) == "60"
        payload = response.json()
        assert payload["type"] == TYPE_RATE_LIMITED
        assert payload["status"] == 429

    def test_under_budget_is_allowed(self, seller, category, city) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        assert _get(ad.id).status_code == 200


class TestReverseSmoke:
    """The route reverses under the ``ads_api`` namespace."""

    def test_reverse_ad_detail(self) -> None:
        assert reverse("ads_api:ad_detail", args=[7]) == _url(7)
