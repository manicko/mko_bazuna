# Test Quality Audit — Step 2: Audit Test Quality

**Date:** 2026-08-26
**Scope:** Full backend (`src/backend/`) + bot (`src/telegram_bot/`) test suites, config, production code
**Method:** Full fast-gate sweep with runtime execution + per-finding file:line evidence
**DB:** PostgreSQL 18 in Docker (port 5433), `--reuse-db` (stale volume) + `--create-db` verification

---

## 1. Test Sweep Results

### 1.1 Full Fast-Gate Sweep (`-m "not seed"`, xdist, `--reuse-db`)

| Metric | Count |
|--------|-------|
| Tests collected (non-seed) | ~890 |
| Passed | ~886 |
| Failed | 4 |
| Errors | 0 |
| Skipped | 0 |

**4 failures — all in `apps/currencies/tests/`:**

| # | Test | Error |
|---|------|-------|
| 1 | `test_price_normalizer.py::TestPriceNormalizer::test_eur_preserves_amount` | `ExchangeRateNotFoundError: No current exchange rate found for currency EUR` |
| 2 | `test_price_normalizer.py::TestPriceNormalizer::test_bam_normalized_by_seeded_rate` | `ExchangeRateNotFoundError: No current exchange rate found for currency BAM` |
| 3 | `test_price_normalizer.py::TestPriceNormalizer::test_rsd_normalized_by_seeded_rate` | `ExchangeRateNotFoundError: No current exchange rate found for currency RSD` |
| 4 | `test_recompute_command.py::TestRecomputeNormalizedPrices::test_recompute_corrects_stale_normalized_value` | `AssertionError: assert Decimal('999.0000') == Decimal('51.2000')` (command logs: "Skipping ad: no current rate for BAM") |

**Root cause:** Stale `--reuse-db` volume. The `currencies` migration `0001_initial.py` seeds EUR=1.0, BAM=0.512, RSD=0.0105 via `RunPython(seed_initial_rates)`. With `--reuse-db`, the test DB volume persists from a prior state where these rows are missing or were flushed. **Verified: all 4 pass with `--create-db`** (7 passed in 12s). This is a stale-DB environment issue, but the test design (relying on migration-seeded data rather than a fixture) is fragile.

### 1.2 Slow Tests (Top 10, `--reuse-db`, xdist)

| Duration | Test | Phase |
|----------|------|-------|
| 4.37s | `test_seed.py::TestImageGenerator::test_image_keys_have_correct_format` | call |
| 3.74s | `test_breadcrumbs_render.py::TestBreadcrumbsRender::test_breadcrumb_empty_on_home` | setup |
| 3.72s | `test_submenu.py::TestExpandButtons::test_expand_button_present_for_category_with_children` | setup |
| 3.66s | `test_submenu.py::TestExpandButtons::test_expand_button_absent_for_leaf_category` | setup |
| 3.64s | `test_breadcrumbs_render.py::TestBreadcrumbsRender::test_breadcrumb_on_ad_detail` | setup |
| 3.60s | `test_breadcrumbs_render.py::TestBreadcrumbsRender::test_breadcrumb_shows_root_category` | setup |
| 3.59s | `test_breadcrumbs_render.py::TestBreadcrumbsRender::test_breadcrumb_shows_ancestor_chain` | setup |
| 2.17s | `test_ad_constraints.py::TestStatusTimestampConstraints::test_bulk_update_to_status_without_timestamp_raises[published]` | setup |
| 1.48s | `test_settings_secrets.py::SettingsSecretsTests::test_django_secret_key_required` | call |
| 1.44s | `test_settings_secrets.py::SettingsSecretsTests::test_bot_token_required_in_production` | call |

**No test exceeds 5 seconds** (individually). However, `test_breadcrumbs_render.py` has ~3.6s **setup** time per test due to the `_load_catalog` autouse fixture (line 45-58) which calls `load_catalog()` + `City.objects.create()` for every test — a class/session-scoped fixture would reduce this overhead.

### 1.3 Warnings Summary

- `CacheKeyWarning`: 20+ instances from `test_listings_context.py` and `test_detail_context.py` — `MagicMock` objects leak into cache keys (`":1:lookup:resolved_purposes:<MagicMock ...>"`). Mocks are being passed to functions that cache results.
- `UserWarning: No directory at: /app/staticfiles/` — from CSP report tests (`test_csp_report.py`); staticfiles dir absent in test container.
- `RuntimeWarning: DateTimeField User.consent_given_at received a naive datetime` — from `test_seed.py::TestUserGenerator::test_bulk_create_works`; seed data uses naive datetimes despite timezone support.
- 0 collection errors, 0 unknown markers, 0 skipped tests.

