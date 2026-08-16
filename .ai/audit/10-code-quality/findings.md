# Phase 10 Audit Findings — Code Quality

**Executor:** audit-executor
**Template:** .ai/audit/templates/audit-findings.md
**Status:** complete
**Validated:** no

> Static-analysis evidence captured against phase rules (typing, StrEnum, logging, SoC, SRP, Pydantic boundaries, English-only, migration discipline, DRY across processes).
> Linter: uv run ruff check src → **All checks passed**. Type-checker: uv run basedpyright src → **6 type errors in 6 files** (CRITICAL/HIGH severity).
> Test suite could not execute host-side (requires PostgreSQL on host db) — static review substituted per phase rule 3.

---

## Findings

### QLT-001: copy_service.py references non-existent latitude/longitude fields on Ad

| Field | Value |
|-------|-------|
| **ID** | QLT-001 |
| **Severity** | CRITICAL |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/backend/apps/ads/models.py, src/backend/apps/ads/services/copy_service.py, src/telegram_bot/handlers/ad_copy.py |
| **Classification** | mandatory |

**Description:** The copy_ad service (invoked by the bot /copy command) assigns source.latitude and source.longitude, but the Ad model in ds/models.py (549 lines) defines **no** latitude or longitude columns. Any call to /copy <ad_id> raises AttributeError at line 48–49 of copy_service.py.

**Evidence:**
- src/backend/apps/ads/services/copy_service.py:48 — latitude=source.latitude,
- src/backend/apps/ads/services/copy_service.py:49 — longitude=source.longitude,
- src/backend/apps/ads/models.py (full 549 lines, lines 1–549) — grep for latitude|longitude|address|location returns **zero** column definitions; only City FK exists at line 97.
- Service docstring (copy_service.py:4) claims to "Preserve… coordinates" — a documented promise the model/schema does not fulfill.
- src/telegram_bot/handlers/ad_copy.py:51 invokes copy_ad via sync_to_async, so the AttributeError surfaces at runtime in production, not in unit tests (tests require PG + never exercise /copy against a real ad with coordinates).

**Recommendation:** Remove the two lines from copy_ad (coordinates were never part of the documented schema) **or** add proper latitude/longitude/ddress model fields with a supporting migration. Remove "coordinates" from the docstring. Effort: trivial. Priority: mandatory — bot path is actively used.

---

### QLT-002: Type-checker reports 6 real errors across 6 files

| Field | Value |
|-------|-------|
| **ID** | QLT-002 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/backend/apps/ads/models.py, src/backend/apps/categories/catalog/builder.py, src/backend/apps/categories/services/lookup_resolution.py, src/backend/apps/lookups/models.py, src/telegram_bot/handlers/ad_copy.py |
| **Classification** | mandatory |

**Description:** asedpyright (strict) reports 6 errors. Per phase rule (a) "type-checker clean except framework-forced Any" — these are not framework-forced; they are genuine type-safety regressions that mask real bugs.

**Evidence (basedpyright output):**
1. src/backend/apps/ads/models.py:472 — join overload mismatch: os.path.join(media_root, self.image) where self.image: CharField (str expected by overload). Type narrowing fails because Django field __str__ is not recognized.
2. src/backend/apps/categories/catalog/builder.py:74 — with transaction.atomic(): used on a **callable**, not a context manager (with on callable is a basedpyright error; runtime TypeError).
3. src/backend/apps/categories/services/lookup_resolution.py:59 — list[SlugField] returned where list[LookupItem] declared (get_resolved_purposes return type mismatch).
4. src/backend/apps/categories/services/lookup_resolution.py:64 — same for get_resolved_feature_codes.
5. src/backend/apps/lookups/models.py:40 — __str__ returns self.code but code is CharField, type narrows to str — minor but flagged.
6. src/backend/apps/lookups/models.py:89 — __str__ returns self.slug, same narrows-to-str issue.
7. src/telegram_bot/handlers/ad_copy.py:35 — rgs = message.text.strip().split(maxsplit=1) then rgs[1] accessed without length check before 	ry/except ValueError; message.text is str | None → .strip() on None → AttributeError if message.text is None (bot receives non-text content).

**Recommendation:** Fix all 7 errors. Most are trivial (msg.text or "" guard; return type annotations; 	ransaction.atomic context usage). Effort: small. Priority: mandatory.

---

### QLT-003: Moderation API uses raw string literals for action types instead of StrEnum

| Field | Value |
|-------|-------|
| **ID** | QLT-003 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/backend/apps/moderation/views/api_bulk.py |
| **Classification** | mandatory |

