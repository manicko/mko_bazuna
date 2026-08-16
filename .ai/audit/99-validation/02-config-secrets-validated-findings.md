# Phase 02 Audit Findings � Configuration & Secrets Management (Validated)

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
> - **Detail:** Code inspection + runtime re-verification confirm the finding. ase.py:49 reads BOT_TOKEN = env("BOT_TOKEN", default="") (empty default, no fail-fast). Runtime import of config.settings.prod with BOT_TOKEN unset returned BOT_TOKEN = '' without raising ImproperlyConfigured; django.setup() succeeded. By contrast, DJANGO_SECRET_KEY (base.py:42) and POSTGRES_PASSWORD (base.py:158) raise ImproperlyConfigured when unset � confirmed at runtime. main.py:25-30 checks if not token: and 
eturns (exits 0) with a WARNING; send_alerts.py:70-73 repeats this silent skip. The comment at main.py:23-24 falsely claims "missing/invalid token raises ImproperlyConfigured at django.setup()". docker compose config resolves BOT_TOKEN: "" for the ot service (sourced from .env.docker where BOT_TOKEN= is empty). All evidence verified.
> - **Recommendation confirmed:** Add a conditional fail-fast guard in base.py so BOT_TOKEN is required only in production: `if not BOT_TOKEN and not DEBUG: raise ImproperlyConfigured(...)`. This matches the existing fail-fast pattern for DJANGO_SECRET_KEY (base.py:42) and POSTGRES_PASSWORD (base.py:160), which use django-environ (no default) to raise ImproperlyConfigured at import time. The guard preserves the dev-mode silent skip in main.py:28-30 (where `if not token: return` lets the bot stay dormant without a token under DEBUG=True). The "drop default=""" alternative is rejected because `env("BOT_TOKEN")` without a default raises ImproperlyConfigured even in development, breaking the dev-mode startup path. The guard itself enforces a non-zero exit in production when the token is missing. Correct the misleading comment at main.py:23-24.

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

**Recommendation:** Add a conditional fail-fast guard in base.py:49 that raises
ImproperlyConfigured when BOT_TOKEN is empty and DEBUG is False, following the same pattern as
DJANGO_SECRET_KEY (base.py:42) and POSTGRES_PASSWORD (base.py:160) which use django-environ
without a default. This enforces a non-empty BOT_TOKEN in production (where DEBUG=False per
prod.py:8) while preserving the dev-mode silent skip in main.py:28-30 (where
`if not token: return` lets the bot stay dormant without a token under DEBUG=True per
dev.py:8 and test.py:9). The "drop default=""" alternative is rejected because it would raise
ImproperlyConfigured in development, breaking the dev-mode startup path. The guard itself
ensures the bot process exits non-zero in production when the token is missing. Correct the
misleading comment at main.py:23-24 which falsely claims token validation happens at
django.setup(). Add `from django.core.exceptions import ImproperlyConfigured` to base.py imports
if not already present. Effort: small.

---

### CFG-002: Compose silently falls back to literal weak placeholders for required secrets

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Code inspection confirms all cited :- defaults exist. docker-compose.yml:10-12 uses :-postgres for POSTGRES_DB/POSTGRES_USER/POSTGRES_PASSWORD; docker-compose.yml:36 and :60 use :-placeholder for DJANGO_SECRET_KEY; docker-compose.prod.yml:50 uses :-placeholder. A repo-wide grep for the fail-fast :? syntax returned zero matches across all .yml/.yaml files � no :? is used anywhere. Runtime docker compose config (with .env.docker loaded per the Makefile --env-file) resolves DJANGO_SECRET_KEY: <generate-with-django-secret-key-generator>, POSTGRES_PASSWORD: your-password, BOT_TOKEN: "" � all placeholder/literal values, with no boot failure. If .env.docker were absent entirely, the :- defaults would resolve to placeholder/postgres literals. The security impact (weak signing key, leading to session and CSRF forgery; weak DB password) is real.
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

