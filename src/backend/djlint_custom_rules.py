"""Custom djlint rule module for detecting multi-line Django comment tags.

Djlint's built-in H017 rule was reassigned to "void tags should be self closing"
in v1.44.x; the multi-line {# ... #} comment detection rule no longer exists.
Additionally, djlint treats all {# ... #} comments as "ignored inline blocks" and
skips pattern-based matches inside them. This Python module rule bypasses that
check by returning errors directly via the run() interface.

The rule H901 detects {# ... #} comment tags where the opening {# and closing
#} appear on different source lines — a silent Django template bug that renders
literal {# text into the HTML output.

This module is auto-loaded by djlint via .djlint_rules.yaml (python_module key).
"""

from __future__ import annotations

import re
from typing import Any

from djlint.lint import get_line
from djlint.settings import Config

# Match Django inline comment tags {# ... #}. Non-greedy with DOTALL so that
# multiple single-line comments on different lines are matched individually,
# not merged into one large match.
_INLINE_COMMENT_RE: re.Pattern[str] = re.compile(r"{#.*?#\}", re.DOTALL)


def run(
    rule: dict[str, Any],
    config: Config,
    html: str,
    filepath: str,
    line_ends: list[dict[str, int]],
    *args: Any,
    **kwargs: Any,
) -> list[dict[str, str]]:
    """Report multi-line {# ... #} comment tags as H901 violations.

    Django's {# ... #} syntax is single-line only. When {# and #} are on
    different source lines, Django does not recognize the comment and renders
    the literal {# text into HTML.
    """
    errors: list[dict[str, str]] = []
    for match in _INLINE_COMMENT_RE.finditer(html):
        matched_text = match.group()
        if "\n" not in matched_text:
            continue
        errors.append(
            {
                "code": rule["name"],
                "line": get_line(match.start(), line_ends),
                "match": matched_text.strip()[:20],
                "message": rule["message"],
            }
        )
    return errors
