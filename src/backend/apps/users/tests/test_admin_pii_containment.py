"""
PII containment regression tests for staff admin list_display.

Guards PII-001 / VAL-001: no admin list_display helper may render the raw
external ``telegram_id`` identifier. All four affected helpers must instead
render a non-identifying value (``str(obj.user)`` = "User <pk>" for the
User-FK helpers; ``mask_telegram_id(...)`` for the standalone LoginToken).
"""

from __future__ import annotations

import inspect

import pytest

from apps.users.admin import LoginTokenAdmin

pytestmark = [pytest.mark.unit]


def _assert_no_raw_telegram_id(source: str) -> None:
    """Assert ``source`` does not render the raw telegram_id identifier.

    The assertion targets the rendering statement ``str(obj.user.telegram_id)``
    (the PII-001 leak) rather than the bare token, because the helper docstrings
    legitimately reference ``telegram_id`` in prose and are intentionally kept.
    """
    assert "str(obj.user.telegram_id)" not in source, (
        "admin list_display helper must not render the raw telegram_id (PII-001)"
    )


def test_ads_user_link_hides_telegram_id() -> None:
    """``ads.admin.user_link`` renders a non-identifying value."""
    from apps.ads.admin import user_link

    _assert_no_raw_telegram_id(inspect.getsource(user_link))
    assert user_link.short_description == "User ID"


def test_analytics_user_link_hides_telegram_id() -> None:
    """``AnalyticsEventAdmin.user_link`` renders a non-identifying value."""
    from apps.analytics.admin import AnalyticsEventAdmin

    _assert_no_raw_telegram_id(inspect.getsource(AnalyticsEventAdmin.user_link))
    assert AnalyticsEventAdmin.user_link.short_description == "User ID"


def test_moderation_log_user_link_hides_telegram_id() -> None:
    """``moderation.admin.log_user_link`` renders a non-identifying value."""
    from apps.moderation.admin import log_user_link

    _assert_no_raw_telegram_id(inspect.getsource(log_user_link))
    assert log_user_link.short_description == "User ID"


def test_login_token_list_display_masks_telegram_id() -> None:
    """``LoginTokenAdmin.list_display`` uses the masked display, not the raw field."""
    assert "telegram_id" not in LoginTokenAdmin.list_display
    assert "telegram_id_display" in LoginTokenAdmin.list_display
    # The display method delegates to mask_telegram_id (VAL-001)
    source = inspect.getsource(LoginTokenAdmin.telegram_id_display)
    assert "mask_telegram_id" in source
    assert "obj.telegram_id" in source
