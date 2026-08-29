---
id: stale-test-db-cleanup-and-doc-hygiene
domain: test-infrastructure
status: planning
priority: p1
tags: [doc-update, makefile, powershell, ci-cd, test-database, postgresql, documentation, prevention-test]
related:
  - file: .ai/plans/done/25_test-optimization-plan_done.md
    relation: target-of-doc-edits
  - file: Makefile
    relation: primary-edit
  - file: Makefile.ps1
    relation: primary-edit
  - file: src/backend/tests/test_docs_ci_parity.py
    relation: new-file
  - file: pyproject.toml
    relation: reference-read-only
  - file: .github/workflows/ci.yml
    relation: reference-read-only
  - file: .github/workflows/ci-nightly.yml
    relation: reference-read-only
  - file: docker/entrypoint-test.sh
    relation: reference-read-only
  - file: docs/99-agent/rules.md
    relation: reference-read-only
  - file: docker-compose.prod.yml
    relation: no-go-read-only
  - file: src/backend/config/settings/base.py
    relation: no-go-read-only
source_spec: .ai/problems/active_findings_compiled.md
verdict_source: §8 (Validator) + §9.2 (Final Go/No-Go)
---

# Stale Test DB Cleanup and Doc Hygiene

**Status:** Planning
**Source of truth:** `.ai/problems/active_findings_compiled.md` (§9.2 Final Actionable Findings — 4 GO findings + 1 prevention task)
**Scope:** Exactly what the Auditor/Validator flagged as GO — nothing resolved, nothing rejected.

---

## 1. Overview

### Current State (stale / broken / missing)

| Area | Current State | Risk |
|---|---|---|
| Plan §1.4 (`25_test-optimization-plan_done.md:70,75-77`) | Claims CI runs "all 934 tests"; table row shows bare `pytest --tb=short --cov` (no `-m`, no `loadgroup`, no `--reuse-db`) | Misleads maintainers; hides real CI behavior |
| Plan §1.3 (`25_test-optimization-plan_done.md:52`) | Shows `addopts` with `--cov --cov-report=term-missing` | Stale — live `pyproject.toml:160` has no `--cov` |
| Plan §1.2 (`25_test-optimization-plan_done.md:33-44`) | Lists `unit`, `e2e`, `seed`, `settings`, `concurrent` as "Not registered" | 9 stale `e2e` references across the doc; live `pyproject.toml:163-172` has 8 registered markers, no `e2e` |
| Plan §13 (`25_test-optimization-plan_done.md:679`) | Claims "5-tier (unit / integration / e2e / ...)" | Stale `e2e` reference |
| Plan §14 (`25_test-optimization-plan_done.md:693,697,702`) | T-01 says `e2e` registered; T-05/T-10 say `--dist loadscope`; T-05 omits `--reuse-db`; T-10 says nightly uses xdist | Contradicts live `ci.yml:91` (`--dist loadgroup --reuse-db`) and `ci-nightly.yml:73` (serial, no xdist) |
| `make test-recreate` (`Makefile:137-139`) | No pre-flight DROP of stale `test_mko_bazuna_gw*` DBs | 16 stale `gw*` DBs found empirically; `--create-db` fails with "database is being accessed" when crashed-worker connections persist |
| `.PHONY` (`Makefile:3-5`) | Does not include `test-clean-db` | Make warns about non-phony target |
| `Makefile.ps1` (`Makefile.ps1:115-121, 333-367`) | No `Invoke-TestCleanDb`; no `test-clean-db` switch entry; `Invoke-TestRecreate` has no cleanup | Windows dev path broken; same stale-DB risk |
| Prevention test | Does not exist | D-01/D-02/D-04 class drift can silently recur |

### Target State

| Area | Target State | Verification |
|---|---|---|
| Plan §1.4 | References live `ci.yml:91` command (`pytest -m "not seed" -n auto --dist loadgroup --reuse-db`); ~1111 non-seed tests | §1.4 no longer contains "all 934 tests"; §1.4 references `loadgroup` |
| Plan §1.3 | `addopts = ["--import-mode=importlib", "-ra", "-q"]` (no `--cov`) | §1.3 matches `pyproject.toml:160` |
| Plan §1.2 | 8 registered markers per `pyproject.toml:163-172`; `e2e` marked removed | `grep -c "e2e" 25_test-optimization-plan_done.md` returns 0 |
| Plan §14 | T-01: `e2e` removed; T-05: `loadgroup` + `--reuse-db`; T-10: `loadgroup` in ci.yml, serial in nightly | §14 matches `ci.yml:91` + `ci-nightly.yml:73`; `grep -c "loadscope"` returns 0 |
| `make test-clean-db` | Drops all `test_mko_bazuna*` DBs (including `gw*` shards) via psql `\gexec` | `make test-clean-db` → exit 0; 0 stale DBs remain |
| `make test-recreate` | Depends on `test-clean-db` | `make test-recreate` runs cleanup first |
| `Makefile.ps1` | `Invoke-TestCleanDb` + switch entry + help text; `Invoke-TestRecreate` calls it | `.\Makefile.ps1 test-clean-db` → exit 0 |
| `test_docs_ci_parity.py` | Asserts live CI config matches contract | `pytest src/backend/tests/test_docs_ci_parity.py` → exit 0 |

### NO-GO (explicitly excluded — do not touch)

§8-rec-3 — `prepare_threshold: None` in `src/backend/config/settings/base.py:160,172-173` — **DO NOT TOUCH**. The Validator rejected this as a false premise: PgBouncer IS deployed in `docker-compose.prod.yml:99-121` with `PGBOUNCER_POOL_MODE=transaction`, and 7 spec docs require `prepare_threshold: None`. The "PgBouncer async safety (zone C5)" comments at `base.py:158` and `base.py:170` are accurate audit-zone references. Keep all settings and comments unchanged.

---

## 2. Findings vs active_findings_compiled.md

This plan covers exactly the §9.2 GO findings. §8-rec-3 (§9.2 line 502) and D-03 (§9.3, treated as stale-resolved) are excluded.

| §9.2 ID | Finding | Status | This Plan Task | Action |
|---|---|---|---|---|
| D-02 | Plan §1.4 claims "all 934 tests" / wrong CI command | GO | **T1** | Rewrite §1.4 to match `ci.yml:91` (`-m "not seed" -n auto --dist loadgroup --reuse-db`, ~1111 tests) |
| D-01 | Plan §1.2 says markers "Not registered"; stale `e2e` refs | GO | **T2** | Rewrite §1.2 to 8 registered markers; purge all `e2e` references (§1.3, §4.1, §4.3, §5.1, §7, §10, §13, §14 T-01, §14 note) |
| D-04 | §14 T-01/T-05/T-10 use `loadscope`/`e2e` (stale) | GO | **T3** | Reconcile §14 T-01/T-05/T-10 rows with `loadgroup`, `e2e` removed, nightly serial |
| §8-rec-4 | Stale `gw*` DB cleanup missing from `make test-recreate` | GO | **T4** | Add `test-clean-db` target (Makefile + Makefile.ps1) using psql `\gexec` |
| §8-rec-3 | Remove `prepare_threshold: None` | NO-GO | — | Not planned. PgBouncer in prod; keep setting + comments. |
| §9.4 Prevention | Add `test_docs_ci_parity.py` | GO | **T5** | New prevention test; stdlib-only parsing |

