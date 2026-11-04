# Test Suite Performance Strategy — mko_bazuna

> **Date:** 2026-10-31 · **Status:** synthesized optimization plan (implementation pending; this document changes no code, tests, or configuration)
> **Sources:** prior structured reports — baseline measurement, bottleneck RCA (with research correction), test taxonomy, validated/rejected optimizations, and tier strategy design. No new findings are introduced; where earlier reports conflict with later research corrections, the correction governs (noted inline).
> **Reading rule:** every timing is tagged **MEASURED** (measured on this host, documented gate recipe) or **ESTIMATE** (projected / derived). Derived-from-measured numbers are tagged **derived**.

---

## 1. Executive summary

- Baseline: **3,813 tests / 284 files**; fast gate runs **581.6s MEASURED** (`-n auto --maxprocesses=4 --dist loadgroup`, skipping only `seed`). Excess time concentrates in: one unmarked rate-limit test (**175.3s single-run / 263.3s under load, MEASURED**), **11 `slow` tests that run locally but not in CI** (marker drift, R3), and settings subprocess spawning (**131 tests / 76.1s MEASURED**).
- Separately, the bot suite is **not parallel-safe** (R1): parallel run = **5 failed / 41 errors in 448s MEASURED**, serial run = clean. This is a correctness blocker that the plan fixes by completing `xdist_group("bot_concurrent")` pinning on 7 uncovered files.
- The plan: unify skip markers via a single env token (T3.1), pin the 7 bot files (T1.1), collapse the per-IP rate-limit test to a pre-seeded counter + **2 real requests** (T2.1), mark >5s tests `slow` (T2.2), and re-tier CI into PR / full pre-merge / nightly gates.
- **Invariant (restated in §5/§6/§8):** no test is deleted merely for being slow, and no integration coverage is replaced by mocks without equivalent coverage. For R2, the per-IP independence assertion stays backed by **real requests (IP-A→429, IP-B→200)**; only the ~239 redundant warm-up requests are replaced by a pre-seeded counter.

| Feedback point | Current | Target |
|---|---|---|
| PR gate (local + CI) | 581.6s **MEASURED** | ≤240s (**ESTIMATE** ~230-250s after steps 1-4) |
| Full pre-merge (excl. seed job) | ≈17min **derived ESTIMATE** (~35min full **MEASURED** − ~18min seed **MEASURED**) | ≤12min (**ESTIMATE**) |
| Nightly (all tests + 2 new checks) | not scheduled today | ≤45min (**ESTIMATE**) |

---

## 2. Bottlenecks and evidence

| ID | Finding | Measured evidence | Confidence | Est. saving |
|---|---|---|---|---|
| **R1** (HIGH, correctness) | Bot suite not parallel-safe under xdist | 29 bot files use `django_db(transaction=True)`; **22 already carry `xdist_group("bot_concurrent")`**; 7 uncovered (listed in §6 step 2). Bot tree serial = clean; parallel = **5 failed / 41 errors in 448s MEASURED**. Root cause per research correction (authoritative): per-worker DBs `_gw0.._gw3` **already exist** — the real cause is leaked `sync_to_async` worker-thread DB backends holding trigger-row locks and colliding with the next test's `TRUNCATE CASCADE`; `_reap_worker_connections` only partially mitigates | High (before/after MEASURED; mechanism corrected and verified — all 7 gap files use `sync_to_async`/`async def`) | Correctness fix, not a time saving. Wall-time delta of full pinning (extra group serialization): small, to **MEASURE** in step 2 |
| **R2** (HIGH cost) | `apps/ads/tests/test_media_security.py::TestMediaGateApplicationRateLimit::test_independent_per_ip` dominates the gate | **175.3s single-run / 263.3s under load MEASURED**; 241 sequential Django test-client requests (= `MEDIA_RATE_LIMIT_REQUESTS + 1`); **UNMARKED `slow`** so it runs in every PR. Sibling same-shape test mock-collapsed = **2.78s MEASURED**. Per-request mechanism (non-loopback `REMOTE_ADDR`, 34-84x gap) **UNVERIFIED** | High (timings MEASURED; mechanism unproven) | **~170s single-run / ~250s+ under load (ESTIMATE, derived from MEASURED endpoints)**; target runtime single-digit seconds |
| **R3** (HIGH parity) | Marker drift between local and CI gates | Local fast gate excludes only `seed`; CI excludes `seed or slow or real_images` → **11 slow tests run locally but not in CI** (count MEASURED) | High | Folds into the ≤240s PR target (**ESTIMATE**): the 11 slow tests leave the local gate |
| **R4** | Settings subprocess overhead | **131 tests / 76.1s MEASURED** across ~55 `django.setup()` subprocess spawns; genuine import-time isolation requirement (cannot trivially go in-process) | High | ~76.1s aggregate moves out of the PR gate behind the `slow` marker (T2.2); wall-clock effect diluted across 4 workers, folds into ≤240s target (**ESTIMATE**). T4.1 would recover ~70s (**ESTIMATE**) but is **DEFERRED** |
| **R5** | Residual `transaction=True` TRUNCATE cost + xdist_group serialization | Inherent to `--dist loadgroup` pinning; not separately timed | Medium | None actionable now; monitored via nightly bot serial drift check |

