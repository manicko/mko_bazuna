"""
Sanitization utilities for safe logging.

Removes control characters and truncates user-supplied strings before
they reach log output, preventing log injection and PII leaks.
"""

import hashlib
import hmac
import json
import logging
import re
import secrets
from typing import TYPE_CHECKING, Final

from django.conf import settings

if TYPE_CHECKING:
    from pydantic import ValidationError

logger = logging.getLogger(__name__)


# Max characters retained for a logged query string.
_MAX_QUERY_LENGTH: Final[int] = 100

# Non-printable control characters (including newlines, tabs, etc.)
# are stripped to prevent log-line injection.
_CONTROL_CHAR_PATTERN: Final[re.Pattern[str]] = re.compile(r"[\x00-\x1f\x7f-\x9f]")

# Redaction of persisted search queries (SRH-004).
#
# Masking-set decision (Path A, conservative): phones and emails are
# high-confidence PII and always masked. Personal names are masked only when
# they appear as two or more consecutive capitalized words (a first+last name
# pattern such as "Ivan Petrov" / "Иван Петров"). Single capitalized words are
# intentionally left intact so legitimate city/brand search terms (e.g.
# "Sarajevo", "Bosna", "Сараево") are not damaged by over-matching.
#
# Letters considered for name detection: Latin + Cyrillic.
_NAME_LETTERS: Final[str] = r"A-Za-zА-Яа-яЁё"

# Uppercase letters (Latin + Cyrillic) used as the first char of a name word.
_UPPER_LETTERS: Final[str] = r"A-ZА-ЯЁ"

# Phone numbers: optional leading '+', 7-15 digits with optional separators.
_PHONE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<!\d)(?:\+?\d[\d\s().\-]{5,}\d|\+?\d{7,15})(?!\d)"
)

# Email addresses: local-part@domain.tld
_EMAIL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
)

# Conservative name pattern: two or more consecutive capitalized words.
_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf"\b[{_UPPER_LETTERS}][{_NAME_LETTERS}]*(?:\s+[{_UPPER_LETTERS}][{_NAME_LETTERS}]*)+"
)


def _mask_phone(match: re.Match[str]) -> str:
    """Mask a phone number, keeping only the leading '+' and first digit."""
    phone = match.group(0)
    offset = 1 if phone.startswith("+") else 0
    return phone[: offset + 1] + "*" * (len(phone) - offset - 1)


def _mask_email(match: re.Match[str]) -> str:
    """Mask the local part of an email, keeping the '@domain' suffix.

    Length-preserving (never lengthens): the local part is replaced by its
    first two characters plus asterisks filling the remaining length. A longer
    fixed ``***`` suffix is not used because it would lengthen short local
    parts and break the never-lengthen invariant that keeps the
    ``max_length=200`` column caps safe.
    """
    email = match.group(0)
    local, sep, domain = email.partition("@")
    if len(local) <= 2:
        masked_local = local
    else:
        masked_local = local[:2] + "*" * (len(local) - 2)
    return f"{masked_local}{sep}{domain}"


def _mask_name(match: re.Match[str]) -> str:
    """Mask a multi-word name, keeping only the first letter of each word."""
    words = match.group(0).split()
    return " ".join(f"{w[0]}{'*' * (len(w) - 1)}" for w in words)


def redact_search_query(query: str) -> str:
    """Redact PII from a search query before it is persisted.

    Masks phone numbers, email addresses and multi-word personal names, then
    truncates to ``_MAX_QUERY_LENGTH``. Redaction never lengthens the string,
    so the ``PopularSearch``/``SearchHistory`` ``max_length=200`` column caps
    remain safe.

    Args:
        query: The raw search query string.

    Returns:
        The redacted (and truncated) query string.
    """
    if not query:
        return query
    redacted = _EMAIL_PATTERN.sub(_mask_email, query)
    redacted = _PHONE_PATTERN.sub(_mask_phone, redacted)
    redacted = _NAME_PATTERN.sub(_mask_name, redacted)
    return redacted[:_MAX_QUERY_LENGTH]


