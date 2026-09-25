"""Translation orchestration helpers for the Telegram bot ad-creation service.

Translates a text body to all target locales in parallel (bot -> backend
direction).
"""

import asyncio
import logging

from apps.core.services.translation import translate_text

logger = logging.getLogger(__name__)

__all__ = [
    "translate_all_languages",
]


async def translate_all_languages(
    text: str, target_locales: list[str]
) -> dict[str, str]:
    """Translate text to all target languages in parallel.

    Uses an ``asyncio.Semaphore`` (created inside the coroutine to stay
    compatible with ``asyncio_mode=strict``) to bound concurrent ``to_thread``
    dispatches, and ``return_exceptions=True`` on ``asyncio.gather`` so one
    locale's failure does not cancel the batch.  Falls back to the original
    text on any failure.

    Call sites pass ``LanguageLocale.values()`` (e.g. ``["ru", "bs", "en"]``)
    so the locale list is never a bare literal (QLT-002).

    Args:
        text: Source text to translate.
        target_locales: List of target locale codes (e.g. ['ru', 'bs', 'en']).

    Returns:
        Dict mapping locale codes to translated text. Falls back to original
        text on failure (via the shared service's graceful fallback).
    """

    _sem = asyncio.Semaphore(len(target_locales))

    async def _translate_one(loc: str) -> str:
        async with _sem:
            return await asyncio.to_thread(translate_text, text, "auto", loc)

    results = await asyncio.gather(
        *(_translate_one(loc) for loc in target_locales),
        return_exceptions=True,
    )

    translated: dict[str, str] = {}
    for loc, result in zip(target_locales, results, strict=True):
        if isinstance(result, Exception):
            logger.warning(
                "Translation for %s raised: %s — falling back to original",
                loc,
                result,
            )
            translated[loc] = text
        else:
            translated[loc] = result
    return translated
