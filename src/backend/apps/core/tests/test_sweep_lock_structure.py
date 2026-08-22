"""Unit tests verifying sweep/purge command transaction ordering.

Pure source-inspection tests (``inspect.getsource``) — no database access.
They assert that every sweep/purge management command wraps its advisory lock
inside ``transaction.atomic()`` (DB-001 fix): the PostgreSQL
``pg_advisory_xact_lock`` is transaction-scoped, so it must be acquired inside
an atomic block, not outside.

These were extracted from ``test_sweep_commands.py`` (which is DB-backed,
``slow`` + ``integration``) so they can run under ``-m unit`` without a
database.
"""

from __future__ import annotations

import inspect

import pytest

from apps.analytics.management.commands import rollup_daily_metrics
from apps.core.management.commands import (
    archive_sweep,
    cleanup_login_tokens,
    consent_hard_delete,
    delete_sweep,
    purge_deleted_ads,
    purge_failed_ads,
    purge_rejected_ads,
    sweep_drafts,
)
from apps.media.management.commands import backfill_thumbnails
from apps.search.management.commands import send_alerts

pytestmark = [pytest.mark.unit]


class TestSweepLockStructure:
    """Verify every sweep/purge command acquires the advisory lock inside
    ``transaction.atomic()``."""

    def test_archive_sweep_lock_inside_transaction(self) -> None:
        """Verify archive_sweep acquires the advisory lock inside transaction.atomic.

        DB-001 fix: the advisory lock (pg_advisory_xact_lock) is transaction-scoped,
        so it must be acquired *inside* a transaction.atomic() block, not outside.
        This test verifies the code structure matches the correct ordering.
        """
        source = inspect.getsource(archive_sweep.Command.handle)
        # The correct pattern: transaction.atomic() wraps advisory_lock()
        tx_idx = source.find("with transaction.atomic")
        lock_idx = source.find("with advisory_lock")
        assert tx_idx < lock_idx, (
            "transaction.atomic() must wrap advisory_lock() — lock-then-atomic "
            "releases the xact_lock in autocommit before the transaction opens"
        )

    def test_all_sweeps_lock_inside_transaction(self) -> None:
        """Verify all sweep commands have transaction.atomic() before advisory_lock."""
        # These commands use the standard pattern: tx wraps advisory_lock
        standard_commands = [
            archive_sweep,
            delete_sweep,
            sweep_drafts,
            consent_hard_delete,
            cleanup_login_tokens,
            purge_failed_ads,
            purge_rejected_ads,
            purge_deleted_ads,
            rollup_daily_metrics,
            backfill_thumbnails,
        ]

        for mod in standard_commands:
            source = inspect.getsource(mod.Command.handle)
            tx_idx = source.find("with transaction.atomic")
            lock_idx = source.find("with advisory_lock")
            assert tx_idx != -1 and lock_idx != -1, (
                f"{mod.__name__}: missing transaction.atomic or advisory_lock"
            )
            assert tx_idx < lock_idx, (
                f"{mod.__name__}: transaction.atomic() must wrap advisory_lock()"
            )

        # send_alerts has a dry-run path (session lock, no writes) +
        # a production path (transaction-wrapped advisory lock).
        # Verify the production path order: tx -> advisory_lock (not session=True)
        send_source = inspect.getsource(send_alerts.Command.handle)
        # Find the production (non-dry-run) advisory_lock
        prod_lock_idx = send_source.find(
            "with advisory_lock(AdvisoryLockId.ALERT_DELIVERY_TASK):"
        )
        prod_tx_idx = send_source.find("with transaction.atomic", 0, prod_lock_idx)
        assert prod_tx_idx != -1 and prod_lock_idx != -1, (
            "send_alerts: missing transaction.atomic wrapping advisory_lock"
        )
        assert prod_tx_idx < prod_lock_idx, (
            "send_alerts: transaction.atomic() must wrap advisory_lock()"
        )