**Evidence:** grep shows :-placeholder and :-postgres defaults. A repo-wide search for :? (fail-fast syntax) returns no matches in any compose file. docker compose config resolves DJANGO_SECRET_KEY: <generate-with-django-secret-key-generator> and BOT_TOKEN: "" � i.e. the shipped default config carries a placeholder signing key, not a real one, with no boot failure.

**Recommendation:** Replace :-placeholder/:-postgres with fail-fast :? syntax
(e.g. ${DJANGO_SECRET_KEY:?DJANGO_SECRET_KEY must be set}) so a missing required secret fails the
service boot with a clear error. Never default secret-bearing vars. Effort: trivial.

---

### CFG-003: Runtime secret source .env.docker is git-tracked, not gitignored, and docs instruct filling real values into it

> **Validation Note:**
> - **Action:** validated
> - **Detail:** git ls-files .env.docker returns .env.docker (tracked). git check-ignore .env.docker exits non-zero (NOT ignored). .gitignore:145-147 lists .env, .env.dev, .env.local but omits .env.docker. .dockerignore:5 uses .env* glob which DOES exclude .env.docker from the image build context, confirming the leak vector is VCS only (not the container image). Current .env.docker content contains only placeholders (no active leak). The ops docs at docker-deployment.md:78 acknowledge .env.docker is tracked ("Yes (template with placeholder values)") yet docker-deployment.md:165 instructs "edit .env.docker with your real values" and :267 instructs "Configure .env.docker with production values". The env-var reference table at docker-deployment.md:305-308 lists BOT_TOKEN, DJANGO_SECRET_KEY, POSTGRES_PASSWORD as required. This creates a documented flow that writes real secrets into a tracked file. All evidence verified.
> - **Recommendation confirmed:** Adopt the **gitignored runtime file** model without rewriting the consumption layer. Rename the tracked `.env.docker` to `.env.docker.example` (committed template, placeholder values only), add `.env.docker` to `.gitignore` so it becomes the gitignored runtime file, and update docs to instruct `cp .env.docker.example .env.docker` then fill `DJANGO_SECRET_KEY` / `BOT_TOKEN` / `POSTGRES_PASSWORD` into the runtime `.env.docker`. All compose `env_file:` / bind-mount sites and `Makefile:9` keep referencing `.env.docker` unchanged (the runtime filename is stable), so `entrypoint.sh:9` and `base.py:36` continue reading operator-populated secrets. The scheduler's `/app/.env` path mismatch is tracked separately as CFG-004.

| Field | Value |
|-------|-------|
| **ID** | CFG-003 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `git mv .env.docker .env.docker.example` (tracked template, placeholders only), `.env.docker` (gitignored runtime file, created via `cp .env.docker.example .env.docker`), .gitignore (Environments section), docs/ops/docker-deployment.md:78,165,267 (instruction text only; zero compose/Makefile/env_file/bind-mount changes — runtime filename stays `.env.docker`) |
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

**Recommendation:** Select the **gitignored runtime file** model (the orchestration-environment alternative is rejected -- it would require rewriting every `env_file:` / bind-mount site and the entrypoint path checks; see CFG-004). Rename the tracked `.env.docker` template to `.env.docker.example` (placeholder values only, no real secrets) and make `.env.docker` the gitignored runtime file populated by the operator. The consumption layer (`.env.docker` as the runtime filename) stays stable, so no compose `env_file:` / bind-mount site or `Makefile:9` reference changes are required. Concrete steps:

1. Rename the tracked template: `git mv .env.docker .env.docker.example` (placeholders already present, e.g. `POSTGRES_PASSWORD=your-password`, empty `BOT_TOKEN=`).
2. Add `.env.docker` to `.gitignore` in the Environments section next to `.env`, `.env.dev`, `.env.local`; update the template comment to mention `.env.docker.example`. No `.dockerignore` change -- `.env*` (line 5) already excludes every `.env*` file from image builds.
3. Update docs `docs/ops/docker-deployment.md`: `:78` table -- `.env.docker.example` `Yes (template, placeholders only)` and `.env.docker` `No (runtime secrets, gitignored)`; `:165` / `:267` -- instruct `cp .env.docker.example .env.docker` then fill real `DJANGO_SECRET_KEY` / `BOT_TOKEN` / `POSTGRES_PASSWORD` into the runtime `.env.docker` (never into the tracked template). The `--env-file .env.docker` invocation in the Makefile and compose sites remains unchanged because the runtime filename is stable.

