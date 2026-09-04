# Validation Report — CI/CD Planning Documents

**Validator:** Kilo (Validator Agent)
**Date:** 2026-09-01
**Documents validated:**
- `.ai/plans/ci_cd/plan.md_updated.md`
- `.ai/plans/ci_cd/preparation-guide.md_updated.md`

**Methodology:** Read both `_updated.md` documents, then verified every claim against the live codebase by reading the actual source files (compose files, workflows, Dockerfile, settings, enums, Makefile, parity test, deployment runbook, `.env.docker.example`, `.gitignore`, `pyproject.toml`, nginx config). Used `git status` to confirm originals are untouched.

---

## Per-Check Results (V1–V10)

### V1. Compose File Naming Accuracy — **PASS** (with 1 FAIL defect)

**Live repo compose files:** `docker-compose.yml`, `docker-compose.dev.override.yml`, `docker-compose.prod.yml`, `docker-compose.test.yml` — all `.yml` (verified via filesystem listing and `Get-ChildItem`).

**Evidence:**
- `Makefile:10` uses `-f docker-compose.yml -f docker-compose.dev.override.yml` ✓
- `Makefile:11` uses `-f docker-compose.yml -f docker-compose.test.yml` ✓
- All Makefile targets, compose overrides, CI workflow, and ops docs depend on these legacy names.

**Findings:**
1. **PASS** — Both docs use the real `docker-compose.*.yml` names in all command blocks, trees, and file listings.
2. **PASS** — `compose.yaml` / `compose.*.yaml` mentions appear ONLY inside explicit correction/migration notes:
   - `plan.md_updated.md:729` — "Rename | docker-compose.yml → compose.yaml etc. | 🚫 Do NOT" (in the Files-to-Create/Modify avoidance table).
   - `preparation-guide.md_updated.md:803-810` — "stale names (DO NOT USE)" correction table mapping `compose.yaml` → `docker-compose.yml` etc.
3. **FAIL** — `preparation-guide.md_updated.md:179` has a path typo: `github/workflows/deploy.yml` (missing leading `.`). Should be `.github/workflows/deploy.yml`. The adjacent lines (177, 178) correctly include the leading dot. The tree diagram at line 121 is correct.

**Correction needed (prep-guide line 179):**
```
- github/workflows/deploy.yml
+ .github/workflows/deploy.yml
```

---

### V2. Language Accuracy — **PASS**

**Live code evidence:**
- `src/backend/config/settings/base.py:67-73` — `LANGUAGE_CODE = "ru"`, `LANGUAGES = [("ru", "Russian"), ("bs", "Bosnian"), ("en", "English")]` ✓
- `src/backend/apps/core/enums.py:187-192` — `LanguageLocale.StrEnum` with `RUSSIAN="ru"`, `BOSNIAN="bs"`, `ENGLISH="en"` ✓
- `docker/Dockerfile:83` — `compilemessages ... --locale ru --locale bs --locale en` ✓
- `src/backend/.gitignore` (not relevant; locale defined in settings)

**Findings:**
1. **PASS** — Both docs state `ru`/`bs`/`en` and use "Bosnian" (not Montenegrin) for the `bs` locale.
2. **PASS** — "Montenegrin" appears ONLY as an explicit correction: `plan.md_updated.md:197` "(Bosnian, not Montenegrin)" and `preparation-guide.md_updated.md:1200` "(Bosnian, not Montenegrin)".
3. **PASS** — "Montenegro" appears only as launch geography/market: `preparation-guide.md_updated.md:1208` "The launch geography is Montenegro, but the UI language code is Bosnian (bs)." Also appears in `docs/ops/docker-deployment.md` (not the plan docs) as real Montenegro cities — out of scope for these docs.
4. **PASS** — `LANGUAGES` tuple order matches: Russian, Bosnian, English. ✓

---

### V3. Secrets Strategy Accuracy — **PASS**