---

## 3. Research Decision — No Research Gate Required

**Decision: RESOLVED — no Researcher agent needed.**

The task brief raises a research question: "The project doesn't have PyYAML as a dependency. Need to determine: should this test use string-level parsing, or should PyYAML be added as a dev dependency?"

**Verification performed (read from working tree + `uv run python`):**

| Dependency | Status | Evidence |
|---|---|---|
| `tomllib` | **Available** (stdlib, Python 3.11+) | Project requires Python 3.14 (`pyproject.toml:9`); `uv run python -c "import tomllib"` → OK |
| `ruamel.yaml` | **Available** (declared production dep) | `pyproject.toml:26`: `ruamel.yaml>=0.19.0`; `uv run python -c "import ruamel.yaml"` → OK |
| `PyYAML` | Available but NOT declared | Installed transitively (6.0.3); not in `pyproject.toml` `[project.dependencies` |

**Implementation decision for T5:**

- **TOML parsing:** Use `tomllib` (stdlib). Parse `pyproject.toml` to assert on the markers list, addopts, etc. Zero new dependencies.
- **YAML parsing:** Use **string-level parsing** (`Path.read_text()` + `in` / `not in` checks). Rationale:
  1. The CI values we assert (`--dist loadgroup`, `-m "not seed"`, `--reuse-db`) are embedded in `run:` command strings — structured YAML navigation adds complexity without benefit.
  2. Follows the project precedent of `test_i18n_completeness.py` (doc-DoD enforcement, "No third-party deps: stdlib regex for template scanning").
  3. `ruamel.yaml` IS available as a declared production dep if structured parsing is ever preferred, but string-level is simpler and sufficient.

**No dependency addition required. No research gate.**

---

## 4. Task Dependency Graph (DAG)

```
                    ┌─────────────┐
                    │     T5      │  New test file
                    │ (prevention)│  src/backend/tests/
                    │             │  test_docs_ci_parity.py
                    └─────────────┘
                           │
              (Makefile assertions depend on T4)
                           │
              ┌────────────┼────────────┬────────────┐
              │            │            │            │
     ┌────────▼──┐  ┌──────▼─────┐  ┌───▼──────────┐  │
     │    T1     │  │    T2      │  │     T3        │  │
     │  (D-02)   │  │  (D-01)    │  │  (D-04)       │  │
     │ §1.4      │  │ §1.2 + e2e │  │  §14 table    │  │
     │ rewrite   │  │ purge      │  │  recon        │  │
     └───────────┘  └────────────┘  └───┬───────────┘  │
                                         │              │
                    (same file — coordinate)              │
                                         │              │
     ┌────────────────────┐  ┌───────────▼──────────┐    │
     │     T4             │  │                      │    │
     │  (§8-rec-4)        │  │  shared file concern │    │
     │ Makefile +         │  │  T1/T2/T3 all edit   │    │
     │ Makefile.ps1       │  │  25_test-optimization │    │
     │ test-clean-db      │  │  -plan_done.md       │    │
     └────────────────────┘  └──────────────────────┘    │
```

**Parallel-safe:**
- T1, T2, T3 (doc edits) — same file `25_test-optimization-plan_done.md`, different sections. Apply in a single sequential edit pass using semantic-anchor matching (text content, not line numbers).
- T4 (Makefile + Makefile.ps1) — different files, fully independent of T1-T3/T5.
- T5 (new test file) — new file. The ci.yml/ci-nightly.yml/pyproject.toml/entrypoint-test.sh assertions have **no dependencies**. The 3 Makefile parity assertions **require T4 to be implemented first**.

**Cross-task relationship:**
- T5 validates live source files (`ci.yml`, `pyproject.toml`, etc.), not the plan doc. T5 catches future drift, not the current doc corrections.

---

## 5. Task Specifications

### T1 — D-02: Rewrite Plan §1.4 to Match Live CI

| Field | Value |
|---|---|
| **Priority** | P2 (doc-only) |
| **Risk** | Trivial — text edit in a "done" plan doc |
| **File** | `.ai/plans/done/25_test-optimization-plan_done.md` |
| **Semantic anchors** | §1.4 `test` job table row (line 70) + Problems bullets (lines 75, 76, 77, 79) |
| **blocked_by** | None |

**Verified live facts (from source):**
- `ci.yml:91`: `uv run pytest -m "not seed" -n auto --dist loadgroup --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db`
- `ci-nightly.yml:73`: `uv run pytest -m "seed" --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db` (no `-n`, no `--dist`)
- Non-seed test count: ~1111 (compiled report §4: 1129 collected; §12 note: 1111 non-seed + 26 seed; treat as directional)

**Changes — exact old-string → new-string replacements:**

1. **Line 70** — `test` job table row:

   **Old:**
   ```
   | `test` | push/PR | `uv run pytest --tb=short --cov --cov-report=term --cov-report=xml` |
   ```

   **New:**
   ```
   | `test` | push/PR | `uv run pytest -m "not seed" -n auto --dist loadgroup --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db` (see [ci.yml:91](.github/workflows/ci.yml)) |
   ```

2. **Line 75** — seed test count claim:

   **Old:**
   ```
   - `test` job runs **all 934 tests** including the ~18-minute seed batch.
   ```

   **New:**
   ```
   - `test` job runs the **non-seed tier only** (~1111 tests); the ~18-minute seed batch (`@pytest.mark.seed`, ~16 tests) runs daily in `ci-nightly.yml` at 03:00 UTC (no xdist, serial).
   ```

3. **Line 76** — test splitting (stale):

   **Old:**
   ```
   - **No test splitting** — single job runs everything sequentially.
   ```

   **New:**
   ```
   - **Test splitting enabled** — CI uses `-n auto` (pytest-xdist, all cores) with `--dist loadgroup` so bot tests sharing FSM state via `xdist_group("bot_concurrent")` are pinned to one worker.
   ```

4. **Line 77** — `--reuse-db` (stale):

   **Old:**
   ```
   - **No `--reuse-db`** — fresh PostgreSQL service each CI run (acceptable in CI, but means full schema setup every time).
   ```

   **New:**
   ```
   - **`--reuse-db` is used in CI** — ephemeral PostgreSQL service is destroyed after each CI run; `--reuse-db` is safe because the service is fresh. Local dev uses `--reuse-db` by default (see `entrypoint-test.sh:41`); `make test-recreate` overrides with `--no-reuse-db --create-db`.
   ```

5. **Line 79** — nightly workflow (stale):

   **Old:**
   ```
   - No nightly/scheduled workflow for slow tests.
   ```

   **New:**
   ```
   - **Nightly workflow exists** — `ci-nightly.yml` runs `@pytest.mark.seed` daily at 03:00 UTC (no xdist; serial run).
   ```

**Acceptance criteria:**
- `grep -n "loadgroup" .github/workflows/ci.yml` returns a match on line 91 (already verified)
- §1.4 no longer contains "all 934 tests": `grep "all 934 tests" .ai/plans/done/25_test-optimization-plan_done.md` → empty
- §1.4 table row references `--dist loadgroup` and `-m "not seed"` and `--reuse-db`

---

### T2 — D-01: Rewrite Plan §1.2 Markers Table + Purge All Stale `e2e` References