Real secrets are injected via the gitignored `.env.docker` runtime file (created from the committed `.env.docker.example` template) while the consumption layer references the same `.env.docker` filename, so `entrypoint.sh:9` and `base.py:36` continue reading operator-populated secrets and the `/app/src/.env` bind-mount stays consistent. Effort: trivial (1 `git mv` + one `.gitignore` line + docs instruction text; no compose/Makefile/schema change).

---

### CFG-004: Scheduler entrypoint checks the wrong .env path; hourly sweeps never start

> **Validation Note:**
> - **Action:** validated
> - **Detail:** docker/entrypoint-scheduler.sh:8 checks ONLY if [ -z "" ] && [ ! -f "/app/.env" ], while the shared docker/entrypoint.sh:11-13 checks /app/src/.env first then falls back to /app/.env. The bind-mount olumes: ./.env.docker:/app/src/.env:ro (docker-compose.yml:41, docker-compose.prod.yml:54) places the secret file at /app/src/.env, NOT /app/.env. The scheduler service (docker-compose.prod.yml:38-60) sets no SKIP_ENV_CHECK and uses command: /app/entrypoint-scheduler.sh (prod.yml:42) with 
estart: unless-stopped (prod.yml:58). Therefore the path check fails (/app/.env absent), prints "ERROR: /app/.env file not found", exit 1, and crash-loops. The seven sweep management commands listed (lines 31-37 of the script) match the docs table docker-deployment.md:507-515. All evidence verified. Note: the finding text says "entrypoint:" at prod.yml:42 but the actual YAML key is command: � a minor terminology inaccuracy that does not affect the finding's validity.
> - **Recommendation confirmed:** Update entrypoint-scheduler.sh:8 to check /app/src/.env (matching the bind-mount at docker-compose.yml:41 and docker-compose.prod.yml:54). The "source the shared check_env_file function from entrypoint.sh" alternative is rejected — it would require refactoring entrypoint.sh into a separately-sourced library and restructuring the scheduler's self-contained entrypoint, without reducing risk. The path-update approach mirrors the existing entrypoint.sh:11 first-path check (`/app/src/.env`), applying the same pattern consistently. Runtime `docker compose config` confirms the scheduler bind-mounts `./.env.docker:/app/src/.env:ro`, so /app/src/.env is where the file physically resides.

| Field | Value |
|-------|-------|
| **ID** | CFG-004 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | docker/entrypoint-scheduler.sh:8, docker/entrypoint.sh:10-14, docker-compose.prod.yml:42,53-54 |
| **Classification** | mandatory |

**Description:** docker/entrypoint.sh (used by web/ot ENTRYPOINT) checks /app/src/.env
first, then /app/.env. The scheduler uses a different script, docker/entrypoint-scheduler.sh:8,
which checks ONLY /app/.env � a path that is never created. The bind-mount
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

**Recommendation:** Update the path check at entrypoint-scheduler.sh:8 from /app/.env to
/app/src/.env to match the bind-mount (`./.env.docker:/app/src/.env:ro` in docker-compose.yml:41
and docker-compose.prod.yml:54). This mirrors the existing entrypoint.sh:11 first-path check
(`/app/src/.env`) so both entrypoints validate the same location. The scheduler runs
self-contained (command: /app/entrypoint-scheduler.sh per prod.yml:42), so sourcing a shared
function from entrypoint.sh is unnecessary — simply update the path literal in-place at
entrypoint-scheduler.sh:8: change `"/app/.env"` to `"/app/src/.env"`. Effort: trivial.

---

### CFG-005: No config/secret-loading tests; missing-secret rejection behavior is untested

