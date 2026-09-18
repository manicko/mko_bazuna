"""
Tests for the copy_ad service.

Verifies the ad-duplication contract (Spec: ad re-listing):
    - A new DRAFT ad is created with textual fields, category, city, and
      listing_purpose copied from the source.
    - Features (M2M) and images (new rows, same storage keys) are transferred.
    - Image positions are preserved.
    - Ownership is enforced (PermissionError for non-owners).
    - A missing source raises Ad.DoesNotExist.

The source ad must be in a non-DRAFT status because of the
``uq_ads_single_draft_per_user`` unique constraint — the seller cannot have
an existing DRAFT when ``copy_ad`` runs. Storage keys use
``f"{uuid.uuid4().hex}.jpg"`` to satisfy ``KEY_FORMAT_REGEX``.
"""

from __future__ import annotations

import uuid

import pytest

from apps.ads.models import Ad, AdImage
from apps.ads.services.copy_service import copy_ad
from apps.core.enums import AdStatus
from apps.lookups.models import LookupGroup, LookupItem
from conftest import create_test_ad

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
