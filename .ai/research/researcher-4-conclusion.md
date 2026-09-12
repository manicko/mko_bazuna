---
title: Researcher 4 Conclusion — Audit Phase Coverage Evaluation
date: 2026-09-12
source: Researcher 4 (replacement for aborted output)
confidence: VERIFIED against source code + official Django docs + Context7
---

# Researcher 4 Conclusion — Audit Phase Coverage Evaluation

## Verdict: YES — 3 new phases needed (12, 13, 14)

The existing 11 phases comprehensively cover **application architecture and logic**
but are entirely absent from **production operational** domains. Three genuinely
uncovered domains require new audit phases:

| New # | Phase | Domain |
|---|---|---|
| 12 | Production Operations, Security & Observability | Container runtime hardening, health-check contracts, backup/DR, CI/CD pipeline security, supply-chain scanning, production logging/error-tracking, metrics/SLOs, deployment/rollback safety |
| 13 | Performance & Scalability | SLOs with error budgets, caching strategy & cache-key locale segmentation, connection-pooling strategy, query profiling discipline, load/stress testing |
| 14 | Internationalization & Localization Correctness | Runtime locale resolution, fallback-chain correctness, per-user language binding in bot notifications, DB-based i18n + cache locale segmentation, completeness beyond the CI test gate, title tags, hreflang, plurals, RTL/Bidi |

---

## Domain-by-Domain Coverage Check Against 11 Phases

Every modern production-readiness audit domain evaluated against the existing 11:

| Domain | Covered? | Where | Evidence |
|---|---|---|---|
| Dependency & supply-chain scanning | **NO** | — | No `pip-audit`, `Trivy`, `gitleaks`, `Dependabot`, or `SBOM` in `.github/workflows/ci.yml`. No `.github/dependabot.yml` exists. |
| Container runtime hardening | **NO** | — | `docker-compose.prod.yml` has zero `security_opt`, `cap_drop`, `read_only`, `tmpfs`, `user:` overrides. Only `USER app` in `Dockerfile`. |
| Django `check --deploy` gate | **NO** | — | `ci.yml` runs build, test, lint, typecheck, lint-templates, i18n — **never** `manage.py check --deploy`. |
| Health-check / readiness contract | **PARTIAL** (Ph 01) | Phase 01 mentions "process isolation" at architectural level | `/health/` exists at `apps/core/views.py:41` (DB-only `SELECT 1`). Bot has `healthcheck-bot.sh`. But: single combined endpoint (no liveness/readiness separation), no Redis probe, no bounded alert thresholds — all under-covered. |
| Backup & DR | **NO** | — | `docker-compose.yml` has an opt-in backup service (`profiles: ["backup"]`) with 7-day retention `pg_dump`. `docs/ops/restore.md` exists. But: **no RPO/RTO definition**, **no restore-test cadence in CI**, no WAL archiving, no S3/media backup strategy. |
| Production logging & error tracking | **NO** | Phase 10 is code-level only | `LOGGING` defined **only** in `dev.py:16-28`; absent from `base.py` and `prod.py`. No `sentry-sdk` in `pyproject.toml`. No structured logging (`structlog` not present). Phase 10 only enforces `getLogger` vs `print()`. |
| Metrics, SLOs, error budgets | **NO** | — | No `/metrics` endpoint; no `prometheus_client`; no SLO/SLI definitions anywhere in the codebase or docs. |
| Deployment strategy & rollback | **NO** | — | No deploy workflow; no blue/green or rolling-update script. Only image-tag rollback via `docker compose`. |
| Performance / caching strategy | **NO** | Phase 03 (concurrency only), Phase 08 (FTS mechanism) | No SLOs with error budgets. Cache invalidation exists (Redis `delete_pattern` calls) but no cache-key locale-segmentation audit. No `EXPLAIN ANALYZE` profiling discipline. No load/stress testing. |
| i18n runtime correctness | **PARTIAL** (Ph 11) | Phase 11 test coverage | CI has `test_i18n_completeness.py` (4 tests: no-hardcoded-text, extraction completeness, no-empty-msgstr, mo-compiled) — but **no runtime audit** of locale-priority resolution, fallback-chain correctness, `<title>` translation, `hreflang`, plural forms, locale switching, or RTL/Bidi. |

