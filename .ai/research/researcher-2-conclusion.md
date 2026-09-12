---
title: Audit Phase Coverage — Researcher 2 Conclusion
date: 2026-09-12
source: @researcher agent (this round)
---

# Verdict: YES — 3 new phases needed (12, 13, 14)

## 1. Do the existing 11 phases adequately cover all critical audit domains?

**No.** After mapping every domain a modern production-readiness audit covers — drawn from the Google SRE Production Readiness Review (PRR) framework, the Django deployment checklist, and the CIS Docker Benchmark — **three genuinely uncovered domains** remain after all 11 phases:

| Uncovered Domain | Modern Best-Practice Source | Evidence in Codebase |
|---|---|---|
| **Production Operations, Security & Observability** | Google SRE PRR (instrumentation/monitoring, emergency response, change management, security); Django `check --deploy`; CIS Docker Benchmark v1.8.0; Susan Fowler production-readiness (deployment pipeline, monitoring, fault tolerance) | `prod.py` has no `LOGGING` dict; no Sentry/structlog/Prometheus; `manage.py check --deploy` not in CI; `docker-compose.prod.yml` omits `security_opt`/`cap_drop`/`read_only`/`tmpfs`; no `CSRF_TRUSTED_ORIGINS`; no pip-audit/Trivy/gitleaks/Dependabot; backup exists but no restore-test cadence or RPO/RTO |
| **Performance & Scalability** | Google SRE PRR (capacity planning, performance: availability/latency/efficiency); Susan Fowler (scalable and performant) | No SLOs/error budgets; no load/stress testing in CI; no `/metrics` endpoint; cache-key locale segmentation not validated |
| **i18n & Localization Correctness** | Django i18n docs; project rule #16 | CI gate (`test_i18n_completeness.py`) is narrow (4 tests: no-hardcoded-text, extraction completeness, no-empty-msgstr, mo-compiled); no runtime audit of title tags, hreflang, plural forms, locale switching, fallback-chain correctness, per-user bot language |

Every other domain a modern audit framework would cover IS already addressed by the existing 11 phases:

| Modern PRR / Best-Practice Domain | Covered By Existing Phase |
|---|---|
| System architecture & interservice dependencies | Phase 01 (entry points, async/sync boundary, shared DB, migration orchestration) |
| Authentication & authorization | Phase 04 (login tokens, hash-only storage, constant-time comparison, atomic claim, expiry/replay, session cookies) |
| Data integrity & concurrency | Phase 03 (transaction atomicity, lost-update prevention, advisory-lock safety, cross-process consistency); plus Ad model `transition_to()` + `select_for_update()` |
| Ad lifecycle / moderation | Phase 05 (state machine, bot FSM-as-DRAFT, moderation gate, purge/sweep jobs) |
| PII protection & consent | Phase 06 (DECLINE vs WITHDRAW, 30-day erasure, contact deep-link gating, soft-delete, cross-process consent) |
| Media handling & security | Phase 07 (upload validation, UUID v4 naming, EXIF stripping, retention/sweep) |
| Search / FTS | Phase 08 (PG TSVECTOR+GIN, visibility filtering, ranking/pagination) |
| External integrations | Phase 09 (bot token, translation client, deep-link, TLS/proxy, secrets management) |
| Code quality & standards | Phase 10 (type safety, StrEnum, logging hygiene, Pydantic at boundaries, English-only) |
| Testing & deployment safety | Phase 11 (two-process testing, migration tests, CI gating, determinism) |

The existing 11 phases provide comprehensive coverage of the application's architectural, domain, and code-quality concerns. The three uncovered domains are all **production-operations / runtime-operations** concerns that sit outside the scope of the application-layer phases.

## 2. Existing phases vs. augmentation vs. new

The three uncovered domains are **entirely absent** from the 11 phases, not merely under-emphasized:

- **Phase 10 (Code Quality)** explicitly scopes itself to *source-level* concerns ("no `print()` statements, use `getLogger(__name__)`"). The Phase 12 problem definition confirms this: Phase 10 "owns source-level logging hygiene; this phase [12] owns the production LOGGING configuration and error-tracking infrastructure." No existing phase audits container runtime hardening, CI pipeline security, supply-chain scanning, backup/restore testing, or SLO/error-budget infrastructure.

- **Phase 09 (External Integrations)** covers proxy-level TLS, egress resilience, and translation-client failure handling — not container runtime hardening, CI/CD pipeline safety, or observability infrastructure. The Phase 12 problem definition explicitly reassigns Django `check --deploy` flags (`CSRF_TRUSTED_ORIGINS`, `SECURE_CONTENT_TYPE_NOSNIFF`) to Phase 12 because `check --deploy` is a pipeline/deployment concern, not a proxy-header concern.

- **Phase 08 (Search)** covers the FTS mechanism (index freshness, ranking, recall) — not cache-key locale segmentation or SLOs.

- **Phase 05 (Ad Lifecycle)** covers the ad state machine, moderation gate, and purge/sweep jobs — but the gap analysis's G7 (business logic integrity) claims about missing transition guards are stale (see §3).

