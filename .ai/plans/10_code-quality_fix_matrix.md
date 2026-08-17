# Phase 10 Fix Matrix — Code Quality

**Audit phase:** 10-code-quality
**Validated findings file:** `.ai/audit/99-validation/10-code-quality-validated-findings.md`
**Total findings:** 13 (QLT-001 … QLT-013) — all validated, 0 rejected, 0 merged-deleted
**Workflow:** orchestrator-driven, parallel researcher/implementor/doc-specialist waves

> Severity grouping (corrected counts; audit summary table was missing QLT-003, QLT-006):
> CRITICAL: 1 · HIGH: 2 · MEDIUM: 5 · LOW: 5

---

## Legend

**Classification**
- **Simple / Low-risk** — trivial change, single clear fix, no architecture impact, no alternatives.
- **Complex / High-risk** — multi-file, architectural impact, data migration, infra change, or behavioral risk.
- **Multiple viable routes** — more than one correct solution exists (→ full research required).

**ID handling note:** Headings QLT-010/011/012/013 were offset vs their `ID` field in the findings file; QLT-013 has no `ID` field at all. The canonical ID for each row below is the heading ID (QLT-001…QLT-013).

---

## Fix Matrix

| # | Finding | Severity | Type | Classification | Complexity / Risk driver | Chosen solution (selected route) | Prod files | Test files | Docs files | Status |
|---|---------|----------|------|----------------|--------------------------|----------------------------------|------------|------------|------------|--------|
| 1 | QLT-001 | CRITICAL | RUNTIME-ERROR | Simple / Low-risk | None — bot `/copy` crashes at runtime (AttributeError) | Remove `latitude`/`longitude` assigns in `copy_service.py:51-52`; update module docstring line 4 to drop the false "preserve coordinates" claim. Do NOT add coordinate columns (YAGNI; no spec/story; `db-schema.md` defines none; `Design_01/03-ad-detail.md` Coordinates Toggle is Jiji research, `ui-ux-patterns-analysis.json` flags CONFLICT: No GPS) | `ads/services/copy_service.py` | existing copy tests | `docs/01-spec/technical-specification.md` §copy (none — no coords exist to document) | done (`100716f`) |
| 2 | QLT-002 | HIGH | SPEC-DEVIATION | Multiple viable routes | Depends on django-stubs presence (not installed); 3/7 audit claims invalid but 5 real errors remain under standard mode | Route B: targeted `str()` casts + `# pyright: ignore` on `transaction.atomic()` (matches the 26 existing ignores + 5 `str()` casts precedent). Route A (install django-stubs) rejected: HIGH risk — would invalidate 26 ignores → `warn_unused_ignores`, surface hundreds of errors, contradict codebase pattern. Real errors: `models.py:472` `os.path.join`+`CharField`, `lookups/models.py:40/89` `__str__`, `ad_copy.py:35` (covered by QLT-008), `builder.py:74` & `lookup_resolution.py:59,64` (re-examined: 8 actual errors in standard mode) | `ads/models.py`, `core/services/lookups/models.py`, `ads/models.py:472`, bot ad_copy | n/a | none | pending |
| 3 | QLT-003 | HIGH | SPEC-DEVIATION | Simple / Low-risk | None — string literals vs enum | Add `BulkModerationAction(StrEnum)` {APPROVE, REJECT, FLAG}; replace raw strings at `api_bulk.py:50-54`; add 400 validation for unknown actions | `core/enums.py`, `moderation/views/api_bulk.py` | `moderation/tests/test_priority_service.py` | `docs/02-database/db-enums.md` | done (`e52869f`) |
| 4 | QLT-004 | MEDIUM | SPEC-DEVIATION | Multiple viable routes | `all` is a UI/query sentinel, cannot extend `AdPriorityLevel` (DB column) | Add `PriorityFilter(StrEnum)` {ALL, HIGH, MEDIUM, LOW}; `ALL`→`None` at query layer. Rejected: extend `AdPriorityLevel` (corrupts stored column) | `core/enums.py`, `moderation/views/queue.py`, `moderation/services/priority.py` | `moderation/tests/test_priority_service.py` | `docs/02-database/db-enums.md` | done (`9770728`) |
| 5 | QLT-005 | MEDIUM | BEST-PRACTICE | Simple / Low-risk | None (callers already select_related user) | Extract `_check_seller_contactable(ad, seller) -> bool`; both functions delegate — behavior-preserving | `core/services/contact.py` | `core/tests/test_contact.py` | none (minor refactor per doc-maintenance-rules.md) | done (`a65bc1a`) |
| 6 | QLT-006 | LOW | BEST-PRACTICE | Multiple viable routes | Dead code vs wiring decision | Wire `record_trust_event(user.id, AnalyticsEventType.TRUST_LEVEL_UPDATED)` into `TrustCalculator.calculate_and_save()` after persisting `SellerTrustScore`; fix `.value` in same edit. SELLER_VERIFIED left exported. Rejected: remove (TRUST_LEVEL_UPDATED is a documented enum; trust-signals-plan.md includes TrustAnalytics) | `trust/services/trust_calculator.py`, `analytics/services/trust_analytics.py` | `trust/tests/test_trust_calculator.py`, `analytics/tests/test_trust_analytics.py` | none (TRUST_LEVEL_UPDATED already in db-enums.md) | done (`82a11c3`) |
| 7 | QLT-007 | LOW | SPEC-DEVIATION | Simple / Low-risk (mechanical multi-file) | None (StrEnum `== str`) | Standardize on enum members; remove `.value` (9 prod edits: `trust_analytics.py:100,103,106`, `rollup_daily_metrics.py:49,50,51,64,70,71`; 3 test edits) | `analytics/services/trust_analytics.py`, `analytics/management/commands/rollup_daily_metrics.py` | `analytics/tests/test_trust_analytics.py`, `test_rollup_daily_metrics.py` | none (refactoring per doc-maintenance-rules.md) | done (`26dcc7c`) |
| 8 | QLT-008 | MEDIUM | BEST-PRACTICE | Simple / Low-risk | None | Guard `message.text or ""`; move inline imports `copy_service.copy_ad` to module top | `telegram_bot/handlers/.../ad_copy.py` | existing bot copy tests | none | done (`2fc9d75`) |
| 9 | QLT-009 | MEDIUM | BEST-PRACTICE | Complex / High-risk | 926-line handler, FSM+ORM+validation+formatting+translation, behavioral parity, dependency on QLT-001 | Route A: function-based `ad_creation.py` service module in `ads/services/` matching existing `copy_service.py` pattern (no `AdDraftService` class exists). Rejected: AdDraftService class (no precedent) | `ads/services/ad_creation.py` (new), `telegram_bot/.../ad_create.py` (trim) | new service tests + existing bot tests | none | pending |
| 10 | QLT-010 | MEDIUM | BEST-PRACTICE | Complex / High-risk | 489-line view, 6 filter stages + sorting + pagination, behavioral parity | Route A: `ListingQuery` service class (cohesive filter state). Rejected: queryset method (too many params) | `ads/services/listings.py` (new), `ads/views/listings.py` (trim) | view tests | none | pending |
| 11 | QLT-011 | LOW | SPEC-DEVIATION | Complex (multi-app migration) | 5 apps each have 0001_initial + 0002_initial (both initial=True); risk of renaming applied migrations | Route A: rename `0002` to descriptive name + remove `initial=True` for all 5 apps (analytics, trust, moderation, search, ads); use `migrate --fake` per migration-workflow.md. Rejected: merge migrations (lose dev-history; heavier) | `analytics/migrations/`, `trust/migrations/`, `moderation/migrations/`, `search/migrations/`, `ads/migrations/` | none (migration-only) | `docs/ops/migration-workflow.md` note | done |
| 12 | QLT-012 | LOW | BEST-PRACTICE | Complex (behavioral, blast radius) | Dedup in `AdImage.save()`; 3 production call sites; silent skip; behavior-change for copy_service (seed bulk_create bypasses save()) | Route A: `AdImageService.create_or_skip()`; model save() stays dumb; log dedup skips. Dedup scoped to ad-level for copy path. Rejected: signal (implicit), manager method (less explicit) | `ads/services/images.py` (new/existing), `ads/models.py`, callers (`ad_create.py:745`, `copy_service.py:63`, seed `images.py:164`) | new service tests | none | done |
| 13 | QLT-013 | LOW | SPEC-DEVIATION | Complex (boundary + generics) | 6 real `Any` annotations; config dict boundary + 2 generic utility methods; touches base.py + seed_service.py (4 places) + 4 subclasses | Route A: `SeedContext(BaseModel)` Pydantic v2 at config boundary (matches `telegram_bot/schemas/message_payloads.py` precedent) + `TypeVar` for `_random_choice`/`_chunked`. Rejected: TypedDict (no runtime validation) | `seed/config/seed_context.py` (new), `seed/generators/base.py`, `seed/services/seed_service.py`, `seed/generators/{ads,images,analytics,users}.py` | `seed/tests/test_seed.py` (add SeedContext validation tests) | none (seed-internal; no public schema) | pending |

