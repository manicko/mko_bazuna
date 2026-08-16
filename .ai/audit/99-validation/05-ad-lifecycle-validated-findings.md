---
name: audit-validated-findings
description: Phase 05 Ad Lifecycle, Categories & Moderation validated findings
agent: validator
alwaysApply: false
---

# Phase 05 Audit Findings Validation — Ad Lifecycle, Categories & Moderation

**Validator:** validator
**Source:** `.ai/audit/05-ad-lifecycle/findings.md`
**Output:** `.ai/audit/99-validation/05-ad-lifecycle-validated-findings.md`
**Validated:** 2026-08-15
**Status:** complete

---

## Methodology

Each finding was validated against the actual implementation in `src/backend/apps/` and `src/telegram_bot/` (codebase root: `src/`). Validation criteria applied to every finding:

1. **Technical correctness** — is the problem real? (verified by code inspection against actual source lines)
2. **Current applicability** — is the codebase still in this state? (verified against current source files)
3. **Architectural fit** — does the recommendation align with project patterns? (checked against `docs/01-spec/technical-specification.md`, `docs/02-database/db-schema.md`, `docs/02-database/db-indexes.md`, `docs/02-database/db-enums.md`, `docs/01-spec/spec-index.md`, and the audit task `.kilo/commands/audit/phases/05-audit-ad-lifecycle.md`)
4. **Operational value** — is the fix worth the effort at this project scale?

---

<!-- severity: CRITICAL -->

### AD-001: Direct status overwrites bypass the transition state-machine driver [VALIDATED]

| Field | Value |
|-------|-------|
| **ID** | AD-001 |
| **Severity** | CRITICAL |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | Ad entity layer, Moderation-gate zone, Purge/sweep zone |
| **Classification** | mandatory |

**Description:** The state-machine transition service that validates ALLOWED_TRANSITIONS and enforces atomic side-effects (lifecycle timestamps, clearing mutually exclusive moderation_failed_at/rejected_at/archived_at fields) is not used by all state-changing code paths. Multiple moderation-action and sweep-command code paths directly overwrite the status field, bypassing the transition matrix and side-effect management entirely. The rejection path permits rejection from any pre-terminal status, not just ON_MODERATION as defined in the legal transition matrix.

**Evidence (validated — all 5 cited locations confirmed):**

- `src/backend/apps/moderation/admin_actions.py:37` — `ad.status = AdStatus.PUBLISHED` in `approve_ad()`. Direct assignment, no `transition_to()` call. The guard at line 34 (`if ad.status != AdStatus.ON_MODERATION: return`) enforces the correct precondition, but the side-effect management (published_by, original_published_at) is duplicated manually instead of going through the driver. **Confirmed.**
- `src/backend/apps/moderation/admin_actions.py:66` — `ad.status = AdStatus.REJECTED` in `reject_ad()`. Direct assignment. Guard at line 63 (`if ad.status == AdStatus.REJECTED: return`) only prevents double-rejection — it does **not** enforce that the source must be `ON_MODERATION`. This allows `REJECTED` from any pre-terminal status (PUBLISHED, DRAFT, ARCHIVED), violating the transition matrix which only permits `ON_MODERATION -> REJECTED`. **Confirmed — this is the most critical violation.**
- `src/backend/apps/moderation/admin_actions.py:114` — `ad.status = AdStatus.DELETED` in `soft_delete_ad()`. Direct assignment, bypasses `transition_to()`. The guard at line 111 (`if ad.status == AdStatus.DELETED: return`) prevents double-delete. The transition `any -> DELETED` is valid per spec, so the bypass does not violate the matrix, but it still skips the driver. **Confirmed.**
- `src/backend/apps/core/management/commands/archive_sweep.py:61` — `queryset.update(status=AdStatus.ARCHIVED, archived_at=timezone.now())`. Queryset-level bulk update bypasses `transition_to()` entirely. The queryset filters `status=AdStatus.PUBLISHED` (line 47) so only PUBLISHED ads are archived, but no transition validation or side-effect management occurs. **Confirmed.**
- `src/backend/apps/ads/models.py:248-374` — `transition_to()` enforces `ALLOWED_TRANSITIONS` dictionary (line 280) and sets/clears lifecycle timestamps atomically (lines 318-374). The `ALLOWED_TRANSITIONS` dict matches the spec state machine (`docs/02-database/db-schema.md:132-137`, `docs/01-spec/spec-index.md:78-82`). **Confirmed.**
- `src/telegram_bot/tests/test_ad_lifecycle.py:338-363` — `TestTransitionValidation` tests `transition_to()` directly (DRAFT->PUBLISHED raises, DELETED blocks transition, DRAFT->ON_MODERATION succeeds). No test verifies that `approve_ad()`, `reject_ad()`, `soft_delete_ad()`, or sweep commands reject forbidden transitions (e.g., PUBLISHED->REJECTED). **Confirmed — no coverage gap tests exist.**

