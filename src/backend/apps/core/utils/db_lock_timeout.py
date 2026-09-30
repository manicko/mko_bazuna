"""Shared classifier for PostgreSQL lock-acquisition timeouts (03-DB-004).

A connection-level ``lock_timeout`` (rendered into
``DATABASES["default"]["OPTIONS"]["options"]`` in ``config/settings/base.py``)
bounds every wait for a row, table or advisory lock. When the bound is reached
PostgreSQL cancels the waiting statement with

    canceling statement due to lock timeout        SQLSTATE 55P03

which the psycopg driver surfaces as ``psycopg.errors.LockNotAvailable``. Django
wraps that as ``django.db.utils.OperationalError``.

Both processes use this one predicate so the web tier, the bot handlers and the
management commands agree on what a lock timeout is. The predicate is
deliberately narrow: a connection refusal, a disk-full or an administrator
shutdown is **not** a lock timeout and must keep its existing behaviour.

Implementation note: Django's ``DatabaseErrorWrapper`` does **not** re-export
``sqlstate`` on the wrapper (``exc.sqlstate`` is ``None``); the driver error is
one level down on ``exc.__cause__``. Matching is on SQLSTATE only — the message
text is locale- and version-fragile, and ``57014`` is a different,
separately-deferred policy.
"""

import logging
from typing import Final

logger = logging.getLogger(__name__)

# PostgreSQL SQLSTATE for a cancelled lock wait: "canceling statement due to
# lock timeout". Always raised as psycopg.errors.LockNotAvailable.
LOCK_TIMEOUT_SQLSTATE: Final[str] = "55P03"

# ``57014`` is ``query_canceled``: a statement cancelled by *any* producer —
# ``statement_timeout``, ``pg_cancel_backend()``, PgBouncer's server cancel and
# ``idle_session_timeout`` — so it does NOT attribute the cancel to
# ``statement_timeout``. It is deliberately NOT matched by ``is_lock_timeout``:
# a lock timeout is ``55P03``, not ``57014``. No constant is defined for it — the
# value has no consumer, and a module-level name for a non-policy would invite
# one to be written.


def is_lock_timeout(exc: BaseException) -> bool:
    """Return True only for a PostgreSQL lock-acquisition timeout (55P03).

    Reads the driver error's SQLSTATE from ``exc.__cause__``, because Django's
    ``DatabaseErrorWrapper`` does not re-export ``sqlstate`` on the wrapper it
    raises. ``57014`` (``query_canceled``), a connection refusal or any error
    without a wrapped driver cause returns False, so callers can re-raise
    everything that is not a lock timeout and preserve its existing behaviour.

    Args:
        exc: The exception to classify, typically a
            ``django.db.utils.OperationalError``.

    Returns:
        True when the wrapped driver error reports SQLSTATE ``55P03``.
    """
    return getattr(exc.__cause__, "sqlstate", None) == LOCK_TIMEOUT_SQLSTATE
