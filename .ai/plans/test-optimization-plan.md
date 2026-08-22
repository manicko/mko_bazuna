# Test Optimization Plan

**Project:** Mko Bazuna (Telegram-driven classifieds board)
**Based on:** Audit Report `.ai/audit/tests/audit_report_1.md`
**Status:** Implemented — Phase A–D complete (commits `b62612` + `3ddc0b2`). See `.ai/plans/test-suite-audit-plan.md` for the ongoing strategy/infra plan (Phase E).
**Author:** Kilo (planner agent)

---

## 1. Objective

Restore and sustain test suite integrity by:

1. **Eliminating redundancy** — collapse ~29 duplicated fixture definitions and ~18 duplicated ad-creation helpers into the canonical root-conftest fixtures and `create_test_ad` (which is currently dead code).
2. **Standardizing the test framework** — migrate 14 `django.test.TestCase` files to pytest-django (`@pytest.mark.django_db` + marker taxonomy) so `-m unit` / `-m integration` filtering works uniformly.
3. **Closing critical coverage gaps** — add missing tests for Ad check constraints, the `approve_ad → PUBLISHED → alert` signal chain, ad-detail trust-score prefetch (N+1), login-token edge cases, and search sort orderings.
4. **Fixing hygiene defects** — remove the unused `e2e` marker, replace private-method coupling in `test_priority.py` with public-API coverage, and add direct unit tests for moderation decorators.
5. **Correcting stale documentation** — rewrite this plan to reflect reality (all 6 markers registered; CI uses `-m "not seed"`; no shadowed `tests.py`).

All tasks are atomic, independently reviewable, and must pass `--create-db` validation.

---

## 2. Current State

### Findings requiring action (7 open + 2 resolved)

| ID  | Finding | Severity | Status |
|-----|---------|----------|--------|
| F-01 | Shadowed `tests.py` modules (31 silently-skipped tests; 1 real failure masked) | CRITICAL | **RESOLVED** (audit commit `07a8f49` / `d72e597`) |
| F-02 | Duplicated `seller`/`user`/`category`/`city` fixtures across ~29 files | BEST-PRACTICE | OPEN |
| F-03 | Duplicated `_make_ad`/`_create_ad` helpers across ~18 files (inconsistent, buggy variants) | BEST-PRACTICE | OPEN |
| F-04 | Canonical `create_test_ad` defined but 0 external references (dead code) | BEST-PRACTICE | OPEN |
| F-05 | 14 files use `django.test.TestCase` instead of `pytest.mark.django_db` | TEST-UPDATE | OPEN |
| F-06 | Missing direct unit tests for `staff_required` / `staff_required_api` decorators | TEST-UPDATE | OPEN |
| F-07 | `test_priority.py` tests private methods `_get_priority_level` / `_estimate_confidence` directly | TEST-UPDATE | OPEN |
| F-08 | `e2e` marker registered but 0 usages | BEST-PRACTICE | **RESOLVED** (removed in A.1) |
| F-09 | Stale test-optimization plan (4 discrepancies, §5) | DOC-UPDATE | OPEN |

### Coverage gaps (11)

| Gap | Priority | Component | Summary |
|------|----------|-----------|---------|
| G-01 | P0 | `Ad` model | 6 CheckConstraints not all tested directly (only 3 tested via `IntegrityError` in `test_ad_lifecycle.py`) |
| G-02 | P0 | `listings.py::ad_detail` | Missing `user__trust_score` prefetch — N+1 on trust badge render |
| G-03 | P0 | `moderation/signals.py` | `approve_ad → PUBLISHED` side-effect chain (priority recalc + immediate alerts on commit) not tested |
| G-04 | P1 | `core/services/contact.py` | Combinatorial edge cases for `can_contact_seller` / `get_seller_for_contact` (banned + WITHROW, DECLINE vs WITHDRAWN) |
| G-05 | P1 | `search/views/search.py` | `DATE_OLD` / `DATE_NEW` sort orderings not asserted in `test_search_triggers.py` |
| G-06 | P1 | `users/models.py` `LoginToken` | Token issuance, replay/claim atomicity, hash-mismatch rejection not tested |
| G-07 | P1 | `telegram_bot/handlers/ad_create.py` | `save_photo → generate_thumbnails` integration (populates `thumbnail_*`) not tested end-to-end |
| G-08 | P2 | `trust/services/trust_calculator.py` | Quality-score truncation edge case (activity cap × threshold interaction) |
| G-09 | P2 | `moderation/services/priority_calculator.py` | `_estimate_confidence` boundary tests via public API |
| G-10 | P2 | `moderation/services/priority_calculator.py` | Priority calculator score-to-level boundary matrix via persisted `AdModerationPriority` row |
| G-11 | P2 | `trust/services/trust_calculator.py` | Trust-level floor (score=0 + verified/premium → VERIFIED) |

### Environment constraints (from audit §4)

