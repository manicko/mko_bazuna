"""Completeness guard for the declarative PII erasure inventory.

These are unit tests: the guard resolves model metadata and reads the
declaration, and needs no database. The "importable without a database
connection" constraint is proven two ways: the declaration is read in a fresh
interpreter whose database is unusable, and a ``CaptureQueriesContext`` proves
that reading it executes no SQL. The tripwire is on *declared* columns, not a
classifier: it cannot decide whether a column is personally identifiable, only
that every data column on a listed model was reviewed.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest
from django.apps import apps
from django.db import connection

from apps.users.services.pii_inventory import (
    PII_ERASURE_ENTRIES,
    REVIEWED_NON_IDENTITY_COLUMNS,
    ErasureAction,
)

pytestmark = [pytest.mark.unit]

#: Subprocess probe: configure Django against an unusable database host and an
#: unparseable ``DATABASE_URL``, then import and read the declaration. If the
#: import required a connection — or gained an ``apps.*`` model import at module
#: scope that resolves a model only on access — this fails. The probe resolves
#: no model: it reads only the declared data.
_IMPORT_WITHOUT_DB_CODE = """
import django
django.setup()
from apps.users.services.pii_inventory import (
    PII_ERASURE_ENTRIES,
    REVIEWED_NON_IDENTITY_COLUMNS,
    ErasureAction,
)
assert len(PII_ERASURE_ENTRIES) > 0
entry = PII_ERASURE_ENTRIES[0]
assert entry[0] and entry[1] and isinstance(entry[2], ErasureAction) and entry[3]
assert REVIEWED_NON_IDENTITY_COLUMNS
print("DECLARATION_READ_WITHOUT_DB")
"""

#: Column names the guard never treats as review candidates: the implicit
#: primary key and lifecycle/audit timestamps.
_NON_DATA_COLUMN_NAMES = frozenset({"id"})

_TIMESTAMP_NAMES = frozenset(
    {
        "created_at",
        "updated_at",
        "published_at",
        "original_published_at",
        "archived_at",
        "deleted_at",
        "moderation_failed_at",
        "rejected_at",
        "consent_given_at",
        "consent_revoked_at",
        "expires_at",
        "consumed_at",
        "last_calculated",
        "last_notified_at",
        "verified_at",
        "last_login",
        "date_joined",
    }
)


def _is_review_candidate(field) -> bool:
    """Return whether *field* is a concrete data column the guard reviews.

    Relational fields, the implicit pk and timestamp columns are not data
    columns in the erasure sense, so they are not required to carry an entry
    or a reviewed decision.
    """
    if not getattr(field, "concrete", False):
        return False
    if getattr(field, "related_model", None) is not None:
        return False
    if field.name in _NON_DATA_COLUMN_NAMES:
        return False
    if field.name in _TIMESTAMP_NAMES:
        return False
    return True


def _entry_lookup() -> dict[tuple[str, str], tuple[str, str, ErasureAction, str]]:
    """Index the declaration by ``(model_label, column)``."""
    return {
        (model_label, column): (model_label, column, action, reason)
        for model_label, column, action, reason in PII_ERASURE_ENTRIES
    }


def test_touching_the_declaration_opens_no_database_connection() -> None:
    """Importing and reading the declaration is possible with no usable database.

    The plan's literal wording is "importable without a database connection, so
    a data migration can consume it inside a RunPython." This asserts exactly
    that in a fresh interpreter whose database host is unroutable and whose
    ``DATABASE_URL`` is unparseable, so *any* connection attempt raises instead
    of being silently satisfied by the (long-lived) in-process test connection.

    The original assertion here — ``django.db.connection.connection is None`` —
    measured the session connection lifecycle, not this module's behaviour: the
    session-scoped autouse fixture ``_restore_test_schema_post_db_setup`` in
    ``conftest.py`` unblocks and runs migrations, leaving an ``IDLE`` connection
    object for the rest of the session regardless of what this module does. It
    was replaced rather than weakened.

    The in-process proof that no query is executed during a declaration read
    lives in ``test_reading_the_declaration_executes_no_query``.
    """
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"DATABASE_URL", "POSTGRES_HOST", "POSTGRES_PORT"}
    }
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    # Discrete POSTGRES_* branch (base.py handles it robustly): an unroutable
    # host/port so no connection attempt can succeed, while settings
    # construction itself must not connect.
    env["POSTGRES_HOST"] = "127.0.0.1"
    env["POSTGRES_PORT"] = "1"

    result = subprocess.run(
        [sys.executable, "-c", _IMPORT_WITHOUT_DB_CODE],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "DECLARATION_READ_WITHOUT_DB" in result.stdout


def test_reading_the_declaration_executes_no_query() -> None:
    """Reading the declaration issues zero SQL statements.

    This is the "no database access" half of the property, proven in-process
    even though a connection object already exists. A counting
    ``execute_wrapper`` spans the declaration access and the model resolution
    the guard performs (``apps.get_model`` resolves metadata without issuing
    SQL); it does not call ``ensure_connection()``, so the test stays a unit
    test and does not need the ``django_db`` marker it exists to avoid.
    """
    executed_sql: list[str] = []

    def _record(execute, sql, params, many, context):
        executed_sql.append(sql)
        return execute(sql, params, many, context)

    with connection.execute_wrapper(_record):
        model_label, _column, _action, _reason = PII_ERASURE_ENTRIES[0]
        # Resolving a model's metadata is not a query; assert that stays true
        # for the declaration's labels and for the reviewed-column mapping.
        for label in REVIEWED_NON_IDENTITY_COLUMNS:
            apps.get_model(label)
        apps.get_model(model_label)

    assert executed_sql == [], (
        f"reading the declaration executed {len(executed_sql)} "
        f"SQL statement(s): {executed_sql}"
    )


def test_every_declared_entry_resolves_to_a_real_field() -> None:
    """Each label resolves via apps.get_model and its column really exists.

    A renamed or dropped column fails the declaration instead of silently
    pointing at nothing.
    """
    for model_label, column, _action, _reason in PII_ERASURE_ENTRIES:
        model = apps.get_model(model_label)
        assert model is not None, f"{model_label!r} does not resolve to a model"
        field_names = {field.name for field in model._meta.get_fields()}
        assert column in field_names, (
            f"declared column {column!r} does not exist on model "
            f"{model_label!r}"
        )


def test_listed_models_have_no_unreviewed_column() -> None:
    """Tripwire: every data column is declared or explicitly reviewed out.

    For each model in ``REVIEWED_NON_IDENTITY_COLUMNS``, no concrete,
    non-relational, non-timestamp column may lack an erasure entry or a
    reviewed decision. The failure message names the model and the column.
    """
    lookup = _entry_lookup()

    for model_label, reviewed_columns in REVIEWED_NON_IDENTITY_COLUMNS.items():
        model = apps.get_model(model_label)
        for field in model._meta.get_fields():
            if not _is_review_candidate(field):
                continue
            column = field.name
            declared = (model_label, column) in lookup
            reviewed = column in reviewed_columns
            assert declared or reviewed, (
                f"unreviewed column on {model_label!r}: {column!r} has neither "
                f"a PII_ERASURE_ENTRIES entry nor a "
                f"REVIEWED_NON_IDENTITY_COLUMNS decision"
            )


def test_user_chat_id_is_a_declared_retain() -> None:
    """User.chat_id is RETAIN with a non-empty reason; nothing nulls/clears it.

    ``AccountStateMiddleware._resolve_user`` depends on ``chat_id`` surviving
    withdrawal, so no entry anywhere may set ``chat_id`` to NULL or CLEAR.
    """
    lookup = _entry_lookup()

    entry = lookup.get(("users.User", "chat_id"))
    assert entry is not None, "User.chat_id must be a declared entry"
    _label, _column, action, reason = entry
    assert action == ErasureAction.RETAIN
    assert reason.strip(), "User.chat_id RETAIN reason must be non-empty"

    for entry_model_label, column, action, _reason in PII_ERASURE_ENTRIES:
        if (entry_model_label, column) != ("users.User", "chat_id"):
            continue
        assert action not in (ErasureAction.NULL, ErasureAction.CLEAR), (
            "User.chat_id must never be NULL/CLEAR; "
            "AccountStateMiddleware resolves the acting user on it"
        )


def test_user_password_is_declared_clear_but_unimplemented() -> None:
    """User.password is CLEAR and the reason says it is not erased today.

    The acceptance criterion is specific: ``withdraw_consent`` does not erase
    the credential hash and no phase-06 block implements it (06-NEW-03). The
    reason must say so in plain words rather than imply it is handled.
    """
    lookup = _entry_lookup()

    entry = lookup.get(("users.User", "password"))
    assert entry is not None, "User.password must be a declared entry"
    _label, _column, action, reason = entry
    assert action == ErasureAction.CLEAR
    lowered = reason.lower()
    assert "not implemented" in lowered or "does not" in lowered, (
        "User.password reason must state the clear is not implemented today"
    )
    assert "withdraw_consent" in reason, (
        "User.password reason must name withdraw_consent as not erasing it"
    )
    assert "06-new-03" in lowered, (
        "User.password reason must cite 06-NEW-03"
    )


def test_retained_free_text_entries_name_their_owning_block() -> None:
    """Free-text columns carry an explicit entry whose reason names its block.

    Free text is where a subject's data is most likely to hide, so each such
    column must carry an explicit entry whose reason names the owning block —
    a deferral with an owner, not a silent omission. The columns this
    acceptance criterion calls RETAIN must actually be RETAIN.
    """
    retained_free_text = {
        ("core.SupportTicket", "text"),
        ("moderation.ModeratorActionLog", "reason"),
        ("search.SavedSearch", "query"),
    }
    all_free_text = retained_free_text | {
        ("ads.Ad", "title"),
        ("ads.Ad", "title_en"),
        ("ads.Ad", "title_bs"),
        ("ads.Ad", "description"),
        ("ads.Ad", "description_en"),
        ("ads.Ad", "description_bs"),
    }
    lookup = _entry_lookup()

    for key in all_free_text:
        entry = lookup.get(key)
        assert entry is not None, f"{key} must be a declared entry"
        _label, _column, _action, reason = entry
        assert "BLOCK" in reason, (
            f"{key} reason must name its owning block"
        )

    for key in retained_free_text:
        entry = lookup.get(key)
        assert entry is not None, f"{key} must be a declared entry"
        _label, _column, action, _reason = entry
        assert action == ErasureAction.RETAIN, f"{key} must be RETAIN"


def test_declared_entries_are_unique() -> None:
    """No duplicate ``(model_label, column)`` in the declaration."""
    keys = [(model_label, column) for model_label, column, _a, _r in PII_ERASURE_ENTRIES]
    assert len(keys) == len(set(keys)), f"duplicate declared entries: {keys}"


def test_no_entry_names_ad_rejected_reason() -> None:
    """``Ad.rejected_reason`` is not a column; the moderation text is a log reason.

    ``apps/ads/admin.py::rejected_reason`` is only a display helper that reads
    ``ModeratorActionLog.reason``. An entry naming ``Ad.rejected_reason`` would
    describe a column that does not exist.
    """
    for model_label, column, _action, _reason in PII_ERASURE_ENTRIES:
        assert not (model_label == "ads.Ad" and column == "rejected_reason"), (
            "Ad has no rejected_reason column; the moderation free text is "
            "ModeratorActionLog.reason"
        )