**Ruled out (MEASURED — not bottlenecks):** test collection ~53s (~1.4%); `--reuse-db` schema restore (sub-second, idempotent); coverage overhead — `--cov` is not in the fast gate at all (only in `ci-seed.yml`).

**Input conflicts resolved (later correction governs):**
1. **R1 root cause:** early RCA framed a shared/missing-worker-DB problem; the research correction is authoritative — worker DBs `_gw0.._gw3` already exist; leaked `sync_to_async` worker-thread backends collide with the next `TRUNCATE CASCADE`. The preferred fix (complete pinning) is unchanged by the correction.
2. **R1 magnitude:** early counts (28 transaction files / 16 pinned / 12 uncovered) corrected to **29 / 22 / 7** (grep-verified).
3. **R2 request count:** early report said 242; corrected count is **241** (= `MEDIA_RATE_LIMIT_REQUESTS + 1`).

---

## 3. Test taxonomy summary

(Full per-test taxonomy matrix lives in the prior taxonomy report — this section is the summary the plan acts on; it is not restated in full.)

- **Layers:** ~60% integration/API, ~40% unit in the core.
- **Critical regression net (~360 integration/API tests)** — must always run in a scheduled tier (placement may shift between tiers; removal may not): ad posting lifecycle (`ads/test_submission.py`, `test_ad_lifecycle.py`, `test_edit.py`, `test_ad_constraints.py`, `bot/test_ad_create*.py`), moderation (`moderation/test_*`), media gate (`ads/test_media_security.py`), auth/login (`users/test_login*.py`, `bot/test_login.py`), search (`search/test_search_api.py`, `test_fts_service.py`), prod settings (`config/settings/tests/*`), i18n (`ads/test_i18n_completeness.py`).
- **Misclassification flags** (labeled `unit` but hit DB/subprocess → treat as integration for tiering, never as trivial): `bot/test_contact_us.py`, `analytics/test_analytics_models.py`, `bot/test_ad_create.py`, all `config/settings/tests`. Label cleanup is optional and behavior-neutral; this plan does not require it.
- **Expensive-but-unmarked (>5s; T2.2 candidates):** `test_independent_per_ip` (175.3s MEASURED — also the T2.1 target), ci_security SAST (12.3s MEASURED), settings subprocess tests (~15s each MEASURED), `env_allowlist_reverse` (10.7s MEASURED), `db_lock_timeout` (10.1s MEASURED).
- **Redundancy:** mostly justified; only the thumbnail null/blank matrices are consolidate-able. **No deletion for slowness.**

---

## 4. Execution strategy

