# Phase 09 Audit Findings — External Integrations & API (VALIDATED)

**Executor:** audit-executor
**Template:** `.kilo/commands/audit/phases/09-audit-external-api.md`
**Status:** complete
**Validated:** yes

> **Validator scope note:** This report validates the findings in `09-external-api/findings.md` only, against the current working tree. Per the phase's own status (`Validated: no (static analysis only; Docker runtime not executed this phase)`), runtime verification (§4 matrix) was **not** re-executed in this pass — no test DB or live proxy was stood up. Each finding was instead **independently reproduced via targeted `grep` + exact source-line reads**, and cross-checked against the phase-09 audit template (`.kilo/commands/audit/phases/09-audit-external-api.md`) and the referenced spec dimensions §5(a–h), §7, §8. Line references in the source findings were all spot-checked at the cited offsets and confirmed live (see per-finding Validation Notes). No source code was modified.

Audit scope: boundary-to-outside-world seams for the dual-process Django app (web gunicorn + aiogram bot, shared PostgreSQL 18). Bot/async runtime (`src/telegram_bot/main.py`, aiogram 3.x polling); async↔sync bridge (`asgiref.sync_to_async`/`asyncio.to_thread`); Telegram gateway (polling, no webhook — `BOT_TOKEN` from env); external translation client (`src/backend/apps/core/services/translation.py` → `deep_translator` `GoogleTranslator`); login-token deep-link flow (`src/backend/apps/users/views/consent.py` + `src/telegram_bot/handlers/login.py`); API surface (`src/backend/apps/moderation/views/api_bulk.py`, cabinet, search, browse); reverse proxy/TLS (`docker/nginx/nginx.conf`, `docker/nginx/nginx.dev.conf`); settings (`src/backend/config/settings/{base,dev,prod,test}.py`).

---

## Findings

### EXT-001: Translation client has no retry/backoff, leaks abandoned worker threads, and masks errors with a broad `except Exception`

