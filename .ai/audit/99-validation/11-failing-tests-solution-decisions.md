# Failing Tests — Consolidated Solution Decisions

**Date:** 2026-09-17  
**Status:** Decisions finalized (Tech Lead sign-off)  
**Process phases completed:** Auditor (read-only) → 2 Researchers (read-only) → Validator (read-only) → **this document**  
**Next step:** Implementation by Implementor

---

## 1. Problem Summary

16 failing tests across 5 independent root causes. All are confirmed by source verification.
The architectural principle: **test fixtures and seed generators must respect the same
business invariants the application enforces in production.**

| Cat | Tests | Root Cause | Architectural Severity |
|-----|-------|------------|----------------------|
| **D** | 1 | `SavedSearch.query` help_text drift between model and migration | Process / discipline |
| **C** | 3 | `api_bulk.py` passes raw `exc.errors()` (contains `bytes`) to `JsonResponse` | API boundary / security |
| **B** | 2 | `telegram_tags.py` calls `gettext()` at module import → frozen translation | i18n correctness |
| **E** | 8 | Seed generator creates multiple DRAFTs per user → `uq_ads_single_draft_per_user` violation | Data integrity / architecture |
| **A** | 2 | `seller_ads` test fixture creates 2 DRAFTs per seller → same constraint violation | Test/fixture correctness |

---

## 2. Per-Category Decisions

### D — Migration help_text drift (1 test: `test_makemigrations_check`)

**Root cause (verified):** `src/backend/apps/search/migrations/0001_initial.py:68` has
`help_text="FTS query string (translated to Russian if Bosnian input)"` while
`src/backend/apps/search/models.py:76-79` has
`help_text="FTS query string stored in the user's language; matched against the per-language search vector (no query-time translation)"`.
Field type (TextField) matches in both — only help_text differs.

**Chosen solution:** Update the migration's help_text to match the model.

**Rationale:** The model's help_text is more accurate (it correctly documents the no-query-time-translation behavior, which was already changed). Editing the single initial migration in-place is acceptable because:
- This is the project's steady-state pattern (one `0001_initial.py` per app).
- The field type (TextField) already matches; only documentation text needs syncing.
- Creating a new migration for a help_text-only change would be migration bloat.

**Risk:** Minimal — help_text is documentation only, no schema change. No test impact beyond `test_makemigrations_check`.

### C — Moderation API 422 serialization (3 tests in `test_priority_service.py`)

**Root cause (verified):** `src/backend/apps/moderation/views/api_bulk.py:42-47` catches
`pydantic.ValidationError` and passes `exc.errors()` directly to `JsonResponse`.
Pydantic v2.13+ returns `bytes` in the `input` field for `json_invalid` errors on raw
bytestring request bodies. Django's `DjangoJSONEncoder` does not serialize `bytes`.

**Chosen solution:** Create a shared helper `pydantic_errors_json(exc)` that uses
`json.loads(exc.json(include_input=False, include_url=False, include_context=False))` —
this delegates serialization to pydantic-core (which handles bytes correctly) and strips
all three non-serializable / sensitive fields. Log full errors server-side *before*
stripping.

**Rationale:** Researcher 2 proved empirically that:
- `exc.errors()` raw → `TypeError` (bytes)
- `exc.errors(include_input=False)` only fixes bytes but **not** the `ctx` hazard (live
  `ValueError` objects from custom validators)
- `exc.json()` with default flags raises `ValueError` on non-UTF-8 bodies
- `json.loads(exc.json(include_input=False, include_url=False, include_context=False))`
  is the **only** form robust against all four scenarios (empty, malformed, non-UTF-8,
  field-level errors)

Security: stripping `input` prevents CWE-209 (raw request body echo); stripping `url`
prevents Pydantic version fingerprinting; stripping `ctx` removes live exception objects.

**Placement:** `src/backend/apps/core/utils/sanitize.py` (existing sanitize utility module)
— adds a `pydantic_errors_json()` function, consistent with the module's naming.

**Risk:** Tests assert only that `"errors"` is a non-empty list — the sanitized output
(`{type, loc, msg}` dicts) satisfies this. No API contract change (422 status retained).
Log-first ensures operators retain full diagnostics.

### B — Template tag i18n timing (2 tests in `test_auth_nav.py`)

**Root cause (verified):** `src/backend/apps/core/templatetags/telegram_tags.py:41,64-69`
defines `_LABELS` dict at module level using `gettext` (`_()`). Translation is evaluated
at **import time** (before any request language is activated), freezing strings in the
default language. The template `header_catalog.html:34` renders `{% telegram_deep_link "create_ad" %}`
which calls `str(_LABELS[cmd])` at line 150 — always returns the import-time translation.

**Chosen solution:** Change `from django.utils.translation import gettext as _` to
`from django.utils.translation import gettext_lazy as _` (line 41). The `str()` call at
line 150 resolves the lazy string at render time, when the per-request language is active.

**Rationale:** This is Django's documented best practice for module-level translatable
strings. The Validator confirmed `telegram_tags.py` is the **only** template tag with this
pattern — `dashboard.py` uses `gettext_lazy` inside function bodies (safe), `enums.py`
uses `gettext_lazy` at class-body level (safe). One-line, zero-risk fix.

**Risk:** Zero. `gettext_lazy` produces an object that behaves identically to `str` when
coerced via `str()` at render time. No test impact beyond fixing the 2 failing tests.

### E — Seed generator draft collision (8 tests in `test_seed.py`)

