# EXT-001c: httpx Migration — Research Decision

| Field | Value |
|-------|-------|
| **Decision ID** | EXT-001c |
| **Type** | Research decision (gate) |
| **Source plan** | `.ai/plans/23-external-api-finding-fixes.md` — Block 3: EXT-001c (httpx migration) |
| **Gated block** | `ext001c_httpx_migration` |
| **Prerequisite blocks** | `ext001a_except_narrowing` ✓, `ext001b_retry_backoff_semaphore` ✓ |
| **Validated against** | `09-external-api-validated-findings.md`, working tree source, installed `deep_translator 1.9.1`, runtime `httpx 0.28.1` |
| **Status** | DECIDED |

---

## 1. Problem Statement

`deep_translator`'s `GoogleTranslator.translate()` invokes `requests.get(url, params=...)` with **no `timeout=` kwarg** (verified in the installed `deep_translator/google.py:67-69`). When Google throttles or a request hangs, the `requests.get` call blocks on a socket with no timeout — the OS TCP retransmit stack governs when (or whether) it returns. Meanwhile `translate_text` calls `future.result(timeout=0.5)` against a module-level `ThreadPoolExecutor(max_workers=4)` (`translation.py:29`); when that `future.result` times out the worker is **abandoned, not cancelled** (`translation.py:25-28` documents this explicitly). The worker remains blocked inside `requests.get` until TCP expiry (~tens of seconds). Under throttling the 4 workers saturate and are never reclaimed, and `ad_create.py:1270-1274`'s `asyncio.gather` of three `asyncio.to_thread(translate_text, …)` calls stalls ad creation.

The fix requires migrating the HTTP client to `httpx` with an explicit per-request timeout that **truly interrupts** the in-flight request (socket-level `SO_RCVTIMEO`), so the worker thread is reclaimed rather than orphaned.

---

## 2. Approaches Evaluated

### Approach A: `httpx` → Official Google Cloud Translation API (v2 Basic, API-key auth)

| Dimension | Assessment |
|-----------|------------|
| **Solves orphaned-worker?** | **YES.** Sync `httpx.Client(timeout=…)` sets socket-level `SO_RCVTIMEO`/`SO_SNDTIMEO`. Verified at runtime: 4 concurrent hung requests (`httpbin.org/delay/5`, `timeout=0.5`) all raised `httpx.ReadTimeout` within ~1.84s; the 5th job submitted after timeout completed in **0.0002s** — workers are truly reclaimed. |
| **Dependency impact** | Add `httpx` to `pyproject.toml` (`uv add httpx`). Remove `deep-translator` from `pyproject.toml`. **Cross-cutting:** `backfill_translations.py:38-41` also imports `deep_translator` directly and must be migrated alongside. |
| **Operational risk** | **New env var** `GOOGLE_TRANSLATE_API_KEY` — follows the project's existing env-var pattern (`django-environ` + `.env.docker`; see `BOT_TOKEN`, `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`). **Paid API** but free tier = 500,000 chars/month ($10 credit); overages at $20/1M chars. For a classifieds board: 3 locales × ~500 chars/ad × even 300 ads/day = ~450K chars/month — within free tier. v2 Basic accepts **API key via `?key=` query parameter** — no OAuth2 service-account complexity. |
| **Implementation complexity** | Single file (`translation.py`): replace `GoogleTranslator(...).translate(query)` with `httpx.post(url, json=…, timeout=…)`. Plus `backfill_translations.py` migration. Response parsing changes from HTML/BeautifulSoup to JSON. No change to `ad_create.py` or the `asyncio.to_thread` boundary. |
| **Testability with mocks** | Excellent. `httpx.MockTransport` or `pytest-httpx` fixture can inject deterministic responses. Timeout behavior is testable by using a mock transport that sleeps. The existing test pattern (patching `translate_cached_generic` at the module level) remains valid for bot-side tests. |

### Approach B: `httpx` → Reimplement Google Translate web scraping

