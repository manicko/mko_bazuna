---
plan_id: "01-entry-architecture-remediation"
phase: "01"
phase_name: "Entry Points & Process Architecture"
source_report: ".ai/audit/99-validation/01-entry-architecture-validated-findings.md"
source_findings: ".ai/audit/01-entry-architecture/findings.md"
date: "2026-09-28"
planner: "Planner (subagent)"
anchor_commit: "8060fcf"
report_anchor_commit: "9e96b84"
status: "executed"
findings_in_scope: 14
findings_implemented: 10
findings_de_scoped: 2
findings_absorbed: 1
findings_documented_only: 1
blocks: 10
---

> ## Execution record (updated post-execution)
>
> **Status: executed.** All ten blocks shipped; the independent Validator returned
> **ACCEPT WITH FOLLOW-UPS**. Follow-ups M-1..M-4 and S-2/S-5/S-8 are closed in a
> separate change set (`docs(phase01)` + this plan's execution-record commit).
>
> Block commit hashes (the primary commit per block; companion docs commits are noted):
> 1. `8bf0517` — CI lint/typecheck scope to `src/` (`ENT-004`)
> 2. `14a561d` — Compose env contract: gunicorn `child_exit` guard + Prometheus multiproc (`ENT-001/011/012`)
> 3. `b7124b4` — scheduler interruptible/bounded stop (`ENT-002`)
> 4. `eb79c4b` — bot readiness markers before command registration (`ENT-007`)
> 5. `b9eabcc` (+ `61c1a54` exit-code propagation) — test-bootstrap containment + `entrypoint-test.sh` header (`ENT-008/014`)
> 6. `fbbb6cf` (+ `dc8aa8c`, `d518fb6`) — durable daily marker + idempotent `send_alerts` (`ENT-003`)
> 7. `6b3b8cf` (+ `516a997`) — liveness marker refreshed only after a clean cycle (`ENT-013`)
> 8. `7aac8d3` — `migrate_locked` docstring + acquisition log (`ENT-006` residual)
> 9. `b0eba44` (+ `a9871bb`) — per-update user memoisation (`ENT-010` Half A)
> 10. `aa71faa` (+ `cc54f8f`) — `LoginToken` lifecycle service extraction (`ENT-005`)
>
> Final documentation alignment: `344ca2b` `docs(phase01)`.
>
> **Disposition of the de-scoped and absorbed findings** (unchanged from §0.3):
> `ENT-006` shipped its residual (docstring + acquisition log) in BLOCK 8; its
> acquisition-timeout half is superseded by phase 03 `DB-004`. `ENT-010` shipped
> Half A only in BLOCK 9 (connection-lifecycle half rejected as intentional design).
> `ENT-009` was absorbed by phase 03 `DB-005` — no phase-01 work. `ENT-014`
> (documented-only) shipped with BLOCK 5.

# Execution Plan — Phase 01 Remediation (Entry Points & Process Architecture)

## 0. Header, provenance and scope statement

### 0.1 Provenance

| Item | Value |
|---|---|
| Source report | `.ai/audit/99-validation/01-entry-architecture-validated-findings.md` (validated, 859 lines) |
| Report anchor commit | `9e96b84` |
| **Working anchor commit for this plan** | **`8060fcf`** (`git rev-parse --short HEAD`; working tree clean) |
| Date | 2026-09-28 |
| Findings in scope | 14 (`ENT-001` … `ENT-014`) |
| Verdicts in source report | Confirmed 10 · Adjusted 4 · Rejected 0 |
| Execution blocks | 10 |
| Implementor concurrency | 1, strictly sequential (project rule: only one implementor at a time) |

### 0.2 Evidence basis — read this before executing any block

The code-context document supplied to the Planner
(`C:\Users\Om\AppData\Local\Temp\kilo\code-context-phase01.md`) **was not readable**:
every access path (`read`, `filesystem_read_text_file`, `grep`, `Get-Content`) was
rejected by the workspace's `external_directory: * deny` permission rule.

The Planner therefore re-derived Sections A–E directly from the working tree at
`8060fcf` and from the sibling validated reports. Everything asserted in this plan
was re-verified in that pass. Specifically re-verified by direct observation:

- `uv run ruff check .` at the repository root → **2 errors**, both inside
  `.ai/audit/03-db-concurrency/verify_db.py` (F841 unused `bar`, UP031 percent
  format). `uv run basedpyright .` at the root → **14 errors**, exactly the split
  recorded below, with no production-code errors.
- `gunicorn.conf.py` is at the **repository root**, not under `src/backend/`.
- The `Makefile` / `Makefile.ps1` `lint`, `format` and `typecheck` targets run
  **inside the `web` container** (`docker compose … run --rm web uv run ruff
  check src/`), not on the host — and they target `src/`, not `.`.
- `config/settings/test.py` pins `DATABASES["default"]["NAME"] = "mko_bazuna"`
  and sets `MIGRATION_MODULES = DisableMigrations()`.
- Test settings use **LocMemCache**, not Redis (`CACHES` is overridden in
  `config/settings/test.py`). This materially affects the ENT-003 marker-substrate
  decision (see §3, BLOCK 6).
- `AnalyticsEvent.Meta` declares an index and **no** unique constraint;
  `DailyAdMetrics` is the model that does carry a `UniqueConstraint`.
- `AdvisoryLockId` currently has 18 members; session-scoped IDs occupy
  100/101/102/103/104/110/111.
- `apps/core/migrations/` contains `0001_initial` … `0004_support_models`, so the
  next number is `0005_*`.
- The compose-contract test precedents are `src/backend/tests/test_compose_hardening.py`
  (string-level `_service_block()` extraction) and
  `src/backend/apps/core/tests/test_health_contract.py` (real YAML via `ruamel.yaml`,
  **single file only — no override merging**).
- `apps/core/tests/test_advisory_lock_release_log.py` asserts the **transaction**
  branch registers a `transaction.on_commit` release callback. This is DB-010's
  territory and must keep passing unchanged after phase 01.

If any statement in this plan conflicts with a fact the code-context document held
but the tree no longer shows, the tree wins — the anchor is `8060fcf`, not `9e96b84`.

### 0.3 Scope statement (explicit)

**In scope — implemented by this plan (10):**
`ENT-001`, `ENT-002`, `ENT-003`, `ENT-004`, `ENT-005`, `ENT-007`, `ENT-008`,
`ENT-011`, `ENT-012`, `ENT-013`.

**De-scoped to a named residual (2):**

- **`ENT-006`** → residual elements only: (a) the `migrate_locked` module-docstring
  "skip" claim vs. the blocking `pg_advisory_lock` actually issued, and (b) the
  silent acquisition wait (the "Acquired …" line fires *after* the lock is granted).
  The **acquisition-timeout half is superseded by phase 03 `DB-004`** (severity
  raised to HIGH, larger remediation). This plan adds **no** `lock_timeout` and
  **no** `statement_timeout`.
- **`ENT-010`** → **Half A only** (memoise the resolved `User` once per update in
  the aiogram `data` dict). **Half B** (`CONN_MAX_AGE` / per-update
  `close_old_connections`) is documented intentional design and is rejected as a
  defect by the report itself; it is not touched.

**Absorbed by another phase's finding (1):**

- **`ENT-009` → absorbed by phase 03 `DB-005`.** Phase 01 ships **no**
  implementation and **no** "short-lived marker" design. `DB-005` owns the design
  decision, *including* the unresolved fork about **where the final move happens
  relative to the transaction boundary** in `submit_ad`. This plan does **not**
  pre-empt that fork and does not touch `apps/ads/services/submission.py`,
  `apps/media/services/filesystem.py`, or
  `apps/media/management/commands/sweep_orphaned_media.py`. The "short-lived
  promotion marker" proposal carried in the phase-01 report's required fix is
  **superseded** by `DB-005` option 1 (keep new files under a directory the sweep
  excludes). See §5.

**Documented-only (1):**

- **`ENT-014`** — the `docker/entrypoint-test.sh` header comment. The code is
  correct; only the comment is wrong. It ships in the same change as `ENT-008`
  because both edit the same file (see BLOCK 5).

**Counts:** 10 implemented + 2 de-scoped + 1 absorbed + 1 documented-only = **14**.

### 0.4 Severity correction (new audit-input defect — VAL-005)

The source report's `Severity movement` summary line reads
`0 CRITICAL, 4 HIGH, 4 MEDIUM, 6 LOW`. That line **contradicts the report's own
per-finding `Final sev.` column**, which tallies to:

| Severity | Findings | Count |
|---|---|---|
| CRITICAL | — | 0 |
| HIGH | `ENT-002`, `ENT-003`, `ENT-004` | **3** |
| MEDIUM | `ENT-001`, `ENT-005`, `ENT-006`, `ENT-007`, `ENT-009` | **5** |
| LOW | `ENT-008`, `ENT-010`, `ENT-011`, `ENT-012`, `ENT-013`, `ENT-014` | **6** |

Recording this as **VAL-005 (documentation-only, no code impact)**. The per-finding
column is treated as authoritative throughout this plan. The severity column in §2
is therefore the acceptance contract and must be read from that table, not from the
report's summary line.

---

## 1. Environment and command contract for the implementor

These constraints bind every block. They are not optional and they are not
re-derived per block.

| Concern | Rule |
|---|---|
| Test execution | **Docker only.** `.\Makefile.ps1 test` (Windows PowerShell 7+) or `make test`. Never `uv run pytest` locally — there is no DB on `localhost:5432`. |
| Test DB | Start once per session: `.\Makefile.ps1 test-db` (starts `mko-bazuna-test-db-*`). |
| Targeted test run | `$dc run --rm -e PYTEST_OPTS="<tokens>" test` with `$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'`. |
| `PYTEST_OPTS` | **Word-split on spaces and unquoted.** `-k test_name` and bare file paths work; a quoted multi-token value such as `-k "a b"` does **not**. Setting `PYTEST_OPTS` **replaces** the defaults (`--reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup`), so targeted runs lose xdist parallelism and DB reuse. |
| `PYTEST_SKIP_MARKERS` | `--env PYTEST_SKIP_MARKERS=seed` skips the nightly seed suite. Prefer this over `PYTEST_OPTS` for marker exclusion. |
| Fresh schema | `.\Makefile.ps1 test-recreate` after any migration change or interrupted run. |
| Image rebuild | **Not needed** — the `test` service bind-mounts the repo. |
| Static gates | `uv run ruff check src/` and `uv run basedpyright src/` run fine on the host (no DB needed). Inside Docker, `make lint` / `make typecheck` run the same commands in the `web` container. |
| `ruff` autofix | `uv run ruff check --fix src/` sorts imports (`I001`). `ruff format` is **not** part of the project's convention. |
| Never | `--override-ini=addopts=` — it strips `--import-mode=importlib`, which `pyproject.toml` sets and which the suite depends on. |
| PowerShell | `head` and `tail` do not work. Use `Select-Object -First/-Last`, `Get-Content -TotalCount`, `Select-String`. |
| Full suite | `.\Makefile.ps1 test-all` (~35 min, includes `seed`). Required only when a block touches seeding or image generation — none of these blocks do. |
| i18n | Any new user-visible string requires `{% trans %}`/`gettext` **and** non-empty `msgstr` for `ru` and `bs`. Only BLOCK 5 and BLOCK 9 plausibly touch user-visible strings; both are pre-existing strings being moved, not new ones. If a new string appears, the i18n completeness gate must pass. |

---

## 2. Scope decisions table (acceptance contract for execution)

| ID | Disposition | Block | Final severity | One-line reason |
|---|---|---|---|---|
| `ENT-001` | **implement** (both halves; compose half merged into the BLOCK 2 contract test) | BLOCK 2 | MEDIUM | Guard is three lines and removes a load-driven arbiter crash; the compose half is one contract assertion, not a fourth one-line fix. |
| `ENT-002` | **implement** | BLOCK 3 | HIGH | Every scheduler stop today is a SIGKILL at 30 s; the one-liner in the report is insufficient and needs a design pass. |
| `ENT-003` | **implement** (marker substrate deliberately left open) | BLOCK 6 | HIGH | Duplicate daily digests after any restart; marker + idempotent delivery must land as one change. |
| `ENT-004` | **implement** (target decision taken; 14 errors) | BLOCK 1 | HIGH | CI cannot see `src/telegram_bot` and the typecheck job is red today. |
| `ENT-005` | **implement** | BLOCK 10 | MEDIUM | The `LoginToken` lifecycle has no owner and `consent.py` is a 470-line view; extraction follows the existing `login_rate_limit.py` precedent. |
| `ENT-006` | **de-scope to residual only** — (a) docstring, (b) pre-acquisition log | BLOCK 8 | MEDIUM | The timeout half is superseded by phase 03 `DB-004` (HIGH); shipping it twice is forbidden. |
| `ENT-007` | **implement** | BLOCK 4 | MEDIUM | Four sequential 30 s Telegram calls gate readiness that a healthcheck gives 120 s; readiness must not depend on Telegram answering. |
| `ENT-008` | **implement** (both halves, internally sequenced) | BLOCK 5 | LOW | A 39-table migration-less schema is built in the non-test DB on every run and `\|\| true` masks real DDL failures. |
| `ENT-009` | **absorbed by phase 03 `DB-005`** — no phase-01 work | — (closed) | MEDIUM | Same defect, same fix; `DB-005` owns the design and its unresolved transaction-boundary fork. |
| `ENT-010` | **de-scope to Half A only** — per-update user memoisation | BLOCK 9 | LOW | Duplicate `User` lookups are real; the connection-lifecycle half is documented intentional design. |
| `ENT-011` | **implement** (folded into the BLOCK 2 contract block) | BLOCK 2 | LOW | One compose line; grouped with `ENT-001`/`ENT-012` per VAL-003 because the regression guard is one test module. |
| `ENT-012` | **implement** (folded into the BLOCK 2 contract block) | BLOCK 2 | LOW | The report's higher-ROI option: record the deliberate dev `bot`/`seed` asymmetry and assert it, rather than mirroring the dependency. |
| `ENT-013` | **implement** | BLOCK 7 | LOW | The marker is refreshed unconditionally, so a failing loop stays `healthy` forever; also inverts a currently-green test. |
| `ENT-014` | **documented-only** (same change as `ENT-008`) | BLOCK 5 | LOW | Only the `entrypoint-test.sh` header comment is wrong; the code is correct. |

---

## 3. Execution blocks

Roster legend and the standing rule: **Implementor is always required, exactly one at
a time, sequentially.** Auditor / Researcher / Planner / Validator are added per block
with an explicit justification and an explicit statement of who is *not* required and
why. The rule "high risk ⇒ all agents" is applied only to BLOCK 5 (fragile insertion
point) and BLOCK 6 (unsafe ordering + HIGH).

---

### BLOCK 1 — Static gate scope + green typecheck

| | |
|---|---|
| **Findings owned** | `ENT-004` |
| **`depends_on`** | *(none)* |
| **Priority** | P0 — executes first |
| **Roster** | **Implementor, Validator** |

**Agent requirement decision.**
- **Implementor — yes.** Always.
- **Auditor — no.** The evidence is complete: 14 errors, exact files, exact rule
  classes, and an established in-repo remedy. There is no unresolved investigative
  question; an audit pass would re-derive facts already reproduced below.
- **Researcher — no.** The *target* decision is forced by constraints, not open: the
  audit tooling under `.ai/audit/**` is unmodifiable, so `ruff check .` at the root
  can never be made green, and `src/` is the only target that both excludes `.ai/**`
  and exactly matches `Makefile` / `Makefile.ps1`. No external best-practice question
  remains.
- **Planner — no.** The change is a four-line YAML edit plus 14 mechanical, explicitly
  specified test-file edits. There is no design to pre-author.
- **Validator — yes.** The artefact under change is the CI gate itself, and the
  claim being made ("a root-level green gate now covers both processes") is only
  established by an independent run. The risk of an unnoticed CI-parity regression is
  the whole point of the finding.

**Findings and notes carried forward.**
1. **Target decision (made, not open):** change the `lint` job's ruff step and the
   `typecheck` job's basedpyright step to run from the **repository root over
   `src/`**, dropping `working-directory: src/backend` for those two steps only.
   Rationale: `src/` reproduces the local gate exactly (`Makefile`'s `ruff check src/`
   and `basedpyright src/`, mirrored in `Makefile.ps1`) — which *is* the
   local/CI parity deviation the finding is about — and it needs **no** config change.
2. **The root-level `ruff check .` trap is real and must not be "fixed" the wrong
   way.** `uv run ruff check .` fails with 2 errors inside
   `.ai/audit/03-db-concurrency/verify_db.py` (F841, UP031) because `[tool.ruff]`
   `exclude` lists `.direnv`, `.eggs`, `.git`, … but no dot-directory entry for
   `.ai`. Those files are audit-phase artefacts and **must not be edited**. Do **not**
   add `.ai` to `[tool.ruff] exclude` to work around it either — that would bake a
   tooling concession into product config. Targeting `src/` sidesteps both.
   `uv run basedpyright .` at the root is already clean of `.ai/**` because
   basedpyright's default exclude covers `**/.*`.
3. **The 14 errors and their exact remedies** (re-verified at `8060fcf`):
   - **12 errors** — `Atomic.__enter__` / `__exit__` are untyped
     (`reportGeneralTypeIssues`) in two **test** files, at two `with advisory_lock(...)`
     sites each: `src/backend/apps/ads/tests/test_edit_views_locking.py` and
     `src/backend/apps/moderation/tests/test_admin_actions.py`. Remedy: the project's
     established inline comment, verbatim —
     `# pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped`
     (identical to the text already in `apps/search/management/commands/send_alerts.py`,
     `apps/media/management/commands/sweep_orphaned_media.py`,
     `apps/ads/services/submission.py`, `apps/users/views/consent.py`,
     `apps/users/services/deletion.py`). Fix the **tests**, never production code
     (project rule 2).
   - **2 errors** — `src/telegram_bot/tests/test_ad_create.py`, two `fake_download`
     coroutines that call `destination.write(...)` while the parameter's declared
     default makes it `None`. Remedy is a **typed signature or an explicit assert on
     `destination` — not a `pyright: ignore`.** The finding's test-gap note is
     explicit that a suppression is the wrong fix here.
4. **The two "production errors" in the original auditor report are not
   reproducible and must not be reintroduced** (`telegram_bot/handlers/alerts.py`,
   `telegram_bot/handlers/contact.py`). `basedpyright` at the root reports 14 errors,
   none in production code.
5. **Do not touch the `test` job.** It keeps its own `working-directory: src/backend`
   and its job-level `PYTHONPATH`. `pythonpath` in `[tool.pytest.ini_options]` is
   resolved relative to the **config file**, not the CWD, so dropping the
   `working-directory` on `lint`/`typecheck` cannot affect collection.
6. **Keep the lockfile/deps steps coherent.** The `lint` and `typecheck` jobs also run
   `uv lock --check` and `uv sync --frozen --no-install-project --group dev` with
   `working-directory: src/backend`. Only the two `run:` steps change target and drop
   their `working-directory`; the dependency-install steps keep theirs, because the
   lockfile and the venv live in `src/backend`.
7. **Optional, recommended:** add `PYTHONPATH: ${{ github.workspace }}/src:${{ github.workspace }}/src/backend`
   at job level for `lint` and `typecheck`, matching the Dockerfile's runtime
   `ENV PYTHONPATH` (which is what `make lint` / `make typecheck` inherit inside the
   `web` container) and matching the existing `test` and `i18n` jobs. This is a
   parity improvement, not a correctness requirement — the current 14 errors are
   import-independent and `reportMissingImports` is `none`.
8. **Out of this block but noted so it is not mistaken for a regression:** the
   `security` job's `uv run bandit -r src/backend src/telegram_bot` runs with
   `working-directory: src/backend`, so its paths resolve to
   `src/backend/src/backend`. That is pre-existing and is **not** a phase-01 finding.

**File surface (semantic units).**
- `.github/workflows/ci.yml` → `jobs.lint.steps["Run ruff"]`,
  `jobs.typecheck.steps["Run basedpyright"]`; optionally the job-level `env` of both.
- `src/backend/apps/ads/tests/test_edit_views_locking.py` → the two
  `with advisory_lock(...)` call sites.
- `src/backend/apps/moderation/tests/test_admin_actions.py` → the two
  `with advisory_lock(...)` call sites.
- `src/telegram_bot/tests/test_ad_create.py` → the two local `fake_download`
  coroutines in the download-size-cap test class.
- **Not touched:** `pyproject.toml` (no config change needed), `.github/workflows/ci.yml`'s
  `test` / `i18n` / `security` / `lint-templates` jobs, `.ai/**`.

**Tests required.**
- *Must keep passing unchanged:* every test in
  `apps/ads/tests/test_edit_views_locking.py` and
  `apps/moderation/tests/test_admin_actions.py` (the change is comment-only there);
  every test in `src/telegram_bot/tests/test_ad_create.py` (the change is a signature
  and/or an assert).
- *Must be added/changed:* none. This block is comment- and annotation-level; the gate
  **is** the test.
- *Gate:* `uv run ruff check src/` → exit 0 · `uv run basedpyright src/` → **0 errors**
  · `uv run ruff check .` is **not** the gate and is expected to stay at 2 errors in
  unmodifiable audit tooling · `.\Makefile.ps1 test` (regression sweep; the change is
  annotation-only but the CI-scope claim warrants one confirmation run).

**Risk / rollback.**
- *Risk:* an implementer "fixes" the root ruff failure by editing
  `.ai/audit/03-db-concurrency/verify_db.py` or by adding `.ai` to `[tool.ruff] exclude`.
  Both are forbidden. The Validator must confirm `.ai/**` is byte-identical afterwards
  (`git status --short .ai`).
- *Risk:* dropping `working-directory` from the wrong step in the same job breaks
  dependency installation. Constrain the edit to the two named steps.
- *Rollback:* revert the `ci.yml` hunk; the test-file annotations are inert.

---

### BLOCK 2 — Compose environment contract (`web` / `bot` / `scheduler`)

| | |
|---|---|
| **Findings owned** | `ENT-001` (code half + compose half), `ENT-011`, `ENT-012` |
| **`depends_on`** | *(none)* |
| **Priority** | P1 |
| **Roster** | **Implementor, Researcher, Validator** |

**Grouping decision (VAL-003) and its justification.**
`ENT-001`, `ENT-011` and `ENT-012` are three instances of one structural weakness:
*a process contract is expressed in exactly one Compose file and nothing asserts that
every environment satisfies it.* The report's own ROI observation is that three
independent one-line fixes are worse than one contract assertion. They are **grouped
into one block** for three reasons:

1. All three edits land in the **same three files** (`docker-compose.yml`,
   `docker-compose.prod.yml`, `docker-compose.dev.override.yml`). Splitting them means
   three blocks touching the same YAML in three review passes.
2. The regression guard for all three is **one test module**. Splitting would produce
   three partial versions of one file across three blocks — a merge hazard, not a
   safety win.
3. The code half of `ENT-001` (the `child_exit` guard) is three lines and belongs to
   the same "one contract, one assertion" story.

The cost is that this block is larger than any single finding's fix. That is accepted,
because the only way to get the VAL-003 benefit is to write the assertion once.

**Agent requirement decision.**
- **Implementor — yes.** Always.
- **Auditor — no.** Every relevant location is already enumerated and verified; nothing
  about the current state is unknown.
- **Researcher — yes**, for **one narrow question only**: *where should
  `PROMETHEUS_MULTIPROC_DIR` live, and what does Compose actually do with
  `environment` and `tmpfs` when the prod override merges over the base file?* Two
  answers are genuinely defensible (§3.1). The merge semantics determine which one is
  correct, and getting it wrong silently changes the prod deployment contract. This is
  a small, bounded question — hence Researcher, not Planner.
- **Planner — no.** Once the placement is chosen, the remaining work is mechanical.
- **Validator — yes.** Compose **is** the deployment contract. A wrong merge can brick
  production or silently alter the dev stack, and no unit test can see it. The
  Validator must run `docker compose config` for each stack.

**3.1 — The one genuinely open choice in this block (do not pre-empt it).**

`ENT-001`'s required fix says two things: guard the hook, *and* set the variable in
the **base** compose. The second half has two viable answers:

| Option | Change | Pro | Con |
|---|---|---|---|
| **A (recommended)** | Add `PROMETHEUS_MULTIPROC_DIR` **and** the matching `tmpfs` mount to the base `web` service; remove the now-duplicate entries from `docker-compose.prod.yml`'s `web`. | Single source of truth — literally "one contract, one place", which is the VAL-003 thesis. Any environment inheriting `gunicorn.conf.py` gets it automatically. | The dev override replaces `web`'s `command` with `manage.py runserver`, so the base `web` would carry a Prometheus tmpfs it never uses (harmless but not free). Requires confirming how Compose merges the `environment` sequence and the `tmpfs` sequence between base and override. |
| **B** | Leave the variable in `docker-compose.prod.yml` where it already is; ship only the `child_exit` guard plus a contract assertion that every stack whose `web` runs gunicorn sets it. | Zero Compose merge risk; smallest possible diff; nothing that ships today changes. | Weakens the "one place" claim — the assertion, not the file, becomes the contract, so a new environment can still drift. |

The **Researcher** must decide and state the Compose merge semantics it relied on.
This plan does **not** choose.

**Findings and notes carried forward (this block).**
1. **Mechanism is reproduced and load-driven, not shutdown-specific** — two HTTP
   requests were enough to take the arbiter to exit 255. `prometheus_client.multiprocess`
   resolves the directory from `PROMETHEUS_MULTIPROC_DIR` then falls back to
   `prometheus_multiproc_dir`; with neither set it is `None`, and
   `glob.glob(os.path.join(None, ...))` raises `TypeError`. `gunicorn/arbiter.py`
   catches only `OSError` around the `child_exit` hook, and the loop-level
   `except Exception` calls `stop(False)` and `sys.exit(-1)`.
2. **`gunicorn.conf.py` is at the repository root** and currently has **no `import os`**.
   The guard requires it. Its module docstring promises "only pure Python values" so
   that `preload_app` can load the config before forking — `os` is a stdlib pure
   import with no Django, so that promise still holds; update the docstring to say so.
3. **The guard should mirror the library's own resolution**, i.e. accept either
   `PROMETHEUS_MULTIPROC_DIR` or the lowercase `prometheus_multiproc_dir` fallback,
   rather than checking only the uppercase name. Otherwise the guard is correct for
   the project's Compose files and still wrong for a deployment that uses the
   documented lowercase fallback.
4. **`test_observability.py` must be retargeted if Option A is chosen.** Its
   `test_prometheus_multiproc_dir_configured` asserts the variable appears in
   `docker-compose.prod.yml`. Under Option A that assertion becomes wrong. Retarget it
   to the file the contract now lives in, and keep `test_gunicorn_has_child_exit_hook`
   (string-level) passing.
5. **`ENT-011`:** add `stop_grace_period: 30s` to the `bot` block in
   `docker-compose.prod.yml`, matching `web` and `scheduler`. The base `bot` service
   declares none and Compose does not inherit one, so the bot currently gets Docker's
   10 s default while its siblings get 30 s. `BOT_HEALTH_CHECK_ENABLED` defaults to
   `False`, which is why the impact is self-muted — that must not be used as a reason
   to skip the change.
6. **`ENT-012` — take the report's higher-ROI option: record, do not mirror.** The dev
   `web` waits on `seed` via `depends_on`; the dev `bot` does not and inherits only
   `load_catalog` + `redis`. Mirroring the `seed` dependency would delay the bot behind
   the full seed run (600 ads by default) in a development loop, for a service that
   serves no media — a strictly worse trade. Instead: add a comment to the dev `bot`
   block stating that the asymmetry is deliberate (the bot needs no seeded media), and
   assert the *decision* so a future well-meaning `depends_on` addition is a deliberate,
   reviewed act. The report's "either/or" is resolved here because the evidence already
   makes it unambiguous; only the exact assertion wording is left to the implementor.
7. **New compose-contract test module.** Precedents: `_service_block()` string
   extraction in `src/backend/tests/test_compose_hardening.py`, and real YAML parsing
   in `src/backend/apps/core/tests/test_health_contract.py`. **Pick one and do not
   mix.** Recommended: `ruamel.yaml` real parsing, matching `test_health_contract.py`.
   **Important limitation the implementor must design around:** `ruamel.yaml` parses a
   single file — it does **not** merge the base and the override. Neither existing
   precedent asserts an *inherited* value. Therefore assert **per file**
   ("the base file declares the contract"; "no override contradicts it"), and do **not**
   shell out to `docker compose config` from the default test gate. If a merged-view
   assertion is wanted, put it in a separate `@pytest.mark.slow` test that skips when
   Docker is unavailable — that is optional, not required.
8. **Follow the existing conventions:** `pytestmark = [pytest.mark.unit]`, root
   resolved by walking upward to `pyproject.toml` (the `test_compose_hardening.py`
   pattern) or via `settings.BASE_DIR.parent` (the `test_health_contract.py` pattern).

**File surface (semantic units).**
- `gunicorn.conf.py` → `child_exit()`; module-level `import os`; module docstring.
- `docker-compose.yml` → `services.web` (environment, tmpfs) — only under Option A.
- `docker-compose.prod.yml` → `services.bot` (`stop_grace_period`);
  `services.web` (environment, tmpfs) — only under Option A.
- `docker-compose.dev.override.yml` → `services.bot` (explanatory comment).
- `src/backend/apps/core/tests/test_observability.py` →
  `test_prometheus_multiproc_dir_configured` (retarget only under Option A).
- **New:** one compose-contract test module under `src/backend/tests/`.
- **New:** a behavioural test for `child_exit`.

**Tests required.**
- *Must keep passing unchanged:* `src/backend/apps/core/tests/test_compose_hardening.py`
  (all of it — note `test_web_service_has_hardening` and `test_bot_service_has_hardening`
  iterate `_HARDENING_KEYS` against the **base** blocks, so any base-file restructuring
  must keep those keys present); `src/backend/apps/core/tests/test_health_contract.py`
  (asserts `/health/live/` and `BOT_HEALTH_STALE_SECONDS=120` in the base file and the
  scheduler healthcheck in the prod file).
- *Must be added:*
  - A **behavioural** test for `child_exit` — with the variable unset it must not
    raise; with it set it must mark the process dead. The module is at the repository
    root, which is not on `src/`'s import path, so load it with
    `importlib.util.spec_from_file_location` against
    `settings.BASE_DIR.parent / "gunicorn.conf.py"` and patch
    `prometheus_client.multiprocess.mark_process_dead`.
  - Compose-contract assertions covering all three contracts: the Prometheus
    directory wherever the `web` service runs gunicorn; `stop_grace_period: 30s` on all
    three long-lived services; and the recorded dev `bot`/no-`seed` decision.
- *Need no test (pure plumbing):* the `stop_grace_period` value itself — it is covered
  by the contract assertion above, not by a behavioural test.
- *Gate:* `.\Makefile.ps1 test` (or `$dc run --rm -e PYTEST_OPTS="src/backend/tests/<new-module>.py src/backend/apps/core/tests/test_observability.py" test`)
  **plus** `docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml config`,
  `docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml config`,
  and the test-project stack, each confirming the resolved `web`/`bot` environment and
  tmpfs.

**Risk / rollback.**
- *Risk (highest in this block):* choosing Option A without knowing how Compose merges
  the `environment` and `tmpfs` sequences, and silently **dropping** the prod
  `PROMETHEUS_MULTIPROC_DIR` or its tmpfs during the move. A dropped tmpfs with
  `read_only: true` makes the web container fail to start; a dropped variable re-opens
  the arbiter crash. The `docker compose config` gate exists for this.
- *Risk:* the new test module's `pytestmark` or root-resolution pattern diverging from
  the two precedents and breaking under the test container's differing CWD.
- *Risk:* the `test_observability.py` retarget being forgotten under Option A — the
  suite then fails, which is the correct outcome, but it must be retargeted in the
  **same** change, not left for a follow-up.
- *Rollback:* each half is independently revertible. The `child_exit` guard is
  behaviourally inert when the variable is set (it performs the same call as today), so
  reverting it changes nothing in the current prod deployment.

---

### BLOCK 3 — Scheduler graceful stop (bounded stop latency)

| | |
|---|---|
| **Findings owned** | `ENT-002` |
| **`depends_on`** | *(none)* |
| **Priority** | P1 |
| **Roster** | **Implementor, Planner, Validator** |

**Agent requirement decision.**
- **Implementor — yes.** Always.
- **Auditor — no.** The module, the signal handler, the loop, the default `sleep_func`
  and the production interval are all identified, and the defect was reproduced at
  runtime. There is nothing left to investigate.
- **Researcher — no.** No external best-practice question is open; the mechanism is
  fully understood from the code, and the report's own required fix is stated.
- **Planner — yes.** The report's one-liner is **insufficient**, and the Planner must
  resolve the parts it does not settle (below). Designing the bounded-wait semantics
  before code is written is the difference between a fix and a partial fix.
- **Validator — yes.** HIGH severity; the change alters the process's shutdown
  contract; and the existing suite **cannot** catch a regression here because every
  scheduler test injects a no-op `sleep_func`.

**Findings and notes carried forward.**
1. **The report's one-liner is insufficient — this is stated explicitly in the
   research brief and must be honoured.** `run_scheduler` calls
   `sleep_func(interval_seconds)` **unconditionally after** the cycle. Substituting a
   `_stop_event`-backed wait breaks the *post-cycle* wait immediately, but a SIGTERM
   delivered **during** a cycle is still not observed until the *next* top-of-loop
   check. The maximum stop latency is therefore `interval + cycle_duration`, not the
   remaining sleep. With the production interval at 3600 s and
   `stop_grace_period: 30s`, this still means SIGKILL. **The Planner must decide and
   justify**: does the stop flag abort the *wait* only, or may it also short-circuit
   the post-cycle wait (e.g. skip or shorten it when the flag is already set)? This
   plan does not pre-empt that.
2. **A per-command timeout already exists and does not help.**
   `SCHEDULER_COMMAND_TIMEOUT` (default 1800) bounds each child `manage.py`
   invocation via `_run_command_subprocess`, not the wait between cycles. A
   nine-command cycle can legitimately exceed 30 s.
3. **Existing tests inject `sleep_func` and therefore still pass** if the *default*
   changes. `TestGracefulShutdown.test_scheduler_stops_on_stop_event_after_one_cycle`
  injects a `sleep_func` that sets the flag itself and asserts one full cycle ran —
  that is the semantics of the *injected* function, not the default, so it stays valid.
  `TestRunScheduler` injects `stop_after_one` which raises `StopIteration` to break the
  loop; likewise unaffected.
4. **Watch for a new lint error.** `import time` at module scope is currently
   referenced **only** by the `sleep_func` default argument (`time.sleep`). Replacing
   that default with an event-backed wait makes `time` unused and `ruff` will flag
   `F401`. Either remove the import or keep a real use.
5. **The fix is confined to `run_scheduler`'s `sleep_func` default and, if the Planner
   so decides, the loop's wait logic.** It must not change the `while True` /
   top-of-loop stop check, the per-command isolation in `_dispatch`, the
   `except Exception: "Scheduler cycle failed — continuing"` behaviour, or
   `_shutdown()`'s contract.
6. **Real-signal integration test.** The report is explicit that a real-signal test
   asserting exit 0 within seconds is required, because the existing style cannot catch
   this. Design constraint: `signal.signal` is only legal on the main thread, so the
   test must either (a) call the real `_handle_shutdown_signal` handler directly from a
   background thread that sets the flag while the main thread is inside the wait, or
   (b) spawn a subprocess running the module. The Planner picks; the Validator
   confirms it genuinely fails against the pre-fix code.

**File surface (semantic units).**
- `src/backend/apps/core/utils/scheduler.py` → `run_scheduler()` (the `sleep_func`
  default and, if decided, the post-cycle wait); module-level `import time` if it
  becomes unused; the `run_scheduler` docstring (the `sleep_func` argument contract).
- `src/backend/apps/core/tests/test_scheduler.py` → `TestGracefulShutdown`; a new
  bounded-latency test.
- **Not touched:** `HOURLY_COMMANDS`, `DAILY_COMMANDS`, `DAILY_HOUR_UTC`,
  `SCHEDULE_INTERVAL_SECONDS`, `should_run_daily()`, `run_one_cycle()`, `_dispatch()`,
  `_run_command_subprocess()`, `_shutdown()`, `main()`, the signal handler.
  **In particular `last_daily` bookkeeping belongs to BLOCK 6, not here.**

**Tests required.**
- *Must keep passing unchanged:* `src/backend/apps/core/tests/test_scheduler.py` in
  full (`TestSchedulerConstants`, `TestShouldRunDaily`, `TestRunOneCycle`,
  `TestRunScheduler`, `TestGracefulShutdown`, `TestValidateCommands`,
  `TestDefaultManagePy`, `TestRunCommandSubprocess`, `TestDispatchIsolation`) and
  `src/backend/apps/core/tests/test_scheduler_error_handling.py` in full.
- *Must be added:* a test proving the wait is interruptible — the loop exits within a
  small bound after the stop flag is set, using the **real** wait, not an injected
  no-op. It must be red against the pre-fix code.
- *Gate:* `$dc run --rm -e PYTEST_OPTS="src/backend/apps/core/tests/test_scheduler.py src/backend/apps/core/tests/test_scheduler_error_handling.py" test`
  then `.\Makefile.ps1 test` for the regression sweep.

**Risk / rollback.**
- *Risk:* bounding only the wait and leaving `interval + cycle_duration` as the
  worst case — the fix would look green in the new test and be ineffective in
  production. The Validator must trace the SIGTERM-during-cycle path explicitly.
- *Risk:* a test that proves the flag is *set* rather than that the loop *exits
  quickly* — that is the current test's blind spot and must not be reproduced.
- *Rollback:* revert the `sleep_func` default; no persisted state, no schema, no
  deployment contract.

---

### BLOCK 4 — Bot lifecycle readiness ordering

| | |
|---|---|
| **Findings owned** | `ENT-007` |
| **`depends_on`** | *(none)* |
| **Priority** | P3 |
| **Roster** | **Implementor** |

**Agent requirement decision.**
- **Implementor — yes.** Always.
- **Auditor — no.** The ordering, the four call sites, the absence of any timeout, and
  the existing coverage are all identified; the module is 172 lines and fully
  characterised.
- **Researcher — no.** No external best-practice question; the remedy is stated in
  the report and the fail-open design is already correct.
- **Planner — no.** The change is a reorder plus one bounded await.
- **Validator — no.** Self-contained module, existing lifecycle coverage, and a new
  regression test pins the behaviour. Risk is contained to bot startup, which the
  healthcheck surfaces immediately.

**Findings and notes carried forward.**
1. `_on_startup` currently awaits `_set_bot_commands(bot)` **before** touching the
   file marker and awaiting `_write_redis_marker()`. `_set_bot_commands` issues one
   `set_my_commands` per configured language plus one default-scope call — four
   sequential round-trips, each individually wrapped in a bare
   `try/except Exception: continue`, with **no** `asyncio.wait_for` and no overall
   budget. aiogram's default per-request timeout is 30 s, so the worst case is ~120 s —
   exactly the bot healthcheck's unhealthy window (`start_period: 30s`,
   `interval: 30s`, `retries: 3`).
