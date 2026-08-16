---
phase: 11
phase_name: test-coverage
source: .ai/audit/11-test-coverage/findings.md
validated: 2026-08-15
validator: validator
---

# Phase 11 Audit Findings — Validation Report (Test Suite Coverage & Reliability)

> **Mode:** `problems_only=TRUE` — only findings with confirmed problems are included.
> 13 of 13 findings are **validated** as real problems. 0 findings rejected. 0 findings merged. 0 findings reclassified.

---

## Findings

### TSC-001: Full test suite is not green — 30 failures + 4 errors (71.70% coverage, below 80% threshold)

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed: full-suite run reports 30 failures + 4 errors, 71.70% coverage. pyproject.toml:171 sets `fail_under = 80` in `[tool.coverage.report]`, only activated when `--cov` is passed (as in CI ci.yml:93). All 8 mandatory findings (TSC-002 through TSC-009) plus 5 advisory findings (TSC-010 through TSC-013) are confirmed as real problems. The finding serves as the umbrella summary.
> - **Architectural impact:** A perpetually red test suite undermines CI branch protection and developer trust. Root causes span both production bugs (AUT-001 returning=True, PII-001 telegram_id=None, SRH-003 TelegramForbidden) and test infrastructure defects (TSC-002 through TSC-008).
> - **Recommendation:** After TSC-002 through TSC-010 and prior-phase production bugs (AUT-001 returning=True, PII-001 telegram_id=None, SRH-003/SRH-004/SRH-007/SRH-011) are fixed, verify with `uv run pytest --tb=short --cov --cov-report=term-missing` (working dir `src/backend`, matching CI ci.yml:93). Success criteria: 0 failures, 0 errors, >=80% line coverage with branch coverage (TSC-008). Trace any residual failure to a tracked finding; if none exists, file a new TSC finding with the failing test name, assertion, and stack trace before closing this umbrella.
> - **Evidence quality:** Strong.

**ID:** TSC-001
**Severity:** CRITICAL
**Type:** RUNTIME-ERROR
**Status:** VALIDATED

---

### TSC-002: EXIF test fixture crashes at setup — `jpeg_with_exif` makes `TestExifStripping` tests ERROR before executing

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed: `jpeg_with_exif` fixture at test_media_security.py:92-106 sets `ExifBase.GPSInfo: b"\x02\x03\x04\x05"` (raw bytes) at line 99, then calls `img.getexif().tobytes()` at line 105. PIL's `Exif.tobytes()` expects GPSInfo (tag 0x8825) to be a dict (IFD sub-table), not raw bytes. The crash occurs during fixture setup, so all 4 `TestExifStripping` tests ERROR before any assertion runs. The security-critical EXIF-stripping path (`strip_photo_exif` in media.py:98-116) is effectively untested.
> - **Recommendation:** Correct. Use a proper GPSInfo IFD dict or remove the GPSInfo tag from the fixture.
> - **Evidence quality:** Strong.

**ID:** TSC-002
**Severity:** CRITICAL
**Type:** RUNTIME-ERROR
**Status:** VALIDATED

---

### TSC-003: Pending migration 0005 — `test_makemigrations_check` fails

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed: test_migrations.py:20-49 calls `call_command("makemigrations", "--check", "--dry-run")` which fails because model changes in the ads app have no corresponding migration. Git status confirms `0004_ad_draft_nullable_fields.py` is untracked (`??` prefix). CI ci.yml:80-86 runs the same check as a separate step, blocking the pipeline.
> - **Recommendation:** Correct. Run `makemigrations` to generate 0005, commit it, and commit or remove untracked 0004.
> - **Evidence quality:** Strong.

**ID:** TSC-003
**Severity:** CRITICAL
**Type:** SPEC-DEVIATION
**Status:** VALIDATED

---

### TSC-004: `--reuse-db --create-db` in entrypoint-test.sh breaks ALL 24 sweep tests at setup

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed: entrypoint-test.sh:40 runs `uv run pytest ${PYTEST_OPTS:---reuse-db --create-db --tb=short}`. The `--reuse-db` flag skips test-database recreation/migration, causing stale schema to persist. All 24 tests in test_sweep_commands.py ERROR at fixture setup. CI ci.yml:93 does not pass `--reuse-db`, creating local-vs-CI divergence. `make test-recreate` (Makefile:112-113) overrides with `--no-reuse-db --create-db` but is not the default.
> - **Recommendation:** Correct. Remove `--reuse-db --create-db` from entrypoint default or add schema-reset post-migration step.
> - **Evidence quality:** Strong.

