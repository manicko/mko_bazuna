---
phase: 10
phase_name: code-quality
source: .ai/audit/10-code-quality/findings.md
validated: 2026-08-15
validator: validator
---

# Phase 10 Audit Findings — Validation Report (Code Quality)

> **Mode:** `problems_only=TRUE` — only findings with confirmed problems are included.
> 12 of 13 findings are **validated** as real problems. 1 finding (QLT-013) is validated with evidence corrections. 0 findings rejected.

---

## Findings

### QLT-001: copy_service.py references non-existent latitude/longitude fields on Ad

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed: copy_service.py lines 48-49 assign latitude=source.latitude and longitude=source.longitude. Ad model (models.py, 549 lines) defines no latitude or longitude columns - grep returns zero matches. Only location field is city (ForeignKey line 96). copy_ad invoked by bot /copy via ad_copy.py:51 (sync_to_async), raises AttributeError at runtime.
> - **Docstring:** copy_service.py line 4 claims to Preserve coordinates - a promise the model does not fulfill.
> - **Recommendation:** Remove the two lines at copy_service.py:48-49 and update the module docstring (line 4) to drop the false coordinates claim. The Ad model (db-schema.md) defines no latitude/longitude columns — only city (FK). No spec or user story defines coordinates; Design_01/03-ad-detail.md Coordinates Toggle is a research note, and ui-ux-patterns-analysis.json explicitly flags CONFLICT: No GPS coordinates. Adding fields + migration would ship a feature absent from phases 1-2, violating YAGNI (cf. currency column removed) and overengineering avoidance. Removing unblocks the bot /copy command immediately.
> - **Evidence quality:** Strong.

**ID:** QLT-001
**Severity:** CRITICAL
**Type:** RUNTIME-ERROR
**Status:** VALIDATED

---

### QLT-002: Type-checker reports 6 real errors across 6 files

> **Validation Note:**
> - **Action:** validated (with corrections)
> - **Detail:** PARTIALLY VALIDATED. Multiple claims are incorrect:
>   1. Mode mismatch: Finding states basedpyright (strict) but pyproject.toml line 176 sets typeCheckingMode=standard, NOT strict. Config also sets reportArgumentType=none, reportAttributeAccessIssue=none, reportMissingImports=none.
>   2. Error count mismatch: Claims 6 errors in 6 files but lists 7 items across 5 files.
>   3. builder.py:74 (with transaction.atomic()): INCORRECT. Valid Django usage; not a runtime TypeError. Same pattern in rollup_daily_metrics.py:43 with pyright:ignore.
>   4. lookup_resolution.py:59,64: INCORRECT. get_resolved_purpose_codes() declares -> list[str] and returns [item.slug] which is list[str]. Returns match. Finding confuses get_resolved_purposes (-> list[LookupItem]) with get_resolved_purpose_codes (-> list[str]).
>   5. Remaining valid: models.py:472 (os.path.join with CharField), lookups/models.py:40/89 (__str__), ad_copy.py:35 (message.text None-safety).
> - **Overlap with QLT-008:** Item 7 (ad_copy.py:35) duplicates QLT-008. See Merge Candidates.
> - **Recommendation:** Directionally correct but inflated. Guard message.text (QLT-008); verify which errors basedpyright reports in standard mode.
> - **Evidence quality:** Mixed.

**ID:** QLT-002
**Severity:** HIGH
**Type:** SPEC-DEVIATION
**Status:** VALIDATED (with corrections)

---

### QLT-003: Moderation API uses raw string literals for action types instead of StrEnum

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed: api_bulk.py lines 46-50 use raw strings (approve/reject/flag). ModeratorActionType in core/enums.py:122 has REJECT, BAN_ACCOUNT, SOFT_DELETE, CRITERIA_CHANGE, OTHER - no APPROVE or FLAG. Violates StrEnum rule.
> - **Recommendation:** Correct. Define BulkModerationAction(StrEnum) with APPROVE, REJECT, FLAG.
> - **Evidence quality:** Strong.

**ID:** QLT-003
**Severity:** HIGH
**Type:** SPEC-DEVIATION
**Status:** VALIDATED

