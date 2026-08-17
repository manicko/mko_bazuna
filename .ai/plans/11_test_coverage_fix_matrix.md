---
phase: 11
phase_name: test-coverage
audit_report: .ai/audit/99-validation/11-test-coverage-validated-findings.md
classification_source: researcher agents (3 parallel)
research_source: researcher deep-dive on Complex/Multi-route findings
status: in_progress
---

# Phase 11 — Test Coverage Fix Matrix

> **Audit Report:** `.ai/audit/99-validation/11-test-coverage-validated-findings.md`
> **All 13 findings validated.** 0 rejected, 0 merged, 0 reclassified.
>
> This matrix consolidates every finding's classification, preferred remediation
> (selected in Step 2.1 research), tests required, and documentation changes.
> Status moves to DONE only after the Implementor commits + passes quality gates
> and the Doc-specialist updates listed docs.

---

## Classification Summary

| ID | Severity | Classification | Preferred Route | Files Affected |
|----|----------|---------------|-----------------|----------------|
| TSC-001 | CRITICAL | Complex/High-risk | Umbrella verification | None (verification only) |
| TSC-002 | CRITICAL | Simple / Low-risk | Direct fix | `test_media_security.py` |
| TSC-003 | CRITICAL | **Multiple viable routes** | **Route A**: Add constraints to model | `models.py`, `migrations/0006_*` |
| TSC-004 | HIGH | Simple / Low-risk | Direct fix + _make_ad bug | `entrypoint-test.sh`, `test_sweep_commands.py` |
| TSC-005 | HIGH | Already fixed | No action | None |
| TSC-006 | HIGH | **Multiple viable routes** | **Route B**: async fixture + sync_to_async | `conftest.py` |
| TSC-007 | HIGH | Simple / Low-risk | Direct fix | `pyproject.toml` |
| TSC-008 | HIGH | Simple / Low-risk | Direct fix | `pyproject.toml` |
| TSC-009 | MEDIUM | Already resolved | No action | None |
| TSC-010 | MEDIUM | Complex / High-risk | 5 new test files | `test_ad_create_fsm.py`, `test_ad_create_media.py`, `test_ad_create_moderate.py`, `test_contact.py`, `test_login_deep_link.py` |
| TSC-011 | MEDIUM | **Multiple viable routes** | **Route A**: Keep `test_login_claim.py` | `test_login_claim.py` + delete `test_claim_login_token.py` |
| TSC-012 | LOW | **Multiple viable routes** | Route A + Route C | `test_query_translator.py`, `test_ad_lifecycle.py` |
| TSC-013 | LOW | Simple / Low-risk (moot) | Eliminated via TSC-012 Route C | `test_ad_lifecycle.py` |

### Prior-Phase Dependencies (block TSC-001 verification)

| ID | Phase | Status | Fix |
|----|-------|--------|-----|
| AUT-001 | 04 | ✅ Already fixed | login.py uses raw SQL UPDATE...RETURNING |
| PII-001 | 06 | ✅ Already fixed | User.telegram_id already nullable |
| SRH-003 | 08 | ✅ Already fixed | send_alerts.py imports `TelegramForbiddenError` |
| SRH-001 | 08 | ✅ Already fixed | migration 0006 includes multi-language FTS trigger |
| **SRH-004** | 08 | ❌ **Still open** | `update_or_create` resets hit_count → fix: `get_or_create` |
| **SRH-007** | 08 | ❌ **Still open** | No cache.clear() autouse fixture in autocomplete tests |
| **SRH-011** | 08 | ❌ **Still open** | Test fixture description contains search term |

---

## Finding Details

### TSC-001 (CRITICAL) — Umbrella: full suite not green

**Classification:** Complex / High-risk

**Current state:** 30 failures + 4 errors, 71.70% coverage (below 80% threshold) via `fail_under = 80`.

**Remediation:** This is a verification-only finding. It depends on all TSC-002 through TSC-013 fixes PLUS prior-phase bugs SRH-004, SRH-007, SRH-011 (all still open). SRH-004 is a production-code bug in `popular_search.py`; SRH-007 and SRH-011 are test-only fixes included in this phase's implementation to unblock verification.

