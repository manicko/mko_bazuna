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
        - Phase 4 jobs: 1-5 (archive_sweep, delete_sweep, consent_hard_delete,
                             sweep_drafts, cleanup_login_tokens)
        - Phase 2 jobs: 6-7 (purge_failed_ads, purge_rejected_ads)
        - migrate service: 100 (session-scoped, runs pre-PgBouncer)
        - create_admin_user: 101 (session-scoped)
        - backfill_thumbnails: 102 (session-scoped)
        - seed service: 110 (session-scoped)
        - test schema setup: 111 (session-scoped, serializes xdist workers)
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