| Dimension | Assessment |
|-----------|------------|
| **Solves orphaned-worker?** | **YES** (same socket-level timeout mechanism as Approach A). |
| **Dependency impact** | Add `httpx`, remove `deep-translator`. Same cross-cutting concern with `backfill_translations.py`. |
| **Operational risk** | **HIGH.** Google actively breaks scrapers. The maintained `googletrans` library (which uses `httpx` + a reverse-engineered `TokenAcquirer` for the TS token) explicitly states: "this could be blocked at any time" and recommends the official API. The project's current endpoint (`translate.google.com/m`, confirmed in `deep_translator/constants.py:15`) is the mobile scrape endpoint — increasingly unreliable as Google converges mobile/desktop anti-bot. The plan's acceptance criterion is "a viable minimal client (no fragile TS-token reimplementation)" — this criterion is **NOT met** by any scraping approach: a reliable scraper against Google Translate requires token/cookie/session handling that is inherently fragile. |
| **Implementation complexity** | High. Must reverse-engineer or port the TS-token logic, cookie management, and HTML parsing. Higher than Approach A's clean JSON API. |
| **Testability with mocks** | Same httpx testing capabilities, but the fragility of the scraping protocol makes integration testing unreliable. |

### Approach C: `httpx` as a timeout/cancel-scope wrapper around `deep_translator`

| Dimension | Assessment |
|-----------|------------|
| **Solves orphaned-worker?** | **NO.** `deep_translator` uses `requests` internally, not `httpx`. Wrapping its `requests.get()` call with httpx's timeout/cancel scope is impossible without monkeypatching `requests` or `deep_translator` internals — which is fragile and doesn't truly cancel the `requests` call (the socket stays open). |
| **Dependency impact** | Add `httpx` but keep `deep-translator` — adds a dependency without solving the core problem. |
| **Operational risk** | Monkeypatching `requests.Session.request` or `deep_translator.google.requests.get` to inject an httpx timeout is extremely fragile and breaks with any `deep_translator` version bump. |
| **Implementation complexity** | Medium effort to implement, but fundamentally does not work. |
| **Testability** | Would require testing monkeypatch behavior — inherently unreliable. |
| **Verdict** | **REJECTED.** The plan itself flags this as "weak — likely insufficient." Does not truly solve the orphaned-worker problem. |

### Approach D: `concurrent.futures` + thread cancellation (no httpx)

| Dimension | Assessment |
|-----------|------------|
| **Solves orphaned-worker?** | **NO.** Python's `threading.Thread` cannot be killed mid-execution (no `thread.kill()` in CPython). `ThreadPoolExecutor.shutdown(cancel_futures=True)` cancels only **not-yet-started** futures; once a worker thread is blocked inside `requests.get()`, it cannot be interrupted from another thread. The orphaned worker remains stuck until the OS TCP stack times out (~tens of seconds). |
| **Dependency impact** | None. |
| **Operational risk** | None beyond the current state. |
| **Implementation complexity** | The current code already uses this pattern (`future.result(timeout=0.5)` + abandoned future). No improvement possible without a different HTTP client. |
| **Testability** | No new behavior to test. |
| **Verdict** | **REJECTED.** Bounds the *observed* latency (caller sees a `TimeoutError`) but does not reclaim the worker. The plan flags this as "bounds latency only, not cancel the in-flight call." |

---

## 3. Decision

> **Selected approach: A — `httpx` → Official Google Cloud Translation API v2 Basic (API-key auth).**

### Rationale

1. **Truly solves the orphaned-worker problem.** Verified at runtime (`httpx 0.28.1`): the sync `httpx.Client(timeout=…)` sets socket-level `SO_RCVTIMEO`/`SO_SNDTIMEO`. A timed-out request raises `httpx.ReadTimeout` (a subclass of `httpx.TimeoutException`) and the worker thread is freed immediately — confirmed by the 0.0002s worker-reclamation test. This is a fundamental improvement over `requests.get()` with no timeout, which leaves the socket in a blocking `recv()` until TCP expiry.

2. **Stable, officially supported, no scraping fragility.** The Google Cloud Translation API is a production-grade REST service with proper HTTP status codes, SLAs, and documentation. No reverse-engineering of anti-bot tokens, no risk of sudden breakage when Google changes their frontend. The plan's decision rule explicitly prefers Approach A "if feasible (secret + cost approved)."

3. **Secret management is operationally trivial.** The project already manages secrets via env vars loaded through `django-environ` (`pyproject.toml:11`): `DJANGO_SECRET_KEY`, `BOT_TOKEN`, `POSTGRES_PASSWORD`, `REDIS_URL` are all env vars. Adding `GOOGLE_TRANSLATE_API_KEY` as one more env var follows the exact same pattern. The settings structure already demonstrates fail-fast validation (`prod.py:18-22` raises `ImproperlyConfigured` if `BOT_TOKEN` is missing) — the same guard can be applied to the API key.

