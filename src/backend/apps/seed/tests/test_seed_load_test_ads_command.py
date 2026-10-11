"""Tests for the ``seed_load_test_ads`` management command.

These tests live outside the ``seed`` marker suite (they are fast and
deterministic) but are tagged ``integration`` because they exercise the ORM
against the real test DB schema (check constraints, FTS trigger, price-sort
index) restored by ``_restore_test_schema_post_db_setup``.

The ``category`` and ``city`` fixtures are requested explicitly: the
session-autouse conftest fixture only restores reference data (triggers,
exchange rates), NOT categories or cities.
"""

from __future__ import annotations

import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ads.models import Ad, AdStatus
from apps.currencies.enums import CurrencyCode
from apps.seed.management.commands.seed_load_test_ads import (
    DEFAULT_LOAD_TEST_PRICE,
    DEFAULT_LOAD_TEST_TELEGRAM_ID,
)
from apps.users.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestSeedLoadTestAds:
    """Validate the command's DB writes and guardrails."""

    def test_creates_correct_number_of_published_ads(self, category, city) -> None:
        count = 5
        out = io.StringIO()

        call_command("seed_load_test_ads", "--count", str(count), stdout=out)

        ads = Ad.objects.all()
        assert ads.count() == count
        assert all(ad.status == AdStatus.PUBLISHED for ad in ads)
        # All rows must satisfy ck_ads_published_at_if_published.
        assert all(ad.published_at is not None for ad in ads)
        assert "Seeded 5 PUBLISHED" in out.getvalue()

    def test_sets_required_constraint_fields(self, category, city) -> None:
        call_command("seed_load_test_ads", "--count", "1")

        ad = Ad.objects.get()
        # Current Ad field names (NOT legacy seller=/price= aliases).
        assert ad.user_id is not None
        assert ad.price_amount == DEFAULT_LOAD_TEST_PRICE
        assert ad.price_normalized_eur == DEFAULT_LOAD_TEST_PRICE
        assert ad.price_currency == CurrencyCode.EUR.value
        # Denormalized Russian category name from the FK category.
        assert ad.category_name == category.name
        assert ad.category_id == category.id
        assert ad.city_id == city.id

    def test_is_idempotent_user_and_adds_ads(self, category, city) -> None:
        """Re-running must not duplicate the seller user (get_or_create),
        but each run inserts fresh ad rows."""
        call_command("seed_load_test_ads", "--count", "3")
        assert User.objects.filter(telegram_id=DEFAULT_LOAD_TEST_TELEGRAM_ID).count() == 1
        assert Ad.objects.count() == 3

        call_command("seed_load_test_ads", "--count", "3")
        # Same single seller user (reuse-db safe), fresh ads.
        assert User.objects.filter(telegram_id=DEFAULT_LOAD_TEST_TELEGRAM_ID).count() == 1
        assert Ad.objects.count() == 6

    def test_raises_when_no_active_categories(self, category, city) -> None:
        # Wipe categories; command checks them before cities.
        category.__class__.objects.all().delete()

        with pytest.raises(CommandError, match="load_catalog"):
            call_command("seed_load_test_ads", "--count", "1")

    def test_raises_when_no_cities(self, category, city) -> None:
        city.__class__.objects.all().delete()

        with pytest.raises(CommandError, match="load_cities"):
            call_command("seed_load_test_ads", "--count", "1")

    def test_rejects_non_positive_count(self, category, city) -> None:
        with pytest.raises(CommandError, match="positive"):
            call_command("seed_load_test_ads", "--count", "0")

    def test_rejects_non_positive_batch_size(self, category, city) -> None:
        with pytest.raises(CommandError, match="positive"):
            call_command("seed_load_test_ads", "--count", "1", "--batch-size", "0")