| Field | Value |
|-------|-------|
| **ID** | EXT-001 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/core/services/translation.py` (translation client), `src/telegram_bot/handlers/ad_create.py:1270-1274` (caller) |
| **Classification** | advisory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Reproduced verbatim against the working tree. All cited lines confirmed live:
>   - `translation.py:29` — `_EXECUTOR: Final[ThreadPoolExecutor] = ThreadPoolExecutor(max_workers=4)` (module-level, no `with` block).
>   - `translation.py:25-28` — comment explicitly acknowledges the abandonment: "a timed-out future is abandoned rather than waited on via shutdown".
>   - `translation.py:33` — `TRANSLATION_TIMEOUT_SECONDS: Final[float] = 0.5`.
>   - `translation.py:156-159` — single attempt: `future = _EXECUTOR.submit(translate_cached_generic, ...)` then `result = future.result(timeout=TRANSLATION_TIMEOUT_SECONDS)`; **no retry loop, no backoff**.
>   - `translation.py:170` — `except (TimeoutError, RequestException, Exception) as e:` — the `Exception` term makes this a catch-all.
>   - `translation.py:107,126` — `GoogleTranslator(source=..., target=...).translate(query)`.
>   - `ad_create.py:1270-1274` — `results = await asyncio.gather(*[asyncio.to_thread(translate_text, text, "auto", loc) for loc in target_locales])` (the caller; three `asyncio.to_thread` calls → double-hop into `_EXECUTOR`).
>   - `deep_translator` runtime source inspected (`uv run python` → `deep_translator/google.py`): `translate()` calls `requests.get(self._base_url, params=..., proxies=self.proxies)` with **no `timeout=` kwarg**, so the worker thread is bound to an unbounded `requests` call until TCP retransmit/idle expiry — confirmed the worker-blocked-under-throttling stall claim.
> - **Spec basis:** §5(c) "Timeout, retry/backoff, circuit-breaker, fallback" — retry/backoff is explicitly required and is the sole missing resilience primitive (timeout/fallback/circuit-breaker are present). The deviation is real.
> - **Evidence-quality note (rollout nuance):** The recommendation to "narrow the `except` to `TimeoutError, RequestException`" is correct in *intent* (let programming errors propagate), but the deep_translator exception hierarchy was verified: `TooManyRequests`, `RequestError`, and `TranslationNotFound` all subclass only `Exception` — **not** `requests.exceptions.RequestException`. Narrowing to `(TimeoutError, RequestException)` would therefore *exclude* the actual retryable translation-protocol errors (Google 429, non-200 responses, no-element-found) and let them propagate to `translate_all_languages`' `asyncio.gather` → a single bad translation would crash ad creation instead of falling back. A correct narrowing must explicitly include `deep_translator.exceptions.{TooManyRequests, RequestError, TranslationNotFound}` (retry/backoff the 429/RequestError subset, fall back on TranslationNotFound). See Warnings.
> - **See also:** §5(c) (retry/backoff requirement); §7 "Translator returns empty/garbage → ad-creation fallback" (the fallback path exists but retry does not).

**Description:** The shared translation client (`apps.core.services.translation`) provides a 500 ms timeout, an in-process circuit-breaker, an LRU cache, and a fallback-to-original-text path — but it is **missing retry/backoff**, which §5(c) explicitly requires. `translate_text` makes a single attempt: on `TimeoutError`/`RequestException` it records one circuit-breaker failure and returns the original text with no retry. The 500 ms bound is enforced by `future.result(timeout=TRANSLATION_TIMEOUT_SECONDS)` (`translation.py:156-159`) against a module-level `ThreadPoolExecutor(max_workers=4)` (`translation.py:29`); when that timeout fires the **worker thread is abandoned and never cancelled** (the module comment at `translation.py:25-28` documents this explicitly), and `GoogleTranslator.translate()` (deep-translator) runs its underlying `requests` call with **no HTTP-level timeout**, so a hung upstream keeps the worker blocked until TCP idle/retransmit expiry (~tens of seconds). Under translator throttling the 4 workers saturate and are never reclaimed; once saturated, `translate_text` can no longer dispatch and the bot's `translate_all_languages` gather (`ad_create.py:1270-1274`, three `asyncio.to_thread` calls) stalls, blocking ad creation. Separately, `except (TimeoutError, RequestException, Exception)` at `translation.py:170` is a catch-all that treats programming errors (e.g. deep-translator `AttributeError`/`KeyError`) as transient translation failures and silently falls back, masking bugs and defeating observability.

**Evidence:**
- `src/backend/apps/core/services/translation.py:29` — `_EXECUTOR: Final[ThreadPoolExecutor] = ThreadPoolExecutor(max_workers=4)`
- `src/backend/apps/core/services/translation.py:25-28` — comment acknowledges abandoned futures ("a timed-out future is abandoned rather than waited on via shutdown")
- `src/backend/apps/core/services/translation.py:155-159` — single attempt; `future.result(timeout=0.5)`; no retry/backoff
- `src/backend/apps/core/services/translation.py:170` — `except (TimeoutError, RequestException, Exception) as e:` catch-all
- `src/backend/apps/core/services/translation.py:107,126` — `GoogleTranslator(...).translate(query)` (deep-translator passes no `timeout`; underlying `requests` has no timeout — verified in installed `deep_translator/google.py`)
- `src/telegram_bot/handlers/ad_create.py:1270-1274` — `asyncio.gather(*[asyncio.to_thread(translate_text, text, "auto", loc) for loc in target_locales])`

**Consequence:** Under Google/translator throttling or a hung upstream, the 4 worker threads saturate and are never reclaimed; once saturated, every `translate_text` dispatch stalls and ad creation effectively hangs (bot FSM blocked on `translate_all_languages`). The catch-all `except Exception` masks non-transient deep-translator/programming errors as benign fallbacks, defeating observability and potentially hiding data-corruption-class bugs (e.g. a malformed `GoogleTranslator` return producing garbage stored as the ad's translated field rather than failing fast).

**Recommendation:** [BEST-PRACTICE] Add bounded retry with capped exponential backoff (1–2 attempts) at the `translate_text` layer; collapse the redundant `asyncio.to_thread`→executor double-hop into a single concurrency scope bounded by a `Semaphore` so saturated throttling degrades to fallback instead of stalling; narrow the `except` to `TimeoutError, RequestException` *plus* `deep_translator.exceptions.{TooManyRequests, RequestError, TranslationNotFound}` so non-transient programming errors propagate while retryable protocol errors fall back/retried; migrate off deep-translator's un-timeout'd `requests` to `httpx` with an explicit per-request timeout + cancel scope so a timed-out call is actually cancelled rather than leaving an orphaned worker. Effort: medium. Priority: recommended.

---

### EXT-002: Publish-time alert delivery bridge spawns a daemon thread + fresh Bot/session per message with no retry on transient Telegram errors

| Field | Value |
|-------|-------|
| **ID** | EXT-002 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/search/services/immediate_alerts.py` (web→async bridge), `src/backend/apps/moderation/signals.py:56-76` (trigger) |
| **Classification** | advisory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Reproduced verbatim. `IMMEDIATE_ALERTS_ENABLED` defaults to OFF (`base.py:243` → `os.getenv("IMMEDIATE_ALERTS_ENABLED", "false")`), so the bridge is inert in the default deploy — but the design flaws are real once enabled. Confirmed:
>   - `moderation/signals.py:56-76` — `deliver_immediate_alerts_on_publish` `post_save` receiver; guarded by `getattr(settings, "IMMEDIATE_ALERTS_ENABLED", False)` (line 65); `transaction.on_commit(_deliver)` at line 76.
>   - `immediate_alerts.py:87-93` — `thread = threading.Thread(target=_run_send, args=(payloads,), daemon=True, name="immediate-alert-send"); thread.start()` — one daemon thread **per published ad**, started from the sync `on_commit` callback.
>   - `immediate_alerts.py:164-168` — `_run_send` wraps `asyncio.run(...)` in `except Exception as exc:` (bare catch-all).
>   - `immediate_alerts.py:172-193` — `_send_payloads` builds `Bot(token=bot_token)` (line 178) **inside** the per-message `_send`, i.e. a fresh `aiohttp` session/connection pool per recipient.
>   - `immediate_alerts.py:174` — `sem = asyncio.Semaphore(_SEND_CONCURRENCY)` (line 38 = `_SEND_CONCURRENCY = 10`) is created **inside** `_send_payloads`, i.e. per-thread (per published ad) — NOT a process-global bound. A burst of N published ads → N threads × up to 10 concurrent sends = unbounded.
>   - `immediate_alerts.py:186` — `except (TelegramBadRequest, TelegramForbiddenError) as exc:` — only these two Telegram exceptions are handled per-message; network reset / 5xx / 429-with-`retry_after` fall through to the bare `except Exception` at line 168 and are logged-then-dropped with no retry.
> - **Architectural note:** This is the web-process counterpart of the bot↔ORM bridge (§2). Unlike EXT-001 (which runs in the bot's event loop), this bridge spawns OS threads from gunicorn sync workers — each `thread.start()` is untracked and unbounded. The finding's "thread-per-message" characterization is accurate (the `Bot(...)` construction is per-message; the thread is per-ad).
> - **ROI:** Recommended, not overengineered — single-Bot reuse, global thread-pool bounding, and 429 retry are standard production patterns. Gating is default-OFF, bounding severity to MEDIUM.
> - **See also:** §2 (async↔sync bridge); §5(c) (client resilience, retry); §7 (graceful degradation when integration down).

**Description:** Near-real-time alert delivery (`deliver_immediate_alerts`, gated by `IMMEDIATE_ALERTS_ENABLED`, default OFF) is invoked from a `transaction.on_commit` callback running in the **sync gunicorn worker** (`moderation/signals.py:76`), which then spawns a **dedicated `threading.Thread` per published ad** (`immediate_alerts.py:87-93`) running `asyncio.run(_send_payloads(...))`. Inside that loop, `Bot(token=bot_token)` is constructed **per alert message** (`immediate_alerts.py:178`) — i.e. a fresh `aiohttp` session / TCP connection pool to `api.telegram.org` per recipient, with no reuse across the batch. The only concurrency cap (`_SEND_CONCURRENCY = 10`, `immediate_alerts.py:38`) is a **per-thread** `asyncio.Semaphore`, **not** a global bound, so a burst of published ads creates an unbounded number of daemon threads. Transients outside `TelegramBadRequest`/`TelegramForbiddenError` (e.g. network reset, 5xx, or a Telegram 429 with `retry_after`) hit the bare `except Exception` at `immediate_alerts.py:168` and are **logged then dropped with no retry** — a published ad's alerts can be silently lost. This is the web-process counterpart of the bot↔ORM bridge; §2 correctly flags the cross-process seam, but the sync→async-over-thread bridge here lacks global bounding and retry.

**Evidence:**
- `src/backend/apps/moderation/signals.py:56-76` — `deliver_immediate_alerts_on_publish`; `transaction.on_commit(_deliver)`; guarded only by `IMMEDIATE_ALERTS_ENABLED`
- `src/backend/apps/search/services/immediate_alerts.py:87-93` — `threading.Thread(target=_run_send, …, daemon=True)` created per published ad
- `src/backend/apps/search/services/immediate_alerts.py:164-168` — `_run_send` → `asyncio.run(...)` wrapped in `except Exception as exc:` (no retry, no 429 back-off)
- `src/backend/apps/search/services/immediate_alerts.py:172-193` — `_send_payloads` builds `Bot(token=bot_token)` inside the per-message `_send` (line 178)
- `src/backend/apps/search/services/immediate_alerts.py:186` — only `TelegramBadRequest, TelegramForbiddenError` are handled per-message
- `src/backend/config/settings/base.py:243` — `IMMEDIATE_ALERTS_ENABLED` defaults to `"false"` (default-OFF gate)

**Consequence:** When alerts are enabled, a publish burst spawns N unbounded daemon threads (one per ad), each spinning up its own `aiohttp` session; under Telegram 429/network-5xx, messages are silently dropped with no retry → alerts lost and users not notified of new ads. The per-message `Bot` construction also defeats connection reuse, amplifying TLS/TCP setup cost per recipient.

**Recommendation:** [BEST-PRACTICE] Reuse a single module-level `Bot` (one shared `aiohttp` session) per worker thread and close it after the batch; bound the number of concurrent delivery threads globally (process-level semaphore / bounded `ThreadPoolExecutor`) so a publish burst cannot spawn unbounded threads; implement retry-with-backoff for non-fatal Telegram errors (honour `retry_after` on 429, exponential backoff on 5xx/network) and route permanently-unreachable chats to a dead-letter record rather than silently dropping. Effort: medium. Priority: recommended.

---

### EXT-003: Reverse-proxy rate limiting covers only /login/ and /search/; public browse surface + moderation API are unthrottled

| Field | Value |
|-------|-------|
| **ID** | EXT-003 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `docker/nginx/nginx.conf` (rate-limit zones), `docker/nginx/nginx.dev.conf` (mirrors same gap), `src/backend/apps/moderation/views/api_bulk.py` (moderation API), `src/backend/apps/ads/views/listings.py` (public browse) |
| **Classification** | mandatory |

> **Validation Note:**
> - **Action:** validated (unchanged) — **with evidence-quality refinement on the amplification rationale** (see Warnings).
> - **Detail:** Reproduced verbatim against both `nginx.conf` and `nginx.dev.conf` (dev config is a structural mirror with identical rate-limit scope). An exhaustive `grep limit_req` across `docker/nginx/` returns exactly **2 `limit_req_zone` declarations** (`login_limit`, `search_limit`) and **2 `limit_req` directives** — both on `/login/` and `/search/` only, in both files. The default `location /` (nginx.conf:128-135 / nginx.dev.conf:120-127), `/media/` (73-79 / 74-80), and `/protected-media/` (82-97 / 83-98) carry **no** `limit_req`. The root `location /` is the catch-all for the entire public browse surface (catalog, category, ad detail, pagination, HTMX fragments) per nginx location matching. Confirmed `api_bulk.py:54` is `for ad_id in ad_ids:` with no upper bound on `selected_items`.
> - **Evidence-quality refinement (does NOT change verdict):** The finding's supporting rationale states the "unthrottled catalog listings perform the same per-language GIN/FTS joins with no comparable guard." The FTS path (`SearchQuery`/`SearchRank` on per-language `search_vector_*`) is confined to the **`/search/`** endpoint (`apps/search/views/search.py:201-203`), which **is** rate-limited by `search_limit` (§8 SRH-001 corroborates this is the FTS read-path DoS amplifier). The `listings` browse view (`ads/views/listings.py`) does **not** issue FTS/GIN scans — it uses standard ORM work: `select_related("category","city","user")`, `prefetch_related("features","user__trust_score")`, per-feature M2M `__in` joins + `distinct()`, `annotate_favorites` (a `get_or_create` on `AdFavorite`), and `Paginator.count()`. So the characterization of browse as doing "the same per-language GIN/FTS joins" is **imprecise**. However, this is *supporting rationale*, not the finding's core claim: the absence of `limit_req` on the public browse surface (`location /`) remains a genuine §5(a)/§8 HIGH spec deviation, and browse still performs non-trivial per-request work (M2M joins + distinct + count + favorites sub-query) that is unamplified but genuinely unthrottled. Verdict and severity **unchanged**.
> - **Spec basis:** §5(a) evidence bullet — "reverse-proxy rate-limits public endpoints"; §8 HIGH — "No rate-limit on API/webhook/public endpoints"; §5(h) "public endpoints must carry a reverse-proxy rate-limit zone."
> - **See also:** phase 08 SRH-001 (search long-query 500-DoS) corroborates the FTS read path is a known DoS amplifier (the `/search/` path is bounded by `search_limit`; browse is the unbounded sibling).

**Description:** `nginx.conf` defines only two `limit_req_zone`s — `login_limit` (10 r/s) and `search_limit` (20 r/s) (`nginx.conf:24-25`) — and attaches `limit_req` to **only** `location /login/` (`nginx.conf:101`) and `location /search/` (`nginx.conf:111`). The default `location /`, the catalog/ads browse surface (`/`, category and ad detail/listings), and the state-changing `POST /moderation/bulk-action/` all inherit **no `limit_req`**. Per §5(a) and §5(h), public endpoints must carry a reverse-proxy rate-limit zone; their absence leaves the listings and the moderation bulk API open to unthrottled requests. This is the amplification path for the §8 DoS class: phase 08 SRH-001 shows `/search/` is bounded by `search_limit` (so its long-query 500-DoS is partially capped), but the unthrottled catalog listings perform the same per-language GIN/FTS joins with no comparable guard, and the admin bulk-action API has no throttle **plus** an unbounded `selected_items` batch, allowing a single request to drive mass ad mutations.

**Evidence:**
- `docker/nginx/nginx.conf:24-25` — only `login_limit` and `search_limit` zones defined
- `docker/nginx/nginx.conf:100-107` — `limit_req zone=login_limit` on `/login/` only
- `docker/nginx/nginx.conf:109-117` — `limit_req zone=search_limit` on `/search/` only
- `docker/nginx/nginx.conf:128-135` — default `location /` has **no** `limit_req`
- `src/backend/apps/moderation/views/api_bulk.py:54` — `for ad_id in ad_ids:` (no cap on `selected_items` batch size)
- `grep limit_req docker/nginx/` — 2 zones + 2 directives across both `nginx.conf` and `nginx.dev.conf`; **0** on `location /`, `/media/`, `/protected-media/`, `/health/`
- phase 08 SRH-001 (search long-query 500-DoS), confirming the FTS read path is a known DoS amplifier

**Consequence:** The public browse catalog and the admin bulk-moderation API are reachable at full speed by any client — no `limit_req` to cap request rate, and the bulk API accepts an unbounded `selected_items` list, so a single request can drive N× DB mutations (approve/reject/flag) and a flood of browse requests each doing M2M joins + distinct + `count()` + favorites sub-query can saturate the DB.

**Recommendation:** [BEST-PRACTICE] Attach a reverse-proxy `limit_req` zone to the public browse surface (`location /`) and to `/moderation/`; enforce an application-level cap on `selected_items` in the bulk API (e.g. max 100/request) and prefer an app-level throttle (cached rate counter) so limits are observable and testable rather than only proxy-imposed. Effort: small. Priority: recommended (mandatory per phase classification — EXT-003 is the sole `mandatory` finding).

---

### EXT-004: `/protected-media/` location drops HSTS and `Referrer-Policy`/`Permissions-Policy` are absent site-wide

| Field | Value |
|-------|-------|
| **ID** | EXT-004 |
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `docker/nginx/nginx.conf` (TLS/header hardening), `docker/nginx/nginx.dev.conf` (mirrors same gap), `src/backend/config/settings/prod.py` (`SECURE_HSTS_SECONDS=31536000`, dev.py `=0`) |
| **Classification** | advisory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Reproduced verbatim. nginx's `add_header` inheritance rule is correctly invoked: a `location` with **any** of its own `add_header` directives **drops all inherited** server-level `add_header`s. Confirmed:
>   - `nginx.conf:38` — server-level `add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;`.
>   - `nginx.conf:82-97` (`/protected-media/` block) — re-declares `X-Content-Type-Options` (87), `Content-Disposition` (88), `X-Frame-Options` (89), `Content-Security-Policy-Report-Only` (90), but **omits `Strict-Transport-Security`** → HSTS is dropped on every protected-media response.
>   - `nginx.conf:66-69` (`/static/` block) — redeclares all four incl. HSTS — this is the correct pattern the finding recommends replicating. ✓
>   - `grep` for `Referrer-Policy` and `Permissions-Policy` across `docker/nginx/` → **0 matches in both** `nginx.conf` and `nginx.dev.conf` (confirmed).
>   - Context: `prod.py:42` sets `SECURE_HSTS_SECONDS=31536000` / `:44` `SECURE_HSTS_PRELOAD=True`, but `/protected-media/` is served by nginx directly (`internal; alias`) via `X-Accel-Redirect` — Django's `SecurityMiddleware` HSTS does **not** apply to those responses (they never reach the Django app), so only the nginx `add_header` HSTS could cover them, and it is dropped here. `dev.py:31` sets `SECURE_HSTS_SECONDS=0` (HSTS intentionally off in dev), so the HSTS-drop is a **production** concern. `nginx.dev.conf` mirrors the same `/protected-media/` gap at lines 83-98.
> - **Spec basis:** §5(g) — "TLS, HSTS, secure headers" / evidence "HSTS+CSP+nosniff+frame-deny present"; §8 LOW "TLS/header weaknesses" and §8 HIGH "TLS/header weaknesses at reverse proxy."
> - **Evidence-quality note (cosmetic):** The finding cites `nginx.conf:82-96` for the protected-media block; the block is actually lines 82–97 (closing `}` at 97; line 96 is `default_type`). Immaterial — the HSTS omission (absence is the claim) is confirmed.
> - **See also:** §5(g) (reverse-proxy TLS hardening).

**Description:** Server-wide security headers are set once at the `server` level (`Strict-Transport-Security`, `X-Content-Type-Options nosniff`, `X-Frame-Options DENY`, `Content-Security-Policy-Report-Only` — `nginx.conf:38-47`). nginx's `add_header` inheritance rule states that a `location` with **any** `add_header` of its own **drops all inherited** `add_header` directives. The `location /protected-media/` block (`nginx.conf:82-96`) re-declares `X-Content-Type-Options` (87), `Content-Disposition` (88), `X-Frame-Options` (89), and `Content-Security-Policy-Report-Only` (90) but **omits `Strict-Transport-Security`** → HSTS is silently dropped on every protected-media response. Additionally, no `Referrer-Policy` and no `Permissions-Policy` header is emitted anywhere in the config (server or location level — 0 matches), leaving referrer-leakage control to browser defaults. CSP is intentionally Report-Only only (deferred "Phase 2" per the inline comment at `nginx.conf:41-47`); that is a deliberate deferral and is not asserted here — the HSTS drop on protected-media is an unintended regression, not a listed deferral.

**Evidence:**
- `docker/nginx/nginx.conf:38` — server-level `Strict-Transport-Security "max-age=31536000; includeSubDomains" always`
- `docker/nginx/nginx.conf:82-97` — `/protected-media/` block declares nosniff (87), `Content-Disposition` (88), `X-Frame-Options` (89), `CSP-Report-Only` (90) but **no** `Strict-Transport-Security`
- `docker/nginx/nginx.conf:66-69` — `/static/` block redeclares all four (incl. HSTS) — the correct pattern to replicate
- `docker/nginx/nginx.dev.conf:83-98` — same HSTS-drop gap in dev config
- `grep -rn "Referrer-Policy\|Permissions-Policy" docker/nginx/` → **0 matches** in `nginx.conf` and `nginx.dev.conf`
- `src/backend/config/settings/prod.py:42` — `SECURE_HSTS_SECONDS = 31536000`; `dev.py:31` — `SECURE_HSTS_SECONDS = 0`

**Consequence:** Every protected-media response (served directly by nginx via `X-Accel-Redirect`, bypassing Django's `SecurityMiddleware`) is emitted **without HSTS**, so browsers are not pinned to HTTPS for media requests. Site-wide absence of `Referrer-Policy` lets the full origin be leaked via the `Referer` header on cross-origin navigations/resources; absence of `Permissions-Policy` leaves feature-policy control to default (browser) behavior.

**Recommendation:** [BEST-PRACTICE] Re-declare `Strict-Transport-Security` inside `/protected-media/` (or factor all security headers into an `include`'d snippet so every `location` emits the full set consistently — the `/static/` block at `nginx.conf:66-69` is the correct pattern to replicate). Add a site-wide `Referrer-Policy: strict-origin-when-cross-origin` (and a `Permissions-Policy` if no cross-origin features are required). Effort: trivial. Priority: recommended.

---

### EXT-005: Bot ad-creation FSM is not idempotent against re-delivered Telegram updates — crash mid-handler can create duplicate DRAFTs

| Field | Value |
|-------|-------|
| **ID** | EXT-005 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/telegram_bot/main.py:65` (`dp.run_polling`), `src/telegram_bot/main.py:43-58` (middleware/routers), `src/telegram_bot/handlers/ad_create.py:865-875` (`create_draft_ad` → `Ad.objects.create(..., DRAFT)`), `src/telegram_bot/handlers/ad_create.py:1270-1274` (translation side-effect), `src/telegram_bot/handlers/login.py:119-131` (idempotent contrast) |
| **Classification** | advisory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Reproduced verbatim. Confirmed:
>   - `main.py:65` — `dp.run_polling(bot)` with **no** `allowed_updates` argument (aiogram defaults to `["message","edited_message","channel_post","edited_channel_post","callback_query","edited_message"]` etc. — the key point is the offset is acknowledged only after handler return with no disk/Redis persistence; `MemoryStorage()` is registered at `main.py:39` for FSM state, not offset persistence).
>   - `main.py:43-58` — only `AccountStateMiddleware()` (line 43) and five routers (`login_router`, `ad_create_router`, `alerts_router`, `ad_copy_router`, `language_router`) are registered. Verified `src/telegram_bot/middlewares/__init__.py` exports only `AccountStateMiddleware` (re-exports from `permissions.py`); `permissions.py` `AccountStateMiddleware` (lines 21-167) is purely an account-state gate (banned/deleted/declined/publish-restriction) — it performs **no** `update_id` dedup. A repo-wide `grep` for `allowed_updates`/`update_id`/`update.update_id` under `src/telegram_bot/` returns **zero matches**.
>   - `ad_create.py:870-875` — `@sync_to_async def _create(): return Ad.objects.create(user_id=user_id, status=AdStatus.DRAFT)` — plain `create`, no idempotency key / no `get_or_create` / no `update_id` guard.
>   - `ad_create.py:1270-1274` — `translate_all_languages` gather is the re-invocable side effect on re-delivery (re-translation + re-counted translation-client load, per EXT-001).
>   - Contrast (idempotent): `login.py:119-131` — `_claim_login_token` uses a single-statement `UPDATE login_tokens SET telegram_id = %s WHERE token_hash = %s AND telegram_id IS NULL AND consumed_at IS NULL AND expires_at > %s RETURNING …` — the row-lock + `WHERE telegram_id IS NULL` guard makes login claim replay-safe. This confirms the project *has* an idempotency pattern; ad creation is the unguarded sibling.
> - **Bot-offset nuance:** aiogram's `run_polling` confirms the `getUpdates` offset in memory only; an update received-but-unacked at process crash is re-delivered by Telegram on restart. The finding's "aiogram does not persist the offset to disk" is accurate for this `MemoryStorage`-configured polling setup (no `RedisStorage`/file offset sink wired).
> - **Spec basis:** §7 edge case — "Duplicate / out-of-order Telegram updates → idempotent handling" (line 91); §2 Bot/Async Runtime; §5(b) bridge correctness; §4.3/§4.9 quality gates.
> - **See also:** EXT-001 (the translation side-effect re-invoked on a re-delivered ad-creation update compounds the thread-leak); phase 04 AU-001 (login token is the idempotent counterpart — same cross-process concern, already guarded).

**Description:** The bot receives updates via `dp.run_polling(bot)` (`main.py:65`) with aiogram's default offset acknowledgement: the `getUpdates` offset is confirmed **only after** a handler returns without error. Updates that were received but not yet acked are therefore **re-delivered on restart** (aiogram does not persist the offset to disk, and `main.py:43-58` registers only `AccountStateMiddleware()` — no update-ID dedup middleware). The login deep-link claim **is** idempotent (phase 04 confirmed the `UPDATE … RETURNING` row-lock guard at `login.py:119-131` rejects replays), but **ad creation is not**: `create_draft_ad` (`ad_create.py:872-875`) does a plain `Ad.objects.create(user_id=..., status=AdStatus.DRAFT)` (`ad_create.py:873`) with no client-message idempotency key, no `update_id` dedup, and no re-creation guard. If the bot process crashes between receiving a `/post` (or the category/photo step) and acknowledging the offset — e.g. mid-`sync_to_async` DB work or during `translate_all_languages` — Telegram re-delivers the update on restart and the handler re-runs, producing a **duplicate DRAFT** plus re-execution of translation/photo side-effects. Phase §7 explicitly lists "Duplicate / out-of-order Telegram updates → idempotent handling" as an edge case to verify; it is currently unguarded on the ad-creation path.

**Evidence:**
- `src/telegram_bot/main.py:65` — `dp.run_polling(bot)` (no `allowed_updates`, no offset persistence, no update-dedup middleware)
- `src/telegram_bot/main.py:43-58` — only `AccountStateMiddleware()` + routers registered (no idempotency middleware)
- `src/telegram_bot/handlers/ad_create.py:870-875` — `@sync_to_async def _create(): return Ad.objects.create(user_id=user_id, status=AdStatus.DRAFT)` (no idempotency key / no `get_or_create`)
- `src/telegram_bot/handlers/ad_create.py:1270-1274` — `translate_all_languages` re-invocable side effect on re-delivery
- `src/telegram_bot/middlewares/__init__.py` — exports only `AccountStateMiddleware`; repo `grep update_id/allowed_updates` in `telegram_bot/` → 0 matches
- contrast (idempotent): `src/telegram_bot/handlers/login.py:119-131` — login claim uses `UPDATE … RETURNING` (`login.py:120-131`) `WHERE token_hash = %s AND telegram_id IS NULL AND consumed_at IS NULL AND expires_at > %s`

**Consequence:** A bot crash mid-ad-creation (during `sync_to_async` DB write or the `translate_all_languages` gather) causes Telegram to re-deliver the unacked update on restart; the handler re-runs `Ad.objects.create` → a **duplicate DRAFT** ad row, plus re-translation (re-counted translator load / potential thread leak via EXT-001) and any photo side-effects re-execution. Duplicate DRAFTs can surface as duplicate ads to the seller or as inconsistent state.

**Recommendation:** [BEST-PRACTICE] **Choose Approach A — an update-level dedup middleware using a Redis SET** (the matching advisory bullet and rollout-safety note below are updated to match). Add a new module `src/telegram_bot/middlewares/update_id_dedup.py` exporting `UpdateIdDedupMiddleware(BaseMiddleware)` whose `__call__(self, handler, event, data)` reads `update_id = event.update_id` (the `Update.update_id` field — a required `int`, verified in the installed aiogram 3.30.0 schema) and performs an atomic `cache.add(f"bot_update:{update_id}", 1, timeout=DEDUP_TTL_SECONDS)` via Django's shared cache (`from django.core.cache import cache`). `cache.add` returns `True` **only** on first insertion — the exact atomic "insert-if-absent" primitive already used in `rate_limit.py:49` (`cache.add(key, 1, timeout=period)`) — so a re-delivered update (same `update_id` after a crash-restart) returns `False` and the middleware short-circuits (`return None`) **without invoking the handler**. This suppresses **all** downstream side-effects in a single guard at the top of the chain: the duplicate `Ad.objects.create(..., status=AdStatus.DRAFT)` in `create_draft_ad` (`ad_create.py:873`), the `translate_all_languages` gather re-invocation (`ad_create.py:1270-1274`), and any photo writes — directly satisfying the finding's "guard side-effects" requirement rather than patching each handler individually. Wrap the `cache.add` in `try/except (ConnectionInterrupted, redis.RedisError)` and **fail-open** (log a warning via the module logger, then `return await handler(event, data)`) so a Redis outage never drops legitimate traffic — mirroring the graceful-degradation pattern in `apps/lookups/signals.py:32-36` and `apps/categories/cache.py`. Set `DEDUP_TTL_SECONDS` generously (e.g. `86400` / 24 h) so the key outlives bot restarts and Telegram's re-delivery window. Register it once in `main.py` via `dp.update.middleware(UpdateIdDedupMiddleware())` — verified in aiogram 3.30.0 that `dp.update` is a `TelegramEventObserver` exposing `.middleware(...)`, which processes **every** `Update` (messages, callback queries, edits) before type dispatch, alongside the existing `AccountStateMiddleware` registration at `main.py:43`. **No migration is required** — the change touches no DB schema and adds no `Ad` model field. **Approach B is rejected** (make `create_draft_ad` idempotent via `get_or_create` on a new `Ad.telegram_update_id` field): it requires a schema migration (only `apps/ads/migrations/0001_initial.py` exists; project rule #13 mandates a migration for any schema change), changes the `create_draft_ad(user_id: int)` signature (breaking the call site at `ad_create.py:117` and every test in `test_create_draft_ad.py` that calls `create_draft_ad(user_id=user.id)`), and only guards DRAFT creation — it does **not** prevent re-execution of the translation/photo side-effects on the category/title/description/price/photos/preview FSM steps, which the finding explicitly requires guarding. This approach reuses infrastructure already wired for the bot process: `REDIS_URL` is configured at `base.py:267-268`, `CACHES` is `django-redis` pointed at `REDIS_URL` (`base.py:257-265`), `django.setup()` runs before middleware import (`main.py:11`), and `rate_limit.py` already imports `from django.core.cache import cache`. Effort: medium. Priority: recommended. (Single, concrete choice; replaces the prior "A or B / at minimum" wording.)

---

### EXT-006: Moderation bulk-action API deviates from the §5(e) API contract (403 for unauthenticated instead of 401; no versioning)

| Field | Value |
|-------|-------|
| **ID** | EXT-006 |
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/moderation/views/decorators.py:34-49` (`staff_required_api`), `src/backend/apps/moderation/views/api_bulk.py` (bulk endpoint), `src/backend/apps/moderation/urls.py` |
| **Classification** | advisory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Reproduced verbatim. Confirmed:
>   - `decorators.py:43-49` — `staff_required_api` wrapper: line 45 `if not (request.user.is_staff or request.user.is_superuser):` → line 46 `return JsonResponse({"error": "Unauthorized"}, status=403)`. There is **no** `is_authenticated` branch and **no** `401`/`WWW-Authenticate` path. For an unauthenticated request, Django's `AuthenticationMiddleware` sets `request.user = AnonymousUser()` (the view has no `@login_required`, only `@staff_required_api`). `AnonymousUser.is_staff`/`is_superuser` are both `False`, so `not (False or False)` = `True` → the view returns **403**, not 401. Verified `AnonymousUser` semantics confirm this (an unauthenticated caller is indistinguishable from an authenticated-non-staff caller under this decorator).
>   - `moderation/urls.py:18` — `path("bulk-action/", bulk_moderation_action, name="bulk_action")` — no version prefix (no `/v1/`).
>   - `decorators.py:17-31` — template-facing `staff_required` raises `Http404` for non-staff (line 28) — the finding's contrast (deny-by-obscurity on templates vs 403 on API) confirmed.
>   - `api_bulk.py:20-21` — `@staff_required_api def bulk_moderation_action(...)` — the only JSON API; no version segment.
> - **Spec basis:** §5(e) — "API surface security (authn/authz)" / evidence "unauth→401"; §7 edge case — "API version mismatch (client v1 vs server v2) → handled, not 500" (line 96). Both confirmed in the phase-09 template.
> - **Evidence-quality note (cosmetic, not a validity issue):** The recommendation is prefixed `[BEST-PRACTICE]` but the `Type` field is `SPEC-DEVIATION`. This prefix inconsistency is a template artifact — **all six** findings in this phase carry the `[BEST-PRACTICE]` recommendation prefix regardless of `Type`. The `Type` field (SPEC-DEVIATION) is the authoritative classification and correctly reflects the §5(e) deviation; the prefix is not updated. No reclassification warranted.
> - **See also:** §5(e) (API authn/authz); §7 (API version mismatch handling).

**Description:** `POST /moderation/bulk-action/` is the system's only JSON API. It is guarded by `staff_required_api` (`decorators.py:34-49`), which returns `JsonResponse({"error": "Unauthorized"}, status=403)` for any non-staff caller — **including a fully unauthenticated (`AnonymousUser`) request**. Per RFC 7235 and phase §5(e) ("unauthenticated → 401"), an unauthenticated caller should receive `401` with a `WWW-Authenticate` challenge so the client knows to authenticate, while an authenticated-but-non-staff caller should receive `403`. Conflating both as `403` blurs the authn/authz boundary and breaks standard API-client auth flow. Additionally the moderation API has **no version segment** in its URL (`moderation/urls.py:18` → `path("bulk-action/", …)`, no `/v1/`), so the §7 edge case "API version mismatch (client v1 vs server v2) → handled, not 500" cannot be satisfied: there is no versioning surface to mismatch against and no explicit error path for an unknown version. (Body input-schema validation is the separate CFG-003 concern filed in phase 02 and is not re-asserted here.)

**Evidence:**
- `src/backend/apps/moderation/views/decorators.py:45-46` — `if not (request.user.is_staff or request.user.is_superuser): return JsonResponse({"error": "Unauthorized"}, status=403)` (no branch for unauthenticated → 401)
- `src/backend/apps/moderation/urls.py:18` — `path("bulk-action/", bulk_moderation_action, name="bulk_action")` (no version prefix)
- `src/backend/apps/moderation/views/decorators.py:26-28` — template moderation views use `Http404` for non-staff (deny-by-obscurity), contrasting with the API's 403

**Consequence:** An unauthenticated request to the bulk API returns `403` (not `401`), so API clients cannot auto-initiate auth flows (no `WWW-Authenticate` challenge) and the authn/authz boundary is blurred. The absence of any version segment means a client/server version skew has no explicit `400`/`404` degradation path — the §7 "API version mismatch → handled, not 500" contract is structurally unsatisfiable today.

**Recommendation:** [BEST-PRACTICE] On API views, return `401` (with `WWW-Authenticate`) when `not request.user.is_authenticated`, else `403` when authenticated-but-not-allowed. Add a version prefix (`/api/v1/moderation/...`) to the JSON endpoint so an unknown version degrades to an explicit `400`/`404` instead of silently matching. Effort: small. Priority: recommended (advisory).

---

## Summary

| Severity | Count | IDs |
|----------|-------|-----|
| CRITICAL | 0 | — |
| HIGH | 1 | EXT-003 |
| MEDIUM | 3 | EXT-001, EXT-002, EXT-005 |
| LOW | 2 | EXT-004, EXT-006 |

## Mandatory Fixes

- **EXT-003** (HIGH): Attach a reverse-proxy `limit_req` zone to the public browse surface (`location /`) and to `/moderation/`; cap `selected_items` in the bulk API (e.g. max 100/request).

## Advisory Recommendations

- **EXT-001**: Add bounded retry/backoff to the translation client; replace the abandoned-`ThreadPoolExecutor`-future pattern with a bounded `Semaphore` and a real (httpx) timeout+cancel scope; narrow the catch-all `except Exception` to `TimeoutError, RequestException` **plus** `deep_translator.exceptions.{TooManyRequests, RequestError, TranslationNotFound}` (see Warnings — blind narrowing to `(TimeoutError, RequestException)` alone would exclude the retryable translation-protocol errors).
- **EXT-002**: Reuse a single module-level `Bot`/session per worker thread; bound delivery threads globally (semaphore/bounded thread pool); retry non-fatal Telegram send errors and honour `retry_after` on 429.
- **EXT-004**: Re-declare `Strict-Transport-Security` in `/protected-media/` (or extract security headers into a shared `include` snippet matching the `/static/` pattern at `nginx.conf:66-69`); add site-wide `Referrer-Policy` (and `Permissions-Policy` if no cross-origin features are required).
- **EXT-005**: Add an update-level `UpdateIdDedupMiddleware` (Redis SET via atomic `cache.add`, fail-open on `ConnectionInterrupted`/`redis.RedisError`, 24 h TTL) registered at `dp.update.middleware()` in `main.py` to skip re-delivered `update_id`s and suppress all restart-replayed side-effects (duplicate DRAFT, translation/photo re-runs); **no** `Ad` model change / **no migration required** (Approach A chosen; the `get_or_create`-keyed-on-`update_id` alternative is rejected — it needs a migration + `create_draft_ad` signature change and only guards DRAFT creation, not translation/photo side-effects).
- **EXT-006**: Return `401` (with `WWW-Authenticate`) for unauthenticated API callers, `403` for authenticated-non-staff; version the moderation JSON API.

## Doc Updates Needed

(None — every finding is a code/config deviation or best-practice gap; no documentation asserts behaviour that the implementation contradicts, so no `[DOC-UPDATE]` findings are raised. Spec cross-references (§5(a–h), §7, §8) were verified against `.kilo/commands/audit/phases/09-audit-external-api.md`; they assert requirements the code does not yet meet, so the spec is the baseline, not a doc to update.)

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 6 | EXT-001, EXT-002, EXT-003, EXT-004, EXT-005, EXT-006 |
| Reclassified | 0 | — |
| Merged | 0 | — |
| Rejected | 0 | — |

### Rejected Findings

_None._ All six findings were verified against the current working tree via targeted `grep` + exact source-line reads and found technically correct, currently applicable, and architecturally sound. None are stale, duplicate, or low-ROI; none introduce operationally unsafe or architecture-breaking changes by themselves.

### Merged Findings

_None._ Cross-finding analysis within this phase surfaced related pairs sharing a seam, but each has a distinct root cause and remains a separate finding:
- **EXT-001 ↔ EXT-005** — both touch `ad_create.py:1270-1274` (translation gather): EXT-001 is translation-client resilience (no retry/backoff, thread leak, catch-all), EXT-005 is bot update-level idempotency (no `update_id` dedup). Fixing EXT-005's idempotency *reduces the blast radius* of EXT-001's thread leak (fewer re-delivered translation calls) but does not remove it (first-delivery throttling still stalls). Distinct root causes; kept separate.
- **EXT-002 ↔ EXT-003** — both bound publish-time blast radius: EXT-002 is the web→async thread/Bot-per-message bridge, EXT-003 is the reverse-proxy/public-endpoint throttle + bulk-batch cap. Different layers (process-thread vs proxy-HTTP); kept separate.
- **EXT-003 ↔ CFG-003 (phase 02)** — same `bulk_moderation_action` endpoint but distinct root causes: EXT-003 = DoS/throttle (no rate-limit, unbounded `selected_items`); CFG-003 = input-type validation (no Pydantic DTO, silent unknown-key drop). Corroborated cross-phase reference; not merged.
- **EXT-005 ↔ AU-001 (phase 04)** — both deal with update/message replay: AU-001 is the login-token claim (already idempotent via `UPDATE…RETURNING`), EXT-005 is ad-creation (unguarded). The findings.md explicitly defers login-token lifecycle to phase 04; ad creation is the unguarded sibling. Not merged.
- Cross-phase references not re-verified in this pass: phase 03 DB-001 (bot DB-connection leak), phase 08 SRH-001/SRH-002 (FTS long-query DoS / search-side translation-bridge removal). These are cited as dedup anchors only.

### Reclassified Findings

_None._ All six retain the auditor's `Type` and `Classification` assignments:
- EXT-001 (`SPEC-DEVIATION`, advisory) — §5(c) requires retry/backoff; code lacks it; fallback exists so severity is MEDIUM/advisory. Correct.
- EXT-002 (`BEST-PRACTICE`, advisory) — thread-per-message/no-retry; gated default-OFF. Correct.
- EXT-003 (`SPEC-DEVIATION`, mandatory) — §5(a)/§8 HIGH require public-endpoint rate-limits; absent. Correct (sole mandatory finding).
- EXT-004 (`SPEC-DEVIATION`, advisory) — NGINX-inherited HSTS drop + missing Referrer/Permissions-Policy; §5(g)/§8. Correct.
- EXT-005 (`BEST-PRACTICE`, advisory) — §7 duplicate-update idempotency gap. Correct.
- EXT-006 (`SPEC-DEVIATION`, advisory) — §5(e) unauth→401 + §7 versioning; code returns 403 / has no version. Correct.

The only Type-level nuance: EXT-006's recommendation is prefixed `[BEST-PRACTICE]` while its `Type` is `SPEC-DEVIATION` — this prefix is applied uniformly to **all six** findings (template artifact) and is treated as cosmetic, not a reclassification trigger (the `Type` field is authoritative). See Warnings.

### Rollout Safety

- **EXT-003 (mandatory, HIGH):** Two independent, safe-to-deploy-separately changes — (a) add `limit_req` zones to `location /` and `/moderation/` in `nginx.conf` (and mirror in `nginx.dev.conf`); (b) app-level `selected_items` cap (e.g. `MAX_BULK_ACTIONS = 100`) in `api_bulk.py`. (a) is additive (existing clients within burst pass; only abusive floods are throttled — no backward-compat break). (b) is a behavior change: oversized batches (>100) are rejected — verify no legitimate admin UI sends >100 at once (the queue view renders one ad at a time, so 100/request is safe). No circular dependencies; proxy and app cap are decoupled. Safe.
- **EXT-001 (advisory, medium):** Refactor is layered behind the existing LRU cache + circuit-breaker; retry/backoff + Semaphore + narrowed-except can be unit-tested with `deep_translator` mocked (per §3 prerequisites). **Rollout hazard:** see Warnings — narrowing the `except` without including `deep_translator.exceptions` would let 429/RequestError/TranslationNotFound propagate to `translate_all_languages`' `asyncio.gather` and break ad creation. The httpx migration (cancel-scope) is a larger refactor — recommend staging (1) retry+semaphore first, (2) httpx migration second). No insertion-point fragility; `translate_text` is a single-entry function.
- **EXT-002 (advisory, medium):** Changes are confined to `immediate_alerts.py` (`_run_send`/`_send_payloads`) + a process-global thread-pool semaphore. Gated default-OFF (`IMMEDIATE_ALERTS_ENABLED`), so blast radius is zero until enabled. Single-module touch; no cross-module dependency. Safe.
- **EXT-004 (advisory, trivial):** Pure nginx header additions (HSTS on `/protected-media/`, site-wide `Referrer-Policy`). Additive; HSTS only re-added where it was dropped — no regression. Mirror in `nginx.dev.conf`. Safe. No backward-compat concern (dev has HSTS off by design; prod HSTS-only reasserts what was lost).
- **EXT-005 (advisory, medium):** Add an update-level `UpdateIdDedupMiddleware` (Redis SET via atomic `cache.add`, fail-open on `ConnectionInterrupted`/`redis.RedisError`, 24 h TTL) registered at `dp.update.middleware()` in `main.py` to skip re-delivered `update_id`s and suppress all restart-re-played side-effects (duplicate DRAFT, translation/photo re-runs); **no migration required** (no `Ad` model field added, no `create_draft_ad` signature change). The `get_or_create`-keyed-on-`update_id` alternative is **rejected** — it needs a migration (only `0001_initial.py` exists) + `create_draft_ad` signature change and only guards DRAFT creation. Rollout coupling: TTL must outlive bot restarts/re-delivery window (use `86400`). No schema change; no unsafe insertion points.
- **EXT-006 (advisory, small):** (a) Split 403→401-by-`is_authenticated` in `staff_required_api` — the decorator is used only by `bulk_moderation_action` (one consumer, grep-verified); additive behavior change for unauthenticated callers (403→401). Backward-compat: any client treating 403 as "denied" still sees a denial (401); a well-behaved API client benefits from the `WWW-Authenticate` challenge. (b) Versioning → URL change → backward-incompatible for clients hitting `POST /moderation/bulk-action/` directly; must be coordinated with any consumer (the admin UI — locate its fetch target before moving the URL). Safe if consumers updated together.
- No unsafe insertion points across findings; no execution-ordering conflicts among findings.

### Execution Validation

| Finding | Targets still exist? | Static verified? | Ready for execution |
|---------|----------------------|------------------|---------------------|
| EXT-001 | Yes — `translation.py:29,33,156-159,170,107,126`; `ad_create.py:1270-1274`; `deep_translator/google.py` `requests.get` no-timeout | Yes (file reads + `uv run python` source inspect) | Yes — medium (note the except-narrowing hazard in Warnings) |
| EXT-002 | Yes — `signals.py:56-76`; `immediate_alerts.py:87-93,164-168,168,174,178,186`; `base.py:243` | Yes (file reads + grep) | Yes — medium (default-OFF gate bounds blast radius) |
| EXT-003 | Yes — `nginx.conf:24-25,100-107,109-117,128-135`; `nginx.dev.conf` mirror; `api_bulk.py:54`; `listings.py:251-255,366-371,422` | Yes (file reads + grep `limit_req`) | Yes — small (mandatory) |
| EXT-004 | Yes — `nginx.conf:38,82-97,66-69`; `nginx.dev.conf:83-98`; `prod.py:42`, `dev.py:31` | Yes (file reads + grep: 0 Referrer/Permissions-Policy) | Yes — trivial |
| EXT-005 | Yes — `main.py:39,43-58,65`; `ad_create.py:870-875,1270-1274`; `login.py:119-131`; `middlewares/__init__.py` | Yes (file reads + grep: 0 `update_id`/`allowed_updates`) | Yes — medium (idempotency anchor / migration prerequisite) |
| EXT-006 | Yes — `decorators.py:26-28,43-49`; `api_bulk.py:20-21`; `moderation/urls.py:18` | Yes (file reads) | Yes — small (versioning move needs consumer coordination) |

### Warnings

1. **EXT-001 except-narrowing hazard (rollout-critical):** The recommendation to "narrow the `except` to `TimeoutError, RequestException`" is unsafe to apply verbatim. Verified via `uv run python` that `deep_translator.exceptions.{TooManyRequests, RequestError, TranslationNotFound}` subclass **only** `Exception` — not `requests.exceptions.RequestException`. Narrowing to `(TimeoutError, RequestException)` alone would let Google's 429 (`TooManyRequests`), non-200 (`RequestError`), and no-element (`TranslationNotFound`) responses **propagate** out of `translate_text` into `translate_all_languages`' `asyncio.gather` — turning a graceful "return original text" into an ad-creation crash. The correct narrowing must explicitly include the deep_translator exception family (retry/backoff the 429/RequestError subset; fall back on TranslationNotFound). This is a substantive execution prerequisite, not a cosmetic note.
2. **EXT-003 amplification rationale imprecise (evidence-quality, not a verdict change):** The finding states the unthrottled browse listings "perform the same per-language GIN/FTS joins." Verified that per-language GIN/FTS scans (`SearchQuery`/`SearchRank` on `search_vector_*`) are confined to the **`/search/`** endpoint (`apps/search/views/search.py:201-203`, rate-limited by `search_limit`) — NOT the `listings` browse view. The `listings` view (`ads/views/listings.py:251-255,366-371,416,422`) uses standard ORM joins (`select_related`/`prefetch_related`/M2M + `distinct` + `annotate_favorites` get_or_create + `Paginator.count`). The browse path is a *lighter* but still real unthrottled DoS surface (no `limit_req`), not a "GIN/FTS" amplifier. The core spec deviation (§5(a)/§8 HIGH — no rate-limit on public endpoints) is unaffected and remains validated; only the supporting rationale overstated the cost. The mitigation (add `limit_req` to `location /` + bulk cap) is correct regardless.
3. **EXT-006 recommendation-type prefix mismatch (cosmetic):** All six findings carry the `[BEST-PRACTICE]` recommendation prefix regardless of `Type` (EXT-001/003/004/006 are `SPEC-DEVIATION`). This is a template convention, not a finding error; the `Type` field is authoritative. Not reclassified.
4. **EXT-005 schema prerequisite (execution):** Making `create_draft_ad` idempotent keyed on `update_id` likely requires a schema column on `Ad` (or a dedicated dedup table) — a migration prerequisite (project rule #13). The dedup-middleware alternative (persist `update_id` in Redis/new table) avoids touching the `Ad` schema. Either path needs the idempotency anchor in place before the `get_or_create` guard lands; deploy migration first.
5. **Cross-config consistency (EXT-003/004):** The gaps exist identically in both `docker/nginx/nginx.conf` and `docker/nginx/nginx.dev.conf`. A fix in one must be mirrored in the other (they are not symlinked — two independent files). Not a separate finding but a rollout coordination note.
6. **Static-only validation ceiling:** No live runtime (Docker proxy, live Telegram 429, live translator outage) was exercised, per the phase's own "static analysis only" status. Findings of transient-error handling (EXT-001 retry, EXT-002 retry-on-429) are therefore inferred from code structure, not runtime reproduction. The static evidence is conclusive for the *absence* of the behavior; runtime confirmation of the *fix* is expected during implementation.

### Required Fixes

1. **EXT-003 (mandatory, HIGH):** In `docker/nginx/nginx.conf` (and mirror in `nginx.dev.conf`), add a `limit_req` zone to `location /` and to a `/moderation/` location, so the public browse surface and the moderation API are throttled. In `src/backend/apps/moderation/views/api_bulk.py`, cap `selected_items` (e.g. `MAX_BULK_ACTIONS = 100`; reject >100 with `400`) to close the unbounded-batch DoS.
2. **EXT-004 (low):** Re-add `Strict-Transport-Security` to the `/protected-media/` location (or extract all security headers into an `include`'d snippet replicating the `nginx.conf:66-69` `/static/` pattern) in both nginx configs; add a site-wide `Referrer-Policy: strict-origin-when-cross-origin`.

### Advisory Recommendations

1. **EXT-001:** Add bounded retry with capped exponential backoff at `translate_text`; replace the abandoned-future pattern with a bounded `Semaphore`; **first** narrow the `except` to `(TimeoutError, RequestException, deep_translator.exceptions.TooManyRequests, RequestError, TranslationNotFound)` (per Warning #1 — do not drop the deep_translator family or ad creation will crash on 429/no-element); migrate to `httpx` with per-request timeout + cancel scope (staged after retry/semaphore).
2. **EXT-002:** Reuse one module-level `Bot` per worker thread (close after batch); bound delivery threads globally via a process-level `ThreadPoolExecutor`/`Semaphore`; add 429 `retry_after` backoff + 5xx/network retry; dead-letter permanently-unreachable chats.
3. **EXT-005:** Add update-level dedup (persist processed `update_id`s in a table/Redis SET, skip re-deliveries in middleware) and/or make `create_draft_ad` idempotent (`get_or_create` on `(user_id, telegram_update_id)`) with migration applied first (Warning #4); guard translation/photo side-effects.
4. **EXT-006:** Split `staff_required_api` into `401` (unauthenticated → `WWW-Authenticate`) vs `403` (authenticated-non-staff); add `/api/v1/` version prefix to the moderation JSON endpoint and locate all consumers (admin UI fetch) before moving the URL.

*Findings validated via static-only evidence (targeted `grep` + exact source-line reads + installed-package source inspection via `uv run python`). The phase's own status was "Validated: no (static analysis only; Docker runtime not executed this phase)" — no test DB / live proxy was stood up in this validation pass. All six findings were reproduced verbatim against the current working tree and found technically correct, currently applicable, and architecturally sound; none were rejected, reclassified, or merged.*
