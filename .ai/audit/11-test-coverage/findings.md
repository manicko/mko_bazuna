---
phase: "11"
phase_name: "Test Coverage"
date: "2026-09-13"
auditor: "Executor (subagent)"
validator: ""
mode: "problems-only"
id_prefix: "TST"
report_status: "draft"
severity_taxonomy: ".kilo/commands/audit/phases/11-audit-test-coverage.md#severity-taxonomy"
phase_11_invariant: "Finding IDs (TST-NNN) are stable. Do not renumber."
---

# Audit Findings — Test Coverage

## Executive Summary

Seven test-suite defects make the safety net untrustworthy for security- and correctness-critical behavior. Two CRITICAL gaps leave unmoderated ad-publishing and schema-drift detection completely untested; a pre-existing failure plus sub-threshold coverage keep CI perpetually red, which desensitizes the team to regressions. CI coverage reporting is under-configured, and test classification markers are miscategorized at module scope.

## Scope & Methodology

**Scope:** Test discovery, baseline execution, critical-path isolation, mock discipline, and CI-gating configuration for the Mko Bazuna Django 5.2 + aiogram 3.x test suite (1,062 tests across 82 files). Production code is read-only; no modifications were made. Focus areas: ad-lifecycle, login-token claim/expiry/replay, PII erasure, contact-gating, FTS visibility, media sweep, translation fallback, migration reproducibility, two-process bot FSM, and CI coverage gating.

### Runtime Verification

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | Critical-path coverage: lifecycle, login-token, PII erasure, contact-gating, FTS, media, translation | Read test files + coverage report | PASS |
| R-02 | Critical-path isolation: each test asserts real behavior | Read test assertions | PASS |
| R-03 | Mock discipline: no real external calls, no PII in test data | Grep tests for requests/Telegram/translator | PASS |
| R-04 | Test quality: no tautologies, no mocking-under-test | Read test assertions | PASS (except TST-002 gap) |
| R-05 | Two-process: bot FSM tested against REAL shared ORM | `test_ad_create.py` uses `django_db(transaction=True)` + `sync_to_async(Ad.objects.get)` | PASS |
| R-06 | Migration test: migrations apply cleanly + idempotent | `test_migrations.py:23` SKIPPED | FAIL |
| R-07 | Determinism: two identical runs | baseline shows consistent counts | PASS |
| R-08 | Prod-code-king: no tests distorting production logic | Read `test_edit.py` docstrings | PASS |
| R-09 | CI gating: lint+type+test+coverage enforced | `.github/workflows/ci.yml` jobs | PARTIAL |
| R-10 | Coverage reporting + threshold configured | `pyproject.toml` + `ci.yml:111` | FAIL |

> PASS results prove the audit was thorough; they are METHODOLOGY evidence, NOT findings.

**Tools used:** `grep`, `read` (source + logs), `read_text_file`, manual source inspection of `edit.py`, `test_edit.py`, `test_migrations.py`, `settings/test.py`, `ci.yml`, `pyproject.toml`. No production code was executed or modified.

**Assumptions:** Production uses PostgreSQL 18 (real DB for tests, no SQLite fallback); Django 5.2 LTS; test settings set `LANGUAGE_CODE = "en"` (msgid source = English); `DisableMigrations` is applied for ALL apps in `settings/test.py`.

## Findings Summary

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| TST-001 | No migration reproducibility/idempotency test | CRITICAL | Open | Migration-Test |
| TST-002 | Text-edit moderation path (PUBLISHED → ON_MODERATION) has zero coverage | CRITICAL | Open | Web-View-Test |
| TST-005 | Concurrent login-token double-claim race test deleted | HIGH | Open | Bot-FSM-Test |
| TST-003 | Coverage below fail_under threshold + pre-existing footer test failure keeps CI red | MEDIUM | Open | CI-Gating |
| TST-004 | `slow` marker applied at module level on 40 files misclassifies 679 fast tests | MEDIUM | Open | Fixture/Factory |
| TST-006 | CI coverage invocation lacks line-missing reporting | MEDIUM | Open | CI-Gating |
| TST-007 | `unit` marker missing on 12 `SimpleTestCase` files; redundant `slow` on bot tests | LOW | Open | Fixture/Factory |

## Empty State

No problems found in this phase.

## Distribution

**Severity counts**

