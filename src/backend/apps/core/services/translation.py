"""
Shared translation service for Mko Bazuna.

Provides Google Translate-backed text translation with timeout (~500ms),
fallback, LRU cache, and circuit-breaker for graceful degradation under
translator throttling.

Used at publication time by the bot's ad-creation translator
(``telegram_bot.handlers.ad_create``). Search/alert query translation was
removed — the search path now uses language-aware per-language FTS vectors
with no external translation.

Log-field sanitisation (two helpers, two audiences — do not pick by name
similarity): seller-authored ad text logged by this module is redacted with
``redact_free_text`` (mask phones / e-mails / multi-word names for ANY free
text, no truncation) and then truncated with ``sanitize_query_for_log``
(control-character strip + ``_MAX_QUERY_LENGTH``). ``sanitize_query_for_log``
alone does NOT mask PII and must never be the sole sanitiser here;
``redact_search_query`` is the *search-query* sibling (it lowers nothing but
adds a 100-char cap) and is not the right audience for ad text. Neither helper
is modified here — ``apps/core/utils/sanitize.py`` is phase 08's.

Observability limit (deliberate, de-scoped follow-on — 09-API-017): the
counters below are created in this module, and this module is imported by the
``bot`` process (publish path, ``telegram_bot.services.ad_data.translation``)
and by the ``migrate`` one-shot (``backfill_translations``) — neither sets
``PROMETHEUS_MULTIPROC_DIR`` nor mounts its tmpfs. Only ``web`` sets that env
var (``docker-compose.yml``, pinned by ``src/backend/tests/
test_compose_contract.py``), and ``web`` never calls ``translate_text``. A
``prometheus_client`` counter is therefore process-local here and is NOT
exported by ``web``'s ``/metrics`` (whose ``ExportToDjangoView`` builds a fresh
registry populated solely by ``MultiProcessCollector``). The counters are
in-process bookkeeping — the increments are real and asserted by the unit
tests — and the open-breaker state remains observable in logs. Exporting them
requires a bot-side ``/metrics`` or a shared multiprocess volume: a
deployment-topology change of the same scale as §6.2's declined "one outbound
gateway", recorded here as a named, de-scoped follow-on and NOT built in this
change.
"""

import html
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from functools import lru_cache
from typing import Final

import httpx
from django.conf import settings
from prometheus_client import Counter, Gauge

from apps.core.utils.sanitize import redact_free_text, sanitize_query_for_log

# Module-level executor. Without a `with` block, a timed-out future is abandoned
# rather than waited on via shutdown(wait=True), so the timeout actually bounds latency.
# max_workers=4 allows the bot's 3-locale parallel gather to translate concurrently
# rather than serializing on a single worker.
_EXECUTOR: Final[ThreadPoolExecutor] = ThreadPoolExecutor(max_workers=4)

logger = logging.getLogger(__name__)

TRANSLATION_TIMEOUT_SECONDS: Final[float] = 0.5  # ~500ms timeout via exceptions

# Retry configuration: 2 total attempts (1 retry) with capped exponential backoff.
TRANSLATION_MAX_ATTEMPTS: Final[int] = 2
TRANSLATION_BACKOFF_BASE: Final[float] = 0.1  # 100ms base; backoff = 0.1 * 2**attempt

GOOGLE_TRANSLATE_V2_URL: Final[str] = "https://translation.googleapis.com/language/translate/v2"

# --- Observability (09-API-017). Process-local only — see the module docstring:
# the modules that import this one do not set PROMETHEUS_MULTIPROC_DIR, so these
# are NOT exported to web's /metrics. The increments are what the tests assert.
TRANSLATION_REQUESTS: Final = Counter(
    "translation_requests_total",
    "translate_text calls that reached the upstream attempt loop (non-empty input).",
)
TRANSLATION_FALLBACKS: Final = Counter(
    "translation_fallback_total",
    "translate_text calls that fell back to the unmodified source.",
)
TRANSLATION_CIRCUIT_OPEN: Final = Gauge(
    "translation_circuit_open",
    "1 when the translation circuit breaker is open, 0 otherwise.",
)

# Module-level httpx client with socket-level timeout enforcement.
# Sync httpx.Client is thread-safe for concurrent requests (connection pool
# is internally synchronized). Timeout truly interrupts hung upstream calls,
# reclaiming ThreadPoolExecutor workers instead of abandoning them (the
# orphaned-worker problem from deep_translator's requests.get without timeout).
_TRANSLATION_CLIENT: Final[httpx.Client] = httpx.Client(timeout=TRANSLATION_TIMEOUT_SECONDS)


