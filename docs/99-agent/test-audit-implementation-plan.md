# Test Quality Audit — Implementation Plan

**Project:** Mko Bazuna
**Date:** 2026-09-17
**Prerequisite:** Review `docs/99-agent/test-audit-master-report.md` for full findings.

---

## Phasing Strategy

Phases are ordered by **(regression risk × blast radius) ÷ effort**. Each phase
ships a coherent set of changes that can be merged independently. Phases run
**sequentially** — later phases may depend on marker/coverage fixes from earlier
ones (e.g., `TimeRange` tests need the `integration` marker corrected first).

| Phase | Focus | Duration | Owner(s) |
|---|---|---|---|
| 0 | 🔴 Critical / Must-fix now | 1–2 days | Implementor |
| 1 | 🟠 High-priority cleanup | 3–5 days | Implementor |
| 2 | 🟡 Missing coverage | 1–2 weeks | Implementor + Test Engineer |
| 3 | 🟢 Harden & decouple (refactor) | 2–3 weeks | Implementor + Test Engineer |

---

## Phase 0 — Critical Fixes (Blocker Risk)

**Goal:** Eliminate findings that cause test breakage on the A4 migration or
provide zero regression protection.

### 0.1 — Fix A4-migration mock targets (Block B, B1)

**File:** `src/backend/apps/ads/tests/test_edit.py` (lines ~356, 482, 551)

**Action:** Change patch target from `apps.ads.views.edit.auto_moderate` to
`apps.moderation.services.auto_moderation.auto_moderate` (matching the pattern
already used in `test_submission.py`).

```python
# Before (breaks on A4):
with patch("apps.ads.views.edit.auto_moderate", return_value=True):
# After:
with patch("apps.moderation.services.auto_moderation.auto_moderate", return_value=True):
```

**Acceptance:** `test_edit.py` tests still pass after the change; no `AttributeError`
at collection time.

### 0.2 — Remove end-to-end false-confidence mock (Block F, F1)

**File:** `src/backend/apps/analytics/tests/test_views.py`

**Action:** The `TestModerationAnalyticsView` class wraps **all 9 tests** in
`self._patched_stats()` which stubs `get_moderation_stats` with a hardcoded dict.
At least 1 test must exercise the real view → service → DB path.

- Add a new test `test_moderation_dashboard_end_to_end` that does NOT patch
  `get_moderation_stats`, creates real `AnalyticsEvent` rows, and asserts
  `response.context["stats"]["approved"] == <actual count>`.
- Keep the mocked tests for template-rendering coverage (they verify the view
  wiring, not the service).

**Acceptance:** New test passes with real DB data; mocked tests still pass.

### 0.3 — Fix `User.DoesNotExist = Exception` (Block E, E3a)

**File:** `src/backend/apps/search/tests/test_send_alerts.py` (lines 67-69, 106-108, 147-149, 185-187, 231-233)

**Action:** Replace `patch("apps.users.models.User")` (entire model) with
`mock.patch.object(User.objects, "aget", new=AsyncMock(...))`. Remove
`mock_user_cls.DoesNotExist = Exception` — use the real `User.DoesNotExist`.

**Acceptance:** Tests still pass; `except User.DoesNotExist:` now catches only
actual `DoesNotExist`, not arbitrary exceptions.

### 0.4 — Fix Block D Finding 6 disputed sub-claims (verify, don't break)

**Action:** The trust-calculator sub-claim in D6 is inaccurate — the test
`test_response_score_with_contacts` correctly asserts `20.0` (= `(2/3)*30`) and
production has no `min_responses=5` threshold. **Do not change production or test.**
Verify `test_priority_filter_param` formula drift separately (small task).

**Acceptance:** Document that D6 trust-calculator sub-claims are invalid; no
code changes required.

---

## Phase 1 — High-Priority Cleanup (Remove False Signals & Duplicates)

**Goal:** Remove tests that provide zero value, fix marker misclassification,
and eliminate the most misleading assertions.

### 1.1 — Remove duplicate nonexistent-token→410 tests (Block F, F2)

**Files:** `src/backend/apps/users/tests/test_login.py`,
`src/backend/apps/users/tests/test_consent.py`

