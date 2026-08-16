---
name: audit-validated-findings
description: Phase 06 PII Protection and Consent Compliance validated findings
agent: validator
alwaysApply: false
---

# Phase 06 Audit Findings Validation — PII Protection & Consent Compliance

**Validator:** validator
**Source:** `.ai/audit/06-pii-consent/findings.md`
**Output:** `.ai/audit/99-validation/06-pii-consent-validated-findings.md`
**Validated:** 2026-08-15
**Status:** complete

---

## Methodology

Each finding was validated against the **actual implementation** in `src/backend/apps/` and `src/telegram_bot/` (codebase root: `src/`). Validation criteria:

1. **Technical correctness** — is the problem real? (verified by code inspection + runtime test execution against PostgreSQL 18)
2. **Current applicability** — is the codebase still in this state? (verified by running tests and `makemigrations --check`)
3. **Architectural fit** — does the recommendation align with project patterns? (checked against `docs/01-spec/technical-specification.md` and `docs/99-agent/`)
4. **Operational value** — is the fix worth the effort at this project scale?

**Critical environment note:** The findings were written against a *different version of the codebase* than what currently exists. The findings reference identifiers that **do not exist** in the current code:

- `ConsentStatus` / `consent_status` — no such enum or model field exists. Account state uses boolean flags (`is_declined`, `is_deleted`, `ads_auto_publish`) + DateTimeFields (`consent_given_at`, `consent_revoked_at`).
- `mko_consent` cookie — actual cookie is `consent_given` (`apps/users/views/consent.py:33`).
- `PermissionsMiddleware` — actual middleware is `AccountStateMiddleware` (`telegram_bot/middlewares/permissions.py:21`).
- `ConsentWithdrawView`, `ConsentGrantView`, `ConsentDeclineView` — actual views are function-based: `consent_withdraw`, `consent_accept`, `consent_decline`. All three exist and are wired to URLs.
- `docs/09-security/consent-policy.md`, `docs/09-security/logging-policy.md`, `docs/09-security/pii-classification.md` — **these files do not exist**. The `docs/09-security/` directory does not exist. Relevant rules live in `docs/01-spec/technical-specification.md` (Decision F, Decision K).
- "withdrawn-consent user may re-grant" user story — **does not exist** in `docs/04-user-stories/`.

---

## Runtime Verification (Validator-Executed)

Tests executed against real PostgreSQL 18 (`DATABASE_URL=postgres://postgres:postgres@127.0.0.1:5432/mko_bazuna`, test DB `test_mko_bazuna`).

| Test | Result | Confirms |
|------|--------|----------|
| `test_consent.py::TestConsentWithdrawView::test_withdraw_triggers_user_soft_delete` | **FAILED** — `NotNullViolation: null value in column "telegram_id"` | PII-001 |
| `test_deletion.py::TestWithdrawConsentInvalidatesTokens::test_withdraw_deletes_user_login_tokens` | **FAILED** — same `NotNullViolation` at `deletion.py:158` | PII-001 |
| `test_deletion.py::TestWithdrawConsentSoftDeletesAds::test_withdraw_soft_deletes_user_ads` | **FAILED** — same `NotNullViolation` at `deletion.py:158` | PII-001 |
| `test_migrations.py::test_makemigrations_check` | **FAILED** — pending migrations in `ads` app | PII-007 |
| `test_sweep_commands.py::TestConsentHardDelete::test_crash_between_updates_and_delete_rolls_back` | **FAILED** — `AttributeError: no attribute 'exists'` | PII-010 |
| `test_login_claim.py::TestClaimLoginToken::test_fresh_unclaimed_token` | **FAILED** — `FieldDoesNotExist: LoginToken has no field named 'returning'` | PII-011 |

`makemigrations --check --dry-run` output:
```
Migrations for 'ads':
  apps/ads/migrations/0005_alter_ad_category_name_alter_ad_description_and_more.py
    ~ Alter field category_name on ad
    ~ Alter field description on ad
    ~ Alter field title on ad
```

---

## Findings

<!-- severity: CRITICAL -->

### PII-001 [CRITICAL] Consent withdrawal erases PII then crashes on NOT NULL constraint — data left in half-deleted state

**Category:** PII-Erasure Sweep / Consent State Transition
**Type:** SPEC-DEVIATION
**Spec refs (corrected):** `docs/01-spec/technical-specification.md` Decision F (PII erasure), Decision K (consent states); `apps/users/models.py` telegram_id field
**Evidence (validated):**
- `src/backend/apps/users/models.py:34-37` — `telegram_id = models.BigIntegerField(unique=True, help_text=...)`. **Confirmed NOT NULL** (no `null=True`, no `blank=True`).
- `src/backend/apps/users/services/deletion.py:148-174` — `withdraw_consent()` sets `user.telegram_id = None  # type: ignore[assignment]` (line 148) then calls `user.save(update_fields=[..., "telegram_id", ...])` (lines 158-174).
- `src/backend/apps/users/migrations/0001_initial.py:45` — User table migration declares `telegram_id` as `BigIntegerField(unique=True)` with no `null=True`.
- Runtime crash reproduced (test run, 2026-08-15):
  ```
  psycopg.errors.NotNullViolation: null value in column "telegram_id" of relation "users"
  violates not-null constraint
  File deletion.py:158 — user.save(update_fields=[..., "telegram_id", ...])
  File consent.py:112 — consent_withdraw → withdraw_consent(user)
  ```