**Validation Note:**
- **Action:** validated
- **Detail:** All 5 cited code locations verified against the current source. The `transition_to()` method at `models.py:248-374` is correct and matches the spec state machine. The `reject_ad` function guard is the most dangerous gap — it allows rejection from any non-REJECTED status, directly violating the `ON_MODERATION -> REJECTED` rule.
- **Dependency:** None. `transition_to()` is already correct; this is purely about routing the admin/sweep code paths through it.

**Rollout safety:** Changing `reject_ad` to enforce `ON_MODERATION -> REJECTED` (via `transition_to()`) is a **behavioral change** — admins will no longer be able to reject ads from PUBLISHED/DRAFT/ARCHIVED statuses. This should be intentional (it brings the code in line with the spec). Low technical risk, medium operational risk (behavior change).

**Recommendation:** Route all single-row status changes through `transition_to()` to guarantee the `ALLOWED_TRANSITIONS` matrix is enforced and lifecycle side-effects are applied consistently. This covers `approve_ad()`, `reject_ad()`, and `soft_delete_ad()` in `admin_actions.py` plus per-row updates in the bot handler. For `reject_ad`, add a guard enforcing `ad.status == AdStatus.ON_MODERATION` before allowing rejection (the current guard at `admin_actions.py:63` only blocks re-rejection, not invalid source statuses).

For the **batch sweep path** (`archive_sweep.py`), the source-status precondition is already enforced at the queryset level (`status=AdStatus.PUBLISHED`, line 47), so the remaining gap is **lifecycle side-effect consistency** - a status timestamp must accompany its status. Enforce this at the SQL level with a **database CHECK constraint** on the `ads` table (selected over a stored procedure - see *Rejected alternative* below), declared through the Django ORM so it is applied by the migration system rather than hand-managed SQL. Implementation steps:

1. Add `CheckConstraint` entries to `Ad.Meta.constraints` in `src/backend/apps/ads/models.py`, one per status-to-timestamp invariant, using the `Q` API and `AdStatus` enum values (mirroring the existing `models.Index(condition=Q(...))` pattern used for `IX_ads_archive_sweep` etc.):

   - `status = ARCHIVED` implies `archived_at IS NOT NULL` -> name `ck_ads_archived_at_if_archived`
   - `status = REJECTED` implies `rejected_at IS NOT NULL` -> name `ck_ads_rejected_at_if_rejected`
   - `status = ON_MODERATION_FAILED` implies `moderation_failed_at IS NOT NULL` -> name `ck_ads_moderation_failed_at_if_failed`
   - `status = DELETED` implies `deleted_at IS NOT NULL` -> name `ck_ads_deleted_at_if_deleted`
   - `status = PUBLISHED` implies `published_at IS NOT NULL` -> name `ck_ads_published_at_if_published`
   - `moderation_failed_at` and `rejected_at` mutually exclusive -> name `ck_ads_failed_and_rejected_mutually_exclusive`

2. Generate and commit the migration via `make makemigrations` (-> `manage.py makemigrations ads`). The constraint is applied by the one-shot advisory-locked `migrate` service described in `docs/ops/migration-workflow.md`, which runs exactly once before both web and bot start - no separate SQL deployment script is required.

3. Verify with `uv run pytest src/backend/apps/core/tests/test_sweep_commands.py src/backend/apps/ads/` and add a regression test asserting that a bulk `Ad.objects.filter(status=AdStatus.PUBLISHED).update(status=AdStatus.ARCHIVED)` (without `archived_at`) raises `django.db.IntegrityError`, proving the constraint guards the sweep path. If any pre-existing dev rows violate the invariants, backfill the timestamps before applying the migration (the dev DB is disposable per `docs/ops/migration-workflow.md`).

**Rejected alternative - stored procedure:** A stored procedure would embed executable transition-matrix logic as procedural `plpgsql` inside PostgreSQL, duplicating the `ALLOWED_TRANSITIONS` dict already defined in Python (`ads/models.py:280`) and violating the project's strict separation of concerns (business logic in Django/Python; the database reserved for declarative integrity). The project uses **zero** stored procedures - a repo-wide search for `CREATE (OR REPLACE) PROCEDURE` returns no matches; the only `CREATE FUNCTION` statements are two trigger functions in `ads/migrations/0002_initial.py` (lines 12 and 34) for FTS `search_vector` sync-safety. A CHECK constraint cannot see the prior row state (`OLD` is unavailable outside a row-level trigger), so it cannot express the full transition matrix; the matrix stays in `transition_to()` (Python) while the constraint enforces the complementary, DB-appropriate invariant - timestamp/side-effect consistency - that the bulk sweep path is the most likely to violate. If full transition-matrix enforcement is ever needed on a bulk path, route through `transition_to()` per-row (or a row-level trigger using `OLD`) rather than a stored procedure.

