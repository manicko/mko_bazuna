"""
Unit tests for AdImage.storage_keys().

Verifies that storage_keys() returns the main image key plus all
non-empty thumbnail keys, ensuring complete filesystem erasure of
derived thumbnail files.

Uses in-memory AdImage instances (no DB).
"""

from __future__ import annotations

import pytest

from apps.ads.models import AdImage
from apps.media.storage_keys import KEY_COLUMNS

pytestmark = [pytest.mark.unit]


def test_storage_keys_returns_image_only_when_thumbnails_none() -> None:
    """Returns [image] when all thumbnails are None."""
    img = AdImage.__new__(AdImage)
    img.image = "abc.jpg"
    img.thumbnail_small = None
    img.thumbnail_medium = None
    img.thumbnail_large = None
    assert img.storage_keys() == ["abc.jpg"]


def test_storage_keys_returns_image_only_when_thumbnails_empty() -> None:
    """Returns [image] when all thumbnails are empty strings."""
    img = AdImage.__new__(AdImage)
    img.image = "abc.jpg"
    img.thumbnail_small = ""
    img.thumbnail_medium = ""
    img.thumbnail_large = ""
    assert img.storage_keys() == ["abc.jpg"]


def test_storage_keys_returns_all_keys_when_thumbnails_set() -> None:
    """Returns all 4 keys when all thumbnails are set."""
    img = AdImage.__new__(AdImage)
    img.image = "abc.jpg"
    img.thumbnail_small = "abc-small.jpg"
    img.thumbnail_medium = "abc-medium.jpg"
    img.thumbnail_large = "abc-large.jpg"
    assert img.storage_keys() == [
        "abc.jpg",
        "abc-small.jpg",
        "abc-medium.jpg",
        "abc-large.jpg",
    ]


def test_storage_keys_returns_only_set_keys_when_some_missing() -> None:
    """Returns only truthy keys when some thumbnails are None or empty."""
    img = AdImage.__new__(AdImage)
    img.image = "abc.jpg"
    img.thumbnail_small = "abc-small.jpg"
    img.thumbnail_medium = None
    img.thumbnail_large = ""
    assert img.storage_keys() == ["abc.jpg", "abc-small.jpg"]


def test_storage_keys_returns_nonempty_columns_in_order() -> None:
    """storage_keys() returns the non-empty columns in KEY_COLUMNS order.

    Independent oracle: the expected list is hardcoded here, NOT derived from
    KEY_COLUMNS or from the instance's own attributes. This catches wrong
    column-set (missing/extra keys) and wrong order (transposed columns) —
    both of which a KEY_COLUMNS-derived expectation would miss.
    """
    img = AdImage.__new__(AdImage)
    img.image = "a.jpg"
    img.thumbnail_small = ""
    img.thumbnail_medium = "a-medium.jpg"
    img.thumbnail_large = "a-large.jpg"
    assert img.storage_keys() == ["a.jpg", "a-medium.jpg", "a-large.jpg"]


def test_storage_keys_omits_empty_image() -> None:
    """storage_keys() returns only non-empty thumbnail keys when image is blank.

    Production skips falsy values via ``if value:`` (L767), so a blank/None
    primary ``image`` key is excluded while populated thumbnails are retained.
    """
    img = AdImage.__new__(AdImage)
    img.image = ""
    img.thumbnail_small = "small.jpg"
    img.thumbnail_medium = None
    img.thumbnail_large = "large.jpg"
    assert img.storage_keys() == ["small.jpg", "large.jpg"]


def test_key_columns_match_model_fields() -> None:
    """Every name in KEY_COLUMNS is a real AdImage field, in order.

    Guards the cross-module invariant: if a field is renamed/removed in the
    model without updating KEY_COLUMNS (or vice-versa), storage_keys() would
    silently skip the field. KEY_COLUMNS is a ``tuple[str, ...]``.
    """
    field_names = {f.name for f in AdImage._meta.get_fields()}
    for col in KEY_COLUMNS:
        assert col in field_names, (
            f"KEY_COLUMNS references {col!r} which is not an AdImage field"
        )
    assert list(KEY_COLUMNS) == [
        "image",
        "thumbnail_small",
        "thumbnail_medium",
        "thumbnail_large",
    ]