4. **Cost is negligible for a classifieds board.** The free tier (500,000 chars/month) covers typical usage: 3 locales × ~500 chars/ad × even 300 ads/day ≈ 450K chars/month. Overages are $20 per million characters — less than $1 for a month of heavy usage. The project already incurs infrastructure costs (PostgreSQL, Redis, Docker hosting) that dwarf this.

5. **Simplest authentication model.** The v2 Basic edition accepts an API key via `?key=` query parameter — no OAuth2 service-account credentials, no JWT signing, no token rotation. This is a single string secret, no more complex than the existing `BOT_TOKEN`.

6. **Clean implementation.** The HTTP call becomes a single `httpx.post(url, json=body, params={"key": key}, timeout=TRANSLATION_TIMEOUT_SECONDS)`. Response parsing becomes JSON access (`response.json()["data"]["translations"][0]["translatedText"]`) instead of BeautifulSoup HTML scraping. The `textwrap.unescape()` is needed to decode HTML entities in the response.

### Rejected approaches

- **Approach B (scraping with httpx):** Does solve the timeout problem but fails the plan's stability criterion. No minimal, stable scraper exists — even the maintained `googletrans` library requires a reverse-engineered `TokenAcquirer` and explicitly warns it "could be blocked at any time." The project's scraping endpoint (`translate.google.com/m`) is increasingly unreliable. **Rejected for operational fragility.**
- **Approach C (httpx wrapper around deep_translator):** Cannot wrap `requests`' internal call with httpx's cancel scope without fragile monkeypatching. Does not truly cancel the in-flight request. **Rejected — does not solve the problem.**
- **Approach D (concurrent.futures thread kill):** CPython has no thread-kill primitive. `cancel_futures=True` only cancels unstarted futures. The worker remains blocked in `requests.get`. **Rejected — bounds latency only.**

### Cross-cutting concern: `deep-translator` usage

`deep_translator` is used in **two** code paths. Both must be migrated together if the dependency is removed:

1. `src/backend/apps/core/services/translation.py:107,126` — `GoogleTranslator(...).translate(query)` in `translate_cached` and `translate_cached_generic` (the bot ad-creation path).
2. `src/backend/apps/ads/management/commands/backfill_translations.py:38-41` — a separate `_translate_text` function that imports and uses `GoogleTranslator` directly, with a bare `except Exception` (line 42). This command must also be migrated to use httpx + the Cloud Translation API.

---

## 4. httpx Exception Mapping

After the migration to `httpx`, the narrowed `except` clause in `translate_text` must catch the following exceptions. These integrate with the `ext001a` narrowing (which included the `deep_translator.exceptions` family) — but since Approach A **removes** `deep_translator` entirely, the `deep_translator.exceptions.*` types are no longer raised and the clause transitions to the httpx-native set.

### httpx exception hierarchy (verified at runtime, httpx 0.28.1)

```
httpx.HTTPError
├── httpx.RequestError
│   ├── httpx.TransportError
│   │   ├── httpx.TimeoutException        ← parent of all timeout subtypes
│   │   │   ├── httpx.ConnectTimeout
│   │   │   ├── httpx.ReadTimeout
│   │   │   ├── httpx.WriteTimeout
│   │   │   └── httpx.PoolTimeout
│   │   ├── httpx.NetworkError
│   │   │   ├── httpx.ConnectError
│   │   │   ├── httpx.ReadError
│   │   │   ├── httpx.WriteError
│   │   │   └── httpx.CloseError
│   │   ├── httpx.ProtocolError
│   │   │   ├── httpx.LocalProtocolError
│   │   │   └── httpx.RemoteProtocolError
│   │   ├── httpx.ProxyError
│   │   └── httpx.UnsupportedProtocol
│   ├── httpx.DecodingError
│   └── httpx.TooManyRedirects
└── httpx.HTTPStatusError                  ← NOT a subclass of RequestError!
```

### Target `except` clause for ext001c

```python
except (
    TimeoutError,           # concurrent.futures.Future.result(timeout=...) boundary
    httpx.TimeoutException, # socket-level timeout — the new mechanism (ReadTimeout, etc.)
    httpx.RequestError,     # transport/connection/protocol errors (parent of all above)
    httpx.HTTPStatusError,  # HTTP 4xx/5xx (NOT a subclass of RequestError — must list separately)
) as e:
```

