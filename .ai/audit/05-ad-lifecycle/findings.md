# Phase 05 Audit Findings — Ad Lifecycle, Categories & Moderation

**Executor:** audit-executor
**Template:** .ai/audit/templates/audit-findings.md
**Status:** complete
**Validated:** no

---

## Findings

### AD-001: Direct status overwrites bypass the transition state-machine driver

| Field | Value |
|-------|-------|
| **ID** | AD-001 |
| **Severity** | CRITICAL |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | Ad entity layer, Moderation-gate zone, Purge/sweep zone |
| **Classification** | mandatory |

**Description:** The state-machine transition service that validates ALLOWED_TRANSITIONS and enforces atomic side-effects (lifecycle timestamps, clearing mutually exclusive moderation_failed_at/rejected_at/archived_at fields) is not used by all state-changing code paths. Multiple moderation-action and sweep-command code paths directly overwrite the status field, bypassing the transition matrix and side-effect management entirely. The rejection path permits rejection from any pre-terminal status, not just ON_MODERATION as defined in the legal transition matrix.

**Evidence:**
- Moderation-action functions directly assign ad.status without calling transition_to():
  - src/backend/apps/moderation/admin_actions.py:37 — ad.status = AdStatus.PUBLISHED (approve_ad)
  - src/backend/apps/moderation/admin_actions.py:66 — ad.status = AdStatus.REJECTED (reject_ad; guard only checks if ad.status == AdStatus.REJECTED: return, allowing REJECTED from any status including PUBLISHED, DRAFT, ARCHIVED)
  - src/backend/apps/moderation/admin_actions.py:114 — ad.status = AdStatus.DELETED (soft_delete_ad)
- Purge/sweep commands bypass transition_to via queryset-level updates:
  - src/backend/apps/core/management/commands/archive_sweep.py:61 — queryset.update(status=AdStatus.ARCHIVED, archived_at=...)
- The canonical driver with validation logic and side-effect management:
  - src/backend/apps/ads/models.py:248-374 — transition_to() enforces ALLOWED_TRANSITIONS dictionary at line 280 and sets/clears lifecycle timestamps atomically at lines 322-374.
- Tests for transition_to validation exist and pass (src/telegram_bot/tests/test_ad_lifecycle.py:338-363), but no test verifies that admin-action or sweep-command paths reject forbidden transitions (e.g., PUBLISHED to REJECTED).

**Recommendation:** Route all status changes through transition_to() to guarantee the ALLOWED_TRANSITIONS matrix is enforced and lifecycle side-effects are applied consistently. For batch sweep operations, add an explicit status precondition filter and also enforce the transition guard at the SQL level via a database CHECK constraint or a stored procedure. For reject_ad, add a guard enforcing ad.status == AdStatus.ON_MODERATION before allowing rejection.

---

### AD-002: No purge job for DELETED status — unbounded accumulation

| Field | Value |
|-------|-------|
| **ID** | AD-002 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | Purge/sweep zone, Ad entity layer |
| **Classification** | mandatory |

**Description:** The retention table defines DELETED to 4-month purge, but no scheduled sweep command targets the DELETED status. The AdStatus enumeration includes a DELETED value, and the soft-delete action transitions ads to DELETED with a deleted_at timestamp, yet there is no scheduled job to permanently remove ads after the 4-month retention window. The existing delete-and-purge sweep only operates on ARCHIVED status, not DELETED.

**Evidence:**
- AdStatus.DELETED is defined in src/backend/apps/core/enums.py:48.
- soft_delete_ad sets ad.status = AdStatus.DELETED and ad.deleted_at = timezone.now() at src/backend/apps/moderation/admin_actions.py:114-115.
- Retention table in audit task: DELETED to 4 months to purge.
- No management command exists targeting AdStatus.DELETED:
  - archive_sweep — targets PUBLISHED, transitions to ARCHIVED after 60 days (src/backend/apps/core/management/commands/archive_sweep.py:47-64)
  - delete_sweep — targets ARCHIVED, deletes after 120 days (src/backend/apps/core/management/commands/delete_sweep.py:49-52)
  - purge_failed_ads — targets ON_MODERATION_FAILED (src/backend/apps/core/management/commands/purge_failed_ads.py:49)
  - purge_rejected_ads — targets REJECTED (src/backend/apps/core/management/commands/purge_rejected_ads.py:50)
- No delete_sweep or similar targeting DELETED exists in src/backend/apps/core/management/commands/.
- No partial index exists for DELETED status filtering (only indexes for PUBLISHED, ARCHIVED, ON_MODERATION_FAILED, REJECTED in src/backend/apps/ads/models.py:207-243).

**Recommendation:** Add a purge command for DELETED status with a 4-month retention window measured from deleted_at, using an advisory lock, and include a partial index on [status, deleted_at] filtered by Q(status=AdStatus.DELETED).

