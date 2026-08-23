---
id: 27_test-optimization-and-verification
domain: testing
status: proposed
sources:
  - .ai/problems/slow-tests-analysis.md
  - .ai/audit/problems/20_plan-verification-test-optimization-audit-plans.md
generated: 2026-08-22
evidence_basis: >
  Five parallel Researcher passes (Branch A/B/C/D/E) each verified findings
  against the current source tree, plus direct manual verification of the
  highest-impact claims (ImageGenerator patch target at seed_service.py,
  test_views.py yield fixtures, ci.yml --reuse-db). Where research corrected
  the source spec, the correction and its evidence are noted inline.
---

# Plan 27 — CI Verification Fixes + Test Optimization (Marker Hygiene, CI Split, Seed Acceleration)

## 0. Overview

This plan transforms two validated specifications into an implementation-ready,
dependency-aware execution DAG, grounded in **five parallel source-verified
research passes** (one per branch) plus direct verification.

1. **`.ai/audit/problems/20_plan-verification-test-optimization-audit-plans.md`**
   — finding **O-03**: CI `lint`/`typecheck` at HEAD are red (4 `F401` + 8
   `basedpyright` errors). Research confirmed all defects real; also found the
   reported count of E402 (`6`) should be `7` (all in `scripts/`, and
   explicitly **out of CI scope** since CI runs from `src/backend`).

2. **`.ai/problems/slow-tests-analysis.md`** — Phase-E infrastructure is
   already committed. The **verified open work**:
   - **Marker hygiene** (P1/P5): 52 module-level `slow` files (~694 tests, only
     ~40 genuinely slow). Research key finding: **the project's own fast gate
     and CI never use `-m "not slow"`** — they filter only on `seed` — and the
     project's own `rules.md` documents `[django_db, integration]` as the
     module-level convention. So the `slow` marker is purely decorative and
     **re-classification is safe**. Gated on an adoption decision.
   - **CI parallel split** (P2): **blocked on marker hygiene**; research
     confirms a 4-job matrix (own Postgres per job) is the correct design, and
     that 16 files currently have no `pytestmark` (15 pure-unit) that would be
     silently dropped by a marker-based split unless `unit` is added.
   - **Coverage merge** (P2): per-job `.coverage.<suite>` + `coverage combine`
     (XML is not combinable).
   - **Seed acceleration** (P2): mock `ImageGenerator` is P0; research **corrected
     the patch target** and **excluded `test_media_cleanup`**; `test_full_seed_coverage`
     must NOT be reduced below 600 ads (coupon-collector analysis).
   - **Secondary optimizations** (P3): research **rejected** the sweep `slow`
     strip and the literal D2 backdate (flawed), and **rejected** all settings
     test changes (already correctly classified; subprocess is mandatory).

### Scope exclusions (explicit)
- All Phase-E committed infra (fast gate, `--reuse-db`, dead deps) — needs no work.
- Resolved findings (currency race, `AdStatus` NameError, `load_catalog` stale,
  shadowed `tests.py`) — no action.
- Parallel seed execution with DB-per-worker (11.9.2) — deferred (LOW confidence/high risk).
- Settings production refactor (11.3.2) — **rejected by research** (HIGH startup risk).
- Settings subprocess consolidation (11.3.1) — **rejected by research** (fragile; import-time
  validation is genuinely untestable in-process due to lazy singleton `django.conf.settings`).
- Snapshot-based seed verification (11.1.7) — **rejected** (idempotency needs 2 real runs).
- `scripts/*.py` E402 (7 errors) — **out of CI scope** (CI runs from `src/backend`); optional.
- `--limit` arg on sweep commands (11.2.2) — **rejected** (marginal; tests use 0–2 records).

---

## 1. Execution DAG

```
BRANCH A — Static Verification (Spec 2 / O-03)            [unblocks CI lint/typecheck]
  A-01 (F401 removal) ──► A-02 (basedpyright fixes) ──► A-03 (verify)

BRANCH B — Marker Hygiene (Spec 1 / P1, gated)            [research gate, then parallel leaves]
  B-01 (RESEARCH gate: adoption decision)
     ├─► B-02 (slow reclassification — 52 files)
     ├─► B-03 (unit population — 12 files + integration on 5 bare files)
     ├─► B-04 (concurrent/xdist_group — 6 files + CI)
     └─► B-05 (verify markers)        [gate for Branch C]

BRANCH C — CI Split (Spec 1 / P2)                         [BLOCKED on B-05]
  C-01 (parallel matrix split) ──► C-02 (coverage merge) ──► C-03 (verify)

BRANCH D — Seed Acceleration (Spec 1 / P2)                [independent, parallel]
  D-01 (mock ImageGenerator) ──► D-03 (class-scoped seed fixture, depends on D-01)
  D-02 (reduce ads in one safe test)
  D-04 (lazy image preprocessing — production fix, independent)
  D-05 (catalog cache — optional, independent)

BRANCH E — Secondary Optimizations (Spec 1 / P3)          [independent, parallel]
  E-01 (sweep: extract 2 source-inspection tests to new file)
  E-02 (priority bulk_create)
  E-03 (settings: NO ACTION — verify placement only)
  E-04 (sleep elimination: D1 timeout patch + D2 anchor fix)
```

**Parallel groups:**
- Group 1 (immediate): A-01, B-01, D-01, D-02, D-04, D-05, E-01, E-02, E-04
- Group 2 (independent of B, after D-01): D-03, E-03
- Group 3 (after B-01): B-02, B-03, B-04
- Group 4 (after B-02/03/04): B-05
- Group 5 (after B-05): C-01 → C-02 → C-03

---

## 2. Dependency & Risk Register