| CRITICAL | 2 |
| HIGH | 1 |
| MEDIUM | 3 |
| LOW | 1 |

**Status counts**

| Status | Count |
|--------|-------|
| Open | 7 |

## Findings by Severity

### CRITICAL

#### TST-001: [CRITICAL] — No migration reproducibility/idempotency test

| Field | Value |
|---|---|
| **ID** | TST-001 |
| **Title** | No migration reproducibility/idempotency test |
| **Severity** | CRITICAL |
| **Category** | Migration-Test |
| **File(s)** | `src/backend/apps/core/tests/test_migrations.py:20,23,28,60`; `src/backend/config/settings/test.py:83-91` |
| **Status** | Open |
| **Problem** | `test_makemigrations_check` and `test_migration_idempotency` are both SKIPPED in every run. `DisableMigrations.__contains__` returns `True` for every app, so `_MIGRATIONS_DISABLED` at `test_migrations.py:20` is `True`, triggering the `skipif` at `test_migrations.py:23`. No test ever replays migration files or asserts drift idempotency. |
| **Impact** | Schema drift between models and committed migrations is undetectable in CI. A developer who edits a model and forgets a migration file, or writes a non-idempotent `RunSQL`, ships silently — only caught at deploy time as a production migration failure or data loss. |
| **Root Cause** | Test settings disable migrations globally for speed (`DisableMigrations` sets every app to `None`), which is the intended Django fast-test pattern, BUT `test_migrations.py`'s skip guard turns the migration tests into dead assertions that never execute. The guard should instead run migration checks against a migration-enabled settings module. |
| **Recommendation** | Add a migration-gating test that runs under `--create-db` with migrations ENABLED (e.g. a dedicated settings module or `DJANGO_SETTINGS_MODULE` override that restores `MIGRATION_MODULES = {}`). Assert `makemigrations --check --dry-run` exits 0 and that `migrate` replay is a no-op. At minimum, run `makemigrations --check` in CI as a separate step. |
| **Effort** | M |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **Reproduction Steps** | 1. `pytest src/backend/apps/core/tests/test_migrations.py -v` 2. Observe both tests SKIPPED with reason "MIGRATION_MODULES=None disables migration replay..." 3. Confirm `src/backend/config/settings/test.py:91` sets `MIGRATION_MODULES = DisableMigrations()` (class at `:83`) returning `None` for all apps |
| **Related Findings** | TST-006 (CI coverage gating) |

**Evidence — `src/backend/config/settings/test.py:83-91`** *(supports: "DisableMigrations returns True for every app, causing the skipif guard")*:
```python
class DisableMigrations:
    def __contains__(self, item):
        return True
    def __getitem__(self, item):
        return None


MIGRATION_MODULES = DisableMigrations()
```

**Evidence — `src/backend/apps/core/tests/test_migrations.py:20-28`** *(supports: "the skipif guard makes both migration tests dead assertions")*:
```python
_MIGRATIONS_DISABLED = bool(getattr(settings, "MIGRATION_MODULES", {}))

@pytest.mark.skipif(
    _MIGRATIONS_DISABLED,
    reason="MIGRATION_MODULES=None disables migration replay; "
    "makemigrations --check is not applicable when apps have no migrations",
)
def test_makemigrations_check() -> None:
```

**Evidence — `.cache/baseline_cov.log:44,390`** *(supports: "the 1 skipped test in the baseline IS the migration test")*:
```text
....s..F.......
SKIPPED [1] src/backend/apps/core/tests/test_migrations.py:23: MIGRATION_MODULES=None...
```

#### TST-002: [CRITICAL] — Text-edit moderation path (PUBLISHED → ON_MODERATION) has zero coverage

