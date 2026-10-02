"""Completeness guard for the declarative PII erasure inventory.

These are unit tests: the guard resolves model metadata and reads the
declaration, and needs no database. That is also how the "importable without a
database connection" constraint is proven — the declaration is asserted to
open no connection when touched. The tripwire is on *declared* columns, not a
classifier: it cannot decide whether a column is personally identifiable, only
that every data column on a listed model was reviewed.
"""

from __future__ import annotations

import pytest
from django.apps import apps
from django.db import connection

from apps.users.services.pii_inventory import (
    PII_ERASURE_ENTRIES,
    REVIEWED_NON_IDENTITY_COLUMNS,
    ErasureAction,
)

pytestmark = [pytest.mark.unit]

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
    """The declaration is importable and readable without a DB connection.

    With no test database fixture active, Django's default connection is still
    closed (``connection.connection is None``). Reading the declaration must
    not resolve a model or execute a query, so it stays closed.
    """
    _ = (PII_ERASURE_ENTRIES[0][0], REVIEWED_NON_IDENTITY_COLUMNS)
    assert connection.connection is None


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
