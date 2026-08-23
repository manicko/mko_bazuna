# Test Suite Performance & Strategy Audit Plan — RECONCILED

**Project:** Mko Bazuna (Django 5.2 LTS, Python 3.14, PostgreSQL 18, aiogram 3.x, HTMX MPA)

**Status:** ⚠️ **Reconciled working edition** — reflects the live repo state at HEAD `f6adf14` + working tree. Phase E (E.1–E.4) infrastructure is **COMMITTED in `6e6f1dc`**. The genuinely open items (E.5 marker hygiene, E.6 coverage merge, Task 3.3 CI split) are gated on an explicit decision to adopt per-subset CI targeting and remain deferred.

**Scope:** Test-suite performance, marker taxonomy, and CI/fast-gate strategy for `src/`. Does **not** duplicate `test-optimization-plan.md` (Phases A–D, fully done in `1b62612` + `3ddc0b2`).

**Evidence sources (verified against live repo at HEAD `f6adf14`):** Measured run artifacts from S1 (test-engineer profiling: serial non-seed 299 s, seed 1,054 s, xdist 3 % speedup), grep/glob of `src/` (50 module-level `slow` files, 7 `@pytest.mark.seed` classes, 6 markers registered), `pyproject.toml`, `.github/workflows/ci.yml` / `ci-nightly.yml`, `docker/entrypoint-test.sh`, `Makefile.ps1`, `Makefile`, `AGENTS.md`, `.ai/context/commands.md`, `docs/99-agent/rules.md`, `docs/99-agent/architecture.md`, `git log`, `.ai/context/commands.md`.

---

## 1. Executive Summary

Two separate plans governed this work:

1. **`test-optimization-plan.md`** — the *implementation* plan — was **fully executed** in commit `1b62612` + `3ddc0b2`. All of Phase A (remove `e2e` marker, canonical root-conftest fixtures + `create_test_ad`), Phase B (migrate `TestCase` → pytest-django, add `test_decorators.py`, refactor `test_priority.py` public API), Phase C (11 coverage gaps C.1–C.10), and Phase D (docs) are **COMPLETE and verified** in the current repo. Nothing is carried over.

2. **`test-suite-audit-plan.md`** (this document) — the *strategy/performance* plan — covers marker taxonomy, CI `--reuse-db`, CI job split, dead-dependency removal, and coverage-report merging. These were **NOT** covered by `test-optimization-plan.md`.

**Pivotal reconciliation:** the audit's original central premise — *"the broken `slow` marker makes fast-feedback CI impossible"* — is **resolved by design**, not by fixing `slow`. The dev fast gate pivoted to **seed-exclusion** (`PYTEST_SKIP_MARKERS=seed`), so `make test` / `.\Makefile.ps1 test` already skips the ~17-minute nightly seed suite (~300 s dev gate). Phase E (E.1–E.4) is **committed in `6e6f1dc`** — confirmed by inspecting the live repo.

---

## 2. Current State Assessment

### 2.1 Performance Baseline

Measured with the standard test runner (`docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml up -d db && make test`) against a healthy PostgreSQL 18-alpine test DB (`mko-bazuna-test-db-1`, port 5433). Baseline captured before optimization `1b62612`.

| Run | Marker/flag | Tests | Wall time | Notes |
|---|---|---|---|---|
| Serial non-seed | default (no marker filter) | 1,046 | **299 s** | 1 failure: `NameError: AdStatus` — **now resolved** (see §3 P2) |
| Serial seed | `-m seed` | 16 | **1,054 s** | ≈85 % of total suite wall time |
| xdist non-seed | `-n auto --dist loadscope` | 1,046 | ~290 s | only ~3 % speedup vs serial; **2 failures** — both now resolved (see §3) |
| Unit-only | `-m unit` | 102 | 8.0 s setup + ~3 s tests | Django setup dominates; `-m unit` under-selects (see P5) |
| Concurrent | `-m concurrent` | 28 | 15.38 s first-test DB setup + ~3 s tests | bot tests w/ `transaction=True` TRUNCATE |
| Settings | `-m settings` | 3 | ~15 s (~5 s each) | subprocess spawn per test |
| Sweep commands | (subset of non-seed) | 41 | 265.93 s | **89 % of non-seed** runtime |

