"""
Data migration to derive ``query_normalized`` from the redacted query (06-PII-108).

Four writers previously derived the dedup key as ``query.strip().lower()`` from
the RAW query, so phone numbers, e-mail addresses and personal names that
``redact_search_query`` strips out of the ``query`` column survived verbatim in
``query_normalized`` — in ``SearchHistory`` (both the table and the anonymous
session store), in the global cross-user ``popular_searches`` table and in the
seeder. This migration re-derives ``query_normalized`` for both tables from
each row's own (already redacted by ``0002``) ``query`` column.

The derivation is exact because redaction is idempotent: re-deriving from the
stored, redacted ``query`` yields the same key the new write path computes.

The redaction logic is inlined here (rather than importing
``redact_search_query``) so the migration stays robust if the application module
changes in the future — mirroring ``0002_redact_search_queries``.

Merge, never duplicate: ``query_normalized`` is NOT unique, and
``increment_popular_search``'s ``get_or_create`` would raise
``MultipleObjectsReturned`` on duplicate keys. So:

* ``popular_searches`` is grouped by the new key, one row survives and its
  ``hit_count`` is the SUM of the group. The total hit count is preserved and
  the merged row stays above ``_MIN_HIT_COUNT = 10``, so autocomplete survives;
  only the split of hits between two collapsed variants is lost.
* ``search_history`` keeps only the NEWEST row per ``(user_id, new key)``.

Reverse is a no-op: the un-redacted originals are the PII being removed and are
intentionally not retained, mirroring ``0002_redact_search_queries``.
"""

import re
from collections import defaultdict

from django.db import migrations

# Letters considered for name detection: Latin + Cyrillic.
_NAME_LETTERS = r"A-Za-zА-Яа-яЁё"

# Uppercase letters (Latin + Cyrillic) used as the first char of a name word.
_UPPER_LETTERS = r"A-ZА-ЯЁ"

# Phone numbers: optional leading '+', 7-15 digits with optional separators.
_PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?\d[\d\s().\-]{5,}\d|\+?\d{7,15})(?!\d)")

# Email addresses: local-part@domain.tld
_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Conservative name pattern: two or more consecutive capitalized words.
_NAME_PATTERN = re.compile(
    rf"\b[{_UPPER_LETTERS}][{_NAME_LETTERS}]*(?:\s+[{_UPPER_LETTERS}][{_NAME_LETTERS}]*)+"
)

# Max characters retained for a persisted query.
_MAX_QUERY_LENGTH = 100


def _mask_phone(match):
    """Mask a phone number, keeping only the leading '+' and first digit."""
    phone = match.group(0)
    offset = 1 if phone.startswith("+") else 0
    return phone[: offset + 1] + "*" * (len(phone) - offset - 1)


def _mask_email(match):
    """Mask the local part of an email, keeping the '@domain' suffix.

    Length-preserving (never lengthens): the local part is replaced by its
    first two characters plus asterisks filling the remaining length.
    """
    email = match.group(0)
    local, sep, domain = email.partition("@")
    if len(local) <= 2:
        masked_local = local
    else:
        masked_local = local[:2] + "*" * (len(local) - 2)
    return f"{masked_local}{sep}{domain}"


def _mask_name(match):
    """Mask a multi-word name, keeping only the first letter of each word."""
    words = match.group(0).split()
    return " ".join(f"{w[0]}{'*' * (len(w) - 1)}" for w in words)


def _redact_query(query):
    """Minimal inline redaction mirroring ``redact_search_query``."""
    if not query:
        return query
    redacted = _EMAIL_PATTERN.sub(_mask_email, query)
    redacted = _PHONE_PATTERN.sub(_mask_phone, redacted)
    redacted = _NAME_PATTERN.sub(_mask_name, redacted)
    return redacted[:_MAX_QUERY_LENGTH]


def _query_key(query):
    """Redact first (on the raw query), then strip and lower."""
    return _redact_query(query).strip().lower()


def redact_query_keys(apps, schema_editor):
    """Re-derive ``query_normalized`` for both tables, merging collisions."""
    PopularSearch = apps.get_model("search", "PopularSearch")
    SearchHistory = apps.get_model("search", "SearchHistory")

    # PopularSearch: group by the new key, keep one row, SUM the hit counts.
    grouped: dict[str, list] = defaultdict(list)
    for pk, query, hit_count in PopularSearch.objects.values_list(
        "pk", "query", "hit_count"
    ):
        grouped[_query_key(query)].append((pk, hit_count))

    for key, rows in grouped.items():
        survivor_pk = rows[0][0]
        total_hits = sum(hit_count for _, hit_count in rows)
        PopularSearch.objects.filter(pk=survivor_pk).update(
            query_normalized=key, hit_count=total_hits
        )
        duplicate_pks = [pk for pk, _ in rows[1:]]
        if duplicate_pks:
            PopularSearch.objects.filter(pk__in=duplicate_pks).delete()

    # SearchHistory: keep only the newest row per (user_id, new key).
    newest: dict[tuple[int | None, str], tuple[int, object]] = {}
    for pk, user_id, query, created_at in SearchHistory.objects.values_list(
        "pk", "user_id", "query", "created_at"
    ):
        key = _query_key(query)
        current = newest.get((user_id, key))
        if current is None or created_at > current[1]:
            newest[(user_id, key)] = (pk, created_at)

    keep_pks = {pk for pk, _ in newest.values()}
    SearchHistory.objects.exclude(pk__in=keep_pks).delete()
    for (_user_id, key), (pk, _) in newest.items():
        SearchHistory.objects.filter(pk=pk).update(query_normalized=key)


class Migration(migrations.Migration):
    dependencies = [
        ("search", "0004_backfill_delivered_at"),
    ]

    operations = [
        migrations.RunPython(
            redact_query_keys,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
