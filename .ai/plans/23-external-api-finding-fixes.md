---
id: 23-external-api-finding-fixes
domain: plan
tags:
  - external-integrations
  - ext-001
  - ext-002
  - ext-003
  - ext-004
  - ext-005
  - ext-006
  - nginx
  - telegram-bot
  - translation-client
  - rate-limiting
  - security-headers
  - api-versioning
  - idempotency
related:
  - .ai/audit/99-validation/09-external-api-validated-findings.md
  - .ai/tasks/templates/task_template.yaml
  - .ai/tasks/templates/task_template_verification.yaml
  - docker/nginx/nginx.conf
  - docker/nginx/nginx.dev.conf
  - src/backend/apps/core/services/translation.py
  - src/telegram_bot/handlers/ad_create.py
  - src/backend/apps/search/services/immediate_alerts.py
  - src/telegram_bot/main.py
  - src/telegram_bot/middlewares/__init__.py
  - src/backend/apps/moderation/views/decorators.py
  - src/backend/apps/moderation/views/api_bulk.py
  - src/backend/apps/moderation/urls.py
  - src/backend/apps/moderation/signals.py
  - src/backend/apps/search/management/commands/send_alerts.py
  - src/telegram_bot/services/rate_limit.py
  - src/backend/apps/lookups/signals.py
  - src/backend/apps/moderation/tests/test_decorators.py
  - src/backend/apps/moderation/tests/test_priority_service.py
  - src/telegram_bot/tests/test_multi_lang_translation.py
  - src/telegram_bot/tests/conftest.py
  - docs/01-spec/spec-index.md
---

# External-API Finding Fixes — Execution Plan (Phase 09)

**Plan ID:** `23-external-api-finding-fixes`
**Source:** `.ai/audit/99-validation/09-external-api-validated-findings.md` (validated 2026-09-10)
**Status:** 6 findings — 1 HIGH mandatory (EXT-003), 3 MEDIUM advisory (EXT-001/002/005), 2 LOW advisory (EXT-004/006). All ship now. EXT-001 is internally staged behind a hard except-narrowing prerequisite.

---

## 1. Baseline — Current Working Tree State

All six findings were independently reproduced against the working tree (static evidence: targeted `grep` + exact source reads + installed-package source inspection). None are implemented. Confirmed:

| Finding | Status | Key verified facts |
|---------|--------|--------------------|
| EXT-001 | Present | `translation.py` `translate_text` uses a catch-all `except (TimeoutError, RequestException, Exception)`; single attempt; abandoned `ThreadPoolExecutor(max_workers=4)`; `ad_create.py` `translate_all_languages` gather has no `return_exceptions=True`. **Verified via `uv run python`:** `deep_translator.exceptions.{TooManyRequests, RequestError, TranslationNotFound}` subclass **only `Exception`** — not `requests.exceptions.RequestException`. |
| EXT-002 | Present | `immediate_alerts.py` constructs `Bot(token=...)` per message inside `_send`; per-thread `Semaphore` (not global); bare `except Exception` in `_run_send`; `asyncio.gather` (line ~195) lacks `return_exceptions=True`; gated `IMMEDIATE_ALERTS_ENABLED` default-off. |
| EXT-003 | Present | `nginx.conf` / `nginx.dev.conf` define only `login_limit` + `search_limit` zones; `limit_req` only on `/login/` and `/search/`; **no** `limit_req` on `location /`, `/media/`, `/protected-media/`, `/health/`; `api_bulk.py` `for ad_id in ad_ids:` has no cap. |
| EXT-004 | Present | `/protected-media/` block redeclares nosniff + CSP-RO + X-Frame-Options + Content-Disposition but **omits `Strict-Transport-Security`** (dropped by nginx `add_header` inheritance); **0** matches for `Referrer-Policy`/`Permissions-Policy` across both nginx configs. |
| EXT-005 | Present | `main.py` `dp.run_polling` registers only `AccountStateMiddleware` + lifecycle middleware; `middlewares/__init__.py` exports only `AccountStateMiddleware`/`DatabaseConnectionMiddleware`; **0** repo-wide matches for `update_id`/`allowed_updates` in `telegram_bot/`; `create_draft_ad` does plain `Ad.objects.create(..., DRAFT)` with no idempotency key. |
| EXT-006 | Present | `decorators.py` `staff_required_api` returns `403` for all non-staff (including `AnonymousUser`); **0** version prefix on `moderation/urls.py`; no JS/template consumer of the bulk API (verified — moderation queue uses per-ad form posts). |

**Environment facts (verified):**
- Cache backend: `django-redis.cache.RedisCache` in prod (`base.py:266`); `LocMemCache` override in dev/test (`base.py:263-264`). `cache.add` is the atomic "insert-if-absent" primitive — already used in `apps/search/services/rate_limit.py:52` and `src/telegram_bot/services/rate_limit.py:52`.
- Fail-open pattern precedent: `apps/lookups/signals.py:31-38` catches `(ConnectionInterrupted, redis.RedisError)` and continues.
- aiogram 3.30.0: `BaseMiddleware` importable from `aiogram`; `TelegramRetryAfter`/`TelegramBadRequest`/`TelegramForbiddenError` all route through `AiogramError` → `Exception` (verified via `uv run python`).
- **`httpx` is NOT a current dependency** (`pyproject.toml`: only `deep-translator`, `aiogram`, `redis`, `django-redis`). The EXT-001 httpx migration therefore requires a dependency decision — see Research gate.
- `nginx.conf` and `nginx.dev.conf` are **two independent files, not symlinked** — every nginx edit must be mirrored.

> **No source code is modified by this plan.** It is an execution specification. Each block below is atomic, semantic (no line numbers), and independently reviewable.

---

## 2. Remaining Work Summary

| # | Block ID | Finding | Scope | Agents | Risk |
|---|----------|---------|-------|--------|------|
| 1 | `ext001a_except_narrowing` | EXT-001 | Narrow `except` to include `deep_translator.exceptions` family | Implementor | low (safety gate) |
| 2 | `ext001b_retry_backoff_semaphore` | EXT-001 | Retry/backoff + bounded Semaphore; collapse double-hop | Implementor | medium |
| 3 | `ext001c_httpx_migration` | EXT-001 | httpx migration (staged) | Implementor + Researcher (gate) + Validator | high |
| 4 | `ext002_immediate_alerts_bridge` | EXT-002 | Bot-per-thread reuse, `return_exceptions`, global thread pool, 429 retry, narrow `except` | Implementor | medium |
| 5 | `ext003a_nginx_rate_limiting` | EXT-003 | `limit_req` zone on `location /` + `/moderation/` (both nginx configs) | Implementor | low |
| 6 | `ext003b_bulk_api_cap` | EXT-003 | Application-level `MAX_BULK_ACTIONS` cap in `api_bulk.py` | Implementor | low |
| 7 | `ext004_security_headers` | EXT-004 | HSTS on `/protected-media/` + site-wide `Referrer-Policy`/`Permissions-Policy` (both configs) | Implementor | trivial |
| 8 | `ext005_dedup_middleware` | EXT-005 | New `UpdateIdDedupMiddleware`; register in `main.py` + bot `conftest` `dp` fixture; no migration | Implementor | low |
| 9 | `ext006a_authz_status_split` | EXT-006 | Split `staff_required_api` 401 (unauth) / 403 (authz-denied) | Implementor | low |
| 10 | `ext006b_api_versioning` | EXT-006 | `/api/v1/` version prefix on moderation JSON endpoint | Implementor + Validator (gate) | low |

---

## 3. Dependency DAG

