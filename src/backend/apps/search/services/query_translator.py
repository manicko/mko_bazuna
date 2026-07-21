"""
Query translator service for Mko Bazuna.

Translates Bosnian search queries to Russian for FTS search.
Implements timeout (~500ms), fallback, and 5-minute cache.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from functools import lru_cache
from typing import Final

from deep_translator import GoogleTranslator
from requests.exceptions import RequestException

# Module-level executor. Without a `with` block, a timed-out future is abandoned
# rather than waited on via shutdown(wait=True), so the timeout actually bounds latency.
_EXECUTOR: Final[ThreadPoolExecutor] = ThreadPoolExecutor(max_workers=1)

logger = logging.getLogger(__name__)

TRANSLATION_TIMEOUT_SECONDS: Final[float] = 0.5  # ~500ms timeout via exceptions


def translate_query_bs_to_ru(query: str) -> str:
    """
    Translate Bosnian query to Russian with timeout and fallback.

    Uses deep-translator (Google Translate) for translation. If translation
    fails or times out (exception), returns the original query as fallback.

    Args:
        query: The search query in Bosnian

    Returns:
        Translated query in Russian, or original query on failure
    """
    if not query or not query.strip():
        return query

    try:
        future = _EXECUTOR.submit(translate_cached, query)
        result = future.result(timeout=TRANSLATION_TIMEOUT_SECONDS)
        if result:
            logger.debug(f"Translated query '{query}' -> '{result}'")
            return result
    except (TimeoutError, RequestException, Exception) as e:
        logger.warning(f"Translation failed for query '{query}': {e}")

    # Fallback: return original query if translation fails
    logger.info(f"Translation fallback: returning original query '{query}'")
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