| Tier | Exact invocation | Scope | Target time | Exclusions + rationale |
|---|---|---|---|---|
| **PR gate** — local (every iteration; post step 1) | `.\Makefile.ps1 test` ≡ `$dc run --rm --env "PYTEST_SKIP_MARKERS=seed or slow or real_images" test` → pytest runs `-m "not (seed or slow or real_images)"` + defaults (`--reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup`) | All tests except `seed`/`slow`/`real_images`, **plus dedicated SLO + i18n invocations** (kept from current CI) | **≤240s (ESTIMATE ~230-250s; baseline 581.6s MEASURED)** | `seed`: 37 tests / ~18min MEASURED, infra-focused, job-scoped; `slow`: >5s tests deferred to full CI + nightly — **deferred, never deleted**; `real_images`: heavy image fixtures, deferred to full CI + nightly |
| **PR gate** — CI (PR job in `.github/workflows/ci.yml`) | Same marker expression `-m "not (seed or slow or real_images)"` (byte-identical set; channel per workflow convention) + dedicated SLO invocation: `uv run pytest -k TestSearchResponseSLORegression -n auto --dist loadgroup --tb=short --reuse-db -v` + i18n completeness invocation (`apps/ads/tests/test_i18n_completeness.py`) | Same as local PR gate | Same (~CI wall time not separately measured; gate recipe identical) | Same — R3 resolved by the byte-identical marker set |
| **Full CI** (pre-merge) | `PYTEST_SKIP_MARKERS=seed`, i.e. pytest `-m "not (seed)"` (local equivalent: `$dc run --rm --env "PYTEST_SKIP_MARKERS=seed" test`) — **restores `slow` + `real_images`**. Seed suite stays a **separate parallel job in `ci-seed.yml`** with `--cov` (coverage ≥80 gate unchanged) | Everything except `seed` | **≤12min (ESTIMATE; re-MEASURE after steps 2-4)** | Only `seed` — covered by its own parallel job (runtime there: to be MEASURED) |
| **Nightly / release** | No skip token — all tests incl. `seed` + `real_images` + `slow`, with the **settings/migrations portion serial**; plus two NEW checks: bot serial drift `pytest src/telegram_bot/tests -p no:xdist`, and **marker-parity check** (local fast-gate token and CI PR-gate expression must both equal `seed or slow or real_images`) | All 3,813 tests | **≤45min (ESTIMATE; full suite today ~35min MEASURED incl. seed)** | None |

**Parallelization policy (all tiers):** keep `--maxprocesses=4` (raising it is REJECTED — ENOMEM); keep `--dist loadgroup` for the backend; bot fix validated by before/after **MEASUREMENT** (step 2); `--reuse-db` + persistent test volume retained.

---

## 5. Recommended optimizations + expected impact