| Field | Value |
|---|---|
| **Priority** | P2 (doc-only) |
| **Risk** | Trivial — text edits in a "done" plan doc |
| **File** | `.ai/plans/done/25_test-optimization-plan_done.md` |
| **Semantic anchors** | §1.2 table (lines 33-44); §1.3 addopts code block (line 52); scattered `e2e` references at lines 203, 255, 273, 466, 553, 679, 724 |
| **blocked_by** | None |

**Verified live facts:**
- `pyproject.toml:163-172`: 8 markers registered: `unit, integration, seed, settings, concurrent, slow, real_images, xdist_group`
- `rules.md:51`: "The `e2e` marker was removed — do not reference it."
- `pyproject.toml:160`: `addopts = ["--import-mode=importlib", "-ra", "-q"]` (no `--cov`)
- §14 T-03 row (line 695) already correctly states the final addopts

**Changes:**

1. **§1.2 table (lines 33-44) — complete replacement:**

   **Old:**
   ```
   | Marker | Registered | Applied | Scope |
   |--------|-----------|---------|-------|
   | `slow` | Yes | ~32 modules | Module-level `pytestmark` (all-or-nothing) |
   | `integration` | Yes | ~32 modules | Module-level `pytestmark` (all-or-nothing) |
   | `django_db` | Yes (pytest-django) | ~40 modules | Per-module or per-class |
   | `django_db(transaction=True)` | Yes (pytest-django) | 5 modules | Per-module `pytestmark` (bot tests only) |
   | `asyncio` | Yes (pytest-asyncio) | 3 modules | Per-module or per-test |
   | `unit` | Not registered | 0 | — |
   | `e2e` | Not registered | 0 | — |
   | `seed` | Not registered | 0 | — |
   | `settings` | Not registered | 0 | — |
   | `concurrent` | Not registered | 0 | — |
   ```

   **New:**
   ```
   | Marker | Registered (pyproject.toml:163-172) | Applied | Scope |
   |--------|-----------|---------|-------|
   | `unit` | Yes | 235 tests | Pure unit tests, no database |
   | `integration` | Yes | ~700 tests | DB-backed integration tests (fast + standard) |
   | `seed` | Yes | ~16 tests (5 classes) | Nightly-only; invokes `call_command('seed')` / `ImageGenerator` |
   | `settings` | Yes | 3 tests | Import-time validation via subprocess isolation |
   | `concurrent` | Yes | ~44 tests (6 bot modules) | `transaction=True` (TRUNCATE per test) |
   | `slow` | Yes | ~32 modules | Module-level `pytestmark` (all-or-nothing) |
   | `real_images` | Yes | opt-in | Opts out of the no-op `ImageGenerator` stub to use the real pipeline |
   | `xdist_group` | Yes (pytest-xdist built-in) | 6 bot modules | Pins tests to a single xdist worker via `--dist loadgroup`; **not project taxonomy** — re-registration is redundant |
   | `e2e` | **Removed** | 0 | Per `docs/99-agent/rules.md:51`: "The `e2e` marker was removed — do not reference it." |
   | `django_db` (pytest-django) | Yes (pytest-django) | ~40 modules | Per-module or per-class |
   | `django_db(transaction=True)` | Yes (pytest-django) | 5 modules | Per-module `pytestmark` (bot tests only) |
   | `asyncio` (pytest-asyncio) | Yes (pytest-asyncio) | 3 modules | Per-module or per-test |
   ```

2. **§1.3 addopts correction (line 52):**

   **Old:**
   ```
   addopts = ["--import-mode=importlib", "-ra", "-q", "--cov", "--cov-report=term-missing"]
   ```

   **New:**
   ```
   addopts = ["--import-mode=importlib", "-ra", "-q"]
   ```

3. **§1.3 code block — add note below closing backtick fence (after line 57):**

   **Old:**
   ```
   ```
   ```

   **New:**
   ```

   > `--cov` is **not** in `addopts` — it is CI-only (passed on the command line in `ci.yml:91` and `ci-nightly.yml:73`). `--reuse-db` is applied via the default `PYTEST_OPTS` in `entrypoint-test.sh:41`, not via `addopts`.
   ```
   ```

4. **Line 203** (§4.1 Proposed State — Current→Proposed row):

   **Old:**
   ```
   | All DB tests = `integration` | `integration` (fast DB) + `e2e` (multi-component) | Separate fast DB unit tests from view/HTTP tests |
   ```

   **New:**
   ```
   | All DB tests = `integration` | `integration` (fast DB); no `e2e` tier (removed) | Separate by seed/settings/concurrent markers instead |
   ```

5. **Line 255** (§4.3 proposed markers list — remove stale `e2e` entry):

   **Old:**
   ```
       "e2e: marks multi-component end-to-end tests (HTTP client, FTS, views)",
   ```

   **New:** *(delete entire line — the proposed marker list is obsolete; live `pyproject.toml:163-172` shows the final 8-marker set)*

6. **Line 273** (§5.1 Suite Composition — CI row):

   **Old:**
   ```
   | **CI (PR / commit)** | `pytest -m "not seed" --cov` | ~918 | ~85s | Fast feedback: unit + integration + e2e + concurrent + settings |
   ```

   **New:**
   ```
   | **CI (PR / commit)** | `pytest -m "not seed" -n auto --dist loadgroup --cov --reuse-db` | ~1111 | ~85s | Fast feedback: unit + integration + concurrent + settings (no `e2e` tier) |
   ```

7. **Line 466** (§7 Implementation Steps — T-01 row):

   **Old:**
   ```
   | 1 | T-01 | Register `seed`, `unit`, `e2e`, `settings`, `concurrent` markers in `pyproject.toml` | P0 | Trivial | N/A (enables selection) | None |
   ```

   **New:**
   ```
   | 1 | T-01 | Register `seed`, `unit`, `settings`, `concurrent`, `slow`, `real_images`, `xdist_group` markers in `pyproject.toml` (`e2e` removed per rules.md:51) | P0 | Trivial | N/A (enables selection) | None |
   ```

8. **Line 553** (§10 Verification Steps):

   **Old:**
   ```
   # Expect: seed, unit, e2e, settings, concurrent all listed
   ```

   **New:**
   ```
   # Expect: seed, unit, settings, concurrent, slow, real_images, xdist_group all listed; NO e2e (removed)
   ```

9. **Line 679** (§13 Expected Outcomes — Marker granularity row):

   **Old:**
   ```
   | Marker granularity | Binary (slow + integration) | 5-tier (unit / integration / e2e / seed / settings / concurrent) | Same |
   ```

   **New:**
   ```
   | Marker granularity | Binary (slow + integration) | 8 registered (unit / integration / seed / settings / concurrent / slow / real_images / xdist_group; `e2e` removed) | Same |
   ```

10. **Line 724** (§14 T-12 correction note — `e2e` mentioned in a correct context):

    **Old:**
    ```
    > - **Current test inventory** (verified via `pytest --collect-only` with the project's real `pyproject.toml` config): **1137 tests across 90 test files** — **1111 non-seed** + **26 seed**; **235** are marked `@pytest.mark.unit`; **8** custom markers are registered (`unit`, `integration`, `seed`, `settings`, `concurrent`, `slow`, `real_images`, `xdist_group`; `e2e` was removed).
    ```

    **New:**
    ```
    > - **Current test inventory** (verified via `pytest --collect-only` with the project's real `pyproject.toml` config): **1137 tests across 90 test files** — **1111 non-seed** + **26 seed**; **235** are marked `@pytest.mark.unit`; **8** custom markers are registered (`unit`, `integration`, `seed`, `settings`, `concurrent`, `slow`, `real_images`, `xdist_group`; the end-to-end marker was removed).
    ```