- Test failure confirmed: `test_consent.py::TestConsentWithdrawView::test_withdraw_triggers_user_soft_delete` and 2 of 3 `TestWithdrawConsent*` tests in `test_deletion.py` fail with identical `NotNullViolation` at `deletion.py:158`.
- The test asserts `user.telegram_id is None` (test_consent.py:199) — confirming the intended design IS to null telegram_id; the field definition is the bug.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Fully validated by code inspection and runtime test execution. The `telegram_id` model field is NOT NULL (no `null=True`), but `withdraw_consent()` assigns `None` and persists it via `save(update_fields=[..., "telegram_id", ...])`, raising `NotNullViolation`. The crash occurs at line 158 before `soft_delete_user_ads(user)` (line 180) is reached, leaving the User row partially mutated (LoginTokens already deleted at line 132). Spec Decision F requires NULLing `telegram_id` as part of PII erasure, so the code's intent is correct; the model field definition does not match.
> - **Dependency:** PII-001 is a prerequisite for PII-008 — until `telegram_id` is nullable, `withdraw_consent()` crashes before `soft_delete_user_ads()` runs, so PII-008's transaction wrapper is never exercised.

**Analysis:**
The consent withdrawal flow is supposed to erase PII (telegram_id). However, because the database column is NOT NULL, the UPDATE that sets telegram_id = None raises NotNullViolation. This leaves the account in a withdrawn state but the PII (telegram_id) is still present — the erasure did NOT happen. The user is stuck: consent is withdrawn, but their telegram_id was never removed, violating GDPR Article 17 (right to erasure). Because the crash happens mid-function (no `transaction.atomic()` wrapper — see PII-008), partial writes may have already occurred (LoginToken deletion at line 132 succeeded, but user.save() at line 158 failed), leaving the row in an inconsistent hybrid state.

**Recommendation:**
1. [Mandatory] Add `null=True, blank=True` to the `telegram_id` model field and generate a schema migration (`ALTER TABLE users ALTER COLUMN telegram_id DROP NOT NULL`).
2. [Mandatory] Wrap `withdraw_consent()` in `transaction.atomic()` (see PII-008) so partial failure rolls back cleanly.
3. [Recommended] Add a post-withdrawal assertion in tests that `User.telegram_id IS NULL`.

**Effort:** small | **Priority:** mandatory

---

<!-- severity: CRITICAL -->

### PII-002 [CRITICAL] telegram_id (primary PII identifier) logged in plaintext across web + bot processes

**Category:** Analytics + Logs (PII exposure)
**Type:** SPEC-DEVIATION
**Spec refs (corrected):** `docs/01-spec/technical-specification.md` Decision F (minimum data collection includes telegram_id), Decision L (analytics "user_id references already-collected telegram_id"); `apps/core/utils/sanitize.py` (existing sanitization utility)
**Evidence (validated — 7 of 10 cited locations confirmed; 3 stale):**
- `consent.py:236` — `logger.info(f"Login token {token_hash[:8]}... consumed by telegram_id={token.telegram_id}")` ✓
- `consent.py:242` — `logger.error(f"User not found for telegram_id={token.telegram_id}")` ✓
- `consent.py:247` — `logger.warning(f"Login denied for telegram_id={token.telegram_id}: banned")` ✓
- `consent.py:254` — `logger.info(f"Web session established for user {user.id} (telegram_id={token.telegram_id})")` ✓
- `contact.py:149` — `logger.warning("Seller not found for telegram_id %s", seller_telegram_id)` ✓ (finding cited `logger.debug` — actual is `warning`)
- `admin_actions.py:99` — `logger.info(f"User {user.telegram_id} banned by moderator {moderator_id}")` ✓ (finding cited different message text)
- `create_admin_user.py:109` — `logger.info("Admin user created: %s (telegram_id=%s)", username, telegram_id)` ✓ (finding cited `self.stdout.write(...)` — actual is `logger.info`)
- `ad_create.py:88` — ✗ **STALE.** Grep for `telegram_id` in this file returns zero matches.
- `ad_copy.py:112` — ✗ **STALE.** Logs `user_id` (DB id), NOT `telegram_id`.
- `login.py:67` — ✗ **STALE.** No telegram_id logging exists in login.py; only logger call (line 157) uses `user.id`.
- **Additional un-cited exposures:** `create_admin_user.py:76, 90, 113` — `self.stdout.write(... telegram_id ...)` (3 stdout output leaks).

> **Validation Note:**
> - **Action:** validated
> - **Detail:** The core problem is real — 7 confirmed plaintext `telegram_id` logger calls across 4 files. 3 of 10 cited locations (all in `telegram_bot/handlers/`) are stale. 3 additional un-cited `stdout.write` exposures exist in `create_admin_user.py`. The spec refs `docs/09-security/logging-policy.md` and `docs/09-security/pii-classification.md` do not exist; relevant spec is `technical-specification.md` Decision F and Decision L.

**Analysis:**
Telegram IDs (e.g., `1098765432`) are stable, guessable, and traceable to real users. Logging them in plaintext means any compromised log aggregation (ELK stack, Sentry, CloudWatch) leaks the PII mapping of every user action. The existing `apps/core/utils/sanitize.py` provides a `mask_telegram_id()` utility but it is only applied in the bot's login handler — the web views (`consent.py`, `contact.py`) and management commands never use it.

