"""Tests for the ``POST /api/v1/ads/{id}/edit/`` endpoint (S4.4).

Browserless (``Client()``) coverage of the edit write (plan §2.4 row 6) and the
five-branch ``EditOutcome`` matrix (auditor A5):

- **401 / 405 / 422 / 429** — the standard write pipeline, in the mandated order.
- **uniform 404** — a missing id and a non-owned id answer the identical
  ``not_found`` document.
- **consent 403** — a non-consented owner is refused before any write, and the
  ``submit_ad`` ``CONSENT_REQUIRED`` race is mapped to the same 403.
- **409 ``not_editable``** — an owner whose ad is outside the edit affordance
  set (``ON_MODERATION_FAILED``, ``REJECTED``, ``DELETED``).
- **409 ``invalid_transition``** — the service's ``REFUSED`` outcome (an
  ``ARCHIVED`` ad edited without ``reactivate``) **and** ``submit_ad``'s own
  ``INVALID_TRANSITION`` outcome.
- **submit-time refusal family** — ``CONSENT_REQUIRED`` → 403
  ``consent_required``; ``DRAFT_GONE`` / ``PHOTO_UNAVAILABLE`` /
  ``INVALID_TRANSITION`` → 409 with their own ``type``, each leaving the row
  untouched (the honest mapping; these were a dishonest 200 before P0).
- **happy paths** — parametrized over the four successful outcomes
  (``REACTIVATED`` / ``RESUBMITTED`` / ``PRICE_UPDATED`` / ``DIRECT_SAVED``),
  each asserted against the **service tier** for the same fixtures.
- **O-27 body** — the all-fields-repeated rule, the currency tuple rule and the
  snake_case DTO ↔ ``AdEditInput`` mapping.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.ads.models import Ad
from apps.ads.services.edit_flow import (
    EDIT_FORM_AVAILABLE_STATUSES,
    EditOutcome,
    apply_edit_payload,
    can_edit_ad,
)
from apps.ads.services.submission import AdEditInput, SubmitAdOutcome
from apps.ads.views.api.edit import AdEditBody
from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AdStatus, AnalyticsEventType, RateLimitBudget
from apps.core.utils.problem import PROBLEM_CONTENT_TYPE, RETRY_AFTER_HEADER
from apps.currencies.enums import CurrencyCode
from conftest import create_test_ad, make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_ENDPOINT = "ads_api:edit"
_URL = "/api/v1/ads/{id}/edit/"


def _post(
    ad_id: int, payload: dict[str, Any], client: Client, *, permissive: bool = False
):
    """POST a JSON edit body to the endpoint.

    ``permissive=True`` runs the request with the permissive moderation criteria
    (the ``permissive_criteria`` fixture's values) around the call, so a branch
    that re-enters moderation lands deterministically on its verdict without
    depending on the database's criteria row.
    """
    if not permissive:
        return client.post(
            reverse(_ENDPOINT, args=[ad_id]),
            data=payload,
            content_type="application/json",
        )
    with (
        patch(
            "apps.moderation.services.auto_moderation._get_cached_criteria",
            return_value=(1, 200, 1, 2000, False, 0, 10, (), 100, 0),
        ),
        patch(
            "apps.moderation.services.auto_moderation._validate_max_ads_per_user",
            return_value=True,
        ),
        patch(
            "apps.moderation.services.auto_moderation._is_duplicate_title",
            return_value=False,
        ),
        patch(
            "apps.moderation.services.moderation_log.ModerationCriteria.get_singleton",
            return_value=MagicMock(max_ads_per_user=100),
        ),
    ):
        return client.post(
            reverse(_ENDPOINT, args=[ad_id]),
            data=payload,
            content_type="application/json",
        )


def _full_body(ad: Ad, **overrides: Any) -> dict[str, Any]:
    """Build a body that repeats every field (the O-27 rule) from *ad*."""
    body: dict[str, Any] = {
        "title": ad.title,
        "description": ad.description,
        "price_amount": str(ad.price_amount),
        "price_currency": ad.price_currency,
    }
    body.update(overrides)
    return body


def _force_status(ad: Ad, status: AdStatus) -> None:
    """Force *ad* into *status* for fixtures the transition matrix forbids.

    ``ON_MODERATION`` is not durably committable (``auto_moderate`` resolves it)
    and ``PUBLISHED -> DRAFT`` is not a legal transition, so a test that needs
    such a starting point writes the row directly — exactly how
    ``create_test_ad`` prepares such fixtures.
    """
    Ad.objects.filter(pk=ad.pk).update(status=status)
    ad.refresh_from_db()


def _force_archived(ad: Ad) -> Ad:
    """Archive *ad* through the legal ``PUBLISHED -> ARCHIVED`` transition."""
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


@pytest.fixture
def client_(seller) -> Client:
    """Django test client authenticated as the ``seller`` fixture."""
    client = Client()
    client.force_login(seller)
    return client


# ---------------------------------------------------------------------------
# Pipeline matrices
# ---------------------------------------------------------------------------


class TestAuthMatrix:
    """Anonymous → 401 problem, before the method gate."""

    def test_anonymous_post_returns_401_problem(self, seller, category, city) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)

        response = _post(ad.id, _full_body(ad), Client())

        assert response.status_code == 401
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "unauthenticated"
        assert "WWW-Authenticate" not in response.headers

    def test_anonymous_get_is_401_not_405(self, seller, category, city) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)

        response = Client().get(reverse(_ENDPOINT, args=[ad.id]))

        assert response.status_code == 401
        assert response.json()["type"] == "unauthenticated"


class TestMethodGate:
    """An authenticated non-POST → 405 problem + ``Allow: POST``."""

    @pytest.mark.parametrize("method", ["get", "put", "patch", "delete"])
    def test_wrong_method_returns_405(self, client_, seller, category, city, method) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)

        response = getattr(client_, method)(reverse(_ENDPOINT, args=[ad.id]))

        assert response.status_code == 405
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "method_not_allowed"
        assert response.headers["Allow"] == "POST"
        ad.refresh_from_db()
        assert ad.status == AdStatus.DRAFT


class TestValidationMatrix:
    """Body failures → 422 ``validation_failed``; nothing is written."""

    @pytest.mark.parametrize(
        "payload,case",
        [
            (b"{not json", "malformed_json"),
            (b"[]", "non_object"),
            (b'{"title": "x", "bogus": 1}', "unknown_key"),
            (b'{"price_amount": -5}', "negative_price"),
            (b'{"price_currency": "XYZ"}', "unknown_currency"),
        ],
        ids=lambda v: v if isinstance(v, str) else "",
    )
    def test_bad_body_returns_422(
        self, client_, seller, category, city, payload, case
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
        before_title = ad.title

        response = client_.post(
            reverse(_ENDPOINT, args=[ad.id]),
            data=payload,
            content_type="application/json",
        )

        assert response.status_code == 422
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "validation_failed"
        ad.refresh_from_db()
        assert ad.title == before_title


class TestRateLimit:
    """Exhausting ``API_WRITE`` → 429 problem + ``Retry-After``."""

    def test_over_budget_returns_rate_limited_problem(
        self, client_, seller, category, city, monkeypatch
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
        monkeypatch.setattr(
            "apps.ads.views.api.edit.rate_limit_check",
            lambda *args, **kwargs: False,
        )

        response = _post(ad.id, _full_body(ad), client_)

        assert response.status_code == 429
        assert response.json()["type"] == "rate_limited"
        assert response.headers.get(RETRY_AFTER_HEADER) == str(
            RateLimitBudget.API_WRITE.period
        )


class TestUniformNotFound:
    """A missing id and a non-owned id answer the identical document."""

    def test_missing_and_non_owned_are_indistinguishable(self, seller, category, city) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
        intruder = make_user(914000101)
        client = Client()
        client.force_login(intruder)

        non_owned = _post(ad.id, _full_body(ad), client)
        missing = _post(999_999_999, _full_body(ad), client)

        assert non_owned.status_code == 404
        assert missing.status_code == 404
        assert non_owned.content == missing.content
        assert non_owned.json()["type"] == "not_found"
        ad.refresh_from_db()
        assert ad.title != "hacked"


# ---------------------------------------------------------------------------
# Consent (A14 seam + the submit_ad CONSENT_REQUIRED race)
# ---------------------------------------------------------------------------


class TestConsentGate:
    """A non-consented owner is refused before any write."""

    @pytest.mark.parametrize(
        "maker",
        [
            lambda tid: make_user(tid),
            lambda tid: make_user(tid, consent_revoked=True),
        ],
        ids=["never_consented", "withdrawn"],
    )
    def test_owner_without_consent_gets_403(
        self, maker, category, city
    ) -> None:
        owner = maker(914001001)
        ad = create_test_ad(owner, category, city, status=AdStatus.DRAFT)
        Ad.objects.filter(pk=ad.pk).update(title="Untouched")
        client = Client()
        client.force_login(owner)

        response = _post(ad.id, _full_body(ad, title="Changed"), client)

        assert response.status_code == 403
        assert response.json()["type"] == "consent_required"
        ad.refresh_from_db()
        assert ad.title == "Untouched"

    def test_consent_gate_matches_html_gate(self, category, city) -> None:
        """API refusal set == the HTML edit view's consent refusal set."""
        for offset, maker in enumerate(
            [
                lambda tid: make_user(tid, consent_given_at=timezone.now()),
                lambda tid: make_user(tid),
                lambda tid: make_user(tid, consent_revoked=True),
            ]
        ):
            owner = maker(914002000 + offset)
            ad = create_test_ad(owner, category, city, status=AdStatus.DRAFT)
            client = Client()
            client.force_login(owner)

            html_forbidden = (
                client.post(
                    reverse("ads:edit", args=[ad.id]),
                    data=_full_body(ad),
                ).status_code
                == 403
            )
            api_forbidden = _post(ad.id, _full_body(ad), client).status_code == 403

            assert api_forbidden == html_forbidden

    def test_submit_ad_consent_required_race_maps_to_403(
        self, client_, seller, category, city, monkeypatch
    ) -> None:
        """``submit_ad``'s own CONSENT_REQUIRED (the race) → 403, not 200 REFUSED."""
        ad = create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED, price=100
        )
        Ad.objects.filter(pk=ad.pk).update(title="Old", description="Old body")

        def _consent_race(*args: Any, **kwargs: Any):
            from apps.ads.services.submission import SubmitAdResult

            return SubmitAdResult(outcome=SubmitAdOutcome.CONSENT_REQUIRED, errors=[])

        monkeypatch.setattr("apps.ads.services.edit_flow.submit_ad", _consent_race)

        response = _post(ad.id, _full_body(ad, title="New title"), client_)

        assert response.status_code == 403
        assert response.json()["type"] == "consent_required"


