---
id: pii-consent-middleware-fix
domain: plan
source: .ai/audit/99-validation/06-pii-consent-validated-findings.md
tags:
  - pii-consent
  - pii-001
  - pii-002
  - pii-003
  - account-state
  - middleware
  - consent
  - block-audit
related:
  - .ai/audit/06-pii-consent/findings.md
  - .ai/audit/99-validation/06-pii-consent-validated-findings.md
  - docs/01-spec/technical-specification.md
  - docs/02-database/db-enums.md
  - src/backend/apps/users/services/account_state.py
  - src/backend/apps/core/services/contact.py
  - src/backend/apps/users/services/deletion.py
  - src/backend/apps/users/services/consent_record.py
  - src/backend/apps/users/schemas.py
  - src/backend/apps/users/views/consent.py
  - src/backend/apps/users/context_processors.py
  - src/backend/apps/core/enums.py
  - src/backend/apps/core/tests/test_contact.py
  - src/backend/apps/users/tests/test_account_state.py
  - src/backend/apps/users/tests/test_deletion.py
  - src/backend/apps/users/tests/test_consent_context.py
---

# Execution Plan 19 — PII Consent: Middleware Fix

## 0. Critical Working-Tree Context (Read Before Executing)

### 0.1 Telegram bot source tree restored

**Status: RESOLVED** — On 2026-09-15, the Tech Lead restored the `src/telegram_bot/`
package from git commit `1dcdbd7` (the commit immediately before the deletion at `2b018a9`)
using `git restore --source=1dcdbd7 -- src/telegram_bot/`. All 38 bot files are now present
in the main worktree. The restoration itself is committed separately before any PII-001/003 work.

### 0.2 No-op bug already fixed

**Status: RESOLVED** — The restored code (commit `1dcdbd7`) already includes the AUT-003 fix:
`AccountStateMiddleware` is registered on `dp.update.middleware()` (main.py:62, conftest.py:80),
not `dp.message.middleware()`. The `isinstance(event, Update)` guard (permissions.py:61) is
correct — the middleware receives `Update` objects and the guard passes. **B2 (research gate)
and B3 (no-op fix) are MOOT.** The DECLINE narrowing (B4) is the sole remaining PII-001 code fix.

### Original deleted files (restored)

The following files were deleted in commit `2b018a9` and restored from `1dcdbd7`:

| Deleted File | Contains |
|---|---|
| `src/telegram_bot/main.py` | Bot entry point; middleware registration |
| `src/telegram_bot/middlewares/permissions.py` | `AccountStateMiddleware` |
| `src/telegram_bot/middlewares/__init__.py` | Package re-exports |
| `src/telegram_bot/handlers/login.py` | `handle_login_deep_link`, `handle_login_orm` |
| `src/telegram_bot/handlers/contact.py` | `handle_contact_start`, `handle_contact_orm`, `CONTACT_PATTERN` |
| `src/telegram_bot/handlers/language.py` | `/language` command handler |
| `src/telegram_bot/middlewares/connection.py` | `DatabaseConnectionMiddleware` |
| `src/telegram_bot/middlewares/update_id_dedup.py` | `UpdateIdDedupMiddleware` |
| `src/telegram_bot/lifecycle.py` | Startup/shutdown hooks, `LivenessMiddleware` |
| `src/telegram_bot/tests/conftest.py` | Bot test fixtures (`dp`, `user`, etc.) |
| `src/telegram_bot/tests/test_account_state_middleware.py` | 17 test items (deleted but in git history at `aafaa61`) |
| `src/telegram_bot/tests/test_contact_us.py` | Contact handler tests |
| `src/telegram_bot/tests/test_login.py` | Login flow tests |
| `src/telegram_bot/handlers/alerts.py` | Alert subscription handler |
| `src/telegram_bot/handlers/ad_create.py` | Ad creation FSM handlers |
| `src/telegram_bot/handlers/ad_copy.py` | Ad copy FSM handlers |
| `src/telegram_bot/services/rate_limit.py` | Rate limiting service |
| `src/telegram_bot/states.py` | FSM state definitions |
| `src/telegram_bot/schemas/*` | Pydantic DTOs for bot payloads |

### 0.2 Broken imports in surviving backend tests

Three backend test files import from the deleted `telegram_bot` package and
will **fail at collection time** until the import is removed or the package is
restored:

```
src/backend/apps/core/tests/test_contact.py:19
    from telegram_bot.handlers.contact import CONTACT_PATTERN

src/backend/apps/media/tests/test_thumbnail_integration.py:44
    from telegram_bot.handlers.ad_create import save_photo

src/backend/apps/media/tests/test_save_photo_exif.py:19
    from telegram_bot.handlers.ad_create import save_photo
```

### 0.3 Discrepancy: no-op bug vs. validated findings

The auditor's critical codebase findings (`context_a`) describe `AccountStateMiddleware`
as a **no-op**: registered via `dp.message.middleware()` (receiving `Message` events),
but `__call__` checks `isinstance(event, Update)` — since `Message` is not `Update`,
the guard short-circuits on every event, making all state checks unreachable.

The **validated findings report** (`.ai/audit/99-validation/06-pii-consent-validated-findings.md`)
describes the middleware as **functional** — it intercepts messages and blocks DECLINE
users from all handlers including contact deep-links.

**Reconciliation (verified against git history):**

