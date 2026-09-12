---
title: Audit Phase Coverage — Researcher 3 Conclusion
date: 2026-09-12
source: @researcher agent (this round)
---

# Verdict: YES — 3 new phases needed (12, 13, 14)

## 1. Answer to the core question

**Do the existing 11 phases adequately cover all critical audit domains?**

**No.** After mapping every domain a modern production-readiness audit covers against the actual codebase, **three genuinely uncovered domains** remain after all 11 phases. Every other domain from a standard framework (Google SRE PRR, Django deployment checklist, CIS Docker Benchmark) is already addressed.

## 2. Evidence — 8 gaps from the prior gap analysis, verified against source

Each gap was checked against the live repository. **6 of 8 are accurate**; **2 are stale** (already solved in the codebase).

| Gap | Status | Evidence (file:line) |
|-----|--------|---------------------|
| **G1 — Dependency & supply-chain security** | ACCURATE | `ci.yml` has 6 jobs: build, test, lint, typecheck, lint-templates, i18n. None is a security scan. No `pip-audit`, `trivy`, `gitleaks`, `dependabot`, or `zizmor` anywhere. No `.github/dependabot.yml`. `pyproject.toml:10-29` has no Sentry/structlog/prometheus/dependency-audit deps. CI plan Stage D marks all as "TO BE BUILT" (`plan.md_updated.md:586-595`). |
| **G2 — Container runtime hardening** | ACCURATE | `Dockerfile:102-106,153` creates non-root `app` user (uid 1000) — good, satisfies CIS §6.1. But `docker-compose.prod.yml` has **zero** runtime hardening: no `security_opt`, `cap_drop`, `read_only: true`, `tmpfs`, or `user:` overrides on `web`/`bot`. Dockerfile `HEALTHCHECK` exists (`:158-159`) but no `security_opt: no-new-privileges` or read-only rootfs in the Dockerfile itself. |
| **G3 — Django production deployment checklist** | ACCURATE | No `manage.py check --deploy` invoked in any CI job or entrypoint. `CSRF_TRUSTED_ORIGINS` absent from `prod.py`, `base.py`, and `dev.py` (grep across all settings: 0 hits). `SECURE_CONTENT_TYPE_NOSNIFF` and `SECURE_BROWSER_XSS_FILTER` absent from `base.py` / `prod.py`. Only `XFrameOptionsMiddleware` present (provides default `DENY` but not the explicit Django settings flag). |
| **G4 — Production observability & logging** | PARTIALLY ACCURATE | `LOGGING` defined **only** in `dev.py:16-28` — absent from `base.py` and `prod.py` (grep: 1 hit, in dev only). No Sentry, no Prometheus, no OpenTelemetry, no `structlog` in deps. **BUT** the gap analysis's sub-claim "no health-check endpoint" is **INACCURATE** — `/health/` exists at `apps/core/views.py:41` (DB-probe only, returns `{"status": "healthy"}` / 503). The gap is real for `/metrics`, Sentry, SLOs, and a proper readiness/liveness distinction — but the "no health endpoint" claim is false. |
| **G5 — Backup & DR** | ACCURATE | `docker-compose.prod.yml:69-97` has a `backup` service (daily `pg_dump`, 7-day retention). `docs/ops/restore.md` documents the restore procedure. But: **no RPO/RTO defined**, **no restore-test cadence**, no WAL archiving / pgBackRest. `restore.md:176` explicitly states "No backup testing in CI (ephemeral environment)." |
| **G6 — i18n compliance** | ACCURATE | CI's `test_i18n_completeness.py` has exactly 4 tests (`pytestmark = [pytest.mark.unit]`): `test_no_hardcoded_visible_text`, `test_extraction_completeness`, `test_no_empty_msgstr` (ru/bs), `test_mo_compiled`. It does **not** verify: `<title>` localization, `hreflang` tags, plural-form correctness, locale-switching behavior, fallback-chain correctness (raw `.name` bypass), or RTL/Bidi. None of the 11 phases audits runtime i18n correctness beyond this narrow stati |
| **G7 — Business logic & data integrity** | **STALE** | The gap analysis claims "no model-level guard in `apps.ads.models.Ad`" preventing invalid transitions. This is **false**. The `Ad` model has a complete `transition_to()` method (`models.py:352-485`) with an enforced `ALLOWED_TRANSITIONS` matrix (line 384), `refresh_from_db()` to defeat stale-state races (line 403), and 6 DB-level `CheckConstraint`s enforcing status-timestamp consistency (lines 321-346). `select_for_update()` is used in ad edit (`ads/views/edit.py:126,281,315`) and moderation views (`moderation/views/review.py:78,125`, `moderation/admin_actions.py:140,186,247`). Dedicated concurrency tests exist (`test_transition_concurrency.py`, `test_edit_views_locking.py`, `test_moderation_views.py:564-591`). Phase 05 covers state-machine integrity (dimensions A1-A4) and Phase 03 covers lost-update/race prevention. Soft-delete: `User.is_deleted` (line 54) + `Ad.status=DELETED` + `Ad.deleted_at` (line 198), both CHECK-constrained. |
| **G8 — Bot input validation** | **STALE** | The gap analysis claims "bot uses raw `aiogram` types with no Pydantic validation." This is **false**. The bot has Pydantic v2 DTOs in `telegram_bot/schemas/message_payloads.py`: `TitlePayload`, `DescriptionPayload`, `PricePayload`, `PhotoCountPayload`. A `SavedSearchQueryPayload` and `SavedSearchPricePayload` also exist in `telegram_bot/schemas/saved_search.py`. These are actively used in `handlers/ad_create.py` (lines 459, 488, 596, 637). Validation failure tests exist in `test_price_payload.py`. Phase 02's boundary-DTO dimension covers this; Phase 05 covers ad-dialog validation. |

