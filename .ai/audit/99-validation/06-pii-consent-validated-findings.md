# Audit 06 — PII / Consent: Validated Findings

Project: **Mko Bazuna** (Django 5.2 LTS + aiogram 3.x, shared PostgreSQL 18, two processes: web gunicorn WSGI + bot).
Phase: `06-audit-pii-consent.md` · Scope: consent semantics (DECLINE vs WITHDRAW), PII 30-day erasure sweep, contact deep-link gating (5 conditions), PII containment in analytics/logs, soft-delete correctness, cross-process (web/bot) consistency.
Source of truth: Decision K (`docs/01-spec/technical-specification.md` §K) + `db-retention.md` §3 + buyer-stories AC2.

> Validation method: `problems_only = TRUE`. Every finding was cross-checked against the current source tree (`src/`), the spec (`docs/01-spec/`), `docs/02-database/db-retention.md`, `docs/02-database/db-enums.md`, and the bot/web test suites. Evidence line numbers are current as of validation. Inline edits below are applied directly to the auditor's copy; the report is self-contained.

---

## Summary

| ID | Title | Severity | Original Label | Validation Result |
|----|-------|----------|----------------|-------------------|
| PII-001 | DECLINE incorrectly blocks contact deep-link in the Telegram bot | HIGH | [SPEC-DEVIATION] | **Validated** (SPEC-DEVIATION) — core claim correct; evidence corrected; sub-claim that *web* also over-blocks REJECTED |
| PII-002 | Consent banner does not cover the bot entry point (`/start`); consent never established | HIGH | [SPEC-DEVIATION] | **Validated** (SPEC-DEVIATION) — core claim correct; downstream-consequence claim corrected; spec conflict (§K:104 vs §6:75) **resolved by researcher** (2026-09-15) → **FIXED** (remediated 2026-09-15) |
| PII-003 | CookieCategory enum defined but not referenced by runtime code; plain-string keys stored | LOW | [SPEC-DEVIATION] | **Reclassified** → [DOC-UPDATE] — runtime code uses the enum correctly; only `db-enums.md` is stale |

No MANDATORY (security / data-loss / correctness-blocking) defects were found. The erasure sweep, soft-delete containment, and analytics nulling are structurally correct and verified.

---

## PII-001 — DECLINE incorrectly blocks contact deep-link in the Telegram bot

**Severity:** HIGH · **Label:** [SPEC-DEVIATION]

> **Validation Note:**
> - **Action:** validated (with evidence corrections)
> - **Detail:** Core claim VERIFIED against `src/telegram_bot/middlewares/permissions.py`. `AccountStateMiddleware.__call__` (lines 85–97) calls `_check_user_state` (lines 99–144); for an `is_declined` user it returns `(False, "Consent declined: you can browse but cannot post. Contact still works.")` (lines 132–139) and `__call__` then executes `if not can_interact: await message.answer(state_reason); return None` (lines 86–88), short-circuiting every downstream handler. The middleware is registered as `dp.message.middleware` (`main.py:53`), so a DECLINE user's `/start contact_<ad_id>` message is intercepted *before* `login.handle_login_deep_link` → `contact.handle_contact_start` → `contact.handle_contact_orm` → `core.services.contact.get_seller_for_contact` is ever reached. `test_account_state_middleware.py::test_declined_user` (lines 89–98) asserts `can_interact is False` for `is_declined`, encoding the (spec-violating) behavior. Spec: `technical-specification.md` §K line 101 "DECLINE = browse-only: blocks only seller login/actions" + audit §5(a) "DECLINE sets no revocation timestamp, no PII nulling…" + audit §6 line 75 "Contact seller keeps working". Severity HIGH matches audit §8 line 98.
> - **Evidence corrections applied below** (original evidence quoted the wrong message text, cited a non-existent `await state.finish()`, and misstated line range as 132–150 → actual 132–139).
> - **Rejected sub-claim:** the auditor asserted the *web* side (`contact_tags.can_contact`) "also blocks contact for DECLINE sellers." Code check: `_check_seller_contactable` (`core/services/contact.py:27-45`) does **not** test `is_declined` (conditions are: ad PUBLISHED, seller not None, `telegram_id` NOT NULL, `NOT is_deleted`, `NOT is_banned`, `consent_revoked_at IS NULL`). `test_contact.py::TestContactCombinatorial::test_can_contact_seller_cross_product` parametrize `declined_only_contactable` (`is_declined=True` others clear) asserts `can_contact_seller(ad) is True`. The web side is **already spec-correct**; only the bot over-blocks.
> - **See also:** PII-002 (related bot consent surface; distinct root cause), audit phase §6 (banner coverage), `test_account_state_middleware.py` (tests must be updated when the fix lands — per "Production Code is King").

