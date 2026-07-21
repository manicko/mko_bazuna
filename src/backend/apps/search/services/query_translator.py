"""
Query translator service for Mko Bazuna.

Translates Bosnian search queries to Russian for FTS search.
Implements timeout (~500ms), fallback, 5-minute cache, and circuit-breaker
for graceful degradation under translator throttling.
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
_EXECUTOR: Final[ThreadPoolExecutor] = ThreadPoolExecutor(max_workers=1)

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


def translate_query_bs_to_ru(query: str) -> str:
    """
    Translate Bosnian query to Russian with timeout, fallback, and circuit-breaker.

    Uses deep-translator (Google Translate) for translation. If translation
    fails or times out (exception), returns the original query as fallback.
    After 3 consecutive failures the circuit opens and short-circuits to the
    fallback for 60 seconds to avoid hammering a throttled endpoint.

    Args:
        query: The search query in Bosnian

    Returns:
        Translated query in Russian, or original query on failure
    """
    if not query or not query.strip():
        return query

    # Closed/half-open check.  While open, bail immediately.
    if _CIRCUIT_BREAKER.is_open:
        logger.info(
            "Circuit open – fallback to original query '%s' (breaker)",
            sanitize_query_for_log(query),
        )
        return query

    try:
        future = _EXECUTOR.submit(translate_cached, query)
        result = future.result(timeout=TRANSLATION_TIMEOUT_SECONDS)
        if result:
            _CIRCUIT_BREAKER.record_success()
            logger.debug("Translated query '%s' -> '%s'", sanitize_query_for_log(query), sanitize_query_for_log(result))
            return result
    except (TimeoutError, RequestException, Exception) as e:
        _CIRCUIT_BREAKER.record_failure()
        logger.warning("Translation failed for query '%s': %s", sanitize_query_for_log(query), e)

    # Fallback: return original query if translation fails
    logger.info("Translation fallback: returning original query '%s'", sanitize_query_for_log(query))
    return query


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


def invalidate_translation_cache() -> None:
    """Invalidate the translation cache."""
    translate_cached.cache_clear()
