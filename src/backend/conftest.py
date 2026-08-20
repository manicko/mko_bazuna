"""
Root test configuration for the Mko Bazuna backend test suite.

Provides shared pytest fixtures that are common across multiple test modules
(user, category, city, seller). Each fixture can be overridden by a more
specific fixture defined in a local ``conftest.py`` or the test module itself
— pytest resolves fixtures from the closest scope first.

Also exposes ``create_test_ad`` as a module-level helper for test modules
that need to construct ``Ad`` rows with status-specific timestamps set,
satisfying the strict database check constraints (e.g.
``ck_ads_published_at_if_published``, ``ck_ads_rejected_at_if_rejected``).
"""

from __future__ import annotations

from typing import Any

import pytest
from django.utils import timezone

from apps.ads.models import Ad
from apps.categories.models import Category
from apps.core.enums import AdSource, AdStatus
from apps.locations.models import City
from apps.users.models import User


# ---------------------------------------------------------------------------
# Generic model fixtures (safe to override per-module)
# ---------------------------------------------------------------------------


@pytest.fixture
def seller() -> User:
    """Create a generic seller user."""
    return User.objects.create(
        telegram_id=900000001,
        chat_id=900000001,
        password="x",
    )


@pytest.fixture
def user() -> User:
    """Create a generic user (alias of seller for modules that use 'user')."""
    return User.objects.create(
        telegram_id=900000002,
        chat_id=900000002,
        password="x",
    )


@pytest.fixture
def category() -> Category:
    """Create a generic root category."""
    return Category.objects.create(name="Транспорт", slug="transport")


@pytest.fixture
def city() -> City:
    """Create a generic city."""
    return City.objects.create(
        country_code="ME",
        name="Тестград",
        region="Central",
        slug="test-grad",
    )


# ---------------------------------------------------------------------------
# Ad creation helper — prevents check-constraint violations
# ---------------------------------------------------------------------------


def create_test_ad(
    user: User,
    category: Category,
    city: City,
    *,
    title: str = "Test Ad",
    description: str = "Test description",
    status: AdStatus = AdStatus.ON_MODERATION,
    price: int | None = 100,
    source: AdSource = AdSource.TELEGRAM,
    **kwargs: Any,
) -> Ad:
    """Create an ``Ad`` with status-specific timestamps.

    Automatically sets ``published_at``, ``rejected_at``, ``archived_at``,
    ``moderation_failed_at``, or ``deleted_at`` based on the ``status``
    value, satisfying the strict database ``CheckConstraint`` rules on the
    ``Ad`` model. Callers can override any field via ``**kwargs``.
    """
    defaults: dict[str, Any] = {
        "user": user,
        "title": title,
        "description": description,
        "price": price,
        "category": category,
        "city": city,
        "category_name": category.name,
        "status": status,
        "source": source,
    }
    defaults.update(kwargs)
    _set_status_timestamp(defaults, status)
    return Ad.objects.create(**defaults)


def _set_status_timestamp(defaults: dict[str, Any], status: AdStatus) -> None:
    """Inject the timestamp required by the check constraint for *status*.

    Existing keys in *defaults* take precedence (callers may pass an explicit
    timestamp). ``auto_now_add`` on ``created_at`` means ``created_at``
    passed through ``**kwargs`` is silently ignored by Django — backdate
    via ``QuerySet.update()`` after creation if needed.
    """
    now = timezone.now()
    if status == AdStatus.PUBLISHED and "published_at" not in defaults:
        defaults["published_at"] = now
    elif status == AdStatus.ARCHIVED and "archived_at" not in defaults:
        defaults["archived_at"] = now
    elif status == AdStatus.REJECTED and "rejected_at" not in defaults:
        defaults["rejected_at"] = now
    elif (
        status == AdStatus.ON_MODERATION_FAILED
        and "moderation_failed_at" not in defaults
    ):
        defaults["moderation_failed_at"] = now
    elif status == AdStatus.DELETED and "deleted_at" not in defaults:
        defaults["deleted_at"] = now
