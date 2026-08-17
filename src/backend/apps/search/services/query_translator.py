"""
Backward-compatibility re-exports from apps.core.services.translation.

All translation logic now lives in the shared module so that both the
search-side query translator and the bot's ad-creation translator share
a single circuit-breaker, timeout, and LRU cache.

This module exists solely for backward compatibility with callers and
tests that import from this path.
"""

from apps.core.services.translation import (
    GoogleTranslator,
    TRANSLATION_TIMEOUT_SECONDS,
    TranslationCircuitBreaker,
    _CIRCUIT_BREAKER,  # noqa: F401 — re-exported for test access
    invalidate_translation_cache,
    translate_cached,
    translate_cached_generic,
    translate_query_bs_to_ru,
    translate_text,
)

# ``translate_query`` is the legacy name used by search-side callers
# (see apps.search.views.search); it is an alias for ``translate_text``.
translate_query = translate_text

__all__ = [
    "GoogleTranslator",
    "TRANSLATION_TIMEOUT_SECONDS",
    "TranslationCircuitBreaker",
    "_CIRCUIT_BREAKER",
    "invalidate_translation_cache",
    "translate_cached",
    "translate_cached_generic",
    "translate_query",
    "translate_query_bs_to_ru",
    "translate_text",
]