| Field | Value |
|---|---|
| **ID** | TST-002 |
| **Title** | Text-edit moderation path (PUBLISHED → ON_MODERATION) has zero coverage |
| **Severity** | CRITICAL |
| **Category** | Web-View-Test |
| **File(s)** | `src/backend/apps/ads/views/edit.py:162,208-244`; `src/backend/apps/ads/tests/test_edit.py:35` |
| **Status** | Open |
| **Problem** | The `ad_edit` view's PUBLISHED + `has_text_change` branch (`edit.py:208-244`) sets the new title/description, saves, calls `ad.transition_to(AdStatus.ON_MODERATION)`, logs, and redirects — but NEVER invokes `auto_moderate`. `test_edit.py` contains 6 methods across 5 `TestReactivation*` classes, ALL exercising the ARCHIVED/reactivation branch (`edit.py:164-206`); zero tests reach the PUBLISHED text-edit branch. |
| **Impact** | After a seller edits a live ad's title or description, the ad drops to ON_MODERATION but the new text is never re-scanned by auto-moderation. Untrusted, freshly-edited content can be approved by `auto_moderate()` being skipped — a trust/safety regression that the test suite cannot catch. This is Phase 05's AD-003 (HIGH) re-exposed at the test layer. |
| **Root Cause** | Test coverage was scoped only to the reactivation path (the `is_reactivation` branch). The non-reactivation PUBLISHED branch was never authored a test; the temporary repro `test_textedit_does_not_remoderate` was deleted in consolidation `c73f54d`. |
| **Recommendation** | Add tests POSTing a text change to a PUBLISHED ad and asserting: (1) status transitions to ON_MODERATION, (2) `auto_moderate` IS invoked, (3) `published_at` is cleared appropriately, (4) new title/description persist. Mirror the existing `permissive_criteria` fixture and `TestReactivationAutoModerate` pattern. |
| **Effort** | L |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **Reproduction Steps** | 1. `pytest src/backend/apps/ads/tests/test_edit.py -v` 2. Observe all tests named `test_edit_reactivation_*` — none exercise `edit.py:212 has_text_change` → `transition_to(ON_MODERATION)` 3. Read `src/backend/apps/ads/views/edit.py:208-244` — note `auto_moderate` is never called in this branch (unlike line 331) |
| **Related Findings** | Phase 05 AD-003; TST-001 |

**Evidence — `src/backend/apps/ads/views/edit.py:208-244`** *(supports: "the PUBLISHED text-edit branch never calls auto_moderate")*:
```python
elif ad.status == AdStatus.PUBLISHED:
    if has_text_change:
        ad.title = new_title
        ad.description = new_description
        ad = _apply_price_change(ad, price_amount_value, price_currency_value)
        ad.save(update_fields=[...])
        ad.transition_to(AdStatus.ON_MODERATION)
        logger.info(f"Ad {ad_id} text edited, moved to ON_MODERATION")
    else:
        ad = _apply_price_change(ad, price_amount_value, price_currency_value)
        ad.save(update_fields=[...])
    return redirect("ads:dashboard")
```

**Evidence — `src/backend/apps/ads/views/edit.py:25,331`** *(supports: "auto_moderate is imported and used only in the reactivation branch, not the text-edit path")*:
```text
edit.py:25: from apps.moderation.services.auto_moderation import auto_moderate
edit.py:176: # transitions ARCHIVED -> ON_MODERATION, then calls auto_moderate
edit.py:331:     auto_moderate(ad)
```

**Evidence — `src/backend/apps/ads/tests/test_edit.py:35` + test class names** *(supports: "all 6 methods target reactivation; none target PUBLISHED text edit")*:
```text
pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]
classes: TestReactivationStatusTransition, TestReactivationAutoModerate,
         TestReactivationCurrencyKeepCurrent, TestReactivationPriceNormalized,
         TestReactivationTextUpdated  — all reactivation
```

### HIGH

#### TST-005: [HIGH] — Concurrent login-token double-claim race test deleted

| Field | Value |
|---|---|
| **ID** | TST-005 |
| **Title** | Concurrent login-token double-claim race test deleted |
| **Severity** | HIGH |
| **Category** | Bot-FSM-Test |
| **File(s)** | `src/backend/apps/users/tests/test_login.py` (no concurrent tests); git history `c73f54d` |
| **Status** | Open |
| **Problem** | `test_concurrent_claim_tmp.py` — the only test exercising concurrent login-token claim contention — was deleted in consolidation `c73f54d`. `test_login.py` (20 methods across `TestLoginIssue`/`TestLoginStatus`/`TestLoginTokenSecurity`/`TestLoginPreferredCitySync`) asserts single-threaded atomic claim (`test_consumed_token_cannot_be_reused`) but never fires two concurrent claimers against the same token. Phase 04's AUT-002 specifically requires the race test. |
| **Impact** | A TOCTOU race in the login-token claim path is undetectable by the suite: two simultaneous buyers claiming the same unclaimed token could both observe `claimed_at IS NULL` before either persists, granting duplicate session establishment. The security guarantee "one token, one claim" is asserted only in serial isolation. |
| **Root Cause** | Temporary repro deleted during test consolidation `c73f54d` without replacement; the permanent test was never reconstituted. `test_ad_create.py` retains the `concurrent` marker for bot FSM TRUNCATE isolation, but login-token concurrency is bot-side and untested. |
| **Recommendation** | Re-add a concurrent double-claim test: spawn two async tasks both calling the claim endpoint with the same unclaimed token, assert one succeeds (200) and the other is rejected (410/already-consumed). Use a real DB row under `transaction=True` isolation mirroring the bot FSM tests. |
| **Effort** | M |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Reproduction Steps** | 1. `pytest src/backend/apps/users/tests/test_login.py -k concurrent -v` → 0 tests collected 2. `git show c73f54d --name-only \| grep concurrent_claim` → confirms deletion 3. Read Phase 04 AUT-002 requirement; confirm no surviving test asserts concurrent claim rejection |
| **Related Findings** | Phase 04 AUT-002; TST-002 |

