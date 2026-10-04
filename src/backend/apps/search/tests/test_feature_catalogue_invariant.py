"""
Guard test for the ``?features=`` catalogue invariant (08-SRCH-001).

Q2 was resolved 2026-10-03 (option (b)): the ``?features=`` bound is **not** a
hard-coded number. It is the catalogue invariant *"the resolved feature set for
any category"*, measured at seed volume, plus stated headroom, and this guard
test is what keeps the ceiling honest as the catalogue grows.

If a category ever resolves more features than ``MAX_FEATURE_FILTER_SLUGS``
allows, this test fails in CI with a named offending category — rather than a
400 at runtime for a query a user could legitimately build from the filter UI.

The measured maximum is pinned to ``FEATURE_CATALOGUE_MAX_AT_SEED`` so the
constant cannot be inflated without a deliberate, reviewed edit.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command

from apps.ads.services.listings_query import (
    FEATURE_CATALOGUE_MAX_AT_SEED,
    MAX_FEATURE_FEATURES_HEADROOM,
    MAX_FEATURE_FILTER_SLUGS,
)
from apps.categories.models import Category
from apps.categories.services.lookup_resolution import CategoryLookupResolver
from apps.locations.models import City

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_catalogue_invariant_is_derived_from_measurement() -> None:
    """The ceiling is the measured maximum plus the stated headroom."""
    assert MAX_FEATURE_FILTER_SLUGS == (
        FEATURE_CATALOGUE_MAX_AT_SEED + MAX_FEATURE_FEATURES_HEADROOM
    ), (
        "MAX_FEATURE_FILTER_SLUGS must equal FEATURE_CATALOGUE_MAX_AT_SEED + "
        "MAX_FEATURE_FEATURES_HEADROOM (08-SRCH-001, Q2 option (b))"
    )
    assert MAX_FEATURE_FEATURES_HEADROOM > 0, "headroom must be stated and positive"


def test_every_category_resolves_within_the_invariant() -> None:
    """No category's resolved feature set exceeds the invariant at seed volume.

    Loads the canonical ``categories.yaml`` (the seed catalogue) and measures
    ``CategoryLookupResolver.get_resolved_features`` for every category. The
    measured maximum must equal ``FEATURE_CATALOGUE_MAX_AT_SEED`` and stay
    within ``MAX_FEATURE_FILTER_SLUGS``.
    """
    # The load_catalog post-load guard requires at least one City row.
    City.objects.get_or_create(slug="invariant-probe-city", defaults={"name": "Probe"})
    call_command("load_catalog", "--no-rewrite")

    categories = list(Category.objects.all())
    assert categories, "the seed catalogue must define categories"

    measured: dict[str, int] = {}
    for category in categories:
        measured[category.slug] = len(
            CategoryLookupResolver.get_resolved_features(category)
        )

    worst_slug = max(measured, key=measured.__getitem__)
    worst = measured[worst_slug]

    assert worst <= MAX_FEATURE_FILTER_SLUGS, (
        f"category '{worst_slug}' resolves {worst} features, exceeding the "
        f"invariant ceiling of {MAX_FEATURE_FILTER_SLUGS} (08-SRCH-001). Either "
        f"the catalogue grew or the invariant must be re-measured and raised "
        f"deliberately."
    )
    assert worst == FEATURE_CATALOGUE_MAX_AT_SEED, (
        f"measured catalogue maximum is {worst} (at '{worst_slug}'), but the "
        f"constant pins it at {FEATURE_CATALOGUE_MAX_AT_SEED}. Re-measure and "
        f"update FEATURE_CATALOGUE_MAX_AT_SEED (08-SRCH-001)."
    )
