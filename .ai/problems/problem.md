All data is in. Final confirmations complete: 92 structural tests pass (88 + 4 new guards), ruff clean, and the base-of-range ci.yml shows the same `working-directory: src/backend` + bare `pytest -m` shape — classifying the newly-discovered collection gap as pre-existing. Compiling the verdict.

---

# Re-Validation Verdict: **ACCEPT** *(fix commit verified; one separate PRE-EXISTING major discovered and flagged for follow-up)*

`e56321d2` touches exactly 4 files (`ci-nightly.yml` 12/10, `ci.yml` 4/0, `docs/99-agent/rules.md` 3/3, `test_docs_ci_parity.py` 155/0 — pure additions, zero test deletions, no production code). Both MAJOR issues are fixed, independently verified end-to-end.

## Checkpoint confirmations

**1. Issue 1 — FIXED.** `ci.yml:215` carries `if: github.event_name == 'push'` (the 4 added lines are 3 comment lines + the `if:`; nothing else in the file changed). `on:` block unchanged (push/pull_request), `test` job untouched, no other job affected. The job is now genuinely push-only and agrees with its in-file comment and all six doc locations (`rules.md` job/tier tables now even document the `if:` explicitly).

**2. Issue 2 — FIXED, exactly-once invariant empirically proven.** Serial step (line 146) now covers `config/settings/tests apps/core/tests/test_migrations.py`; full tier (line 159) carries both `--ignore=` flags. **No marker exclusion exists anywhere in `ci-nightly.yml`** (grep for `-m` returns zero pytest hits; only the 4 documented invocations: 3 serial + 1 parallel). All pre-existing parity assertions (ci-seed/ci.yml/Makefile/entrypoint/docs-ops) are untouched (155/0 pure addition). Enumeration of what each step selects, measured by three `--collect-only` runs in-container **exactly mirroring the CI cwd/rootdir relation** (cwd=`src/backend`, rootdir=`/app`):

| Invocation | Tests collected | settings | migrations |
|---|---|---|---|
| A: full tier **with** the new ignores | 3442 | **0** | **0** |
| B: full tier without ignores | 3575 | 131 (11 modules) | 2 |
| C: serial step args | 133 | 131 | 2 |

A + C = B exactly (3442 + 133 = 3575), A contains zero of the serial-covered tests. The critical risk — pytest resolving `--ignore` against rootdir so the ignores would silently no-op from `src/backend` — is **disproven empirically**: the ignores work from that cwd. Union with the bot serial step (456 collected via `../telegram_bot/tests`) = 456 + 133 + 3442 = **4031 = the complete collection** (independently measured as 456 bot + 3575 backend from cwd=root). Nothing dropped, nothing double-run — except the parity module itself (see Minor 1).

**3. Guards — real, discriminating, YAML-sound.** `test_full_tier_is_push_only` fails on the pre-fix shape (`job.get("if")` → `None` → `isinstance` check fails) and on mis-guarded variants; the RED-proof test exercises those exact shapes. Both nightly guards fail pre-fix: the serial-coverage test requires *both* paths in one `-p no:xdist` command (pre-fix had only `config/settings/tests`), and the full-tier test requires each `--ignore=` and asserts no `-m "not (` snuck in — plus it pins "exactly one parallel pytest invocation". The `yaml.safe_load` approach is sound: PyYAML's YAML 1.1 parsing of bare `on:` as boolean `True` never touches these guards (they access `jobs.<name>.if` / `steps` only; `if` is not a YAML 1.1 bool keyword), and parsing succeeds — proven by the green run. Not vacuous: the discriminating-power test drives the same predicate against wrong shapes, and `--ignore=...` on the `manage.py compilemessages` step is correctly excluded from "pytest invocation" counting.

**4. Tests + ruff — green.** 92 passed in 36.28s through the Docker test service (88 prior + 4 new guards; the slow-marked SAST test re-measured at 16.14s, again confirming its >5s evidence). `ruff check` clean on `test_docs_ci_parity.py` (including the intentional local `import yaml`).