**Live code evidence:**
- `.gitignore:148` — `.env.docker` (confirmed via `git check-ignore .env.docker` → outputs `.env.docker`) ✓
- `.env.docker.example:9-72` — contains exactly **23** app/env variables (verified by count: DJANGO_SECRET_KEY, DEBUG, ALLOWED_HOSTS, POSTGRES_USER, POSTGRES_DB, POSTGRES_PASSWORD, REDIS_URL, BOT_USERNAME, BOT_TOKEN, SITE_URL, IMMEDIATE_ALERTS_ENABLED, TLS_CERT_PATH, PLAUSIBLE_HOST, ADMIN_USERNAME, ADMIN_PASSWORD, ADMIN_TELEGRAM_ID, SEED_USERS, SEED_ADS, REGISTRY, REPOSITORY, IMAGE_TAG, FIX_PERMISSIONS, SKIP_ENV_CHECK) ✓
- `src/backend/config/settings/prod.py:18-22` — fails fast if `BOT_TOKEN` is empty (non-build mode) ✓
- `prod.py:26-30` — fails fast if `SITE_URL` is unset ✓
- `prod.py:50-51` — fails fast if `ALLOWED_HOSTS` is empty ✓
- `src/backend/config/settings/base.py:52` — `SECRET_KEY = env("DJANGO_SECRET_KEY")` (required, no default) ✓

**Findings:**
1. **PASS** — Both docs state ONLY 4 GitHub Secrets: `SERVER_HOST`, `SERVER_USER`, `SERVER_SSH_KEY`, `SERVER_PORT`.
2. **PASS** — Both docs state app secrets live ONLY in `.env.docker` on the VPS.
3. **PASS** — `plan.md_updated.md:261` lists 23 variables in the `.env.docker` template; matches `.env.docker.example` exactly.
4. **PASS** — Both docs explicitly flag `research.md §5.1` (8-secret list) as stale and do NOT present it as current. `plan.md_updated.md:147` "This is stale and contradicts both the code and the other plan files."
5. **PASS** — The fail-fast guards are correctly cited with accurate line numbers.

---

### V4. CI Baseline Accuracy — **PASS** (with 2 WARN line-range inaccuracies)

**Live code evidence:**

`.github/workflows/ci.yml` (253 lines):
- Line 8: `build:` job
- Line 30: `push: false`
- Line 32-33: `cache-from: type=registry,ref=ghcr.io/manicko/mko-bazuna:buildcache` / `cache-to: type=registry,ref=ghcr.io/manicko/mko-bazuna:buildcache,mode=max`
- Line 35: `test:` job
- Line 41: `image: postgres:18-alpine`
- Line 58: `uses: astral-sh/setup-uv@v5`
- Line 111: `uv run pytest -m "not seed" -n auto --dist loadgroup --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db`
- Line 115: `uses: actions/upload-artifact@v4`
- Line 121: `lint:` job
- Line 136: `uv run ruff check .`
- Line 139: `typecheck:` job
- Line 154: `uv run basedpyright .`
- Line 157: `lint-templates:` job
- Line 172: `uv run djlint templates/`
- Line 177: `i18n:` job (spans to line 253, end of file)
- Line 196: `uses: actions/checkout@v4` (used across jobs)
- Line 230/9: `uses: docker/login-action@v3`
- Line 26/226: `uses: docker/build-push-action@v7`

`.github/workflows/ci-nightly.yml` (82 lines):
- Line 5: `cron: "0 3 * * *"` (03:00 UTC daily)
- Line 6: `workflow_dispatch:`
- Line 8-11: `concurrency:` group `nightly-seed-tests`, `cancel-in-progress: false`
- Line 20: `image: postgres:18-alpine`
- Line 37: `uses: astral-sh/setup-uv@v5`
- Line 73: `uv run pytest -m "seed" --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db`
- Line 78: `uses: actions/upload-artifact@v4`

**Findings:**
1. **PASS** — Docs describe 6 parallel jobs: build, test, lint, typecheck, lint-templates, i18n. ✓ (actual ci.yml has exactly these 6)
2. **PASS** — Docs describe nightly serial seed suite, daily cron at 03:00 UTC + manual trigger. ✓
3. **PASS** — Docs describe GHCR registry buildcache with `push: false`. ✓ (ci.yml:30, ci.yml:32-33)
4. **PASS** — Docs describe the exact test command with all flags: `-m "not seed" -n auto --dist loadgroup --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db`. ✓ (ci.yml:111 — exact match) ✓
5. **PASS** — Docs cite `setup-uv@v5`. ✓ (ci.yml:58)
6. **PASS** — Docs cite correct action versions: `checkout@v4`, `login-action@v3`, `build-push-action@v7`, `upload-artifact@v4`. ✓
7. **PASS** — Docs do NOT claim ci.yml has a deploy/push job. `plan.md_updated.md:39`: "it validates that the image builds but never publishes for deployment."
8. **PASS** — Docs correctly identify that `deploy.yml` does NOT exist. `plan.md_updated.md:41`: "There is no .github/workflows/deploy.yml." Confirmed: `.github/workflows/` contains only `ci.yml` and `ci-nightly.yml`.
9. **WARN** — `plan.md_updated.md:191` and `preparation-guide.md_updated.md:558` cite `ci.yml:177-215` for the i18n job. The i18n job actually spans lines 177–253 (end of file). Lines 177–215 cover only the job header through "Install gettext"; the compiletranslations step (ci.yml:233-245) and the i18n completeness test (ci.yml:247-253) are outside this range. The description content is correct; only the line range is inaccurate.
10. **WARN** — `plan.md_updated.md:186` claims the cache ref is `ghcr.io/manicko/mko_bazuna:buildcache` (underscore, matching the GitHub repo name `mko_bazuna`). The actual `ci.yml:32-33` uses `ghcr.io/manicko/mko-bazuna:buildcache` (hyphen). The docs' underscore version is actually the *correct* image name (matches `pyproject.toml:39` `https://github.com/manicko/mko_bazuna`), so ci.yml has a typo. The docs' stated cache ref string does not exactly match the literal ci.yml content. This is a ci.yml bug, not a docs error, but the docs' quoted line reference should note the divergence.

