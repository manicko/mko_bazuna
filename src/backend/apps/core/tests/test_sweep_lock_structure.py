"""Integration tests verifying sweep/purge command advisory-lock ordering.

Guards the DB-001 fix: every scheduled sweep/purge command must acquire its
PostgreSQL advisory lock (``pg_advisory_xact_lock``) *inside* a
``transaction.atomic()`` block. Transaction-scoped locks are released at
commit/rollback, so acquiring the lock in autocommit (outside ``atomic()``)
would release it before the count-to-mutate sequence runs, letting concurrent
scheduler workers race.

Once per-batch commit lands (finding 03-DB-008), ``archive_sweep`` and
``recompute_normalized_prices`` are the exception: a transaction-scoped lock
would be released by the first batch ``COMMIT``, so they hold a **session-scoped**
lock (``pg_advisory_lock``) taken once and released when the sweep ends — and
therefore cannot be inside an enclosing ``atomic()`` (an enclosing ``atomic()``
would turn each per-batch ``atomic()`` into a savepoint, so nothing would ever
commit). See ``_SESSION_SCOPED_BATCHERS``. Every other command keeps the
transaction-scoped, PgBouncer-safe shape this module enforces.

These tests observe run-time behaviour rather than static source structure: a
spy replaces ``advisory_lock`` and each command is driven through
``call_command``; we assert the spy is invoked with the correct
``AdvisoryLockId`` member while a transaction is active.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import DEFAULT, AsyncMock, MagicMock

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from apps.core.enums import AdStatus, AdvisoryLockId
from apps.search.management.commands import send_alerts
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# (management command name, AdvisoryLockId member acquired on the production
# path). send_alerts is run without --dry-run so the transaction-wrapped lock
# path is exercised; the dry-run path now also uses a transaction-scoped lock
# (matching the production path) but is not exercised by the spy because
# call_command does not pass --dry-run.
#
# Exceptions to the transaction-scoped rule: the two commands in
# ``_SESSION_SCOPED_BATCHERS`` lock with a session-scoped lock for the whole
# sweep (see the module docstring). Their entries below are asserted positively
# (``session is True`` / ``in_atomic is False``); the rest are byte-identical.
#
# This is the ONE list of transaction-scoped lock-taking management commands:
# every command that acquires a transaction-scoped advisory lock must appear
# here so its ``session is False`` / ``in_atomic is True`` guarantee stays
# covered. ``EXPECTED_SWEEP_COMMANDS`` pins the name set independently of this
# list, so an accidental omission or a stray append fails loudly instead of
# silently changing coverage.
SWEEP_COMMANDS: list[tuple[str, AdvisoryLockId]] = [
    ("archive_sweep", AdvisoryLockId.ARCHIVE_SWEEP),
    ("delete_sweep", AdvisoryLockId.DELETE_SWEEP),
    ("consent_hard_delete", AdvisoryLockId.CONSENT_HARD_DELETE),
    ("cleanup_login_tokens", AdvisoryLockId.CLEANUP_LOGIN_TOKENS),
    ("sweep_drafts", AdvisoryLockId.SWEEP_DRAFTS),
    ("sweep_orphaned_media", AdvisoryLockId.SWEEP_ORPHANED_MEDIA),
    ("purge_failed_ads", AdvisoryLockId.PURGE_FAILED_ADS),
    ("purge_rejected_ads", AdvisoryLockId.PURGE_REJECTED_ADS),
    ("purge_deleted_ads", AdvisoryLockId.PURGE_DELETED_ADS),
    ("rollup_daily_metrics", AdvisoryLockId.ROLLUP_DAILY_METRICS),
    ("backfill_thumbnails", AdvisoryLockId.BACKFILL_THUMBNAILS),
    ("send_alerts", AdvisoryLockId.ALERT_DELIVERY_TASK),
    ("recompute_normalized_prices", AdvisoryLockId.RECOMPUTE_NORMALIZED_PRICES),
    ("repair_bot_username", AdvisoryLockId.REPAIR_BOT_USERNAME),
    ("purge_consent_records", AdvisoryLockId.CONSENT_RECORD_SWEEP),
    ("purge_media_deletion_errors", AdvisoryLockId.PURGE_MEDIA_DELETION_ERRORS),
]

# The exact set of transaction-scoped lock-taking commands covered above.
# Kept as an explicit constant (rather than derived from ``SWEEP_COMMANDS``) so
# the coverage assertion below is independent of the list it guards: adding or
# removing an entry is a deliberate act that must update this set, rather than a
# change that silently satisfies or silently breaks the coupling.
EXPECTED_SWEEP_COMMANDS: frozenset[str] = frozenset(
    {
        "archive_sweep",
        "delete_sweep",
        "consent_hard_delete",
        "cleanup_login_tokens",
        "sweep_drafts",
        "sweep_orphaned_media",
        "purge_failed_ads",
        "purge_rejected_ads",
        "purge_deleted_ads",
        "rollup_daily_metrics",
        "backfill_thumbnails",
        "send_alerts",
        "recompute_normalized_prices",
        "repair_bot_username",
        "purge_consent_records",
        "purge_media_deletion_errors",
    }
)

# 03-DB-008: these two batch inside per-batch transactions, so they hold a
# SESSION-scoped advisory lock (pg_advisory_lock) — a transaction-scoped one
# would be released by the first batch COMMIT — and therefore cannot be inside
# an enclosing atomic(). Every other entry keeps the transaction-scoped,
# PgBouncer-safe shape, which the assertion below still enforces.
_SESSION_SCOPED_BATCHERS = frozenset(
    {"archive_sweep", "recompute_normalized_prices"}
)

# Every sweep command binds ``advisory_lock`` through
# ``from apps.core.utils.advisory_lock import advisory_lock`` at import time, so
# patching the source module alone does not intercept their calls. The spy must
# also replace the name bound in each command module.
_LOCK_TARGET_MODULES: tuple[str, ...] = (
    "apps.core.management.commands.archive_sweep",
    "apps.core.management.commands.delete_sweep",
    "apps.core.management.commands.consent_hard_delete",
    "apps.core.management.commands.cleanup_login_tokens",
    "apps.core.management.commands.sweep_drafts",
    "apps.core.management.commands.purge_failed_ads",
    "apps.core.management.commands.purge_rejected_ads",
    "apps.core.management.commands.purge_deleted_ads",
    "apps.analytics.management.commands.rollup_daily_metrics",
    "apps.media.management.commands.backfill_thumbnails",
    "apps.media.management.commands.sweep_orphaned_media",
    "apps.search.management.commands.send_alerts",
    "apps.currencies.management.commands.recompute_normalized_prices",
    "apps.core.management.commands.repair_bot_username",
    "apps.core.management.commands.purge_consent_records",
    "apps.media.management.commands.purge_media_deletion_errors",
)


class TestSweepLockOrdering:
    """Runtime verification that each sweep command acquires its advisory lock
    inside ``transaction.atomic()``."""

    @pytest.mark.django_db(transaction=True)
    def test_all_sweep_commands_lock_inside_transaction(self, monkeypatch):
        """Drive every sweep command with a no-op advisory-lock spy and assert
        each is called with the correct ``AdvisoryLockId`` member while a
        transaction is active.

        ``transaction=True`` is required so the test is not wrapped in an outer
        transaction: otherwise ``in_atomic_block`` is True regardless of whether
        the command opens its own ``transaction.atomic()``, making the DB-001
        assertion vacuous.
        """
        lock_calls: list[tuple[AdvisoryLockId, bool, bool]] = []

        def _spy(lock_id, *, session: bool = False):
            lock_calls.append(
                (lock_id, session, transaction.get_connection().in_atomic_block)
            )
            # Returning DEFAULT makes the mock substitute its own (MagicMock)
            # return value, which is a no-op context manager — so the commands
            # run their logic without acquiring a real PostgreSQL lock.
            return DEFAULT

        spy = MagicMock(side_effect=_spy)

        # Patch the canonical definition ...
        monkeypatch.setattr("apps.core.utils.advisory_lock.advisory_lock", spy)
        # ... plus the binding imported into each command module (see note
        # above — ``from ... import advisory_lock`` is bound at import time).
        for module_name in _LOCK_TARGET_MODULES:
            monkeypatch.setattr(f"{module_name}.advisory_lock", spy)

        # send_alerts' production path performs Telegram I/O (Bot token
        # validation + network) after the transaction commits; stub the digest
        # sender so the spy test stays hermetic and token-free.
        monkeypatch.setattr(send_alerts.Command, "_send_user_digests", AsyncMock())

        # repair_bot_username refuses (CommandError) before reaching its lock
        # when BOT_USERNAME is empty or malformed — .env.test ships the
        # placeholder "test-bot", which fails the handle pattern. Supply a
        # valid format so the production lock path is actually exercised; this
        # is test setup only and does not touch any command's logic.
        monkeypatch.setattr(settings, "BOT_USERNAME", "test_bot_username_repair")

        for command_name, _expected_id in SWEEP_COMMANDS:
            call_command(command_name)

        # Coverage is pinned to an explicit name set, not to
        # ``len(SWEEP_COMMANDS)``: the assertion must fail when a lock-taking
        # command is missing from the list or a duplicate hides one, which
        # ``len(lock_calls) == len(SWEEP_COMMANDS)`` cannot detect. The lock-call
        # count is checked against the independent constant for the same reason:
        # one call per listed command means exactly one lock site each.
        assert {name for name, _ in SWEEP_COMMANDS} == EXPECTED_SWEEP_COMMANDS
        assert len(lock_calls) == len(EXPECTED_SWEEP_COMMANDS)

        by_lock_id = {entry[0]: entry for entry in lock_calls}
        for command_name, expected_lock_id in SWEEP_COMMANDS:
            assert expected_lock_id in by_lock_id, (
                f"{command_name}: advisory_lock was not called"
            )
            _lock_id, session, in_atomic = by_lock_id[expected_lock_id]
            if command_name in _SESSION_SCOPED_BATCHERS:
                # 03-DB-008: per-batch commit requires a session-scoped lock
                # held across every batch, which in turn forbids an enclosing
                # atomic() (it would make each per-batch atomic() a savepoint).
                assert session is True, (
                    f"{command_name}: per-batch sweep must hold a session-scoped "
                    "(pg_advisory_lock) advisory lock across every batch"
                )
                assert in_atomic is False, (
                    f"{command_name}: per-batch sweep must NOT be inside an "
                    "enclosing transaction.atomic() — that would turn each "
                    "per-batch atomic() into a savepoint (03-DB-008)"
                )
                continue
            assert in_atomic is True, (
                f"{command_name}: advisory_lock acquired outside "
                "transaction.atomic() — pg_advisory_xact_lock would release "
                "the lock before the mutation runs (DB-001)"
            )
            assert session is False, (
                f"{command_name}: production sweep must use a transaction-scoped "
                "(non-session) lock"
            )


class TestArchiveSweepPositivePath:
    """Behavioural positive-path test for archive_sweep's retention window."""

    @pytest.mark.parametrize("age_days", [61, 90, 180])
    def test_archives_published_ad_older_than_retention(
        self, seller, category, city, age_days: int
    ) -> None:
        """A PUBLISHED ad whose published_at is older than the 60-day cutoff is
        transitioned to ARCHIVED by archive_sweep."""
        stale = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            published_at=timezone.now() - timedelta(days=age_days),
        )
        call_command("archive_sweep")
        stale.refresh_from_db()
        assert stale.status == AdStatus.ARCHIVED
        assert stale.archived_at is not None
