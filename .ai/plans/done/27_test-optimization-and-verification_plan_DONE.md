---
id: 27_test-optimization-and-verification
domain: testing
status: done
generated: 2026-08-22
---

# Plan 27 — CI Verification Fixes + Test Optimization (Marker Hygiene, CI Split, Seed Acceleration) — DONE

## Summary

Executed the validated plan with the following outcome per branch. The primary
CI-blocking work (Branch A) and the concrete, machine-verifiable seed / E-branch
accelerations are **complete and verified**. The large-scale marker-reclassification
(B-02) and CI matrix restructure (Branch C) are **deferred** with rationale (see
Deferred Work).

## Branch A — Static Verification (O-03) ✅ COMPLETE (pre-existing commit `2ff668c`)

- A-01: 4 unused imports removed (`test_dashboard_stats.py`, `test_trust_analytics.py`).
- A-02: 8 basedpyright errors resolved (generator fixture annotations, atomic-block
  type ignore, `list[SlugField]`→`list[str]` coercion).
- A-03: **Verified green**: `uv run ruff check src/backend` → 0 errors;
  `uv run basedpyright src/backend` → 0 errors/warnings/notes.

## Branch D — Seed Acceleration ✅ (partial)

- **D-01 ✅** New `src/backend/apps/seed/tests/conftest.py` — autouse fixture patches
  `seed_service.ImageGenerator` (class-name binding) to a no-op stub returning `[]`,
  skipping the image pipeline + SHA-256 backfill for non-image seed tests. `unit`/`slow`
  markers untouched. `test_media_cleanup` opts out via `@pytest.mark.real_images`
  (registered in pyproject). Verified: `test_seed_with_zero_count`,
  `test_seed_force_skips_prompt` pass under the mock; `test_media_cleanup` /
  `test_generates_ad_images` pass with the real generator.
- **D-02 ✅** `test_no_non_leaf_category_assigned` reduced `--ads=50` → `--ads=10`
  (assertion is no-non-leaf only). Verified passing. `test_full_seed_coverage` untouched
  (coupon-collector bound).
- **D-03 ⏸ DEFERRED** Class-scoped shared seed fixture — **not implemented**. The plan's
  mechanism (`django_db(transaction=True)` + class-scoped fixture persisting across 5 tests)
  is incompatible with pytest-django: TransactionTestCase **flushes (truncates) all tables
  after every test**, so class-scoped seed data would not survive to tests 2–5 (broken
  isolation / false failures in nightly tests). D-01 already delivers the dominant speedup.
- **D-04 ✅** Lazy image preprocessing in `ImageGenerator.generate`: category→photo map is
  built from manifest metadata (file-existence filter only, no disk I/O); each selected photo
  is preprocessed on demand via new `_preprocess_one` (identical filenames/thumbnails, cache
  check preserved). `--ads=0` skips preprocessing entirely. Verified: `test_generates_ad_images`
  and `test_media_cleanup` pass with the real generator.
- **D-05 ⏸ DEFERRED (optional)** Session-scoped `load_catalog` cache — explicitly optional /
  lower-priority per plan; session-scoped DB transaction management is flagged fragile.
  Deferred to avoid test-pollution risk.

## Branch E — Secondary Optimizations ✅ COMPLETE

- **E-01 ✅** Extracted the 2 pure `inspect.getsource` sweep tests to new
  `src/backend/apps/core/tests/test_sweep_lock_structure.py` (`pytestmark = [pytest.mark.unit]`),
  removed them from `test_sweep_commands.py` (which keeps the 37 DB-backed slow+integration
  tests). Verified: new file passes under `-m unit`; sweep_commands still passes.
- **E-02 ✅** Added `create_test_ads_bulk()` to `src/backend/conftest.py` and used it in the 3
  data-heavy priority tests (`test_many_ads_user_score_bonus`, `test_below_ad_threshold_no_bonus`,
  `test_combined_bonus`). Verified: full `test_priority.py` passes.
- **E-03 ✅** NO ACTION (verified): `test_settings_secrets.py` already carries
  `unit` + `settings`; subprocess isolation is the correct pattern.
- **E-04 ✅** Sleep elimination: D1 translation-timeout test patches
  `TRANSLATION_TIMEOUT_SECONDS` to 0.05 and reduces `time.sleep(0.8)`→`0.1`; D2 re-publish test
  backdates `published_at`/`original_published_at` to `now-10s` before capturing `first_published`
  (removed inline `import time`). Verified: full `test_multi_lang_translation.py` and
  `test_ad_lifecycle.py` pass.