2. **Target ordering:** write the file marker and the Redis marker **first**, then run
   the command registration under a bounded budget. Readiness must mean "polling is
   about to start", not "Telegram answered four times".
3. **`asyncio` is not currently imported** in `lifecycle.py`. Add it.
4. **Budget constant.** Per project rule 10, the timeout must be a named module-level
   constant (e.g. `Final[int]`, matching `_BACKOFF_BASE` in `send_alerts.py`), not an
   inline literal. The report suggests 10 s for the whole registration; the
   implementor may pick a different value with a stated rationale, since it must sit
   comfortably under the healthcheck's `start_period`.
5. **The budget's timeout must be swallowed, not propagated.** The existing
   `try/except Exception` around `_set_bot_commands` is expected to catch the timeout
   (since Python 3.11 `asyncio.TimeoutError` is the built-in `TimeoutError`, a subclass
   of `OSError`, hence of `Exception`) — but this must be **verified by the new test**,
   not assumed. If the timeout escapes, startup aborts, which is a regression.
6. **Existing tests remain valid under the reorder.** `TestOnStartupCommands` patches
   `_marker_path` to `None` and `_write_redis_marker` to an `AsyncMock` and asserts
   `_set_bot_commands` was awaited once with the bot kwarg — order-independent.
   `TestOnStartup` and `TestSetBotCommands` are unaffected.