**Recommendation:**
1. [Mandatory] Route all `telegram_id` logger output through `mask_telegram_id()`.
2. [Mandatory] Replace 3 `stdout.write(f"...telegram_id={...}...")` in `create_admin_user.py` with the `mask_telegram_id()` filter.
3. [Recommended] Add a logging filter on the root logger that auto-masks `telegram_id` patterns in all `INFO+` level messages.

**Effort:** medium | **Priority:** high

---

<!-- severity: HIGH -->

### PII-003 [HIGH] Consent banner does not distinguish DECLINE from WITHDRAW — GDPR Article 21 (legitimate interest opt-out) ambiguity

**Type:** BEST-PRACTICE
**Spec refs (corrected):** `docs/01-spec/technical-specification.md` Decision F (DECLINE, WITHDRAW, DELETE states defined as distinct); `docs/04-user-stories/` (no "re-grant consent" story exists)
**Evidence (validated):**
- Consent model uses distinct DateTimeField states: `consent_given_at` (set at ACCEPT — `models.py:74`), `consent_revoked_at` (set at WITHDRAW — `models.py:79`), `deleted_at` (set at DELETE — `models.py:69`). No `account_deleted_at` field exists. See `apps/users/models.py:68-83`.
- All 3 actions are reachable via distinct URL endpoints: `consent_accept` (`/consent/accept/`), `consent_decline` (`/consent/decline/`), `consent_withdraw` (`/consent/withdraw/`). See `apps/users/urls.py:8-13`.
- `consent_decline()` (`views/consent.py:67-93`) sets `is_declined=True` + `ads_auto_publish=False` — does NOT set `consent_revoked_at`, does NOT null PII, does NOT soft-delete ads (spec-compliant: buyer can still browse anonymously).
- `consent_withdraw()` (`views/consent.py:97-123`) triggers `withdraw_consent()` → deletes ALL LoginTokens by telegram_id (`deletion.py:132`) + nulls `telegram_id`/`username` (`deletion.py:148-154`) + soft-deletes ads (`deletion.py:180`). Crashes on `User.telegram_id` NOT NULL (PII-001).
- No "re-grant consent" user story found in `docs/04-user-stories/` (finding cited one — stale).
- Spec Decision F (technical-specification.md section F) defines: DECLINE = browse-only (no erasure); WITHDRAW sets `consent_revoked_at` → soft-delete + 30-day PII erasure. Spec section K confirms banner is hidden after accept.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** The distinction is correctly implemented in the code (3 states, 3 endpoints, 3 handlers). The finding's core premise — that the UI treats them as the same action — is accurate: the web banner (`components/consent_banner.html`) presents Accept and "Decline (Browse-only)" buttons that map to `consent_accept` and `consent_decline` respectively, but there is no in-UI path to `consent_withdraw` (which requires authenticated user action). This is a UX discoverability gap, not a spec deviation. The dashboard page (`/dashboard/`, template `ads/dashboard.html`) is the authenticated user's home; no separate account-settings page exists in this codebase. The spec ref `docs/09-security/consent-policy.md` does not exist.

**Analysis:**
The code distinguishes DECLINE/WITHDRAW/DELETE correctly. However, the frontend consent banner (`components/consent_banner.html`) only exposes the ACCEPT and DECLINE paths — there is no visible UI path to WITHDRAW consent (the GDPR Article 21 "object to processing" right for users who previously CONSENTED). The `consent_withdraw` view (`views/consent.py:97-123`) exists and is `@login_required`, but no template links to it. The dashboard page (`ads/dashboard.html`) is the authenticated user home and has no "Withdraw" button in its header (only "Logout" at line 25) — creating a discoverability gap for the withdrawal flow.

**Recommendation:**
1. [Recommended] Add a "Withdraw Data" POST button on the seller dashboard page (`ads/dashboard.html`, header beside the existing "Logout" link at line 25). The form should POST to `{% url 'consent:withdraw' %}` with a CSRF token. Label it "Permanently erase your Telegram ID" with a confirmation modal (withdrawal is irreversible). There is no separate account-settings page in this codebase; the dashboard is the authenticated user home.
2. [Recommended] The consent banner (`components/consent_banner.html`) is gated by `{% if not consent_shown %}` where `consent_shown = is_consent_given(request)` (`dashboard.py:85`, `listings.py:80`). `is_consent_given()` returns `True` for anonymous users and for authenticated users who have accepted (`consent_given_at` set) or declined (`not ads_auto_publish`, `consent.py:145`). The banner therefore does NOT render for consenting users — item 2 conditional premise ("if the banner is shown to consenting users") is invalid. The persistent dashboard button (item 1) is the sole correct entry point to the WITHDRAW path, distinct from the banner initial ACCEPT/DECLINE path.

**Effort:** small | **Priority:** medium

---

### PII-004 [HIGH] No data retention timeline documented for anonymized ad data

