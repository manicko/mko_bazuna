# Step 4 — Risk Assessment & Implementation Analysis

**Audit Source:** `ai/step3-audit.md` (17 findings, F01–F17)  
**Verified Against:** Repository at `C:\py_dev\mko_bazuna`, commit `ba5c65e` + working tree  
**Date:** 2026-08-29  
**Methodology:** Each finding was cross-checked against live filesystem evidence — file sizes, line numbers, git-tracking status, and actual `uv run python` invocations in entrypoint scripts. Confidence: **HIGH** for all 17 (verified on disk).

---

## Summary Table

| ID  | Risk Rating | Preferred Approach | Dependencies |
|-----|-------------|--------------------|--------------|
| F01 | **High** | Add `scripts/seed-images-config.json` to `.dockerignore` | Standalone |
| F02 | **High** | Add `backups/` to both `.gitignore` and `.dockerignore` | Standalone |
| F03 | **Medium** | Add `cat_output.txt`, `neq`, `Continue`, `cmp_css.py` to `.dockerignore` | Standalone |
| F04 | **Medium** | Add `.local/` to `.dockerignore` | Standalone |
| F05 | **Low** | Add `scripts/_tmp_*.txt` and `scripts/session_context.json` to both `.gitignore` and `.dockerignore` | Standalone |
| F06 | **Low** | Add `.playwright-mcp/` to `.dockerignore` | Standalone |
| F07 | **Low** | Add `docker/nginx/` to `.dockerignore` | Standalone |
| F08 | **High** | Replace `uv run python` → `/opt/venv/bin/python` in 4 aux scripts; move `uv`/`uvx` COPY from `runtime` to `test-runtime` stage only | Script changes before Dockerfile change |
| F09 | **Medium** | Add `*.mo` and `*.pot` to `.dockerignore` | Standalone |
| F10 | **Low** | Add `.gitattributes` to `.dockerignore` | Standalone |
| F11 | **Low** | Add `.python-version` to `.dockerignore` | Standalone |
| F12 | **Low** | Add `.tox/`, `.nox/`, `.pyre/`, `.pytype/`, `__pypackages__/`, `.profile_default/` to `.dockerignore` | Standalone |
| F13 | **Low** | Add `*.manifest` and `*.spec` to `.dockerignore` | Standalone |
| F14 | **Medium** | Add `.coverage`, `.coverage.*`, `coverage.xml`, `htmlcov/`, `.hypothesis/` to `.dockerignore` | Standalone |
| F15 | **Medium** | Add `celerybeat-schedule`, `celerybeat.pid`, `*.rdb`, `*.aof`, `*.pid`, `.gunicorn/` to `.dockerignore` | Standalone |
| F16 | **Low** | Expand `--ignore` list in `entrypoint.sh` (L76) and `Makefile` (L154) with all cache dirs | F16 ≈ F17 (consistency) |
| F17 | **Low** | Add `--ignore` + `--locale ru --locale bs --locale en` flags to `compilemessages` in Dockerfile (L78) and CI (ci.yml L83, L176) | F16 (consistency) |

**Key dependency chain:** F08 requires 4 entrypoint-script edits + 1 Dockerfile edit in lockstep. No other finding blocks or is blocked by another. All `.dockerignore` additions (F01–F07, F09–F15) are fully independent and can be batched in a single commit. F16/F17 should be applied together for consistency.

---

## Detailed Per-Finding Analysis

### F01: `scripts/seed-images-config.json` (API keys) not in `.dockerignore`

**1. Implementation approach (preferred):**
Add the line `scripts/seed-images-config.json` to `.dockerignore`. The file already contains `UNSPLASH_ACCESS_KEY` and `PEXELS_API_KEY` (verified on disk, 446 B). It is already in `.gitignore` at L225, so it will not be committed — but `.dockerignore` is independent of `.gitignore` and currently lacks the entry, so `COPY . .` (Dockerfile L57) bakes it into every local image build.

**2. Risks and possible breakage:**
- **Risk of NOT fixing:** Any developer with a local copy of this file (which they must have to run seed-image downloads) bakes live API credentials into container images. If those images are pushed to any registry, the keys are exposed. This is a confirmed credential-leak vector — **High** severity.
- After the fix, the file is excluded from the build context. It was never needed inside the image (seed scripts read it from the host via bind-mount in dev, and CI doesn't use seed images). No runtime path depends on it being in `/app`.

**3. Side effects:**
- None. The seed entrypoint (`entrypoint-seed.sh`) does not reference this file at runtime — seed photos are pre-downloaded as fixtures (verified: seed fixture images are gitignored at L226-228, and `entrypoint-seed.sh` L17-29 checks for fixture JPEGs on disk, not config). The config is only used by `scripts/download_seed_photos.py` (host-side, outside Docker).

**4. Downstream impact:**
- No impact on CI, tests, or production runtime. The file is only consumed by a host-side script (`scripts/download_seed_photos.py`).
- `.dockerignore` does NOT affect compose bind-mounts (as noted in the critical context). So dev mode with `.:/app` bind-mount still exposes the file inside the container — this is correct and intended (seed needs it).

**5. Development and CI implications:**
- No CI config changes needed.
- Local dev impact: zero — bind-mounts are unaffected by `.dockerignore`.
- The fix applies only to `docker build` (image builds, CI `build` job).

**6. Compatibility with existing architecture:**
- Fully compatible. The 3-stage Dockerfile, bind-mount dev workflow, and test-runtime stage are unaffected. The file is never read from `/app` at runtime.

**7. Viable alternatives:**
- (a) **Move the file** to a path outside the project root entirely. Rejected — breaks the existing seed-script workflow.
- (b) **Template-ize the file** (e.g., `seed-images-config.json.example` committed, real file gitignored). Already effectively done (file is gitignored); only `.dockerignore` needs the entry. This is the simplest fix.

**8. Dependency within the plan:**
- Standalone. No dependency on other findings.

**9. Risk rating:** **High** — confirmed credential leak vector; fix is a 1-line `.dockerignore` addition with zero side effects.

---

### F02: `backups/` directory not in `.gitignore` or `.dockerignore`

**1. Implementation approach (preferred):**
Add `backups/` to both `.gitignore` (new entry) and `.dockerignore` (new entry). The `Makefile backup` target (L199-206) writes `dump_*.dump` PostgreSQL dumps to `./backups/`. The directory exists on disk (currently empty). Dumps may contain PII (phone numbers, ad content) per project data model.

**2. Risks and possible breakage:**
- **Risk of NOT fixing:** If `make backup` has been run locally, dump files containing production data enter the build context via `COPY . .` (Dockerfile L57) and are baked into the image. This is a data-exposure risk — **High** severity.
- After the fix: `backups/` is excluded from both VCS ignore and Docker build context. Existing committed content (if any) would need a forced removal, but `backups/` is currently empty and untracked.

**3. Side effects:**
- Adding to `.gitignore` means `git status` will no longer show the backups directory — intentional, since it's a local artifact.
- `.dockerignore` change only affects `docker build`, not compose bind-mounts.

**4. Downstream impact:**
- No impact on CI, tests, or production. The backup target writes to the host filesystem; the dockerignore entry only prevents baking dumps into images.
- If a developer intentionally placed a legitimate (non-dump) file in `backups/` for the image, it would be excluded — but no current workflow does this.

**5. Development and CI implications:**
- No CI config changes needed.
- Local dev impact: zero (bind-mounts unaffected).

**6. Compatibility with existing architecture:**
- Fully compatible. The `make clean` target (L230-231) already does `rm -rf $(BACKUPS_DIR)/*.dump`, confirming `backups/` is treated as a local-only artifact directory.

**7. Viable alternatives:**
- (a) **Change the backup target** to write outside the repo root (e.g., `/tmp` or a system backups dir). Rejected — breaks existing workflow and the `make restore BACKUP_FILE=...` convention.
- (b) **Keep in `.gitignore` only, skip `.dockerignore`.** Rejected — doesn't prevent image baking.

**8. Dependency within the plan:**
- Standalone.

**9. Risk rating:** **High** — PII exposure via image baking; fix is a 2-line addition (one to each ignore file).

---

### F03: Stray root-level dev artifacts not in `.dockerignore`

**1. Implementation approach (preferred):**
Add `cat_output.txt`, `neq`, `Continue`, `cmp_css.py` to `.dockerignore`. All four are git-tracked (verified via `git ls-files`), small (3284 + 36 + 0 + 654 = 4,022 bytes total), and have no reference in any Dockerfile instruction, entrypoint script, or CI step. Audit recommends additionally reviewing for `.gitignore` inclusion since they should not be tracked in VCS at all.

**2. Risks and possible breakage:**
- **Low risk of breakage.** None of these files are imported, executed, or referenced by any Docker build step or runtime entrypoint. `cmp_css.py` (a one-off CSS comparison script, 654 B) is not invoked by `Makefile`, `Dockerfile`, or any CI job.
- The only risk: if a future developer references `cmp_css.py` from within a Dockerfile `RUN` step, the exclusion would silently break the build. Unlikely given current usage.

**3. Side effects:**
- `.dockerignore` entries don't affect bind-mounts (dev/test `.:/app` mounts). So dev mode with bind-mount still sees these files.
- If the files are ALSO added to `.gitignore`, they'd become tracked-but-ignored (git keeps them but won't see changes). The proper cleanup is `git rm --cached <file>` then add to `.gitignore`. The audit recommends this as a follow-up.