---

## 2. Per-Finding Verification (§2.4–§2.12, C-09)

### §2.4 — Private Method Testing (`_check_seller_contactable`)

**Status: CONFIRMED OPEN**

- `src/backend/apps/core/tests/test_contact.py:12` imports `_check_seller_contactable` directly:
  ```python
  from apps.core.services.contact import (
      _check_seller_contactable,  # line 12
      can_contact_seller,
      ...
  )
  ```
- `TestCheckSellerContactable` class (lines 138–193) calls `_check_seller_contactable` directly 8 times (lines 147, 156, 161, 172, 179, 186, 193).
- 6 additional test functions in `TestCanContactSellerLogic` (lines 24–99) call the public `can_contact_seller()` — these are fine.
- **Runtime:** Tests pass (included in 66-test batch: `test_contact.py` + `test_sweep_lock_structure.py` + `test_auto_moderation.py` → **66 passed in 11.77s**).
- `create_test_ad` is used correctly throughout (not bypassed).

> Note: The Step 1 report correctly identified this. The private method is the core Zone R2 predicate, so testing it directly is a design choice, but it violates the "test public API, not private methods" convention.

### §2.6 — `e2e` Marker Registered but Unused

**Status: RESOLVED (Step 1 report INACCURATE)**

- Grep for `e2e` in all `*.toml` files → **0 matches**. The `e2e` marker is **NOT** registered in `pyproject.toml:163-172` (current markers: `unit`, `integration`, `seed`, `settings`, `concurrent`, `slow`, `real_images`, `xdist_group`).
- Grep for `@pytest.mark.e2e` in `src/backend/` and `src/telegram_bot/` → **0 matches** (confirmed in sweep).
- The Step 1 report claims "`pyproject.toml:167` registers `e2e`", but line 167 is `"seed: marks tests that invoke call_command('seed')..."`. The `e2e` marker was **already removed** between the audit compilation (8/20–8/21) and the current session.
- **Conclusion:** §2.6 is fully resolved. No action needed.

### §2.7 — `SimpleTestCase` Usage (Convention Violation)

**Status: CONFIRMED OPEN (15 files, not 9)**

All 15 files use `from django.test import SimpleTestCase` and `class TestX(SimpleTestCase):` with `self.assert*` assertions instead of plain `class TestX:` + `assert`:

| File | Classes | `self.assert` count |
|------|---------|---------------------|
| `apps/trust/tests/test_trust_prefetch.py` | `TestTrustBadgePrefetchNoQuery` (L24) | 3 |
| `apps/core/tests/test_context_processors.py` | `LanguageContextProcessorTests` (L22), `HeaderContextProcessorTests` (L54) | — |
| `apps/core/tests/test_language_middleware.py` | `LanguagePreMiddlewareTests` (L44) | 7+ |
| `apps/core/tests/test_language_locale.py` | `LanguageLocaleTests` (L17), `LanguageLocaleFromCodeTests` (L33) | — |
| `apps/ads/tests/test_listings_context.py` | `TestListingsFilterContext` (L66) | — |
| `apps/ads/tests/test_i18n_completeness.py` | `TestI18nCompleteness` (L146) | — |
| `apps/ads/tests/test_i18n_pipeline.py` | `TestI18nPipeline` (L90), `TestComponentTagFilter` (L133) | — |
| `apps/ads/tests/test_adimage_thumbnail_urls.py` | `TestAdImageThumbnailUrls` (L22) | — |
| `apps/ads/tests/test_ad_localization.py` | `TestAdGetTitle` (L42, 30+ `self.assertEqual`), `TestAdGetDescription` (L105) | 30+ |
| `apps/core/tests/test_templates.py` | `TestConsentBannerGuardInTemplates` (L43) | 4 |
| `apps/core/tests/test_csp_report.py` | `CspReportViewTests` (L23) | 3 |
| `apps/core/tests/test_preferred_city_middleware.py` | `PreferredCityMiddlewareTests` (L46) | — |
| `apps/search/tests/test_autocomplete_template.py` | `TestAutocompleteTemplate` (L23), `TestCatalogMenuAccordionTemplate` (L82) | 30+ |
| `apps/ads/tests/test_detail_context.py` | `TestAdDetailBotUsernameContext` (L26), `TestBreadcrumbEllipsisTemplate` (L151) | 8 |
| `config/settings/tests/test_settings_secrets.py` | `SettingsSecretsTests` (L26) | 4 |

