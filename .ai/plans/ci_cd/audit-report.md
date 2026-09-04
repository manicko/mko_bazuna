# CI/CD Planning Documents — Architecture & Best-Practice Audit Report

**Audit date:** 2026-09-01
**Auditor:** Senior Staff Architecture Auditor (Kilo)
**Subject files:** `.ai/plans/ci_cd/plan.md` (2026-07-28), `.ai/plans/ci_cd/preparation-guide.md` (2026-07-28), `.ai/plans/ci_cd/research.md` (2026-07-27)
**Baseline constraint:** Updated documents must keep the core approach — Docker + GHCR + manual `workflow_dispatch` deploy to a single VPS, GitHub Actions, PostgreSQL 18, Django 5.2, aiogram.

---

## Executive Summary

The three 2026-07 planning documents were written *before* the CI pipeline was implemented and describe a **target state**, not the current reality. The project has since shipped a substantially different and more mature CI setup that the old plans do not acknowledge, while the planned CD pipeline (the entire deploy stage) has **not been built at all**.

**What reality looks like today.** The repository uses `docker-compose.{yml,dev.override.yml,prod.yml,test.yml}` — the plan's proposed rename to `compose.*.yaml` was never applied and is embedded, untested, in every Makefile target, the dev/prod/test overrides, and `.kilo/rules/commands.md`. CI lives in two workflow files — `.github/workflows/ci.yml` (6 jobs: build, test, lint, typecheck, lint-templates, **i18n**) and `.github/workflows/ci-nightly.yml` (serial seed suite, daily cron + manual trigger) — **not** the `ci.yml + deploy.yml` split the plan proposes. The current `ci.yml` omits several things the plan assumes exist: there is **no concurrency block**, **no path filters**, and the test job uses `uv sync --group dev`, `--dist loadgroup`, `-m "not seed"`, `--reuse-db`, and `--cov` — details captured as an enforceable contract by `src/backend/tests/test_docs_ci_parity.py`.

**The gap that matters most: there is no CD.** No `deploy.yml` exists in `.github/workflows/` (only `ci.yml` and `ci-nightly.yml` are present). The build job runs with `push: false` against a GHCR registry cache, so no image is ever published for deployment. The plan's entire Stage C (C1–C10: GHCR push, SHA tags, SSH deploy, pre-deploy backup, migrations, image override, health-check rollback, prune) is unstarted. Security scanning (Stage D: Trivy, SARIF, pip-audit) is likewise absent. The one place the plan guessed right — `compose.prod.yml` overriding `web`/`bot`/`migrate`/`create_admin`/`seed` with GHCR images (§15.1) — is **already implemented** and correct.

**Secret strategy is already reconciled in code.** `research.md` §5.1 claims 8 GitHub Secrets including app secrets (`DJANGO_SECRET_KEY`, `BOT_TOKEN`, …); `plan.md` §3 and `preparation-guide.md` §B2 counter that only 4 server-access secrets belong in GitHub and app secrets live *only* in `.env.docker` on the VPS. Current reality matches the latter: `.env.docker` is the single source of truth (`.gitignore:148` ignores it), `.env.docker.example` holds the 10+ app variables, `prod.py` fail-fast-guards `BOT_TOKEN`/`SITE_URL`/`ALLOWED_HOSTS` and `base.py` requires `DJANGO_SECRET_KEY` — nothing reads app secrets from GitHub Actions secrets. `research.md` §5.1 is therefore **stale** and should be corrected, not used as a template.

**Other drift.** The plan/research repeatedly say "Montenegrin"; the actual i18n implementation uses **Russian / Bosnian / English** — `config.settings.base.LANGUAGES` (lines 69–73), `LanguageLocale` enum (`enums.py:187`, values `ru`/`bs`/`enium.ENU`) and `Dockerfile:83` (`--locale ru --locale bs --locale en`). This is a spec-accuracy issue: the launch geography is Montenegro, but the UI/content language code is Bosnian, and the docs must stop claiming Montenegrin. Finally, the repo root contains four **0-byte entrypoint stubs** (`entrypoint.sh`, `entrypoint-test.sh`, `entrypoint-catalog.sh`, `entrypoint-seed.sh`) that shadow nothing (the real scripts live in `docker/`) but are confusing dead files.

**Recommendation posture.** The CI baseline is mostly sound and should be preserved in the updated plan as "already in place," with two cheap wins added per modern best practice: a `concurrency` group on `ci.yml` and `paths-ignore` filters for docs-only changes. The CD pipeline must be built from scratch following the plan's Stage C sequence (pull → backup → migrate → up → prune → health-check), now enriched with OIDC authentication to GHCR (deprecating the PAT/`GITHUB_TOKEN`-as-password pattern), Dependabot, gitleaks + `.gitleaks.toml`, zizmor workflow linting, `--dist worksteal` when xdist ≥ 3.8, and `--import-mode=importlib` in pytest addopts. None of these change the core Docker+GHCR+manual-deploy approach; they harden an already-correct architecture.

