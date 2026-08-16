---
name: audit-findings
description: Phase 11 Test Coverage audit findings
agent: audit-executor
alwaysApply: false
---

# Phase 11 Audit Findings — Test Suite Coverage & Reliability

**Executor:** audit-executor
**Template:** .kilo/commands/audit/phases/11-audit-test-coverage.md
**Status:** complete
**Validated:** no

---

## Runtime Verification Summary

Test suite executed against real PostgreSQL 18 on `127.0.0.1:5432` (database `mko_bazuna`).
Test database: `test_mko_bazuna` (pytest-django auto-created).

**Full-suite result:** 30 failed, 4 errors, 71.70% coverage (773 tests collected).
**`fail_under` threshold:** 80% (configured in `[tool.coverage.report]`, enforced only when `--cov` is passed — CI passes it, local `make test`/entrypoint does not).

### Test failure breakdown

| Test file | Failures | Root cause |
|---|---|---|
| test_claim_login_token.py | 7 | `FieldDoesNotExist` (returning=True) + `SynchronousOnlyOperation` in fixtures (Phase 04 AUT-001/AUT-002) |
| test_login_claim.py | 5 | Same `returning=True` bug; sync async partially patched but production bug unblocks none |
| test_deletion.py | 3 | `NotNullViolation` from `telegram_id=None` on NOT NULL field (Phase 06 PII-001) |
| test_consent.py | 3 | Same NOT NULL violation via `withdraw_consent` |
| test_migrations.py | 1 | Pending migration 0005 (schema drift) |
| test_sweep_commands.py | 1 (+24 ERRORS w/ --reuse-db) | Mock missing `.exists()`; `--reuse-db` breaks all at setup |
| test_media_security.py | 4 errors | EXIF fixture crashes at setup |
| test_alert_query.py | 2 | FTS trigger missing i18n; fixture description contains search term (Phase 08 SRH-001/SRH-011) |
| test_autocomplete.py | 3 | Rate-limiter cache leak (Phase 08 SRH-007) |
| test_popular_search.py | 1 | hit_count reset bug (Phase 08 SRH-004) |
| send_alerts command tests | 2 | `TelegramForbidden` import error (Phase 08 SRH-003) |

---

## Findings

### TSC-001: Full test suite is not green — 30 failures + 4 errors (71.70% coverage, below 80% threshold)