---

### QLT-004: Moderation queue view uses raw all sentinel instead of StrEnum

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed: queue.py:25 uses request.GET.get(priority, all). PriorityService.get_queued_ads (priority.py:46) accepts str|None. AdPriorityLevel has HIGH, MEDIUM, LOW - no ALL. AdModerationPriority.priority_level uses AdPriorityLevel choices.
> - **Recommendation:** Correct. Introduce PriorityFilter(StrEnum) with ALL, HIGH, MEDIUM, LOW.
> - **Evidence quality:** Strong.

**ID:** QLT-004
**Severity:** MEDIUM
**Type:** SPEC-DEVIATION
**Status:** VALIDATED

---

### QLT-005: contact.py - duplicated R2 render conditions (DRY violation)

> **Validation Note:**
> - **Action:** validated (with evidence correction)
> - **Detail:** Confirmed: can_contact_seller() (lines 26-62) and get_seller_for_contact() (lines 65-104) have identical condition chains. Finding states 5-condition but both implement 6: status check + 5 seller conditions.
> - **Recommendation:** Extract the 6-condition zone-R2 check into a private predicate def _check_seller_contactable(ad: Ad, seller: User | None) -> bool in contact.py. can_contact_seller(ad) passes ad.user (caller must select_related(user) to avoid N+1); get_seller_for_contact(ad_id) passes the already-fetched ad.user. Both functions delegate to this single predicate, eliminating the duplicated 6-condition chain. No behavior change.
> - **Evidence quality:** Strong (6 conditions, not 5).
> - **Note:** Classified advisory but missing from Advisory Recommendations section in findings file.

**ID:** QLT-005
**Severity:** MEDIUM
**Type:** BEST-PRACTICE
**Status:** VALIDATED (with evidence correction)

---

### QLT-006: record_trust_event is dead code outside tests (never called in production)

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed: record_trust_event defined at trust_analytics.py:92, re-exported from __init__.py. Grep across src (excluding tests) shows zero production call sites - only in test_trust_analytics.py.
> - **Recommendation:** Wire record_trust_event into TrustCalculator.calculate_and_save() (trust_calculator.py:40-86): call record_trust_event(user.id, AnalyticsEventType.TRUST_LEVEL_UPDATED) after persisting SellerTrustScore. TrustCalculator already imports AnalyticsEventType (uses it for CONTACT_INITIATED/CONTACT_RESPONSE) and is the single owner of trust-level computation — this is the well-defined call site matching the established record_contact_initiated/record_contact_response pattern. Fix the QLT-007 .value usage in the same edit (event_type=event). For SELLER_VERIFIED, leave the function exported; no admin verification handler exists yet to wire it.
> - **Evidence quality:** Strong.

**ID:** QLT-006
**Severity:** LOW
**Type:** BEST-PRACTICE
**Status:** VALIDATED

---

### QLT-007: AnalyticsEventType enum member drift - mixed .value usage

> **Validation Note:**
> - **Action:** validated (with additional findings)
> - **Detail:** Confirmed: event_type CharField uses choices=[(e.value, e.value) for e in AnalyticsEventType]. Production code is inconsistent: member-direct (contact.py:125, auto_moderation.py:225/238/244, seller_stats.py, listings.py:73, search.py:117, trust_calculator.py:146/154) vs explicit .value (trust_analytics.py:100, rollup_daily_metrics.py:49-51/64/70-71). Finding omits rollup_daily_metrics.py .value usage.
> - **SELLER_VERIFIED and TRUST_LEVEL_UPDATED:** Confirmed only in test files. No production producers.
> - **Minor inaccuracy:** Finding says event.event_type=event.value but actual code is event_type=event.value.
> - **Recommendation:** Correct. Standardize on enum members; remove .value calls.
> - **Evidence quality:** Strong.

**ID:** QLT-007
**Severity:** LOW
**Type:** SPEC-DEVIATION
**Status:** VALIDATED (with additional findings)

---