**Effort:** medium | **Priority:** mandatory

---

<!-- severity: HIGH -->

### AD-002: No purge job for DELETED status — unbounded accumulation [VALIDATED]

| Field | Value |
|-------|-------|
| **ID** | AD-002 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | Purge/sweep zone, Ad entity layer |
| **Classification** | mandatory |

**Description:** The retention table defines DELETED to 4-month purge, but no scheduled sweep command targets the DELETED status. The AdStatus enumeration includes a DELETED value, and the soft-delete action transitions ads to DELETED with a deleted_at timestamp, yet there is no scheduled job to permanently remove ads after the 4-month retention window. The existing delete-and-purge sweep only operates on ARCHIVED status, not DELETED.

**Evidence (validated — all locations confirmed):**

- `src/backend/apps/core/enums.py:48` — `AdStatus.DELETED = "deleted"`. **Confirmed.**
- `src/backend/apps/moderation/admin_actions.py:114-115` — `soft_delete_ad()` sets `ad.status = AdStatus.DELETED` and `ad.deleted_at = timezone.now()`. **Confirmed.**
- `.kilo/commands/audit/phases/05-audit-ad-lifecycle.md:75` — Retention table: `| DELETED | 4 months | purge |`. **Confirmed.** The audit task is the specification for this audit phase and explicitly defines the 4-month purge retention for DELETED status.
- Management commands verified via `src/backend/apps/core/management/commands/` glob — only these exist:
  - `archive_sweep.py` — targets PUBLISHED -> ARCHIVED (60-day window from `published_at`, line 49)
  - `delete_sweep.py` — targets ARCHIVED -> hard delete (120-day window from `published_at`, line 50-51)
  - `purge_failed_ads.py` — targets ON_MODERATION_FAILED -> delete (7-day window from `moderation_failed_at`, line 49)
  - `purge_rejected_ads.py` — targets REJECTED -> delete (90-day window from `rejected_at`, line 49-50)
  - `sweep_drafts.py` — targets DRAFT -> delete (30-minute window from `created_at`, line 47-48)
  - `consent_hard_delete.py` — targets **User** objects (consent_revoked_at), not AdStatus.DELETED. Cascades via ORM but is triggered by user consent withdrawal, not by ad deletion status. **Not a DELETED-status purge.**
- No partial index exists for DELETED status filtering: `src/backend/apps/ads/models.py:207-243` and `docs/02-database/db-indexes.md:23-38` list indexes only for PUBLISHED, ARCHIVED, ON_MODERATION_FAILED, and REJECTED. **Confirmed — no DELETED index.**

**Validation Note:**
- **Action:** validated
- **Detail:** No management command targets `AdStatus.DELETED` for purge. The `consent_hard_delete` command is a user-level operation (triggers on consent revocation, not ad status), not a status-based purge. The retention table in the audit task explicitly defines a 4-month purge for DELETED, yet `deleted_at` has no corresponding sweep job.

**Recommendation:** Add a purge command for DELETED status with a 4-month retention window measured from `deleted_at`, using an advisory lock, and include a partial index on `[status, deleted_at]` filtered by `Q(status=AdStatus.DELETED)`.

**Effort:** medium | **Priority:** mandatory

---

<!-- severity: HIGH -->

### AD-003: Moderation max-ads check counts failed ads as active [VALIDATED]

| Field | Value |
|-------|-------|
| **ID** | AD-003 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | Moderation-gate zone |
| **Classification** | mandatory |

**Description:** The per-user active-ad limit counts ON_MODERATION_FAILED (a terminal failure state queued for purge) as an active ad alongside PUBLISHED and ON_MODERATION. Failed ads are not actively serving — they are held for a 7-day retention window then permanently purged. Counting them toward the user active ad quota causes progressive lockout for sellers whose ads repeatedly fail auto-moderation.

**Evidence (validated — all 4 cited locations confirmed):**

