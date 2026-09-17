"""
Tests for translate_all_languages — multi-language translation service.

Verifies that ``translate_all_languages`` correctly dispatches parallel
translation and falls back to the original text on failure.

All tests mock ``translate_cached_generic`` (the shared service's LRU-cached
translator) to avoid hitting the real Google Cloud Translation API.  Patching
at this level lets the mock receive ``(text, source_locale, target_locale)``
so per-locale assertions are possible.
"""

import time
from unittest.mock import patch

import httpx
import pytest
from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext as _

from apps.core.services.translation import (
    _CIRCUIT_BREAKER,
    translate_cached_generic,
    translate_text,
)
from telegram_bot.middlewares.language import _resolve_user_language
from telegram_bot.services.ad_data import translate_all_languages

pytestmark = [pytest.mark.unit]

# Patch target: translate_cached_generic in the shared translation module.
# translate_text looks up this name at call-time from the module namespace,
# so patching here intercepts every call from translate_all_languages.
_TRANSLATE_PATH: str = "apps.core.services.translation.translate_cached_generic"

# A reusable httpx.Request for constructing httpx exceptions in tests.
_REQUEST: httpx.Request = httpx.Request("POST", "http://test")


def _make_http_error(status_code: int) -> httpx.HTTPStatusError:
    """Factory for httpx.HTTPStatusError with a given response status code."""
    response = httpx.Response(status_code, request=_REQUEST)
    return httpx.HTTPStatusError(
        f"HTTP {status_code}",
        request=response.request,
        response=response,
    )


@pytest.fixture(autouse=True)
def _reset_translation_state() -> None:
    """Reset circuit-breaker and lru_cache before every test."""
    _CIRCUIT_BREAKER._failure_count = 0
    _CIRCUIT_BREAKER._last_failure_time = 0.0
    translate_cached_generic.cache_clear()