```
  ext001a (narrow except)                        ◄── HARD GATE
          │
          ├─► ext001b (retry+semaphore)          ◄── depends on ext001a
          │        │
          │        └─► ext001c (httpx migration) ◄── depends on ext001b [RESEARCH GATE]
          │
          ▼
  (all other findings are independent of EXT-001 staging
   and of each other — parallel-safe, disjoint files)

  ext003a (nginx rate-limit) ──┬──► same files ──┐
  ext004  (nginx headers)      ──┴──► SEQUENTIAL ─┘   (NOT parallel — both edit nginx.conf + nginx.dev.conf)

  ext003b (backend cap)       — disjoint (api_bulk.py)
  ext002  (alerts bridge)     — disjoint (immediate_alerts.py)
  ext005  (dedup middleware)  — disjoint (telegram_bot middlewares + main + conftest)
  ext006a (authz split)       — disjoint (decorators.py + test_decorators.py)
  ext006b (versioning)       — disjoint (urls.py + test_priority_service.py) [VALIDATOR GATE]

  ┌──────────────────────────────────────────────────────┐
  │  ext001a MUST ship before ext001b and ext001c.       │
  │  A bare narrowing to (TimeoutError, RequestException)│
  │  WITHOUT the deep_translator.exceptions family lets │
  │  429/RequestError/TranslationNotFound propagate to  │
  │  translate_all_languages' gather → crash ad create. │
  │  ext001a INCLUDES the family → safe prerequisite.   │
  └──────────────────────────────────────────────────────┘
```

**Ordering rules:**
1. `ext001a` → `ext001b` → `ext001c` (hard chained prerequisite, per the EXT-001 gating mandate).
2. `ext003a` and `ext004` edit the **same two** nginx files → must be **sequential** (not parallel). Order arbitrary.
3. Everything else has no ordering constraint among itself; the single-Implementor constraint makes them effectively sequential, but any order is valid.

---

## 4. Rollout Sequence (recommended)

| Step | Block | Parallel-safe with | Notes |
|------|-------|--------------------|-------|
| 1 | **`ext001a`** (narrow except) | all other blocks | Ships the safety gate first; safe, minimal, backward-compatible. |
| 2 | **`ext003a`** (nginx rate-limit) | ext003b, ext002, ext005, ext006a, ext006b, ext002 | Mandatory HIGH; additive nginx change. |
| 3 | **`ext004`** (nginx headers) | — (after ext003a: same files) | Same nginx files; do immediately after ext003a. |
| 4 | **`ext003b`** (bulk cap) | all (disjoint) | Backend code; can slot anywhere. |
| 5 | **`ext001b`** (retry+semaphore) | ext002, ext005, ext006a/b (all) | Unlocks after ext001a ✓. |
| 6 | **`ext005`** (dedup middleware) | all (disjoint) | Independent. |
| 7 | **`ext002`** (alerts bridge) | all (disjoint) | Independent. |
| 8 | **`ext006a`** (authz 401/403) | all except ext006b | Independent. |
| 9 | **`ext006b`** (versioning) | ext003a, ext003b, ext005 (disjoint) | After Validator consumer-check gate. |
| 10 | **`ext001c`** (httpx) | — | Staged; after Research gate resolves + ext001b ✓. |

**PR grouping recommendation:**
- **PR 1:** `ext001a` (EXT-001 narrowing) — standalone safety gate, ship first.
- **PR 2:** `ext003a` + `ext004` (nginx hardening — rate-limit + headers, same files, one deploy).
- **PR 3:** `ext003b` (bulk API cap) — small backend change.
- **PR 4:** `ext001b` (EXT-001 retry+semaphore) — layered on PR 1.
- **PR 5:** `ext005` (dedup middleware) + `ext002` (alerts) — both bot/web async-bridge hardening (conceptually adjacent).
- **PR 6:** `ext006a` + `ext006b` (moderation API contract: 401/403 + versioning) — same API surface, one contract change.
- **PR 7 (staged follow-up):** `ext001c` (httpx migration) — after Research gate.

> `ext001a` is the **only** hard cross-block gate. Its absence would turn `ext001b`/`ext001c` into a latent crash. No other finding blocks another.

---

## 5. Execution Blocks

<!-- TASK_START: ext001a_except_narrowing -->

### Block 1: EXT-001a — Narrow the translation `except` clause (HARD PREREQUISITE)

```yaml
id: ext001a_except_narrowing
title: "EXT-001: Narrow except clause in translate_text to include deep_translator.exceptions family (prerequisite gate)"
source_reference: .ai/plans/23-external-api-finding-fixes.md
source_section: "Block 1: EXT-001a"
priority: high              # safety gate; unblocks retry/backoff + httpx stages
depends_on: []              # no predecessor — ships first
classification: mandatory   # hard gating prerequisite per audit Warning #1
risk: low                   # backward-compatible: family was already caught by the Exception term;
                            # the only behavior change is programming errors (AttributeError/KeyError)
                            # now propagate instead of being silently swallowed
agents: [Implementor]
```

**Description:**
`translate_text` in `translation.py` catches `(TimeoutError, RequestException, Exception)` — the trailing `Exception` makes this a catch-all that masks programming errors and prevents correct exception classification for the retry stage. The audit's Validation Note #1 (verified via `uv run python`) confirms `deep_translator.exceptions.{TooManyRequests, RequestError, TranslationNotFound}` subclass **only `Exception`**, **not** `requests.exceptions.RequestException`. A naive narrowing to `(TimeoutError, RequestException)` alone would therefore **exclude** the actual retryable translation-protocol errors and let Google 429 / non-200 / no-element propagate into `translate_all_languages`' `asyncio.gather` → ad-creation crash. This block ships the **correct** narrowing that *includes* the family — the prerequisite for `ext001b` (retry/backoff) and `ext001c` (httpx).

**Approach chosen:**
1. **Replace** the catch-all `except (TimeoutError, RequestException, Exception) as e:` with the explicitly-inclusive family:
   `except (TimeoutError, RequestException, deep_translator.exceptions.TooManyRequests, deep_translator.exceptions.RequestError, deep_translator.exceptions.TranslationNotFound) as e:`
   The fallback path (`_CIRCUIT_BREAKER.record_failure()` → log → return original `text`) is preserved unchanged.
2. The exception-classification split (retryable vs fallback-only) is **not** introduced here — that belongs to `ext001b`. This block is purely the safe narrowing that keeps ad creation from crashing on the family.

**Rejected alternative:** Narrowing to `(TimeoutError, RequestException)` alone (without the family). **Rejected —** verified to crash ad creation on the first Google 429 / no-element (the family is excluded and propagates). This is the exact hazard the prerequisite exists to prevent.

**Implementation scope:**
- `src/backend/apps/core/services/translation.py` — function `translate_text`:
  - Add `import deep_translator.exceptions` (and keep `from requests.exceptions import RequestException`).
  - Replace the `except` clause with the family-inclusive tuple above.
- **No change** to `ad_create.py` `translate_all_languages` gather in this block (its `return_exceptions=True` gap is addressed in `ext001b` as part of the double-hop collapse; narrowing alone does not require it).

**Architectural constraints:**
- The narrowing must be a **superset** of current behavior on the translation exception family (all 5 types still fall back) — guaranteed because the family terms are explicitly listed and the catch-all `Exception` removal only lets *non-family* errors propagate.
- `translate_cached_generic` and `translate_cached` (the `lru_cache` callers) are **not** touched — they call `GoogleTranslator(...).translate()` directly and are outside the timeout/except path; their callers (`translate_text`) own the resilience boundary.

**Tests / verification:**
- Extend `src/backend/apps/core/tests/test_multi_lang_translation.py` (bot-side translation test) — wait, translation service tests are under `src/backend/apps/core/tests/`. Confirm the translation service test module path and add a unit test: `test_narrowed_except_catches_deep_translator_family` — assert that raising `deep_translator.exceptions.TooManyRequests`, `RequestError`, `TranslationNotFound` from the (mocked) translator produces fallback-to-original-text (not propagation). Add `pytestmark = [pytest.mark.unit]`.
- Verify a **non-family** error (`AttributeError` / `KeyError`) now propagates (assert `pytest.raises`) — pins the "programming errors surface" intent.

