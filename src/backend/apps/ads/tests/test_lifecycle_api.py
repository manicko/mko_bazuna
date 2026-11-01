"""Tests for the ``/api/v1/ads/{id}/{archive,reactivate,delete}/`` endpoints (S4.3).

Browserless (``Client()``) coverage of the three lifecycle writes (plan §2.4
rows 7, 8 and 9) and their §2.5 mappings:

- **401 matrix** — an anonymous request of any verb answers the
  ``unauthenticated`` problem (identity before method; no ``WWW-Authenticate``).
- **405 matrix** — an authenticated non-POST answers ``method_not_allowed`` with
  ``Allow: POST``, and changes nothing.
- **429 matrix** — exhausting the shared ``api_write`` budget answers the
  ``rate_limited`` problem with a ``Retry-After`` header.
- **uniform 404** — a missing id and a non-owned id answer the *identical*
  ``not_found`` document.
- **consent 403 (A7)** — archive / reactivate by a non-consented owner answer
  ``consent_required`` and leave the row byte-identical (consent is asserted
  **before** the transition, the stricter §2.5 order); delete is gate-free.
- **happy paths** — archive / reactivate-pass / reactivate-fail / delete assert
  the *post-action* payload and the **service parity** of the recorded state
  (same status transitions, timestamps and analytics rows the service tier and
  the HTML flows produce).
- **409 ``invalid_transition``** — a wrong-status call is refused instead of the
  HTML silent no-op.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.ads.models import Ad
from apps.ads.services.lifecycle import (
    ArchiveResult,
    DeleteResult,
    ReactivateResult,
    archive_ad,
    delete_ad,
    reactivate_ad,
)
from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AdStatus, AnalyticsEventType, RateLimitBudget
from apps.core.utils.problem import PROBLEM_CONTENT_TYPE, RETRY_AFTER_HEADER
from conftest import create_test_ad, make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# Route names registered by ``apps.ads.api_urls`` (``app_name="ads_api"``).
_ARCHIVE = "ads_api:archive"
_REACTIVATE = "ads_api:reactivate"
_DELETE = "ads_api:delete"

_ALL_ROUTES = pytest.mark.parametrize(
    "route_name",
    [_ARCHIVE, _REACTIVATE, _DELETE],
    ids=["archive", "reactivate", "delete"],
)


def _archived_ad(owner: Any, category: Any, city: Any) -> Ad:
    """Create a PUBLISHED ad and archive it so it can be reactivated."""
    ad = create_test_ad(owner, category, city, status=AdStatus.PUBLISHED, price=100)
    ad.transition_to(AdStatus.ARCHIVED)
    ad.refresh_from_db()
    assert ad.status == AdStatus.ARCHIVED
    return ad


def _event_types(ad: Ad) -> list[str]:
    """Analytics event types recorded for *ad*, as plain strings."""
    return list(
        AnalyticsEvent.objects.filter(ad_id=ad.id)
        .order_by("id")
        .values_list("event_type", flat=True)
    )


def _no_consent_owner(telegram_id: int) -> Any:
    """A registered seller who never granted storage consent."""
    return make_user(telegram_id)


def _withdrawn_owner(telegram_id: int) -> Any:
    """A seller who withdrew storage consent."""
    return make_user(telegram_id, consent_revoked=True)


def _banned_owner(telegram_id: int) -> Any:
    """A consented seller who is then banned."""
    user = make_user(telegram_id, consent_given_at=timezone.now())
    user.is_banned = True
    user.save(update_fields=["is_banned"])
    return user


# ---------------------------------------------------------------------------
# Auth matrix
# ---------------------------------------------------------------------------


@_ALL_ROUTES
class TestAuthMatrix:
    """Anonymous → 401 problem on every verb, before the method gate."""

    def test_anonymous_post_returns_401_problem(
        self, route_name, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        response = Client().post(reverse(route_name, args=[ad.id]))

        assert response.status_code == 401
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "unauthenticated"
        assert "WWW-Authenticate" not in response.headers
        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED

    def test_anonymous_get_is_401_not_405(self, route_name, seller, category, city) -> None:
        """Identity is checked before the method, mirroring the frozen decorator."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        response = Client().get(reverse(route_name, args=[ad.id]))

        assert response.status_code == 401
        assert response.json()["type"] == "unauthenticated"