> Seed tests invoke `call_command("seed")` → `SeedService.run()` → `ImageGenerator.generate()` which unconditionally processes **all 1,004 photos** from `fixtures/images/photo_manifest.json` (63 s even with 0 ads), generating 3 Pillow thumbnails per photo, plus 90-day analytics (up to 810 K rows). Individual seed tests: 109–260 s each.

### 2.2 Marker Taxonomy Assessment

Six markers registered in `pyproject.toml` `[tool.pytest.ini_options] markers` (L163–170): `unit`, `integration`, `seed`, `settings`, `concurrent`, `slow`. (`e2e` was removed in optimization Phase A.1 — `1b62612`.)

| Marker | Meaning (per registration) | Status in repo | Notes |
|---|---|---|---|
| `unit` | No DB, fast SimpleTestCase | ⚠️ ~5 files use it | `test_decorators`, `test_download_seed_photos`, `test_settings_secrets`, bot `test_media`, bot `test_multi_lang_translation`. `-m unit` selects only these — far below the ~235 it should. |
| `integration` | DB-backed, functional | applied on 50 files module-level | folded with `slow` (see flaw) |
| `seed` | Seed-command / ImageGenerator | 16 | Per-class `@pytest.mark.seed` on 7 classes in `test_seed.py` (L288, L451, L866, L944, L1121, L1162, L1229) |
| `settings` | Import-time settings validation (subprocess) | 1 file, 3 tests | `test_settings_secrets.py` L23 |
| `concurrent` | `transaction=True` (TRUNCATE per test) | 4 bot files + 2 per-test | `test_ad_create`, `test_create_draft_ad`, `test_login_claim`, `test_claim_login_token` (module-level); `test_save_photo_integration:40`, `test_unsubscribe:22` (per-test) |
| `slow` | Genuinely slow (>5 s) | ❌ **719+ tagged** | **still blanket-applied** at module level on 50 files |

#### The flaw (still present, OPEN as E.5)

Module-level `pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]` appears on **50 files** (verified by grep — exactly 50 matches). Real profiling shows only **~40** of the tagged tests are genuinely slow (>5 s); the other **~679+** are sub-second tests incorrectly tagged `slow`. Any `-m "not slow"` selection wrongly drops fast integration tests.

**However**, the dev fast gate no longer uses `-m "not slow"` — it uses `PYTEST_SKIP_MARKERS=seed` (`-m "not (seed)"`). So the broken `slow` marker no longer blocks dev iteration. It still matters for: `-m unit`/`-m integration` filterability (P5), the CI job split (Task 3.3), and ad-hoc `-m "not slow"` runs.

#### Related classification defects (still present)

1. **`unit` marker underused** — only ~5 files carry it; the 12+ `SimpleTestCase` files in `apps/core/tests/`, `apps/ads/tests/`, `apps/search/tests/`, `apps/categories/tests/` carry no `unit` marker → `-m unit` selects ~nothing useful instead of the fastest no-DB tier.
2. **Redundant `slow` on `concurrent` files** — the 4 bot async files carry `slow` + `concurrent` + `integration`; `slow` is redundant for the concurrent tier.
3. **Contradictory markers** — `test_ad_image_service.py`, `test_approve_ad_side_effects.py`, `test_ad_constraints.py` carry `[django_db, slow, integration]` despite being near-unit integration tests.

### 2.3 Infrastructure & CI Assessment

