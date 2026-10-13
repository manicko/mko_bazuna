"""
Shared test fixtures for the categories test suite.

Fixtures defined here are available to all test modules under
``apps/categories/tests/`` without duplicating definitions (B19 audit finding
#9 — DRY across sibling test modules).
"""

from __future__ import annotations

import pytest

from apps.categories.models import Category


@pytest.fixture
def tree() -> Category:
    """Create a root category with active and inactive children.

    All children carry ``name_i18n`` with ``ru`` translations so that
    localization tests (``?lang=ru``) exercise real ``name_i18n`` data
    rather than falling back to the base ``name`` field (B19 audit #8).
    """
    root = Category.objects.create(
        name="Транспорт",
        slug="transport",
        name_i18n={"ru": "Транспорт"},
    )
    Category.objects.create(
        name="Велосипеды",
        slug="bicycles",
        parent=root,
        name_i18n={"ru": "Велосипеды"},
    )
    Category.objects.create(
        name="Автомобили",
        slug="cars",
        parent=root,
        name_i18n={"ru": "Автомобили"},
    )
    Category.objects.create(
        name="Устаревшее",
        slug="old",
        parent=root,
        is_active=False,
        name_i18n={"ru": "Устаревшее"},
    )
    return root