---

### V5. CD / deploy.yml Accuracy — **PASS** (with 3 defects/caveats)

**Live code evidence:**
- `.github/workflows/deploy.yml` does NOT exist (confirmed: `Test-Path` → `False`).
- `docker/Dockerfile:154-155` — `HEALTHCHECK ... CMD curl -f http://localhost:8000/health/ || exit 1` (runs inside container; uses `localhost`). ✓
- `docker/nginx/nginx.conf:119-126` — `location /health/` proxies to `http://web:8000` on ports 80/443.
- `docker-compose.yml:162` — web service comment: "Port 8000 NOT published - nginx proxies internally" (port 8000 not published in prod).
- `src/backend/apps/core/enums.py:35` — `AdvisoryLockId.MIGRATE = 100` (lock ID 100 confirmed).

**V5-required deploy.yml elements — all present in docs:**
1. **workflow_dispatch** with **required** `image_tag` input, `default: ''` (no `latest`): `plan.md_updated.md:401-406`, `preparation-guide.md_updated.md:649-654`. ✓
2. **concurrency** (`cancel-in-progress: false`): `plan.md_updated.md:467-469`, `preparation-guide.md_updated.md:703-705`. ✓
3. **OIDC permissions** (`id-token: write`) + `docker/login-action`: `plan.md_updated.md:419-423,430-434`, `preparation-guide.md_updated.md:662-665,673-677`. ✓
4. **docker/metadata-action@v5**: `plan.md_updated.md:438`, `preparation-guide.md_updated.md:681`. ✓
5. **docker/build-push-action@v7** with `push: true`: `plan.md_updated.md:446-450`, `preparation-guide.md_updated.md:689-693`. ✓
6. **environment: production**: `plan.md_updated.md:463`, `preparation-guide.md_updated.md:702`. ✓
7. **Deploy sequence**: pull (C5) → pg_dump backup (C6) → migrate (C7) → up -d (C8) → image prune (C10) → health-check (C9) → rollback (C9). ✓ (plan.md:499-558, prep-guide:735-797)
8. **Health-check target** `http://web:8000/health/`: ✓ (plan.md:537, prep-guide:774). Path `/health/` correct per Dockerfile HEALTHCHECK. ✅
9. **Rollback reads stored previous tag** from `/tmp/previous_tag.txt`: ✓ (plan.md:547, prep-guide:784).

**Findings:**
1. **DEFECT (FAIL)** — `plan.md_updated.md:493` has a **buggy `sed` command** for extracting `PREVIOUS_TAG`:
   ```bash
   PREVIOUS_TAG=$(echo "$CURRENT_IMAGE" | sed 's|.*/||' | sed 's|:||; s|.*:||' || echo "")
   ```
   The first `sed 's|.*:||'` is `s|:||` which removes the **first** colon (producing e.g. `mko_bazunasha-a913bc2`), then `sed 's|.*:||'` finds no remaining colon and does nothing. Result: `mko_bazunasha-a913bc2` — incorrect. For input `ghcr.io/manicko/mko_bazuna:sha-a913bc2`, the correct output should be `sha-a913bc2`.
   The **prep-guide** (`preparation-guide.md_updated.md:729`) uses the correct approach: `rev | cut -d: -f1 | rev`. The plan.md deploy template should match.
   **Correction:** Change plan.md line 493 to use the prep-guide's correct `rev | cut -d: -f1 | rev` approach, or use `sed 's/.*://'`.

