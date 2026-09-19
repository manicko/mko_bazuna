"""
PostgreSQL advisory lock context manager for idempotent, locked operations.

Uses transaction-scoped locks (pg_advisory_xact_lock) which are safe under PgBouncer.
For the migrate service, session-scoped lock (pg_advisory_lock) is used because it runs
before PgBouncer is attached to the database.
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
        to prevent the autocommit-release bug (DB-001).

    Lock ID allocation (see AdvisoryLockId enum in apps.core.enums):

    Transaction-scoped (pg_advisory_xact_lock; safe under PgBouncer, held
    inside transaction.atomic()):
          1  ARCHIVE_SWEEP                archive sweep
          2  DELETE_SWEEP                 hard-delete sweep
          3  CONSENT_HARD_DELETE          consent hard delete
          4  SWEEP_DRAFTS                 draft sweep
          5  CLEANUP_LOGIN_TOKENS         login-token cleanup
          6  PURGE_FAILED_ADS             failed-ad purge
          7  PURGE_REJECTED_ADS           rejected-ad purge
          8  ROLLUP_DAILY_METRICS         daily metrics rollup
          9  ALERT_DELIVERY_TASK          search-alert delivery (production path)
         11  PURGE_DELETED_ADS            deleted-ad purge
         12  RECOMPUTE_NORMALIZED_PRICES  price normalization

    Session-scoped (pg_advisory_lock; spans the connection, pre-PgBouncer):
        100  MIGRATE                      post-migration setup (runs pre-PgBouncer)
        101  CREATE_ADMIN                 admin creation
        102  BACKFILL_THUMBNAILS          thumbnail backfill
        103  SWEEP_ORPHANED_MEDIA         orphaned media sweep
        104  CATALOG_LOAD                 catalog load
        110  SEED                         seed service
        111  TEST_SCHEMA_SETUP            test schema setup (serializes xdist workers)

    ID 10 is intentionally unused/reserved; it was formerly QUEUE_PROCESSING and
    was removed in DB-007. IDs 13-99 are reserved for future scheduled jobs.
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
            yield
