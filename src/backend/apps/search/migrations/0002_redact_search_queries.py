"""
Data migration to redact PII from persisted search queries (SRH-004).

Raw search queries were previously stored verbatim in ``PopularSearch.query``
and ``SearchHistory.query``, persisting phone numbers, email addresses and
personal names (a GDPR data-minimization violation). This migration rewrites
``query`` in place with its redacted form.

``query_normalized`` is the lookup/dedup key (NOT ``query``), so redacting
``query`` does not affect matching, deduplication or autocomplete suggestions
and no table rebuild is needed.

The redaction logic is inlined here (rather than importing
``redact_search_query``) so the migration stays robust if the application
module changes in the future.

Reverse is a no-op: the original unredacted values are the PII being removed
and are intentionally not retained; ``query_normalized`` (the meaningful key)
is preserved intact.
"""

import re

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


def redact_queries(apps, schema_editor):
    """Rewrite ``query`` in place with its redacted form for both models."""
    for model_name in ("PopularSearch", "SearchHistory"):
        Model = apps.get_model("search", model_name)
        for pk, query in Model.objects.values_list("pk", "query"):
            redacted = _redact_query(query)
            if redacted != query:
                Model.objects.filter(pk=pk).update(query=redacted)


class Migration(migrations.Migration):
    dependencies = [
        ("search", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            redact_queries,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