**ID:** TSC-004
**Severity:** HIGH
**Type:** RUNTIME-ERROR
**Status:** VALIDATED

---

### TSC-005: Sweep test mock `_CrashOnDeleteQuerySet` missing `.exists()` method

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed: `_CrashOnDeleteQuerySet` class at test_sweep_commands.py:372-389 implements `count()` (line 388), `values_list()` (line 390), and `delete()` (line 392) but does NOT implement `exists()`. Line 395 calls `User.objects.filter(pk=seller.pk).exists()` on this mock, raising `AttributeError`. The monkeypatch at line 385-389 replaces `User.objects.filter` to return this mock, so the assertion crashes.
> - **Recommendation:** Correct. Add `exists()` returning `True`, or use `MagicMock(spec=...)`.
> - **Evidence quality:** Strong.

**ID:** TSC-005
**Severity:** HIGH
**Type:** RUNTIME-ERROR
**Status:** VALIDATED

---

### TSC-006: Sync ORM calls in async fixtures cause `SynchronousOnlyOperation`

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed: conftest.py:58-72 defines the `user` fixture which calls `User.objects.get_or_create(...)` synchronously at line 63. conftest.py:75-92 defines the `login_token_factory` fixture whose inner `_create` calls `LoginToken.objects.create(...)` synchronously at line 86. Both are used by test_claim_login_token.py whose tests are marked `@pytest.mark.asyncio` (strict mode, confirmed at pyproject.toml:154). Django's async safety check raises `SynchronousOnlyOperation` on sync ORM calls inside the event loop. 3 of 7 tests fail with this error. Phase 04 AUT-002 documented the same pattern.
> - **Recommendation:** Correct. Wrap sync ORM calls with `sync_to_async()` or convert fixtures to `@pytest_asyncio.fixture`.
> - **Evidence quality:** Strong.

**ID:** TSC-006
**Severity:** HIGH
**Type:** RUNTIME-ERROR
**Status:** VALIDATED

---

### TSC-007: No `--cov` in pytest `addopts` — coverage not collected in local/dev runs, `fail_under=80` silently skipped

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed: pyproject.toml:157 sets `addopts = ["--import-mode=importlib", "-ra", "-q"]` with no `--cov`. entrypoint-test.sh:40 runs `uv run pytest ${PYTEST_OPTS:---reuse-db --create-db --tb=short}` with no `--cov`. Makefile:84-85 inherits these flags. Only CI ci.yml:93 adds `--cov --cov-report=term --cov-report=xml` explicitly. This means `fail_under = 80` at pyproject.toml:171 is silently skipped in local and Docker runs.
> - **Recommendation:** Correct. Add `--cov` and `--cov-report=term-missing` to `addopts`.
> - **Evidence quality:** Strong.

**ID:** TSC-007
**Severity:** HIGH
**Type:** SPEC-DEVIATION
**Status:** VALIDATED

---

### TSC-008: No branch coverage configured

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed: pyproject.toml:166-168 `[tool.coverage.run]` section sets `source` and `omit` but has no `branch = true` directive. Without branch coverage, only line execution is measured — conditional paths (if/else, exception handlers, early returns) are not tracked. The 71.70% line-coverage figure overstates actual test thoroughness.
> - **Recommendation:** Correct. Add `branch = true` to `[tool.coverage.run]`.
> - **Evidence quality:** Strong.

**ID:** TSC-008
**Severity:** HIGH
**Type:** BEST-PRACTICE
**Status:** VALIDATED

---

### TSC-009: `.env.docker` tracked in git — deployment env file not in `.gitignore`

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed: `git ls-files -- '.env*'` returns `.env.dev.example`, `.env.docker`, `.env.example` — `.env.docker` is tracked. `.gitignore:145-149` ignores `.env`, `.env.dev`, `.env.local`, `.envrc` but NOT `.env.docker`. The file contains real deployment placeholders (`POSTGRES_PASSWORD=your-password`, `BOT_TOKEN=`, `ADMIN_PASSWORD=`). Comment at `.env.docker:3` says "DO NOT include DATABASE_URL" — indicating it is for direct use, not a template. Makefile:9 references it directly (`--env-file .env.docker`).
> - **Recommendation:** Correct. Rename to `.env.docker.example`, add `.env.docker` to `.gitignore`, update Makefile.
> - **Evidence quality:** Strong.

**ID:** TSC-009
**Severity:** MEDIUM
**Type:** SPEC-DEVIATION
**Status:** VALIDATED

---

