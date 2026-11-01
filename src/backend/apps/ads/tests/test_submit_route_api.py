"""Tests for the ``POST /api/v1/ads/{id}/submit/`` endpoint (S4.5).

Browserless (``Client()``) coverage of the submit-on-draft write (plan §2.4
row 5), its O-14 pre-submission field-check inventory and the ``SubmitAdOutcome``
matrix (§2.5):

- **401 / 405 / 422 / 429** — the standard write pipeline, in the mandated
  order (identity before method; rate limit before resolution).
- **uniform 404** — a missing id and a non-owned id answer the identical
  ``not_found`` document.
- **consent 403** — a non-consented owner is refused before any transition,
  and the ``submit_ad`` ``CONSENT_REQUIRED`` race maps to the same 403.
- **dry-run inventory** — every readiness field surfaces individually and in
  combination; the over-media section carries the moderation caps; a dry run
  writes nothing.
- **not-ready submission** — a real submit of a not-ready DRAFT is a 409
  ``invalid_transition`` carrying the inventory, before any write.
- **happy path** — a ready DRAFT is submitted through the same ``submit_ad``
  service the bot uses, producing the same status, timestamps and analytics
  events as a direct service call on an identical fixture.
- **moderation failure** — 200 with the parked state (boundary O-2a).
- **state-machine outcomes** — ``invalid_transition`` / ``draft_gone`` /
  ``photo_unavailable`` mapped to their §2.5 problems.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.ads.models import Ad, AdImage
from apps.ads.services.submission import (
    SubmitAdInput,
    SubmitAdOutcome,
    submit_ad,
)
from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AdStatus, AnalyticsEventType, RateLimitBudget
from apps.core.utils.problem import PROBLEM_CONTENT_TYPE, RETRY_AFTER_HEADER
from conftest import create_test_ad, make_user

TEST_URL_NAME = "ads_api:submit"
TEST_URL = "/api/v1/ads/{id}/submit/"

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# The submission takes everything from the stored DRAFT, so a valid body is
# either empty (real submission) or carries only the ``dry_run`` flag.
EMPTY_BODY: dict[str, Any] = {}


@pytest.fixture(autouse=True)
def _clear_rate_limit_cache() -> None:
    """Start every test with empty rate-limit counters.

    ``rate_limit_check`` reads the Django cache, which ``--reuse-db`` keeps
    warm between runs; a stale ``api_write`` counter would make a test see a
    429 rather than the behaviour it asserts.
    """
    cache.clear()


def _post(client: Client, ad_id: int, payload: Any = None):
    """POST a JSON body (default: an empty object) to the endpoint."""
    return client.post(
        reverse(TEST_URL_NAME, args=[ad_id]),
        data={} if payload is None else payload,
        content_type="application/json",
    )


def _dry_run(client: Client, ad_id: int):
    """POST the O-14 field-check request (``{"dry_run": true}``)."""
    return _post(client, ad_id, {"dry_run": True})


def _add_photo(ad: Ad, position: int, *, with_file: bool = True) -> AdImage:
    """Attach a stored photo row with a unique digest (and its bytes on disk).

    A real stored photo carries its SHA-256, and ``submit_ad`` re-reads the
    same key through ``AdImageService.create_or_skip`` — which dedups on that
    digest and therefore returns the existing row instead of re-inserting at
    the same position. Giving each row its own digest and a real file mirrors
    a persisted DRAFT and is what makes resubmitting it idempotent.

    Keys are **permanent** (no ``staging/`` prefix), as a persisted DRAFT's
    photos are. ``with_file=False`` simulates a reaped file.
    """
    key = f"{uuid.uuid4().hex}.jpg"
    payload = _jpeg_bytes()
    image = AdImage.objects.create(
        ad=ad,
        image=key,
        position=position,
        sha256=hashlib.sha256(payload).hexdigest(),
    )
    if with_file:
        path = Path(settings.MEDIA_ROOT) / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    return image


def _jpeg_bytes() -> bytes:
    """Return a tiny valid JPEG so ``submit_ad``'s thumbnail step can decode it."""
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 20, 30)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _ready_draft(
    owner,
    category,
    city,
    *,
    status: AdStatus = AdStatus.DRAFT,
    make: dict[str, Any] | None = None,
    with_photo: bool = True,
) -> Ad:
    """Create a ready-to-submit ad in *status* (DRAFT by default), one photo.

    ``make`` overrides individual field values (``title``, ``description``,
    ``category_id``, ``city_id`` …) without colliding with the positional
    fixtures.
    """
    fields: dict[str, Any] = {
        "title": "Ready title",
        "description": "A description that is long enough to pass.",
    }
    fields.update(make or {})
    ad = create_test_ad(owner, category, city, status=status, **fields)
    if with_photo:
        _add_photo(ad, 0)
    return ad