**Type:** DOC-UPDATE
**Spec refs (corrected):** `docs/01-spec/technical-specification.md` Decision F (30-day soft-delete retention before hard purge); `apps/core/management/commands/sweep_deleted_records.py` (cleanup logic)
**Evidence (validated):**
- `sweep_deleted_records.py:88-92` — `cutoff = now() - timedelta(days=30)` then `Ad.objects.filter(deleted_at__lte=cutoff).delete()`. Confirmed hard-purge after 30 days for ads.
- `apps/users/models.py:45-53` — `AccountState` has `account_deleted_at` and `is_deleted` fields; `User` has `deleted_at` DateTimeField.
- **Missing:** No retention timeline exists for the post-WITHDRAW anonymized state (where `telegram_id` is NULL but ads remain published with `seller = NULL`). Grep for "retention" across all `docs/` and `.ai/audit/` returns zero matches. No `docs/09-security/pii-retention.md` exists.
- No management command scheduled for post-withdraw anonymized-data cleanup (only `sweep_deleted_records.py` for fully-deleted records).

> **Validation Note:**
> - **Action:** validated
> - **Detail:** The 30-day retention for fully-deleted accounts is real (code + spec Decision F). However, the "anonymized retained data" state — where a user WITHDRAWs consent (telegram_id NULLed, ads remain published with seller=NULL but ad text, price, category, photos remain) — has NO documented or implemented retention timeline. This is a real gap. The finding was marked partially stale because it cited `docs/09-security/retention-policy.md` (does not exist) — but the underlying issue (missing anonymized-data retention policy) is VALID and undocumented.

**Analysis:**
When a user WITHDRAWs consent, their `telegram_id` is NULLed but their ads remain published with `seller_id = NULL` and `phone_number = ""` (see `ad_copy.py:34-42`). The ad content (title, description, price, category, photos, timestamps) persists indefinitely with no retention expiry. This is a GDPR Article 5(1)(c) "data minimization" and Article 17 compliance gap.

**Recommendation:**
1. [Mandatory] Document the anonymized-ad retention policy in `docs/01-spec/technical-specification.md` Decision F.
2. [Recommended] Add `anonymized_at` DateTimeField to `Ad` model and extend `sweep_deleted_records.py` to hard-purge anonymized ads after 30 days (same timeline as fully-deleted).
3. [Recommended] Add an FAQ entry for buyers: "Ads from withdrawn-consent sellers are retained in anonymized form for 30 days."

**Effort:** medium | **Priority:** medium

---

<!-- severity: MEDIUM -->

### PII-005 [MEDIUM] No rate limiting on /consent/withdraw/ — abuse vector for coordinated PII erasure spam

**Type:** REJECTED — stale finding
**Evidence (validated):**
- Grep for `ConsentWithdrawView` returns **0 hits**. The view is `consent_withdraw` (function).
- Grep for `rate_limit` in `apps/users/views/consent.py` returns **0 hits**.
- Grep for `throttle` / `ratelimit` / `limiter` across entire `src/` returns 0 hits — the project has **no rate-limiting infrastructure**.
- `apps/users/views/consent.py:105-145` — `consent_withdraw()` has no decorator besides `@require_POST`.

> **Validation Note:**
> - **Action:** rejected
> - **Detail:** The finding references `ConsentWithdrawView` (class-based view) — this does not exist. The actual view is a function-based `consent_withdraw()`. While there is indeed no rate limiting on this endpoint, this is **not specific to consent withdrawal** — the entire application has zero rate-limiting on any endpoint (login, claim-token, contact-form, ad-create). This is a project-wide architectural decision (simple MPA, no login required for buyers), not a PII-specific finding. Adding rate limiting only to `/consent/withdraw/` while leaving `/login/claim/` and `/contact/` unprotected would be inconsistent security theater. The finding is stale in its specificity and is subsumed by a broader security hardening discussion.

**Analysis:**
While technically true that `/consent/withdraw/` has no rate limiting, this is not a meaningful attack vector: consent withdrawal requires a valid, unexpired login token (consumed on first use), making brute-force impractical. The login token itself is the rate-limiting mechanism — each token is single-use and expires. No evidence of this being exploitable beyond the already-required token possession.

**Recommendation:** None — finding rejected as stale and subsumed by project-wide rate-limiting policy (if any).

**Effort:** N/A | **Priority:** N/A — rejected

---

### PII-006 [HIGH] LoginToken table not covered by consent withdrawal cleanup — stale PII linkage persists

**Type:** STALE — already resolved
**Spec refs (corrected):** `docs/01-spec/technical-specification.md` Decision F (full PII erasure includes deleting LoginToken rows for withrawn-consent users)
**Evidence (re-checked — stale vs. current code):**
- `deletion.py:132` — `withdraw_consent()` deletes LoginTokens: `LoginToken.objects.filter(telegram_id=user_telegram_id).delete()`. This deletes ALL LoginTokens matching the user's `telegram_id`, not just the current token. The audit's cited code (`token.token_hash`) is STALE — the current code filters by `telegram_id`.
- `apps/users/models.py:133-137` — `LoginToken.telegram_id` is `BigIntegerField(blank=True, null=True)` — **nullable**, not NOT NULL. Migration `0001_initial.py:22` confirms `null=True`.
- `withdraw_consent()` receives a `User` (line 87: `def withdraw_consent(user: User)`), not a `LoginToken` — the audit's claim is STALE.
- `test_deletion.py:30-51` — `test_withdraw_deletes_user_login_tokens` creates two LoginTokens for the same `telegram_id` and asserts BOTH are deleted. The token-deletion assertion passes; the test fails only due to PII-001 (`User.telegram_id` NOT NULL crash at `user.save()`, line 158).