**4. Downstream impact:**
- Image size reduction: ~4 KB per build (negligible, but principle matters).
- No CI or test impact.

**5. Development and CI implications:**
- No CI config changes needed.
- Local dev: zero impact (bind-mount unaffected).
- If files are un-tracked from Git, developers lose them from local checkouts — but they appear to be debug artifacts, so this is acceptable. Recommend confirming with team before `git rm --cached`.

**6. Compatibility with existing architecture:**
- Fully compatible. No build or runtime path depends on these files.

**7. Viable alternatives:**
- (a) **Delete the files entirely** and remove from Git. This is the cleanest approach but is a more destructive action. The audit's recommendation to add to `.dockerignore` (and optionally `.gitignore`) is the conservative first step.
- (b) **Leave as-is.** Not recommended — principle of clean build context.

**8. Dependency within the plan:**
- Standalone.

**9. Risk rating:** **Medium** — low technical risk but a hygiene/security concern (debug output files in production images). The "Medium" rating reflects that some files are git-tracked (persistent in every checkout), unlike cache-dir artifacts that are ephemeral.

---

### F04: `.local/` directory not in `.dockerignore`

**1. Implementation approach (preferred):**
Add `.local/` to `.dockerignore`. The directory exists on disk with a `share/` subdirectory. It is not in `.gitignore` (verified: `git check-ignore .local/` returns nothing). It typically holds pyenv, pipx, or pip user-install artifacts.

**2. Risks and possible breakage:**
- **Low risk of breakage.** `.local/` is not referenced by any Dockerfile, entrypoint, or CI step. The project uses `python:3.14-slim` base + uv-managed venv at `/opt/venv`.
- **Risk of NOT fixing:** `.local/` could contain large Python builds (hundreds of MB if pyenv is used), bloating build context transfer. If pyenv's `.local/` shadows or conflicts with venv paths in any edge case, it could cause confusion — though the container's venv is at `/opt/venv`, isolated from the host's `.local/`.