**Action:** Keep only one test for the nonexistent-token→410 path. Remove:
`test_login_status_410_on_post_unknown_token` and
`test_consent.py::TestLoginStatusNoPii.test_invalid_token_returns_410`.

**Acceptance:** 1 test remains; both files' test counts decrease by 1.

### 1.2 — Remove redundant constraint tests in `test_ad_lifecycle.py` (Block B, B2)

**File:** `src/backend/apps/ads/tests/test_ad_lifecycle.py` (lines 101–141)

**Action:** Delete 3 overlap tests (`test_checkconstraint_published_requires_published_at`,
`test_checkconstraint_archived_requires_archived_at`,
`test_checkconstraint_mutual_exclusivity`). Move
`test_transition_after_concurrent_hard_delete_raises` (line 144) to
`test_ad_constraints.py`.

**Acceptance:** No constraint is tested in two places; `test_ad_constraints.py`
retains full coverage.

### 1.3 — Fix marker misclassification (Block B, Block F, Block G)

| File | Issue | Fix |
|---|---|---|
| `test_price_format.py` (B) | No marker | Add `pytestmark = [pytest.mark.unit]` |
| `test_trust_analytics.py` (F) | `django_db`/`slow`/`integration` on pure functions | Split: remove `pytestmark`; mark DB-touching tests individually |
| `test_city_suggestions.py` (G) | `unit` + `django_db` contradiction | Remove `unit`; use `integration` |
| `test_download_seed_photos.py` (G) | Should be nightly, marked `unit` | Add `real_images` marker (matches doc §7) |

**Acceptance:** `pytest.mark.unit` tests never touch DB; `slow` only on >5s tests;
seed-image tests excluded from fast gate.

### 1.4 — Fix weak assertions in dashboard view tests (Block F, F4)

**File:** `src/backend/apps/analytics/tests/test_views.py`

**Action:** For `TestSellerTrustDashboardView`, replace `isinstance(..., int)` /
`isinstance(..., float)` assertions with value checks against known fixture data
(e.g., assert `trust_score == 50 + 30` for 1 published ad). Add at least 2
value-assertion tests (trust score, trust level).

**Acceptance:** Tests fail if aggregation logic returns wrong values.

### 1.5 — Re-audit Block D Finding 6 (D, D6)

**Action:** Independent re-audit of the trust calculator tests and
`test_ban_user_soft_deletes_ads` to resolve the dispute. Either:
- If the sub-claims are valid, fix the test or production code.
- If invalid (as preliminarily found), close as "no action needed" with
  documentation.

**Acceptance:** D6 is resolved — either fixed or documented as invalid.

### 1.6 — Remove duplicate `_parse_po_entries` (Block B, B6)

**Files:** `test_i18n_completeness.py` (lines 50–107), `test_i18n_pipeline.py` (lines 31–71)

**Action:** Extract the plural-aware version to `src/backend/testing/i18n_helpers.py`;
import from both test files.

**Acceptance:** Single source of truth; both test files import the helper.

---

## Phase 2 — Missing Coverage (Fill Gaps)

**Goal:** Add tests for untested production code and unverified business flows.

### 2.1 — `copy_ad` service tests (Block B, B3)

**File:** `src/backend/apps/ads/services/copy_service.py` → new `test_copy_ad.py`

Tests:
1. Happy path: all fields + features + images copied, status=DRAFT.
2. Ownership: `PermissionError` for non-owner.
3. Source not found: `Ad.DoesNotExist`.
4. Image positions preserved.
5. Features M2M copied correctly.

### 2.2 — Moderation side-effect assertions (Block D, D3; Block C, C9)

**Files:** `test_moderation_log.py`, `test_approve_ad_side_effects.py`, `test_ad_create.py`

Tests:
- `test_set_published_logs_analytics_event` — assert `AnalyticsEvent` with `AD_PUBLISHED`.
- `test_set_rejected_logs_analytics_event` — assert `AD_REJECTED`.
- `test_set_moderation_failed_logs_analytics_event` — assert `AD_MODERATION_FAILED`.
- `test_reject_ad_side_effects` — `reject_ad` admin action.
- `test_approve_ad_creates_priority_event` — assert `AD_PRIORITY_CALCULATED`.

