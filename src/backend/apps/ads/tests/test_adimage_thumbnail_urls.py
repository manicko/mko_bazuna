"""
Unit tests for AdImage thumbnail URL properties.

Verifies the contract of thumbnail_small_url, thumbnail_medium_url,
and thumbnail_large_url — returns MEDIA_URL + key when the field is
set, None when it is null or blank.

Uses in-memory AdImage instances (no DB).
"""

from __future__ import annotations

import pytest

from apps.ads.models import AdImage

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _media_url(settings) -> None:
    """Set MEDIA_URL to /media/ for all tests in this module."""
    settings.MEDIA_URL = "/media/"


# ── thumbnail_small_url ─────────────────────────────────────────────


def test_thumbnail_small_url_returns_url_when_set() -> None:
    """Property returns MEDIA_URL + key when thumbnail_small is set."""
    img = AdImage.__new__(AdImage)
    img.thumbnail_small = "abc-small.jpg"
    assert img.thumbnail_small_url == "/media/abc-small.jpg"


def test_thumbnail_small_url_returns_none_when_null() -> None:
    """Property returns None when thumbnail_small is None."""
    img = AdImage.__new__(AdImage)
    img.thumbnail_small = None
    assert img.thumbnail_small_url is None


def test_thumbnail_small_url_returns_none_when_blank() -> None:
    """Property returns None when thumbnail_small is blank string."""
    img = AdImage.__new__(AdImage)
    img.thumbnail_small = ""
    assert img.thumbnail_small_url is None


# ── thumbnail_medium_url ────────────────────────────────────────────


def test_thumbnail_medium_url_returns_url_when_set() -> None:
    """Property returns MEDIA_URL + key when thumbnail_medium is set."""
    img = AdImage.__new__(AdImage)
    img.thumbnail_medium = "abc-medium.jpg"
    assert img.thumbnail_medium_url == "/media/abc-medium.jpg"


def test_thumbnail_medium_url_returns_none_when_null() -> None:
    """Property returns None when thumbnail_medium is None."""
    img = AdImage.__new__(AdImage)
    img.thumbnail_medium = None
    assert img.thumbnail_medium_url is None


# ── thumbnail_large_url ─────────────────────────────────────────────


def test_thumbnail_large_url_returns_url_when_set() -> None:
    """Property returns MEDIA_URL + key when thumbnail_large is set."""
    img = AdImage.__new__(AdImage)
    img.thumbnail_large = "abc-large.jpg"
    assert img.thumbnail_large_url == "/media/abc-large.jpg"


def test_thumbnail_large_url_returns_none_when_null() -> None:
    """Property returns None when thumbnail_large is None."""
    img = AdImage.__new__(AdImage)
    img.thumbnail_large = None
    assert img.thumbnail_large_url is None


# ── Cross-field isolation ───────────────────────────────────────────


def test_thumbnail_urls_do_not_interfere() -> None:
    """Each property returns the correct field independently."""
    img = AdImage.__new__(AdImage)
    img.thumbnail_small = "s.jpg"
    img.thumbnail_medium = "m.jpg"
    img.thumbnail_large = "l.jpg"

    assert img.thumbnail_small_url == "/media/s.jpg"
    assert img.thumbnail_medium_url == "/media/m.jpg"
    assert img.thumbnail_large_url == "/media/l.jpg"


def test_all_thumbnail_urls_return_none_when_all_empty() -> None:
    """All three properties return None when no thumbnails are set."""
    img = AdImage.__new__(AdImage)
    img.thumbnail_small = None
    img.thumbnail_medium = None
    img.thumbnail_large = None

    assert img.thumbnail_small_url is None
    assert img.thumbnail_medium_url is None
    assert img.thumbnail_large_url is None