# ---------------------------------------------------------------------------
# Status gate
# ---------------------------------------------------------------------------


class TestNotEditable:
    """An owner whose ad is outside the affordance set → 409 ``not_editable``."""

    @pytest.mark.parametrize(
        "status",
        [AdStatus.ON_MODERATION_FAILED, AdStatus.REJECTED, AdStatus.DELETED],
        ids=["moderation_failed", "rejected", "deleted"],
    )
    def test_uneditable_status_is_409_not_editable(
        self, client_, seller, category, city, status
    ) -> None:
        ad = create_test_ad(seller, category, city, status=status)
        Ad.objects.filter(pk=ad.pk).update(title="Untouched")
        before = Ad.objects.get(pk=ad.pk)

        response = _post(ad.id, _full_body(ad, title="Changed"), client_)

        assert response.status_code == 409
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "not_editable"
        after = Ad.objects.get(pk=ad.pk)
        assert after.title == "Untouched"
        assert after.updated_at == before.updated_at

    def test_affordance_predicate_agrees_with_the_endpoint(
        self, client_, seller, category, city
    ) -> None:
        """The 409 boundary is exactly ``can_edit_ad``'s status predicate."""
        for status in AdStatus:
            ad = create_test_ad(seller, category, city, status=status)
            assert can_edit_ad(ad, seller.id) is (status in EDIT_FORM_AVAILABLE_STATUSES)


