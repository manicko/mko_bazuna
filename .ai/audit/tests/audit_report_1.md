# Test Quality Audit — Step 4: Audit Report

**Date:** 2026-08-26
**Scope:** Full backend (`src/backend/`) + Telegram bot (`src/telegram_bot/`) test suites (~1,124 tests, 88 files)
**Method:** Static analysis + runtime execution (PostgreSQL 18 in Docker, port 5433). Findings cross-referenced with production code, `pyproject.toml` markers, `docs/99-agent/rules.md` (rule #10 StrEnum, rule #33 pytest pattern), and Step 1 research report.
**Prerequisites:** Step 0 (environment), Step 1 (architecture), Step 2 (runtime-verified findings), Step 3 (prioritization) — all completed.

---

## 1. Overview

This report catalogs **12 open findings** (§2.4, §2.7–§2.12, C-09, NEW-1, NEW-2, NEW-4, NEW-5, NEW-7) confirmed open by runtime execution, plus **16 resolved findings** carried over from Step 2. Findings are grouped by root cause. Each row in the tables below maps a finding to its evidence, classification, severity, and disposition.

**Severity legend:** CRITICAL, HIGH, MEDIUM, LOW. **Type legend:** `[TEST-DELETE]` (remove redundant test), `[TEST-UPDATE]` (modify test to follow convention), `[TEST-REWRITE]` (restructure test logic), `[TEST-ADD]` (write missing test), `[BEST-PRACTICE]`, `[DOC-UPDATE]`.

---

## 2. Open Findings (12)

### Group 1 — Convention Violations: tests don't follow project conventions

| FilePath | TestName | Type | Severity | Problem | Recommendation | Status |
|---|---|---|---|---|---|---|
| `apps/core/tests/test_contact.py:138-193` | `TestCheckSellerContactable` (8 tests) | `[TEST-DELETE]` | MEDIUM | Imports and calls private `_check_seller_contactable()` directly (L147,156,161,172,179,186,193). Redundant with public `TestCanContactSellerLogic` (L24-99) which exercises the same logic via `can_contact_seller()`. Private method at `contact.py:27` is internal — only called by public API. | Remove `TestCheckSellerContactable` class + the `_check_seller_contactable` import (L12). Public `TestCanContactSellerLogic` already covers Zone R2. Investigate whether the private predicate should be promoted to public before removal. | OPEN |
| `apps/moderation/tests/test_auto_moderation.py:15-19` | `TestValidateTitleLength`, `TestValidateDescriptionLength`, `TestValidateImageCount`, `TestContainsBannedWords` (17 tests) + L260 | `[TEST-REWRITE]` | MEDIUM | Tests 5 private functions (`_contains_banned_words`, `_validate_title_length`, `_validate_description_length`, `_validate_image_count`, `_validate_max_ads_per_user`) directly. None are imported elsewhere in production — only public `check()` is used (confirmed by grep). Bypasses composition/fall-through behavior. | Rewrite as parametrized end-to-end `TestCheckFunction` cases that invoke the public `moderate()`/`check()` API and assert final `AdStatus` outcomes, preserving the boundary-coverage intent via input combinations rather than private-function calls. | OPEN |
| `apps/core/tests/test_sweep_lock_structure.py:48,74,87` | `test_archive_sweep_lock_inside_transaction`, `test_all_sweeps_lock_inside_transaction` (2 tests) | `[TEST-REWRITE]` | MEDIUM | Uses `inspect.getsource()` to assert string presence/ordering of `"pg_advisory_xact_lock"` and `"with transaction.atomic"`. Verifies source code text, not runtime behavior. Any refactor extracting lock logic into a helper breaks these tests with no behavioral change. | Replace with a behavioral assertion: run each sweep command against a real DB row and verify no concurrent transaction can acquire the same lock (or assert on `transaction.on_commit` registration). Use database-observable behavior, not source text. | OPEN |

### Group 2 — Convention Violations: StrEnum + shared helper rules (rule #10)

| FilePath | TestName | Type | Severity | Problem | Recommendation | Status |
|---|---|---|---|---|---|---|
| `apps/core/tests/test_sweep_commands.py:279,291,313,317,458` | 5 tests across `TestArchiveSweep`, `TestDeleteSweep` | `[TEST-UPDATE]` | LOW | Raw strings for enum model fields: `event_type="search_performed"` (L279,313), `action_type="ban_account"` (L291,317), `action_type="reject"` (L458). Violates rule #10 (StrEnum for all constants). Enums exist: `AnalyticsEventType.SEARCH_PERFORMED` (core/enums.py:68), `ModeratorActionType.BAN_ACCOUNT`/`REJECT` (core/enums.py:145-146). | Replace 5 raw strings with enum references. | OPEN |
| `apps/seed/tests/test_seed.py:275,370,384` | 3 tests in `TestSeedService` | `[TEST-UPDATE]` | LOW | `price_currency="EUR"` raw string in `Ad.objects.create()` calls. Violates rule #10. Should be `CurrencyCode.EUR`. | Replace 3 raw strings with `CurrencyCode.EUR`. | OPEN |
| `apps/core/tests/test_language_end_to_end.py:93` | `test_` (E2E ad creation) | `[TEST-UPDATE]` | LOW | `price_currency="EUR"` raw string. | Use `CurrencyCode.EUR`. | OPEN |
| `apps/ads/tests/test_breadcrumbs_render.py:97` | breadcrumb test | `[TEST-UPDATE]` | LOW | `price_currency="EUR"` raw string. | Use `CurrencyCode.EUR`. | OPEN |
| `apps/ads/tests/test_price_format.py:42` | price formatting test | `[TEST-UPDATE]` | LOW | `price_currency="BAM"` raw string. Should be `CurrencyCode.BAM` (currencies/enums.py:20). | Use `CurrencyCode.BAM`. | OPEN |

### Group 3 — Convention Violations: bypass of centralized `create_test_ad` helper

| FilePath | TestName | Type | Severity | Problem | Recommendation | Status |
|---|---|---|---|---|---|---|
| `apps/ads/tests/test_breadcrumbs_render.py:92` | 5 tests in `TestBreadcrumbsRender` | `[TEST-UPDATE]` | LOW | Direct `Ad.objects.create()` bypasses `create_test_ad` (conftest.py:78) and `_set_status_timestamp` (conftest.py:163). Timestamps manually set at L104 (`published_at`). Bypasses centralized CheckConstraint enforcement (ads/models.py:314–341). | Replace `Ad.objects.create()` with `create_test_ad(..., status=AdStatus.PUBLISHED)`. | OPEN |
| `apps/users/tests/test_deletion.py:143,153,261,321` | 4 tests across `TestDeleteAccount` | `[TEST-UPDATE]` | LOW | 4 direct `Ad.objects.create()` calls bypassing helper. Timestamps manually set (all currently correct). | Use `create_test_ad` for the 2 PUBLISHED-status ads (L143, 153); verify DRAFT/ON_MODERATION calls (L261, 321) set no extra timestamp. | OPEN |
| `apps/core/tests/test_language_end_to_end.py:81` | E2E test | `[TEST-UPDATE]` | LOW | Direct `Ad.objects.create()`. | Use `create_test_ad(..., status=AdStatus.PUBLISHED)`. | OPEN |
| `apps/search/tests/test_autocomplete.py:592,619,642,673` | 4 tests in `TestAutocomplete` | `[TEST-UPDATE]` | LOW | 4 direct `Ad.objects.create()` calls. All PUBLISHED, `published_at` manually set to `timezone.now()`. | Replace with `create_test_ad`. | OPEN |
| `apps/seed/tests/test_seed.py:270,365,379` | 3 tests in `TestSeedService` | `[TEST-UPDATE]` | LOW | 3 direct `Ad.objects.create()` calls (2 PUBLISHED, 1 DRAFT). Bypasses helper; also uses `price_currency="EUR"` raw string (§2.8 overlap). | Replace with `create_test_ad`. Fixes both §2.8 and §2.9 for these lines. | OPEN |
| `apps/trust/tests/test_trust_prefetch.py`, `apps/core/tests/test_context_processors.py`, `apps/core/tests/test_language_middleware.py`, `apps/core/tests/test_language_locale.py`, `apps/ads/tests/test_listings_context.py`, `apps/ads/tests/test_i18n_completeness.py`, `apps/ads/tests/test_i18n_pipeline.py`, `apps/ads/tests/test_adimage_thumbnail_urls.py`, `apps/ads/tests/test_ad_localization.py`, `apps/core/tests/test_templates.py`, `apps/core/tests/test_csp_report.py`, `apps/core/tests/test_preferred_city_middleware.py`, `apps/search/tests/test_autocomplete_template.py`, `apps/ads/tests/test_detail_context.py`, `config/settings/tests/test_settings_secrets.py` | 15 test classes (100+ `self.assert*` calls) | `[TEST-UPDATE]` | LOW | 15 files use `from django.test import SimpleTestCase` + `class TestX(SimpleTestCase):` with `self.assertEqual`/`self.assertIn` instead of plain `class TestX:` + `assert`. Violates rules.md §33. All pass (127 passed + 7 subtests). | Convert to plain `class TestX:` + remove `SimpleTestCase` import; replace `self.assert*` with built-ins. | OPEN |

### Group 4 — Duplicate coverage & test isolation fragility (bot login tests)

| FilePath | TestName | Type | Severity | Problem | Recommendation | Status |
|---|---|---|---|---|---|---|
| `telegram_bot/tests/test_claim_login_token.py` (7 tests) + `telegram_bot/tests/test_login_claim.py` (5 tests) | `test_claim_valid_token`, `test_reject_expired_token`, `test_reject_already_claimed_token`, `test_fresh_unclaimed_token`, `test_reclaim_blocked`, etc. (3 overlapping scenarios) | `[TEST-DELETE]` / `[TEST-UPDATE]` | HIGH | Both files test `handle_login_orm` with 3 overlapping scenarios (valid, expired, already-claimed). `test_login_claim.py` uses a **fixed** `token_hash` fixture — `hashlib.sha256("a"*32)` (L30) — while `test_claim_login_token.py` uses a random `login_token_factory` (`secrets.token_urlsafe()`, conftest.py:117). Under xdist: 12 pass in 7.86s. **Without xdist (`-p no:xdist`): 3 failures + 6 errors** — `DeadlockDetected` during flush teardown → `IntegrityError: duplicate key` on the fixed `token_hash`. Tests are `concurrent`/`transaction=True` marked but only pass under xdist. | Merge the two files: keep `login_token_factory` (random hashes); preserve `test_login_claim.py`'s unique `consumed_at` replay test. Remove the fixed `token_hash` fixture. This eliminates duplicate coverage and makes the suite pass without xdist. | OPEN |

### Group 5 — Coverage gaps

| FilePath | TestName | Type | Severity | Problem | Recommendation | Status |
|---|---|---|---|---|---|---|
| `telegram_bot/handlers/ad_create.py:961` (def) / `:704` (call) / `:1175` (call) | — (no test covers this chain) | `[TEST-ADD]` | MEDIUM | No integration test for `save_photo()` → disk write → `generate_thumbnails()` (defined at `apps/media/services/thumbnails.py:40`, called at `ad_create.py:1175`) → `AdImage` field population. `telegram_bot/tests/test_save_photo_integration.py:85` bypasses `save_photo` — writes bytes manually to `tmp_path`. `test_thumbnails.py` (11 tests) unit-tests `generate_thumbnails` well, but the full chain through `save_photo` is untested. | Add an integration test that calls `save_photo(photo_bytes)` for real, then invokes the thumbnail pipeline, and asserts `AdImage.thumbnail_small/medium/large` are populated. Use a real (small) JPEG. | OPEN |
| — (no test file) | 4 currency tests: `test_eur_preserves_amount` (L28), `test_bam_normalized_by_seeded_rate` (L33), `test_rsd_normalized_by_seeded_rate` (L38), `test_recompute_corrects_stale_normalized_value` | `[TEST-UPDATE]` | MEDIUM | Tests assert hardcoded rate values (e.g. `100 BAM = 51.20 EUR`) relying on migration-seeded `ExchangeRate` data (`currencies/migrations/0001_initial.py`). Under `--reuse-db` with a stale DB volume, the seeded rows are missing → `ExchangeRateNotFoundError`. All 4 pass with `--create-db`. Production reads via `PriceNormalizer._get_current_rate` (price_normalizer.py:92-97). | Add an autouse fixture in the currencies test module that creates its own `ExchangeRate` rows, decoupling from migration seed data. | OPEN |
| `apps/currencies/tests/test_price_normalizer.py` | (same 4 tests above) | `[TEST-UPDATE]` | HIGH | See Group 5 row above — fails under `--reuse-db`, the CI default. The fixed project uses `--reuse-db` via Docker entrypoint. | Same fix. Severity raised to HIGH because CI default uses `--reuse-db`. | OPEN |

### Group 6 — Test infrastructure & maintainability

| FilePath | TestName | Type | Severity | Problem | Recommendation | Status |
|---|---|---|---|---|---|---|
| `apps/ads/tests/test_listings_context.py`, `apps/ads/tests/test_detail_context.py` | All tests in both files (20+ `CacheKeyWarning`) | `[BEST-PRACTICE]` | LOW | `MagicMock` objects leak into cache keys. `test_listings_context.py` patches `apps.ads.views.listings.Category` (L97, L217) — the mock's `.id` repr (`MagicMock name='Category.objects.filter...'`) is interpolated into a `cache.set()` key by the view. `test_detail_context.py` passes `MagicMock` `ad` objects (L72, L111, L122). Produces unreadable `CacheKeyWarning` output masking real cache-key bugs. | Use real `Category`/`Ad` model instances (via `create_test_ad`) instead of `MagicMock` where the cache path is exercised. Or patch only the specific queryset, returning a real model instance. | OPEN |
| `apps/ads/tests/test_breadcrumbs_render.py:45-58` | `_load_catalog` fixture (autouse, function scope) | `[BEST-PRACTICE]` | LOW | Function-scoped fixture calls `load_catalog()` + `City.objects.create()` for every test — ~3.6s setup per test. Class/session-scoped fixture would save ~18s across the 5-test `TestBreadcrumbsRender` class (4 of 7 slowest setups are from this class). | Change `@pytest.fixture(autouse=True)` to `@pytest.fixture(autouse=True, scope="class")` (or `session`); ensure `load_catalog` is idempotent. | OPEN |
| `docs/99-agent/` planning docs + audit compilation | references to `test_media_security.py` | `[DOC-UPDATE]` | LOW | Documentation (and the audit compilation) references `apps/media/tests/test_media_security.py`, but the file is at `apps/ads/tests/test_media_security.py` (verified by filesystem check). 28-test file is correct; only the doc path reference is stale. | Update doc references from `apps/media/tests/` → `apps/ads/tests/`. | OPEN |

---

## 3. Resolved Findings (16)

All 16 findings below were confirmed resolved by runtime execution in Step 2. No re-implementation was performed by the auditor.

| Finding ID | Type | File (location) | Evidence |
|---|---|---|---|
| F-01 | Shadowed `tests.py` | Deleted; migrated to `tests/` packages | `apps/moderation/tests.py` + `apps/search/tests.py` removed |
| §2.1 | Duplicated fixtures | RESOLVED | Root conftest provides `seller`/`user`/`category`/`city`; 0 local redefinitions in backend apps |
| §2.2 | Duplicated `_make_ad`/`_create_ad` helpers | RESOLVED | 13/14 files now import `create_test_ad`; 1 stub remains in `test_ad_localization.py` |
| §2.3 | `TestCase` usage | RESOLVED | 0 `import TestCase` / `class Test.*TestCase` matches (grep) |
| §2.5 | Missing decorator tests | RESOLVED | `test_decorators.py` (9 unit tests, `RequestFactory`) |
| §2.6 | `e2e` marker registered but unused | RESOLVED | `e2e` absent from `pyproject.toml` markers (L163-172); 0 `@pytest.mark.e2e` uses (grep) — already removed between compilation and session |
| C-01 | Ad check constraints | RESOLVED | `test_ad_constraints.py` (7 tests, all 6 CheckConstraints) |
| C-02 | Trust quality-score truncation | RESOLVED | `TestQualityScoreTruncation` in `test_trust_calculator.py` |
| C-03 | PriorityCalculator boundaries | RESOLVED | `TestPriorityLevelBoundaries` + `TestConfidenceScore` in `test_priority.py` |
| C-04 | Contact service edge cases | RESOLVED | `TestContactCombinatorial` (9 parametrized) + `TestCanContactSellerLogic` (9 tests) in `test_contact.py` |
| C-05 | Search sorting DATE_OLD/DATE_NEW | RESOLVED | `test_listings_sort.py` (4 tests) |
| C-06 | Ad detail trust N+1 prefetch | RESOLVED | `listings.py:61` eagerly prefetches `user__trust_score`; guard test in `test_ad_detail_queries.py` |
| C-07 | `approve_ad` signal chain | RESOLVED | `test_approve_ad_side_effects.py` (6 tests) |
| C-08 | LoginToken HMAC edge cases | RESOLVED | `TestLoginTokenSecurity` in `test_login.py` (5 tests) |
| C-10 | PriorityCalculator boundary edges | RESOLVED | `TestPriorityServiceBoundaries` (parametrized 6 cases) |
| C-11 | Trust level floor logic | RESOLVED | `TestTrustLevelFloor` in `test_trust_calculator.py` (3 tests) |

---

## 4. Summary Statistics

| Metric | Count |
|---|---|
| Total findings this report (open + resolved) | 28 |
| **Open findings** | **12** |
| — `[TEST-DELETE]` / `[TEST-REWRITE]` | 3 (§2.4, §2.10, §2.11) |
| — `[TEST-UPDATE]` | 6 (§2.7, §2.8, §2.9, §2.12, NEW-1, NEW-4) |
| — `[TEST-ADD]` / `[BEST-PRACTICE]` | 3 (C-09, NEW-2, NEW-5) |
| — `[DOC-UPDATE]` | 1 (NEW-7) |
| Resolved findings carried from Step 2 | 16 |
| Severity: CRITICAL | 0 |
| Severity: HIGH | 2 (NEW-2 bot isolation, NEW-1 CI currency fragility) |
| Severity: MEDIUM | 3 (§2.4, §2.10, §2.11) |
| Severity: LOW | 7 |
| Severity: INFO / doc | 1 (NEW-7) |

---

## 5. Validation Matrix

Runtime verification status from Step 2 (`--reuse-db`, xdist unless noted). All open findings were confirmed to **pass at runtime** (i.e., tests are green but architecturally flawed) **unless** the "Runtime" column notes isolation-specific failures.

| Finding ID | Severity | Classification | Runtime Status | Repro Command | Notes |
|---|---|---|---|---|---|
| §2.4 | MEDIUM | `[TEST-DELETE]` | ✅ PASS (66-test batch) | `pytest test_contact.py` | 8 direct calls to `_check_seller_contactable`; redundant with public tests |
| §2.7 | LOW | `[TEST-UPDATE]` | ✅ PASS (127+7 subtests, no xdist) | `pytest -p no:xdist -m 'not seed' <15 files>` | 15 files use `SimpleTestCase` + `self.assert*` |
| §2.8 | LOW | `[TEST-UPDATE]` | ✅ PASS | `pytest test_sweep_commands.py` | 5 raw strings + 4 files with `price_currency` raw strings |
| §2.9 | LOW | `[TEST-UPDATE]` | ✅ PASS | `pytest <5 files>` | 5 files bypass `create_test_ad`; timestamps currently correct |
| §2.10 | MEDIUM | `[TEST-REWRITE]` | ✅ PASS (66-test batch) | `pytest test_sweep_lock_structure.py` | 2 tests; `inspect.getsource()` at L48,74,87 |
| §2.11 | MEDIUM | `[TEST-REWRITE]` | ✅ PASS (66-test batch) | `pytest test_auto_moderation.py` | 17 tests; 5 private functions tested directly |
| §2.12 | LOW (HIGH runtime) | `[TEST-DELETE/UPDATE]` | ⚠️ 12 pass (xdist); ❌ 3 fail + 6 errors (no xdist) | `pytest test_claim_login_token.py test_login_claim.py` / `pytest -p no:xdist ...` | Fixed `token_hash` fixture collides on deadlock-cleanup failure |
| C-09 | MEDIUM | `[TEST-ADD]` | ✅ N/A (coverage gap) | — | `save_photo`→disk→`generate_thumbnails` chain untested |
| NEW-1 | HIGH | `[TEST-UPDATE]` | ❌ 4 fail (`--reuse-db`); ✅ pass (`--create-db`) | `pytest test_price_normalizer.py` / `pytest --create-db ...` | Stale-DB; tests assert hardcoded seeded rates |
| NEW-2 | HIGH | (see §2.12) | ❌ 3 fail + 6 errors (no xdist) | `pytest -p no:xdist test_login_claim.py` | Same root cause as §2.12 |
| NEW-4 | LOW | `[BEST-PRACTICE]` | ✅ PASS (20+ warnings) | `pytest test_listings_context.py test_detail_context.py` | `MagicMock` leaks into cache keys |
| NEW-5 | LOW | `[BEST-PRACTICE]` | ✅ PASS (slow) | `pytest test_breadcrumbs_render.py` | `_load_catalog` function-scoped, ~3.6s/test setup |
| NEW-7 | LOW | `[DOC-UPDATE]` | ✅ N/A (doc issue) | — | `test_media_security.py` at `apps/ads/tests/` not `apps/media/tests/` |

---

## 6. Risk Prioritization (for follow-up work)

**Priority 1 — Correctness / isolation (HIGH):**
- §2.12 / NEW-2: Bot login tests pass only under xdist. CI or isolated runs produce false failures. Merge the two files and adopt the `login_token_factory` pattern.
- NEW-1: Currency tests fail under the CI-default `--reuse-db`. Adding an autouse fixture for `ExchangeRate` is a small, high-ROI fix.

**Priority 2 — Maintainability (MEDIUM):**
- §2.10: `inspect.getsource()` tests are brittle to any refactor. Behavioral replacement is the recommended path.
- §2.11: Private auto-moderation functions tested directly. Rewrite as end-to-end `check()` assertions to preserve boundary coverage while testing through the public API.
- C-09: Add the `save_photo → thumbnails` integration test to close the pipeline gap.

**Priority 3 — Conventions / conventions debt (LOW):**
- §2.7 (15 `SimpleTestCase` files), §2.8 (9 raw string sites), §2.9 (5 files, 11 call sites bypassing `create_test_ad`): bulk but mechanical. Suitable for a single PR.
- §2.4: Delete redundant `TestCheckSellerContactable` (or investigate intent).
- NEW-4, NEW-5, NEW-7: warning hygiene and fixture scope tuning; doc path correction.

---

## 7. Environment & Commands

All runtime verification used the documented Docker test setup:
```powershell
$env:COMPOSE_FILE = "docker-compose.yml;docker-compose.test.yml"
$env:COMPOSE_PROJECT_NAME = "mko-bazuna-test"
docker compose run --rm --entrypoint bash test -c "uv run pytest --reuse-db -q <PATH>"
docker compose run --rm --entrypoint bash test -c "uv run pytest --create-db -q <PATH>"          # fresh schema
docker compose run --rm --entrypoint bash test -c "uv run pytest --reuse-db -q -p no:xdist <PATH>"  # without xdist
```
Test DB: PostgreSQL 18 in Docker on port 5433. Production stack: Python 3.14, Django 5.2 LTS, aiogram 3.x, native PostgreSQL FTS.

*(End of report)*