**Evidence — `src/backend/apps/users/tests/test_login.py` class inventory** *(supports: "no concurrent/contention test exists; claim atomicity tested only serially")*:
```text
TestLoginIssue (5)       TestLoginStatus (7)
TestLoginTokenSecurity (5)  TestLoginPreferredCitySync (3)
= 20 methods, none targeting concurrent double-claim
```

**Evidence — `test_login.py::test_consumed_token_cannot_be_reused`** *(supports: "claim atomicity asserted only in single-threaded serial flow")*:
```python
# single-threaded: claim, refresh_from_db, claim again -> assert 410
token.claim(user)      # succeeds
token.refresh_from_db()
token.claim(other)     # asserts rejection — but never under contention
```

### MEDIUM

#### TST-003: [MEDIUM] — Coverage below fail_under threshold + pre-existing footer test failure keeps CI red

| Field | Value |
|---|---|
| **ID** | TST-003 |
| **Title** | Coverage below fail_under threshold + pre-existing footer test failure keeps CI red |
| **Severity** | MEDIUM |
| **Category** | CI-Gating |
| **File(s)** | `.cache/baseline_cov.log:45,388,391`; `src/backend/apps/core/tests/test_footer_contact_link.py:116-123`; `pyproject.toml:183` |
| **Status** | Open |
| **Problem** | Baseline run fails two gates simultaneously: (1) coverage = 77.55% against `fail_under = 80` (`pyproject.toml:183`), emitting "FAIL Required test coverage of 80.0% not reached"; (2) `test_rendered_footer_contains_contact_link_markup` FAILS at `test_footer_contact_link.py:123` (`assert "Contact us" in html`) — the rendered footer does not contain the English label, a translation/i18n regression in the `telegram_deep_link` tag output. |
| **Impact** | CI is red on every push for two independent reasons. A persistently-red gate desensitizes the team to failures (real regressions hide behind the always-failing footer assertion). The 2.45-point coverage shortfall is masked by the test failure, so neither issue is addressed. |
| **Root Cause** | Footer assertion asserts on a literal English `msgid` ("Contact us") that the `telegram_deep_link` tag no longer emits verbatim — the link label is now obfuscated/base64-assembled per spec Block A. Coverage shortfall stems from large untested modules (`edit.py` 44%, `ad_copy.py` 27%, bot handlers 28-61%) with no per-app thresholds to force remediation. |
| **Recommendation** | (A) Fix the footer test to assert on the obfuscated payload (`data-start="contact_us"`, `data-bot-encoded`) rather than the literal English label — matching the tag's spec Block A contract. (B) Raise coverage to 80% by adding tests for the flagged gaps (notably `edit.py:208-263` addressed by TST-002 and `auto_moderation.py` gaps). Both required for CI-green. |
| **Effort** | M |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Reproduction Steps** | 1. `pytest -m "not seed"` (full CI gate) 2. Observe `ERROR: Coverage failure: total of 78 is less than fail-under=80` and `FAIL ... Total coverage: 77.55%` (`.cache/baseline_cov.log:45,388`) 3. Observe `FAILED test_footer_contact_link.py::test_rendered_footer_contains_contact_link_markup` at line 123 — `assert "Contact us" in html` |
| **Related Findings** | TST-006; TST-002 (edit.py coverage gap) |