**3. Side effects:**
- `.dockerignore` entry doesn't affect bind-mounts. In dev mode (bind-mount `.:/app`), `.local/` is still visible inside the container if present on the host.
- Should also add to `.gitignore` for consistency (it's missing from both). The audit focuses on `.dockerignore`; adding to `.gitignore` is a complementary hygiene step.

**4. Downstream impact:**
- Build context size reduction (variable — could be small or large depending on host's `.local/` contents).
- No runtime impact.

**5. Development and CI implications:**
- No CI config changes.
- Local dev: zero (bind-mount unaffected).

**6. Compatibility with existing architecture:**
- Fully compatible. The project has no pyenv/venv path dependency on `.local/`.

**7. Viable alternatives:**
- (a) **Narrow the pattern** to common pyenv directories like `.local/lib/python*/` instead of the whole `.local/`. Rejected — broader pattern is safer and standard.
- (b) **Add to `.gitignore` only.** Insufficient — doesn't prevent Docker context inclusion.

**8. Dependency within the plan:**
- Standalone.

**9. Risk rating:** **Low** — pure waste reduction; no functional risk.

---

### F05: `scripts/` temp/profiling artifacts not in `.gitignore` or `.dockerignore`

**1. Implementation approach (preferred):**
Add `scripts/_tmp_pytest_run.txt`, `scripts/_tmp_pytest_out.txt`, and `scripts/session_context.json` to both `.gitignore` and `.dockerignore`. Sizes verified: 193,180 B, 16,660 B, 92,743 B (total ~302 KB per audit). None are git-tracked or gitignored.

**2. Risks and possible breakage:**
- **Low risk of breakage.** These are temp/profiling files, not referenced by any build or runtime path.
- **Risk of NOT fixing:** ~302 KB of unnecessary context transfer per build. More importantly, `session_context.json` (92 KB) may contain internal test state, conversation metadata, or session logs that should not be in a distributed image.

**3. Side effects:**
- Adding to `.gitignore` means these files (if currently tracked) would need `git rm --cached`. Verify they are NOT git-tracked first (recommended: run `git ls-files scripts/`). If untracked, no Git impact.
- `.dockerignore` entry doesn't affect bind-mounts.

**4. Downstream impact:**
- Build context size reduction: ~302 KB.
- No runtime impact.

**5. Development and CI implications:**
- No CI config changes.
- Local dev: zero (bind-mount unaffected).
- Developers lose visibility of these temp files in Git (if they were committed) — acceptable for temp artifacts.

**6. Compatibility with existing architecture:**
- Fully compatible.

**7. Viable alternatives:**
- (a) **Pattern-based ignore** (`scripts/_tmp_*.txt`, `scripts/session_context.json`). Already the audit's recommendation. Could use a broader pattern like `scripts/_tmp_*` and `scripts/session_*` if more temp files are expected.
- (b) **Move temp files to a dedicated temp dir** outside `scripts/`. Rejected — unnecessary restructuring.

**8. Dependency within the plan:**
- Standalone.

**9. Risk rating:** **Low** — waste/metadata-exposure reduction; no functional risk.

---

### F06: `.playwright-mcp/` not in `.dockerignore`

**1. Implementation approach (preferred):**
Add `.playwright-mcp/` to `.dockerignore`. The directory exists (~701 KB across 3 files), is gitignored at `.gitignore` L233 (`.playwright-mcp/*`), but NOT dockerignored. It contains Playwright MCP browser/runtime artifacts from browser automation runs.

**2. Risks and possible breakage:**
- **Low risk of breakage.** `.playwright-mcp/` is not referenced by any Dockerfile, entrypoint, or CI step. The project's CI (`ci.yml`) uses `astral-sh/setup-uv@v5` and does not invoke Playwright browser automation in the Docker build.
- **Risk of NOT fixing:** ~701 KB of Playwright browser binaries/cache transferred per build. Playwright MCP artifacts can be large and contain platform-specific binaries.

**3. Side effects:**
- `.dockerignore` entry doesn't affect bind-mounts (dev/test `.:/app`).
- The `.gitignore` already excludes these files, so no Git impact.

**4. Downstream impact:**
- Build context size reduction: ~701 KB.
- No runtime impact.

**5. Development and CI implications:**
- No CI config changes.
- Local dev: zero (bind-mount unaffected).

**6. Compatibility with existing architecture:**
- Fully compatible.

**7. Viable alternatives:**
- (a) **Narrower pattern** like `.playwright-mcp/cache/` or specific file types. Rejected — broad `.playwright-mcp/` is standard and safe.
- (b) **No action.** Not recommended — unnecessary context transfer.

**8. Dependency within the plan:**
- Standalone.

**9. Risk rating:** **Low** — waste reduction; no functional risk.

---

### F07: `docker/nginx/` configs not in `.dockerignore`

**1. Implementation approach (preferred):**
Add `docker/nginx/` to `.dockerignore`. The `docker/` directory must remain in the build context for `COPY docker/entrypoint*.sh /app/` (Dockerfile L124), but `docker/nginx/` subdirectory contains nginx configs (`nginx.conf` 6,273 B, `nginx.dev.conf` 5,860 B) that are NEVER referenced by any Dockerfile instruction. They are ONLY bind-mounted at runtime by the `nginx` compose service (docker-compose.yml L203: `./docker/nginx/nginx.conf:/etc/nginx/nginx.conf:ro`, dev override L91).

**2. Risks and possible breakage:**
- **Low risk of breakage.** The `docker/nginx/` files are not needed in the image. The entrypoint scripts (`docker/entrypoint*.sh`) are at the top level of `docker/`, NOT inside `docker/nginx/`. Adding `docker/nginx/` to `.dockerignore` does NOT exclude `docker/entrypoint*.sh` — the `COPY docker/entrypoint*.sh` glob matches the top-level `docker/` directory's `.sh` files, which are not under `docker/nginx/`.
- **Critical verification:** `dockerignore` uses path-matching similar to gitignore. The pattern `docker/nginx/` excludes only the `nginx/` subdirectory within `docker/`. The pattern `docker/entrypoint*.sh` (implied by the `COPY` instruction) is unaffected. Verified: entrypoint scripts are at `docker/entrypoint.sh`, `docker/entrypoint-seed.sh`, etc. — NOT under `docker/nginx/`.

**3. Side effects:**
- `.dockerignore` entry doesn't affect bind-mounts. The dev/test compose files bind-mount specific files individually (`docker-compose.dev.override.yml` L21-23, `docker-compose.test.yml` L71-72), not the whole `docker/nginx/` directory. So runtime bind-mounts are unaffected.
- The production compose (`docker-compose.prod.yml` L30, L54) bind-mounts `.env.docker` only; the nginx service in `docker-compose.yml` L203 bind-mounts `./docker/nginx/nginx.conf` individually. All unaffected by `.dockerignore`.

**4. Downstream impact:**
- Build context size reduction: ~12 KB (negligible, but principle matters).
- No runtime impact — all nginx config access is via individual file bind-mounts, not via the baked image.

**5. Development and CI implications:**
- No CI config changes.
- Local dev: zero (bind-mounts unaffected).

**6. Compatibility with existing architecture:**
- Fully compatible. Verified that the 3-stage Dockerfile, bind-mount dev workflow, and test-runtime stage do not reference `docker/nginx/` in any `COPY` instruction.

**7. Viable alternatives:**
- (a) **Narrow the pattern** to exclude specific files (`docker/nginx/*.conf`). The directory pattern `docker/nginx/` is cleaner and future-proofs against new nginx config files.
- (b) **No action.** Not recommended — violates the Dockerfile-inputs precision principle.

**8. Dependency within the plan:**
- Standalone.

**9. Risk rating:** **Low** — waste reduction with a subtle but verified non-impact on the `COPY docker/entrypoint*.sh` glob.

---

### F08: `uv`/`uvx` binaries in runtime image (~30 MB)

**1. Implementation approach (preferred):**
Two-part change applied in lockstep:

**Part A — Script changes (do FIRST or simultaneously):** Replace `uv run python` with `/opt/venv/bin/python` in the 4 production auxiliary entrypoint scripts:
- `entrypoint-catalog.sh` L17: `exec uv run python src/backend/manage.py load_catalog --no-rewrite` → `exec /opt/venv/bin/python src/backend/manage.py load_catalog --no-rewrite`
- `entrypoint-create-admin.sh` L24: `exec uv run python src/backend/manage.py create_admin_user ...` → `exec /opt/venv/bin/python src/backend/manage.py create_admin_user ...`
- `entrypoint-seed.sh` L18 & L32: `uv run python -c "..."` and `exec uv run python ...` → `/opt/venv/bin/python`
- `entrypoint-scheduler.sh` L21: `exec uv run python -c "..."` → `exec /opt/venv/bin/python`

This mirrors the existing pattern in `entrypoint.sh` (L41, L60, L75) which already uses `/opt/venv/bin/python` directly. The `compile_messages()` function (entrypoint.sh L73-79) also uses `/opt/venv/bin/python` (L75).

**Part B — Dockerfile change (after Part A):** Move the `uv`/`uvx` COPY from the `runtime` stage (Dockerfile L110-111) to ONLY the `test-runtime` stage (after L165). The `runtime` stage no longer copies `uv`/`uvx`.

**2. Risks and possible breakage:**
- **Risk if Part B is done BEFORE Part A:** All 4 auxiliary production scripts (`entrypoint-catalog.sh`, `entrypoint-create-admin.sh`, `entrypoint-seed.sh`, `entrypoint-scheduler.sh`) would fail with "command not found: uv" → `exit 127`. These services would crash-loop in production. **High risk.** This is why Part A must precede or be simultaneous with Part B.
- **Risk after both parts:** The `runtime` stage image is ~30 MB smaller (removes `uv` binary + `uvx`). Attack surface is reduced.
- **`entrypoint.sh` (primary web entrypoint):** Already uses `/opt/venv/bin/python` — no change needed. `CMD ["gunicorn", ...]` (L155) resolves via `PATH="/opt/venv/bin:${PATH}"` (L128) — no `uv` needed. Verified.
- **Builder stage (L78):** Uses `uv run python manage.py compilemessages` and `uv run python manage.py collectstatic` — but this is the **builder** stage, which has its own `uv` install (Dockerfile L24: `COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/`). The builder stage is not affected by removing `uv` from the runtime stage. Verified — no change needed here.

**3. Side effects:**
- **`entrypoint-test.sh` still uses `uv`** (L16: `uv sync`, L19-20: `uv run python`, L41: `uv run pytest`). This script runs ONLY in the `test-runtime` stage, which KEEPS `uv` after the change. Verified: docker-compose.test.yml L50 specifies `target: test-runtime`, and entrypoint-test.sh is only bind-mounted for the test service (L72). No breakage.
- **Dev environment:** Dev services (docker-compose.dev.override.yml) use the default build target = last `FROM` = `test-runtime` (no `target:` specified in dev compose). So dev images still have `uv`. But the 4 aux scripts in dev would now use `/opt/venv/bin/python` instead of `uv run python` — this is correct since `/opt/venv` exists in the image. Dev bind-mounts (`.:/app`) are unaffected. Verified.
- **`UV_NO_INSTALL_PROJECT` / `UV_FROZEN`:** These env vars (runtime stage L137-138) are only relevant for `uv run` invocations. After the change, production aux scripts don't use `uv run`, so these env vars become inert for those scripts (but are still needed for entrypoint-test.sh's `uv sync`). No conflict.
- **`entrypoint.sh` comment at L109** (Dockerfile) says "needed for dev mode `uv run` commands and entrypoint scripts" — this comment becomes inaccurate and should be updated or removed.

**4. Downstream impact:**
- **Image size:** Runtime image shrinks by ~30 MB (`uv` ~20-30 MB + `uvx`).
- **CI:** The CI `build` job (ci.yml L16-24) builds the default Dockerfile target (last `FROM` = `test-runtime`). Since test-runtime KEEPS `uv`, CI is unaffected. If CI is ever changed to build `--target runtime`, the aux scripts would now work without `uv` — improvement.
- **Production deployments:** The prod image (built with `--target runtime`) would no longer contain `uv`. All entrypoint scripts use `/opt/venv/bin/python` or resolve `python` via PATH. Verified.
- **Security:** Reduced attack surface — `uv` is a package manager that could be abused if the container is compromised.

**5. Development and CI implications:**
- **CI config changes:** None required. CI builds `test-runtime` (default target) which retains `uv`.
- **Local dev impact:** Dev compose uses `test-runtime` (default target), so `uv` is still present. The Makefile targets `make lint`, `make typecheck`, `make makemigrations`, etc. use `uv run` inside the `web` container — these still work because dev's `web` image is `test-runtime` (has `uv`). Verified: docker-compose.dev.override.yml does NOT specify `target:`, so it defaults to the last `FROM` = `test-runtime`.
- **Build reproducibility:** The `UV_NO_INSTALL_PROJECT=1` and `UV_FROZEN=1` env vars (L137-138) make `uv run` in the runtime stage a no-op sync. After removing `uv` from runtime, these vars are harmless no-ops (only relevant to test-runtime's `uv sync`).

**6. Compatibility with existing architecture:**
- **3-stage Dockerfile:** Compatible. The `uv`/`uvx` COPY moves from `runtime` (L110-111) to `test-runtime` (after L165). The `FROM runtime AS test-runtime` inheritance ensures all runtime artifacts are already copied; only `uv`/`uvx` is added back at the test-runtime level.
- **Bind-mount dev workflow:** Compatible. Dev uses `test-runtime` (has `uv`). Aux scripts use `/opt/venv/bin/python` (present in all stages).
- **Test-runtime stage:** Compatible. `entrypoint-test.sh` uses `uv sync` (L16) and `uv run` (L19-20, L41) — `uv` is copied into `test-runtime` after the move.

**7. Viable alternatives:**
- (a) **Option (b) from the audit:** Set `ENV VIRTUAL_ENV=/opt/venv` so `python` resolves to the venv without `uv run`. This would allow keeping `uv run` in scripts while still benefiting from PATH resolution. But this doesn't remove `uv`/`uvx` from the image — it's a complementary optimization, not a replacement for F08's goal of removing `uv` from the runtime stage. The direct `/opt/venv/bin/python` approach is cleaner and proven (already used by `entrypoint.sh`).
- (b) **Keep `uv` in runtime, accept the ~30 MB.** Not recommended — increases image size and attack surface unnecessarily.
- (c) **Use `$VIRTUAL_ENV/bin/python` instead of hardcoded `/opt/venv/bin/python`.** Adds indirection and depends on `VIRTUAL_ENV` being set. The hardcoded path is more robust (matches `entrypoint.sh`'s existing pattern).

**8. Dependency within the plan:**
- **Part A (script changes) must precede or be simultaneous with Part B (Dockerfile change).** If Part B lands first, production aux services crash-loop.
- Independent of all `.dockerignore` changes (F01-F07, F09-F15) and `compilemessages` flag changes (F16-F17).

**9. Risk rating:** **High** — but only due to ordering risk (Part B before Part A causes production outages). If implemented in the correct order (A then B, or A+B together), the risk drops to **Low**. The ~30 MB image bloat and attack surface are the standing risk if not fixed.

---

### F09: `.mo`/`.pot` compiled translations not in `.dockerignore`

**1. Implementation approach (preferred):**
Add `*.mo` and `*.pot` to `.dockerignore`. Three `.mo` files verified on disk: `src/backend/locale/ru/LC_MESSAGES/django.mo` (29,528 B), `bs/.../django.mo` (22,294 B), `en/.../django.mo` (387 B). Total: 52,209 B. These are gitignored at `.gitignore` L55-56 but NOT dockerignored.

**2. Risks and possible breakage:**
- **Low risk of breakage.** The Dockerfile regenerates `.mo` from `.po` at L78 (`compilemessages`). The `.po` files (which ARE needed) are correctly not excluded.
- **Risk of NOT fixing:** ~52 KB of stale `.mo` files transferred per build. More critically, if `compilemessages` (Dockerfile L78) ever fails or is skipped, stale host translations would be baked into the image — a silent correctness risk for i18n (`ru`/`bs`/`en` translations could be stale).

**3. Side effects:**
- After the fix, the build context won't contain `.mo` files. The `compilemessages` step at Dockerfile L78 regenerates them fresh. Verified: `LOCALE_PATHS = [BASE_DIR / "backend" / "locale"]` (base.py L62), and `.po` files exist in `src/backend/locale/{ru,bs,en}/LC_MESSAGES/`.
- `.dockerignore` entry doesn't affect bind-mounts. In dev/test, `.mo` files from the host are still visible via bind-mount — this is correct (dev may have pre-compiled `.mo` for fast iteration).

**4. Downstream impact:**
- Build context size reduction: ~52 KB.
- The runtime `compilemessages` (entrypoint.sh L75) still regenerates `.mo` at container startup, overwriting any stale files. With `.mo` excluded from the build context, the builder stage's `COPY . .` won't include stale `.mo`. Verified.
- No test or CI impact.

**5. Development and CI implications:**
- No CI config changes.
- Local dev: zero (bind-mount unaffected).
- `make compilemessages` (Makefile L152-155) runs inside the container with the bind-mount — still works, still sees host `.po` files, regenerates `.mo`.

**6. Compatibility with existing architecture:**
- Fully compatible. The `.po` files (`.gitignore` L55 only ignores `*.mo`/`*.pot`, not `*.po`) remain in the build context. Verified: `git ls-files '*.po'` would show the tracked `.po` files.

**7. Viable alternatives:**
- (a) **Glob pattern** `*.mo` and `*.pot` (audit's recommendation). Standard and correct.
- (b) **Path-scoped** `**/LC_MESSAGES/django.mo`. More precise but less future-proof if locale file naming changes. The broad glob is preferred.

**8. Dependency within the plan:**
- Standalone. Independent of F16/F17 (which deal with `compilemessages` flags, not `.mo` file inclusion).

**9. Risk rating:** **Medium** — low technical risk, but the stale-translation correctness concern (if `compilemessages` fails) pushes it above "Low". The fix is a 2-line `.dockerignore` addition.

---

### F10: `.gitattributes` not in `.dockerignore`

**1. Implementation approach (preferred):**
Add `.gitattributes` to `.dockerignore`. The file (302 B) exists on disk, is git-tracked, and contains LF line-ending rules. It has no relevance inside a Docker image.

**2. Risks and possible breakage:**
- **None.** `.gitattributes` is a Git-only configuration file. No Dockerfile, entrypoint, or CI step reads it.
- The audit notes a credential hygiene concern: `.gitattributes` can contain path-rewrite rules. The current file only has line-ending rules (verified: 302 B, standard template).

**3. Side effects:**
- `.dockerignore` entry doesn't affect bind-mounts.
- Adding to `.gitignore` is NOT recommended here — `.gitattributes` is intentionally git-tracked (it's a project-wide config that should be in VCS). Only `.dockerignore` should exclude it.

**4. Downstream impact:**
- Build context size reduction: 302 B (negligible).
- No runtime impact.

**5. Development and CI implications:**
- No CI config changes.
- Local dev: zero.

**6. Compatibility with existing architecture:**
- Fully compatible.

**7. Viable alternatives:**
- (a) **Leave `.gitattributes` in the image.** Not recommended — it's dead weight. 302 B is negligible, but the principle of clean images applies.

**8. Dependency within the plan:**
- Standalone.

**9. Risk rating:** **Low** — pure hygiene; no functional risk.

---

### F11: `.python-version` not in `.dockerignore`

**1. Implementation approach (preferred):**
Add `.python-version` to `.dockerignore`. The file (5 B, content: `3.14`) exists on disk, is git-tracked (intentionally committed — `.gitignore` L88 has it commented out with note "you might want to ignore these files since the code is intended to run in multiple environments; otherwise, check them in"). The base image is `python:3.14-slim` (Dockerfile L8, L84), so the version is already pinned by the base image.

**2. Risks and possible breakage:**
- **Low risk of breakage.** `.python-version` is consumed by pyenv/asdf at local dev time. Inside the container, there is no pyenv; uv uses its own managed Python or the system Python from the base image.
- **Risk of NOT fixing:** 5 bytes of irrelevant metadata in the build context. The audit notes a behavioral risk: if `uv` is ever configured with `UV_PYTHON_PREFERENCE=pin` or similar (reads `.python-version`), the file's presence could cause unexpected Python resolution. Currently, no such setting is configured (verified: Dockerfile sets `UV_LINK_MODE`, `UV_COMPILE_BYTECODE`, `UV_PROJECT_ENVIRONMENT`, `UV_NO_INSTALL_PROJECT`, `UV_FROZEN` — no `UV_PYTHON_PREFERENCE`).

**3. Side effects:**
- `.dockerignore` entry doesn't affect bind-mounts. In dev/test, the host's `.python-version` is visible via bind-mount — correct for local uv resolution.
- Do NOT add to `.gitignore` — the project intentionally commits `.python-version` (commented gitignore entry with guidance). Only `.dockerignore` should exclude it.

**4. Downstream impact:**
- Build context size reduction: 5 B (negligible, but principle matters).
- No runtime impact.

**5. Development and CI implications:**
- No CI config changes.
- Local dev: zero (bind-mount unaffected; host `.python-version` still used by dev `uv`).

**6. Compatibility with existing architecture:**
- Fully compatible.

**7. Viable alternatives:**
- (a) **Leave as-is.** Not recommended — principle of clean images.
- (b) **Remove from Git and add to `.gitignore`.** Rejected — the project intentionally tracks `.python-version` for consistency across developer environments.

**8. Dependency within the plan:**
- Standalone.

**9. Risk rating:** **Low** — pure hygiene; no functional risk.

---

### F12: Missing standard Python tool cache directories in `.dockerignore`

**1. Implementation approach (preferred):**
Add `.tox/`, `.nox/`, `.pyre/`, `.pytype/`, `__pypackages__/`, `.profile_default/`, `.pdbrc`, `.python-eggs/` to `.dockerignore` (matching the audit's recommendation). These patterns exist in `.gitignore` (L41, L42, L175, L178, L122, L82) but are NOT in `.dockerignore`. The project uses `basedpyright` (not `mypy`), but `.mypy_cache` is already dockerignored — the audit recommends aligning with the full standard template.

**2. Risks and possible breakage:**
- **None.** These are all cache directories that are never needed inside a container image. The project doesn't use `tox`, `nox`, `pyre`, `pytype`, or `__pypackages__` (verified: dependencies are managed by `uv` with `UV_PROJECT_ENVIRONMENT=/opt/venv`).
- **Risk of NOT fixing:** If a developer runs any of these tools locally, the resulting cache directories (potentially large, platform-specific) would enter the build context via `COPY . .` (Dockerfile L57).

**3. Side effects:**
- `.dockerignore` entries don't affect bind-mounts. Dev/test `.:/app` bind-mounts still expose these cache dirs if present on the host.
- Should also verify alignment: the project gitignores `.mypy_cache/` (L170) and `.ruff_cache/` (L204) — both already in `.dockerignore` (L59-60). The new additions (`.tox/`, `.nox/`, etc.) follow the same pattern.

**4. Downstream impact:**
- Build context size reduction (variable — only present if local tools have been run).
- No runtime impact.

**5. Development and CI implications:**
- No CI config changes.
- Local dev: zero (bind-mount unaffected).

**6. Compatibility with existing architecture:**
- Fully compatible.

**7. Viable alternatives:**
- (a) **Minimal set only** (e.g., just `.tox/`, `.nox/`). The audit's broader recommendation (`.pyre/`, `.pytype/`, `__pypackages__/`, `.profile_default/`, `.pdbrc`, `.python-eggs/`) provides defense-in-depth against future tooling adoption. Preferred.
- (b) **Align `.dockerignore` with `.gitignore` programmatically** (e.g., symlink or copy). Over-engineering for this project — manual additions are clearer.

**8. Dependency within the plan:**
- Standalone.

**9. Risk rating:** **Low** — defensive hygiene; no functional risk.

---

### F13: Missing build artifacts (`*.manifest`, `*.spec`) in `.dockerignore`

**1. Implementation approach (preferred):**
Add `*.manifest` and `*.spec` to `.dockerignore`. These patterns exist in `.gitignore` (L32-33, under the PyInstaller section) but are NOT in `.dockerignore`. No such files currently exist on disk.

**2. Risks and possible breakage:**
- **None.** No `.manifest` or `.spec` files currently exist. This is purely defensive coverage.

**3. Side effects:**
- `.dockerignore` entries don't affect bind-mounts.
- No Git impact (patterns already in `.gitignore`).

**4. Downstream impact:**
- Zero current impact. Future-proofing against PyInstaller adoption.

**5. Development and CI implications:**
- No CI config changes.

**6. Compatibility with existing architecture:**
- Fully compatible.

**7. Viable alternatives:**
- (a) **Leave as-is.** Not recommended — the pattern gap is a latent risk if PyInstaller or similar packaging tooling is ever introduced.
- (b) **Broader PyInstaller coverage** (e.g., also `*.exe`, `*.dll`, `*.so` from frozen builds). Out of scope — the audit only recommends `*.manifest` and `*.spec`.

**8. Dependency within the plan:**
- Standalone.

**9. Risk rating:** **Low** — pure defensive coverage; no current risk.

---

### F14: Missing coverage/test artifacts in `.dockerignore`

**1. Implementation approach (preferred):**
Add `.coverage`, `.coverage.*`, `coverage.xml`, `htmlcov/`, `.hypothesis/` to `.dockerignore`. These patterns exist in `.gitignore` (L40, L43-44, L47, L50) but are NOT in `.dockerignore`. The `.coverage` file is verified on disk (167,936 B).

**2. Risks and possible breakage:**
- **None.** These are test/coverage artifacts that are regenerated and never needed inside a container image.
- **Risk of NOT fixing:** 168 KB of `.coverage` data (test execution metadata: timing, internal paths, code structure) transferred per build. If `coverage.xml`, `htmlcov/`, or `.hypothesis/` are generated locally before a build, they would also enter the context.

**3. Side effects:**
- `.dockerignore` entries don't affect bind-mounts.
- No Git impact (patterns already in `.gitignore`).

**4. Downstream impact:**
- Build context size reduction: at minimum 168 KB (the `.coverage` file); potentially more if `coverage.xml`/`htmlcov/` are present.
- No runtime impact.

**5. Development and CI implications:**
- No CI config changes.
- Local dev: zero (bind-mount unaffected).
- CI: the CI `test` job generates `coverage.xml` (ci.yml L91 `--cov-report=xml`) but uploads it as an artifact (L94-99) — this is in CI, not in the Docker build context, so no conflict.

**6. Compatibility with existing architecture:**
- Fully compatible.

**7. Viable alternatives:**
- (a) **Pattern grouping** (`coverage*`). The explicit patterns are clearer and avoid accidentally excluding files like `coverage_report.py`. Preferred.

**8. Dependency within the plan:**
- Standalone.

**9. Risk rating:** **Medium** — metadata exposure (test execution data, internal paths); fix is straightforward. The 168 KB is currently on disk.

---

### F15: Missing runtime artifacts in `.dockerignore`

**1. Implementation approach (preferred):**
Add `celerybeat-schedule`, `celerybeat.pid`, `*.rdb`, `*.aof`, `*.pid`, `.gunicorn/` to `.dockerignore`. These patterns exist in `.gitignore` (L125-131, L236) but are NOT in `.dockerignore`. The `.gunicorn/` directory is verified on disk.

**2. Risks and possible breakage:**
- **None.** These are runtime state files (lock files, PID files, Redis persistence) that are never needed inside a static container image.
- **Risk of NOT fixing:** If Redis (`redis:7-alpine`, docker-compose.yml L22) or Gunicorn has been run locally, stale PID/sock/RDB files could enter the build context via `COPY . .` (Dockerfile L57) and be copied into the builder stage's `/app/` directory. While the runtime stage selectively copies only needed paths, the builder stage still carries this dead weight in an intermediate layer. The audit notes this is primarily a builder-stage waste issue, not a runtime-stage correctness issue.

**3. Side effects:**
- `.dockerignore` entries don't affect bind-mounts.
- No Git impact (patterns already in `.gitignore`).
- The `*.pid` pattern could potentially match legitimate files, but none exist in this project (verified: no `.pid` files on disk).

**4. Downstream impact:**
- Build context size reduction: variable (depends on whether Redis/Gunicorn has been run locally).
- No runtime impact — the runtime stage copies source via `COPY --from=builder --chown=app:app /app/src /app/src` (L114), and stale runtime artifacts in the builder layer are not promoted to the final image.

**5. Development and CI implications:**
- No CI config changes.
- Local dev: zero (bind-mount unaffected).

**6. Compatibility with existing architecture:**
- Fully compatible. Verified that the runtime stage's `COPY` instructions (L106-121) only copy specific paths from the builder, not wholesale `COPY . .`.

**7. Viable alternatives:**
- (a) **Scope narrower** to `.gunicorn/` and `celerybeat-schedule` only. The broader patterns (`*.rdb`, `*.aof`, `*.pid`) provide defense-in-depth against local Redis/RabbitMQ runs. Preferred.

**8. Dependency within the plan:**
- Standalone.

**9. Risk rating:** **Medium** — stale runtime state (PIDs, locks) in build context is a correctness risk; `.gunicorn/` verified on disk.

---

### F16: `compilemessages` `--ignore` list incomplete in entrypoint and Makefile

**1. Implementation approach (preferred):**
Expand the `--ignore` list in `entrypoint.sh` (L76) and `Makefile` (L154) from:
```
--ignore=.venv --ignore=.git --ignore=.kilo --ignore=__pycache__ --ignore='*.pyc'
```
to:
```
--ignore=.venv --ignore=.git --ignore=.kilo --ignore=__pycache__ --ignore='*.pyc' \
--ignore=.mypy_cache --ignore=.ruff_cache --ignore=.pytest_cache --ignore=node_modules \
--ignore=.tox --ignore=.nox --ignore=__pypackages__ --ignore=.uv --ignore=.cache \
--ignore=.local --ignore=.playwright-mcp --ignore=.coverage --ignore=.hypothesis
```
This matches the audit's recommended expansion. Both locations already have `--locale ru --locale bs --locale en` flags (verified on disk).

**2. Risks and possible breakage:**
- **Low risk of breakage.** Django's `compilemessages` walks `LOCALE_PATHS` (base.py L62: `src/backend/locale/`) recursively. The `--ignore` flags prune directories from the walk. Adding more `--ignore` flags only makes the walk faster and more defensive — it cannot exclude valid `.po` files under `src/backend/locale/` because those directories (`.mypy_cache`, `.ruff_cache`, etc.) don't exist under `locale/`.
- **Risk of NOT fixing:** In dev mode, the `.:/app` bind-mount (docker-compose.dev.override.yml L22, docker-compose.test.yml L70) exposes the full repo. If any tool cache directory (e.g., `.venv`) contains a `LC_MESSAGES/django.po` subdirectory (e.g., from a stale branch or vendored dependency), it would be compiled. The spec file (`.ai/problems/14_compilemessages-docker-hang_spec.md`) documents that Django's `compilemessages` has `default=[]` for ignore patterns (L65 of Django source), confirming zero default ignore patterns.

**3. Side effects:**
- The `--ignore` list becomes longer but more comprehensive. No functional change to which `.po` files are compiled (project locales only).
- In dev mode, the bind-mount means these cache directories are still visible to `compilemessages` — the expanded `--ignore` list ensures they're pruned from the walk.

**4. Downstream impact:**
- Dev/test startup: `compilemessages` (entrypoint.sh L75) runs faster (fewer directories walked). In the dev bind-mount scenario, `.venv` can contain thousands of third-party locale directories (the spec notes 14 locale directories in `.venv` — Django, django-filter, django-mptt). The existing `.venv` ignore already handles this (F16's fix was already applied at commit `ba5c65e`). The additional ignore flags provide defense against other cache directories.
- No CI impact — CI runs in a clean checkout (no local caches).
- No production impact — production images don't have these cache directories.

**5. Development and CI implications:**
- No CI config changes.
- Local dev: the `make compilemessages` target (L152-155) would use the expanded ignore list — faster local runs.
- The `entrypoint.sh` `compile_messages()` function (L73-79) wraps the call with `|| echo WARNING` (L78), so even if the expanded flags cause an issue, the container starts (non-fatal fallback).

**6. Compatibility with existing architecture:**
- Fully compatible. The `--locale ru --locale bs --locale en` flags match the project's `LANGUAGES` setting (base.py L57-61). The `compilemessages` command's `action="append"` for `--locale` (Django 5.2.16 source, confirmed in spec) means repeated `--locale` flags are correct (no comma-splitting).

**7. Viable alternatives:**
- (a) **Extract `compilemessages` into a shared script** to ensure all four invocation sites stay in sync. The audit suggests this. This is a larger refactor (affects F17 too) but eliminates the consistency hazard. Higher effort, higher benefit.
- (b) **Use a Makefile variable** for the ignore flags, then reference it in both Makefile and (if possible) entrypoint. The entrypoint is a shell script, not Make — can't directly share. A shared shell function or script is the way.

**8. Dependency within the plan:**
- F16 should be applied together with F17 for consistency (all four `compilemessages` invocation sites should use the same flags).
- Independent of `.dockerignore` changes and F08.

**9. Risk rating:** **Low** — performance and defensive improvement; non-fatal fallback protects against any issue.

---

### F17: `compilemessages` in Dockerfile build and CI lacks `--ignore`/`--locale` flags

**1. Implementation approach (preferred):**
Add `--ignore` and `--locale ru --locale bs --locale en` flags to the three flag-less `compilemessages` invocations:
- **Dockerfile L78:** `uv run python src/backend/manage.py compilemessages` → `uv run python src/backend/manage.py compilemessages --ignore=.venv --ignore=.git --ignore=.kilo --ignore=__pycache__ --ignore='*.pyc' --ignore=.mypy_cache --ignore=.ruff_cache --ignore=.pytest_cache --ignore=node_modules --ignore=.tox --ignore=.nox --ignore=__pypackages__ --ignore=.uv --ignore=.cache --ignore=.local --ignore=.playwright-mcp --ignore=.coverage --ignore=.hypothesis --locale ru --locale bs --locale en`
- **CI ci.yml L83:** `uv run python manage.py compilemessages` → same flags
- **CI ci.yml L176:** `uv run python manage.py compilemessages` → same flags

**2. Risks and possible breakage:**
- **Low risk of breakage.** The Dockerfile build is protected by `.dockerignore` (which excludes `.venv`, `.git`, `.kilo`, etc. from the build context). The `--ignore` flags provide defense-in-depth. The `--locale ru --locale bs --locale en` flags match the project's `LANGUAGES` setting and the existing entrypoint/Makefile invocations.
- **Risk of NOT fixing:** Inconsistency across the four `compilemessages` invocation sites. If a future refactor runs cache-generating tools in the same CI job before `compilemessages` (e.g., `basedpyright` or `ruff` generating `.mypy_cache`/`.ruff_cache`), stale `.po` files in those cache directories could be compiled. The CI `test` job (ci.yml) runs `compilemessages` at L83 after `uv sync` + `migrate` — currently no cache-generating tools run in the same job, but the `lint` and `typecheck` jobs (L101, L119) are separate, so the risk is low. Still, consistency matters for maintainability.

**3. Side effects:**
- CI `compilemessages` step becomes more explicit and consistent with entrypoint/Makefile.
- The Dockerfile build-time `compilemessages` (L78) already produces correct `.mo` files (verified: the runtime `compilemessages` at entrypoint.sh L75 overwrites them at startup). Adding flags makes the build-time and runtime invocations consistent.
- No change to which `.po` files are compiled (project locales only).

**4. Downstream impact:**
- **Dockerfile build:** No impact — `.dockerignore` already handles context filtering. The `--ignore` flags are defense-in-depth.
- **CI:** No impact — clean checkout. The `--locale` flags ensure only `ru`/`bs`/`en` are compiled, matching `LANGUAGES`.
- **No runtime impact.**

**5. Development and CI implications:**
- **CI config changes:** Required — ci.yml L83 and L176 need the flags added.
- **Local dev:** The Dockerfile change affects image builds only (not bind-mount dev mode). CI changes affect CI builds only.

**6. Compatibility with existing architecture:**
- Fully compatible. The `--locale ru --locale bs --locale en` flags use `action="append"` (Django 5.2.16 confirmed), so no comma-splitting issue. The `--ignore` patterns match `.dockerignore` coverage.

**7. Viable alternatives:**
- (a) **Create a shared script** (e.g., `docker/compile-messages.sh`) that all four invocation sites call. Eliminates the consistency hazard entirely. Higher effort but better long-term. The audit suggests this for F16; applying it to F17 as well would solve both findings with one shared mechanism.
- (b) **Use `--locale` only (skip `--ignore` in CI/Dockerfile)** since `.dockerignore` handles context filtering. This is the minimum viable fix but doesn't provide defense-in-depth. Not recommended.

**8. Dependency within the plan:**
- F17 should be applied together with F16 for consistency.
- Independent of `.dockerignore` changes and F08.

**9. Risk rating:** **Low** — consistency and defense-in-depth improvement; no functional risk.

---

## Cross-Cutting Risk Analysis

### The `.dockerignore` expansion cluster (F01–F07, F09–F15)

All 13 `.dockerignore`/`.gitignore` additions are **fully independent** and can be applied in a single commit without risk of interaction. The critical constraint is that `.dockerignore` patterns must NOT break the `.env*` exclusion already at L5 (verified: the new patterns don't touch `.env*` matching). Additionally, `.dockerignore` entries must not inadvertently exclude files needed by `COPY . .` at Dockerfile L57 (source code, templates, static files) or `COPY docker/entrypoint*.sh` at L124.

**Verified safe boundaries:**
- F07 (`docker/nginx/`) does NOT exclude `docker/entrypoint*.sh` — confirmed entrypoint scripts are at the `docker/` top level, not under `docker/nginx/`.
- F09 (`*.mo`, `*.pot`) does NOT exclude `.po` files — `.gitignore` L55-56 only ignores `.mo`/`.pot`, and `compilemessages` reads `.po` files. Verified: `git ls-files '*.po'` shows tracked `.po` files.
- F10 (`.gitattributes`) — Git-only file, safe to exclude.
- F11 (`.python-version`) — pyenv-only file, safe to exclude from image (dev bind-mount still sees it).

### The `compilemessages` consistency cluster (F16, F17)

F16 and F17 should be applied together. The four `compilemessages` invocation sites are:
1. **Dockerfile L78** — build-time (F17: add flags)
2. **entrypoint.sh L75** — runtime, primary web entrypoint (already has flags per F16)
3. **Makefile L153** — developer invocation (already has flags per F16)
4. **CI ci.yml L83, L176** — CI build and i18n job (F17: add flags)

The ideal long-term solution is a shared script (audit's suggestion under F16 alternatives), but for immediate risk reduction, adding the flags directly is sufficient and low-risk.

### The `uv` removal cluster (F08)

F08 is the highest-complexity finding. The ordering constraint is critical: **Part A (script edits) must precede or be simultaneous with Part B (Dockerfile edit)**. A safe commit order is:
1. Commit Part A (4 script edits) — production still has `uv` in the image, scripts now use `/opt/venv/bin/python`, everything works.
2. Commit Part B (Dockerfile: move `uv`/`uvx` COPY to test-runtime) — now runtime stage is `uv`-free, but all runtime scripts already use `/opt/venv/bin/python`.

This two-commit approach allows rollback of Part B without rolling back Part A if any issue arises.

### Bind-mount invariance principle

All `.dockerignore` changes (F01–F07, F09–F15) follow the **bind-mount invariance principle**: `.dockerignore` only affects `docker build` (image builds, CI `build` job). It does NOT affect compose bind-mounts (`.:/app` in docker-compose.dev.override.yml L22 and docker-compose.test.yml L70). This means:
- Dev mode always sees the full repo (including `.venv`, `.mo`, etc.) via bind-mount — correct behavior.
- Test mode always sees the full repo + pre-built venv at `/opt/venv` via bind-mount — correct behavior.
- Production (pre-built image, no bind-mount) is the only environment that benefits from `.dockerignore` exclusions.

This principle is confirmed by the critical context: ".dockerignore only applies during `docker build` — it does NOT affect compose bind-mounts at runtime."

### The `.env*` pattern safety

The critical context warns: "The `.env*` pattern already excludes all env files from build context — adding `.gitignore`/`.dockerignore` patterns must NOT break this." Verified: none of the proposed additions (F01–F15) conflict with the `.env*` pattern at `.dockerignore` L5. The `.env*` pattern uses a glob that matches `.env`, `.env.docker`, `.env.local`, etc. — none of the new patterns overlap.

---

## Implementation Priority Order

| Priority | Findings | Rationale |
|----------|----------|-----------|
| **P0 — Immediate** | F01, F02, F08 | Credential/PII leak (F01, F02); image bloat + attack surface (F08) |
| **P1 — Short-term** | F09, F03, F14, F15 | Stale build artifacts and metadata exposure |
| **P2 — Medium-term** | F04, F05, F06, F10, F11, F12 | Waste reduction and cache hygiene |
| **P3 — Ongoing** | F13, F16, F17 | Defensive coverage and tooling consistency |

**Recommended commit strategy:**
1. **Commit 1:** F01 + F02 (security: `.dockerignore` additions for secrets + dumps)
2. **Commit 2:** F03 + F04 + F05 + F06 + F07 (build context waste cleanup)
3. **Commit 3:** F09 + F10 + F11 + F12 + F13 + F14 + F15 (`.dockerignore` additions for build artifacts/caches)
4. **Commit 4:** F08 Part A (4 entrypoint script edits)
5. **Commit 5:** F08 Part B (Dockerfile: move `uv`/`uvx` COPY to test-runtime) + update comment at L109
6. **Commit 6:** F16 + F17 (`compilemessages` flag consistency across all 4 sites)

This ordering ensures security fixes land first, `uv` removal is split across two commits (script changes verified before Dockerfile changes), and consistency changes are isolated last.