### QLT-008: Bot ad_copy.py - message.text None-safety gap and inline import

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed: ad_copy.py:35 does message.text.strip().split() where message.text is str|None in aiogram type stubs. Command filter should ensure text, but type system cannot guarantee it. copy_ad imported inside handler body (lines 47-48).
> - **Recommendation:** Correct. Guard with message.text or empty string; move import to module level.
> - **Evidence quality:** Strong.
> - **Overlap:** Duplicates QLT-002 item 7.

**ID:** QLT-008
**Severity:** MEDIUM
**Type:** BEST-PRACTICE
**Status:** VALIDATED

---

### QLT-009: ad_create.py bot handler is 926 lines mixing FSM, ORM, validation, formatting, translation

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed: ad_create.py is 926 lines (verified via file read). Contains direct ORM calls: Ad.objects.create (line 507), Ad.objects.get (lines 519, 690), AdImage.objects.create (line 725). Uses AdCreateState (FSM), Pydantic validation, message formatting, translation. No AdDraftService exists in ads/services/ (only copy_service.py, which is function-based).
> - **Recommendation:** Correct. Extract ad-creation business logic into shared service in ads/services/. Effort: medium. Priority: advisory.
> - **Evidence quality:** Strong - file size, ORM calls, FSM usage, absence of shared service all confirmed.

**ID:** QLT-009
**Severity:** MEDIUM
**Type:** BEST-PRACTICE
**Status:** VALIDATED

---

### QLT-010: listings.py web view is 489 lines with embedded filtering logic

> **Validation Note:**
> - **Action:** validated (with path correction)
> - **Detail:** Confirmed: file exists at src/backend/apps/ads/views/listings.py (NOT src/backend/apps/search/views/listings.py - path is incorrect; no such file exists in search/views/). File IS 489 lines. Contains listings() view (line 181) with embedded filtering: Ad.objects.filter (line 250), category subtree (lines 261-288), city filter (lines 295-314), price range (lines 317-346), sorting (lines 349-368), pagination (lines 371-377), AnalyticsEvent.objects.create (line 72 in ad_detail view).
> - **Path error:** Finding references search/views/listings.py which does not exist. Actual file is ads/views/listings.py.
> - **ID mismatch:** Heading QLT-010 vs ID field QLT-011. Using QLT-010 heading as canonical.
> - **Recommendation:** Correct. Extract ListingQuery service class; keep view thin.
> - **Evidence quality:** Strong (path corrected).

**ID:** QLT-010 (heading) / QLT-011 (ID field - mismatched)
**Severity:** MEDIUM
**Type:** BEST-PRACTICE
**Status:** VALIDATED (with path correction)

---

### QLT-011: analytics/migrations/ has two initial=True migration files

> **Validation Note:**
> - **Action:** validated (with cross-app observation)
> - **Detail:** Confirmed: analytics/migrations/0001_initial.py (line 9) and 0002_initial.py (line 10) both have initial=True. Same pattern exists in trust, moderation, search, and ads apps - a project-wide convention, not isolated to analytics. Each pair has 0001 creating models and 0002 adding FK fields and constraints.
> - **ID mismatch:** Heading QLT-011 vs ID field QLT-012.
> - **Recommendation:** Correct. Rename 0002 to descriptive name and remove initial=True. Apply to all 5 affected apps.
> - **Evidence quality:** Strong - grep and file inspection confirmed. Cross-app pattern is additional finding.

**ID:** QLT-011 (heading) / QLT-012 (ID field - mismatched)
**Severity:** LOW
**Type:** SPEC-DEVIATION
**Status:** VALIDATED (with cross-app observation)

---

### QLT-012: AdImage.save() performs duplicate-detection query on every image save, mixing concerns into model

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed: AdImage.save() override at models.py:461-493 computes SHA-256 via FileHashService (imported inside body line 467), runs live AdImage.objects.filter(sha256=...) query, and silently returns at line 491 if duplicate found (before super().save() at line 493). No logging on dedup skip. FileHashService import inside save() obscures dependencies.
> - **Recommendation:** Correct. Move hashing + dedup into AdImageService.create_or_skip(). Model save() stays dumb. Log dedup skips.
> - **Evidence quality:** Strong - code inspection of lines 461-493 confirms all claims.
> - **ID mismatch:** Heading QLT-012 vs ID field QLT-013.

