"""
Management command to recompute ``price_normalized_eur`` for all ads.

Administrators / cron trigger this command after exchange-rate changes so the
derived EUR-normalized price reflects the *current* ``ExchangeRate`` for each
ad's ``price_currency`` (CR-09, Assumption 7). It is idempotent and
concurrency-safe via the ``RECOMPUTE_NORMALIZED_PRICES`` advisory lock, held
session-scoped for the whole sweep, and commits one batch at a time so row
locks are released as the sweep progresses (finding 03-DB-008). Only rows whose
normalized value actually differs are updated (avoids noise in ``updated_at``
and the DB write log).
"""

import logging
import time

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from apps.ads.models import Ad
from apps.core.enums import AdStatus, AdvisoryLockId
from apps.core.utils.advisory_lock import advisory_lock
from apps.currencies.enums import CurrencyCode
from apps.currencies.services.exceptions import ExchangeRateNotFoundError
from apps.currencies.services.price_normalizer import PriceNormalizer

logger = logging.getLogger(__name__)

_BATCH_SIZE = 500

# Non-draft ads that have a price (amount + currency set).
_RECOMPUTE_PREDICATE = (
    ~Q(status=AdStatus.DRAFT)
    & Q(price_amount__isnull=False)
    & Q(price_currency__isnull=False)
)


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
        """Run the recompute, one committed batch at a time.

        Why there is no enclosing ``transaction.atomic()`` here. The advisory
        lock is **session-scoped** (``pg_advisory_lock``) because the batches
        below each commit; a transaction-scoped lock would be released by the
        first batch ``COMMIT``. An enclosing ``atomic()`` would turn each
        per-batch ``atomic()`` into a savepoint, so nothing would ever commit
        and every row lock would be held for the whole sweep again — the exact
        defect 03-DB-008 fixes. Guarded by
        ``test_batches_commit_independently`` (behavioural) and
        ``test_sweep_lock_structure`` (lock scope).
        """
        dry_run: bool = options["dry_run"]

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
        """Recompute normalized prices in committed batches.

        Considers all non-draft ads that have a price (amount + currency set).
        Each batch is fetched and locked by the caller in the enclosing
        per-batch transaction; rows whose normalized value is already equal are
        left untouched. ``--dry-run`` still walks every batch (to report the
        total checked count) but writes nothing.
        """
        normalizer = PriceNormalizer()
        total_checked = 0
        total_changed = 0
        last_pk = 0
        batch_no = 0

        with advisory_lock(AdvisoryLockId.RECOMPUTE_NORMALIZED_PRICES, session=True):
            try:
                while True:
                    started = time.monotonic()
                    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
                        ads = list(
                            Ad.objects.select_for_update()
                            .filter(_RECOMPUTE_PREDICATE)
                            .filter(pk__gt=last_pk)
                            .order_by("pk")[:_BATCH_SIZE]
                            .only(
                                "pk",
                                "price_amount",
                                "price_currency",
                                "price_normalized_eur",
                            )
                        )
                        if not ads:
                            break
                        checked, changed = self._apply_batch(
                            normalizer, ads, dry_run
                        )
                        last_pk = ads[-1].pk
                    batch_no += 1
                    total_checked += checked
                    total_changed += changed
                    logger.info(
                        "recompute batch %d: checked=%d changed=%d "
                        "last_committed_pk=%d hold_ms=%d",
                        batch_no,
                        checked,
                        changed,
                        last_pk,
                        round((time.monotonic() - started) * 1000),
                    )
            except Exception:
                logger.exception(
                    "recompute_normalized_prices aborted at batch %d "
                    "(last committed pk=%d); %d batch(es) are already "
                    "committed — re-run the command, it is idempotent and "
                    "reprocesses from pk=0",
                    batch_no + 1,
                    last_pk,
                    batch_no,
                )
                raise

        return total_checked, total_changed

    def _apply_batch(
        self, normalizer: PriceNormalizer, ads: list[Ad], dry_run: bool
    ) -> tuple[int, int]:
        """Recompute and persist one batch.

        ``ads`` MUST already be locked with ``select_for_update()`` by the
        caller in the enclosing per-batch transaction — this method issues no
        lock of its own and performs no read. Both expected per-row failures
        (``CurrencyCode`` ``ValueError``, ``ExchangeRateNotFoundError``) stay
        isolated per row.
        """
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
