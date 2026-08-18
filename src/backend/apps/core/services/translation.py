"""
Shared translation service for Mko Bazuna.

Provides Google Translate-backed text translation with timeout (~500ms),
fallback, LRU cache, and circuit-breaker for graceful degradation under
translator throttling.

Used at publication time by the bot's ad-creation translator
(``telegram_bot.handlers.ad_create``). Search/alert query translation was
removed — the search path now uses language-aware per-language FTS vectors
with no external translation.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from functools import lru_cache
from typing import Final

from deep_translator import GoogleTranslator
from requests.exceptions import RequestException

from apps.core.utils.sanitize import sanitize_query_for_log

# Module-level executor. Without a `with` block, a timed-out future is abandoned
# rather than waited on via shutdown(wait=True), so the timeout actually bounds latency.
# max_workers=4 allows the bot's 3-locale parallel gather to translate concurrently
# rather than serializing on a single worker.
_EXECUTOR: Final[ThreadPoolExecutor] = ThreadPoolExecutor(max_workers=4)

logger = logging.getLogger(__name__)

TRANSLATION_TIMEOUT_SECONDS: Final[float] = 0.5  # ~500ms timeout via exceptions


class TranslationCircuitBreaker:
    """
    Lightweight in-process circuit-breaker for the translation service.

    After ``failure_threshold`` consecutive failures the circuit *opens* and
    short-circuits to the original-query fallback for ``cooldown_seconds``.
    After the cooldown the circuit transitions to *half-open*: the next call
    is allowed through.  If it succeeds the circuit resets to *closed*; if it
    fails the counter restarts and the cooldown begins again.

    Thread-safe for the simple read/write in this module (GIL-protected
    int/float operations).
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: float = 60.0,
    ) -> None:
        self.failure_threshold: Final[int] = failure_threshold
        self.cooldown_seconds: Final[float] = cooldown_seconds
        self._failure_count: int = 0
        self._last_failure_time: float = 0.0

    # --- public query API ---------------------------------------------------

    @property
    def is_open(self) -> bool:
        """Return True when the circuit is open (short-circuit to fallback)."""
        if self._failure_count < self.failure_threshold:
            return False
        elapsed = time.monotonic() - self._last_failure_time
        if elapsed >= self.cooldown_seconds:
            return False  # half-open – let the next call through
        return True

    def record_success(self) -> None:
        """Call after a successful translation to reset the breaker."""
        self._failure_count = 0

    def record_failure(self) -> None:
        """Call after a failed translation to increment the counter."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count == self.failure_threshold:
            logger.warning(
                "Translation circuit OPEN after %d consecutive failures "
                "(cooldown=%.0fs)",
                self.failure_threshold,
                self.cooldown_seconds,
            )


# Module-level singleton.
_CIRCUIT_BREAKER: Final[TranslationCircuitBreaker] = TranslationCircuitBreaker()


@lru_cache(maxsize=128)
def translate_cached(query: str) -> str:
    """
    Cached translation function.

    Uses lru_cache with maxsize=128 to cache translations.
    The cache is invalidated by clearing on criteria change or after 5 minutes.

    Args:
        query: The search query to translate

    Returns:
        Translated query in Russian
    """
    translator = GoogleTranslator(source="bs", target="ru")
    return translator.translate(query)


@lru_cache(maxsize=256)
def translate_cached_generic(
    query: str, source_locale: str, target_locale: str
) -> str:
    """
    Cached translation function supporting any language pair.

    Uses lru_cache with maxsize=256 to cache translations.

    Args:
        query: The text to translate
        source_locale: Source language code (e.g., "bs", "ru", "en")
        target_locale: Target language code (e.g., "ru", "en")

    Returns:
        Translated text
    """
    translator = GoogleTranslator(source=source_locale, target=target_locale)
    return translator.translate(query)


def translate_text(text: str, source_locale: str, target_locale: str) -> str:
    """
    Translate text from source_locale to target_locale via deep-translator.

    Generalized version supporting any language pair.
    Uses timeout, fallback, and circuit-breaker pattern for graceful degradation.

    Args:
        text: The text to translate
        source_locale: Source language code (e.g., "bs", "ru", "en")
        target_locale: Target language code (e.g., "ru", "en")

    Returns:
        Translated text, or original text on failure
    """
    if not text or not text.strip():
        return text

    if _CIRCUIT_BREAKER.is_open:
        logger.info(
            "Circuit open -- fallback to original text '%s' (breaker)",
            sanitize_query_for_log(text),
        )
        return text

    try:
        future = _EXECUTOR.submit(
            translate_cached_generic, text, source_locale, target_locale
        )
        result = future.result(timeout=TRANSLATION_TIMEOUT_SECONDS)
        if result:
            _CIRCUIT_BREAKER.record_success()
            logger.debug(
                "Translated '%s' (%s->%s) -> '%s'",
                sanitize_query_for_log(text),
                source_locale,
                target_locale,
                sanitize_query_for_log(result),
            )
            return result
    except (TimeoutError, RequestException, Exception) as e:
        _CIRCUIT_BREAKER.record_failure()
        logger.warning(
            "Translation failed for text '%s' (%s->%s): %s",
            sanitize_query_for_log(text),
            source_locale,
            target_locale,
            e,
        )

    logger.info(
        "Translation fallback: returning original text '%s'",
        sanitize_query_for_log(text),
    )
    return text