**Preferred solution:** No code change for TSC-001 itself. After all other findings (including SRH-004/007/011 fixes) are implemented, verify with:
```
uv run pytest --tb=short --cov --cov-report=term-missing
```
Success criteria: 0 failures, 0 errors, >=80% line coverage with branch coverage. If residual failures exist, file a new TSC finding with test name + assertion + stack trace.

**Tests required:** None (verification only — uses existing test suite).

**Docs required:** None.

---

### TSC-002 (CRITICAL) — EXIF test fixture crashes at setup

**Classification:** Simple / Low-risk

**Root cause:** `jpeg_with_exif` fixture at `test_media_security.py:99` sets `ExifBase.GPSInfo: b"\x02\x03\x04\x05"` (raw bytes). PIL's `Exif.tobytes()` (line 105) expects GPSInfo (tag 0x8825) to be an IFD sub-table dict, not raw bytes. Fixture setup crashes → all 4 `TestExifStripping` tests ERROR before executing.

**Preferred solution:** Replace `b"\x02\x03\x04\x05"` with `{1: "N"}` (GPSLatitudeRef tag, valid GPS sub-IFD entry). This makes `Exif.tobytes()` (line 105) serialize correctly, and `test_strip_photo_exif_removes_gps` (line 306) asserts `ExifBase.GPSInfo not in exif_data` — requiring GPSInfo present in the fixture.

**Rejected alternative:** Remove GPSInfo tag — would make `test_strip_photo_exif_removes_gps` pass vacuously.

**Files to modify:** `src/backend/apps/ads/tests/test_media_security.py:99`

**Tests required:** None (existing tests: `test_strip_photo_exif_removes_make`, `test_strip_photo_exif_removes_model`, `test_strip_photo_exif_removes_gps`, `test_strip_photo_exif_valid_jpeg`, `test_strip_photo_exif_preserves_image` — all should pass after fixture fix).

**Docs required:** None.

---

### TSC-003 (CRITICAL) — Pending migration 0005/0006

**Classification:** Multiple viable routes

**Root cause:** Audit premise stale (migration 0004 was untracked at audit time, now committed via `e912679`). Real drift: migration `0006_ad_ix_ads_purge_deleted_and_more.py` exists on disk (untracked) and adds 6 DB-level `CheckConstraint`s + `IX_ads_purge_deleted` index. The `Ad` model's `Meta` class has neither — no `constraints` list, and `IX_ads_purge_deleted` is not in `indexes`. `makemigrations --check --dry-run` detects the mismatch and generates a pending migration to drop them.

**Preferred solution — Route A:** Add the 6 `CheckConstraint`s and `IX_ads_purge_deleted` index to the `Ad` model's `Meta.constraints` / `Meta.indexes`. This aligns the model state with migration 0006's state, so `makemigrations --check` passes. Preserves DB-level integrity guarantees. Aligns with the `_make_ad` test helper's documented dependency on CheckConstraints (the helper comment at `test_sweep_commands.py:66-70` explicitly says "DB CheckConstraints require timestamps...").

**Rejected alternative — Route B:** Generate migration 0007 to drop the constraints. Matches the model's current (simplified) state but loses DB-level guarantees and makes the `_make_ad` DRAFT-first workaround unnecessary (removing a safety net).

**Files to modify:**
- `src/backend/apps/ads/models.py` — add `constraints` list + `IX_ads_purge_deleted` to `Meta.indexes`
- `src/backend/apps/ads/migrations/0006_ad_ix_ads_purge_deleted_and_more.py` — ensure committed (git add + commit)

**Constraint definitions** (from migration 0006 operations, applied to model Meta):
```
ck_ads_published_at_if_published  → published_at NOT NULL when status=PUBLISHED
ck_ads_archived_at_if_archived    → archived_at NOT NULL when status=ARCHIVED
ck_ads_rejected_at_if_rejected    → rejected_at NOT NULL when status=REJECTED
ck_ads_moderation_failed_at_if_failed → moderation_failed_at NOT NULL when status=ON_MODERATION_FAILED
ck_ads_deleted_at_if_deleted      → deleted_at NOT NULL when status=DELETED
ck_ads_failed_and_rejected_mutually_exclusive → moderation_failed_at IS NULL OR rejected_at IS NULL
```