**Acceptance criteria:**
- `grep -c "e2e" .ai/plans/done/25_test-optimization-plan_done.md` returns 0
- §1.2 marker list matches `pyproject.toml:163-172` (8 markers)
- §1.3 addopts no longer contains `--cov`

---

### T3 — D-04: Reconcile §14 Completion Table (T-01, T-05, T-10)

| Field | Value |
|---|---|
| **Priority** | P2 (doc-only) |
| **Risk** | Trivial — text edits in §14 table |
| **File** | `.ai/plans/done/25_test-optimization-plan_done.md` |
| **Semantic anchors** | §14 T-01 (line 693), T-05 (line 697), T-10 (line 702) |
| **blocked_by** | None (T2 also touches line 693 for `e2e` removal in a different column — apply T2's row-693 fix first, then T3's) |

**Verified live facts:**
- `ci.yml:91`: `--dist loadgroup` (NOT `loadscope`), includes `--reuse-db`
- `ci-nightly.yml:73`: `pytest -m "seed"` — no `-n auto`, no `--dist` (serial)
- `pyproject.toml:171`: `xdist_group` registered (pytest-xdist built-in, not project taxonomy per `rules.md:47`)

**Changes — exact old → new:**

1. **T-01 (line 693) — `e2e` registered → removed:**

   **Old:**
   ```
   | T-01 | Register `seed`, `unit`, `e2e`, `settings`, `concurrent` markers in `pyproject.toml` | ✅ Done | `pytest --collect-only` → 934 tests collected, no marker warnings |
   ```

   **New:**
   ```
   | T-01 | Register `seed`, `unit`, `settings`, `concurrent`, `slow`, `real_images`, `xdist_group` markers in `pyproject.toml` (`e2e` removed per rules.md:51) | ✅ Done | `pytest --collect-only` → 1137 tests collected; 8 markers registered, no `e2e` |
   ```

2. **T-05 (line 697) — `loadscope` → `loadgroup`; add `--reuse-db`:**

   **Old:**
   ```
   | T-05 | Modify `ci.yml` test job to run `pytest -m "not seed"` | ✅ Done | CI test job runs `uv run pytest -m "not seed" -n auto --dist loadscope --tb=short --cov --durations=10 --cov-report=term --cov-report=xml` |
   ```

   **New:**
   ```
   | T-05 | Modify `ci.yml` test job to run `pytest -m "not seed"` | ✅ Done | CI test job runs `uv run pytest -m "not seed" -n auto --dist loadgroup --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db` (see [ci.yml:91](.github/workflows/ci.yml)) |
   ```

3. **T-10 (line 702) — `loadscope` → `loadgroup`; nightly is serial:**

   **Old:**
   ```
   | T-10 | Add `pytest-xdist` to dev deps; enable `-n auto` in CI | ✅ Done | `pytest-xdist>=3.8.0` in dev group; `-n auto --dist loadscope` in `ci.yml` and `ci-nightly.yml` |
   ```

   **New:**
   ```
   | T-10 | Add `pytest-xdist` to dev deps; enable `-n auto` in CI | ✅ Done | `pytest-xdist>=3.8.0` in dev group; `-n auto --dist loadgroup` in `ci.yml` (PR gate); `ci-nightly.yml:73` runs seed **serially** (no `-n`, no `--dist`) |
   ```

**Acceptance criteria:**
- `grep -c "loadscope" .ai/plans/done/25_test-optimization-plan_done.md` returns 0
- §14 T-05 row says `--dist loadgroup`
- §14 T-10 row says `loadgroup` in ci.yml, serial in ci-nightly.yml
- §14 T-01 row marks `e2e` as removed

---

### T4 — §8-rec-4: Add `test-clean-db` Target (Makefile + Makefile.ps1)

| Field | Value |
|---|---|
| **Priority** | P1 (prevents recurring test failures from stale `gw*` DBs) |
| **Risk** | Low — new Makefile targets; only drops `test_mko_bazuna*` DBs; does NOT touch the persistent `postgres_data` volume or any non-test DB |
| **Files** | `Makefile` (edit), `Makefile.ps1` (edit) |
| **Semantic anchors** | `Makefile:.PHONY` (line 3); `Makefile:COMPOSE_PROJECT_NAME test group` (line 21); `Makefile:help test env section` (lines 38-45); `Makefile:test-recreate` (lines 133-139); `Makefile:test-logs` (lines 129-131) |
| **Semantic anchors (ps1)** | `Makefile.ps1:Show-Help test env lines` (lines 51-53); `Makefile.ps1:Invoke-TestRecreate` (lines 115-121); `Makefile.ps1:Invoke-TestDb` (lines 97-101); `Makefile.ps1:switch-case test entries` (lines 338-341) |
| **blocked_by** | None |

**Background (from compiled report §7.2 + §8.4):**

The project does NOT override `django_db_modify_db_settings` (grep: 0 matches in `src/`), so pytest-xdist's default per-worker DB creation is active. Each worker creates `test_mko_bazuna_gw0`, `test_mko_bazuna_gw1`, etc. Under `--reuse-db` (default in entrypoint + CI) with the persistent named volume `mko-bazuna-test_postgres_data` (confirmed in `docker-compose.test.yml:7-8`), stale `gw*` databases accumulate when worker count changes or runs are interrupted. `make test-recreate` runs `--no-reuse-db --create-db` but does NOT drop stale `gw*` DBs, and can fail with "database is being accessed by other users" when crashed-worker connections persist.

**Validator correction (§8.4):** The `DO $$ … EXECUTE 'DROP DATABASE'` PL/pgSQL block fails on PostgreSQL 18:
```
ERROR: DROP DATABASE cannot be executed from a function or procedure
```
`DROP DATABASE` is DDL that cannot execute inside a function/block. The correct approach is psql's `\gexec` meta-command (client-level, autocommit). Empirically validated against live test DB (dropped 16 stale databases, exit 0).

#### Makefile edits:

**Edit 1 — `.PHONY` (line 3):**

**Old:**
```makefile
.PHONY: help up down reset build restart test test-all test-db test-down test-logs test-recreate \
```

**New:**
```makefile
.PHONY: help up down reset build restart test test-all test-db test-down test-logs test-recreate test-clean-db \
```

**Edit 2 — `COMPOSE_PROJECT_NAME` target group (line 21):**

**Old:**
```makefile
test test-all test-db test-down test-logs test-recreate: \
    export COMPOSE_PROJECT_NAME = mko-bazuna-test
```

**New:**
```makefile
test test-all test-db test-down test-logs test-recreate test-clean-db: \
    export COMPOSE_PROJECT_NAME = mko-bazuna-test
```

**Edit 3 — Help text (after `test-logs`, before `test-recreate`):**

**Old:**
```makefile
	@echo "  test-logs      Follow test environment logs"
	@echo "  test-recreate  Drop and rebuild test DB schema (--no-reuse-db)"
```

**New:**
```makefile
	@echo "  test-logs      Follow test environment logs"
	@echo "  test-clean-db  Drop stale test databases (test_mko_bazuna + gw* shards)"
	@echo "  test-recreate  Drop and rebuild test DB schema (--no-reuse-db)"
```

