---
phase: "12"
phase_name: "production-ops"
date: "2026-09-28"
auditor: "Executor (subagent)"
validator: ""
mode: "problems-only"
id_prefix: "OPS"
report_status: "draft"
severity_taxonomy: ".kilo/commands/audit/phases/12-audit-production-ops.md#severity-taxonomy"
---

# Audit Findings — Production Operations, Security & Observability

## Executive Summary

The production deployment pipeline is largely unverified. Of the security,
disaster-recovery and monitoring controls the project believes it has, the
static-analysis gate scans nothing and reports success, the monthly restore
drill restores a throwaway copy of an empty database, all three SLO alerts
reference measurements that do not exist, and nothing anywhere notifies an
operator when any of this is true. The disaster-recovery and rollback
runbooks — the documents an engineer reaches for at 3 a.m. — contain commands
that fail immediately on a production host. Twenty-one problems were found,
one of them critical and seven high; the broadest business risk is that a
failure in production would be discovered by users rather than by the system,
and that a rollback would not restore a known-good state.

## Scope & Methodology

**Scope:** Deployability and CI/CD gating (`.github/workflows/*`, `dependabot.yml`,
`.pre-commit-config.yaml`), container runtime hardening and the image build
(`docker/Dockerfile`, `docker-compose*.yml`), health/liveness/readiness
contract, backup & DR (`docker-compose.prod.yml` `backup` service, `Makefile`
targets, `docs/ops/restore.md`, `.github/workflows/restore-test.yml`),
deploy/rollback mechanics (`deploy.yml`, `docs/ops/rollback.md`), production
logging & error tracking (`config/settings/{base,prod}.py`,
`apps/core/utils/json_logging.py`), metrics & SLOs (`/metrics`, `gunicorn.conf.py`,
`docs/ops/prometheus-slo-alerts.yaml`, `grafana-slo-dashboard.json`), and the
accuracy of the nine documents in `docs/ops/`.

### Runtime Verification

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | Runtime image runs as non-root | `read docker/Dockerfile` — `USER app` at `:171` | PASS |
| R-02 | CIS directives on every long-lived service | `read docker-compose.yml` / `.prod.yml`; `test_compose_hardening.py` asserts the same 5 keys per service | PASS |
| R-03 | Distinct liveness vs readiness endpoints | `curl /health/live/` `200`; `curl /health/ready/` `200` with `{"database":"ok","cache":"ok","bot":"disabled"}` | PASS (bot limb = FAIL, see OPS-010) |
| R-04 | Container `HEALTHCHECK` targets the liveness path | `Dockerfile:176-177` + `docker-compose.yml:255` both `curl -f .../health/live/`; `bot`/`scheduler` use marker scripts | PASS |
| R-05 | Bounded healthcheck thresholds (not `start_period`-only) | every long-lived service has `interval` + `timeout` + `retries` | PASS (`db`/`redis` have no `start_period` — see OPS-019) |
| R-06 | **SAST gate actually scans** | `docker run … bandit -r src/backend src/telegram_bot -c pyproject.toml` from `/app/src/backend` | **FAIL** — `Total lines of code: 0`, `Files skipped (2): No such file or directory`, `CI_FORM_EXIT=0` |
| R-07 | Same command with repo-root paths | `bandit -q -r /app/src/backend /app/src/telegram_bot` | 81 medium + 36 high issues, `CORRECT_EXIT=1` |
| R-08 | Dependency/secret scanning present | `ci.yml:310-373` — `pip-audit`, Trivy fs, gitleaks, bandit; SARIF uploaded | PASS |
| R-09 | SBOM + auto-updates | `Dockerfile:90-93` syft CycloneDX; `.github/dependabot.yml` (actions + uv) | PASS |
| R-10 | **SLO alert series exist** | scraped live `/metrics` from a gunicorn container built from the shipped image | **FAIL** — see OPS-003 |
| R-11 | Prometheus/Grafana/exporter deployed | `grep -i prometheus\|grafana\|alertmanager` across all four compose files | **FAIL** — only `PROMETHEUS_MULTIPROC_DIR` matches |
| R-12 | `/metrics` reachable by an external scraper | `docker/nginx/nginx.conf:160-168` → `allow 127.0.0.1; deny all;` | FAIL |
| R-13 | Prod `LOGGING` + redacting formatter | `prod.py:22-67` `RedactingJsonFormatter`; `pyproject.toml:29` `sentry-sdk` is a production dep | PASS |
| R-14 | **Sentry init survives a bad DSN** | `sentry_sdk.init(dsn='not-a-valid-dsn')` in the shipped image | **FAIL** — raises `sentry_sdk.utils.BadDsn` (see OPS-013) |
| R-15 | Backup job: `pg_dump -F c`, daily, ≥7-day retention | `docker-compose.prod.yml:141-155` | PASS |
| R-16 | **Restore-test exercises a production backup** | `restore-test.yml:70-81` dumps the freshly-bootstrapped CI database | **FAIL** — see OPS-004 |
| R-17 | RPO/RTO documented | `docs/ops/restore.md:195-225` (RPO 24 h, RTO ≈4 h) | PASS |
| R-18 | **Documented prod `docker compose` commands run** | `docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile backup config --services` | **FAIL** — `EXIT=1`, `required variable POSTGRES_USER is missing a value` |
| R-19 | Deploy workflow gated on CI | `ci.yml:3-5` (`push` only, no `pull_request`); `deploy.yml` has no `needs`/status check | FAIL |
| R-20 | Deploy/rollback covers all long-lived services | `deploy.yml:90` and `:115`; profile-gated `scheduler` | FAIL |
| R-21 | PgBouncer auth compatible with PG18 | `psql SHOW password_encryption` → `scram-sha-256`; `pg_authid.rolpassword` → `SCRAM-SHA-256$…`; compose sets `PGBOUNCER_AUTH_TYPE=md5` | FAIL |
| R-22 | An operator-notification channel exists | `grep -r send_mail\|EmailMessage\|mail.outbox` over `src/` → 0 hits outside tests | FAIL |

> PASS results prove the audit was thorough; they are METHODOLOGY evidence, NOT findings.

**Tools used:** `read`/`grep`/`glob` over the repository, `git log -S`, `docker compose config` (read-only interpolation check), `docker run`/`docker exec` against the already-built `mko-bazuna-test-*` images, `psql` against the running test instance, a live gunicorn + `/metrics` scrape, and `bandit`/`sentry_sdk` executed inside the shipped runtime image.

**Assumptions:** "Production" = `docker-compose.yml` + `docker-compose.prod.yml` deployed from the repository's own `deploy.yml` workflow against `.env.prod`. The `mko-bazuna-test` PostgreSQL 18 instance is behaviourally equivalent to the production engine for the checks used here (extension, `password_encryption`, SCRAM verifier format) and is used as the live stand-in. GitHub Actions were not executed — CI behaviour is established by static reading plus local reproduction of the exact commands the workflows run. Working-tree `.env.prod` is the operator's local copy and is treated as evidence about *template coverage and key naming only*, never about real secret values (no value was read or quoted).

<!-- Phase 99 NOTE: Phase 99 does NOT simply replace this section inline. -->
<!-- It produces a different document type: change the title to "# Audit Findings — Validation Report", -->
<!-- preserve this Summary section verbatim, and add a separate ## Validation Summary section. -->

## Findings Summary

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| OPS-001 | CI SAST gate scans zero files and always passes | CRITICAL | Open | Security / CI gating |
| OPS-002 | Production deploy is not gated on any CI result | HIGH | Open | CI/CD gating |
| OPS-003 | Every SLO alert references a metric that does not exist; no Prometheus is deployed | HIGH | Open | Observability |
| OPS-004 | Monthly restore-test restores a self-generated empty dump, not a production backup | HIGH | Open | Reliability / DR |
| OPS-005 | Backups are single-host, same-volume, and the daily job is opt-in and never started by deploy | HIGH | Open | Reliability / DR |
| OPS-006 | DR and rollback runbooks are not executable on a production host | HIGH | Open | Documentation / operability |
| OPS-007 | Deploy and rollback never update the profile-gated scheduler — rollback is not atomic | HIGH | Open | Deployment safety |
| OPS-008 | Rollback target may be the mutable `latest` tag, so rollback can be a silent no-op | HIGH | Open | Deployment safety |
| OPS-009 | CI pushes and production pulls from three different registry namespaces | MEDIUM | Open | Supply chain |
| OPS-010 | Bot-marker freshness is disabled in every shipped config, so readiness cannot detect a wedged bot | MEDIUM | Open | Reliability / health contract |
| OPS-011 | No alerting channel exists anywhere in the system | MEDIUM | Open | Observability |
| OPS-012 | Gunicorn access and error logs bypass the redacting JSON formatter | MEDIUM | Open | Observability / logging |
| OPS-013 | A malformed `SENTRY_DSN` raises out of the prod settings import and crash-loops every service | MEDIUM | Open | Observability / error tracking |
| OPS-014 | Backup job runs as root, has no healthcheck, and deploy backups are never pruned | MEDIUM | Open | Container runtime / DR |
| OPS-015 | PgBouncer is configured for md5 auth against PostgreSQL 18 SCRAM verifiers | MEDIUM | Open | Configuration |
| OPS-016 | No `concurrency` group on CI or deploy; overlapping runs race shared refs | MEDIUM | Open | CI/CD gating |
| OPS-017 | Pipeline supply chain: mutable action tags and an unverified `curl \| tar` gitleaks fetch | MEDIUM | Open | Supply chain |
| OPS-018 | Ops documentation asserts controls that are not live | MEDIUM | Open | Documentation |
| OPS-019 | `db`/`redis` healthchecks have no `start_period`, so the whole boot chain can flap | LOW | Open | Reliability |
| OPS-020 | Public readiness endpoint exposes internal dependency state | LOW | Open | Security |
| OPS-021 | Backup loop has no drift compensation or freshness assertion; dead comment in `ci.yml` | LOW | Open | Maintainability |

## Distribution

**Severity counts**

| CRITICAL | HIGH | MEDIUM | LOW |
|----------|------|--------|-----|
| 1 | 7 | 10 | 3 |

**Status counts**

| Status | Count |
|--------|-------|
| Open | 21 |

> Note: Status is `Open` for all findings in raw phase reports. Phase 99 validation mutates Status to `Validated` / `Reclassified` / `Merged` / `Rejected` / `Deferred`. Values `Fixed` / `Verified` are forbidden here — they belong to a remediation tracker, not the audit report.

## Findings by Severity

### CRITICAL

#### OPS-001: [CRITICAL] — CI SAST gate scans zero files and always passes

| Field | Value |
|---|---|
| **ID** | OPS-001 |
| **Title** | CI SAST gate scans zero files and always passes |
| **Severity** | CRITICAL |
| **Category** | Security / CI gating (ISO 25010: Security, Analytical maintainability) |
| **File(s)** | `.github/workflows/ci.yml:355-358`, `src/backend/apps/core/tests/test_ci_security.py:158-173`, `pyproject.toml:230-233` |
| **Status** | Open |
| **Problem** | The only static-application-security-test step in the pipeline is `uv run bandit -r src/backend src/telegram_bot -c pyproject.toml` with `working-directory: src/backend`. Both targets are resolved relative to `/app`-style checkouts, i.e. `src/backend/src/backend` and `src/backend/src/telegram_bot`, neither of which exists. `bandit` treats the missing paths as skipped files, reports `No issues identified`, and exits 0. The `security` job therefore passes unconditionally and no Python source file in the repository has ever been statically analysed. |
| **Impact** | The phase rubric lists "SAST absent (no bandit/semgrep step)" as the single live CRITICAL limb of the pipeline-security dimension. A step that exists but analyses zero lines satisfies neither the letter nor the intent: the control is indistinguishable from no control. Every insecure-coding pattern bandit is meant to catch (subprocess with `shell=True`, weak hashing, disabled certificate verification, hardcoded credentials) ships unchallenged, and the green `security` badge actively misinforms reviewers about the risk posture. |
| **Root Cause** | Path relativity error introduced when the step was added (`0f96dcc ci(sast): add bandit SAST scanning to security pipeline`, 2026-09-25) and never exercised. It survived because the accompanying regression guard `test_ci_yml_has_sast_job` only asserts the substring `"bandit"` is present in `ci.yml`; no test can distinguish a working step from one that scans nothing, and the `security` job does not run pytest. |
| **Recommendation** | Change the step to repo-root-relative paths (`bandit -r src/backend src/telegram_bot -c pyproject.toml` with `working-directory: .`), or keep `working-directory: src/backend` and target `apps config theme` plus `../../src/telegram_bot`. Then triage the resulting 117 findings (81 medium / 36 high) into a committed baseline rather than silencing the rule wholesale, and add a guard that asserts a non-zero scanned-file count rather than a substring. |
| **Effort** | S |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **Owner** | Platform/DevOps + Backend lead |
| **Target Date** | 2026-10-05 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-018 (docs assert a working SAST step) |