---

## Section-by-Section Verdicts

### `plan.md` Section 0 — Overview (lines 9–17)

| Claim | Verdict | Evidence |
|---|---|---|
| CI = parallel lint → typecheck → test | **PARTIALLY INACCURATE** | `ci.yml` has 6 parallel jobs: build, test, lint, typecheck, **lint-templates** (djlint), **i18n** (compilemessages + `test_i18n_completeness.py`). The i18n + lint-templates jobs are undocumented in the plan. |
| CD = manual workflow dispatch → build → push → deploy | **NOT YET REALIZED** | No `deploy.yml` exists. `ci.yml` build job uses `push: false` (`.github/workflows/ci.yml:30`). |
| Workflow files: `ci.yml` + `deploy.yml` | **STALE** | Reality is `ci.yml` + `ci-nightly.yml`. No `deploy.yml` exists at all. |
| Registry: GHCR | **ACCURATE** | `ci.yml:19–23` logs into `ghcr.io`; `docker-compose.prod.yml:8,13,18,22,26` uses `${REGISTRY:-ghcr.io}`. |
| Target: single VPS, no staging | **ACCURATE** | Consistent with `docker-deployment.md:264–275` and the manual `workflow_dispatch` design. |

### `plan.md` Section 1 — Repository Structure (lines 20–46)

| Claim | Verdict | Evidence |
|---|---|---|
| Compose files named `compose.yaml`, `compose.prod.yaml`, `compose.test.yaml` | **WRONG / STALE** | All files use legacy `docker-compose.*.yml` naming. `Makefile:10` `-f docker-compose.yml -f docker-compose.dev.override.yml`; `Makefile:11` `-f docker-compose.yml -f docker-compose.test.yml`. Every Makefile target, `docker-deployment.md`, and `.kilo/rules/commands.md` references `docker-compose.*.yml`. The rename proposed here was never applied and is embedded in tooling. |
| Rename compose files during implementation | **STALE** | Never applied; should be **dropped** from the updated plan. |

### `plan.md` Section 2 — What Lives Where (lines 50–83)

| Claim | Verdict | Evidence |
|---|---|---|---|
| `.env.docker` = production env, NOT committed | **ACCURATE** | `.gitignore:148` ignores `.env.docker`; tracked template is `.env.docker.example` (3391 bytes, confirmed at repo root). |
| Three `.example` templates tracked | **ACCURATE** | Repo root has `.env.docker.example`, `.env.example`, `.env.dev.example`. |
| App secrets ONLY in `.env.docker` on VPS; GitHub Secrets = 4 server-access creds | **ACCURATE** | Reconciles `research.md` §5.1 (which wrongly lists 8 secrets). `prod.py:18–22,26–30,50–51` fail-fast guards `BOT_TOKEN`/`SITE_URL`/`ALLOWED_HOSTS`; `base.py:52` requires `DJANGO_SECRET_KEY`. No workflow reads app secrets from GitHub. |
| `docker/entrypoint*.sh` committed | **ACCURATE BUT INCOMPLETE** | Real scripts are in `docker/` (6 files, all >0 bytes). However 4 **0-byte stubs** also exist at repo root (see Dead Files). |
| `compose.dev.yaml` listed in git-tracked files | **STALE** | Reality is `docker-compose.dev.override.yml`. The prep-guide §Repository Structure (line 139) reproduces this same naming error. |

### `plan.md` Section 3 — SSH Key Pairs (lines 85–97)

| Claim | Verdict | Evidence |
|---|---|---|
| `github_bazuna` (GitHub access, Windows→GitHub) | **ACCURATE** | Matches `preparation-guide.md` §0.5 and §SSH Key Pairs. |
| `deploy_bazuna` (VPS deploy, GitHub Actions→VPS) | **ACCURATE** | Matches `preparation-guide.md` §B2/§SSH Key Pairs; `SERVER_SSH_KEY` GitHub Secret. |

### `plan.md` Section 4 — Pre-implemented Components (lines 100–109)

| Claim | Verdict | Evidence |
|---|---|---|
| Non-root uid-1000 | **ACCURATE** | `docker/Dockerfile:102–106,149` creates `app` group/user uid 1000; `USER app` at `:149`. |
| Coverage upload | **ACCURATE** | `ci.yml:114–119` uploads `coverage.xml` artifact. |
| PostgreSQL 18 service | **ACCURATE** | `postgres:18-alpine` in `ci.yml:41` (CI) and `docker-compose.yml:7` (docker). |
| Build cache (⚠️ optional, registry cache) | **IMPLEMENTED** | `ci.yml:32–33` `cache-from: type=registry,ref=ghcr.io/manicko/mko_bazuna:buildcache`, `cache-to: type=registry,…,mode=max`. The "optional" framing is stale; the registry cache is live. |
| Health endpoint | **ACCURATE** | `docker/Dockerfile:154–155` `HEALTHCHECK … curl -f http://localhost:8000/health/`. |
| Docker image prune | **PLANNED, not implemented** | No `deploy.yml`; `image prune` belongs to the unbuilt deploy job. `docker-deployment.md:223` only documents `make prune-backups` (DB backups), not image prune. |