- `src/backend/apps/moderation/services/auto_moderation.py:195` — `active_statuses = [AdStatus.PUBLISHED, AdStatus.ON_MODERATION, AdStatus.ON_MODERATION_FAILED]`. **Confirmed** — `ON_MODERATION_FAILED` is included.
- `src/backend/apps/moderation/services/auto_moderation.py:194` — Comment: `# Count only published and on-moderation ads (not drafts, rejected, archived, deleted)`. The comment's intent is to count only active (serving) ads, but the code contradicts this by including `ON_MODERATION_FAILED`. **Confirmed — comment and code disagree.**
- `src/backend/apps/ads/models.py:290` — In `ALLOWED_TRANSITIONS`: `AdStatus.ON_MODERATION_FAILED: set(),  # Terminal`. **Confirmed —** it is a terminal state with no outgoing transitions.
- `.kilo/commands/audit/phases/05-audit-ad-lifecycle.md:71` — Retention table: `| ON_MODERATION_FAILED | 7 days | purge |`. **Confirmed** — it is a purge-bound terminal state, not active. Also confirmed by `docs/02-database/db-enums.md:30`: "failed auto-check (purged after 7 days)".

**Validation Note:**
- **Action:** validated
- **Detail:** All evidence confirmed. The code at line 195 includes `ON_MODERATION_FAILED` in the active-ads count, while the comment at line 194 and the spec both treat it as a terminal/purge-bound state. This causes sellers whose ads fail auto-moderation to have those non-serving ads count against their quota, potentially causing progressive lockout.

**Recommendation:** Remove `AdStatus.ON_MODERATION_FAILED` from the active-statuses list in `_validate_max_ads_per_user`. The correct active set should be `[AdStatus.PUBLISHED, AdStatus.ON_MODERATION]` only.

**Effort:** small | **Priority:** mandatory

---

<!-- severity: MEDIUM -->

### AD-004: Pre-submission validation function mutates ad state [VALIDATED — evidence corrected]

| Field | Value |
|-------|-------|
| **ID** | AD-004 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | Moderation-gate zone, Audit-log zone |
| **Classification** | mandatory |

**Description:** The pre-submission validation function is documented as read-only compliance checking that returns (passed, error_message) without publishing. Internally, however, it calls the failure handler on every validation failure, which transitions the ad to ON_MODERATION_FAILED, sets moderation_failed_at, creates a ModeratorActionLog entry, and creates an AnalyticsEvent. If used for pre-submission validation (as documented), the ad is marked as failed before it is ever submitted, making publication impossible. Audit-log and analytics entries are also created for validation-only checks, polluting the audit trail.

**Evidence (validated — 4 of 4 substantive locations confirmed; 1 claim corrected):**

- `src/backend/apps/moderation/services/auto_moderation.py:254-324` — `check()` function; docstring at line 254 states "Check ad compliance against ModerationCriteria without publishing" and "This function is for pre-submission validation where seller-safe errors are required." **Confirmed.**
- `src/backend/apps/moderation/services/auto_moderation.py:290, 295, 300, 305, 310, 315, 320` — Each validation branch calls `_fail_moderation(ad)`. **Confirmed —** all 7 validation branches call `_fail_moderation`.
- `src/backend/apps/moderation/services/auto_moderation.py:218-228` — `_fail_moderation()` calls `set_moderation_failed(ad)` (line 222), which at `src/backend/apps/moderation/services/moderation_log.py:176` calls `ad.transition_to(AdStatus.ON_MODERATION_FAILED)` and `log_auto_fail()` (line 178). Also creates `AnalyticsEvent` (lines 224-228). **Confirmed** — the state mutation occurs via `set_moderation_failed` -> `transition_to`, not directly in `_fail_moderation` as the finding described.
- `src/backend/apps/moderation/services/__init__.py:3` — `check` is exported: `from .auto_moderation import auto_moderate, check`. **Confirmed.**
- `src/backend/apps/moderation/tests/test_auto_moderation.py:248, 258` — `check()` is called in tests. **CORRECTION:** The finding claimed "never called anywhere in the codebase (confirmed via grep — no callers found)" — this is INACCURATE. `check()` IS called in test code (lines 248, 258). It is NOT called in any production code path. The test at line 252-263 creates an ad with `title="abc"` (too short) and calls `check(ad)` — this test unknowingly exercises the state mutation (the ad is transitioned to `ON_MODERATION_FAILED`), but the test only asserts on the return tuple, not the ad status.
- `src/backend/apps/moderation/services/auto_moderation.py:90` — `auto_moderate()` is the documented path for actual status transitions and IS used in the bot handler (`ad_create.py:685` imports it; called from `update_ad_and_moderate` at `ad_create.py:465`). **Confirmed.**