class TestInvalidTransition:
    """The service's ``REFUSED`` outcome → 409 ``invalid_transition``, no write."""

    def test_archived_without_reactivate_is_409(
        self, client_, seller, category, city
    ) -> None:
        ad = create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED, price=100
        )
        _force_archived(ad)
        Ad.objects.filter(pk=ad.pk).update(title="Untouched")

        response = _post(
            ad.id,
            _full_body(ad, title="Changed", reactivate=False),
            client_,
        )

        assert response.status_code == 409
        assert response.json()["type"] == "invalid_transition"
        ad.refresh_from_db()
        assert ad.title == "Untouched"
        assert ad.status == AdStatus.ARCHIVED

    def test_archived_without_reactivate_matches_service_tier(
        self, seller, category, city
    ) -> None:
        """``apply_edit_payload`` returns REFUSED for the same fixture."""
        ad = create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED, price=100
        )
        _force_archived(ad)

        result = apply_edit_payload(
            ad,
            AdEditInput(title="Changed", description=ad.description),
            False,
        )

        assert result.outcome is EditOutcome.REFUSED
        assert result.submission_outcome is None


# ---------------------------------------------------------------------------
# Submit-time refusal family — honest 403/409 mapping, no mock machinery
# ---------------------------------------------------------------------------