**File surface (semantic units).**
- `src/telegram_bot/lifecycle.py` → `_on_startup()`; `_set_bot_commands()` (or a new
  wrapper providing the budget); a new module-level budget constant; module-level
  `import asyncio`.
- `src/telegram_bot/tests/test_lifecycle.py` → `TestOnStartupCommands`; a new class or
  test for the budget.

**Tests required.**
- *Must keep passing unchanged:* all of `src/telegram_bot/tests/test_lifecycle.py`.
- *Must be added:* **the marker exists even when command registration hangs.** Make
  `_set_bot_commands` await an event that never fires, assert both markers are already
  written, and assert the hook returns within the budget rather than hanging.
- *Gate:* `$dc run --rm -e PYTEST_OPTS="src/telegram_bot/tests/test_lifecycle.py" test`
  then `.\Makefile.ps1 test`.

**Risk / rollback.**
- *Risk:* a hanging `set_my_commands` now burns the budget on every startup. Acceptable
  and bounded; it is fail-open by design.
- *Risk:* the swallowed timeout masking a genuinely broken registration path. The
  existing `test_set_commands_fail_open` still covers the per-scope error path.
- *Rollback:* revert the reorder. The failure mode is "readiness takes up to ~120 s
  again" — the pre-fix behaviour.

---

### BLOCK 5 — Test-bootstrap containment and the `entrypoint-test.sh` header

| | |
|---|---|
| **Findings owned** | `ENT-008` (both halves), `ENT-014` (comment-only, same file) |
| **`depends_on`** | *(none)* |
| **Priority** | P2 |
| **Roster** | **Implementor, Auditor, Planner, Validator** → *all four* |

**Agent requirement decision (the "high risk ⇒ all agents" rule applies here).**
The report designates this the phase's **fragile insertion point**, and its failure
mode is *silently green with a broken schema* — the worst kind. That justifies the
full roster:

- **Implementor — yes.** Always.
- **Auditor — yes.** The Auditor must establish, before any code is written, whether
  **anything at all** reads the non-test `mko_bazuna` database, and exactly what the
  `conftest.py` autouse `_restore_test_schema_post_db_setup` fixture provides versus
  what the entrypoint step provides. The report asserts the damage is contained; that
  assertion must be re-verified against the tree at `8060fcf`, not inherited.
- **Researcher — no.** There is no external best-practice question; the two end states
  are both project-internal options already named in the report.
- **Planner — yes.** Two viable end states, and an internal ordering constraint
  (`|| true` must not be removed before the step is repointed or dropped, or the
  container fails on every run). Sequencing a fail-open → fail-closed transition
  correctly is a design task.
- **Validator — yes.** `.\Makefile.ps1 test` is the only gate, and the Validator must
  run it **after** `|| true` is gone — i.e. in the state where a real DDL failure is
  visible. A run before that point proves nothing.

**3.2 — The end-state choice (Planner owns it; this plan does not pre-empt).**

| Option | Change | Pro | Con |
|---|---|---|---|
| **A (recommended)** | **Drop the `bootstrap_reference_data` step** from `entrypoint-test.sh` and let the `conftest.py` autouse fixture own the bootstrap. | The fixture already bootstraps `test_mko_bazuna` under `AdvisoryLockId.TEST_SCHEMA_SETUP`; the step's only effect today is on a database nothing reads. Removes both problems at once. | Must confirm nothing in the CI `test` job depends on the step having run. **Note:** the CI `test` job runs `bootstrap_reference_data` as its **own** step, independent of `entrypoint-test.sh` — so CI is unaffected either way, but this must be verified, not assumed. |
| **B** | **Repoint** the step at the test database under lock 111. | Preserves the entrypoint step's intent. | It is a *step whose stated purpose (populating the DB tests use) is already met by the fixture*; keeping it duplicates the bootstrap in two places, and the report's own note is that `bootstrap_reference_data` "spawns subprocesses that would connect to the hardcoded `mko_bazuna` database rather than pytest-django's test database" — i.e. repointing fights the command's own design. |

Either way, `|| true` is removed **last**, never first.

**Findings and notes carried forward.**
1. **The chain, verified:** `config/settings/test.py` pins
   `DATABASES["default"]["NAME"] = "mko_bazuna"` and sets
   `MIGRATION_MODULES = DisableMigrations()`; `docker/entrypoint-test.sh` runs
   `bootstrap_reference_data || true`; that command delegates to
   `migrate_locked.main()`, which spawns `manage.py migrate --noinput --run-syncdb`
   as a **subprocess** that inherits the same settings and therefore targets
   `mko_bazuna` with migrations disabled — pure syncdb. The command's own docstring
   documents this hazard and explains why `conftest.py` avoids it.
2. **Live confirmation from the report:** the non-test database holds 39 tables and
   **no** `django_migrations` table.
3. **Containment claim to re-verify (Auditor):** pytest uses `test_mko_bazuna`, whose
   triggers and currency rows `conftest.py` bootstraps itself under
   `AdvisoryLockId.TEST_SCHEMA_SETUP`; and no documented command (`make test`,
   `make test-db`, `make test-recreate`) starts any service that reads `mko_bazuna`.
4. **Internal ordering (fragile insertion point).** The correct sequence is:
   (a) repoint-or-drop the step; (b) run the suite; (c) **then** remove `|| true`;
   (d) run the suite again. Removing `|| true` first makes the step fail the container
   on every run and breaks every test at once.
5. **`ENT-014` — comment-only, same file, same change.** The header currently claims
   the base entrypoint "already waits for the DB, **runs migrations**, and compiles
   translations". `docker/entrypoint.sh`'s executed path is
   `check_env_file` → `fix_volume_permissions` → `wait_for_db` → `wait_for_redis` →
   `compile_messages` → `deploy_check` → `exec "$@"`. **There is no migration step.**
   Migrations come from the explicit `bootstrap_reference_data` call. Rewrite the
   comment to list what the base entrypoint actually does and to state that this script
   performs the reference-data bootstrap itself. **Do not remove the explicit call** —
   that would cost the suite its search triggers and exchange rates.
6. **If Option A is chosen, the comment must be updated as part of the same edit** so
   it does not describe a step that no longer exists. This is the strongest argument
   for landing `ENT-014` and `ENT-008` together, as this block does.

**File surface (semantic units).**
- `docker/entrypoint-test.sh` → the `bootstrap_reference_data` invocation line and its
  comment block; the header comment block.
- `src/backend/apps/core/management/commands/bootstrap_reference_data.py` → **read
  only**; its docstring is the authoritative explanation of the hazard and should not
  be edited.
- `src/backend/conftest.py` → **read only** (fixture `_restore_test_schema_post_db_setup`);
  consulted by the Auditor and Planner, not modified.
- `src/backend/apps/core/tests/test_bootstrap_reference_data.py` → read only, must
  keep passing.
- `src/backend/apps/core/tests/test_docs_ci_parity.py` → read only; it asserts
  `--reuse-db`, `--dist loadgroup` and `--maxprocesses` in the default `PYTEST_OPTS`
  of this same file. If the `bootstrap_reference_data` line is removed, none of those
  assertions are affected — but confirm.
- **Option B only:** a new way to point the command at `test_mko_bazuna`, which
  almost certainly means a new settings module or an explicit database override for
  the subprocess. The Planner must scope this before choosing.

**Tests required.**
- *Must keep passing unchanged:* `src/backend/apps/core/tests/test_bootstrap_reference_data.py`;
  `src/backend/tests/test_docs_ci_parity.py`; the full suite.
- *Must be added/changed:* none required by the finding. The correct verification is
  the **gate itself**, run twice.
- *Verification beyond the suite (Validator):* after the change, the non-test
  `mko_bazuna` database must **not** gain a new 39-table migration-less schema on a
  test run. Confirm with
  `docker exec mko-bazuna-test-db-1 psql -U postgres -d mko_bazuna -tAc "SELECT to_regclass('public.django_migrations');"`
  before and after.
- *Gate:* `.\Makefile.ps1 test` — run **twice**, once after the repoint/drop and once
  after `|| true` is removed. If any step failed, use `.\Makefile.ps1 test-recreate`.

**Risk / rollback.**
- *Risk (fragile insertion point):* removing `|| true` before repointing or dropping
  the step. The container then fails on every run and the whole suite goes red for a
  reason unrelated to the change. Sequence is mandatory.
- *Risk:* dropping the step when the CI `test` job actually depends on it. The CI job
  has its own `bootstrap_reference_data` step, so it should be independent — the
  Auditor verifies this before Option A is committed to.
- *Risk:* a stale `mko_bazuna` database in an existing test volume masks the fix. The
  before/after `to_regclass` check is the control.
- *Rollback:* restore the single line and re-add `|| true`. Fully reversible; no
  schema, no code, no contract.

---

### BLOCK 6 — Durable daily marker and idempotent `send_alerts` delivery

| | |
|---|---|
| **Findings owned** | `ENT-003` |
| **`depends_on`** | **BLOCK 3** |
| **Priority** | P1 |
| **Roster** | **Implementor, Auditor, Planner, Researcher, Validator** → *all five* |

> Only Implementor is ever concurrent, and there is only one Implementor. The other
> four agents run as analysis/review passes inside this block.

**Agent requirement decision (the "high risk ⇒ all agents" rule applies here).**
This is the phase's **only unsafe ordering**, it is HIGH, and it may require a schema
migration.

- **Implementor — yes.** Always.
- **Auditor — yes.** The exact duplication surface is not settled by the report and
  determines what "idempotent" even means. Specifically: what `SavedSearchNotification`
  already dedupes, whether `AnalyticsEvent` can take a uniqueness constraint **without
  affecting writers other than `send_alerts`** (it is a general-purpose event table
  written by many call sites and has **no** constraint today — a naive
  `UniqueConstraint` would break other writers), and what
  `apps/search/services/alert_query.py`'s `find_matching_ads` already excludes.
- **Researcher — yes.** The **marker substrate is an explicitly open choice** with two
  accepted answers and a schema consequence. See §3.3.
- **Planner — yes.** New persistence (possibly a new model and
  `apps/core/migrations/0005_*`), a changed delivery contract, and a mandatory coupled
  landing. This is the definition of "detailed pre-implementation design,
  architecture, testing".
- **Validator — yes.** HIGH; the finding's own Rollout Safety row names it the unsafe
  ordering; and the fix is **not** verifiable by any single test.

**3.3 — The marker substrate (open choice; recommendation with rationale, not a
decision).**

The report explicitly accepts **both** of these. The Planner and Researcher must
choose; this plan records the trade-off and a recommendation, and does not decide.