### `plan.md` Section 5 — Implementation Stages (lines 113–263)

**Stage 0 (lines 115–143):** Local Windows machine. ✅ **ACCURATE.** Matches `preparation-guide.md` §0 and current toolchain (Git, Docker Desktop, Python 3.14, uv). *Note:* line 141 `docker compose -f compose.yaml -f compose.test.yaml up -d` uses stale naming — should be `docker-compose.yml` / `docker-compose.test.yml`; `make up` / `make test-db` is the canonical invocation (`Makefile`, `docker-deployment.md:116`).

**Stage A (lines 147–220):** VPS prep + secrets. ✅ **MOSTLY ACCURATE.** `.env.docker` content matches `.env.docker.example`. The 4-GitHub-Secret rule matches code reality. *Minor inaccuracy:* A9 lists "file permissions" — `docker-deployment.md:393–402` confirms `chmod 600 .env.docker` and `certs` perms are already documented.

**Stage B (lines 224–235):** CI enhancement — B1 concurrency, B2 split into `ci.yml + deploy.yml`, B3 path filters. ⚠️ **MIXED.**
- B1 (concurrency): **NOT IMPLEMENTED.** `ci.yml:3–7` has no `concurrency:` block at workflow level.
- B2 (split ci.yml + deploy.yml): **PARTIALLY MISMATCHED.** CI was split, but into `ci.yml + ci-nightly.yml` (nightly seed suite), **not** `ci.yml + deploy.yml`. No deploy file exists.
- B3 (path filters): **NOT IMPLEMENTED.** No `paths-ignore` in `ci.yml:3–7`.
- B6 (rollback docs into `docs/ops/docker-deployment.md`): **ALREADY DONE.** `docker-deployment.md:788–736` has a rollback/ssh section; see §Stage E below.

**Stage C (lines 239–252):** CD extension (C1–C10). ❌ **NOT STARTED.** No `deploy.yml`; no GHCR push (`ci.yml:30` `push: false`); no SHA-based deploy tags; no SSH deploy step; no pre-deploy `pg_dump`; no pre-deploy migrations in prod; no health-check/rollback in workflow. `compose.prod.yml` image override (C8) **is implemented** (lines 7–26).

**Stage D (lines 256–263):** Security (D1 Trivy, D2 SARIF, D3 pip-audit). ❌ **NOT IMPLEMENTED.** No security scanning anywhere in `.github/workflows/`. Confirmed by absence.

### `plan.md` Section 10 — Files to Create/Modify (lines 383–395)

| Action | Verdict | Evidence |
|---|---|---|
| Create `.github/workflows/ci.yml` | **IMPLEMENTED** | Exists; 6 jobs (see §Section 5 above). |
| Create `.github/workflows/deploy.yml` | **NOT DONE** | `.github/workflows/` contains only `ci.yml` + `ci-nightly.yml`. |
| Rename `docker-compose.yml`→`compose.yaml` etc. | **STALE — DO NOT DO** | All tooling uses legacy names; renaming breaks Makefile, overrides, CI, and docs. |
| Modify `compose.prod.yaml` for image override | **ALREADY DONE** | `docker-compose.prod.yml:7–26`. |
| Merge rollback docs into `docs/ops/docker-deployment.md` | **ALREADY DONE** | `docker-deployment.md:788–876` has rollback section (§Stage E in prep-guide maps here). |
| Ensure `.env.docker` in `.gitignore` | **ALREADY DONE** | `.gitignore:148`. |

### `plan.md` Section 14 — Branch Strategy (lines 757–763)

| Claim | Verdict | Evidence |
|---|---|---|
| `main` = CI + CD; `develop` = CI only | **PARTIALLY INACCURATE** | CI exists on both branches (`ci.yml:3–5`). CD is absent entirely. The branch distinction is correct in principle but the "CD" half is unbuilt. Does **not** account for `ci-nightly.yml` (serial seed suite, cron + manual). |

### `plan.md` Section 15 — Architecture Constraints (lines 825–858)

| Claim | Verdict | Evidence |
|---|---|---|
| 15.1 Build vs Pull Resolution (image override) | **IMPLEMENTED** | `docker-compose.prod.yml:7–26`; base `build:` at `docker-compose.yml:31–50`. ✅ matches. |
| 15.2 Deploy workflow sequence | **UNIMPLEMENTED** | No deploy workflow. Documented sequence (pull → backup → migrate → up → prune) should be preserved verbatim in updated plan. |
| 15.3 Secrets strategy | **ACCURATE / ALREADY ADOPTED** | App secrets in `.env.docker` only; 4 GitHub Secrets. |
| 15.4 Compose naming | **STALE** | Legacy names in use; do not rename. |

