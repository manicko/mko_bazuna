---
phase: "09"
phase_name: "External Integrations & API"
date: "2026-09-28"
auditor: "Executor (subagent)"
validator: "Validator (subagent), Phase 99"
mode: "problems-only"
id_prefix: "API"
report_status: "validated"
severity_taxonomy: ".kilo/commands/audit/phases/09-audit-external-api.md#severity-taxonomy"
---

# Audit Findings — External Integrations & API (VALIDATED)

> Phase 99 validation. Every finding below carries an explicit verdict.
> **CONFIRMED** = technically correct and currently applicable, kept as filed.
> **ADJUSTED** = the defect is real but the severity, type, scope or evidence
> needed correction (the correction is stated in the Validation Note).
> **REJECTED** = the claim does not hold against the tree; replaced with a
> rejection reason.
> **MERGED** = folded into another finding or another phase's finding.
>
> This file is self-contained: the reader never needs the raw phase report or
> any source file to act on it.

## Validated Executive Summary

The phase-09 thesis is **sound and independently reproduced**. Seventeen findings
were re-derived from the tree; ten survive unchanged, seven are adjusted (two
downgrades, one split, two type reclassifications, two evidence corrections), and
none is rejected outright. The report's central
claim — that the system's risk is *fragility and unverified capability claims*
rather than leakage — holds, and the leak-adjacent posture (env-sourced
credentials, no tracked secrets, rate-limit zones keyed on the real client IP)
is genuinely good.

Two capability claims the project believes about itself are false, and both are
confirmed with a stronger evidence anchor than the auditor supplied:

- **There is no external exchange-rate feed.** The operations runbook states in
  plain language that `load_exchange_rates` "makes HTTP calls to ECB". It makes
  none. It is a three-entry hard-coded literal, and because it is run with
  `update_or_create` on the `migrate` one-shot, it **silently reverts any rate an
  operator corrects in the admin on every container start**.
- **There is no password-reset or transactional-email flow.** `send_mail` has
  exactly one call site (a fail-open support-desk notification). Yet
  `EMAIL_HOST` is a hard boot gate for the whole system, and the ops runbook
  repeats the "password-reset" rationale in four further places.

Both were flagged in the phase brief as existing features. They do not exist.
That makes API-008 and API-009 the two findings most likely to cause a wrong
operational decision, because a runbook that tells an operator to expect a live
rate feed and a working password-reset mail path is actively misleading during an
incident.

One structural correction matters for remediation: **several of the report's
line-numbered evidence anchors do not match the current tree** (VAL-003). The
*claims* mostly survive; the *citations* for API-007 and parts of API-006/API-008
point at code that does not exist. Remediation keyed to those line numbers will
land in the wrong place. Corrected anchors are given in each finding below.

## Severity Distribution — Before and After Validation

| | CRITICAL | HIGH | MEDIUM | LOW | Total |
|---|---|---|---|---|---|
| **Auditor (as filed)** | 0 | 5 | 8 | 4 | 17 |
| **After validation** | 0 | **4** | **8** | **5** | 17 |

*Two movements only: API-005 HIGH→MEDIUM, API-010 MEDIUM→LOW. No finding is
added, removed or merged.*

| Verdict | Count | IDs |
|---|---|---|
| CONFIRMED unchanged | 10 | API-001, API-002, API-003, API-004, API-006, API-013, API-014, API-015, API-016, API-017 |
| ADJUSTED | 7 | API-005 (HIGH→MEDIUM) · API-007 (split, half rejected) · API-008 (DOC-UPDATE→SPEC-DEVIATION) · API-009 (DOC-UPDATE→SPEC-DEVIATION, scope 1→5 sites) · API-010 (MEDIUM→LOW) · API-011 (evidence corrected) · API-012 (scope bounded against VAL-002) |
| REJECTED | 0 | — |
| MERGED | 0 | — |
| VAL- (new) | 6 | VAL-001 … VAL-006 |

---

## Checkpoint 1 — Auditor analysis

- **Stage:** Auditor analysis
- **Findings in scope:** 17 (HIGH 5, MEDIUM 8, LOW 4)
- **Evidence anchor:** `.ai/audit/09-external-api/findings.md` (1389 lines, raw phase report, 20 runtime checks R-01…R-20)
- **Dependencies / blockers:** none. Live third-party calls impossible (dev web+bot containers crash-loop on a placeholder `BOT_TOKEN`); all verification is read-only against the `mko-bazuna-test` project.
- **Checkpoint status:** closed

## Checkpoint 2 — Researcher verification (cross-finding analysis)

- **Stage:** Researcher verification
- **Cross-phase conflicts:** 1 (VAL-001) — API-009 and CFG-004 reach opposite conclusions about the same `EMAIL_HOST`/`EMAIL_BACKEND` pair from different angles; not contradictory, but double-owned.
- **Merge candidates:** 2 — API-008 ↔ DB-008 (adjacent, not mergeable); API-012 ↔ new VAL-002 (same root cause, one absorbs the other).
- **Merge candidates that were rejected as merges:** API-010 ↔ AUT-003 (both reflect `$host`/XFF trust, different mechanisms and different fixes — cross-referenced, not merged).
- **Checkpoint status:** closed

## Checkpoint 3 — Per-finding validation

- **Stage:** Per-finding validation
- **Decision tally:** Validated unchanged 10 · Reclassified/Adjusted 7 · Merged 0 · Rejected 0 · VAL- additions 6
- **Independent reproductions performed by the validator** (not auditor-cited):
  1. Cache-outage end-to-end: `/`, `/search/`, `/privacy/` all return **HTTP 500**; `/health/` returns 503 with `cache: fail`; both site-config getters raise; **all four** bot rate limiters raise. (API-001, API-002)
  2. Telegram 429 with `retry_after=300` through the real handler: `sleeps=[300.0, 300.0, 300.0] total=900.0s replays=3 handled=True`; a `TelegramServerError` produces `sleeps=[] replays=0 handled=False`. (API-004)
  3. Alert body built from a seller-controlled title: the raw markup reaches the wire verbatim and neither module imports an escaping helper. (API-006)
  4. Test-container bootstrap on a warm database: `Exchange rates loaded: 0 created, 3 updated` — the seed always overwrites. (API-008)
- **Checkpoint status:** closed

## Checkpoint 4 — Final consistency audit

- **Stage:** Final audit
- **Pipeline integrity:** OK. All 17 IDs preserved; no renames; no file renames; no source file modified by the validator. Six `VAL-` findings appended. All checkpoints closed.
- **Checkpoint status:** closed

---

# Findings by Severity

## HIGH (4)

### API-001: [HIGH] — A cache (Redis) outage 500s every public page — CONFIRMED

| Field | Value |
|---|---|
| **ID** | API-001 |
| **Title** | A cache (Redis) outage 500s every public page — the documented `site_config` fallback covers only the DB branch |
| **Severity** | HIGH (held) |
| **Category** | Availability / graceful degradation |
| **File(s)** | `src/backend/apps/core/services/site_config.py:27-37,56-66` · `src/backend/apps/core/utils/cache.py:60-70,104-114` · `src/backend/apps/core/context_processors.py:93,116` · `src/backend/apps/core/templatetags/telegram_tags.py:163` |
| **Type** | SPEC-DEVIATION |
| **Status** | Validated |

**Problem (verified).** In both `get_site_name()` and `get_bot_username()` the
cache read executes *before* the `try:` block, and the `try` wraps only the ORM
call. The two cache getters are bare `cache.get()` calls with no exception
handling. Both function docstrings promise a fallback "if the DB **or cache** is
unavailable" — the cache half of that contract is not implemented.

**Independent reproduction (validator, read-only, pytest against the test DB):**
the shared cache object was patched so every operation raises
`django_redis.exceptions.ConnectionInterrupted`, then:

```text
=== documented site_config fallback under cache outage ===
  get_site_name   -> ConnectionInterrupted
  get_bot_username -> ConnectionInterrupted
=== public pages under cache outage ===
  GET /          -> 500
  GET /search/   -> 500
  GET /privacy/  -> 500
=== readiness probe under cache outage ===
  GET /health/   -> 503 {"status":"not_ready","checks":{"database":"ok","cache":"fail","bot":"disabled"}}
```

**Severity judgement.** HIGH is correct and was specifically challenged. An
undeclared cache dependency is only HIGH when the failure is *total, silent and
user-visible*. All three hold: the site has **no** degraded mode, the readiness
probe correctly reports the failure but nothing behind it can serve traffic, and
the loss is complete rather than partial (site name, bot deep-link target and
header city all disappear on every page). There is a mitigating factor the
auditor under-weighted — the *fix* is genuinely small (move two statements inside
an existing `try`) — but effort is not a severity input. HIGH stands.

**Root cause.** The cache was treated as an accelerator inside an
already-fallible function, so the guard was written around the wrong call.

**Recommendation (unchanged, and it is the right shape).** Move the two cache
reads inside the existing `try`. Better: state the contract once in
`apps/core/utils/cache.py` as a `cache_get_or_none(key)` helper that swallows
`ConnectionInterrupted`/`RedisError` and returns `None`, and route **every**
request-path cached read through it. Add a regression test that patches the cache
to raise and asserts `/`, `/ads/<id>/` and `/login/issue/` still return 200.