| Task | Risk | Key evidence-driven gate / mitigation |
|------|------|----------------------------------------|
| A-01 | LOW | grep-verified 4 unused imports; run `ruff check` + targeted suites (A-03) |
| A-02 | LOW | annotation-only; use repo's existing `# pyright: ignore[reportGeneralTypeIssues]` and `str(...)` coercion conventions |
| B-01 | n/a | **Research gate** — must output Go before B-02..B-04 |
| B-02 | MEDIUM | genuinely-slow tag list is evidence-derived; verify via `--collect-only` counts (B-05) |
| B-03 | LOW–MEDIUM | 15 no-marker pure-unit files MUST get `unit` or CI matrix would drop them (C blocked) |
| B-04 | LOW | `xdist_group` auto-registered by xdist; register defensively; switches CI `--dist loadgroup` |
| C-01 | HIGH | **BLOCKED on B-05**; each job own Postgres; `-m "unit and not settings"` avoids double-run |
| C-02 | MEDIUM | `coverage combine` is a union; `--cov-fail-under=0` per-job; gate on merged |
| D-01 | VERY LOW | patch class name binding, NOT `.generate`; exclude `test_media_cleanup` |
| D-02 | MEDIUM | reduce only `test_no_non_leaf...`→10; do NOT reduce `test_full_seed_coverage` (<90% coverage) |
| D-03 | MEDIUM | class-scoped `transaction=True`; tests verified read-only |
| D-04 | LOW–MEDIUM | production refactor; low runtime risk but non-trivial; apply in parallel |
| D-05 | LOW–MEDIUM | optional; session-scoped catalog; yield to D-01 in priority |
| E-01 | NONE | extract to NEW file (module `pytestmark` is additive — in-file exempt impossible) |
| E-02 | VERY LOW | FTS trigger row-level; auto_now auto-populated; shared helper |
| E-03 | NONE | no action; placement only |
| E-04 | VERY LOW | D2 fix differs from spec (anchor-backdate BEFORE capture) |

---

## 3. Task Specifications

---

# TASK A-01 — Remove 4 unused imports (F401) blocking CI lint

