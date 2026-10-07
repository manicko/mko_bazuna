"""
PostgreSQL advisory lock context manager for idempotent, locked operations.

Uses transaction-scoped locks (pg_advisory_xact_lock) which are safe under PgBouncer.
Session-scoped locks (pg_advisory_lock) are used for the migrate service (before
PgBouncer attaches to the database) and for archive_sweep and
recompute_normalized_prices, whose per-batch commits would release a
transaction-scoped lock at the first batch boundary — see the lock ID allocation
table below for the full assignment and the PgBouncer caveat.
"""

import logging
from contextlib import contextmanager

from django.db import connection, transaction

logger = logging.getLogger(__name__)


@contextmanager
def advisory_lock(lock_id: int, *, session: bool = False):
    """Context manager for PostgreSQL advisory locks.

    Args:
        lock_id: Lock identifier (must be unique per operation). See AdvisoryLockId enum
                 in apps.core.enums for the canonical ID allocation.
        session: If True, use session-scoped lock (pg_advisory_lock).
                 If False, use transaction-scoped lock (pg_advisory_xact_lock).
                 Session locks must be explicitly released; transaction locks release
                 on commit/rollback.

    Important:
        Transaction-scoped locks (session=False) are released at the end of the
        current database transaction. Callers **must** wrap the entire operation
        inside ``transaction.atomic()`` to ensure the lock covers the full
        count-to-mutate sequence. This function asserts that a transaction is active
        to prevent the autocommit-release bug.

    Lock ID allocation (see AdvisoryLockId enum in apps.core.enums):

    Transaction-scoped (pg_advisory_xact_lock; safe under PgBouncer, held
    inside transaction.atomic()):
          2  DELETE_SWEEP                 hard-delete sweep
          3  CONSENT_HARD_DELETE          consent hard delete
          4  SWEEP_DRAFTS                 draft sweep
          5  CLEANUP_LOGIN_TOKENS         login-token cleanup
          6  PURGE_FAILED_ADS             failed-ad purge
          7  PURGE_REJECTED_ADS           rejected-ad purge
          8  ROLLUP_DAILY_METRICS         daily metrics rollup
          9  ALERT_DELIVERY_TASK          search-alert delivery (production path)
          11  PURGE_DELETED_ADS            deleted-ad purge
          13  REPAIR_BOT_USERNAME           BOT_USERNAME repair
          14  CONSENT_RECORD_SWEEP         consent-record retention sweep
          15  PURGE_MEDIA_DELETION_ERRORS  deletion-error retention purge
          102  BACKFILL_THUMBNAILS          thumbnail backfill
          103  SWEEP_ORPHANED_MEDIA         orphaned media sweep

    Session-scoped (pg_advisory_lock; spans the connection, pre-PgBouncer):
          1  ARCHIVE_SWEEP                archive sweep (per-batch commits)
          12  RECOMPUTE_NORMALIZED_PRICES  price normalization (per-batch commits)
          100  MIGRATE                      post-migration setup (runs pre-PgBouncer)
          101  CREATE_ADMIN                 admin creation
          104  CATALOG_LOAD                 catalog load
          110  SEED                         seed service
          111  TEST_SCHEMA_SETUP            test schema setup (serializes xdist workers)

    IDs 1 (ARCHIVE_SWEEP) and 12 (RECOMPUTE_NORMALIZED_PRICES) are session-scoped
    because their sweeps commit per batch: a transaction-scoped lock
    (pg_advisory_xact_lock) would be released by the first batch COMMIT, allowing
    a second scheduler worker to enter the sweep. They take ``session=True`` once
    and release via ``pg_advisory_unlock`` in a ``finally`` when the sweep ends —
    and therefore run OUTSIDE an enclosing ``transaction.atomic()`` (an
    enclosing ``atomic()`` would turn each per-batch ``atomic()`` into a
    savepoint, so no batch would ever truly commit). See BLOCK 7 / finding
    03-DB-008 and ``test_sweep_lock_structure.py::_SESSION_SCOPED_BATCHERS``.

    PgBouncer caveat (Q11 / 03-DB-008 resolution): a session-scoped lock is
    bound to the pooled backend connection and is NOT safe under PgBouncer
    transaction-mode pooling — ``session=True`` is the documented pre-PgBouncer
    deployment shape and is only correct where the scheduler runs before
    PgBouncer attaches the pool (or on a dedicated non-pooled connection).

    ID 10 is intentionally unused/reserved; it was formerly QUEUE_PROCESSING and
    was removed. IDs 16-99 are reserved for future scheduled jobs.
    """
    if not session:
        if not transaction.get_connection().in_atomic_block:
            raise RuntimeError(
                "advisory_lock (transaction-scoped) must be called inside "
                "transaction.atomic(). Acquire the lock inside the transaction "
                "block: `with transaction.atomic(): with advisory_lock(N): ...`"
            )

    with connection.cursor() as cursor:
        if session:
            # Log acquisition intent BEFORE pg_advisory_lock so a contending
            # run (which blocks until the lock is granted) is not a silent
            # hang. Deliberately placed only in the session branch: the
            # transaction-scoped branch logs acquisition then release around
            # its yield, and 03-DB-004 owns any timeout wording.
            logger.info("Requesting session advisory lock %s", lock_id)
            cursor.execute("SELECT pg_advisory_lock(%s)", [lock_id])
            logger.info("Acquired session advisory lock %s", lock_id)
            try:
                yield
            finally:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [lock_id])
                logger.info("Released session advisory lock %s", lock_id)
        else:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_id])
            logger.info("Acquired transaction advisory lock %s", lock_id)
            try:
                yield
            finally:
                # pg_advisory_xact_lock releases on both commit and rollback;
                # log the release here so it is observed on the failure path too.
                logger.info("Released transaction advisory lock %s", lock_id)