**Edit 4 — Add `test-clean-db` target (insert after `test-logs` target at line 131, before `test-recreate` comment at line 133):**

```makefile
# Drop stale test databases (test_mko_bazuna + test_mko_bazuna_gw*) from the
# persistent test PostgreSQL volume. Run before test-recreate to handle stuck
# connections from crashed xdist workers. Uses psql \gexec — DROP DATABASE
# cannot run inside a DO $$ block on PostgreSQL 13+ (PG restriction:
# "DROP DATABASE cannot be executed from a function or procedure").
# Empirically verified: drops all 16 stale gw* databases, exit 0.
test-clean-db:
	docker compose $(COMPOSE_TEST) up -d db
	docker compose $(COMPOSE_TEST) exec -T db psql -U postgres -d postgres -c \
		"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname LIKE 'test_mko_bazuna%' AND pid <> pg_backend_pid();"
	docker compose $(COMPOSE_TEST) exec -T db psql -U postgres -d postgres -t -A -c \
		"SELECT format('DROP DATABASE IF EXISTS %I WITH (FORCE);', datname) FROM pg_database WHERE datname LIKE 'test_mko_bazuna%'" \
	| while IFS= read -r stmt; do docker compose $(COMPOSE_TEST) exec -T db psql -U postgres -d postgres -c "$$stmt"; done
	@echo "Stale test databases dropped."
```

**Key details:**
- `$(COMPOSE_TEST)` = `-f docker-compose.yml -f docker-compose.test.yml` (Makefile:11)
- `$$stmt` uses Make's `$$` escaping → shell receives `$stmt` (correct for bash `while` loop)
- `-T db` disables Docker TTY allocation (required for piped psql output over Docker exec)
- `-t -A` psql flags: `-t` (tuples only, no headers), `-A` (unaligned/raw output) — produces clean DROP statements
- `WITH (FORCE)` requires PostgreSQL 13+ (project uses PG18)
- `pid <> pg_backend_pid()` ensures the current psql session is never killed
- `LIKE 'test_mko_bazuna%'` matches both `test_mko_bazuna` and `test_mko_bazuna_gw0` through `gw15`

**Edit 5 — Modify `test-recreate` to depend on `test-clean-db`:**

**Old:**
```makefile
test-recreate:
	docker compose $(COMPOSE_TEST) up -d db
	docker compose $(COMPOSE_TEST) run --rm --env PYTEST_OPTS="--no-reuse-db --create-db --tb=short -n auto --dist loadgroup" test
```

**New:**
```makefile
test-recreate: test-clean-db
	# test-clean-db (pre-flight) drops stale test_mko_bazuna* + gw* databases,
	# handling stuck connections from crashed xdist workers before pytest runs.
	docker compose $(COMPOSE_TEST) up -d db
	docker compose $(COMPOSE_TEST) run --rm --env PYTEST_OPTS="--no-reuse-db --create-db --tb=short -n auto --dist loadgroup" test
```

#### Makefile.ps1 edits:

**Edit 1 — Help text (Show-Help, after `test-logs`):**

**Old:**
```powershell
    Write-Host "  test-logs      Follow test environment logs"
    Write-Host "  test-recreate  Drop and rebuild test DB schema (--no-reuse-db)"
```

**New:**
```powershell
    Write-Host "  test-logs      Follow test environment logs"
    Write-Host "  test-clean-db  Drop stale test databases (test_mko_bazuna + gw* shards)"
    Write-Host "  test-recreate  Drop and rebuild test DB schema (--no-reuse-db)"
```

**Edit 2 — Add `Invoke-TestCleanDb` function (insert before `Invoke-TestRecreate`, after `Invoke-TestDb`):**

```powershell
# Drop stale test databases (test_mko_bazuna + gw* shards) from the persistent
# test PostgreSQL volume. Uses psql format() to generate DROP DATABASE statements
# and executes each via `psql -c` (psql \gexec is not available for piped input
# in PowerShell the same way as bash). Run before Invoke-TestRecreate to handle
# stuck connections from crashed xdist workers.
function Invoke-TestCleanDb {
    $env:COMPOSE_PROJECT_NAME = $TestProject
    docker compose -f docker-compose.yml -f docker-compose.test.yml up -d db
    # Terminate active connections to test databases (exclude this session)
    docker compose -f docker-compose.yml -f docker-compose.test.yml exec -T db psql -U postgres -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname LIKE 'test_mko_bazuna%' AND pid <> pg_backend_pid();"
    # Generate DROP DATABASE IF EXISTS ... WITH (FORCE); statements and execute each
    docker compose -f docker-compose.yml -f docker-compose.test.yml exec -T db psql -U postgres -d postgres -t -A -c "SELECT format('DROP DATABASE IF EXISTS %I WITH (FORCE);', datname) FROM pg_database WHERE datname LIKE 'test_mko_bazuna%'" | ForEach-Object {
        $stmt = $_.Trim()
        if ($stmt) {
            docker compose -f docker-compose.yml -f docker-compose.test.yml exec -T db psql -U postgres -d postgres -c $stmt
        }
    }
    Write-Host "Stale test databases dropped." -ForegroundColor Green
}
```

**PowerShell notes:**
- The Makefile uses a bash `while IFS= read -r` loop; PowerShell uses `ForEach-Object` (equivalent)
- `$_` in PowerShell is the current pipeline object (each line of psql output)
- `.Trim()` removes leading/trailing whitespace from psql `-t -A` output
- The `if ($stmt)` guard handles empty lines in the output

**Edit 3 — Modify `Invoke-TestRecreate` to call cleanup first:**

**Old:**
```powershell
function Invoke-TestRecreate {
    $env:COMPOSE_PROJECT_NAME = $TestProject
    docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm --env "PYTEST_OPTS=--no-reuse-db --create-db --tb=short -n auto --dist loadgroup" test
}
```

**New:**
```powershell
function Invoke-TestRecreate {
    # Pre-flight: drop stale test_mko_bazuna + gw* databases (handles stuck
    # connections from crashed xdist workers before pytest spawns new ones).
    Invoke-TestCleanDb
    $env:COMPOSE_PROJECT_NAME = $TestProject
    docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm --env "PYTEST_OPTS=--no-reuse-db --create-db --tb=short -n auto --dist loadgroup" test
}
```

**Edit 4 — Switch-case dispatch (after `test-logs`, before `test-recreate`):**

**Old:**
```powershell
    "test-logs" { Invoke-TestLogs }
    "test-recreate" { Invoke-TestRecreate }
```

**New:**
```powershell
    "test-logs" { Invoke-TestLogs }
    "test-clean-db" { Invoke-TestCleanDb }
    "test-recreate" { Invoke-TestRecreate }
```

**Acceptance criteria:**
- `make test-clean-db` drops all `test_mko_bazuna*` databases (including `gw*` shards), exit 0
- `make test-recreate` depends on `test-clean-db` (Makefile prerequisite)
- `test-clean-db` is in `.PHONY` (Makefile line 3) and the `COMPOSE_PROJECT_NAME = mko-bazuna-test` target group (Makefile line 21)
- `test-clean-db` appears in `make help` output
- `.\Makefile.ps1 test-clean-db` runs `Invoke-TestCleanDb`, exit 0
- `.\Makefile.ps1 test-recreate` calls `Invoke-TestCleanDb` first
- `test-clean-db` appears in `.\Makefile.psh help` output
- `test-clean-db` has a switch-case entry in `Makefile.ps1`

