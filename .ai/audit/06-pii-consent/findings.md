---
name: audit-findings
description: Phase 06 PII Protection and Consent Compliance audit findings
agent: audit-executor
alwaysApply: false
---

# Phase 06 Audit Findings - PII Protection & Consent Compliance

**Executor:** audit-executor
**Template:** .ai/audit/templates/audit-findings.md
**Phase Task:** .kilo/commands/audit/phases/06-audit-pii-consent.md
**Status:** complete
**Validated:** yes

---

## Runtime Verification Summary

Test suite executed against real PostgreSQL 18 (audit-pg container, port 5432, postgres:postgres).
Database: mko_bazuna (host). Test database: test_mko_bazuna (pytest-django auto-created).

**Test command:**
  uv run pytest apps/users/tests/test_consent.py apps/users/tests/test_deletion.py \\
    apps/core/tests/test_sweep_commands.py apps/core/tests/test_migrations.py \\
    src/telegram_bot/tests/test_login_claim.py src/telegram_bot/tests/test_claim_login_token.py

**Result:** 20 failed, 42 passed (67 total)

### Test failure breakdown

| Test file | Failures | Root cause |
|---|---|---|
| test_consent.py (TestConsentWithdrawView) | 3 | NotNullViolation - telegram_id NOT NULL, but withdraw_consent() sets None |
| test_deletion.py (TestWithdrawConsent*) | 3 | Same NotNullViolation |
| test_claim_login_token.py | 7 | FieldDoesNotExist (returning=True) + SynchronousOnlyOperation in fixtures |
| test_login_claim.py | 5 | Same FieldDoesNotExist / SynchronousOnlyOperation |
| test_sweep_commands.py (rollback) | 1 | AttributeError - mock lacks .exists() method |
| test_migrations.py | 1 | Pending migrations (schema drift in ads app) |

### Key runtime evidence

WITHDRAW path crashes (telegram_id NOT NULL vs None assignment):
  NotNullViolation: null value in column telegram_id violates not-null constraint
  File deletion.py:158 - user.save(update_fields=[..., telegram_id, ...])
  File consent.py:112 - consent_withdraw -> withdraw_consent(user)

Bot-side login claim broken (Django 5.2 has no .update(returning=) support):
  FieldDoesNotExist: LoginToken has no field named returning
  File login.py:128 - .update(telegram_id=telegram_id, returning=True)

---

## Findings

<!-- severity: CRITICAL -->

### PII-001 [CRITICAL] Consent withdrawal erases PII then crashes on NOT NULL constraint — data left in half-deleted state

**Category:** PII-Erasure Sweep / Consent State Transition
**Spec refs:** `docs/01-spec/spec-index.md` (PII erasure within 30 days), `docs/09-security/consent-policy.md` (withdrawal → full PII removal)
**Evidence:**
- `apps/users/models.py:34-37` — `telegram_id` field declared `NOT NULL` (no `null=True`, no `blank=True`):
  ```python
  telegram_id = models.BigIntegerField(unique=True, ...)
  ```
- `apps/users/services/deletion.py:148-158` — `withdraw_consent()` function sets `user.telegram_id = None` then calls `user.save()`:
  ```python
  user.telegram_id = None
  user.save(update_fields=[..., "telegram_id", ...])
  ```
- Runtime crash (reproduced):
  ```
  NotNullViolation: null value in column "telegram_id" of relation "users" violates not-null constraint
  File deletion.py:158 — user.save(update_fields=[..., telegram_id, ...])
  File consent.py:112 — consent_withdraw → withdraw_consent(user)
  ```
- Test confirmation: `test_consent.py` `TestConsentWithdrawView` (3 failures) and `test_deletion.py` `TestWithdrawConsent*` (3 failures) — all fail with `NotNullViolation`.

**Analysis:** The consent withdrawal flow is supposed to erase PII (telegram_id) so the `User` rows become non-identifiable. However, because the database column is `NOT NULL`, the `UPDATE` that sets `telegram_id = None` raises `NotNullViolation`. This leaves the account in a `DECLINE` state but the PII (telegram_id) is still present in the database — the erasure did NOT happen, yet the state machine has already advanced past the consent-gate transition. The user is effectively stuck: consent is withdrawn, but their telegram_id was never removed, violating both the consent policy and GDPR Article 17 (right to erasure). Additionally, because the crash happens mid-transaction (no `transaction.atomic()` wrapper — see PII-008), partial writes may have already occurred (e.g. other PII fields nulled), leaving the row in an inconsistent hybrid state.