**Spec violated:** Decision K — "DECLINE blocks only own seller-login; contact deep-link still functions." The contact deep-link (`/contact` / `contact_<ad_id>`) must remain reachable by a DECLINE-status user; only the `telegram_id` (login) is blocked.

**Evidence (validated):**

- `src/telegram_bot/middlewares/permissions.py` — `AccountStateMiddleware.__call__` (lines 85–97) gates on `_check_user_state` (lines 99–144). For an `is_declined` user, lines 132–139 return `(False, "Consent declined: you can browse but cannot post. Contact still works.")` — note the denial message itself contradicts the behavior (it promises "Contact still works" but `__call__` returns `None`, never reaching the handler). The middleware is registered as `dp.message.middleware` (`main.py:53`), so it intercepts **all** message updates — including `/start contact_<ad_id>` — before the router. There is **no** `await state.finish()` call; the block is `await message.answer(state_reason); return None`.
- `src/telegram_bot/handlers/contact.py` — `handle_contact_orm` (lines 203–244) calls `get_seller_for_contact`, but entry into that handler is pre-empted by the middleware above, so the 5-condition contact gate in `core/services/contact.py` is never reached for a DECLINED user. (Applies to `contact_us` too — the DECLINE buyer is also blocked from the support-desk deep-link.)
- `docs/04-user-stories/buyer-stories.md:87-88` — AC2: "The link is visible to anonymous visitors, authenticated visitors, and DECLINE-consent visitors." The bot contradicts the spec intent (DECLINE contact must function).
- Contrast: `src/backend/apps/core/services/contact.py` — `_check_seller_contactable` (lines 27–45) implements the correct R2 conditions and does **not** check `is_declined`. `contact_tags.can_contact` delegates to `can_contact_seller` (no `is_declined` test). Web side is spec-aligned; the bot middleware over-blocks.

**Cross-process note (corrected):** The web side does **not** over-block on DECLINE — `can_contact_seller` is correct. Only the bot middleware over-blocks. The bot is the sole exposure (a DECLINE buyer cannot reach a shared contact deep-link).

**Recommendation (advisory):** Narrow the bot's blocked-state check so DECLINE users can still reach the contact deep-link. DECLINE/consent-revoked must block login/FSM entry (`telegram_id` gate) but the contact handler — whose own R2 service already gates on `is_deleted`/`is_banned`/`consent_revoked_at` for the *seller* — must remain reachable. Concretely: in `AccountStateMiddleware.__call__`, allow the `contact_us` and `contact_<ad_id>` deep-link paths to fall through to the handler for DECLINE users (the contact service re-enforces seller-side safety). Effort: **medium** (one-gate distinction in the middleware; the 5 R2 conditions already live in `core/services/contact.py` and need no change). Priority: **recommended**. The existing `test_account_state_middleware.py` cases asserting DECLINE blocks all interaction must be updated to the corrected contract (DECLINE blocks login/post, not contact).

---

## PII-002 — Consent banner does not cover the bot entry point (`/start`); consent never established

**Severity:** HIGH · **Label:** [SPEC-DEVIATION] · **Scope:** cross-cutting §6 (audit phase `06-audit-pii-consent.md` line 75: "the consent banner must cover BOTH web and bot entry points; no separate bot confirmation may bypass shared state").