### `preparation-guide.md` Section-by-Section

| Section | Verdict | Notes |
|---|---|---|
| §Stage 0 (Windows setup) | ✅ Accurate | Matches toolchain reality. |
| §Repository Structure (line 120) | ⚠️ Stale naming | Lists `compose.yaml`, `compose.dev.yaml`, `compose.prod.yaml`, `compose.test.yaml`. Reality: `docker-compose.yml`, `docker-compose.dev.override.yml`, `docker-compose.prod.yml`, `docker-compose.test.yml`. Also list `docker-compose.dev.override.yml` which the plan omits. |
| §What Lives Where | ✅ Accurate | Matches gitignore + templates. |
| §SSH Key Pairs | ✅ Accurate | |
| §Stage A (VPS prep) | ✅ Accurate | |
| §Stage B (GitHub config: 4 secrets) | ✅ Accurate | Matches code's actual secret strategy (reconciles research.md §5.1). |
| §Stage C (Workflow files: ci.yml + deploy.yml) | ⚠️ Partially stale | ci.yml exists but differs (6 jobs, no concurrency, no path filters); **deploy.yml never created**. §C5 claims `compose.prod.yaml` "already has image overrides" — correct. §C5 also references `docs/ops/docker-deployment.md` rollback merge — already done. Forward-looking §4 recommends rename to `compose.*.yaml` — stale, do not follow. |
| §Stage E (Rollback) | ⚠️ Half-accurate | Automatic rollback references a `deploy.yml` health-check step that does not exist. Manual rollback via Actions assumes a Deploy workflow. Manual rollback via SSH is accurate. |
| §Stage F (Verification) | ⚠️ Partially stale | CI verification assumes path filters and concurrency (not implemented); CD/rollback verification depends on the missing deploy.yml. |
| §Stage G (Daily release) | ❌ Not achievable | Depends on the unbuilt `deploy.yml`. |
| §Forward-looking §3 (rename compose) | ❌ Do not do | Rename breaks existing tooling. |
| §Forward-looking §4 (pip-audit) | ✅ Still valid | Not implemented; recommend adding as CI job. |

### `research.md` Section-by-Section

| Section | Verdict | Notes |
|---|---|---|
| §1.3 Docker services table | ⚠️ Incomplete | Lists db, migrate, create_admin, web, bot, nginx, scheduler, backup, pgbouncer. Missing `redis`, `load_catalog`, `seed`. Current `docker-compose.yml` also defines redis + load_catalog; prod adds scheduler/backup/pgbouncer. |
| §5.1 GitHub Secrets (8 secrets incl. app secrets) | ❌ CONTRADICTS reality | Current stance (plan §3, prep-guide §B2, code) is 4 server-access secrets only; app secrets in `.env.docker`. research.md §5.1 is stale and must be corrected. |
| §5.2 Single `ci-cd.yml` | ❌ STALE | Reality is `ci.yml` + `ci-nightly.yml`. |
| §5.5 Cost ~2,160 min/month | 🟡 Forward-looking concern | Valid concern (exceeds 2,000 free tier for private repos). Recommend path filters + concurrency to reduce. Not a reality-check item. |

---

## Claim Matrix

