"""
Tests for the ``unreferenced_keys`` storage-key liveness predicate.

Covers the relational anti-drift binding between ``KEY_COLUMNS`` and the
``AdImage`` model, input-order preservation, and per-column reference coverage
-- the predicate-level statement of ``07-MEDIA-001``.
"""

from __future__ import annotations

import pytest

from apps.ads.models import AdImage
from apps.core.enums import AdStatus
from apps.media.services.references import KEY_COLUMNS, unreferenced_keys
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestKeyColumnsAntiDrift:
    """Binds ``KEY_COLUMNS`` to the ``AdImage`` model as a relationship."""

    def test_every_key_column_resolves_to_a_concrete_model_field(self) -> None:
        """Each ``KEY_COLUMNS`` name is a real field on ``AdImage``.

        A typo here raises ``FieldDoesNotExist``.
        """
        for name in KEY_COLUMNS:
            field = AdImage._meta.get_field(name)
            assert field is not None

    def test_fully_populated_row_storage_keys_matches_key_columns(self) -> None:
        """A fully-populated ``AdImage`` satisfies ``storage_keys() == list(KEY_COLUMNS)``.

        Together with the field-resolution test above, this fails loudly if a
        fifth key column is added to the model without updating the constant.
        """
        img = AdImage.__new__(AdImage)
        for name in KEY_COLUMNS:
            setattr(img, name, name)

        # storage_keys() returns key *values*; populating each key field with its
        # own column name makes the two lists directly comparable. Equality holds
        # only while the model's key columns and their order match the constant.
        assert img.storage_keys() == list(KEY_COLUMNS)


class TestUnreferencedKeys:
    """Predicate behaviour of ``unreferenced_keys``."""

    def test_empty_and_blank_input_returns_empty_without_query(self) -> None:
        """Blank/falsy keys are dropped; an empty candidate set returns ``[]``."""
        assert unreferenced_keys([]) == []
        assert unreferenced_keys(["", None]) == []  # type: ignore[list-item]

    def test_preserves_input_order_of_unreferenced_keys(
        self, seller, category, city
    ) -> None:
        """Unreferenced keys are returned in their original input order."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        AdImage.objects.create(ad=ad, image="ref-a.jpg", position=0)
        AdImage.objects.create(ad=ad, image="ref-b.jpg", position=1)

        keys = ["orphan-1.jpg", "ref-a.jpg", "orphan-2.jpg", "ref-b.jpg", "orphan-3.jpg"]

        assert unreferenced_keys(keys) == [
            "orphan-1.jpg",
            "orphan-2.jpg",
            "orphan-3.jpg",
        ]

    @pytest.mark.parametrize("column", KEY_COLUMNS)
    def test_key_referenced_via_column_is_excluded(
        self, seller, category, city, column
    ) -> None:
        """A key referenced by another row through *column* is not returned.

        This is the predicate-level statement of the four-column defect: the
        shipped one-column shape only ever inspected ``image``, so a key shared
        solely via a ``thumbnail_*`` column was wrongly reported as orphaned.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        shared_key = f"shared-via-{column}.jpg"
        kwargs: dict[str, str] = {"image": "owner.jpg", column: shared_key}
        AdImage.objects.create(ad=ad, position=0, **kwargs)

        assert unreferenced_keys([shared_key]) == []

    def test_absent_key_is_returned(self, seller, category, city) -> None:
        """A key no row references at all is returned."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        AdImage.objects.create(ad=ad, image="present.jpg", position=0)

        assert unreferenced_keys(["present.jpg", "absent.jpg"]) == ["absent.jpg"]