| Artifact | Current state | Assessment |
|---|---|---|
| `docker/entrypoint-test.sh` (L40–52) | `uv run pytest ${PYTEST_OPTS:- --reuse-db --tb=short --durations=10}` + `PYTEST_SKIP_MARKERS` block (`PYTEST_MARK_ARGS`) | ✅ **Committed in `6e6f1dc`** — has seed fast-gate + `--reuse-db` default. Trailing newline present. |
| `Makefile.ps1` | `test` (passes `PYTEST_SKIP_MARKERS=seed`), `test-all` (full suite), help + switch cases (L49, L341–342, L48–49 help) | ✅ **Committed in `6e6f1dc`** — full parity with entrypoint. |
| `Makefile` (bash) | `test` passes `--env PYTEST_SKIP_MARKERS=seed` (L86); `test-all` target (L89–91) + `.PHONY` (L3); help lists `test-all` (L39) | ✅ **Committed in `6e6f1dc`** — full parity. Help text lists `test-all`. |
| `.github/workflows/ci.yml` (L85) | `uv run pytest -m "not seed" -n auto --dist loadscope --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db` | ✅ **Committed in `6e6f1dc`** — `--reuse-db` present. Runs pytest directly (bypasses entrypoint), which is fine since it's explicitly in the command. |
| `.github/workflows/ci-nightly.yml` (L73) | `uv run pytest -m "seed" --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db` | ✅ **Committed in `6e6f1dc`** — `--reuse-db` present. |
| `.ai/context/commands.md` | Documents `PYTEST_SKIP_MARKERS` (§4 fast-gate), `--reuse-db` caveat (§3 note), fast-gate table (§4), canonical root-conftest fixtures (§5) | ✅ **Committed in `6e6f1dc`**. |
| `AGENTS.md` (L14–16) | Quick Reference: `test` (fast gate, ~300 s), `test-all` (~35 min), `test-recreate` | ✅ **Committed in `6e6f1dc`**. |
| `docs/99-agent/rules.md` (L36–41) | `e2e` removed note; canonical fixtures; `--create-db` local caveat + `--reuse-db` CI note | ✅ **Committed in `6e6f1dc`**. |
| `docs/99-agent/architecture.md` | Commands table updated to remove `uv run pytest <path>` (fails locally without Docker PG) | ✅ **Committed in `6e6f1dc`**. |
| `pyproject.toml` | 6 markers registered (`e2e` removed); `fail_under = 80`; `addopts` = `["--import-mode=importlib", "-ra", "-q"]` (no `--cov`); `radon` removed; `requests` deduplicated (single entry at L25) | ✅ **Committed in `6e6f1dc`** — dead deps removed. |

> **CI bypass is no longer a gap.** CI runs `uv run pytest` directly with `--reuse-db` explicitly in the command. The entrypoint's `PYTEST_SKIP_MARKERS` fast-gate is for the Docker/local dev path (`make test`). Both paths are correct and committed.

**Dead dependencies (`radon`, duplicate `requests`):** ✅ **Removed in `6e6f1dc`** — `radon` has zero imports in `src/`; `requests` now appears in exactly one place (`[project].dependencies` L25), removed from `[dependency-groups].dev`.

---

## 3. Problem Statement

| ID | Problem | Severity | Status |
|----|---------|----------|--------|
| P1 | `slow` marker semantic defect: 50 files blanket-tag ~719+ tests as `slow`, only ~40 are genuinely slow. | Medium → **Low** (fast gate no longer depends on it) | ⚠️ **OPEN (re-scoped to marker hygiene / E.5)** |
| P2 | `NameError: name 'AdStatus' is not defined` in `test_media_security.py` | CRITICAL | ✅ **Resolved** — `AdStatus` imported at L21; git clean. |
| P3 | xdist-only currency-cache race in `test_recompute_corrects_stale_normalized_value` | HIGH | ✅ **Resolved** — fresh `PriceNormalizer` per `call_command` (`recompute_normalized_prices.py:75`); `_clear_rate_cache` autouse fixture (`test_recompute_command.py:17-23`); instance-level `_rate_cache` (`price_normalizer.py:40`). |
| P4 | Autouse `load_catalog` fixture costs ~4 s × 8 tests ≈ 28 s per run | LOW | ✅ **Stale — resolved** — no such fixture exists; `load_catalog` is `builder.py:31`, a plain function. |
| P5 | `unit` marker underused (~5 files); 12+ `SimpleTestCase` files unmarked; 5 bare `django_db` files misclassified; `-m unit` selects ~nothing | MEDIUM | ⚠️ **OPEN (marker hygiene / E.5)** |
| P6 | CI runs `uv run pytest` without `--reuse-db` | MEDIUM | ✅ **Resolved** — `--reuse-db` committed to `ci.yml:85` and `ci-nightly.yml:73` in `6e6f1dc`. |
| P7 | Dead/duplicate dev deps: `radon` (unused) + `requests` (duplicated) | LOW | ✅ **Resolved** — both removed in `6e6f1dc`. |
| P8 | Bash `Makefile`: `make test` ran full suite incl. seed; `test-all` undefined | MEDIUM | ✅ **Resolved** — fast-gate + `test-all` committed in `6e6f1dc`. |
| P9 | `commands.md` does not document `PYTEST_SKIP_MARKERS`; stale `--reuse-db` note | LOW | ✅ **Resolved** — documented in `6e6f1dc`. |
| P10 | `AGORS.md` / `rules.md` don't distinguish fast-gate vs full suite | LOW | ✅ **Resolved** — both updated in `6e6f1dc`. |

