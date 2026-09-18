"""
Shared fixtures for ads/tests.

These were extracted from test_catalog_filters.py to support the split into
per-concern test files. Each fixture creates a lookup group with its items.
"""

from __future__ import annotations

import pytest

from apps.lookups.models import LookupGroup, LookupItem


def _create_lookup_group(
    code: str, items: dict[str, dict[str, str]]
) -> dict[str, LookupItem]:
    """Create a LookupGroup with the given items and return a slug-keyed dict."""
    group = LookupGroup.objects.create(code=code, is_system=True)
    result: dict[str, LookupItem] = {}
    for slug, name_i18n in items.items():
        result[slug] = LookupItem.objects.create(
            group=group,
            slug=slug,
            name_i18n=name_i18n,
            is_active=True,
        )
    return result


@pytest.fixture
def purpose_lookup() -> dict[str, LookupItem]:
    """Create the ``listing_purpose`` group with sell/rent items."""
    return _create_lookup_group(
        "listing_purpose",
        {
            "sell": {"ru": "Продажа", "en": "Sell"},
            "rent": {"ru": "Аренда", "en": "Rent"},
        },
    )


@pytest.fixture
def feature_lookup() -> dict[str, LookupItem]:
    """Create the ``listing_feature`` group with genuine multi-select features.

    ``new``/``used`` are intentionally absent: they live in the
    ``listing_condition`` group (see ``condition_lookup``) and are excluded
    from the feature multi-select (Spec 12 / REQ-12.3).
    """
    return _create_lookup_group(
        "listing_feature",
        {
            "delivery": {"ru": "Доставка", "en": "Delivery"},
            "negotiable": {"ru": "Торг уместен", "en": "Negotiable"},
        },
    )


@pytest.fixture
def condition_lookup() -> dict[str, LookupItem]:
    """Create the ``listing_condition`` group with new/used items."""
    return _create_lookup_group(
        "listing_condition",
        {
            "new": {"ru": "Новый", "en": "New"},
            "used": {"ru": "Б/У", "en": "Used"},
        },
    )