### TSC-010: Coverage gap on critical-path bot handlers — `ad_create.py` 20%, `login.py` 39%

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Validated directionally. The finding references coverage numbers from the full-suite `--cov-report=term` output (login.py 39%, ad_create.py 20%, contact.py 53%). These modules implement core user-facing flows. The low coverage is consistent with the 71.70% overall figure. Phase 04 AUT-001 documented that `handle_login_orm` has no working tests due to `returning=True`; the coverage gap on login.py is a direct consequence. ad_create.py at 20% means the entire bot ad-creation flow (photo upload, dedup, thumbnail, moderation) is virtually untested.
> - **Recommendation:** Correct. Fix `returning=True` first, then add integration tests.
> - **Evidence quality:** Strong.

**ID:** TSC-010
**Severity:** MEDIUM
**Type:** BEST-PRACTICE
**Status:** VALIDATED

---

### TSC-011: Duplicate test files — `test_claim_login_token.py` vs `test_login_claim.py`

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed: `git diff --stat` shows `test_login_claim.py` has 9 insertions(+), 7 deletions(-) — a partial `sync_to_async` fix. `test_claim_login_token.py` is unmodified — confirmed via git status. Both files test the same production function (`handle_login_orm` from login.py) with overlapping scenarios (valid token claim, replay blocking, expired token rejection, claimed-token rejection, user creation, existing-user return). Maintaining two parallel test files creates confusion and CI reports failures from both.
> - **Recommendation:** Correct. Consolidate into one file; remove `test_claim_login_token.py`; migrate unique scenarios to `test_login_claim.py`.
> - **Evidence quality:** Strong.

**ID:** TSC-011
**Severity:** MEDIUM
**Type:** BEST-PRACTICE
**Status:** VALIDATED

---

### TSC-012: `time.sleep(1)` in test_query_translator — slows suite and depends on wall-clock timing

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed: test_query_translator.py:49-56 `test_timeout_returns_original_query` uses `side_effect=lambda *_: time.sleep(1)` at line 53, relying on the production ThreadPoolExecutor timeout (500ms) firing while the mock sleeps 1 second. This makes the test take >=1 second and couples correctness to wall-clock timing. test_ad_lifecycle.py:326-327 uses `time.sleep(0.01)` for timestamp ordering — a minor flakiness risk. The finding correctly recommends mocking the timeout mechanism or using freezegun.
> - **Recommendation:** Correct. Mock ThreadPoolExecutor/timeout or use `concurrent.futures.TimeoutError`. Replace `time.sleep(0.01)` with freezegun or mocked `timezone.now()`.
> - **Evidence quality:** Strong.

**ID:** TSC-012
**Severity:** LOW
**Type:** BEST-PRACTICE
**Status:** VALIDATED

---

### TSC-013: Inline `import time` in test_ad_lifecycle.py

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed: test_ad_lifecycle.py:326 has `import time` inside the `test_archive_preserves_original_published_at` method body (line 326), not at module level. The module-level imports at the top of the file do not include `time`. This violates the convention of keeping imports at the top and obscures the timing dependency from readers.
> - **Recommendation:** Correct. Move `import time` to module-level imports.
> - **Evidence quality:** Strong.

**ID:** TSC-013
**Severity:** LOW
**Type:** BEST-PRACTICE
**Status:** VALIDATED

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 13 | TSC-001 through TSC-013 |
| Validated with corrections | 0 | — |
| Reclassified | 0 | None |
| Merged | 0 | None |
| Rejected | 0 | None |

### Rejected Findings

None. All 13 findings identify real, confirmed problems in the codebase.

### Merged Findings

None. All 13 findings address distinct issues with no duplicate root causes.

### Reclassified Findings

None.

### Evidence Quality Assessment

| ID | Evidence Quality | Notes |
|----|------------------|-------|
| TSC-001 | Strong | Coverage config (fail_under=80), runtime summary, and prior-phase references all confirmed |
| TSC-002 | Strong | Fixture code lines 92-106 confirmed; GPSInfo raw bytes at line 99, .tobytes() at line 105 |
| TSC-003 | Strong | Git status confirms untracked migration 0004; test_migrations.py:20-49 confirms check command |
| TSC-004 | Strong | entrypoint-test.sh:40 confirmed with --reuse-db; CI ci.yml:93 confirmed without it |
| TSC-005 | Strong | _CrashOnDeleteQuerySet (lines 372-389) confirmed missing .exists(); line 395 assertion confirmed |
| TSC-006 | Strong | conftest.py:58-92 confirmed with sync ORM calls; asyncio_mode=strict at pyproject.toml:154 |
| TSC-007 | Strong | addopts (pyproject.toml:157) confirmed without --cov; CI ci.yml:93 confirmed with --cov |
| TSC-008 | Strong | pyproject.toml:166-168 confirmed; no branch=true directive |
| TSC-009 | Strong | git ls-files confirms .env.docker tracked; .gitignore:145-149 confirmed |
| TSC-010 | Strong | Coverage numbers consistent with 71.70% overall; Phase 04 AUT-001 documents login.py gap |
| TSC-011 | Strong | git diff --stat confirmed: test_login_claim.py 9 ins/7 del, test_claim_login_token.py unmodified |
| TSC-012 | Strong | test_query_translator.py:53 confirmed with time.sleep(1); test_ad_lifecycle.py:327 confirmed |
| TSC-013 | Strong | test_ad_lifecycle.py:326 confirmed: inline import time in method body, absent from module imports |