### 2.3 — Bot photo-flow integration tests (Block C, C2)

**File:** `src/telegram_bot/tests/test_ad_create.py`

Replace 2 of the 7 over-mocked tests in `TestProcessPhotos` with a real
integration test using a small JPG fixture that exercises `AdCreateState.PHOTO`
→ `AdImage` creation → `ThumbnailService.generate_thumbnails` → real thumbnail
keys.

### 2.4 — Analytics end-to-end & missing media coverage (Block F, F9)

| Test to Add | Target | Purpose |
|---|---|---|
| Moderation dashboard unmocked | `test_views.py` | View → service → model |
| Cache hit/miss | `test_seller_stats.py` | Verify caching behavior |
| `TimeRange` 7-day/30-day | `test_seller_stats.py` | Time-range filtering |
| Seed-source exclusion | `test_rollup_daily_metrics.py` | No metric contamination |
| `strip_photo_exif` unit | `test_filesystem.py` | Security hardening |
| `assert_storage_key_contained` | `test_filesystem.py` | CWE-22 path traversal |
| `move_staging_to_permanent` | `test_filesystem.py` | Data integrity |
| Signal registration | `test_media_config.py` | `pre_delete` handler |

### 2.5 — Search coverage gaps (Block E, E9)

| Test to Add | Target | Purpose |
|---|---|---|
| `build_alert_message` keyboard | `test_immediate_alerts.py` | Unsubscribe button `callback_data` |
| `assert_storage_key_contained` | `test_filesystem.py` | Path-traversal security |
| Cache invalidation on tree bump | `test_categories.py` | Cache correctness |
| `login_rate_limit_check` unit | `test_login.py` | Cache `add`/`incr` pattern |
| `consent_withdraw` idempotent on deleted user | `test_consent.py` | Idempotency |
| Anonymous-gate coverage (POST endpoints) | `test_cabinet_sections.py` | 302 redirect |

### 2.6 — Untested production code in Core (Block A, A1)

Add tests for: `health_check` (DB probe + 503), `translate_text`/circuit breaker,
`record_contact_initiated`, `can_contact` filter, `get_title`/`get_description`
template tags, `get_item` filter.

---

## Phase 3 — Harden & Decouple (Refactor)

**Goal:** Eliminate fragile tests, cross-block coupling, and bloated files.
Lower urgency but improves long-term maintainability.

### 3.1 — Fix `slow` marker abuse (Block F, all analytics files)

**Files:** `test_moderation_analytics.py`, `test_rollup_daily_metrics.py`,
`test_seller_stats.py`, `test_trust_analytics.py`, `test_ads_published.py` +
all analytics/users/media files with blanket `slow`.

**Action:** Remove `slow` from files where no test takes >5s. Apply `slow` only
to specific tests that need it (e.g., `TestBackfillThumbnails` bulk operations).

### 3.2 — Fix async/sync boundary in rate-limit tests (Block C, C3)

**Files:** `test_rate_limit_service.py`, `test_login_rate_limit.py`

**Action:** Either (a) add `@pytest.mark.asyncio` + `await` calls, or (b) add
`assert` that the function is wrapped by `sync_to_async`. Per `pyproject.toml`
`asyncio_mode = "strict"`, explicit markers are required.

### 3.3 — Fix shared hardcoded identifiers (Block C, C4)

**Files:** `test_ad_create.py`, `test_login.py`, `test_account_state_middleware.py`,
`test_create_draft_ad.py`, `test_unsubscribe.py`, `test_price_payload.py`

**Action:** Replace hardcoded Telegram IDs with bot conftest's `seller`/`user`
fixtures. Add `pytest.mark.xdist_group("telegram_ids")` to tests sharing IDs.

### 3.4 — Harden fragile fixtures (Blocks A, F, G)

