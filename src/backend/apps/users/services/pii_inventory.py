"""Declarative PII erasure inventory and its completeness guard.

This module **declares** the PII erasure contract for the models in scope; it
does **not enforce** it. Production erasure still happens in
``apps.users.services.deletion`` (and, in later blocks, in the ads and trust
apps). Nothing in phase 06 imports this module to drive a mutation — BLOCK 9,
BLOCK 13 and BLOCK 11 are the consumers, and they read the declaration rather
than replace it.

The guard in ``tests/test_pii_inventory.py`` is a **tripwire on declared
columns, not a classifier**. It does not try to decide whether a column is
personally identifiable; there is no reliable way to do that mechanically.
Instead, each listed model gets a complete review surface: every concrete,
non-relational, non-timestamp column must either appear in
``PII_ERASURE_ENTRIES`` or be explicitly ruled out in
``REVIEWED_NON_IDENTITY_COLUMNS``. Adding a new data column to a listed model
therefore turns the tripwire red until a human records a decision — either an
erasure entry or a reviewed exclusion.

Look-alike columns are deliberately excluded from the erasure contract because
they are *not* identity material on this product:

- ``User.source`` — record provenance (``null`` = real user, ``'seed'`` =
  seed-generated), not an identity attribute.
- ``User.last_login`` — a timestamp the guard skips as non-data.
- ``User.date_joined`` — a timestamp the guard skips as non-data.
- ``core.SupportContact.telegram_id`` — a **support channel's** public
  destination (a bot/channel id), never a subject's identity; it is not the
  ``SupportTicket.telegram_id`` denormalised copy that 06-PII-101 concerns.

Promotion path to a real registry: the consuming block (BLOCK 9 first) may
write a single accessor function over the *same* tuples — resolving each
model label through ``django.apps.apps.get_model`` **at call time** so the
lazy-string import boundary below is preserved — and use it to drive erasure.
No such accessor is written here; writing one speculatively would be the
registry-with-consumers that Q-D9 explicitly rejected (project rule 5).

Import boundary: this module imports **stdlib only**. Model labels are lazy
strings resolved by the caller/test, so no ``apps.*`` model is imported and no
``users -> core.models`` / ``ads`` / ``trust`` / ``moderation`` import edge is
created. In particular ``core.SupportTicket`` and ``core.SupportContact`` live
in ``src/backend/apps/core/models.py`` (``src/backend/apps/support/`` does not
exist), and the label is written ``core.SupportTicket``.
"""

from __future__ import annotations

from enum import StrEnum


class ErasureAction(StrEnum):
    """The action an erasure path takes on one declared column."""

    CLEAR = "clear"
    NULL = "null"
    DELETE_ROW = "delete_row"
    RETAIN = "retain"
    DROP_COLUMN = "drop_column"


