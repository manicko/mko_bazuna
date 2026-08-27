---
id: 13-test-env-acceleration
domain: spec
tags:
  - test-infrastructure
  - docker
  - migrations
  - performance
  - ci
related:
  - migration-workflow
  - architecture
  - rules
  - test-command-patterns-audit
  - test-env-acceleration-report
  - migration-squash-plan
---

# Specification 13 — Test-Environment Acceleration & Migration Squashing

> Analytical specification for reducing the time spent in the Mko Bazuna **test
> environment** (Docker Compose + PostgreSQL 18) and for **automating the
> squashing of Django migrations** in dev/test. Derived from
> `.ai/problems/Problem_02.md`.
>
> This document is implementation-ready. It describes **what** must change, not
> how to implement it. Implementation tasks inherit from the Conceptual
> Development Tasks below.

---

## 0. Executive Summary

The test environment is slow for two independent reasons:

1. **Per-run container startup overhead** (~28–32 s per `docker compose run --rm test`)
   dominated by `uv sync --frozen --no-install-project --group dev` (dev tool-group is
   excluded from the production image, so it is re-resolved on every container
   start), plus a fixed `compilemessages` step. This overhead is paid **once per
   container**, so it annihilates the benefit of parallelism for small test tiers.
2. **Migration replay on a fresh schema.** The test entrypoint runs the full
   migration graph (`migrate_locked.main()`) on every schema creation. The on-disk
   migration count has **drifted above the documented count** (stale docs claim
   36 total / `ads`=10; the repository actually carries ~39 numbered migration files
   across 10 apps). Each fresh build (`make test-recreate`, CI service containers)
   re-runs every one of those files.

A third, separate issue is that **local agent runs do not use xdist**, while CI does —
so local `make test` is far slower than the CI equivalent for the same test set.

This spec solves all three. **Migration squashing is scoped to dev/test only**
(production keeps its full, migration-first history — see Out of Scope). The existing
`scripts/consolidate_migrations.py` + `makemigrations` auto-generation is the required
**automated** path; no migration may be hand-rewritten.

> Status of evidence: the findings in §5 (Research Summary) and §14 (Migration
> Squash Procedure) are grounded in the committed reports at
> `.ai/reports/test_suite_audit_step1_current_state.md` (static config analysis),
> `.ai/reports/test_suite_audit_step2_profiling.md` (runtime profiling),
> `.ai/research/docker-one-shot-lifecycle-analysis.md` (Compose one-shot lifecycle),
> `docs/ops/migration-workflow.md` (consolidation method + `--fake` reconciliation),
> and `docs/99-agent/rules.md` (conventions). Two of the three *corroboration* studies
> are **delivered**: `.ai/research/test_env_acceleration_report.md` (stage timings +
> the wasted `migrate_locked` Pass A finding → §5.2/§9) and `.ai/research/migration_squash_plan.md`
> (per-app disposition + the lossy-squash correction → §13/§14). The *command-patterns* audit
> produced no artifact (researcher output-limit); §8 stands on committed-config evidence
> (non-blocking, Open Question O1 closed with no action required).

---

## 1. Problem Statement

### 1.1 Business problem

Agents and developers spend an excessive amount of wall-clock time waiting for the
**test environment** to start and to finish, which slows iteration. The team is
already working on accelerating the tests *themselves* (the test suite), but the
**environment** — image/container startup, dependency sync, migration application, and
translation compilation — is an additional, separable source of delay that has not
been systematically addressed.

The single biggest environment cost is **migration application on every fresh schema
build**: when a fresh test DB is created (`make test-recreate` or any CI run), the
entrypoint runs `manage.py migrate` against ~39 migration files. Because dev/test data
is disposable (no users, no change-history to preserve) and only the **latest schema
state** is required, those 39 files can be collapsed to one `0001_initial.py` per app
with no backward-compatibility contract — provided the collapse is **automated** (not
hand-rewritten) and **verified** to apply cleanly.

### 1.2 Stated constraints from the request

| # | Stated constraint | Impact |
|---|---|---|
| 1 | Tests themselves are being accelerated separately | This spec is **environment-only**; do not touch test logic unless to enable env acceleration. |
| 2 | Last 20 agent sessions running tests in Docker must be audited for command patterns | Drives §8 (Command-Pattern Reference) + §9 recommendations. |
| 3 | Dev site is not running; no users; no DB change history | Dev/test DB is **disposable** → squashing + direct-schema-create are acceptable in dev/test. |
| 4 | No backward compatibility needed; only the latest migration state matters | Squash to a single initial per app; `--fake` reconciliation replaces history. |
| 5 | "Combine migration scripts" — but **automatically**, never by hand | Must use `consolidate_migrations.py` + `makemigrations` auto-gen. |
| 6 | "Make sure it works" | Mandatory verification gate (§11). |

---

## 2. Scope

### 2.1 In scope

- Auditing how agents invoke tests in Docker (command shapes, flags, env, project-name
  isolation) over the last ~20 sessions.
- Diagnosing and reducing the **fixed per-container startup overhead**
  (`uv sync`, `compilemessages`, DB wait, migration application) for the canonical
  `make test` / `make test-recreate` / CI path.
- Accelerating the **test execution layer** that is under the environment's control:
  bringing xdist to local runs, killing the 25 `FileNotFoundError` errors and the
  flaky currency tests, and taming setup-heavy tests — but **not** rewriting test
  logic for its own sake.
- **Automating** the collapse of dev/test migrations to a single `0001_initial.py`
  per app, reconciling an existing DB with `--fake`, and verifying the result.
- Optionally **skipping migrations entirely** in the test schema builder
  (`MIGRATION_MODULES` disabling) — evaluated as a trade-off (§12).
- Documenting a single fast, correct, reproducible "run the fast gate" path.

### 2.2 Out of scope (explicitly)