2. **CAVEAT (FAIL-worthy)** — The health-check `curl http://web:8000/health/` runs via `appleboy/ssh-action` on the **VPS host** (SSH session), not inside the Docker compose network. On the VPS host:
   - `web` is a Docker Compose service name that does **not** resolve (it only resolves within the compose network or via `docker compose exec`).
   - Port 8000 is **NOT published** in production (`docker-compose.yml:162`: "Port 8000 NOT published").
   - The docs note "compose-internal hostname" (`plan.md:535`, `preparation-guide:772`) but do **not** address that the SSH execution context is the host, not the network.
   - This means the health check would **always fail** and trigger a false rollback.
   **Recommended fix:** Use `docker compose -f docker-compose.yml -f docker-compose.prod.yml exec web curl -sf http://localhost:8000/health/` or check via nginx (`curl -k https://localhost/health/`) or use `docker compose ps` health status.
   The nginx config (`nginx.conf:119-126`) does expose `/health/` on ports 80/443, providing a working host-side health target.

3. **CAVEAT** — The docs claim "OIDC authentication to GHCR (`permissions: id-token: write`)" (`plan.md:412`, `preparation-guide.md:638`) but the deploy template uses `token: ${{ secrets.GITHUB_TOKEN }}` (`plan.md:434`, `preparation-guide:677`), which is **GITHUB_TOKEN-as-password**, not true OIDC. The `docker/login-action@v3` with `GITHUB_TOKEN` uses the standard bearer-token flow. True OIDC for GHCR (no stored token) requires a different invocation (e.g., `docker/login-action` with OIDC token exchange or newer `registry-type: oidc`). The checklist V5 accepts this combination, but the docs' framing as "OIDC" is technically inaccurate. This is advisory only (CD is unbuilt) but should be acknowledged.

4. **CAVEAT (per checklist V5)** — `/tmp/previous_tag.txt` is ephemeral and fragile for rollback state. The docs flag this as advisory (`plan.md:561`: "consider image-digest pinning") but should recommend persisting the previous tag in a reliable location (e.g., `/opt/mko_bazuna/.previous_tag` or Docker Compose labels) rather than `/tmp/`.

---

### V6. Modern Best-Practice Claims Accuracy — **PASS** (with 1 WARN gap)

**Findings:**
1. **PASS** — OIDC: docs describe `permissions: id-token: write` (with caveat above). ✓
2. **PASS** — Trivy fs-mode + SARIF via `github/codeql-action/upload-sarif@v3`: `plan.md:586-600` uses `scan-type: fs`, `format: sarif`, `output: trivy-results.sarif`, `exit-code: '0'` (non-blocking). ✓ Accurate 2025–2026 practice.
3. **PASS** — gitleaks + `.gitleaks.toml` (TOML syntax): `plan.md:573,867`. ✓ Accurate.
4. **PASS** — zizmor: `plan.md:574,868`. ✓ Accurate (advisory, non-mandatory).
5. **PASS** — `--dist worksteal` only with "if xdist ≥ 3.8" caveat: `plan.md:869`, `preparation-guide:1079`. ✓ Both note the condition.
6. **PASS** — `--import-mode=importlib` in pyproject addopts: `pyproject.toml:168` `addopts = ["--import-mode=importlib", "-ra", "-q"]`. ✓
7. **PASS** — No `setup-python` claim (docs use `astral-sh/setup-uv@v5`, which is correct). ✓
8. **WARN** — **No Dependabot YAML snippet** provided. The docs describe Dependabot (`github-actions` + `docker` ecosystems, weekly) in prose and table rows (`plan.md:572,726,864`, `preparation-guide:1077`) but do **not** include a complete `dependabot.yml` snippet with `version: 2` and `package-ecosystem` entries. The checklist asks to verify the snippet is syntactically valid; no snippet exists to validate. Minor gap — the description is accurate but a concrete YAML example would strengthen the doc.
9. **PASS** — All best-practice recommendations are flagged advisory/non-mandatory. ✓

---

### V7. Project Rule Compliance — **PASS**

