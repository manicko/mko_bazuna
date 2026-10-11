"""Management command to seed load-test (performance-test) published ads.

Creates N PUBLISHED ``Ad`` rows for the CI load-test (locust) and query-profile
jobs. Centralizes the constraint-correct field set that was previously
duplicated as inline ``python -c`` scripts in the CI workflows — scripts that
broke twice: once for a missing ``chat_id`` on the seed user, and again for
``Ad`` field renames (``seller`` -> ``user``, ``price`` -> ``price_amount``).

The command deliberately does NOT load reference data (cities / catalog); it
requires a category and a city to pre-exist and fails fast with a clear
``CommandError`` when they are absent. This mirrors the ``ci-seed.yml``
``query-profile`` pattern, where ``load_cities`` and ``load_catalog`` run as
explicit CI steps before seeding, and avoids advisory-lock / data-collision
issues from importing the catalog inside a management command.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.ads.models import Ad
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.currencies.enums import CurrencyCode
from apps.locations.models import City
from apps.users.models import User

logger = logging.getLogger(__name__)

# Identity of the command-created "seller" user. Per spec assumption 5, a
# Telegram account's chat_id equals its telegram_id; keying on telegram_id
# (unique) makes re-runs --reuse-db safe (no duplicate user, no IntegrityError),
# matching the conftest ``seller``/``user`` fixtures' get_or_create pattern.
DEFAULT_LOAD_TEST_TELEGRAM_ID = 999999

# Price assigned to every seeded ad. Seed ads are EUR by assumption 8, so the
# EUR-normalized value equals the amount — ``price_normalized_eur`` is set
# explicitly because no DB trigger computes it (the PriceNormalizer service /
# ``recompute_normalized_prices`` command own it). The load-test price-filter
# tasks filter on ``price_normalized_eur`` and must exercise the
# ``IX_ads_pub_price_sort`` index, so it must be populated.
DEFAULT_LOAD_TEST_PRICE = Decimal("100")


class Command(BaseCommand):
    """Seed N PUBLISHED ads for the CI load-test and query-profile jobs."""

    help = (
        "Seed N PUBLISHED ads (with valid constraint-satisfying timestamps and "
        "EUR-normalized prices) for the CI load-test (locust) and query-profile "
        "jobs. Requires cities and categories to be loaded first "
        "(run 'load_cities' and 'load_catalog' before this command)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--count",
            type=int,
            default=120,
            help="Number of PUBLISHED ads to seed (default: 120).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="batch_size for bulk_create (default: 1000).",
        )

    def handle(self, *args, **options) -> None:
        count: int = options["count"]
        batch_size: int = options["batch_size"]

        if count <= 0:
            raise CommandError(f"--count must be positive, got {count}")
        if batch_size <= 0:
            raise CommandError(f"--batch-size must be positive, got {batch_size}")

        category = self._require_category()
        city = self._require_city()
        seller = self._get_or_create_seller()

        ads = self._build_ads(count, seller, category, city)
        created = self._create_ads(ads, batch_size)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created} PUBLISHED load-test ads (batch_size={batch_size})"
            )
        )

    def _require_category(self) -> Category:
        """Return the first active category, or fail with an actionable error."""
        category = Category.objects.filter(is_active=True).first()
        if category is None:
            raise CommandError(
                "No active categories found. Run 'python manage.py load_catalog' "
                "before seeding load-test ads."
            )
        return category

    def _require_city(self) -> City:
        """Return the first city, or fail with an actionable error."""
        city = City.objects.first()
        if city is None:
            raise CommandError(
                "No cities found. Run 'python manage.py load_cities' "
                "before seeding load-test ads."
            )
        return city

    def _get_or_create_seller(self) -> User:
        """Ensure the load-test seller user exists (idempotent, reuse-db safe)."""
        user, created = User.objects.get_or_create(
            telegram_id=DEFAULT_LOAD_TEST_TELEGRAM_ID,
            defaults={
                "chat_id": DEFAULT_LOAD_TEST_TELEGRAM_ID,
                "username": f"load-test-{DEFAULT_LOAD_TEST_TELEGRAM_ID}",
                "password": "x",
            },
        )
        if created:
            logger.info(
                "Created load-test seller user (telegram_id=%d)",
                DEFAULT_LOAD_TEST_TELEGRAM_ID,
            )
        return user

    def _build_ads(
        self,
        count: int,
        seller: User,
        category: Category,
        city: City,
    ) -> list[Ad]:
        """Build ``count`` unsaved PUBLISHED Ad instances.

        All field names mirror the current ``Ad`` model (NOT the legacy
        ``seller``/``price`` aliases): ``user``, ``price_amount``, plus
        ``price_normalized_eur`` and ``published_at`` which the check constraints
        and the price-sort index require.
        """
        now = timezone.now()
        price = DEFAULT_LOAD_TEST_PRICE
        # category_name is the denormalized Russian base name; cheap to set and
        # keeps the seed rows realistic (FTS trigger can index category context).
        category_name = category.name
        return [
            Ad(
                user=seller,
                title=f"Load test ad {i}",
                category=category,
                city=city,
                category_name=category_name,
                price_amount=price,
                price_currency=CurrencyCode.EUR.value,
                price_normalized_eur=price,
                status=AdStatus.PUBLISHED,
                # Required by ck_ads_published_at_if_published (status=PUBLISHED
                # => published_at NOT NULL). Set explicitly rather than relying on
                # transition_to(), which is for the bot's moderation flow.
                published_at=now,
            )
            for i in range(count)
        ]

    def _create_ads(self, ads: list[Ad], batch_size: int) -> int:
        """Persist ads in one bulk insert inside a transaction.

        Returns the number of rows written. ``bulk_create`` is safe here: the
        FTS search-vector trigger is a row-level BEFORE INSERT trigger (fires per
        row on multi-row INSERTs) and the ``search_vector`` columns are nullable.
        """
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
            created = Ad.objects.bulk_create(ads, batch_size=batch_size)
        return len(created)