#: Declarative erasure contract: ``(model_label, column, action, reason)``.
#:
#: ``model_label`` is a lazy ``"app.Model"`` string; the reason must say whether
#: the action is implemented today, so an unimplemented action is visible rather
#: than silently absent. ``DROP_COLUMN`` exists because the real fix for
#: 06-PII-111 is a ``RemoveField`` migration — declaring ``NULL`` or ``RETAIN``
#: for that permanently-NULL column would be fiction.
PII_ERASURE_ENTRIES: tuple[tuple[str, str, ErasureAction, str], ...] = (
    (
        "users.User",
        "telegram_id",
        ErasureAction.NULL,
        "Implemented today: nulled by withdraw_consent inside its existing "
        "transaction.atomic(); breaks chat linkage so no re-link is possible. "
        "Declared so the column can never fall out of the erasure contract "
        "again (06-PII-110).",
    ),
    (
        "users.User",
        "username",
        ErasureAction.NULL,
        "Implemented today: the public Telegram handle, nulled together with "
        "telegram_id. Re-identifying, never in scope on DECLINE (06-PII-110).",
    ),
    (
        "users.User",
        "first_name",
        ErasureAction.CLEAR,
        "Implemented today: emptied to the empty string — the column is NOT "
        "NULL, so the action is CLEAR, not NULL (06-PII-110).",
    ),
    (
        "users.User",
        "last_name",
        ErasureAction.CLEAR,
        "Implemented today: emptied to the empty string — NOT NULL, so CLEAR, "
        "not NULL (06-PII-110).",
    ),
    (
        "users.User",
        "email",
        ErasureAction.CLEAR,
        "Implemented today: emptied to the empty string — NOT NULL, so CLEAR, "
        "not NULL (06-PII-110).",
    ),
    (
        "users.User",
        "password",
        ErasureAction.CLEAR,
        "NOT implemented today: identity-bearing credential hash. "
        "withdraw_consent does NOT touch it today and NO block in phase 06 "
        "implements the clear — the declaration is honest about that so the "
        "omission is visible rather than invisible (06-NEW-03).",
    ),
    (
        "users.User",
        "chat_id",
        ErasureAction.RETAIN,
        "Implemented today (retention): retained deliberately and permanently. "
        "telegram_bot/middlewares/permissions.py::AccountStateMiddleware._resolve_user "
        'resolves the acting user on chat_id precisely so withdrawn/deleted '
        "users — whose telegram_id is nulled — are still found and stay "
        'blocked; User.chat_id.help_text reads "never nullified". Nulling '
        "chat_id is forbidden.",
    ),
    (
        "users.User",
        "preferred_city",
        ErasureAction.NULL,
        "Implemented today: cleared to NULL by decline_consent and by "
        "withdraw_consent inside its existing transaction.atomic(). The clear "
        "is durable because all four restore paths are closed: the decline "
        "response expires the preferred_city cookie with a hand-rolled secure "
        "Set-Cookie (delete_cookie cannot clear a Secure cookie over HTTPS), "
        "set_preferred_city gates its DB write on not is_declined, and the "
        "login reconcile returns early for a declined user. Re-acceptance via "
        "give_consent clears is_declined and is a new consent (06-PII-110).",
    ),
    (
        "users.ConsentRecord",
        "session_key",
        ErasureAction.RETAIN,
        "NOT implemented today: a live Django session identifier with no "
        "retention boundary. The ConsentRecord half of 06-PII-110 was absorbed "
        "into 06-PII-116; BLOCK 15 owns the TTL decision (Q-D4) and the sweep. "
        "Declared so the deferral is visible.",
    ),
    (
        "users.ConsentRecord",
        "user_agent",
        ErasureAction.RETAIN,
        "NOT implemented today: browser-fingerprint-grade text, same table and "
        "retention class as session_key. BLOCK 15's sweep (06-PII-116) owns its "
        "boundary (Q-D4).",
    ),
    (
        "users.ConsentRecord",
        "ip_address",
        ErasureAction.RETAIN,
        "NOT implemented today: declared by BLOCK 3, not by any finding — same "
        "table and retention class as session_key/user_agent, and an undeclared "
        "sibling in a table BLOCK 15 will sweep is exactly the omission this "
        "block exists to prevent. BLOCK 15 (06-PII-116) owns its boundary "
        "(Q-D4).",
    ),
    (
        "users.LoginToken",
        "telegram_id",
        ErasureAction.DELETE_ROW,
        "Implemented today: active login tokens are deleted BEFORE telegram_id "
        "is nulled, so a still-valid token cannot re-link a withdrawn identity. "
        "The whole row goes, including token_hash and browser_binding. Declared "
        "to make the one already-implemented row erasure visible.",
    ),
    (
        "core.SupportTicket",
        "chat_id",
        ErasureAction.DELETE_ROW,
        "Implemented today (BLOCK 13, 06-PII-101): the whole ticket row is "
        "DELETED, not scrubbed. withdraw_consent deletes the user's tickets "
        "inside its existing transaction.atomic(), the FK CASCADE removes them "
        "on a hard user delete, and consent_hard_delete sweeps them before its "
        "queryset.delete(). The row is deleted, so this denormalised Telegram "
        "chat id leaves with it.",
    ),
    (
        "core.SupportTicket",
        "telegram_id",
        ErasureAction.DELETE_ROW,
        "Implemented today (BLOCK 13, 06-PII-101): the denormalised Telegram "
        "id leaves with the whole ticket row on withdrawal's explicit delete, on "
        "the hard delete's CASCADE, and on the sweep. Nothing is derived from a "
        "ticket, so the row is deleted rather than scrubbed.",
    ),
    (
        "core.SupportTicket",
        "username",
        ErasureAction.DELETE_ROW,
        "Implemented today (BLOCK 13, 06-PII-101): the public handle leaves "
        "with the whole ticket row on withdrawal, on the hard delete's CASCADE, "
        "and on the consent_hard_delete sweep. The row is deleted, not scrubbed.",
    ),
    (
        "core.SupportTicket",
        "text",
        ErasureAction.DELETE_ROW,
        "Implemented today (BLOCK 13, 06-PII-101): the ticket body is deleted "
        "with the row. Nothing is derived from a ticket — no trigger, index, "
        "aggregate, AnalyticsEvent type, stamp or signal receiver — so erasing "
        "the whole row is conservation-correct. The bot also refuses to create a "
        "ticket without storage consent.",
    ),
    (
        "ads.Ad",
        "title",
        ErasureAction.CLEAR,
        "NOT implemented today: user-authored free text, surviving the 30-day "
        "window byte-for-byte and listed and full-text searchable by any staff "
        "account. BLOCK 11 (06-PII-109) owns the scrub or the spec correction; "
        "the scope choice is the product's (Q-D3). DECLARATION-ONLY.",
    ),
    (
        "ads.Ad",
        "title_en",
        ErasureAction.CLEAR,
        "NOT implemented today: per-language variant of Ad.title; same owner "
        "and deferral (BLOCK 11, 06-PII-109, Q-D3). DECLARATION-ONLY.",
    ),
    (
        "ads.Ad",
        "title_bs",
        ErasureAction.CLEAR,
        "NOT implemented today: per-language variant of Ad.title; same owner "
        "and deferral (BLOCK 11, 06-PII-109, Q-D3). DECLARATION-ONLY.",
    ),
    (
        "ads.Ad",
        "description",
        ErasureAction.CLEAR,
        "NOT implemented today: on a classifieds board the description is the "
        'most likely place for a seller to have typed a name, a phone number '
        'or a "call me at" line. BLOCK 11 (06-PII-109) owns the scrub; Q-D3 '
        "decides scrub versus spec correction. DECLARATION-ONLY.",
    ),
    (
        "ads.Ad",
        "description_en",
        ErasureAction.CLEAR,
        "NOT implemented today: per-language variant of Ad.description; same "
        "owner and deferral (BLOCK 11, 06-PII-109, Q-D3). DECLARATION-ONLY.",
    ),
    (
        "ads.Ad",
        "description_bs",
        ErasureAction.CLEAR,
        "NOT implemented today: per-language variant of Ad.description; same "
        "owner and deferral (BLOCK 11, 06-PII-109, Q-D3). DECLARATION-ONLY.",
    ),
    (
        "moderation.ModeratorActionLog",
        "reason",
        ErasureAction.RETAIN,
        "NOT implemented today (retention): staff-authored free text, "
        "unbounded, on a row that deliberately survives user erasure with "
        "user_id = NULL; a moderator quoting a seller's message persists the "
        "subject's data indefinitely. BLOCK 16 (06-PII-114) redacts at WRITE "
        "TIME, which is not an erasure action — adding a write-time rule to "
        "this inventory would be a category error.",
    ),
    (
        "search.SavedSearch",
        "query",
        ErasureAction.RETAIN,
        "NOT implemented today (retention): the FTS query string, stored in the "
        "user's language and matched against the per-language search vector — "
        "it cannot be redacted. BLOCK 14's redaction concerns "
        "SearchHistory.query_normalized, a different column in a different "
        "model. BLOCK 9 (06-PII-110) deactivates the row on withdrawal rather "
        "than editing the query.",
    ),
)