---

### AD-003: Moderation max-ads check counts failed ads as active

| Field | Value |
|-------|-------|
| **ID** | AD-003 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | Moderation-gate zone |
| **Classification** | mandatory |

**Description:** The per-user active-ad limit counts ON_MODERATION_FAILED (a terminal failure state queued for purge) as an active ad alongside PUBLISHED and ON_MODERATION. Failed ads are not actively serving — they are held for a 7-day retention window then permanently purged. Counting them toward the user active ad quota causes progressive lockout for sellers whose ads repeatedly fail auto-moderation.

**Evidence:**
- src/backend/apps/moderation/services/auto_moderation.py:195 — active_statuses = [AdStatus.PUBLISHED, AdStatus.ON_MODERATION, AdStatus.ON_MODERATION_FAILED]
- The comment at line 194 states Count only published and on-moderation ads, but ON_MODERATION_FAILED is included in the list.
- AdStatus.ON_MODERATION_FAILED is defined as a terminal state in src/backend/apps/ads/models.py:290 — ALLOWED_TRANSITIONS maps it to set() (no outgoing transitions).
- The retention table specifies ON_MODERATION_FAILED to 7 days to purge, confirming it is a terminal/purge-bound state, not active.

**Recommendation:** Remove AdStatus.ON_MODERATION_FAILED from the active-statuses list in _validate_max_ads_per_user. The correct active set should be [AdStatus.PUBLISHED, AdStatus.ON_MODERATION] only.

---

### AD-004: Pre-submission validation function mutates ad state

| Field | Value |
|-------|-------|
| **ID** | AD-004 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | Moderation-gate zone, Audit-log zone |
| **Classification** | mandatory |

**Description:** The pre-submission validation function is documented as read-only compliance checking that returns (passed, error_message) without publishing. Internally, however, it calls the failure handler on every validation failure, which transitions the ad to ON_MODERATION_FAILED, sets moderation_failed_at, creates a ModeratorActionLog entry, and creates an AnalyticsEvent. If used for pre-submission validation (as documented), the ad is marked as failed before it is ever submitted, making publication impossible. Audit-log and analytics entries are also created for validation-only checks, polluting the audit trail.

**Evidence:**
- src/backend/apps/moderation/services/auto_moderation.py:254-324 — check() function; docstring at line 254 states Check ad compliance against ModerationCriteria without publishing and This function is for pre-submission validation where seller-safe errors are required.
- Each validation branch calls _fail_moderation(ad) (lines 290, 295, 300, 305, 310, 315, 320), which at line 218 calls set_moderation_failed(ad) then ad.transition_to(AdStatus.ON_MODERATION_FAILED) plus log_auto_fail() creation, and also creates an AnalyticsEvent at lines 224-228.
- The function is exported via src/backend/apps/moderation/services/__init__.py:3 but is never called anywhere in the codebase (confirmed via grep — no callers found).
- By contrast, auto_moderate() (line 90) is the documented path for actual status transitions and is correctly used in the bot handler.

**Recommendation:** Remove the side-effect calls (_fail_moderation()) from the validation function. It should perform pure validation and return (False, error_message) without mutating ad status or creating audit entries. If side-effects are needed, callers should use auto_moderate() instead.

---

### AD-005: Category rename propagation relies on no-op UPDATE trigger

| Field | Value |
|-------|-------|
| **ID** | AD-005 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | Category-tree zone, Search/FTS zone |
| **Classification** | mandatory |

**Description:** The AFTER-trigger on category name rename performs a self-assignment UPDATE (SET category_id = ads.category_id) that has no direct effect on its own. Propagation of the denormalized category_name field and the search_vector field works only as an accidental side-effect: the no-op UPDATE fires the BEFORE INSERT OR UPDATE search-vector trigger, which then re-fetches the category name from the (now-renamed) categories table and populates NEW.category_name and NEW.search_vector. This trigger-chaining is fragile and semantically incorrect.

**Evidence:**
- src/backend/apps/ads/migrations/0002_initial.py:33-41 — CATEGORY_PROPAGATE_FN_SQL:
  ```sql
  BEGIN
    UPDATE ads SET category_id = ads.category_id
    WHERE category_id = NEW.id;
    RETURN NEW;
  END;
```
  The SET category_id = ads.category_id is a self-assignment (no-op) — it does not update category_name.
- src/backend/apps/ads/migrations/0002_initial.py:11-23 — SEARCH_VECTOR_FN_SQL: the BEFORE INSERT OR UPDATE trigger that sets NEW.category_name and NEW.search_vector by SELECTing from categories WHERE id = NEW.category_id.
- src/backend/apps/ads/migrations/0002_initial.py:26-31 — SEARCH_VECTOR_TRIGGER_SQL: fires BEFORE INSERT OR UPDATE ON ads FOR EACH ROW.
- Test test_category_rename_propagates (src/backend/apps/ads/tests/test_search_triggers.py:96-103) passes, confirming propagation works today — but only because the no-op UPDATE activates the search-vector trigger.
- The categories_name_propagate function updates ALL ads matching category_id = NEW.id on every name change (line 37 WHERE clause), rewriting every affected row even if only the name text changed.