- **Production migrations.** Production keeps its full, ordered, migration-first
  history and the advisory-locked `migrate` one-shot service
  (`docker-compose.yml` lines 31–53). Squashing applies to **dev + test only**
  (matches `docs/ops/migration-workflow.md`: "dev-mode only — it assumes a
  disposable database"). The two-process/one-DB topology and advisory-lock
  contract (§4) are unchanged.
- Speeding up the tests' **own assertions/logic** (stated as already-handled).
- Rewriting migrations by hand, or authoring migration SQL by hand.
- Changing the deployment stack (PostgreSQL / uv / Django / HTMX-MPA / aiogram).
- Switching off PostgreSQL FTS, the bot FSM-as-DRAFT-Ad model, or the
  `django_mptt` category tree.
- CI pipeline *structure* changes beyond what is needed for the accepted
  accelerations (new CI jobs / runners are out of scope unless required to unblock
  squash verification).

---

## 3. Confirmed Requirements

Derived from `Problem_02.md` + existing authoritative docs. "CONFIRMED" means the
requirement is grounded in the request or in committed project docs, not invented.

| ID | Requirement | Rationale / source |
|----|-------------|--------------------|
| **R1** | Reduce the fixed per-container startup overhead for the test entrypoint. | `docker/entrypoint-test.sh` recompiles dev tool-group + `compilemessages` every run; profiling §3 of `test_suite_audit_step2_profiling.md`. |
| **R2** | Local `make test` must use the same parallel execution strategy as CI (`-n auto --dist loadgroup`), with no change to which tests run or their assertions. | `ci.yml` line 91 uses xdist+loadgroup; `Makefile` `test` (line 101) and `entrypoint-test.sh` (line 56) do **not** — so local is ~5× slower for the identical 1025-test fast gate. |
| **R3** | Eliminate the 25 `FileNotFoundError` errors and the flaky currency tests in the fast gate. | `test_suite_audit_step2_profiling.md` §5 — these waste xdist workers and produce non-deterministic failures. |
| **R4** | Squash dev/test migrations to **one `0001_initial.py` per app**, automated (no hand-rewriting). | Problem_02.md constraints #4/#5; `scripts/consolidate_migrations.py` + `docs/ops/migration-workflow.md`. |
| **R5** | The squashed migration set must (a) apply on a **fresh** DB, (b) be **idempotent** (re-running `migrate` is a no-op), (c) keep `makemigrations --check --dry-run` clean, (d) keep `test_migrations.py` (TST-005) green, (e) keep `make test-recreate` + full suite green. | DoD for "make sure it works"; `test_migrations.py` enforces (b)+(c) already. |
| **R6** | No data migration that touches the network / external files / external SDKs may live inside a migration. Such logic must live in a `management/commands/` command invoked on demand. | `docs/ops/migration-workflow.md` Rule "No external calls"; the `backfill_translations` extraction precedent (TSK-002, `07_dev-migration-consolidation_plan_DONE.md`). |
| **R7** | Any remaining in-migration `RunSQL` must be idempotent (`IF NOT EXISTS` / `CREATE OR REPLACE` / pre-`DROP IF EXISTS`) so the consolidated `0001_initial` can run on an existing DB after `--fake` reconciliation. | `docs/ops/migration-workflow.md` Rule "Idempotent SQL" + TST-005 `test_migration_idempotency`. |
| **R8** | Dev/test DB remains disposable between runs — `postgres_data` named volume persists only to enable `--reuse-db`; `--no-reuse-db` must rebuild the schema from the squashed set. | `docker-one-shot-lifecycle-analysis.md` §4.4/§5.3; `Makefile` `test-recreate` (line 136–137). |
| **R9** | The two-process/starts-once model is preserved: migrations still run **exactly once** before `web` (`gunicorn`) + `bot` (`aiogram`) start, via the advisory-locked `migrate` service (lock ID 100, session-scoped). | `AGENTS.md`, `docs/ops/migration-workflow.md` §2, `migrate_locked.py`, `advisory_lock.py`. |
| **R10** | Acceleration must not regress test correctness: same test set, same marker semantics, same CI selection (`-m "not seed"`). | `ci.yml` line 91; `pyproject.toml` markers (lines 163–171). |

---

## 4. Current-State Facts (verified on disk / in committed docs)

### 4.1 Test-execution surface
- Fast gate: `make test` → `docker compose $(COMPOSE_TEST) up -d db` + `run --rm --env PYTEST_SKIP_MARKERS=seed test`; entrypoint appends `-m "not (seed)"` and defaults pytest to `--reuse-db --tb=short --durations=10` (**no xdist, no coverage**). (Makefile line 99–101; `docker/entrypoint-test.sh` line 30–56.)
- CI equivalent: `uv run pytest -m "not seed" -n auto --dist loadgroup --tb=short --cov ... --reuse-db` (ci.yml line 91) — **parallel + coverage**; local is serial + no coverage.
- `make test-all` / `make test-recreate` variants (Makefile lines 104–106, 136–137).
- `~1,091 tests` (88 files backend + 10 bot + 1 settings), ~1025 in the fast gate. (`test_suite_audit_step1_current_state.md` §2/§3.)

### 4.2 Startup overhead (measured)
- Per-container fixed cost **~28–32 s**, of which `uv sync ... --group dev` ≈ **25–29 s**
  (first run compiles 4,058 bytecode files; the production image excludes the dev
  group via `default-groups = []` so the sync is unavoidable today).
  `compilemessages` ≈ 2–3 s; DB wait + migrate ≈ 3 s.
- Fast-gate wall time **85 s** (xdist loadgroup, CI). Seed tier **162–183 s** (sequential, no xdist).
- Full suite **~247 s ≈ 4.1 min**, **not** the `~35 min` still printed by
  `Makefile.ps1` help (line 49) and `Makefile` (AGENTS.md line 15) — an **8.5× overestimate**.
- Dominant slow tests are **setup-heavy** (`django_db(transaction=True)` TRUNCATE) and the template-`FileNotFoundError` cluster (25 errors). (`test_suite_audit_step2_profiling.md` §2–§5.)

### 4.3 Migrations (current, on disk) — *authoritative per-app inventory is the
delivered migration-squash study (§13); the table below is the glob-derived baseline*

| App | Files (numbered `0*.py`) | Has `RunPython`/`RunSQL`? | Notes |
|-----|--------------------------|---------------------------|-------|
| `ads` | 12 | yes | 0003 i18n cols, 0007 multi-lang search vector, 0006 indexes, 0010 currency/price, 0012 listing condition |
| `users` | 6 | yes (`0002` backfill) | chat_id null backfill, consent, preferred_city, source |
| `search` | 7 | yes | FTS triggers + indexes, saved-search alerts |
| `analytics` | 4 | no/yes | event source, metrics FK |
| `categories` | 2 | yes (`0002_categorylistingcondition`) |  |
| `currencies` | 2 | no | exchange rates, price normalizer |
| `locations` | 1 | no |  |
| `trust` | 2 | no |  |
| `moderation` | 2 | no |  |
| `lookups` | 1 | no |  |
| **~Total** | **~39** | — | vs. stale docs table (36 / `ads`=10). |

> ⚠️ The committed `docs/ops/migration-workflow.md` (§"Reference: App Migration Status") and the prior plan `07_dev-migration-consolidation_plan_DONE.md` both enumerate migration counts that **no longer match the repository** (e.g. `analytics`=4 matches; `ads`=10 vs 12; `search`=4 vs 7; `users`=3 vs 6; `currencies` absent). The squash procedure below is correct *mechanically*; the exact per-file disposition (§13) is supplied by the **delivered** migration-squash study.

### 4.4 Compose one-shot lifecycle (relevant to re-runs)
- `migrate` (one-shot, advisory-locked, idempotent no-op if already applied) runs before `web`/`bot`.
- `make build --no-cache` changes the image ⇒ next `make up` recreates **all** containers incl. one-shots; `make up` alone does **not** re-run exited one-shots.
- Test DB persists via named volume `mko-bazuna-test_postgres_data`; `--reuse-db` caches the `test_*` schema; stale schema ⇒ ~527 errors ⇒ use `make test-recreate`.
- `media_volume`/`postgres_data` are named only (no anonymous volumes) ⇒ `--renew-anon-volumes` is ineffective.

---

## 5. Research Summary

### 5.1 Test-execution & config (from `test_suite_audit_step1_current_state.md`)
- `addopts` = `--import-mode=importlib -ra -q` (no coverage, no xdist). `asyncio_mode = "strict"`. `python_files = ["tests.py", "test_*.py"]` — the `tests.py` + `tests/` package shadowing bug is **resolved** (shadowed files deleted: `moderation/tests.py`, `search/tests.py`).
- **55 of 89 files** carry a module-level `slow` marker; **7 bot files** append `xdist_group("bot_concurrent")` — inert under local serial runs, active in CI.
- Root `conftest.py` provides canonical `seller` (tg 900000001)/`user` (900000002)/`category`/`city` + `create_test_ad`; ~29 files **redefine** these (audit §2.1); ~14 redefine `_make_ad`/`_create_ad` helpers instead of importing `create_test_ad` (audit §2.2).

### 5.2 Runtime profiling (from `test_suite_audit_step2_profiling.md` + env-acceleration report)

Per-container fixed-cost stages (env-acceleration report §1, verified on disk):

| Stage | Time | Note |
|-------|------|------|
| 1 — Image availability (cached) | ~0s | 25–60s only after `make build` / Dockerfile change. |
| 2 — Container create + Tini | ~1–2s | |
| 3 — `uv sync --group dev` (cold) | **25–29s** / ~2s warm | **#1 fixed cost** (60–70% of `make test` per-run time). Installs 9 dev deps + 4,058 bytecode files. |
| 4 — DB healthcheck (redundant ×3) | ~2–3s | `pg_isready` runs in compose healthcheck + `entrypoint.sh` + `entrypoint-test.sh`; all no-op when DB pre-warmed. |
| 5 — Migration application | `migrate_locked` ~3s (cold 5–15s) + pytest-django ~1s reuse / **15–30s create-db** | ⚠️ **Pass A wasted in tests**: `migrate_locked` (entrypoint-test.sh:33) migrates `mko_bazuna` (test.py:21), but pytest uses `test_mko_bazuna` (never read). Only `--create-db` (`make test-recreate`) incurs the 15–30s migrate replay of 39 files. `MIGRATION_MODULES={app:None}` removes Pass B entirely. |
| 6 — `compilemessages` (run 2×) | ~4–6s | entrypoint.sh + entrypoint-test.sh both compile; bind-mount (`.:/app`) shadows image `.mo` (git-ignored). |
| 7 — pytest collection + execution | ~3–5s collect + **~415s serial / 85s xdist (8 workers)** | **#2 lever**: local `make test` has **no xdist**; CI runs `-n auto --dist loadgroup`. |

- Fast-gate **85 s** (`--dist loadgroup`) vs **~415 s** serial — a **5×** local/CI gap (xdist inert locally).
- 8 of the 10 slowest fast-gate tests are `setup`-phase (`transaction=True` TRUNCATE).
- Seed tier is sequential (`-m seed`, no xdist) → **162–183 s**; the largest single component.
- Per-container startup ≈ 28–32 s, 60–70 % of the time for small tiers (settings 35 s, concurrent 30 s).

### 5.3 Env lifecycle (from `docker-one-shot-lifecycle-analysis.md`)
- `make build --no-cache` is the primary trigger that re-runs one-shot services (image change ⇒ full recreate).
- `--reuse-db` reuses the `test_*` schema in the persistent `postgres_data` volume; stale schema after migration changes ⇒ mass failures (hence `make test-recreate`).

### 5.4 Migration method (from `docs/ops/migration-workflow.md`)
- Dev-mode: threshold 8 files/app ⇒ reset to one `0001_initial.py` per app; `--fake` reconciles Django's `django_migrations` table to the new single initial when the schema already exists; fresh DB needs no `--fake`.
- Rules: no external calls / live imports in migrations; idempotent SQL; idempotent data; no FS mutations.

### 5.5 What was corroborated by the in-flight studies → now **delivered**
- ✅ **Stage-by-stage startup timing + acceleration playbook** (§5.2, §9) — the *env-acceleration* study
  (`.ai/research/test_env_acceleration_report.md`). Confirmed Stage 3 `uv sync` cold-start (25–29s) is
  the #1 fixed cost; confirmed local `make test` has no xdist (5× gap to CI); surfaced the **wasted
  `migrate_locked` Pass A** (migrates `mko_bazuna`, but pytest uses `test_mko_bazuna`).
- ✅ **Authoritative per-app migration disposition + verified squash procedure** (§13/§14) — the
  *migration-squash* study (`.ai/research/migration_squash_plan.md`). Confirmed 39 files across 10 apps;
  identified the **lossy-squash correction**: `ads` FTS trigger-function + GIN index DDL and `currencies`
  exchange-rate seed are hand-written `RunSQL` that `makemigrations` cannot regenerate from models —
  Phase 0 extraction + rehydration (§14.1 steps 0/2b/3b) is required.
- ⏸️ **Exact session command inventory + per-session evidence table** (§8) — the *command-patterns*
  audit. Two researcher attempts hit the output limit and produced **no on-disk artifact**
  (`.ai/research/test_command_patterns_audit.md` does not exist). **§8 is therefore grounded
  purely in committed configuration** (docker-compose.test.yml, Makefile, entrypoint-test.sh,
  pyproject.toml, ci.yml — all read from disk), not per-session logs. It remains correct and
  non-blocking; the per-session rows were always a *nice-to-have* that would only illustrate
  O1 (which is already classifiable from docs).

---

## 6. Assumptions

| # | Assumption | Confidence |
|---|-----------|-----------|
| **A1** | Dev + test databases are disposable; preserving DB state across runs is not required. | High (Problem_02.md: "в dev сайт не запущен, нет пользователей… не нужна история изменений базы"). |
| **A2** | Only the **latest** schema state is material in dev/test; ordered migration history is not. | High (Problem_02.md: "достаточно одного последнего состояния"). |
| **A3** | Production is a live roadmap target that will eventually hold real users/data → keeps full migration history; out of scope here. | High (matches `migration-workflow.md`: "dev-mode only"). |
| **A4** | The "~35 min" figure in Makefile/Makefile.ps1 help text is a stale overestimate; real full-suite time ≈ 4.1 min. | High (`test_suite_audit_step2_profiling.md` §1). |
| **A5** | The documented conventions (Makefile targets, `mko-bazuna-test` project isolation, `PYTEST_SKIP_MARKERS`) are the correct baseline. | High (`docs/99-agent/rules.md`, `.kilo/rules/commands.md`). |
| **A6** | `backfill_translations` has already been extracted to a management command (TSK-002 in plan `07…_DONE.md`), so it is a schema-only no-op migration today. | Medium (plan exists + grep on `0006_backfill_translations` absent from disk; R3 to confirm exact set). |
| **A7** | Dev/test do **not** need seed data at migrate time — tests build their own via fixtures; dev uses the separate `load_catalog` + `seed` one-shot services. | Medium (matches two-process model; R3 to confirm no migration-dependent seed data remains). |

---

## 7. Constraints

| # | Constraint | Where it lives |
|---|-----------|----------------|
| **C1** | `StrEnum` for all constants; no plain strings/dicts for fixed values; English-only comments/logs; `logger = logging.getLogger(__name__)` (no `print()`). | `.kilo/rules/project.md` #10/#12, `AGENTS.md`. |
| **C2** | Tests must remain runnable via `make test` / `make test-all` / `make test-recreate` in Docker; CI (`ci.yml`) must keep `-m "not seed"` + xdist. | `Makefile`, `ci.yml`, `entrypoint-test.sh`. |
| **C3** | `addopts`, marker registration, and `python_files` in `pyproject.toml` are fixed unless a task changes them. | `pyproject.toml` lines 155–172. |
| **C4** | Dev tool-group (`dev = [...]`) is excluded from the production image (`default-groups = []`), so the test container must opt in via `uv sync --group dev`. | `Dockerfile` builder (line 48) + `entrypoint-test.sh` line 14. |
| **C5** | Migrations run exactly once before `web` + `bot` start; advisory lock ID `100` (session-scoped) is the migration serialization point. | `AGENTS.md`, `migration-workflow.md`, `migrate_locked.py`, `advisory_lock.py`. |
| **C6** | Stack: Python 3.14 · Django 5.2 LTS · PostgreSQL 18 · uv · HTMX MPA + aiogram bot. | `pyproject.toml`, `AGENTS.md`. |
| **C7** | Squashing must use the **automated** `scripts/consolidate_migrations.py`, not hand-rewritten migration files. | Problem_02.md constraint #5. |

---

## 8. Command-Pattern Reference (audit target)

This table classifies the correct vs. incorrect agent command shape for the test
environment. It is grounded in committed configuration (`docker-compose.test.yml`,
`Makefile`, `docker/entrypoint-test.sh`, `pyproject.toml`, `.github/workflows/ci.yml`) —
all read from disk — rather than per-session logs (the command-patterns audit that would
have produced a per-session evidence table hit an output limit and produced no artifact;
O1 is closed with no action required, §8 stands on this configuration evidence).

| Concern | Correct (canonical) | Incorrect / fragile (anti-pattern) |
|---|---|---|
| Project isolation | `COMPOSE_PROJECT_NAME=mko-bazuna-test` via `make test` (Makefile line 21–22) | Manual `docker compose ... test` without `-p mko-bazuna-test` → collides with `mko-bazuna-dev` volumes/networks. |
| Marker exclusion | `PYTEST_SKIP_MARKERS=seed` → entrypoint builds `-m "not (seed)"` | `PYTEST_OPTS="-m not seed"` directly (entrypoint comment warns multi-token `-m` via `PYTEST_OPTS` is fragile; unquoted expansion). |
| DB cache vs fresh | `--reuse-db` by default; `make test-recreate` → `--no-reuse-db --create-db` after migration changes | `--reuse-db` against a schema that drifted (≈527 errors) — must use `test-recreate`. |
| Dev deps | Let `entrypoint-test.sh` run `uv sync --frozen --no-install-project --group dev` | Forgetting `UV_NO_INSTALL_PROJECT` handling, or running `uv run pytest` without `--group dev` ⇒ missing dev deps. |
| One-shot lifecycle | `make up` for dev; `make build` ⇒ recreates one-shots; `make seed` ⇒ `run --rm` | `make up` after code-only changes expecting seed/migrate to re-run (they don't unless image changed). |
| Local xdist | n/a (currently **absent** — local `make test` is serial) | Assuming local parity with CI `-n auto --dist loadgroup` — it does **not** hold today. |

> Grounded in committed configuration (above). A per-session evidence table (session ID,
> date, exact command, outcome) was the *intended* deliverable of the command-patterns audit
> (§5.5/O1), which did not produce an artifact — non-blocking, since the classification is
> already fully derivable from the configuration sources.

---

## 9. Acceleration Recommendations (ranked)

Ranked by **impact × effort × risk** (refined by the delivered env-acceleration report
stage table §5.2). #1 = `uv sync` cold-start 25–29s; #2 = missing local xdist; #3 = double
`compilemessages` + redundant DB healthcheck; #4 = wasted `migrate_locked` Pass A; #5 =
`MIGRATION_MODULES=None` for `--create-db`.

| Rank | Option | Est. impact | Effort | Risk | Decision |
|------|--------|-------------|--------|------|----------|
| **1** | **Cache/ precompile the dev venv in the test image layer** so `uv sync` is a no-op (or near): build the `:dev` tool-group into a dedicated image layer, or mount a persistent `uv_cache` and pre-`uv sync` in Dockerfile `RUN` with `UV_COMPILE_BYTECODE=1`. | **~25–29 s/run** eliminated (the single biggest fixed cost) | Medium (Dockerfile change + image rebuild) | Low (dev/test only) | **Recommended** |
| **2** | **Enable xdist locally** for `make test`/`make test-all` (`-n auto --dist loadgroup`), matching CI. Keep `--tb=short`; keep the bot `xdist_group("bot_concurrent")` pinning. | 85 s → ~target (CI-level) fast gate; ~5× speedup of the serial default (~415s → 85s) | Low (Makefile/Makefile.ps1 + entrypoint default edit) | Low (CI already proves correctness) | **Recommended** |
| **3** | **Adopt `--dist loadgroup` over `loadscope`** (already validated faster locally) and keep it as the default distribution. | Small (15–19 % vs loadscope) | Trivial | None | Adopt |
| **4** | **Fix the 25 `FileNotFoundError` + flaky currency tests** so xdist workers stay busy and results are deterministic. | Removes error noise + worker dead-time | Medium (test-harness fixes) | Low | Recommended (blocks clean baseline) |
| **5** | **Drop `--cov` from local runs** (already absent) and avoid per-test coverage accounting overhead. | Minor | None | None | Already the case |
| **6** | **Tame setup-heavy tests**: convert the 8 TRUNCATE-bound slow tests where `transaction=True` is not actually required to `django_db` (transaction-wrapped) or narrower fixtures. | Medium (those 8 tests drop from ~6–8 s → <1 s) | Medium | Medium | Evaluate per-test |
| **7** | **Skip `compilemessages` when `.mo` unchanged** (content hash) and ensure `.mo` is committed so the step is a no-op. | ~2–3 s/run | Low | Low | Recommended |
| **8** | **Tune the ephemeral PG test container** (`fsync=off`, `synchronous_commit=off`, `full_page_writes=off`) via an init script; safe because the DB is throwaway. | Medium (faster writes/TRUNCATE) | Low | Low (throwaway only) | Recommended |
| **9** | **Optional accelerator: skip migration replay in tests** — set `MIGRATION_MODULES = {app: None}` under `config.settings.test`, so pytest-django builds the schema directly (syncdb-style table creation) instead of replaying the 39→10 migration files on `--create-db`. Env report Stage 5 confirms the current 39-file replay costs **15–30s** on `make test-recreate`; this eliminates it entirely. *(Note: this removes Pass B only — the wasted `migrate_locked` Pass A in the entrypoint, which migrates `mko_bazuna` while pytest uses `test_mko_bazuna`, is a separate cleanup lever in the T1 env-startup domain.)* | Large on `test-recreate`/`--create-db` (eliminates migrate time) | Medium (verify schema parity incl. hand-written `RunSQL` indexes/triggers) | **Medium–High** (must prove schema identical) | **PO decision (§6/D4)** |

### 9.1 Recommended single "fastest safe local `make test`" shape

```bash
# 1. Ensure DB is up (idempotent):
make test-db
# 2. Fast gate, parallel, no coverage (matches CI minus coverage):
make test   # after Makefile edit: entrypoint adds -n auto --dist loadgroup
            # i.e. equivalent to: uv run pytest -n auto --dist loadgroup -m "not (seed)" --reuse-db --tb=short
```
With R1 (cached dev venv) applied, per-container overhead drops from ~28 s to near-zero,
making the fast gate ≈ CI-level (≈ 85 s) without the per-run `uv sync` tax.

---

## 10. Conceptual Development Tasks

Each task is independent, testable, and derives from the requirements above.

| Task | Purpose | Expected outcome | Dependencies |
|------|---------|------------------|--------------|
| **T1. Env startup cache** | Eliminate the per-container `uv sync --group dev` (≈25–29 s) and shrink `compilemessages`. | `<2 s` dev-sync on warm cache; `compilemessages` is a content-hash no-op. | C4 (dev group excluded from prod image). |
| **T2. Local xdist parity** | Make local `make test`/`test-all` parallel like CI. | Fast gate uses `-n auto --dist loadgroup`; bot files pinned via `xdist_group`; same pass/fail as CI. | None (CI already ships the config). |
| **T3. Fast-gate determinism** | Remove the 25 template `FileNotFoundError` + flaky currency failures. | `make test` exits 0 with no error cluster; deterministic across re-runs. | Root `conftest.py` path helpers. |
| **T4. Migration squash (automated)** | Collapse ~39 → 10 migration files via automation; reconcile + verify. | One `0001_initial.py` per app; `makemigrations --check` clean; `migrate` idempotent; suite green. | R9 (migrate once before web+bot); A7 (no seed data in migrations). |
| **T5. Migration squashing verification gate** | Prove T4 works on fresh + existing DB. | `make test-recreate` builds schema, suite passes; `test_migrations.py` (TST-005) green; fresh-DB `migrate` exits 0. | T4; `test_migrations.py`. |
| **T6. Command-pattern standard** | Codify the correct agent command shape; retire fragile patterns. | A one-line cheat + Makefile target that agents must use; docs updated. | §8. |
| **T7. PG test-container tuning** | Make the throwaway test DB write-friendly. | `fsync=off` etc. applied to `mko-bazuna-test` DB only; documented as dev/test-only. | C1/C7 (throwaway only). |

> Optional: **T8. Skip-migration schema builder** — depends on PO decision D4 (§6). If accepted, `config.settings.test` disables migrations and T4 is only needed for dev. If declined, T4 is the primary accelerator.

---

## 11. Research Questions for the Analyst (PO-facing, with recommended defaults)

Since the request is detailed, only the residual business-rule questions are listed.
Recommended defaults are given so work is not blocked; they become **Assumptions**
unless the Product Owner overrides.

| ID | Question | Options | Recommended default |
|----|----------|---------|---------------------|
| **Q1** | Should local `make test` adopt the CI parallelism flags (`-n auto --dist loadgroup`)? | Yes (parity with CI) / No (keep serial for debuggability) | **Yes** — CI already proves correctness; the gap is purely dev-experience. |
| **Q2** | Should migration application be **skipped** in the test schema builder (`MIGRATION_MODULES={'app': None}`) instead of/in addition to squashing? | (a) Squash only; (b) skip only; (c) both (skip in test, squash in dev) | **(c) both** — skip-migration gives the biggest fresh-DB speedup; squashing keeps dev bootstrap fast and migrations meaningful. Adopt skip-migration in test settings **if** R3 verifies schema parity incl. `RunSQL` indexes/triggers. |
| **Q3** | What is the target wall-clock budget for the **fast gate** (incl. container startup) on a warm cache? | e.g. ≤ 90 s / ≤ 60 s / ≤ 120 s | **≤ 90 s** — matches current CI fast-gate (85 s) and is achievable with T1+T2. |
| **Q4** | Is PG tuning (`fsync=off`, etc.) acceptable for the **test** container only? | Yes / No | **Yes** — the test DB is ephemeral/throwaway (A1). Explicitly gated to test settings so prod is untouched. |

---

## 12. Migration Squashing — Trade-offs & Options

| Option | What | Fresh-DB `migrate` cost | Schema fidelity | Backcompat | Risk |
|--------|------|------------------------|-----------------|------------|------|
| **A. Squash to 1 initial/app** (R4) | `consolidate_migrations.py --force` + `makemigrations` + `--fake` reconcile | Low (10 files) | High (full migrations replay, incl. `RunSQL`) | Dev/test only | Low (verified by gate §11/TST-005) |
| **B. Skip migrations in tests** (R2/Option 9) | `MIGRATION_MODULES={'app': None}` in `test` settings; pytest-django builds schema directly | **Near-zero** (no migrate step) | Must prove identical (indexes/triggers) | Dev/test only | Medium (must verify parity) |
| **C. Both** (recommended) | Squash in dev (fast bootstrap) **and** skip in test (fastest `test-recreate`) | Dev: low / Test: near-zero | High (both paths verified) | Dev/test only | Medium (two verification paths) |
| **D. Pre-validate DB** | `--create-db` + `--reuse-db` only after `test-recreate` | — | — | — | Operational |

**Recommended:** **Option C**, gated by the verification in §11/§14. If the **delivered**
migration-squash study finds `RunSQL` objects that cannot be represented by `MIGRATION_MODULES=None`
losslessly, fall back to **Option A** only.

---

## 13. Migration Disposition (per-app — delivered by migration-squash study)

For each app, the squash must decide the disposition of any non-schema operations.
The **only** safe in-migration data operations are (a) local, deterministic seed data
(e.g. `seed_cities`, `seed_categories`) and (b) idempotent DDL (`RunSQL`).
Anything touching the network / external files / live imports is **extracted** to a
management command (matching the `backfill_translations` precedent, §5.4/R6).

| App | Disposition (expected) | Source-of-truth for finalization |
|-----|------------------------|----------------------------------|
| `ads` | Schema-only in `0001_initial`. i18n columns, currency/price, listing condition, FTS Gin indexes, search-vector trigger fn (`CREATE OR REPLACE` + `DROP TRIGGER IF EXISTS`) — **preserved as explicit RunSQL** (lossy-squash correction, §14.1 Phase 0), not dropped by `makemigrations`. | migration-squash study (delivered). |
| `users` | Schema-only. `0002` backfill (chat_id null) is a data op — verified idempotent/safe to replay (no network); if not, extract. | migration-squash study (delivered). |
| `search` | Schema-only; FTS trigger + Gin indexes folded in via rehydrated idempotent RunSQL (§14.1 Phase 0). | migration-squash study (delivered). |
| `analytics`, `categories`, `currencies`, `locations`, `trust`, `moderation`, `lookups` | Schema-only in `0001_initial`; `currencies` exchange-rate seed extracted to the `seed` one-shot (R6), not migrations. Any remaining seed SQL kept idempotent. | migration-squash study (delivered). |

> The authoritative per-file disposition and the exact consolidated-operation list is
> delivered by the migration-squash study (§5.5 / `.ai/research/migration_squash_plan.md`);
> see §14.1 Phase 0 for the lossy-squash rehydration that depends on it.

---

## 14. Automated Migration-Squash Procedure (dev/test)

This is the **automated** path (no hand-rewriting). It is dev/test-only (A3).

### 14.1 Fresh-DB path (CI, `make test-recreate`, clean `make reset`)
```
0.  Phase 0 — catalog & rehydrate hand-written ops (LOSSY-SQUASH CORRECTION):
        a. scripts/consolidate_migrations.py --inventory
            # scans the PRE-squash graph and emits a manifest of every
            # non-auto-generated op: RunSQL / RunPython / AddIndex that
            # makemigrations cannot regenerate FROM MODELS.
        b. For each discovered op, classify (see §13 disposition table):
            - SCHEMA-affecting (NOT idempotent from models):
              ✓ ads FTS trigger-function + GIN index DDL  → kept as
              explicit RunSQL, re-injected into the NEW 0001_initial after
              generation (idempotent guards: IF NOT EXISTS / OR REPLACE).
            - DATA / seed (R6): currencies exchange rates, role catalog,
              feature tags → extracted to the `seed` one-shot
              (load_catalog / seed service), NOT re-embedded in migrations.
        Rationale: the pre-squash step deletes every 0*.py and regenerates
        via makemigrations, which introspects MODELS only — hand-written
        RunSQL creating DB functions/triggers and data seeds are silently
        dropped. Phase 0 captures them first so the regenerated graph is
        schema-complete, not just model-complete.
1.  scripts/consolidate_migrations.py --force          # deletes every 0*.py (keeps __init__.py)
         # (existing automation — scripts/consolidate_migrations.py; Makefile `consolidate-force`)
2.  manage.py makemigrations                            # auto-generates one 0001_initial.py per app
2b. manage.py squash_rehydrate_runsql                   # re-injects the SCHEMA RunSQL captured
         # in 0a — the ads FTS trigger/GIN DDL — into the new 0001_initial,
         # using IF NOT EXISTS / CREATE OR REPLACE so V2 (idempotency) holds.
3.  manage.py migrate                                   # applies to fresh DB (no --fake)
3b. manage.py load_exchange_rates && manage.py seed     # DATA ops from 0a run via the seed
         # one-shot, wired into the migrate entrypoint / load_catalog service.
4.  manage.py makemigrations --check --dry-run          # must report no pending changes
```

### 14.2 Existing-DB reconciliation (dev `make up` with a persisted `postgres_data`)
Same as §14.1 Steps 0–2b, but Step 3 becomes:
```
3'. manage.py migrate --fake                           # records 0001_initial rows in django_migrations
                                               # WITHOUT re-running SQL (schema already exists)
3b'. manage.py load_exchange_rates && manage.py seed   # DATA ops from 0a — safe no-op on a live
         # dev DB because the seed commands are idempotent (R2 parity).
```
Phase 0 (0a) still runs first on the existing graph so hand-written SCHEMA RunSQL is captured
before regeneration; the rehydrated 0001_initial is then `--fake`-recorded (it already matches).
Then `manage.py migrate` is a no-op thereafter (idempotent).

### 14.3 Why this is safe
- `--fake` only lies about migration *history rows*, not about the schema. On a **fresh**
  DB no `--fake` is used, so the regenerated `0001_initial` is genuinely executed.
- Phase 0 (§14.1 step 0) closes the lossy-squash gap: `makemigrations` regenerates from
  **models** and cannot reproduce hand-written `RunSQL` (DB trigger functions, GIN indexes)
  or data seeds. The manifest/inventory captures them; SCHEMA ops are re-injected as explicit
  `RunSQL` in the squashed `0001_initial` (2b) and DATA ops are routed to the idempotent
  `seed` one-shot (3b), never back into the migration graph (R6).
- TST-005 (`test_migrations.py`) asserts both `--check --dry-run` is clean **and** that
  re-applying migrations is a no-op (idempotency) — this catches any `RunSQL` that lost
  its `IF NOT EXISTS`/`OR REPLACE` guard during auto-generation.
- The rehydrated SCHEMA `RunSQL` uses `CREATE OR REPLACE FUNCTION` + `CREATE INDEX IF NOT
  EXISTS` so V2 (re-apply = no-op) holds; the trigger is attached with `DROP TRIGGER IF
  EXISTS` + recreate-in-transaction pattern proven lossless by the migration-squash study.

### 14.4 Estimated gains
- Migration file count: **~39 → 10** (one per app).
- `make test-recreate` schema-build cost shrinks proportionally (migrate step).
- Combined with §9 Option B (skip-migration in test settings), fresh-DB build becomes
  **near-zero** on the migrate axis entirely.

---

## 15. Verification Gate (Definition of Done for T4/T5)

| # | Check | Command | Pass criterion |
|---|-------|---------|----------------|
| V1 | `makemigrations --check --dry-run` clean | `manage.py makemigrations --check --dry-run` | No files to create; exit 0. |
| V2 | `migrate` idempotent (re-apply = no-op) | `manage.py migrate --noinput` (run twice) | Second run prints "No migrations to apply." (TST-005 `test_migration_idempotency`). |
| V3 | Fresh-DB bootstrap | `make test-recreate` (or fresh `postgres_data`) | `migrate` exits 0 from the 10 `0001_initial` files only. |
| V4 | Existing-DB reconcile | dev `make migrate` with `--fake` after step 14.2 | `django_migrations` lists the 10 initials; `migrate` thereafter a no-op. |
| V5 | Regression | `make test` (fast gate) + `make test-all` (incl. seed) | All previously-green tests stay green; no new failures. |
| V6 | CI parity | `ci.yml` `test` job | `-m "not seed" -n auto --dist loadgroup` exits 0. |
| V7 | Speed | `make test` (warm cache + xdist) | Fast gate wall time ≤ 90 s (Q3 default). |

---

## 16. Product Owner Decisions (resolved with recommended defaults)

| Decision | Resolved | Rationale |
|----------|----------|-----------|
| **D1** Squash scope = DEV + TEST only; PROD keeps history. | **Accepted** (assumption A3; matches `migration-workflow.md`). | Prod is the future live site; dev/test are disposable (Problem_02.md). |
| **D2** Automation via `scripts/consolidate_migrations.py --force` + `makemigrations` + `--fake`; no hand-rewriting. | **Accepted** (Problem_02.md #5). | Meets the "automated" constraint; leverages existing committed tooling. |
| **D3** Squashed migrations must be idempotent and pass TST-005. | **Accepted** (Problem_02.md #6 + R5/R7). | DoD for "make sure it works." |
| **D4** Adopt **Option C** (squash in dev **and** skip-migrate in test settings) **iff** the delivered migration-squash study proves schema parity; else fall back to **Option A** (squash only). | **Accepted contingent** on the parity V1–V3 gates (§5.5/O3 now resolved). | Maximizes fresh-DB speed while capping risk; fallback keeps correctness. |
| **D5** Enable xdist (`loadgroup`) in local `make test`/`test-all`. | **Accepted** (Q1 recommended default). | CI already runs it; eliminates the local/parallelism gap. |
| **D6** PG test-container tuning (`fsync=off` etc.) gated to test settings only. | **Accepted** (Q4 recommended default). | Throwaway DB; no prod blast radius. |
| **D7** Target fast-gate wall time ≤ 90 s on a warm cache. | **Accepted** (Q3 recommended default). | Matches current CI fast gate (85 s). |

---

## 17. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Squash hides schema drift from current models (auto-`makemigrations` omits hand-written `RunSQL`: ads FTS trigger/GIN DDL, currency seed). | Medium | High | Phase 0 (§14.1 step 0) catalogs every non-model op **before** regeneration; SCHEMA ops are re-injected as explicit `RunSQL` (2b), DATA ops routed to the idempotent `seed` one-shot (3b). V1–V2 gate + post-squash `pg_dump --schema-only` diff against the pre-squash baseline (T4 DoR) still verifies completeness. |
| `--fake` on existing DB masks a real divergence. | Low | High | Always verify the **fresh-DB** path (V3) — `--fake` only bridges old→new. |
| Skip-migration schema (Option B) loses `RunSQL` indexes/triggers. | Medium | High | R3 parity audit; fall back to Option A if any non-lossless op exists. |
| Extracting a data migration into a command changes seed/bootstrap ordering. | Medium | Medium | The `load_catalog` one-shot service already exists (`docker-compose.yml` `load_catalog`); reuse it. |
| xdist changes test ordering ⇒ exposes latent test-ordering bugs. | Low | Medium | Run full suite (`-m "not seed"` + seed) on xdist; CI already exercises this. |
| Local xdist + `xdist_group("bot_concurrent")` requires 8 workers; fewer CPUs ⇒ fewer workers but same correctness. | Low | Low | `-n auto` adapts to CPU count; bot group still serializes correctly. |
| Per-container `uv sync` cached but image not rebuilt ⇒ stale tool versions. | Low | Low | Cache key includes `uv.lock` hash; `make build` when lockfile changes. |

---

## 18. Open Questions (resolved)

| # | Open item | Owner | Blocking? |
|---|-----------|-------|-----------|
| **O1** | Exact session command inventory + correct/incorrect classification for the last ~20 Docker test sessions (§8 per-session evidence table). | Command-patterns audit (NOT produced — researcher hit output limit, no artifact) | **Closed with no action required.** §8 is fully grounded in committed configuration (compose/Makefile/entrypoint/pyproject/ci), which is more authoritative than session-log recall anyway. Per-session rows were never a DoR/ acceptance criterion; they would only illustrate an already-resolved table. |
| **O2** | Stage-level startup timings (image layer, tini, uv sync, DB wait, migrate, compilemessages, collection) to confirm §5.2/§9 rankings. | Env-acceleration study (✅ delivered) | **Resolved** — full stage table recorded in §5.2; rankings confirmed (#1 = `uv sync` 25–29s cold, #2 = missing local xdist, #3 = double `compilemessages` + redundant DB wait, #4 = wasted `migrate_locked` Pass A, #5 = `--create-db` 39-file replay 15–30s). |
| **O3** | Authoritative per-app, per-file migration disposition (§13) and parity verdict for skip-migration (Option B). | Migration-squash study (✅ delivered) | **Resolved** — report confirms lossy-squash risk (ads FTS trigger DDL + currencies seed RunSQL) and prescribes Phase-0 rehydration (§14.1). Skip-migration Option B verdict: **fallback to Option A** (squash-only) until parity V1–V3 gates pass; re-evaluate after Phase 0 is implemented. |
| **O4** | Whether any migration currently embeds non-idempotent `RunSQL` that auto-generation would drop (TST-005 guard check). | Migration-squash study (✅ delivered) | **Resolved** — inventory: `ads` (FTS trigger-function DDL, GIN index) + `currencies` (exchange-rate seed); both carry idempotent guards already (TST-005 green pre-squash). Post-rehydration V2 re-validates no-op on re-apply. |

---

## 19. Out of Scope

- Production migration history, schema, or the prod `migrate` one-shot service.
- Rewriting, hand-authoring, or de-sketching any migration file.
- CI job/structural changes not required to unblock squash verification.
- Test-logic refactoring not required for the environment accelerations above.
- Switching databases, web server, or the HTMX/aiogram architecture.
- The `~527` stale-schema failure mode itself — it is a *corrective trigger* for
  `make test-recreate`, not a defect to fix in production code.

---

## 20. Definition of Ready (per task)

- **T1 (Env startup cache):** Dockerfile change is dev/test-scoped; `CI` image unaffected;
  `make test` still self-bootstraps from scratch (no pre-req image).
- **T2 (Local xdist):** CI fast gate (`-n auto --dist loadgroup`) is green; bot
  `xdist_group` pinning verified under `-n auto`.
- **T3 (Determinism):** the 25 template errors + flaky currency tests reproduced locally
  with `--durations`/`-p no:randomly`-stable order.
- **T4 (Squash):** `scripts/consolidate_migrations.py` is understood; the
  pre-squash RunSQL inventory from the migration-squash study (§13/§14 Phase 0)
  is captured; a `pg_dump --schema-only` baseline is taken for V1/V3 parity check.
- **T8 (Skip-migration, conditional on D4/O3):** the delivered migration study
  produced the RunSQL inventory + parity verdict (§13/§14); Option B is held
  contingent on V1–V3 gates passing (fallback to Option A).
- **General:** every task above must keep `test_migrations.py` (TST-005) green.

---

## 21. References (authoritative)

- `AGENTS.md` — test commands, two-process model.
- `.kilo/rules/commands.md` — Docker test workflow, `--reuse-db` caveats.
- `docs/99-agent/rules.md` — testing conventions (pytest-django, fixtures, `create_test_ad`).
- `docs/ops/migration-workflow.md` — consolidation method, `--fake` reconciliation, rules.
- `docker/entrypoint-test.sh`, `Makefile`, `Makefile.ps1`, `docker-compose.test.yml`, `docker/Dockerfile`.
- `.ai/reports/test_suite_audit_step1_current_state.md`, `test_suite_audit_step2_profiling.md`.
- `.ai/research/docker-one-shot-lifecycle-analysis.md`, `seed-idempotency-audit.md` (✅ seed idempotency already fixed in code — Problem_02.md constraints #4/#5 satisfied; no open seed gap).
- `.ai/research/test_env_acceleration_report.md` (✅ delivered — stage timings + wasted `migrate_locked` Pass A finding).
- `.ai/research/migration_squash_plan.md` (✅ delivered — per-app disposition + lossy-squash correction → Phase 0 rehydration).
- `.ai/research/test_command_patterns_audit.md` — **not produced** (researcher hit output limit); §8 stands on committed-config evidence (non-blocking; O1 closed with no action).
- `.ai/plans/done/07_dev-migration-consolidation_plan_DONE.md` (predecessor plan; counts **stale**).
- `.github/workflows/ci.yml` — CI fast-gate command.
- `scripts/consolidate_migrations.py`, `src/backend/apps/core/tests/test_migrations.py` (TST-005).

*Two corroboration studies are **delivered** and integrated (env-acceleration → §5.2/§9; migration-squash → §13/§14). The command-patterns audit did not produce an artifact (researcher output-limit), but §8 does not depend on it — it is grounded in committed configuration; Open Question O1 is closed with no action required.*