Commit `544fc1e` ("fix(auth): move AccountStateMiddleware to dp.update to fix
isinstance no-op (AUT-003)") moved the registration from `dp.message.middleware()`
to `dp.update.middleware(AccountStateMiddleware())`. The `isinstance(event, Update)`
guard became correct (Update events pass the check). The subsequent commit `7ed761c`
("refactor(pc-003)") delegated `_check_user_state` to `get_account_state` and
introduced state-specific denial messages. The latest bot source (commit `aafaa61`)
confirmed:

- Registration: `dp.update.middleware(AccountStateMiddleware())` in `main.py`
- `__call__`: `if not isinstance(event, Update): return await handler(event, data)`
  — now correct because the event IS an `Update`
- `_check_user_state`: delegates to `get_account_state`, returns state-specific messages
- DECLINE denial message: `"Consent declined: you can browse but cannot post. Contact still works."`
- The denial message **contradicts** the enforced behavior (it promises "Contact still works"
  but `__call__` returns `None`, never reaching the handler) — strong evidence the
  over-block is unintended

Because the code is now **deleted**, both the no-op and the DECLINE-narrowing must be
addressed during re-implementation. The Researcher/Implementor must verify the
middleware registration when the bot code is restored and choose between the two
fix options presented below.

### 0.4 Phase-06 plan already executed

The backend-side phase-06 plan (`.kilo/plans/phase-06-pii-consent-execution-dag.md`)
has been **fully implemented** in the current working tree. Verified:

- `decline_consent` clears `consent_given_at` (deletion.py:61–63)
- `withdraw_consent` clears `consent_given_at` + `email` (deletion.py:135–149)
- `_anonymize_ip` handles IPv6 `/64` masking (consent_record.py:20–34)
- `ConsentSubmission.categories()` uses `CookieCategory` enum (schemas.py:28–38)
- All consent views pass `{CookieCategory.ANALYTICS: ...}` (consent.py:160–163, 209–211, 248–251)
- `context_processors.consent_state` zeros analytics/preferences for declined/withdrawn (lines 68–72)
- `get_account_state` shared predicate exists (account_state.py:26–48)
- `_check_seller_contactable` does NOT check `is_declined` (contact.py:27–45)

The **bot-side** phase-06 work (i18n wrapping, permissions.py refactor) existed
only in the deleted `src/telegram_bot/` and must be re-implemented if the bot
is rebuilt.

---

## 1. Findings at a Glance

| ID | Title | Severity | Status | Scope |
|---|---|---|---|---|
| PII-001 | `AccountStateMiddleware` over-blocks DECLINE users from contact deep-links | HIGH (mandatory) | **Open** | Bot middleware |
| PII-002 | Consent banner does not cover bot `/start`; consent never established | HIGH | **BLOCKED** — spec conflict (technical-specification.md §K:104 vs audit §6) | Bot login handler |
| PII-003 | `db-enums.md:214-217` and `technical-specification.md:112-113` stale — `CookieCategory` enum IS used at runtime | LOW | **Open** (doc-only) | Documentation |

### 1.1 PII-002 — BLOCKED (do not implement)

Per the validated findings, PII-002 is **BLOCKED until the Product Owner resolves**
the spec conflict between `technical-specification.md` §K line 104
("no separate bot confirmation required") and audit §6 line 75
("the consent banner must cover BOTH web and bot entry points").

- `handle_login_orm` (login.py:158–214) creates a `User` via `get_or_create`
  without setting `consent_given_at` or calling `give_consent` /
  `record_consent_action`.
- Shared consent services already exist and are web-only:
  `users/services/deletion.py:224` `give_consent`,
  `users/services/consent_record.py:31` `record_consent_action`.
- No code change is included in this plan. This block exists to track the
  dependency and risk containment.

### 1.2 PII-003 — Doc-only (trivial)

`docs/02-database/db-enums.md:214-217` asserts that `CookieCategory` enum members
are "not referenced by runtime code" and that categories are stored as "plain string
keys." This is **false** — all runtime code uses the enum members:

- `apps/users/schemas.py:28-38` — `ConsentSubmission.categories()` returns
  `dict[CookieCategory, bool]`, built with `{CookieCategory.ANALYTICS: ...}`.
- `apps/users/services/consent_record.py:40` — `record_consent_action` typed
  `dict[CookieCategory, bool]`.
- `apps/users/views/consent.py:160-163, 209-211, 248-251` — all three consent
  views pass `{CookieCategory.ANALYTICS: ...}` / `{CookieCategory.PREFERENCES: ...}`.
- `test_consent_records.py:34` confirms `record.categories == {"analytics": True,
  "preferences": True}` — StrEnum `.value` serialization is stable.

`technical-specification.md` §K:112-113 repeats the same stale claim
("`CookieCategory` ... is not referenced at runtime"). Both must be corrected.

---

## 2. Block Summary Table

| ID | Name | PII | Agent(s) | Risk | Ordering | Status |
|---|---|---|---|---|---|---|
| B1 | PII-003 doc sync — `db-enums.md` + `technical-specification.md` §K | PII-003 | Doc-specialist → Validator | None | Any | Ready |
| B2 | PII-001-A research gate — no-op fix approach | PII-001 | (MOOT — already fixed) | — | — | Skipped |
| B3 | PII-001-A implementation — make middleware functional | PII-001 | (MOOT — already fixed) | — | — | Skipped |
| B4 | PII-001-B — narrow DECLINE block for contact deep-links | PII-001 | Implementor | High | After B1 | Ready |
| B5 | PII-001 — test contract updates | PII-001 | Implementor | Medium | After B4 | Gated on B4 |
| B6 | Code deletion prerequisite — restore bot scaffolding | PII-001/002 | (DONE — restored from 1dcdbd7) | — | — | Complete |
| B7 | Broken import cleanup — 3 backend test files | PII-001 | (RESOLVED by restoration) | Low | Before B5 | Complete |
| B8 | PII-002 PO resolution gate | PII-002 | PO, Validator | — | — | Blocked |

---

## 3. Per-Block Detail

### Block B1 — PII-003: Doc Sync (CookieCategory enum is used at runtime)

**Goals:**
- Correct `db-enums.md:214-217` to state that `CookieCategory` enum members
  are used as dict keys throughout runtime code.
- Correct `technical-specification.md:112-113` (section K) with the same correction.
- No code changes.

**File / module / symbol targets:**
- `docs/02-database/db-enums.md` — `CookieCategory` section, lines 214–217 (the
  blockquote at the end of the section).
- `docs/01-spec/technical-specification.md` — section K, lines 112–113 (the
  blockquote within the "Script gating" bullet).

**Implementation sequence:**
1. `db-enums.md`: Replace the stale blockquote with:
   > `CookieCategory` members are used as dict keys throughout the consent
   > subsystem — `ConsentSubmission.categories()` (schemas.py) returns
   > `dict[CookieCategory, bool]`, `record_consent_action` (consent_record.py)
   > accepts `dict[CookieCategory, bool]`, and all three consent views
   > (consent_accept, consent_decline, consent_withdraw) pass
   > `{CookieCategory.ANALYTICS: ...}` / `{CookieCategory.PREFERENCES: ...}`.
   > The `JSONField` stores the StrEnum `.value` strings (`"analytics"`,
   > `"preferences"`) via StrEnum serialization — no string-literal code paths
   > exist. `ESSENTIAL` cookies are always-on and intentionally not stored in
   > the `categories` dict.
2. `technical-specification.md`: Same correction in section K.

**Required tests:** None — documentation only.

**Acceptance criteria:**
- No `test_i18n_completeness.py` or other test references db-enums.md content
  (docs are not covered by tests).
- The stale claim ("not referenced at runtime") is removed from both files.
- The corrected text accurately reflects the runtime code (verified by reading
  `schemas.py:28-38`, `consent_record.py:40`, `consent.py:160-163`).

**Risks:** None. Doc-only. No schema, no code, no migration.

**Agents:** Planner (make the edits) → Validator (verify against runtime code).

---

### Block B2 — PII-001-A: Research Gate (No-op Fix Approach Selection)

**Goals:**
- Determine whether `AccountStateMiddleware` is currently registered on
  `dp.message.middleware()` (no-op) or `dp.update.middleware()` (functional).
- If no-op: select between Option A and Option B (see below) based on aiogram 3.x
  best practices, architectural implications, and test coverage requirements.
- Verify deep-link parsing details (how `/start contact_<ad_id>` is routed) and
  callback_query implications (inline "Contact us" button).

**Research questions:**

1. **Current registration state:** Verify the registration line in
   `main.py` and `tests/conftest.py:dp` fixture. If already on `dp.update`,
   the no-op fix is moot — proceed directly to B4 (DECLINE narrowing).

2. **Deep-link parsing:** `handle_login_deep_link` (login.py) receives
   `message.text = "/start contact_<ad_id>"`, splits on whitespace, and passes
   the argument to `handle_contact_start` (contact.py), which matches against
   `CONTACT_PATTERN = re.compile(r"^contact_(\d+)$")` and
   `CONTACT_US_PATTERN = re.compile(r"^contact_us$")`. The middleware must
   replicate this pattern detection to allow DECLINE users through.
   - **Question:** Should the middleware import the pattern regexes from
     `contact.py`, or should the deep-link classification be extracted into a
     shared utility (e.g., `contact.py:parse_deep_link_kind(text) -> ContactDeepLinkKind`)?
   - **Recommendation to Researcher:** Extract a shared classifier to avoid
     duplicating regex patterns in middleware and handler.

3. **Callback query implications:** The inline "Contact us" button
   (`callback_data="contact_us"`) triggers `handle_contact_us_callback` in
   `contact.py`. This is a `CallbackQuery` event, not a `Message`.
   - **Option A (dp.update.outer_middleware):** Gates ALL event types
     (messages + callbacks). DECLINE narrowing must handle callback_query
     events too (`event.callback_query.data == "contact_us"`).
   - **Option B (rewrite for Message):** Only gates `Message` events.
     CallbackQuery events bypass the middleware entirely — meaning BANNED/DELETED
     users could trigger callback handlers (security risk). The Researcher must
     weigh this trade-off.
   - **Question for Auditor:** Are there other callback_query handlers that
     need account-state gating (e.g., ad-creation FSM callbacks, alert
     subscription toggles)?

**Option A — Move registration to `dp.update.outer_middleware()`:**

| Aspect | Detail |
|---|---|
| File targets | `main.py` (registration line), `tests/conftest.py:dp` fixture (mirrors registration) |
| Mechanism | Outer update-level middleware receives `Update` objects → `isinstance(event, Update)` passes → `event.message` / `event.callback_query` access is valid |
| Pros | Minimal code change (registration-only); gates ALL event types (messages + callbacks); matches the AUT-003 fix already applied in commit `544fc1e` |
| Cons | Gates callback_query events — must verify no existing callback handlers break under the gate; DECLINE narrowing must handle both Message and CallbackQuery paths; `DatabaseConnectionMiddleware` is already on `dp.update.outer_middleware()`, so `AccountStateMiddleware` would be at the same level (ordering matters) |
| Test impact | `TestCallPipeline` tests already exercise Update events — only need to add contact-deep-link assertions; `conftest.py` `dp` fixture must mirror the new registration |
| aiogram best practice | Update-level outer middleware is the canonical pattern for universal guards in aiogram 3.x |

**Option B — Rewrite middleware for `Message` events:**

| Aspect | Detail |
|---|---|
| File targets | `permissions.py:AccountStateMiddleware.__call__`, `__call__` signature |
| Mechanism | Remove `isinstance(event, Update)` guard; access `event.from_user`, `event.text` directly on `Message`; handle `CallbackQuery` separately (or skip) |
| Pros | No registration change needed (stays on `dp.message`); simpler event access (no Update unwrapping) |
| Cons | CallbackQuery events bypass the middleware entirely (security gap — banned/deleted users could trigger callbacks); more invasive code change (rewrites `__call__` body, not just registration); must separately handle `Message` from `CallbackQuery.message` if callback gating is needed |
| Test impact | Existing `TestCallPipeline` tests (which pass `Update` objects) would need rewriting to pass `Message` objects; callback_query coverage would need a separate mechanism |
| aiogram best practice | Less aligned — aiogram 3.x documentation recommends update-level middleware for cross-cutting concerns; `dp.message.middleware()` is considered narrow |

**Decision needed from Researcher:**
- If the no-op is confirmed present: choose Option A or Option B.
- If the no-op is already fixed (per git history): skip to B4.
- For DECLINE narrowing: decide whether callback_query events
  (`callback_data="contact_us"`) should also be exempt from the DECLINE block,
  and whether the contact-pattern detection should be a shared service function.

**Agents:** Researcher (select approach, evaluate trade-offs), Auditor (verify
deep-link parsing and callback_query coverage), Validator (review approach
selection).

---

### Block B3 — PII-001-A: Implement No-op Fix (if selected)

**Goals:**
- Make `AccountStateMiddleware` functional by ensuring it receives events it
  can act on.
- If Option A selected: change registration from `dp.message.middleware()` to
  `dp.update.outer_middleware()` in both `main.py` and `conftest.py:dp` fixture.
- If Option B selected: rewrite `__call__` to accept `Message` events directly.

**File / module / symbol targets (Option A):**
- `src/telegram_bot/main.py` — `main()` function, middleware registration line
  (currently `dp.update.middleware(AccountStateMiddleware())` per git history
  at `aafaa61`; the fix re-confirms or corrects this based on Researcher decision).
- `src/telegram_bot/tests/conftest.py` — `dp` fixture, mirrors production
  registration.
- `src/telegram_bot/middlewares/permissions.py` — `AccountStateMiddleware.__call__`
  (verify `isinstance(event, Update)` guard is correct for the chosen registration).

**File / module / symbol targets (Option B):**
- `src/telegram_bot/middlewares/permissions.py` — `AccountStateMiddleware.__call__`
  signature and body (remove `isinstance(event, Update)` guard, access
  `event.from_user` / `event.text` directly; handle `CallbackQuery` extraction).
- `src/telegram_bot/middlewares/permissions.py` — `_check_user_state` (may need
  signature change from `chat_id: int` to accept `User` or `Message`).

**Implementation sequence (Option A):**
1. In `main.py`, confirm or change registration from `dp.message.middleware()`
   to `dp.update.outer_middleware()` (or `dp.update.middleware()` if
   `DatabaseConnectionMiddleware` ordering requires it).
2. In `conftest.py:dp` fixture, mirror the same registration.
3. Verify `__call__`'s `isinstance(event, Update)` guard is consistent with the
   registration (if on `dp.update`, the guard should pass; if on `dp.message`,
   the guard should be removed or inverted).

**Implementation sequence (Option B):**
1. Rewrite `__call__` to accept `Message` directly (remove the `Update` isinstance
   guard, access `event.from_user.id`, `event.text`).
2. If callback_query support is needed, add a separate handler or convert
   `CallbackQuery.message` to a `Message` before processing.
3. Update `main.py` and `conftest.py` registration to remain on `dp.message`.

**Required tests (Option A):**
- `TestCallPipeline.test_call_passes_update_event` — verifies Update events
  reach the handler (already exists in git history at `aafaa61`).
- `TestCallPipeline.test_call_blocks_banned_user` — verifies BANNED users are
  blocked.
- `TestCallPipeline.test_call_handles_callback_query_update` — verifies callback
  events are gated (critical for Option A).

**Required tests (Option B):**
- Tests must pass `Message` objects (not `Update`).
- `TestCallPipeline` tests need rewriting to use `Message` doubles.
- Callback query gating may need a separate test or may be skipped (Auditor must verify).

**Acceptance criteria:**
- Middleware `__call__` runs `_check_user_state` for all relevant event types.
- BANNED / DELETED / REVOKED users are blocked (denial message sent, handler not called).
- Normal users proceed to handler without denial message.
- The `isinstance` guard (if retained) does not short-circuit functional events.

**Dependencies:** B2 (Researcher decision). B6 if bot code was deleted.

**Risks:**
- **High** — behavioral change to the universal guard. If the registration level
  changes, callback_query events may newly be gated, potentially breaking
  ad-creation FSM callbacks, alert toggles, language selection, etc.
- **High** — `DatabaseConnectionMiddleware` is already on
  `dp.update.outer_middleware()`. Adding `AccountStateMiddleware` at the same
  level requires verifying middleware ordering (outer middlewares run in
  registration order; AccountStateMiddleware must run AFTER
  DatabaseConnectionMiddleware to have a DB connection).
- **Medium** — Bot tests (`conftest.py:dp` fixture) must mirror production
  registration exactly; mismatch between test and prod registration hides bugs.

**Agents:** Researcher (select approach), Implementor (apply changes), Validator
(review registration + ordering).

---

### Block B4 — PII-001-B: Narrow DECLINE Block for Contact Deep-Links

**Goals:**
- Allow DECLINE users to reach `contact_us` and `contact_<ad_id>` deep-links.
- Continue blocking DECLINE users from login (`can_login`) and `/post`
  (`ads_auto_publish`).
- Continue blocking BANNED / DELETED / REVOKED users from ALL interactions.
- The contact R2 service (`core/services/contact.py:_check_seller_contactable`)
  already enforces seller-side safety (does NOT check `is_declined` for the
  buyer) — no change needed there.

**Design decision (for Researcher/Implementor):**

The middleware currently conflates two access scopes in a single predicate:
`_check_user_state` returns a blanket "can_interact" boolean. The clean fix
introduces an **access scope** concept:

- `LOGIN_SCOPE` — blocks DECLINE for login/FSM entry (but allows contact)
- `CONTACT_SCOPE` — allows DECLINE (and all states except BANNED/DELETED/REVOKED)
- `BLOCK_ALL_SCOPE` — blocks BANNED/DELETED/REVOKED unconditionally

The middleware classifies the incoming event:
- `/start contact_us` → CONTACT_SCOPE
- `/start contact_<ad_id>` → CONTACT_SCOPE
- `callback_data="contact_us"` → CONTACT_SCOPE
- `/post` or ad-creation FSM → LOGIN_SCOPE (publish check)
- Anything else → LOGIN_SCOPE

**File / module / symbol targets:**
- `src/telegram_bot/middlewares/permissions.py` — `AccountStateMiddleware`:
  - `__call__`: add deep-link classification BEFORE `_check_user_state`.
    If the event is a contact deep-link and the user is DECLINE (but not
    BANNED/DELETED/REVOKED), skip the block and proceed to handler.
  - `_check_user_state`: add a `scope` parameter (or split into two methods:
    `_check_login_state` and `_check_contact_state`) so DECLINE is evaluated
    differently per scope.
  - Consider extracting `ContactDeepLinkKind` enum +
    `classify_deep_link(text: str | None) -> ContactDeepLinkKind` to a shared
    location (see B2 research question about shared classifier).

- `src/telegram_bot/handlers/contact.py` — export `CONTACT_PATTERN` and
  `CONTACT_US_PATTERN` (or a combined classifier function) for reuse by the
  middleware, to avoid duplicating regex patterns.
  - Alternatively: `src/telegram_bot/handlers/login.py` — export the deep-link
    classification from where it's already consumed.

- `src/telegram_bot/handlers/login.py` — `handle_login_deep_link` is the
  handler that receives `/start contact_...`. The middleware runs BEFORE this
  handler, so the middleware must independently detect the contact pattern.
  Confirm: `message.text` contains the full `/start contact_<ad_id>` string.

**Implementation sequence:**
1. (If bot code was deleted) Restore `permissions.py`, `main.py`, `contact.py`,
   `login.py`, `handlers/__init__.py`, `middlewares/__init__.py` at their
   `aafaa61` state (or re-implement with the no-op fix from B3).
2. Add a deep-link classifier function (e.g., in `contact.py` or a new
   `contact_links.py` utility module):
   ```python
   class ContactDeepLinkKind(StrEnum):
       SELLER_CONTACT = "seller_contact"
       SUPPORT_DESK = "support_desk"

   def classify_contact_deep_link(text: str | None) -> ContactDeepLinkKind | None:
       if text is None:
           return None
       args = text.split(maxsplit=1)
       if len(args) < 2:
           return None
       deep_link = args[1]
       if CONTACT_US_PATTERN.match(deep_link):
           return ContactDeepLinkKind.SUPPORT_DESK
       match = CONTACT_PATTERN.match(deep_link)
       if match:
           return ContactDeepLinkKind.SELLER_CONTACT
       return None
   ```
3. In `AccountStateMiddleware.__call__`, before `_check_user_state`:
   - Extract `message.text` from the `Update`.
   - Call `classify_contact_deep_link(text)`.
   - If the result is not `None` AND the user is DECLINE (but NOT
     BANNED/DELETED/REVOKED), allow through (proceed to handler).
   - If the result is not `None` AND the user is BANNED/DELETED/REVOKED,
     block as before.
4. Modify `_check_user_state` (or add `_check_contact_state`) to handle the
   DECLINE exemption:
   - DECLINE + contact scope → `(True, "")` (allow through)
   - DECLINE + login scope → `(False, "Consent declined: you can browse...")`
   - BANNED/DELETED/REVOKED + any scope → `(False, ...)`
5. Fix the contradiction in the DECLINE denial message: it currently says
   "Contact still works" but blocks contact. After the narrowing, the message
   is accurate.

**Required tests:**
- `test_declined_user_can_reach_contact_ad_deep_link` — DECLINE user sends
  `/start contact_42` → handler is called (not blocked).
- `test_declined_user_can_reach_contact_us_deep_link` — DECLINE user sends
  `/start contact_us` → handler is called.
- `test_declined_user_blocked_from_post` — DECLINE user sends `/post` → blocked.
- `test_declined_user_blocked_from_normal_message` — DECLINE user sends
  `/language` → blocked (login scope).
- `test_banned_user_blocked_from_contact` — BANNED user sends `/start contact_42`
  → blocked (BANNED blocks everything).
- `test_callback_contact_us_not_blocked_for_declined` — DECLINE user triggers
  `callback_query` with `data="contact_us"` → handler is called (only if
  Option A was chosen and callback gating is implemented).
- `test_classify_contact_deep_link` — unit test for the classifier function
  (valid patterns, invalid patterns, None input).

**Acceptance criteria:**
1. DECLINE user can reach `handle_login_deep_link` → `handle_contact_start` →
   `handle_contact_orm` → `get_seller_for_contact` for both `contact_us` and
   `contact_<ad_id>` paths.
2. DECLINE user is still blocked from `/post` and `/language` and other
   non-contact commands.
3. BANNED / DELETED / REVOKED users are blocked from ALL paths including
   contact.
4. The contact R2 service (`_check_seller_contactable`) remains unchanged.
5. The `can_login` service function remains unchanged (already spec-correct).
6. The denial message for DECLINE no longer contradicts behavior.

**Dependencies:** B3 (middleware must be functional first) OR B6 (code restoration).

**Risks:**
- **High** — behavioral change to the universal guard. A regression could
  either (a) allow blocked users through (security), or (b) block contact for
  DECLINE users (spec deviation).
- **High** — the deep-link classification must stay in sync with the handler's
  own classification in `handle_login_deep_link`. If the patterns drift, the
  middleware may allow/deny inconsistently. Mitigation: extract shared
  classifier (research decision in B2).
- **Medium** — callback_query gating: if Option A was chosen, callback events
  are now gated, and the DECLINE narrowing must handle `callback_data` parsing.
  If Option B was chosen, callbacks bypass the middleware (banned users could
  trigger callbacks — Auditor must verify this is acceptable).
- **Medium** — test contract change: `test_account_state_middleware.py` must
  be updated. The old `test_call_blocks_declined_user` (asserts handler NOT
  called for `/start contact_42`) must change to assert handler IS called for
  contact deep-links but NOT for `/post`.

**Agents:** Planner (design), Implementor (implementation), Auditor (verify
  deep-link parsing + callback path), Validator (review access-scope model).

---

### Block B5 — PII-001: Test Contract Updates

**Goals:**
- Update `test_account_state_middleware.py` to reflect the corrected contract:
  DECLINE blocks login/post only, not contact.
- Add coverage for the DECLINE contact exemption.
- Add coverage for the deep-link classifier.

**File / module / symbol targets:**
- `src/telegram_bot/tests/test_account_state_middleware.py` — modify:
  - `test_call_blocks_declined_user` → rename to
    `test_call_blocks_declined_user_for_non_contact` (assert DECLINE blocks
    `/post`, `/language`, etc.).
  - Add `test_declined_user_allowed_for_contact_deep_link` — DECLINE user
    with `/start contact_<ad_id>` → handler called, no denial message.
  - Add `test_declined_user_allowed_for_contact_us` — DECLINE user with
    `/start contact_us` → handler called.
  - Add `test_banned_user_blocked_for_contact_deep_link` — BANNED user with
    `/start contact_42` → blocked (BANNED blocks everything).
- `src/telegram_bot/tests/test_contact_us.py` — verify existing tests still
  pass after middleware narrowing (contact handlers are now reachable by DECLINE
  users; the R2 gate in `get_seller_for_contact` still blocks unreachable sellers).
- `src/telegram_bot/tests/test_login.py` — verify DECLINE users can now reach
  `handle_login_deep_link` with a contact deep-link (previously blocked by middleware).

**Implementation sequence:**
1. Update `test_call_blocks_declined_user` → split into contact-allowed and
   non-contact-blocked variants.
2. Add new test cases for the DECLINE contact exemption (see B4 test list).
3. Add unit tests for the deep-link classifier (if extracted as shared function).
4. Run bot test suite: `$dc run --rm -e PYTEST_OPTS="-k test_account_state_middleware" test`

**Acceptance criteria:**
- All existing `TestCallPipeline` and `TestCrossPredicateAgreement` tests
  pass (with updated assertions for the DECLINE narrowing).
- New tests for DECLINE contact exemption pass.
- `test_contact.py` cross-product (`declined_only_contactable` → True) remains green.

**Dependencies:** B4 (implementation complete).

**Risks:**
- **Medium** — The test contract change encodes the new business rule. If the
  Implementor's test assertions are too narrow, a regression could pass tests
  but fail in production.
- **Low** — Bot tests use `django_db(transaction=True)` + `pytest_asyncio` +
  `xdist_group("bot_concurrent")`; the existing test infrastructure at
  `conftest.py` (restored) handles DB connection cleanup for worker threads.

**Agents:** Test Engineer (design test cases), Implementor (update tests),
  Validator (review coverage).

---

### Block B6 — Code Deletion Prerequisite (Restoration/Verification Gate)

**Goals:**
- Determine whether the `src/telegram_bot/` package must be restored from git
  history before PII-001/002 work can proceed.
- If restoration is needed: identify the correct baseline commit (aafaa61 or
  later) and coordinate with the team that deleted the code.

**Status:** The `src/telegram_bot/` directory is empty in the current working
tree (deleted in commit 2b018a9). Neither PII-001 nor PII-002 can be implemented
without the bot code existing.

**File / module / symbol targets:**
- `src/telegram_bot/main.py` — bot entry point (registration of middleware)
- `src/telegram_bot/middlewares/permissions.py` — `AccountStateMiddleware`
- `src/telegram_bot/middlewares/__init__.py` — package exports
- `src/telegram_bot/handlers/login.py` — deep-link routing
- `src/telegram_bot/handlers/contact.py` — contact handlers
- `src/telegram_bot/handlers/language.py` — language handler (affected by DECLINE narrowing)
- `src/telegram_bot/tests/conftest.py` — `dp` fixture, test DB connection cleanup
- `src/telegram_bot/tests/test_account_state_middleware.py` — existing tests (17 items)
- `src/telegram_bot/tests/test_contact_us.py` — existing contact tests
- `src/telegram_bot/tests/test_login.py` — existing login tests

**Implementation sequence:**
1. **Auditor** verifies: was the deletion intentional (bot re-architecture) or
   accidental? Check commit message, PR description, and related issues.
2. If intentional: determine the re-architecture timeline and whether the new
   bot will have an equivalent `AccountStateMiddleware`. PII-001/002 become
   forward-looking fixes against the re-architecture.
3. If accidental or if restoration is needed: `git checkout aafaa61 --
   src/telegram_bot/` to restore the code at the validation point.
4. After restoration: verify B6's broken-import cleanup (B7) so the test suite
   collects cleanly.

**Acceptance criteria:**
- The Auditor confirms whether the deletion is intentional or needs reversal.
- If restored: `src/telegram_bot/` package exists at the expected commit.
- If intentional: the plan notes the forward-looking nature and adjusts targets.

**Risks:**
- **Critical** — If the bot code is permanently deleted (intentional
  re-architecture), PII-001 and PII-002 may be moot or need re-scoping.
- **High** — If restored from `aafaa61`, the restored code includes the
  `isinstance(event, Update)` guard AND the `dp.update.middleware()` registration
  (both correct). The no-op described in context_a may already be fixed in the
  restored code. The Researcher (B2) must verify.

**Agents:** Auditor (investigate deletion intent), Planner (coordinate with team),
  Validator (verify restoration).

---

### Block B7 — Broken Import Cleanup (3 backend test files)

**Goals:**
- Fix the three backend test files that import from the deleted
  `telegram_bot` package, so the test suite collects cleanly.

**File / module / symbol targets:**
- `src/backend/apps/core/tests/test_contact.py:19` —
  `from telegram_bot.handlers.contact import CONTACT_PATTERN`
  - `CONTACT_PATTERN` is used in `TestContactPattern` (lines 102-121) to test
    the contact deep-link regex. Since the bot handler is deleted, this import
    fails. Fix: inline the regex or mark the test as skipped/pending bot
    restoration. The pattern is `re.compile(r"^contact_(\d+)$")`.
- `src/backend/apps/media/tests/test_thumbnail_integration.py:44` —
  `from telegram_bot.handlers.ad_create import save_photo`
  - `save_photo` is a bot handler function for persisting Telegram-compressed
    photos. Fix: skip the test or move `save_photo` to a shared location.
- `src/backend/apps/media/tests/test_save_photo_exif.py:19` —
  `from telegram_bot.handlers.ad_create import save_photo`
  - Same as above.

**Implementation sequence:**
1. `test_contact.py`: Replace the `CONTACT_PATTERN` import with a local regex
   definition, or mark `TestContactPattern` as `@pytest.mark.skip` with a note
   that it depends on the bot package.
2. `test_thumbnail_integration.py` and `test_save_photo_exif.py`: Mark tests
   that depend on `save_photo` as skip with reason "telegram_bot package
   deleted; pending restoration."

**Acceptance criteria:**
- `src/backend` test suite collects without import errors.
- Skipped tests are clearly marked with the reason.

**Risks:** None — test-only changes, no production code.

**Agents:** Auditor (identify all broken imports), Implementor (apply fixes).

---

### Block B8 — PII-002: PO Resolution Gate

**Goals:**
- Document the spec conflict and escalate to Product Owner.
- Do NOT implement any code changes.

**Spec conflict:**
- `technical-specification.md` §K line 104: "Site banner consent covers all
  PII processing including the bot; **no separate bot confirmation required.**"
- Audit §6 line 75: "the consent banner must cover BOTH web and bot entry
  points; no separate bot confirmation may bypass shared state."
- Research report
  (`docs/97-plans/consent-banner-gdpr-research-report.md:238`): Decision K
  "Site banner covers bot too" recorded as MET ("bot checks same User model
  fields").

**Acceptance criteria:**
- PO resolves the conflict (either: bot `/start` shows a consent prompt, or:
  bot relies on shared `User.consent_given_at` with no separate prompt).
- Once resolved, a new plan block can be created for the chosen approach.

**Agents:** Product Owner, Validator (document the conflict).

---

## 5. Risk Analysis

### PII-001 — High risk

| Risk | Impact | Mitigation |
|---|---|---|
| No-op bug leaves ALL bot users ungated | Security: banned/deleted users can interact with bot | Verify middleware registration before implementing DECLINE narrowing; the Researcher (B2) must confirm whether registration is on `dp.update` or `dp.message` |
| DECLINE narrowing allows too much access | Security: DECLINE users bypass login gate | Restrict exemption to `contact_us` and `contact_<ad_id>` deep-link patterns only; BANNED/DELETED/REVOKED still blocked everywhere |
| DECLINE narrowing blocks too little | Spec deviation: DECLINE users can post or login | Exemption is pattern-based, not state-based; non-contact `/post` and `/language` still blocked for DECLINE |
| Callback query bypass | Security: callback events bypass middleware (Option B) or newly gated (Option A) | Researcher must choose; Auditor must verify all callback handlers are safe |
| Deep-link pattern drift | Correctness: middleware and handler disagree on what is a contact link | Extract shared classifier function (research decision in B2) |
| Test contract regression | Correctness: old tests encode the wrong behavior | B5 updates all assertions; cross-check with `test_contact.py` R2 cross-product |
| Re-implementation after deletion | Correctness: restored code may differ from validation point | Use `aafaa61` as baseline; verify against findings report |

### PII-002 — Blocked (no risk until PO decision)

| Risk | Impact | Mitigation |
|---|---|---|
| If implemented without PO resolution | Architectural: builds "separate bot confirmation" that spec §K:104 disclaims | Do NOT implement until B8 is resolved |

### PII-003 — None

Doc-only. No runtime risk.

---

## 6. Execution Order and Dependencies

```
B1 (PII-003 doc) ────────────────► Validator
      │
      │ (parallel)
      ▼
B4 (PII-001 narrowing) ──► B5 (test updates) ──► Validator
                            │
                            ▼
                        B7 (broken imports RESOLVED)

B8 (PII-002 PO gate) — strictly BLOCKED — no implementation
B2 (research gate)   — SKIPPED (no-op already fixed)
B3 (no-op fix)       — SKIPPED (already on dp.update.middleware)
B6 (code restore)    — COMPLETE (restored from 1dcdbd7, committed)
```

### Ordering constraints:

1. **B1 (PII-003) is independent** — can execute in parallel with B4/B5.
2. **B6 (code restoration) is COMPLETE** — bot code restored from `1dcdbd7`, committed separately.
3. **B7 (broken imports) is RESOLVED** — restoration restored `CONTACT_PATTERN` and `save_photo`, fixing all 3 imports.
4. **B2 and B3 are SKIPPED** — no-op already fixed (registration on `dp.update.middleware()` in both `main.py:62` and `conftest.py:80`). The `isinstance(event, Update)` guard is correct. No research gate needed.
5. **B4 (DECLINE narrowing) follows B1/B6** — can run in parallel with B1 since they touch different files.
6. **B5 (test updates) follows B4** — tests can only be updated after the middleware change exists.
7. **B8 (PII-002 PO gate) is strictly blocked** — no implementation until PO resolves the spec conflict.
5. **B4 (DECLINE narrowing) follows B1** — can run in parallel with B1 since they touch different files.
6. **B5 (test updates) follows B4** — tests can only be updated after the middleware change exists.
7. **B8 (PII-002 PO gate) is strictly blocked** — no implementation until PO resolves the spec conflict.

### Parallelization opportunities:

- **B1** can run in parallel with B6, B7, B8 (no shared code).
- **B7** can run in parallel with B2, B3, B4 (different files).
- **B8** runs in parallel but produces no code changes.

### Sequential dependencies (cannot parallelize):

- B6 → B2 → B3 → B4 → B5 (the PII-001 chain).
- B7 → B5 (test suite must collect before test updates run).

---

## 7. Agent Requirements Summary

| Block | Primary Agent | Supporting Agents | Review Gate |
|---|---|---|---|
| B1 | Planner | Validator | Validator verifies doc matches runtime code |
| B2 | Researcher | Auditor, Validator | Researcher selects approach; Auditor verifies deep-link/callback details |
| B3 | Implementor | Researcher, Validator | Validator reviews registration + middleware ordering |
| B4 | Implementor | Planner, Auditor, Validator | Validator reviews access-scope model + security boundaries |
| B5 | Test Engineer | Implementor, Validator | Validator reviews test coverage for DECLINE contact exemption |
| B6 | Auditor | Planner, Validator | Auditor confirms deletion intent; Planner coordinates restoration |
| B7 | Implementor | Auditor | Auditor verifies all broken imports identified |
| B8 | Product Owner | Validator | PO resolves spec conflict; Validator documents decision |

### Key decision points:

1. **B2-DP1:** Is the no-op already fixed (registration on `dp.update`)?
   → Verify `main.py` registration line before choosing Option A or B.
2. **B2-DP2:** Should callback_query events be gated?
   → If Option A: yes; if Option B: no (security gap to assess).
3. **B2-DP3:** Deep-link classification — shared function or inline in middleware?
   → Recommendation: extract shared `classify_contact_deep_link()` to avoid pattern drift.
4. **B4-DP1:** Access scope model — single `_check_user_state(scope)` or split methods?
   → Recommendation: split into `_check_login_state` and `_check_contact_state`
   for clarity, or use a `BotAccessScope` StrEnum parameter.

---

## 8. Verification Strategy

### Unit tests (no DB):
- Deep-link classifier: valid patterns (`contact_42`, `contact_us`), invalid
  patterns (`login_abc`, `contact_abc`, empty text, None).
- DECLINE contact exemption logic (mocked user state).

### Integration tests (with PostgreSQL via Docker):
- `test_account_state_middleware.py` — full `__call__` pipeline with real `Update`
  objects, DECLINE user, contact deep-link → handler called.
- `test_account_state_middleware.py` — DECLINE user, `/post` → handler NOT called.
- `test_account_state_middleware.py` — BANNED user, `/start contact_42` → handler NOT called.
- `test_contact_us.py` — existing contact handler tests still pass.
- `test_login.py` — existing login flow tests still pass.

### Cross-suite verification:
- `src/backend/apps/core/tests/test_contact.py` — R2 cross-product
  (`declined_only_contactable` → True) remains green. Confirms web-side contact
  is already spec-correct and serves as a reference oracle.
- `src/backend/apps/users/tests/test_account_state.py` — `can_login` /
  `can_publish_ad` / `get_account_state` flag matrix unchanged.

### Commands:
```powershell
# Fast gate (skips seed suite)
$dc run --rm --env PYTEST_SKIP_MARKERS=seed test

# Single test file
$dc run --rm -e PYTEST_OPTS="-k test_account_state_middleware" test

# Fresh schema (after any migration changes)
$dc run --rm --env PYTEST_OPTS="--create-db -n auto" test

# Lint + typecheck (dev container)
$dc run --rm dev uv run ruff check src/telegram_bot src/backend/apps/users src/backend/apps/core
$dc run --rm dev uv run basedpyright src/telegram_bot
```

---

## 9. Summary

- **PII-001 (HIGH, mandatory):** Two-layer fix. (1) No-op fix — choose Option A
  (`dp.update.outer_middleware`) or Option B (rewrite for `Message`); decision
  deferred to Researcher (B2). (2) DECLINE narrowing — allow DECLINE users to
  reach `contact_us` / `contact_<ad_id>` deep-links while blocking login/post.
  Implemented in `AccountStateMiddleware.__call__` + `_check_user_state` via an
  access-scope model. Tests updated in `test_account_state_middleware.py`.
- **PII-002 (HIGH):** BLOCKED. Spec conflict (§K:104 "no separate bot confirmation"
  vs audit §6 "banner covers both web and bot"). No implementation until PO resolves.
- **PII-003 (LOW):** Doc-only. Update `db-enums.md:214-217` and
  `technical-specification.md:112-113` to reflect that `CookieCategory` enum
  members are used as keys throughout runtime code.
- **Critical prerequisite:** The `src/telegram_bot/` package was deleted in
  commit `2b018a9`. B6 must resolve whether to restore it before PII-001/002
  work can proceed.
- **Broken imports:** 3 backend test files import from the deleted package
  (B7 cleanup required).