**Tests required:**
| Scope | Test File | Test Case | Key Assertions |
|-------|-----------|-----------|----------------|
| Integration | `test_migrations.py` | `test_makemigrations_check` | `makemigrations --check --dry-run` exits 0 |

**Docs required:** None (model Meta change is self-documenting; migration already has inline SQL).

---

### TSC-004 (HIGH) — `--reuse-db --create-db` breaks sweep tests + _make_ad bug

**Classification:** Simple / Low-risk (entrypoint) + secondary bug fix (_make_ad)

**Root cause (primary):** `docker/entrypoint-test.sh:40` uses `${PYTEST_OPTS:---reuse-db --create-db --tb=short}`. `--reuse-db` caches the test DB schema across runs, leaving stale schema after migration changes. CI (`ci.yml:93`) passes no DB-caching flags.

**Root cause (secondary, discovered by researcher):** `_make_ad` in `test_sweep_commands.py:63-99` has a bug: `status` is not excluded from the `data` dict (line 81), so `defaults.update(data)` overwrites `status` from DRAFT to the target status, then `Ad.objects.create(**defaults)` inserts with target status + no timestamps — violating the CheckConstraints from migration 0006. This causes INSERT failures even without `--reuse-db`.

**Preferred solution:**
1. Change default `PYTEST_OPTS` in `entrypoint-test.sh:40` from `--reuse-db --create-db --tb=short` to `--tb=short`
2. Update comment at lines 36-38 to reflect new default (no schema caching; pytest-django recreates test DB each run)
3. Fix `_make_ad` bug at `test_sweep_commands.py:81`: exclude `"status"` from `data` dict, and read `status` from `kwargs` in the `update_data` step

**Files to modify:**
- `docker/entrypoint-test.sh:40` (and lines 36-38)
- `src/backend/apps/core/tests/test_sweep_commands.py:81` + line 94-95

**Tests required:**
| Scope | Test File | Test Case | Key Assertions |
|-------|-----------|-----------|----------------|
| Integration | `test_sweep_commands.py` | All 24 tests | 24 pass, 0 errors (was ERRORing at fixture setup) |
| Integration | `test_migrations.py` | `test_makemigrations_check` | passes (no pending migrations) |

**Docs required:** None (entrypoint comment update is code-level, not docs).

---

### TSC-005 (HIGH) — Sweep test mock missing `.exists()`

**Classification:** Already fixed — no action needed.

**Current state:** `_CrashOnDeleteQuerySet` in `test_sweep_commands.py:384-398` already implements `exists()` returning `True` (added in commit `dd116c1`). "Restore original filter" step present at lines 410-411. ✅ Confirmed.

**Tests required:** None.

**Docs required:** None.

---

### TSC-006 (HIGH) — Sync ORM calls in async fixtures

**Classification:** Multiple viable routes

**Current state:** `login_token_factory` (conftest.py:88-92) already fixed with `sync_to_async`. `user` fixture (conftest.py:62-76) still calls `User.objects.get_or_create(...)` synchronously.

**Conflict:** Phase 04 audit says the `user` fixture is functionally safe (sync fixtures run outside the event loop in pytest-asyncio strict mode → `SynchronousOnlyOperation` never raised). Phase 11 audit recommends converting for consistency.

**Preferred solution — Route B:** Convert `user` fixture to `@pytest_asyncio.fixture` + `await sync_to_async(User.objects.get_or_create)(...)`. Add `import pytest_asyncio`. This matches the `login_token_factory` pattern, is consistent with the rest of the async test suite, and is explicitly recommended by the Phase 11 audit.

**Rejected alternative — Route A:** Leave as-is. While functionally safe per Phase 04 audit, it's inconsistent with `login_token_factory` and fragile against pytest-asyncio version changes. The `user` fixture is consumed by 4 `@pytest.mark.asyncio` tests in `test_create_draft_ad.py`.

