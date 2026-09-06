"""
Tests for Spec 18 Block E — login_issue.html source-level assertions
(Outcome 1b).

Verifies that the login token template does NOT leak the bot username
through cleartext template variables, and that it uses the
``{% telegram_deep_link %}`` tag for the deep-link anchor.

These are pure file-level assertions — no database access required.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings

pytestmark = [pytest.mark.unit]

# Path to the login_issue.html template source (mirrors test_rtl_obfuscation.py
# and test_footer_contact_link.py patterns).
_LOGIN_ISSUE_PATH: Path = (
    Path(settings.TEMPLATES[0]["DIRS"][0]) / "users" / "login_issue.html"
)


# ---------------------------------------------------------------------------
# login_issue.html source-level checks
# ---------------------------------------------------------------------------


def test_login_issue_template_no_cleartext_bot_username() -> None:
    """``login_issue.html`` must not reference cleartext bot username variables.

    The bot username is delivered exclusively through the ``telegram_deep_link``
    tag (which base64-encodes it in ``data-bot-encoded``). No ``{{ bot_username }}``,
    ``{{ deep_link }}``, or ``{{ settings.BOT_USERNAME }}`` may appear in the
    raw template source.
    """
    source = _LOGIN_ISSUE_PATH.read_text(encoding="utf-8")
    assert "{{ bot_username }}" not in source
    assert "{{ deep_link }}" not in source
    assert "settings.BOT_USERNAME" not in source


def test_login_issue_template_uses_telegram_deep_link() -> None:
    """``login_issue.html`` uses the ``{% telegram_deep_link %}`` tag for the link."""
    source = _LOGIN_ISSUE_PATH.read_text(encoding="utf-8")
    assert "{% telegram_deep_link" in source
