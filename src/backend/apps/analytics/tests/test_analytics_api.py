"""Tests for the ``GET /api/v1/trust/seller/`` and ``…/moderation/`` reads (S2.6).

Browserless (``Client()``) coverage of the two trust-dashboard reads:

- **Auth matrix** — seller: anonymous → 401 problem (the HTML mirror redirects to
  login; the API answers a problem document), session → 200. Moderation:
  anonymous → 401, non-staff → 403, staff → 200. Every refusal carries **no**
  ``WWW-Authenticate`` header. Wrong method → 405.
- **Payload parity** — the JSON payload equals the HTML dashboard context for the
  same fixtures (score, level, daily rows, totals; moderation stats, queue size,
  performance, rejection reasons, window).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

import pytest
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.analytics.models import AnalyticsEvent, DailyAdMetrics
from apps.core.enums import AdStatus, AnalyticsEventType, TrustLevel
from apps.core.utils.problem import PROBLEM_CONTENT_TYPE
from conftest import create_test_ad, make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

SELLER_ENDPOINT = "/api/v1/trust/seller/"
MODERATION_ENDPOINT = "/api/v1/trust/moderation/"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dashboard_seller(seller, category, city) -> dict:
    """A seller with one published ad (mirrors the analytics view test fixture)."""
    ad = create_test_ad(
        seller, category, city, title="Trust Ad", status=AdStatus.PUBLISHED
    )
    return {"seller": seller, "ad": ad}


@pytest.fixture(autouse=True)
def _locmem_cache() -> Iterator[None]:
    """Apply the locmem cache + staticfiles storage the dashboards use."""
    with override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            },
        },
        STORAGES={
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
            },
        },
    ):
        yield


# ---------------------------------------------------------------------------
# Seller dashboard — auth + payload
# ---------------------------------------------------------------------------


class TestSellerDashboardApiAuth:
    """Session-gated seller read: anon → 401 problem, session → 200."""

    def test_anonymous_returns_401_problem_no_challenge(self) -> None:
        response = Client().get(SELLER_ENDPOINT)

        assert response.status_code == 401
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "unauthenticated"
        assert "WWW-Authenticate" not in response.headers

    def test_authenticated_returns_200(self, dashboard_seller) -> None:
        client = Client()
        client.force_login(dashboard_seller["seller"])
        response = client.get(SELLER_ENDPOINT)
        assert response.status_code == 200

    def test_wrong_method_returns_405(self, dashboard_seller) -> None:
        client = Client()
        client.force_login(dashboard_seller["seller"])
        response = client.post(SELLER_ENDPOINT)

        assert response.status_code == 405
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "method_not_allowed"
        assert response.headers.get("Allow") == "GET"
        assert "WWW-Authenticate" not in response.headers


class TestSellerDashboardApiPayload:
    """The JSON payload equals the HTML dashboard context for the same fixtures."""

    def test_payload_matches_html_context(self, dashboard_seller) -> None:
        client = Client()
        client.force_login(dashboard_seller["seller"])

        payload = client.get(SELLER_ENDPOINT).json()
        context = client.get(
            reverse("analytics:seller_trust_dashboard")
        ).context

        assert payload["trust_score"] == round(context["trust_score"], 1)
        assert payload["trust_level"] == context["trust_level"].value
        assert payload["total_views"] == context["total_views"]
        assert payload["total_contacts"] == context["total_contacts"]
        assert payload["daily_metrics"] == [
            {
                "date": m.date.isoformat(),
                "ad_id": m.ad_id,
                "views_count": m.views_count,
                "contacts_count": m.contacts_count,
                "trust_score": m.trust_score,
                "avg_response_time": m.avg_response_time,
            }
            for m in context["daily_metrics"]
        ]

    def test_default_fixture_score_and_level(self, dashboard_seller) -> None:
        """One published ad → score 60.0, VERIFIED band (matches HTML test)."""
        client = Client()
        client.force_login(dashboard_seller["seller"])
        payload = client.get(SELLER_ENDPOINT).json()

        assert payload["trust_score"] == 60.0
        assert payload["trust_level"] == TrustLevel.VERIFIED.value
        assert payload["daily_metrics"] == []
        assert payload["total_views"] == 0
        assert payload["total_contacts"] == 0

    def test_daily_metrics_totals(self, dashboard_seller) -> None:
        client = Client()
        client.force_login(dashboard_seller["seller"])
        DailyAdMetrics.objects.create(
            ad=dashboard_seller["ad"],
            date=timezone.now().date() - timedelta(days=1),
            views_count=5,
            contacts_count=2,
        )

        payload = client.get(SELLER_ENDPOINT).json()

        assert payload["total_views"] == 5
        assert payload["total_contacts"] == 2
        assert len(payload["daily_metrics"]) == 1
        row = payload["daily_metrics"][0]
        assert row["ad_id"] == dashboard_seller["ad"].id
        assert row["views_count"] == 5
        assert row["contacts_count"] == 2


# ---------------------------------------------------------------------------
# Moderation dashboard — auth + payload
# ---------------------------------------------------------------------------


@pytest.fixture
def moderation_context(seller, category, city) -> dict:
    """Staff + superuser + one approved moderation event (mirrors the view test)."""
    staff_user = make_user(telegram_id=990312002, is_staff=True)
    other_user = make_user(telegram_id=990312004)

    approved_ad = create_test_ad(
        other_user,
        category,
        city,
        title="Mod Approved",
        status=AdStatus.PUBLISHED,
    )
    AnalyticsEvent.objects.create(
        event_type=AnalyticsEventType.MODERATION_APPROVED,
        ad=approved_ad,
        timestamp=timezone.now() - timedelta(hours=2),
    )

    return {
        "staff_user": staff_user,
        "seller": other_user,
        "ad_approved": approved_ad,
    }


class TestModerationDashboardApiAuth:
    """Staff-gated moderation read: 401 anon / 403 non-staff / 405 wrong method."""

    def test_anonymous_returns_401_problem_no_challenge(self, moderation_context) -> None:
        response = Client().get(MODERATION_ENDPOINT)

        assert response.status_code == 401
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "unauthenticated"
        assert "WWW-Authenticate" not in response.headers

    def test_non_staff_returns_403_problem_no_challenge(
        self, moderation_context
    ) -> None:
        client = Client()
        client.force_login(moderation_context["seller"])
        response = client.get(MODERATION_ENDPOINT)

        assert response.status_code == 403
        assert response.json()["type"] == "forbidden"
        assert "WWW-Authenticate" not in response.headers

    def test_staff_returns_200(self, moderation_context) -> None:
        client = Client()
        client.force_login(moderation_context["staff_user"])
        response = client.get(MODERATION_ENDPOINT)
        assert response.status_code == 200

    def test_wrong_method_returns_405(self, moderation_context) -> None:
        client = Client()
        client.force_login(moderation_context["staff_user"])
        response = client.post(MODERATION_ENDPOINT)

        assert response.status_code == 405
        assert response.json()["type"] == "method_not_allowed"
        assert "WWW-Authenticate" not in response.headers


class TestModerationDashboardApiPayload:
    """The JSON payload equals the HTML dashboard context for the same fixtures."""

    def test_payload_matches_html_context(self, moderation_context) -> None:
        client = Client()
        client.force_login(moderation_context["staff_user"])

        payload = client.get(MODERATION_ENDPOINT).json()
        context = client.get(reverse("analytics:moderation_analytics")).context

        assert payload["stats"] == dict(context["stats"])
        assert payload["pending_queue_size"] == context["pending_queue_size"]
        assert payload["moderator_performance"] == [
            dict(row) for row in context["moderator_performance"]
        ]
        assert payload["rejection_reasons"] == dict(context["rejection_reasons"])
        assert payload["days"] == context["days"] == 30

    def test_stats_reflect_real_approved_event(self, moderation_context) -> None:
        """The approved event created by the fixture is counted (no patching)."""
        client = Client()
        client.force_login(moderation_context["staff_user"])
        payload = client.get(MODERATION_ENDPOINT).json()

        assert payload["stats"]["approved"] == 1
        assert "avg_time_to_moderate" in payload["stats"]


def test_analytics_api_namespace_reverses() -> None:
    """The route namespace resolves without colliding with the HTML one."""
    assert reverse("analytics_api:seller") == "/api/v1/trust/seller/"
    assert reverse("analytics_api:moderation") == "/api/v1/trust/moderation/"