---

## Verification of Prior Gap-Analysis Claims (G1–G8)

### Claims that are **accurate and still valid**:

| Gap ID | Claim | Verification Result |
|---|---|---|
| G1 | No pip-audit, Trivy, gitleaks, Dependabot, SBOM in CI | **CONFIRMED** — `ci.yml` has 6 jobs (build, test, lint, typecheck, lint-templates, i18n); zero security scanning. No `.github/dependabot.yml` exists. |
| G2 | No container hardening in `docker-compose.prod.yml` | **CONFIRMED** — no `security_opt`, `cap_drop`, `read_only`, `tmpfs`, `user:` overrides. Dockerfile has `USER app` only. |
| G3 | No `manage.py check --deploy` in CI | **CONFIRMED** — not in any workflow file. |
| G3 | `CSRF_TRUSTED_ORIGINS` missing | **CONFIRMED** — not in `base.py`, `prod.py`, or `dev.py`. This triggers Django's W004 deployment check warning. |
| G4 | `LOGGING` only in dev.py | **CONFIRMED** — defined at `dev.py:16-28`; absent from `base.py` and `prod.py`. |
| G4 | No Sentry/error-tracking SDK | **CONFIRMED** — `sentry-sdk` absent from `pyproject.toml` dependencies (both `[project]` and `[dependency-groups.dev]`). |
| G4 | No `/metrics` endpoint | **CONFIRMED** — no `prometheus_client`, no metrics URL in `config/urls.py`. |
| G5 | No i18n audit phase for title tags, hreflang, plurals | **CONFIRMED** — `test_i18n_completeness.py` has 4 narrow tests; no runtime checks for `<title>`, `hreflang`, or plural-form correctness. |

### Claims that are **false, stale, or outdated** (the codebase evolved):

| Gap ID | Claim | Verification Result | Source of staleness |
|---|---|---|---|
| G4 | "No health-check endpoint" | **FALSE** — `/health/` exists at `apps/core/views.py:41` with DB connectivity check. Dockerfile `HEALTHCHECK` (line 158) curls it. Bot has `healthcheck-bot.sh`. | Gap analysis conflated "no endpoint" with "no `/healthz`/`/readyz` separation" — the real gap is the *separation*, not the *existence*. |
| G7 | "No check for ad state transition guards" | **FALSE** — `Ad.transition_to()` at `apps/ads/models.py:352-485` enforces a validated transition matrix with `refresh_from_db()` anti-stale-state. Five `CheckConstraint`s enforce timestamp/status consistency. | Gap analysis was written before the state-machine method was implemented. |
| G7 | "No concurrent edit protection on Ad rows" | **MIXED** — `select_for_update()` IS used in moderation views (`moderation/views/review.py:78,125`). `transition_to()` calls `refresh_from_db()` (line 403) to defeat stale-state races. No version/timestamp-based optimistic locking, but the race-prevention pattern exists. | Gap analysis predated `select_for_update` usage and the `transition_to` method. |
| G8 | "Bot uses raw aiogram types; no Pydantic validation" | **FALSE** — Pydantic v2 schemas exist at `src/telegram_bot/schemas/message_payloads.py` (`TitlePayload`, `DescriptionPayload`, `PricePayload`, `PhotoCountPayload`) and `src/telegram_bot/schemas/saved_search.py` (`SavedSearchQueryPayload`, `SavedSearchPricePayload`). Rule #11 is satisfied. | Gap analysis was written before the Pydantic schema layer was introduced. |
| G3 | `SECURE_CONTENT_TYPE_NOSNIFF` missing | **MISLEADING** — This setting defaults to `True` since Django 3.0 and `SecurityMiddleware` (in `MIDDLEWARE` at `base.py:130`) sets the `X-Content-Type-Options: nosniff` header. nginx also sets it (`nginx.conf:43`). Not a gap. | Gap analysis listed it as a missing setting without checking Django's default or the nginx config. |
| G3 | `SECURE_BROWSER_XSS_FILTER` missing | **STALE/OBSOLETE** — This setting was deprecated in Django 5.0 and **removed** in Django 5.2 (the project targets `>=5.2.16`). `X-XSS-Protection` is an obsolete header (`django/docs/releases/4.0.txt`). Security is handled via CSP-Report-Only in nginx (`nginx.conf:53`). | Gap analysis referenced a setting that no longer exists in the target Django version. |

