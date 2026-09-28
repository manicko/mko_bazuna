---
# Report metadata — fill once per phase report.
phase: "09"
phase_name: "External Integrations & API"
date: "2026-09-28"
auditor: "Executor (subagent)"
validator: ""  # Phase 99 only — omit/blank for raw phase findings
mode: "problems-only"
# Correct prefix per phase: 01-ENT, 02-CFG, 03-DB, 04-AUT, 05-AD, 06-PII, 07-MED,
# 08-SRH, 09-EXT, 10-QLT, 11-TST, 12-OPS, 13-PERF, 14-I18N
# DEVIATION (deliberate, orchestrator-instructed): the phase rubric §10 and the
# report template both prescribe `EXT-`, but `EXT-002/003/004/005/007` are already
# hard-coded as in-source markers in shipped code (nginx.conf:139, nginx.dev.conf:130,
# telegram_bot/retry.py:1, middlewares/update_id_dedup.py, handlers/login.py:112,
# core/tests/test_translation.py:232, search/tests/test_immediate_alerts.py:2).
# This report therefore uses `API-` so that Phase 99 and the remediation tracker
# cannot confuse a new finding with a prior in-source marker.
id_prefix: "API"
report_status: "draft"
severity_taxonomy: ".kilo/commands/audit/phases/09-audit-external-api.md#severity-taxonomy"
---

# Audit Findings — External Integrations & API

## Executive Summary

The board's outside-world connections — the Telegram bot, the machine-translation
service, e-mail, the reverse proxy and the credential store — are wired correctly
and no secret or credential is exposed. The risk in this phase is not leakage; it
is **fragility and unverified claims**. Five HIGH findings show that single
third-party or infrastructure failures cascade far wider than intended: losing the
shared cache takes the whole public site offline, four of the bot's own abuse
guards throw instead of failing open, one public bot link lets anyone message any
seller without limit, and the Telegram retry handler can pin a request for fifteen
minutes and still drop the message. Two documented capabilities the project
believes it has — an external exchange-rate feed and transactional e-mail for
password resets — do not exist in the code, and one of them is a hard boot gate.

## Scope & Methodology

**Scope:** Every boundary between the running system and an outside party: the
aiogram bot runtime (`src/telegram_bot/**`), the Google Translate egress
(`apps.core.services.translation` + its bot/backend callers), the Telegram
login-token deep-link handshake (`users/views/consent.py`, `handlers/login.py`),
the mixed JSON/template API surface (`config/urls.py` and every `*/urls.py`),
the nginx reverse proxy and TLS termination (`docker/nginx/**`,
`docker-compose*.yml`), the e-mail/SMTP path, the exchange-rate dependency, and
credential sourcing/rotation for `BOT_TOKEN`, `GOOGLE_TRANSLATE_API_KEY` and
`DJANGO_SECRET_KEY`.

### Runtime Verification

Live third-party calls were impossible (the `mko-bazuna-dev` web and bot
containers are crash-looping on a placeholder `BOT_TOKEN`, so the real Telegram
API is unreachable and must not be called). Verification was therefore a
combination of Docker test runs against the `mko-bazuna-test` project, a
read-only outage-simulation probe, and static/aiogram-source inspection.

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | No webhook ingress for the bot exists (`set_webhook`, `WEBHOOK_URL`, `TELEGRAM_WEBHOOK_SECRET` referenced nowhere) | `Select-String` over `src/**`, `docker/**`, `.github/**` — 0 matches | PASS |
| R-02 | Public endpoints 200 anonymous; staff JSON API 401+`WWW-Authenticate: Bearer` / 403 / 405; staff template views 404 | `apps/moderation/tests/test_decorators.py` in Docker (8 decorator cases) | PASS |
| R-03 | Malformed DTO input → 422 on the JSON API and on the CSP sink | `test_csp_report.py` + `test_decorators.py` in Docker | PASS |
| R-04 | Translation client resilience: timeout, bounded retry, circuit breaker, malformed-body handling, fallback | `apps/core/tests/test_translation.py` in Docker (16 cases) | PASS (but see API-007/API-017) |
| R-05 | Search degrades rather than 500s while the translator is down | `apps/search/tests/test_search_translation_outage.py` in Docker | PASS |
| R-06 | Telegram 429 backoff replays the failed method with a bound | `src/telegram_bot/tests/test_error_handler.py` in Docker | PASS (bound = 3 attempts; see API-004) |
| R-07 | Update de-duplication by `update_id`, fail-open on cache outage | `test_update_id_dedup.py` in Docker | PASS (this is the only cache consumer that fail-opens — see API-002) |
| R-08 | Async↔Sync bridge closes the thread-local connection on every update, including on exception | `test_db_connection_middleware.py` in Docker | PASS |
| R-09 | Bot dispatcher wiring == production wiring; retry handler registered | `test_main.py` in Docker | PASS |
| R-10 | Support e-mail delivery fails open and never breaks the bot dialog | `test_support_delivery_email.py` in Docker | PASS |
| R-11 | **Cache (Redis) outage vs. the documented `site_config` fallback** | Outage probe: monkeypatched the cache to raise `django_redis.exceptions.ConnectionInterrupted`, then called `get_bot_username()` / `get_site_name()` | **FAIL** — both raise (API-001) |
| R-12 | **Cache outage vs. the four bot rate limiters** | Same probe against `check_login_rate_limit`, `check_contact_start_rate_limit`, `check_support_message_rate_limit`, `check_upload_rate_limit` | **FAIL** — all four raise (API-002) |
| R-13 | **Telegram 429 (`retry_after=300`) → total wait imposed by `retry_transient`** | Outage probe with `asyncio.sleep` instrumented | **FAIL** — `sleeps=[300.0, 300.0, 300.0] total=900s`, then `handled=True` (API-004) |
| R-14 | **Alert message escaping for `parse_mode="HTML"`** | Outage probe built the message body from a seller title containing `<`, `"`, `&`; `Select-String` for `escape|html` over both alert modules returns only the 4 `parse_mode` lines | **FAIL** — no escaping exists (API-006) |
| R-15 | Exchange rates: is there an external feed, and are operator edits preserved? | Read `load_exchange_rates.py` (hard-coded `INITIAL_RATES`, `update_or_create`); observed test-container bootstrap output `Exchange rates loaded: 0 created, 3 updated` | **FAIL** — no feed, edits reverted every boot (API-008) |
| R-16 | No hardcoded secret and no tracked credential file | `git ls-files docker/nginx/certs/` → only `.gitkeep`; `git ls-files \| Select-String '^\.env'` → only `*.example`; `git check-ignore` confirms `docker/nginx/certs/*.pem` and the real `.env.*` are ignored | PASS |
| R-17 | Rotation procedure exists for `BOT_TOKEN`, `GOOGLE_TRANSLATE_API_KEY`, `DJANGO_SECRET_KEY` | `docs/ops/docker-deployment.md:355-420` ("Rotating Secrets", per-secret procedure) | PASS |
| R-18 | Bot token absent from aiogram exception strings / structured logs | Read `aiogram/exceptions.py` (`TelegramAPIError.url` is a `core.telegram.org` docs link, not the request URL) and `aiogram/client/session/aiohttp.py:173-176`; `prod.py` LOGGING sets root to WARNING, so `aiohttp.access` is never emitted | PASS |
| R-19 | No `csrf_exempt` anywhere; no `staff_member_required` in use | `Select-String` over `src/**` — 0 matches for both | PASS |
| R-20 | API gateway behaviour under a live nginx | Not exercised — nginx is profile-gated in dev and the dev stack is crash-looping; assessed statically from `docker/nginx/nginx.conf` and `nginx.dev.conf` | N/A |

> PASS results prove the audit was thorough; they are METHODOLOGY evidence, NOT findings.

**Tools used:** `Select-String` / `Grep` (source, aiogram + django-redis internals
in `.venv`), `git ls-files` / `git check-ignore`, `docker compose --project-name
mko-bazuna-test ... run --rm test` (2 targeted runs, 131 tests, all green), a
read-only outage probe (`python`, no DB, no network) run in the shipped image.

**Assumptions:** production uses the `django-redis` cache and aiogram
`RedisStorage`; `docker/nginx/nginx.conf` is the production proxy config and
`nginx.dev.conf` the dev one; `long-polling` (`dp.run_polling`, no args) means
aiogram's defaults apply — `handle_as_tasks=True`, `tasks_concurrency_limit=None`,
`DEFAULT_TIMEOUT=60.0`; Telegram rejects malformed entities in `parse_mode="HTML"`
(documented Bot API behaviour — not runtime-verified, no network).

**Cross-phase boundaries respected:** phase 02 owns settings/env/secret
*validation*; phase 06 owns PII minimisation and consent; phase 04 owns the
login token/session layer; phase 03 owns connection-pool behaviour; phase 07 owns
media. Findings below that touch those areas are scoped to the *integration
boundary* and are cross-referenced rather than re-argued.

## Findings Summary

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| API-001 | A cache (Redis) outage 500s every public page — the documented `site_config` fallback covers only the DB branch | HIGH | Open | Availability / graceful degradation |
| API-002 | All four bot rate limiters raise on a cache outage instead of failing open, unlike the dedup middleware | HIGH | Open | Resilience / availability |
| API-003 | The `contact_<ad_id>` deep link is unrated: any Telegram user can message any seller without limit and grow the DB unboundedly | HIGH | Open | Abuse control / resource exhaustion |
| API-004 | Telegram 429 backoff has no ceiling (900 s for one flood response), never retries network/5xx siblings, then reports the message as handled | HIGH | Open | Resilience / retry amplification |
| API-005 | `/media/` — the only public path that runs a per-request DB access check — has no nginx rate-limit zone | HIGH | Open | Abuse control / capacity |
| API-006 | Telegram alert messages are built with `parse_mode="HTML"` from unescaped seller text, so a title containing `<` silently kills that seller's alerts | MEDIUM | Open | Correctness / data integrity |
| API-007 | A failed translation is indistinguishable from a real one, so `backfill_translations` permanently writes the untranslated source into the English/Bosnian columns | MEDIUM | Open | Correctness / cost control |
| API-008 | `load_exchange_rates` reverts operator-edited rates on every container start, and no external rate feed exists at all | MEDIUM | Open | Data integrity / spec deviation |
| API-009 | Mandatory `EMAIL_HOST` in production is justified by flows that do not exist; an optional, fail-open integration can block the whole web tier from booting | MEDIUM | Open | Availability / spec deviation |
| API-010 | The nginx :80 catch-all redirects to `https://$host$request_uri`, so the redirect target is attacker-controlled | MEDIUM | Open | Security (open redirect) |
| API-011 | `BOT_TOKEN` is distributed to six containers and is actively used by the web and scheduler tiers, not only the bot | MEDIUM | Open | Least privilege |
| API-012 | `/save-search/` is the only query-persistence ingress that skips `redact_search_query()` | MEDIUM | Open | Privacy / consistency |
| API-013 | `immediate_alerts` dispatches fire-and-forget: unretrieved futures, an unbounded queue, and a shutdown that can outlast gunicorn's grace period | MEDIUM | Open | Reliability / observability |
| API-014 | API-contract drift: a `Bearer` challenge that is never satisfiable, manual POST guards, no versioning, unauthenticated `/metrics`, trusted `X-Forwarded-Host`, unpinned TLS parameters | LOW | Open | Maintainability / hardening |
| API-015 | `/csp-report/` logs the whole report — including `document-uri` and `referrer` — at INFO from an unauthenticated POST | LOW | Open | Log hygiene |
| API-016 | Runtime images use floating tags and the production TLS cert mount defaults to a host path that is empty on most hosts | LOW | Open | Deployment portability |
| API-017 | Translation logs seller free text with the non-redacting sanitiser, and breaker state is invisible to operators | LOW | Open | Observability / log hygiene |

## Distribution

**Severity counts**

| CRITICAL | HIGH | MEDIUM | LOW |
|----------|------|--------|-----|
| 0 | 5 | 8 | 4 |

**Status counts**

| Status | Count |
|--------|-------|
| Open | 17 |

> Note: Status is `Open` for all findings in raw phase reports. Phase 99 validation
> mutates Status to `Validated` / `Reclassified` / `Merged` / `Rejected` / `Deferred`.
> Values `Fixed` / `Verified` are forbidden here — they belong to a remediation
> tracker, not the audit report.

## Findings by Severity

### HIGH

#### API-001: [HIGH] — A cache (Redis) outage 500s every public page — the documented `site_config` fallback covers only the DB branch