```yaml
id: task_027_a01
branch: A
title: Remove 4 unused imports (F401) in analytics and ads test files

priority: high
depends_on: []

source_reference: .ai/audit/problems/20_plan-verification-test-optimization-audit-plans.md
source_section: O-03 — finding 1 (F401)

description: >
  Restore green CI `ruff check .` from src/backend. Research confirmed all 4
  imports appear only on their import lines and are never referenced anywhere
  in the file (fixtures, params, comprehensions). Remove the unused names.

goals:
  - eliminate the 4 F401 errors in CI scope
  - preserve all genuinely-used imports
  - zero behavioral change

files:
  - path: src/backend/apps/ads/tests/test_dashboard_stats.py
    targets:
      - type: import
        name: patch
    changes:
      - action: remove_import
        description: Remove `from unittest.mock import patch` (unused — only the import line matches)
      - action: verify_no_usage
        description: Confirm no `patch(` / `Mock` reference remains

  - path: src/backend/apps/analytics/tests/test_trust_analytics.py
    targets:
      - type: import
        name: Ad
      - type: import
        name: Category
      - type: import
        name: City
    changes:
      - action: remove_import
        description: Remove `from apps.ads.models import Ad` (unused — helper `create_test_ad` used instead)
      - action: remove_import
        description: Remove `from apps.categories.models import Category` (unused — lowercase `category` fixtures)
      - action: remove_import
        description: Remove `from apps.locations.models import City` (unused — lowercase `city` fixtures)

acceptance_criteria:
  - `ruff check src/backend` reports 0 F401
  - modified test files still collect and pass
```

---

# TASK A-02 — Resolve 8 basedpyright errors blocking CI typecheck

```yaml
id: task_027_a02
branch: A
title: Resolve 8 basedpyright errors (2 generators, context-manager typing, list[SlugField])

priority: high
depends_on: [task_027_a01]

source_reference: .ai/audit/problems/20_plan-verification-test-optimization-audit-plans.md
source_section: O-03 — finding 2 (basedpyright)

description: >
  Research verified the root cause of all basedpyright errors: the project does
  NOT install django-stubs, so Django 5.2's untyped model/atomic() APIs resolve
  to broad/incorrect types. The codebase already has UNANIMOUS conventions to
  work around both: `# pyright: ignore[reportGeneralTypeIssues]` on every
  `transaction.atomic()` call (20+ usages) and `str(self.field)` coercion in
  the `LookupItem` model. Use those existing conventions. Two of the four
  "locations" in the audit are the `def`+`yield` of the SAME two fixtures —
  only two fixtures need annotation changes.

goals:
  - eliminate the 8 basedpyright errors in CI scope
  - follow the repo's existing workaround conventions
  - zero runtime behavior change

files:
  - path: src/backend/apps/analytics/tests/test_views.py
    targets:
      - type: method
        name: TestSellerTrustDashboardView._setup   # def at L111, yield at L126
      - type: method
        name: TestModerationAnalyticsView._setup     # def at L277, yield at L288
    changes:
      - action: fix_return_type
        description: >
          Change both `-> None` to `-> Generator[None]` and add
          `from collections.abc import Generator` if not already imported.
          Matches the existing `test_auth_nav.py` pattern (verified passing
          basedpyright with 0 errors).

  - path: src/backend/apps/categories/catalog/builder.py
    targets:
      - type: function
        name: load_catalog
    changes:
      - action: add_type_ignore
        description: >
          Add `# pyright: ignore[reportGeneralTypeIssues]` to the
          `with transaction.atomic():` line (L74). This is the ONLY
          `transaction.atomic()` in the codebase missing this comment; the
          other 20+ usages already carry it. Runtime unchanged.

  - path: src/backend/apps/categories/services/lookup_resolution.py
    targets:
      - type: method
        name: CategoryLookupResolver.get_resolved_purpose_codes
      - type: method
        name: CategoryLookupResolver.get_resolved_feature_codes
    changes:
      - action: coerce_to_str
        description: >
          In both methods, change `item.slug` to `str(item.slug)` in the list
          comprehension. Matches the `LookupItem` model's `__str__`/`get_name`
          coercion pattern. `str(str)` is identity at runtime.

acceptance_criteria:
  - `basedpyright .` (from src/backend) reports 0 errors, 0 warnings, 0 notes
  - category catalog + lookup-resolution tests pass
  - dashboard + analytics view tests pass
```

---

# TASK A-03 — Verify — CI lint and typecheck green

```yaml
id: task_027_a03
branch: A
type: verification
title: Verify — CI lint and typecheck green after O-03 fixes

priority: high
depends_on: [task_027_a02]
verifies: [task_027_a01, task_027_a02]

verification_steps:
  - lint: "uv run ruff check src/backend"
  - typecheck: "cd src/backend && uv run basedpyright ."   # as CI does
  - test_dashboard: "uv run pytest src/backend/apps/ads/tests/test_dashboard_stats.py -q"
  - test_trust: "uv run pytest src/backend/apps/analytics/tests/test_trust_analytics.py -q"
  - test_views: "uv run pytest src/backend/apps/analytics/tests/test_views.py -q"
  - test_categories: "uv run pytest src/backend/apps/categories -q"

pass_criteria:
  - ruff 0 errors in src/backend
  - basedpyright 0 errors/warnings/notes
  - all listed suites pass

failure_action: return task_027_a01 / task_027_a02 to rework
```

---

# TASK B-01 — RESEARCH GATE — adopt marker hygiene + CI subset targeting

```yaml
id: task_027_b01
branch: B
type: research
title: Research gate — confirm adoption of marker hygiene (slow reclassification + unit population)

priority: high
depends_on: []

source_reference: .ai/problems/slow-tests-analysis.md
source_section: §5 (broken slow), §8 P1 (gated), §10 (adoption gate)

description: >
  Marker hygiene is explicitly GATED. Research established the key safety facts
  and the definitive 52-file inventory, plus the 12 SimpleTestCase files for
  `unit` and the 5 bare `django_db` files missing `integration`. This gate must
  record the Go / Go-with-changes decision and lock the exact file lists so the
  downstream marker tasks are deterministic.

goals:
  - record explicit adoption decision (Go / Go-with-changes)
  - lock the 52-file `slow` inventory, the 12-file `unit` inventory, and the 5-file `integration` inventory
  - confirm the genuinely-slow (~40) test list from profiling evidence
  - unlock B-02..B-04 and the whole Branch C

research_evidence (locked):
  - inventory_52_slow: verified by grep (50 single-line + 2 multi-line module-level `pytestmark`)
  - unit_files_12: verified SimpleTestCase files with no django_db/pytestmark
  - bare_integration_5: test_create_admin_user, test_privacy, test_price_normalizer, test_recompute_command, test_consent_context
  - genuinely_slow: sweep ~37 DB-backed, dashboard_stats 16, priority 3 data-heavy, migrations 2, seed handled by `seed` marker
  - fast_gate: never uses `-m "not slow"` → reclassification safe
  - convention: rules.md documents `[django_db, integration]` (slow was ad-hoc)

outcome:
  - decision_recorded: true
  - blocked_tasks_unblocked: [task_027_b02, task_027_b03, task_027_b04, task_027_c01, task_027_c02]

pass_criteria:
  - Go / Go-with-changes recorded
  - locked inventories written into this plan (closure block)

failure_action: do not proceed to B-02 if scope/decision cannot be established
```

---

# TASK B-02 — Reclassify `slow` marker from module-level to genuinely-slow tests

```yaml
id: task_027_b02
branch: B
title: Reclassify `slow` on 52 files to per-genuinely-slow tests/classes

priority: high
depends_on: [task_027_b01]

source_reference: .ai/problems/slow-tests-analysis.md
source_section: §5, §8 P1 (gated); strategy 11.2.3 (partially rejected)

description: >
  Remove `pytest.mark.slow` from the module-level `pytestmark` on all 52 files
  and re-attach it per-class/per-test ONLY to genuinely slow tests (>5 s), using
  the evidence-based tag list. This restores `-m slow`/`-m "not slow"`,
  `-m unit`, and `-m integration` correctness and unblocks Branch C. SAFE: the
  fast gate and CI never filter on `slow`.

goals:
  - `-m slow` selects only the genuinely-slow tests
  - `-m "not slow"` frees the ~654 falsely-excluded tests
  - restore `-m unit` / `-m integration` correctness
  - align with project rule `[django_db, integration]` at module level

reclassify_rules (evidence-based):
  - keep slow per-test/class on: test_sweep_commands.py (the ~37 DB-backed tests; the 2 source-inspection ones move to unit in E-01), test_dashboard_stats.py (all 16), test_priority.py (the 3 data-heavy), test_migrations.py (both)
  - test_seed.py: remove `slow` from module-level entirely — the 21 `@pytest.mark.seed` tests are already excluded by the fast gate; the 34 non-seed are fast
  - 6 concurrent bot files: remove `slow` entirely (redundant with `concurrent`)
  - all other files: remove `slow` from module-level; add no per-test `slow` (fast tests)

changes:
  - action: remove_module_marker
    description: Remove `pytest.mark.slow` from module-level `pytestmark` on each of the 52 files (indexed in B-01 closure)
  - action: add_per_test_markers
    description: Add `@pytest.mark.slow` (and `@pytest.mark.integration` where applicable) only to the genuine >5s tests/classes from the locked list

acceptance_criteria:
  - `-m slow` selects ~40 tests (was ~694)
  - `-m "not slow"` selects ~1022 (was ~368)
  - full suite still passes when markers ignored

risk_mitigation:
  - verify counts via `pytest --collect-only` (B-05)
  - do NOT remove `django_db`/`integration` module markers
```

---

# TASK B-03 — Populate `unit` marker + add missing `integration` markers

```yaml
id: task_027_b03
branch: B
title: Populate `unit` on 12 SimpleTestCase files; add `integration` on 5 bare django_db files

priority: high
depends_on: [task_027_b01]

source_reference: .ai/problems/slow-tests-analysis.md
source_section: §2 (unit underused), §8 P1 (gated)

description: >
  Two related classification fixes that make marker-based CI splitting safe.
  Research found 12 verified DB-free SimpleTestCase files lacking `unit`. It
  also found that the CI matrix split (C-01) would SILENTLY DROP the 16 files
  with no `pytestmark` (15 are these pure-unit files) — so this task is a hard
  prerequisite for Branch C. Also add `integration` to 5 bare `django_db` files
  missing it.

goals:
  - make `-m unit` select ~235 tests instead of ~102
  - ensure every DB-backed module carries `integration`
  - guarantee no test is dropped by the future CI matrix (prerequisite for C-01)

files (12 for unit — locked in B-01 closure; from research):
  - test_ad_localization.py, test_adimage_thumbnail_urls.py, test_detail_context.py, test_listings_context.py
  - categories/test_trust_prefetch.py
  - core: test_context_processors.py, test_csp_report.py, test_language_locale.py, test_language_middleware.py, test_preferred_city_middleware.py, test_templates.py
  - search/test_autocomplete_template.py

files (5 for integration — locked in B-01 closure):
  - core/test_create_admin_user.py, core/test_privacy.py
  - currencies/test_price_normalizer.py, currencies/test_recompute_command.py
  - users/test_consent_context.py

changes:
  - action: add_unit_marker
    description: Add `pytestmark = [pytest.mark.unit]` (ensure `import pytest`) to each of the 12 DB-free files. Do not add `django_db`.
  - action: add_integration_marker
    description: Append `pytest.mark.integration` to the 5 bare `django_db` files so they are classified for the integration matrix job.

acceptance_criteria:
  - `-m unit` collects ~235 tests
  - every DB-backed module carries `integration`
  - no DB-free file carries `django_db`
  - `-m "not unit"` still collects all DB tests
```

---

# TASK B-04 — Group concurrent bot tests via xdist_group; switch CI to `--dist loadgroup`

```yaml
id: task_027_b04
branch: B
title: Add xdist_group to 6 concurrent files and switch CI `--dist loadscope` → `loadgroup`

priority: high
depends_on: [task_027_b01]

source_reference: .ai/problems/slow-tests-analysis.md
source_section: §3.5, §7; strategies 11.4.3 / 11.8.1

description: >
  The 6 `transaction=True`/`concurrent` bot files cause per-test TRUNCATE and,
  across forked xdist workers, cross-worker TRUNCATE lock contention. Pin all
  `concurrent`-marked tests to one worker via `@pytest.mark.xdist_group("bot_concurrent")`
  and switch CI to `--dist loadgroup`.

goals:
  - eliminate cross-worker TRUNCATE deadlocks (reliability)
  - enable safe xdist parallelism for the non-concurrent majority
  - preserve serial behavior

files (6 concurrent — locked in B-01 closure):
  - telegram_bot/tests/test_ad_create.py
  - telegram_bot/tests/test_create_draft_ad.py
  - telegram_bot/tests/test_login_claim.py
  - telegram_bot/tests/test_claim_login_token.py
  - telegram_bot/tests/test_unsubscribe.py
  - telegram_bot/tests/test_save_photo_integration.py

changes:
  - action: add_xdist_group_marker
    description: Add `@pytest.mark.xdist_group("bot_concurrent")` at module level to the 6 concurrent files.
  - action: register_xdist_group
    description: Add `"xdist_group: marks tests pinned to a single xdist worker"` to `markers` in pyproject.toml (defensive; xdist auto-registers it).
  - action: ci_loadgroup
    description: Change `--dist loadscope` → `--dist loadgroup` in ci.yml and ci-nightly.yml pytest invocations.

acceptance_criteria:
  - concurrent tests pinned to one worker under loadgroup
  - serial run behavior unchanged
  - no marker warnings
```

---

# TASK B-05 — Verify — marker hygiene correctness (gate for Branch C)

```yaml
id: task_027_b05
branch: B
type: verification
title: Verify marker selection correctness after hygiene

priority: high
depends_on: [task_027_b02, task_027_b03, task_027_b04]
verifies: [task_027_b02, task_027_b03, task_027_b04]

verification_steps:
  - unit: "uv run pytest -m unit --collect-only -q | tail -1"            # ~235
  - slow: "uv run pytest -m slow --collect-only -q | tail -1"            # ~40
  - not_slow: "uv run pytest -m 'not slow' --collect-only -q | tail -1"  # ~1022
  - integration: "uv run pytest -m integration --collect-only -q | tail -1"  # ~761
  - concurrent: "uv run pytest -m concurrent --collect-only -q | tail -1"    # 28
  - seed: "uv run pytest -m seed --collect-only -q | tail -1"                # 21
  - settings: "uv run pytest -m settings --collect-only -q | tail -1"        # 3
  - contradictions: "uv run pytest -m 'unit and slow' --collect-only -q"     # 0
  - contradictions2: "uv run pytest -m 'concurrent and slow' --collect-only -q"  # 0

pass_criteria:
  - counts match: unit ~235, slow ~40, not_slow ~1022, concurrent 28, seed 21, settings 3
  - unit-and-slow = 0, concurrent-and-slow = 0
  - no marker warnings

failure_action: return marker tasks to rework; do NOT unblock C-01 until pass
```

---

# TASK C-01 — Split CI test job into parallel matrix (own Postgres per job)

```yaml
id: task_027_c01
branch: C
title: Split ci.yml test job into 4-job matrix (unit / integration-non-concurrent / concurrent / settings)

priority: medium
depends_on: [task_027_b05]
blocked_by: [task_027_b02, task_027_b03, task_027_b04]

source_reference: .ai/problems/slow-tests-analysis.md
source_section: §8 P2 (gated), strategy 11.9.1

description: >
  Replace the single ci.yml test job (currently `pytest -m "not seed" -n auto
  --dist loadscope ... --reuse-db`, ~300 s) with a 4-job matrix. Research found
  xdist gives only ~3% speedup on the shared-DB single job (DB-bound), but a
  matrix gives each job its OWN Postgres service, eliminating the contention.
  Nightly seed job stays separate.

goals:
  - reduce CI wall time ~300 s → ~120–160 s
  - keep seed nightly-only
  - no test dropped (union == full non-seed suite)

matrix_subsets:
  - unit:        "-m 'unit and not settings' --dist loadgroup"   # avoid double-running settings tests
  - integration: "-m 'integration and not concurrent' --dist loadgroup"
  - concurrent:  "-m concurrent --dist loadgroup"
  - settings:    "-m settings --dist loadgroup"

changes:
  - action: matrix_ci
    description: >
      Restructure the ci.yml test job as a strategy.matrix over the 4 subsets,
      each running its own postgres:18-alpine service, with
      `uv run pytest <subset> -n auto --dist loadgroup --tb=short --cov --durations=10
      --cov-report=term --cov-report=xml --reuse-db --cov-fail-under=0`.
      Each job sets `COVERAGE_FILE: .coverage.<subset>` and emits a per-job
      coverage artifact.
  - action: keep_nightly
    description: Leave ci-nightly.yml seed job schema-equivalent (already `--reuse-db`).

acceptance_criteria:
  - 4 parallel jobs; each own Postgres
  - union of subsets == full suite minus seed
  - CI wall time reduced
  - each job emits a coverage artifact

risk_mitigation:
  - C-01 is blocked on B-05 proof of marker correctness
  - verify subset union completeness before enabling matrix in CI
```

---

# TASK C-02 — Merge coverage across CI stages; gate fail_under=80 on merged coverage

```yaml
id: task_027_c02
branch: C
title: coverage combine across matrix jobs; enforce fail_under=80 on merged result

priority: medium
depends_on: [task_027_c01]

source_reference: .ai/problems/slow-tests-analysis.md
source_section: §8 P2 (gated), strategy 11.8.2, §9 coverage strategy

description: >
  Research found coverage XML is NOT combinable — the merge must run on the
  raw per-job `.coverage.*` sqlite data files via `coverage combine` (a union,
  equal to a serial run; no undercounting). `fail_under=80` (in
  [tool.coverage.report]) is then enforced by a final `coverage report` step.
  Per-job `--cov-fail-under=0` defers gating to the merge.

goals:
  - single merged coverage gate over the whole non-seed suite
  - fail_under=80 on merged coverage
  - no per-job false-negative gating

changes:
  - action: coverage_merge
    description: >
      Add a final CI job (after test matrix) that downloads the per-job
      `.coverage.*` artifacts (with `include-hidden-files: true` — dotfile!),
      runs `coverage combine` then `coverage report` (reads fail_under=80 from
      pyproject [tool.coverage.report]).
  - action: per_job_opt_out
    description: Pass `--cov-fail-under=0` in each matrix job so only the merged gate enforces the threshold.

acceptance_criteria:
  - merged coverage equals a clean single non-seed `--cov` run
  - fail_under=80 passes on merged coverage
  - single coverage gate reported in CI

risk_mitigation:
  - C-03 compares merged coverage vs a clean run before accepting
```

---

# TASK C-03 — Verify — CI matrix completeness + merged coverage gate

```yaml
id: task_027_c03
branch: C
type: verification
title: Verify CI matrix completeness and merged coverage gate

priority: medium
depends_on: [task_027_c02]
verifies: [task_027_c01, task_027_c02]

verification_steps:
  - subset_union: "for each subset run --collect-only; confirm union == full suite minus seed; no file dropped"
  - merged_gate: "coverage combine over 4 artifacts; coverage report → fail_under=80 passes"
  - ci_wall: "confirm CI matrix jobs run in parallel and wall time reduced vs ~300 s baseline"

pass_criteria:
  - subset union == full non-seed suite
  - merged coverage ≥ 80
  - CI wall time < baseline

failure_action: return C-01/C-02 to rework; do not merge CI changes
```

---

# TASK D-01 — Mock `ImageGenerator` for non-image seed tests (P0 primary)

```yaml
id: task_027_d01
branch: D
title: Mock ImageGenerator in seed tests that do not assert on images

priority: high
depends_on: []

source_reference: .ai/problems/slow-tests-analysis.md
source_section: §11.1.2 (corrected)

description: >
  Research CORRECTED the patch target: patch the class-name binding
  `apps.seed.services.seed_service.ImageGenerator` (imported at
  seed_service.py:27, instantiated at :138), NOT `ImageGenerator.generate`
  (patching `.generate` would break the direct test imports in
  `TestImageGenerator`). Also EXCLUDES `test_media_cleanup` (asserts the seed
  dir exists, recreated by `_ensure_seed_dir()`). When the mocked class returns
  `[]`, the SHA-256 N+1 backfill is skipped via the `if ad_images:` guard
  (seed_service.py:146), saving a further 5–10 s/call. Est. ~760–1140 s
  cumulative.

goals:
  - eliminate ~40–60 s image + ~5–10 s sha256 backfill per affected seed call
  - keep real path covered by `test_generates_ad_images`
  - keep `test_media_cleanup` real

files:
  - path: src/backend/apps/seed/tests/conftest.py   # NEW file — no conftest exists in seed/tests/
    changes:
      - action: add_autouse_mock_fixture
        description: >
          Add an autouse fixture patching `"apps.seed.services.seed_service.ImageGenerator"`
          to a stub whose `generate()` returns `[]`. Scope the exclusion for
          `test_media_cleanup` (marker or fixture opt-out) so it keeps the real
          generator.

acceptance_criteria:
  - non-image seed tests skip the image pipeline
  - `test_generates_ad_images` and `test_media_cleanup` still pass (real path)
  - seed tests still assert correct Ad / AnalyticsEvent counts
  - expected seed suite ~120–150 s (from ~1054 s)
```

---

# TASK D-02 — Reduce ads in the one safe seed test

```yaml
id: task_027_d02
branch: D
title: Reduce --ads to 10 in test_no_non_leaf_category_assigned only

priority: medium
depends_on: []

source_reference: .ai/problems/slow-tests-analysis.md
source_section: §11.1.6 (partially rejected)

description: >
  Research analyzed `test_full_seed_coverage` with coupon-collector math: 200
  ads (~120 published) yields only ~51% leaf coverage — far below the ≥90%
  assertion (needs ~360+ published). So that test MUST keep 600 ads. Only
  `test_no_non_leaf_category_assigned` is safe to reduce (it only asserts no
  non-leaf assignment; >0 ads suffices).

goals:
  - safely cut `test_no_non_leaf_category_assigned` ~90 s → ~20 s
  - do NOT touch `test_full_seed_coverage`

files:
  - path: src/backend/apps/seed/tests/test_seed.py
    targets:
      - type: method
        name: TestAdGeneratorLeafOnly.test_no_non_leaf_category_assigned
    changes:
      - action: reduce_seed_ads
        description: Change `--ads=50` → `--ads=10` in this test only.

acceptance_criteria:
  - test still passes its no-non-leaf assertion
  - test_full_seed_coverage unchanged and still ≥90% (relies on D-01 for speed)

risk_mitigation:
  - do NOT apply to test_full_seed_coverage (would break coverage assertion)
```

---

# TASK D-03 — Class-scoped shared seed fixture for `TestSeedFilterCoverage`

```yaml
id: task_027_d03
branch: D
title: Replace 5 repeated seed runs in TestSeedFilterCoverage with one class-scoped fixture

priority: medium
depends_on: [task_027_d01]

source_reference: .ai/problems/slow-tests-analysis.md
source_section: §11.1.3

description: >
  Research verified all 5 tests in `TestSeedFilterCoverage` are read-only on
  seed data (they only `Ad.objects.filter(source=SEED, ...)`, make GET /search/
  requests, or check `features.count()`). Replace the 5 `_run_seed()` calls
  with a single `scope="class"` fixture running the seed once. Requires class-level
  `django_db(transaction=True)` (TransactionTestCase) so class-scoped data
  persists across the 5 tests, with TRUNCATE once at class teardown. Apply
  AFTER D-01 so the single seed run also benefits from the image mock.

goals:
  - run seed once for the class, not 5×
  - keep tests read-only and isolated

files:
  - path: src/backend/apps/seed/tests/test_seed.py
    targets:
      - type: class
        name: TestSeedFilterCoverage
      - type: method
        name: TestSeedFilterCoverage._run_seed
    changes:
      - action: add_class_fixture
        description: Add class-scoped autouse fixture calling `_run_seed()` once; add class-level `django_db(transaction=True)`; remove per-test `_run_seed()` calls.

acceptance_criteria:
  - seed runs once for the class
  - all 5 tests pass, remain read-only
  - no cross-test state corruption
```

---

# TASK D-04 — Lazy image preprocessing (production fix)

```yaml
id: task_027_d04
branch: D
title: Lazily preprocess only selected photos in ImageGenerator.generate (production)

priority: medium
depends_on: []

source_reference: .ai/problems/slow-tests-analysis.md
source_section: §11.1.1

description: >
  `ImageGenerator.generate()` (images.py:83-176) builds `all_entries` from the
  FULL 1,004-photo manifest and preprocesses them unconditionally before the
  ad-assignment loop, even when `--ads=0` or few ads. Refactor to build a
  category→photo map from manifest metadata first, then lazily preprocess only
  photos actually selected for ads. Identical thumbnails/output; only timing
  changes. Benefits `test_media_cleanup` (~60 s → ~2 s) and production `make seed`.

goals:
  - skip preprocessing of unused photos
  - identical AdImage/thumbnail output
  - benefit test_media_cleanup + production

files:
  - path: src/backend/apps/seed/generators/images.py
    targets:
      - type: method
        name: ImageGenerator.generate
      - type: method
        name: ImageGenerator._preprocess_images
    changes:
      - action: lazy_preprocess
        description: >
          Build category_key_map first (no disk I/O); in the ad-assignment loop,
          lazily call preprocessing per selected photo. Keep
          `_load_manifest`/`_ensure_seed_dir` behavior. Guard `test_generates_ad_images`
          still passes unchanged.

acceptance_criteria:
  - selected photos produce identical thumbnails (same filenames/PIL ops)
  - `--ads=0` skips preprocessing entirely
  - test_generates_ad_images + test_media_cleanup pass
  - production `make seed` unaffected (or faster)

risk_mitigation:
  - low runtime risk; guard with existing image tests
```

---

# TASK D-05 — Cache load_catalog via session-scoped fixture (optional, lower priority)

```yaml
id: task_027_d05
branch: D
title: Cache load_catalog load across seed tests via a session-scoped fixture

priority: low
depends_on: []

source_reference: .ai/problems/slow-tests-analysis.md
source_section: §11.1.5

description: >
  `load_catalog()` rebuilds 171 categories via ~342 update_or_create round-trips
  on every `call_command("seed")` (~3–5 s). Research confirmed categories are
  idempotent (`update_or_create`) and no test modifies them, so a session-scoped
  fixture that loads the catalog once (with transaction-rollback handling) is
  safe. Saves ~42–70 s total. **Lower priority than D-01** — do only after D-01
  lands, and only if session-scoped DB transaction management is verified to
  not cause test pollution.

goals:
  - eliminate redundant catalog rebuilds (~42–70 s)
  - keep categories correct across seed tests

changes:
  - action: session_catalog
    description: >
      Add a session-scoped catalog fixture (in src/backend/conftest.py or the
      seed conftest) that loads categories once; individual seed tests skip
      `_load_category_fixtures` by mocking `SeedService._load_category_fixtures`
      to return `[]` after the session load. Verify rollback isolation.

acceptance_criteria:
  - categories load once per session
  - no test pollution
  - seed tests still pass

risk_mitigation:
  - optional; skip if session transaction management proves fragile
```

---

# TASK E-01 — Extract sweep source-inspection tests to a new `unit`-marked file

```yaml
id: task_027_e01
branch: E
title: Move 2 inspect.getsource sweep tests to test_sweep_lock_structure.py (unit)

priority: low
depends_on: []

source_reference: .ai/problems/slow-tests-analysis.md
source_section: §3.2, §11.2.1 (corrected)

description: >
  Research verified: `TestConcurrentSweep` has exactly 2 pure `inspect.getsource()`
  tests (`test_archive_sweep_lock_inside_transaction`, `test_all_sweeps_lock_inside_transaction`)
  with no DB, plus 1 DB-backed (`test_file_deletion_after_commit_not_inside_transaction`).
  Because module-level `pytestmark` is ADDITIVE (pytest marks can't be removed
  per-test), the 2 must be extracted to a NEW file carrying
  `pytestmark = [pytest.mark.unit]` (no django_db/slow/integration). Do NOT strip
  `slow` from the original file — the ~37 DB-backed tests are genuinely slow
  (~265 s).

goals:
  - reclassify 2 pure-inspection tests to unit
  - leave the DB-backed sweep file correctly tagged slow+integration

files:
  - path: src/backend/apps/core/tests/test_sweep_lock_structure.py   # NEW
    changes:
      - action: create_unit_file
        description: Move the 2 inspect.getsource tests here with `pytestmark = [pytest.mark.unit]`.
  - path: src/backend/apps/core/tests/test_sweep_commands.py
    targets:
      - type: class
        name: TestConcurrentSweep
    changes:
      - action: remove_source_inspection_tests
        description: Remove the 2 moved tests; keep `test_file_deletion_after_commit_not_inside_transaction`.

acceptance_criteria:
  - 2 source-inspection tests run under `-m unit` without DB setup
  - DB-backed sweep file still runs its 37 tests as slow+integration
  - count correction: file has 37 tests, NOT 41 (spec was wrong)
```

---

# TASK E-02 — `bulk_create` for priority multi-ad setup via shared helper

```yaml
id: task_027_e02
branch: E
title: Add create_test_ads_bulk helper + use bulk_create in 3 data-heavy priority tests

priority: medium
depends_on: []

source_reference: .ai/problems/slow-tests-analysis.md
source_section: §3.8, §11.6.1 / 11.8.4

description: >
  Research verified: `create_test_ad` (conftest.py:78-117) does one INSERT per
  call via `_set_status_timestamp`. The FTS trigger is ROW-level (fires per-row
  on multi-row INSERT — identical to individual inserts), and Django's
  `bulk_create` INSERT compiler auto-populates `auto_now_add`/`auto_now`
  (`created_at`/`updated_at`). Method names verified current:
  `test_many_ads_user_score_bonus` (51), `test_combined_bonus` (4 REJECTED + 51
  PUBLISHED), `test_below_ad_threshold_no_bonus` (49). Use a shared
  `create_test_ads_bulk()` helper replicating `_set_status_timestamp`
  (set `published_at` for PUBLISHED, `rejected_at` for REJECTED).

goals:
  - cut ~6–12 s across the 3 tests
  - preserve check-constraint compliance and identical rows

files:
  - path: src/backend/conftest.py
    targets:
      - type: function
        name: create_test_ads_bulk      # NEW companion to create_test_ad
    changes:
      - action: add_bulk_helper
        description: Add `create_test_ads_bulk(user, category, city, count, *, status, **base)` building Ad instances and calling `Ad.objects.bulk_create()`, replicating `_set_status_timestamp` (published_at/rejected_at).
  - path: src/backend/apps/moderation/tests/test_priority.py
    targets:
      - type: method
        name: TestPriorityCalculator.test_many_ads_user_score_bonus
      - type: method
        name: TestPriorityCalculator.test_below_ad_threshold_no_bonus
      - type: method
        name: TestPriorityCalculator.test_combined_bonus
    changes:
      - action: use_bulk_create
        description: Replace the per-ad loops with `create_test_ads_bulk(...)` calls (status-specific).

acceptance_criteria:
  - 3 priority tests still pass with identical asserted outcomes
  - row content unchanged (insert strategy only)
  - runtime reduced

risk_mitigation:
  - do NOT touch test_escalation_when_flag_count_reaches_three (only 4 ads; no benefit)
```

---

# TASK E-03 — Settings subprocess tests: NO ACTION; verify classification/placement

```yaml
id: task_027_e03
branch: E
title: Confirm settings tests remain unit+settings; rely on CI matrix placement

priority: low
depends_on: [task_027_b01]

source_reference: .ai/problems/slow-tests-analysis.md
source_section: §3.3, §11.3 (11.3.1/11.3.2 rejected)

description: >
  Research verified these tests are ALREADY correctly `unit`+`settings` and the
  subprocess pattern is the ONLY correct way to test import-time validation
  (Django's `django.conf.settings` is a lazy singleton cached on first access;
  `override_settings` cannot test import-time `ImproperlyConfigured`). Both the
  production-refactor (11.3.2) and single-subprocess consolidation (11.3.1) were
  REJECTED as high-risk/fragile. ONLY valid action: ensure they land in the
  `settings` CI matrix job (Branch C). No code change.

goals:
  - keep subprocess tests intact and correctly classified
  - ensure `-m settings` selects them in Branch C
  - no test-code change

changes:
  - action: verify_classification
    description: Confirm `test_settings_secrets.py` carries `unit`+`settings`; ensure C-01's settings job selects it. No file change unless off.

acceptance_criteria:
  - `-m settings` collects the 3 tests
  - Branch C settings job includes them
```

---

# TASK E-04 — Eliminate wall-clock sleeps (translation timeout + re-publish anchor)

```yaml
id: task_027_e04
branch: E
title: Remove time.sleep from translation-timeout and ad re-publish tests

priority: low
depends_on: []

source_reference: .ai/problems/slow-tests-analysis.md
source_section: §3.6, §11.5.1 / 11.5.2 (D2 fix corrected)

description: >
  Two sleep eliminations, both verified:
  D1 — the translation timeout test: patch `apps.core.services.translation.TRANSLATION_TIMEOUT_SECONDS`
  to 0.05 (constant resolved via module globals at call time — patch takes
  effect) and reduce the mock `time.sleep(0.8)` → `0.1` (still exceeds 0.05 so
  the real `future.result(timeout=X)` fires first). D2 — the re-publish test:
  the spec's literal "backdate after capture" is FLAWED because
  `transition_to(PUBLISHED)` overwrites `published_at` with `timezone.now()`.
  Correct fix: backdate the FIRST publish's `published_at` AND
  `original_published_at` to `now - 10s` BEFORE capturing `first_published`,
  then re-publish; assertion `now() > (now-10s)` becomes deterministic. Remove
  the inline `import time`.

goals:
  - remove non-deterministic wall-clock dependencies
  - shrink D1 test ~0.5 s → ~0.05 s
  - correct D2 so the fix actually eliminates the clock dependency

files:
  - path: src/telegram_bot/tests/test_multi_lang_translation.py
    targets:
      - type: method
        name: test_timeout_fallback_returns_original
    changes:
      - action: patch_timeout
        description: Wrap with `patch("apps.core.services.translation.TRANSLATION_TIMEOUT_SECONDS", 0.05)`; reduce `time.sleep(0.8)` → `time.sleep(0.1)`.

  - path: src/telegram_bot/tests/test_ad_lifecycle.py
    targets:
      - type: method
        name: test_published_at_updates_on_re_publish
    changes:
      - action: anchor_backdate
        description: >
          After the first `auto_moderate`, set
          `Ad.objects.filter(pk=ad.pk).update(published_at=now-10s, original_published_at=now-10s)`,
          refresh, capture `first_published = ad.published_at`, THEN archive and
          re-publish. Remove inline `import time`.

acceptance_criteria:
  - no `time.sleep` remains in the two tests
  - assertions (timeout fallback; `published_at > first_published`) still hold deterministically
  - D1 runtime ~0.05 s
```

---

## 4. Ordering Summary (YAML form)

```yaml
tasks:
  - id: task_027_a01
    depends_on: []
  - id: task_027_a02
    depends_on: [task_027_a01]
  - id: task_027_a03
    depends_on: [task_027_a02]
  - id: task_027_b01
    depends_on: []
  - id: task_027_b02
    depends_on: [task_027_b01]
  - id: task_027_b03
    depends_on: [task_027_b01]
  - id: task_027_b04
    depends_on: [task_027_b01]
  - id: task_027_b05
    depends_on: [task_027_b02, task_027_b03, task_027_b04]
  - id: task_027_c01
    depends_on: [task_027_b05]
  - id: task_027_c02
    depends_on: [task_027_c01]
  - id: task_027_c03
    depends_on: [task_027_c02]
  - id: task_027_d01
    depends_on: []
  - id: task_027_d02
    depends_on: []
  - id: task_027_d03
    depends_on: [task_027_d01]
  - id: task_027_d04
    depends_on: []
  - id: task_027_d05
    depends_on: []
  - id: task_027_e01
    depends_on: []
  - id: task_027_e02
    depends_on: []
  - id: task_027_e03
    depends_on: [task_027_b01]
  - id: task_027_e04
    depends_on: []
```

---

## 5. Rollout Sequence

1. **Group 1 (immediate, parallel):** A-01, B-01 (research gate), D-01, D-02,
   D-04, D-05, E-01, E-02, E-04. A-01 unblocks CI lint; D/E are independent
   accelerations.
2. **A-02 → A-03:** complete O-03 verification (green CI lint/typecheck).
3. **After D-01:** D-03 (class-scoped seed fixture).
4. **After B-01:** B-02, B-03, B-04, E-03 (all in parallel).
5. **B-05:** verify marker correctness — the hard gate for Branch C.
6. **After B-05:** C-01 → C-02 → C-03.

---

## 6. Files Affected (consolidated)

| File | Tasks |
|------|-------|
| `src/backend/apps/ads/tests/test_dashboard_stats.py` | A-01 |
| `src/backend/apps/analytics/tests/test_trust_analytics.py` | A-01 |
| `src/backend/apps/analytics/tests/test_views.py` | A-02 |
| `src/backend/apps/categories/catalog/builder.py` | A-02 |
| `src/backend/apps/categories/services/lookup_resolution.py` | A-02 |
| `src/backend/apps/seed/tests/conftest.py` (NEW) | D-01 |
| `src/backend/apps/seed/tests/test_seed.py` | D-02, D-03 (B-02 metadata) |
| `src/backend/apps/seed/generators/images.py` | D-04 |
| `src/backend/conftest.py` | D-05, E-02 (helper) |
| `src/backend/apps/moderation/tests/test_priority.py` | E-02 (B-02) |
| `src/backend/apps/core/tests/test_sweep_lock_structure.py` (NEW) | E-01 |
| `src/backend/apps/core/tests/test_sweep_commands.py` | E-01 (B-02) |
| `src/backend/config/settings/tests/test_settings_secrets.py` | E-03 (no change) |
| `src/telegram_bot/tests/test_multi_lang_translation.py` | E-04 |
| `src/telegram_bot/tests/test_ad_lifecycle.py` | E-04 (B-02) |
| 6 concurrent telegram_bot files | B-04 |
| 12 SimpleTestCase files | B-03 |
| 5 bare django_db files | B-03 |
| 52 slow files (module-level) | B-02 |
| `pyproject.toml` | B-04 (xdist_group registration) |
| `.github/workflows/ci.yml` | B-04, C-01, C-02 |
| `.github/workflows/ci-nightly.yml` | B-04, C-01 |

---

## 7. Verification Strategy

- **Branch A:** dedicated A-03 (exact CI lint + typecheck + targeted suites).
- **Branch B:** dedicated B-05 (collection-count matrix + cross-marker
  contradiction checks) — the hard gate for Branch C.
- **Branch C:** dedicated C-03 (subset union + merged coverage gate).
- **Branches D/E:** inline `acceptance_criteria` + targeted test commands
  (proportional — localized, low/very-low risk).

---

## 8. Excluded / Deferred Work (explicit non-goals — research-validated)

- Parallel seed execution with DB-per-worker (11.9.2) — LOW confidence/high risk.
- Settings production refactor (11.3.2) — HIGH startup risk, REJECTED.
- Settings subprocess consolidation (11.3.1) — fragile; REJECTED.
- Snapshot-based seed verification (11.1.7) — idempotency needs 2 real runs; REJECTED.
- Sweep `--limit` arg (11.2.2) — marginal; REJECTED.
- `scripts/*.py` E402 (7 errors) — out of CI scope; OPTIONAL.
- Reduce `test_full_seed_coverage` ads (11.1.6 partial) — would break ≥90% coverage; REJECTED.
- Moving `slow` off `test_sweep_commands.py` wholesale (11.2.3) — 37 DB-backed tests
  are genuinely slow; REJECTED.

---

## 9. Research Evidence Log (corrections to source spec)

| Spec claim | Research finding | Source evidence |
|------------|------------------|-----------------|
| 8 basedpyright errors at test_views.py:111,126,277,288 | Only 2 fixtures; 111/126 and 277/288 are def+yield of same fixtures | test_views.py read |
| `ImageGenerator.generate` patch target | Patch class binding `seed_service.ImageGenerator`, not `.generate` | seed_service.py:27,138 |
| 11.1.2 mocks all but test_generates_ad_images | ALSO exclude `test_media_cleanup` (asserts seed_dir) | test_seed.py:881 |
| test_full_seed_coverage 600→200 ads | BREAKS ≥90% (coupon-collector ~51%) | assertion + distribution logic |
| Sweep file has 41 tests | Actually 37 | test_sweep_commands.py count |
| Sweep 2 tests reclassifiable in-file | Must extract to NEW file (additive pytestmark) | pytest additive semantics |
| D2 sleep fix: backdate after capture | FLAWED — transition_to overwrites published_at; anchor-before-capture | models.py transition_to |
| ci.yml uses --reuse-db | PRESENT at ci.yml:85 (verified) | ci.yml:85 |
| E402 count = 6 | Actual = 7 (scripts/, out of CI scope) | ruff scan |

---

## 10. Risk Summary

| Branch | Highest risk | Mitigation |
|--------|--------------|------------|
| A | LOW | annotation/import removal only; A-03 runs exact CI commands |
| B | MEDIUM (52 files) | B-01 gate + evidence lists + B-05 collection gates |
| C | HIGH (CI restructure) | blocked on B-05; C-01 per-job DB; C-03 union + merged-gate check |
| D | MEDIUM (D-02/D-03) | research verified safety; coupon-collector math; read-only fixture audit |
| E | LOW | extracted-file approach; corrected anchor fix; targeted test commands |
