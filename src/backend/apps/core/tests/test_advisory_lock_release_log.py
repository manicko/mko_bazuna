"""
Unit test for PII-002: transaction-scoped advisory lock release logging.

The transaction-scoped branch of ``advisory_lock`` must register a
``transaction.on_commit`` callback that logs lock release, restoring
observability symmetry with the session-scoped branch (which logs both
acquire and release). The on_commit callback fires only on successful
commit — matching when pg_advisory_xact_lock releases the lock.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from django.db import transaction

from apps.core.utils.advisory_lock import advisory_lock

pytestmark = [pytest.mark.unit]


def test_transaction_scoped_lock_logs_release_on_commit(caplog) -> None:
    """Transaction-scoped advisory_lock registers an on_commit release log.

    on_commit is patched to execute the callback immediately, simulating a
    successful commit, so the release log is emitted inline without a real
    database transaction.
    """
    caplog.set_level(logging.INFO, logger="apps.core.utils.advisory_lock")

    with (
        patch.object(transaction, "on_commit", side_effect=lambda fn: fn()),
        patch(
            "apps.core.utils.advisory_lock.transaction.get_connection"
        ) as mock_get_conn,
        patch("apps.core.utils.advisory_lock.connection"),
    ):
        mock_get_conn.return_value.in_atomic_block = True
        with advisory_lock(1234):
            pass

    messages = [r.message for r in caplog.records]
    assert any("Acquired transaction advisory lock 1234" in m for m in messages)
    assert any("Released transaction advisory lock 1234" in m for m in messages)


def test_transaction_scoped_lock_registers_on_commit_callback() -> None:
    """advisory_lock registers an on_commit callback for the xact branch.

    Structural companion: with on_commit stubbed (not executed), assert the
    callback was actually registered for the transaction-scoped path.
    """
    registered: list = []

    def _record(fn):
        registered.append(fn)

    with (
        patch.object(transaction, "on_commit", side_effect=_record),
        patch(
            "apps.core.utils.advisory_lock.transaction.get_connection"
        ) as mock_get_conn,
        patch("apps.core.utils.advisory_lock.connection"),
    ):
        mock_get_conn.return_value.in_atomic_block = True
        with advisory_lock(999):
            pass

    assert len(registered) == 1
