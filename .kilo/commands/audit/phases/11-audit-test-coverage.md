# 11 — Test Coverage

> Audit phase. LLM-auditor instruction. Architecture-agnostic: described via
> ARCHITECTURAL LAYERS, ZONES OF RESPONSIBILITY, KEY RISKS, GOALS. NOT tied to
> specific files, modules, or functions. Must stay valid if the architecture changes.
>
> **Output mode:** `problems-only` — report only findings; do not narrate a clean bill of health.

## 1. Goal

Verify the test suite is a trustworthy safety net for every security- and
correctness-critical behavior owned by phases 01–09: the ad-lifecycle state
machine, the login-token two-phase claim/expiry/replay, the PII-erasure sweep,
contact-gating, FTS visibility, the media sweep, and translation fallback. Tests
must be meaningful (not tautological), deterministic, isolated, and compliant
with the production-code-king rule.

## 2. System Under Audit (layers & zones)

| Zone | Concern |
|------|---------|
| **Persistence / Model-Test** | ORM behavior, status transitions, data invariants. |
| **Service-Logic-Test** | Business-logic validation, moderation rules, sweeps. |
| **Web-View-Test** | Request/response, search visibility, contact gating. |
| **Bot-Handler / FSM-Test** | Bot flow, login-token claim, contact deep-link, FSM persisted as DRAFT rows in the shared ORM. |
| **Integration / E2E-Test** | Cross-process ORM sharing; full flows against the real DB. |
| **External-Mock** | Telegram gateway + translator mocked; no real calls, no PII egress. |
| **Migration-Test** | Schema reproducibility; migrations idempotent; no drift. |
| **Fixture / Factory** | Synthetic data only (no PII/secrets); isolated DB + media store. |
| **CI-Gating** | Lint + type-check + test (+ coverage) enforced on PR; deterministic. |

## 3. Prerequisites

- Test suite runnable via the documented command (pytest over the whole repo).
- Coverage tooling available (line + branch).
- Real DB available for tests per project spec (no SQLite fallback masking drift).
- External dependencies mockable (no network/cost in CI).
- No code modification — audit only.

## 4. Runtime Verification (mandatory)

Execute, then capture evidence (pass/fail/skip, duration, coverage numbers, grep hits):

1. **Suite baseline** — run full suite → capture counts + duration.
2. **Critical-path coverage** — measure branch coverage on each critical behavior: lifecycle transitions, login-token claim/expiry/replay, PII-erasure sweep, contact-gating (all conditions), FTS visibility (PUBLISHED-only), media sweep (file+row atomicity), translation fallback. Assert each is actually exercised (not mocked away).
3. **Critical-path isolation** — run each critical test alone → confirm it asserts real behavior (e.g. consumed token rejected, sweep removes only expired revocations, each gating condition blocks independently, non-PUBLISHED ads excluded from search).
4. **Mock discipline** — grep tests for real external calls (gateway/translator) → assert mocked; assert no PII/secrets in test data.
5. **Test quality** — flag tests that mock the function under test or assert nothing real (tautology); flag tests coupled to private internals that break on refactor without behavior change.
6. **Two-process testing** — confirm bot FSM is tested against the REAL shared ORM (DRAFT persistence), not a fake; confirm web+bot consistency where relevant.
7. **Migration test** — confirm a test verifies migrations apply cleanly + are idempotent.
8. **Determinism** — run suite twice → identical results; confirm timezone/randomness/order handled explicitly.
9. **Prod-code-king** — flag any test that asserts wrong business logic or forces a production distortion; recommend fix/removal.
10. **CI gating** — confirm lint→type-check→test enforced; coverage reporting + threshold configured (or flag absence).

## 5. Audit Dimensions (checks + evidence)

### (a) Coverage of critical paths — CRITICAL
Every critical behavior from phases 01–09 has meaningful tests.
- Evidence: coverage on each path; tests assert real ORM/behavioral state.

### (b) Mock discipline — CRITICAL
External deps mocked; no real calls; no PII in test data.
- Evidence: grep clean; synthetic fixtures; no network in CI.

### (c) Test quality — HIGH
Assertions validate behavior, not implementation; no tautological tests.
- Evidence: tests fail on behavior regression, not on refactor; meaningful asserts.

