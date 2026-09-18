# Block F (Analytics + Users + Media) — Test Quality Audit Findings

**Auditor:** Test Engineering
**Scope:** `src/backend/apps/analytics/tests/` (6 files) + `src/backend/apps/users/tests/` (7 files) + `src/backend/apps/media/tests/` (7 files) = 20 test files
**Method:** Static analysis only (bash/shell blocked by global rule)
**Date:** 2026-09-17

---

## Root Cause 1 — Over-Mocking in View Integration Tests

**File:** `src/backend/apps/analytics/tests/test_views.py`

| Test | Problem |
|---|---|
| `TestModerationAnalyticsView.test_stats_reflects_actual_moderation_events` | Patches `get_moderation_stats` with `mocker.Mock(return_value={"approved": 1, "rejected": 0, ...})` then asserts `response.context["stats"]["approved"] == 1`. The mock return value IS the assertion — the `AnalyticsEvent` rows created in setUp are never queried. The test name claims to verify "moderation events" but is a tautology on a hardcoded dict. |
| `TestModerationAnalyticsView` (all 9 tests) | Every test wraps its request in `self._patched_stats()`, stubbing `get_moderation_stats` entirely. No test exercises the real end-to-end view → service → model path. |
| `TestModerationAnalyticsView` (all except 2) | `get_pending_queue_size`, `get_moderator_performance`, `get_rejection_reasons` are NOT patched — they run against the real DB — yet tests only assert `isinstance(context["pending_queue_size"], int)` (type presence), never the computed values. |

**Contrast:** `TestSellerTrustDashboardView` does NOT mock anything — it exercises real `SellerStats`, `calculate_seller_trust_score`, and `get_seller_daily_metrics` against the real DB. This is the correct pattern.

---

## Root Cause 2 — Redundant / Duplicate Tests

### Cross-file duplication
**File:** `src/backend/apps/users/tests/test_login.py` + `src/backend/apps/users/tests/test_consent.py`

| Test | Problem |
|---|---|
| `test_login.py::test_login_status_410_nonexistent_token` | POST to `/login/status/` with a fake token → asserts 410. |
| `test_login.py::test_login_status_410_on_post_unknown_token` | POST to `/login/status/` with a different fake token → asserts 410. |
| `test_consent.py::TestLoginStatusNoPii::test_invalid_token_returns_410` | POST to `/login/status/` with a fake token → asserts 410. |

Three tests for the identical non-existent-token → 410 behavior across two files.

### Same-file duplication
**File:** `src/backend/apps/users/tests/test_deletion.py`

| Test | Problem |
|---|---|
| `TestWithdrawConsentSoftDeletesAds.test_withdraw_returns_all_thumbnail_storage_keys` | Creates a DRAFT ad with an `AdImage` (4 storage keys); calls `withdraw_consent`; asserts return has 4 keys and `delete_photo` called 4 times. |
| `TestWithdrawConsentAtomicity.test_withdraw_returns_storage_keys` | Identical setup and assertions; adds only type-checking (`isinstance(result, list)`, `all(isinstance(k, str))`). |

**File:** `src/backend/apps/users/tests/test_deletion.py`

| Test | Problem |
|---|---|
| `TestWithdrawConsentInvalidatesTokens.test_withdraw_deletes_user_login_tokens` | Creates 2 LoginTokens, calls `withdraw_consent`, asserts both deleted. |
| `TestWithdrawConsentAtomicity.test_withdraw_invalidates_tokens` | Creates 1 LoginToken, calls `withdraw_consent`, asserts deleted. Overlapping coverage. |

---

## Root Cause 3 — Duplicated `_make_user` / Helper Code Across Test Files (Resolved)

