"""
Tests for the ``recompute_normalized_prices`` management command (spec Task 11).

Also covers DB-001: the batch read in ``_process_batch`` uses
``select_for_update()`` so a concurrent web/bot price edit cannot overwrite the
correctly-computed ``price_normalized_eur`` with a stale value (lost update).
"""

from __future__ import annotations

import logging
import threading
import time
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.db import connection, transaction
from django.db.models.query import QuerySet

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from apps.currencies.enums import CurrencyCode
from apps.currencies.models import ExchangeRate
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# Cache isolation between tests is provided by the root conftest's autouse
# ``_clear_cache_between_tests`` fixture (src/backend/conftest.py, lines 90-103),
# which clears the LocMem cache before and after every backend test.


class TestRecomputeNormalizedPrices:
    def test_recompute_corrects_stale_normalized_value(
        self, exchange_rates, seller, category, city
    ) -> None:
        """A stale EUR-normalized value is recomputed from the current rate.

        The ad is BAM with amount 100 (100 * 0.512 = 51.20 EUR); the stored
        normalized value (999) is stale and must be corrected.
        """
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            price=100,
            price_currency=CurrencyCode.BAM,
            price_normalized_eur=999,
        )

        call_command("recompute_normalized_prices")

        ad.refresh_from_db()
        assert ad.price_normalized_eur == Decimal("51.2000")

    def test_dry_run_does_not_write(
        self, exchange_rates, seller, category, city, caplog
    ) -> None:
        """``--dry-run`` reports without persisting any change."""
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            price=100,
            price_currency=CurrencyCode.BAM,
            price_normalized_eur=999,
        )

        with caplog.at_level(logging.INFO):
            call_command("recompute_normalized_prices", dry_run=True)

        ad.refresh_from_db()
        assert ad.price_normalized_eur == Decimal("999")
        # The dry-run summary reports the count of stale-value ads to update.
        assert "DRY RUN: Would recompute 1 of 1 checked ads" in caplog.text

    def test_draft_ads_are_skipped(
        self, exchange_rates, seller, category, city
    ) -> None:
        """Draft ads (pre-submission) are excluded from recompute."""
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.DRAFT,
            price=100,
            price_currency=CurrencyCode.BAM,
            price_normalized_eur=999,
        )

        call_command("recompute_normalized_prices")

        ad.refresh_from_db()
        assert ad.price_normalized_eur == Decimal("999")

    def test_recompute_locks_batch_with_select_for_update(self) -> None:
        """``recompute_normalized_prices`` genuinely calls
        ``select_for_update()`` at runtime.

        Replaces an ``inspect.getsource(Command._process_batch)`` token
        assertion (finding 03-DB-008). Under the per-batch design the batch is
        fetched and locked by the caller (``_recompute``) in the per-batch
        transaction, so the lock legitimately leaves ``_apply_batch``. This
        asserts a real ``QuerySet.select_for_update`` call rather than a
        substring — the runtime-spy pattern from
        ``test_db_lock_timeout_boundary.py::TestBulkLockTimeout``.
        """
        calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
        original = QuerySet.select_for_update

        def _spy(queryset: QuerySet, *args: object, **kwargs: object) -> QuerySet:
            calls.append((args, kwargs))
            return original(queryset, *args, **kwargs)

        with patch.object(QuerySet, "select_for_update", _spy):
            call_command("recompute_normalized_prices")

        assert calls, "recompute_normalized_prices never called select_for_update()"

    @pytest.mark.django_db(transaction=True)
    def test_batches_commit_independently(
        self, exchange_rates, seller, category, city, monkeypatch
    ) -> None:
        """Each batch commits independently; a later failure keeps earlier work.

        Mirror of ``test_sweep_archive.py::test_batches_commit_independently``
        for finding 03-DB-008. ``transaction=True`` makes each per-batch
        ``atomic()`` a real transaction; a small batch size spans at least three
        batches, and ``bulk_update`` fails on the second. Pre-fix the whole
        recompute is one transaction and rolls back — no row is updated, which is
        exactly why this test is RED against the pre-fix code.
        """
        from apps.currencies.management.commands import (
            recompute_normalized_prices,
        )

        monkeypatch.setattr(recompute_normalized_prices, "_BATCH_SIZE", 2)

        ads = [
            create_test_ad(
                seller,
                category,
                city,
                status=AdStatus.PUBLISHED,
                price=100,
                price_currency=CurrencyCode.BAM,
                price_normalized_eur=999,
            )
            for _ in range(6)
        ]
        ads.sort(key=lambda ad: ad.pk)
        batch_one_pks = {ad.pk for ad in ads[:2]}

        original_bulk_update = Ad.objects.bulk_update
        call_count = 0

        def _bulk_update(objs, fields, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("injected failure in batch 2")
            return original_bulk_update(objs, fields, *args, **kwargs)

        monkeypatch.setattr(Ad.objects, "bulk_update", _bulk_update)

        with pytest.raises(RuntimeError, match="injected failure in batch 2"):
            call_command("recompute_normalized_prices")

        updated_pks = set(
            Ad.objects.filter(pk__in=batch_one_pks, price_normalized_eur=Decimal("51.2000"))
            .values_list("pk", flat=True)
        )
        assert updated_pks == batch_one_pks, (
            "batch 1 must be committed when a later batch fails — the per-batch "
            "commit is not taking effect (03-DB-008)"
        )

    def test_unknown_currency_is_skipped_and_logged(
        self, exchange_rates, seller, category, city, caplog
    ) -> None:
        """An ad with an unknown ``price_currency`` is skipped per-row.

        ``CurrencyCode(ad.price_currency)`` raises ``ValueError`` for a currency
        code no longer in the StrEnum (e.g. a deprecated value persisted in the
        DB). ``_apply_batch`` catches it, logs a warning, and ``continue``s —
        other ads in the same batch are still recomputed.
        """
        good_ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            price=100,
            price_currency=CurrencyCode.BAM,
            price_normalized_eur=999,
        )
        bad_ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            price=100,
            price_currency=CurrencyCode.BAM,
            price_normalized_eur=999,
        )
        # Simulate a deprecated currency code no longer in the CurrencyCode enum
        Ad.objects.filter(pk=bad_ad.pk).update(price_currency="XXX")

        with caplog.at_level(logging.WARNING):
            call_command("recompute_normalized_prices")

        good_ad.refresh_from_db()
        assert good_ad.price_normalized_eur == Decimal("51.2000")
        bad_ad.refresh_from_db()
        assert bad_ad.price_normalized_eur == Decimal("999")
        assert any(
            "Skipping ad" in record.message and "XXX" in record.message
            for record in caplog.records
        )

    def test_missing_exchange_rate_is_skipped_and_logged(
        self, exchange_rates, seller, category, city, caplog
    ) -> None:
        """An ad whose currency has no current rate is skipped per-row.

        ``PriceNormalizer.normalize_to_eur`` raises ``ExchangeRateNotFoundError``
        when no ``is_current=True`` rate row exists; ``_apply_batch`` catches it,
        logs a warning, and ``continue``s — other ads in the same batch are
        still recomputed.
        """
        good_ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            price=100,
            price_currency=CurrencyCode.EUR,
            price_normalized_eur=999,
        )
        stale_ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            price=100,
            price_currency=CurrencyCode.BAM,
            price_normalized_eur=999,
        )
        # Remove the current BAM rate so normalize_to_eur raises
        ExchangeRate.objects.filter(
            currency=CurrencyCode.BAM.value
        ).update(is_current=False)

        with caplog.at_level(logging.WARNING):
            call_command("recompute_normalized_prices")

        good_ad.refresh_from_db()
        assert good_ad.price_normalized_eur == Decimal("100.0000")
        stale_ad.refresh_from_db()
        assert stale_ad.price_normalized_eur == Decimal("999")
        assert any(
            "Skipping ad" in record.message and "BAM" in record.message
            for record in caplog.records
        )

    def test_null_price_currency_is_excluded(
        self, exchange_rates, seller, category, city, caplog
    ) -> None:
        """A null ``price_currency`` is excluded by ``_RECOMPUTE_PREDICATE``.

        The predicate filters ``Q(price_currency__isnull=False)``, so an ad with
        a null currency is never loaded into a batch or seen by ``_apply_batch``.
        A sibling ad with a valid currency is still recomputed normally.
        """
        good_ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            price=100,
            price_currency=CurrencyCode.EUR,
            price_normalized_eur=999,
        )
        null_ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            price=100,
            price_currency=CurrencyCode.EUR,
            price_normalized_eur=999,
        )
        # Clear price_currency (allowed by the model: null=True, blank=True)
        Ad.objects.filter(pk=null_ad.pk).update(price_currency=None)

        with caplog.at_level(logging.WARNING):
            call_command("recompute_normalized_prices")

        good_ad.refresh_from_db()
        assert good_ad.price_normalized_eur == Decimal("100.0000")
        null_ad.refresh_from_db()
        assert null_ad.price_currency is None
        assert null_ad.price_normalized_eur == Decimal("999")
        # The null-currency ad is excluded by the predicate — it never reaches
        # _apply_batch, so no "Skipping ad" warning references it.
        assert not any(
            str(null_ad.pk) in record.message for record in caplog.records
        )