**Validation Note:**
- **Action:** validated (evidence corrected)
- **Detail:** The core finding is correct — `check()` is documented as read-only pre-submission validation but mutates state via `_fail_moderation()` -> `set_moderation_failed()` -> `transition_to(ON_MODERATION_FAILED)` + `log_auto_fail()` + `AnalyticsEvent` creation. One evidence claim is inaccurate: `check()` IS called in tests (not "no callers found"), but it is NOT wired into production code paths. The test `test_check_returns_seller_safe_error_on_fail` (test_auto_moderation.py:252-263) demonstrates the bug — it calls `check()` on an ad that fails validation, silently transitioning it to `ON_MODERATION_FAILED`.
- **Dependency:** If `check()` were wired into the bot pre-submission validation flow, it would make ads un-publishable. Currently latent (tests only).

**Recommendation:** Remove all `_fail_moderation()` calls from `check()` (lines 290, 295, 300, 305, 310, 315, 320) so the function performs pure validation — returning `(False, error_message)` without mutating ad status, setting timestamps, or creating audit/analytics entries. `check()` is not called in any production code path (verified: invoked only in `test_auto_moderation.py:248,258`); `auto_moderate()` is the designated production handler for status transitions, used by the bot handler (`ad_create.py:685,756`) and web edit view (`ads/views/edit.py:15`). After removing the side-effects, update the docstring at line 259 to no longer describe the mutation behavior.

**Effort:** small | **Priority:** mandatory

---

<!-- severity: MEDIUM -->

### AD-005: Category rename propagation relies on no-op UPDATE trigger [RECLASSIFIED]

| Field | Value |
|-------|-------|
| **ID** | AD-005 |
| **Severity** | MEDIUM |
| **Original Type** | SPEC-DEVIATION |
| **Reclassified Type** | BEST-PRACTICE |
| **Affected Modules** | Category-tree zone, Search/FTS zone |
| **Classification** | mandatory |

**Description:** The AFTER-trigger on category name rename performs a self-assignment UPDATE (SET category_id = ads.category_id) that has no direct effect on its own. Propagation of the denormalized category_name field and the search_vector field works only as an accidental side-effect: the no-op UPDATE fires the BEFORE INSERT OR UPDATE search-vector trigger, which then re-fetches the category name from the (now-renamed) categories table and populates NEW.category_name and NEW.search_vector. This trigger-chaining is fragile and semantically incorrect.

**Evidence (validated — all 4 cited locations confirmed):**

- `src/backend/apps/ads/migrations/0002_initial.py:33-41` — `CATEGORY_PROPAGATE_FN_SQL`: `UPDATE ads SET category_id = ads.category_id WHERE category_id = NEW.id;`. The `SET category_id = ads.category_id` is a self-assignment (no-op). **Confirmed.**
- `src/backend/apps/ads/migrations/0002_initial.py:11-23` — `SEARCH_VECTOR_FN_SQL`: BEFORE INSERT OR UPDATE trigger that sets `NEW.category_name` and `NEW.search_vector` by SELECTing from `categories WHERE id = NEW.category_id`. **Confirmed.**
- `src/backend/apps/ads/migrations/0002_initial.py:26-31` — `SEARCH_VECTOR_TRIGGER_SQL`: fires BEFORE INSERT OR UPDATE ON ads FOR EACH ROW. **Confirmed.**
- `src/backend/apps/ads/tests/test_search_triggers.py:96-103` — `test_category_rename_propagates` passes, confirming propagation works today — but only because the no-op UPDATE activates the search-vector trigger. **Confirmed.**
- `src/backend/apps/ads/migrations/0002_initial.py:37` — The `WHERE category_id = NEW.id` clause updates ALL ads matching that category, rewriting every affected row even if only the name text changed. **Confirmed.**

**Critical spec alignment finding:**

- `docs/02-database/db-indexes.md:86-97` — The spec doc **explicitly documents** the no-op self-assignment pattern with the comment `-- trigger #2 recomputes category_name+search_vector`:

  ```sql
  CREATE OR REPLACE FUNCTION categories_name_propagate() RETURNS TRIGGER AS $$
  BEGIN
    UPDATE ads SET category_id = ads.category_id  -- trigger #2 recomputes category_name+search_vector
    WHERE category_id = NEW.id;
    RETURN NEW;
  END;
  $$ LANGUAGE plpgsql;
  ```

  The migration code (`0002_initial.py:36`) matches this spec doc **exactly**. Therefore, the implementation does **not** deviate from the specification — it follows the documented pattern.