#: Per-model review surface of concrete, non-relational, non-timestamp columns
#: that are deliberately NOT in the erasure contract.
#:
#: Generated mechanically from ``Model._meta`` in a one-off introspection run
#: (never hand-typed), so the guard can prove every such column on a listed
#: model was reviewed: a column is either declared in ``PII_ERASURE_ENTRIES``
#: or listed here. Relational fields, the implicit ``id`` primary key and
#: timestamp columns are excluded by the guard's own field filter and are not
#: recorded here.
REVIEWED_NON_IDENTITY_COLUMNS: dict[str, frozenset[str]] = {
    "users.User": frozenset(
        {
            "is_superuser",
            "is_staff",
            "is_active",
            "is_banned",
            "is_deleted",
            "is_declined",
            "ads_auto_publish",
            "telegram_premium",
            "telegram_language",
            "source",
            "last_login",
            "date_joined",
        }
    ),
    "users.ConsentRecord": frozenset(
        {
            "consent_version",
            "choice",
            "categories",
        }
    ),
    "users.LoginToken": frozenset(
        {
            "token_hash",
            "browser_binding",
        }
    ),
    "core.SupportTicket": frozenset(
        {
            "status",
            "ticket_ref",
        }
    ),
    "ads.Ad": frozenset(
        {
            "original_language",
            "price_amount",
            "price_currency",
            "price_normalized_eur",
            "category_name",
            "status",
            "source",
            "search_vector",
            "search_vector_ru",
            "search_vector_bs",
            "search_vector_en",
        }
    ),
    "trust.SellerVerification": frozenset(
        {
            "verified_by_admin",
        }
    ),
    "moderation.ModeratorActionLog": frozenset(
        {
            "action_type",
        }
    ),
    "search.SavedSearch": frozenset(
        {
            "min_price",
            "max_price",
            "is_active",
            "language",
            "unsubscribe_token",
        }
    ),
}