| ID | Technique | Bottleneck | Benefit | Risk | Effort | Coverage-equivalence |
|---|---|---|---|---|---|---|
| **T3.1** | Unify local + CI skip markers via the single env token `PYTEST_SKIP_MARKERS="seed or slow or real_images"` (entrypoint already expands it to `-m "not (...)"`; multi-token supported) | R3 | Local gate stops running the 11 CI-excluded slow tests; local/CI parity; prerequisite for a single honest PR-gate measurement | Low — supported single-token form; no code change | XS | Pure scheduling; zero coverage change (tests still run in full CI) |
| **T1.1 (preferred)** | Complete `xdist_group("bot_concurrent")` pinning on the 7 uncovered bot files — smallest diff | R1 | Stable parallel bot suite (today 5F/41E MEASURED); bot cleanup no longer races TRUNCATE CASCADE | Medium — adds group serialization; wall-time delta must be re-MEASURED | S | Execution placement only; no coverage change |
| **T1.2 (fallback only)** | Scope `--dist loadfile` to the bot tree only | R1 | Same correctness outcome if pinning proves insufficient | Medium — coarser; wholesale `loadfile` is REJECTED (would drop the existing 22 pins) | S | Same as T1.1 |
| **T2.1** | Collapse `test_independent_per_ip` to a **pre-seeded counter + exactly 2 real requests** — IP-A expects **429**, IP-B expects **200** (pattern already proven in `apps/core/tests/test_contact_rate_limit.py` and the sibling `test_over_budget_is_refused_before_the_db_lookup`) | R2 | **~170s single-run / ~250s+ under load off the gate (ESTIMATE, derived from MEASURED endpoints; target single-digit seconds vs sibling 2.78s MEASURED)** | Low-Medium — the per-IP dimension must remain asserted by real requests | S | **Equivalent coverage preserved:** the pre-seeded counter replaces only the ~239 warm-up requests; the two discriminating per-IP requests remain real Django test-client requests through the gate. **No mock replaces the assertion.** |
| **T2.2** | Mark >5s tests `slow` (candidates: ci_security SAST 12.3s, settings subprocess suites ~15s each / 76.1s aggregate, `env_allowlist_reverse` 10.7s, `db_lock_timeout` 10.1s — all MEASURED; plus any other >5s from `--durations`) | R4 (and residual gate cost) | Moves 76.1s MEASURED of settings subprocess time plus the other >5s stragglers out of the PR tier; they remain in full CI (`-m "not (seed)"`) and nightly | Low — marker only (project convention: module-level `pytestmark`) | XS | Scheduling only; tests **deferred, not deleted**; rollback trivial (see step 4) |
| **T4.1** (DEFERRED) | In-process settings import instead of ~55 subprocess `django.setup()` spawns | R4 | ~70s potential (**ESTIMATE**) in tiers that keep settings tests | **High — DEFERRED, needs design review** (import-time isolation is genuinely required) | M-L | Deferred; settings tests unchanged until reviewed |
| **T5.1 / T5.2 / T5.4** | Keep as-is: coverage only in the seed job (`ci-seed.yml`); `--reuse-db` + persistent volume; uv/Docker cache (already optimal) | — | Prevents regression from tooling churn | — | — | Coverage ≥80 gate unchanged; fast gate stays cov-free |

**Rejected (do not reconsider):** SQLite · Django `--parallel` · testmon / pytest-picked as a CI gate · `--maxprocesses` above 4 (ENOMEM) · wholesale `--dist loadfile` (drops xdist_group pins) · coverage in the fast gate · `--override-ini=addopts=` (strips `--import-mode=importlib`).

---

## 6. Prioritized implementation steps

> Rollout order fixed by the strategy report: (1) T3.1 → (2) R1 pin + re-measure → (3) R2 collapse → (4) full-CI tier → (5) nightly → (6) deferred. **T2.2 is unslotted in that order**; it is inserted here as its own step (step 4) after the R2 collapse and before the full-CI tier — it only changes PR-tier composition and is independent of the CI tier definitions.

**Step 1 — T3.1: unify skip markers**
- **Action:** set the local fast-gate env token to `PYTEST_SKIP_MARKERS="seed or slow or real_images"` (today `seed`) and make the CI PR-gate use the byte-identical marker set. No code change: `docker/entrypoint-test.sh` already expands the token to `-m "not (${PYTEST_SKIP_MARKERS})"`.
- **Touches:** `Makefile` (`test` target), `Makefile.ps1` (`test` target), `.github/workflows/ci.yml` (PR-gate job), docs to keep current: `.kilo/rules/commands.md` (fast-gate row), `docs/99-agent/rules.md` (markers note), `docs/ops/VERIFY_TESTS_INSTRUCTIONS.md`.
- **Acceptance:** local and CI PR gates deselect exactly `seed | slow | real_images`; the 11 slow tests (and `real_images`) stop running locally; new gate wall time recorded (**MEASURED**, vs 581.6s baseline).
- **Verification:** `.\Makefile.ps1 test`; check pytest deselect counts; confirm the two token definitions are identical.
- **Rollback:** revert the env token at the touched entry points (one-line change each).