**Evidence — `.cache/baseline_cov.log:44-45,388`** *(supports: "coverage=77.55% < fail_under=80; gate fails")*:
```text
ERROR: Coverage failure: total of 78 is less than fail-under=80
FAIL Required test coverage of 80.0% not reached. Total coverage: 77.55%
```

**Evidence — `.cache/baseline_cov.log:48-52`** *(supports: "footer test fails on literal 'Contact us' assertion")*:
```text
src/backend/apps/core/tests/test_footer_contact_link.py:123: in test_rendered_footer_contains_contact_link_markup
    assert "Contact us" in html
E   assert 'Contact us' in '\n\n\n<footer class="bg-white border-t border-gray-200 mt-8">...'
```

**Evidence — `src/backend/apps/ads/views/edit.py` coverage line** *(supports: "edit.py untested branch drives the coverage shortfall")*:
```text
src/backend/apps/ads/views/edit.py  107  55  28  5  44%   50-63, 107-110, 143->152, 155->162, 208-263, 280-296, 314-335
```

#### TST-004: [MEDIUM] — `slow` marker applied at module level on 40 files misclassifies 679 fast tests

| Field | Value |
|---|---|
| **ID** | TST-004 |
| **Title** | `slow` marker applied at module level on 40 files misclassifies 679 fast tests |
| **Severity** | MEDIUM |
| **Category** | Fixture/Factory |
| **File(s)** | `src/backend/apps/ads/tests/test_edit.py:35`; `.cache/test-strategy-report.md:25,75-103` |
| **Status** | Open |
| **Problem** | 40 files apply `pytestmark = [..., pytest.mark.slow]` at module scope, tagging all 719 contained tests as `slow`. Only ~40 of those are genuinely >5s; ~679 are sub-second. `-m "not slow"` therefore excludes 679 fast tests alongside the ~40 genuinely slow ones. The PR gate cannot select "fast integration" — it gets 102 unit tests or 0 integration tests. |
| **Impact** | The `slow` marker is unusable for cost-based filtering. Any CI optimization depending on `-m "not slow"` silently drops 679 valid integration tests from fast feedback, defeating the tiered-suite intent (`test_auto_moderation.py:75` is the one correct per-class pattern; 39 other files diverge). |
| **Root Cause** | `slow` was applied via `pytestmark` (module-level convenience) rather than per-test/per-class. The test-strategy report (§3.3.1) documented this as the "root cause of taxonomy collapse" but no remediation was applied. |
| **Recommendation** | Move `slow` from module-level `pytestmark` to per-test/per-class decorators on the ~40 genuinely slow tests (use `test_auto_moderation.py` `TestCheckFunction` as the reference pattern). Keep `slow` on all 41 sweep-command tests (genuinely 6.5s avg). |
| **Effort** | L |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Reproduction Steps** | 1. `pytest --collect-only -q -m "not slow" \| grep -c "::"` → ~102 (only unit; 0 integration) 2. `pytest --collect-only -q -m "slow" \| grep -c "::"` → 719 3. Confirm `src/backend/apps/ads/tests/test_edit.py:35` sets module-level `slow` despite all 6 methods running <1s |
| **Related Findings** | TST-007 (marker hygiene) |

**Evidence — `.cache/test-strategy-report.md:25`** *(supports: "40 files, 719 tests, only ~40 genuinely slow")*:
```text
The `slow` marker is applied at module level on ~40 files containing 719 tests.
Of those 719, only ~40 tests actually take >5s. The remaining ~679 are sub-second
tests that are falsely excluded by `-m "not slow"`.
```

**Evidence — `src/backend/apps/ads/tests/test_edit.py:35`** *(supports: "module-level slow on a file whose tests are all sub-second")*:
```python
pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]
```

#### TST-006: [MEDIUM] — CI coverage invocation lacks line-missing reporting