| File | Fix |
|---|---|
| `test_rtl_obfuscation.py` (A) | Replace CSS file content assertion with programmatic check |
| `test_advisory_lock_ids.py` (A) | Replace AST/regex source parsing with enum-value cross-reference |
| `test_save_photo_exif.py` (F) | Replace manual TIFF byte construction with Pillow-generated EXIF fixture |
| `test_filesystem.py` (F) | Replace `SimpleNamespace` settings hack with `override_settings(MEDIA_ROOT=...)` |
| `test_thumbnails.py` (F) | Replace exact string `== "abc123-small.jpg"` with pattern assertion |
| `test_load_cities.py` (G) | Decouple from exact count (assert `>= 15` or derive from source) |
| `test_docs_ci_parity.py` (G) | Replace positional `.PHONY` parsing with regex |

### 3.5 — Split bloated test files (Blocks A, B)

| File | Action |
|---|---|
| `test_sweep_commands.py` (1,046 lines, A) | Split into per-command files |
| `test_catalog_filters.py` (1,333 lines, B) | Split filter tests by concern |

### 3.6 — Decouple cross-block imports (Blocks A, C, F)

| File | Fix |
|---|---|
| Core tests importing bot (A, A3) | Move to bot test dir |
| `test_ad_lifecycle.py` moved to bot tree (C, C1) | Delete from bot; verify Block D coverage |
| Media tests importing bot + ads (F, F7) | Test `strip_photo_exif` directly; test `AdImageService` in ads test dir |

### 3.7 — Consolidate duplicated helpers (Blocks B, C, D, E, F)

| File | Fix | Status |
|---|---|---|
| `_make_user` in 4 analytics files (F) + 6 cross-block files (B, C, D, F) | Replaced local `_make_user` with root conftest `make_user()` (now accepts `consent_revoked: bool = False`) | ✅ Done |
| `buyer` fixture in 5 search files (E) | Add to root `conftest.py` | ⏳ Pending |
| Inline `Category`/`City` imports in `test_deletion.py` (F) | Use shared fixtures | ⏳ Pending |
| `_assert_*` helpers in `test_priority_service.py` (D) | Move to `conftest.py` | ⏳ Pending |

**Files consolidated (P3.7):** `test_moderation_analytics.py`, `test_rollup_daily_metrics.py`,
`test_seller_stats.py`, `test_trust_analytics.py` (Block F analytics),
`test_dashboard_stats.py` (B), `test_trust_tags.py` (D), `test_trust_calculator.py` (D),
`test_priority_service.py` (D), `test_account_state.py` (F), `test_account_state_middleware.py` (C).
Root `make_user()` in `src/backend/conftest.py` now accepts `consent_revoked: bool = False` to
set `consent_revoked_at` when `True`.

---

## 4. Sequencing & Dependencies

```
Phase 0 (1-2 days) → Phase 1 (3-5 days) → Phase 2 (1-2 weeks) → Phase 3 (2-3 weeks)
     ↓                    ↓                    ↓                    ↓
  Unblocks A4           Removes false         Fills coverage      Improves
  migration landing     signals + dupes        gaps               maintainability
```

- **Phase 0 must complete before A4 migration lands** (B1).
- **Phase 1 should complete before Phase 2**: marker fixes (1.3) enable correct
  fast-gate behavior so new coverage tests land in the right category.
- **Phase 3 depends on Phase 1 + 2**: splitting bloated files (3.5) and
  decoupling imports (3.6) is easier after duplicates are removed and coverage
  is verified.

## 5. Acceptance Criteria (Overall)

| Metric | Current | Target (after all phases) |
|---|---|---|
| Critical findings | 1 | 0 |
| High findings | 14 | ≤ 3 |
| Medium findings | 32 | ≤ 10 |
| `slow`-marked tests taking <5s | ~15+ | 0 |
| Duplicate tests | ~10 | 0 |
| Cross-block import coupling in tests | 4 instances | 0 |
| `copy_ad` test coverage | 0 | Complete |
| Unused `seller/category/city` fixture params | 6 | 0 |

## 6. Non-Goals (Explicitly Out of Scope)

- No production code changes driven by test cleanup (tests should not distort
  production logic — project rule #2).
- No new test framework or tooling migration.
- No changes to the two-process (web + bot) architecture or migration-once
  deployment model.
- i18n `msgstr` completeness is verified by `test_i18n_completeness.py` — not
  in scope for this audit.