**Acceptance criteria:**
- `translate_text` `except` clause lists exactly `TimeoutError, RequestException, deep_translator.exceptions.TooManyRequests, deep_translator.exceptions.RequestError, deep_translator.exceptions.TranslationNotFound`.
- Raising any of the three `deep_translator.exceptions` family → fallback to original text (no crash).
- Raising `AttributeError` / `KeyError` (non-family) → propagates (no silent swallow).
- No migration; no behavioral change for the happy path or existing fallback.
- `ruff check translation.py`; `basedpyright translation.py`.

**Run command:**
```powershell
$dc run --rm -e PYTEST_OPTS="-k test_narrowed_except" test
```

<!-- TASK_END: ext001a_except_narrowing -->

---

<!-- TASK_START: ext001b_retry_backoff_semaphore -->

### Block 2: EXT-001b — Add retry/backoff + bounded Semaphore (collapse double-hop)

```yaml
id: ext001b_retry_backoff_semaphore
title: "EXT-001: Add bounded retry/backoff + Semaphore-bounded concurrency in translate_text/translate_all_languages"
source_reference: .ai/plans/23-external-api-finding-fixes.md
source_section: "Block 2: EXT-001b"
priority: medium
depends_on: [ext001a_except_narrowing]   # MUST ship after narrowing — unblocks correct retry classification
classification: advisory
risk: medium
agents: [Implementor]
```

**Description:**
With the except clause narrowed (ext001a), `translate_text` now has a correct exception-classification surface. This block adds bounded retry with capped exponential backoff and replaces the abandoned-`ThreadPoolExecutor`-future stall pattern with a bounded `Semaphore` so throttled saturation degrades to fallback instead of stalling ad creation. It also adds `return_exceptions=True` to the `translate_all_languages` gather so a single locale's failure no longer aborts the batch.

**Exception classification (from narrowed set):**
- **Retry (with backoff):** `TimeoutError`, `RequestException`, `deep_translator.exceptions.TooManyRequests` (429), `deep_translator.exceptions.RequestError` (non-200).
- **Fall back only (no retry — same input returns same response):** `deep_translator.exceptions.TranslationNotFound` (no-element).
- **Propagate:** anything outside the narrowed set (programming errors) — already handled by ext001a.

**Implementation scope:**
- `src/backend/apps/core/services/translation.py` — function `translate_text`:
  - Wrap the single `future.result(timeout=...)` attempt in a **bounded retry loop** (1–2 retries, e.g. 2 total attempts with `TRANSLATION_BACKOFF_BASE`/`TRANSLATION_MAX_ATTEMPTS` constants).
  - Honor 429 backoff where possible (the audit notes `TooManyRequests` has no structured `retry_after` in deep_translator ≤1.9.1; use a fixed capped backoff ≈ 100–200ms — document as a known limitation; the httpx stage may improve this).
  - Keep the existing circuit-breaker (`_CIRCUIT_BREAKER`) integration: record failure on each attempt, short-circuit when open — the retry loop sits *inside* the circuit-closed branch.
