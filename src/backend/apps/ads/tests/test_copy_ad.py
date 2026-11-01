"""
Tests for the copy_ad service.

Verifies the ad-duplication contract (Spec: ad re-listing):
    - A new DRAFT ad is created with textual fields, category, city, and
      listing_purpose copied from the source.
    - Features (M2M) and images (new rows, same storage keys) are transferred.
    - Image positions are preserved.
    - Ownership is enforced (PermissionError for non-owners).
    - A missing source raises Ad.DoesNotExist.
    - An existing DRAFT owned by the seller is replaced by the copy, so the
      seller ends with exactly one DRAFT (single-draft policy shared with
      ``create_draft_ad``).

The source ad must be in a non-DRAFT status so a copy from it is
unambiguous, though ``copy_ad`` itself does not require this: if the seller
already holds a DRAFT it is deleted inside the same transaction before the
copy is created. Storage keys use ``f"{uuid.uuid4().hex}.jpg"`` to satisfy
``KEY_FORMAT_REGEX``.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.ads.models import Ad, AdImage
from apps.ads.services.copy_service import copy_ad
from apps.core.enums import AdStatus, RateLimitBudget
from apps.core.utils.problem import PROBLEM_CONTENT_TYPE, RETRY_AFTER_HEADER
from apps.lookups.models import LookupGroup, LookupItem
from conftest import create_test_ad, make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def purpose_item() -> LookupItem:
    """Create a listing_purpose lookup item."""
    group = LookupGroup.objects.create(code="listing_purpose", is_system=True)
    return LookupItem.objects.create(
        group=group,
        slug="sell",
        name_i18n={"ru": "Продажа", "en": "Sell"},
        is_active=True,
    )


@pytest.fixture
def feature_items() -> list[LookupItem]:
    """Create two listing_feature lookup items."""
    group = LookupGroup.objects.create(code="listing_feature", is_system=True)
    return [
        LookupItem.objects.create(
            group=group,
            slug="delivery",
            name_i18n={"ru": "Доставка", "en": "Delivery"},
            is_active=True,
        ),
        LookupItem.objects.create(
            group=group,
            slug="negotiable",
            name_i18n={"ru": "Торг уместен", "en": "Negotiable"},
            is_active=True,
        ),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCopyAd:
    """Coverage for apps.ads.services.copy_service.copy_ad."""

    def test_copy_ad_replaces_existing_draft(
        self, seller, category, city, purpose_item: LookupItem
    ) -> None:
        """A seller with an existing DRAFT ends with exactly one DRAFT — the copy."""
        source = create_test_ad(
            seller,
            category,
            city,
            listing_purpose=purpose_item,
            status=AdStatus.PUBLISHED,
        )
        existing_draft = create_test_ad(
            seller, category, city, status=AdStatus.DRAFT
        )

        new_ad = copy_ad(source.id, seller.id)
        new_ad.refresh_from_db()

        # The invariant: a draft is returned, and it is the copy.
        assert new_ad.pk != source.pk
        assert new_ad.pk != existing_draft.pk
        assert new_ad.status == AdStatus.DRAFT

        # Exactly one DRAFT remains for this seller, and it is the copy.
        drafts = list(
            Ad.objects.filter(user=seller, status=AdStatus.DRAFT).values_list(
                "id", flat=True
            )
        )
        assert drafts == [new_ad.id]

    def test_copy_ad_happy_path(
        self,
        seller,
        category,
        city,
        purpose_item: LookupItem,
        feature_items: list[LookupItem],
    ) -> None:
        """All textual fields, FKs, features (M2M), and images are copied; DRAFT status."""
        source = create_test_ad(
            seller,
            category,
            city,
            title="Original Title",
            title_en="Original Title EN",
            title_bs="Original Title BS",
            description="Original Description",
            description_en="Original Description EN",
            description_bs="Original Description BS",
            original_language="en",
            listing_purpose=purpose_item,
            status=AdStatus.PUBLISHED,
        )
        source.features.add(*feature_items)

        key_a = f"{uuid.uuid4().hex}.jpg"
        key_b = f"{uuid.uuid4().hex}.jpg"
        AdImage.objects.create(ad=source, image=key_a, position=0)
        AdImage.objects.create(ad=source, image=key_b, position=1)

        new_ad = copy_ad(source.id, seller.id)
        new_ad.refresh_from_db()

        # New row, DRAFT status (model default — no timestamp required).
        assert new_ad.pk != source.pk
        assert new_ad.status == AdStatus.DRAFT

        # Textual fields — copied verbatim (no title_ru / description_ru columns).
        assert new_ad.title == source.title
        assert new_ad.title_en == source.title_en
        assert new_ad.title_bs == source.title_bs
        assert new_ad.description == source.description
        assert new_ad.description_en == source.description_en
        assert new_ad.description_bs == source.description_bs
        assert new_ad.original_language == source.original_language

        # Foreign keys and ownership.
        assert new_ad.user_id == seller.id
        assert new_ad.category_id == source.category_id
        assert new_ad.city_id == source.city_id
        assert new_ad.listing_purpose_id == source.listing_purpose_id

        # Features M2M.
        assert set(new_ad.features.values_list("id", flat=True)) == set(
            source.features.values_list("id", flat=True)
        )

        # Images — same storage keys, same positions.
        new_images = list(new_ad.images.order_by("position"))
        source_images = list(source.images.order_by("position"))
        assert len(new_images) == len(source_images) == 2
        for new_img, src_img in zip(new_images, source_images, strict=True):
            assert new_img.image == src_img.image
            assert new_img.position == src_img.position

    def test_copy_ad_non_owner_raises_permission_error(
        self, seller, user, category, city
    ) -> None:
        """A seller who does not own the source ad raises PermissionError."""
        source = create_test_ad(user, category, city, status=AdStatus.PUBLISHED)

        with pytest.raises(PermissionError):
            copy_ad(source.id, seller.id)

    def test_copy_ad_source_not_found_raises_do_not_exist(self, seller) -> None:
        """A nonexistent source_ad_id raises Ad.DoesNotExist."""
        with pytest.raises(Ad.DoesNotExist):
            copy_ad(999999, seller.id)

    def test_copy_ad_image_positions_preserved(
        self, seller, category, city
    ) -> None:
        """Image positions — including non-sequential gaps — are preserved on copy."""
        source = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        positions = [0, 2, 5]
        keys = [f"{uuid.uuid4().hex}.jpg" for _ in positions]
        for key, pos in zip(keys, positions, strict=True):
            AdImage.objects.create(ad=source, image=key, position=pos)

        new_ad = copy_ad(source.id, seller.id)

        new_images = list(new_ad.images.order_by("position"))
        assert [img.position for img in new_images] == positions
        assert [img.image for img in new_images] == keys

    def test_copy_ad_features_m2m_copied(
        self, seller, category, city, feature_items: list[LookupItem]
    ) -> None:
        """Features attached to the source are transferred to the copy."""
        source = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        source.features.add(*feature_items)

        new_ad = copy_ad(source.id, seller.id)

        assert set(new_ad.features.values_list("id", flat=True)) == set(
            source.features.values_list("id", flat=True)
        )


# ---------------------------------------------------------------------------
# S4.6 — POST /api/v1/ads/{id}/copy/ (plan §2.4 row 10)
# ---------------------------------------------------------------------------

_COPY_URL_NAME = "ads_api:copy"


def _copy_post(client: Client, ad_id: int, payload: Any = None):
    """POST to the copy endpoint (JSON body by default: an empty object)."""
    return client.post(
        reverse(_COPY_URL_NAME, args=[ad_id]),
        data={} if payload is None else payload,
        content_type="application/json",
    )


@pytest.fixture(autouse=True)
def _clear_rate_limit_cache() -> None:
    """Start every test in this module with empty rate-limit counters."""
    cache.clear()


@pytest.fixture
def client_(seller) -> Client:
    """Django test client authenticated as the ``seller`` fixture."""
    client = Client()
    client.force_login(seller)
    return client


class TestCopyEndpointPipeline:
    """401 / 405 / 422 / 429 and the uniform 404, in the mandated order."""

    def test_anonymous_post_returns_401_problem(
        self, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        response = _copy_post(Client(), ad.id)

        assert response.status_code == 401
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "unauthenticated"
        assert "WWW-Authenticate" not in response.headers

    def test_anonymous_get_is_401_not_405(self, seller, category, city) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        response = Client().get(reverse(_COPY_URL_NAME, args=[ad.id]))

        assert response.status_code == 401
        assert response.json()["type"] == "unauthenticated"

    @pytest.mark.parametrize("method", ["get", "put", "patch", "delete"])
    def test_wrong_method_returns_405(
        self, client_, seller, category, city, method
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        response = getattr(client_, method)(reverse(_COPY_URL_NAME, args=[ad.id]))

        assert response.status_code == 405
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "method_not_allowed"
        assert response.headers["Allow"] == "POST"
        assert Ad.objects.filter(user=seller, status=AdStatus.DRAFT).count() == 0

    @pytest.mark.parametrize(
        "raw,case",
        [
            (b"{not json", "malformed_json"),
            (b"[]", "non_object"),
            (b'{"title": "smuggled"}', "unknown_key"),
        ],
        ids=lambda v: v if isinstance(v, str) else "",
    )
    def test_bad_body_returns_422(
        self, client_, seller, category, city, raw, case
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        response = client_.post(
            reverse(_COPY_URL_NAME, args=[ad.id]),
            data=raw,
            content_type="application/json",
        )

        assert response.status_code == 422
        assert response.json()["type"] == "validation_failed"
        assert Ad.objects.filter(user=seller, status=AdStatus.DRAFT).count() == 0

    def test_over_budget_returns_rate_limited_problem(
        self, client_, seller, category, city, monkeypatch
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        monkeypatch.setattr(
            "apps.ads.views.api.copy.rate_limit_check",
            lambda *args, **kwargs: False,
        )

        response = _copy_post(client_, ad.id)

        assert response.status_code == 429
        assert response.json()["type"] == "rate_limited"
        assert response.headers.get(RETRY_AFTER_HEADER) == str(
            RateLimitBudget.API_WRITE.period
        )
        assert Ad.objects.filter(user=seller, status=AdStatus.DRAFT).count() == 0

    def test_missing_and_non_owned_are_indistinguishable(
        self, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        intruder = make_user(916000001)
        client = Client()
        client.force_login(intruder)

        non_owned = _copy_post(client, ad.id)
        missing = _copy_post(client, 999_999_999)

        assert non_owned.status_code == 404
        assert missing.status_code == 404
        assert non_owned.content == missing.content
        assert non_owned.json()["type"] == "not_found"
        # No copy leaked to the intruder, and no draft appeared for the source
        # owner either.
        assert Ad.objects.filter(user=intruder).count() == 0
        assert Ad.objects.filter(user=seller, status=AdStatus.DRAFT).count() == 0


class TestCopyEndpointHappyPath:
    """A copy produces a new DRAFT and matches the shared service result."""

    def test_copy_published_ad_creates_new_draft(
        self, client_, seller, category, city
    ) -> None:
        source = create_test_ad(
            seller,
            category,
            city,
            title="Original title",
            description="Original description",
            status=AdStatus.PUBLISHED,
            price=250,
        )

        response = _copy_post(client_, source.id)

        assert response.status_code == 200
        payload = response.json()
        new_id = payload["id"]
        assert new_id != source.id
        assert payload["source_ad_id"] == source.id
        assert payload["outcome"] == "copied"
        assert payload["status"] == AdStatus.DRAFT
        assert payload["title"] == source.title
        assert payload["description"] == source.description
        assert payload["category"]["slug"] == source.category.slug

        new_ad = Ad.objects.get(id=new_id)
        assert new_ad.user_id == seller.id
        assert new_ad.status == AdStatus.DRAFT
        # Reset: the source's publication history is not carried over.
        assert new_ad.published_at is None
        assert new_ad.archived_at is None
        assert new_ad.rejected_at is None
        assert new_ad.moderation_failed_at is None
        assert new_ad.deleted_at is None
        # The source keeps its own history untouched.
        source.refresh_from_db()
        assert source.status == AdStatus.PUBLISHED
        assert source.published_at is not None

    def test_copy_archived_ad_creates_new_draft(
        self, client_, seller, category, city
    ) -> None:
        source = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        source.transition_to(AdStatus.ARCHIVED)

        response = _copy_post(client_, source.id)

        assert response.status_code == 200
        new_ad = Ad.objects.get(id=response.json()["id"])
        assert new_ad.status == AdStatus.DRAFT
        assert new_ad.archived_at is None

    def test_copied_fields_match_service_tier(
        self, client_, seller, category, city
    ) -> None:
        """The endpoint's new draft matches a direct ``copy_ad`` call field-by-field."""
        source = create_test_ad(
            seller,
            category,
            city,
            title="Shared title",
            description="Shared description",
            title_en="Shared title EN",
            status=AdStatus.PUBLISHED,
        )
        key = f"{uuid.uuid4().hex}.jpg"
        AdImage.objects.create(ad=source, image=key, position=0)

        service_owner = make_user(916001000, consent_given_at=timezone.now())
        service_source = create_test_ad(
            service_owner,
            category,
            city,
            title="Shared title",
            description="Shared description",
            title_en="Shared title EN",
            status=AdStatus.PUBLISHED,
        )
        AdImage.objects.create(ad=service_source, image=key, position=0)

        response = _copy_post(client_, source.id)
        service_copy = copy_ad(service_source.id, service_owner.id)

        api_copy = Ad.objects.get(id=response.json()["id"])
        for field in ("title", "title_en", "description", "original_language"):
            assert getattr(api_copy, field) == getattr(service_copy, field)
        assert api_copy.category_id == service_copy.category_id
        assert api_copy.city_id == service_copy.city_id
        assert (
            api_copy.images.count()
            == service_copy.images.count()
            == 1  # noqa: PLR2004 - one photo on each side
        )
        assert list(api_copy.images.values_list("image", flat=True)) == [
            key
        ]

    def test_copy_replaces_the_sellers_existing_draft(
        self, client_, seller, category, city
    ) -> None:
        """Single-draft policy: the copy replaces the seller's current DRAFT."""
        source = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        existing = create_test_ad(seller, category, city, status=AdStatus.DRAFT)

        response = _copy_post(client_, source.id)

        assert response.status_code == 200
        new_id = response.json()["id"]
        drafts = list(
            Ad.objects.filter(user=seller, status=AdStatus.DRAFT).values_list(
                "id", flat=True
            )
        )
        assert drafts == [new_id]
        assert not Ad.objects.filter(id=existing.id).exists()

    def test_copy_is_owned_and_visible_only_to_its_owner(
        self, client_, seller, user, category, city
    ) -> None:
        source = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        response = _copy_post(client_, source.id)

        new_ad = Ad.objects.get(id=response.json()["id"])
        other = Client()
        other.force_login(user)
        # Another seller cannot see or copy the new draft.
        assert _copy_post(other, new_ad.id).status_code == 404
        assert new_ad.user_id == seller.id