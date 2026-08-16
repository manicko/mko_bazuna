# Phase 02 Audit Findings — Configuration & Secrets Management (Validated)

**Executor:** audit-executor (original) / validator (validation)
**Template:** .kilo/commands/audit/phases/02-audit-config-secrets.md
**Source findings:** .ai/audit/02-config-secrets/findings.md
**Status:** complete
**Validated:** yes

Runtime verification performed host-side with the project .venv (Python 3.14 / Django 5.2.16 /
django-environ 0.14) under DJANGO_SETTINGS_MODULE = prod/test with env vars set and unset, plus
docker compose config (no running services required). Evidence sources re-verified: git ls-files,
git check-ignore, direct settings imports, and code inspection.

## Findings

### CFG-001: BOT_TOKEN silently defaults to empty in production; bot silently skips startup

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Code inspection + runtime re-verification confirm the finding. ase.py:49 reads BOT_TOKEN = env("BOT_TOKEN", default="") (empty default, no fail-fast). Runtime import of config.settings.prod with BOT_TOKEN unset returned BOT_TOKEN = '' without raising ImproperlyConfigured; django.setup() succeeded. By contrast, DJANGO_SECRET_KEY (base.py:42) and POSTGRES_PASSWORD (base.py:158) raise ImproperlyConfigured when unset — confirmed at runtime. main.py:25-30 checks if not token: and eturns (exits 0) with a WARNING; send_alerts.py:70-73 repeats this silent skip. The comment at main.py:23-24 falsely claims "missing/invalid token raises ImproperlyConfigured at django.setup()". docker compose config resolves BOT_TOKEN: "" for the ot service (sourced from .env.docker where BOT_TOKEN= is empty). All evidence verified.
> - **Recommendation confirmed:** Drop default="" or add if not BOT_TOKEN and not DEBUG: raise ImproperlyConfigured(...). Make the bot exit non-zero on missing token. Correct the misleading comment at main.py:23-24.

| Field | Value |
|-------|-------|
| **ID** | CFG-001 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION / BEST-PRACTICE |
| **Affected Modules** | src/backend/config/settings/base.py, src/telegram_bot/main.py, src/backend/apps/search/management/commands/send_alerts.py |
| **Classification** | mandatory |

**Description:** ase.py:49 reads BOT_TOKEN = env("BOT_TOKEN", default=""). In main.py:25-30 an
empty token is treated as "development mode": it logs a WARNING and returns (container exits 0)
instead of failing. send_alerts.py:70-73 repeats the silent skip for alert delivery. The
main.py:23-24 comment falsely documents that "missing/invalid token raises ImproperlyConfigured
at django.setup()".

**Evidence:** Importing config.settings.prod with BOT_TOKEN unset returns BOT_TOKEN = ''
(no error). docker compose config resolves BOT_TOKEN: "" in the ot service. Both
required-secret siblings fail fast (DJANGO_SECRET_KEY, POSTGRES_PASSWORD raise
ImproperlyConfigured), but BOT_TOKEN does not.

**Recommendation:** In production, require a non-empty BOT_TOKEN (drop the default="", or add an
explicit if not BOT_TOKEN and not DEBUG: raise ImproperlyConfigured(...) guard) and make the bot
process exit non-zero on a missing token. Correct the misleading comment. Effort: small.

---

### CFG-002: Compose silently falls back to literal weak placeholders for required secrets

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Code inspection confirms all cited :- defaults exist. docker-compose.yml:10-12 uses :-postgres for POSTGRES_DB/POSTGRES_USER/POSTGRES_PASSWORD; docker-compose.yml:36 and :60 use :-placeholder for DJANGO_SECRET_KEY; docker-compose.prod.yml:50 uses :-placeholder. A repo-wide grep for the fail-fast :? syntax returned zero matches across all .yml/.yaml files — no :? is used anywhere. Runtime docker compose config (with .env.docker loaded per the Makefile --env-file) resolves DJANGO_SECRET_KEY: <generate-with-django-secret-key-generator>, POSTGRES_PASSWORD: your-password, BOT_TOKEN: "" — all placeholder/literal values, with no boot failure. If .env.docker were absent entirely, the :- defaults would resolve to placeholder/postgres literals. The security impact (weak signing key, leading to session and CSRF forgery; weak DB password) is real.
> - **Recommendation confirmed:** Replace all :-placeholder/:-postgres with fail-fast :? syntax so a missing required secret fails the service boot with a clear error.