| Plan § | Claim | Current Reality | Status | Best Practice | Action for Updated Doc |
|---|---|---|---|---|---|
| plan.md §0 | CI = lint+typecheck+test only | 6 jobs incl. lint-templates + i18n | STALE | Keep i18n + lint-templates jobs | Document full 6-job CI; mark lint-templates & i18n as already-implemented |
| plan.md §0 | CD = workflow_dispatch deploy | No deploy.yml; build push:false | STALE/IMPLEMENTED-GAP | OIDC→GHCR, build-push | Create deploy.yml from scratch (Stage C), preserve pull→backup→migrate→up→prune sequence |
| plan.md §1, §10, §15.4 | Rename compose.*.yml → compose.*.yaml | All tooling uses docker-compose.*.yml | WRONG | Follow repo convention | **Do not rename.** State legacy naming as baseline. |
| plan.md §2, §A8 | App secrets in .env.docker only; 4 GH Secrets | .gitignore:148; prod.py guards; no GH secret reads | ACCURATE | Same (current stance is correct) | Keep verbatim; note it reconciles research.md §5.1 |
| plan.md §4 | Build cache ⚠️ optional | ci.yml:32–33 registry cache live | IMPLEMENTED | Add metadata-action + GHA cache | State as done; recommend GHA cache + metadata-action as hardening |
| plan.md §4 | docker image prune | In unbuilt deploy job | NOT IMPLEMENTED | prune after deploy | Add to deploy.yml; document in updated plan §C10 |
| plan.md §B1 | concurrency control on ci.yml | No concurrency block in ci.yml | NOT IMPLEMENTED | concurrency group + cancel-in-progress | Add `concurrency:` block; mark as recommended hardening |
| plan.md §B2 | split into ci.yml + deploy.yml | Real split is ci.yml + ci-nightly.yml | MISMATCHED | Separate CI from CD | Update plan: CI split = ci.yml + ci-nightly.yml; CD = deploy.yml (to build) |
| plan.md §B3 | path filters (skip docs CI) | No paths-ignore in ci.yml | NOT IMPLEMENTED | Skip docs/*.md on push/PR | Add `paths-ignore`; mark as small hardening |
| plan.md §C1–C10 | Full CD pipeline | Nothing implemented (no deploy.yml, push:false) | NOT STARTED | OIDC auth, metadata-action, SHA tags | Implement Stage C whole; keep SHA-required workflow_dispatch |
| plan.md §D1–D3 | Trivy + SARIF + pip-audit | No scanning in workflows | NOT IMPLEMENTED | Trivy fs mode (simplest), pip-audit Py3.14 verify | Add security-scan job (non-blocking) + pip-audit CI job |
| plan.md §10.1 | ci.yml inline YAML | ci.yml real content differs (build cache, i18n, group dev) | STALE | Match documented contract to reality | Reference `test_docs_ci_parity.py` as CI contract; show real ci.yml shape |
| plan.md §14 | branch strategy main/develop | Same; but no CD yet; nightly unaccounted | PARTIALLY INACCURATE | Branch strategy w/ nightly | Add ci-nightly.yml to branch table; note CD is manual dispatch on main only |
| prep guide §Repo Structure | compose.*.yaml naming; compose.dev.yaml | docker-compose.*.yml; dev.override.yml | STALE | Match repo reality | Correct all compose file names in updated docs |
| prep guide §Forward-looking §3 | rename to compose.*.yaml | Legacy names entrenched | WRONG | Keep legacy | Remove the rename recommendation entirely |
| prep guide §Forward-looking §4 | pip-audit job | Not implemented | NOT IMPLEMENTED | Verify Py3.14 support | Add pip-audit CI job; reference in updated prep-guide |
| research.md §1.3 | services: db,migrate,create_admin,web,bot,nginx,scheduler,backup,pgbouncer | Adds redis, load_catalog, seed | STALE | Document full set | Correct service inventory; add redis/load_catalog/seed |
| research.md §5.1 | 8 GitHub Secrets incl. DJANGO_SECRET_KEY etc. | 4 server-only creds; app secrets in .env.docker | CONTRADICTS REALITY | Keep app secrets out of GitHub | **Correct** research.md §5.1 → 4 secrets only |
| research.md §5.2 | single ci-cd.yml | ci.yml + ci-nightly.yml | STALE | Split CI from CD | Reflect actual two-file CI split |
| plan.md §5 Stage D / research §5.8 | "Montenegrin" language | ru/bs/en (Bosnian) in code | STALE | Align docs to code | State ru/bs/en; note launch geography is Montenegro |
| plan.md §10.3 deploy.yml health check | curl http://web:8000/health/ | Unimplemented | NOT IMPLEMENTED | internal-network health probe | Preserve in deploy.yml; note compose-internal hostname |
| plan.md §10.3 deploy.yml rollback | read /tmp/previous_tag.txt | Unimplemented | NOT IMPLEMENTED | Image digest pinning | Preserve rollback flow; recommend digest pinning as hardening |
| plan.md §C5 (prep guide) | compose.prod.yaml has image overrides | Implemented | ALREADY DONE | — | Mark as already-implemented in updated docs |
| plan.md §B6 / prep §C5 | rollback docs in docker-deployment.md | Exists (lines 788–876) | ALREADY DONE | — | Do not re-create; reference existing docs |

---

## Dead Files / Stale References

### 0-byte entrypoint stubs at repository root

The real entrypoint scripts live in `docker/` (6 non-empty files). The following **0-byte stubs** exist at the repo root and serve no purpose — they are not referenced by any compose file (which mounts `docker/entrypoint*.sh`) and shadow nothing meaningful. They are likely accidental leftovers from a copy or an earlier layout.

| File (repo root) | Size | Real counterpart |
|---|---|---|
| `entrypoint.sh` | 0 bytes | `docker/entrypoint.sh` (3,472 bytes) |
| `entrypoint-test.sh` | 0 bytes | `docker/entrypoint-test.sh` (2,702 bytes) |
| `entrypoint-catalog.sh` | 0 bytes | `docker/entrypoint-catalog.sh` (493 bytes) |
| `entrypoint-seed.sh` | 0 bytes | `docker/entrypoint-seed.sh` (1,376 bytes) |

**Recommendation:** Investigate purpose before removal (per dead-code policy). If no workflow or tool references them, delete them and add the root-level stubs to `.gitignore` or `.dockerignore` exclusion as appropriate. Do **not** delete `docker/entrypoint*.sh`.

### Stale naming references

Every occurrence of `compose.yaml` / `compose.prod.yaml` / `compose.test.yaml` / `compose.dev.yaml` in the three plan files is a **stale reference**. Current files are `docker-compose.yml`, `docker-compose.dev.override.yml`, `docker-compose.prod.yml`, `docker-compose.test.yml`. Tooling that depends on the legacy names:
- `Makefile:10–11,223,239` — all `-f docker-compose*.yml`
- `docker-compose.dev.override.yml` mounts `./docker/entrypoint*.sh` explicitly (lines 23, 42, 53, 71, 82)
- `docker-deployment.md` §Compose Project Isolation table (line 63–64) and all "Exact invocation forms"
- `.kilo/rules/commands.md` (referenced in context) uses `docker-compose.*.yml`
- `entrypoint-test.sh` (the real one) is invoked as `/app/entrypoint-test.sh` inside the `test` service (`docker-compose.test.yml:51`)

### Language: "Montenegrin" vs Bosnian

The plan and research files, and much of `docs/`, describe a "Montenegrin" UI language. The **implementation** uses **Bosnian** (`bs`):
- `src/backend/config/settings/base.py:69–73` — `LANGUAGES = [("ru","Russian"),("bs","Bosnian"),("en","English")]`, `LANGUAGE_CODE = "ru"`
- `src/backend/apps/core/enums.py:187–192` — `LanguageLocale.RUSSIAN="ru"`, `LanguageLocale.BOSNIAN="bs"`, `LanguageLocale.ENGLISH="en"`
- `docker/Dockerfile:76–83` — `compilemessages --locale ru --locale bs --locale en`
- `ci.yml:100,203` — `--locale ru --locale bs --locale en`

**Recommendation:** Updated docs must state **`ru`/`bs`/`en`** (Russian/Bosnian/English). "Montenegro" remains correct as the **launch geography / market**, but the UI language code is Bosnian, not Montenegrin. Correct `docs/06-design-system/index.md:27`, `docs/01-spec/technical-specification.md:28,62`, and similar spec prose to avoid conflating geography with locale.

### Secrets-strategy contradiction in source files

- `plan.md §3 / §15.3 / §A8`: app secrets in `.env.docker` only; 4 GitHub Secrets. ✅ Correct.
- `preparation-guide.md §B2`: "only 4 secrets." ✅ Correct.
- `research.md §5.1 (lines 209–217)`: lists 8 secrets **including `DJANGO_SECRET_KEY`, `BOT_TOKEN`, `ADMIN_PASSWORD`, `POSTGRES_PASSWORD`** as GitHub Secrets. ❌ Contradicts reality and the other two files. The updated `research.md` must be corrected to 4 server-only secrets.

---

## Recommended Structure for Updated Docs

The updated `plan.md` and `preparation-guide.md` must **not** re-propose work already done, must **correct** the stale/wrong claims, and must **preserve** the core Docker + GHCR + manual-`workflow_dispatch` + single-VPS approach. They should also **integrate** the modern best-practice additions (OIDC, Dependabot, concurrency, Trivy, gitleaks, zizmor, worksteal, importlib) **without** altering the deployment model.

### `plan.md_updated.md` — structure

1. **Metadata** — date, author, status (draft), links to `preparation-guide.md` and `arch.md`.
2. **Overview** — restated: CI (6-job parallel gate in `ci.yml` + nightly seed suite `ci-nightly.yml`) → manual `workflow_dispatch` CD (`deploy.yml`, to be built) → GHCR → single VPS. Explicitly state CI is **live**, CD is **to-do**.
3. **Repository Structure** — corrected tree using `docker-compose.*.yml` names. Add: `.github/workflows/{ci.yml, ci-nightly.yml, deploy.yml (NEW)}`, `docker/entrypoint*.sh` (6 files), `.env*.example` (3 tracked templates), 4 root-level 0-byte stubs (marked dead, pending cleanup).
4. **What Lives Where** — unchanged (app secrets in `.env.docker` only; 4 GitHub Secrets). Add the reconciliation note that `research.md` §5.1 is corrected.
5. **Pre-implemented Components** — reclassified to an "Already in Place" baseline table:
   - ✅ Dockerfile 3-stage (builder/runtime/test-runtime), uid-1000, HEALTHCHECK, standalone Tailwind
   - ✅ CI: 6 jobs + nightly; GHCR registry build cache (`push:false`); PG 18 service
   - ✅ `docker-compose.prod.yml` image overrides (web/bot/migrate/create_admin/seed → GHCR) + scheduler/backup/pgbouncer profile-gated
   - ✅ `.env.docker` gitignored; 3 templates; fail-fast prod settings guards
   - ✅ `test_docs_ci_parity.py` enforces CI contract (loadgroup, not-seed, reuse-db, etc.)
   - ✅ Rollback docs merged into `docs/ops/docker-deployment.md`
   - ⚠️ Build cache: implemented via registry cache; recommend metadata-action + GHA cache as next hardening
6. **SSH Key Pairs** — unchanged (two pairs).
7. **Implementation Stages** — restructured:
   - **Stage 0:** Local dev (Windows PowerShell + `Makefile.ps1`) — unchanged.
   - **Stage A:** VPS prep — unchanged (4 GH Secrets, `.env.docker` on VPS).
   - **Stage B (CI — largely DONE):** Document current 6-job `ci.yml` + `ci-nightly.yml` as baseline. **Two gap-closing tasks only:** B1 add `concurrency:` group; B3 add `paths-ignore` for docs/markdown. Mark B2/B6 as DONE.
   - **Stage C (CD — TO BUILD):** Full C1–C10 from scratch. Use OIDC (`id-token: write`) for GHCR auth (replaces `GITHUB_TOKEN`-as-password). SHA-required `image_tag` (no `latest` default). Preserve pull → backup → migrate → up → prune → health-check → rollback sequence. **Modernize:** `--dist worksteal` (xdist ≥3.8), `--import-mode=importlib` in pytest addopts (already present), metadata-action for tags.
   - **Stage D (Security — TO BUILD):** D1 Trivy (fs mode simplest + non-blocking CRITICAL/HIGH), D2 SARIF upload, D3 pip-audit (verify Py3.14 support), **plus** best-practice D4 Dependabot (actions + docker), D5 gitleaks + `.gitleaks.toml`, D6 zizmor workflow linting.
8. **Execution Order / DAG** — redraw to reflect: CI baseline live → (B1, B3 small) → CD build (C1–C10) → Security (D1–D6). Nightly suite is separate (cron + manual).
9. **Risk Assessment** — keep table; update Trivy-blocking risk (now non-blocking), add OIDC-key-leak risk (mitigate: `id-token: write`, no PAT), add cost risk (path filters/concurrency mitigate).
10. **Verification Steps** — split into "already verified" (CI gate, parity test) and "to verify after CD built" (deploy, health, rollback).
11. **Files to Create/Modify** — correct the table: create `deploy.yml` (+ `trivy` config, `.gitleaks.toml`, `.github/dependabot.yml`), **do not rename** compose files, do **not** recreate rollback docs.
12. **Deployment Commands Reference** — keep §10.1 script (corrected compose names) as the deploy job body; fix `docker inspect web | jq` to use the running container name with `docker compose ps`.
13. **Branch Strategy** — `main` (CI + trigger CD via dispatch); `develop` (CI only); add **nightly** row (ci-nightly.yml: cron + manual, always-runs seed).
14. **Architecture Constraints** — §15.1 (image override) now marked DONE/implemented; §15.2 (deploy sequence) preserved; §15.3 (secrets) preserved (4+G; reconcile research.md); §15.4 (naming) corrected — **do not rename**.
15. **Modern Best-Practice Integration** — explicit section mapping each recommendation (OIDC, Dependabot, concurrency, Trivy, gitleaks, zizmor, worksteal, importlib, metadata-action) to a concrete file/effort/priority, flagged as advisory (recommended, not mandatory).

### `preparation-guide.md_updated.md` — structure

1. **Metadata** — date, author, links.
2. **Stage 0 — Local Dev Machine (Windows)** — unchanged, but use `make up` / `make test-db` (or `Makefile.ps1`) instead of raw `docker compose -f compose.yaml …`; correct compose file names.
3. **Repository Structure** — corrected tree (legacy compose names; `docker/entrypoint*.sh`; 3 `.example` templates; note 4 dead root stubs).
4. **What Lives Where** — unchanged.
5. **SSH Key Pairs** — unchanged.
6. **Stage A — One-time Server Preparation** — unchanged (4 secrets, `.env.docker` on VPS, TLS via certbot).
7. **Stage B — GitHub Configuration** — unchanged (production env + 4 secrets). Add note: OIDC requires no secret for GHCR.
8. **Stage C — GitHub Actions Workflow:**
   - §C1: CI split is `ci.yml + ci-nightly.yml` (NOT ci.yml + deploy.yml). Show the **real** `ci.yml` job list (build, test, lint, typecheck, lint-templates, i18n) + `ci-nightly.yml` (serial seed). Reference `test_docs_ci_parity.py` as the contract.
   - §C2: `deploy.yml` — **to be created** (full YAML with OIDC login, metadata-action, build-push `push:true`, deploy job with pull→backup→migrate→up→prune→health→rollback).
   - §C3: Corrected compose file names everywhere (`docker-compose.yml`, `docker-compose.prod.yml`).
   - §C4: Triggers table updated to include `ci-nightly.yml` schedule + `workflow_dispatch` for deploy.
   - §C5: `compose.prod.yaml` image overrides — mark ALREADY DONE.
   - §C6: `.env.docker` gitignored — mark ALREADY DONE.
   - §C7: Health endpoint — accurate.
9. **Stage E — Rollback Procedure** — accurate for manual SSH; automatic rollback is **part of the unbuilt deploy.yml** (reference plan §Stage C C9). Mark automatic-rollback as "to be implemented."
10. **Stage F — Verification Checklist** — split: CI parity (verify `test_docs_ci_parity.py` passes; concurrency/path filters present); CD (to verify once deploy.yml built).
11. **Stage G — Daily Release Process** — unchanged in shape (merge main → workflow_dispatch with `sha-{SHA}`) but mark "unblock: deploy.yml must be built first."
12. **Forward-looking Recommendations** — keep pip-audit + GitHub Releases + staging + Dependabot + OIDC + Trivy/gitleaks/zizmor. **Remove** the compose rename recommendation. Correct "Montenegrin" → Bosnian.
13. **Quick Reference** — 4 GitHub Secrets + `.env.docker` vars (use the real 11 from `.env.docker.example`) + SSH key + directory structure. Fix compose file names throughout.

### Shared corrections both updated docs must make

- **All `compose.*.yaml` → `docker-compose.*.yml`** (and `compose.dev.yaml` → `docker-compose.dev.override.yml`).
- **All "Montenegrin" language claims → Bosnian (`bs`)**; "Montenegro" retained only as launch geography/market.
- **All `research.md` §5.1 secret list → 4 server-only secrets.**
- **Mark already-implemented items as DONE** (compose.prod image overrides, rollback docs in `docker-deployment.md`, parity test, GHCR registry cache, 3-stage Dockerfile, fail-fast settings).
- **Add modern best practices** as advisory, explicitly non-mandatory, preserving the manual-deploy-to-VPS model.

---

## Appendix — Key File/Line Evidence

| Item | File:lines | Value |
|---|---|---|
| Compose file names (legacy, entrenched) | `Makefile:10–11` | `docker-compose.yml`, `docker-compose.dev.override.yml`, `docker-compose.test.yml` |
| Prod image override (GHCR) | `docker-compose.prod.yml:7–26` | `${REGISTRY:-ghcr.io}/${REPOSITORY:-manicko/mko_bazuna}:${IMAGE_TAG:-latest}` |
| CI workflow (2 files) | `.github/workflows/ci.yml:1–216`; `ci-nightly.yml:1–82` | 6 jobs + nightly; `build push:false` |
| CI build cache (registry) | `ci.yml:32–33` | `type=registry,ref=ghcr.io/manicko/mko_bazuna:buildcache` |
| CI test command contract | `ci.yml:111` | `-m "not seed" -n auto --dist loadgroup … --reuse-db` |
| Nightly seed command | `ci-nightly.yml:73` | `-m "seed"` (no xdist) |
| CI contract test | `src/backend/tests/test_docs_ci_parity.py:45–175` | asserts loadgroup/not-seed/reuse-db/makeclean-db |
| Test DB port (local) | `.kilo/rules/commands.md` (context) | PostgreSQL 18 on 5433 |
| `.env.docker` gitignored | `.gitignore:148` | `.env.docker` |
| Languages | `config/settings/base.py:69–73`; `apps/core/enums.py:187–192`; `Dockerfile:83` | ru/bs/en (Bosnian, not Montenegrin) |
| Fail-fast prod guards | `config/settings/prod.py:18–22,26–30,50–51`; `base.py:52` | BOT_TOKEN/SITE_URL/ALLOWED_HOSTS/DJANGO_SECRET_KEY |
| Dockerfile stages | `docker/Dockerfile:8,89,168` | builder / runtime / test-runtime; uid-1000 (`:102–106,149`); HEALTHCHECK `:154–155` |
| StrEnum count | `src/backend/apps/core/enums.py` + `apps/lookups/enums.py` + `apps/currencies/enums.py` | 18 StrEnum + 1 IntEnum = 19 enum classes |
| Makefile test targets | `Makefile:3,102,140,153` | `test-clean-db`, `test-recreate: test-clean-db`, seed-skip via `PYTEST_SKIP_MARKERS=seed` |
| Rollback docs location | `docs/ops/docker-deployment.md:788–876` | already merged (§Stage E) |
| 0-byte root stubs | repo root: `entrypoint.sh`, `entrypoint-test.sh`, `entrypoint-catalog.sh`, `entrypoint-seed.sh` | all 0 bytes |
| Real entrypoint scripts | `docker/entrypoint*.sh` (6 files) | `entrypoint.sh:3472`, `entrypoint-test.sh:2702`, `entrypoint-catalog.sh:493`, `entrypoint-seed.sh:1376`, `entrypoint-scheduler.sh:2066`, `entrypoint-create-admin.sh:838` |

---

*End of audit report. Written for consumption by the planner agent to produce `plan.md_updated.md` and `preparation-guide_updated.md`. This audit asserts observed reality and does not modify any production code, workflows, or configuration.*