- `src/telegram_bot/handlers/ad_create.py` — function `translate_all_languages`:
  - Bound the `asyncio.to_thread(translate_text, ...)` fan-out with an `asyncio.Semaphore` (e.g. `min(3, len(locale))` — bot currently targets 3 locales) so concurrent translation dispatches are capped and saturated throttling degrades to fallback rather than exhausting the 4-worker pool.
  - Add `return_exceptions=True` to the `asyncio.gather` so one locale's failure does not cancel sibling in-flight sends (mirrors EXT-002's requirement). Classify results: map an exception result → original text fallback (consistent with `translate_text`'s own fallback).

**Decision point (documented, not a gate):**
- Retry count: 2 attempts total (1 retry). Rationale: §5(c) requires retry/backoff; the 500ms timeout means aggressive retry risks compounding latency — 2 attempts bounds it. The Implementor confirms against test outcomes.
- The `_EXECUTOR` module-level `ThreadPoolExecutor(max_workers=4)` is **retained** (not removed in this stage) — the Semaphore at the caller bounds the *dispatch*, and the executor remains the bounded work pool. The "double-hop" is collapsed conceptually by Semaphore-bounding the `to_thread` calls rather than removing the executor (full removal is the httpx stage, ext001c).

**Tests / verification:**
- `src/backend/apps/core/tests/` translation service test: `test_retry_succeeds_after_transient_failure` (mock raises `TimeoutError` once, then returns translated → succeeds with retry); `test_too_many_requests_retried_then_fallback` (mock raises `TooManyRequests` → retried, then circuit opens/fallback). 
- Bot-side: extend `src/telegram_bot/tests/test_multi_lang_translation.py` — `test_gather_return_exceptions_isolates_failure` (one locale raises non-family error that *would* propagate; verify other locales still get translations — but note: after ext001a, only non-family errors propagate; with `return_exceptions=True` they become result entries, not crashes). Assert the caller maps them to fallback.

**Acceptance criteria:**
- `translate_text` retries retryable exceptions with backoff (≤2 attempts).
- `TranslationNotFound` is NOT retried (fallback only).
- `translate_all_languages` gather uses `return_exceptions=True` and a `Semaphore` bound on `to_thread` dispatch.
- Circuit-breaker still opens after 3 consecutive failures (existing test `test_circuit_breaker_open_short_circuits` still passes).
- No migration.
- `ruff check`/`basedpyright` clean on both files.

**Run command:**
```powershell
$dc run --rm -e PYTEST_OPTS="-k 'retry or circuit_breaker or gather'" test
```

<!-- TASK_END: ext001b_retry_backoff_semaphore -->

---

<!-- TASK_START: ext001c_httpx_migration -->

### Block 3: EXT-001c — httpx migration (STAGED; requires Research decision gate)

```yaml
id: ext001c_httpx_migration
title: "EXT-001: Migrate translation client from deep_translator/requests to httpx with per-request timeout + cancel scope"
source_reference: .ai/plans/23-external-api-finding-fixes.md
source_section: "Block 3: EXT-001c"
priority: medium
depends_on: [ext001b_retry_backoff_semaphore]   # staged after retry+semaphore per audit
classification: advisory
risk: high            # large refactor; dependency + protocol decision
agents: [Implementor, Researcher, Validator]
research_gate: REQUIRED   # httpx not a current dependency; protocol/approach ambiguous
```

**Description:**
`deep_translator`'s `GoogleTranslator.translate()` invokes `requests.get(...)` with **no `timeout=` kwarg** (verified in installed `deep_translator/google.py`), so a hung upstream keeps the `_EXECUTOR` worker blocked until TCP retransmit/idle expiry (~tens of seconds) — the worker can never be reclaimed and ad creation stalls once the 4 workers saturate. The fix is to migrate the translation call to `httpx` with an explicit per-request timeout and a cancel scope so a timed-out call is **actually cancelled** (not just abandoned).

**Research decision gate (must resolve before implementation):**
`httpx` is **not** a current dependency. The migration has >1 viable approach — a Researcher must resolve the decision and record it in `.ai/research/` before the Implementor proceeds. The decision must weigh:

| Approach | What | Concern | Decision criteria |
|----------|------|---------|-------------------|
| **A. httpx → official Google Cloud Translation API** | Replace scraping with REST API (paid, requires `GOOGLE_TRANSLATE_API_KEY` secret) | New secret management + cost model change (free→paid) | Reject if project forbids paid external API / secret churn unacceptable. |
| **B. httpx → Google Translate web endpoint (reimplement scraping)** | Replace `deep_translator` with a thin httpx client hitting the same web endpoint | Google actively breaks scrapers (TS token, cookies); fragile; high maintenance | Acceptable only if a stable, minimal httpx scraper exists/reusable. |
| **C. httpx as a timeout wrapper ONLY (keep deep_translator protocol)** | Add `httpx` solely to gate `deep_translator`'s call with a real timeout/cancel | `deep_translator` uses `requests`, not `httpx` — can't wrap its internal call without monkeypatching; does not truly solve the orphaned-worker problem | Weak — likely insufficient. |
| **D. concurrent.futures + thread kill (no httpx)** | Run `deep_translator` in `ThreadPoolExecutor` with a hard wall-clock + `shutdown(cancel_futures=True)` | `requests` is uninterruptible on a non-blocking socket; can only bound latency, not cancel the in-flight call | Bounds latency only; does not reclaim the worker mid-call. |

**Decision rule (pre-recorded by Researcher):** Choose the approach that adds `httpx` with a per-request `timeout` + structured concurrency cancel scope (httpx `AsyncClient` with `timeout=` + `anyio`-style cancel scope, or sync `httpx.Client` with `timeout` + a `concurrent.futures` boundary). If Approach A (official API) is feasible (secret + cost approved), prefer it (stable, supported). If the project must stay on free scraping, Approach B with httpx is required and the Researcher must confirm a viable minimal client (no fragile TS-token reimplementation).

> **Gate dependency:** `ext001c` is **blocked** until the Researcher decision is recorded. It also depends on `ext001b` ✓ (retry+semaphore shipped) and `ext001a` ✓ (narrowing shipped), so the httpx stage inherits correct exception classification.

**Implementation scope (once gate passes):**
- `src/backend/apps/core/services/translation.py`:
  - Replace `GoogleTranslator(...).translate(query)` calls in `translate_cached` and `translate_cached_generic` with an httpx call carrying an explicit `timeout` (matching `TRANSLATION_TIMEOUT_SECONDS` semantics — the 500ms bound becomes a *real* per-request timeout, not just `future.result` abandonment).
  - Wrap the call in a cancel scope so a timed-out request is actually cancelled (reclaiming the executor worker). This is the payoff: the 4-worker pool is no longer permanently saturated by hung upstream sockets.
  - Add `httpx` to `pyproject.toml` dependencies (`uv add httpx`); remove/replace `deep-translator` if Approach A or B fully supersedes it (Researcher decision).
- `src/telegram_bot/handlers/ad_create.py` — no change expected (the double-hop collapse already happened in ext001b); the httpx client is internal to `translation.py`.

**Tests / verification:**
- Unit: mock the httpx transport; assert a `timeout` exception is raised and retry/fallback engages (the narrowed except from ext001a handles it).
- Validator: smoke-test the real (or test-credential) translation path end-to-end if Approach A uses a stub/test API key; otherwise confirm no orphaned-worker stall under a mocked hung upstream.

**Acceptance criteria:**
- `httpx` per-request timeout is enforced (a hung upstream no longer blocks an executor worker past the timeout).
- Cancel scope reclaims the worker on timeout (no permanent saturation under 4 concurrent hung calls).
- `deep_translator` exceptions family still correctly mapped to retry/fallback (ext001a narrowing intact).
- `uv add httpx` recorded in `pyproject.toml`.
- Researcher decision documented in `.ai/research/ext-001c-httpx-decision.md`.

**Run command:**
```powershell
$dc run --rm -e PYTEST_OPTS="-k 'httpx or translate_text'" test
```

<!-- TASK_END: ext001c_httpx_migration -->

---

<!-- TASK_START: ext002_immediate_alerts_bridge -->

### Block 4: EXT-002 — Harden the immediate-alert delivery bridge

```yaml
id: ext002_immediate_alerts_bridge
title: "EXT-002: One Bot per thread/loop, return_exceptions, global thread pool, 429 retry, narrow except"
source_reference: .ai/plans/23-external-api-finding-fixes.md
source_section: "Block 4: EXT-002"
priority: medium
depends_on: []              # independent of all other findings
classification: advisory
risk: medium                # gated default-OFF (IMMEDIATE_ALERTS_ENABLED) → zero blast radius until enabled
agents: [Implementor]
```

**Description:**
`deliver_immediate_alerts` spawns a daemon thread per published ad (`threading.Thread(target=_run_send, ...)`), constructs a fresh `Bot(token=...)` per message inside `_send` (→ a fresh `aiohttp` session per recipient), uses a **per-thread** `asyncio.Semaphore` (not global → unbounded fan-out under publish bursts), and handles only `TelegramBadRequest`/`TelegramForbiddenError` per message while a bare `except Exception` at `_run_send` drops transient errors (network reset, 5xx, 429-with-`retry_after`) with no retry. The `asyncio.gather` lacks `return_exceptions=True`, so a single failed `_send` cancels all in-flight sibling sends.

**Reference pattern (existing, correct):** `src/backend/apps/search/management/commands/send_alerts.py` — lines 145/182 construct **one** `Bot(token=bot_token)`, reuse it across the batch, and close it once via `await bot.session.close()` in a `finally` block. The audit explicitly corrected the recommendation (Validator report): a process-global shared `Bot` is **infeasible** (`aiohttp.ClientSession` binds to the event loop at creation; `asyncio.run` creates a fresh loop per thread). The correct pattern is **one Bot per thread/loop, reused across the batch**.

**Approach chosen:**
- Construct **one `Bot` per thread/loop** at the top of `_run_send` (or `_send_payloads`), shared across the batch, closed once in `finally` (mirroring `send_alerts.py:145/182`). NOT a module-level shared `Bot`.
- Move `asyncio.Semaphore(_SEND_CONCURRENCY=10)` to a **process-global** bound (module-level or a `BoundedThreadPoolExecutor` controlling thread count) so N publish bursts → N threads is capped globally, not per-thread.
- Add `return_exceptions=True` to the `asyncio.gather` in `_send_payloads`.
- Classify per-send results:
   - **Retry (transient, with backoff):** `AiogramError` subtypes `TelegramRetryAfter` (honor `retry_after`), `TelegramNetworkError` (network reset), `TelegramServerError` (5xx) — retry with capped backoff.
  - **Dead-letter (permanent):** `TelegramForbiddenError` (chat blocked/bot removed), `TelegramBadRequest` (bad chat_id) — log + skip without retry.
- Narrow the bare `except Exception` at `_run_send` to `except AiogramError` so programming errors propagate.

**Implementation scope:**
- `src/backend/apps/search/services/immediate_alerts.py` — functions `_run_send` and `_send_payloads`:
  - Hoist `Bot(token=settings.BOT_TOKEN)` creation out of the per-message `_send` closure to `_send_payloads` (one per thread/loop), shared across all `_send` coroutines; `await bot.session.close()` in `finally`.
  - Move the `asyncio.Semaphore` to module level (`_DELIVERY_SEMAPHORE`) as a process-global concurrency cap, OR replace the `threading.Thread` spawn with a bounded `ThreadPoolExecutor(max_workers=_MAX_DELIVERY_THREADS)` so the number of concurrent daemon threads is globally bounded (recommended — addresses the "unbounded daemon threads" hull).
  - Add `return_exceptions=True` to `asyncio.gather`.
  - Re-import: `from aiogram.exceptions import AiogramError, TelegramRetryAfter, TelegramNetworkError, TelegramServerError, TelegramBadRequest, TelegramForbiddenError` (all verified subclasses of `AiogramError` in installed aiogram 3.30.0).
  - Per-send `except` narrowed to the AiogramError family with retry/backoff for `TelegramRetryAfter` (honor `retry_after`), `TelegramNetworkError` (network reset/5xx) and `TelegramServerError` (5xx); dead-letter for `TelegramBadRequest`/`TelegramForbiddenError`.
  - `_run_send`: `except AiogramError` (drop the bare `except Exception`).

**Tests / verification:**
- New test module `src/backend/apps/search/tests/test_immediate_alerts.py` (or extend existing alert tests): `test_one_bot_per_thread_reused` (assert `Bot` constructed once, `session.close` called once per batch); `test_gather_return_exceptions_isolates_failure` (one send raises `TelegramForbiddenError`, others proceed); `test_429_retry_after_honored` (mock `TelegramRetryAfter` with `retry_after`, assert backoff `sleep` called).
- Mark `pytestmark = [pytest.mark.unit]` (no live Telegram — mock `Bot`).

**Acceptance criteria:**
- Exactly one `Bot` constructed per deliver call (not per message); `session.close()` called once in `finally`.
- Global thread bound exists (process-level semaphore or bounded executor).
- `asyncio.gather` has `return_exceptions=True`.
- Per-send `except` classifies retry vs dead-letter; `TelegramRetryAfter.retry_after` is honored.
- `_run_send` catches `AiogramError` (not bare `Exception`).
- `ruff check`/`basedpyright` clean.

**Run command:**
```powershell
$dc run --rm -e PYTEST_OPTS="-k 'immediate_alerts or _send_payloads'" test
```

<!-- TASK_END: ext002_immediate_alerts_bridge -->

---

<!-- TASK_START: ext003a_nginx_rate_limiting -->

### Block 5: EXT-003a — Reverse-proxy rate limiting on public browse + moderation

```yaml
id: ext003a_nginx_rate_limiting
title: "EXT-003: Add limit_req zones to location / and /moderation/ in nginx.conf + nginx.dev.conf"
source_reference: .ai/plans/23-external-api-finding-fixes.md
source_section: "Block 5: EXT-003a"
priority: high             # mandatory — sole HIGH finding
depends_on: []             # independent
classification: mandatory
risk: low                  # additive: only abusive floods throttled; legit clients pass
agents: [Implementor]
```

**Description:**
`nginx.conf` defines only `login_limit` (10 r/s) and `search_limit` (20 r/s) and attaches `limit_req` to `/login/` and `/search/` only. The public browse surface (`location /` — catalog, category, ad detail, HTMX fragments) and the moderation API (`/moderation/`) inherit no `limit_req`, leaving them open to unthrottled floods while each request does non-trivial ORM work (M2M joins + `distinct` + `Paginator.count` + favorites sub-query).

**Approach chosen:**
- Add a new `browse_limit` zone (rate ≈ `20r/s`, mirroring `search_limit`) — decision documented below.
- Attach `limit_req zone=browse_limit burst=40 nodelay;` to `location /` and a `location /moderation/` block.
- Add `limit_req_status 429;` at the `http` level so throttled requests return a clean 429 (visible in logs) rather than nginx's default 503.

**Decision point (documented, not gated):** rate value. `search_limit` is 20 r/s (search is the FTS DoS amplifier, already capped). Browse is a *lighter* path but still unthrottled. Recommendation: `browse_limit = 20r/s, burst=40` — equal to search, since both serve anonymous buyers and the catalog is the higher-traffic surface. The Implementor may tune burst upward if legit browser pagination bursts exceed 40 req/s in staging (rare). No tuning knob exposed to app code — proxy-only.

**Implementation scope (semantic — both files):**
- `docker/nginx/nginx.conf`:
  - `http` block: add `limit_req_zone $binary_remote_addr zone=browse_limit:10m rate=20r/s;` after the existing `search_limit` declaration.
  - `location /moderation/ { limit_req zone=browse_limit burst=40 nodelay; ... proxy_pass ... }` — add a dedicated moderation location (currently moderation falls through `location /`).
  - `location /` — add `limit_req zone=browse_limit burst=40 nodelay;`.
  - `http` block: add `limit_req_status 429;`.
- `docker/nginx/nginx.dev.conf`: mirror the above exactly (no HSTS in dev by design; `limit_req_status` applies in both).

> **Shared-file constraint:** `ext004` edits the *same* two nginx files. `ext003a` and `ext004` must be **sequential** (not parallel). Recommended order: `ext003a` then `ext004` (or vice-versa) in the same PR/deploy.

**Tests / verification:**
- nginx config validation: `nginx -t -c docker/nginx/nginx.conf` and `-c docker/nginx/nginx.dev.conf` (can run in a throwaway nginx container or via the dev compose service).
- Grep assertion: `limit_req zone=browse_limit` appears in both `location /` and `location /moderation/` in both configs.

**Acceptance criteria:**
- `browse_limit` zone declared in `http` block of both configs.
- `location /` and `location /moderation/` each carry `limit_req zone=browse_limit burst=40 nodelay;` in both configs.
- `limit_req_status 429;` present in `http` block of both configs.
- `nginx -t` passes on both configs.
- No `limit_req` removed from existing `/login/` or `/search/`.

**Run command:**
```powershell
docker run --rm -v ${PWD}/docker/nginx/nginx.conf:/etc/nginx/nginx.conf:ro nginx:1.27-alpine nginx -t -p /tmp/nginx/
```

<!-- TASK_END: ext003a_nginx_rate_limiting -->

---

<!-- TASK_START: ext003b_bulk_api_cap -->

### Block 6: EXT-003b — Application-level cap on bulk moderation `selected_items`

```yaml
id: ext003b_bulk_api_cap
title: "EXT-003: Cap selected_items batch size in bulk_moderation_action (MAX_BULK_ACTIONS)"
source_reference: .ai/plans/23-external-api-finding-fixes.md
source_section: "Block 6: EXT-003b"
priority: high             # mandatory
depends_on: []             # independent; parallel-safe with all blocks (disjoint file)
classification: mandatory
risk: low                  # no legitimate consumer sends >100 (queue renders one ad at a time)
agents: [Implementor]
```

**Description:**
`bulk_moderation_action` in `api_bulk.py` iterates `for ad_id in ad_ids:` with no upper bound on `selected_items` — a single request can drive N× DB mutations (approve/reject/flag). This is the application-layer complement to `ext003a`'s proxy `limit_req` (proxy caps *rate*; app caps *batch size*). Decoupling is intentional: rate-limiting and batch-size are independent DoS surfaces.

**Approach chosen:**
- Add a module-level constant `MAX_BULK_ACTIONS: Final[int] = 100` (aligned to `BulkModerationAction` usage).
- After parsing `ad_ids`, reject with `400` if `len(ad_ids) > MAX_BULK_ACTIONS` — **before** entering the per-ad processing loop. Return `{"error": "selected_items exceeds maximum of N"}` so the caller knows the cap.

**Rejected alternative:** Capping *silently* (truncate to 100). **Rejected** — a silent truncate hides a malformed/buggy client and risks the moderator believing more ads were acted on than were. Explicit `400` is observable and matches §5(h) "rate-limit / batch bounds are observable."

**Implementation scope:**
- `src/backend/apps/moderation/views/api_bulk.py` — function `bulk_moderation_action`:
  - Add `MAX_BULK_ACTIONS: Final[int] = 100` and `from typing import Final` (if not present — confirm via `apps/core/enums.py` pattern; `api_bulk.py` currently imports no `Final`).
  - Insert the length guard immediately after `ad_ids: list[int] = data.get("selected_items", [])` and before the `try: action_enum = BulkModerationAction(action)` block.
- `src/backend/apps/moderation/views/decorators.py` — no change (the 401/403 split in ext006a is a separate, composable concern).

**Tests / verification:**
- Extend `TestBulkModerationActionView` in `test_priority_service.py`: `test_bulk_exceeds_max_actions_returns_400` (staff, 101 ids → 400); `test_bulk_at_max_actions_ok` (100 ids → 200, no 400). Reuse `bulk_url = reverse("moderation:bulk_action")` and `staff_user` fixture.

**Acceptance criteria:**
- `MAX_BULK_ACTIONS = 100` constant present.
- `len(ad_ids) > 100` → `400` JSON `{"error": ...}` before any DB write.
- `len(ad_ids) == 100` → proceeds (no false rejection).
- Existing tests (`test_requires_staff_forbidden`, `test_bulk_approve`, etc.) unaffected.
- `ruff check`/`basedpyright` clean.

**Run command:**
```powershell
$dc run --rm -e PYTEST_OPTS="-k 'TestBulkModerationActionView and bulk_max'" test
```

<!-- TASK_END: ext003b_bulk_api_cap -->

---

<!-- TASK_START: ext004_security_headers -->

### Block 7: EXT-004 — Security headers on `/protected-media/` + site-wide Referrer/Permissions-Policy

```yaml
id: ext004_security_headers
title: "EXT-004: Re-add HSTS to /protected-media/ + add site-wide Referrer-Policy and Permissions-Policy"
source_reference: .ai/plans/23-external-api-finding-fixes.md
source_section: "Block 7: EXT-004"
priority: low
depends_on: [ext003a_nginx_rate_limiting]   # SAME nginx files → must be sequential after ext003a
classification: advisory
risk: trivial
agents: [Implementor]
```

**Description:**
Server-level `add_header Strict-Transport-Security` (nginx `Strict-Transport-Security`) is silently **dropped** on `/protected-media/` responses because that location block declares its own `add_header`s (nginx inheritance rule: any `add_header` in a location kills all inherited server-level `add_header`s). Protected media is served by nginx directly via `X-Accel-Redirect` — Django's `SecurityMiddleware` HSTS does **not** apply — so only the nginx `add_header` could cover it, and it's missing. Additionally, no `Referrer-Policy` or `Permissions-Policy` is emitted anywhere.

**Approach chosen:** Re-declare `Strict-Transport-Security` inside `/protected-media/`, replicating the **correct pattern** already at `/static/` (nginx.conf lines 66–69 redeclare all four headers including HSTS). Add a site-wide `Referrer-Policy: strict-origin-when-cross-origin` and `Permissions-Policy: geolocation=(), microphone=(), camera=()` (no cross-origin features required) at the **server level** so they inherit to all locations that don't override headers.

> The audit offers an alternative (extract headers into an `include`'d snippet). **Rejected for this phase** — that's a refactor touching every location block and risks breaking the inheritance model; the targeted re-addition at `/protected-media/` (matching the existing `/static/` pattern) is minimal, backward-compatible, and resolves the finding. Snippet extraction can be a Phase-2 cleanup.

**Implementation scope (both nginx configs):**
- `docker/nginx/nginx.conf`:
  - `/protected-media/` block: add `add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;` (matching the `/static/` block).
  - Server level: add `add_header Referrer-Policy "strict-origin-when-cross-origin" always;` and `add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;` alongside the existing server-level headers.
- `docker/nginx/nginx.dev.conf`: mirror exactly (note: dev has HSTS off by design at server level — but `/protected-media/` in dev currently has NO HSTS either since dev server level omits it; re-adding `Referrer-Policy`/`Permissions-Policy` is the universal win, HSTS in dev is intentionally omitted).

**Tests / verification:**
- `nginx -t` on both configs (no syntax errors, especially around `add_header` placement).
- Grep: `Strict-Transport-Security` present in `/protected-media/` of `nginx.conf`; `Referrer-Policy` + `Permissions-Policy` present in server-level of both configs.

**Acceptance criteria:**
- `/protected-media/` in `nginx.conf` re-declares `Strict-Transport-Security` (matching `/static/` pattern).
- Server level in both configs has `Referrer-Policy: strict-origin-when-cross-origin`.
- Server level in both configs has `Permissions-Policy` restricting `geolocation`/`microphone`/`camera`.
- `nginx -t` passes on both configs.
- Dev config intentionally keeps server-level HSTS off (matches `dev.py: SECURE_HSTS_SECONDS=0`); `Referrer-Policy`/`Permissions-Policy` still added.

**Run command:**
```powershell
docker run --rm -v ${PWD}/docker/nginx/nginx.conf:/etc/nginx/nginx.conf:ro nginx:1.27-alpine nginx -t
```

<!-- TASK_END: ext004_security_headers -->

---

<!-- TASK_START: ext005_dedup_middleware -->

### Block 8: EXT-005 — Update-level dedup middleware (no migration)

```yaml
id: ext005_dedup_middleware
title: "EXT-005: Add UpdateIdDedupMiddleware to dedup re-delivered Telegram updates (no migration)"
source_reference: .ai/plans/23-external-api-finding-fixes.md
source_section: "Block 8: EXT-005"
priority: medium
depends_on: []              # independent; parallel-safe (disjoint files)
classification: advisory
risk: low                  # fail-open; cache-based; no schema change
agents: [Implementor]
```

**Description:**
`dp.run_polling(bot)` confirms the `getUpdates` offset in memory only. A bot crash between receiving an update and acknowledging it → Telegram re-delivers on restart → `create_draft_ad`'s plain `Ad.objects.create(..., DRAFT)` re-runs → duplicate DRAFT + re-translation + re-photo side-effects. The login deep-link claim is already idempotent (`login.py` `UPDATE … RETURNING` row-lock) but ad creation is not.

**Approach chosen:** `UpdateIdDedupMiddleware` (Approach A, audit-validated). A new `BaseMiddleware` reads `event.update_id` and performs an atomic `cache.add(f"bot_update:{update_id}", 1, timeout=DEDUP_TTL_SECONDS)`. `cache.add` returns `True` **only** on first insertion (the exact primitive at `apps/search/services/rate_limit.py:52` / `src/telegram_bot/services/rate_limit.py:52`). On re-delivery (same `update_id` after crash-restart) → `cache.add` returns `False` → middleware short-circuits (`return None`) **before** any handler runs, suppressing **all** downstream side-effects (duplicate DRAFT, translation gather, photo writes) at one guard point.

> **No migration required** (Validator Warning #4): the chosen approach persists `update_id` in the Django-cache/Redis backing store — **not** on the `Ad` model. The rejected `get_or_create`-keyed-on-`update_id` alternative (which would need a schema migration + `create_draft_ad` signature change) is explicitly rejected — it only guards DRAFT creation, not translation/photo side-effects.

**Implementation scope (semantic):**
- **New file:** `src/telegram_bot/middlewares/update_id_dedup.py` — class `UpdateIdDedupMiddleware(BaseMiddleware)` with `__call__(self, handler, event, data)`:
  - `update_id = event.update_id` (aiogram `Update.update_id` — verified `int`, required field).
  - `added = cache.add(f"bot_update:{update_id}", 1, timeout=DEDUP_TTL_SECONDS)` where `DEDUP_TTL_SECONDS: Final[int] = 86400` (24h — outlives bot restarts and Telegram's re-delivery window).
  - If `added` is `True` → `return await handler(event, data)` (first delivery — proceed).
  - If `added` is `False` → log warning, `return None` (re-delivery — suppress).
  - Wrap `cache.add` in `try/except (ConnectionInterrupted, RedisError)` → **fail-open** (log warning, `return await handler(event, data)`) — mirrors `apps/lookups/signals.py:31-38`. Import: `from django_redis.exceptions import ConnectionInterrupted` + `import redis`.
- `src/telegram_bot/middlewares/__init__.py` — export `UpdateIdDedupMiddleware` in `__all__`.
- `src/telegram_bot/main.py` — register `dp.update.middleware(UpdateIdDedupMiddleware())` (alongside existing `LivenessMiddleware` / `DatabaseConnectionMiddleware`).
- `src/telegram_bot/tests/conftest.py` — register the same middleware in the `dp()` fixture so handler tests exercise the dedup guard (mirrors production `main.py`).

**Architectural constraints:**
- TTL must be `86400` (24h) — longer than any bot restart/re-delivery window; shorter would risk a legit duplicate within the window, longer would retain keys unnecessarily.
- Fail-open is mandatory: a Redis outage must never drop legitimate traffic (the bot would simply lose dedup — acceptable degradation, not a crash).
- `cache.add` is atomic on both Redis (prod) and LocMem (dev/test) — verified.

**Tests / verification:**
- New test module `src/telegram_bot/tests/test_update_id_dedup.py`:
  - `test_first_delivery_proceeds` — `cache.add` returns `True` → handler invoked.
  - `test_redelivered_update_skipped` — `cache.add` returns `False` → handler NOT invoked, returns `None`.
  - `test_redis_unavailable_fail_open` — `cache.add` raises `ConnectionInterrupted` → handler still invoked (fail-open).
  - Use `pytest-asyncio` + `MagicMock`/`AsyncMock` for the handler (no live Telegram).
- Mark `pytestmark = [pytest.mark.unit, pytest.mark.asyncio]`.

**Acceptance criteria:**
- `UpdateIdDedupMiddleware` exists in `middlewares/update_id_dedup.py`, subclasses `aiogram.BaseMiddleware`.
- `cache.add(f"bot_update:{update_id}", 1, timeout=86400)` is the dedup primitive; `cache.add` returns `False` → `return None` (suppress).
- `except (ConnectionInterrupted, redis.RedisError)` → fail-open (proceed).
- Registered in `main.py` `dp.update.middleware(...)` AND bot-test `dp` fixture.
- Exported from `middlewares/__init__.py`.
- No migration; no `Ad` model field added; no `create_draft_ad` signature change.
- `ruff check`/`basedpyright` clean.

**Run command:**
```powershell
$dc run --rm -e PYTEST_OPTS="-k 'test_update_id_dedup'" test
```

<!-- TASK_END: ext005_dedup_middleware -->

---

<!-- TASK_START: ext006a_authz_status_split -->

### Block 9: EXT-006a — Split API authz: 401 (unauth) / 403 (authz-denied)

```yaml
id: ext006a_authz_status_split
title: "EXT-006: Split staff_required_api into 401 (unauthenticated) vs 403 (authenticated-non-staff)"
source_reference: .ai/plans/23-external-api-finding-fixes.md
source_section: "Block 9: EXT-006a"
priority: low
depends_on: []              # independent
classification: advisory
risk: low                  # single consumer (bulk_moderation_action); 403→401 is a stricter, standard code
agents: [Implementor]
```

**Description:**
`staff_required_api` in `decorators.py` returns `403` for any non-staff caller — including an unauthenticated (`AnonymousUser`) request. Per RFC 7235 / §5(e), an unauthenticated caller should receive `401` with a `WWW-Authenticate` challenge; an authenticated-but-non-staff caller should receive `403`. The decorator has **one consumer**: `bulk_moderation_action` in `api_bulk.py` (grep-verified).

**Approach chosen:** Insert an `is_authenticated` branch before the staff check:
```
if not request.user.is_authenticated:
    return JsonResponse({"error": "Authentication required"}, status=401,
                         headers={"WWW-Authenticate": "Bearer"})
if not (request.user.is_staff or request.user.is_superuser):
    return JsonResponse({"error": "Staff access required"}, status=403)
```
This is **additive** for authenticated clients (authz-denied still 403) and only changes the unauthenticated path (403→401) — a well-behaved API client benefits from the `WWW-Authenticate` challenge and can auto-initiate auth. The `WWW-Authenticate: Bearer` scheme matches the project's login-token deep-link flow (see `login.py`).

**Rejected alternative:** Returning `401` for *all* non-staff (collapsing the authn/authz boundary). **Rejected** — it would make authenticated-but-non-staff callers indistinguishable from unauthenticated, losing the 403 signal for authz decisions.

**Implementation scope:**
- `src/backend/apps/moderation/views/decorators.py` — function `staff_required_api`'s inner `wrapper`:
  - Insert the `is_authenticated` → `401` (with `WWW-Authenticate` header) branch **before** the existing `is_staff` check.
  - Keep the existing `403` for authenticated-non-staff.
- Confirm `WWW-Authenticate` scheme matches the project's token auth (login deep-link uses token claims — `Bearer` is the standard scheme; the Implementor cross-checks `users/views/consent.py` / `login.py` for the exact scheme and adjusts the header value if a different one is used).

**Tests / verification:**
- Update `src/backend/apps/moderation/tests/test_decorators.py` — `TestStaffRequiredApi`:
  - Rename/repurpose `test_non_staff_returns_403_json` → add `test_unauthenticated_returns_401` (anonymous: `is_authenticated=False` → 401 + `WWW-Authenticate`). Use `_make_request` with `user.is_authenticated = False`.
  - Add `test_authenticated_non_staff_returns_403` (keep existing semantics for authenticated non-staff).
  - Existing `test_staff_get_returns_405` / `test_staff_post_passthrough` / `test_superuser_post_passthrough` unchanged (staff still pass through; the new 401 branch is *before* the method check, so a GET non-staff still 401/403 — verify ordering: authz-status check precedes method check, matching the current staff-first ordering).
- Update `TestBulkModerationActionView` in `test_priority_service.py`: `test_requires_staff_forbidden` currently asserts 403 for a non-staff *authenticated* user — still valid (authenticated non-staff → 403). No change needed there, but add `test_unauthenticated_returns_401` for completeness (anonymous POST → 401).

**Acceptance criteria:**
- `staff_required_api` returns `401` (with `WWW-Authenticate`) for `AnonymousUser` / `!is_authenticated`.
- Authenticated non-staff still returns `403`.
- Staff/superuser still reaches the view (or 405 for wrong method, as before).
- `staff_required` (template variant) unchanged (404 for non-staff — deny-by-obscurity).
- Tests updated: `test_decorators.py` asserts 401 for unauthenticated; existing 403/405/200 cases intact.
- `ruff check`/`basedpyright` clean.

**Run command:**
```powershell
$dc run --rm -e PYTEST_OPTS="-k 'test_decorators or TestBulkModerationActionView'" test
```

<!-- TASK_END: ext006a_authz_status_split -->

---

<!-- TASK_START: ext006b_api_versioning -->

### Block 10: EXT-006b — Version-prefix the moderation JSON API

```yaml
id: ext006b_api_versioning
title: "EXT-006: Add /api/v1/ version prefix to bulk_moderation_action endpoint"
source_reference: .ai/plans/23-external-api-finding-fixes.md
source_section: "Block 10: EXT-006b"
priority: low
depends_on: []              # independent of ext006a (different file); same API surface
classification: advisory
risk: low                  # NO JS/template consumer verified; only test reverse() affected
agents: [Implementor, Validator]
validator_gate: REQUIRED   # re-verify no consumer before URL move
```

**Description:**
`moderation/urls.py` defines `path("bulk-action/", bulk_moderation_action, name="bulk_action")` with **no version prefix**. §7 requires "API version mismatch (client v1 vs server v2) → handled, not 500." With no version segment, there is no versioning surface to mismatch — the contract is structurally unsatisfiable. The URL is currently served at `POST /moderation/bulk-action/`.

**Pre-implementation Validator gate (must pass before the URL move):**
- Re-verify **no consumer** of `/moderation/bulk-action/` exists beyond the test (`reverse("moderation:bulk_action")` in `test_priority_service.py`). Confirmed in baseline: the moderation queue (`queue.py` / `review.html`) uses per-ad **form posts** (`action="../approve/{{ ad.id }}/"`) to `/moderation/approve/<id>/`, not the bulk API; no JS `fetch` to `/moderation/bulk-action/` exists (grep across `*.html`/`*.js`/`*.ts`/`*.tsx` returned 0 matches). **If any consumer is found, halt and coordinate the URL update with the consumer first.**

**Approach chosen:** Nest the bulk-action route under a version segment **within** `moderation/urls.py`, scoped to the JSON endpoint only (template views `/queue/`, `/review/<id>/`, `/approve/<id>/`, etc. stay on the unversioned `/moderation/` path):
```
path("api/v1/bulk-action/", bulk_moderation_action, name="bulk_action")
```
This moves the JSON endpoint to `POST /moderation/api/v1/bulk-action/` while leaving the template UI URLs (`/moderation/queue/`, etc.) untouched. An unknown version (`/moderation/api/v2/...`) degrades to `404` (no route match) — satisfying §7 "handled, not 500." The `name="bulk_action"` is preserved so `reverse("moderation:bulk_action")` keeps working (test needs no URL change — only the resolver picks up the new path).

**Rejected alternative:** Moving the entire moderation app under `/api/v1/moderation/...`. **Rejected** — the moderation app mixes template views (queue/review, server-rendered, staff-only) with one JSON API; versioning the template URLs adds churn with no benefit and risks breaking the server-rendered admin UI's relative form-action paths (`../approve/<id>/`). Scoping the version to the JSON endpoint only is minimal.

**Implementation scope:**
- `src/backend/apps/moderation/urls.py` — change the bulk-action path to `path("api/v1/bulk-action/", bulk_moderation_action, name="bulk_action")`. No other routes touched.
- No change to `config/urls.py` (the `path("moderation/", include(...))` mount stays).
- No change to `api_bulk.py` (the `MAX_BULK_ACTIONS` cap from ext003b is compatible — it returns 400 for oversized batches regardless of URL).

**Tests / verification:**
- `TestBulkModerationActionView` in `test_priority_service.py` — `bulk_url = reverse("moderation:bulk_action")` resolves to the **new** path automatically (name preserved); confirm via `assert self.bulk_url == "/moderation/api/v1/bulk-action/"`.
- Add `test_unknown_version_404` — POST to `/moderation/api/v2/bulk-action/` → 404 (version-mismatch contract).
- Run `django check` + URL resolve.

**Acceptance criteria:**
- `moderation/urls.py` registers bulk-action at `api/v1/bulk-action/` (name `"bulk_action"` preserved).
- `reverse("moderation:bulk_action")` == `/moderation/api/v1/bulk-action/`.
- Unknown version path → 404 (not 500).
- Template moderation routes (`/moderation/queue/`, `/moderation/approve/<id>/`, etc.) unchanged.
- `test_requires_staff_forbidden` / `test_bulk_approve` etc. still resolve and pass.
- `ruff check`/`basedpyright` clean; `django check` passes.

**Run command:**
```powershell
$dc run --rm -e PYTEST_OPTS="-k 'TestBulkModerationActionView'" test
```

<!-- TASK_END: ext006b_api_versioning -->

---

## 6. Cross-Cutting Risks & Gates

### 6.1 The EXT-001 Prerequisite Gate (rollout-critical)
**The single hard cross-block dependency.** `ext001a` (except-narrowing **with the `deep_translator.exceptions` family**) **must** ship before `ext001b` (retry/backoff) and `ext001c` (httpx). Rationale (verified): `deep_translator.exceptions.{TooManyRequests, RequestError, TranslationNotFound}` subclass `Exception` only — not `requests.exceptions.RequestException`. A narrowing to `(TimeoutError, RequestException)` alone would **exclude** them, letting Google 429 / non-200 / no-element propagate into `translate_all_languages`' `asyncio.gather` and crash ad creation on the first throttling event. `ext001a` mitigates by including the family explicitly; `ext001b` then layers correct retry/fallback classification on top. **Rollout rule:** if `ext001a` and `ext001b` ship in the same PR, the narrowing diff must be reviewed **first**; if split, `ext001a` merges (and ideally deploys) before `ext001b`'s PR opens.

### 6.2 Research Gate — EXT-001c httpx (Approach A/B/C/D, §6.3)
`httpx` is not a current dependency. The migration approach is ambiguous and high-risk. **Block `ext001c` is blocked on a Researcher decision** (recorded in `.ai/research/ext-001c-httpx-decision.md`) choosing between: (A) official Google Cloud Translation API via httpx [paid, needs secret]; (B) httpx reimplementation of the web-scrape [fragile]; (C) httpx-only timeout wrapper [insufficient]; (D) `concurrent.futures` thread-kill [latency-bound only]. The Researcher must confirm which, considering the project's no-paid-API / minimal-secret-churn stance. `ext001c` also inherits the `ext001a`+`ext001b` gate (staged after retry+semaphore per audit).

### 6.3 Validator Gate — EXT-006b Consumer Check
Before moving the moderation JSON URL, a Validator must re-confirm no consumer exists (template form-posts use per-ad paths, not the bulk API). If a consumer is discovered, the URL move is deferred and coordinated. Baseline verification: 0 matches for `bulk-action`/`bulk_action`/`moderation:` in `*.html`/`*.js`/`*.ts`/`*.tsx`; the only reference is `reverse("moderation:bulk_action")` in `test_priority_service.py`.

### 6.4 Dual-Config Consistency (EXT-003 / EXT-004)
`nginx.conf` and `nginx.dev.conf` are **two independent files** (not symlinked). Every nginx change in `ext003a` and `ext004` must be applied to **both**, and they share file ownership → **sequential** (not parallel). Recommend combining `ext003a`+`ext004` in one PR so one `nginx -t` pass validates both across both files.

### 6.5 Single Implementor → effective sequential execution
With one Implementor, all parallel-safe blocks execute one-at-a-time. Only the **documented dependency gates** (`ext001a → ext001b → ext001c`, `ext003a → ext004` same-file sequencing, `ext001c` research gate, `ext006b` validator gate) constrain ordering — every other pair is interchangeable.

### 6.6 i18n DoD (project rule #16)
No finding introduces new user-visible strings except possibly EXT-006a's error messages (`"Authentication required"` / `"Staff access required"`). These are JSON API error bodies (machine-readable, not wrapped in `{% trans %}` per project convention for API JSON). If the project convention wraps API JSON errors, run `makemessages -l ru -l bs -l en` + `compilemessages` after EXT-006a and confirm `test_i18n_completeness.py` passes. EXT-001/002/003/004/005/006b introduce **no** user-visible strings.

### 6.7 Backward Compatibility Summary
| Block | Compat impact | Mitigation |
|-------|---------------|------------|
| ext001a | Programming errors now propagate (was swallowed) | Intentional (surface bugs); only translation-family errors still fall back |
| ext001b | None (retry/fallback is additive) | N/A |
| ext001c | Depends on Research decision (B/C replaces deep_translator) | Staged; validated against ext001a/ex001b narrowing |
| ext002 | None (gated default-OFF) | `IMMEDIATE_ALERTS_ENABLED` stays false until explicitly enabled |
| ext003a | Abusive floods get 429 | Legit clients within burst pass |
| ext003b | Oversized (>100) batches → 400 | No legit consumer exceeds 100 |
| ext004 | None (additive headers) | HSTS re-added where dropped; Referrer/Permissions-Policy new |
| ext005 | Duplicate DRAFTs suppressed on re-delivery | Fail-open on Redis outage |
| ext006a | Unauth 403→401 | Standard RFC 7235; clients seeing denial still see denial |
| ext006b | URL `/moderation/bulk-action/` → `/moderation/api/v1/bulk-action/` | No consumer verified; name-based `reverse()` preserved |

---

## 7. Verification Commands (reference)

| Gate | Command |
|------|---------|
| Fast test gate | `$dc run --rm --env PYTEST_SKIP_MARKERS=seed test` |
| Fresh schema (after any migration) | `$dc run --rm test` with `--create-db` |
| Lint | `uv run ruff check <paths>` |
| Format check | `uv run ruff format --check <paths>` |
| Typecheck | `uv run basedpyright <paths>` |
| i18n completeness | `uv run pytest src/backend/apps/core/tests/test_i18n_completeness.py` |
| nginx config valid | `docker run --rm -v ${PWD}/docker/nginx/nginx.conf:/etc/nginx/nginx.conf:ro nginx:1.27-alpine nginx -t` |
| Single test (any block) | `$dc run --rm -e PYTEST_OPTS="-k <pattern>" test` |