**Files to modify:** `src/telegram_bot/tests/conftest.py:62-76` — change decorator to `@pytest_asyncio.fixture`, function to `async def`, wrap ORM call with `sync_to_async`, add `import pytest_asyncio`

**Tests required:**
| Scope | Test File | Test Case | Key Assertions |
|-------|-----------|-----------|----------------|
| Integration | `test_create_draft_ad.py` | All 4 tests using `user` fixture | 0 failures from `SynchronousOnlyOperation` |

**Docs required:** None.

---

### TSC-007 (HIGH) — No `--cov` in pytest `addopts`

**Classification:** Simple / Low-risk

**Fix:** Add `--cov` and `--cov-report=term-missing` to `addopts` in `pyproject.toml:157`. Ensures coverage is collected in local/Docker runs and `fail_under = 80` is enforced everywhere.

**Files to modify:** `pyproject.toml:157`

**Tests required:** None (configuration change; `fail_under = 80` enforces coverage threshold on next run).

**Docs required:** None.

---

### TSC-008 (HIGH) — No branch coverage configured

**Classification:** Simple / Low-risk

**Fix:** Add `branch = true` to `[tool.coverage.run]` in `pyproject.toml:166`.

**Files to modify:** `pyproject.toml:166-168` (`[tool.coverage.run]` section)

**Tests required:** None (configuration change). Branch coverage reveals untested branches but does not itself break tests.

**Docs required:** None.

---

### TSC-009 (MEDIUM) — `.env.docker` tracked in git

**Classification:** Already resolved — no action needed.

**Current state:** `.gitignore:148` already lists `.env.docker`. `.env.docker.example` exists and is tracked. `git ls-files .env.docker .env.docker.example` returns only `.env.docker.example` — `.env.docker` is NOT tracked. Makefile:9 correctly references `.env.docker` (runtime file, correct). ✅ Confirmed.

**Tests required:** None.

**Docs required:** None.

---

### TSC-010 (MEDIUM) — Coverage gap on critical-path bot handlers

**Classification:** Complex / High-risk

**Current state:** `ad_create.py` ~16% coverage, `login.py` ~23%, `contact.py` ~27%. AUT-001 (returning=True) already fixed — bot login flow works. TSC-006 (user fixture) must be fixed first.

**Preferred solution:** Create 5 new test files following existing patterns (MagicMock for Message/FSMContext, `permissive_criteria` monkeypatch, `sync_to_async` for ORM, `pytest.mark.django_db(transaction=True)`):

| New File | Scope | Untested Functions Covered |
|----------|-------|--------------------------|
| `test_ad_create_fsm.py` | Tier 1 | `cmd_post`, `process_category`, `process_category_selected`, `proceed_to_features_or_city`, `process_purpose`, `process_features`, `process_city`, `process_title`, `process_description`, `process_price`, `process_photos` |
| `test_ad_create_media.py` | Tier 2 | `save_photo`, `build_purpose_keyboard`, `build_feature_keyboard` |
| `test_ad_create_moderate.py` | Tier 3 | `update_ad_and_moderate`, `translate_all_languages` |
| `test_contact.py` | Tier 4 | `handle_contact_start`, `handle_contact`, `handle_contact_orm` |
| `test_login_deep_link.py` | Tier 5 | `handle_login_deep_link` |

**Files to create:**
- `src/telegram_bot/tests/test_ad_create_fsm.py`
- `src/telegram_bot/tests/test_ad_create_media.py`
- `src/telegram_bot/tests/test_ad_create_moderate.py`
- `src/telegram_bot/tests/test_contact.py`
- `src/telegram_bot/tests/test_login_deep_link.py`

**Tests required:** All tests in the 5 new files (15+ integration tests covering FSM flow, media paths, moderation pass/fail, contact handler, login deep-link).

**Docs required:** None (new test files are self-documenting; follow existing test patterns).

---

### TSC-011 (MEDIUM) — Duplicate test files

**Classification:** Multiple viable routes

