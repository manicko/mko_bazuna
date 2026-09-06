"""
Tests for Spec 18 Block E — SiteConfig admin configuration (Outcome 3).

Covers:
- bot_username appears in SiteConfigAdmin.list_display
- bot_username field has a RegexValidator
- bot_username field max_length is 32
- bot_username field has help_text mentioning "without @ prefix"

All checks are pure metadata introspection — no database access required.
"""

from __future__ import annotations

import pytest
from apps.core.models import SiteConfig
from django.core.validators import RegexValidator

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# SiteConfigAdmin.list_display
# ---------------------------------------------------------------------------


def test_bot_username_in_list_display() -> None:
    """``bot_username`` is present in ``SiteConfigAdmin.list_display``."""
    from apps.core.admin import SiteConfigAdmin

    assert "bot_username" in SiteConfigAdmin.list_display


# ---------------------------------------------------------------------------
# SiteConfig.bot_username field definition
# ---------------------------------------------------------------------------


def test_bot_username_field_has_regex_validator() -> None:
    """The ``bot_username`` field has a ``RegexValidator`` in its validators."""
    field = SiteConfig._meta.get_field("bot_username")
    assert any(isinstance(v, RegexValidator) for v in field.validators)


def test_bot_username_field_max_length() -> None:
    """The ``bot_username`` field ``max_length`` is 32."""
    field = SiteConfig._meta.get_field("bot_username")
    assert field.max_length == 32


def test_bot_username_field_has_help_text() -> None:
    """The ``bot_username`` field ``help_text`` mentions "without @ prefix"."""
    field = SiteConfig._meta.get_field("bot_username")
    assert "without @ prefix" in str(field.help_text)