| Field | Value |
|-------|-------|
| **ID** | CFG-002 |
| **Severity** | HIGH |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | docker-compose.yml:36,60, docker-compose.prod.yml:50, docker-compose.yml:10-12 |
| **Classification** | mandatory |

**Description:** Required secret vars use :- defaults instead of fail-fast :?:
DJANGO_SECRET_KEY:  (yml:36,60; prod.yml:50) and
POSTGRES_PASSWORD:  / POSTGRES_USER: 
(yml:10-12, repeated in prod). When the var is absent the service boots with the literal string
placeholder as SECRET_KEY (known/weak, leading to session and CSRF forgery) or postgres as the
DB password.

**Evidence:** grep shows :-placeholder and :-postgres defaults. A repo-wide search for :? (fail-fast syntax) returns no matches in any compose file. docker compose config resolves DJANGO_SECRET_KEY: <generate-with-django-secret-key-generator> and BOT_TOKEN: "" — i.e. the shipped default config carries a placeholder signing key, not a real one, with no boot failure.

**Recommendation:** Replace :-placeholder/:-postgres with fail-fast :? syntax
(e.g. ${DJANGO_SECRET_KEY:?DJANGO_SECRET_KEY must be set}) so a missing required secret fails the
service boot with a clear error. Never default secret-bearing vars. Effort: trivial.

---

### CFG-003: Runtime secret source .env.docker is git-tracked, not gitignored, and docs instruct filling real values into it

> **Validation Note:**
> - **Action:** validated
> - **Detail:** git ls-files .env.docker returns .env.docker (tracked). git check-ignore .env.docker exits non-zero (NOT ignored). .gitignore:145-147 lists .env, .env.dev, .env.local but omits .env.docker. .dockerignore:5 uses .env* glob which DOES exclude .env.docker from the image build context, confirming the leak vector is VCS only (not the container image). Current .env.docker content contains only placeholders (no active leak). The ops docs at docker-deployment.md:78 acknowledge .env.docker is tracked ("Yes (template with placeholder values)") yet docker-deployment.md:165 instructs "edit .env.docker with your real values" and :267 instructs "Configure .env.docker with production values". The env-var reference table at docker-deployment.md:305-308 lists BOT_TOKEN, DJANGO_SECRET_KEY, POSTGRES_PASSWORD as required. This creates a documented flow that writes real secrets into a tracked file. All evidence verified.
> - **Recommendation confirmed:** Decouple the tracked template from runtime secrets — keep .env.docker as a tracked template, inject real secrets via a gitignored runtime file or orchestration environment, and add .env.docker-handling guidance to .gitignore/.dockerignore.

| Field | Value |
|-------|-------|
| **ID** | CFG-003 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | .env.docker, .gitignore:145-149, docker-compose.yml (all services env_file: .env.docker + ./.env.docker:/app/src/.env:ro), docs/ops/docker-deployment.md:165,267 |
| **Classification** | mandatory |

**Description:** .env.docker is BOTH the only runtime secret source (loaded by every service via
env_file: and bind-mounted as src/.env) AND a git-tracked file. .gitignore ignores .env,
.env.dev, .env.local but explicitly does NOT list .env.docker. The ops docs instruct operators
to "Configure .env.docker with your real values" (dev + prod). Any git add .env.docker after
filling real DJANGO_SECRET_KEY/BOT_TOKEN/POSTGRES_PASSWORD commits production secrets to VCS.