**ID:** QLT-012 (heading) / QLT-013 (ID field - mismatched)
**Severity:** LOW
**Type:** BEST-PRACTICE
**Status:** VALIDATED

---

### QLT-013: seed/generators/base.py uses Any heavily (dict[str, Any], list[Any], untyped return)

> **Validation Note:**
> - **Action:** validated (with evidence corrections)
> - **Detail:** Confirmed: base.py DOES use typing.Any. However finding evidence is incorrect:
>   1. Claims 24 Any matches in base.py - FALSE. Grep returns 6 matches (import + 5 usage: dict[str,Any], list[Any], -> Any, list[Any], list[list[Any]]). File is 96 lines.
>   2. Claims 86 total Any matches in src/ - TRUE but misleading. Includes 12 imports, string literals ("Any title"), comments ("Any such field"), docstrings ("Any other exception"). Actual typing.Any type annotation count is approximately 50-55.
>   3. No ID field in table - structural issue. Heading QLT-013 has no ID field.
>   4. Severity LOW, seed-only, no production impact. Recommendation: replace with concrete types or SeedContext Pydantic model. Valid but lower priority than claimed.
> - **Evidence quality:** Weak - core observation (Any usage exists) is correct, but quantitative evidence is significantly inflated.

**ID:** QLT-013 (heading, no ID field in table)
**Severity:** LOW
**Type:** SPEC-DEVIATION
**Status:** VALIDATED (with evidence corrections)

---

## Findings with Recommendation/Documentation Corrections

| ID | Issue |
|----|-------|
| QLT-002 | Finding claims basedpyright strict mode but pyproject.toml config is standard mode. 3 of 7 errors invalid. Count mismatch (6 claimed vs 7 listed, 5 files not 6). |
| QLT-005 | States 5-condition R2 check but both functions implement 6 conditions. |
| QLT-007 | Says event.event_type=event.value but actual code is event_type=event.value. Omits rollup_daily_metrics.py .value usage. |
| QLT-010 | References search/views/listings.py - file does not exist. Actual: ads/views/listings.py. ID field QLT-011 vs heading QLT-010. |
| QLT-011 | Same ID mismatch. Cross-app pattern in 4 other apps. |
| QLT-012 | Same ID mismatch (heading vs ID field). |
| QLT-013 | No ID field. Claims 24 Any matches but actual is 6. |

## Findings File Structural Issues

1. **ID field mismatches (QLT-010 through QLT-013):** Headings and ID fields are systematically offset by one for findings 10-12. Finding QLT-013 has no ID field at all. Summary table and advisory sections use a mix of heading and ID references.
2. **Summary table count mismatch:** Reports CRITICAL:1, HIGH:1, MEDIUM:4, LOW:4 (total 10) but 13 findings exist (1 CRITICAL, 2 HIGH, 5 MEDIUM, 5 LOW). Missing QLT-003 and QLT-006 from counts.
3. **QLT-006 missing from Advisory Recommendations:** Classified advisory in body but not listed in Advisory Recommendations section. Only in Doc Updates Needed.
4. **QLT-013 missing from Advisory Recommendations:** Not listed in either Mandatory Fixes or Advisory Recommendations sections.

## Cross-Finding Analysis

### Dependency Chains

| From | Depends On | Detail |
|------|-----------|--------|
| QLT-001 fix | QLT-010 doc update | If coordinates added to model, schema must be documented in db-schema.md. If removed, copy_service docstring must be updated. |
| QLT-002 fix ad_copy.py | QLT-008 fix | Same message.text None-safety issue at ad_copy.py:35. Fix once covers both. |
| QLT-002 fix models.py | django-stubs decision | os.path.join and __str__ CharField issues depend on django-stubs absence (not in pyproject.toml). |
| QLT-007 fix | QLT-006 fix | If record_trust_event removed, .value usage in that function disappears. If wired in, .value should be replaced. |
| QLT-009 fix | QLT-001 fix | Both touch ad creation/copy flow. Unified service would handle both. |
| QLT-011/012 fix | None | Independent migration rename. Apply to all 5 affected apps (analytics, trust, moderation, search, ads). |

