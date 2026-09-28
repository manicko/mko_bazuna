---
# Report metadata — fill once per phase report.
phase: "04"
phase_name: "Authentication & Login Token Security"
date: "2026-09-28"
auditor: "Executor (subagent)"
validator: ""
mode: "problems-only"
id_prefix: "AUT"
report_status: "draft"
severity_taxonomy: ".kilo/commands/audit/phases/04-audit-auth-login.md#severity-taxonomy"
---

# Audit Findings — Authentication & Login Token Security

## Executive Summary

Sellers log in to the website by scanning a Telegram deep link; a short-lived one-time
code is created on the site, confirmed inside Telegram, and then exchanged for a
website session. The code itself is handled well: it is generated with a proper
cryptographic random source, only a one-way fingerprint of it is stored, it can be used
only once, it expires after five minutes, and it is never written to logs. The problems
found are in what happens *around* that code. The code is not tied to the browser that
asked for it, which allows a person to trick a buyer into confirming a login and then
sign in to that buyer's account themselves. Separately, a moderator who bans a seller
does not actually cut off the seller's existing website session, and the website has no
per-request account-state check, so a ban or a consent change takes up to two weeks to
take effect. Three further gaps let an operator's normal "disable this account" and
"throttle login attempts" controls silently fail. Overall: the login *token* is sound;
the login *session* is not.

## Scope & Methodology

**Scope:** The Telegram deep-link login mechanism end-to-end across both processes —
`apps/users/views/consent.py` (`login_issue` issuance, `login_status` web consumption),
`src/telegram_bot/handlers/login.py` (bot claim), `apps/users/models.py::LoginToken`,
`apps/users/services/login_rate_limit.py`, `apps/core/management/commands/cleanup_login_tokens.py`,
`apps/users/services/account_state.py`, session/cookie settings in
`config/settings/{base,prod}.py`, `docker/nginx/nginx.conf`, and
`backend/templates/users/login_issue.html`. Authorization/RBAC and object-level access
control are out of scope (Phase 15).

### Runtime Verification

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | Only the SHA-256 hash of the login token is persisted; no raw-token column exists | `read models.py:175-214`; `read 0001_initial.py:32-37` (`token_hash` `unique=True`) | PASS |
| R-02 | Raw token is never logged on issuance / claim / consumption | `grep -rn raw_token` across `src/` — only the issuance view, the bot handler, tests, and the template tag reference it; log statements emit `token_hash[:8]` only (`consent.py:333`, `consent.py:432-436`) | PASS |
| R-03 | No raw-token `==` / `compare_digest` gate; hash computed before the indexed lookup | `grep -rn "compare_digest\|constant_time_compare\|hmac\."` → 0 project matches; `consent.py:402` hashes before `LoginToken.objects.get(token_hash=…)`; `login.py:124` hashes before the `UPDATE` | PASS |
| R-04 | Indexed unique `token_hash` lookup (no linear scan) | `0001_initial.py:37` `unique=True`; `models.py:185-190` | PASS |
| R-05 | Expired / unknown / already-consumed tokens are rejected | `read consent.py:404-430`; tests `test_login_status_410_{no_token,nonexistent_token,expired,already_consumed}` | PASS |
| R-06 | Concurrent double-claim yields exactly one winner | `read login.py:154-187` (single `UPDATE … RETURNING` guarded by `telegram_id IS NULL AND consumed_at IS NULL AND expires_at > %s`); `read consent.py:421-430` (guarded `UPDATE … consumed_at`); test `test_concurrent_login_token_race` | PASS |
| R-07 | Token entropy ≥ 256-bit CSPRNG, URL-safe, fixed width matching the bot regex | `read consent.py:323` `secrets.token_urlsafe(24)` → 24 random bytes / 192 bits / 32 chars; `read login.py:37` `^login_([A-Za-z0-9_-]{32})$` | PASS |
| R-08 | Expired / consumed tokens are swept by a scheduled job | `read cleanup_login_tokens.py`; `read apps/core/utils/scheduler.py:61` (command is in the hourly cycle) | PASS |
| R-09 | Session cookie is `Secure` + `HttpOnly` + `SameSite`; logout is POST-only + CSRF | `read base.py:139-144`; `read views/logout.py:15-25`; `test_post_logout_without_csrf_returns_403` | PASS |
| R-10 | Login token is bound to the browser session that requested it | `Select-String "request\.session\|session_key" consent.py` → **0 matches**; `LoginToken` model has no session/device column | **FAIL → AUT-001** |
| R-11 | Web requests re-check account state (ban / delete / decline) on every request | `grep -rn "can_login\|is_banned" src/backend/apps` → `can_login` invoked only at `consent.py:449`; no account-state middleware in `base.py:196-211`; bot has `AccountStateMiddleware` (`permissions.py:103-108`), web has no equivalent | **FAIL → AUT-002** |
| R-12 | Login issuance rate limit is keyed by a non-spoofable client IP | `read login_rate_limit.py:63-79` (takes `X-Forwarded-For[0]`); `read nginx.conf:116` (`$proxy_add_x_forwarded_for` preserves the client-supplied value as element 0) | **FAIL → AUT-003** |
| R-13 | Django's `is_active` account kill-switch is honoured by the login flow | `grep -rn is_active src/backend/apps src/telegram_bot` → no check on `User.is_active` anywhere; `consent.py:459` uses low-level `auth_login()` which bypasses `ModelBackend.user_can_authenticate()` | **FAIL → AUT-004** |
| R-14 | A recovery path exists for the only password-based credential (Django admin) | `grep -rn "password_reset\|PasswordReset\|django.contrib.auth.urls"` → 0 matches; `config/urls.py:11-23` has no auth URL include; `AUTH_PASSWORD_VALIDATORS` absent from settings | **FAIL → AUT-005** |
| R-15 | Session lifetime is explicitly configured | `grep -rn "SESSION_COOKIE_AGE\|SESSION_EXPIRE_AT_BROWSER_CLOSE\|SESSION_ENGINE"` → 0 matches; Django default (14-day absolute, no idle timeout) applies | **FAIL → AUT-006** |
| R-16 | Repeated issuance invalidates the browser's previous outstanding token | `read consent.py:315-342` — no lookup of prior tokens, no deletion; `GET /login/issue/` performs an INSERT | **FAIL → AUT-007** |
| R-17 | Auth/login test suite green | `docker compose --project-name mko-bazuna-test … run --rm -e "PYTEST_OPTS=…test_login.py …test_logout.py …test_login.py" test` | PASS (43 tests) — see Appendix A |
| R-18 | Linter + type-checker clean on the auth surface | `uv run ruff check src/backend/apps/users/ src/telegram_bot/handlers/login.py …` → `All checks passed!`; `uv run basedpyright consent.py login_rate_limit.py login.py` → `0 errors, 0 warnings, 0 notes` | PASS |

