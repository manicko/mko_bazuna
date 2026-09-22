# 12 — Production Operations, Security & Observability

> Audit phase. LLM-auditor instruction. Architecture-agnostic: described via
> ARCHITECTURAL LAYERS, ZONES OF RESPONSIBILITY, KEY RISKS, GOALS. NOT tied to
> specific files, modules, or functions. Must stay valid if the architecture changes.
>
> **Output mode:** `problems-only` — report only findings; do not narrate a clean bill of health.

## 1. Goal

Verify that the production deployment is hardened, observable, and recoverable:
container runtime hardening (CIS Docker Benchmark baseline), a health-check /
readiness contract with alert thresholds, backup & disaster-recovery with defined
RPO/RTO and restore-test cadence, CI/CD pipeline security (deployment readiness
check, dependency/secret scanning, SAST), supply-chain integrity (SBOM, pip-audit,
Trivy, Dependabot), production logging & error tracking (no dev-only LOGGING),
metrics & SLOs, and deployment/rollback safety (blue/green or rolling updates).

## 2. System Under Audit (layers & zones)

| Zone | Concern |
|------|---------|
| **Container Runtime** | The container images run a non-root runtime user; the orchestration manifest declares the runtime-hardening directives (cap_drop, read_only, tmpfs, no-new-privileges, security_opt, mem_limit/cpus). |
| **Health Contract** | A liveness/readiness endpoint probes internal dependencies (DB, shared cache, bot marker freshness). Orchestration uses readiness to drain traffic and liveness to restart; alert thresholds are bounded (not `start_period`-only). |
| **Backup & DR** | A scheduled backup job produces consistent dumps with retained history. RPO and RTO are defined; restore is exercised on a cadence (not assumed from `pg_dump` output alone). |
| **CI/CD Pipeline** | The CI workflow runs Django's deployment check (`manage.py check --deploy`), dependency scanning, secret scanning, and SAST; a deployment workflow performs rolling/blue-green updates with rollback. |
| **Supply Chain** | The dependency lockfile is scanned; an SBOM (CycloneDX) is produced; automated update PRs are configured (Dependabot or equivalent). |
| **Production Logging / Error Tracking** | The production settings define a structured LOGGING configuration; an error-tracking SDK captures unhandled exceptions; no raw secrets in log output. |
| **Metrics & SLOs** | A metrics endpoint exposes application-level SLIs; SLOs with error budgets are defined and alert on burn-down, not on a single threshold. |
| **Deployment & Rollback** | Deployments are incremental (rolling/blue-green); rollback reverts the image+config atomically; no image-only rollback leaves data in a half-applied state. |

## 3. Prerequisites

- Access to the production compose manifest and the runtime image definition.
- Access to the CI workflow definitions and the dependency lockfile.
- Ability to run `manage.py check --deploy` against production-equivalent settings.
- Ability to curl the health endpoint and inspect container runtime directives.
- A staging or test stack where a restore-test can be executed end-to-end.
- Linter and type-checker available (pipeline gates).

## 4. Runtime Verification (mandatory)

Execute, then capture evidence (config dumps, HTTP responses, command output, grep hits):

1. **Deployment check** — run `manage.py check --deploy` against production settings → assert zero warnings/errors at `--fail-level WARNING` (W004 CSRF_TRUSTED_ORIGINS, missing security flags must not appear). The CI `deploy-check` job executes this against `config.settings.prod`.
2. **Container hardening** — assert `USER app` (non-root) in the runtime image; assert `cap_drop: ["ALL"]`, `read_only: true`, `tmpfs`, `no-new-privileges`, `mem_limit`/`cpus` on every long-lived service in the production manifest. Regression guard: `test_compose_hardening.py`.
3. **Health contract** — assert a distinct liveness path (zero DB/cache dependency) and a distinct readiness path (probes DB + cache + bot-marker freshness); curl liveness under DB-down/cache-down → 200; curl readiness under DB-down/cache-down → 503; assert each container `HEALTHCHECK` points to the liveness path (not readiness). Regression guard: `test_health_contract.py`.
4. **Backup & DR** — assert a backup job (`pg_dump -F c`, daily, ≥7-day retention) exists; assert a restore-test is scheduled (cron + manual dispatch) and runs `migrate --plan --check` against an isolated target; assert RPO and RTO are documented. Regression guard: `restore-test.yml` + `restore.md`.
5. **CI/CD security** — enumerate CI jobs; assert a `security` job (pip-audit + Trivy + gitleaks) and a `deploy-check` job (`check --deploy --fail-level WARNING` against production settings) exist; assert a `deploy` workflow exists. **SAST is explicitly expected but currently absent** (no bandit/semgrep step) — see §8; this negative assertion is a live gap.
6. **Supply chain** — grep for pip-audit (CI security job), Trivy image + fs scans (CI build + security), a CycloneDX SBOM produced at image build, and a `.github/dependabot.yml` → assert all present. Regression guard: `test_ci_security.py`.
7. **Production logging** — inspect production settings for a structured `LOGGING` config (JSON, redacting formatter) and a Sentry/error-tracking SDK init guarded on its DSN; assert the SDK is a production dependency, not dev-only. Regression guard: `test_prod_logging.py`.
8. **Metrics / SLOs** — probe `/metrics` → 200 with Prometheus exposition; assert the metrics middleware is wired (`django-prometheus` in `INSTALLED_APPS`/`MIDDLEWARE`) and the route is registered; assert SLO/SLI/error-budget definitions exist (SLO constants, grafana dashboard, prometheus burn-rate alerts) and a CI gate fails on SLO regression. Regression guard: `test_observability.py`.
9. **Deployment strategy** — enumerate the deploy workflow; assert it performs an incremental rollout (rolling/blue-green) with a health-check gate, and that a rollback runbook (covering image + config + schema dimensions) exists with health-gated validation. Regression guard: `rollback.md`.