**Current state:** Both `test_claim_login_token.py` (7 tests, 209 lines) and `test_login_claim.py` (5 tests, 159 lines) exist. Both test `handle_login_orm` with overlapping scenarios.

**Overlap:** `test_claim_valid_token` ↔ `test_fresh_unclaimed_token`; `test_reject_expired_token` ↔ `test_expired_token_rejected`; `test_reject_already_claimed_token` ↔ `test_claimed_token_rejected`.

**Unique tests:**
- `test_claim_login_token.py`: `test_claim_sets_telegram_id_on_token`, `test_creates_user_on_first_claim`, `test_invalid_token_hash_returns_none`
- `test_login_claim.py`: `test_reclaim_blocked`, `test_consumed_token_rejected`

**Preferred solution — Route A:** Keep `test_login_claim.py` (superior structure: module-level `pytestmark` with `asyncio`, all imports at module level, clear Arrange/Act/Assert comments, matches `test_ad_lifecycle.py` pattern). Delete `test_claim_login_token.py`. Migrate 3 unique tests from the deleted file into `test_login_claim.py`.

**Rejected alternatives:**
- Route B (keep `test_claim_login_token.py`): inferior structure (per-method `@pytest.mark.asyncio`, function-level imports), harder to migrate `test_reclaim_blocked` (compound test) and `test_consumed_token_rejected` (needs `consumed_at` field not in factory).
- Route C (merge into new file): unnecessary churn, both files have merits, same outcome as Route A.

**Files to modify:**
- `src/telegram_bot/tests/test_login_claim.py` — add 3 migrated tests
- Delete `src/telegram_bot/tests/test_claim_login_token.py`

**Tests required:**
| Scope | Test File | Test Case | Key Assertions |
|-------|-----------|-----------|----------------|
| Integration | `test_login_claim.py` | 5 existing + 3 migrated = 8 tests | All pass, no duplicates, covers all scenarios |

**Docs required:** None.

---

### TSC-012 (LOW) — `time.sleep` in tests

**Classification:** Multiple viable routes (LOW severity)

**Current state:**
- `test_query_translator.py:53`: `time.sleep(1)` in `test_timeout_returns_original_query` — tests real ThreadPoolExecutor timeout (500ms) but takes ~0.5s + leaks thread for 1s
- `test_ad_lifecycle.py:327`: `time.sleep(0.01)` in `test_published_at_updates_on_re_publish` — ensures timestamps differ

**Preferred solution:**
- **test_query_translator.py — Route A:** Patch `TRANSLATION_TIMEOUT_SECONDS` to 0.05 and reduce sleep to 0.2s. Keeps real ThreadPoolExecutor timeout mechanism.
- **test_ad_lifecycle.py — Route C:** Replace `time.sleep(0.01)` with direct field manipulation: set `ad.published_at = first_published - timedelta(seconds=10)` + `ad.save(update_fields=["published_at"])`.

**Rejected alternatives:**
- test_query_translator Route C (mock `future.result`): bypasses real timeout mechanism — test name/docstring claims "ThreadPoolExecutor timeout," mocking would test the mock.
- test_ad_lifecycle Route A/B (monkeypatch/freezegun): too complex or adds dependency.

**Files to modify:**
- `src/backend/apps/search/tests/test_query_translator.py:53` (and import for `patch`)
- `src/telegram_bot/tests/test_ad_lifecycle.py:326-327` (remove `import time` + `time.sleep(0.01)`, add `from datetime import timedelta`)

**Tests required:**
| Scope | Test File | Test Case | Key Assertions |
|-------|-----------|-----------|----------------|
| Integration | `test_query_translator.py` | `test_timeout_returns_original_query` | Still returns original query; timeout fires; test <0.1s |
| Integration | `test_ad_lifecycle.py` | `test_published_at_updates_on_re_publish` | published_at updates on re-publish; no time.sleep |

**Docs required:** None.

---

### TSC-013 (LOW) — Inline `import time` in test_ad_lifecycle.py

**Classification:** Simple / Low-risk (moot with TSC-012 Route C)