| Field | Value |
|-------|-------|
| **ID** | TSC-001 |
| **Severity** | CRITICAL |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/** (entire test suite) |
| **Classification** | mandatory |

**Description:**

The full test suite produces 30 failures and 4 errors across 773 tests, with 71.70% coverage — below the configured `fail_under = 80` threshold. A test suite that is perpetually red cannot serve as a safety net: developers either ignore failures (risking regressions slipping through) or treat them as noise (breaking branch-protection gates). The failures stem from a mix of prior-phase production bugs (AUT-001 `returning=True`, PII-001 `telegram_id=None`, SRH-003 `TelegramForbidden`, SRH-004 `hit_count` reset, SRH-001 FTS i18n, SRH-007 cache leak, SRH-011 fixture description) and genuine test-infrastructure defects (broken fixtures, mock gaps, `--reuse-db` incompatibility — see TSC-002 through TSC-008). Resolving the production bugs alone will not yield a green suite; the test bugs must also be fixed.

**Evidence:**

- Full-suite run output: `30 failed, 4 errors, 71.70% coverage` (71.70% < 80% `fail_under`).
- Targeted coverage by module:
  - `telegram_bot/handlers/login.py` — 39% (3 of 5 functions untested due to crash)
  - `telegram_bot/handlers/ad_create.py` — 20% (bot ad-creation flow virtually untested)
  - `apps/core/services/contact.py` — 53%
- `[tool.coverage.report]` at `pyproject.toml:170-171`: `fail_under = 80`.
- `[tool.coverage.run]` at `pyproject.toml:166-168`: `source = ["src/backend", "src/telegram_bot"]`.
- Phase 06 findings (line 28): `20 failed, 42 passed (67 total)` in targeted run — same root causes.

**Recommendation:**

Address all findings TSC-002 through TSC-008, plus the prior-phase production bugs (AUT-001, PII-001, SRH-003, SRH-004, SRH-007, SRH-011). After fixes, the suite should be 100% green with ≥80% coverage (line + branch). Add a CI status check comment to PRs to surface per-branch coverage diffs.

Effort: large. Priority: mandatory.

---

### TSC-002: EXIF test fixture crashes at setup — `jpeg_with_exif` makes `TestExifStripping` tests ERROR before executing

| Field | Value |
|-------|-------|
| **ID** | TSC-002 |
| **Severity** | CRITICAL |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/backend/apps/ads/tests/test_media_security.py:92-106 |
| **Classification** | mandatory |

**Description:**

The `jpeg_with_exif` fixture at `test_media_security.py:92-106` builds an EXIF dictionary with `ExifBase.GPSInfo` set to raw bytes (`b"\x02\x03\x04\x05"`). It then calls `img.getexif().tobytes()`. PIL's `Exif.tobytes()` expects the GPSInfo tag (0x8825) to be a dict (an IFD sub-table), not a raw bytes object. When it encounters bytes, it attempts internal IFD serialization and raises `AttributeError: 'Exif' object has no attribute 'fp'` during fixture setup.

This means all `TestExifStripping` tests (4 tests at lines 289-331) ERROR at fixture setup — they never execute a single assertion. The EXIF-stripping function (`strip_photo_exif` in `media.py:98-116`) is effectively untested, despite being a security-critical PII-erasure path. Phase 07 finding MED-006 already noted the gap (isolation-only testing), but the fixture crash is a distinct defect that makes even the isolation tests non-functional.

**Evidence:**

- `test_media_security.py:96-106`:
  ```python
  exif_dict = {
      ExifBase.Make: "CameraMaker",
      ExifBase.Model: "CameraModel",
      ExifBase.GPSInfo: b"\x02\x03\x04\x05",  # Mock GPS data
  }
  exif_bytes = img.getexif()
  for tag, value in exif_dict.items():
      exif_bytes[tag] = value
  img.save(buf, format="JPEG", exif=exif_bytes.tobytes())  # CRASHES here
  ```
- Runtime: 4 `ERROR`s at fixture setup with `AttributeError: 'Exif' object has no attribute 'fp'`.
- Phase 07 MED-006 noted the EXIF-stripping test gap but did not catch the fixture-level crash.

**Recommendation:**

Fix the fixture to use a proper GPSInfo IFD dict (e.g., `{"GPSLatitude": "43/1", "GPSLongitude": "15/1"}`) or remove the GPSInfo tag entirely. Then re-enable the `TestExifStripping` tests that currently ERROR. Add an integration test that calls `save_photo()` with an EXIF-bearing JPEG and verifies the on-disk file is stripped (Phase 07 MED-006 recommendation).

Effort: small. Priority: mandatory.

---

### TSC-003: Pending migration 0005 — `test_makemigrations_check` fails

| Field | Value |
|-------|-------|
| **ID** | TSC-003 |
| **Severity** | CRITICAL |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | apps/ads/models.py, apps/ads/migrations/ |
| **Classification** | mandatory |

**Description:**

`test_makemigrations_check` at `test_migrations.py:20-49` invokes `call_command("makemigrations", "--check", "--dry-run")` and fails because there are model changes in the `ads` app with no corresponding migration file. The pending migration `0005_alter_ad_category_name_alter_ad_description_and_more.py` would alter `Ad.category_name`, `Ad.description`, and `Ad.title` fields. This is the same schema-drift issue flagged in Phase 06 (PII-010 migration test).

In CI, the workflow `ci.yml:80-86` runs `makemigrations --check --dry-run` as a separate step, which would fail before tests even run — blocking the entire CI pipeline.

**Evidence:**

- `test_migrations.py:20-49`: `test_makemigrations_check` catches `SystemExit` and calls `pytest.fail(...)` if exit code != 0.
- CI `ci.yml:80-86`: `uv run python -m django makemigrations --check --dry-run`.
- `untracked: src/backend/apps/ads/migrations/0004_ad_draft_nullable_fields.py` exists on disk but is untracked — migrations directory is in an inconsistent state.
- Phase 06 findings (line 39): `test_migrations.py — 1 failure — Pending migrations (schema drift in ads app)`.

**Recommendation:**

Run `makemigrations` to generate the pending `0005` migration, commit it, and verify `test_makemigrations_check` passes. The untracked `0004_ad_draft_nullable_fields.py` should either be committed or removed — a half-applied migration state is dangerous for reproducibility.

Effort: trivial. Priority: mandatory.

---

### TSC-004: `--reuse-db --create-db` in entrypoint-test.sh breaks ALL 24 sweep tests at setup

| Field | Value |
|-------|-------|
| **ID** | TSC-004 |
| **Severity** | HIGH |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | docker/entrypoint-test.sh:40, apps/core/tests/test_sweep_commands.py |
| **Classification** | mandatory |

**Description:**

The Docker test entrypoint (`entrypoint-test.sh:40`) runs `uv run pytest ${PYTEST_OPTS:---reuse-db --create-db --tb=short}`. The `--reuse-db` flag tells pytest-django to skip test-database creation if `test_mko_bazuna` already exists. When the database persists between runs (as designed by `make test-db`), the existing test DB may have stale schema or data. With `--reuse-db`, pytest-django does not re-run migrations, so fixtures that expect a fresh schema state fail at setup.

Result: ALL 24 tests in `test_sweep_commands.py` ERROR at fixture setup. The `make test-recreate` target (`Makefile:112-113`) works around this by passing `--no-reuse-db --create-db`, but this is not the default and not documented in `make test` help text.

CI (`ci.yml:93`) runs `uv run pytest --tb=short --cov --cov-report=term --cov-report=xml` — no `--reuse-db` flags, so CI does not exhibit this failure. This creates a local-vs-CI divergence: developers see 24 ERRORS locally but CI appears green (modulo the 6 actual failures that exist in both).

**Evidence:**

- `entrypoint-test.sh:40`: `uv run pytest ${PYTEST_OPTS:---reuse-db --create-db --tb=short}`.
- `Makefile:83-85`: `test` target runs `docker compose ... run --rm test` (uses default entrypoint flags).
- `Makefile:112-113`: `test-recreate` target overrides with `--no-reuse-db --create-db`.
- Targeted run without `--reuse-db`: 23 passed, 1 failed.
- Targeted run with `--reuse-db`: 0 passed, 24 errors at setup.
- CI `ci.yml:93`: no `--reuse-db` or `--create-db` flags.

**Recommendation:**

Remove `--reuse-db --create-db` from the entrypoint default and let pytest-django manage the test database lifecycle per run. If `--reuse-db` is desired for fast iteration, add a post-migration schema-validation step, or require developers to use `make test-recreate` when the schema changes. At minimum, document the divergence in `entrypoint-test.sh` comments.

Effort: small. Priority: mandatory.

---

### TSC-005: Sweep test mock `_CrashOnDeleteQuerySet` missing `.exists()` method

| Field | Value |
|-------|-------|
| **ID** | TSC-005 |
| **Severity** | HIGH |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/backend/apps/core/tests/test_sweep_commands.py:372-389, 395 |
| **Classification** | mandatory |

**Description:**

The `_CrashOnDeleteQuerySet` class at `test_sweep_commands.py:372` is a mock queryset designed to crash on `.delete()` while allowing `.count()` and `.values_list()`. However, line 395 asserts `User.objects.filter(pk=seller.pk).exists()` — calling `.exists()` on the mock. Since the mock does not implement `.exists()`, it raises `AttributeError`. The `monkeypatch` at line 385-389 replaces `User.objects.filter` to return this mock, so the assertion at line 395 (which calls `.exists()`) crashes.

**Evidence:**

- `test_sweep_commands.py:372-383`:
  ```python
  class _CrashOnDeleteQuerySet:
      def __init__(self, target_pk):
          self._target_pk = target_pk
      def count(self):
          return 1
      def values_list(self, *args, **kwargs):
          return [self._target_pk]
      def delete(self):
          raise RuntimeError("Simulated crash during delete")
  ```
- `test_sweep_commands.py:385-389`: `monkeypatch.setattr(User.objects, "filter", lambda *args, **kwargs: _CrashOnDeleteQuerySet(seller.pk))`
- `test_sweep_commands.py:395`: `assert User.objects.filter(pk=seller.pk).exists()` — `exists()` is not defined on the mock.
- Targeted run: `test_crash_between_updates_and_delete_rolls_back` fails with `AttributeError: '_CrashOnDeleteQuerySet' object has no attribute 'exists'`.

**Recommendation:**

Add an `exists()` method to `_CrashOnDeleteQuerySet` that returns `True` (since the mock simulates a user that exists). Alternatively, use `unittest.mock.MagicMock(spec=User.objects.filter(...))` to auto-generate all queryset methods.

Effort: trivial. Priority: mandatory.

---

### TSC-006: Sync ORM calls in async fixtures cause `SynchronousOnlyOperation`

| Field | Value |
|-------|-------|
| **ID** | TSC-006 |
| **Severity** | HIGH |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/telegram_bot/tests/conftest.py:58-72, 75-91; src/telegram_bot/tests/test_claim_login_token.py |
| **Classification** | mandatory |

**Description:**

The `login_token_factory` fixture (`conftest.py:75-91`) defines an inner `_create` function that calls `LoginToken.objects.create()` synchronously. The `user` fixture (`conftest.py:58-72`) calls `User.objects.get_or_create()` synchronously. Both are used by `test_claim_login_token.py`, whose tests are marked `@pytest.mark.asyncio` (async). In pytest-asyncio strict mode, Django's async safety check raises `SynchronousOnlyOperation: You cannot call this from an async context - use a thread or sync_to_async` when sync ORM calls execute inside the event loop.

3 of 7 tests in `test_claim_login_token.py` fail with this error. The sibling file `test_login_claim.py` was partially fixed (working tree modification adds `sync_to_async` wrappers and `pytest.mark.asyncio` to `pytestmark`), but `test_claim_login_token.py` and the conftest fixtures remain unfixed.

**Evidence:**

- `conftest.py:84-89`: `_create` calls `LoginToken.objects.create(...)` synchronously.
- `conftest.py:63-71`: `user` fixture calls `User.objects.get_or_create(...)` synchronously.
- `test_claim_login_token.py:24-28`: `@pytest.mark.asyncio` on `test_claim_valid_token` uses `login_token_factory`.
- Runtime: `SynchronousOnlyOperation` on 3 tests.
- Phase 04 AUT-002 documented this same issue.

**Recommendation:**

Wrap all sync ORM calls in the `login_token_factory` and `user` fixtures with `sync_to_async()`, or convert the fixtures to `@pytest_asyncio.fixture` async fixtures.

Effort: small. Priority: mandatory.

---

### TSC-007: No `--cov` in pytest `addopts` — coverage not collected in local/dev runs, `fail_under=80` silently skipped

| Field | Value |
|-------|-------|
| **ID** | TSC-007 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | pyproject.toml:157, docker/entrypoint-test.sh:40, Makefile:83-85 |
| **Classification** | mandatory |

**Description:**

The `addopts` in `pyproject.toml:157` is `["--import-mode=importlib","-ra", "-q"]` — it does NOT include `--cov`. This means when developers run `pytest` locally (or via `make test` → `entrypoint-test.sh`), no coverage data is collected. The `fail_under = 80` threshold in `[tool.coverage.report]` is only activated when `--cov` is passed, which only happens in CI (`ci.yml:93`).

The entrypoint (`entrypoint-test.sh:40`) runs `uv run pytest ${PYTEST_OPTS:---reuse-db --create-db --tb=short}` — also no `--cov`. A developer can reduce coverage to 0% and never know locally; only CI catches it, and CI is already red from test failures (TSC-001). There is no mechanism to gradually improve coverage in a dev workflow — the gate is all-or-nothing and only runs in CI.

**Evidence:**

- `pyproject.toml:157`: `addopts = ["--import-mode=importlib","-ra", "-q"]` — no `--cov`.
- `entrypoint-test.sh:40`: `uv run pytest ${PYTEST_OPTS:---reuse-db --create-db --tb=short}` — no `--cov`.
- `Makefile:84-85`: `test` target runs `docker compose ... run --rm test` — inherits entrypoint flags, no `--cov`.
- `ci.yml:93`: `uv run pytest --tb=short --cov --cov-report=term --cov-report=xml` — CI adds `--cov` explicitly.
- `[tool.coverage.report]` at `pyproject.toml:170-173`: `fail_under = 80` — only active when `--cov` is passed.

**Recommendation:**

Add `--cov` and `--cov-report=term-missing` to the `addopts` list in `pyproject.toml`. This makes every `pytest` invocation — local, Docker, and CI — collect coverage and enforce the 80% threshold. The CI workflow can then drop its redundant `--cov` flag.

Effort: trivial. Priority: mandatory.

---

### TSC-008: No branch coverage configured

| Field | Value |
|-------|-------|
| **ID** | TSC-008 |
| **Severity** | HIGH |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | pyproject.toml:166-168 |
| **Classification** | advisory |

**Description:**

`[tool.coverage.run]` at `pyproject.toml:166-168` configures `source` and `omit` but does NOT set `branch = true`. Without branch coverage, conditional paths (e.g., `if`/`else` branches, exception handlers, early returns) are not tracked — only line execution is measured. A function with 100% line coverage could still have 0% branch coverage if the `else` path is never taken. This means the 71.70% line-coverage figure overstates actual test thoroughness.

**Evidence:**

- `pyproject.toml:166-168`:
  ```toml
  [tool.coverage.run]
  source = ["src/backend", "src/telegram_bot"]
  omit = ["*/migrations/*", "*/tests/*", "*/test_*.py", "*/conftest.py", "*/manage.py", "*/wsgi.py", "*/asgi.py"]
  ```
- No `branch = true` directive anywhere in `[tool.coverage.*]` sections.

**Recommendation:**

Add `branch = true` to `[tool.coverage.run]` in `pyproject.toml`. This will reveal untested conditional paths (e.g., error-handling branches in `consent_hard_delete`, `archive_sweep` retention-window logic, `handle_login_orm` IntegrityError fallback). Consider also adding `partial_branches` exclusions for `# pragma: no branch` on genuinely single-sided branches.