## 5. Audit Dimensions (checks + evidence)

### (a) Container runtime hardening — CRITICAL
The production manifest declares CIS-Docker-Benchmark runtime controls and the image is non-root.
- Evidence: manifest contains `no-new-privileges` / `security_opt`, `cap_drop`, `read_only: true`, `tmpfs` on `/tmp`; image defines a non-root `USER` directive. Absence of any hardening directive beyond `USER app` in the Dockerfile is a finding.

### (b) Health-check / readiness contract & alert thresholds — HIGH
A distinct readiness probe exists, the bot liveness marker freshness is verified, and alert thresholds are bounded rather than `start_period`-only.
- Evidence: two health endpoints (or query-param distinction) for liveness vs readiness; health job probes DB + cache + bot marker; alert threshold includes a concrete upper-bound (e.g. `start_period` is not the only parameter). A single `/health/` endpoint doing `SELECT 1` with only `--start-period` is a finding.

### (c) Backup, RPO/RTO & restore-test cadence — HIGH
RPO and RTO are explicitly defined; restore is exercised on a schedule, not merely assumed from backup existence.
- Evidence: documented RPO/RTO; a cron/scheduler job that performs a restore-test on N-day cadence. A backup job with `pg_dump` + 7-day retention and NO restore-test is a finding.

### (d) CI/CD pipeline security — CRITICAL
CI runs Django's deployment check and gates on dependency scanning, secret scanning, and SAST; a deployment workflow performs safe rollouts.
- Evidence: CI steps invoking `manage.py check --deploy`; a dedicated security job (pip-audit / Trivy / secret-scan); a deploy job. CI enumerating only build, test, lint, typecheck, lint-templates, i18n with NO security/deploy job is a finding.

### (e) Supply-chain integrity — HIGH
The dependency surface is scanned and an SBOM is produced; updates are automated.
- Evidence: pip-audit / Trivy scan in CI; CycloneDX SBOM artifact; Dependabot or equivalent auto-update config. Absence of all of these is a finding.

### (f) Production logging & error tracking — CRITICAL
Production settings define a structured LOGGING configuration and an error-tracking SDK; no raw secrets appear in logs.
- Evidence: `LOGGING` dict present in production settings (not only dev); Sentry/error-tracking SDK in dependencies (not only in dev). `LOGGING` defined ONLY in dev settings and absent from base/prod, with no error-tracking SDK, is a finding.

### (g) Metrics, SLOs & error budgets — HIGH
Application-level SLIs are exposed and SLOs with error budgets are defined and alerted on.
- Evidence: `/metrics` endpoint or SDK emitting counters; SLO/error-budget dashboard; alert on burn-down. Absence of any metrics endpoint, SLO definition, or error-tracking SDK is a finding.

### (h) Deployment & rollback safety — HIGH
Rollouts are incremental (rolling or blue/green); rollback is atomic.
- Evidence: a deploy workflow implementing rolling/blue-green updates; rollback reverts image+config together. Only an image-tag rollback with no incremental rollout strategy is a finding.

## 6. Cross-Cutting (owned here, not duplicated)

This phase owns the **production operations, security posture, and observability stack**. It explicitly does NOT audit:

- **Phase 01 (entry/bootstrap, migration-once)** owns bootstrap ordering, the
  migration-once advisory-lock coordination, and the async↔sync boundary (the
  aiogram bot transport ↔ the shared Django ORM). Phase 01 does NOT own
  container runtime hardening, the health/readiness contract, or rollback
  mechanics — those are owned here (§2 Container Runtime, Health Contract,
  Deployment & Rollback; verified by the §4 positive presence checks). Phase 01's
  adjacent, cross-cutting concerns are *restart-policy expectations* (crash →
  restart, no duplicate migration, boot-fails-fast-on-missing-secrets) and the
  *process* restart contract ("DB-down-after-boot → exit/restart; no stuck
  threads"). That process contract is the distinct layer beneath this phase's
  **container** liveness contract (`HEALTHCHECK → /health/live/`); it governs
  process isolation/restart but does not extend into hardening directives, the
  readiness endpoint, or rollback mechanics. No overlap.
- **Phase 02 (secrets storage at the settings/config-loading layer)** — pipeline secret-scanning or supply-chain scanning. Phase 02 owns where secrets are read at runtime; this phase owns whether the pipeline scans for leaked/expired secrets.
- **Phase 09 (TLS/headers at the proxy, external-integration egress)** — reverse-proxy header hardening. Phase 09 owns proxy-level TLS and egress-resilience; this phase owns container-level hardening, CI pipeline scanning, and the observability stack. (Note: `SECURE_CONTENT_TYPE_NOSNIFF` / `SECURE_BROWSER_XSS_FILTER` / `CSRF_TRUSTED_ORIGINS` are Django-level deployment-check W-series findings — surfaced here because `check --deploy` is a pipeline/deployment concern owned by this phase, not by Phase 09's proxy-header zone.)
- **Phase 10 (code-level logging: no-`print` rule)** — the `print()` prohibition. Phase 10 owns source-level logging hygiene; this phase owns the production LOGGING configuration and error-tracking infrastructure.

## 7. Edge Cases

- Health endpoint returns 200 while the bot marker is stale (process alive, updates blocked) → must be caught by readiness, not liveness.
- `manage.py check --deploy` passes in CI but prod settings omit `CSRF_TRUSTED_ORIGINS` (W004) → deployment-check gate must run against prod settings.
- Backup job runs `pg_dump` while a write transaction is open → consistency not guaranteed without `--no-sync`/lock hints.
- Restore-test restores to the same DB volume → destructive; must use an isolated restore target.
- Dependency scanning is added but `check --deploy` is not → deployment-check gap remains.
- Sentry DSN present in dev settings but absent at runtime via env → error tracking silently degraded in prod.
- Alert threshold = `start_period` only → restart loops masked during deploy.
- Rolling update swaps one container while the shared ORM still holds connections to the previous pod → connection-draining contract required.

## 8. Severity Taxonomy

- **CRITICAL**
  - Container runs as root, or the manifest omits `no-new-privileges`/`cap_drop`/`read_only`. → **RESOLVED** — non-root runtime user + CIS directives on all long-lived services; see §4.2.
  - CI does NOT run `manage.py check --deploy` and a known W-series finding (W004, nosniff flags) ships to production. → **RESOLVED** — `deploy-check` runs `manage.py check --deploy --fail-level WARNING` against production settings; see §4.5.
  - No dependency/secret scanning or SAST in CI. **Split** (scanning limb satisfied; SAST is the live gap):
    - Dependency/secret scanning absent (Trivy image + fs, gitleaks, pip-audit). → **RESOLVED** — a blocking `security` job scans dependencies, image, filesystem, and secrets; see §4.5 / §4.6.
    - SAST absent (no bandit/semgrep step; ruff `S` rules not selected; no SAST tool in dev dependencies). → **OPEN** — the single live gap; no regression guard exists yet; see §4.5 and §5(d).
  - Production settings lack a `LOGGING` configuration and no error-tracking SDK is present. → **RESOLVED** — structured production `LOGGING` + an error-tracking SDK init guarded on its DSN, present as a production dependency; see §4.7.
  - Unauthenticated/health endpoint serves as both liveness and readiness with `start_period`-only alerting. → **RESOLVED** — distinct liveness (zero DB/cache dependency) and distinct readiness (DB + cache + bot-marker freshness) with bounded alert thresholds; see §4.3.
  - No deployment workflow; only image-tag rollback with no incremental rollout. → **RESOLVED** — a `deploy` workflow performs an incremental (recreate) rollout with a health-check gate; a rollback runbook covers image + config + schema dimensions with health-gated validation; see §4.9.
- **HIGH**
  - No restore-test cadence; RPO/RTO undefined.
  - No supply-chain scanning (pip-audit/Trivy) and no SBOM/Dependabot.
  - No `/metrics` endpoint and no SLO/error-budget definitions.
  - Backup job lacks consistency guarantees (no lock/`--no-sync`).
  - Secrets present in container env without a rotation procedure.
- **MEDIUM**
  - Health endpoint lacks bot-marker-freshness verification.
  - Sentry log-level too noisy or DSN misconfigured at runtime.
  - SBOM produced but not verified against the lockfile.
  - SLOs defined but alerts fire only on single-threshold, not burn-down.
- **LOW**
  - Missing health endpoint versioning.
  - No documented rollback runbook.
  - Healthcheck `start_period` exceeds 60s (too long).

## 9. Recommended Sequence

1. Discovery — map the container runtime, health endpoint, backup/DR, CI jobs, supply-chain, logging, metrics, and deployment strategy.
2. Runtime verification (§4).
3. Per-dimension checks (§5 a–h).
4. Cross-cutting (§6) and edge cases (§7).
5. Consolidate findings.

## 10. Finding Prefix

Use `OPS-` for all findings in this phase.

## 11. Reporting

- `problems-only: true`.
- Each finding: severity, zone, evidence (config dump / HTTP response / command output / grep hit), and recommendation with effort/priority.
- Append incrementally (≤100 lines per write) to the phase findings file per `docs/99-agent/rules.md`.
