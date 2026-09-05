---
name: 04-auth-login-findings
phase: 04-auth-login
template: .ai/audit/templates/audit-findings.md
executor: audit-executor
status: complete
validated: yes
---

# Phase 04 Audit Findings — Authentication & Login Token Security

**Executor:** audit-executor
**Phase template:** `.kilo/commands/audit/phases/04-audit-auth-login.md`
**Scope:** security correctness of the login-token mechanism (issuance → claim → consumption → session) across the web (`consent.py`) and Telegram bot (`handlers/login.py`) processes sharing the `LoginToken` model.

## Finding Inventory (problems-only)

Two deviations found. All other checklist rows pass at runtime.

### AU-001: Raw login token transmitted in GET query string for web polling

| Field | Value |
|-------|-------|
| **ID** | AU-001 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/users/views/consent.py` (`login_status`), `src/backend/templates/users/login_issue.html` |
| **Classification** | mandatory (security) |
| **Phase checks** | (e) No token leakage · R5 token-leak scan · (f) no session fixation / secure cookie |

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
- `src/backend/apps/users/urls.py:20` — `path("login/status/", login_status, …)`; the view is not `@never_cache`+`@require_POST` nor CSRF-exempt-guarded for POST.
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
| **Phase checks** | (e) Sufficient entropy `>= ~256 bits` |

**Description:** `raw_token = secrets.token_urlsafe(24)` produces 24 bytes = **192 bits** of entropy, rendered as 32 URL-safe chars. This matches the bot regex `LOGIN_PATTERN = re.compile(r"^login_([A-Za-z0-9_-]{32})$")` (`telegram_bot/handlers/login.py:27`) and the documented "32-char URL-safe token" (`docs/01-spec/spec-index.md:75`, `docs/02-database/db-schema.md:84`). However, the phase checkpoint requires `>= ~256 bits`.

**Consequence:** 192 bits is cryptographically strong (exceeds NIST SP 800-63B's 128-bit authenticator minimum and is unguessable for a rate-limited 5-min token) — there is **no practical brute-force risk**. The deviation is a spec/checkpoint tension rather than a vulnerability: the phase's ~256-bit target is stricter than the 32-char design the bot regex enforces.

**Evidence:**
- `consent.py:298` — `secrets.token_urlsafe(24)` → 24 bytes → 192 bits → 32 chars.
- `telegram_bot/handlers/login.py:27` — regex `{32}` caps the token at 1024 bits max but the generator emits 32 chars.
- R1 verified: only the SHA-256 hash is stored (`test_login_issue_stores_token_hash_not_raw`, `test_stored_hash_is_sha256_not_raw`).

**Recommendation:** Decide and document one direction: (a) accept 192-bit/32-char as sufficient (update the phase checkpoint and docs to state `32-char, ~192-bit CSPRNG, rate-limited 5-min TTL`), or (b) upgrade to `secrets.token_urlsafe(32)` for 256-bit entropy and update the bot regex to `{43}` + docs + tests. **Effort: small (docs) / medium (option b).**

---

## Evidence Mapping (R1–R6)

| Row | Check | Result | Evidence |
|-----|-------|--------|----------|
| R1 | Raw token never in response/storage/logs | PASS | Hash stored only (`consent.py:299-302`, `models.py:162-166`); logger emits `token_hash[:8]` only (`consent.py:309`); bot logs no raw token (`login.py`, grep). Tests: `test_login_issue_stores_token_hash_not_raw`, `test_stored_hash_is_sha256_not_raw`. |
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

*Findings written incrementally; surface linted with `ruff` and typed with `basedpyright` (0 errors); auth/login test suites run green inside the `mko-bazuna-test` Docker compose test DB (PostgreSQL 18, healthy). Static-only for runtime race verification (true concurrent claims verified by code trace of `UPDATE…RETURNING` row-lock + conditional web `UPDATE`).*
