---
phase: "12"
phase_name: "production-ops"
date: "2026-09-28"
auditor: "Executor (subagent)"
validator: "Researcher verification (Phase 99)"
mode: "problems-only"
id_prefix: "OPS"
report_status: "validated"
severity_taxonomy: ".kilo/commands/audit/phases/12-audit-production-ops.md#severity-taxonomy"
---

# Audit Findings — Production Operations, Security & Observability (Validation Report)

> **This document is self-contained.** It records every decision taken by Phase 99
> against the 21 `OPS-` findings, the evidence reproduced by the validator, and the
> corrected recommendations. Neither the original auditor report nor any source file
> is required to read it.
>
> **Problems-only.** Only defects and rejected claims are reported. Verified-clean
> items are listed once, in §2, so the reader can tell a deliberate silence from an
> oversight.

---

## 1. Executive Summary (original auditor text, preserved verbatim)

> The production deployment pipeline is largely unverified. Of the security,
> disaster-recovery and monitoring controls the project believes it has, the
> static-analysis gate scans nothing and reports success, the monthly restore
> drill restores a throwaway copy of an empty database, all three SLO alerts
> reference measurements that do not exist, and nothing anywhere notifies an
> operator when any of this is true. The disaster-recovery and rollback
> runbooks — the documents an engineer reaches for at 3 a.m. — contain commands
> that fail immediately on a production host. Twenty-one problems were found,
> one of them critical and seven high; the broadest business risk is that a
> failure in production would be discovered by users rather than by the system,
> and that a rollback would not restore a known-good state.

**Validator annotation — three sentences of the above are refuted and must not
survive into the final document:**

1. *"the static-analysis gate scans nothing **and reports success**"* — the gate
   does not report success. It fails, with exit code 2. See `OPS-001`.
2. *"one of them critical"* — there is no CRITICAL in this phase. `OPS-001` is
   reclassified HIGH. See §4.
3. *"the disaster-recovery **and rollback** runbooks … contain commands that fail
   immediately"* — accurate for `restore.md`; **not** accurate for `rollback.md`,
   whose image-tag rollback and scheduler-marker check both carry
   `--env-file .env.prod`. See `OPS-006`.

The remaining thesis — that failure in production would be discovered by users
rather than by the system, and that the SLO alerting and DR drill are inert — is
**confirmed**.

**Net result of validation:**

| Outcome | Count | IDs |
|---|---|---|
| Confirmed, fully unchanged | 10 | OPS-002, 003, 004, 007*, 009, 014, 016, 019, 020, 021 |
| Confirmed, **severity** adjusted | 5 | OPS-001 ↓CRITICAL→HIGH, OPS-005 ↓HIGH→MEDIUM, OPS-008 ↓HIGH→MEDIUM, OPS-012 ↓MEDIUM→LOW, OPS-015 ↓MEDIUM→LOW |
| Confirmed, **evidence/claims** corrected (severity held) | 6 | OPS-006, OPS-010, OPS-011, OPS-013, OPS-017, OPS-018 |
| Merged | 1 | OPS-005 → OPS-007 |
| Rejected outright | 0 | — |
| Duplicated against a validated phase | 1 sub-claim | OPS-011 `EMAIL_HOST` limb → API-009 (phase 09) |
| Validation-level findings raised | 3 | VAL-001, VAL-002, VAL-003 |

10 + 5 + 6 = 21 ✔. `OPS-005` appears in two rows because it is both a severity
adjustment and the single merge; it is not counted twice in the total.

\* `OPS-007` is confirmed at HIGH and additionally absorbs `OPS-005`.

**Post-validation severity distribution:** CRITICAL 0 · HIGH 5 · MEDIUM 10 · LOW 6.

---

## 2. Verified-Clean Items (methodology evidence, not findings)

These are recorded so that their absence from the findings list is deliberate.
All were re-verified by the validator unless marked otherwise.

| Item | Evidence |
|---|---|
| Runtime image runs as non-root | `docker/Dockerfile:171` `USER app` |
| SBOM generated at build time | `docker/Dockerfile:90-93` `syft … -o cyclonedx-json` |
| liveness vs readiness are distinct endpoints | `apps/core/views.py:131-138` (readiness, 503-aware) vs the `/health/live/` contract in `docker/Dockerfile:176-177` and `docker-compose.yml:255` |
| container `HEALTHCHECK` targets liveness | `docker/Dockerfile:176-177` + `docker-compose.yml:255`, both `/health/live/` |
| liveness/readiness thresholds are bounded | `interval`+`timeout`+`retries` on every long-lived service (`:256-259`, `:299-302`, `docker-compose.prod.yml:124-127`) |
| `pip-audit` + Trivy fs + Trivy image + gitleaks steps exist and upload SARIF | `ci.yml:310-373`, `:41-56` |
| Dependabot covers `github-actions` and `uv` ecosystems, weekly | `.github/dependabot.yml` |
| prod `LOGGING` uses `RedactingJsonFormatter` | `config/settings/prod.py:22-67`, formatter at `apps/core/utils/json_logging.py:68-93` |
| backup job uses `pg_dump -F c`, daily, 7-day retention | `docker-compose.prod.yml:141-155` |
| RPO/RTO are documented | `docs/ops/restore.md:195-226` (RPO 24 h, RTO ≈4 h) |
| `rollback.md:555-604` faithfully transcribes `deploy.yml` | diffed line-for-line; identical, including both defects |
| ops-doc line/offset citations are all in range | every cited offset falls inside its file (checked against actual line counts: `docker-deployment.md` 1139, `rollback.md` 748, `restore.md` 317, `migration-workflow.md` 523, `postgres-18-docker-volume-migration.md` 325, `prometheus-slo-alerts.yaml` 158). **No past-EOF citations.** |

---

## 3. Validation Method

| Stage | What the validator did |
|---|---|
| R1 — Ingest | All 21 findings copied forward with IDs preserved. |
| R2 — Cross-finding | Compared against the eleven already-validated phases (§8). |
| R3 — Per-finding | Re-ran every falsifiable runtime claim. Probes were run inside the already-built `mko-bazuna-test-web:latest` image with the repository bind-mounted read-only at `/app`, plus a `config --services` interpolation check. No scratch containers left running; no write to the shared `mko_bazuna` database; no dev-stack dependency. |
| R4 — Rollout | Dependency chains, merge candidates and coverage gaps → §7, §9, VAL-001…003. |

Reproduction commands used (for the record; all read-only):

```text
# OPS-001 — the CI SAST step, exact CWD and flags
docker run --rm --entrypoint sh -v <repo>:/app -w /app/src/backend \
  mko-bazuna-test-web:latest \
  -c "bandit -r src/backend src/telegram_bot -c pyproject.toml; echo EXIT=$?"
  →  [main] ERROR pyproject.toml : Could not read config file.   EXIT=2

# OPS-001 — the same binary, repository-root paths and config
docker run … -w /app … -c "bandit -q -r src/backend src/telegram_bot -c pyproject.toml"
  →  Total lines of code: 61063
     Low: 104   Medium: 10   High: 0            (severity)
     Medium: 77 High: 37                        (confidence)   EXIT=1

# OPS-013 — Sentry DSN handling in the shipped image (sentry-sdk 2.69.2)
python -c "sentry_sdk.init(dsn='not-a-valid-dsn')"
  →  sentry_sdk.utils.BadDsn: Unsupported scheme ''
python -c "sentry_sdk.init(dsn=' https://key@o1.ingest.sentry.io/2 ')"      → OK
python -c "sentry_sdk.init(dsn='https://key@o1.ingest.sentry.io/2\n')"     → OK
```

---

## 4. Findings Summary (status and severity mutated)

| ID | Title | Original | **Validated** | Action | Note |
|---|---|---|---|---|---|
| OPS-001 | CI SAST gate scans zero files and always passes | CRITICAL | **HIGH** | ADJUSTED | Two evidence claims refuted; baseline recommendation rejected |
| OPS-002 | Production deploy is not gated on any CI result | HIGH | **HIGH** | CONFIRMED | Real deployment defect |
| OPS-003 | Every SLO alert references a metric that does not exist | HIGH | **HIGH** | CONFIRMED | Statically proven against installed lib |
| OPS-004 | Monthly restore-test restores a self-generated empty dump | HIGH | **HIGH** | CONFIRMED | Real DR defect |
| OPS-005 | Backups are single-host, opt-in, never started by deploy | HIGH | **MEDIUM** | MERGED → OPS-007 | Deploy-path limb real; off-host limb is strategy |
| OPS-006 | DR and rollback runbooks are not executable on a prod host | HIGH | **HIGH** | ADJUSTED (scope) | "Every invocation" refuted; `restore.md` limb holds |
| OPS-007 | Deploy/rollback never update the profile-gated scheduler | HIGH | **HIGH** | CONFIRMED + ABSORBS OPS-005 | Absorbing finding for the profile gap |
| OPS-008 | Rollback target may be the mutable `latest` tag | HIGH | **MEDIUM** | ADJUSTED | "Default configuration" claim refuted |
| OPS-009 | CI pushes and prod pulls from three registry namespaces | MEDIUM | **MEDIUM** | CONFIRMED | All five literals verified |
| OPS-010 | Bot-marker freshness disabled in every shipped config | MEDIUM | **MEDIUM** | CONFIRMED | Impact statement overstated |
| OPS-011 | No alerting channel exists anywhere in the system | MEDIUM | **MEDIUM** | ADJUSTED | `send_mail` evidence **refuted**; core survives |
| OPS-012 | Gunicorn access/error logs bypass the redacting formatter | MEDIUM | **LOW** | ADJUSTED | Hygiene; security impact is speculative |
| OPS-013 | Malformed `SENTRY_DSN` crash-loops every service | MEDIUM | **MEDIUM** | CONFIRMED | Stated triggers corrected |
| OPS-014 | Backup job runs as root, no healthcheck, deploy dumps never pruned | MEDIUM | **MEDIUM** | CONFIRMED | Strongest single catch in the report |
| OPS-015 | PgBouncer is md5 against PG18 SCRAM verifiers | MEDIUM | **LOW** | ADJUSTED | No documented guidance exists; latent |
| OPS-016 | No `concurrency` group on CI or deploy | MEDIUM | **MEDIUM** | CONFIRMED | Deploy race is the real limb |
| OPS-017 | Mutable action tags and unverified `curl \| tar` gitleaks fetch | MEDIUM | **MEDIUM** | CONFIRMED | Same class also in the image build |
| OPS-018 | Ops documentation asserts controls that are not live | MEDIUM | **MEDIUM** | ADJUSTED | 1 sub-claim refuted, 4 instances missed |
| OPS-019 | `db`/`redis` healthchecks have no `start_period` | LOW | **LOW** | CONFIRMED | One-line fix |
| OPS-020 | Public readiness endpoint exposes internal dependency state | LOW | **LOW** | CONFIRMED | Genuine, small, free to close |
| OPS-021 | Backup loop drift compensation; misplaced `ci.yml` comment | LOW | **LOW** | CONFIRMED | Merges into OPS-005/014 thematically |

**Distribution after validation**

| CRITICAL | HIGH | MEDIUM | LOW |
|---|---|---|---|
| 0 | 5 | 10 | 6 |

**Status counts** *(mutually exclusive; every finding appears exactly once)*

| Status | Count | IDs |
|---|---|---|
| Validated unchanged | 10 | OPS-002, 003, 004, 007, 009, 014, 016, 019, 020, 021 |
| Validated, severity reclassified | 5 | OPS-001, 005, 008, 012, 015 |
| Validated, evidence/claims corrected | 6 | OPS-006, 010, 011, 013, 017, 018 |
| Merged away | 1 | OPS-005 (→ OPS-007) |
| Rejected | 0 | — |
| Deferred | 0 | — |

`OPS-005` is listed in both the "severity reclassified" and "merged away" rows
because both actions apply to it; the 21 in-scope findings are accounted for by
10 + 5 + 6.

---

## 5. Findings by Severity (validated)

### HIGH

---

#### OPS-001: [HIGH] — The CI SAST step is a no-op: it scans nothing **and fails**

> **Validation Note:**
> - **Action:** Reclassified — **CRITICAL → HIGH**; two evidence claims refuted; the
>   baseline recommendation **rejected**.
> - **Detail:** The step is genuinely broken, but not in the way reported. The gate
>   does **not** "always pass" — it **always fails**, with exit code 2, because
>   `-c pyproject.toml` is resolved relative to `working-directory: src/backend` and
>   the repository contains exactly **one** `pyproject.toml`, at the root. Separately,
>   the quoted backlog of "117 findings (81 medium / 36 high)" is wrong in both
>   total and distribution. CRITICAL requires a demonstrable severe production
>   consequence; a process gate that never analyses a line has none.
> - **See also:** `OPS-018` (the same control is documented as working at
>   `docs/ops/docker-deployment.md:431-436`); `VAL-003`.

| Field | Value |
|---|---|
| **ID** | OPS-001 |
| **Severity** | HIGH (was CRITICAL) |
| **Category** | Security / CI gating |
| **File(s)** | `.github/workflows/ci.yml:355-358`, `pyproject.toml:230-233`, `docs/ops/docker-deployment.md:431-436`, `src/backend/apps/core/tests/test_ci_security.py:158-173` |
| **Status** | Validated |

**Problem.** The only static-application-security-test step in the pipeline is
`uv run bandit -r src/backend src/telegram_bot -c pyproject.toml` with
`working-directory: src/backend` (`ci.yml:355-358`). Two independent
path-relativity errors make it non-functional:

1. **The scan roots are wrong.** Resolved against `src/backend`, the targets become
   `src/backend/src/backend` and `src/backend/src/telegram_bot`. Neither exists.
2. **The config path is wrong.** `-c pyproject.toml` is likewise CWD-relative.
   The repository has a single `pyproject.toml`, at the root; there is no
   `src/backend/pyproject.toml`.

**Impact (corrected).** `bandit` aborts with `ERROR pyproject.toml : Could not
read config file.` and exits **2**. The `security` job therefore **fails on every
run**, and no Python source file in the repository has ever been statically
analysed. The harm is the inverse of what was reported: not a green badge that
misinforms reviewers, but a permanently red `security` job that nobody gates on
(compounded by `OPS-002`) — which is why the defect survived review. The
`security` job has no `needs:` and nothing depends on it.

**Root cause (corrected).** The step was added in `0f96dcc` (`ci(sast): add bandit
SAST scanning to security pipeline`, 2026-09-25) and never exercised. It survived
because the accompanying regression guard `test_ci_yml_has_sast_job`
(`test_ci_security.py:158-161`) only asserts the **substring** `"bandit"` is
present, and the `security` job does not run pytest — so no test can distinguish a
working step from one that scans nothing, and no test in the `security` job can
fail because the job is already red for a different reason.

**Evidence — the CI step, run with its exact CWD and flags in the shipped image**
*(supports: "the step does not silently pass — it aborts")*:

```text
[main] ERROR pyproject.toml : Could not read config file.
CI_FORM_EXIT=2
```

**Evidence — the same binary with repository-root paths and the repository's own
`[tool.bandit]` config** *(refutes the "117 findings / 81 medium / 36 high" claim)*:

```text
Code scanned:
	Total lines of code: 61063
Run metrics:
	Total issues (by severity):
		Undefined: 0
		Low: 104
		Medium: 10
		High: 0
	Total issues (by confidence):
		Undefined: 0
		Low: 0
		Medium: 77
		High: 37
Files skipped (0):
CORRECT_EXIT=1
```

The reported figures (117 total; 81 medium / 36 high) match **neither** the
severity table (104/10/0) nor the confidence table (0/77/37).

**Evidence — the actual 114-finding composition** *(supports: "the real backlog is
dominated by test-fixture noise and ten reviewable Medium items")*:

```text
LOW      B106  x72     hardcoded password function argument
LOW      B603  x16     subprocess without shell=True
LOW      B404  x9      import subprocess
MEDIUM   B108  x5      hardcoded /tmp
MEDIUM   B703  x3      mark_safe — potential XSS
MEDIUM   B308  x2      mark_safe — review for XSS
LOW      B311  x4      random (not secrets) — seed generators only
LOW      B110  x2      try/except/pass
LOW      B403  x1      pickle — apps/core/utils/swr_cache.py:30
```

Of the 72 `B106`, **64 sit in test files**: 20 in
`src/backend/config/settings/tests/test_settings_secrets.py`, 17 in
`src/backend/apps/moderation/tests/test_admin_actions.py`, 13 in
`src/backend/apps/core/tests/test_create_admin_user.py`, 9 in
`src/backend/apps/seed/tests/test_seed.py`, 5 in
`src/backend/apps/users/tests/test_deletion.py`. These are password literals that
are themselves the subject under test. The ten Medium items are genuinely
reviewable: `mark_safe` at `apps/ads/templatetags/global_tags.py:33` and
`apps/core/templatetags/telegram_tags.py:164,176`, and hardcoded `/tmp` defaults at
`config/settings/base.py:314` (`BOT_LIVENESS_FILE`) and `:335`
(`SCHEDULER_LIVENESS_FILE`).

**Why the `exclude_dirs` config under-performs** *(supports: "the exclusion config
is itself part of the defect")*. `pyproject.toml:231` declares
`exclude_dirs = ["src/backend/apps/**/tests", "src/backend/tests", "docs"]`. This
does not cover `src/backend/config/settings/tests/` or
`src/telegram_bot/tests/`, and as a `fnmatch` pattern `**` collapses to `*`, so it
does not reliably match the nested `tests` directories either. The exclusion
config — not the rule set — is the main reason the backlog looks alarming.

**Recommendation (corrected — the baseline proposal is REJECTED).**

A committed baseline is the wrong instrument here and should not be adopted. It
would institutionalise 64 `B106` suppressions in test fixtures, permanently
permit **new** `B106` in production code (where a hardcoded credential *is* a real
defect), and freeze the `B311`/`B403` classes as acceptable. It also encodes
today's suppression decisions as untested truth. Correct sequence:

1. Fix both paths: `working-directory: .` with `-r src/backend src/telegram_bot
   -c pyproject.toml`, or keep the CWD and target `apps config theme` plus
   `../../src/telegram_bot` with `-c ../../pyproject.toml`.
2. Repair `exclude_dirs` to the real test trees (`src/backend/**/tests`,
   `src/telegram_bot/tests`) and re-measure.
3. Triage the residual, by class, not by file: `# nosec B106` with a one-line
   justification on the test fixtures; individual review and fix for the ten
   Medium items (`mark_safe` call sites, `/tmp` liveness paths); `# nosec` with
   rationale for `B603`/`B404` (the project already wraps `subprocess` for
   `manage.py` child dispatch); deliberate decision on `B311` (seed data only) and
   `B403` (`swr_cache.py`).
4. Replace the substring guard `test_ci_yml_has_sast_job` with a guard that
   asserts a **non-zero scanned-file count** and that the configured paths exist —
   the check that would have caught this on day one.

| **Effort** | M (raised from S — the triage is the work, not the path fix) |
|---|---|

---

#### OPS-002: [HIGH] — Production deploy is not gated on any CI result

> **Validation Note:** **Confirmed as written.** Both limbs re-verified byte-exact.
> No adjustment. This is a genuine deployment defect, not operational hygiene: the
> only automated prod-config gate in the system (`deploy-check`, see `CFG-002`) does
> not run, so a manual dispatch is the sole path to production.
> - **See also:** `OPS-009`, `OPS-016`, `CFG-002` (phase 02).

| Field | Value |
|---|---|
| **Severity** | HIGH |
| **Category** | CI/CD gating |
| **File(s)** | `.github/workflows/deploy.yml:8-14, 24, 30-38`, `.github/workflows/ci.yml:3-5` |
| **Status** | Validated |

**Problem.** `deploy.yml` triggers only on `workflow_dispatch` (`:8-14`) and
declares no dependency on any CI job — no `needs:`, no `workflow_run` trigger, and
no required status check on the `production` environment (`:24`). Its `image_tag`
input is free text defaulting to `${GITHUB_SHA}` and is used verbatim as
`IMAGE_TAG`. Separately, `ci.yml:3-5` triggers only on `push: [main, develop]` —
there is **no** `pull_request` trigger, so a pull request is never gated by lint,
typecheck, tests, `security` or `deploy-check` at all.

**Impact.** Two independent paths to an ungated production image: a branch that
never passed `security` can be dispatched, and any SHA — including one carrying a
known CVE — can be shipped by typing it into the workflow input. The manual
approval on the `production` environment is a human checkbox, not a verification.

**Root cause.** The deploy workflow was written as a convenience wrapper around a
manual `docker compose up -d` (`0f28ffe`) without being wired to the pipeline it
consumes. A mutable-tag compose deployment has no notion of a "green build", so
the linkage must be made explicitly and was not.

**Evidence — `.github/workflows/ci.yml:3-5`** *(no `pull_request` trigger)*:

```yaml
on:
  push:
    branches: [main, develop]
```

**Evidence — `.github/workflows/deploy.yml:8-14, 24`** *(free-text input, no
`needs`, no status check)*:

```yaml
on:
  workflow_dispatch:
    inputs:
      image_tag:
        description: "Git SHA from the CI build to deploy. Defaults to the current commit SHA."
        required: false
        default: ""
...
    environment: production
```

**Recommendation (unchanged, plus one addition).**

1. Add `on: pull_request:` to `ci.yml` so every change is gated before merge.
2. Constrain `deploy.yml`: replace the free-text `image_tag` with a constrained
   input, or assert the requested tag is a commit on `main` with a successful `CI`
   run for that SHA before the SSH step. This is also the point at which the
   `deploy-check` job (`CFG-002`) becomes load-bearing again — it is currently
   dead, so fixing `CFG-002` and `OPS-002` together is the highest-leverage pair in
   this phase.
3. Add `concurrency: {group: deploy-production, cancel-in-progress: false}` (see
   `OPS-016`).

---

#### OPS-003: [HIGH] — Every SLO alert references a metric that does not exist; no Prometheus is deployed

> **Validation Note:** **Confirmed at HIGH.** Independently re-derived from the
> installed library source rather than from a scrape, and from a repository-wide
> grep of all four compose files. All four limbs of the problem statement hold
> exactly as written. The recommended minimal path is retained; the "add a
> Prometheus service" half is scoped down to an explicit decision, not an
> assumption.
> - **See also:** `OPS-011`, `OPS-018`, `AD-008` (phase 05 — checked, no duplication).

| Field | Value |
|---|---|
| **Severity** | HIGH |
| **Category** | Observability / SLOs |
| **File(s)** | `docs/ops/prometheus-slo-alerts.yaml:56-67, 95-102, 132-140, 9`, `docker/nginx/nginx.conf:159-168`, `docker-compose*.yml` |
| **Status** | Validated |

**Problem.** The three alert rules in `docs/ops/prometheus-slo-alerts.yaml` select
series that are never emitted.

1. `search_slo_burn_rate` (`:56-67`) and `search_p95_latency_slo` (`:95-102`) use
   `django_http_response_duration_seconds_bucket` with `handler="search:search"`.
   The installed `django-prometheus 2.5.0` emits
   `django_http_requests_latency_including_middlewares_seconds` and
   `django_http_requests_latency_seconds_by_view_method`, labelled by
   `view`/`method`. There is **no** `django_http_response_duration_seconds` family
   and **no** `handler` label.
2. Even a corrected metric name would not resolve the selector: the rules use
   `le="2.000"`, and `PROMETHEUS_LATENCY_BUCKETS` defaults to
   `0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0, 25.0,
   50.0, 75.0, +Inf`. There is no 2.0 edge, and **no** `PROMETHEUS_LATENCY_BUCKETS`
   override exists in `pyproject.toml` or any `config/settings/*.py`. The edges
   either side of the 2 s SLO are 1.0 and 2.5.
3. `cache_hit_rate_slo` (`:132-140`) uses `redis_db_keyspace_hits_total`, emitted
   by a `redis_exporter` that is in no compose file.
4. Independently, **no** Prometheus, Alertmanager, Grafana or exporter service
   exists in any of the four compose files — a repository-wide case-insensitive
   grep for `prometheus|grafana|alertmanager|node_exporter|redis_exporter` across
   `docker-compose*.yml` returns exactly two hits, both the
   `PROMETHEUS_MULTIPROC_DIR` variable and its tmpfs mount in
   `docker-compose.prod.yml:14,16`. And `docker/nginx/nginx.conf:159-168`
   restricts `location = /metrics` with `allow 127.0.0.1; deny all;`, so no
   container other than `web` itself can scrape it.

**Impact.** With zero matching series, all three rules evaluate to an empty vector
and can never enter the firing state. Search-latency SLO breaches, cache collapse
and error-budget burn-down are invisible to any human, and
`docs/ops/grafana-slo-dashboard.json` is equally unconsumed.
`docs/ops/docker-deployment.md:1013-1015` states "An external Prometheus instance
scrapes it on its own schedule", but the shipped configuration makes that scrape
return `403` from anywhere but the host itself. The file is a `PrometheusRule`
CRD, so it additionally presupposes a Kubernetes monitoring stack the project does
not run.

**Root cause.** The rules were written against a remembered `django-prometheus` API
surface (pre-2.4 metric names, an assumed `handler` label, an assumed 2 s bucket
edge) rather than the exposition the installed version produces. The thresholds
were cross-checked only against the constants in `src/benchmark/constants.py`
(`PerformanceSLO`), never against `/metrics`. No test ever evaluated an `expr`
against a live scrape — the same string-level-guard pattern that let `OPS-001`
through.

**Evidence — `docker/nginx/nginx.conf:159-162`** *(an external scraper is denied at
the proxy)*:

```nginx
        # Metrics endpoint — restricted to localhost (production monitoring only)
        location = /metrics {
            allow 127.0.0.1;
            deny all;
```

**Evidence — the installed metric names** *(supports: "no `django_http_response_duration_seconds`
family exists; the label is `view`/`method`, not `handler`")*:

```text
# /opt/venv/lib/python3.14/site-packages/django_prometheus/middleware.py
            "django_http_requests_latency_including_middlewares_seconds",
            "django_http_requests_latency_seconds_by_view_method",
django-prometheus 2.5.0
```

**Evidence — repository-wide grep across all four compose files** *(supports: "no
scrape target or rule evaluator is deployed")*:

```text
docker-compose.prod.yml:14:      - PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc
docker-compose.prod.yml:16:      - /tmp/prometheus_multiproc:rw
```

**Evidence — `docs/ops/docker-deployment.md:1013-1015`** *(the doc promises a
scrape the configuration blocks)*:

```text
Production exposes a Prometheus `/metrics` endpoint behind the `web` service (wired via
`django_prometheus` in `INSTALLED_APPS`, middleware, and `path("", include("django_prometheus.urls"))`
in `config/urls.py`). An external Prometheus instance scrapes it on its own schedule.
```

**Recommendation (unchanged; scope clarified).**

Decide the monitoring deployment explicitly — this is a decision, not a task.
Minimum viable: correct the selectors to the real series
(`..._latency_including_middlewares_seconds_bucket{view="search"}`) with an
interpolated p95/p99, **or** set `PROMETHEUS_LATENCY_BUCKETS` to include `2.0` so
the existing `le="2.000"` resolves; add a `prometheus` service with a
`prometheus.yml` whose `rule_files` include this file; and either move the rules out
of the Kubernetes-only `PrometheusRule` CRD form or document the prerequisite.
Add `promtool check rules` plus a scrape-contract test asserting every `expr`
selector resolves against a live `/metrics` render — that test is the durable fix,
because it converts a hand-maintained PromQL file into a verified contract.

---

#### OPS-004: [HIGH] — Monthly restore-test restores a self-generated empty dump, not a production backup

> **Validation Note:** **Confirmed at HIGH.** Workflow re-read end to end; the
> guard tests re-read; the Makefile smoke tests re-read. A real disaster-recovery
> defect, not hygiene: the control exists solely to prove real artifacts are
> restorable, and it proves nothing about them.
> - **See also:** `OPS-005` (now merged into `OPS-007`), `OPS-006`.

| Field | Value |
|---|---|
| **Severity** | HIGH |
| **Category** | Reliability / Disaster recovery |
| **File(s)** | `.github/workflows/restore-test.yml:70-81, 91, 94`, `Makefile:271-341`, `src/backend/tests/test_restore_test_workflow.py:36-71` |
| **Status** | Validated |

**Problem.** `restore-test.yml` bootstraps a fresh CI database via
`bootstrap_reference_data` (migrations + reference data, no user data) at `:70-76`,
then runs `pg_dump --no-sync … -d mko_bazuna -F c > backups/test_backup.dump`
against *that* database at `:78-81`, and hands the resulting file to
`make restore-test` at `:94`. No production backup is fetched, downloaded, or
referenced at any point. The job therefore exercises a `pg_dump` → `pg_restore`
round trip of a nearly empty schema, never a real backup artifact.

**Impact.** The monthly control gives false assurance about the only thing it
exists to prove. A production backup that is truncated, silently corrupted by a
disk error, written with an incompatible `pg_dump` version, or missing rows
because of a `pg_dump` bug would still pass, because the file under test was
produced three steps earlier from a healthy in-memory database.
`docs/ops/restore.md:197` documents a 24 h RPO and `restore.md:215` an ≈4 h RTO on
the strength of this cadence; neither number is backed by evidence.

**Root cause.** The workflow was designed to be self-contained and hermetic —
avoiding any secret or artifact transfer into CI — at the cost of testing nothing
real. `test_restore_test_workflow.py:36-71` asserts only that the YAML *contains* a
`schedule:`, a `cron:`, and the string `migrate --plan --check`; the same
string-level-guard pattern that let `OPS-001` through.

**Evidence — `.github/workflows/restore-test.yml:70-81`** *(the dump under test is
generated from a freshly-bootstrapped database in the same job)*:

```yaml
      - name: Run migrations (bootstrap reference data)
        env:
          DJANGO_SETTINGS_MODULE: config.settings.test
          DATABASE_URL: postgres://postgres:postgres@localhost:5432/mko_bazuna
          DJANGO_SECRET_KEY: test-secret-key-for-testing-only
        run: uv run python manage.py bootstrap_reference_data
        working-directory: src/backend

      - name: Generate test backup
        run: |
          mkdir -p backups
          pg_dump --no-sync -h localhost -U postgres -d mko_bazuna -F c > backups/test_backup.dump
```

**Evidence — `Makefile:320-325`** *(the smoke tests only count tables and echo
`ads_ad` rows — they never assert the counts are plausible)*:

```make
	echo "→ Smoke test 2/4: table count (schema present)" && \
	echo "  Tables: $$(docker exec restore-db psql -U restore_user -d bazuna_restore -t -A -c \
		"SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")" && \
	echo "→ Smoke test 3/4: row count in ads_ad (data present)" && \
	echo "  ads_ad rows: $$(docker exec restore-db psql -U restore_user -d bazuna_restore -t -A -c \
		"SELECT count(*) FROM ads_ad;")" && \
```

**Additional defect the auditor missed** *(validator finding, folded into OPS-004)*.
`restore-test.yml:91` pulls `ghcr.io/mko-bazuna/mko_bazuna:${{ github.sha }}`. On a
`schedule` trigger, `github.sha` is the tip of the default branch at fire time,
which may have no image pushed under that SHA (CI only builds on `push`). The
monthly drill can therefore fail at the `docker pull` step for a reason unrelated
to backup integrity. Use a pinned known-good tag, or record the last successful
image tag as an artifact.

**Recommendation (unchanged, plus the pull fix).**

Make the job consume a real artifact: have the `backup` service push the newest
dump to object storage (a signed push is the practical route), and have
`restore-test.yml` download the most recent artifact rather than generating one.
Add a precondition assertion on restored row counts (`SELECT count(*) FROM
`ads_ad` must be > 0 and `django_migrations` must exist) so an empty or partial
restore fails the job — the Makefile already computes both counts, it just does
not assert on them. Keep the self-generated dump path as an additional smoke test,
and pin the application image to a recorded tag rather than `${{ github.sha }}`.

---

#### OPS-006: [HIGH] — The DR runbook is not executable on a production host

> **Validation Note:**
> - **Action:** Reclassified in scope. The universal quantifier is **refuted**:
>   `docs/ops/rollback.md:147-149` and `:432-434`, and
>   `docs/ops/docker-deployment.md:420`, **do** pass `--env-file .env.prod`. The
>   "rollback runbook" limb of the title does not hold. The `restore.md` limb holds
>   completely and the finding remains **HIGH** — the disaster-recovery document an
>   engineer opens at 3 a.m. cannot be followed, which is the more urgent of the two
>   because it is the one used when data is already lost.
> - **Detail:** Production compose files use mandatory interpolation
>   (`${POSTGRES_USER:?…}`, `${DJANGO_SECRET_KEY:?…}`), so every compose
>   invocation without `--env-file` aborts during config rendering — including
>   read-only commands like `ps`, `stop` and `exec`. On a production host the
>   compose project directory holds `.env.prod`, not `.env`, and the repository
>   ships only `.env.*.example` (`.gitignore:144-148`), so compose finds no
>   default env file either.
> - **See also:** `OPS-004`, `OPS-007`, `OPS-008`, `OPS-018`.

| Field | Value |
|---|---|
| **Severity** | HIGH (scope narrowed) |
| **Category** | Documentation / operability |
| **File(s)** | `docs/ops/restore.md:25, 33, 71, 77, 91-92, 95, 106, 125, 131, 137`, `docs/ops/rollback.md:441-450, 555, 570, 590, 595, 604`, `docs/ops/migration-workflow.md`, `docs/ops/postgres-18-docker-volume-migration.md` |
| **Status** | Validated |

**Problem (corrected).** Every `docker compose` invocation in `docs/ops/restore.md`
omits `--env-file .env.prod` — all of them, at `:33` (the documented way to start
the daily backup), `:71` (`ps db`), `:77` (`stop web bot`), `:95` and `:106`
(`pg_restore`, the production restore path itself), `:125` (`start web bot`),
`:131` (connectivity check) and `:137` (`run --rm migrate`). Each aborts with
`required variable POSTGRES_USER is missing a value` before doing anything.

Additionally `docs/ops/restore.md:25` and `:91-92` — the prerequisites and the first
two steps of the **production** restore procedure — read `POSTGRES_USER` and
`POSTGRES_DB` out of **`.env.dev`**:

```bash
# Set environment variables for the restore
export POSTGRES_USER=$(grep POSTGRES_USER .env.dev | cut -d= -f2)
export POSTGRES_DB=$(grep POSTGRES_DB .env.dev | cut -d= -f2)
```

This is a dev/prod credential-source confusion, not merely a missing flag: the
values it yields are the development database's, not production's.

The same omission affects `docs/ops/rollback.md:441-450` (the health-validation
checklist), `:555` (`PREVIOUS_IMAGE_TAG` capture) and `:570, :590, :595, :604`
(the automated-rollback block transcribed from `deploy.yml`) — though these are
lower harm, because they are normally executed from a shell that has already
sourced `.env.prod`, which is what `deploy.yml:62-64` does.

**Impact.** The document an engineer opens when the database is already lost
cannot be followed. Each command fails immediately, and the `.env.dev` credential
read at `restore.md:91` would either fail or point the operator at the wrong
database. Combined with `OPS-004` (the restore drill proves nothing) and
`OPS-007` (the backup job is not started by the deploy path), the recovery
capability of this system is unproven end to end.

**Root cause.** The runbooks were written by paraphrasing commands rather than by
executing them, and the `--env-file` requirement — documented in `AGENTS.md` and
`.kilo/rules/commands.md` — was not applied retroactively. Nothing in CI compiles
or dry-runs the shell blocks inside the runbooks.

**Evidence — reproduced command** *(supports: "the documented form aborts")*:

```text
$ docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile backup config --services
error while interpolating services.migrate.environment.POSTGRES_USER: required variable POSTGRES_USER is missing a value: POSTGRES_USER must be set
error while interpolating services.web.environment.[]: required variable DJANGO_SECRET_KEY is missing a value: DJANGO_SECRET_KEY must be set
EXIT=1
```

**Evidence — the counter-examples that refute the universal claim** *(these commands
are correct as written and must not be "fixed")*:

```bash
# docs/ops/rollback.md:147-149 — correct
   docker compose --env-file .env.prod \
     -f docker-compose.yml -f docker-compose.prod.yml \
     up -d --pull always web bot

# docs/ops/rollback.md:432-434 — correct
docker compose --env-file .env.prod \
  -f docker-compose.yml -f docker-compose.prod.yml \
  exec scheduler stat -c '%Y %n' /tmp/mko_bazuna_scheduler_alive
```

**Recommendation (unchanged, sweep widened).**

Add `--env-file .env.prod` to every production `docker compose` invocation in
`restore.md`; change `restore.md:25` and `:91-92` to source `.env.prod`; sweep
`migration-workflow.md` and `postgres-18-docker-volume-migration.md` in the same
pass. Then extract the code blocks into a single executable script
(`scripts/ops/restore.sh`, `scripts/ops/rollback.sh`) and have the runbooks
reference it, so a broken command fails a lint/CI step instead of an incident.
That extraction is the structural fix — without it, documentation drift on this
surface is unbounded (see `OPS-018`).

---

#### OPS-007: [HIGH] — Deploy and rollback never update the profile-gated services, so rollback is not atomic

> **Validation Note:**
> - **Action:** Confirmed as written, and **extended to absorb OPS-005** (see §6).
> - **Detail:** Root cause is identical to `OPS-005` and the fix is the *same edit*
> — adding `--profile backup --profile scheduler --profile pgbouncer` to the
> `deploy.yml` and runbook compose invocations. The auditor's Cross-Finding
> Analysis argued for keeping them separate; that argument does not hold, because
> the two findings cannot be fixed independently and a partial fix of one leaves
> the other open. The consequence differs (stale scheduler vs. absent backup), so
> both consequences are preserved below.
> - **See also:** `OPS-005` (merged here), `OPS-008`, `ENT-002`/`ENT-003` (phase 01
>   — checked, different property, no duplication).

| Field | Value |
|---|---|
| **Severity** | HIGH |
| **Category** | Deployment safety |
| **File(s)** | `.github/workflows/deploy.yml:86, 90, 110, 115`, `docker-compose.prod.yml:120-121, 168-169, 192-193`, `docs/ops/rollback.md:152-157` |
| **Status** | Validated — absorbs OPS-005 |

**Problem.** Three production services are gated behind compose profiles —
`scheduler` (`docker-compose.prod.yml:120-121`), `backup` (`:168-169`) and
`pgbouncer` (`:192-193`) — so they are outside the default service set. The deploy
workflow passes no `--profile` on any of its four compose calls
(`deploy.yml:86, 90, 110, 115`), and its automated rollback branch is narrower
still: `up -d --force-recreate --remove-orphans web bot` (`:115`) names only `web`
and `bot`. The documented manual rollback (`rollback.md:145-150`) uses the same
`web bot` filter, and the runbook's own note justifying it (`rollback.md:152-157`)
enumerates what is "not long-lived" while omitting `scheduler`, which is
`restart: unless-stopped` and runs hourly forever.

**Impact.** Two consequences, both real:

- **Stale scheduler (original limb).** `scheduler` runs `send_alerts` (Telegram
  buyer digests carrying ad titles, prices, cities and working deep links) and
  `consent_hard_delete` (the 30-day PII erasure the privacy policy promises).
  After any deploy it keeps running whatever image it started with, so it can be
  arbitrarily stale. Worse, after a detected-bad deploy the automated rollback
  restores `web` and `bot` while deliberately leaving the scheduler on the image
  that was just judged faulty — continuing to send messages and delete PII under
  code known to be broken. Rollback is not atomic across the long-lived service
  set.
- **No backup (absorbed OPS-005).** The same omission means the daily `backup`
  job is never started and never recreated on a fresh host. Dumps are written to
  `./backups` on the same host via a bind mount, with no copy, encryption or
  off-host replication, so a host loss or a disk failure destroys the database and
  every backup of it simultaneously. The site can then run for days or weeks with
  no daily dump before anyone notices. The 24 h RPO in `restore.md:197` is an
  upper bound on a control that may not be running at all.

**Root cause.** Compose profiles are a local convenience with no deploy-time
awareness: `up -d` silently ignores profile-gated services, and no test or CI
check asserts that the set of long-lived services in `docker-compose.prod.yml`
equals the set the deploy path recreates. The profile gate on `backup` was added
deliberately (`docker-compose.prod.yml:130`: "Opt-in via --profile backup to
prevent storage consumption before needed") and the deploy workflow was written
later against a different service subset. Nothing asserts the production profile
set is complete at deploy time, so the two drift apart silently.

**Evidence — `.github/workflows/deploy.yml:88-90, 112-115`** *(both the main deploy
and the automated rollback omit every profile-gated service)*:

```bash
            # c. Recreate services (brief downtime; acceptable for this classifieds board)
            echo "=== Step 3: Recreate services ==="
            IMAGE_TAG="${IMAGE_TAG}" docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --remove-orphans
...
              echo "=== Step 4b: Recreate services with previous image ==="
              IMAGE_TAG="${PREVIOUS_IMAGE_TAG}" docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate --remove-orphans web bot
```

**Evidence — `.github/workflows/deploy.yml:56-64`** *(a mitigation the auditor
missed, which is why OPS-008 was downgraded — compose interpolation in the deploy
path is satisfied by sourcing `.env.prod`, not by `--env-file`)*:

```bash
            cd /app
            # Capture CI-provided image tag before sourcing .env.prod,
            # which has IMAGE_TAG=latest as its default.
            CI_IMAGE_TAG="${IMAGE_TAG}"
            # Load production environment variables for POSTGRES_* and REGISTRY/REPOSITORY.
            set -a
            source .env.prod
            set +a
```

**Evidence — `docs/ops/rollback.md:152-157`** *(the runbook repeats the same gap
as guidance, and the omission is in the justification itself)*:

```text
   > `up -d` with no service names recreates **all** services. Targeting `web bot`
   > is sufficient for a code-only rollback (the one-shot services `migrate`,
   > `load_catalog`, etc. are not long-lived and will only re-run if their image
   > hash changed and you omit the service filter).
```
*(the enumeration of what is "not long-lived" omits `scheduler`, which is
`restart: unless-stopped` and runs hourly forever)*

**Recommendation (extended to cover the absorbed limb).**

1. Add `--profile scheduler --profile backup --profile pgbouncer` explicitly to
   the `deploy.yml` compose invocations, and include the profile-gated services in
   both recreate commands — `up -d --remove-orphans` (with profiles) for the main
   deploy, and `up -d --force-recreate --remove-orphans web bot scheduler` for the
   rollback. Record the intent in `docs/ops/rollback.md`'s recreate commands and
   fix the `rollback.md:152-157` note.
2. **Structural:** declare the production long-lived service set **once** — a
   single source of truth that `deploy.yml`, the rollback block and the runbooks
   all consume — and add a regression guard asserting that every service with
   `restart:` set in `docker-compose.prod.yml` is named in the deploy recreate
   command. This is the same "contract expressed in one file" gap that Phase 01
   logged as `VAL-003`; it should be one fix, not three.
3. *(Absorbed OPS-005, de-scoped from required to advisory)* Off-host
   replication: `pg_dump` piped to a second destination (object storage or a
   second host) with retention, and a restore path that reads from it. This is a
   platform investment rather than a defect for a single-host Compose deployment
   — land it if the data-loss exposure is accepted as a business risk, and
   document the decision either way.

**Rollout note.** Recreating `scheduler` during a deploy changes when `send_alerts`
fires. `ENT-003` (phase 01) already establishes that the `last_daily` dedupe is
process-local, so a post-08:00 restart re-runs `send_alerts` and produces duplicate
digests plus inflated analytics. Land `OPS-007` together with, or after,
`ENT-003` — otherwise the first deploy that actually starts the scheduler will
send a duplicate digest.

---

### MEDIUM

---

#### OPS-008: [MEDIUM] — Rollback target is a mutable tag, and no digest is ever captured

> **Validation Note:**
> - **Action:** Reclassified — **HIGH → MEDIUM**. The underlying facts are all
>   confirmed, but the impact statement's central claim is **refuted**.
> - **Detail:** The report asserts the rollback is a silent no-op "in exactly the
>   default configuration". It is not, for the repository's own deploy path:
>   `deploy.yml:57-67` deliberately captures the CI-provided tag *before* sourcing
>   `.env.prod` and re-exports it afterwards, precisely so the `IMAGE_TAG=latest`
>   default cannot win. A deployment performed by `deploy.yml` runs a SHA, so the
>   captured previous tag is the prior SHA and the rollback target is correct.
>   The defect is therefore **conditional** — it bites only when a site was last
>   deployed by a manual `docker compose up -d` with the template default of
>   `latest`, which `rollback.md:78` and `:130-136` do document as a path. That is
>   a real exposure but a MEDIUM one, not a HIGH.
> - **See also:** `OPS-002`, `OPS-007`.

| Field | Value |
|---|---|
| **Severity** | MEDIUM (was HIGH) |
| **Category** | Deployment safety |
| **File(s)** | `.github/workflows/deploy.yml:57-67, 71-75, 107-115`, `docker-compose.prod.yml:8`, `.env.prod.example:83`, `docs/ops/rollback.md:78, 130-141` |
| **Status** | Validated |

**Problem.** The rollback target is derived by reading the tag string currently
attached to the `web` container (`docker compose images --format '{{.Tag}}' web |
head -1`, `deploy.yml:74`) and re-pulling that tag (`:110`). Tags are mutable
labels, not identity. No image digest is captured anywhere, and neither is the
`--profile` service set (see `OPS-007`).

**Impact (corrected).** Three residual risks, all conditional on how the site was
last deployed:

1. If a manual `docker compose up -d` was used with the template default
   `IMAGE_TAG=latest` (`.env.prod.example:83`, `docker-compose.prod.yml:8`), the
   previous tag is `latest` — the same mutable reference that was just replaced.
   Re-pulling and force-recreating `latest` reproduces the failing image, the
   post-rollback `/health/ready/` poll fails identically, and the workflow reports
   a rollback attempt with a meaningless success/failure signal.
2. A retagged or force-pushed tag breaks rollback even in the SHA case, because no
   digest is recorded.
3. The digest-absent-from-registry and no-previous-tag branches (`:101-105`) are
   untested.

**Root cause.** The workflow treats an image tag as an identity. The capture step
(`deploy.yml:74`) was written to read a tag because that is what compose keys its
container cache on, and no digest-based record
(`docker inspect --format='{{index .Image}}' "$(docker compose ps -q web)"`) was
added.

**Evidence — `.env.prod.example:81-83`** *(the shipped default tag is mutable)*:

```text
81: REGISTRY=ghcr.io
82: REPOSITORY=manicko/mko_bazuna
83: IMAGE_TAG=latest
```

**Recommendation (unchanged).**

Capture the running image's digest before the pull, or require `IMAGE_TAG` to be a
SHA in `.env.prod` and forbid `latest` in the prod template. Roll back by digest
(`image@sha256:…`) rather than by tag, and record both tag and digest in the deploy
log. Add a guard test asserting `.env.prod.example` does not default `IMAGE_TAG`
to `latest`.

---

#### OPS-010: [MEDIUM] — Bot-marker freshness is disabled in every shipped config, so readiness cannot detect a wedged bot

> **Validation Note:** **Confirmed at MEDIUM.** All four citations verified
> byte-exact, including the absence of the enable flag in the operator's real
> `.env.prod` (checked by key **name** only). The *impact* sentence is overstated
> and is corrected below. This finding is also the check requested against
> `AD-008` (phase 05) — see §8.
> - **See also:** `OPS-007`, `OPS-018`.

| Field | Value |
|---|---|
| **Severity** | MEDIUM |
| **Category** | Reliability / health contract |
| **File(s)** | `src/backend/config/settings/base.py:322-329`, `src/backend/apps/core/views.py:112-129`, `docker-compose.yml:239`, `.env.prod.example` |
| **Status** | Validated |

**Problem.** `readiness_check` verifies the Redis `bot:liveness` marker only when
`BOT_HEALTH_CHECK_ENABLED` is true (`views.py:113-114`), and `base.py:329` defaults
it to `False`. No compose file sets it, it is absent from `.env.prod.example`, and
it is absent from the operator's real `.env.prod`. The base compose sets
`BOT_HEALTH_STALE_SECONDS=120` for `web` (`docker-compose.yml:239`) but never the
enable flag, so the staleness window is configured for a check that is switched
off — a configured-but-disabled control.

**Impact (corrected).** The readiness endpoint — which is the deploy gate
(`deploy.yml:94`) and the documented rollback validation target (`rollback.md:332`)
— cannot observe a bot that is alive but no longer polling: a retry loop, a stuck
long-poll, or a wedged dispatcher all leave `web` reporting `ready` and the deploy
declared successful. The consequence is that **new** ad submissions silently stop
being started by the bot. (The report's phrasing "sellers would see ads accepted
by the bot that are never actually published" conflates this with the FSM/draft
path and is withdrawn: an ad that is already a `DRAFT` row is unaffected by a
stale liveness marker.)

**Root cause.** The coupling was deliberately defaulted off to keep web readiness
independent of bot liveness (`base.py:322-328` documents the reasoning) and the
re-enabling path was never wired into the production configuration, so the
documented "readiness probes DB + cache + bot-marker freshness" control exists
only in code.

**Evidence — `src/backend/config/settings/base.py:322-329`** *(the coupling defaults
off)*:

```python
# When True, the web readiness probe also verifies the Redis bot:liveness marker
# and gates web readiness on it. Defaults to False so web readiness is decoupled
# from bot liveness: when False (the default), the probe reports
# checks["bot"] == "disabled" and does not gate web readiness on the bot.
BOT_HEALTH_CHECK_ENABLED = env.bool("BOT_HEALTH_CHECK_ENABLED", default=False)
```

**Evidence — `docker-compose.yml:239`** *(the staleness window is shipped, the
enable flag is not)*:

```yaml
      - BOT_HEALTH_STALE_SECONDS=120
```

**Recommendation (unchanged).**

Set `BOT_HEALTH_CHECK_ENABLED=true` in `docker-compose.prod.yml`'s `web` service —
it is already the intended coupling, given `BOT_HEALTH_STALE_SECONDS` is shipped
there — and add the key to `.env.prod.example`. If the decoupling is genuinely
wanted, remove `BOT_HEALTH_STALE_SECONDS` from the `web` service and drop the bot
claim from `docs/ops/rollback.md:81, 443` and
`docs/ops/docker-deployment.md:334`, so the documentation matches the intent. Do
not leave a configured-but-disabled probe described as active. Note that Phase 05's
`AD-008` separately establishes that any alerting keyed on moderation-queue depth
can never fire; that is a different signal from this one and the two must not be
conflated in the remediation.

---

#### OPS-011: [MEDIUM] — No operator-alerting channel exists

> **Validation Note:**
> - **Action:** Reclassified — evidence **refuted**, one sub-claim **DUPLICATE-OF
>   API-009**, core finding retained at MEDIUM.
> - **Detail:** The report's stated evidence is false. Its claim that a
>   repository-wide search for `send_mail` / `EmailMessage` / `mail.outbox` over
>   `src/` "returns zero production hits", with "every hit is a test fixture or the
>   allowlist", is contradicted by a real production sender. Consequently the
>   impact sentence "`EMAIL_HOST` is required at boot to protect a delivery path
>   that does not exist" is also false — the delivery path exists.
> - **See also:** `OPS-003`, `OPS-005`/`OPS-007`, `OPS-021`, and **`API-009`
>   (phase 09)** which owns the `send_mail` call site.

| Field | Value |
|---|---|
| **Severity** | MEDIUM |
| **Category** | Observability |
| **File(s)** | `src/telegram_bot/services/support_delivery_email.py:21, 39, 101`, `src/backend/config/settings/base.py:378-402`, `src/backend/config/settings/prod.py:198-208`, `docker-compose.prod.yml:129-169` |
| **Status** | Validated — evidence corrected; `EMAIL_HOST` limb removed as API-009 |

**Problem (corrected).** There is no *operator-alerting* path anywhere in the
system: no management command, service, signal or host-side job inspects container
health, dump freshness, deploy outcome, or the SLO alerts, and no webhook or
Telegram admin-notify command exists.

**Refuted evidence.** `src/telegram_bot/services/support_delivery_email.py:39` calls
`django.core.mail.send_mail` in production, delivering seller support tickets to
`settings.SUPPORT_NOTIFICATION_RECIPIENTS` (or to active EMAIL-channel
`SupportContact` rows), fail-open. `SUPPORT_NOTIFICATION_RECIPIENTS`,
`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` and `DEFAULT_FROM_EMAIL` are configured in
`base.py:378-402`, and `EMAIL_HOST` is a mandatory production gate
(`prod.py:203-208`) — and that gate protects a **real** delivery path. The report's
claim on this point is therefore wrong, and the `EMAIL_HOST` sub-finding is
**dropped from OPS-011** as a duplicate of `API-009` (phase 09), which already
records that the only `send_mail` call site is a fail-open support-desk
notification while `prod.py:198-199` cites "password resets" to justify a
mandatory `EMAIL_HOST`. `prod.py:198-199` and `.env.prod.example:37-39` carry the
same speculative justification; `docs/ops/` contains **zero** occurrences of
"password reset", so `API-009`'s runbook sites lie outside the ops surface and
there is **no** OPS/runbook overlap for that limb.

**Impact (retained).** A container stuck `unhealthy`, a backup job that died, a
nightly `send_alerts` that failed, an SLO breach, and a failed deploy are all
discovered by users filing complaints. This is the detection floor that `OPS-005`
(now `OPS-007`), `OPS-014` and `OPS-021` all depend on — none of those can be
noticed without it.

**Root cause.** Alerting was designed as a Prometheus/Grafana deployment
(`OPS-003`) that was never stood up, and no in-process notification path was built
as a floor.

**Recommendation (unchanged, one substitution).**

Pick one concrete floor and implement it: a `manage.py notify_operator` command
invoked by the `backup` service after each dump and by a small host-side job that
reads `docker compose ps --format json`, delivering via **Telegram bot message**
(the bot already has a transport) rather than SMTP. If a full Prometheus stack is
not going to be deployed soon, delete `docs/ops/prometheus-slo-alerts.yaml` and
`docs/ops/grafana-slo-dashboard.json` or move them under a clearly-labelled
"planned — not deployed" heading, so they stop reading as active controls.

---

#### OPS-013: [MEDIUM] — A malformed `SENTRY_DSN` raises out of the prod settings import and crash-loops every service

> **Validation Note:** **Confirmed at MEDIUM**, with the stated failure triggers
> corrected. Independently reproduced in the shipped image against the installed
> `sentry-sdk 2.69.2`.
> - **See also:** `OPS-011`, `OPS-018`.

| Field | Value |
|---|---|
| **Severity** | MEDIUM |
| **Category** | Observability / error tracking |
| **File(s)** | `src/backend/config/settings/prod.py:69-85`, `src/backend/config/settings/base.py:355-357`, `.env.prod.example:73` |
| **Status** | Validated — trigger mechanism corrected |

**Problem.** `prod.py:72-85` initialises Sentry inside
`if SENTRY_DSN and not DEBUG:` and guards only `ImportError`.
`sentry_sdk.init()` raises `sentry_sdk.utils.BadDsn` for a malformed DSN, and that
exception is not caught. It propagates out of the settings-module import, so every
process that imports `config.settings.prod` (`web`, `bot`, `migrate`,
`load_cities`, `load_catalog`, `create_admin`, `seed`, `scheduler`) fails at import
with `restart: unless-stopped` looping.

**Impact.** A purely optional, non-security integration setting — shipped empty by
default and absent from the operator's real `.env.prod` — can take the entire
production stack offline. The failure mode is maximally confusing: the log shows
a settings-import traceback rather than "SENTRY_DSN is invalid", and the operator's
instinct is to check the secret store rather than the DSN format. The
error-tracking SDK — the component whose whole purpose is to be present when things
go wrong — becomes a source of the outage.

**Corrected trigger mechanism.** The report lists "a leading space, a trailing
newline from a copy-paste, or an unrecognised scheme" as the live triggers. In
`sentry-sdk 2.69.2` the first two are **handled** — both
`' https://key@o1.ingest.sentry.io/2 '` and
`'https://key@o1.ingest.sentry.io/2\n'` initialise cleanly. The live trigger is an
unrecognised or malformed scheme (e.g. a DSN pasted without the
`https://key@host/project-id` shape, or a bare token). The defect is real; the
example set was wrong for the installed version.

**Root cause.** The `try` block was scoped to the "dependency may not be installed"
case and not to the "operator supplied a bad value" case. `SENTRY_DSN` is optional
with a `""` default (`base.py:357`) and is shipped empty in
`.env.prod.example:73`, so the happy path is untested;
`test_prod_logging.py` covers only the *absent* DSN, not a malformed one.

**Evidence — executed in the shipped runtime image** *(an invalid DSN raises
`BadDsn`, which the guard does not catch)*:

```text
sentry-sdk 2.69.2
RAISE sentry_sdk.utils.BadDsn | 'not-a-valid-dsn'
OK    ' https://key@o1.ingest.sentry.io/2 '
OK    'https://key@o1.ingest.sentry.io/2\n'
```

**Recommendation (unchanged).**

Validate the DSN before use (a scheme/`@`/project-id shape check, or a guarded
`except Exception` around `sentry_sdk.init`) and emit a single
`logger.error("SENTRY_DSN is invalid — error tracking disabled")` naming the
variable but not the value, mirroring the value-free style of
`_validate_production_secret`. Add a settings test for a malformed DSN asserting
the import still succeeds.

---

#### OPS-014: [MEDIUM] — Backup job runs as root, has no healthcheck, and deploy backups are never pruned

> **Validation Note:** **Confirmed at MEDIUM.** The validator independently
> re-derived *why* the backup container is root while `db` is not, which is the
> non-obvious part of the finding and the part that makes it actionable. This is
> the strongest single catch in the phase report.
> - **See also:** `OPS-005` (merged into `OPS-007`), `OPS-011`, `OPS-021`.

| Field | Value |
|---|---|
| **Severity** | MEDIUM |
| **Category** | Container runtime / DR |
| **File(s)** | `docker-compose.prod.yml:131-169`, `.github/workflows/deploy.yml:78-82`, `src/backend/tests/test_compose_hardening.py:35-41, 176-181` |
| **Status** | Validated |

**Problem.** Three defects in the backup path.

1. **Runs as UID 0.** The `backup` service declares `cap_drop: ["ALL"]`,
   `read_only: true`, `tmpfs` and `no-new-privileges`, but **no** `user:`
   directive, and it overrides `command:` with `/bin/sh -c …`
   (`docker-compose.prod.yml:141-155`). That override **bypasses the
   `docker-entrypoint.sh` of `postgres:18-alpine`**, which is the mechanism by which
   the `db` service drops to the `postgres` user. With a non-`postgres` first
   argument the entrypoint execs the command directly as the image's default user,
   i.e. root. The validator confirmed the difference is exactly the `command:`
   override, not an oversight in the hardening keys.
2. **No healthcheck.** The service declares none, so Docker cannot distinguish
   "looping and dumping" from "looping and failing".
3. **Deploy backups are never pruned.** `docker-compose.prod.yml:153` prunes
   `dump_*.dump` only, while `deploy.yml:80-81` writes
   `backup-YYYYmmdd-HHMMSS.dump`. Those files accumulate on the production host
   indefinitely. `Makefile:343-345` (`prune-backups`) has the same `dump_*.dump`
   glob.

**Impact.** A root-run container that holds `POSTGRES_PASSWORD` in its environment
and writes to a host bind mount is a wider blast radius than the hardening on the
same block suggests. With no healthcheck and no dump-age alert (`OPS-011`), a job
that has been failing for a week is indistinguishable from a healthy one. And
because pruning never matches the deploy path's filenames, `backup-*.dump` files
accumulate until the disk fills — at which point the database volume is at risk.

**Root cause.** The backup block was written for functional correctness (`pg_dump`
in a loop) and given the standard hardening keys by pattern, but nobody checked
whether the `user` directive, the `command:` override, and the filename
conventions lined up between the two backup producers. The existing guard,
`test_compose_hardening.py:176-181`, asserts `_HARDENING_KEYS` — which is
`["read_only: true", "tmpfs:", "no-new-privileges:true", "mem_limit:", "cpus:"]`
(`:35-41`) and does not include `user:`, so the suite passes on a root container.

**Recommendation (unchanged).**

Add `user: postgres` (or a numeric uid) to the `backup` service; add a healthcheck
that asserts a dump newer than 26 h exists; and align the filename convention —
either have `deploy.yml` write `dump_<ts>.dump` or widen the prune glob in both
`docker-compose.prod.yml:153` and `Makefile:344` to `*.dump`. Add a guard test
asserting every service in the production manifest that is not on an explicit
exception list declares a `user:` **and** does not override `command:` in a way
that bypasses the image entrypoint's privilege drop.

---

#### OPS-016: [MEDIUM] — No `concurrency` group on CI or deploy; overlapping runs race shared refs

> **Validation Note:** **Confirmed at MEDIUM.** Verified by grep across all five
> workflow files. The CI-build limb is a cache-quality problem; the deploy limb
> interacts with `OPS-008` and is the one that matters. No severity change.
> - **See also:** `OPS-002`, `OPS-007`, `OPS-008`, and `OPS-009` (the same
>   duplicate-coordinate problem manifests as a cache miss).

| Field | Value |
|---|---|
| **Severity** | MEDIUM |
| **Category** | CI/CD gating |
| **File(s)** | `.github/workflows/ci.yml:1-7`, `.github/workflows/deploy.yml:1-19` |
| **Status** | Validated |

**Problem.** `ci.yml` and `deploy.yml` declare no `concurrency:` block, unlike
`ci-nightly.yml:8-11` and `restore-test.yml:12-15`, which both do. Two `push`
events minutes apart run two `build` jobs concurrently, each pushing its own SHA
tag but both writing the same `:buildcache` reference. Two `workflow_dispatch`
deploys interleave their `pull` / `up -d` sequences against the same production
host.

**Impact.** Concurrent deploys interleave `docker compose pull` and `up -d`, so
the `PREVIOUS_IMAGE_TAG` one run captures may be overwritten by the other before
it is used, and the health gate can validate a half-applied mix of images.
Concurrent builds corrupt each other's exported build cache (last writer wins) and
burn runner budget re-doing work. Neither failure is loud: both produce green runs.

**Root cause.** The two newest workflows were written with `concurrency` while the
two oldest predate the convention, and no lint or test enforces its presence.

**Recommendation (unchanged).**

Add `concurrency: {group: ci-${{ github.ref }}, cancel-in-progress: true}` to
`ci.yml` and `concurrency: {group: deploy-production, cancel-in-progress: false}`
to `deploy.yml` — never cancel a deploy mid-flight. Add a guard test asserting
every workflow file declares a `concurrency` key.

---

#### OPS-017: [MEDIUM] — Pipeline supply chain: mutable action tags and an unverified `curl | tar` gitleaks fetch

> **Validation Note:** **Confirmed at MEDIUM.** All citations verified. One further
> instance of the same class was found in the image build and is folded in.
> - **See also:** `OPS-001`, `OPS-009`.

| Field | Value |
|---|---|
| **Severity** | MEDIUM |
| **Category** | Supply chain |
| **File(s)** | `.github/workflows/ci.yml:317, 320, 339, 363, 370, 352`, `.github/workflows/deploy.yml:28, 43`, `.github/workflows/restore-test.yml:45, 48, 84, 91`, `.github/dependabot.yml`, `docker/Dockerfile:90-93` |
| **Status** | Validated — one instance added |

**Problem.** Every third-party action in the pipeline is referenced by a mutable
tag: `actions/checkout@v4`, `docker/setup-buildx-action@v3`,
`docker/login-action@v3`, `docker/build-push-action@v7`,
`aquasecurity/trivy-action@v0.36.0`, `github/codeql-action/upload-sarif@v4`,
`astral-sh/setup-uv@v5`, `appleboy/ssh-action@v1.2.0`. The `security` job
additionally downloads the gitleaks binary with
`curl -sSfL …/gitleaks_8.27.2_linux_x64.tar.gz | tar xz` and executes it with no
checksum or signature verification — and that job holds `security-events: write`
and a `GITHUB_TOKEN`. **Validator addition:** the same unverified
`curl … | sh` pattern installs **syft** at image-build time
(`docker/Dockerfile:90-93`, `install.sh` from `raw.githubusercontent.com`), so the
unverified-install class reaches the artefact every deploy ships.

`dependabot.yml` covers the `github-actions` and `uv` ecosystems weekly, so tags
will be bumped — but a tag is a pointer, not a pin.

**Impact.** The pipeline that is supposed to be the trust boundary is itself the
least-pinned part of the system. A compromised or hijacked upstream tag — plausible
for `appleboy/ssh-action`, a small third-party action that receives the production
SSH private key as a secret — executes with the pipeline's token on every run. The
unverified gitleaks tarball is the same class, and it is the step that decides
whether a secret is allowed into the repository. The unverified syft install means
the shipped image's toolchain provenance is unverified at every build.

**Root cause.** Action pinning was never adopted; the `security` job needed a tool
that is not a GitHub Action and the quickest route was a pipe-to-shell install,
which is the exact pattern the job exists to prevent elsewhere.

**Recommendation (extended).**

Pin all actions to full commit SHAs with the version in a trailing comment
(Dependabot keeps these updated). Replace the gitleaks pipe with a maintained
action or a `sha256sum --check` against a checksum committed to the repository.
**Add the same treatment to `docker/Dockerfile:90-93`** — pin syft to a released
version with a verified checksum, or install it from a pinned base image. Both
changes are mechanical and Dependabot-compatible.

---

#### OPS-018: [MEDIUM] — Ops documentation asserts controls that are not live

> **Validation Note:**
> - **Action:** Reclassified — one sub-claim **refuted**, two sub-claims
>   **partially wrong**, four further instances **added** (including the strongest
>   one). Severity retained at MEDIUM; the finding is strengthened, not weakened.
> - **Detail:** The report's `bazuna_db` claim is false —
>   `.env.prod.example:22` **is** `POSTGRES_DB=bazuna_db`. The bot-readiness claim
>   overstates: `rollback.md:321-323` documents the `"disabled"` value correctly,
>   so the defect is an internal contradiction between `rollback.md:81, 443` and
>   `rollback.md:321-323`, not a uniformly wrong document. The report missed the
>   single clearest instance of the whole class, at
>   `docs/ops/docker-deployment.md:431-436`.
> - **See also:** `OPS-001`, `OPS-003`, `OPS-006`, `OPS-010`, `OPS-013`, and
>   `CFG-002` (phase 02, correctly **not** re-filed here).

| Field | Value |
|---|---|
| **Severity** | MEDIUM |
| **Category** | Documentation |
| **File(s)** | `docs/ops/docker-deployment.md:427, 431-436, 1011-1015`, `docs/ops/rollback.md:79, 81, 110-113, 138-141, 321-323, 443`, `docs/ops/restore.md:25, 83, 91-92`, `docs/ops/prometheus-slo-alerts.yaml:9` |
| **Status** | Validated — claims corrected and extended |

**Problem (corrected).** Several passages in `docs/ops/` describe controls that
either do not run or cannot work.

**Confirmed instances:**

| Location | Claim | Reality |
|---|---|---|
| `docker-deployment.md:427` | the `deploy-check` job sets `REDIS_URL=redis://redis:6379/0` and is a blocking gate | `ci.yml:510-518` sets no `REDIS_URL` and no `EMAIL_HOST`; the job aborts on import. That defect is `CFG-002` (phase 02) and is deliberately **not** re-filed here — only the documentation claim is in scope. |
| `docker-deployment.md:1013-1015` | "An external Prometheus instance scrapes it on its own schedule" | `nginx.conf:159-162` returns `403` to any scraper outside `127.0.0.1`, and no Prometheus is deployed. |
| `docker-deployment.md:431-436` *(validator addition — the strongest instance)* | the CI `security` job "runs `bandit` … against `src/backend` and `src/telegram_bot` per the `[tool.bandit]` config", spelling out the test-dir exclusions | `OPS-001`: the step never executes against any file. This paragraph is the most explicit false claim in the ops surface, because it not only asserts the control but explains its configuration. |
| `rollback.md:79` | `git checkout .env.prod` to pinned commit is the config-rollback procedure | `.env.prod` is gitignored and untracked (`.gitignore:144-148`), so this cannot work. *(Validator addition: `rollback.md:110-113` gives the same impossible recipe — `git log --oneline -10 -- .env.prod` and `git show <commit>:.env.prod`.)* |
| `rollback.md:81, 443` | `checks.bot == "ok"` is the rollback validation criterion | the probe reports `"disabled"` in every shipped config (`OPS-010`). *(Partially wrong: `rollback.md:321-323` documents `"disabled"` and states it is now the default — so the defect is the contradiction.)* |
| `rollback.md:138-141` *(validator addition)* | "All seven services in `docker-compose.prod.yml` (lines 8, 18, 28, 36, 44, 54, 63) reference `${IMAGE_TAG:-latest}`" | the actual `image:` lines are at **8, 23, 33, 41, 49, 59, 68, 85** — **eight** services, none of the cited line numbers except 8 matching. |
| `prometheus-slo-alerts.yaml:9` *(validator addition)* | `/metrics` restricted via `docker/nginx/nginx.conf:156` | the restriction is at `nginx.conf:160-162`. |

**Refuted sub-claim — must be deleted.** The report asserts "`restore.md:83` names
the production database `bazuna_db`, a name that appears in no template." That is
false: `.env.prod.example:22` is `POSTGRES_DB=bazuna_db`. The real defect at
`restore.md` is different and already covered by `OPS-006` — `:25` and `:91-92`
source the name from **`.env.dev`**, which holds a different value, so the runbook
points at the wrong database rather than at an unknown one.

**Impact.** The ops documentation is the only description of the production
system, and a reader cannot tell which parts are live. An engineer planning
capacity or on call during an incident will reason from a burn-rate alerting
setup, a bot-marker readiness gate, a config-rollback-by-git procedure, and a
working SAST step — none of which work as described. Because these are narrative
claims rather than code, no test fails when they drift.

**Root cause.** The docs were written when each control was added, and each
control was subsequently changed, disabled or found not to work (`OPS-001`,
`OPS-003`, `OPS-006`, `OPS-010`) without a doc pass. The project rule
"documentation must always stay current" is machine-enforced for i18n
completeness but not for ops claims. The stale `docker-compose.prod.yml` line
references at `rollback.md:138-141` show the drift is not confined to control
claims — ordinary file anchors have rotted too.

**Recommendation (extended).**

Bring `docs/ops/` back in line with the repository:

1. `docker-deployment.md:431-436` — correct or delete the SAST paragraph (this
   depends on `OPS-001` landing first; see the dependency chain in §7).
2. `docker-deployment.md:1011-1015` — state that no Prometheus/Grafana stack is
   deployed and that the alert rules and dashboard are aspirational.
3. `docker-deployment.md:427` — drop the `REDIS_URL` claim.
4. `rollback.md:79` and `:110-113` — replace `git checkout`/`git log` on
   `.env.prod` with a documented off-repo config-versioning procedure.
5. `rollback.md:81, 443` vs `:321-323` — make the readiness criterion match what
   the probe returns today (or fix the probe via `OPS-010` first).
6. `rollback.md:138-141` — correct the service count and line references.
7. `prometheus-slo-alerts.yaml:9` — correct the `nginx.conf` reference.

Then extend the existing `test_docs_ci_parity.py` pattern to assert that every
`ghcr.io` literal, every `docker compose` command's flags, and every env-var name
quoted in `docs/ops/` appears in the corresponding live file. **The parity test
must not encode today's wrong claims as truth** — write it only after the docs are
corrected.

---

### LOW

---

#### OPS-012: [LOW] — Gunicorn access and error logs bypass the redacting JSON formatter

> **Validation Note:** **Reclassified — MEDIUM → LOW.** All three facts are
> confirmed, but both claimed impacts are weak. The security impact is explicitly
> speculative ("any *future* query-string parameter that carries a token"), and the
> `django.server` 4xx-discard consequence is a deliberate consequence of a
> production root level of `WARNING`, not a defect. What remains is log-format
> consistency and aggregator ergonomics — operational hygiene, which is precisely
> the class of item ops audits tends to inflate.
> - **See also:** `OPS-003`, `OPS-011`.

| Field | Value |
|---|---|
| **Severity** | LOW (was MEDIUM) |
| **Category** | Observability / logging |
| **File(s)** | `gunicorn.conf.py:29-35`, `src/backend/config/settings/prod.py:22-67`, `src/backend/apps/core/utils/json_logging.py:68-93` |
| **Status** | Validated — severity reduced |

**Problem.** Production configures a structured `LOGGING` dict with
`RedactingJsonFormatter` for the `django*` and `apps*` logger trees
(`prod.py:22-67`) and sets the root logger to `WARNING`. Gunicorn's own
`accesslog`/`errorlog` are `"-"` (stdout/stderr) at `loglevel = "info"`
(`gunicorn.conf.py:29-35`); those are emitted by gunicorn's own handlers and never
pass through the Django `LOGGING` tree or the redactor, and there is no
`logconfig_dict`.

**Impact (reduced).** The production log stream is a mixture of JSONL and
unstructured plaintext, with the highest-volume record type — the access log — in
the unstructured form. A log aggregator cannot parse the two uniformly. No
currently demonstrated security exposure exists: the redaction gap is a property of
the *format*, not of any parameter the application emits today.

**Recommendation (unchanged).**

Route gunicorn through the same formatter (`logconfig_dict` in
`gunicorn.conf.py` pointing `gunicorn.access`/`gunicorn.error` at a
`RedactingJsonFormatter` handler) and set a structured `access_log_format` that
emits named fields rather than a raw request line. Alternatively, set
`accesslog = None` and instrument request metrics/IDs through Django, where the
redaction already applies. This is a P2 item; do not let it compete with
`OPS-007` for the same deploy window.

---

#### OPS-015: [LOW] — PgBouncer is configured for md5 auth against PostgreSQL 18 SCRAM verifiers

> **Validation Note:** **Reclassified — MEDIUM → LOW.** The mechanism is correct;
> the impact statement is **false** and is withdrawn.
> - **See also:** `OPS-005` (merged into `OPS-007`).

| Field | Value |
|---|---|
| **Severity** | LOW (was MEDIUM) |
| **Category** | Configuration |
| **File(s)** | `docker-compose.prod.yml:171-201`, `src/backend/config/settings/base.py:248-250, 261` |
| **Status** | Validated — severity reduced, impact withdrawn |

**Problem.** The opt-in `pgbouncer` service sets `PGBOUNCER_AUTH_TYPE=md5` with
`PGBOUNCER_USER=${POSTGRES_USER}` (`docker-compose.prod.yml:180`), the same role
whose password the PostgreSQL 18 image stores using the engine default. That
default is `scram-sha-256` (unchanged since PostgreSQL 14), and `pg_authid.rolpassword`
then holds a `SCRAM-SHA-256$…` verifier, which an md5 authenticator cannot use.
The rest of the application is explicitly designed for this pooler
(`base.py:248-250` sets `prepare_threshold: None`, `base.py:261` sets
`CONN_MAX_AGE = 0`).

**Impact (withdrawn).** The report states "Anyone following the documented
connection-pooling guidance would redirect the application at a component that
cannot authenticate." There is **no** such documented guidance: a case-insensitive
search for `pgbouncer` across all nine `docs/ops/*.md` files returns **zero**
hits. The service is profile-gated and entirely undocumented, and its own
healthcheck (`pg_isready` at `:187-191`) does not exercise authentication, so
nothing in the repository would ever cause anyone to enable it. The residual
defect is a latent misconfiguration in an unreferenced opt-in profile.

**Recommendation (unchanged).**

Set `PGBOUNCER_AUTH_TYPE=scram-sha-256` (PgBouncer ≥1.19 supports SCRAM verifiers
in `auth_file`). Do **not** spend effort documenting the profile as available until
someone intends to use it — documenting an unused profile is how the current
latent state became invisible. Add a settings test asserting that whenever the
PgBouncer profile's `PGBOUNCER_AUTH_TYPE` is set, it matches the engine's
`password_encryption` default.

---

#### OPS-019: [LOW] — `db`/`redis` healthchecks have no `start_period`

> **Validation Note:** **Confirmed at LOW.** All citations exact; the impact
> statement is appropriately hedged (it already notes that `restart: always`
> recovers). One-line fix per service.
> - **See also:** `OPS-007`.

| Field | Value |
|---|---|
| **Severity** | LOW |
| **Category** | Reliability |
| **File(s)** | `docker-compose.yml:23-27, 41-45` |
| **Status** | Validated |

**Problem.** The `db` and `redis` healthchecks declare `interval`, `timeout` and
`retries` but no `start_period` (Docker's default is 0), so a failing probe counts
toward `retries` immediately. Every other long-lived service does declare one
(`docker-compose.yml:259` → 5 s, `:302` → 30 s,
`docker-compose.prod.yml:127` → 30 s), and every bootstrap service gates on
`condition: service_healthy` against `db` and/or `redis`.

**Impact.** On a cold start or a host reboot, PostgreSQL 18 needs several seconds
for crash recovery and to reach `pg_isready`; if it misses `retries: 5` at a 5 s
interval the container is marked `unhealthy` before it was given a chance, and the
`depends_on` chain fails to start. `restart: always` eventually recovers, so the
failure surfaces as a cascade of one-shot services exiting non-zero rather than as
"database still starting" — which is confusing but not an outage.

**Recommendation (unchanged).**

Add `start_period: 30s` to both the `db` and `redis` healthchecks — a one-line
change per service, safe in every environment. Extend
`test_compose_hardening.py` to assert every healthcheck block in
`docker-compose.yml` and `docker-compose.prod.yml` declares a `start_period`, so
the next service added cannot regress it.

---

#### OPS-020: [LOW] — Public readiness endpoint exposes internal dependency state

> **Validation Note:** **Confirmed at LOW.** Both citations exact; the nginx
> comment even names the gap. The report's own rollout row already flags the
> compatibility trade-off, which is the real constraint on the fix.
> - **See also:** `OPS-003`.

| Field | Value |
|---|---|
| **Severity** | LOW |
| **Category** | Security |
| **File(s)** | `docker/nginx/nginx.conf:130-137, 159-168`, `src/backend/apps/core/views.py:131-138` |
| **Status** | Validated |

**Problem.** nginx proxies `location /health/` (`nginx.conf:131-137`) with no
`allow`/`deny` and no `limit_req` — the block's own comment at `:130` reads "Health
check endpoint (no rate limiting, no auth)" — while the view returns
`{"version": 1, "status": "ready", "checks": {"database": "ok", "cache": "ok",
"bot": "disabled"}}`, or, when degraded, exactly which of database, cache and bot
has failed (`views.py:131-138`). The `/metrics` endpoint declared immediately below
(`:159-168`) is correctly restricted to `127.0.0.1`; the health endpoints are not.

**Impact.** An anonymous caller can poll readiness and read both service
availability and the identity of the failing dependency. The liveness/readiness
split is otherwise sound, so the exposure is small — but it is free to close.

**Recommendation (unchanged, with the compatibility check named).**

Restrict `/health/` the same way `/metrics` is restricted — `allow 127.0.0.1` plus
a dedicated internal listener, or `limit_req` plus a reduced public body. If the
endpoints must stay public for an external uptime probe, return only
`{"status": "alive"}` from the public alias and keep the per-dependency breakdown
on an internal-only path. **Before landing, confirm no external uptime monitor
currently reads `/health/`** — the report's own rollout table flags this as the one
non-backward-compatible item in the whole phase.

---

#### OPS-021: [LOW] — Backup loop has no drift compensation or freshness assertion; dead comment in `ci.yml`

> **Validation Note:** **Confirmed at LOW.** Both limbs verified exactly. Thematically
> merged with `OPS-007`/`OPS-014` but kept separate: the fixes are independent and
> the `ci.yml` comment has nothing to do with backups.
> - **See also:** `OPS-005` (merged into `OPS-007`), `OPS-011`, `OPS-014`.

| Field | Value |
|---|---|
| **Severity** | LOW |
| **Category** | Maintainability |
| **File(s)** | `docker-compose.prod.yml:147-155`, `.github/workflows/ci.yml:375-382, 508` |
| **Status** | Validated |

**Problem.** The backup loop is `pg_dump … ; sleep 86400`, so the true interval is
24 h plus the dump duration and any retry delay, and nothing anywhere asserts that
the newest dump is recent. Separately, `ci.yml:375-381` is a seven-line comment
explaining the `deploy-check` gate — that it "replaces" a previous test-settings
step, why no DB service container is needed, that the env vars are placeholders —
sitting immediately above the `load-test:` job key at `:382`, while `deploy-check`
is declared 126 lines later at `:508`.

**Impact.** Neither is an outage on its own. The drift makes the effective RPO
slightly worse than the documented 24 h with no way to measure it, and the
misplaced comment means the next editor working on `load-test` reads rationale that
does not apply to it, while the rationale for the actual gate sits 130 lines from
the code it explains.

**Evidence — `.github/workflows/ci.yml:375-384`** *(the `deploy-check` rationale is
attached to the `load-test` job)*:

```yaml
  # Deploy-check gate (OPS-001): run manage.py check --deploy against the
  # production settings module so deployment warnings (W-series) fail the
  # build. The previous step ran against config.settings.test and produced
  # 6 false-positive warnings that masked real gaps. No DB service container
  # is required: check --deploy is static (no custom deploy checks, no DB
  # connection). All required production env vars are set to valid non-secret
  # placeholders so the full prod settings import path is exercised.
  load-test:
    runs-on: ubuntu-latest
    needs: build
```

**Recommendation (unchanged).**

Compute the sleep from the dump's own start time (`sleep $(( 86400 - elapsed ))`)
and add a `healthcheck` to the `backup` service asserting a dump newer than 26 h
exists — this closes the detection gap named in `OPS-007` and `OPS-011` with the
smallest possible change. Move the `ci.yml:375-381` comment to sit directly above
`deploy-check:`. Also fix the comment's own header, which cites "OPS-001" — in this
phase `OPS-001` is the bandit finding, not the deploy-check gate; the reference
predates the ID scheme and now points at the wrong thing.

---

## 6. Merged Findings

| Original ID | Merged Into | Rationale |
|---|---|---|
| **OPS-005** | **OPS-007** (Phase 12) | Identical root cause (compose profiles invisible to the deploy path) and an identical fix (add `--profile backup --profile scheduler --profile pgbouncer` to the `deploy.yml` and runbook compose invocations). The auditor's Cross-Finding Analysis kept them separate on the grounds that "each has an independent consequence and an independent fix" — the consequences do differ (absent backup vs. stale scheduler) but the fix does not, so a partial fix of one leaves the other open. Both consequences are preserved in the merged OPS-007 body. OPS-005 additionally over-scoped: "single-host, same-volume, no off-host replication" is a design choice appropriate to a single-host Compose deployment, not a defect, and is demoted to an advisory. **OPS-005 is removed as a standalone entry; its title, evidence and impact are absorbed into OPS-007.** |

No other merge candidates were found. `OPS-001` and `OPS-018` share a root-cause
*theme* (guards and docs describe controls that do not function) but have different
fixes, different owners and different files; keeping them separate is correct.
`OPS-014` and `OPS-021` both concern the backup loop and could be implemented in
one commit, but the fixes are independent and only one is about the loop.

---

## 7. Rejected Claims and Withdrawn Sub-Findings

Nothing is rejected wholesale. Four specific claims in the source report are
refuted and must not survive into the final document:

| Claim | Location in source report | Status | Basis |
|---|---|---|---|
| "the static-analysis gate … reports success", "`CI_FORM_EXIT=0`", "Total lines of code: 0" | OPS-001, runtime row R-06 | **REFUTED** | Reproduced with the CI step's exact CWD and flags: bandit aborts with `ERROR pyproject.toml : Could not read config file.` and exits **2**. The quoted transcript is what you get when `-c` is dropped entirely — i.e. it is not the CI command. |
| "117 findings (81 medium / 36 high)" | OPS-001, runtime row R-07, recommendation | **REFUTED** | Reproduced with the repository's own `[tool.bandit]`: **114 issues — Low 104, Medium 10, High 0**; confidence Medium 77 / High 37. 81/36 matches neither table. |
| "Commit a baseline rather than silencing the rule" | OPS-001 recommendation | **REJECTED as strategy** | The backlog is 64 test-fixture `B106`s plus 25 informational `subprocess` items; 0 High. A baseline would institutionalise them and permanently permit new hardcoded credentials in production code. Triage by class instead (§ OPS-001). |
| "A repository-wide search … returns zero production hits … zero senders"; "`EMAIL_HOST` … protects a delivery path that does not exist" | OPS-011, problem + impact, runtime row R-22 | **REFUTED / DUPLICATE-OF `API-009`** | `src/telegram_bot/services/support_delivery_email.py:39` calls `django.core.mail.send_mail` in production. The `EMAIL_HOST` sub-finding is exactly what `API-009` (phase 09) already records. |
| "`restore.md:83` names the production database `bazuna_db`, a name that appears in no template" | OPS-018 | **REFUTED** | `.env.prod.example:22` is `POSTGRES_DB=bazuna_db`. The real defect is that `restore.md:25, 91-92` source the name from `.env.dev` — already covered by `OPS-006`. |
| "Every documented `docker compose` invocation in the two incident runbooks omits `--env-file .env.prod`" | OPS-006, problem | **REFUTED (universal quantifier)** | `rollback.md:147-149`, `rollback.md:432-434` and `docker-deployment.md:420` all pass `--env-file .env.prod` correctly. The claim holds for `restore.md` only. |
| "rollback is a no-op in exactly the default configuration" | OPS-008, impact | **REFUTED** | `deploy.yml:57-67` captures the CI tag before sourcing `.env.prod` and re-exports it after, specifically to defeat the `latest` default. The exposure is conditional on a manual deploy. |
| "Anyone following the documented connection-pooling guidance …" | OPS-015, impact | **REFUTED** | Zero occurrences of `pgbouncer` in any `docs/ops/*.md`. There is no documented guidance. |
| "Sellers would see ads accepted by the bot that are never actually published" | OPS-010, impact | **WITHDRAWN** | A stale liveness marker means new submissions are not *started*; already-persisted `DRAFT` rows are unaffected. |

---

## 8. Cross-Phase Reconciliation

Checked against the eleven already-validated phases. **No OPS finding is rejected as
a duplicate of a validated finding**; one sub-claim is a duplicate and is removed.

| Validated finding | Relationship to this phase | Verdict |
|---|---|---|
| **`CFG-002`** (phase 02, CONFIRMED HIGH) — the CI `deploy-check` job cannot import `config.settings.prod`; it has not run since `8be3638` | `OPS-018` cites `docker-deployment.md:427` and re-quotes the job's env block from `ci.yml:510-518` as evidence for a **documentation** claim only | **Correctly scoped, no duplication.** The source report explicitly declines to re-file the code defect. Both must be remediated in the same pass: `CFG-002` makes the doc's "blocking gate" claim false in the strongest way. *Interaction:* `CFG-002` is also what makes `OPS-002`'s recommendation (2) load-bearing — a constrained deploy input is only safe if some automated prod-config gate actually runs. **Land `CFG-002` before `OPS-002`.** |
| **`CFG-001`** (phase 02, HIGH→MEDIUM) — `DJANGO_ONESHOT`/`DJANGO_BUILD` disable all eight prod secret guards; `check --deploy` is non-fatal | No OPS finding re-files this | **No overlap.** |
| **`CFG-006`** (phase 02) — a bot-only config error crash-loops the whole dev stack | `OPS-013` is a *production* analogue: a `SENTRY_DSN` value error takes down every prod service at settings import | **Related, not duplicated.** `OPS-013` is independently confirmed and is a different setting in a different environment. It does show the pattern is systemic: optional integrations that raise during settings import are unguarded everywhere. |
| **`ENT-002`** (phase 01, CONFIRMED HIGH) — the scheduler ignores SIGTERM | `OPS-007` touches the scheduler **only** for image-version atomicity | **No duplication** — a different property of the same service. The source report's Cross-Finding Analysis states this correctly. |
| **`ENT-003`** (phase 01, HIGH) — `last_daily` dedupe is process-local | Referenced in `OPS-007`'s rollout table as a constraint | **Correctly handled** — and it is a real sequencing constraint: see §9. |
| **`ENT-001`** (phase 01) — `child_exit` can kill the arbiter when `PROMETHEUS_MULTIPROC_DIR` is unset | Not re-filed | **No overlap.** |
| **`ENT-004`** (phase 01, HIGH) — CI lint/typecheck scoped to `src/backend` only; the bot process is excluded | Related in kind to `OPS-001` (a gate that does not cover what it claims) but a different pipeline job and a different excluded tree | **No duplication.** Both should be noted in the same "the gates do not cover what they say" cluster when the final report is assembled. |
| **`DB-004`** (phase 03, HIGH) — no `lock_timeout`/`statement_timeout` anywhere in `src/` or `docker/` | **Not covered by the OPS report at all** | **GAP → `VAL-002`.** Validator independently reconfirmed 0 matches across `src/` and `docker/`. The consequence (unbounded lock/statement waits) is `DB-004`'s; the *ops-surface* consequence — the `migrate`, `backup`, `load_cities` and `load_catalog` one-shot containers also run with no statement cap, so a stuck `pg_dump` or `bootstrap_reference_data` is indistinguishable from a slow one and nothing prunes it — is in the ops layer's scope and is stated nowhere. |
| **`DB-008`** (phase 03, HIGH) — `archive_sweep` and `recompute_normalized_prices` use whole-sweep transactions | Not re-filed | **No overlap.** |
| **`AD-008`** (phase 05, MEDIUM) — `ON_MODERATION` is never committed, so `get_pending_queue_size()` is structurally 0; any alerting keyed on "pending moderation == 0" can never fire | **Checked explicitly, as requested. The OPS report contains no such metric.** OPS-003 inventories all three alert rules and none references moderation queue depth; OPS-011 recommends alert surfaces (dump age, container health, deploy outcome) with no moderation-queue alert among them | **No duplication and no missed detection.** This is a clean result: because no Prometheus is deployed at all, the structural-zero bug in `AD-008` has not been operationalised. The risk is prospective — if `OPS-003` lands, a naive `pending_moderation` alert would be dead on arrival, and `OPS-003`'s recommendation should carry that warning forward. |
| **`API-008`** (phase 09, MEDIUM) — `load_exchange_rates` is a hard-coded 2026-08-22 seed that overwrites operator edits on every boot | **Checked, as requested, for backup/restore overlap. None found.** The ops surface has no mention of exchange rates; `restore.md` covers `pg_dump`/`pg_restore` and `migrate --plan --check` only. `OPS-004`'s recommendation (a row-count precondition on restore) is orthogonal to the seed-overwrite defect | **No overlap, no missed detection.** |
| **`API-009`** (phase 09, MEDIUM) — no password-reset or transactional-email flow exists, even though `prod.py:198-199` cites "password resets" to justify mandatory `EMAIL_HOST`; the sole `send_mail` call site is a fail-open support-desk notification | `OPS-011` re-derived the same fact and reached the opposite conclusion ("zero senders"). `OPS-018` quotes `prod.py` only via `OPS-011` | **`OPS-011`'s `EMAIL_HOST` limb is a DUPLICATE-OF `API-009` and is removed.** The speculative justification at `prod.py:198-199` and `.env.prod.example:37-39` is correctly attributed to `API-009`. Note: `docs/ops/` contains **zero** occurrences of "password reset", so `API-009`'s five runbook sites lie **outside** the ops documentation surface and there is no OPS-side instance to correct. |
| **`SRCH-001`** (phase 08, CRITICAL) — unbounded `?features=` joins 120+ tables; the kill is the cgroup OOM killer; `DB_MEM_LIMIT` is unset in all three `.env.*` files so the 1 GB cap ships to production; `statement_timeout`/`lock_timeout` are zero repo-wide | **Checked explicitly, as requested. The OPS report does not cover `DB_MEM_LIMIT` or any container memory limit** | **GAP → `VAL-001`.** This is the most consequential coverage gap in the phase. The `mem_limit` layer is squarely the ops layer's responsibility — `docker-compose.yml:15` sets `mem_limit: ${DB_MEM_LIMIT:-1g}`, and the validator confirmed that **no** `*_MEM_LIMIT` or `*_CPUS` key exists in `.env.dev`, `.env.test` or `.env.prod`, so every environment falls back to the compose default. `SRCH-001` owns the OOM consequence; the ops layer owns the absence of a capacity-limit inventory and of any guard test over the `mem_limit` keys. The two must be cross-referenced, not independently fixed. |
| **`TEST-002`** (phase 11, HIGH) — CI never loads `[tool.coverage.*]`, so `fail_under=80` is inert and `src/telegram_bot` is absent from the coverage report | Not re-filed | **No overlap.** Worth noting alongside `OPS-001`: both are gates that are configured but not effective, and both are in the same "the pipeline asserts controls it does not deliver" cluster. |

**Net cross-phase outcome:** zero OPS findings rejected as duplicates; one sub-claim
(OPS-011 / `EMAIL_HOST`) removed as a duplicate of `API-009`; one merge (OPS-005 →
OPS-007); two coverage gaps raised against the OPS report itself (`VAL-001`,
`VAL-002`); one explicit clean check on `AD-008`; one explicit clean check on
`API-008`.

---

## 9. Rollout Analysis

### Dependency chains and safe ordering

The remediation set is not order-independent. The safe sequence:

1. **`OPS-001` (paths + exclusion config) must land before `OPS-018`'s SAST
   paragraph is rewritten.** Rewriting the doc first would encode either a wrong
   claim or a claim about a step that still fails. Land the path fix, triage the
   114 findings, and *then* correct `docker-deployment.md:431-436`.
2. **`CFG-002` (phase 02) should land before `OPS-002`.** `OPS-002`'s
   recommendation — require a green `CI` run for the dispatched SHA — is only
   meaningful if the `deploy-check` job inside that run actually executes. Today it
   has not run since `8be3638`.
3. **`OPS-009` (single image coordinate) should land before `OPS-002`'s
   constraint.** Otherwise the deploy gate would assert on an image coordinate that
   may name the wrong repository.
4. **`ENT-003` (phase 01) should land before or with `OPS-007`.** `OPS-007` is what
   first makes the scheduler actually start on a deploy. `ENT-003` establishes that
   a post-08:00 restart re-runs the non-idempotent `send_alerts`, producing
   duplicate buyer digests and inflated analytics. The first `OPS-007` deploy is
   therefore a live trigger for `ENT-003`.
5. **`OPS-005`/off-host replication must land before `OPS-004`'s real-artifact
   drill can pass.** An off-host copy of the newest dump is what makes a *real*
   restore-test possible, and a real restore-test is what makes the RPO/RTO numbers
   at `restore.md:195-226` meaningful. Landing `OPS-004` without it is not possible
   at all.
6. **`OPS-011` is the detection floor for `OPS-007`, `OPS-014` and `OPS-021`.**
   None of those three can be *noticed* without it. It does not block their
   implementation, only their verification.
7. **`OPS-006` before `OPS-018`.** The runbook flag corrections are part of the docs
   sweep; extracting the runbook shell blocks into executable scripts
   (`scripts/ops/*.sh`) should happen first so the docs sweep has something stable
   to reference.
8. **`OPS-020` is the only non-backward-compatible change in the phase.** An
   external uptime monitor currently reading `/health/` would begin receiving
   `403`. Confirm no such consumer exists before landing.

### Rollout-safety issues detected during validation

- **No circular dependencies** among the OPS findings.
- **One hidden dependency**: `OPS-007`'s value is unverifiable without `OPS-011` —
  there is currently no way to observe that the scheduler started, stayed fresh, or
  is running the new image. The deploy health gate only polls `web`.
- **One fragile insertion point**: the remediation roadmap orders `OPS-006`
  (runbook fix) second and `OPS-007` (scheduler/backup profiles) third, both P0,
  on the assumption they are independent edits to different files. They are not —
  both add `--profile` flags to the same compose invocations, and `rollback.md` is
  touched by both. Sequencing them in separate pull requests will conflict on
  `docs/ops/rollback.md` and on `deploy.yml`. **Merge them into one change.**
- **Rollback for `OPS-012`**: `logconfig_dict` changes gunicorn startup. A malformed
  log config crashes the arbiter before the server binds, turning a logging change
  into an outage. Test the config in a throwaway container first, and keep
  `accesslog`/`errorlog` set until the new handler is proven.

### Test gaps (must be closed by the fix, in the same change)

| Finding | Gap |
|---|---|
| OPS-001 | No test distinguishes a working SAST step from a no-op. Add an assertion on scanned-file count, and a test that the configured paths exist. |
| OPS-002 | No test covers workflow trigger wiring. Add structural guards for `pull_request` and for a deploy↔CI dependency. |
| OPS-003 | No test evaluates a PromQL selector against a live scrape. Add one. |
| OPS-004 | No test asserts the restored database is non-empty. Add row-count preconditions to the `Makefile` target. |
| OPS-005/OPS-007 | No test asserts the long-lived prod service set matches the deploy recreate set. Add a guard keyed on `restart:` in `docker-compose.prod.yml`. |
| OPS-006 | No test compiles the shell blocks in the runbooks. Extract them into scripts and lint them. |
| OPS-008 | Digest-based rollback is a new code path. Cover the "no previous digest" and "digest absent from registry" branches. |
| OPS-009 | No test asserts image-coordinate consistency across workflows. Add a literal-scan guard. |
| OPS-010 | Turning the bot check on makes `web` readiness return 503 when the bot is down. Cover that path in the deploy-gate tests. |
| OPS-013 | Add the malformed-DSN settings test. |
| OPS-014 | `user: postgres` on a `read_only` container — assert the bind mount stays writable and the loop still dumps. |
| OPS-016 | `cancel-in-progress: true` on CI can cancel a needed build. Verify branch-protection semantics after landing. |
| OPS-019 | Extend `test_compose_hardening.py` to assert every healthcheck block declares a `start_period`. |
| OPS-020 | Confirm no external uptime probe depends on a public `/health/`. |
| OPS-021 | Drift compensation changes the backup cadence. Assert the loop still sleeps between runs. |

---

## 10. Findings That Genuinely Require Structural or Architectural Change

Everything else in this phase is a bounded, local, low-risk edit. Six findings need
a structural change — a contract, a source of truth, or a new component — rather
than a patch:

1. **`OPS-007` (absorbing `OPS-005`) — the production service-set contract.** The
   production long-lived service set must be declared **once** and consumed by
   `deploy.yml`, the rollback block, and the runbooks. Today it is expressed three
   times, in three places, and they disagree. This is the same "contract expressed
   in one file" gap that Phase 01 logged as `VAL-003`; it should be one fix, not
   three, and it is the single highest-leverage change in the phase.
2. **`OPS-003` — the monitoring topology and the alert file.** The project must
   either deploy a scrape-and-evaluate stack or formally retire the SLO artifacts.
   Keeping a hand-written PromQL file that is never evaluated is the defect. The
   durable fix is a scrape-contract test, which turns a narrative artefact into a
   verified contract.
3. **`OPS-004` — the DR drill must consume a real artifact.** This requires a new
   off-host artifact path and a non-empty-restore precondition. It cannot be closed
   by editing the workflow, and it is the only finding whose fix makes a
   *documented* number (RPO 24 h / RTO ≈4 h) true.
4. **`OPS-002` — deploy provenance.** A deploy must be derived from a green CI run
   for a specific immutable artefact, not from a free-text input plus a human
   checkbox. Together with `OPS-008` this is the "tags are not identity" correction
   and should be designed as one change: record `registry/repository@sha256` as the
   deploy unit.
5. **`OPS-001` — the SAST gate is a contract, not a command.** Needs a
   scanned-file-count assertion, a working exclusion configuration, and an explicit
   triage decision on 114 findings. The path typo is the symptom; the missing
   guard is the cause.
6. **`OPS-006` / `OPS-018` — runbooks must become executable.** The code blocks in
   `docs/ops/` must move into `scripts/ops/*.sh` that CI lints, with the markdown
   referencing them. Without that extraction, documentation drift on this surface is
   unbounded — as `rollback.md:138-141` (stale service count and line references)
   and `prometheus-slo-alerts.yaml:9` (stale `nginx.conf` reference) demonstrate.
   Both belong to this project: the binding project rule is that documentation must
   always stay current, and today nothing enforces it for ops claims.

---

## 11. Warnings

- **Architectural risk.** The production service-set contract (`OPS-007`) is
  currently implicit in three places. Any future profile addition to
  `docker-compose.prod.yml` will be silently excluded from deploys and rollbacks
  the same way. This class of failure grows with every profile-gated service.
- **Maintainability risk.** Every CI/deploy control in this phase is verified by a
  **substring or string-presence** assertion: `test_ci_yml_has_sast_job` asserts
  `"bandit" in content`; `test_restore_test_workflow.py` asserts `"schedule:" in
  text`; `test_compose_hardening.py` asserts key presence in a text block. This is
  the single root cause shared by `OPS-001`, `OPS-003` and `OPS-004` — **guards
  that assert a token is present cannot assert a control is effective.** Every new
  ops guard should assert a *behaviour* (a non-zero count, a resolved selector, a
  restored row) rather than a string.
- **Rollout risk.** `OPS-007` and `OPS-006` are P0 items that edit overlapping
  regions of `deploy.yml` and `docs/ops/rollback.md`. Land them as one change (see
  §9). `OPS-020` is the only non-backward-compatible item in the phase.
- **Dependency risk.** `ENT-003` (phase 01) is a live trigger for the first
  `OPS-007` deploy. Sequencing matters.
- **Documentation risk.** The ops surface currently contains a *false claim about a
  security control* (`docker-deployment.md:431-436`, the SAST paragraph), a
  *false recovery procedure* (`restore.md`), and a *false rollback procedure*
  (`rollback.md:79, 110-113`, git operations on a gitignored file). These are the
  three highest-harm documentation defects in the repository and all three are
  correctable within a single pass.
- **Evidence-integrity risk.** See `VAL-003`. Three of the source report's four
  falsifiable runtime claims did not reproduce. Numeric claims in this report that
  were not re-derived by the validator should be treated as untrusted.

---

## 12. Validation-Level Findings

### VAL-001 — The phase report has no item covering the `mem_limit` layer, which is where `SRCH-001`'s blast radius is set

| Field | Value |
|---|---|
| **ID** | VAL-001 |
| **Severity** | MEDIUM (audit-input gap; the consequence is `SRCH-001`'s CRITICAL) |
| **Status** | Open |

`SRCH-001` (phase 08, CRITICAL) establishes that the kill mechanism for an unbounded
`?features=` query is the cgroup OOM killer, and that `DB_MEM_LIMIT` is unset in all
three `.env.*` files. The ops report — whose declared scope includes "container
runtime hardening and the image build" and "the accuracy of the nine documents in
`docs/ops/`" — contains **no** item on container memory limits.

Independently confirmed by the validator: `docker-compose.yml:15` declares
`mem_limit: ${DB_MEM_LIMIT:-1g}`, and **no** `*_MEM_LIMIT` or `*_CPUS` key exists in
`.env.dev`, `.env.test` or `.env.prod`. Every environment therefore falls back to
the compose default for every service — `db` 1 g, `web` 512 m, `bot` 512 m,
`migrate`/`load_cities`/`load_catalog`/`create_admin` 256 m, `seed` 512 m, `redis`
256 m, `nginx` 128 m, `scheduler`/`backup` 256 m, `pgbouncer` 128 m. There is no
capacity-limit inventory, no test over the `mem_limit` keys, and no documented
tuning guidance in `docs/ops/`.

**Required action.** `SRCH-001` owns the OOM consequence; this phase should own
"the ops layer declares no capacity limits and enforces no `mem_limit` contract".
Cross-reference the two findings explicitly so that a reader does not conclude that
fixing one closes the other. Recommended addition: a test asserting every
`mem_limit:`/`cpus:` in the compose files resolves to a non-default value in
`.env.prod.example`, so the defaults cannot ship unnoticed.

### VAL-002 — The phase report has no item on the absence of statement/lock timeouts in the ops one-shot containers

| Field | Value |
|---|---|
| **ID** | VAL-002 |
| **Severity** | LOW (audit-input gap; the consequence is `DB-004`'s) |
| **Status** | Open |

Independently confirmed: **0** matches for `lock_timeout` or `statement_timeout`
across all `.py` and `.sh` files in `src/` and `docker/`. `DB-004` (phase 03) owns
the application-side consequence. The ops-surface consequence is unstated: the
`migrate`, `backup`, `load_cities`, `load_catalog` and `create_admin` one-shot
containers, and the `scheduler`'s `manage.py` child dispatch, all run with no
statement cap and no timeout budget, so a stuck `pg_dump` in `backup` is
indistinguishable from a slow one, is not covered by any healthcheck (see
`OPS-014`), and is never pruned. That is the intersection of `DB-004` and
`OPS-014`/`OPS-021`, and it belongs in the ops report.

### VAL-003 — Evidence-integrity defects in the source report

| Field | Value |
|---|---|
| **ID** | VAL-003 |
| **Severity** | MEDIUM (process defect in the audit itself) |
| **Status** | Open |

Four falsifiable runtime claims in the source report did not reproduce on
re-execution, three of them contradicted by a single command:

1. `OPS-001` / R-06 — a fabricated bandit transcript (see §7). The real step exits 2.
2. `OPS-001` / R-07 — "117 findings (81 medium / 36 high)"; the real figure is
   114 (104 Low / 10 Medium / 0 High).
3. `OPS-011` / R-22 — "0 hits outside tests" for `send_mail`; there is a production
   call site.
4. `OPS-006` / problem — "every documented invocation omits `--env-file`"; three
   documented invocations include it correctly.

Two of the report's conclusions (the baseline recommendation, and the SAST gate
"reports success" impact) are load-bearing for the phase's only CRITICAL and would
have propagated unchallenged. **Required action:** treat every numeric and grep
claim in the raw phase report as untrusted until re-derived; when re-deriving,
record the exact command, the image, and the working directory — the R-06 failure
was caused by running a *modified* command (the `-c` flag dropped) while labelling
it as the CI form. Also note that Appendix D of the source report concedes the
relevant guard test files were never executed, which is a reasonable and honest
disclosure — but the greps and the bandit run were presented as executed, and they
were not the repository's commands.

---

## 13. Required Fixes

Ordered by dependency (§9), then by severity. One row per fix.

| Order | ID | Severity | Effort | Fix |
|---|---|---|---|---|
| 1 | `OPS-001` | HIGH | M | Fix both bandit paths **and** the `exclude_dirs` config; triage 114 findings by class (no baseline); replace the substring guard with a scanned-file-count assertion |
| 2 | `OPS-007` (incl. `OPS-005`) | HIGH | M | Declare the prod long-lived service set once; add `--profile scheduler --profile backup --profile pgbouncer` to `deploy.yml` and to both recreate commands; fix the `rollback.md:152-157` note; land with or after `ENT-003` |
| 3 | `OPS-006` | HIGH | M | Add `--env-file .env.prod` to every `restore.md` invocation; source `.env.prod` (not `.env.dev`) at `:25, :91-92`; extract the runbook shell blocks into `scripts/ops/*.sh` that CI lints; sweep `migration-workflow.md` and `postgres-18-docker-volume-migration.md` |
| 4 | `OPS-004` | HIGH | M | Restore-test consumes a real dump artifact; assert non-zero restored row counts and `django_migrations`; pin the app image to a recorded tag instead of `${{ github.sha }}` |
| 5 | `OPS-003` | HIGH | M | Decide the monitoring topology; correct the selectors to the real series (or add the 2.0 bucket); deploy Prometheus with `rule_files`; add a scrape-contract test |
| 6 | `OPS-002` | HIGH | M | Add `pull_request` to `ci.yml`; require a green `CI` run for the dispatched SHA; constrain the `image_tag` input. **After `CFG-002`.** |
| 7 | `OPS-018` | MEDIUM | M | Correct the seven confirmed doc claims; delete the refuted `bazuna_db` sub-claim; then add the docs-parity test. **After `OPS-001` and `OPS-006`.** |
| 8 | `OPS-009` | MEDIUM | S | Define the image coordinate once as build-job outputs; align `cache-from` with `cache-to`; guard the literals |
| 9 | `OPS-010` | MEDIUM | S | Set `BOT_HEALTH_CHECK_ENABLED=true` for `web` in prod, **or** drop the bot claim and the unused `BOT_HEALTH_STALE_SECONDS` from the runbooks |
| 10 | `OPS-013` | MEDIUM | S | Guard `sentry_sdk.init` against a malformed DSN; log value-free; add the bad-DSN test |
| 11 | `OPS-014` | MEDIUM | S | `user: postgres` + healthcheck on `backup`; align the dump filename with the prune glob; extend the hardening guard to cover `user:` and entrypoint-bypassing `command:` overrides |
| 12 | `OPS-011` | MEDIUM | M | Build one concrete operator-notification floor (Telegram); label or remove the unconsumed SLO artefacts. **`EMAIL_HOST` limb removed — owned by `API-009`.** |
| 13 | `OPS-016` | MEDIUM | S | Add `concurrency` to `ci.yml` and `deploy.yml`; guard its presence |
| 14 | `OPS-017` | MEDIUM | S | Pin all actions to commit SHAs; verify the gitleaks download; **and pin/verify the syft install at `docker/Dockerfile:90-93`** |
| 15 | `OPS-008` | MEDIUM | S | Capture and roll back by digest; forbid `IMAGE_TAG=latest` in the prod template |
| 16 | `VAL-001` | MEDIUM | S | Add a `mem_limit`/`cpus` contract test and an ops capacity-limit inventory; cross-reference `SRCH-001` |
| 17 | `OPS-012` | LOW | S | Route gunicorn access/error logs through `RedactingJsonFormatter` via `logconfig_dict`; test in a throwaway container first |
| 18 | `OPS-015` | LOW | S | `PGBOUNCER_AUTH_TYPE=scram-sha-256`; do not document the profile as available until someone intends to use it |
| 19 | `OPS-019` | LOW | S | Add `start_period: 30s` to the `db` and `redis` healthchecks; extend the hardening guard to cover it |
| 20 | `OPS-020` | LOW | S | Restrict `/health/` at nginx or return a reduced public body — **after confirming no external uptime probe consumes it** |
| 21 | `OPS-021` | LOW | S | Drift-compensate the backup sleep; move the misplaced `ci.yml:375-381` comment above `deploy-check:` and fix its stale `OPS-001` reference |
| 22 | `VAL-002` | LOW | S | Add the ops-surface timeout-budget item for the one-shot containers and the scheduler's child dispatch |

---

## 14. Advisory Recommendations

Not required; listed because each improves long-term operability at low cost.

1. **Adopt one assertion style for ops guards: behavioural, not textual.** Every
   defect in `OPS-001`, `OPS-003` and `OPS-004` existed because a guard asserted a
   *string*. A repo-wide convention of "an ops guard must fail when the control it
   describes is ineffective" would have caught all three at the moment of
   introduction. This is the highest-leverage single change in the phase and it
   costs nothing to state.
2. **Give the ops surface a machine-checked inventory.** A small generated table of
   "declared control → where it is declared → how it is verified → is it currently
   effective" would make `OPS-018` self-detecting. The three highest-harm doc
   defects found here (the SAST paragraph, the `.env.dev` restore credential read,
   the `git checkout .env.prod` rollback) would all have been caught by it.
3. **Record image digests, not tags, as the deploy unit.** This subsumes
   `OPS-008` and half of `OPS-002` and makes the rollback story answerable from the
   deploy log alone.
4. **Consider a single `make ops-check` target** that runs the read-only
   operational verifications (compose interpolation with `--env-file`, `/health/`
   and `/metrics` contract, `mem_limit` resolution, runbook script lint) so the
   same checks can run locally and in CI. Several findings in this phase would
   never have reached a report if such a target existed.
5. **Document the RPO/RTO as conditional statements.** `restore.md:195-226` states
   RPO and RTO as facts while three of their preconditions (backup job running,
   off-host copy, real restore drill) are unmet. Marking them conditional costs one
   sentence and removes a whole class of false confidence.

---

## 15. Validation Summary

| Action | Count | Details |
|---|---|---|
| Validated, fully unchanged | 10 | OPS-002, OPS-003, OPS-004, OPS-007, OPS-009, OPS-014, OPS-016, OPS-019, OPS-020, OPS-021 |
| Reclassified — severity | 5 | OPS-001 ↓, OPS-005 ↓, OPS-008 ↓, OPS-012 ↓, OPS-015 ↓ |
| Reclassified — evidence/claims only (severity held) | 6 | OPS-006, OPS-010, OPS-011, OPS-013, OPS-017, OPS-018 |
| Merged | 1 | OPS-005 → OPS-007 |
| Rejected | 0 | — |
| Duplicated against a validated phase | 1 | OPS-011 `EMAIL_HOST` limb → API-009 (phase 09) |
| Sub-claims refuted or withdrawn (see §7) | 9 | OPS-001 ×3, OPS-006, OPS-008, OPS-010, OPS-011, OPS-015, OPS-018 |
| VAL- (audit-input / rollout) | 3 | VAL-001, VAL-002, VAL-003 |

10 + 5 + 6 = 21 findings in scope. `OPS-005` is counted once in "Reclassified —
severity" and once in "Merged", because both actions apply to it.

### Reclassified Findings

| ID | Original Severity | Validated Severity | Rationale |
|---|---|---|---|
| OPS-001 | CRITICAL | **HIGH** | No demonstrable production consequence — a process gate that analyses zero lines. Worse, the "always passes / green badge" impact is refuted: the job **fails** (exit 2). Two evidence claims and the baseline recommendation are rejected. |
| OPS-005 | HIGH | **MEDIUM** (merged) | Deploy-path limb is real; single-host/no-off-host limb is a strategic choice, not a defect. Same root cause and same fix as OPS-007, so it is absorbed rather than maintained separately. |
| OPS-006 | HIGH | **HIGH** (scope narrowed) | The universal "every invocation" claim is refuted — three documented invocations are correct. `restore.md` remains wholly non-executable, which sustains HIGH on its own. |
| OPS-008 | HIGH | **MEDIUM** | `deploy.yml:57-67` defeats the `latest` default on the repository's own deploy path; the exposure is conditional on a manual deploy. |
| OPS-011 | MEDIUM | **MEDIUM** (evidence replaced) | The `send_mail` evidence is false and the `EMAIL_HOST` sub-finding duplicates `API-009`. The no-operator-alerting core survives unchanged. |
| OPS-012 | MEDIUM | **LOW** | Facts confirmed, but both impacts are weak: the security exposure is explicitly speculative, and the level filtering is by design. Log-format hygiene. |
| OPS-013 | MEDIUM | **MEDIUM** (trigger corrected) | Real and reproduced. The stated triggers (leading space, trailing newline) are handled by `sentry-sdk 2.69.2`; the live trigger is a malformed scheme. |
| OPS-015 | MEDIUM | **LOW** | Real latent misconfiguration, but zero mentions of `pgbouncer` exist in `docs/ops`, so the stated impact ("documented connection-pooling guidance") does not exist. Profile-gated and undocumented means nothing would enable it. |
| OPS-018 | MEDIUM | **MEDIUM** (claims corrected, extended) | Seven claims confirmed, one refuted (`bazuna_db`), two partially wrong, four instances added — including the strongest one at `docker-deployment.md:431-436`. |

### Merged Findings

| Original ID | Merged Into | Rationale |
|---|---|---|
| OPS-005 | OPS-007 (Phase 12) | Identical root cause and identical fix; cannot be fixed independently. The distinct consequence (no backup) is preserved in the merged body; the off-host-replication limb is demoted to an advisory. |

### Cross-Phase Duplicates Removed

| Finding | Duplicate Of | Disposition |
|---|---|---|
| OPS-011 — "`EMAIL_HOST` is required at boot to protect a delivery path that does not exist" | `API-009` (phase 09) | Sub-claim removed. `API-009` already records the sole `send_mail` call site and the speculative `prod.py:198-199` justification. `docs/ops/` contains zero "password reset" references, so there is no ops-side instance to correct. |

### Explicitly Not Duplicates (checked and cleared)

| Checked against | Finding | Result |
|---|---|---|
| `AD-008` (phase 05) | `OPS-003`, `OPS-011` | The OPS report contains **no** metric or alert keyed on moderation-queue depth. Because no Prometheus is deployed, `AD-008`'s structural zero has not been operationalised. Risk is **prospective** — carry the `AD-008` warning into `OPS-003`'s implementation. |
| `API-008` (phase 09) | `OPS-004`, `OPS-005` | No overlap. The ops surface never mentions exchange rates; `restore.md` covers `pg_dump`/`pg_restore` and `migrate --plan --check` only. |
| `ENT-002` / `ENT-003` (phase 01) | `OPS-007` | Different properties of the scheduler (signal handling / dedupe vs. image-version atomicity). `ENT-003` is instead a **sequencing constraint** on `OPS-007`. |
| `CFG-002` (phase 02) | `OPS-018` | Correctly scoped as a documentation claim only; the code defect is not re-filed. `CFG-002` should land **before** `OPS-002`. |
| `SRCH-001` (phase 08) | *(nothing in this phase)* | **Gap, not duplication** → `VAL-001`. SRCH-001 owns the OOM consequence; this phase owns the absent `mem_limit` contract. |
| `DB-004` (phase 03) | *(nothing in this phase)* | **Gap, not duplication** → `VAL-002`. |
| `TEST-002` (phase 11) | *(nothing in this phase)* | No overlap; note both are "configured but ineffective gates" and belong to the same cluster in the final report. |

---

## Checkpoint 1 — Auditor analysis

- **Stage:** Auditor analysis
- **Findings in scope:** 21 (CRITICAL 1 · HIGH 7 · MEDIUM 10 · LOW 3)
- **Evidence anchor:** `.ai/audit/12-production-ops/findings.md` (1396 lines, incl. 4 appendices)
- **Dependencies / blockers:** none — source report self-contained
- **Checkpoint status:** closed

## Checkpoint 2 — Researcher verification

- **Stage:** Researcher verification
- **Findings in scope:** 21
- **Cross-phase conflict count:** 0 (no OPS finding contradicts a validated finding; the single contradiction is *internal to* the source report — the bandit "passes" claim vs. observed exit 2)
- **Merge-candidate count:** 1 confirmed (OPS-005 → OPS-007); 1 rejected as a theme-only merge (OPS-001 ↔ OPS-018)
- **Sub-claims refuted:** 9
- **Coverage gaps found:** 2 (VAL-001, VAL-002)
- **Checkpoint status:** closed

## Checkpoint 3 — Per-finding validation

- **Stage:** Per-finding validation
- **Findings in scope:** 21 (Validated unchanged 10 · Severity reclassified 5 ·
  Evidence/claims corrected 6 · Merged 1 · Rejected 0)
- **Evidence anchor:** this document, self-contained; every verdict carries a
  reproduction command or an exact `file:line` citation
- **Severity distribution after validation:** CRITICAL 0 · HIGH 5 · MEDIUM 10 · LOW 6
- **Findings requiring structural change:** 6 (OPS-007, OPS-003, OPS-004, OPS-002, OPS-001, OPS-006+OPS-018)
- **Dependencies / blockers:** none
- **Checkpoint status:** closed

## Checkpoint 4 — Final audit

- **Stage:** Final audit
- **Pipeline integrity:** OK — all IDs preserved, no renames, no source file changed, report self-contained
- **Open checkpoints:** 0
- **Residual items for the remediation tracker:** 22 fixes (13 merged from findings, 3 VAL items, 1 merged-away finding re-scoped as an advisory)
- **Checkpoint status:** closed
