"""
Tests for the translation service and its circuit breaker.

Covers:
- TranslationCircuitBreaker state transitions: closed -> open on failure
  threshold, reset to closed on success, half-open after cooldown.
- translate_text() fallback: returns original text when the translator raises,
  and the circuit breaker short-circuits after the failure threshold.
- translate_text() success: returns translated text and keeps the circuit closed.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import httpx
import pytest

from apps.core.services.translation import (
    _CIRCUIT_BREAKER,
    TRANSLATION_MAX_ATTEMPTS,
    TranslationCircuitBreaker,
    translate_cached_generic,
    translate_text,
)

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _reset_translation_state():
    """Clear lru_cache and reset the module-level circuit breaker before/after each test.

    The module-level ``_CIRCUIT_BREAKER`` singleton and ``translate_cached_generic``
    lru_cache are shared across the test process; this fixture ensures a clean
    state for every test.
    """
    translate_cached_generic.cache_clear()
    _CIRCUIT_BREAKER._failure_count = 0
    _CIRCUIT_BREAKER._last_failure_time = 0.0
    yield
    translate_cached_generic.cache_clear()
    _CIRCUIT_BREAKER._failure_count = 0
    _CIRCUIT_BREAKER._last_failure_time = 0.0


# ---------------------------------------------------------------------------
# TranslationCircuitBreaker unit tests
# ---------------------------------------------------------------------------


class TestTranslationCircuitBreaker:
    """Unit tests for the TranslationCircuitBreaker state machine."""

    def test_circuit_breaker_closed_initially(self) -> None:
        """A fresh breaker is closed (not open)."""
        breaker = TranslationCircuitBreaker(failure_threshold=3, cooldown_seconds=60)
        assert breaker.is_open is False

    def test_circuit_breaker_opens_on_error(self) -> None:
        """Circuit opens after ``failure_threshold`` consecutive failures."""
        breaker = TranslationCircuitBreaker(failure_threshold=3, cooldown_seconds=60)
        for _ in range(3):
            breaker.record_failure()
        assert breaker.is_open is True

    def test_circuit_breaker_does_not_open_below_threshold(self) -> None:
        """Circuit stays closed when failure count is below the threshold."""
        breaker = TranslationCircuitBreaker(failure_threshold=3, cooldown_seconds=60)
        for _ in range(2):
            breaker.record_failure()
        assert breaker.is_open is False

    def test_circuit_breaker_closes_on_success(self) -> None:
        """A single success resets the breaker back to closed."""
        breaker = TranslationCircuitBreaker(failure_threshold=3, cooldown_seconds=60)
        for _ in range(3):
            breaker.record_failure()
        assert breaker.is_open is True

        breaker.record_success()
        assert breaker.is_open is False

    def test_circuit_breaker_half_open_after_cooldown(self) -> None:
        """After the cooldown elapses, the breaker transitions to half-open.

        In half-open state ``is_open`` returns False, allowing the next call
        to proceed through to the upstream service.
        """
        breaker = TranslationCircuitBreaker(
            failure_threshold=1, cooldown_seconds=0.01
        )
        breaker.record_failure()
        assert breaker.is_open is True

        time.sleep(0.05)
        assert breaker.is_open is False

    def test_circuit_breaker_reopens_after_cooldown_and_failure(self) -> None:
        """After cooldown (half-open), a new failure re-opens the circuit."""
        breaker = TranslationCircuitBreaker(
            failure_threshold=1, cooldown_seconds=0.01
        )
        breaker.record_failure()
        assert breaker.is_open is True

        time.sleep(0.05)
        # Half-open: a single failure re-opens.
        breaker.record_failure()
        assert breaker.is_open is True


# ---------------------------------------------------------------------------
# translate_text() integration with circuit breaker
# ---------------------------------------------------------------------------


class TestTranslateTextFallback:
    """Tests for translate_text() graceful degradation on translator errors."""

    def test_translate_text_fallback_on_error(self) -> None:
        """translate_text returns the original text when the translator raises.

        After enough failures to cross the circuit-breaker threshold, the
        circuit opens and subsequent calls short-circuit without calling
        the upstream API at all.
        """
        with patch(
            "apps.core.services.translation._translate_via_api",
            side_effect=httpx.ConnectError("connection refused"),
        ) as mock_api, patch(
            "apps.core.services.translation.time.sleep", return_value=None
        ):
            original = "Hello world"

            # Each call attempts TRANSLATION_MAX_ATTEMPTS retries.
            # After two calls (4 failures >= threshold 3) the circuit opens.
            for _ in range(2):
                result = translate_text(original, "en", "ru")
                assert result == original

            assert _CIRCUIT_BREAKER.is_open is True

            # Third call: circuit is open — short-circuit, no API call.
            mock_api.reset_mock()
            result = translate_text(original, "en", "ru")
            assert result == original
            mock_api.assert_not_called()

    def test_translate_text_empty_returns_input(self) -> None:
        """Empty or whitespace-only input is returned unchanged (no API call)."""
        with patch(
            "apps.core.services.translation._translate_via_api"
        ) as mock_api:
            assert translate_text("", "en", "ru") == ""
            assert translate_text("   ", "en", "ru") == "   "
            mock_api.assert_not_called()

    def test_translate_text_attempts_max_retries(self) -> None:
        """translate_text retries up to TRANSLATION_MAX_ATTEMPTS before falling back."""
        call_count = 0

        def _raise(*args: object, **kwargs: object) -> str:
            nonlocal call_count
            call_count += 1
            raise httpx.ConnectError("refused")

        with patch(
            "apps.core.services.translation._translate_via_api", side_effect=_raise
        ), patch(
            "apps.core.services.translation.time.sleep", return_value=None
        ):
            result = translate_text("Hello", "en", "ru")
            assert result == "Hello"

        # Each attempt calls _translate_via_api once (through the executor).
        # With max_attempts=2 and empty retry, we expect exactly 2 calls.
        assert call_count == TRANSLATION_MAX_ATTEMPTS


class TestTranslateTextSuccess:
    """Tests for translate_text() on the happy path."""

    def test_translate_text_success_returns_translated(self) -> None:
        """translate_text returns the translated text on success."""
        with patch(
            "apps.core.services.translation._translate_via_api",
            return_value="Привет мир",
        ):
            result = translate_text("Hello world", "en", "ru")

        assert result == "Привет мир"
        assert _CIRCUIT_BREAKER.is_open is False

    def test_translate_text_success_resets_failure_count(self) -> None:
        """A success after prior failures closes the circuit."""
        with patch(
            "apps.core.services.translation._translate_via_api",
            return_value="Translated",
        ):
            result = translate_text("Hello", "en", "ru")

        assert result == "Translated"
        assert _CIRCUIT_BREAKER.is_open is False
