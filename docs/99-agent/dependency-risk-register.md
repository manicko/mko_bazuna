---
id: dependency-risk-register
domain: agent
tags:
  - dependencies
  - risk
  - security
  - upstream
related:
  - architecture
  - rules
  - references
---

## Purpose

Tracks dependency risks that are accepted as trade-offs, deferred for a future refactor, or under ongoing monitoring for the Mko Bazuna project. Risks resolved by plan 30 (DEP-001/002/003/006) are summarized in [## Resolved dependency risks (plan 30)](#resolved-dependency-risks-plan-30) rather than registered as open risk.

This register is the single source of truth for "we know about X and we deliberately accept/defer it." Re-evaluate each entry before the conditions for its Next action are met.

## DEP-004 — faker bundled in all production images (Accepted trade-off)

- Dependency: `faker` `>=40.35.0` (declared in `[project].dependencies`, i.e. core)
- Status: Open — Accepted trade-off (not remediated in plan 30)
- Risk rating: LOW
- Where used: Solely `src/backend/apps/seed/` — `faker` is imported in `apps/seed/generators/base.py`; all other usages are `self.faker.*` on generator instances. No web/bot/scheduler/migrate code imports it.
- Why not fixed: The production image model is single and shared — all services (web, bot, scheduler, migrate, seed) run one GHCR image built from one `docker/Dockerfile`. The `runtime` stage ships NO `uv` binary (`UV_FROZEN=1`), so a runtime `uv sync --extra seed` is impossible, and the `seed` compose service builds the Dockerfile with no `build.target` (uses `runtime`). Therefore faker MUST live in the one venv every service shares. Removing it requires a backward-incompatible build-time image split (dedicated `seed-runtime` Docker stage installing the `seed` extra, `build.target` overrides in both `docker-compose.yml` and `docker-compose.prod.yml`, prod GHCR push/tag wiring, and `--extra seed` in `docker/entrypoint-test.sh` for the seed tests). The clean split is tracked as plan 30 §B5A (skipped — DG-2 = Path B).
- Trade-off: faker + its transitive footprint ships in every production image until the image model is split per-service.
- Next action / Re-evaluate: When deployment moves to per-service images, move `faker` into `[project.optional-dependencies] seed` and build a dedicated seed image (cap spec: plan 30 §B5A). Until then, do not refactor for a LOW-priority issue whose clean fix is a large, backward-incompatible change.

## DEP-005 — django-mptt 0.18.0 unmaintained upstream (Deferred migration)

- Dependency: `django-mptt` `>=0.18.0` → locked `0.18.0`
- Status: Open — Deferred migration (not remediated in plan 30)
- Risk rating: MEDIUM (long-term)
- Surface: `Category(MPTTModel)` in `apps/categories/models.py`; `CategoryAdmin(MPTTModelAdmin)` in `apps/categories/admin.py`; migration `apps/categories/migrations/0001_initial.py` uses `mptt.fields.TreeForeignKey`.
- Why not fixed now: No known CVEs; django-mptt 0.18.0 still works with Django 5.2 and the PostgreSQL 18 stack. PyPI/UPM marks the project unmaintained; there is no 0.19 stable (only a 0.19rc1 pre-release). The migration is L effort and out of scope here; tracked so it is revisited before the next Django LTS (6.0), where an unmaintained tree library risks incompatibility.
- Successor evaluated: `django-tree-queries` v0.26.1 (released 2026-09-07) — supports Django 3.2+, Python 3.14, PostgreSQL recursive CTEs, ships an official django-mptt migration guide. Confirmed viable for this stack.
- Migration scope (future): swap `MPTTModel`→`TreeNode`, `TreeForeignKey`→`parent` FK (named `parent`), `MPTTModelAdmin`→`TreeAdmin`; data migration to populate `position` from MPTT `lft` (tree-queries' documented `fill_position` recipe); rewrite template/admin calls using `tree_id`/`level`/`recursetree` to `tree_depth`/`tree_path`/`with_tree_fields()`/`recursetree`. Touch points: model + admin + migration + templates across `apps/categories/`.
- Next action: Before the Django 6.0 LTS upgrade, prototype the model+admin swap and the data migration on a branch; measure query regressions (the category tree is FTS-seeded and category-browsed). If acceptable, cut over.

## Resolved dependency risks (plan 30)

| Finding | Resolution | Commit |
|---|---|---|
| DEP-001 — Known vulnerabilities in the production lockfile (Django 5.2.16, sqlparse 0.5.5) | Lock bumped to Django 5.2.17 + sqlparse 0.6.0; `pip-audit` now reports 0 vulnerabilities. | `fix(deps): bump Django 5.2.17 + sqlparse 0.6.0 in uv.lock` (B2) |
| DEP-002 — CI security scanning not enforced | CI security job made blocking: pip-audit, Trivy (fs + image), gitleaks now fail the build (`exit-code: 1`, no `continue-on-error`). Commit-time prevention is now in place via `.pre-commit-config.yaml` (a `gitleaks protect` hook at the `commit` stage) that rejects secret-leaking commits before they enter history — complementing the post-commit CI scan and closing the gap at both layers. **Relaxation (plan 04):** the SARIF-mode `severity` filter was inert — `aquasecurity/trivy-action` unsets `TRIVY_SEVERITY` unless `limit-severities-for-sarif: true`, so the gate failed on *any* severity with a fix. Both Trivy SARIF steps now set that flag, so only CRITICAL/HIGH block (LOW/MEDIUM-with-fix findings no longer do). Both keep `exit-code: 1`, and a read-only `Summarise Trivy image findings` step prints the SARIF into the job log. | `chore(ci): make pip-audit, Trivy, and gitleaks scans blocking and align CI-security tests` (B4) |
| DEP-003 — Lower-bound-only version constraints | Upper bounds (`<N+1.0`) added to all 20 lower-bound-only direct dependencies in `[project].dependencies`; django cap retained as the model. The `pillow` cap was corrected from `<11.0` to `<13.0` during implementation to avoid downgrading to the vulnerable 10.4.0 line. **Relaxation (plan 04):** the cap moved `<13.0` → `<14.0` so the `pillow` 13.0.0 security fix (44 advisories) can be installed. The cap is an `<N+1.0` policy convention, not a technical constraint (the `<13.0` value came from commit `0d04b876`); the API blast radius of 13.0.0 was audited as none. | `chore(deps): add upper bounds to major-version-sensitive direct dependencies` (B3) |
| DEP-006 — Dependabot/uv-lock freshness gap | Dependabot switched `pip`→`uv` ecosystem; `.python-version` pinned to `3.14`; `uv lock --check` freshness gate added to all 6 dev CI jobs + a `lock-check` Makefile target. | `chore(ci): add uv.lock freshness gate, switch Dependabot to uv ecosystem, pin .python-version` (B1) |
| Known vulnerabilities in the lockfile (plan 04, CI run 42020286691) | Narrow per-package lock bump (66 advisories across 6 packages): `aiohttp` 3.14.3→3.14.5, `brotli` 1.2.0→1.2.1, `certifi` 2026.7.22→2026.10.23, `filelock` 4.0.0→4.2.9, `msgpack` 1.2.2→1.2.4, `pillow` 12.3.0→13.0.0, plus the forced transitive `yarl` 1.24.5→1.25.1 (aiohttp ≥3.14.4 requires `yarl>=1.25.1`). Verified: `pip-audit` reports 0 vulnerabilities; `uv lock --check` exits 0; `git diff uv.lock` shows only those packages. `certifi` targets 2026.10.23, not the advisory-named 2026.10.18, because that release removed all emSign roots including healthy ones. | `fix(ci): resolve pip-audit CVEs and surface Trivy image findings` (plan 04) |

Conventions: status values are Open / Accepted trade-off / Deferred migration; risk ratings LOW/MEDIUM/HIGH (see the findings for Severity × Priority). An item moves to "Resolved" only after its verification gates pass (e.g., DEP-003 resolved only after `pip-audit` + `uv lock --check` both passed).