**Files (resolved):** `test_moderation_analytics.py`, `test_rollup_daily_metrics.py`,
`test_seller_stats.py`, `test_trust_analytics.py` (Block F, 4 analytics) +
`test_dashboard_stats.py` (Block B), `test_trust_tags.py` (Block D),
`test_trust_calculator.py` (Block D), `test_priority_service.py` (Block D),
`test_account_state.py` (Block F), `test_account_state_middleware.py` (Block C) —
6 cross-block files consolidated during P3.7.

Each independently defined `_make_user(telegram_id=9900XXXX, ...)`, `_make_category`, `_make_city`, `_make_seller`, `_make_moderator` — replicating root `conftest.py` `seller`/`user` fixtures but with per-file telegram_id prefixes to avoid uniqueness conflicts.

**Resolution (P3.7):** All `_make_user` helpers consolidated into a single `make_user()`
function in root `conftest.py` (`src/backend/conftest.py`). `make_user()` now accepts a
`consent_revoked: bool = False` parameter that sets `consent_revoked_at` when `True`.
All 10 files replaced their local `_make_user` with the shared `make_user`.

**File:** `src/backend/apps/users/tests/test_deletion.py` — inline `from apps.categories.models import Category` / `City` imports inside 4 test methods; `Category.objects.create(...)` inline instead of using shared `category`/`city` fixtures.

---

## Root Cause 4 — Weak / Missing Assertions (Type/Presence Only)

**File:** `src/backend/apps/analytics/tests/test_views.py`

| Test | Problem |
|---|---|
| `test_staff_user_gets_200` | Asserts `response.context["stats"]` exists and is a dict. Never checks actual stat values. |
| `test_trust_score_in_context` | Asserts `isinstance(stats["trust_score"], float)` — never verifies computed score matches expected. |
| `test_trust_level_in_context` | Asserts `str(stats["trust_level"])` is one of 4 valid enum values — never verifies level corresponds to score. |
| `test_total_views_in_context` | Asserts `isinstance(stats["total_views"], int)` — never verifies the sum matches event data. |

**File:** `src/backend/apps/users/tests/test_consent_records.py`

| Test | Problem |
|---|---|
| `test_ip_is_anonymized_and_ua_truncated` | Uses `if record.ip_address is not None:` guard before asserting `.endswith(".0")`. Django test client always sets `REMOTE_ADDR=127.0.0.1`, so the IP assertion is dead code. |

**File:** `src/backend/apps/media/tests/test_backfill_thumbnails.py`

| Test | Problem |
|---|---|
| `test_dry_run_reports_count` | Name says "reports count" but never inspects `self.stdout` or logged count. |

---

## Root Cause 5 — Missing Side-Effect Verification

**File:** `src/backend/apps/users/tests/test_consent.py`

| Test | Problem |
|---|---|
| `test_withdraw_sets_withdrawn_cookie` | Asserts `consent_given == "withdrawn"` only. Does NOT verify `consent_analytics == "false"` or `consent_preferences == "false"`, or `preferred_city` cookie deletion. |
| `test_accept_sets_consent_given_at` | Verifies `consent_given_at` set and redirect, but NOT that `ConsentRecord` was created (no DB assertion). |

**File:** `src/backend/apps/users/tests/test_login.py`

| Test | Problem |
|---|---|
| `test_login_status_200_claimed_and_user_exists` | Asserts `status_code == 200` and session exists, but never checks `token.consumed_at is not None`. |

**File:** `src/backend/apps/media/tests/test_filesystem.py`

| Test | Problem |
|---|---|
| `test_delete_photo_logs_media_deletion_error_on_retry_exhaustion` | Verifies `storage_key`, `error_type`, `attempts` but never checks `error_message` (the field whose 1000-char truncation is part of the model contract). |

---

## Root Cause 6 — Misapplied Markers

**File:** `src/backend/apps/analytics/tests/test_trust_analytics.py`

`TestGetTrustLevel` (9 tests) — pure function calls (`get_trust_level(0)`). Module-level `pytestmark = [django_db, slow, integration]` applies all three unnecessarily.

**File:** `src/backend/apps/analytics/tests/test_seller_stats.py`