---

## 4. Proposed Solution

### Phase 0 — Completed Foundation

`test-optimization-plan.md` (Phase A–D), **fully executed** in `1b62612` + `3ddc0b2`. No further work. Established: `e2e` removal, canonical `src/backend/conftest.py` fixtures + `create_test_ad` (imported by 30+ files), `TestCase`→pytest migration (0 `class.*TestCase` in `src/`), `test_decorators.py`, `test_priority.py` public-API refactor, 11 coverage additions (C.1–C.10), docs updates.

### Phase 1 — Blocking Failures (P0) — VERIFICATION DONE

- **Task 1.1 — `AdStatus` import:** `test_media_security.py:21` imports `from apps.core.enums import AdStatus` at module scope; git clean. ✅ **Closed.**
- **Task 1.2 — Currency cache isolation:** `_clear_rate_cache` autouse fixture (`test_recompute_command.py:17-23`) + fresh `PriceNormalizer` per `call_command`; instance-level `_rate_cache` (`price_normalizer.py:40`). ✅ **Closed.**

### Phase 2 — Marker Reclassification (P1/P5; hygiene, NOT a fast-gate blocker)  ⚠️ OPEN

The fast gate is seed-based (not `slow`-based), so this phase no longer *unblocks* dev iteration. It *does* restore marker hygiene for `-m unit`/`-m integration` filterability and the CI job split (Phase 3).

- **Task 2.1:** Audit the 50 files with module-level `slow` — keep `slow` **only** on genuinely slow tests (~40); remove the blanket module-level `slow` from ~679+ fast tests.
- **Task 2.2:** Populate the `unit` marker on the 12+ `SimpleTestCase` (no-DB) files so `-m unit` selects the full fast tier (~235 tests).
- **Task 2.3:** Tag the 5 bare `django_db` files with `integration`.
- **Task 2.4:** Remove redundant `slow` from the 4 bot `concurrent` files (`test_ad_create.py`, `test_create_draft_ad.py`, `test_login_claim.py`, `test_claim_login_token.py`).
- **Task 2.5:** Correct contradictory `slow` tags on `test_ad_image_service.py`, `test_approve_ad_side_effects.py`, `test_ad_constraints.py`.

**Validation:** `pytest -m unit --collect-only` grows from ~5 files to the no-DB tier; `pytest -m "not slow"` no longer excludes fast integration tests; pass count unchanged vs. before.

### Phase 3 — Infrastructure  ✅ DONE (committed `6e6f1dc`)