> PASS results prove the audit was thorough; they are METHODOLOGY evidence, NOT findings.

**Tools used:** `read`/`grep`/`glob` over the live source, `Select-String`, `docker compose run` (test project `mko-bazuna-test`), `uv run ruff check`, `uv run basedpyright`, `uv run python -c "ast.parse(...)"`, manual review of `docker/nginx/nginx.conf`.

**Assumptions:** Production runs `config.settings.prod` behind the bundled nginx TLS terminator; the Redis cache is shared by web and bot (enforced by the `REDIS_URL` fail-fast guard in `prod.py:246-251`); PostgreSQL uses the default READ COMMITTED isolation, so the two-phase claim's guarded `UPDATE` sees committed state from a competing transaction; the `mko-bazuna-dev` web/bot containers were crash-looping throughout the audit, so no live HTTP traffic was captured — all runtime evidence is source-level or test-level.

## Findings Summary

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| AUT-001 | Login token is not bound to the browser session that issued it — forwarded deep link yields account takeover | HIGH | Open | Authentication |
| AUT-002 | Banning/deleting/declining an account never revokes its live web session (no web-side account-state check) | HIGH | Open | Session management |
| AUT-003 | Login issuance rate limit is keyed on a client-controlled `X-Forwarded-For` — limit is bypassable | MEDIUM | Open | Abuse prevention |
| AUT-004 | `User.is_active` kill-switch is silently ignored by the Telegram login flow | MEDIUM | Open | Authentication |
| AUT-005 | No password-reset / credential-recovery path and no password validators for the admin login | MEDIUM | Open | Credential management |
| AUT-006 | Session lifetime falls back to the unconfigured Django 14-day default; no idle timeout | LOW | Open | Session management |
| AUT-007 | `login_issue` is a state-changing GET that never invalidates the browser's previous outstanding token | LOW | Open | Design / abuse prevention |

## Distribution

**Severity counts**

| CRITICAL | HIGH | MEDIUM | LOW |
|----------|------|--------|-----|
| 0 | 2 | 3 | 2 |

**Status counts**

| Status | Count |
|--------|-------|
| Open | 7 |

> Note: Status is `Open` for all findings in raw phase reports. Phase 99 validation mutates Status to `Validated` / `Reclassified` / `Merged` / `Rejected` / `Deferred`. Values `Fixed` / `Verified` are forbidden here — they belong to a remediation tracker, not the audit report.

## Findings by Severity

### HIGH

#### AUT-001: [HIGH] — Login token is not bound to the browser session that issued it — forwarded deep link yields account takeover

| Field | Value |
|---|---|
| **ID** | AUT-001 |
| **Title** | Login token is not bound to the browser session that issued it — forwarded deep link yields account takeover |
| **Severity** | HIGH |
| **Category** | Authentication (CWE-346 Origin Validation Error / CWE-305 Authentication Bypass by Primary Weakness) |
| **File(s)** | `src/backend/apps/users/views/consent.py:315-342` (issuance), `src/backend/apps/users/views/consent.py:398-406` (consumption), `src/backend/apps/users/models.py:185-208` (model), `src/backend/templates/users/login_issue.html:38,47` |
| **Status** | Open |
| **Problem** | `login_issue` never touches `request.session` — the `LoginToken` row is created with no reference to the browser that asked for it, and `login_status` never inspects `request.session` before authenticating. The raw token is therefore a **bearer credential with no origin check**: any client that possesses it may exchange it for a session, regardless of which browser it was minted for. CSRF protection does not help, because the party performing the exchange is the attacker, acting from their own browser with their own valid CSRF token. |
| **Impact** | An attacker calls `GET /login/issue/`, receives raw token `T`, and sends the victim the link `https://t.me/<bot>?start=login_T` ("tap this to log in to your account"). The victim taps it in Telegram; the bot atomically binds `telegram_id = <victim>` to `T` and confirms "Login successful!". The attacker then `POST`s `T` to `/login/status/` from their own browser and receives `200` plus an authenticated session cookie **for the victim's account**. The attacker can then read and edit the victim's ads, delete them, view/alter saved searches, favourites and search history, and withdraw the victim's consent (triggering erasure of the victim's data). The victim only has to tap a link that looks like an ordinary login prompt. |
| **Root Cause** | Session-binding was never part of the two-phase token design. `LoginToken` carries only `token_hash`, `telegram_id`, `created_at`, `expires_at`, `consumed_at` (`models.py:185-208`) — there is no `session_key`/`device_fingerprint` column, and no `select ... where session_key = request.session.session_key` guard on the consumption `UPDATE`. The CSRF token rendered into the login page (`login_issue.html:38`) is trivially obtainable by the attacker, so CSRF provides no origin assurance for this endpoint. |
| **Recommendation** | Bind the token to the browser at issuance and enforce it at consumption: (1) add a nullable `session_key = CharField(max_length=40, db_index=True)` to `LoginToken` (the same width as `ConsentRecord.session_key`, `models.py:237-242`) and a migration; (2) in `login_issue`, ensure the session exists and store `request.session.session_key` on the new row; (3) in `login_status`, add `session_key=request.session.session_key` to the `LoginToken.objects.filter(...)` consumption guard so a token minted in another browser is rejected with `410`. Because `request.session` is not written on the `login_issue` GET path today, note that `SessionMiddleware` will not persist a session that was never modified — the view must touch the session (e.g. `request.session.setdefault("login_started", True)`) to force a session key. As defence in depth, keep the POST-only + CSRF contract already in place. |
| **Effort** | M (~1 person-day incl. migration + tests) |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **CWE** | CWE-346 (Origin Validation Error); CWE-305 (Authentication Bypass by Primary Weakness) |
| **Likelihood** | MEDIUM (requires the victim to tap an attacker-supplied deep link, but that is a routine user action and the link is indistinguishable from a normal login prompt) |

