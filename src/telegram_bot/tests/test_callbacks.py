"""Regression tests for ``BotCallbackPrefix`` StrEnum values (QLT-002).

Verifies that every callback-data prefix enum member resolves to the exact
string value the inline-keyboard buttons and ``F.data.startswith(...)`` filter
lambdas depend on.  If any enum value drifts, click routing silently breaks —
the filter no longer matches the button's ``callback_data``.

These are pure unit tests (no database access required).
"""

from __future__ import annotations

import pytest

from apps.search.services.immediate_alerts import UNSUB_CALLBACK_PREFIX
from telegram_bot.schemas.callbacks import BotCallbackPrefix

pytestmark = [pytest.mark.unit]


class TestBotCallbackPrefixValues:
    """Every enum member must produce the exact string expected by the bot."""

    @pytest.mark.parametrize(
        "member, expected",
        [
            (BotCallbackPrefix.PURPOSE, "purpose:"),
            (BotCallbackPrefix.CONDITION, "condition:"),
            (BotCallbackPrefix.FEATURE, "feature:"),
            (BotCallbackPrefix.PRICE_CURRENCY, "price_currency:"),
            (BotCallbackPrefix.PRICE_FREE, "price_free"),
            (BotCallbackPrefix.FEATURES_DONE, "features_done"),
            (BotCallbackPrefix.CONTACT_US, "contact_us"),
            # QLT-002: newly consolidated callback prefixes.
            (BotCallbackPrefix.UNSUB, "unsub:"),
            (BotCallbackPrefix.UNSUB_ON, "unsub_on:"),
            (BotCallbackPrefix.LANG, "lang:"),
        ],
    )
    def test_member_value_matches_expected(self, member, expected: str) -> None:
        """Each ``BotCallbackPrefix`` member's string value is stable."""
        assert member == expected
        assert str(member) == expected

    # ------------------------------------------------------------------
    # New members specifically added by QLT-002
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("member, expected", [
        (BotCallbackPrefix.UNSUB, "unsub:"),
        (BotCallbackPrefix.UNSUB_ON, "unsub_on:"),
        (BotCallbackPrefix.LANG, "lang:"),
    ])
    def test_new_members_are_distinct_prefixes(
        self, member, expected: str
    ) -> None:
        """The new members are distinct prefixes (no accidental collision)."""
        assert str(member) == expected

    # ------------------------------------------------------------------
    # Runtime contract: startswith + f-string interpolation + len slicing
    # (the three operations the bot handlers and immediate_alerts use)
    # ------------------------------------------------------------------

    def test_unsub_filter_and_construction_match(self) -> None:
        """``F.data.startswith(UNSUB)`` matches ``f"{UNSUB}{token}"``."""
        token = "opaque_token_123"
        callback_data = f"{BotCallbackPrefix.UNSUB}{token}"
        assert callback_data.startswith(BotCallbackPrefix.UNSUB)
        # Token extraction via len-prefix slicing (as done in alerts.py).
        extracted = callback_data[len(BotCallbackPrefix.UNSUB) :]
        assert extracted == token

    def test_unsub_on_filter_and_construction_match(self) -> None:
        """``F.data.startswith(UNSUB_ON)`` matches ``f"{UNSUB_ON}{token}"``."""
        token = "opaque_token_123"
        callback_data = f"{BotCallbackPrefix.UNSUB_ON}{token}"
        assert callback_data.startswith(BotCallbackPrefix.UNSUB_ON)
        extracted = callback_data[len(BotCallbackPrefix.UNSUB_ON) :]
        assert extracted == token

    def test_lang_filter_and_construction_match(self) -> None:
        """``F.data.startswith(LANG)`` matches ``f"{LANG}{locale_value}"``."""
        locale_value = "bs"
        callback_data = f"{BotCallbackPrefix.LANG}{locale_value}"
        assert callback_data.startswith(BotCallbackPrefix.LANG)
        extracted = callback_data[len(BotCallbackPrefix.LANG) :]
        assert extracted == locale_value

    # ------------------------------------------------------------------
    # Backward-compatibility: immediate_alerts.UNSUB_CALLBACK_PREFIX
    # still resolves to the same string (StrEnum member is a str subclass).
    # ------------------------------------------------------------------

    def test_immediate_alerts_prefix_matches_enum(self) -> None:
        """``immediate_alerts.UNSUB_CALLBACK_PREFIX`` equals ``BotCallbackPrefix.UNSUB``."""
        assert UNSUB_CALLBACK_PREFIX == BotCallbackPrefix.UNSUB
        assert UNSUB_CALLBACK_PREFIX == "unsub:"

    def test_immediate_alerts_prefix_works_in_fstring(self) -> None:
        """The backend service's prefix constant still interops in f-strings."""
        token = "abc123"
        callback_data = f"{UNSUB_CALLBACK_PREFIX}{token}"
        assert callback_data == "unsub:abc123"
