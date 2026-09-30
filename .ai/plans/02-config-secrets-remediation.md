---
plan_id: "02-config-secrets-remediation"
phase: "02"
phase_name: "Configuration & Secrets Management"
source_report: ".ai/audit/99-validation/02-config-secrets-validated-findings.md"
source_findings: ".ai/audit/02-config-secrets/findings.md"
date: "2026-09-28"
planner: "Planner (subagent)"
anchor_commit: "344ca2b"
report_anchor_commit: "9e96b84"
status: "ready-for-execution"
findings_in_scope: 16
findings_implemented: 11
findings_absorbed: 1
findings_documented_only: 1
findings_constrained: 3
blocks: 10
---

# Execution Plan — Phase 02 Remediation (Configuration & Secrets Management)

## 0. Header, provenance and scope statement

### 0.1 Provenance

| Item | Value |
|---|---|
| Source report | `.ai/audit/99-validation/02-config-secrets-validated-findings.md` (validated, 1095 lines) |
| Report anchor commit | `9e96b84` |
| **Working anchor commit for this plan** | **`344ca2b`** (`git rev-parse --short HEAD`) |
| Date | 2026-09-28 |
| Findings in scope | 11 `CFG-001` … `CFG-011` + 5 `VAL-001` … `VAL-005` = **16** |
| Verdicts in source report | Confirmed 8 · Adjusted 3 · Rejected 0 |
| Execution blocks | 10 |
| Implementor concurrency | 1, strictly sequential (project rule: only one implementor at a time) |

### 0.2 Evidence basis — read this before executing any block

The report is anchored at `9e96b84`, roughly 40 commits behind `344ca2b`; the entire
phase-01 remediation has landed since. The Planner re-derived every load-bearing claim
against the working tree at `344ca2b` by direct observation. Corrections to the supplied
code-context document, which are recorded here because they change risk ratings:

| Claim in the code-context document | What the tree actually shows at `344ca2b` |
|---|---|
| Working tree has 8 modified files, incl. `src/backend/apps/core/utils/scheduler.py` | The dirty set is **different and unstable**. At the first read `src/backend/apps/core/utils/scheduler.py` was **clean** and `src/backend/apps/core/tests/test_scheduler_error_handling.py` was modified; at the second read, minutes later, **both** were modified, along with two further doc files. The tree is being edited in parallel while this plan is written. §1's staging rule is written to survive that. |
| Working tree "NOT clean" but only via modifications | It is also **dirty by deletion**: 19 tracked files under `.ai/audit/**` (all 16 `findings.md`, three phase-03 verification scripts, and `templates/audit-findings.md`) are deleted in the worktree. See the hard rule in §1. |
| "`config/settings/tests/` **IS** scanned by bandit" (R-2) | **Not true in CI.** The `security` job runs `uv run bandit -r src/backend src/telegram_bot -c pyproject.toml` with `working-directory: src/backend`, so the relative paths resolve to `src/backend/src/backend` and `src/backend/src/telegram_bot` — neither exists — and `-c pyproject.toml` resolves to `src/backend/pyproject.toml`, which does not exist (the real file is at the repository root). Bandit scans nothing today. Recorded as **VAL-006** in §0.5 and routed out of phase 02. |
| `test_compose_contract.py` has 8 tests | 9 test functions. Phase 01 added one more than the context recorded. |
| Dev stack: `web` and `bot` `Restarting (1)` | **Re-confirmed live** at planning time. CFG-006 is still an active outage. |

Everything else in the code-context document was confirmed and is used as given. In
particular, re-verified by direct read: `base.py` (402 lines), `prod.py` (251 lines),
`dev.py` (66 lines), `test.py` (97 lines), `test_migrations.py`, and migration
`0003_add_bot_username.py` are byte-identical to the report's reading. `ci.yml` is
**+2 lines** from the report's line numbers (§6, "Stale report claims"), and the
`deploy-check` job's `env:` block is unchanged since `6ef5390` — all eight variables,
still no `EMAIL_HOST` and no `REDIS_URL`. The orphaned contract comment still sits
above the `load-test:` job, 133 lines above the `deploy-check:` job it documents.

**If any statement in this plan conflicts with a fact the code-context document held but
the tree no longer shows, the tree wins — the anchor is `344ca2b`, not `9e96b84`.**

### 0.3 Scope statement (explicit)

**In scope — implemented by this plan (11):**
`CFG-001`, `CFG-002`, `CFG-003`, `CFG-004`, `CFG-005`, `CFG-006`, `CFG-007`,
`CFG-008`, `CFG-009`, `CFG-010`, `CFG-011`.

**Landed as binding constraints inside the block that owns the code (3):**

- **`VAL-001`** → BLOCK 3. `test_django_oneshot_bypasses_all_secrets` is **rewritten
  in the same change** as the CFG-001 code half. A remediation that follows the report's
  Rollout-Safety table literally lands a red suite and gets reverted.
- **`VAL-002`** → BLOCK 10. CFG-003 is re-scoped to command-contract hygiene, and the
  block must not claim the fix reduces the real exposure.
- **`VAL-003`** → BLOCK 6. CFG-009's `.env.example` **deletion** branch is rejected. The
  retitle branch is used and the stub retains `CSRF_TRUSTED_ORIGINS=` and
  `SENTRY_DSN=`, both of which are pinned by shipped green tests.

**Absorbed (1):**

- **`VAL-004`** → the cross-cutting recommendation is split across owners, not shipped
  once here. Instance (a), compose-rendering parity, **already landed** in phase 01 as
  `src/backend/tests/test_compose_contract.py` — which is why the anti-pattern instance
  count drops from five to three. Instance (b), prod-settings import parity, is
  **BLOCK 4**. Instance (c), bidirectional consumed↔allowlist↔template parity, is
  **BLOCK 6**. Phase 02 ships (b) and (c) only.

**Documented-only / verification-environment (1):**

- **`VAL-005`** — `gitleaks` and `pre-commit` are not installed on this host, so the
  project-declared secret scanner was not exercised. No code change. See §0.5.
- **`VAL-006`** *(new; Planner finding, not in the source report)* — the CI `security`
  job's bandit invocation resolves to non-existent paths and a non-existent config
  file. Routed **out** of phase 02 to phase 12 (production-ops) / phase 10; see §5.3.

**Counts:** 11 implemented + 3 constrained + 1 absorbed + 1 documented-only = **16**
(of which `VAL-006` is an additional Planner-recorded input defect, not a source-report
item).

### 0.4 Severity correction

The source report's `Severity movement` summary reads
`0 CRITICAL, 1 HIGH, 5 MEDIUM, 5 LOW`, which **matches** its per-finding `Final sev.`
column. No correction is needed — recorded here so the per-finding column is treated as
authoritative by default, and so a future reader does not go looking for a phase-02
equivalent of phase 01's `VAL-005` and not find one.

| Severity | Findings |
|---|---|
| CRITICAL | — (0) |
| HIGH | `CFG-002` (1) |
| MEDIUM | `CFG-001`, `CFG-004`, `CFG-005`, `CFG-006`, `CFG-007` (5) |
| LOW | `CFG-003`, `CFG-008`, `CFG-009`, `CFG-010`, `CFG-011` (5) |

### 0.5 Open technical questions — resolved here or explicitly deferred

The eight questions raised for the Planner are answered as follows. **Two are decided,
one is decided-with-a-residual, and five are surfaced as explicit open questions for the
named block's Planner/Researcher.** Nothing below is left silently ambiguous.

| # | Question | Disposition | Owner |
|---|---|---|---|
| G1 | Does `DJANGO_ONESHOT` survive CFG-001's fix? | **DECIDED: yes, the name survives and it stays in `ALLOWED_ENV_VARS`.** It ceases to be a bypass for `config.settings.prod`; the bypass becomes reachable only through a settings module that is not `prod`. Both `test_compose_oneshot_flags` and `test_python_consumed_vars_in_allowlist` key on this exact name — renaming it churns two green tests for zero security benefit. The **mechanism** (how the non-prod module is selected) is open — see §3.3. | Planner, BLOCK 3 |
| G2 | What replaces `DJANGO_BUILD`? | **DECIDED: nothing — it is unchanged.** The builder stage has no `.env` at all, runs `collectstatic` and `compilemessages` under `config.settings.prod`, and a bootstrap settings module cannot serve a build. `test_csrf_trusted_origins_skipped_during_build` pins its behaviour. **Residual stated honestly:** `DJANGO_BUILD` in `.env.prod` would still bypass everything; BLOCK 3 closes that channel with the report's own mechanism (own commented allowlist group + a `.env.prod.example` absence assertion), not by changing the flag. | — closed |
| G3 | Is the `EmailTransport` StrEnum half in scope? | **DECIDED: split into two blocks.** BLOCK 7 ships the unconditional re-pin (the harm is closed there). BLOCK 8 is the enum, **gated on a named activation trigger** and explicitly not to be started speculatively — project rule 5 outweighs rule 10 until an operator need exists. | — closed |
| G4 | What counts as a "placeholder" for `BOT_USERNAME`? | **OPEN.** `^<[^>]+>$` is strictly weaker than the model's `^[A-Za-z0-9_]{3,32}$`. The shared helper extracted for CFG-011 must expose a **validator**, not only a placeholder detector. Options and the exact validation surface are BLOCK 5's Planner's call. | Planner, BLOCK 5 |
| G5 | CFG-005 data repair: repair command or manual admin edit? | **OPEN.** Editing migration `0003` only protects *fresh* databases — it will not re-run on an applied deployment, and no management command or signal re-syncs `SiteConfig.bot_username` from settings. The DB value also **wins over env** at read time. BLOCK 5's Planner must choose. | Planner, BLOCK 5 |
| G6 | CFG-009 retitle: what must the stub retain? | **DECIDED: `CSRF_TRUSTED_ORIGINS=` and `SENTRY_DSN=`.** Both are asserted by shipped green tests (`test_csrf_trusted_origins_in_example`, `test_sentry_dsn_in_env_examples`). The file is retitled, not deleted; two doc references (`docs/01-spec/architecture-structure.md`, `docs/99-agent/architecture.md`) stay valid because the file survives. | — closed |
| G7 | Which mechanism for the CFG-010 dev/test parity assertion? | **DECIDED: subprocess isolation, in `test_settings_defaults.py`.** Every existing settings test uses subprocess isolation because `override_settings` cannot test import-time configuration, and `test_settings_defaults.py` already owns exactly that pattern for a per-module default. An AST-parse alternative exists but is a new pattern for this repo. | — closed |
| G8 | Reverse-direction allowlist test: regex sweep or curated constant? | **OPEN — and it is the pivotal design question of BLOCK 6.** Three independent sweeps produced 33 / 36 / 36 consumed names. A regex sweep that false-positives will be disabled within a week. Three candidate mechanisms are laid out in §3.6 with a recommendation; the Planner picks. | Planner + Researcher, BLOCK 6 |

---

## 1. Environment and command contract for the implementor

These constraints bind every block. They are not optional and they are not re-derived
per block.

| Concern | Rule |
|---|---|
| Test execution | **Docker only.** `.\Makefile.ps1 test` (Windows PowerShell 7+) or `make test`. **Never `uv run pytest` locally** — there is no DB on `localhost:5432`. |
| Test DB | Start once per session: `.\Makefile.ps1 test-db`. It is currently **Up (healthy)**. |
| Targeted test run | `$dc run --rm -e PYTEST_OPTS="<tokens>" test` with `$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'`. |
| `PYTEST_OPTS` | **Word-split on spaces and unquoted.** `-k test_name` and bare file paths work; a quoted multi-token value such as `-k "a b"` does **not**. Setting `PYTEST_OPTS` **replaces** the defaults (`--reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup`), so targeted runs lose xdist parallelism and DB reuse. |
| `PYTEST_SKIP_MARKERS` | `--env PYTEST_SKIP_MARKERS=seed` skips the nightly seed suite. Prefer this over `PYTEST_OPTS` for marker exclusion. |
| Fresh schema | `.\Makefile.ps1 test-recreate` after any migration change or interrupted run. Required by BLOCK 5 (it edits a migration). |
| Image rebuild | Not needed for the suite — the `test` service bind-mounts the repo. **Needed** for BLOCK 1/3/4, which touch `ci.yml` and the Dockerfile-adjacent build path, to confirm the `deploy-check` job runs green. |
| Static gates | `uv run ruff check src/` and `uv run basedpyright src/` run fine on the host. **Both are currently green** at `344ca2b` (ruff: all checks passed; basedpyright: 0 errors, 0 warnings, 0 notes) — phase 01's `ENT-004` fixed the gate scope. They must stay green. |
| `ruff` autofix | `uv run ruff check --fix src/` sorts imports (`I001`). `ruff format` is **not** the project convention. |
| Never | `--override-ini=addopts=` — it strips `--import-mode=importlib`, which `pyproject.toml` sets and the suite depends on. |
| `bandit` | **Not installed on the host**; runs in CI only. `pyproject.toml` `[tool.bandit]` sets `level = "low"`, `skips = ["B101", "B105"]`, and `exclude_dirs` that does **not** cover `config/settings/tests/`. Because of VAL-006 the job currently scans nothing, but the pattern is still required: invoke subprocesses as `subprocess.run([sys.executable, ...])` (list form, absolute interpreter — avoids `B603`/`B607`), and never use a literal `/tmp` path (`B108`). The existing settings tests already satisfy this. |
| `gitleaks` | **Not installed on the host** (VAL-005). CI enforces it. Any new literal in a settings test that looks like a credential **must** match an existing `.gitleaks.toml` allowlist regex — `test-secret-key-for-testing-only`, `test-bot-token-for-testing`, `test-admin-password` — or the `security` job goes red. Prefer the existing `config/settings/tests/__init__.py` constants (`TEST_SECRET_KEY`, `TEST_BOT_TOKEN`, `TEST_TRANSLATE_KEY`) over new literals. |
| Real `.env.*` files | **Never read, print, quote or transcribe a value from a real `.env.*`.** Key names only. `src/.env` is a 0-byte file so `read_env()` is a local no-op; use synthetic environments in tests, never the real file. The working-tree `.env.prod` is **not deployable** (missing `EMAIL_HOST` and `CSRF_TRUSTED_ORIGINS`) — do not "fix" it as part of this plan; it is a gitignored operator file. |
| PowerShell | `head` / `tail` do not work. Use `Select-Object -First/-Last`, `Get-Content -TotalCount`, `Select-String`. |
| Full suite | `.\Makefile.ps1 test-all` (~35 min, includes `seed`). Not required by any block in this plan. |
| i18n | Any new **user-visible** string requires `{% trans %}` / `gettext` **and** non-empty `msgstr` for `ru` and `bs`. **No block in this plan introduces a user-visible string.** `ImproperlyConfigured` / `ValueError` messages and `logger.warning` calls are operator diagnostics, not UI, and are not translated anywhere in this codebase. Management-command `help` text is likewise untranslated by existing convention (verified: no `gettext` import in any of the 13 `apps/core/management/commands/*.py`). The i18n completeness gate must nevertheless pass, since BLOCK 6 edits `.env` templates and BLOCK 3 may touch a management command. |
| **Dirty tree** | **Hard rule.** The working tree was **actively changing during planning** — the modified-file set grew between two `git status` runs minutes apart — and it is dirty in two directions: several tracked files modified, **and 19 tracked deletions under `.ai/audit/**`**. Never `git add -A`, never `git add .`, never `git commit -a`. **Stage explicit paths only**, and re-read `git status --short` immediately before every commit rather than trusting a list captured earlier. Two files were confirmed modified at planning time and are phase-02 doc targets: `docs/99-agent/rules.md` and `docs/ops/docker-deployment.md`. **Coordinate; do not clobber.** |
| Audit tree | `.ai/audit/**` is unmodifiable. No block may edit, restore, or re-create any file under it. |
| Commits | Do not commit without an explicit user request. |

---

## 2. Scope decisions table (acceptance contract for execution)

| ID | Disposition | Block | Final severity | One-line reason |
|---|---|---|---|---|
| `CFG-001` | **implement** — bypass made reachable only outside `config.settings.prod`; allowlist regrouped; both green tests rewritten | BLOCK 3 | MEDIUM | Guard-on-guard defect with a catastrophic tail; the file must be touched anyway and the fix is small once the placement is designed. |
| `CFG-002` | **implement, split in two** — (a) restore the gate (`ci.yml`), (b) make the restore durable (shared required-variable set + a test in the `test` job) | BLOCK 1, BLOCK 4 | HIGH | The only automated production-config check cannot import the module it checks. The split lets the 2-line restore land first and the design land after CFG-001 settles the requirement set. |
| `CFG-003` | **implement, re-scoped per VAL-002** — command-contract hygiene only; the block may not claim it reduces the real exposure | BLOCK 10 | LOW | Impact refuted: the credential is already in `Config.Env`. What remains is `--password required=True` forcing a secret through argv. |
| `CFG-004` | **implement half A** (unconditional re-pin) + **half B conditional** (`EmailTransport` StrEnum, gated on a named trigger) | BLOCK 7, BLOCK 8 | MEDIUM | Re-pinning closes a real harm class immediately; the enum is the operator-facing escape hatch and must not be built speculatively. |
| `CFG-005` | **implement** — guard `BOT_USERNAME` in prod and dev, make migration `0003` validate before writing, plus the **data-repair** path | BLOCK 5 | MEDIUM | The DB value wins over env, so a seeded placeholder produces dead `t.me/` links site-wide; an env fix alone does not repair an applied deployment. |
| `CFG-006` | **implement** — relocate the guard to the bot entrypoint; retarget the three dev tests in the same change | BLOCK 2 | MEDIUM | **Live outage.** A bot-only credential takes the whole dev stack down through module-scope `raise` plus `restart: unless-stopped`. |
| `CFG-007` | **implement** — delete the dead setting; pin `STORAGES` with a test; correct the `test.py` comment's subject | BLOCK 9 | MEDIUM | Taxonomy bucket for unused config; one line. Fix opportunistically alongside the other settings-module hygiene. |
| `CFG-008` | **implement, together with CFG-009** | BLOCK 6 | LOW | One missing allowlist entry for a documented, consumed variable; the impact is a false-positive warning that degrades the one mechanism meant to catch a real typo. |
| `CFG-009` | **implement, retitle branch only** — deletion branch rejected per VAL-003 | BLOCK 6 | LOW | A file labelled "Comprehensive" is neither comprehensive nor authoritative. Retitle + add the missing blocks + the reverse-direction test. |
| `CFG-010` | **implement** — reset the HSTS triple in `test.py`; add a dev/test transport-tuple parity assertion | BLOCK 9 | LOW | Browser-cache-only impact in a deliberately divergent test module; the report asks for it to be absorbed into adjacent settings-test work, and this is that work. |
| `CFG-011` | **implement** — correct the comment; extract the shared placeholder/validation helper **first** | BLOCK 5 | LOW | The comment names the right container and the wrong mechanism. The Pydantic-settings half is rejected by the report and is not in any block. |
| `VAL-001` | **binding constraint** in BLOCK 3 | BLOCK 3 | MEDIUM | A shipped green test asserts the bypass as intended behaviour; the rewrite is not optional. |
| `VAL-002` | **binding constraint** in BLOCK 10 | BLOCK 10 | MEDIUM | The recommended fix reduces exposure by exactly zero; the block must not overstate it. |
| `VAL-003` | **binding constraint** in BLOCK 6 | BLOCK 6 | LOW | Deletion turns two green tests red and desynchronises a spec line. |
| `VAL-004` | **absorbed** — (a) landed in phase 01, (b) BLOCK 4, (c) BLOCK 6 | BLOCK 4, BLOCK 6 | LOW | One anti-pattern, five instances, two already owned elsewhere. Three remain, and each gets exactly one assertion. |
| `VAL-005` | **documented-only** — verification-environment limitation, no code | — | LOW | Manual `git grep` sweeps are not gitleaks assurance and must not be reported as such. |

---

## 3. Execution blocks

Roster legend and the standing rule: **Implementor is always required, exactly one at a
time, sequentially.** Auditor / Researcher / Planner / Validator are added per block with
an explicit justification and an explicit statement of who is **not** required and why.
The rule "high risk ⇒ all agents" is applied to **BLOCK 3** (CFG-001: the VAL-001 trap, a
HIGH tail, a possible new settings module, two live tests to retarget), **BLOCK 4**
(CFG-002b: the only HIGH finding's durable half, plus a genuinely open shared-constant
design), and **BLOCK 6** (CFG-008 + CFG-009: the VAL-004 cross-cutting recommendation,
new test infrastructure, and the deletion-branch hazard).

---

### BLOCK 1 — Restore the CI `deploy-check` gate (CFG-002, restoration half)

| | |
|---|---|
| **Findings owned** | `CFG-002` — **restoration half only** |
| **`depends_on`** | *(none)* |
| **Priority** | P0 — executes first |
| **Roster** | **Implementor, Validator** |

**Why this block is split from CFG-002's durable half.**
The report records both facts and they are not in conflict once separated: the dependency
chain says *CFG-001 must be resolved before CFG-002 can be **trusted***, and the roadmap
note says *consider landing CFG-002 first because it is 2 lines with no test churn*. Both
are satisfied by splitting: **restoring** a broken gate can only turn a red job green and
is independent of CFG-001; **making the restore durable** (a shared required-variable set)
depends on CFG-001, because the set of required variables is conditional on where the
bypass lives. BLOCK 1 is the restore. BLOCK 4 is the durability.

**Agent requirement decision.**
- **Implementor — yes.** Always.
- **Auditor — no.** Every relevant location is named and the failure was reproduced twice
  by the validator (import fails at `EMAIL_HOST`, then at `REDIS_URL`, then imports
  cleanly with both). The Planner re-read the `deploy-check` job's `env:` block, the
  orphaned comment block, and the `check --deploy` step at `344ca2b` and confirms all
  three facts. There is no unresolved investigative question.
- **Researcher — no.** No external best-practice question. The two added values are
  dictated by the `prod.py` guards themselves and the report's own successful
  reproduction. The comment move is a one-line-adjacent relocation whose correct position
  is specified (directly above `deploy-check:`).
- **Planner — no.** A two-variable addition plus a comment relocation. There is no design
  to pre-author; the design lives in BLOCK 4.
- **Validator — yes.** The entire finding is *"the gate is silently dead and nothing
  noticed"*. A claim that the gate now runs must be established by an independent
  execution of the job, not by inspection of the diff. The Validator runs
  `check --deploy --fail-level WARNING` against `config.settings.prod` with exactly the
  job's variable set and must see it pass — and must confirm the gate would still fail if
  a variable were removed, i.e. that it is not passing for a different reason.

**Findings and notes carried forward.**
1. **The two variables are `EMAIL_HOST` and `REDIS_URL`.** Both guards are unconditional
   once `_SKIP_SECRET_VALIDATION` is false, and CI sets neither bypass flag. The values
   must be **non-secret placeholders** consistent with the job's existing convention
   (`https://example.com`, `redis://...`). No real credential may be introduced — the
   `security` job's gitleaks scan runs on the repository and the added values must match
   an existing allowlist or be obviously non-credential.
2. **The structural cause is the orphaned comment, not the missing variables.** The
   contract statement — *"All required production env vars are set to valid non-secret
   placeholders so the full prod settings import path is exercised"* — sits above the
   `load-test:` job, 133 lines from the job it documents. Moving it directly above
   `deploy-check:` removes the cause; adding the two variables removes the symptom. **Do
   both.** A fix that only adds the variables leaves the next drift invisible.
3. **The comment's last sentence becomes false if only the variables are added** — no.
   It is currently *aspirationally* true and *factually* false. After this block it is
   true. The Validator must confirm the moved comment describes the block that now
   follows it.
4. **`check --deploy` is the only production-config check in the whole pipeline** and the
   `test` job does not run it. Nothing else covers the gap; that is why the gate matters.
5. **Do not touch any other CI job.** Phase 01 already edited the `lint` and `typecheck`
   jobs' run-steps (§5.5 of the phase-01 plan reserved `ci.yml` for both phases and
   required phase 01 to go first — it has). The `test`, `i18n`, `security`,
   `load-test`, `build` and `lint-templates` jobs are untouched.
6. **The `deploy-check` job has no DB service container**, by design — `check --deploy`
   is static. The two added variables must not introduce a connection attempt.
7. **Forward dependency recorded:** after this block the gate is live and will cover
   every subsequent prod-settings change in this plan. If a later block turns the gate
   red, that is the gate working, not a regression to be suppressed.

**File surface (semantic units).**
- `.github/workflows/ci.yml` → `jobs.deploy-check.env` (add `EMAIL_HOST`, `REDIS_URL`);
  the orphaned deploy-check contract comment block (relocate to sit directly above
  `jobs.deploy-check`).
- **Not touched:** every other `ci.yml` job; `docker/entrypoint.sh`; any settings module;
  any test file.

**Tests required.**
- *Must keep passing unchanged:* everything. This block adds no test and changes no
  Python. It is a CI-only change.
- *Must be added:* none here. The durable regression test is BLOCK 4's deliverable, and
  per the report it must run in the **`test` job**, not in `deploy-check` — a test that
  only runs inside the job it guards cannot fail that job.
- *Gate:* `uv run python src/backend/manage.py check --deploy --fail-level WARNING` from
  a shell carrying **exactly** the `deploy-check` `env:` block and nothing else
  (`DJANGO_SETTINGS_MODULE=config.settings.prod` plus the now-ten variables) → exit 0.
  Then, as a negative control, remove `REDIS_URL` and confirm the command **fails**;
  restore it. A passing gate that also passes when a variable is missing is not a gate.
  Finally `.\Makefile.ps1 test` as a no-regression sweep.

**Risk / rollback.**
- *Risk:* adding the two variables without moving the comment, leaving the structural
  cause in place. BLOCK 1 requires both halves.
- *Risk:* a placeholder that trips gitleaks and reds the `security` job. Use values
  consistent with the job's existing convention and verify against `.gitleaks.toml`'s
  regex allowlist.
- *Risk:* a future guard addition still lands silently — that is exactly what BLOCK 4
  exists to prevent. This block alone is a restore, not a fix for the anti-pattern.
- *Rollback:* revert the `ci.yml` hunk. Fully reversible; no code, no contract, no state.

---

### BLOCK 2 — Relocate the bot-token placeholder guard out of `dev.py` (CFG-006)

| | |
|---|---|
| **Findings owned** | `CFG-006` |
| **`depends_on`** | *(none)* |
| **Priority** | P0 — **restores the live dev stack**, and unblocks BLOCK 3's live verification |
| **Roster** | **Implementor, Auditor, Validator** |

**Agent requirement decision.**
- **Implementor — yes.** Always.
- **Auditor — yes.** The guard is being moved from a *settings-import* failure to a
  *process-startup* failure, and that changes three things the report does not enumerate:
  the bot container's observable failure mode under `restart: unless-stopped`, whether
  `docker/healthcheck-bot.sh` can distinguish "refused to start" from "hung", and
  whether the dev one-shot services (which do **not** import `dev.py`) are affected at
  all. The Auditor establishes the bot's failure-mode and healthcheck contract from
  `src/telegram_bot/main.py`, `src/telegram_bot/lifecycle.py`,
  `docker/healthcheck-bot.sh` and the `bot` service block in `docker-compose.yml` before
  the guard is written.
- **Researcher — no.** The report names the destination (`telegram_bot/main.py`,
  immediately after `token = settings.BOT_TOKEN`) and the reason (production runs both
  tiers from one secret source, so a blank key must still fail the web tier fast). There
  is no external best-practice question and no library behaviour to check.
- **Planner — no.** The change is a relocation of a four-line guard plus a retarget of
  three named tests. The one genuine fork — *raise or return* — is small enough to settle
  in the file surface note below; it does not warrant a design pass.
- **Validator — yes.** This block restores a system that is **down right now**, and it
  inverts the premise of three shipped green tests. An independent reviewer must confirm
  the retargeted tests assert the new contract rather than merely pass.

**Findings and notes carried forward.**
1. **The mechanism is a module-scope `raise` inside `django.setup()`**, executed by
   *both* dev services because `docker-compose.dev.override.yml` sets
   `DJANGO_SETTINGS_MODULE=config.settings.dev` for both `web` and `bot`. A credential
   only the bot consumes therefore takes the web tier down, and `docker ps` alone gives
   no diagnosis. Confirmed live at planning time: `mko-bazuna-dev-web-1` and
   `mko-bazuna-dev-bot-1` are both `Restarting`.
2. **The `raise` vs `return` decision — resolved here, with the reasoning stated.** The
   existing truthiness branch in `main()` (`if not token:` → warn and return) exists for
   the *legitimate* "bot not needed" case that `dev.py`'s own message sanctions
   (*"or leave it empty (BOT_TOKEN=) to skip bot startup"*). A **placeholder** is not
   that case: it is a misconfiguration. Therefore the relocated guard must **raise**, not
   return — a return would let the bot container exit 0 and report healthy while carrying
   an unusable token, which is the exact failure class this finding is about. The
   Implementor must preserve the empty-token skip untouched and add the placeholder raise
   beside it.
3. **The prod guard must not move.** `prod.py`'s `_validate_production_secret` on
   `BOT_TOKEN` stays exactly where it is: production runs `web` and `bot` from one secret
   source, so a blank or placeholder key there must still fail both tiers at boot.
4. **The duplicated regex is the real cost of this block as scoped.** `dev.py`'s
   `_BOT_TOKEN_PLACEHOLDER_RE` is a *copy* of `prod.py`'s `_SECRET_PLACEHOLDER_RE`, and
   its own comment says so. BLOCK 2 does **not** extract the shared helper — that is
   CFG-011's job and lands in **BLOCK 5**. BLOCK 2's job is to stop the crash loop.
   Extracting the helper here would drag CFG-005's open questions (G4, G5) into a
   block whose whole value is that it is small and unblocked.
5. **Three tests must be retargeted in the same change**, or the suite goes red:
   `test_bot_token_required_in_dev`, `test_bot_token_placeholder_rejects_in_dev`, and
   `test_bot_token_real_value_allowed_in_dev`. The first two currently assert an
   **import-time** `ImproperlyConfigured` from `config.settings.dev`; after this block
   the import must **succeed** and the failure must be asserted at
   `telegram_bot.main.main()`. The third asserts a successful import — it still passes,
   but its docstring's premise ("passes the dev placeholder guard") becomes false and
   must be rewritten, not left stale.
6. **None of the seven tests in `src/telegram_bot/tests/test_main.py` exercise
   `main()`** — they all test `configure_dispatcher`. The new test needs a harness: call
   `main()` with `settings.BOT_TOKEN` patched to a placeholder and assert it raises
   without entering `run_polling`. `configure_dispatcher` is not on that path once the
   raise fires, so no aiogram wiring needs stubbing. `main()` is synchronous and must be
   invoked with the Django settings already configured — the bot package's own
   `conftest.py` (which redefines `user` as async and **cannot** import the backend
   conftest) is the right home for the new test.
7. **The dev one-shot services are unaffected** — they run `config.settings.prod` and
   never import `dev.py`. `DJANGO_ONESHOT` and their compose contract are untouched here.
8. **The dev override's `web`/`bot` `DJANGO_SETTINGS_MODULE` must not change.** Relocating
   the guard is the whole fix; changing which settings module dev uses would be a redesign.

**File surface (semantic units).**
- `src/backend/config/settings/dev.py` → the module-scope placeholder guard and the
  `_BOT_TOKEN_PLACEHOLDER_RE` definition (**remove the guard**; whether the now-unused
  local regex is deleted or left for BLOCK 5's helper is an implementor call that must be
  stated in the commit message — an unused module-level name is not a `ruff` error but is
  dead weight).
- `src/telegram_bot/main.py` → `main()`, immediately after the `token = settings.BOT_TOKEN`
  read; the existing empty-token skip branch (**preserve unchanged**).
- `src/backend/config/settings/tests/test_settings_secrets.py` →
  `test_bot_token_required_in_dev`, `test_bot_token_placeholder_rejects_in_dev`,
  `test_bot_token_real_value_allowed_in_dev` (**retarget**, not delete).
- `src/telegram_bot/tests/test_main.py` → a new test (or class) for the relocated guard.
  Follow the file's existing `pytestmark` and the `dp` fixture conventions.
- **Not touched:** `docker-compose.dev.override.yml`, `prod.py`, the healthcheck script,
  any compose file.

**Tests required.**
- *Must keep passing unchanged:* all of `src/telegram_bot/tests/test_main.py` (the seven
  `configure_dispatcher` tests are orthogonal to `main()`); all of
  `src/backend/config/settings/tests/test_prod_logging.py`;
  `test_settings_secrets.py`'s other seventeen tests.
- *Must be changed (retargeted, not removed):* the three named dev bot-token tests, each
  asserting the **new** contract: `import config.settings.dev` **succeeds** with a
  placeholder token, and `telegram_bot.main.main()` **refuses to start**.
- *Must be added:* a case proving an **empty** `BOT_TOKEN` still takes the graceful
  skip path and returns normally — the relocated guard must not have swallowed the
  legitimate case.
- *Gate:* `$dc run --rm -e PYTEST_OPTS="src/telegram_bot/tests/test_main.py src/backend/config/settings/tests/test_settings_secrets.py" test`,
  then `.\Makefile.ps1 test`, then a **live** confirmation:
  `.\Makefile.ps1 up` (or `docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml up -d`)
  followed by `docker ps --filter "name=mko-bazuna-dev-"` showing `web` and `bot` **Up**
  rather than `Restarting`, and `docker logs mko-bazuna-dev-web-1` showing a successful
  `runserver` start.

**Risk / rollback.**
- *Risk:* the guard returns instead of raising, so the bot exits 0 and reports healthy
  with an unusable token — a worse failure than the crash loop because it is silent.
  Note 2 fixes this; the "empty token still skips" test is the paired guard.
- *Risk:* retargeting the three dev tests to `main()` while `main()`'s guard has not
  moved yet, or vice versa. They land in one change.
- *Risk:* the new `main()` test pulls in aiogram wiring it does not need. Place the
  assertion so the raise fires **before** `configure_dispatcher` / `Bot(...)` /
  `run_polling`.
- *Rollback:* revert `dev.py` and `main.py` together — reverting one leaves the guard in
  the wrong process and the tests asserting a contract that no longer holds. The
  crash loop returns; nothing else changes.

---

### BLOCK 3 — Scope the secret-validation bypass (CFG-001 + VAL-001)

| | |
|---|---|
| **Findings owned** | `CFG-001` (code half, allowlist half, `.env.prod.example` half), `VAL-001` |
| **`depends_on`** | **BLOCK 1** (so the now-live `deploy-check` gate covers this change), **BLOCK 2** (the dev stack must be up to verify the five one-shot services still boot) |
| **Priority** | P0 — the phase's defining block |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

> Only the Implementor is ever concurrent, and there is only one. The other four run as
> analysis and review passes inside this block.

**Agent requirement decision (the "high risk ⇒ all agents" rule applies here).**
This is the phase's **fragile insertion point**. Four independent reasons, each
sufficient on its own:
- A shipped green test currently asserts the defective behaviour as **intended**
  (`VAL-001`) and must be rewritten in the same change.
- The tail is catastrophic: with the bypass honoured, prod imports with a zero-length
  `SECRET_KEY`, empty `CSRF_TRUSTED_ORIGINS`, empty `REDIS_URL` and empty `BOT_TOKEN`,
  and the **only** signal is one `W009` line in a **non-fatal** boot log
  (`docker/entrypoint.sh`'s `deploy_check()` pipes the failure into
  `|| echo "WARNING: …"`).
- The fix may add a **new settings module**, which changes the settings chain that every
  environment in the compose graph resolves.
- The five dev one-shot services all run `config.settings.prod`, so a scoping rule that
  keys on the settings-module name alone **cannot** distinguish "one-shot in dev" from
  "one-shot in prod" — the report states this explicitly and it is the reason option (a)
  as originally written is wrong.

- **Implementor — yes.** Always.
- **Auditor — yes.** The Auditor must establish, before any code is written: the exact set
  of services that resolve to `config.settings.prod` in each of the three compose stacks;
  whether any non-compose caller (the CI `deploy-check` job, the Dockerfile builder, the
  entrypoints) would be affected by a new module; and the exact blast radius of changing
  the `.env` fail-fast branch's interaction with `DJANGO_BUILD`. The report's evidence is
  forty commits old and the tree moved.
- **Researcher — yes.** The open question is a genuine ecosystem one, not a repo-internal
  derivation: **what is the standard way to distinguish a bootstrap/migration invocation
  from an application-serving invocation when both use the same settings module?** The
  candidate answers — a dedicated settings module, a marker env var plus a non-prod
  signal, a context-local set by the entrypoint, a wrapper management command — have
  materially different failure modes (a stale flag in `.env.prod`; a second settings
  module drifting from `prod`; an entrypoint that must be bypassed when run by hand).
  See §3.3.
- **Planner — yes.** New settings module (possible), changed guard semantics, two
  rewritten tests, an allowlist regroup, a compose change, and a template assertion —
  with an internal ordering constraint. This is the definition of "detailed
  pre-implementation design, architecture, testing, or complex execution".
- **Validator — yes.** HIGH tail; the failure mode is a silently degraded production
  deployment; and the fix is verified by a *negative* assertion (the bypass must now be
  refused) that only exists if the test is written correctly.

**3.3 — Where the bypass should live (open choice; recommendation with rationale, not a
decision).**

| Option | Change | Pro | Con |
|---|---|---|---|
| **A (recommended)** | Add `config/settings/bootstrap.py`: `from .base import *` plus the dev-grade transport flags, and make `prod.py` **unconditionally strict** (no `DJANGO_ONESHOT` branch at all). The dev override switches the five one-shot services to `DJANGO_SETTINGS_MODULE=config.settings.bootstrap` instead of carrying `DJANGO_ONESHOT=1`. | The only option that makes `prod.py` unconditionally strict, which is the actual goal. Scoping is by **module identity**, so no env file can re-enable the bypass. Matches the report's stated preference. | `test_compose_oneshot_flags` and `test_python_consumed_vars_in_allowlist` both key on the string `DJANGO_ONESHOT` and must be **rewritten** (not deleted). A second settings module can drift from `prod` — mitigated by an explicit test asserting the transport-flag parity between `bootstrap` and `dev`. |
| **B** | Keep one settings module. Honour the bypass only when `DJANGO_ONESHOT` is set **and** `DJANGO_SETTINGS_MODULE` does not resolve to a `*.prod` module. | Smallest diff; no new module. | **Does not work as written**: the five dev one-shot services resolve to `config.settings.prod`. Making them resolve to something else is Option A wearing a disguise. If the Planner takes B, the additional non-prod signal (per the report's own aside) must be a *second* condition, and the combination is strictly more machinery than A for strictly less safety. |
| **C** | Keep the flag; require a wrapper: a dedicated management command or entrypoint that sets the context before importing settings. | No env file can trigger it at all. | Reaches across three processes (`migrate`, `load_cities`, `load_catalog`, `create_admin`, `seed`) with different entrypoints, and a developer running `manage.py <cmd>` by hand against the dev DB loses the bypass entirely — a real developer-experience regression. Highest implementation cost. |

**Recommendation:** Option A. The Planner must record which it chose and the Compose
diff each option implies. **This plan does not decide.**

**Findings and notes carried forward.**
1. **`DJANGO_BUILD` is unchanged and out of scope** (G2, decided). It is builder-stage
   only, the runtime image carries no `DJANGO_*`, and
   `test_csrf_trusted_origins_skipped_during_build` pins its behaviour. **State the
   residual honestly in the module docstring:** `DJANGO_BUILD` in `.env.prod` would still
   bypass every guard, because the build stage genuinely needs it and cannot be
   distinguished by a settings module. The mitigation is the report's own, not a code
   change.
2. **The allowlist regroup is part of the fix, not cosmetic.** `DJANGO_BUILD` and
   `DJANGO_ONESHOT` currently sit on the **same line** as `DJANGO_SECRET_KEY` and
   `DJANGO_SETTINGS_MODULE` inside the "Python-consumed" group, which is what makes the
   `.env` channel a silent bypass with no warning. They must move to their own commented
   group stating that they are build/bootstrap control flags which must never appear in a
   production secret file. `test_python_consumed_vars_in_allowlist` asserts
   `DJANGO_ONESHOT` is *present*; splitting them into a separate commented group keeps
   that test green, and the test must **keep** asserting presence.
3. **The `.env.prod.example` assertion is the missing coverage.** `test_compose_hardening`
   covers the Compose channel. The `.env` channel has none. Assert that
   `.env.prod.example` contains neither flag — and, per the report's own recommendation,
   decide whether to also assert the same for the **real** file. (Do not: `.env.prod` is
   gitignored, operator-local, and not deployable anyway.)
4. **The silent-degradation tail is real and the Validator must reason about it.**
   `check --deploy` does **not** touch `SECRET_KEY`, so with the bypass on, `W009` is not
   even emitted at boot; the failure lands on the **first request**, as an
   `ImproperlyConfigured` from `django/conf/__init__.py` on first signing-key access. Do
   not write a test or a docstring that claims the boot log surfaces this.
5. **`base.py`'s `.env` handling has two branches and both are load-bearing for tests.**
   The *missing-file* branch exempts `DJANGO_BUILD`; the *present-file* branch skips
   `read_env()` whenever `DJANGO_SETTINGS_MODULE` contains `"test"`. That skip is exactly
   what lets `test_django_secret_key_required` and `test_bot_token_required_in_production`
   unset a variable and observe the guard. **Any change to the `read_env()` skip
   condition breaks those two tests.** This block must not touch that condition.
6. **`test_migrations.py` is a sixth settings module the report never mentioned** and it
   does `from .test import *`. If a new module is added, the Planner must confirm whether
   it belongs in that inheritance chain and state the answer.
7. **`config.settings` currently has no `bootstrap.py` and the package has no `__init__`
   change pending** — a new module is additive and imports nothing from `prod`.
8. **Five services, three files.** `migrate`, `load_cities`, `load_catalog`,
   `create_admin` and `seed` are declared in `docker-compose.yml` with
   `DJANGO_SETTINGS_MODULE` set there, and each carries its own `DJANGO_ONESHOT=1` in
   `docker-compose.dev.override.yml`. Under Option A **all five** change. A partial edit
   leaves a service on prod settings with no bypass, and it will fail on `EMAIL_HOST` in
   dev. `test_compose_oneshot_flags` iterating `_ONE_SHOT_SERVICES` is the tripwire.

**File surface (semantic units).**
- `src/backend/config/settings/prod.py` → the `_SKIP_SECRET_VALIDATION` definition and
  the explanatory comment block above it (the comment is the primary documentation of the
  whole mechanism and must be rewritten to match whatever Option the Planner chose);
  every `if not _SKIP_SECRET_VALIDATION:` guard branch.
- **Option A only (new):** `src/backend/config/settings/bootstrap.py`.
- `src/backend/config/settings/base.py` → `ALLOWED_ENV_VARS` (the group comment and the
  placement of `DJANGO_BUILD` / `DJANGO_ONESHOT`). **Do not touch** the `.env`
  missing-file branch or the `read_env()` skip condition.
- `docker-compose.dev.override.yml` → the `migrate`, `load_cities`, `load_catalog`,
  `create_admin` and `seed` service blocks.
- `src/backend/config/settings/tests/test_settings_secrets.py` →
  `test_django_oneshot_bypasses_all_secrets` (**rewritten**, `VAL-001`);
  the three prod/dev guard tests remain as-is unless the chosen option changes what they
  assert.
- `src/backend/tests/test_compose_hardening.py` → `test_compose_oneshot_flags`
  (**rewritten** under Option A; still green unchanged under an option that keeps the
  flag in the dev override).
- `src/backend/config/settings/tests/test_env_allowlist.py` →
  `test_python_consumed_vars_in_allowlist` (assertion preserved; extend to cover the new
  grouping) and a **new** `.env.prod.example` absence test.
- **Not touched:** `docker/Dockerfile` (the builder stage is out of scope — G2),
  `docker-compose.prod.yml` (already free of both flags; `test_compose_oneshot_flags`
  proves it), `src/backend/config/settings/test.py`, `dev.py`, `test_migrations.py`.

**Tests required.**
- *Must keep passing unchanged:* `test_django_secret_key_required`,
  `test_bot_token_required_in_production`, `test_google_translate_api_key_required_in_production`,
  `test_redis_url_required_in_production`, `test_csrf_trusted_origins_skipped_during_build`,
  `test_csrf_trusted_origins_required_in_production`, and every `prod.py` placeholder /
  dev-only-dummy rejection test. `test_bot_token_*_in_dev` are retargeted in BLOCK 2 and
  must stay green here.
- *Must be changed:* `test_django_oneshot_bypasses_all_secrets` — inverted to assert that
  the bypass is **not** available to `config.settings.prod` (`VAL-001`). It must be
  **red against the pre-fix code**; if it still passes, the test was not rewritten.
- *Must be added:*
  - `DJANGO_ONESHOT=1` + `DJANGO_SETTINGS_MODULE=config.settings.prod` + a blank
    `SECRET_KEY` **still raises** — the finding's own mandatory assertion.
  - A positive assertion that the bootstrap path still works: the chosen bootstrap
    invocation with dev-only dummy secrets imports cleanly. Without it, the fix could
    simply have removed the bypass and broken the dev stack.
  - Under Option A, a parity assertion that the new module carries the same
    dev-grade transport flags `dev.py` sets, so the two cannot drift.
  - `.env.prod.example` contains neither `DJANGO_ONESHOT` nor `DJANGO_BUILD`.
- *Gate:* `$dc run --rm -e PYTEST_OPTS="src/backend/config/settings/tests src/backend/tests/test_compose_hardening.py" test`
  (the report's own V16 selection — 60 passed in ~81 s at the old anchor; re-baseline),
  then `.\Makefile.ps1 test`, then `docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml config`
  to confirm the resolved settings module per one-shot service.

**Risk / rollback.**
- *Risk (the VAL-001 trap):* applying the report's Rollout-Safety table literally, which
  adds a new assertion and leaves the existing one asserting the opposite. Red suite,
  reverted fix. **The rewrite is in the same change by mandate.**
- *Risk:* the dev override edited for four of the five one-shot services. The fifth fails
  in dev on `EMAIL_HOST`. `test_compose_oneshot_flags` is the tripwire; run it, do not
  assume it.
- *Risk:* a stale `DJANGO_ONESHOT=1` left in a real `.env.prod` after the fix. Under
  Option A it becomes **inert** (the flag is no longer read by `prod.py`) — which is the
  point, and must be stated in the docstring so operators are not misled into thinking
  the flag still does something.
- *Risk:* `base.py`'s `read_env()` skip condition edited in passing, breaking the two
  secret tests. Note 5 forbids it.
- *Rollback:* revert `prod.py`, the compose override, the allowlist grouping and the test
  rewrite **together**. Any partial revert is either a bypassed guard or a broken
  dev stack.

#### BLOCK 3 — Implementation task

> Written by the BLOCK 3 Planner against the tree at `cb31553` (BLOCK 1 = `071e5c7`,
> BLOCK 2 = `cb31553`). This task resolves the Researcher's open decisions, selects the
> mechanism, and is the contract the BLOCK 3 Implementor executes. **Never use line
> numbers** — every target below is a file, module, class, function, variable or
> compose service block.

```yaml
id: block3-cfg001-scope-secret-bypass

title: >
  Scope the secret-validation bypass out of config.settings.prod, and pin the
  bootstrap contract with tests (CFG-001 + VAL-001)

priority: P0

depends_on:
  - "BLOCK 1 (071e5c7) — the restored deploy-check gate must be live before this lands"
  - "BLOCK 2 (cb31553) — the dev stack must be up so the five one-shot services can be verified live"

source_reference: .ai/plans/02-config-secrets-remediation.md
source_section: "BLOCK 3 — Scope the secret-validation bypass (CFG-001 + VAL-001); option analysis in §3.3"
source_file: .ai/audit/99-validation/02-config-secrets-validated-findings.md
source_blocks:
  - "BLOCK 3 — Scope the secret-validation bypass (CFG-001 + VAL-001)"
  - "VAL-001 — CFG-001's remediation is pinned by a shipped green test"
  - "G1 — DJANGO_ONESHOT survives the fix"
  - "G2 — DJANGO_BUILD is replaced by nothing"

description: >
  `config/settings/prod.py` currently decides whether to run its seven secret guards by
  reading DJANGO_BUILD or DJANGO_ONESHOT from os.environ with no reference to which
  settings module is being loaded. Both variables are read through the same mechanism as
  the secrets themselves (django-environ `read_env(overwrite=False)` on the bind-mounted
  `.env`), so an operator who writes one line into `.env.prod` opens every guard at once
  and gets no warning: both names are in `ALLOWED_ENV_VARS`, and `check --deploy` does
  not emit W009 for a zero-length SECRET_KEY, so the failure lands on the first request.

  This task moves the dev-bootstrap bypass out of `prod.py` into a dedicated settings
  module whose selection is made by the *deployment descriptor* (Compose `environment:`,
  which is the process environment before `read_env()` runs and which `overwrite=False`
  cannot overwrite). `prod.py` stops honouring `DJANGO_ONESHOT` whenever the process is
  loading a `*.prod` settings module, and emits a one-line warning when it observes the
  flag in that situation, so the operator error becomes self-explaining instead of
  silent. `DJANGO_BUILD` is untouched: the Dockerfile builder stage and `make restore-test`
  genuinely need it and cannot be distinguished by a settings module.

  The same change must rewrite `test_django_oneshot_bypasses_all_secrets`, which today
  asserts the defective behaviour as intended (VAL-001), and must add the positive
  bootstrap-path assertion so that "remove the bypass and break the dev stack" cannot
  pass.

goals:
  - >
    Make `config.settings.prod` unconditionally strict with respect to DJANGO_ONESHOT:
    the flag has no effect on a `*.prod` settings module.
  - >
    Keep the five dev one-shot bootstrap services booting with dev placeholder secrets,
    by giving them a settings module that is selected by the deployment descriptor.
  - >
    Keep DJANGO_BUILD honoured by `prod.py` for the Docker builder stage and
    `Makefile`'s `restore-test` target, with test coverage that proves it.
  - >
    Rewrite the shipped green test that asserts the bypass (VAL-001) in the same change,
    asserting the negative, and add a positive bootstrap-path assertion beside it.
  - >
    Regroup DJANGO_BUILD and DJANGO_ONESHOT into a commented sub-group inside the same
    ALLOWED_ENV_VARS literal, and add the missing `.env` template-channel coverage.
  - >
    Leave no silent operator trap: a stale or stray DJANGO_ONESHOT in any `.env` file
    produces a loud, value-free warning naming the flag.
  - >
    Change no file outside the declared surface; touch nothing under `.ai/audit/**`.

# ─────────────────────────────────────────────────────────────────────────────
# Decisions taken by the BLOCK 3 Planner (the Researcher's open decisions)
# ─────────────────────────────────────────────────────────────────────────────
decisions:
  - id: "D1 — mechanism: Option D, not Option A"
    choice: >
      Add `src/backend/config/settings/oneshot.py`, which does `from .prod import *`
      and then re-pins `DEBUG = False`. The bypass is obtained because the process
      resolves `DJANGO_SETTINGS_MODULE=config.settings.oneshot`, not because any flag
      says so at the module level; `prod.py` honours DJANGO_ONESHOT only while the
      loaded module is not a `*.prod` module.
    rationale: >
      Option A (a standalone `bootstrap.py` built from `base`) needs a ~46-line copy of
      `prod.py`'s LOGGING block that must be kept in sync forever, plus a parity test to
      catch drift, plus four explicit "do not inherit from dev" decisions. Option D
      eliminates the copy, the parity test and the hazard list *by construction*: a
      setting added to `prod.py` is picked up automatically instead of silently going
      stale. It is roughly fifteen lines against A's ninety. A's only advantage — a new
      module that does not star-import a stronger module — is a readability concern, and
      is mitigated by an explicit module docstring plus the parity test below.
    honest_cost: >
      `from .prod import *` reads as a dependency inversion: bootstrap is *weaker* than
      production, yet the arrow points from the weaker thing to the stronger. The
      mitigation is a docstring and a test, not an enforcement mechanism. State this in
      the docstring rather than leaving a future reader to guess.

  - id: "D2 — module name: oneshot.py, not oneshot_prod.py"
    choice: "config/settings/oneshot.py"
    rationale: >
      Both `base.py`'s missing-`.env` hint and `docker/entrypoint.sh`'s `check_env_file`
      classify a process as production by a `.prod` module-name suffix. The new module is
      dev-only, and the only shipped configuration that uses it is a **dev** one-shot —
      so `oneshot.py` yields the *correct* `.env.dev` hint on a missing `.env`, while
      `oneshot_prod.py` would yield the wrong `.env.prod` hint in the real case. The
      inverse error (a production one-shot pointed at a dev-only module printing the
      `.env.dev` hint) is a misconfiguration, is error text only, and exits 1 either way.
      `oneshot_prod.py` additionally reads as production to humans and to `grep`, which is
      the worse failure. The gotcha must be acknowledged in the module docstring.

  - id: "D3 — inert-flag warning: YES, add it"
    choice: >
      `prod.py` emits a one-line, value-free `logger.warning` when it observes
      DJANGO_ONESHOT set while the loaded settings module is a `*.prod` module. The
      message must begin with the exact string `DJANGO_ONESHOT is set but ignored` so the
      test and the documentation can pin it.
    rationale: >
      It warns rather than bypasses, so it does not violate the "DJANGO_ONESHOT is inert
      in production" goal, and it converts the highest-value residual — operator
      confusion over a flag that suddenly does nothing — from a silent no-op into a
      self-explaining one, at the exact moment the operator is doing the dangerous thing.
      It must be emitted **above** the first guard so it is visible even when a guard
      raises and the import aborts. Use `logging.getLogger(__name__).warning(...)`, the
      module-local convention already used by the Sentry block in the same file; do not
      use `print()` (project rule 12). At settings-import time no handler is configured,
      so CPython's `logging.lastResort` writes the record to stderr at WARNING level —
      which is what makes the assertion on the subprocess's `stderr` meaningful.

  - id: "D4 — dev override env lines: leave them"
    choice: >
      The per-service `SITE_URL`, `GOOGLE_TRANSLATE_API_KEY` and
      `CSRF_TRUSTED_ORIGINS` dev-override lines stay exactly as they are. Only
      `DJANGO_SETTINGS_MODULE` is added and the stale comments are corrected.
    rationale: >
      They are a separate concern (dev one-shots still need values for the guards that
      stay active under the new module) and touching them expands the diff into
      configuration nobody asked to change. Their **comments**, however, assert something
      this change makes false and must be corrected in the same edit.

  - id: "D5 — test assertions"
    choice: >
      Specified in full under `tests:` below. The rewritten test is negative plus a
      warning assertion; the positive bootstrap-path pair lives in a new module and
      asserts both directions (flag honoured, flag absent refused).

  - id: "D6 — allowlist group wording and template assertion"
    choice: >
      A commented sub-group **inside the same `frozenset({...})` literal** stating that
      both names are bootstrap/build control flags honoured only from the process
      environment and never from a production `.env` file. The absence assertion is
      `test_bypass_flags_absent_from_env_templates`, parametrized over
      `.env.prod.example` and `.env.example`, reusing the existing `_example_keys`
      helper.

  - id: "D7 — documentation"
    choice: >
      Three files are updated (below). The hand-typed-command developer-experience
      regression is documented with a runnable one-liner, and DJANGO_ONESHOT's new
      inert-in-production status is stated in the same place. No template gains the flag.

  - id: "D8 — cookiecutter-django restructure: record, do not do"
    choice: "Out of scope for this block. Recorded as a follow-up below."

recorded_follow_ups:
  - >
    **Do not run production settings at image build / move `collectstatic` to container
    start** (the cookiecutter-django shape, and what the Researcher's survey found no
    counter-example to). It would let `DJANGO_BUILD` be deleted entirely and would close
    the residual below by construction. It is a Dockerfile and image-pipeline change, it
    touches the CI `build` and `load-test` jobs, and it is not a CFG-001 remedy. Recorded
    here; the coordinator may route it to a later block. Do not start it.
  - >
    **Consolidate the duplicated prod-env builders / subprocess helpers** — already
    out of scope for this plan (§6). This task must not create a fifth copy (see
    `files:` for `test_oneshot_settings.py`).

# ─────────────────────────────────────────────────────────────────────────────
# Binding constraints — violating any of these reddens a shipped green test,
# breaks a live build, or re-opens the finding
# ─────────────────────────────────────────────────────────────────────────────
binding_constraints:
  - id: BC-1
    rule: >
      DJANGO_ONESHOT and DJANGO_BUILD must both remain members of ALLOWED_ENV_VARS.
      Move them into a commented sub-group **inside the same frozenset literal**;
      deleting or relocating either out of the literal reds
      `test_env_allowlist.py::test_python_consumed_vars_in_allowlist`.
    accepted_consequence: >
      `_warn_unknown_env_vars` can never warn on these two names. The commented sub-group
      plus the template-absence assertion are the only available coverage for the `.env`
      channel. Do not attempt to "fix" this by removing them from the allowlist.
  - id: BC-2
    rule: >
      prod.py must keep honouring DJANGO_BUILD. Three things break otherwise:
      `test_csrf_trusted_origins_skipped_during_build` goes red; the Dockerfile
      **builder** stage breaks the CI `build` job and `load-test` with it (it runs
      `collectstatic` and `compilemessages` under config.settings.prod with placeholder
      values and **no `.env`**, because `.dockerignore` excludes `**/.env*`); and
      `Makefile`'s `restore-test` target breaks — a second prod-settings bypass channel
      outside compose and outside the image, running `manage.py migrate --plan --check`
      with `DJANGO_BUILD=1` under `DJANGO_SETTINGS_MODULE=config.settings.prod`
      (documented at `docs/ops/restore.md`, section "Migrate --plan --check").
    note: >
      The `_SKIP_SECRET_VALIDATION` *variable* may be narrowed; the DJANGO_BUILD *branch*
      may not be removed.
  - id: BC-3
    rule: >
      base.py's present-file skip condition — the `"test" not in os.getenv("DJANGO_SETTINGS_MODULE", "")`
      branch that guards `read_env()` — must not be edited.
    why: >
      It is strictly load-bearing: `read_env()` restores a non-empty DJANGO_SECRET_KEY from
      the bind-mounted `.env.test`, so removing the skip turns
      `test_django_secret_key_required` and `test_bot_token_required_in_production` red.
      (The second of those is nominally governed by `read_env`'s `overwrite=False`
      semantics with a present-but-empty value, not by the "test" substring — the value
      must be set present-but-empty in the subprocess env, and that is how it is written
      today.)
  - id: BC-4
    rule: >
      base.py's missing-file branch must not gain a DJANGO_ONESHOT exemption and must not
      lose its DJANGO_BUILD one. The latter is the only thing standing between the image
      build and `sys.exit(1)`.
  - id: BC-5
    rule: >
      All five dev one-shot services change together or none do. A four-of-five edit
      produces a fifth service that dies at import on its first prod guard, and
      `test_compose_oneshot_flags`'s dev half names the missed service.
  - id: BC-6
    rule: >
      `test_django_oneshot_bypasses_all_secrets` must be rewritten in the same change,
      and the rewrite must assert the **negative** *and* a positive bootstrap-path
      assertion. A rewrite that only inverts the existing assertion leaves the fix
      "remove the bypass and break the dev stack" able to pass.
  - id: BC-7
    rule: >
      base.py's LOGGING absence is load-bearing for the design: `base.py` defines no
      LOGGING at all, so a module that did not carry prod's would fall back to Django's
      plaintext DEFAULT_LOGGING. `test_prod_logging.py` pins LOGGING for
      `config.settings.prod` **only**, so a dropped LOGGING on the new module would go
      undetected. That is why D3's parity test below exists.
  - id: BC-8
    rule: >
      Preserve `bool(os.getenv(...))` truthiness semantics exactly for both flags. An
      empty `DJANGO_ONESHOT=` in a `.env` file is "not set" today and must stay "not set",
      and it must not produce the warning.
  - id: BC-9
    rule: >
      Do not add DJANGO_ONESHOT or DJANGO_BUILD to any `.env.*.example` template. The
      templates are the operator-facing documentation of this contract; adding the flag
      to `.env.dev.example` would re-open the same class of trap, because `.env.dev` is
      bind-mounted to `/app/src/.env` and read by `read_env()`.
  - id: BC-10
    rule: >
      The dev stack must be left running at the end of the block. BLOCK 2 landed with
      `web` and `bot` Up; a dev stack that is down at hand-off is a regression this block
      introduced, not a pre-existing condition.

residual_risk: >
  Stated in the new module's docstring, in these words or equivalent: **DJANGO_BUILD=1
  written into `.env.prod` would still bypass every guard.** The build stage genuinely
  needs it and cannot be distinguished by a settings module, and `Makefile`'s
  `restore-test` is the same channel. The mitigation is the commented ALLOWED_ENV_VARS
  sub-group plus the `.env.prod.example` absence assertion — **not** a code change. Do
  not write a docstring, a test, a commit message or a summary claiming the boot log
  surfaces this failure: `check --deploy` does not touch SECRET_KEY, so W009 is not even
  emitted at boot, and the failure lands on the first request.

# ─────────────────────────────────────────────────────────────────────────────
files:
  - path: src/backend/config/settings/oneshot.py
    status: new
    targets:
      - type: module
        name: config.settings.oneshot
      - type: module_docstring
        name: "bootstrap one-shot settings"
      - type: star_import
        name: ".prod"
      - type: variable
        name: DEBUG
    semantic_anchors:
      first_statement: '"""Bootstrap settings for one-shot services."""'
      must_contain: ["from .prod import *", "DEBUG = False"]
      must_not_contain:
        - "config.settings.dev"
        - "config.settings.base"
        - "LocMemCache"
        - "console.EmailBackend"

  - path: src/backend/config/settings/prod.py
    targets:
      - type: comment_block
        name: "Secret-validation bypass flags"
      - type: variable
        name: _SKIP_SECRET_VALIDATION
      - type: function
        name: _is_production_settings_module
      - type: guard_block
        name: "the SECRET_KEY / BOT_TOKEN / GOOGLE_TRANSLATE_API_KEY / SITE_URL / EMAIL_HOST / CSRF_TRUSTED_ORIGINS / REDIS_URL guards"
    semantic_anchors:
      replace_definition: "_SKIP_SECRET_VALIDATION"
      insert_before:
        type: if_statement
        value: "if not _SKIP_SECRET_VALIDATION:  # the first SECRET_KEY guard"
      do_not_edit:
        - "_validate_production_secret (body and signature)"
        - "ALLOWED_HOSTS unconditional guard"
        - "the transport pins (DEBUG, SECURE_*, SECURE_PROXY_SSL_HEADER, USE_X_FORWARDED_HOST, HSTS triple)"
        - "the LOGGING dict"
        - "the Sentry init block"
        - "STATICFILES_STORAGE"

  - path: src/backend/config/settings/base.py
    targets:
      - type: variable
        name: ALLOWED_ENV_VARS
      - type: comment_block
        name: "Python-consumed group header"
    semantic_anchors:
      contains: "the same frozenset({...}) literal, same import block, nothing else"
      do_not_edit:
        - "the missing-.env branch (its DJANGO_BUILD exemption and the sys.exit(1))"
        - 'the "test" not in os.getenv("DJANGO_SETTINGS_MODULE", "") read_env skip'
        - "_warn_unknown_env_vars"

  - path: docker-compose.dev.override.yml
    targets:
      - type: service_block
        name: migrate
      - type: service_block
        name: load_cities
      - type: service_block
        name: load_catalog
      - type: service_block
        name: create_admin
      - type: service_block
        name: seed
    semantic_anchors:
      add_next_to: "- DJANGO_ONESHOT=1"
      add_value: "- DJANGO_SETTINGS_MODULE=config.settings.oneshot"
      do_not_edit:
        - "the SITE_URL / GOOGLE_TRANSLATE_API_KEY / CSRF_TRUSTED_ORIGINS lines"
        - "profiles: !reset []"
        - "the web and bot service blocks"
        - "the volumes blocks"

  - path: src/backend/config/settings/tests/test_settings_secrets.py
    targets:
      - type: function
        name: test_django_oneshot_bypasses_all_secrets
    semantic_anchors:
      replaces: "test_django_oneshot_bypasses_all_secrets (renamed; see tests: below)"
      do_not_edit:
        - "_run_in_subprocess"
        - "_dev_env_overrides"
        - "every other test in the module"

  - path: src/backend/config/settings/tests/test_oneshot_settings.py
    status: new
    targets:
      - type: module
        name: test_oneshot_settings
    semantic_anchors:
      import_from: "config.settings.tests (TEST_SECRET_KEY, TEST_BOT_TOKEN, TEST_TRANSLATE_KEY) and config.settings.tests.test_prod_logging (_run_in_subprocess, _prod_env_overrides)"
      must_not_contain:
        - "a new subprocess.run helper"
        - "a new prod-env builder copy"
    note: >
      The established cross-module import precedent is
      `from config.settings.tests.test_prod_logging import TEST_SECRET_KEY, _prod_env_overrides`
      in test_settings_secrets.py. Reuse it; §6 forbids creating a fifth copy of either
      helper. `test_prod_logging._run_in_subprocess` returns a `CompletedProcess`, which is
      what these tests need (returncode, stdout, stderr).

  - path: src/backend/tests/test_compose_hardening.py
    targets:
      - type: function
        name: test_compose_oneshot_flags
    semantic_anchors:
      edit_region: "the dev half only (the loop over _ONE_SHOT_SERVICES against _DEV_OVERRIDE_COMPOSE)"
      do_not_edit:
        - "the prod half loop"
        - "_ONE_SHOT_SERVICES"
        - "_service_block"

  - path: src/backend/config/settings/tests/test_env_allowlist.py
    targets:
      - type: function
        name: test_python_consumed_vars_in_allowlist
      - type: helper
        name: _example_keys
      - type: new_function
        name: test_bypass_flags_absent_from_env_templates
    semantic_anchors:
      do_not_edit:
        - "test_python_consumed_vars_in_allowlist (its presence assertions must keep passing untouched)"
        - "_example_keys"
        - "test_example_keys_in_allowlist"

  - path: docs/ops/docker-deployment.md
    targets:
      - type: list_item
        name: "the DJANGO_ONESHOT=1 environment-variable bullet"
      - type: paragraph
        name: "the prod.py import-time validation paragraph that lists the two bypass cases"
    semantic_anchors:
      note: >
        §5.3 records this file as contended. `git status --short` is currently clean, but
        re-read immediately before editing and stage this path explicitly.

  - path: docs/99-agent/architecture.md
    targets:
      - type: list_item
        name: "the guard-skipped-under note for REDIS_URL / EMAIL_HOST"
      - type: list_item
        name: "the DJANGO_BUILD=1 Dockerfile ENV note"
      - type: table_row
        name: "the EMAIL_HOST row of the env-var table"
    semantic_anchors:
      note: "same read-before-edit discipline as above"

  - path: docs/ops/migration-workflow.md
    targets:
      - type: paragraph
        name: "the DJANGO_BUILD=1 / DJANGO_ONESHOT=1 statement"
    semantic_anchors:
      add: "the hand-run recipe (see changes: id change_docs)"

  - path: docker/Dockerfile
    status: not_touched
  - path: Makefile
    status: not_touched
  - path: docker-compose.yml
    status: not_touched
  - path: docker-compose.prod.yml
    status: not_touched
  - path: docker-compose.test.yml
    status: not_touched
  - path: src/backend/config/settings/dev.py
    status: not_touched
  - path: src/backend/config/settings/test.py
    status: not_touched
  - path: src/backend/config/settings/test_migrations.py
    status: not_touched
  - path: src/telegram_bot/main.py
    status: not_touched
  - path: .env.prod.example
    status: not_touched
  - path: docs/ops/restore.md
    status: not_touched
    note: "its DJANGO_BUILD=1 description remains accurate after this change"

# ─────────────────────────────────────────────────────────────────────────────
changes:

  - action: add_file
    id: change_oneshot_module
    path: src/backend/config/settings/oneshot.py
    description: >
      New bootstrap settings module, roughly fifteen lines plus a docstring. It star-imports
      `prod`, so it carries prod's guards, prod's LOGGING, the Sentry init, the transport
      pins, `STATICFILES_STORAGE` and `ALLOWED_HOSTS` — and therefore automatically picks
      up any future setting added to `prod.py`. It re-pins `DEBUG = False` explicitly so
      the pin is visible in the module that exists for bootstrap, rather than inherited
      from `base`, which reads DEBUG from the gitignored `.env`.

      The docstring must state, in this order: what the module is for (one-shot bootstrap
      services that serve no HTTP traffic); that it must never serve requests; that it
      inherits from `prod` on purpose and that the arrow is a dependency inversion, because
      bootstrap is weaker than production; that the DJANGO_ONESHOT bypass reaches it only
      because the process resolves this module, never because a `.env` file can select it;
      the D2 name-mangling caveat (a missing `.env` here prints the `.env.dev` hint, which
      is correct for this module's only shipped use); and the residual above, verbatim in
      substance.

      It must NOT import from `dev` — not for `DEBUG = True`, not for the console
      `EMAIL_BACKEND` (CFG-004's harm class: the one-shots run `migrate_locked` backfills
      that can send mail), not for the `LocMemCache` `CACHES` (that would silently unshare
      the rate-limit and stale-while-revalidate caches from `web` and `bot`), and not for
      dev's plain-console `LOGGING`. It must not join the
      `config.settings.test_migrations` → `test` → `base` chain: the test stack resolves
      every service to `config.settings.test`, so a module here is unreachable from it.
    code_hint: |
      """
      Bootstrap settings for one-shot services (migrate, load_cities, load_catalog,
      create_admin, seed). ... [full docstring per the description above]
      """

      from .prod import *  # noqa: F403, F401

      # Re-pinned: base.py reads DEBUG from the .env file, which is not present
      # in every bootstrap invocation. A bootstrap process must never run with
      # DEBUG enabled.
      DEBUG = False

  - action: modify
    id: change_prod_bypass
    path: src/backend/config/settings/prod.py
    description: >
      Rewrite the bypass comment block and the flag expression; add the inert-flag
      warning. The seven guard sites themselves are pure raises and change **structurally
      not at all** — only the predicate that decides whether they run changes. This is what
      makes the diff auditable: if a guard block moves, something is wrong.

      The new flag expression must express, in one named predicate plus one expression:
      DJANGO_BUILD is honoured unconditionally; DJANGO_ONESHOT is honoured only while the
      loaded settings module is not a `*.prod` module. Use a module-level constant for the
      `".prod"` suffix rather than an inline literal (project rule 10), and keep the shell's
      suffix semantics so the Python predicate and `docker/entrypoint.sh` classify
      production identically.

      Add immediately after the flag computation, and **above** the first guard, a
      `logging.getLogger(__name__).warning(...)` whose message begins with the exact
      prefix `DJANGO_ONESHOT is set but ignored` and names `DJANGO_SETTINGS_MODULE` and the
      remediation. No `print()`; no `import sys`.

      Rewrite the six per-guard comments that currently say "Skip during Docker build
      (DJANGO_BUILD=1) and dev one-shot services (DJANGO_ONESHOT=1)": the second half is
      now false for this module. The accurate statement is that the guard is skipped
      during the Docker image build, and that dev bootstrap one-shots run
      `config.settings.oneshot` — they do not run this module. The top comment block must
      be rewritten in full: it is the primary documentation of the mechanism, and it
      currently teaches a reader that writing the flag into the environment is safe.
    code_hint: |
      _PRODUCTION_SETTINGS_MODULE_SUFFIX = ".prod"


      def _is_production_settings_module() -> bool:
          """True when the process is loading a production settings module.

          DJANGO_SETTINGS_MODULE is set in the process environment before settings
          import (manage.py, wsgi.py and asgi.py all setdefault it, and Compose sets
          it per service). read_env() uses overwrite=False, so a value written into
          a .env file cannot move an already-set process onto a non-production
          module. That is the trust boundary this predicate relies on.
          """
          return os.getenv("DJANGO_SETTINGS_MODULE", "").endswith(
              _PRODUCTION_SETTINGS_MODULE_SUFFIX
          )


      _ONESHOT_REQUESTED = bool(os.getenv("DJANGO_ONESHOT"))
      _SKIP_SECRET_VALIDATION = bool(
          os.getenv("DJANGO_BUILD")
          or (_ONESHOT_REQUESTED and not _is_production_settings_module())
      )
      if _ONESHOT_REQUESTED and _is_production_settings_module():
          logging.getLogger(__name__).warning(
              "DJANGO_ONESHOT is set but ignored: this process loaded the production "
              "settings module (DJANGO_SETTINGS_MODULE=%s), which always validates "
              "secrets. Remove DJANGO_ONESHOT from the environment and from the .env "
              "file; dev bootstrap services use config.settings.oneshot instead.",
              os.getenv("DJANGO_SETTINGS_MODULE", ""),
          )

  - action: modify
    id: change_allowlist_regroup
    path: src/backend/config/settings/base.py
    description: >
      Move DJANGO_BUILD and DJANGO_ONESHOT out of the "Python-consumed" line, where they
      sit on the same physical line as DJANGO_SECRET_KEY and DJANGO_SETTINGS_MODULE —
      the arrangement that makes the `.env` channel a silent bypass — into their own
      commented sub-group **inside the same frozenset literal**, stating that they are
      build/bootstrap control flags honoured only from the process environment, that
      DJANGO_ONESHOT is ignored outright under a `*.prod` settings module, and that
      neither may ever appear in a production secret file.

      Add nothing and remove nothing. Do not touch the two `.env` branches (BC-3, BC-4).
    code_hint: |
          # --- Bootstrap control flags (honoured only from the process environment) ---
          # DJANGO_BUILD: Docker image builder stage only (collectstatic, no .env file).
          # DJANGO_ONESHOT: dev bootstrap one-shots, which run config.settings.oneshot.
          # Both are ignored by config.settings.prod; never add either to .env.prod.
          "DJANGO_BUILD", "DJANGO_ONESHOT",

  - action: modify
    id: change_compose_dev
    path: docker-compose.dev.override.yml
    description: >
      For all five one-shot service blocks — `migrate`, `load_cities`, `load_catalog`,
      `create_admin`, `seed` — add
      `- DJANGO_SETTINGS_MODULE=config.settings.oneshot` next to the existing
      `- DJANGO_ONESHOT=1`, and keep the flag. Both are now load-bearing: the module name
      decides whether the flag counts, and the flag decides whether the guards run.

      Compose merges `environment` by key across files and normalises list and map
      syntax, so the override value replaces the base file's
      `config.settings.prod`. The `web` and `bot` blocks already rely on exactly this
      merge today. Confirm it with the `docker compose config` gate rather than assuming.

      Correct the per-service comments, which currently say "uses prod settings (base
      compose)" and "to bypass the one-shot secret-validation guards" — both become false.
      The `seed` block carries a longer comment paragraph making the same claim; rewrite
      it to state that seed runs `config.settings.oneshot` and therefore still inherits
      prod's LOGGING, DEBUG=False and the base Redis cache.

      Do not touch `profiles: !reset []`, the volumes, the `SITE_URL` /
      `GOOGLE_TRANSLATE_API_KEY` / `CSRF_TRUSTED_ORIGINS` lines (D4), or the `web`/`bot`
      blocks.
    code_hint: |
        environment:
          - SITE_URL=${SITE_URL:-http://localhost:8000}
          - GOOGLE_TRANSLATE_API_KEY=${GOOGLE_TRANSLATE_API_KEY:-dev-only-dummy-key-not-for-production}
          - CSRF_TRUSTED_ORIGINS=${CSRF_TRUSTED_ORIGINS:-http://localhost:8000}
          - DJANGO_ONESHOT=1
          # Bootstrap settings module: dev one-shots are not production, so the
          # DJANGO_ONESHOT bypass is honoured here and nowhere else.
          - DJANGO_SETTINGS_MODULE=config.settings.oneshot

  - action: rewrite_test
    id: change_test_secrets
    path: src/backend/config/settings/tests/test_settings_secrets.py
    description: >
      VAL-001 (BC-6). Replace `test_django_oneshot_bypasses_all_secrets` with a negative
      test of the same subject. Keep it in this file, in this module, using the module's
      existing `subprocess.run` invocation style so the diff reads as an inversion rather
      than a deletion. The docstring must say what the old test asserted and why that was
      wrong, so the next reader does not re-add it.

      This test must be **red against the pre-fix code**. The Implementor demonstrates
      this by stashing the `prod.py` hunk and re-running it (see the gate's negative
      control), and records the result. A test that never went red proves nothing.
    code_hint: |
      def test_django_oneshot_does_not_bypass_prod_secrets() -> None:
          """DJANGO_ONESHOT no longer opens the prod guards for a *.prod module.

          The former test_django_oneshot_bypasses_all_secrets asserted the opposite.
          The bypass now reaches only config.settings.oneshot, and only because the
          deployment descriptor selected that module.
          """
          env = _prod_env_overrides(
              DJANGO_SECRET_KEY="dev-only-dummy-key-not-for-production",
              BOT_TOKEN="dev-only-dummy-key-not-for-production",
              GOOGLE_TRANSLATE_API_KEY="dev-only-dummy-key-not-for-production",
              EMAIL_HOST="",
              SITE_URL="",
          )
          env["CSRF_TRUSTED_ORIGINS"] = ""
          env["DJANGO_ONESHOT"] = "1"
          result = subprocess.run(...)
          assert result.returncode != 0, result.stderr
          assert "ImproperlyConfigured" in result.stderr
          assert "DJANGO_SECRET_KEY" in result.stderr
          assert "DJANGO_ONESHOT is set but ignored" in result.stderr

  - action: add_tests
    id: change_test_oneshot_module
    path: src/backend/config/settings/tests/test_oneshot_settings.py
    description: >
      New test module owning the contract of the new settings module: the positive
      bootstrap path, the mechanism's two halves, the build-flag regression, and the
      drift/parity assertions that a star-import makes necessary. Every test is
      subprocess-isolated for the same reason every sibling test is: settings are
      evaluated at import time and `override_settings` cannot test them.

      Build the environment by copying `_prod_env_overrides` from `test_prod_logging.py`
      and overriding the module name plus the dev-dummy profile, in a single local helper.
      Do not add a subprocess helper (reuse `test_prod_logging._run_in_subprocess`) and do
      not add a second prod-env builder. Reuse `config.settings.tests`' constants rather
      than writing new credential-shaped literals, so `.gitleaks.toml`'s allowlist keeps
      matching.
    code_hint: |
      _BOOTSTRAP_MODULE = "config.settings.oneshot"
      _DEV_DUMMY_SECRET = "dev-only-dummy-key-not-for-production"


      def _bootstrap_env(*, oneshot_flag: bool = True) -> dict[str, str]:
          env = _prod_env_overrides(
              DJANGO_SECRET_KEY=_DEV_DUMMY_SECRET,
              BOT_TOKEN=_DEV_DUMMY_SECRET,
              GOOGLE_TRANSLATE_API_KEY=_DEV_DUMMY_SECRET,
              EMAIL_HOST="",
              SITE_URL="",
              CSRF_TRUSTED_ORIGINS="",
          )
          env["DJANGO_SETTINGS_MODULE"] = _BOOTSTRAP_MODULE
          env.pop("DJANGO_ONESHOT", None)
          if oneshot_flag:
              env["DJANGO_ONESHOT"] = "1"
          return env

  - action: modify_test
    id: change_test_compose
    path: src/backend/tests/test_compose_hardening.py
    description: >
      Rewrite the **dev half** of `test_compose_oneshot_flags` so it asserts both halves of
      the new mechanism for every service in `_ONE_SHOT_SERVICES`, and add one assertion
      that pins the module's blast radius: the string `config.settings.oneshot` must appear
      in the dev override and **nowhere** in `docker-compose.yml` or
      `docker-compose.prod.yml`. That single assertion is what keeps the prod half and the
      test stack (which resolves everything to `config.settings.test`) honest without
      editing either.

      Leave the prod half byte-identical. Update the module comment above
      `_ONE_SHOT_SERVICES` and the section header comment, which both describe the old
      mechanism.
    code_hint: |
        # Dev: every one-shot service must run the bootstrap settings module and
        # carry the flag that module honours.
        for service in _ONE_SHOT_SERVICES:
            block = _service_block(_DEV_OVERRIDE_COMPOSE, service)
            assert f"DJANGO_SETTINGS_MODULE={_BOOTSTRAP_MODULE}" in block, (
                f"{service} in dev override must set DJANGO_SETTINGS_MODULE={_BOOTSTRAP_MODULE}"
            )
            assert "DJANGO_ONESHOT=1" in block, (
                f"{service} in dev override must set DJANGO_ONESHOT=1"
            )

        # The bootstrap module is dev-only: no other stack may reference it.
        for path in (_COMPOSE, _PROD_COMPOSE):
            assert _BOOTSTRAP_MODULE not in path.read_text(encoding="utf-8"), (
                f"{path.name} must not reference {_BOOTSTRAP_MODULE}"
            )

  - action: add_test
    id: change_test_env_template
    path: src/backend/config/settings/tests/test_env_allowlist.py
    description: >
      Add the missing coverage for the `.env` channel. `test_compose_hardening.py` covers
      the Compose channel; nothing covered the template channel, which is the channel the
      finding's realistic trigger actually uses. Reuse the existing `_example_keys` helper
      so the parsing rule (skip comments and blanks, split on the first `=`) matches the
      allowlist test exactly. Parametrize over the two files an operator is most likely to
      copy from; `.env.dev.example` and `.env.test.example` are out of scope by design
      (BC-9) and adding them to the parametrization would only invite someone to add the
      flag to one of them.

      Do not assert anything about the real, gitignored `.env.prod` — it is
      operator-local and unversioned, and a test that reads it is a test that fails on a
      developer's machine.
    code_hint: |
      @pytest.mark.parametrize("filename", [".env.prod.example", ".env.example"])
      def test_bypass_flags_absent_from_env_templates(filename: str) -> None:
          """DJANGO_BUILD and DJANGO_ONESHOT must never appear in a .env template.

          Both are honoured only from the process environment. Shipping either in a
          template would teach operators to put a guard-disabling flag in a secret
          file — the exact CFG-001 trigger.
          """
          present = _BYPASS_FLAGS & _example_keys(filename)
          assert not present, f"{filename} must not define {sorted(present)}"

  - action: update_docs
    id: change_docs
    paths:
      - docs/ops/docker-deployment.md
      - docs/99-agent/architecture.md
      - docs/ops/migration-workflow.md
    description: >
      Three documentation surfaces state the old mechanism and would become false:

      1. `docs/ops/docker-deployment.md` — the environment-variable bullet for
         DJANGO_ONESHOT and the paragraph listing the two cases in which prod.py's
         validation is bypassed. Both must say the flag is honoured only when the process
         is not loading a `*.prod` settings module, that dev one-shots run
         `config.settings.oneshot`, and that the flag is ignored (with a boot warning) if
         it appears under production settings.
      2. `docs/99-agent/architecture.md` — the guard-skipped-under notes, the DJANGO_BUILD
         Dockerfile-ENV note, and the `EMAIL_HOST` row of the env-var table. These should
         be corrected only where they assert the one-shot behaviour; do not rewrite the
         surrounding architecture prose.
      3. `docs/ops/migration-workflow.md` — the paragraph that states both flags make prod
         settings accept dev values. Correct it, and add the **hand-typed-command
         developer-experience regression**: a developer running `manage.py <cmd>` by hand
         against the dev database no longer gets the bypass implicitly, because
         `manage.py` defaults DJANGO_SETTINGS_MODULE to `config.settings.prod`. Give the
         runnable one-liner that restores it, and say plainly that omitting it now fails on
         the first production guard rather than silently doing the wrong thing.

      Both contested doc files (§5.3) must be re-read immediately before editing, and
      staged by explicit path. No user-visible string is introduced, so the i18n
      completeness gate is not triggered — but it must still pass.
    code_hint: |
      DJANGO_SETTINGS_MODULE=config.settings.oneshot DJANGO_ONESHOT=1 \
        python src/backend/manage.py <command>

# ─────────────────────────────────────────────────────────────────────────────
sequence:
  - step: 0
    name: preflight
    actions:
      - "Confirm BLOCK 1 (071e5c7) and BLOCK 2 (cb31553) are the two most recent commits and the dev stack is Up."
      - "`git status --short` and re-read the six binding constraints against the tree. The tree is the authority over this task where they disagree."
      - "Confirm the Docker test DB is Up (`.\\Makefile.ps1 test-db`)."
      - "Baseline the scoped suite before editing, so a pre-existing failure is not attributed to this change."
    gate: "scoped settings + compose run is green at baseline"
  - step: 1
    name: add the bootstrap settings module
    depends_on: [0]
    actions:
      - "Create `config/settings/oneshot.py` per `change_oneshot_module`."
    note: >
      Additive and inert: nothing imports it yet, so this step cannot break anything.
      Do it first so the module's own import is proven before it is wired into compose.
  - step: 2
    name: narrow the bypass in prod.py
    depends_on: [1]
    actions:
      - "Apply `change_prod_bypass`: predicate, flag expression, warning, comment rewrite."
    warning: >
      **The suite is red from here until step 5.** `test_django_oneshot_bypasses_all_secrets`
      now fails, and the five dev one-shots would die at import if the stack were restarted.
      This is the VAL-001 trap made visible. Do not weaken the test to get back to green —
      fix it in step 5. Run no gate inside this window.
  - step: 3
    name: repoint the five dev one-shot services
    depends_on: [2]
    actions:
      - "Apply `change_compose_dev` to all five service blocks together (BC-5)."
      - "Immediately run `docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml config` and read the resolved `DJANGO_SETTINGS_MODULE` for each of the five, plus `web` and `bot`."
    why_first: >
      This restores the dev stack and validates the cross-file environment merge, while the
      window between step 2 and step 3 is as short as possible.
  - step: 4
    name: regroup the allowlist
    depends_on: [3]
    actions:
      - "Apply `change_allowlist_regroup`. Add nothing, remove nothing, touch no branch (BC-1, BC-3, BC-4)."
  - step: 5
    name: rewrite and add the tests
    depends_on: [4]
    actions:
      - "Apply `change_test_secrets` (the VAL-001 rewrite)."
      - "Apply `change_test_oneshot_module` (the new module)."
      - "Apply `change_test_compose` (dev half + module-scope assertion)."
      - "Apply `change_test_env_template` (template absence assertion)."
    note: >
      All four land in the same change as the `prod.py` and compose edits. Partial
      delivery is the failure mode VAL-001 was filed for.
  - step: 6
    name: documentation
    depends_on: [5]
    actions:
      - "Apply `change_docs` to the three files."
  - step: 7
    name: gates
    depends_on: [6]
    actions:
      - "Run the full `tests.verification_gate` sequence below, including the negative control and the live dev-stack check."
  - step: 8
    name: hand-off
    depends_on: [7]
    actions:
      - "Re-read `git status --short` and stage explicit paths only (§1 hard rule). Never `git add -A`."
      - "Do not commit without an explicit user request."
      - "Leave the dev stack running (BC-10)."

# ─────────────────────────────────────────────────────────────────────────────
tests:

  must_keep_passing_unchanged:
    - "`config/settings/tests/test_settings_secrets.py::test_django_secret_key_required` — depends on the base.py present-file read_env skip (BC-3)."
    - "`config/settings/tests/test_settings_secrets.py::test_bot_token_required_in_production` — same skip, plus read_env's overwrite=False semantics with a present-but-empty value."
    - "`config/settings/tests/test_settings_secrets.py::test_google_translate_api_key_required_in_production`."
    - "`config/settings/tests/test_settings_secrets.py::test_redis_url_required_in_production`."
    - "`config/settings/tests/test_csrf_trusted_origins.py::test_csrf_trusted_origins_skipped_during_build` — the DJANGO_BUILD branch (BC-2). This is the only shipped test that would notice the builder stage being broken by a well-meaning 'prod is now unconditionally strict' edit."
    - "`config/settings/tests/test_csrf_trusted_origins.py::test_csrf_trusted_origins_required_in_production`."
    - "`config/settings/tests/test_csrf_trusted_origins.py::test_csrf_trusted_origins_defaults_empty_in_dev`."
    - "`config/settings/tests/test_env_allowlist.py::test_python_consumed_vars_in_allowlist` — asserts both bypass names are present in ALLOWED_ENV_VARS (BC-1)."
    - "`config/settings/tests/test_env_allowlist.py::test_example_keys_in_allowlist` (all four parametrizations) — the regroup must not add or remove a key."
    - "`config/settings/tests/test_env_allowlist.py::test_known_env_vars_no_warning` and `test_unknown_env_var_logs_warning`."
    - "Every prod placeholder / dev-only-dummy rejection test in test_settings_secrets.py: `test_django_secret_key_rejects_empty`, `test_prod_secret_key_rejects_short`, `test_prod_secret_key_rejects_placeholder`, `test_prod_secret_key_rejects_dev_only_dummy`, `test_prod_secret_key_still_rejects_empty`, `test_prod_secret_key_accepts_strong_key`, `test_prod_bot_token_rejects_placeholder`, `test_prod_bot_token_rejects_dev_only_dummy`, `test_prod_bot_token_accepts_real_token`, `test_prod_google_translate_api_key_rejects_placeholder`."
    - "BLOCK 2's three retargeted dev bot-token tests (`test_bot_token_required_in_dev`, `test_bot_token_placeholder_rejects_in_dev`, `test_bot_token_real_value_allowed_in_dev`) and `test_bot_token_allowed_empty_in_debug`."
    - "All of `config/settings/tests/test_prod_logging.py`, including `test_prod_logging_uses_json_formatter`, `test_sentry_dsn_in_env_examples`, `test_prod_settings_email_accessible` and the two Sentry tests. Note that this module pins LOGGING for `config.settings.prod` **only** — which is precisely why the new parity test below exists."
    - "The **prod half** of `src/backend/tests/test_compose_hardening.py::test_compose_oneshot_flags`, byte-identical."
    - "`src/backend/tests/test_compose_contract.py` in full (phase 01 artefact, untouched)."
    - "The seven `configure_dispatcher` tests in `src/telegram_bot/tests/test_main.py` — the new module is not on the bot's import path and must not become one."
    - "`test_settings_defaults.py` and the whole `config/settings/tests` package, which is why every block runs the package and not a subset."

  must_be_rewritten:
    - name: test_django_oneshot_bypasses_all_secrets
      path: src/backend/config/settings/tests/test_settings_secrets.py
      becomes: test_django_oneshot_does_not_bypass_prod_secrets
      asserts:
        - "`DJANGO_ONESHOT=1` + `DJANGO_SETTINGS_MODULE=config.settings.prod` + a blank `DJANGO_SECRET_KEY` (and empty `EMAIL_HOST`, `SITE_URL`, `CSRF_TRUSTED_ORIGINS`, dev-dummy tokens) → the subprocess exits non-zero."
        - "`ImproperlyConfigured` and `DJANGO_SECRET_KEY` both appear in stderr — the guard, not merely an import crash, is what fired."
        - "`DJANGO_ONESHOT is set but ignored` appears in stderr (D3), so the operator error is self-explaining."
      must_be_red_before_the_fix: true
    - name: test_compose_oneshot_flags (dev half)
      path: src/backend/tests/test_compose_hardening.py
      asserts:
        - "For every service in `_ONE_SHOT_SERVICES`, the dev-override block sets `DJANGO_SETTINGS_MODULE=config.settings.oneshot` **and** `DJANGO_ONESHOT=1`."
        - "`config.settings.oneshot` appears nowhere in `docker-compose.yml` or `docker-compose.prod.yml` — one assertion covering the prod stack and the test stack's reachability."
      note: "A four-of-five compose edit now fails this loop by naming the missed service (BC-5)."

  must_be_added:
    - name: test_oneshot_bypasses_secrets_for_oneshot_module
      path: src/backend/config/settings/tests/test_oneshot_settings.py
      why: >
        The positive bootstrap-path assertion VAL-001 requires. Without it, "delete the
        bypass and let the dev stack break" is a passing remediation.
      asserts:
        - "`DJANGO_ONESHOT=1` + `DJANGO_SETTINGS_MODULE=config.settings.oneshot` + the dev-dummy profile → exit 0, no `ImproperlyConfigured`, no `ValueError`."
        - "The inert-flag warning is **absent** from stderr — the flag was honoured, not merely tolerated."
    - name: test_oneshot_module_still_requires_oneshot_flag
      path: src/backend/config/settings/tests/test_oneshot_settings.py
      why: >
        The mechanism is a pair, not a module name. This proves the new settings module is
        not itself a universal bypass, which is the failure mode a reviewer cannot see by
        reading `oneshot.py`.
      asserts:
        - "Identical environment with `DJANGO_ONESHOT` removed → the SECRET_KEY guard fires and stderr names `DJANGO_SECRET_KEY`."
    - name: test_django_build_flag_bypasses_all_prod_guards
      path: src/backend/config/settings/tests/test_oneshot_settings.py
      why: >
        BC-2's regression guard, and the coverage the rewritten test used to provide by
        accident. `test_csrf_trusted_origins_skipped_during_build` covers exactly one
        guard; the image build and `make restore-test` need all of them skipped at once,
        including `EMAIL_HOST` and `REDIS_URL`. Without this test, "prod is now
        unconditionally strict" is a green suite and a broken image build.
      asserts:
        - "`DJANGO_BUILD=1` + `DJANGO_SETTINGS_MODULE=config.settings.prod` + the dev-dummy profile → exit 0."
    - name: test_oneshot_inherits_prod_logging
      path: src/backend/config/settings/tests/test_oneshot_settings.py
      why: >
        BC-7. The parity assertion Option D's star-import makes necessary in place of a
        copied LOGGING block. Without it, deleting the `from .prod import *` line would
        silently fall back to Django's plaintext `DEFAULT_LOGGING` and no shipped test
        would notice.
      asserts:
        - "`LOGGING['formatters']['json']['()']` is `apps.core.utils.json_logging.RedactingJsonFormatter`, the console handler's formatter is `json`, and the root level is `WARNING` — identical to what `test_prod_logging_uses_json_formatter` asserts for prod."
    - name: test_oneshot_pins_debug_and_smtp_transport
      path: src/backend/config/settings/tests/test_oneshot_settings.py
      why: >
        The two "do not inherit from dev" decisions that matter: `DEBUG` read from a
        gitignored `.env`, and the console mail backend (CFG-004's harm class — the
        one-shots run `migrate_locked` backfills that can send mail).
      asserts:
        - "`DEBUG is False` even when the environment sets `DEBUG=True`."
        - "`EMAIL_BACKEND` is the SMTP backend even when the environment names the console backend."
    - name: test_oneshot_shares_the_redis_cache
      path: src/backend/config/settings/tests/test_oneshot_settings.py
      why: >
        The third "do not inherit from dev" decision. A `LocMemCache` here would silently
        unshare the rate-limit and stale-while-revalidate caches from `web` and `bot`
        while still looking healthy.
      asserts:
        - "`CACHES['default']['BACKEND']` is the Redis cache backend, not `LocMemCache`."
    - name: test_oneshot_flag_is_inert_under_a_valid_prod_environment
      path: src/backend/config/settings/tests/test_oneshot_settings.py
      why: >
        Separates the warning from the raise. A stale `DJANGO_ONESHOT=1` left in an
        operator's `.env.prod` must not make a correctly configured production boot fail —
        it must warn and continue. Asserting this separately is what keeps the fix from
        becoming an outage.
      asserts:
        - "`DJANGO_ONESHOT=1` + `config.settings.prod` + a fully valid prod environment → exit 0."
        - "`DJANGO_ONESHOT is set but ignored` appears in stderr."
    - name: test_bypass_flags_absent_from_env_templates
      path: src/backend/config/settings/tests/test_env_allowlist.py
      why: "The `.env` channel's only coverage; the Compose channel is already covered by test_compose_hardening.py."
      asserts:
        - "Neither `DJANGO_BUILD` nor `DJANGO_ONESHOT` is a key in `.env.prod.example`, nor in `.env.example`."
        - "Implemented with the existing `_example_keys` helper; no new parser."

  need_no_test:
    - >
      The absence of a DJANGO_ONESHOT branch in `prod.py`'s guard blocks. Asserting the
      negative form ("the code does not read the flag here") is a test of the source text,
      not of behaviour; the behavioural statement is the bypass-refused test above.
    - >
      The `config.settings.test_migrations` → `test` → `base` chain. The new module is not
      part of it and nothing imports it from there; the module-scope assertion in the
      compose test already proves the test stack cannot reach it.
    - >
      The Makefile `restore-test` target. It needs a backup file and a SHA-tagged image. It
      is unchanged by this task, and `test_django_build_flag_bypasses_all_prod_guards`
      covers the settings contract it depends on. Run it only if a backup and `APP_IMAGE`
      are available; otherwise say so in the hand-off rather than implying it was exercised.

  verification_gate:
    - step: 1
      name: scoped run
      command: >
        `$dc run --rm -e PYTEST_SKIP_MARKERS=seed -e
        PYTEST_OPTS="src/backend/config/settings/tests src/backend/tests/test_compose_hardening.py" test`
        with `$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test
        -f docker-compose.yml -f docker-compose.test.yml'`
      expect: "all green, no new warnings from `_warn_unknown_env_vars`"
    - step: 2
      name: full fast gate
      command: ".\\Makefile.ps1 test"
      expect: "green"
    - step: 3
      name: static gates
      command: "uv run ruff check src/ and uv run basedpyright src/"
      expect: "both green — both are green at the anchor and must stay so"
    - step: 4
      name: resolved compose inspection
      command: "docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml config"
      expect: >
        Each of `migrate`, `load_cities`, `load_catalog`, `create_admin` and `seed` resolves
        `DJANGO_SETTINGS_MODULE: config.settings.oneshot` and carries `DJANGO_ONESHOT: "1"`;
        `web` and `bot` still resolve to `config.settings.dev`. This is the check that
        catches a cross-file environment merge that did not take effect — which would
        present as five one-shots dying at import in step 6, not as a test failure.
    - step: 5
      name: negative control
      command: "stash the prod.py hunk only, re-run the two rewritten tests, restore."
      expect: >
        Both fail. This is the demonstration that VAL-001's rewrite and the compose rewrite
        are real assertions and not tautologies. Record the output.
    - step: 6
      name: live dev stack
      command: ".\\Makefile.ps1 up, then docker ps -a --filter \"name=mko-bazuna-dev-\""
      expect: >
        All five one-shot services show **Exited (0)**, and `web` and `bot` show **Up** —
        not `Restarting`, and not a non-zero exit. `docker logs mko-bazuna-dev-migrate-1`
        shows a completed migration with no `ImproperlyConfigured`. This is the gate the
        whole finding is about: the bypass must still work where it is meant to.
    - step: 7
      name: image build (BC-2)
      command: ".\\Makefile.ps1 build, or docker build -f docker/Dockerfile -t mko-bazuna-block3-verify ."
      expect: >
        The builder stage completes `collectstatic` under `config.settings.prod` with
        `DJANGO_BUILD=1` and no `.env` file. If this cannot be run in the environment, say
        so explicitly in the hand-off and state which evidence stands in for it
        (`test_django_build_flag_bypasses_all_prod_guards`).
    - step: 8
      name: i18n completeness
      command: "part of step 2's full run"
      expect: >
        Green. No user-visible string is introduced; the warning is an operator diagnostic
        and follows the codebase's existing convention of untranslated log and exception
        messages.

acceptance_criteria:
  - "`DJANGO_ONESHOT=1` under `config.settings.prod` no longer suppresses any guard, and the boot log carries the `DJANGO_ONESHOT is set but ignored` warning."
  - "`DJANGO_BUILD=1` under `config.settings.prod` still suppresses every guard, verified by a test and by a successful image build."
  - >
    `config/settings/oneshot.py` exists, star-imports `prod`, re-pins `DEBUG = False`, and
    its docstring states the dependency inversion, the name-mangling caveat and the
    DJANGO_BUILD residual in those terms.
  - "All five dev one-shot services resolve to `config.settings.oneshot` in the rendered dev compose, and all five still exit 0 in a live dev stack."
  - "`config.settings.oneshot` is referenced by no compose file other than the dev override."
  - "`DJANGO_BUILD` and `DJANGO_ONESHOT` are both still in `ALLOWED_ENV_VARS`, in a commented sub-group inside the same frozenset literal."
  - "Neither flag appears in `.env.prod.example` or `.env.example`."
  - "`test_django_oneshot_bypasses_all_secrets` no longer exists under that name; its replacement asserts the negative, the warning, and was demonstrated red before the fix."
  - "A positive bootstrap-path test asserts the bypass still works — the pair, not just the negative."
  - "A test asserts the new module without the flag is refused, so the module is not a universal bypass."
  - "A parity test asserts the new module carries `prod`'s LOGGING, so the star-import cannot be silently dropped."
  - "Tests assert the new module does **not** inherit dev's console `EMAIL_BACKEND` or `LocMemCache`."
  - "Every test in the `must_keep_passing_unchanged` list is green, unchanged."
  - "`uv run ruff check src/` and `uv run basedpyright src/` are green."
  - "base.py's two `.env` branches and its `read_env` skip condition are byte-unchanged."
  - "`docker/Dockerfile`, `Makefile`, `docker-compose.yml`, `docker-compose.prod.yml`, `docker-compose.test.yml`, `dev.py`, `test.py` and `test_migrations.py` are untouched."
  - "No file under `.ai/audit/**` is modified, restored or re-created."
  - "The three documentation surfaces describe the new mechanism, including the runnable one-liner for a hand-typed `manage.py` command."
  - "The hand-off states which gates were run, and names any gate that could not be run in this environment rather than implying it passed."
  - "The dev stack is left running (BC-10)."
  - "Nothing was committed without an explicit user request."
```

**Why this shape.** The mechanism is one predicate and one file. The risk is not in the
diff — it is in the ten binding constraints, any one of which reddens a shipped green
test or breaks a live build, and in the fact that a partial delivery produces a *green*
suite with a broken dev stack or a silently broken image build. That is why the task
separates the settings-module work (steps 1–4) from the test work (step 5), forbids any
gate between them, and makes the decisive check a **live** `docker compose up` in which
all five one-shot services must still exit 0 — not an assertion about them.

**Two decisions worth the coordinator's attention.** First, `DJANGO_ONESHOT` is now inert
under production settings but remains a **load-bearing** flag for the dev one-shots: the
module name decides whether it counts, and the flag decides whether the guards run. Both
must be present in the dev override, and the compose test asserts both. Second, the
`DJANGO_BUILD` residual is real and is not fixed by this block — it is mitigated by a
comment and a template assertion, and no part of the change may claim otherwise.

---

### BLOCK 4 — Make the prod-settings import gate durable (CFG-002, durability half)

| | |
|---|---|
| **Findings owned** | `CFG-002` — **durability half**; `VAL-004` instance (b) |
| **`depends_on`** | **BLOCK 1** (the gate it protects), **BLOCK 3** (the required-variable set is conditional on where the bypass lives) |
| **Priority** | P1 |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**Agent requirement decision (the "high risk ⇒ all agents" rule applies here).**
The report's own cross-cutting recommendation calls this *"the single highest-ROI change
in the whole phase"*, and it is the durable half of the phase's only HIGH finding. The
central design question is not answerable by reading the report: **a GitHub Actions
`env:` block cannot import a Python constant.** The report proposes *"Extracting the set
into one shared constant consumed by both the test and the workflow is the durable
form"* — which is either impossible as stated or a build step, and choosing wrongly adds
a generation step to the pipeline.

- **Implementor — yes.** Always.
- **Auditor — yes.** Before designing anything, the Auditor must establish: every
  `env()` / `env.*()` read and every `os.getenv` in the whole settings chain that
  `prod.py` guards (or could guard) — i.e. the authoritative "required production
  variables" set, derived from the tree rather than from the eight lines currently in
  `ci.yml`; whether `EMAIL_*` has a partial set or a whole block; and whether any
  existing test already encodes a version of this set (two do: `_prod_env_overrides` and
  `_prod_env`).
- **Researcher — yes.** The specific question: **what is the accepted pattern for keeping
  a CI job's environment and a test's expectations from drifting, when one of them is
  YAML and the other Python?** The candidates are materially different — (i) the test
  *parses* `ci.yml` and asserts the parsed set satisfies the import (single source of
  truth = the YAML, drift is impossible, but the test's value depends on a YAML parse and
  on `ci.yml` living at a path a test can find); (ii) a Python
  `REQUIRED_PROD_ENV_VARS` constant asserted **against** the parsed `ci.yml` env block,
  with the test failing on either side of a mismatch (both sides named, drift is
  impossible, and the failure message says which side moved); (iii) generate the YAML env
  block from the constant (single source of truth = Python, but adds a generation step
  and a drift-of-its-own between generated and committed YAML). See §3.4.
- **Planner — yes.** The test's placement, the mechanism choice, the `test`-job
  integration, and the interaction with the settings-test duplication in note 3.
- **Validator — yes.** The change lands in the CI gate for the phase's only HIGH finding.
  A negative control is mandatory: the new test must be shown to **fail** when a
  variable is removed from the `deploy-check` env block, and to pass when restored.

**3.4 — Keeping the YAML and the test from drifting (open choice; recommendation, not a
decision).**

| Option | Change | Pro | Con |
|---|---|---|---|
| **A (recommended)** | The test **parses the `deploy-check` job's `env:` block out of `ci.yml`** (real YAML, per the `test_health_contract.py` / phase-01 `test_compose_contract.py` precedent) and asserts that a `config.settings.prod` import succeeds in a subprocess with **exactly** that set. | `ci.yml` stays the single source of truth; drift is structurally impossible; **zero** new pipeline machinery; matches the report's stated intent ("using **exactly** the variable set parsed out of `ci.yml`"). | The test's guarantee now depends on locating `ci.yml` at a stable path from the test's CWD, and on the `env:` block being parseable as a mapping. Both are already established patterns in this repo. |
| **B** | A Python `REQUIRED_PROD_ENV_VARS` constant in `config/settings/`, asserted **for equality** against the parsed `ci.yml` env block. | Names the requirement explicitly in code, so "what does prod require?" has one documented answer; the failure message can say which side moved. | Two representations that must agree; a rename in one place fails the test, which is the point — but it is a **bigger** surface than A for the same guarantee. |
| **C** | Generate the `env:` block from a Python constant at CI time. | Python is unambiguously the source of truth. | Adds a generation step to the pipeline, a checked-in-vs-generated drift class of its own, and a local/CI parity gap. **Not recommended.** |

**Recommendation:** Option A, optionally **strengthened** by a single assertion under B
("the parsed set is non-empty and contains the guards' documented minimum") without
introducing a second source of truth. **The Planner must state which it chose.**

**Findings and notes carried forward.**
1. **The test must run in the `test` job, not in `deploy-check`.** This is stated by the
   report and it is the whole point: a test that executes only inside the job it guards
   cannot fail that job early enough to be useful, and `deploy-check` has no pytest
   environment.
2. **Two existing prod-env builders already encode the correct set, and they disagree.**
   `_prod_env_overrides` (14 keys) and `_prod_env` (13 keys) are near-duplicates across
   four test modules; the second omits `SUPPORT_NOTIFICATION_RECIPIENTS`. Both already
   contain `EMAIL_HOST` and `REDIS_URL` — which is precisely why CI drifted and the tests
   did not.
3. **Consolidating the four `_run_in_subprocess` helpers and the two env builders is
   explicitly OUT OF SCOPE for this plan.** It touches four test modules and is a
   maintainability change, not a fix for CFG-002. **Constraint instead:** the new test
   must not create a *fifth* copy of the helper — import one, or place the new test in a
   module that already owns one. And if the Planner changes `_prod_env_overrides`,
   `test_settings_secrets.py`'s import of it **must be updated in the same change**
   (that coupling is real and is a live breakage vector). The consolidation itself is
   recorded in §6 as a phase-10/phase-11 candidate.
4. **Blocker the design must respect:** `DJANGO_ONESHOT` reaching the `deploy-check` job
   from a `.env` file would make the gate pass vacuously. Under BLOCK 3's chosen option
   the flag is inert against `prod` — the new test is then a genuine check. **If the
   Planner chooses an option where it is not inert, this block must add an explicit
   assertion that neither bypass flag is present in the `deploy-check` env block.**
5. **The new test is a subprocess import**, matching the four existing helpers. Keep the
   list-form `subprocess.run([sys.executable, ...])` invocation (bandit-clean, and
   required once VAL-006 is fixed).
6. **The comment moved in BLOCK 1 is the natural place to record the mechanism.** If the
   test parses `ci.yml`, the moved comment should say so, so the next editor of that job
   knows an assertion depends on its shape.
7. **Do not add a new CI job.** The test joins the existing `test` job. Adding a job
   changes the required-status-check set and is a repository-settings concern outside
   this plan.

**File surface (semantic units).**
- `.github/workflows/ci.yml` → `jobs.test.steps` (add the test invocation); the
  deploy-check contract comment block (extended by BLOCK 1) **only** if the chosen option
  requires a note there. `jobs.deploy-check` itself is **not** edited again.
- **New or existing:** a settings-test module owning the prod-import parity assertion.
  `test_settings_secrets.py` already owns prod import-time guard tests and already
  imports a subprocess helper; that is the default home. If a **new** module is created
  instead, it must follow the `_ROOT`-walk-to-`pyproject.toml` convention.
- `src/backend/config/settings/tests/test_prod_logging.py` → **only if**
  `_prod_env_overrides` changes, and then `test_settings_secrets.py`'s import must change
  with it.
- **Not touched:** `src/backend/config/settings/prod.py`, `base.py`, the compose files,
  `src/telegram_bot/**`.

**Tests required.**
- *Must keep passing unchanged:* all of `src/backend/config/settings/tests/**`; all of
  `src/backend/tests/test_compose_hardening.py`; all of
  `src/backend/tests/test_compose_contract.py`.
- *Must be added:* the parity test — parse the `deploy-check` `env:` block from `ci.yml`,
  build a subprocess environment from it, import `config.settings.prod`, assert success.
  Plus, under the design chosen in note 4, an assertion that no bypass flag is present.
- *Must be demonstrated red (Validator, not shipped as a test):* removing `REDIS_URL`
  from the `deploy-check` env block must make the new test **fail**; restoring it must
  make it pass. This is the negative control and it is mandatory.
- *Gate:* `$dc run --rm -e PYTEST_OPTS="src/backend/config/settings/tests src/backend/tests" test`,
  then `.\Makefile.ps1 test`, then the BLOCK 1 gate re-run (the YAML is now consumed by a
  test, so a malformed `env:` block breaks collection as well as the job).

**Risk / rollback.**
- *Risk:* a YAML-parsing test that silently finds no `deploy-check` job and passes
  vacuously. The test must assert that it **found** a non-empty env block before it
  asserts anything about it. This is the single most likely way this block ships a
  useless test.
- *Risk:* the test location changes the `test` job's dependency install or CWD
  assumptions. It runs inside the existing `test` service; no new step requirements.
- *Risk:* editing `_prod_env_overrides` and forgetting `test_settings_secrets.py`'s
  import (note 3). Same-change mandate.
- *Rollback:* remove the test and its `ci.yml` step. BLOCK 1's restore remains valid and
  independently useful — the gate stays green without this block.

#### BLOCK 4 — Implementation task

> Written by the BLOCK 4 Planner against the tree at `9443ade` (BLOCK 1 = `071e5c7`,
> BLOCK 2 = `cb31553`, BLOCK 3 = `9443ade`). This task resolves the Researcher's open
> decisions, corrects three stale counts in the block's notes above, and is the contract
> the BLOCK 4 Implementor executes. **Never use line numbers** — every target below is a
> file, module, class, function, variable or workflow job/block.
>
> **This subsection supersedes the "File surface" and "Tests required" paragraphs above it
> where they disagree.** It is an append; nothing above it is edited. Two of its rulings
> reverse what those paragraphs state: **D2** removes the mandated `jobs.test.steps` edit
> (the evidence says it is unnecessary), and **D1** reverses the default home from
> `test_settings_secrets.py` to a new module.

```yaml
id: block4-cfg002b-durable-prod-import-parity

title: >
  Make the CI deploy-check env block durably drive a config.settings.prod import,
  with a test that cannot pass vacuously (CFG-002 durability half + VAL-004 (b))

priority: P1

depends_on:
  - "BLOCK 1 (071e5c7) — the restored ten-variable deploy-check env block is the fixture this test reads"
  - "BLOCK 3 (9443ade) — DJANGO_ONESHOT is inert under a *.prod module, which is what makes the no-bypass-flag assertion meaningful"

source_reference: .ai/plans/02-config-secrets-remediation.md
source_section: "BLOCK 4 — Make the prod-settings import gate durable (CFG-002, durability half); option analysis in §3.4"
source_file: .ai/audit/99-validation/02-config-secrets-validated-findings.md
source_blocks:
  - "BLOCK 4 — Make the prod-settings import gate durable (CFG-002, durability half)"
  - "CFG-002 — CI deploy-check job cannot import config.settings.prod; the production config gate never runs"
  - "VAL-004 (b) — prod-settings import parity"
  - "§3.4 — Keeping the YAML and the test from drifting (open choice)"

description: >
  CFG-002 was a detection gap with a structural cause. BLOCK 1 closed the symptom (the
  `deploy-check` env block gained `EMAIL_HOST` and `REDIS_URL`) and moved the orphaned
  contract comment back above the job it documents. Neither changed the fact that a
  contract — "every required production env var is set" — is asserted in exactly one place
  with nothing verifying the application agrees. Two guard commits added a required
  variable; the env block was never updated; the gate that would have noticed has been
  failing at import ever since, and no test noticed because the gate is the only thing
  that imports `config.settings.prod`.

  This block ships the missing verifier. A new test parses the `deploy-check` job's
  `env:` block out of `.github/workflows/ci.yml` and asserts that a real
  `config.settings.prod` import succeeds in a subprocess driven by **exactly that block**,
  hardened at six construction points against the failure mode that makes YAML-consuming
  tests worthless: finding nothing and passing. `ci.yml` stays the single source of
  truth; there is no second representation to keep in sync and no generation step to keep
  honest.

  The report's own wording — "one shared required-variable constant consumed by both
  `deploy-check` and a unit test" — is **impossible as literally written**: a GitHub
  Actions `env:` block cannot import a Python constant. Its only faithful implementation
  is code generation, which relocates the drift class (a generator plus a committed
  artefact) rather than removing it, adds tooling the repository does not have, and
  collapses reviewability. The Researcher's conclusion and this task agree: the assertion
  must be **execution-based**, because only importing the module can tell you what the
  application requires. See D3.

  The block's scope is two files: one new test module, and one sentence appended to the
  contract comment BLOCK 1 relocated. No production code, no settings module, no compose
  file, no CI job step.

goals:
  - >
    A test in the `test` job fails the moment the `deploy-check` env block stops
    satisfying `config.settings.prod` — whether a required variable is removed, emptied,
    or a new guard is added.
  - >
    The test cannot pass vacuously: it proves it found a real job, a real mapping-shaped
    env block and a non-empty value set **before** it asserts anything about the
    environment, and a malformed or missing workflow file fails the test rather than
    skipping it.
  - >
    The test is honest about the `.env` back-fill channel: the two negative controls it
    ships are chosen to be valid in **both** the Docker test container (where
    `src/.env` is bind-mounted from `.env.test` and `read_env()` restores absent keys)
    and the CI `test` runner (where no `src/.env` exists).
  - >
    No new credential-shaped literal, no interpolated env value in any assertion message,
    no new dependency, no new CI job, and no fifth copy of `_run_in_subprocess` or of a
    prod-env builder.
  - >
    The next editor of the `deploy-check` job learns that the block's **shape** is now
    load-bearing, from the comment directly above the job rather than from a test file
    they will not open.
  - >
    Failures are self-explaining: a message states which layer failed, names the key, and
    — when the import is the thing that failed — says outright that a new required
    production variable is the expected cause and names the file and block to edit.

# ─────────────────────────────────────────────────────────────────────────────
# Decisions taken by the BLOCK 4 Planner
# ─────────────────────────────────────────────────────────────────────────────
decisions:
  - id: "D1 — placement: a NEW module, not test_settings_secrets.py"
    choice: >
      New file `src/backend/config/settings/tests/test_deploy_check_env_parity.py`.
    rationale: >
      The block's own file-surface note names `test_settings_secrets.py` as "the default
      home"; that default is reversed. That file is the phase's most contended artefact —
      BLOCK 2 retargets three tests in it, BLOCK 3 rewrites one, BLOCK 5 adds one, BLOCK 7
      adds one — and every one of those is a same-file merge into a region a human is
      already editing. The subject here is different too: every existing test in that file
      asserts a property of the *settings module* under a synthetic environment it
      constructs itself. This one asserts a property of a *pipeline descriptor's
      compatibility with* that module. Same package (so it carries `pytest.mark.settings`
      and imports the shared subprocess helper by the established
      `config.settings.tests.test_prod_logging` path), different subject, zero contention.
    considered_and_rejected: >
      `src/backend/tests/` (where `test_compose_contract.py` and `test_docs_ci_parity.py`
      live) is defensible on the "it is a CI-contract test" reading, and it would place the
      module next to its siblings. It loses because the `settings` marker would have to be
      dropped or duplicated, and the helper import would cross package boundaries. If a
      reviewer disagrees, the move is a one-line import-path change; the design is
      unaffected.

  - id: "D2 — the `jobs.test.steps` edit is NOT made. The plan above is wrong here."
    choice: >
      `.github/workflows/ci.yml` is edited in **exactly one place**: the `deploy-check`
      contract comment block, extended by the sentences specified under
      `change_extend_contract_comment`. `jobs.test.steps` is **not** edited, and
      `jobs.deploy-check.env` is **not** edited.
    rationale: >
      The block's file surface says "`jobs.test.steps` (add the test invocation)". The
      evidence contradicts it. The `test` job's pytest step runs `uv run pytest -m "not
      seed" -n auto --dist loadgroup --tb=short --cov --durations=10 ...` with
      `working-directory: src/backend` and **no path argument**, and `pyproject.toml`
      sets `testpaths = ["src/backend", "src/telegram_bot"]` with
      `python_files = ["tests.py", "test_*.py"]`. A new `test_*.py` under `src/backend` is
      therefore collected automatically. The invocation is unchanged and the test is
      invisible to the pipeline it protects — which is exactly the required property: the
      assertion runs where a failure is actionable, and it needs no step of its own.
    consequence: >
      `ci.yml`'s diff for this block is comment-only. `test_docs_ci_parity.py` and
      `test_ci_security.py` read `ci.yml` as text and are unaffected; run them anyway,
      because a comment edit is still a `ci.yml` edit and both files assert on it.
    also_recorded: >
      A step-scoped `-p no:randomly`-style isolation or a `--tb` tweak is not needed and
      must not be added. The new tests carry the `unit` and `settings` markers and are
      therefore inside the `-m "not seed"` selection.

  - id: "D3 — mechanism: Option A′, execution-based, hardened against vacuity. Codegen is rejected."
    choice: >
      Parse `ci.yml` with `ruamel.yaml`'s `YAML(typ="safe")`, fail closed on `YAMLError`,
      walk document → `jobs` → `"deploy-check" in jobs` → `env` is a `dict` →
      `len(env) > 0`, and only then assert anything about the contents. The subprocess
      environment is a scrubbed `MINIMAL_BASE` (`PATH`, `HOME`) merged with the parsed
      block — explicitly **not** `os.environ`, which would make the test behave differently
      in CI than on a developer machine and would let an inherited `DJANGO_BUILD` or
      `DJANGO_SECRET_KEY` from a developer's shell decide the outcome.
    rationale: >
      Three of the four rejected alternatives are dead on arrival, and it is worth saying
      why so the next reader does not re-propose them. **(i) No workflow linter covers this
      defect class**: `actionlint` knows which names a workflow *defines* but has no model
      of what the *application requires*; a schema (the Helm `values.schema.json` pattern)
      is one-directional — it catches unknown keys, not "the app now requires a key the
      schema does not mention", which is the only direction that matters. **(ii) A Python
      `REQUIRED_PROD_ENV_VARS` constant asserted for equality against the parsed block**
      (option B) introduces a second hand-maintained representation and grows: the
      equality assertion is true whenever both sides drift together, and it cannot detect
      the class of drift that actually happened (a *new guard* in `prod.py` adds no name
      to either side). **(iii) Generating the env block from a constant** (option C) moves
      the drift into a generator plus a committed artefact, needs tooling the repository
      does not have, and would not run outside CI. Only importing the settings module can
      answer "what does prod require", so only an execution-based assertion can close the
      gap the report describes.
    honest_cost: >
      The guarantee is now conditioned on a YAML parse succeeding and on the `deploy-check`
      job continuing to exist under that name. Both are cheap to make loud (hence the
      fail-closed ladder) and both are already-established patterns in this repository
      (`test_health_contract.py`, `test_compose_contract.py`).

  - id: "D4 — the negative control ships as a parametrized test, in BOTH portable forms"
    choice: >
      Ship `test_deploy_check_env_block_rejects_missing_variable`, parametrized over two
      rows, each with its masking channel and its own expected exception surface:
        - `REDIS_URL`, **present-but-empty** → `ImproperlyConfigured`
        - `CSRF_TRUSTED_ORIGINS`, **key removed** → `ValueError`
      Neither row uses `DJANGO_SECRET_KEY`.
    rationale: >
      Two facts force this shape. First, the local Docker test container bind-mounts
      `./.env.test` to `/app/src/.env` and also injects it via `env_file`; for a
      `config.settings.prod` import, `base.py`'s present-file branch **runs**
      (`"test"` is not in the module name) and `read_env(overwrite=False)` back-fills any
      key **absent** from the process environment. Six of the ten required variables are
      defined in `.env.test`, so a *deleted* key is silently restored and the control
      passes for the wrong reason. The repo's own documented convention answers this:
      **present-but-empty**, not delete. Second, present-but-empty is **not** portable for
      `DJANGO_SECRET_KEY` in the other direction: in the CI `test` runner there is no
      `src/.env`, so `base.py` takes its missing-file branch and, with the key empty, its
      condition is satisfied and the process `sys.exit(1)`s with a `.env file not found`
      message — a red herring that looks like a different bug. Hence the two-row design:
      the empty form covers the six keys `.env.test` would restore, the delete form is
      used on `CSRF_TRUSTED_ORIGINS` precisely because `.env.test` does not define it, and
      both forms are therefore valid in **both** environments. The two rows also assert
      two different exception types on purpose, which pins the fact that the prod import
      has **no single** failure surface: six guards raise `ImproperlyConfigured`, two
      (`ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`) raise a bare `ValueError`, and an unset
      `DJANGO_SECRET_KEY` raises from `base.py` with yet another message.
    why_not_just_redis_url: >
      Because the empty form alone is the portable one, and the delete form is the one
      that proves the harness can observe a *missing* key as opposed to an empty one.
      One row would leave a channel untested; the two-row form costs one `parametrize`
      line.

  - id: "D5 — the no-bypass-flag assertion ships as its OWN test"
    choice: >
      `test_deploy_check_env_block_declares_no_bypass_flag` is a separate test function,
      not a clause inside the import test.
    rationale: >
      It has a different failure mode, a different remediation and a different reviewer.
      Its failure mode is the catastrophic one — the gate passing **vacuously** because a
      guard-disabling flag reached the job, which is CFG-001's tail arriving through CI
      configuration rather than through a `.env` file. Its remediation is "delete a line
      from the YAML", not "add a required variable". A separate test also cannot be
      lost by accident: if the import test is later refactored, the flag assertion is
      still a first-class, independently named check rather than a clause someone
      rationalises away.
    scope_correction: >
      It must cover **both** names, `DJANGO_BUILD` and `DJANGO_ONESHOT`, and the block's
      note 4 wording — which collapses the two and reasons only about `DJANGO_ONESHOT` —
      is corrected here. The distinction is load-bearing after BLOCK 3: `DJANGO_ONESHOT`
      **is** inert against a `*.prod` settings module, so its presence in the block would
      be a no-op. `DJANGO_BUILD` is **not** scoped — `prod.py` honours it
      unconditionally — so its presence would suppress every guard and the job would pass
      for no reason at all. Neither name appears in `ci.yml` today; the assertion is
      forward-looking, and its value is precisely that `DJANGO_BUILD` is the live case.

  - id: "D6 — the \"no GitHub Actions expression in any value\" assertion: YES, ship it"
    choice: >
      Assert that no value in the parsed `env` block contains a `${{ … }}` expression.
    rationale: >
      This is not a style preference; it is the same defect class one level down. A value
      written as `${{ secrets.X }}` is expanded by the Actions runner **before** the step
      runs, so the test — which sees the literal source text — would assert against a
      string CI never uses, and would keep passing while checking something that is not
      what the job sees. A value the test cannot reproduce is a value the test does not
      check, which is the exact premise BLOCK 4 exists to remove. It also enforces a
      contract that already exists: the relocated comment states that the block holds
      "valid non-secret placeholders" so the full prod import path is exercised. Nothing
      in the block uses an expression today, so the assertion is green on arrival and
      costs one line.
    stated_cost: >
      It would reject a future attempt to give the gate a real secret. That is the
      intended behaviour, not a false positive: a real secret in this job is the mistake
      the comment already forbids, and it would make the job's result depend on a
      repository secret that no local run can exercise.

  - id: "D7 — extend the relocated contract comment: YES, one short block"
    choice: >
      Append three sentences to the existing `deploy-check` comment, directly above the
      job, stating that a test parses the block and asserting the three properties the
      block must keep: it stays a YAML mapping, it stays non-empty, and it never gains a
      bypass flag — and naming the test module so `grep` connects the two.
    rationale: >
      The defect's structural cause was an invisible dependency: the contract comment was
      orphaned 133 lines above the job, so nobody editing the env block knew a contract
      was pinned there. Adding a second, equally invisible dependency — a test that now
      reads this job's shape — without a word in the file would reproduce the same class
      one commit later. The comment is the only place the next editor of this block will
      look.
    constraints: >
      The existing text is **not** rewritten and the comment is **not** moved; BLOCK 1
      placed it and this block only appends. No test-visible behaviour depends on the
      comment's content — `test_ci_security.py` slices from the `deploy-check:` header
      and `test_docs_ci_parity.py` asserts on unrelated tokens — so the edit is inert to
      the suite by construction. Confirm that after editing.

  - id: "D8 — failure messages: value-free, layered, and forward-pointing"
    choice: >
      No assertion message in the new module may interpolate a value read from the parsed
      env block; messages name **keys**, layer names and file paths. The import failure
      message additionally states the expected cause and the remediation.
    rationale: >
      Value-free messages are the repository's standing convention (every
      `ImproperlyConfigured` in `prod.py` is value-free by design) and they keep both the
      CI log and gitleaks clean. The forward-pointing half is the sequencing requirement
      below: without it, whoever hits the first red — which BLOCK 5 is scheduled to
      cause — has to reverse-engineer that the fix is to add a variable to a YAML file.
    on_stderr: >
      `assert ... , result.stderr` is the established sibling pattern and is kept, because
      the exception text this test observes is value-free by the settings modules' own
      contract. The module docstring must say that this is a **dependency on that
      contract**, so a future change that starts echoing values is caught by a reviewer
      reading this file rather than in a CI log.

  - id: "D9 — the sequencing hazard is handled by message, never by weakening the test"
    choice: >
      BLOCKS 5, 7 and 9 change what `config.settings.prod` requires. Of those, only
      **BLOCK 5** legitimately turns this test red (its `BOT_USERNAME` guard makes a
      currently-unrequired variable required; the block's `env` has no `BOT_USERNAME`).
      BLOCK 7 pins `EMAIL_BACKEND` as an unconditional assignment — no new variable
      required — and BLOCK 9 deletes a dead `STATICFILES_STORAGE` line. Neither turns it
      red. The `deploy-check` **job** goes red in exactly the same case, which is the
      gate working, not a regression.
    handling: >
      The response is the **forward-pointing failure message** (D8): it must name
      `config.settings.prod` having gained a required variable as the expected cause, and
      name `.github/workflows/ci.yml` → `jobs.deploy-check.env` as the place to fix it.
      **No `skipif`, no `xfail`, no version guard, and no "known missing variables" list**
      is permitted: a suppression here would recreate the exact silent-drift failure the
      block exists to end, and the report's own `R-7` names it. BLOCK 5's Implementor is
      required to add `BOT_USERNAME` to `jobs.deploy-check.env` in the same change that
      adds the guard; this test is what makes that obligation visible instead of
      optional. That is the whole return on the block.
    recorded_as_forward_constraint: true

# ─────────────────────────────────────────────────────────────────────────────
# Corrections to the block's notes above (the tree is the authority)
# ─────────────────────────────────────────────────────────────────────────────
corrections_to_block_notes:
  - >
    Note 2's counts are stale. `_prod_env_overrides` (`test_prod_logging.py`) sets
    **18** keys, not 14; `_prod_env` (`test_csrf_trusted_origins.py`) sets **14**, not
    13. They disagree on `SUPPORT_NOTIFICATION_RECIPIENTS` and `DEBUG`, they differ in how
    they treat `CSRF_TRUSTED_ORIGINS`, and **both omit `EMAIL_USE_TLS`** even though
    `base.py` reads it. Neither builder is used by the new module, and neither is edited
    by this block.
  - >
    Note 3's "must not create a fifth copy" is honoured by importing
    `test_prod_logging._run_in_subprocess` (which returns a `CompletedProcess[str]`,
    unlike the `str`-returning copy in `test_settings_secrets.py`). The same-change
    coupling in note 3 does **not** fire, because this block does not change
    `_prod_env_overrides` at all — stated explicitly so the Implementor does not "helpfully"
    reconcile the 18-vs-14 divergence inside this block. That is §6's out-of-scope item.
  - >
    Note 4's wording collapses `DJANGO_BUILD` into `DJANGO_ONESHOT`. Corrected in D5.
  - >
    Note 7 ("the moved comment should say so") is adopted and made concrete in D7, and is
    the only `ci.yml` edit this block makes (D2).

recorded_follow_ups:
  - >
    **`_deploy_check_section()`'s "deploy-check is the last job" fragility** in
    `src/backend/apps/core/tests/test_ci_security.py`. It slices `content[index(marker):]`
    to end-of-file, so appending any job after `deploy-check` silently widens the slice
    and turns two negative assertions (`"config.settings.test" not in section`,
    `"continue-on-error" not in section`) into whole-file assertions that will fail for an
    unrelated reason. Replace the slice with a real YAML parse of the single job's node.
    **Not done in this block** — it is a phase-11 test-quality item and this block's new
    module must not depend on that helper.
  - >
    **`actionlint` adoption.** The Researcher's finding stands: no workflow linter models
    what the application *requires*, so `actionlint` would not have caught CFG-002. It
    would still catch malformed YAML, bad expressions and shellcheck-class errors, which
    makes it worth having — but it is not a substitute for anything in this block, and
    adopting it is a phase-12 repository-settings change (it adds a CI job, which
    §"Do not add a new CI job" forbids here).
  - >
    **Consolidating the four `_run_in_subprocess` helpers and the two prod-env builders**
    (§6, out of scope for this plan). The counts and divergences are now recorded in
    `corrections_to_block_notes`. This block adds no copy of either.

# ─────────────────────────────────────────────────────────────────────────────
# Binding constraints
# ─────────────────────────────────────────────────────────────────────────────
binding_constraints:
  - id: BC-1
    rule: >
      The test must **fail closed** at every rung of the non-vacuity ladder. A `YAMLError`,
      a non-mapping document, a missing `jobs` key, a missing `deploy-check` job, a
      non-mapping `env`, or an empty `env` must each produce a distinct, named assertion
      failure. There is no `try/except` that falls back to a default, and no `pytest.skip`
      anywhere in the module.
    why: >
      A YAML-consuming test that finds nothing and passes is worse than no test, because
      it is indistinguishable from a working one in every report downstream. This is the
      single most likely way this block ships something useless, and it is named as such
      in the block's own risk register.
  - id: BC-2
    rule: >
      The job must be located with `"deploy-check" in jobs` — **not**
      `jobs.get("deploy-check", {})`. A defaulting `.get` is the textbook vacuity bug:
      it turns "the job is gone" into "the env block is empty", which under a weaker
      assertion is a pass.
  - id: BC-3
    rule: >
      The subprocess environment is a **scrubbed** `MINIMAL_BASE` (`PATH`, `HOME`) merged
      with the parsed block. It must never be seeded from `os.environ`.
    why: >
      `_prod_env_overrides` seeds from `os.environ` and that is correct for it — it is
      testing settings under a real developer shell. It is **wrong** here: the point of
      this test is that the parsed block alone determines the outcome. Inheriting
      `os.environ` would let a developer's `DJANGO_BUILD` or `DJANGO_SECRET_KEY` decide
      the result, and would make the CI run and the local run differ. (`PYTHONPATH` is
      supplied by the shared `_run_in_subprocess` helper, which overwrites whatever the
      base carries — that is the intended behaviour, not a conflict.)
  - id: BC-4
    rule: >
      No credential-shaped literal may be introduced. Every value the test uses comes from
      the parsed YAML at run time. The only literals in the module are the job name, the
      settings-module name, the two bypass-flag names, `PATH`/`HOME`, and the import
      statement — none of which `.gitleaks.toml` treats as a finding. The parsed block
      must never be printed, logged, or interpolated into an assertion message.
  - id: BC-5
    rule: >
      `src/backend/config/settings/tests/test_prod_logging.py` is **not edited** — not
      `_run_in_subprocess`, not `_prod_env_overrides`, not `_ROOT`. It is imported from.
      Consequently `test_settings_secrets.py`'s and `test_oneshot_settings.py`'s
      cross-module imports of it stay valid with no change, and the §7 "all blocks" risk
      about that coupling does not fire.
  - id: BC-6
    rule: >
      No new dependency, no new CI job, no change to `jobs.test.steps`, no change to
      `jobs.deploy-check.env`, and no change to any settings module, compose file,
      Dockerfile or Makefile target. `ci.yml`'s entire diff for this block is the appended
      comment sentences.
  - id: BC-7
    rule: >
      The new module must not import from `apps.core.tests.test_ci_security`, and must not
      reuse `_deploy_check_section()`. That helper is a **text slice**, not a parse, and
      reusing it would inherit the "last job in the file" fragility recorded above.

# ─────────────────────────────────────────────────────────────────────────────
files:
  - path: src/backend/config/settings/tests/test_deploy_check_env_parity.py
    status: new
    targets:
      - type: module
        name: test_deploy_check_env_parity
      - type: module_docstring
        name: "why the block is read from ci.yml and why the two negative-control forms differ"
      - type: constant
        name: _CI_YML
      - type: constant
        name: _JOB_NAME
      - type: constant
        name: _PROD_MODULE
      - type: constant
        name: _BYPASS_FLAGS
      - type: constant
        name: _MINIMAL_BASE_KEYS
      - type: constant
        name: _IMPORT_CODE
      - type: helper
        name: _load_ci_document
      - type: helper
        name: _deploy_check_env
      - type: helper
        name: _subprocess_env
      - type: function
        name: test_deploy_check_env_block_imports_prod_settings
      - type: function
        name: test_deploy_check_env_block_declares_no_bypass_flag
      - type: function
        name: test_deploy_check_env_block_rejects_missing_variable
    semantic_anchors:
      resolve_root: >
        Walk up from `Path(__file__).resolve().parent` to the directory containing
        `pyproject.toml` — the `_ROOT` convention already used by
        `test_prod_logging.py`, `test_csrf_trusted_origins.py`,
        `test_compose_contract.py` and `test_docs_ci_parity.py`. Do **not** copy the loop
        into a new shape; four modules already spell it identically.
      import_from: >
        `from ruamel.yaml import YAML` and
        `from ruamel.yaml.error import YAMLError` (both already used in
        `test_compose_contract.py`); `from config.settings.tests.test_prod_logging import
        _run_in_subprocess`. Nothing else.
      markers: "pytestmark = [pytest.mark.unit, pytest.mark.settings] — the file's siblings' value"
      must_not_contain:
        - "a new subprocess.run call"
        - "a new prod-env builder"
        - "any string literal that looks like a credential"
        - "pytest.skip / pytest.mark.skipif / xfail"
        - "jobs.get("
        - "os.environ as the subprocess base"

  - path: .github/workflows/ci.yml
    targets:
      - type: comment_block
        name: "the deploy-check gate contract comment directly above the deploy-check job"
    semantic_anchors:
      append_to: "the sentence ending \"so the full prod settings import path is exercised.\""
      do_not_edit:
        - "jobs.deploy-check.env (all ten keys, byte-identical)"
        - "jobs.deploy-check.steps"
        - "jobs.test (env, services and steps)"
        - "the existing sentences of the comment block, including their order"
        - "every other job"
      note: >
        BLOCK 1 (`071e5c7`) placed this comment directly above `jobs.deploy-check`. This
        block appends to it; it does not move, reword or reorder it.

  # ── Explicitly not touched. Named so the Implementor does not "improve" them. ──
  - path: src/backend/config/settings/tests/test_prod_logging.py
    status: not_touched
    note: "imported from, never edited (BC-5)"
  - path: src/backend/config/settings/tests/test_settings_secrets.py
    status: not_touched
    note: "the phase's most contended file; D1 exists to keep it untouched"
  - path: src/backend/config/settings/tests/test_csrf_trusted_origins.py
    status: not_touched
  - path: src/backend/config/settings/tests/test_oneshot_settings.py
    status: not_touched
  - path: src/backend/config/settings/tests/test_settings_defaults.py
    status: not_touched
  - path: src/backend/config/settings/tests/test_env_allowlist.py
    status: not_touched
  - path: src/backend/config/settings/tests/__init__.py
    status: not_touched
    note: "the module reuses no constant from it, and must not add one"
  - path: src/backend/apps/core/tests/test_ci_security.py
    status: not_touched
    note: "its _deploy_check_section() fragility is recorded as a follow-up, not fixed here"
  - path: src/backend/tests/test_docs_ci_parity.py
    status: not_touched
  - path: src/backend/tests/test_compose_hardening.py
    status: not_touched
  - path: src/backend/tests/test_compose_contract.py
    status: not_touched
  - path: src/backend/config/settings/prod.py
    status: not_touched
  - path: src/backend/config/settings/base.py
    status: not_touched
  - path: src/backend/config/settings/dev.py
    status: not_touched
  - path: src/backend/config/settings/test.py
    status: not_touched
  - path: src/backend/config/settings/test_migrations.py
    status: not_touched
  - path: src/backend/config/settings/oneshot.py
    status: not_touched
  - path: docker/Dockerfile
    status: not_touched
  - path: docker-compose.yml
    status: not_touched
  - path: docker-compose.prod.yml
    status: not_touched
  - path: docker-compose.dev.override.yml
    status: not_touched
  - path: docker-compose.test.yml
    status: not_touched
  - path: Makefile
    status: not_touched
  - path: Makefile.ps1
    status: not_touched
  - path: src/telegram_bot
    status: not_touched
  - path: ".ai/audit"
    status: not_touched
    note: "unmodifiable by mandate; 18 tracked deletions there are pre-existing and not this block's"

# ─────────────────────────────────────────────────────────────────────────────
changes:

  - action: add_test_module
    id: change_add_parity_module
    path: src/backend/config/settings/tests/test_deploy_check_env_parity.py
    description: >
      One new module, three test functions, two small helpers. Its job is to answer a
      single question — *can the environment the `deploy-check` job actually runs with
      import `config.settings.prod`?* — and to be incapable of answering "yes" for any
      reason other than the truth.

      The module docstring must state, in this order: what the assertion is and that it
      is the detection half of CFG-002 (BLOCK 1 restored the gate; this makes its
      restoration durable); that `ci.yml` is the single source of truth and there is
      deliberately no second representation; why the subprocess environment is scrubbed
      rather than inherited; that every message is value-free **and that this relies on
      `prod.py`'s value-free exception contract being preserved**; and the two negative-control
      rows, each with the environment it is valid in and the masking channel it works
      around.

      `_load_ci_document` opens the file, parses with a stock `YAML(typ="safe")` —
      `ci.yml` carries no custom tags, unlike the compose files that need `!reset` and
      `!override` registered — and lets a `YAMLError` propagate as a test failure. There
      must be no `try/except` around it.

      `_deploy_check_env` is the non-vacuity ladder, and it is the most important function
      in the module. It must assert, in order and each with its own message: the document
      is a mapping; `jobs` is present and is a mapping; `"deploy-check"` is a **key** of
      it; the job is a mapping; `env` is present and is a `dict`; `len(env) > 0`. It
      returns `dict[str, str]`. Every rung names what is missing, so a failure says
      "deploy-check job's env block is not a mapping" rather than raising `TypeError` from
      a subscript.

      `_subprocess_env` builds `MINIMAL_BASE` from `PATH` and `HOME` only, then overlays
      the parsed block. `PYTHONPATH` is deliberately absent from the base because
      `_run_in_subprocess` overwrites it with the parent `sys.path`; the docstring must
      say so rather than leaving a reader to wonder why the base is incomplete.

      The three tests, in the order the ladder supports:

      1. `test_deploy_check_env_block_imports_prod_settings` — the parity assertion.
         Reads the block through the ladder, asserts
         `env["DJANGO_SETTINGS_MODULE"] == "config.settings.prod"`, asserts every value is
         a non-empty string (BC-1's cheapest rung, and the one layer the `.env`
         back-fill channel cannot mask because a key that is present-and-empty is never
         overwritten by `read_env(overwrite=False)`), asserts no value contains a GitHub
         Actions expression (D6), then runs the import in a subprocess and asserts
         `returncode == 0`. On failure the message must be the forward-pointing one
         (D8/D9) naming the layer, the file and the block to edit.
      2. `test_deploy_check_env_block_declares_no_bypass_flag` — D5. Asserts neither
         `DJANGO_BUILD` nor `DJANGO_ONESHOT` is a key of the block, and names in the
         message which of the two is the live hazard (`DJANGO_BUILD` is honoured
         unconditionally by `prod.py`; `DJANGO_ONESHOT` is inert under a `*.prod` module
         since BLOCK 3). It reads the block through the same ladder and asserts nothing
         about the values, so it keeps working if the import test is refactored.
      3. `test_deploy_check_env_block_rejects_missing_variable` — D4, parametrized over
         `("REDIS_URL", "empty")` and `("CSRF_TRUSTED_ORIGINS", "absent")`. Each row
         takes the block, applies its one mutation, and asserts the import fails **with
         its own exception surface** (`ImproperlyConfigured` + the key name for the first,
         `ValueError` + the key name for the second). This is the test that proves the
         harness can observe a failure at all: without it, a green import test is
         compatible with a broken harness.

      Use a stock `subprocess.CompletedProcess` return from the shared helper; do not
      introduce a local one. Do not mark the module `slow` — the sibling settings tests
      are not, and the whole point is that the assertion runs on every push.
    code_hint: |
      _CI_YML = _ROOT / ".github" / "workflows" / "ci.yml"
      _JOB_NAME = "deploy-check"
      _PROD_MODULE = "config.settings.prod"
      _BYPASS_FLAGS = frozenset({"DJANGO_BUILD", "DJANGO_ONESHOT"})
      _MINIMAL_BASE_KEYS = ("PATH", "HOME")
      # Importing the settings module directly (rather than django.setup()) is the
      # exact subject of the assertion and adds no app-population surface to the
      # failure. PYTHONPATH is supplied by _run_in_subprocess.
      _IMPORT_CODE = "import config.settings.prod"


      def _load_ci_document() -> dict:
          with _CI_YML.open(encoding="utf-8") as fh:
              document = YAML(typ="safe").load(fh)   # a YAMLError must fail the test
          assert isinstance(document, dict), (
              "ci.yml must parse to a mapping at the document root"
          )
          return document


      def _deploy_check_env() -> dict[str, str]:
          """Return the deploy-check job's env block, proving it was found."""
          document = _load_ci_document()
          assert "jobs" in document, "ci.yml has no 'jobs' key"
          jobs = document["jobs"]
          assert isinstance(jobs, dict), "ci.yml 'jobs' must be a mapping"
          assert _JOB_NAME in jobs, (
              f"ci.yml has no '{_JOB_NAME}' job; the test's subject does not exist"
          )
          job = jobs[_JOB_NAME]
          assert isinstance(job, dict), f"ci.yml job '{_JOB_NAME}' must be a mapping"
          assert "env" in job, f"ci.yml job '{_JOB_NAME}' has no 'env' key"
          env = job["env"]
          assert isinstance(env, dict), (
              f"ci.yml job '{_JOB_NAME}': env must be a YAML mapping, "
              "which is what this test reads"
          )
          assert len(env) > 0, f"ci.yml job '{_JOB_NAME}': env block is empty"
          return {str(k): str(v) for k, v in env.items()}


      def _subprocess_env(env: dict[str, str]) -> dict[str, str]:
          """Scrubbed base + the parsed block. Never seeded from os.environ (BC-3)."""
          base = {key: os.environ[key] for key in _MINIMAL_BASE_KEYS if key in os.environ}
          return {**base, **env}


      def test_deploy_check_env_block_imports_prod_settings() -> None:
          env = _deploy_check_env()
          assert env["DJANGO_SETTINGS_MODULE"] == _PROD_MODULE, (
              f"ci.yml job '{_JOB_NAME}': DJANGO_SETTINGS_MODULE must be {_PROD_MODULE}"
          )
          empty = sorted(key for key, value in env.items() if not value)
          assert not empty, (
              f"ci.yml job '{_JOB_NAME}': these keys must carry a non-empty "
              f"placeholder value: {empty}"
          )
          templated = sorted(key for key, value in env.items() if "${{" in value)
          assert not templated, (
              f"ci.yml job '{_JOB_NAME}': these keys use a GitHub Actions expression, "
              f"so this test cannot reproduce the value CI uses: {templated}"
          )
          result = _run_in_subprocess(_subprocess_env(env), _IMPORT_CODE)
          assert result.returncode == 0, (
              f"config.settings.prod does not import with the env block from "
              f"ci.yml job '{_JOB_NAME}'. If prod.py recently gained a new required "
              f"variable, add it to jobs.deploy-check.env in .github/workflows/ci.yml "
              f"as a non-secret placeholder — that is this test and the deploy-check "
              f"job both working, not a regression.\n{result.stderr}"
          )


      def test_deploy_check_env_block_declares_no_bypass_flag() -> None:
          env = _deploy_check_env()
          present = sorted(_BYPASS_FLAGS & env.keys())
          assert not present, (
              f"ci.yml job '{_JOB_NAME}' must not set {present}. "
              "DJANGO_BUILD suppresses every prod guard unconditionally; "
              "DJANGO_ONESHOT is inert under a *.prod settings module but still "
              "suppresses it against any other module. Either one here makes the "
              "gate pass for no reason."
          )


      @pytest.mark.parametrize(
          ("name", "form", "expected_error"),
          [
              ("REDIS_URL", "empty", "ImproperlyConfigured"),
              ("CSRF_TRUSTED_ORIGINS", "absent", "ValueError"),
          ],
      )
      def test_deploy_check_env_block_rejects_missing_variable(
          name: str, form: str, expected_error: str
      ) -> None:
          env = _deploy_check_env()
          if form == "empty":
              env[name] = ""      # read_env(overwrite=False) will not restore a present key
          else:
              del env[name]       # .env.test does not define it, so it is not back-filled
          result = _run_in_subprocess(_subprocess_env(env), _IMPORT_CODE)
          assert result.returncode != 0, (
              f"removing '{name}' did not break the prod import — this test's "
              f"harness cannot observe a failure, so the parity assertion is worthless"
          )
          assert expected_error in result.stderr
          assert name in result.stderr

  - action: update_comment
    id: change_extend_contract_comment
    path: .github/workflows/ci.yml
    description: >
      Append sentences to the existing `deploy-check` contract comment, directly above
      the job. D7's three properties, plus the module name so `grep` connects the
      comment to the test. This is the **only** `ci.yml` edit in the block (D2) — no key
      is added, removed or reordered, and no step is added to any job.

      Do not rewrite or reorder the existing sentences; BLOCK 1 (`071e5c7`) moved this
      block here and its wording is now accurate. Do not move it. Do not let the new
      sentences restate the variable list — that is the second representation the whole
      design refuses to create, and a list is exactly what goes stale.

      The comment must not become a test oracle: no test asserts on its content, and
      `test_ci_security.py` slices from the `deploy-check:` header while
      `test_docs_ci_parity.py` asserts on unrelated tokens. Confirm both stay green
      after the edit, because a `ci.yml` edit is a `ci.yml` edit.
    code_hint: |
      #   connection). All required production env vars are set to valid non-secret
      #   placeholders so the full prod settings import path is exercised.
      #   The env block below is also read by the test job's
      #   config/settings/tests/test_deploy_check_env_parity.py, which imports
      #   config.settings.prod with exactly this set. Keep the block a non-empty YAML
      #   mapping, and never add DJANGO_BUILD or DJANGO_ONESHOT here: either one
      #   suppresses the guards and makes this gate pass without checking anything.

# ─────────────────────────────────────────────────────────────────────────────
sequence:
  - step: 0
    name: preflight
    actions:
      - "Confirm BLOCK 1 (`071e5c7`) and BLOCK 3 (`9443ade`) are landed and `git log --oneline -3` shows them."
      - "Confirm `.github/workflows/ci.yml`'s `deploy-check` env block has **ten** keys and that `EMAIL_HOST` and `REDIS_URL` are among them. If it does not, BLOCK 1 has not landed — stop and report rather than writing a test against a block the gate is not using."
      - "Confirm the test DB is Up (`.\\Makefile.ps1 test-db`)."
      - "Baseline the scoped suite before editing, so a pre-existing failure is not attributed to this change."
      - "Re-read the ten binding constraints against the tree. The tree wins where they disagree."
    gate: "scoped settings + tests suites green at baseline"
  - step: 1
    name: add the parity module
    depends_on: [0]
    actions:
      - "Create `test_deploy_check_env_parity.py` per `change_add_parity_module`: the ladder helper, the two small helpers, the three tests."
      - "Run it in isolation before touching anything else."
    expect: >
      **Green on arrival.** BLOCK 1 restored the block, so the parity assertion must pass
      against today's `ci.yml`. If it does not, the cause is one of the six mandatory
      variables, the `DJANGO_SECRET_KEY` length/placeholder rules, or an inherited value
      leaking in through an unscrubbed base — diagnose before proceeding. **Do not** edit
      the test to accommodate a failure.
  - step: 2
    name: extend the contract comment
    depends_on: [1]
    actions:
      - "Apply `change_extend_contract_comment` to the `deploy-check` comment block."
      - "Re-read `git diff .github/workflows/ci.yml` and confirm the diff is **comment-only**: no key added, removed or reordered, no step touched, no other job touched."
    note: >
      This is the only step that edits `ci.yml`, and it is what BLOCK 1's "move the
      comment too" rationale is completed by. The comment's placement is the whole
      structural fix; the sentences are the visible-dependency half.
  - step: 3
    name: gates
    depends_on: [2]
    actions:
      - "Run the full `tests.verification_gate` sequence below, including the two
         negative-control demonstrations and the two comment-safety checks."
  - step: 4
    name: hand-off
    depends_on: [3]
    actions:
      - "Re-read `git status --short` and stage explicit paths only (§1 hard rule). Never `git add -A` — the tree carries 18 pre-existing `.ai/audit/**` deletions that must not be swept in."
      - "Do not commit without an explicit user request."
      - "Record the forward constraint on BLOCK 5 in the hand-off: adding the `BOT_USERNAME` guard **must** be accompanied by adding `BOT_USERNAME` to `jobs.deploy-check.env`, and this test is what will otherwise make both the `test` job and `deploy-check` red."
      - "Restate the two `jobs.test.steps` facts for the coordinator: no CI step was added, and none is needed, because the `test` job's pytest invocation carries no path argument and `testpaths` collects every `test_*.py` under `src/backend`."

# ─────────────────────────────────────────────────────────────────────────────
tests:

  must_keep_passing_unchanged:
    - "All of `src/backend/config/settings/tests/**` — in particular `test_settings_secrets.py` (whose `from config.settings.tests.test_prod_logging import TEST_SECRET_KEY, _prod_env_overrides` must keep resolving, BC-5), `test_prod_logging.py`, `test_csrf_trusted_origins.py`, `test_oneshot_settings.py`, `test_settings_defaults.py`, `test_env_allowlist.py`."
    - "`src/backend/tests/test_compose_hardening.py` in full — including `test_compose_oneshot_flags`, which is BLOCK 3's tripwire for the five dev one-shot services."
    - "`src/backend/tests/test_compose_contract.py` in full (phase 01's VAL-004 instance (a); BLOCK 4 is instance (b) and the two must not merge)."
    - "`src/backend/apps/core/tests/test_ci_security.py` in full — including the two `_deploy_check_section()` tests, which slice from the `deploy-check:` header to end-of-file. This is the check that the appended comment (step 2) did not break the slice's negative assertions."
    - "`src/backend/tests/test_docs_ci_parity.py` in full — the same reason; it reads `ci.yml` as text."
    - "`src/telegram_bot/tests/**` — untouched, and the new module must not become reachable from the bot's import path."
    - "Every `prod.py` guard test, because `base.py`'s `.env` handling and the guard bodies are not edited: `test_django_secret_key_required`, `test_django_secret_key_rejects_empty`, `test_bot_token_required_in_production`, `test_google_translate_api_key_required_in_production`, `test_redis_url_required_in_production`, `test_csrf_trusted_origins_required_in_production`, `test_csrf_trusted_origins_skipped_during_build`, `test_csrf_trusted_origins_defaults_empty_in_dev`, `test_csrf_trusted_origins_accepted_in_production`, `test_oneshot_bypasses_secrets_for_oneshot_module`, `test_oneshot_module_still_requires_oneshot_flag`, `test_django_build_flag_bypasses_all_prod_guards`, `test_oneshot_flag_is_inert_under_a_valid_prod_environment`, `test_django_oneshot_does_not_bypass_prod_secrets`, and the nine placeholder / dev-only-dummy rejection tests."

  must_be_added:
    - name: test_deploy_check_env_block_imports_prod_settings
      path: src/backend/config/settings/tests/test_deploy_check_env_parity.py
      why: >
        The block's deliverable. It is the assertion the report's `R-7` says is missing,
        and the reason the phase's only HIGH finding will not recur.
      asserts:
        - "`ci.yml` parses; the document is a mapping; `jobs` is a mapping; `deploy-check` is a **key** of it; its `env` is a `dict`; `len(env) > 0`. Every rung fails closed with a message naming what is missing."
        - "`env['DJANGO_SETTINGS_MODULE'] == 'config.settings.prod'` — a guard against the test silently importing a different module than the job runs."
        - "Every value in the block is a non-empty string. This is the one layer the `.env` back-fill channel cannot mask, because `read_env(overwrite=False)` never overwrites a key that is present."
        - "No value contains a `${{ … }}` expression (D6)."
        - "`import config.settings.prod` exits 0 in a subprocess whose environment is a scrubbed `MINIMAL_BASE` (`PATH`, `HOME`) plus exactly the parsed block, with `PYTHONPATH` supplied by the shared helper."
        - "On failure the message names the layer, `.github/workflows/ci.yml` → `jobs.deploy-check.env`, and says that a newly-required production variable is the expected cause."
      not_asserted: >
        The test does not assert which variables are *required*. It asserts that the ones
        the job supplies are sufficient — which is the direction that matters and the
        direction that actually failed. A curated `REQUIRED_PROD_ENV_VARS` list would be
        a second source of truth that is true whenever both sides drift together (D3).

    - name: test_deploy_check_env_block_declares_no_bypass_flag
      path: src/backend/config/settings/tests/test_deploy_check_env_parity.py
      why: >
        D5. `DJANGO_BUILD` is honoured by `prod.py` **unconditionally** and is not scoped
        by BLOCK 3, so it would suppress every guard and make the gate pass for no reason
        at all. `DJANGO_ONESHOT` is inert against a `*.prod` module since BLOCK 3 but
        would suppress every guard against any other module. Neither name appears in
        `ci.yml` today; the assertion is forward-looking and `DJANGO_BUILD` is the live
        case. The block's own note 4 covers only the inert one and is corrected here.
      asserts:
        - "`{'DJANGO_BUILD', 'DJANGO_ONESHOT'} & env.keys()` is empty."
        - "The message names which of the two is the live hazard, so the reader does not have to know BLOCK 3's mechanism to act."

    - name: test_deploy_check_env_block_rejects_missing_variable
      path: src/backend/config/settings/tests/test_deploy_check_env_parity.py
      why: >
        The permanent, portable form of the negative control, and the reason the parity
        test's green result means anything: a harness that cannot observe a failure would
        also report success on the parity assertion.
      asserts:
        - "Row `('REDIS_URL', 'empty')` — present-but-empty, so `read_env(overwrite=False)` does not restore it. Valid in the **Docker test container** and in the **CI `test` runner** (the key is present in both, and the empty-string form of `DJANGO_SECRET_KEY` is the one case that is *not* portable, because with no `src/.env` in CI `base.py` takes its missing-file branch and `sys.exit(1)`s). The import fails with `ImproperlyConfigured` and stderr names `REDIS_URL`."
        - "Row `('CSRF_TRUSTED_ORIGINS', 'absent')` — the key is **deleted**, which works in both environments precisely because `.env.test` does not define it, so there is nothing to back-fill. The import fails with a bare `ValueError` and stderr names `CSRF_TRUSTED_ORIGINS`."
        - "Each row asserts **its own** exception type. The point is that `config.settings.prod` has no single failure surface: six guards raise `ImproperlyConfigured`, two raise a bare `ValueError`, an unset `DJANGO_SECRET_KEY` raises from `base.py` with a different message again, and a missing `.env` is a `sys.exit(1)` rather than an exception. A single-string stderr assertion is wrong on at least one row of the ten."
        - "On `returncode == 0` the message says the harness cannot observe a failure and the parity assertion is therefore worthless — i.e. this test failing *green* is itself the alarm."

  must_be_demonstrated_red:
    - >
      **Demonstration A — the key is emptied in the parsed block.** Set
      `REDIS_URL: ""` in `ci.yml`'s `deploy-check` env block and run
      `test_deploy_check_env_block_imports_prod_settings`. It must fail on the
      **all-values-non-empty** layer, naming `REDIS_URL`. Restore and confirm green.
      *Environment:* valid in the Docker test container **and** in the CI `test` runner —
      this one edits the YAML, not the process environment, so the `.env` back-fill
      channel is not involved either way.
    - >
      **Demonstration B — the key is removed from the parsed block.** Delete the
      `REDIS_URL` line from `ci.yml` entirely and re-run the same test. It must fail
      again, this time at the **import** layer, with the forward-pointing message. This
      is the faithful reproduction of the defect as it actually occurred — the key was
      absent, not empty — and it is the only demonstration that proves the *subprocess
      layer* fires rather than the cheap string check. Restore and confirm green.
      *Environment:* valid in the Docker test container **and** in the CI `test` runner,
      for the same reason. It passes there because the *subprocess* environment is
      scrubbed (`BC-3`), so no inherited `REDIS_URL` and no `.env` back-fill can rescue
      the import.
    - >
      **Demonstration C — the vacuity guard.** Temporarily rename the `deploy-check:` job
      key in `ci.yml` (e.g. to `deploy-check-disabled:`) and run the module. All three
      tests must fail with the ladder's own message, **not** with a `KeyError`, a
      `TypeError` or a skip. This is the demonstration the block's own risk register names
      as its highest-likelihood failure. Restore and confirm green.
      *Environment:* both.
    - >
      **Demonstration D — the no-bypass-flag assertion.** Temporarily add
      `DJANGO_BUILD: "1"` to the `deploy-check` env block and run the module.
      `test_deploy_check_env_block_declares_no_bypass_flag` must fail naming
      `DJANGO_BUILD`. Observe at the same time that
      `test_deploy_check_env_block_imports_prod_settings` **still passes** — the import
      genuinely succeeds, which is precisely why the two tests are separate (D5) and why
      the import test alone would be insufficient. Restore and confirm green.
      *Environment:* both.
    - >
      **Demonstration E — the comment edit is inert.** After step 2, confirm
      `git diff .github/workflows/ci.yml` shows comment lines only, and that
      `test_ci_security.py` and `test_docs_ci_parity.py` are still green. Both read
      `ci.yml`; a comment edit can only be inert, and the point of running them is to say
      so rather than assume it.
    - >
      All five are **Validator duties, not shipped tests** (except the two rows of
      `test_deploy_check_env_block_rejects_missing_variable`, which are shipped and run
      continuously). Record the output of each. A negative control that was never seen
      red proves nothing.

  need_no_test:
    - >
      The ten-variable set itself, as a named list. See D3: a curated
      `REQUIRED_PROD_ENV_VARS` constant is a second representation that is true whenever
      both sides drift together and cannot see a *new guard* adding a name to neither side.
    - >
      The `deploy-check` job's `runs-on`, `steps` or the `check --deploy --fail-level
      WARNING` invocation. `test_ci_security.py` already pins those, and duplicating them
      here would create the second source of truth D3 rejects.
    - >
      `jobs.test.steps` (D2). Its existing content is correct as-is; the new test is
      collected by `testpaths` without it.
    - >
      Any change to `prod.py`. The test discovers what prod requires by importing it. A
      test that pins the requirement set as data would be asserting a copy.

  verification_gate:
    - step: 1
      name: scoped run (the new module alone)
      command: >
        `$dc run --rm -e PYTEST_SKIP_MARKERS=seed -e
        PYTEST_OPTS="src/backend/config/settings/tests/test_deploy_check_env_parity.py" test`
        with `$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test
        -f docker-compose.yml -f docker-compose.test.yml'`
      expect: >
        **3 passed** (the parity test, the bypass-flag test, and the two parametrizations
        of the negative control). If the count differs, collection picked up something
        else — check for a duplicate module.
    - step: 2
      name: scoped run (the whole affected surface)
      command: >
        `$dc run --rm -e PYTEST_SKIP_MARKERS=seed -e
        PYTEST_OPTS="src/backend/config/settings/tests src/backend/tests src/backend/apps/core/tests/test_ci_security.py" test`
      expect: >
        Green, and the total count is the pre-existing count **plus 3**. A drop means a
        collection or import regression — most likely the `test_prod_logging` import
        (BC-5).
    - step: 3
      name: full fast gate
      command: ".\\Makefile.ps1 test"
      expect: "green. The new module is collected automatically by the existing invocation (D2); its presence in this run is the proof."
    - step: 4
      name: static gates
      command: "uv run ruff check src/ and uv run basedpyright src/"
      expect: >
        Both green. The new module must type-check under the project's basedpyright
        configuration: `_deploy_check_env` returns `dict[str, str]`, the ladder's
        `isinstance` narrowing is what makes the returned dict type-check, and
        `YAML(typ="safe")` is already used in `test_compose_contract.py` so the typing
        pattern is known-good. `ruff check --fix` if the import order trips `I001`.
    - step: 5
      name: the BLOCK 1 gate, re-run
      command: >
        `uv run python src/backend/manage.py check --deploy --fail-level WARNING` with
        exactly the `deploy-check` env block and nothing else
      expect: >
        Exit 0. BLOCK 4 does not change the block, so this must still hold — but the YAML
        is now consumed by a test, so a malformed block breaks collection as well as the
        job, and both halves are worth confirming.
    - step: 6
      name: the CI collection contract, confirmed
      command: >
        `$dc run --rm -e PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="--collect-only -q src/backend" test`
        (or the equivalent `--collect-only` invocation in the container)
      expect: >
        `test_deploy_check_env_parity.py` appears in the collection. This is the direct
        proof of D2: the `test` job runs pytest with **no path argument** and
        `testpaths = ["src/backend", "src/telegram_bot"]`, so no `jobs.test.steps` edit
        was needed and none was made.
    - step: 7
      name: negative controls A–E
      command: "the five demonstrations above, each restored afterwards"
      expect: >
        Each red, then green again. Record every output. Also record which of the two
        environments each was run in, and note explicitly if a demonstration could not
        be run in one of them.
    - step: 8
      name: i18n completeness
      command: "part of step 3's full run"
      expect: >
        Green. No user-visible string is introduced; the test module is not user-facing
        and the comment is a CI file. Nothing to translate.

acceptance_criteria:
  - >
    `src/backend/config/settings/tests/test_deploy_check_env_parity.py` exists and
    contains three test functions, of which the negative control is parametrized over two
    rows — **4 collected tests** in total.
  - >
    The test fails closed at every rung of the non-vacuity ladder, locates the job with
    `"deploy-check" in jobs` rather than `jobs.get(...)`, and contains no `pytest.skip`,
    `skipif` or `xfail` anywhere.
  - >
    The subprocess environment is a scrubbed `MINIMAL_BASE` (`PATH`, `HOME`) merged with
    the parsed block, and is never seeded from `os.environ`.
  - >
    The module imports `_run_in_subprocess` from `test_prod_logging` and defines **no**
    subprocess helper of its own, **no** prod-env builder, and **no** new credential-shaped
    literal.
  - >
    The no-bypass-flag assertion covers **both** `DJANGO_BUILD` and `DJANGO_ONESHOT`, and
    ships as its own test rather than as a clause inside the import test.
  - >
    The negative control covers both masking channels — present-but-empty for a key
    `.env.test` would otherwise restore, deleted for a key it does not define — and each
    row asserts its own exception surface (`ImproperlyConfigured` and a bare `ValueError`).
  - >
    No assertion message in the new module interpolates a value read from the parsed env
    block, and the module docstring states that relying on `result.stderr` depends on
    `prod.py`'s value-free exception contract.
  - >
    `git diff .github/workflows/ci.yml` is **comment-only**: the block's ten keys, the
    `deploy-check` steps, `jobs.test` and every other job are byte-identical.
  - >
    The appended comment names the test module and states the three properties the block
    must keep — non-empty YAML mapping, never a bypass flag — without restating the
    variable list.
  - >
    `jobs.test.steps` was **not** edited, and the block's earlier file-surface line
    mandating that edit is superseded by D2 with the evidence recorded.
  - >
    Demonstrations A–E above were each shown red and then green, and their output and
    environment were recorded.
  - >
    Everything in `must_keep_passing_unchanged` is green and unmodified, including
    `test_ci_security.py` — whose `_deploy_check_section()` fragility is **recorded as a
    follow-up, not fixed here**.
  - >
    `uv run ruff check src/` and `uv run basedpyright src/` are green.
  - >
    No settings module, compose file, Dockerfile, Makefile or `src/telegram_bot/**` file
    is modified. No file under `.ai/audit/**` is edited, restored or re-created.
  - >
    The hand-off records the **forward constraint on BLOCK 5**: its `BOT_USERNAME` guard
    must land together with `BOT_USERNAME` added to `jobs.deploy-check.env`, and states
    plainly that this test going red at that moment is the gate working.
  - >
    The hand-off names any gate that could not be run in this environment rather than
    implying it passed, and states that nothing was committed without an explicit user
    request.
```

**Why this shape.** The block's value is entirely in whether the test can be fooled. A
YAML-consuming test has exactly one way to be useless — find nothing, or find something
the application does not need, and pass — so the whole design is spent on the
non-vacuity ladder, the scrubbed environment, and the shipped negative control. The
scrubbed environment is the part most likely to be got wrong silently: every existing
helper in this package seeds from `os.environ`, which is right for them and wrong here,
because the entire claim is that the parsed block *alone* determines the outcome.

**Three decisions worth the coordinator's attention.** First, **D2 reverses a
mandate in the plan above it** — the `jobs.test.steps` edit is not merely unnecessary but
wrong, and `ci.yml`'s diff for this block is one comment block. Second, **D4's
present-vs-absent split is not a stylistic preference**: the local test container
bind-mounts `.env.test` as `src/.env`, so a *deleted* key is silently restored and a
"negative control" that passes for the wrong reason is worse than none; the two rows are
chosen so that each masking channel is worked around by the row that can survive it, and
each is valid in both environments. Third, **D9 makes BLOCK 5's cost visible instead of
hiding it**: this block will hand BLOCK 5 a red test and a red `deploy-check` job unless
BLOCK 5 adds `BOT_USERNAME` to the env block in the same change. That is the mechanism
working, and the plan deliberately refuses to suppress it.

**One residual, stated honestly.** The guarantee is conditioned on the `deploy-check` job
continuing to exist under that name with a mapping-shaped `env:` block, and on `ci.yml`
continuing to parse. Both are now loud rather than silent, which is as far as an
execution-based assertion can go; a rename or a reformat is a *failing* test now rather
than a silent one, which is the improvement available without codegen. The follow-ups
recorded above (`actionlint` adoption, the `_deploy_check_section()` fragility,
consolidating the four subprocess helpers) are real and are routed out of this block by
§6 and §5.2.

---

### BLOCK 5 — Shared secret-validation helper and the `BOT_USERNAME` guard (CFG-011 + CFG-005)

| | |
|---|---|
| **Findings owned** | `CFG-011` (helper extraction + comment correction), `CFG-005` (prod/dev guard, migration validation, data repair) |
| **`depends_on`** | **BLOCK 3** (both halves edit `prod.py` and the settings chain; BLOCK 3 may have added a new module) |
| **Priority** | P1 |
| **Roster** | **Implementor, Auditor, Planner, Validator** |

**Ordering is intra-block and mandatory: CFG-011's helper extraction lands first, then
CFG-005 builds on it.** Adding a third copy of the placeholder regex is what the report
forbids, and the report's own roadmap is explicit that the auditor's ordering (CFG-011
last) is *"the wrong order"*.

**Agent requirement decision.**
- **Implementor — yes.** Always.
- **Auditor — yes.** Two things must be established before code is written. First, the
  full consumer list of the persisted bot username — the report names the footer, the
  context processor, the consent deep link, the listings view and a templatetag, and
  the Auditor must confirm the set is complete and current, because a miss means either
  the finding is not fixed or a live link regresses. Second, the **repair surface**: what
  already exists in `apps/core/management/commands/` (13 commands, English untranslated
  help text), whether `SiteConfig` is admin-editable today, and whether the 1-hour cache
  means a repair must also invalidate it.
- **Researcher — no.** G4 and G5 are *design* questions, not ecosystem questions: the
  authoritative validation contract already exists in the model
  (`^[A-Za-z0-9_]{3,32}$`), the fix is derivable entirely from the repository, and the
  project has a services-layer and management-command convention to follow. A Researcher
  pass would restate `docs/django-admin.md`.
- **Planner — yes.** Two open questions (G4, G5) with real consequences each, a new
  shared helper with a public surface, a migration edit, and a decision about whether the
  guard lives in `prod.py`, `dev.py`, both, or the new module BLOCK 3 created.
- **Validator — yes.** Editing a **shipped migration** and adding a data-repair path are
  both outside the ordinary test-and-green loop, and the DB-wins-over-env semantics mean a
  green suite does **not** prove a real deployment is repaired.

**Findings and notes carried forward.**
1. **There is no guard for `BOT_USERNAME` anywhere.** `prod.py` validates exactly three
   secrets; `base.py` gives `BOT_USERNAME` an empty default; both `.env.prod.example` and
   `.env.dev.example` ship the literal placeholder `<your-bot-username>`.
2. **The migration's validator is bypassed provably.** `0003_add_bot_username.py` declares
   a `RegexValidator` and then seeds via `QuerySet.update()`, which does not call
   `full_clean()`. The shipped placeholder contains `<`, `>` and `-`, all rejected by the
   model's own regex.
3. **Editing `0003` protects only fresh databases.** Applied deployments do not re-run
   it, and even a forced re-run is gated on `filter(pk=1, bot_username="bazuna_bot")`, so
   a value already overwritten with the placeholder is not repaired. **This is G5 and it
   must be answered, not assumed away.** The Planner's options: (i) a management command
   that re-syncs `SiteConfig.bot_username` from settings when the current value fails the
   validator, plus a cache invalidation; (ii) a **new** forward migration that repairs
   the value; (iii) documented manual admin repair per deployment. (ii) is the only
   option that reaches deployments that never run a new command — but it adds a migration
   number to a directory shared with other phases, which phase 01's §5.5 flagged as a
   real collision risk (`apps/core/migrations/0004_*` already exists as the highest).
4. **The DB value wins over the env var at read time.** `get_bot_username()` reads the
   model and caches it for an hour. So a correct `BOT_USERNAME` in `.env.prod` does **not**
   fix a bad DB row, and a repair that does not invalidate the cache is not observed for
   up to an hour. Any chosen repair path must state this.
5. **The bot itself is unaffected** — the support handler derives the username from the
   Telegram API. The blast radius is web-side deep links.
6. **G4 — what is a "placeholder" for `BOT_USERNAME` is open.** `^<[^>]+>$` is strictly
   *weaker* than `^[A-Za-z0-9_]{3,32}$`; it accepts nothing useful and rejects a real
   username, but it also accepts junk like `not a username` that the model rejects. The
   shared helper must therefore expose a **validator**, not only a placeholder detector.
   The Planner states the validation surface; the report's constraint is that the helper
   is the single home and both `prod.py` and `dev.py` use it.
7. **The dev half is the cheaper one and stops the bad value reaching the database**,
   because the dev one-shot services run the migration. The report explicitly wants both
   halves, dev first.
8. **`git grep pydantic_settings|BaseSettings` returns zero.** CFG-011's Pydantic half is
   rejected by the report and appears in **no** block of this plan. Do not introduce
   `pydantic-settings`.
9. **`base.py`'s `BOT_TOKEN` comment must be corrected to name the real mechanism and
   both locations** — and after BLOCK 5 it should name the **shared helper**, not two
   regexes, because there will no longer be two.
10. **The existing migration test must keep passing.** All three tests in
    `test_migration_seed_bot_username.py` use values matching `^[A-Za-z0-9_]{3,32}$` and
    use `override_settings`, which bypasses import-time guards — which is exactly why a
    `full_clean()` change in the migration will not break them. The Planner must still
    run them.

**File surface (semantic units).**
- **New (recommended):** a small shared helper under `src/backend/config/settings/`
  (e.g. `secret_validation.py`) exposing the placeholder detector and a value validator.
  It must import **nothing** from `prod.py` or `dev.py` — that constraint is the reason
  `dev.py` duplicated the regex in the first place, and repeating it would defeat the
  block.
- `src/backend/config/settings/prod.py` → the `BOT_USERNAME` guard; the comment block
  above `_validate_production_secret` (which currently documents the shared helper
  indirectly and must be updated).
- `src/backend/config/settings/dev.py` → `_BOT_TOKEN_PLACEHOLDER_RE` (consume the helper);
  the `BOT_USERNAME` guard; the "Mirrors prod" comment.
- `src/backend/config/settings/base.py` → the `BOT_TOKEN` comment above the `env()`
  read (CFG-011's doc half).
- `src/backend/apps/core/migrations/0003_add_bot_username.py` → `seed_bot_username()`
  (fetch, assign, `full_clean()`, save). **Editing an applied migration is a deliberate,
  documented choice** — it protects fresh databases only, and the module docstring must
  say so.
- **G5 outcome, whichever is chosen:** a new management command under
  `src/backend/apps/core/management/commands/`, **or** a new migration in
  `src/backend/apps/core/migrations/` (next number `0005_*` — **check the directory
  immediately before creating**; phase 03 also plans migrations in `apps/core`), **or**
  documentation only.
- `src/backend/apps/core/services/site_config.py` → **only if** the chosen repair path
  needs a cache invalidation call. Read-only otherwise.
- **Not touched:** `SiteConfig` model definition, `get_bot_username()`'s fallback string,
  the bot handlers, any template.

**Tests required.**
- *Must keep passing unchanged:* all of
  `src/backend/apps/core/tests/test_migration_seed_bot_username.py`; all of
  `src/backend/apps/core/tests/test_migrate_locked.py`; all of
  `src/backend/tests/test_docs_ci_parity.py` (it asserts against command docs);
  `test_settings_defaults.py`.
- *Must be added:*
  - A placeholder `BOT_USERNAME` is rejected under `config.settings.prod` **and** under
    `config.settings.dev`.
  - A real-format `BOT_USERNAME` (matching `^[A-Za-z0-9_]{3,32}$`) is accepted in both.
  - A value that is *not* a `<...>` placeholder but fails the model regex is rejected in
    production — this is the assertion that distinguishes G4 option (b) from (a) and is
    the reason the helper must expose a validator.
  - The migration refuses to write a value failing the `RegexValidator`. This one must
    drive `seed_bot_username()` through a historical-model `apps.get_model` harness
    (the existing migration test module shows the pattern) and assert the raise.
  - G5: whatever the chosen repair path is, a test that a `SiteConfig` row holding an
    invalid username is corrected and that the cached value is invalidated. If the choice
    is "manual admin repair", the test is replaced by an explicit documentation assertion
    in §8.
- *Gate:* `$dc run --rm -e PYTEST_OPTS="src/backend/config/settings/tests src/backend/apps/core/tests/test_migration_seed_bot_username.py src/backend/apps/core/tests/test_migrate_locked.py" test`,
  then **`.\Makefile.ps1 test-recreate`** (a migration changed), then `.\Makefile.ps1 test`.

**Risk / rollback.**
- *Risk:* the helper importing from `prod.py` to reuse the regex, creating an import cycle
  (`prod.py` star-imports `base`, and `dev.py` must not pull prod's logging/Sentry
  config). The constraint is stated; the Validator checks the import graph.
- *Risk:* a `full_clean()` in the migration rejects the **default** value in a fresh
  database. `bazuna_bot` matches the regex, so this is safe — but assert it, do not
  assume it.
- *Risk:* a repair command that does not invalidate the cached bot username, so the fix
  appears not to work for an hour (note 4). This is the most likely "the fix is broken"
  report.
- *Risk:* a new `0005_*` migration number colliding with phase 03. Check the directory
  immediately before generating.
- *Rollback:* the guard halves and the migration edit are separately revertible. Reverting the
  guard while keeping the stricter migration is safe. Reverting the migration after a
  repair path has shipped leaves a repair command that is still correct.

#### BLOCK 5 — Implementation task

> Written by the BLOCK 5 Planner against the tree at `4fd8bd0` (BLOCK 1 = `071e5c7`,
> BLOCK 2 = `cb31553`, BLOCK 3 = `9443ade`, BLOCK 4 = `4fd8bd0`). This task resolves
> G4 and G5, corrects five stale claims in the block's notes above, and is the contract
> the BLOCK 5 Implementor executes. **Never use line numbers** — every target below is a
> file, module, class, function, variable, comment block or workflow job block.
>
> **This subsection supersedes the "Findings and notes carried forward", "File surface
> (semantic units)" and "Tests required" paragraphs above it wherever they disagree.** It
> is an append; nothing above it is edited. Four of its rulings reverse what those
> paragraphs state: **D1** makes `BOT_USERNAME` a required non-empty production variable
> (so `ci.yml` and two test env builders must change), **D2/D3** place the guard in
> `prod.py` **only** — the report's `dev.py` half is rejected as ineffective after BLOCK 3
> — **D4** chooses a management command over a forward migration, and **D7** records the
> CI-side verification obligation that a local green run cannot discharge.

```yaml
id: block5-cfg005-cfg011-bot-username-guard

title: >
  Extract the shared secret-validation helper, guard BOT_USERNAME in production,
  make migration 0003 validate before writing, and ship a repair command (CFG-011 + CFG-005)

priority: P1

depends_on:
  - "BLOCK 3 (9443ade) — config/settings/oneshot.py exists and the dev one-shots resolve it, which is what makes a dev.py guard inert (D3) and what makes the test_django_build_flag_bypasses_all_prod_guards test decide between a gated and an ungated guard (D2)"
  - "BLOCK 4 (4fd8bd0) — test_deploy_check_env_parity.py parses the deploy-check env block and drives a prod import with exactly that set; it is the tripwire that obliges BOT_USERNAME to be added to ci.yml in the same change (C6)"

source_reference: .ai/plans/02-config-secrets-remediation.md
source_section: "BLOCK 5 — Shared secret-validation helper and the BOT_USERNAME guard (CFG-011 + CFG-005)"
source_file: .ai/audit/99-validation/02-config-secrets-validated-findings.md
source_blocks:
  - "BLOCK 5 — Shared secret-validation helper and the BOT_USERNAME guard (CFG-011 + CFG-005)"
  - "CFG-005 — BOT_USERNAME placeholder is unvalidated and is persisted into the DB by a migration"
  - "CFG-011 — base.py comment cites a non-existent \"Env schema\" for BOT_TOKEN validation"
  - "G4 — What counts as a \"placeholder\" for BOT_USERNAME"
  - "G5 — CFG-005 data repair: repair command or manual admin edit"

description: >
  `config/settings/base.py` reads `BOT_USERNAME` with a silent `default=""`. Both
  `.env.prod.example` and `.env.dev.example` ship the literal
  `BOT_USERNAME=<your-bot-username>`, no settings module validates it, and migration
  `0003_add_bot_username.py` persists it into the `SiteConfig` singleton through
  `QuerySet.update()` — which never calls `full_clean()`, so the field's own
  `RegexValidator ^[A-Za-z0-9_]{3,32}$` is never evaluated. From that point the database
  wins over the environment for the rest of the deployment's life: `get_bot_username()`
  reads the model and caches it for an hour, and the `telegram_deep_link` template tag
  base64-encodes it into a `data-bot-encoded` attribute behind an `href="#"`, so nothing on
  the rendered page reveals that every Telegram contact and login deep link on the site is
  dead. The only user-visible symptom is a broken contact button; the only cleartext
  `{{ bot_username }}` reader in the template tree is `privacy.html`.

  This block closes the defect at four layers and repairs the data. A new shared helper
  `config/settings/secret_validation.py` becomes the single home for placeholder detection
  and for the bot-username validity contract, replacing the two hand-rolled copies CFG-011
  complains about. `config/settings/prod.py` gains a `BOT_USERNAME` guard — gated like the
  other seven, and placed after all of them so the existing per-guard failure ordering stays
  intact. `ci.yml`'s `deploy-check` env block and the two subprocess env builders that
  stand in for production gain the variable, so the guard does not turn four shipped green
  tests red. Migration `0003` validates before writing. A new
  `manage.py repair_bot_username` command re-synchronises the singleton from settings when —
  and only when — the persisted value fails the validator, using `save()` so the existing
  `post_save` receiver invalidates both caches for free.

  **The block's defining hazard is not the code; it is that a green
  `.\Makefile.ps1 test` is not evidence.** The Docker test container receives
  `BOT_USERNAME=test-bot` from `.env.test` through `env_file:` and again through the
  `./.env.test:/app/src/.env:ro` bind-mount that `base.py`'s present-file branch reads with
  `read_env(overwrite=False)`. The CI `test` job has neither. Two module-scoped builders
  (`_prod_env_overrides`, `_prod_env`) start from `os.environ` and do not set the key, so
  the same tests are green locally and red in CI. Every step below that touches a
  production env fixture is specified against that divergence, and `acceptance_criteria`
  forbids reporting this block complete on a local green run alone.

goals:
  - >
    A single shared helper owns placeholder detection and bot-username validity.
    `config/settings/prod.py` and any future consumer import it; no second copy of
    `^<[^>]+>$` and no second copy of `^[A-Za-z0-9_]{3,32}$` exist in the repository.
  - >
    `config.settings.prod` refuses to import with a `BOT_USERNAME` that is empty, that is a
    shipped `<...>` placeholder, or that fails the model regex — with a value-free
    `ImproperlyConfigured` naming the variable and the remediation.
  - >
    The guard is gated exactly like the seven beside it, so the Docker builder stage
    (`DJANGO_BUILD=1`, no `.env`) and the dev bootstrap one-shots
    (`config.settings.oneshot` + `DJANGO_ONESHOT=1`) continue to import.
  - >
    Migration `0003` cannot write a value its own `RegexValidator` rejects, and
    `test_django_build_flag_bypasses_all_prod_guards` stays green without being weakened.
  - >
    A deployment whose `SiteConfig.bot_username` holds a placeholder can be repaired with
    one command, and the repair is observable immediately rather than up to an hour later.
  - >
    The block is provably correct in the CI `test` job's environment as well as in the
    Docker test container, and the difference between the two is exercised rather than
    assumed.
  - >
    No user-visible string is introduced; no new dependency; no new CI job; no new
    migration; no file under `.ai/audit/**` touched.

# ─────────────────────────────────────────────────────────────────────────────
# Decisions taken by the BLOCK 5 Planner
# ─────────────────────────────────────────────────────────────────────────────
decisions:
  - id: "D1 — G4: required-non-empty. The loud failure is preferred."
    choice: >
      The shared helper exposes `validate_bot_username(var_name, value)`, which rejects in
      this order: **empty**, then **placeholder** (`^<[^>]+>$`), then **model regex**
      (`^[A-Za-z0-9_]{3,32}$`). In production an unset or empty `BOT_USERNAME` is a hard
      `ImproperlyConfigured`, not a tolerated default. Consequences, all in the same change:
      `ci.yml` `jobs.deploy-check.env` gains `BOT_USERNAME`, `_prod_env_overrides` in
      `test_prod_logging.py` gains it, and `_prod_env` in `test_csrf_trusted_origins.py`
      gains it.
    rationale: >
      The rejected option is validate-if-present, under which `BOT_USERNAME=` ships a bot
      called `bazuna_bot` — a different wrong link rather than an obviously wrong one. That
      is *the same harm class the finding is about*: the report's own statement is that a
      seeded placeholder "produces dead `t.me/` links site-wide", and `bazuna_bot` is
      equally dead for any deployment whose real bot is named something else. Nothing
      downstream can tell the two apart, because the DB value wins over env and
      `get_bot_username()`'s own fallback is the literal `"bazuna_bot"`. Requiring the
      value converts a silent wrong link into a boot refusal, which is the same treatment
      the other seven prod guards already give their variables, and it is the only option
      under which the *empty* case — arguably the more likely operator mistake, because the
      DB wins over env so the line looks decorative — is caught at all.
      The cost is real and is accepted: three one-line fixture edits, all in this change,
      and a deliberate one-time breaking change for any production deployment currently
      running with an empty `BOT_USERNAME` and a `bazuna_bot` row. That deployment is
      already serving a possibly-wrong deep link, and it gets the repair command (C10) plus
      a documented manual admin path (C14) rather than a new bypass channel — adding an
      escape hatch would recreate exactly the class of hole BLOCK 3 closed.
    alternative_rejected: >
      Validate-if-present, on the argument that it needs no CI change. That argument is
      correct about the cost and wrong about the failure mode: it trades a loud, correct,
      immediately-actionable boot failure for a permanently silent wrong link on the site's
      single most important conversion path.
    g4_discriminating_assertion: >
      `test_bot_username_rejects_empty_in_production`. A **non**-placeholder value that fails
      the model regex is rejected under *both* options; only the empty case discriminates.
      Both are shipped — see `tests.must_be_added`.

  - id: "D2 — Secret or invariant: GATED. The bypass comment must read eight, not seven."
    choice: >
      The guard is written as an eighth `if not _SKIP_SECRET_VALIDATION:` block in
      `prod.py`, and the bypass comment block's "The seven secret guards below" becomes
      "The eight secret guards below". No `DJANGO_BUILD` exemption is added, no
      `ALLOWED_HOSTS`-style ungated block is added, and `oneshot.py` is not edited.
    rationale: >
      An ungated guard is unconditionally fatal here, for a reason the plan above does not
      address. The Docker **builder** stage runs `collectstatic` under
      `config.settings.prod` with `DJANGO_BUILD=1` and **no `.env` file at all**, so
      `BOT_USERNAME` is `""`; an ungated guard would make the image build fail. And
      `test_oneshot_settings.py::test_django_build_flag_bypasses_all_prod_guards` asserts
      that *every* prod guard is skipped under `DJANGO_BUILD=1` — so an ungated guard breaks
      that shipped green test by construction, unconditionally, and would force a rewrite of
      a test whose whole purpose is to be a regression guard on the bypass mechanism.
      `prod.py`'s existing ungated `ALLOWED_HOSTS` check survives only because
      `base.py` gives it a default that the build happens to satisfy; there is no such
      luck available here.
      The honesty point, which must appear in the guard's comment: `BOT_USERNAME` is **not
      a secret** — it is a public Telegram handle, and the finding is a correctness defect,
      not a disclosure. It is written inside the secret gate because the gate is the
      project's existing mechanism for "this variable must be real when we are serving
      traffic", and because reusing it is strictly cheaper than inventing a second bypass
      discipline that BLOCK 3 would then have to re-audit. Say exactly that in the comment;
      a reader who is told it is gated and not told why will assume the next editor can
      widen it.

  - id: "D3 — Where the guard lives: prod.py ONLY. The report's dev.py half is rejected."
    choice: >
      `dev.py` is **not edited**. No `BOT_USERNAME` guard is added to it, no helper import
      is added to it, and no comment is corrected in it. `oneshot.py` is not edited.
    rationale: >
      The block's note 7 — "the dev half is the cheaper one and stops the bad value
      reaching the database, because the dev one-shot services use prod settings and run
      the migration" — was true when the report was written and is **false after BLOCK 3**.
      The five dev one-shot services now resolve `config.settings.oneshot`, not `prod`;
      `oneshot.py` is `from .prod import *`, so prod's guard *code* executes, but
      `_SKIP_SECRET_VALIDATION` is `True` there (the module name does not end in `.prod`),
      so **any guard written inside `if not _SKIP_SECRET_VALIDATION:` is inert for
      `oneshot`**. A `dev.py` guard would therefore cover only the dev `web` and `bot`,
      which do **not** run the migration and therefore cannot put a value into the
      database. It would stop nothing that reaches the DB — the report's own stated purpose
      for the dev half.
      What actually protects the dev database is the **migration's `full_clean()`** (C8),
      which runs in every environment including `oneshot`, is not a settings-module guard,
      and is exercised by the three existing seed tests against the live app registry. That
      is the correct replacement for the dev half, and `test_bot_username_guard_skipped_for_oneshot_bootstrap`
      pins its absence so a future editor does not "fix" the gap by adding an ungated
      guard to `oneshot.py`.
      A secondary reason, independent of the above: requiring `BOT_USERNAME` in `dev.py`
      would make every fresh developer setup fail to import, because `.env.dev.example`
      ships the placeholder and `base.py` defaults it to `""`. That is a real
      developer-experience regression bought for no protection.

  - id: "D4 — G5: a management command, using save(). No new migration."
    choice: >
      A new command `apps/core/management/commands/repair_bot_username.py` guarded by a
      new `AdvisoryLockId.REPAIR_BOT_USERNAME = 13`, with `--dry-run`, wrapped in
      `transaction.atomic()`. It re-synchronises `SiteConfig.bot_username` from
      `settings.BOT_USERNAME` **only when the persisted value fails the model validator**,
      and it uses **`instance.save()`**, never `QuerySet.update()`.
      Option (ii), a forward migration, is **rejected**. Option (iii), documented manual
      admin repair, is **kept** and is referenced by the command's docstring and by
      `docs/01-spec/contact-us.md` (C14), at zero code cost.
    rationale: >
      The plan's note 3 argues for (ii) on the grounds that it "is the only option that
      reaches deployments that never run a new command". That premise is weaker than it
      looks, and the option has a decisive defect: a migration that reads
      `settings.BOT_USERNAME` embeds **runtime configuration into a historical record**,
      so a deployment whose env is wrong installs a permanently-wrong migration, and every
      fresh database built from it afterwards is poisoned. `reverse_code` is `noop`, so
      there is no way to undo a value written from a bad env. Worse, a migration runs at an
      arbitrary moment inside an upgrade — typically before the operator has corrected
      `.env.prod` — whereas a command runs when the operator chooses, which is the correct
      order. Finally the number is contested: `0005_scheduler_daily_state.py` already
      exists (phase 01), the next free number is `0006_*`, and phase 03 also plans
      migrations in `apps/core`. A command carries no shared-artefact reservation.
      `save()` over `update()` is the whole difference between a repair that works and a
      repair that appears not to work: `QuerySet.update()` emits no `post_save`, so
      `invalidate_site_config()` and `invalidate_bot_username_cache()` would not fire and
      the stale value would survive in the cache for the full `SITE_CONFIG_CACHE_TTL` of
      3600 seconds. That is the single most likely "the fix is broken" report this block
      will generate, and `test_repair_bot_username_invalidates_cached_bot_username` is the
      assertion that closes it.
    command_semantics: >
      Four cases, in this order, each with its own outcome:
      1. `settings.BOT_USERNAME` is empty or fails the helper's validator → the command
         **cannot** repair, logs an error naming the variable and the `.env.prod` file, and
         exits **non-zero** without touching the row. Rationale: the env is the source, and
         substituting the model default here would manufacture the exact silent
         `bazuna_bot` failure mode D1 exists to prevent. The admin path remains open.
      2. The persisted value already satisfies the validator → **no-op**, logged at info,
         exit 0. A correct admin-edited value is never overwritten; the DB is the operator
         of record by design.
      3. Otherwise → assign, `full_clean()` (which raises `ValidationError` if the source
         value is invalid, naming the field), `save()`, log, exit 0.
      4. `--dry-run` reports which of 1–3 applies and changes nothing.
      The fallback username, when case 1 does not apply, is taken from
      `SiteConfig().bot_username` — the model field default — not from a new string literal,
      so the command, the migration and `get_bot_username()`'s fallback cannot drift apart.

  - id: "D5 — The migration edit: full_clean() before save, and no schema_editor dereference."
    choice: >
      `seed_bot_username` fetches the row, assigns, calls `full_clean()`, and saves. The
      `schema_editor` argument is never dereferenced — the three existing tests pass `None`
      for it, and the function is driven against the **live** app registry
      (`django_apps`), not a historical one, so `full_clean()` resolves against the real
      model and its real validator.
    rationale: >
      The validator bypass is provable and the fix is one call. The three shipped tests will
      still pass: `test_bot` and `env_bot` match the regex, and the `"" → "bazuna_bot"`
      fallback matches it too. That last one is the non-obvious case and it is why
      `test_seed_falls_back_to_default` must be run rather than assumed.
      Two behavioural gaps are recorded in the migration's docstring rather than designed
      around, because they are properties of the `0003` contract and changing them would
      alter what an already-applied migration means: if the row is **missing** the filter
      matches nothing and the migration is inert; and a row that already holds the
      placeholder is **not** matched, so re-running repairs nothing. The second gap is
      exactly why G5 cannot be answered by the migration at all.

  - id: "D6 — The model is not touched; the regex duplication is closed by a test instead."
    choice: >
      `apps/core/models.py` is untouched. `test_admin_site_config.py` pins the field's
      `RegexValidator`, `max_length == 32`, the `help_text` and `list_display` membership,
      and a broken model is worse than a documented duplication. The helper therefore owns
      `BOT_USERNAME_PATTERN` for settings-side validation, and
      `test_bot_username_helper_agrees_with_model_validator` asserts the helper's pattern is
      the **same string** as the `RegexValidator`'s on the live model and that the two agree
      on a table of boundary values.
    rationale: >
      A settings module cannot import `apps.core.models` — the app registry is not ready
      when settings are being imported — so the duplication is structural, not accidental.
      The only remaining lever is a test that makes the two copies agree, and that is
      cheaper and safer than a lazy import. The migration's own `AddField` copy is
      historical and immovable by design; the docstring says so rather than pretending it
      is a third live copy.

  - id: "D7 — The CI-side condition is verified two-sided, and a local green run is not evidence."
    choice: >
      Four obligations, none of which is discharged by `.\Makefile.ps1 test` alone:
      1. **Structural** — the new settings-test module builds its subprocess environment by
         *allowlisting* the keys of `_prod_env_overrides()` and setting `BOT_USERNAME` from
         an explicit parameter that is deliberately **absent** from the allowlist. It
         therefore cannot observe `.env.test`, `os.environ`, or a developer's shell, and is
         green in both environments by construction rather than by luck.
      2. **Fixture** — `_prod_env_overrides` and `_prod_env` assign `BOT_USERNAME`
         explicitly, so the four tests that drive prod imports through them
         (`test_oneshot_flag_is_inert_under_a_valid_prod_environment`,
         `test_csrf_trusted_origins_accepted_in_production`, the Sentry/LOGGING/email tests
         in `test_prod_logging.py`) no longer depend on whether the key happens to be
         present in the ambient environment.
      3. **Empirical** — a **two-sided** demonstration in which `BOT_USERNAME` is removed
         from the local `.env.test` (gitignored, untracked, never regenerated by
         `Makefile.ps1`): the suite goes red with the fixture edits reverted, and stays
         green with them in place. Both outputs are recorded, and `.env.test` is restored and
         its `BOT_USERNAME` line re-read afterwards.
      4. **Deferred** — the first CI run of this block is part of its acceptance, not a
         follow-up. The hand-off must say so explicitly and must not imply the CI `test`
         job was observed if it was not.
    rationale: >
      The divergence is the finding, not a side effect of it. `.env.test` reaches the test
      container twice — once through `env_file:` and once through the
      `./.env.test:/app/src/.env:ro` bind-mount that `base.py`'s present-file branch reads —
      and the CI `test` job's environment is only `PYTHONPATH` with no `.env` on disk. A
      builder that seeds from `os.environ` therefore reports a green run in the container
      and a red run in CI, and **the local run is the one that cannot fail.** Obligation 3
      is the only way to see the CI condition without a CI run, and it must be done in both
      directions or it proves nothing: green-with-the-fix shows the coupling was closed, and
      red-without-the-fix shows the demonstration has teeth.

  - id: "D8 — Helper placement and the dev.py staleness corrections."
    choice: >
      The helper is a new module `src/backend/config/settings/secret_validation.py`,
      importing **only** the standard library and `django.core.exceptions`. The block's
      file surface lists `dev.py` targets `_BOT_TOKEN_PLACEHOLDER_RE` and the "Mirrors prod"
      comment; **neither exists** — BLOCK 2 removed the first and the only `Mirrors` string
      in the settings package is in `test.py`, which is BLOCK 9's scope. `dev.py` and
      `test.py` are therefore both marked `not_touched`, and `prod.py` becomes the helper's
      only settings-module consumer.
    rationale: >
      "Two locations" is the wrong number the moment this block lands: there is one helper.
      `base.py`'s `BOT_TOKEN` comment must name the helper, not two regexes, or the next
      reader goes looking for a second copy that has been deleted. Naming `test.py` here
      would put BLOCK 9's file in this block's diff and create a same-file collision with a
      later block.

# ─────────────────────────────────────────────────────────────────────────────
# Corrections to the block's notes above (the tree is the authority)
# ─────────────────────────────────────────────────────────────────────────────
corrections_to_block_notes:
  - >
    **Note 7 is stale and is reversed by D3.** After BLOCK 3 the dev one-shot services load
    `config.settings.oneshot`, not `config.settings.prod`, and every guard written inside
    `if not _SKIP_SECRET_VALIDATION:` is inert there. The premise "the dev half stops the
    bad value reaching the database because the dev one-shot services run the migration"
    no longer holds: the one-shots that run the migration are exactly the processes a
    settings-module guard cannot reach. The dev half's role is taken by the migration's
    `full_clean()`, which runs everywhere.
  - >
    **Note 9's "both locations" is one helper after this block.** `base.py`'s `BOT_TOKEN`
    comment names `config/settings/secret_validation.py` and the guard that consumes it.
  - >
    **The file surface's `dev.py` targets do not exist.** BLOCK 2 deleted
    `_BOT_TOKEN_PLACEHOLDER_RE`; there is no "Mirrors prod" comment in `dev.py`. The only
    `Mirrors` string in the settings package is in `test.py` (BLOCK 9). Strike both, or the
    Implementor edits `test.py` out of scope.
  - >
    **`test_docs_ci_parity.py` has nothing to do with management-command docs.** It asserts
    string parity across `ci.yml`, `ci-nightly.yml`, `pyproject.toml`,
    `docker/entrypoint-test.sh`, `Makefile` and `Makefile.ps1`. It is on the must-pass list
    because this block edits `ci.yml`, and for no other reason. **No command-registry test
    exists anywhere in the repository**, so the new repair command needs none and none is
    added.
  - >
    **The G5 file-surface line says the next migration number is `0005_*`. It is `0006_*`**
    — `0005_scheduler_daily_state.py` was added by phase 01. D4 rejects the migration
    entirely; the number is recorded so that any future reader who revives option (ii)
    re-checks the directory immediately before creating.
  - >
    **The consumer list in the Auditor's brief supersedes the report's.** `privacy_view` in
    `apps/core/views.py` is **not** the footer; `privacy.html` is the only cleartext
    `{{ bot_username }}` reader in the template tree. `apps/ads/views/listings.py` is
    inside `ad_detail` and its context value is read by no template. The login-issued
    context value in `apps/users/views/consent.py` is dead: the template uses the deep-link
    tag and a shipped test asserts `{{ bot_username }}` is absent. The only user-visible
    failure is `telegram_deep_link`, whose `href` is always `#` and which therefore
    disguises the breakage. Bot handlers are unaffected and the bot's own deep links are
    correct.

recorded_follow_ups:
  - >
    **`consolidating the subprocess env builders`.** This block does not add a fourth
    `_run_in_subprocess` — it imports the one from `test_prod_logging`. It does add one
    **allowlist-filtered** environment builder inside the new settings-test module, which
    is a deliberately different contract from `_prod_env_overrides` (scrubbed, not
    inherited) and not a copy. The count of prod-env builders therefore goes from two to
    three, and the §6 consolidation item is updated accordingly.
  - >
    **`_prod_env_overrides` remains `os.environ`-seeded.** Making it scrubbed would break
    its own purpose for `test_settings_secrets.py`, which needs to unset a key and observe
    the guard. The fix applied here is that the two keys this block makes required are
    assigned **explicitly**, which is the narrow, correct change.
  - >
    **`privacy.html`'s cleartext `{{ bot_username }}` reader.** `docs/01-spec/contact-us.md`
    records it as an open spec deviation (F-BB-002) with "a re-verification grep is
    recommended". This block does not change the template; the repair path fixes the value
    it prints, not the fact that it prints it in cleartext.

# ─────────────────────────────────────────────────────────────────────────────
# Binding constraints
# ─────────────────────────────────────────────────────────────────────────────
binding_constraints:
  - id: BC-1
    rule: >
      `config/settings/secret_validation.py` imports **nothing** from `base.py`, `prod.py`,
      `dev.py`, `test.py`, `oneshot.py` or `apps.*`. Only the standard library and
      `django.core.exceptions.ImproperlyConfigured`. `Validator` checks the import graph.
    why: >
      This is the constraint the report states and the reason `dev.py` duplicated the regex
      in the first place. A helper that imports `prod.py` creates a cycle the moment
      `prod.py` imports the helper, and drags prod's logging and Sentry configuration into
      every consumer.
  - id: BC-2
    rule: >
      Exactly one copy of `^<[^>]+>$` and exactly one live copy of the bot-username pattern
      exist outside the model and the historical migration. `prod.py`'s module-level
      `_SECRET_PLACEHOLDER_RE` is **removed** and replaced by a call into the helper; the
      name is not aliased or re-declared. `grep` for the literal must return the helper, the
      model, and `0003_add_bot_username.py` — and nothing else.
  - id: BC-3
    rule: >
      The new `BOT_USERNAME` guard is the **last** guard in `prod.py`, after the `REDIS_URL`
      block. It is not hoisted next to the `BOT_TOKEN` guard for readability.
    why: >
      `test_csrf_trusted_origins_required_in_production` asserts a **bare `ValueError`**
      naming `CSRF_TRUSTED_ORIGINS` when the origin is missing. Guards fire top to bottom,
      and under D1 an unset `BOT_USERNAME` raises `ImproperlyConfigured` — which is not a
      `ValueError`. Placing the new guard above the CSRF guard turns that shipped test red
      in the CI environment for a reason that has nothing to do with CSRF. Placement at the
      end preserves every existing per-guard failure surface, which is the contract
      `test_deploy_check_env_parity.py`'s two negative-control rows also rely on.
  - id: BC-4
    rule: >
      Every new `ImproperlyConfigured` and `ValueError` message is **value-free**: it names
      the variable, the failure mode and the remediation, and never interpolates the value.
      `logger` output follows the same rule.
    why: >
      Repository convention, and it keeps the CI log and gitleaks clean. Every existing
      `prod.py` message obeys it and BLOCK 4's parity test asserts on `result.stderr`
      *because* that contract holds.
  - id: BC-5
    rule: >
      No user-visible string is introduced. `ImproperlyConfigured` / `ValueError` /
      `ValidationError` messages and `logger` calls are operator diagnostics and are not
      translated, matching existing convention. The management command's `help` is English
      and untranslated, as all twelve existing commands' are. The i18n completeness gate
      must still pass.
  - id: BC-6
    rule: >
      The repair command uses `save()`. `QuerySet.update()`, `.bulk_update()` and raw SQL are
      all forbidden, and no explicit `invalidate_bot_username_cache()` call is added as a
      belt-and-braces measure.
    why: >
      `save()` is what obtains the `post_save` invalidation. A second, manual invalidation
      would be a second source of truth for a fact the signal already owns, and would
      hide the day someone changes the command back to `update()` and the manual call goes
      with it.
  - id: BC-7
    rule: >
      No new dependency, no new CI job, no `jobs.test.steps` edit, no new migration, no new
      management-command registry test, no change to `docker/Dockerfile`, any compose file,
      either Makefile, `src/telegram_bot/**`, or any template.
    rationale: >
      `ci.yml`'s diff for this block is exactly one added key in one env block. Everything
      else is Python, one enum member, and two doc paragraphs.
  - id: BC-8
    rule: >
      The working tree is dirty and the tree wins over this document. Stage explicit paths
      only (§1 hard rule). Never `git add -A`; the tree carries pre-existing `.ai/audit/**`
      deletions that must not be swept in. `docs/ops/docker-deployment.md` was modified at
      planning time by another activity — re-read it immediately before editing and do not
      clobber.
  - id: BC-9
    rule: >
      `.env.prod`, `.env.dev` and `.env.test` are never read for values, never quoted and
      never committed. `.env.test` is edited only for obligation D7-3, is restored
      immediately afterwards, and its `BOT_USERNAME` line is re-read to prove the restore.

# ─────────────────────────────────────────────────────────────────────────────
files:
  - path: src/backend/config/settings/secret_validation.py
    status: new
    targets:
      - type: module
        name: secret_validation
      - type: module_docstring
        name: "why this module exists, what it must never import (BC-1), and that BOT_USERNAME is a public handle rather than a secret"
      - type: constant
        name: BOT_USERNAME_PATTERN
      - type: private_constant
        name: _PLACEHOLDER_RE
      - type: function
        name: is_placeholder
      - type: function
        name: is_valid_bot_username
      - type: function
        name: validate_bot_username
    semantic_anchors:
      imports:
        - "re"
        - "typing.Final"
        - "django.core.exceptions.ImproperlyConfigured"
      must_not_contain:
        - "any import from config.settings.*"
        - "any import from apps.*"
        - "django.conf.settings"
        - "os.environ"
        - "gettext"
      public_surface: "is_placeholder, is_valid_bot_username, validate_bot_username, BOT_USERNAME_PATTERN — nothing else is exported; the compiled regex stays private"
      message_contract: "value-free (BC-4); one distinct message per failure mode, naming the variable"

  - path: src/backend/config/settings/prod.py
    targets:
      - type: private_constant
        name: _SECRET_PLACEHOLDER_RE
      - type: function
        name: _validate_production_secret
      - type: comment_block
        name: the secret-validation bypass comment block above the _PROD_SETTINGS_MODULE_SUFFIX constant
      - type: statement
        name: "the final if not _SKIP_SECRET_VALIDATION block guarding REDIS_URL"
    semantic_anchors:
      import_from:
        - "from .secret_validation import is_placeholder, validate_bot_username"
      remove:
        - "_SECRET_PLACEHOLDER_RE and its explanatory comment (replaced by the helper)"
        - "the `import re` that existed only to compile it — remove only if nothing else in the module uses `re`"
      insert_after:
        type: statement
        value: "the REDIS_URL guard block, which is the last statement in the module"
      do_not_edit:
        - "_SKIP_SECRET_VALIDATION and its computation"
        - "_is_production_settings_module"
        - "the DJANGO_ONESHOT-inert warning block"
        - "LOGGING, the Sentry init, and every non-guard settings assignment"
        - "the seven existing guards and their comment blocks"
        - "the unguarded ALLOWED_HOSTS check"

  - path: src/backend/config/settings/base.py
    targets:
      - type: comment
        name: "the comment above the BOT_TOKEN = env(...) read"
      - type: comment
        name: "the comment above the BOT_USERNAME = env(...) read"
    semantic_anchors:
      do_not_edit:
        - "ALLOWED_ENV_VARS (BOT_USERNAME is already a member; BLOCK 6 owns this group)"
        - "the .env missing-file branch and the read_env() skip condition — the two load-bearing branches BLOCK 3 named"
        - "every env() read and its default"

  - path: src/backend/config/settings/dev.py
    status: not_touched
    note: >
      D3 rejects the dev half. `_BOT_TOKEN_PLACEHOLDER_RE` and the "Mirrors prod" comment
      named in the block's file surface were removed by BLOCK 2 and do not exist. Importing
      the helper here for no reason would be a second consumer with no caller.

  - path: src/backend/config/settings/oneshot.py
    status: not_touched
    note: >
      D2/D3. An ungated guard here would break `test_oneshot_bypasses_secrets_for_oneshot_module`
      and `test_oneshot_module_still_requires_oneshot_flag`; a gated one would be inert. The
      bootstrap path is deliberately unguarded and `test_bot_username_guard_skipped_for_oneshot_bootstrap`
      pins that.

  - path: src/backend/config/settings/test.py
    status: not_touched
    note: "the only `Mirrors` string in the settings package; BLOCK 9's scope (D8)"

  - path: .github/workflows/ci.yml
    targets:
      - type: workflow_job
        name: deploy-check
    semantic_anchors:
      resolve_target: "jobs.deploy-check.env — the YAML mapping directly above the job's steps"
      do_not_edit:
        - "the other ten keys and their values"
        - "the contract comment block above the job (BLOCK 4 placed it and appended to it)"
        - "jobs.deploy-check.steps and the check --deploy invocation"
        - "jobs.test, jobs.build, jobs.security and every other job"

  - path: src/backend/config/settings/tests/test_prod_logging.py
    targets:
      - type: function
        name: _prod_env_overrides
      - type: function
        name: _run_in_subprocess
    semantic_anchors:
      do_not_edit:
        - "_run_in_subprocess — imported from by four modules, and BLOCK 4's BC-5 forbids editing it"
        - "the os.environ seeding of _prod_env_overrides"
        - "every existing default and every test function in the module"
      insert_into: >
        _prod_env_overrides, alongside the other required-variable defaults, following the
        file's existing `overrides.pop(...)` idiom.

  - path: src/backend/config/settings/tests/test_csrf_trusted_origins.py
    targets:
      - type: function
        name: _prod_env
    semantic_anchors:
      do_not_edit:
        - "_run_in_subprocess"
        - "the os.environ seeding and the CSRF_TRUSTED_ORIGINS exclusion"
        - "every test function in the module"
      note: >
        Not in the block's original test list and not in the coordinator's must-pass list,
        but it drives a prod import with `DJANGO_SETTINGS_MODULE=config.settings.prod`, does
        not set `BOT_USERNAME`, and asserts `returncode == 0` in
        `test_csrf_trusted_origins_accepted_in_production`. Under D1 it goes red in CI
        without this edit.

  - path: src/backend/apps/core/migrations/0003_add_bot_username.py
    targets:
      - type: function
        name: seed_bot_username
      - type: module_docstring
        name: "must record that editing an applied migration protects fresh databases only, and that the data-repair path is manage.py repair_bot_username"
    semantic_anchors:
      do_not_edit:
        - "the AddField operation and its RegexValidator"
        - "the dependencies tuple"
        - "reverse_code=migrations.RunPython.noop"
        - "the filter(pk=1, bot_username=\"bazuna_bot\") guard, and both gaps it implies (missing row; row already holding the placeholder)"

  - path: src/backend/apps/core/enums.py
    targets:
      - type: enum
        name: AdvisoryLockId
    semantic_anchors:
      insert_into: "the 1..12 member band, which is contiguous and whose next free value is 13"
      note: >
        AdvisoryLockId is an IntEnum, not a StrEnum. The band 100..111 is a separate
        bootstrap/service range and must not be joined. Re-read the enum immediately before
        editing: 13 is free at the time of writing, not guaranteed to be at execution time.

  - path: src/backend/apps/core/management/commands/repair_bot_username.py
    status: new
    targets:
      - type: module_docstring
        name: "what it repairs, the DB-wins-over-env contract, that save() is what invalidates the cache, and that the Django admin remains an equivalent manual path"
      - type: function
        name: add_arguments
      - type: class
        name: Command
    semantic_anchors:
      follow_the_convention_of:
        - "apps/core/management/commands/cleanup_login_tokens.py — module docstring, logger not print(), English untranslated help, transaction.atomic() + advisory_lock(), --dry-run on a mutating command"
      must_contain:
        - "logger = logging.getLogger(__name__)"
        - "transaction.atomic() wrapping the advisory_lock context"
        - "--dry-run reporting which of the four cases in D4 applies"
        - "instance.save() and never QuerySet.update() (BC-6)"
        - "the fallback username taken from SiteConfig().bot_username, not a literal (D4)"
      must_not_contain:
        - "gettext / gettext_lazy"
        - "any explicit invalidate_bot_username_cache() call"
        - "a new string literal for the default username"

  - path: src/backend/config/settings/tests/test_bot_username_validation.py
    status: new
    targets:
      - type: module_docstring
        name: "G4's decision, the required-non-empty surface, and why this module builds a scrubbed environment instead of using _prod_env_overrides directly"
      - type: constant
        name: _PROD_ENV_ALLOWLIST
      - type: constant
        name: _PROD_MODULE
      - type: constant
        name: _ONESHOT_MODULE
      - type: constant
        name: _DEFAULT_BOT_USERNAME
      - type: helper
        name: _prod_env
      - type: function
        name: test_bot_username_placeholder_rejected_in_production
      - type: function
        name: test_bot_username_rejects_empty_in_production
      - type: function
        name: test_bot_username_rejects_value_failing_model_regex_in_production
      - type: function
        name: test_bot_username_valid_value_accepted_in_production
      - type: function
        name: test_bot_username_guard_skipped_during_build
      - type: function
        name: test_bot_username_guard_skipped_for_oneshot_bootstrap
      - type: function
        name: test_secret_validation_placeholder_detector
      - type: function
        name: test_bot_username_helper_agrees_with_model_validator
    semantic_anchors:
      import_from:
        - "config.settings.tests.test_prod_logging import _run_in_subprocess (never a local subprocess.run)"
        - "config.settings.secret_validation import BOT_USERNAME_PATTERN, is_placeholder, is_valid_bot_username"
        - "apps.core.models import SiteConfig (for the drift test only)"
      markers: "pytestmark = [pytest.mark.unit, pytest.mark.settings] — the siblings' value"
      env_discipline: >
        `_prod_env` calls `_prod_env_overrides()` and then keeps only the keys in
        `_PROD_ENV_ALLOWLIST`, then sets BOT_USERNAME from an explicit parameter.
        `BOT_USERNAME` is deliberately NOT in the allowlist, so no ambient value — from
        `.env.test`, from `os.environ`, or from a developer's shell — can reach the
        subprocess. `PATH` and `HOME` are the only inherited keys, and `PYTHONPATH` is
        supplied by the shared helper.
      must_not_contain:
        - "a local subprocess.run"
        - "any string literal that looks like a credential"
        - "pytest.skip / skipif / xfail"

  - path: src/backend/apps/core/tests/test_repair_bot_username_command.py
    status: new
    targets:
      - type: module_docstring
        name: "why the cache assertion is the load-bearing one"
      - type: function
        name: test_repair_bot_username_corrects_invalid_row
      - type: function
        name: test_repair_bot_username_invalidates_cached_bot_username
      - type: function
        name: test_repair_bot_username_leaves_valid_row_untouched
      - type: function
        name: test_repair_bot_username_refuses_when_settings_value_is_invalid
      - type: function
        name: test_repair_bot_username_dry_run_changes_nothing
    semantic_anchors:
      markers: "pytestmark = [pytest.mark.django_db, pytest.mark.integration] — test_migration_seed_bot_username.py's value, because the cache is LocMem-backed under config.settings.test"
      import_from:
        - "apps.core.services.site_config import get_bot_username"
        - "apps.core.utils.cache import get_cached_bot_username, set_cached_bot_username"
        - "apps.core.models import SiteConfig"
      prime_the_cache_with: "set_cached_bot_username(<the invalid value>) before calling the command, so the assertion is not vacuous — assert the primed value is returned first, then run the command, then assert the new value is returned"

  - path: src/backend/apps/core/tests/test_migration_seed_bot_username.py
    targets:
      - type: function
        name: test_seed_populates_from_settings
      - type: function
        name: test_seed_does_not_overwrite_custom
      - type: function
        name: test_seed_falls_back_to_default
      - type: fixture
        name: seed_bot_username
    semantic_anchors:
      do_not_edit: >
        The three existing tests, the fixture, the module docstring and the `importlib`
        load pattern are unchanged. Exactly one test is appended, using the same fixture and
        the same `override_settings` idiom.

  - path: src/backend/apps/core/tests/test_admin_site_config.py
    status: not_touched
    note: "D6 — it pins the model field definition, which is why the model is not touched"
  - path: src/backend/apps/core/tests/test_site_config_bot_username.py
    status: not_touched
  - path: src/backend/apps/core/tests/test_migrate_locked.py
    status: not_touched
  - path: src/backend/apps/core/models.py
    status: not_touched
    note: "D6; `test_admin_site_config.py` pins the field"
  - path: src/backend/apps/core/services/site_config.py
    status: not_touched
    note: >
      The block's file surface says "only if the chosen repair path needs a cache
      invalidation call". D4/BC-6 make it unnecessary: `save()` triggers the existing
      `post_save` receiver, which already calls both `invalidate_site_config()` and
      `invalidate_bot_username_cache()`. No new service function is added.
  - path: src/backend/apps/core/signals.py
    status: not_touched
  - path: src/backend/apps/core/utils/cache.py
    status: not_touched
  - path: src/backend/apps/core/admin.py
    status: not_touched
    note: "option (iii) already works today: SiteConfig is registered and bot_username is an editable, validated form field"
  - path: src/backend/config/settings/tests/test_settings_secrets.py
    status: not_touched
    note: "the phase's most contended file; this block adds nothing to it"
  - path: src/backend/config/settings/tests/test_deploy_check_env_parity.py
    status: not_touched
    note: >
      BLOCK 4's module is the tripwire for C6. It must go red if `BOT_USERNAME` is added to
      the prod guard without being added to the env block, and green once both are in place.
      It is read, not edited.
  - path: src/backend/config/settings/tests/test_oneshot_settings.py
    status: not_touched
    note: "read: its test_django_build_flag_bypasses_all_prod_guards is the test that decides D2, and its test_oneshot_flag_is_inert_under_a_valid_prod_environment is one of the four that C4 un-couples from the ambient environment"
  - path: src/backend/config/settings/tests/test_settings_defaults.py
    status: not_touched
  - path: src/backend/tests/test_docs_ci_parity.py
    status: not_touched
  - path: src/backend/tests/test_compose_contract.py
    status: not_touched
  - path: src/backend/tests/test_compose_hardening.py
    status: not_touched
  - path: src/backend/apps/core/tests/test_ci_security.py
    status: not_touched
    note: "its _deploy_check_section() slice still isolates the job: the added key is inside the env mapping, above the steps"
  - path: src/backend/apps/core/tests/test_migrations.py
    status: not_touched
  - path: docker/Dockerfile
    status: not_touched
    note: "G2 closed in BLOCK 3; D2 keeps the builder stage working by gating rather than by touching the image"
  - path: docker-compose.yml
    status: not_touched
  - path: docker-compose.prod.yml
    status: not_touched
  - path: docker-compose.dev.override.yml
    status: not_touched
  - path: docker-compose.test.yml
    status: not_touched
  - path: Makefile
    status: not_touched
  - path: Makefile.ps1
    status: not_touched
  - path: src/telegram_bot
    status: not_touched
  - path: ".env.prod.example"
    status: not_touched
    note: >
      The shipped `BOT_USERNAME=<your-bot-username>` is the defect's trigger, not the
      defect. It stays, and the guard is what makes shipping it survivable. The docstring
      change the finding implies (telling the operator the value is required) belongs in
      `docs/ops/docker-deployment.md`, not in the example file.
  - path: ".env.dev.example"
    status: not_touched
    note: "D3 — dev is deliberately unguarded, so the dev example must keep working as-is"
  - path: ".ai/audit"
    status: not_touched
    note: "unmodifiable by mandate; the pre-existing tracked deletions there are not this block's"

  - path: docs/01-spec/contact-us.md
    status: edited
    targets:
      - type: section
        name: "Bot username centralization"
      - type: table_row
        name: "the table row describing the admin layer as the operator path"
    semantic_anchors:
      insert_into: >
        the "Bot username centralization" section, after the table, as a short
        "Repairing a placeholder username" paragraph naming `manage.py repair_bot_username`,
        its `--dry-run`, the Django-admin equivalent, and the one-hour cache caveat.
      do_not_edit:
        - "the layer table, the RegexValidator row, or the deep-link rendering section"
        - "the 'Known deviations' list"

  - path: docs/ops/docker-deployment.md
    status: edited
    targets:
      - type: section
        name: "the required production environment variables list"
    semantic_anchors:
      insert_into: >
        wherever the file enumerates required production env vars, add `BOT_USERNAME` and
        state that it must be a real Telegram handle matching the model's format — not the
        `<your-bot-username>` template value.
      coordination: >
        This file was modified at planning time by another activity. Re-read it immediately
        before editing, edit only the enumerated-variable list, and do not reformat or
        reorder anything else (BC-8).

# ─────────────────────────────────────────────────────────────────────────────
changes:

  # ── CFG-011 half. Lands first. ────────────────────────────────────────────
  - action: add_module
    id: change_add_helper
    path: src/backend/config/settings/secret_validation.py
    description: >
      The single home for placeholder detection and for the bot-username validity
      contract. Four public names and nothing else.

      `BOT_USERNAME_PATTERN` is a `Final[str]` holding `^[A-Za-z0-9_]{3,32}$`, byte-identical
      to the model's `RegexValidator` regex and to the one in migration `0003`. D6 explains
      why it cannot import the model's.

      `is_placeholder(value)` matches the compiled private `_PLACEHOLDER_RE` — the same
      `^<[^>]+>$` that `prod.py` compiled locally, moved here verbatim so the two
      descriptions of the same thing are now one.

      `is_valid_bot_username(value)` is the pure predicate: non-empty, not a placeholder,
      and matching `BOT_USERNAME_PATTERN`.

      `validate_bot_username(var_name, value)` is the raising wrapper the settings modules
      call, and it checks in a fixed order — empty, then placeholder, then regex — so the
      operator always gets the most actionable message. The empty case is a
      required-non-empty refusal (D1); the placeholder case names `.env.prod` and the
      template; the regex case states the required format. All three messages are
      value-free and name `var_name` (BC-4).

      The module docstring must state, in order: what the module is for; that it must
      never import from a settings module or from `apps.*` and why; that `BOT_USERNAME` is
      a **public Telegram handle and not a secret**, so the settings modules gate it inside
      their secret block for a single-mechanism reason rather than for secrecy; and that the
      pattern duplicates the model field's on purpose, with
      `test_bot_username_helper_agrees_with_model_validator` holding the two together.
    code_hint: |
      """Shared secret and bot-username validation for the settings modules.

      Single home for the ``^<[^>]+>$`` placeholder pattern and for the bot-username
      validity contract. Exists because the pattern was previously compiled in two
      settings modules and each copy could drift from the other.

      Import constraints (BC-1): this module must never import from another settings
      module or from ``apps.*``. ``prod.py`` imports it, so a reverse import is a cycle,
      and the app registry is not ready while settings are being imported.

      Note on classification: ``BOT_USERNAME`` is a public Telegram handle, not a secret.
      The defect is correctness, not disclosure. Settings modules validate it inside their
      existing secret-validation block because that block is the project's single
      "this variable must be real when we serve traffic" mechanism — not because the value
      is confidential. Widening the block is therefore a deliberate decision, not a
      convenience.

      ``BOT_USERNAME_PATTERN`` duplicates ``SiteConfig.bot_username``'s ``RegexValidator``
      on purpose: settings cannot import the model. The two are held together by
      ``config/settings/tests/test_bot_username_validation.py::
      test_bot_username_helper_agrees_with_model_validator``.
      """

      import re
      from typing import Final

      from django.core.exceptions import ImproperlyConfigured

      # Byte-identical to SiteConfig.bot_username's RegexValidator (see module docstring).
      BOT_USERNAME_PATTERN: Final[str] = r"^[A-Za-z0-9_]{3,32}$"

      # Matches values shipped as templates in .env.*.example files, e.g.
      # <generate-with-django-secret-key-generator>, <your-bot-token-from-botfather>
      _PLACEHOLDER_RE: Final[re.Pattern[str]] = re.compile(r"^<[^>]+>$")


      def is_placeholder(value: str) -> bool:
          """Return True when the value is a shipped ``<...>`` template placeholder."""
          return _PLACEHOLDER_RE.match(value) is not None


      def is_valid_bot_username(value: str) -> bool:
          """Return True when the value is usable as a Telegram bot username.

          Rejects the empty string, a shipped placeholder, and anything outside
          ``BOT_USERNAME_PATTERN``. This is the predicate the settings guard and the
          repair command both use, so "what the guard accepts" and "what the model
          accepts" cannot diverge.
          """
          if not value:
              return False
          if is_placeholder(value):
              return False
          return re.match(BOT_USERNAME_PATTERN, value) is not None


      def validate_bot_username(var_name: str, value: str) -> None:
          """Fail fast when a bot username is missing, a template, or malformed.

          Checks in the order that produces the most actionable message first. Raises
          ImproperlyConfigured with a value-free message naming the variable and the
          remediation; never logs or echoes the value.
          """
          if not value:
              raise ImproperlyConfigured(
                  f"{var_name} must be set and non-empty in production. "
                  "Provide the real Telegram bot handle (without the @ prefix) via the "
                  ".env.prod runtime file."
              )
          if is_placeholder(value):
              raise ImproperlyConfigured(
                  f"{var_name} appears to be a placeholder value from a .env template. "
                  "Replace it with the real value in .env.prod."
              )
          if re.match(BOT_USERNAME_PATTERN, value) is None:
              raise ImproperlyConfigured(
                  f"{var_name} must be 3-32 characters, alphanumeric and underscore "
                  "only, because it is persisted into SiteConfig.bot_username. Provide "
                  "the real Telegram bot handle (without the @ prefix) in .env.prod."
              )

  - action: update_code
    id: change_prod_consumes_helper
    path: src/backend/config/settings/prod.py
    description: >
      CFG-011's first half, on the production side. Delete the module-level
      `_SECRET_PLACEHOLDER_RE` and its two-line explanatory comment; delete `import re` if
      and only if nothing else in the module uses it. Import `is_placeholder` from the new
      helper and use it inside `_validate_production_secret` in place of the compiled
      pattern.

      The guard's own docstring is updated in the same change: it currently says the
      function rejects values that "match shipped placeholder templates" by way of a
      regex local to the module, and the docstring must now name where the check lives.
      Do not otherwise touch `_validate_production_secret` — its dev-only-dummy branch, its
      `DJANGO_SECRET_KEY` length branch, its message wording and its value-free contract
      are all pinned by shipped tests, and `test_deploy_check_env_parity.py` asserts on
      `result.stderr` because that contract holds.
    code_hint: |
      # before
      import re
      from .base import *  # noqa: F403, F401

      # Matches values shipped as templates in .env.*.example files, e.g.
      # <generate-with-django-secret-key-generator>, <your-bot-token-from-botfather>
      _SECRET_PLACEHOLDER_RE = re.compile(r"^<[^>]+>$")

      # after
      from .base import *  # noqa: F403, F401
      from .secret_validation import is_placeholder, validate_bot_username


      def _validate_production_secret(var_name: str, value: str) -> None:
          """Fail-fast validation for production secrets.

          Rejects values that look like dev-only dummies or match shipped placeholder
          templates — the placeholder pattern lives in secret_validation, the single
          home shared by every settings module — or (for DJANGO_SECRET_KEY) are too
          short.

          Raises ImproperlyConfigured with a value-free message naming the env var
          and remediation guidance. Does NOT log the value itself.
          """
          if "dev-only-dummy" in value:
              raise ImproperlyConfigured(
                  f"{var_name} appears to use a dev-only dummy value. "
                  "Provide a real value via the .env.prod runtime file."
              )
          if is_placeholder(value):
              raise ImproperlyConfigured(
                  f"{var_name} appears to be a placeholder value from a .env template. "
                  "Replace it with the real value in .env.prod."
              )
          ...

  - action: update_comment
    id: change_base_bot_token_comment
    path: src/backend/config/settings/base.py
    description: >
      CFG-011's document half. `base.py`'s comment above the `BOT_TOKEN = env(...)` read
      currently says "validated via Env schema", which names the right container and the
      wrong mechanism: the `Env(...)` entry above it provides a **cast and a default, not
      validation**, and no schema object exists anywhere in the repository.

      The replacement names the actual mechanism and its single home: the shared helper
      `config/settings/secret_validation.py`, consumed by the guard in `config/settings/prod.py`.
      It must say "the shared helper" and name the guard, **not** "two locations" — after
      this block there is one helper, and telling the next reader to look for a second copy
      sends them looking for code that BLOCK 2 deleted.

      The `BOT_USERNAME` comment above its own `env()` read gains two sentences: the value
      is required and non-empty in production (D1), and it is a **seed** consumed once by
      migration `0003` — after that the database is the source of truth, which is the fact
      that makes a production env edit alone insufficient to fix a bad row.

      `ALLOWED_ENV_VARS` already contains `BOT_USERNAME`; do not touch that group (BLOCK 6
      owns it), and do not touch either `.env` branch in this module.
    code_hint: |
      # before
      # Telegram bot token (required for bot process, validated via Env schema)
      # Allow empty string for development when bot is not needed
      BOT_TOKEN = env("BOT_TOKEN", default="")

      # after
      # Telegram bot token (required for bot process). The env(...) entry above declares
      # a cast and a default, not a schema: the actual placeholder/dummy validation lives
      # in config/settings/secret_validation.py and is applied by the guard in
      # config/settings/prod.py. Allow empty string for development when bot is not
      # needed; production requires it.
      BOT_TOKEN = env("BOT_TOKEN", default="")

      # Telegram Bot username for contact deep-links
      # Format: without @ prefix, e.g., "MyBot" not "@MyBot"
      # Required and non-empty in production. This is a SEED value: migration
      # 0003_add_bot_username copies it into SiteConfig.bot_username once, and from then
      # on the database is the source of truth (get_bot_username() reads the model, not
      # this setting), so changing it later does not change a deployed site. Use
      # `manage.py repair_bot_username` or the Django admin to correct a stored value.
      BOT_USERNAME = env("BOT_USERNAME", default="")

  # ── G4's coupling. Lands before the guard, so the guard is a no-op on arrival. ──
  - action: update_workflow
    id: change_ci_deploy_check_bot_username
    path: .github/workflows/ci.yml
    description: >
      Add `BOT_USERNAME` to `jobs.deploy-check.env`. This is BLOCK 4's D9 forward
      constraint coming due: the parity test that landed in `4fd8bd0` drives a
      `config.settings.prod` import with exactly this block, so the moment the guard exists
      the `test` job **and** the `deploy-check` job both go red unless this key is present.
      Both going red is the gate working; this key is the answer.

      The value must be non-empty (the parity test asserts every value is), must match
      `^[A-Za-z0-9_]{3,32}$` (the guard checks it), and must be obviously non-credential.
      Underscores rather than hyphens, unlike the neighbouring `ci-test-bot-token`, because
      the username format does not permit them — the fixture has to be realistic or the
      gate is not exercising the path it claims to. `ci_test_bot` satisfies all three and
      is not a finding under `.gitleaks.toml`'s allowlists (which match
      `test-secret-key-for-testing-only`, `test-bot-token-for-testing` and
      `test-admin-password`, none of which a public handle resembles).

      Nothing else in the file changes: not the other ten keys, not the contract comment
      BLOCK 4 appended, not the steps, not another job.
    code_hint: |
      # jobs.deploy-check.env — one key added, in the Telegram group of the block
          DJANGO_SETTINGS_MODULE: config.settings.prod
          DJANGO_SECRET_KEY: "ci-deploy-check-secret-key-not-for-production-use-1234567890"
          BOT_TOKEN: ci-test-bot-token
          # Underscores: a real Telegram handle matches ^[A-Za-z0-9_]{3,32}$, and this
          # guard now requires BOT_USERNAME, so the fixture must be realistic.
          BOT_USERNAME: ci_test_bot
          GOOGLE_TRANSLATE_API_KEY: ci-test-translate-key

  - action: update_test_helper
    id: change_prod_env_overrides_bot_username
    path: src/backend/config/settings/tests/test_prod_logging.py
    description: >
      Add `BOT_USERNAME` to `_prod_env_overrides`, following the file's existing
      `overrides.pop(...)` idiom and sitting with the other required-variable defaults.

      This is not cosmetic. `_prod_env_overrides` seeds from `os.environ` and does not set
      the key, so today it resolves to `test-bot` inside the Docker test container (from
      `.env.test` through both `env_file:` and the `src/.env` bind-mount) and to `""` in
      the CI `test` job. Under D1 that is the difference between four green tests and four
      red ones. Assigning it explicitly makes the builder deterministic and **removes** a
      divergence rather than adding one.

      Callers that need a different value pass `BOT_USERNAME=...` and the `overrides.pop`
      idiom handles it, including the empty string.

      `_run_in_subprocess` is **not** touched (BC-1 of BLOCK 4 forbids it and four modules
      import it), and no test function in the module changes.
    code_hint: |
          env["BOT_TOKEN"] = overrides.pop("BOT_TOKEN", "test-bot-token-for-testing-only")
          # Must be explicit: without it the builder inherits whatever the ambient
          # environment supplies, which differs between the Docker test container
          # (.env.test) and the CI test job (no .env). See BLOCK 5 decision D1.
          env["BOT_USERNAME"] = overrides.pop("BOT_USERNAME", "test_bot_for_testing_only")

  - action: update_test_helper
    id: change_prod_env_bot_username
    path: src/backend/config/settings/tests/test_csrf_trusted_origins.py
    description: >
      The same one-line addition to `_prod_env`, for the same reason. This module is not in
      the block's original test list and was not named in the coordinator's must-pass list,
      but it drives a `config.settings.prod` import, does not set `BOT_USERNAME`, and
      asserts `returncode == 0` in `test_csrf_trusted_origins_accepted_in_production`. It
      goes red in CI without this edit, for a reason that has nothing to do with CSRF.

      Leave `_run_in_subprocess`, the `os.environ` seeding, the `CSRF_TRUSTED_ORIGINS`
      exclusion and every test function untouched.
    code_hint: |
          env["BOT_TOKEN"] = overrides.pop("BOT_TOKEN", "test-bot-token-for-testing-only")
          # Explicit for the same reason as test_prod_logging._prod_env_overrides: the
          # ambient environment differs between the Docker test container and CI.
          env["BOT_USERNAME"] = overrides.pop("BOT_USERNAME", "test_bot_for_testing_only")

  # ── CFG-005's guard. ───────────────────────────────────────────────────────
  - action: add_code
    id: change_prod_bot_username_guard
    path: src/backend/config/settings/prod.py
    description: >
      The eighth gated guard, appended as the **last** statement in the module (BC-3). It
      calls `validate_bot_username("BOT_USERNAME", BOT_USERNAME)`, which covers all three
      rejection modes in the right order.

      The comment above it states, in this order: what the guard is for (a persisted
      handle, not a secret — D2); that it is written inside the secret-validation block
      because that block is the project's single "must be real when serving traffic"
      mechanism, **not** because the value is confidential, and that widening the block is
      therefore deliberate; that it is skipped under `DJANGO_BUILD=1` for the Docker image
      builder and under the bootstrap module for the dev one-shots, and that the
      `full_clean()` in migration `0003` — not this guard — is what protects the database
      in the bootstrap path (D3); and that a correct `.env.prod` value does not repair an
      already-seeded row, because the database is the source of truth after `0003`.

      The bypass comment block above `_PROD_SETTINGS_MODULE_SUFFIX` changes in exactly one
      place: "The seven secret guards below" becomes "The eight secret guards below". That
      block is the primary documentation of the whole bypass mechanism and BLOCK 3 rewrote
      it one commit ago; do not restate it, do not reorder it, and do not "improve" its
      wording.
    code_hint: |
      # Fail fast: BOT_USERNAME is required in production. It is a public Telegram
      # handle rather than a secret, but it is persisted into SiteConfig.bot_username by
      # migration 0003 and read back from the database, so a template or malformed value
      # produces dead t.me/ deep links site-wide — invisibly, because the
      # telegram_deep_link template tag base64-encodes it behind href="#".
      #
      # It lives inside the secret-validation block because that block is the project's
      # single "this variable must be real when we serve traffic" mechanism. Widening the
      # block to cover a non-secret value is a deliberate choice, made here; it is not
      # justified by confidentiality.
      #
      # Skipped during the Docker image build (DJANGO_BUILD=1), which runs collectstatic
      # under this module with no .env at all, and under config.settings.oneshot, which is
      # what the dev bootstrap one-shots load. In that bootstrap path the guard cannot
      # help: migration 0003's full_clean() is what stops a bad value reaching the
      # database there.
      #
      # A correct value in .env.prod does NOT repair a row already seeded with a
      # placeholder — the database is the source of truth after 0003. Run
      # `manage.py repair_bot_username`, or edit SiteConfig in the Django admin.
      if not _SKIP_SECRET_VALIDATION:
          validate_bot_username("BOT_USERNAME", BOT_USERNAME)  # noqa: F405

  # ── CFG-005's migration half. ─────────────────────────────────────────────
  - action: update_code
    id: change_migration_full_clean
    path: src/backend/apps/core/migrations/0003_add_bot_username.py
    description: >
      Close the provable validator bypass. Fetch the row, assign the resolved value, call
      `full_clean()`, then `save()`.

      `schema_editor` is never dereferenced — the three shipped tests pass `None` for it,
      and the function is driven against the live app registry, so `full_clean()` resolves
      against the real model and its real validator. The function signature is unchanged.

      The `filter(pk=1, bot_username="bazuna_bot")` guard is **kept**: it is what stops the
      migration overwriting an admin-edited value, and the existing
      `test_seed_does_not_overwrite_custom` pins it.

      The module docstring gains, in this order: a statement that editing an applied
      migration protects **fresh databases only**; the two behavioural gaps the filter
      implies — if the row is missing the filter matches nothing, and a row that already
      holds the placeholder is not matched, so a re-run repairs nothing; the consequence,
      which is that **this migration cannot be the data-repair path** and
      `manage.py repair_bot_username` is; and a note that switching `update()` to `save()`
      introduces a `post_save`-triggered cache invalidation into a migration whose
      `reverse_code` is `noop`, which is correct — a migration-time cache invalidation is
      harmless and, for a one-shot bootstrap, useful.
    code_hint: |
      def seed_bot_username(apps, schema_editor):
          """Seed SiteConfig.bot_username from settings, validating before writing.

          `schema_editor` is accepted for the RunPython contract and never used.

          This migration protects FRESH databases only. It will not re-run on an applied
          deployment, and even a forced re-run is inert in the two cases that matter:
          if the singleton row does not exist the filter matches nothing, and a row that
          already holds the placeholder is not matched either. Repairing an already-seeded
          deployment is `manage.py repair_bot_username`'s job, not this migration's.
          """
          SiteConfig = apps.get_model("core", "SiteConfig")

          from django.conf import settings as dj_settings

          bot_username = getattr(dj_settings, "BOT_USERNAME", "") or "bazuna_bot"

          # Only seed rows that are still at the factory default — never
          # overwrite an admin-edited value on re-run (migration-workflow.md:285).
          config = SiteConfig.objects.filter(
              pk=1, bot_username="bazuna_bot"
          ).first()
          if config is None:
              return
          config.bot_username = bot_username
          # update() bypasses full_clean(), which is how a template value
          # (BOT_USERNAME=<your-bot-username>) was being persisted into a field whose
          # own RegexValidator rejects it. save() rather than update() also fires
          # post_save, so the bot-username cache is invalidated — correct here even
          # though reverse_code is a noop.
          config.full_clean()
          config.save()

  # ── G5's repair path. ─────────────────────────────────────────────────────
  - action: update_enum
    id: change_advisory_lock_id
    path: src/backend/apps/core/enums.py
    description: >
      Add `REPAIR_BOT_USERNAME = 13` to `AdvisoryLockId`, in the contiguous `1..12` band
      alongside the other scheduled-job locks and **not** in the `100..111` bootstrap
      service range. `AdvisoryLockId` is an `IntEnum`.

      Re-read the enum immediately before editing. `13` is free at the time of writing;
      a later phase may have taken it, and a duplicate `IntEnum` member is an alias that
      silently makes two commands share one lock. If `13` is taken, take the next free
      value in the band and say so in the commit message.
    code_hint: |
      class AdvisoryLockId(IntEnum):
          """PostgreSQL advisory lock IDs for idempotent scheduled jobs."""

          ARCHIVE_SWEEP = 1
          ...
          RECOMPUTE_NORMALIZED_PRICES = 12
          REPAIR_BOT_USERNAME = 13
          SEED = 110

  - action: add_module
    id: change_repair_command
    path: src/backend/apps/core/management/commands/repair_bot_username.py
    description: >
      The chosen G5 repair path (D4). Follows `cleanup_login_tokens.py`'s shape exactly:
      module docstring, `logger = logging.getLogger(__name__)` and no `print()`,
      `class Command(BaseCommand)`, English untranslated `help`, `add_arguments` with
      `--dry-run`, and `transaction.atomic()` wrapping `advisory_lock(...)`.

      The four cases in D4, in that order. Case 1 exits **non-zero** and changes nothing —
      a non-zero exit is correct because the operator asked for a repair and the inputs
      cannot produce one; silently succeeding is the failure mode this block exists to
      remove. Cases 2 and 3 exit 0. `--dry-run` reports which case applies and changes
      nothing in every case.

      Use `SiteConfig.get_singleton()`, not `filter(pk=1).first()`: it is `get_or_create(pk=1)`,
      so a missing row is created at the field default — which is valid — and there is no
      missing-row branch to design, log or test.

      The fallback username is `SiteConfig().bot_username`, the field default, not a
      string literal. The migration's own `"bazuna_bot"` literal is left alone because
      three shipped tests pin it; the command must not add a **fourth** copy of the value.

      The docstring must state: the DB wins over env by design, so this repairs a
      demonstrably-invalid stored value and never a valid one; `save()` is what triggers
      the `post_save` cache invalidation, and `update()` would leave the old value cached
      for `SITE_CONFIG_CACHE_TTL`; and the Django admin is an equivalent manual path
      because `bot_username` is already an editable, validated admin form field.
    code_hint: |
      """
      Repair an invalid SiteConfig.bot_username from the BOT_USERNAME setting.

      Why this exists: migration 0003 seeded the singleton from settings.BOT_USERNAME via
      QuerySet.update(), which bypasses full_clean(), so a deployment that shipped the
      .env template value persisted "<your-bot-username>" into a field whose own
      RegexValidator rejects it. The database is the source of truth after that migration
      (get_bot_username() reads the model, not the setting), so correcting .env.prod alone
      changes nothing on a deployed site.

      What it does, and deliberately does not do:
        - It repairs the stored value ONLY when that value fails the model's validator.
          A valid value — including one an operator set through the Django admin — is
          never overwritten. The admin is the operator of record for this field.
        - It refuses (non-zero exit) when the setting it would copy from is itself empty
          or malformed, rather than substituting the model default. Doing the latter would
          manufacture the same silent dead-link this command exists to repair.
        - It uses instance.save(), not QuerySet.update(). save() fires the post_save
          receiver in apps.core.signals, which invalidates both the site-config and the
          bot-username cache keys. update() emits no signal and the stale value would
          survive in the cache for SITE_CONFIG_CACHE_TTL (1 hour) — the most likely
          "the fix is broken" report this command will generate.
        - It is idempotent: a second run finds a valid value and does nothing.
        - It is safe to run concurrently: an advisory lock plus transaction.atomic().

      Equivalent manual path: SiteConfig is registered in the Django admin and
      bot_username is an editable, validated form field, so an operator who knows their
      handle can simply edit the row. See docs/01-spec/contact-us.md.
      """

      import logging

      from django.conf import settings
      from django.core.management.base import BaseCommand
      from django.db import transaction

      from apps.core.enums import AdvisoryLockId
      from apps.core.models import SiteConfig
      from apps.core.utils.advisory_lock import advisory_lock
      from config.settings.secret_validation import is_valid_bot_username

      logger = logging.getLogger(__name__)


      class Command(BaseCommand):
          """Repair an invalid SiteConfig.bot_username from the BOT_USERNAME setting."""

          help = (
              "Re-sync SiteConfig.bot_username from BOT_USERNAME when the stored value "
              "fails the model validator; never overwrites a valid value"
          )

          def add_arguments(self, parser) -> None:
              parser.add_argument(
                  "--dry-run",
                  action="store_true",
                  dest="dry_run",
                  default=False,
                  help="Report what would change without writing anything",
              )

          def handle(self, *args, **options) -> None:
              dry_run: bool = options["dry_run"]
              source: str = getattr(settings, "BOT_USERNAME", "") or ""

              if not is_valid_bot_username(source):
                  # Case 1: the source is unusable. Refuse rather than substitute the
                  # model default — that would reproduce the silent dead link.
                  logger.error(
                      "Cannot repair SiteConfig.bot_username: the BOT_USERNAME setting is "
                      "missing, a template placeholder, or malformed. Set the real "
                      "Telegram handle (no @ prefix) in the .env.prod runtime file, or "
                      "edit the row in the Django admin, then re-run. The stored value "
                      "was left unchanged."
                  )
                  return

              with transaction.atomic():
                  with advisory_lock(AdvisoryLockId.REPAIR_BOT_USERNAME):
                      config = SiteConfig.get_singleton()

                      if is_valid_bot_username(config.bot_username):
                          # Case 2: nothing to do. A correct admin-edited value wins.
                          logger.info(
                              "SiteConfig.bot_username is already valid; nothing to repair."
                          )
                          return

                      logger.warning(
                          "SiteConfig.bot_username does not satisfy the model validator; "
                          "repairing it from the BOT_USERNAME setting."
                      )
                      if dry_run:
                          logger.info(
                              "DRY RUN: would repair SiteConfig.bot_username and "
                              "invalidate the bot-username cache"
                          )
                          return

                      config.bot_username = source
                      config.full_clean()
                      config.save()   # fires post_save -> invalidates both cache keys
                      logger.info(
                          "Repaired SiteConfig.bot_username from the BOT_USERNAME "
                          "setting; the bot-username cache was invalidated."
                      )

  # ── Tests. ────────────────────────────────────────────────────────────────
  - action: add_test_module
    id: change_settings_tests
    path: src/backend/config/settings/tests/test_bot_username_validation.py
    description: >
      A new module, not an addition to `test_settings_secrets.py`, and the reason is
      structural rather than stylistic: this is the only settings-test module whose
      environment must **not** be seeded from `os.environ`, and putting that contract in
      the same file as `_prod_env_overrides`' opposite contract invites the exact
      copy-paste that produced the environment divergence this block must not ship.
      `test_settings_secrets.py` is also the phase's most contended file (BLOCK 2
      retargets tests in it, BLOCK 3 rewrites one, BLOCK 7 adds one).

      `_prod_env` calls `_prod_env_overrides()` and then keeps **only** the keys in
      `_PROD_ENV_ALLOWLIST`, and sets `BOT_USERNAME` from an explicit keyword parameter
      whose default is a valid value. `BOT_USERNAME` is deliberately absent from the
      allowlist, so no ambient value from `.env.test`, `os.environ` or a developer's shell
      can reach the subprocess. `PATH` and `HOME` are the only inherited keys;
      `PYTHONPATH` comes from the shared `_run_in_subprocess`. This is D7-1: the module is
      green in both environments by construction, not by luck.

      Reusing `_prod_env_overrides()` for the **values** and replacing its **base** with an
      allowlist is deliberate and is documented in the function's docstring. It is a
      different contract, not a copy, and it is not a third copy of anything.

      The module docstring states: G4's decision and the required-non-empty surface; the
      DB-wins-over-env fact that makes a stored value unfixable by an env edit; why the
      environment is scrubbed rather than inherited; and that the assertion order in
      `validate_bot_username` is part of the contract because the empty case and the
      placeholder case produce different, differently-actionable messages.

      The eight test functions are specified in `tests.must_be_added` below. Five drive a
      subprocess; one is a pure-function table; one is a build-skip; one is a bootstrap-skip;
      one is the anti-drift test against the live model.
    code_hint: |
      _PROD_MODULE = "config.settings.prod"
      _ONESHOT_MODULE = "config.settings.oneshot"
      _DEFAULT_BOT_USERNAME = "test_bot_for_testing_only"

      # The only keys a subprocess is allowed to inherit. BOT_USERNAME is deliberately
      # ABSENT: it is always set from an explicit parameter, so no value from .env.test,
      # os.environ or a developer's shell can reach the assertion. This is what makes the
      # module behave identically in the Docker test container and in the CI test job.
      _PROD_ENV_ALLOWLIST = frozenset({
          "DJANGO_SETTINGS_MODULE", "DEBUG", "DJANGO_SECRET_KEY", "BOT_TOKEN",
          "GOOGLE_TRANSLATE_API_KEY", "SITE_URL", "ALLOWED_HOSTS",
          "CSRF_TRUSTED_ORIGINS", "REDIS_URL", "EMAIL_HOST", "EMAIL_PORT",
          "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD", "EMAIL_TIMEOUT",
          "EMAIL_BACKEND", "DEFAULT_FROM_EMAIL", "SUPPORT_NOTIFICATION_RECIPIENTS",
          "SENTRY_DSN", "PATH", "HOME",
      })


      def _prod_env(*, bot_username: str = _DEFAULT_BOT_USERNAME) -> dict[str, str]:
          """A production environment with an explicit BOT_USERNAME and nothing inherited.

          Values come from _prod_env_overrides() (the shared source of truth for what a
          valid production environment looks like); the *base* does not. The result is
          filtered to _PROD_ENV_ALLOWLIST, so an ambient DJANGO_BUILD or DJANGO_ONESHOT
          or a developer's shell cannot decide the outcome. This is a different contract
          from _prod_env_overrides, not a copy of it.
          """
          env = {
              key: value
              for key, value in _prod_env_overrides().items()
              if key in _PROD_ENV_ALLOWLIST
          }
          env["BOT_USERNAME"] = bot_username
          return env

  - action: add_test
    id: change_migration_refuses_invalid
    path: src/backend/apps/core/tests/test_migration_seed_bot_username.py
    description: >
      Append exactly one test. The three existing tests, the `seed_bot_username` fixture,
      the module docstring and the `importlib` load pattern are **unchanged**.

      The new test uses the same fixture and the same `@override_settings` idiom, drives
      `seed_bot_username(django_apps, None)` with a value that fails the validator, and
      asserts both that it raises `django.core.exceptions.ValidationError` and that the
      row is **unchanged** — the second assertion is the one that matters, because a
      migration that raised after writing would leave the corrupt value in place.

      Drive it against the live app registry exactly as the existing three do, and with
      `schema_editor=None`, which is the condition the new migration code must tolerate.
    code_hint: |
      @override_settings(BOT_USERNAME="<your-bot-username>")
      def test_seed_refuses_value_failing_validator(seed_bot_username) -> None:
          """The seed refuses to persist a value the model's own validator rejects.

          This is the provable bypass from CFG-005: the migration declared a
          RegexValidator and then wrote through QuerySet.update(), which never calls
          full_clean(). The row must be left untouched when the value is rejected.
          """
          config = SiteConfig.get_singleton()
          assert config.bot_username == "bazuna_bot"

          with pytest.raises(ValidationError):
              seed_bot_username(django_apps, None)

          config.refresh_from_db()
          assert config.bot_username == "bazuna_bot"

  - action: add_test_module
    id: change_repair_command_tests
    path: src/backend/apps/core/tests/test_repair_bot_username_command.py
    description: >
      Five tests over the command, using `call_command` with the canonical
      `SiteConfig.get_singleton()` fixture from `conftest.py`.

      The load-bearing one is `test_repair_bot_username_invalidates_cached_bot_username`,
      and the way to write it matters: **prime the cache first** with the invalid value via
      `set_cached_bot_username(...)`, assert that `get_bot_username()` returns the primed
      value (so the test cannot pass vacuously because nothing was cached), run the command,
      then assert `get_bot_username()` returns the repaired value. A test that only checks
      the database row passes identically whether the command uses `save()` or `update()`,
      and `update()` is precisely the defect this block's most likely bug report describes.

      The other four: the row is corrected; a valid row (including one an operator set
      through the admin) is left untouched and the command is a no-op; the command refuses
      with a non-zero exit and leaves the row unchanged when the setting is empty or a
      placeholder; and `--dry-run` changes nothing in each of those cases.
    code_hint: |
      _INVALID_USERNAME = "<your-bot-username>"
      _REPAIRED_USERNAME = "test_bot_for_testing_only"


      @pytest.mark.django_db
      def test_repair_bot_username_invalidates_cached_bot_username() -> None:
          """A repair is visible immediately, not after the 1-hour cache TTL.

          QuerySet.update() emits no post_save, so a repair written that way leaves the
          old value cached. Prime the cache first so this test cannot pass because
          nothing was cached in the first place.
          """
          config = SiteConfig.get_singleton()
          config.bot_username = _INVALID_USERNAME
          config.save()
          set_cached_bot_username(_INVALID_USERNAME)
          assert get_bot_username() == _INVALID_USERNAME

          with override_settings(BOT_USERNAME=_REPAIRED_USERNAME):
              call_command("repair_bot_username")

          config.refresh_from_db()
          assert config.bot_username == _REPAIRED_USERNAME
          assert get_bot_username() == _REPAIRED_USERNAME

  - action: update_doc
    id: change_contact_us_doc
    path: docs/01-spec/contact-us.md
    description: >
      Add a short "Repairing a placeholder username" subsection after the bot-username
      centralization table. It names `manage.py repair_bot_username`, `--dry-run`, the
      one-hour cache and the requirement that the command invalidates it, the Django-admin
      equivalent, and the ordering — fix `.env.prod` **first**, then run the command —
      which is the one thing an operator gets wrong.

      It also corrects the one row of the existing table that this block makes stale: the
      "Seed migration" row's parenthetical "(seed value only)" is now enforced rather than
      advisory, because the migration refuses to write a value its validator rejects.

      Do not touch the deep-link rendering section, the layer table's other rows, or the
      "Known deviations" list.
    code_hint: |
      ### Repairing a placeholder username

      If `.env.prod` still carried the `<your-bot-username>` template value when migration
      `0003_add_bot_username` ran, the singleton holds a value its own validator rejects
      and every `t.me/` deep link on the site is dead. The value is base64-encoded behind
      `href="#"`, so nothing on the rendered page shows it.

      The database is the source of truth after `0003`, so correcting `.env.prod` alone
      changes nothing. Repair the stored value instead — fix the env **first**, then run
      the command:

          # 1. Set BOT_USERNAME in .env.prod to the real handle (no @ prefix).
          # 2. Preview:
          manage.py repair_bot_username --dry-run
          # 3. Apply:
          manage.py repair_bot_username

      The command repairs the stored value only when it fails the validator; a valid
      value, including one set through the Django admin, is never overwritten. It uses
      `save()`, so the one-hour bot-username cache is invalidated and the change is
      visible immediately. Editing the singleton in the Django admin is an equivalent
      manual path — `bot_username` is an editable, validated field there.

  - action: update_doc
    id: change_deployment_doc
    path: docs/ops/docker-deployment.md
    description: >
      Add `BOT_USERNAME` to the enumerated required production environment variables, and
      state that it must be the real Telegram handle matching the model's format — not the
      `<your-bot-username>` template value.

      The file was modified at planning time by another activity (BC-8): re-read it
      immediately before editing, change only the enumerated-variable list, and do not
      reformat or reorder anything else.

      This is the documentation half of D1's deliberate breaking change. An operator whose
      deployment currently runs with an empty `BOT_USERNAME` will start failing at boot
      after this block, and the sentence is what tells them why and what to do. It must name
      the repair command.
    code_hint: |
      | `BOT_USERNAME` | yes | Telegram handle without `@`; 3-32 chars, `[A-Za-z0-9_]` only. The template value `<your-bot-username>` is rejected. Seeded into `SiteConfig` by migration `0003`; see `manage.py repair_bot_username` to correct an already-seeded row. |

# ─────────────────────────────────────────────────────────────────────────────
sequence:
  - step: 0
    name: preflight
    actions:
      - "Confirm BLOCK 3 (`9443ade`) and BLOCK 4 (`4fd8bd0`) are landed and `git log --oneline -4` shows them."
      - "Confirm `src/backend/config/settings/oneshot.py` exists and `test_django_build_flag_bypasses_all_prod_guards` is green. If `oneshot.py` is absent, BLOCK 3 has not landed and D3's premise is unverified — stop and report."
      - "Re-read `AdvisoryLockId` and confirm the next free value in the `1..12` band is still `13`."
      - "Re-check `src/backend/apps/core/migrations/` immediately. The next free number is `0006_*`, and D4 rejects adding one — but the fact is recorded so nobody revives option (ii) without re-checking (phase 03 also plans migrations here)."
      - "Confirm `dev.py` contains no `_BOT_TOKEN_PLACEHOLDER_RE` and no `Mirrors` comment, and that the only `Mirrors` string in `config/settings/` is in `test.py`. If either is present, BLOCK 2 has not landed — stop and report."
      - "Confirm the test DB is Up (`.\\Makefile.ps1 test-db`)."
      - "Baseline the scoped suite so a pre-existing failure is not attributed to this change."
      - "Re-read the nine binding constraints against the tree. The tree wins where they disagree."
    gate: "settings + apps/core suites green at baseline"
  - step: 1
    name: CFG-011 — the shared helper (MANDATORY FIRST)
    depends_on: [0]
    actions:
      - "Apply `change_add_helper`, then `change_prod_consumes_helper`, then `change_base_bot_token_comment`."
      - "Run `config/settings/tests` in full. Nothing about `BOT_USERNAME` is required yet, so nothing should move."
      - "Grep for `^<\\[\\^>\\]\\+>$` and for `\\^\\[A-Za-z0-9_\\]\\{3,32\\}$`. BC-2's first half is satisfied: the pattern appears in the helper, the model and the historical migration, and nowhere else."
    expect: >
      Green on arrival. **This step must land before any `BOT_USERNAME` guard exists**, or
      the block ships a second copy of the placeholder regex — the exact thing CFG-011
      reports and the reason the block's own ordering note exists.
  - step: 2
    name: G4's coupling — the env fixtures (BEFORE the guard, deliberately)
    depends_on: [1]
    actions:
      - "Apply `change_ci_deploy_check_bot_username`, `change_prod_env_overrides_bot_username` and `change_prod_env_bot_username`."
      - "Run `config/settings/tests` in full, including `test_deploy_check_env_parity.py` and `test_oneshot_settings.py`."
    expect: >
      Green, and `test_deploy_check_env_block_imports_prod_settings` is still green **with
      the new key present but unused** — the guard does not exist yet, so the extra key is
      inert. That is the point of doing this step before step 3: it means the guard lands as
      a no-op for every shipped test, instead of turning four of them red and requiring the
      Implementor to work out whether the cause is the guard or the fixture.
    note: >
      BLOCK 4's D9 made this obligation explicit and handed it forward. This step discharges
      it.
  - step: 3
    name: CFG-005 — the prod guard
    depends_on: [2]
    actions:
      - "Apply `change_prod_bot_username_guard`, including the seven-to-eight comment change in the bypass comment block."
      - "Apply `change_settings_tests`."
      - "Run the new module in isolation first, then the whole `config/settings/tests` package."
    expect: >
      Green. Five subprocess tests, one pure table, two skips, one anti-drift check.
      `test_deploy_check_env_block_imports_prod_settings` stays green **because** step 2
      already put the key in the block — this is the first place the two halves of the
      coupling meet, and it is the observable proof that D1 was implemented rather than
      papered over.
  - step: 4
    name: the migration validation
    depends_on: [3]
    actions:
      - "Apply `change_migration_full_clean` and `change_migration_refuses_invalid`."
      - "Run `src/backend/apps/core/tests/test_migration_seed_bot_username.py` alone."
    expect: >
      All **four** tests green. The three existing ones are the load-bearing part: they will
      pass because `test_bot`, `env_bot` and the `"" → bazuna_bot` fallback all satisfy the
      regex, and the fallback case is the one that is not obvious. Run it; do not assume it.
  - step: 5
    name: G5 — the repair path
    depends_on: [4]
    actions:
      - "Apply `change_advisory_lock_id` and `change_repair_command`."
      - "Apply `change_repair_command_tests` and run it alone."
      - "Run the command once against a scratch row by hand: set a `SiteConfig` row to the placeholder, prime the cache, run `manage.py repair_bot_username --dry-run`, then without the flag, and observe the value change with no wait."
    expect: >
      Green, and the manual run confirms the repair is observable immediately. This is the
      step that answers the block's most likely "the fix is broken" report.
  - step: 6
    name: documentation
    depends_on: [5]
    actions:
      - "Apply `change_contact_us_doc`."
      - "Re-read `docs/ops/docker-deployment.md` (BC-8), then apply `change_deployment_doc` to the enumerated-variable list only."
  - step: 7
    name: gates
    depends_on: [6]
    actions:
      - "Run the full `tests.verification_gate` sequence below, including the two-sided environment-divergence demonstration and the two red-before-green demonstrations."
  - step: 8
    name: hand-off
    depends_on: [7]
    actions:
      - "Re-read `git status --short` and stage explicit paths only (§1 hard rule). Never `git add -A`."
      - "Do not commit without an explicit user request."
      - "Record the CI obligation plainly: the first CI run of this block is part of its acceptance. The `test` job and the `deploy-check` job both exercise the new guard, and neither was observable locally."
      - "Record the deliberate breaking change: a production deployment running with an empty `BOT_USERNAME` will start failing at boot, and its operator needs `manage.py repair_bot_username` (or the Django admin)."
      - "Name any gate that could not be run here rather than implying it passed."

# ─────────────────────────────────────────────────────────────────────────────
tests:

  must_keep_passing_unchanged:
    - "`src/backend/apps/core/tests/test_migration_seed_bot_username.py`'s three existing tests and its fixture — byte-identical. One test is appended; none is edited."
    - "`src/backend/apps/core/tests/test_migrate_locked.py` in full — the block adds an `AdvisoryLockId` member and touches no migration-locking code, but the enum is imported here and a duplicate `IntEnum` member would alias."
    - "`src/backend/tests/test_docs_ci_parity.py` in full — it asserts string parity across `ci.yml`, `ci-nightly.yml`, `pyproject.toml`, `docker/entrypoint-test.sh`, `Makefile` and `Makefile.ps1`. It is on this list because step 2 edits `ci.yml`, and for no other reason. It has nothing to do with management-command docs, and no command-registry test exists anywhere in the repository."
    - "`src/backend/config/settings/tests/test_settings_defaults.py` in full."
    - "`src/backend/apps/core/tests/test_admin_site_config.py` in full — `list_display` membership, the `RegexValidator`, `max_length == 32` and the `help_text`. It is the reason the model is not touched (D6)."
    - "`src/backend/apps/core/tests/test_site_config_bot_username.py` in full — including `test_save_invalidates_bot_username_cache` and `test_cache_key_is_distinct_from_site_name`, which pin the cache contract the command depends on."
    - "`src/backend/config/settings/tests/test_oneshot_settings.py` in full — all seven. `test_django_build_flag_bypasses_all_prod_guards` is the test that decides D2 and must stay green **unmodified**; an ungated guard would break it by construction. `test_oneshot_bypasses_secrets_for_oneshot_module` and `test_oneshot_module_still_requires_oneshot_flag` are the reason D3 adds nothing to `oneshot.py`. `test_oneshot_flag_is_inert_under_a_valid_prod_environment` is one of the four that step 2 un-couples from the ambient environment."
    - "`src/backend/config/settings/tests/test_deploy_check_env_parity.py` in full — the block's tripwire. It must be green **after** step 2 and **because of** step 2. It is not edited."
    - "`src/backend/config/settings/tests/test_prod_logging.py` in full — every Sentry, LOGGING and EMAIL_* test. `_run_in_subprocess` is imported by four modules and is not edited."
    - "`src/backend/config/settings/tests/test_settings_secrets.py` in full, including its `from config.settings.tests.test_prod_logging import TEST_SECRET_KEY, _prod_env_overrides` resolving unchanged. Not one line is added to it."
    - "`src/backend/config/settings/tests/test_csrf_trusted_origins.py` in full — **not in the block's original list and not in the coordinator's list, and required anyway**: it drives a prod import, does not set `BOT_USERNAME`, and asserts `returncode == 0`. `test_csrf_trusted_origins_required_in_production` additionally pins the bare-`ValueError` failure surface that BC-3's guard placement exists to preserve."
    - "`src/backend/apps/core/tests/test_ci_security.py` in full, and `src/backend/config/settings/tests/test_env_allowlist.py` in full — the first because `ci.yml` changed, the second because `BOT_USERNAME` was already an allowlist member and step 2 adds nothing to it."
    - "`src/telegram_bot/tests/**` — untouched, and the new settings module must not become reachable from the bot's import path."

  must_be_added:

    - name: test_secret_validation_placeholder_detector
      path: src/backend/config/settings/tests/test_bot_username_validation.py
      why: >
        CFG-011's own test. The helper is a pure function pair and needs no subprocess, no
        settings module and no database; testing it directly is the cheapest possible
        regression guard on the extraction itself.
      asserts:
        - "Parametrized: `<your-bot-username>` and `<generate-with-django-secret-key-generator>` are placeholders; `x`, an empty string and a real handle are not."
        - "`is_valid_bot_username` agrees: a placeholder is invalid, an empty string is invalid, `test_bot` is valid."
        - "No subprocess and no environment — the fastest test in the module, and the one that fails first if the extraction is wrong."

    - name: test_bot_username_helper_agrees_with_model_validator
      path: src/backend/config/settings/tests/test_bot_username_validation.py
      why: >
        D6. The pattern is duplicated because settings cannot import the model; this is
        the only thing holding the two copies together. It needs no database — `_meta`
        access is registry-only.
      asserts:
        - "The `RegexValidator` on `SiteConfig.bot_username` carries the same pattern string as `BOT_USERNAME_PATTERN`."
        - "The two agree on a boundary table: 2 chars, 3 chars, 32 chars, 33 chars, a hyphen, a space, a leading `@`, and the shipped placeholder."
        - "`test_admin_site_config.py`'s four assertions are unaffected and the model is not modified."

    - name: test_bot_username_placeholder_rejected_in_production
      path: src/backend/config/settings/tests/test_bot_username_validation.py
      why: >
        The finding's headline case: the literal both `.env.*.example` files ship.
      asserts:
        - "`import config.settings.prod` exits non-zero in a scrubbed environment carrying `BOT_USERNAME=<your-bot-username>`."
        - "`ImproperlyConfigured` is in stderr, `BOT_USERNAME` is in stderr, and the message names `.env.prod`."
        - "stderr does **not** contain the value — the value-free message contract (BC-4), which `test_deploy_check_env_parity.py` also depends on."

    - name: test_bot_username_rejects_empty_in_production
      path: src/backend/config/settings/tests/test_bot_username_validation.py
      why: >
        **This is the assertion that distinguishes G4's two options.** A non-placeholder
        value failing the model regex is rejected under *both* required-non-empty and
        validate-if-present; only the empty case does. Under the rejected option this test
        would assert `returncode == 0`, i.e. it would document that an operator who writes
        `BOT_USERNAME=` ships a bot called `bazuna_bot` and a site full of dead links. It
        is shipped in the opposite direction on purpose, and the module docstring must say
        why.
      asserts:
        - "Present-but-empty `BOT_USERNAME` exits non-zero with `ImproperlyConfigured` naming `BOT_USERNAME`."
        - "The value is empty rather than absent, so the assertion is portable: the test's own scrubbed environment supplies the key explicitly and `read_env(overwrite=False)` never overwrites a key that is present."

    - name: test_bot_username_rejects_value_failing_model_regex_in_production
      path: src/backend/config/settings/tests/test_bot_username_validation.py
      why: >
        **The assertion that distinguishes a validator from a placeholder detector.**
        `^<[^>]+>$` accepts every one of these, so a helper that only detects the shipped
        template would let all of them through and the finding's own note 6 would be
        unaddressed. This is why the helper exposes a predicate and not only a detector.
      asserts:
        - >
          Parametrized over: two characters (too short), a value containing a space, a
          value containing a hyphen, a value with a leading `@`, and 33 characters (too
          long) — each exits non-zero with `ImproperlyConfigured` naming `BOT_USERNAME`.
        - "None of the values is a `<...>` template, so the placeholder branch cannot be what fired; the message is the regex-branch one and says so."

    - name: test_bot_username_valid_value_accepted_in_production
      path: src/backend/config/settings/tests/test_bot_username_validation.py
      why: >
        The other direction. A guard with no positive case is indistinguishable from a
        guard that rejects everything, and `test_deploy_check_env_parity.py` is what would
        catch that — an assertion belonging to a different module would be read as a
        failure of this one.
      asserts:
        - "A value matching `^[A-Za-z0-9_]{3,32}$` imports cleanly, and `settings.BOT_USERNAME` reads back unchanged."
        - "Same assertion in the Docker test container and in the CI test job, because the environment is scrubbed (D7-1)."

    - name: test_bot_username_guard_skipped_during_build
      path: src/backend/config/settings/tests/test_bot_username_validation.py
      why: >
        D2's counterpart. An ungated guard would make the Docker builder stage fail — it
        runs `collectstatic` under `config.settings.prod` with `DJANGO_BUILD=1` and no
        `.env` at all — and would break `test_django_build_flag_bypasses_all_prod_guards` by
        construction. This test is the block's own statement that it did not.
      asserts:
        - "The placeholder value plus `DJANGO_BUILD=1` under `config.settings.prod` imports with exit 0."
        - "`ImproperlyConfigured` and `ValueError` are both absent from stderr."

    - name: test_bot_username_guard_skipped_for_oneshot_bootstrap
      path: src/backend/config/settings/tests/test_bot_username_validation.py
      why: >
        D3's counterpart, and the assertion that keeps the dev half from being "fixed"
        later. The bootstrap path is deliberately unguarded because a guard cannot be
        reached there; the migration's `full_clean()` is what protects the database. If
        someone later adds an ungated guard to `oneshot.py` to close the gap, this test
        fails — which is the point.
      asserts:
        - "`DJANGO_ONESHOT=1` plus `DJANGO_SETTINGS_MODULE=config.settings.oneshot` with the placeholder value imports with exit 0."
        - "The docstring records that the DB is protected there by migration `0003`'s `full_clean()`, not by this guard."

    - name: test_seed_refuses_value_failing_validator
      path: src/backend/apps/core/tests/test_migration_seed_bot_username.py
      why: >
        The provable bypass, closed. `QuerySet.update()` never calls `full_clean()`, which
        is how `<your-bot-username>` came to live in a field whose own `RegexValidator`
        rejects it.
      asserts:
        - "`seed_bot_username(django_apps, None)` under `override_settings(BOT_USERNAME=\"<your-bot-username>\")` raises `ValidationError`."
        - "**The row is unchanged after the raise** — the assertion that catches a migration which validates after writing."
        - "`schema_editor=None` throughout, matching the three existing tests."

    - name: test_repair_bot_username_corrects_invalid_row
      path: src/backend/apps/core/tests/test_repair_bot_username_command.py
      asserts:
        - "A `SiteConfig` row holding the placeholder becomes the `BOT_USERNAME` setting value after `call_command(\"repair_bot_username\")`."
        - "The value is the model's field default when the setting is empty is **not** asserted here — that is case 1 and has its own test."

    - name: test_repair_bot_username_invalidates_cached_bot_username
      path: src/backend/apps/core/tests/test_repair_bot_username_command.py
      why: >
        The load-bearing test in the whole block, and the direct answer to the most likely
        "the fix is broken" report. `QuerySet.update()` emits no `post_save`, so a repair
        written that way leaves the stale value cached for `SITE_CONFIG_CACHE_TTL` = 3600
        seconds. A test that only checks the database row passes identically for `save()`
        and `update()`.
      asserts:
        - "The cache is **primed** with the invalid value and `get_bot_username()` is asserted to return it, so the test cannot pass vacuously."
        - "After the command, `get_bot_username()` returns the repaired value with no cache manipulation and no wait."
        - "A companion assertion that `update()` would fail this: demonstrated red, below."

    - name: test_repair_bot_username_leaves_valid_row_untouched
      path: src/backend/apps/core/tests/test_repair_bot_username_command.py
      why: >
        The guard against the command becoming a way to stomp the admin. The DB is the
        operator of record by design and `docs/01-spec/contact-us.md` says so.
      asserts:
        - "A row holding an admin-set value is unchanged after the command, even when the setting differs."
        - "The command is idempotent: a second run changes nothing and exits 0."

    - name: test_repair_bot_username_refuses_when_settings_value_is_invalid
      path: src/backend/apps/core/tests/test_repair_bot_username_command.py
      asserts:
        - "With `BOT_USERNAME` empty **or** a placeholder, the command raises `CommandError` (or exits non-zero) and the row is unchanged."
        - "The refusal is D4's case 1: substituting the model default here would manufacture the silent `bazuna_bot` dead link that D1 exists to prevent."

    - name: test_repair_bot_username_dry_run_changes_nothing
      path: src/backend/apps/core/tests/test_repair_bot_username_command.py
      asserts:
        - "`--dry-run` leaves the row **and the cache** unchanged, in each of the three applicable cases."

  must_be_demonstrated_red:
    - >
      **Demonstration A — the guard's red before its green (the required Validator duty).**
      Temporarily delete the new `BOT_USERNAME` guard block from `prod.py`, run
      `test_bot_username_placeholder_rejected_in_production`,
      `test_bot_username_rejects_empty_in_production` and
      `test_bot_username_rejects_value_failing_model_regex_in_production`, and confirm
      **all three go red** — each with a message saying the import succeeded when it should
      have failed. Restore `prod.py` byte-identically and confirm all three are green again.
      *This is the demonstration that the tests are observing the guard and not the
      fixture, the ambient environment, or a stale import cache.* It is a **Validator duty,
      not a shipped test**; BLOCK 3 set the precedent and BLOCK 4 repeated it.
      *Environment:* valid in both — the new module's environment is scrubbed, so the
      result does not depend on which environment it runs in.
    - >
      **Demonstration B — the cache-invalidation assertion has teeth.** Temporarily change
      the command's `config.save()` to `SiteConfig.objects.filter(pk=config.pk).update(...)`
      and run `test_repair_bot_username_invalidates_cached_bot_username`. It must go **red**
      with the primed value still being returned. Restore and confirm green. This is the
      one demonstration that would have caught the block's most likely real bug.
    - >
      **Demonstration C — the CI environment condition, two-sided (D7-3).**
      Back up `.env.test`, comment out its `BOT_USERNAME` line, and run the full
      `src/backend/config/settings/tests` package. Record both directions:
        1. With `change_prod_env_overrides_bot_username` and `change_prod_env_bot_username`
           **reverted**, at least
           `test_oneshot_flag_is_inert_under_a_valid_prod_environment` and
           `test_csrf_trusted_origins_accepted_in_production` go **red**. That is the
           environment divergence made visible, and it is what the CI `test` job would see
           today.
        2. With the edits in place, the package is **green** in that same environment.
      Then restore `.env.test`, re-read its `BOT_USERNAME` line to prove the restore, and
      confirm the package is green again with the ambient value present.
      *Why this is the only faithful local reproduction:* `BOT_USERNAME` reaches the test
      container twice — through `env_file:` and through the `./.env.test:/app/src/.env:ro`
      bind-mount that `base.py`'s present-file branch reads with `read_env(overwrite=False)`
      — so removing the key from the process environment is not enough; it has to leave
      the file. `.env.test` is gitignored, untracked and never regenerated by
      `Makefile.ps1`, so the edit is invisible to the repository, and BC-9 requires the
      restore to be verified rather than assumed.
    - >
      **Demonstration D — the guard's placement is load-bearing (BC-3).** Temporarily move
      the new guard to sit immediately above the `CSRF_TRUSTED_ORIGINS` check, set
      `CSRF_TRUSTED_ORIGINS=""` with an empty `BOT_USERNAME` in the scrubbed environment,
      and run `test_csrf_trusted_origins_required_in_production`. It must go **red** with an
      `ImproperlyConfigured` about `BOT_USERNAME` where a bare `ValueError` about CSRF was
      expected. Restore and confirm green. *This is what stops a future "let me group the
      bot guards together" edit from silently changing six tests' failure surfaces.*
    - >
      **Demonstration E — the migration edit is inert where it should be.** Confirm the
      three existing seed tests pass unchanged with the `full_clean()` in place, and that
      `test_seed_does_not_overwrite_custom` still passes — it is the one that proves the
      `filter(pk=1, bot_username="bazuna_bot")` guard survived the rewrite.
    - >
      **Demonstration F — the Docker builder stage still builds.** Run the builder stage
      (`DJANGO_BUILD=1`, `config.settings.prod`, no `.env`, `collectstatic --noinput`) and
      confirm exit 0. `test_bot_username_guard_skipped_during_build` is the cheap
      approximation; this is the real one, and it is the only way to be sure D2's
      consequence was reasoned about rather than assumed. Record it.
    - >
      All six are **Validator duties**. Record each output and, where the behaviour could
      differ between environments, say which environment it was run in. A negative control
      that was never seen red proves nothing.
    - >
      **One thing that cannot be demonstrated locally, and must be stated rather than
      implied:** the CI `test` job's actual result. Neither the guard's behaviour nor the
      fixture coupling can be *observed* in CI from this host. The hand-off must say the
      first CI run is part of this block's acceptance.

  need_no_test:
    - >
      A command-registry or `--help` test. No such test exists anywhere in the repository
      and none is added; the block's note justifying `test_docs_ci_parity.py` by
      "management-command docs" is corrected above — that file asserts CI/Makefile/pytest
      string parity and nothing about commands.
    - >
      A test that `.env.prod.example` and `.env.dev.example` ship the placeholder. The
      placeholder **should** stay: it is the trigger the guard exists for, and a test
      pinning it would make the file a contract to preserve the defect. What is asserted is
      the guard's rejection of it.
    - >
      A test for `AdvisoryLockId.REPAIR_BOT_USERNAME`'s numeric value. The enum is the
      convention; `13` is a free slot, not a contract, and a test pinning it would fight
      the next phase that needs a lock.
    - >
      Any change to `test_admin_site_config.py` or to the model. The duplication between
      the helper's pattern and the model's is real and is held together by
      `test_bot_username_helper_agrees_with_model_validator`, not by a test that rewrites
      the model.
    - >
      A test on the *template* layer. No template is touched. The only user-visible failure
      is `telegram_deep_link`'s base64 `data-bot-encoded` attribute, and it is fixed by
      fixing the value it encodes, not by changing the tag.

  verification_gate:
    - step: 1
      name: scoped run (the new settings module alone)
      command: >
        `$dc run --rm -e PYTEST_SKIP_MARKERS=seed -e
        PYTEST_OPTS="src/backend/config/settings/tests/test_bot_username_validation.py" test`
        with `$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test
        -f docker-compose.yml -f docker-compose.test.yml'`
      expect: "Green. Count the collected tests against the eight functions listed above; a mismatch means collection picked up something else."
    - step: 2
      name: scoped run (the whole affected surface)
      command: >
        `$dc run --rm -e PYTEST_SKIP_MARKERS=seed -e
        PYTEST_OPTS="src/backend/config/settings/tests src/backend/apps/core/tests/test_migration_seed_bot_username.py src/backend/apps/core/tests/test_repair_bot_username_command.py src/backend/apps/core/tests/test_site_config_bot_username.py src/backend/apps/core/tests/test_admin_site_config.py src/backend/apps/core/tests/test_migrate_locked.py src/backend/apps/core/tests/test_ci_security.py src/backend/tests" test`
      expect: >
        Green, and the total is the pre-existing count **plus** the new tests. A drop is a
        collection or import regression — most likely the `test_prod_logging` import.
    - step: 3
      name: fresh schema
      command: ".\\Makefile.ps1 test-recreate"
      expect: >
        Required: `0003`'s data function changed. A `--reuse-db` run does not replay
        migrations, so a green `--reuse-db` suite is not evidence that the edited migration
        still works end to end.
    - step: 4
      name: full fast gate
      command: ".\\Makefile.ps1 test"
      expect: >
        Green. **This is necessary and not sufficient** — see step 6. The i18n completeness
        gate is part of this run and must pass (BC-5: no user-visible string was added).
    - step: 5
      name: static gates
      command: "uv run ruff check src/ and uv run basedpyright src/"
      expect: >
        Both green. The new helper is `Final`-annotated and must type-check under the
        project's basedpyright configuration; `re.match(BOT_USERNAME_PATTERN, value)` returns
        `Match[str] | None` and the `is None` comparison is what narrows it. Run
        `ruff check --fix src/` if import order trips `I001` in any new module.
    - step: 6
      name: the environment-divergence demonstration (D7-3)
      command: "Demonstration C above — back up `.env.test`, comment out its `BOT_USERNAME` line, run the settings package in both directions, restore, re-read, re-run."
      expect: >
        Red without the fixture edits, green with them, green again after the restore. This
        is the gate that discharges the CI-side condition locally. Record every output.
    - step: 7
      name: red-before-green demonstrations
      command: "Demonstrations A, B, D, E and F above, each restored and re-confirmed green."
      expect: "Each red, then green again. Record every output and the environment it was run in."
    - step: 8
      name: the live dev stack
      command: >
        `docker compose --env-file .env.dev -f docker-compose.yml
        -f docker-compose.dev.override.yml up -d` then inspect the five one-shot services
        and `web`.
      expect: >
        The five one-shots complete (they resolve `config.settings.oneshot`, where the
        guard is deliberately inert — D3) and `web` comes up. This is the check that D3's
        rejection of the `dev.py` half did not break anything: a dev guard is only
        reachable from `web`/`bot`, and the value that reaches the database comes from the
        migration, which now validates.
    - step: 9
      name: the first CI run
      command: "the `test` and `deploy-check` jobs on the branch carrying this block"
      expect: >
        Both green. **This step cannot be discharged on this host** and is recorded as an
        acceptance obligation, not a gate the Implementor can tick. If it has not been
        observed, the hand-off says so.

acceptance_criteria:
  - >
    `src/backend/config/settings/secret_validation.py` exists, exports only
    `BOT_USERNAME_PATTERN`, `is_placeholder`, `is_valid_bot_username` and
    `validate_bot_username`, and imports nothing from any settings module or from `apps.*`
    (BC-1, checked by inspecting the import graph, not by reading the file top to bottom).
  - >
    `grep` finds exactly one live copy of the placeholder pattern outside the model and the
    historical migration, and exactly one live copy of the bot-username regex outside the
    model and the historical migration. `prod.py` no longer defines
    `_SECRET_PLACEHOLDER_RE` and aliases nothing under that name (BC-2).
  - >
    `config.settings.prod` rejects an empty, a placeholder, and a model-regex-failing
    `BOT_USERNAME`, and accepts a real-format one — each with a distinct, value-free
    `ImproperlyConfigured` message naming the variable and the remediation (BC-4).
  - >
    The guard is the **last** statement in `prod.py`, after the `REDIS_URL` block, and
    `test_csrf_trusted_origins_required_in_production` still fails with a bare `ValueError`
    naming `CSRF_TRUSTED_ORIGINS` (BC-3).
  - >
    The guard sits inside `if not _SKIP_SECRET_VALIDATION:`, the bypass comment block reads
    "The eight secret guards below", and `test_django_build_flag_bypasses_all_prod_guards`
    is green **unmodified** (D2). Nothing else in that comment block changed.
  - >
    `dev.py` and `oneshot.py` are byte-identical. `config/settings/test.py` is
    byte-identical — it is BLOCK 9's file, and the block's original file surface named a
    "Mirrors prod" comment that does not exist in either module (D3, D8).
  - >
    `base.py`'s `BOT_TOKEN` comment names the shared helper and the guard that consumes it,
    and says "the shared helper" rather than "two locations". `ALLOWED_ENV_VARS` and both
    `.env` handling branches are untouched.
  - >
    `.env.prod.example` and `.env.dev.example` are byte-identical. The placeholder stays:
    it is the defect's trigger, and the guard is what makes shipping it survivable.
  - >
    `ci.yml`'s diff is exactly one added key in `jobs.deploy-check.env`. The other ten
    keys, the contract comment, the steps and every other job are byte-identical, and
    `test_ci_security.py` and `test_docs_ci_parity.py` are both still green.
  - >
    `_prod_env_overrides` and `_prod_env` both assign `BOT_USERNAME` explicitly, following
    the file's existing `overrides.pop` idiom, and `_run_in_subprocess` is untouched in both
    files.
  - >
    Migration `0003`'s `seed_bot_username` calls `full_clean()` before `save()`, never
    dereferences `schema_editor`, keeps the `filter(pk=1, bot_username="bazuna_bot")`
    guard, and its docstring records that it protects fresh databases only, names both of
    that filter's blind spots, and points at `manage.py repair_bot_username`.
  - >
    `AdvisoryLockId.REPAIR_BOT_USERNAME` is in the `1..12` band, not in the `100..111`
    range, and no existing member was renumbered.
  - >
    `manage.py repair_bot_username` follows `cleanup_login_tokens.py`'s conventions
    (module docstring, `logger` and no `print()`, English untranslated `help`,
    `transaction.atomic()` + `advisory_lock()`, `--dry-run`), uses `save()` and contains
    no `invalidate_bot_username_cache()` call and no fourth copy of the default username
    (BC-6, D4).
  - >
    A `SiteConfig` row holding an invalid username is corrected **and the cached value is
    invalidated** — demonstrated by priming the cache, asserting the primed value is
    returned, running the command, and asserting the new value is returned with no wait.
    Demonstration B shows the same test going red when `save()` is replaced by `update()`.
  - >
    A valid row is never overwritten, the command is idempotent, and the command refuses
    with a non-zero exit — changing nothing — when `settings.BOT_USERNAME` is empty or a
    placeholder.
  - >
    The new settings-test module builds its environment by allowlisting
    `_prod_env_overrides()`'s keys with `BOT_USERNAME` deliberately absent, so it cannot
    observe `.env.test`, `os.environ`, or a developer's shell; it defines no local
    `subprocess.run` and imports `_run_in_subprocess` from `test_prod_logging`.
  - >
    **The environment-divergence condition was verified in both directions, not once.**
    With `BOT_USERNAME` removed from `.env.test`, the settings package goes red with the
    fixture edits reverted and stays green with them in place; `.env.test` is restored and
    its `BOT_USERNAME` line re-read, and the package is green again. Outputs recorded.
  - >
    **A green `.\\Makefile.ps1 test` is not, on its own, evidence for this block.** The
    Docker test container supplies `BOT_USERNAME` from `.env.test` through both `env_file:`
    and the `src/.env` bind-mount; the CI `test` job supplies it through neither, so a
    local green run is the run that **cannot** fail. The hand-off must record the CI
    obligation as outstanding until the first CI run of this block is observed, and must
    not imply the `test` or `deploy-check` job was observed if it was not.
  - >
    The intra-block order was honoured: CFG-011's helper landed and went green **before**
    any `BOT_USERNAME` guard existed, and the env fixtures landed **before** the guard, so
    no shipped test was ever red because of this block's own intermediate state. No third
    copy of the placeholder regex exists at any point in the sequence.
  - >
    Demonstrations A–F were each shown red and then green, with their outputs and
    environments recorded. No `skipif`, `xfail` or "known missing variables" list was added
    anywhere: a suppression here would recreate the silent-drift failure BLOCK 4 exists to
    end.
  - >
    `test_migration_seed_bot_username.py`'s three original tests, its fixture and
    `test_admin_site_config.py` are unmodified. `uv run ruff check src/` and
    `uv run basedpyright src/` are green. No dependency, CI job, Dockerfile, compose file,
    Makefile, template, bot file or `.ai/audit/**` file was added or modified.
  - >
    `docs/01-spec/contact-us.md` names the repair command, `--dry-run`, the cache
    invalidation and the admin equivalent, and the order (fix `.env.prod` first).
    `docs/ops/docker-deployment.md` lists `BOT_USERNAME` as required and names the repair
    command; the file was re-read immediately before editing and only the enumerated-variable
    list changed.
  - >
    Nothing was committed without an explicit user request, and only explicitly staged
    paths are in the commit (§1 hard rule — never `git add -A`).
```

**Why this shape.** Two of the block's five rulings are reversals of the text above it, and
both reversals come from the same place: BLOCK 3 moved the dev one-shots off `prod`. That
single change invalidates the report's stated justification for the `dev.py` half — the
processes that run the migration are now exactly the processes a settings-module guard
cannot reach — and it removes the possibility of writing the `BOT_USERNAME` guard ungated,
because the Docker builder stage runs `collectstatic` under prod settings with no `.env` and
a shipped test asserts that *every* guard is skipped under `DJANGO_BUILD=1`. The guard
therefore goes in `prod.py` only, gated, and the dev half's job is taken by the migration's
`full_clean()`, which runs everywhere. That is a smaller change than the plan describes and
a more effective one.

**The second reversal is G4, and it is coupled to the block's most dangerous property.**
D1 makes `BOT_USERNAME` required and non-empty, which sounds like one guard and is in fact
one guard plus three fixture edits plus a two-sided environment demonstration. The reason
is worth stating plainly: the rejected option is not cheaper, it is *quieter*. An operator
who writes `BOT_USERNAME=` under validate-if-present ships a bot called `bazuna_bot`, and
because the database wins over the environment and `get_bot_username()`'s own fallback is
that same literal, nothing downstream can distinguish that from a correct deployment. The
whole point of the finding is that a wrong username is invisible; a guard that tolerates
the empty case would leave the most likely operator mistake invisible too.

**One hazard the coordinator should carry forward.** `.\Makefile.ps1 test` is green locally
and the CI `test` job is red for any of four shipped tests, because the Docker container
receives `BOT_USERNAME` from `.env.test` twice over and CI receives it not at all. That is
the same defect class as CFG-002 — a contract asserted in one place and verified nowhere —
one level down, and it is why the block ships a scrubbed test environment (structurally
immune), explicit fixture assignments (the divergence closed), and a two-sided local
reproduction (the condition actually observed). Until the first CI run of this block is
watched, the correct statement is that the divergence has been *designed out*, not that it
has been *seen* closed.

---

### BLOCK 6 — Env contract parity: allowlist, templates, and the reverse-direction test (CFG-008 + CFG-009 + VAL-003)

| | |
|---|---|
| **Findings owned** | `CFG-008`, `CFG-009`, `VAL-003` (hard constraint), `VAL-004` instance (c) |
| **`depends_on`** | **BLOCK 3** (which regroups `ALLOWED_ENV_VARS` — editing the same structure first would produce a merge conflict and two partial regroupings) |
| **Priority** | P2 |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**Agent requirement decision (the "high risk ⇒ all agents" rule applies here).**
- New **test infrastructure** whose failure mode is a false positive (a noisy test gets
  disabled, and the durable half of the phase silently dies).
- The **VAL-003 hazard**: the report offered a deletion branch as cost-equivalent with
  the retitle branch. It is not — deletion turns two shipped green tests red and
  desynchronises a spec line.
- The **VAL-004** cross-cutting recommendation rides on this block.
- It edits the **env templates**, which is the operator-facing deployment contract, and
  one template edit is blocked by a shipped test.

- **Implementor — yes.** Always.
- **Auditor — yes.** The authoritative consumed-name set must be re-derived at `344ca2b`
  — not inherited from the report's 33-vs-36 sweeps. The Auditor must also establish
  which `.env.*.example` keys are **shell-consumed** rather than Python-consumed
  (the report found one such key, `SCHEDULER_HEALTH_STALE_SECONDS`, read by
  `docker/healthcheck-scheduler.sh` and set by `docker-compose.prod.yml`), because a
  pure-Python sweep will keep missing them and a test built on it will keep
  false-failing.
- **Researcher — yes.** One bounded question: **what is a maintainable way to keep a
  hand-maintained env-var contract honest in a codebase that reads variables four
  different ways** (`env()`, `env.*()`, `os.getenv`, `os.environ[...]`) **and through four
  channels** (settings modules, management commands, shell scripts, compose files)? The
  answer determines whether the reverse-direction test is viable at all. See §3.6.
- **Planner — yes.** G8 is unresolved, the test's location and shape must be designed,
  and the `.env.example` rewrite is a documentation-architecture decision (what does a
  stub that is not comprehensive actually contain?).
- **Validator — yes.** The measure of this block is whether the new test **would have
  caught** the two drift instances that already exist, and whether it is quiet enough to
  survive. Both require independent judgment, not inspection.

**3.6 — The reverse-direction test (G8: open; recommendation, not a decision).**

| Option | Change | Pro | Con |
|---|---|---|---|
| **A** | A static-source **regex sweep** over non-test `src/**/*.py` asserting every `os.getenv` / `env()` name is in `ALLOWED_ENV_VARS`. | Directly catches the `RUN_TRANSLATION_BACKFILL` class without touching production code. | **Three independent sweeps produced 33, 36 and 36 names.** It is inherently approximate; a false positive disables the test within a week, and a false negative gives false assurance. It also cannot see the `deploy-check` env block or the compose files (the report's own `R-7`). |
| **B (recommended)** | An **explicit, curated `CONSUMED_ENV_VARS`** constant owned next to `ALLOWED_ENV_VARS`, plus a test that (i) every name in it is in `ALLOWED_ENV_VARS`, and (iI) every `env()` / `env.*()` call **in the settings package** appears in it. Sweep only the settings modules — a small, stable, high-signal surface — and treat the wider `src/**` sweep as a separate, non-default `@pytest.mark.slow` job. | The curated list is a readable, reviewable statement of the contract, which is what makes the next reviewer's job easy. The automated check is exact for the surface that matters most and cannot false-positive on shell noise. | A curated list can drift from the wider codebase by construction. That is a trade, not a free win — and it must be stated in the block's summary so nobody reads the test as total coverage. |
| **C** | Skip the reverse-direction test; ship only the forward fix (the one allowlist entry + the template additions) and record the gap. | Zero risk of a noisy test. | Leaves VAL-004 instance (c) open and the anti-pattern unguarded — the opposite of the phase's stated ROI thesis. |

**Recommendation:** Option B. **The Planner must state which it chose and must not
describe any of these as complete coverage** — the report's `R-7` is explicit that the
allowlist structurally cannot see the `deploy-check` env block or the compose files.

**Findings and notes carried forward.**
1. **The only missing allowlist entry is `RUN_TRANSLATION_BACKFILL`**, read by
   `apps/core/utils/migrate_locked.py` and documented in **six** tracked documentation
   files plus the command docstring. Adding it to `ALLOWED_ENV_VARS` is one line; the
   report asks for a note in `.env.prod.example` next to the migrate notes, which is
   where an operator following the migration workflow will look.
2. **`.env.example` carries a UTF-8 BOM** (`EF BB BF` confirmed at the anchor). It
   defeats a naive `startswith("#")` parser and must be removed in the same edit.
3. **`.env.example` says "Comprehensive" and is not.** No compose file, script or
   Makefile target uses it; the operational templates are the three tier files. The
   retitle must state plainly that the tier templates are authoritative, and must not
   contradict the "copy one of the three" instructions already in its header.
4. **The stub must retain `CSRF_TRUSTED_ORIGINS=` and `SENTRY_DSN=`** (G6, decided).
   `test_csrf_trusted_origins_in_example` and `test_sentry_dsn_in_env_examples` assert
   their presence. If the retitled stub is reduced to a pointer, **both keys must
   remain** or the suite goes red for a reason that has nothing to do with the finding.
5. **The two doc references stay valid** because the file survives:
   `docs/01-spec/architecture-structure.md`'s repository-structure listing and
   `docs/99-agent/architecture.md`'s `.env.*` note. If the retitle changes what the file
   *is*, both may need a one-line amendment — but the file listing itself does not
   change.
6. **The real `.env.prod` is missing 12 of the same names**, including `EMAIL_HOST`. That
   is a gitignored operator file and is **out of scope** — but the Validator should note
   it, because it is the same trap the finding describes, one level up.
7. **`.env.*.example` paths are allowlisted in `.gitleaks.toml`**, so adding placeholder
   values to the templates does not trip the secret scanner. Adding a *non*-placeholder
   real value would.
8. **The counts to verify before writing:** the report records `.env.example` = 26 keys
   and `.env.prod.example` = 34 keys, with 19 and 12 consumed names absent. Re-derive at
   the anchor; do not transcribe.

**File surface (semantic units).**
- `src/backend/config/settings/base.py` → `ALLOWED_ENV_VARS` (**one entry added**; the
  grouping is BLOCK 3's, not this block's).
- `.env.example` → the header block (retitle, BOM removal), plus the missing variable
  blocks or explicit "see `.env.<tier>.example`" markers.
- `.env.prod.example` → the migrate-notes area (`RUN_TRANSLATION_BACKFILL`) and the
  missing blocks.
- `src/backend/config/settings/tests/test_env_allowlist.py` → the new reverse-direction
  and template-parity tests (per the chosen option), and `test_example_keys_in_allowlist`
  (must keep passing).
- **New (Option B only):** a curated consumed-name constant. Place it in the settings
  package beside `ALLOWED_ENV_VARS`, not in a test module — it is a contract, not a
  test fixture.
- `docs/01-spec/architecture-structure.md` and `docs/99-agent/architecture.md` → **only**
  if the retitle changes what the file is. See note 5.
- **Not touched:** `docker/entrypoint.sh`, any settings module body, any compose file.

**Tests required.**
- *Must keep passing unchanged:* `test_example_keys_in_allowlist` (all four
  parametrizations), `test_scheduler_health_stale_seconds_allowlisted`,
  `test_unknown_env_var_logs_warning`, `test_known_env_vars_no_warning`,
  `test_csrf_trusted_origins_in_example`, `test_sentry_dsn_in_env_examples`.
- *Must be added:*
  - The reverse-direction test per the chosen option, plus a demonstration that it is
    **red** when `RUN_TRANSLATION_BACKFILL` is removed from `ALLOWED_ENV_VARS` and green
    when restored. A test that was never seen red proves nothing.
  - Template parity: the chosen mechanism's assertion over the tier templates.
  - A `.env.example` assertion that it no longer claims to be comprehensive — cheap, and
    it stops the retitle from silently regressing.
- *Need no test:* the individual added template keys — they are documentation. The
  parity test is the guard.
- *Gate:* `$dc run --rm -e PYTEST_OPTS="src/backend/config/settings/tests/test_env_allowlist.py src/backend/config/settings/tests/test_csrf_trusted_origins.py src/backend/config/settings/tests/test_prod_logging.py" test`,
  then `.\Makefile.ps1 test`.

**Risk / rollback.**
- *Risk:* the new test is noisy and gets disabled, destroying the durable half of the
  phase. The red/green demonstration and the "no option provides complete coverage"
  statement in the block summary are the controls.
- *Risk:* a reduced stub drops `CSRF_TRUSTED_ORIGINS=` or `SENTRY_DSN=` and turns two
  green tests red — the correct outcome, but it must be caught **in this change**, not in
  a follow-up. Note 4.
- *Risk:* the block touches a documentation file that is **already modified in the working
  tree** (see §6). Coordinate; do not clobber.
- *Risk:* over-claiming coverage. The block's summary must say what the test does **not**
  cover (the `deploy-check` env block, the compose files).
- *Rollback:* the allowlist entry and the template edits are independently revertible.
  The test is revertible only together with whatever constant it consumes (Option B).

#### BLOCK 6 — Implementation task

> Written by the BLOCK 6 Planner against the tree at `6413df5` (BLOCK 1 = `071e5c7`,
> BLOCK 2 = `cb31553`, BLOCK 3 = `9443ade`, BLOCK 4 = `4fd8bd0`, BLOCK 5 = `6413df5`).
> This task resolves **G8**, designs the `.env.example` shape, and is the contract the
> BLOCK 6 Implementor executes. **Never use line numbers** — every target below is a
> file, module, constant, comment block, template section or prose sentence.
>
> **This subsection supersedes §3.6, the "Findings and notes carried forward" notes, the
> "File surface (semantic units)" list and the "Tests required" list above it wherever
> they disagree.** It is an append; nothing above it is edited. Four of its rulings
> reverse that text: **D1** rejects the §3.6 recommendation (Option B) in favour of an
> **AST scan over the whole non-test `src` tree with no new production constant**,
> **D2** fixes the `.env.example` shape as a cross-tier stub with the `Email / SMTP`
> block added, **D3** replaces the block's implied "add every missing key" plan with a
> single derivable scope rule, and **D5** settles how a settings module named
> `test_migrations.py` is classified. The block's own "clobber hazard" risk (it edits a
> doc already modified in the working tree) is **void** — see
> `corrections_to_block_notes`.
>
> **Measured at the anchor, by this Planner, independently of the Auditor and the
> Researcher:** `ALLOWED_ENV_VARS` is a 48-entry `frozenset` in three groups
> (Python-consumed 34, bootstrap control flags 2, shell/compose 12). An `ast.NodeVisitor`
> walk over all **337** non-`tests`-path `.py` files under `src/` yields exactly **36**
> consumed names in **≈0.3 s** with **zero** false positives, and the single name missing
> from the allowlist is exactly `RUN_TRANSLATION_BACKFILL`, read at
> `apps/core/utils/migrate_locked.py`. Reads occur in exactly **three** files
> (`config/settings/base.py` — 34, `config/settings/prod.py` — 4, and
> `apps/core/utils/migrate_locked.py` — 1); `prod.py`'s four overlap `base.py`'s set, so
> the settings package contributes 35 and the tree contributes 36.
> *Reconciling the Researcher's "300 non-test files" with this Planner's 337:* 36 of the
> 337 are migration files, which are **in** scope — a migration can read an environment
> variable, and excluding them would reintroduce exactly the scope gap D1 exists to close.
> 337 − 36 migrations = 301, which is the Researcher's count. The name set is 36 either
> way, because no migration reads anything today.

```yaml
id: block6-cfg008-cfg009-env-contract-parity

title: >
  Add the missing allowlist entry, close the consumed-to-allowlist gap with an
  AST-derived reverse-direction test, and retitle .env.example as a cross-tier stub
  (CFG-008 + CFG-009 + VAL-003 + VAL-004 instance (c))

priority: P2

depends_on:
  - "BLOCK 3 (9443ade) — ALLOWED_ENV_VARS was regrouped into Python-consumed / bootstrap control flags / shell-compose, and the group comments were written by that block. D1 amends one of those comments in the same edit; the grouping itself is not BLOCK 6's to change."
  - "BLOCK 4 (4fd8bd0) — test_deploy_check_env_parity.py is VAL-004 instance (b) and this block is instance (c). The two are different contracts and must not be merged: BLOCK 4's module deliberately has no hand-maintained required-variable constant, D1 refuses to introduce one here, and BLOCK 4's module is not touched."
  - "BLOCK 5 (6413df5) — landed, and it did not change the consumed-name set: prod.py gained a guard, secret_validation.py was added, and neither reads a new environment variable. Recorded so the Implementor does not re-derive a BLOCK 5 dependency that does not exist."

source_reference: .ai/plans/02-config-secrets-remediation.md
source_section: "BLOCK 6 — Env contract parity: allowlist, templates, and the reverse-direction test (CFG-008 + CFG-009 + VAL-003)"
source_file: .ai/audit/99-validation/02-config-secrets-validated-findings.md
source_blocks:
  - "BLOCK 6 — Env contract parity: allowlist, templates, and the reverse-direction test (CFG-008 + CFG-009 + VAL-003)"
  - "CFG-008 — RUN_TRANSLATION_BACKFILL is read by migrate_locked.py but absent from ALLOWED_ENV_VARS"
  - "CFG-009 — .env.example claims to be Comprehensive and omits consumed variables"
  - "VAL-003 — hard constraint: retitle, never delete; the stub retains CSRF_TRUSTED_ORIGINS= and SENTRY_DSN="
  - "VAL-004 instance (c) — bidirectional consumed <-> allowlist <-> template parity"
  - "G8 — reverse-direction allowlist test: regex sweep or curated constant?"
  - "G6 — closed by §0.5: the stub retains CSRF_TRUSTED_ORIGINS= and SENTRY_DSN="

description: >
  `config/settings/base.py`'s `ALLOWED_ENV_VARS` is the allowlist `_warn_unknown_env_vars`
  consults, and it is the project's only mechanism for catching a typo'd environment
  variable. Two defects make it weak. **The first** is CFG-008: `RUN_TRANSLATION_BACKFILL`
  is read by `apps/core/utils/migrate_locked.py` and documented in five tracked files plus
  a command docstring, and it is not in the allowlist — so a deployment that sets it
  correctly gets a WARNING naming a variable it set on purpose. **The second** is the
  direction that does not exist: nothing asserts that a variable the code reads is in the
  allowlist at all. The report's remediation for CFG-008 is one line; the durable half is
  the reverse-direction assertion, and it is where the design work in this block sits.

  **The block's central premise, as written above, is false, and D1 reverses it.** §3.6
  records that "three independent sweeps produced 33, 36 and 36 consumed names", and
  concludes from that a regex sweep "is inherently approximate". That dispersion is a
  property of **regex**, not of coverage: a line-anchored pattern cannot see
  `env(\n    "EMAIL_BACKEND",\n ...)`, which is why the low count misses `EMAIL_BACKEND`,
  `DEFAULT_FROM_EMAIL` and `SUPPORT_NOTIFICATION_RECIPIENTS` — all three of which are
  multi-line calls. An `ast.NodeVisitor` over the same tree returns a single, stable
  answer: 36 names, zero false positives, 0.4 s. The ecosystem is unanimous on this — the
  env-variable scanners this mechanism is usually compared against (`env-finder`,
  `envsleuth`, `envcheck-sync`, `envsniff`) all use `ast.NodeVisitor`, not regex.

  The decisive argument is not elegance, it is coverage. **Option B — §3.6's own
  recommendation — would not have caught CFG-008.** Its automated half sweeps only the
  settings package, which contains 35 of the 36 names; the one it drops is precisely
  `RUN_TRANSLATION_BACKFILL`, read from `apps/core/utils/migrate_locked.py`, a file
  outside that package. So Option B could only have closed this finding through the
  hand-maintained constant it also proposes — and that constant is the exact anti-pattern
  BLOCK 4's shipped docstring (`test_deploy_check_env_parity.py`) argues against in
  detail: a contract asserted in one place and verified nowhere, one level down. D1
  therefore takes the full-tree AST scan and adds **no new production constant**.

  The second half of the block is CFG-009. `.env.example` is titled "Comprehensive", is
  not comprehensive, and is not authoritative: no compose file, script or Makefile target
  reads it, and the three tier templates are what an operator actually copies. The
  finding's *harm* is concrete and was reproduced by the report: an operator copies what
  the file calls itself, and the resulting `.env.prod` fails to boot on `EMAIL_HOST`, a
  variable they were never shown. VAL-003 forbids the deletion branch, and G6 fixes the
  two keys the retitled stub must keep (`CSRF_TRUSTED_ORIGINS=`, `SENTRY_DSN=` — both
  pinned by shipped green substring tests). D2 and D3 fix the resulting shape.

  **What the block deliberately does not do.** It does not assert that consumed ⊆
  template keys. That is the Researcher's option F, it is deferred (D7), and the reason
  it is deferred is a consequence of D3: the two names that would have to be exempted —
  `DATABASE_URL` and the two bootstrap flags — are exactly the three cases the operator
  is told about in prose in the templates themselves, and turning prose into a
  machine-readable exemption list would rebuild the anti-pattern this block exists to
  remove.

goals:
  - >
    `RUN_TRANSLATION_BACKFILL` is in `ALLOWED_ENV_VARS`, in the Python-consumed group,
    and the group's parenthetical comment is amended **in the same edit** so the
    grouping does not contradict the read it now covers.
  - >
    A hard-failing test derives the consumed set from the source tree by AST and asserts
    `consumed ⊆ ALLOWED_ENV_VARS`, over **all** non-test `src/**/*.py` — not the settings
    package. The one-name allowlist change is not enough on its own; the test is the
    durable half and it is what would catch the next instance.
  - >
    That test is **seen red** on the real defect before it is seen green, and the
    red demonstration runs the full-tree scan, because a settings-only demonstration
    passes vacuously.
  - >
    An unrecognised read shape is **loud**, not silent. The scan knows the four read
    shapes in use, handles django-environ's zero-argument helpers explicitly, and fails
    on any `env`-ish call it cannot attribute to a variable name.
  - >
    `.env.example` no longer claims to be comprehensive, no longer carries a UTF-8 BOM,
    states that the tier templates are authoritative, keeps the existing "copy one of the
    three" instructions verbatim, and keeps `CSRF_TRUSTED_ORIGINS=` and `SENTRY_DSN=`.
  - >
    The `Email / SMTP` block an operator needs to produce a booting `.env.prod` is
    present in the stub, and every consumed variable that is deliberately absent from it
    is named in prose with the reason — without a second hand-maintained exemption list.
  - >
    `RUN_TRANSLATION_BACKFILL` is documented in `.env.prod.example` in a new section, so
    an operator following the migration workflow finds it where they look.
  - >
    No new production constant, no new dependency, no new CI job, no settings-module
    body change, no compose or shell change, no user-visible string, and no file under
    `.ai/audit/**` touched.

# ─────────────────────────────────────────────────────────────────────────────
# Decisions taken by the BLOCK 6 Planner
# ─────────────────────────────────────────────────────────────────────────────
decisions:
  - id: "D1 — G8: Option E. An AST scan over the whole non-test src tree, and NO new production constant."
    choice: >
      The reverse-direction mechanism is a new test module containing an
      `ast.NodeVisitor` that walks every non-test `src/**/*.py` file, collects the
      environment-variable names the code reads, and asserts
      `consumed_set ⊆ ALLOWED_ENV_VARS`. It reads `ALLOWED_ENV_VARS` from `base.py` and
      **introduces no second constant**: there is no curated consumed-name list, and
      nothing new in production code at all.
    rationale: >
      Three reasons, in order of weight.

      **(1) Option B cannot catch the finding it was recommended to catch.** Its
      automated half is a settings-package sweep. Measured at the anchor, the settings
      package holds 35 of the 36 consumed names; the 36th, `RUN_TRANSLATION_BACKFILL`, is
      read from `apps/core/utils/migrate_locked.py`. A settings-only scan of the current
      tree passes vacuously against the current defect. Option B could therefore only
      have closed CFG-008 through its hand-maintained constant — and that constant is
      exactly the "contract asserted in one place and verified nowhere" pattern that
      BLOCK 4's shipped docstring rejects and that VAL-004 names as the phase's
      anti-pattern. Choosing B would have reproduced the anti-pattern inside the block
      written to end it.

      **(2) The 33/36/36 dispersion is a regex artefact, not evidence of
      approximation.** This Planner re-ran the sweep by AST over the same 337 files: 36
      names, zero false positives, ≈0.3 s, one stable answer. The report's low-count sweep
      misses exactly the three variables whose reads are split across lines
      (`EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL`, `SUPPORT_NOTIFICATION_RECIPIENTS`), all
      written as `env(\n    "NAME",\n ...)`. That is a defect of line-anchored matching,
      and it is the whole of the disagreement. The report's own stated con — "a false
      positive disables the test within a week" — does not apply: the AST walk has no
      false positives today because a variable name is a `Constant` node, not a regex
      capture, and the scan cannot see a name unless the code passes one.

      **(3) The four channels the Researcher was asked about are separable, and only one
      of them is automatable cheaply.** Shell (`docker/*.sh`), compose interpolation and
      the `deploy-check` env block are text channels with their own syntaxes; BLOCK 4
      already owns the `deploy-check` one and phase 01 owns compose rendering. Bolting
      them onto this test would make one module that asserts three unrelated contracts —
      the coupling the phase's own rule about single responsibility forbids. The Python
      channel is asserted here; the others are stated as out of scope in
      `acceptance_criteria` rather than half-covered.
    rejected:
      - "Option A (regex sweep) — measured noise, and the objection is an artefact of the matcher, not of the scope. Rejected."
      - "Option B (curated constant) — its automated half is blind to the finding; the rest duplicates BLOCK 4's rejected anti-pattern. Rejected."
      - "Option C (skip) — leaves VAL-004 instance (c) open and the anti-pattern unguarded. Rejected."
      - "Option D (AST alone, no template half) — the template half is what stops `.env.example` regressing to a false completeness claim, and it is the half that carries the finding's actual harm. Superseded by E."
      - "Option F (execution-derived required set ⊆ template) — deferred. See D7 and `recorded_follow_ups`."
    consequence: >
      The red/green demonstration in `tests.must_be_demonstrated_red` **must** remove
      `RUN_TRANSLATION_BACKFILL` from `ALLOWED_ENV_VARS` and run the new module. A
      demonstration that pointed the scan at the settings package would pass vacuously
      and would prove nothing; the sequence step that runs it says so explicitly.

  - id: "D2 — .env.example is a cross-tier stub with the Email/SMTP block added, not a completeness list."
    choice: >
      The file keeps its existing body and gains three things. **(a)** A retitled header
      that drops "Comprehensive", states that the three tier templates are the
      authoritative ones, and **keeps the existing `cp .env.<tier>.example .env.<tier>`
      instructions verbatim** — the retitle reinforces them rather than competing with
      them. **(b)** The whole `Email / SMTP` block, added after the `Telegram Bot` section
      so it sits in the same relative position it occupies in `.env.prod.example`:
      `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
      `EMAIL_USE_TLS`, `EMAIL_TIMEOUT`, `DEFAULT_FROM_EMAIL` and
      `SUPPORT_NOTIFICATION_RECIPIENTS`, with non-secret placeholder or empty values
      matching the file's existing convention. `EMAIL_BACKEND` is **not** given a key
      line — see D3. **(c)** `POSTGRES_HOST=db` added to the existing `PostgreSQL Database`
      section, which currently ships `POSTGRES_USER` / `POSTGRES_DB` /
      `POSTGRES_PASSWORD` but omits the host its own comment names. Plus the BOM removal,
      and one new prose block near the end listing the consumed variables that are
      deliberately **not** in the stub, each with the reason.
    rationale: >
      The finding's harm is reproduced in the report and is specific: the operator produces
      a `.env.prod` that fails to boot on `EMAIL_HOST`. A stub that is honest about being
      a stub and *still* carries the block that causes the boot failure has not been
      fixed — it has been relabelled. So the `Email / SMTP` block is added rather than
      pointed at. What is **not** added is everything whose absence cannot fail a boot and
      whose presence in a secret file would mislead: the container-path liveness and
      timeout knobs, and the two process-environment flags. Those get the prose
      treatment, which is what the report itself offers ("Add the missing blocks, **or**
      mark each as 'see .env.<tier>.example'").

      `POSTGRES_HOST` is added because it is the same class as the three keys already in
      that section and its absence is an oversight, not a decision — `.env.dev.example`
      and `.env.prod.example` both already ship `POSTGRES_HOST=db`.

      The retitle cannot contradict "copy one of the three" because those three lines are
      the operative instruction and they stay. What changes is only the claim about what
      this file *is*.
    must_retain:
      - "`CSRF_TRUSTED_ORIGINS=` and `SENTRY_DSN=` as live key lines (G6, VAL-003). `test_csrf_trusted_origins_in_example` and `test_sentry_dsn_in_env_examples` assert them by substring; a commented line also satisfies both, so a human must confirm they are real keys, not comments. The Implementor re-reads both lines after the edit."
      - "The three `cp .env.<tier>.example .env.<tier>` instruction lines, byte-identical."
      - "The existing 'All .env.* files are gitignored. These .example templates are tracked in git.' sentence."
    not_added:
      - "`EMAIL_BACKEND` — D3."
      - "`DATABASE_URL` — D3; the file's existing `PostgreSQL Database` prose already forbids it and that prose stays."
      - "`DJANGO_BUILD`, `DJANGO_ONESHOT`, `DJANGO_SETTINGS_MODULE` — D3."
      - "`BOT_LIVENESS_FILE`, `BOT_HEALTH_STALE_SECONDS`, `BOT_HEALTH_CHECK_ENABLED`, `SCHEDULER_LIVENESS_FILE`, `SCHEDULER_COMMAND_TIMEOUT`, `SCHEDULER_HEALTH_STALE_SECONDS` — container-path and container-tuning values with working defaults in `base.py` and in the compose files. Naming an operator copy of `BOT_LIVENESS_FILE=/tmp/...` is worse than omitting it. Prose only."
      - "`SCHEDULER_HEALTH_STALE_SECONDS` in particular — the report's original single shell-only finding. It stays prose-only in the stub and stays allowlisted, which is what `test_scheduler_health_stale_seconds_allowlisted` requires."

  - id: "D3 — The template scope rule is derivable, and it is one sentence. No second exemption list is built."
    choice: >
      **A variable appears as a `KEY=` line in a template if and only if the operator
      must type its value into that file by hand to obtain a working deployment in that
      tier. Everything else is either absent, or named in prose with the reason.**
    rationale: >
      The three exclusions the block's own notes stumble over fall out of the rule instead
      of needing a list:

      - **`DATABASE_URL`** is constructed by Docker Compose from `POSTGRES_*`, so the
        operator never types it. `.env.example`, `.env.dev.example` and
        `.env.prod.example` already say exactly this in prose; D2 keeps that prose and
        adds nothing. This is also the one exclusion that cannot be relaxed — putting
        `DATABASE_URL` in a secret file makes the compose-constructed value and the file
        value disagree, which is the class of bug `test_compose_contract.py` exists to
        catch.
      - **`DJANGO_BUILD` and `DJANGO_ONESHOT`** are honoured only from the process
        environment, never from a file, and a shipped test
        (`test_bypass_flags_absent_from_env_templates`) asserts their absence from every
        tracked template. They are not mentioned in prose either: naming a
        guard-disabling flag in a secret template is how it ends up in one.
      - **`EMAIL_BACKEND`** is pinned per tier by the settings modules — `dev.py` and
        `test.py` set a console/locmem backend and `prod.py` re-pins it unconditionally
        (BLOCK 7). Nobody types it, so by the rule it gets no key line. **This is also
        forward-compatible:** adding `EMAIL_BACKEND=` to a template now would document a
        knob BLOCK 7 is about to make un-settable in production.

      The rule is a property of the deployment, not of a list someone maintains, which is
      what makes it safe to leave in a template that will be edited again. The block
      asserts the rule's *outward* consequence only where a shipped test already does —
      `test_example_keys_in_allowlist` (template → allowlist). It adds **no** assertion in
      the other direction; that is the deferred option F.
    corollary: >
      Because the rule is a sentence and not a list, there is nothing to go stale. A
      future variable that fails the "operator types it" test needs no exemption entry; it
      simply does not get a key line. A future variable that passes it gets one, and
      `test_example_keys_in_allowlist` is what tells the author to add it to
      `ALLOWED_ENV_VARS`.

  - id: "D4 — A separate test module; a plain `# env-contract:` comment as the escape hatch, not `# noqa`; and the visitor asserts its own shape coverage."
    choice: >
      **Placement.** A new module,
      `src/backend/config/settings/tests/test_env_allowlist_reverse.py`, not an addition
      to `test_env_allowlist.py`. **Escape hatch.** A per-line
      `# env-contract: <reason>` comment, matched by the scanner on the same physical
      line — **not** a `# noqa` directive. **Shape coverage.** Yes: the visitor records
      which read shapes it recognised, and one test fails on any `env`-ish call it could
      not attribute to a name, plus asserts that each shape the module documents was
      actually exercised.
    rationale: >
      **Placement.** `test_env_allowlist.py` is 109 lines of small, one-directional
      assertions over a hand-written frozenset; its whole value is being readable at a
      glance. Adding an `ast` visitor, a filesystem walk and an encoding-tolerant reader
      changes what the file *is*, and the new module's failure mode is categorically
      different (a set difference across a source tree, not a frozenset comparison). The
      two also differ in what they must not be confused with: this module derives a fact
      about the source tree and compares it to the allowlist; the old module compares a
      template to the allowlist. Different subjects, different remedies. BLOCK 4 set the
      same precedent for the same reason. The new module lives in the same package so it
      inherits the existing `pytestmark` convention and the existing `_ROOT` walk-up
      idiom — it must not invent a second one.

      **Escape hatch — reconciled with ruff and bandit, by measurement, not by
      assumption.** A bare `# noqa: env-contract` **fails on this project's ruff**:
      `uv run ruff check` on a probe file emits
      `warning: Invalid '# noqa' directive ... expected a comma-separated list of codes`.
      Registering the code under `[tool.ruff.lint.external]` does not help — ruff 0.16
      rejects that key in the configuration shapes available here, and adding a lint
      configuration key for a test-only escape hatch is over-engineering by the project's
      own rule 5. The mixed form `# noqa: E501, env-contract` does parse, but it attaches
      a real lint code to a suppression that has nothing to do with E501, which is a
      small lie in a file a reviewer will read. A **plain comment** marker is inert to
      ruff (verified: no diagnostic), inert to bandit (which does not read `# noqa` at
      all), greppable, self-documenting, and honoured by exactly the one tool that
      defines it. The escape hatch is **unused today** — the module docstring says so, and
      `acceptance_criteria` requires the Implementor to report the count — but it is
      **proven** by a synthetic-source test, so it is not untested machinery.

      **Shape coverage — this is the part that would otherwise be silent.** Three
      specific hazards, all measured at the anchor: (i) `env.db()` takes **no
      positional argument** and implicitly reads `DATABASE_URL`, so a visitor that only
      inspects `args[0]` is green and wrong — the single most likely silent failure of
      this whole design, and it is invisible without a test; (ii) `base.py` reads
      `set(os.environ)` twice, which is a *name-set* read of every variable and must be
      **excluded**, or the scan would report every key in the environment; (iii) a future
      zero-argument helper (`env.cache()`, `env.json()`, …) would be silently missed. The
      design answer to all three is the same: the scanner holds an explicit table of
      django-environ helpers whose variable name is **not** in `args[0]`, and **any
      other** `env.<attr>()` call with no positional argument is recorded as
      *unrecognised*, which fails the test by name, file and line. A new read shape is
      then a red test, not a smaller number.
    forbidden:
      - "A hand-maintained consumed-name constant in `config/settings/` (D1). The new module defines no frozenset of variable names."
      - "Any `os.environ` read that is not a `get`, a subscript, or an explicit
         `set(...)` name-set comparison. In particular `_env_keys_before = set(os.environ)`
         in `base.py` must not be treated as a read of every variable."
      - "`import re` for the name scan. The scan is structural; a regex would reintroduce exactly the failure §3.6 documents."
      - "Importing `_example_keys` from `test_env_allowlist.py`. The two modules assert opposite directions of the same contract and share no helper."

  - id: "D5 — The non-test exclusion is by PATH COMPONENT. `test_migrations.py` is therefore IN scope, and that is correct."
    choice: >
      A file is scanned if and only if it is a `.py` file under `src/` and **no component
      of its path relative to `src/` is exactly `tests`**. Filename patterns play no part
      in the decision. `config/settings/test_migrations.py` is consequently **scanned**,
      and `config/settings/tests/**` is consequently **not**.
    rationale: >
      The Auditor flagged that a naive `test_*` filename classifier mis-buckets
      `config/settings/test_migrations.py`. It does, and the file is in scope, and that is
      the correct classification rather than an accident to be tolerated: it is a Django
      settings module, loaded by `apps/core/tests/test_migrations.py` in a subprocess with
      `MIGRATION_MODULES` re-enabled and a dedicated test database. It is production
      settings code whose only resemblance to a test is its filename, and a settings
      module is exactly where a new `env()` read would be added. Excluding it by name
      would be a rule that is wrong today and wrong in the direction that matters.

      It is harmless today, and the harmlessness is measured rather than assumed: the file
      contains no environment read of any shape; its variables come from
      `from .test import *`, which re-exports `test.py`, which imports `base.py`. The
      scan therefore attributes the reads to the modules that make them, which is the
      behaviour a reader wants in a failure message.

      Substring matching is rejected outright, and this is not hypothetical: a
      `if "test" not in str(path)` rule excludes any path containing that sequence, which
      is how a module such as `protest_handler.py` — the Researcher's worked example — is
      silently dropped from a contract test, with no failure anywhere. Component
      equality cannot do that.

      Two consequences the Implementor must not "tidy": the `testing/` package
      (`src/backend/testing/`, three files, imported only by the i18n test suites) and
      `src/backend/conftest.py` are **in** scope by this rule, because neither lives under
      a `tests` component. Both are verified to contain no environment read today, so
      including them is correct-by-rule and harmless. If one of them ever grows a read
      that is genuinely not a deployment variable, the escape hatch from D4 is the
      mechanism — and it must be used visibly, not by narrowing the rule.
    related_known_quirk: >
      `pyproject.toml` sets `python_files = ["tests.py", "test_*.py"]` with
      `testpaths = ["src/backend", "src/telegram_bot"]`, so pytest **does** collect
      `config/settings/test_migrations.py` as a test module and imports it during
      collection. That is a pre-existing quirk with no test functions in the file, it is
      unrelated to this block, and it is **not** fixed here. It is recorded so that
      nobody "corrects" the scanner by aligning it with pytest's collection rule, and so
      nobody reads the scan scope as a claim about what pytest collects.

  - id: "D6 — The 13 non-Python-read allowlist entries get no new inline annotations; the asymmetry is documented once, in the test module."
    choice: >
      `ALLOWED_ENV_VARS` grows by exactly one entry. No member of the shell/compose group
      gets an inline annotation, and `base.py` gains no second comment block. The
      asymmetry is stated once, in the new test module's docstring, with
      `SCHEDULER_HEALTH_STALE_SECONDS` named as the worked example.
    rationale: >
      At the anchor the allowlist is 48 entries and the tree consumes 36, so **13**
      allowlist entries have no Python read. Every one of them is real: they are read by
      shell scripts, by compose interpolation, or injected by the test container, and
      `test_scheduler_health_stale_seconds_allowlisted` already pins the least obvious
      member. Announcing this thirteen times inside the constant would put a maintenance
      burden on the production file to communicate something that is true of the constant
      as a whole. One statement, in the module whose contract it explains, is both
      shorter and harder to misread.

      This is the same "asymmetry" the Researcher identified, and it is the honest
      boundary of D1: **only the forward direction is asserted.** Asserting the reverse —
      every allowlist entry must be read somewhere in Python — would be false by
      construction and would be the second hand-maintained contract D1 refuses to build.
      The docstring says so in those terms, so the next reader does not have to
      rediscover it.

  - id: "D7 — The option-F deferral is recorded here, inside the block, and nowhere else this Planner may write."
    choice: >
      Deferred: asserting that a variable the code actually **requires** appears in the
      template that tier uses. Recorded in `recorded_follow_ups` in this task and in the
      `acceptance_criteria` coverage-boundary sentence, and **not** written into §5 or §6
      of this plan, because this Planner is permitted to append to the BLOCK 6 section
      only.
    rationale: >
      The Researcher's assessment — overweight for a LOW finding, and it would require
      either an execution-derived required-set (a second contract, and one derived from
      live behaviour rather than from the source) or an exemption list (D3 forbids) — is
      accepted. But the deferral is a *known* gap, not a non-issue, and CFG-009's harm
      ("the operator was never shown `EMAIL_HOST`") is exactly the class it would close.
      It is therefore recorded as a named follow-up with the reason, so a future block
      picks it up deliberately rather than rediscovering it.
    handed_to: >
      The coordinator. Folding this entry into the plan's §5.2 "documented follow-ups"
      or §6 "Stale report claims" is a one-line edit **by main**, not by this Planner.

# ─────────────────────────────────────────────────────────────────────────────
corrections_to_block_notes:
  - >
    **The clobber hazard in "Risk / rollback" is void.** It warns that this block "touches
    a documentation file that is already modified in the working tree" (`docs/99-agent/rules.md`,
    `docs/ops/docker-deployment.md`). Both files are **clean** at `6413df5`. The working
    tree has **zero modified tracked files**; it is dirty only by the 19 `.ai/audit/**`
    deletions and by untracked `.ai/plans/*`, `.ai/tmp/` and `staticfiles/`. Neither
    documentation file is in this block's surface. `docs/99-agent/architecture.md` and
    `docs/ops/migration-workflow.md` are also clean (BLOCK 3 committed them). The §1
    staging rule still applies — explicit paths only, never `git add -A` — but there is
    nothing to coordinate this time.
  - >
    **Note 1's "six tracked documentation files" is five.** Re-measured across
    `docs/**`: `docs/01-spec/architecture-structure.md`, `docs/99-agent/architecture.md`,
    `docs/ops/docker-deployment.md`, `docs/ops/migration-workflow.md` and
    `docs/99-agent/VERIFY_TESTS_INSTRUCTIONS.md` — plus the `migrate_locked.py` module and
    `_build_steps` docstrings. Do not transcribe a count; grep immediately before editing.
  - >
    **Note 1's "the migrate notes in `.env.prod.example`" do not exist.** There is no
    migrate-notes section in that file. A new section must be **created** — see
    `change_prod_example_migrate_section`, which places it by semantic anchor (after the
    `Container runtime` block, before the `Prometheus Metrics` block), never by line
    number.
  - >
    **Note 2 is incomplete and note 8 is stale in the opposite direction.** The BOM is
    real on `.env.example` only. `.env.prod.example` and `.env.test.example` are **not
    valid UTF-8** — they carry four CP1252 `0x97` em dashes between other bytes — so any
    test that reads them must pass `errors="replace"` or `errors="ignore"`, and any edit
    that appends to them must write bytes, not a decoded string. The new prose test
    encodes this. Conversely, note 8's clobber warning does not apply (see above).
  - >
    **Note 8's counts must be re-derived, and the tree disagrees with the report in both
    directions.** Measured: `.env.example` has 26 keys and omits 21 consumed names
    (18 real + `DJANGO_BUILD`, `DJANGO_ONESHOT`, `DJANGO_SETTINGS_MODULE`, which must
    stay out); `.env.prod.example` has 33 keys and omits 8. The report's "19" for
    `.env.example` reconciles only once the shell-only `SCHEDULER_HEALTH_STALE_SECONDS`
    is added back to the 18. The Implementor re-derives; nothing here is transcribed.
  - >
    **Note 5's clobber prediction resolves as follows.** `docs/01-spec/architecture-structure.md`'s
    bare repository-structure listing still names `.env.example` and does **not** become
    stale — the file survives. `docs/99-agent/architecture.md`'s `.env.*` note ("The
    `.env.*` files are gitignored ... `.env.example`, `.env.dev.example`,
    `.env.test.example`, and `.env.prod.example` are the tracked templates to copy from")
    **does** become stale, because after D2 the first of those four is not one you copy
    from. That is the only documentation edit in the block —
    `change_architecture_doc_env_note`.
  - >
    **§3.6's Option B con — "sweep only the settings modules ... a small, stable,
    high-signal surface" — is the finding.** The settings package does not contain
    `RUN_TRANSLATION_BACKFILL`. See D1.
  - >
    **The `ALLOWED_ENV_VARS` group comment is BLOCK 3's, but the parenthetical becomes
    false in this change.** It currently reads "Python-consumed (env()/env.*()/os.getenv
    in base.py & prod.py)". `RUN_TRANSLATION_BACKFILL` is read in
    `apps/core/utils/migrate_locked.py`, so the comment must be amended in the same edit
    or the grouping self-contradicts on the day it is created. Only the parenthetical is
    touched; the group ordering, the two other group comments and every other entry are
    byte-identical.

recorded_follow_ups:
  - >
    **Deferred option F — required variables must be discoverable in the template that
    tier uses.** CFG-009's reproduced harm is that the stub never showed `EMAIL_HOST`, and
    D2 fixes it by adding the block. What is not fixed is the general form: nothing
    asserts that a variable the code *requires* in a tier appears in that tier's template.
    Two shapes were considered and both are rejected here: an execution-derived required
    set (a second contract, derived from live behaviour rather than from the source) and
    an exemption list (D3). The natural home is a future block, at LOW priority, and it
    should be picked up together with any future work on `docs/ops/docker-deployment.md`'s
    enumerated-variable list. The coordinator should fold this entry into §5.2 of the
    plan; this Planner appends to BLOCK 6 only.
  - >
    **`SCHEDULER_HEALTH_STALE_SECONDS` is allowlisted but has no Python read.** It is read
    by `docker/healthcheck-scheduler.sh` and set by `docker-compose.prod.yml`. The
    existing `test_scheduler_health_stale_seconds_allowlisted` documents the asymmetry in
    two lines, which is the right amount. It is named again in the new module's docstring
    only because the new module is where a reader will ask the question. No new test, no
    new constant.
  - >
    **The real `.env.prod` in this working tree is missing 12 of the same names,
    `EMAIL_HOST` among them.** Unchanged from the block's own note 6, re-confirmed: it is
    a gitignored operator file and is out of scope. The Validator notes it; nobody fixes
    it as part of phase 02.

# ─────────────────────────────────────────────────────────────────────────────
files:

  - path: src/backend/config/settings/base.py
    targets:
      - type: constant
        name: ALLOWED_ENV_VARS
      - type: comment_block
        name: "the group comment above the Python-consumed group of ALLOWED_ENV_VARS"
    semantic_anchors:
      change: >
        **Exactly one entry added**: `"RUN_TRANSLATION_BACKFILL"`, placed at the end of
        the Python-consumed group, after `"SUPPORT_NOTIFICATION_RECIPIENTS"`.
      amend: >
        **Exactly one comment amended in the same edit**: the Python-consumed group's
        parenthetical, currently "(in base.py & prod.py)". It must name the third
        location, because the entry being added is read there. Amending it later is not
        acceptable — the grouping would contradict itself from the moment the entry lands.
      do_not_edit:
        - "The group ordering and the group-boundary comments for the bootstrap control flags and the shell/compose group"
        - "The three individual bootstrap-flag comments (DJANGO_BUILD, DJANGO_ONESHOT, POSTGRES_* device note)"
        - "Every other entry, byte-identical"
        - "The `env = environ.Env(...)` construction, the `read_env()` branch, `_warn_unknown_env_vars` and everything else in the module"
        - "Any settings value, guard or setting name"
      note: >
        BLOCK 3 wrote the grouping. BLOCK 6 adds one member and fixes one comment. The
        `frozenset(env(...))` wrapper, the trailing-comma style and the surrounding
        indentation stay exactly as they are.

  - path: src/backend/config/settings/tests/test_env_allowlist_reverse.py
    status: new
    targets:
      - type: module
        name: test_env_allowlist_reverse
      - type: module_docstring
        name: "what the reverse direction is, and the asymmetry it deliberately does not assert"
      - type: constant
        name: _SRC_ROOT
      - type: constant
        name: _EXCLUDED_PATH_COMPONENTS
      - type: constant
        name: _ENV_CALLABLE_NAMES
      - type: constant
        name: _IMPLICIT_VAR_HELPERS
      - type: constant
        name: _OPT_OUT_MARKER
      - type: class
        name: _EnvReadVisitor
      - type: helper
        name: _iter_source_files
      - type: helper
        name: _scan_source
      - type: helper
        name: _consumed_env_vars
      - type: function
        name: test_consumed_env_vars_are_allowlisted
      - type: function
        name: test_env_read_shapes_are_all_recognised
      - type: function
        name: test_env_scan_covers_more_than_the_settings_package
      - type: function
        name: test_env_contract_opt_out_is_honoured
      - type: function
        name: test_env_example_points_at_the_tier_templates
      - type: function
        name: test_env_prod_example_documents_translation_backfill
    semantic_anchors:
      resolve_root: >
        Walk up from `Path(__file__).resolve().parent` until the directory containing
        `pyproject.toml` is found — the existing `_ROOT` convention, spelled identically
        by `test_prod_logging.py`, `test_csrf_trusted_origins.py`, `test_env_allowlist.py`
        and `test_deploy_check_env_parity.py`. Do not invent a second shape. The source
        root is that directory's `src/`; it is derived, never hard-coded as a relative
        path from the repository root.
      import_from: >
        `ast`, `pathlib.Path`, `pytest`, and
        `from config.settings.base import ALLOWED_ENV_VARS`. Nothing else — no
        `re`, no `django.conf`, no subprocess, no environment fixture.
      markers: "pytestmark = [pytest.mark.unit, pytest.mark.settings] — the package's existing value"
      must_not_contain:
        - "a frozenset or tuple of variable names that is not one of the four constants above"
        - "import re"
        - "`ast.walk()` without an `isinstance` guard before every attribute read — `AST` declares no `.args` / `.func` / `.value`. Prefer the `NodeVisitor` subclass, which narrows for free"
        - "a bare `node.args` / `node.func` / `node.value` on a node whose concrete type has not been narrowed"
        - "any subprocess call, any prod-env builder, any string literal resembling a credential"
        - "pytest.skip / skipif / xfail / a known-exceptions list"
        - "an import of `_example_keys` or of any helper from `test_env_allowlist.py`"
        - "a read of the real `.env.*` files (key names and tracked `.example` templates only)"

  - path: .env.example
    targets:
      - type: comment_block
        name: "the header block: title line and the copy-one-of-the-three instructions"
      - type: section
        name: "the PostgreSQL Database section"
      - type: section
        name: "the Telegram Bot section (the Email / SMTP block is inserted after it)"
      - type: comment_block
        name: "the new trailing block naming the consumed variables deliberately absent from this stub"
    semantic_anchors:
      encoding: >
        **The file currently begins with a UTF-8 BOM (`EF BB BF`).** The rewritten file
        must be plain UTF-8 with **no BOM**, and the trailing prose block must be appended
        in a way that does not reintroduce one. The block's own `# ======================`
        section style is already established in the file — match it, do not invent a
        format.
      retain_byte_identical:
        - "the three `cp .env.<tier>.example .env.<tier>` instruction lines"
        - "`CSRF_TRUSTED_ORIGINS=` and `SENTRY_DSN=` as live, uncommented key lines"
        - "the `PostgreSQL Database` section's existing `DO NOT set DATABASE_URL in Docker environments.` prose"
        - "every other existing key and its comment"
      do_not_add:
        - "`EMAIL_BACKEND`, `DATABASE_URL`, `DJANGO_BUILD`, `DJANGO_ONESHOT`, `DJANGO_SETTINGS_MODULE` (D3)"
        - "any liveness-file, health-stale or command-timeout key (D2)"
        - "any real or plausible-looking credential. Placeholders only; `.env.*.example` paths are gitleaks-allowlisted, but the allowlist is a path allowance, not a licence to write a real value"

  - path: .env.prod.example
    targets:
      - type: section
        name: "the Container runtime section"
      - type: section
        name: "the Prometheus Metrics section"
    semantic_anchors:
      change: >
        Insert a new **"Migration bootstrap"** section carrying a documented
        `RUN_TRANSLATION_BACKFILL` entry, positioned **between the `Container runtime`
        block and the `Prometheus Metrics` block**. Anchor semantically: it belongs with
        the other one-shot container-runtime controls, and `Prometheus Metrics` is the
        last block in the file.
      entry_form: >
        The entry ships **commented out** with the value spelled out
        (`# RUN_TRANSLATION_BACKFILL=true`), together with prose saying that the migrate
        one-shot appends the optional `backfill_translations` step **only** when the value
        is exactly `true`, that the step runs inside the same advisory lock as the rest of
        the sequence, and that it is a one-time operator action to be removed afterwards.
        The comparison in `migrate_locked._build_steps` is `== "true"`, so a live empty
        key would be misleading rather than harmless, and a live `=true` key would switch
        the backfill on in every deployment that copies the template. **Commented is the
        only correct form.**
      encoding: >
        **This file is not valid UTF-8.** It contains four CP1252 `0x97` em-dash bytes.
        Edit it as **bytes**, appending only ASCII, and never re-encode the existing
        content. A round-trip through `read_text()`/`write_text()` would corrupt the file
        or silently change its encoding, and any test that reads it must pass
        `errors="replace"`.
      do_not_edit:
        - "the existing `DO NOT include DATABASE_URL` prose"
        - "every existing key, its value and its comment"
        - "the `Email / SMTP` section, including `EMAIL_HOST` and its REQUIRED comment"
        - "the `Admin User`, `Seed` and `Container image` sections"

  - path: docs/99-agent/architecture.md
    targets:
      - type: paragraph
        name: "the note stating that .env.* files are gitignored and naming the four tracked .example templates"
    semantic_anchors:
      change: >
        One sentence, amended in place. The note currently ends by calling all four
        "the tracked templates to copy from". After D2, `.env.example` is a cross-tier
        reference stub, not a template to copy from; the three tier files are. The
        amendment says which is which, in one sentence, and changes nothing else in the
        paragraph. The file's repository-structure listing is not in this file and is not
        touched by this change.
      do_not_edit:
        - "any other paragraph of the file"
        - "any code block or table"
      note: >
        `docs/99-agent/architecture.md` was last committed by BLOCK 3 and is clean at the
        anchor. Re-read it immediately before editing anyway (§1: the tree was changing
        during planning).

  # ── Explicitly not touched. Named so the Implementor does not "improve" them. ──
  - path: src/backend/config/settings/tests/test_env_allowlist.py
    status: not_touched
    note: >
      `test_example_keys_in_allowlist` (×4), `test_python_consumed_vars_in_allowlist`,
      `test_scheduler_health_stale_seconds_allowlisted`, `test_unknown_env_var_logs_warning`,
      `test_known_env_vars_no_warning` and `test_bypass_flags_absent_from_env_templates`
      (×2) all live here and all must keep passing **unchanged**. It is not edited, not
      extended, and not used as the host for the new scan (D4).
  - path: src/backend/config/settings/tests/test_deploy_check_env_parity.py
    status: not_touched
    note: >
      BLOCK 4's module and VAL-004 instance (b). Its docstring argues against a
      hand-maintained required-variable constant; D1 refuses to introduce one here
      precisely on that argument. A different contract is compatible; merging them,
      importing from it, or editing its constants is not.
  - path: docs/01-spec/architecture-structure.md
    status: not_touched
    note: "the bare repository-structure listing names the file, which survives the retitle; nothing about it changes"
  - path: docs/99-agent/rules.md
    status: not_touched
    note: "the block's clobber hazard named this file; it is clean at the anchor and is not in the block's surface"
  - path: docs/ops/docker-deployment.md
    status: not_touched
    note: "same — clean, and not in the block's surface. BLOCK 5 committed it."
  - path: docs/ops/migration-workflow.md
    status: not_touched
    note: >
      Already documents `RUN_TRANSLATION_BACKFILL` in five places and is correct. The
      block adds a template entry, not a documentation change; editing the workflow doc
      would be scope creep.
  - path: docker
    status: not_touched
    note: "the shell channel is out of scope (D1, acceptance_criteria). No `healthcheck-*.sh` or `entrypoint-*.sh` edit."
  - path: .github/workflows/ci.yml
    status: not_touched
    note: "the `deploy-check` env block is BLOCK 4's contract. BLOCK 5 already added `BOT_USERNAME` there."
  - path: pyproject.toml
    status: not_touched
    note: "no new marker, no ruff or pytest configuration change — D4's escape hatch is a plain comment precisely so that none is needed."
  - path: .gitleaks.toml
    status: not_touched
    note: "`.env.*.example` is already allowlisted by path; the block adds placeholders only, so no allowlist edit is required or wanted."

# ─────────────────────────────────────────────────────────────────────────────
changes:

  - action: edit_constant
    id: change_allowlist_entry
    path: src/backend/config/settings/base.py
    depends_on: [change_allowlist_group_comment]
    description: >
      Add `"RUN_TRANSLATION_BACKFILL"` to `ALLOWED_ENV_VARS`, at the end of the
      Python-consumed group. This is the finding's own one-line fix and it is the *only*
      production-code change in the block.

      It is deliberately the **only** production change. The reverse-direction guarantee
      comes entirely from the test (D1), which is what makes the test load-bearing rather
      than decorative: if the next variable is read without being allowlisted, the test
      catches it, and no human has to remember.
    code_hint: |
      # --- Python-consumed (env()/env.*()/os.getenv in base.py, prod.py and
      #     apps/core/utils/migrate_locked.py) ---
      ...
      "EMAIL_USE_TLS", "EMAIL_TIMEOUT", "EMAIL_BACKEND",
      "DEFAULT_FROM_EMAIL", "SUPPORT_NOTIFICATION_RECIPIENTS",
      "RUN_TRANSLATION_BACKFILL",
    note: >
      **The `depends_on` above is load-bearing in the opposite direction too:** the two
      edits are one logical change. Landing the entry without the comment amendment
      creates a grouping that contradicts itself immediately, and the comment is a
      reviewer-visible lie until it is fixed. Same commit, same edit.

  - action: edit_comment
    id: change_allowlist_group_comment
    path: src/backend/config/settings/base.py
    description: >
      Amend the Python-consumed group's parenthetical so it names the third read location.
      The current text claims the group is consumed "in base.py & prod.py", which becomes
      false the moment `RUN_TRANSLATION_BACKFILL` lands — the entry is read in
      `apps/core/utils/migrate_locked.py`, outside the settings package entirely.

      The replacement must name all three locations. It must **not** be reworded into a
      general statement about "the codebase" or "src/", because a vague comment is what
      makes the next reviewer stop checking.
    code_hint: |
      # --- Python-consumed (env()/env.*()/os.getenv in base.py, prod.py,
      #     apps/core/utils/migrate_locked.py) ---
    do_not_edit:
      - "the bootstrap control flags group or its three comments"
      - "the shell/compose group or its comments"
      - "any other entry"

  - action: add_test_module
    id: change_reverse_scan_module
    path: src/backend/config/settings/tests/test_env_allowlist_reverse.py
    description: >
      The reverse-direction contract. `ALLOWED_ENV_VARS` is the only thing it reads from
      production; everything else is derived from the source tree by AST.

      **File walk.** `_iter_source_files` walks `src/**/*.py` and keeps a file if and only
      if **no path component of its path relative to `src/` is exactly `tests`**. The
      exclusion is component equality, never a substring test on the full path string —
      the documented `protest_handler.py` failure mode (D5) is precisely a substring rule
      silently dropping a real module. `test_migrations.py`, `conftest.py` and the
      `testing/` package are **in** scope by this rule, which is correct and documented
      in the module docstring.

      **Read shapes.** The visitor recognises exactly four shapes and records which it
      saw:
        1. `env("NAME", …)` — the bare call; the name is `args[0]`.
        2. `env.<cast>("NAME", …)` — the attribute call (`bool`, `int`, `str`, `list`,
           `float`, `dict`, `tuple`, `json`, `url`, `path`, `bytes`); the name is `args[0]`.
        3. `os.getenv("NAME", …)` and `os.environ.get("NAME", …)`.
        4. `os.environ["NAME"]` — a subscript whose slice is a string constant.
      It must resolve the name **without a regex and without reading the line text**,
      which is what makes `env(\n    "EMAIL_BACKEND",\n …)` a non-event instead of the
      three-variable miss the report's low-count sweep produced.

      **`env.db()` is the load-bearing special case, and it is the reason the whole
      design needs a test.** django-environ's URL helpers read a variable that is **not in
      the call arguments at all**: `env.db()` takes **no positional argument whatsoever**
      and implicitly reads `DATABASE_URL`. A visitor that inspects only the first
      positional argument is therefore **green and wrong** — it contributes zero names,
      the set it compares is one name smaller, and the subset assertion keeps passing.
      That is the single most likely silent failure of this block, and it is invisible
      without an explicit test.

      `_IMPLICIT_VAR_HELPERS` is the fix: an explicit table mapping the zero-argument
      helpers to the variable they read (`db` and `db_url` → `DATABASE_URL`), consulted
      **before** `args[0]` is ever looked at. And **any other** `env.<attr>()` call with
      no positional argument is recorded as *unrecognised*, which fails
      `test_env_read_shapes_are_all_recognised` by file and line. A future zero-argument
      helper — `env.cache()`, `env.json()`, anything django-environ adds — is therefore a
      red test naming the call, not a quietly smaller number.

      **`set(os.environ)` must not be mistaken for a read.** `base.py` snapshots the
      environment twice (`_env_keys_before = set(os.environ)`, then
      `_warn_unknown_env_vars(set(os.environ) - _env_keys_before)`). `set(os.environ)` is
      a name-set comparison, not a read of a specific variable; the visitor must not
      attribute every ambient key to the allowlist. The module docstring says why, because
      the next reader will otherwise "fix" it.

      **Escape hatch (D4).** A line whose source contains `_OPT_OUT_MARKER`
      (`env-contract:`) is excluded from `consumed` and recorded in `opt_outs`. There are
      **zero** current users, and the mechanism is proven by
      `test_env_contract_opt_out_is_honoured`, which runs the scanner over a **synthetic
      source string** passed to `_scan_source` — not over a real file, not over
      `tmp_path`, so no filesystem and no bandit surface. The docstring records that a
      first user is expected to be rare and must be visible in review.

      **Module docstring — required content, in this order.** (1) What the test asserts:
      the forward direction, `consumed ⊆ ALLOWED_ENV_VARS`. (2) **The asymmetry, stated
      plainly:** the reverse direction is *not* asserted, because 13 of the 48 allowlist
      entries have no Python read and every one of them is deliberate —
      `SCHEDULER_HEALTH_STALE_SECONDS` is the worked example, read by
      `docker/healthcheck-scheduler.sh` and set by `docker-compose.prod.yml`; the
      bootstrap flags are honoured only from the process environment. Asserting
      "allowlisted ⇒ read in Python" would be false by construction and would be the
      second hand-maintained contract D1 refuses. (3) The coverage boundary: **the Python
      channel only** — not `docker/*.sh`, not the compose files, not the `deploy-check`
      env block (BLOCK 4's). (4) Why exclusion is by path component and why
      `test_migrations.py` is therefore scanned. (5) That a green run is not evidence the
      test *would have caught* CFG-008; the red/green demonstration is.

      **Failure message discipline (BC-4):** name the missing variables and the files
      that read them. **Never interpolate a variable's value** — the scanner never has
      one, and no assertion may.
    code_hint: |
      _SRC_ROOT = ...            # <repo>/src, derived via the _ROOT walk-up
      _EXCLUDED_PATH_COMPONENTS = frozenset({"tests"})
      _OPT_OUT_MARKER = "env-contract:"

      # django-environ helpers whose variable name is NOT in the call arguments.
      # env.db() takes no arguments at all and reads DATABASE_URL -- a visitor that
      # only inspects args[0] under-counts silently. Any OTHER env.<helper>() with no
      # positional argument is recorded as unrecognised and fails the shape test.
      _IMPLICIT_VAR_HELPERS = {
          "db": "DATABASE_URL",
          "db_url": "DATABASE_URL",
      }

      # Read shapes this visitor knows. It asserts on its own coverage: a shape it does
      # not recognise is a failure, not a smaller number.
      _RECOGNISED_READ_SHAPES = frozenset({
          "env(...)",
          "env.<cast>(...)",
          "os.getenv(...) / os.environ.get(...)",
          "os.environ[...]",
      })

      # Typing: ast.walk() returns Iterator[AST] and AST declares no .args / .func /
      # .value. Either subclass NodeVisitor and override visit_Call / visit_Subscript
      # (preferred -- the narrowing and the shape bookkeeping then live in one place), or
      # guard every single attribute read with isinstance(node, ast.Call) /
      # isinstance(node, ast.Subscript). A bare ``node.args`` on a walked node is an
      # attribute the type does not declare.

      class _EnvReadVisitor(ast.NodeVisitor):
          """Collect environment-variable names read by one module.

          A NodeVisitor subclass, not an ast.walk() loop: ast.walk() yields Iterator[AST]
          and the AST base class declares no .args / .func / .value, so a walk-based scan
          reads attributes the type does not declare. Overriding visit_Call and
          visit_Subscript narrows the node type before every attribute read, and is also
          where the unrecognised-shape bookkeeping lives.

          Handles all four read shapes. Records any env-ish call it cannot attribute to a
          name in ``unrecognised`` so an unrecognised shape fails loudly.
          """

      def test_consumed_env_vars_are_allowlisted() -> None:
          """Every environment variable read by non-test src/**/*.py is allowlisted.

          The reverse direction of the VAL-004 contract. Full-tree, not settings-only:
          RUN_TRANSLATION_BACKFILL is read in apps/core/utils/migrate_locked.py, which
          a settings-package scan would not see.
          """
          missing = _consumed_env_vars() - ALLOWED_ENV_VARS
          assert not missing, (
              "Environment variables read by src/**/*.py but absent from "
              f"ALLOWED_ENV_VARS: {sorted(missing)}. Add each to the Python-consumed "
              "group in config/settings/base.py, or use the '# env-contract:' opt-out "
              "on the read if it is not a deployment variable."
          )

      def test_env_read_shapes_are_all_recognised() -> None:
          """The visitor understood every env-ish call it met.

          Three hazards this closes, in order of how silently they fail:
            1. env.db() reads DATABASE_URL with NO positional argument.
            2. set(os.environ) is a name-set snapshot, not a read of one variable.
            3. a future zero-argument django-environ helper would be missed entirely.
          """
          ...

  - action: add_test_function
    id: change_scan_coverage_assertions
    path: src/backend/config/settings/tests/test_env_allowlist_reverse.py
    depends_on: [change_reverse_scan_module]
    description: >
      The two coverage assertions that keep the scan from silently shrinking to nothing.
      Without them, a future refactor that breaks the file walk — a bad glob, a wrong
      root, an over-eager exclusion — produces a test that still passes because the set it
      compares is empty, and CFG-008's class of defect returns with a green suite.

      `test_env_scan_covers_more_than_the_settings_package` asserts three things about
      the walked file set: it is non-empty; at least one scanned file lies **outside**
      `config/settings`; and its size is greater than the number of `.py` files the
      settings package alone contains. The second assertion is the one that matters —
      it is the assertion that makes a settings-only scan **red**, which is why the
      red/green demonstration in `tests.must_be_demonstrated_red` is meaningful rather
      than vacuous.

      It must be an **existence and breadth** assertion, never a count of consumed names.
      A hard-coded `len(consumed) == 36` would go red the first time a variable is added
      anywhere in the tree, which is the wrong signal and would train the next person to
      update a magic number instead of reading the failure.
    code_hint: |
      def test_env_scan_covers_more_than_the_settings_package() -> None:
          """The scan is whole-tree, so a settings-only regression cannot pass silently."""
          files = list(_iter_source_files())
          assert files, "no source files were scanned -- the walk is broken"
          outside_settings = [p for p in files if "config/settings" not in p.parts]
          assert outside_settings, (
              "the scan saw nothing outside config/settings; it must cover all of src/"
          )
          settings_files = [p for p in files if "config/settings" in p.parts]
          assert len(files) > len(settings_files)

  - action: add_test_function
    id: change_escape_hatch_test
    path: src/backend/config/settings/tests/test_env_allowlist_reverse.py
    depends_on: [change_reverse_scan_module]
    description: >
      Prove the escape hatch works, using a **synthetic source string** handed to
      `_scan_source` — not a file on disk, not `tmp_path`, and never a real module. The
      synthetic source contains one ordinary read and one read carrying the marker; the
      test asserts the first is collected and the second is not and is recorded in
      `opt_outs`.

      This is the only test of the hatch, and the hatch has **zero real users** today.
      The docstring says so, and `acceptance_criteria` requires the Implementor to report
      the count of real opt-outs as `0`. A hatch that is untested is worse than no hatch,
      because a reader will trust it; a hatch with a synthetic proof and no users is
      honest.

      It must not be paired with a `len(opt_outs) == 0` assertion over the real tree.
      That would turn the first legitimate future use into a second required edit, and the
      docstring already carries the fact that a use should be visible in review.
    code_hint: |
      def test_env_contract_opt_out_is_honoured() -> None:
          """A read carrying the opt-out marker is excluded and recorded.

          Proven on a synthetic source string, not on a real module: the marker has zero
          users in the tree today and the mechanism must not be shipped untested.
          """
          source = (
              "import os\\n"
              "PLAIN = os.getenv('SOME_PLAIN_NAME')\\n"
              "HIDDEN = os.getenv('NOT_A_DEPLOYMENT_VAR')  # env-contract: fixture only\\n"
          )
          consumed, _, opt_outs = _scan_source(source, "<synthetic>")
          assert "SOME_PLAIN_NAME" in consumed
          assert "NOT_A_DEPLOYMENT_VAR" not in consumed
          assert opt_outs == ["<synthetic>:3"]

  - action: edit_template
    id: change_env_example_retitle
    path: .env.example
    description: >
      Retitle the header and remove the BOM, per D2. The new title drops
      "Comprehensive" and states that the three tier templates are the authoritative ones
      and that this file is a cross-tier reference — **without** contradicting the
      "copy one of the three" instructions, which stay byte-identical immediately below
      it. The retitle reinforces those instructions; it does not compete with them.

      The file is rewritten as plain UTF-8 with **no BOM**. The existing `—` em dash in
      the title is fine in UTF-8; the BOM is not, because it defeats any parser that
      checks the first character.

      The trailing prose block is new and is D2's "named in prose" half: it lists the
      consumed variables that are deliberately absent from this stub, each with the reason
      in one clause — the container-path and container-tuning knobs ("defaults live in
      `base.py` and the compose files; set them in your tier template if you must"), and
      the three forbidden ones (`DATABASE_URL` is constructed by Compose; the bootstrap
      flags are process-environment-only and are not file settings). **Do not print the
      literal flag names in a way that invites an operator to set them** — name them as a
      category, the way the existing templates already do.
    code_hint: |
      # .env.example - Cross-tier reference for Mko Bazuna environment variables
      #
      # This file is NOT the authoritative list and is deliberately not exhaustive.
      # The authoritative templates are the three tier files - copy the one you need:
      #   cp .env.dev.example .env.dev     # development (Docker)
      #   cp .env.prod.example .env.prod   # production (Docker)
      #   cp .env.test.example .env.test   # testing (Docker)
      #
      # Blocks that apply to every tier are kept below; a variable missing from this file
      # is not thereby unsettable. See the note at the end of this file.

      # ====================== Email / SMTP ======================
      # Required in production. Provide real values in your .env.<tier> file.
      EMAIL_HOST=
      EMAIL_PORT=587
      EMAIL_HOST_USER=
      EMAIL_HOST_PASSWORD=
      EMAIL_USE_TLS=True
      EMAIL_TIMEOUT=10
      DEFAULT_FROM_EMAIL=
      # Optional. Comma-separated admin addresses for support notifications.
      # SUPPORT_NOTIFICATION_RECIPIENTS=admin@example.com

      # ====================== Not listed here ======================
      # DATABASE_URL is constructed by Docker Compose from POSTGRES_* - do not set it.
      # The bootstrap control flags (image build, dev one-shots) are honoured only from
      # the process environment; they are not file settings and are not listed.
      # Liveness files, health-stale windows and command timeouts are container paths
      # with working defaults in config/settings/base.py and the compose files.

    placement: >
      The `Email / SMTP` section is inserted **after the `Telegram Bot` section and before
      the `Google Cloud Translation API` section**, mirroring the relative order
      `.env.prod.example` already uses. The `POSTGRES_HOST=db` line is appended to the
      existing `PostgreSQL Database` section, directly after the `POSTGRES_PASSWORD`
      entry, matching `.env.dev.example` and `.env.prod.example`.

  - action: edit_template
    id: change_prod_example_migrate_section
    path: .env.prod.example
    depends_on: [change_allowlist_entry]
    description: >
      Create the `Migration bootstrap` section the block's note 1 assumes already exists
      (it does not — see `corrections_to_block_notes`), positioned between the
      `Container runtime` and `Prometheus Metrics` sections, and put
      `RUN_TRANSLATION_BACKFILL` in it as a **commented** entry.

      Commented is the only correct form, for two reasons that are both in the code: the
      comparison in `migrate_locked._build_steps` is `== "true"`, so a live empty key says
      nothing useful; and a live `=true` key would switch a one-time translation backfill
      on in every deployment that copies the template. The prose says what the flag does,
      that the step runs inside the same advisory lock as the rest of the sequence, and
      that it is removed after the run.

      **Encoding (correction to note 2).** This file is **not valid UTF-8** — it carries
      four CP1252 `0x97` em-dash bytes. Append bytes; write ASCII only; never re-encode
      the existing content. A `read_text()` / `write_text()` round-trip would corrupt it.

      **Sequencing.** This step runs **after** `change_allowlist_entry`. Until the
      allowlist carries the name, a *live* key here would turn
      `test_example_keys_in_allowlist[.env.prod.example]` red. The key is commented, so
      the test cannot see it either way — which is exactly why the ordering is stated
      rather than assumed, and why the Implementor confirms the allowlist edit is present
      before this one.
    code_hint: |
      # ====================== Migration bootstrap ======================
      # One-shot operator action for the `migrate` service. Set to exactly "true" to
      # append the optional `backfill_translations` step to the bootstrap sequence; the
      # step runs inside the same advisory lock as migrate / setup_search_triggers /
      # load_exchange_rates. Unset it again after the run -- this is a one-time
      # backfill, not a standing setting.
      # See docs/ops/migration-workflow.md.
      # RUN_TRANSLATION_BACKFILL=true

  - action: add_test_function
    id: change_template_prose_tests
    path: src/backend/config/settings/tests/test_env_allowlist_reverse.py
    depends_on: [change_env_example_retitle, change_prod_example_migrate_section]
    description: >
      Two narrow **prose** assertions. They assert on words and on key names, never on a
      variable *set*, which is what stops them false-positiving on a template that happens
      to be incomplete for a reason nobody modelled.

      `test_env_example_points_at_the_tier_templates` reads `.env.example` as UTF-8 and
      asserts: the word "Comprehensive" no longer appears in its **title line**; the three
      tier template filenames all appear in the file; and the `cp .env.<tier>.example
      .env.<tier>` instruction is still present. It also asserts the file carries **no
      UTF-8 BOM** — cheap, exact, and the one encoding fact about this file the block can
      pin without over-claiming.

      Title-line scoping for the "Comprehensive" check is deliberate: the word is
      legitimate English elsewhere, and an assertion over the whole file would be a
      tripwire with no meaning.

      `test_env_prod_example_documents_translation_backfill` reads `.env.prod.example`
      with `errors="replace"` — mandatory, the file is CP1252 — and asserts
      `RUN_TRANSLATION_BACKFILL` appears. That single assertion is the guard on CFG-008's
      documentation half: it is the only thing that stops the entry being quietly deleted
      from the template in a later cleanup.

      Neither test is a template-parity test. There is none, and D3 says why.
    code_hint: |
      def test_env_example_points_at_the_tier_templates() -> None:
          """.env.example no longer claims to be comprehensive and points at the tiers.

          Asserts on prose, not on a variable set: an incomplete stub is the *intent*
          after CFG-009, so any assertion of the form "template keys == consumed names"
          would be asserting the defect back into existence.
          """
          raw = (_ROOT / ".env.example").read_bytes()
          assert not raw.startswith(codecs.BOM_UTF8), ".env.example must not carry a UTF-8 BOM"
          text = raw.decode("utf-8")
          title = text.splitlines()[0]
          assert "comprehensive" not in title.lower(), (
              f"the title still claims completeness: {title!r}"
          )
          for tier in (".env.dev.example", ".env.prod.example", ".env.test.example"):
              assert tier in text, f".env.example must point at {tier}"
          assert "cp .env." in text, "the copy-one-of-the-three instructions must survive"

      def test_env_prod_example_documents_translation_backfill() -> None:
          """.env.prod.example documents RUN_TRANSLATION_BACKFILL for the migrate one-shot."""
          text = (_ROOT / ".env.prod.example").read_text(encoding="utf-8", errors="replace")
          assert "RUN_TRANSLATION_BACKFILL" in text

  - action: edit_doc
    id: change_architecture_doc_env_note
    path: docs/99-agent/architecture.md
    depends_on: [change_env_example_retitle]
    description: >
      One sentence. The note currently ends by calling `.env.example`,
      `.env.dev.example`, `.env.test.example` and `.env.prod.example` "the tracked
      templates to copy from". After D2 that is true of three of them and false of the
      first. The sentence is amended to say which are the templates and which is the
      cross-tier reference stub.

      This is the **only** documentation edit in the block. `docs/01-spec/architecture-structure.md`
      is a bare repository-structure listing and stays correct as-is, because the file
      survives the retitle (VAL-003's whole point).

      Re-read the paragraph immediately before editing: BLOCK 3 last committed this file
      and the tree was moving during planning.

# ─────────────────────────────────────────────────────────────────────────────
sequence:

  - step: 0
    name: preflight and re-derivation
    actions:
      - "Confirm BLOCK 3 (`9443ade`) and BLOCK 5 (`6413df5`) are landed: `git log --oneline -5`."
      - "Re-derive, do not transcribe: the size of `ALLOWED_ENV_VARS` and its three group sizes; the consumed-name count from an `ast` walk over non-`tests`-path `src/**/*.py`; and that `RUN_TRANSLATION_BACKFILL` is the only consumed name not allowlisted. If the consumed set differs from 36, the block's decisions still hold; the counts in this task are the anchor's, not a contract."
      - "Confirm `.env.example` still carries a BOM, `.env.prod.example` is still not valid UTF-8, and `.env.example` still has no `Email / SMTP` section. If any of the three is already different, the retitle's shape changes and this task's wording is a starting point, not a specification."
      - "Baseline the scoped suite before editing, so a pre-existing failure is not attributed to this change."
      - "Re-read §1's constraints against the tree. The tree wins where they disagree."
    gate: "scoped settings + tests suites green at baseline"

  - step: 1
    name: production change first, alone
    depends_on: [0]
    actions:
      - "Apply `change_allowlist_group_comment` and `change_allowlist_entry` — one entry, one comment, one logical change."
      - "Run `src/backend/config/settings/tests/test_env_allowlist.py` alone. It must stay green: `RUN_TRANSLATION_BACKFILL` is not in any tracked template, so no template-key assertion is affected."
    expect: >
      Green. If `test_python_consumed_vars_in_allowlist` goes red, the entry was added to
      the wrong group or the comment edit corrupted the literal — inspect `base.py`,
      do not edit the test.

  - step: 2
    name: the reverse-direction module
    depends_on: [1]
    actions:
      - "Create `test_env_allowlist_reverse.py` per `change_reverse_scan_module`, then `change_scan_coverage_assertions` and `change_escape_hatch_test`."
      - "Run the new module alone, before any template edit."
    expect: >
      Green. `test_consumed_env_vars_are_allowlisted` passing here is the **only** evidence
      the block has that the full-tree scan reaches `apps/core/utils/migrate_locked.py` —
      a settings-only scan would also be green, and step 5 is what tells the two apart.
      `test_env_scan_covers_more_than_the_settings_package` is the assertion that makes
      that distinction, so confirm it is present and that it is not vacuous: the walked
      set must include files outside `config/settings`.

  - step: 3
    name: the red/green demonstration — the step the block exists for
    depends_on: [2]
    actions:
      - "Remove `RUN_TRANSLATION_BACKFILL` from `ALLOWED_ENV_VARS` in `base.py`. Run `test_consumed_env_vars_are_allowlisted`."
      - "Confirm it goes **red** naming `RUN_TRANSLATION_BACKFILL` and the file that reads it."
      - "Restore the entry. Confirm green again. Re-read the `base.py` constant to prove the restore."
      - "Then, as a second and separate check, temporarily narrow `_iter_source_files` to the settings package and confirm the same test goes **green** while the entry is absent. Restore. This is what proves the coverage assertion is load-bearing and the first demonstration is not vacuous."
    expect: >
      Red, then green, then red-by-narrowing, then green. Record all four outputs.
      **A settings-only demonstration passes vacuously** and proves nothing; the second
      half of this step is what rules that out. This is the block's defining evidence and
      it is a Validator duty.

  - step: 4
    name: templates
    depends_on: [3]
    actions:
      - "Apply `change_env_example_retitle` to `.env.example`: retitle, BOM removal, the `Email / SMTP` section, the `POSTGRES_HOST` line, the trailing prose block."
      - "Re-read the whole file. Confirm `CSRF_TRUSTED_ORIGINS=` and `SENTRY_DSN=` are still **live key lines, not comments** (D2), and that the three `cp` lines are byte-identical."
      - "Apply `change_prod_example_migrate_section` to `.env.prod.example`, appending bytes and writing ASCII only."
      - "Re-read `.env.prod.example` decoded as CP1252 and confirm the four original `0x97` bytes are intact and that no new non-ASCII byte was introduced."
      - "Run `test_env_allowlist.py`, `test_csrf_trusted_origins.py` and `test_prod_logging.py` together."
    expect: >
      Green. The two substring tests would also pass on a **commented** line, so the
      human re-read of those two lines is not optional. If any of the three modules goes
      red, the retitle broke a shipped contract — fix the template, never the test.

  - step: 5
    name: the template prose assertions
    depends_on: [4]
    actions:
      - "Apply `change_template_prose_tests` to the new module."
      - "Run the new module alone, then the whole settings-test package."
    expect: >
      Green. The new tests read a **retitled** file, so they are red until step 4 lands —
      that is the intended order, and it is why the module is created in step 2 and the
      template tests are appended in step 5 rather than written all at once.

  - step: 6
    name: documentation
    depends_on: [5]
    actions:
      - "Re-read the `.env.*` note in `docs/99-agent/architecture.md`, then apply `change_architecture_doc_env_note` — one sentence."
      - "Confirm `docs/01-spec/architecture-structure.md` is unchanged and still correct."
    expect: "One sentence changed. Nothing else in either file."

  - step: 7
    name: gates
    depends_on: [6]
    actions:
      - "Run the full `tests.verification_gate` sequence below, including the red/green demonstration from step 3 and the encoding checks."

  - step: 8
    name: hand-off
    depends_on: [7]
    actions:
      - "Re-read `git status --short` and stage explicit paths only (§1 hard rule). Never `git add -A` — the tree carries 19 pre-existing `.ai/audit/**` deletions that must not be swept in."
      - "Do not commit without an explicit user request."
      - "Restate the coverage boundary in the hand-off, in the words of `acceptance_criteria`: the scan sees the **Python channel only**. A reader who believes it also guards the shell, the compose files or the `deploy-check` env block will trust it for the wrong thing."
      - "Hand the coordinator the option-F deferral for folding into the plan's §5.2. This task records it; the plan's summary sections are not this Planner's to edit."
      - "Name any gate that could not be run here rather than implying it passed."

# ─────────────────────────────────────────────────────────────────────────────
tests:

  must_keep_passing_unchanged:
    - "`src/backend/config/settings/tests/test_env_allowlist.py` **in full, byte-identical** — `test_example_keys_in_allowlist` (all four parametrizations: `.env.example`, `.env.dev.example`, `.env.prod.example`, `.env.test.example`), `test_python_consumed_vars_in_allowlist`, `test_scheduler_health_stale_seconds_allowlisted`, `test_unknown_env_var_logs_warning`, `test_known_env_vars_no_warning`, and `test_bypass_flags_absent_from_env_templates` (both parametrizations). It is `not_touched` in the file list and the block's new test lives in a separate module (D4). The first two of these are the pair that makes the round trip meaningful: the template→allowlist direction and a spot-check of the allowlist→consumed direction, neither of which the new scan replaces."
    - "`test_csrf_trusted_origins.py`'s `test_csrf_trusted_origins_in_example` and `test_csrf_trusted_origins_in_prod_example` — both assert a **substring**, so both survive the retitle whether or not the key stays a live line. That is precisely why D2 requires a human re-read of the two lines rather than trusting the suite."
    - "`test_prod_logging.py`'s `test_sentry_dsn_in_env_examples` — same substring property, same reason. It reads `.env.prod.example` with `errors=\"replace\"`, which is the encoding-correct way to read a CP1252 file and is the precedent the new test follows."
    - "`src/backend/config/settings/tests/test_deploy_check_env_parity.py` **in full** — BLOCK 4's module and VAL-004 instance (b). The block adds no key to `ci.yml`, no key to the allowlist's shell group, and no constant it could collide with. Its docstring's argument against a hand-maintained required set is the argument D1 relies on."
    - "`src/backend/config/settings/tests/test_prod_logging.py`, `test_settings_secrets.py`, `test_csrf_trusted_origins.py`, `test_oneshot_settings.py`, `test_settings_defaults.py` in full — none is edited and none is imported by the new module."
    - "`src/backend/tests/test_compose_contract.py` in full (phase 01's VAL-004 instance (a)). The block adds no `POSTGRES_*` or `DATABASE_URL` key to any template; `DATABASE_URL` is explicitly excluded by D3."
    - "`src/backend/apps/core/tests/test_migrate_locked.py` in full — it exercises `_build_steps`, the function whose flag this block allowlists and documents. The block does not change `_build_steps`."
    - "`src/telegram_bot/**` — untouched, and the new module must not become reachable from the bot's import path."
    - "Every `prod.py` guard test. No settings-module body is edited in this block."

  must_be_added:

    - name: test_consumed_env_vars_are_allowlisted
      path: src/backend/config/settings/tests/test_env_allowlist_reverse.py
      why: >
        CFG-008's durable half, and the assertion VAL-004 instance (c) asks for. It walks
        **all** non-test `src/**/*.py` by AST, collects the read variable names, and
        asserts the set is a subset of `ALLOWED_ENV_VARS`. Forward direction only, by
        design (D6).
      asserts:
        - "`consumed ⊆ ALLOWED_ENV_VARS`, with a message naming the missing variables and the files that read them, and naming the opt-out mechanism."
        - "**No variable value appears in any message.** The scanner never holds one."
        - "The walk covers `apps/core/utils/migrate_locked.py`. This is what makes the red/green demonstration non-vacuous, and `test_env_scan_covers_more_than_the_settings_package` is the assertion that guarantees it rather than leaving it to inspection."

    - name: test_env_read_shapes_are_all_recognised
      path: src/backend/config/settings/tests/test_env_allowlist_reverse.py
      why: >
        The only thing that makes an unrecognised read shape **loud**. Without it the scan
        degrades silently: a new helper or a new call form simply stops contributing, the
        set gets smaller, and the subset assertion keeps passing.
      asserts:
        - "No `env`-ish call was left unattributed. Any occurrence is reported with file and line, so the failure names the shape that needs teaching rather than a count."
        - "Every shape in the module's declared shape table was actually exercised by the current tree — a declared-but-unexercised shape is itself the finding, because it means the visitor has a branch no code reaches."
        - "`_IMPLICIT_VAR_HELPERS` actually resolved `DATABASE_URL` from `env.db()`. This is the `env.db()` gap stated as a test: a first-argument-only visitor is green and wrong, and this is the assertion that makes it impossible to stay that way."

    - name: test_env_scan_covers_more_than_the_settings_package
      path: src/backend/config/settings/tests/test_env_allowlist_reverse.py
      why: >
        Anti-vacuity. A scan whose walk is broken, mis-rooted or over-filtered returns an
        empty or settings-only set and passes. This is the assertion that turns that
        failure into a red test.
      asserts:
        - "The walked set is non-empty."
        - "At least one walked file lies **outside** `config/settings`. This is the assertion a settings-only regression fails."
        - "The walked set is larger than the settings package's own file count."
        - "**No hard-coded count of consumed names.** A count assertion would red on the next legitimate variable and would train the next author to update a magic number instead of reading a failure message."

    - name: test_env_contract_opt_out_is_honoured
      path: src/backend/config/settings/tests/test_env_allowlist_reverse.py
      why: >
        Proves the escape hatch on a **synthetic source string**, so the mechanism is not
        shipped untested even though it has zero real users (D4). Not on a real module, not
        on `tmp_path`, so the test adds no filesystem surface and no bandit consideration.
      asserts:
        - "An ordinary read in the synthetic source is collected."
        - "A read carrying the marker is excluded from `consumed` and recorded in `opt_outs` with its position."

    - name: test_env_example_points_at_the_tier_templates
      path: src/backend/config/settings/tests/test_env_allowlist_reverse.py
      why: >
        Guards the retitle against regression (D2). A **prose** assertion, on purpose: the
        stub is deliberately incomplete after CFG-009, so any assertion over a variable set
        would assert the defect back into existence.
      asserts:
        - "The title line no longer contains the word \"comprehensive\", case-insensitively. Scoped to the title line — the word is legitimate English elsewhere, and a whole-file check would be a meaningless tripwire."
        - "All three tier template filenames appear in the file."
        - "The `cp .env.` copy instruction is still present, so the retitle did not quietly delete the operational instruction it claims to reinforce."
        - "The file does **not** start with a UTF-8 BOM."

    - name: test_env_prod_example_documents_translation_backfill
      path: src/backend/config/settings/tests/test_env_allowlist_reverse.py
      why: >
        The guard on CFG-008's documentation half. Read with `errors=\"replace\"` — mandatory,
        the file is CP1252, and this is the encoding fact `corrections_to_block_notes`
        records against the block's note 2.
      asserts:
        - "`RUN_TRANSLATION_BACKFILL` appears in `.env.prod.example`."

  must_be_demonstrated_red:
    - >
      **Demonstration A — the reverse-direction test's red before its green. This is the
      block's defining evidence and it is a Validator duty, not a shipped test.**
      Remove `RUN_TRANSLATION_BACKFILL` from `ALLOWED_ENV_VARS` in `base.py` and run
      `test_consumed_env_vars_are_allowlisted`. It must go **red**, naming the variable
      and the file that reads it. Restore the entry, re-read the constant to prove the
      restore, and confirm green.

      **The demonstration must go through the full-tree scan.** Run the new module, not a
      settings-package subset: `RUN_TRANSLATION_BACKFILL` is read in
      `apps/core/utils/migrate_locked.py`, which is **not** in the settings package, so a
      settings-only demonstration of the same defect passes vacuously and demonstrates
      nothing. This is the single most important sentence in this section, and it is the
      reason D1 rejects Option B.
    - >
      **Demonstration B — the coverage assertion is load-bearing, shown two-sided.** With
      `RUN_TRANSLATION_BACKFILL` again absent from the allowlist, temporarily narrow
      `_iter_source_files` to `config/settings` and run the module. Two results, and both
      matter:
        1. `test_consumed_env_vars_are_allowlisted` goes **green** — the defect is now
           invisible, which is exactly Option B's blind spot demonstrated rather than
           asserted.
        2. `test_env_scan_covers_more_than_the_settings_package` goes **red**.
      Restore the walk. This is what converts "the scan is whole-tree" from a claim in a
      docstring into a property the suite enforces.
    - >
      **Demonstration C — the retitle cannot silently drop the two pinned keys.** Comment
      out `CSRF_TRUSTED_ORIGINS=` in `.env.example` and run
      `test_csrf_trusted_origins_in_example`; it must go red, because a commented line no
      longer contains the substring. Restore. This proves the two suite-green tests are
      *substring* tests rather than key tests, and it is why `change_env_example_retitle`
      requires a human re-read of both lines instead of trusting a green run.
    - >
      All three are **Validator duties**. Record each output. A negative control that was
      never seen red proves nothing.
    - >
      **The one-line allowlist change needs no behavioural test of its own beyond
      Demonstration A.** Removing `RUN_TRANSLATION_BACKFILL` from `ALLOWED_ENV_VARS` does
      not change any runtime behaviour: `_warn_unknown_env_vars` is advisory, and a
      production deployment that sets the flag gets a WARNING either way before this
      change and none after it. A subprocess test of the warning would be a test of
      `_warn_unknown_env_vars`, which `test_unknown_env_var_logs_warning` already owns.
      One entry, one comment, one demonstration.

  need_no_test:
    - >
      **A template-parity test asserting consumed ⊆ template keys.** This is the
      Researcher's option F and it is **deferred** (D7). It is not needed for this block
      because D3 makes it unbuildable without a second hand-maintained contract: the two
      names that would need exempting — `DATABASE_URL`, constructed by Compose, and the
      two process-environment bootstrap flags, already forbidden by a shipped test — are
      exactly the cases the templates already state in prose. Turning prose into an
      exemption list rebuilds the anti-pattern the block exists to remove.
    - >
      **A test per added template key.** The `Email / SMTP` block and the
      `POSTGRES_HOST` line are documentation. The guards that matter are
      `test_example_keys_in_allowlist` (template → allowlist, already shipped) and
      `test_env_prod_example_documents_translation_backfill` (the one template entry whose
      deletion would be silent).
    - >
      **Inline annotations on the 13 non-Python-read allowlist entries.** D6. The
      asymmetry is stated once, in the new module's docstring, with
      `SCHEDULER_HEALTH_STALE_SECONDS` named. Annotating thirteen entries in a production
      constant to repeat it is maintenance burden for no additional information.
    - >
      **A test that `.env.example` "is complete" or "matches a required set".** That is
      the defect CFG-009 names, restated as a contract. The retitle's whole purpose is to
      stop the file claiming completeness it does not have.
    - >
      **Any change to `test_env_allowlist.py`, `_example_keys`, `_warn_unknown_env_vars`, or
      the settings-module bodies.** The block reads production code; it does not change it
      beyond one allowlist entry and one comment.
    - >
      **A shell/compose counterpart to the new scan.** Out of scope, stated in
      `acceptance_criteria`, and BLOCK 4 already owns the `deploy-check` env block. A
      single module asserting three unrelated channels would violate the project's
      single-responsibility rule.
    - >
      **A test for `ALLOWED_ENV_VARS`'s size, group sizes, or group membership.** 48
      entries, 34/2/12 grouping, and "zero dead entries" are measurements of the anchor,
      not contracts. Pinning them would red on the next legitimate addition and would
      replace a readable failure with a numeric one.

  verification_gate:
    - step: 1
      name: scoped run (the new module alone)
      command: >
        `$dc run --rm -e PYTEST_SKIP_MARKERS=seed -e
        PYTEST_OPTS="src/backend/config/settings/tests/test_env_allowlist_reverse.py" test`
        with `$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test
        -f docker-compose.yml -f docker-compose.test.yml'`
      expect: >
        Six tests, green. After step 2 of the sequence, four; after step 5, six. Count
        them — a mismatch means collection picked up something else.
    - step: 2
      name: scoped run (the whole affected surface)
      command: >
        `$dc run --rm -e PYTEST_SKIP_MARKERS=seed -e
        PYTEST_OPTS="src/backend/config/settings/tests src/backend/apps/core/tests/test_migrate_locked.py src/backend/tests/test_compose_contract.py" test`
      expect: >
        Green, and the total is the pre-existing count **plus** six. A drop is a collection
        or import regression.
    - step: 3
      name: the red/green demonstrations
      command: "Demonstrations A, B and C above, each restored and re-confirmed green."
      expect: >
        Red, then green, then red-by-narrowing, then green; red, then green. Record every
        output. **Demonstration A must be run against the new module, not a settings-only
        subset** — a settings-only run is vacuous and would be reported as passing.
    - step: 4
      name: encoding checks
      command: >
        Re-read `.env.example` as bytes and assert no `EF BB BF` prefix; re-read
        `.env.prod.example` as bytes and assert the four original `0x97` bytes are
        unchanged and no new non-ASCII byte was introduced.
      expect: >
        Both hold. This is a manual check, not a test, and it is listed as a gate because
        the two files are not valid UTF-8 and a well-meaning editor can corrupt either one
        without any test going red.
    - step: 5
      name: full fast gate
      command: ".\\Makefile.ps1 test"
      expect: >
        Green. **Necessary, not sufficient** — a green run is *not* evidence that the new
        test would have caught CFG-008; only Demonstration A is. The **i18n completeness
        gate** is part of this run and must pass: the block introduces no user-visible
        string (the template prose and the assertion messages are operator diagnostics and
        documentation, not UI, and are not translated anywhere in this codebase).
    - step: 6
      name: static gates
      command: "uv run ruff check src/ and uv run basedpyright src/"
      expect: >
        Both green. The new module is plain stdlib (`ast`, `pathlib`, `pytest`) plus one
        import from `config.settings.base`; basedpyright must be satisfied by annotating
        the visitor's collections explicitly (`set[str]`, `list[tuple[str, int, str]]`).
        Run `ruff check --fix src/` if `I001` trips on the new module's import block.
        **Neither gate needs a configuration change** — D4's escape hatch is a plain
        comment precisely so that no ruff or bandit configuration is touched.

        **The `ast` typing requirement, and why the green gate is not the reason for it.**
        `ast.walk()` returns `Iterator[AST]`, and the `AST` base class declares no
        `.args`, no `.func` and no `.value` — those exist only on `ast.Call`, `ast.Attribute`
        and `ast.Subscript`. A scan written as `for node in ast.walk(tree): node.args …`
        is therefore attribute access on a type that does not declare it. The block
        **requires** the narrow form regardless: an `ast.NodeVisitor` subclass that
        overrides `visit_Call` and `visit_Subscript` (so `self.generic_visit(node)` is
        never needed to see an attribute that is not there), **or** an
        `isinstance(node, ast.Call)` / `isinstance(node, ast.Subscript)` guard before
        every single attribute read. Prefer the visitor: it is the only one of the two
        that also gives `D4`'s shape-coverage assertion somewhere to live.

        Correction to the standing warning, recorded because the tree wins (§0.2): a
        `[tool.basedpyright]` section **does** exist in `pyproject.toml`, at
        `typeCheckingMode = "standard"` with `reportAttributeAccessIssue = "none"`. So
        this pattern would **not** fail the gate today. The requirement stands anyway,
        for the reason that matters: `reportAttributeAccessIssue = "none"` is a
        project-wide suppression, the code is correct only by that suppression, and a
        narrowing form is what makes the visitor's own contract — "I understand every
        shape I met" — true rather than asserted. If the Implementor prefers
        `ast.walk()`, the `isinstance` guard is mandatory on every read.
    - step: 7
      name: gitleaks
      command: "not runnable on this host (VAL-005)"
      expect: >
        Placeholder-only values were added, and `.env.*.example` is allowlisted **by path**
        in `.gitleaks.toml` — a path allowance, not a licence to write a real value. The
        hand-off states plainly that the scanner was not exercised here.

# ─────────────────────────────────────────────────────────────────────────────
acceptance_criteria:
  - >
    `ALLOWED_ENV_VARS` contains `RUN_TRANSLATION_BACKFILL`, it is the last entry of the
    **Python-consumed** group, and that group's parenthetical comment is amended **in the
    same change** to name `base.py`, `prod.py` **and** `apps/core/utils/migrate_locked.py`.
    The entry count moves 48 → 49. Nothing else in the constant changes: the two other
    groups, the bootstrap-flag comments, the trailing-comma style and the `frozenset(env(...))`
    wrapper are byte-identical.
  - >
    **No new production constant exists.** There is no consumed-name set, no
    required-name set, and no exemption list anywhere in `src/backend/config/`. The new
    test module is the entire reverse-direction mechanism, and it reads
    `ALLOWED_ENV_VARS` and nothing else from production.
  - >
    The new module walks **all** non-`src`-excluded `.py` files under `src/` — measured at
    337 at the anchor — by AST, recognises the four read shapes
    (`env(...)`, `env.<cast>(...)`, `os.getenv` / `os.environ.get`, `os.environ[...]`),
    resolves django-environ's zero-argument helpers through an explicit table, and asserts
    `consumed ⊆ ALLOWED_ENV_VARS`.
  - >
    **Coverage boundary — stated here so it cannot be over-claimed later.** The new test
    covers the **Python channel only**: non-test `src/**/*.py` read through
    django-environ, `os.getenv`, `os.environ.get` and `os.environ[...]`. It does **not**
    cover `docker/*.sh`, the compose files, the GitHub Actions `deploy-check` env block
    (BLOCK 4's `test_deploy_check_env_parity.py`), `.env.test`'s CLI-injected
    `PYTEST_*` variables, or any template. A reader who believes otherwise will trust it
    for the wrong thing, and this sentence is the guard.
  - >
    **A green run is not evidence that the test would have caught CFG-008.** The
    red/green demonstration is the only thing that establishes it, and it must be run
    against the new module's full-tree scan. A settings-only demonstration passes
    vacuously, because the settings package does not contain
    `RUN_TRANSLATION_BACKFILL`. The hand-off records the demonstration outputs or says
    plainly that they were not run.
  - >
    The file walk excludes by **path component** equality against `tests`, never by
    filename pattern and never by substring on the full path. `config/settings/test_migrations.py`
    is therefore **scanned**, which is correct: it is a Django settings module, and a
    filename-based rule would be wrong in the direction that matters. It contributes zero
    names today because it contains no environment read; that is measured, not assumed.
    `src/backend/testing/` and `src/backend/conftest.py` are likewise in scope.
  - >
    The visitor's own shape coverage is asserted: no `env`-ish call went unattributed, every
    declared shape was exercised, and `env.db()` resolved `DATABASE_URL` — so the
    silent-under-count failure mode is impossible to reintroduce unnoticed.
    `set(os.environ)` in `base.py` is **not** treated as a read of every ambient variable.
  - >
    The escape hatch is a per-line `# env-contract:` **comment**, not a `# noqa`
    directive; it is proven by a synthetic-source test; it has **zero** real users, and the
    hand-off reports that count. No ruff, bandit, pytest or packaging configuration was
    changed, and none is required for the mechanism to work.
  - >
    The new module's docstring states the **asymmetry** plainly: only the forward direction
    is asserted, because 13 of the 49 allowlist entries have no Python read and every one
    is deliberate — `SCHEDULER_HEALTH_STALE_SECONDS` named as the worked example — and
    asserting the reverse would be false by construction.
  - >
    `.env.example` no longer claims to be comprehensive, carries **no UTF-8 BOM**, names
    all three tier templates, and still contains the `cp .env.<tier>.example .env.<tier>`
    instructions byte-identical. `CSRF_TRUSTED_ORIGINS=` and `SENTRY_DSN=` remain **live
    key lines** — a human confirmed this, because the two tests that assert them are
    substring tests that a commented line also satisfies.
  - >
    The `Email / SMTP` section exists in `.env.example` with `EMAIL_HOST`, `EMAIL_PORT`,
    `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_TIMEOUT`,
    `DEFAULT_FROM_EMAIL` and `SUPPORT_NOTIFICATION_RECIPIENTS`, and `POSTGRES_HOST=db`
    is present in the `PostgreSQL Database` section. All values are placeholders or empty.
    `EMAIL_BACKEND`, `DATABASE_URL`, the bootstrap control flags and the
    liveness/health/timeout knobs are **not** key lines, and each is accounted for by D2 or
    D3 — not by a list.
  - >
    `.env.prod.example` has a new `Migration bootstrap` section, positioned between the
    `Container runtime` and `Prometheus Metrics` sections, carrying `RUN_TRANFLATION_BACKFILL`
    as a **commented** entry with prose. The file is still not valid UTF-8, its four
    original `0x97` bytes are byte-identical, and no new non-ASCII byte was introduced.
  - >
    `docs/99-agent/architecture.md`'s `.env.*` note is amended in one sentence so that
    `.env.example` is no longer described as a template to copy from.
    `docs/01-spec/architecture-structure.md` is unchanged and still correct.
  - >
    **`src/backend/config/settings/tests/test_env_allowlist.py` is byte-identical** — not
    one line added, edited or removed, including
    `test_example_keys_in_allowlist` (×4), `test_python_consumed_vars_in_allowlist`,
    `test_scheduler_health_stale_seconds_allowlisted`,
    `test_bypass_flags_absent_from_env_templates` (×2),
    `test_unknown_env_var_logs_warning` and `test_known_env_vars_no_warning`.
    `test_csrf_trusted_origins.py`, `test_prod_logging.py` and BLOCK 4's
    `test_deploy_check_env_parity.py` are likewise unmodified and green.
  - >
    **`.\\Makefile.ps1 test` passes**, and the **i18n completeness gate** — part of that
    run — passes. The block introduces no user-visible string: the template prose, the
    module docstring and the assertion messages are documentation and operator
    diagnostics, and are not translated anywhere in this codebase.
  - >
    `uv run ruff check src/` and `uv run basedpyright src/` are green. The new scan
    **narrows before it reads**: an `ast.NodeVisitor` subclass overriding `visit_Call`
    and `visit_Subscript`, or an `isinstance` guard on every attribute access. A bare
    `node.args` on a node from `ast.walk()` is not acceptable — `ast.walk()` yields
    `Iterator[AST]` and `AST` declares no `.args`, `.func` or `.value`. (Standing
    correction: a `[tool.basedpyright]` section **does** exist, at
    `typeCheckingMode = "standard"` with `reportAttributeAccessIssue = "none"`, so this
    would not fail the gate today; the requirement stands because the code is correct
    only by that project-wide suppression.)
  - >
    **`env.db()` is handled by the implicit-helper table, not by positional inspection.**
    A visitor that reads only `args[0]` is green and wrong — `env.db()` takes no
    positional argument and reads `DATABASE_URL` — so the table is consulted first, and
    `test_env_read_shapes_are_all_recognised` asserts that `DATABASE_URL` was actually
    resolved through it. Any *other* zero-argument `env.<attr>()` call fails the test by
    file and line instead of being skipped.
  - >
    `uv run ruff check src/` and `uv run basedpyright src/` are green. No new dependency,
    no new CI job, no settings-module body change, no compose file, no shell script, no
    Makefile target, and **no file under `.ai/audit/**` was read into the change, modified
    or restored**.
  - >
    The option-F deferral is recorded — in this task's `recorded_follow_ups` and as a
    hand-off item for the coordinator to fold into the plan's §5.2 — together with the
    reason it was not built here. It is a **known gap**, not a resolved question, and it
    is the general form of CFG-009's harm.
  - >
    Nothing was committed without an explicit user request, and only explicitly staged
    paths are in the commit (§1 hard rule — never `git add -A`).
```

**Why this shape.** The block's own notes treat G8 as a tooling question — regex versus a
curated list — and recommend Option B. The measurement says otherwise, and the reversal is
narrow and specific. Option B's automated half sweeps the settings package, which holds 35
of the 36 consumed names; the one it does not hold is exactly the variable the finding is
about. So Option B could only have closed CFG-008 through the hand-maintained constant it
also proposes, which is the anti-pattern BLOCK 4's shipped docstring argues against and
that VAL-004 names. The 33-vs-36 dispersion in §3.6, which drives the whole "a sweep is
inherently approximate" premise, is a line-anchored matcher's failure to see
`env(\n    "EMAIL_BACKEND",\n …)` — it misses the three variables whose reads wrap across
lines and nothing else. An AST walk returns one answer, has no false positives to disable,
and needs no second contract to stay true.

**The second half is smaller than the block describes, on purpose.** CFG-009 asks for the
missing blocks. D2 adds the one block whose absence breaks a boot and names the rest in
prose; D3 turns "which variables belong in which template" into a single derivable
sentence, so the two names the block's own notes trip over — `DATABASE_URL`, constructed by
Compose, and the bootstrap flags, already forbidden by a shipped test — need no exemption
entry. That is what keeps the block's durable surface to **one** production entry, **one**
comment, **one** test module, and two template edits. The `.env.example` retitle is also
the one change with a real VAL-003 hazard: the two keys the shipped substring tests pin
would survive being commented out, so the human re-read in the sequence is load-bearing,
not a nicety.

**What the coordinator should carry forward.** Three items, none of which this Planner may
write into §5 or §6: the option-F deferral (fold into §5.2); the fact that `.env.example`
and `.env.prod.example` are edited as **bytes** and that the latter is not valid UTF-8, so
any future template test must pass `errors="replace"`; and the coverage boundary, which
must survive into the phase summary — the scan sees the Python channel only, and the
shell, compose and `deploy-check` channels are each owned elsewhere or unowned, which is a
real residual, not a completed coverage story.

---

### BLOCK 7 — Pin `EMAIL_BACKEND` in production (CFG-004, half A)

| | |
|---|---|
| **Findings owned** | `CFG-004` — **half A only** (the unconditional re-pin) |
| **`depends_on`** | *(none)* |
| **Priority** | P1 — closes the harm class immediately |
| **Roster** | **Implementor, Validator** |

**Agent requirement decision (G3: half A is deliberately small).**
- **Implementor — yes.** Always.
- **Auditor — no.** The mechanism is reproduced, the asymmetry is identified (every other
  transport-relevant setting is pinned in `prod.py`; `EMAIL_BACKEND` is not), and the
  location is a single assignment.
- **Researcher — no.** The remedy is prescribed: re-pin exactly as `DEBUG` is pinned.
- **Planner — no.** One assignment plus one comment.
- **Validator — yes.** The change deliberately makes an existing env override inert.
  Someone relying on it would break silently, and the only evidence that is intentional
  is a test that asserts the override is **ignored** — not merely that the default
  resolved correctly.

**Findings and notes carried forward.**
1. **The pin must be unconditional**, matching `DEBUG = False`, and must sit with the
   other transport pins rather than near the email guard, so the file's own structure
   communicates that mail transport is not operator-configurable in production.
2. **`dev.py` and `test.py` overrides must be untouched** — console and locmem backends
   respectively. The pin is a `prod.py` assignment; the inherited value is overridden by
   the child module in both cases.
3. **The harm being closed is real and log-borne.** With the console backend selected,
   message bodies — password-reset tokens, seller confirmations, alert digests, support
   ticket free text — are written to stdout, which in production is the JSONL log stream.
   The `RedactingJsonFormatter` redacts *sensitive field values in log records*; it does
   not intercept a mail backend's writes.
4. **`test_prod_settings_email_accessible` gets stronger, not broken.** It builds its env
   with `EMAIL_BACKEND` already set to the SMTP backend and asserts the resolved value;
   under the pin it passes unchanged. The new test must set the env var to the
   **console** backend and assert the resolved value is still SMTP. That is the whole
   point.
5. **BLOCK 8 is the escape hatch, and it is conditional.** A deployment that genuinely
   needs a non-SMTP transport is broken by this block until BLOCK 8 ships or the operator
   reverts. The block's summary must state this explicitly so the coordinator can
   sequence BLOCK 8 if such a deployment exists — **and must ask before starting it.**

**File surface (semantic units).**
- `src/backend/config/settings/prod.py` → the transport-pin block (`DEBUG`,
  `SECURE_SSL_REDIRECT`, `SECURE_PROXY_SSL_HEADER`, `USE_X_FORWARDED_HOST`,
  `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS triple) — add `EMAIL_BACKEND` and a
  one-line comment stating why it is pinned.
- `src/backend/config/settings/tests/test_settings_secrets.py` → a new prod test for the
  override-is-ignored behaviour (or an existing prod test module).
- **Not touched:** `base.py`'s `EMAIL_BACKEND` read (it keeps the env default for
  dev/test), `dev.py`, `test.py`, `prod.py`'s `EMAIL_HOST` guard.

**Tests required.**
- *Must keep passing unchanged:* `test_prod_settings_email_accessible`,
  `test_prod_secret_key_accepts_strong_key`, and every other prod import test — all of
  them build environments that already satisfy the pin.
- *Must be added:* `EMAIL_BACKEND` set to the console backend +
  `DJANGO_SETTINGS_MODULE=config.settings.prod` → `settings.EMAIL_BACKEND` is the SMTP
  backend. Assert on the **resolved setting**, not on the absence of a warning.
- *Gate:* `$dc run --rm -e PYTEST_OPTS="src/backend/config/settings/tests" test`, then
  `.\Makefile.ps1 test`.

**Risk / rollback.**
- *Risk:* an operator relying on the override to reach a non-SMTP transport breaks. This
  is the finding's own stated rollout risk; note 5 makes BLOCK 8 the mitigation and
  makes asking a precondition.
- *Risk:* pinning in the wrong place (e.g. inside the `EMAIL_HOST` guard block) makes it
  conditional on a guard that the bypass can skip. **It must be an unconditional
  top-level assignment**, like `DEBUG`.
- *Rollback:* delete the assignment. One line, no state.

---

### BLOCK 8 — Closed `EMAIL_BACKEND` transport set (CFG-004, half B — **conditional**)

| | |
|---|---|
| **Findings owned** | `CFG-004` — **half B only** (the `EmailTransport` StrEnum) |
| **`depends_on`** | **BLOCK 7** |
| **Priority** | P2 — **do not start until the trigger fires** |
| **Roster** | **Implementor, Planner, Validator** |

**Activation trigger (all three must hold; otherwise this block does not run).**
1. A real deployment is identified that needs a non-SMTP transport, **or** the operator
   asks for one.
2. BLOCK 7 has landed, so the closed set is the *replacement* for an unpinned free-form
   string rather than a refinement of one.
3. The coordinator has confirmed the activation in writing.

**Rationale for not building it speculatively.** Project rule 5 (avoid
overengineering) outranks project rule 10 (StrEnum for constants) *until a value needs to
exist*. Right now `EMAIL_BACKEND` has exactly one legitimate production value, and
BLOCK 7 has already removed the ability to set an arbitrary one. Building the enum first
would create a second configuration surface — with its own template entries, its own
allowlist entry, its own validation, its own tests — to represent a set of size one.
If the trigger never fires, this block is correctly never executed and the enum is
correctly never written.

**Agent requirement decision.**
- **Implementor — yes.** Always — *if the block runs at all.*
- **Auditor — no.** The only places `EMAIL_BACKEND` can be set are `base.py`'s read,
  `dev.py`, `test.py`, `prod.py`'s pin, the templates and the compose files; all are
  already enumerated by this plan.
- **Researcher — no.** Whether a closed enum beats a free-form dotted path is not in
  doubt once the requirement for non-SMTP transport is established; the report states the
  benefit and there is no competing modern approach worth surveying.
- **Planner — yes.** The set of permitted transports, the unknown-backend failure mode
  (fail-fast at import, consistent with every other prod guard), the default, and the
  template/allowlist/doc surface all have to be decided together — and the failing-mode
  choice is what makes this a design task rather than a typing task.
- **Validator — yes.** A new closed set in production configuration. The Validator must
  confirm each permitted value resolves to a real backend and that an unknown value
  fails at import rather than at first send.

**Findings and notes carried forward.**
1. **The permitted set is unknown and is the Planner's to propose.** A plausible
   starting point is exactly what the project already uses across environments —
   `smtp` and `locmem` (and possibly `console` for a deliberate "dev-grade production"
   mode) — but this plan does not choose, because a wrong set is worse than no set.
2. **The unknown-value failure must be an import-time `ImproperlyConfigured`**, matching
   every other `prod.py` guard. A backend that fails at first send is the exact class of
   silent degradation this phase is about.
3. **`dev.py` and `test.py` must not be routed through the enum** unless the Planner
   explicitly decides they should. They set `EMAIL_BACKEND` directly and legitimately;
   routing them through a production allow-list would couple the dev environment to a
   production policy.
4. **The template, allowlist and doc surface follows the enum**: one env var
   (`EMAIL_TRANSPORT` or whatever is chosen) replaces the free-form `EMAIL_BACKEND` in
   `.env.prod.example`, and `ALLOWED_ENV_VARS` needs the new name. **`EMAIL_BACKEND` must
   stay allowlisted** while `base.py` still reads it, or the existing
   `test_example_keys_in_allowlist` breaks. Decide whether `EMAIL_BACKEND` remains
   readable at all in production.
5. **No user-visible string is introduced**, so the i18n DoD is not triggered — unless the
   value set is surfaced in an admin UI, which is out of scope.

**File surface (semantic units).**
- **New:** an `EmailTransport` `StrEnum` in the project's existing constants location
  for settings (check `src/backend/config/settings/` and `apps/core/enums.py`; follow
  whichever the project's rule-10 convention uses for settings constants — the Planner
  decides and states it).
- `src/backend/config/settings/prod.py` → the transport-pin block from BLOCK 7, now
  mapping the enum to a dotted path; a new unknown-value guard.
- `src/backend/config/settings/base.py` → `ALLOWED_ENV_VARS` (new name added; the old one
  retained or removed per note 4).
- `.env.prod.example` → the new variable, replacing the free-form backend path.
- **Not touched:** `dev.py`, `test.py`, `docker/entrypoint.sh`, any compose file.

**Tests required.**
- *Must keep passing unchanged:* BLOCK 7's override-is-ignored test **only if**
  `EMAIL_BACKEND` is removed from `prod.py`'s reachable inputs. If the enum replaces the
  free-form path, that test's premise changes and it must be rewritten **in the same
  change** — this is the block's one coupling to BLOCK 7 and it is mandatory.
- *Must be added:* one case per permitted transport resolving to the expected backend
  path; an unknown transport value failing at import; the default (unset) resolving to
  SMTP.
- *Gate:* `$dc run --rm -e PYTEST_OPTS="src/backend/config/settings/tests" test`, then
  `.\Makefile.ps1 test`.

**Risk / rollback.**
- *Risk:* the permitted set is too narrow and blocks a legitimate deployment. The
  activation trigger is the control; do not start the block speculatively.
- *Risk:* BLOCK 7's test is not rewritten and goes red. Same-change mandate.
- *Rollback:* revert to BLOCK 7's single unconditional assignment. The enum is additive
  and self-contained.

---

### BLOCK 9 — Dead static-files setting and the test-settings transport tuple (CFG-007 + CFG-010)

| | |
|---|---|
| **Findings owned** | `CFG-007`, `CFG-010` |
| **`depends_on`** | *(none)* |
| **Priority** | P2 — opportunistic, as the report directs |
| **Roster** | **Implementor, Validator** |

**Agent requirement decision.**
- **Implementor — yes.** Always.
- **Auditor — no.** Both findings are fully characterised and re-confirmed at the anchor:
  `STATICFILES_STORAGE` is absent from the installed Django's `global_settings` and
  referenced by no security check, so it is silently inert; and `test.py` inherits
  `SECURE_HSTS_SECONDS=3600` / `INCLUDE_SUBDOMAINS=True` from `base.py` while its own
  comment claims to mirror `dev.py`, which zeroes the triple. Nothing is unknown.
- **Researcher — no.** G7 (the parity assertion's mechanism) is **decided**: subprocess
  isolation in `test_settings_defaults.py`, matching every other settings test in the
  package and that file's existing pattern. No external question remains.
- **Planner — no.** One deletion plus one comment correction, three assignments, and one
  parity assertion, all with named locations.
- **Validator — yes.** CFG-010 changes settings the whole suite runs under. A transport
  header that appears in a test response where none appeared before is exactly the kind
  of change that is invisible in a green suite.

**Grouping decision and its justification.**
`CFG-007` and `CFG-010` are both settings-module hygiene in the same three files, both
LOW, and the report explicitly asks for CFG-010 to be *"absorbed into whatever
settings-test change lands"* rather than scheduled. This is that absorption point: the
settings-test work is already done, so CFG-010 is scheduled after all — as a pairing
with a same-shaped, same-file change. The alternative (two separate trivial blocks) would
cost two review passes over `test.py` for three lines.

**Findings and notes carried forward.**
1. **The deletion is safe because the effective configuration is owned elsewhere.**
   `base.py`'s `STORAGES["staticfiles"]["BACKEND"]` already carries the same
   `theme.storage.ThemeStaticFilesStorage` value, so removing the dead key changes
   nothing observable — and the new pinning test is what proves it.
2. **The new pinning test asserts the real decision**, not the deleted line's absence.
   Asserting "`STATICFILES_STORAGE` is not set" would pass on a build where the storage
   backend silently reverted to Django's default. Assert `STORAGES["staticfiles"]["BACKEND"]`
   is the theme backend.
3. **`test.py`'s storage comment misattributes its subject.** It reasons at length about
   *"the production/dev storage"* while `test.py` itself overrides `STORAGES` — so the
   comment is about `base.py`'s dict, not `prod.py`'s deleted line. Correct the comment's
   subject while deleting the line; otherwise a future reader "fixes" `prod.py` again.
4. **The HSTS reset is three assignments** mirroring what `dev.py` sets, placed under the
   existing "Mirrors config/settings/dev.py" comment so the comment becomes true rather
   than aspirational. **`test_migrations.py` does `from .test import *` and inherits
   every one of them** — the Planner must state whether that is intended (it almost
   certainly is) and whether the parity assertion should also cover it.
5. **The parity assertion compares `config.settings.dev` and `config.settings.test` on the
   full transport tuple** — `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`,
   `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`, `SECURE_HSTS_INCLUDE_SUBDOMAINS`,
   `SECURE_HSTS_PRELOAD` — via two subprocess imports. Name the settings as a module-level
   constant (project rule 10), not as inline literals.
6. **The pytest suite is unaffected today** (`SECURE_SSL_REDIRECT` is already `False`, so
   the test client's plain HTTP is not redirected, and the test client is not subject to
   browser HSTS caching). The exposure is to a browser-driven tool pointed at a
   test-mode server. The Validator's check is therefore a **response-header** assertion,
   not a suite assertion.
7. **`test.py` is a deliberately divergent module** — `DEBUG = True`, migrations disabled,
   storage and mail backends overridden. This block does not attempt to make it resemble
   `prod.py`; it makes it resemble `dev.py`, which is what the comment always claimed.

**File surface (semantic units).**
- `src/backend/config/settings/prod.py` → the `STATICFILES_STORAGE` assignment
  (**delete**) and its comment.
- `src/backend/config/settings/test.py` → the "Mirrors config/settings/dev.py" block
  (add the HSTS triple); the `STORAGES` comment (correct its subject).
- `src/backend/config/settings/tests/test_settings_defaults.py` → the transport-tuple
  parity assertion and its named settings constant.
- **Not touched:** `base.py`'s `STORAGES` dict, `dev.py` (it is the reference side of the
  parity), `test_migrations.py`, `docker/Dockerfile` (the builder runs `collectstatic`
  and needs the manifest the theme backend produces).

**Tests required.**
- *Must keep passing unchanged:* every test in
  `src/backend/config/settings/tests/**`; every view test that issues a request through
  the test client (a transport-header change can surface here); `test_migrations.py`'s
  suite via the inherited settings.
- *Must be added:*
  - Under `config.settings.prod`, `STORAGES["staticfiles"]["BACKEND"]` is
    `theme.storage.ThemeStaticFilesStorage` — the real decision, pinned.
  - `config.settings.dev` and `config.settings.test` agree on all six transport settings
    (subprocess-isolated, named constant).
- *Need no test:* the absence of `STATICFILES_STORAGE` — see note 2.
- *Gate:* `$dc run --rm -e PYTEST_OPTS="src/backend/config/settings/tests" test`, then
  `.\Makefile.ps1 test` (the full sweep matters here: `test.py` is imported by every
  test).

**Risk / rollback.**
- *Risk:* deleting the wrong line and breaking static-file collection in the **builder**
  stage. The `STORAGES` dict in `base.py` is the effective configuration and the pin test
  is the guard; the Validator must confirm the Docker build still runs `collectstatic`
  successfully, or at minimum that `STORAGES` is untouched.
- *Risk:* the HSTS reset changes response headers across the whole suite. The full-sweep
  gate is the control.
- *Rollback:* the deletion and the three assignments are independently revertible.

---

### BLOCK 10 — Admin-creation command contract (CFG-003 + VAL-002)

| | |
|---|---|
| **Findings owned** | `CFG-003`, `VAL-002` (re-scoping constraint) |
| **`depends_on`** | *(none)* — but sequenced last, and **de-scopable to zero** |
| **Priority** | P3 |
| **Roster** | **Implementor, Researcher, Planner, Validator** |

**De-scoping gate (read before starting).**
This block is the phase's lowest-severity finding and its impact was **refuted by the
validator**: the credential is already in cleartext in the container's environment via
`env_file`, verified against the live container, so `docker inspect` already returns the
plaintext. Removing it from `argv` reduces the exposure by **zero**. The coordinator may
record CFG-003 as *accepted, no change* and skip this block entirely. If it is recorded
that way, the only requirement is that §8 records the decision and the reasoning.

**Agent requirement decision.**
- **Implementor — yes.** Always.
- **Auditor — no.** Every touch point is named: the entrypoint's skip branch, the
  command's `--password` argument, and the `env_file` channel. The blast radius is one
  one-shot container and one management command.
- **Researcher — yes.** One bounded question: **if the goal is to stop the credential
  appearing in `docker inspect`, what is the mechanism?** Docker Compose `secrets`, a
  file-mounted credential the command reads, or a stdin/FD handoff each have different
  operational costs (image rebuild for file mounts, swarm-mode-only semantics for some
  secret backends, an orchestrator dependency for others). This determines whether option
  B below is even feasible on this deployment. See §3.10.
- **Planner — yes.** The three options have materially different scope, and the one that
  actually closes the exposure is a deployment-contract change touching compose, the
  entrypoint, the command, the templates and the ops documentation.
- **Validator — yes.** Whatever is chosen changes a production bootstrap path. The
  empty-password skip is a load-bearing behaviour that must survive, and the Validator
  must confirm both the `--password`-present and `--password`-absent paths.

**3.10 — What, if anything, to change (open choice; recommendation, not a decision).**

| Option | Change | Effect | Cost |
|---|---|---|---|
| **A (recommended if the block runs)** | Make `--password` **optional**; the command falls back to `ADMIN_PASSWORD` from the environment when the flag is absent. Keep the entrypoint's empty-password skip. | Command-contract hygiene: a secret is no longer *forced* through `argv`. The real exposure is unchanged. | Low. Two files. Backward compatible (the flag still works). **Must not be described as reducing exposure** — `VAL-002`. |
| **B** | Replace the `env_file` channel with a file-mounted credential or a Docker secret that the command reads. | **Actually** removes the plaintext from `docker inspect`. | High: compose, entrypoint, command, `.env.prod.example`, `ALLOWED_ENV_VARS` semantics, and `docs/ops/docker-deployment.md` — which is **currently modified in the working tree** (see §6). Requires the Researcher's feasibility answer. |
| **C** | No change; record CFG-003 as accepted. | Nothing. | Zero. Defensible: the finding's stated impact is refuted. |

**Recommendation:** Option A if the coordinator wants the hygiene; Option C is equally
defensible. **Option B is the only one that changes the exposure** and should not be
attempted without the Researcher's feasibility answer and an explicit scope decision.

**Findings and notes carried forward.**
1. **`VAL-002` is binding.** Whatever is chosen, the block's summary and the commit
   message must state that the `env_file` channel is the real exposure and that this
   change does not address it. Shipping option A with a message claiming the credential
   "no longer appears in `docker inspect`" would be a false claim in the permanent record.
2. **The empty-password skip is load-bearing** and must be preserved exactly: no
   `ADMIN_PASSWORD` → log, exit 0, no admin created.
3. **`ADMIN_PASSWORD` is already classified** in `ALLOWED_ENV_VARS` under the
   shell/entrypoint/compose-injected group, so the current design accepted this channel
   deliberately. Option A does not move it; option B might.
4. **The threat model in the source finding has no concrete instance here** — the
   container is a single-process one-shot, so "a sidecar, a debugger, a crash handler
   that captures argv" does not exist. Do not carry that framing into the commit.
5. **Option A introduces no user-visible string**; a new management command would
   follow the existing convention (English, untranslated `help`).

**File surface (semantic units).**
- `docker/entrypoint-create-admin.sh` → the `create_admin_user` invocation and the
  empty-password skip (**preserve**).
- `src/backend/apps/core/management/commands/create_admin_user.py` → the `--password`
  argument definition and the resolution order.
- **Option B only:** the `create_admin` service block in `docker-compose.prod.yml` and
  `docker-compose.yml`; `.env.prod.example`; `src/backend/config/settings/base.py`'s
  `ALLOWED_ENV_VARS`; `docs/ops/docker-deployment.md` (**dirty — coordinate**).
- **Not touched:** `SiteConfig`, the admin model, any other service.

**Tests required.**
- *Must keep passing unchanged:* every existing `create_admin_user` test; the entrypoint
  script's own tests if any.
- *Must be added (option A):* the command resolves the password from the environment
  with `--password` absent; it still resolves from `--password` when present; and an
  absent-and-empty `ADMIN_PASSWORD` preserves the skip path.
- *Need no test (option C):* none.
- *Gate:* `$dc run --rm -e PYTEST_OPTS="src/backend/apps/core/tests" test` for option A;
  for option B, `docker compose … config` for the prod stack in addition.

**Risk / rollback.**
- *Risk:* shipping option A with a claim it does not support. `VAL-002` is binding.
- *Risk:* the empty-password skip is broken and the container fails its bootstrap step.
  That is a visible, loud failure — which is the correct direction, but it is tested.
- *Risk:* option B is started without the feasibility answer and strands the deployment.
  The Researcher's answer is a precondition.
- *Rollback:* one script and one command; fully reversible.

#### BLOCK 10 — Implementation task

> Written by the BLOCK 10 Planner against the tree at `da399d7` (BLOCK 7 = `d42f778`,
> BLOCK 9 = `da399d7`; BLOCK 8 not taken).
> **Never use line numbers** — every target below is a file, module, class, method,
> command-line argument, shell branch or prose sentence.
>
> **The scope decision is already taken: Option A.** The coordinator accepted
> `--password` becoming optional with an `ADMIN_PASSWORD` environment fallback, the
> entrypoint's empty-password skip preserved exactly, and **Option B (file-mounted
> credential or Docker secret) explicitly out of scope**. Option C was considered and
> rejected: leaving `--password` `required=True` means the *only* possible way to invoke
> the command forces a secret through `argv`. That is a real command-contract defect, it
> is cheap to fix, and the fix is backward compatible. §3.10's de-scoping gate is
> therefore satisfied and the block runs.
>
> **This subsection supersedes §3.10's open choice table, the "Findings and notes carried
> forward" list, the "File surface (semantic units)" list and the "Tests required" list
> above it wherever they disagree.** It is an append; nothing above it is edited. Five of
> its rulings change that text: **D1** fixes the resolution order, **D2** makes the
> fallback trigger on *absence* and never on falsiness (this is what keeps two shipped
> green tests green), **D3** keeps the environment read on `os.environ` and out of the
> settings layer so `ALLOWED_ENV_VARS`' classification is unchanged, **D4** forbids a
> second error message, and **D6** splits the new coverage into a *behavioural* test for
> the skip path and a *static* test for the invocation, because only one of the two is
> executable in the test container.
>
> **Measured at `da399d7`, by this Planner, independently of the Auditor and the
> Researcher:** the script runs `set -euo pipefail`, so an **unset** `ADMIN_PASSWORD` makes
> `[ -z "${ADMIN_PASSWORD}" ]` a `set -u` unbound-variable error and the container exits 1
> — only the **set-but-empty** case reaches the skip. Compose always defines it, so the
> empty case is the real one. There is **no** test anywhere in the tree that references
> `entrypoint-create-admin.sh`: the "the entrypoint script's own tests if any" clause in
> §3.10 resolves to **none**, so the new script test is that file's *first* coverage
> (§3.10's tests list is corrected in `corrections_to_block_notes`).

```yaml
id: block10-cfg003-admin-password-command-contract

title: >
  Make --password optional in create_admin_user and fall back to ADMIN_PASSWORD from
  the environment, and stop passing the secret through argv in the create_admin
  entrypoint (CFG-003, re-scoped per VAL-002)

priority: P3

depends_on:
  - "BLOCK 7 (d42f778) and BLOCK 9 (da399d7) — landed. Neither touches the admin bootstrap path; recorded so the Implementor does not re-derive a dependency that does not exist. BLOCK 8 was not taken."
  - "No hard edge on BLOCK 6 (e57f8f8), but a LIVE INTERACTION that must be verified: BLOCK 6's shipped test_env_allowlist_reverse.py walks every non-test src/**/*.py by AST and asserts consumed ⊆ ALLOWED_ENV_VARS. This block adds the first Python read of ADMIN_PASSWORD anywhere in the tree. It stays green (D3) and that green run is a required gate, not an assumption."

source_reference: .ai/plans/02-config-secrets-remediation.md
source_section: "BLOCK 10 — Admin-creation command contract (CFG-003 + VAL-002)"
source_file: .ai/audit/99-validation/02-config-secrets-validated-findings.md
source_blocks:
  - "BLOCK 10 — Admin-creation command contract (CFG-003 + VAL-002)"
  - "§3.10 — What, if anything, to change (open choice table): Option A taken, Option B out of scope, Option C rejected"
  - "CFG-003 — Admin password passed as management-command argv, down-graded MEDIUM → LOW and reclassified to BEST-PRACTICE by the validator"
  - "VAL-002 — binding constraint: the recommended fix does not close the exposure it names, and would create false assurance"
  - "V13 / A.8 — docker inspect on the live create_admin container: ADMIN_PASSWORD is present in Config.Env (the impact refutation)"

description: >
  `create_admin_user` declares `--password` with `required=True`. That single keyword is
  the whole of CFG-003 after the validator's re-scoping: with it set, **every** possible
  invocation of the command must carry the admin password in `argv`, because there is no
  other way to satisfy argparse. The `create_admin` one-shot does exactly that — it
  `exec`s `manage.py create_admin_user --username … --password "${ADMIN_PASSWORD}" …`.

  **What this change is:** command-contract hygiene. `--password` becomes optional and
  the command reads `ADMIN_PASSWORD` from the process environment when the flag is
  absent, so the secret is no longer *forced* through `argv`. The entrypoint stops
  passing it. That is the entire scope: two production files, four lines of resolution
  logic, and no behaviour change for any existing caller.

  **What this change is not, and may never be described as (VAL-002, binding):** it does
  not reduce the credential's exposure, by exactly zero. The `create_admin` service
  receives the password through `env_file: .env.prod` in `docker-compose.prod.yml` and
  through `ADMIN_PASSWORD=${ADMIN_PASSWORD:-}` in `docker-compose.yml`, so the plaintext
  is **already** in the container's `Config.Env` and `docker inspect` **already** returns
  it — verified against the live container by the validator (V13 / A.8). Moving the value
  from `argv` to the environment crosses no additional privilege boundary: inside the
  container, `/proc/1/environ` is readable by the same uid that could read
  `/proc/1/cmdline`. A commit message, code comment or docstring claiming the credential
  "no longer appears in `docker inspect`" is a **false claim in the permanent record** and
  is prohibited by `acceptance_criteria` and by BC-1/BC-2.

  **The one behaviour that must not move** is the entrypoint's empty-password skip: a
  container that is not given an admin password logs, exits 0, and creates no user. That
  is what makes the one-shot safe to leave on the production boot path, and it currently
  has **zero** test coverage anywhere in the tree. D6 gives it a behavioural test.

goals:
  - >
    `--password` is no longer `required`. The command resolves the password as:
    an explicitly supplied flag value wins, even when it is empty; otherwise
    `ADMIN_PASSWORD` from the process environment; otherwise the existing
    empty-password validation fires.
  - >
    The entrypoint's `create_admin_user` invocation no longer passes `--password`. The
    empty-password skip branch — its `-z` test, its log line and its `exit 0` — is
    preserved byte-identical.
  - >
    Every existing test in `test_create_admin_user.py` keeps passing **without being
    edited, renamed or skipped**, including the two that supply an empty or
    whitespace-only `--password` and expect a `CommandError`.
  - >
    `create_admin_user` is covered for the first time by a test that reads the
    environment fallback, and that test is **seen red** against the pre-change command
    before it is seen green.
  - >
    `docker/entrypoint-create-admin.sh` is covered for the first time by a test that
    **executes** the script and observes exit 0, the skip log line, and the command
    never being launched.
  - >
    Nothing claims a reduction in exposure. The commit message, every comment this
    change introduces, and the hand-off all state that the `env_file` channel is the real
    exposure and that this change does not address it.

# ─────────────────────────────────────────────────────────────────────────────
# Decisions taken by the BLOCK 10 Planner
# ─────────────────────────────────────────────────────────────────────────────
decisions:
  - id: "D1 — Option A, scoped to exactly the argv-forcing contract. Three lines of resolution."
    choice: >
      `--password` becomes `required=False, default=None`. `handle` resolves:

          password = (
              options["password"]
              if options["password"] is not None
              else os.environ.get("ADMIN_PASSWORD", "")
          )

      and everything downstream of that line is unchanged. The module docstring's
      `Usage:` block, the `--password` `help` text, and the entrypoint's exec line are
      updated to match. Nothing else in the command is touched — not the advisory lock,
      not the two idempotency early-returns, not `set_password`, not the stdout/masking
      discipline.
    rationale: >
      `default=None` (not `default=""`) is what makes D2 expressible, and `os.environ
      .get(..., "")` (not `os.environ.get(...)` bare) is what makes the absent-env case
      land on the existing empty-password branch instead of a new one. The alternative
      shapes were a second `--password-from-env` flag (two ways to do one thing, and the
      operator must now know which), and reading through `django.conf.settings` (rejected
      by D3).
    rejected:
      - "Option B — replace the env_file channel with a file-mounted credential or a Docker secret. The only option that changes the real exposure, and explicitly OUT OF SCOPE by coordinator decision. Its feasibility question is Option B's precondition and this block does not answer it (see BC-9)."
      - "Option C — no change, CFG-003 recorded as accepted. Rejected by the coordinator: with --password required=True the only possible invocation forces a secret through argv, which is a real command-contract defect, cheap to fix, and backward compatible."

  - id: "D2 — The fallback triggers on ABSENCE (`is None`), never on falsiness. This is what keeps two shipped green tests green."
    choice: >
      The condition is `options["password"] is not None`, never `if not
      options["password"]` and never `options["password"] or os.environ.get(...)`.
    rationale: >
      `test_empty_password_raises_error` calls the command with `password=""` and
      `test_empty_password_whitespace_only_raises_error` with `password="   "`, both
      expecting `CommandError`. Under a falsiness-triggered fallback, an operator who
      passes `--password ""` while `ADMIN_PASSWORD` happens to be set in the environment
      would silently get a **different** password than the one they typed — a worse
      outcome than the original defect, and one the existing tests would not catch. The
      empty value must keep reaching the existing validation.
    consequence: >
      This is a **test-visible** property, not an internal detail:
      `test_empty_password_flag_does_not_fall_back_to_environment` is a required new
      test, and it is the assertion that keeps D2 from being refactored away later.

  - id: "D3 — The environment is read from `os.environ` directly, never through django-environ or `django.conf.settings`."
    choice: >
      `os.environ.get("ADMIN_PASSWORD", "")`, in the command module.
    rationale: >
      Three reasons, in order.

      **(1) It is what `ALLOWED_ENV_VARS` already says.** `config/settings/base.py`
      classifies `ADMIN_PASSWORD` under the group commented
      `--- Shell/entrypoint/compose-injected (not consumed by Python env()) ---`. That
      classification is a deliberate statement that this variable is *not* a settings-layer
      input. Routing it through `env()` or `django.conf.settings` would silently
      reclassify it as one — and the group comment would become false the day the change
      lands, which is exactly the "grouping that contradicts itself" failure BLOCK 6
      recorded against `base.py`. Option A does not move the variable; D3 keeps that true.

      **(2) It is correct at the point of use.** The value arrives in the process
      environment from Compose (`env_file` in prod, `environment:` in base and test) and
      is needed by a one-shot container that imports settings but is not a settings
      consumer.

      **(3) It keeps BLOCK 6's shipped reverse scan green with no edit to it.**
      `test_env_allowlist_reverse.py` walks every non-test `src/**/*.py` by AST and
      recognises four read shapes; `os.environ.get(...)` is one of them
      (`_RECOGNISED_READ_SHAPES`, shape label
      `"os.getenv(...) / os.environ.get(...)"`), and `ADMIN_PASSWORD` is already in
      `ALLOWED_ENV_VARS`. `test_consumed_env_vars_are_allowlisted` therefore stays green
      and **no BLOCK 6 file is touched**. This is measured, not assumed — it is a
      required gate in `tests.verification_gate`.

  - id: "D4 — The existing empty-password error message is not changed, and no second message is added."
    choice: >
      Absent flag **and** absent/empty `ADMIN_PASSWORD` resolves to `""` and falls into
      the existing `CommandError("Password cannot be empty. Please provide a valid
      password.")`. No new branch, no new message, no special case.
    rationale: >
      One condition, one error. The existing text is already accurate — there is no
      password, which is what "cannot be empty" says — and the `--password` help text and
      the module docstring now name the environment fallback, so the operator is told
      where the value may come from. A distinct "you passed no flag" message would be a
      second code path for a situation the existing branch already describes, and it would
      be the kind of growth project rule 5 exists to prevent. (`pytest.raises(match=...)`
      is a `re.search`, so extending the sentence would also have been safe — the point is
      not to grow the code, not a technical blocker.)
    note: >
      If the Implementor nonetheless judges the message misleading, the **prefix
      `Password cannot be empty` must be preserved byte-identical** (both shipped tests
      match on it) and the change must be reported in the hand-off. Preferred outcome is
      no change at all.

  - id: "D5 — The entrypoint stops passing `--password`. The skip branch is preserved byte-identical, including its wording."
    choice: >
      Only the `exec` invocation changes: the `--password "${ADMIN_PASSWORD}"` line and
      its backslash continuation are removed. The `if [ -z "${ADMIN_PASSWORD}" ]; then …
      echo …; exit 0; fi` block, the `set -euo pipefail`, the `source` of
      `entrypoint.sh`, the four setup calls, the header comments and the `exec` keyword
      itself are byte-identical.
    rationale: >
      The value is still in the container's environment after the change, so the command's
      fallback resolves it: `docker-compose.yml`'s `create_admin` passes
      `ADMIN_PASSWORD=${ADMIN_PASSWORD:-}`, `docker-compose.prod.yml` supplies
      `env_file: .env.prod`, and `docker-compose.test.yml` sets it explicitly. The skip
      branch reads the *same* variable it always did, so the skip and the create now
      agree by construction rather than by two different channels.
    do_not_edit:
      - "The `-z` test, the echo line, the `exit 0`, the `fi`, their order and their indentation"
      - "The `check_env_file` / `fix_volume_permissions` / `wait_for_db` / `wait_for_redis` call sequence"
      - "The `source \"${SCRIPT_DIR}/entrypoint.sh\"` line and the `shellcheck source=` directive above it"
      - "The three header comment lines"
      - "The `--username` and `--telegram-id` arguments and their `${VAR:-default}` defaults"

  - id: "D6 — The skip path gets a behavioural test; the invocation gets a static one. The split is forced by what is executable in the test container."
    choice: >
      **Behavioural** (`test_script_exits_zero_when_admin_password_is_empty`): the real
      script is copied into `tmp_path` beside a **stub** `entrypoint.sh` defining the four
      setup functions as no-ops, and executed with `bash` under a **scrubbed** environment
      (`PATH`, `HOME`, and `ADMIN_PASSWORD` only). It asserts exit 0, the skip log line on
      stdout, and that `create_admin_user` never appears in the output.
      **Static** (`test_script_does_not_pass_the_password_on_the_command_line`): the
      script text is read and asserted for `--password` absence, `--username` and
      `--telegram-id` presence, the `${VAR:-default}` forms, and the `exec` keyword.
    rationale: >
      The skip branch is the block's only load-bearing pre-existing behaviour and it has
      **zero** coverage today. A substring assertion over the file would be the first and
      only evidence, and it is satisfiable by a reworded log line — exactly the weakness
      BLOCK 9 recorded for substring template tests. The branch is cheap to run for real:
      `bash` is present in the test image (`python:3.14-slim`; every entrypoint is
      `#!/bin/bash`), the guard executes **before** any Python, and the script's
      `source "${SCRIPT_DIR}/entrypoint.sh"` resolves against the copy's own directory —
      which is precisely why the stub is placed beside it. The invocation, by contrast,
      needs a database, Redis and `/opt/venv/bin/python`, so it cannot be executed; a
      static assertion is the honest form there, not a compromise.
    precedent: >
      `apps/core/tests/test_scheduler_wiring.py` is the precedent for reading a shell
      script from disk and asserting on its text, and for the module-level pytest marker
      (`pytest.mark.unit`, no DB). The new module copies that shape.
    why_not_one_module: >
      `test_create_admin_user.py` carries `pytestmark = [pytest.mark.django_db,
      pytest.mark.integration]` at module level. Adding a pure-shell test there would
      drag a database and an integration marker onto a test that needs neither, and would
      put the executable test and the argv-removal static test in different execution
      classes for no reason. Two modules, two responsibilities (project rule 4).

# ─────────────────────────────────────────────────────────────────────────────
# Binding constraints
# ─────────────────────────────────────────────────────────────────────────────
binding_constraints:
  - id: BC-1
    title: "VAL-002 honesty — binding on the commit message and on every comment this change introduces."
    rule: >
      The commit message, the block summary, and **every** comment, docstring and
      `# ...` shell comment the change adds must state that the `env_file` channel is the
      real exposure and that this change does not address it. Specifically: the credential
      is **already** in cleartext in the container's environment via `env_file` (verified
      against the live container), so `docker inspect` already returns the plaintext;
      moving the value out of `argv` reduces the exposure by **exactly zero**. Any claim
      that the credential "no longer appears in `docker inspect`", that the value is "no
      longer visible to the host", or that this "removes the secret from the process
      table" is a **false claim** and must not appear in the commit message, in any code
      comment, in any docstring, in the test docstrings, or in the hand-off.
    verbatim_source: >
      VAL-002 (MEDIUM) — "CFG-003's recommended fix does not close the exposure it names,
      and would create false assurance." Required fix: re-scope CFG-003 to LOW
      defense-in-depth / command-contract hygiene, and state that the goal of stopping the
      credential appearing in `docker inspect` requires scoping the fix to the `env_file`
      channel, "which is the only change that reduces the real exposure."
  - id: BC-2
    rule: >
      **The source finding's threat model must not be carried into the change.** The
      container is a single-process one-shot, so "a sidecar, a debugger, a crash handler
      that captures argv" has no concrete instance in this deployment. Neither the commit
      message nor a comment may assert one.
  - id: BC-3
    rule: >
      The empty-password skip is **byte-identical** after the change. Not re-indented, not
      re-wrapped, not re-commented, not re-ordered, not "cleaned up". `change_skip_branch`
      is an `assert unchanged` action, not an edit.
  - id: BC-4
    rule: >
      Backward compatibility is proven, not asserted. `--password` still works exactly as
      before, and `Makefile.ps1` / `Makefile`'s `Invoke-CreateAdmin` — which passes
      `--password $env:ADMIN_PASSWORD` — is **not edited** and is the compatibility
      witness. `test_create_admin_user.py` is not edited, renamed, reordered or skipped;
      project rule 2 applies (fix production code, never distort a test).
  - id: BC-5
    rule: >
      `config/settings/base.py` is **not touched**. `ADMIN_PASSWORD` stays in the
      `--- Shell/entrypoint/compose-injected (not consumed by Python env()) ---` group,
      with the group comment unchanged. The allowlist is BLOCK 3's grouping and BLOCK 6's
      contract; this block adds a read that those contracts already permit.
  - id: BC-6
    rule: >
      No credential-shaped literal is introduced. Test values come from
      `docker-compose.test.yml`'s existing `test-admin-password` literal (already covered
      by `.gitleaks.toml`'s `[[allowlists]]` regex `test-admin-password`) or from
      `monkeypatch.setenv` with an obviously non-credential value. **Never read, print,
      quote or transcribe a value from a real `.env.*`** (§1) — key names only.
  - id: BC-7
    rule: >
      No `pytest.skip`, no `xfail`, no conditional skip anywhere in the new or edited
      test modules. A test that finds nothing and passes is worse than no test, and no
      rung of the fail-closed ladder may be open.
  - id: BC-8
    rule: >
      Out of scope, untouched, and named here so a reviewer does not look for them:
      `SiteConfig`, the admin model and its `UserAdmin`, `User.set_password`, the advisory
      lock, every other service, every compose file, `docker/entrypoint.sh`,
      `Makefile` / `Makefile.ps1`, `config/settings/**`, `docs/**`, and anything under
      `.ai/audit/**`. No new dependency, no CI change, no migration, no user-visible
      string — the management-command `help` text is English and untranslated by existing
      convention (verified: no `gettext` import in any of the `apps/core/management/
      commands/*.py` modules), so §1's i18n rule is satisfied without a `.po` change.
  - id: BC-9
    rule: >
      **No Researcher pass is required for this block, and this task does not wait for
      one.** §3.10 required a Researcher for exactly one question — "if the goal is to stop
      the credential appearing in `docker inspect`, what is the mechanism?" — and stated
      that the answer is a precondition of **Option B**. The coordinator took Option A and
      put Option B out of scope, so the question is a precondition of a branch that is not
      being taken. Requiring it would gate a two-line change on an answer nothing in this
      block consumes. The Validator **is** still required: the block changes a production
      bootstrap path and the skip path is load-bearing.

# ─────────────────────────────────────────────────────────────────────────────
corrections_to_block_notes:
  - >
    **§3.10's "the entrypoint script's own tests if any" resolves to NONE, and this
    Planner measured it rather than assuming it.** No file under `src/` references
    `docker/entrypoint-create-admin.sh` in any test: the only matches anywhere are the
    script itself, the four compose files that point an `entrypoint:` at it, and the
    `.ai/` plan and audit documents. `test_docs_ci_parity.py` reads `entrypoint-test.sh`
    only; `test_compose_hardening.py` and `test_health_contract.py` assert on
    `entrypoint-scheduler.sh` and `healthcheck-scheduler.sh` only. So "keep them passing"
    is vacuous, and the new script test is that script's **first** coverage in the
    repository's history. Treat it as a net-new contract, not a regression guard.
  - >
    **Note 2's "no `ADMIN_PASSWORD` → log, exit 0, no admin created" is imprecise, and
    the imprecision matters to the new test.** `entrypoint-create-admin.sh` runs
    `set -euo pipefail` (its parent `entrypoint.sh` runs only `set -e`). Under `set -u`,
    expanding an **unset** `${ADMIN_PASSWORD}` is an unbound-variable error: the `[ -z
    ... ]` test aborts the script with a non-zero status and the skip is never reached.
    Only the **set-but-empty** case reaches the skip. In practice the variable is always
    defined — `docker-compose.yml`'s `create_admin` passes
    `ADMIN_PASSWORD=${ADMIN_PASSWORD:-}`, which is defined-and-empty when the operator
    has not set one, and `docker-compose.test.yml` sets it explicitly — so the empty case
    is the real trigger and the log line's "not set" is a slight over-statement. **Not a
    defect to fix in this block** (it is a load-bearing branch and rewording it is BC-3's
    opposite), but the new behavioural test must assert the **empty** case and must not
    assert something untrue about the unset case. If the Implementor wants to note the
    distinction, it goes in the test's docstring, not in the script.
  - >
    **§3.10's "File surface" lists two files; the real surface is four.** It omits (a) the
    command's **module docstring**, whose `Usage:` block still shows
    `--password <password>` as a mandatory flag and would become a false instruction the
    moment the flag becomes optional, and (b) **two test modules** — the existing
    `test_create_admin_user.py`, which is appended to and not edited, and a new
    `test_create_admin_entrypoint.py`. See `files`.
  - >
    **§3.10's "Not touched" list is correct, and a fifth item joins it:**
    `Makefile.ps1` / `Makefile`'s `Invoke-CreateAdmin` target also invokes
    `create_admin_user --password …` from a developer shell. It is not a change site; it
    is the **compatibility witness** for BC-4 and it must keep working unchanged.
  - >
    **§3.10's roster line "Researcher — yes" is void for this block.** Its single question
    was Option B's feasibility precondition. Option B is out of scope by coordinator
    decision, so the question is not a precondition of the work being shipped. See BC-9.
    The "Validator — yes" line **stands** and is a duty, not a formality.
  - >
    **§3.10's de-scoping gate is satisfied and the block runs.** The coordinator chose
    Option A. Nothing in this task re-opens that decision, and nothing in it is a
    feasibility question about Option B.

recorded_follow_ups:
  - >
    **The real exposure — the `env_file` channel — is NOT addressed by this block, and is
    named here as the follow-up if anyone wants it closed.** `docker-compose.prod.yml`'s
    `create_admin` service carries `env_file: .env.prod` and mounts
    `./.env.prod:/app/src/.env:ro`; `docker-compose.yml` carries `env_file: .env.dev` and
    `ADMIN_PASSWORD=${ADMIN_PASSWORD:-}`. The plaintext is therefore in `Config.Env`
    today, and `docker inspect` returns it today and after this change. Closing it is
    Option B: a Docker secret or a file-mounted credential that the command reads, which
    reaches compose, the entrypoint, the command, `.env.prod.example`, the *semantics* of
    `ALLOWED_ENV_VARS` (the variable would leave the shell/compose group and enter a
    file-mount group), and `docs/ops/docker-deployment.md` — and which first needs the
    feasibility answer this block does not provide. The coordinator should fold this into
    §5.2 of the plan; this Planner appends to BLOCK 10 only.
  - >
    **`test_requires_username_and_password` becomes over-broad by name, and is
    deliberately not renamed.** After this change only `--username` is required. The test
    calls the command with no arguments and asserts a `CommandError` matching
    `--username`; that assertion is still exactly right, so the test keeps passing
    unchanged (BC-4). Only the *name* and its docstring phrase "required arguments" now
    over-claim. Renaming a shipped test to match a change in the same commit is a
    reviewer-visible way to hide a behaviour change behind a cosmetic edit, so it is
    recorded here instead. A follow-up may rename it on its own.
  - >
    **`test_env_allowlist_reverse.py`'s module docstring says "13 of the 49 allowlist
    entries have no Python read". After this change that becomes 12 of 49**, because
    `ADMIN_PASSWORD` gains its first Python read in the tree. Measured: that number is
    **prose in a docstring, not an assertion** — there is no count assertion in
    `test_env_allowlist_reverse.py` or `test_env_allowlist.py`, and D6's `need_no_test`
    below cites the deliberate absence of one. Nothing goes red. It is **left alone on
    purpose**: the file is BLOCK 6's, editing it from BLOCK 10 creates a cross-block
    coupling for zero test value, and a stale count in a docstring is a far smaller cost
    than a second block's file appearing in this block's diff.
  - >
    **`docker-compose.test.yml` already sets `ADMIN_PASSWORD=test-admin-password`** in the
    `create_admin` service's `environment:` block, and that literal is covered by
    `.gitleaks.toml`'s `[[allowlists]]` regex `test-admin-password`. The new tests reuse
    that exact literal where a literal is needed, so the CI `security` job stays green.
    No new credential-shaped string is introduced anywhere (BC-6).

# ─────────────────────────────────────────────────────────────────────────────
files:

  - path: src/backend/apps/core/management/commands/create_admin_user.py
    targets:
      - type: module_docstring
        name: "the Usage block, which shows the invocation form"
      - type: class
        name: Command
      - type: method
        name: Command.add_arguments
      - type: method
        name: Command.handle
      - type: argument
        name: "--password"
      - type: statement
        name: "the local assignment that binds options['password'] to `password`"
    semantic_anchors:
      change: >
        **Exactly three things.** (a) The `--password` argument: `required=True` becomes
        `required=False` and `default=None` is added; its `help` text gains one clause
        naming the `ADMIN_PASSWORD` environment fallback. (b) The `password` local in
        `handle`, replaced by the D1/D2 resolution expression. (c) The module
        docstring's `Usage:` line, which must show that `--password` may be omitted.
      do_not_edit:
        - "The `--username` argument (still required=True), `--telegram-id`, `--email`, `--dry-run`"
        - "The empty/whitespace password validation branch and its CommandError text (D4)"
        - "The advisory-lock context manager, both idempotency early-returns, the dry-run branch, `User.objects.create`, `set_password`, the `logger.info` call and both `stdout.write` blocks"
        - "The `help = \"Create an admin user for Django admin site (idempotent)\"` class attribute"
        - "The import block, except for adding `import os`"
      note: >
        `import os` is added to the module's stdlib group. The command's existing imports
        are `logging`, `django.contrib.auth.get_user_model`,
        `django.core.management.base.{BaseCommand,CommandError}`, and the three
        `apps.core.*` names. `ruff check --fix` sorts the group (I001); it must stay
        sorted.

  - path: docker/entrypoint-create-admin.sh
    targets:
      - type: shell_block
        name: "the empty-password skip branch (PRESERVE BYTE-IDENTICAL)"
      - type: shell_statement
        name: "the exec invocation of manage.py create_admin_user"
    semantic_anchors:
      change: >
        The `--password "${ADMIN_PASSWORD}" \` line is removed from the `exec`
        invocation, together with its backslash continuation, so `--username` becomes the
        last continued line and `--telegram-id` the final argument. Nothing else in the
        file changes.
      assert_unchanged:
        - "`set -euo pipefail`"
        - "The `SCRIPT_DIR` computation and the `source \"${SCRIPT_DIR}/entrypoint.sh\"` line, and the `# shellcheck source=entrypoint.sh` directive above it"
        - "The four setup calls, in order: check_env_file, fix_volume_permissions, wait_for_db, wait_for_redis"
        - "The skip branch verbatim: the `if [ -z \"${ADMIN_PASSWORD}\" ]; then` test, the `echo \"ADMIN_PASSWORD not set, skipping admin user creation\"` line, the `exit 0`, the `fi`, and their indentation"
        - "The `exec` keyword itself and the absolute `/opt/venv/bin/python src/backend/manage.py create_admin_user` prefix"
        - "The three header comment lines"
      note: >
        One comment may be **added** immediately above the `exec` (BC-1 requires the
        argv fact to be stated where a reader is looking). It replaces the existing
        `# Run the create_admin_user command with environment variables` line's claim
        that the variables are passed on the command line, which becomes false. No other
        comment is edited.

  - path: src/backend/apps/core/tests/test_create_admin_user.py
    status: edit
    targets:
      - type: class
        name: TestCreateAdminUser
      - type: module_constant
        name: pytestmark
    semantic_anchors:
      change: >
        New test methods **appended to the existing class**. Nothing existing is edited,
        reordered, renamed, removed or skipped (BC-4). The module keeps its
        `pytestmark = [pytest.mark.django_db, pytest.mark.integration]` and its existing
        imports; `monkeypatch` arrives as a pytest fixture argument on the new methods, so
        no new import is needed.
      do_not_edit:
        - "Any of the fourteen existing test methods"
        - "The module docstring's 'Verifies:' list, except for appending one bullet naming the environment fallback"
        - "`pytestmark`, the `User` module-level binding, and the `AdvisoryLockId` import (used by test_lock_id_is_create_admin)"

  - path: src/backend/apps/core/tests/test_create_admin_entrypoint.py
    status: new
    targets:
      - type: module
        name: test_create_admin_entrypoint
      - type: module_docstring
        name: "what the script contract is and what it is not (VAL-002)"
      - type: constant
        name: _SCRIPT
      - type: constant
        name: _STUB_ENTRYPOINT
      - type: helper
        name: _run_script
      - type: function
        name: test_script_exits_zero_when_admin_password_is_empty
      - type: function
        name: test_script_does_not_pass_the_password_on_the_command_line
      - type: function
        name: test_script_still_passes_username_and_telegram_id
    semantic_anchors:
      note: >
        New module. `pytestmark = [pytest.mark.unit]` — no DB, no integration marker (D6).
        The script is located the way `apps/core/tests/test_scheduler_wiring.py` locates
        `entrypoint-scheduler.sh`: `settings.BASE_DIR.parent / "docker" /
        "entrypoint-create-admin.sh"`, read with `encoding="utf-8"`. `subprocess.run`
        uses the **list form with the absolute interpreter** — `["bash", str(script)]` —
        which is what `pyproject.toml`'s `[tool.bandit]` requires to avoid `B603`/`B607`,
        and there is no literal `/tmp` path anywhere (`B108`): the harness writes only
        into pytest's `tmp_path`. No `print()`; a module-level `logger` is not needed
        because the module asserts rather than reports.

# ─────────────────────────────────────────────────────────────────────────────
changes:

  - action: edit_argument_definition
    id: change_password_argument
    path: src/backend/apps/core/management/commands/create_admin_user.py
    description: >
      Make `--password` optional and document the fallback. `required=True` is the entire
      mechanism by which CFG-003 is true: with it set, no invocation of this command can
      avoid putting the secret in `argv`. `default=None` (never `default=""`) is required
      by D2 — it is what distinguishes "the operator passed the flag" from "the operator
      did not".

      The `help` text grows by one clause naming `ADMIN_PASSWORD` as the fallback. It is
      English, untranslated, and is **not** a user-visible string: management-command help
      is untranslated by existing convention across all of
      `apps/core/management/commands/`, so §1's i18n completeness gate is unaffected and
      no `.po` file changes.
    code_hint: |
      parser.add_argument(
          "--password",
          type=str,
          required=False,
          default=None,
          help=(
              "Admin password (must be non-empty). If omitted, falls back to the "
              "ADMIN_PASSWORD environment variable."
          ),
      )
    do_not_edit:
      - "`--username`, which stays required=True"
      - "`--telegram-id`, `--email`, `--dry-run`"

  - action: edit_resolution_logic
    id: change_password_resolution
    path: src/backend/apps/core/management/commands/create_admin_user.py
    depends_on: [change_password_argument]
    description: >
      Replace the single local binding in `handle` with the D1/D2 resolution. The
      condition is `is not None`, never a truthiness test, and the environment default is
      `""` rather than `None`, so the absent-everything case lands on the existing
      empty-password `CommandError` instead of a new branch (D4).

      The comment above the assignment is **required by BC-1** and must say, in substance:
      the fallback exists so the secret is not forced through `argv`; the value is still
      in the process environment by design, so `docker inspect` still returns it; this
      change does not reduce the credential's exposure.
    code_hint: |
      import os
      ...
      # Resolution order: an explicitly supplied --password always wins, even when it is
      # empty -- an empty value must still fail the validation below rather than
      # silently picking up a different password from the environment. The fallback
      # exists so the secret is no longer *forced* through argv. It does not reduce the
      # credential's exposure: ADMIN_PASSWORD is already in the container's environment
      # via env_file, so `docker inspect` already returns it in cleartext (VAL-002).
      password = (
          options["password"]
          if options["password"] is not None
          else os.environ.get("ADMIN_PASSWORD", "")
      )
    do_not_edit:
      - "The validation branch that raises CommandError, and its message"
      - "Every line after the password is bound"

  - action: edit_docstring
    id: change_command_usage_docstring
    path: src/backend/apps/core/management/commands/create_admin_user.py
    depends_on: [change_password_resolution]
    description: >
      The module docstring's `Usage:` block is a **false instruction the moment the flag
      becomes optional** — it tells a reader the password is a required argument. One
      line is rewritten to show the invocation with `--password` omitted and the
      environment variable supplying the value. This is documentation of a contract, not a
      comment about the change, and it is where a reader looks first.
    code_hint: |
      Usage:
          uv run python manage.py create_admin_user --username admin --telegram-id -1
          # or, equivalently, with the password supplied by the environment:
          #   ADMIN_PASSWORD=<password> uv run python manage.py create_admin_user ...

  - action: edit_shell_invocation
    id: change_entrypoint_invocation
    path: docker/entrypoint-create-admin.sh
    depends_on: [change_password_resolution]
    description: >
      Remove `--password "${ADMIN_PASSWORD}" \` from the `exec` invocation. The value is
      still in the container's environment — `docker-compose.yml` passes
      `ADMIN_PASSWORD=${ADMIN_PASSWORD:-}`, `docker-compose.prod.yml` supplies
      `env_file: .env.prod`, `docker-compose.test.yml` sets it explicitly — so the
      command's fallback resolves it, and the skip branch reads the very same variable
      (D5).

      The comment immediately above the `exec` is rewritten, because its current claim —
      "with environment variables" — reads as "passed as variables on the command line"
      and becomes false. The replacement states what actually happens and, per BC-1, that
      the exposure is unchanged.
    code_hint: |
      # Run the create_admin_user command. The admin password is read from
      # ADMIN_PASSWORD in the environment by the command itself, so it is not placed on
      # the command line. This does not change the credential's exposure: it is already
      # in the container's environment via env_file, so `docker inspect` already shows
      # it in cleartext (VAL-002).
      exec /opt/venv/bin/python src/backend/manage.py create_admin_user \
          --username "${ADMIN_USERNAME:-admin}" \
          --telegram-id "${ADMIN_TELEGRAM_ID:--1}"
    assert_unchanged: change_skip_branch

  - action: assert_unchanged
    id: change_skip_branch
    path: docker/entrypoint-create-admin.sh
    description: >
      The empty-password skip is **not edited** (BC-3). This change exists so the
      Implementor states the preservation explicitly and the Validator can check it
      against the diff rather than against memory. Before committing, run
      `git diff -- docker/entrypoint-create-admin.sh` and confirm the **only** removed
      line is the `--password` one and the only added lines are the replacement comment
      block.
    assert:
      - "`if [ -z \"${ADMIN_PASSWORD}\" ]; then` is byte-identical"
      - "`echo \"ADMIN_PASSWORD not set, skipping admin user creation\"` is byte-identical, including capitalisation and the absence of a trailing period"
      - "`exit 0` and `fi` are byte-identical, in that order"
      - "The skip branch is still reached **before** the `exec`"
    verification: >
      `git diff -- docker/entrypoint-create-admin.sh` shows the skip block as context
      lines, never as `-`/`+` pairs. That is the whole check.

  - action: add_test_methods
    id: change_command_tests
    path: src/backend/apps/core/tests/test_create_admin_user.py
    depends_on: [change_password_resolution]
    description: >
      Four methods appended to `TestCreateAdminUser`. They use the module's existing
      harness: `call_command` with keyword options, a `StringIO` for `stdout` where the
      output matters, `User.objects` for the outcome, and `monkeypatch.setenv` /
      `monkeypatch.delenv` for the environment. No new import is required.

      `monkeypatch.setenv("ADMIN_PASSWORD", ...)` is what makes these tests hermetic: the
      developer's or CI's ambient value is restored by pytest after each test, and the
      test does not read any real `.env.*`.
    code_hint: |
      def test_password_resolved_from_environment_when_flag_absent(self, monkeypatch):
          """With --password omitted the command reads ADMIN_PASSWORD (CFG-003)."""
          monkeypatch.setenv("ADMIN_PASSWORD", "test-admin-password")
          call_command("create_admin_user", username="envadmin", telegram_id=-1)
          assert User.objects.get(username="envadmin").check_password(
              "test-admin-password"
          )

      def test_explicit_password_flag_wins_over_environment(self, monkeypatch):
          """--password takes precedence over ADMIN_PASSWORD when both are present."""
          monkeypatch.setenv("ADMIN_PASSWORD", "test-admin-password")
          call_command("create_admin_user", username="flagadmin",
                       password="flag-wins", telegram_id=-1)
          user = User.objects.get(username="flagadmin")
          assert user.check_password("flag-wins")
          assert not user.check_password("test-admin-password")

      def test_empty_password_flag_does_not_fall_back_to_environment(self, monkeypatch):
          """An explicitly empty --password must fail, not silently use the environment.

          Guards D2: a falsiness-triggered fallback would hand the operator a different
          password than the one they typed.
          """
          monkeypatch.setenv("ADMIN_PASSWORD", "test-admin-password")
          with pytest.raises(CommandError, match="Password cannot be empty"):
              call_command("create_admin_user", username="emptyflag",
                           password="", telegram_id=-1)
          assert not User.objects.filter(username="emptyflag").exists()

      def test_no_password_flag_and_no_env_password_raises(self, monkeypatch):
          """Neither flag nor environment: the existing empty-password error fires."""
          monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
          with pytest.raises(CommandError, match="Password cannot be empty"):
              call_command("create_admin_user", username="nopassnoenv", telegram_id=-1)
          assert not User.objects.filter(username="nopassnoenv").exists()

  - action: add_test_module
    id: change_entrypoint_tests
    path: src/backend/apps/core/tests/test_create_admin_entrypoint.py
    depends_on: [change_entrypoint_invocation, change_skip_branch]
    description: >
      The script's first coverage anywhere in the tree (see
      `corrections_to_block_notes`). One behavioural test for the skip path and two
      static tests for the invocation — the split D6 explains and the test container
      forces.

      **The harness.** `_run_script` copies the real script into `tmp_path` beside a
      stub `entrypoint.sh` that defines the four setup functions as no-ops, marks the
      copy executable, and runs `["bash", str(script)]` with a **scrubbed** environment.
      The scrub matters and is the same lesson as BLOCK 4's BC-3: inheriting
      `os.environ` would let a developer's ambient `ADMIN_PASSWORD`, `DJANGO_BUILD` or
      `DJANGO_SETTINGS_MODULE` decide the outcome, and the CI run and the local run would
      differ. The child gets `PATH` and `HOME` only, plus `ADMIN_PASSWORD` where the test
      sets it. The copy is what makes the stub reachable at all, because the script
      resolves `SCRIPT_DIR` from its own location and sources `entrypoint.sh` from there.

      **The behavioural assertion** proves three things at once: the exit status is 0,
      the skip log line is on stdout, and `create_admin_user` **never appears in the
      output** — the last is what proves the command was not launched, which an exit-code
      check alone would not.

      **The static assertions** cover what cannot be executed. `--password` must be
      absent from the file; `--username "${ADMIN_USERNAME:-admin}"` and
      `--telegram-id "${ADMIN_TELEGRAM_ID:--1}"` must survive with their defaults; `exec`
      must survive. The skip branch's three lines are asserted present verbatim, which is
      the cheap belt to `change_skip_branch`'s diff check.
    code_hint: |
      _SCRIPT = settings.BASE_DIR.parent / "docker" / "entrypoint-create-admin.sh"

      # Copied next to the script under test; the script sources entrypoint.sh from its
      # own SCRIPT_DIR, so this is the only way to run the real skip branch without a
      # database, Redis and /opt/venv/bin/python.
      _STUB_ENTRYPOINT = """#!/bin/bash
      set -e
      check_env_file() { :; }
      fix_volume_permissions() { :; }
      wait_for_db() { :; }
      wait_for_redis() { :; }
      """

      def _run_script(tmp_path, admin_password):
          # Scrubbed: PATH and HOME only, never os.environ. See BC-3 in BLOCK 4.
          env = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/root")}
          if admin_password is not None:
              env["ADMIN_PASSWORD"] = admin_password
          (tmp_path / "entrypoint.sh").write_text(_STUB_ENTRYPOINT, encoding="utf-8")
          script = tmp_path / "entrypoint-create-admin.sh"
          script.write_text(_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
          script.chmod(0o755)
          return subprocess.run(
              ["bash", str(script)], env=env, capture_output=True, text=True, timeout=30
          )

      def test_script_exits_zero_when_admin_password_is_empty(tmp_path):
          """ADMIN_PASSWORD set-but-empty: log, exit 0, no admin created.

          Note the script runs `set -euo pipefail`, so an *unset* ADMIN_PASSWORD is an
          unbound-variable error, not a skip. Compose always defines the variable
          (`ADMIN_PASSWORD=${ADMIN_PASSWORD:-}`), so the empty case is the real one.
          """
          result = _run_script(tmp_path, admin_password="")
          assert result.returncode == 0, result.stderr
          assert "ADMIN_PASSWORD not set, skipping admin user creation" in result.stdout
          assert "create_admin_user" not in result.stdout

      def test_script_does_not_pass_the_password_on_the_command_line():
          """The secret is not placed on argv (CFG-003)."""
          content = _SCRIPT.read_text(encoding="utf-8")
          assert "--password" not in content
          assert "exec " in content

      def test_script_still_passes_username_and_telegram_id():
          """The non-secret arguments and the skip branch survive unchanged."""
          content = _SCRIPT.read_text(encoding="utf-8")
          assert '--username "${ADMIN_USERNAME:-admin}"' in content
          assert '--telegram-id "${ADMIN_TELEGRAM_ID:--1}"' in content
          assert 'if [ -z "${ADMIN_PASSWORD}" ]; then' in content
          assert "exit 0" in content
    module_docstring: >
      Required content, in this order. (1) What the module asserts: the create_admin
      entrypoint's two contracts — the empty-password skip and the absence of the secret
      from the command line. (2) **The VAL-002 caveat, plainly:** this is command-contract
      hygiene and it does **not** reduce the credential's exposure, which comes from the
      `env_file` channel and is unchanged. (3) Why the split between a behavioural and a
      static test: the skip branch runs before any Python and is executable against a
      stubbed `entrypoint.sh`; the invocation needs a database, Redis and
      `/opt/venv/bin/python` and cannot be. (4) That the child process runs under a
      scrubbed environment, never `os.environ`.

# ─────────────────────────────────────────────────────────────────────────────
sequence:

  - step: 0
    name: preflight and re-derivation
    actions:
      - "Confirm the anchor: `git log --oneline -3` shows `da399d7` (BLOCK 9) and `d42f778` (BLOCK 7)."
      - "Re-derive, do not transcribe: that `--password` is still `required=True`; that the skip branch is still `if [ -z \"${ADMIN_PASSWORD}\" ]; then … exit 0`; that no test anywhere references `entrypoint-create-admin.sh`; and that `ADMIN_PASSWORD` is still in `ALLOWED_ENV_VARS` under the shell/entrypoint/compose-injected group. If any differs, this task's wording is a starting point, not a specification."
      - "Baseline `src/backend/apps/core/tests/test_create_admin_user.py` alone, so a pre-existing failure is not attributed to this change."
      - "Re-read §1's constraints against the tree. The tree wins where they disagree."
    gate: "test_create_admin_user.py green at baseline"

  - step: 1
    name: the command change, alone
    depends_on: [0]
    actions:
      - "Apply `change_password_argument`, `change_password_resolution` and `change_command_usage_docstring`. One logical change."
      - "Run `uv run ruff check --fix src/backend/apps/core/management/commands/create_admin_user.py` so the `import os` placement is sorted (I001)."
      - "Run `test_create_admin_user.py` in full. **All fourteen existing tests must still pass, unedited.**"
    expect: >
      Green. Two of them are the ones that prove D2 survived:
      `test_empty_password_raises_error` and
      `test_empty_password_whitespace_only_raises_error` pass an explicitly empty or
      whitespace-only `--password` and expect `CommandError`. If either goes green-without-error,
      the resolution used a truthiness test instead of `is not None` — fix the code, not the
      test. `test_requires_username_and_password` also stays green because `--username` is
      still required.

  - step: 2
    name: the new command tests, and the red/green demonstration
    depends_on: [1]
    actions:
      - "**Demonstration first, before the tests are written in final form:** check out the command module at the anchor (`git stash` the step-1 change, or `git show da399d7:src/backend/apps/core/management/commands/create_admin_user.py`), write `test_password_resolved_from_environment_when_flag_absent`, and run it. It must go **RED** — argparse's `the following arguments are required: --password`."
      - "Restore the step-1 change. Confirm the test is **GREEN**, and that the user row was created with the environment's password."
      - "Then apply `change_command_tests` in full and run the module."
      - "Confirm `test_empty_password_flag_does_not_fall_back_to_environment` is a genuine guard, not a tautology: with `ADMIN_PASSWORD` set in the environment, a falsiness-triggered fallback would have created a user and raised nothing. The assertion `not User.objects.filter(username=...).exists()` is what makes that visible."
    expect: >
      Red, then green. Record both outputs. **A test that has never been seen red may be
      passing vacuously** — for this one, vacuity is a live possibility, because a
      `monkeypatch`-only test can pass simply because the command never ran. That is why
      the red step comes first and why the assertions check the created user's password,
      not merely the absence of an exception.

  - step: 3
    name: the entrypoint change
    depends_on: [2]
    actions:
      - "Apply `change_entrypoint_invocation`, then run `change_skip_branch`'s diff check: `git diff -- docker/entrypoint-create-admin.sh` shows the `--password` line removed and the replacement comment block added, with the skip branch appearing only as context lines."
    expect: >
      One removed line, one added comment block, nothing else. If the diff touches the skip
      branch, restore it — BC-3 is absolute and a reindented skip is indistinguishable in
      review from a behavioural change.

  - step: 4
    name: the entrypoint tests
    depends_on: [3]
    actions:
      - "Create `test_create_admin_entrypoint.py` per `change_entrypoint_tests`, module docstring included."
      - "Run it alone. Then run it with `ADMIN_PASSWORD` genuinely unset in the parent shell, to confirm the scrubbed child environment is what decides the result (BC-3)."
      - "Re-run `test_create_admin_user.py` — the command's behaviour must be identical whether it is invoked from the container or from a developer's shell."
    expect: >
      Green. If `test_script_exits_zero_when_admin_password_is_empty` goes red with a
      non-zero status and `ADMIN_PASSWORD: unbound variable` on stderr, the harness is
      passing an *unset* variable rather than an empty one — the `corrections_to_block_notes`
      distinction, caught in the test. Set it to `""`, do not relax the assertion.

  - step: 5
    name: the settings-contract gate
    depends_on: [4]
    actions:
      - "Run `src/backend/config/settings/tests/test_env_allowlist_reverse.py` and `test_env_allowlist.py` in full (D3). The new `os.environ.get(\"ADMIN_PASSWORD\", …)` read is the first Python read of that name in the tree; both modules must stay green with no edit to either file."
      - "Run `test_settings_defaults.py` in full — BLOCK 9's `STORAGES` pin and the dev/test transport-tuple parity are unaffected by this change and must be reported green, not assumed."
    expect: >
      Green, unedited. If `test_consumed_env_vars_are_allowlisted` goes red, the read was
      routed somewhere the scanner does not recognise (D3) or the allowlist entry was
      moved. Fix the routing, not the test, and not the allowlist.

  - step: 6
    name: static gates and hand-off
    depends_on: [5]
    actions:
      - "`uv run ruff check src/` and `uv run basedpyright src/` — both must be green."
      - "`.\Makefile.ps1 test` — the fast gate. This block touches no settings module and no template, so the sweep is a regression check, not a targeted requirement; run it anyway and report it."
      - "Re-read `git status --short` and stage **explicit paths only** (§1 hard rule — never `git add -A`; the tree carries 19 pre-existing `.ai/audit/**` deletions and untracked `.ai/plans/*`, `.ai/tmp/` and `staticfiles/`). Do not commit without an explicit user request."
      - "Before the commit message is written, re-read BC-1 and BC-2 and confirm the message contains no exposure-reduction claim."
      - "Name any gate that could not be run here rather than implying it passed."

# ─────────────────────────────────────────────────────────────────────────────
tests:

  must_keep_passing_unchanged:

    - "`src/backend/apps/core/tests/test_create_admin_user.py` — **all fourteen existing test methods, byte-identical, none renamed, reordered, removed or skipped** (BC-4). They are: `test_create_admin_user_success`, `test_create_with_custom_telegram_id`, `test_create_with_email`, `test_duplicate_telegram_id_skips_with_warning`, `test_duplicate_username_skips_with_warning`, `test_dry_run_does_not_create_user`, `test_dry_run_shows_details`, `test_empty_password_raises_error`, `test_empty_password_whitespace_only_raises_error`, `test_requires_username_and_password`, `test_sets_password_correctly`, `test_lock_id_is_create_admin`, `test_idempotent_on_rerun`, `test_command_dry_run_does_not_leak_telegram_id`. **Every one of them passes `--password` explicitly**, so the module's entire existing coverage already exercises the flag path this change must not break. The two load-bearing ones for D2 are `test_empty_password_raises_error` and `test_empty_password_whitespace_only_raises_error`; `test_requires_username_and_password` is the one that proves `--username` is still required, and it stays green only because `--username` was not touched."

    - "`src/backend/config/settings/tests/test_env_allowlist_reverse.py` in full — BLOCK 6's, VAL-004 instance (c). **This block adds the tree's first Python read of `ADMIN_PASSWORD`**, and the module's whole-tree AST scan will see it. It stays green because `ADMIN_PASSWORD` is already in `ALLOWED_ENV_VARS` and `os.environ.get(...)` is one of the four shapes `_RECOGNISED_READ_SHAPES` declares (D3). This is a required gate, not a formality."

    - "`src/backend/config/settings/tests/test_env_allowlist.py` in full — BLOCK 6's. No template and no allowlist entry changes, so `test_example_keys_in_allowlist` and `test_python_consumed_vars_in_allowlist` are unaffected. The prose count in the reverse module's docstring becomes stale; see `recorded_follow_ups`."

    - "`src/backend/config/settings/tests/test_deploy_check_env_parity.py` in full — BLOCK 4's, VAL-004 instance (b). Untouched by this block; it is named because the block adds no CI env key and no allowlist key that could collide with its required-variable derivation."

    - "`src/backend/config/settings/tests/test_settings_defaults.py` in full — BLOCK 9's, carrying `test_prod_staticfiles_backend_is_theme_storage` (the `STORAGES` pin) and `test_dev_and_test_share_the_transport_tuple` (the dev/test transport-tuple parity). Neither is in this block's blast radius; both are named because they are the most recent shipped contracts and the hand-off must report them green rather than untested."

    - "`src/backend/apps/core/tests/test_scheduler_wiring.py` in full — the precedent for `test_create_admin_entrypoint.py` (D6). The new module copies its shape and does not import it, edit it, or collide with its `_SCHEDULER_SCRIPT` module constant."

    - "`src/backend/tests/test_compose_contract.py` and `src/backend/tests/test_compose_hardening.py` in full — phase 01's VAL-004 instance (a) and the compose hardening suite. **No compose file changes in this block**, including the `create_admin` service block in `docker-compose.yml`, `docker-compose.prod.yml` and `docker-compose.test.yml`."

    - "`Makefile.ps1` / `Makefile`'s `Invoke-CreateAdmin` target — not a test, but a compatibility witness (BC-4). It invokes the command with `--password` and is not edited."

    - "`src/backend/tests/test_docs_ci_parity.py` in full — it reads `docker/entrypoint-test.sh`, not `entrypoint-create-admin.sh`, and is unaffected. Named because it is the only test in the tree that reads a shell script's text, and a reader checking whether this block's new module duplicates a role will look here."

    - "**The entrypoint script's own tests: there are none, and this is a measurement, not an omission.** No file under `src/` references `entrypoint-create-admin.sh`; the only matches anywhere are the script itself, the compose files that point an `entrypoint:` at it, and the `.ai/` documents. `test_docs_ci_parity.py` reads `entrypoint-test.sh`; `test_compose_hardening.py` and `test_health_contract.py` read `entrypoint-scheduler.sh` and `healthcheck-scheduler.sh`. The new module is this script's **first** coverage in the repository's history."

  must_be_added:

    - name: test_password_resolved_from_environment_when_flag_absent
      path: src/backend/apps/core/tests/test_create_admin_user.py
      why: >
        The assertion that Option A exists to make possible, and the one §3.10's
        "Tests required" list names first. Before the change it is **unrunnable**:
        argparse rejects the invocation because `--password` is required.
      asserts:
        - "With `ADMIN_PASSWORD` set in the environment and no `--password` flag, the command succeeds."
        - "A user row exists for the requested username, and `check_password` accepts the **environment's** value — not merely that no exception was raised. Asserting only the absence of an error is the vacuous form of this test."
        - "The value is set with `monkeypatch.setenv`, so the test is hermetic and the developer's ambient value cannot decide the result."

    - name: test_explicit_password_flag_wins_over_environment
      path: src/backend/apps/core/tests/test_create_admin_user.py
      why: >
        Backward compatibility, proven rather than asserted (BC-4). This is the flag path
        every existing test in the module already exercises; the test that matters is the
        one that runs it **with the environment also set**, because precedence is a
        property neither path has alone.
      asserts:
        - "With both `ADMIN_PASSWORD` and `--password` present, the created user authenticates with the **flag's** value."
        - "The user does **not** authenticate with the environment's value. This second assertion is what makes it a precedence test rather than a smoke test."

    - name: test_empty_password_flag_does_not_fall_back_to_environment
      path: src/backend/apps/core/tests/test_create_admin_user.py
      why: >
        The D2 guard. Without it, a future refactor to `options["password"] or
        os.environ.get(...)` is green on every other test in the module and silently
        hands the operator a **different password than the one they typed** — a worse
        outcome than the defect this block exists to fix, and one no shipped test would
        catch.
      asserts:
        - "`--password \"\"` with `ADMIN_PASSWORD` set raises `CommandError` matching `Password cannot be empty`."
        - "No user row was created."

    - name: test_no_password_flag_and_no_env_password_raises
      path: src/backend/apps/core/tests/test_create_admin_user.py
      why: >
        The D4 guard: absent flag **and** absent environment lands on the existing
        empty-password error, with no new branch and no new message. It also proves the
        command fails loudly rather than creating a user with an unusable password.
      asserts:
        - "`CommandError` matching `Password cannot be empty` — the **existing** message, unchanged (D4)."
        - "No user row was created."
        - "`ADMIN_PASSWORD` is removed with `monkeypatch.delenv(..., raising=False)`, so the test is hermetic in an environment that legitimately sets the variable."

    - name: test_script_exits_zero_when_admin_password_is_empty
      path: src/backend/apps/core/tests/test_create_admin_entrypoint.py
      why: >
        The load-bearing pre-existing behaviour, covered for the first time. D6:
        behavioural, because the guard runs before any Python and the script can be
        executed for real against a stubbed `entrypoint.sh` in `tmp_path`. A substring
        assertion over the file would be the only evidence and would be satisfiable by a
        reworded log line.
      asserts:
        - "Exit status is 0."
        - "The skip line `ADMIN_PASSWORD not set, skipping admin user creation` is on stdout, byte-for-byte — this is what pins BC-3."
        - "`create_admin_user` does **not** appear in stdout. Exit 0 alone would also be produced by a script that logged and then ran the command; this assertion is what proves the command was never launched, and hence that no admin was created."
        - "The child environment is **scrubbed** to `PATH` and `HOME` plus `ADMIN_PASSWORD`; the test never inherits `os.environ` (BLOCK 4's BC-3 lesson, applied here)."
        - "`ADMIN_PASSWORD` is set to the **empty string**, not deleted — the `set -euo pipefail` distinction recorded in `corrections_to_block_notes`. An unset variable produces an unbound-variable error and this test must not assert otherwise."

    - name: test_script_does_not_pass_the_password_on_the_command_line
      path: src/backend/apps/core/tests/test_create_admin_entrypoint.py
      why: >
        The CFG-003 assertion, in the only form the test container can execute: static.
        The invocation itself needs a database, Redis and `/opt/venv/bin/python`, so it
        cannot be run. A static read of the script is the honest form, not a compromise.
      asserts:
        - "`--password` does not appear anywhere in the script."
        - "`exec ` is still present, so the shell still replaces itself with the command and PID-1 signal handling is unchanged."

    - name: test_script_still_passes_username_and_telegram_id
      path: src/backend/apps/core/tests/test_create_admin_entrypoint.py
      why: >
        The negative space of the previous test. Removing an argument from a line-continued
        shell command is exactly the edit that silently drops a neighbour, and
        `test_script_does_not_pass_the_password_on_the_command_line` would stay green if
        the whole invocation were mangled.
      asserts:
        - "`--username \"${ADMIN_USERNAME:-admin}\"` is present, with its default form intact."
        - "`--telegram-id \"${ADMIN_TELEGRAM_ID:--1}\"` is present, with its default form intact."
        - "The skip branch's test line `if [ -z \"${ADMIN_PASSWORD}\" ]; then` and its `exit 0` are present — the cheap belt to `change_skip_branch`'s diff check."

  must_be_demonstrated_red:

    - >
      **The new "resolves from the environment when the flag is absent" assertion must be
      shown to fail against the pre-change command.** This is a Validator duty, not a
      shipped test, and it is the block's defining evidence. Procedure: with the
      `test_create_admin_user.py` addition in place, restore the command module to its
      `da399d7` state (`git stash` the production change, or
      `git show da399d7:src/backend/apps/core/management/commands/create_admin_user.py`),
      and run `test_password_resolved_from_environment_when_flag_absent`. It must go
      **red** with argparse's *"the following arguments are required: --password"*. Then
      restore the change and confirm **green**, with the created user authenticating
      against the environment's value. Record both outputs in the hand-off.
    - >
      **Why this demonstration is not optional.** The test sets a variable in the
      environment and asserts a user was created. Against a command that ignores the
      environment entirely, a sloppily-written test could still pass — for instance if it
      asserted only "no exception was raised", or if an unrelated `call_command` in the
      same test created the row. That is why the test asserts `check_password` against
      the environment's value, and why the red run is what proves the assertion has teeth.
      A green run that was never seen red is not evidence.
    - >
      **Second demonstration — the argv assertion is load-bearing.** With the new command
      and the new script change in place, temporarily re-add `--password "${ADMIN_PASSWORD}"`
      to the entrypoint and run `test_script_does_not_pass_the_password_on_the_command_line`;
      it must go **red**. Restore. This proves the static test is not a tripwire that
      passes on any file, and it is the entrypoint-side counterpart of the demonstration
      above.
    - >
      All demonstrations are **Validator duties**. A negative control that was never seen
      red proves nothing. If a demonstration could not be run in this environment, say so
      in the hand-off rather than implying it passed.

  need_no_test:
    - >
      **That the credential no longer appears in `docker inspect`.** It still does, before
      and after, and a test asserting otherwise would be asserting a falsehood (VAL-002,
      BC-1). The real exposure is the `env_file` channel and closing it is Option B, which
      is out of scope and is named in `recorded_follow_ups` as a follow-up.
    - >
      **That `ADMIN_PASSWORD` appears in `ALLOWED_ENV_VARS`.** `test_env_allowlist.py` and
      `test_env_allowlist_reverse.py` already assert it from both directions, and this
      block does not touch the allowlist (BC-5).
    - >
      **That the entrypoint's *non-empty* path creates an admin in a container.** That
      needs a database, Redis and `/opt/venv/bin/python`; it is an integration concern of
      the deployment, not a unit-test concern. The command's create path is covered
      fourteen times over by the existing module.
    - >
      **A test asserting `test_requires_username_and_password` is renamed.** BC-4 forbids
      editing it, and the staleness is recorded in `recorded_follow_ups` instead.
    - >
      **A count assertion on the "N allowlist entries have no Python read" prose.** BLOCK 6
      deliberately ships no such assertion so the number can be re-derived rather than
      maintained; this block does not add one, and the number's drift is recorded rather
      than pinned.
    - >
      **A test that `Makefile.ps1`'s `Invoke-CreateAdmin` still works.** It is a
      compatibility witness by inspection: the flag it passes is unchanged and every
      existing test in the module exercises that same flag path.

  verification_gate:
    - step: 1
      name: "red/green demonstration, command side"
      command: >
        Restore the command module to `da399d7`, run
        `test_password_resolved_from_environment_when_flag_absent` (RED), restore the
        change, run it again (GREEN). Record both outputs.
      expect: "red with 'the following arguments are required: --password', then green"
    - step: 2
      name: "scoped run, existing command tests"
      command: "`$dc run --rm -e PYTEST_OPTS=\"src/backend/apps/core/tests/test_create_admin_user.py\" test`"
      expect: >
        All eighteen tests green (fourteen existing, unedited, plus four new). If
        `test_empty_password_raises_error` or
        `test_empty_password_whitespace_only_raises_error` fails, D2 was violated.
    - step: 3
      name: "scoped run, new entrypoint tests"
      command: "`$dc run --rm -e PYTEST_OPTS=\"src/backend/apps/core/tests/test_create_admin_entrypoint.py\" test`"
      expect: "green; the skip test asserts exit 0, the log line, and that the command never ran"
    - step: 4
      name: "red/green demonstration, entrypoint side"
      command: >
        Re-add `--password "${ADMIN_PASSWORD}"` to the script, run
        `test_script_does_not_pass_the_password_on_the_command_line` (RED), restore (GREEN).
      expect: "red, then green"
    - step: 5
      name: "settings-contract gate (D3)"
      command: "`$dc run --rm -e PYTEST_OPTS=\"src/backend/config/settings/tests\" test`"
      expect: >
        Green, unedited. The reverse scan now sees `ADMIN_PASSWORD` as a consumed name for
        the first time; it is allowlisted, so the suite stays green. Any red here is a
        routing mistake (D3), not a test to fix.
    - step: 6
      name: "core-app package run"
      command: "`$dc run --rm -e PYTEST_OPTS=\"src/backend/apps/core/tests\" test`"
      expect: >
        Green. This is the block's scoped gate: the command, its tests, the new entrypoint
        module, the scheduler-wiring precedent and every other core test.
    - step: 7
      name: "static gates"
      command: "`uv run ruff check src/` and `uv run basedpyright src/`"
      expect: "both green, as they are at the anchor"
    - step: 8
      name: "full fast gate"
      command: "`.\Makefile.ps1 test`"
      expect: >
        Green. Not strictly required — this block touches no settings module, no template
        and no compose file — but it is the sweep that would catch an import error in the
        command reaching an unrelated process. `.\Makefile.ps1 test-all` is not required.
    - step: 9
      name: "diff review"
      command: "`git diff -- docker/entrypoint-create-admin.sh src/backend/apps/core/management/commands/create_admin_user.py`"
      expect: >
        The skip branch appears only as context lines. One removed `--password` line, one
        replaced comment block, one `required=True` → `required=False` + `default=None`,
        one `is not None` resolution expression, one `import os`, one rewritten `Usage:`
        line, and **no** test that existed before this change.

# ─────────────────────────────────────────────────────────────────────────────
acceptance_criteria:
  - >
    **VAL-002 honesty, binding on the commit message and on every comment this change
    introduces.** The commit message, the hand-off, and every added comment, docstring
    and test docstring must state that the `env_file` channel is the real exposure and
    that this change does not address it. Specifically: the credential is **already** in
    cleartext in the container's environment via `env_file` (verified against the live
    container), so `docker inspect` already returns the plaintext, and moving the value
    out of `argv` reduces the exposure by **exactly zero**. **Any claim that the
    credential "no longer appears in `docker inspect`", that it is "no longer visible to
    the host", or that this "removes the secret from the process table" is a false claim
    and must appear in none of the commit message, the code comments, the docstrings, the
    test docstrings, or the hand-off.**
  - >
    **The real exposure is explicitly not addressed by this block, and closing it is a
    named follow-up.** `docker-compose.prod.yml`'s `create_admin` service carries
    `env_file: .env.prod` and mounts `./.env.prod:/app/src/.env:ro`; `docker-compose.yml`
    carries `env_file: .env.dev` and `ADMIN_PASSWORD=${ADMIN_PASSWORD:-}`. The plaintext
    is in `Config.Env` before and after. Reducing it requires Option B — a Docker secret
    or a file-mounted credential the command reads — which needs the feasibility answer
    this block does not provide, and which reaches compose, the entrypoint, the command,
    `.env.prod.example`, the semantics of `ALLOWED_ENV_VARS` and
    `docs/ops/docker-deployment.md`. It is recorded in `recorded_follow_ups` for the
    coordinator to fold into §5.2.
  - >
    **The source finding's threat model is not carried into the change.** The container is
    a single-process one-shot, so "a sidecar, a debugger, a crash handler that captures
    argv" has no concrete instance here. Neither the commit message nor any comment may
    assert one (BC-2).
  - >
    `--password` is `required=False` with `default=None`, and its `help` text names the
    `ADMIN_PASSWORD` environment fallback. `--username` is still `required=True`.
  - >
    The resolution is `options["password"]` when it `is not None`, otherwise
    `os.environ.get("ADMIN_PASSWORD", "")` — a truthiness test is not acceptable, and
    neither is a second error message (D2, D4). The existing
    `"Password cannot be empty. Please provide a valid password."` text is byte-identical.
  - >
    The environment is read from `os.environ` directly, never through django-environ or
    `django.conf.settings`. `config/settings/base.py` is **not touched**:
    `ADMIN_PASSWORD` stays in the `--- Shell/entrypoint/compose-injected (not consumed by
    Python env()) ---` group with its comment unchanged (BC-5, D3).
  - >
    The entrypoint's `create_admin_user` invocation no longer passes `--password`.
    `--username "${ADMIN_USERNAME:-admin}"`, `--telegram-id "${ADMIN_TELEGRAM_ID:--1}"`,
    the `exec` keyword and the absolute interpreter path are unchanged.
  - >
    **The empty-password skip is byte-identical.** `if [ -z "${ADMIN_PASSWORD}" ]; then`,
    `echo "ADMIN_PASSWORD not set, skipping admin user creation"`, `exit 0` and `fi` are
    unchanged, in that order, still ahead of the `exec`, and `git diff` shows them as
    context lines only (BC-3, `change_skip_branch`).
  - >
    **The command's behaviour is unchanged for every existing caller.** All fourteen
    existing tests in `test_create_admin_user.py` pass **unedited, unrenamed, unreordered
    and unskipped**, including `test_empty_password_raises_error` and
    `test_empty_password_whitespace_only_raises_error` (which pin D2) and
    `test_requires_username_and_password` (which pins that `--username` is still
    required). `Makefile.ps1` / `Makefile`'s `Invoke-CreateAdmin` is not edited and is the
    compatibility witness (BC-4).
  - >
    The command's module docstring no longer shows `--password` as a mandatory argument.
    A reader who copies the `Usage:` line must get a working invocation.
  - >
    `docker/entrypoint-create-admin.sh` has test coverage for the **first time** — there
    is none today, measured. The skip path is proven **behaviourally** (exit 0, the log
    line, and `create_admin_user` never appearing in stdout) against the real script with
    a stubbed `entrypoint.sh`; the invocation is proven **statically** (`--password`
    absent, `--username` and `--telegram-id` present with their defaults, `exec`
    present). The child process runs under a **scrubbed** environment — `PATH`, `HOME`
    and `ADMIN_PASSWORD` only — and never inherits `os.environ` (D6).
  - >
    The behavioural skip test sets `ADMIN_PASSWORD` to the **empty string**, not
    deletes it. The script runs `set -euo pipefail`, so an unset variable is an
    unbound-variable error and the skip is never reached; Compose always defines it, so
    the empty case is the real trigger.
  - >
    **The new environment-fallback assertion was seen red against the pre-change command
    before it was seen green** — argparse's *"the following arguments are required:
    --password"* — and the argv assertion was seen red with `--password` re-added to the
    script. Both outputs are recorded in the hand-off, or their absence is stated plainly
    as "not run". A green run that was never seen red is not evidence.
  - >
    `test_env_allowlist_reverse.py` and `test_env_allowlist.py` (BLOCK 6) are **not
    edited** and are green: the new `os.environ.get("ADMIN_PASSWORD", …)` read is the
    tree's first Python read of that name, the shape is one the scan already recognises,
    and the name is already allowlisted. `test_deploy_check_env_parity.py` (BLOCK 4),
    `test_settings_defaults.py` (BLOCK 9, carrying the `STORAGES` pin and the dev/test
    transport-tuple parity) and `test_scheduler_wiring.py` are unedited and green.
  - >
    No credential-shaped literal was introduced: test values come from
    `docker-compose.test.yml`'s existing `test-admin-password` (covered by
    `.gitleaks.toml`'s `[[allowlists]]`) or from `monkeypatch`, and **no value from a real
    `.env.*` was read, printed, quoted or transcribed** — key names only (§1, BC-6).
  - >
    No new dependency, no CI change, no migration, no compose change, no settings-module
    body change, no `docs/**` change, no `print()`, and no `pytest.skip` or `xfail`
    anywhere in the new or edited modules (BC-7, BC-8). **No user-visible string is
    introduced**: the management-command `help` text is English and untranslated by
    existing convention, so the i18n completeness gate passes with no `.po` change.
  - >
    Only two production files changed — the command and the shell script — plus two test
    files (one appended, one new). `SiteConfig`, the admin model and its `UserAdmin`, the
    advisory lock, every other service, `docker/entrypoint.sh`, `Makefile` /
    `Makefile.ps1` and every file under `.ai/audit/**` are untouched; nothing under
    `.ai/audit/**` was read into the change, modified or restored.
  - >
    The three recorded staleness items are recorded and **not** silently fixed: the
    over-broad name of `test_requires_username_and_password`, the now-stale "13 of the 49
    allowlist entries have no Python read" prose in BLOCK 6's reverse-scan docstring, and
    the over-stated "not set" in the skip branch's log line. Each is a deliberate,
    recorded decision with a reason, not an oversight.
  - >
    Nothing was committed without an explicit user request, and only explicitly staged
    paths are in any commit (§1 hard rule — never `git add -A`; the tree carries 19
    pre-existing `.ai/audit/**` deletions and untracked `.ai/plans/*`, `.ai/tmp/` and
    `staticfiles/`).
  - >
    The hand-off names the two gates that could not be run in this environment, if any,
    rather than implying they passed — and the Researcher's Option B feasibility question
    is handed to the coordinator as **not answered and not required here**, per BC-9.
```

**Why this shape.** The block's own notes frame CFG-003 as a question about secret
handling, and the validator's answer is that the secret is already in the cleartext
environment, so the only thing left is a **command contract**: `--password` is
`required=True`, which means *no* invocation exists that does not put the secret in
`argv`. Option A removes the coercion and nothing else. That is why the block is two
production files and four lines of resolution logic, and why the interesting engineering
is entirely in the two things §3.10 under-specified: the fallback must trigger on
**absence**, not on falsiness (D2 — otherwise an operator typing `--password ""` silently
receives a different password, which no shipped test would catch), and the environment
read must stay on `os.environ` (D3 — routing it through the settings layer would make
`ALLOWED_ENV_VARS`' own group comment false on the day it lands).

**What is genuinely new here, and why the tests are shaped this way.** The skip branch is
the only load-bearing behaviour this block touches, and it has **zero** coverage anywhere
in the tree — §3.10's "the entrypoint script's own tests if any" resolves to *none*. A
substring assertion over the file would therefore be the first and only evidence, and it
is satisfiable by a reworded log line, which is exactly the weakness BLOCK 9 recorded for
substring template tests. So the skip gets a **behavioural** test: `bash` is in the test
image, the guard runs before any Python, and `SCRIPT_DIR` is derived from the script's own
location — so a copy of the real script beside a stub `entrypoint.sh` exercises the real
branch, for real, with a **scrubbed** environment so the developer's ambient
`ADMIN_PASSWORD` cannot decide the result. The invocation, which needs a database, Redis
and `/opt/venv/bin/python`, gets a static assertion instead. That split is the block's
substantive design decision, and the red/green demonstrations on both sides are what stop
either test from being vacuous.

**What the coordinator should carry forward.** Three items this Planner may not write
into §5 or §6: the `env_file` follow-up (fold into §5.2 — the real exposure, and the only
change that would reduce it); the fact that the Researcher question is **void** for this
block and remains open for anyone who takes Option B later; and the corrected
characterisation of the skip branch — it triggers on **set-but-empty**, not on *unset*,
because the script runs `set -euo pipefail`, which is a fact any future test of that
branch needs and which the plan's note 2 states loosely.

---

## 4. Dependency graph

### 4.1 Execution order

```
BLOCK 1  CFG-002a  Restore the CI deploy-check gate              deps: —
     │      ──► gates BLOCK 4 (the gate must be live to be protected)
BLOCK 2  CFG-006   Relocate the bot-token guard (restores dev)     deps: —
     │      ──► gates BLOCK 3 (dev stack must be up to verify one-shots)
BLOCK 3  CFG-001 + VAL-001  Scope the secret-validation bypass     deps: BLOCK 1, BLOCK 2
     │      ──► gates BLOCK 4, BLOCK 5, BLOCK 6
BLOCK 4  CFG-002b + VAL-004(b)  Durable prod-import parity test    deps: BLOCK 1, BLOCK 3
BLOCK 5  CFG-011 + CFG-005  Shared helper + BOT_USERNAME guard     deps: BLOCK 3
BLOCK 6  CFG-008 + CFG-009 + VAL-003/VAL-004(c)  Env parity         deps: BLOCK 3
BLOCK 7  CFG-004a  Pin EMAIL_BACKEND in production                 deps: —
BLOCK 8  CFG-004b  Closed EmailTransport set (CONDITIONAL)         deps: BLOCK 7
BLOCK 9  CFG-007 + CFG-010  Dead setting + test transport tuple    deps: —
BLOCK 10 CFG-003 + VAL-002  Admin-creation command contract        deps: — (de-scopable to zero)
```

### 4.2 Why each edge exists

| Edge | Reason |
|---|---|
| `1 → 3` | Not a correctness dependency — an **observability** one. BLOCK 3 changes `prod.py`; the `deploy-check` gate restored in BLOCK 1 is the only automated check that imports those settings, and it is far more useful running than red. |
| `2 → 3` | BLOCK 3 must verify that the five dev one-shot services still boot. That verification needs a running dev stack, and the dev stack is **down today** because of CFG-006. BLOCK 2 is also cheap, unblocked, and restores a live outage. |
| `1 → 4` | BLOCK 4's test parses the `deploy-check` env block and asserts against it. Landing the test before the block is correct would mean pinning the broken eight-variable set. |
| `3 → 4` | The **required-variable set is conditional on where the bypass lives.** BLOCK 4's assertion must be written against the post-CFG-001 guard set, and BLOCK 4's "no bypass flag is present" assertion (note 4) only holds once the flag is inert against `prod`. |
| `3 → 5` | Both edit `prod.py` and the settings chain. If BLOCK 5 landed first, BLOCK 3 would re-edit the same module body, and the new shared helper's placement depends on which modules exist after BLOCK 3. |
| `3 → 6` | BLOCK 3 regroups `ALLOWED_ENV_VARS`; BLOCK 6 adds an entry to it. Same structure, two blocks — a merge hazard, not a safety win, if the order is reversed. |

### 4.3 No edge exists for these, and why

- **BLOCK 7, 8, 9, 10 have no dependencies** and are order-free among themselves.
  BLOCK 7 touches `prod.py`'s transport pins, BLOCK 9 touches `prod.py`'s static-files
  line and `test.py`, BLOCK 10 touches a shell script and a management command. They are
  sequenced only because a single Implementor runs sequentially. BLOCK 7 → BLOCK 8 is the
  one real edge in this group and it is a *content* dependency (the enum replaces the
  pin), not an ordering constraint.
- **BLOCK 9 does not depend on BLOCK 3**, even though both are settings work. BLOCK 3
  may add a settings module; BLOCK 9's parity assertion compares `dev` against `test`,
  which are both stable. The Validator should still re-read `dev.py` after BLOCK 3, since
  BLOCK 5 may consume its regex.
- **BLOCK 10 is listed last and has no dependency** because it is the finding the
  coordinator is most likely to de-scope, and listing it last makes that a single decision
  rather than an interruption.
- **BLOCK 4 does not depend on BLOCK 6** and vice versa, despite both being VAL-004
  instances. They are different directions of different contracts (prod-import
  satisfiability vs. consumed↔allowlist↔template parity) and share no code. Keeping them
  separate means a coordinator can de-scope one without touching the other.

---

## 5. Cross-phase coordination

### 5.1 What phase 01 already owns and phase 02 must not re-ship

| Phase 01 artefact | What phase 02 must not do | Boundary |
|---|---|---|
| `src/backend/tests/test_compose_contract.py` (VAL-004 instance a) | Do not re-assert compose rendering parity, `stop_grace_period`, or the dev `bot`/`seed` asymmetry. | BLOCK 6's test is about env-var parity, not compose. The two must not merge. |
| `ci.yml`'s `lint` and `typecheck` jobs (ENT-004) | Do not edit their `run:` steps or their job-level `env`. | BLOCK 1 and BLOCK 4 touch `deploy-check` and `test` only — disjoint jobs. |
| `docs/99-agent/rules.md` and `docs/ops/docker-deployment.md` doc alignment | Do not revert or reword the phase-01 changes. **Both files are currently modified in the working tree** — see §6. | BLOCK 6 may touch `docs/99-agent/architecture.md` (a *different* file). BLOCK 10 option B would touch `docs/ops/docker-deployment.md` and must coordinate. |
| `apps/core/tests/test_scheduler_error_handling.py` (currently modified) | Do not touch it. It is not a phase-02 surface. | — |

### 5.2 What phase 02 must not do, for other phases' sake

| Other phase | What phase 02 must not do | Boundary |
|---|---|---|
| **DB-004** (phase 03) | BLOCK 5 must not add a `SiteConfig` repair that takes an advisory lock or a new `AdvisoryLockId`. A repair command that writes `SiteConfig` must be safe to run concurrently; if that cannot be shown, escalate. | BLOCK 5 note 3. Prefer no lock. |
| **DB-005 / DB-007** (phase 03) | BLOCK 5's G5 decision must **not** add a new migration to `apps/search`. It belongs in `apps/core` if anywhere. | `apps/core/migrations/` — next number `0005_*`, **check the directory immediately before creating**. |
| **AUT-007** (phase 04) | Nothing. | — |
| **Phase 10 (code quality)** | The four near-identical `_run_in_subprocess` helpers and the two divergent prod-env builders are a **maintainability** item, not a phase-02 finding. Phase 02 must not consolidate them (§6), and phase 10 must not file them as a phase-02 regression. | BLOCK 4 note 3. |
| **Phase 11 (test coverage)** | Same. | — |
| **Phase 12 (production-ops)** | `VAL-006` (the bandit path) and `VAL-005` (gitleaks not installed) are **verification-environment** defects. Phase 12 owns them. Phase 02 must not fix the bandit invocation. | §5.3. |

### 5.3 Shared-artefact reservations

| Artefact | Claimed by | Risk |
|---|---|---|
| `.github/workflows/ci.yml` | BLOCK 1 (`jobs.deploy-check.env` + the relocated comment), BLOCK 4 (`jobs.test.steps` + possibly the same comment) | Phase 01 already edited the `lint`/`typecheck` jobs. BLOCK 1 and BLOCK 4 touch **disjoint** jobs but may both want the relocated comment — BLOCK 4 extends it, BLOCK 1 creates it. Sequence is already correct. |
| `src/backend/config/settings/prod.py` | BLOCK 3 (bypass), BLOCK 5 (`BOT_USERNAME` guard), BLOCK 7 (`EMAIL_BACKEND` pin), BLOCK 9 (dead line) | Four blocks, one module. All four touch **disjoint regions** (guards / a new guard / transport pins / a dead assignment) and the sequence is fixed by §4.1. If a later block cannot place its edit without re-reading an earlier one, the Implementor must re-read the module, not assume. |
| `src/backend/config/settings/base.py` | BLOCK 3 (`ALLOWED_ENV_VARS` grouping), BLOCK 5 (the `BOT_TOKEN` comment), BLOCK 6 (one allowlist entry) | BLOCK 3 must precede BLOCK 6. BLOCK 5's comment edit is in a different region and is order-free. |
| `src/backend/config/settings/dev.py` | BLOCK 2 (guard removal), BLOCK 5 (helper consumption + `BOT_USERNAME` guard) | BLOCK 2 removes the guard; BLOCK 5 consumes what remains. **BLOCK 2 must state in its commit message what it left behind** so BLOCK 5 knows. |
| `src/backend/config/settings/tests/test_settings_secrets.py` | BLOCK 2 (retarget 3), BLOCK 3 (rewrite 1), BLOCK 4 (new test), BLOCK 5 (new test), BLOCK 7 (new test) | The phase's most contended file. Every block must run the **whole** `config/settings/tests` package, not just its own test — a partial run will not catch a cross-module import break (notably `test_settings_secrets.py`'s import of `_prod_env_overrides`). |
| `apps/core/migrations/0005_*` | BLOCK 5 **only if** G5 option (ii) is chosen | Phase 03 also plans migrations in `apps/core`. **Check the directory immediately before generating.** |
| `docker-compose.dev.override.yml` | BLOCK 3 (five one-shot services) | Phase 01's BLOCK 2 already edited this file (the `bot` comment, Prometheus pair). Disjoint regions; the `test_compose_oneshot_flags` rewrite in BLOCK 3 is the tripwire. |
| `docs/ops/docker-deployment.md`, `docs/99-agent/rules.md` | Currently **modified, uncommitted** | §6. BLOCK 10 option B and BLOCK 6's doc amendments must not clobber. |

### 5.4 `VAL-006` — new, recorded here, routed out of phase 02

**Claim:** the code-context document's R-2 states that `config/settings/tests/` is
scanned by `bandit` in CI. Verified at `344ca2b`, it is not: the `security` job runs
`uv run bandit -r src/backend src/telegram_bot -c pyproject.toml` with
`working-directory: src/backend`, so the source paths resolve to
`src/backend/src/backend` and `src/backend/src/telegram_bot` (neither exists) and the
config path resolves to `src/backend/pyproject.toml` (the real file is at the repository
root).

**Consequence for this plan:** R-2's severity drops from "a new CI gate will scan new
test code" to "a latent gate that scans nothing today". New settings tests are still
written bandit-clean (list-form `subprocess.run([sys.executable, ...])`, no literal
`/tmp`), because the cost of that discipline is zero and the cost of getting it wrong
once VAL-006 is fixed is a red `security` job.

**Routing:** phase 12 (production-ops) / phase 10. Phase 01 recorded the same observation
as "pre-existing and not a phase-01 finding" in its §5.1 and §6. **This plan does not fix
it** — it is a CI path defect owned by another phase, and fixing it would newly scan the
whole repository, which is a change no phase should make unilaterally.

---

## 6. Out of scope for this plan

| Item | Reason |
|---|---|
| **Pydantic v2 settings model** (`pydantic-settings`, `BaseSettings`) | Explicitly rejected by the source report as overengineering: django-environ is load-bearing for `overwrite=False` semantics the test suite depends on, and it is woven through every settings module, migration and entrypoint. `git grep` confirms zero occurrences today. CFG-011's doc half is in BLOCK 5; the Pydantic half is in **no** block. |
| **`.env.example` deletion** | Rejected by `VAL-003`. Two shipped green tests assert its presence (`test_csrf_trusted_origins_in_example`, `test_sentry_dsn_in_env_examples`) and `docs/01-spec/architecture-structure.md` lists it in the repository structure. BLOCK 6 retitles. |
| **Consolidating the four `_run_in_subprocess` helpers and the two prod-env builders** | R-3/R-4 make this real, but it is a maintainability change touching four test modules, not a fix for any phase-02 finding. Routed to phase 10 / phase 11. BLOCK 4 carries a **constraint** (do not create a fifth copy) instead of a mandate. |
| **The `bandit` invocation path in `ci.yml`** | `VAL-006`; owned by phase 12. See §5.4. |
| **Installing `gitleaks` / `pre-commit` on the host** | Environment setup, not a remediation. `VAL-005` records that the "no hardcoded secret" conclusion rests on manual sweeps and must not be upgraded to "verified by the project's secret scanner". |
| **The working-tree `.env.prod`** | Gitignored, operator-local, and not deployable (missing `EMAIL_HOST` and `CSRF_TRUSTED_ORIGINS`). It is *evidence* for CFG-001's severity, not a repository defect. Do not edit it in any block. |
| **`.ai/audit/**`** | Unmodifiable. Note that 19 tracked files there are currently **deleted in the working tree** — §1's staging rule exists so no block can accidentally commit that deletion or restore those files. |
| **`docker/Dockerfile`'s builder stage** | `DJANGO_BUILD` is builder-only and out of scope (G2, decided). BLOCK 3 does not touch the Dockerfile. |
| **`docker-compose.prod.yml`'s one-shot services** | Already free of both bypass flags; `test_compose_oneshot_flags` proves it. BLOCK 3 changes only the **dev** override. |
| **`docker/entrypoint.sh`'s non-fatal `deploy_check()`** | The non-fatal wrapper is intentional (a deploy warning must not brick a boot). BLOCK 3's docstring must state honestly that with the bypass honoured, `check --deploy` would not surface the empty `SECRET_KEY` at all — but the function itself is not in scope. |
| **Restoring `APP` / `DRF` / `pytest-randomly` or any other dependency** | Nothing in this plan requires a new dependency. Adding one would require `uv add`, a lockfile update and a CI `uv lock --check` pass. |
| **The `source_findings` file** | `.ai/audit/02-config-secrets/findings.md` is referenced in this plan's front-matter for traceability but is **currently deleted in the working tree**. The validated report at `.ai/audit/99-validation/02-config-secrets-validated-findings.md` is present and is the operative source. |
| **The 19 uncommitted `.ai/audit/**` deletions** | Not this plan's to resolve. Recorded so that no block's `git status` check trips over them and mistakes them for its own changes. |

---

## 7. Per-block risk register

Severity is this Planner's assessment of **execution** risk for the change, not the
finding's severity.

| Block | Risk | Likelihood | Impact | Mitigation / detection | Residual |
|---|---|---|---|---|---|
| **All** | An implementor runs `git add -A` and commits the 19 uncommitted `.ai/audit/**` deletions, or reverts another block's uncommitted work | Med | **High** | §1's hard staging rule; `git status --short` before every commit; the audit tree is unmodifiable by mandate. | Very low |
| **All** | Two blocks edit `test_settings_secrets.py` and one breaks the other's cross-module import | Med | Med | Every block runs the **whole** `config/settings/tests` package, not a subset. The `test_settings_secrets.py` → `test_prod_logging` import is the known vector. | Low |
| **All** | A block is executed with its `depends_on` incomplete, or blocks are parallelised | Low | High | One Implementor, strictly sequential, in the §4.1 order. | Very low |
| **All** | A block's tests are asserted rather than run | Med | High | Every block names its exact gate command; tests run **only** through Docker. | Low |
| **1** | The gate passes for the wrong reason (e.g. a bypass flag leaked in from a `.env`) | Low | **High** | BLOCK 1's negative control: remove `REDIS_URL`, confirm the command **fails**, restore. BLOCK 4 note 4 adds the explicit no-bypass-flag assertion. | Low |
| **1** | Only the two variables are added and the orphaned comment is left, so the structural cause survives | Med | Med | BLOCK 1 mandates both halves; the Validator confirms the moved comment now describes the block that follows it. | Low |
| **2** | The relocated guard returns instead of raising, so the bot exits 0 and reports healthy with an unusable token | Med | **High** | Note 2 decides raise-over-return with the reasoning stated; the "empty token still skips" test is the paired guard. | Low |
| **2** | The guard is moved but the three dev tests are not retargeted in the same change | Med | Med | Same-change mandate; the block's test list names all three. | Very low |
| **3** | `test_django_oneshot_bypasses_all_secrets` is left asserting the bypass (the `VAL-001` trap) | Med | **High** | Same-change mandate; the new test must be **red against the pre-fix code** or the rewrite did not happen. | Low |
| **3** | The dev override is edited for four of five one-shot services; the fifth fails on `EMAIL_HOST` | Med | Med | `test_compose_oneshot_flags` iterating `_ONE_SHOT_SERVICES` is the tripwire. Run it. | Low |
| **3** | A new settings module drifts from `dev.py`'s transport flags | Med | Med | The parity assertion required under Option A. | Low |
| **3** | `base.py`'s `read_env()` skip condition is edited in passing, breaking two secret tests | Low | High | Note 5 forbids it; the full `config/settings/tests` run catches it immediately. | Very low |
| **4** | The YAML-parsing test finds no `deploy-check` job and passes **vacuously** | Med | **High** | The test must assert it found a non-empty env block **before** asserting anything about it. The Validator's red/green demonstration is the control. | Low |
| **4** | `_prod_env_overrides` is refactored and `test_settings_secrets.py`'s import breaks | Med | Med | Note 3; same-change mandate; the full package run. | Low |
| **5** | The new helper imports from `prod.py`, creating a cycle or pulling prod's logging/Sentry config into `dev.py` | Med | Med | The constraint is stated in the file surface; the Validator checks the import graph. | Low |
| **5** | A repair path is shipped that does not invalidate the cached bot username, so the fix appears not to work for up to an hour | Med | Med | Note 4; the G5 test must assert the cache invalidation. | Low |
| **5** | `full_clean()` in the migration rejects the default `bazuna_bot` on a fresh database | Low | High | `bazuna_bot` matches the regex; assert it rather than assume it. | Very low |
| **5** | A new `0005_*` migration number collides with phase 03 | Med | Med | Check the directory immediately before generating (§5.3). | Low |
| **6** | The reverse-direction test is noisy and gets disabled, destroying the phase's durable half | Med | Med | The red/green demonstration plus the "no option provides complete coverage" statement in the block summary. | Med — accepted |
| **6** | A reduced `.env.example` stub drops `CSRF_TRUSTED_ORIGINS=` or `SENTRY_DSN=` | Med | Med | Note 4; both keys pinned by green tests. Caught in this change, not a follow-up. | Low |
| **6** | The block clobbers uncommitted work in `docs/99-agent/rules.md` or `docs/ops/docker-deployment.md` | Med | Med | §1 staging rule; BLOCK 6's doc surface is a *different* file (`architecture.md`). | Low |
| **7** | An operator relying on the `EMAIL_BACKEND` override to reach a non-SMTP transport breaks | Med | **High** | The finding's own stated risk. BLOCK 8 is the mitigation and is gated on an explicit written confirmation that such a deployment exists. | Med — accepted and disclosed |
| **7** | The pin is placed inside the `EMAIL_HOST` guard block and is therefore skippable | Low | **High** | It must be an unconditional top-level assignment, like `DEBUG`. Stated in the file surface. | Very low |
| **8** | The permitted transport set is too narrow and blocks a legitimate deployment | Med | Med | The activation trigger is the control; do not start the block speculatively. | Low |
| **8** | BLOCK 7's override-is-ignored test is not rewritten when the enum replaces the free-form path | Med | Med | Same-change mandate, stated in the block's test list. | Low |
| **9** | Deleting the static-files line breaks `collectstatic` in the builder stage | Low | **High** | `STORAGES` in `base.py` is the effective configuration; the pin test is the guard. | Very low |
| **9** | The HSTS reset changes response headers across the whole suite | Med | Med | The full-sweep gate is the control. | Low |
| **10** | Option A is shipped with a claim that it reduces the credential's exposure | Med | Med | `VAL-002` is binding; it is stated in the block summary, the file surface and §8. | Low |
| **10** | Option B is started without the feasibility answer and strands the deployment | Low | **High** | The Researcher's answer is a precondition. | Very low |
| **10** | The empty-password skip is broken | Low | Med | Tested; loud, visible failure. | Very low |

---

## 8. Definition of done for the whole plan

Phase 02 is complete when **all** of the following hold.

### 8.1 Scope

- [ ] All 11 `CFG` findings have a recorded disposition: 11 implemented, with `CFG-004`
      split across two blocks.
- [ ] All 5 `VAL` findings have a recorded disposition: `VAL-001`/`VAL-002`/`VAL-003`
      landed as binding constraints in their owning blocks, `VAL-004` absorbed
      (instance (a) already shipped by phase 01, (b) BLOCK 4, (c) BLOCK 6), `VAL-005`
      recorded as a verification-environment limitation.
- [ ] `VAL-006` (the bandit invocation path) is recorded in the audit tracker and routed
      to phase 12; **no phase-02 block fixes it**.
- [ ] BLOCK 8 has an explicit written activation decision — either the trigger fired and
      it ran, or it did not and it was correctly skipped. Silence is not an acceptable
      outcome.
- [ ] BLOCK 10 has an explicit written disposition — either it ran, or the coordinator
      recorded CFG-003 as accepted-with-no-change and §8.2's `VAL-002` statement was
      written.

### 8.2 Gates — all green

- [ ] `uv run ruff check src/` → exit 0.
- [ ] `uv run basedpyright src/` → **0 errors**.
- [ ] `git status --short .ai` shows **no new modifications** beyond the 19 pre-existing
      uncommitted deletions. No audit-phase file was edited, restored or re-created.
- [ ] `.\Makefile.ps1 test` → full suite green, run at least once **after** BLOCK 5's
      migration edit and with `.\Makefile.ps1 test-recreate` executed at least once.
- [ ] BLOCK 1's gate: `check --deploy --fail-level WARNING` passes with exactly the
      `deploy-check` env set, and **fails** when `REDIS_URL` is removed.
- [ ] BLOCK 2's live gate: `docker ps` shows the dev `web` and `bot` **Up**, not
      `Restarting`.

### 8.3 Per-finding behavioural confirmation

- [ ] **CFG-001** — `DJANGO_ONESHOT=1` + `config.settings.prod` + a blank `SECRET_KEY`
      **raises**. The dev one-shot services still import with dev-only dummy secrets. The
      bootstrap path is not simply removed.
- [ ] **CFG-002** — the `deploy-check` job imports `config.settings.prod` successfully
      with its own `env:` block; a new test in the **`test` job** asserts the same and was
      demonstrated **red** when a variable was removed.
- [ ] **CFG-003** — whatever was chosen, the empty-password skip is preserved and the
      commit message does **not** claim the `env_file` exposure was reduced (`VAL-002`).
- [ ] **CFG-004** — `settings.EMAIL_BACKEND` is the SMTP backend under
      `config.settings.prod` **even when** the env var names the console backend.
- [ ] **CFG-005** — a placeholder `BOT_USERNAME` is rejected in prod **and** dev; a value
      that is not a `<...>` placeholder but fails the model regex is rejected in prod; the
      migration refuses to write an invalid value; the chosen repair path is tested or
      documented.
- [ ] **CFG-006** — `import config.settings.dev` succeeds with a placeholder token and
      `telegram_bot.main.main()` raises; an **empty** token still takes the graceful skip
      path; the dev stack is up.
- [ ] **CFG-007** — under prod settings,
      `STORAGES["staticfiles"]["BACKEND"] == "theme.storage.ThemeStaticFilesStorage"`.
- [ ] **CFG-008** — `RUN_TRANSLATION_BACKFILL` is in `ALLOWED_ENV_VARS` and documented in
      `.env.prod.example`; the reverse-direction test passes and was **red** without the
      entry.
- [ ] **CFG-009** — `.env.example` has no BOM, no longer claims to be comprehensive, and
      **still contains** `CSRF_TRUSTED_ORIGINS=` and `SENTRY_DSN=`.
- [ ] **CFG-010** — `config.settings.dev` and `config.settings.test` agree on all six
      transport settings, and a test-mode server response carries no HSTS header.
- [ ] **CFG-011** — the `BOT_TOKEN` comment names the real mechanism; the placeholder
      helper exists in exactly one place and is imported by both `prod.py` and `dev.py`.
- [ ] **VAL-001** — `test_django_oneshot_bypasses_all_secrets` was **rewritten**, and the
      rewritten version is red against the pre-fix code.

### 8.4 Cross-phase integrity

- [ ] Phase 01's `test_compose_contract.py` is untouched and still green.
- [ ] `ci.yml`'s `lint`, `typecheck`, `i18n`, `security`, `build`, `load-test` and
      `lint-templates` jobs are untouched; only `deploy-check` and `test` changed.
- [ ] No `AdvisoryLockId` allocated; no lock taken by the `SiteConfig` repair path.
- [ ] No new migration in `apps/search`; any `apps/core` migration number was checked
      against the directory immediately before generation.
- [ ] The four `_run_in_subprocess` helpers and the two prod-env builders are **not**
      consolidated (§6), and no **fifth** copy was created.
- [ ] No user-visible string was introduced without a complete `ru` and `bs`
      translation; the i18n completeness gate passes.
- [ ] `docker/Dockerfile` and `docker-compose.prod.yml` are untouched except where §5.3
      records otherwise.

### 8.5 Project conventions

- [ ] Every new constant is a named module-level constant or a `StrEnum` member, never an
      inline literal or a dict-of-strings (project rule 10).
- [ ] No `print()`; `logger = logging.getLogger(__name__)` with lazy `%s` formatting.
- [ ] All comments, docstrings, log messages and error messages are in English.
- [ ] Every non-trivial behaviour change has a test that verifies logic and component
      interaction. Pure plumbing is covered by the contract assertion, not a behavioural
      test.
- [ ] `pytestmark` conventions follow the surrounding file.
- [ ] `uv run ruff check --fix src/` was run if imports were reordered.
- [ ] New subprocess invocations use list form with `sys.executable` (bandit-clean for
      when `VAL-006` is fixed), and no literal `/tmp` path is introduced (`B108`).
- [ ] Any new literal that resembles a credential in a test matches an existing
      `.gitleaks.toml` allowlist regex, or reuses `config/settings/tests/__init__.py`'s
      constants.

### 8.6 Deliverables

- [ ] `VAL-005` is recorded in the audit tracker **as a limitation**: the "no hardcoded
      secret" conclusion rests on manual pattern sweeps, and the project-declared
      `gitleaks` control was not exercised in this environment. It must not be reported as
      "verified by the project's secret scanner".
- [ ] `VAL-006` is recorded and routed to phase 12.
- [ ] This plan file is updated to mark each block's completion, so the phase
      coordinator has a single status surface.
- [ ] No commit was made without an explicit user request.