### (d) Two-process testing — HIGH
Bot FSM tested against the real shared ORM (DRAFT persistence); web+bot consistency covered.
- Evidence: real-DB FSM tests; no fake-ORM false confidence.

### (e) Migration tests — HIGH
Migrations verified reproducible + idempotent.
- Evidence: migration test exists; re-run yields no drift/data loss.

### (f) Determinism — HIGH
No flakiness from timezone/randomness/DB order.
- Evidence: two identical runs; explicit time/order handling.

### (g) Prod-code-king compliance — CRITICAL
Tests don't distort production; bad tests fixed/removed.
- Evidence: no test-only branches in prod; wrong-logic tests flagged.

### (h) Fixtures hygiene — HIGH
No real PII/secrets; isolated DB + media store.
- Evidence: fixture scan clean; temp media root used.

### (i) CI gating + coverage reporting + speed — MEDIUM
Lint+type-check+test+coverage enforced; suite fast enough for CI.
- Evidence: CI config gates all; coverage threshold set; duration acceptable.

## 6. Cross-Cutting (owned here, not duplicated)
This phase verifies the TEST SAFETY NET for behaviors owned by other phases:
- Phase 05 lifecycle, Phase 04 login-token, Phase 06 PII/consent, Phase 07 media,
  Phase 08 search/FTS, Phase 09 integrations. The behaviors belong to those
  phases; this phase confirms they are actually tested and the tests are trustworthy.

## 7. Edge Cases
- A "test" mocks the very function it claims to test (zero-assertion tautology).
- Test passes but would not catch a regression (no assertion on changed behavior).
- Bot FSM test uses a fake ORM instead of the real shared one (false confidence).
- Timezone-dependent test passes locally, fails in UTC CI.
- Randomness/DB-order non-determinism.
- Migration test missing → schema drift undetected.
- Fixture with a real identity / secret.
- Test that, to pass, required a production distortion (prod-code-king violation).
- E2E test hitting the real translator (cost/flaky).

## 8. Severity Taxonomy

- **CRITICAL**
  - A security-critical path has ZERO tests (login-token replay, PII erasure, contact-gating, FTS visibility, lifecycle transitions, media sweep).
  - Tests assert WRONG business logic and pressure production distortion.
  - Tests make REAL external calls with PII.
  - Fixture contains real PII/secrets.
  - Forbidden lifecycle transition not blocked by tests.
- **HIGH**
  - Critical path tested only with mocks asserting nothing real / tautological.
  - Bot FSM not tested against the shared ORM.
  - No migration test.
  - Flaky / non-deterministic tests in CI.
  - Coverage <50% on security-critical modules.
  - Two-process consistency untested.
- **MEDIUM**
  - Branch coverage <80% on critical code.
  - Tests coupled to implementation details.
  - No coverage reporting / threshold.
  - Slow suite hurting CI.
- **LOW**
  - Missing type hints in tests.
  - Minor fixture duplication.
  - No test markers for slow/integration.

## 9. Recommended Sequence
1. Run suite → baseline.
2. Coverage on critical paths.
3. Mock discipline + fixtures hygiene.
4. Test quality (tautology / impl-coupling).
5. Two-process + migration + determinism.
6. Prod-code-king + CI gating.

## 10. Finding Prefix
Use `TST-` for all findings in this phase.

## 11. Reporting
- `problems-only: true`.
- Each finding: severity, zone, evidence (test name/line/coverage number/grep hit), and recommendation with effort/priority.
- Append incrementally (≤100 lines per write) to the phase findings file per `docs/99-agent/rules.md`.

## 12. Findings (verified)

Verified findings live in this section; the full auditor-verification memo (with
line-level evidence) is in `.kilo/research/11-testing.md`. Findings are prefixed
`TST-` per §10.

### TST-001 — Mischaracterized settings topology (HIGH / refinement)

Finding TST-001 — Mischaracterized settings topology (HIGH). The auditor's "two
test settings (backend vs bot)" is not supported by source:

- **One** settings module is shared by *both* suites: `config.settings.test`.
  Verified across all compose services — `DJANGO_SETTINGS_MODULE=config.settings.test`
  on `test`, `bot`, `web`, `migrate`, `load_cities`, `load_catalog`, `seed`,
  `create_admin` (`docker-compose.test.yml:62,81,106,121,131,142,151,162`).