| Field | Value |
|---|---|
| **Related Findings** | AUT-002 (session that this attack creates also survives a later ban) |

**Evidence — `src/backend/apps/users/views/consent.py:315-342`** *(supports: "the issuance path never binds the token to a browser session")*:
```python
    if not login_rate_limit_check(request):
        logger.warning("Rate limit exceeded for login_issue")
        return HttpResponse(status=429)

    raw_token = secrets.token_urlsafe(24)  # 32 URL-safe chars, matches bot regex `{32}`
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    LoginToken.objects.create(
        token_hash=token_hash,
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    # ... render(..., {"bot_username": bot_username, "raw_token": raw_token})
```

**Evidence — `src/backend/apps/users/views/consent.py:398-426`** *(supports: "the consumption path authenticates on the token alone, never on the requesting session")*:
```python
    raw_token = request.POST.get("token", "")
    if not raw_token:
        return HttpResponse(status=410)

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    with transaction.atomic():
        try:
            token = LoginToken.objects.get(token_hash=token_hash)
        except LoginToken.DoesNotExist:
            return HttpResponse(status=410)
        ...
        updated = LoginToken.objects.filter(
            token_hash=token_hash,
            telegram_id=token.telegram_id,
            consumed_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).update(consumed_at=timezone.now())
```

**Evidence — `Select-String "request\.session|session_key" src/backend/apps/users/views/consent.py`** *(supports: "no session reference exists anywhere in the login views")*:
```text
(no matches — 0 hits across all 470 lines of consent.py)
```

**Evidence — `src/backend/templates/users/login_issue.html:37-48`** *(supports: "the attacker can obtain a valid CSRF token for their own session, so CSRF does not prevent the exchange")*:
```html
            var pollUrl = "{% url 'consent:login_status' %}";
            var csrfToken = "{{ csrf_token|escapejs }}";
            ...
                fd.append("token", "{{ raw_token }}");
                fetch(pollUrl, { method: "POST", body: fd, headers: { "X-CSRFToken": csrfToken } })
```

---

#### AUT-002: [HIGH] — Banning/deleting/declining an account never revokes its live web session (no web-side account-state check)

| Field | Value |
|---|---|
| **ID** | AUT-002 |
| **Title** | Banning/deleting/declining an account never revokes its live web session (no web-side account-state check) |
| **Severity** | HIGH |
| **Category** | Session management (CWE-613 Insufficient Session Expiration) |
| **File(s)** | `src/backend/apps/moderation/admin_actions.py:98-100`, `src/backend/apps/moderation/admin_actions.py:255`, `src/backend/apps/users/admin.py:55-65`, `src/backend/apps/users/views/consent.py:449`, `src/backend/config/settings/base.py:196-211` |
| **Status** | Open |
| **Problem** | `can_login()` is consulted at exactly one place — the moment a session is created (`consent.py:449`). After that, every `@login_required` view in `ads`, `cabinet`, `analytics` and `search` trusts the session alone. There is no Django middleware mirroring the bot's `AccountStateMiddleware`, and no code path deletes the affected user's `django_session` rows. Consequently `is_banned`, `is_deleted` and `is_declined` are enforced **only at the next login**, never during an existing session. |
| **Impact** | A moderator who bans a seller for abuse (spam, fraud, illegal goods) does not stop them: the seller's already-open session keeps working on the seller dashboard — viewing, editing and deleting their ads, managing saved searches, favourites and search history — until the session expires, which is Django's unconfigured 14-day default (see AUT-006). The same applies to a user who clicks "decline consent" (browse-only mode is meant to remove seller capability immediately) and to a user whose consent is withdrawn **by an administrator** through the `/admin/` bulk action, which calls `withdraw_consent(user)` in the admin's own request context and never touches the target user's session. Only the self-service web withdrawal path calls `logout(request)` (`consent.py:259`). The abuse-response control silently takes up to two weeks to bite, and the "banned" badge shown to staff does not reflect what the seller can actually still do. |
| **Root Cause** | Account state lives in three boolean columns on `User`, but only the Telegram process has a per-request evaluator (`telegram_bot/middlewares/permissions.py:103-108`). The web process has no equivalent gate in `MIDDLEWARE` (`base.py:196-211`) and no session-revocation helper. `ban_user_for_ad` / `bulk_ban_users` only write `is_banned`; `UserAdmin.withdraw_consent_action` only calls `withdraw_consent`. |
| **Recommendation** | Close the loop in two complementary places. (1) Add a web-side account-state gate — a small Django middleware (or a shared `require_active_seller` decorator applied to the `@login_required` seller views) that calls `get_account_state(user)` and, for `is_banned` / `is_deleted` / `is_declined`, flushes the session and redirects to `LOGIN_URL`; it reuses the same `AccountState` named tuple the bot already consumes, so there is one source of truth. (2) Make revocation immediate on the write side: in `ban_user_for_ad`, `bulk_ban_users` and `UserAdmin.withdraw_consent_action`, delete the target user's `django_session` rows (`Session.objects.filter(session_data__contains=...)` is not viable — instead store `user_id` via Django's built-in `Session` backend API: `Session.objects.all()` filtered by decoded `_auth_user_id`, or simply rely on (1) with a short `SESSION_COOKIE_AGE`). Option (1) alone is sufficient for correctness; (2) is defence in depth. |
| **Effort** | M (~1-2 person-days incl. tests across `ads`/`cabinet`/`analytics`/`search` views) |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **CWE** | CWE-613 (Insufficient Session Expiration); CWE-862 (Missing Authorization) |
| **Likelihood** | HIGH (a ban is a routine moderation action; the gap triggers on every one of them) |