## 3. New phases needed: 3 (not 1, not 6)

### Why three — and specifically these three

Three domains are **entirely absent** from the 11 phases, each with a distinct evidence type and remediation path:

| New # | Phase | Domain | Evidence Type | Key Files Affected |
|-------|-------|--------|---------------|-------------------|
| 12 | **Production Operations, Security & Observability** | Container runtime hardening (CIS Docker Benchmark), health/readiness contract, backup/DR with RPO/RTO, CI/CD pipeline security (check --deploy, dependency/secret scanning, SAST), supply-chain integrity (SBOM, pip-audit, Trivy, Dependabot), production LOGGING config, error tracking, metrics & SLOs, deployment/rollback safety | Config dumps, HTTP responses, grep hits, command output | `Dockerfile`, `docker-compose.prod.yml`, `.github/workflows/*.yml`, `config/settings/prod.py` |
| 13 | **Performance & Scalability** | Spec-derived SLOs with error budgets, caching strategy (invalidation correctness, locale-key segmentation, cache-stampede prevention), connection-pooling strategy at scale, query-performance profiling discipline (beyond FTS index freshness), load/stress testing | Timing measurements, query plans, cache-key analysis, load-test output | `base.py` (CACHES, CONN_MAX_AGE), search/listing services, gunicorn config, cache-invalidation call sites |
| 14 | **Internationalization & Localization Correctness** | Runtime locale resolution & normalization (`en-US`→`en`), fallback-chain correctness (no raw `.name` bypass), per-user bot language in notifications, DB-based i18n (cache-key locale segment), completeness beyond the CI test gate (title tags, hreflang, plurals, locale switching, RTL/Bidi) | Rendered HTML, HTTP headers, cache keys, notification text comparisons | `LanguagePreMiddleware`, templates, `LanguageLocale` enum, bot notification paths, `test_i18n_completeness.py` test boundaries |

### Why three and not one (rejecting Researcher 3's consolidation)

Researcher 3 proposed folding all operational concerns into a single "Phase 12 — Production Operations & Observability." This is **suboptimal**:

1. **Different evidence types** — Phase 12 (ops) produces config dumps and grep hits; Phase 13 (performance) produces timing measurements and `EXPLAIN ANALYZE` plans; Phase 14 (i18n) produces rendered HTML in different locales. These require different runtime-verification procedures and different expertise.
2. **Different urgency & remediation paths** — A missing `check --deploy` (Phase 12) is a different class of fix from a missing SLO dashboard (Phase 13) or a locale-bleed bug in the submenu cache key (Phase 14). Merging them into one phase dilutes accountability.
3. **The project has already split them** — `.ai/audit/problems/` contains three separate, architecture-agnostic problem definitions (12, 13, 14) with distinct cross-cutting boundaries. The project's own direction is three phases, not one.

### Why three and not six (rejecting Researcher 2's over-split)

Researcher 2 proposed 6 phases (12-17), folding in G7 (business logic integrity) and G8 (bot input validation). This is **over-engineered** because:

1. **G7 is already solved** — the Ad model has `transition_to()` with a transition matrix, 6 DB CHECK constraints, `select_for_update()` locking in edit/moderation views, and dedicated concurrency tests. Phase 05 (dimension A1-A4) + Phase 03 already cover this. Creating a new "Business Logic Integrity" phase would re-audit territory already owned by two existing phases.
2. **G8 is already solved** — the bot has Pydantic v2 DTOs (`TitlePayload`, `DescriptionPayload`, `PricePayload`, `PhotoCountPayload`) actively used in `ad_create.py`. Phase 02 (boundary DTOs) + Phase 05 cover this.
3. **G1-G5 are not six separate phases** — they all converge on the same implementation touchpoints (`Dockerfile`, `docker-compose.*.yml`, `.github/workflows/*.yml`, `settings/prod.py`) and the same audit procedure (config inspection + grep + runtime verification). Splitting dependency scanning, container hardening, logging, and backup/DR into four separate phases fragments a unified operational concern without adding audit value.