**Preferred solution:** By adopting TSC-012 Route C (remove the sleep entirely), `import time` is no longer needed. If Route C is not adopted, move `import time` to module level (line 10).

**Files to modify:** `src/telegram_bot/tests/test_ad_lifecycle.py` (handled as part of TSC-012)

**Tests required:** None.

**Docs required:** None.

---

## Prior-Phase Bug Fixes (dependencies of TSC-001)

### SRH-004 (Phase 08, HIGH) — `popular_search` hit_count reset

**Fix:** Change `PopularSearch.objects.update_or_create(..., defaults={"query": query, "hit_count": 1})` to `PopularSearch.objects.get_or_create(..., defaults={"query": query, "hit_count": 1})` in `src/backend/apps/search/services/popular_search.py:37`. With `get_or_create`, `defaults` only apply on CREATE, so the `F("hit_count") + 1` increment on the update path works correctly.

**Files to modify:** `src/backend/apps/search/services/popular_search.py:37`

**Tests required:**
| Scope | Test File | Test Case | Key Assertions |
|-------|-----------|-----------|----------------|
| Integration | `test_autocomplete.py` | `test_increment_popular_search_increments_existing` | hit_count == 3 after 3 calls |

**Docs required:** None.

---

### SRH-007 (Phase 08, LOW) — Rate limiter cache not isolated between tests

**Fix:** Add an `@pytest.fixture(autouse=True)` to `TestAutocompleteEndpoint` class (or module-level) that calls `cache.clear()` before each test. Currently only `test_autocomplete_rate_limit` (line 175) calls `cache.clear()`.

**Files to modify:** `src/backend/apps/search/tests/test_autocomplete.py` — add autouse cache.clear fixture

**Tests required:**
| Scope | Test File | Test Case | Key Assertions |
|-------|-----------|-----------|----------------|
| Integration | `test_autocomplete.py` | `test_autocomplete_deduplication`, `test_autocomplete_anonymous_user_returns_popular_and_entities`, `test_autocomplete_malicious_query_sanitized` | All pass (previously 429 due to leaked rate limit) |

**Docs required:** None.

---

### SRH-011 (Phase 08, LOW) — Alert query test fixture description contains search term

**Fix:** Change the default `description` in `_create_published_ad` at `test_alert_query.py:98` from `"Продается детский велосипед"` (contains "велосипед") to a generic description like `"Продается товар описание для теста"` (does not contain any search term).

**Files to modify:** `src/backend/apps/search/tests/test_alert_query.py:98`

**Tests required:**
| Scope | Test File | Test Case | Key Assertions |
|-------|-----------|-----------|----------------|
| Integration | `test_alert_query.py` | `test_returns_matching_ads_by_query`, `test_excludes_non_matching_ads` | Correct match count (1 and 0 respectively) |

**Docs required:** None.

---

## Implementation Wave Plan

| Wave | Findings | Files | Rationale |
|------|----------|-------|----------|
| 1 | TSC-007, TSC-008, TSC-002, SRH-004 | `pyproject.toml`, `test_media_security.py`, `popular_search.py` | Independent, different files, trivial fixes |
| 2 | TSC-003, TSC-004, TSC-006, TSC-012, SRH-007, SRH-011 | `models.py`, `entrypoint-test.sh`, `test_sweep_commands.py`, `conftest.py`, `test_query_translator.py`, `test_ad_lifecycle.py`, `test_autocomplete.py`, `test_alert_query.py` | Different files, no conflicts. TSC-003 (model) + TSC-004 (_make_ad) are related but touch different files. |
| 3 | TSC-011 | `test_login_claim.py`, `test_claim_login_token.py` | Depends on TSC-006 (conftest fixtures) |
| 4 | TSC-010 | 5 new test files | Depends on TSC-006 (user fixture) + AUT-001 (already fixed) |
| 5 | TSC-001 | (verification only) | Depends on all above + prior-phase fixes |

**No circular dependencies.** TSC-012 Route C eliminates TSC-013 entirely. TCC-003 (model constraints) precedes TSC-004 (_make_ad fix) to ensure the test helper respects the constraints it depends on.
