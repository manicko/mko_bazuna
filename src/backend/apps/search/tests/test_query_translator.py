"""
Tests for translate_query_bs_to_ru with mocked network (TST-006).

Covers:
- Success: returns translated string
- Exception / timeout: returns original query (fallback)
- Empty / whitespace: short-circuits without calling the translator
"""

import time
from unittest.mock import patch

import pytest
from requests.exceptions import RequestException

from apps.search.services.query_translator import (
    _CIRCUIT_BREAKER,
    translate_cached,
    translate_query_bs_to_ru,
)

# Module path for GoogleTranslator.translate in the query_translator module.
# Using the string path form of patch() to avoid importing the real class.
_TRANSLATE_PATH: str = "apps.search.services.query_translator.GoogleTranslator.translate"


@pytest.fixture(autouse=True)
def _reset_translation_state() -> None:
    """Reset circuit-breaker and lru_cache before every test."""
    _CIRCUIT_BREAKER._failure_count = 0
    _CIRCUIT_BREAKER._last_failure_time = 0.0
    translate_cached.cache_clear()


class TestTranslateQueryBsToRuSuccess:
    """Happy-path: mocked translator returns a translated string."""

    def test_returns_translated_text(self) -> None:
        """translate_query_bs_to_ru returns the mocked translated text."""
        with patch(_TRANSLATE_PATH, return_value="привет") as mock_translate:
            result = translate_query_bs_to_ru("zdravo")
        assert result == "привет"
        mock_translate.assert_called_once()


class TestTranslateQueryBsToRuFallback:
    """Fallback: exception/timeout returns the original query."""

    def test_timeout_returns_original_query(self) -> None:
        """ThreadPoolExecutor timeout returns original query."""
        with patch(
            "apps.core.services.translation.TRANSLATION_TIMEOUT_SECONDS", 0.05
        ), patch(
            _TRANSLATE_PATH,
            side_effect=lambda *_: time.sleep(0.2),
        ):
            result = translate_query_bs_to_ru("bok")
        assert result == "bok"

    def test_request_exception_returns_original_query(self) -> None:
        """RequestException returns original query."""
        with patch(
            _TRANSLATE_PATH,
            side_effect=RequestException("connection refused"),
        ):
            result = translate_query_bs_to_ru("hvala")
        assert result == "hvala"

    def test_generic_exception_returns_original_query(self) -> None:
        """Any other exception returns original query."""
        with patch(
            _TRANSLATE_PATH,
            side_effect=RuntimeError("unexpected"),
        ):
            result = translate_query_bs_to_ru("dobar dan")
        assert result == "dobar dan"


class TestTranslateQueryBsToRuShortCircuit:
    """Short-circuit: empty/whitespace returns immediately."""

    def test_empty_query_returns_empty(self) -> None:
        """Empty string returns immediately without calling translator."""
        with patch(_TRANSLATE_PATH) as mock_translate:
            result = translate_query_bs_to_ru("")
        assert result == ""
        mock_translate.assert_not_called()

    def test_whitespace_only_returns_whitespace(self) -> None:
        """Whitespace-only string returns immediately without calling translator."""
        with patch(_TRANSLATE_PATH) as mock_translate:
            result = translate_query_bs_to_ru("   ")
        assert result == "   "
        mock_translate.assert_not_called()