---

### T5 — T_PREVENTION: Add `test_docs_ci_parity.py` (prevention test)

| Field | Value |
|---|---|
| **Priority** | P2 (prevention — catches D-01/D-02/D-04 class drift and §8-rec-4 regression) |
| **Risk** | Low — new test file; no production code changes; stdlib-only parsing; no DB needed (`@pytest.mark.unit`, no `@pytest.mark.django_db`) |
| **File** | `src/backend/tests/test_docs_ci_parity.py` (NEW — `src/backend/tests/` directory must be created first) |
| **Semantic anchors** | Module-level constants resolving to `.github/workflows/ci.yml:91`, `.github/workflows/ci-nightly.yml:73`, `pyproject.toml:160,163-172`, `docker/entrypoint-test.sh:41`, `Makefile` (`test-clean-db` target + `.PHONY` + `test-recreate` dependency) |
| **blocked_by** | None for ci.yml/ci-nightly.yml/pyproject.toml/entrypoint assertions. The 3 Makefile parity assertions (last 3 tests) **require T4 to be implemented first** — these tests verify T4's output. |

**Research decision:** No research gate. `tomllib` (stdlib, Python 3.11+; project requires 3.14) handles TOML. YAML files are read as text with string-level assertions. No `PyYAML` addition required.

**Verified live facts (asserted by the test):**
- `ci.yml:91`: contains `--dist loadgroup`, `-m "not seed"`, `-n auto`, `--reuse-db`, `--cov`, `--cov-report=xml`
- `ci-nightly.yml:73`: contains `-m "seed"`; does NOT contain `-n auto` or `--dist`
- `pyproject.toml:163-172`: 8 markers (`unit, integration, seed, settings, concurrent, slow, real_images, xdist_group`); no `e2e`
- `pyproject.toml:160`: `addopts = ["--import-mode=importlib", "-ra", "-q"]` (no `--cov`)
- `entrypoint-test.sh:41`: default PYTEST_OPTS includes `--reuse-db` and `--dist loadgroup`
- `Makefile`: `test-clean-db:` target; `.PHONY` includes `test-clean-db`; `test-recreate: test-clean-db` (these require T4 first)

**Test file content:**

```python
"""
CI configuration parity tests (Prevention — guards against D-01/D-02/D-04 / §8-rec-4 drift).

Asserts that live CI configuration matches the documented contract, converting
doc drift into a CI gate:

1. ci.yml:91 uses `--dist loadgroup` + `-m "not seed"` + `--reuse-db` (not loadscope).
2. ci-nightly.yml:73 uses `-m "seed"` with NO xdist (serial run).
3. pyproject.toml: no `e2e` marker; `xdist_group` registered; `addopts` has no `--cov`.
4. entrypoint-test.sh:41 default PYTEST_OPTS includes `--reuse-db` + `--dist loadgroup`.
5. Makefile: `test-clean-db` target exists, is in `.PHONY`, and `test-recreate`
   depends on it (requires T4/§8-rec-4 to be implemented first).

Uses stdlib only: tomllib for TOML; Path.read_text() for YAML (string-level checks).
No PyYAML dependency — the asserted values are command-line substrings in `run:` lines.
Follows the test_i18n_completeness.py precedent (doc-DoD enforcement, no third-party deps).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Resolve repository root by searching upward for pyproject.toml.
# Robust to varying CWD in Docker (WORKDIR=/app or /app/src/backend) and
# local development (from repo root). pyproject.toml exists only at repo root.
_ROOT = Path(__file__).resolve().parent
while not (_ROOT / "pyproject.toml").exists():
    _ROOT = _ROOT.parent

_CI_YML = _ROOT / ".github" / "workflows" / "ci.yml"
_CI_NIGHTLY_YML = _ROOT / ".github" / "workflows" / "ci-nightly.yml"
_PYPROJECT = _ROOT / "pyproject.toml"
_ENTRYPOINT = _ROOT / "docker" / "entrypoint-test.sh"
_MAKEFILE = _ROOT / "Makefile"


# --- ci.yml parity -------------------------------------------------------


def test_ci_uses_loadgroup() -> None:
    """ci.yml:91 must use --dist loadgroup (not loadscope)."""
    text = _CI_YML.read_text()
    assert "--dist loadgroup" in text, "ci.yml:91 must use --dist loadgroup"


def test_ci_excludes_seed() -> None:
    """ci.yml:91 must exclude seed tests with -m 'not seed'."""
    text = _CI_YML.read_text()
    assert '-m "not seed"' in text, "ci.yml:91 must use -m 'not seed'"


def test_ci_uses_reuse_db() -> None:
    """ci.yml:91 must use --reuse-db."""
    text = _CI_YML.read_text()
    assert "--reuse-db" in text, "ci.yml:91 must use --reuse-db"


def test_ci_does_not_use_loadscope() -> None:
    """ci.yml must never reference loadscope."""
    text = _CI_YML.read_text()
    assert "--dist loadscope" not in text, "ci.yml must not use --dist loadscope"


def test_ci_command_subset() -> None:
    """ci.yml:91 must contain the full expected command token set."""
    text = _CI_YML.read_text()
    expected = (
        '-m "not seed"',
        "-n auto",
        "--dist loadgroup",
        "--reuse-db",
        "--cov",
        "--cov-report=xml",
    )
    missing = [token for token in expected if token not in text]
    assert not missing, f"ci.yml missing expected tokens: {missing}"


# --- ci-nightly.yml parity -----------------------------------------------


def test_nightly_runs_seed() -> None:
    """ci-nightly.yml:73 must run -m 'seed'."""
    text = _CI_NIGHTLY_YML.read_text()
    assert '-m "seed"' in text, "ci-nightly.yml:73 must use -m 'seed'"


def test_nightly_is_serial() -> None:
    """ci-nightly.yml must NOT use xdist (no -n, no --dist)."""
    text = _CI_NIGHTLY_YML.read_text()
    assert "-n auto" not in text, "ci-nightly.yml must not use -n auto (serial run)"
    assert "--dist" not in text, "ci-nightly.yml must not use --dist (serial run)"


# --- pyproject.toml parity -----------------------------------------------


def _load_pyproject() -> dict:
    with _PYPROJECT.open("rb") as f:
        return tomllib.load(f)


def _marker_names() -> list[str]:
    markers: list[str] = _load_pyproject()["tool"]["pytest"]["ini_options"]["markers"]
    return [m.split(":")[0] for m in markers]


def test_no_e2e_marker() -> None:
    """e2e must not be a registered marker (removed per rules.md:51)."""
    assert "e2e" not in _marker_names(), "e2e marker must not be registered"


def test_xdist_group_marker_registered() -> None:
    """xdist_group must be in the markers list (pytest-xdist built-in)."""
    assert "xdist_group" in _marker_names()


def test_xdist_group_not_double_registered() -> None:
    """xdist_group must appear exactly once in markers (not double-registered)."""
    names = _marker_names()
    assert names.count("xdist_group") == 1, "xdist_group must appear exactly once"


def test_addopts_has_no_cov() -> None:
    """--cov must not be in addopts (CI-only, passed on command line)."""
    addopts: list[str] = _load_pyproject()["tool"]["pytest"]["ini_options"]["addopts"]
    assert "--cov" not in addopts, "--cov must be CI-only"


def test_addopts_uses_importlib() -> None:
    """addopts must use --import-mode=importlib."""
    addopts: list[str] = _load_pyproject()["tool"]["pytest"]["ini_options"]["addopts"]
    assert "--import-mode=importlib" in addopts


# --- entrypoint-test.sh parity -------------------------------------------


def test_entrypoint_defaults_reuse_db() -> None:
    """entrypoint-test.sh:41 default PYTEST_OPTS must include --reuse-db."""
    text = _ENTRYPOINT.read_text()
    assert "--reuse-db" in text


def test_entrypoint_defaults_loadgroup() -> None:
    """entrypoint-test.sh:41 default PYTEST_OPTS must include --dist loadgroup."""
    text = _ENTRYPOINT.read_text()
    assert "--dist loadgroup" in text


# --- Makefile parity (requires T4 / §8-rec-4 implemented) ----------------


def test_makefile_has_test_clean_db() -> None:
    """Makefile must define a test-clean-db target."""
    text = _MAKEFILE.read_text()
    assert "test-clean-db:" in text


def test_makefile_phony_includes_test_clean_db() -> None:
    """test-clean-db must be declared in .PHONY."""
    text = _MAKEFILE.read_text()
    phony_line = text.split(".PHONY")[1].split("\n")[0]
    assert "test-clean-db" in phony_line


def test_makefile_test_recreate_depends_on_clean_db() -> None:
    """test-recreate must depend on test-clean-db (pre-flight cleanup)."""
    text = _MAKEFILE.read_text()
    assert "test-recreate: test-clean-db" in text
```