`test_cache_key_format` — calls `SellerStats(user_id=42)._cache_key(...)` (private method) but is marked `django_db` with no DB usage.

**All 6 analytics files + 7 users files** — `pytestmark = [django_db, slow, integration]` on every file. The `slow` marker (>5s) is misapplied — no test involves heavy computation.

**File:** `src/backend/apps/media/tests/test_filesystem.py`

`test_delete_photo_logs_media_deletion_error_on_retry_exhaustion` carries `@pytest.mark.unit` (class-level pytestmark) but uses `@pytest.mark.django_db` — marker contradiction.

---

## Root Cause 7 — Cross-Block Import Coupling

**Files:** `src/backend/apps/media/tests/test_save_photo_exif.py`, `src/backend/apps/media/tests/test_thumbnail_integration.py`

| Test | Problem |
|---|---|
| `test_save_photo_strips_exif_and_writes_staging_key` | Imports `save_photo` from `telegram_bot.services.ad_data` (Block C). Should test `strip_photo_exif` directly. |
| `test_thumbnail_integration.py` | Imports `save_photo` from `telegram_bot.services.ad_data` (Block C) AND `AdImageService.create_or_skip` from `apps.ads.services.images` (Block B). Spans 3 blocks despite living in media test dir. |

---

## Root Cause 8 — Fragile Test Fixtures / Infrastructure

**File:** `src/backend/apps/media/tests/test_save_photo_exif.py` — `jpeg_with_exif` fixture manually constructs TIFF IFD bytes via `struct.pack` with hardcoded offsets. Tightly coupled to EXIF binary format + specific Pillow version.

**File:** `src/backend/apps/media/tests/test_filesystem.py` — `_isolate_media_root` fixture replaces entire Django `settings` with `SimpleNamespace(MEDIA_ROOT=tmp_path)` via monkeypatch. Breaks if any code references other settings attributes.

**File:** `src/backend/apps/media/tests/test_thumbnails.py`

`test_storage_key_format_follows_uuid_size_pattern` asserts `thumbnails[SMALL] == "abc123-small.jpg"` — tightly coupled to `"{stem}-{size}.jpg"` naming convention.

---

## Root Cause 9 — Missing Coverage (Business Flows, Negative Cases, Boundaries)

### Analytics
| Area | Missing Test |
|---|---|
| `test_views.py::TestModerationAnalyticsView` | No end-to-end (unmocked) test; view → service → model path never verified. |
| `test_seller_stats.py` | No cache hit/miss behavior test; `test_cache_key_format` tests private method only. |
| `test_seller_stats.py` | No `TimeRange.SEVEN_DAYS` or `TimeRange.THIRTY_DAYS` filtering test. |
| `test_rollup_daily_metrics.py` | No test verifying seed-source events excluded from rollup. |

### Users
| Area | Missing Test |
|---|---|
| `test_consent.py` | No `consent_withdraw` on already-soft-deleted user (idempotency). |
| `test_consent.py` | No GET `/consent/withdraw/` → 405 (no method enforcement test). |
| `test_login.py` | No unit test for `login_rate_limit_check` service (cache.add/increment pattern). |
| `test_consent.py` | No test verifying `record_consent_action` called with correct `choice`/`categories` for authenticated path. |