## Branch B — Marker Hygiene ⏸ PARTIAL

- **B-01 (research gate)**: Adoption decision recorded as **Go-with-changes**. The `slow`
  marker is verified decorative (fast gate / CI filter only on `seed`), so reclassification
  is safe; however the genuinely-slow (~40) list is not fully enumerated in a deterministic
  per-test form in the plan/spec, and the primary consumer (Branch C) is deferred.
- **B-03 ✅** Added `pytestmark = [pytest.mark.unit]` to 12 DB-free SimpleTestCase files
  (`test_ad_localization`, `test_adimage_thumbnail_urls`, `test_detail_context`,
  `test_listings_context`, `test_trust_prefetch` [path corrected to `apps/trust/tests/`],
  `test_context_processors`, `test_csp_report`, `test_language_locale`,
  `test_language_middleware`, `test_preferred_city_middleware`, `test_templates`,
  `test_autocomplete_template`); added `integration` to 5 bare `django_db` files
  (`test_create_admin_user`, `test_privacy`, `test_price_normalizer`, `test_recompute_command`,
  `test_consent_context`). Verified: 12 unit files pass under `-m unit` (no DB access
  required); `-m unit` collects ~227.
- **B-04 ✅** Added module-level `pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))`
  to the 6 concurrent bot files; registered `xdist_group` in `pyproject.toml` markers; switched
  `--dist loadscope` → `--dist loadgroup` in `.github/workflows/ci.yml`. (ci-nightly.yml had no
  `--dist loadscope` occurrence — verified via grep; the seed command never used `--dist`.)
  Verified `-m concurrent` collects 28.
- **B-02 ⏸ DEFERRED** Reclassify `slow` off 52 module-level files to ~40 genuinely-slow tests.
  Deferred: (1) its sole consumer is Branch C, itself deferred; (2) the evidence-derived
  genuinely-slow list is not deterministically enumerated per-test in the plan, so per-file
  manual classification across 52 files risks introducing misleading markers with no
  verifiable benefit; (3) nothing in the fast gate / CI filters on `slow`, so deferring is
  behaviorally neutral.

## Branch C — CI Split + Coverage Merge ⏸ DEFERRED

- C-01/C-02/C-03 (4-job matrix, per-job Postgres, `coverage combine`, merged `fail_under=80`):
  **deferred entirely**. Rationale: (1) requires GitHub Actions execution to verify — not
  available in this implementation session; (2) HIGH risk CI restructure gated on B-05
  (full-suite collection proof) which itself depends on B-02; (3) per-job Postgres services
  and artifact merge cannot be validated locally. Deferring avoids shipping an unverified
  CI refactor.

## Files Changed (this execution)

- `pyproject.toml` (B-04 marker, B-03/D-01 marker registration)
- `.github/workflows/ci.yml` (B-04 `--dist loadgroup`)
- `src/backend/conftest.py` (E-02 `create_test_ads_bulk`)
- `src/backend/apps/seed/generators/images.py` (D-04 lazy preprocessing)
- `src/backend/apps/seed/tests/conftest.py` (NEW, D-01 image mock)
- `src/backend/apps/seed/tests/test_seed.py` (D-01 real_images opt-out, D-02 ads reduction)
- `src/backend/apps/moderation/tests/test_priority.py` (E-02 bulk helper)
- `src/backend/apps/core/tests/test_sweep_lock_structure.py` (NEW, E-01 unit file)
- `src/backend/apps/core/tests/test_sweep_commands.py` (E-01 removed 2 inspection tests)
- `src/telegram_bot/tests/test_multi_lang_translation.py` (E-04 D1)
- `src/telegram_bot/tests/test_ad_lifecycle.py` (E-04 D2)
- 12 unit-marked files (B-03a), 5 integration-marked files (B-03b), 6 concurrent bot files (B-04)

## Verification Performed

- `uv run ruff check src/backend src/telegram_bot` → 0 errors
- `uv run basedpyright src/backend` → 0 errors/warnings/notes
- Docker test runs (PostgreSQL): seed image tests, seed command tests, E-branch suites
  (priority/sweep/translation/lifecycle), 12 unit-marked files — all pass.
