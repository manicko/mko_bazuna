# Execution Plan — Test Suite Performance Strategy

> **Source plan:** `.ai/plans/test-suite-performance-strategy.md` (untracked; treated as read-only input)
> **Phase 0 input:** Auditor `{code_context}` (2026-11-01) — branch `main`.
> **Role:** Tech Lead orchestration. Blocks execute sequentially (max 1 Implementor at a time).
> **Planner phase:** SKIPPED by Product Owner instruction — this file is the decomposition.

## Non-negotiables (carried from the source plan §8 + audit §C)

- No test deleted for being slow. Deferral by marker only.
- No mocks replacing integration coverage without equivalent coverage.
- Never `uv run pytest` on the host; all verification via `.\Makefile.ps1` / `$dc` (Docker).
- Never `--override-ini=addopts=` (strips `--import-mode=importlib`).
- `--maxprocesses` stays 4. `--dist loadgroup` retained. `--reuse-db` retained.
- `Makefile` ↔ `Makefile.ps1` parity for every command change.
- No production-code changes (tests, workflows, Makefiles, docs only).
- `ci-seed.yml`: no `-n auto`, no `--dist`, no `schedule:`/`cron:` (pinned by `src/backend/tests/test_docs_ci_parity.py`).
- `ci.yml` must keep tokens pinned by `test_docs_ci_parity.py` (`-m "not (seed or slow or real_images)"`, `-n auto`, `--maxprocesses=4`, `--dist loadgroup`, `--reuse-db`, `--durations=10`), the step name `Run SAST (bandit)` (pinned by `apps/core/tests/test_ci_security.py`), and TRIVY env (pinned by `tests/test_ci_image_coordinate.py`).
- All structural tests that pin workflow text must be updated in the same commit as the workflow edit.

## Decisions taken (from audit open questions)