**Evidence — `.github/workflows/ci.yml:355-358`** *(supports: "the step's target paths are relative to the wrong root")*:
```yaml
      # --- SAST (static application security testing) ---
      - name: Run SAST (bandit)
        run: uv run bandit -r src/backend src/telegram_bot -c pyproject.toml
        working-directory: src/backend
```

**Evidence — `docker run … bandit` (shipped image, CWD `/app/src/backend`)** *(supports: "0 lines scanned, 2 files skipped, exit 0 — the gate is a no-op")*:
```text
Test results:
	No issues identified.

Code scanned:
	Total lines of code: 0
...
Files skipped (2):
	./src/backend (No such file or directory)
	./src/telegram_bot (No such file or directory)
CI_FORM_EXIT=0
```

**Evidence — same binary, repo-root paths** *(supports: "the real backlog is 117 findings, so the fix must be landed with a triage baseline or CI turns permanently red")*:
```text
	Total issues (by severity):
		Low: 0
		Medium: 81
		High: 36
	Files skipped (0):
CORRECT_EXIT=1
```

**Evidence — `src/backend/apps/core/tests/test_ci_security.py:158-161`** *(supports: "the regression guard cannot detect a non-functional step")*:
```python
def test_ci_yml_has_sast_job() -> None:
    """ci.yml references a SAST tool (bandit or semgrep)."""
    content = _read(".github", "workflows", "ci.yml")
    assert "bandit" in content or "semgrep" in content
```

---

### HIGH

#### OPS-002: [HIGH] — Production deploy is not gated on any CI result

| Field | Value |
|---|---|
| **ID** | OPS-002 |
| **Title** | Production deploy is not gated on any CI result |
| **Severity** | HIGH |
| **Category** | CI/CD gating |
| **File(s)** | `.github/workflows/deploy.yml:8-14,30-38`, `.github/workflows/ci.yml:3-5` |
| **Status** | Open |
| **Problem** | `deploy.yml` triggers only on `workflow_dispatch` and declares no dependency on any CI job — there is no `needs:`, no `workflow_run` trigger, and no status check on the `production` environment. Its `image_tag` input is a free-text string defaulting to the current commit SHA and is used verbatim as the compose `IMAGE_TAG`. Separately, `ci.yml` triggers only on `push: [main, develop]`; there is no `pull_request` trigger, so a pull request is never gated by lint, typecheck, tests, `security` or `deploy-check` at all. |
| **Impact** | Two independent paths to an ungated production image: a branch that never passed `security` can be dispatched to production, and an older or deliberately chosen SHA (for example one containing a known CVE) can be shipped by typing it into the workflow input. The manual approval on the `production` environment is the only remaining control, and it is a human checkbox, not a verification. |
| **Root Cause** | The deploy workflow was written as a convenience wrapper around a manual `docker compose up -d` (`0f28ffe`) without being wired to the pipeline it consumes. A mutable-tag compose deployment has no notion of a "green build", so the linkage must be made explicitly and was not. |
| **Recommendation** | (1) Add `on: pull_request:` to `ci.yml` so every change is gated before merge. (2) Constrain `deploy.yml`: replace the free-text `image_tag` with a constrained input, or assert the requested tag is a commit on `main` with a successful `CI` run for that SHA before the SSH step. (3) Add `concurrency: {group: deploy-production, cancel-in-progress: false}`. |
| **Effort** | M |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **Owner** | Platform/DevOps |
| **Target Date** | 2026-10-12 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-009 (registry mismatch), OPS-016 (no concurrency) |

**Evidence — `.github/workflows/ci.yml:3-5`** *(supports: "no pull_request trigger exists, so PRs are ungated")*:
```yaml
on:
  push:
    branches: [main, develop]
```

**Evidence — `.github/workflows/deploy.yml:8-14`** *(supports: "workflow_dispatch with a free-text image_tag and no needs/status check")*:
```yaml
on:
  workflow_dispatch:
    inputs:
      image_tag:
        description: "Git SHA from the CI build to deploy. Defaults to the current commit SHA."
        required: false
        default: ""
```

**Evidence — `grep -n "concurrency|pull_request|workflow_run|needs:|environment:" .github/workflows/*.yml`** *(supports: "the only `needs:` in the whole pipeline is load-test→build; no concurrency group anywhere")*:
```text
ci.yml:384:    needs: build
deploy.yml:6: # manual approval (environment: production).
deploy.yml:24:    environment: production
```

---

#### OPS-003: [HIGH] — Every SLO alert references a metric that does not exist; no Prometheus is deployed

| Field | Value |
|---|---|
| **ID** | OPS-003 |
| **Title** | Every SLO alert references a metric that does not exist; no Prometheus is deployed |
| **Severity** | HIGH |
| **Category** | Observability / SLOs |
| **File(s)** | `docs/ops/prometheus-slo-alerts.yaml:56-67,95-102,132-140`, `docker-compose.yml`, `docker-compose.prod.yml`, `docker/nginx/nginx.conf:159-168` |
| **Status** | Open |
| **Problem** | The three alert rules in `docs/ops/prometheus-slo-alerts.yaml` select series that are never emitted. `search_slo_burn_rate` and `search_p95_latency_slo` use `django_http_response_duration_seconds_bucket` with `handler="search:search"` and `le="2.000"`; the installed `django-prometheus` emits `django_http_{requests,responses}_latency_including_middlewares_seconds_bucket` labelled by `view`/`method`, and its bucket edges are `0.01 … 1.0, 2.5, 5.0 …` — there is no `2.0` bucket, so even a corrected metric name would not resolve `le="2.000"`. `cache_hit_rate_slo` uses `redis_db_keyspace_hits_total`, emitted by a `redis_exporter` that is in no compose file. Independently, no Prometheus, Alertmanager, Grafana or exporter service exists in any of the four compose files, and nginx restricts `/metrics` to `allow 127.0.0.1`, so no container other than `web` itself can scrape it. |
| **Impact** | The project's only SLO alerting is inert: with zero matching series all three rules evaluate to an empty vector and can never enter the firing state. Search-latency SLO breaches, cache collapse and error-budget burn-down are invisible to any human, and `docs/ops/grafana-slo-dashboard.json` is equally unconsumed. `docs/ops/docker-deployment.md:1015` states "An external Prometheus instance scrapes it on its own schedule", but the configuration shipped in this repository makes that scrape return `403` from anywhere but the host itself. |
| **Root Cause** | The rules were written against a remembered `django-prometheus` API surface (pre-2.4 metric names, an assumed `handler` label, an assumed 2 s bucket edge) rather than the exposition the installed version produces, and no test ever evaluated an `expr` against a live scrape. The thresholds were cross-checked only against the constant in `src/benchmark/constants.py`, never against `/metrics`. |
| **Recommendation** | Decide the monitoring deployment explicitly. Minimum viable: correct the selectors to the real series (`..._latency_including_middlewares_seconds_bucket{view="search"}` with an interpolated p95/p99, or set `PROMETHEUS_LATENCY_BUCKETS` to include 2.0), add a `prometheus` service with a `prometheus.yml` whose `rule_files` include this file, and either move the rules out of the Kubernetes-only `PrometheusRule` CRD form or document the prerequisite. Add `promtool check rules` plus a scrape-contract test asserting every `expr` selector resolves against a live `/metrics` render. |
| **Effort** | M |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Owner** | Platform/DevOps |
| **Target Date** | 2026-11-15 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-011 (no alerting channel), OPS-018 (docs claim an external scraper) |

**Evidence — `docs/ops/prometheus-slo-alerts.yaml:56-68`** *(supports: "the selector names a metric family and a bucket edge that do not exist; the expression also carries no threshold despite the comment claiming `> 10`")*:
```yaml
        - alert: search_slo_burn_rate
          expr: |
            (
              1
              - rate(
                  django_http_response_duration_seconds_bucket{le="2.000", handler="search:search"}[14.4m]
                )
                / rate(
                    django_http_response_duration_seconds_count{handler="search:search"}[14.4m]
                  )
            )
            / 0.01
          for: 2s
```

**Evidence — live `/metrics` scrape from a gunicorn container built from `mko-bazuna-test-web:latest`** *(supports: "the real metric family, the real label names, and the real bucket edges")*:
```text
django_http_requests_latency_including_middlewares_seconds_bucket{le="1.0"} 9.0
django_http_requests_latency_including_middlewares_seconds_bucket{le="2.5"} 9.0
django_http_requests_latency_including_middlewares_seconds_bucket{le="5.0"} 9.0
django_http_requests_latency_seconds_by_view_method_bucket{le="0.01",method="GET",view="prometheus-django-metrics"} 2.0
```

**Evidence — `grep -i "prometheus|grafana|alertmanager|node_exporter" docker-compose*.yml`** *(supports: "no scrape target or rule evaluator is deployed")*:
```text
docker-compose.prod.yml:14: - PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc
docker-compose.prod.yml:16: - /tmp/prometheus_multiproc:rw
```

**Evidence — `docker/nginx/nginx.conf:159-162`** *(supports: "an external scraper is denied at the proxy")*:
```nginx
        # Metrics endpoint — restricted to localhost (production monitoring only)
        location = /metrics {
            allow 127.0.0.1;
            deny all;
```

---

#### OPS-004: [HIGH] — Monthly restore-test restores a self-generated empty dump, not a production backup

| Field | Value |
|---|---|
| **ID** | OPS-004 |
| **Title** | Monthly restore-test restores a self-generated empty dump, not a production backup |
| **Severity** | HIGH |
| **Category** | Reliability / Disaster recovery |
| **File(s)** | `.github/workflows/restore-test.yml:70-81,93-94`, `src/backend/tests/test_restore_test_workflow.py:36-71` |
| **Status** | Open |
| **Problem** | `restore-test.yml` bootstraps a fresh CI database (`bootstrap_reference_data`, i.e. migrations + reference data, no user data), then runs `pg_dump --no-sync … -d mko_bazuna -F c > backups/test_backup.dump` against *that* database, and hands the resulting file to `make restore-test`. No production backup is fetched, downloaded, or referenced at any point. The job therefore exercises a `pg_dump` → `pg_restore` round trip of a nearly empty schema, never a real backup artifact. |
| **Impact** | The monthly control gives false assurance about the only thing it exists to prove. A production backup that is truncated, silently corrupted by a disk error, written with an incompatible `pg_dump` version, or missing rows because of a `pg_dump` bug would still pass, because the file under test was produced three steps earlier from a healthy in-memory database. `docs/ops/restore.md:197-225` documents a 24 h RPO and ≈4 h RTO on the strength of this cadence; neither number is backed by evidence. |
| **Root Cause** | The workflow was designed to be self-contained and hermetic (avoiding any secret or artifact transfer into CI) at the cost of testing nothing real. `test_restore_test_workflow.py` only asserts the YAML *contains* a `schedule:`, a `cron`, and the string `migrate --plan --check` — the same string-level guard pattern that let OPS-001 through. |
| **Recommendation** | Make the job consume a real artifact: upload the newest production dump to a CI artifact or object store in the `backup` service (a signed object-storage push is the practical route), and have `restore-test.yml` download the most recent artifact rather than generating one. Add a precondition assertion on restored row counts (e.g. `SELECT count(*) FROM ads_ad` must be > 0 and `django_migrations` must exist) so an empty or partial restore fails the job. Keep the self-generated dump path only as a smoke test. |
| **Effort** | M |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Owner** | Platform/DevOps |
| **Target Date** | 2026-11-01 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-005 (single-host backups), OPS-006 (restore runbook not executable) |