def redact_free_text(text: str) -> str:
    """Redact PII from staff-authored free text before it is persisted.

    Masks phone numbers, e-mail addresses and multi-word personal names using
    the same patterns and masks as ``redact_search_query``, but unlike that
    helper it does NOT truncate: the caller is storing moderator prose in an
    unbounded ``TextField``, where a 100-character cap would silently discard
    the operator's own words.

    Two measured properties this contract depends on:

    * It never lengthens its input, so an unbounded column cannot overflow and a
      render-time truncation cannot grow.
    * It is idempotent. Each mask leaves a run of ``*``; ``*`` is in none of the
      three character classes and cannot form a match, so a second pass is a
      no-op and a placeholder is never corrupted by double redaction.

    Args:
        text: The raw staff-authored text.

    Returns:
        The redacted text, untruncated.
    """
    if not text:
        return text
    redacted = _EMAIL_PATTERN.sub(_mask_email, text)
    redacted = _PHONE_PATTERN.sub(_mask_phone, redacted)
    return _NAME_PATTERN.sub(_mask_name, redacted)


def search_query_key(query: str) -> str:
    """Derive the persisted dedup key for a search query.

    Redaction runs FIRST, on the raw query, then strip and lower. The order is
    load-bearing: ``redact_search_query`` matches personal names on
    ``\\b[А-ЯЁA-Z]``, which matches nothing in an already-lowercased string, so
    lower-then-redact would leave every name in the key. The result keeps the
    prefix structure ``get_popular_suggestions`` reads with
    ``query_normalized__startswith``, and never lengthens the input.

    Args:
        query: The raw search query string.

    Returns:
        The dedup key: the redacted query, stripped and lowercased.
    """
    return redact_search_query(query).strip().lower()


def sanitize_query_for_log(query: str | None) -> str:
    """
    Sanitize a user-supplied query string for safe logging.

    Strips control characters and truncates to ``_MAX_QUERY_LENGTH``.

    Args:
        query: The raw user-supplied query string, or ``None``.

    Returns:
        A sanitised string safe for inclusion in log records.
    """
    if not query:
        return ""

    cleaned = _CONTROL_CHAR_PATTERN.sub("", query)
    return cleaned[:_MAX_QUERY_LENGTH]


def strip_control_chars(query: str | None) -> str:
    """Remove control characters from a user query WITHOUT truncating.

    A NUL byte (``0x00``) in a search query reaches psycopg unencoded and
    raises ``DataError`` — PostgreSQL text values cannot contain NUL — so the
    value must be cleaned before it reaches any parameterised sink
    (08-SRCH-006). Unlike :func:`sanitize_query_for_log` this helper performs
    **no truncation**: the view/column contract is 200 characters while the
    log sanitiser caps at 100, and reusing the sanitiser wholesale would
    silently shorten ``q`` (the Product Owner's 2026-10-03 constraint on Q4).

    Args:
        query: The raw user-supplied query string, or ``None``.

    Returns:
        The query with every character in ``_CONTROL_CHAR_PATTERN`` removed,
        untruncated. Empty input returns an empty string.
    """
    if not query:
        return ""
    return _CONTROL_CHAR_PATTERN.sub("", query)


def sanitize_autocomplete_query(query: str) -> str:
    """Sanitize autocomplete query — control chars stripped, then 2–100 chars.

    Control characters are stripped **before** the length window so the guard
    measures the value that is actually searched (08-SRCH-006). The documented
    contract order is strip-then-measure; ``[;'"\\]`` removal and the
    empty-string return on a window miss are unchanged.
    """
    cleaned = strip_control_chars(query)
    if len(cleaned) < 2 or len(cleaned) > 100:
        return ""
    return re.sub(r"[;'\"\\]", "", cleaned.strip())


# Whether the empty-key warning has already been emitted for this process, so a
# developer is told once rather than once per masked value.
_log_mask_key_warning_emitted: bool = False