---

## Rollout sequencing (per audit §Rollout Sequencing Recommendation)

Independently parallelizable waves:

- **Wave 1 (parallel, independent):** QLT-001 → QLT-008 → QLT-003 → QLT-005 → QLT-007 — **done**
- **Wave 2 (independent of each other):** QLT-004, QLT-006 (includes QLT-007 `.value` fix in trust_analytics.py), QLT-013 — QLT-004/006/007 **done**; QLT-013 pending
- **Wave 3 (migration):** QLT-011 (5 apps) — **done**
- **Wave 4 (behavioral, precedes ad-service extraction):** QLT-012 (AdImageService — must precede QLT-009 per audit §dependency) — **done**
- **Wave 5 (service extraction):** QLT-009 (ad creation service, incorporates QLT-001 copy fix)
- **Wave 6 (view extraction):** QLT-010 (ListingQuery)
- **Wave 7 (final cleanup):** QLT-002 (residual basedpyright errors after QLT-008/012 address their items)

> Dependency notes: QLT-009 should incorporate the QLT-001 copy_service fix when creating the unified ad service. QLT-002's `ad_copy.py:35` item is resolved by QLT-008. QLT-006 co-fixes the `trust_analytics.py` `.value` usage (QLT-007). QLT-012 precedes QLT-009 (both touch ad image persistence).