class TestRecomputeRowLockConcurrency:
    """DB-001: ``select_for_update()`` in ``_process_batch`` prevents lost
    update on ``price_normalized_eur`` from a concurrent price edit.

    Mirrors the concurrency pattern from ``test_sweep_archive.py`` (DB-010) and
    ``test_transition_concurrency.py`` (DB-003): the main thread holds the
    ``FOR UPDATE`` row lock (simulating recompute's batch read through
    ``bulk_update``), and the background thread performs a conflicting
    ``select_for_update`` price edit that must block until the recompute
    transaction commits.
    """

    pytestmark = [
        pytest.mark.django_db(transaction=True),
        pytest.mark.concurrent,
    ]

    @pytest.mark.slow
    @pytest.mark.django_db(transaction=True)
    @pytest.mark.concurrent
    @pytest.mark.xdist_group("concurrent")
    @pytest.mark.flaky(reruns=1, reruns_delay=1)
    def test_recompute_row_lock_blocks_concurrent_price_edit(
        self, exchange_rates, seller, category, city
    ) -> None:
        """A concurrent price edit blocks on recompute's row lock and its
        correctly-computed normalized value is not lost.

        Setup: ad is BAM 100 with a stale normalized value (999). Recompute
        holds the ``FOR UPDATE`` lock, computes 51.20 for price 100, and writes
        it. A concurrent edit raises ``price_amount`` to 200 (BAM) and sets
        ``price_normalized_eur`` to 102.40 — it must block until recompute
        commits, then proceed. If the row lock were missing, the edit could
        interleave before recompute's write and be clobbered by the blind
        ``bulk_update``, leaving a stale ``price_normalized_eur`` of 51.20.
        """
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            price=100,
            price_currency=CurrencyCode.BAM,
            price_normalized_eur=999,
        )
        ad_id = ad.id

        started = threading.Event()
        finished = threading.Event()
        errors: list[BaseException] = []

        def concurrent_price_edit() -> None:
            """Background thread: a web/bot price edit on the same ad.

            Acquires the same ``FOR UPDATE`` row lock (mirroring
            ``edit._apply_price_change``), then changes the price and its
            normalized value. Must block until recompute's transaction
            releases the lock.
            """
            started.set()
            try:
                with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
                    locked_ad = Ad.objects.select_for_update().get(pk=ad_id)
                    locked_ad.price_amount = 200
                    locked_ad.price_normalized_eur = Decimal("102.4000")
                    locked_ad.save(
                        update_fields=["price_amount", "price_normalized_eur"]
                    )
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                finished.set()
                connection.close()

        # --- Main thread: simulate recompute's _process_batch read+write ---
        # Uses transaction=True (pytestmark below) so this atomic block is a
        # real transaction — row locks are released only on commit, not on
        # savepoint commit.
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
            locked_ad = (
                Ad.objects.select_for_update().filter(pk=ad_id).only(
                    "pk", "price_amount", "price_currency", "price_normalized_eur"
                ).get()
            )
            # Recompute computes 51.20 for price 100 BAM and writes it, while
            # still holding the row lock (read through bulk_update window).
            locked_ad.price_normalized_eur = Decimal("51.2000")
            locked_ad.save(update_fields=["price_normalized_eur"])

            # --- Start the concurrent price edit ---
            thread = threading.Thread(target=concurrent_price_edit)
            thread.start()

            assert started.wait(timeout=5), "Background thread did not start"

            # The edit must be blocked waiting for the row lock.
            time.sleep(1.0)
            assert not finished.is_set(), (
                "Concurrent price edit completed before lock was released — "
                "select_for_update did not block it"
            )

        # --- Recomputed transaction commits, releasing the row lock ---
        # The concurrent edit can now proceed and must not be lost.
        assert finished.wait(timeout=10), (
            "Concurrent price edit did not complete after lock was released"
        )
        thread.join(timeout=10)

        assert not errors, f"Background thread raised: {errors}"

        ad.refresh_from_db()
        assert ad.price_amount == 200
        assert ad.price_normalized_eur == Decimal("102.4000"), (
            "price_normalized_eur was overwritten by recompute — lost update "
            "(concurrent edit should have won after recompute committed)"
        )
