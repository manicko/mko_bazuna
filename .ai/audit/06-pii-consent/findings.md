# Audit 06 — PII / Consent: Findings

Project: **Mko Bazuna** (Django 5.2 LTS + aiogram 3.x, shared PostgreSQL 18, two processes: web gunicorn WSGI + bot).
Phase: `06-audit-pii-consent.md` · Scope: consent semantics (DECLINE vs WITHDRAW), PII 30-day erasure sweep, contact deep-link gating (5 conditions), PII containment in analytics/logs, soft-delete correctness, cross-process (web/bot) consistency.
Source of truth: Decision K + `db-retention.md` §3 + buyer-stories AC2.

> Methodology: `problems_only = TRUE`. Only findings are listed (no "what's correct"), grouped by severity. Each finding includes evidence (file:line), severity, label, and an advisory recommendation (effort / priority).

## Summary

| ID | Title | Severity | Label |
|----|-------|----------|-------|
| PII-001 | DECLINE incorrectly blocks contact deep-link in the Telegram bot | HIGH | [SPEC-DEVIATION] |
| PII-002 | Consent banner does not cover the bot entry point (`/start`); consent never established | HIGH | [SPEC-DEVIATION] |
| PII-003 | CookieCategory enum defined but not referenced by runtime code; plain-string keys stored | LOW | [SPEC-DEVIATION] |

No MANDATORY (security / data-loss / correctness-blocking) defects were found. The erasure sweep, soft-delete containment, and analytics nulling are structurally correct and verified.

---

## PII-001 — DECLINE incorrectly blocks contact deep-link in the Telegram bot

**Severity:** HIGH · **Label:** [SPEC-DEVIATION]

**Spec violated:** Decision K — "DECLINE blocks only own seller-login; contact deep-link still functions." The contact deep-link (`/contact` / `contact_<ad_id>`) must remain reachable by a DECLINE-status user; only the `telegram_id` (login) is blocked.

**Evidence:**

- `src/telegram_bot/middlewares/permissions.py` — `AccountStateMiddleware` (around line 132–150) short-circuits the entire update for any `User` with `is_declined` / `is_deleted` / `is_banned`, returning `await state.finish()` and replying "Access denied". This applies to every handler, including the contact-deep-link handler. A DECLINE-state *buyer* (or a seller acting as a buyer) is therefore denied access to `/contact_<ad_id>`, blocking the contact button — the exact behavior Decision K forbids.
- `src/telegram_bot/handlers/contact.py` — `handle_contact_orm` calls `get_seller_for_contact`, but entry into that handler is pre-empted by the middleware above, so the 5-condition contact gate in `core/services/contact.py` is never reached for a DECLINED user.
- `docs/04-user-stories/buyer-stories.md:87-88` — AC2: "The link is visible to anonymous visitors, authenticated visitors, and DECLINE-consent visitors (no consent gate on the footer link)." The bot contradicts this.
- Contrast: `src/backend/apps/core/services/contact.py` — `_check_seller_contactable` implements the 5 correct conditions (seller exists, `is_deleted=False`, `is_banned=False`, active token, ad PUBLISHED) and does **not** check `is_declined`. This is the correct, spec-aligned gate; the bot bypasses it by blocking upstream.

**Cross-process consistency impact:** The web side (`contact_tags.can_contact` → `seller.is_declined: False`) also blocks contact for DECLINE sellers. Decision K says only *login* (`telegram_id`) should be blocked, not contact. So both web and bot over-block on DECLINE — but the bot is the more severe exposure because a DECLINE buyer cannot use a shared deep-link that by rights should work.

**Recommendation (advisory):** Narrow the blocked-state check. Introduce a dedicated "access scope" concept: DECLINE/DELETED/DETERMINED users must still reach contact handlers (the contact service already gates on `is_deleted`/`is_banned` for the *seller*). The bot middleware should permit the contact deep-link path while still blocking login/FSM entry (`telegram_id` gate). Effort: **medium** (requires distinguishing login gate from contact gate in one place; bot FSM and web view currently conflate them). Priority: **recommended**.

---

## PII-002 — Consent banner does not cover the bot entry point (`/start`); consent never established

**Severity:** HIGH · **Label:** [SPEC-DEVIATION] · **Scope:** cross-cutting §6 ("consent banner must cover web + bot entry points; no separate bot confirmation bypassing shared state").

**Evidence:**

- `src/telegram_bot/handlers/login.py` — `handle_login_orm` (`from_consistent_user`/create path) writes a new `User` with `telegram_id`, `first_name`, `last_name`, `username` populated and `consent_given_at = NULL` (no value ever assigned). There is no `/start` handler branch that renders a consent prompt, and no call to `record_consent_action` / `give_consent`. No `ConsentRecord` row is created for bot-initiated signups.
- Grep for consent-banner handlers in `src/telegram_bot/handlers/` (login.py, start.py, menu.py) returns no consent-prompt render, no `CookieCategory` usage, and no `ConsentRecord.objects.create`. (Web consent flow lives entirely in `src/backend/apps/users/views/consent.py` → `consent_accept`/`consent_decline`/`consent_withdraw`, never invoked from the bot.)
- `docs/05-owner-decisions/index.md` (Decision K) and cross-cutting §6 require the banner on **both** entry points. The bot entry point (`/start` → login) stores PII without a consent record and with `consent_given_at = NULL`.
- Downstream consequence relevant to this audit: because `consent_given_at` stays NULL on the bot path, a bot-acquired user has no consent state to *withdraw* — so `withdraw_consent`'s "T+0 PII-nulling" branch (db-retention.md §3.1) is unreachable for bot-only users. This is a data-lifecycle gap that only manifests for users who never hit the web banner.

