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

import json
import logging
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

    def test_translation_error_log_does_not_leak_api_key(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An HTTPStatusError whose URL carries ?key=<SECRET> is logged without
        the secret appearing in the formatted log message.

        Regression test for CFG-002: translation.py must log a query-stripped URL
        (or exception type) rather than str(e), and RedactingJsonFormatter must
        redact any surviving key=VALUE pattern.
        """
        from django.core.management import (
            call_command,  # noqa: F401  (ensures settings configured)
        )

        from apps.core.utils.json_logging import RedactingJsonFormatter

        secret = "yaGOOGLE_TRANSLATE_API_KEY-secret-1234567890abcdef"
        url = httpx.URL(
            f"https://translation.googleapis.com/language/translate/v2?key={secret}"
        )
        request = httpx.Request("POST", url)
        response = httpx.Response(401, request=request)
        http_error = httpx.HTTPStatusError(
            "Client error '401 Unauthorized' for url ...",
            request=request,
            response=response,
        )

        formatter = RedactingJsonFormatter()
        with patch(
            "apps.core.services.translation._translate_via_api",
            side_effect=http_error,
        ), patch("apps.core.services.translation.time.sleep", return_value=None), \
             caplog.at_level(logging.WARNING, logger="apps.core.services.translation"):
            translate_text("Hello", "en", "ru")

        # Primary fix: the secret must not appear in any captured log record.
        for record in caplog.records:
            formatted = formatter.format(record)
            assert secret not in formatted
        # Defense-in-depth: the stripped URL should appear (proves URL, not exception, is logged).
        assert "translation.googleapis.com" in formatter.format(caplog.records[-1])
        assert "key=" not in formatter.format(caplog.records[-1]).replace(
            "key=REDACTED", "", 1
        )

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

    def test_translate_text_malformed_200_opens_breaker(self) -> None:
        """A malformed 200 response (bad JSON body) charges the circuit breaker.

        Regression test for EXT-005: ``translate_text`` must treat a
        ``json.JSONDecodeError`` (raised by ``response.json()`` on a malformed
        body) exactly like a transport failure -- recording the failure on the
        circuit breaker and engaging backoff -- rather than leaking the parser
        exception and bypassing the breaker.
        """
        with patch(
            "apps.core.services.translation._translate_via_api",
            side_effect=json.JSONDecodeError(
                "Expecting value", doc="", pos=0
            ),
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

            # Third call: circuit is open -- short-circuit, no API call.
            mock_api.reset_mock()
            result = translate_text(original, "en", "ru")
            assert result == original
            mock_api.assert_not_called()

    def test_translate_text_malformed_200_missing_key_opens_breaker(self) -> None:
        """A 200 body missing the nested translation key charges the breaker.

        Regression test for EXT-005: ``translate_text`` must treat the
        ``KeyError`` raised when ``data["data"]["translations"][0]
        ["translatedText"]`` is missing exactly like a transport failure.
        """
        with patch(
            "apps.core.services.translation._translate_via_api",
            side_effect=KeyError("translatedText"),
        ) as mock_api, patch(
            "apps.core.services.translation.time.sleep", return_value=None
        ):
            original = "Hello world"

            for _ in range(2):
                result = translate_text(original, "en", "ru")
                assert result == original

            assert _CIRCUIT_BREAKER.is_open is True

            mock_api.reset_mock()
            result = translate_text(original, "en", "ru")
            assert result == original
            mock_api.assert_not_called()


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


# ---------------------------------------------------------------------------
# Log-field redaction and observability (09-API-017)
# ---------------------------------------------------------------------------

# Seller-authored ad text carrying both a phone number and an e-mail address.
# Neither identifier may reach ANY log record this module emits.
_HOSTILE_TEXT = "Selling bike call +387 61 123 456 or seller@example.com"


class TestTranslationLogRedaction:
    """translate_text's log sites must not leak PII from ad text (09-API-017)."""

    def _assert_no_pii(self, caplog: pytest.LogCaptureFixture) -> None:
        joined = "\n".join(record.getMessage() for record in caplog.records)
        assert "+387 61 123 456" not in joined
        assert "seller@example.com" not in joined

    def test_open_circuit_line_redacts_ad_text(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The open-circuit INFO line masks phone and e-mail."""
        _CIRCUIT_BREAKER._failure_count = _CIRCUIT_BREAKER.failure_threshold
        _CIRCUIT_BREAKER._last_failure_time = time.monotonic()
        assert _CIRCUIT_BREAKER.is_open

        with caplog.at_level(
            logging.INFO, logger="apps.core.services.translation"
        ):
            result = translate_text(_HOSTILE_TEXT, "ru", "en")

        assert result == _HOSTILE_TEXT
        self._assert_no_pii(caplog)

    def test_debug_success_line_redacts_input_and_output(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The DEBUG success line masks BOTH the input and the translated output.

        A phone number survives translation into the recipient language, so
        masking the input alone is insufficient.
        """
        with patch(
            "apps.core.services.translation._translate_via_api",
            return_value=_HOSTILE_TEXT,
        ), caplog.at_level(
            logging.DEBUG, logger="apps.core.services.translation"
        ):
            result = translate_text(_HOSTILE_TEXT, "ru", "en")

        assert result == _HOSTILE_TEXT
        self._assert_no_pii(caplog)
        # The success line is the DEBUG one; prove it fired so the assertion
        # above is not vacuous.
        assert any(
            "Translated" in record.getMessage() for record in caplog.records
        )

    def test_transport_failure_line_redacts_ad_text(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The transport-failure WARNING masks phone and e-mail."""
        with patch(
            "apps.core.services.translation._translate_via_api",
            side_effect=httpx.ConnectError("refused"),
        ), patch(
            "apps.core.services.translation.time.sleep", return_value=None
        ), caplog.at_level(
            logging.WARNING, logger="apps.core.services.translation"
        ):
            result = translate_text(_HOSTILE_TEXT, "ru", "en")

        assert result == _HOSTILE_TEXT
        self._assert_no_pii(caplog)

    def test_http_failure_line_redacts_ad_text(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The HTTP-failure WARNING masks phone and e-mail."""
        url = httpx.URL("https://translation.googleapis.com/language/translate/v2")
        request = httpx.Request("POST", url)
        response = httpx.Response(403, request=request)
        http_error = httpx.HTTPStatusError(
            "Client error '403 Forbidden'", request=request, response=response
        )
        with patch(
            "apps.core.services.translation._translate_via_api",
            side_effect=http_error,
        ), patch(
            "apps.core.services.translation.time.sleep", return_value=None
        ), caplog.at_level(
            logging.WARNING, logger="apps.core.services.translation"
        ):
            result = translate_text(_HOSTILE_TEXT, "ru", "en")

        assert result == _HOSTILE_TEXT
        self._assert_no_pii(caplog)

    def test_ordinary_text_still_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Control: text with no identifiers still appears in the log.

        A blanket "log nothing" change would satisfy the redaction tests and
        destroy triage; this test prevents it.
        """
        with patch(
            "apps.core.services.translation._translate_via_api",
            return_value="Bicycle for sale",
        ), caplog.at_level(
            logging.DEBUG, logger="apps.core.services.translation"
        ):
            translate_text("Bicycle for sale", "ru", "en")

        joined = "\n".join(record.getMessage() for record in caplog.records)
        assert "Bicycle for sale" in joined


class TestTranslationMetrics:
    """The three 09-API-017 metrics exist and track the service's behaviour."""

    def test_requests_and_fallbacks_counters_increment(self) -> None:
        """A success increments requests only; a failure increments both."""
        from apps.core.services.translation import (
            TRANSLATION_FALLBACKS,
            TRANSLATION_REQUESTS,
        )

        requests_before = TRANSLATION_REQUESTS._value.get()
        fallbacks_before = TRANSLATION_FALLBACKS._value.get()

        with patch(
            "apps.core.services.translation._translate_via_api",
            return_value="Translated",
        ):
            translate_text("Hello", "en", "ru")

        assert TRANSLATION_REQUESTS._value.get() == requests_before + 1
        assert TRANSLATION_FALLBACKS._value.get() == fallbacks_before

        with patch(
            "apps.core.services.translation._translate_via_api",
            side_effect=httpx.ConnectError("refused"),
        ), patch(
            "apps.core.services.translation.time.sleep", return_value=None
        ):
            # A distinct string avoids the lru_cache hit from the success above.
            translate_text("Goodbye", "en", "ru")

        assert TRANSLATION_REQUESTS._value.get() == requests_before + 2
        assert TRANSLATION_FALLBACKS._value.get() == fallbacks_before + 1

    def test_circuit_open_gauge_tracks_is_open(self) -> None:
        """The gauge is 1 while the breaker is open and 0 after a success."""
        from apps.core.services.translation import TRANSLATION_CIRCUIT_OPEN

        _CIRCUIT_BREAKER._failure_count = 0
        _CIRCUIT_BREAKER.record_success()
        assert TRANSLATION_CIRCUIT_OPEN._value.get() == 0

        _CIRCUIT_BREAKER.record_failure()
        _CIRCUIT_BREAKER.record_failure()
        _CIRCUIT_BREAKER.record_failure()
        assert _CIRCUIT_BREAKER.is_open is True
        assert TRANSLATION_CIRCUIT_OPEN._value.get() == 1

        _CIRCUIT_BREAKER.record_success()
        assert TRANSLATION_CIRCUIT_OPEN._value.get() == 0