**Root cause (verified):** `src/backend/apps/seed/generators/ads.py:401-426` loops
`ad_count` times, independently selecting `user = self._rng.choice(self.users)` and
`status = self._weighted_status(statuses, weights)`. With 10% DRAFT weight and 4-10 users,
multiple DRAFTs land on the same user → `IntegrityError` on `bulk_create` (line 110).

**Chosen solution:** Implement **Researcher 1's Option A** — "pre-compute allocation":
add a `_deduplicate_drafts(ads, statuses, weights)` post-processing step in
`AdGenerator.generate()` (called after the generation loop, before returning) that:
1. Counts DRAFTs per user.
2. For any user with >1 DRAFT, reassigns excess DRAFTs to a non-DRAFT status (weighted
   random from the same distribution, excluding DRAFT) using the same `self._rng`.
3. Sets appropriate timestamps for the reassigned status.

This mirrors the bot's `create_draft_ad` pattern (`ad_create.py:911-913` deletes existing
DRAFTs before creating a new one) — the seed generator enforces the same invariant.

**Rationale:**
- **Deterministic:** Uses `self._rng` (seeded from `faker_seed=42`), preserving
  reproducibility. No RNG stream disruption for downstream steps (image generation, etc.).
- **Full PK backfill:** `bulk_create` runs normally (no `ignore_conflicts`), so PKs are
  correctly set. No silent row drops.
- **No DB changes:** The constraint stays as-is (it's the business rule).
- **Architectural:** Makes the seed generator constraint-aware — a reusable pattern for
  future constraints.

**Risk:** Low. The status distribution shifts slightly (excess DRAFTs become non-DRAFT),
but the seed config uses approximate weights, not exact counts. All seed tests assert
behavioral properties (feature/condition/purpose data present), not exact draft counts.

### A — Test fixture draft duplication (2 errors in `test_ads_published.py`)

**Root cause (verified):** `src/backend/apps/analytics/tests/test_ads_published.py:43-44`
fixture `seller_ads` creates:
- 3 PUBLISHED ads
- 1 DRAFT ("Draft Ad")
- 1 DRAFT ("Another Draft") ← violates `uq_ads_single_draft_per_user`
- 1 REJECTED ("Rejected Ad")

The test `test_per_ad_stats_includes_all_ads` expects 6 total ads; `test_ads_published_counts_only_published`
expects `ads_published == 3`.

**Chosen solution:** Change the second DRAFT to `AdStatus.REJECTED` (matching the existing
"Rejected Ad" pattern). Update the fixture docstring/comment accordingly.

**Rationale:** The test's purpose is to verify non-published ads (DRAFT, REJECTED, etc.)
are excluded from `ads_published` and included in `per_ad_stats`. The specific status of
the non-published ads doesn't matter — only that they're not PUBLISHED. Using
`AdStatus.REJECTED` for the second "non-published" ad preserves the test intent
(3 published + 3 non-published = 6 total, `ads_published == 3`) while respecting the
constraint.

This aligns with the architectural principle: **test fixtures must respect production
invariants.** The bot enforces "one DRAFT per user" — tests should too.

**Risk:** Zero. The test assertions don't check for specific status counts beyond
`ads_published == 3` and `len(per_ad_stats) == 6`. Both still hold.

---

## 3. Execution Ordering & Dependencies

All five fixes are **independent** — no fix depends on another's output. However,
ordering for clean verification:

| Step | Category | Change | Lines | Independent? |
|------|----------|--------|-------|-------------|
| 1 | D | Sync help_text in migration | 1 | ✅ Yes |
| 2 | C | Add `pydantic_errors_json()` + use in `api_bulk.py` | 2 files | ✅ Yes |
| 3 | B | `gettext` → `gettext_lazy` in `telegram_tags.py` | 1 line | ✅ Yes |
| 4 | E | Add `_deduplicate_drafts()` in `AdGenerator.generate()` | 1 method | ✅ Yes |
| 5 | A | Change 2nd DRAFT → REJECTED in `seller_ads` fixture | 1 line | ✅ Yes |

**No ordering dependencies.** The Implementor may execute all 5 in a single pass.

---

## 4. Risk Assessment

| Category | Backward Compatibility | Test Impact | Rollback Safety |
|----------|----------------------|-------------|-----------------|
| D | ✅ None (help_text only) | ✅ Fixes 1 test | ✅ Single-line revert |
| C | ✅ API still returns 422 | ✅ Fixes 3 tests, satisfies existing assertions | ✅ Revert helper + view line |
| B | ✅ `gettext_lazy` resolves identically at render | ✅ Fixes 2 tests | ✅ Single import change |
| E | ✅ Seed data still varied (just no DRAFT collisions) | ✅ Fixes 8 tests | ✅ Revert method |
| A | ✅ No production code change | ✅ Fixes 2 errors | ✅ Single-line revert |

**Aggregate:** All fixes are backward-compatible. No schema changes beyond the
already-correct help_text sync. No API contract changes (422 retained, error
format unchanged — still a list under `"errors"`).

---

## 5. Post-Fix Verification

- `make test` (fast gate, skips seed suite) — expect 0 failures
- Seed suite: `pytest -m seed` or `make test-all` (seed subset) — expect 0 failures
- `makemigrations --check --dry-run` — expect no pending migrations
- Moderation API returns 422 (not 500) on empty/malformed/malformed-JSON bodies
- Template renders translated strings for `ru`/`bs` locales