**Step 2 — T1.1: pin the 7 bot files + re-measure**
- **Action:** add `@pytest.mark.xdist_group("bot_concurrent")` (module-level `pytestmark`, matching the 22 already pinned) to: `src/telegram_bot/tests/test_contact_us.py`, `test_language.py`, `test_language_middleware.py`, `test_multi_lang_translation.py`, `test_support.py`, `test_support_delivery_telegram.py`, `test_support_delivery_email.py`.
- **Acceptance:** bot tree parallel = clean, 3 consecutive runs, 0 failed / 0 errors; result set matches the serial control run.
- **Verification:** `$dc run --rm -e "PYTEST_OPTS=src/telegram_bot/tests -n auto --maxprocesses=4 --dist loadgroup" test` (×3); serial control `$dc run --rm -e "PYTEST_OPTS=-p no:xdist src/telegram_bot/tests" test`; then full `.\Makefile.ps1 test` — record the wall-time delta vs 581.6s MEASURED baseline.
- **Rollback:** remove the 7 marks (small-diff revert). Fallback: T1.2 (`--dist loadfile` scoped to the bot tree only).

**Step 3 — T2.1: collapse `test_independent_per_ip`**
- **Action:** rewrite `TestMediaGateApplicationRateLimit::test_independent_per_ip` (in `src/backend/apps/ads/tests/test_media_security.py`) to pre-seed the IP-A rate-limit counter (the proven pre-seed/patch pattern from `apps/core/tests/test_contact_rate_limit.py` and the sibling test) and issue **exactly 2 real requests**: IP-A → **429**, IP-B → **200** (per-IP independence preserved).
- **Acceptance:** per-IP dimension still asserted via real requests; runtime single-digit seconds (sibling 2.78s MEASURED); full gate time re-**MEASURED**.
- **Coverage-equivalence:** only the ~239 warm-up requests (241 total → 2) are replaced by the pre-seeded counter; the discriminating requests stay real Django test-client requests through the media gate. No integration coverage is replaced by mocks without equivalent coverage.
- **Verification:** `$dc run --rm -e "PYTEST_OPTS=-k test_independent_per_ip --tb=short" test`; then `.\Makefile.ps1 test`.
- **Rollback:** `git revert` the single test — the 241-request original remains in history (nothing deleted).

**Step 4 — T2.2: mark >5s tests `slow`**
- **Action:** add the `slow` marker to tests currently >5s (per `--durations` report): the ci_security SAST test (12.3s MEASURED), the settings subprocess suites under `src/backend/config/settings/tests/` (~15s each MEASURED; 131 tests / 76.1s aggregate), `test_env_allowlist_reverse.py` (10.7s MEASURED), the `db_lock_timeout` concurrent test (`src/backend/apps/core/tests/test_db_lock_timeout.py`, 10.1s MEASURED), plus any other >5s stragglers. (Do **not** mark `test_independent_per_ip` — resolved in step 3.)
- **Acceptance:** PR gate lands in the ≤240s zone (**MEASURED**; prior estimate ~230-250s confirmed or revised); all newly marked tests still selected by the full tier `-m "not (seed)"`.
- **Verification:** `.\Makefile.ps1 test` (deselects + duration); `$dc run --rm --env "PYTEST_SKIP_MARKERS=seed" test` (still selects them).
- **Rollback:** remove the `slow` marks — tests simply return to the PR gate (marking, not deleting, is what makes rollback trivial).

**Step 5 — full-CI tier**
- **Action:** align CI: PR job keeps the unified marker set (step 1); the full pre-merge job runs `-m "not (seed)"` (restores slow + real_images); the seed suite remains a separate **parallel** job in `ci-seed.yml` with its `--cov` ≥80 gate unchanged.
- **Touches:** `.github/workflows/ci.yml` (job split/token), `ci-seed.yml` (job parallelism only) — no test code.
- **Acceptance:** pre-merge pipeline green; full job ≤12min (**MEASURED**; **ESTIMATE** ~12min prior); seed job green with coverage ≥80.
- **Verification:** CI run observation; local equivalent `$dc run --rm --env "PYTEST_SKIP_MARKERS=seed" test`.
- **Rollback:** restore previous CI job definitions (workflow-only revert).