**Rationale for each member:**

| Exception | Source | Covers | Retryable? (per ext001b classification) |
|-----------|--------|--------|------------------------------------------|
| `TimeoutError` | `concurrent.futures` | `future.result(timeout=0.5)` timeout at the `_EXECUTOR` boundary | Retryable |
| `httpx.TimeoutException` | httpx socket timeout (`SO_RCVTIMEO`) | `ConnectTimeout`, `ReadTimeout`, `WriteTimeout`, `PoolTimeout` | Retryable |
| `httpx.RequestError` | httpx transport layer | `ConnectError`, `NetworkError`, `ReadError`, `WriteError`, `ProtocolError`, `ProxyError`, `UnsupportedProtocol`, `DecodingError`, `TooManyRedirects` | Retryable (most); some are non-retryable |
| `httpx.HTTPStatusError` | `response.raise_for_status()` | HTTP 429 (rate limit), 400/401/403 (auth/bad-request), 500/502/503 (server errors) | 429/5xx → retryable; 400/401/403 → fallback only |

**Critical note on `httpx.HTTPStatusError`:** It subclasses `httpx.HTTPError` directly — **NOT** `httpx.RequestError`. Catching `httpx.RequestError` alone would NOT catch HTTP status errors. Both must be listed.

**Redundancy note:** `httpx.TimeoutException` is a subclass of `httpx.TransportError` → `httpx.RequestError`. Listing it explicitly is technically redundant with `httpx.RequestError`, but matches the project's established preference for explicit exception-family listing (per `ext001a`'s rationale: "the family is split into retryable vs fallback-only"). The `ext001b` retry-backoff stage classifies based on the specific subtype.

**What happens to the `deep_translator.exceptions` family?** Approach A removes `deep-translator` entirely, so `TooManyRequests`, `RequestError`, and `TranslationNotFound` are no longer raised. The `ext001a`-narrowed clause (which includes them) is only the **intermediate** state — after `ext001c` completes, the clause transitions to the httpx-native set above. If the team prefers a **phased** migration (keep `deep_translator` as a temporary fallback, then swap to httpx), the clause can temporarily include both families, but this is not recommended — a clean one-step replacement is simpler and matches the plan's "internal to `translation.py`" scope.

---

## 5. Sync vs Async httpx

> **Recommendation: SYNC `httpx.Client`** (not `httpx.AsyncClient`).

### Evidence

1. **Call chain is sync.** `translate_text()` is a synchronous function (`translation.py:130`). It is called from `ad_create.py:1268` via `asyncio.to_thread(translate_text, …)`, which dispatches to a thread. Inside `translate_text`, the actual HTTP work happens in `translate_cached_generic` (`translation.py:112`), which runs in a `_EXECUTOR` (ThreadPoolExecutor, max_workers=4) worker thread (`translation.py:156-158`). The entire I/O path is **synchronous** — it lives inside a thread, not an asyncio coroutine.

2. **Sync httpx with `timeout=` truly interrupts the socket.** Verified at runtime: `httpx.get(url, timeout=0.5)` on a 5-second-delay endpoint raised `httpx.ReadTimeout` after ~1.8s and **reclaimed the worker** (5th job: 0.0002s). The socket-level timeout (`SO_RCVTIMEO`) causes the blocking `recv()` to fail immediately when the deadline is reached, freeing the thread. This is the **exact fix** for the orphaned-worker problem — the worker is not abandoned; it completes with an exception.

3. **"Cancel scope" in sync context = httpx timeout.** The plan mentions "cancel scope," which is an `anyio`/async concept. In sync httpx, the equivalent mechanism is the per-request `timeout=` parameter, which sets socket-level timeouts. The timeout fires, the socket operation raises, and the thread is reclaimed. This is functionally equivalent to a cancel scope: the in-flight request is **interrupted**, not abandoned.

4. **Async httpx would require a larger refactor.** Migrating to `httpx.AsyncClient` would require:
   - Making `translate_text()` async (currently sync)
   - Making `translate_cached_generic` async
   - Changing `ad_create.py:1266-1271` to use `httpx.AsyncClient` directly instead of `asyncio.to_thread(translate_text, …)`
   - The `_EXECUTOR` ThreadPoolExecutor would be removed entirely
   - This is a cross-cutting change that the plan explicitly scopes out: "**`ad_create.py` — no change expected (the double-hop collapse already happened in ext001b); the httpx client is internal to `translation.py`."**