| Field | Value |
|---|---|
| **Related Findings** | AUT-001, AUT-004, AUT-006 |

**Evidence — `src/backend/apps/moderation/admin_actions.py:98-100`** *(supports: "ban flips a flag only; no session is touched")*:
```python
        if not user.is_banned:
            user.is_banned = True
            user.save(update_fields=["is_banned"])
```

**Evidence — `src/backend/apps/moderation/admin_actions.py:255`** *(supports: "bulk ban likewise performs a bare UPDATE with no session cleanup")*:
```python
        User.objects.filter(id__in=user_ids).update(is_banned=True)
```

**Evidence — `grep -rn "can_login|can_publish_ad|is_banned|is_declined" src/backend/apps`** *(supports: "`can_login` is invoked only once, at session-creation time")*:
```text
src/backend/apps/users/views/consent.py:41:    can_login,
src/backend/apps/users/views/consent.py:449:    if not can_login(user):
src/backend/apps/moderation/admin_actions.py:98:  if not user.is_banned:
src/backend/apps/moderation/admin_actions.py:99:      user.is_banned = True
src/backend/apps/moderation/admin_actions.py:255: User.objects.filter(id__in=user_ids).update(is_banned=True)
(no other consumers of can_login; no account-state middleware in base.py MIDDLEWARE)
```

**Evidence — `src/telegram_bot/middlewares/permissions.py:102-108`** *(supports: "the bot process enforces the same three flags on every message — the web process has no counterpart")*:
```python
        # Check if user is banned, deleted, or has revoked consent
        can_interact, state_reason = await self._check_user_state(
            chat_id, is_contact_link=is_contact_link
        )
        if not can_interact:
            await message.answer(state_reason)
            return None
```

**Evidence — `src/backend/apps/users/admin.py:55-65`** *(supports: "admin-initiated consent withdrawal runs in the admin's request and never logs the target user out")*:
```python
    @admin.action(description="Withdraw consent for selected users")
    def withdraw_consent_action(self, request, queryset):
        for user in queryset:
            withdraw_consent(user)
```

---

### MEDIUM

#### AUT-003: [MEDIUM] — Login issuance rate limit is keyed on a client-controlled `X-Forwarded-For` — limit is bypassable

| Field | Value |
|---|---|
| **ID** | AUT-003 |
| **Title** | Login issuance rate limit is keyed on a client-controlled `X-Forwarded-For` — limit is bypassable |
| **Severity** | MEDIUM |
| **Category** | Abuse prevention (CWE-348 Use of Less Trusted Source) |
| **File(s)** | `src/backend/apps/users/services/login_rate_limit.py:63-79`, `src/backend/apps/core/services/contact_rate_limit.py:24-29`, `docker/nginx/nginx.conf:116` |
| **Status** | Open |
| **Problem** | `login_rate_limit_check` builds its cache key from `HTTP_X_FORWARDED_FOR.split(",")[0]` whenever that header is present, with no trusted-proxy validation. The bundled nginx sets the upstream header with `$proxy_add_x_forwarded_for`, which **appends** `$remote_addr` to whatever the client sent — so element `0` is exactly the attacker-controlled value, not the peer address. The same helper is duplicated verbatim in `contact_rate_limit.py`, so the 60-renders/600 s deep-link cap on the same page is bypassable too. |
| **Impact** | The "10 requests / 60 s per IP" issuance control that `docs/01-spec/spec-index.md:75` and `docs/01-spec/technical-specification.md:140` advertise as a login-hardening property is not enforced: rotating the `X-Forwarded-For` header on each request yields a fresh cache key every time, so the counter never exceeds 1. The only remaining cap is nginx's own `limit_req zone=login_limit rate=10r/s burst=20` (`nginx.conf:24,112`), which permits roughly 10 `LoginToken` INSERTs per second sustained from one source and, because gunicorn workers handle requests independently, is a throughput cap rather than a quota. Combined with AUT-007 (no invalidation of prior tokens), this is an unauthenticated way to grow the `login_tokens` table continuously; the hourly `cleanup_login_tokens` sweep bounds it but does not prevent the write amplification. |
| **Root Cause** | The IP-extraction helper treats any inbound `X-Forwarded-For` as authoritative. Django has no built-in trusted-proxy list, so the project must either configure nginx to *overwrite* the header (`proxy_set_header X-Forwarded-For $remote_addr;`) or the helper must only honour the header when `request.META["REMOTE_ADDR"]` matches a configured proxy address. The helper is also copy-pasted in two modules, so the fix must be applied twice. |
| **Recommendation** | Pick one and apply it consistently. Preferred: change `docker/nginx/nginx.conf` to `proxy_set_header X-Forwarded-For $remote_addr;` (the real peer) in all locations, and have the Django helper prefer `REMOTE_ADDR` unless an explicit `TRUSTED_PROXY_CIDRS` setting matches. Then extract the duplicated `_get_client_ip` into a single shared helper (e.g. `apps.core.utils.client_ip.get_client_ip`) used by `login_rate_limit`, `contact_rate_limit` and `search.services.rate_limit`. Add a regression test that asserts two requests with different `HTTP_X_FORWARDED_FOR` values but the same `REMOTE_ADDR` share one counter. |
| **Effort** | S (~0.5 person-day) |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | CWE-348 (Use of Less Trusted Source) |
| **Likelihood** | HIGH (one extra request header defeats the control) |