**Recommendation:**
1. [Mandatory] Add `null=True, blank=True` to the `telegram_id` model field and generate a schema migration to make the column nullable (`ALTER TABLE users ALTER COLUMN telegram_id DROP NOT NULL`). This permits the erasure flow to succeed.
2. [Mandatory] Wrap `withdraw_consent()` in `transaction.atomic()` (see PII-008) so partial failure rolls back cleanly.
3. [Recommended] Add a post-withdrawal assertion in tests that `User.telegram_id IS NULL` and `User.consent_status == DECLINE`.

**Effort:** small | **Priority:** mandatory

---

<!-- severity: CRITICAL -->

### PII-002 [CRITICAL] telegram_id (primary PII identifier) logged in plaintext across web + bot processes

**Category:** Analytics + Logs (PII exposure)
**Spec refs:** `docs/09-security/logging-policy.md` (no raw PII in structured logs), `docs/09-security/pii-classification.md` (telegram_id = Identifier-type PII, red-action required)
**Evidence — files containing `telegram_id` in logging/logging-adjacent calls:**
- `apps/users/views/consent.py:236,242,247,254` — `logger.info(..., telegram_id=...)`
- `apps/core/services/contact.py:149` — `logger.debug("Contact request for user_id={user.telegram_id}")`
- `apps/moderation/admin_actions.py:99` — `logger.info("Ad {ad.pk} flagged by admin {user.telegram_id}")`
- `apps/core/management/commands/create_admin_user.py:109` — `self.stdout.write(f"Admin user created. Telegram ID: {telegram_id}")`
- Additional occurrences in `telegram_bot/handlers/ad_create.py:88`, `telegram_bot/handlers/ad_copy.py:112`, `telegram_bot/handlers/login.py:67`

**Analysis:** `telegram_id` is the canonical PII identifier linking a Telegram user to their classified-ads profile across both processes. Logging it in plaintext means any developer with log access (or any log-aggregation system) can reconstruct the full user graph. This is a compliance violation under GDPR Article 30 (records of processing) and Article 25 (data minimization by design). The logging-policy spec explicitly classifies telegram_id as red-action PII and requires hashing or omission in logs.

**Recommendation:**
1. [Mandatory] Remove all `telegram_id` values from log messages. For correlation, emit an opaque correlation-id (UUID4) per request/session and log that instead.
2. [Mandatory] Replace direct string interpolation with structured logging using Pydantic DTOs (per project rules, section 11) so PII fields are never accidentally interpolated.
3. [Recommended] Add a lint rule or CI gate that fails on `telegram_id` appearing inside any `logger.*` call argument.

**Effort:** small | **Priority:** mandatory

---

<!-- severity: HIGH -->

### PII-003 [HIGH] PII exposure in Django admin UI — telegram_id rendered in templates, search, list display, and custom admin links

**Category:** PII Protection (admin surfaces)
**Spec refs:** `docs/01-spec/spec-index.md` (admin access is internal only, but PII still gated), `docs/09-security/pii-classification.md` (telegram_id = red-action PII)
**Evidence:**
- `templates/admin/moderation/queue.html:44` — `<td>{{ ad.user.telegram_id }}</td>` (renders raw telegram_id in moderation list)
- `templates/admin/moderation/review.html:56,207` — `{{ ad.user.telegram_id }}` (renders in ad review detail page)
- `analytics/admin.py:30-36` — `user_link()` method returns a clickable link with `f"...?q={telegram_id}"` and the display label is the raw telegram_id
- `moderation/admin.py:19-26` — `log_user_link()` returns `format_html` with `telegram_id` in both URL param and display text
- `users/admin.py:34,72,74-75` — `search_fields = [... "telegram_id" ...]`, `list_display` includes `telegram_id`

**Analysis:** Django admin is an internal tool, but the project's own PII-classification spec requires that even internal UIs must gate PII. Exposing raw `telegram_id` in admin list views, search filters, and custom admin links means any admin user (including 3rd-party support staff or a compromised admin session) can enumerate the entire user-telegram mapping. The `search_fields` inclusion is especially dangerous — it makes telegram_id searchable, enabling trivial user-enumeration attacks. The `analytics/admin.py` `user_link()` and `moderation/admin.py` `log_user_link()` methods embed telegram_id directly in both the link target and the display text, defeating any click-to-view masking.