### Claims that are **partially accurate but mis-scoped**:

| Gap ID | Claim | Corrected Assessment |
|---|---|---|
| G5 | "No backup/DR" | Backup service **exists** in `docker-compose.yml:71-101` (opt-in via `profiles: ["backup"]`, 7-day retention, `pg_dump -F c`). `docs/ops/restore.md` documents the restore runbook. But RPO/RTO are undefined, no restore-test cadence, no WAL archiving, and media files are NOT backed up to object storage. |
| G7 | "No soft-delete consistency" | `User` model has `is_deleted` boolean (`users/models.py:54`), enforced via `soft_delete_user_ads` service (`users/services/deletion.py:165`) inside `transaction.atomic()`. However, the `Ad` model uses `deleted_at` timestamp + `DELETED` status rather than an `is_deleted` field, and no custom manager filtering `status != DELETED` was found on the `Ad` model. The soft-delete pattern exists but is only partially applied. |

### CI/CD plan reference (Researcher 2's source):
Researcher 2 cited `.ai/plans/ci_cd/plan.md_updated.md` as evidence. **This file does not exist** in the repository (`glob` for `.ai/**/ci_cd*` returned no results). The `/.ai/plans/` directory contains only `docs/97-plans/` subdirectories. Researcher 2's reference is therefore unverified — the document may have been a proposal that was never created.

---

## Evaluation of Prior Research Finders

| Researcher | Finding | Assessment |
|---|---|---|
| **Researcher 1** (3 phases) | 3 new phases: Production Ops/Security/Observability, Performance & Scalability, i18n | **CORRECT** — all three domains are genuinely uncovered. The staleness corrections (health endpoint exists, state transitions exist, Pydantic schemas exist) are accurate. The 3-phase granularity matches the project's SRP/small-module philosophy. The 3 phase template files already drafted at `.ai/audit/problems/{12,13,14}-audit-*.md` are well-structured and architecture-agnostic. |
| **Researcher 2** (6 phases) | 6 new phases: dependency security, container hardening, observability, backup/DR, i18n, business logic | **PARTIALLY STALE** — G7 (business logic) and G8 (bot input validation) are false: both are already implemented (`transition_to()` and Pydantic schemas). The 6-phase split over-fragments concerns the Phase 12 template already consolidates (container hardening + CI/CD security + observability + supply-chain). 6 phases would violate "avoid overengineering." |
| **Researcher 3** (1 phase) | 1 consolidated phase: Production Operations & Observability | **UNDER-COUNTS** — correctly identifies the ops/observability/security gap, but consolidates three distinct domains (operations, performance, i18n) into one phase. This violates the project's "single responsibility" rule — i18n correctness has different evidence types (rendered HTML, cache keys, locale headers), different toolchains, and different owners than ops hardening. The 3-phase split is better aligned with the project philosophy. |
| **Researcher 4** (prior) | Aborted — no output | This conclusion replaces it. |

---

## Why 3 Phases (Not 1, Not 6, Not 7)