**5. `docs/99-agent/rules.md` matches the final workflows** — job table documents the `if:`, nightly steps 4–5 quote the landed commands verbatim (`config/settings/tests apps/core/tests/test_migrations.py` serial; `--ignore=...` × 2 in the full tier).

**6. No regressions.** Marker token parity re-verified green; the commit touches no bot test file (29 pins intact), no ads/media test (`test_independent_per_ip` unchanged from round 1), no `pyproject.toml`, no Makefiles. The 13 deletions across the 4 files are comment/doc rewording only.

## Remaining findings

### MAJOR (pre-existing, NOT introduced by the reviewed range) — CI parallel gates never collect the bot tree; report as required follow-up

- **Evidence:** pytest's `testpaths` entries are used as collection args resolved **relative to cwd**, not rootdir — proven empirically: from cwd=`src/backend`, bare `uv run pytest --collect-only` collects **252 backend modules / 3575 tests and ZERO `src/telegram_bot` modules**; from cwd=`/app` it collects 252 + **42 bot modules / 456 tests**. All three CI parallel gates invoke bare pytest with `working-directory: src/backend`: `ci.yml` `test` (lines 185–186), `test-full` (295–296), `ci-nightly.yml` full tier (159). This shape pre-dates the entire range (verified at `3d3c8a55^`: same cwd + bare `pytest -m`). Consequence: the 456 bot tests (~11% of the suite, covering the product's primary surface) run in CI **only** via the nightly *serial* step — they are invisible to every PR/push gate, and before `e01cf78e` had zero CI presence at all. This contradicts `.ai/context/test-command-patterns.md`'s "local xdist parity with CI is achieved; CI already proves correctness" and the docs' tier-mirroring framing; the round-1 measurements (3961/4022 counts, 370.7s) were all local cwd=/root runs that do include the bot. Net: this range moved coverage **forward** (nightly serial added), so I do not hold it against the fix commit — but it is a serious latent hole my round-1 report also missed, and it must be tracked.
- **Minimal fix:** pass explicit path args instead of relying on testpaths — add `../telegram_bot/tests .` to the `test`, `test-full`, and nightly full-tier pytest commands (the serial bot step already proves `../telegram_bot/tests` resolves correctly from that cwd; the `--ignore`s are proven compatible). Optionally extend `test_docs_ci_parity.py` (same D9/D10 precedent) with a guard that each parallel-gate invocation names both trees, and correct the `.ai/context` parity claim.

### Minor 1 — "exactly once" comment slightly overstates inside the fix commit

- **Evidence:** `ci-nightly.yml` new comment: "every test still runs exactly once per nightly run" — but `tests/test_docs_ci_parity.py` (88 tests) is collected both by step 2 (marker-parity, serial) and by the full tier (`src/backend`, not ignored).
- **Why:** trivial duplicated ~15–20s, deliberate routing ("routed first" rationale), but the comment is strictly false.
- **Minimal fix:** soften the comment to "no suite *module* runs twice (the parity guard is deliberately re-routed first)" or add `--ignore=tests/test_docs_ci_parity.py` to the full tier. Either is fine; no coverage impact.

### Minor 2 — advisory doc looseness (pre-existing)

`commands.md`/`rules.md` tier table maps "Nightly ↔ `make test-all`" as mirrors; locally `test-all` runs bot+settings in **parallel and duplicated** (no ignores, cwd=root), while the CI nightly runs those portions serially exactly once. The marker-set mirroring is exact; the execution-mode mirroring is approximate — worth one clarifying sentence when the MAJOR follow-up is done.

---

**Summary:** `e56321d2` correctly and completely resolves both REJECT-driving majors from round 1, with proper structural guards, honest RED proofs, matching docs, and no regressions — **ACCEPT**. The two minors are nano-fixes. The discovered pre-existing CI bot-collection gap is outside this commit's responsibility and should enter the backlog as its own task with the minimal fix above.