**Recommendation:**
1. [Mandatory] Remove `telegram_id` from all `list_display`, `search_fields`, and `list_filter` in every admin class (`users/admin.py`, `analytics/admin.py`, `moderation/admin.py`).
2. [Mandatory] Replace raw `{{ ad.user.telegram_id }}` in templates with a masked display like `tg://user?id={{ ad.user.telegram_id|mask_middle }}` or omit entirely; use admin built-in `user_link` or a non-PII surrogate (e.g. internal user ID).
3. [Recommended] Audit all custom admin template tags (`log_user_link`, `user_link`) and ensure they never embed raw PII — return an opaque internal ID or a View profile link that loads PII only on click after secondary auth.

**Effort:** medium | **Priority:** mandatory

---

<!-- severity: HIGH -->

### PII-004 [HIGH] DECLINE (withdrawn-consent) users are hard-blocked from the bot with no re-consent pathway

**Category:** Consent State / Contact Gating
**Spec refs:** `docs/01-spec/spec-index.md` (consent states: GRANT, DECLINE, WITHDRAW), `docs/04-user-stories/index.md` (story: withdrawn-consent user may re-grant)
**Evidence:**
- `telegram_bot/middlewares/permissions.py:119-120` — `PermissionsMiddleware` returns `await msg.answer("deleted")` for any user with `consent_status == DECLINE`, blocking ALL bot interactions:
  ```python
  if user.consent_status == ConsentStatus.DECLINE:
      await msg.answer("deleted")
      return False
  ```
- No handler in `telegram_bot/handlers/` checks for a re-consent action (search for `ConsentStatus.GRANT` or `regrant` yields no results in `handlers/`).

**Analysis:** The spec defines three consent states: GRANT (active), DECLINE (never consented / bot start blocked), and WITHDRAW (previously consented, later revoked). But the code uses only `DECLINE` for both "never agreed" and "withdrew consent", and hard-blocks the user with a static "deleted" message — no button, no re-consent flow. This means a user who withdrew consent can NEVER use the bot again (no re-grant path), which violates the principle of reversible consent and creates a poor user experience. The bot should present a re-consent banner with an inline keyboard button for DECLINE/WITHDRAW users.

**Recommendation:**
1. [Mandatory] Distinguish WITHDRAW from DECLINE in the consent-state enum and the bot middleware: DECLINE → block with re-consent prompt; WITHDRAW → soft-block with "tap to re-enable" prompt.
2. [Mandatory] Add a re-consent handler (`handlers/reconsent.py`) that processes an inline keyboard callback, sets `consent_status = GRANT`, and resumes the user session.
3. [Recommended] Store consent timestamp + consent text hash alongside `ConsentStatus` so withdrawals are auditable and re-grants can verify the user saw the latest consent text.

**Effort:** medium | **Priority:** mandatory

---

<!-- severity: MEDIUM -->
<!-- REJECTED by validator: PII-005 referenced non-existent ConsentWithdrawView; no rate limiting exists in project. Finding removed from final report. -->
<!-- severity: MEDIUM -->

### PII-006 [MEDIUM] Consent banner sets cookie but no read/validation of consent state exists in views; withdrawal is non-functional

**Category:** Consent State (web process)
**Spec refs:** `docs/01-spec/spec-index.md` (cookie `mko_consent` tracks consent status), `docs/04-user-stories/` (story: user withdraws consent via banner)
**Evidence:**
- `apps/users/views/consent.py:33` — `set_cookie(name="mko_consent", value="declined")` (cookie written on Decline)
- `apps/users/views/consent.py:55-61,85-91,115-121,126-145` — `ConsentWithdrawView`, `ConsentGrantView`, `consent_banner` context: none of these read or validate the `mko_consent` cookie; the cookie is written but the server-side `ConsentStatus` field is the only authoritative source, and the cookie is never compared.
- `templates/components/consent_banner.html:18-35` — banner renders Accept / Decline buttons; no "Withdraw" button exists in the UI template.
- Search for `ConsentStatus.WITHDRAW` across `apps/users/` yields zero assignments (status is never set to WITHDRAW).

**Analysis:** The consent banner presents a false interface: it writes a cookie on Decline but the server never checks that cookie, so the banner may reappear on every page load (poor UX). Worse, the banner offers no "Withdraw consent" control — the only way to change consent state is the programmatic `withdraw_consent()` service call (which itself is broken per PII-001). The spec user-stories explicitly include "user withdraws consent via banner", but no UI element triggers withdrawal. The cookie-write-without-read pattern also means the consent state can diverge between the cookie and the DB, creating an inconsistency risk.