# ---------------------------------------------------------------------------
# Method gate
# ---------------------------------------------------------------------------


@_ALL_ROUTES
class TestMethodGate:
    """An authenticated non-POST is 405 ``method_not_allowed`` + ``Allow``."""

    @pytest.mark.parametrize("method", ["get", "put", "patch", "delete"])
    def test_wrong_method_returns_405_problem(
        self, route_name, method, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(seller)

        response = getattr(client, method)(reverse(route_name, args=[ad.id]))

        assert response.status_code == 405
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "method_not_allowed"
        assert response.headers["Allow"] == "POST"
        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED

    def test_wrong_method_on_archived_ad_changes_nothing(
        self, route_name, seller, category, city
    ) -> None:
        ad = _archived_ad(seller, category, city)
        client = Client()
        client.force_login(seller)

        response = client.get(reverse(route_name, args=[ad.id]))

        assert response.status_code == 405
        ad.refresh_from_db()
        assert ad.status == AdStatus.ARCHIVED


# ---------------------------------------------------------------------------
# Rate limit
# ---------------------------------------------------------------------------


@_ALL_ROUTES
class TestRateLimit:
    """Exhausting the shared ``api_write`` budget → 429 problem + Retry-After."""

    def test_budget_exhaustion_returns_429_problem(
        self, route_name, seller, category, city, monkeypatch
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(seller)
        monkeypatch.setattr(
            "apps.ads.views.api.lifecycle_actions.rate_limit_check",
            lambda *args, **kwargs: False,
        )

        response = client.post(reverse(route_name, args=[ad.id]))

        assert response.status_code == 429
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "rate_limited"
        assert response.headers.get(RETRY_AFTER_HEADER) == str(RateLimitBudget.API_WRITE.period)
        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED


# ---------------------------------------------------------------------------
# Uniform 404
# ---------------------------------------------------------------------------


@_ALL_ROUTES
class TestUniformNotFound:
    """A missing id and a non-owned id answer the identical 404 document."""

    def test_missing_and_non_owned_are_indistinguishable(
        self, route_name, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        intruder = make_user(913000100)
        client = Client()
        client.force_login(intruder)

        non_owned = client.post(reverse(route_name, args=[ad.id]))
        missing = client.post(reverse(route_name, args=[999_999_999]))

        assert non_owned.status_code == 404
        assert missing.status_code == 404
        assert non_owned.content == missing.content
        assert non_owned.json()["type"] == "not_found"
        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED


# ---------------------------------------------------------------------------
# Consent gate (A7): consent BEFORE transition
# ---------------------------------------------------------------------------


class TestConsentGate:
    """Archive / reactivate refuse a non-consented owner before any write."""

    @pytest.mark.parametrize(
        "maker", [_no_consent_owner, _withdrawn_owner, _banned_owner],
        ids=["never_consented", "withdrawn", "banned"],
    )
    def test_archive_refused_and_state_unchanged(
        self, maker, category, city
    ) -> None:
        owner = maker(913001000 + abs(hash(maker.__name__)) % 100)
        ad = create_test_ad(owner, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(owner)

        response = client.post(reverse(_ARCHIVE, args=[ad.id]))

        assert response.status_code == 403
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "consent_required"
        # Consent is asserted BEFORE the transition: nothing was written.
        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED
        assert ad.archived_at is None

    @pytest.mark.parametrize(
        "maker", [_no_consent_owner, _withdrawn_owner, _banned_owner],
        ids=["never_consented", "withdrawn", "banned"],
    )
    def test_reactivate_refused_and_state_unchanged(
        self, maker, category, city
    ) -> None:
        owner = maker(913002000 + abs(hash(maker.__name__)) % 100)
        ad = _archived_ad(owner, category, city)
        client = Client()
        client.force_login(owner)

        response = client.post(reverse(_REACTIVATE, args=[ad.id]))

        assert response.status_code == 403
        assert response.json()["type"] == "consent_required"
        ad.refresh_from_db()
        assert ad.status == AdStatus.ARCHIVED
        assert ad.archived_at is not None

    def test_delete_is_gate_free(self, category, city) -> None:
        """Row 9 carries no consent term: a non-consented owner may delete."""
        owner = _no_consent_owner(913003001)
        ad = create_test_ad(owner, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(owner)

        response = client.post(reverse(_DELETE, args=[ad.id]))

        assert response.status_code == 200
        ad.refresh_from_db()
        assert ad.status == AdStatus.DELETED

    def test_consent_gate_matches_html_gate(self, category, city) -> None:
        """API refusal set == HTML ``_seller_may_create_ad`` refusal set."""
        for offset, maker in enumerate(
            [lambda: make_user(913004000, consent_given_at=timezone.now()),
             _no_consent_owner, _withdrawn_owner, _banned_owner]
        ):
            owner = maker() if offset == 0 else maker(913004010 + offset)
            ad = create_test_ad(owner, category, city, status=AdStatus.PUBLISHED)
            client = Client()
            client.force_login(owner)

            html_forbidden = (
                client.post(reverse("ads:archive", args=[ad.id])).status_code == 403
            )
            api_forbidden = (
                client.post(reverse(_ARCHIVE, args=[ad.id])).status_code == 403
            )

            assert api_forbidden == html_forbidden


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


class TestArchiveHappyPath:
    """``archived=True`` → 200 with the post-action state."""

    def test_published_ad_is_archived(self, seller, category, city) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(seller)

        response = client.post(reverse(_ARCHIVE, args=[ad.id]))

        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == ad.id
        assert payload["outcome"] == "archived"
        assert payload["status"] == AdStatus.ARCHIVED
        assert payload["archived_at"] is not None

        ad.refresh_from_db()
        assert ad.status == AdStatus.ARCHIVED
        assert ad.archived_at is not None
        assert ad.published_at is not None  # untouched by the archive
        assert _event_types(ad) == []  # archiving emits no analytics row

    def test_matches_service_tier(self, seller, category, city) -> None:
        """The endpoint's state == the service's state for the same fixture."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        published_before = ad.published_at

        assert archive_ad(ad.id, seller.id) == ArchiveResult(archived=True)
        ad.refresh_from_db()
        expected = (ad.status, ad.archived_at is not None, ad.published_at)

        other = create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED, title="Second"
        )
        other_published_before = other.published_at
        client = Client()
        client.force_login(seller)
        response = client.post(reverse(_ARCHIVE, args=[other.id]))
        assert response.status_code == 200

        other.refresh_from_db()
        # Same status, same timestamp flags, and the pre-existing
        # ``published_at`` is carried through untouched by both tiers (the two
        # fixtures are created at different instants, so the absolute value is
        # compared against each ad's own pre-archive value).
        assert (other.status, other.archived_at is not None) == expected[:2]
        assert other.published_at == other_published_before
        assert ad.published_at == published_before


class TestReactivateHappyPath:
    """``attempted=True`` → 200 for both moderation verdicts."""

    def test_pass_publishes(
        self, seller, category, city, permissive_criteria
    ) -> None:
        ad = _archived_ad(seller, category, city)
        client = Client()
        client.force_login(seller)

        response = client.post(reverse(_REACTIVATE, args=[ad.id]))

        assert response.status_code == 200
        payload = response.json()
        assert payload["outcome"] == "reactivated"
        assert payload["status"] == AdStatus.PUBLISHED
        assert payload["published_at"] is not None
        assert payload["archived_at"] is None

        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED
        # Same events the service tier and the HTML flow produce on a pass.
        assert _event_types(ad) == [
            AnalyticsEventType.AD_PUBLISHED,
            AnalyticsEventType.MODERATION_APPROVED,
        ]

    def test_pass_matches_service_tier(
        self, seller, category, city, permissive_criteria
    ) -> None:
        service_ad = _archived_ad(seller, category, city)
        assert reactivate_ad(service_ad.id, seller.id) == ReactivateResult(
            attempted=True, passed=True
        )
        service_ad.refresh_from_db()

        api_ad = _archived_ad(seller, category, city)
        client = Client()
        client.force_login(seller)
        assert client.post(reverse(_REACTIVATE, args=[api_ad.id])).status_code == 200
        api_ad.refresh_from_db()

        assert api_ad.status == service_ad.status
        assert api_ad.archived_at == service_ad.archived_at
        assert _event_types(api_ad) == _event_types(service_ad)

    def test_fail_parks_on_moderation_failed(
        self, seller, category, city, banning_criteria
    ) -> None:
        ad = _archived_ad(seller, category, city)
        Ad.objects.filter(pk=ad.pk).update(title="spam offer")
        client = Client()
        client.force_login(seller)

        response = client.post(reverse(_REACTIVATE, args=[ad.id]))

        # A failed content check is a terminal, well-formed outcome (O-2a):
        # the ad was committed as ON_MODERATION_FAILED, so this is a 200.
        assert response.status_code == 200
        payload = response.json()
        assert payload["outcome"] == "moderation_failed"
        assert payload["status"] == AdStatus.ON_MODERATION_FAILED
        assert payload["moderation_failed_at"] is not None

        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION_FAILED
        assert _event_types(ad) == [AnalyticsEventType.MODERATION_REJECTED]


class TestDeleteHappyPath:
    """``deleted=True`` → 200 with the confirmed deleted state."""

    def test_ad_is_soft_deleted(self, seller, category, city) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(seller)

        response = client.post(reverse(_DELETE, args=[ad.id]))

        assert response.status_code == 200
        payload = response.json()
        assert payload["outcome"] == "deleted"
        assert payload["status"] == AdStatus.DELETED
        assert payload["deleted_at"] is not None

        ad.refresh_from_db()
        assert ad.status == AdStatus.DELETED
        assert ad.deleted_at is not None

    def test_matches_service_tier(self, seller, category, city) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        assert delete_ad(ad.id, seller.id) == DeleteResult(deleted=True)
        ad.refresh_from_db()

        api_ad = create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED, title="Second"
        )
        client = Client()
        client.force_login(seller)
        assert client.post(reverse(_DELETE, args=[api_ad.id])).status_code == 200
        api_ad.refresh_from_db()

        assert api_ad.status == ad.status
        assert (api_ad.deleted_at is not None) == (ad.deleted_at is not None)


# ---------------------------------------------------------------------------
# 409 invalid_transition (the service's silent no-op, surfaced)
# ---------------------------------------------------------------------------


class TestInvalidTransition:
    """A wrong-status call → 409 ``invalid_transition``, no write."""

    @pytest.mark.parametrize(
        "status",
        [AdStatus.DRAFT, AdStatus.REJECTED, AdStatus.ARCHIVED, AdStatus.DELETED],
        ids=["draft", "rejected", "archived", "deleted"],
    )
    def test_archive_wrong_status_is_409(
        self, seller, category, city, status
    ) -> None:
        ad = create_test_ad(seller, category, city, status=status)
        client = Client()
        client.force_login(seller)

        response = client.post(reverse(_ARCHIVE, args=[ad.id]))

        assert response.status_code == 409
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "invalid_transition"
        ad.refresh_from_db()
        assert ad.status == status

    @pytest.mark.parametrize(
        "status",
        [AdStatus.PUBLISHED, AdStatus.DRAFT, AdStatus.ON_MODERATION_FAILED],
        ids=["published", "draft", "moderation_failed"],
    )
    def test_reactivate_wrong_status_is_409(
        self, seller, category, city, status
    ) -> None:
        ad = create_test_ad(seller, category, city, status=status)
        client = Client()
        client.force_login(seller)

        response = client.post(reverse(_REACTIVATE, args=[ad.id]))

        assert response.status_code == 409
        assert response.json()["type"] == "invalid_transition"
        ad.refresh_from_db()
        assert ad.status == status
        assert _event_types(ad) == []

    def test_delete_already_deleted_is_409(self, seller, category, city) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.DELETED)
        client = Client()
        client.force_login(seller)

        response = client.post(reverse(_DELETE, args=[ad.id]))

        assert response.status_code == 409
        assert response.json()["type"] == "invalid_transition"


# ---------------------------------------------------------------------------
# Body handling
# ---------------------------------------------------------------------------


class TestRequestBody:
    """No body field exists; an empty body is fine and an unknown key is 422."""

    def test_empty_body_is_accepted(self, seller, category, city) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(seller)

        response = client.post(reverse(_ARCHIVE, args=[ad.id]))

        assert response.status_code == 200

    def test_unknown_key_is_422(self, seller, category, city) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(seller)

        response = client.post(
            reverse(_ARCHIVE, args=[ad.id]),
            data={"reason": "spam"},
            content_type="application/json",
        )

        assert response.status_code == 422
        assert response.json()["type"] == "validation_failed"
        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED
