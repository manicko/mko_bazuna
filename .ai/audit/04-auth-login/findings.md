---
name: audit-findings
description: Structured findings template for audit phase output
agent: audit-executor
alwaysApply: false
---

# Phase 04 Audit Findings — Authentication & Login Token Security

**Executor:** auditor
**Template:** .kilo/commands/audit/phases/04-audit-auth-login.md
**Status:** complete
**Validated:** no

---

## Findings

### AUT-001: Web-side token issuance is entirely missing (no token generator anywhere)

| Field | Value |
|-------|-------|
| **ID** | AUT-001 |
| **Severity** | CRITICAL |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/users/` (no issuance view/command), `src/backend/config/settings/base.py:171` (`BOT_USERNAME`) |
| **Classification** | mandatory |

**Description:** The documented login flow (docs/01-spec technical-specification.md §H, docs/02-database/db-schema.md `login_tokens`, user story US-S1) requires the **site** to generate a 32-char URL-safe token and render a QR/deep-link `https://t.me/<bot_username>?start=login_<token>`. A repo-wide search for any CSPRNG token generation (`secrets.token_urlsafe`, `token_hex`, `os.urandom`, `randbytes`) in source returns **zero matches** — only audit-plan/command markdown references it. There is no view, URL, template, or management command that issues a `LoginToken`. Consequently `LoginToken` rows can only exist if created out-of-band; the documented dual-process contract (web issues → bot claims) is broken on the issuing side.

**Evidence:**
- `grep` for `secrets.token|token_urlsafe|token_hex|os.urandom|randbytes` across `src/` → 0 production matches (only `.kilo/commands/...` docs).
- `users` app contains only `views/consent.py`; no login/issue view (`filesystem_list_directory src/backend/apps/users/views`).
- `LoginToken.objects.create` appears only in tests (`test_sweep_commands.py:264`), never in production issuance code.

**Recommendation:** Implement the issuance side: a web view/endpoint that generates a token via `secrets.token_urlsafe(24)` (≈192 bits; for ≥256 bits use `secrets.token_bytes(32).hex()` or `token_urlsafe(32)`), stores only the SHA-256 hash, sets `expires_at = now + 5min`, and renders the deep-link using `BOT_USERNAME`. Without this the QR "Login via Telegram" feature described in US-S1 cannot function; the bot claim has nothing to claim. This is the single largest correctness gap in the phase.

---

### AUT-002: Web consumption (phase 2 — set `consumed_at`) does not exist

| Field | Value |
|-------|-------|
| **ID** | AUT-002 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/users/` (no consumption view), `src/telegram_bot/handlers/login.py:100-126` (only phase 1) |
| **Classification** | mandatory |

**Description:** The model docstring (`models.py:110`) and spec describe a **two-phase atomic claim**: (1) bot sets `telegram_id`; (2) **web sets `consumed_at`**. `consumed_at` is **never assigned in production code** — a repo-wide search for `consumed_at=` yields matches only in tests, docs, and the deprecated wiki. The web `UPDATE ... SET consumed_at=now() WHERE telegram_id IS NOT NULL AND consumed_at IS NULL AND expires_at > now()` is documented but not implemented. A claimed token therefore stays `consumed_at IS NULL` indefinitely (until the cleanup sweep deletes it on `created_at` age), so the "consumed-once / replay-protected" property that the web side is supposed to enforce is never realized. No web session is ever established from a successful claim.

**Evidence:**
- `grep` for `consumed_at=` → matches only `test_sweep_commands.py:289,298` (tests), `docs/02-database/db-schema.md:73`, `wiki-deprecated/*` (docs). No production write.
- `claim_login_token` (`login.py:100-126`) only performs phase 1 (`telegram_id` update); no caller sets `consumed_at`.

**Recommendation:** Implement the web consumption step: on login completion, perform the documented atomic `UPDATE login_tokens SET consumed_at=now() WHERE token_hash=? AND telegram_id IS NOT NULL AND consumed_at IS NULL AND expires_at > now()` and then establish the Django session (see AUT-003). This closes the replay/consumed-once guarantee owned by this phase.

---

### AUT-003: Web session is never established from a claim (no `auth.login`, no session creation)

| Field | Value |
|-------|-------|
| **ID** | AUT-003 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/users/` (no login view), `src/telegram_bot/handlers/login.py:79-97` (bot only creates user, never a web session) |
| **Classification** | mandatory |

**Description:** Per spec §H the site "authenticates by `telegram_id` (create/find)" and issues a "persistent session cookie". In the current code the **bot** calls `get_or_create_user` (`login.py:80-85`) and answers the user in Telegram — it never touches the web session. The web process has no code path that reads a claimed `LoginToken`, looks up the user by `telegram_id`, and calls Django `auth.login` / `session.cycle_key`. The `SessionMiddleware`/`AuthenticationMiddleware` are installed (`base.py:81,84`) and `SESSION_COOKIE_SECURE=True` is set (`base.py:48`, `prod.py:16`), but nothing ever populates the session. End result: there is no working web login at all — buyers/sellers cannot be authenticated on the site via the documented flow. (Cookie attributes themselves are correctly configured; the missing link is the establishment step.)

**Evidence:**
- Repo-wide grep for `auth.login|login(|session.save|cycle_key` → only `services/account_state.py:can_login` definition, no session establishment call.
- `users/urls.py` exposes only `consent/accept/` and `consent/decline/`; no login route.
- `login.py:79-97` ends with a Telegram reply, no web session action.

**Recommendation:** Add a web endpoint (e.g. polling/redirect) that, given the `token_hash` (or a short-lived session key handed back from the bot flow), performs phase 2 (AUT-002) and then `auth.login(request, user)` with `session.cycle_key()` to defeat session fixation. Decide the bot↔web handoff (callback URL vs. status poll) and document it. Until then the entire auth surface is non-functional on the web side.

---

### AUT-004: `hmac.compare_digest` is claimed in code/docstring but NOT used

| Field | Value |
|-------|-------|
| **ID** | AUT-004 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION / DOC-UPDATE |
| **Affected Modules** | `src/telegram_bot/handlers/login.py:106` (docstring), `docs/01-spec/...` §H, `docs/02-database/db-schema.md` |
| **Classification** | advisory |

**Description:** The docstring of `claim_login_token` states "Uses constant-time comparison via hmac.compare_digest" and the spec repeatedly asserts the claim uses `hmac.compare_digest`. In reality the implementation validates the token by passing `token_hash` as a plain equality filter to the ORM: `LoginToken.objects.filter(token_hash=token_hash, ...).update(...)`. There is **no `import hmac`** and **no `compare_digest` call** anywhere in the codebase (grep confirms a single match — the docstring text itself). Functionally, the hash is looked up by indexed equality in SQL, which is acceptable; but the documented "constant-time comparison" property is **misrepresented**, and the audit dimension (b) "No `==` on secrets / constant-time utility used" is therefore unverifiable as documented.

**Evidence:**
- `grep` for `compare_digest|hmac.` across `src/` → 1 match: `login.py:106` (docstring only). No import, no call.
- `login.py:114-119` uses ORM equality filter, not `hmac.compare_digest`.

**Recommendation:** Either (a) remove the misleading "constant-time" claim from the docstring and spec and document that validation is an indexed hash-equality DB lookup (accurate, simpler), or (b) if constant-time is genuinely desired, perform the comparison in Python against the fetched row using `hmac.compare_digest`. Given the token is a SHA-256 hash looked up by a unique indexed column, option (a) is the more maintainable choice — update docs, not code. This is a documentation-accuracy issue, not a live vulnerability.

---

### AUT-005: `can_login()` is defined and exported but never invoked (dead code)

| Field | Value |
|-------|-------|
| **ID** | AUT-005 |
| **Severity** | LOW |
| **Type** | DEAD-CODE |
| **Affected Modules** | `src/backend/apps/users/services/account_state.py:80-99`, `src/backend/apps/users/services/__init__.py:6,20` |
| **Classification** | advisory |

**Description:** `can_login(user)` implements a ban check intended to gate authentication, but a repo-wide search shows it is **never called** from any view, middleware, or handler — only re-exported from the services package. Because the web login flow does not exist (AUT-001/002/003), this gate is currently inert. Per the dead-code policy, before any removal, investigate its intended wiring: it should be called inside the web consumption/login step (AUT-003) to refuse `is_banned` users.

**Evidence:**
- `grep` for `can_login` in `src/` → only `account_state.py:80` (def) and `services/__init__.py:6,20` (re-export). No call sites.

**Recommendation:** When implementing AUT-003, wire `can_login(user)` into the web login completion to enforce the ban gate (spec §H "No silent failures"). Keep the function; do not delete until its purpose/placement is confirmed. Update docs if the gate is intentionally web-only.

---

### AUT-006: Consumed-token cleanup keyed on `created_at`, not `consumed_at`

| Field | Value |
|-------|-------|
| **ID** | AUT-006 |
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/core/management/commands/cleanup_login_tokens.py:45-50` |
| **Classification** | advisory |

**Description:** The cleanup command deletes tokens that are expired (`expires_at < now`) OR "consumed over 24 hours ago". However the "consumed" branch filters on `created_at__lt=consumed_cutoff` (`cleanup_login_tokens.py:48-49`), not `consumed_at__lt=consumed_cutoff`. Since `consumed_at` is currently never set (AUT-002), this branch is effectively inert today; but even once AUT-002 lands, a token claimed/consumed moments after creation will not be eligible for the "consumed >24h" cleanup until 24h after `created_at`, which is the intended window — so the practical impact is minor. The mismatch is still a latent correctness bug and a spec deviation (spec says "consumed over 24 hours ago").

**Evidence:**
- `cleanup_login_tokens.py:45-50`: second queryset branch is `LoginToken.objects.filter(consumed_at__isnull=False, created_at__lt=consumed_cutoff)` — uses `created_at`, not `consumed_at`.

**Recommendation:** Change the second branch to `consumed_at__lt=consumed_cutoff` so the retention window is measured from consumption time, matching the documented behavior. Trivial fix.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH | 2 |
| MEDIUM | 1 |
| LOW | 2 |

## Mandatory Fixes

- **AUT-001** (CRITICAL): Implement web-side token issuance (CSPRNG + SHA-256 hash stored, raw never persisted, QR/deep-link rendered).
- **AUT-002** (HIGH): Implement web consumption phase 2 (set `consumed_at` atomically).
- **AUT-003** (HIGH): Establish the web session from a claimed token (`auth.login` + `cycle_key`).

## Advisory Recommendations

- **AUT-004** (MEDIUM): Correct the `hmac.compare_digest` misrepresentation in docstring + spec (or truly use it).
- **AUT-005** (LOW): Wire `can_login()` into the web login step; do not delete.
- **AUT-006** (LOW): Fix cleanup sweep to key on `consumed_at`, not `created_at`.

## Doc Updates Needed

- **AUT-004** — docs/01-spec technical-specification.md §H and docs/02-database/db-schema.md assert constant-time `hmac.compare_digest`; reality is indexed hash-equality. Update docs to match code (or vice-versa).
- **AUT-001 / AUT-002 / AUT-003** — spec describes a complete dual-process flow that is only partially implemented (bot claim only). Docs currently imply a finished feature; mark as not-yet-implemented or track via task.