| Field | Value |
|---|---|
| **ID** | TST-006 |
| **Title** | CI coverage invocation lacks line-missing reporting |
| **Severity** | MEDIUM |
| **Category** | CI-Gating |
| **File(s)** | `.github/workflows/ci.yml:111`; `pyproject.toml:162,183` |
| **Status** | Open |
| **Problem** | `ci.yml:111` invokes `--cov --cov-report=term --cov-report=xml` but omits `--cov-report=term-missing` (no line-level gaps in CI logs) and omits `--cov-fail-under` (the 80% threshold is enforced only implicitly via `pyproject.toml:183`, making the gate invisible in the invocation). When coverage fails (TST-003, 77.55%), the failure is buried among `--durations=10` and coverage output rather than surfaced as an explicit, scannable CI step. |
| **Impact** | Developers cannot see which lines are uncovered from CI logs; debugging the coverage shortfall requires re-running locally with `--cov-report=term-missing`. The implicit config-based threshold means a future edit to `pyproject.toml` could silently alter the gate without CI configuration noticing. |
| **Root Cause** | Coverage flags were assembled by piecemeal extension rather than a deliberate reporting strategy; `term-missing` was never added. |
| **Recommendation** | Add `--cov-report=term-missing` to `ci.yml:111` so uncovered lines print in CI logs. Optionally add an explicit `--cov-fail-under=80` to the invocation to make the gate self-documenting in the workflow file. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Reproduction Steps** | 1. Read `.github/workflows/ci.yml:111` → observe `--cov --cov-report=term --cov-report=xml` with no `--cov-fail-under` and no `--cov-report=term-missing` 2. Confirm `pyproject.toml:183` holds `fail_under = 80` (enforced via config, not CLI) |
| **Related Findings** | TST-003 |

**Evidence — `.github/workflows/ci.yml:111`** *(supports: "CI omits --cov-fail-under and --cov-report=term-missing")*:
```yaml
run: uv run pytest -m "not seed" -n auto --dist loadgroup --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db
```

**Evidence — `pyproject.toml:162,182-183`** *(supports: "threshold lives in config, not CI flags; addopts has no --cov-fail-under")*:
```toml
addopts = ["--import-mode=importlib", "-ra", "-q"]
[tool.coverage.report]
fail_under = 80
```

### LOW

#### TST-007: [LOW] — `unit` marker missing on 12 `SimpleTestCase` files; redundant `slow` on bot tests

| Field | Value |
|---|---|
| **ID** | TST-007 |
| **Title** | `unit` marker missing on 12 `SimpleTestCase` files; redundant `slow` on bot tests |
| **Severity** | LOW |
| **Category** | Fixture/Factory |
| **File(s)** | `.cache/test-strategy-report.md:27,109,111`; `src/backend/apps/ads/tests/test_edit.py:35` |
| **Status** | Open |
| **Problem** | 12 `SimpleTestCase` files (~133 pure-logic tests with zero DB access) lack the `unit` marker, so `-m unit` selects only 102 tests instead of ~235. Conversely, bot `test_ad_create.py` and `test_create_draft_ad.py` carry `slow + integration + concurrent` — `slow` is redundant because `concurrent` already implies DB-intensive TRUNCATE isolation. |
| **Impact** | The marker taxonomy is internally inconsistent, eroding the tiered-suite contract. Fast pure-logic tests are invisible to `-m unit`, and genuinely slow `concurrent` bot tests are double-labeled, confusing selection logic (`-m "not slow"` drops concurrent bot tests unnecessarily). |
| **Root Cause** | Marker hygiene drifted: `SimpleTestCase` files were left unmarked, and bot files inherited a copy-paste `slow` before `concurrent` was introduced. The test-strategy report (§3.3.2) enumerated all 12 files but remediation was not applied. |
| **Recommendation** | Add `pytestmark = pytest.mark.unit` to the 12 `SimpleTestCase` files (remove any stray `slow`/`integration`). Remove the redundant `slow` from `test_ad_create.py` and `test_create_draft_ad.py` (keep `concurrent + integration`). |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Reproduction Steps** | 1. `pytest --collect-only -q -m "unit" \| grep -c "::"` → 102 (expected ~235) 2. Confirm `test_ad_create.py` and `test_create_draft_ad.py` declare `pytestmark = [django_db, slow, integration, concurrent]` — `slow` redundant with `concurrent` |
| **Related Findings** | TST-004 |

**Evidence — `.cache/test-strategy-report.md:27,109`** *(supports: "12 SimpleTestCase files lack unit marker; bot files carry redundant slow")*:
```text
12 SimpleTestCase test files (~133 tests) — pure unit tests with zero DB access — lack the `unit` marker entirely, so `-m "unit"` selects only 102 tests instead of ~235.
`test_ad_create.py` ... Marked `slow + integration + concurrent` — `concurrent` already implies DB-intensive; `slow` is redundant
```

