"""
Tests for translate_all_languages — multi-language translation service.

Verifies that ``translate_all_languages`` correctly dispatches parallel
translation and falls back to the original text on failure.

All tests mock ``translate_cached_generic`` (the shared service's LRU-cached
translator) to avoid hitting real translation APIs (deep-translator / Google
Translate).  Patching at this level lets the mock receive ``(text,
source_locale, target_locale)`` so per-locale assertions are possible.
"""

import time
from unittest.mock import patch

import pytest

from apps.core.services.translation import (
    _CIRCUIT_BREAKER,
    translate_cached,
    translate_cached_generic,
)
from telegram_bot.handlers.ad_create import translate_all_languages

pytestmark = [pytest.mark.asyncio]

# Patch target: translate_cached_generic in the shared translation module.
# translate_text looks up this name at call-time from the module namespace,
# so patching here intercepts every call from translate_all_languages.
_TRANSLATE_PATH: str = "apps.core.services.translation.translate_cached_generic"


@pytest.fixture(autouse=True)
def _reset_translation_state() -> None:
    """Reset circuit-breaker and lru_cache before every test."""
    _CIRCUIT_BREAKER._failure_count = 0
    _CIRCUIT_BREAKER._last_failure_time = 0.0
    translate_cached.cache_clear()
    translate_cached_generic.cache_clear()


class TestTranslateAllLanguages:
    """Tests for translate_all_languages with mocked translator."""

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    async def test_returns_dict_with_all_locale_codes(self) -> None:
        """Returns a dict containing all requested locale codes as keys."""
        with patch(_TRANSLATE_PATH) as mock_translate:
            mock_translate.return_value = "translated"
            result = await translate_all_languages("Hello", ["ru", "bs", "en"])

        assert isinstance(result, dict)
        assert set(result) == {"ru", "bs", "en"}

    async def test_translation_non_empty_for_valid_input(self) -> None:
        """Returns a non-empty translated string when the translator succeeds."""
        with patch(_TRANSLATE_PATH) as mock_translate:
            mock_translate.return_value = "привет"
            result = await translate_all_languages("Hello", ["ru"])

        assert result["ru"] == "привет"

    async def test_translates_each_locale_independently(self) -> None:
        """Each locale receives the correct translation via parallel dispatch."""
        with patch(_TRANSLATE_PATH) as mock_translate:
            mock_translate.side_effect = lambda text, src, tgt: f"{text}-{tgt}"
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
        with patch(_TRANSLATE_PATH) as mock_translate:
            mock_translate.side_effect = RuntimeError("Translation failed")
            result = await translate_all_languages(
                "Original text", ["ru", "bs"]
            )

        assert result["ru"] == "Original text"
        assert result["bs"] == "Original text"

    async def test_partial_failure_falls_back_per_locale(self) -> None:
        """One failing locale does not prevent others from succeeding."""

        def _side_effect(text: str, source: str, target: str) -> str:
            if target == "bs":
                raise RuntimeError("BS translation failed")
            return f"{text}-{target}"

        with patch(_TRANSLATE_PATH) as mock_translate:
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
        """Empty string input is passed through without calling translator."""
        with patch(_TRANSLATE_PATH) as mock_translate:
            mock_translate.return_value = ""
            result = await translate_all_languages("", ["ru", "en"])

        assert result["ru"] == ""
        assert result["en"] == ""
        mock_translate.assert_not_called()

    async def test_single_locale(self) -> None:
        """Works correctly with a single target locale."""
        with patch(_TRANSLATE_PATH) as mock_translate:
            mock_translate.return_value = "Здравствуйте"
            result = await translate_all_languages("Hi", ["ru"])

        assert len(result) == 1
        assert result["ru"] == "Здравствуйте"

    # ------------------------------------------------------------------
    # Parity tests (circuit breaker & timeout in shared service)
    # ------------------------------------------------------------------

    async def test_circuit_breaker_open_short_circuits(self) -> None:
        """After 3 translation failures the circuit opens and short-circuits."""
        with patch(_TRANSLATE_PATH, side_effect=RuntimeError("fail")):
            # Three failed calls open the circuit.
            await translate_all_languages("test text", ["ru"])
            await translate_all_languages("test text", ["ru"])
            await translate_all_languages("test text", ["ru"])

        assert _CIRCUIT_BREAKER.is_open

        # Fourth call short-circuits: translator not called at all.
        with patch(_TRANSLATE_PATH) as mock_translate:
            result = await translate_all_languages("different text", ["ru"])
            assert result["ru"] == "different text"
            mock_translate.assert_not_called()

    async def test_timeout_fallback_returns_original(self) -> None:
        """Translation exceeding the 500ms timeout falls back to original text."""

        def slow_translate(text: str, source: str, target: str) -> str:
            time.sleep(0.8)  # exceeds 500ms timeout
            return "too slow"

        with patch(_TRANSLATE_PATH, side_effect=slow_translate):
            result = await translate_all_languages("original", ["ru"])

        assert result["ru"] == "original"

    async def test_empty_string_returns_empty(self) -> None:
        """Empty input is returned as empty without calling the translator."""
        with patch(_TRANSLATE_PATH) as mock_translate:
            result = await translate_all_languages("", ["ru", "en"])

        assert result == {"ru": "", "en": ""}
        mock_translate.assert_not_called()