**Evidence — `.github/workflows/restore-test.yml:70-81`** *(supports: "the dump under test is generated from a freshly-bootstrapped database in the same job")*:
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

**Evidence — `Makefile:320-325`** *(supports: "the smoke tests only count tables and echo `ads_ad` rows — they never assert the counts are plausible")*:
```make
	echo "→ Smoke test 2/4: table count (schema present)" && \
	echo "  Tables: $$(docker exec restore-db psql -U restore_user -d bazuna_restore -t -A -c \
		"SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")" && \
	echo "→ Smoke test 3/4: row count in ads_ad (data present)" && \
	echo "  ads_ad rows: $$(docker exec restore-db psql -U restore_user -d bazuna_restore -t -A -c \
		"SELECT count(*) FROM ads_ad;")" && \
```

---

#### OPS-005: [HIGH] — Backups are single-host and the daily job is opt-in and never started by deploy

| Field | Value |
|---|---|
| **ID** | OPS-005 |
| **Title** | Backups are single-host and the daily job is opt-in and never started by deploy |
| **Severity** | HIGH |
| **Category** | Reliability / Disaster recovery |
| **File(s)** | `docker-compose.prod.yml:131-169`, `.github/workflows/deploy.yml:86-90` |
| **Status** | Open |
| **Problem** | The daily `backup` service is gated behind `profiles: ["backup"]` and is therefore excluded from every compose invocation unless `--profile backup` is passed explicitly. The deploy workflow passes no `--profile` on any of its three compose calls (`deploy.yml:86`, `:90`, `:115`), so it never starts the backup container and never recreates it. Dumps are written to `./backups` on the same host, via a bind mount from the `db` service's own host, with no copy, encryption, or off-host replication. |
| **Impact** | A host loss, a disk failure, or a mistaken `rm -rf` destroys the production database and every backup of it simultaneously. On a fresh host, the documented deploy path brings up web/bot/nginx but silently no backup job, so the site runs for days or weeks with no daily dump before anyone notices. The 24 h RPO in `docs/ops/restore.md:197` is therefore an upper bound on a control that may not be running at all. |
| **Root Cause** | The profile gate was added "to prevent storage consumption before needed" (`docker-compose.prod.yml:130`) and the deploy workflow was written later against a different service subset. Nothing asserts that the production profile set is complete at deploy time, so the two drift apart silently. |
| **Recommendation** | (1) Pass `--profile backup --profile scheduler --profile pgbouncer` explicitly in `deploy.yml` (and record the intent in `docs/ops/rollback.md`'s recreate commands). (2) Add an off-host replication step: `pg_dump` piped to a second destination (object storage via `aws s3 cp`/`mc cp`, or a second host) with retention, and a restore path that reads from it. (3) Add a healthcheck to the `backup` service and an alert on "newest dump older than 26 h" (see OPS-011) so a silently-stopped job is detected. |
| **Effort** | M |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Owner** | Platform/DevOps |
| **Target Date** | 2026-11-01 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-004 (restore-test proves nothing), OPS-014 (backup job hygiene), OPS-021 (no freshness assertion) |

**Evidence — `docker-compose.prod.yml:129-141,168-169`** *(supports: "the backup service is profile-gated and dumps to a same-host bind mount")*:
```yaml
  # Backup service: daily database dumps with 7-day retention
  # Opt-in via --profile backup to prevent storage consumption before needed
  backup:
    image: postgres:18-alpine
...
    volumes:
      - ./backups:/backups
...
    profiles:
      - backup
```

**Evidence — `.github/workflows/deploy.yml:86,90`** *(supports: "no compose call in the deploy path enables a profile")*:
```bash
            IMAGE_TAG="${IMAGE_TAG}" docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
...
            IMAGE_TAG="${IMAGE_TAG}" docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --remove-orphans
```

**Evidence — `docker compose … --profile backup --profile scheduler --profile pgbouncer config --services`** *(supports: "the profile-gated services are real compose services that the deploy path simply never names")*:
```text
db
backup
migrate
redis
load_cities
load_catalog
bot
create_admin
web
nginx
scheduler
pgbouncer
```

---

#### OPS-006: [HIGH] — DR and rollback runbooks are not executable on a production host

| Field | Value |
|---|---|
| **ID** | OPS-006 |
| **Title** | DR and rollback runbooks are not executable on a production host |
| **Severity** | HIGH |
| **Category** | Documentation / operability |
| **File(s)** | `docs/ops/restore.md:33,71,77,91-106,125-137`, `docs/ops/rollback.md:332-335,441-450,555,570,590-604` |
| **Status** | Open |
| **Problem** | The production compose files use mandatory interpolation (`${POSTGRES_USER:?POSTGRES_USER must be set}`, `${DJANGO_SECRET_KEY:?…}`). Every documented `docker compose` invocation in the two incident runbooks omits `--env-file .env.prod`, so compose aborts with exit 1 before doing anything. Additionally `docs/ops/restore.md:91-92` — the first two steps of the *production* restore procedure — reads `POSTGRES_USER` and `POSTGRES_DB` out of **`.env.dev`**. |
| **Impact** | The two documents an engineer opens at 3 a.m. cannot be followed. `restore.md:33` is the documented way to start the daily backup; `restore.md:71-137` is the whole production restore path; `rollback.md:332-335` and `:441-450` are the health-validation commands used to decide whether a rollback succeeded. Each fails immediately, and the `.env.dev` credential read at `restore.md:91` would either fail or point the operator at the wrong database. |
| **Root Cause** | The runbooks were written by paraphrasing commands rather than by executing them, and the `--env-file` requirement (documented in `AGENTS.md` and `.kilo/rules/commands.md`) was not applied retroactively. Nothing in CI compiles or dry-runs the shell blocks inside the runbooks. |
| **Recommendation** | Add `--env-file .env.prod` to every production `docker compose` invocation in `restore.md` and `rollback.md`, and change `restore.md:91-92` to source `.env.prod`. Then extract the code blocks into a single executable script (`scripts/ops/restore.sh`, `scripts/ops/rollback.sh`) and have the runbooks reference it, so a broken command fails a lint/CI step instead of an incident. `docs/ops/migration-workflow.md` and `postgres-18-docker-volume-migration.md` carry the same defect and should be swept in the same pass. |
| **Effort** | S |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **Owner** | Platform/DevOps |
| **Target Date** | 2026-10-12 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-004, OPS-007, OPS-008, OPS-018 |

**Evidence — `docs/ops/restore.md:31-34,90-95`** *(supports: "the documented start-backup and restore commands omit `--env-file`; the restore reads credentials from `.env.dev`")*:
```bash
# Start production with backup service
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile backup up -d
...
# Set environment variables for the restore
export POSTGRES_USER=$(grep POSTGRES_USER .env.dev | cut -d= -f2)
export POSTGRES_DB=$(grep POSTGRES_DB .env.dev | cut -d= -f2)

# Perform the restore
docker compose exec -T db pg_restore \
```

**Evidence — reproduced command** *(supports: "the documented form aborts")*:
```text
$ docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile backup config --services
error while interpolating services.migrate.environment.POSTGRES_USER: required variable POSTGRES_USER is missing a value: POSTGRES_USER must be set
error while interpolating services.web.environment.[]: required variable DJANGO_SECRET_KEY is missing a value: DJANGO_SECRET_KEY must be set
EXIT=1
```

**Evidence — `.gitignore:144-148` + `git ls-files .env.prod`** *(supports: "`rollback.md:79`'s `git checkout .env.prod` config-rollback step cannot work either")*:
```text
# Environment files — all runtime env files are gitignored
.env
.env.*
!.env.example
!.env.*.example
---
error: pathspec '.env.prod' did not match any file(s) known to git
```

---

#### OPS-007: [HIGH] — Deploy and rollback never update the profile-gated scheduler, so rollback is not atomic

| Field | Value |
|---|---|
| **ID** | OPS-007 |
| **Title** | Deploy and rollback never update the profile-gated scheduler, so rollback is not atomic |
| **Severity** | HIGH |
| **Category** | Deployment safety |
| **File(s)** | `.github/workflows/deploy.yml:88-90,113-115`, `docker-compose.prod.yml:120-121`, `docs/ops/rollback.md:145-157` |
| **Status** | Open |
| **Problem** | The `scheduler` service is gated behind `profiles: ["scheduler"]`, so it is outside the default service set. The deploy workflow's recreate step (`deploy.yml:90`) passes no `--profile` and therefore never updates it; its automated rollback branch (`deploy.yml:115`) is even narrower — `up -d --force-recreate --remove-orphans web bot` — and names only `web` and `bot`. The documented manual rollback (`rollback.md:145-150`) uses the same `web bot` filter. |
| **Impact** | The scheduler is a long-lived service that runs `send_alerts` (Telegram buyer digests carrying ad titles, prices, cities and working deep links) and `consent_hard_delete` (the 30-day PII erasure the privacy policy promises). After any deploy it keeps running whatever image it started with — so it can be arbitrarily stale. Worse, after a detected-bad deploy the automated rollback restores `web` and `bot` while deliberately leaving the scheduler on the image that was just judged faulty, continuing to send messages and delete PII under code that is known to be broken. Rollback is therefore not atomic across the long-lived service set, which is the phase rubric's own definition of a deployment-safety failure. |
| **Root Cause** | Compose profiles are a local convenience with no deploy-time awareness: `up -d` silently ignores profile-gated services, and no test or CI check asserts that the set of long-lived services in `docker-compose.prod.yml` equals the set the deploy path recreates. |
| **Recommendation** | Name every long-lived service explicitly in the deploy and rollback recreate steps (`up -d --force-recreate --remove-orphans web bot scheduler` plus the profiles), or add `--profile scheduler --profile backup --profile pgbouncer` to the default deploy invocation. Add a regression guard asserting that every service with `restart:` set in `docker-compose.prod.yml` appears in both `deploy.yml` recreate commands — the same "contract expressed in one file" gap that Phase 01's validator logged as VAL-003. |
| **Effort** | S |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **Owner** | Platform/DevOps |
| **Target Date** | 2026-10-12 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-005 (same profile-gating gap, backup), OPS-008, OPS-010 |

**Evidence — `.github/workflows/deploy.yml:88-90,112-115`** *(supports: "the main deploy and the automated rollback both omit the scheduler")*:
```bash
            # c. Recreate services (brief downtime; acceptable for this classifieds board)
            echo "=== Step 3: Recreate services ==="
            IMAGE_TAG="${IMAGE_TAG}" docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --remove-orphans
...
              echo "=== Step 4b: Recreate services with previous image ==="
              IMAGE_TAG="${PREVIOUS_IMAGE_TAG}" docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate --remove-orphans web bot
```

**Evidence — `docker-compose.prod.yml:120-121`** *(supports: "the scheduler is outside the default service set")*:
```yaml
    profiles:
      - scheduler
```

**Evidence — `docs/ops/rollback.md:152-157`** *(supports: "the runbook repeats the same gap as guidance")*:
```text
   > `up -d` with no service names recreates **all** services. Targeting `web bot`
   > is sufficient for a code-only rollback (the one-shot services `migrate`,
   > `load_catalog`, etc. are not long-lived and will only re-run if their image
   > hash changed and you omit the service filter).
```
*(the enumeration of what is "not long-lived" omits `scheduler`, which is
`restart: unless-stopped` and runs hourly forever)*

---

#### OPS-008: [HIGH] — Rollback target may be the mutable `latest` tag, so rollback can be a silent no-op

| Field | Value |
|---|---|
| **ID** | OPS-008 |
| **Title** | Rollback target may be the mutable `latest` tag, so rollback can be a silent no-op |
| **Severity** | HIGH |
| **Category** | Deployment safety |
| **File(s)** | `.github/workflows/deploy.yml:71-75,107-115`, `docs/ops/rollback.md:133-141` |
| **Status** | Open |
| **Problem** | The rollback target is derived by reading the tag string currently attached to the `web` container (`docker compose images --format '{{.Tag}}' web | head -1`) and re-pulling that tag. `.env.prod.example:83` ships `IMAGE_TAG=latest` and `docker-compose.prod.yml` defaults to `${IMAGE_TAG:-latest}`, so on any deployment performed with the shipped default the "previous tag" is `latest` — the same mutable reference that was just replaced. Re-pulling and force-recreating `latest` reproduces the failing image, and the post-rollback `/health/ready/` poll then fails identically while the workflow reports a rollback attempt. No image digest is captured anywhere. |
| **Impact** | The automated rollback's success/failure signal becomes meaningless in exactly the default configuration: it can report "Rollback complete" while serving the bad image, or fail twice and hand a genuinely unrecoverable state to a human under time pressure. Separately, because the workflow dispatches a SHA by default but a manual `docker compose up -d` with `IMAGE_TAG=latest` is still a documented path (`rollback.md:79`, `docker-deployment.md:317`), the mutable-tag state is reachable in normal operation, not just by misconfiguration. |
| **Root Cause** | The workflow treats an image tag as an identity. Tags are mutable labels; digests are identity. The capture step (`deploy.yml:74`) was written to read a tag because that is what compose keys its container cache on, and no digest-based record (`docker image inspect --format '{{index .RepoDigests 0}}'`) was added. |
| **Recommendation** | Capture the digest of the running image before the pull (`PREVIOUS_DIGEST=$(docker inspect --format='{{index .Image}}' "$(docker compose ps -q web)"`) or require `IMAGE_TAG` to be a SHA in `.env.prod` and forbid `latest` in the prod template. Roll back by digest (`image@sha256:…`) rather than by tag, and record both tag and digest in the deploy log. Add a guard test asserting `.env.prod.example` does not default `IMAGE_TAG` to `latest`. |
| **Effort** | S |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **Owner** | Platform/DevOps |
| **Target Date** | 2026-10-19 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-002, OPS-007 |

**Evidence — `.github/workflows/deploy.yml:71-75,109-115`** *(supports: "the rollback target is a tag read from the running container, then re-pulled")*:
```bash
            # Capture the currently running image tag before pulling/recreating.
            # Must be captured while old containers still run (before pull/up),
            # so it reflects the last-known-good IMAGE_TAG for potential rollback.
            PREVIOUS_IMAGE_TAG=$(docker compose images --format '{{.Tag}}' web | head -1)
            echo "Previous image tag: ${PREVIOUS_IMAGE_TAG:-none}"
...
              echo "Rolling back to previous image: ${PREVIOUS_IMAGE_TAG}"

              # Revert IMAGE_TAG to the previous known-good tag and pull it.
              IMAGE_TAG="${PREVIOUS_IMAGE_TAG}" docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
```

**Evidence — `.env.prod.example:81-83`** *(supports: "the shipped default tag is the mutable `latest`")*:
```text
81: REGISTRY=ghcr.io
82: REPOSITORY=manicko/mko_bazuna
83: IMAGE_TAG=latest
```

---

### MEDIUM

#### OPS-009: [MEDIUM] — CI pushes and production pulls from three different registry namespaces

| Field | Value |
|---|---|
| **ID** | OPS-009 |
| **Title** | CI pushes and production pulls from three different registry namespaces |
| **Severity** | MEDIUM |
| **Category** | Supply chain / CI-CD |
| **File(s)** | `.github/workflows/ci.yml:37-39`, `.github/workflows/deploy.yml:39`, `.github/workflows/restore-test.yml:91,94`, `docker-compose.prod.yml:8`, `.env.prod.example:81-82` |
| **Status** | Open |
| **Problem** | CI pushes the application image to `ghcr.io/mko-bazuna/mko_bazuna:<sha>` (`ci.yml:37`). The production compose reference defaults to `ghcr.io/manicko/mko_bazuna:<tag>` (`docker-compose.prod.yml:8`, and `REPOSITORY=manicko/mko_bazuna` in `.env.prod.example:82`). `deploy.yml:39` echoes a third string, `ghcr.io/mko-bazuna/mko_bazuna`. The two buildx cache references in the same `build` step use `ghcr.io/manicko/mko_bazuna:buildcache` for `cache-from` and `ghcr.io/mko-bazuna/mko-bazuna:buildcache` for `cache-to`. `restore-test.yml:91,94` uses the `mko-bazuna` namespace, matching CI. |
| **Impact** | The build, the deploy and the restore-test each reference a different repository, so at most one of them can be correct and the mismatch is invisible until a pull fails. If `REPOSITORY` is left at the template default, production deploys a stale or nonexistent image while the log line claims it deployed the SHA just built. Because `cache-from` never matches `cache-to`, the registry cache is also a permanent miss and every CI build is cold. |
| **Root Cause** | The image coordinate is duplicated as a literal string in five places instead of being defined once (for example a build output consumed by the deploy and restore-test workflows, or a single `REGISTRY`/`REPOSITORY` pair documented as authoritative). |
| **Recommendation** | Define the coordinate once — publish `registry` and `repository` as outputs of the `build` job and have `deploy.yml` / `restore-test.yml` consume them instead of hard-coding strings — and set `cache-from` to the same reference as `cache-to`. Add a guard test that asserts every `ghcr.io/...` literal in `.github/workflows/` matches the `REPOSITORY` default in `docker-compose.prod.yml`. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Owner** | Platform/DevOps |
| **Target Date** | 2026-10-26 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-002, OPS-008 |

**Evidence — `.github/workflows/ci.yml:35-39`** *(supports: "push and cache coordinates disagree with each other and with prod")*:
```yaml
          tags: |
            mko-bazuna:ci
            ghcr.io/mko-bazuna/mko_bazuna:${{ github.sha }}
          cache-from: type=registry,ref=ghcr.io/manicko/mko_bazuna:buildcache
          cache-to: type=registry,ref=ghcr.io/mko-bazuna/mko-bazuna:buildcache,mode=max
```

**Evidence — `docker-compose.prod.yml:8` and `.env.prod.example:82`** *(supports: "production pulls from the `manicko` namespace")*:
```yaml
    image: ${REGISTRY:-ghcr.io}/${REPOSITORY:-manicko/mko_bazuna}:${IMAGE_TAG:-latest}
```
```text
82: REPOSITORY=manicko/mko_bazuna
```

---

#### OPS-010: [MEDIUM] — Bot-marker freshness is disabled in every shipped config, so readiness cannot detect a wedged bot

| Field | Value |
|---|---|
| **ID** | OPS-010 |
| **Title** | Bot-marker freshness is disabled in every shipped config, so readiness cannot detect a wedged bot |
| **Severity** | MEDIUM |
| **Category** | Reliability / health contract |
| **File(s)** | `src/backend/config/settings/base.py:322-329`, `src/backend/apps/core/views.py:112-129`, `docker-compose.yml:239`, `.env.prod.example` |
| **Status** | Open |
| **Problem** | `readiness_check` verifies the Redis `bot:liveness` marker only when `BOT_HEALTH_CHECK_ENABLED` is true (`views.py:113-114`), and `base.py:329` defaults it to `False`. No compose file sets it, and it is absent from `.env.prod.example` and from the working-tree `.env.prod`. The base compose sets `BOT_HEALTH_STALE_SECONDS=120` for `web` (`docker-compose.yml:239`) but never the enable flag, so the staleness window is configured for a check that is switched off. |
| **Impact** | The readiness endpoint — which is the deploy gate (`deploy.yml:94`) and the documented rollback validation target (`rollback.md:332`) — cannot observe a bot that is alive but no longer polling: a retry loop, a stuck long-poll, or a wedged dispatcher all leave `web` reporting `ready` and the deploy declared successful. Sellers would see ads accepted by the bot that are never actually published. Live evidence below shows the shipped state: `bot: disabled`. |
| **Root Cause** | The coupling was deliberately defaulted off to keep web readiness independent of bot liveness (`base.py:322-328` documents the reasoning) and the re-enabling path was never wired into the production configuration, so the documented "readiness probes DB + cache + bot-marker freshness" control exists only in code. |
| **Recommendation** | Set `BOT_HEALTH_CHECK_ENABLED=true` in `docker-compose.prod.yml`'s `web` service (it is already the intended coupling, given `BOT_HEALTH_STALE_SECONDS` is shipped there) and add the key to `.env.prod.example`. If the decoupling is genuinely wanted, remove `BOT_HEALTH_STALE_SECONDS` from the `web` service and drop the bot claim from `docs/ops/rollback.md:81,443` and `docs/ops/docker-deployment.md:334` so the documentation matches the intent — but do not leave a configured-but-disabled probe described as active. Note that Phase 05's AD-008 also warns that any alerting keyed on queue depth can never fire; that is a separate signal from this one. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Owner** | Backend lead |
| **Target Date** | 2026-10-19 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-007, OPS-018 |

**Evidence — `src/backend/config/settings/base.py:322-329`** *(supports: "the coupling defaults off")*:
```python
# When True, the web readiness probe also verifies the Redis bot:liveness marker
# and gates web readiness on it. Defaults to False so web readiness is decoupled
# from bot liveness: when False (the default), the probe reports
# checks["bot"] == "disabled" and does not gate web readiness on the bot.
BOT_HEALTH_CHECK_ENABLED = env.bool("BOT_HEALTH_CHECK_ENABLED", default=False)
```

**Evidence — live `/health/ready/` from the shipped image** *(supports: "the production-shaped configuration reports the bot check as disabled")*:
```json
{"version": 1, "status": "ready", "checks": {"database": "ok", "cache": "ok", "bot": "disabled"}}
```

**Evidence — `grep -c BOT_HEALTH_CHECK_ENABLED docker-compose*.yml .env.prod.example`** *(supports: "no shipped file enables it")*:
```text
0
```

---

#### OPS-011: [MEDIUM] — No alerting channel exists anywhere in the system

| Field | Value |
|---|---|
| **ID** | OPS-011 |
| **Title** | No alerting channel exists anywhere in the system |
| **Severity** | MEDIUM |
| **Category** | Observability |
| **File(s)** | `src/backend/config/settings/base.py:378-402`, `.env.prod.example` (Email / Analytics sections), `docker-compose.prod.yml:129-169` |
| **Status** | Open |
| **Problem** | A repository-wide search for `send_mail`, `EmailMessage` and `mail.outbox` over `src/` returns zero production hits — no management command, service or signal ever sends a notification. `SUPPORT_NOTIFICATION_RECIPIENTS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` and `DEFAULT_FROM_EMAIL` are configured in `base.py:378-402`, and `EMAIL_HOST` is a *mandatory* production gate (`prod.py:203-208`), but no code consumes them. There is likewise no webhook, no Telegram admin-notify command, and no process that inspects container health, dump freshness, deploy outcome or the SLO alerts. |
| **Impact** | The system has no way to tell a human that something is wrong. A container stuck in `unhealthy`, a backup job that died, a nightly `send_alerts` that failed, an SLO breach, or a failed deploy are all discovered by users filing complaints. `EMAIL_HOST` is required at boot to protect a delivery path that does not exist, so the gate produces boot-time fragility (see OPS-013 for how a related optional setting crashes boot) with no compensating benefit. |
| **Root Cause** | Alerting was designed as a Prometheus/Grafana deployment (OPS-003) that was never stood up, and no in-process notification path was built as a floor. The email settings were configured speculatively against an assumed future feature set ("password resets, alert notifications, and seller confirmations" per the `prod.py:198-199` comment) — Phase 04's validation already noted that no such flows exist. |
| **Recommendation** | Pick one concrete floor and implement it: a `manage.py notify_operator` command invoked by the `backup` service after each dump and by a small host-side cron that reads `docker compose ps --format json`, delivering via Telegram bot message (the bot already has a transport) rather than SMTP. If a full Prometheus stack is not going to be deployed soon, delete `docs/ops/prometheus-slo-alerts.yaml` and `grafana-slo-dashboard.json` or move them under a clearly-labelled "planned" heading so they stop reading as active controls. |
| **Effort** | M |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Owner** | Platform/DevOps |
| **Target Date** | 2026-11-15 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-003, OPS-005, OPS-021 |

**Evidence — `grep -rn "send_mail|EmailMessage|mail.outbox" src/`** *(supports: "no production code sends a notification")*:
```text
src/backend/config/settings/tests/test_csrf_trusted_origins.py:70:    env["EMAIL_BACKEND"] = overrides.pop(
src/backend/config/settings/tests/test_prod_logging.py:190:    print(f'email_backend={settings.EMAIL_BACKEND}'); "
src/backend/config/settings/base.py:31:    "EMAIL_USE_TLS", "EMAIL_TIMEOUT", "EMAIL_BACKEND",
```
*(every hit is a test fixture or the allowlist; zero senders)*

---

#### OPS-012: [MEDIUM] — Gunicorn access and error logs bypass the redacting JSON formatter

| Field | Value |
|---|---|
| **ID** | OPS-012 |
| **Title** | Gunicorn access and error logs bypass the redacting JSON formatter |
| **Severity** | MEDIUM |
| **Category** | Observability / logging |
| **File(s)** | `gunicorn.conf.py:30-35`, `src/backend/config/settings/prod.py:22-67`, `src/backend/apps/core/utils/json_logging.py:68-93` |
| **Status** | Open |
| **Problem** | Production configures a structured `LOGGING` dict with `RedactingJsonFormatter` for the `django*` and `apps*` logger trees (`prod.py:22-67`) and sets the root logger to `WARNING`. Gunicorn's own `accesslog`/`errorlog` are `"-"` (stdout/stderr) at `loglevel = "info"` (`gunicorn.conf.py:30-35`); these are emitted by gunicorn's own handlers and never pass through the Django `LOGGING` tree or the redactor. |
| **Impact** | The production log stream is a mixture of JSONL and unstructured plaintext, with the access log — the highest-volume record type — in the unstructured form. A log aggregator cannot parse the two uniformly, and a raw request line is not subject to `RedactingJsonFormatter`'s key-based redaction, so any future query-string parameter that carries a token would be written verbatim. Setting the Django root logger to `WARNING` also discards `django.server` 4xx lines, so the plaintext gunicorn log becomes the *only* record of HTTP outcomes, with no level or severity normalisation. |
| **Root Cause** | The JSON logging work was scoped to the Django logger tree and never extended to the WSGI server that produces the bulk of the records. `disable_existing_loggers: False` does not help because gunicorn installs its own handlers before Django configures logging. |
| **Recommendation** | Route gunicorn through the same formatter (`logconfig_dict` in `gunicorn.conf.py` pointing `gunicorn.access`/`gunicorn.error` at a `RedactingJsonFormatter` handler), and set a structured `access_log_format` that emits named fields rather than a raw request line. Alternatively, set `accesslog = None` and instrument request metrics/IDs through Django, where the redaction already applies. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Owner** | Backend lead |
| **Target Date** | 2026-12-15 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-003, OPS-011 |

**Evidence — `gunicorn.conf.py:29-35`** *(supports: "gunicorn logs straight to stdout/stderr at info level, outside the Django LOGGING tree")*:
```python
# Log level for Gunicorn's own error/access logs.
loglevel = "info"

# Stream access and error logs to stdout/stderr so the container runtime
# captures them.
accesslog = "-"
errorlog = "-"
```

**Evidence — `docker logs` of the shipped image** *(supports: "the plaintext access/error lines coexist with the boot-time `check --deploy` output, none of it JSON")*:
```text
[2026-09-28 04:12:04 -0500] [1] [INFO] Starting gunicorn 26.0.0
[2026-09-28 04:12:04 -0500] [1] [INFO] Listening at: http://0.0.0.0:8000 (1)
[2026-09-28 04:12:04 -0500] [1] [INFO] Using worker: sync
[2026-09-28 04:12:04 -0500] [1] [INFO] Booting worker with pid: 18
?: (security.W018) You should not have DEBUG set to True in deployment.
```

---

#### OPS-013: [MEDIUM] — A malformed `SENTRY_DSN` raises out of the prod settings import and crash-loops every service

| Field | Value |
|---|---|
| **ID** | OPS-013 |
| **Title** | A malformed `SENTRY_DSN` raises out of the prod settings import and crash-loops every service |
| **Severity** | MEDIUM |
| **Category** | Observability / error tracking |
| **File(s)** | `src/backend/config/settings/prod.py:69-85`, `src/backend/config/settings/base.py:355-357` |
| **Status** | Open |
| **Problem** | `prod.py:72-85` initialises Sentry inside `if SENTRY_DSN and not DEBUG:` and guards only `ImportError`. `sentry_sdk.init()` raises `sentry_sdk.utils.BadDsn` for a malformed DSN — a leading space, a trailing newline from a copy-paste, or an unrecognised scheme — and that exception is not caught. It propagates out of the settings module import, so every process that imports `config.settings.prod` (`web`, `bot`, `migrate`, `load_cities`, `load_catalog`, `create_admin`, `seed`, `scheduler`) fails at import with `restart: unless-stopped` looping. |
| **Impact** | A purely optional, non-security integration setting can take the entire production stack offline. The failure mode is maximally confusing: the log shows a settings import traceback rather than "SENTRY_DSN is invalid", and the operator's instinct is to check the secret store rather than the DSN format. It also means the error-tracking SDK — the one component whose whole purpose is to be present when things go wrong — is a source of the outage instead. |
| **Root Cause** | The `try` block was scoped to the "dependency may not be installed" case and not to the "operator supplied a bad value" case. `SENTRY_DSN` is optional with a `""` default (`base.py:357`) and is shipped empty in `.env.prod.example:73`, so the happy path is untested; `test_prod_logging.py:105-118` only covers the *absent* DSN, not a malformed one. |
| **Recommendation** | Validate the DSN before use (a scheme/`@`/project-id shape check, or `sentry_sdk.init(..., _experiments={...})` with a guarded `except Exception`) and emit a single `logger.error("SENTRY_DSN is invalid — error tracking disabled", extra={...})` naming the variable but not the value, mirroring the value-free style of `_validate_production_secret`. Add a test case for a malformed DSN asserting the settings import still succeeds. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Owner** | Backend lead |
| **Target Date** | 2026-10-19 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-011, OPS-018 |

**Evidence — `src/backend/config/settings/prod.py:72-85`** *(supports: "only ImportError is guarded")*:
```python
if SENTRY_DSN and not DEBUG:  # noqa: F405 (SENTRY_DSN from base via *)
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=SENTRY_DSN,  # noqa: F405
            send_default_pii=False,
            traces_sample_rate=0.1,
        )
        logging.getLogger(__name__).info("Sentry error tracking initialized")
    except ImportError:
        logging.getLogger(__name__).warning(
            "sentry-sdk not installed — error tracking disabled"
        )
```

**Evidence — executed in the shipped runtime image** *(supports: "an invalid DSN raises `BadDsn`, which the guard does not catch")*:
```text
$ python -c "import sentry_sdk; sentry_sdk.init(dsn='not-a-valid-dsn', send_default_pii=False, traces_sample_rate=0.1)"
sentry_sdk.utils.BadDsn -> Unsupported scheme ''
```

---

#### OPS-014: [MEDIUM] — Backup job runs as root, has no healthcheck, and deploy backups are never pruned

| Field | Value |
|---|---|
| **ID** | OPS-014 |
| **Title** | Backup job runs as root, has no healthcheck, and deploy backups are never pruned |
| **Severity** | MEDIUM |
| **Category** | Container runtime / DR |
| **File(s)** | `docker-compose.prod.yml:131-169`, `.github/workflows/deploy.yml:78-82` |
| **Status** | Open |
| **Problem** | The `backup` service has `cap_drop: ["ALL"]`, `read_only: true`, `tmpfs` and `no-new-privileges`, but no `user:` directive, so the `postgres:18-alpine` container runs as UID 0 — the only service in the production manifest besides the documented `db`/`nginx` exceptions that does. It also declares no `healthcheck`, so Docker cannot distinguish "looping and dumping" from "looping and failing". Separately, the deploy workflow writes its pre-deploy snapshot as `/app/backups/backup-YYYYmmdd-HHMMSS.dump`, a filename pattern that the retention logic never matches. |
| **Impact** | A root-run container that holds `POSTGRES_PASSWORD` in its environment and writes to a host bind mount is a wider blast radius than the hardening on the same block suggests. With no healthcheck and no dump-age alert (OPS-011), a job that has been failing for a week is indistinguishable from a healthy one. And because pruning matches `dump_*.dump` only, the deploy path's `backup-*.dump` files accumulate on the production host indefinitely until the disk fills — at which point the database volume is at risk. |
| **Root Cause** | The backup block was written for functional correctness (`pg_dump` in a loop) and given the standard hardening keys by pattern, but nobody checked whether the `user` directive and the filename conventions lined up between the two backup producers. |
| **Recommendation** | Add `user: postgres` (or a numeric uid) to the `backup` service, add a healthcheck that asserts a dump newer than 26 h exists, and align the filename convention — either have `deploy.yml` write `dump_<ts>.dump` or widen the prune glob in both `docker-compose.prod.yml:153` and `Makefile:344` to `*.dump`. Add a guard test asserting every service in the production manifest that is not on an explicit exception list declares a `user:`. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Owner** | Platform/DevOps |
| **Target Date** | 2026-11-15 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-005, OPS-011, OPS-021 |

**Evidence — `docker-compose.prod.yml:139-169`** *(supports: "no `user:`, no healthcheck, and pruning that matches only `dump_*.dump`")*:
```yaml
    volumes:
      - ./backups:/backups
    command:
      - /bin/sh
      - -c
      - |
        set -e;
        until pg_isready -h $$POSTGRES_HOST -p $$POSTGRES_PORT; do sleep 5; done;
        while true; do
          date=$$(date +%Y%m%d);
          pg_dump --no-sync -h $$POSTGRES_HOST -p $$POSTGRES_PORT
            -U $$POSTGRES_USER -d $$POSTGRES_DB -F c
            -f /backups/dump_$$date.dump;
          echo "Backup completed: dump_$$date.dump";
          find /backups -name 'dump_*.dump' -mtime +7 -delete 2>/dev/null || true;
          sleep 86400;
        done
```

**Evidence — `.github/workflows/deploy.yml:78-82`** *(supports: "the deploy path writes a filename the prune glob never matches")*:
```bash
            mkdir -p /app/backups
            docker compose exec -T db pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" -F c \
              > "/app/backups/backup-$(date +%Y%m%d-%H%M%S).dump"
```

---

#### OPS-015: [MEDIUM] — PgBouncer is configured for md5 auth against PostgreSQL 18 SCRAM verifiers

| Field | Value |
|---|---|
| **ID** | OPS-015 |
| **Title** | PgBouncer is configured for md5 auth against PostgreSQL 18 SCRAM verifiers |
| **Severity** | MEDIUM |
| **Category** | Configuration |
| **File(s)** | `docker-compose.prod.yml:171-183`, `src/backend/config/settings/base.py:248-250,261` |
| **Status** | Open |
| **Problem** | The opt-in `pgbouncer` service sets `PGBOUNCER_AUTH_TYPE=md5` with `PGBOUNCER_USER=${POSTGRES_USER}`, the same role whose password the PostgreSQL 18 image stores using the engine default. On this engine that default is `scram-sha-256`, and `pg_authid.rolpassword` holds a `SCRAM-SHA-256$…` verifier, which an md5 authenticator cannot use. The rest of the application is explicitly designed for this pooler (`base.py:248-250` sets `prepare_threshold: None` and `base.py:261` sets `CONN_MAX_AGE = 0` "PgBouncer async safety"). |
| **Impact** | Enabling `--profile pgbouncer` produces a pooler that accepts TCP connections (`pg_isready` reports healthy) but rejects every client authentication. Anyone following the documented connection-pooling guidance would redirect the application at a component that cannot authenticate, and the `pg_isready` healthcheck would report `healthy` throughout, so the failure surfaces only as application connection errors. |
| **Root Cause** | `md5` was carried over from a pre-PostgreSQL-14 default. Since the service is profile-gated it is never exercised by `docker compose config` in any documented command, and no test asserts the auth type against the engine's `password_encryption`. |
| **Recommendation** | Set `PGBOUNCER_AUTH_TYPE=scram-sha-256` (PgBouncer ≥1.19 supports SCRAM verifiers in `auth_file`) and document the profile in `docs/ops/docker-deployment.md` with the exact enable command. Add a settings test asserting that whenever the PgBouncer profile is described as available, its `PGBOUNCER_AUTH_TYPE` matches the engine's `password_encryption` default. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Owner** | Platform/DevOps |
| **Target Date** | 2026-12-15 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-005, OPS-009 |

**Evidence — `docker-compose.prod.yml:174-181`** *(supports: "md5 auth against a SCRAM-stored role")*:
```yaml
    environment:
      - POSTGRES_HOST=db
      - POSTGRES_PORT=5432
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}
      - PGBOUNCER_DATABASE=${POSTGRES_DB:?POSTGRES_DB must be set}
      - PGBOUNCER_USER=${POSTGRES_USER:?POSTGRES_USER must be set}
      - PGBOUNCER_AUTH_TYPE=md5
      - PGBOUNCER_POOL_MODE=transaction
```

**Evidence — `psql` on the running PostgreSQL 18 instance** *(supports: "the engine stores SCRAM verifiers, which md5 cannot validate")*:
```text
SHOW password_encryption  ->  scram-sha-256
SELECT rolname, left(rolpassword,14) FROM pg_authid WHERE rolpassword IS NOT NULL
  ->  postgres|SCRAM-SHA-256$
```

---

#### OPS-016: [MEDIUM] — No `concurrency` group on CI or deploy; overlapping runs race shared refs

| Field | Value |
|---|---|
| **ID** | OPS-016 |
| **Title** | No `concurrency` group on CI or deploy; overlapping runs race shared refs |
| **Severity** | MEDIUM |
| **Category** | CI/CD gating |
| **File(s)** | `.github/workflows/ci.yml:1-7`, `.github/workflows/deploy.yml:1-19` |
| **Status** | Open |
| **Problem** | `ci.yml` and `deploy.yml` declare no `concurrency:` block, unlike `ci-nightly.yml:8-11` and `restore-test.yml:12-15` which both do. Two `push` events minutes apart run two `build` jobs concurrently; each pushes its own SHA tag but both write the same `:buildcache` reference, and each logs into GHCR with the same `GITHUB_TOKEN`. Two `workflow_dispatch` deploys likewise interleave their `pull` / `up -d` sequences against the same production host. |
| **Impact** | Concurrent deploys interleave `docker compose pull` and `up -d`, so the `PREVIOUS_IMAGE_TAG` one run captures may be overwritten by the other before it is used, and the health gate can validate a half-applied mix of images. Concurrent builds corrupt each other's exported build cache (last writer wins) and burn the runner budget re-doing work. Neither failure is loud: both produce green runs. |
| **Root Cause** | The two newest workflows (`ci-nightly.yml`, `restore-test.yml`) were written with `concurrency` while the two oldest (`ci.yml`, `deploy.yml`) predate the convention, and no lint or test enforces its presence. |
| **Recommendation** | Add `concurrency: {group: ci-${{ github.ref }}, cancel-in-progress: true}` to `ci.yml` and `concurrency: {group: deploy-production, cancel-in-progress: false}` to `deploy.yml` (never cancel a deploy mid-flight). Add a guard test asserting every workflow file declares a `concurrency` key. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Owner** | Platform/DevOps |
| **Target Date** | 2026-11-15 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-002, OPS-007 |

**Evidence — `grep -n concurrency .github/workflows/*.yml`** *(supports: "only the two newest workflows have one")*:
```text
(no matches in ci.yml, deploy.yml; present in ci-nightly.yml:8-11 and restore-test.yml:12-15)
```

---

#### OPS-017: [MEDIUM] — Pipeline supply chain: mutable action tags and an unverified `curl | tar` gitleaks fetch

| Field | Value |
|---|---|
| **ID** | OPS-017 |
| **Title** | Pipeline supply chain: mutable action tags and an unverified `curl \| tar` gitleaks fetch |
| **Severity** | MEDIUM |
| **Category** | Supply chain |
| **File(s)** | `.github/workflows/ci.yml:16,19,30,43,53,317,339,363`, `.github/workflows/deploy.yml:28,43`, `.github/dependabot.yml:4-12` |
| **Status** | Open |
| **Problem** | Every third-party action in the pipeline is referenced by a mutable tag: `actions/checkout@v4`, `docker/setup-buildx-action@v3`, `docker/login-action@v3`, `docker/build-push-action@v7`, `aquasecurity/trivy-action@v0.36.0`, `github/codeql-action/upload-sarif@v4`, `astral-sh/setup-uv@v5`, `appleboy/ssh-action@v1.2.0`. The `security` job additionally downloads the gitleaks binary with `curl -sSfL https://github.com/gitleaks/gitleaks/releases/download/v8.27.2/… | tar xz` and executes it, with no checksum or signature verification — and that job holds `security-events: write` and a `GITHUB_TOKEN`. `dependabot.yml` covers the `github-actions` and `uv` ecosystems, so Dependabot will bump these tags, but a tag is a pointer, not a pin. |
| **Impact** | The pipeline that is supposed to be the trust boundary is itself the least-pinned part of the system. A compromised or hijacked upstream tag — plausible for `appleboy/ssh-action`, a small third-party action that receives the production SSH private key as a secret — executes with the pipeline's token on every run. The unverified gitleaks tarball is the same class of exposure, and it is the step that decides whether a secret is allowed into the repository. |
| **Root Cause** | Action pinning was never adopted; the `security` job needed a tool that is not a GitHub Action and the quickest route was a pipe-to-shell install, which is the exact pattern the job exists to prevent elsewhere. |
| **Recommendation** | Pin all actions to full commit SHAs with the version in a trailing comment (Dependabot keeps these updated), and replace the gitleaks pipe with either a maintained action or a `sha256sum --check` against a checksum committed to the repository. Both changes are mechanical and Dependabot-compatible. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Owner** | Platform/DevOps |
| **Target Date** | 2026-12-15 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-001, OPS-009 |

**Evidence — `.github/workflows/ci.yml:349-353`** *(supports: "the secret-scanning binary is fetched and executed with no integrity verification")*:
```yaml
      # --- Secret scanning ---
      - name: Run gitleaks secret scan
        run: |
          curl -sSfL https://github.com/gitleaks/gitleaks/releases/download/v8.27.2/gitleaks_8.27.2_linux_x64.tar.gz | tar xz
          ./gitleaks detect --source . --exit-code 1 --report-format sarif --report-path gitleaks-results.sarif
```

**Evidence — `.github/workflows/deploy.yml:41-51`** *(supports: "a mutable third-party action receives the production SSH private key")*:
```yaml
      - name: Deploy to production via SSH
        id: deploy
        uses: appleboy/ssh-action@v1.2.0
        env:
          IMAGE_TAG: ${{ steps.set_tag.outputs.image_tag }}
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
```

---

#### OPS-018: [MEDIUM] — Ops documentation asserts controls that are not live

| Field | Value |
|---|---|
| **ID** | OPS-018 |
| **Title** | Ops documentation asserts controls that are not live |
| **Severity** | MEDIUM |
| **Category** | Documentation |
| **File(s)** | `docs/ops/docker-deployment.md:427,1011-1015`, `docs/ops/rollback.md:79,81,443`, `docs/ops/restore.md:83` |
| **Status** | Open |
| **Problem** | Several passages in `docs/ops/` describe controls that either do not run or cannot work. `docker-deployment.md:427` enumerates the `deploy-check` job's environment including `REDIS_URL=redis://redis:6379/0` and calls it a blocking gate; the job at `ci.yml:508-519` sets no `REDIS_URL` and no `EMAIL_HOST` and aborts on import (that defect belongs to Phase 02 as CFG-002 and is deliberately not re-filed here — only the documentation claim is in scope). `docker-deployment.md:1013-1015` states "An external Prometheus instance scrapes it on its own schedule", while nginx returns `403` to any scraper outside `127.0.0.1` and no Prometheus is deployed. `rollback.md:79` offers `git checkout .env.prod` as the config-rollback procedure for a file that is gitignored and untracked. `rollback.md:81,443` presents `checks.bot == "ok"` in the readiness response as a rollback validation criterion when the probe reports `disabled`. `restore.md:83` names the production database `bazuna_db`, a name that appears in no template. |
| **Impact** | The ops documentation is the only description of the production system, and a reader cannot tell which parts are live. An engineer planning capacity or on call during an incident will reason from a burn-rate alerting setup, a bot-marker readiness gate and a config-rollback-by-git procedure, none of which work as described. Because these are narrative claims rather than code, no test fails when they drift. |
| **Root Cause** | The docs were written when each control was added, and each control was subsequently changed, disabled or found not to work (OPS-001, OPS-003, OPS-006, OPS-010) without a doc pass. The project rule "documentation must always stay current" is machine-enforced for i18n completeness but not for ops claims. |
| **Recommendation** | Bring `docs/ops/` back in line with the repository: state that no Prometheus/Grafana stack is deployed and that the alert rules and dashboard are aspirational; correct or remove the `git checkout .env.prod` step; correct the readiness criterion to what the probe actually returns today (or fix the probe via OPS-010 first); drop the `REDIS_URL` claim from the deploy-check paragraph. Then extend the existing `test_docs_ci_parity.py` pattern to assert that every `ghcr.io` literal, every `docker compose` command's flags, and every env-var name quoted in `docs/ops/` appears in the corresponding live file. |
| **Effort** | M |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Owner** | Platform/DevOps |
| **Target Date** | 2026-11-01 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-001, OPS-003, OPS-006, OPS-010, OPS-013 |

**Evidence — `docs/ops/docker-deployment.md:427`** *(truncated) *(supports: "the doc claims a gate configuration the job does not have")*:
```text
…It sets all required production env vars to valid non-secret placeholders — `DJANGO_SECRET_KEY`
(a 50+ character literal), `BOT_TOKEN`, `GOOGLE_TRANSLATE_API_KEY`, `SITE_URL=https://example.com`,
`ALLOWED_HOSTS=example.com`, `CSRF_TRUSTED_ORIGINS=https://example.com`,
`REDIS_URL=redis://redis:6379/0`, and `DATABASE_URL` …
```

**Evidence — `.github/workflows/ci.yml:510-518`** *(supports: "`REDIS_URL` is not in the job's env block")*:
```yaml
    env:
      DJANGO_SETTINGS_MODULE: config.settings.prod
      DJANGO_SECRET_KEY: "ci-deploy-check-secret-key-not-for-production-use-1234567890"
      BOT_TOKEN: ci-test-bot-token
      GOOGLE_TRANSLATE_API_KEY: ci-test-translate-key
      SITE_URL: https://example.com
      ALLOWED_HOSTS: example.com
      CSRF_TRUSTED_ORIGINS: https://example.com
      DATABASE_URL: postgres://postgres:postgres@localhost:5432/mko_bazuna
```

**Evidence — `docs/ops/docker-deployment.md:1013-1015`** *(supports: "the doc promises an external scrape the configuration blocks")*:
```text
Production exposes a Prometheus `/metrics` endpoint behind the `web` service (wired via
`django_prometheus` in `INSTALLED_APPS`, middleware, and `path("", include("django_prometheus.urls"))`
in `config/urls.py`). An external Prometheus instance scrapes it on its own schedule.
```

**Evidence — `docs/ops/rollback.md:78-81`** *(supports: "config rollback via git, and the bot readiness criterion")*:
```text
| Config | `git checkout .env.prod` to pinned commit, re-deploy | Low |
| Schema | `migrate <app> <previous_migration>` + data backfill | High |
| Health | Liveness: `/health/live/` · Readiness: `/health/ready/` (incl. Redis `bot:liveness`, scheduler marker via `healthcheck-scheduler.sh`) | — (validation) |
```

---

### LOW

#### OPS-019: [LOW] — `db`/`redis` healthchecks have no `start_period`, so the whole boot chain can flap

| Field | Value |
|---|---|
| **ID** | OPS-019 |
| **Title** | `db`/`redis` healthchecks have no `start_period`, so the whole boot chain can flap |
| **Severity** | LOW |
| **Category** | Reliability |
| **File(s)** | `docker-compose.yml:23-27,41-45` |
| **Status** | Open |
| **Problem** | The `db` and `redis` healthchecks declare `interval`, `timeout` and `retries` but no `start_period` (Docker's default is 0), so a failing probe counts toward `retries` immediately. Every other service in the chain — `migrate`, `load_cities`, `load_catalog`, `create_admin`, `web`, `bot` — gates on `condition: service_healthy` against one or both of them. |
| **Impact** | On a cold start or a host reboot, PostgreSQL 18 needs several seconds for crash recovery and to reach `pg_isready`; if it misses `retries: 5` at a 5 s interval the container is marked `unhealthy` before it was ever given a chance, and the whole `depends_on` chain fails to start. `restart: always` eventually recovers, but the failure surfaces as a cascade of one-shot services exiting non-zero rather than as "database still starting". |
| **Root Cause** | The `start_period` hardening was applied to the application services (which do declare it) but not to the stateful ones, whose healthchecks predate the convention. |
| **Recommendation** | Add `start_period: 30s` to both the `db` and `redis` healthchecks — a one-line change per service, safe in every environment. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Owner** | Platform/DevOps |
| **Target Date** | 2026-12-15 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-007 |

**Evidence — `docker-compose.yml:23-27`** *(supports: "`db` has interval/timeout/retries but no start_period, and seven other services gate on it")*:
```yaml
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:?POSTGRES_USER must be set} -d ${POSTGRES_DB:?POSTGRES_DB must be set}"]
      interval: 5s
      timeout: 5s
      retries: 5
