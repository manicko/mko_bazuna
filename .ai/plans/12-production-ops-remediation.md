---
plan_id: "12-production-ops-remediation"
phase: "12"
phase_name: "Production / Operations, Security & Observability"
source_report: ".ai/audit/99-validation/12-production-ops-validated-findings.md"
source_findings: ".ai/audit/12-production-ops/findings.md (deleted in the working tree — not an input)"
code_context: ".ai/tmp/code-context-phase12.md"
date: "2026-09-29"
planner: "Planner (subagent)"
anchor_commit: "6413df5"
report_anchor_commit: "6413df5"
status: "planned"
findings_in_scope: 24
findings_still_exist: 18
findings_partial: 2
findings_merged: 1
findings_already_fixed: 0
findings_rejected: 0
val_findings_open: 3
blocks: 18
---

# Execution Plan — Phase 12 Remediation (Production / Operations)

## 0. Header, provenance and scope statement

### 0.1 Provenance

| Item | Value |
|---|---|
| Source report | `.ai/audit/99-validation/12-production-ops-validated-findings.md` (validated, 2014 lines) — the **only** surviving phase-12 input, and self-contained |
| Source findings file | `.ai/audit/12-production-ops/findings.md` — **does not exist in the working tree.** Recorded for traceability only; not an input, and not a problem to fix. **No block may restore it** |
| Code-context document | `.ai/tmp/code-context-phase12.md` (957 lines, Auditor), anchor `6413df5` |
| **Working anchor commit for this plan** | **`6413df5`** (`git rev-parse --short HEAD`, taken before writing) |
| Date | 2026-09-29 |
| Findings in scope | 24 units: 21 `OPS-` + 3 `VAL-` (`VAL-001`, `VAL-002`, `VAL-003`) |
| State at the anchor | **18 still exist unchanged · 2 partially fixed (`OPS-018`, `OPS-021`) · 1 merged (`OPS-005` → `OPS-007`) · 0 already fixed · 0 rejected · 3 `VAL-` open** |
| Validated severity split | **0 CRITICAL · 5 HIGH · 10 MEDIUM · 6 LOW** (the report's reclassifications are upheld in full — §0.4) |
| Execution blocks | **18** — 8 `mechanical`, 7 `behavioural`, 1 `structural`, 2 `conditional` (§2 carries the classification per finding) |
| Implementor concurrency | **1**, strictly sequential (project rule: only one implementor at a time) |
| Migration | **none.** No block ships a schema change, and no block allocates an `AdvisoryLockId` |
| i18n | No block adds a **user-visible** string. BLOCK 6 adds one operator-facing **log** message (`ru`/`bs` not required); BLOCK 12's option (b) would add one admin-visible message and is gated accordingly |

**This phase has the widest blast radius in the whole programme.** `docker-compose.yml` is
the base of all three stacks — dev, test and prod. A syntax or interpolation error in it
breaks `.\Makefile.ps1 test` for **every** phase, not only phase 12. `.github/workflows/ci.yml`
is the gate every phase depends on, and `apps/core/enums.py`, `config/settings/**` and
`docs/ops/**` are all contended. Section 0.2.2 states the four structural hazards; §7 states
the blast radius of every block individually.

**Naming convention.** Every citation of this phase's own findings is cycle-scoped
**`12-OPS-0NN`**, never a bare `OPS-0NN`, wherever it must survive into a comment, a
docstring, a workflow comment, a tracker entry or a commit message. The convention is
already partly present in the shipped source (`.github/workflows/deploy.yml` says
`12-OPS-005`, `docs/ops/docker-deployment.md` says `12-OPS-008`) and partly **wrong**
(`.github/workflows/ci.yml`'s `deploy-check` rationale header says `OPS-001`, which in this
phase is the bandit finding, not the deploy-check gate). BLOCK 3 fixes that header.

---

### 0.2 Evidence basis — read this before executing any block

The validated report is the narrative source; the Auditor's code context re-measured it
against the tree at `6413df5`; this Planner re-verified the load-bearing claims against the
same tree. **The tree is the authority.** Where the report and the tree disagree, the
correction is here and the plan is built on the tree's answer.

#### 0.2.1 Corrections — the tree wins

| # | Claim | Report / context says | **Tree at `6413df5` says** (✔ = verified by this Planner) | Consequence |
|---|---|---|---|---|
| **C-1** | `OPS-019`: `db`/`redis` healthchecks in `docker-compose.yml` lack `start_period`; the report did not name the test override | two sites | ✔ **Four** healthcheck blocks across **three** files lack it: `docker-compose.yml` `db` (interval 5s / timeout 5s / retries 5) and `redis` (5s / 3s / 5); `docker-compose.test.yml` `db` override (5s / 5s / 5); and — **not named by the report and not named by the code context** — `docker-compose.prod.yml` `pgbouncer` (5s / 5s / 5). Every other healthcheck (`web` 5 s, `bot` 30 s, prod `scheduler` 600 s) declares one | In scope and BLOCK 1, **including** the test override. The report's "safe in every environment" claim becomes "must be re-verified per file", because `docker-compose.test.yml` is the file every phase's test command reads |
| **C-2** | `OPS-018`: "all seven services in `docker-compose.prod.yml` (lines 8, 18, 28, 36, 44, 54, 63)" | seven services, those line numbers | ✔ `docker-compose.prod.yml` declares **eight** `image:` lines (`web`, `bot`, `migrate`, `create_admin`, `seed`, `load_cities`, `load_catalog`, `scheduler`) and the `pgbouncer` service adds a ninth service with no `image:` reference to `IMAGE_TAG`. The "seven services" sentence is wrong in count and in every cited offset | BLOCK 14 corrects the count **and** the sentence, and does not encode the wrong number in the parity test |
| **C-3** | `OPS-014`: the backup service "runs as UID 0" because its `command:` override bypasses `docker-entrypoint.sh` | root by mechanism | ✔ Confirmed structurally: `backup` declares `image: postgres:18-alpine`, a three-element `command: ["/bin/sh", "-c", …]`, `read_only: true`, `cap_drop: ["ALL"]`, `tmpfs`, `no-new-privileges`, `mem_limit`, `cpus`, `restart: unless-stopped`, `volumes: ./backups:/backups` — and **no `user:` and no `healthcheck:`**. The runtime uid was **not** observed. The `db` service, by contrast, has no `command:` override | The **fix** is in scope; the **mechanism claim** must be re-derived before it is asserted in a test or a commit body. BLOCK 2 makes the *absence* the assertion, not the inferred uid |
| **C-4** | `_HARDENING_KEYS` in `test_compose_hardening.py` is the list the OPS-014 guard uses | five keys | ✔ Exactly `["read_only: true", "tmpfs:", "no-new-privileges:true", "mem_limit:", "cpus:"]`, and it is iterated by **twelve** service assertions: `web`, `bot`, `db`, `redis`, `scheduler`, `backup`, `pgbouncer`, `migrate`, `load_cities`, `load_catalog`, `create_admin`, `seed`. ✔ **`redis` is the only service in that list that declares `user:`** — `db` has none **by design** (its privilege drop is the image entrypoint's job) and `nginx`, which is separately documented as an exception, is not iterated at all | Adding `user:` to the shared list turns **eleven** green assertions red for a key they should not have. BLOCK 2 introduces an **exception list**; it does **not** extend the shared constant. See 0.2.2 item 2 |
| **C-5** | `_deploy_check_section()` isolates the `deploy-check` job | it slices to EOF | ✔ Confirmed and load-bearing: `content.index("  deploy-check:")` then `content[idx:]`, with the docstring asserting "The job is the last definition in `ci.yml`". Three shipped assertions (`test_ci_deploy_check_uses_prod_settings`, `…fails_on_warnings`, `…sets_valid_secret_key`) read that slice, and one asserts `"continue-on-error" not in section` | **No phase-12 block may append a job after `deploy-check:`.** BLOCK 3 changes the `ci.yml` top-level and `build` job only; BLOCK 4 edits an existing `security` step; BLOCK 5 pins action refs in place. If any block ever must add a job, it changes the helper **in the same commit**, and says so |
| **C-6** | `AdvisoryLockId` is contended | — | ✔ 19 members: `ARCHIVE_SWEEP=1` … `ALERT_DELIVERY_TASK=9`, `MIGRATE=100`, `CREATE_ADMIN=101`, `BACKFILL_THUMBNAILS=102`, `SWEEP_ORPHANED_MEDIA=103`, `CATALOG_LOAD=104`, `PURGE_DELETED_ADS=11`, `RECOMPUTE_NORMALIZED_PRICES=12`, `REPAIR_BOT_USERNAME=13`, `SEED=110`, `TEST_SCHEMA_SETUP=111`. **Next free integer id: 14** | **Phase 12 allocates no lock id.** If a block appears to need one, that is **Q13** — a decision gate, not a default. Phases 03/05/06/07/10 all list `apps/core/enums.py` as contended; it is re-read immediately before any edit |
| **C-7** | `Makefile`'s `restore` target is a dev-stack target; `restore.md` Option B points at it for production | irreversible-data surface | ✔ Confirmed and **wider than stated**: `Makefile`'s `COMPOSE_FILES := --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml` is the target's implicit invocation context, and the target runs `docker compose … exec -T db pg_restore --clean --if-exists`. `COMPOSE_PROD := $(ENV_PROD) -f docker-compose.yml -f docker-compose.prod.yml` is **defined and used by no target** | BLOCK 9 must not leave a dev-stack `restore` target reachable from a production runbook. Three options are gated in **Q2**; none is a silent choice |
| **C-8** | `scripts/ops/*.sh` and `docker/healthcheck-backup.sh` are proposed new artifacts | new files | ✔ Neither exists. `scripts/` holds only `consolidate_migrations.py`, `download_seed_photos.py`, `generate_po.py`, `github-actions-logs.ps1`, `profile_search.py`, `run-profile.sh`. `docker/` has `healthcheck-bot.sh` and `healthcheck-scheduler.sh`, both `chmod +x` in the Dockerfile and both asserted executable by `apps/core/tests/test_health_contract.py` | The healthcheck script follows an **existing** shape (BLOCK 2). The `scripts/ops/` directory has **no precedent and no lint harness** — that is precisely why BLOCK 9 carries the instrument decision as a gate (**Q3**) instead of shipping a directory |
| **C-9** | `OPS-003`: the alert file's selectors are wrong | three rules dead | ✔ Confirmed verbatim: `search_slo_burn_rate` and `search_p95_latency_slo` select `django_http_response_duration_seconds_bucket{le="2.000", handler="search:search"}`; `cache_hit_rate_slo` selects `redis_db_keyspace_hits_total`. ✔ No `prometheus`, `grafana`, `alertmanager`, `node_exporter` or `redis_exporter` service exists in any of the four compose files; the only Prometheus tokens are `PROMETHEUS_MULTIPROC_DIR` and its tmpfs on `web`. ✔ `docker/nginx/nginx.conf`'s `location = /metrics` carries `allow 127.0.0.1; deny all;` | Block 11's selector correction is verifiable **today** by a scrape-contract test on `apps/core/tests/test_observability.py` (which already renders `/metrics` through the Django test client). Whether to *deploy* a Prometheus is a separate question and stays a gate (**Q5**) |
| **C-10** | `OPS-006`: every `docker compose` invocation in `restore.md` omits `--env-file` | all of them | ✔ All nine: `restore.md`'s prerequisites line (`.env.dev` as the credential source), the `--profile backup up -d`, `ps db`, `stop web bot`, both `pg_restore` blocks, `start web bot`, the connectivity check and `run --rm migrate`. ✔ `docs/ops/rollback.md`'s production invocations **do** carry `--env-file .env.prod` — do not "fix" those | BLOCK 9's sweep is per-file and per-block; the rollback.md `--env-file` lines are left byte-identical |
| **C-11** | `OPS-018`: one of seven doc instances was fixed by phase 02 | one closed | ✔ Confirmed: `docker-deployment.md`'s deploy-check env paragraph now matches the fixed job. ✔ The other six are live, plus **six new drift instances** created by phases 01/02 (the `INFO` root-logger claim at `docker-deployment.md`, the "Build image" production-service table, the stale `Known limitation` multiprocess caveat in `prometheus-slo-alerts.yaml`, a cross-reference to the **deleted** `.ai/audit/12-production-ops/findings.md`, `rollback.md`'s "line 68" for `IMAGE_TAG` — it is **83** — and `restore.md`'s "No backup testing in CI") | BLOCK 14 corrects **twelve** instances, not six. BLOCK 15's parity test is written **after** BLOCK 14 so it cannot institutionalise a wrong claim — this is the report's own warning |
| **C-12** | `OPS-021`: the `ci.yml` comment is misplaced | still misplaced | ✔ **Partially false.** The seven-line `deploy-check` rationale now sits directly above `deploy-check:`, and phase 02 extended it with a paragraph naming `config/settings/tests/test_deploy_check_env_parity.py`. The remaining defect is only its header's stale `OPS-001` reference | BLOCK 3 fixes the header citation only. The backup-loop limb is BLOCK 2's |
| **C-13** | `OPS-010`: the bot-marker enable flag is absent from every shipped config | absent | ✔ `config/settings/base.py` declares `BOT_HEALTH_CHECK_ENABLED` with `default=False`; `docker-compose.yml` ships `BOT_HEALTH_STALE_SECONDS=120` on `web` and `bot` and never the enable flag; `docker-compose.prod.yml`'s `web` override sets only `image`, `env_file`, `volumes` and `stop_grace_period`, so it inherits the base `environment:` verbatim. ✔ `.env.prod.example` carries **no** `BOT_HEALTH_CHECK_ENABLED` line | Enabling it makes `/health/ready/` return 503 on a stale marker — and `/health/ready/` is the **deploy gate** and the documented rollback validation target. That is a deploy-pipeline behaviour change, not a config flip. **Q6** |
| **C-14** | `VAL-001`: no `*_MEM_LIMIT` / `*_CPUS` key in any environment file | confirmed | ✔ Every `mem_limit:` / `cpus:` in all four compose files is `${VAR:-default}`; `.env.prod.example` contains `POSTGRES_DB=bazuna_db` (22), `SUPPORT_NOTIFICATION_RECIPIENTS` (49), `SENTRY_DSN=` (73, empty), `IMAGE_TAG=latest` (83) and **no** limit key | BLOCK 7's scope is itself gated (**Q7**) because closing it means adding keys to four example files **and** to `ALLOWED_ENV_VARS` in `config/settings/base.py` — a phase-02-owned surface that `test_env_allowlist.py` reads in both directions |
| **C-15** | `OPS-004` cannot be closed without an off-host artifact path | confirmed | ✔ `restore-test.yml` bootstraps a fresh database and dumps **that**; `Makefile`'s `restore-test` smoke steps 2/4 and 3/4 `echo` a table count and an `ads_ad` row count and assert nothing; `Makefile.ps1` has **no** `restore-test` target (so there is no parity obligation for that edit) | BLOCK 16 is **conditional**. Its unconditional half (pin the image tag, assert non-empty restores, label the self-generated dump honestly) ships either way; the real-artifact half is **Q8** and may be declined |
| **C-16** | Phase 11's plan exists | the brief said plans through 11 exist | ✔ **It did not exist when this plan was written and appeared while it was being written** — the same concurrent-agent drift the anchor rule exists for. ✔ It is now readable and anchored at `6413df5`, the same anchor. Re-verified: it claims **`.github/workflows/ci.yml` in TWO of its blocks** (the `--cov` shape in BLOCK 2, `timeout-minutes` in BLOCK 3) and **`ci-nightly.yml`** — *"phase 11 is the first phase to touch `ci-nightly.yml`, no other plan claims it"* — and **`config/settings/test.py`** in BLOCK 5. ✔ It **reads** `test_docs_ci_parity.py` and `test_ci_security.py` for a workflow-claim baseline and **edits neither** | `ci.yml` now has **five** phase-12-adjacent owners. §5.3 records the collision and §5.4 records the one-way non-interference: phase 12's BLOCKS 3/4/5 and phase 11's BLOCKS 2/3 all edit `ci.yml`, and **phase 11's edits are the `pytest` and `test` jobs while phase 12's are the `on:` block, the `build` job, the `security` job and top-level keys** — a re-read-before-edit sequence, not a merge conflict |

#### 0.2.2 The four hazards that constrain how any block may be implemented

1. **`docker-compose.yml` is the highest blast-radius file in the repository.** It is the
   base of dev (`+dev.override`), test (`+test.yml`) and prod (`+prod.yml`). A syntax error
   or a broken `${VAR:?}` interpolation breaks `.\Makefile.ps1 test` for **every phase**,
   and it fails as a confusing `POSTGRES_USER is missing a value` at config-render time, not
   as a YAML error. **`docker-compose.test.yml` is the file the `test` service itself reads**
   and the code context shows it also lacks `start_period` (C-1). Only **BLOCK 1** writes
   `docker-compose.yml`; only **BLOCK 1** writes `docker-compose.test.yml`. Every other
   block's compose edits are prod-only, which is the safer surface.
2. **`_HARDENING_KEYS` is a shared module constant iterated by twelve service assertions.**
   Adding `user:` to it (the obvious implementation of `OPS-014`) turns `db`, `redis`,
   `nginx`, `migrate`, `load_cities`, `load_catalog`, `create_admin` and `seed` red for a
   key they should not have. **The remedy is an exception list, not an extended constant**
   — and the exception list must be per-service and justified, because an exception list
   with no rationale is how the next service silently opts out.
3. **`_deploy_check_section()` slices `ci.yml` to end-of-file** (C-5). Appending any job
   after `deploy-check:` silently breaks three shipped assertions. Any new CI job must be
   placed **before** `deploy-check:` **or** the helper must be changed **in the same commit**
   with the reason stated.
4. **Every existing `ops` guard is string-level, and that is the shared root cause of
   `OPS-001`, `OPS-003` and `OPS-004`** (`VAL-003`). `test_ci_security.py::test_ci_yml_has_sast_job`
   asserts `"bandit" in content`; `test_restore_test_workflow.py` asserts `"schedule:" in text`;
   `test_compose_hardening.py` asserts key presence in a text block. **A new guard that asserts
   a substring reproduces the defect it was written to prevent.** The one behavioural precedent
   in the repository is `apps/core/tests/test_observability.py::test_metrics_endpoint`, which
   renders `/metrics` through the Django test client and asserts the exposition. **Every new
   ops guard in this plan follows that model**: assert the observable outcome, not the token.

#### 0.2.3 Runtime re-verification required before a block relies on a claim

No test suite was run for the audit, for the code context, or for this plan. Nothing was
executed against a running stack; no container or compose project was started, stopped or
altered. `VAL-003` requires that **every numeric or grep claim be re-derived with the exact
command, the image and the working directory recorded** before it is relied upon — the
report's own fabricated bandit transcript is the cautionary example.

| # | Claim to re-verify | Block | How |
|---|---|---|---|
| 1 | The bandit step exits 2 and scans zero files | 4 | `docker run --rm --entrypoint sh -v <repo>:/app -w /app/src/backend mko-bazuna-test-web:latest -c "bandit -r src/backend src/telegram_bot -c pyproject.toml; echo EXIT=$?"` — record the CWD and the **un-modified** flag set |
| 2 | The real finding count (report: 114 — Low 104 / Medium 10 / High 0) | 4 | Same binary, CWD `/app`, un-modified flags. **Treat the report's number as untrusted until reproduced** |
| 3 | `/metrics` emits `django_http_requests_latency_including_middlewares_seconds` and **no** `django_http_response_duration_seconds` family | 11 | Render a live `/metrics` inside the test container (`PYTEST_OPTS="-k test_metrics_endpoint -s"`) and read the exposition. Never assert the series from the library source alone |
| 4 | There is no `le="2.000"` bucket edge | 11 | Same render: the bucket edges actually exposed by `django_http_requests_latency_including_middlewares_seconds_bucket` |
| 5 | The `backup` container runs as UID 0 | 2 | `docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml run --rm --entrypoint /bin/sh backup -c "id -u"` — expect `0`. **Key names only, never values, when touching `.env.prod`** |
| 6 | `restore.md`'s flagless invocations abort during config rendering | 9 | `docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile backup config --services` with **no** `--env-file`; expect exit 1 |
| 7 | `/health/` is publicly reachable through the proxy | 18 | `curl -s https://<host>/health/ready/` from an external network. **The absence of a repository record is not proof that no external uptime monitor reads it** — see Q9 |
| 8 | A compose invocation **without** `--env-file` aborts | 1, 9, 10, 12 | Same command as 6. This is the mechanism behind `OPS-006`, `OPS-007` and `OPS-010`; all three depend on it |
| 9 | `Makefile`'s `restore` target resolves against the dev stack | 9 | Read `COMPOSE_FILES` and the target body; do not execute a `pg_restore` |
| 10 | `alembic`/`makemigrations --check` stays clean | all | `.\Makefile.ps1 test` includes the migration check. **Phase 12 ships no migration** |

---

### 0.3 Scope statement (explicit)

**In scope — 21 open finding-units.** 18 whole `OPS-` findings still exist unchanged, the
live halves of 2 partially-fixed findings, and 2 of the 3 `VAL-` findings (`VAL-001`,
`VAL-003`). Mapped onto 18 blocks in §2.

**De-scoped, absorbed, or narrowed by earlier phases — and where each is routed:**

| Item | What happened before this plan | Where it is recorded |
|---|---|---|
| **`OPS-005`** | **Merged into `OPS-007` by the validator.** Identical root cause, identical fix (add `--profile backup --profile scheduler --profile pgbouncer` to the deploy path). It is **not** a separate work item | BLOCK 8, which owns both consequences (stale scheduler, absent backup). The off-host-replication limb the validator demoted to advisory is **§6.1** |
| **`OPS-018`, 1 of 7 instances** | **Closed by phase 02** (`CFG-002`): `docker-deployment.md`'s deploy-check env paragraph was rewritten in the same commit that fixed the job. It is now true | Restated here so it is not silently re-filed. BLOCK 14 corrects the other **six** plus **six** new drift instances (C-11) |
| **`OPS-021`, comment limb (placement)** | **Half-closed by phase 02**: the rationale comment was relocated to sit above `deploy-check:` and extended to name `test_deploy_check_env_parity.py` | Only the stale `OPS-001` citation remains, and it is **BLOCK 3**'s. The backup-loop limb is **BLOCK 2**'s (C-12) |
| **`OPS-002`'s `CFG-002` precondition** | **Satisfied.** Phase 02 shipped `ci.yml`'s `deploy-check` env block and `config/settings/tests/test_deploy_check_env_parity.py`, which proves `config.settings.prod` imports in a scrubbed subprocess and carries two negative controls | BLOCK 10 may rely on the deploy gate actually executing. **It does not remove the post-merge-only gap**: `deploy-check` still runs on `push`, not `pull_request`, which is exactly what BLOCK 10 fixes |
| **`OPS-007`'s `ENT-003` sequencing constraint** | **Satisfied.** Phase 01 shipped the durable daily marker (`DailyMarker` protocol, `SchedulerDailyMarker` over the `SchedulerDailyState` singleton, `apps/core/migrations/0005_scheduler_daily_state.py`) plus the `send_alerts` idempotency contract (`uq_saved_search_ad` + `ignore_conflicts=True`) | BLOCK 8 may land without waiting for `ENT-003`. The first deploy that actually starts `scheduler` will not re-send the daily set. **The constraint is discharged, not ignored** |
| **`OPS-011`'s `EMAIL_HOST` limb** | **Removed by the validator as a duplicate of `API-009`** (phase 09). ✔ `src/telegram_bot/services/support_delivery_email.py` calls `send_mail` in production, and `EMAIL_HOST` is a mandatory guard in `prod.py` protecting a real path. `docs/ops/` contains zero "password reset" occurrences, so there is no ops-side instance | **Not re-filed.** BLOCK 12 touches operator alerting only, never `EMAIL_HOST` |
| **`VAL-002`** | **Stays open but is not a code change in this plan.** It is an audit-input gap about statement/lock timeouts; its application-side consequence is phase 03's `DB-004` and its ops-side consequence requires a timeout-budget decision | **§6.1**, routed to phase 03 with the cross-reference recorded |

**Not in scope — see §6.** Nine items the report proposed or implied and this plan refuses:
deploying a Prometheus/Alertmanager/Grafana stack, `scripts/ops/*.sh` *unless Q3 selects it*,
off-host backup replication, a `notify_operator` Telegram command *unless Q10 selects it*,
adopting `user: postgres` everywhere as a policy, documenting the `pgbouncer` profile as
available, `Makefile.ps1` gaining a `restore-test` target, an in-place migration of the ops
docs to scripts, and any new monitoring/ops framework. Every one has a stated rationale.

**No new architectural layer, base class, manager, registry or plugin mechanism is proposed.**
The net-new surface is: **one** shell script (`docker/healthcheck-backup.sh`, following an
existing shape), **one** committed contract file if `OPS-007`'s Q1 selects option (a), and
**one** management command if `OPS-011`'s Q10 selects option (a). Both of the latter two are
behind gates and neither may be created by an Implementor choosing on their own.

---

### 0.4 Severity corrections

The report's own reclassification is **upheld in full** and is not re-litigated.

| ID | Movement | This plan's position |
|---|---|---|
| `OPS-001` | CRITICAL → **HIGH** | **Upheld, and the direction matters.** There is no CRITICAL in this phase. The gate does **not** "always pass" — it **always fails** with exit 2, which is why nothing gates on it. The baseline strategy is rejected outright: a committed baseline would institutionalise 64 test-fixture `B106` suppressions and permanently permit new hardcoded credentials in production code. BLOCK 4 triages by class |
| `OPS-008`, `OPS-012`, `OPS-015` | HIGH→ / MEDIUM→ **LOW** or **MEDIUM** | **Upheld.** `OPS-008`'s central impact claim ("silent no-op in exactly the default configuration") is refuted — `deploy.yml` captures the CI tag before sourcing `.env.prod` and re-exports it after, specifically to defeat the `latest` default. The residual exposure is conditional on a manual deploy. `OPS-012` is log-format hygiene with a speculative security impact. `OPS-015` is a latent misconfiguration in a profile-gated service that zero `docs/ops` files mention |
| `OPS-005` | HIGH → **MEDIUM**, merged | **Upheld.** Single-host with no off-host copy is a design choice for a single-host Compose deployment, not a defect |
| `OPS-006`, `OPS-010`, `OPS-011`, `OPS-013` | severity held, evidence corrected | **Upheld.** Each finding survives on a narrower, sharper claim than reported (C-3, C-10, C-13) |

**Corrections this Planner makes to the *executed* risk, without re-grading the findings:**

- **`OPS-019` executes as LOW risk in `docker-compose.yml` but as a MEDIUM-risk edit in
  `docker-compose.test.yml`** (C-1). The base file's `db`/`redis` healthchecks are read by
  every stack and adding a `start_period` is additive. The **test** override is the file the
  `test` service itself depends on for its `depends_on: condition: service_healthy` chain;
  a mistake there turns the fast gate itself into a flake source for every phase. Both are
  BLOCK 1; the test-override edit is the reviewed part.
- **`OPS-014`'s stated mechanism is a hypothesis, not an observation** (C-3). The report's
  derivation — a `command:` override bypasses `postgres`'s entrypoint privilege drop — is
  structurally plausible and was not observed at runtime. BLOCK 2 asserts the **absence of
  `user:`** and the presence of a healthcheck, and it does **not** assert the running uid.
  The `id -u` probe is verification item 5, not a test.
- **`OPS-013` is the narrowest HIGH-adjacent item in the phase but the widest blast radius of
  the MEDIUM ones.** Every process importing `config.settings.prod` — `web`, `bot`, `migrate`,
  `load_cities`, `load_catalog`, `create_admin`, `seed`, `scheduler`, plus the CI `deploy-check`
  job — fails at import. `config/settings/prod.py` is a **phase-02-owned file**. BLOCK 6 is
  therefore small in diff and large in coordination, and it runs **after** BLOCK 7 so that
  the one `prod.py` edit in this plan is not competing with the env-allowlist edit.
- **`OPS-003`'s severity depends on a decision nobody has made.** If a monitoring stack is
  deployed, the finding is HIGH and the whole block grows. If the SLO artefacts are formally
  retired, the finding collapses to a documentation correction and the **rules file should
  not keep existing as if it were live**. That is why Q5 is a gate and not an assumption.

---

### 0.5 Open technical questions — resolved here, or explicitly gated in their block

**This plan does not choose where technical uncertainty exists.** Thirteen questions are
carried forward from the code context, plus four this Planner adds. Each produces either a
labelled **decision required before implementation** gate inside its block, with options and
consequences, or a named routing. **Silence is not an acceptable outcome for any of them.**

| ID | Question | Block | Who decides | Status |
|---|---|---|---|---|
| **Q1** | Where does the production long-lived service set live, given `deploy.yml`, `rollback.md` and `Makefile` must all consume it? (a) one committed contract file; (b) three copies plus a regression guard that asserts they agree; (c) `Makefile`'s currently-unused `COMPOSE_PROD` | **8** | Planner + Researcher | **GATED.** The report calls this the single highest-leverage change in the phase. It creates the file (or not), and it decides whether BLOCK 14's doc sweep has something stable to reference |
| **Q2** | What happens to `Makefile`'s dev-stack `restore` target, which `restore.md` points at for a **production** restore? (a) split into `restore` (dev) and `restore-prod`; (b) make it refuse without an explicit `--env-file .env.prod`; (c) document it as dev-only and give the runbook a separate procedure | **9** | Planner | **GATED.** This is the **irreversible-data surface**. An engineer at 3 a.m. following `restore.md` runs `pg_restore --clean --if-exists` against the **dev** database. No option is silent |
| **Q3** | Is `scripts/ops/*.sh` the right instrument for making runbooks executable, or is a markdown-parity test the better guard? (a) extract shell into linted scripts; (b) a parity test asserting every production `docker compose` block in `docs/ops/*.md` carries `--env-file` and both `-f` files; (c) both | **9** | Planner + Researcher | **GATED.** `scripts/ops/` has **no precedent and no lint harness** in the tree (C-8). Option (a) is a new capability; option (b) is string-level and therefore inherits `VAL-003`'s weakness; option (c) costs both |
| **Q4** | Is `user: postgres` on the `backup` service actually writable against the `./backups` host bind mount, and does the fix need a pre-created directory with matching ownership? | **2** | Researcher (runtime probe) + Planner (compose shape) | **GATED.** `postgres` in `postgres:18-alpine` is uid 70; a host bind mount is owned by the invoking uid. The answer may be "yes, plus a directory-provisioning step", which is an ops change, not a compose change |
| **Q5** | Does phase 12 deploy a monitoring stack, or retire the SLO artefacts? (a) deploy `prometheus` with `rule_files`; (b) retire the SLO artefacts and correct the docs; (c) minimum viable — correct the selectors, add a `promtool`-style lint, add the scrape-contract test, and defer the stack | **11** | **Owner** (product/infrastructure decision), escalated by the Planner | **GATED.** The report states plainly: *"this is a decision, not a task."* It changes the block's size by an order of magnitude and adds a secret surface if (a) is chosen |
| **Q6** | For `OPS-010`: enable `BOT_HEALTH_CHECK_ENABLED=true` for `web` in production, or remove the shipped-but-disabled staleness window and the doc claims? | **13** | Owner (operational) + Planner | **GATED.** Enabling makes a wedged bot return 503 from `/health/ready/`, which is the **deploy gate** and the rollback validation target. That is a deploy-pipeline behaviour change |
| **Q7** | For `VAL-001`: add every `*_MEM_LIMIT` / `*_CPUS` key to all four `.env.*.example` files and to `ALLOWED_ENV_VARS`, or ship only the guard that prevents **silent** regression? | **7** | Planner + phase 02 (which owns the allowlist) | **GATED.** `config/settings/base.py`'s allowlist is phase-02-owned and `test_env_allowlist.py` reads it in **both** directions. Adding ~20 keys × 4 files is a large diff against another phase's file |
| **Q8** | For `OPS-004`: is off-host artifact replication in scope? Without it, the real-artifact restore drill cannot pass at all | **16** | **Owner** (infrastructure) | **GATED, may be declined.** BLOCK 16's *unconditional* half still ships either way; only the real-artifact consumption is conditional |
| **Q9** | **Does anything external consume `/health/`?** | **18** | **Coordinator / owner** — not the Implementor | **GATED, blocking.** This is the only backward-incompatible change in the phase. ✔ Nothing in the repository records an uptime monitor, a status-page integration or a `UptimeRobot`/`healthchecks.io` reference — **but absence of a record is not proof**, and an external monitor reading `/health/ready/` would begin receiving `403` |
| **Q10** | For `OPS-011`, what is the operator-notification floor? (a) a `manage.py notify_operator` command delivered over the existing Telegram transport; (b) a dump-age + container-health **metric** only, consumed by whatever Q5 decides; (c) neither — formally declare detection out of scope for a single-host deployment and document the gap | **12** | **Owner**, with Planner on (a)'s shape | **GATED.** Option (a) needs a recipient configuration key that does not exist: adding one means `ALLOWED_ENV_VARS` **and** all four `.env.*.example` files, or `test_env_allowlist.py` fails. And it must run inside the `backup` service, which is `read_only: true`, `cap_drop: ["ALL"]` and — until BLOCK 2 — root |
| **Q11** | For `OPS-002`, what is the deploy-gate mechanism? (a) assert in-workflow that the dispatched SHA is on `main` with a green `CI` run; (b) a `workflow_run` trigger chained to `CI`; (c) repository branch protection as the enforcement point plus a constrained input | **10** | **Owner**, with Planner on (a)'s implementation | **GATED.** (b) removes the human approval that currently exists; (c) moves the control outside the repository, where this plan cannot verify it. All four agents are required for this block |
| **Q12** | For `OPS-008`, what replaces the tag-based capture — digest capture, a required-SHA template, or both? | **10** | Planner | **GATED.** `docker inspect --format='{{index .Image}}' "$(docker compose ps -q web)"` appears nowhere in the repository and is untested here; `restore-test.yml` also pulls by tag, so a digest-only scheme needs a second change |
| **Q13** | *New.* Does any phase-12 block need an `AdvisoryLockId`? | — | Planner | **ROUTED, default is no.** Phase 12 allocates **none** (C-6). Next free integer is `14`. If a block appears to need one — the plausible case is a `notify_operator` invoked concurrently — that is a decision gate, it requires re-reading `apps/core/enums.py` immediately before editing, and it must be reported to the coordinator because phases 03/05/06/07/10 all hold that file |
| **Q14** | *New.* Does the `docs/ops` parity test resolve markdown cross-references? | **15** | Planner | **GATED, and it must be answered as (b) unless argued.** `docs/ops/docker-deployment.md` contains a link to the **deleted** `.ai/audit/12-production-ops/findings.md`. Option (a) resolve links → the test is red on arrival for a defect BLOCK 14 must also fix; option (b) do not resolve links → the dead link stays. **The default answer is (b)** with the dead link re-pointed at the validated report, and BLOCK 14 must say so in its commit body |

**Resolved in this plan, with the reasoning stated** (rulings, so a block does not re-derive
them — these are *not* open questions):

- **The block taxonomy.** `mechanical` = no observable behaviour change, no outcome-changing
  gate. `behavioural` = changes an observable response, touches a shared contract, breaks a
  shipped test, or is gated. `structural` = introduces a contract or a source of truth. `conditional`
  = ships a reduced deliverable if its gate is declined. The classification is in §2 and
  repeated in each block header.
- **The order principle.** `docker-compose.yml` and `docker-compose.test.yml` get exactly one
  owner (BLOCK 1, first). `ci.yml` gets three sequential owners (BLOCKS 3 → 4 → 5), all
  mechanical and all in-place. `deploy.yml` gets four (BLOCKS 2 → 3 → 8 → 10), structural last.
  `test_compose_contract.py` gets three (BLOCKS 1 → 2 → 7). The docs sweep (BLOCK 14) lands
  after every code change it documents, and the parity guard (BLOCK 15) after the docs.
- **`OPS-006` and `OPS-007` are NOT merged into one block**, contrary to the report's
  "merge them into one change" instruction. The report's reason is a **merge conflict** — both
  edit `deploy.yml` and `rollback.md`. With one Implementor running strictly sequentially there
  is no conflict to avoid; merging would instead put two independent decision gates (Q1, Q3)
  and two different owners' reasoning into one commit, and would make BLOCK 9 — the
  irreversible-data block — un-reviewable in isolation. The overlap is recorded in §4.2 as a
  hard sequential edge instead, which delivers the same single review window.
- **`VAL-003` is a convention, not a code change.** It is enforced by §1.5 and by every block's
  `acceptance_criteria`; it ships no file.

---

## 1. Environment and command contract for the implementor

**This environment is Windows 11 / PowerShell 7.** `make` requires WSL or GNU Make; use
`.\Makefile.ps1 <target>`. `head` / `tail` are unavailable in PowerShell.

### 1.1 Tests are Docker-only — `uv run pytest` on the host always fails

There is no PostgreSQL on `localhost:5432`. Every test run goes through the `test` service
of the `mko-bazuna-test` Compose project. `docker/entrypoint-test.sh` performs **no** database
setup: pytest-django provisions `test_mko_bazuna`, and the session-autouse fixture in
`src/backend/conftest.py` restores reference data under advisory lock `111`.

```powershell
# Alias, copied once per session
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'

# Start the DB if it is not already up
docker ps --filter "name=mko-bazuna-test-db-"
$dc up -d db

# Fast gate (skips the nightly `seed` suite) - the default iteration command
$dc run --rm --env PYTEST_SKIP_MARKERS=seed test

# Targeted run
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="-k test_name" test
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/tests/test_compose_hardening.py --tb=short" test

# Full suite (only when the change touches seeding or images)
$dc run --rm test

# Fresh schema (no phase-12 block ships a migration; use only if one appears
# that phase 12 did not write)
$dc run --rm --env PYTEST_OPTS="--create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup" test
```

**Four caveats that will silently produce a wrong result if ignored:**

- `--env-file .env.test` is **required**; without it compose aborts on `${POSTGRES_*?}`
  interpolation. **Never** substitute the `mko-bazuna-dev` project name.
- Setting `PYTEST_OPTS` **replaces** the defaults
  (`--reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup`), so a
  targeted run loses xdist parallelism and DB reuse. `PYTEST_OPTS` is also **unquoted** in
  the entrypoint, so each token is word-split on spaces: `-k test_name` and bare paths work,
  quoted multi-token values do **not**. Never use `--override-ini=addopts=` — it strips
  `--import-mode=importlib`, which `pyproject.toml` requires.
- **Never use `--override-ini=addopts=`** and never `uv run pytest` locally. Both are the
  documented ways to get a green gate that tested nothing.
- **Concurrent runs collide on the single `test_mko_bazuna` database.** If a gate goes red
  while another phase agent is running, **re-run it serially** before reporting it as a
  defect. Teardown races surface as `FATAL: database "test_mko_bazuna" does not exist` and
  `relation "..." does not exist`, not as product failures.

Prefer `.\Makefile.ps1 up | test | test-all | test-recreate | test-down` — they manage the
project name and env file for you.

**A phase-12-specific warning.** BLOCK 1 edits `docker-compose.test.yml`, the file this
command reads. **Run the fast gate after BLOCK 1 and again after any block that touches
`docker-compose.yml` or `docker-compose.test.yml`, before running anything else.** If the
gate cannot even reach the test service, the failure is the compose file, not a test.

### 1.2 Lint, typecheck, i18n

```powershell
uv run ruff check <path>            # lint
uv run ruff check --fix <path>      # auto-fix, INCLUDING import sorting (I001)
uv run basedpyright <path>          # typecheck
uv run djlint src/backend/templates/   # only if a template changes
```

CI runs `uv run ruff check src/` and `uv run basedpyright src/` (phase 01 `ENT-004` scoped
both to `src/`, so **the bot process is inside both gates**).

**Ops work is mostly YAML, shell and Markdown, and none of it is covered by `ruff` or
`basedpyright`.** The gates that matter for this phase are: `docker compose … config`
renders cleanly for each of the three stacks; `.\Makefile.ps1 test` is green; and any new
`*.py` test file passes ruff and basedpyright.

**Shell:** there is **no shell-lint harness in the repository**. If BLOCK 2 ships
`docker/healthcheck-backup.sh` or BLOCK 9 ships anything under `scripts/`, it must be
`chmod +x` (the Dockerfile does this for the two existing healthcheck scripts), must be
asserted executable by a test, and must be verified with `sh -n <script>` — there is no
`shellcheck` in the toolchain and this plan does not add one.

**YAML:** there is **no YAML linter in the toolchain** either. The verification is
`docker compose … config` per stack (below), plus `ruamel.yaml` parsing in the tests, which
is the existing precedent in `src/backend/tests/test_compose_contract.py`.

```powershell
# Render each stack; every one must exit 0
$dc config --services                       # test stack
$dc config --services --profile backup      # prod-ish (needs .env.prod; see note)
docker compose --project-name mko-bazuna-dev --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml config --services
```

**Never render the prod stack against the operator's real `.env.prod`** — it is gitignored and
operator-local. If a prod render is needed, use a scratch env file in
`C:\Users\Om\AppData\Local\Temp\kilo` with placeholder values, and read **key names only,
never values** (phase 02's rule).

**i18n is part of DoD, and this phase almost does not touch it.** Only BLOCK 12 option (a)
could add an operator-facing message, and only under its gate. BLOCK 6 adds a **log**
message, which is not a translatable string and must be written in English, value-free.
`LOCALE_PATHS` is `[BASE_DIR / "backend" / "locale"]` — **one** catalogue serves web and bot,
shared with phases 03/05/06/07/10/11/14. **Append; never regenerate wholesale.**

### 1.3 Git contract — one implementor, sequential, one commit per block

- **One Implementor at a time.** Never two. Never a background implementor.
- If a block is stopped mid-way, **resume the existing session**; do not launch a new agent.
- Each block is committed separately, explicitly staged: `git add <specific files>` —
  never `git add -A`, never `git add .`.
- Message form, matching the repo style: `"{type}({scope}): {description}"`, e.g.
  `fix(ops): add start_period to db and redis healthchecks (12-OPS-019)`,
  `ci(ops): constrain the deploy input to a verified SHA (12-OPS-002)`,
  `docs(ops): correct the false control claims in docs/ops (12-OPS-018)`.
  Every citation is cycle-scoped **`12-OPS-0NN`**, never a bare `OPS-0NN`.
- **Never** `git reset`, `git checkout`, `git restore`, `git stash`, `--amend`,
  `--no-verify`, or any other history mutation. Never force-push.
- **Other agents are working in parallel**, and several are editing the same files. Files
  you did not change appearing in `git status` is normal. **Never** revert, stash or
  `git checkout` a file you did not write. If a file you are about to edit already has
  uncommitted changes from another agent, **stop and report it** rather than clobbering it.
  This is the normal case for `config/settings/base.py`, `config/settings/prod.py`,
  `.github/workflows/ci.yml`, `docker-compose.prod.yml` and `apps/core/enums.py`.
- Do not commit unless the block's instructions say to.

### 1.4 Standing project rules (restated for every block)

- **English only** — comments, logs, docstrings, error messages, documentation.
- **No `print()`.** `logger = logging.getLogger(__name__)` with lazy `%s` formatting.
  This matters most in BLOCK 6 and BLOCK 12, which are the only blocks that add logging.
- Stack: **Python 3.14 · Django 5.2 LTS (`>=5.2.16,<6.0`) · PostgreSQL 18 · aiogram 3.x ·
  native PostgreSQL FTS.** **Two processes, one DB:** web (gunicorn sync WSGI, HTMX MPA)
  and bot (aiogram, `django.setup()` + shared ORM). **Migrations run exactly once** before
  both start — a migration that must run in only one process is a defect.
- **Django ORM is the persistence layer.** **Pydantic v2 only at system boundaries** (bot
  input, settings schemas, DTOs at a request edge). Business logic lives in `services/`.
  **This plan adds no DTO and no model.**
- **All schema changes via Django migrations.** **This plan ships no migration.** Never
  renumber or edit an applied migration.
- **Fixed values via `StrEnum` / `Enum`** (project rule 10) — never plain strings, dicts or
  lists. In-repo precedent: `AdStatus`, `AdSort`, `AdvisoryLockId`, `LanguageLocale`,
  `CategoryRejectReason`, `LookupGroupCode`.
- **Small, focused modules and functions. Composition over inheritance.** Follow existing
  patterns; **no new abstraction without strong justification**; no speculative redesign;
  **no scope creep**. Every remedy the report proposes that fails this test is in §6.
- **Production code is king.** If a test conflicts with the architecture or the business
  logic, **fix the test** — and say which change and why in the commit body. This plan
  pre-authorises exactly **two** such changes, each under a named gate: BLOCK 4's
  `test_ci_yml_has_sast_job` (substring → behavioural) and BLOCK 15's parity test (written
  *after* the docs are corrected). Each must state the rule invoked and why in its body.
- **Docs must stay in sync.** `docs/00-overview/doc-maintenance-rules.md`,
  `docs/99-agent/architecture.md`, `docs/99-agent/rules.md`, and any ops or runbook document.
  BLOCK 14 is the phase's documentation block; BLOCK 9 also edits runbooks.
- **Secret handling is governed by phase 02**, not by this phase: `ALLOWED_ENV_VARS` in
  `config/settings/base.py`, the `prod.py` deploy gate, and
  `config/settings/tests/test_deploy_check_env_parity.py`. **Any new env key a block adds to
  an `.env.*.example` file must also be added to `ALLOWED_ENV_VARS` in the same commit**, or
  `test_env_allowlist.py` fails — the test reads in **both** directions.
  **Never read or print a value from `.env.prod`.** Key names only.
- **`gunicorn.conf.py` lives at the repository root**, not under `src/backend/` — the runtime
  CWD is `/app`. BLOCK 12 edits it and **must not remove phase 01's `child_exit` hook**.
- **Do not edit `src/backend/conftest.py`.** It is among the most contended files in the
  repository. If a block appears to need a new fixture, that is a signal the test is
  over-fitted.
- **Do not start, stop or modify any container or compose stack** except through the test
  commands in §1.1 and the read-only `config` renders in §1.2. Never `docker compose down -v`.

### 1.5 Test authoring standard for every block

Tests verify **logic and component interaction**, not implementation trivia. No test asserts
a line number, a column count from introspection, a literal private name, a template-string
substring, or the mere presence of a symbol. Assert on **observable behaviour** and on the
**absence of danger**.

**The phase-specific rule — `VAL-003`.** A guard that asserts a *string* cannot assert that a
*control* is effective. That single fact is the shared root cause of `OPS-001`, `OPS-003` and
`OPS-004`, and every new ops guard in this plan is measured against it:

| Instead of | Assert |
|---|---|
| `"bandit" in content` | the step's scan roots **exist** and the configured scan produces a **non-zero file count** (BLOCK 4) |
| `"/metrics" returns 200` | the exposition **contains the series every alert selector names** (BLOCK 11) |
| `"healthcheck:" in block` | every healthcheck **declares `start_period`** and the value is a parseable duration (BLOCK 1) |
| `"user:" not in block` is inferred | the service **either declares `user:` or is on the exception list**, and an exception has a reason (BLOCK 2) |
| the restore drill `echo`s counts | the restored database **has `django_migrations` and a plausible `ads_ad` row count** (BLOCK 16) |
| `for key in _HARDENING_KEYS: assert key in block` | keep the existing string guard **and add** the behavioural assertions; do not extend the shared constant (BLOCK 2) |

**`apps/core/tests/test_observability.py::test_metrics_endpoint` is the one behavioural
precedent in the repository** — it renders a real response and asserts the exposition. Use
it as the model for BLOCK 11, and its shape for every other behavioural guard here.

**Good targets for this phase:**

- every healthcheck in every compose file declares a `start_period`, and deleting it from any
  one of them turns the guard red;
- `backup` declares a `user:` **or** appears in the exception list **with a reason**, and a
  service added to the exception list without one fails;
- the alert file's every `expr` selector resolves against a rendered `/metrics`, and adding
  a selector naming a series that does not exist turns the test red;
- the deploy workflow's compose invocations name **every** service the prod manifest declares
  as long-lived, and adding a `restart:`-carrying service to the prod manifest without naming
  it in the deploy path turns the guard red;
- a malformed `SENTRY_DSN` leaves `config.settings.prod` importable and the process booting;
- a restored database with zero `ads_ad` rows **fails** the restore target.

**Never use a line number as a task target.** Every target is a file plus a **semantic**
anchor: a service name in a compose file, a job key in a workflow, a compose **profile** name,
a class, a method, a module-level constant, a function call, a URL route name, a `.po` msgid,
a shell script path.

Fixtures are canonical in `src/backend/conftest.py`: `seller` (900000001), `user` (900000002),
`category`, `city`, and
`create_test_ad(user, category, city, *, status=AdStatus.PUBLISHED, **kwargs)`.

### 1.6 Task shape for every block

Each block's implementor task follows `.ai\tasks\templates\task_template.yaml`: semantic
`targets` with `type` / `name`, `semantic_anchors`, `changes`, `acceptance_criteria`,
`source_reference` / `source_section` / `source_blocks`, and an `extra_context` block carrying
the block's binding constraints **verbatim**. Verification is **inline** for `mechanical`
blocks (the Implementor runs `tests_to_run` and checks `acceptance_criteria`); a **separate
Validator task is required** for every `behavioural`, `structural` and `conditional` block,
for every block whose acceptance depends on a decision the Implementor was told not to make,
and for **all four agents** on the six high-risk blocks named in each header.

---

## 2. Scope decisions table (acceptance contract for execution)

`mechanical` = no observable behaviour change, no outcome-changing gate, safe to batch or run
without a Validator. `behavioural` = changes an observable response, touches a shared contract,
breaks a shipped test, or is gated. `structural` = introduces a contract or a source of truth.
`conditional` = ships a reduced deliverable if its gate is declined.

| ID | Class | Disposition | Block | Severity | One-line reason |
|---|---|---|---|---|---|
| `OPS-001` | **behavioural** | **implement — gated on nothing, but the triage is the work.** Fix both scan roots and the config path, repair `exclude_dirs` to the real test trees, triage the residual **by class, never by baseline**, and replace `test_ci_yml_has_sast_job` with a scanned-file-count assertion | **4** | HIGH (↓CRITICAL) | Two independent path-relativity errors make the step exit 2; **no Python file in the repository has ever been statically analysed**. The report's baseline recommendation is **rejected** (it would institutionalise 64 test-fixture `B106` and permanently permit new hardcoded credentials in production code). The `security` job runs no pytest, so no test there can fail for a second reason |
| `OPS-002` | **behavioural** | **implement — gated on Q11.** Add `on: pull_request` to `ci.yml`; constrain the deploy input per the chosen mechanism. **The `CFG-002` precondition is already satisfied** | **10** | HIGH | Two independent ungated paths to a production image: any PR is ungated, and any SHA can be typed into a free-text input. The manual environment approval is a human checkbox, not a verification. The report's sequencing constraint ("land `CFG-002` before `OPS-002`") is **discharged** |
| `OPS-003` | **behavioural** | **implement the selector correction and the scrape-contract test unconditionally; the monitoring stack is gated on Q5 and may be declined.** Correct the stale multiprocess caveat in the same pass | **11** | HIGH | Three alert rules select series that do not exist (`django_http_response_duration_seconds` + a `handler` label + a `le="2.000"` edge), one of them from a `redis_exporter` that is not deployed, and **no Prometheus exists in any compose file**. The durable fix is a scrape-contract test, which is verifiable **today** through `test_observability.py` |
| `OPS-004` | **conditional** | **implement the unconditional half; gate the real-artifact half on Q8.** Assert non-empty restores and `django_migrations` presence; pin the app image to a recorded known-good tag instead of `${{ github.sha }}`; keep the self-generated dump as a labelled **additional** smoke test | **16** | HIGH | The monthly control restores a dump it generated three steps earlier from a healthy in-memory database, so it proves nothing about the artifacts it exists to prove. ✔ **Without an off-host artifact path the real-artifact half is impossible** — that is a platform investment, not an edit. On a `schedule` trigger `github.sha` is the default-branch tip and may have no pushed image |
| `OPS-005` | — | **merged → `OPS-007`; not a separate work item** | **8** | MEDIUM | Same root cause and same fix as `OPS-007`. The off-host-replication limb was demoted by the validator to advisory (§6.1) |
| `OPS-006` | **behavioural** | **implement — gated on Q2 (irreversible-data surface) and Q3 (instrument).** `--env-file .env.prod` on every production invocation in `restore.md`; `.env.prod` as the credential source, never `.env.dev`; sweep `postgres-18-docker-volume-migration.md` and `migration-workflow.md` | **9** | HIGH | The document an engineer opens when the database is already lost cannot be followed: **every** invocation aborts at config rendering. The `.env.dev` credential read is a dev/prod confusion, not a missing flag — it points the operator at the wrong database. **Do not touch `rollback.md`'s production invocations — they are already correct** (C-10) |
| `OPS-007` | **structural** | **implement — gated on Q1.** Name every long-lived prod service in every deploy compose invocation, in both recreate commands, and in the runbooks; add the regression guard keyed on `restart:` | **8** | HIGH | Three services are profile-gated and none is named by the deploy path, so after a deploy the scheduler runs an arbitrarily stale image and the daily backup job **is never started**. Rollback is not atomic. **The report's `ENT-003` sequencing constraint is discharged** by phase 01 |
| `OPS-008` | **behavioural** | **implement — gated on Q12, with BLOCK 10.** Capture the digest, roll back by digest, forbid `IMAGE_TAG=latest` in the prod template, and cover the no-previous-digest and digest-absent branches | **10** | MEDIUM (↓HIGH) | Tags are mutable labels, not identity, and no digest is captured anywhere. The report's "silent no-op in exactly the default configuration" is **refuted** — `deploy.yml` deliberately re-exports the CI tag after sourcing `.env.prod` — so the exposure is conditional on a manual deploy |
| `OPS-009` | **mechanical** | **implement.** Define the image coordinate once as a `build` job output; align `cache-from` with `cache-to`; guard the literals across the four files | **3** | MEDIUM | Three namespaces, and `cache-from`/`cache-to` **also disagree with each other** (`mko_bazuna` vs `mko-bazuna`) — which silently degrades every CI build to a cold cache. The `build` job already declares `outputs.image_tag`, the natural single source |
| `OPS-010` | **behavioural** | **implement — gated on Q6.** Either enable the coupling in prod and document it, or remove the shipped-but-disabled window and the doc claims | **13** | MEDIUM | A configured-but-disabled control: `BOT_HEALTH_STALE_SECONDS=120` ships for `web` and `bot`, the enable flag defaults `False`, appears in no compose file and no `.env.*.example`. The impact is narrower than reported — new submissions are not *started*, already-persisted `DRAFT` rows are unaffected |
| `OPS-011` | **behavioural** | **implement the labelling half unconditionally; gate the notification floor on Q10.** Whatever is chosen, the SLO artefacts must stop reading as active controls | **12** | MEDIUM | Nothing anywhere inspects container health, dump freshness, deploy outcome or the SLO rules. A stuck `unhealthy` container and a backup job that died a week ago are discovered by users. **`EMAIL_HOST` is phase 09's `API-009` and is not re-filed** |
| `OPS-012` | **behavioural** | **implement.** `logconfig_dict` routing `gunicorn.access`/`gunicorn.error` at the existing `RedactingJsonFormatter`, plus a structured `access_log_format`. **Preserve phase 01's `child_exit` hook.** Keep `accesslog`/`errorlog` set until proven | **17** | LOW (↓MEDIUM) | The production log stream mixes JSONL and plaintext with the highest-volume record unstructured. **No demonstrated security exposure exists** — the gap is a property of the format, not of any parameter the application emits. `logconfig_dict` changes gunicorn startup; a malformed config crashes the arbiter **before** the bind, turning a logging change into an outage |
| `OPS-013` | **mechanical** | **implement.** Validate the DSN before use (shape check, or a guarded `except` around `sentry_sdk.init`), log **value-free**, add the malformed-DSN row to the existing subprocess harness | **6** | MEDIUM | A purely optional, non-security setting, shipped empty, can take the **entire** production stack offline at settings import — every process plus the CI `deploy-check` job. The report's trigger examples (leading space, trailing newline) are **handled** by `sentry-sdk 2.69.2`; the live trigger is an unrecognised scheme |
| `OPS-014` | **behavioural** | **implement — gated on Q4.** `user:` + a dump-age healthcheck on `backup`; align the dump filename with the prune glob at all three sites; add the hardening guard **as an exception list**, not by extending `_HARDENING_KEYS` | **2** | MEDIUM | A root container holding `POSTGRES_PASSWORD` and writing to a host bind mount, with no healthcheck and no dump-age signal, and `backup-*.dump` files the prune globs never match accumulating until the disk fills. ✔ The **running uid was not observed** (C-3) — the assertion is the **absence**, not the inferred uid |
| `OPS-015` | **mechanical** | **implement.** `PGBOUNCER_AUTH_TYPE=scram-sha-256`; a real-YAML assertion that the auth type matches the engine's `password_encryption` default. **Do not document the profile as available** | **7** | LOW (↓MEDIUM) | The application is explicitly designed for this pooler (`prepare_threshold: None`, `CONN_MAX_AGE = 0`) and the pooler cannot authenticate. Latent only: the service is profile-gated and `pgbouncer` appears in **zero** `docs/ops` files, so nothing in the repository would ever enable it |
| `OPS-016` | **mechanical** | **implement.** `concurrency` on `ci.yml` and `deploy.yml`, following the `ci-nightly.yml` / `restore-test.yml` shape; guard its presence | **3** | MEDIUM | Two overlapping deploys interleave `pull` and `up -d` against one host, and the health gate can validate a half-applied mix of images — **green runs, silently**. Compounded by `OPS-009`'s cache-coordinate mismatch |
| `OPS-017` | **mechanical** | **implement.** Pin every third-party action to a full commit SHA with the version in a trailing comment; verify the gitleaks download against a committed checksum; **pin and verify the `syft` install in `docker/Dockerfile` and the Tailwind `latest/download` fetch** | **5** | MEDIUM | The trust boundary is the least-pinned part of the system. `appleboy/ssh-action` receives the **production SSH private key**. The unverified gitleaks tarball is the step that decides whether a secret enters the repository; the unverified `syft` install means the shipped image's toolchain provenance is unverified at every build. Dependabot keeps the pins updated |
| `OPS-018` | **behavioural** | **implement — after BLOCKS 4 and 9.** Correct **twelve** instances (the report's six live ones plus the six drift instances phases 01/02 created). Do **not** reintroduce the refuted `bazuna_db` sub-claim | **14** | MEDIUM | The ops documentation is the only description of the production system and a reader cannot tell which parts are live: a false claim about a security control, a false recovery procedure, and a false rollback procedure on a gitignored file. The report's warning holds — **the parity test comes later, never in the same commit** |
| `OPS-019` | **mechanical** | **implement — first block in the plan.** `start_period` on all four missing healthchecks, **including `docker-compose.test.yml` and `docker-compose.prod.yml`'s `pgbouncer`**, which the report did not name; per-file guard | **1** | LOW | A failing probe counts toward `retries` immediately, so PostgreSQL 18 can be marked `unhealthy` during crash recovery and the `depends_on` chain fails to start — surfacing as a cascade of one-shot services exiting non-zero rather than "database still starting". **Wider than the report** (C-1), and one of the four files is the one every phase's test command reads |
| `OPS-020` | **conditional** | **implement — blocked on Q9.** Restrict `/health/` the same way `/metrics` is restricted, or return a reduced public body behind an internal-only path | **18** | LOW | An anonymous caller can poll readiness and read both service availability and the identity of the failing dependency. **The only backward-incompatible change in the phase.** ✔ Nothing in the repository records an external consumer — **but that is not proof** |
| `OPS-021` | **mechanical** | **implement the comment limb in BLOCK 3; the backup-loop limb in BLOCK 2.** Fix the stale `OPS-001` citation in the `deploy-check` rationale header; drift-compensate the sleep and assert dump freshness | **2**, **3** | LOW | The rationale comment now sits in the right place (phase 02 moved it) — **only the wrong ID reference remains**, and it points at the bandit finding. The loop's true interval is 24 h plus dump duration plus retry delay, and nothing anywhere asserts the newest dump is recent |
| `VAL-001` | **behavioural** | **implement — gated on Q7.** `mem_limit` / `cpus` resolution contract plus a guard that the defaults cannot ship silently; cross-reference `SRCH-001` rather than merging with it | **7** | MEDIUM | The ops layer declares **no** capacity limits and enforces no `mem_limit` contract; every environment falls back to the compose default. `SRCH-001` owns the OOM consequence — **fixing one does not close the other**, and a reader must not conclude otherwise |
| `VAL-002` | — | **not a code change here** — the ops-surface timeout-budget item requires a decision that interacts with phase 03 `DB-004` | §6.1 | LOW | 0 matches for `lock_timeout` / `statement_timeout` in the one-shot containers or the scheduler's child dispatch. A stuck `pg_dump` is indistinguishable from a slow one, is not covered by any healthcheck, and is never pruned. Routed to phase 03 with the intersection recorded |
| `VAL-003` | **mechanical** | **implement as a convention**, enforced by §1.5 and by every block's `acceptance_criteria`. Ships no file | all | MEDIUM | Every existing ops guard is string-level, and that is the shared root cause of `OPS-001`, `OPS-003` and `OPS-004`. **A guard that asserts a token is present cannot assert that a control is effective.** Highest leverage per byte in the phase |
| `Q1` / `Q11` | — | **GATED** — Planner + Researcher (Q1); Owner + Planner (Q11) | **8**, **10** | — | The two structural gates. Q1 creates the contract file; Q11 chooses the deploy-gate mechanism and therefore the block's shape |
| `Q2` / `Q3` / `Q4` / `Q5` / `Q6` / `Q7` / `Q8` / `Q9` / `Q10` / `Q12` | — | **GATED** — each inside its block, with the options and consequences written down | **2**, **9**, **11**, **13**, **16**, **18**, **12**, **10** | — | Ten further gates. Q9 is **blocking** on BLOCK 18. Q5, Q8, Q10 and Q11 are **owner** decisions, not Planner decisions — the report itself says "this is a decision, not a task" |
| `Q13` / `Q14` | — | **ROUTED** / **GATED, default answer stated** | — | **Q14** BLOCK 15 | `Q13`: phase 12 allocates no lock id; next free is `14`; the file is held by five phases. `Q14`: the parity test does **not** resolve markdown links by default, and BLOCK 14 re-points the dead one |

**Note on `OPS-012`.** Its subject (`gunicorn.conf.py` at the repository root) is owned by
phase 01 (`ENT-001`, the `child_exit` hook). It is **not** merged into BLOCK 12 because
BLOCK 12's subject is `docs/ops/prometheus-slo-alerts.yaml` and the operator-notification
decision — two different files, two different owners and two different failure modes. It is
**BLOCK 17**, and the `child_exit` constraint is stated in its header. The report's own
instruction ("do not let it compete with `OPS-007` for the same deploy window") is honoured by
placing it near the end of the order.

**Block classification summary:** `mechanical` = **1, 3, 5, 6, 7** ·
`behavioural` = **2, 4, 9, 10, 11, 12, 13, 14, 15, 17** · `structural` = **8** ·
`conditional` = **16, 18**.

---

## 3. Execution blocks

Eighteen blocks. **One Implementor, strictly sequential, one commit per block** (§1.3). The
numbering *is* the serial order, and the order is chosen so that **the highest blast-radius
files in the repository are written exactly once, by the earliest blocks**:

```
docker-compose.yml          1 only                (base of all three stacks)
docker-compose.test.yml     1 only                (the file the test command reads)
ci.yml                      3 → 4 → 5             (all mechanical, all in place)
deploy.yml                  2 → 3 → 8 → 10        (structural last)
docker-compose.prod.yml     2 → 7 → 13            (prod-only: safest surface)
test_compose_contract.py    1 → 2 → 7             (real YAML, per file, no merge)
Makefile                    2 → 9 → 16            (prune globs, restore target, drill)
docs/ops/**                 9 → 14 → 15           (runbooks, then truth, then the guard)
config/settings/prod.py     6 only                (phase-02-owned file)
```

**Eleven blocks carry a labelled decision required before implementation gate or an external
gate.** A gated block does not start until the answer is written down; **the Implementor is
forbidden from choosing an option** (§1.3, §8.1).

---

### BLOCK 1 — Healthcheck `start_period` on every service that lacks one (`OPS-019`)

| | |
|---|---|
| **Findings owned** | `OPS-019` (LOW) |
| **Class** | **mechanical** — additive YAML keys with no behaviour change |
| **Depends on** | nothing in-plan |
| **Blocks** | BLOCK 2, BLOCK 7 (`test_compose_contract.py`); every block's fast gate |
| **Priority** | **P0.** First because it touches the two files whose breakage is felt by every phase |
| **Risk level** | **MEDIUM execution risk** — LOW for `docker-compose.yml`, MEDIUM for `docker-compose.test.yml` |
| **Blast radius** | **The widest in the plan.** `docker-compose.yml` is the base of dev, test and prod; `docker-compose.test.yml` is the file `.\Makefile.ps1 test` reads. A mistake here breaks the fast gate for **every** phase in the programme |
| **Required agents** | **Auditor · Researcher · Planner · Validator** — all four, because the blast radius is programme-wide |

**Scope correction (C-1).** The report names two healthchecks in one file. The tree has
**four, across three files**: `docker-compose.yml` `db` and `redis`; `docker-compose.test.yml`
`db`; and `docker-compose.prod.yml` `pgbouncer` — the last of which **neither the report nor
the code context named**. All four are in scope for this block.

**File surface (semantic units)**

| File | Service | Current | Notes |
|---|---|---|---|
| `docker-compose.yml` | `db` | `interval: 5s` / `timeout: 5s` / `retries: 5` | Add `start_period` |
| `docker-compose.yml` | `redis` | `interval: 5s` / `timeout: 3s` / `retries: 5` | Add `start_period` |
| `docker-compose.test.yml` | `db` | `interval: 5s` / `timeout: 5s` / `retries: 5` | **The reviewed edit.** The `test` service gates on this service with `condition: service_healthy` |
| `docker-compose.prod.yml` | `pgbouncer` | `interval: 5s` / `timeout: 5s` / `retries: 5` | Add `start_period`. **Unfiled by the report** |

The existing `start_period` values are the precedent for the scale: `web` 5 s, `bot` 30 s,
prod `scheduler` 600 s. **Choose the value from the recovery characteristics of the service,
not by copying a neighbour** — and say which value and why in the commit body.

**Binding constraints**

1. **`docker-compose.yml` and `docker-compose.test.yml` are written by no other block in this
   plan.** If a later block appears to need an edit there, that is a report, not an edit.
2. **Parse each compose file independently; never merge.** The base, dev-override, test and
   prod files use `!reset` and `!override` YAML tags, and the prod file needs neither.
   `src/backend/tests/test_compose_contract.py::_load_yaml` is the existing precedent and
   registers pass-through constructors for both tags.
3. **The guard asserts a parseable duration, not the string `"start_period"`.** A guard that
   asserts the token reproduces `VAL-003` — the class of defect this phase exists to remove.
4. **Run `.\Makefile.ps1 test` immediately after this block, before starting BLOCK 2.** If the
   gate cannot reach the test service, the failure is the compose file, not a test.
5. **Do not change `interval`, `timeout` or `retries`.** This block adds `start_period` and
   nothing else. A `retries` change alters cold-start recovery semantics and is a different
   decision.

**Implementor task**

```yaml
id: task_12_b01_healthcheck_start_period
title: "Add start_period to every healthcheck that lacks one (12-OPS-019)"
priority: high
depends_on: []
source_reference: ".ai/plans/12-production-ops-remediation.md"
source_section: "BLOCK 1 - Healthcheck start_period on every service that lacks one"
source_blocks: ["BLOCK 1"]
description: >
  Four healthcheck blocks across three compose files declare interval, timeout and retries but
  no start_period, so a failing probe counts toward retries immediately. PostgreSQL 18 can be
  marked unhealthy during crash recovery and the depends_on chain fails to start. The four
  sites are docker-compose.yml db and redis, docker-compose.test.yml db, and
  docker-compose.prod.yml pgbouncer - the last of which no audit report named. docker-compose.yml
  is the base of all three stacks and docker-compose.test.yml is the file the test command
  reads, so this edit is felt by every phase in the programme.
goals:
  - "declare start_period on all four healthchecks"
  - "add a per-file guard that parses each compose file independently and fails when any healthcheck omits it"
  - "keep the fast gate green"
extra_context: |
  BINDING CONSTRAINTS
  1. These two files are written by no other block in this plan.
  2. Parse each compose file independently; never merge base + override. Register pass-through
     constructors for the !reset and !override tags, following test_compose_contract.py::_load_yaml.
  3. The guard must assert a parseable duration value, not the presence of the key.
  4. Run the Docker fast gate immediately after this block, before starting any other block.
  5. Do not change interval, timeout or retries.
  FORBIDDEN: editing docker-compose.prod.yml's scheduler healthcheck (phase 01 owns it);
  changing depends_on conditions; starting or stopping any compose stack beyond the test
  commands in section 1.1.
  EVIDENCE: render the test stack with "docker compose --project-name mko-bazuna-test
  --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml config --services"
  and confirm exit 0 before and after.
files:
  - path: docker-compose.yml
    targets:
      - type: service
        name: db
      - type: service
        name: redis
    semantic_anchors:
      insert_after:
        type: yaml_key
        value: "retries"
  - path: docker-compose.test.yml
    targets:
      - type: service
        name: db
    semantic_anchors:
      insert_after:
        type: yaml_key
        value: "retries"
  - path: docker-compose.prod.yml
    targets:
      - type: service
        name: pgbouncer
    semantic_anchors:
      insert_after:
        type: yaml_key
        value: "retries"
  - path: src/backend/tests/test_compose_contract.py
    targets:
      - type: function
        name: _load_yaml
    changes: []  # a NEW test module or a new test in this file; do not weaken existing assertions
changes:
  - action: add_code
    description: >
      Add a start_period key to each of the four healthcheck blocks, chosen from the service's
      recovery characteristics rather than copied from a neighbour.
  - action: add_code
    description: >
      Add a guard that walks every healthcheck block in every compose file it is pointed at,
      parses it with ruamel.yaml, and fails when start_period is absent or is not a parseable
      duration. The test must be able to fail - verify by temporarily removing one key.
acceptance_criteria:
  - "all four healthcheck blocks declare a start_period and each compose file still renders with config"
  - "the guard fails when a start_period is removed from any healthcheck, and that failure is demonstrated before the commit"
  - "the guard does not merge compose files with their overrides"
  - "the fast Docker gate is green"
  - "no interval, timeout, retries or depends_on value changed"
tests_to_run:
  - src/backend/tests/test_compose_contract.py
  - src/backend/tests/test_compose_hardening.py
  - src/backend/apps/core/tests/test_health_contract.py
```

---

### BLOCK 2 — The backup container: `user`, a dump-age healthcheck, and one prune convention (`OPS-014` + `OPS-021`'s loop limb)

| | |
|---|---|
| **Findings owned** | `OPS-014` (MEDIUM), `OPS-021` loop limb (LOW) |
| **Class** | **behavioural** — the container's runtime identity and cadence both change |
| **Depends on** | BLOCK 1 (both write `test_compose_contract.py`) |
| **Blocks** | BLOCK 9 and BLOCK 16 (both write `Makefile`); BLOCK 12 (the backup service is a candidate notification site) |
| **Priority** | **P0** — the strongest single catch in the report |
| **Risk level** | **HIGH** — the answer to Q4 may require a host-side directory-provisioning step |
| **Blast radius** | Prod-only compose plus `Makefile` / `Makefile.ps1`. **No base compose edit**, so the fast gate for other phases is unaffected — except that a new `docker/healthcheck-backup.sh` is a new file the image must ship |
| **Required agents** | **Auditor · Researcher · Planner · Validator** — all four; the Q4 probe is a runtime question |

**Decision required before implementation — Q4: is `user: postgres` on `backup` actually
writable, and does the fix need a directory-provisioning step?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | `user: postgres` only, and document that `./backups` must be writable by uid 70 before first deploy | **Gains:** the smallest possible compose change; one key, one file. **Costs:** if the host directory is owned by the invoking uid, the loop fails with a permission error on the first `pg_dump` and — because the service has **no healthcheck** until this same block adds one — the failure is silent. The `cap_drop`/`read_only` hardening already in place makes the container unable to fix its own problem |
| **(b)** | `user: postgres` **plus** a documented host-side provisioning step (create `./backups` owned by uid 70, or a numeric `user:` matching the host uid) | **Gains:** actually works on a fresh host. **Costs:** an operator procedure that lives outside compose and therefore outside any guard; it must be in `docs/ops/docker-deployment.md` and BLOCK 14 must sweep it |
| **(c)** | Keep root but **bound** it: add the healthcheck and the prune fix, and defer `user:` until the host ownership model is decided | **Gains:** no risk of breaking the daily dump. **Costs:** the root container holding `POSTGRES_PASSWORD` in its environment and writing to a host bind mount **remains**. That is the largest part of `OPS-014`'s stated impact |

**The Implementor may not choose.** BLOCK 2 runs the Q4 probe first (`id -u` in a throwaway
`run`, and a write test against a scratch `./backups` directory) and records the result.

**File surface (semantic units)**

| File | Service / target | Notes |
|---|---|---|
| `docker-compose.prod.yml` | `backup` — `user:`, `healthcheck:`, the `command:` loop's `pg_dump` filename, the `find … -name 'dump_*.dump'` prune | The four fixes, all inside one service block |
| `docker/healthcheck-backup.sh` | **new file** | Follows `docker/healthcheck-bot.sh` / `docker/healthcheck-scheduler.sh` exactly. **There is no precedent for a backup healthcheck** (C-8) — match the existing shape, do not invent one |
| `docker/Dockerfile` | the `chmod +x` step that already covers the two existing healthcheck scripts | The new script must be covered by it, in the **same commit** |
| `Makefile` | `prune-backups` target glob | Currently `dump_*.dump`, which never matches `deploy.yml`'s `backup-*.dump` |
| `Makefile.ps1` | `Invoke-PruneBackups`, `Invoke-Backup`, `Invoke-Clean` globs | Three more sites with the same mismatch. **A `Makefile`/PS1 parity test may already exist** — check `src/backend/tests/test_docs_ci_parity.py` before adding one |
| `.github/workflows/deploy.yml` | the pre-deploy `pg_dump` output filename | **Either** rename it to the loop's convention **or** widen the prune globs. Pick one and apply it at every site — a half-convention is worse than either |
| `src/backend/tests/test_compose_hardening.py` | `_HARDENING_KEYS`, `test_backup_hardened_in_prod` | **See the exception-list constraint below** |
| `src/backend/tests/test_compose_contract.py` | a new test module or a new test | The entrypoint-bypass detection needs real YAML, not `_service_block()` |

**Binding constraints**

1. **Do not add `user:` to `_HARDENING_KEYS`.** ✔ It is a module constant iterated by **twelve**
   service assertions — `web`, `bot`, `db`, `redis`, `scheduler`, `backup`, `pgbouncer`,
   `migrate`, `load_cities`, `load_catalog`, `create_admin`, `seed` (C-4). **`redis` is the only
   one that declares `user:` today**, so adding the key to the shared list turns the other
   **eleven** green assertions red for a key they must not have — including `db`, whose
   privilege drop is the image entrypoint's job.
   **Introduce a separate, per-service assertion with an explicit exception list**, and every
   entry in that list carries a one-line reason. An exception list with no reasons is how the
   next service silently opts out.
2. **The assertion is the absence of `user:`, not the running uid.** ✔ The report's root-cause
   derivation — that a `command:` override bypasses `postgres`'s entrypoint privilege drop — is
   structurally plausible and **was not observed at runtime** (C-3). The runtime `id -u` probe
   is Q4's evidence, not a test. A test that shells into a container is not a unit test.
3. **One filename convention, applied at every site.** There are four producers/pruners
   today: the compose loop (`dump_*.dump`), `deploy.yml` (`backup-*.dump`), `Makefile`
   (`dump_*.dump`), `Makefile.ps1` (`dump_*.dump` plus a `*.dump` clean). Naming only the
   prod loop and one Makefile target leaves the leak open.
4. **The healthcheck asserts freshness, not process liveness.** It must fail when the newest
   dump is older than the window. Do not assert that the container is running — `restart:
   unless-stopped` already covers that and Docker reports it.
5. **Drift compensation must not shorten the interval below one day.** The sleep is computed
   from the dump's own start time; the total must still be 24 h, and the loop must still sleep
   between runs (the report's test gap for `OPS-021`).
6. **Keep `cap_drop: ["ALL"]`, `read_only: true`, `tmpfs`, `no-new-privileges`, `mem_limit`
   and `cpus` byte-identical.** This block narrows the container's privileges; it does not
   relax them.
7. **Never read or print a value from `.env.prod`.** The Q4 probe uses key names and
   placeholder values only.

**Implementor task**

```yaml
id: task_12_b02_backup_service_hardening
title: "Harden the backup container and unify the dump prune convention (12-OPS-014, 12-OPS-021)"
priority: high
depends_on: [task_12_b01_healthcheck_start_period]
source_reference: ".ai/plans/12-production-ops-remediation.md"
source_section: "BLOCK 2 - The backup container: user, a dump-age healthcheck, and one prune convention"
source_blocks: ["BLOCK 2"]
description: >
  The prod backup service declares read_only, cap_drop ALL, tmpfs, no-new-privileges and limits
  but no user and no healthcheck, and overrides command with a shell loop. A root container
  holding POSTGRES_PASSWORD writes to a host bind mount, a job that has been failing for a week
  is indistinguishable from a healthy one, and deploy.yml writes backup-*.dump while three
  prune sites match only dump_*.dump, so deploy backups accumulate until the disk fills. The
  loop is pg_dump then sleep 86400, so the true interval exceeds 24h and nothing asserts that
  the newest dump is recent.
goals:
  - "declare user on the backup service per the recorded Q4 answer"
  - "add a healthcheck that fails when the newest dump is older than the freshness window"
  - "apply one dump filename convention across the loop, deploy.yml, the Makefile and Makefile.ps1"
  - "compensate the sleep so the cadence is 24h without shortening it"
  - "add a guard that does not extend the shared _HARDENING_KEYS constant"
extra_context: |
  DECISION GATE - Q4 MUST BE ANSWERED FIRST. Run the runtime probe (a throwaway
  "docker compose --env-file .env.prod ... run --rm --entrypoint /bin/sh backup -c \"id -u\""
  and a write test against a scratch ./backups directory), record the result, and select
  option (a), (b) or (c) from the block's decision table. The Implementor may not choose.

  BINDING CONSTRAINTS
  1. Do NOT add user: to _HARDENING_KEYS. It is a module constant iterated by twelve service
     assertions. Add a separate per-service assertion with an explicit, justified exception list.
  2. Assert the absence of user: and the presence of a healthcheck. Do NOT assert the running
     uid - that was never observed and a container-shelling test is not a unit test.
  3. One filename convention, applied at every producer AND pruner: the compose loop,
     deploy.yml, the Makefile and Makefile.ps1.
  4. The healthcheck asserts dump FRESHNESS, not process liveness.
  5. Drift compensation must keep the total at 24h.
  6. Keep cap_drop, read_only, tmpfs, no-new-privileges, mem_limit and cpus byte-identical.
  7. Never read or print a value from .env.prod.
  FORBIDDEN: touching docker-compose.yml or docker-compose.test.yml (BLOCK 1 owns them);
  touching the scheduler healthcheck (phase 01); adding a shell-lint dependency to the project;
  extending _ONE_SHOT_SERVICES.
files:
  - path: docker-compose.prod.yml
    targets:
      - type: service
        name: backup
  - path: docker/healthcheck-backup.sh
    targets:
      - type: file
        name: healthcheck-backup.sh
  - path: docker/Dockerfile
    targets:
      - type: build_stage
        name: runtime
  - path: Makefile
    targets:
      - type: make_target
        name: prune-backups
  - path: Makefile.ps1
    targets:
      - type: powershell_function
        name: Invoke-PruneBackups
      - type: powershell_function
        name: Invoke-Backup
      - type: powershell_function
        name: Invoke-Clean
  - path: .github/workflows/deploy.yml
    targets:
      - type: job
        name: deploy
  - path: src/backend/tests/test_compose_hardening.py
    targets:
      - type: module_constant
        name: _HARDENING_KEYS
  - path: src/backend/tests/test_compose_contract.py
    targets:
      - type: function
        name: _load_yaml
changes:
  - action: add_code
    description: >
      Add user: and healthcheck: to the backup service block, per the recorded Q4 option.
  - action: add_code
    description: >
      Create docker/healthcheck-backup.sh asserting the newest dump is newer than the freshness
      window, matching the shape of healthcheck-bot.sh and healthcheck-scheduler.sh.
  - action: add_code
    description: >
      Apply one dump filename convention at every producer and pruner.
  - action: add_code
    description: >
      Add a guard asserting that every prod service either declares user: or appears in an
      exception list WITH a reason, and that no service overrides command: in a way that
      bypasses the image entrypoint without declaring a user.
acceptance_criteria:
  - "the Q4 probe result and the selected option are recorded in the commit body"
  - "the backup service declares a user per the selected option, or the commit states why option (c) was taken"
  - "removing the healthcheck from the backup service turns the new guard red, and that failure is demonstrated"
  - "adding a service to the exception list without a reason turns the new guard red"
  - "no prune site misses the deploy filename, verified by listing a backup-*.dump fixture through each site"
  - "the loop's total cadence is 24h and it still sleeps between runs"
  - "_HARDENING_KEYS is byte-identical and all twelve existing assertions are green unchanged"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/tests/test_compose_hardening.py
  - src/backend/tests/test_compose_contract.py
  - src/backend/tests/test_docs_ci_parity.py
  - src/backend/tests/test_deploy_workflow.py
  - src/backend/apps/core/tests/test_deploy_workflow.py
```

---

### BLOCK 3 — Workflow wiring: one image coordinate, concurrency, and the stale ID citation (`OPS-009` + `OPS-016` + `OPS-021` comment limb)

| | |
|---|---|
| **Findings owned** | `OPS-009` (MEDIUM), `OPS-016` (MEDIUM), `OPS-021` comment limb (LOW) |
| **Class** | **mechanical** — workflow keys and literals, no behaviour change to the product |
| **Depends on** | BLOCK 2 (`deploy.yml`) |
| **Blocks** | BLOCK 10 (the constrained deploy input asserts on the coordinate this block fixes); BLOCK 4 and BLOCK 5 (`ci.yml` in-place edits, later) |
| **Priority** | P1 |
| **Risk level** | LOW |
| **Blast radius** | `ci.yml` and `deploy.yml`. **C-5 applies: no job may be appended after `deploy-check:`.** These are workflow files, so a mistake does not break the local fast gate — it is discovered on the next push |
| **Required agents** | **Auditor · Planner.** Researcher not required. No separate Validator (mechanical), but the guards must be shown to fire |

**Scope note on `OPS-021`.** ✔ The report's finding is that the `deploy-check` rationale
comment sits above `load-test:` instead of above `deploy-check:`. **That is already fixed** —
phase 02 moved it and extended it to name `test_deploy_check_env_parity.py` (C-12). The only
remaining defect is the comment's own header citing `OPS-001`, which in this phase is the
bandit finding. This block changes that citation and nothing else in the comment.

**File surface (semantic units)**

| File | Target | Notes |
|---|---|---|
| `.github/workflows/ci.yml` | `on:` | Add `pull_request`. **BLOCK 10 owns the assertion that this is sufficient; BLOCK 3 only adds the trigger** — actually, see the gate note below |
| `.github/workflows/ci.yml` | `jobs.build` — `outputs`, the push tag, `cache-from`, `cache-to` | Define the coordinate **once** as a job output and consume it at every use site |
| `.github/workflows/ci.yml` | top-level `concurrency:` | Follow the `ci-nightly.yml` shape |
| `.github/workflows/ci.yml` | the `deploy-check` job's leading comment header | The stale `OPS-001` citation only |
| `.github/workflows/deploy.yml` | top-level `concurrency:` | **`cancel-in-progress: false`. Never cancel a deploy mid-flight** |
| `.github/workflows/deploy.yml` | the coordinate the log and pull use | Consume the coordinate this block defines |

**Two coordinates, two behaviours — do not merge them by accident.**

| Workflow | Existing `concurrency` | Model |
|---|---|---|
| `ci-nightly.yml` | `group: nightly-seed-tests`, `cancel-in-progress: false` | Model for `deploy.yml` |
| `restore-test.yml` | `group: restore-test`, `cancel-in-progress: false` | Model for `deploy.yml` |
| `ci.yml` | **none** | Adding one is new; `cancel-in-progress: true` on `${{ github.ref }}` is what cancels a superseded push |
| `deploy.yml` | **none** | **Must be `cancel-in-progress: false`** — the opposite of CI, and this asymmetry is deliberate |

**Binding constraints**

1. **`cancel-in-progress: false` on `deploy.yml`.** Two concurrent deploys interleave `pull`
   and `up -d` against one host, and the health gate can validate a half-applied mix of images
   — and report green. That is the failure this block removes.
2. **`cancel-in-progress: true` on `ci.yml` is a branch-protection-adjacent change.** The
   report flags "verify branch-protection semantics after landing" as a test gap. A cancelled
   build must never be mistaken for a green one, and a required status check that never reports
   blocks a merge forever. State which behaviour was chosen and why in the commit body.
3. **Do not append a job to `ci.yml` after `deploy-check:`** (C-5). If a guard requires a new
   job, change `_deploy_check_section()` **in the same commit** and say why in the body.
4. **Do not change the `deploy-check` job's `env:` block.** ✔ Phase 02 owns it;
   `config/settings/tests/test_deploy_check_env_parity.py` proves `config.settings.prod` imports
   from it, with two negative controls. Any key a new `prod.py` guard needs is added by the
   block that adds the guard — BLOCK 6 does not add a guard, so it adds nothing here.
5. **One coordinate, defined once.** ✔ `cache-from` and `cache-to` disagree with **each
   other** today (`manicko/mko_bazuna` vs `manicko/mko-bazuna`) independently of the namespace
   split, which degrades every build to a cold cache. Fix both halves.
6. **The `deploy-check` comment keeps its second paragraph.** Phase 02's addition naming
   `test_deploy_check_env_parity.py` and forbidding `DJANGO_BUILD` / `DJANGO_ONESHOT` is live
   guidance. Change the header citation only.
7. **Guards assert behaviour, not tokens.** "every workflow declares a `concurrency` key" is a
   structural check with no string-level equivalent and is acceptable. "the coordinate literal
   appears" is **not** — assert that the workflow's own build outputs feed the deploy pull.

**Implementor task**

```yaml
id: task_12_b03_workflow_wiring
title: "Unify the image coordinate, add concurrency, fix the stale ID citation (12-OPS-009, 12-OPS-016, 12-OPS-021)"
priority: high
depends_on: [task_12_b02_backup_service_hardening]
source_reference: ".ai/plans/12-production-ops-remediation.md"
source_section: "BLOCK 3 - Workflow wiring"
source_blocks: ["BLOCK 3"]
description: >
  CI pushes to ghcr.io/mko-bazuna/mko_bazuna, caches to ghcr.io/manicko/mko-bazuna and caches
  FROM ghcr.io/manicko/mko_bazuna, while .env.prod.example names ghcr.io/manicko/mko_bazuna -
  three namespaces, and cache-from and cache-to disagree with each other, degrading every build
  to a cold cache. Neither ci.yml nor deploy.yml declares a concurrency group, so two push
  events race the shared buildcache reference and two manual deploys interleave pull and up -d
  against one production host. The deploy-check rationale comment header cites OPS-001, which
  in this phase is the bandit finding rather than the deploy-check gate.
goals:
  - "define the image coordinate once as a build job output and consume it at every use site"
  - "align cache-from with cache-to"
  - "declare concurrency on ci.yml and deploy.yml, with cancel-in-progress false on deploy"
  - "correct the stale OPS-001 citation in the deploy-check rationale comment header"
extra_context: |
  BINDING CONSTRAINTS
  1. cancel-in-progress: false on deploy.yml - never cancel a deploy mid-flight.
  2. cancel-in-progress on ci.yml is branch-protection adjacent; state the chosen value and the
     reason in the commit body, and confirm a cancelled build cannot be read as a green one.
  3. Do NOT append a job to ci.yml after the deploy-check key. test_ci_security.py's
     _deploy_check_section() slices from that marker to end-of-file, so any appended job breaks
     three shipped assertions. If a new job is genuinely required, change that helper in the
     SAME commit and say why.
  4. Do NOT modify the deploy-check job's env: block. Phase 02 owns it and
     test_deploy_check_env_parity.py proves the prod settings import from it.
  5. Keep the deploy-check comment's second paragraph (the one naming
     test_deploy_check_env_parity.py and forbidding DJANGO_BUILD / DJANGO_ONESHOT).
  6. Do NOT change the pull_request trigger scope; BLOCK 10 owns that decision.
  FORBIDDEN: editing docker-compose.yml or docker-compose.test.yml (BLOCK 1); adding a job
  after deploy-check:; touching the deploy workflow's health-gate step.
files:
  - path: .github/workflows/ci.yml
    targets:
      - type: workflow_job
        name: build
      - type: workflow_job
        name: deploy-check
  - path: .github/workflows/deploy.yml
    targets:
      - type: workflow_job
        name: deploy
  - path: src/backend/tests/test_deploy_workflow.py
    targets: []
  - path: src/backend/apps/core/tests/test_deploy_workflow.py
    targets: []
changes:
  - action: add_code
    description: >
      Add a build job output carrying the full image coordinate and replace every push, cache-from,
      cache-to and pull reference with that output.
  - action: add_code
    description: >
      Add a top-level concurrency key to ci.yml and to deploy.yml, with cancel-in-progress
      false on deploy.yml.
  - action: update_code
    description: >
      Correct the stale OPS-001 citation in the deploy-check rationale comment header to the
      finding the comment actually describes.
  - action: add_code
    description: >
      Add a guard asserting every workflow file declares a concurrency key, and a guard
      asserting cache-from and cache-to name the same reference.
acceptance_criteria:
  - "cache-from and cache-to name the same reference and neither names a namespace absent from the coordinate definition"
  - "every workflow file declares a concurrency key, verified by removing one and observing the guard fail"
  - "deploy.yml declares cancel-in-progress false"
  - "test_ci_security.py's three deploy-check assertions are green unchanged"
  - "the deploy-check env: block is byte-identical"
  - "the deploy-check comment still names test_deploy_check_env_parity.py"
tests_to_run:
  - src/backend/apps/core/tests/test_ci_security.py
  - src/backend/tests/test_deploy_workflow.py
  - src/backend/apps/core/tests/test_deploy_workflow.py
  - src/backend/config/settings/tests/test_deploy_check_env_parity.py
```

---

### BLOCK 4 — Make the SAST gate a contract, not a command (`OPS-001`)

| | |
|---|---|
| **Findings owned** | `OPS-001` (HIGH, ↓CRITICAL) |
| **Class** | **behavioural** — the first successful static analysis of this repository will surface findings |
| **Depends on** | BLOCK 3 (`ci.yml`); **BLOCK 14 must not start until this lands** |
| **Blocks** | BLOCK 14's SAST paragraph correction |
| **Priority** | **P0** — the report's constraint is "land the path fix and the triage, *then* correct the doc" |
| **Risk level** | **MEDIUM–HIGH** — the triage touches source files across five apps |
| **Blast radius** | `ci.yml`, `pyproject.toml`, and potentially ~20 source files carrying `# nosec` annotations. **No Python source file is affected behaviourally** — `# nosec` and `exclude_dirs` are non-semantic. The risk is a *red* `security` job, not a broken product |
| **Required agents** | **Auditor · Researcher · Planner · Validator** — all four; this is the phase's largest behavioural change and it modifies files other phases are editing |

**The baseline is rejected.** Do not create a `.bandit` baseline file. It would institutionalise
64 `B106` suppressions in test fixtures, **permanently permit new `B106` in production code**
(where a hardcoded credential is a real defect), freeze the `B311`/`B403` classes as
acceptable, and encode today's suppression decisions as untested truth. **Triage by class.**

**Verification required before the block relies on any number (C-2, `VAL-003`).** The
report's own runtime transcript was fabricated, so its finding counts are **untrusted**:

```text
# 1. Does the step really exit 2? (the CI form, CWD src/backend)
docker run --rm --entrypoint sh -v <repo>:/app -w /app/src/backend mko-bazuna-test-web:latest \
  -c "bandit -r src/backend src/telegram_bot -c pyproject.toml; echo EXIT=$?"
# 2. What does a correctly-invoked scan actually report? (CWD /app, same flags)
docker run --rm --entrypoint sh -v <repo>:/app -w /app mko-bazuna-test-web:latest \
  -c "bandit -q -r src/backend src/telegram_bot -c pyproject.toml"
```

Record the exact command, the image and the CWD next to the number in the commit body.

**The triage, by class, not by file**

| Class | Sites | Disposition |
|---|---|---|
| `B106` hardcoded password argument | 72 total, **64 in test fixtures** across 5 test files | `# nosec B106` with a one-line justification, on the fixtures only. **Review every `B106` in production code individually — that is where the class is a real defect** |
| `B703` / `B308` `mark_safe` | 5 sites (`apps/ads/templatetags/global_tags.py`, `apps/core/templatetags/telegram_tags.py`) | Individual review and fix. **An XSS-shaped finding is never silenced** |
| `B108` hardcoded `/tmp` | 5 sites (`config/settings/base.py` `BOT_LIVENESS_FILE`, `SCHEDULER_LIVENESS_FILE`) | Individual review and fix. **These two defaults are read by the healthcheck scripts phase 01 shipped — do not change the paths without re-reading them** |
| `B603` / `B404` subprocess | 25 informational | `# nosec` with rationale. The project already wraps `subprocess` for `manage.py` child dispatch |
| `B311` random | 4 sites | Deliberate decision: **seed generators only**. If any site is not a seed generator, that is a finding, not a suppression |
| `B403` pickle | 1 site (`apps/core/utils/swr_cache.py`) | Deliberate decision, recorded. **Do not rewrite the cache module in this block** |
| `B110` try/except/pass | 2 sites | Review; these may be real |

**Binding constraints**

1. **No baseline file.** Not `.bandit`, not a `--baseline` flag, not an exclusion list that
   swallows classes silently.
2. **Fix both path errors.** Either `working-directory: .` with
   `-r src/backend src/telegram_bot -c pyproject.toml`, or keep the CWD and target
   `apps config theme` plus `../../src/telegram_bot` with `-c ../../pyproject.toml`. **State
   which in the commit body** — the two have different failure modes when the repo layout moves.
3. **Repair `exclude_dirs` to the real test trees.** ✔ The current config misses
   `src/backend/config/settings/tests/` and `src/telegram_bot/tests/` entirely, and as an
   `fnmatch` pattern `**` collapses to `*` so it does not reliably match the nested `tests`
   directories either. **The exclusion config, not the rule set, is the main reason the backlog
   looks alarming.** Narrow the scope to test trees only — never exclude a production directory.
4. **Replace `test_ci_yml_has_sast_job` under project rule 2, and say so in the commit body.**
   ✔ `assert "bandit" in content or "semgrep" in content` cannot distinguish a working step from
   one that scans nothing. The replacement must assert a **non-zero scanned-file count** and
   that the **configured scan roots exist**. This is one of the two pre-authorised test
   rewrites in this plan.
5. **The new guard must be shown to fire.** Temporarily break a scan root, observe the failure,
   restore it. A guard never observed failing is not a guard (`VAL-003`).
6. **`pyproject.toml` is a shared file.** Re-read it immediately before editing; if another
   agent has uncommitted changes, **stop and report**.
7. **Do not suppress a Medium finding to make the job green without a written per-class
   decision.** Every `# nosec` carries a reason on the same line or the commit body.
8. **Bands the CI job to fail on the residual** only if the triage leaves nothing above the
   configured `level = "low"`. If residual findings remain, the commit body must state which
   class they belong to and why they are not yet triaged — a red `security` job is the honest
   state; a silently narrowed threshold is not.

**Implementor task**

```yaml
id: task_12_b04_sast_gate
title: "Make the SAST gate a contract, not a command (12-OPS-001)"
priority: high
depends_on: [task_12_b03_workflow_wiring]
source_reference: ".ai/plans/12-production-ops-remediation.md"
source_section: "BLOCK 4 - Make the SAST gate a contract, not a command"
source_blocks: ["BLOCK 4"]
description: >
  The only static-application-security-test step in the pipeline resolves its scan roots and its
  config path relative to src/backend, where neither exists, so bandit aborts with exit 2 and the
  security job is permanently red. No Python source file in the repository has ever been
  statically analysed. The exclusion config under-matches the real test trees, which is why the
  backlog looks alarming, and the guard that let this ship asserts only that the substring
  "bandit" appears - which cannot distinguish a working step from a no-op.
goals:
  - "make the bandit step execute against the whole repository"
  - "repair exclude_dirs to the real test trees and nowhere else"
  - "triage the residual by class with a written decision per class, never by baseline"
  - "replace the substring guard with a scanned-file-count assertion that is shown to fail"
extra_context: |
  EVIDENCE GATE. The source report's runtime transcript was fabricated and its finding counts are
  untrusted. Re-run both commands in the block header, from the shipped image, recording the exact
  command, the image and the working directory, and record the real counts in the commit body.

  BINDING CONSTRAINTS
  1. NO BASELINE FILE of any kind.
  2. Fix both path errors and state which invocation form was chosen and why.
  3. Narrow exclude_dirs to the real test trees only (including src/backend/config/settings/tests
     and src/telegram_bot/tests). Never exclude a production directory.
  4. Replacing test_ci_yml_has_sast_job invokes project rule 2 ("production code is king"). The
     commit body must name the rule and why. The replacement asserts a non-zero scanned-file
     count and that the configured scan roots exist.
  5. Demonstrate the new guard failing before committing.
  6. Re-read pyproject.toml immediately before editing; stop and report on a concurrent change.
  7. Every # nosec carries a reason. A Medium finding is never silenced without a written
     per-class decision.
  8. BOT_LIVENESS_FILE and SCHEDULER_LIVENESS_FILE in config/settings/base.py are read by the
     healthcheck scripts phase 01 shipped. Do not change those paths without re-reading them.
  FORBIDDEN: creating scripts/ops/ (phase 12 BLOCK 9 territory); adding a lint dependency;
  rewriting apps/core/utils/swr_cache.py; touching docker-compose.yml or docker-compose.test.yml.
files:
  - path: .github/workflows/ci.yml
    targets:
      - type: workflow_step
        name: "Run SAST (bandit)"
  - path: pyproject.toml
    targets:
      - type: toml_table
        name: tool.bandit
  - path: src/backend/apps/core/tests/test_ci_security.py
    targets:
      - type: function
        name: test_ci_yml_has_sast_job
changes:
  - action: add_code
    description: >
      Correct the step's working directory and its scan roots and config path so the scan executes.
  - action: update_code
    description: >
      Repair exclude_dirs to name the real test trees.
  - action: add_code
    description: >
      Triage the residual by class: per-site nosec with justification on test fixtures, individual
      review and fix for mark_safe and hardcoded /tmp, written decisions for random and pickle.
  - action: update_code
    description: >
      Replace test_ci_yml_has_sast_job with assertions on scanned-file count and on the existence
      of the configured scan roots.
acceptance_criteria:
  - "the bandit step exits 0 or exits 1 with findings, and never exits 2"
  - "the scanned-file count is non-zero and is recorded in the commit body with the exact command, image and working directory"
  - "the new guard fails when a scan root is broken, and that failure is demonstrated"
  - "no baseline file exists"
  - "every nosec annotation carries a reason"
  - "test_ci_security.py's other assertions are green unchanged"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/apps/core/tests/test_ci_security.py
```

---

### BLOCK 5 — Pin the pipeline's own supply chain (`OPS-017`)

| | |
|---|---|
| **Findings owned** | `OPS-017` (MEDIUM) |
| **Class** | **mechanical** — reference and checksum changes, no behaviour change |
| **Depends on** | BLOCK 4 (`ci.yml`, `deploy.yml`) |
| **Blocks** | nothing in-plan; BLOCK 14 documents the pinning convention |
| **Priority** | P1 |
| **Risk level** | LOW for the workflow pins · **MEDIUM for the `Dockerfile`** — a wrong checksum breaks every image build, including every other phase's |
| **Blast radius** | `.github/workflows/**` and `docker/Dockerfile`. **A wrong Dockerfile checksum breaks the build for every phase** |
| **Required agents** | **Auditor · Planner.** No separate Validator (mechanical), but every checksum must be verified against the upstream published value |

**File surface (semantic units)**

| File | Target | Notes |
|---|---|---|
| `.github/workflows/ci.yml` | every third-party `uses:` reference; the gitleaks fetch step | Pin to full commit SHAs with the version in a trailing comment |
| `.github/workflows/deploy.yml` | every third-party `uses:` reference | `appleboy/ssh-action` is the highest-consequence one — it receives the **production SSH private key** |
| `.github/workflows/restore-test.yml` | every third-party `uses:` reference | |
| `docker/Dockerfile` | the `syft` builder-stage install (`install.sh` from `main`) | **Not even a tag — a branch.** Pin to a released version with a verified checksum, or install from a pinned base image |
| `docker/Dockerfile` | the Tailwind CLI download (`releases/latest/download/...`) | **Not named by the report.** Same class, same treatment |
| `.github/dependabot.yml` | the `github-actions` ecosystem entry | ✔ Already weekly and grouped to `*` — verify the pinned SHAs are still picked up after the change |

**Binding constraints**

1. **Every pin carries the version in a trailing comment.** `uses: actions/checkout@<sha> # v4`.
   A pin without a version makes the next Dependabot bump unauditable.
2. **Verify every checksum against the upstream release's published checksum file**, and record
   the command in the commit body. A checksum copied from the same page that served the
   artefact verifies nothing.
3. **The `security` job holds `security-events: write` and a `GITHUB_TOKEN`.** The gitleaks
   fetch is the step that decides whether a secret enters the repository, and it currently
   runs an unverified tarball in a job with both. Replace it with a maintained action **or** a
   `sha256sum --check` against a checksum committed to the repository.
4. **Do not remove `.gitleaks.toml`** — `test_ci_security.py::test_gitleaks_config_exists`
   asserts it exists, and it is the configuration the pinned fetch needs.
5. **The `Dockerfile` change must not change what the SBOM contains.** `syft` output feeds the
   image; pinning the version may change the SBOM schema. If CI's SBOM assertion is
   version-sensitive, say so in the commit body rather than widening it.
6. **Dependabot must keep working.** After the change, confirm the `github-actions` ecosystem
   entry still matches the pinned-reference form it expects.
7. **Do not add `shellcheck` or any new lint tool.** This block verifies existing tooling.

**Implementor task**

```yaml
id: task_12_b05_supply_chain_pins
title: "Pin every third-party action and verified download (12-OPS-017)"
priority: medium
depends_on: [task_12_b04_sast_gate]
source_reference: ".ai/plans/12-production-ops-remediation.md"
source_section: "BLOCK 5 - Pin the pipeline's own supply chain"
source_blocks: ["BLOCK 5"]
description: >
  Every third-party action in the pipeline is referenced by a mutable tag, and the security job
  downloads the gitleaks binary with an unverified pipe-to-tar in a job holding
  security-events: write and a GITHUB_TOKEN. The image build installs syft from a branch of an
  install script with no verification, and downloads the Tailwind CLI from a latest-release
  path. Dependabot bumps the tags weekly, but a tag is a pointer, not a pin.
goals:
  - "pin every third-party action reference to a full commit SHA with the version in a comment"
  - "verify the gitleaks download against a committed checksum or replace it with a maintained action"
  - "pin and verify the syft and Tailwind downloads in the Dockerfile"
extra_context: |
  BINDING CONSTRAINTS
  1. Every pin carries the version in a trailing comment.
  2. Verify every checksum against the upstream release's published checksum file and record
     the command in the commit body.
  3. The security job holds security-events: write and a GITHUB_TOKEN.
  4. Do NOT remove .gitleaks.toml - test_ci_security.py asserts it exists.
  5. The Dockerfile change must not change what the SBOM contains; if CI's SBOM assertion is
     version-sensitive, say so rather than widening it.
  6. Confirm Dependabot's github-actions entry still matches the pinned-reference form.
  FORBIDDEN: adding shellcheck or any new lint dependency; touching docker-compose.yml or
  docker-compose.test.yml; changing the image's runtime contents.
files:
  - path: .github/workflows/ci.yml
    targets:
      - type: workflow_job
        name: security
  - path: .github/workflows/deploy.yml
    targets:
      - type: workflow_job
        name: deploy
  - path: .github/workflows/restore-test.yml
    targets:
      - type: workflow
        name: restore-test
  - path: docker/Dockerfile
    targets:
      - type: build_stage
        name: builder
  - path: .github/dependabot.yml
    targets:
      - type: toml_table
        name: github-actions
changes:
  - action: update_code
    description: >
      Replace every third-party uses: reference with a full commit SHA and a trailing version comment.
  - action: update_code
    description: >
      Replace the pipe-to-tar gitleaks fetch with a verified download or a maintained action.
  - action: update_code
    description: >
      Pin the syft install to a released version with a verified checksum, or install it from a
      pinned base image. Apply the same treatment to the Tailwind CLI download.
acceptance_criteria:
  - "no third-party uses: reference in any workflow is a mutable tag or branch"
  - "every pin carries its version in a trailing comment"
  - "every checksum was verified against the upstream published checksum file and the command is recorded"
  - "gitleaks.toml still exists and its test is green"
  - "the image still builds and still emits an SBOM"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/apps/core/tests/test_ci_security.py
```

---

### BLOCK 6 — A malformed `SENTRY_DSN` must not take production offline (`OPS-013`)

| | |
|---|---|
| **Findings owned** | `OPS-013` (MEDIUM) |
| **Class** | **mechanical** — a guard and a test row; no behaviour change on the happy path |
| **Depends on** | BLOCK 5 (in-plan order only; there is no file overlap with BLOCK 7) |
| **Blocks** | nothing in-plan |
| **Priority** | P1 |
| **Risk level** | **MEDIUM** — the diff is ~10 lines; the blast radius is every process importing `config.settings.prod` |
| **Blast radius** | `config/settings/prod.py` — a **phase-02-owned** file. Every process (`web`, `bot`, `migrate`, `load_cities`, `load_catalog`, `create_admin`, `seed`, `scheduler`) plus the CI `deploy-check` job plus the `Makefile restore-test` migrate step import this module |
| **Required agents** | **Auditor · Researcher · Planner · Validator.** The Researcher confirms the `sentry-sdk` version and the exception type |

**File surface (semantic units)**

| File | Target | Notes |
|---|---|---|
| `src/backend/config/settings/prod.py` | the Sentry initialisation block inside `if SENTRY_DSN and not DEBUG:` | ✔ Currently guarded only by `except ImportError` |
| `src/backend/config/settings/tests/test_prod_logging.py` | `_run_in_subprocess`, `_prod_env_overrides`, the existing Sentry rows | **The harness already exists** — a malformed-DSN row is a one-line addition |
| `src/backend/config/settings/tests/test_deploy_check_env_parity.py` | — | **Read-only.** ✔ It imports `_prod_env_overrides` from `test_prod_logging.py`. **Do not create a fifth copy of the harness** |

**Binding constraints**

1. **The log message names the variable, never the value**, mirroring
   `_validate_production_secret`'s value-free style and phase 02's assertion discipline. A
   message containing the DSN would put a credential into the log stream this very finding is
   about protecting.
2. **The guard must not mask a real import failure.** `except ImportError` exists because the
   dependency may be absent. A malformed DSN is a different condition and must be reported as
   such — one `logger.error` naming `SENTRY_DSN` and disabling error tracking, with the process
   continuing to boot. **`except Exception` around the whole block is not acceptable**: it would
   also swallow a genuine misconfiguration.
3. **Prefer validation over catching.** A shape check (`scheme`, `@`, project id) or
   `sentry_sdk.utils.BadDsn` handled explicitly is better than a broad catch. If the installed
   `sentry-sdk` exposes a stable exception type, use it; record the version in the commit body.
4. **✔ The report's trigger examples are wrong.** In `sentry-sdk 2.69.2` a leading space and a
   trailing newline are **handled**. The live trigger is an unrecognised or malformed scheme.
   The test must use a genuinely malformed DSN; a DSN with a trailing space would assert nothing.
5. **The new test uses the existing subprocess harness and the existing env override helper.**
   Never duplicate `_prod_env_overrides`.
6. **Run the whole `config/settings/tests` package, not a subset.** ✔ `test_deploy_check_env_parity.py`
   imports from `test_prod_logging.py`; a targeted run of one file can hide a broken import.
7. **`prod.py` is phase-02-owned.** Re-read it immediately before editing; if another agent has
   uncommitted changes, **stop and report**.
8. **This block adds no guard, therefore adds nothing to the `deploy-check` `env:` block**
   (see BLOCK 3 constraint 4). `SENTRY_DSN` is optional and empty by default.

**Implementor task**

```yaml
id: task_12_b06_sentry_dsn_guard
title: "Stop a malformed SENTRY_DSN from taking production offline (12-OPS-013)"
priority: high
depends_on: [task_12_b05_supply_chain_pins]
source_reference: ".ai/plans/12-production-ops-remediation.md"
source_section: "BLOCK 6 - A malformed SENTRY_DSN must not take production offline"
source_blocks: ["BLOCK 6"]
description: >
  config/settings/prod.py initialises Sentry inside "if SENTRY_DSN and not DEBUG" and guards only
  ImportError. sentry_sdk.init raises BadDsn for a malformed DSN and that exception escapes the
  settings-module import, so every process importing config.settings.prod - web, bot, migrate,
  load_cities, load_catalog, create_admin, seed, scheduler - fails at import and loops under
  restart: unless-stopped. An optional integration setting shipped empty by default can take the
  whole stack offline.
goals:
  - "make a malformed SENTRY_DSN leave the settings module importable and the process booting"
  - "log one value-free error naming the variable and disabling error tracking"
  - "cover the malformed case in the existing subprocess harness"
extra_context: |
  BINDING CONSTRAINTS
  1. The log message names the variable, never the value.
  2. Do not wrap the whole block in "except Exception" - it would swallow a genuine
     misconfiguration. Handle BadDsn explicitly or validate the shape before use.
  3. Prefer validation over a broad catch; record the installed sentry-sdk version in the
     commit body.
  4. The live trigger is an unrecognised or malformed SCHEME. A leading space and a trailing
     newline are handled by sentry-sdk 2.69.2, so a DSN with a trailing space asserts nothing.
  5. Reuse _run_in_subprocess and _prod_env_overrides from test_prod_logging.py. Never
     duplicate them; test_deploy_check_env_parity.py imports _prod_env_overrides from there.
  6. Run the whole config/settings/tests package, not a subset.
  7. Re-read prod.py immediately before editing; stop and report on a concurrent change.
  8. Do NOT add a guard, therefore do NOT touch the ci.yml deploy-check env: block.
  FORBIDDEN: changing SENTRY_DSN's default; making SENTRY_DSN mandatory in prod; editing
  config/settings/base.py; adding an env key.
files:
  - path: src/backend/config/settings/prod.py
    targets:
      - type: module_block
        name: Sentry initialisation
  - path: src/backend/config/settings/tests/test_prod_logging.py
    targets:
      - type: function
        name: _run_in_subprocess
      - type: function
        name: _prod_env_overrides
changes:
  - action: add_code
    description: >
      Validate the DSN before use, or handle BadDsn explicitly, and emit a single value-free
      logger.error naming SENTRY_DSN and disabling error tracking.
  - action: add_code
    description: >
      Add a malformed-DSN row to the existing subprocess harness asserting the import succeeds.
acceptance_criteria:
  - "a malformed SENTRY_DSN leaves config.settings.prod importable"
  - "the log message names SENTRY_DSN and contains no part of its value"
  - "the absent-DSN and valid-DSN rows remain green unchanged"
  - "no broad except was introduced around the settings block"
  - "the whole config/settings/tests package is green"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/config/settings/tests
```

---

### BLOCK 7 — PgBouncer authentication, and a capacity-limit contract that cannot ship silently (`OPS-015` + `VAL-001`)

| | |
|---|---|
| **Findings owned** | `OPS-015` (LOW), `VAL-001` (MEDIUM) |
| **Class** | **behavioural** — a real-YAML assertion over an env-allowlist surface another phase owns |
| **Depends on** | BLOCK 2 (`test_compose_contract.py`, `docker-compose.prod.yml`) |
| **Blocks** | BLOCK 13 (which also writes `docker-compose.prod.yml`'s `web` block) |
| **Priority** | P1 |
| **Risk level** | **MEDIUM** — the `VAL-001` half edits `config/settings/base.py`, a phase-02-owned file, and all four `.env.*.example` files |
| **Blast radius** | Prod compose (profile-gated service only), the env allowlist, the four example env files. **No base compose edit.** A mis-scoped `VAL-001` implementation turns `test_env_allowlist.py` red for every phase |
| **Required agents** | **Auditor · Researcher · Planner · Validator.** Researcher verifies the PG18 `password_encryption` default against a live `pg_authid` |

**Decision required before implementation — Q7: how far does `VAL-001` go?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Declare **every** `*_MEM_LIMIT` / `*_CPUS` key in `.env.prod.example` (and the three other example files), add them all to `ALLOWED_ENV_VARS`, and guard that each resolves | **Gains:** the compose defaults cannot ship unnoticed anywhere; an operator can tune every service. **Costs:** ~20 new keys × 4 files plus a ~20-entry addition to a file five other phases edit, each needing an allowlist entry and a doc line. That is a large diff against another phase's surface, and the values are **guesses** — this Planner cannot know the right limit for a host nobody has measured |
| **(b)** | Ship **only the guard**: assert that every `mem_limit:` / `cpus:` in the compose files is backed by an `${VAR:-default}` form, and that `.env.prod.example` declares at least the `db` limit, which `SRCH-001` depends on | **Gains:** the specific gap that has a demonstrated consequence (the cgroup OOM kill) is closed; the diff stays small; phase 02's allowlist gets a bounded addition. **Costs:** the other ~18 services keep shipping undeclared defaults, which is what the finding names |
| **(c)** | Ship **neither**; record `VAL-001` as an infrastructure decision owned by whoever sizes the host | **Gains:** no speculative capacity numbers committed to a repository. **Costs:** the finding stays open with no destination, and `SRCH-001`'s blast radius keeps its undeclared half |

**The Implementor may not choose.** `VAL-001` is a coverage gap the validator raised *against
the audit report*, and its remedy is partly an **infrastructure** decision that belongs to the
owner of the host. Option (b) is the Planner's recommendation and is stated as such, not as a
decision.

**File surface (semantic units)**

| File | Target | Notes |
|---|---|---|
| `docker-compose.prod.yml` | `pgbouncer` — `PGBOUNCER_AUTH_TYPE` | `md5` → `scram-sha-256`. ✔ PgBouncer ≥1.19 supports SCRAM verifiers in `auth_file`; the image is `edoburu/pgbouncer:1.25.2` |
| `docker-compose.prod.yml` | `web` — `BOT_HEALTH_STALE_SECONDS` counterpart | **BLOCK 13's**, not this block's. Read-only here |
| `src/backend/tests/test_compose_contract.py` | a new test | Real YAML, parsed per file with no merge. Assert the PgBouncer auth type matches the engine's `password_encryption` default |
| `config/settings/base.py` | `ALLOWED_ENV_VARS` | **Phase-02-owned.** Only under Q7 option (a) or the bounded (b) |
| `.env.prod.example`, `.env.dev.example`, `.env.test.example`, `.env.example` | new limit keys | Only under the chosen Q7 option. **`test_env_allowlist.py` reads in both directions** |
| `docs/99-agent/architecture.md` or `docs/ops/docker-deployment.md` | the capacity-limit inventory | BLOCK 14 owns the sweep; this block supplies the **content** |

**Binding constraints**

1. **Do not document the PgBouncer profile as available.** ✔ Zero `docs/ops` files mention it
   today, which is precisely why the latent misconfiguration stayed invisible. Documenting an
   unused profile is how it became invisible; leave it undocumented until someone intends to use it.
2. **`PGBOUNCER_AUTH_TYPE` is an env key that already exists** — it is **not** in
   `ALLOWED_ENV_VARS` today because it is read by the container's own entrypoint, not by
   Django. **Do not add it to the allowlist** unless a Django consumer is introduced. Verify
   this before editing `base.py`.
3. **The PgBouncer healthcheck does not exercise authentication** (`pg_isready` against the
   pooler port). ✔ That is why the defect is latent and why no existing test catches it. The
   new assertion is a **configuration** assertion, and it must be described as such — do not
   claim it proves PgBouncer can authenticate.
4. **`VAL-001` must not claim to close `SRCH-001`.** `SRCH-001` (phase 08) owns the OOM
   consequence of an unbounded `?features=` join. This block owns only "the ops layer declares
   no capacity limits and enforces no contract". **Cross-reference, do not merge.** Any commit
   body for this block must say which half it fixed.
5. **Every new env key is added to `ALLOWED_ENV_VARS` in the same commit** as the example-file
   entry, or `test_env_allowlist.py` fails.
6. **Re-read `config/settings/base.py` and all four `.env.*.example` files immediately before
   editing.** Phase 02 shipped the allowlist and other phases are still adding keys. If another
   agent has uncommitted changes here, **stop and report**.
7. **Every limit value is a default, not a measurement.** A value that has not been observed on
   a production host must be labelled as such in the example file's comment. Do not present a
   guess as a tuned value.

**Implementor task**

```yaml
id: task_12_b07_pgbouncer_and_mem_limits
title: "Fix PgBouncer auth and close the capacity-limit contract (12-OPS-015, VAL-001)"
priority: medium
depends_on: [task_12_b02_backup_service_hardening]
source_reference: ".ai/plans/12-production-ops-remediation.md"
source_section: "BLOCK 7 - PgBouncer authentication and a capacity-limit contract"
source_blocks: ["BLOCK 7"]
description: >
  The opt-in pgbouncer service sets PGBOUNCER_AUTH_TYPE=md5 against the same role whose
  password PostgreSQL 18 stores using the engine default, scram-sha-256, so the pooler cannot
  authenticate. Separately, every mem_limit and cpus value in all four compose files resolves
  through a ${VAR:-default} fallback and no limit key exists in any .env.*.example, so every
  environment ships the compose default and nothing declares or enforces a capacity contract.
goals:
  - "set the PgBouncer auth type to match the engine's password_encryption default"
  - "add a real-YAML assertion that the two stay in step"
  - "close the capacity-limit coverage gap per the recorded Q7 option, and state clearly that it does not close SRCH-001"
extra_context: |
  DECISION GATE - Q7 MUST BE ANSWERED FIRST. Select option (a), (b) or (c) from the block's
  decision table. The Implementor may not choose. Option (b) is the Planner's recommendation
  and is stated as a recommendation, not a decision.

  BINDING CONSTRAINTS
  1. Do NOT document the PgBouncer profile as available. Zero docs/ops files mention it today,
     which is why the latent misconfiguration stayed invisible.
  2. PGBOUNCER_AUTH_TYPE is read by the container entrypoint, not by Django. Do NOT add it to
     ALLOWED_ENV_VARS unless a Django consumer is introduced. Verify this first.
  3. The PgBouncer healthcheck is pg_isready, which does not exercise authentication. The new
     assertion is a configuration assertion and must be described as one.
  4. This block does NOT close SRCH-001. Cross-reference it; do not merge the findings, and say
     which half was fixed in the commit body.
  5. Every new env key is added to ALLOWED_ENV_VARS in the SAME commit as its example-file
     entry - test_env_allowlist.py reads in both directions.
  6. Re-read config/settings/base.py and all four .env.*.example files immediately before
     editing; stop and report on a concurrent change.
  7. Every limit value is a default, not a measurement. Label it as such.
  FORBIDDEN: touching docker-compose.yml or docker-compose.test.yml (BLOCK 1); editing the
  backup or scheduler service blocks (BLOCK 2 and phase 01); writing documentation (BLOCK 14).
files:
  - path: docker-compose.prod.yml
    targets:
      - type: service
        name: pgbouncer
  - path: src/backend/tests/test_compose_contract.py
    targets:
      - type: function
        name: _load_yaml
  - path: src/backend/config/settings/base.py
    targets:
      - type: module_constant
        name: ALLOWED_ENV_VARS
  - path: .env.prod.example
    targets: []
  - path: .env.dev.example
    targets: []
  - path: .env.test.example
    targets: []
  - path: .env.example
    targets: []
changes:
  - action: update_code
    description: >
      Set PGBOUNCER_AUTH_TYPE to scram-sha-256 in the pgbouncer service block.
  - action: add_code
    description: >
      Add a real-YAML assertion that the PgBouncer auth type matches the engine's
      password_encryption default, and that changing one without the other turns the test red.
  - action: add_code
    description: >
      Per the Q7 option, declare the capacity-limit keys and/or add the guard that the compose
      defaults cannot ship silently.
acceptance_criteria:
  - "PGBOUNCER_AUTH_TYPE matches the engine default, verified against a live pg_authid verifier prefix"
  - "changing the auth type alone turns the new assertion red, and that failure is demonstrated"
  - "test_env_allowlist.py is green and ALLOWED_ENV_VARS is a superset of every example key"
  - "the commit body states that SRCH-001 is not closed by this block"
  - "every declared limit value is labelled as an unmeasured default"
  - "the pgbouncer profile is still undocumented in docs/ops"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/tests/test_compose_contract.py
  - src/backend/config/settings/tests/test_env_allowlist.py
  - src/backend/tests/test_compose_hardening.py
```

---

### BLOCK 8 — Declare the production service set once (`OPS-007`, absorbing `OPS-005`)

| | |
|---|---|
| **Findings owned** | `OPS-007` (HIGH), `OPS-005` (merged into it) |
| **Class** | **structural** — introduces a contract or a source of truth |
| **Depends on** | BLOCK 3 (`deploy.yml`), BLOCK 7 (`docker-compose.prod.yml`) |
| **Blocks** | BLOCK 10 (the same deploy path), BLOCK 14 (the runbook correction references the contract) |
| **Priority** | **P0** — the report calls it the single highest-leverage change in the phase |
| **Risk level** | **HIGH** — it is the first deploy that will actually start `scheduler` and `backup` |
| **Blast radius** | `deploy.yml`, `docker-compose.prod.yml` (read), `docs/ops/rollback.md`, the contract file, three test modules. **No base compose edit.** The first production deploy that runs this is the first time the scheduler is recreated by the deploy path |
| **Required agents** | **Auditor · Researcher · Planner · Validator** — all four |

**Two consequences, one fix.** The report merges `OPS-005` into `OPS-007` because the two have
an identical root cause and an identical fix. Both consequences are preserved and both are
closed by this block:

- **Stale scheduler.** `scheduler` is `restart: unless-stopped`, runs hourly forever, and is
  `profiles: [scheduler]`. The deploy path names no profile, so it keeps running whatever
  image it started with — and after a detected-bad deploy the automated rollback restores
  `web` and `bot` while deliberately leaving the scheduler on the image just judged faulty,
  continuing to send buyer digests and execute the 30-day PII erasure under known-broken code.
- **No backup.** The same omission means the daily `backup` job is never started and never
  recreated on a fresh host, so the site can run for weeks with no dump.

**Decision required before implementation — Q1: where does the production long-lived service
set live?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | One committed contract file (a small YAML or a profile list) that `deploy.yml`, the runbook and the `Makefile` all read | **Gains:** the finding's structural half is closed — one expression, three consumers. Any future profile addition fails a guard instead of drifting. **Costs:** a **new committed artefact with no precedent in the tree** (a Makefile variable cannot be read by a workflow or a markdown file, and `Makefile`'s `COMPOSE_PROD` is defined and used by no target). A GitHub Actions workflow reading a repo file at deploy time is a new capability |
| **(b)** | **Three copies plus a regression guard** asserting they agree | **Gains:** zero new artefacts; the guard is the contract, and it fails on drift. **Costs:** three places to edit every time; the guard only catches divergence at test time, and the report's structural recommendation ("declare once") is not met. It is still strictly better than today |
| **(c)** | Wire `Makefile`'s existing, unused `COMPOSE_PROD` into a target that emits the service list, and have the workflow call `make` on the host | **Gains:** reuses something that exists; no new artefact. **Costs:** `make` is **not available on the production host** in the deploy path as written (the workflow runs `cd /app` and calls `docker compose` directly), and `docs/ops/rollback.md` still cannot read a Makefile. Does not solve the three-consumer problem |

**The Implementor may not choose.** BLOCK 8 is the phase's structural block; its answer is
recorded in the commit body and in §5.3 if it creates a new shared artefact.

**File surface (semantic units)**

| File | Target | Notes |
|---|---|---|
| `.github/workflows/deploy.yml` | **every** `docker compose` invocation: the pre-deploy `pg_dump`, the `pull`, the main `up -d`, and the rollback `up -d` | Add the profiles explicitly and name every long-lived service in both recreate commands |
| `docker-compose.prod.yml` | `scheduler`, `backup`, `pgbouncer` — their `profiles:` lists | **Read-only.** ✔ BLOCK 2 owns the `backup` block; BLOCK 7 owns `pgbouncer`. Re-read before relying on the current profile names |
| the contract file | — | **Only under Q1 option (a).** New artefact |
| `docs/ops/rollback.md` | the recreate commands; the note justifying `up -d web bot` | ✔ The note enumerates what is "not long-lived" and **omits `scheduler`**, which is `restart: unless-stopped` and runs hourly forever |
| `src/backend/tests/test_deploy_workflow.py` | — | The deploy-workflow guard |
| `src/backend/apps/core/tests/test_deploy_workflow.py` | — | **A second, thinner guard for the same file.** Both must be updated if the shape changes |
| `src/backend/tests/test_compose_hardening.py` | — | The prod long-lived service set assertion |

**Binding constraints**

1. **The guard is keyed on `restart:`, not on a hand-written list.** ✔ Every service with
   `restart:` set in `docker-compose.prod.yml` must be named in the deploy recreate command —
   and a service *added* to the prod manifest with a `restart:` and not named in the deploy
   path must turn the guard red. That is the assertion that catches the next profile.
2. **Profiles are explicit, never implicit.** `--profile scheduler --profile backup
   --profile pgbouncer` on every invocation. Relying on `up -d` with no service names does
   **not** activate a profile-gated service, which is the entire defect.
3. **Both recreate commands change.** The main deploy's `up -d --remove-orphans` and the
   rollback's `up -d --force-recreate --remove-orphans web bot` are not symmetric today. A
   rollback that leaves the scheduler on the faulty image is not a rollback.
4. **The `ENT-003` sequencing constraint is discharged.** ✔ Phase 01 shipped the durable daily
   marker and the `send_alerts` idempotency contract, so a post-08:00 scheduler restart does
   **not** re-send the daily set. This block may land without waiting for anything.
5. **Do not add a second dedupe mechanism to the scheduler.** Phase 01 owns it.
6. **Off-host backup replication is out of scope** (§6.1). This block makes the daily dump
   *start*; it does not make it survive a host loss. The commit body must say so, and BLOCK
   14's `restore.md` correction must mark the RPO as conditional on the backup job running.
7. **Nothing in this block observes whether the scheduler actually started.** ✔ The deploy
   health gate polls `web` only. That is the hidden dependency the report names: this block's
   **value is unverifiable** until BLOCK 12 lands. Record that in the commit body.
8. **`docs/ops/rollback.md` is edited here and again in BLOCK 14.** BLOCK 8 changes the
   recreate commands and the stale note; BLOCK 14 corrects the false claims. **Re-read before
   BLOCK 14.**

**Implementor task**

```yaml
id: task_12_b08_prod_service_set_contract
title: "Declare the production long-lived service set once (12-OPS-007, 12-OPS-005)"
priority: high
depends_on: [task_12_b03_workflow_wiring, task_12_b07_pgbouncer_and_mem_limits]
source_reference: ".ai/plans/12-production-ops-remediation.md"
source_section: "BLOCK 8 - Declare the production service set once"
source_blocks: ["BLOCK 8"]
description: >
  Three production services - scheduler, backup and pgbouncer - are gated behind compose
  profiles, and deploy.yml passes no --profile on any of its four compose calls. The automated
  rollback names only web and bot. So after a deploy the scheduler keeps running whatever image
  it started with, a rollback leaves it on the image just judged faulty, and the daily backup
  job is never started at all. The runbook repeats the gap as guidance.
goals:
  - "name every long-lived production service in every deploy compose invocation and in both recreate commands"
  - "declare the service set once, per the recorded Q1 option"
  - "add a regression guard keyed on restart: that fails when a new long-lived service is not named in the deploy path"
  - "correct the rollback runbook's justification note"
extra_context: |
  DECISION GATE - Q1 MUST BE ANSWERED FIRST. Select option (a), (b) or (c) from the block's
  decision table. The Implementor may not choose. If option (a) is selected, the new contract
  file is a SHARED ARTEFACT and must be reported to the coordinator so it can be reserved.

  BINDING CONSTRAINTS
  1. The guard is keyed on restart:, not on a hand-written list. Adding a restart:-carrying
     service to the prod manifest without naming it in the deploy path must turn the guard red.
  2. Profiles are explicit on every invocation: --profile scheduler --profile backup
     --profile pgbouncer. up -d with no service names does NOT activate a profile-gated service.
  3. BOTH recreate commands change - the main deploy and the automated rollback.
  4. Phase 01's ENT-003 is discharged; do not add a second dedupe mechanism to the scheduler.
  5. Off-host backup replication is out of scope. This block makes the daily dump START; it does
     not make it survive a host loss. Say so in the commit body.
  6. This block's value is UNVERIFIABLE until the operator-notification block lands, because
     nothing observes whether the scheduler started. Say so in the commit body.
  7. Re-read docs/ops/rollback.md immediately before editing - BLOCK 14 edits it later.
  FORBIDDEN: editing the backup service block (BLOCK 2) or the pgbouncer block (BLOCK 7);
  adding a compose file; touching docker-compose.yml or docker-compose.test.yml; adding a
  second scheduler dedupe mechanism.
files:
  - path: .github/workflows/deploy.yml
    targets:
      - type: workflow_job
        name: deploy
  - path: docker-compose.prod.yml
    targets:
      - type: service
        name: scheduler
      - type: service
        name: pgbouncer
  - path: docs/ops/rollback.md
    targets:
      - type: section
        name: "Image-Tag Rollback"
  - path: src/backend/tests/test_deploy_workflow.py
    targets: []
  - path: src/backend/apps/core/tests/test_deploy_workflow.py
    targets: []
  - path: src/backend/tests/test_compose_hardening.py
    targets: []
changes:
  - action: update_code
    description: >
      Add the explicit profile flags to every compose invocation in the deploy workflow and name
      every long-lived service in both recreate commands.
  - action: add_code
    description: >
      Per the Q1 option, declare the service set once and consume it from the deploy path and
      the runbook.
  - action: add_code
    description: >
      Add a guard asserting that every service with restart: set in the prod manifest is named
      in the deploy recreate command.
  - action: update_code
    description: >
      Correct the rollback runbook's justification note so it no longer omits scheduler from the
      list of services that are not long-lived.
acceptance_criteria:
  - "every deploy compose invocation carries the explicit profile flags"
  - "both recreate commands name every long-lived production service"
  - "adding a restart:-carrying service to the prod manifest without naming it in the deploy path turns the guard red, and that failure is demonstrated"
  - "the rollback runbook's note no longer omits scheduler"
  - "the Q1 option and its consequences are recorded in the commit body"
  - "the commit body states that the daily dump now starts but does not survive host loss, and that nothing yet observes whether the scheduler started"
  - "test_compose_contract.py's scheduler healthcheck assertions are green unchanged"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/tests/test_deploy_workflow.py
  - src/backend/apps/core/tests/test_deploy_workflow.py
  - src/backend/tests/test_compose_hardening.py
  - src/backend/tests/test_compose_contract.py
  - src/backend/apps/core/tests/test_health_contract.py
```

---

### BLOCK 9 — Make the disaster-recovery runbook executable on a production host (`OPS-006`)

| | |
|---|---|
| **Findings owned** | `OPS-006` (HIGH) |
| **Class** | **behavioural** — a runbook an engineer follows at 3 a.m. when data is already lost |
| **Depends on** | BLOCK 8 (`rollback.md`) |
| **Blocks** | BLOCK 14 (the docs sweep corrects the claims this block makes true) |
| **Priority** | **P0** |
| **Risk level** | **HIGH — irreversible-data surface.** ✔ `Makefile`'s `restore` target runs `pg_restore --clean --if-exists` against the **dev** stack, and `restore.md` points at it for a production restore |
| **Blast radius** | `docs/ops/restore.md`, `docs/ops/postgres-18-docker-volume-migration.md`, `docs/ops/migration-workflow.md`, `Makefile`, and possibly a new `scripts/ops/` directory. **No compose file edit.** The blast radius is *human*: an operator following the corrected document |
| **Required agents** | **Auditor · Researcher · Planner · Validator** — all four |

**Scope correction (C-10).** ✔ The report's universal quantifier is refuted:
`docs/ops/rollback.md`'s production invocations **already carry `--env-file .env.prod`** and
must **not** be "fixed". The defect is confined to `restore.md`, which is wholly
non-executable, plus the `postgres-18-docker-volume-migration.md` sweep the report ordered.

**Why every invocation aborts.** `docker-compose.yml` and `docker-compose.prod.yml` both use
mandatory interpolation (`${POSTGRES_USER:?…}`, `${DJANGO_SECRET_KEY:?…}`), so **any** compose
invocation without `--env-file` aborts during config rendering — including read-only `ps`,
`stop` and `exec`. On a production host the compose project directory holds `.env.prod`, not
`.env`, and the repository ships only `.env.*.example` (`.env` and `.env.*` are gitignored),
so compose finds no default env file either.

**Decision required before implementation — Q2: what happens to `Makefile`'s dev-stack
`restore` target?** (the irreversible-data question)

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Split into `restore` (dev, unchanged semantics) and a new `restore-prod` that uses `COMPOSE_PROD` | **Gains:** the runbook can name the correct target and the wrong one cannot be reached by accident. **Costs:** a new target in `Makefile` — and `Makefile.ps1` gains no equivalent, so a Windows operator has only the dev path. `test_docs_ci_parity.py` already enforces parity for one target; extending it is consistent |
| **(b)** | Keep one `restore` target that **refuses** to run without an explicit production opt-in | **Gains:** one target, one name, and the footgun is removed at the point of use. **Costs:** a refusal message an engineer reads at 3 a.m. is a second thing to understand; and a target that can restore into production is now reachable from the dev context |
| **(c)** | Document `restore` as dev-only and give `restore.md` a separate, self-contained production procedure | **Gains:** smallest diff; no new target. **Costs:** **the dev/prod confusion the finding is about remains** — an operator following the runbook still has a plausible wrong command one scroll away. This is the option the report does not choose and this Planner does not prefer |

**Decision required before implementation — Q3: what makes a runbook durable?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Extract the shell blocks into `scripts/ops/restore.sh` and `scripts/ops/rollback.sh` and have the markdown reference them | **Gains:** the structural fix — a broken command fails a lint step instead of an incident, and documentation drift on this surface becomes bounded. **Costs:** ✔ **no precedent in the tree** and **no shell-lint harness** (C-8). A new directory, two new scripts, a new CI job to lint them, and the markdown must be restructured to reference a script it no longer shows |
| **(b)** | A parity test asserting every production `docker compose` block in `docs/ops/*.md` carries `--env-file` and both `-f` files | **Gains:** checkable today, no new artefacts, and it **would have caught this on introduction**. **Costs:** string-level, and therefore inherits `VAL-003`'s weakness — it can tell you a flag is missing, not that the procedure works |
| **(c)** | Both | **Gains:** the structural fix and the cheap net. **Costs:** both costs above; the largest diff in the phase for a HIGH finding whose core is a missing flag |

**The Implementor may not choose either.** `VAL-003` says a token-presence guard cannot prove
a control works, and that is the tension Q3 exists to resolve.

**File surface (semantic units)**

| File | Target | Notes |
|---|---|---|
| `docs/ops/restore.md` | **every** `docker compose` invocation: the prerequisites line, the `--profile backup up -d`, `ps db`, `stop web bot`, both `pg_restore` blocks, `start web bot`, the connectivity check, `run --rm migrate` | Add `--env-file .env.prod` and both `-f` files to each |
| `docs/ops/restore.md` | the prerequisites line and the first two steps of the production procedure | ✔ Read `POSTGRES_USER` / `POSTGRES_DB` from `.env.prod`, **never `.env.dev`** (C-10) |
| `docs/ops/postgres-18-docker-volume-migration.md` | every `docker compose` invocation | ✔ Seven affected sites the report's file list did not name; the code context's sweep is wider than the report's |
| `docs/ops/migration-workflow.md` | ~10 flagless invocations | ✔ Dev-stack-scoped; decide whether they need `--env-file .env.dev` or are prose. **Do not add `.env.prod` here** |
| `Makefile` | the `restore` target; `COMPOSE_PROD` | Per Q2. `COMPOSE_PROD` is currently defined and used by **no** target |
| `Makefile.ps1` | — | Per Q2 option (a), and the `restore-test` question in §6.1 |
| `scripts/ops/*.sh` | — | **Only under Q3 option (a) or (c)** |
| `src/backend/tests/test_docs_ci_parity.py` | — | ✔ Covers `ci.yml`, `ci-nightly.yml`, `pyproject.toml`, `entrypoint-test.sh`, `Makefile`, `Makefile.ps1` — **not** `docs/ops/` |

**Binding constraints**

1. **`docs/ops/rollback.md`'s production invocations are correct and stay byte-identical.**
   Changing them "for consistency" would be a regression in review quality and would obscure
   the real defect.
2. **`.env.dev` never appears in a production procedure again.** This is a dev/prod
   **credential-source** confusion, not a missing flag: the values it yields are the
   development database's.
3. **Both `-f` files are required in every production invocation**, not just `--env-file`.
   ✔ A prod invocation that omits `docker-compose.prod.yml` silently runs the **dev**
   configuration, which is a quieter failure than the interpolation abort.
4. **The procedure must be executable as written.** After the edit, each command must be
   runnable in sequence against a production-shaped host. Use a scratch env file with
   placeholder values to validate; **never** read or print a value from `.env.prod`.
5. **The RPO and RTO statements in `restore.md` become conditional.** They are stated as
   facts while three of their preconditions (backup job running, off-host copy, real restore
   drill) are unmet. Marking them conditional costs one sentence and removes a whole class of
   false confidence — and it is the honest statement of what BLOCK 8 achieved.
6. **`docker-compose.yml` and `docker-compose.test.yml` are not edited by this block.**
7. **The `bazuna_db` sub-claim must not be reintroduced.** ✔ `.env.prod.example` **is**
   `POSTGRES_DB=bazuna_db` and `restore.md` names it correctly; the defect was the credential
   *source*, which is already fixed above.
8. **If Q3 option (a) is taken, the scripts must be `chmod +x`, must be verified with
   `sh -n`, and must be asserted executable by a test** — matching the two existing
   healthcheck scripts. There is no shell linter; do not add one.

**Implementor task**

```yaml
id: task_12_b09_runbook_executability
title: "Make the DR runbook executable on a production host (12-OPS-006)"
priority: high
depends_on: [task_12_b08_prod_service_set_contract]
source_reference: ".ai/plans/12-production-ops-remediation.md"
source_section: "BLOCK 9 - Make the disaster-recovery runbook executable"
source_blocks: ["BLOCK 9"]
description: >
  Every docker compose invocation in docs/ops/restore.md omits --env-file .env.prod and omits
  the prod override file, so each aborts during config rendering with "required variable
  POSTGRES_USER is missing a value" - including read-only ps, stop and exec, and including
  both pg_restore blocks that are the production restore path itself. The prerequisites and the
  first two production steps additionally read POSTGRES_USER and POSTGRES_DB out of .env.dev,
  yielding the development database's credentials. Separately, Makefile's restore target is a
  dev-stack target that restore.md points at for a production restore.
goals:
  - "make every production docker compose invocation in restore.md executable as written"
  - "stop the production procedure from reading credentials from .env.dev"
  - "close the dev/prod confusion around Makefile's restore target"
  - "sweep postgres-18-docker-volume-migration.md and decide migration-workflow.md"
  - "make the RPO and RTO statements conditional on their stated preconditions"
extra_context: |
  DECISION GATES - Q2 AND Q3 MUST BOTH BE ANSWERED FIRST. The Implementor may not choose either
  option. Q2 is the irreversible-data question: Makefile's restore target runs
  "docker compose ... exec -T db pg_restore --clean --if-exists" against the DEV stack, and
  restore.md points at it for a production restore.

  BINDING CONSTRAINTS
  1. docs/ops/rollback.md's production invocations already carry --env-file .env.prod. Leave
     them byte-identical. Changing them for consistency is a review regression.
  2. .env.dev never appears in a production procedure again.
  3. BOTH -f files are required in every production invocation. Omitting docker-compose.prod.yml
     silently runs the dev configuration, which is quieter than the interpolation abort.
  4. Validate the procedure against a scratch env file with placeholder values. Never read or
     print a value from .env.prod - key names only.
  5. The RPO and RTO statements become conditional on their preconditions.
  6. Do NOT edit docker-compose.yml or docker-compose.test.yml (BLOCK 1 owns them).
  7. Do NOT reintroduce the refuted bazuna_db sub-claim. .env.prod.example IS
     POSTGRES_DB=bazuna_db; the defect was the credential SOURCE.
  8. If Q3 option (a) or (c) is taken, the scripts are chmod +x, verified with sh -n, and
     asserted executable by a test. There is no shell linter; do not add one.
  FORBIDDEN: editing the compose files; rewriting migration-workflow.md wholesale; adding a
  shell-lint dependency; deleting the self-generated restore-test path (BLOCK 16 owns it).
files:
  - path: docs/ops/restore.md
    targets:
      - type: markdown_section
        name: "Prerequisites"
      - type: markdown_section
        name: "Restore Procedure"
  - path: docs/ops/postgres-18-docker-volume-migration.md
    targets: []
  - path: docs/ops/migration-workflow.md
    targets: []
  - path: Makefile
    targets:
      - type: make_target
        name: restore
      - type: make_variable
        name: COMPOSE_PROD
  - path: Makefile.ps1
    targets: []
  - path: src/backend/tests/test_docs_ci_parity.py
    targets: []
changes:
  - action: update_code
    description: >
      Add --env-file .env.prod and both -f files to every production docker compose invocation in
      restore.md, and change the credential source from .env.dev to .env.prod.
  - action: update_code
    description: >
      Sweep postgres-18-docker-volume-migration.md; decide migration-workflow.md per its dev scope.
  - action: update_code
    description: >
      Per Q2, close the dev/prod confusion around the restore target.
  - action: update_code
    description: >
      Mark the RPO and RTO statements as conditional on the backup job running, an off-host copy
      existing, and a real restore drill.
  - action: add_code
    description: >
      Per Q3, add a guard that every production docker compose block in docs/ops carries the
      required flags. It must be shown to fail.
acceptance_criteria:
  - "every production docker compose invocation in restore.md carries --env-file .env.prod and both -f files"
  - ".env.dev appears nowhere in a production procedure"
  - "docs/ops/rollback.md's production invocations are byte-identical to their pre-block state"
  - "the Q2 and Q3 options and their consequences are recorded in the commit body"
  - "the new guard fails when a flag is removed from any documented production invocation, and that failure is demonstrated"
  - "the RPO and RTO statements are conditional"
  - "no bazuna_db sub-claim was reintroduced"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/tests/test_docs_ci_parity.py
  - src/backend/tests/test_compose_contract.py
```

---

### BLOCK 10 — Deploy provenance: a green build, and a rollback target that is an identity (`OPS-002` + `OPS-008`)

| | |
|---|---|
| **Findings owned** | `OPS-002` (HIGH), `OPS-008` (MEDIUM) |
| **Class** | **behavioural** — the deploy path's contract changes |
| **Depends on** | BLOCK 8 (the same deploy file and the same service set), BLOCK 9 |
| **Blocks** | BLOCK 16 (the restore drill pins a recorded image tag; the recording mechanism is this block's) |
| **Priority** | **P0** — the report calls fixing `OPS-002` with `CFG-002` "the highest-leverage pair in this phase", and `CFG-002` is **already shipped** |
| **Risk level** | **HIGH** — this block changes how production is deployed. A mistake stops deploys; it does not corrupt data |
| **Blast radius** | `ci.yml`, `deploy.yml`, `.env.prod.example`, three test modules. **No compose file edit** |
| **Required agents** | **Auditor · Researcher · Planner · Validator** — all four |

**The precondition is discharged.** ✔ Phase 02 shipped `ci.yml`'s `deploy-check` env block and
`test_deploy_check_env_parity.py`, so the automated prod-config gate **actually executes**
today. The report's "land `CFG-002` before `OPS-002`" constraint is satisfied. What remains
is the residual gap this block states honestly: `deploy-check` runs on `push`, so it is a
**post-merge** gate, not a pre-merge one.

**Two mechanisms, one unit.** The report's own framing: *"a deploy must be derived from a green
CI run for a specific immutable artefact, not from a free-text input plus a human checkbox"*.
`registry/repository@sha256` is the deploy unit; the tag is a label on it.

**Decision required before implementation — Q11: what is the deploy gate mechanism?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Assert in-workflow that the dispatched SHA is on `main` and has a successful `CI` run for that SHA, before the SSH step | **Gains:** the control lives in the repository and is reviewable; the human approval stays. **Costs:** the assertion needs a token with enough scope to read workflow runs and check statuses; if the scope is wrong the gate fails closed and deploys stop. Also adds a `pull_request` trigger whose **pre-existing** failures surface immediately |
| **(b)** | A `workflow_run` trigger chained to `CI`, removing the manual dispatch entirely | **Gains:** a deploy cannot happen without a CI run, structurally. **Costs:** removes the human approval that currently exists, auto-deploys on every green `main` push, and turns any `pull_request`-triggered breakage into a deploy blocker. A significant change to how the team ships |
| **(c)** | Repository branch protection as the enforcement point plus a constrained input | **Gains:** the smallest workflow diff. **Costs:** moves the control **outside the repository**, where this plan cannot verify it and no test can guard it. `branch protection` is also not expressible in a compose or YAML contract this plan owns |

**Decision required before implementation — Q12: what replaces the tag-based capture?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Capture the running image's digest (`docker inspect --format='{{index .Image}}' "$(docker compose ps -q web)"`) before the pull; roll back by `image@sha256:…`; record both tag and digest in the deploy log | **Gains:** tags stop being identity. **Costs:** ✔ the `docker inspect` form appears **nowhere** in this repository and is untested here (verification item 6 in §0.2.3); `restore-test.yml` also pulls by tag, so a second change is needed there (BLOCK 16). A digest not present in the registry is a new failure branch that needs its own message and its own test |
| **(b)** | Require `IMAGE_TAG` to be a SHA in `.env.prod` and forbid `latest` in the prod template | **Gains:** one line in the template plus one guard. **Costs:** does not survive a **retagged or force-pushed** tag, which is a real exposure the report names; and it depends on an operator maintaining a SHA in a file compose reads |
| **(c)** | Both | **Gains:** identity is recorded, and the mutable default cannot ship. **Costs:** both. This is the report's recommendation and this Planner's recommendation |

**File surface (semantic units)**

| File | Target | Notes |
|---|---|---|
| `.github/workflows/ci.yml` | `on:` — add `pull_request` | ✔ Currently `push: branches: [main, develop]` only. **Expect pre-existing failures to surface**; the fast local gate is `.\Makefile.ps1 test`, not CI |
| `.github/workflows/deploy.yml` | the `workflow_dispatch` `image_tag` input; the `set_tag` step; the `PREVIOUS_IMAGE_TAG` capture; the health-gate and rollback branches | Per Q11 and Q12 |
| `.env.prod.example` | `IMAGE_TAG=latest` | ✔ Confirmed at line 83. Forbid the mutable default |
| `src/backend/tests/test_deploy_workflow.py` | — | ✔ Both modules assert only that `PREVIOUS_IMAGE_TAG` / `--force-recreate` strings are present. **Neither covers the no-previous-tag or digest-absent branches** |
| `src/backend/apps/core/tests/test_deploy_workflow.py` | — | **The second, thinner guard.** Both must be updated if the shape changes |

**Binding constraints**

1. **`pull_request` will surface pre-existing failures.** That is the point of the change, not
   a regression in it. If the workflow turns red on the first PR, **the fix is the failing
   check, not the removal of the trigger**. Record what surfaced in the commit body — the
   information is worth keeping even if the block does not fix it.
2. **Digest capture must be tested in a scratch project, not asserted.** ✔ `docker inspect`
   against `docker compose ps -q web` has never been run in this repository. The no-digest and
   digest-absent-from-registry branches must have **their own messages**, not a generic failure.
3. **The `PREVIOUS_IMAGE_TAG` capture is timing-sensitive.** ✔ It must be captured while the
   old containers still run — before `pull` and before `up`. Moving it after `up` captures
   the image being deployed, which makes the rollback reproduce the failing image.
4. **Do not remove the manual environment approval** unless Q11 option (b) is selected, and
   say so explicitly in the commit body. Removing a human gate without recording it is the
   most dangerous outcome this block can produce.
5. **`.env.prod.example` must not ship `IMAGE_TAG=latest`** under Q12 option (b) or (c), and
   the guard must be **shown to fail** when the default is `latest`.
6. **`deploy.yml`'s compose invocations must keep BLOCK 8's profiles and service set.**
   This block edits the same commands; it must not drop what BLOCK 8 added.
7. **Never read or print a value from `.env.prod`.**
8. **Both `test_deploy_workflow.py` modules must be updated in the same commit.** ✔ One is in
   `src/backend/tests/` and one in `src/backend/apps/core/tests/`; they are duplicates for the
   same file and a shape change breaks the one you forgot.

**Implementor task**

```yaml
id: task_12_b10_deploy_provenance
title: "Derive the deploy from a green CI run and roll back by digest (12-OPS-002, 12-OPS-008)"
priority: high
depends_on: [task_12_b08_prod_service_set_contract, task_12_b09_runbook_executability]
source_reference: ".ai/plans/12-production-ops-remediation.md"
source_section: "BLOCK 10 - Deploy provenance"
source_blocks: ["BLOCK 10"]
description: >
  deploy.yml triggers only on workflow_dispatch with a free-text image_tag input defaulting to
  the current SHA, declares no dependency on any CI job, and has no required status check on the
  production environment; ci.yml triggers only on push to main and develop, so no pull request is
  gated at all. The automated rollback derives its target by reading the tag string currently
  attached to the web container, and no digest is captured anywhere - tags are mutable labels,
  not identity. Phase 02 already shipped the deploy-check gate, so the config precondition is
  satisfied; the residual gap is that it is a post-merge gate.
goals:
  - "add a pull_request trigger so every change is gated before merge"
  - "constrain the dispatched SHA per the recorded Q11 option"
  - "capture and roll back by digest per the recorded Q12 option"
  - "forbid IMAGE_TAG=latest in the production template"
  - "cover the no-digest and digest-absent-from-registry branches"
extra_context: |
  DECISION GATES - Q11 AND Q12 MUST BOTH BE ANSWERED FIRST. The Implementor may not choose either.
  Q11 is an owner decision about how the team ships. Q12 is a Planner decision about what
  replaces tag identity; option (c) is the recommendation.

  BINDING CONSTRAINTS
  1. pull_request will surface pre-existing failures. That is the point. If the workflow turns
     red on the first PR, fix the failing check - do not remove the trigger. Record what
     surfaced in the commit body.
  2. Digest capture is UNTESTED in this repository. docker inspect --format on a compose service
     appears nowhere in the tree. Test it in a scratch project before relying on it, and give the
     no-digest and digest-absent branches their own messages rather than a generic failure.
  3. The previous-image capture must happen while the old containers still run - before pull and
     before up. Capturing after up captures the image being deployed.
  4. Do NOT remove the manual environment approval unless Q11 option (b) is selected, and say so
     explicitly in the commit body.
  5. The guard forbidding IMAGE_TAG=latest must be shown to fail.
  6. Preserve BLOCK 8's profiles and service set in every deploy compose invocation.
  7. Never read or print a value from .env.prod.
  8. BOTH test_deploy_workflow.py modules - src/backend/tests/ and src/backend/apps/core/tests/ -
     are updated in the same commit. They are duplicates for the same file.
  FORBIDDEN: appending a job to ci.yml after deploy-check: (test_ci_security.py slices from that
  marker to EOF); removing the deploy-check env: block (phase 02 owns it); editing the compose
  files; editing docker-compose.prod.yml.
files:
  - path: .github/workflows/ci.yml
    targets:
      - type: workflow_trigger
        name: on
  - path: .github/workflows/deploy.yml
    targets:
      - type: workflow_trigger
        name: workflow_dispatch
      - type: workflow_step
        name: "Capture previous image"
  - path: .env.prod.example
    targets:
      - type: env_key
        name: IMAGE_TAG
  - path: src/backend/tests/test_deploy_workflow.py
    targets: []
  - path: src/backend/apps/core/tests/test_deploy_workflow.py
    targets: []
changes:
  - action: add_code
    description: >
      Add a pull_request trigger to ci.yml.
  - action: update_code
    description: >
      Constrain the dispatched SHA per Q11 and capture the running image digest per Q12, recording
      both tag and digest in the deploy log.
  - action: update_code
    description: >
      Give the no-digest and digest-absent-from-registry branches their own messages.
  - action: update_code
    description: >
      Remove the mutable default from the production template and add a guard that fails when it
      reappears.
  - action: add_code
    description: >
      Add tests for the two untested rollback branches.
acceptance_criteria:
  - "ci.yml declares a pull_request trigger"
  - "the dispatched SHA is constrained per the recorded Q11 option and the option is named in the commit body"
  - "the previous image is captured before pull and before up, and the capture is digest-based per the recorded Q12 option"
  - "the /health/ready/ deploy gate step is byte-identical; OPS-020's exposure is BLOCK 18's and is not touched here"
  - "the no-digest and digest-absent branches each have a distinct message and a test"
  - "IMAGE_TAG=latest does not ship in the production template, and the guard is shown to fail when it does"
  - "BLOCK 8's profile flags and service set are still present in every deploy compose invocation"
  - "test_ci_security.py's three deploy-check assertions are green unchanged"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/tests/test_deploy_workflow.py
  - src/backend/apps/core/tests/test_deploy_workflow.py
  - src/backend/apps/core/tests/test_ci_security.py
  - src/backend/config/settings/tests/test_deploy_check_env_parity.py
```

---

### BLOCK 11 — Make the alert file a verified contract, or stop it reading as one (`OPS-003`)

| | |
|---|---|
| **Findings owned** | `OPS-003` (HIGH) |
| **Class** | **behavioural** — the rules file and the doc sweep both change |
| **Depends on** | BLOCK 10 (nothing functional; it runs after so the phase's highest-coordination block is not waiting) |
| **Blocks** | BLOCK 12 (the operator-notification floor is the detection path for whatever Q5 decides); BLOCK 14 |
| **Priority** | **P0** |
| **Risk level** | **MEDIUM for the unconditional half, HIGH under Q5 option (a)** — a new compose service, a new configuration file and a new secret surface |
| **Blast radius** | `docs/ops/prometheus-slo-alerts.yaml`, `apps/core/tests/test_observability.py`, `config/settings/base.py` (only under Q5 option (a)), and `docker-compose.prod.yml` (only under (a)). **Base compose is never edited.** Under Q5 option (a) a **new prod service** is introduced, which is the largest structural change in the phase |
| **Required agents** | **Auditor · Researcher · Planner · Validator** — all four |

**Two limbs, only one of which is unconditional.**

- **Unconditional:** the selectors name series that do not exist; the stale multiprocess caveat
  is now wrong; `AD-008`'s warning must be carried forward; a scrape-contract test must exist.
- **Gated (Q5):** whether a monitoring stack is deployed at all.

**Verification required first (C-9).** ✔ The alert file's selectors are confirmed verbatim in
the tree. The claim that `django-prometheus 2.5.0` emits no
`django_http_response_duration_seconds` family was **derived from library source, not from a
scrape**. The scrape-contract test reads a rendered `/metrics` — which is both the test and
the verification.

**Decision required before implementation — Q5: deploy a monitoring stack, or retire the SLO
artefacts?** The report states plainly: *"this is a decision, not a task."*

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Deploy `prometheus` with a `prometheus.yml` whose `rule_files` include this file, and move the rules out of the Kubernetes-only `PrometheusRule` CRD form or document the prerequisite | **Gains:** the alerts become real and the SLOs become measurable. **Costs:** a **new long-lived service** in `docker-compose.prod.yml` — which BLOCK 8's service-set guard will then require to be named in the deploy path, a direct coupling between two gates. A new configuration file, a new persistent-volume or tmpfs decision, and a secret surface if remote-write is added. **An order of magnitude larger than the finding's "minimum viable path"** |
| **(b)** | **Retire** `docs/ops/prometheus-slo-alerts.yaml` and `docs/ops/grafana-slo-dashboard.json`, or move them under a clearly-labelled "planned — not deployed" heading | **Gains:** the docs stop reading as active controls, which is exactly `OPS-011`'s second half and `OPS-018`'s Prometheus instance. **Costs:** the SLO thresholds in `src/benchmark/constants.py::PerformanceSLO` lose their operational expression, and the alert **definitions** are lost — they were written deliberately, if against the wrong API surface |
| **(c)** | **Minimum viable:** correct the selectors against the real series (or set `PROMETHEUS_LATENCY_BUCKETS` to include a `2.0` edge so the existing `le="2.000"` resolves), add the scrape-contract test, correct the stale caveat, and **defer the stack** | **Gains:** the durable half ships either way — a hand-maintained PromQL file becomes a **verified contract** that cannot drift into a dead selector again — and the file remains ready to deploy. **Costs:** no alert fires until someone deploys a stack, so the *detection* half of `OPS-011` is still unmet and BLOCK 12 must say so |

**The Implementor may not choose.** Q5 is an infrastructure decision the owner makes. The
Planner's recommendation is **(c) then (a) later**, because (c) ships the guard that makes (a)
safe and costs nothing if (a) never happens.

**Carry forward (`AD-008`, phase 05).** `get_pending_queue_size()` is structurally 0 because
`ON_MODERATION` is never committed. **A naive `pending_moderation` alert is dead on arrival.**
If Q5 option (a) is taken, that warning must travel with it into the rules file.

**File surface (semantic units)**

| File | Target | Notes |
|---|---|---|
| `docs/ops/prometheus-slo-alerts.yaml` | the three rules' `expr` selectors; the header comment's stale multiprocess caveat; the `le=` bucket edge | ✔ Confirmed at the current content |
| `src/backend/apps/core/tests/test_observability.py` | beside `test_metrics_endpoint` | **The one behavioural precedent in the repository** — render `/metrics` through the Django test client and assert the exposition. **Model this guard on it** |
| `config/settings/base.py` | `PROMETHEUS_LATENCY_BUCKETS` | **Only** if Q5 chooses the bucket-edge remedy. It does not exist today; adding it is a new `ALLOWED_ENV_VARS` entry plus example-file entries in the same commit |
| `docker-compose.prod.yml` | a new `prometheus` service | **Only under Q5 option (a)** |
| `docs/ops/grafana-slo-dashboard.json` | — | Only under Q5 option (b) (retire) |
| `src/backend/apps/core/tests/test_slo_constants.py` | — | ✔ Read-only. It pins `PerformanceSLO` **values only** and never touches PromQL — which is precisely the gap |

**Binding constraints**

1. **The scrape-contract test asserts against a rendered `/metrics`, never against the
   library source.** ✔ That is the whole point of `VAL-003`: the rules were written against a
   remembered API surface, and a test that re-derives the same remembered surface reproduces
   the defect.
2. **The test must fail when a selector is added that names a series the exposition does not
   contain**, and that failure must be demonstrated. A guard that only checks today's three
   rules is not a contract.
3. **Never add a moderation-queue-depth alert.** `AD-008` makes it structurally dead.
4. **The `redis_db_keyspace_hits_total` rule has no exporter.** ✔ No `redis_exporter` exists
   and none is deployed. Either the rule is retired, or it names a series the scrape will
   never produce — **which the new guard will reject**. Decide per Q5 and say which.
5. **A `PrometheusRule` CRD presupposes Kubernetes.** This project runs Compose. Under Q5
   option (a) the file must change form, and under (b) it must be labelled. It must not stay
   a CRD that nothing consumes.
6. **The stale multiprocess caveat is corrected in this block, not deferred.** ✔ Phase 01
   shipped `PROMETHEUS_MULTIPROC_DIR` plus the paired tmpfs plus the `child_exit` hook; the
   caveat that the default registry is in-process is now wrong.
7. **If Q5 option (a) is taken, BLOCK 8's service-set guard will fail** until the new
   `prometheus` service is named in the deploy path. That coupling is real and must be
   reported, not worked around.

**Implementor task**

```yaml
id: task_12_b11_slo_alert_contract
title: "Turn the SLO alert file into a verified contract, or stop it reading as one (12-OPS-003)"
priority: high
depends_on: [task_12_b10_deploy_provenance]
source_reference: ".ai/plans/12-production-ops-remediation.md"
source_section: "BLOCK 11 - Make the alert file a verified contract"
source_blocks: ["BLOCK 11"]
description: >
  Three alert rules in docs/ops/prometheus-slo-alerts.yaml select series that are never emitted:
  django_http_response_duration_seconds_bucket with a handler label and an le="2.000" edge that
  no bucket set contains, and redis_db_keyspace_hits_total from a redis_exporter that is in no
  compose file. No Prometheus, Alertmanager or Grafana exists in any of the four compose files,
  and nginx restricts /metrics to 127.0.0.1, so no other container can scrape it. The file is
  a Kubernetes PrometheusRule CRD in a Compose-only project, and its header caveat about an
  in-process metrics registry is now stale after phase 01 shipped multiprocess mode.
goals:
  - "correct every selector against the series a live scrape actually exposes"
  - "add a scrape-contract test that resolves every expr selector against a rendered /metrics"
  - "correct the stale multiprocess caveat"
  - "per the recorded Q5 option, either deploy a monitoring stack or stop the artefacts reading as active controls"
extra_context: |
  DECISION GATE - Q5 MUST BE ANSWERED FIRST. The Implementor may not choose. Q5 is an
  infrastructure decision the owner makes. Option (c) - minimum viable - is the Planner's
  recommendation: it ships the guard that makes a later deploy safe and costs nothing if it
  never happens.

  CARRY FORWARD: phase 05's AD-008 establishes that get_pending_queue_size() is structurally
  zero because ON_MODERATION is never committed. A moderation-queue-depth alert is dead on
  arrival. Never add one.

  BINDING CONSTRAINTS
  1. The scrape-contract test asserts against a RENDERED /metrics, never against the library
     source. Model it on apps/core/tests/test_observability.py::test_metrics_endpoint.
  2. The test must fail when a selector naming an absent series is added, and that failure must
     be demonstrated. Checking only today's three rules is not a contract.
  3. redis_db_keyspace_hits_total has no deployed exporter. Decide per Q5 which way it resolves
     and say which - the new guard will reject a selector the exposition cannot produce.
  4. The file must not remain a Kubernetes PrometheusRule CRD that nothing consumes.
  5. Correct the stale multiprocess caveat in this block.
  6. If Q5 option (a) is taken, BLOCK 8's service-set guard will fail until the new prometheus
     service is named in the deploy path. Report that coupling; do not work around it.
  7. If PROMETHEUS_LATENCY_BUCKETS is introduced, it is a new ALLOWED_ENV_VARS entry plus
     example-file entries in the SAME commit.
  FORBIDDEN: adding a moderation-queue alert; editing docker-compose.yml or
  docker-compose.test.yml; deploying Grafana or Alertmanager without the Q5 answer; editing
  the backup, scheduler or pgbouncer service blocks.
files:
  - path: docs/ops/prometheus-slo-alerts.yaml
    targets:
      - type: prometheus_rule
        name: search_slo_burn_rate
      - type: prometheus_rule
        name: search_p95_latency_slo
      - type: prometheus_rule
        name: cache_hit_rate_slo
  - path: src/backend/apps/core/tests/test_observability.py
    targets:
      - type: function
        name: test_metrics_endpoint
  - path: src/backend/apps/core/tests/test_slo_constants.py
    targets: []
  - path: docker-compose.prod.yml
    targets: []
  - path: config/settings/base.py
    targets:
      - type: module_constant
        name: ALLOWED_ENV_VARS
changes:
  - action: update_code
    description: >
      Correct every selector to the series a rendered /metrics exposes, or to a bucket edge the
      configured latency buckets actually contain.
  - action: update_code
    description: >
      Correct the header's stale multiprocess caveat and carry the AD-008 warning.
  - action: add_code
    description: >
      Add a scrape-contract test that parses every expr selector in the file and resolves it
      against the rendered exposition.
  - action: update_code
    description: >
      Per Q5, deploy the stack or label the artefacts as not deployed.
acceptance_criteria:
  - "every selector in the file resolves against a rendered /metrics, or the rule is retired"
  - "adding a selector naming an absent series turns the new test red, and that failure is demonstrated"
  - "the file is no longer a Kubernetes CRD that nothing consumes"
  - "the stale multiprocess caveat is corrected"
  - "no moderation-queue-depth alert exists"
  - "test_observability.py's existing assertions are green unchanged"
  - "the Q5 option and its consequences are recorded in the commit body"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/apps/core/tests/test_observability.py
  - src/backend/apps/core/tests/test_slo_constants.py
  - src/backend/tests/test_compose_contract.py
```

---

### BLOCK 12 — The detection floor, and the end of the unconsumed SLO artefacts (`OPS-011`)

| | |
|---|---|
| **Findings owned** | `OPS-011` (MEDIUM). **The `EMAIL_HOST` limb is phase 09's `API-009` and is not re-filed** |
| **Class** | **behavioural** — a new operator-visible surface, or an explicit declaration that there is none |
| **Depends on** | BLOCK 11 (Q5's answer determines what the floor *is* consumed by) |
| **Blocks** | BLOCK 14 (the doc sweep must describe whatever this block lands) |
| **Priority** | **P1** — the report calls this the detection floor that `OPS-007`, `OPS-014` and `OPS-021` all depend on |
| **Risk level** | **MEDIUM** under option (a) (a new env key, a new management command, a new transport path); **LOW** under (b) and (c) |
| **Blast radius** | `ALLOWED_ENV_VARS` + four example files (option (a) only), one management command, the `backup` service, `docs/ops/`. **The finding's value is that BLOCKS 2, 8 and 16 cannot be *noticed* without it** |
| **Required agents** | **Auditor · Planner · Validator.** Under option (a), **Researcher** as well (the transport and the recipient key) |

**What the finding actually is, after correction.** ✔ The report's stated evidence — that a
repository-wide `send_mail` search returns zero production hits — is **false**.
`src/telegram_bot/services/support_delivery_email.py::_send_mail` calls `send_mail` in
production and `EMAIL_HOST` is a mandatory guard in `prod.py` protecting a **real** delivery
path. The `EMAIL_HOST` sub-finding is therefore **duplicate of `API-009`** (phase 09) and is
removed. What survives is narrower and true: **there is no *operator-alerting* path anywhere**
— no management command, service, signal or host-side job inspects container health, dump
freshness, deploy outcome or the SLO rules.

**Decision required before implementation — Q10: what is the operator-notification floor?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | A `manage.py notify_operator` command delivered over the **Telegram transport the bot already has**, invoked by the `backup` service after each dump and by a host-side job reading `docker compose ps --format json` | **Gains:** the only option that reaches a human today. **Costs:** a recipient configuration key that does not exist — adding one means `ALLOWED_ENV_VARS` **and** all four `.env.*.example` files, or `test_env_allowlist.py` fails. It runs inside the `backup` service, which is `read_only: true` and `cap_drop: ["ALL"]`, and — until BLOCK 2 — root. And it introduces a **second sender** alongside the support-desk mail, which is exactly the adjacency `API-009` is examining |
| **(b)** | No command; ship the **dump-age and container-health signals** that BLOCK 2 already produces, for whatever Q5 decided to consume | **Gains:** no new command, no new env key, no second sender; it makes BLOCK 2's healthcheck actually *reachable*. **Costs:** if Q5 declined to deploy a stack, the signals go nowhere — **the detection gap remains exactly as wide** and this block becomes a documentation exercise |
| **(c)** | Neither; **formally declare detection out of scope** for a single-host deployment and document the gap as a known, accepted risk | **Gains:** honest, zero new surface, and it stops pretending. **Costs:** `OPS-011` is not closed; the finding's whole content is the absence, and declaring the absence accepted is a business decision, not a fix |

**The Implementor may not choose.** Q10 is an owner decision about who is on call.

**The unconditional half.** Whichever option is taken, `docs/ops/prometheus-slo-alerts.yaml`
and `docs/ops/grafana-slo-dashboard.json` must **stop reading as active controls** — either
corrected and labelled, or explicitly marked "planned — not deployed". BLOCK 11 may already
have done this under Q5 option (b); this block confirms the outcome rather than repeating it.

**File surface (semantic units)**

| File | Target | Notes |
|---|---|---|
| a new management command | `manage.py notify_operator` | **Only under Q10 option (a).** Its home is a decision, not an assumption |
| `config/settings/base.py` | `ALLOWED_ENV_VARS` | **Only under (a)** — the recipient key |
| `.env.prod.example`, `.env.dev.example`, `.env.test.example`, `.env.example` | the recipient key | **Only under (a).** All four, in the same commit |
| `docker-compose.prod.yml` | the `backup` service's `command:` loop | ✔ **BLOCK 2 owns this block.** This block may add an invocation; it may not re-edit the loop |
| `src/telegram_bot/services/` | the existing transport | Read-only unless (a) selects it; reuse the existing helper rather than opening an aiogram session |
| `docs/ops/` | the SLO artefacts' labelling | Confirm BLOCK 11's outcome |

**Binding constraints**

1. **`EMAIL_HOST`, `EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL` and the support-desk sender are out of
   scope.** They are phase 09's `API-009` and phase 02's settings surface. This block adds a
   **Telegram** notification path or none.
2. **The new recipient key is added to `ALLOWED_ENV_VARS` and all four example files in the
   same commit**, or `test_env_allowlist.py` fails in both directions.
3. **No `print()`.** A notification path is a `logging` caller first and a sender second.
   Exceptions must be **fail-open** — a failed alert must never take down the process that
   raised it, and it must say so in a comment. ✔ That is the existing convention the
   support-desk sender follows and the reason the report's evidence check found it at all.
4. **Reuse the existing Telegram transport**, not a new aiogram session, not a raw HTTP call
   with a hand-rolled bot token read. `SITE_URL` is already enforced in production for deep
   links; follow that precedent.
5. **Do not modify `backup`'s loop.** ✔ BLOCK 2 owns it, including the drift compensation and
   the prune convention. Adding an invocation is the maximum change here.
6. **The `backup` service runs `read_only: true` with `cap_drop: ["ALL"]`.** Anything the
   command writes to disk needs a `tmpfs` or it does not happen. Say which in the commit body.
7. **Under option (b), say plainly that the detection gap is unchanged.** A commit that ships
   a signal nobody consumes and calls `OPS-011` closed is a false completion.

**Implementor task**

```yaml
id: task_12_b12_operator_notification
title: "Build one operator-notification floor and end the unconsumed SLO artefacts (12-OPS-011)"
priority: medium
depends_on: [task_12_b11_slo_alert_contract]
source_reference: ".ai/plans/12-production-ops-remediation.md"
source_section: "BLOCK 12 - The detection floor"
source_blocks: ["BLOCK 12"]
description: >
  Nothing anywhere in the system inspects container health, dump freshness, deploy outcome or the
  SLO rules, and no webhook or Telegram admin-notify command exists. A container stuck unhealthy,
  a backup job that died a week ago, a failed nightly alert run and a failed deploy are all
  discovered by users filing complaints. Separately, the SLO alert file and the Grafana dashboard
  are referenced by nothing that runs.
goals:
  - "per the recorded Q10 option, establish one concrete operator-notification floor or formally record that there is none"
  - "make the SLO artefacts stop reading as active controls"
extra_context: |
  DECISION GATE - Q10 MUST BE ANSWERED FIRST. The Implementor may not choose. Q10 is an owner
  decision about who is on call. Under option (a), Researcher is also required.

  BINDING CONSTRAINTS
  1. EMAIL_HOST, EMAIL_BACKEND, DEFAULT_FROM_EMAIL and the support-desk sender are OUT OF SCOPE
     - phase 09's API-009 and phase 02's settings surface. This block adds a Telegram path or none.
  2. Any new recipient key goes into ALLOWED_ENV_VARS and all four .env.*.example files in the
     SAME commit.
  3. No print(). The notification path is a logging caller first and a sender second. Exceptions
     are fail-open, and the comment must say why: a failed alert must never take down the process
     that raised it.
  4. Reuse the existing Telegram transport. Do not open a new aiogram session and do not read a
     bot token by hand.
  5. Do NOT modify the backup service's loop - BLOCK 2 owns it. Adding an invocation is the
     maximum change.
  6. The backup service is read_only: true with cap_drop ALL. Anything written to disk needs a
     tmpfs; say which in the commit body.
  7. Under option (b), say plainly that the detection gap is UNCHANGED.
  FORBIDDEN: re-filing the EMAIL_HOST limb; adding a second send_mail call site; editing
  docker-compose.yml or docker-compose.test.yml; touching the backup loop's sleep, prune or
  filename convention.
files:
  - path: docs/ops/prometheus-slo-alerts.yaml
    targets: []
  - path: docs/ops/grafana-slo-dashboard.json
    targets: []
  - path: config/settings/base.py
    targets:
      - type: module_constant
        name: ALLOWED_ENV_VARS
  - path: .env.prod.example
    targets: []
  - path: .env.dev.example
    targets: []
  - path: .env.test.example
    targets: []
  - path: .env.example
    targets: []
changes:
  - action: update_code
    description: >
      Per Q10, add the notification floor or record the accepted gap.
  - action: update_code
    description: >
      Confirm the SLO artefacts are labelled as deployed or not deployed.
acceptance_criteria:
  - "the Q10 option and its consequences are recorded in the commit body"
  - "under option (b), the commit body states that the detection gap is unchanged and does not claim 12-OPS-011 is closed"
  - "under option (a), the recipient key is in ALLOWED_ENV_VARS and all four example files in the same commit"
  - "under option (a), a failed notification cannot take down the calling process, and that is demonstrated"
  - "the backup service loop is byte-identical to the end of BLOCK 2"
  - "no send_mail call site was added"
  - "the SLO artefacts do not read as active controls"
  - "test_env_allowlist.py is green"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/config/settings/tests/test_env_allowlist.py
  - src/backend/tests/test_compose_hardening.py
  - src/backend/tests/test_compose_contract.py
```

---

### BLOCK 13 — Decide what the readiness probe is allowed to claim (`OPS-010`)

| | |
|---|---|
| **Findings owned** | `OPS-010` (MEDIUM) |
| **Class** | **behavioural** — `/health/ready/` is the deploy gate |
| **Depends on** | BLOCK 7 (`docker-compose.prod.yml`) |
| **Blocks** | BLOCK 14 (the doc sweep corrects the readiness criterion to match this block's outcome); BLOCK 18 (both touch the health surface) |
| **Priority** | P2 |
| **Risk level** | **MEDIUM** — the change can make a deploy fail for a reason unrelated to the deploy |
| **Blast radius** | `docker-compose.prod.yml`'s `web` block, `.env.prod.example`, three `docs/ops/` files, `apps/core/tests/test_health_contract.py` |
| **Required agents** | **Auditor · Planner · Validator.** **Researcher** under option (a), because the deploy-pipeline consequence must be reproduced |

**The finding, after correction.** ✔ `readiness_check` verifies the Redis `bot:liveness` marker
only when `BOT_HEALTH_CHECK_ENABLED` is true, and `base.py` defaults it `False`. No compose file
sets it, it is absent from `.env.prod.example`, and the base compose ships
`BOT_HEALTH_STALE_SECONDS=120` for `web` and `bot` without ever shipping the enable flag — **a
configured-but-disabled control.** The reported impact ("ads accepted by the bot that are never
published") is **withdrawn**: a stale marker means new submissions are not *started*;
already-persisted `DRAFT` rows are unaffected.

**Why this is not a config flip.** `/health/ready/` is the **deploy gate** — `deploy.yml` polls
it for 60 s and rolls the deploy back if it does not return 200 — and it is the **documented
rollback validation target** in `rollback.md`. Turning the bot check on means **a wedged bot
fails the deploy**, not merely reports degraded readiness. That is a change to the deploy
pipeline's failure model.

**Decision required before implementation — Q6: enable the coupling, or remove the claim?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Set `BOT_HEALTH_CHECK_ENABLED=true` for `web` in `docker-compose.prod.yml`, ship the key in `.env.prod.example`, and document the widened readiness contract | **Gains:** the readiness probe observes a bot that is alive but no longer polling — a retry loop, a stuck long-poll, a wedged dispatcher — which today it cannot. **Costs:** the deploy gate now fails on a bot fault. A bot outage blocks deploys and a deploy can roll back for a bot reason. The 120 s window is also shorter than a gunicorn restart cycle in some configurations — that must be measured, not assumed |
| **(b)** | Keep the decoupling (the setting comment documents the reasoning) and **remove** `BOT_HEALTH_STALE_SECONDS` from `web` and `bot`, drop the bot claim from the runbooks, and say readiness probes DB + cache only | **Gains:** no configured-but-disabled control; the documentation matches the intent. **Costs:** the readiness probe cannot observe a wedged bot at all, and the deploy gate cannot either |
| **(c)** | Keep the flag off in production but ship it in `.env.prod.example` as an operator opt-in, documented | **Gains:** the capability exists without changing the deploy failure model. **Costs:** a default-off control with documentation is the shape `OPS-018` complains about, one level up. Only defensible if the documentation is unambiguous about it being off by default |

**The Implementor may not choose.** Q6 changes what "the deploy succeeded" means.

**File surface (semantic units)**

| File | Target | Notes |
|---|---|---|
| `docker-compose.prod.yml` | `web` — `environment:` (or the base's `web` `environment:` if the prod override must inherit it) | Per Q6. ✔ The prod `web` override sets only `image`, `env_file`, `volumes` and `stop_grace_period`, so it inherits the base `environment:` verbatim |
| `docker-compose.yml` | `web`, `bot` — `BOT_HEALTH_STALE_SECONDS` | **Only under Q6 option (b).** ✔ **BLOCK 1 owns this file** — BLOCK 13 may not edit it. If option (b) is selected, this is a **reported** cross-block edit, executed by whoever runs BLOCK 1 or in a follow-up commit, never silently by BLOCK 13 |
| `.env.prod.example` | `BOT_HEALTH_CHECK_ENABLED` | ✔ The key is **already in `ALLOWED_ENV_VARS`**, so shipping it in the example file is allowlist-clean |
| `apps/core/tests/test_health_contract.py` | the `BOT_HEALTH_CHECK_ENABLED` branches | ✔ Already covers **both** branches via `override_settings` |
| `docs/ops/rollback.md`, `docs/ops/docker-deployment.md` | the readiness criterion | BLOCK 14's sweep, informed by this block |

**Binding constraints**

1. **`BOT_HEALTH_CHECK_ENABLED` is already in `ALLOWED_ENV_VARS`** ✔ — unlike BLOCK 7's and
   BLOCK 12's new keys, this one needs no allowlist edit. **Verify that before editing**; if
   another phase has removed it, this block must re-add it and run `test_env_allowlist.py`.
2. **`docker-compose.yml` is BLOCK 1's file.** Q6 option (b) requires removing
   `BOT_HEALTH_STALE_SECONDS` from it. That edit is **reported, not silently made** — see the
   file-surface table.
3. **The `120 s` staleness window must be measured, not assumed**, under option (a). ✔ It
   ships for both `web` and `bot`; a window shorter than a legitimate pause produces a false
   deploy rollback.
4. **`test_health_contract.py` already covers both branches.** Do not rewrite it. Extend it
   only if the option adds a case it does not have.
5. **Do not conflate this with `AD-008`** (phase 05). That is a different signal — a
   moderation-queue metric — and the two must not appear in the same remediation narrative.
6. **`/health/live/` must remain dependency-free.** ✔ It is the container `HEALTHCHECK` target
   in both `docker/Dockerfile` and `docker-compose.yml`. A liveness probe that depends on
   anything restarts the container; this block changes readiness only.
7. **If the option changes the readiness contract, `rollback.md`'s validation criterion is
   BLOCK 14's to correct** — this block records the outcome and BLOCK 14 writes it down.

**Implementor task**

```yaml
id: task_12_b13_bot_readiness
title: "Decide what the readiness probe is allowed to claim (12-OPS-010)"
priority: medium
depends_on: [task_12_b07_pgbouncer_and_mem_limits]
source_reference: ".ai/plans/12-production-ops-remediation.md"
source_section: "BLOCK 13 - Decide what the readiness probe is allowed to claim"
source_blocks: ["BLOCK 13"]
description: >
  readiness_check verifies the Redis bot:liveness marker only when BOT_HEALTH_CHECK_ENABLED is
  true, and base.py defaults it False. No compose file sets it and it is absent from
  .env.prod.example, yet the base compose ships BOT_HEALTH_STALE_SECONDS=120 for web and bot
  without shipping the enable flag - a configured-but-disabled control. /health/ready/ is the
  deploy gate and the documented rollback validation target, so enabling the coupling means a
  wedged bot fails a deploy rather than merely reporting degraded readiness.
goals:
  - "per the recorded Q6 option, either enable the coupling in production and document the widened readiness contract, or remove the shipped-but-disabled window and the claims that depend on it"
  - "leave no configured-but-disabled control described as active"
extra_context: |
  DECISION GATE - Q6 MUST BE ANSWERED FIRST. The Implementor may not choose. Q6 changes what
  "the deploy succeeded" means. Under option (a), Researcher is required to measure the staleness
  window against a real pause in the bot's liveness refresh.

  BINDING CONSTRAINTS
  1. BOT_HEALTH_CHECK_ENABLED is ALREADY in ALLOWED_ENV_VARS - verify before editing. If another
     phase removed it, re-add it and run test_env_allowlist.py.
  2. docker-compose.yml is BLOCK 1's file. Q6 option (b) needs BOT_HEALTH_STALE_SECONDS removed
     from it. REPORT that cross-block edit; do not make it silently in this block.
  3. Under option (a), the 120 s window must be MEASURED against a real pause, not assumed.
  4. Do NOT rewrite test_health_contract.py - it already covers both branches. Extend only if the
     option adds an uncovered case.
  5. Do NOT conflate this with phase 05's AD-008, which is a different signal.
  6. /health/live/ stays dependency-free. It is the container HEALTHCHECK target.
  FORBIDDEN: editing docker-compose.yml without reporting it (BLOCK 1 owns it); editing
  docker-compose.test.yml; changing liveness_check; removing the /health/ready/ deploy gate.
files:
  - path: docker-compose.prod.yml
    targets:
      - type: service
        name: web
  - path: .env.prod.example
    targets:
      - type: env_key
        name: BOT_HEALTH_CHECK_ENABLED
  - path: src/backend/apps/core/tests/test_health_contract.py
    targets: []
changes:
  - action: update_code
    description: >
      Per Q6, set the coupling in production or remove the shipped-but-disabled window, and record
      the outcome for BLOCK 14.
acceptance_criteria:
  - "the Q6 option and its consequences are recorded in the commit body"
  - "no configured-but-disabled control is left described as active"
  - "liveness_check is byte-identical and /health/live/ remains dependency-free"
  - "test_health_contract.py is green unchanged unless a genuinely new case was added"
  - "test_env_allowlist.py is green"
  - "any required docker-compose.yml edit is reported rather than made silently"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/apps/core/tests/test_health_contract.py
  - src/backend/config/settings/tests/test_env_allowlist.py
  - src/backend/tests/test_compose_contract.py
  - src/backend/tests/test_compose_hardening.py
```

---

### BLOCK 14 — Bring `docs/ops/` back in line with the repository (`OPS-018`)

| | |
|---|---|
| **Findings owned** | `OPS-018` (MEDIUM) — **twelve** instances, not seven |
| **Class** | **behavioural** — the only description of the production system changes |
| **Depends on** | BLOCK 4 (the SAST paragraph), BLOCK 9 (the runbooks), BLOCK 13 (the readiness criterion) |
| **Blocks** | BLOCK 15 (the parity guard must be written **after** the docs, never with them) |
| **Priority** | P1 — the three highest-harm documentation defects in the repository are correctable in one pass |
| **Risk level** | **LOW technically, HIGH in consequence** — a wrong correction is worse than a known-false claim, because it removes the signal that something is off |
| **Blast radius** | Six `docs/ops/` files plus `docs/99-agent/` if a topology statement changed. **No code, no compose** |
| **Required agents** | **Auditor · Planner · Validator.** Researcher not required; every claim was re-read in the tree |

**Twelve instances, grouped by kind**

**False claims about controls that do not work** (the report's live six):

| Location | Claim | Reality |
|---|---|---|
| `docker-deployment.md` — the SAST blockquote | the `security` job runs bandit against both trees per `[tool.bandit]`, spelling out the exclusions | ✔ BLOCK 4 made it true. If BLOCK 4 did not land, **delete the paragraph** rather than restate it |
| `docker-deployment.md` — "Prometheus Metrics" | "An external Prometheus instance scrapes it on its own schedule" | ✔ BLOCK 11's outcome. State what is actually deployed, or that none is |
| `docker-deployment.md` — the `deploy-check` env list | the job sets `REDIS_URL` | ✔ **Already true** (phase 02). **Not corrected here** — correcting a true statement is a regression |
| `rollback.md` — the config-rollback table row | `git checkout .env.prod` to a pinned commit | ✔ `.env` and `.env.*` are gitignored; this cannot work |
| `rollback.md` — "Identifying the target image tag" | `git log --oneline -10 -- .env.prod` / `git show <commit>:.env.prod` | Same |
| `rollback.md` — the validation-checklist row | `checks.bot == "ok"` | ✔ BLOCK 13's outcome. **Note the internal contradiction**: another section of the *same document* correctly documents `"disabled"` as the default |
| `rollback.md` — the image-tag note | "All seven services in `docker-compose.prod.yml` (lines 8, 18, 28, 36, 44, 54, 63)" | ✔ **Eight** `image:` lines, at different offsets, plus `pgbouncer` which has no `IMAGE_TAG` reference at all (C-2) |

**Drift instances created by phases 01/02** (six, none of them in the report):

| Location | Claim | Reality |
|---|---|---|
| `docker-deployment.md` — "Production Logging" | the root logger is configured at `INFO` | ✔ `prod.py` sets `root.level = "WARNING"` |
| `docker-deployment.md` — "Production Services" | `web`/`bot`/`migrate` are "Build image" | In production they are GHCR images |
| `prometheus-slo-alerts.yaml` — header | the default `prometheus_client` registry is in-process and each scrape returns one worker's metrics | ✔ Phase 01 shipped multiprocess mode. **BLOCK 11 owns this file** — do not double-edit; BLOCK 11's outcome is the answer |
| `docker-deployment.md` — a cross-reference | links to `.ai/audit/12-production-ops/findings.md` | ✔ **That file is deleted.** Re-point at the validated report (**Q14**) |
| `rollback.md` | `IMAGE_TAG` is at `.env.prod.example` "line 68" | ✔ It is line **83** |
| `restore.md` — "Related Documentation" | "No backup testing in CI (ephemeral environment)" | ✔ `restore-test.yml` exists and runs monthly |

**Binding constraints**

1. **Never encode a false claim as truth.** The parity guard comes in BLOCK 15, **after** this
   block. A test written in the same commit as the correction cannot be reviewed against the
   truth.
2. **The refuted `bazuna_db` sub-claim must not be reintroduced in either direction.**
   ✔ `.env.prod.example` **is** `POSTGRES_DB=bazuna_db` and `restore.md` names it correctly.
   The defect was the credential *source*, which BLOCK 9 fixed.
3. **Do not correct `rollback.md`'s correct invocations.** ✔ Its production `docker compose`
   lines already carry `--env-file .env.prod`.
4. **A correction must state what is true now, not only that the old text was false.** A
   reader needs the procedure, not the erratum.
5. **Per Q14's default, re-point the dead audit link at the validated report** and do **not**
   add markdown link resolution to any guard. ✔ The audit tree is unmodifiable by mandate;
   **the doc** is what changes.
6. **Do not restore `.ai/audit/12-production-ops/findings.md`.** It is deleted, and the
   validated report preserves the corrected evidence inline.
7. **Line-number citations in prose rot.** Where this block rewrites a line reference, prefer a
   **semantic** anchor — a service name, a key name, a URL — over a line number. That is the
   root cause of the `rollback.md` and `prometheus-slo-alerts.yaml` drift instances, and it
   must not be reproduced.
8. **`docs/99-agent/architecture.md` and `docs/99-agent/rules.md`** change only if a
   deployment-topology statement changed in this phase — most plausibly if BLOCK 8 created a
   shared contract file or BLOCK 11 added a service.
9. **No user-visible string.** Documentation is not translated; `msgstr` obligations do not
   apply and the locale catalogues are untouched.

**Implementor task**

```yaml
id: task_12_b14_ops_docs_truth
title: "Bring docs/ops back in line with the repository (12-OPS-018)"
priority: high
depends_on: [task_12_b04_sast_gate, task_12_b09_runbook_executability, task_12_b13_bot_readiness]
source_reference: ".ai/plans/12-production-ops-remediation.md"
source_section: "BLOCK 14 - Bring docs/ops back in line with the repository"
source_blocks: ["BLOCK 14"]
description: >
  Six of the report's seven documented claims are still false - a security control described as
  working when it never ran, a Prometheus scrape that nginx refuses, git operations on a
  gitignored file, a readiness criterion the probe does not return, and a service count with
  wrong line references. Six further instances of drift were created by phases 01 and 02 and are
  not in the report. One of the report's seven was already fixed by phase 02 and must not be
  "corrected" back.
goals:
  - "correct every confirmed false claim in docs/ops to state what is true after blocks 4, 9, 11 and 13"
  - "correct the six drift instances phases 01 and 02 created"
  - "leave every true statement untouched"
  - "replace rotting line-number citations with semantic anchors"
extra_context: |
  BINDING CONSTRAINTS
  1. No parity test in this block. BLOCK 15 writes it, after this block lands.
  2. Do NOT reintroduce the refuted bazuna_db sub-claim in either direction. The defect was the
     credential SOURCE, which BLOCK 9 fixed.
  3. Do NOT touch the deploy-check env claim in docker-deployment.md - phase 02 made it TRUE.
  4. Do NOT "correct" rollback.md's production docker compose invocations - they are already
     correct.
  5. A correction states what is true now, not only that the old text was false.
  6. Per Q14's default, re-point the dead .ai/audit/12-production-ops/findings.md link at the
     validated report, and do NOT add markdown link resolution to any test.
  7. Never restore .ai/audit/12-production-ops/findings.md.
  8. Prefer semantic anchors over line numbers when rewriting a reference.
  9. prometheus-slo-alerts.yaml is BLOCK 11's file. Do not double-edit its header; use BLOCK 11's
     recorded outcome.
  10. Documentation is not translated. Do not touch any locale file.
  FORBIDDEN: writing the parity test; editing code; editing compose files; editing any file
  under .ai/audit/.
files:
  - path: docs/ops/docker-deployment.md
    targets:
      - type: markdown_section
        name: "CI security scanning (SAST)"
      - type: markdown_section
        name: "Prometheus Metrics"
      - type: markdown_section
        name: "Production Logging"
      - type: markdown_section
        name: "Production Services"
  - path: docs/ops/rollback.md
    targets:
      - type: markdown_section
        name: "Config Rollback"
      - type: markdown_section
        name: "Identifying the target image tag"
      - type: markdown_section
        name: "Image-Tag Rollback"
  - path: docs/ops/restore.md
    targets:
      - type: markdown_section
        name: "Related Documentation"
  - path: docs/99-agent/architecture.md
    targets: []
  - path: docs/99-agent/rules.md
    targets: []
changes:
  - action: update_code
    description: >
      Correct each confirmed false claim to state what is true after blocks 4, 9, 11 and 13.
  - action: update_code
    description: >
      Correct the six drift instances created by phases 01 and 02, including the root-logger
      level, the production-service table, the dead audit link, the IMAGE_TAG line reference and
      the "no backup testing in CI" claim.
  - action: update_code
    description: >
      Replace rotting line-number citations with semantic anchors.
acceptance_criteria:
  - "no statement in docs/ops describes a control that does not run or cannot work"
  - "the already-true deploy-check env claim is untouched"
  - "rollback.md's correct production compose invocations are untouched"
  - "no line-number-only citation remains where a semantic anchor is available"
  - "the dead audit link is re-pointed at the validated report"
  - "no file under .ai/audit/ was created, restored or modified"
  - "no locale file was touched"
  - "the parity test is NOT in this commit"
tests_to_run: []
```

---

### BLOCK 15 — The behavioural-guard convention, and a `docs/ops` parity guard (`VAL-003`)

| | |
|---|---|
| **Findings owned** | `VAL-003` (MEDIUM) — implemented as a guard, not as a convention note |
| **Class** | **mechanical** — a test file |
| **Depends on** | **BLOCK 14**, strictly |
| **Blocks** | nothing in-plan; it is the phase's guard for BLOCK 18 and any future ops change |
| **Priority** | P1 |
| **Risk level** | **MEDIUM** — a guard written in the same commit as the documentation it checks can only ever confirm the documentation |
| **Blast radius** | `src/backend/tests/test_docs_ci_parity.py` or a new sibling module. **Nothing else** |
| **Required agents** | **Auditor · Planner · Validator.** The Validator adds a deliberate break, confirms the guard fires, and removes it |

**Why it is a separate block.** ✔ The report's warning is explicit: *"the parity test must not
encode today's wrong claims as truth — write it only after the docs are corrected."* A guard
written in the same commit as the correction is reviewed against the version it is meant to
police.

**Decision required before implementation — Q14: does the guard resolve markdown
cross-references?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Resolve every relative markdown link in `docs/ops/` | **Gains:** a dead link becomes a red test forever. **Costs:** the guard is **red on arrival** — `docker-deployment.md` links to the deleted `findings.md`, so BLOCK 15 would also have to fix a doc, collapsing it into BLOCK 14. It also asserts a property nobody asked for |
| **(b)** *(default, stated)* | **Do not resolve links.** Assert the properties the finding actually names: every `ghcr.io` literal, every `docker compose` command's flags, and every env-var name quoted in `docs/ops/` appears in the corresponding live file | **Gains:** checkable today, on the finding's own terms, and the dead link is fixed by BLOCK 14 as a **documentation** change. **Costs:** a markdown link can still rot |

**The default answer is (b).** BLOCK 15 must not silently take (a).

**Binding constraints**

1. **BLOCK 14 lands first, in its own commit.** This block's guard is reviewed against the
   corrected documentation.
2. **The guard's direction matters.** It asserts **documentation → live file**, not
   **live file → documentation**. A newly added compose service must not force a doc sentence
   unless the doc makes a claim about it.
3. **Do not assert line numbers.** ✔ Line-number citations are what rotted in the first place
   (C-2, the `rollback.md` "line 68" instance). Assert on service names, key names, commands
   and flags.
4. **Do not assert on content BLOCK 11 or BLOCK 13 owns** — `prometheus-slo-alerts.yaml`'s
   header and the readiness criterion are their outcomes. This guard confirms the recorded
   result; it does not set it.
5. **The `Makefile` / `Makefile.ps1` parity test already exists** for `test-recreate`. ✔ Extend
   it only if BLOCK 9 option (a) added a target; do not build a second mechanism.
6. **Demonstrate the guard failing.** ✔ Every guard this plan adds is shown to fire (0.2.2
   item 4). A guard never observed failing is not a guard.
7. **This block replaces no shipped assertion**, so project rule 2 is not invoked. Say so
   explicitly rather than leaving it ambiguous.

**Implementor task**

```yaml
id: task_12_b15_ops_docs_parity
title: "Assert the ops documentation against the live files (VAL-003)"
priority: medium
depends_on: [task_12_b14_ops_docs_truth]
source_reference: ".ai/plans/12-production-ops-remediation.md"
source_section: "BLOCK 15 - The behavioural-guard convention and a docs/ops parity guard"
source_blocks: ["BLOCK 15"]
description: >
  Every control the pipeline asserts is verified by a string-presence check, which is the shared
  root cause of three findings in this phase: a substring guard could not detect a SAST step that
  scanned nothing, a documentation-level assertion could not detect a dead PromQL selector, and a
  string-level drill guard could not detect a drill that restored nothing. BLOCK 14 corrected the
  documentation; this block makes the corrected documentation a contract.
goals:
  - "assert that every ghcr.io literal, every docker compose command's flags and every env-var name quoted in docs/ops appears in the corresponding live file"
  - "assert in the documentation-to-live-file direction, on semantic anchors, never on line numbers"
  - "demonstrate the guard failing"
extra_context: |
  DECISION GATE - Q14. The DEFAULT ANSWER IS (b): do NOT resolve markdown links. Option (a)
  would be red on arrival because docker-deployment.md links to the deleted
  .ai/audit/12-production-ops/findings.md, which BLOCK 14 fixes as a documentation change.

  BINDING CONSTRAINTS
  1. BLOCK 14 must already be committed. This block's guard is reviewed against the corrected
     documentation, never against the version it is meant to police.
  2. The guard runs documentation -> live file, not the reverse.
  3. Never assert a line number. Assert service names, key names, commands and flags.
  4. Do not assert on the prometheus-slo-alerts.yaml header or the readiness criterion -
     BLOCKS 11 and 13 own those. This guard confirms their recorded outcomes.
  5. Extend the existing Makefile / Makefile.ps1 parity test rather than building a second
     mechanism.
  6. Demonstrate the guard failing before committing.
  FORBIDDEN: editing docs/ops/ in this block; resolving markdown links; editing any compose or
  workflow file; editing a file under .ai/audit/.
files:
  - path: src/backend/tests/test_docs_ci_parity.py
    targets:
      - type: module
        name: test_docs_ci_parity
  - path: src/backend/tests/test_compose_contract.py
    targets: []
changes:
  - action: add_code
    description: >
      Add tests asserting every registry literal, every docker compose command's flags and every
      env-var name quoted in docs/ops resolves in the corresponding live file.
acceptance_criteria:
  - "the guard is red when a documented flag is removed and red when a documented literal is changed, and both failures are demonstrated"
  - "no line number appears in any new assertion"
  - "no markdown link is resolved by the new guard"
  - "BLOCK 14's corrections are present and unmodified by this block"
  - "the existing docs/ops-free parity assertions are green unchanged"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/tests/test_docs_ci_parity.py
```

---

### BLOCK 16 — Make the restore drill prove something about a real restore (`OPS-004`)

| | |
|---|---|
| **Findings owned** | `OPS-004` (HIGH) |
| **Class** | **conditional** — the unconditional half always ships; the real-artifact half may be declined |
| **Depends on** | BLOCK 2 (`Makefile`), BLOCK 9 (the runbook), BLOCK 10 (the recorded image tag) |
| **Blocks** | nothing in-plan; BLOCK 14's RPO/RTO correction cites this block's outcome |
| **Priority** | P1 |
| **Risk level** | **MEDIUM** — `pg_restore` into an isolated instance is destructive by nature, and the target it changes is the one an operator reaches for |
| **Blast radius** | `Makefile`'s `restore-test` target, `.github/workflows/restore-test.yml`, `src/backend/tests/test_restore_test_workflow.py`, `docs/ops/restore.md`. **No compose file edit.** The blast radius is **the recovery path** |
| **Required agents** | **Auditor · Researcher · Planner · Validator** |

**What is unconditional and what is gated.**

| Half | Ships? | Content |
|---|---|---|
| **Preconditions** | **always** | ✔ The drill's smoke tests currently `echo` a table count and an `ads_ad` row count and assert **nothing**. Make an empty or partial restore **fail**: `django_migrations` must exist, `ads_ad` rows must be plausible |
| **Image pin** | **always** | ✔ `restore-test.yml` pulls `ghcr.io/mko-bazuna/mko_bazuna:${{ github.sha }}`. On a `schedule` trigger `github.sha` is the default-branch tip at fire time, which may have **no pushed image**, so the monthly drill can fail at `docker pull` for a reason unrelated to backup integrity |
| **Honest labelling** | **always** | The self-generated dump is kept, but as an **additional** smoke test, labelled as what it is |
| **Real artifact** | **gated on Q8** | Downloading the newest production dump requires an off-host artifact path that **does not exist** |

**Decision required before implementation — Q8: is off-host artifact replication in scope?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Have the `backup` service push the newest dump to object storage (a signed push is the practical route); `restore-test.yml` downloads the most recent artifact | **Gains:** the control proves what it exists to prove — that real artifacts are restorable. A truncated, silently corrupted, wrong-version or row-missing backup fails. **Costs:** new credentials, a new external dependency, retention policy, and a restore path that reads from it. **This is a platform investment, not an edit** |
| **(b)** | Decline; ship the unconditional half and **document precisely what the drill does and does not prove** | **Gains:** the control becomes honest about its scope at near-zero cost. **Costs:** ✔ **the finding is not closed** — `OPS-004`'s content is precisely that the drill proves nothing about real backups. This must be recorded as an accepted, documented risk, not as a fix |
| **(c)** | Ship the unconditional half **and** raise the off-host replication as a separate infrastructure work item with a named owner | **Gains:** nothing is dropped and the decision is on record. **Costs:** the same as (b) plus a commitment |

**The Implementor may not choose.** Q8 is an infrastructure decision. **Under any option, the
unconditional half ships** — that is the point of splitting it.

**File surface (semantic units)**

| File | Target | Notes |
|---|---|---|
| `Makefile` | the `restore-test` target — smoke steps 2/4 and 3/4, plus a new `django_migrations` check | ✔ It already computes both counts; it just does not assert on them |
| `.github/workflows/restore-test.yml` | the `migrate --plan --check` step's image reference; the dump-acquisition steps | Per Q8 |
| `src/backend/tests/test_restore_test_workflow.py` | the string-level guards | ✔ Currently asserts `"schedule:" in text`, `"cron:" in text`, `"migrate --plan --check" in text` — **the same class that let this through** |
| `docs/ops/restore.md` | the drill's scope statement | BLOCK 14's sweep; this block supplies the honest description |

**Binding constraints**

1. **`make restore-test` must still restore into an isolated instance** — separate volume,
   separate network, separate database, using `docker run` directly rather than
   `docker compose`. ✔ The target's isolation property is the reason a drill is safe to run on
   a schedule, and it must not change.
2. **The preconditions must be able to fail.** Asserting `ads_ad` rows > 0 is only meaningful
   if an empty restore genuinely fails the target. Demonstrate it.
3. **The image pin must be a recorded, known-good tag** — not `${{ github.sha }}` on a
   `schedule` trigger. If BLOCK 10 introduced digest-based rollback, use that mechanism.
4. **Keep the self-generated dump path as an additional smoke test** and label it. Deleting it
   would lose a fast, hermetic check that the round trip works at all.
5. **Do not run `pg_restore` against a live database.** Never. The isolation property is a
   hard constraint, not a preference.
6. **The new guard must be behavioural, not string-level.** ✔ Asserting that the target
   *computes* a count is the defect; asserting that an empty restore **fails** is the fix.
   `test_restore_test_workflow.py`'s existing string guards may stay, but they are not the
   guard for this finding.
7. **`Makefile.ps1` has no `restore-test` target** (C-15), so **no parity obligation arises** for
   this edit. ✔ Do not add one — that is §6.1.

**Implementor task**

```yaml
id: task_12_b16_restore_drill
title: "Make the restore drill prove something about a real restore (12-OPS-004)"
priority: high
depends_on: [task_12_b09_runbook_executability, task_12_b10_deploy_provenance]
source_reference: ".ai/plans/12-production-ops-remediation.md"
source_section: "BLOCK 16 - Make the restore drill prove something about a real restore"
source_blocks: ["BLOCK 16"]
description: >
  The monthly restore-test job bootstraps a fresh CI database, pg_dumps that same database three
  steps later and hands the result to make restore-test, so it proves nothing about any real
  backup. Its smoke steps echo a table count and an ads_ad row count and assert nothing, and its
  migrate --plan --check step pulls an image tagged with github.sha, which on a schedule trigger
  is the default-branch tip and may have no pushed image.
goals:
  - "make an empty or partial restore fail the drill"
  - "pin the drill's application image to a recorded known-good tag"
  - "keep the self-generated dump as a labelled additional smoke test"
  - "per the recorded Q8 option, either consume a real artifact or document precisely what the drill does not prove"
extra_context: |
  DECISION GATE - Q8. The UNCONDITIONAL HALF SHIPS UNDER EVERY OPTION. Q8 decides only whether
  the real-artifact half ships. Under option (b) or (c), 12-OPS-004 IS NOT CLOSED and the
  commit body must say so.

  BINDING CONSTRAINTS
  1. make restore-test must still restore into a fully isolated instance - separate volume,
     network and database, via docker run rather than docker compose. This is a hard constraint.
  2. The preconditions must be able to fail. Demonstrate that an empty restore fails the target.
  3. The image pin must be a recorded known-good tag, not github.sha on a schedule trigger. If
     BLOCK 10 introduced digest-based rollback, use that mechanism.
  4. Keep the self-generated dump as a labelled ADDITIONAL smoke test. Deleting it loses a fast
     hermetic check that the round trip works at all.
  5. Never run pg_restore against a live database.
  6. The new guard is behavioural. The existing string guards in
     test_restore_test_workflow.py may stay, but they are not the guard for this finding.
  7. Do NOT add a restore-test target to Makefile.ps1 - it has none and none is required.
  FORBIDDEN: editing compose files; weakening the isolation property; deleting the self-generated
  dump path; editing docs/ops/restore.md beyond the drill's scope statement.
files:
  - path: Makefile
    targets:
      - type: make_target
        name: restore-test
  - path: .github/workflows/restore-test.yml
    targets:
      - type: workflow_job
        name: restore-test
  - path: src/backend/tests/test_restore_test_workflow.py
    targets: []
changes:
  - action: update_code
    description: >
      Make the smoke steps assert: django_migrations exists and ads_ad has a plausible row count.
  - action: update_code
    description: >
      Pin the migrate --plan --check image to a recorded known-good tag.
  - action: update_code
    description: >
      Per Q8, either download the newest real artifact or label the self-generated dump honestly
      and record what the drill does not prove.
  - action: add_code
    description: >
      Add a behavioural guard demonstrating that an empty restore fails.
acceptance_criteria:
  - "an empty or partial restore fails the drill target, and that failure is demonstrated"
  - "django_migrations presence is asserted, not merely counted"
  - "the drill no longer pulls an image tagged with github.sha on a schedule trigger"
  - "the self-generated dump path still exists and is labelled as an additional smoke test"
  - "the isolation property - separate volume, network and database via docker run - is unchanged"
  - "the Q8 option is recorded in the commit body, and under (b) or (c) the body states that 12-OPS-004 is not closed"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/tests/test_restore_test_workflow.py
  - src/backend/tests/test_docs_ci_parity.py
```

---

### BLOCK 17 — Route gunicorn's own logs through the redacting formatter (`OPS-012`)

| | |
|---|---|
| **Findings owned** | `OPS-012` (LOW, ↓MEDIUM) |
| **Class** | **behavioural** — it changes how the arbiter starts |
| **Depends on** | BLOCK 12 (the phase's observability work precedes its log-format work) |
| **Blocks** | nothing in-plan |
| **Priority** | P3 — ✔ the report says explicitly: *"do not let it compete with `OPS-007` for the same deploy window"* |
| **Risk level** | **HIGH for its severity** — `logconfig_dict` is evaluated at startup and a malformed log config crashes the arbiter **before** the server binds, turning a logging change into an outage |
| **Blast radius** | `gunicorn.conf.py` — **a phase-01-owned file at the repository root**. Plus the log stream every operator reads |
| **Required agents** | **Auditor · Researcher · Planner · Validator.** The Researcher verifies the config in a throwaway container before it lands |

**The finding, after the severity correction.** ✔ The facts are confirmed: production configures
a structured `LOGGING` dict with `RedactingJsonFormatter` for the `django*`/`apps*`/`telegram_bot`
trees and sets the root logger to `WARNING`; gunicorn's `accesslog`/`errorlog` are `"-"` at
`loglevel = "info"`; those records are emitted by gunicorn's own handlers, never pass through
the Django `LOGGING` tree or the redactor, and there is no `logconfig_dict`. **No demonstrated
security exposure exists** — the redaction gap is a property of the *format*, not of any
parameter the application emits today. What remains is log-format consistency and aggregator
ergonomics.

**The rollout hazard is the whole reason this is a `behavioural` block.** ✔ `preload_app = True`
means the config module is imported by the master; a malformed `logconfig_dict` crashes the
arbiter **before** the bind, so the container never listens and the failure looks like a
deployment problem, not a logging problem.

**File surface (semantic units)**

| File | Target | Notes |
|---|---|---|
| `gunicorn.conf.py` | `accesslog`, `errorlog`, `loglevel`, `logconfig_dict`, `access_log_format` | **At the repository root**, auto-discovered because the runtime CWD is `/app` |
| `gunicorn.conf.py` | the `child_exit` hook | ✔ **Phase 01 `ENT-001` owns it. Do not remove, move or re-shape it** |
| `src/backend/apps/core/utils/json_logging.py` | `is_sensitive_key`, `redact_value`, `redact_string`, `RedactingJsonFormatter` | ✔ Read-only unless the formatter cannot serve a gunicorn record |

**Binding constraints**

1. **Do not remove phase 01's `child_exit` hook.** ✔ It is the guard for `ENT-001` (an arbiter
   kill when `PROMETHEUS_MULTIPROC_DIR` is unset). Phase 12 edits this file; it does not own it.
2. **Keep `accesslog` and `errorlog` set** — do **not** set them to `None` in this block. The
   report offers that as an alternative; doing both at once means a broken `logconfig_dict`
   produces silence instead of plaintext, which is a worse failure to diagnose. **Silence is a
   failure mode; plaintext is a diagnostic.**
3. **Verify in a throwaway container before it lands**, not on the production path. A config
   that has never been loaded by a gunicorn arbiter is an untested config.
4. **The formatter must actually apply.** The `logconfig_dict` handler must reference the same
   `RedactingJsonFormatter`, and the verification is a **rendered record** — assert that an
   access record carrying a sensitive-looking query parameter comes back redacted, not merely
   that the config parses.
5. **No new logging dependency, no new formatter class.** `RedactingJsonFormatter` already
   exists and is the point of reuse.
6. **`docs/ops/docker-deployment.md`'s "Production Logging" section is BLOCK 14's.** This block
   records what gunicorn now does; BLOCK 14 writes it down.
7. **This block changes no metric, no alert and no readiness probe.** It is log hygiene.

**Implementor task**

```yaml
id: task_12_b17_gunicorn_log_format
title: "Route gunicorn access and error logs through the redacting formatter (12-OPS-012)"
priority: low
depends_on: [task_12_b12_operator_notification]
source_reference: ".ai/plans/12-production-ops-remediation.md"
source_section: "BLOCK 17 - Route gunicorn's own logs through the redacting formatter"
source_blocks: ["BLOCK 17"]
description: >
  Production configures a structured LOGGING dict with RedactingJsonFormatter for the django and
  apps logger trees, but gunicorn's accesslog and errorlog are "-" at loglevel info and are
  emitted by gunicorn's own handlers. They never pass through the Django LOGGING tree or the
  redactor, and there is no logconfig_dict, so the highest-volume record type in production is
  unstructured plaintext. The security impact is speculative; the real gain is that a log
  aggregator can parse the stream uniformly.
goals:
  - "route gunicorn.access and gunicorn.error through RedactingJsonFormatter via logconfig_dict"
  - "give the access log a structured format with named fields instead of a raw request line"
  - "prove on a rendered record that a sensitive-looking parameter comes back redacted"
extra_context: |
  BINDING CONSTRAINTS
  1. DO NOT remove phase 01's child_exit hook in gunicorn.conf.py. It is the ENT-001 guard.
  2. KEEP accesslog and errorlog set. Do NOT set them to None in this block - a broken
     logconfig_dict would then produce silence instead of plaintext.
  3. Verify the config in a THROWAWAY CONTAINER before it lands. A config never loaded by a
     gunicorn arbiter is untested; preload_app means a malformed config crashes before the bind.
  4. The verification is a RENDERED RECORD - assert that an access record carrying a
     sensitive-looking parameter comes back redacted, not merely that the config parses.
  5. No new logging dependency and no new formatter class. Reuse RedactingJsonFormatter.
  6. This block changes no metric, no alert and no readiness probe.
  7. docs/ops/docker-deployment.md is BLOCK 14's; record the outcome for it rather than editing
     the doc here.
  FORBIDDEN: removing the child_exit hook; setting accesslog or errorlog to None; adding a
  logging dependency; editing the compose files.
files:
  - path: gunicorn.conf.py
    targets:
      - type: module_attribute
        name: logconfig_dict
      - type: module_attribute
        name: access_log_format
      - type: module_function
        name: child_exit
  - path: src/backend/apps/core/utils/json_logging.py
    targets: []
changes:
  - action: add_code
    description: >
      Add a logconfig_dict routing gunicorn.access and gunicorn.error at the existing
      RedactingJsonFormatter.
  - action: add_code
    description: >
      Add a structured access_log_format emitting named fields rather than a raw request line.
  - action: add_code
    description: >
      Add a test asserting a rendered gunicorn record is redacted.
acceptance_criteria:
  - "gunicorn.access and gunicorn.error both route through RedactingJsonFormatter"
  - "a rendered access record carrying a sensitive-looking parameter is redacted, and that is demonstrated"
  - "the config loads in a throwaway container without crashing the arbiter"
  - "child_exit is present and unchanged"
  - "accesslog and errorlog remain set"
  - "no new logging dependency or formatter class was added"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/apps/core/tests/test_prod_logging.py
```

---

### BLOCK 18 — Stop `/health/` from describing the dependency graph to the public (`OPS-020`)

| | |
|---|---|
| **Findings owned** | `OPS-020` (LOW) |
| **Class** | **conditional** — **the only backward-incompatible change in the phase**, and it is blocked until Q9 is answered |
| **Depends on** | BLOCK 13 (both change what the health surface says), BLOCK 15 |
| **Blocks** | nothing in-plan |
| **Priority** | **P3, and gated.** It is free to close and the last thing that should be done |
| **Risk level** | **HIGH for a LOW finding** — a wrong assumption takes an external uptime monitor dark |
| **Blast radius** | `docker/nginx/nginx.conf`, possibly `apps/core/views.py` and `apps/core/urls.py`, three test modules. **No compose file edit** |
| **Required agents** | **Auditor · Researcher · Planner · Validator** — all four |

**Blocking gate — Q9: does anything external consume `/health/`?** (the coordinator / owner, not
the Implementor)

✔ Nothing in the repository records an uptime monitor, a status-page integration, or a
`UptimeRobot` / `healthchecks.io` reference — **but absence of a record is not proof**, and the
report itself flags this as the one non-backward-compatible item in the phase. **Until the
answer is written down, this block does not start.** The in-repo half is answered; the external
half is a question to whoever operates the site.

**What is exposed.** ✔ nginx proxies `location /health/` with no `allow`/`deny` and no
`limit_req` — the block's own comment reads *"Health check endpoint (no rate limiting, no
auth)"* — while `location = /metrics` immediately below it correctly carries
`allow 127.0.0.1; deny all;`. The view returns `{"version": 1, "status": "ready", "checks":
{"database": "ok", "cache": "ok", "bot": "disabled"}}`, or when degraded, **exactly which of
database, cache and bot has failed**. An anonymous caller can read both service availability and
the identity of the failing dependency.

**Decision required before implementation — where the restriction is expressed.**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Restrict at nginx, exactly as `/metrics` is restricted — `allow 127.0.0.1; deny all;` plus a dedicated internal listener | **Gains:** one mechanism, one place, matching the file's existing precedent; **no Django change**; the deploy gate's `docker compose exec -T web curl http://localhost:8000/health/ready/` is unaffected because it does not traverse nginx. **Costs:** ✔ the container healthcheck targets `/health/live/`, and the deploy gate polls `/health/ready/` **from inside `web`** — both still work. But **any** external consumer stops, which is exactly what Q9 must rule out |
| **(b)** | Keep `/health/` reachable but return a **reduced public body** (`{"status": "alive"}`) and move the per-dependency breakdown to an internal-only path | **Gains:** a status probe keeps working; the dependency graph stops leaking. **Costs:** a Django change — new view, new route, `apps/core/urls.py` edits — and it makes the `/health/` alias no longer a backward-compatible alias of `/health/ready/`. **More surface for a LOW finding** |
| **(c)** | Restrict `/health/` like `/metrics` **and** expose a deliberately minimal public liveness alias | **Gains:** both properties — availability signal stays public, dependency detail does not. **Costs:** both costs above |

**The Implementor may not choose**, and **Q9 must be answered first regardless of which option
is selected.** Option (b) still changes an existing public response body, which is the same
compatibility question wearing a different hat.

**File surface (semantic units)**

| File | Target | Notes |
|---|---|---|
| `docker/nginx/nginx.conf` | the `location /health/` block; the adjacent `location = /metrics` block as the precedent | ✔ `src/backend/tests/test_nginx_config.py::_location_block` is a brace-depth extractor — the tool if the restriction is expressed here |
| `src/backend/apps/core/views.py` | `readiness_check`, `health_check` — **only under option (b) or (c)** | ✔ `health_check` is currently a backward-compatible alias that delegates to `readiness_check`; changing what it returns changes that contract |
| `src/backend/apps/core/urls.py` | the `health/`, `health/live/`, `health/ready/`, `health/v1/` routes | **Only under (b) or (c)** |
| `src/backend/apps/core/tests/test_health_contract.py` | the four route assertions | ✔ Already behavioural, with DB and cache mocked |
| `src/backend/tests/test_nginx_config.py` | the `/metrics` restriction assertions | The precedent the new guard copies |

**Binding constraints**

1. **Q9 is answered in writing before this block starts.** A non-answer is not an answer.
2. **`/health/live/` must remain reachable by the container healthcheck.** ✔ It is the target in
   both `docker/Dockerfile` and `docker-compose.yml` for three services. If it is restricted,
   the container is marked `unhealthy` and `restart: unless-stopped` begins a restart loop —
   **an availability outage created by a security fix.**
3. **The deploy gate runs from inside `web`.** ✔ `deploy.yml` polls
   `docker compose exec -T web curl … /health/ready/`, which does not traverse nginx. Verify
   this rather than assuming it — the gate must not start failing because of this block.
4. **`docker-compose.dev.override.yml` gates `nginx` behind `profiles: [use-nginx]`.** ✔ A dev
   stack without nginx bypasses nginx entirely, so the behaviour differs by topology. Say which
   topology each claim applies to.
5. **Do not change `/metrics`'s existing restriction.** It is correct and BLOCK 11's scrape
   contract depends on it.
6. **Prefer nginx over Django.** The exposure is a **proxy** property; the project already has
   the correct answer one block below in the same file. Expressing it in Django adds a view,
   a route and an alias-contract change for a LOW finding.

**Implementor task**

```yaml
id: task_12_b18_health_endpoint_exposure
title: "Stop /health/ from describing the dependency graph to the public (12-OPS-020)"
priority: low
depends_on: [task_12_b13_bot_readiness, task_12_b15_ops_docs_parity]
source_reference: ".ai/plans/12-production-ops-remediation.md"
source_section: "BLOCK 18 - Stop /health/ from describing the dependency graph to the public"
source_blocks: ["BLOCK 18"]
description: >
  nginx proxies location /health/ with no allow/deny and no rate limit - the block's own comment
  says so - while the /metrics block immediately below correctly carries allow 127.0.0.1 and
  deny all. The view returns the status of every dependency, so an anonymous caller can read both
  service availability and the identity of the failing dependency. This is the only
  backward-incompatible change in the phase.
goals:
  - "per the recorded option, restrict /health/ the way /metrics is restricted, or return a reduced public body with the breakdown on an internal-only path"
  - "confirm no external consumer depends on the current response before changing it"
extra_context: |
  BLOCKING GATE - Q9 MUST BE ANSWERED IN WRITING FIRST. "Does anything external consume
  /health/?" The repository records no uptime monitor, no status-page integration and no
  healthchecks.io reference, but absence of a record is not proof. A non-answer is not an answer.
  This is the only backward-incompatible change in the phase.

  BINDING CONSTRAINTS
  1. Q9 is answered before the block starts.
  2. /health/live/ must remain reachable by the container healthcheck - it is the target in
     docker/Dockerfile and docker-compose.yml for three services. Restricting it creates a
     restart loop, i.e. an availability outage created by a security fix.
  3. The deploy gate runs from inside web and does not traverse nginx. VERIFY that, do not
     assume it.
  4. docker-compose.dev.override.yml gates nginx behind profiles [use-nginx]; behaviour differs
     by topology. Say which topology each claim applies to.
  5. Do NOT change /metrics's existing restriction - BLOCK 11's scrape contract depends on it.
  6. Prefer nginx over Django. The exposure is a proxy property and the correct answer already
     exists one block below in the same file.
  FORBIDDEN: editing the compose files; changing liveness_check; removing the deploy health gate;
  editing the scheduler or backup service blocks.
files:
  - path: docker/nginx/nginx.conf
    targets:
      - type: nginx_location
        name: "/health/"
      - type: nginx_location
        name: "= /metrics"
  - path: src/backend/tests/test_nginx_config.py
    targets:
      - type: function
        name: _location_block
  - path: src/backend/apps/core/tests/test_health_contract.py
    targets: []
  - path: src/backend/apps/core/views.py
    targets: []
  - path: src/backend/apps/core/urls.py
    targets: []
changes:
  - action: update_code
    description: >
      Per the recorded option, express the restriction in nginx or reduce the public response body.
  - action: add_code
    description: >
      Add a guard that fails when /health/ is reachable without a restriction, modelled on the
      existing /metrics assertion.
acceptance_criteria:
  - "the Q9 answer is recorded in the commit body"
  - "the container healthcheck target remains reachable, and that is verified rather than assumed"
  - "the deploy health gate still passes, and that is verified rather than assumed"
  - "/metrics's existing restriction is unchanged"
  - "the new guard is red when the restriction is removed, and that failure is demonstrated"
  - "test_health_contract.py and test_nginx_config.py are green"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/tests/test_nginx_config.py
  - src/backend/apps/core/tests/test_health_contract.py
```

---

## 4. Dependency graph

### 4.1 Execution order (the safe serial order)

One Implementor, strictly sequential. Every block is one commit (§1.3). The numbering *is* the
order, and the order is chosen so that **one file is written by one phase-12 block per run**,
with the programme's highest blast-radius file written exactly once, first.

| # | Block | Findings | Class | Depends on (in-plan) | Gate | Risk |
|---|---|---|---|---|---|---|
| 1 | Healthcheck `start_period` | `OPS-019` | M | — | — | **MED** (programme-wide) |
| 2 | Backup container + prune convention | `OPS-014`, `OPS-021` (loop) | B | 1 | **Q4** | **HIGH** |
| 3 | Workflow wiring | `OPS-009`, `OPS-016`, `OPS-021` (comment) | M | 2 | — | LOW |
| 4 | SAST gate contract | `OPS-001` | B | 3 | — | **MED–HIGH** |
| 5 | Supply-chain pins | `OPS-017` | M | 4 | — | LOW / MED (Dockerfile) |
| 6 | `SENTRY_DSN` guard | `OPS-013` | M | 5 | — | MED (wide blast radius) |
| 7 | PgBouncer + capacity limits | `OPS-015`, `VAL-001` | B | 2 | **Q7** | MED |
| 8 | Prod service-set contract | `OPS-007` (+`OPS-005`) | **S** | 3, 7 | **Q1** | **HIGH** |
| 9 | Runbook executability | `OPS-006` | B | 8 | **Q2**, **Q3** | **HIGH** (irreversible data) |
| 10 | Deploy provenance | `OPS-002`, `OPS-008` | B | 8, 9 | **Q11**, **Q12** | **HIGH** |
| 11 | SLO alert contract | `OPS-003` | B | 10 | **Q5** | MED / **HIGH** under (a) |
| 12 | Operator-notification floor | `OPS-011` | B | 11 | **Q10** | MED |
| 13 | Bot readiness contract | `OPS-010` | B | 7 | **Q6** | MED |
| 14 | `docs/ops` truth sweep | `OPS-018` | B | 4, 9, 13 | — | LOW / HIGH consequence |
| 15 | `docs/ops` parity guard | `VAL-003` | M | **14**, strictly | **Q14** | MED |
| 16 | Restore drill | `OPS-004` | **C** | 2, 9, 10 | **Q8** | MED |
| 17 | Gunicorn log format | `OPS-012` | B | 12 | — | **HIGH** for a LOW finding |
| 18 | `/health/` exposure | `OPS-020` | **C** | 13, 15 | **Q9 (blocking)** | **HIGH** |

`M` = mechanical · `B` = behavioural · `S` = structural · `C` = conditional.

### 4.2 The DAG and why each edge exists

```
  (none) --> [1 start_period] --> [2 backup container] --> [7 pgbouncer + limits] --Q7
                 |                    |                        |
                 |                    |                        +--> [13 bot readiness] --Q6
                 |                    |                                     |
                 |                    +--> [8 service-set contract] --Q1    |
                 |                             |       |                   |
                 |                             |       +--> [9 runbooks] --Q2,Q3
                 |                             |                |          |
                 |                             |                v          v
                 |                             |          [10 deploy provenance] --Q11,Q12
                 |                             |                |                 |
                 |                             |                v                 v
                 |                             |          [11 SLO contract] --Q5   |
                 |                             |                |                   |
                 |                             |                v                   v
                 |                             +<-- [14 docs truth]              [12 notify] --Q10
                 |                                    ^                              |
                 |                                    |                              v
                 +--> [3 wiring] --> [4 SAST] --> [5 pins]                        [17 gunicorn]
                              \           |                                          ^
                               \          | (SAST paragraph)                       |
                                \         v                                          |
                          [8]   [14 docs truth] --> [15 parity guard] --Q14 --> [18 /health/] --Q9
                                                ^
                                                |
                                          [6 SENTRY_DSN]  [from 5]
```

**Each edge, with the reason it exists:**

| Edge | Kind | Why it exists |
|---|---|---|
| **1 → 2** | hard, file | Both write `test_compose_contract.py`. ✔ BLOCK 1's guard establishes the per-file, no-merge parse discipline; BLOCK 2's entrypoint-bypass detection needs it. **Reverse order means the entrypoint check is written against a parse helper that does not exist yet** |
| **1 → everything** | hard, gate | ✔ `docker-compose.yml` and `docker-compose.test.yml` are the base of all three stacks and the file `.\Makefile.ps1 test` reads. Every later block's fast gate depends on BLOCK 1's compose files being sound. It goes first so that a later block's failure is unambiguously its own |
| **2 → 3** | hard, file | ✔ `deploy.yml`'s pre-deploy `pg_dump` filename is BLOCK 2's; BLOCK 3 adds the workflow-level `concurrency` key and the coordinate outputs to the same file. Two owners of one file in one run is a review that can see both |
| **2 → 7** | hard, file | Both write `docker-compose.prod.yml` — BLOCK 2's `backup` block and BLOCK 7's `pgbouncer` block — and both write `test_compose_contract.py` |
| **3 → 4** | hard, file + gate | ✔ `ci.yml`. BLOCK 4's guard change depends on BLOCK 3's structural context: the job graph BLOCK 4 edits is the one BLOCK 3's coordinate outputs feed |
| **4 → 5** | hard, file | ✔ `ci.yml` again. **In-place edits only in both cases.** C-5 applies throughout: no job may be appended after `deploy-check:` |
| **5 → 6** | soft, ordering | No file overlap. BLOCK 6 is placed here so that the phase's last *in-place* `ci.yml` edit is complete before the structural work in BLOCKS 8–10 begins. **Soft** — BLOCK 6 would be correct in any position |
| **7 → 13** | hard, file | Both write `docker-compose.prod.yml` — BLOCK 7's `pgbouncer` block and BLOCK 13's `web` override. Running 13 first means its `environment:` change lands on a file a later block rewrites for capacity keys |
| **3, 7 → 8** | hard, file | BLOCK 8 rewrites the **same** compose invocations in `deploy.yml` that BLOCK 3 wired. The profile flags and the coordinate outputs must be read as one diff |
| **8 → 9** | hard, file | ✔ The report states the overlap explicitly: `OPS-006` and `OPS-007` both edit `deploy.yml` and `docs/ops/rollback.md`. BLOCK 8 changes the recreate commands; BLOCK 9 corrects the flags in the same commands and in `restore.md`. Sequentially there is no merge conflict, but there is one file and one review window — which is what the report's "merge them into one change" was protecting |
| **8, 9 → 10** | hard, file | ✔ `deploy.yml` has four phase-12 owners: BLOCK 2 (filename), BLOCK 3 (concurrency, coordinate), BLOCK 8 (profiles, service set), BLOCK 10 (input constraint, digest). **Structural last**, because BLOCK 10's assertion reads the image coordinate BLOCK 3 defined and the service set BLOCK 8 named |
| **10 → 11** | soft, ordering | No file overlap. Placed so the deploy path is settled before the observability work that depends on knowing what production runs. **Soft** — either order is correct |
| **11 → 12** | hard, dependency | ✔ Q10's options are defined **in terms of** Q5's answer: a notification floor needs a consumer, and if Q5 declined to deploy a stack then option (b) has nothing to feed. BLOCK 12 cannot be specified before BLOCK 11 |
| **4, 9, 13 → 14** | hard, dependency | ✔ The report's ordering is explicit: *"land the path fix, triage the findings, and **then** correct `docker-deployment.md:431-436`"*. Rewriting the doc first encodes either a wrong claim or a claim about a step that still fails. BLOCK 9 supplies the runbook flags; BLOCK 13 supplies the readiness criterion |
| **14 → 15** | hard, strict | ✔ The report's own warning: *"the parity test must not encode today's wrong claims as truth — write it only after the docs are corrected."* A guard written in the same commit as the correction is reviewed against the version it is meant to police. **There is no soft variant of this edge** |
| **2, 9, 10 → 16** | hard, file + dependency | ✔ `Makefile` is BLOCK 2's (`prune-backups`) and BLOCK 16's (`restore-test`). BLOCK 9's Q2 decision also rewrites the `restore` target. BLOCK 10 supplies the recorded image tag BLOCK 16 pins the drill to |
| **12 → 17** | soft, ordering | No file overlap. ✔ The report says `OPS-012` is *"a P2 item; do not let it compete with `OPS-007` for the same deploy window"* — placing it after the detection work satisfies that without creating a false dependency |
| **13, 15 → 18** | hard, dependency + external | ✔ Both change what the health surface says; Q9 must be answered; and the parity guard must already exist so that a restricted `/health/` does not immediately invalidate a documented claim |

### 4.3 Where there is deliberately **no** edge, and why

| Pair with no edge | Why |
|---|---|
| **1 ↔ 13** | BLOCK 13 may need to remove `BOT_HEALTH_STALE_SECONDS` from `docker-compose.yml` under Q6 option (b) — **that edit is reported, not made**, because BLOCK 1 owns the file. Making the edge would mean BLOCK 13 silently rewrites BLOCK 1's file mid-plan |
| **6 ↔ 7** | Both touch `config/settings/**` — BLOCK 6 `prod.py`, BLOCK 7 `base.py`. **Different files, different owners.** Phase 02 owns the surface as a whole; the coordinator sequences that, not this plan |
| **4 ↔ 14** (direct) | BLOCK 14 depends on BLOCK 4's SAST paragraph, but BLOCK 4 has no dependency on BLOCK 14. The edge exists in BLOCK 14's direction only |
| **11 ↔ 13** | Two observability decisions with different blast radii: one adds an alert contract, the other changes the deploy gate's failure model. Merging them would couple a rule file to a readiness probe |
| **17 ↔ everything** | `gunicorn.conf.py` has **one** phase-12 owner. Making it a hub would turn a P3 log-hygiene change into a serialisation bottleneck |
| **18 ↔ 12** | BLOCK 18 changes what a public caller can read; BLOCK 12 changes who gets told. Different consumers, different failure modes. If BLOCK 12 delivers over Telegram, its messages could arguably carry readiness detail — **that is an explicit note in BLOCK 12, not an edge** |
| **16 ↔ 8** | The report's constraint is *"off-host replication must land before `OPS-004`'s real-artifact drill can pass"*. ✔ **That constraint lives inside Q8, not between blocks** — BLOCK 8 makes the daily dump *start*; BLOCK 16 decides whether a real artifact can be fetched. Neither block's implementation requires the other's to have run |

### 4.4 The orders that are unsafe

1. **BLOCK 15 before BLOCK 14.** The parity guard is written against uncorrected
   documentation and institutionalises the false claims it was meant to prevent. This is the
   report's explicit warning and the plan's only non-negotiable edge.
2. **Any block editing `docker-compose.yml` or `docker-compose.test.yml` other than BLOCK 1.**
   ✔ These are the base of all three stacks; a mistake breaks `.\Makefile.ps1 test` for every
   phase, and the failure surfaces as an interpolation error, not a YAML error.
3. **BLOCK 9 before BLOCK 8.** Both rewrite the same `deploy.yml` compose invocations and
   `docs/ops/rollback.md`. The reverse order splits one file's diff across two unrelated
   commits and re-introduces the conflict the report warns about.
4. **BLOCK 2 after BLOCK 7 or BLOCK 13.** All three write `docker-compose.prod.yml`. BLOCK 2 is
   the one with a Q4 probe that must run before any edit, so it is early by construction.
5. **BLOCK 18 without the Q9 answer.** The only backward-incompatible change in the phase. A
   wrong assumption takes an external uptime monitor dark, and nothing in the repository would
   reveal it.
6. **BLOCK 4 before BLOCK 3.** BLOCK 3's coordinate outputs and BLOCK 4's `security` step are
   both in-place `ci.yml` edits; running 4 first means 3's diff is written against a file whose
   job graph has changed underneath it.
7. **Extending `_HARDENING_KEYS` with `user:`.** ✔ Not an ordering error but an ordering-
   adjacent one: it turns eleven green assertions red in BLOCK 2's own commit, in the file the
   fast gate reads. §7 records it.
8. **Appending a job to `ci.yml` after `deploy-check:`.** ✔ `_deploy_check_section()` slices from
   that marker to EOF; three shipped assertions break silently. Not an ordering error at all —
   an insertion-point error — but with the same blast radius.
9. **Any block restoring `.ai/audit/12-production-ops/findings.md`.** It is deleted; the
   validated report preserves the corrected evidence inline.

### 4.5 What the DAG does *not* decide

The DAG orders blocks. It does **not** resolve Q1 … Q14. Each is a gate inside a block, recorded
in that block's `extra_context` and in §0.5, and §8.1 checks that a **written** answer exists
for each. **A block whose gate is unanswered does not start, and the Implementor is forbidden
from choosing the option.**

The DAG also does not sequence phase 12 against the other phases. §5 does, from phase 12's
side only. **Phase 12 does not contact, negotiate with, or wait on any other agent** — the
coordinator sequences the cross-phase gates.

---

## 5. Cross-phase coordination

Plans `.ai/plans/01-…` through `.ai/plans/11-test-coverage-remediation.md` all exist; ✔ plan
**11 appeared while this plan was being written** (C-16) and is re-verified in §5.4. Phases
13–15 are still to be planned. This section is the boundary contract and is deliberately
**one-directional**: phase 12 states what it owns, what it will not touch, and where its
boundaries lie. It does **not** attempt to contact the other agents.

### 5.1 What phase 12 already owns and must not re-ship

| Prior work | What it shipped | Consequence for phase 12 |
|---|---|---|
| **Phase 01 `ENT-001`** | ✔ `gunicorn.conf.py::child_exit` guard | BLOCK 17 edits that file and **must not remove, move or re-shape the hook** |
| **Phase 01 `ENT-002`** | ✔ Interruptible, bounded scheduler stop | BLOCK 8 recreates the scheduler container; the bounded stop is what makes that safe |
| **Phase 01 `ENT-003`** | ✔ Durable daily marker + `send_alerts` idempotency | **OPS-007's rollout constraint is discharged.** BLOCK 8 lands without waiting. Do not add a second dedupe mechanism |
| **Phase 01 `ENT-005` / `ENT-013`** | ✔ `docker/healthcheck-bot.sh`, `healthcheck-scheduler.sh`; the scheduler healthcheck with `start_period: 600s` | ✔ BLOCK 2's `healthcheck-backup.sh` **follows this shape**; BLOCK 1 must not regress the scheduler's `start_period` |
| **Phase 01 `ENT-011` / `ENT-012`** | ✔ `stop_grace_period` contract; the dev `bot`/`seed` asymmetry | ✔ Locked by `test_compose_contract.py`. **BLOCK 1 adds guards beside these, not over them** |
| **Phase 01 `ENT-004`** | ✔ CI lint/typecheck scoped to `src/` | The bot is inside both gates; **no phase-12 precondition is unmet here** |
| **Phase 02 `CFG-002`** | ✔ `ci.yml`'s `deploy-check` env block + `test_deploy_check_env_parity.py` | ✔ **OPS-002's gate precondition is met.** BLOCK 3 must not modify that `env:` block; BLOCK 10 relies on the gate actually executing |
| **Phase 02 `CFG-001`** | ✔ `ALLOWED_ENV_VARS` + the `DJANGO_ONESHOT` import gate | ✔ BLOCKS 7, 12 and 13 add env keys and **must** add them to the allowlist in the same commit. BLOCK 13's key is already there |
| **Phase 02 (`OPS-021` comment limb)** | ✔ The `deploy-check` rationale comment relocated and extended | ✔ Only the stale `OPS-001` citation remains — BLOCK 3's, and nothing else |
| **Phase 02 `CFG-004`** | ✔ `EMAIL_BACKEND` pin and the closed transport set | **Conditioned on an activation decision that was never triggered.** Phase 12 assumes neither landed and touches neither |
| **Phase 09 `API-009`** | ✔ The sole `send_mail` call site and the speculative "password reset" justification for `EMAIL_HOST` | ✔ **Removed from phase-12 scope.** BLOCK 12 must not re-file it, must not add a second sender, and must not touch `EMAIL_HOST` |
| **Phase 08 `SRCH-001`** | ✔ The OOM consequence of an unbounded `?features=` join | ✔ `VAL-001` owns only "the ops layer declares no capacity limits". **Cross-reference; never merge.** BLOCK 7's commit body says which half it fixed |
| **Phase 03 `DB-004`** | ✔ `lock_timeout` / `statement_timeout` on the application side | ✔ `VAL-002` owns only the one-shot-container / scheduler-dispatch side. **§6.1** |
| **Phase 05 `AD-008`** | ✔ `get_pending_queue_size()` is structurally 0 | ✔ **Carry the warning into BLOCK 11.** No moderation-queue-depth alert, ever |
| **Phase 11 `TEST-002`** | ✔ `[tool.coverage.*]` never loaded | Same "configured but ineffective gate" cluster as `OPS-001`. **No overlap** |
| **Phase 10 `CQ-017.3`** | ✔ the `AdvisoryLockId` reorder was **de-scoped** | ✔ Consistent with Q13: phase 12 allocates no lock id |

### 5.2 What phase 12 must **not** do, for other phases' sake

1. **Do not edit `docker-compose.yml` or `docker-compose.test.yml`** outside BLOCK 1. ✔ They are
   the compose/test-command contract **every other phase depends on**; a break is felt by all of
   them, not by phase 12.
2. **Do not append a job to `.github/workflows/ci.yml` after `deploy-check:`.** ✔
   `_deploy_check_section()` slices from that marker to EOF.
3. **Do not change `ci.yml`'s `deploy-check` `env:` block.** ✔ Phase 02 owns it, and
   `test_deploy_check_env_parity.py` proves the prod settings import from it with two negative
   controls.
4. **Do not change an existing `ALLOWED_ENV_VARS` entry beyond adding the keys this plan
   introduces, and never remove one.** ✔ Five phases read that surface.
5. **Do not remove phase 01's `child_exit` hook** from `gunicorn.conf.py` (BLOCK 17).
6. **Do not allocate or renumber an `AdvisoryLockId`.** ✔ Next free is `14`; phases 03/05/06/07/10
   all list `apps/core/enums.py` as contended. Q13.
7. **Do not touch `apps/core/services/scheduler_daily_state.py` or the `SchedulerDailyState`
   model.** ✔ Read-only reference for BLOCK 8.
8. **Do not change `src/backend/conftest.py`, the scheduler's command set, or its cadence.** ✔
   `test_scheduler_error_handling.py`, `test_scheduler.py` and `test_scheduler_wiring.py` gate
   all three.
9. **Do not restore or edit anything under `.ai/audit/`.** ✔ Only the plan file is phase 12's.
10. **Do not edit `docs/01-spec/technical-specification.md` or any other phase-06-held
    document.** ✔ Phase 06 holds the technical specification.
11. **Do not deploy or reconfigure a Prometheus/Grafana stack** without Q5's answer, and do not
    add one to the **base** compose file under any circumstance.

### 5.3 Shared-artefact reservations

The coordinator sequences these. Phase 12's claim is stated so it can be compared; **phase 12
does not negotiate.**

| Artefact | Phase-12 claim | Other claimants | Ordering rule |
|---|---|---|---|
| `docker-compose.yml` | **BLOCK 1 only** — `start_period` on `db` and `redis` | Every phase's test command, transitively | **Phase 12 first among phase-12 work.** Any other phase editing it must re-read after BLOCK 1 |
| `docker-compose.test.yml` | **BLOCK 1 only** — `start_period` on `db` | The `test` service itself | **Same.** The `db` override is the file the fast gate reads |
| `docker-compose.prod.yml` | BLOCK 2 (`backup`), BLOCK 7 (`pgbouncer`), BLOCK 8 (read), BLOCK 11 (`prometheus`, under Q5(a)), BLOCK 13 (`web`) | Phase 01 and 02 both edited it | **Sequential within phase 12**: 2 → 7 → 11/13. Re-read before each |
| `.github/workflows/ci.yml` | BLOCKS 3 → 4 → 5, all in-place | ✔ **Phase 11 BLOCKS 2 and 3** (`--cov` shape, `timeout-minutes`), phase 09 BLOCK 15, phase 02 (`deploy-check`) | **Never append after `deploy-check:`.** Phase 12 edits the `on:` block, the `build` job, the `security` job and top-level keys; **phase 11 edits the `pytest` and `test` jobs** — disjoint regions, but **sequential with a re-read before each edit**. Phase 02's `env:` block is read-only for both |
| `.github/workflows/ci-nightly.yml` | **None** | ✔ **Phase 11 BLOCK 2** — *"the first phase to touch `ci-nightly.yml`; no other plan claims it"* | **Phase 12 does not touch it.** Note that `ci-nightly.yml` already has the `concurrency` shape BLOCK 3 copies |
| `config/settings/test.py` | **None** | ✔ Phase 11 BLOCK 5 (the test-side `statement_timeout` bound) | **Phase 12 does not touch it.** It is phase 11's, and it is gated on phase 03's `DB-002`/`DB-004` |
| `.github/workflows/deploy.yml` | BLOCKS 2 → 3 → 8 → 10 | — | Sequential. **Structural last** |
| `src/backend/tests/test_compose_hardening.py` | BLOCKS 1, 2, 8 | Phase 01 (`_ONE_SHOT_SERVICES`, the entrypoint assertions) | Sequential; `_HARDENING_KEYS` and `_ONE_SHOT_SERVICES` are **never renamed or removed** |
| `src/backend/tests/test_compose_contract.py` | BLOCKS 1 → 2 → 7 → 11 → 13 | Phase 01 (the Prometheus variable+tmpfs **pair** assertion, `stop_grace_period`) | Sequential. **The variable/tmpfs pair assertion is phase 01's** — do not restate it |
| `src/backend/tests/test_deploy_workflow.py` **and** `src/backend/apps/core/tests/test_deploy_workflow.py` | BLOCKS 8, 10 | — | **Both updated in the same commit.** They are duplicates for the same file |
| `src/backend/apps/core/tests/test_ci_security.py` | BLOCKS 3, 4, 5 | Phase 02 (the deploy-check block) | **`_deploy_check_section()`'s EOF slice is never extended** |
| `src/backend/apps/core/tests/test_health_contract.py` | BLOCKS 13, 18 | Phase 01 (the scheduler healthcheck and both `BOT_HEALTH_CHECK_ENABLED` branches) | **Extend; never rewrite** |
| `apps/core/tests/test_observability.py` | BLOCK 11 | Phase 01 (the multiprocess contract) | **Add the scrape contract beside `test_metrics_endpoint`; do not disturb the multiproc assertions** |
| `src/backend/apps/core/tests/test_scheduler_daily_marker.py` | — | Phase 01 (`ENT-003`) | **Phase 12 does not touch it.** BLOCK 8's scheduler change is compose-side only |
| `config/settings/tests/test_prod_logging.py` | BLOCK 6 | ✔ **Phase 02, via `_prod_env_overrides` consumers** | **The most contended settings-test file in the project.** Run the **whole** `config/settings/tests` package, never a subset |
| `config/settings/tests/test_env_allowlist.py` | BLOCKS 7, 12, 13 | Phase 02 (the allowlist itself) | Reads in **both** directions. A key added to one side without the other is a red gate |
| `config/settings/tests/test_deploy_check_env_parity.py` | **Read-only** | Phase 02 | ✔ Never modified by phase 12 |
| `src/backend/tests/test_docs_ci_parity.py` | BLOCKS 9, 15 | Phase 01 (`test-recreate` Makefile/PS1 parity) | Sequential; the existing `test-recreate` assertion is **extended, never replaced** |
| `config/settings/prod.py` | BLOCK 6 only | **Phase 02 owns the file** | One phase-12 block; re-read before editing |
| `config/settings/base.py` | BLOCKS 7, 11 (both gated), 12 | Phase 02 (the allowlist), phases 06/07/08 | **Re-read immediately before editing. Stop and report on a concurrent change** |
| `gunicorn.conf.py` | BLOCK 17 only | Phase 01 (`child_exit`) | One phase-12 owner; `child_exit` is untouchable |
| `Makefile` | BLOCKS 2, 9, 16 | Phase 02 (`restore`) | Sequential. **`COMPOSE_PROD` is not dead code** — it is BLOCK 8/9's candidate home |
| `Makefile.ps1` | BLOCKS 2, 9 | Phase 02 (the `test-recreate` parity assertion) | Sequential; **no `restore-test` target is added** (§6.1) |
| `docker/nginx/nginx.conf` | BLOCK 18 | Phase 01 (the `/metrics` restriction) | `/metrics` is untouchable |
| `docker/Dockerfile` | BLOCK 5 (syft, Tailwind) | Phase 01 (`USER app`, SBOM, healthcheck scripts, `chmod +x`) | **The SBOM step and the two `chmod +x` lines are phase 01's.** BLOCK 2 adds one line to the existing `chmod` |
| `docs/ops/**` | BLOCKS 9, 11, 12, 14, 15, 16 | — | Sequential: 9 → 14 → 15 |
| `docs/01-spec/technical-specification.md` | **None** | **Phase 06 holds it** | ✔ Phase 12 does not touch it |
| `docs/99-agent/architecture.md`, `docs/99-agent/rules.md` | BLOCK 14, conditionally | Phase 06 | Only if a topology statement changed in this phase |
| `apps/core/enums.py` | **None** | **Phases 03/05/06/07/10** | ✔ Q13: **phase 12 allocates no lock id and reorders nothing** |
| `apps/core/migrations/` | **None** | Phase 01 (`0005_*`), phase 02 (considered `0005_*`) | ✔ **This plan ships no migration.** If one appears, the next free number is `0006_*` — **check the directory immediately before generating** |

### 5.4 Phase 11 — verified, and what phase 12 will not do for its sake

✔ `.ai/plans/11-test-coverage-remediation.md` appeared while this plan was being written
(C-16). It is readable and anchored at `6413df5`, the same anchor. Phase 12 states its
position against it **without asserting anything it did not verify**:

1. **The Docker test-command contract in §1.1 is identical in both plans.** Phase 11 quotes
   the same `$dc` alias, the same `--env-file .env.test` requirement, the same "never
   `--override-ini=addopts=`" rule and the same warning about concurrent runs colliding on one
   `test_mko_bazuna`. **Phase 12 did not invent it and does not change it.** If either plan's
   contract changes, the other's block obligations still hold — the gate is whatever the
   current contract says.
2. **Phase 12 does not run a repository-wide test-coverage sweep, does not add tests to modules
   it does not change, and does not consolidate or restructure existing test files.** Every test
   phase 12 adds exists because a shipped guard could not detect the control it described
   (`VAL-003`), and each names the finding it closes.
3. **Phase 12 does not raise or lower `fail_under`, and does not change how
   `[tool.coverage.*]` is loaded.** ✔ `11-TEST-002` is phase 11's, and it is explicitly
   *"a gate that has never fired beginning to fire"* — a real behaviour change on CI, owned by
   one plan. Phase 12 changes CI for other reasons.
4. **Phase 12 does not touch `config/settings/test.py`, `ci-nightly.yml`,
   `src/backend/conftest.py`, or `[tool.pytest.ini_options]`.** ✔ All four are phase 11's.
   `src/backend/conftest.py` was already read-only for phase 12 (§5.2 item 8).
5. **`ci.yml` is the one genuine overlap.** Phase 11 BLOCK 2 edits the `pytest` step's `--cov`
   flags; phase 11 BLOCK 3 adds `timeout-minutes` to the `test` job. Phase 12 BLOCK 3 edits the
   `on:` block and the `build` job; BLOCK 4 edits the `security` job's SAST step; BLOCK 5 pins
   third-party action references. **These are disjoint regions of one file**, so the rule is
   **sequential with an immediate re-read before each edit** — not a merge conflict and not a
   barrier. Phase 12 does not negotiate the order; the coordinator sequences it.
6. **Phase 11 reads `test_docs_ci_parity.py` and `test_ci_security.py` for a workflow-claim
   baseline and edits neither.** ✔ That is directly compatible with phase 12's BLOCK 15 (which
   extends the first) and BLOCKS 3/4/5 (which edit the second). **No collision.**
7. **Phase 12 does not move a test between packages.** ✔ `test_deploy_workflow.py` exists in
   **two** packages — a genuine duplication — and phase 12's choice is to **update both in the
   same commit**, not to consolidate. Consolidating a test file is a coverage-phase decision.
8. **Phase 12 does not raise the retry or timeout behaviour of the suite**, and adds no test
   that depends on a `statement_timeout` bound phase 11 has not yet landed.

### 5.5 What phase 12 needs from other phases (forward dependencies)

| Need | From | Status |
|---|---|---|
| Nothing to wait for | — | ✔ **Both of the report's external sequencing constraints are discharged**: `CFG-002` (phase 02) landed, and `ENT-003` (phase 01) landed. **No phase-12 block is blocked on another phase's execution** |
| A production-host observation | Operator | §0.2.3 items 5, 6, 8. None blocks a block's *implementation*; all are verification |
| The Q5, Q8, Q10, Q11 answers | Owner | **These are the phase's real external dependencies**, and all four are recorded as decisions, not tasks |
| The Q9 answer | Coordinator / owner | **Blocks BLOCK 18 only** |
| `technical-specification.md` untouched | Phase 06 | ✔ Phase 12 holds `docs/ops/**` and does not touch phase 06's file |

---

## 6. Out of scope for this plan

Every de-scoping below is **routed**, not dropped. A de-scoped item with no destination is a
re-filed finding.

### 6.1 De-scoped by design (deliberately not done here, with the rationale)

| Item | Why |
|---|---|
| **Deploying a Prometheus / Alertmanager / Grafana stack** (`OPS-003`, Q5(a)) | A **new long-lived service**, a new configuration file, a new volume-or-tmpfs decision and a secret surface. It changes the block's size by an order of magnitude and **couples two gates**: BLOCK 8's service-set guard would immediately require the new service to be named in the deploy path. Project rules 5 and 7 argue against landing an infrastructure decision inside a remediation block. **Routed to the owner as Q5**, with option (c) — ship the guard that makes a later deploy safe — as the Planner's recommendation |
| **Off-host backup replication** (`OPS-005`'s demoted limb, and `OPS-004`'s real-artifact half) | The validator explicitly demoted it: *"single-host, same-volume, no off-host replication is a design choice appropriate to a single-host Compose deployment, not a defect."* It requires new credentials, a new external dependency, retention policy and a restore path that reads from it. **Routed to the owner as Q8.** BLOCK 16's unconditional half ships either way and BLOCK 8's commit body says the daily dump now *starts* but does not survive host loss |
| **`scripts/ops/*.sh`** (`OPS-006`'s structural half) | ✔ No precedent in the tree and **no shell-lint harness** (C-8). It is a new capability, not a patch, and it would be landed from a HIGH finding whose core is a missing flag. **Routed as Q3** to BLOCK 9, where it is one of three options with its consequences written down — **not** assumed |
| **A `manage.py notify_operator` Telegram command** (`OPS-011`, Q10(a)) | Needs a recipient key that does not exist, across `ALLOWED_ENV_VARS` and four example files; it would introduce a **second sender** adjacent to the support-desk mail that phase 09's `API-009` is examining; and it runs inside a `read_only: true`, `cap_drop: ["ALL"]` container. **Routed to the owner as Q10.** The *labelling* half of `OPS-011` — the SLO artefacts must stop reading as active controls — is unconditional and lands in BLOCKS 11/12 |
| **Adopting `user:` as a policy across every service** | The finding is about **one** service. A blanket policy would put `user:` on `db` (whose privilege drop is the image entrypoint's job), on `nginx` (which needs its capabilities) and on every one-shot. Project rule 7. BLOCK 2 asserts `user:` **or a justified exception** per service, and nothing more |
| **Documenting the PgBouncer profile as available** (`OPS-015`) | ✔ The report's instruction, and the reason the defect stayed latent: *"do not spend effort documenting the profile as available until someone intends to use it — documenting an unused profile is how the current latent state became invisible."* The block ships the configuration fix and **leaves the profile undocumented** |
| **Adding a `restore-test` target to `Makefile.ps1`** | ✔ `Makefile.ps1` has none today (C-15), and `restore-test.yml` runs on `ubuntu-latest` calling `make`, so this is **not a live defect**. ✔ The `Makefile`/`Makefile.ps1` parity precedent exists (`test_makefile_test_recreate_opts_match`), so adding one would be *consistent* — and is **scope the report did not ask for**. BLOCK 16 therefore has no parity obligation and adds nothing |
| **`VAL-002` — the ops-surface statement/lock-timeout item** | ✔ Zero matches for `lock_timeout` / `statement_timeout` in the one-shot containers or the scheduler's child dispatch. The application-side consequence is **phase 03's `DB-004`**; the ops-side consequence — a stuck `pg_dump` is indistinguishable from a slow one — is partly closed by BLOCK 2's freshness healthcheck. The **remainder** (an explicit timeout *budget* per one-shot container) is a design decision that interacts with `DB-004` and belongs with it. **Routed to phase 03** with the intersection recorded in §5.1. Phase 12 adds no timeout |
| **In-place migration of every `docs/ops/` runbook to script form** | The report proposes it and this plan gates it (Q3), but it is a **different project**: restucturing nine operational documents, adding a CI job, and changing how an engineer works at 3 a.m. The finding is a missing flag. The flag ships; the migration is a decision |
| **A `make ops-check` target** (report advisory 4) | ✔ A genuinely good idea, but it is **advisory**, it aggregates work that the eighteen blocks already ship, and it would add a `Makefile.ps1` parity obligation in the same commit as BLOCK 2's and BLOCK 16's Makefile edits. **Routed as a follow-up** once the individual guards exist and their shape is known |
| **An ops control inventory** (report advisory 2) | A "declared control → where → how verified → is it effective" table is exactly the artefact BLOCKS 14 and 15 collectively produce. Building it separately would duplicate both |
| **`AdvisoryLockId` reordering or a new lock id** | ✔ Q13: next free is `14`; the file is held by **five** phases. Phase 12 allocates none and reorders nothing |
| **Rewriting `apps/core/utils/swr_cache.py`** (`OPS-001`'s `B403`) | A pickle usage in one module. Rewriting a cache is a design change; the finding is a *suppression decision*, and BLOCK 4 records it as a decision |
| **Changing `BOT_HEALTH_STALE_SECONDS` in `docker-compose.yml`** directly | ✔ It is BLOCK 1's file. Under Q6 option (b) the edit is **reported**, not silently made by BLOCK 13 |
| **Re-filing `OPS-011`'s `EMAIL_HOST` limb** | ✔ A **duplicate of `API-009`** (phase 09), removed by the validator. `docs/ops/` contains zero "password reset" occurrences, so there is no ops-side instance. **Routed to phase 09** |
| **A new schema for alerting state** | Nothing in this plan writes to the database. No migration, no model, no admin |

### 6.2 Rostered elsewhere, not dropped

| Item | Owner | Note |
|---|---|---|
| `API-009` — the `send_mail` call site and the `EMAIL_HOST` justification | Phase 09 | ✔ Removed from phase-12 scope; BLOCK 12 must not re-file it |
| `SRCH-001` — the cgroup OOM consequence of an unbounded `?features=` join | Phase 08 | ✔ `VAL-001` owns only the capacity-limit declaration. **Cross-reference, never merge** |
| `DB-004` — application-side `lock_timeout` / `statement_timeout` | Phase 03 | ✔ `VAL-002`'s remainder is routed here |
| `AD-008` — `get_pending_queue_size()` is structurally 0 | Phase 05 | ✔ **Carried into BLOCK 11** as a warning against a dead-on-arrival alert |
| `ENT-003` — the durable daily marker | Phase 01 | ✔ Shipped. `OPS-007`'s sequencing constraint is discharged |
| `ENT-001` — the gunicorn `child_exit` guard | Phase 01 | ✔ BLOCK 17 edits the same file and must not remove the hook |
| `CFG-002` — the `deploy-check` env block | Phase 02 | ✔ Shipped. `OPS-002`'s precondition is discharged |
| `TEST-002` — `[tool.coverage.*]` never loaded | Phase 11 | ✔ Same cluster, no overlap. §5.4 |
| `OPS-005`'s off-host replication limb | Owner (Q8) | Demoted to advisory by the validator; absorbed into BLOCK 16's conditional half |
| `OPS-004`'s real-artifact drill | Owner (Q8) | ✔ **Cannot be closed without off-host replication.** BLOCK 16 says so in its commit body under options (b) and (c) |

### 6.3 Explicitly forbidden while implementing

1. Editing `docker-compose.yml` or `docker-compose.test.yml` outside **BLOCK 1** — and under
   Q6 option (b), editing them *at all* in BLOCK 13 (report it instead).
2. Adding a job to `.github/workflows/ci.yml` after `deploy-check:`, or extending
   `_deploy_check_section()`'s EOF slice without saying so in the commit body.
3. Modifying `ci.yml`'s `deploy-check` `env:` block.
4. Adding `user:` to `_HARDENING_KEYS`, or renaming/removing `_HARDENING_KEYS`,
   `_ONE_SHOT_SERVICES`, `_COMPOSE`, `_PROD_COMPOSE` or `_DEV_OVERRIDE_COMPOSE`.
5. Creating a bandit **baseline** file of any kind, or an exclusion that swallows a class
   silently.
6. Removing, moving or re-shaping `gunicorn.conf.py::child_exit`, or setting
   `accesslog`/`errorlog` to `None`.
7. Restoring, creating or editing anything under `.ai/audit/`, including
   `.ai/audit/12-production-ops/findings.md`.
8. Editing `docs/01-spec/technical-specification.md` or any other phase-06-held document.
9. Adding an `AdvisoryLockId` member, renumbering an existing one, or reordering the enum.
10. Writing a migration, editing an applied migration, or adding a model.
11. Editing `src/backend/conftest.py`, `apps/core/services/scheduler_daily_state.py`, or the
    `SchedulerDailyState` model.
12. Adding a moderation-queue-depth alert, a `pending_moderation` metric rule, or any
    `AD-008`-derived signal.
13. Adding a second `send_mail` call site, or touching `EMAIL_HOST` / `EMAIL_BACKEND` /
    `DEFAULT_FROM_EMAIL`.
14. Adding a moderation, alerting, notification or monitoring **framework**, plugin mechanism,
    registry or base class.
15. `ruff check --fix` over anything other than the files the current block edits; `ruff format`
    (not the project convention); any import reordering in a file the block did not touch.
16. Running a test on the host (`uv run pytest` always fails — §1.1), or setting
    `--override-ini=addopts=`.
17. `git reset` / `git checkout` / `git restore` / `git stash` / `--amend` / force-push, or
    reverting a file another agent changed.
18. Committing without an explicit instruction; committing more than one block in one commit;
    `git add -A` or `git add .`.
19. Writing a test that asserts a line number, a template-string substring, a literal private
    name, or the mere presence of a symbol (§1.5).
20. Adding `shellcheck`, `yamllint` or any new lint dependency (§1.2).
21. Deleting a shipped source-inspection test to make a block green.
22. Enabling `BOT_HEALTH_CHECK_ENABLED` without the Q6 answer recorded.
23. Deploying a `prometheus`, `grafana` or `alertmanager` service without the Q5 answer.

---

## 7. Per-block risk register

Severity here is **this Planner's assessment of execution risk for the change**, not the
finding's severity. "Blast" covers what else feels the change. "Contention" covers shared files.
"Behaviour" covers observable response changes. "Corpus" covers global or cross-cutting edits.

| Block | Risk | Kind | Likelihood | Impact | Mitigation / detection | Residual |
|---|---|---|---|---|---|---|
| **All** | An implementor works from the **report's** file list and "fixes" `rollback.md`'s already-correct `--env-file` lines, or reintroduces the refuted `bazuna_db` claim | Process | Med | **High** | C-10 and the block constraints; §6.3 items 3/8; both are in `extra_context` | Very low |
| **All** | A block runs with its gate unanswered, or the Implementor silently picks an option | Process | Med | **High** | Every gate is a labelled block in §3 and a row in §0.5, repeated verbatim in the task YAML's `extra_context`; §8.1 checks a written answer exists for each | Low |
| **All** | A block's tests are **asserted** rather than **run**, or run on the host where there is no database | Process | Med | **High** | Every block names its exact Docker gate command; tests run **only** through the `test` service (§1.1) | Low |
| **All** | A red gate is captured while another phase agent runs and a teardown race is reported as a product defect | Process | **High** | Med | Concurrent runs collide on one `test_mko_bazuna`. Re-run serially before reporting. The symptom is `test_mko_bazuna does not exist` / `relation "..." does not exist` | Low |
| **All** | A blanket `ruff check --fix src/` reorders imports another phase's uncommitted work depends on | Process | Med | Med | `[tool.ruff] fix = false` is set deliberately; §1.2 and §6.3 item 15 scope `--fix` to the block's own files | Low |
| **All** | A new guard is added and never observed failing, reproducing `VAL-003` in the guard that exists to close it | Quality | **High** | **High** | 0.2.2 item 4 and §1.5; **every** new guard's acceptance criteria include "and that failure is demonstrated" | Low |
| **All** | An ops guard is written at string level, so it passes when the control is inert | Correctness | Med | **High** | §1.5's substitution table; the `test_metrics_endpoint` model | Low |
| **All** | The phase's own evidence is trusted without re-derivation | Process | Med | **High** | ✔ `VAL-003`: the source report's runtime transcript was fabricated. §0.2.3 requires the exact command, image and working directory next to every number | Low |
| **All** | A phase-02-owned or phase-01-owned file is edited on a stale read | Contention | **High** | Med | Re-read immediately before editing; stop and report on a concurrent change; never stage by directory. Normal for `config/settings/base.py`, `prod.py`, `ci.yml`, `gunicorn.conf.py` | Med — accepted |
| **1** | A syntax or interpolation error in `docker-compose.yml` breaks **every** phase's fast gate | **Blast** | Low | **High** | Additive keys only; `config --services` renders before and after; the fast gate runs immediately after the block | Very low |
| **1** | The `docker-compose.test.yml` edit flakes the gate by making `db` healthy too late | Behaviour | Med | **High** | A **larger** `start_period` can only delay the "healthy" transition; the `test` service waits on `condition: service_healthy`, so this is a latency change, never a readiness loss. Bound it: the value must not exceed a minute | Low |
| **1** | The guard merges compose files with their overrides and mis-asserts on `!reset` / `!override` | Correctness | Med | Med | Constraint 2; `test_compose_contract.py::_load_yaml` is the precedent | Very low |
| **1** | The guard is written to parse only the base file and misses the test override | Quality | Med | Med | The guard's file list is explicit; deleting a `start_period` from the test override must turn it red — demonstrated | Very low |
| **2** | `user: postgres` cannot write to the `./backups` bind mount and **the daily dump silently stops** | **Correctness** | Med | **High** | Q4's probe runs before the edit; the new healthcheck makes the failure *visible* within one window; BLOCK 12's floor (Q10) is what makes it *notified* | Med — accepted, by decision |
| **2** | Extending `_HARDENING_KEYS` turns **eleven** green assertions red | Correctness | **High** | Med | ✔ Constraint 1; the list is named in `extra_context` and §7; the acceptance criteria require the constant to be byte-identical | Very low |
| **2** | The exception list becomes a silent opt-out | Quality | Med | Med | Every exception entry carries a reason and a failing guard for a reason-less entry | Low |
| **2** | The prune-convention fix is applied to one site and the `backup-*.dump` leak remains | Correctness | Med | **High** | Constraint 3 names all four producers/pruners; the acceptance criteria list a `backup-*.dump` fixture through each site | Low |
| **2** | Drift compensation shortens the interval below a day | Behaviour | Low | Med | Constraint 5; the loop must still sleep and the total must remain 24 h | Very low |
| **2** | The Q4 probe touches the operator's `.env.prod` | **Data** | Low | **High** | Constraint 7: key names only, placeholder values, a scratch directory; **never a production host** | Very low |
| **3** | A new job is appended after `deploy-check:` and three shipped assertions break | Correctness | Low | Med | ✔ C-5; constraints 3 and 4; the `ci.yml` assertion is byte-identical | Very low |
| **3** | `cancel-in-progress: true` on `ci.yml` cancels a build a required status check depends on | Correctness | Med | **High** | Constraint 2; the choice and its reason must be in the commit body; the existing `ci-nightly.yml` shape (`false`) is the model for deploy | Low |
| **3** | Fixing the coordinate makes the `cache-from` / `cache-to` mismatch *visible* as a cold-cache regression | Behaviour | Med | Low | That is the fix working. Record the before/after in the commit body | Very low |
| **4** | The corrected scan surfaces 114 findings and the `security` job goes red on arrival | Behaviour | **High** | Med | Expected. The commit body records the class each residual belongs to and why it is not yet triaged. **A silently narrowed threshold is not an acceptable resolution**; a red gate is the honest state | Low |
| **4** | The `exclude_dirs` repair is over-broad and hides a production directory | Security | Med | **High** | Constraint 3: narrow to the real test trees only; the acceptance criteria require the exclusion list to name production paths nowhere | Low |
| **4** | A `# nosec` is added to silence a Medium `mark_safe` finding | **Security** | Med | **High** | Constraint 7; the triage table marks `B703`/`B308` as "individual review and fix", never suppressed | Low |
| **4** | The SAST paragraph in `docker-deployment.md` is corrected before the fix lands | Process | Med | **High** | The 4 → 14 edge exists for this; BLOCK 14 says *"if BLOCK 4 did not land, delete the paragraph rather than restate it"* | Very low |
| **5** | A wrong `Dockerfile` checksum breaks **every** image build, including every other phase's | **Blast** | Med | **High** | Verify against the upstream published checksum file and record the command; constraint 2 | Low |
| **5** | Pinning `syft` changes the SBOM schema and breaks CI's SBOM assertion | Behaviour | Med | Med | Constraint 5; say so rather than widening the assertion | Low |
| **5** | A pin is added without a version comment and Dependabot cannot bump it | Quality | Med | Low | Constraint 1 | Very low |
| **6** | A `BadDsn` guard is written as a broad `except Exception` and swallows a real misconfiguration | **Correctness** | Med | **High** | Constraints 2 and 3; the acceptance criteria reject a broad except explicitly | Low |
| **6** | The log message leaks part of the DSN | **Security** | Low | **High** | Constraint 1; the acceptance criteria require the message to name the variable and contain no part of its value | Very low |
| **6** | A targeted test run of one file hides a broken `_prod_env_overrides` import | Correctness | Med | Med | ✔ Constraint 6: run the whole `config/settings/tests` package | Very low |
| **6** | The test's "malformed" DSN is one the SDK actually handles | Quality | Med | Low | ✔ Constraint 4: a trailing space or newline is *handled* by `sentry-sdk 2.69.2`; use an unrecognised scheme | Very low |
| **7** | Q7 option (a) adds ~20 keys to a file five phases edit, and a concurrent edit is clobbered | Contention | Med | Med | ✔ Constraint 6; re-read before editing; option (b) is the stated recommendation | Med — accepted, by decision |
| **7** | `PGBOUNCER_AUTH_TYPE` is added to `ALLOWED_ENV_VARS` although no Django consumer reads it | Quality | Med | Low | ✔ Constraint 2: verify first, then do not | Very low |
| **7** | The commit claims to close `SRCH-001` | Review | Med | Med | ✔ Constraint 4: the body must say which half was fixed | Very low |
| **8** | The first deploy that actually starts `scheduler` runs `send_alerts` twice | **Behaviour** | **Low** (ENT-003 shipped) | Med | ✔ The constraint is discharged; the durable daily marker and the idempotency contract are phase 01's. This was the report's live rollout risk and it no longer applies | Very low |
| **8** | The new contract file is a **shared artefact** another phase then edits | Contention | Med | Med | Report it to the coordinator so §5.3 can be updated | Low |
| **8** | BLOCK 8 lands and **nothing observes** whether the scheduler started | **Detection** | **High** | Med | ✔ The report's hidden dependency; constraint 7 requires the commit body to say so. BLOCK 12 is the eventual answer | Med — accepted |
| **8** | Q1 option (a) adds a new deployment capability (a workflow reading a repo file) | Architecture | Med | Med | The gate; option (c) is shown to fail because `make` is not on the deploy path | Low |
| **9** | The corrected procedure is still wrong in a way no test can see | **Correctness** | Med | **High** | Constraint 4: validate against a production-shaped host with placeholder values, command by command, in sequence | Med — accepted |
| **9** | An engineer at 3 a.m. runs `pg_restore --clean --if-exists` against the **dev** database | **Irreversible data** | Med | **High** | ✔ Q2 is a gate with three options and their consequences; constraint 2 removes `.env.dev` from the procedure; the drift-compensation and prune changes are BLOCK 2's and already committed | Med — accepted, by decision |
| **9** | `docs/ops/rollback.md`'s correct invocations are "fixed" | Process | Med | Med | ✔ Constraint 1; the acceptance criteria require byte-identity | Very low |
| **9** | Q3 option (a) lands `scripts/ops/` with no lint harness, so the "structural fix" is not one | Quality | Med | Med | ✔ Constraint 8 requires `sh -n` and an executable assertion; the gate's consequences say a new CI job is part of the option's cost | Low |
| **10** | The deploy gate fails closed and **production deploys stop** | **Availability** | Med | **High** | Q11 is an owner decision; the assertion's token scope must be stated in the commit body; the rollback path is unchanged and manual | Med — accepted, by decision |
| **10** | `pull_request` surfaces pre-existing failures and someone removes the trigger | Process | Med | Med | ✔ Constraint 1: *"the fix is the failing check, not the removal of the trigger"* | Low |
| **10** | The digest capture runs after `up` and captures the image being deployed | **Correctness** | Low | **High** | ✔ Constraint 3 names the ordering; the capture position is in the acceptance criteria | Very low |
| **10** | One of the two `test_deploy_workflow.py` modules is forgotten | Correctness | Med | Med | ✔ Constraint 8: both in the same commit; both named in the file surface | Very low |
| **11** | Q5 option (a) adds a service BLOCK 8's guard then rejects | Contention | **High** (under (a)) | Med | ✔ Constraint 7: report the coupling, do not work around it | Med — accepted under (a) |
| **11** | The scrape-contract test is written against the library source and reproduces the defect | Correctness | Med | **High** | ✔ Constraint 1; model on `test_metrics_endpoint`, which renders a live response | Low |
| **11** | A `pending_moderation` alert is added and is dead on arrival | **Correctness** | Low | Med | ✔ `AD-008` is carried into the block and constraint 3 forbids it | Very low |
| **11** | The rules are corrected but nothing evaluates them, and the block claims closure | Review | Med | Med | ✔ Constraint 4 and the Q5 option consequences: option (c) explicitly says the *detection* half of `OPS-011` is still unmet | Low |
| **12** | Q10 option (a) adds a second sender beside the support-desk mail | **Architecture** | Med | Med | ✔ Constraint 1: `EMAIL_HOST` and the existing sender are phase 09's; the commit must reuse the transport, not open a session | Med — accepted, by decision |
| **12** | Q10 option (b) ships a signal nobody consumes and calls `OPS-011` closed | Review | **High** | Med | ✔ Constraint 7: *"under option (b), say plainly that the detection gap is unchanged"* | Low |
| **12** | A failed alert takes down the process that raised it | **Correctness** | Low | **High** | ✔ Constraint 3: fail-open, with the reason in a comment | Very low |
| **13** | Enabling the bot check makes a bot outage block deploys and roll back healthy code | **Availability** | Med | **High** | Q6 is an owner decision with that consequence written into option (a); constraint 3 requires the 120 s window to be measured | Med — accepted, by decision |
| **13** | BLOCK 13 silently edits `docker-compose.yml` to remove `BOT_HEALTH_STALE_SECONDS` | Contention | Med | **High** | ✔ Constraint 2 and the acceptance criteria: report it, do not make it | Very low |
| **13** | `liveness_check` is touched and the container healthcheck starts restarting | **Availability** | Low | **High** | ✔ Constraint 6: liveness stays dependency-free | Very low |
| **14** | A correction states what was false rather than what is true | Review | Med | Med | ✔ Constraint 4 | Low |
| **14** | A **true** statement is "corrected" back (the already-fixed `deploy-check` env claim) | Process | Med | Med | ✔ Constraint 3; named explicitly in the instance table and the acceptance criteria | Very low |
| **14** | A new false claim is introduced while rewriting twelve instances | Documentation | Med | Med | BLOCK 15's parity guard is the detector — which is exactly why it exists | Low |
| **15** | The guard is written in the same commit as the docs it checks | Process | **Low** | **High** | ✔ The 14 → 15 edge is strict and is the plan's only non-negotiable ordering | Very low |
| **15** | Q14 option (a) is taken silently and the guard is red on arrival | Process | Med | Med | The **default answer is (b)** and is stated in the block; the acceptance criteria forbid link resolution | Very low |
| **15** | The guard asserts live-file → documentation and a new compose service forces an unrelated doc edit | Design | Med | Low | ✔ Constraint 2: the direction is documentation → live file | Very low |
| **16** | The preconditions cannot fail and the drill stays decorative | **Correctness** | Med | **High** | ✔ Constraint 2; an empty restore is demonstrated to fail | Low |
| **16** | The isolation property is weakened and a `pg_restore` reaches a live database | **Irreversible data** | Low | **High** | ✔ Constraint 1 (hard) and 5 (never); separate volume, network and database via `docker run` | Very low |
| **16** | The drill pins an image that has been garbage-collected | Behaviour | Low | Med | Constraint 3; "a recorded known-good tag", and BLOCK 10's digest mechanism where available | Low |
| **16** | Q8 is declined and `OPS-004` is reported closed | Review | Med | Med | ✔ The block's `extra_context` requires the commit body to state the finding is **not closed** under (b) or (c) | Low |
| **17** | A malformed `logconfig_dict` crashes the arbiter **before** the bind | **Availability** | Med | **High** | ✔ Constraint 3: verify in a throwaway container first; `preload_app` makes this the arbiter's config, not a worker's | Low |
| **17** | `accesslog` is set to `None` "because the formatter is better", and a broken config produces silence | Correctness | Low | **High** | ✔ Constraint 2: keep both set; silence is a failure mode, plaintext is a diagnostic | Very low |
| **17** | Phase 01's `child_exit` hook is removed "while reorganising the config" | **Correctness** | Low | **High** | ✔ Constraint 1 and the acceptance criteria | Very low |
| **18** | No external uptime monitor exists — but one does, and it goes dark | **Compatibility** | Low | **High** | ✔ Q9 is a **blocking** gate; the block does not start until the answer is written down. This is the only backward-incompatible change in the phase | Low |
| **18** | `/health/live/` is restricted and three containers begin a restart loop | **Availability** | Low | **High** | ✔ Constraint 2; the acceptance criteria require the reachability to be **verified, not assumed** | Low |
| **18** | The deploy gate starts failing because the health check was restricted | Availability | Low | **High** | ✔ Constraint 3: the gate runs from inside `web`; verify it | Low |
| **18** | Option (b) changes the `/health/` alias contract without anyone deciding to | Compatibility | Med | Med | Constraint 6 prefers nginx; the Django route change is the larger surface for a LOW finding | Low |
| **18** | A documented health claim in `docs/ops/` is invalidated by the restriction | Documentation | Med | Low | The 15 → 18 edge exists for this; BLOCK 15's guard is the detector | Low |

---

## 8. Definition of done for the whole plan

Phase 12 is complete when **all** of the following hold.

### 8.1 Scope

- [ ] All **24** finding-units have a recorded disposition: **18 implemented unchanged**,
      **2 partially fixed with both live halves closed** (`OPS-018`'s remaining six plus six
      drift instances; `OPS-021`'s stale citation plus its loop limb), **1 merged and remediated
      inside `OPS-007`** (`OPS-005`), **0 rejected**, **0 dropped without a destination**,
      **2 `VAL-` items implemented** (`VAL-001` in BLOCK 7, `VAL-003` in BLOCKS 4, 8, 11, 15,
      16), **1 `VAL-` item routed** (`VAL-002` → phase 03, §6.1).
- [ ] Every gated block (**2, 7, 8, 9, 10, 11, 12, 13, 15, 16, 18**) has a **written** answer
      for each of its open questions, naming the option chosen and the consequences accepted.
      **Silence is not an acceptable outcome for any of them.**
- [ ] Each of **Q1 … Q14** is either answered with a record or explicitly re-routed with a named
      destination. **Q1, Q2, Q3, Q4, Q7, Q12, Q14** are Planner/Researcher rulings; **Q5, Q6,
      Q8, Q9, Q10, Q11** are owner or coordinator decisions; **Q13** is routed with a stated
      default (phase 12 allocates no lock id).
- [ ] The `OPS-005` → `OPS-007` merge was honoured: the profile flags appear in every deploy
      compose invocation and `OPS-005` is not tracked as a separate item.
- [ ] The `CFG-002` precondition was used, not re-asserted: `OPS-002` was implemented on the
      basis of a deploy gate that actually runs.
- [ ] The `ENT-003` precondition was used, not re-asserted: BLOCK 8 landed without waiting, and
      no second dedupe mechanism exists.
- [ ] `OPS-011`'s `EMAIL_HOST` limb was **not** re-filed, and no second `send_mail` call site
      was added.
- [ ] Every de-scoping in §6 has a named destination or a stated rationale.

### 8.2 Gates — all green

- [ ] `uv run ruff check src/` → exit 0.
- [ ] `uv run basedpyright src/` → **0 errors**.
- [ ] `.\Makefile.ps1 test` → fast gate green (`seed` marker skipped), run **after every
      block**, and **immediately after BLOCK 1** (§1.1).
- [ ] `docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml
      -f docker-compose.test.yml config --services` → exit 0, after BLOCK 1 and after any later
      compose edit.
- [ ] `docker compose --project-name mko-bazuna-dev --env-file .env.dev -f docker-compose.yml
      -f docker-compose.dev.override.yml config --services` → exit 0.
- [ ] The prod stack renders against a **scratch** env file with placeholder values — never
      against the operator's `.env.prod`.
- [ ] `makemigrations --check` → **no changes**. **This plan ships no migration.**
- [ ] No locale file was touched (no block adds a user-visible string). If BLOCK 12 option (a)
      added an operator-facing message, `test_i18n_completeness.py` is green and the `ru` and
      `bs` `msgstr` values are non-empty.
- [ ] Every red-gate observation was **re-run serially** before being reported as a defect
      (§1.1).
- [ ] **Every guard this plan adds was demonstrated failing** at least once (0.2.2 item 4).
- [ ] `git status --short .ai` shows **no new modifications** beyond the pre-existing
      `.ai/audit/**` deletions and this plan's own file.
- [ ] No commit was made without an explicit user request; no `git reset`, `git checkout`,
      `git restore` or `git stash` was run at any point; no container or compose stack was
      started, stopped or modified outside the commands in §1.1 and §1.2.

### 8.3 Per-finding behavioural confirmation

- [ ] **`OPS-001`** — the bandit step exits 0 or 1 and never 2; a scanned-file count is recorded
      in the commit body with the exact command, image and working directory; no baseline file
      exists; every `# nosec` carries a reason; the scanned-file-count guard was demonstrated
      failing.
- [ ] **`OPS-002`** — `ci.yml` declares a `pull_request` trigger; the dispatched SHA is
      constrained per Q11 and the option is recorded; the gate fails closed rather than open.
- [ ] **`OPS-003`** — every selector in the alert file resolves against a rendered `/metrics`, or
      the rule is retired; adding a dead selector turns the guard red; the file is no longer a
      Kubernetes CRD that nothing consumes; the multiprocess caveat is corrected; **no
      moderation-queue alert exists**.
- [ ] **`OPS-004`** — an empty or partial restore **fails** the drill; `django_migrations` is
      asserted; the image pin is a recorded known-good tag; the isolation property is unchanged;
      and the commit body states the Q8 outcome, including that the finding is **not closed**
      under options (b) or (c).
- [ ] **`OPS-005`** — see `OPS-007`.
- [ ] **`OPS-006`** — every production invocation in `restore.md` carries `--env-file .env.prod`
      and both `-f` files; `.env.dev` appears in no production procedure; `rollback.md`'s correct
      invocations are byte-identical; the RPO/RTO statements are conditional; the Q2 and Q3
      answers are recorded.
- [ ] **`OPS-007`** — every deploy compose invocation carries the explicit profiles; both recreate
      commands name every long-lived service; adding a `restart:`-carrying service to the prod
      manifest without naming it in the deploy path turns the guard red; the rollback runbook's
      note no longer omits `scheduler`; the commit body states that the daily dump now *starts*
      but does not survive host loss.
- [ ] **`OPS-008`** — the previous image is captured **before** pull and before `up` and is
      digest-based per Q12; the no-digest and digest-absent branches have distinct messages and
      tests; `IMAGE_TAG=latest` does not ship in the production template.
- [ ] **`OPS-009`** — `cache-from` and `cache-to` name the same reference; no namespace appears
      that is not defined once.
- [ ] **`OPS-010`** — the Q6 answer is recorded; no configured-but-disabled control is described
      as active; `liveness_check` is byte-identical and `/health/live/` remains dependency-free.
- [ ] **`OPS-011`** — the Q10 answer is recorded; under option (b) the body says the detection
      gap is unchanged; no second sender; the SLO artefacts do not read as active controls.
- [ ] **`OPS-012`** — `gunicorn.access` and `gunicorn.error` route through
      `RedactingJsonFormatter`; a rendered record is redacted; the config loads in a throwaway
      container; `child_exit` is present and unchanged; `accesslog` and `errorlog` remain set.
- [ ] **`OPS-013`** — a malformed `SENTRY_DSN` leaves `config.settings.prod` importable; the log
      message names the variable and contains no part of its value; no broad `except` was
      introduced.
- [ ] **`OPS-014`** — the Q4 probe result and option are recorded; the backup service declares a
      `user:` per the selected option; the healthcheck asserts **freshness**; no prune site misses
      the deploy filename; `_HARDENING_KEYS` is byte-identical and all twelve existing assertions
      are green.
- [ ] **`OPS-015`** — the auth type matches the engine's `password_encryption` default,
      verified against a live `pg_authid`; changing one without the other turns the guard red; the
      profile is still undocumented.
- [ ] **`OPS-016`** — every workflow declares a `concurrency` key; `deploy.yml` declares
      `cancel-in-progress: false`.
- [ ] **`OPS-017`** — no third-party `uses:` reference is a mutable tag or branch; every pin
      carries its version; every checksum was verified upstream and the command recorded;
      `.gitleaks.toml` still exists; the image still builds and still emits an SBOM.
- [ ] **`OPS-018`** — no statement in `docs/ops` describes a control that does not run or cannot
      work; the already-true `deploy-check` claim is untouched; no line-number-only citation
      remains where a semantic anchor is available; the dead audit link is re-pointed.
- [ ] **`OPS-019`** — all four healthchecks declare a `start_period` and each compose file still
      renders; removing any one turns the guard red; **no `interval`, `timeout`, `retries` or
      `depends_on` value changed**.
- [ ] **`OPS-020`** — the Q9 answer is recorded; the container healthcheck target remains
      reachable and the deploy gate still passes, **both verified rather than assumed**;
      `/metrics`'s restriction is unchanged.
- [ ] **`OPS-021`** — the `deploy-check` rationale header cites the finding it actually describes;
      the backup loop's total cadence is 24 h and it still sleeps between runs.
- [ ] **`VAL-001`** — the commit body states that `SRCH-001` is **not** closed by this block; every
      declared limit value is labelled as an unmeasured default.
- [ ] **`VAL-003`** — no new guard is string-level where a behavioural assertion was available;
      every new guard was demonstrated failing.
- [ ] **`VAL-002`** — routed to phase 03 with the intersection recorded (§6.1).

### 8.4 Cross-phase integrity

- [ ] `gunicorn.conf.py::child_exit` (phase 01 `ENT-001`) is present and unchanged.
- [ ] The scheduler's durable daily marker and `send_alerts` idempotency (phase 01 `ENT-003`) are
      present and unchanged; no second dedupe mechanism exists.
- [ ] `docker/healthcheck-bot.sh` and `healthcheck-scheduler.sh` are unchanged, and the scheduler
      healthcheck's `start_period: 600s` is intact.
- [ ] `ci.yml`'s `deploy-check` `env:` block is byte-identical (phase 02 `CFG-002`).
- [ ] `config/settings/tests/test_deploy_check_env_parity.py` is byte-identical (phase 02).
- [ ] `ALLOWED_ENV_VARS` is a **superset** of every key in all four `.env.*.example` files, and no
      existing entry was removed (phase 02 `CFG-001`).
- [ ] `test_prod_logging.py::_prod_env_overrides` was not duplicated (phase 02).
- [ ] `AdvisoryLockId` is byte-identical — **19 members, `REPAIR_BOT_USERNAME = 13`, next free
      `14`** — and no phase-12 lock id was allocated (phases 03/05/06/07/10).
- [ ] `apps/core/migrations/` gained nothing; **no migration was written**.
- [ ] `EMAIL_HOST` / `EMAIL_BACKEND` / `DEFAULT_FROM_EMAIL` and
      `telegram_bot/services/support_delivery_email.py` are byte-identical (phase 09 `API-009`).
- [ ] `docker/nginx/nginx.conf`'s `location = /metrics` restriction is byte-identical.
- [ ] `docs/01-spec/technical-specification.md` is byte-identical (phase 06).
- [ ] `src/backend/conftest.py`, `scheduler_daily_state.py` and `SchedulerDailyState` are
      byte-identical.
- [ ] Nothing under `.ai/audit/` was created, restored or modified.

### 8.5 Project conventions

- [ ] English only in every comment, log, docstring, error message and document added.
- [ ] No `print()` anywhere; `logger = logging.getLogger(__name__)` with lazy `%s` formatting.
- [ ] No migration, no new model, no new DTO, no new enum member.
- [ ] `ALLOWED_ENV_VARS` and all four example files were updated together for every new key.
- [ ] No `# nosec` without a reason; no bandit baseline; no new lint dependency.
- [ ] `[tool.ruff] fix = false` was respected — `ruff check --fix` ran only on the block's own
      files; no `ruff format`.
- [ ] Docs are in sync: `docs/ops/**`, and `docs/99-agent/**` if a topology statement changed.
- [ ] **Production code is king.** Two test treatments were pre-authorised and both name the
      rule and the reason in their commit bodies: BLOCK 4's `test_ci_yml_has_sast_job`
      (substring → behavioural) and BLOCK 4's `exclude_dirs`. No other shipped assertion was
      weakened, and **no source-inspection test was deleted**.
- [ ] Tests verify **logic and component interaction**; no test asserts a line number, an
      introspected count, a literal private name, a template-string substring, or the mere
      presence of a symbol.
- [ ] No test was run on the host; no `--override-ini=addopts=`.
- [ ] Every commit message uses `"{type}({scope}): {description}"` and cites **cycle-scoped**
      `12-OPS-0NN`, never a bare `OPS-0NN`.

### 8.6 Deliverables

| # | Deliverable | Block |
|---|---|---|
| 1 | `start_period` on four healthchecks across three compose files, plus a per-file guard | 1 |
| 2 | `docker/healthcheck-backup.sh`; `user:` and a freshness healthcheck on `backup`; one prune convention at four sites; a hardening guard with a justified exception list | 2 |
| 3 | One image coordinate defined once; `concurrency` on two workflows; the corrected finding citation | 3 |
| 4 | A working SAST gate, a repaired exclusion config, a by-class triage, and a scanned-file-count guard | 4 |
| 5 | SHA-pinned actions and verified downloads, in the workflows and the image build | 5 |
| 6 | A `SENTRY_DSN` guard with a value-free error and a malformed-DSN test row | 6 |
| 7 | SCRAM PgBouncer auth; a capacity-limit contract per Q7; cross-referenced to `SRCH-001` | 7 |
| 8 | The production long-lived service set declared once, consumed by the deploy path and the runbook, with a `restart:`-keyed guard | 8 |
| 9 | Executable runbooks; no `.env.dev` in a production procedure; the Q2 dev/proprod fix; conditional RPO/RTO | 9 |
| 10 | A deploy derived from a verified build, rolled back by digest, with both failure branches tested | 10 |
| 11 | A scrape-contract test, corrected selectors, and a monitoring-topology decision | 11 |
| 12 | An operator-notification floor or a recorded accepted gap; SLO artefacts labelled | 12 |
| 13 | A readiness contract that matches what the probe does | 13 |
| 14 | Twelve corrected documentation instances and no new ones | 14 |
| 15 | A `docs/ops` parity guard that runs documentation → live file | 15 |
| 16 | A restore drill that fails on an empty restore, pinned to a recorded image | 16 |
| 17 | gunicorn access and error logs through `RedactingJsonFormatter` | 17 |
| 18 | A `/health/` surface that does not describe the dependency graph to the public | 18 |
| — | This plan file | — |

**The plan is complete when every box above is checked or explicitly waived with a written
reason.**