| Field | Value |
|---|---|
| **Related Findings** | AUT-007 |

**Evidence — `src/backend/apps/users/services/login_rate_limit.py:63-79`** *(supports: "the rate-limit key is taken from the first, client-controlled X-Forwarded-For element")*:
```python
def _get_client_ip(request: HttpRequest) -> str:
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")
```

**Evidence — `docker/nginx/nginx.conf:111-118`** *(supports: "nginx preserves the client-supplied XFF as element 0, so the Django helper reads attacker input")*:
```nginx
        location /login/ {
            limit_req zone=login_limit burst=20 nodelay;
            proxy_pass http://web:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
```

---

#### AUT-004: [MEDIUM] — `User.is_active` kill-switch is silently ignored by the Telegram login flow

| Field | Value |
|---|---|
| **ID** | AUT-004 |
| **Title** | `User.is_active` kill-switch is silently ignored by the Telegram login flow |
| **Severity** | MEDIUM |
| **Category** | Authentication (CWE-287 Improper Authentication / CWE-863 Incorrect Authorization) |
| **File(s)** | `src/backend/apps/users/views/consent.py:438-459`, `src/backend/apps/users/admin.py:14-41` |
| **Status** | Open |
| **Problem** | `User` inherits Django's `AbstractUser.is_active` boolean, and `UserAdmin` does not restrict `fields`/`fieldsets`, so the flag is editable in the `/admin/` change form. But the login flow never reads it: `login_status` resolves the account with a bare `User.objects.get(telegram_id=…)` and then calls the low-level `django.contrib.auth.login()`, which writes the session **without** running any authentication backend. Django's `ModelBackend.user_can_authenticate()` — the only place `is_active` is enforced — is bypassed entirely. The only gate is `can_login()`, which inspects `is_banned` and `is_declined` exclusively. |
| **Impact** | An operator who deactivates an account in `/admin/` — Django's standard "disable this account" control, and the reflex action for a compromised or unwanted account — observes no effect: the user can still mint a token on the site, confirm it in Telegram, and obtain a fully authenticated seller session. The flag is also absent from `UserAdmin.list_display`/`list_filter` (`admin.py:22-35`), so the state is not even visible in the changelist, which makes the silent failure hard to notice. Two independent account-state vocabularies (`is_banned`/`is_declined` and `is_active`) now mean overlapping things and only one of them is enforced. |
| **Root Cause** | The project implemented a bespoke, backend-free authentication path (raw token → `User` row → `auth_login`) and reimplemented the eligibility check in `can_login()` without carrying over Django's `is_active` predicate. Nothing in the auth surface references the flag, so its removal from the model would not break any test. |
| **Recommendation** | Decide on one source of truth and make it explicit. Lowest-risk fix: add `if not user.is_active: return False` to `can_login()` (`apps/users/services/account_state.py:96-106`) and to `AccountState` as a field, so both the bot middleware and the web gate honour it; add `is_active` to `UserAdmin.list_display`/`list_filter`. If instead the project intends to drop `is_active` entirely (Telegram identity is the only account state), then remove the column in a migration and add a `UserAdmin` fieldset that hides it, so operators are not offered an inoperative control. Either way, add a test asserting a deactivated account cannot complete a Telegram login. |
| **Effort** | S (~0.5 person-day) |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | CWE-287 (Improper Authentication) |
| **Likelihood** | MEDIUM (operator must use the standard control; the bot's own `AccountStateMiddleware` also ignores `is_active`, so a deactivated user also keeps full bot access) |

| Field | Value |
|---|---|
| **Related Findings** | AUT-002 |

**Evidence — `src/backend/apps/users/views/consent.py:438-459`** *(supports: "the account is fetched directly and logged in via the low-level helper; no backend and no `is_active` check runs")*:
```python
    # Look up the user by telegram_id
    try:
        user = User.objects.get(telegram_id=token.telegram_id)
    except User.DoesNotExist:
        logger.error(
            "User not found for telegram_id=%s",
            mask_telegram_id(token.telegram_id),
        )
        return HttpResponse(status=410)

    # Check if user is banned
    if not can_login(user):
        logger.warning(
            "Login denied for telegram_id=%s: banned",
            mask_telegram_id(token.telegram_id),
        )
        return HttpResponse(status=410)

    # Establish web session
    auth_login(request, user)
```

**Evidence — `src/backend/apps/users/services/account_state.py:96-106`** *(supports: "`can_login` — the only eligibility gate — inspects `is_banned` and `is_declined` only")*:
```python
    state = get_account_state(user)

    if state.is_banned:
        logger.info("User %s cannot login: banned", user.id)
        return False

    if state.is_declined:
        logger.info("User %s cannot login: declined consent", user.id)
        return False

    return True
```

**Evidence — `grep -rn "is_active" src/backend/apps src/telegram_bot`** *(supports: "`User.is_active` is never read on any authentication or authorization path")*:
```text
(no match on users.User: every hit is Category.is_active, LookupItem.is_active,
 SavedSearch.is_active, or an unrelated *_channel*/ContactChannel field.
 The users app references is_active only in apps/users/migrations/0001_initial.py:122
 as an inherited AbstractUser column.)
```

---

#### AUT-005: [MEDIUM] — No password-reset / credential-recovery path and no password validators for the admin login

| Field | Value |
|---|---|
| **ID** | AUT-005 |
| **Title** | No password-reset / credential-recovery path and no password validators for the admin login |
| **Severity** | MEDIUM |
| **Category** | Credential management (CWE-640 Weak Password Recovery Mechanism) |
| **File(s)** | `src/backend/config/urls.py:11-23`, `src/backend/apps/users/models.py:126-127`, `src/backend/config/settings/prod.py:198-208`, `src/backend/config/settings/base.py` (absent `AUTH_PASSWORD_VALIDATORS`) |
| **Status** | Open |
| **Problem** | Telegram users never hold a password, but the project does have exactly one password-based identity: `User.USERNAME_FIELD = "username"` powers `/admin/`, and `docker/entrypoint-create-admin.sh` bootstraps it from `$ADMIN_PASSWORD`. There is no recovery path: `config/urls.py` includes only `django_prometheus`, `admin`, and the project apps — `django.contrib.auth.urls` and any `PasswordResetView`/`PasswordChangeView` are absent, and `grep` for `password_reset|PasswordReset|django.contrib.auth.urls` returns nothing. There is also no `AUTH_PASSWORD_VALIDATORS` setting in `base.py` or `prod.py`, so the admin password is accepted verbatim. Meanwhile `prod.py:198-199` justifies a hard `EMAIL_HOST` fail-fast partly on the grounds that it is "required … for transactional emails (password resets, …)" — a flow that does not exist. |
| **Impact** | Losing or rotating the sole moderator/admin credential requires shell access to a running container to execute `manage.py`, i.e. a production host and database access, on the spot. There is no self-service or mail-based recovery, and no policy forcing rotation or a minimum strength. The comment in `prod.py` also misleads operators into believing a password-reset mail path is live, so a lockout will be discovered during an incident rather than planned for. |
| **Root Cause** | The auth surface was designed around Telegram only; the inherited Django password credential was treated as out of scope and never given a lifecycle (issuance policy, validators, recovery), while documentation and settings comments were written as though it had one. |
| **Recommendation** | Minimal, proportionate fix: (1) add `AUTH_PASSWORD_VALIDATORS` to `config/settings/base.py` with the four standard Django validators (or at minimum `MinimumLengthValidator(12)` + `CommonPasswordValidator`) so any future password — including one supplied to `create_admin_user` — is policy-checked; (2) either wire `django.contrib.auth.urls` (or just `password_reset` + `password_reset_done`) behind `login_required`/staff-only so a moderator can self-serve, or, if that is deliberately out of scope, correct the `prod.py:198` comment to stop claiming password resets exist and document the container-shell recovery runbook in `docs/ops/`; (3) once a `password` field is user-editable, call `update_session_auth_hash()` on change so other sessions are not silently invalidated. |
| **Effort** | S (~0.5 person-day) |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **CWE** | CWE-640 (Weak Password Recovery Mechanism) |
| **Likelihood** | LOW (requires credential loss or a desire to rotate one) |

| Field | Value |
|---|---|
| **Related Findings** | AUT-006 |

**Evidence — `src/backend/config/urls.py:11-23`** *(supports: "no authentication/password URL namespace is mounted")*:
```python
urlpatterns = [
    path("", include("django_prometheus.urls")),
    path("admin/", admin.site.urls),
    path("moderation/", include("apps.moderation.urls")),
    path("analytics/", include("apps.analytics.urls")),
    path("cabinet/", include("apps.cabinet.urls")),
    path("", include("apps.users.urls")),
    ...
]
```

**Evidence — `src/backend/config/settings/prod.py:198-208`** *(supports: "settings documentation claims a password-reset mail flow that is not implemented")*:
```python
# Fail fast: EMAIL_HOST is required in production so transactional emails
# (password resets, alert notifications, seller confirmations) are deliverable.
if not _SKIP_SECRET_VALIDATION:
    if not EMAIL_HOST:  # noqa: F405
        raise ImproperlyConfigured(
            "EMAIL_HOST must be set in production. "
            "Provide it via the .env.prod runtime file."
        )
```

**Evidence — `grep -rn "password_reset|PasswordReset|django\.contrib\.auth\.urls|AUTH_PASSWORD_VALIDATORS|PASSWORD_HASHERS"`** *(supports: "neither a reset view nor a password policy is configured anywhere")*:
```text
src/backend/config/settings/test.py:57:    PASSWORD_HASHERS = [  # noqa: F405
(the only match: the test-only MD5 hasher used to keep test runs fast.
 No AUTH_PASSWORD_VALIDATORS and no password_reset URL/view anywhere in the repo.)
```

---

### LOW

#### AUT-006: [LOW] — Session lifetime falls back to the unconfigured Django 14-day default; no idle timeout

| Field | Value |
|---|---|
| **ID** | AUT-006 |
| **Title** | Session lifetime falls back to the unconfigured Django 14-day default; no idle timeout |
| **Severity** | LOW |
| **Category** | Session management (CWE-613) |
| **File(s)** | `src/backend/config/settings/base.py:139-144`, `src/backend/config/settings/prod.py:215-217` |
| **Status** | Open |
| **Problem** | `base.py` sets the three cookie *flags* (`SESSION_COOKIE_SECURE/HTTPONLY/SAMESITE`) but never sets a lifetime. `grep` for `SESSION_COOKIE_AGE`, `SESSION_EXPIRE_AT_BROWSER_CLOSE`, `SESSION_SAVE_EVERY_REQUEST`, `SESSION_ENGINE` and `SESSION_COOKIE_NAME` returns **zero matches** across the whole repository, so the Django defaults apply: a 14-day absolute session lifetime, no idle timeout (`SESSION_SAVE_EVERY_REQUEST = False`), and a perpetual 28-day CSRF cookie. `prod.py` restates only the two `Secure` flags. |
| **Impact** | A seller session stolen on a shared or borrowed device stays usable for two weeks, which is the window that AUT-001's attack and AUT-002's ban gap both rely on. There is no shorter idle timeout to shrink that window for abandoned sessions on shared machines, and no documented session policy for operators. |
| **Root Cause** | Cookie flags were treated as the whole session-security contract; lifetime was left implicit. |
| **Recommendation** | Make the policy explicit in `config/settings/base.py` and tighten it: `SESSION_COOKIE_AGE = 60 * 60 * 24 * 7` (7 days) or shorter, `SESSION_SAVE_EVERY_REQUEST = False` (keep the absolute timeout), and `SESSION_COOKIE_AGE`-independent `CSRF_COOKIE_AGE` if desired. If an absolute cap shorter than the cookie age is wanted, use `request.session.set_expiry()` in `login_status`. This is a one-line settings change with no code impact and can ship independently of AUT-001/AUT-002 — though it only blunts those findings, it does not fix them. |
| **Effort** | S (trivial, ~0.25 person-day) |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **CWE** | CWE-613 (Insufficient Session Expiration) |
| **Likelihood** | LOW |

| Field | Value |
|---|---|
| **Related Findings** | AUT-001, AUT-002, AUT-005 |

**Evidence — `src/backend/config/settings/base.py:138-144`** *(supports: "cookie flags are configured; lifetime is not")*:
```python
# Security settings (TLS/SSL ready)
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
```

**Evidence — `grep -rn "SESSION_COOKIE_AGE|SESSION_EXPIRE_AT_BROWSER_CLOSE|SESSION_SAVE_EVERY_REQUEST|SESSION_ENGINE|SESSION_COOKIE_NAME|SESSION_COOKIE_PATH|SESSION_COOKIE_DOMAIN"`** *(supports: "no session-lifetime setting exists anywhere in the repository")*:
```text
No files found
```

---

#### AUT-007: [LOW] — `login_issue` is a state-changing GET that never invalidates the browser's previous outstanding token

| Field | Value |
|---|---|
| **ID** | AUT-007 |
| **Title** | `login_issue` is a state-changing GET that never invalidates the browser's previous outstanding token |
| **Severity** | LOW |
| **Category** | Design / abuse prevention |
| **File(s)** | `src/backend/apps/users/views/consent.py:297-342`, `src/backend/apps/users/urls.py:20` |
| **Status** | Open |
| **Problem** | `login_issue` is routed as a plain `GET` (`users/urls.py:20`) and performs a database `INSERT` on every hit without a CSRF token, and it does not look for — or invalidate — the tokens it previously handed to the same browser. A user who reloads the login page, opens it in several tabs, or is prefetched by the browser accumulates several simultaneously valid tokens, each independently claimable by any Telegram account within its 5-minute window. The dead `bot_username` context value (`consent.py:331,339`) is also still passed although the template now sources the username from the `{% telegram_deep_link %}` tag. |
| **Impact** | The number of live, claimable credentials in a browser's hands grows with every reload, widening the window in which a token leaked from a shared machine, a screenshot, or a stray prefetch can be claimed. Because a GET is both a state change and CSRF-exempt, any third-party page can force token creation for a visitor through an `<img>`/prefetch, and the resulting rows are only reclaimed by the hourly `cleanup_login_tokens` sweep. |
| **Root Cause** | Issuance was modelled as a page render rather than as an authenticated operation, so no idempotency key (the browser session) is available to scope or replace prior tokens. |
| **Recommendation** | Two small changes, both in `login_issue`: (1) before `LoginToken.objects.create(...)`, expire the current browser's outstanding unconsumed tokens — this becomes trivial once AUT-001 adds `session_key` to the model (`LoginToken.objects.filter(session_key=…, consumed_at__isnull=True).delete()`), so fixing AUT-001 first also fixes half of this; (2) drop the unused `bot_username` context value (`consent.py:331,339`) — the template tag resolves it itself, and `apps/core/tests/test_login_issue_template.py:36` already asserts the username is delivered exclusively through the tag. Converting issuance to POST is optional and would degrade the QR/deep-link UX, so it is not recommended. |
| **Effort** | S (~0.25 person-day, mostly test updates) |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **CWE** | CWE-352 (Cross-Site Request Forgery, state-changing GET); CWE-384 (Session Fixation-adjacent credential accumulation) |
| **Likelihood** | LOW |

| Field | Value |
|---|---|
| **Related Findings** | AUT-001, AUT-003 |

**Evidence — `src/backend/apps/users/urls.py:20-21`** *(supports: "issuance is a GET, consumption is the only POST-bound endpoint")*:
```python
    path("login/issue/", login_issue, name="login_issue"),
    path("login/status/", login_status, name="login_status"),
```

**Evidence — `src/backend/apps/users/views/consent.py:323-342`** *(supports: "each GET mints a fresh token; nothing invalidates the previous one and `bot_username` is passed unused")*:
```python
    raw_token = secrets.token_urlsafe(24)  # 32 URL-safe chars, matches bot regex `{32}`
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    LoginToken.objects.create(
        token_hash=token_hash,
        expires_at=timezone.now() + timedelta(minutes=5),
    )

    bot_username = get_bot_username()

    logger.info("Issued login token hash=%s...", token_hash[:8])

    return render(
        request,
        "users/login_issue.html",
        {
            "bot_username": bot_username,
            "raw_token": raw_token,
        },
    )
```

---

## Cross-Finding Analysis

- **Merge candidates:** AUT-006 and AUT-002 share a symptom (long-lived sessions) but not a root cause — AUT-002 is a missing revocation hook, AUT-006 is a missing lifetime policy, and the recommended fixes are independent. Keep separate; AUT-001 and AUT-007, by contrast, are *resolved by the same change* (adding `session_key` to `LoginToken`) and should be fixed in one commit — AUT-007's recommendation explicitly depends on AUT-001's schema change.
- **Conflicting evidence:** None. No two findings assert incompatible facts; the bot-side `AccountStateMiddleware` behaviour (AUT-002 evidence) and the web-side absence of any equivalent are complementary observations of the same gap, not contradictions.
- **Dependency chains:** AUT-001 → AUT-007 (session binding must land before per-browser token invalidation is expressible). AUT-002 is independent of both and can ship in parallel. AUT-006 reduces the exposure window of AUT-001 and AUT-002 but remediates neither. AUT-005 and AUT-007 are fully independent.

## Remediation Roadmap

| Order | ID | Severity | Effort | Priority | Recommendation (summary) |
|-------|----|----------|--------|----------|--------------------------|
| 1 | AUT-001 | HIGH | M | P0 | Add `LoginToken.session_key` (+ migration); write it in `login_issue`, require it in the `login_status` consumption guard |
| 2 | AUT-002 | HIGH | M | P0 | Add a web account-state gate (middleware or shared decorator) mirroring `AccountStateMiddleware`; revoke sessions on ban/withdraw |
| 3 | AUT-003 | MEDIUM | S | P1 | Make nginx overwrite `X-Forwarded-For` with `$remote_addr`; de-duplicate `_get_client_ip` into a shared helper |
| 4 | AUT-004 | MEDIUM | S | P1 | Enforce (or remove) `User.is_active`; surface it in `UserAdmin` |
| 5 | AUT-005 | MEDIUM | S | P2 | Add `AUTH_PASSWORD_VALIDATORS`; wire a reset view or correct the `prod.py` claim and document shell recovery |
| 6 | AUT-006 | LOW | S | P2 | Set `SESSION_COOKIE_AGE` explicitly (e.g. 7 days) and document the session policy |
| 7 | AUT-007 | LOW | S | P2 | Invalidate the browser's prior unconsumed tokens on re-issuance; drop the dead `bot_username` context value |

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| AUT-001 | Med | No — existing outstanding tokens have a NULL `session_key` and would be rejected mid-flow, logging out any user who was mid-login at deploy time | New: token minted in session A cannot be consumed from session B; token with matching `session_key` still consumes; a NULL-`session_key` legacy row behaves as defined (reject) |
| AUT-002 | Med | Yes for browsing; a currently-banned/declined user's next request will now redirect to `/login/issue/` instead of rendering the dashboard | New: a session held by a user flipped to `is_banned`/`is_declined`/`is_deleted` is flushed on the next request; an unaffected user's session survives; the bot path is unchanged |
| AUT-003 | Low | Yes — same limits, just correctly keyed | New: two requests with distinct `HTTP_X_FORWARDED_FOR` but identical `REMOTE_ADDR` share one counter and the 11th is throttled |
| AUT-004 | Low | Depends on choice — enforcing `is_active` will start rejecting accounts an operator may already have deactivated without noticing | New: `is_active=False` user gets `410` from `/login/status/` and is blocked by the bot middleware; `is_active=True` path unchanged |
| AUT-005 | Low | Yes — additive settings | New: an admin password failing a validator is rejected; if a reset view is added, end-to-end reset-and-login test |
| AUT-006 | Low | Behavioural — existing sessions keep their original expiry; only new logins get the shorter age | New: `settings.SESSION_COOKIE_AGE` value asserted; a session created after the change expires at the configured age |
| AUT-007 | Low | Yes — reload still works | New: a second `/login/issue/` in the same session leaves exactly one unconsumed token for that session |

## Appendices

### Appendix A — Auth/login test suite run (R-17)

Command (Windows PowerShell 7+; the test DB must be healthy first — the first two attempts
failed with `dependency failed to start: container mko-bazuna-test-db-1 is unhealthy`
during a DB recreate, then succeeded once `mko-bazuna-test-db-1` reported `healthy`):

```text
docker compose --project-name mko-bazuna-test --env-file .env.test `
  -f docker-compose.yml -f docker-compose.test.yml run --rm `
  -e "PYTEST_OPTS=src/backend/apps/users/tests/test_login.py src/backend/apps/users/tests/test_logout.py src/telegram_bot/tests/test_login.py --tb=short" test
```

Result (tail of output):

```text
43 passed, 25 warnings in 20.23s
```

The warnings are environmental, not defects: `UserWarning: No directory at: /app/staticfiles/`
(24×, `staticfiles` volume not mounted for a one-shot `run` container) and a teardown
`OperationalError('database "test_mko_bazuna" is being accessed by other users')` emitted
after the summary — the parallel long-running `mko-bazuna-test-test-run-7d9866f4d9ff`
container holds a second connection. Neither affects the pass count.

*(supports the claim: "the existing auth/login test suite is green; the gaps in
AUT-001…AUT-007 are therefore untested behaviours, not known-broken tests")*

### Appendix B — R-04/R-06 code trace: the two-phase atomic claim

```python
# src/telegram_bot/handlers/login.py:169-187  (phase 1 — bot binds identity)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE login_tokens
               SET telegram_id = %s
             WHERE token_hash = %s
               AND telegram_id IS NULL
               AND consumed_at IS NULL
               AND expires_at > %s
            RETURNING id, token_hash, telegram_id, created_at, expires_at, consumed_at
            """,
            [telegram_id, token_hash, now],
        )
        row = cursor.fetchone()
        if row is None:
            return None
```

```python
# src/backend/apps/users/views/consent.py:421-430  (phase 2 — web consumes)
        updated = LoginToken.objects.filter(
            token_hash=token_hash,
            telegram_id=token.telegram_id,
            consumed_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).update(consumed_at=timezone.now())

        if updated == 0:
            # Race condition — another request already consumed it
            return HttpResponse(status=410)
```

*(supports the claim: "single-statement, zero-TOCTOU claim with expiry and replay guards
inside the query — R-06 PASS; the design is sound and is not the subject of any finding")*