Effort: trivial. Priority: recommended.

---

### TSC-009: `.env.docker` tracked in git — deployment env file not in `.gitignore`

| Field | Value |
|-------|-------|
| **ID** | TSC-009 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | .env.docker (repo root), .gitignore:145-149 |
| **Classification** | mandatory |

**Description:**

`.env.docker` (repo root, 29 lines) is tracked by git (`git ls-files` confirms) but is NOT listed in `.gitignore`. The `.gitignore` at line 145-149 ignores `.env`, `.env.dev`, `.env.local`, `.envrc` — but not `.env.docker`. The comment at `.gitignore:149` says "`.env.example`, `.env.dev.example`, are committed as templates" — but `.env.docker` is NOT an example template; it is a real deployment configuration file with placeholder secrets (`POSTGRES_PASSWORD=your-password`, `BOT_TOKEN=`, `ADMIN_PASSWORD=`).

Once a developer fills in real `BOT_TOKEN` and `ADMIN_PASSWORD` values for production and commits them, those secrets will be permanently exposed in git history.

**Evidence:**

- `git ls-files -- '.env*'` returns: `.env.dev.example`, `.env.docker`, `.env.example`.
- `.gitignore:145-147`: ignores `.env`, `.env.dev`, `.env.local` — `.env.docker` not listed.
- `.env.docker` content: `POSTGRES_PASSWORD=your-password`, `BOT_TOKEN=`, `ADMIN_PASSWORD=` — placeholder deployment secrets.
- Comment at `.env.docker:3`: "DO NOT include DATABASE_URL - Docker Compose constructs it" — indicates this file is meant for direct use, not as a template.
- `Makefile:9`: `ENV_FILE := --env-file .env.docker` — Makefile references this file directly.