**Description:** ulk_moderation_action compares ction == "approve", "reject", "flag" as raw string literals. The codebase already defines ModeratorActionType in core/enums.py (values eject, an_account, etc.) and AdStatus (AdStatus.PUBLISHED, etc.). Using raw strings here violates the phase's StrEnum rule and creates drift risk.

**Evidence:**
- src/backend/apps/moderation/views/api_bulk.py:46 — if action == "approve":
- src/backend/apps/moderation/views/api_bulk.py:48 — elif action == "reject":
- src/backend/apps/moderation/views/api_bulk.py:50 — elif action == "flag":
- src/backend/apps/core/enums.py:122 — ModeratorActionType enum exists but action values (pprove/eject/lag) do not map to it.

**Recommendation:** Define a BulkModerationAction(StrEnum) with APPROVE, REJECT, FLAG (or reuse/extend ModeratorActionType) and compare against enum members. Remove the bare-string else: raise ValueError fallback. Effort: trivial. Priority: mandatory.

---

### QLT-004: Moderation queue view uses raw "all" sentinel instead of StrEnum

| Field | Value |
|-------|-------|
| **ID** | QLT-004 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/backend/apps/moderation/views/queue.py, src/backend/apps/moderation/services/priority.py |
| **Classification** | advisory |

**Description:** moderation_queue reads priority = request.GET.get("priority", "all") and passes None if priority == "all" to PriorityService.get_queued_ads. The string "all" is a raw literal where an AdPriorityLevel enum exists. get_queued_ads accepts priority_filter: str | None, accepting arbitrary strings without validation.

**Evidence:**
- src/backend/apps/moderation/views/queue.py:25 — priority = request.GET.get("priority", "all")
- src/backend/apps/moderation/views/queue.py:29 — priority_filter=None if priority == "all" else priority,
- src/backend/apps/moderation/services/priority.py:46 — def get_queued_ads(self, priority_filter: str | None = None):

**Recommendation:** Introduce PriorityFilter(StrEnum) with members ALL, HIGH, MEDIUM, LOW. Validate the query param against it. Effort: small. Priority: advisory.

---

### QLT-005: contact.py — duplicated R2 render conditions (DRY violation across functions)

| Field | Value |
|-------|-------|
| **ID** | QLT-005 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/core/services/contact.py |
| **Classification** | advisory |

**Description:** can_contact_seller (lines 26–62) and get_seller_for_contact (lines 65–104) implement the **same** 5-condition R2 render check twice — ad.status == PUBLISHED, telegram_id not null, not deleted, not banned, consent not revoked. Per phase rule (i) "shared rules live in ONE place." This is the shared business-logic seam between web (can_contact_seller) and bot (get_seller_for_contact); duplication risks divergence.

**Evidence:**
- contact.py:43–60 — identical condition chain in can_contact_seller.
- contact.py:85–102 — identical condition chain in get_seller_for_contact.

**Recommendation:** Extract _seller_meets_contact_conditions(seller: User) -> bool and have both functions call it. Effort: trivial. Priority: advisory.

---

### QLT-006: ecord_trust_event is dead code outside tests (never called in production)

| Field | Value |
|-------|-------|
| **ID** | QLT-006 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/analytics/services/trust_analytics.py |
| **Classification** | advisory |

**Description:** ecord_trust_event (line 92) is implemented and exported from nalytics/services/__init__.py but is **only** referenced in 	ests/test_trust_analytics.py. No production handler or service calls it. Per phase rule 12 (small modules) and the Dead Code Policy, investigate purpose before deletion.

**Evidence:**
- src/backend/apps/analytics/services/trust_analytics.py:92 — def record_trust_event(user_id: int, event: AnalyticsEventType) -> None:
- src/backend/apps/analytics/services/__init__.py:10 — re-exported ecord_trust_event.
- grep for ecord_trust_event across src/ (excluding tests) → **zero** production call sites.

**Recommendation:** Investigate intended use (was it replaced by seller_stats.py / 	rust_calculator.py?). If truly unused, remove the function and its re-export. Effort: small. Priority: advisory.

---

### QLT-007: AnalyticsEventType enum member drift — mixed .value usage and raw comparisons

| Field | Value |
|-------|-------|
| **ID** | QLT-007 |
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/backend/apps/analytics/services/trust_analytics.py, src/backend/apps/analytics/models.py, src/backend/apps/ads/views/listings.py, src/backend/apps/search/views/search.py, src/backend/apps/moderation/services/auto_moderation.py, src/backend/apps/core/services/contact.py |
| **Classification** | advisory |