```

---

#### OPS-020: [LOW] — Public readiness endpoint exposes internal dependency state

| Field | Value |
|---|---|
| **ID** | OPS-020 |
| **Title** | Public readiness endpoint exposes internal dependency state |
| **Severity** | LOW |
| **Category** | Security |
| **File(s)** | `docker/nginx/nginx.conf:130-137,159-168`, `src/backend/apps/core/views.py:131-138` |
| **Status** | Open |
| **Problem** | nginx proxies `location /health/` with no `allow`/`deny` and no `limit_req`, and the view returns `{"version": 1, "status": "ready", "checks": {"database": "ok", "cache": "ok", "bot": "disabled"}}` — or, when degraded, exactly which of database, cache and bot has failed. The `/metrics` endpoint declared immediately below is correctly restricted to `127.0.0.1`; the health endpoints are not. |
| **Impact** | An anonymous caller can poll readiness and read both service availability and the identity of the failing dependency, which is useful reconnaissance when timing an attack and makes "is it down or just me" trivial to answer. The liveness/readiness split is otherwise sound, so the exposure is small — but it is free to close. |
| **Root Cause** | The `/metrics` restriction was added when the endpoint was added; `/health/` predates it and was never revisited, and the later liveness/readiness split did not carry an access-control decision with it. |
| **Recommendation** | Restrict `/health/` the same way `/metrics` is restricted — `allow 127.0.0.1` plus a dedicated internal listener, or `limit_req` plus a reduced public body. If the endpoints must stay public for an external uptime probe, return only `{"status": "alive"}` from the public alias and keep the per-dependency breakdown on an internal-only path. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Owner** | Platform/DevOps |
| **Target Date** | 2026-12-15 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-003 |

**Evidence — `docker/nginx/nginx.conf:130-137` vs `:159-162`** *(supports: "the health path is proxied with no access control, unlike /metrics")*:
```nginx
        # Health check endpoint (no rate limiting, no auth)
        location /health/ {
            proxy_pass http://web:8000;
            ...
        # Metrics endpoint — restricted to localhost (production monitoring only)
        location = /metrics {
            allow 127.0.0.1;
            deny all;
```

**Evidence — `curl http://localhost:8000/health/` from the shipped image** *(supports: "the public response names each internal dependency")*:
```json
{"version": 1, "status": "ready", "checks": {"database": "ok", "cache": "ok", "bot": "disabled"}}
```

---

#### OPS-021: [LOW] — Backup loop has no drift compensation or freshness assertion; dead comment in `ci.yml`

| Field | Value |
|---|---|
| **ID** | OPS-021 |
| **Title** | Backup loop has no drift compensation or freshness assertion; dead comment in `ci.yml` |
| **Severity** | LOW |
| **Category** | Maintainability |
| **File(s)** | `docker-compose.prod.yml:146-155`, `.github/workflows/ci.yml:375-382` |
| **Status** | Open |
| **Problem** | The backup loop is `pg_dump … ; sleep 86400`, so the true interval is 24 h plus the dump duration and any retry delay, and nothing anywhere asserts that the newest dump is recent. Separately, `ci.yml:375-381` is a seven-line comment explaining the `deploy-check` gate — that it "replaces" a previous test-settings step, why no DB service container is needed, that the env vars are placeholders — but it sits immediately above the `load-test:` job, not `deploy-check:`; it documents a job declared 126 lines later. |
| **Impact** | Neither is an outage on its own. The drift makes the effective RPO slightly worse than the documented 24 h with no way to measure it, and the misplaced comment means the next editor working on `load-test` reads rationale that does not apply to it, while the rationale for the actual gate sits 130 lines away from the code it explains. |
| **Root Cause** | The loop was written as the simplest possible daily job; the comment block was inserted above the wrong job key when the deploy-check job was later moved to the end of the file. |
| **Recommendation** | Compute the sleep from the dump's own start time (`sleep $(( 86400 - elapsed ))`) and add a `healthcheck` to the `backup` service asserting a dump newer than 26 h exists — this closes the detection gap named in OPS-005 and OPS-011 with the smallest possible change. Move the `ci.yml:375-381` comment to sit directly above `deploy-check:`. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Owner** | Platform/DevOps |
| **Target Date** | 2026-12-15 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-005, OPS-011, OPS-014 |

**Evidence — `.github/workflows/ci.yml:375-384`** *(supports: "the deploy-check rationale comment is attached to the `load-test` job")*:
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

**Evidence — `docker-compose.prod.yml:152-155`** *(supports: "a fixed 24 h sleep with no age assertion")*:
```yaml
          echo "Backup completed: dump_$$date.dump";
          find /backups -name 'dump_*.dump' -mtime +7 -delete 2>/dev/null || true;
          sleep 86400;
        done
```

---

## Cross-Finding Analysis

- **Merge candidates:** OPS-001 and OPS-018 share a root cause (documentation and regression guards describe controls that do not function) but have different fixes and different owners, so they are kept separate. OPS-005, OPS-007 and OPS-014 all stem from the same compose-profiles gap and could be merged into one "the production profile set is invisible to the deploy path" finding; they are kept separate because each has an independent consequence (no backup, stale scheduler, root container) and an independent fix.
- **Conflicting evidence:** None. OPS-006 (runbooks not executable) and OPS-018 (docs assert non-live controls) point the same way and are consistent: OPS-006 is the executable-command limb, OPS-018 the narrative-claim limb. The registry-namespace evidence in OPS-009 and the `latest`-tag evidence in OPS-008 are consistent with each other (both mean the deploy path is not pinned to a specific artifact).
- **Dependency chains:** OPS-010 must be resolved before `docs/ops/rollback.md:81,443` can be written correctly (the rollback readiness criterion is either a real gate or a documentation fix — see OPS-018). OPS-004 should land together with OPS-005: an off-host copy of the newest dump is what makes a *real* restore-test possible, and a real restore-test is what makes the RPO/RTO numbers at `restore.md:195-225` meaningful. OPS-011 is the detection floor for OPS-005, OPS-014 and OPS-021 — none of those three can be noticed without it. OPS-002 should land after OPS-009, otherwise the deploy gate would assert on an image coordinate that may name the wrong repository.
- **Explicitly not re-filed:** CFG-002 (dead `deploy-check` job) belongs to Phase 02 and is referenced in OPS-018 only as the reason a documentation claim is wrong. ENT-001 (`child_exit` arbiter crash), ENT-002 (scheduler SIGTERM) and ENT-003 (process-local `last_daily`) belong to Phase 01; OPS-007 touches the scheduler only for image-version atomicity, which is a different property.

## Remediation Roadmap

Ordered fixes by Severity × Priority. One row per fix.

| Order | ID | Severity | Effort | Priority | Recommendation (summary) |
|-------|-----|----------|--------|----------|--------------------------|
| 1 | OPS-001 | CRITICAL | S | P0 | Fix bandit target paths; land a triage baseline for the 117 findings; guard on scanned-file count |
| 2 | OPS-006 | HIGH | S | P0 | Add `--env-file .env.prod` to every prod `docker compose` in `restore.md`/`rollback.md`; stop reading `.env.dev` credentials |
| 3 | OPS-007 | HIGH | S | P0 | Name the scheduler (and the profiles) in both `deploy.yml` recreate commands; guard the long-lived service set |
| 4 | OPS-008 | HIGH | S | P0 | Capture and roll back by image digest; forbid `IMAGE_TAG=latest` in the prod template |
| 5 | OPS-002 | HIGH | M | P0 | Add a `pull_request` trigger; require a green `CI` run for the dispatched SHA; constrain the `image_tag` input |
| 6 | OPS-003 | HIGH | M | P1 | Correct the alert selectors to the real series; deploy Prometheus + a `rule_files` config; add a scrape-contract test |
| 7 | OPS-004 | HIGH | M | P1 | Restore-test consumes a real production dump artifact; assert non-zero restored row counts |
| 8 | OPS-005 | HIGH | M | P1 | Enable the `backup` profile in the deploy path; replicate dumps off-host; alert on dump age |
| 9 | OPS-018 | MEDIUM | M | P1 | Bring `docs/ops/` claims back in line with the repository; add a docs-parity test |
| 10 | OPS-010 | MEDIUM | S | P1 | Set `BOT_HEALTH_CHECK_ENABLED=true` for `web` in prod, or drop the bot claim from the runbooks |
| 11 | OPS-013 | MEDIUM | S | P1 | Guard Sentry init against a malformed DSN; log value-free; add a bad-DSN test |
| 12 | OPS-009 | MEDIUM | S | P1 | Define the image coordinate once; align `cache-from` with `cache-to`; guard the literals |
| 13 | OPS-011 | MEDIUM | M | P1 | Build one concrete operator-notification floor (Telegram); demote the unconsumed alert artifacts |
| 14 | OPS-016 | MEDIUM | S | P2 | Add `concurrency` to `ci.yml` and `deploy.yml`; guard its presence |
| 15 | OPS-017 | MEDIUM | S | P2 | Pin actions to commit SHAs; verify the gitleaks download |
| 16 | OPS-014 | MEDIUM | S | P2 | `user:` + healthcheck on `backup`; align dump filename conventions with the prune glob |
| 17 | OPS-015 | MEDIUM | S | P2 | `PGBOUNCER_AUTH_TYPE=scram-sha-256`; document the profile |
| 18 | OPS-012 | MEDIUM | S | P2 | Route gunicorn access/error logs through `RedactingJsonFormatter` |
| 19 | OPS-019 | LOW | S | P2 | Add `start_period: 30s` to the `db` and `redis` healthchecks |
| 20 | OPS-020 | LOW | S | P2 | Restrict `/health/` at nginx or return a reduced body publicly |
| 21 | OPS-021 | LOW | S | P2 | Drift-compensate the backup sleep; move the misplaced `ci.yml` comment |

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|------------------------|
| OPS-001 | Med | Yes | No existing test distinguishes a working SAST step from a no-op; add an assertion on scanned-file count |
| OPS-002 | Low | Yes | No test covers workflow trigger wiring; add structural guards for `pull_request` and for a deploy↔CI dependency |
| OPS-003 | Med | Yes | No test evaluates a PromQL selector against a live scrape; add one |
| OPS-004 | Med | Yes | No test asserts the restored database is non-empty; add row-count preconditions to the Makefile target |
| OPS-005 | High | Yes | Off-host replication is new infrastructure with no coverage; verify the restore path reads from the new location |
| OPS-006 | Low | Yes | No test compiles the shell blocks in the runbooks; extract them into scripts and lint them |
| OPS-007 | Med | Yes | Recreating the scheduler during a deploy changes when `send_alerts` runs; assert the dedupe marker still holds (cross-reference ENT-003) |
| OPS-008 | Med | Yes | Digest-based rollback is a new code path; cover the "no previous digest" and "digest absent from registry" branches |
| OPS-009 | Med | Yes | No test asserts image-coordinate consistency across workflows; add a literal-scan guard |
| OPS-010 | Med | Yes | Turning the bot check on makes `web` readiness return 503 when the bot is down; cover that path in the deploy-gate tests |
| OPS-011 | Med | Yes | New command; needs a test asserting the message is sent once per event and not once per retry |
| OPS-012 | Low | Yes | `logconfig_dict` changes gunicorn startup; assert the server still boots and access lines still appear |
| OPS-013 | Low | Yes | Add the malformed-DSN settings test described in the recommendation |
| OPS-014 | Med | Yes | `user: postgres` on a `read_only` container — assert the bind mount stays writable and the loop still dumps |
| OPS-015 | Low | Yes | Profile-gated and untested; assert `docker compose config` renders and PgBouncer starts |
| OPS-016 | Low | Yes | `cancel-in-progress: true` on CI can cancel a needed build; verify branch-protection semantics after landing |
| OPS-017 | Low | Yes | SHA pinning changes every `uses:` line; verify each resolves |
| OPS-018 | Low | Yes | Documentation only, but the new docs-parity test must not encode today's wrong claims as truth |
| OPS-019 | Low | Yes | None; assert the compose healthcheck blocks still parse |
| OPS-020 | Low | No | An external uptime probe currently reading `/health/` would start receiving `403`; confirm no consumer depends on it |
| OPS-021 | Low | Yes | Drift compensation changes the backup cadence; assert the loop still sleeps between runs |

## Appendices

### Appendix A — Runtime verification transcript (live `/health/*` and `/metrics` from the shipped image)

```text
# Container started from mko-bazuna-test-web:latest on the mko-bazuna-test_default network
$ docker run --rm -d --name ops12probe --network mko-bazuna-test_default \
    -e DJANGO_SETTINGS_MODULE=config.settings.test \
    -e DATABASE_URL=postgres://postgres:postgres@db:5432/mko_bazuna \
    -e DJANGO_SECRET_KEY=ops12-probe-only-not-a-real-secret \
    mko-bazuna-test-web:latest \
    gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 1

live=200  ready=200  health=200  search=200

$ docker exec ops12probe curl -s http://localhost:8000/health/ready/
{"version": 1, "status": "ready", "checks": {"database": "ok", "cache": "ok", "bot": "disabled"}}
$ docker exec ops12probe curl -s http://localhost:8000/health/
{"version": 1, "status": "ready", "checks": {"database": "ok", "cache": "ok", "bot": "disabled"}}

$ docker exec ops12probe curl -s http://localhost:8000/metrics \
    | grep duration_seconds_bucket | awk '{print $1}' | sort -u
django_http_requests_latency_including_middlewares_seconds_bucket{le="0.01"}
django_http_requests_latency_including_middlewares_seconds_bucket{le="0.025"}
django_http_requests_latency_including_middlewares_seconds_bucket{le="0.05"}
django_http_requests_latency_including_middlewares_seconds_bucket{le="0.075"}
django_http_requests_latency_including_middlewares_seconds_bucket{le="0.1"}
django_http_requests_latency_including_middlewares_seconds_bucket{le="0.25"}
django_http_requests_latency_including_middlewares_seconds_bucket{le="0.5"}
django_http_requests_latency_including_middlewares_seconds_bucket{le="0.75"}
django_http_requests_latency_including_middlewares_seconds_bucket{le="1.0"}
django_http_requests_latency_including_middlewares_seconds_bucket{le="2.5"}
django_http_requests_latency_including_middlewares_seconds_bucket{le="5.0"}
django_http_requests_latency_including_middlewares_seconds_bucket{le="7.5"}
django_http_requests_latency_including_middlewares_seconds_bucket{le="10.0"}
django_http_requests_latency_including_middlewares_seconds_bucket{le="25.0"}
django_http_requests_latency_including_middlewares_seconds_bucket{le="50.0"}
django_http_requests_latency_including_middlewares_seconds_bucket{le="75.0"}
django_http_requests_latency_including_middlewares_seconds_bucket{le="+Inf"}
django_http_requests_latency_seconds_by_view_method_bucket{le="0.01",method="GET",view="prometheus-django-metrics"}
...
$ docker rm -f ops12probe   # scratch container removed
```

*(Supports OPS-003 — no `le="2.000"` bucket exists, no
`django_http_response_duration_seconds` family exists, and the label is
`view`/`method`, not `handler`; and OPS-010 — the readiness probe reports
`bot: disabled` in a production-shaped configuration.)*

### Appendix B — `django_prometheus` default latency buckets (source of the missing `le="2.000"` edge)

```text
$ docker run --rm --entrypoint cat mko-bazuna-test-web:latest \
    /opt/venv/lib/python3.14/site-packages/django_prometheus/conf/__init__.py
PROMETHEUS_LATENCY_BUCKETS = (
    0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0,
    2.5, 5.0, 7.5, 10.0, 25.0, 50.0, 75.0, float("inf"),
)
if settings.configured:
    NAMESPACE = getattr(settings, "PROMETHEUS_METRIC_NAMESPACE", NAMESPACE)
    PROMETHEUS_LATENCY_BUCKETS = getattr(settings, "PROMETHEUS_LATENCY_BUCKETS", PROMETHEUS_LATENCY_BUCKETS)
```

*(No `PROMETHEUS_LATENCY_BUCKETS` override exists in `pyproject.toml` or
`config/settings/*.py`. The bucket edges either side of the 2 s SLO are 1.0 and
2.5, so the `le="2.000"` selector in `prometheus-slo-alerts.yaml` can never
match — independently of the metric-name error.)*

### Appendix C — Ops runbooks: `docker compose` invocations that abort without `--env-file`

```text
docs/ops/restore.md:33   docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile backup up -d
docs/ops/restore.md:71   docker compose ps db
docs/ops/restore.md:77   docker compose stop web bot
docs/ops/restore.md:91   export POSTGRES_USER=$(grep POSTGRES_USER .env.dev | cut -d= -f2)   <-- wrong env file
docs/ops/restore.md:95   docker compose exec -T db pg_restore \
docs/ops/restore.md:106  docker compose exec -T db pg_restore \
docs/ops/restore.md:125  docker compose start web bot
docs/ops/restore.md:131  docker compose exec web python -c "import django; django.setup(); ..."
docs/ops/restore.md:137  docker compose run --rm migrate
docs/ops/rollback.md:332 timeout 90 bash -c 'while ! docker compose exec -T web curl -sf .../health/ready/ ...'
docs/ops/rollback.md:335 docker compose exec -T web curl -s .../health/ready/ | python -m json.tool
docs/ops/rollback.md:441-450  (health-validation table: docker compose exec -T web curl / docker compose ps)
docs/ops/rollback.md:555 PREVIOUS_IMAGE_TAG=$(docker compose images --format '{{.Tag}}' web | head -1)
docs/ops/rollback.md:570,590,595,604  (automated rollback block, transcribed from deploy.yml)
docs/ops/migration-workflow.md:200,203,276,278,437,443,455,469,482,495
docs/ops/postgres-18-docker-volume-migration.md:80,83,187,190,205,208,214,222,225,228
```

*(The `rollback.md:555-604` block is the manual transcription of `deploy.yml`,
so it shares `deploy.yml`'s missing `--env-file` as well as its missing
`--profile` — see OPS-005, OPS-006, OPS-007.)*

### Appendix D — Methodology note: what was NOT executed, and why

```text
1. GitHub Actions were not run. The findings about the pipeline are established by
   static reading of the workflow files plus local reproduction of the exact commands
   those workflows execute (bandit, gitleaks config, compose interpolation, pg_dump
   round trip). Whether a given run is currently green/red on github.com was not
   observed; only what the workflow *specifies* was verified.

2. The ops regression-guard test files (test_compose_hardening.py, test_ci_security.py,
   test_docs_ci_parity.py, test_restore_test_workflow.py, test_deploy_workflow.py,
   test_observability.py, test_nginx_config.py) were NOT executed. The `test` compose
   service bind-mounts the repository at /app (docker-compose.test.yml:89); a bare
   `docker run` of the same image without that mount fails 53 of these tests with
   FileNotFoundError because the runtime image ships no Makefile, docker-compose*.yml,
   .github/ or docs/. Two other agents had the `test` service occupied at the time, so
   the correct invocation was not run and their pass/fail status is unverified.

3. The shared dev stack (mko-bazuna-dev web/bot) was left untouched; it is
   crash-looping on a placeholder BOT_TOKEN in .env.dev (Phase 02, CFG-006) and
   repairing it is outside this phase's scope. All runtime evidence above was gathered
   from the already-built mko-bazuna-test-* images and the mko-bazuna-test PostgreSQL
   instance, which is read-only-compatible for every check performed.

4. gitleaks/pre-commit are not installed on this host. No claim in this report rests on
   a gitleaks scan having been executed here; OPS-017 is based on reading the workflow
   step and the .pre-commit-config.yaml / .gitleaks.toml files.

5. No real secret value was read, printed or quoted. The working-tree .env.prod was
   inspected for key NAMES only (the set of variable names it defines), to establish
   which template keys it omits. All other secret-bearing evidence is referenced by
   file:line and variable name.
```
