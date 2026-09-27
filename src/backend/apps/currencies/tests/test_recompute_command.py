"""
Tests for the ``recompute_normalized_prices`` management command (spec Task 11).

Also covers DB-001: the batch read in ``_process_batch`` uses
``select_for_update()`` so a concurrent web/bot price edit cannot overwrite the
correctly-computed ``price_normalized_eur`` with a stale value (lost update).
"""

from __future__ import annotations

import inspect
import threading
import time
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.db import connection, transaction

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from apps.currencies.enums import CurrencyCode
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _clear_rate_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


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
        self, exchange_rates, seller, category, city
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

        call_command("recompute_normalized_prices", dry_run=True)

        ad.refresh_from_db()
        assert ad.price_normalized_eur == Decimal("999")

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

    def test_process_batch_uses_select_for_update(self) -> None:
        """``_process_batch`` locks the batch rows with ``select_for_update``.

        DB-001: the batch read must acquire a row lock (inside the
        ``transaction.atomic()`` block opened by ``handle()``) so a concurrent
        web/bot edit changing ``price_amount`` cannot race between the read and
        the blind ``bulk_update`` on ``price_normalized_eur``.
        """
        from apps.currencies.management.commands import (
            recompute_normalized_prices,
        )

        source = inspect.getsource(
            recompute_normalized_prices.Command._process_batch
        )
        assert "select_for_update" in source


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

    @pytest.mark.concurrent
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
