"""
Management command to recompute ``price_normalized_eur`` for all ads.

Administrators / cron trigger this command after exchange-rate changes so the
derived EUR-normalized price reflects the *current* ``ExchangeRate`` for each
ad's ``price_currency`` (CR-09, Assumption 7). It is idempotent and
concurrency-safe via the ``RECOMPUTE_NORMALIZED_PRICES`` advisory lock, and
only updates rows whose normalized value actually differs (avoids noise in
``updated_at`` and the DB write log).
"""

import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.ads.models import Ad
from apps.core.enums import AdStatus, AdvisoryLockId
from apps.core.utils.advisory_lock import advisory_lock
from apps.currencies.enums import CurrencyCode
from apps.currencies.services.exceptions import ExchangeRateNotFoundError
from apps.currencies.services.price_normalizer import PriceNormalizer

logger = logging.getLogger(__name__)

_BATCH_SIZE = 500


class Command(BaseCommand):
    """Recompute the EUR-normalized price for all non-draft ads."""

    help = (
        "Recompute price_normalized_eur for all non-draft ads using the "
        "current exchange rate for each ad's price_currency"
    )

    def add_arguments(self, parser) -> None:
        """Add the --dry-run flag."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            default=False,
            help="Print the number of ads to update without writing anything",
        )

    def handle(self, *args, **options) -> None:
        """Run the recompute with an advisory lock."""
        dry_run: bool = options["dry_run"]

        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
            with advisory_lock(AdvisoryLockId.RECOMPUTE_NORMALIZED_PRICES):
                total_checked, total_changed = self._recompute(dry_run)

        if dry_run:
            logger.info(
                "DRY RUN: Would recompute %d of %d checked ads",
                total_changed,
                total_checked,
            )
        else:
            logger.info(
                "Recomputed %d of %d checked ads",
                total_changed,
                total_checked,
            )

    def _recompute(self, dry_run: bool) -> tuple[int, int]:
        """Recompute normalized prices in batches, returning checked/changed counts.

        Considers all non-draft ads that have a price (amount + currency set).
        Uses ``bulk_update`` per batch; rows whose normalized value is already
        equal are left untouched.
        """
        normalizer = PriceNormalizer()
        queryset = Ad.objects.exclude(status=AdStatus.DRAFT).filter(
            price_amount__isnull=False,
            price_currency__isnull=False,
        )

        total_checked = 0
        total_changed = 0
        batch_ids: list[int] = []

        for pk in queryset.values_list("pk", flat=True).iterator(
            chunk_size=_BATCH_SIZE
        ):
            batch_ids.append(pk)
            if len(batch_ids) >= _BATCH_SIZE:
                checked, changed = self._process_batch(normalizer, batch_ids, dry_run)
                total_checked += checked
                total_changed += changed
                batch_ids = []

        if batch_ids:
            checked, changed = self._process_batch(normalizer, batch_ids, dry_run)
            total_checked += checked
            total_changed += changed

        return total_checked, total_changed

    def _process_batch(
        self,
        normalizer: PriceNormalizer,
        batch_ids: list[int],
        dry_run: bool,
    ) -> tuple[int, int]:
        """Recompute one batch of ads.

        Returns:
            A ``(checked, changed)`` tuple for this batch.
        """
        ads = list(
            Ad.objects.filter(pk__in=batch_ids).only(
                "pk", "price_amount", "price_currency", "price_normalized_eur"
            )
        )

        to_update: list[Ad] = []
        for ad in ads:
            try:
                currency = CurrencyCode(ad.price_currency)
            except ValueError:
                logger.warning(
                    "Skipping ad %s: unknown currency %r", ad.pk, ad.price_currency
                )
                continue

            try:
                normalized = normalizer.normalize_to_eur(ad.price_amount, currency)
            except ExchangeRateNotFoundError:
                logger.warning(
                    "Skipping ad %s: no current rate for %s", ad.pk, currency.value
                )
                continue

            if ad.price_normalized_eur != normalized:
                ad.price_normalized_eur = normalized
                to_update.append(ad)

        if to_update and not dry_run:
            Ad.objects.bulk_update(
                to_update, ["price_normalized_eur"], batch_size=_BATCH_SIZE
            )

        return len(ads), len(to_update)