**CWE:** CWE-400 (availability class) · **Effort** S · **Priority** P0 · **Likelihood** MEDIUM
**Related:** API-002, API-011, VAL-006

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Defect, docstring-vs-code contract violation and blast radius all reproduced end-to-end at the HTTP layer, not just at function level. The auditor's evidence was function-level only; the validator additionally proved the 500s. `CACHES` in `base.py:369-377` sets no `IGNORE_EXCEPTIONS`, so django-redis's default (`False`) applies and exceptions do propagate — the premise is sound.
> - **See also:** VAL-006 (this fix and API-008's cache fix share one contract and must land together).

---

### API-002: [HIGH] — All four bot rate limiters raise on a cache outage instead of failing open — CONFIRMED

| Field | Value |
|---|---|
| **ID** | API-002 |
| **Title** | All four bot rate limiters raise on a cache outage instead of failing open, unlike the dedup middleware |
| **Severity** | HIGH (held) |
| **Category** | Resilience / availability |
| **File(s)** | `src/telegram_bot/services/rate_limit.py:62-65,116-119,166-169,216-219` · `src/telegram_bot/middlewares/update_id_dedup.py:58-68` |
| **Type** | SPEC-DEVIATION |
| **Status** | Validated |

**Problem (verified).** All four guards in `telegram_bot/services/rate_limit.py`
(`check_login_rate_limit`, `check_contact_start_rate_limit`,
`check_support_message_rate_limit`, `check_upload_rate_limit`) wrap the
`cache.add` + `cache.incr` pair in `except ValueError` **only**. django-redis
signals an unreachable server with `django_redis.exceptions.ConnectionInterrupted`,
which inherits directly from `Exception` and is **not** a `ValueError`, so it
escapes. The sibling `UpdateIdDedupMiddleware` catches
`(ConnectionInterrupted, redis.RedisError)` and documents the intended policy:
*"a Redis outage degrades to 'no dedup' rather than dropping legitimate traffic."*

**Independent reproduction:** with the same patched cache,
`check_login_rate_limit`, `check_contact_start_rate_limit`,
`check_support_message_rate_limit` and `check_upload_rate_limit` **all raise**.
None fails open.

**Severity judgement.** HIGH is correct. The bot's login handshake, support
intake, contact greeting and photo upload all stop at once, and the guards that
should *protect* the system are exactly what the outage removes. This is a
higher-order failure than API-001's: a 500 is a visible degradation, whereas
abuse controls that fail **closed** on the guard path and **open** on the
consume path is an inversion of the intended policy, and it is silent — no log
line distinguishes "rate limited" from "cache is down".

**Root cause.** The `add`/`incr` idiom was copy-pasted across four call sites and
each copy re-derived the exception set from memory rather than from the cache
backend's contract. The fail-open policy was documented in one file and never
generalised.

**Recommendation (unchanged).** One shared private helper (`_bump_window(key,
period, limit) -> bool`) catching `(ConnectionInterrupted, redis.RedisError,
ValueError)` and returning `True` with a `logger.warning`, called by all four
guards. This also removes the four-copy duplication. Add a test per guard that
patches the cache to raise and asserts `True`.

**CWE:** CWE-703 · **Effort** S · **Priority** P0 · **Likelihood** MEDIUM
**Related:** API-001, API-003, VAL-005

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Exception hierarchy confirmed against the installed package (`ConnectionInterrupted(Exception)` — not a `ValueError` subclass), so the auditor's mechanism is exactly right. **However, the recommended "must land in the same release as API-003" sequencing is rejected — see VAL-005.**
> - **See also:** VAL-005 (the release coupling is unsound as stated).

---

### API-003: [HIGH] — The `contact_<ad_id>` deep link is unrated — CONFIRMED (fix sequencing REJECTED, see VAL-005)

| Field | Value |
|---|---|
| **ID** | API-003 |
| **Title** | The `contact_<ad_id>` deep link is unrated: any Telegram user can message any seller without limit and grow the DB unboundedly |
| **Severity** | HIGH (held) |
| **Category** | Abuse control / resource exhaustion |
| **File(s)** | `src/telegram_bot/handlers/contact.py:113-121,179-239` · `src/telegram_bot/services/rate_limit.py:73-119` · `src/backend/apps/core/services/contact.py` · `src/backend/templates/ads/detail.html` |
| **Type** | BEST-PRACTICE (held) |
| **Status** | Validated |

**Problem (verified).** `handle_contact_start` routes two very different deep
links through one handler. The `contact_us` branch is guarded by
`check_contact_start_rate_limit` (5 / 600 s). The `contact_<ad_id>` branch has
**no rate limit of any kind** — not per user, not per ad, not global. Verified by
reading the handler: the `contact_<ad_id>` path returns directly into
`handle_contact()`, which contains no limiter call. Each hit performs a DB read
(`get_seller_for_contact`), an `AnalyticsEvent` INSERT
(`record_contact_initiated`), and an **outbound Telegram `send_message` to the
seller**. The identifier space is a dense, trivially enumerable integer, and the
link is rendered on the anonymously reachable ad detail page. `AccountStateMiddleware`
*widens* access here — it admits declined/browse-only accounts when
`classify_contact_deep_link` matches, so a browse-only account can drive the loop.

**Impact.** Any Telegram account can iterate `/start contact_1 … contact_N` to
flood every seller with "New request from a buyer!" messages and inflate
`analytics_events` without bound. Three follow-on harms, all real: seller spam;
a Telegram flood-control response that lands in `retry_transient` and triggers
the API-004 amplification; and damage to the `CONTACT_INITIATED` counter the
`TrustCalculator` reads, so the attacker's spam lowers the victim's trust score.

**Root cause.** The limiter was added for the *support-desk* deep link (the one
that was actually reported as abusive) and never generalised to the sibling
branch that shares its regex block and enum.

**Recommendation (unchanged, and the two-part shape is correct).** Add a
`check_contact_forward_rate_limit(message.from_user.id)` guard to the
`contact_<ad_id>` branch mirroring the existing one (5 / 600 s per buyer), **plus
a separate, tighter per-seller cap (~20 / 3600 s) keyed on the ad owner**. The
per-seller cap is the one that actually protects sellers, because the expensive
part of the flow is the outbound message to the seller. Reuse the shared helper
from API-002 rather than adding a fifth copy of the `add`/`incr` idiom. Add a
test asserting the 6th `contact_<ad_id>` trigger from one user is refused **and
that no `send_message` is issued**.

**CWE:** CWE-799 · **Effort** S · **Priority** P0 · **Likelihood** HIGH
**Related:** API-002, API-004, API-011

> **Validation Note:**
> - **Action:** validated (defect unchanged); **the report's release-sequencing claim attached to it is rejected.**
> - **Detail:** The defect is real and HIGH. The roadmap's "This must land together with API-002, because API-002 makes the limiter fail open … and a fail-open seller-spam guard is not a guard" is a rollout-safety claim about *deploy order*, and it does not survive scrutiny. See **VAL-005** for the full refutation and the corrected ordering.
> - **See also:** VAL-005, API-002, API-004.

---

### API-004: [HIGH] — Telegram 429 backoff has no ceiling, never retries network/5xx siblings, reports failure as success — CONFIRMED (+ rollout hazard VAL-004)

| Field | Value |
|---|---|
| **ID** | API-004 |
| **Title** | Telegram 429 backoff has no ceiling (900 s for one flood response), never retries network/5xx siblings, then reports the message as handled |
| **Severity** | HIGH (held) |
| **Category** | Resilience / retry amplification |
| **File(s)** | `src/telegram_bot/retry.py:32-33,43-91` · `src/telegram_bot/main.py:79-88` |
| **Type** | SPEC-DEVIATION |
| **Status** | Validated |

**Three defects in one 40-line handler — all three verified.**

**(1) No ceiling on the mandated wait.** `delay = float(exc.retry_after)` is used
verbatim and slept on every one of `_MAX_RETRIES = 3` attempts.

**(2) The declared transient set is unreachable.** `main.py` registers the
handler as `ExceptionTypeFilter(TelegramRetryAfter)` and the handler body opens
with `if not isinstance(exc, TelegramRetryAfter): return False` — so
`TelegramNetworkError` and `TelegramServerError`, both listed in
`_TRANSIENT_EXCEPTIONS` and both handled *inside* the replay loop, can never
*enter* the handler. Only 429 is ever retried.

**(3) Terminal failure is reported as success.** After exhausting retries the
handler returns `True`, which aiogram's `ErrorsMiddleware` reads as "handled",
so the exception is swallowed and nothing above it logs the drop.

**Independent reproduction (validator):**

```text
=== Telegram 429 retry_after=300 through retry_transient ===
  sleeps=[300.0, 300.0, 300.0] total=900.0s attempts_replayed=3
  _MAX_RETRIES=3  handler_returned(handled)=True
=== TelegramServerError (declared in _TRANSIENT_EXCEPTIONS) ===
  sleeps=[] replays=0 handled=False
```

**Impact.** (1) One flood response pins an update task for 15 minutes;
`dp.run_polling` is called with no arguments, so aiogram's defaults apply
(`handle_as_tasks=True`, `tasks_concurrency_limit=None`) and nothing bounds how
many tasks sit in that state — N concurrent 429s become 3N replayed outbound
calls, the opposite of what flood control asks for. (2) A Telegram 5xx window
loses every seller-facing message with no replay. (3) The drop is invisible to
the generic handler, so there is no line anywhere that says "N messages were
dropped".

**Root cause.** The handler was written for one exception type; its signature
locks that in while the body was written as if it handled a family. Nothing
asserts `_TRANSIENT_EXCEPTIONS` is reachable, and returning `True` after
exhaustion was chosen to suppress a re-raise that was never wanted.

**Recommendation (unchanged).** (1) `delay = min(float(exc.retry_after or 0),
_MAX_BACKOFF_SECONDS)` with a small ceiling, and bound the loop by *total
budget* rather than attempt count. (2) Register
`ExceptionTypeFilter(_TRANSIENT_EXCEPTIONS)` and delete the now-redundant
`isinstance` guard so the body matches its own constant. (3) Return `False` on
exhaustion so `ErrorsMiddleware` re-raises, plus a counter so "messages dropped"
is a signal.

**CWE:** CWE-770 · **Effort** S · **Priority** P0 · **Likelihood** MEDIUM
**Related:** API-003, API-013, **VAL-004**

> **Validation Note:**
> - **Action:** validated (unchanged) + **new rollout hazard VAL-004 raised**
> - **Detail on the return-contract question (explicitly requested):** `retry_transient` has **exactly one production caller** — the Dispatcher `errors` observer, which only consumes the boolean. There is no application code that branches on it. **One in-repo dependency exists and it asserts the wrong contract:** `src/telegram_bot/tests/test_error_handler.py:123-125` (`test_error_handler_marks_handled_after_exhausting_bound`) does `result = await handler(...)` then `assert result is True`. Changing the contract to `False` will fail that test. Per the project's "production code is king" rule, the **test** is what must change — it currently encodes the defect as intended behaviour, which is itself a finding about test quality. `test_error_handler_returns_false_for_unrelated_error` (line 128) is unaffected. The test file's `_make_dispatcher()` helper also hard-codes `ExceptionTypeFilter(TelegramRetryAfter)`, so recommendation (2) requires updating the helper to `_TRANSIENT_EXCEPTIONS` in the same change.
> - **See also:** VAL-004.

---

## MEDIUM (8)

### API-005: [MEDIUM] — `/media/` has no nginx rate-limit zone — ADJUSTED (HIGH → MEDIUM)

| Field | Value |
|---|---|
| **ID** | API-005 |
| **Title** | `/media/` — the only public path that runs a per-request DB access check — has no nginx rate-limit zone |
| **Severity** | **MEDIUM** (downgraded from HIGH) · **Priority** P1 (from P0) |
| **Category** | Abuse control / capacity |
| **File(s)** | `docker/nginx/nginx.conf:80-87,170-178` · `docker/nginx/nginx.dev.conf` · `src/backend/apps/ads/urls.py:25` · `src/backend/apps/ads/views/listings.py:155-215` · `src/backend/apps/ads/views/listings.py:229` |
| **Type** | BEST-PRACTICE |
| **Status** | Validated (reclassified) |

**Problem (verified).** Every public path in the production proxy declares a
`limit_req` zone **except `location /media/`**. Because nginx resolves the
*longest* matching prefix, a `/media/…` request never falls through to
`location /`, so the catch-all `browse_limit` zone does not cover it — the zone
is simply absent. (`/static/` is also unrated but is whitenoise with no DB work,
so that omission is harmless — correctly noted by the auditor.)

**Strengthening evidence the auditor missed.** The gap is not only at the proxy.
The Django view behind it has **no application-level limiter either** — and its
sibling on the same module, `listings`, *does* have one
(`check_deep_link_render_rate_limit`, `listings.py:229`). So `/media/` is the
only anonymous, DB-backed path with neither an app-level nor a proxy-level
control. Additionally, `media_gate` runs the *same* `AdImage.objects.filter(key_q)`
query **twice** per valid request (`listings.py:182` and `listings.py:200`) — the
first result is not reused — so a valid key costs 2 identical indexed
`EXISTS` queries, and with `CONN_MAX_AGE=0` a new DB connection per request.

**Why the grade was lowered to MEDIUM.** The mechanism is fully confirmed, but
the *harm* is a capacity concern, not a demonstrated loss of a stated guarantee:
an invalid key costs exactly one `EXISTS`; a valid key costs two. Unlike
API-001/002/003/004 — each of which removes a *guarantee the system claims to
provide* — this removes a *defence-in-depth layer*. There is no evidence of a
scraper, no availability loss, and the mitigation is a single nginx line any
operator can add in under a minute. It is one incident away from HIGH, and if a
scraper is ever observed it must be re-graded immediately.

**Recommendation (unchanged, still correct).** Add a **tighter, separate** zone
to `location /media/` in both configs, since the point is to protect the DB
rather than the user: `limit_req_zone $binary_remote_addr zone=media_limit:10m
rate=30r/s;` with `burst=60 nodelay`. Keep `$binary_remote_addr` — do **not**
switch to `$proxy_add_x_forwarded_for`; the XFF-first form is bypassable
(phase 04 `AUT-003`). Then add the same application-level limiter
`listings.py:229` uses, and assert the zone assignment in a test that parses the
shipped config so the next `location` block added cannot silently miss one.
De-duplicating the `AdImage` query is a cheap bonus, not a requirement.

**CWE:** CWE-770 · **Effort** S · **Likelihood** MEDIUM
**Related:** API-014

> **Validation Note:**
> - **Action:** reclassified — severity HIGH → **MEDIUM**, priority P0 → P1
> - **Detail:** Defect CONFIRMED with additional evidence (no app-level limiter, duplicated query). The grade was lowered because HIGH in this project's taxonomy is reserved for losses of a stated guarantee or a fail-closed control; this is a missing capacity control on an endpoint whose worst case is DB pressure, not a breach, and it is a one-line fix. The substance of the finding is unchanged and it should still ship early.
> - **See also:** API-014 (same config, same owner, same wave).

---

### API-006: [MEDIUM] — Telegram alert messages are built with `parse_mode="HTML"` from unescaped seller text — CONFIRMED (impact sharpened)

| Field | Value |
|---|---|
| **ID** | API-006 |
| **Title** | Telegram alert messages are built with `parse_mode="HTML"` from unescaped seller text, so a title containing `<` silently kills that seller's alerts |
| **Severity** | MEDIUM (held) |
| **Category** | Correctness / data integrity |
| **File(s)** | `src/backend/apps/search/services/immediate_alerts.py:143-149,207,232` · `src/backend/apps/search/management/commands/send_alerts.py:188,207,237` · `src/backend/apps/ads/models.py` (`title`/`title_bs`/`title_en`) |
| **Type** | BEST-PRACTICE |
| **Status** | Validated |

**Problem (verified).** Both alert builders interpolate seller-authored text
straight into an HTML-parse-mode message. `build_alert_message` does
`f"<b>{title}</b>"`, `f"📍 {city_name}"`, `f'<a href="{...}">{label}</a>'`;
`_format_digest` does `f"• {ad.get_title(locale)[:50]}"`. Neither module
imports an escaping helper. Both send with `parse_mode="HTML"`.

**Independent reproduction (validator):** built the message body from a seller
title of `Bicikl <b>novi</b> & "brz" <a href="http://evil.example">x</a>`:

```text
| <b>Bicikl <b>novi</b> & "brz" <a href="http://evil.example">x</a></b>
| 📍 Podgorica <b>glavni</b> grad
| 💰 100 EUR
| <a href="https://site.example/ads/1/">Просмотреть объявление</a>
raw seller markup present: True
'html' module imported by immediate_alerts: False
```

**Impact — sharpened by validation.** Telegram rejects a message whose entities
cannot be parsed, and both modules classify `TelegramBadRequest` as a
**permanent** failure logged at WARNING with no retry. The practical outcome is
worse than "one seller loses their alerts":

- The **`contact_us`/daily digest path is per-user, not per-seller.** One seller's
  bad title kills the *entire* digest for every recipient whose batch included
  that ad — up to 10 ads per user per message. It is a cross-seller blast radius.
- `SavedSearchNotification` rows are written **before** the send, so the system
  reports the alert as delivered. Neither the seller nor the buyers see a symptom.
- The mirror risk is confirmed: a title containing `<a href="…">` becomes a
  clickable link injected by a seller into every subscriber's chat.

**Root cause.** The messages are assembled as HTML strings rather than sent as
plain text, and nothing in the chain treats seller text as untrusted. The
project's own templatetags and Django templates escape by default; the Telegram
path bypassed that discipline entirely.

**Recommendation — pick ONE shape and apply it to both modules.**
(a) Drop `parse_mode="HTML"` and send plain text (the bold/anchor formatting is
cosmetic; the contact handler already does exactly this). **This is the
preferred shape**: it removes the entire class of defect and needs no per-field
auditing. (b) Keep HTML and escape every interpolation with
`django.utils.html.escape`, using unescaped values only for structural tags.
Add a test that builds a message from a title of `Bike <b>new</b> & fast` and
asserts the seller's markup does not survive.

**CWE:** CWE-116 · **Effort** S · **Priority** P1 · **Likelihood** MEDIUM
**Related:** API-013, API-017

> **Validation Note:**
> - **Action:** validated (unchanged); evidence corrected, impact sharpened
> - **Detail:** Absence of escaping independently reproduced. Two corrections: (1) the digest blast radius is **per recipient batch**, not per seller — the auditor understated it; (2) the report cited a `_format_digest` interpolation of `ad.get_title(locale)[:50]` without noting the 50-char truncation, which is why a full raw-markup substring check on the digest returns `False` while the unescaped `<b>` is still present in the truncated prefix. Neither changes the verdict. **The daily digest is live**: `send_alerts` is in `DAILY_COMMANDS` (`scheduler.py:70-73`), firing at 08:00 UTC. The publish-time path is dormant by default (`IMMEDIATE_ALERTS_ENABLED=false` in all three `.env.*.example` files).
> - **See also:** API-013, API-017.

---

### API-007: [MEDIUM] — A failed translation is indistinguishable from a real one — ADJUSTED (split; part (b) REJECTED)

| Field | Value |
|---|---|
| **ID** | API-007 |
| **Title** | A failed translation is indistinguishable from a real one, so `backfill_translations` permanently writes the untranslated source into the English/Bosnian columns |
| **Severity** | MEDIUM (held, on the surviving half) |
| **Category** | Correctness / cost control |
| **File(s)** | `src/backend/apps/ads/management/commands/backfill_translations.py:25-39,62-66,79-98` · `src/backend/apps/core/services/translation.py:169-250` · `src/backend/apps/ads/services/submission.py:194-204` |
| **Type** | SPEC-DEVIATION |
| **Status** | Validated (scope corrected) |

**Part (a) — CONFIRMED, and it is the whole of the real finding.**
`translate_text` returns the unmodified source on **every** failure path (open
breaker, empty body, non-2xx, invalid key, timeout). The caller cannot tell that
from a translation. `_translate_for_backfill` returns that value verbatim and
`handle()` stores it into `title_en` / `title_bs` unconditionally:

```python
translated_title = _translate_for_backfill(ad.title, locale)   # == ad.title on failure
updates[title_field] = translated_title
```

The command's "is a translation missing?" test is **column nullability**
(`Ad.objects.filter(title_en__isnull=True) | Ad.objects.filter(Q(title_bs__isnull=True))`),
which the fallback quietly satisfies. Once the Russian source is written into
the English column, the row no longer matches the filter and the backfill will
**never revisit it**. The damage is permanent and the command reports success.
The missing marker is the defect; the nullability-derived selection query is why
it is unrecoverable.

**Part (b) — REJECTED.** The claim that the backfill is "bounded only by the
1800 s `SCHEDULER_COMMAND_TIMEOUT`", that it has "no `--limit`, no batching, no
progress logging", that `_translate_for_backfill` is "called up to four times per
ad with a 0.5 s client timeout", and that it uses `asyncio.run(run_backfill(qs))`
is **not true of the current code** and must not be actioned:

| Report claim | Actual code |
|---|---|
| `asyncio.run(run_backfill(qs))` | No `asyncio.run` anywhere; the command is synchronous. |
| "no `--limit`, no batching" | `--batch-size` exists (default 100) and drives `iterator(chunk_size=…)`. |
| "no progress logging" | Per-ad `logger.error` on save failure plus a final summary line exist. |
| Cited at `:97-102,163-180,221-231` | The file is **124 lines**; those offsets do not exist. |
| "runs inside `migrate_locked` … on every boot" | `migrate_locked` includes it **only** when `RUN_TRANSLATION_BACKFILL=true`; the bootstrap is documented as env-gated. |
| `submit_ad` "assigns the return value to `title_bs`/`title_en` unconditionally" | `submission.py:194-202` assigns **only if** `input.title_bs` / `input.title_en` is truthy. The quoted evidence does not exist. |

**What survives on the "is it bounded" question.** The command *is* still bounded
only by wall clock when it does run (up to 4 translation calls per ad × a 0.5 s
client timeout × 2 attempts, with no work-based limit), and `migrate_locked`
would time it out at `SCHEDULER_COMMAND_TIMEOUT` — but this is now a
**low-value, rarely-triggered, opt-in** concern, not a deploy-blocking one. Fold
`--limit` into the fix; do not treat it as a separate P1 item.

**Root cause.** The degradation path returns a *value* where the caller needs a
*status*. `translate_text` has no way to say "this is the original", so the
"is a translation missing?" query is derived from field nullability — which the
fallback satisfies.

**Recommendation.** Make the status explicit rather than inferred. **Minimal
(and sufficient for the confirmed defect):** have `_translate_for_backfill`
compare the result to the source; on equality leave the column `NULL` and count
the row into a `fallback` total that the summary line and a `logger.warning`
both report — so a partially-degraded run is visible *and re-runnable*.
**Better:** return a result object (or a bool out-param) from `translate_text` so
callers can distinguish the two, and record a `translation_failed_at` timestamp
so the backfill can target retries (a migration, and the only schema change
proposed anywhere in this phase). While there, add `--limit`.

**CWE:** CWE-703 · **Effort** S (minimal) / M (status object + column) · **Priority** P1 · **Likelihood** MEDIUM
**Related:** API-017

> **Validation Note:**
> - **Action:** **adjusted (split)** — half (a) confirmed unchanged; half (b) rejected on evidence
> - **Detail:** The direction of the finding — "the degradation contract is right but unmarked" — is correct and is the whole problem. The evidence for the secondary claim does not match the tree: the file is 124 lines, the cited offsets are past its end, the command is synchronous with a `--batch-size` flag, and it is env-gated out of the default boot. See **VAL-003**. The `submit_ad` sub-claim is separately refuted (`submission.py:194-202`), which narrows the blast radius to the backfill — but the backfill is the *worse* of the two paths because it is unrecoverable.
> - **See also:** VAL-003, API-017, API-008.

---

### API-008: [MEDIUM] — `load_exchange_rates` reverts operator-edited rates on every boot, and no external rate feed exists — CONFIRMED + RECLASSIFIED (DOC-UPDATE → SPEC-DEVIATION)

| Field | Value |
|---|---|
| **ID** | API-008 |
| **Title** | `load_exchange_rates` reverts operator-edited rates on every container start, and no external rate feed exists at all |
| **Severity** | MEDIUM (held) |
| **Category** | Data integrity / spec deviation |
| **File(s)** | `src/backend/apps/currencies/management/commands/load_exchange_rates.py:27-35,50-59` · `src/backend/apps/currencies/services/price_normalizer.py:110-121` · `src/backend/apps/core/utils/migrate_locked.py:52-60` · `docs/ops/migration-workflow.md:353-354` |
| **Type** | **SPEC-DEVIATION** (was DOC-UPDATE) |
| **Status** | Validated (reclassified) |

**This finding confirms a false claim in the phase brief.** The brief asserted an
external exchange-rate feed exists. It does not. Two independent confirmations:

1. **Code:** `INITIAL_RATES` is a three-entry literal `EUR 1.0 / BAM 0.512 /
   RSD 0.0105` with `EFFECTIVE_DATE = 2026-08-22` and `SOURCE = "manual_seed"`.
   There is no HTTP client, no scheduler task and no network call anywhere under
   `apps/currencies`. The model docstring itself says the table "is designed to
   **later** accept automated rate updates from an official source (e.g. ECB)".
2. **Docs:** the operations runbook asserts the opposite in plain language —
   `docs/ops/migration-workflow.md:353-354`: *"…`load_cities` reads
   `cities.json`; **`load_exchange_rates` makes HTTP calls to ECB.** These do not
   belong in migrations…"*. This is the *reason the command exists as a separate
   one-shot* — a rationale built entirely on a capability that was never
   implemented.

**Part (b) — the seed overwrites operator edits on every boot (CONFIRMED).**
`load_exchange_rates` is step three of `migrate_locked._build_steps()`, which
runs unconditionally on **every** `docker compose up` and every deploy, under
`advisory_lock(AdvisoryLockId.MIGRATE)`. It uses
`update_or_create(currency=code, defaults={...})` matched on the unique
`currency` field, so an existing row is **always** rewritten — an operator's
correction is reverted with no warning. The seed also does **not** re-run
`recompute_normalized_prices`, so the rate table and the derived
`price_normalized_eur` column drift apart.

**Independent runtime confirmation:** the validator's own test-container
bootstrap printed, on a warm database:

```text
Updated EUR: rate_to_eur=1.0
Updated BAM: rate_to_eur=0.512
Updated RSD: rate_to_eur=0.0105
Exchange rates loaded: 0 created, 3 updated
```

**Cache invalidation (CONFIRMED).** `PriceNormalizer.invalidate_rate_cache()` is
implemented and correct — and has **zero call sites** anywhere in `src/`
(a repo-wide search for the symbol returns exactly one hit: its own definition;
the only other occurrence is a prior audit document). So the 5-minute shared
rate cache serves the pre-boot value until it expires on its own, and there is
no path that clears it when a rate is edited in the admin.

**Root cause.** Idempotence was implemented as *"make the row look like the
constant"* rather than *"create it if absent"*. `update_or_create` is idempotent
for the *seed* value — precisely the wrong property for a value operators are
expected to be able to correct.

**Impact, stated precisely.** This is a **silent, recurring, operator-facing
data loss**, not a cosmetic doc drift: an operator who corrects a drifted rate
in the Django admin gets it reverted at the next deploy, with no log line and no
record of the previous value. Because price normalisation feeds every
cross-currency filter and sort, an operator who believes a correction took
effect is reading and serving prices computed from a rate they did not choose.
The second, larger impact is informational: **any sizing, egress-budget or
failure-mode analysis that assumes a live rate feed is wrong in both
directions** — there is no egress to budget and no upstream to fail.

**Recommendation — separate the two jobs.** (1) Treat the constant as a
*bootstrap default*: switch to `get_or_create(currency=code, defaults={...})` so
an existing row is never rewritten, and log the rate in use together with
whether it came from the seed or a prior edit. (2) Wire
`invalidate_rate_cache()` into the rate-change path — it is already written and
already correct; it has simply never been called. (3) Resolve the documentation
either way: **correct `docs/ops/migration-workflow.md:353-354`**, which is the
line that misleads an operator, and correct the aspirational model docstring to
say so; *or*, if a live feed is genuinely wanted, implement it (`--remote`
against ECB, writing `source`/`effective_date` plus a history row) and update the
docs to describe it. Option (1)+(2)+doc-correction is the small, correct fix.
The "make the rate read-only in the admin" alternative the report offers is
worth recording as the *other* coherent reading, but it is a product decision,
not a code fix.

**CWE:** CWE-665 · **Effort** S (doc + `get_or_create` + one call) / L (remote feed) · **Priority** P1 · **Likelihood** HIGH
**Related:** API-017, **VAL-006**

> **Validation Note:**
> - **Action:** **reclassified** DOC-UPDATE → **SPEC-DEVIATION**; evidence strengthened
> - **Detail:** Per §5's dead-code cross-reference rule: the spec/README/config do **not** reference a rate feed as a shipped feature — `spec-index.md` describes only "Current exchange rates live in `exchange_rates`" with no source claim. The false claim lives in the **ops runbook** and in the **settings comment** that motivates the command, which is a code-vs-documentation contradiction, not dead code. Therefore this is a spec deviation, not a doc refresh. The auditor found the aspiration in a model docstring; validation found the stronger, operator-facing instance in `migration-workflow.md`, which should be the primary doc fix.
> - **See also:** **VAL-001** (boundary with DB-008), **VAL-006** (shared-cache contract with API-001).

---

### API-009: [MEDIUM] — Mandatory `EMAIL_HOST` justified by flows that do not exist — CONFIRMED + RECLASSIFIED (DOC-UPDATE → SPEC-DEVIATION)

| Field | Value |
|---|---|
| **ID** | API-009 |
| **Title** | Mandatory `EMAIL_HOST` in production is justified by flows that do not exist; an optional, fail-open integration can block the whole web tier from booting |
| **Severity** | MEDIUM (held) |
| **Category** | Availability / spec deviation |
| **File(s)** | `src/backend/config/settings/prod.py:198-208` · `src/telegram_bot/services/support_delivery_email.py:39,99-104` · `src/backend/apps/core/management/commands/create_admin_user.py:116` · `docs/ops/docker-deployment.md:355,402,429` · `docs/ops/rollback.md:218` |
| **Type** | **SPEC-DEVIATION** (was DOC-UPDATE) |
| **Status** | Validated (reclassified, scope widened) |

**This finding confirms a second false claim in the phase brief.** The brief
cited `prod.py:198-199`'s "password resets" justification. Verified against the
tree:

- `send_mail` has exactly **one** call site in the whole codebase — the bot's
  support-desk notification to the admin inbox.
- `set_password` has exactly **one** call site — the initial superuser creation
  in `create_admin_user.py:116`. It writes a local password; it sends nothing.
- There is **no** password-reset view, URL, template, `token_generator`,
  `PasswordResetView` or `PasswordResetForm` anywhere in `src/`.
- There is no e-mail alert path (alerts are Telegram, both the instant fan-out
  and the daily digest) and no e-mail seller confirmation (publishing is a
  Telegram reply).
- The single real e-mail consumer is explicitly **fail-open**:
  `deliver_support_ticket_email` wraps the send in `except Exception` and logs
  `"Support email delivery failed (continuing)"`.

**Scope widened by validation — the fiction is repeated in five places, not one.**
The auditor found the settings comment. A repo-wide search for password-reset
language found four further doc sites that repeat the same non-existent flow as
though it were operational:

| Site | Claim |
|---|---|
| `prod.py:198-199` | "transactional emails (**password resets**, alert notifications, seller confirmations) must be deliverable" |
| `docker-deployment.md:355` | "all signed tokens (sessions, CSRF, **password-reset**) are invalidated" |
| `docker-deployment.md:402` | "users must re-authenticate and **password-reset links** expire" |
| `docker-deployment.md:429` | "preventing session/CSRF/**password-reset** token forgery" |
| `rollback.md:218` | "All signed tokens (sessions, CSRF, **password-reset**) become valid again for the old key" |

The two `docker-deployment.md` rotation entries are the most operationally
consequential: a compromise-response runbook tells the operator that rotating
`DJANGO_SECRET_KEY` will expire password-reset links. No such links exist.

**Impact.** `ImproperlyConfigured` at settings import means web, bot, scheduler
and every one-shot container fail to start. A *fail-open, best-effort,
single-purpose* integration has therefore been made a **hard boot gate for the
entire system**, justified by a rationale the codebase does not support. A
staging or DR host that can serve the site perfectly well without SMTP cannot
boot. And the legitimate operational reason to demand SMTP (compliance? a
support SLA?) is invisible to whoever writes the next runbook, because the
stated reason is fictional.

**Root cause.** The guard was authored from a feature roadmap rather than from
the flows present in the tree, and the fail-open behaviour of the one real
consumer was not read before making the dependency mandatory.

**Recommendation.** Fix the *reason* at all five sites and make the guard match
the actual blast radius. Two coherent options:
**(a)** keep it mandatory but justify it correctly — "the support-desk
notification is the only transactional e-mail; without it seller escalations are
silently lost" — and state that loudly in the deployment runbook; or
**(b)** demote it to a `logger.warning` at settings import so the site boots and
only the support-desk e-mail degrades, which is what the code already does.

**Given the delivery path already fails open, (b) is the option that matches the
code's own behaviour.** Option (a) is a defensible product decision — but then
the reason must be the real one, in all five places.

**CWE:** CWE-703 · **Effort** S · **Priority** P2 · **Likelihood** MEDIUM
**Related:** API-012, **VAL-001**

> **Validation Note:**
> - **Action:** **reclassified** DOC-UPDATE → **SPEC-DEVIATION**; scope widened from 1 site to 5
> - **Detail:** Not a dead-code finding. Per §5's cross-reference rule the spec, README, models and config templates do **not** reference password reset anywhere — so there is no "missing integration to build", only a **false justification embedded in shipped code and in the ops runbook**. Code must change (the comment) or the policy must change (the guard), which is a spec deviation, not a doc refresh. **Scope correction:** the auditor's recommendation ("fix the comment") is under-scoped — correcting only `prod.py:198-199` leaves four runbook statements asserting a feature that does not exist, two of them in the compromise-response procedure.
> - **See also:** **VAL-001** (boundary with phase 02 `CFG-004` — do not double-file).

---

### API-010: [LOW] — The nginx :80 catch-all redirects to `https://$host$request_uri` — ADJUSTED (MEDIUM → LOW)

| Field | Value |
|---|---|
| **ID** | API-010 |
| **Title** | The nginx :80 catch-all redirects to `https://$host$request_uri`, so the redirect target is client-supplied |
| **Severity** | **LOW** (downgraded from MEDIUM) · **Priority** P2 (from P1) |
| **Category** | Security (hardening) |
| **File(s)** | `docker/nginx/nginx.conf:31-35` · `docker/nginx/nginx.dev.conf:34-38` |
| **Type** | BEST-PRACTICE |
| **Status** | Validated (reclassified) |

**Problem (verified).** The only server block on the plaintext listener is a bare
`listen 80;` with **no `server_name` directive and no `default_server` flag**, and
its sole job is `return 301 https://$host$request_uri;`. With no `server_name`
configured, nginx has nothing to substitute and `$host` resolves to the client's
`Host` header verbatim. The TLS block *does* declare `server_name _;`, so the
asymmetry is specific to the :80 listener.

**Why the grade was lowered to LOW.** The auditor framed this as an open-redirect
phishing primitive "served from the project's own domain". That framing does not
survive analysis of the actual mechanism: **a browser derives the `Host` header
from the host in the URL it was asked to load.** For the response to redirect to
`attacker.example`, the victim must have already requested `attacker.example` —
in which case the request never reached this nginx. The reflected value is, by
construction, the same value the client used to address the server, so no
attacker-supplied input is introduced. The remaining exposure is to non-browser
HTTP clients and to misconfigured clients behind a preserving proxy, where the
consequence is a redirect to a host the caller already named. The auditor's own
impact paragraph already concedes the practical bounds: the victim sees the
attacker's host in the address bar, there is no response-body reflection, the
access log format does not include `$host`, and CSP/HSTS are on the :443 block
only.

This is a genuine hardening gap and a real misconfiguration trap (an operator who
adds a second vhost to this file gets surprising behaviour), but it is not a
MEDIUM security finding. The fix is still worth doing.

**Recommendation (unchanged, still correct).** Stop reflecting the client-supplied
host. In production, give the :80 block an explicit `server_name <site-domain>;`
and add a second `listen 80 default_server;` block that `return 444;` (nginx
closes the connection with no response at all), keeping
`return 301 https://$host$request_uri;` only inside the named block. If a single
block must be kept for the Docker/dev case, use `$server_name` instead of `$host`
— that resolves to the configured name rather than the header, and fails closed
when the operator forgets to set it. **Rollout note:** this is the only change in
the phase that can break a working deployment, because it requires the operator
to set a real `server_name`. Gate it on the domain/TLS work in the deployment
runbook and verify with `nginx -t` before rolling.

**CWE:** CWE-601 (as-filed; see note) · **Effort** S · **Likelihood** LOW
**Related:** API-014

> **Validation Note:**
> - **Action:** reclassified — severity MEDIUM → **LOW**, priority P1 → P2
> - **Detail:** The code fact is CONFIRMED exactly as filed. The *impact model* is not: the reflected value is the same value the client used to address the server, so a browser cannot be induced to follow a 301 from this origin to an attacker origin. The CWE-601 label is retained for traceability, but this is a hardening/defence-in-depth item, not an open redirect with a phishing primitive. Do not let the LOW grade suppress the fix — the missing `server_name` remains a real misconfiguration trap.
> - **See also:** API-014, AUT-003 (phase 04 — adjacent `$host`/XFF trust, different mechanism, **not** a merge).

---

### API-011: [MEDIUM] — `BOT_TOKEN` distribution is broader than the bot tier — ADJUSTED (evidence corrected)

| Field | Value |
|---|---|
| **ID** | API-011 |
| **Title** | `BOT_TOKEN` is distributed to more containers than the bot needs, and the web/scheduler tiers hold it |
| **Severity** | MEDIUM (held) |
| **Category** | Least privilege |
| **File(s)** | `docker-compose.yml:62,96,131,240-243,283-286` · `docker-compose.prod.yml:11-12,99-102,131-169` · `src/backend/apps/search/services/immediate_alerts.py:186,199` · `src/backend/apps/search/management/commands/send_alerts.py:161` · `src/backend/config/settings/prod.py:161-174` |
| **Type** | SPEC-DEVIATION |
| **Status** | Validated (reclassified) |

**Problem (verified, counts corrected).** The project's stated model is "one web
process, one bot process, one shared DB", and the phase rubric asks that the bot
credential be present "nowhere except the runtime environment". The token is
env-sourced (correct) but distributed far beyond the bot:

- The base compose passes `BOT_TOKEN: ${BOT_TOKEN}` **explicitly** to three
  one-shot services (`migrate`, `load_cities`, `load_catalog`) — verified.
- Every service carries `env_file`, and the base compose sets `env_file: .env.dev`
  on **all nine** services, while the production override sets
  `env_file: .env.prod` on eight (`web`, `bot`, `migrate`, `create_admin`, `seed`,
  `load_cities`, `load_catalog`, `scheduler`) and bind-mounts
  `./.env.prod:/app/src/.env:ro` into each — which `base.py` loads into
  `os.environ` at import.

**Two corrections to the auditor's evidence.**

1. **The count is wrong in both directions.** The report says "six containers"
   and names `backup` as one of them. The `backup` service has an explicit
   `environment:` block and **no `env_file` and no `.env.prod` mount** — it is a
   `pg_dump` loop in the `postgres` image and correctly does not hold the token.
   The real exposure is **eight** Django containers (the list above), all of
   which also bind-mount the whole `.env.prod` file. The finding's *direction* is
   therefore understated, not overstated.
2. **The explicit `BOT_TOKEN:` lines are not the mechanism.** All three one-shot
   services already have `env_file: .env.dev` (and `.env.prod` in production), so
   the token reaches them regardless. The explicit lines document intent; the
   `env_file`-everywhere pattern is what actually distributes the credential.
   Fixing only the explicit lines would change nothing.

**The web/scheduler claim, corrected.** The report says the web and scheduler
tiers "actively use it". Verified: `send_alerts.py:161` (the **scheduler**,
daily at 08:00 UTC) constructs its own `Bot` — live and unconditional.
`immediate_alerts.py:186` (the **web** tier, via `Ad.post_save` →
`transaction.on_commit`) also constructs its own `Bot`, **but that path is gated
by `IMMEDIATE_ALERTS_ENABLED`, which defaults to `False` and is set to `false` in
all three `.env.*.example` files** — so the web-tier use is dormant unless an
operator opts in. The audit's claim of three active processes is two active, one
latent.

**Impact (unchanged in substance).** The blast radius of any single-tier
compromise widens from "the site" to "the site plus the ability to post as the
bot and message every user" — the latter enables phishing from a trusted,
pre-existing conversation. The one-shot services are the weakest link: they run
on every deploy, read the token and the entire `.env` at import, and are the
least hardened. The token is also re-read by the settings module purely as an
import-time *requirement* (`prod.py` raises if it is empty), so the one-shots
are forced to hold it to satisfy a guard they never exercise.

**Root cause.** The production settings module is monolithic: `prod.py` requires
`BOT_TOKEN` unconditionally, so any process importing it must hold the token.
Separately, the two alert senders mint their own `Bot` instead of delegating to a
single outbound gateway, so the credential naturally spreads.

**Recommendation (unchanged).** Two small moves. (1) Make the guard conditional
on what the process actually does — move the `BOT_TOKEN` requirement out of
`prod.py` and into the bot/scheduler bootstrap, so the one-shots never need it;
then **remove `env_file` from the services that do not need the whole `.env`**
(the three one-shots, `create_admin`, `seed`), not just the explicit
`BOT_TOKEN:` lines. (2) If the env-file restructuring is judged too invasive for
now, at least document the exposure in `docs/ops/docker-deployment.md` so a
compromise-response runbook knows to rotate `BOT_TOKEN` — not just
`DJANGO_SECRET_KEY` — when the web tier is suspected, and note the multi-process
flood-control consequence (each process has its own rate-limit budget, so
flood control is enforced against the token in aggregate, not per process).

**CWE:** CWE-250 · **Effort** S (compose only) / M (settings split + env_file) · **Priority** P2 · **Likelihood** LOW
**Related:** API-003, API-004, API-014

> **Validation Note:**
> - **Action:** validated; **evidence corrected** (container count, `backup` claim, web-tier activity)
> - **Detail:** The defect is real and MEDIUM is right, but two pieces of evidence do not survive checking: `backup` does **not** hold `BOT_TOKEN` (no `env_file`, no mount), and the web-tier `Bot` construction is behind a default-off flag, so it is latent rather than active. The correct exposure is **eight** Django containers, and the real distribution mechanism is `env_file` on every service, not the three explicit `BOT_TOKEN:` lines. **The recommendation must change accordingly** — removing only the explicit lines is a no-op.
> - **See also:** API-003, API-004.

---

### API-012: [MEDIUM] — `/save-search/` skips `redact_search_query()` — CONFIRMED (scoped down; superseded in part by VAL-002)

| Field | Value |
|---|---|
| **ID** | API-012 |
| **Title** | `/save-search/` is the only query-persistence ingress that skips `redact_search_query()` |
| **Severity** | MEDIUM (held) |
| **Category** | Privacy / consistency |
| **File(s)** | `src/backend/apps/search/views/save_search.py:37,48-57` · `src/backend/apps/search/services/search_history.py:58-83` · `src/backend/apps/search/services/popular_search.py:35-52` · `src/backend/apps/search/migrations/0002_redact_search_queries.py` |
| **Type** | BEST-PRACTICE |
| **Status** | Validated |

**Problem (verified).** The project ships a dedicated PII redactor for
buyer-typed queries. Two of the three write paths use it —
`record_search_history()` stores `redact_search_query(query)` into
`SearchHistory.query`, and `bump_popular_search()` stores the redacted form into
`PopularSearch.query`. The third write path, `save_search.save_search()`, takes
the raw `request.POST["query"]` and writes it straight into `SavedSearch.query`:

```python
query = (request.POST.get("query") or "").strip()
...
saved_search = SavedSearch.objects.create(user=request.user, query=query or None, ...)
```

The row is retained indefinitely, has no expiry, and is echoed back to the buyer
in the bot's `/alerts` listing.

**Impact.** A logged-in buyer who types a phone number, an e-mail address or
their own name into the "save this search" box has it stored verbatim for the
lifetime of the row, defeating the redaction applied to the same data two tables
away. It is also an inconsistent-privacy footgun: a reviewer reading
`save_search.py` alone cannot know redaction is required, because the rule lives
in two sibling service modules and a migration.

**Scope correction by validation — this is a real gap, but not the biggest one in
this area.** The auditor correctly scoped this to the *API surface* rather than
the PII policy (phase 06's territory) and that scoping is right. But validation
found that the redaction control this finding relies on is **itself ineffective
at the storage layer**: both "protected" tables store the **raw** query in their
`query_normalized` column, which the `0002_redact_search_queries` migration
deliberately left intact. That is filed separately as **VAL-002** because it is a
different defect with a different fix (a storage-layer decision, not a missing
call at a view). **Do not treat fixing API-012 alone as closing the PII gap in
search persistence.**

**Root cause.** The redaction rule was applied per-table at the time each table
was added, rather than at the boundary where buyer text enters the system, so
each new write path has to remember it independently.

**Recommendation.** Apply `redact_search_query()` in `save_search.save_search()`
before `SavedSearch.objects.create(query=...)`, matching the other two paths, and
add a test asserting a `SavedSearch` created with `"+382 69 000 123"` does not
store the raw digits. If the unredacted form is genuinely wanted for the buyer's
own saved search, that is a legitimate product decision — but then it must be
(a) an explicit, documented decision, (b) covered by a retention rule, and
(c) excluded from any path that renders to a third party. Recommend: redact on
write for consistency, and note the decision in the privacy page's
search-history paragraph. **Sequence this with VAL-002, not instead of it.**

**CWE:** CWE-359 · **Effort** S · **Priority** P1 · **Likelihood** MEDIUM
**Related:** API-009, API-017, **VAL-002**

> **Validation Note:**
> - **Action:** validated (unchanged); scope boundary drawn against VAL-002
> - **Detail:** The gap is exactly as filed. Two clarifications for remediation: (1) the correct cross-phase owner for the *policy* question is phase 06, and the API-surface framing is right — a missing call at an authenticated endpoint; (2) the recommended one-line fix is necessary but **not sufficient**, because `query_normalized` stores the unredacted value in both tables this finding cites as "protected" (VAL-002). Recording the boundary now prevents a false "search PII is handled" signal.
> - **See also:** VAL-002, API-017.

---

### API-013: [MEDIUM] — `immediate_alerts` dispatches fire-and-forget — CONFIRMED

| Field | Value |
|---|---|
| **ID** | API-013 |
| **Title** | `immediate_alerts` dispatches fire-and-forget: unretrieved futures, an unbounded queue, and a shutdown that can outlast gunicorn's grace period |
| **Severity** | MEDIUM (held) |
| **Category** | Reliability / observability |
| **File(s)** | `src/backend/apps/search/services/immediate_alerts.py:52-58,97-112,183-188` · `gunicorn.conf.py:18,27` |
| **Type** | BEST-PRACTICE |
| **Status** | Validated |

**Three coupled weaknesses, all verified in source.**

**(a) The result is never inspected.** `_executor.submit(_run_send, payloads)`
discards the `Future`, and `_run_send` catches only `AiogramError` — so any other
exception is stored in a `Future` nobody retrieves, and the alert is lost with no
application log at all.

**(b) The queue is unbounded.** The pool is capped at 5 workers, but
`ThreadPoolExecutor`'s work queue is an unbounded `queue.SimpleQueue`, so the cap
throttles *concurrency* without bounding *backlog*. During a Telegram outage each
in-flight send can sit on aiogram's 60 s socket timeout plus a `retry_after`
sleep, so work accumulates with nothing to shed load.

**(c) The executor is never drained and blocks interpreter exit.**
`ThreadPoolExecutor` registers its workers with `threading._register_atexit`,
which joins every thread at exit; a send in flight at SIGTERM holds gunicorn's
`graceful_timeout = 30` / `timeout = 60` budget, after which the arbiter
force-kills the worker mid-send.

**Impact.** (a) A class of send failures is invisible — the system believes it
delivered, because the `SavedSearchNotification` row was written *before* the
send. (b) A sustained Telegram outage turns the cap from a protection into a
buffer that grows without limit, still issuing traffic at a Telegram that has
already said "stop". (c) Deploys get 502s or force-killed workers.

**Root cause.** The module replaced an unbounded `threading.Thread` with a
bounded pool but kept the fire-and-forget contract, so the parts of the contract
a `submit()`-based design makes explicit — error propagation, backpressure,
shutdown — were never added. `deliver_immediate_alerts` is also called from
`transaction.on_commit`, where blocking is not an option, which is presumably why
nothing blocks.

**Recommendation.** Make the dispatch observable and bounded without making the
request path block. (1) Attach a done-callback that calls `future.exception()` and
logs at ERROR with the payload count, so nothing is ever unretrieved. (2) Add a
backpressure gate: track in-flight batches and, above a threshold, log a WARNING
and skip the send (the daily `send_alerts` digest remains the safety net and the
`SavedSearchNotification` row still prevents a duplicate) — or at minimum make
`_MAX_DELIVERY_THREADS` a settings value so it can be tuned per environment.
(3) Register a shutdown hook calling
`_executor.shutdown(wait=False, cancel_futures=True)` so a deploy drops queued
sends instead of being killed holding them. Raise the `AiogramError`-only catch
in `_run_send` to `Exception` with `logger.exception`.

**CWE:** CWE-253 · **Effort** M · **Priority** P1 · **Likelihood** MEDIUM
**Related:** API-004, API-006

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** All three mechanisms confirmed in source. **Two qualifiers that affect prioritisation, not the verdict:** (1) the publish-time path is behind `IMMEDIATE_ALERTS_ENABLED`, which defaults to `False` in all three `.env.*.example` files — so (a) and (b) are **latent today**, not live, and the whole finding becomes live the moment an operator opts in; (2) the daily `send_alerts` path is **unconditional** and does not use this executor at all (it is a plain `asyncio.run` in a management-command subprocess), so the "alerts silently lost" impact applies to the publish-time path only. **Fix the code before flipping the flag.**
> - **See also:** API-004, API-006, API-011 (the `Bot` this module constructs is the dormant web-tier use).

---

## LOW (5)

### API-014: [LOW] — API-contract drift: unsatisfiable `Bearer` challenge, manual POST guards, no versioning, unauthenticated `/metrics`, trusted `X-Forwarded-Host`, unpinned TLS parameters — CONFIRMED

| Field | Value |
|---|---|
| **ID** | API-014 |
| **Title** | API-contract drift: unsatisfiable `Bearer` challenge, manual POST guards, no versioning, unauthenticated `/metrics`, trusted `X-Forwarded-Host`, unpinned TLS parameters |
| **Severity** | LOW (held) |
| **Category** | Maintainability / hardening |
| **File(s)** | `src/backend/apps/moderation/views/decorators.py:47-52` · `src/backend/apps/moderation/views/review.py` · `src/backend/config/urls.py:12` · `docker/nginx/nginx.conf:53-58,60-78,160-168` · `src/backend/config/settings/base.py:152-154` |
| **Type** | SPEC-DEVIATION |
| **Status** | Validated |

**Five small contract observations, all verified in source.**

1. `staff_required_api` answers 401 with `WWW-Authenticate: Bearer`, but the only
   accepted credential is a session cookie — the advertised scheme can never
   satisfy the challenge, so a generic HTTP client will retry with a Bearer token
   forever. (Verified at `decorators.py:47-52`.)
2. `approve_ad` guards with `@require_POST`; `reject_ad` and `ban_user` use a
   hand-written `if request.method != "POST": return redirect(...)`. Three
   state-changing endpoints, three shapes. **CSRF is still enforced on all of
   them — no `csrf_exempt` exists anywhere — so this is consistency, not a hole.**
   The auditor's framing is correct and should be preserved.
3. `/api/v1/bulk-action/` is the only versioned prefix; the other endpoints are
   unversioned, so there is no migration story when a shape must change.
4. `django_prometheus.urls` is included at path `""` (verified:
   `config/urls.py:12`), so `/metrics` is **unauthenticated in Django**; only
   nginx's `allow 127.0.0.1; deny all;` protects it, and it is therefore
   reachable from every sibling container on the Docker network — and in dev,
   where the web container publishes `8000:8000`, from the host.
5. `USE_X_FORWARDED_HOST = True` is trusted, but nginx never sets or clears
   `X-Forwarded-Host`, so a client-supplied value passes through untouched; the
   exposure is contained today only by `ALLOWED_HOSTS`. Separately, the TLS block
   pins no `ssl_protocols`, `ssl_ciphers`, `ssl_session_cache` or
   `ssl_session_tickets`.

**Impact.** Individually small; together they are the maintenance tax of an API
layer that grew by accretion. (4) is one missing network-policy line away from a
public metrics scrape once a sibling container is compromised. (5b) means a
future nginx upgrade can silently change the accepted cipher set.

**Recommendation (unchanged).** (1) Drop the `WWW-Authenticate` header on the 401
(or change it to `Session` with a comment) — one line, and it makes the challenge
honest. (2) Convert `reject_ad` and `ban_user` to `@require_POST` to match
`approve_ad`. (3) Document in `docs/01-spec/architecture-structure.md` that the
surface is an internal HTMX/JSON surface, that `/api/v1/` is the only versioned
prefix, and that versioning is a deliberate non-goal for a single-consumer
frontend — defensible, but it needs writing down. (4) Restrict `/metrics` in
Django as well as nginx, so the control does not live in one file only. (5) Add
`proxy_set_header X-Forwarded-Host $host;` to the proxied locations and pin
`ssl_protocols TLSv1.2 TLSv1.3;` plus `ssl_session_cache shared:SSL:10m;` so the
posture is reviewable rather than inherited.

**CWE:** CWE-319 (for the unpinned TLS parameters) · **Effort** S · **Priority** P2 · **Likelihood** LOW
**Related:** API-010

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** All five verified independently, including the `config/urls.py:12` root-mount that makes `/metrics` open in Django — the single most actionable item here. One correction to the auditor's inference: the `location /static/` block in `nginx.conf:61-78` has **no `X-Forwarded-Host`** either, and it *does* carry its own re-declared security headers, so item 5 applies to every proxied location, not only the catch-all. LOW is correct; this is a maintenance-and-hardening bundle, not a defect with a single failure mode.
> - **See also:** API-010 (same config file, same release).

---

### API-015: [LOW] — `/csp-report/` logs the whole report at INFO from an unauthenticated POST — CONFIRMED

| Field | Value |
|---|---|
| **ID** | API-015 |
| **Title** | `/csp-report/` logs the whole report — including `document-uri` and `referrer` — at INFO from an unauthenticated POST |
| **Severity** | LOW (held) |
| **Category** | Log hygiene |
| **File(s)** | `src/backend/apps/core/views.py:150-181` (log at `:180`) · `docker/nginx/nginx.conf:149-157` |
| **Type** | BEST-PRACTICE |
| **Status** | Validated |

**Problem (verified).** The view validates the payload with `CSPReportPayload`
(Pydantic, 422 on schema failure) and then logs the **entire, unfiltered** report
dict at INFO: `logger.info("CSP violation report: %s", report)`. The CSP report
schema browsers send includes `document-uri` (the full URL including its query
string) and `referrer`. Neither is bounded in the log statement, and the endpoint
is reachable by anyone — `@require_POST`-equivalent method check only, no auth —
while nginx allows it 10 r/s with `burst=10 nodelay`, an order of magnitude
looser than the ~1 r/s a violation-report sink would ever need.

**Impact.** Two distinct effects. (1) *Log volume / availability*: an
unauthenticated caller can push 10 requests/second of arbitrary JSON, each
producing a full-dict INFO line — the cheapest form of log DoS. (2) *PII in
logs*: page URLs routinely carry search queries (`/search/?q=…`), so a violation
on a search-results page writes the buyer's own search text into the log stream
in clear. Phase 06 owns PII minimisation; this is filed against the ingress
because the endpoint's design — log everything, from anyone — is the finding.

**Root cause.** The endpoint was built for Report-Only mode, where operators want
full visibility; logging the whole report was the fastest way to get it, and
nobody revisited it once it was clear the body contains URLs rather than just a
violated directive.

**Recommendation.** Log the fields an operator actually acts on —
`violated-directive`, `effective-directive`, `disposition`, `blocked-uri` (host +
path only) and the script `sample` — and drop `document-uri`'s query string and
`referrer` entirely, or route them through the existing `sanitize_query_for_log`.
Tighten the nginx zone to `rate=1r/s burst=5 nodelay`. Optionally cap the accepted
body size explicitly as defence in depth.

**CWE:** CWE-532 · **Effort** S · **Priority** P2 · **Likelihood** LOW
**Related:** API-012, API-017, API-005 (same nginx config)

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** The log line, the unauthenticated POST and the 10 r/s zone are all confirmed as filed. One correction: the endpoint has **no `@require_POST` decorator** — it is a hand-written `if request.method != "POST": return JsonResponse(..., status=405)` at `views.py:156-160`, matching the pattern API-014 flags for inconsistency. Immaterial to the verdict, but do not let a remediation write `@require_POST` onto a view whose siblings the report is simultaneously standardising.
> - **See also:** API-014, API-012.

---

### API-016: [LOW] — Floating image tags and a misleading default TLS cert path — CONFIRMED + STRENGTHENED

| Field | Value |
|---|---|
| **ID** | API-016 |
| **Title** | Runtime images use floating tags and the production TLS cert mount defaults to a host path that is empty on most hosts |
| **Severity** | LOW (held) |
| **Category** | Deployment portability |
| **File(s)** | `docker-compose.yml:7,29,304` · `docker-compose.prod.yml:8,23,33,42,50,59,67,80,85,132,173` |
| **Type** | BEST-PRACTICE |
| **Status** | Validated |

**Problem (verified).** Every third-party image in the production topology is
floating-tagged: `postgres:18-alpine`, `redis:7-alpine`, `nginx:alpine`
(pgbouncer is the exception, pinned at `1.25.2`). Separately, the production TLS
mount is `${TLS_CERT_PATH:-/etc/nginx/certs}:/etc/nginx/certs:ro` — an **absolute
host path**, not the repository's own `./docker/nginx/certs`, which is where the
`certs/` directory that ships with the project actually lives (and contains only
`.gitkeep`). Docker auto-creates a missing host bind-mount source as an empty
directory, so a deployment that forgets to export `TLS_CERT_PATH` does not fail at
mount time — it starts, mounts an empty directory, and nginx then aborts with
`cannot load certificate`. The `${VAR:-default}` syntax produces no warning.

**Strengthening evidence the auditor missed — the application image is floating
too, and that matters more.** Every production service references
`${REGISTRY:-ghcr.io}/${REPOSITORY:-manicko/mko_bazuna}:${IMAGE_TAG:-latest}`.
`docker-compose pull` on two hosts running "the current compose file" can move
**the entire application**, not just the datastores, to different code with no
change to the repository. The auditor inventoried the datastores and the proxy
and missed the app image, which is the higher-consequence half of the same
supply-chain argument.

**Impact.** (1) Non-reproducible deploys / supply chain: two hosts can be on
different code *and* different datastore minor versions without any repository
change; for PostgreSQL that is a genuine hazard across a major-version boundary.
(2) A misleading default for the one thing nginx cannot start without: an
operator following the deployment runbook who misses the `TLS_CERT_PATH` export
gets an empty mount and a crash-looping proxy, with compose output looking
successful.

**Root cause.** Floating tags are the default habit for compose files; the
`TLS_CERT_PATH` default was written as "where certificates usually live on a
Linux box" rather than "where this repository keeps them".

**Recommendation.** (1) Pin **every** image, starting with the application image:
require `IMAGE_TAG` (change the default from `latest` to something that fails
loudly, or remove the default entirely) and pin the third-party images to a
patch version or digest. Add a scheduled bump job — a monthly "pull and test"
run keeps them current without making every deploy a coin flip. (2) Change the
default to the in-repo path so a fresh clone works with no export:
`${TLS_CERT_PATH:-./docker/nginx/certs}:/etc/nginx/certs:ro`, and state in the
runbook that the path resolves on the **host**. Optionally add an entrypoint
precondition so the failure is a one-line explanation instead of an nginx
TLS-parsing error.

**CWE:** CWE-1104 · **Effort** S · **Priority** P2 · **Likelihood** LOW
**Related:** API-014

> **Validation Note:**
> - **Action:** validated; **scope widened** (application image added)
> - **Detail:** Both halves confirmed as filed, plus the `IMAGE_TAG:-latest` default on all eight production services — the more material half of the same finding, and the one a reader would most want flagged. LOW is correct (deployment hygiene, not a runtime defect). Coordinate the tag bumps with phase 12's runbooks.
> - **See also:** API-014, CFG-002 (phase 02 — CI's prod-config import gate is *also* dead; the two together mean the deployment surface has no automated check at all).

---

### API-017: [LOW] — Translation logs seller free text with the non-redacting sanitiser; breaker state is invisible — CONFIRMED

| Field | Value |
|---|---|
| **ID** | API-017 |
| **Title** | Translation logs seller free text with the non-redacting sanitiser, and breaker state is only visible as a per-call INFO line |
| **Severity** | LOW (held) |
| **Category** | Observability / log hygiene |
| **File(s)** | `src/backend/apps/core/services/translation.py:172-177,187-193,207-215,222-233,246-250` · `src/backend/apps/core/utils/sanitize.py` |
| **Type** | BEST-PRACTICE |
| **Status** | Validated |

**Problem (verified).** Every log line in the translation service that includes ad
text passes it through `sanitize_query_for_log`, which strips control characters
and truncates — it does **not** mask PII. The project ships a second sanitiser,
`redact_search_query`, which masks phone numbers, e-mails and personal names. A
seller who writes their phone number into a title (extremely common on a
classifieds board) therefore has it written to production logs at INFO and
WARNING by the translator's own diagnostics. The circuit breaker is observable
only as one INFO line per call, so "how many ads were published untranslated in
the last hour" requires a log grep — there is no counter, gauge or threshold to
alert on.

**Credit where due, and it is verified:** the HTTP-failure lines already strip
the credential — `str(e.request.url.copy_with(params={}))` removes the `key` query
parameter, so `GOOGLE_TRANSLATE_API_KEY` cannot leak through these logs. The
practise is correct and should be the model for the ad-text lines.

**Impact.** Modest but real: the ad text that a buyer-side PII control already
decided to mask is persisted in the log stream by a different code path, and the
single most operationally interesting state of this integration (the breaker being
open, meaning every ad ships untranslated) has no metric. The two combine with
API-007: the fallback is invisible, unmeasured and logged at a level that will
not page anyone.

**Root cause.** Two sanitisers exist for two different audiences — one written
for safe-to-log text, one for user-typed text — and the boundary was never
stated, so the translation path picked the wrong one by name similarity.

**Recommendation.** (1) Route ad text through `redact_search_query` in the log
sites, or compose the two — redact, then truncate. (2) Add counters
(`translation_requests_total`, `translation_fallback_total`,
`translation_circuit_open`) exposed on the existing `/metrics` endpoint (the
`django_prometheus` wiring is already in place), so "the translator is down"
becomes alertable and the API-007 fallback count can be measured rather than
inferred. (3) Note in the module docstring which sanitiser applies to which kind
of text, so the next caller picks correctly.

**CWE:** CWE-532 · **Effort** S · **Priority** P2 · **Likelihood** MEDIUM
**Related:** API-007, API-012

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** The mechanism and the credential-stripping credit are both confirmed. One **cross-phase ownership note:** the ad-text-in-logs half is the same class of defect phase 06 filed as PII-102 (raw identifiers logged on send failure) and phase 06 already owns the log-hygiene policy and has regression tests for it. **Do not action the log-field-selection change twice** — the metric/counter half (2) is unambiguously this phase's; the sanitiser swap (1) should be reviewed against phase 06's existing redaction tests so the new assertions land in one place.
> - **See also:** API-007, API-012, PII-102 (phase 06).

---

# Validation-Level Findings (VAL-)

These are issues with the **audit inputs and the remediation plan**, not
source-code defects.

### VAL-001: [MEDIUM] — Cross-phase double-ownership: API-009 ↔ CFG-004, and API-008 ↔ DB-008

**Action:** cross-phase reconciliation recorded, no merge performed.

| This phase | Other phase | Relationship | Ruling |
|---|---|---|---|
| **API-009** (`EMAIL_HOST` mandatory, justified by flows that do not exist) | **02-CFG / CFG-004** (`EMAIL_BACKEND` env-overridable in prod; transactional email can be routed to stdout — reproduced via the console backend) | **Different defects, same settings block.** CFG-004 is the *backend-selection* problem (a prod operator can point mail at stdout, dumping a support ticket into logs). API-009 is the *requirement-justification* problem (the host itself is a hard boot gate for a feature that does not exist). Neither subsumes the other; both live in `prod.py`'s email section. | **Do not merge. Do not re-file.** Phase 02 owns CFG-001/002/004 (settings/env validation); phase 09 owns the *existence-of-consumers* question. A single fix pass should touch both lines together. |
| **API-008** (`load_exchange_rates` reverts operator edits; no external feed) | **03-DB / DB-008** (hourly and full-table sweeps hold `select_for_update()` row locks for their entire duration, including `recompute_normalized_prices`) | **Adjacent, not overlapping.** DB-008 is about lock *duration* in the recompute sweep; API-008 is about the *rate table being overwritten* by a boot-time seed. Different code, different mechanism, different failure. They compose — a reverted rate produces a full-table recompute that then locks for its whole sweep — but fixing either does not fix the other. | **No merge. Cross-reference only.** DB-008's mechanism and remediation (bounding the sweep) stay with phase 03. |
| **API-001/002** (Redis as an undeclared hard dependency) | **03-DB / DB-004** (one blocked `select_for_update` stalls every DB op in the bot; no `lock_timeout`/`statement_timeout` anywhere) | **Complementary, both untested failure posture.** DB-004 establishes that the project has no bounded failure mode for *any* blocking resource; API-001/002 establish that a cache blip takes both tiers down. Together they mean the system's failure posture is systematically untested — relevant context, but the ownership does not overlap. | **No merge.** DB-004's timeout remediation is phase 03's. Record API-001/002 as an *instance* of the same class in the phase-03 roll-up. |

**Contradiction check: none found.** No two phases assert incompatible facts
about the same code. Phase 06's PII-104 (alert audience ignores consent state)
and this phase's API-006 (alert body is unescaped) are both real and independent.

### VAL-002: [MEDIUM] — MISS: `query_normalized` stores the *unredacted* query, so the SRH-004 redaction control is cosmetic

| Field | Value |
|---|---|
| **ID** | VAL-002 |
| **Title** | `SearchHistory.query_normalized` and `PopularSearch.query_normalized` are written with the **raw** query, so the redaction this project believes it applies to buyer search text does not remove the PII from storage |
| **Severity** | MEDIUM |
| **Category** | Privacy / data integrity |
| **Type** | SPEC-DEVIATION (auditor miss) |
| **Status** | Open — needs an owner |

**The miss.** Both write paths that *do* call `redact_search_query()` write two
values:

```python
# apps/search/services/search_history.py:58-83
normalized = query.strip().lower()          # <-- RAW, unredacted
redacted   = redact_search_query(query)     # <-- redacted
SearchHistory.objects.create(query=redacted, query_normalized=normalized)

# apps/search/services/popular_search.py:35-52  — identical shape
PopularSearch.objects.get_or_create(query_normalized=normalized, defaults={"query": redacted, ...})
```

`query_normalized` is a persisted, indexed `CharField(max_length=200)` on both
models. The data migration `0002_redact_search_queries` rewrites **only** the
`query` column and says so explicitly: *"`query_normalized` is the lookup/dedup
key … **`query_normalized` … is preserved intact**."*

**Impact.** A buyer who types a phone number or e-mail into the search box gets
it stored in clear in `query_normalized` — the column the dedup and lookup logic
actually keys on, and the one the migration deliberately preserved. The
`query` column shows a masked value, which is what makes this look safe when
read. The retention story is therefore a redaction that does not redact.

**Why this is filed at MEDIUM and not CRITICAL.** The exposure is the buyer's
own search text, reached only through an authenticated or anonymous search
action, and the PII is retained under the same retention rules as the rest of
the search data. It is not the orphaned-with-every-identifier-intact defect
phase 06 filed as PII-101, and it is not a credential.

**Ruling on ownership — this must be actioned once, not twice.** The
*correctness* defect is in `apps/search` (two service modules plus one migration
that would need a follow-up data migration to repair existing rows), so it is a
strong candidate for the phase-08 search owner. The *policy* question ("may we
key a dedup index on unredacted PII at all?") belongs to phase 06, which owns
PII minimisation. API-012 and VAL-002 are **not merged** — they have different
fixes (a missing call at a view vs. a storage-layer decision plus a data
migration) — but they must be sequenced together and reported as one remediation
item, or the tracker will record "search PII handled" after fixing only the view.

### VAL-003: [MEDIUM] — Evidence defect: several phase-09 line anchors do not match the tree

| Field | Value |
|---|---|
| **ID** | VAL-003 |
| **Title** | The phase-09 report's line-numbered evidence for API-007 (and parts of API-006/API-008) points at code that does not exist, so remediation keyed to those offsets will land in the wrong place |
| **Severity** | MEDIUM |
| **Category** | Audit-input quality |
| **Type** | Process finding |
| **Status** | Open — affects the remediation tracker |

**The problem.** Findings were checked line-by-line against the tree. Most anchors
are accurate, but a meaningful minority are not:

| Finding | Cited | Actual |
|---|---|---|
| API-007 | `backfill_translations.py:97-102,163-180,221-231` | File is **124 lines**. Offsets 163–231 do not exist. |
| API-007 | `asyncio.run(run_backfill(qs))` | No `asyncio.run` in the file; the command is synchronous. |
| API-007 | "no `--limit`, no batching, no progress logging" | `--batch-size` exists and drives `iterator(chunk_size=…)`. |
| API-007 | `submission.py:120-137` with `title_bs=input.title_bs or bs_title` | `submission.py:194-202` assigns only when the input field is truthy; the quoted expression does not exist. |
| API-007 | `translation.py:301-327,353-358` | File is **250 lines**. |
| API-006 | `immediate_alerts.py:134-161,207,232` | File is **247 lines**; the builder is at `143-149`, the `parse_mode` lines at `207`/`232` (these are correct). |
| API-008 | `models.py:41-56,58-90`; `load_exchange_rates.py:30-40,62-73` | Command is **79 lines**; `62-73` is inside `handle`, close but offset. |

**Why this matters and does not.** The **claims** survive — every one of them was
re-derived independently and confirmed against the current code. What is unsafe is
the **remediation anchor**. A developer or agent handed "fix
`backfill_translations.py:221-231`" will either find nothing or edit the wrong
region. Given the remediation tracker keys on finding IDs and this report is its
input, every line anchor in this phase should be treated as **advisory** and
re-resolved by symbol name at implementation time.

**Corrected anchors for the three affected findings** are supplied inline in
their sections above (API-006, API-007, API-008) and are symbol-anchored, not
line-anchored.

**Wider note.** The same `API-` vs `EXT-` collision the report documents in its
metadata is a symptom of a shared root cause: this project hard-codes finding IDs
from **prior audit cycles** as in-source markers (the report lists
`nginx.conf:139`, `telegram_bot/retry.py:1`, `middlewares/update_id_dedup.py`,
`handlers/login.py:112`, and two test files), and phase 01's validator raised the
identical hazard as VAL-002 for the `AUT-` prefix. **The remediation tracker must
be keyed on `<phase>-<prefix>-<NNN>` (e.g. `09-API-007`), never on the bare ID.**
I have found a third instance in this phase's own scope: `docs/ops/docker-deployment.md:429`
attributes the `REDIS_URL` fail-fast guard to **CFG-001**, but in the current
phase-02 numbering CFG-001 is `DJANGO_ONESHOT=1` disabling the prod secret guards
— a different defect. That doc line should be corrected when the email/password-reset
corrections in API-009 are made.

### VAL-004: [MEDIUM] — Rollout hazard: API-004's return-contract change breaks a green test that encodes the defect as intended behaviour

| Field | Value |
|---|---|
| **ID** | VAL-004 |
| **Title** | Changing `retry_transient` to return `False` on exhaustion fails `test_error_handler_marks_handled_after_exhausting_bound`, which asserts the current (incorrect) contract; the test must change, not the production code |
| **Severity** | MEDIUM |
| **Category** | Rollout safety / test quality |
| **Type** | Process finding |
| **Status** | Open — must be handled in the same change as API-004 |

**Detail.** `retry_transient` has exactly one production caller (the Dispatcher
`errors` observer) and **no application code depends on its return value** — this
was checked specifically, and the answer is clean. There is exactly one in-repo
dependency, and it is a test:

```python
# src/telegram_bot/tests/test_error_handler.py:93-125
async def test_error_handler_marks_handled_after_exhausting_bound(monkeypatch):
    ...
    result = await handler(event, bot=bot)
    assert result is True          # <-- asserts the defect as intended behaviour
```

Additionally, the file's `_make_dispatcher()` helper (line 32-36) hard-codes
`ExceptionTypeFilter(TelegramRetryAfter)`, so the recommendation to register
`ExceptionTypeFilter(_TRANSIENT_EXCEPTIONS)` also requires editing the helper —
otherwise the new test for a `TelegramServerError` replay would not reach the
handler at all, and would pass vacuously.

**Ruling.** The project's binding rule is *production code is king* — when a test
conflicts with the correct behaviour, the **test** is what changes. This test
does conflict: it encodes "mark an exhausted outbound call as handled" as the
intended contract, which is precisely defect (3) of API-004. The change must
therefore be presented as a **single atomic change touching `retry.py`,
`main.py`, and `test_error_handler.py`**. Shipping `retry.py` alone will produce
a red suite and will invite someone to "fix" the test by reverting the
production change.

**Also required:** a new test asserting a `TelegramServerError` is replayed, and
one asserting a `retry_after=600` produces a **bounded** total sleep. Both are
part of API-004's recommendation; the first depends on the helper change above.

### VAL-005: [MEDIUM] — Rollout-safety claim REJECTED: the API-002/API-003 same-release coupling is unsound as stated

| Field | Value |
|---|---|
| **ID** | VAL-005 |
| **Title** | The report's claim that API-002 and API-003 "must land in the same release" does not hold; the correct constraint is the opposite ordering, and the real prerequisite is API-003's per-seller cap landing *before* API-002 ships fail-open |
| **Severity** | MEDIUM |
| **Category** | Rollout safety |
| **Type** | Process finding |
| **Status** | Open — corrects the phase's roadmap |

**The claim under test.** The report's Wave 1 states: *"API-003 … **This must
land together with API-002**, because API-002 makes the limiter fail open during
a cache outage and a fail-open seller-spam guard is not a guard."*

**Why it is wrong.** The argument conflates two independent properties:

1. **A guard that fails *closed* is not a working guard either.** Today,
   API-002's state means that during a Redis outage the `contact_<ad_id>` branch
   raises — and the deep link is *already* unrated, so it is unprotected in both
   states. API-002's fix changes the *failure mode of the existing* guards
   (login, contact_us, support, upload). It does **not** create a new hole on
   `contact_<ad_id>`, because no limiter exists there to fail either way. Adding
   API-002 before API-003 therefore does not "remove" the contact guard; it was
   never there.
2. **The harm API-002's fail-open could enable is bounded by a much shorter
   window than a release cycle.** A Redis outage that coincides with a
   `contact_<ad_id>` spam run is a compound event. Meanwhile the *guaranteed*
   consequence of shipping API-003 alone is **zero** — a new limiter on a
   previously unlimited path is a pure tightening, with no failure mode it can
   introduce. A pure tightening has no ordering constraint.

**The constraint that IS real.** The valid sequencing is narrower and belongs to
API-003 itself, not to API-002:

- **API-003's per-seller cap must be part of API-003, not a follow-up.** The
  auditor's own reasoning is correct on this: because the expensive part of the
  flow is the outbound message *to the seller*, a per-buyer limit alone can be
  trivially evaded by the attacker (they control the buyer's account, not the
  seller's). If API-003 ships with only the per-buyer guard, the fail-open
  scenario becomes materially worse. So: **the per-seller cap is a prerequisite
  of shipping API-003 at all.**
- **API-002 and API-003 may ship in separate releases** — and should, because
  they are independent one-line-to-one-helper changes in different layers
  (backend cache guards vs. bot handler), and coupling them doubles the blast
  radius of a single deploy for no safety gain.

**Corrected rollout order for Wave 1:** API-001 → API-003 (with per-seller cap)
→ API-002 → API-004 (with VAL-004's test change) → API-005. This is also strictly
better as a sequence: it closes the *unbounded external* abuse path before
introducing any fail-open behaviour anywhere.

### VAL-006: [MEDIUM] — Dependency: API-001 and API-008 both define "what a cache read does on failure", and must land in one wave

| Field | Value |
|---|---|
| **ID** | VAL-006 |
| **Title** | API-001 introduces a `cache_get_or_none()` shared contract and API-008 requires `invalidate_rate_cache()` to be wired; landing them in different releases leaves a half-migrated cache contract with no owner |
| **Severity** | MEDIUM |
| **Category** | Rollout safety / architectural consistency |
| **Type** | Process finding |
| **Status** | Open — sequencing constraint |

**Detail.** API-001's recommendation is to state the fail-open cache contract
**once**, in `apps/core/utils/cache.py`, as a `cache_get_or_none()` helper, and to
route every request-path cached read through it. API-008's recommendation is to
wire the already-written `PriceNormalizer.invalidate_rate_cache()` into the
rate-change path — and the shared-cache contract those two interact through is
the same 5-minute rate cache read at `price_normalizer.py:93`.

Two risks if they are split:

1. **Half-migrated contract.** If API-008 lands first, the rate cache keeps
   serving the pre-boot value for up to 5 minutes with no invalidation, and the
   next developer to touch `apps/core/utils/cache.py` finds a `cache_get_or_none`
   helper that does not exist yet. If API-001 lands first, the helper exists but
   `invalidate_rate_cache` is still orphaned, so the auditor's API-008
   recommendation reads as already-done.
2. **The rate-cache read is a *third* instance of the API-001 pattern that the
   report under-counts.** The report lists `PriceNormalizer._get_current_rate`
   among the consumers to route through the helper, but does not note that on the
   `submit_ad` / `edit` paths it is already inside a broad `except Exception` that
   degrades to `price_normalized_eur = None` — i.e. under a cache outage **price
   normalisation silently stops working and prices are stored un-normalised**,
   which is a data-integrity consequence the report does not call out.

**Constraint.** Land API-001 and API-008 in the **same release**, or land API-001
first and treat API-008 as "in progress, do not close". Add the
`price_normalized_eur = None` degradation to API-001's regression test so the
silent-normalisation-failure mode is asserted, not just the 200s.

---

# Cross-Phase Reconciliation

This section is required reading before acting on API-008 and API-009, because
both **refute a claim made in the phase brief**.

## 1. API-008 — there is no external exchange-rate feed. The brief was wrong.

**Brief asserted:** an external exchange-rate feed exists, and `load_exchange_rates`
refreshes it.

**Verified false, on three independent grounds:**

| Evidence | Finding |
|---|---|
| `apps/currencies` contains **no HTTP client, no scheduler task and no network call** of any kind. `INITIAL_RATES` is a three-entry literal with `EFFECTIVE_DATE = 2026-08-22` and `SOURCE = "manual_seed"`. The model docstring itself says the feed is designed to arrive **"later"**. | The feed is aspirational. |
| `docs/ops/migration-workflow.md:353-354` states that **`load_exchange_rates` makes HTTP calls to ECB** — and gives that as the *reason* the command is a separate one-shot rather than a data migration. | The ops runbook is the *actively misleading* artifact, and the auditor did not find it. |
| Test-container bootstrap on a warm DB printed `Exchange rates loaded: 0 created, 3 updated`. | The command overwrites unconditionally, every boot. |

**Impact, stated precisely.** Two distinct harms, and they should not be conflated:

- **Operational (the real one).** An operator who corrects a drifted rate in the
  Django admin has it silently reverted at the next deploy, with no warning and
  no record of the previous value. Because `price_normalized_eur` is derived from
  the rate and is **not** recomputed by the seed, the rate table and every
  derived price silently diverge. An operator who believes their correction took
  effect is serving prices computed from a rate they did not choose — and every
  cross-currency filter and sort on the site reads that column.
- **Informational.** Any capacity, egress or failure-mode analysis of this system
  that assumes a live rate feed is wrong in both directions: there is no egress
  to budget and no upstream that can fail. `REDIS_URL`-based assumptions are the
  ones that actually matter here, and those are API-001's subject.

**Overlap with phase 03 (DB-008):** **none in mechanism.** DB-008 is about
`recompute_normalized_prices` holding row locks for a whole-table sweep inside one
transaction. API-008 is about the rate row being overwritten by a boot-time seed.
They compose — a reverted rate causes a full-table recompute that then holds locks
for its entire sweep — but fixing either does not fix the other, and the
remediations are unrelated. **Do not merge; cross-reference.** See VAL-001.

## 2. API-009 — there is no password-reset or transactional-email flow. The brief was wrong.

**Brief asserted:** `prod.py:198-199` justifies mandatory `EMAIL_HOST` by
referring to password resets; a prior phase had confirmed the console backend is
accepted in prod and message bodies including a reset token reach stdout.

**Verified:** the console-backend half is phase 02's `CFG-004` and is not
re-litigated here. The password-reset half is **false** — there is no such flow,
and therefore no reset token that could ever reach stdout. The auditor is right
and the brief's framing needs correcting.

| Claimed flow | Actual |
|---|---|
| Password resets | **Do not exist.** No view, URL, template, `token_generator`, `PasswordResetView` or `PasswordResetForm` anywhere in `src/`. |
| Alert notifications by e-mail | **Do not exist.** Alerts are Telegram — both the instant fan-out and the daily digest. |
| Seller confirmations by e-mail | **Do not exist.** Publishing is a Telegram reply. |
| — | The **only** real e-mail path: `support_delivery_email.deliver_support_ticket_email`, the bot's support-desk notification to the admin inbox. Explicitly **fail-open** (`except Exception` → log → return `False`). |
| — | `set_password` has exactly one call site, in `create_admin_user.py:116`, writing a local superuser password. It sends nothing. |

**Impact, stated precisely.** A fail-open, best-effort, single-purpose integration
has been made a **hard boot gate for the entire system**: `ImproperlyConfigured`
at settings import stops web, bot, scheduler and every one-shot container. Two
consequences follow, and the second is the more important:

1. A staging or DR host that can serve the site perfectly well without SMTP
   cannot boot. That is a self-inflicted availability dependency with no
   corresponding capability.
2. **The stated reason is fictional, and it is repeated in the runbook that
   operators follow during an incident.** Not just the settings comment — also
   `docker-deployment.md:355`, `:402`, `:429` and `rollback.md:218`. Two of
   those are in the *secret-rotation / compromise-response* procedure and tell
   the operator that rotating `DJANGO_SECRET_KEY` expires "password-reset
   links". A runbook that overstates the system's identity capabilities during an
   incident is worse than an incorrect code comment, because it changes what an
   operator believes they are protecting.

**Overlap with phase 02 (CFG-004):** **adjacent, not duplicate — do not re-file.**
CFG-004 is the *backend-selection* problem (prod `EMAIL_BACKEND` is
env-overridable, so transactional mail can be routed to stdout). API-009 is the
*requirement-justification* problem (the host is a hard gate for a feature that
does not exist). Different defects, same settings block, both small. Action them
in one pass; report them as two findings. See VAL-001.

**Decision required (a human call, not a code call).** Keep `EMAIL_HOST` mandatory
with a *correct* justification, or demote it to a warning. Given the delivery path
already fails open, demoting matches the code's own behaviour; keeping it
mandatory is a defensible product decision, but the reason must be the real one
in all five places. This decision should be recorded before remediation starts,
because it determines whether the fix touches one comment or a settings guard.

---

# Required Fixes

Mandatory, in dependency order. This is the corrected Wave 1 from VAL-005 plus the
coupling constraints from VAL-004 and VAL-006.

| # | Action | Findings | Gate |
|---|---|---|---|
| 1 | Add `cache_get_or_none()` to `apps/core/utils/cache.py`; move the two site-config cache reads inside their existing `try`; route the rate-cache read through it. Regression test: patched cache → `/`, `/ads/<id>/`, `/login/issue/` return 200 **and** `price_normalized_eur` degradation is asserted. | API-001, VAL-006 | Must land with #5 |
| 2 | Add the buyer-per-10-min **and per-seller-per-hour** guards to the `contact_<ad_id>` branch. Test: the 6th trigger is refused **and no `send_message` is issued**. | API-003 | Per-seller cap is a prerequisite of shipping #2 at all |
| 3 | One shared `_bump_window()` helper catching `(ConnectionInterrupted, redis.RedisError, ValueError)`, failing open with a `logger.warning`; all four guards call it. | API-002 | Independent of #2 — may ship separately |
| 4 | Cap the backoff, register `ExceptionTypeFilter(_TRANSIENT_EXCEPTIONS)`, delete the unreachable `isinstance` guard, return `False` on exhaustion. **Atomically** update `test_error_handler.py` (the `_make_dispatcher` helper *and* the exhaustion test) — do not ship `retry.py` alone. | API-004, VAL-004 | Single atomic change |
| 5 | `get_or_create` instead of `update_or_create` in `load_exchange_rates`; wire `invalidate_rate_cache()` into the rate-change path; **correct `migration-workflow.md:353-354`**. | API-008, VAL-006 | Must land with #1 |
| 6 | Correct the password-reset rationale at all **five** sites, then decide mandatory-vs-warning for `EMAIL_HOST` and write the decision down. | API-009 | Human decision first |
| 7 | Redact on write in `save_search`; and separately resolve the `query_normalized` storage decision + follow-up data migration. | API-012, VAL-002 | Report as ONE remediation item |
| 8 | Escape (or plain-text) both alert builders; add the markup test. | API-006 | |
| 9 | Add a done-callback with `future.exception()`; bound the backlog; `shutdown(wait=False, cancel_futures=True)` on app shutdown. **Before** anyone enables `IMMEDIATE_ALERTS_ENABLED`. | API-013 | Flag is default-off; keep it off until this lands |
| 10 | Add a `media_limit` zone to `location /media/` in both configs; assert the assignment in a test that parses the shipped config. | API-005 | |

# Advisory Recommendations

1. **Adopt one cache-failure policy for the whole project, written down once.**
   The project already has the correct precedent (`UpdateIdDedupMiddleware`
   documents fail-open explicitly); it was simply never generalised. Every cache
   consumer should state its policy in its module docstring. This is the single
   highest-leverage structural change in the phase and it is a documentation
   convention, not new machinery.
2. **Route every outbound integration through one gateway.** `immediate_alerts`
   and `send_alerts` each mint their own `Bot` from `settings.BOT_TOKEN`, which is
   why the credential spreads to the web and scheduler tiers (API-011) and why
   retry policy lives in two places with different behaviour (API-004 vs
   API-006/API-013). A single outbound module owning the `Bot`, the retry
   policy, the per-process rate budget and the drop counter would collapse
   API-004, API-011 and API-013 into one change with one owner.
3. **Reconcile the in-source finding-ID markers.** `EXT-`, `AUT-` and `API-` all
   appear as hard-coded markers in shipped source and test files. Until the
   tracker is keyed on `<phase>-<prefix>-<NNN>`, ID collisions are a standing
   hazard. See VAL-003.
4. **Fix the ops runbook's capability claims as a class.** Three of the phase's
   findings are, at root, "the documentation asserts a capability the code does
   not have": the ECB feed, password reset, and (per phase 02) a live prod-config
   CI gate. A short "verified capabilities" section in the deployment runbook —
   each line with the command that proves it — would prevent the next cycle from
   re-deriving the same findings.
5. **Re-grade API-005 upward if a scraper is ever observed.** It was lowered from
   HIGH to MEDIUM on the strength of the harm being bounded to DB pressure rather
   than a lost guarantee. That judgement is contingent on the absence of
   observed traffic; one incident changes it.

# Warnings

- **Architectural risk.** The three HIGH availability findings share one root
  cause: an undeclared, unguarded Redis dependency across both tiers. Fixing them
  as three patches leaves the *class* intact. The durable fix is one documented
  cache-failure policy plus one shared helper (advisory #1), not three
  `try/except` blocks.
- **Architectural risk.** There is no single owner for outbound Telegram. Three
  modules construct `Bot` objects with three different retry policies and three
  different error taxonomies. API-004, API-006, API-011 and API-013 are four
  symptoms of that one gap and will keep recurring until it has an owner.
- **Rollout risk.** API-004 shipped without its test change produces a red suite
  and invites a revert of a correct fix (VAL-004). This is the highest-risk
  single change in the phase precisely because the fix is right.
- **Rollout risk.** API-010 is the only change that can break a *working*
  deployment — it requires the operator to set a real `server_name`. Verify with
  `nginx -t` before rolling.
- **Evidence risk.** Line-numbered anchors in this phase's raw report are not
  reliable (VAL-003). Re-resolve every target by symbol name.
- **Documentation risk.** The ops runbook currently asserts two capabilities the
  system does not have, in the compromise-response procedure. That is the finding
  most likely to cause a wrong decision under pressure, which is why API-008 and
  API-009 are placed first in the decision list even though API-009 is P2.
- **Maintainability risk.** The exchange-rate path has a correctly-written
  `invalidate_rate_cache()` with zero callers. A helper that is implemented,
  documented and never called is worse than an absent one — it reads as done.
  Add a lint or test rule that asserts every `invalidate_*`/`get_or_create`
  invalidation helper has a call site.

# Execution Validation

| Item | Status |
|---|---|
| All 17 finding IDs still exist in the tree | **Verified** — no finding is stale |
| Any finding already implemented | **None.** The one candidate — the documented `site_config` fallback — is documented but **not** implemented, which is exactly API-001's point. `invalidate_rate_cache` is implemented but unwired, which is API-008's point. |
| Dependencies remain valid | **Verified**, and two were found that the report did not state (VAL-004 test dependency, VAL-006 cache-contract coupling) |
| Architecture improves rather than degrades | **Yes**, provided advisory #1 and #2 are adopted. The current shape — cache policy and outbound policy duplicated per call site — is the thing that generated four of this phase's findings. |
| Source files modified by this validation | **None.** Read-only throughout; both probe scripts were deleted. |
| Task applicability | **Complete.** All 17 findings carry an explicit verdict. |

---

# Validation Summary

| Action | Count | Details |
|---|---|---|
| Validated (unchanged) | 10 | API-001, API-002, API-003, API-004, API-006, API-013, API-014, API-015, API-016, API-017 |
| Reclassified / Adjusted | 7 | API-005, API-007, API-008, API-009, API-010, API-011, API-012 |
| Merged | 0 | — |
| Rejected | 0 | No finding is rejected outright; API-007's secondary claim is rejected *within* the finding |
| VAL- (cross-phase / rollout / misses) | 6 | VAL-001, VAL-002, VAL-003, VAL-004, VAL-005, VAL-006 |

## Rejected Findings

| ID | Claim rejected | Reason |
|---|---|---|
| — | none | — |
| API-007 (part b) | Backfill is unbounded, has no `--limit`/batching/progress, uses `asyncio.run`, and `submit_ad` writes the fallback unconditionally | The cited offsets are past the end of a 124-line file; the command is synchronous and has `--batch-size`; it is env-gated out of the default boot; and `submission.py:194-202` assigns only when the input field is truthy. The surviving half (a) is confirmed. |

## Merged Findings

| Original ID | Merged Into | Rationale |
|---|---|---|
| — | none | No two findings in this phase share a root cause, and no cross-phase finding cleanly absorbs another. API-008 ↔ DB-008 and API-009 ↔ CFG-004 are adjacent, not mergeable — both pairs have different mechanisms *and* different fixes. Recorded in VAL-001. |

## Reclassified Findings

| ID | Original Type | New Type | Severity change | Rationale |
|---|---|---|---|---|
| API-005 | BEST-PRACTICE | BEST-PRACTICE | **HIGH → MEDIUM** | Defect confirmed and strengthened (no app-level limiter either, plus a duplicated query). Graded down because the harm is bounded DB pressure, not a lost guarantee, and the fix is one nginx line. One incident from HIGH. |
| API-010 | BEST-PRACTICE | BEST-PRACTICE | **MEDIUM → LOW** | The reflected value is the same value the client used to address the server, so no browser can be induced to follow a 301 from this origin to an attacker origin. The "phishing primitive served from your own domain" framing does not hold. Real hardening gap, not a MEDIUM security finding. |
| API-007 | SPEC-DEVIATION | SPEC-DEVIATION | MEDIUM held (narrowed) | Half (a) confirmed; half (b) rejected on evidence. Scope narrowed to `backfill_translations` — which is the worse path, because it is unrecoverable. |
| API-008 | DOC-UPDATE | **SPEC-DEVIATION** | MEDIUM held | Per §5's cross-reference rule: the spec/README/config do not claim a rate feed, so this is not a stale doc. The false claim lives in a code comment that motivates the command *and* in `migration-workflow.md:353-354`. A code-vs-documentation contradiction → code or policy must change. |
| API-009 | DOC-UPDATE | **SPEC-DEVIATION** | MEDIUM held | Same rule: no spec/README/config reference to password reset anywhere, so there is no "missing integration to build" — only a false justification in shipped code and in four runbook sites. Scope widened from 1 site to 5. |
