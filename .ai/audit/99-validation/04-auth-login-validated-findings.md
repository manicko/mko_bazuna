# Phase 04 Audit Findings — Authentication & Login Token Security (VALIDATED)

**Executor:** audit-executor
**Template:** `.kilo/commands/audit/phases/04-audit-auth-login.md`
**Status:** complete
**Validated:** yes

> **Validator scope note:** This report validates the findings in `04-auth-login/findings.md` only, against the current working tree. Each finding was independently reproduced via targeted `grep` + exact source-line reads (not re-running the runtime test suites — no test DB was stood up in this pass; static evidence is the basis). No source code was modified. Line references in the original findings were spot-checked at the cited offsets; all confirmed live (see per-finding Validation Notes).

Audit scope: security correctness of the login-token mechanism (issuance → claim → consumption → session) across the web (`apps/users/views/consent.py`) and Telegram bot (`telegram_bot/handlers/login.py`) processes sharing the `LoginToken` model, one PostgreSQL 18 DB.

## Findings

### AU-001: Raw login token transmitted in GET query string for web polling

| Field | Value |
|-------|-------|
| **ID** | AU-001 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/users/views/consent.py` (`login_status`), `src/backend/templates/users/login_issue.html` |
| **Classification** | mandatory (security) |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Reproduced verbatim. `consent.py:374` → `raw_token = request.GET.get("token", "")` (confirmed at line 374). `login_issue.html:38` → `var pollUrl = "{% url 'consent:login_status' %}?token={{ raw_token }}";` (confirmed at line 38). `login_issue.html:45-46,63` → `setInterval(..., 3000)` with `fetch(pollUrl, { cache: "no-store" })`, i.e. the raw token is re-sent in the URL every 3 s; the 5-min TTL (set at `consent.py:303`) yields ~100 requests, so ~100 poll-URLs carrying `?token=<raw>` would be emitted over the window — the math in the finding is correct. `users/urls.py:20` → `path("login/status/", login_status, name="login_status")` (confirmed, no `@require_POST`, no `csrf_exempt`); `login_status` is decorated only with `@never_cache` (`consent.py:356`), **not** `@require_POST`, so the state-changing consumption is exposed as an unguarded `GET` — confirmed. The `compare_digest` mitigation (`consent.py:387`: `hmac.compare_digest(token.token_hash, token_hash)`) is correct and is **not** disputed by this finding (constant-time comparison prevents timing oracles on the hash lookup; the leak vector is the URL, not the comparison). **Evidence-quality note (cosmetic, not a validity issue):** the finding's parenthetical "the view is not `@never_cache`+`@require_POST`" is slightly imprecise — `@never_cache` *is* present (`consent.py:356`); the accurate statement is that `@require_POST` is **absent**, which is what makes the consumption a state-changing GET. The substance of the finding is unaffected. The `UPDATE…RETURNING` cited in R3 is the *bot* side (`login.py:119-131`) — correct; the *web* side uses an optimistic conditional `UPDATE` (`consent.py:401-406`) with `consumed_at IS NULL` guard and `updated == 0` re-check (`consent.py:408-410`) — also correct. Issuance `GET /login/issue/` (`login_issue` is `@never_cache`, no `@require_GET`, but is a pure read/issuance and is explicitly *not* part of this finding per the recommendation) and the Telegram `t.me` deep-link carry the raw token by design into the browser/Telegram context, not server access logs.
> - **See also:** R1/R5 (no raw token in logs — issuance uses hash-prefix `token_hash[:8]` only, `consent.py:309`; bot logs no raw token, grepped) and R3 (atomic claim).

**Description:** The web token-consumption step is a state-changing operation exposed as a `GET` endpoint that receives the raw token in the URL query string. The client-side poll URL is built as:

```js
var pollUrl = "{% url 'consent:login_status' %}?token={{ raw_token }}";
```

`login_status` reads the secret from `request.GET.get("token", "")` (`consent.py:374`), and the polling `fetch` re-sends it every 3 s for up to 5 min (~100 requests).

**Consequence:**
1. **Access-log exposure (CRITICAL-class):** every poll request URL — including `?token=<raw_token>` — is recorded by the HTTP server / reverse-proxy access log. The raw login token therefore lives in server logs ~100 times over the 5-min TTL. An attacker with read access to access logs during that window can steal a live, bot-claimed token and replay it to `/login/status/?token=<stolen>` (the `UPDATE … consumed_at IS NULL` guard loses the race if the attacker is faster), establishing a session as the victim — full account takeover.
2. **Login-CSRF surface (H):** consumption is a state-changing `GET` with no CSRF token. Per OWASP, `GET` requests that mutate server state are vulnerable to Cross-Site Request Forgery. Because the session cookie is `SameSite=Lax`, subresource-based CSRF is blocked, but a top-level navigation to a crafted `/login/status/?token=<attacker-claimed-token>` (victim must click) binds the victim's session to the *attacker's* account.

**Evidence:**
- `src/backend/templates/users/login_issue.html:38` — `pollUrl` built with `?token={{ raw_token }}` in GET.
- `src/backend/apps/users/views/consent.py:374` — `raw_token = request.GET.get("token", "")`.
- `src/backend/apps/users/urls.py:20` — `path("login/status/", login_status, …)`; the view is not `@require_POST` (only `@never_cache` at `consent.py:356`).
- Phase check (e) "Token not in logs / referrer / URLs" is violated by the poll URL.

**Recommendation:** Switch consumption to `POST` with the token placed in the request body (never the URL), and require a Django CSRF token in the same origin. This removes the token from access logs and eliminates the state-changing-GET CSRF vector in one change. The issuance `GET /login/issue/` and the Telegram `t.me` deep-link legitimately carry the token to the client by design (accepted deep-link zone) and are *not* part of this finding. **Effort: small.**

**Doc-update note:** `docs/01-spec/spec-index.md:75` lists `hmac.compare_digest` but does not state the poll transport; the spec should mandate POST-body token transport for consumption.

---

### AU-002: Token entropy below the phase's ~256-bit guideline (192 bits)

| Field | Value |
|-------|-------|
| **ID** | AU-002 |
| **Severity** | LOW |
| **Type** | DOC-UPDATE |
| **Affected Modules** | `src/backend/apps/users/views/consent.py:298` |
| **Classification** | advisory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Reproduced verbatim. `consent.py:298` → `raw_token = secrets.token_urlsafe(24)` (confirmed at line 298). `secrets.token_urlsafe(24)` = 24 random bytes = 192 bits, rendered as exactly 32 URL-safe chars (verified: ceil(24 × 4/3) = 32). `telegram_bot/handlers/login.py:27` → `LOGIN_PATTERN = re.compile(r"^login_([A-Za-z0-9_-]{32})$")` (confirmed at line 27; the `{32}` cap matches the 32-char generator output — a 256-bit token via `token_urlsafe(32)` would render 43 chars and would **not** match this regex, so the finding's option-b note about updating the regex to `{43}` is accurate). `docs/01-spec/spec-index.md:75` → "32-char" + `hmac.compare_digest` (confirmed). `docs/02-database/db-schema.md:84` → "token_hash (CHAR(64) UNIQUE, indexed) # SHA-256 of raw 32-char URL-safe token; raw token NEVER stored" (confirmed; SHA-256 hex = 64 chars, consistent with 192-bit/32-char raw input). The classification as `DOC-UPDATE` (not a vulnerability) is correct and the consequence reasoning (192 bits exceeds NIST SP 800-63B's 128-bit authenticator minimum and is unguessable for a 5-min rate-limited token) is sound. The R1 test-name references (`test_login_issue_stores_token_hash_not_raw`, `test_stored_hash_is_sha256_not_raw`) are corroborated by the hash-only-storage design (`consent.py:299` compute, `consent.py:301-304` persist only `token_hash`).
> - **See also:** R1 (hash-only storage) and dimension (e).

**Description:** `raw_token = secrets.token_urlsafe(24)` produces 24 bytes = **192 bits** of entropy, rendered as 32 URL-safe chars. This matches the bot regex `LOGIN_PATTERN = re.compile(r"^login_([A-Za-z0-9_-]{32})$")` (`telegram_bot/handlers/login.py:27`) and the documented "32-char URL-safe token" (`docs/01-spec/spec-index.md:75`, `docs/02-database/db-schema.md:84`). However, the phase checkpoint requires `>= ~256 bits`.

**Consequence:** 192 bits is cryptographically strong (exceeds NIST SP 800-63B's 128-bit authenticator minimum and is unguessable for a rate-limited 5-min token) — there is **no practical brute-force risk**. The deviation is a spec/checkpoint tension rather than a vulnerability: the phase's ~256-bit target is stricter than the 32-char design the bot regex enforces.

**Evidence:**
- `consent.py:298` — `secrets.token_urlsafe(24)` → 24 bytes → 192 bits → 32 chars.
- `telegram_bot/handlers/login.py:27` — regex `{32}` caps the token at 32 chars (a 256-bit token would need `{43}` and would not match).
- R1 verified: only the SHA-256 hash is stored (`test_login_issue_stores_token_hash_not_raw`, `test_stored_hash_is_sha256_not_raw`).

**Recommendation:** Decide and document one direction: (a) accept 192-bit/32-char as sufficient (update the phase checkpoint and docs to state `32-char, ~192-bit CSPRNG, rate-limited 5-min TTL`), or (b) upgrade to `secrets.token_urlsafe(32)` for 256-bit entropy and update the bot regex to `{43}` + docs + tests. **Effort: small (docs) / medium (option b).**

---

## Evidence Mapping (R1–R6)

| Row | Check | Result | Evidence |
|-----|-------|--------|----------|
| R1 | Raw token never in response/storage/logs | PASS | Hash stored only (`consent.py:299-304`, `models.py:162-166`); logger emits `token_hash[:8]` only (`consent.py:309`); bot logs no raw token (`login.py`, grep). Tests: `test_login_issue_stores_token_hash_not_raw`, `test_stored_hash_is_sha256_not_raw`. |
| R2 | Invalid/expired/consumed rejected | PASS | 410 for nonexistent/mismatch/expired/consumed/banned (`consent.py:384,388,391,410,423,430`); bot rejects expired/claimed/unknown (`login.py` reject path + `TestTokenRejection`). 8 tests green. |
| R3 | Concurrent double-claim → one winner | PASS | Bot: atomic `UPDATE … RETURNING` under row lock, `WHERE telegram_id IS NULL AND consumed_at IS NULL AND expires_at > %s` (`login.py:119-131`); web: optimistic `UPDATE … consumed_at__isnull=True`, re-checks `updated==0` (`consent.py:401-410`). Tests: `test_reclaim_blocked`, `test_consumed_token_cannot_be_reused`. |
| R4 | No `==` on secrets; constant-time used | PASS | Only secret comparison is `hmac.compare_digest(token.token_hash, token_hash)` (`consent.py:387`); grep for `token_hash ==`/`== token_hash`/`raw_token ==` across `src/` returns **only test assertions**, no production `==`. Bot uses indexed DB lookup (no byte-wise compare). |
| R5 | No token logging/leak in messages | PASS (app logs) | No production logger emits `raw_token`/`deep_link` token; all auth logs use hash-prefix + `mask_telegram_id` (`consent.py:309,412,420,427,441`). *Caveat:* token present in GET poll URL — see AU-001. |
| R6 | Lint + type-check + login tests | PASS | `ruff check` 5 files: **All checks passed**. `basedpyright` 4 files: **0 errors, 0 warnings, 0 notes**. `pytest`: web `test_login.py` **22 passed**; bot `test_login.py` **6 passed**. |

## Checklist Coverage (dimensions a–f)

| Dimension | Result | Notes |
|-----------|--------|-------|
| (a) Hash-only storage | PASS | `token_hash CHAR(64) UNIQUE+indexed`; no raw column; raw never logged. |
| (b) Constant-time comparison | PASS | `hmac.compare_digest` at `consent.py:387`; hash pre-computed. |
| (c) Atomic/idempotent claim | PASS | Bot single-statement `UPDATE…RETURNING`; web conditional `UPDATE` with `consumed_at__isnull`. |
| (d) Expiry & replay | PASS | Server-side `expires_at`/`consumed_at` in both `WHERE` clauses; `cleanup_login_tokens` sweep wired hourly via `docker/entrypoint-scheduler.sh:33` (advisory lock 5). |
| (e) Token generation | PASS (with note) | CSPRNG via `secrets.token_urlsafe`; 192-bit/32-char; URL-safe. See AU-002 (below ~256-bit target). |
| (f) Deep-link/QR + FSM + session | PARTIAL | Deep-link unguessable, no PII; FSM binds `telegram_id=message.from_user.id` (bot); cookie `Secure+HttpOnly+SameSite=Lax` (`base.py:77-79`); `auth_login` cycles session key. **Defect: token in GET poll URL — AU-001.** |

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 1 |
| MEDIUM | 0 |
| LOW | 1 |

## Mandatory Fixes

- **AU-001** — Move login-token consumption from `GET ?token=` to `POST` with the token in the body plus a CSRF token (removes access-log exposure and login-CSRF). Affects `consent.login_status`, `login_issue.html` JS, `users.urls`.

## Advisory Recommendations

- **AU-002** — Align the entropy target with the implementation (192-bit, 32-char) in docs, or upgrade to 256-bit and update the bot regex `{32}` → `{43}` + docs + tests.

## Doc Updates Needed

- **AU-001** — `docs/01-spec/spec-index.md:75` & `docs/02-database/db-schema.md:84`: state that consumption MUST use POST-body transport (not URL query), to match the implemented deep-link design.
- **AU-002** — `docs/01-spec/spec-index.md:75`, `docs/02-database/db-schema.md:84`, `docs/01-spec/technical-specification.md:141`: state the exact entropy (192-bit / 32-char) or upgrade to 256-bit.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 2 | AU-001, AU-002 |
| Reclassified | 0 | — |
| Merged | 0 | — |
| Rejected | 0 | — |

### Rejected Findings

_None._ Both findings were verified against the current working tree and found technically correct, currently applicable, and architecturally sound. No stale, duplicate, or low-ROI findings.

### Merged Findings

_None._ Both findings target distinct, non-overlapping root causes: AU-001 is the GET-token-transport / state-changing-GET-CSRF defect; AU-002 is a spec/doctrine entropy-target tension. No cross-finding overlap.

### Reclassified Findings

_None._ AU-001 (`SPEC-DEVIATION`, mandatory) and AU-002 (`DOC-UPDATE`, advisory) were both retained as-is; the auditor's type assignments hold under validation. Specifically, AU-002 is correctly a `DOC-UPDATE`: 192-bit/32-char entropy is cryptographically strong (above the NIST 128-bit floor) and is *enforced* by the bot regex, so the deviation is a checkpoint-vs-implementation tension, not a vulnerability — code should not be distorted for it (per project rule #2).

### Rollout Safety

- **AU-001 (mandatory, HIGH):** Requires a coordinated three-point change — (1) `login_status` view (`consent.py:356-444`) gains `@require_POST` (and CSRF middleware already in place via `base.py:80-82`), (2) `login_issue.html` JS (`consent.py:45-64`) switches `fetch` from GET-with-query-token to POST-with-body-token and must supply a `X-CSRFToken` header, and (3) the URL path itself is unchanged (`/login/status/` → `users.urls:20`). **Rollout hazard if deployed non-atomically:** if the view flips to `@require_POST` while the template JS still issues a GET-poll, the browser receives `403 CSRF`/`405 Method Not Allowed` and login silently hangs. The issuance endpoint `GET /login/issue/` and the bot deep-link legitimately remain GET (not in scope). No circular dependencies; no hidden consumers of the GET form (the deep-link originates browser-side). **Safe only if the view + template change is deployed as one unit.** No backward-compat concern (the old GET behavior has no legitimate consumers once the JS is updated).
- **AU-002 (advisory, docs / small code):** Option (a) is docs-only — zero rollout risk. Option (b) touches `consent.py:298` (`token_urlsafe(32)`), `login.py:27` (`{32}`→`{43}`), the `LoginToken` model/regex tests, and docs — must be applied together so the bot's regex still matches the longer token, or bot-side claims break for in-flight tokens. **Small, isolated, no cross-module dependency risk.**
- **No unsafe insertion points.** Both fixes are additive (view decorator + POST body) rather than rewrites of the atomic-claim logic (R3 `UPDATE…RETURNING` / conditional `UPDATE` is preserved verbatim).

### Execution Validation

| Finding | Targets still exist? | Static verified? | Ready for execution |
|---------|----------------------|------------------|---------------------|
| AU-001 | Yes — `consent.login_status` (`consent.py:356-444`), `login_issue.html` JS (`login_issue.html:36-64`), `users.urls:20` | Yes (grep + file reads; `@never_cache` present, `@require_POST` absent; `request.GET.get("token", "")` at `consent.py:374`) | Yes — small (note atomicity requirement above) |
| AU-002 | Yes — `consent.py:298` (`secrets.token_urlsafe(24)`), `login.py:27` (`LOGIN_PATTERN` `{32}`), `docs/01-spec/spec-index.md:75`, `docs/02-database/db-schema.md:84` | Yes (grep + file reads; 24 bytes→192 bits→32 chars; SHA-256 hex=64 chars) | Yes — trivial (docs) / small (option b) |

### Warnings

- **AU-001 rollout coupling:** The web-poll `fetch` (template JS) and the consumption view are a single logical unit. Splitting their deployment (view to POST first, JS second, or vice versa) yields a window where login is broken for all users. Execution must treat `consent.py` + `login_issue.html` as one atomic change. This is the only non-trivial operational risk.
- **Evidence-quality (cosmetic):** AU-001's parenthetical "the view is not `@never_cache`+`@require_POST`" is imprecise — `@never_cache` *is* applied at `consent.py:356`; only `@require_post`/`@csrf_exempt` is absent. The finding's substance (state-changing GET with raw token in the URL) is fully correct; the decorator claim is merely over-broad. No reclassification warranted.
- **AU-002 option (b) regex coupling:** bumping to 256-bit requires the bot regex `login.py:27` to move from `{32}` to `{43}` *and* the deep-link generator (`consent.py:307`) emits the raw token into `?start=login_<raw_token>` — both ends must change together, but they are the same code path the regex already governs, so the coupling is local and observable in tests. No silent breakage beyond the brief in-flight-token window.

### Required Fixes

1. **AU-001 (mandatory):** Deploy together as one change — (a) add `@require_POST` to `login_status` in `consent.py` (CSRF middleware already enforces the token at `base.py:80-82`); (b) change the token read from `request.GET.get("token", "")` (`consent.py:374`) to a POST-body read (e.g. `request.POST.get("token", "")`); (c) update `login_issue.html` JS to `fetch(pollUrl, {method:"POST", body: new URLSearchParams({token: raw_token}), headers: {"X-CSRFToken": csrftoken}})` and drop the token from the URL. This removes access-log exposure and the state-changing-GET CSRF vector.

### Advisory Recommendations

1. **AU-002:** Either (a) update `docs/01-spec/spec-index.md:75`, `docs/02-database/db-schema.md:84`, and the phase checkpoint to state "32-char, ~192-bit CSPRNG, rate-limited 5-min TTL" — trivial, docs-only; or (b) raise `consent.py:298` to `secrets.token_urlsafe(32)` (256-bit), move `login.py:27` regex to `{43}`, and update docs + token tests — small/medium; deploy as one unit.

*Findings validated incrementally; static-only evidence used (runtime race verification relied on code trace of `UPDATE…RETURNING` row-lock + conditional web `UPDATE`, both confirmed live at `telegram_bot/handlers/login.py:119-131` and `apps/users/views/consent.py:401-410`).*