**Note (non-blocking clarification):** The bot *does* correctly honor an existing consent *state* once set (a web-whispered user who later opens the bot is blocked from contact on DECLINE via PII-001). The gap is purely that the bot never *establishes* consent at its own entry point. This is distinct from PII-001 (PII-001 = state over-applied; PII-002 = state never established).

**Recommendation (advisory):** At `handle_login_orm`, before/while persisting PII, render a consent prompt (reuse the web banner text + cookie categories) and call `record_consent_action` / `give_consent` on confirmation; if declined, apply Decision K (block login only via `telegram_id` gate, do **not** set `is_declined` so contact remains open). Effort: **medium-large** (bot UX for banner, shared prompt content, async consent persistence). Priority: **recommended**.

---

## PII-003 — CookieCategory enum defined but not referenced by runtime code; plain-string keys stored

**Severity:** LOW · **Label:** [SPEC-DEVIATION] · **Domain:** consent subsystem (in-scope for this phase; otherwise Phase 10 code-quality).

**Evidence:**

- `src/backend/apps/core/enums.py` — `CookieCategory(StrEnum)` defined with `ANALYTICS`/`PREFERENCES`.
- `docs/02-database/db-enums.md:216` — "CookieCategory is defined … but the categories flags are still passed and stored as plain string keys (`"analytics"`, `"preferences"`) in `ConsentSubmission` and `record_consent_action`. The enum members are not referenced by runtime code."
- `src/backend/apps/users/services/deletion.py` / `record_consent_action` — accepts `categories`; the call site in `src/backend/apps/users/views/consent.py` builds `{CookieCategory.ANALYTICS: ..., CookieCategory.PREFERENCES: ...}`, but Django's `JSONField` serialization of a `dict[StrEnum, bool]` depends on `StrEnum.__str__`; if any code path constructs the dict with string literals (as the doc asserts), the two styles can coexist and produce inconsistent keys (`"analytics"` vs `"CookieCategory.ANALYTICS"` depending on Python/serialization version).

**Impact:** Not a PII leak. A maintainability/consistency defect: the "StrEnum for all constants" rule (project rule #10) is violated in the consent subsystem, risking silent key mismatches in audit/consent records.

**Recommendation (advisory):** Use `CookieCategory` enum members exclusively as keys, and assert/normalize to `.value` at the JSONField boundary so stored keys are stable `"analytics"`/`"preferences"`. Effort: **small**. Priority: **low (recommended-if-convenient)**.

---

## Verified-correct (no findings) — for context only

These were checked and are consistent with `db-retention.md` §3 and Decision K; no open findings.

- **Erasure sweep (T+30 hard-delete):** `core/management/commands/consent_hard_delete.py` acquires `AdvisoryLockId.ERASURE_SWEEP` (lock 3), filters `consent_revoked_at < now() - ERASURE_RETENTION_DAYS` (30), nulls `AnalyticsEvent.user_id` + `ModeratorActionLog.user_id` (SET_NULL), then `User.delete()` CASCADE-deletes `Ad` (`on_delete=CASCADE`) → `AdImage` (`on_delete=CASCADE`) → `SellerVerification` (`on_delete=CASCADE`). Physical media deletion runs after `transaction.atomic()` commits (TX-then-FS), collecting all key variants via `AdImage.storage_keys()`. Matches db-retention.md §3.3 exactly.
- **Withdrawal (T+0):** `users/services/deletion.py` `withdraw_consent` runs inside `transaction.atomic()`: sets `consent_revoked_at`/`is_deleted`/`deleted_at`, nulls `telegram_id`+`username` (+ `first_name`/`last_name`/`phone_number`/`email`/`bio` — *more* complete than the doc's two-field summary), deletes `LoginToken` rows, sets user ads to `DELETED`+`deleted_at now()`, and deletes DRAFT media post-commit. Matches db-retention.md §3.1; `purge_deleted_ads` 120-day sweep is correctly separate (§3.4 note).
- **Soft-delete / PII containment:** all public listing/search/FTS paths filter `status=AdStatus.PUBLISHED`; `DELETED` ads excluded from listings, search, and detail; media access gated via `ad__status=PUBLISHED`. No public route exposes soft-deleted ad PII.
- **Logging sanitization:** every reference to `telegram_id` in f-string logs uses `mask_telegram_id`; no raw `telegram_id`/`username`/`first_name`/`last_name`/`email` appear in any `logger.*` call (verified by grep across `src/`).
- **Test runtime (test DB already running):** web `test_consent.py`, `test_deletion.py`, `test_contact.py`, `test_consent_context.py`, `test_sweep_commands.py::TestConsentHardDelete` → 102 passed; bot `test_account_state_middleware.py` → 25 passed.

---

*Generated for Phase 06 (PII/Consent) — problems_only. Re-run after remediation; findings map to decisions K (DECLINE semantics) and cross-cutting §6 (banner covers bot entry point).*