# The per-process random fallback key, materialised at most once. It must be
# stable across calls within a process or same-input-same-output correlation
# within that process would break; it is deliberately NOT configurable.
_log_mask_key_fallback: bytes | None = None


def _resolve_log_mask_key() -> bytes:
    """Return the HMAC key used to pseudonymise Telegram IDs.

    Production is guarded in ``config/settings/prod.py``, so
    ``settings.LOG_MASK_KEY`` is always a real, non-placeholder key there.

    Outside production the setting defaults to the empty string. Falling back
    to the old unkeyed digest would reintroduce exactly the enumeration defect
    this module exists to remove, so an empty key is instead replaced by a
    per-process random value. Correlation across processes is deliberately
    unavailable in that case — the mask is still unverifiable and never leaks
    the raw ID — and a single warning is emitted so a developer is not misled
    into believing non-production logs are correlatable.
    """
    global _log_mask_key_fallback, _log_mask_key_warning_emitted

    key = settings.LOG_MASK_KEY
    if key:
        return key.encode()
    if _log_mask_key_fallback is None:
        _log_mask_key_fallback = secrets.token_bytes(32)
    if not _log_mask_key_warning_emitted:
        _log_mask_key_warning_emitted = True
        logger.warning(
            "LOG_MASK_KEY is unset: mask_telegram_id is using a per-process random "
            "key. Masked values are not correlatable across processes and change on "
            "every restart. Set LOG_MASK_KEY to a shared value for correlatable logs."
        )
    return _log_mask_key_fallback


def mask_telegram_id(telegram_id: int | None) -> str:
    """Mask a Telegram user ID for safe logging.

    Keyed HMAC-SHA-256 over ``str(telegram_id)``, truncated to the first 12 hex
    characters, with a ``tg_`` prefix. The KEY is what makes the value unusable
    to anyone who does not hold it: without ``LOG_MASK_KEY`` an attacker may
    enumerate candidate Telegram IDs but cannot confirm any of them. A retained
    key means the value is pseudonymised, never anonymised.

    CORRELATION IDENTIFIER, NEVER AN AUTHENTICATOR. 12 hex is 48 bits,
    deliberately below RFC 2104 section 5's 80-bit floor for a truncated HMAC,
    because this mask is never accepted as proof of anything: it is written
    into logs and never checked against anything. If a future change needs it to
    authenticate, 48 bits is insufficient and the width must be raised then.

    Rotating ``LOG_MASK_KEY`` changes every value: old and new log lines stop
    being correlatable. Rotation is on suspected compromise, never on a
    schedule; a scheduled rotation would cost permanent loss of correlation
    across the log history while shortening no exposure window.

    Args:
        telegram_id: The Telegram user ID to mask, or None.

    Returns:
        Masked string safe for log output. None -> "None".
    """
    if telegram_id is None:
        return "None"
    tid = str(telegram_id)
    key = _resolve_log_mask_key()
    digest = hmac.new(key, tid.encode(), hashlib.sha256).hexdigest()
    return f"tg_{digest[:12]}"


def pydantic_errors_json(exc: ValidationError) -> list[dict[str, object]]:
    """Return Pydantic v2 validation errors as a JSON-serializable, sanitized list.

    Delegates to pydantic-core's own serializer (exc.json), which correctly
    handles values stdlib json.dumps cannot — raw bytes in the ``input``
    field (for json_invalid errors on bytestring request bodies) and live
    objects in ``ctx`` (for value_error errors from custom validators).

    ``input``, ``ctx`` and ``url`` are excluded:
      - input: may contain the raw request body (bytes) — CWE-209 risk.
      - ctx: holds live exception objects (not JSON-serializable).
      - url: only leaks the Pydantic version (reconnaissance).

    Full diagnostic detail is expected to have been logged server-side
    by the caller before this function is invoked.

    Returns only {type, loc, msg} per error — all JSON-native.
    """
    return json.loads(
        exc.json(include_input=False, include_url=False, include_context=False)
    )