| Option | Change | Migration | Testability | Notes |
|---|---|---|---|---|
| **A** | A new Django model recording the last successful daily dispatch, in `apps/core` (next migration number `0005_*`). | **Yes** — required (project rule 13). | Fully testable under the real `test_mko_bazuna`. Survives Redis eviction and restart. Matches the "no process-local state assumed" taxonomy the finding is filed under. | Adds a table and a model; must be registered in `apps/core/migrations/`; must be covered by `test_migrations.py`-style checks if the project has any. **Migration number is shared with phase 03 — see §5.5.** |
| **B (recommended)** | A Redis key holding the last successful daily dispatch date, with a TTL **greater than 24 h** (the report's "one sweep interval" reasoning applies here too). | **No** — zero-migration. | **Caveat the Planner must design around:** `config/settings/test.py` overrides `CACHES` to `LocMemCache`, and the scheduler process and the test process are not the same process in production but *are* the same process in unit tests. So a Redis-backed marker is testable only as in-process cache behaviour, **not** as cross-process durability. Any test that claims to prove durability would be lying. | Redis is already a hard dependency of both long-lived processes (bot FSM storage, shared cache, rate limits). No new infrastructure. The `<=24 h TTL` must exceed the daily interval with margin or a slow day can re-fire. |

**Recommendation:** Option B, because it is zero-migration and the infrastructure
already exists, **provided** the Planner can write honest tests (in-process cache
behaviour plus an explicit TTL assertion) and can state the durability limitation
rather than hide it. Choose Option A if the Planner judges that a dedupe guarantee
which evaporates on Redis eviction is not acceptable for a user-visible digest.

**Findings and notes carried forward.**
1. **The unsafe ordering is real and is the block's defining constraint:** the durable
   marker and the idempotent `send_alerts` delivery **must land together**.
   Recording the marker first would only persist the fact that a run happened whose
   delivery was still duplicated. Neither half may be a separate commit that is
   meaningful on its own.
2. **The full chain, verified:** `run_scheduler` holds `last_daily: date | None` in
   memory, re-initialised every process start; `should_run_daily` returns `True` for
   any fresh process whose hour is `>= DAILY_HOUR_UTC`; `send_alerts` is in
   `DAILY_COMMANDS`; `AnalyticsEvent.objects.bulk_create(analytics_events)` runs with
   **no** `ignore_conflicts`, while the `SavedSearchNotification` insert on the
   adjacent line correctly passes `ignore_conflicts=True`; `AnalyticsEvent.Meta` has
   no unique constraint, so a second run inserts a second `SEARCH_ALERT_MATCHED` row
   per saved search; and delivery happens **outside** the advisory lock and **outside**
   the transaction, with `_collect_alerts` re-collecting matching ads without
   excluding already-notified ones.
3. **Scope boundary — `rollup_daily_metrics` is not the concern.** It is idempotent by
   construction (`update_or_create` keyed on yesterday). Do not modify it.
4. **Hard boundary from phase 03 `DB-007`:** `deliver_immediate_alerts`
   (`apps/search/services/immediate_alerts.py`) takes **no** advisory lock and is
   fired from an `Ad.post_save` signal via `transaction.on_commit`. This block must
   **not** add `AdvisoryLockId.ALERT_DELIVERY_TASK` to the immediate path and must
   **not** modify `immediate_alerts.py` at all. See §5.3 for the schema-collision
   hazard.
5. **Hard boundary from phase 10 / the Auditor's blast-radius check:** do **not** add a
   uniqueness constraint to `analytics_events` unless the Auditor confirms the only
   writer affected is `send_alerts`. `AnalyticsEvent` is written from many call sites
   (`record_event` in `apps/core/services/analytics.py` and others).
6. **`_shutdown()` and the loop's `last_daily` bookkeeping belong to this block** once
   the marker moves out of process memory — that is the part BLOCK 3 deliberately did
   not touch.
7. **No new `AdvisoryLockId` unless the chosen design genuinely needs one.** If one is
   needed, the value must come from the free range and the enum's docstring table in
   `apps/core/utils/advisory_lock.py` **and** `apps/core/enums.py` must both be updated
   in the same change (the enum is the allocation record). `AdvisoryLockId` is a shared
   artefact with other phases — see §5.5.

**File surface (semantic units).**
- `src/backend/apps/core/utils/scheduler.py` → `run_scheduler()` (the `last_daily`
  in-memory variable), `run_one_cycle()` (the daily-firing branch and the value
  returned), `should_run_daily()` (**signature may change** if the marker becomes a
  timestamp rather than a `date` — this is the public seam and every caller and test
  must be updated together).
- **Option A only:** a new model in `src/backend/apps/core/models.py` and a new
  migration in `src/backend/apps/core/migrations/` (next number `0005_*`).
- `src/backend/apps/search/management/commands/send_alerts.py` →
  `Command.handle()`, `Command._collect_alerts()`, `Command._persist_alerts()`.
- **New (either option):** the durable marker's read/write helper. Follow the
  `services/` convention: `src/backend/apps/core/services/` (a cross-app read/write
  marker) or `src/backend/apps/search/services/` (if it is alert-specific). The
  Planner picks; the project has a `services/` package in every app and this must not
  be a third option.
- `src/backend/apps/core/enums.py` → `AdvisoryLockId` **only** if required.
- `src/backend/apps/core/tests/test_scheduler.py` → `TestShouldRunDaily`,
  `TestRunOneCycle`, `TestRunScheduler` (all construct or assert on `last_daily`).
- `src/backend/apps/search/tests/test_send_alerts.py` → the delivery-idempotency tests.
- **Not touched:** `apps/search/services/immediate_alerts.py`,
  `apps/analytics/management/commands/rollup_daily_metrics.py`,
  `apps/search/services/alert_query.py`'s matching semantics.

**Tests required.**
- *Must keep passing unchanged* (signature-sensitive — the Auditor/Planner must update
  them if `should_run_daily`'s contract changes, but the **behaviours** they assert
  must survive): `TestShouldRunDaily` (all ten cases — the threshold semantics are
  correct today and must not regress), `TestRunOneCycle` (dispatch counts and
  `last_daily` return values), `TestRunScheduler`, and
  `src/backend/apps/core/tests/test_scheduler_error_handling.py` in full
  (`TestRunCommandLogging`, `TestTimeoutHandling`, `TestDispatchIsolation`,
  `TestCycleErrorIsolation`, `TestWriteLivenessMarker`,
  `TestLivenessMarkerIntegration`).
- *Must be added:*
  - A **second-run** test: with the durable marker already written for today, the
    daily commands are **not** dispatched. This is the actual defect.
  - A **fresh-process** test: the marker persists across a `run_scheduler`
    restart-in-process, proving the state is no longer process-local.
  - **Idempotency of `send_alerts`:** run the command twice against unchanged data and
    assert no duplicate user-visible digest and no duplicate analytics rows.
  - **Option B only:** an explicit assertion on the marker's TTL, and a docstring
    stating the durability limitation honestly. Do not write a test that claims
    cross-process durability under `LocMemCache`.
- *Gate:* `$dc run --rm -e PYTEST_OPTS="src/backend/apps/core/tests/test_scheduler.py src/backend/apps/core/tests/test_scheduler_error_handling.py src/backend/apps/search/tests/test_send_alerts.py" test`
  then `.\Makefile.ps1 test`, and — if Option A — `.\Makefile.ps1 test-recreate`
  first, because a new migration requires a fresh schema.

**Risk / rollback.**
- *Risk (unsafe ordering):* the marker landing without the idempotent delivery, or vice
  versa. Both are wrong states; neither is an improvement. Ship as one change.
- *Risk (silent regression):* a durable marker whose TTL is too short, or a marker
  written **before** delivery completes, re-fires the daily set — reproducing the
  original defect in a new shape. Write the marker only on a clean, successful run.
- *Risk (schema blast radius):* a uniqueness constraint on `analytics_events` breaking
  an unrelated writer. Audit first.
- *Risk (migration number collision):* `apps/core/migrations/0005_*` may be claimed by
  a phase-03 plan landing earlier. See §5.5.
- *Rollback:* the marker artefact and the `ignore_conflicts` change are separately
  revertible, but **rolling back only one of them restores the original defect** —
  they must be reverted together or not at all. The migration is revertible if it has
  not been applied in any environment that matters.

---

### BLOCK 7 — Scheduler liveness semantics ("alive" vs. "succeeded")

| | |
|---|---|
| **Findings owned** | `ENT-013` |
| **`depends_on`** | **BLOCK 3**, **BLOCK 6** |
| **Priority** | P2 |
| **Roster** | **Implementor, Planner, Validator** |

**Agent requirement decision.**
- **Implementor — yes.** Always.
- **Auditor — no.** The call site, the failure-propagation path and the existing tests
  are all identified.
- **Researcher — no.** Dropped deliberately: the healthcheck budget could be framed as
  an operational-calibration question, but the calibration input is already in the
  repo (`SCHEDULE_INTERVAL_SECONDS`, the nine-command cycle, and the production
  `SCHEDULER_HEALTH_STALE_SECONDS=7200`). That is a derivation the Planner performs, not
  a research question.
- **Planner — yes.** The fix changes what the marker *means*, and the report offers two
  different mechanisms with different observability properties. Choosing requires
  design, and the same decision interacts with BLOCK 6's clean-run semantics.
- **Validator — yes.** A **currently-green test asserts the defective behaviour**. An
  independent reviewer must confirm the inversion is *correct*, not merely convenient.

**Findings and notes carried forward.**
1. **A green test asserts the defect and must be inverted in the same change.**
   `src/backend/apps/core/tests/test_scheduler_error_handling.py` contains
   `TestLivenessMarkerIntegration::test_marker_written_even_when_hourly_command_fails`,
   which asserts the marker is written even when an hourly command fails. Its docstring
   states the current behaviour is intentional. Per project rule 2 (production code is
   king), the **test is wrong and must be inverted**, not the production code bent to
   satisfy it.
2. **Correction to the report's Rollout Safety row.** The report says to "extend
   `test_scheduler_wiring.py` to assert the marker is not refreshed after a failed
   cycle". That is the **wrong file**: `test_scheduler_wiring.py` is a static
   configuration test that reads `docker/entrypoint-scheduler.sh` as text and imports
   nothing from the scheduler. The marker-behaviour assertion belongs in
   `test_scheduler_error_handling.py`, which already owns `TestWriteLivenessMarker` and
   `TestLivenessMarkerIntegration`. **Follow the file's responsibility, not the
   report's file name.**
3. **Why the marker cannot be a health signal today:** `_write_liveness_marker()` is
   called unconditionally after the nine-command hourly loop; per-command failures
   never propagate (`_dispatch` returns `1` on exception and `run_one_cycle` discards
   the return values); and cycle-level exceptions are swallowed with
   "Scheduler cycle failed — continuing". The 7200 s staleness check therefore catches
   a **stuck** loop, not a **failing** one.
4. **The two mechanisms the report offers (Planner decides):**
   - (a) write the marker only after a cycle in which no command returned non-zero;
   - (b) keep the always-refreshed marker and record the last successful cycle
     separately, reading that instead.
   Option (a) is simpler and is what the report lists first; option (b) is more
   informative (it distinguishes "failing" from "stalled" without making a stuck loop
   look like a failing one — under (a) a loop that never completes a cycle never
   refreshes either, which is arguably correct but conflates the two). The Planner must
   state the choice and its observability consequences.
5. **Note the interaction with `run_scheduler`'s stop path.** Under option (a) with
   the stop flag set, a deliberately-skipped or aborted final cycle must not be
   recorded as a failure. The Planner must confirm the interaction with BLOCK 3's
   bounded-wait design.
6. **The second half: raise the scheduler healthcheck `start_period`.** The first marker
   cannot appear until a full nine-command cycle completes, but the healthcheck allows
   only `start_period: 30s` + 3 × `interval: 30s`. A legitimately slow first cycle (a
   large `consent_hard_delete`, a `sweep_orphaned_media` over a large `MEDIA_ROOT`)
   can mark a healthy container `unhealthy`. Raise `start_period` in
   `docker-compose.prod.yml`'s `scheduler` block to cover one full cycle. Derive the
   value from `SCHEDULE_INTERVAL_SECONDS` and the worst-case cycle duration and state
   the derivation.
7. **Tests that must keep passing** (all use a no-op command returning 0, so all nine
   commands succeed and the marker is still written exactly once):
   `test_hourly_cycle_writes_marker`, `test_daily_cycle_does_not_write_marker`
   (asserts the marker is called exactly once per cycle), and
   `TestWriteLivenessMarker` (fail-open behaviour, empty path no-op, `OSError`
   tolerance). **The fail-open contract must not change** — the scheduler must never
   crash on a healthcheck concern.

**File surface (semantic units).**
- `src/backend/apps/core/utils/scheduler.py` → `run_one_cycle()` (aggregate command
  results, gate the marker), `_write_liveness_marker()` (signature only if the Planner
  must pass outcome information).
- `src/backend/apps/core/tests/test_scheduler_error_handling.py` →
  `TestLivenessMarkerIntegration` (invert the failing-command test; keep the other
  three).
- `docker-compose.prod.yml` → `services.scheduler.healthcheck.start_period`.
- **Not touched:** `test_scheduler_wiring.py`; `docker/healthcheck-scheduler.sh`
  (its staleness logic already keys off the marker's mtime, which is exactly what
  option (a) preserves — the Planner must confirm whether the script needs a comment
  update to reflect the marker's narrowed meaning).

**Tests required.**
- *Must keep passing unchanged:* the three liveness tests named above; all of
  `test_scheduler.py`.
- *Must be changed:* `test_marker_written_even_when_hourly_command_fails` — **inverted**
  to assert the marker is **not** refreshed when a command fails. Rename it to describe
  the new contract.
- *Must be added:* a case where a **daily** command returns non-zero, and a case where
  a cycle raises (the swallow path), to pin both failure modes.
- *Need no test:* the `start_period` value — it is a compose value (pure plumbing).
  `test_scheduler_compose_has_healthcheck` and
  `test_scheduler_compose_has_stale_seconds` in `test_health_contract.py` must keep
  passing untouched.
- *Gate:* `$dc run --rm -e PYTEST_OPTS="src/backend/apps/core/tests/test_scheduler_error_handling.py src/backend/apps/core/tests/test_scheduler.py src/backend/apps/core/tests/test_health_contract.py" test`
  then `.\Makefile.ps1 test`.

**Risk / rollback.**
- *Risk:* a persistently failing command turns the scheduler `unhealthy`, and Docker's
  restart policy restarts it — converting a quiet failure into a crash loop. This is
  the intended direction (a failing scheduler *should* be visible) but the Planner must
  state the escalation explicitly so the team is not surprised.
- *Risk:* "invert the test" being read as "make the test pass somehow". The inversion
  must be a genuine contract change with the production code changed to match.
- *Rollback:* revert `run_one_cycle` and the test inversion together. The
  `start_period` bump is independently revertible and harmless either way.

---

### BLOCK 8 — Migration-lock acquisition diagnostics (ENT-006 residual)

| | |
|---|---|
| **Findings owned** | `ENT-006` — **residual elements (a) and (b) only** |
| **`depends_on`** | *(none)* — sequenced after BLOCK 1 for gate coverage |
| **Priority** | P2 |
| **Roster** | **Implementor** |

**Agent requirement decision.**
- **Implementor — yes.** Always.
- **Auditor — no.** Both residual elements are named with exact locations.
- **Researcher — no.** No external question.
- **Planner — no.** Two small, explicitly specified edits. The report even tells the
  implementor what the alternatives are.
- **Validator — no.** The change is a docstring and one log line. The surrounding
  behaviour is covered by existing tests, and **neither existing test is affected**:
  `test_advisory_lock_release_log.py` covers the **transaction** branch, and
  `test_migrate_locked.py` covers `_build_steps` and the subprocess timeout path.
  The plan-level DoD gate (§8) provides the cross-block review.

**Findings and notes carried forward — and the boundaries that matter more than the
change.**
1. **Element (a) — docstring vs. implementation.** `apps/core/utils/migrate_locked.py`'s
   module docstring claims *"Idempotent: subsequent runs will find lock already held
   and **skip**."* The implementation calls `advisory_lock(AdvisoryLockId.MIGRATE,
   session=True)`, which issues the **blocking** `pg_advisory_lock`. It never skips.
   Decide the documented intent and make the docstring match. Because this block
   deliberately does **not** introduce a timeout (DB-004 owns that), the honest
   documentation today is: *a contending run **blocks** until the lock is granted*,
   and the log now says so before it happens.
2. **Element (b) — silent wait.** The only acquisition line,
   `logger.info("Acquired session advisory lock %s", lock_id)`, fires **after** the
   lock is granted. A blocked run therefore emits **nothing at all** and the operator
   sees a silent hang, not even a "waiting" message. Add a line **before** the
   acquisition statement.
3. **Boundary — DB-004 (acquisition timeout).** Do **not** add `lock_timeout` or
   `statement_timeout` to `advisory_lock.py`, to `advisory_lock`'s call sites, or to
   `config/settings/base.py`'s `DATABASES["default"]["OPTIONS"]`. Phase 03's `DB-004`
   (HIGH) owns the whole timeout remediation. Shipping it here would duplicate it.
4. **Boundary — DB-010 (release log).** Do **not** touch the **transaction-scoped**
   branch's `transaction.on_commit` release callback. That is DB-010's finding, which
   requires wrapping the body in `try/finally` instead. These are **two different log
   lines at two different points**: this block is the *acquisition* side, DB-010 is the
   *release* side. `test_advisory_lock_release_log.py` asserts the current `on_commit`
   registration and **must keep passing unchanged** — it is the tripwire that proves
   this block did not overreach.
5. **Where to put the pre-acquisition line — implementer's choice, with a
   recommendation.** Putting it inside the `if session:` branch touches the least code
   and keeps the transaction branch (which the existing test covers) completely
   untouched, minimising merge friction with phase 03's `DB-004`, which will likely
   rework this function. Putting it before the branch is more useful for both lock
   kinds. **Recommend the session branch only**, for merge-friction reasons, and record
   the trade-off in the code comment.
6. **A second, arguably wrong claim.** The `migrate` service comment in
   `docker-compose.yml` says *"Idempotent: advisory lock prevents concurrent runs"*. The
   lock **serialises** concurrent runs; it does not make them no-ops. This is adjacent
   to element (a) and the implementor should fix it in the same pass **if** the wording
   change stays strictly descriptive. Do not restructure the Compose service.
7. **The change must be visibly separable from DB-004's two addendum elements.** Phase
   03 recorded (a) and (b) as a "scoped addendum" it expects to be delivered together
   with its own timeout work. Phase 01 delivers the two log/doc edits now. **Two edits,
   one work item, two phases** — the implementor must not reword them in a way that
   contradicts DB-004's future `lock_timeout` message.
8. **`SCHEDULER_COMMAND_TIMEOUT` bounds the child `manage.py` invocations, not the
   wait for the lock.** Do not conflate them in the docstring.

**File surface (semantic units).**
- `src/backend/apps/core/utils/migrate_locked.py` → module docstring (element a).
- `src/backend/apps/core/utils/advisory_lock.py` → `advisory_lock()`, the
  **session-scoped** branch only (element b).
- `docker-compose.yml` → `services.migrate` trailing comment (optional, see note 6).
- `src/backend/apps/core/tests/test_migrate_locked.py` → new test for element (b).

**Tests required.**
- *Must keep passing unchanged:* `src/backend/apps/core/tests/test_advisory_lock_release_log.py`
  **in full** (both tests — the tripwire against touching DB-010's line);
  `src/backend/apps/core/tests/test_migrate_locked.py`
  (`TestBuildStepsDefault`, `TestBuildStepsEnvGated`, `TestMainTimeout`,
  `TestDefaultSettings`); `src/backend/apps/core/tests/test_advisory_lock_ids.py`.
- *Must be added:* **one** test asserting a "waiting / acquiring" INFO line is emitted
  **before** the acquisition statement executes. Construct it so the assertion would
  fail against the current code — e.g. patch the cursor so the acquire call raises or
  blocks, and assert the line is already in the log. This tests the finding's substance
  (no more silent hang), not an implementation detail.
- *Explicitly NOT required:* a contention test asserting a **bounded** wait. That is
  DB-004's test, and writing it here would pre-empt DB-004's design.
- *Gate:* `$dc run --rm -e PYTEST_OPTS="src/backend/apps/core/tests/test_migrate_locked.py src/backend/apps/core/tests/test_advisory_lock_release_log.py src/backend/apps/core/tests/test_advisory_lock_ids.py" test`
  then `.\Makefile.ps1 test`.

**Risk / rollback.**
- *Risk:* accidentally modifying the transaction branch, which breaks
  `test_advisory_lock_release_log.py` and re-opens DB-010. The unchanged test is the
  guard.
- *Risk:* wording the new log line as a "timeout" or "retry" promise, which DB-004 has
  not yet implemented. The message must describe what the code does today.
- *Rollback:* two log/doc edits; fully reversible, no behaviour change.

---

### BLOCK 9 — Bot per-update `User` memoisation (ENT-010, Half A only)

| | |
|---|---|
| **Findings owned** | `ENT-010` — **Half A only** |
| **`depends_on`** | **BLOCK 1** |
| **Priority** | P2 |
| **Roster** | **Implementor, Auditor, Planner, Validator** |

**Agent requirement decision.**
- **Implementor — yes.** Always.
- **Auditor — yes.** Every consumer of the resolved user must be enumerated before the
  memo is introduced, and the **column mismatch** must be mapped. Missing one consumer
  means either a redundant lookup survives (the finding is not fixed) or a lookup is
  skipped (a behaviour regression). This is cheap to check and expensive to get wrong.
- **Researcher — no.** The remedy is prescribed; there is no external question.
- **Planner — yes.** The design is genuinely open: who owns the cache key, what
  sentinel represents "not registered", and what the cross-middleware ordering
  guarantees are. Getting this wrong changes bot auth behaviour.
- **Validator — yes.** The refactor sits directly on the bot's account-state gate; a
  memoisation bug can let a banned or withdrawn user through, or block a legitimate
  one. User-visible security behaviour deserves independent confirmation.

**Findings and notes carried forward.**
1. **Middleware order is fixed and load-bearing:** `DatabaseConnectionMiddleware`
   (outer) → `UpdateIdDedupMiddleware` → `LivenessMiddleware` → `LanguageMiddleware` →
   `AccountStateMiddleware` (innermost update middleware). `LanguageMiddleware` **must**
   remain before `AccountStateMiddleware` so denial messages render in the user's
   locale.
2. **The lookups to be eliminated.** Today, before any handler runs:
   - `update_id_dedup` → `cache.add`;
   - `lifecycle.LivenessMiddleware` → `os.utime` + `cache.set`;
   - `language.py` → `User.objects.filter(telegram_id=…).values_list(…).first()` plus
     a cache read;
   - `permissions.py` → `User.objects.get(chat_id=…)` in `_check_user_state` (every
     update);
   - `permissions.py` → the same lookup in `_check_publish_permission` (`/post` only);
   - `permissions.py` → the same lookup in the FSM `user_id` backfill (only when the
     FSM data lacks `user_id`).
   `_get_user` is a bare `@sync_to_async` with **no** memoisation, and none of the four
   share a result.
3. **The column mismatch — the Planner must resolve this explicitly.**
   `language.py` keys on **`telegram_id`**; `permissions.py` keys on **`chat_id`**.
   The two differ for withdrawn users, whose `telegram_id` is nulled while `chat_id` is
   stable — which is precisely why `AccountStateMiddleware` uses `chat_id`. A shared
   memo must be keyed on the **stable** column. Whether `language.py` may then read
   `user.telegram_language` from the same object is a **behaviour change** for
   withdrawn users (they would get their stored locale instead of falling through to
   the anon-language cache and then `settings.LANGUAGE_CODE`). The Planner must decide
   whether to take that improvement or preserve the current fallback, and state which.
   **Default to preserving current behaviour**: the finding is a performance
   clean-up, not a semantic change.
4. **The "user not found must not become an error" tolerance is load-bearing.** Both
   `_check_user_state` and `_check_publish_permission` catch `User.DoesNotExist` and
   return `(True, "")`; the FSM backfill catches it and passes, deferring to the
   handler's auth gate. A memo must represent "not registered" as a distinct,
   non-exceptional state, and each call site must keep its existing tolerance. Do not
   let the memo turn `DoesNotExist` into a raised error.
5. **Scope the memo to one update.** Store the result in the aiogram `data` dict that
   already threads through the middleware chain. **Do not** introduce a module-level
   or cross-update cache — that would leak one user's identity into another update.
6. **The events that bypass the lookups** must be preserved: a non-`Update` event, an
   event with no message, an event with no `from_user`, and a `callback_query` whose
   acting user is `callback_query.from_user` rather than `message.from_user`. The memo
   key must therefore be resolved from the **acting user id**, not from
   `message.from_user.id`.
7. **Forbidden in this block:** `CONN_MAX_AGE`, `DatabaseConnectionMiddleware`, and the
   per-update `close_old_connections` call. `CONN_MAX_AGE = 0` carries the comment
   *"PgBouncer async safety (zone C5)"* and the middleware's docstring explains in
   detail that it deliberately mirrors the HTTP `request_finished` hook. This is
   documented intentional design; revisiting it is a phase-13 question.
8. **Existing test files that own this behaviour:**
   `src/telegram_bot/tests/test_account_state_middleware.py`,
   `test_db_connection_middleware.py`, `test_main.py` (dispatcher wiring),
   `test_language.py`, `test_multi_lang_translation.py`, `test_ad_data_locale.py`.

**File surface (semantic units).**
- `src/telegram_bot/middlewares/permissions.py` → `AccountStateMiddleware.__call__()`,
  `_check_user_state()`, `_check_publish_permission()`, `_get_user()`.
- `src/telegram_bot/middlewares/language.py` → `LanguageMiddleware.__call__()`,
  `_resolve_user_language()`.
- **New (recommended):** a small shared resolver in
  `src/telegram_bot/middlewares/` (or `src/telegram_bot/services/`) so both
  middlewares agree on the key and the sentinel. Follow the project's
  services-per-app convention; do not create a new abstraction layer for two callers
  if a shared helper in the existing `middlewares` package suffices.
- `src/telegram_bot/tests/test_account_state_middleware.py`,
  `src/telegram_bot/tests/test_language.py` → extended.

**Tests required.**
- *Must keep passing unchanged:* `test_account_state_middleware.py`,
  `test_db_connection_middleware.py`, `test_main.py`, `test_language.py`,
  `test_multi_lang_translation.py`.
- *Must be added:*
  - A **query-count** test per update shape, so the fan-out cannot silently regress.
    The report asks for exactly this and it is the real gate for the finding. Use
    `django_assert_num_queries` (or an equivalent counter) around one update of each
    shape: a plain message, a `/post` message, and a callback query.
  - A test that the **same resolved object** is used by all consumers within one update
    (proving the memo is shared, not merely duplicated).
  - A test that "user not registered" still passes through to the handler with the
    existing tolerance — no exception, no denial.
  - A test that two consecutive updates with different acting users do **not** share a
    memoised user.
- *Gate:* `$dc run --rm -e PYTEST_OPTS="src/telegram_bot/tests/test_account_state_middleware.py src/telegram_bot/tests/test_language.py src/telegram_bot/tests/test_db_connection_middleware.py" test`
  then `.\Makefile.ps1 test`.

**Risk / rollback.**
- *Risk:* a memo that survives across updates — a cross-user identity leak, the most
  serious failure mode in this block. The "two updates, two users" test is the
  specific guard.
- *Risk:* unifying the lookup keys silently changing locale behaviour for withdrawn
  users. Note 3 makes this an explicit decision, defaulted to no behaviour change.
- *Risk:* turning `User.DoesNotExist` into an error and breaking unregistered-user
  flows.
- *Rollback:* two middleware modules; revertible in isolation, and the current
  behaviour is the fallback.

---

### BLOCK 10 — `LoginToken` service owner and `consent.py` slimming

| | |
|---|---|
| **Findings owned** | `ENT-005` |
| **`depends_on`** | **BLOCK 1** |
| **Priority** | P2 (largest unit; execute last) |
| **Roster** | **Implementor, Auditor, Planner, Validator** |

**Agent requirement decision.**
- **Implementor — yes.** Always.
- **Auditor — yes.** Every `LoginToken` touch point must be mapped, and the full
  inventory of tests that must survive unchanged must be catalogued *before* the
  refactor. A miss silently breaks a two-phase login handshake that spans two
  processes.
- **Researcher — no.** `apps/users/services/login_rate_limit.py` is the in-repo
  precedent the report itself names, and the service layer already exists across
  almost every app. There is no external best-practice question.
- **Planner — yes.** This is the largest unit in the phase: a new service module with
  three operations, plus decomposing a 470-line view. "Detailed pre-implementation
  design, architecture, testing, or complex execution" is exactly this.
- **Validator — yes.** It rewrites a security-relevant two-phase protocol on both
  sides of two processes. The entire value of the finding is that the claim and
  consume predicates remain **deliberately different** and both **zero-TOCTOU**; that
  is precisely what an independent reviewer must confirm.

**Findings and notes carried forward.**
1. **The report's stated root cause is wrong, and the correction strengthens the case.**
   The report says there is no `apps.users.services` counterpart for the login
   handshake. In fact `src/backend/apps/users/services/` exists with `account_state.py`
   (holding `can_login`, the predicate `login_status` calls), `consent_record.py`,
   `deletion.py` (which deletes outstanding tokens on consent withdrawal) and
   **`login_rate_limit.py`** — the exact precedent for extracting `login_issue`'s logic
   out of the view. The service layer is already the established convention: 13 of the
   14 apps under `src/backend/apps/` ship a `services/` package (`cabinet` is the sole
   view-only exception). What is missing is **one module**, `login_token.py`.
2. **"The same rule twice" is a mischaracterisation, and the extraction must not
   collapse the two predicates.** They are two distinct operations of a two-phase
   protocol and their predicates legitimately differ:

   | | Bot (`telegram_bot/handlers/login.py`) | Web (`apps/users/views/consent.py`) |
   |---|---|---|
   | Operation | **claim** — sets `telegram_id` | **consume** — sets `consumed_at` |
   | Predicate | `telegram_id IS NULL AND consumed_at IS NULL AND expires_at > now` | `telegram_id = <observed> AND consumed_at IS NULL AND expires_at > now` |
   | Mechanism | `UPDATE … RETURNING` (row lock ⇒ zero TOCTOU) | conditional `.filter(…).update(…)` (row count ⇒ zero TOCTOU) |
   | Must it read first? | no | **yes** — it needs `token.telegram_id` to log in the right user |

   The only shared invariant is *"the token is still live"*
   (`consumed_at IS NULL AND expires_at > now`). Phase 04 independently rated the
   two-phase claim zero-TOCTOU and sound, so there is **no defect to fix here** — the
   value is structural. **Do not "unify" the predicates into one shared function**;
   that would destroy the correctness the audit confirmed.
3. **The bot side must be preserved byte-for-byte in behaviour.** `_claim_login_token`
   uses a raw `UPDATE … RETURNING` with `RETURNING` columns, and
   `TestConcurrentClaim` asserts its zero-TOCTOU semantics under real concurrency. The
   extraction must not weaken that. The raw SQL and its docstring are load-bearing.
4. **The bot's transaction must not be split.** `handle_login_orm` performs
   claim + get-or-create user + language reconciliation in a **single**
   `sync_to_async` call and a single `transaction.atomic()`, with a `SAVEPOINT`
   inner block for the `IntegrityError` race on `chat_id`. Moving `claim_token` into
   the new service must preserve the ability to keep that one transaction, and must
   preserve the "one `sync_to_async` call reduces DB connection churn with
   `CONN_MAX_AGE=0`" rationale.
5. **Target shape (from the report, subject to the Planner's decomposition):**
   `apps/users/services/login_token.py` exposing `issue_token()`,
   `claim_token(token_hash, telegram_id, now)` and
   `consume_token(token_hash, expected_telegram_id)` — one transaction each, each
   owning its own predicate, each using the ORM. Handlers become
   parse → delegate → respond. `consent.py` shrinks.
6. **What must move out of `consent.py`** per the report: token minting/hashing/rate
   limit application (into the service, delegating to the existing
   `login_rate_limit_check`), and the token claim/consume predicate. **What stays in
   the view:** HTTP concerns — status-code mapping (200 / 204 / 410), `auth_login`,
   `session` handling, and the response. `_reconcile_preferred_city_on_login` is a
   separate concern and may stay or move, at the Planner's discretion — but moving it
   is out of the finding's scope and should be justified if done.
7. **Cross-phase: `AUT-007` (VAL-002).** The same root cause — no service owning the
   `LoginToken` lifecycle — is filed as `AUT-007` in another phase, whose concrete
   instance is that `login_issue` never invalidates the browser's previous outstanding
   token. The report is explicit: the two findings are **retained and
   cross-referenced, not merged**, and *"the two findings must not be fixed by two
   separate ad-hoc patches."* **Constraint on this block: do not implement AUT-007's
   behaviour change here** (no invalidation of prior tokens) — but **do** structure
   `login_token.py` so that a lifecycle service *could* own it. State this boundary in
   the service module's docstring so the next phase does not add a second ad-hoc patch.
8. **Tests that must survive unchanged (both sides):**
   *Backend* — `src/backend/apps/users/tests/test_login.py`:
   `TestLoginIssue`, `TestLoginStatus`, `TestLoginTokenSecurity`,
   `TestLoginPreferredCitySync`, `TestAnonLanguageReconcile`, `TestLoginRateLimit`,
   `TestLoginRateLimitCheck`.
   *Bot* — `src/telegram_bot/tests/test_login.py`: `TestClaimLoginToken`,
   `TestTokenRejection`, `TestConcurrentClaim`, `TestAnonLanguageReconcile`,
   `TestLoginRateLimit`.
   *Also* — `src/backend/apps/users/tests/test_consent.py`,
   `test_deletion.py` (token cleanup on consent withdrawal),
   `test_login_issue_template.py`, and
   `src/backend/apps/core/tests/test_core_tags.py` if it touches login rendering.
9. **A test the report asks for and does not yet exist:** one asserting that claim and
   consume agree on their (deliberately different) predicates — specifically that a
   token claimed by a *different* `telegram_id` cannot be consumed by this browser, and
   that a consumed/expired token cannot be claimed. This is the direct regression guard
   for the extraction.

**File surface (semantic units).**
- **New:** `src/backend/apps/users/services/login_token.py` —
  `issue_token()`, `claim_token()`, `consume_token()`.
- `src/backend/apps/users/views/consent.py` → `login_issue()`, `login_status()`
  (and possibly `_reconcile_preferred_city_on_login()`).
- `src/telegram_bot/handlers/login.py` → `_claim_login_token()` (delegates to the
  service while preserving its zero-TOCTOU semantics), `handle_login_orm()`.
- **Not touched:** `apps/users/models.py` (`LoginToken` model shape), `urls.py`,
  templates, migrations.
- **Not touched:** `apps/users/services/deletion.py` — it is the *third* touch point
  the report names, but rewiring it is not required; the Planner should at minimum
  ensure the new service does not create a second, competing place that deletes
  outstanding tokens.

**Tests required.**
- *Must keep passing unchanged:* every suite listed in note 8 above, **particularly
  `TestConcurrentClaim`**, which is the tripwire for the bot's zero-TOCTOU guarantee.
- *Must be added:*
  - Unit tests for `issue_token()` / `claim_token()` / `consume_token()` in isolation
    (the report's third surviving point: the predicates are currently not
    independently unit-testable without HTTP and Telegram).
  - The cross-predicate agreement test in note 9.
  - A test that a claimed token is not consumable by a different `telegram_id`, and
    that a consumed token cannot be re-claimed.
- *Gate:* `$dc run --rm -e PYTEST_OPTS="src/backend/apps/users/tests/test_login.py src/backend/apps/users/tests/test_consent.py src/telegram_bot/tests/test_login.py" test`
  then `.\Makefile.ps1 test`.

**Risk / rollback.**
- *Risk (highest in this block):* collapsing the two predicates into one shared
  helper "for consistency", which would break the deliberate asymmetry and reintroduce
  a TOCTOU or a wrong-user login. The cross-predicate test is the guard.
- *Risk:* splitting `handle_login_orm`'s single transaction across an async boundary,
  which would silently weaken the `IntegrityError` race handling.
- *Risk:* the "slimming" half turning into a broad rewrite of `consent.py`. Constraint
  the diff to the token lifecycle; the consent-accept/decline/withdraw views are out of
  scope.
- *Risk:* phase 04's `AUT-007` landing a second ad-hoc token patch. The service module's
  docstring must state the boundary (note 7).
- *Rollback:* the service module can be deleted and both call sites restored. The view's
  HTTP behaviour is unchanged throughout, so rollback is safe at any point.

---

## 4. Dependency graph

### 4.1 Execution order

```
BLOCK 1  Static gate scope + green typecheck (ENT-004)          deps: —
    │      ──► gates BLOCK 9, BLOCK 10
    │
BLOCK 2  Compose environment contract (ENT-001/011/012)        deps: —
BLOCK 3  Scheduler graceful stop (ENT-002)                      deps: —
    │      ──► gates BLOCK 6, BLOCK 7
BLOCK 4  Bot lifecycle readiness ordering (ENT-007)             deps: —
BLOCK 5  Test-bootstrap containment (ENT-008 + ENT-014)         deps: —
    │
BLOCK 6  Durable daily marker + idempotent send_alerts (ENT-003) deps: BLOCK 3
    │      ──► gates BLOCK 7
BLOCK 7  Scheduler liveness semantics (ENT-013)                  deps: BLOCK 3, BLOCK 6
BLOCK 8  Migration-lock diagnostics (ENT-006 residual)          deps: —
BLOCK 9  Bot per-update user memoisation (ENT-010 Half A)        deps: BLOCK 1
BLOCK 10 LoginToken service + consent.py slimming (ENT-005)      deps: BLOCK 1
```

### 4.2 Why each edge exists

| Edge | Reason |
|---|---|
| `1 → 9` | The report's own dependency chain: bring the async entry layer inside the static gate **before** refactoring it. BLOCK 9 is the first refactor of `src/telegram_bot` middleware. |
| `1 → 10` | Same chain. BLOCK 10 rewrites `telegram_bot/handlers/login.py` and a 470-line backend view; both should be under a gate that already sees the bot. |
| `3 → 6` | The report's confirmed chain `ENT-002 → ENT-003`: a scheduler restart is the duplicate-digest trigger. Fix the stop path first, otherwise the restarts that fire the duplicate keep happening. Both blocks also edit `scheduler.py`'s daily-firing logic. |
| `3 → 7` | Both edit the scheduler's loop/cycle. BLOCK 3 changes the wait; BLOCK 7 changes what the cycle records. BLOCK 7's "did this cycle succeed" semantics must be written against the post-BLOCK-3 code. |
| `6 → 7` | Weak but real. BLOCK 7 defines "a clean cycle" in terms of non-zero returns, and BLOCK 6 changes what a daily run does and when it is recorded. Implementing BLOCK 7 first would mean re-reading `run_one_cycle` after BLOCK 6 lands. |

### 4.3 No edge exists for these, and why

- **BLOCK 2, 4, 5, 8 have no dependencies** and are therefore order-free among
  themselves. They are sequenced only because a single Implementor runs
  sequentially. `BLOCK 2` touches Compose and `gunicorn.conf.py`; `BLOCK 4` touches
  `telegram_bot/lifecycle.py`; `BLOCK 5` touches `docker/entrypoint-test.sh`; `BLOCK 8`
  touches `apps/core/utils/`. No file overlap — they could be parallelised if the
  one-Implementor rule were ever relaxed.
- **BLOCK 9 and BLOCK 10 are not ordered relative to each other** (different files).
  BLOCK 10 is listed last because it is the largest unit and benefits from the tree
  being quiet, not because it depends on BLOCK 9.
- **BLOCK 8 has no dependency on BLOCK 1** — the change is inert to the type checker.
  It is sequenced after BLOCK 1 only so that the new gate covers it.

### 4.4 The unsafe ordering (must be respected)

**ENT-003 / BLOCK 6** — the report's Rollout Safety table marks this as the phase's
one **unsafe ordering**:

> the durable marker and the idempotent `send_alerts` change must land together.
> Recording the marker first would only persist a run whose delivery is still
> duplicated.

Concretely, this means:

1. The marker and the `send_alerts` idempotency change ship as **one** change.
2. The durable marker is written **only after** a successful delivery, never before.
3. Neither half is a "safe" intermediate state. A rollback that restores only one of
   them **restores the original defect** — revert both or neither.
4. If a migration is required (Option A), it must be present in the same change as the
   code that reads and writes it. A model with no reader is dead weight; a reader with
   no model is an `OperationalError`.

### 4.5 The fragile insertion point (must be respected)

**ENT-008 / BLOCK 5** — removing the bootstrap step is the change most likely to break
the suite **silently**. Two hard rules:

1. **The internal sequence inside BLOCK 5 is mandatory:**
   `(a) repoint or drop the step` → `(b) run the suite` →
   `(c) remove || true` → `(d) run the suite again`.
   Removing `|| true` before (a) fails the container on every run and takes the whole
   suite red for an unrelated reason.
2. **`.\Makefile.ps1 test` is the only gate**, and a run at state (b) proves nothing
   about the fail-open removal. The Validator must run at state (d).
3. `ENT-014` lands in the **same change** — after (a), the header comment must describe
   whatever the file now does.

---

## 5. Cross-phase coordination

### 5.1 What must NOT be shipped twice

| Other phase's finding | What phase 01 must not do | Where the boundary lives |
|---|---|---|
| **DB-004** (phase 03, HIGH) | Add **no** `lock_timeout`, **no** `statement_timeout`, and no `OperationalError` retry to `apps/core/utils/advisory_lock.py`, to any `advisory_lock()` call site, or to `config/settings/base.py`'s `DATABASES["default"]["OPTIONS"]`. | BLOCK 8 ships only the docstring and the pre-acquisition log. |
| **DB-005** (phase 03, MEDIUM — **absorbs ENT-009**) | No phase-01 code at all. No "short-lived promotion marker". No change to `apps/ads/services/submission.py`'s promote-then-insert ordering, to `move_staging_to_permanent`, or to `sweep_orphaned_media`. No new `AdvisoryLockId` for media promotion. | ENT-009 is recorded as **closed by absorption** in §2. |
| **DB-007** (phase 03, MEDIUM) | BLOCK 6 must **not** take `AdvisoryLockId.ALERT_DELIVERY_TASK` in `deliver_immediate_alerts` and must **not** modify `apps/search/services/immediate_alerts.py`. | See §5.3 — this is the highest cross-phase hazard in the plan. |
| **DB-010** (phase 03, LOW) | Do **not** change the **transaction-scoped** branch's `transaction.on_commit` release callback, and do not convert the body to `try/finally`. | `test_advisory_lock_release_log.py` is the tripwire; it must pass unchanged after BLOCK 8. |
| **AD-003** (phase 05) | Nothing. AD-003 shares a symptom with DB-005/ENT-009 but has a different root cause (no refcount on shared storage keys) and a different fix. The three validated reports explicitly forbid merging them. | — |
| **CFG-002** (phase 02, HIGH) | BLOCK 2's compose-contract test must assert **only** the Compose contract. It must **not** assert anything about the CI `deploy-check` job. | The `deploy-check` job fix is phase 02's. VAL-003 groups the findings; it does not transfer ownership. |
| **CFG-006** (phase 02) | Nothing. The dev-stack crash loop on a placeholder `BOT_TOKEN` is not a phase-01 finding. | Listed in §6. |
| **AUT-007** (phase 04, VAL-002) | BLOCK 10 must **not** implement the token-invalidation behaviour change. It must only create the service that *could* own it, and must say so in the module docstring. | Two findings, one root cause, different fixes — retained and cross-referenced, never patched twice. |
| **Phase 10** (code quality) | The 12 type errors are remediated here **only** because the gate must go green (ENT-004). They are not filed as a phase-10 code-quality item, and phase 10 must not re-file them. | — |

### 5.2 DB-004 / ENT-006 — the three-way split (read this before BLOCK 8)

Three distinct log/doc issues live in `advisory_lock.py` and are spread across two
phases. They are **one work item with two changes**, not one finding:

| Element | Location | Owner | Phase 01 action |
|---|---|---|---|
| Acquisition **timeout** (bounded wait) | the whole `pg_advisory_lock` call | **DB-004** | **None.** |
| Acquisition **log** (silent wait) | the line before the acquire statement | **DB-004 addendum (b)** | **Yes** — BLOCK 8. |
| **Docstring** "skip" claim | `migrate_locked.py` module docstring | **DB-004 addendum (a)** | **Yes** — BLOCK 8. |
| **Release** log (`on_commit` never fires on rollback) | the transaction branch's `on_commit` callback | **DB-010** | **None.** |

### 5.3 DB-007 — the `SavedSearchNotification` schema hazard (highest cross-phase risk)

`DB-007`'s recommendation is: *"split 'selected' from 'delivered' — record the
notification only after a successful send (or add an explicit delivery-state
column)"*. `ENT-003`'s remediation also requires "recorded dispatch state" for
idempotent delivery. **Both findings want to change the same model.**

**Coordination requirement on BLOCK 6:**

- BLOCK 6 is scoped to: `ignore_conflicts` on the analytics bulk-create, and a durable
  record of *whether the daily dispatch already ran*. Both are answerable **without**
  touching `SavedSearchNotification`'s schema.
- **If the Planner concludes that an explicit delivery-state column is genuinely
  required**, that is now a **shared schema decision** and BLOCK 6 must stop and
  escalate to the coordinator before writing the migration. Two phases must not add
  overlapping migrations to `apps/search`.
- Recommended default: BLOCK 6 stays inside its scope; `DB-007` owns any
  delivery-state column. The daily-run marker (a separate artefact) already gives
  `ENT-003` the idempotency it needs at the *run* level, which is the granularity the
  finding actually describes.

### 5.4 Media / migration implications

- **No media migration from this plan.** ENT-009 is absorbed by DB-005, so phase 01
  adds no migration to `apps/media` and makes no change to the media storage contract.
- **A migration is possible only from BLOCK 6**, and only under marker Option A, and
  only into `apps/core/migrations/`.

### 5.5 Shared-artefact reservations (the coordinator must sequence these)

| Artefact | Claimed by | Risk |
|---|---|---|
| `apps/core/migrations/0005_*` | BLOCK 6 **if** Option A is chosen | Phase 03 also plans migrations in `apps/core`. If a phase-03 `0005_*` lands first, BLOCK 6 must renumber to `0006_*`. **The implementor must check the migrations directory immediately before generating, not assume.** |
| `AdvisoryLockId` (`apps/core/enums.py` + the docstring table in `advisory_lock.py`) | BLOCK 6 **only if** the marker design needs a lock | A shared enum with other phases. If one is allocated, **both** places must change in the same commit, and `test_advisory_lock_ids.py` must pass. Prefer not to allocate one. |
| `docker-compose.yml` / `docker-compose.prod.yml` / `docker-compose.dev.override.yml` | BLOCK 2 (all three), BLOCK 7 (prod `scheduler` healthcheck) | Different files within the prod file; BLOCK 7 must not disturb BLOCK 2's `web`/`bot` edits. If phase 02 (CFG-002) also edits compose, sequence BLOCK 2 first. |
| `.github/workflows/ci.yml` | BLOCK 1 (`lint` + `typecheck` jobs) | Phase 02's CFG-002 also targets `ci.yml` (`deploy-check`). **Sequence BLOCK 1 first** so the two edits merge cleanly; they touch disjoint jobs. |
| `docker/entrypoint-test.sh` | BLOCK 5 | Phase 03's `DB-004` may revisit test timeouts. Disjoint regions. |

---

## 6. Out of scope for this plan

Explicitly **not** touched, with the reason:

| Item | Reason |
|---|---|
| `CONN_MAX_AGE` and `DatabaseConnectionMiddleware` | Documented intentional design ("PgBouncer async safety (zone C5)"; the middleware docstring explains the per-update close mirrors the HTTP `request_finished` hook). ENT-010 Half B was **rejected as a defect by the report itself**. Revisiting it is a phase-13 question about a deliberate trade-off. |
| ENT-009's design, including the "short-lived promotion marker" | Absorbed by DB-005, which owns the design **and its unresolved fork** about where the final move happens relative to the transaction boundary. This plan does not pre-empt it. |
| `apps/ads/services/submission.py`, `apps/media/services/filesystem.py`, `apps/media/management/commands/sweep_orphaned_media.py` | DB-005's surface. |
| The `test` job's `working-directory` and `PYTHONPATH` in `ci.yml` | Unaffected by BLOCK 1 and must stay as-is: `pythonpath` in `pyproject.toml` is resolved relative to the config file, not the CWD. |
| Unauthenticated `/metrics` at the site root | Owned by phases 09/12. BLOCK 2 touches only the `PROMETHEUS_MULTIPROC_DIR` variable, never the endpoint's exposure. |
| The dev-stack crash loop on a placeholder `BOT_TOKEN` | Phase 02, CFG-006. It blocked live dev-stack evidence during the audit but is not a phase-01 finding. |
| The CI `security` job's `bandit -r src/backend src/telegram_bot` path (which resolves wrong under its `working-directory`) | Pre-existing and not a phase-01 finding. **Noted in BLOCK 1 so it is not mistaken for a regression.** |
| CI jobs `build`, `test`, `i18n`, `lint-templates`, `security`, `load-test`, `deploy-check` | Only the `lint` and `typecheck` run-steps change. |
| The 12 type errors as a *code-quality* concern | Phase 10. Phase 01 owns only the CI scope and the red gate. |
| `apps/api/` as a documented empty scaffold | Not dead code. |
| The ENT-006 acquisition-timeout half | Superseded by DB-004. |
| Any uniqueness constraint on `analytics_events` affecting writers other than `send_alerts` | Out of scope unless BLOCK 6's Auditor proves the blast radius is confined to `send_alerts`. If wider, defer to phase 10/13. |
| `find_matching_ads`'s matching semantics, `rollup_daily_metrics`, `deliver_immediate_alerts` | Not described by any phase-01 finding; `rollup_daily_metrics` is already idempotent; the immediate path is DB-007's. |
| Making `test_scheduler_wiring.py` the home for ENT-013's test | That file is a static shell-script test with no scheduler imports. The assertion belongs in `test_scheduler_error_handling.py`. |

---

## 7. Per-block risk register

Severity is this Planner's assessment of **execution** risk for the change, not the
finding's severity.

| Block | Risk | Likelihood | Impact | Mitigation / detection | Residual |
|---|---|---|---|---|---|
| **1** | Editing unmodifiable audit tooling to make root `ruff` green | Med | Med | BLOCK 1 states explicitly that `.ai/**` must not be edited and that `.ai` must not be added to `[tool.ruff] exclude`; the Validator confirms `git status --short .ai` is clean afterwards. | Low |
| **1** | Dropping `working-directory` from a dependency-install step | Low | High | Edit is constrained to the two named `run:` steps; the `test` job proves the suite still runs. | Low |
| **1** | "Fixing" the `test_ad_create.py` errors with a suppression | Med | Med | BLOCK 1 states the remedy is a typed signature or an assert, **not** a `pyright: ignore`; the Validator inspects the diff. | Low |
| **2** | Compose sequence-merge drops `PROMETHEUS_MULTIPROC_DIR` or its tmpfs from prod | Med | **High** | The `docker compose config` gate for all three stacks. A dropped tmpfs with `read_only: true` bricks the web container. | Low |
| **2** | New contract test asserts an *inherited* value using single-file `ruamel.yaml` | Med | Med | BLOCK 2 states plainly that `ruamel.yaml` does not merge overrides and prescribes per-file assertions; no Docker subprocess in the default gate. | Low |
| **2** | Mirroring the dev `bot`'s `seed` dependency by mistake | Low | Low | ENT-012 is scoped to "record the decision", explicitly not to mirroring. | Very low |
| **3** | Bounding only the post-cycle wait, leaving `interval + cycle_duration` as the worst case | Med | **High** | The Planner must decide and justify; the Validator must trace the SIGTERM-during-cycle path explicitly. | Med |
| **3** | `import time` becomes unused after the `sleep_func` default changes → new `F401` | Med | Low | Called out in BLOCK 3's carried-forward note 4. Gate: `uv run ruff check src/`. | Very low |
| **3** | The new test proves the flag is *set*, not that the loop *exits fast* | Med | Med | BLOCK 3 requires the new test to be **red against the pre-fix code**. | Low |
| **4** | The `asyncio` timeout escapes instead of being swallowed, aborting startup | Low | High | The new hanging-registration test asserts the hook *returns* within the budget, not just that markers exist. | Low |
| **5** | **Removing `\|\| true` before repointing or dropping the step** | Med | **High** | The four-step internal sequence is mandatory (§4.5). | Low |
| **5** | Dropping the step when the CI `test` job actually depends on it | Low | High | The Auditor verifies the CI job has its own independent `bootstrap_reference_data` step **before** Option A is committed to. | Low |
| **5** | A stale 39-table `mko_bazuna` in an existing volume masks the fix | Med | Med | The `to_regclass('public.django_migrations')` before/after check is the control. | Low |
| **6** | **Marker and idempotent delivery land separately** | Med | **High** | The unsafe ordering (§4.4): one change, marker written only on success, revert both or neither. | Low |
| **6** | A unique constraint on `analytics_events` breaks an unrelated writer | Med | High | BLOCK 6's Auditor must prove the blast radius is confined to `send_alerts`; otherwise the constraint is out of scope. | Low |
| **6** | Marker TTL too short, or marker written before delivery → re-fires the daily set | Med | High | Write the marker only after a successful run; assert the TTL explicitly under Option B. | Low |
| **6** | A delivery-state column is added to `SavedSearchNotification`, colliding with DB-007 | Med | **High** | §5.3: BLOCK 6 must **escalate to the coordinator** before adding it; default is to stay in scope. | Low |
| **6** | `apps/core/migrations/0005_*` is already claimed by phase 03 | Med | Med | Check the directory immediately before generating; renumber to `0006_*` if needed (§5.5). | Low |
| **7** | The inversion of the green test is done to make the suite pass rather than because the contract changed | Med | Med | The contract change is specified in the production code; the Validator reviews the pair together. | Low |
| **7** | A persistently failing command turns the scheduler `unhealthy`, and `restart: unless-stopped` turns that into a crash loop | Med | Med | This is the *intended* direction; BLOCK 7 requires the escalation to be stated explicitly. | Med — accepted and disclosed |
| **7** | `start_period` set too high, masking a genuinely stuck scheduler for longer | Low | Med | The Planner must derive the value from the cycle bound and state the derivation. | Low |
| **8** | Touching the transaction branch and re-opening DB-010 | Low | Med | `test_advisory_lock_release_log.py` is the tripwire and must pass unchanged. | Very low |
| **8** | Wording the new log line as a "timeout" promise that DB-004 has not implemented | Med | Med | BLOCK 8 requires the message to describe current behaviour only. | Low |
| **9** | The memo survives across updates → cross-user identity leak | Low | **Critical** | Per-update storage in the aiogram `data` dict; the "two updates, two users" test is the specific guard. | Low |
| **9** | Unifying the lookup keys silently changes locale behaviour for withdrawn users | Med | Med | BLOCK 9 defaults to **preserving** current behaviour; the Planner must justify any change explicitly. | Low |
| **9** | `User.DoesNotExist` becomes a raised error, breaking unregistered-user flows | Med | High | "User not found must not become an error" is called out; a dedicated test pins the tolerance. | Low |
| **10** | Collapsing the claim and consume predicates into one shared helper | Med | **Critical** | The report's correction is explicit that the predicates legitimately differ; the cross-predicate agreement test is the guard. | Low |
| **10** | Splitting `handle_login_orm`'s single transaction across an async boundary | Med | High | Preserving the one `sync_to_async` + one `transaction.atomic()` (with the `SAVEPOINT` inner block) is a stated constraint. | Low |
| **10** | "Slimming" `consent.py` broadens into a rewrite | Med | Med | The diff is constrained to the token lifecycle; the consent views are out of scope. | Low |
| **10** | Phase 04's AUT-007 lands a second ad-hoc token patch | Med | Med | The service docstring must state the AUT-007 boundary explicitly. | Low |
| **All** | A block is executed with its `depends_on` incomplete, or blocks are parallelised | Low | High | One Implementor, strictly sequential, in the §4.1 order. | Very low |
| **All** | A block's tests are asserted rather than run | Med | High | Every block names its exact gate command; tests run **only** through Docker. | Low |

---

## 8. Definition of done for the whole plan

Phase 01 is complete when **all** of the following hold.

### 8.1 Scope

- [ ] All 14 findings have a recorded disposition: 10 implemented, 2 de-scoped to a
      named residual, 1 absorbed by DB-005, 1 documented-only.
- [ ] `ENT-009` is recorded as closed by absorption with the `DB-005` cross-reference,
      and **no** phase-01 file under `apps/ads/services/submission.py`,
      `apps/media/services/filesystem.py` or
      `apps/media/management/commands/sweep_orphaned_media.py` appears in the diff.
- [ ] `ENT-006` shows exactly two changes: the `migrate_locked` docstring and a
      pre-acquisition log line in the **session** branch of `advisory_lock`.
      No timeout is introduced anywhere.
- [ ] `ENT-010` shows **no** change to `CONN_MAX_AGE` or `DatabaseConnectionMiddleware`.
- [ ] The `DB-005` transaction-boundary fork has **not** been decided or pre-empted.

### 8.2 Gates — all green

- [ ] `uv run ruff check src/` → exit 0.
- [ ] `uv run basedpyright src/` → **0 errors** (down from 14).
- [ ] `uv run ruff check .` still reports 2 errors in `.ai/audit/03-db-concurrency/verify_db.py`
      — this is **expected** and proves the audit tooling was not edited.
- [ ] `git status --short .ai` → empty. No audit-phase file was modified.
- [ ] `.\Makefile.ps1 test` (or `make test`) → full suite green, run at least once
      after BLOCK 5's `|| true` removal, not only before it.
- [ ] `docker compose config` resolves successfully for the dev stack, the prod stack
      and the test stack, and the resolved `web` and `bot` services carry the expected
      environment, tmpfs and `stop_grace_period`.

### 8.3 Per-finding behavioural confirmation

- [ ] `ENT-001` — a test calls `child_exit` with the variable unset (must not raise)
      and with it set (must mark dead). No Compose environment that runs gunicorn is
      missing the variable.
- [ ] `ENT-002` — a test using the **real** wait, not an injected no-op, shows the
      loop exits promptly after the stop flag is set, and it is **red** against the
      pre-fix code. The SIGTERM-during-cycle worst case is documented and bounded.
- [ ] `ENT-003` — a second run on the same calendar day does **not** dispatch the
      daily commands; a restart does **not** re-dispatch; `send_alerts` run twice
      produces no duplicate digest and no duplicate analytics rows. Marker and
      idempotency shipped together.
- [ ] `ENT-004` — CI `lint` and `typecheck` run from the repository root over `src/`
      and are green. The `test` job is unchanged.
- [ ] `ENT-005` — all eleven existing login test classes across both the backend and
      bot suites pass **unchanged**, including `TestConcurrentClaim`. A new test asserts
      claim and consume agree on their deliberately different predicates. The
      `AUT-007` boundary is stated in the new service module's docstring.
- [ ] `ENT-007` — a test asserts both markers are written when command registration
      hangs, and that the startup hook returns within its budget.
- [ ] `ENT-008` — `docker exec … psql … to_regclass('public.django_migrations')` shows
      the non-test `mko_bazuna` database is **not** repopulated by a test run. The
      `|| true` is gone and the suite is green in that state.
- [ ] `ENT-011` — all three long-lived services carry the same shutdown contract.
- [ ] `ENT-012` — the dev `bot`'s `seed` asymmetry is recorded in a comment and
      asserted.
- [ ] `ENT-013` — the marker is **not** refreshed after a failing cycle, and the
      scheduler healthcheck `start_period` covers a full cycle.
- [ ] `ENT-014` — the `entrypoint-test.sh` header lists what the base entrypoint
      actually does and states that this script runs the reference-data bootstrap
      itself.

### 8.4 Cross-phase integrity

- [ ] No `lock_timeout` / `statement_timeout` added (DB-004 intact).
- [ ] `test_advisory_lock_release_log.py` passes **unchanged** (DB-010 intact).
- [ ] `apps/search/services/immediate_alerts.py` untouched (DB-007 intact).
- [ ] No delivery-state column added to `SavedSearchNotification` without coordinator
      sign-off (§5.3).
- [ ] No `AdvisoryLockId` allocated unless strictly required, and if allocated, both
      `apps/core/enums.py` and the `advisory_lock` docstring table changed together
      with `test_advisory_lock_ids.py` green.
- [ ] If a migration was added, the number was checked against the migrations
      directory immediately before generation, and `.\Makefile.ps1 test-recreate` was
      run (§5.5).
- [ ] No new user-visible string was introduced without a complete `ru` and `bs`
      translation, and the i18n completeness gate passes.

### 8.5 Project conventions

- [ ] Every new constant is a named module-level constant (or a `StrEnum` / `IntEnum`
      member), never an inline literal or a dict-of-strings.
- [ ] New service logic lives in a `services/` package, not in a view or handler.
- [ ] No `print()` statements; `logger = logging.getLogger(__name__)` with lazy `%s`.
- [ ] All comments, docstrings and log messages are in English.
- [ ] Every non-trivial behaviour change has a test that verifies **logic and
      component interaction**. Pure plumbing (a compose value, a comment) is covered by
      the contract assertion, not by a behavioural test.
- [ ] `pytestmark` conventions follow the surrounding file.
- [ ] `uv run ruff check --fix src/` was run if imports were reordered.

### 8.6 Deliverables

- [ ] `VAL-005` (the report's inconsistent severity tally) is recorded in the audit
      tracker as a documentation-only input defect.
- [ ] This plan file is updated to mark each block's completion, so the phase
      coordinator has a single status surface.
- [ ] Nothing was committed without an explicit user request.