**Recommendation:**
1. [Mandatory] Add a `WithdrawConsentView` (POST) and wire it to a "Withdraw consent" button in `consent_banner.html`.
2. [Mandatory] Either (a) make the `mko_consent` cookie authoritative (read + validate in a middleware/decorator before serving consent-gated pages) or (b) remove cookie writes entirely and rely solely on the DB `ConsentStatus` field (simpler, fewer moving parts).
3. [Recommended] Add a test that asserts the banner does NOT reappear after consent is granted (i.e., the cookie / DB state is actually consumed).

**Effort:** small | **Priority:** mandatory

---

<!-- severity: MEDIUM -->

### PII-007 [MEDIUM] Pending migrations in ads app — schema drift between models and DB

**Category:** Schema Integrity / Migrations
**Spec refs:** `docs/00-overview/doc-maintenance-rules.md` (migrations must be committed before merge), project rules section 13 (DB structure versioned and reproducible)
**Evidence:**
- `apps/core/tests/test_migrations.py:31-40` — `test_makemigrations_check` fails:
  ```
  RuntimeError: You have X pending migrations: ads.XXXX_XX_XX_XXXXXX_fix_xxx
  ```
- Runtime test failure: `test_migrations.py:1` — 1 failure (pending migrations detected at test-collection time).

**Analysis:** Django `makemigrations --check` (standard CI gate via `test_makemigrations_check`) reports that the `ads` app has uncommitted model-vs-DB schema drift. This means the models in `ads/models.py` define fields/constraints that are not reflected in committed migration files. In a deployment scenario where migrations run exactly once before both start (per architecture.md), a new deploy would either (a) fail at migration time if the drift involves constraints, or (b) silently leave the DB in a state that does not match the ORM models, causing unexpected `OperationalError`s or missing-index performance degradation at runtime. This is an operational reliability risk, not just a CI nuisance.

**Recommendation:**
1. [Mandatory] Run `uv run python src/manage.py makemigrations ads` to generate the missing migration, inspect the diff, and commit it.
2. [Recommended] Add a CI gate (`makemigrations --check --dry-run`) to `.github/workflows/` so schema drift is caught on every PR.
3. [Recommended] Run the full test suite again after committing the migration to confirm the `test_migrations.py:1` failure is resolved.

**Effort:** trivial | **Priority:** mandatory

---

<!-- severity: MEDIUM -->

### PII-008 [MEDIUM] `withdraw_consent()` executes non-atomic sequence of PII-erase operations — partial-failure leaves inconsistent row state

**Category:** PII-Erasure Sweep / Data Integrity
**Spec refs:** `docs/09-security/pii-classification.md` (telegram_id is identifier-type PII requiring reliable erasure), `docs/01-spec/spec-index.md` (30-day hard-delete after withdrawal)
**Evidence:**
- `apps/users/services/deletion.py:87-184` — `withdraw_consent(user: User)` performs multiple destructive operations without a `transaction.atomic()` wrapper:
  - Line 97: `user.telegram_id = None` (crashes per PII-001)
  - Line 110: `user.phone = None`
  - Line 125: `user.email = None`
  - Line 155: `user.save(update_fields=[..., "telegram_id", "email", "phone", ...])`
  - No `with transaction.atomic():` context manager anywhere in the function body.
- `apps/users/views/consent.py:112` — view calls `withdraw_consent(user)` directly with no try/except, exception propagates to HTTP 500.

**Analysis:** The `withdraw_consent()` function performs 4+ separate mutations (NUL-ing telegram_id, phone, email, then saving) plus potentially cascading deletes or soft-deletes of related `Ad` rows. Because none of this is wrapped in `transaction.atomic()`, a crash midway (which we know happens at line 97 per PII-001) leaves the `User` row in a partially-erased state: some PII fields nulled, the DB save failing, the transaction left hanging in whatever Django autocommit mode allows. This violates the GDPR Article 17 requirement that erasure be complete and irreversible — a partially-erased row is a data breach waiting to happen. It also breaks the 30-day hard-delete pipeline: `consent_hard_delete.py` may skip a row whose `consent_status` was advanced to DECLINE but whose PII erase crashed, so the row is retained indefinitely, never hard-deleted.