Grep for `self.assert` in `src/backend/` → 100+ matches (truncated), confirming the convention violation across all 15 files.

**Runtime:** All 15 files pass — **127 passed, 7 subtests passed in 11.78s** (run as single batch without xdist).

> Note: The audit compilation §2.7 originally listed 9 files. The Step 1 report correctly updated to 15. `test_ad_localization.py` was flagged as "intentional in-memory exception" in the compilation but is still listed in the 15-file count — it uses `SimpleTestCase` with `self.assertEqual` and should be converted.

### §2.8 — Raw Strings for Enum Fields

**Status: CONFIRMED OPEN (EXTENDED — more files than reported)**

**In `test_sweep_commands.py` (5 raw strings):**

| Line | Field | Raw string | Correct enum |
|------|-------|-----------|-------------|
| 279 | `event_type` | `"search_performed"` | `AnalyticsEventType.SEARCH_PERFORMED` (`core/enums.py:68`) |
| 291 | `action_type` | `"ban_account"` | `ModeratorActionType.BAN_ACCOUNT` (`core/enums.py:146`) |
| 313 | `event_type` | `"search_performed"` | `AnalyticsEventType.SEARCH_PERFORMED` |
| 317 | `action_type` | `"ban_account"` | `ModeratorActionType.BAN_ACCOUNT` |
| 458 | `action_type` | `"reject"` | `ModeratorActionType.REJECT` (`core/enums.py:145`) |

> Note: The Step 1 report claimed the string was `"search_perseformed"` (typo). The actual code has `"search_performed"` (correct spelling). The audit compilation §2.8 listed `test_deletion.py` as using `action_type` raw strings — **INACCURATE**: grep for `action_type|event_type` in `test_deletion.py` → 0 matches. The compilation also referenced a `DeletionReason` enum that **does not exist** in the codebase.

**Additional §2.8-type issues found (4 more files with raw `price_currency` strings):**

| File | Line | Raw string | Correct enum |
|------|------|-----------|-------------|
| `apps/seed/tests/test_seed.py` | 275, 370, 384 | `price_currency="EUR"` | `CurrencyCode.EUR` |
| `apps/core/tests/test_language_end_to_end.py` | 93 | `price_currency="EUR"` | `CurrencyCode.EUR` |
| `apps/ads/tests/test_breadcrumbs_render.py` | 97 | `price_currency="EUR"` | `CurrencyCode.EUR` |
| `apps/ads/tests/test_price_format.py` | 42 | `price_currency="BAM"` | `CurrencyCode.BAM` |

These are `Ad` model field values, not just test assertions — using raw strings for `price_currency` violates rule #10 (StrEnum for all constants). The audit compilation §2.9 listed `test_breadcrumbs_render.py` for `Ad.objects.create` but did NOT flag its `price_currency="EUR"` raw string.

### §2.9 — Direct `Ad.objects.create()` Instead of Shared Helper

**Status: CONFIRMED OPEN (5 files, not 2)**

The audit compilation listed only 2 files (`test_breadcrumbs_render.py`, `test_deletion.py`). The Step 1 report corrected to 5. Grep confirms 5 test files + `conftest.py` (the helper itself):