| Field | Value |
|---|---|
| **ID** | API-001 |
| **Title** | A cache (Redis) outage 500s every public page — the documented `site_config` fallback covers only the DB branch |
| **Severity** | HIGH |
| **Category** | Availability / graceful degradation |
| **File(s)** | `src/backend/apps/core/services/site_config.py:27-37,56-66`, `src/backend/apps/core/utils/cache.py:60-70,104-114`, `src/backend/apps/core/context_processors.py:93,116`, `src/backend/apps/core/templatetags/telegram_tags.py:163` |
| **Type** | SPEC-DEVIATION |
| **Status** | Open |
| **Problem** | `get_site_name()` and `get_bot_username()` both read the cache *before* entering their `try` block, and the `try` only wraps the ORM call. `get_cached_site_config()` / `get_cached_bot_username()` are bare `cache.get()` calls with no exception handling, so a `django_redis.exceptions.ConnectionInterrupted` propagates straight out of both functions. Both are consumed by the `header_context` and `site_config` context processors, which run on **every** template render, and `telegram_deep_link` calls `get_bot_username()` a third time. Both docstrings promise "Falls back to 'Bazuna' if the DB or cache is unavailable (R-SN-05)" — the cache half of that contract is not implemented. |
| **Impact** | Redis is a single shared dependency of the web tier (rate-limit counters, cache invalidation, bot liveness marker, exchange-rate cache). If it becomes unreachable, every public page — listings, ad detail, search, privacy, the login page — returns HTTP 500 instead of degrading, and the "Entire country" header, the site name and every Telegram deep-link button disappear site-wide. The bot's `/start` greeting (`get_site_name_async`) breaks on the same dependency. The `readiness_check` correctly returns 503, so the container is *reported* unhealthy, but there is no working fallback behind that signal. |
| **Root Cause** | The cache was treated as an accelerator inside an already-fallible function, and the guard was written around the wrong call. The one consumer that did think about a cache outage — `UpdateIdDedupMiddleware` (API-002) — wraps `cache.add` in `try/except (ConnectionInterrupted, redis.RedisError)`; the read path was never given the same treatment. |
| **Recommendation** | Move the cache read inside the existing `try` (or wrap the whole body) in both `get_site_name()` and `get_bot_username()`, so the documented fallback is real for both the DB *and* the cache. Better: make the contract explicit once, in `apps/core/utils/cache.py` — a `cache_get_or_none(key)` helper that swallows `ConnectionInterrupted`/`RedisError` and returns `None` — and use it for every cached read on a request path (`get_cached_*`, `get_user_search_history`, `get_popular_suggestions`, `PriceNormalizer._get_current_rate`). Add a regression test that patches the cache to raise `ConnectionInterrupted` and asserts `/`, `/ads/<id>/` and `/login/issue/` still return 200. |
| **Effort** | S |
| **Priority** | P0 |
| **CWE** | CWE-400 (Uncontrolled Resource Consumption) — availability class; no CWE-703 applies because nothing is checked |
| **Likelihood** | MEDIUM |
| **Related Findings** | API-002, API-011 |

**Evidence — `src/backend/apps/core/services/site_config.py:26-37,55-66`** *(supports: "the cache read sits outside the `try`, so the documented fallback cannot fire for a cache outage")*:
```python
    cached = get_cached_site_config()      # <-- OUTSIDE the try
    if cached:
        return cached
    try:
        obj = SiteConfig.get_singleton()   # <-- only the ORM branch is guarded
        name = cast(str, obj.name)
        set_cached_site_config(name)
        return name
    except Exception:
        logger.warning("SiteConfig unavailable; falling back to 'Bazuna'")
        return "Bazuna"
```

**Evidence — outage probe (R-11), run in the shipped image against a patched cache** *(supports: "both functions raise `ConnectionInterrupted`, so every context-processor render 500s")*:
```text
=== PROBE 1: cache outage vs the documented site_config fallback ===
  get_bot_username() -> RAISED ConnectionInterrupted: Redis NoneType: None
  get_site_name() -> RAISED ConnectionInterrupted: Redis NoneType: None
```

**Evidence — `src/backend/apps/core/context_processors.py:93,116`** *(supports: "both un-guarded readers are on the every-request path")*:
```python
    return {
        "bot_username": get_bot_username(),      # header_context — every render
        ...
    }

def site_config(request) -> dict:
    from apps.core.services.site_config import get_site_name
    return {"site_name": get_site_name()}        # every render
```

---

#### API-002: [HIGH] — All four bot rate limiters raise on a cache outage instead of failing open, unlike the dedup middleware

| Field | Value |
|---|---|
| **ID** | API-002 |
| **Title** | All four bot rate limiters raise on a cache outage instead of failing open, unlike the dedup middleware |
| **Severity** | HIGH |
| **Category** | Resilience / availability |
| **File(s)** | `src/telegram_bot/services/rate_limit.py:62-65,116-119,166-169,216-219`, `src/telegram_bot/middlewares/update_id_dedup.py:58-68` |
| **Type** | SPEC-DEVIATION |
| **Status** | Open |
| **Problem** | All four abuse guards in `telegram_bot/services/rate_limit.py` (`check_login_rate_limit`, `check_contact_start_rate_limit`, `check_support_message_rate_limit`, `check_upload_rate_limit`) wrap the `cache.add` + `cache.incr` pair in `except ValueError` only. `django_redis` signals an unreachable server with `django_redis.exceptions.ConnectionInterrupted`, which is not a `ValueError`, so it escapes. The consequence is that during a cache outage every `/start login_<token>`, `/start contact_us`, support message and photo upload raises instead of degrading. The sibling module `UpdateIdDedupMiddleware` gets this right and documents the intended policy: "a Redis outage degrades to 'no dedup' rather than dropping legitimate traffic." |
| **Impact** | A cache outage therefore does not degrade the bot — it removes exactly the paths that are supposed to protect it. The login handshake stops completing, contact/support intake stops working, and photo upload stops. Because the rate limiters are the guard *against* the abuse in API-003, the two findings compound: the guard is the only thing standing between the site and a spam flood, and it fails closed at the worst possible moment while the same cache outage is also taking the web tier offline (API-001). |
| **Root Cause** | The `cache.add`/`cache.incr` idiom was copied across four call sites with a `ValueError`-only handler, and the fail-open policy that `update_id_dedup.py` documents was never generalised into a shared helper. Each copy re-derived the exception set from memory instead of from the cache backend's contract. |
| **Recommendation** | Introduce one `try/except` around the add/incr pair in a single shared private helper (e.g. `_bump_window(key, period, limit) -> bool`) and call it from all four guards, catching `(ConnectionInterrupted, redis.RedisError)` alongside `ValueError` and returning `True` (fail-open) with a `logger.warning`. This also removes the four-copy duplication flagged by phase 04 (`AUT-003` third `_get_client_ip` copy is the same anti-pattern in the web app). Add a test that patches the cache to raise `ConnectionInterrupted` and asserts each guard returns `True`. |
| **Effort** | S |
| **Priority** | P0 |
| **CWE** | CWE-703 (Improper Check or Handling of Exceptional Conditions) |
| **Likelihood** | MEDIUM |
| **Related Findings** | API-001, API-003 |

**Evidence — `src/telegram_bot/services/rate_limit.py:206-219`** *(supports: "the handler catches `ValueError` only, so `ConnectionInterrupted` escapes")*:
```python
    try:
        added = cache.add(key, 1, timeout=period)
        if added:
            current = 1
        else:
            current = cache.incr(key)
        return current <= limit
    except ValueError:
        # Key expired between the add/incr calls — treat as a fresh start.
        cache.set(key, 1, timeout=period)
        return True
```

**Evidence — `src/telegram_bot/middlewares/update_id_dedup.py:58-68`** *(supports: "the fail-open policy is documented and implemented in exactly one of the five cache consumers")*:
```python
        try:
            added = await sync_to_async(cache.add)(
                f"bot_update:{update_id}", 1, timeout=DEDUP_TTL_SECONDS
            )
        except (ConnectionInterrupted, redis.RedisError):
            logger.warning(
                "Cache backend unavailable — skipping dedup guard for "
                "update_id=%s (fail-open)", update_id,
            )
            return await handler(event, data)
```

**Evidence — outage probe (R-12)** *(supports: "all four guards raise, none fail open")*:
```text
=== PROBE 1b: does the same outage break the bot rate limiters? ===
  check_login_rate_limit -> RAISED ConnectionInterrupted: Redis NoneType: None
  check_contact_start_rate_limit -> RAISED ConnectionInterrupted: Redis NoneType: None
  check_support_message_rate_limit -> RAISED ConnectionInterrupted: Redis NoneType: None
  check_upload_rate_limit -> RAISED ConnectionInterrupted: Redis NoneType: None
```

---

#### API-003: [HIGH] — The `contact_<ad_id>` deep link is unrated: any Telegram user can message any seller without limit and grow the DB unboundedly

| Field | Value |
|---|---|
| **ID** | API-003 |
| **Title** | The `contact_<ad_id>` deep link is unrated: any Telegram user can message any seller without limit and grow the DB unboundedly |
| **Severity** | HIGH |
| **Category** | Abuse control / resource exhaustion |
| **File(s)** | `src/telegram_bot/handlers/contact.py:113-121,179-239`, `src/telegram_bot/services/rate_limit.py:73-119`, `src/backend/apps/core/services/contact.py:97-115`, `src/backend/templates/ads/detail.html:169` |
| **Type** | BEST-PRACTICE |
| **Status** | Open |
| **Problem** | `handle_contact_start` routes two very different deep links through one regex block. The `contact_us` branch is protected by `check_contact_start_rate_limit` (5 per 10 min). The `contact_<ad_id>` branch has **no rate limit of any kind** — not per user, not per ad, not global. Each hit performs a DB read (`get_seller_for_contact`), an `AnalyticsEvent` INSERT (`record_contact_initiated`), and an **outbound Telegram `send_message` to the seller**. The identifier space is a dense, trivially enumerable small integer (`ad_id`), and the link is rendered on the anonymously reachable ad detail page. `AccountStateMiddleware` explicitly *widens* access here: it lets `is_declined` users through when `classify_contact_deep_link` matches, so even a browse-only account can drive the loop. |
| **Impact** | Any Telegram account can flood every seller with "New request from a buyer!" messages by iterating `/start contact_1 … contact_N`, and can inflate `analytics_events` without bound. Seller spam is the direct harm; the follow-on harm is a flood-control response from Telegram, which lands in `retry_transient` and triggers the retry amplification in API-004. `ContactRequest`-style abuse also inflates the `CONTACT_INITIATED` counter that `TrustCalculator` reads, so the seller's trust score is damaged by the attack. |
| **Root Cause** | The rate limiter was added for the *support-desk* deep link (which is the one that was reported as abusive) and never generalised to the sibling branch in the same handler. The two branches share a regex block and a name (`ContactDeepLinkKind`) but not a guard. |
| **Recommendation** | Add a `check_contact_forward_rate_limit(message.from_user.id)` guard to the `contact_<ad_id>` branch, mirroring `check_contact_start_rate_limit` (suggest 5 / 600 s per buyer, plus a separate, tighter per-seller cap of ~20 / 3600 s keyed on the ad owner so one buyer cannot be the only defence). Reuse the existing helper rather than adding a fifth copy of the add/incr idiom. Because the seller-facing send is the expensive part, the per-seller cap is the one that actually protects sellers. Add a test asserting the 6th `contact_<ad_id>` trigger from one user is refused and that no `send_message` is issued. |
| **Effort** | S |
| **Priority** | P0 |
| **CWE** | CWE-799 (Improper Control of Interaction Frequency) |
| **Likelihood** | HIGH |
| **Related Findings** | API-002, API-004, API-011 |

**Evidence — `src/telegram_bot/handlers/contact.py:113-121`** *(supports: "only the `contact_us` branch is rate-limited; `contact_<ad_id>` has no guard")*:
```python
    if CONTACT_US_PATTERN.match(deep_link):
        return await handle_contact_us_start(message, bot)   # -> check_contact_start_rate_limit
    match = CONTACT_PATTERN.match(deep_link)
    if not match:
        return False  # Not a contact deep-link
    ad_id = int(match.group(1))
    return await handle_contact(message, bot, ad_id)        # -> NO rate limit
```

**Evidence — `src/telegram_bot/handlers/contact.py:206-232`** *(supports: "each unrated hit writes a row and sends a Telegram message to the seller")*:
```python
    is_available, seller_telegram_id = await handle_contact_orm(
        ad_id=ad_id, buyer_telegram_id=buyer_telegram_id,
    )                                     # record_contact_initiated() -> AnalyticsEvent INSERT
    ...
    await bot.send_message(               # outbound message to the seller
        chat_id=seller_telegram_id,
        text=(_("New request from a buyer!...") % {"buyer": ANONYMOUS_BUYER_LABEL, "ad_id": ad_id}),
    )
```

**Evidence — `Select-String` over `src/`** *(supports: "the limiter exists but is only ever called from the `contact_us` branch")*:
```text
src/telegram_bot/handlers/contact.py:156:    if not await check_contact_start_rate_limit(message.from_user.id):
src/telegram_bot/handlers/support.py:83:    if not await check_support_message_rate_limit(callback.from_user.id):
src/telegram_bot/handlers/login.py:113:    if not await check_login_rate_limit(message.from_user.id):
src/telegram_bot/handlers/ad_create/photos.py:79:    if user_id is not None and not await check_upload_rate_limit(user_id):
# zero call sites for any limiter on the contact_<ad_id> branch
```

**Evidence — `src/backend/templates/ads/detail.html:169`** *(supports: "the deep link is rendered on the anonymously reachable ad page, so the id space is public")*:
```html
{% telegram_deep_link "contact" ad.id classes="inline-block px-6 py-3 bg-blue-600 ..." %}
```

---

#### API-004: [HIGH] — Telegram 429 backoff has no ceiling (900 s for one flood response), never retries network/5xx siblings, then reports the message as handled