**Description:** AnalyticsEvent.event_type is a CharField with choices=[(e.value, e.value) for e in AnalyticsEventType], so the DB stores the string **value**. Production code is inconsistent in how it references the enum:
- Some write AnalyticsEventType.CONTACT_INITIATED (the enum member, auto-coerced to .value by Django) — e.g. contact.py:125, 	rust_calculator.py:146.
- Some explicitly write .value — e.g. 	rust_analytics.py:100 (event.event_type=event.value).
- uto_moderation.py:225 uses AnalyticsEventType.MODERATION_REJECTED (member directly).
- AnalyticsEventType.SELLER_VERIFIED and TRUST_LEVEL_UPDATED are only ever used in tests; no producer writes them in production.

This works at runtime (Django coerces), but the .value calls are redundant noise and the inconsistency signals unclear ownership of the enum-to-string contract.

**Evidence:**
- src/backend/apps/analytics/models.py:21 — choices=[(e.value, e.value) for e in AnalyticsEventType]
- src/backend/apps/analytics/services/trust_analytics.py:100 — event_type=event.value,
- src/backend/apps/core/services/contact.py:125 — event_type=AnalyticsEventType.CONTACT_INITIATED, (member, not .value)

**Recommendation:** Standardize on passing the enum member directly to event_type= everywhere (Django handles coercion); remove manual .value calls. Effort: trivial. Priority: advisory. Consider adding ecord_trust_event callers if SELLER_VERIFIED/TRUST_LEVEL_UPDATED events are intended to fire.

---

### QLT-008: Bot entry-point d_copy.py — message.text None-safety gap and inline import in handler body

| Field | Value |
|-------|-------|
| **ID** | QLT-008 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/telegram_bot/handlers/ad_copy.py |
| **Classification** | advisory |

**Description:** message.text.strip().split(...) on line 35 will raise AttributeError if message.text is None (e.g., bot receives a non-text message triggering the /copy filter). Additionally, copy_ad is imported inside the handler body (line 48) rather than at module top — minor performance hit per call and obscures dependencies.

**Evidence:**
- src/telegram_bot/handlers/ad_copy.py:35 — rgs = message.text.strip().split(maxsplit=1)
- src/telegram_bot/handlers/ad_copy.py:47–48 — inline rom apps.ads.services.copy_service import copy_ad

**Recommendation:** Guard with 	ext = message.text or "". Move copy_ad import to module level. Effort: trivial. Priority: advisory.

---

### QLT-009: d_create.py bot handler is 926 lines mixing FSM, ORM, validation, formatting, translation

| Field | Value |
|-------|-------|
| **ID** | QLT-009 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/telegram_bot/handlers/ad_create.py |
| **Classification** | advisory |

**Description:** 926-line single handler mixes ad-creation FSM orchestration, direct ORM calls (Ad.objects.create), multi-language validation, message formatting, and translation string selection. Per phase rule (d) "Bot handlers are thin adapters" and rule (e) "no giant handlers mixing ORM + validation + formatting." The bot process must django.setup() and share the ORM via the service layer, not embed ORM writes directly.

**Evidence:** src/telegram_bot/handlers/ad_create.py = 926 lines. wc -l confirms. No delegation to a shared AdDraftService for the core write/format logic.

**Recommendation:** Extract ad-creation business logic (validation → Ad row in DRAFT → formatted confirmation) into a shared service in pps/ads/services/ that both bot and web can call. Thin handler dispatches to it. Effort: medium. Priority: advisory.

---

### QLT-010: listings.py web view is 489 lines with embedded filtering logic

| Field | Value |
|-------|-------|
| **ID** | QLT-011 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/search/views/listings.py |
| **Classification** | advisory |

**Description:** 489-line view embeds ad filtering, pagination, sorting, and analytics-event recording inline rather than delegating to a query/filter service. Violates phase rule (d) "web views are thin adapters" and rule (e) "small, focused units."

**Evidence:** src/backend/apps/search/views/listings.py = 489 lines. Contains raw ORM .filter() chains and AnalyticsEvent.objects.create directly.

**Recommendation:** Extract filtering/sorting into a ListingQuery service class; keep view to param parsing + delegation + render. Effort: medium. Priority: advisory.

---

### QLT-011: nalytics/migrations/ has two initial=True migration files ( 001_initial.py +  002_initial.py)