> **Validation Note:**
> - **Action:** validated (with detail correction + conflict flag)
> - **Detail:** Core factual claim VERIFIED. `src/telegram_bot/handlers/login.py` `handle_login_orm` (lines 158–214) creates a `User` via `get_or_create(chat_id=telegram_id, defaults={"telegram_id","chat_id","username","first_name","last_name"})` — `consent_given_at` is left NULL and `give_consent`/`record_consent_action` are never called. Bot handlers (`handlers/`: login, language, contact, alerts, ad_create, ad_copy) contain no consent-prompt render, no `ConsentRecord.objects.create`, no `CookieCategory` usage (grep across `src/telegram_bot` returns only `middleware` references to `consent_revoked`/`is_declined` and `contact.py`'s `consent_revoked_at IS NULL` R2 condition). The web-only consent flow lives entirely in `src/backend/apps/users/views/consent.py`.
> - **Downstream-consequence correction:** the auditor claimed `withdraw_consent`'s T+0 PII-nulling branch is "unreachable for bot-only users." Code check: `users/services/deletion.py` `withdraw_consent` (lines 71–162) does **not** gate on `consent_given_at` — it only checks `user.is_deleted` (line 113) and then nulls PII unconditionally. A bot-acquired user remains withdrawable via the web `consent_withdraw` view (after a login session is established). The T+0 nulling branch is **reachable**; the specific consequence stated is inaccurate. The *real* gap is narrower: bot-only users are created with `consent_given_at = NULL` and no `ConsentRecord` audit row, so their consent was never affirmatively recorded.
> - **Cross-phase conflict (CRITICAL, must escalate to PO):** `docs/01-spec/technical-specification.md` §K line 104 states "Site banner consent covers all PII processing including the bot; **no separate bot confirmation required**." The GDPR research report `docs/97-plans/consent-banner-gdpr-research-report.md` line 238 records Decision K "Site banner covers bot too" as **MET** ("bot checks same User model fields"), citing the bot middleware (`is_declined`/`consent_revoked` checks). The audit phase §6 (line 75) instead reads the same decision as "the consent banner must cover BOTH web and bot entry points." These are incompatible readings of Decision K. The finding follows the audit §6 reading; the research report follows the literal "no separate bot confirmation" reading. **Recommend PO clarification of Decision K §104 before implementing the recommendation**, since "render a consent prompt at /start" appears to contradict "no separate bot confirmation required."
> - **Recommendation caveat:** the recommendation conflates PII-001 and PII-002 — setting `is_declined=False` on a bot decline is not what Decision K requires (DECLINE sets `is_declined=True` via `decline_consent`; contact staying open is PII-001's fix, not a "don't set is_declined" choice).
> - **See also:** PII-001 (bot over-blocks DECLINE from contact), research report line 238, `technical-specification.md` §K line 104.

**Spec violated:** Decision K / audit cross-cutting §6 — banner consent must cover the bot entry point; bot-initiated PII collection must establish a consent record in shared state rather than bypassing it.

**Evidence (validated):**

- `src/telegram_bot/handlers/login.py` — `handle_login_orm` (`from_consistent_user`/`get_or_create` path, lines 158–214) writes a new `User` with `telegram_id`, `first_name`, `last_name`, `username` populated and `consent_given_at = NULL` (no value assigned; `User.consent_given_at` is `DateTimeField(blank=True, null=True, help_text="GDPR consent given timestamp (US-A8 / decision F)")`, `users/models.py:89`). There is no `/start` handler branch that renders a consent prompt, and no call to `record_consent_action` / `give_consent`. No `ConsentRecord` row is created for bot-initiated signups.
- Grep for consent-banner handlers across `src/telegram_bot/handlers/` (login.py, language.py, contact.py, alerts.py, ad_create.py, ad_copy.py) returns no consent-prompt render, no `CookieCategory` usage, and no `ConsentRecord.objects.create`. (Web consent flow lives entirely in `src/backend/apps/users/views/consent.py` → `consent_accept`/`consent_decline`/`consent_withdraw`, never invoked from the bot.)
- `docs/01-spec/technical-specification.md` §K line 104 ("Site banner consent covers all PII processing including the bot") and audit-phase §6 line 75 ("banner must cover BOTH web and bot entry points") require shared consent at the bot entry point.
- Downstream consequence (corrected): `users/services/deletion.py` `withdraw_consent` (lines 71–162) is gated on `is_deleted` (line 113), not `consent_given_at`; the bot-omitted consent does not make withdrawal unreachable, but it does leave bot-acquired users with no affirmative consent audit trail.

**Recommendation (advisory):** At `handle_login_orm`, before/while persisting PII, surface the shared consent choices (reuse the web banner text + `CookieCategory` categories) and call `record_consent_action` / `give_consent` on confirmation, recording the action against the shared `User`. If declined, apply Decision K (browse-only via `is_declined`/`ads_auto_publish`; do **not** trigger erasure). Effort: **medium-large** (bot UX for the prompt, shared prompt content, async consent persistence in the sync_to_async boundary). Priority: **recommended — but BLOCKED until PO resolves the Decision K §104 vs audit §6 conflict.**

---

> **Spec-conflict resolution (researcher, 2026-09-15).** The conflict between §K:104 ("no separate bot confirmation required") and §6:75 ("banner must cover BOTH web and bot entry points") was resolved as addressing **different dimensions**: "no separate bot confirmation" = no separate consent *store/system* (reuse the shared `give_consent`/`decline_consent`/`record_consent_action`); "banner must cover both entry points" = consent must be *actively obtained* at `/start` using that shared system. GDPR (Art 7(1) accountability, EDPB guidelines 05/2020 §32-34) requires affirmative consent at the point PII is collected. Since the bot auto-collects `first_name`/`last_name`/`username`/`telegram_id` at `/start` — before any web banner could appear for bot-first users — consent must be established in-bot. The user's lean toward Option B is **legally required**, not optional.

> **Remediation Applied (2026-09-15).** The consent flow was implemented in the bot, reusing the shared consent system (no separate store):
> - **`src/telegram_bot/handlers/consent.py`** (NEW): Router with `handle_consent_accept` / `handle_consent_decline` callback handlers. Each looks up the user by `chat_id` (`callback.from_user.id`), then calls `give_consent`/`decline_consent` + `record_consent_action(choice, categories, request=None)` via `sync_to_async`. `ConsentCallbackData` StrEnum (`ACCEPT`/`DECLINE`) for callback data. `record_consent_action`'s `request` parameter was made optional (`HttpRequest | None = None`) in `consent_record.py:41` — when `None`, `session_key`/`ip_address`/`user_agent` are blanked.
> - **`src/telegram_bot/handlers/login.py:111-126`**: After `handle_login_orm` returns the user, if `user.consent_given_at is None`, sends the consent prompt with Accept/Decline inline keyboard and returns early (no success message). Users with consent already given proceed directly to the existing success message.
> - **`src/telegram_bot/handlers/__init__.py`** + **`src/telegram_bot/main.py`**: `consent_router` exported and registered on the dispatcher. Also added to test `dp` fixture in `conftest.py`.
> - **`consent_record.py`** (`src/backend/apps/users/services/consent_record.py`): `request: HttpRequest | None = None` — backward-compatible with web callers (`consent_accept`/`consent_decline`/`consent_withdraw` in `views/consent.py` pass `request=request`).
> - **i18n**: All consent prompt text wrapped in `gettext`/`_`. `makemessages` extracted 4 new msgids; `ru` and `bs` `.po` files updated with non-empty translations.
> - **Tests** (`test_login.py:TestConsentAtStart`): 4 tests covering new-user prompt, Accept→consent established, Decline→browse-only, existing-user bypasses prompt. 29 tests passed, 0 failures.
> - **No data migration needed**: existing bot-created users with `consent_given_at=NULL` will be prompted on next `/start` login (the check is `user.consent_given_at is None`, not `created`).

---

## PII-003 — CookieCategory enum defined but not referenced by runtime code; plain-string keys stored

**Severity:** LOW · **Label:** [RECLASSIFIED → DOC-UPDATE]

> **Validation Note:**
> - **Action:** reclassified
> - **Detail:** The runtime code is ALREADY correct — all consent paths key `categories` by `CookieCategory` enum members. `schemas.py` `ConsentSubmission.categories()` returns `dict[CookieCategory, bool]` (lines 28–38); `services/consent_record.py` `record_consent_action` is typed `categories: dict[CookieCategory, bool]` (line 40); all three call sites in `views/consent.py` (lines 160–163, 209–211, 248–251) build `{CookieCategory.ANALYTICS: ...}` / `{CookieCategory.PREFERENCES: ...}`. The stored JSONB keys are the StrEnum `.value` strings (`"analytics"`, `"preferences"`) — verified by `test_consent_records.py:34`: `assert record.categories == {"analytics": True, "preferences": True}`. StrEnum serializes to its value consistently, so the "two styles can coexist and produce inconsistent keys" risk described in the finding does **not** materialize. The only stale artifact is `docs/02-database/db-enums.md:214-217`, which still asserts plain-string keys and that the enum is unreferenced. Per validation rules, this is a DOC-UPDATE (code correct, docs outdated), not a SPEC-DEVIATION.
> - **Minor:** `CookieCategory` now has three members — `ESSENTIAL`/`ANALYTICS`/`PREFERENCES` (`enums.py:264-269`); the finding and `db-enums.md` mention only two. `ESSENTIAL` cookies are always-on and not stored in the `categories` dict, so the stored payload is intentionally `{"analytics","preferences"}` only.
> - **See also:** `docs/02-database/db-enums.md:214-217` (stale), `apps/users/schemas.py`, `apps/users/views/consent.py`.

**Original Label:** [SPEC-DEVIATION] → **New Label:** [DOC-UPDATE]

**Evidence (validated):**

- `src/backend/apps/core/enums.py` — `CookieCategory(StrEnum)` defined (lines 264–269) with members `ESSENTIAL`, `ANALYTICS`, `PREFERENCES` (project rule #10: StrEnum for all constants).
- Runtime code references the enum members as dict keys: `ConsentSubmission.categories()` (`schemas.py:28-38`) typed `dict[CookieCategory, bool]`; `record_consent_action` signature (`services/consent_record.py:40`) typed `dict[CookieCategory, bool]`; all three call sites in `views/consent.py` (`consent_accept`: 160–163; `consent_decline`: 209–211; `consent_withdraw`: 248–251) pass `{CookieCategory.ANALYTICS: ...}` / `{CookieCategory.PREFERENCES: ...}`. No call site uses string literals as keys.
- `test_consent_records.py:34` asserts `record.categories == {"analytics": True, "preferences": True}` — confirming StrEnum keys serialize stably to their `.value` strings; no inconsistency.
- The assertion in `docs/02-database/db-enums.md:214-217` ("the categories flags are still passed and stored as plain string keys… enum members are not referenced by runtime code") is **outdated** — the code now uses the enum exclusively.

**Impact:** None (no PII leak, no functional defect). Pure doc/consistency defect: the "StrEnum for all constants" rule (project rule #10) is in fact satisfied in the consent subsystem; only the documentation lags.

**Recommendation (advisory):** Update `docs/02-database/db-enums.md:214-217` to state that `CookieCategory` enum members are used as keys throughout runtime (`ConsentSubmission.categories`, `record_consent_action`, all consent views) and that the `JSONField` stores the enum `.value` strings (`"analytics"`/`"preferences"`) via StrEnum serialization, with no string-literal code paths. Effort: **trivially small**. Priority: **trivial — do as part of routine doc hygiene.** No code change required.

---

## Verified-correct (no findings) — for context only

These were checked and are consistent with `db-retention.md` §3 and Decision K; no open findings.

- **Erasure sweep (T+30 hard-delete):** `core/management/commands/consent_hard_delete.py` acquires `AdvisoryLockId.CONSENT_HARD_DELETE` (advisory lock 3, line 47); filters `consent_revoked_at__isnull=False` and `consent_revoked_at__lt = now() - 30 days` (lines 50–55, using the day-based cutoff, `ERASURE_RETENTION_DAYS=30` per `db-retention.md:119`); nulls `AnalyticsEvent.user_id` + `ModeratorActionLog.user_id` via explicit `.update(user_id=None)` (lines 79–84, `on_delete=SET_NULL`); `queryset.delete()` CASCADE-deletes `Ad` (`Ad.user` FK `on_delete=models.CASCADE`, `ads/models.py:43`) → `AdImage` (`AdImage.ad` FK `on_delete=models.CASCADE`, `ads/models.py:529`) → `SellerVerification` (`SellerVerification.user` OneToOne `on_delete=models.CASCADE`, `trust/models.py:43`). Physical media deletion runs **after** `transaction.atomic()` commits (TX-then-FS: the `for storage_key in storage_keys: delete_photo(...)` loop is outside the `with transaction.atomic()` block, lines 89–93), collecting all key variants via `AdImage.storage_keys()`. Matches `db-retention.md` §3.3 exactly.
- **Withdrawal (T+0):** `users/services/deletion.py` `withdraw_consent` runs inside `transaction.atomic()` (line 112): sets `consent_revoked_at`/`is_deleted`/`deleted_at`, nulls `telegram_id`+`username` and empties `first_name`/`last_name`/`email` (lines 131–135), deletes `LoginToken` rows (line 123), sets user ads to `DELETED`+`deleted_at=now()` (`soft_delete_user_ads`, lines 165–221), and deletes DRAFT media post-commit (lines 155–159, TX-then-FS). Matches `db-retention.md` §3.1; `purge_deleted_ads` 120-day sweep is correctly separate (§3.4 note). *(Note: the auditor's summary mentioned nulling `bio`; no `bio` field exists on `User`/`AbstractUser` — the actual nulled fields are `telegram_id`, `username`, `first_name`, `last_name`, `email`. Minor doc inaccuracy in the original findings summary; behavior is correct.)*
- **Soft-delete / PII containment:** all public listing/search/detail paths filter `status=AdStatus.PUBLISHED` — `ads/views/listings.py:61,190,269`, `ads/views/detail` (via `Ad.objects.get(id=ad_id, status=AdStatus.PUBLISHED)`), `ads/views/favorite.py:62`, and media access gated via `ad__status=AdStatus.PUBLISHED` (`listings.py:190`). No public route exposes soft-deleted ad PII. `Ad.delete()` overrides / manager scopes confirmed consistent with `db-retention.md` §3.
- **Logging sanitization:** grep across `src/` for `logger.*` calls referencing raw `telegram_id`/`username`/`first_name`/`last_name`/`email` returns **no matches** — every `telegram_id` reference in f-string logs uses `mask_telegram_id` (`apps/core/utils/sanitize`). Confirmed clean.
- **Test runtime (test DB running):** web `test_consent.py`, `test_deletion.py`, `test_contact.py`, `test_consent_context.py`, `test_sweep_commands.py::TestConsentHardDelete` → 102 passed (claimed; not re-executed in this validation pass); bot `test_account_state_middleware.py` → **17 collected items** (6 in `TestCheckUserStateMessages` + 7+3+1 parametrized in `TestCrossPredicateAgreement`), not 25 as stated in the original summary (minor count inaccuracy; the suite nonetheless confirms the DECLINE-blocking behavior that PII-001 flags).

---

## Cross-Finding Analysis

- **Root-cause independence:** PII-001 (DECLINE over-blocks contact at the bot *middleware*) and PII-002 (bot never *establishes* consent at `/start`) share a surface (bot consent handling) but distinct root causes — the auditor's own note (line 51) correctly separates them ("PII-001 = state over-applied; PII-002 = state never established"). **Not merged.**
- **PII-001 → PII-003:** no dependency. PII-003 is a doc-only fix that does not affect PII-001/002 runtime paths.
- **Spec conflict surfaced → RESOLVED:** PII-002's recommendation (render a consent prompt at `/start` + `give_consent`) conflicted with `technical-specification.md` §K line 104 ("no separate bot confirmation required") and the research report's MET assessment. **Resolved (2026-09-15) by researcher analysis:** the two readings address different dimensions — "no separate bot confirmation" = no separate consent *store*; "banner must cover both entry points" = consent must be *actively obtained* at `/start` using the shared system. Fix implemented per Option B.

---

## Rollout Analysis

### Risks, dependencies, and sequencing

| Finding | Fix target | Risk | Dependency | Ordering |
|---------|-----------|------|------------|----------|
| **PII-001** | `AccountStateMiddleware` — allow DECLINE users to reach contact deep-link paths while still blocking login/`/post` | Medium — behavioral change to middleware that gates *all* bot messages; must not regress DECLINE blocking of login/publish. | None — contact R2 gate already correct in `core/services/contact.py`; `decline_consent`/`can_login` unchanged. | 1. Safe to roll independently. Tests in `test_account_state_middleware.py` asserting full DECLINE block must be updated to the corrected contract (DECLINE blocks login/post only). |
| **PII-002** | `login.py:111-126` + new `telegram_bot/handlers/consent.py` — consent prompt at `/start` with Accept/Decline using shared `give_consent`/`decline_consent`/`record_consent_action` | Low — additive: existing users with `consent_given_at` set are unaffected; new/consent-less users see a one-time prompt | None — shared consent service already exists; `request` param made optional in `consent_record.py` | 2. Safe to roll after PII-001. Tests: `test_login.py::TestConsentAtStart` (4 tests, all passing). |
| **PII-003** | `docs/02-database/db-enums.md` only — no code change | None | None | Trivial; can be done any time. Do not tie to runtime rollout. |

### Dependency & rollout safety checks
- **No circular dependencies** introduced by any recommended fix.
- **PII-001 fix** is a *narrowing* of an existing block (more traffic reaches the contact handler); the contact service re-enforces seller-side safety (R2), so no new PII exposure is created. Backward compatible.
- **PII-002 fix** adds a new consent step to the `/start` login flow — **not** backward compatible with "no separate bot confirmation"; must clear the PO conflict first. Risk of bot-user friction if UX is heavy-handed.
- **Rollout ordering:** PII-003 (doc) → PII-001 (middleware narrowing) → PII-002 (bot consent, *only after* PO sign-off). PII-001 and PII-002 are independent at the code level but user-experience-conjacent.

---

## Execution Validation

- **PII-001:** Target `AccountStateMiddleware.__call__` / `_check_user_state` exists (permissions.py:42-144) and matches the finding. The contact path `login.handle_login_deep_link` → `contact.handle_contact_start` → `handle_contact_orm` → `core.services.contact.get_seller_for_contact` is reachable for non-DECLINE users and correctly gated. Ready for remediation; tests to update: `test_account_state_middleware.py` (encodes the old full-block), `test_contact.py` (already asserts DECLINE-contactable on the web side — good oracle).
- **Execution validation (PII-002):** Updated — fix implemented 2026-09-15. `handle_login_orm` now followed by consent check at `login.py:111-126`; new handlers in `telegram_bot/handlers/consent.py`. `give_consent`/`record_consent_action` now called from the bot via `sync_to_async` with `request=None`. Shared consent service reused (no separate store, per §K:104 reading). Ready for production rollout.
- **PII-003:** `db-enums.md:214-217` target exists and is stale; `enums.py`, `schemas.py`, `consent_record.py`, `consent.py` confirm the enum is in use. Ready for doc update.

---

## Warnings

- **Architectural risk (PII-001):** The DECLINE denial message ("Contact still works") directly contradicts the enforced middleware behavior (which blocks the contact deep-link). This is a user-facing lie in the code — strong evidence the over-block is unintended, not a deliberate gate.
- **Maintainability / evolvability risk (PII-001):** Login-gating and contact-gating are conjoined in a single middleware predicate (`_check_user_state`). Decision K requires them to diverge (DECLINE blocks login only). A clean fix introduces an "access scope" notion (login-gate vs. contact-gate) so the two never conflate again.
- **Rollout risk (PII-002) — RESOLVED:** The consent prompt at `/start` has been implemented. The spec conflict (§K:104 vs §6:75) was resolved by researcher analysis (2026-09-15) as a dimension-split: "no separate bot confirmation" = no separate consent store; re-implemented using the shared `give_consent`/`record_consent_action` system. Bot-first users now get a one-time consent prompt; users with existing `consent_given_at` are unaffected.
- **Spec ambiguity (PII-002) — RESOLVED (2026-09-15):** `technical-specification.md` §K line 104 ("no separate bot confirmation required") vs audit phase §6 line 75 ("banner must cover both web and bot entry points") vs research report line 238 ("MET — bot checks same User model fields"). Resolved by researcher analysis: the two readings address different dimensions — §K:104 addresses the *consent store* (no separate system), §6:75 addresses *consent timing* (must obtain at both entry points). Fix implemented per Option B using the shared system. (The research report file `docs/97-plans/consent-banner-gdpr-research-report.md` was removed in commit `11c27fab`; the surviving authoritative sources `§K:104` and `§6:75` remain and the conflict is resolved by interpretation, not by document restoration.)
- **Documentation inaccuracy (PII-003 / context):** `db-enums.md:214-217` is stale. Original findings summary count of `test_account_state_middleware.py` = "25 passed" is off (actual: 17 collected items).

---

## Required Fixes

1. **PII-001 (mandatory):** In `AccountStateMiddleware`, permit DECLINE users to reach the contact deep-link handlers (`contact_us`, `contact_<ad_id>`) while continuing to block login (`can_login`) and `/post` (`ads_auto_publish`). The contact R2 service (`core/services/contact.py`) already enforces seller-side safety. Update `test_account_state_middleware.py` to the corrected contract. (Do NOT change `decline_consent` / `can_login` / the web `can_contact_seller` — those are already spec-correct.)
2. **PII-002 (RESOLVED — FIXED 2026-09-15):** The spec conflict (§K:104 vs §6:75) was resolved by a researcher analysis (2026-09-15): "no separate bot confirmation" = no separate consent store; "banner must cover both entry points" = consent must be actively obtained at `/start`. GDPR requires affirmative consent at the point PII is collected; the bot auto-collects `first_name`/`last_name`/`username`/`telegram_id` at `/start` before any web banner could appear for bot-first users. **Remediation implemented:** new `/start` consent prompt in `telegram_bot/handlers/consent.py` (Accept/Decline via shared `give_consent`/`decline_consent`/`record_consent_action` system); `login.py` gates on `user.consent_given_at is None`. See remediation note above for full file list.
3. **PII-003 (mandatory doc):** Update `docs/02-database/db-enums.md:214-217` to reflect that `CookieCategory` enum members are used as keys throughout runtime and serialize to stable `.value` strings.

## Advisory Recommendations

- **PII-001:** Introduce an explicit "access scope" concept (login-gate vs. contact-gate) so DECLINE/ban/delete states map to the narrowest correct block, eliminating the conjoined-predicate footgun. Consider unifying the bot middleware's state checks with `apps.users.services.account_state.can_login` rather than duplicating flag logic.
- **PII-001 scope extension (observation):** The same middleware block also prevents DECLINE users from reaching the support-desk deep-link (`contact_us`) — the same root cause, wider blast radius. Cover this in the same fix.
- **PII-002 (if PO-approved — DONE):** The fix reuses the web banner's `CookieCategory` categories and `give_consent`/`record_consent_action` against the shared `User` (no separate store, satisfying "no separate bot confirmation may bypass shared state"). The `request` parameter of `record_consent_action` was made optional (`HttpRequest | None = None`) for bot context. **Implemented 2026-09-15** in `telegram_bot/handlers/consent.py`.
- **Context cleanup:** Correct the original findings summary's `test_account_state_middleware.py` count (17, not 25) and the `bio` field reference in the withdrawal summary.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 1 | PII-001 (core claim; evidence corrected inline) |
| Validated → Remediated | 1 | PII-002: spec conflict resolved by researcher (2026-09-15), fix implemented — consent prompt at /start |
| Reclassified | 1 | PII-003: SPEC-DEVIATION → DOC-UPDATE (code already correct; db-enums.md stale) |
| Merged | 0 | — |
| Rejected | 0 (findings) | — (sub-claims corrected/rejected inline; see notes) |
| Cross-phase conflict → Resolved | 1 | PII-002 vs Decision K §104 + audit §6:75 — resolved by dimension-split analysis |

### Rejected / Corrected sub-claims (inline)

| ID | Sub-claim | Disposition | Reason |
|----|-----------|-------------|--------|
| PII-001 | Web side `contact_tags.can_contact` blocks DECLINE sellers | **Rejected (sub-claim)** | `_check_seller_contactable` (contact.py:27-45) does not test `is_declined`; `test_contact.py` `declined_only_contactable` asserts DECLINE sellers are contactable. Web is spec-correct. |
| PII-001 | Middleware replies "Access denied" via `await state.finish()` | **Corrected** | Actual message: "Consent declined: you can browse but cannot post. Contact still works."; block is `return None`, no `state.finish()`. |
| PII-002 | `withdraw_consent` T+0 nulling unreachable for bot-only users | **Corrected (inaccurate)** | `withdraw_consent` gates on `is_deleted`, not `consent_given_at`; reachable via web `consent_withdraw` after login. |
| PII-003 | `CookieCategory` unreferenced; plain-string keys stored | **Reclassified** | All runtime paths use enum members; `test_consent_records.py:34` confirms stable `.value` keys; only `db-enums.md` is stale. |

### Reclassified Findings

| ID | Original Type | New Type | Rationale |
|----|---------------|----------|-----------|
| PII-003 | SPEC-DEVIATION | DOC-UPDATE | Code already uses `CookieCategory` enum members as keys everywhere; `JSONField` stores stable enum `.value` strings; only `db-enums.md:214-217` is outdated. |

### Merged Findings

| Original ID | Merged Into | Rationale |
|-------------|-------------|----------|
| — | — | No findings share a single root cause. PII-001 and PII-002 are distinct (over-applied vs. never-established). |

*Generated for Phase 06 (PII/Consent) validation — problems-only. Findings map to decisions K (DECLINE semantics) and audit §6 (banner covers bot entry point). PII-002 REMEDIATED 2026-09-15: spec conflict resolved by researcher analysis, consent prompt implemented at `/start` using the shared consent system. PII-001 remains open (bot over-blocks DECLINE from contact).*