| # | Question | Decision | Rationale |
|---|---|---|---|
| D1 | Step 1: does `ci.yml` PR gate need editing? | **No rewrite** — `ci.yml` already uses the byte-identical marker set. Only the two local Makefile tokens + docs change. Add a structural guard (D9). | Audit B.1: ci.yml:185 already conformant. |
| D2 | Step 1: Makefile quoting | `--env "PYTEST_SKIP_MARKERS=seed or slow or real_images"` — quoted (value contains spaces). | Audit risk 1 (silent misrouting). |
| D3 | Step 2: `test_language_middleware.py`, `test_multi_lang_translation.py` pinning depth | Module-level `pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))` in `test_language_middleware.py` (its only class is the transaction one). For `test_multi_lang_translation.py`: class-level `@pytest.mark.xdist_group("bot_concurrent")` on `TestPerUserLocaleActivation` only, so fully-mocked unit classes are NOT serialized into the bot group. | Audit risk 5 — minimal placement change; wall-time is the goal of T1.1, not group inflation. |
| D4 | Step 4: scope of `slow` marking | Only tests **proven** > 5s from a fresh `--durations=10` run on this host, captured as evidence in the task. Settings suites: module-level append **only** for modules whose tests are subprocess-based and > 5s. `test_ci_security.py` → function-level; `test_db_lock_timeout.py` → class-level `TestLockWaitIsBounded`. Never mark `test_independent_per_ip` in this step. | Audit risk 7; audit B.5. |
| D5 | Step 4: `test_env_allowlist_reverse.py` | Managed by the settings-module rule (it is one of the 11 settings modules), not duplicated. | Audit B.5. |
| D6 | Step 5: seed job "parallel" | Interpreted as a **separate CI job** (already true). No `ci-seed.yml` change. Only ci.yml gains a full pre-merge job. | Audit B.9 / risk 3. |
| D7 | Step 6: nightly workflow location | New workflow file `.github/workflows/ci-nightly.yml` (do not touch `ci-seed.yml`; keep `ci.yml`'s pinned tokens untouched). | Audit risk 2 + B.6 (working-directory). |
| D8 | Step 6: nightly paths | Job `working-directory` chosen so `src/telegram_bot/tests` resolves (repo root) or use `../telegram_bot/tests` under `src/backend`. Bot-drift command must run **serially** with `-p no:xdist`. | Audit B.6. |
| D9 | Marker parity check strength | Implement as a **structural test** inside `src/backend/tests/test_docs_ci_parity.py` asserting both `Makefile` and `Makefile.ps1` carry `PYTEST_SKIP_MARKERS=seed or slow or real_images` and that ci.yml carries the same marker set — it runs in every PR and locally (stronger than a nightly-only CI step). The nightly job still runs it explicitly. | Audit risk 9 recommendation (repo precedent: convert doc drift into a gate). |
| D10 | Step 3: pre-seed value | `cache.set(f"media_gate_rl:{IP_A}", MEDIA_RATE_LIMIT_REQUESTS, timeout=MEDIA_RATE_LIMIT_PERIOD)` then exactly 2 real requests: IP-A → 429, IP-B → 200. Import the key pattern / constants from the production module rather than re-hardcoding the string if exported; otherwise use the documented pattern with a comment. | Audit D.8; plan step 3. |

## Execution blocks

Dependency order fixed by source plan §6: 1 → 2 → 3 → 4 → 5 → 6. Each block is one Implementor run + one commit. Blocks 1-4 touch disjoint files from 5-6 → all sequential (single-implementor rule).

### Block 1 — T3.1: unify local skip markers
- **Risk:** low. **Agents:** Implementor only (audit already produced context).
- **Depends on:** —.
- **Scope:** `Makefile` (`test` target + help/comment), `Makefile.ps1` (`Invoke-Test` + help/comment), `docker/entrypoint-test.sh` (comment only), `AGENTS.md` (quick reference row), `.kilo/rules/commands.md`, `docs/99-agent/rules.md`, `docs/ops/VERIFY_TESTS_INSTRUCTIONS.md`, `.ai/context/test-command-patterns.md`.
- **Acceptance:** both Makefiles use the identically-quoted token; entrypoint expands it correctly; test deselect count includes `slow` + `real_images`; new gate wall time MEASURED and recorded.
- **Verification:** `.\Makefile.ps1 test` (record wall time + selected/deselected counts); `docker compose ... run --rm --env "PYTEST_SKIP_MARKERS=seed or slow or real_images" test --collect-only`-equivalent count check.

### Block 2 — T1.1: pin the 7 bot files
- **Risk:** medium (parallel-safety fix; correctness). **Agents:** Implementor only.
- **Depends on:** Block 1.
- **Scope:** `test_contact_us.py`, `test_language.py`, `test_support.py`, `test_support_delivery_telegram.py`, `test_support_delivery_email.py`, `test_language_middleware.py` (module append), `test_multi_lang_translation.py` (class-level on `TestPerUserLocaleActivation`) — all under `src/telegram_bot/tests/`. Per D3.
- **Acceptance:** bot tree parallel ×3 = 0 failed / 0 errors, result set matches the serial control; full `.\Makefile.ps1 test` wall-time delta recorded vs Block 1 measurement.
- **Verification:** `$dc run --rm -e "PYTEST_OPTS=src/telegram_bot/tests -n auto --maxprocesses=4 --dist loadgroup" test` (×3); serial control `$dc run --rm -e "PYTEST_OPTS=-p no:xdist src/telegram_bot/tests" test`.

### Block 3 — T2.1: collapse `test_independent_per_ip`
- **Risk:** low-medium. **Agents:** Implementor only.
- **Depends on:** Block 2 (measurement chain).
- **Scope:** `TestMediaGateApplicationRateLimit::test_independent_per_ip` in `src/backend/apps/ads/tests/test_media_security.py` only. Per D10.
- **Acceptance:** IP-A → 429 (strengthened vs current, which never asserted it), IP-B → 200; runtime single-digit seconds; full gate re-MEASURED.
- **Verification:** `$dc run --rm -e "PYTEST_OPTS=-k test_independent_per_ip --tb=short" test`; then `.\Makefile.ps1 test`.

### Block 4 — T2.2: mark > 5s tests `slow`
- **Risk:** low. **Agents:** Implementor only.
- **Depends on:** Block 3.
- **Scope:** per D4 (evidence-driven). Candidate files from audit §A.4 / E. No production code.
- **Acceptance:** every newly marked test is > 5s in the recorded durations output; PR gate lands in the ≤ 240 s zone (MEASURED) or the deviation is reported; newly marked tests still selected by `-m "not (seed)"`.
- **Verification:** `$dc run --rm --env "PYTEST_SKIP_MARKERS=seed" test` (selected-count check for the newly marked tests); `.\Makefile.ps1 test` (deselect + duration).

### Block 5 — full-CI tier
- **Risk:** medium (structural tests pin workflow text). **Agents:** Implementor only.
- **Depends on:** Block 4.
- **Scope:** `.github/workflows/ci.yml` — add a full pre-merge job running `-m "not (seed)"` (restores `slow` + `real_images`); keep PR job tokens intact; `ci-seed.yml` untouched. Update `src/backend/tests/test_docs_ci_parity.py` docstrings/guards **only if** its assertions require it (tokens remain present).
- **Acceptance:** full job definition present and consistent; all structural tests (`test_docs_ci_parity.py`, `test_ci_security.py`, `test_ci_image_coordinate.py`) green; local equivalent `$dc run --rm --env "PYTEST_SKIP_MARKERS=seed" test` green.
- **Verification:** targeted run of the three structural test modules + local full-tier run (wall time recorded).

### Block 6 — nightly / release tier + parity guard
- **Risk:** medium. **Agents:** Implementor only.
- **Depends on:** Block 5.
- **Scope:** new `.github/workflows/ci-nightly.yml` (schedule + `workflow_dispatch`) running all tests (no skip token), bot serial drift (`-p no:xdist src/telegram_bot/tests` from repo root), and the marker-parity check; plus the structural parity test in `src/backend/tests/test_docs_ci_parity.py` per D9. Do not add `schedule`/`cron` to `ci-seed.yml`.
- **Acceptance:** nightly workflow valid (YAML lint / actionlint if available locally); parity test implemented and green; runs in the PR gate; `test_docs_ci_parity.py` still green.
- **Verification:** run the affected structural tests through the Docker test service; local serial bot drift command also executed once and result recorded.

### Measured results so far (host: Win 11 + Docker Desktop, xdist 4)

| After block | Gate pytest time | Notes |
|---|---|---|
| Baseline (old token, `seed` only) | 581.6s (plan) / 570.3s (Block 1 re-run) — not comparable | 3978 selected |
| 1 (T3.1 token) | 570.3s | 3969 selected, 53 deselected (37 seed + 16 slow/real_images) |
| 2 (T1.1 pins) | 453.5s | bot parallel 456 passed ×3 = serial control; `test_independent_per_ip` still present (~209s) |
| 3 (T2.1 collapse) | 365.9s | the test went 182–209s → 1.6s |
| 4 (T2.2 marks) | 370.7s | 8 more deselected; no further >5s test remains unmarked |

**Open finding (must be reported to the Product Owner): the ≤240s PR-gate target is NOT met by steps 1-4 alone.** Post-step-4 evidence: no individual test >5s remains in the PR tier (largest is 4.96s); the residual ~370s is aggregate mass of ~3961 tests plus per-test `django_db` fixture cost under xdist, not outliers. Further reduction requires structural work (fixture/teardown cost, settings subprocess pattern = deferred T4.1) which is explicitly out of scope for this plan. The plan's §7 item 3 already flags this as "ESTIMATE — confirm or revise with data"; this is that confirmation.

### Block 7 — deferred (out of scope)
- T4.1 (in-process settings import) and test sharding: **not implemented**. Recorded only.

## Documentation (post-implementation)
`Doc-specialist` updates only docs affected by the landed changes, following `docs/00-overview/doc-maintenance-rules.md`, committed separately. Block 1 already touches agent-facing docs; the Doc-specialist run reconciles them with the final state (tiers, nightly, markers) and must not introduce unrelated edits.
## Final validation

`Validator` checks plan completeness, cross-block integration (marker set identical across Makefile / Makefile.ps1 / entrypoint expansion / ci.yml / nightly), architectural consistency (no production code touched), regressions (bot parallel parity, media gate assertion preserved), quality gates (structural tests + fast gate), documentation and unrelated changes.

### Validation outcome

Round 1 → **REJECT** with 2 majors (both genuine defects introduced by Blocks 5/6):
1. `test-full` had no `if:` → the ~7 min full tier ran on every PR, directly regressing the goal. Fixed in `e56321d2` (`if: github.event_name == 'push'`) + structural guard `test_full_tier_is_push_only`.
2. `ci-nightly.yml` ran the settings package twice (serial **and** parallel) and never ran `test_migrations.py` serially. Fixed in `e56321d2` (serial step covers settings + migrations; full tier `--ignore`s both) + guards; exactly-once invariant proven empirically (3442 + 133 + 456 = 4031 = full collection).

Round 2 → **ACCEPT**. Minor 1 ("exactly once" overstated) and Minor 2 (tier-mirroring looseness) closed in `94aab776` (parity module `--ignore`d from the nightly full tier; one-sentence clarification in both tier tables).

### Backlog item (out of scope, not fixed here — pre-existing, pre-dates this range)

**CI parallel gates never collect the bot tree.** All parallel gate invocations run bare `pytest` from `working-directory: src/backend`, so pytest's `testpaths` (`src/backend`, `src/telegram_bot`) is resolved against that cwd: the 42 bot modules / 456 tests are silently not collected by `ci.yml` `test`, `ci.yml` `test-full`, and the nightly full tier. Today the bot suite reaches CI only through the nightly **serial** step.
- Evidence: from cwd=`src/backend`, bare `--collect-only` = 252 modules / 3575 tests (0 bot); from repo root = +42 modules / 456 tests.
- Minimal fix: pass explicit path args (`../telegram_bot/tests .`) in the three parallel invocations; add a `test_docs_ci_parity.py` guard naming both trees; correct the `.ai/context/test-command-patterns.md` "CI already proves correctness" parity claim.
- Why deferred: it is a pre-existing coverage defect unrelated to suite performance, and fixing it changes the PR-gate composition (invalidating this plan's measurements). It needs its own change and its own re-measurement.


## Risks register
1. Wall-time measurement drift between blocks (different host load) — record only in-block deltas.
2. Bot group serialization cost (T1.1) may raise wall time — acceptance is correctness; delta recorded.
3. Nightly workflow cannot be executed on this host against GitHub runners — validate syntax/structurally + local equivalent commands.
4. Structural tests pinning workflow text will fail if tokens/step names are altered — handled in Block 5/6 acceptance.