- Test DB: `mko-bazuna-test-db-1` on port 5433
- Test command: `docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm test`
- CI command: `pytest -m "not seed" -n auto --dist loadscope --tb=short --cov --durations=10`
- Use `--create-db` to avoid stale-schema errors (527 errors on `--reuse-db`)
- All 6 markers registered in `pyproject.toml` `[tool.pytest.ini_options] markers`: `unit`, `integration`, `seed`, `settings`, `concurrent`, `slow` (the `e2e` marker was removed in A.1)

---

## 3. Implementation Tasks (grouped in phases)

### Phase A: Cleanup & Consistency (high-impact, low-risk)

#### A.1 — Remove unused `e2e` marker
| Field | Value |
|-------|-------|
| **ID** | A.1 |
| **Type** | Cleanup |
| **Priority** | Low |
| **Finding** | F-08 |
| **Description** | Remove the `e2e` marker line from `pyproject.toml` `[tool.pytest.ini_options] markers`. Audit for any `e2e` usage in `.ai/` docs and remove references. No `pytest.mark.e2e` usages exist in source (confirmed by grep — only the slug `"transport-e2e"` in `test_language_end_to_end.py`, unrelated). |
| **Files to change** | `pyproject.toml` |
| **Acceptance criteria** | `grep -r "e2e" pyproject.toml` returns nothing in the markers list. Test collection still succeeds. |
| **Test command** | `docker compose ... run --rm test --collect-only` (collection succeeds, no `e2e` marker warning) |

#### A.2 — Adopt root conftest fixtures across all test files
| Field | Value |
|-------|-------|
| **ID** | A.2 |
| **Type** | Refactoring |
| **Priority** | Medium |
| **Finding** | F-02 |
| **Description** | Remove local `seller`/`user`/`category`/`city` fixture redefinitions from all ~29 test files and their local `conftest.py` files. Rely on the root `src/backend/conftest.py` fixtures. **Exception**: `src/telegram_bot/tests/conftest.py` defines an async `user` fixture (scope conflict with the synchronous root fixture) — keep the local fixture or rename it; document the decision in the bot conftest. Files affected: `test_ad_lifecycle.py`, `test_admin_actions.py`, `test_auto_moderation.py`, `test_moderation_views.py`, `test_search_view.py`, `test_autocomplete.py`, `test_saved_search_create.py`, `test_preferred_city_readback.py`, `test_alert_query.py`, `test_preferred_city.py`, `test_auth_nav.py`, `test_search_triggers.py`, `test_script_gating.py`, `test_media_security.py`, `test_favorites.py`, `test_gallery_markup.py`, `test_backfill_thumbnails.py`, `test_contact.py`, `test_sweep_commands.py`, `test_logout.py`, `test_consent_context.py`, `test_consent.py`, `test_deletion.py`, `test_account_state.py`, `test_consent_records.py`, `test_favorites_badge.py`, `test_cabinet_sections.py`, `telegram_bot/tests/test_ad_lifecycle.py`, `telegram_bot/tests/test_ad_create.py`. |
| **Files to change** | All ~29 test files + `src/telegram_bot/tests/conftest.py` (decision on async `user`) |
| **Acceptance criteria** | Root conftest is the single source of truth for these 4 fixtures. No file redefines them (except documented async override in bot conftest). Full test suite passes with `--create-db`. |
| **Test command** | `docker compose ... run --rm test -m "not seed" --create-db` |