**Validation Note:**
- **Action:** reclassified
- **Detail:** The no-op UPDATE pattern is **real and fragile** (propagation works only via accidental trigger-chaining). However, the spec doc (`docs/02-database/db-indexes.md:86-97`) explicitly documents this exact pattern, and the migration code matches it precisely. The code does not deviate from the spec; the concern is a fragile design that the spec itself endorses. Reclassified from SPEC-DEVIATION to BEST-PRACTICE.
- **Cross-finding observation (not one of the 7 findings):** `docs/02-database/db-indexes.md:57-76` shows a **multi-language** `search_vector` function (with `title_bs`, `description_bs`, `title_en`, `description_en`), but the migration `0002_initial.py:11-24` only implements the **Russian** variant (`title`, `description`). Migration `0003_ad_i18n_fields.py` adds the language columns but does **not** update the trigger function.

**Recommendation:** Rewrite the category rename trigger to directly update `category_name` on affected ads (rather than the no-op self-assignment). This removes the fragile trigger-chaining dependency and makes the intent obvious. The search-vector trigger will still fire on the `category_name` UPDATE and refresh `search_vector` as needed. **Requires a new database migration.**

**Rollout safety:** Changing a database trigger function requires a new migration. The `test_category_rename_propagates` test (test_search_triggers.py:96-103) must continue to pass. Medium risk.

**Effort:** medium | **Priority:** mandatory

---
<!-- severity: LOW -->

### AD-006: original_language hardcoded to bs in bot handler [VALIDATED]

| Field | Value |
|-------|-------|
| **ID** | AD-006 |
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | Bot FSM + DRAFT-persistence zone, Ad entity layer |
| **Classification** | advisory |

**Description:** The bot handler that persists ad content after translation sets original_language to a single hardcoded value regardless of the seller actual input language. The bot collects the seller original title/description, translates to all supported languages, then sets original_language to a fixed value. This means all bot-created ads are incorrectly attributed to one language, even if the seller wrote in a different language.

**Evidence (validated — all 4 cited locations confirmed):**

- `src/telegram_bot/handlers/ad_create.py:473` — `original_language="bs"` — a literal string, not via `LanguageLocale` enum value or language detection. **Confirmed.**
- `src/backend/apps/core/enums.py:159-164` — `LanguageLocale` StrEnum: `RUSSIAN = "ru"`, `BOSNIAN = "bs"`, `ENGLISH = "en"`. **Confirmed.**
- `src/telegram_bot/handlers/ad_create.py:675` — `update_ad_and_moderate()` accepts `original_language: str | None = None`. Line 711: `if original_language: ad.original_language = original_language`. **Confirmed.**
- `src/backend/apps/ads/models.py:75-79` — `original_language = models.CharField(max_length=5, ..., help_text="Original language code of the ad (e.g. 'ru', 'en', 'bs')")`. **Confirmed.**
- `docs/02-database/db-schema.md:102` — `original_language (VARCHAR(5), nullable) # Source language code (e.g. 'ru', 'bs', 'en')`. **Confirmed.**
- `src/backend/apps/core/middleware/language.py:30,74,104,147-148` — `LanguageLocale` is used for language resolution elsewhere in the project. **Confirmed.**
- `src/backend/apps/seed/generators/ads.py:443` — The seed module demonstrates the **correct pattern**: `original_language=LanguageLocale.RUSSIAN.value`. This confirms the project convention that `ad_create.py` violates. **Confirmed.**

**Validation Note:**
- **Action:** validated
- **Detail:** All evidence confirmed. The bot handler hardcodes `original_language="bs"` at line 473, bypassing the `LanguageLocale` enum. The project already has the correct pattern in the seed module (`ads.py:443` uses `LanguageLocale.RUSSIAN.value`). The spec (`db-schema.md:102`, `db-enums.md:91-99`) defines the field as a source language code.

**Recommendation:** Detect the seller input language from the Telegram message `from_user.language_code` or content analysis, and set `original_language` to the matching `LanguageLocale` value. At minimum, use the `LanguageLocale` enum value instead of the raw string literal to maintain type safety.

**Effort:** small | **Priority:** advisory

---

<!-- severity: LOW -->

### AD-007: Physical file deletion inside database transaction [VALIDATED]

| Field | Value |
|-------|-------|
| **ID** | AD-007 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | Purge/sweep zone, Photo-collection zone |
| **Classification** | advisory |

**Description:** All sweep and purge commands call physical file deletion (os.remove) inside transaction.atomic(). The file-deletion utility only catches FileNotFoundError; any other filesystem error (e.g., PermissionError, OSError) propagates and rolls back the transaction. However, files deleted before the failing call are already physically removed — a non-atomic outcome where the DB rows are restored but disk files are lost.

**Evidence (validated — all cited locations confirmed):**