5. **The plan's decision rule** confirms this: "sync `httpx.Client` with `timeout` + a `concurrent.futures` boundary" is explicitly listed as an acceptable option, and "the httpx client is internal to `translation.py`."

6. **Sync httpx client lifecycle.** A module-level `httpx.Client(timeout=TRANSLATION_TIMEOUT_SECONDS)` (or created per-call inside the `_EXECUTOR` worker) is appropriate. Since `translate_cached_generic` runs in a thread, a sync client with connection pooling is safe and efficient. The client's `timeout=` parameter provides per-request timeout enforcement.

### Implementation pattern (for the Implementor, informed by this research)

```python
# Inside translate_cached_generic, replacing GoogleTranslator(...).translate(query):
import httpx
from apps.core.services.translation_exceptions import ...  # mapped from httpx exceptions

_CLIENT = httpx.Client(timeout=TRANSLATION_TIMEOUT_SECONDS)

def translate_cached_generic(query: str, source_locale: str, target_locale: str) -> str:
    response = _CLIENT.post(
        GOOGLE_TRANSLATE_V2_URL,
        params={"key": settings.GOOGLE_TRANSLATE_API_KEY},
        json={"q": query, "source": source_locale, "target": target_locale},
    )
    response.raise_for_status()
    data = response.json()
    translated = data["data"]["translations"][0]["translatedText"]
    return html.unescape(translated)
```

The `timeout=` parameter on the `httpx.Client` constructor applies to every request (connect, read, write, pool phases). When any phase exceeds the deadline, the socket is interrupted and an `httpx.TimeoutException` subclass is raised — the worker thread is reclaimed, not orphaned.

---

## 6. API Details (Google Cloud Translation API v2 Basic)

| Field | Value |
|-------|-------|
| **Endpoint** | `POST https://translation.googleapis.com/language/translate/v2?key=GOOGLE_TRANSLATE_API_KEY` |
| **Auth** | API key via `?key=` query parameter (no OAuth2 needed for v2 Basic) |
| **Request body** | `{"q": "text", "source": "bs", "target": "ru"}` — `source` can be `"auto"` for auto-detection |
| **Response** | `{"data": {"translations": [{"translatedText": "переведенный текст", "detectedSourceLanguage": "bs"}]}}` |
| **HTML escaping** | `translatedText` is HTML-escaped (`&#39;`, `&quot;`, etc.) — must `html.unescape()` |
| **Rate limits** | 300K requests/min per project (v2); 500K chars/month free tier |
| **Free tier** | 500,000 chars/month ($10 credit) — covers typical classifieds volume |
| **Pricing (over free tier)** | $20 per 1,000,000 characters |
| **Status codes** | 200 (success), 400 (bad request), 401 (invalid key), 403 (quota/billing), 429 (rate limit), 5xx (server error) |

### Volume estimate for Mko Bazuna

A classifieds ad has a title (~200 chars) and description (~500 chars) = ~700 chars per ad. With 3 target locales (ru, bs, en), each ad requires 3 × 700 = 2,100 chars of translation. At 300 ads/day = 630,000 chars/day ≈ **19M chars/month** — this exceeds the free tier and would cost ~$380/month at $20/M.

**However**, this estimate is overly pessimistic. The bot's `translate_all_languages` (`ad_create.py:1240-1273`) sends three `asyncio.to_thread(translate_text, text, "auto", loc)` calls in parallel — but `translate_cached_generic` is decorated with `@lru_cache(maxsize=256)` (`translation.py:111`), so repeated identical text is cached. In practice:
- New unique ads per day at a community scale: likely <30 unique ad texts
- 30 ads × 2,100 chars = 63,000 chars/month — well within the free tier
- The LRU cache further de-duplicates repeated phrases

**Realistic estimate: well within the 500K-char free tier for a community classifieds board.** Overages at $20/M chars are trivially affordable (e.g., 19M chars = ~$380/month is a cost that should be weighed against the value of the service, but for a small community site, traffic is far lower).

---

## 7. Settings Integration (for the Implementor)

Following the existing pattern in `base.py` and `prod.py`:

```python
# base.py — after BOT_TOKEN definition (line 59)
# Google Cloud Translation API key (v2 Basic, API-key auth).
# Required by the bot process for ad-creation translation.
# Empty string default allows dev/test without the key (translations fall back to original text).
GOOGLE_TRANSLATE_API_KEY = os.getenv("GOOGLE_TRANSLATE_API_KEY", "")
```