| Field | Value |
|---|---|
| **ID** | API-004 |
| **Title** | Telegram 429 backoff has no ceiling (900 s for one flood response), never retries network/5xx siblings, then reports the message as handled |
| **Severity** | HIGH |
| **Category** | Resilience / retry amplification |
| **File(s)** | `src/telegram_bot/retry.py:32-33,43-91`, `src/telegram_bot/main.py:79-88` |
| **Type** | SPEC-DEVIATION |
| **Status** | Open |
| **Problem** | Three defects in one 40-line handler. (1) **No ceiling on the mandated wait.** `delay = float(exc.retry_after)` is used verbatim and slept `_MAX_RETRIES` (3) times inside the loop, so one flood response with `retry_after=300` pins the update task for 900 s. (2) **The declared transient set is never reached.** `main.py` registers the handler as `ExceptionTypeFilter(TelegramRetryAfter)`, and `retry_transient` returns `False` for anything else — so `TelegramNetworkError` and `TelegramServerError`, both listed in `_TRANSIENT_EXCEPTIONS` and both handled inside the replay loop, can never *enter* the handler. Only the 429 path retries; a Telegram 5xx or network blip drops every confirmation. (3) **Terminal failure is reported as success.** After exhausting retries the handler returns `True`, which `ErrorsMiddleware` interprets as "handled", so the exception is swallowed and `_process_update` never logs it. The only trace is a `logger.warning` on the `telegram_bot` logger. |
| **Impact** | (1) A single flood response holds one update task for up to 15 minutes; because `dp.run_polling` is called with no arguments, aiogram uses `handle_as_tasks=True` with `tasks_concurrency_limit=None`, so nothing bounds how many tasks can be in that state at once — N concurrent 429s become 3N replayed outbound calls, which is the opposite of what flood control asks for. (2) During a Telegram 5xx window every seller-facing message (confirmations, "ad submitted", "language set", contact notifications) is lost, with only an ERROR traceback and no replay. (3) Because the drop is invisible to the generic handler, there is no single log line that says "N messages were dropped"; an operator sees nothing until sellers complain. |
| **Root Cause** | The handler was written for one exception type and its signature (`ExceptionTypeFilter(TelegramRetryAfter)`) locks that in, while the body was written as if it handled a family. Nothing asserts that `_TRANSIENT_EXCEPTIONS` is reachable, and returning `True` after exhaustion was chosen to suppress a re-raise that was never wanted in the first place. |
| **Recommendation** | (1) Cap the wait: `delay = min(float(exc.retry_after or 0), _MAX_BACKOFF_SECONDS)` with `_MAX_BACKOFF_SECONDS = 5.0`, and cap the loop's *total* budget rather than the attempt count. (2) Register the handler for the whole transient family — `ExceptionTypeFilter(_TRANSIENT_EXCEPTIONS)` — and delete the `if not isinstance(exc, TelegramRetryAfter): return False` guard so the body matches its own constant; the mandatory `retry_after` sleep is already handled by the `getattr(exc, "retry_after", None)` branch. (3) Return `False` on exhaustion so `ErrorsMiddleware` re-raises and `_process_update` logs the drop, and add a counter (`telegram_bot` logger + a Prometheus gauge) so "messages dropped" is a signal. Add tests for a 429 with `retry_after=600` (assert total sleep is bounded) and for a `TelegramServerError` (assert the method is replayed). |
| **Effort** | S |
| **Priority** | P0 |
| **CWE** | CWE-770 (Allocation of Resources Without Limits or Throttling) |
| **Likelihood** | MEDIUM |
| **Related Findings** | API-003, API-013 |

**Evidence — `src/telegram_bot/retry.py:55-64`** *(supports: "the full `retry_after` is used verbatim and repeated three times, and the entry guard admits only `TelegramRetryAfter`")*:
```python
    exc = event.exception

    if not isinstance(exc, TelegramRetryAfter):     # TelegramNetworkError / TelegramServerError
        return False                                # can never reach the loop below
    for attempt in range(1, _MAX_RETRIES + 1):      # _MAX_RETRIES = 3
        delay = float(exc.retry_after) if getattr(exc, "retry_after", None) else _BACKOFF_BASE
        await asyncio.sleep(delay)                  # no ceiling
        try:
            await bot(exc.method)
```

**Evidence — `src/telegram_bot/retry.py:36-40,86-91`** *(supports: "the declared transient set includes the two siblings that the entry guard excludes, and exhaustion is reported as handled")*:
```python
_TRANSIENT_EXCEPTIONS: Final[tuple[type[AiogramError], ...]] = (
    TelegramRetryAfter,
    TelegramNetworkError,   # declared, never reachable as an entry condition
    TelegramServerError,    # declared, never reachable as an entry condition
)
...
    logger.warning(
        "Exhausted %d retries for outbound call %s; marking handled",
        _MAX_RETRIES, type(exc.method).__name__,
    )
    return True      # -> ErrorsMiddleware treats this as handled; no re-raise, no ERROR log
```

**Evidence — `src/telegram_bot/main.py:88`** *(supports: "the registration filter locks the handler to one exception type")*:
```python
    dp.errors(ExceptionTypeFilter(TelegramRetryAfter))(retry_transient)
```

**Evidence — outage probe (R-13), `asyncio.sleep` instrumented** *(supports: "one 429 with `retry_after=300` costs 900 s and ends in a false success")*:
```text
=== PROBE 2: Telegram 429 (retry_after=300) -> total sleep in retry_transient ===
  sleeps=[300.0, 300.0, 300.0] total=900s handled=True
```

---

#### API-005: [HIGH] — `/media/` — the only public path that runs a per-request DB access check — has no nginx rate-limit zone

