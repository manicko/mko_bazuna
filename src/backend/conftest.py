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

from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

from apps.ads.models import Ad
from apps.categories.models import Category
from apps.core.enums import AdSource, AdStatus, AdvisoryLockId
from apps.currencies.enums import CurrencyCode
from apps.locations.models import City
from apps.users.models import User


# ---------------------------------------------------------------------------
# Schema restoration — pytest-django creates the test DB from model
# introspection (MIGRATION_MODULES=None), so migration RunSQL/seed data that
# creates triggers and currency rows is skipped. This autouse fixture runs
# after django_db_setup and restores that schema/data so the test DB mirrors
# production.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _restore_test_schema_post_db_setup(django_db_setup, django_db_blocker):
    """Restore trigger DDL + seed data that MIGRATION_MODULES=None skips.

    Runs after pytest-django creates the test DB (via django_db_setup).
    Temporarily unblocks the pytest-django DB access blocker so the commands
    can run during session setup (even for unit-only tests that lack the
    ``django_db`` marker).
    Idempotent: safe to run even when migrations are active (after squash
    without MIGRATION_MODULES). migrate --run-syncdb is also idempotent and
    ensures tables for unmigrated apps (e.g. currencies) exist even on --reuse-db.

    Under pytest-xdist (-n auto), each worker runs this session-scoped fixture
    independently against the same test_mko_bazuna DB. A session-scoped
    PostgreSQL advisory lock (``AdvisoryLockId.TEST_SCHEMA_SETUP``) serializes
    the DDL so concurrent CREATE OR REPLACE FUNCTION and DROP/CREATE TRIGGER
    do not clash on system catalogs ("tuple concurrently updated"). The
    management commands are idempotent, so sequential re-runs by each worker
    under the lock are safe and fast.
    """
    from apps.core.utils.advisory_lock import advisory_lock
    from django.core.management import call_command

    with django_db_blocker.unblock():
        # Serialize DDL across xdist workers: all 16 workers run this session-
        # scoped autouse fixture concurrently against the shared test_mko_bazuna
        # DB. Without the lock, concurrent CREATE OR REPLACE FUNCTION and
        # DROP/CREATE TRIGGER cause "tuple concurrently updated" on PostgreSQL
        # system catalogs. pg_advisory_lock provides server-level mutual
        # exclusion; the management commands are idempotent, so sequential
        # re-runs by each worker are safe.
        with advisory_lock(AdvisoryLockId.TEST_SCHEMA_SETUP, session=True):
            # Ensure tables for unmigrated apps exist. With MIGRATION_MODULES=
            # DisableMigrations (test settings), app tables are only created via
            # syncdb during django_db_setup. However, if the test DB was reused
            # (--reuse-db) with a stale state, the currencies table may be absent.
            # migrate --run-syncdb is idempotent and recreates any missing tables.
            call_command("migrate", "--run-syncdb")
            call_command("load_exchange_rates")
            call_command("setup_search_triggers")


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
    price: int | Decimal = 100,
    price_currency: CurrencyCode | str = CurrencyCode.EUR,
    source: AdSource = AdSource.TELEGRAM,
    **kwargs: Any,
) -> Ad:
    """Create an ``Ad`` with status-specific timestamps.

    Automatically sets ``published_at``, ``rejected_at``, ``archived_at``,
    ``moderation_failed_at``, or ``deleted_at`` based on the ``status``
    value, satisfying the strict database ``CheckConstraint`` rules on the
    ``Ad`` model. Callers can override any field via ``**kwargs``.

    The ``price`` argument is the seller's original amount (in
    ``price_currency``, default EUR); the EUR-normalized value is set equal to
    it (EUR base rate 1.0). Pass ``price=0`` for a Free/Charity ad.
    """
    defaults: dict[str, Any] = {
        "user": user,
        "title": title,
        "description": description,
        "price_amount": price,
        "price_currency": CurrencyCode(price_currency).value,
        "price_normalized_eur": price,
        "category": category,
        "city": city,
        "category_name": category.name,
        "status": status,
        "source": source,
    }
    defaults.update(kwargs)
    _set_status_timestamp(defaults, status)
    return Ad.objects.create(**defaults)


def create_test_ads_bulk(
    user: User,
    category: Category,
    city: City,
    count: int,
    *,
    title_prefix: str = "Test Ad",
    description: str = "Test description",
    status: AdStatus = AdStatus.ON_MODERATION,
    price: int | Decimal = 100,
    price_currency: CurrencyCode | str = CurrencyCode.EUR,
    source: AdSource = AdSource.TELEGRAM,
    **kwargs: Any,
) -> list[Ad]:
    """Bulk-create ``count`` ``Ad`` rows with status-specific timestamps.

    Companion to ``create_test_ad`` for tests that need many rows. Uses
    ``Ad.objects.bulk_create`` to collapse the rows into one multi-row INSERT;
    the FTS trigger is row-level, so behavior is identical to individual
    inserts. Rows are titled ``f"{title_prefix} {i}"`` (numbering can be
    disabled by passing an explicit ``title`` via ``kwargs``).
    """
    ads: list[Ad] = []
    for i in range(count):
        defaults: dict[str, Any] = {
            "user": user,
            "title": f"{title_prefix} {i}",
            "description": description,
            "price_amount": price,
            "price_currency": CurrencyCode(price_currency).value,
            "price_normalized_eur": price,
            "category": category,
            "city": city,
            "category_name": category.name,
            "status": status,
            "source": source,
        }
        defaults.update(kwargs)
        _set_status_timestamp(defaults, status)
        ads.append(Ad(**defaults))
    return Ad.objects.bulk_create(ads)


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