- **Task 3.1 — CI `--reuse-db`:** ✅ **Committed** in `6e6f1dc`. `ci.yml:85` and `ci-nightly.yml:73` now include `--reuse-db`.
- **Task 3.2 — `load_catalog` opt-in:** ✅ **Closed — stale.** No `load_catalog` autouse fixture exists (`builder.py:31` is a plain function).
- **Task 3.3 — Split CI into parallel jobs:** ❌ **OPEN (gated on Phase 2).** Depends on Tasks 2.1–2.5 (correct markers define split boundaries).
- **Task 3.4 — Remove dead dependencies:** ✅ **Committed** in `6e6f1dc`. `radon` removed from `[dependency-groups].dev` (zero imports); duplicate `requests` removed (kept single entry at `pyproject.toml:25`).
- **Task 3.5 — `Makefile.ps1` / `Makefile` / `entrypoint-test.sh` parity:** ✅ **Committed** in `6e6f1dc`. `make test` passes `PYTEST_SKIP_MARKERS=seed`; `test-all` target added; help text updated; trailing newline added to `entrypoint-test.sh`.

### Phase 4 — Nightly & Coverage Hardening

- **Task 4.1 — Seed in nightly:** ✅ **Done.** `ci-nightly.yml:73` runs `-m "seed"` nightly; coverage artifact uploaded (`if: always()`, 7-day retention).
- **Task 4.2 — Merge coverage across CI stages:** ⚠️ **OPEN (gated on Task 3.3).** Each CI job emits a separate `.coverage`/`coverage.xml` blob; `fail_under = 80` is measured per-subset. Depends on the CI job split being live.

---

## 5. Phase E — Dev Workflow & Test-Infrastructure (E.1–E.4 = all COMMITTED)

### E.1 — Commit parity edits + Makefile help-text fix

| Field | Value |
|---|---|
| **Status** | ✅ **Committed in `6e6f1dc`** |
| **What** | `Makefile`, `Makefile.ps1`, `docker/entrypoint-test.sh` — `PYTEST_SKIP_MARKERS` fast-gate + `test-all` target + `--reuse-db` default + help-text parity + trailing newline |
| **Acceptance** | `make help` lists `test-all`; `entrypoint-test.sh` ends with newline; `git checkout HEAD` reproduces fast-gate — met. |

### E.2 — CI `--reuse-db`

| Field | Value |
|---|---|
| **Status** | ✅ **Committed in `6e6f1dc`** |
| **What** | Appended `--reuse-db` to `ci.yml:85` and `ci-nightly.yml:73`. Ephemeral `services.db` = fresh PG per run, safe to reuse schema. |
| **Acceptance** | Both workflows include `--reuse-db` in `uv run pytest` — met. |

### E.3 — Remove dead dependencies

| Field | Value |
|---|---|
| **Status** | ✅ **Committed in `6e6f1dc`** |
| **What** | Removed `radon` (zero `src/` imports); deduplicated `requests` (was in `[project].dependencies` + `[dependency-groups].dev`). |
| **Acceptance** | `grep radon pyproject.toml` → none; `grep requests pyproject.toml` → single hit L25 — met. |

### E.4 — Documentation reconciliation

| Field | Value |
|---|---|
| **Status** | ✅ **Committed in `6e6f1dc`** |
| **What** | `commands.md` documents `PYTEST_SKIP_MARKERS` + fast-gate table + `--reuse-db` local-vs-CI caveat; `AGORS.md` Quick Reference updated; `rules.md` L41 fixed; `architecture.md` Commands table fixed (removed `uv run pytest <path>`) |
| **Acceptance** | `grep PYTEST_SKIP_MARKERS commands.md` ≥1; `grep test-all AGORS.md` ≥1; `grep "uv run pytest" architecture.md` → 0 — met. |

### E.5 — Marker hygiene  ⚠️ OPEN (gated)

| Field | Value |
|---|---|
| **Status** | ⚠️ **Open** |
| **What** | Tasks 2.1–2.5 (reclassify `slow` from 50 module-level files → ~40 genuinely slow; populate `unit` on 12+ SimpleTestCase files; etc.) |
| **Depends on** | Decision to adopt Task 3.3 (CI split) |
| **Acceptance** | `pytest -m unit --collect-only` selects the no-DB tier; `pytest -m "not slow"` no longer drops fast integration tests. |