**Recommendation:**

Rename `.env.docker` → `.env.docker.example` (making it clearly a template), add `.env.docker` to `.gitignore`, and update `Makefile:9` to point to `.env.docker.example`. This follows the same pattern as `.env.example`.

Effort: small. Priority: recommended.

---

### TSC-010: Coverage gap on critical-path bot handlers — `ad_create.py` 20%, `login.py` 39%

| Field | Value |
|-------|-------|
| **ID** | TSC-010 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/telegram_bot/handlers/ad_create.py, src/telegram_bot/handlers/login.py, apps/core/services/contact.py |
| **Classification** | advisory |

**Description:**

Three modules that implement core user-facing flows have coverage far below the 80% threshold:

- `telegram_bot/handlers/login.py` — 39%. The `handle_login_orm` function (Phase 04) is the two-phase token-claim entry point. Three of its functions are untested because the `returning=True` bug crashes tests before assertions run.
- `telegram_bot/handlers/ad_create.py` — 20%. The bot-side ad creation flow (Phase 05: photo upload, dedup, thumbnail generation, moderation) has virtually no test coverage. A regression in ad submission would have no guard.
- `apps/core/services/contact.py` — 53%. The contact-gating service (Phase 07) determines whether a buyer can reveal a seller's phone number. Insufficient coverage on the gating logic.