def _safe_log_text(text: str) -> str:
    """Redact PII from seller-authored text, then truncate it for a log line.

    Redaction runs FIRST so a phone number that survives to the log is masked
    before truncation can split it; ``redact_free_text`` never lengthens, so the
    subsequent ``sanitize_query_for_log`` cap is the only length bound. Neither
    helper is modified (``sanitize.py`` is phase 08's).
    """
    return sanitize_query_for_log(redact_free_text(text))



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
        TRANSLATION_CIRCUIT_OPEN.set(0)

    def record_failure(self) -> None:
        """Call after a failed translation to increment the counter."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count == self.failure_threshold:
            TRANSLATION_CIRCUIT_OPEN.set(1)
            logger.warning(
                "Translation circuit OPEN after %d consecutive failures "
                "(cooldown=%.0fs)",
                self.failure_threshold,
                self.cooldown_seconds,
            )


# Module-level singleton.
_CIRCUIT_BREAKER: Final[TranslationCircuitBreaker] = TranslationCircuitBreaker()


@lru_cache(maxsize=256)
def translate_cached_generic(query: str, source_locale: str, target_locale: str) -> str:
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
    return _translate_via_api(query, source_locale, target_locale)


def _translate_via_api(query: str, source_locale: str, target_locale: str) -> str:
    """Translate text via Google Cloud Translation API v2 Basic.

    Raises httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException
    on failure -- the caller (``translate_text``) owns retry, circuit-breaker,
    and graceful fallback.

    On a malformed 200 response this may also raise ``json.JSONDecodeError``
    (unparseable body) or ``KeyError``/``ValueError`` (body missing the nested
    ``data["data"]["translations"][0]["translatedText"]`` key). These are also
    handled by ``translate_text`` as transport-failure-equivalent errors.
    """
    response = _TRANSLATION_CLIENT.post(
        GOOGLE_TRANSLATE_V2_URL,
        params={"key": settings.GOOGLE_TRANSLATE_API_KEY},
        json={"q": query, "source": source_locale, "target": target_locale},
    )
    response.raise_for_status()
    data = response.json()
    translated = data["data"]["translations"][0]["translatedText"]
    return html.unescape(translated)


def translate_text(text: str, source_locale: str, target_locale: str) -> str:
    """
    Translate text from source_locale to target_locale via the Google Cloud Translation API.

    Generalized version supporting any language pair.
    Uses timeout, fallback, circuit-breaker pattern for graceful degradation.

    Retries retryable failures (TimeoutError, httpx.TimeoutException, httpx.RequestError,
    httpx.HTTPStatusError on 429/5xx) up to ``TRANSLATION_MAX_ATTEMPTS`` with
    exponential backoff. Non-retryable HTTP errors (400/401/403) fall back
    immediately without retry.

    Args:
        text: The text to translate
        source_locale: Source language code (e.g., "bs", "ru", "en")
        target_locale: Target language code (e.g., "ru", "en")

    Returns:
        Translated text, or original text on failure
    """
    if not text or not text.strip():
        return text

    TRANSLATION_REQUESTS.inc()

    if _CIRCUIT_BREAKER.is_open:
        TRANSLATION_FALLBACKS.inc()
        logger.info(
            "Circuit open -- fallback to original text '%s' (breaker)",
            _safe_log_text(text),
        )
        return text

    for attempt in range(TRANSLATION_MAX_ATTEMPTS):
        try:
            future = _EXECUTOR.submit(
                translate_cached_generic, text, source_locale, target_locale
            )
            result = future.result(timeout=TRANSLATION_TIMEOUT_SECONDS)
            if result:
                _CIRCUIT_BREAKER.record_success()
                logger.debug(
                    "Translated '%s' (%s->%s) -> '%s'",
                    _safe_log_text(text),
                    source_locale,
                    target_locale,
                    _safe_log_text(result),
                )
                return result
            # Empty result — fall back without retrying
            break
        except (
            TimeoutError,
            httpx.TimeoutException,
            httpx.RequestError,
            json.JSONDecodeError,
            KeyError,
            ValueError,
        ) as e:
            # Transport-level failures — always retryable
            _CIRCUIT_BREAKER.record_failure()
            logger.warning(
                "Translation failed (attempt %d/%d) for text '%s' (%s->%s): %s",
                attempt + 1,
                TRANSLATION_MAX_ATTEMPTS,
                _safe_log_text(text),
                source_locale,
                target_locale,
                type(e).__name__,
            )
            if attempt + 1 < TRANSLATION_MAX_ATTEMPTS:
                time.sleep(TRANSLATION_BACKOFF_BASE * (2 ** attempt))
        except httpx.HTTPStatusError as e:
            # HTTP 4xx/5xx — retry only for 429/5xx, fall back on 400/401/403
            _CIRCUIT_BREAKER.record_failure()
            status = e.response.status_code
            if status in (429, 500, 502, 503, 504) and attempt + 1 < TRANSLATION_MAX_ATTEMPTS:
                logger.warning(
                    "Translation rate-limited/server error (attempt %d/%d, HTTP %d) "
                    "for text '%s' (%s->%s): %s",
                    attempt + 1,
                    TRANSLATION_MAX_ATTEMPTS,
                    status,
                    _safe_log_text(text),
                    source_locale,
                    target_locale,
                    str(e.request.url.copy_with(params={})),
                )
                time.sleep(TRANSLATION_BACKOFF_BASE * (2 ** attempt))
            else:
                logger.warning(
                    "Translation failed (HTTP %d) for text '%s' (%s->%s): %s",
                    status,
                    _safe_log_text(text),
                    source_locale,
                    target_locale,
                    str(e.request.url.copy_with(params={})),
                )
                break

    TRANSLATION_FALLBACKS.inc()
    logger.info(
        "Translation fallback: returning original text '%s'",
        _safe_log_text(text),
    )
    return text