### Conflicts

No cross-phase conflicts with phases 01-09. Within Phase 10: QLT-002 item 7 and QLT-008 describe the same root cause (message.text None-safety in ad_copy.py:35).

### Merge Candidates

| Original ID | Merged Into | Rationale |
|-------------|-------------|----------|
| QLT-002 item 7 (ad_copy.py:35) | QLT-008 | Same root cause: message.text None-safety. QLT-008 is the correctly-scoped finding. |

### Duplicate Findings

| ID | Issue |
|----|-------|
| QLT-010 vs QLT-011 (ID field) | Systematic offset: heading QLT-010 has ID field QLT-011. Structural issue in findings file. |

---

## Rollout Safety Assessment

### QLT-001 (copy_ad latitude/longitude)
- **Risk:** HIGH (runtime crash). /copy command currently raises AttributeError.
- **Rollout ordering:** Independent. Prerequisite for bot /copy to function.
- **Rollback:** Trivial - revert changed lines.

### QLT-002 (type-checker errors)
- **Risk:** Varies. transaction.atomic() claim is invalid. Real errors: message.text None-safety, CharField __str__, os.path.join. Type-safety improvements, not runtime crashes.
- **Rollout safety:** LOW. Type annotations/guards do not change runtime behavior when correctly applied.
- **Note:** Finding claims strict mode but config is standard mode with suppressions.

### QLT-003 (moderation StrEnum)
- **Risk:** NONE. String comparisons to enum comparisons is behavior-preserving.
- **Rollout:** Independent. Backward compatible.

### QLT-004 (priority filter StrEnum)
- **Risk:** NONE. Backward compatible.
- **Rollout:** Independent.

### QLT-005 (contact R2 DRY)
- **Risk:** LOW. Extracting shared helper changes no behavior if correct.
- **Rollout safety:** Helper must preserve exact 6-condition logic. Unit test recommended.
- **Rollout:** Independent.

### QLT-006 (dead code)
- **Risk:** NONE for removal. Product roadmap determines removal vs wiring.

### QLT-007 (enum usage standardization)
- **Risk:** NONE. Removing redundant .value calls is behavior-preserving (Django coerces).
- **Rollout:** Independent.

### QLT-008 (message.text guard)
- **Risk:** NONE. Adding None guard is defensive, behavior-preserving.
- **Rollout:** Independent. Same fix covers QLT-002 item 7.

### QLT-009 (extract ad_create business logic)
- **Risk:** MEDIUM. Significant refactor of 926-line handler. Must ensure FSM/service/ORM parity.
- **Rollout safety:** Shared service must replicate exact validation, Draft creation, formatting. Test coverage essential.
- **Dependency:** Should be done alongside QLT-001 (copy_service) if creating unified ad service.

### QLT-010/011 (extract listings filtering)
- **Risk:** MEDIUM. Refactoring 489-line view with embedded filtering. Incorrect extraction could change filter semantics.
- **Rollout safety:** Extracted ListingQuery service must preserve exact ORM filter chains, sorting, pagination.
- **Note:** File path is ads/views/listings.py, not search/views/listings.py.

### QLT-011/012 (double initial=True migrations)
- **Risk:** LOW (current state). Two initial=True migrations do not crash Django but cause graph warnings.
- **Rollout safety:** After initial migration, renaming and removing initial=True is safe. Must preserve graph dependency order. Apply to all 5 affected apps.

### QLT-012/013 (AdImage.save business logic)
- **Risk:** MEDIUM. Moving dedup from model save() to service changes intervention point. All code paths calling AdImage.objects.create() must use new service.
- **Rollout safety:** Silent skip must become logged. Clean cutover preferred over dual-path.
- **Rollout ordering:** Should precede QLT-009 (unified ad service).