**Evidence:** git ls-files .env.docker shows it is tracked. git check-ignore .env.docker exits
1 (not ignored). Current content is placeholders only (no active leak), but the documented
deployment flow writes real secrets into this tracked file. .dockerignore correctly excludes
.env* from images (line 5), so the leak vector is VCS, not the image.

**Recommendation:** Decouple the tracked template from the runtime secret file: keep .env.docker
as a tracked template only, and inject real secrets via a gitignored runtime file (e.g. copy to a
gitignored .env) or via the orchestration environment. Add .env.docker-secrets-handling
guidance to .gitignore/.dockerignore. Effort: small.

---

### CFG-004: Scheduler entrypoint checks the wrong .env path; hourly sweeps never start

> **Validation Note:**
> - **Action:** validated
> - **Detail:** docker/entrypoint-scheduler.sh:8 checks ONLY if [ -z "" ] && [ ! -f "/app/.env" ], while the shared docker/entrypoint.sh:11-13 checks /app/src/.env first then falls back to /app/.env. The bind-mount olumes: ./.env.docker:/app/src/.env:ro (docker-compose.yml:41, docker-compose.prod.yml:54) places the secret file at /app/src/.env, NOT /app/.env. The scheduler service (docker-compose.prod.yml:38-60) sets no SKIP_ENV_CHECK and uses command: /app/entrypoint-scheduler.sh (prod.yml:42) with estart: unless-stopped (prod.yml:58). Therefore the path check fails (/app/.env absent), prints "ERROR: /app/.env file not found", exit 1, and crash-loops. The seven sweep management commands listed (lines 31-37 of the script) match the docs table docker-deployment.md:507-515. All evidence verified. Note: the finding text says "entrypoint:" at prod.yml:42 but the actual YAML key is command: — a minor terminology inaccuracy that does not affect the finding's validity.
> - **Recommendation confirmed:** Fix entrypoint-scheduler.sh:8 to check /app/src/.env (matching the bind-mount) or source the shared check_env_file function from entrypoint.sh.

| Field | Value |
|-------|-------|
| **ID** | CFG-004 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | docker/entrypoint-scheduler.sh:8, docker/entrypoint.sh:10-14, docker-compose.prod.yml:42,53-54 |
| **Classification** | mandatory |

**Description:** docker/entrypoint.sh (used by web/ot ENTRYPOINT) checks /app/src/.env
first, then /app/.env. The scheduler uses a different script, docker/entrypoint-scheduler.sh:8,
which checks ONLY /app/.env — a path that is never created. The bind-mount
olumes: ./.env.docker:/app/src/.env:ro (prod.yml:54) lands the secret file at /app/src/.env,
not /app/.env. The scheduler service sets no SKIP_ENV_CHECK.

**Evidence:** docker compose config for the scheduler shows olumes:
./.env.docker:/app/src/.env:ro and entrypoint: /app/entrypoint-scheduler.sh. Reading
entrypoint-scheduler.sh shows if [ -z "" ] && [ ! -f "/app/.env" ] evaluates to
true (because /app/.env is absent), prints "ERROR: /app/.env file not found", then exit 1. With
estart: unless-stopped (prod.yml:58) this is a crash loop.

**Consequence:** When deployed with --profile scheduler, the hourly sweeps (rchive_sweep,
delete_sweep, consent_hard_delete, sweep_drafts, cleanup_login_tokens,
purge_failed_ads, purge_rejected_ads) never execute until the path check is fixed.

**Recommendation:** Fix entrypoint-scheduler.sh to check /app/src/.env (match the bind-mount)
or source the shared check from entrypoint.sh. Effort: trivial.

---

### CFG-005: No config/secret-loading tests; missing-secret rejection behavior is untested