## Cross-Finding Analysis

- **Merge candidates:** None. TST-003 and TST-006 share the CI/red-gate domain but have distinct root causes (coverage shortfall + footer assertion vs. missing `term-missing` flag). Merging would conflate a behavioral defect with a reporting-config defect.
- **Conflicting evidence:** None. All severity assignments are consistent with the Phase 11 taxonomy and the provided runtime evidence.
- **Dependency chains:**
  - TST-002 (text-edit coverage) directly reduces the `edit.py` coverage gap that contributes to TST-003's 77.55% shortfall — fixing TST-002 recovers measurable coverage.
  - TST-003 must be resolved before TST-006's CI-gating improvements can be validated green (a green CI requires both the footer fix and 80% coverage).
  - TST-004 and TST-007 are independent cleanup of the same marker-hygiene class but address different axes (cost marks vs. classification marks).

## Remediation Roadmap

Ordered fixes by Severity × Priority.

| Order | ID | Severity | Effort | Priority | Recommendation (summary) |
|-------|----|----------|--------|----------|--------------------------|
| 1 | TST-001 | CRITICAL | M | P0 | Add migration-gating test under migration-enabled settings; run `makemigrations --check` in CI |
| 2 | TST-002 | CRITICAL | L | P0 | Add tests for PUBLISHED text-edit → ON_MODERATION + `auto_moderate` invocation (Phase 05 AD-003) |
| 3 | TST-005 | HIGH | M | P1 | Re-add concurrent login-token double-claim race test (Phase 04 AUT-002) |
| 4 | TST-003 | MEDIUM | M | P1 | Fix footer assertion to use obfuscated payload; close coverage gaps to reach 80% |
| 5 | TST-004 | MEDIUM | L | P1 | Move module-level `slow` to per-test/per-class on the ~40 genuinely slow tests |
| 6 | TST-006 | MEDIUM | S | P2 | Add `--cov-report=term-missing` (and optional `--cov-fail-under=80`) to CI |
| 7 | TST-007 | LOW | S | P2 | Add `unit` marker to 12 `SimpleTestCase` files; remove redundant `slow` from bot tests |

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| TST-001 | Low | Yes | Migration test must assert no drift on `--create-db` with migrations enabled |
| TST-002 | Med | Yes | New text-edit tests must assert `auto_moderate` is called and status transitions to ON_MODERATION |
| TST-005 | Med | Yes | Concurrent test must assert one winner, one rejection under real DB contention |
| TST-003 | Med | No (test-only change) | Footer assertion rewritten to match obfuscated payload; coverage must reach 80% |
| TST-004 | Low | Yes (test-only marker change) | Re-running `-m "not slow"` must include the 679 recovered fast tests |
| TST-006 | Low | Yes (CI config only) | CI logs must print `term-missing` output; gate still fails below 80% |
| TST-007 | Low | Yes (test-only marker change) | `-m unit` must select ~235 tests; `-m "not slow"` must not drop concurrent bot tests |

## Appendices

### Appendix A — Baseline test + coverage tail

*(supports: "baseline = 1451 passed, 1 skipped, 1 FAILED; coverage 77.55% < 80")*

```text
40: .....................................................................s.......................................F...
45: ERROR: Coverage failure: total of 78 is less than fail-under=80
388: FAIL Required test coverage of 80.0% not reached. Total coverage: 77.55%
390: SKIPPED [1] src/backend/apps/core/tests/test_migrations.py:23: MIGRATION_MODULES=None...
391: FAILED src/backend/apps/core/tests/test_footer_contact_link.py::test_rendered_footer_contains_contact_link_markup
```

### Appendix B — `edit.py` text-edit branch with no `auto_moderate`

*(supports: "TST-002 — the PUBLISHED text-edit branch omits auto-moderation")*

```python
elif ad.status == AdStatus.PUBLISHED:
    if has_text_change:
        ad.title = new_title
        ad.description = new_description
        ad = _apply_price_change(ad, price_amount_value, price_currency_value)
        ad.save(update_fields=[...])
        ad.transition_to(AdStatus.ON_MODERATION)
        logger.info(f"Ad {ad_id} text edited, moved to ON_MODERATION")
        # NOTE: auto_moderate() is NOT called here — only at edit.py:331 (reactivation)
    ...
    return redirect("ads:dashboard")
```
