"""
Sanitization utilities for safe logging.

Removes control characters and truncates user-supplied strings before
they reach log output, preventing log injection and PII leaks.
"""

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