#### A.3 — Consolidate `_make_ad`/`_create_ad` helpers into `create_test_ad`
| Field | Value |
|-------|-------|
| **ID** | A.3 |
| **Type** | Refactoring |
| **Priority** | Medium |
| **Finding** | F-03, F-04 |
| **Description** | For each of the ~18 files defining `_make_ad` or `_create_ad`, replace the local helper body with a call to the canonical `create_test_ad` from root conftest (imported via `from conftest import create_test_ad` or accessed through `pytest.fixture` composition). Delete the local helper definitions. The canonical helper already handles all 6 status-timestamp combinations correctly. **Decision**: Adopt (not delete) since it is documented future-proofing with 0 bugs; A.3 makes it live code. Sub-tasks are grouped per-app to keep diffs reviewable: A.3a (ads app, 8 files), A.3b (moderation app, 5 files), A.3c (search app, 4 files), A.3d (core/trust/media apps, 1 file each). |
| **Files to change** | `apps/ads/tests/test_ad_lifecycle.py`, `apps/ads/tests/test_ad_image_service.py`, `apps/ads/tests/test_media_security.py`, `apps/ads/tests/test_script_gating.py`, `apps/ads/tests/test_favorites.py`, `apps/ads/tests/test_gallery_markup.py`, `apps/ads/tests/test_dashboard_stats.py`, `apps/trust/tests/test_trust_calculator.py`, `apps/moderation/tests/test_admin_actions.py`, `apps/moderation/tests/test_auto_moderation.py`, `apps/moderation/tests/test_moderation_views.py`, `apps/moderation/tests/test_priority.py`, `apps/moderation/tests/test_priority_service.py`, `apps/search/tests/test_search_view.py`, `apps/search/tests/test_alert_query.py`, `apps/search/tests/test_preferred_city.py`, `apps/search/tests/test_preferred_city_readback.py`, `apps/core/tests/test_contact.py`, `apps/core/tests/test_sweep_commands.py`, `apps/media/tests/test_backfill_thumbnails.py`, `apps/users/tests/test_consent.py` |
| **Acceptance criteria** | `grep -rn "def _make_ad\|def _create_ad" src/` returns 0 results (dead-code helper in `test_ad_localization.py` is a SimpleTestCase in-memory variant — keep, it doesn't touch DB). `create_test_ad` is referenced from ≥15 test files. Full suite passes with `--create-db`. |
| **Test command** | `docker compose ... run --rm test -m "not seed" --create-db` |

> **Note on `test_ad_localization.py`**: Its `_make_ad` builds an in-memory `Ad` via `__new__` (no DB) for testing `get_title`/`get_description` fallback. It does **not** hit the DB or check constraints, so it is **out of scope** for A.3. Document this exception.

### Phase B: Framework Migration & Refactoring (medium-effort, medium-risk)

#### B.1 — Migrate 14 `TestCase` files to pytest-django
| Field | Value |
|-------|-------|
| **ID** | B.1 |
| **Type** | Framework migration |
| **Priority** | Medium |
| **Finding** | F-05 |
| **Description** | Convert each of the 14 `django.test.TestCase` classes to pytest-style test classes/functions using `@pytest.mark.django_db` and the appropriate marker (`unit` or `integration`). Convert `self.assertEqual(a, b)` → `assert a == b`, `self.assertIn` → `assert ... in`, `self.assertNotIn` → `assert ... not in`, `self.assertGreaterEqual` → `assert ... >=`, `self.assertLess` → `assert ... <`, `self.assertTrue` → `assert`, `self.assertFalse` → `assert not`. Replace `setUpTestData`/`setUp` with fixtures or module-level setup. Apply `pytestmark = [pytest.mark.django_db, pytest.mark.integration]` (or `unit` for pure-logic tests) at module level, matching the pattern in `test_ad_lifecycle.py` and `test_admin_actions.py`. |
| **Files to change** | `apps/analytics/tests/test_views.py`, `apps/analytics/tests/test_trust_analytics.py`, `apps/analytics/tests/test_seller_stats.py`, `apps/analytics/tests/test_rollup_daily_metrics.py`, `apps/analytics/tests/test_moderation_analytics.py`, `apps/analytics/tests/test_ads_published.py`, `apps/ads/tests/test_breadcrumbs_render.py`, `apps/ads/tests/test_dashboard_stats.py`, `apps/moderation/tests/test_priority.py`, `apps/moderation/tests/test_priority_service.py`, `apps/trust/tests/test_trust_calculator.py`, `apps/trust/tests/test_trust_tags.py`, `apps/core/tests/test_language_end_to_end.py`, `apps/seed/tests/test_seed.py` |
| **Acceptance criteria** | `grep -rn "django\\.test.*TestCase" src/` returns 0 (all `SimpleTestCase` usages are fine — they don't require DB). Each file has `pytestmark = [..., pytest.mark.unit/integration]` matching its semantics. `-m unit` and `-m integration` correctly select/deselect all migrated files. Full suite passes. |
| **Test command** | `docker compose ... run --rm test -m "not seed" --create-db` + `docker compose ... run --rm test -m unit --create-db` (verifies marker filterability) |

#### B.2 — Add direct unit tests for moderation decorators
| Field | Value |
|-------|-------|
| **ID** | B.2 |
| **Type** | Test addition |
| **Priority** | Low |
| **Finding** | F-06 |
| **Description** | Create `apps/moderation/tests/test_decorators.py` with parametrized unit tests covering: (a) `staff_required` non-staff → `Http404`, (b) staff → passthrough, (c) superuser → passthrough, (d) `staff_required_api` non-staff → 403 JSON, (e) `staff_required_api` staff + wrong method (GET) → 405, (f) `staff_required_api` staff + POST → passthrough. Use `RequestFactory` + `AnonymousUser`/`User` mocks; mark `pytest.mark.unit`. |
| **Files to change** | **New:** `apps/moderation/tests/test_decorators.py` |
| **Acceptance criteria** | 6 test cases pass. `grep -rn "staff_required" apps/moderation/tests/test_decorators.py` returns the tested functions. |
| **Test command** | `docker compose ... run --rm test apps/moderation/tests/test_decorators.py --create-db` |

#### B.3 — Refactor `test_priority.py` to test public API, not private methods
| Field | Value |
|-------|-------|
| **ID** | B.3 |
| **Type** | Test refactoring |
| **Priority** | Low |
| **Finding** | F-07 |
| **Description** | In `apps/moderation/tests/test_priority.py`, replace the two tests that call `_get_priority_level` and `_estimate_confidence` directly with tests that exercise the public `PriorityCalculator.calculate_priority` return dict. Add boundary coverage through the public API for the score→level mapping (0→LOW, 49→LOW, 50→MEDIUM, 79→MEDIUM, 80→HIGH, 100→HIGH) and the confidence value (0.7). Remove the direct private-method calls. This is also the basis for coverage gap G-09. |
| **Files to change** | `apps/moderation/tests/test_priority.py` |
| **Acceptance criteria** | `grep -n "_get_priority_level\|_estimate_confidence" apps/moderation/tests/test_priority.py` returns 0. Boundary score matrix is tested through `calculate_priority`. Full test file passes. |
| **Test command** | `docker compose ... run --rm test apps/moderation/tests/test_priority.py --create-db` |

### Phase C: Coverage Expansion (high-effort, high-value)

#### C.1 — Add Ad model CheckConstraint tests (all 6)
| Field | Value |
|-------|-------|
| **ID** | C.1 |
| **Type** | Test addition |
| **Priority** | High (P0) |
| **Gap** | G-01 |
| **Description** | Create `apps/ads/tests/test_ad_constraints.py` covering all 6 CheckConstraints on `Ad.Meta`: `ck_ads_published_at_if_published`, `ck_ads_archived_at_if_archived`, `ck_ads_rejected_at_if_rejected`, `ck_ads_moderation_failed_at_if_failed`, `ck_ads_deleted_at_if_deleted`, `ck_ads_failed_and_rejected_mutually_exclusive`. For each, use `bulk update` within `transaction.atomic()` to assert `IntegrityError`, then verify the row is untouched (savepoint rollback). This complements the 3 existing tests in `test_ad_lifecycle.py` with the remaining 3 + the mutual-exclusivity constraint (already partially covered). Uses `create_test_ad` from root conftest. Mark `pytest.mark.integration`. |
| **Files to change** | **New:** `apps/ads/tests/test_ad_constraints.py` |
| **Acceptance criteria** | 6+ test cases, each asserting `IntegrityError` for a violated constraint. All 6 constraint names referenced. Full suite passes. |
| **Test command** | `docker compose ... run --rm test apps/ads/tests/test_ad_constraints.py --create-db -v` |

#### C.2 — Fix ad-detail view trust-score prefetch (N+1)
| Field | Value |
|-------|-------|
| **ID** | C.2 |
| **Type** | Code fix + test |
| **Priority** | High (P0) |
| **Gap** | G-02 |
| **Description** | In `apps/ads/views/listings.py::ad_detail`, add `prefetch_related("user__trust_score")` to the queryset (mirroring the `listings` view at line ~255). Update `test_detail_context.py` — the current mock chains `select_related().prefetch_related().get()` but does not assert `user__trust_score` is in the prefetch call. Add an assertion that `prefetch_related` is called with `"user__trust_score"`. Additionally, add a `django.assertNumQueries` or `CaptureQueriesContext` test in a new `test_ad_detail_queries.py` that renders a real detail page and asserts no more than N queries (catching N+1 regressions). |
| **Files to change** | `apps/ads/views/listings.py` (1 line), `apps/ads/tests/test_detail_context.py` (extend mock assertion), **New:** `apps/ads/tests/test_ad_detail_queries.py` |
| **Acceptance criteria** | `ad_detail` queryset includes `.prefetch_related("user__trust_score")`. `test_detail_context.py` asserts the prefetch call arg. New query-count test passes with ≤ N queries for a page with M ads. |
| **Test command** | `docker compose ... run --rm test apps/ads/tests/test_detail_context.py apps/ads/tests/test_ad_detail_queries.py --create-db` |

#### C.3 — Add admin-action side-effect tests (`approve_ad → PUBLISHED` signal chain)
| Field | Value |
|-------|-------|
| **ID** | C.3 |
| **Type** | Test addition |
| **Priority** | High (P0) |
| **Gap** | G-03 |
| **Description** | Extend `apps/moderation/tests/test_admin_actions.py` (or create `test_approve_ad_side_effects.py`) to assert: (a) `approve_ad` on an `ON_MODERATION` ad → status `PUBLISHED` (not just routed through `set_published`), (b) `Ad.post_save` fires `deliver_immediate_alerts_on_publish` — when `IMMEDIATE_ALERTS_ENABLED=False` (default), no alert call is made; when enabled, `transaction.on_commit` schedules `deliver_immediate_alerts` and it runs after commit. (c) `calculate_ad_priority` signal fires when ad transitions to `ON_MODERATION` (assert `AdModerationPriority` row is created). Use `override_settings` and mock `deliver_immediate_alerts` to avoid real Telegram calls. Mark `pytest.mark.integration`. |
| **Files to change** | **New:** `apps/moderation/tests/test_approve_ad_side_effects.py` |
| **Acceptance criteria** | Tests assert both branches of `IMMEDIATE_ALERTS_ENABLED` and that `AdModerationPriority` is created on `ON_MODERATION`. All assertions pass with `--create-db`. |
| **Test command** | `docker compose ... run --rm test apps/moderation/tests/test_approve_ad_side_effects.py --create-db -v` |

#### C.4 — Add search sorting tests (`DATE_OLD` / `DATE_NEW`)
| Field | Value |
|-------|-------|
| **ID** | C.4 |
| **Type** | Test addition |
| **Priority** | Medium (P1) |
| **Gap** | G-05 |
| **Description** | In `apps/ads/tests/test_search_triggers.py`, add tests for `DATE_OLD` (`?sort=date_asc` → `order_by("published_at")`) and `DATE_NEW` (`?sort=date_desc` → `order_by("-published_at")`). Create 3+ PUBLISHED ads with distinct `published_at` timestamps, call the search view via `Client`, and assert the result order matches ascending/descending. The existing `test_search_rank_orders_by_relevance` only covers the FTS relevance path. Mark `pytest.mark.integration`. |
| **Files to change** | `apps/ads/tests/test_search_triggers.py` |
| **Acceptance criteria** | 2 new test functions asserting correct sort order for DATE_OLD and DATE_NEW. Existing tests still pass. |
| **Test command** | `docker compose ... run --rm test apps/ads/tests/test_search_triggers.py --create-db -v` |

#### C.5 — Add LoginToken edge-case tests
| Field | Value |
|-------|-------|
| **ID** | C.5 |
| **Type** | Test addition |
| **Priority** | Medium (P1) |
| **Gap** | G-06 |
| **Description** | Extend `apps/users/tests/test_login.py` with tests for: (a) token hash mismatch — polling `/login/status/?token=<wrong_hash>` for a known raw token returns 410, (b) `token_hash` is always `sha256(raw)`, never raw — assert the stored hash ≠ raw token string, (c) replay/claim atomicity — two-phase claim (bot sets `telegram_id`, web sets `consumed_at`) can't be double-consumed. Add a parametrized test over the `token_hash` length (64 hex chars). Mark `pytest.mark.integration`. |
| **Files to change** | `apps/users/tests/test_login.py` |
| **Acceptance criteria** | 3+ new test cases covering hash mismatch, raw-token-never-stored, and claim atomicity. Full login test file passes. |
| **Test command** | `docker compose ... run --rm test apps/users/tests/test_login.py --create-db -v` |

#### C.6 — Add `save_photo → generate_thumbnails` integration test
| Field | Value |
|-------|-------|
| **ID** | C.6 |
| **Type** | Test addition |
| **Priority** | Medium (P1) |
| **Gap** | G-07 |
| **Description** | Create `apps/media/tests/test_save_photo_integration.py`. Test the integration between `save_photo` (in `telegram_bot/handlers/ad_create.py`) and `ThumbnailService.generate_thumbnails` (already unit-tested in `test_thumbnails.py`). Assert that after `save_photo` writes a photo, the three thumbnail keys (`thumbnail_small`, `thumbnail_medium`, `thumbnail_large`) are populated on the resulting `AdImage` row (or set to `None` on the failure path at lines 728–735). Use `isolated_media_root` pattern from `test_ad_image_service.py`. Since `save_photo` lives in the bot package, test it as an integration through the bot test infrastructure or mock `ThumbnailService.generate_thumbnails` to assert it is called with correct args. Mark `pytest.mark.integration`. |
| **Files to change** | **New:** `apps/media/tests/test_save_photo_integration.py` |
| **Acceptance criteria** | Test asserts `generate_thumbnails` is invoked after `save_photo` and thumbnail fields are populated. Failure path sets all three to `None`. |
| **Test command** | `docker compose ... run --rm test apps/media/tests/test_save_photo_integration.py --create-db -v` |

#### C.7 — Add contact service combinatorial edge-case tests
| Field | Value |
|-------|-------|
| **ID** | C.7 |
| **Type** | Test addition |
| **Priority** | Medium (P1) |
| **Gap** | G-04 |
| **Description** | Extend `apps/core/tests/test_contact.py` with combinatorial tests for `can_contact_seller` and `get_seller_for_contact`: (a) banned + consent WITHDRAWN (30-day PII erasure window), (b) DECLINE vs WITHDRAWN consent paths, (c) `get_seller_for_contact` return-tuple contract across all combinations. The existing tests cover individual conditions; this adds the cross-product. Mark `pytest.mark.integration`. |
| **Files to change** | `apps/core/tests/test_contact.py` |
| **Acceptance criteria** | 4+ new parametrized test cases covering combined conditions. All pass with `--create-db`. |
| **Test command** | `docker compose ... run --rm test apps/core/tests/test_contact.py --create-db -v` |

#### C.8 — Add TrustCalculator quality-score truncation tests
| Field | Value |
|-------|-------|
| **ID** | C.8 |
| **Type** | Test addition |
| **Priority** | Low (P2) |
| **Gap** | G-08 |
| **Description** | Extend `apps/trust/tests/test_trust_calculator.py` with edge cases: (a) activity score cap interaction with `_QUALITY_MAX` — 9 published ads (activity = 40 cap) + all non-rejected (quality = 30) → total = 70 → TRUSTED boundary, (b) quality score `int()` truncation — when `rejected/total` produces a fractional `(1-r/t)*30` that truncates, verify the persisted score, (c) response score `round()` to 2 decimal places boundary. Mark `pytest.mark.integration`. |
| **Files to change** | `apps/trust/tests/test_trust_calculator.py` |
| **Acceptance criteria** | 3 new tests asserting truncation/cap behavior at boundaries. Passes with `--create-db`. |
| **Test command** | `docker compose ... run --rm test apps/trust/tests/test_trust_calculator.py --create-db -v` |

#### C.9 — Add TrustCalculator trust-level floor tests (score=0)
| Field | Value |
|-------|-------|
| **ID** | C.9 |
| **Type** | Test addition |
| **Priority** | Low (P2) |
| **Gap** | G-11 |
| **Description** | Extend `apps/trust/tests/test_trust_calculator.py` with: (a) score=0 + `verified_by_admin=True` → `VERIFIED` (the existing `test_verification_bonus_admin_floor` has score≈10, not exactly 0), (b) score=0 + `telegram_premium=True` → `VERIFIED`, (c) score=0 + neither → `UNVERIFIED`. These isolate the floor logic explicitly. Mark `pytest.mark.integration`. |
| **Files to change** | `apps/trust/tests/test_trust_calculator.py` |
| **Acceptance criteria** | 3 new tests, each asserting the floor behavior at exactly score=0. Passes with `--create-db`. |
| **Test command** | `docker compose ... run --rm test apps/trust/tests/test_trust_calculator.py --create-db -v` |

#### C.10 — Add PriorityCalculator boundary tests via public API
| Field | Value |
|-------|-------|
| **ID** | C.10 |
| **Type** | Test addition |
| **Priority** | Low (P2) |
| **Gap** | G-09, G-10 |
| **Description** | Extend `apps/moderation/tests/test_priority.py`: (a) assert `_estimate_confidence` via the public `calculate_priority` return dict at various ad states (always 0.7 — the placeholder constant), (b) add `test_priority_service_boundaries` in `test_priority_service.py` that persists `AdModerationPriority` rows via `PriorityService.calculate_and_save` and asserts the `priority_level` column at score boundaries (0→LOW, 49→LOW, 50→MEDIUM, 79→MEDIUM, 80→HIGH, 100→HIGH). This closes the "private method testing" gap (F-07) and G-10 simultaneously. Mark `pytest.mark.integration`. This task **depends on B.3** being complete. |
| **Files to change** | `apps/moderation/tests/test_priority.py`, `apps/moderation/tests/test_priority_service.py` |
| **Acceptance criteria** | Boundary matrix tested through public API and persisted rows. `grep -n "_get_priority_level\|_estimate_confidence" apps/moderation/tests/test_priority.py` returns 0 (from B.3). Passes with `--create-db`. |
| **Test command** | `docker compose ... run --rm test apps/moderation/tests/test_priority.py apps/moderation/tests/test_priority_service.py --create-db -v` |

> **Dependency**: C.10 must run after B.3 (refactor removes private-method tests, then adds public-API boundary tests).
>
> **Implementation note (C.10)**: The exact boundary literals `49`, `50`, `79`
> are **not reachable** through the public `calculate_priority` API — the
> achievable content scores are `{0,20,40,60,80,100}` (banned_count×20 capped at
> 100) and user scores `{0,15,25,40}`, so totals span only
> `{0,15,20,25,40,60,80,100}`. The boundary test therefore lives in
> `test_priority.py` (`TestPriorityServiceBoundaries.test_persisted_priority_level_at_boundaries`)
> using the achievable values `40→LOW / 60→MEDIUM / 80→HIGH / 100→HIGH`, which
> still bracket the `>=50 MEDIUM` and `>=80 HIGH` thresholds. Do not re-add
> `49/50/79` — they cannot be produced through the public API.

### Phase D: Documentation & Plan Correction (low-effort)

#### D.1 — Fix this plan's own discrepancies (§5 from audit)
| Field | Value |
|-------|-------|
| **ID** | D.1 |
| **Type** | Documentation |
| **Priority** | Low |
| **Finding** | F-09 |
| **Description** | This plan document itself corrects the 4 discrepancies: (1) §1.2 — all 6 markers ARE registered (no "not registered" claim; `e2e` was removed in A.1), (2) §1.4 — CI runs `pytest -m "not seed"` (not "all 934 tests"), (3) §1.1 — references to deleted `tests.py` files removed, (4) §14 T-12 — baseline reset against migrated replacement tests in `test_moderation_views.py` and `test_search_view.py`. No stale references remain. |
| **Files to change** | This document (`test-optimization-plan.md`) — self-correcting |
| **Acceptance criteria** | Document contains no claim that markers are unregistered, no claim that CI runs all 934 tests, no reference to deleted `tests.py` files, and no invalid T-12 baseline. |
| **Test command** | N/A (documentation) |

#### D.2 — Update test-operations documentation
| Field | Value |
|-------|-------|
| **ID** | D.2 |
| **Type** | Documentation |
| **Priority** | Low |
| **Finding** | F-09 |
| **Description** | Update `.ai/context/commands.md` and any `docs/99-agent/` test references to reflect: (a) `--create-db` is required for local runs (not `--reuse-db`), (b) the `e2e` marker no longer exists, (c) root conftest fixtures are the source of truth for `seller`/`user`/`category`/`city` and `create_test_ad`. |
| **Files to change** | `.ai/context/commands.md`, `docs/99-agent/rules.md` (if it references test markers/fixtures) |
| **Acceptance criteria** | Commands doc shows `--create-db` in the PYTEST_OPTS example. No reference to `e2e` marker. Root conftest fixtures documented as canonical. |
| **Test command** | N/A (documentation) |

---

## 4. Execution Order & Rationale

```
Phase A (A.1 → A.2 → A.3) → Phase B (B.1 → B.2 → B.3) → Phase C (C.1 → C.2 → C.3 → ... → C.10) → Phase D (D.1 → D.2)
```

**Rationale for ordering:**

1. **Phase A first (cleanup)** — removes noise and establishes canonical helpers/fixtures *before* writing new tests. If A.2 and A.3 are done first, all Phase C test additions can use `create_test_ad` and root-conftest fixtures directly, avoiding the very duplication we're eliminating. A.1 is independent and removed first as a trivial no-op.

2. **Phase B second (framework convergence)** — once fixtures/helpers are unified (A), migrating `TestCase` → pytest is lower-risk because fewer files diverge in their setup patterns. B.1 is the highest-effort sub-task; doing it before C means new coverage tests (Phase C) are written in the standardized pytest style from the start. B.2 and B.3 are small and independently valuable.

3. **Phase C third (coverage)** — all new tests use the established patterns (`pytest.mark.django_db`, `pytestmark`, `create_test_ad`, root fixtures, `assert` syntax). This is the highest-value work but also the most test code to review, so it comes after the foundation is solid. C.10 explicitly depends on B.3.

4. **Phase D last (documentation)** — plan corrections and doc updates reference the final state of the test suite. Writing them last ensures they match reality. D.1 is self-correcting (this document); D.2 updates operational docs.

**Critical path:** A.2 → A.3 → B.1 → C.1, C.3, C.2 (all P0/P1 coverage). B.3 must precede C.10.

**Parallelizable:** A.1 (standalone). B.2 (standalone new file). C.1–C.10 are independent of each other (except C.10 → B.3) and can be executed in parallel once Phase A is done. D.1 and D.2 are independent of code work and can run anytime.

---

## 5. Task Template

Each task in this plan follows this template:

| Field | Description |
|-------|-------------|
| **ID** | Unique identifier (e.g., `A.1`, `C.3`). Follows `Phase.Letter.Number` convention. |
| **Title** | One-line summary of the work. |
| **Type** | One of: `Cleanup`, `Refactoring`, `Framework migration`, `Test addition`, `Test refactoring`, `Code fix + test`, `Documentation`. |
| **Priority** | `High (P0)`, `Medium (P1)`, `Low (P2)` — mapped from audit gap priority. |
| **Finding** | Audit finding ID (F-xx) or coverage gap ID (G-xx) this task addresses. |
| **Description** | What to do, how, and any key decisions. References specific files, functions, or line anchors (never line numbers in production code — use symbols/contracts). |
| **Files to change** | Exact file paths. `**New:**` prefix for new files. |
| **Depends on** | Other task IDs that must complete first (if any). |
| **Acceptance criteria** | Concrete, verifiable conditions. If a grep pattern is specified, it must return the stated result. |
| **Test command** | Exact Docker Compose command to verify. Always uses `--create-db` to avoid stale-DB state. |

---

## 6. Acceptance Criteria (Overall)

The plan is **complete** when all of the following hold:

1. **No duplicated fixtures** — `grep -rn "^def seller\|^def user\|^def category\|^def city" src/` returns hits only in `src/backend/conftest.py` and the documented async override in `src/telegram_bot/tests/conftest.py`.

2. **No duplicated ad-creation helpers** — `grep -rn "def _make_ad\|def _create_ad" src/` returns 0 results (excluding `test_ad_localization.py`'s in-memory variant, documented as out-of-scope). `create_test_ad` is referenced from ≥15 test files.

3. **Framework convergence** — `grep -rn "from django\.test import.*TestCase\|class.*\(TestCase\)" src/ --include="test_*.py"` returns 0 results (only `SimpleTestCase` remains, which is correct for no-DB tests).

4. **e2e marker removed** — `e2e` does not appear in `pyproject.toml` markers list.

5. **Decorator tests** — `apps/moderation/tests/test_decorators.py` exists with ≥6 parametrized test cases covering all decorator branches.

6. **No private-method testing in priority** — `grep -n "_get_priority_level\|_estimate_confidence" apps/moderation/tests/test_priority.py` returns 0.

7. **Coverage gap closure** — all 11 coverage gaps (G-01 through G-11) have corresponding tests in the specified files. The 4 plan discrepancies (F-09, §5) are corrected.

8. **Full suite passes** — `docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm test --create-db` exits 0.

9. **CI marker filterability works** — `docker compose ... run --rm test -m unit --create-db` and `-m integration --create-db` both select/deselect the correct test sets with no collection errors.

---

## 7. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **B.1 (TestCase→pytest) breaks 14 files** | High — could lose test coverage or introduce subtle assertion failures | Run affected test subset individually with `--create-db` before full suite. Convert `setUpTestData` to fixtures incrementally. Keep `assertEqual`→`assert` conversions mechanical and verified by `-v` output. |
| **A.2 fixture removal breaks test isolation** | Medium — removing local fixtures may cause tests that relied on different values to fail or silently change behavior | Before removing each local fixture, grep for fixture usage within that file. If a fixture overrides root values intentionally (e.g., bot conftest's async `user`), document and keep. Verify per-file with `--collect-only` + targeted run. |
| **A.3 migration introduces constraint violations** | Medium — if `create_test_ad` doesn't match every call site's expected Ad shape | `create_test_ad` accepts `**kwargs` and delegates to `Ad.objects.create`. For tests needing special fields (e.g., `category=None`, `telegram_file_id`), pass via kwargs. Run each file's tests after migration. |
| **C.2 code change to `ad_detail` queryset** | High — production code change in a view | Minimal 1-line change (add `.prefetch_related("user__trust_score")`). Verify with existing `test_detail_context.py` mock assertion (extend it) + new query-count test. Run full ads test suite. |
| **C.6 bot handler integration test is complex** | Medium — `save_photo` is async + in bot package | Mock `generate_thumbnails` at the boundary; test the integration through the bot test conftest (which already handles `sync_to_async` worker threads). Scope to thumbnail-field population, not full handler flow. |
| **`--reuse-db` stale state** | Medium — 527 errors on reuse (pre-existing) | All test commands in this plan use `--create-db`. Document in D.2 that `--reuse-db` is unsupported. |
| **Test DB unavailable on port 5433** | Blocking — all tests fail | Pre-flight: `docker ps --filter "name=mko-bazuna-test-db-"` before running any test command. Start with `docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml up -d db` if missing. |
| **Phase ordering risk (A→B→C)** | Low — if a phase is partially done, tests may be inconsistent | Each phase gates on the previous: do not start Phase B until Phase A passes full suite; do not start Phase C until Phase B passes. |

---

## Appendix A: Task Index

| ID | Title | Phase | Priority | Type | Depends on |
|----|-------|-------|----------|------|-----------|
| A.1 | Remove unused `e2e` marker | A | Low | Cleanup | — |
| A.2 | Adopt root conftest fixtures | A | Medium | Refactoring | A.1 |
| A.3 | Consolidate `_make_ad`/`_create_ad` into `create_test_ad` | A | Medium | Refactoring | A.2 |
| B.1 | Migrate 14 `TestCase` files to pytest-django | B | Medium | Framework migration | A.3 |
| B.2 | Add decorator unit tests | B | Low | Test addition | — |
| B.3 | Refactor `test_priority.py` to public API | B | Low | Test refactoring | — |
| C.1 | Ad model CheckConstraint tests (all 6) | C | High (P0) | Test addition | A.3 |
| C.2 | Fix ad-detail trust-score prefetch (N+1) | C | High (P0) | Code fix + test | — |
| C.3 | Admin-action side-effect tests | C | High (P0) | Test addition | — |
| C.4 | Search sorting tests (DATE_OLD/NEW) | C | Medium (P1) | Test addition | — |
| C.5 | LoginToken edge-case tests | C | Medium (P1) | Test addition | — |
| C.6 | `save_photo → generate_thumbnails` integration test | C | Medium (P1) | Test addition | — |
| C.7 | Contact service combinatorial edge cases | C | Medium (P1) | Test addition | — |
| C.8 | TrustCalculator quality-score truncation tests | C | Low (P2) | Test addition | B.1 (framework) |
| C.9 | TrustCalculator trust-level floor tests (score=0) | C | Low (P2) | Test addition | B.1 (framework) |
| C.10 | PriorityCalculator boundary tests (public API) | C | Low (P2) | Test addition | B.3 |
| D.1 | Correct plan discrepancies | D | Low | Documentation | — |
| D.2 | Update test-operations docs | D | Low | Documentation | — |

---

## Appendix B: Reference — Existing Patterns to Follow

**Pytest-django module marker pattern** (from `test_ad_lifecycle.py`, `test_admin_actions.py`):
```python
pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]
```

**Root conftest fixtures** (from `src/backend/conftest.py`):
- `seller` → `User(telegram_id=900000001, chat_id=900000001, password="x")`
- `user` → `User(telegram_id=900000002, chat_id=900000002, password="x")`
- `category` → `Category(name="Транспорт", slug="transport")`
- `city` → `City(country_code="ME", name="Тестград", region="Central", slug="test-grad")`
- `create_test_ad(user, category, city, *, title, description, status, price, source, **kwargs) -> Ad` — sets status-specific timestamp automatically.

**CI command:** `pytest -m "not seed" -n auto --dist loadscope --tb=short --cov --durations=10`

**Local test command:** `docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm test` (append `-e PYTEST_OPTS="--create-db <path>"` for targeted runs)
