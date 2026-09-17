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