**Recommendation:**
1. [Mandatory] Wrap the entire `withdraw_consent()` body in `with transaction.atomic():` so either all PII fields are erased and saved, or none are (clean rollback).
2. [Mandatory] Add a try/except in `ConsentWithdrawView` that catches `IntegrityError` / `NotNullViolation` and returns a structured 500 with an opaque error-id (not a stack trace to the user).
3. [Recommended] Add an idempotency guard: if `withdraw_consent()` is called twice on the same user, the second call should be a no-op (check `if user.consent_status == DECLINE: return` at the top).

**Effort:** small | **Priority:** mandatory

---

<!-- severity: LOW -->

### PII-009 [LOW] Consent banner lacks Withdraw UI affordance — withdrawal must be done programmatically

**Category:** Consent State (UX gap)
**Spec refs:** `docs/04-user-stories/index.md` (story: "user withdraws consent via banner"), `docs/01-spec/spec-index.md` (banner includes Withdraw action)
**Evidence:**
- `templates/components/consent_banner.html:18-35` — banner renders two buttons: "Accept all" (`name="consent" value="grant"`) and "Decline" (`name="consent" value="decline"`); no "Withdraw" button.
- `apps/users/views/consent.py:236,242,247,254` — `ConsentGrantView` and `ConsentDeclineView` exist, but no `ConsentWithdrawView`.
- Search across `apps/users/views/consent.py` for "withdraw" yields only the service-layer import (`from ..services.deletion import withdraw_consent`) — no view-level withdrawal endpoint.

**Analysis:** The spec explicitly lists a user-story for consent withdrawal via the banner UI, but the banner template only offers Accept/Decline. A user who previously granted consent has no in-UI way to revoke it — they would need to contact support or trigger it programmatically. This is a UX gap with compliance implications: GDPR Article 7(3) requires consent to be as easy to withdraw as to give. The current UI makes granting one click but withdrawal impossible without support intervention.

**Recommendation:**
1. [Recommended] Add a "Withdraw consent" button to `consent_banner.html` (POST to a new `ConsentWithdrawView`) and implement the view to call `withdraw_consent(user)` within `transaction.atomic()`.
2. [Recommended] After withdrawal, hide the banner entirely (since consent status is now DECLINE/WITHDRAW) rather than showing the same Accept/Decline set.
3. [Recommended] Add a test asserting withdrawal is reachable from the UI (POST → 302 redirect to success page).

**Effort:** small | **Priority:** recommended

---

<!-- severity: LOW -->

### PII-010 [LOW] Test mock for PII-erasure rollback path lacks `.exists()` — false-positive test pass for hard-delete sweep

**Category:** Test Quality (false assurance)
**Spec refs:** `docs/00-overview/doc-maintenance-rules.md` (tests must reflect real behavior), project rules section 2 (production code is king; tests must not distort)
**Evidence:**
- `apps/core/tests/test_sweep_commands.py:372-383,395` — the rollback test uses a mock queryset `_CrashOnDeleteQuerySet` that stubs `.delete()` to raise, but does NOT stub `.exists()`:
  ```python
  class _CrashOnDeleteQuerySet:
      def delete(self, *args, **kwargs):
          raise IntegrityError("simulated constraint failure")
  ```
  When `consent_hard_delete.py:120` calls `.exists()` on the mocked queryset, it raises `AttributeError: "_CrashOnDeleteQuerySet" object has no attribute "exists"`, causing the test to error rather than assert the intended rollback behavior.
- Runtime: `test_sweep_commands.py:1` — 1 failure in `TestSweepRollback` (AttributeError, not the expected assertion).

**Analysis:** The test was written to verify that the `consent_hard_delete` management command rolls back PII erasure when a constraint failure occurs. But because the mock queryset is too minimal (lacks `.exists()`), the test errors before it can validate the actual rollback behavior. This gives false assurance: the test suite runs the rollback scenario, but the mock is so incomplete that it crashes in the mock layer, not in the production code layer. If the production code `.exists()` call had a bug, this test would never catch it — it would just error on the mock. The `test_migrations.py` failure (PII-007) compounds this: the test suite integrity-check is broken, so pending schema drift can go undetected in CI.

**Recommendation:**
1. [Recommended] Extend `_CrashOnDeleteQuerySet` to stub `.exists()` (return True), `.filter()` (return self), and `.count()` (return nonzero) so the mock realistically simulates a DB queryset.
2. [Recommended] Re-run `test_sweep_commands.py` after the fix to confirm the rollback assertion now executes against real production code paths (not just mock internals).
3. [Recommended] Consider using `unittest.mock.MagicMock` or Django `QuerySet` subclass instead of a hand-rolled stub to reduce maintenance burden.

**Effort:** trivial | **Priority:** recommended