---

## Tests required (consolidated)

| Finding | Test scope | Existing tests to extend/re-run |
|---------|-----------|--------------------------------|
| QLT-001 | copy_ad drops nonexistent attrs; no AttributeError; preserves city | copy service tests |
| QLT-002 | type checks pass under standard mode | type-check gate only |
| QLT-003 | bulk approve/reject/flag; unknown→400 | `test_priority_service.py::TestBulkModerationActionView` |
| QLT-004 | all/high/medium/low filter + invalid→default | `test_priority_service.py` |
| QLT-005 | `_check_seller_contactable` 6 conds x pass/fail; get_seller_for_contact returns tuple | `core/tests/test_contact.py` |
| QLT-006 | `calculate_and_save` records TRUST_LEVEL_UPDATED x1 per save | `test_trust_calculator.py`, `test_trust_analytics.py` |
| QLT-007 | no regressions (member == value) | `test_trust_analytics.py`, `test_rollup_daily_metrics.py`, `test_seller_stats`, `test_trust_calculator`, `test_contact` |
| QLT-008 | message.text None guarded; import at module level | bot copy tests |
| QLT-009 | create-from-dialog parity | new service tests + existing bot tests |
| QLT-010 | filter/sort/pagination parity | view tests |
| QLT-011 | migration graph applies clean | `uv run python manage.py makemigrations --check` / migrate dry-run |
| QLT-012 | dedup skips logged; create_or_skip returns saved/skipped | new AdImageService tests |
| QLT-013 | SeedContext validates JSON; defaults preserved; empty-config fallback | `seed/tests/test_seed.py` |

---

## Docs required (consolidated)

| Finding | Docs files |
|---------|-----------|
| QLT-003 | `docs/02-database/db-enums.md` — add `BulkModerationAction` |
| QLT-004 | `docs/02-database/db-enums.md` — add `PriorityFilter` (note ALL is sentinel, not DB column) |
| QLT-001, QLT-002, QLT-005, QLT-006, QLT-007, QLT-008, QLT-009, QLT-010, QLT-011, QLT-012, QLT-013 | see per-row "Docs" — most refactoring/type-only need none; QLT-011 notes `docs/ops/migration-workflow.md` |

---

## Implementation status tracker

| # | Finding | Status |
|---|---------|--------|
| 1 | QLT-001 | done | `100716f` |
| 2 | QLT-002 | pending | |
| 3 | QLT-003 | done | `e52869f` |
| 4 | QLT-004 | done | `9770728` |
| 5 | QLT-005 | done | `a65bc1a` |
| 6 | QLT-006 | done | `82a11c3` |
| 7 | QLT-007 | done | `26dcc7c` |
| 8 | QLT-008 | done | `2fc9d75` |
| 9 | QLT-009 | pending | |
| 10 | QLT-010 | pending | |
| 11 | QLT-011 | done | |
| 12 | QLT-012 | done | |
| 13 | QLT-013 | pending | |