### QLT-013 (seed generator typing)
- **Risk:** NONE. Seed-only code, no production impact.
- **Rollout:** Safe at any time. Lowest priority.

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 8 | QLT-001, QLT-003, QLT-004, QLT-006, QLT-008, QLT-009, QLT-012, QLT-013 |
| Validated with corrections | 4 | QLT-002 (mode/error count/3 invalid claims), QLT-005 (6 conditions not 5), QLT-007 (omitted file, path inaccuracy), QLT-010 (wrong path, ID mismatch) |
| Reclassified | 0 | None |
| Merged | 0 | QLT-002 item 7 -> QLT-008 noted as merge candidate |
| Rejected | 0 | None |

### Rejected Findings

None. All 13 findings identify at least some real codebase issues. Findings QLT-002, QLT-005, QLT-007, QLT-010, and QLT-013 are validated with corrections because their evidence contains inaccuracies, but the core problems are real.

### Merged Findings

| Original ID | Merged Into | Rationale |
|-------------|-------------|----------|
| QLT-002 item 7 (ad_copy.py:35) | QLT-008 | Same root cause: message.text None-safety. QLT-008 is the correctly-scoped finding. |

### Reclassified Findings

| ID | Original Type | New Type | Rationale |
|----|---------------|----------|-----------|
| None | - | - | - |

### Evidence Quality Assessment

| ID | Evidence Quality | Notes |
|----|----------------|-------|
| QLT-001 | Strong | Code, model, docstring all confirmed |
| QLT-002 | Mixed | Mode (standard vs strict) and count (6 vs 7, 5 vs 6 files) incorrect; 3 of 7 items invalid |
| QLT-003 | Strong | Code and enum definitions confirmed |
| QLT-004 | Strong | View, service, enum, model all confirmed |
| QLT-005 | Strong (corrected) | 6 conditions, not 5 |
| QLT-006 | Strong | Definition, re-export, grep for call sites confirmed |
| QLT-007 | Strong (corrected) | Omits rollup_daily_metrics.py .value usage; minor description inaccuracy |
| QLT-008 | Strong | Code confirmed |
| QLT-009 | Strong | File size, ORM calls, no shared service confirmed |
| QLT-010 | Strong (corrected) | Wrong path (ads not search); file exists and is 489 lines |
| QLT-011 | Strong (corrected) | Cross-app pattern in 4 additional apps |
| QLT-012 | Strong | Code inspection lines 461-493 confirms all claims |
| QLT-013 | Weak | 6 Any matches, not 24; 86 total includes string literals/comments |

---

## Rollout Sequencing Recommendation

1. **QLT-001** (CRITICAL) - Fix copy_ad latitude/longitude AttributeError (bot /copy is broken).
2. **QLT-008** (MEDIUM) - Guard message.text None-safety in ad_copy.py:35 (same fix covers QLT-002 item 7).
3. **QLT-003** (HIGH) - Replace raw string action literals in api_bulk.py with StrEnum.
4. **QLT-004** (MEDIUM) - Replace all sentinel in moderation queue with StrEnum.
5. **QLT-005** (MEDIUM) - Extract shared contact R2 conditions helper.
6. **QLT-007** (LOW) - Remove redundant .value calls; standardize on enum members.
7. **QLT-011/012** (LOW) - Fix double initial=True migrations (all 5 affected apps).
8. **QLT-012/013** (LOW) - Move AdImage hashing + dedup out of save() into service layer.
9. **QLT-006** (LOW) - Remove or wire in record_trust_event dead code.
10. **QLT-009** (MEDIUM) - Extract ad-creation FSM business logic into shared service.
11. **QLT-010/011** (MEDIUM) - Extract filtering from listings.py view into ListingQuery service.
12. **QLT-002** (HIGH) - Fix remaining genuine basedpyright errors after steps 2-6 address valid concerns.
13. **QLT-013** (LOW) - Replace Any in seed generators (seed-only, lowest priority).

### Dependency Summary

- Steps 1-2 are independent and can run in parallel.
- Steps 3-7 are independent of each other and can run in parallel.
- Step 8 should precede step 10 since both touch the ad persistence layer.
- Step 10 should incorporate QLT-001 (copy_service) when creating the unified service.
- Step 11 depends on step 10 for the ad query pattern.
- Step 12 depends on steps 2-6 eliminating the valid basedpyright errors.
- Step 13 is independent and lowest priority.