**Recommendation:** Rewrite the category rename trigger to directly update category_name on affected ads (rather than the no-op self-assignment). This removes the fragile trigger-chaining dependency and makes the intent obvious:
```sql
BEGIN
  UPDATE ads SET category_name = NEW.name
  WHERE category_id = NEW.id;
  RETURN NEW;
END;
```
The search-vector trigger will still fire on the category_name UPDATE and refresh search_vector as needed.

---

### AD-006: original_language hardcoded to bs in bot handler

| Field | Value |
|-------|-------|
| **ID** | AD-006 |
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | Bot FSM + DRAFT-persistence zone, Ad entity layer |
| **Classification** | advisory |

**Description:** The bot handler that persists ad content after translation sets original_language to a single hardcoded value regardless of the seller actual input language. The bot collects the seller original title/description, translates to all supported languages, then sets original_language to a fixed value. This means all bot-created ads are incorrectly attributed to one language, even if the seller wrote in a different language.

**Evidence:**
- src/telegram_bot/handlers/ad_create.py:473 — original_language passed as a literal string, not via LanguageLocale enum value or language detection.
- src/backend/apps/core/enums.py:159-178 — LanguageLocale StrEnum defines language values available for proper lookup.
- The LanguageLocale enum is imported and used elsewhere (e.g., FTS config lookup in fts_config property).
- src/backend/apps/ads/models.py:75-79 — original_language field documented as Original language code of the ad.

**Recommendation:** Detect the seller input language from the Telegram message from_user.language_code or content analysis, and set original_language to the matching LanguageLocale value. At minimum, use the LanguageLocale enum value instead of the raw string literal to maintain type safety per project rules.

---

### AD-007: Physical file deletion inside database transaction

| Field | Value |
|-------|-------|
| **ID** | AD-007 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | Purge/sweep zone, Photo-collection zone |
| **Classification** | advisory |

**Description:** All sweep and purge commands call physical file deletion (os.remove) inside transaction.atomic(). The file-deletion utility only catches FileNotFoundError; any other filesystem error (e.g., PermissionError, OSError) propagates and rolls back the transaction. However, files deleted before the failing call are already physically removed — a non-atomic outcome where the DB rows are restored but disk files are lost.

**Evidence:**
- src/telegram_bot/services/media.py:80-96 — delete_photo() catches only FileNotFoundError (line 94), letting other OSError subtypes propagate.
- Sweep/purge commands call delete_photo() inside transaction.atomic():
  - src/backend/apps/core/management/commands/delete_sweep.py:72-76
  - src/backend/apps/core/management/commands/purge_failed_ads.py:71-75
  - src/backend/apps/core/management/commands/purge_rejected_ads.py:73-77
  - src/backend/apps/core/management/commands/sweep_drafts.py:70-74
- The DB delete (queryset.delete()) always runs before the file-deletion loop in each command.
- Tests (src/backend/apps/core/tests/test_sweep_commands.py) verify CASCADE deletion of AdImage DB rows but do not exercise the file-deletion path (uses test storage keys like test-uuid.jpg that do not exist on disk).

**Recommendation:** Move physical file deletion outside the database transaction. After the transaction.atomic() block commits successfully, iterate over the collected storage keys and call delete_photo() with independent error handling (catch and log all OSError subtypes, queue for retry). This ensures DB consistency is not coupled to filesystem reliability.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH | 2 |
| MEDIUM | 2 |
| LOW | 2 |

## Mandatory Fixes

- **AD-001** (CRITICAL): Route all status changes through transition_to() to enforce the transition matrix; add guards to reject_ad to only allow ON_MODERATION to REJECTED.
- **AD-002** (HIGH): Add a purge command for DELETED status with 4-month retention from deleted_at, including an advisory lock and partial index.
- **AD-003** (HIGH): Remove ON_MODERATION_FAILED from the active-statuses list in the max-ads-per-user validation.
- **AD-004** (MEDIUM): Remove state-mutating calls from the pre-submission validation function; make it purely read-only.
- **AD-005** (MEDIUM): Rewrite the category rename trigger to directly update category_name instead of the no-op self-assignment UPDATE.

## Advisory Recommendations

- **AD-006** (LOW): Detect and set the seller actual language for original_language instead of hardcoding a fixed value.
- **AD-007** (LOW): Decouple physical file deletion from the database transaction to prevent inconsistent state on filesystem errors.

## Doc Updates Needed

- No DOC-UPDATE findings in this phase.
