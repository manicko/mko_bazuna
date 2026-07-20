---
name: validated-findings
description: Phase 09 — External Integrations & API validated findings
agent: validator
related:
  - audit-findings
---

# Phase 09 Audit Findings — External Integrations & API (Validated)

**Executor:** auditor  
**Template:** .kilo/commands/audit/phases/09-audit-external-api.md  
**Status:** validated  
**Validator:** validator  
**Date:** 2026-07-20  

> `problems-only: true` — only problems, bugs, and deviations are documented.  
> All findings below have been validated against actual code, spec, and documentation.

---

## Findings

### EXT-001: Login-token issuance path is entirely missing — the deep-link login flow cannot work end-to-end

| Field | Value |
|-------|-------|
| **ID** | EXT-001 |
| **Severity** | CRITICAL |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | apps/users/urls.py, apps/users/views/*, apps/api/, config/urls.py, docker/nginx/nginx.conf |
| **Classification** | mandatory |

**Description:** The phase handbook treats the login-token deep-link as a core external integration (issuance → delivery → claim → replay → expiry). The **claim** side exists (src/telegram_bot/handlers/login.py:65-66, 69) but the **issuance + delivery** side has no production implementation:

- No code anywhere calls `LoginToken.objects.create(...)` except inside **tests** (apps/core/tests/test_sweep_commands.py:264).
- No Django view/URL mints a token; no `secrets.token_urlsafe` / `os.urandom` / `uuid` call exists for login (grep across the repo returns zero issuance sites).
- `apps/users/urls.py` registers only consent endpoints (`consent/accept/`, `consent/decline/`); there is no `/login/` route.
- The `apps/api/` app is an empty stub (`views/` and `serializers/` are empty dirs) — no token-issuance API.
- nginx rate-limits `location /login/` (docker/nginx/nginx.conf:79-86), but that path does not exist in Django, so the rate-limit zone is dead config guarding a non-existent route.

Consequence: a user can never obtain a `login_<token>` deep-link. The bot's claim handler will always answer "This login link is invalid, expired, or already used." The documented telegram-driven auth is non-functional in production. This also means the only path to create a `User` (which requires a `telegram_id` via the login flow) is blocked, so ad posting (`/post`) is unreachable for real users.

**Evidence:**
```
# Issuance sites in production code:
$ grep -rn "LoginToken.objects.create\|token_urlsafe\|os.urandom\|secrets\." src/backend/apps
  (no production hits; only apps/core/tests/test_sweep_commands.py:264 in tests)

# users URLs contain no login issuance:
apps/users/urls.py:
    path("consent/accept/", consent_accept, name="accept"),
    path("consent/decline/", consent_decline, name="decline"),

# Claim side exists and depends on a token that is never created:
src/telegram_bot/handlers/login.py:65-66
    raw_token = match.group(1)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
src/telegram_bot/handlers/login.py:69  claim_login_token(token_hash=..., telegram_id=...)

# nginx guards a route Django never serves:
docker/nginx/nginx.conf:79  location /login/ { limit_req zone=login_limit ... }
```

**Recommendation:** Implement the issuance half of the flow: a web (or API) endpoint that generates a cryptographically random 32-char token (`secrets.token_urlsafe`), stores only its `sha256` hash with `expires_at = now() + 5min`, and delivers the raw token to the user (via the website UI / a generated `t.me/<bot>?start=login_<token>` deep-link). This is the code-side gap; the claim side is already correct. Until issued, the `/login/` nginx rate-limit zone should either be removed or pointed at the real issuance route to avoid dead/misleading config. Effort: medium. Priority: mandatory (core auth is broken).

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Finding is technically correct. The login-token claim handler exists but token issuance is entirely missing from production code. nginx rate-limit config guards a non-existent route. This breaks the documented Telegram deep-link auth flow (US-S1). Per spec, login-token issuance is required - not deferred.
> - **Evidence verified:** grep for LoginToken.objects.create; apps/users/urls.py has no /login/; apps/api/views is empty; nginx.conf has rate-limit on non-existent route.

---

### EXT-002: Login-token claim has a TOCTOU race — two non-atomic queries allow double-claim under concurrency

| Field | Value |
|-------|-------|
| **ID** | EXT-002 |
| **Severity** | HIGH |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/telegram_bot/handlers/login.py |
| **Classification** | mandatory |

**Description:** `claim_login_token()` (lines 100-126) performs the claim as two separate queries: an `UPDATE ... .filter(token_hash=..., telegram_id__isnull=True, consumed_at__isnull=True, expires_at__gt=now()).update(telegram_id=...)` (returns row count), then a *separate* `LoginToken.objects.get(token_hash=token_hash)` to return the row. The phase requires "concurrent claim race → exactly one wins" and "cross-process claim atomic."

Problems:
1. The `get()` re-reads the row outside the UPDATE's transaction scope. Under `CONN_MAX_AGE=0` (per settings) each ORM call may open its own connection/transaction, so the UPDATE and GET are not guaranteed to be in the same transaction. A concurrent second claimant can pass the `telegram_id__isnull=True` filter in its own UPDATE (both UPDATEs can match the same row if scheduled between the first UPDATE and the row being re-read), and both callers receive a truthy `LoginToken` object — a replay of the same token by two users.
2. There is no `select_for_update()` / row lock, and no `hmac.compare_digest` constant-time guarantee on the DB filter (the docstring claims constant-time comparison via `hmac.compare_digest`, but the code never calls it — the comparison happens in SQL, not in Python). The docstring (lines 106-107) is therefore inaccurate.

This is a real correctness/security gap for the "exactly one wins" requirement, even though in practice the linear Telegram polling loop rarely races; cross-process (bot + future web claim) makes it reachable.

**Evidence:**
```
src/telegram_bot/handlers/login.py:109-124
    @sync_to_async
    def _claim() -> LoginToken | None:
        now = timezone.now()
        updated = LoginToken.objects.filter(
            token_hash=token_hash, telegram_id__isnull=True,
            consumed_at__isnull=True, expires_at__gt=now,
        ).update(telegram_id=telegram_id)          # UPDATE #1
        if updated == 0:
            return None
        return LoginToken.objects.get(token_hash=token_hash)  # GET #2 (separate query)
Docstring line 106 claims "constant-time comparison via hmac.compare_digest" but no such call exists in the function.
```

**Recommendation:** Use Django's `QuerySet.update(..., returning=True)` (Django 3.1+) to return the updated `LoginToken` row from a single atomic UPDATE, eliminating the separate `get()` call. Wrap the operation in `transaction.atomic()` for explicit transaction scoping under `CONN_MAX_AGE=0`. Remove the `hmac.compare_digest` claim from the docstring since the comparison is performed in SQL, not Python — the DB index already provides efficient equality lookup. Effort: small. Priority: recommended (hardening; close the race before a web claim side is added).

> **Validation Note:**
> - **Action:** validated
> - **Detail:** TOCTOU race exists because UPDATE and GET are separate queries. Under `CONN_MAX_AGE=0`, they can open separate connections/transactions. Docstring falsely claims `hmac.compare_digest` usage. Spec (US-S1) requires "atomic token, constant-time compare".
> - **Evidence verified:** login.py lines 100-126, docstring lines 3-5 and 103-107.

---

### EXT-003: Bot `translate_to_russian()` is a blocking network call on the event loop with no timeout, retry, or circuit-breaker

| Field | Value |
|-------|-------|
| **ID** | EXT-003 |
| **Severity** | HIGH |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/telegram_bot/handlers/ad_create.py |
| **Classification** | mandatory |

**Description:** On ad-submit confirmation, `translate_to_russian()` (ad_create.py:468-482) calls `deep_translator.GoogleTranslator(...).translate()` **synchronously inside an `async def`** that is `await`ed at ad_create.py:327. The synchronous HTTP request blocks the single aiogram event loop for its entire latency, freezing **all** in-flight Telegram updates for every user while one ad is translated. There is no `sync_to_async`/executor wrapper (unlike every other ORM helper in the file), no timeout, and no circuit-breaker. The only resilience is a bare `except Exception: return original` fallback.

This is the same class of defect as audit phase 01 ENT-004, still present in this phase's "translation client resilience" dimension. It also violates the project rule "all ORM/blocking calls wrapped in sync_to_async" — the translation is a blocking external IO left unwrapped, and it blocks the loop worse than a DB call because it is a network round-trip to an unofficial third-party endpoint.

**Evidence:**
```
ad_create.py:468-482
    async def translate_to_russian(title, description):
        from deep_translator import GoogleTranslator
        try:
            title_ru = GoogleTranslator(source="auto", target="ru").translate(title)
        except Exception:
            title_ru = title
        try:
            desc_ru  = GoogleTranslator(source="auto", target="ru").translate(description)
        except Exception:
            desc_ru  = description
        return title_ru, desc_ru
# awaited at ad_create.py:327: title_ru, desc_ru = await translate_to_russian(...)
No sync_to_async, no timeout, no backoff. Contrast with create_draft_ad, search_categories,
etc. which all use @sync_to_async.
```

**Recommendation:** Move the translation off the event loop (`sync_to_async` with a bounded timeout, or `asyncio.to_thread`), and add a hard timeout so a stalled translator cannot block the loop. Keep the original-text fallback (already present) but make translation best-effort and non-blocking to submission latency. Effort: small. Priority: recommended.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Synchronous HTTP call blocks the single aiogram event loop. No timeout or async wrapper. Contradicts project rule about wrapping blocking calls. In contrast, `query_translator.py` has 500ms timeout via ThreadPoolExecutor.
> - **Evidence verified:** ad_create.py lines 468-482, 327; compare with query_translator.py lines 38-40.

---

### EXT-004: Contact deep-link forwards the buyer's REAL name to the seller — violates the documented anonymous/PII design (Zone R2)

| Field | Value |
|-------|-------|
| **ID** | EXT-004 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/telegram_bot/handlers/contact.py |
| **Classification** | mandatory |

**Description:** The module docstring and Zone-R2 comments state the contact flow is "anonymous forwarding" with "no PII exposure" — the buyer's identity must not reach the seller. Yet `handle_contact()` builds the seller notification from the buyer's actual Telegram profile:

```
contact.py:89-97
    buyer_name = _get_buyer_display_name(message.from_user)   # first_name + last_name
    await bot.send_message(chat_id=seller_telegram_id, text=(
        f"...Покупатель: {buyer_name}\n..."                    # real name sent to seller
    ))
```

`_get_buyer_display_name` (lines 189-208) returns the buyer's real `first_name` and `last_name`. This PII is transmitted to a third party (the seller, via Telegram) on every contact request, directly contradicting the stated design ("anonymous buyer-seller communication", "without exposing Telegram username/ID"). The docstring even says it avoids exposing username/ID, but leaks the legal name instead.

**Evidence:**
```
contact.py module docstring (lines 1-6): "Handles buyer-to-seller contact ... without PII exposure."
contact.py:30-36 Zone R2 conditions (no PII noted, but implies anonymity)
contact.py:89  buyer_name = _get_buyer_display_name(message.from_user)
contact.py:94  f"Покупатель: {buyer_name}\n"   # real first/last name delivered to seller
```

**Recommendation:** Replace `buyer_name = _get_buyer_display_name(message.from_user)` with a fixed anonymous label (`"Покупатель"`/`"Buyer"`) in the seller notification. The buyer may voluntarily disclose their identity in the free-text message if they choose. Update the contact.py module docstring to reflect that anonymous forwarding is the default behavior and real names are no longer transmitted. (Secondary option: if the design intent is to share real names, update the docstring to remove anonymous/no-PII claims and add explicit consent wording). Effort: trivial. Priority: recommended (privacy/PII-to-third-party).

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Code contradicts its own docstring. The "no PII exposure" claim is violated by sending buyer's real name to seller. This should either be fixed to send anonymous label, or docstring updated to reflect actual behavior.
> - **Evidence verified:** contact.py lines 1-6, 89-94, 189-208.

---

### EXT-005: Translation client relies on Google's unofficial `translate.google.com/m` endpoint with no circuit-breaker — availability/cost risk

| Field | Value |
|-------|-------|
| **ID** | EXT-005 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/search/services/query_translator.py, src/telegram_bot/handlers/ad_create.py, pyproject.toml |
| **Classification** | advisory |

**Description:** Both translation paths use `deep_translator.GoogleTranslator`, which (per its own constants) hits the **unofficial** `https://translate.google.com/m` endpoint — not the Google Cloud Translation API. Web research confirms:
- The endpoint is undocumented and Google has repeatedly changed/blocked it; users report intermittent 500s and newly tightened rate limits (deep-translator issues #228, #263, #283).
- `deep_translator`'s own "free and unlimited" framing is misleading; the underlying endpoint's limits are undocumented and can be cut off at any time.
- The web search path (`query_translator.py`) adds a 500ms `ThreadPoolExecutor` timeout and fallback to the original query — good — but there is **no circuit-breaker, no retry/backoff with jitter, and no rate-limit awareness** (`TooManyRequests` is caught only as a generic `Exception` and silently falls back). The bot path (`ad_create.py`) has no timeout at all (see EXT-003).

For a production classifieds site, depending on an undocumented endpoint for two core flows (search recall and ad publishing) is an availability risk: when Google throttles the endpoint, search silently degrades and ad submission latency spikes. There is also no cost guardrail if the project later switches to the paid Cloud API (no per-day character budget).

**Evidence:**
```
query_translator.py:13,66  GoogleTranslator(source="bs", target="ru")  # unofficial endpoint
query_translator.py:18     TRANSLATION_TIMEOUT_SECONDS = 0.5
query_translator.py:44     except (TimeoutError, RequestException, Exception): fallback
# No circuit-breaker / backoff / quota tracking anywhere.
pyproject.toml:17          "deep-translator>=1.11.0"
# Web research: deep-translator uses `translate.google.com/m` (unofficial); Google has
# throttled it repeatedly; limits undocumented.
```

**Recommendation:** Add a lightweight in-process circuit-breaker in `query_translator.py` — maintain a failure counter with a cooldown window (e.g., after N consecutive failures, short-circuit to original-query fallback for T seconds and log a warning). This avoids adding the `pybreaker` dependency while providing basic resilience. Also add a hard timeout to `ad_create.py`'s `translate_to_russian()` using `sync_to_async` with `asyncio.wait_for`. Defer Google Cloud Translation API integration and quota tracking to a later hardening pass. Effort: small. Priority: recommended.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Unofficial endpoint dependency with incomplete resilience. Web path has timeout, bot path does not. No circuit-breaker or rate-limit awareness. Low ROI for immediate fix but valid architecture risk.
> - **Evidence verified:** pyproject.toml:17, query_translator.py:18,44-48, ad_create.py:468-482.

---

### EXT-006: nginx terminates TLS but sets no HSTS header; proxy security header set is incomplete

| Field | Value |
|-------|-------|
| **ID** | EXT-006 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | docker/nginx/nginx.conf |
| **Classification** | advisory |

**Description:** The phase requires "HSTS, CSP, nosniff, frame-deny at the proxy." The nginx config (`nginx.conf`) serves HTTPS and applies `X-Content-Type-Options nosniff`, `X-Frame-Options DENY`, and a strict CSP **only inside `location /media/`** (lines 66-69). At the server level / for the app proxy (`location /`, `/login/`, `/search/`) there is:
- **No `Strict-Transport-Security` (HSTS)** header anywhere — the phase explicitly lists HSTS as required and the codebase grep for HSTS returns only the phase doc, not nginx.
- No `X-Content-Type-Options`, `X-Frame-Options`, or CSP on HTML responses.
- Django's `SecurityMiddleware` would add some of these only if `SECURE_HSTS_*` settings are configured — but `base.py`/`prod.py` set `SECURE_SSL_REDIRECT` and secure cookies yet **never set `SECURE_HSTS_SECONDS`**, so Django emits no HSTS either.

Result: browsers are not instructed to pin HTTPS; users hitting `http://` are 301-redirected but remain vulnerable to SSL-strip on first contact, and HTML responses lack the defense-in-depth headers. The media-only header placement also means the documented "secure headers at the proxy" guarantee is only partially met.

**Evidence:**
```
nginx.conf:33-106  server { listen 443 ssl; ... }
nginx.conf:66-69  add_header X-Content-Type-Options nosniff ... (MEDIA location ONLY)
# No add_header Strict-Transport-Security anywhere in the file.
# No server-level X-Frame-Options / CSP for location /

base.py:47-52  SESSION_COOKIE_SECURE/CSRF_COOKIE_SECURE/SECURE_SSL_REDIRECT set;
               SECURE_HSTS_SECONDS NOT set (grep: no HSTS in settings).
prod.py:8-17   TLS-ready settings; still no SECURE_HSTS_SECONDS.
```

**Recommendation:** Add a server-level `add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;` in nginx (and/or set `SECURE_HSTS_SECONDS` in Django), plus `X-Content-Type-Options nosniff` and `X-Frame-Options DENY` at the server level so they apply to HTML responses, not just `/media/`. Keep the strict media CSP as-is. Effort: trivial. Priority: recommended.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** HSTS missing. Security headers confined to `/media/` location, not applied to main site. Phase requirements explicitly list HSTS as required.
> - **Evidence verified:** nginx.conf:66-69; base.py:47-52; prod.py: no HSTS settings.

---

### EXT-007: Bot `save_photo()` performs a blocking filesystem write on the event loop

| Field | Value |
|-------|-------|
| **ID** | EXT-007 |
| **Severity** | MEDIUM |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/telegram_bot/handlers/ad_create.py |
| **Classification** | mandatory |

**Description:** `save_photo()` (`ad_create.py:431-437`) is an `async def` that does a synchronous `os.makedirs` + `open(...).write()` directly on the event loop and is `await`ed at `ad_create.py:282` during the photo step. Like EXT-003, this blocks the single loop for all users during the disk write. Every other ORM helper in the file uses `sync_to_async`, but the media write is left unwrapped. On slow/network-backed volumes (the compose mounts a Docker `media_volume`), this stalls all concurrent updates.

(Reported as ENT-003 in phase 01; still present and in-scope here as the async↔sync bridge gap for external media storage.)

**Evidence:**
```
ad_create.py:431-437
    async def save_photo(storage_key, photo_bytes):
        media_path = os.path.join(settings.MEDIA_ROOT, storage_key)
        os.makedirs(os.path.dirname(media_path), exist_ok=True)
        with open(media_path, "wb") as f:
            f.write(photo_bytes)         # blocking, runs on event loop
# awaited at ad_create.py:282  await save_photo(storage_key, photo_bytes)
```

**Recommendation:** Wrap the write in `sync_to_async` / `asyncio.to_thread` so it runs off the event loop, consistent with the other helpers. Effort: trivial. Priority: recommended.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Blocking filesystem write on event loop. Same pattern as EXT-003. Should use `sync_to_async` or `asyncio.to_thread`.
> - **Evidence verified:** ad_create.py:431-437, 282.

---

### EXT-008: Base `web` service has no restart policy — split-brain if the website crashes while the bot keeps running

| Field | Value |
|-------|-------|
| **ID** | EXT-008 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | docker-compose.yml |
| **Classification** | advisory |

**Description:** In `docker-compose.yml`, `bot` and `nginx` declare `restart: unless-stopped`, but the `web` (gunicorn) service has **no** `restart` key. The production override (`docker-compose.prod.yml:6-7`) adds it, so this is base/dev-only — but base compose is what `docker compose up` runs by default and is the audit's runtime model. If `web` crashes or is OOM-killed, Docker will not restart it and the site goes down silently while the bot keeps accepting `/post` flows that the website cannot serve.

(First reported as ENT-005 in phase 01; still present in base compose.)

**Evidence:**
```
docker-compose.yml:42-54  web: { build, command: gunicorn ... }  # no `restart:`
docker-compose.yml:74      bot:  restart: unless-stopped
docker-compose.prod.yml:6  web:  restart: unless-stopped  # only in prod override
```

**Recommendation:** Give `web` an explicit `restart: unless-stopped` (or `on-failure`) in the base `docker-compose.yml` so web and bot share consistent restart semantics. Effort: trivial. Priority: recommended.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Base compose lacks restart policy on web service. Production override adds it but default `docker compose up` runs without restart. Operational risk: web crash → site down while bot still accepts /post flows.
> - **Evidence verified:** docker-compose.yml:42-58, 74, 86; docker-compose.prod.yml:6-7.

---

### EXT-009: Ad content (title/description) is egressed to Google Translate on every submission — undocumented PII-to-third-party exposure

| Field | Value |
|-------|-------|
| **ID** | EXT-009 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/telegram_bot/handlers/ad_create.py, src/backend/apps/search/services/query_translator.py |
| **Classification** | advisory |

**Description:** The phase requires "NO PII sent to the third party" for the translation client. User-generated ad text (title + description, up to 2000 chars) is sent to Google's translation endpoint on every `/post` confirmation (`ad_create.py:327-329` → `translate_to_russian`). Search queries are also sent (`query_translator.py:50`). This is not *identity* PII, but it is user content leaving the trust boundary to an undocumented third-party endpoint with no documented data-handling/retention stance. There is no privacy notice, no opt-out, and no record that this egress occurs. For a GDPR-context project (the codebase has full consent machinery in `apps/users`), sending user content to an external translator without disclosure is a consistency gap.

**Evidence:**
```
ad_create.py:327-329  title_ru, desc_ru = await translate_to_russian(data["title"], data["description"])
ad_create.py:468-482  GoogleTranslator(...).translate(title/description)  # egress to Google
query_translator.py:50  translated_query = translate_query_bs_to_ru(query)  # search egress
# No privacy notice / consent linkage for translation egress anywhere.
```

**Recommendation:** Add a short data-flow note to the privacy/consent documentation stating that ad title/description and search queries are sent to Google Translate for language normalization, that this is best-effort and non-identifying content, and that users may disable auto-translation via a settings toggle in a future release. No code change required for MVP — treat as disclosed-by-default. Effort: small. Priority: recommended.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** User content sent to external translator without privacy notice. Valid concern for GDPR context with existing consent machinery.
> - **Evidence verified:** ad_create.py:327,468-482; query_translator.py:50.

---

### EXT-010: No integration-health observability for external dependencies (bot, translator)

| Field | Value |
|-------|-------|
| **ID** | EXT-010 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/telegram_bot/handlers/ad_create.py, src/backend/apps/search/services/query_translator.py |
| **Classification** | advisory |

**Description:** The phase lists "no integration-health metrics" and "no alerting on repeated translation failures" as LOW items. Currently:
- Translation failures are logged at `warning`/`info` (`query_translator.py:44-49`) but there is no counter/metric, so a sustained translator outage is invisible to operators.
- The bot has no healthcheck/heartbeat exposed; `docker-compose.yml` `bot` service has no `healthcheck`, unlike `db` (which has `pg_isready`). If the bot process hangs on a blocked call (EXT-003/EXT-007) it is not detected by the orchestrator.
- No graceful-degradation signal is emitted when translation is in fallback mode.

**Evidence:**
```
query_translator.py:44  logger.warning(f"Translation failed for query '{query}': {e}")
query_translator.py:48  logger.info(f"Translation fallback: returning original query '{query}'")
# No metrics/alerting; bot service in compose has no healthcheck block.
```

**Recommendation:** Add a lightweight failure counter (e.g. increment a Prometheus/`statsd` metric or a process-level counter logged periodically) for translation failures, and add a bot `healthcheck` (e.g. a periodic log line or a liveness file) so the orchestrator can detect a stalled loop. Effort: small. Priority: recommended.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Translation failures logged but no metrics. Bot has no healthcheck. Sustained translator outage would be invisible. Valid improvement opportunity.
> - **Evidence verified:** query_translator.py:44-48; docker-compose.yml (no healthcheck on bot).

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 10 | All findings validated as correct |
| Reclassified | 0 | — |
| Merged | 0 | — |
| Rejected | 0 | — |

### Mandatory Fixes

- **EXT-001** (CRITICAL) — Login-token issuance + delivery is entirely missing; the documented telegram deep-link auth is non-functional in production. Must implement issuance endpoint and token delivery mechanism.
- **EXT-002** (HIGH) — Login-token claim has TOCTOU race (filter-then-get, no row lock); double-claim possible under concurrency; docstring falsely claims constant-time comparison.
- **EXT-003** (HIGH) — `translate_to_russian()` is a blocking network call on the bot event loop (no timeout/executor/circuit-breaker).
- **EXT-004** (HIGH) — Contact deep-link sends the buyer's real name to the seller, contradicting the documented anonymous/PII-free design.
- **EXT-007** (MEDIUM) — `save_photo()` performs a blocking filesystem write on the event loop.

### Advisory Recommendations

- **EXT-005** (MEDIUM) — Translation depends on Google's unofficial endpoint with no circuit-breaker/backoff/quota awareness; availability + cost risk.
- **EXT-006** (MEDIUM) — nginx sets no HSTS and applies security headers only to `/media/`; HTML responses lack HSTS/nosniff/frame-deny.
- **EXT-008** (MEDIUM) — Base `web` service lacks a `restart` policy (split-brain vs bot).
- **EXT-009** (LOW) — Ad/search content egressed to Google Translate undocumented in privacy/consent material.
- **EXT-010** (LOW) — No integration-health metrics/alerting; bot has no healthcheck.

### Risk Assessment

| Risk Category | Findings |
|---------------|----------|
| **Breaking Change Risk** | EXT-001 (core auth broken), EXT-002 (race condition fix may affect claim logic) |
| **Operational Risk** | EXT-003, EXT-007 (event loop blocking), EXT-008 (split-brain on crash) |
| **Privacy/Compliance Risk** | EXT-004 (PII exposure), EXT-009 (undisclosed content egress) |
| **Security Risk** | EXT-006 (missing HSTS), EXT-002 (race condition) |

---

## Architectural Notes

### Dependency Chain

The findings reveal a dependency chain:
1. **EXT-001** must be fixed before any real user can use `/post` (login required)
2. **EXT-003/EXT-007** are independent runtime fixes (can be done in parallel)
3. **EXT-002** should be addressed before adding web-based token claim (future work)
4. **EXT-004/EXT-009** are privacy-related and should align with consent flow (US-A8)

### Code Quality Patterns

- The codebase consistently uses `@sync_to_async` for ORM operations but inconsistently applies it to blocking I/O (EXT-003, EXT-007)
- nginx configuration shows security awareness (media hardening) but incomplete server-level policy (EXT-006)
- Docker compose shows operational maturity but inconsistent service hardening (EXT-008)