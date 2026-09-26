"""Tests for the SEEDABLE_AD_STATUSES set derived from the AdStatus enum."""

from __future__ import annotations

from apps.core.enums import SEEDABLE_AD_STATUSES, AdStatus


def test_seedable_statuses_has_exact_value_set() -> None:
    """The seedable set covers the five statuses used by the seed pipeline."""
    assert {s.value for s in SEEDABLE_AD_STATUSES} == {
        "draft",
        "on_moderation",
        "published",
        "rejected",
        "archived",
    }


def test_on_moderation_failed_excluded() -> None:
    """ON_MODERATION_FAILED is not seedable."""
    assert AdStatus.ON_MODERATION_FAILED not in SEEDABLE_AD_STATUSES


def test_deleted_excluded() -> None:
    """DELETED is not seedable."""
    assert AdStatus.DELETED not in SEEDABLE_AD_STATUSES


def test_seedable_statuses_len() -> None:
    """There are exactly five seedable statuses."""
    assert len(SEEDABLE_AD_STATUSES) == 5