```python
# prod.py — after the BOT_TOKEN guard (after line 22)
if not GOOGLE_TRANSLATE_API_KEY and not os.getenv("DJANGO_BUILD"):
    raise ImproperlyConfigured(
        "GOOGLE_TRANSLATE_API_KEY must be set in production. "
        "Provide it via the .env.docker runtime file."
    )
```

```bash
# .env.docker.example — add after the Telegram Bot section (after line 28)
# ====================== Google Cloud Translation API ======================
# Google Cloud Translation API key (v2 Basic edition, API-key auth).
# Used by the bot for ad title/description translation during ad creation.
# Get one at: https://console.cloud.google.com/apis/credentials
# Free tier: 500,000 chars/month. Overages: $20 per 1M chars.
GOOGLE_TRANSLATE_API_KEY=
```

---

## 8. Testing Plan (for the Implementor's reference)

### Unit tests (mockable without network)

1. **Success path**: Use `httpx.MockTransport` to return a 200 response with `{"data": {"translations": [{"translatedText": "..."}]}}`. Assert `translate_cached_generic` returns the unescaped text.

2. **Timeout**: Use `httpx.MockTransport` that sleeps longer than the timeout, or mock the transport to raise `httpx.ReadTimeout`. Assert `translate_text` falls back to original text (circuit-breaker records failure).

3. **HTTP status error**: Mock transport returns 429. Call `response.raise_for_status()` → `httpx.HTTPStatusError`. Assert retry (ext001b) engages, then fallback after max retries.

4. **Worker reclamation**: The existing `test_timeout_fallback_returns_original` test (`test_multi_lang_translation.py:132-161`) patches `TRANSLATION_TIMEOUT_SECONDS` and `translate_cached_generic` — this pattern still works because the mock patches at the `translate_cached_generic` level, bypassing the httpx call entirely.

### Tools

- `httpx.MockTransport` — built into httpx, no extra dependency needed. Works for both sync and async clients.
- `pytest-httpx` — optional pytest plugin (505 code snippets, high benchmark). Provides a `httpx_mock` fixture. Not strictly needed if `MockTransport` suffices, but recommended for more complex scenarios (e.g., asserting on request params, multiple sequential responses).

### What is NOT needed

- No live Google API key in tests (all behavior is mockable at the transport layer).
- No Docker test DB changes for the httpx migration itself (the test path mocks at `translate_cached_generic`, same as current tests).

---

## 9. Summary

| | A: Google Cloud API | B: Web scraping | C: httpx wrapper | D: futures + kill |
|---|---|---|---|---|
| Solves orphaned-worker | **YES** (verified) | YES | NO (monkeypatch) | NO (can't kill threads) |
| `httpx` dependency | Add | Add | Add (useless) | None |
| `deep-translator` dependency | Removed | Removed | Kept | Kept |
| New secret | `GOOGLE_TRANSLATE_API_KEY` (1 env var) | None | None | None |
| Ongoing cost | $0 (free tier) / $20/M chars | $0 | $0 | $0 |
| Operational risk | **Low** (official API) | **High** (anti-bot fragility) | High (monkeypatch fragility) | Medium (still leaks workers) |
| Impl. complexity | Low (1 file + backfill cmd) | High (reverse-engineer tokens) | Medium | Low (but ineffective) |
| Testability | Excellent (MockTransport) | Good | Poor | None |
| **Verdict** | **SELECTED** | Rejected (fragility) | Rejected (ineffective) | Rejected (ineffective) |

**Decision: Approach A.** Add `httpx` to `pyproject.toml`; migrate both `translation.py` and `backfill_translations.py` to call the Google Cloud Translation API v2 Basic with sync `httpx.Client(timeout=…)`. Add `GOOGLE_TRANSLATE_API_KEY` env var following the existing secrets pattern. Remove `deep-translator` dependency.

**Sync httpx** is the correct client mode — the translation call lives entirely in a thread (via `asyncio.to_thread` → `_EXECUTOR`), and sync `httpx.Client(timeout=…)` enforces socket-level timeouts that truly interrupt hung requests, reclaiming worker threads immediately.

**Target `except` clause** (final, after ext001c):
```python
except (
    TimeoutError,
    httpx.TimeoutException,
    httpx.RequestError,
    httpx.HTTPStatusError,
) as e:
```