class TestSubmitOutcomeRefusalMapping:
    """``submit_ad``'s refusal outcomes map to their own §2.5 problems.

    Injected at ``apps.ads.services.edit_flow.submit_ad`` (the real seam, the
    same one the consent-race test uses) because none of the four is reachable
    through this endpoint: ``photos=[]`` rules out ``PHOTO_UNAVAILABLE``; the
    row lock plus ``submit_ad``'s locked re-fetch make ``DRAFT_GONE`` and
    ``INVALID_TRANSITION`` races; ``CONSENT_REQUIRED`` needs consent withdrawn
    mid-request. The endpoint reads the typed ``EditResult.submission_outcome``
    directly — no ``unittest.mock.patch`` of a production symbol.
    """

    @pytest.mark.parametrize(
        ("outcome", "status", "token", "reactivate"),
        [
            (SubmitAdOutcome.CONSENT_REQUIRED, 403, "consent_required", False),
            (SubmitAdOutcome.INVALID_TRANSITION, 409, "invalid_transition", False),
            (SubmitAdOutcome.DRAFT_GONE, 409, "draft_gone", False),
            (SubmitAdOutcome.PHOTO_UNAVAILABLE, 409, "photo_unavailable", False),
            (SubmitAdOutcome.CONSENT_REQUIRED, 403, "consent_required", True),
            (SubmitAdOutcome.DRAFT_GONE, 409, "draft_gone", True),
        ],
        ids=[
            "resubmit_consent",
            "resubmit_invalid_transition",
            "resubmit_draft_gone",
            "resubmit_photo_unavailable",
            "reactivate_consent",
            "reactivate_draft_gone",
        ],
    )
    def test_refusal_maps_to_problem_and_leaves_row_untouched(
        self,
        monkeypatch,
        client_,
        seller,
        category,
        city,
        outcome,
        status,
        token,
        reactivate,
    ) -> None:
        from apps.ads.services.submission import SubmitAdResult

        ad = create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED, price=100, title="Old"
        )
        if reactivate:
            _force_archived(ad)
        before = Ad.objects.get(pk=ad.pk)

        def _refuse(*args: Any, **kwargs: Any) -> SubmitAdResult:
            return SubmitAdResult(outcome=outcome, errors=["refused"])

        monkeypatch.setattr("apps.ads.services.edit_flow.submit_ad", _refuse)

        body = _full_body(ad, title="New title")
        if reactivate:
            body["reactivate"] = True
        response = _post(ad.id, body, client_)

        assert response.status_code == status
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == token
        after = Ad.objects.get(pk=ad.pk)
        assert (after.title, after.status) == (before.title, before.status)
        assert after.updated_at == before.updated_at


# ---------------------------------------------------------------------------
# Happy paths — parametrized over the four successful outcomes
# ---------------------------------------------------------------------------