- The **second** settings module is `config.settings.test_migrations`
  (`test_migrations.py`), used *only* by `apps/core/tests/test_migrations.py`
  (`test_migrations.py:30` → `config.settings.test_migrations`). It re-enables
  `MIGRATION_MODULES = {}` and uses a unique `test_migration_repro` DB so the
  subprocess does not collide with xdist workers — purely a migration-
  reproducibility concern, **not** a bot-backend split.
- The root `conftest.py` (repo root, shared) centralizes `pytest_plugins` and
  re-exports `create_test_ad` so both trees resolve fixtures; the bot conftest
  (`telegram_bot/tests/conftest.py`) itself says bot tests "cannot import the
  backend conftest" by tree (lines 93-110) but they *do* share the **same
  settings module**.
- Bot FSM is tested against the real shared ORM (`create_test_ad` imported via
  `from conftest import create_test_ad`, `telegram_bot/tests/conftest.py:109-110`)
  — satisfying dimension (d), just not via a separate settings file.

✅ **Recommendation (Priority 1):** Treat the two settings as `test.py`
(fast-suite, `DisableMigrations`) vs `test_migrations.py` (migration-repro
subprocess). No bot-specific settings module exists; document this to prevent
future contributors from inventing one.

### TST-002 — CI runs pytest natively, not via Docker Compose (CONFIRMED / MEDIUM / phrasing refinement)

TST-002 — (CONFIRMED/MEDIUM): "pytest + Docker real PostgreSQL" is imprecise:
CI runs `uv run pytest` natively with a `postgres:18-alpine` service container,
not inside Docker; the Docker path is the local `make test`. Intent (no SQLite)
is met.

- CI runs `uv run pytest` natively on `ubuntu-latest` with a `postgres:18-alpine`
  service container (`ci.yml:58-75,138`), **not** inside Docker.
- The Docker-Compose path is **local** only: `make test` spawns the `test` compose
  service in Docker against a PG 18 container on host port 5433
  (`docker-compose.test.yml:43-54,68-95`; `Makefile:113-115`).
- No SQLite anywhere: `grep sqlite src/backend` → 0 matches.
- `entrypoint-test.sh:43-45` defaults to `--reuse-db`; `make test-recreate`
  forces `--create-db` (`Makefile:178`).

✅ **Recommendation:** No change. Intent met; only the phrasing in any summary
should be corrected from "Docker" to "service container (CI) / Docker Compose
(local make test)".

### TST-003 — `real_images` marker in active use (CONFIRMED USED, no action)

TST-003 — (CONFIRMED USED, no action): `real_images` marker is in active,
meaningful use. `apps/seed/tests/conftest.py:36-46` autouse fixture patches
`seed_service.ImageGenerator` to a no-op stub and *opts out* for tests marked
`real_images` (e.g. `test_media_cleanup`, `test_seed.py:912`), which assert on
the real image pipeline. Registry entry is justified; do **not** prune.

### TST-004 — Migration reproducibility + idempotency tested (CONFIRMED, no action)

TST-004 — (CONFIRMED, no action): Migration reproducibility + idempotency IS
tested via `apps/core/tests/test_migrations.py` (`test_makemigrations_check`,
`test_migration_idempotency`, `@pytest.mark.slow`, `xdist_group("migrations")`)
using `config.settings.test_migrations` in an isolated subprocess + fresh
`test_migration_repro` DB. Addresses phase-spec edge case "Migration test
missing → schema drift undetected". *(Evidence: `test_migrations.py:2-145`.)*

### TST-005 — Mock discipline sound (CONFIRMED, no action)

TST-005 — (CONFIRMED, no action): Mock discipline appears sound: bot tests build
`Bot(token=settings.BOT_TOKEN)` with a placeholder token and never call the real
Telegram API; `compilemessages` + `makemessages` run without DB per
`commands.md`. (Static grep for real external calls not run in this pass —
low-risk given the i18n job runs the no-DB extraction path.)

### Verified CONFIRMED findings (kept as-is)

These phase-spec dimensions (§5 a–i) are satisfied by the current source:

- **DisableMigrations for speed** — `config/settings/test.py:88-96` defines
  `DisableMigrations` (returns `True` for `__contains__`, `None` for
  `__getitem__`) and sets `MIGRATION_MODULES = DisableMigrations()` for **all**
  apps (including Django built-ins, per lines 71-87). Compensated by the
  session-scoped autouse fixture at `src/backend/conftest.py:111-165`
  (`_restore_test_schema_post_db_setup`), which under
  `AdvisoryLockId.TEST_SCHEMA_SETUP` (111) runs `call_command("migrate",
  "--run-syncdb")` + `load_exchange_rates` + `setup_search_triggers` in-process.
- **Bot isolation via xdist group** — 9 bot files pin to
  `xdist_group("bot_concurrent")` via `pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))`:
  `test_unsubscribe.py:24`, `test_save_photo_integration.py:40`,
  `test_price_payload.py:34`, `test_ad_data_locale.py:28`,
  `test_ad_create_condition.py:35`, `test_ad_create.py:25`,
  `test_account_state_middleware.py:35`, `test_login.py:43`,
  `test_create_draft_ad.py:19`. `--dist loadgroup` is the CI/entrypoint
  distribution mode (`ci.yml:138`; `entrypoint-test.sh:43-45`), so `bot_concurrent`
  tests are pinned to a worker set separate from `xdist_group("migrations")`
  (used by `apps/core/tests/test_migrations.py:26`). Bot tests use
  `pytest.mark.django_db(transaction=True)` (9 files, e.g.
  `test_ad_create.py:21`); the `_reap_worker_connections` autouse fixture
  (`telegram_bot/tests/conftest.py:245-254`) + `connection_created` signal
  tracker (`conftest.py:218-242`) closes worker backends after each test.
- **pytest markers** — 8 registered markers in `pyproject.toml:170-179`
  (`strict_config = true; minversion = "8.4"`), all in active use:
  `unit`, `integration`, `seed`, `concurrent`, `settings`, `slow`,
  `real_images`, `xdist_group`.
- **Migration test** — see TST-004.
- **Coverage gate** — `[tool.coverage.run] branch = true` +
  `[tool.coverage.report] fail_under = 80` + `show_missing = true`
  (`pyproject.toml:182-190`); CI runs `--cov` and uploads `coverage.xml`
  (`ci.yml:138,153-158`).

### Cross-phase resolution notes (relevant to this phase's safety net)

- **HSTS preload (`#09-EXT-03`) — RESOLVED.** `nginx.conf:42` now includes
  `preload`; `prod.py:135` sets `SECURE_HSTS_PRELOAD = True`. (One residual
  LOW: nginx emits a duplicated HSTS header alongside Django's
  `SecurityMiddleware`; both include `preload`, so they don't conflict — just
  redundant.) — Per Phase 09, `.kilo/research/09-integration.md`.
- **SAST absent (`#OPS-003`) — OPEN GAP (Phase 12, not Phase 11).** CI runs
  `pip-audit` + Trivy + `gitleaks` but no SAST tool (repo-wide
  `grep -i "bandit|semgrp"` over `.github/` → 0 matches; `pyproject.toml` dev
  group has no SAST tool; ruff `lint.select` is `E,F,I,B,UP,G` — `S` (bandit)
  **not** enabled). `test_ci_security.py` asserts only the 3 present scanners
  and never SAST, so the gap is **untested**. This is a Phase 12
  (production-ops) concern; it does **not** affect Phase 11's testing safety
  net, which is sound. — Per Phase 12, `.kilo/research/12-deployment.md`.

### Overall Recommendation

**Status: Phase 11 testing scaffold is well-engineered and trustworthy.** The
auditor's core findings stand; only TST-001 (settings topology mischaracterization)
requires a correction to the mental model, and TST-002 is a phrasing refinement.
The suite satisfies phase-spec dimensions (a)–(i): real PostgreSQL,
`DisableMigrations` + schema-restore, `unit`/`integration`/`seed` markers,
xdist-group bot isolation with `transaction=True` + worker-connection reaping,
subprocess migration repro/idempotency, 80% branch coverage gate, and full CI
gating (lint/typecheck/test+coverage+SLI/i18n/security/deploy-check) plus
nightly seed + monthly restore-test. No production-code distortion detected in
the testing layer.

**Priority 1:** Correct documentation/mental model re: TST-001.
**Priority 2:** None pending.
**Priority 3:** No further action required — the testing safety net is a net
positive for Phases 01–09 invariants (lifecycle, login-token, PII sweep,
contact-gating, FTS visibility, media sweep, translation fallback).