- `src/telegram_bot/services/media.py:80-96` — `delete_photo()` catches only `FileNotFoundError` (line 94). Any other `OSError` subtype (e.g., `PermissionError`, `IsADirectoryError`) propagates uncaught. **Confirmed.**
- All four sweep/purge commands call `delete_photo()` inside `transaction.atomic()`:
  - `src/backend/apps/core/management/commands/delete_sweep.py:72-76` — `queryset.delete()` at line 72, then `delete_photo()` at lines 75-76, inside `with transaction.atomic():` (line 44). **Confirmed.**
  - `src/backend/apps/core/management/commands/purge_failed_ads.py:71-75` — same pattern. **Confirmed.**
  - `src/backend/apps/core/management/commands/purge_rejected_ads.py:73-77` — same pattern. **Confirmed.**
  - `src/backend/apps/core/management/commands/sweep_drafts.py:70-74` — same pattern. **Confirmed.**
- In all four commands, the DB delete (`queryset.delete()`) runs **before** the file-deletion loop. **Confirmed.**
- `src/backend/apps/core/tests/test_sweep_commands.py:161, 174, 195` — Tests use storage keys like `"test-uuid.jpg"` that do not exist on disk. When `delete_photo()` is called on these keys, it raises `FileNotFoundError` (caught). Tests verify ORM CASCADE deletion of `AdImage` DB rows but do **not** exercise the file-deletion error path with real files. **Confirmed.**

**Validation Note:**
- **Action:** validated
- **Detail:** All evidence confirmed. The `delete_photo()` utility at media.py:94 catches only `FileNotFoundError`, letting `PermissionError`, `IsADirectoryError`, and other `OSError` subtypes propagate. All four sweep/purge commands call `delete_photo()` inside `transaction.atomic()` after the ORM cascade delete. If a filesystem error occurs mid-loop, the transaction rolls back (DB rows restored) but already-deleted files are physically lost — a non-atomic outcome.

**Recommendation:** Move physical file deletion outside the database transaction. After the `transaction.atomic()` block commits successfully, iterate over the collected storage keys and call `delete_photo()` with independent error handling (catch and log all `OSError` subtypes, queue for retry).

**Effort:** medium | **Priority:** advisory

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 6 | AD-001, AD-002, AD-003, AD-004, AD-006, AD-007 |
| Reclassified | 1 | AD-005 (SPEC-DEVIATION -> BEST-PRACTICE) |
| Merged | 0 | — |
| Rejected | 0 | — |

### Reclassified Findings

| ID | Original Type | New Type | Rationale |
|----|---------------|----------|-----------|
| AD-005 | SPEC-DEVIATION | BEST-PRACTICE | The no-op UPDATE pattern is explicitly documented in `docs/02-database/db-indexes.md:86-97` with a comment acknowledging the trigger-chain. The migration code matches the spec exactly. The code does not deviate from the spec; the concern is a fragile design that the spec itself endorses. The recommendation (rewrite the trigger to directly update `category_name`) remains valid as a best-practice improvement. |

### Rejected Findings

(None — all 7 findings have valid evidence and correct or near-correct recommendations.)

### Merged Findings

(None — no findings share a root cause.)

---

## Cross-Finding Analysis

### Same Root Cause (merge candidates)

- **AD-001 + AD-007** both affect the purge/sweep zone, but have different root causes: AD-001 is about bypassing the `transition_to()` state-machine driver; AD-007 is about filesystem/DB atomicity mismatch. **No merge.**
- **AD-001 + AD-004** both relate to `transition_to()` usage: AD-001 is about admin actions bypassing `transition_to()`; AD-004 is about `check()` calling `_fail_moderation()` which internally calls `transition_to()` (via `set_moderation_failed()`). The issue in AD-004 is that `check()` should be read-only, not that it bypasses `transition_to()`. **Different root causes — no merge.**

### Conflict Detection

No conflicting evidence found between findings. The findings are internally consistent and describe distinct problems.

### Dependency Chains

| Finding | Depends On | Notes |
|---------|-----------|-------|
| AD-001 | `transition_to()` correctness (models.py:248-374) | Already correct; fix is routing admin/sweep paths through it |
| AD-005 | DB migration workflow | Requires new `RunSQL` migration to rewrite trigger function |
| AD-007 | All 4 sweep/purge commands | Fix touches 4 files simultaneously; must be coordinated |
| AD-004 | Test files (test_auto_moderation.py:248,258) | Tests that call `check()` may need updating after `_fail_moderation` is removed |

### Cross-Finding Observation (not one of the 7 findings)

**Search vector SQL discrepancy:** `docs/02-database/db-indexes.md:57-76` documents a **multi-language** `ads_search_vector_fn()` function (with `title_bs`, `description_bs`, `title_en`, `description_en`), but the actual migration `0002_initial.py:11-24` only implements the **Russian** variant (`title`, `description`). Migration `0003_ad_i18n_fields.py` adds the language columns to the model but does **not** update the trigger function. This means the `search_vector` does not include Bosnian or English content, which would break multi-language search — a functional gap despite the spec documenting multi-language FTS.