**Step 6 — nightly / release tier**
- **Action:** add a scheduled nightly run: all tests (no skip token) incl. seed + real_images + slow, settings/migrations portion serial, plus the two NEW checks — bot serial drift (`pytest src/telegram_bot/tests -p no:xdist`; result must match the grouped-parallel result) and **marker-parity check** (local fast-gate token and CI PR-gate expression must both equal `seed or slow or real_images`; fail the job on divergence).
- **Touches:** CI workflow (new scheduled job; small parity-assertion step).
- **Acceptance:** nightly green ≤45min (**MEASURED** on first run; **ESTIMATE** prior); drift + parity checks enforced.
- **Verification:** first nightly run; ad hoc `$dc run --rm -e "PYTEST_OPTS=-p no:xdist src/telegram_bot/tests" test`.
- **Rollback:** unschedule the nightly job (purely additive; no product or test code touched).

**Step 7 — deferred (explicitly out of scope now)**
- **T4.1** in-process settings import: **DEFERRED** — revisit only with a design review (high risk; import-time isolation genuinely required, 131 tests / 76.1s MEASURED, ~55 spawns). Reassess trigger: full-CI job >12min **MEASURED** after step 5.
- **Test sharding:** deferred (not needed at current scale).

---

## 7. Feedback-time targets + open evidence gaps

| Tier / check | Current | Target | Basis |
|---|---|---|---|
| PR gate | 581.6s **MEASURED** | ≤240s | **ESTIMATE** ~230-250s after T2.1 + T2.2 + T3.1 (+ T1.1 delta) |
| Full pre-merge (excl. seed job) | ≈17min **derived ESTIMATE** (full ~35min **MEASURED** − seed ~18min **MEASURED**) | ≤12min | after T2.1; slow + real_images still included |
| Seed job | ~18min, 37 tests **MEASURED** | parallel job, unchanged scope | runtime to **MEASURE** in step 5 |
| Nightly (with serial settings/migrations + 2 checks) | not scheduled today | ≤45min | **ESTIMATE** |
| Bot tree, parallel | 448s, 5F/41E **MEASURED** | clean, matches serial | re-**MEASURE** after step 2 |

**Open evidence gaps (UNVERIFIED):**
1. **R2 mechanism — UNVERIFIED:** the 34-84x per-request gap for non-loopback `REMOTE_ADDR` is unproven (needs instrumentation). **Not blocking:** T2.1 is justified by the MEASURED endpoints (175.3s vs 2.78s sibling) and is coverage-equivalent regardless of the mechanism.
2. **T1.1 wall-time delta — pending:** group serialization cost of pinning 7 files is unknown until step 2 re-measures.
3. **PR-gate composition at ~230-250s — ESTIMATE** until steps 1-4 land; confirm or revise the ≤240s target with data.
4. **Seed-job parallel runtime — not yet measured.**
5. **R5 residual cost (TRUNCATE + group serialization) — not separately timed;** observed indirectly via the nightly drift check.
6. Earlier RCA measurements ran with a **shared-DB harness artifact** (one `AdminShutdown` from container recreation) — deadlocks were independently reproduced between workers; treat only the corrected root cause (§2) as authoritative.

---

## 8. What must not change (coverage preservation)

- The **~360-test critical regression net** (§3) stays in scheduled tiers; tier placement may change, removal may not.
- All `slow` / `real_images` tests are **deferred, never deleted. No test is removed merely for being slow.**
- **No integration coverage is replaced by mocks without equivalent coverage.** R2 citation: `test_independent_per_ip` keeps 2 real requests (IP-A 429 / IP-B 200); the pre-seeded counter replaces only warm-up requests.
- Seed suite + coverage ≥80 gate in `ci-seed.yml` unchanged; coverage never added to the fast gate.
- **SLO gate** (`TestSearchResponseSLORegression`) and **i18n completeness gate** keep explicit PR-tier invocations.
- **Bot serial drift check** (`pytest src/telegram_bot/tests -p no:xdist`) stays in nightly — the serial result is the oracle for the grouped-parallel result.
- **Per-IP assertion** must remain backed by real requests (not mocks) in the collapsed R2 test.
- `--import-mode=importlib` (pyproject) is never stripped — no `--override-ini=addopts=`.
- `--reuse-db` + persistent test volume retained.
- The existing 22 `xdist_group("bot_concurrent")` pins are preserved; no wholesale `--dist loadfile`.
- `--maxprocesses=4` cap (above 4 is REJECTED — ENOMEM).
- Only consolidation permitted anywhere in the suite: the **thumbnail null/blank matrices** — justified redundancy only, never slowness.