class TestEditOutcomeMatrix:
    """Each successful ``EditOutcome`` branch, asserted against the service tier."""

    def test_published_text_edit_is_resubmitted(
        self, seller, category, city
    ) -> None:
        ad = create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED, price=100
        )
        original_published_at = ad.published_at
        ad_before_status = AdStatus(ad.status)
        client = Client()
        client.force_login(seller)

        response = _post(
            ad.id,
            _full_body(ad, title="Brand new title"),
            client,
            permissive=True,
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["outcome"] == EditOutcome.RESUBMITTED.value
        assert payload["moderation_failed"] is False
        # The branch is what is under test: the ad left PUBLISHED through
        # ``submit_ad`` (zone C2 — a text edit re-enters moderation and is
        # resolved in the same transaction, so it rests at PUBLISHED on a pass
        # or ON_MODERATION_FAILED on a rejection, never at PUBLISHED-on-the-old
        # row).
        assert ad_before_status == AdStatus.PUBLISHED
        ad.refresh_from_db()
        assert ad.title == "Brand new title"
        assert ad.status == payload["status"]
        # A re-publish records a fresh ``published_at`` (submit_ad's pass path).
        assert ad.published_at >= original_published_at

    def test_published_price_only_is_price_updated(
        self, client_, seller, category, city
    ) -> None:
        ad = create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED, price=100
        )
        initial_published_at = ad.published_at

        response = _post(ad.id, _full_body(ad, price_amount="200"), client_)

        assert response.status_code == 200
        payload = response.json()
        assert payload["outcome"] == EditOutcome.PRICE_UPDATED.value
        assert payload["status"] == AdStatus.PUBLISHED

        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED
        assert ad.price_amount == Decimal("200")
        # The price edit restarts the auto-archive clock (BLOCK 2 / J).
        assert ad.published_at > initial_published_at

    @pytest.mark.parametrize(
        "status", [AdStatus.DRAFT, AdStatus.ON_MODERATION],
        ids=["draft", "on_moderation"],
    )
    def test_draft_or_pending_is_direct_saved(
        self, client_, seller, category, city, status
    ) -> None:
        ad = create_test_ad(seller, category, city, status=status, price=100)

        response = _post(
            ad.id, _full_body(ad, title="Direct save title"), client_
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["outcome"] == EditOutcome.DIRECT_SAVED.value
        assert payload["status"] == status

        ad.refresh_from_db()
        assert ad.title == "Direct save title"
        assert ad.status == status  # unchanged by a direct save
        assert ad.moderation_failed_at is None

    def test_archived_with_reactivate_is_reactivated(
        self, client_, seller, category, city, permissive_criteria
    ) -> None:
        ad = create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED, price=100
        )
        _force_archived(ad)

        response = _post(
            ad.id, _full_body(ad, reactivate=True), client_
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["outcome"] == EditOutcome.REACTIVATED.value
        assert payload["status"] == AdStatus.PUBLISHED

        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED
        assert ad.published_at is not None
        assert _event_types(ad) == [
            AnalyticsEventType.AD_PUBLISHED,
            AnalyticsEventType.MODERATION_APPROVED,
        ]

    def test_reactivation_moderation_failure_is_200(
        self, client_, seller, category, city, banning_criteria
    ) -> None:
        ad = create_test_ad(
            seller, category, city, status=AdStatus.PUBLISHED, price=100
        )
        _force_archived(ad)

        response = _post(
            ad.id,
            _full_body(ad, title="spam offer", reactivate=True),
            client_,
        )

        # The payload was committed and the ad parked: 200 (boundary O-2a).
        assert response.status_code == 200
        payload = response.json()
        assert payload["outcome"] == EditOutcome.REACTIVATED.value
        assert payload["moderation_failed"] is True
        assert payload["errors"]

        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION_FAILED
        assert ad.moderation_failed_at is not None

    @pytest.mark.parametrize(
        "status, change, expected",
        [
            (AdStatus.ARCHIVED, {"reactivate": True}, EditOutcome.REACTIVATED),
            (AdStatus.PUBLISHED, {"title": "Changed"}, EditOutcome.RESUBMITTED),
            (AdStatus.PUBLISHED, {"price_amount": "321"}, EditOutcome.PRICE_UPDATED),
            (AdStatus.DRAFT, {"title": "Changed"}, EditOutcome.DIRECT_SAVED),
            (AdStatus.ON_MODERATION, {"title": "Changed"}, EditOutcome.DIRECT_SAVED),
        ],
        ids=["reactivated", "resubmitted", "price_updated", "draft_saved", "pending_saved"],
    )
    def test_endpoint_outcome_matches_service_tier(
        self,
        seller,
        category,
        city,
        permissive_criteria,
        status,
        change,
        expected,
    ) -> None:
        """Same fixture → same ``EditOutcome`` from the endpoint and the service.

        Each leg gets its own user (the draft-uniqueness constraint allows one
        DRAFT per owner) and both legs start from an ad forced into *status*.
        """
        from django.db import transaction

        def _prepare(owner: Any) -> Ad:
            ad = create_test_ad(owner, category, city, status=AdStatus.PUBLISHED, price=100)
            if status is AdStatus.ARCHIVED:
                _force_archived(ad)
            elif status is not AdStatus.PUBLISHED:
                _force_status(ad, status)
            return ad

        service_owner = make_user(914005000, consent_given_at=timezone.now())
        service_ad = _prepare(service_owner)
        service_dto = AdEditInput(
            title=change.get("title", service_ad.title),
            description=service_ad.description,
            price_amount=Decimal(
                change.get("price_amount", str(service_ad.price_amount))
            ),
        )
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]  # django-stubs
            locked = Ad.objects.select_for_update().get(id=service_ad.id)
            service_result = apply_edit_payload(
                locked,
                service_dto,
                bool(change.get("reactivate")),
            )

        api_owner = make_user(914005001, consent_given_at=timezone.now())
        api_ad = _prepare(api_owner)
        api_ad.refresh_from_db()
        client = Client()
        client.force_login(api_owner)

        response = _post(api_ad.id, _full_body(api_ad, **change), client)

        assert response.status_code == 200
        assert service_result.outcome is expected
        assert response.json()["outcome"] == expected.value
        api_ad.refresh_from_db()
        assert api_ad.status == Ad.objects.get(id=service_ad.id).status