**Evidence:**

- Full-suite coverage report: `login.py` 39%, `ad_create.py` 20%, `contact.py` 53% (excerpted from `--cov-report=term` output).
- Phase 04 audit (AUT-001) documented that `handle_login_orm` has no working tests due to `returning=True`.
- Phase 05 audit (AD-001) documented that sweep/purge paths bypass `transition_to()` — tests only cover the transition matrix, not the bypass paths.

**Recommendation:**

Prioritize test coverage for `handle_login_orm` (fix `returning=True` first), then add integration tests for the bot ad-creation flow (photo upload → dedup → moderation → publish). For `contact.py`, add tests for the visibility-gating logic (buyer-seller relationship, consent checks, time-window limits).

Effort: large. Priority: recommended.

---

### TSC-011: Duplicate test files — `test_claim_login_token.py` vs `test_login_claim.py`

| Field | Value |
|-------|-------|
| **ID** | TSC-011 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/telegram_bot/tests/test_claim_login_token.py (7 tests, unmodified), src/telegram_bot/tests/test_login_claim.py (5 tests, partially modified) |
| **Classification** | advisory |

**Description:**

Two test files in `src/telegram_bot/tests/` test the same production function (`handle_login_orm` from `login.py`) with overlapping scenarios:

- `test_claim_login_token.py` — 7 tests, uses `login_token_factory` fixture from conftest, ALL failing (4 `FieldDoesNotExist`, 3 `SynchronousOnlyOperation`). Unmodified — does not reflect the partial `sync_to_async` fix already applied to its sibling.
- `test_login_claim.py` — 5 tests, uses inline fixtures, partially modified (added `sync_to_async` wrappers and `pytest.mark.asyncio` to `pytestmark`), but still fails because the production `returning=True` bug is unaddressed.