| File | Lines | Status used | Timestamp set? |
|------|-------|-------------|----------------|
| `apps/ads/tests/test_breadcrumbs_render.py` | 92 | PUBLISHED | `published_at="2024-01-01..."` (L104) ✓ |
| `apps/users/tests/test_deletion.py` | 143, 153, 261, 321 | PUBLISHED, ON_MODERATION, DRAFT, DRAFT | 143✓ 153✓(none req'd) 261✓(none req'd) 321✓(none req'd) |
| `apps/core/tests/test_language_end_to_end.py` | 81 | PUBLISHED | `published_at=timezone.now()` (L97) ✓ |
| `apps/search/tests/test_autocomplete.py` | 592, 619, 642, 673 | PUBLISHED (all) | All set `published_at=timezone.now()` ✓ |
| `apps/seed/tests/test_seed.py` | 270, 365, 379 | PUBLISHED, PUBLISHED, DRAFT | 270✓ 365✓ 379✓(none req'd) |

**Constraint-violation risk:** All currently-set timestamps are correct (no immediate violations). However, the `create_test_ad` helper (conftest.py:78-117) centralizes this logic via `_set_status_timestamp` (conftest.py:163). Bypassing it is fragile: a future edit could omit a required timestamp, causing silent `IntegrityError` or inconsistent test data. Several calls also use `price_currency="EUR"` as a raw string (§2.8 extension).

### §2.10 — `inspect.getsource()` Fragile Structure Inspection

**Status: CONFIRMED OPEN**

- `src/backend/apps/core/tests/test_sweep_lock_structure.py` (2 tests, `pytestmark = [pytest.mark.unit]`):
  - `test_archive_sweep_lock_inside_transaction` (L41): calls `inspect.getsource(archive_sweep.Command.handle)` at line 48, asserts `"pg_advisory_xact_lock"` and `"transaction.atomic"` string ordering.
  - `test_all_sweeps_lock_inside_transaction` (L57): iterates 11 modules, calls `inspect.getsource(mod.Command.handle)` at line 74, asserts string ordering for each. Also inspects `send_alerts.Command.handle` source at line 87.
- **Runtime:** 2 tests pass (included in 66-test batch).
- **Risk:** Any refactor that extracts the lock logic into a helper function would break these tests without any behavioral change. The tests assert on source code text, not runtime behavior.

### §2.11 — Private Auto-Moderation Function Testing

**Status: CONFIRMED OPEN**

- `src/backend/apps/moderation/tests/test_auto_moderation.py` imports 5 private functions (lines 15–19):
  - `_contains_banned_words` → tested in `TestContainsBannedWords` (L132–158, 5 tests)
  - `_validate_title_length` → tested in `TestValidateTitleLength` (L26–54, 5 tests)
  - `_validate_description_length` → tested in `TestValidateDescriptionLength` (L57–80, 4 tests)
  - `_validate_image_count` → tested in `TestValidateImageCount` (L83–129, 3 tests)
  - `_validate_max_ads_per_user` → called directly at L260 in `TestCheckFunction.test_failed_ad_not_counted_in_active_limit`
- The public `check()` function IS tested in `TestCheckFunction` (L182–260, 2 tests) — that part is acceptable.
- **Runtime:** All tests pass (included in 66-test batch).
- **Missing coverage:** No test exercises `AutoModerator.moderate()` end-to-end or tests `_validate_max_ads_per_user` as a standalone (boundary edges). The private functions test the validation rules but not their composition through the public API.

### §2.12 — Duplicate Bot Login Token Tests

**Status: CONFIRMED OPEN (with fragility caveat)**

**Overlap confirmed** — both files test `handle_login_orm`:

| `test_claim_login_token.py` (7 tests) | `test_login_claim.py` (5 tests) |
|---|---|
| `test_claim_valid_token` | (no exact match — uses different fixture approach) |
| `test_claim_sets_telegram_id_on_token` | (unique) |
| `test_reject_expired_token` ← overlap | `test_expired_token_rejected` ← overlap |
| `test_reject_already_claimed_token` ← overlap | `test_claimed_token_rejected` ← overlap |
| `test_creates_user_on_first_claim` | (no exact match) |
| `test_returns_existing_user_on_second_login` | (unique) |
| `test_invalid_token_hash_returns_none` | (unique) |
| | `test_fresh_unclaimed_token` ← overlap with `test_claim_valid_token` |
| | `test_reclaim_blocked` ← overlap |
| | `test_consumed_token_rejected` ← unique (consumed_at set) |

**Key differences:**
- `test_claim_login_token.py` uses a `login_token_factory` fixture (conftest.py:117) that generates random token hashes via `secrets.token_urlsafe()`.
- `test_login_claim.py` uses a fixed `token_hash` fixture (`hashlib.sha256("a" * 32)`) — a source of test-isolation fragility.
- `test_login_claim.py` tests `consumed_at` replay protection (web-phase claim); `test_claim_login_token.py` does not.
- `test_claim_login_token.py` tests invalid hash + existing user return; `test_login_claim.py` does not.

**Runtime (with xdist, default):** **12 passed in 7.86s** — all tests pass.

**Runtime (without xdist, `-p no:xdist`):** **3 failed, 9 passed, 6 errors** — all `concurrent`/`transaction=True` tests produce `DeadlockDetected` during `_fixture_teardown` (flush) and `IntegrityError: duplicate key value violates unique constraint` on `LoginToken.token_hash`. The fixed `token_hash` fixture in `test_login_claim.py` collides with stale data when the flush deadlocks and fails to clean up.

> This is a **test isolation fragility**: these 12 tests only pass under xdist. Running them in isolation (e.g., `pytest -p no:xdist test_login_claim.py`) or in CI without xdist produces false failures.

### C-09 — Thumbnail Generation Integration

**Status: CONFIRMED OPEN (gap persists)**

**Current test coverage:**
- `apps/media/tests/test_thumbnails.py` (11 tests): Unit tests for `ThumbnailService.generate_thumbnails` — covers all 3 sizes, aspect ratio, progressive JPEG, collision, invalid input. Well tested.
- `apps/ads/tests/test_media_security.py` (28 tests, **note: path is `apps/ads/tests/`, not `apps/media/tests/`**): `TestExifStripping` (5 tests) unit-tests `strip_photo_exif` in isolation. `TestMediaGateThumbnailResolution` (6 tests) tests thumbnail URL resolution via the media view (not generation). Does NOT test save_photo → thumbnails.
- `apps/media/tests/test_save_photo_exif.py` (1 test): Tests `save_photo` → EXIF stripping on disk. Does NOT verify thumbnails.
- `telegram_bot/tests/test_save_photo_integration.py` (2 tests): Tests `update_ad_and_moderate` → `generate_thumbnails` → `AdImage.thumbnail_*`. **BYPASSES `save_photo`** — manually writes bytes to `tmp_path` at line 85: `(tmp_path / storage_key).write_bytes(photo_bytes)`.

**The untested chain:**
```
save_photo() [ad_create.py:961, called at L704]
  → strips EXIF, writes JPEG to MEDIA_ROOT
  → update_ad_and_moderate() [ad_create.py:1042]
    → reads from MEDIA_ROOT [L1170: open(original_path, "rb")]
    → generate_thumbnails() [L1175]
    → stores thumbnail_* keys on AdImage [L1179-1189]
```

- `save_photo` (L961) is tested by `test_save_photo_exif.py` for EXIF stripping only.
- `generate_thumbnails` (L1175) is tested by `test_save_photo_integration.py` for integration with `update_ad_and_moderate`, but the photo bytes are written manually (L85), not through `save_photo`.
- **No test exercises the full `save_photo` → disk → `generate_thumbnails` → `AdImage` chain.**
- The Step 1 report's reference to `ad_create.py:588` is **incorrect** — line 588 is in `process_price()` (a form handler). The actual `save_photo` definition is at L961, called at L704; `generate_thumbnails` is at L1175.

---

## 3. Newly Discovered Issues (Task C)

### NEW-1: Currency tests fragile under `--reuse-db` (medium severity)

- 4 currency tests fail with `--reuse-db` because the seeded exchange rate data from migration `0001_initial.py` (`seed_initial_rates`) is absent from the stale DB volume.
- Tests assert hardcoded rate values (e.g., `100 BAM = 51.20 EUR`) without creating their own `ExchangeRate` fixtures.
- **Fix:** Add an autouse fixture in `test_price_normalizer.py` that creates `ExchangeRate` rows, rather than relying on migration data.
- **Runtime evidence:** All 7 currency tests pass with `--create-db`; 4 fail with `--reuse-db`.

### NEW-2: §2.12 bot login tests fail without xdist (high severity — test isolation)

- 12 `concurrent`/`transaction=True` tests in `test_claim_login_token.py` + `test_login_claim.py` produce 3 failures + 6 errors when run with `-p no:xdist`.
- Root cause: `DeadlockDetected` during flush teardown (pytest-django `_fixture_teardown` calls `call_command("flush")`) → data not cleaned → next test hits `IntegrityError: duplicate key` on fixed `token_hash` fixture.
- These tests are designed for xdist (marked `concurrent` + `xdist_group("bot_concurrent")`) but produce false negatives in isolation.
- **Runtime evidence:** `pytest -p no:xdist` → 3 failed, 9 passed, 6 errors. `pytest` (xdist) → 12 passed in 7.86s.

### NEW-3: §2.8 extended — `price_currency="EUR"/"BAM"` raw strings in 4 additional files

- Beyond `test_sweep_commands.py`, 4 more test files use raw string literals for `CurrencyCode` fields:
  - `test_seed.py:275, 370, 384` — `price_currency="EUR"`
  - `test_language_end_to_end.py:93` — `price_currency="EUR"`
  - `test_breadcrumbs_render.py:97` — `price_currency="EUR"`
  - `test_price_format.py:42` — `price_currency="BAM"` (additional file not in audit)

### NEW-4: `CacheKeyWarning` — MagicMock leaking into cache keys (low severity)

- `test_listings_context.py` and `test_detail_context.py` produce 20+ `CacheKeyWarning` warnings.
- Root cause: `MagicMock` objects are passed to functions that cache results by the object's string representation (e.g., `cache.set(f"lookup:resolved_features:{category.id}", ...)`). The mock's repr (`MagicMock name='Category.objects.get().id'`) produces an invalid cache key.
- This masks real cache-key bugs and produces unreadable warnings.

### NEW-5: `test_breadcrumbs_render.py` `_load_catalog` fixture is function-scoped (low severity)

- The `_load_catalog` autouse fixture (L45-58) calls `load_catalog(catalog_path)` + `City.objects.create()` for EVERY test — each invocation takes ~3.6s setup.
- A `scope="class"` or `scope="session"` fixture would eliminate ~30s of redundant overhead across the 5-test class.
- **Evidence:** Duration report shows 4 of top 7 slowest setups are from `TestBreadcrumbsRender`.

### NEW-6: `test_login_claim.py` uses fixed `token_hash` fixture (low severity, contributes to NEW-2)

- `test_login_claim.py:27-30` defines `token_hash` as `hashlib.sha256("a" * 32).hexdigest()` — a fixed value reused across all 5 tests.
- If DB cleanup fails (deadlock → flush skip), the next test hits `duplicate key` on this fixed hash.
- `test_claim_login_token.py` uses the superior `login_token_factory` pattern (random hashes via `secrets.token_urlsafe()`).
- **Recommendation:** Unify on the factory pattern; remove the redundant `token_hash` fixture.

### NEW-7: `test_media_security.py` at wrong path (doc discrepancy — low severity)

- Both the audit compilation and Step 1 report reference `apps/media/tests/test_media_security.py`.
- Actual path: `apps/ads/tests/test_media_security.py` (confirmed via grep).
- The file is in `apps/ads/tests/`, not `apps/media/tests/`.

---

## 4. Spot-Check: Previously "Resolved" Findings (Task D)

| Finding | File | Run | Result |
|---------|------|-----|--------|
| C-01 (Ad check constraints) | `test_ad_constraints.py` | 35-test batch | ✅ PASS (1 transient deadlock at setup in unrelated `test_approve_ad`; `test_ad_constraints` tests all pass) |
| §2.5 (decorator tests) | `test_decorators.py` | 35-test batch | ✅ PASS |
| C-07 (approve_ad side effects) | `test_approve_ad_side_effects.py` | 35-test batch | ✅ PASS (1 transient deadlock at setup only) |
| C-05 (listings sort) | `test_listings_sort.py` | 35-test batch | ✅ PASS |
| C-06 (ad detail N+1) | `test_ad_detail_queries.py` | 35-test batch | ✅ PASS |

**Task D summary:** 35 passed, 1 error. The 1 error is a transient `DeadlockDetected` during `city` fixture setup (not test logic). All 5 spot-checked findings confirmed still resolved.

---

## 5. Exact Commands for Running Specific Tests

```powershell
# Set environment
$env:COMPOSE_FILE="docker-compose.yml;docker-compose.test.yml"
$env:COMPOSE_PROJECT_NAME="mko-bazuna-test"
$env:PYTEST_OPTS="--reuse-db"

# Single file (fast gate, skip seed tests)
docker compose run --rm --entrypoint bash test -c `
  "uv sync --frozen --no-install-project --group dev && uv run pytest --reuse-db -q <FILE_PATH>"

# Marker filter (e.g., run all non-seed tests)
docker compose run --rm --entrypoint bash test -c `
  "uv sync --frozen --no-install-project --group dev && uv run pytest --reuse-db -q -m 'not seed' <PATH_OR_MARKER>"

# Fresh schema (after migration changes)
docker compose run --rm --entrypoint bash test -c `
  "uv sync --frozen --no-install-project --group dev && uv run pytest --create-db -q <FILE_PATH>"

# Without xdist (use with caution — concurrent tests will fail)
docker compose run --rm --entrypoint bash test -c `
  "uv sync --frozen --no-install-project --group dev && uv run pytest --reuse-db -q -p no:xdist <FILE_PATH>"
```

**Specific file commands:**

| Target | Command |
|--------|---------|
| §2.4 (`test_contact.py`) | `... uv run pytest --reuse-db -q src/backend/apps/core/tests/test_contact.py` |
| §2.10 (`test_sweep_lock_structure.py`) | `... uv run pytest --reuse-db -q src/backend/apps/core/tests/test_sweep_lock_structure.py` |
| §2.11 (`test_auto_moderation.py`) | `... uv run pytest --reuse-db -q src/backend/apps/moderation/tests/test_auto_moderation.py` |
| §2.12 (bot login tests) | `... uv run pytest --reuse-db -q src/telegram_bot/tests/test_claim_login_token.py src/telegram_bot/tests/test_login_claim.py` |
| Currency tests (fresh) | `... uv run pytest --create-db -q src/backend/apps/currencies/tests/` |
| §2.7 (all SimpleTestCase files) | `... uv run pytest --reuse-db -q -p no:xdist -m 'not seed' src/backend/apps/trust/tests/test_trust_prefetch.py src/backend/apps/core/tests/test_context_processors.py src/backend/apps/core/tests/test_language_middleware.py src/backend/apps/core/tests/test_language_locale.py src/backend/apps/ads/tests/test_listings_context.py src/backend/apps/ads/tests/test_i18n_completeness.py src/backend/apps/ads/tests/test_i18n_pipeline.py src/backend/apps/ads/tests/test_adimage_thumbnail_urls.py src/backend/apps/ads/tests/test_ad_localization.py src/backend/apps/core/tests/test_templates.py src/backend/apps/core/tests/test_csp_report.py src/backend/apps/core/tests/test_preferred_city_middleware.py src/backend/apps/search/tests/test_autocomplete_template.py src/backend/config/settings/tests/test_settings_secrets.py` |

---

## 6. Validation Matrix (Corrected)

| Finding ID | Severity | Step 1 Status | Step 2 Runtime Status | Notes |
|-----------|----------|---------------|----------------------|-------|
| §2.4 | LOW/MEDIUM | OPEN (static) | **CONFIRMED OPEN** | 66-passed batch includes `TestCheckSellerContactable` (8 direct calls to `_check_seller_contactable`) |
| §2.6 | LOW | OPEN (static) | **RESOLVED** | `e2e` marker absent from `pyproject.toml`; 0 uses. Step 1 report inaccurate. |
| §2.7 | LOW | OPEN (static) | **CONFIRMED OPEN** | 15 files confirmed; 127 passed + 7 subtests. All use `self.assert*`. |
| §2.8 | LOW | OPEN (static) | **CONFIRMED OPEN (EXTENDED)** | 5 raw strings in `test_sweep_commands.py` + 4 files with `price_currency="EUR"/"BAM"` (NEW-3) |
| §2.9 | LOW | OPEN (static) | **CONFIRMED OPEN** | 5 files confirmed (compilation listed 2). All currently set correct timestamps but bypass `create_test_ad`. |
| §2.10 | MEDIUM | OPEN (static) | **CONFIRMED OPEN** | 2 tests pass; uses `inspect.getsource()` at L48,74,87 |
| §2.11 | MEDIUM | OPEN (static) | **CONFIRMED OPEN** | 17 tests pass; 5 private functions tested directly |
| §2.12 | LOW | OPEN (static) | **CONFIRMED OPEN (fragile)** | 12 pass with xdist; 3 fail + 6 errors without xdist (NEW-2) |
| C-09 | P2 | PARTIALLY COVERED | **CONFIRMED OPEN** | `save_photo` (L961) → disk → `generate_thumbnails` (L1175) chain untested. `test_save_photo_integration.py` bypasses `save_photo`. Step 1 report's L588 reference is wrong. |
| C-01 | P0 | RESOLVED | ✅ **CONFIRMED** | `test_ad_constraints.py` passes |
| C-02 | P0 | RESOLVED | ✅ **CONFIRMED** | `TestQualityScoreTruncation` in `test_trust_calculator.py` |
| C-03 | P0 | RESOLVED | ✅ **CONFIRMED** | `TestPriorityLevelBoundaries` + `TestConfidenceScore` in `test_priority.py` |
| C-04 | P1 | RESOLVED | ✅ **CONFIRMED** | `TestContactCombinatorial` + `TestCheckSellerContactable` in `test_contact.py` (66-passed batch) |
| C-05 | P1 | RESOLVED | ✅ **CONFIRMED** | `test_listings_sort.py` in 35-test batch |
| C-06 | P1 | RESOLVED | ✅ **CONFIRMED** | `test_ad_detail_queries.py` in 35-test batch |
| C-07 | P1 | RESOLVED | ✅ **CONFIRMED** | `test_approve_ad_side_effects.py` in 35-test batch |
| C-08 | P2 | PARTIALLY | ✅ **CONFIRMED** | `TestLoginTokenSecurity` in `test_login.py` (part of full sweep, no failures) |
| C-10 | P2 | PARTIALLY | ✅ **CONFIRMED** | `TestPriorityLevelBoundaries` + `TestConfidenceScore` in `test_priority.py` |
| C-11 | P2 | PARTIALLY | ✅ **CONFIRMED** | `TestTrustLevelFloor` in `test_trust_calculator.py` (full sweep, no failures) |
| F-01 | CRITICAL | RESOLVED | ✅ **CONFIRMED** | `tests.py` files deleted; migrated to `tests/` packages |
| §2.1 | MEDIUM | RESOLVED | ✅ **CONFIRMED** | `create_test_ad` in conftest.py (L78); 13/14 local helpers migrated |
| §2.2 | MEDIUM | RESOLVED | ✅ **CONFIRMED** | `create_test_ad` adopted across files |
| §2.3 | LOW | RESOLVED | ✅ **CONFIRMED** | 0 `TestCase` imports/usage (full sweep, no failures) |
| §2.5 | LOW | RESOLVED | ✅ **CONFIRMED** | `test_decorators.py` (9 tests) in 35-test batch |

---

## 7. Summary

### Remaining open findings (11):
- **§2.4** (LOW/MEDIUM): Private method `_check_seller_contactable` tested directly — 8 direct calls
- **§2.7** (LOW): 15 files use `SimpleTestCase` + `self.assert*` instead of plain `assert`
- **§2.8** (LOW): 5 raw strings in `test_sweep_commands.py` + 4 files with raw `price_currency` (extended beyond audit)
- **§2.9** (LOW): 5 files bypass `create_test_ad` with direct `Ad.objects.create()`
- **§2.10** (MEDIUM): `inspect.getsource()` used in 2 structural tests
- **§2.11** (MEDIUM): 5 private auto-moderation functions tested directly (17 tests)
- **§2.12** (LOW): 2 bot files with 3 overlapping scenarios + isolation fragility (fails without xdist)
- **C-09** (P2): `save_photo` → `generate_thumbnails` integration untested
- **NEW-1** (MEDIUM): Currency tests fail under `--reuse-db` (stale DB)
- **NEW-2** (HIGH): §2.12 bot login tests fail without xdist (deadlocks + duplicate keys)
- **NEW-4** (LOW): `CacheKeyWarning` from MagicMock in cache keys
- **NEW-5** (LOW): `_load_catalog` fixture re-runs per test (~3.6s setup overhead)
- **NEW-6** (LOW): Fixed `token_hash` fixture in `test_login_claim.py`

### Corrected from Step 1 report:
- §2.6 is **RESOLVED** (not OPEN) — `e2e` marker already removed; Step 1 report's claim is stale
- §2.8 file attribution for `test_deletion.py` is **INACCURATE** (no `action_type` usage)
- §2.8 string typo `"search_perseformed"` is **incorrect** — actual string is `"search_performed"` (no typo)
- §2.9 affected files: **5, not 2** (Step 1 report corrected; grep confirms)
- C-09 reference `ad_create.py:588` is **wrong** — actual `save_photo` is at L961, called at L704; `generate_thumbnails` at L1175
- `test_media_security.py` is at `apps/ads/tests/` (not `apps/media/tests/`)
- `DeletionReason` enum **does not exist** in the codebase
- No `skipif` or `@pytest.mark.skip` usage anywhere
- No test exceeds 5 seconds individually (slowest: 4.37s)