**Not 1 (Researcher 3's consolidation):** The three domains have non-overlapping evidence, toolchains, and ownership:
- **Phase 12 (Operations):** config dumps, HTTP responses, CI job traces, Docker manifest inspection, `check --deploy` output
- **Phase 13 (Performance):** `EXPLAIN ANALYZE` output, cache-key inspection, load-test results, timing measurements
- **Phase 14 (i18n):** rendered HTML, HTTP headers, cache keys per locale, notification text per user language

Conflating them into one phase makes each audit run unfocused and harder to maintain.

**Not 6–7 (Researcher 2 / gap-analysis):** The granular split fragments concerns that share implementation touchpoints (`Dockerfile`, `docker-compose.prod.yml`, `ci.yml`, `prod.py`). Dependency scanning, container hardening, and CI/CD security all audit the same files and can be verified in a single pass. The gap analysis also includes G7 and G8 phases that are **already addressed** in the codebase — adding phases for solved problems adds maintenance debt without value.

**3 phases (Researcher 1):** Each phase owns one responsibility, has distinct evidence types, and maps to existing partial work:
- Phase 12 subsumes G1 (deps), G2 (container), G3 (deployment check), G4 (logging/metrics), G5 (backup/DR), and the observability gap from the prior G4
- Phase 13 covers the performance/scalability gap (SLOs, caching, pooling, profiling, load testing)
- Phase 14 covers the i18n correctness gap (runtime locale behavior + gate breadth)

G7 (business logic integrity) and G8 (bot input validation) are **already covered** by existing phases:
- G7 → Phase 05 (Ad lifecycle, state machine) + Phase 03 (transaction atomicity, `refresh_from_db` race defense)
- G8 → Phase 02 (boundary DTOs via Pydantic v2) + Phase 05 (bot FSM-as-DRAFT persistence)

The three `.ai/audit/problems/` phase template files (12, 13, 14) already drafted at this path are correct, well-structured, and should be adopted as the final phase definitions with no structural changes needed.

---

## Summary Table: Prior Gap Analysis vs. Current Reality

| Gap | Prior claim | Current code reality | Gap still valid? |
|---|---|---|---|
| G1 — Dependency security | No scanning in CI | CI has no pip-audit/Trivy/gitleaks/Dependabot | **YES** — assign to Phase 12 |
| G2 — Container hardening | No runtime hardening | No `cap_drop`/`read_only`/`tmpfs`/`security_opt` in compose | **YES** — assign to Phase 12 |
| G3 — Django deploy checklist | No `check --deploy`, missing CSRF_TRUSTED_ORIGINS, missing nosniff/xss-filter | No `check --deploy` in CI; `CSRF_TRUSTED_ORIGINS` absent; `SECURE_CONTENT_TYPE_NOSNIFF` defaults True; `SECURE_BROWSER_XSS_FILTER` removed in Django 5.2 | **PARTIAL** — CSRF_TRUSTED_ORIGINS + no `check --deploy` are real; nosniff/xss-filter claims are stale |
| G4 — Observability | No health endpoint, no LOGGING in prod, no Sentry/metrics | `/health/` exists (DB-only, no liveness/readiness split); LOGGING only in dev; no Sentry/metrics | **YES** (weakened) — health endpoint exists but split is missing; logging/metrics are real gaps |
| G5 — Backup/DR | No backup/DR audit | Backup service exists (opt-in, 7-day retention); restore docs exist; no RPO/RTO, no restore-test | **YES** — procedure exists but no audit/validation of it |
| G6 — i18n compliance | No i18n audit beyond test gate | CI gate is narrow (4 tests); no runtime/locale-correctness audit | **YES** — assign to Phase 14 |
| G7 — Business logic integrity | No state transition guards, no soft-delete, no concurrency protection | `Ad.transition_to()` with validated matrix exists; `select_for_update` in moderation; soft-delete on User via `is_deleted` | **NO** — already addressed by Phase 03 + Phase 05 |
| G8 — Bot input validation | No Pydantic at bot boundary | Pydantic v2 schemas exist (`message_payloads.py`, `saved_search.py`) | **NO** — already addressed by Phase 02 + Phase 05 |

---

## Recommendation

**Adopt 3 new audit phases (12–14)** as already drafted in `.ai/audit/problems/`:

1. **Phase 12 — Production Operations, Security & Observability**
   - Absorbs gaps G1, G2, G3 (real portions), G4 (logging/metrics portion), G5, and the observability gap from G4
   - Finding prefix: `OPS-`

2. **Phase 13 — Performance & Scalability**
   - Covers SLOs, caching strategy, connection pooling, query profiling, load testing
   - Finding prefix: `PERF-`

3. **Phase 14 — Internationalization & Localization Correctness**
   - Absorbs gap G6 (extended to runtime correctness)
   - Finding prefix: `I18N-`

**Do NOT add phases for G7 or G8** — these are already covered by existing Phase 03 + Phase 05 (G7) and Phase 02 + Phase 05 (G8). The prior gap analysis was written against an earlier state of the codebase that has since implemented the state machine (`transition_to`) and the Pydantic schema layer.

**The current 11 phases are not sufficient** — 3 new phases are required to close the production operational gap.
