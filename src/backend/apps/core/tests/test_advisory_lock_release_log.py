"""
Unit test for the transaction-scoped advisory-lock release log.

The transaction-scoped branch of ``advisory_lock`` must log lock release on
*both* transaction outcomes: the normal exit path (the transaction commits and
``pg_advisory_xact_lock`` releases) and the exception path (the transaction
rolls back and the lock is likewise released). Logging the release from a
``finally`` block is what makes the line observable precisely when a sweep
fails, instead of only when it succeeds.

The tests here do not open a real database transaction: ``connection`` and the
atomic-block check are patched, so the release log is exercised in isolation
from any real commit or rollback.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from apps.core.utils.advisory_lock import advisory_lock

pytestmark = [pytest.mark.unit]


def _run_lock_block(lock_id: int, body) -> None:
    """Enter ``advisory_lock`` under a patched connection and run ``body``."""
    with (
        patch(
            "apps.core.utils.advisory_lock.transaction.get_connection"
        ) as mock_get_conn,
        patch("apps.core.utils.advisory_lock.connection"),
    ):
        mock_get_conn.return_value.in_atomic_block = True
        with advisory_lock(lock_id):
            body()


def test_transaction_scoped_lock_logs_release_on_commit(caplog) -> None:
    """The release line is emitted on the normal (commit) exit path."""
    caplog.set_level(logging.INFO, logger="apps.core.utils.advisory_lock")

    _run_lock_block(1234, lambda: None)

    messages = [r.message for r in caplog.records]
    assert any("Acquired transaction advisory lock 1234" in m for m in messages)
    assert any("Released transaction advisory lock 1234" in m for m in messages)


def test_transaction_scoped_lock_logs_release_on_rollback(caplog) -> None:
    """The release line is emitted when the body raises.

    ``pg_advisory_xact_lock`` releases on rollback as well as on commit, so the
    release line must be observable on the failure path — the case an operator
    actually needs it. The exception must still propagate to the caller.
    """
    caplog.set_level(logging.INFO, logger="apps.core.utils.advisory_lock")

    def _raise() -> None:
        raise ValueError("simulated sweep failure")

    with pytest.raises(ValueError, match="simulated sweep failure"):
        _run_lock_block(4321, _raise)

    messages = [r.message for r in caplog.records]
    assert any("Released transaction advisory lock 4321" in m for m in messages), (
        "expected the release line on the rollback path; it is omitted when the "
        "release log is registered via transaction.on_commit"
    )