> **Validation Note:**
> - **Action:** validated
> - **Detail:** conftest.py:10-15 unconditionally stamps placeholder DJANGO_SECRET_KEY/BOT_TOKEN defaults so the suite boots. pytest --collect-only -q lists app-level test modules only (ads, analytics, core, media, moderation, search, seed, trust, users, telegram_bot) — no settings/config/secret test module exists. A grep for ImproperlyConfigured across 	ests/** returns zero matches. The only SECRET_KEY/BOT_TOKEN references in 	ests/ are in conftest.py (root, sets defaults) and 	elegram_bot/tests/conftest.py:30 (uses settings.BOT_TOKEN as a Bot constructor argument, not a test of rejection behavior). No test asserts that missing DJANGO_SECRET_KEY raises ImproperlyConfigured or that the per-environment BOT_TOKEN policy behaves as intended. Runtime verification (CFG-001 evidence) confirmed DJANGO_SECRET_KEY missing raises ImproperlyConfigured, proving there is a testable contract to assert. All evidence verified.
> - **Recommendation confirmed:** Add a SimpleTestCase asserting ImproperlyConfigured for absent DJANGO_SECRET_KEY, and a test pinning the per-environment BOT_TOKEN policy.

| Field | Value |
|-------|-------|
| **ID** | CFG-005 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | conftest.py:10-15 (sets defaults instead of asserting), no settings/config test module |
| **Classification** | advisory |

**Description:** conftest.py unconditionally stamps placeholder DJANGO_SECRET_KEY/BOT_TOKEN
defaults so the suite can boot; no test asserts that a missing required secret raises
ImproperlyConfigured, nor that BOT_TOKEN empty handling is intentional per-environment. The
rejection behavior verified manually in R2 (CFG-001/002) has no CI guard.

**Evidence:** pytest --collect-only -q lists app-level test modules only; grep for
SECRET_KEY|BOT_TOKEN|ImproperlyConfigured across **/tests/** returns matches in conftest.py
only. 	est_context_processors.py passes (4/4) — it does not cover settings.

**Recommendation:** Add a SimpleTestCase asserting ImproperlyConfigured is raised when
DJANGO_SECRET_KEY is absent, and a test pinning the per-environment BOT_TOKEN policy.
Effort: small.

---

### CFG-006: Docs claim test DEBUG=False; code sets DEBUG=True (and test HSTS still differs from dev)

> **Validation Note:**
> - **Action:** validated (primary type: DOC-UPDATE; code is correct/intentional)
> - **Detail:** Per the SPEC-DEVIATION reclassification rule ("if code is better than docs, reclassify as DOC-UPDATE"), the code is the correct, intentional behavior: 	est.py:9 sets DEBUG = True with an explicit adjacent comment "test settings must behave like dev, not prod" (test.py:14). The documentation at docker-deployment.md:396 table shows DEBUG | True | False (Dev=True, Test=False) — this is stale. Runtime import of config.settings.test confirms DEBUG=True, SECURE_HSTS_SECONDS=3600, SECURE_HSTS_INCLUDE_SUBDOMAINS=True (inherited from base.py:73-74). dev.py:31-32 sets SECURE_HSTS_SECONDS=0 / SECURE_HSTS_INCLUDE_SUBDOMAINS=False. The docs table does not mention HSTS, so the HSTS inconsistency is a code-consistency observation (test inherits base HSTS while dev zeroes it), not a doc discrepancy. The code choice is reasonable for richer test failures. All evidence verified.
> - **Recommendation confirmed:** Update the docs table at docker-deployment.md:396 to DEBUG = True for Test. Optionally align test HSTS to   if "behave like dev" is the strict goal.

| Field | Value |
|-------|-------|
| **ID** | CFG-006 |
| **Severity** | LOW |
| **Type** | DOC-UPDATE / SPEC-DEVIATION |
| **Affected Modules** | docs/ops/docker-deployment.md:396, src/backend/config/settings/test.py:9 |
| **Classification** | advisory |

**Description:** The ops architecture-comparison table states Test DEBUG = False, but
	est.py:9 sets DEBUG = True (intentional per the adjacent comment: "test settings must behave
like dev, not prod"). Test also retains base's SECURE_HSTS_SECONDS = 3600 and
SECURE_HSTS_INCLUDE_SUBDOMAINS = True, whereas dev.py sets HSTS to   / False. The code
choice is reasonable (richer test failures); the documentation is stale.

**Evidence:** Import config.settings.test -> DEBUG=True, SECURE_HSTS_SECONDS=3600,
SECURE_HSTS_INCLUDE_SUBDOMAINS=True. Doc table row: DEBUG | True | False.

**Recommendation:** Update the docs table to DEBUG = True for Test. If "behave like dev" is the
goal, also align test HSTS to  . Effort: trivial.

---

### CFG-007: Dead zero-byte root entrypoint stubs are git-tracked and unused

> **Validation Note:**
> - **Action:** validated
> - **Detail:** git ls-files entrypoint*.sh returns 4 root stubs: entrypoint-catalog.sh, entrypoint-seed.sh, entrypoint-test.sh, entrypoint.sh. git cat-file -s HEAD:<name> returns   for all four (confirmed via repo inspection). Get-Item confirms 0 bytes on disk for all four. The real scripts live in docker/entrypoint*.sh (entrypoint.sh=1654B, entrypoint-catalog.sh=201B, entrypoint-seed.sh=211B, entrypoint-test.sh=1540B, entrypoint-scheduler.sh=1549B, entrypoint-create-admin.sh=546B). The Dockerfile (line 121) copies docker/entrypoint*.sh (NOT root stubs) into /app/. All compose references (.yml base, .dev.override.yml, .test.yml) use /app/entrypoint*.sh or ./docker/entrypoint*.sh — never the root-level stubs. In dev, the .:/app bind-mount would expose root stubs at /app/entrypoint*.sh, but the dev override explicitly re-bind-mounts ./docker/entrypoint*.sh:/app/entrypoint*.sh (dev.override.yml:22,33,40,53) which override them. The root stubs are harmless but confusing dead code. All evidence verified.
> - **Recommendation confirmed:** Delete the 4 root stubs. Deletion is safe — they are never referenced in the Dockerfile COPY or any compose file.

| Field | Value |
|-------|-------|
| **ID** | CFG-007 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | ./entrypoint.sh, ./entrypoint-catalog.sh, ./entrypoint-seed.sh, ./entrypoint-test.sh (all 0 bytes), docker/entrypoint*.sh (real) |
| **Classification** | advisory |

**Description:** The repository root contains four 0-byte entrypoint*.sh stubs that are
git-tracked but never referenced — docker-compose.yml resolves entrypoints to /app/entrypoint*.sh
(copied from docker/entrypoint*.sh by the Dockerfile L121, optionally overridden by
./docker/entrypoint*.sh bind-mounts in the dev override). The real scripts live in docker/.

**Evidence:** git ls-files entrypoint*.sh -> 4 root stubs tracked; Get-Item -> 0 bytes each;
grep entrypoint in docker-compose.yml -> matches are /app/entrypoint-catalog.sh (line 49) etc.

**Recommendation:** Delete the root stubs (or clarify they are intentionally empty) to avoid
confusion about which entrypoint actually runs. Effort: trivial.

---

## Cross-Finding Analysis

| Aspect | Finding A | Finding B | Assessment |
|--------|-----------|-----------|------------|
| Root cause overlap | CFG-001 | CFG-003 | Related but distinct. CFG-003 is about the tracked secret file; CFG-001 is about the runtime silent-skip when the token is empty. No merge warranted. |
| Root cause overlap | CFG-002 | CFG-003 | Related but distinct. CFG-002 is about compose :- defaults; CFG-003 is about the git-tracked .env.docker file. No merge warranted. |
| Complementary controls | CFG-001 | CFG-002 | Complementary: CFG-002 makes the Compose layer fail-fast on missing secrets; CFG-001 makes the Django settings + bot process fail-fast on missing BOT_TOKEN. Together they provide defense-in-depth. |
| Dependency chain | CFG-004 | CFG-003 | The scheduler bind-mount path (./.env.docker:/app/src/.env:ro) is the root cause of the path mismatch in CFG-004. If CFG-003 changes the secret injection mechanism, the bind-mount target must remain consistent with entrypoint-scheduler.sh's check. Fixes are independent but must stay coherent. |
| Conflicting evidence | None | None | No cross-phase conflicts detected. No finding contradicts another. |
| Circular dependency | None | — | None detected. Each fix is self-contained. |

## Rollout Safety Assessment

| Finding | Rollout risk | Notes |
|---------|-------------|-------|
| CFG-001 | Medium | Changing BOT_TOKEN to fail-fast in production will cause the ot container to exit non-zero if the token is missing. Operators relying on the current silent skip (e.g. web-only deployments) must set BOT_TOKEN or use DEBUG=True. Backward-compatible only if gated on DEBUG. |
| CFG-002 | High | Switching :- to :? makes Compose fail-fast on any missing secret at config/parse time. Any deployment relying on placeholder defaults (e.g. quick local bootstrap with .env.docker placeholders) will break. Requires coordinated rollout with secret provisioning. |
| CFG-003 | High | gitignoring .env.docker changes the secret injection mechanism. Deployment scripts, Makefile targets, and CI/CD must source secrets from the new gitignored runtime file or orchestration env. Highest operational coordination burden. Should be sequenced AFTER or TOGETHER with CFG-002. |
| CFG-004 | Low | Path fix in a shell script; no schema or behavioral change. estart: unless-stopped means the current crash-loop stops. Safe to deploy independently. |
| CFG-005 | Trivial | New test cases only; no production impact. |
| CFG-006 | Trivial | Documentation update only; no code or config change. |
| CFG-007 | Trivial | Deleting 0-byte files that are never referenced; no runtime impact. |

**Recommended rollout sequencing:**
1. Phase 1 (low-risk, independent): CFG-004 (path fix), CFG-006 (docs), CFG-007 (stub deletion), CFG-005 (tests).
2. Phase 2 (coordinated secrets hardening): CFG-002 (compose :? fail-fast) + CFG-003 (gitignore .env.docker, inject via runtime file or orchestrator env). Apply together to avoid a window where secrets are required but not provisioned.
3. Phase 3 (runtime guard): CFG-001 (settings-level BOT_TOKEN guard + bot non-zero exit + comment fix). Apply after Phase 2 so the fail-fast behavior is consistent across layers.

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 7 | CFG-001, CFG-002, CFG-003, CFG-004, CFG-005, CFG-006, CFG-007 |
| Reclassified | 0 | — |
| Merged | 0 | — |
| Rejected | 0 | — |

### Rejected Findings

*(none — all 7 findings validated against code, runtime, and documentation)*

### Merged Findings

*(none — all 7 findings address distinct root causes)*

### Reclassified Findings

*(none — all 7 findings retain their original or dual classification)*

## Warnings

- **Secret fail-fast behavior change (CFG-001 + CFG-002):** Once both are applied, any deployment with missing or placeholder secrets will fail at boot rather than silently degrading. This is the desired security posture but is a breaking change for deployments currently relying on the silent fallback. Operators must provision real secrets before deploying.
- **.env.docker tracking (CFG-003):** The file is currently tracked with placeholder values and no active leak. However, the documented deployment flow (docs:165, 267) instructs operators to fill real secrets into it. The window of risk grows with each deployment.
- **Scheduler crash-loop (CFG-004):** The scheduler profile service is currently in a crash-loop when enabled. All scheduled sweep tasks (archive/delete/consent/draft sweep/login-token cleanup/purge-failed/purge-rejected) are suspended until fixed.
- **No CI guard for secret rejection (CFG-005):** The fail-fast behavior of DJANGO_SECRET_KEY/POSTGRES_PASSWORD (verified at runtime) has no automated test. A future refactor could silently regress this.