**Findings:**
1. **PASS** — English-only: Both docs are entirely in English. Scanned for Cyrillic and non-English prose; none found.
2. **PASS** — StrEnum rule: Both docs reference StrEnum-based constants. `plan.md:197` cites `enums.py:187-192` `LanguageLocale.RUSSIAN/BOSNIAN/ENGLISH` (confirmed: `LanguageLocale.StrEnum` at enums.py:187). `preparation-guide:1200-1208` lists StrEnum names with evidence. ✓
3. **PASS** — i18n DoD (#16): Both docs reference `compilemessages` + `test_i18n_completeness.py`. `plan.md:191` "compilemessages + test_i18n_completeness.py". `preparation-guide:558,578` reference `--locale ru --locale bs --locale en` and completeness tests. ✓
4. **PASS** — Two processes, one DB: Both docs correctly describe the web (gunicorn WSGI) + bot (aiogram) model sharing one PostgreSQL 18 DB, with migrations run once before both start via advisory-locked one-shot service. ✓

---

### V8. Already-Implemented Items Marked Done — **FAIL** (1 critical defect)

**Live code evidence for items the docs claim are ✅ Done:**

| Claimed Done | Live Evidence | Status |
|---|---|---|
| 3-stage Dockerfile (builder/runtime/test-runtime) | `docker/Dockerfile:8` (builder), `:89` (runtime), `:168` (test-runtime) | ✅ PASS |
| Non-root user uid 1000 | `docker/Dockerfile:103-104` `groupadd -g 1000 app` / `useradd -u 1000`; `:149` `USER app` | ✅ PASS |
| HEALTHCHECK | `docker/Dockerfile:154-155` `curl -f http://localhost:8000/health/` | ✅ PASS |
| Prod image overrides | `docker-compose.prod.yml:7-26` (web, bot, migrate, create_admin, seed → GHCR images) | ✅ PASS |
| Scheduler/backup/pgbouncer profiles | `docker-compose.prod.yml:38-63` (scheduler), `:67-97` (backup), `:100-121` (pgbouncer) | ✅ PASS |
| `.env.docker` gitignored | `.gitignore:148` | ✅ PASS |
| Fail-fast prod settings guards | `prod.py:18-22` (BOT_TOKEN), `:26-30` (SITE_URL), `:50-51` (ALLOWED_HOSTS); `base.py:52` (DJANGO_SECRET_KEY) | ✅ PASS |
| Languages ru/bs/en | `base.py:69-73`, `enums.py:187-192`, `Dockerfile:83` | ✅ PASS |
| `test_docs_ci_parity.py` contract | `src/backend/tests/test_docs_ci_parity.py` (175 lines) — asserts loadgroup, not-seed, reuse-db, importlib | ✅ PASS |
| pytest `--import-mode=importlib` | `pyproject.toml:168` | ✅ PASS |
| pytest-xdist ≥ 3.8 | `pyproject.toml:213` `pytest-xdist>=3.8.0` | ✅ PASS |
| Migrate-locked advisory lock (ID 100) | `enums.py:35` `AdvisoryLockId.MIGRATE = 100`; `docker-compose.yml:35` calls `migrate_locked.main()` | ✅ PASS |
| `docker/entrypoint.sh` shared functions | 6 entrypoint scripts in `docker/` (entrypoint.sh:3472, entrypoint-test.sh:2702, entrypoint-catalog.sh:493, entrypoint-scheduler.sh:2066, entrypoint-seed.sh:1376, entrypoint-create-admin.sh:838 bytes) | ✅ PASS |
| 3 tracked `.env*.example` templates | `.env.example`, `.env.dev.example`, `.env.docker.example` all present at repo root | ✅ PASS |
| `.env.docker.example` = 23 variables | `.env.docker.example` contains exactly 23 `VAR=` lines | ✅ PASS |

**CRITICAL FAIL:**
- **Rollback docs claim in `docs/ops/docker-deployment.md` is FALSE.**
  - `plan.md_updated.md:199` claims: "Rollback docs in `docs/ops/docker-deployment.md` | ✅ Done"
  - `preparation-guide.md_updated.md:892` claims: "Rollback procedures are also documented in `docs/ops/docker-deployment.md` (§Stage E)"
  - **Reality:** `docs/ops/docker-deployment.md` has **zero** (0) mentions of "rollback" (grep across all `docs/ops/*.md` returned 0 matches). The 896-line file covers Purpose, Compose Project Isolation, Startup Dependency Chain, Local Dev Setup, Production Deployment, Makefile Commands, Test Environment, Scheduled Jobs, Nginx Configuration, Database Operations (Backup/Restore/Migrations), Admin User Setup, Seed Data, Monitoring & Logging, Troubleshooting, and Related Documentation — but **no rollback section**.
  - The audit report propagated this same error: `audit-report.md:83` claims "docker-deployment.md:788–736 has a rollback/ssh section" and `audit-report.md:170,301` claim rollback docs are at `docker-deployment.md:788-876` — but lines 788-876 are actually the "Container Health", "Log Access", and "Viewing Metrics" sections (Monitoring & Logging), not rollback.
  - **The rollback documentation actually lives ONLY in `preparation-guide.md_updated.md` §Stage E (lines 838-893).**
  - **Correction:** Either (a) remove the claim that rollback docs are already in `docker-deployment.md` and mark the rollback section as documentation-in-prep-guide-only, or (b) actually add a rollback section to `docker-deployment.md`.

---

### V9. Dead Files & Stale References — **PASS**

**Findings:**
1. **PASS** — Both docs mention the 4 root-level 0-byte stubs as dead files:
   - `plan.md_updated.md:92-101` — table with sizes (0 bytes) and real counterparts.
   - `preparation-guide.md_updated.md:149-157` — lists stubs with sizes and real counterparts.
   - Verified: `entrypoint.sh` (0 bytes), `entrypoint-test.sh` (0 bytes), `entrypoint-catalog.sh` (0 bytes), `entrypoint-seed.sh` (0 bytes) at repo root. Real scripts in `docker/` have sizes: 3472, 2702, 493, 1376, 2066, 838 bytes — all match docs. ✓
2. **PASS** — Neither doc says "rename compose files." Both explicitly say "Do NOT rename":
   - `plan.md_updated.md:90,729,848,855` — "Do NOT rename", "Do not rename", "Do not rename", "Do not rename"
   - `preparation-guide.md_updated.md:160,803,812,1083` — "Do NOT rename", correction notes, "Do not rename"

---

### V10. Structural Completeness & Originals Unchanged — **PASS**

**Section count — `plan.md_updated.md`:**
The audit (`audit-report.md:220-248`) recommends 15 sections: Metadata, Overview, Repository Structure, What Lives Where, Pre-implemented Components, SSH Key Pairs, Implementation Stages, Execution Order/DAG, Risk Assessment, Verification Steps, Files to Create/Modify, Deployment Commands Reference, Branch Strategy, Architecture Constraints, Modern Best-Practice.

The updated plan.md contains:
- Metadata header block (lines 1-9) ✓
- ## 0. Overview ✓ (line 32)
- ## 1. Repository Structure ✓ (line 53)
- ## 2. What Lives Where ✓ (line 105)
- ## 3. SSH Key Pairs ✓ (line 159)
- ## 4. Pre-implemented Components ✓ (line 174)
- ## 5. Implementation Stages ✓ (line 209)
- ## 6. Execution Order / DAG ✓ (line 622)
- ## 7. Risk Assessment ✓ (line 668)
- ## 8. Verification Steps ✓ (line 688)
- ## 9. Files to Create/Modify ✓ (line 721)
- ## 10. Deployment Commands Reference ✓ (line 738)
- ## 11. Branch Strategy ✓ (line 787)
- ## 12. Architecture Constraints ✓ (line 799)
- ## 13. Modern Best-Practice Integration ✓ (line 857)

All 15 recommended sections present (Metadata is a header block rather than a numbered section, but its content is fully present). ✓

**Section count — `preparation-guide.md_updated.md`:**
The audit (`audit-report.md:250-271`) recommends 13 sections: Metadata, Stage 0, Repository Structure, What Lives Where, SSH Key Pairs, Stage A, Stage B, Stage C, Stage E, Stage F, Stage G, Forward-looking Recommendations, Quick Reference.

The updated prep-guide contains:
- Metadata header block (lines 1-10) ✓
- ## 0. Stage 0 — Local Development Machine ✓ (line 35)
- ## 1. Repository Structure ✓ (line 111)
- ## 2. What Lives Where ✓ (line 172)
- ## 3. SSH Key Pairs ✓ (line 229)
- ## 4. Stage A — One-time Server Preparation ✓ (line 251)
- ## 5. Stage B — GitHub Configuration ✓ (line 480)
- ## 6. Stage C — GitHub Actions Workflow ✓ (line 530)
- ## 7. Stage E — Rollback Procedure ✓ (line 838)
- ## 8. Stage F — Verification Checklist ✓ (line 896)
- ## 9. Stage G — Daily Release Process ✓ (line 964)
- ## 10. Forward-looking Recommendations ✓ (line 1055)
- ## 11. Quick Reference ✓ (line 1087)

All 13 recommended sections present. ✓

**Originals unchanged:**
- `git status`: Only `plan.md_updated.md`, `preparation-guide.md_updated.md`, and `audit-report.md` appear as new untracked files. The originals (`plan.md`, `preparation-guide.md`, `research.md`) do NOT appear in git status (not modified, not staged).
- File timestamps confirm: `plan.md` (2026-07-28 21:21), `preparation-guide.md` (2026-07-28 21:24), `research.md` (2026-07-28 10:22) — all original. The `_updated.md` files are dated 2026-09-01. ✓
- Only `.ai/plans/ci_cd/plan.md_updated.md` and `.ai/plans/ci_cd/preparation-guide.md_updated.md` were created. ✓

---

## Defects to Fix (FAIL items)

| # | Doc | Line(s) | Defect | Correction |
|---|---|---|---|---|
| 1 | `preparation-guide.md_updated.md` | 179 | Path typo: `github/workflows/deploy.yml` (missing leading `.`) | Change to `.github/workflows/deploy.yml` |
| 2 | `plan.md_updated.md` | 493 | Buggy `sed` for PREVIOUS_TAG extraction: `sed 's\|.\*/\|; s\|:\|; s\|.*:\|'` produces `mko_bazunasha-a913bc2` instead of `sha-a913bc2` | Replace with the correct approach used in prep-guide line 729: `rev \| cut -d: -f1 \| rev` |
| 3 | `plan.md_updated.md` | 199 | Claims "Rollback docs in `docs/ops/docker-deployment.md` | ✅ Done" — FALSE. `docker-deployment.md` has 0 "rollback" mentions. | Remove claim or add rollback section to `docker-deployment.md` |
| 4 | `preparation-guide.md_updated.md` | 892 | Claims "Rollback procedures are also documented in `docs/ops/docker-deployment.md` (§Stage E)" — FALSE. | Remove claim or add rollback section to `docker-deployment.md` |

---

## Caveats to Surface (WARN items)

| # | Doc | Line(s) | Caveat | Impact |
|---|---|---|---|---|
| 1 | Both | 191 (plan), 558 (prep) | i18n job line range cited as `ci.yml:177-215` but actual job spans 177–253. compiletranslations (233-245) and completeness test (247-253) are outside cited range. | Low — description text is correct; only line numbers are slightly off. |
| 2 | `plan.md_updated.md` | 186 | Cache ref cited as `ghcr.io/manicko/mko_bazuna:buildcache` (underscore) but actual `ci.yml:32` uses `ghcr.io/manicko/mko-bazuna:buildcache` (hyphen). Docs are correct (underscore matches repo name); ci.yml has a typo. | Medium — ci.yml cache ref uses wrong name, meaning cache reads may miss. Recommend fixing ci.yml:32-33 to use `mko_bazuna` (underscore). |
| 3 | `plan.md_updated.md` | 699 | Cites `Makefile:101` for `make test-db`, but `test-db:` target is at `Makefile:121`. Line 101 is the `test:` target's DB-start command. | Low — minor line attribution error. |
| 4 | Both | 537 (plan), 774 (prep) | Health check `curl http://web:8000/health/` runs via SSH on the VPS **host**, where `web` (compose-internal hostname) does not resolve and port 8000 is NOT published in prod (`docker-compose.yml:162`). This would always fail and trigger false rollback. | Medium — the deploy.yml template's health check is broken as written. Should use `docker compose exec web curl ...` or check nginx `/health/` on port 80/443. |
| 5 | Both | 434 (plan), 677 (prep) | Docs claim "OIDC authentication to GHCR" but template uses `token: ${{ secrets.GITHUB_TOKEN }}` (GITHUB_TOKEN-as-password, not true OIDC). `docker/login-action@v3` with `GITHUB_TOKEN` is the standard bearer-token flow. | Low for now (CD is unbuilt, advisory). If implemented as-is, auth works but it's not OIDC. True OIDC would omit the token and rely on the action's OIDC exchange. |
| 6 | Both | 494, 547 (plan), 730, 784 (prep) | `/tmp/previous_tag.txt` for rollback state is fragile and non-persistent across reboots/cleans. Each `appleboy/ssh-action` invocation is a separate SSH session; while `/tmp` persists on the VPS host, it's not resilient. | Medium — docs flag this as advisory but should recommend a persistent location like `/opt/mko_bazuna/.previous_tag`. |
| 7 | Both | 869 (plan), 1079 (prep) | `--dist worksteal` recommendation is correctly gated on "if xdist ≥ 3.8" and notes the parity test update requirement. | None — correctly scoped as advisory. ✓ |
| 8 | `plan.md_updated.md` | 572, 726, 864 | Dependabot described in prose/table but no complete `dependabot.yml` YAML snippet with `version: 2` + `package-ecosystem` entries provided. | Low — description is accurate; a concrete YAML example would allow validation. |

---

## Rollout Analysis

**Sequence validated:** Stage 0 (local) → Stage A (VPS prep + 4 secrets) → Stage B (CI baseline documented, B1 concurrency + B3 paths-ignore to-do) → Stage C (CD build, C1→C2→C4→C5→C6→C7→C9→C10, C8 already done) → Stage D (D1→D2 Trivy+SARIF; D3 pip-audit; D4 Dependabot; D5 gitleaks; D6 zizmor — all independent). ✓

**Dependencies validated (no circular):**
- C4 (deploy) depends on C2 (build/push) — correct: image must exist in GHCR before deploy pulls it.
- C9 (health-check rollback) depends on C4, C5, C6, C7, C8 — correct.
- C6 (backup) must run BEFORE C7 (migrate) and C8 (up) — correct ordering.
- D1 (Trivy) depends on C2 (built image available) — correct.
- D2 depends on D1 — correct.
- D3/D4/D5/D6 are independent — correct.

**Rollback feasibility:** The deploy.yml template does NOT implement actual rollback via GitHub Actions `workflow_run` or re-dispatch — it's an in-script `docker compose pull` + `up -d --no-deps web` on the VPS. This is feasible but fragile (see caveats #4 and #6).

**Backward compatibility:** No existing production code, workflows, or databases are modified by the plan. Only `.github/workflows/deploy.yml` (new) and security configs (`.gitleaks.toml`, `dependabot.yml`) would be created. ✓

**Risk:** The highest-risk items are the two FAIL defects (#1 stale rollback-docs claim, #2 buggy sed) — both must be corrected before the deploy.yml template can be implemented faithfully. The health-check caveat (#4) is the most operationally significant.

---

## Execution Validation

**Applicability:** The docs describe a Docker + GHCR + manual-`workflow_dispatch` + single-VPS model, consistent with the live architecture (`docs/99-agent/architecture.md`). The CI baseline (ci.yml, ci-nightly.yml) is accurately documented as live. The CD pipeline (deploy.yml) is correctly identified as to-be-built. ✓

**Prerequisites confirmed:**
- `setup-uv@v5` is the correct tool (not `setup-python`) — docs correctly use `setup-uv@v5` matching `ci.yml:58`. ✓
- `pyproject.toml:213` confirms `pytest-xdist>=3.8.0` (worksteal available). ✓
- `pyproject.toml:168` confirms `--import-mode=importlib` in addopts. ✓
- `AdvisoryLockId.MIGRATE = 100` (enums.py:35) matches the migrate-locked lock ID claim. ✓
- `docker-compose.prod.yml:7-26` image overrides match the documented prod image override. ✓

---

## Overall Verdict: **REVISE**

The updated documents are **mostly accurate** — they correctly identify the repo structure, secrets strategy, CI baseline (6 jobs, nightly seed suite, parity contract), already-implemented components (3-stage Dockerfile, uid-1000, HEALTHCHECK, prod overrides, profiles, parity test, StrEnum, i18n), and the to-be-built nature of CD. The core architecture constraints (no compose rename, Bosnian not Montenegrin, 4 secrets only) are correctly captured.

However, **3 FAIL defects** require correction before the documents can be considered accurate:
1. **Stale rollback-docs claim** (plan.md:199, prep-guide:892) — `docs/ops/docker-deployment.md` has no rollback section; this claim is inherited from an erroneous audit report finding.
2. **Path typo** (prep-guide:179) — `github/workflows/deploy.yml` missing leading dot.
3. **Buggy sed** (plan.md:493) — PREVIOUS_TAG extraction produces incorrect result.

Additionally, **2 caveats** require maintainer attention before CD implementation:
- The health-check `curl http://web:8000/health/` is broken as written (runs on VPS host where `web` doesn't resolve and port 8000 isn't published).
- The OIDC claim vs. GITHUB_TOKEN-as-password mismatch in the deploy template.

**Recommendation:** Fix the 3 FAIL defects, address the health-check caveat (corrected in both the deploy.yml template and the commands reference), and acknowledge the OIDC/TAG-extraction caveats. After corrections, re-validate.

---

*This validation report does not modify any production code, workflows, or configuration. It evaluates the two `_updated.md` planning documents against the live codebase as of 2026-09-01.*