---

## 9. Appendix — exact commands reference

### Local (Windows PowerShell)

```powershell
# Copy once — canonical $dc alias (--env-file .env.test is REQUIRED for raw compose)
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'

# Start the DB once per session (persistent volume -> --reuse-db caching)
$dc up -d db

# --- Tier 1: PR gate (post step 1; canonical form) ---
.\Makefile.ps1 test
# raw compose equivalent:
$dc run --rm --env "PYTEST_SKIP_MARKERS=seed or slow or real_images" test
#   entrypoint expands token to: -m "not (seed or slow or real_images)"
#   defaults preserved: --reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup

# --- Tier 2: full pre-merge equivalent (only seed skipped; slow + real_images restored) ---
$dc run --rm --env "PYTEST_SKIP_MARKERS=seed" test

# --- Everything incl. seed (local full suite, ~35 min MEASURED) ---
$dc run --rm test            # = .\Makefile.ps1 test-all

# --- Fresh schema after migration changes ---
$dc run --rm --env "PYTEST_OPTS=--create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup" test
#   = .\Makefile.ps1 test-recreate

# --- Targeted runs (PYTEST_OPTS REPLACES defaults; unquoted value word-splits on spaces:
#     bare paths and single-token -k work; quoted multi-token values like -k "a b" do NOT) ---
$dc run --rm -e "PYTEST_OPTS=-k test_independent_per_ip" test
$dc run --rm -e "PYTEST_OPTS=src/backend/apps/ads/tests/test_media_security.py --tb=short" test

# --- Bot tree: parallel check (post step 2; expect clean; repeat x3) ---
$dc run --rm -e "PYTEST_OPTS=src/telegram_bot/tests -n auto --maxprocesses=4 --dist loadgroup" test

# --- Bot tree: serial control + nightly drift check ---
$dc run --rm -e "PYTEST_OPTS=-p no:xdist src/telegram_bot/tests" test
```

### CI (representative `uv run pytest` forms; exact flag placement follows the existing workflow convention in `.github/workflows/ci.yml`)

```bash
# PR gate (PR job)
uv run pytest -m "not (seed or slow or real_images)" --reuse-db --tb=short -n auto --maxprocesses=4 --dist loadgroup
# dedicated SLO invocation (existing ci.yml form — keep)
uv run pytest -k TestSearchResponseSLORegression -n auto --dist loadgroup --tb=short --reuse-db -v
# i18n completeness invocation (existing dedicated CI i18n gate — keep)
uv run pytest src/backend/apps/ads/tests/test_i18n_completeness.py

# Full pre-merge job (new tier): only seed skipped
uv run pytest -m "not (seed)" --reuse-db --tb=short -n auto --maxprocesses=4 --dist loadgroup

# Seed job: unchanged scope in ci-seed.yml (parallel; --cov >= 80 gate)

# Nightly: no skip token (all tests; settings/migrations serial) + NEW checks:
uv run pytest src/telegram_bot/tests -p no:xdist      # bot serial drift check
# + marker-parity step: local token == CI PR expression == "seed or slow or real_images"
```

### Docker / host caveats (from project command rules)

- Never `uv run pytest` on the host — no DB on `localhost:5432`; run through the Docker `test` service or in CI.
- `--env-file .env.test` is mandatory for raw compose invocations (`${POSTGRES_*?}` interpolation).
- `PYTEST_OPTS` replaces pytest defaults (loses xdist parallelism and DB reuse for targeted runs); value is word-split in `docker/entrypoint-test.sh`.
- Never `--override-ini=addopts=` (strips `--import-mode=importlib`).
- `make` needs WSL on this host — use `.\Makefile.ps1`; `head`/`tail` are unavailable in PowerShell.