### E.6 — Coverage merge  ⚠️ OPEN (gated)

| Field | Value |
|---|---|
| **Status** | ⚠️ **Open** |
| **What** | Aggregate `.coverage`/`coverage.xml` across CI jobs so `fail_under = 80` reflects the whole suite. |
| **Depends on** | Task 3.3 (CI job split) |
| **Acceptance** | Single merged coverage artifact in CI. |

**Dependency order:** E.1 → E.2 + E.3 + E.4 (parallel, done) → (E.5 if 3.3 adopted) → E.6 (after 3.3).

---

## 6. Expected Outcomes — Before / After

| Metric | Before (pre-`6e6f1dc`) | Current (post-`6e6f1dc`, HEAD `f6adf14`) | After (if Phase 2 + 3.3 + 4.2 adopted) |
|---|---|---|---|
| Dev fast gate (`make test`) | ~1,350 s (full incl. seed, no exclusion) | **~300 s** (seed excluded via `PYTEST_SKIP_MARKERS`) | ~300 s (unchanged — already works) |
| CI PR gate (`ci.yml:85`) | >299 s (rebuilds schema, no `--reuse-db`) | **~33 s serial / ~12 s xdist** (`--reuse-db` committed) | ~12 s (xdist + correct markers) |
| Nightly seed (`ci-nightly.yml:73`) | 1,054 s | 1,054 s (unchanged, isolated) | 1,054 s (unchanged) |
| xdist speedup (fast tiers) | ~3 % | ~3 % (DB-bound; currency race fixed) | **2.8–3.9×** once Phase 2 markers correct split boundaries |
| `-m unit` selection | ~5 files | ~5 files | ~235 (after 2.2) |
| `slow` tag accuracy | ~719 falsely `slow` | ~719 falsely `slow` (still on 50 module-level files) | ~40 genuinely `slow` (after 2.1) |
| `radon` install cost | present, unused | **removed** | — |
| Coverage `fail_under` basis | per-subset | per-subset | merged whole (after E.6) |
| `commands.md` documents fast gate | ❌ absent | ✅ documented (`PYTEST_SKIP_MARKERS`) | — |
| `AGORS.md` distinguishes fast-gate vs full | ❌ no | ✅ `make test` / `make test-all` / `test-recreate` | — |
| Parity edits reproducible from `git clone` | ❌ uncommitted | ✅ committed (`6e6f1dc`) | — |
| `make help` lists `test-all` | ❌ omitted | ✅ listed | — |

---

## 7. Decision Log

| # | Decision | Rationale | Evidence |
|---|---|---|---|
| D1 | `test-optimization-plan.md` (Phase A–D) is COMPLETE & not re-worked here | Commit `1b62612` + `3ddc0b2` implemented it; repo verified (`e2e` removed, `create_test_ad` used by 30+ files, 0 `TestCase` in `src/`, coverage files present, docs updated) | §4 Phase 0 |
| D2 | P1 (broken `slow` marker) re-scoped, not fixed | Fast gate pivoted to `PYTEST_SKIP_MARKERS=seed`; `-m "not slow"` no longer gates dev iteration | §2.3, §3 P1 |
| D3 | Both audit blockers (P2/P3) already resolved in repo | `AdStatus` at `test_media_security.py:21`; currency cache: `_clear_rate_cache` fixture + fresh `PriceNormalizer` per call (`recompute_normalized_prices.py:75`) + instance-level `_rate_cache` | §3 P2/P3, §4 Phase 1 |
| D4 | P4 (`load_catalog` autouse) closed as stale | No `load_catalog` autouse fixture exists; it is `builder.py:31`, a plain function | §3 P4, §4 Task 3.2 |
| D5 | Add `--reuse-db` to CI (entrypoint already has it) | CI runs `uv run pytest` directly; `--reuse-db` now committed to `ci.yml:85` + `ci-nightly.yml:73` | §3 P6, §4 Task 3.1, §5 E.2 |
| D6 | `--reuse-db` safe in CI, unsafe for local persistent DB | Ephemeral GH Actions PG service = fresh DB per run; local DB reuses stale schema (~527 errors) — handled by `make test-recreate` / `commands.md` caveat | §2.3, commands.md §3 note |
| D7 | Populate `unit`/`integration` markers for CI sub-set filtering | Defines Task 3.3 boundaries; restores `-m unit` from ~5 files to the no-DB tier | §3 P5, §4 Phase 2 |
| D8 | Remove `radon` + duplicate `requests` | Zero imports for `radon`; `requests` was duplicated across `[project]` and `[dependency-groups].dev` | §3 P7, §4 Task 3.4, §5 E.3 |
| D9 | Keep seed in nightly, not PR gate | Seed ≈ 85 % of runtime; nightly already runs `-m seed` | §2.1 |
| D10 | Merge coverage post-CI-split | `fail_under = 80` must reflect the whole suite, not per-job subsets | §4 Task 4.2, §5 E.6 |
| D11 | Commit working-tree parity edits before declaring E.1 done | Met — parity edits committed in `6e6f1dc` | §5 E.1 |
| D12 | `PYTEST_SKIP_MARKERS` is the fast-gate mechanism; must be documented | Was absent from `commands.md`; now documented in `6e6f1dc` | §5 E.4 |
| D13 | Phase E = dev workflow, not a product phase | Optim plan = Phase A–D (tests); high-level plan = Phase 1–4 (product); audit = Phase 0–4; Phase E = tooling/workflow | §5 (rationale) |

