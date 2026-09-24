"""
Sanitization utilities for safe logging.

Removes control characters and truncates user-supplied strings before
they reach log output, preventing log injection and PII leaks.
"""

import hashlib
import json
import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pydantic import ValidationError


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


def sanitize_autocomplete_query(query: str) -> str:
    """Sanitize autocomplete query — 2–100 chars, SQL injection safe."""
    if not query or len(query) < 2 or len(query) > 100:
        return ""
    return re.sub(r"[;'\"\\]", "", query.strip())


def mask_telegram_id(telegram_id: int | None) -> str:
    """Mask a Telegram user ID for safe logging.

    Non-reversible SHA-256 hash (first 8 hex chars) with 'tg_' prefix.
    Same input always produces the same output, enabling log correlation
    without exposing the raw PII.

    Args:
        telegram_id: The Telegram user ID to mask, or None.

    Returns:
        Masked string safe for log output. None -> "None".
    """
    if telegram_id is None:
        return "None"
    tid = str(telegram_id)
    return f"tg_{hashlib.sha256(tid.encode()).hexdigest()[:8]}"


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