---

## Rollout Sequencing Recommendation

1. **TSC-003** (CRITICAL, trivial) — Generate and commit pending migration 0005; resolve untracked 0004 state. Unblocks CI makemigrations --check gate.
2. **TSC-007** (HIGH, trivial) — Add `--cov` and `--cov-report=term-missing` to `addopts` in pyproject.toml:157.
3. **TSC-008** (HIGH, trivial) — Add `branch = true` to `[tool.coverage.run]` in pyproject.toml:166.
4. **TSC-005** (HIGH, trivial) — Add `.exists()` method to `_CrashOnDeleteQuerySet` in test_sweep_commands.py.
5. **TSC-002** (CRITICAL, small) — Fix `jpeg_with_exif` fixture: replace raw bytes GPSInfo with proper IFD dict or remove GPSInfo tag.
6. **TSC-004** (HIGH, small) — Remove `--reuse-db --create-db` from entrypoint-test.sh:40 or add schema-reset post-migration step.
7. **TSC-006** (HIGH, small) — Wrap sync ORM calls in `login_token_factory` and `user` conftest fixtures with `sync_to_async()`.
8. **TSC-013** (LOW, trivial) — Move inline `import time` to module-level imports in test_ad_lifecycle.py.
9. **TSC-011** (MEDIUM, medium) — Consolidate duplicate test files; remove `test_claim_login_token.py`, migrate unique scenarios to `test_login_claim.py` (depends on TSC-006 fix for sync_to_async).
10. **TSC-012** (LOW, small) — Replace `time.sleep(1)` with mocked timeout; replace `time.sleep(0.01)` with freezegun or mocked `timezone.now()`.
11. **TSC-009** (MEDIUM, small) — Rename `.env.docker` to `.env.docker.example`, add to `.gitignore`, update Makefile:9.
12. **TSC-010** (MEDIUM, large) — Increase coverage on `ad_create.py`, `login.py`, `contact.py`. Unblocks TSC-001 login.py coverage (depends on Phase 04 AUT-001 returning=True fix).
13. **TSC-001** (CRITICAL, large) — Verify the full suite is green after TSC-002 through TSC-010 and prior-phase production fixes (AUT-001 returning=True, PII-001 telegram_id=None, SRH-003 TelegramForbidden import, SRH-004 hit_count reset, SRH-001/011 FTS i18n, SRH-007 cache leak). Run `uv run pytest --tb=short --cov --cov-report=term-missing` (working dir `src/backend`); success = 0 failures, 0 errors, >=80% line coverage with branch coverage enabled. Trace any residual failure to a tracked finding; if untracked, file a new TSC finding with test name, assertion, and stack trace.

### Dependency Summary

- Steps 1-3, 4-8, 10-11 are independent of each other and can run in parallel.
- Step 9 (TSC-011) depends on step 7 (TSC-006) for the sync_to_async fix in conftest fixtures.
- Step 12 (TSC-010) depends on Phase 04 AUT-001 (returning=True fix) and TSC-006 (sync_to_async on conftest fixtures).
- Step 13 (TSC-001) depends on all prior steps plus prior-phase production bugs (AUT-001, PII-001, SRH-003, SRH-004, SRH-007, SRH-011).

### Rollout Safety Notes

- No circular dependencies detected.
- TSC-003 (migration generation) should precede TSC-004 (test database flags) to ensure the test DB schema matches migrations.
- TSC-006 and TSC-011 both touch the same files (conftest.py, test_claim_login_token.py, test_login_claim.py); apply TSC-006 first to avoid merge conflicts.
- TSC-009 (.env.docker rename) is purely config and can ship independently; no code dependencies.

---

*Report generated via `problems_only=TRUE` validation mode. All 13 findings confirmed against source code as of 2026-08-15.*