| Field | Value |
|-------|-------|
| **ID** | QLT-012 |
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/backend/apps/analytics/migrations/ |
| **Classification** | advisory |

**Description:** Both  001_initial.py and  002_initial.py are marked initial = True in the Migration class. Django's migration autodetector and migration graph expect exactly **one** initial migration per app. Two initials can cause dependency-resolution warnings or graph ambiguity, especially when apps are partially migrated (e.g., seed-only subsets).

**Evidence:** grep -r "initial = True" src/backend/apps/analytics/migrations/ → 2 matches.

**Recommendation:** Rename  002_initial.py to a descriptive name (e.g.,  002_auto_...) and remove initial = True, OR merge both into a single  001_initial.py. Effort: trivial. Priority: advisory.

---

### QLT-012: AdImage.save() performs duplicate-detection query on every image save, mixing concerns into model

| Field | Value |
|-------|-------|
| **ID** | QLT-013 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/ads/models.py (AdImage.save, lines 461–493) |
| **Classification** | advisory |

**Description:** AdImage.save() overrides the default to compute SHA-256 via FileHashService, then runs a live AdImage.objects.filter(sha256=...) query to detect duplicates and silently eturns (skipping super().save()). This embeds hashing + dedup logic inside a model save() — mixing persistence with business policy. It also silently swallows duplicate creation (no signal, no log), making debugging hard. Per phase rule (d), business logic belongs in the service layer.

**Evidence:**
- src/backend/apps/ads/models.py:461–493 — AdImage.save() with rom apps.media.services.hash_service import FileHashService import inside body.
- src/backend/apps/ads/models.py:490–491 — if duplicate: return (silent dedup, no logging).

**Recommendation:** Move hashing + dedup decision into AdImageService.create_or_skip(image_path, ad, ...). Model save() stays dumb. Log dedup skips via logger. Effort: medium. Priority: advisory.

---

### QLT-013: seed/generators/base.py uses Any heavily (dict[str, Any], list[Any], untyped return)

| Field | Value |
|-------|-------|
| **ID** | QLT-014 |
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/backend/apps/seed/generators/base.py |
| **Classification** | advisory |

**Description:** Seed/dev-only generator module uses dict[str, Any], list[Any], and implicit Any returns extensively, eroding type safety. While the phase allows Any where a framework signature forces it, seed code is hand-written and should be typed. 24 of the 86 total Any matches in src/ live in this single file.

**Evidence:** grep -n "Any" src/backend/apps/seed/generators/base.py → 24 matches across class/return signatures.

**Recommendation:** Replace Any with concrete types (dict[str, object] or a SeedContext Pydantic model). Effort: small. Priority: advisory (seed-only, no prod impact).

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH | 1 |
| MEDIUM | 4 |
| LOW | 4 |

## Mandatory Fixes

1. **QLT-001 (CRITICAL):** Fix copy_ad referencing nonexistent latitude/longitude on Ad model — remove fields or add schema + migration. This breaks the bot /copy command at runtime.
2. **QLT-002 (HIGH):** Fix all 6+ basedpyright strict errors. These mask real bugs (	ransaction.atomic() on a callable, None.strip(), os.path.join type mismatch).

## Advisory Recommendations

1. **QLT-003:** Replace raw string action literals in pi_bulk.py with StrEnum.
2. **QLT-004:** Replace "all" raw-string sentinel in moderation queue with StrEnum.
3. **QLT-005:** Deduplicate R2 contact conditions in contact.py.
4. **QLT-007:** Standardize AnalyticsEventType usage — drop redundant .value, use enum members consistently.
5. **QLT-008:** Guard message.text None in bot handler; hoist inline imports.
6. **QLT-009:** Extract ad-creation FSM business logic from 926-line d_create.py into shared service.
7. **QLT-010:** Extract filtering from 489-line listings.py view into ListingQuery service.
8. **QLT-012:** Move SHA-256 hashing + dedup out of AdImage.save() into service layer.
9. **QLT-013:** Replace Any in seed generators with concrete/Pydantic types.

## Doc Updates Needed

1. **QLT-001:** copy_service.py docstring claims to "Preserve… coordinates" — either remove that claim or add the fields to the documented Ad schema in docs/02-database/db-schema.md.
2. **QLT-006:** Document the intended lifecycle of ecord_trust_event (or confirm deprecation) in docs/99-agent/architecture.md so future audits know whether it is dead code or future-proofing.
3. **QLT-011:** Clarify analytics migration strategy in migration docs — confirm only one initial=True per app is the rule.
---
