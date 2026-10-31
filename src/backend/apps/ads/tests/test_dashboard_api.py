"""Tests for the ``GET /api/v1/dashboard/`` JSON read endpoint (S2.3).

Browserless (``Client()``) coverage of the seller-dashboard read:

- **Auth matrix** — anonymous answers the 401 ``unauthenticated`` problem;
  an authenticated, consented seller answers 200 with the grouped payload.
- **R-L1 consent gate** — a never-consented / withdrawn-consent / banned seller
  is refused with a 403 ``consent_required`` problem **before** any grouping is
  built; the body is asserted to be a problem document, never an empty grouping.
- **Gate equivalence** — the API ``can_create_ad`` refusal set equals the HTML
  dashboard gate's refusal set (both surfaces forbid precisely for the same
  fixtures).
- **``?time_range=`` parity** — the same range values drive the same grouping /
  stats as the HTML dashboard's grouped context.
- **Payload shape** — JSON structured asserts on the grouping and stats keys.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client
from django.utils import timezone

from apps.core.enums import AdStatus, TimeRange
from apps.core.utils.problem import PROBLEM_CONTENT_TYPE
from conftest import create_test_ad, make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

ENDPOINT = "/api/v1/dashboard/"
HTML_ENDPOINT = "/dashboard/"


def _consented_user(telegram_id: int) -> Any:
    """Create a consented seller (the shape ``can_create_ad`` admits)."""
    return make_user(telegram_id, consent_given_at=timezone.now())


def _no_consent_user(telegram_id: int) -> Any:
    """Create a registered seller who never granted storage consent."""
    return make_user(telegram_id)


def _withdrawn_user(telegram_id: int) -> Any:
    """Create a seller who withdrew storage consent."""
    return make_user(telegram_id, consent_revoked=True)


def _banned_user(telegram_id: int) -> Any:
    """Create a consented seller who is then banned."""
    user = make_user(telegram_id, consent_given_at=timezone.now())
    user.is_banned = True
    user.save(update_fields=["is_banned"])
    return user


class TestAuthMatrix:
    """Anonymous → 401 problem; authenticated + consented → 200 payload."""

    def test_anonymous_returns_401_problem(self) -> None:
        response = Client().get(ENDPOINT)

        assert response.status_code == 401
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        payload = response.json()
        assert payload["type"] == "unauthenticated"
        assert payload["status"] == 401
        # No bearer scheme exists; a WWW-Authenticate challenge would be a lie.
        assert "WWW-Authenticate" not in response.headers

    def test_consented_seller_returns_200_grouped_payload(
        self, category, city
    ) -> None:
        seller = _consented_user(992003001)
        published = create_test_ad(
            seller, category, city, title="Live", status=AdStatus.PUBLISHED
        )
        archived = create_test_ad(
            seller, category, city, title="Old", status=AdStatus.ARCHIVED
        )
        client = Client()
        client.force_login(seller)

        response = client.get(ENDPOINT)

        assert response.status_code == 200
        payload = response.json()
        assert payload["time_range"] == TimeRange.ALL_TIME.value
        assert payload["groups"][AdStatus.PUBLISHED]["count"] == 1
        assert payload["groups"][AdStatus.ARCHIVED]["count"] == 1
        assert payload["groups"][AdStatus.PUBLISHED]["results"][0]["id"] == published.id
        assert payload["groups"][AdStatus.ARCHIVED]["results"][0]["id"] == archived.id


class TestConsentGateRL1:
    """R-L1: absent / withdrawn / banned → 403 ``consent_required``, never [].

    The refusal must fire before the groups are built, so the refusal body can
    never masquerade as an empty grouping.
    """

    @pytest.mark.parametrize(
        "maker",
        [_no_consent_user, _withdrawn_user, _banned_user],
        ids=["never_consented", "withdrawn", "banned"],
    )
    def test_refused_account_gets_403_problem_not_empty_groups(
        self, maker, category, city
    ) -> None:
        seller = maker(992004000 + abs(hash(maker.__name__)) % 1000)
        # The account owns ads, so a silent empty grouping would be a lie.
        create_test_ad(seller, category, city, title="Mine", status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(seller)

        response = client.get(ENDPOINT)

        assert response.status_code == 403
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        payload = response.json()
        assert payload["type"] == "consent_required"
        assert payload["status"] == 403
        # R-L1: the body is a problem document, NOT an empty grouping.
        assert "groups" not in payload
        assert "results" not in payload


class TestGateEquivalence:
    """The API ``can_create_ad`` refusal set == the HTML dashboard gate's."""

    @pytest.mark.parametrize(
        "maker",
        [_consented_user, _no_consent_user, _withdrawn_user, _banned_user],
        ids=["consented", "never_consented", "withdrawn", "banned"],
    )
    def test_api_forbids_precisely_when_html_forbids(
        self, maker, category, city
    ) -> None:
        seller = maker(992005000 + abs(hash(maker.__name__)) % 1000)
        create_test_ad(seller, category, city, title="Mine", status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(seller)

        html_forbidden = client.get(HTML_ENDPOINT).status_code == 403
        api_forbidden = client.get(ENDPOINT).status_code == 403

        assert api_forbidden == html_forbidden


class TestTimeRangeParity:
    """``?time_range=`` values drive identical grouping on both surfaces."""

    @pytest.mark.parametrize(
        "value",
        [
            TimeRange.ALL_TIME.value,
            TimeRange.THIRTY_DAYS.value,
            TimeRange.SEVEN_DAYS.value,
            "invalid",
            "",
        ],
        ids=["all_time", "30_days", "7_days", "invalid", "empty"],
    )
    def test_time_range_selection_matches_html_context(
        self, value, category, city
    ) -> None:
        seller = _consented_user(992006000 + abs(hash(value)) % 1000)
        create_test_ad(seller, category, city, title="Pub", status=AdStatus.PUBLISHED)
        create_test_ad(seller, category, city, title="Arch", status=AdStatus.ARCHIVED)
        client = Client()
        client.force_login(seller)

        html_response = client.get(HTML_ENDPOINT, {"time_range": value})
        api_payload = client.get(ENDPOINT, {"time_range": value}).json()

        # The selected range resolves identically on both surfaces.
        assert api_payload["time_range"] == html_response.context["selected_time_range"]

        # The grouped ids match the HTML grouped context for every dashboard
        # status bucket.
        html_groups = html_response.context["ads_by_status"]
        for status in html_groups:
            assert {ad.id for ad in html_groups[status]} == {
                ad["id"] for ad in api_payload["groups"][status.value]["results"]
            }


class TestPayloadShape:
    """Structured asserts on the grouping and stats keys."""

    def test_groups_cover_the_five_dashboard_statuses(self, category, city) -> None:
        seller = _consented_user(992007001)
        client = Client()
        client.force_login(seller)

        payload = client.get(ENDPOINT).json()

        assert list(payload["groups"].keys()) == [
            AdStatus.PUBLISHED.value,
            AdStatus.ON_MODERATION.value,
            AdStatus.ON_MODERATION_FAILED.value,
            AdStatus.ARCHIVED.value,
            AdStatus.REJECTED.value,
        ]
        assert payload["time_range_options"] == [
            TimeRange.ALL_TIME.value,
            TimeRange.THIRTY_DAYS.value,
            TimeRange.SEVEN_DAYS.value,
        ]

    def test_stats_block_matches_html_seller_stats(self, category, city) -> None:
        seller = _consented_user(992007002)
        create_test_ad(seller, category, city, title="Pub", status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(seller)

        html_stats = client.get(HTML_ENDPOINT).context["seller_stats"]
        api_stats = client.get(ENDPOINT).json()["stats"]

        assert api_stats["total_views"] == html_stats["total_views"]
        assert api_stats["total_contacts"] == html_stats["total_contacts"]
        assert api_stats["ads_published"] == html_stats["ads_published"]
        assert api_stats["per_ad_stats"] == html_stats["per_ad_stats"]

    def test_serialized_ad_carries_listings_shape(self, category, city) -> None:
        seller = _consented_user(992007003)
        ad = create_test_ad(seller, category, city, title="Pub", status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(seller)

        result = client.get(ENDPOINT).json()["groups"][AdStatus.PUBLISHED.value][
            "results"
        ][0]

        assert result["id"] == ad.id
        assert result["title"] == "Pub"
        assert result["status"] == AdStatus.PUBLISHED
        assert result["city"]["slug"] == city.slug
        assert result["category"]["slug"] == category.slug
        assert result["absolute_url"] == ad.get_absolute_url()