---

## Rollout Safety Assessment

### AD-001 (CRITICAL — SPEC-DEVIATION)
- **Risk:** Changing `reject_ad` to route through `transition_to()` would enforce `ON_MODERATION -> REJECTED` only. This is a **behavioral change** — admins will no longer be able to reject ads from PUBLISHED/DRAFT/ARCHIVED statuses. This aligns with the spec state machine but may require operational awareness.
- **Ordering:** Fix admin_actions.py first (approve_ad, reject_ad, soft_delete_ad), then archive_sweep.py. No circular dependencies.

### AD-002 (HIGH — SPEC-DEVIATION)
- **Risk:** New management command + DB migration (partial index). Follows existing sweep patterns (advisory lock, transaction, dry-run). Low risk.
- **Spec gap:** The audit task defines DELETED to 4-month purge, but `db-enums.md:32` only says "soft delete" without a retention period. Implementation should follow the audit task.

### AD-003 (HIGH — SPEC-DEVIATION)
- **Risk:** One-line change. Very low risk. Correct behavior change.

### AD-004 (MEDIUM — SPEC-DEVIATION)
- **Risk:** Removing `_fail_moderation()` calls from `check()`. Since `check()` is only called in tests, production impact is zero. Tests at `test_auto_moderation.py:248,258` do not assert on the side-effects, so they should still pass.

### AD-005 (MEDIUM — BEST-PRACTICE, reclassified)
- **Risk:** New DB migration rewriting the `categories_name_propagate()` trigger function. Medium risk. The `test_category_rename_propagates` test (test_search_triggers.py:96-103) must pass.

### AD-006 (LOW — SPEC-DEVIATION, advisory)
- **Risk:** Adding language detection logic. Low risk. The seed module (`ads.py:443`) already demonstrates the correct pattern. The `from_user.language_code` is available from aiogram.

### AD-007 (LOW — BEST-PRACTICE, advisory)
- **Risk:** Restructuring 4 sweep/purge commands. Medium risk — changes the error recovery model. The DB deletion and file deletion are already decoupled in data collection. Moving the file-deletion loop outside `transaction.atomic()` is a straightforward refactor.

---

## Required Fixes

1. **AD-001 (CRITICAL, mandatory):** Route `approve_ad()`, `reject_ad()`, `soft_delete_ad()` in `admin_actions.py` through `transition_to()`. Fix `reject_ad` guard to enforce `ON_MODERATION -> REJECTED`. Add DB `CheckConstraint`(s) on `Ad.Meta` enforcing status-timestamp invariants (see AD-001 Recommendation) and generate the migration; the sweep already enforces source-status via its queryset filter.
2. **AD-002 (HIGH, mandatory):** Add a `purge_deleted_ads` management command with 4-month retention from `deleted_at`, advisory lock, and a partial index `IX_ads_purge_deleted` on `[status, deleted_at]` filtered `Q(status=AdStatus.DELETED)`. Schedule in cron.
3. **AD-003 (HIGH, mandatory):** Remove `AdStatus.ON_MODERATION_FAILED` from `active_statuses` in `_validate_max_ads_per_user()` (auto_moderation.py:195). Correct set: `[AdStatus.PUBLISHED, AdStatus.ON_MODERATION]`.
4. **AD-004 (MEDIUM, mandatory):** Remove all `_fail_moderation(ad)` calls from `check()` in `auto_moderation.py:254-324`. Make `check()` purely read-only validation.
5. **AD-005 (MEDIUM, mandatory):** Rewrite `categories_name_propagate()` trigger function in a new migration to directly `UPDATE ads SET category_name = NEW.name WHERE category_id = NEW.id`.

## Advisory Recommendations

6. **AD-006 (LOW, advisory):** Replace hardcoded `original_language="bs"` at `ad_create.py:473` with language detection from `message.from_user.language_code` mapped to `LanguageLocale`, or at minimum use `LanguageLocale.BOSNIAN.value`.
7. **AD-007 (LOW, advisory):** Move `delete_photo()` calls outside `transaction.atomic()` in all 4 sweep/purge commands. Add independent error handling that catches all `OSError` subtypes, logs, and queues for retry.

### Additional Advisory (cross-finding)

8. **Search vector discrepancy (cross-finding):** Migrate `ads_search_vector_fn()` to include multi-language columns (`title_bs`, `description_bs`, `title_en`, `description_en`) as documented in `db-indexes.md:57-76` but absent from `migration 0002_initial.py:11-24`.