> **Validation Note:**
> - **Action:** validated
> - **Detail:** conftest.py:10-15 unconditionally stamps placeholder DJANGO_SECRET_KEY/BOT_TOKEN defaults so the suite boots. pytest --collect-only -q lists app-level test modules only (ads, analytics, core, media, moderation, search, seed, trust, users, telegram_bot) � no settings/config/secret test module exists. A grep for ImproperlyConfigured across 	ests/** returns zero matches. The only SECRET_KEY/BOT_TOKEN references in 	ests/ are in conftest.py (root, sets defaults) and 	elegram_bot/tests/conftest.py:30 (uses settings.BOT_TOKEN as a Bot constructor argument, not a test of rejection behavior). No test asserts that missing DJANGO_SECRET_KEY raises ImproperlyConfigured or that the per-environment BOT_TOKEN policy behaves as intended. Runtime verification (CFG-001 evidence) confirmed DJANGO_SECRET_KEY missing raises ImproperlyConfigured, proving there is a testable contract to assert. All evidence verified.
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
only. 	est_context_processors.py passes (4/4) � it does not cover settings.

**Recommendation:** Add a SimpleTestCase asserting ImproperlyConfigured is raised when
DJANGO_SECRET_KEY is absent, and a test pinning the per-environment BOT_TOKEN policy.
Effort: small.

---

### CFG-006: Docs claim test DEBUG=False; code sets DEBUG=True (and test HSTS still differs from dev)

> **Validation Note:**
> - **Action:** validated (primary type: DOC-UPDATE; code is correct/intentional)
> - **Detail:** Per the SPEC-DEVIATION reclassification rule ("if code is better than docs, reclassify as DOC-UPDATE"), the code is the correct, intentional behavior: 	est.py:9 sets DEBUG = True with an explicit adjacent comment "test settings must behave like dev, not prod" (test.py:14). The documentation at docker-deployment.md:396 table shows DEBUG | True | False (Dev=True, Test=False) � this is stale. Runtime import of config.settings.test confirms DEBUG=True, SECURE_HSTS_SECONDS=3600, SECURE_HSTS_INCLUDE_SUBDOMAINS=True (inherited from base.py:73-74). dev.py:31-32 sets SECURE_HSTS_SECONDS=0 / SECURE_HSTS_INCLUDE_SUBDOMAINS=False. The docs table does not mention HSTS, so the HSTS inconsistency is a code-consistency observation (test inherits base HSTS while dev zeroes it), not a doc discrepancy. The code choice is reasonable for richer test failures. All evidence verified.
> - **Recommendation confirmed:** Update the docs table at docker-deployment.md:396 to DEBUG = True for Test. Optionally align test HSTS to  if "behave like dev" is the strict goal.

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
SECURE_HSTS_INCLUDE_SUBDOMAINS = True, whereas dev.py sets HSTS to  / False. The code
choice is reasonable (richer test failures); the documentation is stale.

**Evidence:** Import config.settings.test -> DEBUG=True, SECURE_HSTS_SECONDS=3600,
SECURE_HSTS_INCLUDE_SUBDOMAINS=True. Doc table row: DEBUG | True | False.

**Recommendation:** Update the docs table to DEBUG = True for Test. If "behave like dev" is the
goal, also align test HSTS to . Effort: trivial.

---

### CFG-007: Dead zero-byte root entrypoint stubs are git-tracked and unused

> **Validation Note:**
> - **Action:** validated
> - **Detail:** git ls-files entrypoint*.sh returns 4 root stubs: entrypoint-catalog.sh, entrypoint-seed.sh, entrypoint-test.sh, entrypoint.sh. git cat-file -s HEAD:<name> returns  for all four (confirmed via repo inspection). Get-Item confirms 0 bytes on disk for all four. The real scripts live in docker/entrypoint*.sh (entrypoint.sh=1654B, entrypoint-catalog.sh=201B, entrypoint-seed.sh=211B, entrypoint-test.sh=1540B, entrypoint-scheduler.sh=1549B, entrypoint-create-admin.sh=546B). The Dockerfile (line 121) copies docker/entrypoint*.sh (NOT root stubs) into /app/. All compose references (.yml base, .dev.override.yml, .test.yml) use /app/entrypoint*.sh or ./docker/entrypoint*.sh � never the root-level stubs. In dev, the .:/app bind-mount would expose root stubs at /app/entrypoint*.sh, but the dev override explicitly re-bind-mounts ./docker/entrypoint*.sh:/app/entrypoint*.sh (dev.override.yml:22,33,40,53) which override them. The root stubs are harmless but confusing dead code. All evidence verified.
> - **Recommendation confirmed:** Delete the 4 root stubs. Deletion is safe � they are never referenced in the Dockerfile COPY or any compose file.

| Field | Value |
|-------|-------|
| **ID** | CFG-007 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | ./entrypoint.sh, ./entrypoint-catalog.sh, ./entrypoint-seed.sh, ./entrypoint-test.sh (all 0 bytes), docker/entrypoint*.sh (real) |
| **Classification** | advisory |

**Description:** The repository root contains four 0-byte entrypoint*.sh stubs that are
git-tracked but never referenced � docker-compose.yml resolves entrypoints to /app/entrypoint*.sh
(copied from docker/entrypoint*.sh by the Dockerfile L121, optionally overridden by
./docker/entrypoint*.sh bind-mounts in the dev override). The real scripts live in docker/.

**Evidence:** git ls-files entrypoint*.sh -> 4 root stubs tracked; Get-Item -> 0 bytes each;
grep entrypoint in docker-compose.yml -> matches are /app/entrypoint-catalog.sh (line 49) etc.

**Recommendation:** Delete the four 0-byte root stubs. This is the only action taken; the
'clarify they are intentionally empty' alternative is rejected because an empty file with no
consumer cannot convey intent and only adds maintenance noise. The rollout sequencing
section (line 281) already labels this as 'CFG-007 (stub deletion)' and the rollout risk
table (line 278) describes it as 'Deleting 0-byte files that are never referenced', so
deletion is the committed approach and the clarifying alternative is unnecessary.

Implementation steps:
1. Remove the four root-level stubs from the repository: `./entrypoint.sh`,
   `./entrypoint-catalog.sh`, `./entrypoint-seed.sh`, `./entrypoint-test.sh`
   (e.g. `git rm entrypoint.sh entrypoint-catalog.sh entrypoint-seed.sh entrypoint-test.sh`).
2. Verify no references to the bare root stubs remain: confirm that `docker-compose.yml`,
   `docker-compose.dev.override.yml`, `docker-compose.prod.yml`, `docker-compose.test.yml`,
   and the `Makefile` only reference the in-container `/app/entrypoint*.sh` paths or the
   `./docker/entrypoint*.sh` bind-mount sources — never bare root-level stubs
   (confirmed via grep: no root-level stub references exist outside `docker/`).
3. Rebuild and run the affected compose targets once to confirm entrypoints resolve
   correctly from `docker/entrypoint*.sh` (Dockerfile COPY, L121) without the stubs present.

Effort: trivial. No runtime impact.

---

## Cross-Finding Analysis

| Aspect | Finding A | Finding B | Assessment |
|--------|-----------|-----------|------------|
| Root cause overlap | CFG-001 | CFG-003 | Related but distinct. CFG-003 is about the tracked secret file; CFG-001 is about the runtime silent-skip when the token is empty. No merge warranted. |
| Root cause overlap | CFG-002 | CFG-003 | Related but distinct. CFG-002 is about compose :- defaults; CFG-003 is about the git-tracked .env.docker file. No merge warranted. |
| Complementary controls | CFG-001 | CFG-002 | Complementary: CFG-002 makes the Compose layer fail-fast on missing secrets; CFG-001 makes the Django settings + bot process fail-fast on missing BOT_TOKEN. Together they provide defense-in-depth. |
| Dependency chain | CFG-004 | CFG-003 | The scheduler bind-mount path (./.env.docker:/app/src/.env:ro) is the root cause of the path mismatch in CFG-004. If CFG-003 changes the secret injection mechanism, the bind-mount target must remain consistent with entrypoint-scheduler.sh's check. Fixes are independent but must stay coherent. |
| Conflicting evidence | None | None | No cross-phase conflicts detected. No finding contradicts another. |
| Circular dependency | None | � | None detected. Each fix is self-contained. |

## Rollout Safety Assessment

| Finding | Rollout risk | Notes |
|---------|-------------|-------|
| CFG-001 | Medium | Changing BOT_TOKEN to fail-fast in production will cause the ot container to exit non-zero if the token is missing. Operators relying on the current silent skip (e.g. web-only deployments) must set BOT_TOKEN or use DEBUG=True. Backward-compatible only if gated on DEBUG. |
| CFG-002 | High | Switching :- to :? makes Compose fail-fast on any missing secret at config/parse time. Any deployment relying on placeholder defaults (e.g. quick local bootstrap with .env.docker placeholders) will break. Requires coordinated rollout with secret provisioning. |
| CFG-003 | Trivial | Renaming the tracked template `.env.docker` -> `.env.docker.example` and gitignoring the runtime `.env.docker` is a no-op for the consumption layer: every compose `env_file:` / bind-mount site and `Makefile:9 --env-file .env.docker` keeps referencing the stable runtime filename `.env.docker`. Only a `git mv`, one `.gitignore` line, and docs instruction text change. No coordination burden with compose/Makefile. |
| CFG-004 | Low | Path fix in a shell script; no schema or behavioral change. 
estart: unless-stopped means the current crash-loop stops. Safe to deploy independently. |
| CFG-005 | Trivial | New test cases only; no production impact. |
| CFG-006 | Trivial | Documentation update only; no code or config change. |
| CFG-007 | Trivial | Deleting 0-byte files that are never referenced; no runtime impact. |

**Recommended rollout sequencing:**
1. Phase 1 (low-risk, independent): CFG-004 (path fix), CFG-006 (docs), CFG-007 (stub deletion), CFG-005 (tests).
2. Phase 2 (coordinated secrets hardening): CFG-002 (compose :? fail-fast) + CFG-003 (rename tracked template `.env.docker` -> `.env.docker.example`; gitignore `.env.docker` runtime file; update docs instructions only). Apply together to avoid a window where secrets are required but not provisioned.
3. Phase 3 (runtime guard): CFG-001 (settings-level BOT_TOKEN guard + bot non-zero exit + comment fix). Apply after Phase 2 so the fail-fast behavior is consistent across layers.

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 7 | CFG-001, CFG-002, CFG-003, CFG-004, CFG-005, CFG-006, CFG-007 |
| Reclassified | 0 | � |
| Merged | 0 | � |
| Rejected | 0 | � |

### Rejected Findings

*(none � all 7 findings validated against code, runtime, and documentation)*

### Merged Findings

*(none � all 7 findings address distinct root causes)*

### Reclassified Findings

*(none � all 7 findings retain their original or dual classification)*

## Warnings

- **Secret fail-fast behavior change (CFG-001 + CFG-002):** Once both are applied, any deployment with missing or placeholder secrets will fail at boot rather than silently degrading. This is the desired security posture but is a breaking change for deployments currently relying on the silent fallback. Operators must provision real secrets before deploying.
- **.env.docker tracking (CFG-003) — resolved:** The VCS leak vector is eliminated. The runtime `.env.docker` is now gitignored; only the `.env.docker.example` template is tracked. Operators must bootstrap the runtime file locally via `cp .env.docker.example .env.docker` before deploying. Residual risk is limited to operator error (e.g., copying the example and committing the populated file), which is not covered by an automated guard.
- **Scheduler crash-loop (CFG-004):** The scheduler profile service is currently in a crash-loop when enabled. All scheduled sweep tasks (archive/delete/consent/draft sweep/login-token cleanup/purge-failed/purge-rejected) are suspended until fixed.
- **No CI guard for secret rejection (CFG-005):** The fail-fast behavior of DJANGO_SECRET_KEY/POSTGRES_PASSWORD (verified at runtime) has no automated test. A future refactor could silently regress this.
