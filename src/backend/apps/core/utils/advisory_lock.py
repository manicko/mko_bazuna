"""
PostgreSQL advisory lock context manager for idempotent, locked operations.

Uses transaction-scoped locks (pg_advisory_xact_lock) which are safe under PgBouncer.
For the migrate service, session-scoped lock (pg_advisory_lock) is used because it runs
before PgBouncer is attached to the database.
"""

import logging
from contextlib import contextmanager

from django.db import connection

logger = logging.getLogger(__name__)


@contextmanager
def advisory_lock(lock_id: int, *, session: bool = False):
    """
    Context manager for PostgreSQL advisory locks.

    Args:
        lock_id: Lock identifier (must be unique per operation). See AdvisoryLockId enum
                 in apps.core.enums for the canonical ID allocation.
        session: If True, use session-scoped lock (pg_advisory_lock).
                 If False, use transaction-scoped lock (pg_advisory_xact_lock).
                 Session locks must be explicitly released; transaction locks release
                 on commit/rollback.

    Lock ID allocation (see AdvisoryLockId enum in apps.core.enums):
        - Phase 4 jobs: 1-5 (archive_sweep, delete_sweep, consent_hard_delete,
                             sweep_drafts, cleanup_login_tokens)
        - Phase 2 jobs: 6-7 (purge_failed_ads, purge_rejected_ads)
        - migrate service: 100 (session-scoped, runs pre-PgBouncer)
    """
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