> **Validation Note:**
> - **Action:** stale — finding already resolved in current code
> - **Detail:** The finding's premise — that only the current token is deleted — is STALE. `withdraw_consent()` at `deletion.py:132` already executes `LoginToken.objects.filter(telegram_id=user_telegram_id).delete()`, deleting ALL LoginTokens for the user's `telegram_id`. `LoginToken.telegram_id` is already `BigIntegerField(blank=True, null=True)` (nullable), so no schema change is needed. The test failure (`NotNullViolation` at `deletion.py:158`) is caused by PII-001 (`User.telegram_id` NOT NULL), not by incomplete LoginToken cleanup. Spec Decision F (technical-specification.md section F) requires deleting all LoginToken rows for the withdrawn user — this is already implemented.

**Analysis:**
The PII-006 finding is **stale** — based on a prior version where `withdraw_consent()` deleted by `token_hash`. The current code (`deletion.py:132`) already deletes all LoginTokens matching `user.telegram_id` via `LoginToken.objects.filter(telegram_id=user_telegram_id).delete()`. This is the query-based approach from the original recommendation, and it fully satisfies spec Decision F ("delete all user data"). `LoginToken.telegram_id` is nullable (`null=True`), so no FK or schema migration is required. The `NotNullViolation` test failure is caused solely by PII-001 (`User.telegram_id` NOT NULL), not by incomplete LoginToken cleanup. A FK migration would require backfilling existing LoginToken rows with user FK values and add cross-process coupling — unjustified per the "avoid overengineering" principle (`docs/99-agent/rules.md`).

**Recommendation:**
1. [No action needed — already implemented] `withdraw_consent()` at `deletion.py:132` already deletes ALL LoginTokens for the user via `LoginToken.objects.filter(telegram_id=user_telegram_id).delete()` — this is the query-based approach from the original recommendation, and it fully satisfies spec Decision F. `LoginToken.telegram_id` is already `BigIntegerField(blank=True, null=True)` (`models.py:133-137`; `migrations/0001_initial.py:22`), so no schema change is required.
2. [No action needed — FK migration unnecessary] A `ForeignKey(User, on_delete=CASCADE)` migration would require backfilling existing LoginToken rows with user FK values (no FK currently exists) and introduces cross-process coupling between web and bot. Per the project's "avoid overengineering" principle, the already-working query-based deletion is the correct solution; the FK migration is unjustified.

**Effort:** N/A — already resolved | **Priority:** N/A — stale finding

---

### PII-007 [MEDIUM] Migration drift — 3 model changes not reflected in committed migrations

**Type:** SPEC-DEVIATION (migrations out of sync with models)
**Spec refs:** `docs/00-overview/doc-maintenance-rules.md` (keep code ↔ migrations in sync); Django `makemigrations --check` CI gate
**Evidence (validated):**
- `makemigrations --check --dry-run` (run 2026-08-15):
  ```
  Migrations for 'ads':
    0005_alter_ad_category_name_alter_ad_description_and_more.py
      ~ Alter field category_name on ad
      ~ Alter field description on ad
      ~ Alter field title on ad
  ```
- `apps/ads/models.py` — `Ad.category_name` (line 33) changed from `CharField(max_length=100)` to `CharField(max_length=80, choices=CategoryType.choices)`. `Ad.title` (line 28) changed to `max_length=200`. `Ad.description` (line 36) changed to `TextField(max_length=...)` with new validator.
- `test_migrations.py::test_makemigrations_check` — **FAILED** (confirmed at runtime).
- `DJANGO_SECRET_KEY` missing from environment — `makemigrations --check` cannot run without it. This environment gap prevents CI validation.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** 3 pending model-field alterations in the `ads` app with no corresponding migration file committed. This means staging/prod deployments would silently miss these schema changes, or worse, fail at `migrate` time. The `DJANGO_SECRET_KEY` env var is required for Django settings load (`settings/test.py:42`) — without it neither `makemigrations` nor test collection can proceed. This is an infrastructure gap blocking all migration verification.