Maintaining two parallel test files for the same function creates confusion: a developer fixing one might not fix the other, and CI reports failures from both. The working-tree modification to `test_login_claim.py` suggests an active effort to consolidate, but `test_claim_login_token.py` was left behind.

**Evidence:**

- `git diff --stat`: `test_login_claim.py` has 9 insertions(+), 7 deletions(-) (partial fix applied).
- `test_claim_login_token.py` is unmodified — still uses sync `login_token_factory` fixture.
- Both files test: valid token claim, replay blocking, expired token rejection, claimed-token rejection, user creation, existing-user return.
- Phase 04 AUT-002 referenced both files.

**Recommendation:**

Consolidate into a single test file. Remove `test_claim_login_token.py` and migrate any unique scenarios into `test_login_claim.py` (which already has the `sync_to_async` fix). Ensure the conftest `login_token_factory` and `user` fixtures are also fixed to use `sync_to_async` (TSC-006).

Effort: medium. Priority: recommended.

---

### TSC-012: `time.sleep(1)` in test_query_translator — slows suite and depends on wall-clock timing

| Field | Value |
|-------|-------|
| **ID** | TSC-012 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/search/tests/test_query_translator.py:49-56, src/telegram_bot/tests/test_ad_lifecycle.py:326-327 |
| **Classification** | advisory |

**Description:**

`test_timeout_returns_original_query` at `test_query_translator.py:49-56` mocks `GoogleTranslator.translate` with `side_effect=lambda *_: time.sleep(1)`. The test relies on the production code's `ThreadPoolExecutor` timeout (500ms) firing while the mock sleeps for 1 full second. This makes the test take ≥1 second, and its correctness depends on the real wall-clock timeout — if the timeout value or the executor implementation changes, the test may break or pass for the wrong reason. A similar `time.sleep(0.01)` in `test_ad_lifecycle.py:326-327` uses a real sleep for timestamp ordering, a minor flakiness risk.