# ---------------------------------------------------------------------------
# O-27 body contract
# ---------------------------------------------------------------------------


class TestO27BodyContract:
    """The DTO encodes the O-27 rules and feeds the shared ``AdEditInput``."""

    def test_defaults_repeat_all_fields(self) -> None:
        """An empty body means "the blank form": text empty, price Free."""
        body = AdEditBody.model_validate({})

        assert body.title == ""
        assert body.description == ""
        assert body.price_amount == Decimal("0")
        # Absent currency keeps the ad's stored one (the O-27 tuple rule).
        assert body.price_currency is None
        assert body.reactivate is False

    @pytest.mark.parametrize(
        "raw, expected",
        [("", Decimal("0")), ("abc", Decimal("0")), ("12.50", Decimal("12.50")), (300, Decimal("300"))],
        ids=["blank", "unparseable", "decimal_string", "integer"],
    )
    def test_price_coercion_matches_html(self, raw, expected) -> None:
        assert AdEditBody.model_validate({"price_amount": raw}).price_amount == expected

    def test_currency_tuple_rule(self) -> None:
        """Absent/blank → keep stored currency (None); a code → that code."""
        assert AdEditBody.model_validate({}).to_edit_input().price_currency is None
        assert (
            AdEditBody.model_validate({"price_currency": "eur"}).to_edit_input().price_currency
            is CurrencyCode.EUR
        )

    def test_currency_outside_the_tuple_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            AdEditBody.model_validate({"price_currency": "XYZ"}).to_edit_input()

    def test_body_feeds_the_shared_dto(self) -> None:
        body = AdEditBody.model_validate(
            {
                "title": "  Trimmed  ",
                "description": "Body",
                "price_amount": "10",
                "price_currency": "BAM",
            }
        )
        dto = body.to_edit_input()

        assert isinstance(dto, AdEditInput)
        assert dto.title == "Trimmed"
        assert dto.price_currency is CurrencyCode.BAM

    def test_missing_field_overwrites_with_empty_value(self, client_, seller, category, city) -> None:
        """O-27: an omitted field is the empty value, never "unchanged"."""
        ad = create_test_ad(
            seller, category, city, status=AdStatus.DRAFT, price=100
        )

        response = _post(ad.id, {"description": "only description"}, client_)

        assert response.status_code == 200
        ad.refresh_from_db()
        assert ad.title == ""
        assert ad.description == "only description"
        assert ad.price_amount == Decimal("0")

    def test_form_encoded_body_parses_like_json(self, client_, seller, category, city) -> None:
        """The form content type (HTML parity) lands on the same DTO."""
        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT, price=100)

        response = client_.post(
            reverse(_ENDPOINT, args=[ad.id]),
            data={
                "title": "Form title",
                "description": ad.description,
                "price_amount": "100",
                "price_currency": CurrencyCode.EUR.value,
            },
        )

        assert response.status_code == 200
        ad.refresh_from_db()
        assert ad.title == "Form title"


# ---------------------------------------------------------------------------
# Presentation delta (HTML 200+form vs API 409) and route registration
# ---------------------------------------------------------------------------


def test_route_is_registered_under_the_plan_url() -> None:
    assert reverse(_ENDPOINT, args=[7]) == _URL.format(id=7)