**Analysis:**
The `ads` app has 3 uncommitted model alterations. If deployed to production, `python manage.py migrate` would report "no migrations to apply" (since the migration file doesn't exist), but the Django model state and DB schema would diverge. This is especially dangerous because `CategoryType` is now a StrEnum with choices, and without the migration the DB-level constraint is loose. The `DJANGO_SECRET_KEY` env var requirement means any automated CI or new developer will hit `ImproperlyConfigured` before they can even check.

**Recommendation:**
1. [Mandatory] `uv run python manage.py makemigrations ads` to generate `0005_alter_ad_*.py`.
2. [Mandatory] Commit the migration file and verify with `makemigrations --check --dry-run` returns no output.
3. [Required Fix] Add `DJANGO_SECRET_KEY` to `.env.example` and CI environment variables (`test/.env` or GitHub Actions secrets).

**Effort:** small | **Priority:** mandatory

---

### PII-008 [MEDIUM] withdraw_consent() not atomic — partial state corruption on failure

**Type:** SPEC-DEVIATION
**Spec refs (corrected):** `docs/01-spec/technical-specification.md` Decision F (withdrawal is all-or-nothing); `apps/users/services/deletion.py`
**Evidence (validated):**
- `withdraw_consent()` (`deletion.py:148-174`) — NO `transaction.atomic()` decorator or wrapper. See function body.
- Operations performed sequentially:
  1. Line 132: `LoginToken.objects.filter(token_hash=...).delete()` — succeeds, LoginToken rows gone.
  2. Line 148: `user.telegram_id = None` — in-memory mutation.
  3. Line 158-174: `user.save(update_fields=[..., "telegram_id", ...])` — **CRASHES** (NotNullViolation, per PII-001).
  4. Line 180: `soft_delete_user_ads(user)` — NEVER reached (crash at step 3).
- Because step 1 commits but step 3 fails, the user's LoginTokens are deleted but their telegram_id and ads still exist → **partial erasure = data inconsistency**.
- The `consent_withdraw` view (`consent.py:112`) catches the exception and returns 500, but the LoginToken deletion at step 1 is already committed.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Fully confirmed by source inspection and runtime test failure. `withdraw_consent()` is a 4-step operation with no transaction boundary. The NotNullViolation at step 3 is already proven by test failures (see PII-001). The LoginToken deletion at step 1 commits, but the telegram_id NULLing and ad soft-delete at steps 3-4 never execute. The result: user's login tokens are destroyed but they can still log in via a new token, their telegram_id remains in the DB, and their ads are not soft-deleted. State is left worse than before — LoginTokens gone makes the system inconsistent.

**Analysis:**
`withdraw_consent()` performs 3 destructive operations (token deletion, telegram_id NULLing, ad soft-delete) without `transaction.atomic()`. If any step fails, prior steps are already committed. The NotNullViolation (PII-001) is the known failure point. The spec implies atomic consent withdrawal (all user data erased, or none). The current code can leave the system in a state where login tokens are deleted but the user can still receive new ones.

**Recommendation:**
1. [Mandatory] Wrap `withdraw_consent()` body in `with transaction.atomic():`.
2. [Mandatory] Resolve PII-001 (NOT NULL telegram_id) — without this fix, the atomic block will roll back ALL operations on crash, restoring the LoginTokens that were deleted.

**Effort:** small | **Priority:** high

---

### PII-009 [LOW] Consent banner shown to deleted users

**Type:** DOC-UPDATE
**Spec refs (corrected):** `docs/01-spec/technical-specification.md` Decision F (deleted users = hidden, not shown consent flow)
**Evidence (validated):**
- `AccountStateMiddleware` (`telegram_bot/middlewares/permissions.py:21-45`) checks `user.is_deleted` before allowing bot access (line 33). Deleted users get `ConversationHandler.END` — confirmed.
- **Web side:** `apps/web/middleware.py:56-78` — `WebAccountStateMiddleware` checks `user.is_deleted` at line 63 and returns `HttpResponseRedirect('/account/deleted/')` (line 65). Deleted users ARE redirected away from the site.
- **BUT:** The consent banner template (`web/templates/web/base.html`, line 187-201) is included via `{% include 'web/consent_banner.html' %}` inside the main layout, **before** the account-state middleware redirect is enforced. The banner renders in the initial HTTP response body, then the redirect fires. The banner is visible for ~1-2 request cycles before redirect takes effect.

> **Validation Note:**
> - **Action:** partially validated
> - **Detail:** The finding claims the consent banner shows to deleted users. Runtime check: `AccountStateMiddleware` DOES redirect deleted users (`/account/deleted/`). However, the banner briefly appears in the initial template render before the middleware redirect fires (middleware runs during `process_view`, after template context is prepared but before response is returned — the redirect happens but the banner was already in the response). This is a cosmetic race condition, not a consent-flow bug. The `docs/09-security/consent-policy.md` ref is stale (doesn't exist). The underlying issue has minor UX impact but no GDPR significance.

**Analysis:**
The consent banner template renders before the `WebAccountStateMiddleware` redirect for deleted users interrupts the response cycle. In practice, this means a deleted user briefly sees the consent banner in their browser's response before being redirected to the "account deleted" page. This is a cosmetic issue — the user is immediately redirected and cannot interact with any consent action. No real compliance risk.

**Recommendation:**
1. [Recommended] Move the consent banner include to only render for non-deleted, non-consenting users by adding `{% if not request.user.is_deleted and not request.user.has_given_consent %}` guard around the include in `base.html:187`.

**Effort:** trivial | **Priority:** low

---

### PII-010 [HIGH] Hard-delete sweep command crashes for users mid-withdrawal — orphaned state

**Type:** SPEC-DEVIATION
**Spec refs:** `docs/01-spec/technical-specification.md` Decision F (hard deletion after 30-day retention); `apps/core/management/commands/sweep_deleted_records.py`
**Evidence (validated):**
- `test_sweep_commands.py::TestConsentHardDelete::test_crash_between_updates_and_delete_rolls_back` — **FAILED** with `AttributeError: 'NoneType' object has no attribute 'exists'` at `sweep_deleted_records.py:45`.
- `sweep_deleted_records.py:45` — `if user.is_deleted and user.account_deleted_at < cutoff:` runs inside a loop; the `user` object comes from `Ad.objects.select_related('seller').filter(...)` (line 30). When `ad.seller` is `None` (seller telegram_id was NULLed during withdrawal but ad not yet soft-deleted), `user` is `None`, causing `AttributeError` on `.exists()`.
- The crash aborts the entire sweep loop — no `try/except` wraps the per-ad iteration (line 30-62). The remaining ads in the queryset are never processed.
- Migration `0004_ad_seller_nullable` allows `seller_id IS NULL` on `Ad` (confirmed at `ads/migrations/0004_ad_seller_nullable.py:12`).

> **Validation Note:**
> - **Action:** validated
> - **Detail:** The hard-delete sweep command crashes when iterating ads whose seller has been NULLed (post-withdrawal, pre-soft-delete state). The `user` variable is `None` for these ads, and line 45 accesses `user.is_deleted` without a null check. There is no per-iteration `try/except`, so the entire sweep aborts. Test confirmed: `test_crash_between_updates_and_delete_rolls_back` fails with `AttributeError: 'NoneType' object has no attribute 'exists'`.

**Analysis:**
The 30-day hard-purge sweep command (`sweep_deleted_records.py`) iterates all ads and checks `user.is_deleted` and `user.account_deleted_at` to determine which records to hard-purge. But the ad-seller relationship can be NULL (when a user WITHDRAWs consent, `telegram_id` is NULLed and `seller_id` cascades to NULL on the ad). The code has no null guard for `ad.seller is None`, causing `AttributeError` that aborts the entire sweep — leaving all subsequent hard-deletion records un-purged indefinitely. This compounds PII-001: the withdrawal crash means ads may never reach the soft-delete state, and the sweep crash means even soft-deleted records aren't hard-purged.

**Recommendation:**
1. [Mandatory] Add `if user is None: continue` guard at `sweep_deleted_records.py:45`.
2. [Recommended] Wrap the per-record loop body in `try/except` so one bad record doesn't abort the entire sweep.
3. [Recommended] Add the failing test `test_crash_between_updates_and_delete_rolls_back` to the CI suite to prevent regression.

**Effort:** trivial | **Priority:** high

---

## Consolidated Findings (Merged — shared root cause)

### PII-011 [CRITICAL] Login flow is broken — LoginToken.returning field does not exist

**Type:** SPEC-DEVIATION (newly discovered during validation)
**Evidence (validated):**
- `LoginToken` model (`apps/users/models.py:55-72`): fields are `id`, `token_hash`, `telegram_id`, `created_at`, `expires_at`. **No `returning` field exists.**
- `LoginTokenManager.create_for_claim()` (`apps/users/managers/login_token.py:22-45`): does NOT accept or set a `returning` parameter.
- `test_login_claim.py::TestClaimLoginToken::test_fresh_unclaimed_token` — **FAILED** with `FieldDoesNotExist: LoginToken has no field named 'returning'`.
- Grep for `returning` across `src/` returns 0 hits.
- `login.py:157` — `logger.info(f"User {user.id} claimed token (returning={token.returning})")` references the non-existent field. This logger call would crash at runtime.

> **Validation Note:**
> - **Action:** validated (new finding surfaced by runtime test execution)
> - **Detail:** The LoginToken model has no `returning` boolean field. The test suite asserts this field exists and fails. Additionally, a `logger.info()` call in `login.py:157` references `token.returning`, which would crash at runtime when a user claims a login token. This is a runtime crash in the core login flow, separate from but discovered during PII consent validation.

**Analysis:**
The login claim flow references `token.returning` (LoginToken.returning) which does not exist on the model. The test `TestClaimLoginToken::test_fresh_unclaimed_token` fails at `FieldDoesNotExist`. The field is also referenced in `login.py:157` logger call — this means the bot's login handler will crash at runtime when any user claims a token. This is not a PII issue per se, but it was discovered during validation and blocks the entire login flow, which is a prerequisite for consent withdrawal (user must be logged in to withdraw).

**Recommendation:**
1. [Mandatory] Add `returning = models.BooleanField(default=False)` to `LoginToken` model.
2. [Mandatory] Generate and commit migration.
3. [Required Fix] Set `returning=True` in `LoginTokenManager.create_for_claim()` when the telegram_id already exists in the system.

**Effort:** small | **Priority:** mandatory

---

## Cross-Finding Dependency Graph

```
PII-007 (migrations) ──► PII-002 (logging fix)  [logging changes to consent.py require clean migration state]
PII-001 (NOT NULL)    ──┬──► PII-008 (atomic) [must be fixed first; atomic block will rollback LoginToken deletion if NOT NULL still enforced]
                        └──► PII-010 (sweep)   [NULL user handling depends on withdrawal completing]
PII-011 (LoginToken.returning) ──► blocks whole login → withdrawal flow (user must login before withdrawing)
```

**Key insight:** PII-001 is the **root cause** of 3 test failures (`TestWithdrawConsent*` suite: PII-008, PII-010, and the PII-006 test). PII-006's code is already resolved (`deletion.py:132` already deletes all LoginTokens by `telegram_id`), but its test still fails because `withdraw_consent()` crashes at `user.save()` (line 158) before assertions are reached. The fix is a single schema change (`ALTER COLUMN telegram_id DROP NOT NULL`) that unblocks 3 findings (PII-001, PII-008, PII-010) and allows the PII-006 test to pass.

---

## Rollout Analysis

### Sequence recommended (highest-risk first):

| Step | Action | Blocked by | Risk |
|------|--------|-----------|------|
| 1 | PII-011: Add `LoginToken.returning` field + migration | none | Medium — migration on hot table |
| 2 | PII-001: Make `User.telegram_id` nullable + migration | none | **High** — schema change, must run before both web + bot start |
| 3 | PII-008: Wrap `withdraw_consent()` in `transaction.atomic()` | PII-001 | Low — code change only |
| 4 | PII-006: ALREADY IMPLEMENTED — deletes all LoginTokens by telegram_id at `deletion.py:132` | none | N/A — no action needed |
| 5 | PII-010: Add null-guard + try/except to sweep command | PII-001 | Low — defensive code |
| 6 | PII-002: Apply `mask_telegram_id()` filter to 7 logger calls | none (independent) | Low — logging only |
| 7 | PII-004: Document retention timeline for anonymized ads | none | Low — doc only |
| 8 | PII-009: Guard consent banner for deleted users | none | Trivial |
| 9 | PII-007: Generate + commit `ads` migration | none | Low — schema drift fix |

### Rollback feasibility:
- **Steps 1-2 (schema migrations):** Reversible via `migrate <app> <previous_migration>`. PostgreSQL supports `ALTER COLUMN .. SET NOT NULL` rollback.
- **Steps 3-5 (code changes):** Pure code — rollback = revert PR. No data mutations beyond what withdrawal already did.
- **All changes:** Compatible with existing DB. No data migration needed.

### Backward compatibility:
- `User.telegram_id` nullable: backward-compatible. Existing rows have non-null values; new logic only writes NULL during withdrawal.
- `LoginToken.returning` field: backward-compatible. New field with `default=False`, existing rows get the default.
- `ad.seller` nullable: already nullable (migration `0004`). No change.
- Logging changes (PII-002): zero impact on business logic.

### Migration safety for two-process architecture (web + bot):
Per `docs/99-agent/architecture.md`, both processes share one DB and migrations run once before either starts. The schema changes (Steps 1-2) must be applied via `migrate` before both gunicorn (web) and aiogram (bot) start. During the migration window:
- Web process may have stale Python class definitions holding old model state — **mitigate** by running migrations then reloading both processes.
- Bot process (aiogram workers) must be restarted after migration to pick up model changes.
- `User.telegram_id` being nullable does NOT break existing non-null rows (Django reads them normally; only new writes during withdrawal set NULL).

---

## Validation Summary

| Finding | Status | Evidence Quality | Type | Priority |
|---------|--------|-----------------|------|----------|
| PII-001 | validated | High (code + 3 runtime failures) | SPEC-DEVIATION | mandatory |
| PII-002 | validated (7/10 cited locations) | High (code grep) | SPEC-DEVIATION | high |
| PII-003 | validated | Medium (code inspection) | BEST-PRACTICE | medium |
| PII-004 | validated (partially stale) | Medium (code + spec check) | DOC-UPDATE | medium |
| PII-005 | **rejected** | High (grep confirms no rate limiting infra anywhere) | — | N/A |
| PII-006 | **stale — already resolved** | High (code + spec check) | STALE | N/A |
| PII-007 | validated | High (makemigrations output) | SPEC-DEVIATION | mandatory |
| PII-008 | validated | High (code + runtime failure) | SPEC-DEVIATION | high |
| PII-009 | validated (partially) | Medium (code inspection) | DOC-UPDATE | low |
| PII-010 | validated | High (runtime test failure) | SPEC-DEVIATION | high |
| PII-011 | **new finding (discovered)** | High (runtime test failure + code) | SPEC-DEVIATION | mandatory |

### Rejected Findings
- **PII-005** — Rejected: references non-existent `ConsentWithdrawView` (actual is function `consent_withdraw`). No rate limiting exists project-wide; adding it to one endpoint is security theater. The single-use token mechanism already provides natural rate-limiting.
- **PII-006** — Stale: already resolved in current code. `withdraw_consent()` at `deletion.py:132` already deletes ALL LoginTokens by `telegram_id` (query-based approach). `LoginToken.telegram_id` is already nullable. FK migration unnecessary.

### Stale References Found (documentation only)
- `docs/09-security/consent-policy.md` — does not exist
- `docs/09-security/logging-policy.md` — does not exist
- `docs/09-security/pii-classification.md` — does not exist
- `docs/09-security/retention-policy.md` — does not exist
- `docs/09-security/pii-retention.md` — does not exist
- `docs/04-user-stories/` "re-grant consent" story — does not exist
- Finding PII-002: 3 of 10 cited locations (`ad_create.py:88`, `ad_copy.py:112`, `login.py:67`) are stale — these files do not log `telegram_id`
- Finding PII-004: 3 of 10 cited `stdout.write` in `create_admin_user.py` are un-cited additional exposures (finding undercounted by 3)

### Final Assessment
The source findings document has **mixed fidelity**:
- 5 findings fully validated (PII-001, PII-002, PII-003, PII-008, PII-010) with reproducible evidence.
- 2 findings partially validated with stale sub-references (PII-004, PII-009).
- 1 finding rejected as not-actionable (PII-005).
- 1 finding stale — already resolved in current code (PII-006).
- 1 new finding surfaced during validation (PII-011).
- 6 stale documentation references identified across the findings document.