No existing phase can be reasonably augmented to cover these without expanding its scope beyond its stated boundary. New phases are required.

## 3. New phases: 3 (not 1, not 6)

**Three phases — not consolidated into one, not split into six.**

The project has already begun this work: `.ai/audit/problems/` contains detailed, architecture-agnostic problem definitions for exactly these three phases (created 2026-09-12, same date as this analysis):

- `12-audit-production-ops.md` — Production Operations, Security & Observability
- `13-audit-performance.md` — Performance & Scalability
- `14-audit-i18n.md` — Internationalization & Localization Correctness

This matches **Researcher 1's** recommendation and the project's own direction. Three phases is the correct granularity for this architecture because:

1. **Distinct evidence types** — Phase 12 produces config dumps/HTTP responses/grep hits; Phase 13 produces timing/query plans/cache-key analysis; Phase 14 produces rendered HTML/locale-switch verification. These require different runtime-verification procedures.

2. **Non-overlapping zones of responsibility** — The Phase 12 problem definition explicitly documents its cross-cutting boundaries (does NOT audit process bootstrap, secrets loading, proxy TLS, code-level logging, or test coverage). Phase 13 owns SLOs/caching/pooling — explicitly excluding FTS mechanism (Phase 08) and DB atomicity (Phase 03). Phase 14 owns runtime i18n correctness — explicitly excluding PII consent (Phase 06), FTS search-vector mechanism (Phase 08), and translation-client egress (Phase 09).

3. **Shares implementation touchpoints within phases but not across** — Phases 12's domains (container hardening, CI/CD security, observability, backup) all converge on `Dockerfile`, `docker-compose.*.yml`, `.github/workflows/*.yml`, and `settings/prod.py`. Phase 13's caching/concurrency/SLO concerns live in `base.py` (`CACHES`, `CONN_MAX_AGE`), search services, and gunicorn config. Phase 14's concerns live in middleware, templates, and Pydantic schemas. These are genuinely different file surfaces.

