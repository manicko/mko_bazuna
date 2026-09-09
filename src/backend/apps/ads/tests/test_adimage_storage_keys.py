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


def test_storage_keys_matches_truthy_filter() -> None:
    """storage_keys() equals [image, ...] filtered to truthy values."""
    img = AdImage.__new__(AdImage)
    img.image = "abc.jpg"
    img.thumbnail_small = "abc-small.jpg"
    img.thumbnail_medium = None
    img.thumbnail_large = "abc-large.jpg"
    all_fields = [
        img.image,
        img.thumbnail_small,
        img.thumbnail_medium,
        img.thumbnail_large,
    ]
    expected = [k for k in all_fields if k]
    assert img.storage_keys() == expected