### Phase consolidation map

| Prior gap analysis gap | Resolution |
|---|---|
| G1 (dependency security) | **Folds into Phase 12** (supply-chain integrity) |
| G2 (container hardening) | **Folds into Phase 12** (container runtime) |
| G3 (Django deploy checklist) | **Folds into Phase 12** (CI/CD pipeline security) |
| G4 (observability) | **Folds into Phase 12** (production logging & error tracking) — minus the "no health endpoint" inaccuracy |
| G5 (backup/DR) | **Folds into Phase 12** (backup & DR operations) |
| G6 (i18n compliance) | **Becomes Phase 14** |
| G7 (business logic) | **REJECTED** — already solved (Ad.transition_to + CHECK constraints + select_for_update + tests) |
| G8 (bot validation) | **REJECTED** — already solved (Pydantic v2 DTOs in schemas/) |

## 4. Prior research accuracy assessment

| Researcher | Verdict | Phase count | Accuracy |
|---|---|---|---|
| **Researcher 1** (summary) | 3 phases (12-14) | 3 | **CORRECT.** Accurately identified the gap analysis's errors on the `/health/` endpoint, G7, and G8. Recommended the same 3-phase split that the project has already started implementing in `.ai/audit/problems/`. |
| **Researcher 2** (gap analysis author) | 6 phases (12-17) | 6 | **MIXED.** The 6 accurate gap-analysis claims (G1-G6) are valid, but the gap analysis incorrectly treated G7 and G8 as real gaps — both are already solved in the codebase. Accepting stale claims as phase triggers led to over-splitting. |
| **Researcher 3** (summary) | 1 phase (12) | 1 | **CORRECT on gaps, SUBOPTIMAL on structure.** Correctly identified that no existing phase covers operational/security/observability concerns. Incorrectly recommended consolidating three domains with different evidence types and expertise into one phase. |
| **Researcher 2 (actual file)** | 3 phases (12-14) | 3 | **CORRECT.** The `researcher-2-conclusion.md` file on disk actually recommends 3 phases (not 6), correctly invalidates G7/G8, and aligns with the project's own `.ai/audit/problems/` directory. This contradicts the summary's description of Researcher 2 (which attributed a 6-phase proposal to them). |

## 5. Confidence

**HIGH.** All claims were verified directly against the repository:

- Settings: `prod.py:59 lines`, `base.py:271 lines`, `dev.py:44 lines` — confirmed `LOGGING` only in dev; no `CSRF_TRUSTED_ORIGINS`, no `SECURE_CONTENT_TYPE_NOSNIFF`/`SECURE_BROWSER_XSS_FILTER` in prod/base.
- CI: `ci.yml:253 lines` — confirmed 6 jobs, no security deploy job, no `check --deploy`, no pip-audit/Trivy/gitleaks.
- Dockerfile: `177 lines` — confirmed `USER app` at line 153, `HEALTHCHECK` at line 158.
- docker-compose: `prod.yml:125 lines` — confirmed no runtime hardening directives.
- Ad model: `models.py:766 lines` — confirmed `transition_to()` at line 352, `ALLOWED_TRANSITIONS` matrix at line 384, 6 CheckConstraints at lines 321-346, `select_for_update()` usage in edit/moderation views.
- Bot schemas: `message_payloads.py:59 lines` — confirmed Pydantic v2 DTOs actively used in `handlers/ad_create.py:1311 lines` (lines 459, 488, 596, 637).
- Backup: `restore.md:176 lines` — confirmed pg_dump + 7-day retention, no RPO/RTO, no restore-test cadence.
- i18n gate: `test_i18n_completeness.py:301 lines` — confirmed 4 narrow tests, no title-tag/hreflang/plural/locale-switch coverage.

---

## Conclusion

**Add 3 new phases (12, 13, 14)** matching the problem definitions already started in `.ai/audit/problems/`:

1. **Phase 12 — Production Operations, Security & Observability** — consolidates G1-G5 (dependency/security scanning, container hardening, CI/CD pipeline security, production logging, metrics/SLOs, health contract, backup/DR, deployment/rollback).
2. **Phase 13 — Performance & Scalability** — SLOs with error budgets, caching strategy (invalidity, locale segmentation, stampede prevention), connection-pooling strategy, query profiling discipline, load testing.
3. **Phase 14 — Internationalization & Localization Correctness** — runtime locale resolution, fallback-chain correctness, per-user bot language, DB-based i18n, completeness beyond the CI test gate (title tags, hreflang, plurals), RTL/Bidi.

**Do not add phases for G7 or G8** — both are stale claims already addressed by the codebase and covered by existing phases (03, 05, 10 for G7; 02, 05 for G8).