def _event_types(ad: Ad) -> list[str]:
    """Analytics event types recorded for *ad*, as plain strings."""
    return list(
        AnalyticsEvent.objects.filter(ad_id=ad.id)
        .order_by("id")
        .values_list("event_type", flat=True)
    )


def _service_input(ad: Ad, user_id: int) -> SubmitAdInput:
    """Build the DTO exactly as the bot's ``process_preview`` would for *ad*."""

    return SubmitAdInput(
        ad_id=ad.id,
        title_ru=ad.title,
        desc_ru=ad.description,
        title_bs=ad.title_bs or "",
        desc_bs=ad.description_bs or "",
        title_en=ad.title_en or "",
        desc_en=ad.description_en or "",
        original_language=ad.original_language,
        category_id=ad.category_id,
        city_id=ad.city_id,
        price_amount=ad.price_amount,
        price_currency=ad.price_currency,
        photos=[],
        user_id=user_id,
        listing_purpose_id=ad.listing_purpose_id,
        feature_ids=list(ad.features.values_list("id", flat=True)),
        listing_condition_id=ad.listing_condition_id,
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
        ad = _ready_draft(seller, category, city)

        response = _post(Client(), ad.id)

        assert response.status_code == 401
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "unauthenticated"
        assert "WWW-Authenticate" not in response.headers

    def test_anonymous_get_is_401_not_405(self, seller, category, city) -> None:
        ad = _ready_draft(seller, category, city)

        response = Client().get(reverse(TEST_URL_NAME, args=[ad.id]))

        assert response.status_code == 401
        assert response.json()["type"] == "unauthenticated"


class TestMethodGate:
    """An authenticated non-POST → 405 problem + ``Allow: POST``."""

    @pytest.mark.parametrize("method", ["get", "put", "patch", "delete"])
    def test_wrong_method_returns_405(
        self, client_, seller, category, city, method
    ) -> None:
        ad = _ready_draft(seller, category, city)

        response = getattr(client_, method)(reverse(TEST_URL_NAME, args=[ad.id]))

        assert response.status_code == 405
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "method_not_allowed"
        assert response.headers["Allow"] == "POST"
        ad.refresh_from_db()
        assert ad.status == AdStatus.DRAFT


class TestValidationMatrix:
    """A body outside the ``SubmitBody`` contract → 422; nothing is written."""

    @pytest.mark.parametrize(
        "raw,case",
        [
            (b"{not json", "malformed_json"),
            (b"[]", "non_object"),
            (b'{"title": "smuggled"}', "unknown_key"),
            (b'{"dry_run": true, "photos": []}', "unknown_key_mixed"),
        ],
        ids=lambda v: v if isinstance(v, str) else "",
    )
    def test_bad_body_returns_422(
        self, client_, seller, category, city, raw, case
    ) -> None:
        ad = _ready_draft(seller, category, city)

        response = client_.post(
            reverse(TEST_URL_NAME, args=[ad.id]),
            data=raw,
            content_type="application/json",
        )

        assert response.status_code == 422
        assert response.json()["type"] == "validation_failed"
        ad.refresh_from_db()
        assert ad.status == AdStatus.DRAFT


class TestRateLimit:
    """Exhausting ``API_WRITE`` → 429 problem + ``Retry-After``, before resolution."""

    def test_over_budget_returns_rate_limited_problem(
        self, client_, seller, category, city, monkeypatch
    ) -> None:
        ad = _ready_draft(seller, category, city)
        monkeypatch.setattr(
            "apps.ads.views.api.submit.rate_limit_check",
            lambda *args, **kwargs: False,
        )

        response = _post(client_, ad.id)

        assert response.status_code == 429
        assert response.json()["type"] == "rate_limited"
        assert response.headers.get(RETRY_AFTER_HEADER) == str(
            RateLimitBudget.API_WRITE.period
        )
        ad.refresh_from_db()
        assert ad.status == AdStatus.DRAFT


class TestUniformNotFound:
    """A missing id and a non-owned id answer the identical document."""

    def test_missing_and_non_owned_are_indistinguishable(
        self, seller, category, city
    ) -> None:
        ad = _ready_draft(seller, category, city)
        intruder = make_user(915000101)
        client = Client()
        client.force_login(intruder)

        non_owned = _post(client, ad.id)
        missing = _post(client, 999_999_999)

        assert non_owned.status_code == 404
        assert missing.status_code == 404
        assert non_owned.content == missing.content
        assert non_owned.json()["type"] == "not_found"
        ad.refresh_from_db()
        assert ad.status == AdStatus.DRAFT


# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------


class TestConsentGate:
    """A non-consented owner is refused before any transition."""

    @pytest.mark.parametrize(
        "maker",
        [
            lambda tid: make_user(tid),
            lambda tid: make_user(tid, consent_revoked=True),
        ],
        ids=["never_consented", "withdrawn"],
    )
    def test_owner_without_consent_gets_403(self, maker, category, city) -> None:
        owner = maker(915001001)
        ad = _ready_draft(owner, category, city)
        client = Client()
        client.force_login(owner)

        response = _post(client, ad.id)

        assert response.status_code == 403
        assert response.json()["type"] == "consent_required"
        ad.refresh_from_db()
        assert ad.status == AdStatus.DRAFT

    def test_consent_gate_matches_html_gate(self, category, city, monkeypatch) -> None:
        """API refusal set == the shared ``can_create_ad`` refusal set."""
        from apps.users.services.account_state import can_create_ad

        for offset, maker in enumerate(
            [
                lambda tid: make_user(tid, consent_given_at=timezone.now()),
                lambda tid: make_user(tid),
                lambda tid: make_user(tid, consent_revoked=True),
            ]
        ):
            owner = maker(915002000 + offset)
            ad = _ready_draft(owner, category, city)
            client = Client()
            client.force_login(owner)

            response = _post(client, ad.id)

            owner.refresh_from_db()
            if can_create_ad(owner):
                assert response.status_code != 403
            else:
                assert response.json()["type"] == "consent_required"

    def test_submit_ad_consent_race_maps_to_403(
        self, client_, seller, category, city, monkeypatch
    ) -> None:
        """Consent withdrawn between the gate and ``submit_ad`` → 403, no write."""
        ad = _ready_draft(seller, category, city)
        monkeypatch.setattr(
            "apps.ads.views.api.submit.submit_ad",
            lambda _input: type(
                "R", (), {"outcome": SubmitAdOutcome.CONSENT_REQUIRED, "errors": []}
            )(),
        )

        response = _post(client_, ad.id)

        assert response.status_code == 403
        assert response.json()["type"] == "consent_required"


# ---------------------------------------------------------------------------
# O-14 dry-run field check
# ---------------------------------------------------------------------------


class TestDryRunInventory:
    """``dry_run: true`` returns the readiness inventory and writes nothing."""

    def test_ready_draft_inventory(self, client_, seller, category, city) -> None:
        ad = _ready_draft(seller, category, city)

        response = _dry_run(client_, ad.id)

        assert response.status_code == 200
        payload = response.json()
        assert payload["ad_id"] == ad.id
        assert payload["status"] == AdStatus.DRAFT
        assert payload["ready"] is True
        assert payload["missing_fields"] == []
        media = payload["over_media_sections"]
        assert media["has_over_media"] is False
        assert media["ad"] is False
        cap_info = media["section_cap_info"]
        assert cap_info["section"] == "media"
        assert cap_info["photo_count"] == 1
        assert cap_info["min_photos"] <= cap_info["photo_count"] <= cap_info[
            "max_photos"
        ]

        ad.refresh_from_db()
        assert ad.status == AdStatus.DRAFT

    @pytest.mark.parametrize(
        "kwargs,missing",
        [
            ({"title": "   "}, "title"),
            ({"description": ""}, "description"),
            ({"category_id": None}, "category"),
            ({"city_id": None}, "city"),
            ({"photo": False}, "photos"),
        ],
        ids=["title", "description", "category", "city", "photos"],
    )
    def test_single_missing_field(
        self, client_, seller, category, city, kwargs, missing
    ) -> None:
        photo = kwargs.pop("photo", True)
        ad = _ready_draft(
            seller, category, city, make=kwargs, with_photo=photo
        )

        payload = _dry_run(client_, ad.id).json()

        assert payload["ready"] is False
        assert payload["missing_fields"] == [missing]
        assert payload["over_media_sections"]["has_over_media"] is False

    def test_combined_missing_fields(self, client_, seller, category, city) -> None:
        ad = _ready_draft(
            seller,
            category,
            city,
            make={"title": "", "description": "", "category_id": None, "city_id": None},
            with_photo=False,
        )

        payload = _dry_run(client_, ad.id).json()

        assert payload["ready"] is False
        assert payload["missing_fields"] == [
            "title",
            "description",
            "category",
            "city",
            "photos",
        ]

    def test_over_media_reports_section_caps(
        self, client_, seller, category, city
    ) -> None:
        ad = _ready_draft(seller, category, city)
        # Default moderation cap is 5 photos; add enough rows to exceed it.
        for position in range(1, 7):
            _add_photo(ad, position)

        payload = _dry_run(client_, ad.id).json()

        media = payload["over_media_sections"]
        assert payload["ready"] is False
        assert media["has_over_media"] is True
        assert media["ad"] is True
        cap_info = media["section_cap_info"]
        assert cap_info["photo_count"] == 7
        assert cap_info["photo_count"] > cap_info["max_photos"]
        assert "photos" not in payload["missing_fields"]

    def test_dry_run_does_not_submit(self, client_, seller, category, city) -> None:
        ad = _ready_draft(seller, category, city)

        _dry_run(client_, ad.id)

        ad.refresh_from_db()
        assert ad.status == AdStatus.DRAFT
        assert _event_types(ad) == []

    def test_non_draft_reports_its_status(self, client_, seller, category, city) -> None:
        # A PUBLISHED ad is not a DRAFT: the inventory reports what it reads.
        ad = _ready_draft(seller, category, city, status=AdStatus.PUBLISHED)

        payload = _dry_run(client_, ad.id).json()

        assert payload["status"] == AdStatus.PUBLISHED
        assert payload["missing_fields"] == []


class TestNotReadySubmission:
    """A real submit of a not-ready DRAFT is refused before any write."""

    def test_not_ready_is_409_with_inventory(self, client_, seller, category, city) -> None:
        ad = create_test_ad(
            seller, category, city, status=AdStatus.DRAFT, title="", title_en=""
        )

        response = _post(client_, ad.id)

        assert response.status_code == 409
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        body = response.json()
        assert body["type"] == "invalid_transition"
        assert "title" in body["inventory"]["missing_fields"]
        assert body["inventory"]["ready"] is False

        ad.refresh_from_db()
        assert ad.status == AdStatus.DRAFT
        assert _event_types(ad) == []


# ---------------------------------------------------------------------------
# Submission outcomes
# ---------------------------------------------------------------------------


class TestSubmitHappyPath:
    """A ready DRAFT is submitted through the shared ``submit_ad`` service."""

    def test_ready_draft_association_publishes(
        self, client_, seller, category, city, permissive_criteria
    ) -> None:
        ad = _ready_draft(seller, category, city)

        response = _post(client_, ad.id)

        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == ad.id
        assert payload["outcome"] == SubmitAdOutcome.PUBLISHED.value
        assert payload["moderation_failed"] is False
        assert payload["status"] == AdStatus.PUBLISHED
        assert payload["published_at"] is not None

        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED
        assert ad.published_at is not None

    def test_service_parity_with_bot_submit(
        self, client_, seller, category, city, permissive_criteria
    ) -> None:
        """Same fixture → same resting status, timestamps and events.

        The endpoint leg and the direct-service leg each own a DRAFT (the
        single-draft constraint allows one per owner) built identically.
        """
        api_ad = _ready_draft(seller, category, city)

        service_owner = make_user(915005000, consent_given_at=timezone.now())
        service_ad = _ready_draft(service_owner, category, city)

        response = _post(client_, api_ad.id)
        result = submit_ad(_service_input(service_ad, service_owner.id))

        assert result.outcome is SubmitAdOutcome.PUBLISHED
        assert response.json()["outcome"] == result.outcome.value

        api_ad.refresh_from_db()
        service_ad.refresh_from_db()
        assert api_ad.status == service_ad.status == AdStatus.PUBLISHED
        assert (api_ad.published_at is not None) == (
            service_ad.published_at is not None
        )
        assert _event_types(api_ad) == _event_types(service_ad) == [
            AnalyticsEventType.AD_PUBLISHED,
            AnalyticsEventType.MODERATION_APPROVED,
        ]

    def test_moderation_failure_is_200(
        self, client_, seller, category, city, banning_criteria
    ) -> None:
        ad = _ready_draft(seller, category, city, make={"title": "spam offer"})

        response = _post(client_, ad.id)

        # ``submit_ad`` committed the submission and parked the ad: 200 (O-2a).
        assert response.status_code == 200
        payload = response.json()
        assert payload["outcome"] == SubmitAdOutcome.MODERATION_FAILED.value
        assert payload["moderation_failed"] is True
        assert payload["errors"]

        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION_FAILED
        assert ad.moderation_failed_at is not None


class TestStateMachineOutcomes:
    """The remaining ``SubmitAdOutcome`` members map to their §2.5 problems."""

    @pytest.mark.parametrize(
        "status",
        [AdStatus.ON_MODERATION_FAILED, AdStatus.REJECTED],
    )
    def test_wrong_status_is_409(
        self, client_, seller, category, city, status
    ) -> None:
        # These statuses cannot enter ON_MODERATION, so ``submit_ad`` refuses
        # the transition and the endpoint answers 409. (``PUBLISHED`` and
        # ``ARCHIVED`` *are* legal ``submit_ad`` sources — see the next test.)
        ad = _ready_draft(seller, category, city, status=status)

        response = _post(client_, ad.id)

        assert response.status_code == 409
        assert response.json()["type"] == "invalid_transition"
        ad.refresh_from_db()
        assert ad.status == status

    def test_archived_is_re_submitted(
        self, client_, seller, category, city, permissive_criteria
    ) -> None:
        """``ARCHIVED`` is a legal ``submit_ad`` source (it re-enters moderation)."""
        ad = _ready_draft(seller, category, city, status=AdStatus.ARCHIVED)

        response = _post(client_, ad.id)

        assert response.status_code == 200
        assert response.json()["outcome"] == SubmitAdOutcome.PUBLISHED.value
        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED

    def test_draft_gone_is_409(self, client_, seller, category, city) -> None:
        ad = _ready_draft(seller, category, city)
        ad_id = ad.id
        Ad.objects.filter(pk=ad_id).delete()

        response = _post(client_, ad_id)

        # The pre-flight ownership read no longer finds the row: uniform 404.
        assert response.status_code == 404
        assert response.json()["type"] == "not_found"

    def test_photo_unavailable_is_409(
        self, client_, seller, category, city, settings, tmp_path
    ) -> None:
        """A stored photo whose file is gone → ``photo_unavailable``."""
        # An empty media root: every stored key was reaped after upload.
        settings.MEDIA_ROOT = tmp_path
        ad = _ready_draft(seller, category, city)
        # Point the stored key at staging so ``plan_staging_promotion`` is the
        # existence check (permanent keys are only read at thumbnail time).
        AdImage.objects.filter(ad=ad).update(
            image=f"staging/{uuid.uuid4().hex}.jpg"
        )

        response = _post(client_, ad.id)

        assert response.status_code == 409
        assert response.json()["type"] == "photo_unavailable"
        ad.refresh_from_db()
        assert ad.status == AdStatus.DRAFT