### Media
| Area | Missing Test |
|---|---|
| `test_filesystem.py` | No direct unit test for `strip_photo_exif` (only exercised via bot's `save_photo`). |
| `test_filesystem.py` | No test for `assert_storage_key_contained` (NUL bytes, absolute paths, `..` traversal — CWE-22). |
| `test_filesystem.py` | No test for `move_staging_to_permanent` (staging-to-permanent promotion). |
| `test_filesystem.py` | No test for `validate_jpeg_bytes` magic-byte-only edge case. |
| `test_media_config.py` | No test for signal handler registration (`pre_delete` on `AdImage`). |

### Cross-cutting negative/boundary cases
| Area | Missing Test |
|---|---|
| `test_account_state.py` | No test for `can_publish_ad` when `is_declined=True`. |
| `test_account_state.py` | No test for `can_login` when `is_deleted=True`. |

---

## Root Cause 10 — Testing Implementation Details (Private Methods)

**File:** `src/backend/apps/analytics/tests/test_seller_stats.py`

`test_cache_key_format` calls `svc._cache_key(TimeRange.ALL_TIME)` (private method) and asserts exact string `"seller_stats:42:all_time"`. Breaks on any cache-key format change.

---

## Root Cause 11 — Misleading Test Names / Docstrings

**File:** `src/backend/apps/users/tests/test_login.py`

`test_login_status_410_on_post_unknown_token` — docstring mentions "POST path regression" but `login_status` only handles POST (via `@require_POST`); no GET path exists to regress.

**File:** `src/backend/apps/users/tests/test_consent.py`

`TestLoginStatusNoPii.test_invalid_token_returns_410` — class name implies PII focus but test only checks status code.

---

## Root Cause 12 — Lint / Code Hygiene Issues in Tests

**File:** `src/backend/apps/users/tests/test_consent.py` — `assert response.url == "/dashboard/"` carries `# noqa: S105` (possible hardcoded password). `"/dashboard/"` is a URL path, not a password — suppression is noise.

**File:** `src/backend/apps/media/tests/test_thumbnails.py`

`test_invalid_image_handling` uses try/except/else instead of `pytest.raises(ValueError)`.

---

## Root Cause 13 — Wasteful / Unused Fixture Dependencies

**File:** `src/backend/apps/media/tests/test_sweep_orphaned_media.py` — 6 tests accept `seller, category, city` fixtures but never create `AdImage` records. Only 2 tests actually need the `AdImage` model.

**File:** `src/backend/apps/analytics/tests/test_views.py` — `TestSellerTrustDashboardView` (all 11 tests) calls `self._setup()` creating a `dashboard_seller` with 1 PUBLISHED ad, but only 1 test asserts on ad data. The other 10 don't need it.

---

## Root Cause 14 — Obsolete / Misaligned Test Data

**File:** `src/backend/apps/analytics/tests/test_ads_published.py` — `seller_ads` fixture creates ads titled `"Published 0"`, `"Published 1"`, `"Published 2"`, then `"Rejected Ad 2"` (line 43) followed by `"Rejected Ad"` (line 46). Out-of-order numbering.

**File:** `src/backend/apps/analytics/tests/test_moderation_analytics.py` — `moderation_stats_data` fixture creates `AnalyticsEvent` rows via `events._make_moderation_event(ad, ...)` bypassing `record_event` service that sets `source`. Test data doesn't match how events are created in production.

---

## Summary Table

| # | Root Cause | Files | Tests Affected | Severity |
|---|---|---|---|---|
| 1 | Over-mocking view integration tests | 1 | 9 | High |
| 2 | Redundant/duplicate tests | 2 | 7 | Medium |
| 3 | Duplicated helper code across files (`_make_user` resolved via P3.7) | 5+6 | — | Low |
| 4 | Weak/missing assertions (type only) | 3 | 8 | Medium |
| 5 | Missing side-effect verification | 3 | 5 | Medium |
| 6 | Misapplied markers | 3 | 15+ | Medium |
| 7 | Cross-block import coupling | 2 | 4 | High |
| 8 | Fragile fixtures / infrastructure | 3 | 5 | Medium |
| 9 | Missing coverage (flows, negative, boundary) | 5 | — | High |
| 10 | Testing implementation details (private methods) | 1 | 1 | Low |
| 11 | Misleading names/docstrings | 2 | 3 | Low |
| 12 | Lint/code hygiene in tests | 2 | 2 | Low |
| 13 | Wasteful/unused fixtures | 2 | 16 | Low |
| 14 | Obsolete/misaligned test data | 2 | — | Low |