4. **Project philosophy** — The project's rules state "small modules and functions," "single responsibility," and "avoid overengineering." Three focused phases align with this; one mega-phase (Researcher 3's proposal) would be too broad and dilute focus; six granular phases (Researcher 2's proposal) over-cuts and includes phases for already-solved problems.

**Why not 1 phase (Researcher 3):** Consolidating operations, performance, and i18n into one phase would merge three domains with fundamentally different evidence types, expertise, and remediation paths. A security-scanning finding and an i18n fallback-chain bug have different urgency, different owners, and different verification procedures.

**Why not 6 phases (Researcher 2):** Researcher 2 accepted the gap analysis's stale claims (G7, G8) as real gaps and proposed separate phases for business-logic integrity and bot input validation — domains already addressed by the codebase. Splitting operations (G1, G2, G3, G4, G5) into 4 phases (dependency security, container hardening, observability, backup/DR) fragments concerns that share the same implementation touchpoints without adding audit value.

## 4. Prior research findings — accurate vs. stale

### Gap analysis (`.ai/audit/gap-analysis-new-phases.md`) — 6 of 7 claims accurate, 2 stale

| Finding | Status | Evidence |
|---|---|---|
| G1: No dependency/supply-chain scanning (pip-audit, Trivy, gitleaks, Dependabot, SBOM) | **ACCURATE** | `ci.yml` has 6 jobs (build, test, lint, typecheck, lint-templates, i18n). No security-scan job. `pyproject.toml` has no sentry/structlog/prometheus/trivy/pip-audit/gitleaks/bandit/semgrep dependencies. CI plan Stage D confirms all "TO BE BUILT." |
| G2: No container runtime hardening in compose | **ACCURATE** | `docker-compose.prod.yml` has no `security_opt`, `cap_drop`, `read_only`, `tmpfs`, or `user:` directives for web/bot. Dockerfile has `USER app` (CIS §4.1) but omits read-only rootfs (§5.12), `no-new-privileges` (§2.14/5.25), capability dropping (§5.3), and tmpfs (§5.10). |
| G3: `manage.py check --deploy` not invoked; `CSRF_TRUSTED_ORIGINS` missing; nosniff/XSS-filter missing | **ACCURATE** | No `check --deploy` anywhere in codebase. `prod.py` and `base.py` have no `CSRF_TRUSTED_ORIGINS`. No `SECURE_CONTENT_TYPE_NOSNIFF` or `SECURE_BROWSER_XSS_FILTER`. Only `XFrameOptionsMiddleware` is present (nginx handles X-Frame-Options). |
| G4: No `LOGGING` in prod; no Sentry/metrics/error tracking | **ACCURATE** | `LOGGING` dict exists **only** in `dev.py:16-28`. `base.py` and `prod.py` have no `LOGGING` setting (falls back to Django defaults). No Sentry, no Prometheus, no OTel, no `structlog` in dependencies. Note: `/health/` endpoint exists at `apps/core/views.py:41` (gap analysis was wrong on "no health endpoint"). |
| G5: No restore-test cadence / no RPO/RTO | **ACCURATE** | `docs/ops/restore.md` documents backup (pg_dump, 7-day retention) and restore procedure, but defines no RPO/RTO and mentions "No backup testing in CI" explicitly. No quarterly restore-test schedule. |
| G6: No i18n audit beyond CI test gate | **ACCURATE** | `test_i18n_completeness.py` has 4 narrow tests. No runtime audit phase for title tags, hreflang, plural forms, locale switching, fallback-chain correctness, or RTL/Bidi — all genuine correctness domains beyond the gate. |
| G7: No ad state transition guards / no soft-delete consistency | **STALE** | The Ad model has a complete `transition_to()` method (`models.py:352-485`) with an enforced transition matrix (`ALLOWED_TRANSITIONS` dict at line 384). DB-level CHECK constraints enforce status-timestamp consistency (6 constraints, lines 321-346). `User.is_deleted` (line 54) and `Ad.deleted_at` (line 198) implement soft-delete with CHECK constraints. Concurrency protection via `select_for_update()` is tested in `test_edit_views_locking.py` and `test_transition_concurrency.py`. Owned by Phase 05 (ad lifecycle) + Phase 03 (concurrency). |
| G8: No Pydantic validation at bot boundary | **STALE** | Bot has Pydantic v2 DTOs in `schemas/message_payloads.py` (`TitlePayload`, `DescriptionPayload`, `PricePayload`, `PhotoCountPayload`) and `schemas/saved_search.py` (`SavedSearchQueryPayload`, `SavedSearchPricePayload`). These are actively used in `handlers/ad_create.py` (lines 459, 488, 596, 637). Tests in `test_price_payload.py` verify `ValidationError` on invalid input. Owned by Phase 02 (boundary DTOs) + Phase 05 (ad dialog). |

### Researcher 1 — mostly accurate
- **Correct:** `/health/` endpoint exists (gap analysis was wrong); G7 already owned by Phase 05 + Phase 03; G8 owned by Phase 02 + Phase 05.
- **Correct recommendation:** 3 phases (ops/observability, performance, i18n).
- **Status:** Fully vindicated. The project has already adopted this direction (problem definitions for 12-14 exist).

### Researcher 2 — two stale claims accepted
- **Accurate:** No pip-audit/Trivy/gitleaks in CI; no `LOGGING` in prod.py; no container hardening; no `CSRF_TRUSTED_ORIGINS`.
- **Inaccurate:** Accepted G7 (business logic) and G8 (bot input validation) as real gaps — these are already solved in the codebase.
- **Over-engineering:** Proposed 6 phases when 3 suffice; split operational concerns that share touchpoints; elevated already-solved domains to new phases.

### Researcher 3 — accurate but suboptimal scope
- **Correct:** No `LOGGING` in prod.py, no metrics, no Sentry, no `check --deploy`, no container hardening, single `/health/` (no healthz/readyz distinction).
- **Correct** that these are completely absent from existing phases.
- **Suboptimal recommendation:** 1 consolidated phase merges domains with different evidence types and expertise (operations ≠ performance ≠ i18n correctness). The project's own direction (3 phases) and Researcher 1's analysis support splitting.

## 5. Recommendation

**Adopt 3 new phases (12, 13, 14)** matching the project's existing problem definitions in `.ai/audit/problems/`:

1. **Phase 12 — Production Operations, Security & Observability** (consolidates G1-G5): Container hardening (CIS Docker Benchmark), health-check/readiness contract, backup/DR with RPO/RTO, CI/CD pipeline security, dependency & supply-chain scanning, production LOGGING config, error tracking (Sentry), metrics & SLOs, deployment/rollback safety.

2. **Phase 13 — Performance & Scalability** (consolidates performance aspects): Spec-derived SLOs with error budgets, caching strategy (invalidation correctness, locale segmentation, stampede prevention), connection-pooling strategy, query performance (EXPLAIN ANALYZE, N+1 discipline), load/stress testing.

3. **Phase 14 — Internationalization & Localization Correctness** (consolidates G6): Runtime locale resolution & normalization, fallback-chain correctness (no raw `.name` bypass), per-user language binding in bot notifications, DB-based i18n (cache-key locale segmentation), completeness beyond the CI test gate (title tags, hreflang, plurals, locale switching), RTL/Bidi readiness.

**Do NOT add phases for G7 or G8** — these are stale claims. The Ad model already has state-transition guards (`transition_to()`), DB CHECK constraints, soft-delete fields, concurrency protection (`select_for_update()`), and tests. The bot already has Pydantic v2 DTOs at its boundary. Both are covered by the existing 11 phases (03, 05, 10 for G7; 02, 05 for G8).

**Alignment with prior research:** This conclusion agrees with Researcher 1 on the 3-phase recommendation and the invalidation of stale G7/G8 claims. It agrees with Researcher 3 on the substantive gaps but disagrees on consolidation (3 focused phases > 1 mega-phase). It corrects Researcher 2 by rejecting stale G7/G8 as new-phase triggers.

---

*Confidence: HIGH. All claims verified against the actual codebase (settings files, CI workflows, Dockerfile, docker-compose, Ad model, bot schemas, handlers, tests). Two of eight gap-analysis claims (G7, G8) were found stale upon source-code inspection.*