**Evidence:**

- `test_query_translator.py:49-56`:
  ```python
  with patch(_TRANSLATE_PATH, side_effect=lambda *_: time.sleep(1)):
      result = translate_query_bs_to_ru("bok")
  assert result == "bok"
  ```
- `test_ad_lifecycle.py:326-327`: `import time; time.sleep(0.01)` — used to ensure `published_at` timestamps differ between publish operations.

**Recommendation:**

For `test_query_translator`: mock the `ThreadPoolExecutor` or the timeout mechanism directly instead of relying on a real 1-second sleep. Use `unittest.mock.patch` on the timeout constant (`TRANSLATION_TIMEOUT_SECONDS`) and verify the fallback path with a mock that raises `concurrent.futures.TimeoutError`. For `test_ad_lifecycle`: use `freezegun` or `unittest.mock.patch` on `timezone.now()` instead of `time.sleep(0.01)`.

Effort: small. Priority: recommended.

---

### TSC-013: Inline `import time` in test_ad_lifecycle.py

| Field | Value |
|-------|-------|
| **ID** | TSC-013 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/telegram_bot/tests/test_ad_lifecycle.py:326 |
| **Classification** | advisory |

**Description:**

At `test_ad_lifecycle.py:326`, `import time` is executed inline inside a test method body rather than at the module level. While functionally valid Python, it violates the project's convention of keeping imports at the top of the module. It also obscures the test's timing dependency — a reader scanning imports won't see `time` as a dependency.

**Evidence:**

- `test_ad_lifecycle.py:326`: `import time` inside `test_archive_preserves_original_published_at` method body.
- No `import time` at the top of `test_ad_lifecycle.py`.

**Recommendation:**

Move `import time` to the module-level imports at the top of the file, alongside other dependencies.

Effort: trivial. Priority: recommended.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 3 |
| HIGH | 5 |
| MEDIUM | 3 |
| LOW | 2 |
| **Total** | **13** |

| Classification | Count |
|----------------|-------|
| mandatory | 8 |
| advisory | 5 |
| **Total** | **13** |

## Mandatory Fixes

1. **TSC-001** — Resolve all 30 failures + 4 errors (TSC-002 through TSC-008 and prior-phase production bugs AUT-001, PII-001, SRH-003, SRH-004, SRH-007, SRH-011) to restore a green suite.
2. **TSC-002** — Fix `jpeg_with_exif` fixture in `test_media_security.py:92-106` (use proper GPSInfo dict or remove GPSInfo tag) and re-enable `TestExifStripping` tests.
3. **TSC-003** — Generate and commit pending migration 0005; resolve the untracked `0004_ad_draft_nullable_fields.py` state.
4. **TSC-004** — Remove `--reuse-db --create-db` from `entrypoint-test.sh` default flags, or add a schema-reset step after `--reuse-db`.
5. **TSC-005** — Add `.exists()` method to `_CrashOnDeleteQuerySet` in `test_sweep_commands.py:372`.
6. **TSC-006** — Wrap sync ORM calls in `login_token_factory` and `user` conftest fixtures with `sync_to_async`.
7. **TSC-007** — Add `--cov` to `addopts` in `pyproject.toml:157`.
8. **TSC-009** — Rename `.env.docker` → `.env.docker.example`, add to `.gitignore`, update `Makefile:9`.

## Advisory Recommendations

1. **TSC-008** — Enable branch coverage (`branch = true` in `[tool.coverage.run]`).
2. **TSC-010** — Increase coverage on critical-path modules: `ad_create.py` (20%), `login.py` (39%), `contact.py` (53%).
3. **TSC-011** — Consolidate duplicate test files `test_claim_login_token.py` and `test_login_claim.py` into one.
4. **TSC-012** — Replace `time.sleep(1)` in `test_query_translator.py:53` and `time.sleep(0.01)` in `test_ad_lifecycle.py:327` with mock-based approaches.
5. **TSC-013** — Move inline `import time` in `test_ad_lifecycle.py:326` to module-level imports.