class TestTranslateAllLanguages:
    """Tests for translate_all_languages with mocked translator."""

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_returns_dict_with_all_locale_codes(self) -> None:
        """Returns a dict containing all requested locale codes as keys."""
        with patch(_TRANSLATE_PATH) as mock_translate:
            mock_translate.return_value = "translated"
            result = await translate_all_languages("Hello", ["ru", "bs", "en"])

        assert isinstance(result, dict)
        assert set(result) == {"ru", "bs", "en"}

    @pytest.mark.asyncio
    async def test_translation_non_empty_for_valid_input(self) -> None:
        """Returns a non-empty translated string when the translator succeeds."""
        with patch(_TRANSLATE_PATH) as mock_translate:
            mock_translate.return_value = "привет"
            result = await translate_all_languages("Hello", ["ru"])

        assert result["ru"] == "привет"

    @pytest.mark.asyncio
    async def test_translates_each_locale_independently(self) -> None:
        """Each locale receives the correct translation via parallel dispatch."""
        with patch(_TRANSLATE_PATH) as mock_translate:
            mock_translate.side_effect = lambda text, src, tgt: f"{text}-{tgt}"
            result = await translate_all_languages("Hello", ["ru", "bs", "en"])

        assert result["ru"] == "Hello-ru"
        assert result["bs"] == "Hello-bs"
        assert result["en"] == "Hello-en"

    # ------------------------------------------------------------------
    # Fallback behaviour
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_timeout_fallback_returns_original_text(self) -> None:
        """Returns original text when translation raises an exception."""
        with patch(_TRANSLATE_PATH) as mock_translate:
            mock_translate.side_effect = _make_http_error(429)
            result = await translate_all_languages("Original text", ["ru", "bs"])

        assert result["ru"] == "Original text"
        assert result["bs"] == "Original text"

    @pytest.mark.asyncio
    async def test_partial_failure_falls_back_per_locale(self) -> None:
        """One failing locale does not prevent others from succeeding."""

        def _side_effect(text: str, source: str, target: str) -> str:
            if target == "bs":
                raise _make_http_error(429)
            return f"{text}-{target}"

        with patch(_TRANSLATE_PATH) as mock_translate:
            mock_translate.side_effect = _side_effect
            result = await translate_all_languages("Hello", ["ru", "bs", "en"])

        assert result["ru"] == "Hello-ru"
        assert result["bs"] == "Hello"  # fallback
        assert result["en"] == "Hello-en"

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_empty_string_input(self) -> None:
        """Empty string input is passed through without calling translator."""
        with patch(_TRANSLATE_PATH) as mock_translate:
            mock_translate.return_value = ""
            result = await translate_all_languages("", ["ru", "en"])

        assert result["ru"] == ""
        assert result["en"] == ""
        mock_translate.assert_not_called()

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    async def test_circuit_breaker_open_short_circuits(self) -> None:
        """After 3 translation failures the circuit opens and short-circuits."""
        with patch(_TRANSLATE_PATH, side_effect=_make_http_error(429)):
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

    @pytest.mark.asyncio
    async def test_timeout_fallback_returns_original(self) -> None:
        """Translation exceeding the (patched) timeout falls back to original text."""

        def slow_translate(text: str, source: str, target: str) -> str:
            time.sleep(0.1)  # exceeds the patched 0.05s timeout
            return "too slow"

        with (
            patch("apps.core.services.translation.TRANSLATION_TIMEOUT_SECONDS", 0.05),
            patch(_TRANSLATE_PATH, side_effect=slow_translate),
        ):
            result = await translate_all_languages("original", ["ru"])

        assert result["ru"] == "original"

    @pytest.mark.asyncio
    async def test_empty_string_returns_empty(self) -> None:
        """Empty input is returned as empty without calling the translator."""
        with patch(_TRANSLATE_PATH) as mock_translate:
            result = await translate_all_languages("", ["ru", "en"])

        assert result == {"ru": "", "en": ""}
        mock_translate.assert_not_called()

    @pytest.mark.asyncio
    async def test_gather_return_exceptions_isolates_failure(self) -> None:
        """One locale's failure does not cancel translations in other locales."""

        def _side_effect(text: str, source: str, target: str) -> str:
            if target == "bs":
                raise httpx.RequestError("BS translation failed", request=_REQUEST)
            return f"{text}-{target}"

        with patch(_TRANSLATE_PATH) as mock_translate:
            mock_translate.side_effect = _side_effect
            result = await translate_all_languages("Hello", ["ru", "bs", "en"])

        assert result["ru"] == "Hello-ru"
        assert result["bs"] == "Hello"
        assert result["en"] == "Hello-en"


class TestTranslateTextExceptNarrowing:
    """Unit tests for the narrowed except clause in translate_text (sync).

    translate_text is synchronous (it owns its thread-pool worker), so these
    tests call it directly without requiring an event loop.
    """

    @pytest.mark.parametrize(
        "exc",
        [
            httpx.RequestError("transport error", request=_REQUEST),
            httpx.ReadTimeout("read timeout", request=_REQUEST),
            _make_http_error(429),
            _make_http_error(400),
        ],
        ids=[
            "RequestError",
            "ReadTimeout",
            "HTTPStatusError-429",
            "HTTPStatusError-400",
        ],
    )
    def test_narrowed_except_catches_httpx_family(self, exc: Exception) -> None:
        """httpx exception family is caught and falls back to original text."""
        with patch(_TRANSLATE_PATH, side_effect=exc):
            result = translate_text("Original text", "auto", "ru")

        assert result == "Original text"

    def test_non_family_error_propagates(self) -> None:
        """Non-family exceptions (AttributeError) propagate instead of being swallowed."""
        with patch(_TRANSLATE_PATH, side_effect=AttributeError("unexpected")):
            with pytest.raises(AttributeError):
                translate_text("Original text", "auto", "ru")


