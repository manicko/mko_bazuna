"""
Sanitization utilities for safe logging.

Removes control characters and truncates user-supplied strings before
they reach log output, preventing log injection and PII leaks.
"""

import hashlib
import re
from typing import Final

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