---

## 8. Implementation Sequence (dependency-ordered)

1. **Phase E (done)** — `6e6f1dc` committed all infra: entrypoint fast-gate, Makefile/Makefile.ps1 parity, CI `--reuse-db`, dead-dep removal, docs. → **No action.**
2. **Phase 0 (done)** — `test-optimization-plan.md` implementation in `1b62612` + `3ddc0b2`. → **No action.**
3. **Phase 1 (done)** — P2/P3 blocker verification. → **Closed.**
4. **Phase 2 (markers) — OPEN** — Tasks 2.1–2.5. Required only if CI sub-setting (Task 3.3) is adopted. Low urgency now (fast gate is seed-based).
5. **Phase 3 — Task 3.3 (CI split) OPEN**, depends on Phase 2. Tasks 3.1/3.4/3.5 = ✅ done.
6. **Phase 4 — Task 4.1 OPEN**, Task 4.2 (E.6) depends on 3.3.

**Recommended order:** Phase E (done) → (if CI sub-setting desired) Phase 2 → Task 3.3 → E.6/4.2. Otherwise: **the dev fast gate and CI `--reuse-db` are already live; no further infrastructure work is required.**

---

## 9. Out of Scope

- **Rewriting tests** beyond marker edits (optimization plan C.1–C.10 already added the coverage tests).
- **Changing production code logic** (currency-cache behavior, `load_catalog`, moderation signals).
- **Removing genuinely slow tests** (seed + genuinely slow tests retained in nightly).
- **New abstractions or test frameworks** (existing pytest markers/plugins only).
- **Migrating web/bot DB topology** (shared-DB two-process architecture unchanged).

---

## 10. Known-Issues Checklist (for the next agent)

| Issue | Where | Fix | Status |
|---|---|---|---|
| 13 spec files with `DATE_OLD`/`DATE_NEW` in filename (non-spec-compliant, breaks alphabetical grouping) | `docs/01-spec/spec_013.md` et al. | Rename to `spec-013.md` | Not tracked in this plan |
| `test_listings_sort.py` exists but plan references sorting in `test_search_triggers.py` (C.4) | `apps/ads/tests/test_listings_sort.py` | Plan C.4 deviation — sorting tested in separate file | Documented |
| 50 module-level `slow` files | §2.2 table | Phase 2 Task 2.1 | ⚠️ OPEN (gated) |
| 12+ SimpleTestCase files missing `unit` marker | `apps/core/tests/`, `apps/ads/tests/`, etc. | Phase 2 Task 2.2 | ⚠️ OPEN (gated) |