| Field | Value |
|---|---|
| **ID** | API-005 |
| **Title** | `/media/` — the only public path that runs a per-request DB access check — has no nginx rate-limit zone |
| **Severity** | HIGH |
| **Category** | Abuse control / capacity |
| **File(s)** | `docker/nginx/nginx.conf:80-87,170-178`, `docker/nginx/nginx.dev.conf`, `src/backend/apps/ads/views/listings.py:155-215`, `src/backend/apps/ads/urls.py:21` |
| **Type** | BEST-PRACTICE |
| **Status** | Open |
| **Problem** | Every public path in the production proxy has a rate-limit zone — `location /login/`, `/search/`, `/moderation/`, `/csp-report/` each declare `limit_req`, and the catch-all `location /` has `limit_req zone=browse_limit burst=40 nodelay`. `location /media/` declares none. Because nginx resolves the *longest* matching prefix, a `/media/…` request never falls through to `location /`, so the missing zone is not inherited — it is simply absent. (`/static/` is also unrated but is served by whitenoise with no DB work, so the omission there is harmless.) The route behind it is `media_gate`, which per request validates the storage key, queries `AdImage` (including the three thumbnail-key fallbacks), then queries the parent `Ad` and its `user` to decide 200 / 403 / 404. |
| **Impact** | A single client can drive arbitrary request volume through the most expensive anonymous endpoint in the application — every hit is at least two indexed ORM queries plus Django middleware — bypassing the 20 r/s + burst 40 budget that every other public path is held to. Because `media_gate` responses are `Cache-Control: no-store`, no shared cache absorbs the repetition either. The nginx rate-limit zones are the only capacity control in front of a 3-worker gunicorn pod with `cpus: 1.5` and `mem_limit: 512m`; losing it on this path converts a modest scraper into a database-pressure event. |
| **Root Cause** | Rate-limit zones were added per-endpoint as each abuse was reported (the comments name `R8 hardening` and `EXT-003 hardening`), and `/media/` was added to the config for the access-control proxy pass without a matching `limit_req`. The catch-all zone was assumed to cover it. |
| **Recommendation** | Add `limit_req zone=browse_limit burst=40 nodelay;` to `location /media/` in both `nginx.conf` and `nginx.dev.conf`, and — since the point of the zone is to protect the DB rather than the user — a **tighter, separate** zone is the better shape: `limit_req_zone $binary_remote_addr zone=media_limit:10m rate=30r/s;` with `burst=60 nodelay`. Keep `$binary_remote_addr` (do not switch to `$proxy_add_x_forwarded_for`; see phase 04's `AUT-003` for why the XFF-first form is bypassable). Then assert the zone assignment in a test that parses the shipped config, so the next `location` block added cannot silently miss one. |
| **Effort** | S |
| **Priority** | P0 |
| **CWE** | CWE-770 (Allocation of Resources Without Limits or Throttling) |
| **Likelihood** | MEDIUM |
| **Related Findings** | API-014 |

**Evidence — `docker/nginx/nginx.conf:80-87,170-178`** *(supports: "`/media/` has no `limit_req`; the longest-match rule means `location /` does not cover it")*:
```nginx
        # Media files proxied to Django for per-request access control
        location /media/ {
            proxy_pass http://web:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }                                    # <-- no limit_req
        ...
        # Reverse proxy to Django web service
        location / {
            limit_req zone=browse_limit burst=40 nodelay;   # <-- never reached for /media/
            proxy_pass http://web:8000;
        }
```

**Evidence — `docker/nginx/nginx.conf:24-26`** *(supports: "the zones a new location block is expected to pick from all key on the real client IP")*:
```nginx
    limit_req_zone $binary_remote_addr zone=login_limit:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=search_limit:10m rate=20r/s;
    limit_req_zone $binary_remote_addr zone=browse_limit:10m rate=20r/s;
```

**Evidence — `src/backend/apps/ads/urls.py:21` + `src/backend/apps/ads/views/listings.py:186-194`** *(supports: "the unrated path is a DB-backed access-control gate, not a static file")*:
```python
    path("media/<path:image_key>", media_gate, name="media_gate"),
...
    if request.user.is_staff:
        if settings.DEBUG:
            response = _serve_image(image_key)
            response["Cache-Control"] = "no-cache"
            return response
        response = HttpResponse()
        response["X-Accel-Redirect"] = f"/protected-media/{image_key}"
        response["Cache-Control"] = "no-store"     # no shared cache absorbs repeats
        return response
```

---

### MEDIUM

#### API-006: [MEDIUM] — Telegram alert messages are built with `parse_mode="HTML"` from unescaped seller text, so a title containing `<` silently kills that seller's alerts

| Field | Value |
|---|---|
| **ID** | API-006 |
| **Title** | Telegram alert messages are built with `parse_mode="HTML"` from unescaped seller text, so a title containing `<` silently kills that seller's alerts |
| **Severity** | MEDIUM |
| **Category** | Correctness / data integrity |
| **File(s)** | `src/backend/apps/search/services/immediate_alerts.py:134-161,207,232`, `src/backend/apps/search/management/commands/send_alerts.py:223-239,188,207`, `src/backend/apps/ads/models.py:48-65,502-512` |
| **Type** | BEST-PRACTICE |
| **Status** | Open |
| **Problem** | Both alert builders interpolate seller-authored text straight into an HTML-parse-mode message. `build_alert_message` does `f"<b>{title}</b>"` and `f'<a href="{ad.get_absolute_url()}">…</a>'`; `_format_digest` does `f"• {ad.get_title(locale)[:50]}"`. `Ad.title` / `title_bs` / `title_en` are `CharField`s with no `escape`, `strip_tags` or `conditional_escape` anywhere on the write path (`submit_ad` assigns `ad.title = input.title_ru` verbatim), and neither alert module imports `html` or `django.utils.html`. Neither module escapes. The resulting string is sent with `parse_mode="HTML"`. |
| **Impact** | Telegram rejects a message whose entities cannot be parsed with `400 Bad Request: can't parse entities`, which both modules classify as a **permanent** failure and log at WARNING with no retry. The practical outcome: any seller whose title contains `<`, `>` or `&` never receives a single saved-search alert for any of their ads, and neither the seller nor the buyer sees any symptom — `SavedSearchNotification` rows are still created, so the system reports the alert as delivered. The mirror risk is that a title containing `<a href="…">` becomes a clickable link in an alert message, letting a seller inject arbitrary link markup into every subscriber's chat. |
| **Root Cause** | The messages are assembled as HTML strings rather than sent with the default (plain-text) `parse_mode`, and nothing in the chain treats seller text as untrusted. The project's own `localized_content` templatetag and Django templates escape by default; the Telegram path bypassed that discipline entirely. |
| **Recommendation** | Two viable shapes; pick one and apply it to both modules. (a) Drop `parse_mode="HTML"` and send plain text (the bold/anchor formatting is cosmetic; `contact.py` already does exactly this). (b) Keep HTML and escape every interpolation with `django.utils.html.escape` — `escape(title)`, `escape(city_name)`, `escape(price_str)` — and use the unescaped values only for `<a href>`/`<b>` structure. Add a test that builds a message from a title of `Bike <b>new</b> & fast` and asserts the body contains no raw `<b>new</b>` (i.e. the seller's markup is escaped) and that the module no longer references `parse_mode` without escaping. |
| **Effort** | S |
| **Priority** | P1 |
| **CWE** | CWE-116 (Improper Encoding or Escaping of Output) |
| **Likelihood** | MEDIUM |
| **Related Findings** | API-013 |

**Evidence — `src/backend/apps/search/services/immediate_alerts.py:134-149`** *(supports: "seller text is interpolated into an HTML message with no escaping")*:
```python
    with translation_override(locale):
        title = ad.get_title(locale) or _("Ad")
        city_name = ad.city.get_name(locale) if ad.city else "—"
        price_str = format_price_value(ad.price_amount, ad.price_currency) or _("Price not specified")
        lines = [
            f"<b>{title}</b>",                       # <-- seller text, unescaped
            f"📍 {city_name}",
            f"💰 {price_str}",
            "",
            f'<a href="{ad.get_absolute_url()}">{view_ad_label}</a>',
        ]
```

**Evidence — `src/backend/apps/search/services/immediate_alerts.py:210-215`** *(supports: "an unparseable message is treated as a permanent failure and dropped, so the seller is never told")*:
```python
                except (TelegramBadRequest, TelegramForbiddenError) as exc:
                    # Permanent failures — dead-letter (no retry).
                    logger.warning(
                        "Permanent immediate alert failure to chat %s: %s",
                        payload["chat_id"], exc,
                    )
```

**Evidence — `Select-String -Path <both alert modules> -Pattern "escape|html|sanitize"`** *(supports: "no escaping helper is imported by either module; the only hits are the `parse_mode` lines")*:
```text
Path                                                                                LineNumber
immediate_alerts.py                                                                  207   parse_mode="HTML"
immediate_alerts.py                                                                  232   parse_mode="HTML"
send_alerts.py                                                                       188   parse_mode="HTML"
send_alerts.py                                                                       207   parse_mode="HTML"
# zero matches for "escape", "html." or "sanitize"
```

**Evidence — outage probe (R-14), message body built from a seller title `Bicikl <red> "novi" & taчке`** *(supports: "the raw markup reaches the wire")*:
```text
  message body:
    | <b>Bicikl <red> "novi" & tачке</b>
    | Paket 100 EUR
    | <a href="https://site/ads/1/">Pogledaj</a>
  'html' module imported by immediate_alerts/send_alerts? False
```

**Note on verification limits:** the *absence of escaping* is runtime-verified
(R-14). Telegram's rejection of unparseable entities is documented Bot API
behaviour and could **not** be exercised here — the dev bot container is
crash-looping on a placeholder `BOT_TOKEN`, so no real API call was made.

---

#### API-007: [MEDIUM] — A failed translation is indistinguishable from a real one, so `backfill_translations` permanently writes the untranslated source into the English/Bosnian columns

| Field | Value |
|---|---|
| **ID** | API-007 |
| **Title** | A failed translation is indistinguishable from a real one, so `backfill_translations` permanently writes the untranslated source into the English/Bosnian columns |
| **Severity** | MEDIUM |
| **Category** | Correctness / cost control |
| **File(s)** | `src/backend/apps/ads/services/submission.py:120-137`, `src/backend/apps/ads/management/commands/backfill_translations.py:97-102,163-180,221-231`, `src/backend/apps/core/services/translation.py:301-327,353-358` |
| **Type** | SPEC-DEVIATION |
| **Status** | Open |
| **Problem** | The graceful-degradation contract ("store the original, never crash") is correct, but it is implemented without a **marker**. `translate_text` returns the unmodified source on every failure path (empty body, exhausted breaker, non-2xx, invalid API key, timeout). Callers cannot tell that from a translation. `submit_ad` assigns the return value to `title_bs` / `title_en` unconditionally, and `backfill_translations._translate_for_backfill` does the same and then filters on `title_en__isnull=True` / `Q(title_bs__isnull=True)`. Once the original text is written into a locale column, the row is no longer "missing" a translation, so the backfill never revisits it. There is also no column, timestamp, log count or metric recording how many ads were served a fallback, and no per-run budget: `_translate_for_backfill` is called up to four times per ad with a 0.5 s client timeout and no rate limiting, bounded only by the 1800 s `SCHEDULER_COMMAND_TIMEOUT`. |
| **Impact** | If Google Translate is unavailable, mis-keyed, or rate-limited when a backfill runs, the command writes the **Russian source text into the English and Bosnian columns for every remaining ad** and reports `done=0 errors=0` — a silent success. The English and Bosnian pages then serve Russian copy, and the damage is permanent because the selection filter no longer matches. Separately, a large catalogue produces up to 4N API calls in one run: past 1800 s `migrate_locked` raises `TimeoutExpired`, the one-shot `migrate` service exits non-zero, and a deploy is blocked with the backfill only partially applied. |
| **Root Cause** | The degradation path returns a *value* where the caller needs a *status*. `translate_text` has no way to say "this is the original", so the backfill's "is a translation missing?" query is derived from field nullability, which the fallback quietly satisfies. |
| **Recommendation** | Make the status explicit rather than inferring it. Minimal: have `_translate_for_backfill` compare the result to the source and, on equality, leave the column `NULL` and count the row into a `fallback=0` counter that the command's summary line and a `logger.warning` both report — so a partially-degraded run is visible and re-runnable. Better: add a `TranslatedText`-style result object (or a `bool` out-param) so `translate_text` can distinguish the two, and record a `translation_failed_at` timestamp on the ad so the backfill can target retries. Independently: bound the backfill by *work*, not by wall clock — process at most N ads per invocation, print a progress line every 25 rows, and expose `--limit` / `--dry-run`, so a large catalogue is backfilled over several deploys instead of timing out and failing one. |
| **Effort** | M |
| **Priority** | P1 |
| **CWE** | CWE-703 (Improper Check or Handling of Exceptional Conditions) |
| **Likelihood** | MEDIUM |
| **Related Findings** | API-017 |

**Evidence — `src/backend/apps/ads/services/submission.py:120-137`** *(supports: "the return value is written to both locale columns with no marker")*:
```python
    ad = Ad.objects.create(
        ...,
        title_bs=input.title_bs or bs_title,   # bs_title == the Russian source on failure
        title_en=input.title_en or en_title,   # en_title == the Russian source on failure
        ...
    )
```

**Evidence — `src/backend/apps/ads/management/commands/backfill_translations.py:221-231`** *(supports: "the backfill's 'is a translation missing' test is column nullability, which the fallback satisfies")*:
```python
    qs = Ad.objects.filter(title_en__isnull=True) | Ad.objects.filter(
        Q(title_bs__isnull=True)
    )
    for index, ad in enumerate(qs.iterator(chunk_size=50), start=1):
        for title_field, title, body_field, body in (
            ("title_en", ad.title_en, "description_en", ad.description_en),
            ("title_bs", ad.title_bs, "description_bs", ad.description_bs),
        ):
            if title:
                updates[title_field] = await to_thread(
                    _translate_for_backfill, title, target_lang=TRANSLATION_TARGETS[title_field]
                )
```
Combined with `_translate_for_backfill` (lines 163-180), which is
`return str(await to_thread(translate_text, text, target_lang=target_lang))` — i.e.
it returns the source verbatim whenever the translator is down, and the caller
stores it in the locale column as though it were a translation.

**Evidence — `src/backend/apps/ads/management/commands/backfill_translations.py:97-102`** *(supports: "the command is bounded only by the wall clock")*:
```python
    if dry_run:
        logger.info("DRY RUN: would backfill up to %d ads (limit=%s)", MAX_ADS, limit)
        return

    # Translate outside the lock (releases the advisory lock, holds only the loop's snapshot)
    asyncio.run(run_backfill(qs))
```
…with `migrate_locked.main()` invoking it inside `advisory_lock(AdvisoryLockId.MIGRATE)`
and passing `timeout=command_timeout` (default 1800 s). No `--limit`, no batching,
no progress logging between the "Starting" and "Completed" summary lines.

---

#### API-008: [MEDIUM] — `load_exchange_rates` reverts operator-edited rates on every container start, and no external rate feed exists at all

| Field | Value |
|---|---|
| **ID** | API-008 |
| **Title** | `load_exchange_rates` reverts operator-edited rates on every container start, and no external rate feed exists at all |
| **Severity** | MEDIUM |
| **Category** | Data integrity / spec deviation |
| **File(s)** | `src/backend/apps/currencies/management/commands/load_exchange_rates.py:30-40,62-73`, `src/backend/apps/currencies/models.py:41-56,58-90`, `src/backend/apps/core/management/commands/bootstrap_reference_data.py:32,56` |
| **Type** | DOC-UPDATE |
| **Status** | Open |
| **Problem** | Two coupled issues. **(a) The rates are hard-coded.** `INITIAL_RATES` is a three-entry literal `("EUR","1.0") / ("BAM","0.512") / ("RSD","0.0105")` with `EFFECTIVE_DATE = date(2026, 8, 22)` and `SOURCE = "manual_seed"`. There is no HTTP client, no scheduler task and no network call anywhere in `apps/currencies` — the command's own docstring says it exists because a data migration "cannot be regenerated from model state", and the model docstring says it "is designed to **later** accept automated rate updates from an official source (e.g. ECB)". Today it is a manual seed, not a data dependency. **(b) The seed overwrites operator edits on every boot.** `load_exchange_rates` runs inside `bootstrap_reference_data.migrate_locked.main()`, which is the `migrate` one-shot's `command` on **every** `docker compose up` and every deploy, under `advisory_lock(AdvisoryLockId.MIGRATE)`. It does `update_or_create(currency=code, defaults={...})`, matched on the unique `currency` field, so an existing row is always rewritten. `PriceNormalizer.invalidate_rate_cache()` exists but has **zero callers in `src/`**, so the 5-minute Redis rate cache also keeps serving the pre-boot value until it expires on its own. |
| **Impact** | Any rate an operator corrects in Django admin (a real scenario — the seed is dated and EUR→BAM drifts) is silently reverted at the next deploy, with no log line above INFO and no record of the previous value. Meanwhile every `price_normalized_eur` computed from the pre-edit rate stays wrong, because the seed does not re-run `recompute_normalized_prices` — the rate table and the derived column drift apart. And the phase-level assumption that this is "a third-party data dependency with a scheduled refresh" is **not true of the code**; anyone sizing the system's egress or failure modes from that assumption is wrong in both directions. |
| **Root Cause** | Idempotence was implemented as "make the row look like the constant" rather than "create it if absent". `update_or_create` is idempotent for the *seed* value, which is precisely the wrong property for a value an operator is expected to be able to correct. |
| **Recommendation** | Separate the two jobs. Keep the constant as a **bootstrap default**: change the command to `get_or_create(currency=code, defaults={...})` so an existing row is never rewritten, and log the rate in use together with whether it came from the seed or a prior edit. If the intent really is "the seed is authoritative", make `rate_to_eur` read-only in the admin and say so in the docstring — right now the code supports neither reading. Independently: either drop the "external feed" claim from the docs, or add the fetch (`--remote` against ECB, writing `source`/`effective_date` plus a history row) so the claim becomes true. Either way, call `invalidate_rate_cache()` when a rate does change — it is already written and already correct; it has simply never been wired up. |
| **Effort** | S (doc + `get_or_create`) / L (if the remote feed is genuinely wanted) |
| **Priority** | P1 |
| **CWE** | CWE-665 (Improper Initialization) |
| **Likelihood** | HIGH |
| **Related Findings** | API-017 |

**Evidence — `src/backend/apps/currencies/management/commands/load_exchange_rates.py:27-35,50-63`** *(supports: "hard-coded rates, overwritten by `update_or_create` on every run, cache never invalidated")*:
```python
EFFECTIVE_DATE = date(2026, 8, 22)
SOURCE = "manual_seed"

# (ISO code, rate_to_eur as string to preserve decimal precision)
INITIAL_RATES: tuple[tuple[str, str], ...] = (
    ("EUR", "1.0"),
    ("BAM", "0.512"),
    ("RSD", "0.0105"),
)
...
        for currency_code, rate_to_eur in INITIAL_RATES:
            obj, was_created = ExchangeRate.objects.update_or_create(
                currency=currency_code,
                defaults={
                    "rate_to_eur": rate_to_eur,       # an operator's edit lands in "updated"
                    "effective_date": EFFECTIVE_DATE,  # and is overwritten with no warning
                    "source": SOURCE,
                    "is_current": True,
                },
            )
```

**Evidence — runtime observation from the test container bootstrap (R-15)** *(supports: "the command always reports updates, never creates, on a warm database")*:
```text
Updated EUR: rate_to_eur=1.0
Updated BAM: rate_to_eur=0.512
Updated RSD: rate_to_eur=0.0105
Exchange rates loaded: 0 created, 3 updated
```

**Evidence — `grep invalidate_rate_cache` over the repo** *(supports: "the invalidation helper is implemented and has no caller in `src/`")*:
```text
src/backend/apps/currencies/services/price_normalizer.py:111:    def invalidate_rate_cache(currency: CurrencyCode) -> None:
(no other hit outside docs/ and this report)
```

**Evidence — `src/backend/apps/currencies/models.py:1-8`** *(supports: "no external source exists today; the feed is aspirational")*:
```python
"""
ExchangeRate model for Mko Bazuna.

Single source of truth for the current exchange rate of each supported
currency relative to EUR. Only ``is_current=True`` rows are used for price
normalization. The model is designed to later accept automated rate updates
from an official source (e.g. ECB) without a schema change.
"""
```

---

#### API-009: [MEDIUM] — Mandatory `EMAIL_HOST` in production is justified by flows that do not exist; an optional, fail-open integration can block the whole web tier from booting

| Field | Value |
|---|---|
| **ID** | API-009 |
| **Title** | Mandatory `EMAIL_HOST` in production is justified by flows that do not exist; an optional, fail-open integration can block the whole web tier from booting |
| **Severity** | MEDIUM |
| **Category** | Availability / spec deviation |
| **File(s)** | `src/backend/config/settings/prod.py:197-208`, `src/backend/apps/currencies/management/commands/create_admin.py:73-79`, `src/telegram_bot/services/support_delivery_email.py:88-118` |
| **Type** | DOC-UPDATE |
| **Status** | Open |
| **Problem** | `prod.py` raises `ImproperlyConfigured` at import when `EMAIL_HOST` is empty, citing "transactional emails (password resets, alert notifications, seller confirmations) must be deliverable." None of those three flows exists. Verified: `send_mail` has exactly **one** call site in the whole codebase — `support_delivery_email.deliver_support_ticket_email`, the bot's support-desk notification to the admin inbox — and `set_password` has exactly one, in `create_admin.py` for the first superuser. There is no password-reset view, URL, template or `token_generator` anywhere; there is no e-mail alert (alerts are Telegram, both the instant fan-out and the daily digest) and no e-mail seller confirmation (publishing is a Telegram reply). The only e-mail consumer is explicitly fail-open: `deliver_support_ticket_email` catches `Exception` and logs `"Support email delivery failed (continuing)"`. |
| **Impact** | `ImproperlyConfigured` at settings import means the web, bot, scheduler and every one-shot container fail to start. So a *fail-open, best-effort, single-purpose* integration has been made a hard boot gate for the entire system, justified by a rationale the codebase does not support. A staging or DR host that can serve the site perfectly well without SMTP now cannot boot; and a legitimate reason to demand SMTP on a new production host (compliance? a support SLA?) is invisible to whoever writes the next ops runbook, because the stated reason is fictional. |
| **Root Cause** | The guard was authored from a feature roadmap (there *was* a planned password-reset flow) rather than from the flows present in the tree, and the fail-open behaviour of the one real consumer was not read before making the dependency mandatory. |
| **Recommendation** | Fix the comment to name the one real consumer, and make the guard match the actual blast radius. Two coherent options: (a) keep it mandatory but justify it correctly — "the support-desk notification is the only transactional e-mail; without it seller escalations are silently lost" — and state that loudly in `docs/ops/docker-deployment.md`; or (b) demote it to a warning (`logger.warning` at settings import) so the site boots and only the support-desk e-mail degrades, which is what the code actually does today. Given the delivery path already fails open, (b) is the option that matches the code's own behaviour; if (a) is preferred for operational discipline, that is a defensible product decision, but the reason must be the real one. |
| **Effort** | S |
| **Priority** | P2 |
| **CWE** | CWE-703 (Improper Check or Handling of Exceptional Conditions) |
| **Likelihood** | MEDIUM |
| **Related Findings** | API-012 |

**Evidence — `src/backend/config/settings/prod.py:197-208`** *(supports: "the boot gate names three flows, none of which exists")*:
```python
    # Email — transactional emails (password resets, alert notifications, seller
    # confirmations) must be deliverable in production.
    email_host = env("EMAIL_HOST", default="").strip()
    if not email_host:
        raise ImproperlyConfigured("EMAIL_HOST must be set in production")
```

**Evidence — `grep send_mail|EmailMessage|password_reset|PasswordReset|set_password|token_generator` over `src/`** *(supports: "one e-mail call site (the support ticket) and one password write (the initial admin), so the two named flows do not exist")*:
```text
src/telegram_bot/services/support_delivery_email.py:99:        send_mail(          # the only send_mail in the codebase
src/backend/apps/currencies/management/commands/create_admin.py:77:    user.set_password(password)   # the only password write; local, no e-mail
# no match for password_reset, PasswordReset, or token_generator anywhere
```

**Evidence — `src/telegram_bot/services/support_delivery_email.py:110-118`** *(supports: "the one real e-mail path is explicitly fail-open, which is what the boot gate contradicts")*:
```python
    except Exception as exc:
        # Never break the seller's flow because e-mail failed.
        logger.warning("Support email delivery failed (continuing): %s", exc)
        return False
```

---

#### API-010: [MEDIUM] — The nginx :80 catch-all redirects to `https://$host$request_uri`, so the redirect target is attacker-controlled

| Field | Value |
|---|---|
| **ID** | API-010 |
| **Title** | The nginx :80 catch-all redirects to `https://$host$request_uri`, so the redirect target is attacker-controlled |
| **Severity** | MEDIUM |
| **Category** | Security (open redirect) |
| **File(s)** | `docker/nginx/nginx.conf:31-35`, `docker/nginx/nginx.dev.conf:34-38` |
| **Type** | BEST-PRACTICE |
| **Status** | Open |
| **Problem** | The only server block on the plaintext listener is a bare `listen 80;` with **no `server_name` directive and no default_server flag**, and its sole job is `return 301 https://$host$request_uri;`. With no `server_name` configured, nginx has nothing to substitute and `$host` resolves to the client's `Host` header verbatim. A request with `Host: attacker.example` therefore produces `301 Location: https://attacker.example/<path>`. Nothing in the config validates the host: `ALLOWED_HOSTS` gates Django, not nginx, and this redirect never reaches Django. The TLS block does declare `server_name _;` (line 58), so the asymmetry is specific to the :80 listener. |
| **Impact** | A phishing primitive served from the project's own domain: `http://mko-bazuna.example/ads/123` with a crafted `Host` yields a 301 to an attacker-controlled HTTPS origin. Impact is bounded in practice — the victim sees the attacker's host in the address bar after the hop, there is no response-body reflection, the access log format (`log_format main`) does not include `$host`, and the CSP/HSTS headers are on the :443 block only — but the 301 is generated by the trusted origin and can be embedded in a link a user is willing to click. It is also a live example of the `$host` trust that phase 04's `AUT-003` is about for the rate-limit zones: the same attacker-controlled value is reflected into a response header here. |
| **Root Cause** | The redirect was written for a single-tenant setup where `$host` is always correct. Because the :80 block declares no `server_name`, that assumption became implicit rather than enforced, and the reflection was left in place. |
| **Recommendation** | Stop reflecting the client-supplied host. In production, give the :80 block an explicit `server_name <site-domain>;` and add a second `listen 80 default_server;` block that `return 444;` (nginx closes the connection without any response), keeping `return 301 https://$host$request_uri;` only inside the named block. If a single block must be kept for the Docker/dev case, use `$server_name` instead of `$host` — that resolves to the configured name rather than the header, and fails closed when the operator forgets to set it. |
| **Effort** | S |
| **Priority** | P1 |
| **CWE** | CWE-601 (URL Redirection to Untrusted Site / Open Redirect) |
| **Likelihood** | LOW |
| **Related Findings** | API-014 |

**Evidence — `docker/nginx/nginx.conf:31-35`** *(supports: "the only server on :80 has no `server_name` at all, so `$host` is the client-supplied Host header")*:
```nginx
    server {
        listen 80;
        # HTTP to HTTPS redirect
        return 301 https://$host$request_uri;
    }
```

**Evidence — `docker/nginx/nginx.dev.conf:34-38`** *(supports: "the same construction is shipped for dev, so it is the shape new deployments will copy")*:
```nginx
    server {
        listen 80;
        # HTTP to HTTPS redirect
        return 301 https://$host$request_uri;
    }
```

---

#### API-011: [MEDIUM] — `BOT_TOKEN` is distributed to six containers and is actively used by the web and scheduler tiers, not only the bot

| Field | Value |
|---|---|
| **ID** | API-011 |
| **Title** | `BOT_TOKEN` is distributed to six containers and is actively used by the web and scheduler tiers, not only the bot |
| **Severity** | MEDIUM |
| **Category** | Least privilege |
| **File(s)** | `docker-compose.yml:62,96,131`, `docker-compose.prod.yml` (`env_file` on every service), `src/backend/apps/search/services/immediate_alerts.py:186,199`, `src/backend/apps/search/management/commands/send_alerts.py:161`, `src/backend/config/settings/prod.py:17-22` |
| **Type** | SPEC-DEVIATION |
| **Status** | Open |
| **Problem** | The project's stated model is "one web process, one bot process, one shared DB" and the phase rubric asks that the bot credential be present "nowhere except the runtime environment". The token is env-sourced (correct) but it is distributed far beyond the bot: the base compose passes `BOT_TOKEN: ${BOT_TOKEN}` explicitly to the three one-shot services `migrate`, `load_cities` and `load_catalog`, and every service in `docker-compose.prod.yml` inherits `env_file: .env.prod`, so `web`, `bot`, `scheduler`, `create_admin` and `backup` all hold it. More importantly this is not merely latent exposure — the **web tier and the scheduler actively use it**: `immediate_alerts` and `send_alerts` both construct `Bot(token=settings.BOT_TOKEN)` themselves, and `immediate_alerts` runs in the web process via `Ad.post_save` → `transaction.on_commit`. Three separate processes now hold a credential that can post as the bot, and each carries its own rate-limit budget, so flood control is enforced against the token in aggregate rather than per process. |
| **Impact** | The blast radius of any single-tier compromise (an LFI, an SSTI, a leaked worker dump, a read-only file-inclusion bug) widens from "the site" to "the site plus the ability to post as the bot and message every user" — the latter enables phishing from a trusted, pre-existing conversation. The one-shot services are the weakest link: they run on every deploy, read `BOT_TOKEN` and the entire `.env` at import, and are the least hardened (they execute `makemigrations`-style code paths against operator-controlled input). The token is also re-read by `migrate_locked` only as a *requirement* (`prod.py:17-22` raises if it is empty), so the one-shots are forced to hold it purely to satisfy an import-time guard — they never use it. |
| **Root Cause** | The production settings module is monolithic: `prod.py` requires `BOT_TOKEN` unconditionally, so any process importing it must have the token, including the one-shots. Separately, the two alert senders mint their own `Bot` instead of delegating to a single outbound gateway, so the credential naturally spreads. |
| **Recommendation** | Two independent moves, both small. (1) Make the guard conditional on what the process actually does — move the `BOT_TOKEN` requirement out of `prod.py` and into the bot/scheduler bootstrap (`telegram_bot/main.py` and the `send_alerts` command), so `migrate`, `load_cities`, `load_catalog` and `create_admin` never need it; then drop the explicit `BOT_TOKEN: ${BOT_TOKEN}` lines from the three one-shot services in `docker-compose.yml`. (2) If the one-shot removal is judged too invasive for now, at least document the exposure in `docs/ops/docker-deployment.md` so a compromise-response runbook knows to rotate `BOT_TOKEN` (not just `DJANGO_SECRET_KEY`) when the web tier is suspected, and note the multi-process flood-control consequence. |
| **Effort** | S (config only) / M (settings split) |
| **Priority** | P2 |
| **CWE** | CWE-250 (Execution with Unnecessary Privileges) |
| **Likelihood** | LOW |
| **Related Findings** | API-003, API-004, API-014 |

**Evidence — `docker-compose.yml:60-63,94-97,129-132`** *(supports: "the three one-shot services receive the bot credential explicitly and never use it")*:
```yaml
  migrate:
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_DB: ${POSTGRES_DB}
      BOT_TOKEN: ${BOT_TOKEN}       # migrate_locked imports prod.py, which requires it
  ...
  load_cities:
    environment:
      ...
      BOT_TOKEN: ${BOT_TOKEN}
  ...
  load_catalog:
    environment:
      ...
      BOT_TOKEN: ${BOT_TOKEN}
```

**Evidence — `src/backend/apps/search/services/immediate_alerts.py:180-199`** *(supports: "the web process reads `settings.BOT_TOKEN` and mints its own `Bot`, outside the bot runtime")*:
```python
def _run_send(payloads: list[dict]) -> None:
    """Run the async send loop for the collected payloads in this thread."""
    try:
        asyncio.run(_send_payloads(settings.BOT_TOKEN, payloads))   # <-- the web tier's own Bot
    except AiogramError as exc:
        logger.error("Immediate alert send failed: %s", exc)


async def _send_payloads(bot_token: str, payloads: list[dict]) -> None:
    """Send all payloads concurrently, capped by ``asyncio.Semaphore``.
    ...
    """
    sem = asyncio.Semaphore(_SEND_CONCURRENCY)
    bot = Bot(token=bot_token)
```
…and the same shape in the scheduler path, `send_alerts.py:161`: `bot = Bot(token=bot_token)`.

**Evidence — `src/backend/config/settings/prod.py:17-22`** *(supports: "the credential is a settings-level requirement, so every importer must hold it")*:
```python
    bot_token = env("BOT_TOKEN", default="").strip()
    if not bot_token or bot_token.startswith("<"):
        raise ImproperlyConfigured(
            "BOT_TOKEN must be set in production (placeholder values are rejected at boot)"
        )
```

---

#### API-012: [MEDIUM] — `/save-search/` is the only query-persistence ingress that skips `redact_search_query()`

| Field | Value |
|---|---|
| **ID** | API-012 |
| **Title** | `/save-search/` is the only query-persistence ingress that skips `redact_search_query()` |
| **Severity** | MEDIUM |
| **Category** | Privacy / consistency |
| **File(s)** | `src/backend/apps/search/views/save_search.py:34-57`, `src/backend/apps/search/services/search_history.py:60-70`, `src/backend/apps/search/services/popular_search.py:38-48` |
| **Type** | BEST-PRACTICE |
| **Status** | Open |
| **Problem** | The project has a dedicated PII redactor for buyer-typed queries — `redact_search_query()` masks phone numbers, e-mail addresses and personal names, and there is even a data migration (`0002_redact_search_queries`) that backfilled the two tables that store them. Two of the three write paths use it: `record_search_history()` stores `redact_search_query(query)` into `SearchHistory.query`, and `bump_popular_search()` stores the redacted form into `PopularSearch.query`. The third write path, `save_search.save_search()`, takes the raw `request.POST["query"]` and writes it straight into `SavedSearch.query` with no redaction. The row is retained indefinitely, has no expiry, and is echoed back to the buyer in the bot's `/alerts` listing (`query_display = ss.query`). |
| **Impact** | A logged-in buyer who types a phone number, an e-mail address or their own name into the "save this search" box gets it stored verbatim for the lifetime of the `SavedSearch` row, defeating the redaction the project applied to the same data two tables away. It is also an inconsistent-privacy footgun: a reviewer reading `save_search.py` alone has no way to know the redaction is required, because the rule lives in two sibling service modules and in a migration. Phase 06 owns the PII policy; this finding is filed against the **API surface** because the gap is a missing call on an authenticated endpoint, not a policy disagreement. |
| **Root Cause** | The redaction rule was applied per-table at the time each table was added rather than at the boundary where buyer text enters the system, so each new write path has to remember it independently. |
| **Recommendation** | Apply `redact_search_query()` in `save_search.save_search()` before `SavedSearch.objects.create(query=...)`, matching the other two paths. If the unredacted form is genuinely wanted for the buyer's own saved search, that is a legitimate product decision (the buyer retyping their own number is their own data) — but then it must be (a) an explicit, documented decision, (b) covered by a retention rule, and (c) excluded from any path that renders to a third party. Recommend: redact on write for consistency, and note the decision in the privacy page's search-history paragraph. Add a test asserting a `SavedSearch` created with `"+382 69 000 123"` does not store the raw digits. |
| **Effort** | S |
| **Priority** | P1 |
| **CWE** | CWE-359 (Exposure of Private Personal Information to an Unauthorized Actor) |
| **Likelihood** | MEDIUM |
| **Related Findings** | API-009 |

**Evidence — `src/backend/apps/search/views/save_search.py:37,48-57`** *(supports: "the raw query is persisted with no redaction")*:
```python
    query = (request.POST.get("query") or "").strip()
    ...
    saved_search = SavedSearch.objects.create(
        user=request.user,
        query=query or None,      # <-- raw, no redact_search_query()
        city_id=_int_or_none("city_id"),
        ...
    )
```

**Evidence — `src/backend/apps/search/services/search_history.py:62-65` and `popular_search.py:39-51`** *(supports: "the two sibling write paths do redact, so the rule exists and this path simply omits it")*:
```python
    # Redact PII (phones, emails, names) before persisting, both to the
    # database (authenticated users) and to the session (anonymous users).
    # ``query_normalized`` remains the dedup/lookup key (SRH-004).
    redacted = redact_search_query(query)
    ...
    obj, created = PopularSearch.objects.get_or_create(
        query_normalized=normalized, defaults={"query": redacted, "hit_count": 1},
    )
```

**Evidence — `grep redact_search_query` over `src/backend`** *(supports: "only two application call sites, neither in the view layer")*:
```text
src/backend/apps/core/utils/sanitize.py:86:def redact_search_query(query: str) -> str:
src/backend/apps/search/services/search_history.py:17,65
src/backend/apps/search/services/popular_search.py:14,42
# no call site in apps/search/views/
```

---

#### API-013: [MEDIUM] — `immediate_alerts` dispatches fire-and-forget: unretrieved futures, an unbounded queue, and a shutdown that can outlast gunicorn's grace period

| Field | Value |
|---|---|
| **ID** | API-013 |
| **Title** | `immediate_alerts` dispatches fire-and-forget: unretrieved futures, an unbounded queue, and a shutdown that can outlast gunicorn's grace period |
| **Severity** | MEDIUM |
| **Category** | Reliability / observability |
| **File(s)** | `src/backend/apps/search/services/immediate_alerts.py:52-58,110-112,183-188`, `gunicorn.conf.py:19-27,32-33` |
| **Type** | BEST-PRACTICE |
| **Status** | Open |
| **Problem** | Three coupled weaknesses in the same dispatch. **(a) The result is never inspected.** `_executor.submit(_run_send, payloads)` discards the `Future`. `_run_send` catches only `AiogramError`, so any other exception (a `TelegramNetworkError` raised by `Bot(...)` construction, a `RuntimeError` from `asyncio.run()` inside a running loop, a `KeyError` in a payload) is stored in a `Future` nobody ever retrieves — Python then emits only the default "exception was never retrieved" notice, and the alert is lost with no application log at all. **(b) The queue is unbounded.** The pool is capped at `_MAX_DELIVERY_THREADS = 5` workers, but `ThreadPoolExecutor`'s work queue is an unbounded `queue.SimpleQueue`, so the cap throttles *concurrency* without bounding *backlog*. During a Telegram outage each in-flight send can sit on aiogram's `DEFAULT_TIMEOUT = 60.0` socket timeout plus a `retry_after` sleep, so a publish burst or the `bulk_approve` fan-out (up to 100 ads) accumulates work with nothing to shed load. **(c) The executor is never drained and blocks interpreter exit.** `ThreadPoolExecutor` registers its workers with `threading._register_atexit`, which joins every thread at exit; a send in flight at SIGTERM holds gunicorn's `graceful_timeout = 30` / `timeout = 60` budget, after which the arbiter force-kills the worker mid-send. |
| **Impact** | (a) A class of send failures is invisible: the system believes it delivered (the `SavedSearchNotification` row was already written at line 99, before the send) and only the generic Future warning surfaces. (b) A sustained Telegram outage turns the cap from a protection into a buffer that grows without limit, and — because every queued send will eventually make a real outbound call — the queue keeps issuing traffic at a Telegram that has already said "stop". (c) Deploys get 502s or force-killed workers, which is the least convenient possible moment to discover an alert problem. |
| **Root Cause** | The module replaced an unbounded `threading.Thread` with a bounded pool but kept the fire-and-forget contract, so the parts of the contract that a `submit()`-based design makes explicit — error propagation, backpressure, shutdown — were never added. `deliver_immediate_alerts` is also called from `transaction.on_commit`, where blocking is not an option, which is presumably why nothing blocks. |
| **Recommendation** | Make the dispatch observable and bounded, without making the request path block. (1) Attach a done-callback that logs at ERROR with the ad id / payload count: `_executor.submit(_run_send, payloads).add_done_callback(_log_send_result)`, where the callback calls `future.exception()` so nothing is ever unretrieved. (2) Add a backpressure gate: track an `asyncio`-free counter of in-flight batches and, when a threshold is exceeded, log a WARNING and skip the send (the daily `send_alerts` digest remains the safety net, and the `SavedSearchNotification` row still prevents a duplicate) — or simply make `_MAX_DELIVERY_THREADS` a settings value so it can be tuned per environment. (3) Register a Django `AppConfig.ready()` shutdown hook (or a `close_old_connections`-style hook) that calls `_executor.shutdown(wait=False, cancel_futures=True)` so a deploy drops queued sends instead of being killed holding them. Also raise the `AiogramError`-only catch in `_run_send` to `Exception` with an `logger.exception`, so the fallback is at least visible. |
| **Effort** | M |
| **Priority** | P1 |
| **CWE** | CWE-253 (Incorrect Check of Function Return Value) |
| **Likelihood** | MEDIUM |
| **Related Findings** | API-004, API-006 |

**Evidence — `src/backend/apps/search/services/immediate_alerts.py:52-58,110-112,183-188`** *(supports: "the pool bounds concurrency but not backlog, the result is discarded, and only `AiogramError` is caught")*:
```python
# Bounded thread pool: caps concurrent delivery daemon threads globally.
# Replaces unbounded threading.Thread (one per published ad burst).
_MAX_DELIVERY_THREADS: Final[int] = 5
_executor: ThreadPoolExecutor = ThreadPoolExecutor(
    max_workers=_MAX_DELIVERY_THREADS,
    thread_name_prefix="immediate-alert-send",
)
...
    # Dispatch to the bounded global thread pool so concurrent publish
    # bursts never exceed _MAX_DELIVERY_THREADS daemon threads.
    _executor.submit(_run_send, payloads)      # <-- Future discarded, unbounded queue


def _run_send(payloads: list[dict]) -> None:
    """Run the async send loop for the collected payloads in this thread."""
    try:
        asyncio.run(_send_payloads(settings.BOT_TOKEN, payloads))
    except AiogramError as exc:
        logger.error("Immediate alert send failed: %s", exc)   # <-- AiogramError only
```

**Evidence — `src/backend/apps/search/services/immediate_alerts.py:97-101`** *(supports: "the idempotency row is written *before* the send, so a lost send looks like a delivered one")*:
```python
    # Record notifications idempotently so the daily command never double-sends.
    for saved_search in searches:
        record_notifications(saved_search, [ad])
        saved_search.last_notified_at = timezone.now()
        saved_search.save(update_fields=["last_notified_at", "updated_at"])
```

**Evidence — `gunicorn.conf.py:19-33`** *(supports: "the web tier's shutdown budget is 30 s grace / 60 s kill, shorter than a 60 s Telegram socket timeout plus a `retry_after` sleep")*:
```python
timeout = 60
...
graceful_timeout = 30
```

---

### LOW

#### API-014: [LOW] — API-contract drift: an unsatisfiable `Bearer` challenge, manual POST guards, no versioning, unauthenticated `/metrics`, a trusted `X-Forwarded-Host`, unpinned TLS parameters

| Field | Value |
|---|---|
| **ID** | API-014 |
| **Title** | API-contract drift: an unsatisfiable `Bearer` challenge, manual POST guards, no versioning, unauthenticated `/metrics`, a trusted `X-Forwarded-Host`, unpinned TLS parameters |
| **Severity** | LOW |
| **Category** | Maintainability / hardening |
| **File(s)** | `src/backend/apps/moderation/views/decorators.py:44-55`, `src/backend/apps/moderation/views/review.py:76-99`, `src/backend/apps/moderation/urls.py:11-27`, `src/backend/config/urls.py:14-19`, `docker/nginx/nginx.conf:53-58,160-178`, `src/backend/config/settings/base.py:152-154` |
| **Type** | SPEC-DEVIATION |
| **Status** | Open |
| **Problem** | Five small contract observations, all verified in source. **(1)** `staff_required_api` answers 401 with `WWW-Authenticate: Bearer`, but the only accepted credential is a session cookie — the advertised scheme can never satisfy the challenge, so a generic HTTP client will retry with a Bearer token forever. **(2)** `approve_ad` guards with `@require_POST`; `reject_ad` and `ban_user` use a hand-written `if request.method != "POST": return redirect(...)`. The three state-changing moderation endpoints in the same module therefore have three different shapes (CSRF is still enforced on all of them — no `csrf_exempt` exists anywhere — so this is consistency, not a hole). **(3)** `/api/v1/bulk-action/` is the only versioned prefix in the project; the other six API/HTMX endpoints are unversioned, so there is no migration story when a shape must change. **(4)** `django_prometheus.urls` is included at path `""`, so `/metrics` is unauthenticated in Django; only nginx's `allow 127.0.0.1; deny all;` protects it, and it is therefore reachable from every sibling container on the Docker network (and in dev, where the web container publishes `8000:8000`, from the host). **(5)** `USE_X_FORWARDED_HOST = True` is trusted, but nginx never sets or clears `X-Forwarded-Host`, so a client-supplied value passes through untouched; the exposure is contained today only by `ALLOWED_HOSTS` in `get_host()`. Separately, the TLS server block pins no `ssl_protocols`, `ssl_ciphers`, `ssl_session_cache` or `ssl_session_tickets`, so all four rely on the nginx image's defaults. |
| **Impact** | Individually small; together they are the maintenance tax of an API layer that grew by accretion. (1) wastes a client's time and hides the real auth model. (2) makes the moderation surface harder to reason about and easier to get wrong when a fourth endpoint is added — the reason `@require_POST` exists is to get the 405 and the CSRF interaction for free. (3) means a breaking change has no deprecation window. (4) is one missing `X-Forwarded-Host`/network-policy line away from a public metrics scrape once a sibling container is compromised. (5) is defence-in-depth rather than an active hole, and (5b) means a future nginx upgrade can silently change the accepted cipher set. |
| **Root Cause** | The API surface was added endpoint-by-endpoint as each feature needed it, with no shared response/guard contract, and the reverse-proxy hardening stopped at "set the security headers". |
| **Recommendation** | (1) Drop the `WWW-Authenticate` header on the 401 (or change it to `Session` with a comment); it is a one-line change that makes the challenge honest. (2) Convert `reject_ad` and `ban_user` to `@require_POST` to match `approve_ad` — same behaviour, one shape. (3) Document in `docs/01-spec/architecture-structure.md` that the surface is an internal HTMX/JSON surface, that `/api/v1/` is the only versioned prefix, and that versioning is a deliberate non-goal for a single-consumer frontend; that is a defensible call, it just needs writing down. (4) Restrict `/metrics` in Django as well as nginx (a tiny `staff_required` wrapper, or a `settings.DEBUG`/env gate), so the control does not live in one file only. (5) Add `proxy_set_header X-Forwarded-Host $host;` to the proxied locations so the trust is explicit, and add `ssl_protocols TLSv1.2 TLSv1.3;` plus `ssl_session_cache shared:SSL:10m;` to the TLS server block to make the posture reviewable rather than inherited. |
| **Effort** | S |
| **Priority** | P2 |
| **CWE** | CWE-319 (Cleartext Transmission of Sensitive Information) — for the unpinned TLS parameters; no single CWE covers the set |
| **Likelihood** | LOW |
| **Related Findings** | API-010 |

**Evidence — `src/backend/apps/moderation/views/decorators.py:44-55`** *(supports: "the challenge advertises a scheme the app does not implement")*:
```python
    if not request.user.is_authenticated:
        return JsonResponse(
            {"error": "Authentication required"},
            status=401,
            headers={"WWW-Authenticate": "Bearer"},   # no Bearer scheme is ever accepted
        )
```

**Evidence — `src/backend/apps/moderation/views/review.py:76-99`** *(supports: "the same file uses two different method guards for state-changing actions")*:
```python
@staff_required
@require_POST
def approve_ad(request: HttpRequest, ad_id: int) -> HttpResponseRedirect: ...

@staff_required
def reject_ad(request: HttpRequest, ad_id: int) -> HttpResponseRedirect:
    if request.method != "POST":
        return redirect("moderation:queue")
```
…while `approve_ad` gets the 405 and the method handling for free from the decorator.

**Evidence — `docker/nginx/nginx.conf:53-58,160-168,170-178`** *(supports: "`X-Forwarded-Host` is neither set nor cleared, `/metrics` is protected only at the proxy, and no TLS parameter is pinned")*:
```nginx
        add_header Content-Security-Policy-Report-Only "default-src 'none'; ... report-uri /csp-report/" always;
        # TLS certificates mounted via docker-compose.prod.yml
        ssl_certificate /etc/nginx/certs/fullchain.pem;
        ssl_certificate_key /etc/nginx/certs/privkey.pem;
        # no ssl_protocols, ssl_ciphers, ssl_session_cache or ssl_session_tickets

        server_name _;                        # the :443 block declares it; the :80 block does not
        ...
        # Metrics endpoint — restricted to localhost (production monitoring only)
        location = /metrics {
            allow 127.0.0.1;                  # proxy-layer only; Django serves /metrics unauthenticated
            deny  all;
            proxy_pass http://web:8000;
        }
        ...
        location / {
            limit_req zone=browse_limit burst=40 nodelay;
            proxy_pass http://web:8000;
            proxy_set_header Host              $host;
            proxy_set_header X-Real-IP         $remote_addr;
            proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            # no X-Forwarded-Host, despite USE_X_FORWARDED_HOST = True
        }
```

**Evidence — `src/backend/config/settings/base.py:152-154`** *(supports: "the host is taken from a client-supplied header when it is present")*:
```python
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True
```

---

#### API-015: [LOW] — `/csp-report/` logs the whole report — including `document-uri` and `referrer` — at INFO from an unauthenticated POST

| Field | Value |
|---|---|
| **ID** | API-015 |
| **Title** | `/csp-report/` logs the whole report — including `document-uri` and `referrer` — at INFO from an unauthenticated POST |
| **Severity** | LOW |
| **Category** | Log hygiene |
| **File(s)** | `src/backend/apps/core/views.py:150-181`, `src/backend/apps/core/schemas.py` (`CSPReportPayload`), `docker/nginx/nginx.conf:149-157` |
| **Type** | BEST-PRACTICE |
| **Status** | Open |
| **Problem** | The view validates the payload with `CSPReportPayload` (Pydantic, 422 on schema failure — verified in R-03) and then logs the **entire, unfiltered** `report` dict at INFO: `logger.info("CSP violation report: %s", report)`. The CSP report schema browsers send includes `document-uri` (the full URL of the page, including its query string) and `referrer` (the full referring URL). Neither is a bounded field in the log statement, and the endpoint is reachable by anyone: `@require_POST` only, no auth, no CSRF exemption needed, and nginx allows 10 r/s with `burst=10 nodelay` — an order of magnitude looser than the 1 r/s a violation-report sink would ever legitimately need. |
| **Impact** | Two distinct effects. (1) *Log volume / availability*: an unauthenticated caller can push 10 requests/second of arbitrary JSON, each producing a full-dict INFO line through the `RedactingJsonFormatter`; a sustained caller inflates the log store at will, which is the cheapest form of log DoS. (2) *PII in logs*: page URLs routinely carry search queries (`/search/?q=…`) and session-adjacent identifiers, so a violation on a search-results page writes the buyer's own search text into the log stream in clear. Phase 06 owns PII minimisation; this is filed against the ingress because the endpoint's design — log everything, from anyone — is the finding. |
| **Root Cause** | The endpoint was built for Report-Only mode, where operators want visibility into violations; logging the whole report was the fastest way to get it, and no one revisited it once it was clear that the report body contains URLs rather than just a violated directive. |
| **Recommendation** | Log the fields an operator actually acts on — `violated-directive`, `effective-directive`, `disposition`, `blocked-uri` (host + path only) and the script `sample` — and drop `document-uri`'s query string and `referrer` entirely, or route them through the existing `sanitize_query_for_log`. Tighten the nginx zone to `rate=1r/s burst=5 nodelay`; a real browser reports a handful of violations per page load, so 1 r/s is generous. Optionally cap the accepted body size explicitly (Django's `DATA_UPLOAD_MAX_MEMORY_SIZE` already bounds `request.body`, so this is defence in depth). |
| **Effort** | S |
| **Priority** | P2 |
| **CWE** | CWE-532 (Insertion of Sensitive Information into Log File) |
| **Likelihood** | LOW |
| **Related Findings** | API-012, API-017 |

**Evidence — `src/backend/apps/core/views.py:169-181`** *(supports: "the whole validated report is logged at INFO, including its URL fields")*:
```python
    try:
        CSPReportPayload(**report["csp-report"])
    except ValidationError as exc:
        logger.warning("Invalid CSP report payload: %s", exc)
        return JsonResponse({...}, status=422)
    logger.info("CSP violation report: %s", report)   # <-- document-uri and referrer included
    return JsonResponse({"status": "ok"})
```

**Evidence — `docker/nginx/nginx.conf:149-157`** *(supports: "the sink is unauthenticated and allowed 10 r/s — the loosest budget in the config")*:
```nginx
        # Rate limit: CSP violation reports (EXT-04 hardening)
        location /csp-report/ {
            limit_req zone=login_limit burst=10 nodelay;   # login_limit = 10r/s
            proxy_pass http://web:8000;
            ...
        }
```

---

#### API-016: [LOW] — Runtime images use floating tags and the production TLS cert mount defaults to a host path that is empty on most hosts

| Field | Value |
|---|---|
| **ID** | API-016 |
| **Title** | Runtime images use floating tags and the production TLS cert mount defaults to a host path that is empty on most hosts |
| **Severity** | LOW |
| **Category** | Deployment portability |
| **File(s)** | `docker-compose.yml:1,17,25,34`, `docker-compose.prod.yml:8,80,132,173` |
| **Type** | BEST-PRACTICE |
| **Status** | Open |
| **Problem** | Every third-party image in the production topology is referenced by a floating tag: `nginx:alpine`, `postgres:18-alpine`, `redis:7-alpine` (pgbouncer is the exception, pinned at `1.25.2`). Separately, the production TLS mount is `- ${TLS_CERT_PATH:-/etc/nginx/certs}:/etc/nginx/certs:ro`. The default is an **absolute host path** (`/etc/nginx/certs`), not the repository's own `./docker/nginx/certs`, where the `certs/` directory that ships with the project actually lives. Docker auto-creates a missing host bind-mount source as an empty directory, so a deployment that forgets to export `TLS_CERT_PATH` does not fail at mount time — it starts, mounts an empty directory, and nginx then aborts with `cannot load certificate`. The `${VAR:-default}` syntax also means the failure produces no warning from compose. |
| **Impact** | (1) *Non-reproducible deploys / supply chain*: `docker compose pull` can move nginx, PostgreSQL and Redis to new minor versions without any change to the repository, so two hosts that both run "the current compose file" can be on different minor versions of every datastore. For PostgreSQL that is a genuine operational hazard across a major-version boundary. (2) *A misleading default for the one thing nginx cannot start without*: an operator following `docs/ops/docker-deployment.md` who misses the `TLS_CERT_PATH` export gets an empty mount and a crash-looping proxy, with the compose output looking successful. The in-repo certificate directory is the obvious default and is not what the file uses. |
| **Root Cause** | Floating tags are the default habit for `compose` files; the `TLS_CERT_PATH` default was written as "where certificates usually live on a Linux box" rather than "where this repository keeps them", so the repository's own `docker/nginx/certs/` is never referenced by the production path. |
| **Recommendation** | (1) Pin every third-party image to a patch version (`nginx:1.29-alpine`, `postgres:18.0-alpine`, `redis:7.4-alpine`) or, better, to a digest, and add a scheduled bump job — a monthly "pull and test" run is enough to keep them current without making every deploy a coin flip. (2) Change the default to the in-repo path so a fresh clone works with no export: `- ${TLS_CERT_PATH:-./docker/nginx/certs}:/etc/nginx/certs:ro`, and make the `docs/ops/docker-deployment.md` TLS section state explicitly that the path is resolved on the **host** and defaults to the repository's `docker/nginx/certs/`. Optionally add an entrypoint precondition (`test -s /etc/nginx/certs/fullchain.pem || { echo "TLS_CERT_PATH does not resolve to a real certificate"; exit 1; }`) so the failure is a one-line explanation instead of an nginx TLS-parsing error. Phase 12 owns the deployment runbooks; this finding is filed under this phase because TLS termination and the reverse-proxy image are the artefacts audited here. |
| **Effort** | S |
| **Priority** | P2 |
| **CWE** | CWE-1104 (Use of Unmaintained Third Party Components) |
| **Likelihood** | LOW |
| **Related Findings** | API-014 |

**Evidence — `docker-compose.yml:17,25,34`** *(supports: "the three stateful/edge images are floating-tagged")*:
```yaml
  db:
    image: postgres:18-alpine
  redis:
    image: redis:7-alpine
  nginx:
    image: nginx:alpine
```

**Evidence — `docker-compose.prod.yml:73-80`** *(supports: "the TLS mount default is a host path, not the in-repo certs directory")*:
```yaml
      volumes:
        - media_volume:/media_volume:ro
        - ./docker/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
        # TLS certificates from environment variable
        - ${TLS_CERT_PATH:-/etc/nginx/certs}:/etc/nginx/certs:ro
```
…and `docker/nginx/certs/` in this repository contains only `.gitkeep` (the real `fullchain.pem` / `privkey.pem` are gitignored and must be placed by the operator), which is exactly why the in-repo default is the right one.

---

#### API-017: [LOW] — Translation logs seller free text with the non-redacting sanitiser, and breaker state is only visible as a per-call INFO line

| Field | Value |
|---|---|
| **ID** | API-017 |
| **Title** | Translation logs seller free text with the non-redacting sanitiser, and breaker state is only visible as a per-call INFO line |
| **Severity** | LOW |
| **Category** | Observability / log hygiene |
| **File(s)** | `src/backend/apps/core/services/translation.py:172-177,187-193,206-215,222-233,246-250`, `src/backend/apps/core/utils/sanitize.py:1-84` |
| **Type** | BEST-PRACTICE |
| **Status** | Open |
| **Problem** | Every log line in the translation service that includes the ad text passes it through `sanitize_query_for_log`, which strips control characters and truncates — it does **not** mask PII. The project ships a second sanitiser, `redact_search_query`, which masks phone numbers, e-mails and personal names, and the same buyer text is redacted before it reaches `SearchHistory`/`PopularSearch` (see API-012). A seller who writes their phone number into a title (extremely common on a classifieds board) therefore has it written to production logs at INFO and WARNING by the translator's own diagnostics. The breaker is observable only as one INFO line per call — `"Circuit open -- fallback to original text … (breaker)"` — so "how many ads were published untranslated in the last hour" requires a log grep, and there is no counter, gauge or threshold to alert on. |
| **Impact** | Modest but real: the ad text that a buyer-side PII control already decided to mask is persisted in the log stream by a different code path, and the single most operationally interesting state of this integration (the breaker being open, meaning every ad is shipping untranslated) has no metric. The two combine with API-007: the fallback is invisible, unmeasured and logged at a level that will not page anyone. The good news, verified in R-04/R-18, is that the HTTP-failure lines already strip the credential: `str(e.request.url.copy_with(params={}))` removes the `key` query parameter, so `GOOGLE_TRANSLATE_API_KEY` cannot leak through these logs. |
| **Root Cause** | Two sanitisers exist for two different audiences — `sanitize_query_for_log` is written for *safe-to-log* text and `redact_search_query` for *user-typed* text — and the boundary between the two was never stated, so the translation path (which handles seller-typed text) picked the wrong one by name similarity. |
| **Recommendation** | (1) Route the ad text through `redact_search_query` in the three log sites (`translation.py:175,189,211,229,239,248`), leaving `sanitize_query_for_log` for genuinely internal values; or, if the truncation is what makes the log usable, compose the two — redact, then truncate. (2) Add three counters — `translation_requests_total`, `translation_fallback_total`, `translation_circuit_open` — and expose them on the existing `/metrics` endpoint (the `django_prometheus` wiring is already in place), so "the translator is down" becomes an alertable condition and the `backfill_translations` fallback count in API-007 can be measured rather than inferred. (3) While there, note in the module docstring which sanitiser applies to which kind of text, so the next caller picks correctly. |
| **Effort** | S |
| **Priority** | P2 |
| **CWE** | CWE-532 (Insertion of Sensitive Information into Log File) |
| **Likelihood** | MEDIUM |
| **Related Findings** | API-007, API-012 |

**Evidence — `src/backend/apps/core/services/translation.py:172-177,246-250`** *(supports: "seller ad text reaches the log via the non-masking sanitiser, and the open breaker is only a per-call INFO line")*:
```python
    if _CIRCUIT_BREAKER.is_open:
        logger.info(
            "Circuit open -- fallback to original text '%s' (breaker)",
            sanitize_query_for_log(text),      # control-char strip + truncate, no PII masking
        )
        return text
    ...
    logger.info(
        "Translation fallback: returning original text '%s'",
        sanitize_query_for_log(text),
    )
    return text
```

**Evidence — `src/backend/apps/core/services/translation.py:222-233`** *(supports: "the credential is correctly stripped from the URL in HTTP-failure logs — the practice the ad-text lines should match")*:
```python
                if status in (429, 500, 502, 503, 504) and attempt + 1 < TRANSLATION_MAX_ATTEMPTS:
                    logger.warning(
                        "Translation rate-limited/server error (attempt %d/%d, HTTP %d) "
                        "for text '%s' (%s->%s): %s",
                        attempt + 1, TRANSLATION_MAX_ATTEMPTS, status,
                        sanitize_query_for_log(text),
                        source_locale, target_locale,
                        str(e.request.url.copy_with(params={})),   # <-- key= removed; no leak
                    )
```

---

## Cross-Finding Analysis

### 1. Ownership Map

| Cluster | Findings | Primary owner | Cross-phase overlaps |
|---|---|---|---|
| **Cache / Redis as an undeclared hard dependency** | API-001, API-002 | 09 | 12-OPS (Redis SLO), 03-DB (consequence on the bot's single ORM thread) |
| **Telegram outbound resilience** | API-003, API-004, API-006, API-013 | 09 | 06-PII (API-006's alert *audience* is filed there as PII-101) |
| **Google Translate egress** | API-007, API-017 | 09 | 08-SRH (search-side degradation already PASSes, R-05) |
| **Reverse proxy / TLS** | API-005, API-010, API-014, API-016 | 09 | 04-AUT (`AUT-003`, XFF-first rate-limit bypass — same `$host` trust), 12-OPS (runbooks) |
| **Credential distribution** | API-011 | 09 | 02-CFG owns the *validation*; this is *distribution* only |
| **Documented-vs-actual claims** | API-008, API-009 | 09 | 00-Overview doc rules, 12-OPS |

### 2. Compounding Failure Chains

**Chain A — one Redis outage removes the whole system.** `API-002` makes four
bot abuse guards throw, `API-001` makes every public page 500 through the
context processors, `readiness_check` returns 503, and the bot's
`RedisStorage` FSM raises inside `AccountStateMiddleware`. There is no
degraded mode: the system goes from fully up to fully down on a single cache
outage, and the two HIGH findings are the same root cause (a cache read left
outside its guard) in two different layers. Fixing API-001 and API-002
together converts a total outage into a slow, logged, rate-limit-free bot —
the second half of which is exactly what API-003 says not to accept, so the
per-seller cap in API-003's recommendation is what makes the fail-open
defensible.

**Chain B — an unrated deep link becomes a flood-control event.** `API-003`
lets any account drive outbound Telegram sends without limit. Telegram
responds with `TelegramRetryAfter`; `API-004` then sleeps the mandated wait
three times with no ceiling and replays the method, so the amplification is
3x on top of the flood. The fixed egress budget for the whole platform is
therefore one user's afternoon, and the observable symptom (sellers not
receiving alerts) is filed as a data-integrity issue rather than as abuse.

**Chain C — a Telegram 5xx loses every seller-facing message, invisibly.**
`API-004`'s entry guard means only 429 is replayed; a 5xx window drops every
confirmation. `API-013` means the alert path additionally swallows any
non-`AiogramError` into an unretrieved `Future`, and `API-013` writes the
`SavedSearchNotification` row *before* the send, so the system records success
for messages that were never delivered. Three independent mechanisms, one
outcome: a Telegram-side incident looks like a quiet Tuesday.

**Chain D — silent data poisoning in the translation columns.** `API-007`'s
unmarked fallback writes the Russian source into `title_en` / `title_bs`;
`API-008`'s seed silently rewrites the exchange rate the price normalisation
depends on; `API-017` means neither is measurable. The common theme is that
all three are *successful* operations from the process's point of view, so
nothing alerts.

### 3. What Is Genuinely Well Built

Stated plainly, because these were verified and the remediation effort should
not disturb them:

- **No credential leak anywhere.** No tracked `.env` file, no tracked
  certificate, no hardcoded token, no secret in any exception string
  (`TelegramAPIError.url` is a docs link, not the request URL), and the
  translation service already strips `key=` from logged URLs. Rotation is
  documented per-secret in `docs/ops/docker-deployment.md:385-420`.
- **Correct security-header posture at the edge.** HSTS with
  `includeSubDomains; preload`, `X-Frame-Options DENY`, `nosniff`, a
  restrictive `Referrer-Policy`, and a `default-src 'none'` CSP — Report-Only
  by a *deliberate, tracked* deferral rather than by accident.
- **A correct fail-open precedent that simply was not generalised.**
  `UpdateIdDedupMiddleware` catches `ConnectionInterrupted` and logs the
  choice explicitly; the translation service's circuit breaker, timeout and
  fallback are a well-shaped graceful-degradation design; the search outage
  test proves the reader side stays up. The gap is consistency, not knowledge.
- **Rate-limit zones keyed on the real client IP.** All three zones use
  `$binary_remote_addr`, so the XFF-spoofing bypass from `AUT-003` does not
  apply to them.
- **The login-token handshake is well built on the bot side.** The token is
  claimed once under `SELECT … FOR UPDATE`, bound to the claiming chat, and
  the raw token is never stored (only its SHA-256). No token in logs, no
  webhook ingress to misconfigure, a per-user claim limiter, and the web side
  honours `DENY` when `USE_X_FORWARDED_HOST` is on.

---

## Recommended Roadmap

Sequenced by dependency, not by severity. Each wave is independently
deployable and independently revertable, and the deferrals in Wave 4 are the
judgement calls a human should make.

### Wave 1 — Stop the bleeding (P0, all small, no behaviour change)

1. **API-001** — move the two cache reads inside their `try` in
   `site_config.py`; add a `cache_get_or_none()` helper in
   `apps/core/utils/cache.py` and route every request-path cached read through
   it. Ship with a regression test that patches the cache to raise.
2. **API-002** — one shared `_bump_window()` helper catching
   `(ConnectionInterrupted, redis.RedisError, ValueError)` and failing open;
   all four guards call it. Removes four copies of the same code at the same
   time.
3. **API-003** — add the buyer-per-10-min and seller-per-hour limiters to the
   `contact_<ad_id>` branch. **This must land together with API-002**, because
   API-002 makes the limiter fail open during a cache outage and a fail-open
   seller-spam guard is not a guard.
4. **API-004** — cap the backoff (`min(retry_after, 5.0)`), register
   `ExceptionTypeFilter(_TRANSIENT_EXCEPTIONS)`, delete the unreachable
   `isinstance` guard, and return `False` on exhaustion so the drop is logged.
5. **API-005** — add a `media_limit` zone to `location /media/` in both configs.

*Why together:* API-002 makes the bot's guards fail open, which is only
acceptable once API-003's per-seller cap exists. Splitting these two across
releases means either a window with no seller-spam protection, or a window
where a cache outage silently disables the login limiter.

### Wave 2 — Correctness of delivered messages

6. **API-006** — escape or de-HTML the alert bodies; add the markup test.
7. **API-007** — make the fallback distinguishable, count it, and bound
   `backfill_translations` by work rather than by wall clock (`--limit`,
   progress output). Independent of the schema, so it can ship first; if a
   `translation_failed_at` column is wanted, that is a separate migration.
8. **API-013** — done-callback with `future.exception()`, bounded backlog,
   `shutdown(wait=False, cancel_futures=True)` on app shutdown.

### Wave 3 — Spec and documentation alignment

9. **API-008** — `get_or_create` instead of `update_or_create`, and either add
   the remote feed or correct the docs that claim one exists.
10. **API-009** — correct the `EMAIL_HOST` comment, then decide mandatory vs
    warning and write the decision down either way.
11. **API-010** — explicit `server_name` on :80 plus a `return 444;` default
    block. One-line change, immediately verifiable with `nginx -t`.
12. **API-012** — `redact_search_query()` in `save_search`.

### Wave 4 — Judgement calls and hardening (P2)

13. **API-014** — drop the `Bearer` challenge; unify the moderation POST
    guards; pin `ssl_protocols` / `ssl_session_cache`; set
    `X-Forwarded-Host`; restrict `/metrics` in Django as well as nginx;
    document the versioning non-goal.
14. **API-016** — pin image tags; change the `TLS_CERT_PATH` default to
    `./docker/nginx/certs` and add an entrypoint precondition. Coordinate the
    tag bumps with phase 12's runbooks.
15. **API-011** — move the `BOT_TOKEN` requirement out of `prod.py` into the
    bot/scheduler bootstrap and drop it from the three one-shot services.
16. **API-015**, **API-017** — log-field selection and the translation
    counters, ideally as one observability change so the alerts have metrics
    to fire on.

### Rollout Safety

Every item in Waves 1 and 2 is additive or a pure tightening and none changes
a public response shape; the two exceptions are noted here. **API-001** turns
a 500 into a 200 on a path that is currently broken, so the only risk is the
new `try` swallowing a `SiteConfig` misconfiguration that operators were, in
practice, never seeing anyway. **API-004** makes previously-dropped Telegram
calls succeed, which slightly *increases* outbound volume in the first minutes
after deploy — acceptable, because API-003 lands in the same wave and caps the
source. **API-007**'s `--limit` is a new flag with a safe default. **API-010**
is the only change that can break a working deployment: it requires the
operator to set a real `server_name`, so gate it on the `TLS_CERT_PATH`/
domain work in `docs/ops/docker-deployment.md` and verify with `nginx -t`
before rolling. **No finding in this report requires a data migration**;
API-007's optional `translation_failed_at` column is the only schema change
proposed anywhere, and it is optional.

### Deferred Findings

None. Every issue found was either filed with evidence or is explicitly
recorded as a verified PASS in the R-table (and is therefore out of scope by
the problem-chasing mode). Where a finding is owned by another phase, the
overlap is stated in the finding itself rather than deferred here.

---

## Appendix A — Verified Assets (no finding)

Recorded so a later reviewer does not re-litigate them, and so the roadmap is
not read as "nothing in this area works".

| Area | Verified state | Evidence |
|---|---|---|
| Webhook ingress | None. Long-polling only; no `set_webhook`, no `WEBHOOK_URL`, no `TELEGRAM_WEBHOOK_SECRET` anywhere in `src/`, `docker/` or `.github/` | R-01 |
| Secret hygiene | `.env.dev` / `.env.test` / `.env.prod` and `docker/nginx/certs/*.pem` are all gitignored; only `*.example` files are tracked | R-16 (`git ls-files`, `git check-ignore`) |
| Token in logs | `TelegramAPIError.url` is a `core.telegram.org` docs link; `TelegramNetworkError` carries only `type(e).__name__`; `prod.py` LOGGING leaves the root at WARNING so `aiohttp.access` is never emitted | R-18 |
| Translator credential in logs | `e.request.url.copy_with(params={})` strips the `key` query parameter on every HTTP-failure log line | API-017 evidence |
| Login handshake (bot side) | Token claimed once under `SELECT … FOR UPDATE`, bound to the claiming `chat_id`, raw token never stored (SHA-256 only), per-user claim limiter, generic failure message | `handlers/login.py:96-135` |
| Rate-limit keying | All three nginx zones use `$binary_remote_addr` (real client IP), so the XFF-first bypass in `AUT-003` does not apply to them | `nginx.conf:24-26` |
| Edge security headers | HSTS 1y + `includeSubDomains; preload`, `X-Frame-Options DENY`, `nosniff`, `Referrer-Policy strict-origin-when-cross-origin`, `default-src 'none'` CSP (Report-Only, deliberately deferred and tracked) | `nginx.conf:42-53` |
| `POST` token hash comparison | The web side refuses to accept a raw token when `USE_X_FORWARDED_HOST` is on, blocking Host-header injection of a second token | `users/views/consent.py:64-68` |
| CSRF | No `csrf_exempt` and no `staff_member_required` anywhere in `src/` | R-19 |
| Failure-open precedent | `UpdateIdDedupMiddleware` catches `ConnectionInterrupted` and logs the fail-open decision explicitly | API-002 evidence |

## Appendix B — Endpoints and Integrations Inventory

**Third-party egress (outbound).**

| Integration | Reached from | Credential | Timeout | Retry | Circuit / limiter |
|---|---|---|---|---|---|
| Telegram Bot API (long-polling + sends) | `telegram_bot` (primary), `apps.search` `immediate_alerts` / `send_alerts` (web + scheduler) | `BOT_TOKEN` (env) | aiogram `DEFAULT_TIMEOUT = 60.0` | `retry.py` — 3 attempts on 429 only, uncapped | none global; per-guards in the bot only |
| Google Translate v2 | `core.services.translation` from the bot's ad-create flow and from `backfill_translations` | `GOOGLE_TRANSLATE_API_KEY` (query param) | `TRANSLATION_TIMEOUT_SECONDS = 0.5` | `TRANSLATION_MAX_ATTEMPTS = 2`, 100 ms base | `TranslationCircuitBreaker`; `lru_cache(256)`; no quota meter |
| SMTP (support tickets only) | `telegram_bot.services.support_delivery_email` | `EMAIL_HOST`/`EMAIL_PORT`/`EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD` | Django `EMAIL_TIMEOUT` (unset → 30 s default) | none | none; fail-open by design |
| Plausible analytics | browser, `base.html:56-58`, gated on `consent_analytics and PLAUSIBLE_HOST` | none (host-only) | n/a | n/a | consent gate |
| Exchange rates | **no network call exists** — `load_exchange_rates` is a hard-coded manual seed | none | n/a | n/a | n/a |

**Application ingress (unauthenticated, rate-limited).**

| Path | nginx zone | Auth | CSRF | Notes |
|---|---|---|---|---|
| `/` and all other public pages | `browse_limit` 20 r/s burst 40 | anonymous | n/a | `header_context` → `get_bot_username()` → cache (API-001) |
| `/media/<key>` | **none** | anonymous | n/a | API-005; per-request DB access check |
| `/static/` | none | anonymous | n/a | whitenoise, no DB; omission harmless |
| `/search/` | `search_limit` 20 r/s burst 40 | anonymous | n/a | degrades cleanly on translator outage (R-05) |
| `/login/` | `login_limit` 10 r/s burst 20 | anonymous | n/a | `/login/issue/` (GET, issues token) and `/login/status/` (POST, consumes) |
| `/csp-report/` | `login_limit` 10 r/s burst 10 | anonymous | exempt by design | API-015 |
| `/api/search/autocomplete` | `browse_limit` (via `location /`) | anonymous | n/a | app-level sliding-window limiter too |
| `/health/` | **none** (intentional) | anonymous | n/a | `readiness_check` returns 503 on DB/cache/bot failure |
| `/metrics` | `location = /metrics`, `allow 127.0.0.1; deny all` | proxy-only | n/a | Django serves it unauthenticated (API-014) |
| `/admin/` | `browse_limit` | Django admin session | yes | `staff_member_required` is Django's own |

**Telegram ingress (deep links).**

| Deep link | Guard | State changed |
|---|---|---|
| `/start login_<32-char>` | `check_login_rate_limit` (10 / 60 s) — fails closed on cache outage (API-002) | `LoginToken.telegram_id` set, once |
| `/start contact_us` | `check_contact_start_rate_limit` (5 / 600 s) | none |
| `/start contact_<ad_id>` | **none** | `AnalyticsEvent` INSERT + outbound Telegram send to the seller (API-003) |
| `/start unsub_<32-char>` | none, but ownership-checked via stable `chat_id` | `SavedSearch.is_active` |
| `unsub:` / `unsub_on:` callback | none, ownership-checked via stable `chat_id` | `SavedSearch.is_active` |

---

**Report complete.** 17 findings: 0 CRITICAL, 5 HIGH, 8 MEDIUM, 4 LOW.
**Validator:** Phase 99 (not run — this is a raw phase report).