**Implementation steps:**
1. Create directory `src/backend/tests/` (does not currently exist — verified via `Get-ChildItem`)
2. Write `src/backend/tests/test_docs_ci_parity.py` with the content above
3. No `__init__.py` needed (`--import-mode=importlib` in `pyproject.toml:160`)
4. No `conftest.py` needed (root conftest at `src/backend/conftest.py` applies)

**Acceptance criteria:**
- `src/backend/tests/test_docs_ci_parity.py` exists
- `pytest src/backend/tests/test_docs_ci_parity.py` → exit 0 (all 17 tests pass)
- All tests are marked `@pytest.mark.unit` (fast gate, no DB)
- No third-party imports beyond `tomllib` (stdlib) and `pytest` (already a dev dependency)

---

## 6. Execution Order (Phased)

### Phase 1 — Foundation (parallel: T4 + T5 file creation, sequential: doc edits)

| Task | Duration | Rationale |
|---|---|---|
| **T4a** — Makefile `test-clean-db` target | 5 min | Different file; fully independent |
| **T4b** — Makefile.ps1 `Invoke-TestCleanDb` + switch entry | 10 min | Different file; fully independent |
| **T5a** — Create `src/backend/tests/` dir | 1 min | New file; independent |
| **T5b** — Write `test_docs_ci_parity.py` | 5 min | New file; independent |
| **T1/T2/T3** — Doc edits (sequential, same file) | 10 min | Same file; apply in order T2 → T1 → T3 to avoid line-shift conflicts |

**Rationale:** T4 and T5 touch different files and can run fully in parallel. The T1/T2/T3 doc edits all touch `25_test-optimization-plan_done.md` — apply them in a single sequential pass (T2 first since it touches the most e2e references, then T1 for §1.4, then T3 for §14) to avoid line-shift conflicts.

### Phase 2 — Verification

| Step | Command | Expected |
|---|---|---|
| 2.1 Verify D-01 (no e2e) | `grep -c "e2e" .ai/plans/done/25_test-optimization-plan_done.md` | 0 |
| 2.2 Verify D-04 (no loadscope) | `grep -c "loadscope" .ai/plans/done/25_test-optimization-plan_done.md` | 0 |
| 2.3 Verify D-02 (no "934 tests") | `grep "all 934 tests" .ai/plans/done/25_test-optimization-plan_done.md` | empty |
| 2.4 Verify §1.3 no `--cov` in addopts | `grep "addopts" .ai/plans/done/25_test-optimization-plan_done.md` | shows `["--import-mode=importlib", "-ra", "-q"]` |
| 2.5 Verify §8-rec-4 Makefile | `make test-clean-db` | exit 0; all `test_mko_bazuna*` DBs dropped |
| 2.6 Verify §8-rec-4 Makefile.ps1 | `.\Makefile.ps1 test-clean-db` | exit 0; all `test_mko_bazuna*` DBs dropped |
| 2.7 Verify §8-rec-4 test-recreate dep | `grep "test-recreate: test-clean-db" Makefile` | match found |
| 2.8 Run prevention test | `pytest src/backend/tests/test_docs_ci_parity.py` | 17 passed, exit 0 |

**Timeline estimate:** ~25–35 minutes total (most steps are trivial text edits; §8-rec-4 requires Docker DB access for empirical verification).

---

## 7. Appendices

### Appendix A — Files Referenced (read-only verification)

| File | Lines Checked | Verification Result |
|---|---|---|
| `pyproject.toml` | 160, 163-172 | `addopts` has no `--cov`; 8 markers registered; no `e2e` |
| `.github/workflows/ci.yml` | 91 | `pytest -m "not seed" -n auto --dist loadgroup --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db` |
| `.github/workflows/ci-nightly.yml` | 73 | `pytest -m "seed" --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db` (no `-n`, no `--dist`) |
| `docker/entrypoint-test.sh` | 41 | Default PYTEST_OPTS: `--reuse-db --tb=short --durations=10 -n auto --dist loadgroup` |
| `docs/99-agent/rules.md` | 47-51 | `xdist_group` is pytest-xdist built-in; "The `e2e` marker was removed — do not reference it." |
| `Makefile` | 3-5, 11, 21, 117-139 | `.PHONY` has no `test-clean-db`; `COMPOSE_TEST` defined; `test-recreate` has no cleanup |
| `Makefile.ps1` | 51-53, 97-121, 333-367 | `Invoke-TestRecreate` has no cleanup; switch-case has no `test-clean-db` |
| `docker-compose.test.yml` | 7-8 | Persistent `postgres_data` volume confirmed |
| `docker-compose.prod.yml` | 99-121 | PgBouncer service with `PGBOUNCER_POOL_MODE=transaction`, opt-in via `profiles: ["pgbouncer"]` |
| `src/backend/config/settings/base.py` | 158-174 | `prepare_threshold: None` at lines 160, 172-173; "PgBouncer async safety (zone C5)" at 158, 170 — **DO NOT TOUCH** |
| `src/backend/conftest.py` | 64, 74, 84, 90, 105, 147 | Canonical `seller`, `user`, `category`, `city` fixtures + `create_test_ad` (preimage for T5) |
| `.ai/plans/done/25_test-optimization-plan_done.md` | 28, 40-44, 52, 75-79, 203, 255, 273, 466, 553, 679, 693, 697, 702, 724 | 9 stale `e2e` references; stale `loadscope` at 697/702; stale `addopts` at 52; stale CI at 70/75-79 |

