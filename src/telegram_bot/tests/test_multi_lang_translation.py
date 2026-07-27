"""
Tests for translate_all_languages — multi-language translation service.

Verifies that ``translate_all_languages`` correctly dispatches parallel
translation and falls back to the original text on failure.

All tests mock the synchronous ``_do_translate_to`` function to avoid
hitting real translation APIs (deep-translator / Google Translate).
"""

from unittest.mock import patch

import pytest

from telegram_bot.handlers.ad_create import translate_all_languages

pytestmark = [pytest.mark.asyncio]


class TestTranslateAllLanguages:
    """Tests for translate_all_languages with mocked translator."""

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    async def test_returns_dict_with_all_locale_codes(self) -> None:
        """Returns a dict containing all requested locale codes as keys."""
        with patch(
            "telegram_bot.handlers.ad_create._do_translate_to"
        ) as mock_translate:
            mock_translate.return_value = "translated"
            result = await translate_all_languages("Hello", ["ru", "bs", "en"])

        assert isinstance(result, dict)
        assert set(result) == {"ru", "bs", "en"}

    async def test_translation_non_empty_for_valid_input(self) -> None:
        """Returns a non-empty translated string when the translator succeeds."""
        with patch(
            "telegram_bot.handlers.ad_create._do_translate_to"
        ) as mock_translate:
            mock_translate.return_value = "привет"
            result = await translate_all_languages("Hello", ["ru"])

        assert result["ru"] == "привет"

    async def test_translates_each_locale_independently(self) -> None:
        """Each locale receives the correct translation via parallel dispatch."""
        with patch(
            "telegram_bot.handlers.ad_create._do_translate_to"
        ) as mock_translate:
            mock_translate.side_effect = lambda text, target: f"{text}-{target}"
            result = await translate_all_languages(
                "Hello", ["ru", "bs", "en"]
            )

        assert result["ru"] == "Hello-ru"
        assert result["bs"] == "Hello-bs"
        assert result["en"] == "Hello-en"

    # ------------------------------------------------------------------
    # Fallback behaviour
    # ------------------------------------------------------------------

    async def test_timeout_fallback_returns_original_text(self) -> None:
        """Returns original text when translation raises an exception."""
        with patch(
            "telegram_bot.handlers.ad_create._do_translate_to"
        ) as mock_translate:
            mock_translate.side_effect = RuntimeError("Translation failed")
            result = await translate_all_languages(
                "Original text", ["ru", "bs"]
            )

        assert result["ru"] == "Original text"
        assert result["bs"] == "Original text"

    async def test_partial_failure_falls_back_per_locale(self) -> None:
        """One failing locale does not prevent others from succeeding."""
        call_count = 0

        def _side_effect(text: str, target: str) -> str:
            nonlocal call_count
            call_count += 1
            if target == "bs":
                raise RuntimeError("BS translation failed")
            return f"{text}-{target}"

        with patch(
            "telegram_bot.handlers.ad_create._do_translate_to"
        ) as mock_translate:
            mock_translate.side_effect = _side_effect
            result = await translate_all_languages(
                "Hello", ["ru", "bs", "en"]
            )

        assert result["ru"] == "Hello-ru"
        assert result["bs"] == "Hello"  # fallback
        assert result["en"] == "Hello-en"

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    async def test_empty_string_input(self) -> None:
        """Empty string input is passed through to the translator."""
        with patch(
            "telegram_bot.handlers.ad_create._do_translate_to"
        ) as mock_translate:
            mock_translate.return_value = ""
            result = await translate_all_languages("", ["ru", "en"])

        assert result["ru"] == ""
        assert result["en"] == ""

    async def test_single_locale(self) -> None:
        """Works correctly with a single target locale."""
        with patch(
            "telegram_bot.handlers.ad_create._do_translate_to"
        ) as mock_translate:
            mock_translate.return_value = "Здравствуйте"
            result = await translate_all_languages("Hi", ["ru"])

        assert len(result) == 1
        assert result["ru"] == "Здравствуйте"