class TestTranslateTextRetry:
    """Tests for bounded retry with exponential backoff in translate_text.

    translate_text retries retryable exceptions (httpx.TimeoutException,
    httpx.RequestError, httpx.HTTPStatusError on 429/5xx) up to
    ``TRANSLATION_MAX_ATTEMPTS`` (2), while non-retryable HTTP errors
    (400/401/403) fall back immediately without retry.
    """

    def test_retry_succeeds_after_transient_failure(self) -> None:
        """A retryable failure followed by success returns the translation."""
        with patch(_TRANSLATE_PATH) as mock_translate:
            mock_translate.side_effect = [
                _make_http_error(429),
                "переведено",
            ]
            result = translate_text("hello", "auto", "ru")

        assert result == "переведено"
        assert mock_translate.call_count == 2

    def test_too_many_requests_retried_then_fallback(self) -> None:
        """Persistent HTTP 429 exhausts retries and falls back to original."""
        with patch(_TRANSLATE_PATH) as mock_translate:
            mock_translate.side_effect = _make_http_error(429)
            result = translate_text("hello", "auto", "ru")

        assert result == "hello"
        assert mock_translate.call_count == 2
        assert _CIRCUIT_BREAKER._failure_count > 0

    def test_non_retryable_http_error_not_retried(self) -> None:
        """HTTP 400 is not retried — single attempt then fallback."""
        with patch(_TRANSLATE_PATH) as mock_translate:
            mock_translate.side_effect = _make_http_error(400)
            result = translate_text("hello", "auto", "ru")

        assert result == "hello"
        assert mock_translate.call_count == 1


# ---------------------------------------------------------------------------
# Per-user locale activation (FQ-001)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
class TestPerUserLocaleActivation:
    """Verify that ``_resolve_user_language`` + ``translation.activate``
    renders gettext strings in the user's preferred locale.

    DB-backed: creates real ``User`` rows and exercises the ``sync_to_async``
    ORM lookup path in ``LanguageMiddleware._resolve_user_language``.
    Uses ``transaction=True`` (bot-test convention) to avoid deadlock
    against leaked worker-thread connections.
    """

    @pytest.mark.asyncio
    async def test_ru_user_resolves_and_translates(self) -> None:
        """A user with ``telegram_language='ru'`` gets Russian gettext output."""
        from apps.users.models import User

        user = await sync_to_async(User.objects.create)(
            telegram_id=900000301,
            chat_id=900000301,
            username="ru_user",
            telegram_language="ru",
        )
        try:
            lang = await _resolve_user_language(user.telegram_id)
            assert lang == "ru"

            translation.activate(lang)
            try:
                assert _("Contact us") == "Связаться с нами"
            finally:
                translation.deactivate()
        finally:
            await sync_to_async(user.delete)()

    @pytest.mark.asyncio
    async def test_bs_user_resolves_and_translates(self) -> None:
        """A user with ``telegram_language='bs'`` gets Bosnian gettext output."""
        from apps.users.models import User

        user = await sync_to_async(User.objects.create)(
            telegram_id=900000302,
            chat_id=900000302,
            username="bs_user",
            telegram_language="bs",
        )
        try:
            lang = await _resolve_user_language(user.telegram_id)
            assert lang == "bs"

            translation.activate(lang)
            try:
                assert _("Contact us") == "Kontaktiraj nas"
            finally:
                translation.deactivate()
        finally:
            await sync_to_async(user.delete)()

    @pytest.mark.asyncio
    async def test_unknown_user_falls_back_to_default(self) -> None:
        """A non-existent Telegram ID falls back to ``settings.LANGUAGE_CODE``."""
        lang = await _resolve_user_language(999_999_999)
        assert lang == settings.LANGUAGE_CODE

    @pytest.mark.asyncio
    async def test_null_language_falls_back_to_default(self) -> None:
        """A user with ``telegram_language=""`` falls back to ``LANGUAGE_CODE``."""
        from apps.users.models import User

        user = await sync_to_async(User.objects.create)(
            telegram_id=900000303,
            chat_id=900000303,
            username="no_lang_user",
            telegram_language="",
        )
        try:
            lang = await _resolve_user_language(user.telegram_id)
            assert lang == settings.LANGUAGE_CODE
        finally:
            await sync_to_async(user.delete)()