### Appendix B — Risk Summary

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Doc edits introduce inconsistency | Low | Low | T5 prevention test asserts live config; doc edits are text-only, verifiable by grep |
| T1/T2/T3 edits conflict (same file) | Medium | Low | Apply sequentially in order T2→T1→T3; use semantic-anchor matching, not line numbers |
| `test-clean-db` drops wrong databases | Low | Medium | Pattern `LIKE 'test_mko_bazuna%'` only matches test DBs; `pid <> pg_backend_pid()` protects current session |
| Makefile `$$stmt` escaping error | Low | Low | Use exact validated code from §8.4 (empirically tested, exit 0) |
| PowerShell `ForEach-Object` empty output | Low | Low | `if ($stmt)` guard handles empty lines |
| T5 Makefile parity tests fail if run before T4 | High (if run early) | Low | Phase 1 runs T4 and T5 concurrently; T5 Makefile assertions only pass AFTER T4 is applied |
| Prevention test false-positive on CI config change | Low | Low | Test asserts specific command tokens, not entire command; maintainer updates test when intentionally changing CI config |
| `test-recreate: test-clean-db` breaks non-Docker `make` | Low | Low | Makefile is Docker-only by convention (all targets use `docker compose`); `test-clean-db` uses `$(COMPOSE_TEST)` which is Docker-only |

### Appendix C — Recommended Commands

```bash
# --- Verify D-01 (no e2e references in plan doc) ---
grep -c "e2e" .ai/plans/done/25_test-optimization-plan_done.md

# --- Verify D-04 (no loadscope in plan doc) ---
grep -c "loadscope" .ai/plans/done/25_test-optimization-plan_done.md

# --- Verify D-02 (no "all 934 tests" in §1.4) ---
grep "all 934 tests" .ai/plans/done/25_test-optimization-plan_done.md

# --- Verify live CI (already correct, not changed by this plan) ---
grep -n "loadgroup" .github/workflows/ci.yml          # → line 91
grep -n "not seed"  .github/workflows/ci.yml          # → line 91
grep -n "reuse-db"  .github/workflows/ci.yml          # → line 91
grep -n '"seed"'    .github/workflows/ci-nightly.yml  # → line 73 (no -n)

# --- Verify §8-rec-4: test-clean-db works ---
make test-clean-db                    # → exit 0, "Stale test databases dropped."
# Confirm no test DBs remain:
docker compose -f docker-compose.yml -f docker-compose.test.yml exec -T db \
  psql -U postgres -d postgres -t -A -c \
  "SELECT datname FROM pg_database WHERE datname LIKE 'test_mko_bazuna%'"
# → (empty output)

# --- Verify §8-rec-4: test-recreate calls cleanup first ---
grep "test-recreate: test-clean-db" Makefile     # → match found

# --- Verify T5: prevention test passes ---
pytest src/backend/tests/test_docs_ci_parity.py -v   # → 17 passed

# --- Verify Makefile.ps1 ---
.\Makefile.ps1 test-clean-db    # → "Stale test databases dropped." + exit 0
.\Makefile.ps1 test-recreate    # → runs cleanup, then pytest
.\Makefile.ps1 help             # → shows test-clean-db line
```

### Appendix D — NO-GO Confirmation (§8-rec-3)

Files that must NOT be modified by this plan:
- `src/backend/config/settings/base.py` (lines 158-174) — `prepare_threshold: None`, "PgBouncer async safety (zone C5)" comments
- `docker-compose.prod.yml` (lines 99-121) — PgBouncer service

Validator verdict: **NO-GO** — PgBouncer IS in `docker-compose.prod.yml` with transaction pool mode (`PGBOUNCER_POOL_MODE=transaction`); 7 spec docs require `prepare_threshold: None`; removing would be a behavioral no-op (Django 5.2 defaults to `None`) but removes a documented safety layer and contradicts architecture specs.

---

## 8. Research Agent Inputs

The following were credited in `active_findings_compiled.md` §9.1 and applied with Validator corrections:

| Researcher | Focus | Key Contribution | Applied Here |
|---|---|---|---|
| **Researcher 1** | `prepare_threshold: None` (§8-rec-3) | Django 5.2 defaults to `None` — removal is behaviorally a no-op; `[BAD]` connection is caused by `BaseDatabaseWrapper.close()` in atomic block, NOT `prepare_threshold` | **NOT applied** — Validator REJECTED §8-rec-3 (PgBouncer in prod; NO-GO). Plan §7 (current state) explicitly excludes this. |
| **Researcher 2** | Stale `gw*` DB cleanup (§8-rec-4) | Per-worker `gw*` DBs ARE created by default (no `django_db_modify_db_settings` override); stale DBs recur under `--reuse-db` + persistent volume; proposed `DO $$` block for cleanup | **Applied with Validator correction:** `DO $$` block fails on PG18 ("DROP DATABASE cannot be executed from a function"). Correct approach: psql `\gexec` meta-command (client-level, autocommit). Empirically validated — dropped 16 stale DBs, exit 0. Implemented in T4. |
| **Researcher 3** | pytest markers + CI doc accuracy (D-01/D-02/D-04) | `xdist_group` is a pytest-xdist built-in (redundant in `markers`); `--strict-markers` recommended; proposed `test_docs_ci_parity.py` for doc-drift prevention; `addopts` has no `--cov` (CI-only); `entrypoint-test.sh:41` is the PYTEST_OPTS default line | **Applied:** T1-T3 implement the doc corrections; T5 implements the prevention test with stdlib-only parsing (tomllib + string-level YAML). |

**Validator corrections applied:**
1. §8-rec-3: PgBouncer found in `docker-compose.prod.yml:99-121` (Auditor grepped only `docker-compose.yml`). NO-GO. Not planned.
2. §8-rec-4: `DO $$` block fails on PG18 → use `\gexec` (psql client-level). T4 uses the validated `\gexec` + `while IFS= read -r` implementation from §8.4.
3. §7.3: Researcher 3 cited `entrypoint-test.sh:56` for PYTEST_OPTS default — actual line is **41** (minor line-number inaccuracy, doesn't affect correctness; plan uses correct line 41).
4. §7.3: `xdist_group` IS registered in `pyproject.toml:171` (not proposed for removal in this plan scope — that would be a separate finding; T2 notes it as a pytest-xdist built-in in the markers table).

---

## 9. Task Checklist (Summary)

| ID | Task | File(s) | Edits | Status |
|---|---|---|---|---|
| T1 | D-02: Rewrite §1.4 CI command | `.ai/plans/done/25_test-optimization-plan_done.md` | 5 replacements (lines 70, 75, 76, 77, 79) | Planning |
| T2 | D-01: Rewrite §1.2 + purge `e2e` | `.ai/plans/done/25_test-optimization-plan_done.md` | §1.2 table + §1.3 addopts + 8 scattered `e2e` replacements | Planning |
| T3 | D-04: Reconcile §14 T-01/T-05/T-10 | `.ai/plans/done/25_test-optimization-plan_done.md` | 3 table-row replacements (lines 693, 697, 702) | Planning |
| T4 | §8-rec-4: `test-clean-db` (Makefile + .ps1) | `Makefile`, `Makefile.ps1` | Makefile: `.PHONY` + COMPOSE_PROJECT_NAME group + help + target + `test-recreate` dep. ps1: help + function + switch entry + `Invoke-TestRecreate` modification | Planning |
| T5 | Prevention: `test_docs_ci_parity.py` | `src/backend/tests/test_docs_ci_parity.py` (NEW) | New file: 17 test functions, stdlib-only | Planning |

**Total: 5 tasks across 3 files modified + 1 file created.**
