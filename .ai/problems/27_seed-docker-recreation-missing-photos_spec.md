# Specification: Seed Data Not Appearing After Docker Container Recreation

**File:** `27_seed-docker-recreation-missing-photos_spec.md`
**Status:** Final (ready for implementation planning)
**Date:** 2026-08-23

---

## 1. Problem Statement

After fully recreating Docker containers (e.g., via `make clean && make up` or `docker compose down -v && docker compose up --build -d`), photos do not appear on the site at `http://localhost:8000/`. The 1,046 fixture JPEG files exist on disk at `src/backend/apps/seed/fixtures/images/` and all 1,004 manifest entries in `photo_manifest.json` reference files that exist locally. However, the photos are not visible on the site.

The seed workflow is documented in `docs/ops/seed-workflow.md` as a three-stage pipeline:
1. **Download** — JPEGs downloaded to `fixtures/images/` (standalone script)
2. **Seed** — `ImageGenerator` copies fixture JPEGs to `MEDIA_ROOT/seed/` inside the runtime volume
3. **Serve** — `media_gate` view serves images from `MEDIA_ROOT/seed/`

The investigation traced the entire pipeline and found **two independent root causes** working together, plus several latent issues that prevent a clean Docker recreation experience.

---

## 2. Confirmed Requirements

### 2.1 Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR01 | After `make up` (dev mode), the site at `http://localhost:8000/` must show ads with photos within a reasonable startup window | Must |
| FR02 | Recreating containers via `make clean && make up` must produce the same result as the first `make up` — photos must be present | Must |
| FR03 | The seed service must wait for the database to be ready before executing (no silent failures from premature startup) | Must |
| FR04 | The seed service must fix `media_volume` permissions before writing to it (no PermissionError on fresh volumes) | Must |
| FR05 | All one-shot service entrypoints (`seed`, `load_catalog`, `create_admin`) must share the same environment setup as the `web` service | Must |
| FR06 | If fixture JPEGs are missing, the seed must report a clear error or warning (not silently produce ads with zero images) | Must |
| FR07 | The `.env.docker` file must contain all variables needed for dev and production environments | Must |
| FR08 | After a successful seed, `media_gate` must serve seed images at `/media/seed/<filename>.jpg` for non-staff users viewing PUBLISHED ads | Must |

### 2.2 Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR01 | Dev mode startup time with seed dependency should not exceed 120 seconds for default seed parameters |
| NFR02 | Production mode must be unaffected — seed remains profile-gated and must NOT block `web` startup |
| NFR03 | The seed entrypoint must not introduce new dependencies beyond what `entrypoint.sh` already uses |
| NFR04 | All fixes must work on both Linux (Docker VM) and Windows (Docker Desktop) |

---

## 3. Conceptual Development Tasks

### Task 1: Add `seed` dependency to `web` service (dev mode only)

**Purpose:** Eliminate the race condition where `web` starts serving before `seed` has copied images to `media_volume`.

**Expected outcome:**
- In `docker-compose.dev.override.yml`, add `seed` as a `depends_on` with `condition: service_completed_successfully` to the `web` service.
- In the base `docker-compose.yml`, do NOT add this dependency (production uses profile-gated seed that must not block web).
- Verify that `docker compose up` in dev mode waits for seed to complete before web starts serving.

**Dependencies:** None. This is a compose file change only.

**Files affected:**
- `docker-compose.dev.override.yml`

### Task 2: Make one-shot service entrypoints call `entrypoint.sh` setup

**Purpose:** Ensure `seed`, `load_catalog`, and `create_admin` services perform DB readiness checks and volume permission fixes before running their commands, matching the behavior of `web` and `migrate` services.

**Expected outcome:**
- `entrypoint-seed.sh`, `entrypoint-catalog.sh`, and `entrypoint-create-admin.sh` source or call the setup functions from `entrypoint.sh` (`check_env_file`, `fix_volume_permissions`, `wait_for_db`, `wait_for_redis`).
- Alternative: refactor `entrypoint.sh` to expose its setup functions as sourceable functions, then have one-shot entrypoints import and call them.
- On fresh `media_volume` (after `docker compose down -v`), the seed service can write files without `PermissionError`.

**Dependencies:** None. Changes are to `docker/entrypoint-*.sh` files only.

**Files affected:**
- `docker/entrypoint-seed.sh`
- `docker/entrypoint-catalog.sh`
- `docker/entrypoint-create-admin.sh`
- `docker/entrypoint.sh` (potential refactor)

### Task 3: Add seed image presence check to `entrypoint-seed.sh`

**Purpose:** Prevent silent degradation when Git-ignored JPEG fixtures are not present in the container (fresh clone, CI, or image built without local JPEG files).

**Expected outcome:**
- Before running `manage.py seed`, check that `FIXTURES_IMAGES_DIR` contains at least one `.jpg` file.
- If no JPEGs found, print a clear warning and exit with a non-zero code (or proceed with a `--skip-images` flag if available).
- This check uses the existing `FIXTURES_IMAGES_DIR` path from `apps/seed/paths.py` (no new imports needed).

**Dependencies:** Task 2 (entrypoint refactor) is helpful but not required.

**Files affected:**
- `docker/entrypoint-seed.sh`

### Task 4: Reduce default `--ads` count for dev mode

**Purpose:** Reduce startup time in dev mode so `web` (which now waits for `seed`) starts serving sooner.

**Expected outcome:**
- In `docker-compose.dev.override.yml`, set `SEED_ADS=30` and `SEED_USERS=10` as environment variables for the `seed` service.
- This changes the default from 600 ads to 30 ads in dev mode, reducing seed time from ~60s to ~5-10s.
- Production retains `--ads=600` (base compose default via `${SEED_ADS:-600}`).

**Dependencies:** Task 1 (web waits for seed) makes this more important — lower ad count means shorter web startup delay.

**Files affected:**
- `docker-compose.dev.override.yml`

### Task 5: Complete `.env.docker` from `.env.docker.example`

**Purpose:** Ensure `.env.docker` contains all variables needed for both dev and production environments, preventing missing-variable failures.

**Expected outcome:**
- Add `REDIS_URL=redis://redis:6379/0` to `.env.docker` (needed for production Redis cache).
- Add `SITE_URL=http://localhost:8000` to `.env.docker` (needed for production prod.py guard).
- Add `SEED_USERS=10` and `SEED_ADS=30` to `.env.docker` (explicit dev defaults).
- Add `IMMEDIATE_ALERTS_ENABLED=false` to `.env.docker` (explicit default).
- Add `FIX_PERMISSIONS=0` to `.env.docker` (explicit default).
- Do NOT add `REGISTRY`, `REPOSITORY`, `IMAGE_TAG` — these have inline defaults in `docker-compose.prod.yml`.

**Dependencies:** None.

**Files affected:**
- `.env.docker`

### Task 6: Add `make down` target that preserves volumes

**Purpose:** Give developers a safe way to recreate containers without destroying `media_volume`, avoiding the need to re-seed photos every time.

**Expected outcome:**
- Add a `down` target to the Makefile that runs `docker compose down` (preserves volumes).
- Document `make clean` as the destructive variant (destroys volumes) in the Makefile help text.
- The existing `make down` target is renamed to `make down-clean` or `make reset` (which destroys volumes).

**Dependencies:** None.

**Files affected:**
- `Makefile`

### Task 7: Add seed image recovery procedure to documentation

**Purpose:** Document the recovery procedure for when seed images are missing (e.g., after `git clean -fdx` wipes JPEGs or after a fresh clone).

**Expected outcome:**
- Add a "Troubleshooting: Missing Photos" section to `docs/ops/seed-workflow.md` that covers:
  1. Verify JPEGs exist in `src/backend/apps/seed/fixtures/images/`
  2. If missing, download them: `uv run python scripts/download_seed_photos.py --all`
  3. Validate: `uv run python scripts/download_seed_photos.py --validate`
  4. Re-run seed: `make seed` or `docker compose run --rm seed`
  5. Verify media volume: `docker compose exec web ls -la /app/media/seed/`

**Dependencies:** Tasks 1-4 (the fixes above).

**Files affected:**
- `docs/ops/seed-workflow.md`

---

## 4. Product Owner Decisions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| D1 | Should `web` depend on `seed` completion in dev mode? | **YES — dev override only.** Add `seed` to `web`'s `depends_on` in `docker-compose.dev.override.yml`. Do NOT add to base `docker-compose.yml` (prod seed is profile-gated). | In dev mode, the user expects a complete site immediately. Blocking web until seed completes ensures ads and images are present. Production seed is opt-in via `--profile seed` and must NOT block. |
| D2 | Should seed/default ad count for dev be reduced? | **YES — `SEED_ADS=30` in dev override.** | 600 ads with images takes ~60s in dev; 30 ads is sufficient for visual evaluation and takes ~5-10s. Matches `.env.example` default of `SEED_ADS=30`. |
| D3 | Should `entrypoint-seed.sh` call `entrypoint.sh` or its setup functions? | **YES — source setup functions.** Refactor `entrypoint.sh` to expose `check_env_file`, `fix_volume_permissions`, `wait_for_db`, `wait_for_redis` as sourceable functions. Have one-shot entrypoints source and call them. | Ensures DB readiness and volume permissions are fixed before seed runs. Prevents silent failures on fresh volumes. `wait_for_db` is especially important because seed bypasses the Dockerfile's default entrypoint. |
| D4 | Should `make clean` preserve `media_volume`? | **NO — keep `make clean` destructive. Add separate `make down` that preserves volumes.** | `make clean` is explicitly meant for a clean slate. Users who want to recreate containers without losing seed data should use `make down`. Clear naming separates the two workflows. |
| D5 | Should seed check for fixture JPEGs before running? | **YES — check + clear warning.** If no `.jpg` files in `FIXTURES_IMAGES_DIR`, print a warning with recovery instructions and exit with non-zero code. | Git-ignored JPEGs won't be present in fresh clones. A clear error message prevents the confusing "ads exist but no images" scenario. |
| D6 | Should `.env.docker` be completed? | **YES — add all missing dev/prod variables.** | Missing `SITE_URL` blocks production startup (`prod.py` raises `ImproperlyConfigured`). Missing `REDIS_URL` breaks production cache sharing. Missing `SEED_USERS`/`SEED_ADS` relies on shell defaults that work but are unclear. |

---

## 5. Research Summary

A comprehensive Researcher task investigated all six areas of the seed-to-Docker-to-serving pipeline. Key findings:

### 5.1 Docker Compose Startup Chain

- **Dev mode** (`make up`): The `seed` service starts automatically due to `profiles: !reset []` in the dev override (docker-compose.dev.override.yml line 60-61). This replaces the base compose's `profiles: ["seed"]` gate.
- **Dependency tree**: `db` → `migrate` → `load_catalog` → { `web`, `seed`, `create_admin`, `bot` }
- **CRITICAL**: `web` depends on `load_catalog` and `redis`, but NOT on `seed`. Both `web` and `seed` start concurrently after `load_catalog` completes.
- `web` starts serving in ~1-2 seconds (Django `runserver` starts fast); `seed` takes 30-60+ seconds to generate 600 ads with 360+ images and thumbnails.

### 5.2 Entrypoint Bypass

- `entrypoint.sh` (the Dockerfile default ENTRYPOINT) provides: `check_env_file`, `fix_volume_permissions`, `wait_for_db`, `wait_for_redis`
- `entrypoint-seed.sh` (line 5-9): directly runs `exec uv run python ... manage.py seed` — **bypasses all setup functions**
- `entrypoint-catalog.sh` (line 5-7): directly runs `exec uv run python ... load_catalog` — **bypasses all setup functions**
- `entrypoint-create-admin.sh` (line 5-17): directly runs `exec uv run python ... create_admin_user` — **bypasses all setup functions**
- Only `migrate` (which uses the Dockerfile's default entrypoint) and `web` (same) call `entrypoint.sh`.

### 5.3 media_volume Lifecycle

- `media_volume` is a named Docker volume shared by `seed`, `web`, `bot`, and `nginx` (read-only)
- `docker compose down` (without `-v`): volume persists
- `docker compose down -v` / `make clean`: volume **destroyed** — all seeded images lost
- `SeedService._clean()` (seed_service.py lines 198-243): wipes `MEDIA_ROOT/seed/` on every re-seed, BEFORE ImageGenerator writes new images. If seed crashes between `_clean()` and image generation, images are permanently lost.

### 5.4 Fixture Path Resolution

- `FIXTURES_IMAGES_DIR` resolves to `/app/src/backend/apps/seed/fixtures/images/` in container
- Dev mode (`.:/app` bind mount): host's `src/backend/apps/seed/fixtures/images/` is available ✓
- Production mode (`COPY . .` in Dockerfile): `.dockerignore` does NOT exclude `*.jpg` in this path ✓
- All 1,004 manifest-referenced JPEGs exist on disk locally ✓
- **CRITICAL**: `.gitignore` lines 226-228 exclude `*.jpg`, `*.jpeg`, `*.png` from git — JPEG fixtures are NOT tracked. `git ls-files` returns 0 JPEGs. Fresh clones have no images.

### 5.5 Image Serving Chain (Dev Mode)

- `MEDIA_ROOT` resolves to `/app/media` in container (= `media_volume` mount) ✓
- URL pattern: `media/<path:image_key>` → `media_gate` view ✓
- Template uses `image.image_url` = `f"{MEDIA_URL}{self.image}"` = `/media/seed/<filename>.jpg` ✓
- `media_gate` for non-staff (DEBUG=True): `_serve_image` reads from `MEDIA_ROOT / image_key` ✓
- `media_gate` authorizes: `AdImage.objects.filter(key_q, ad__status=AdStatus.PUBLISHED).exists()` ✓
- Serving chain is correct — images appear if AdImage rows exist in DB AND files exist at `MEDIA_ROOT/seed/`

### 5.6 Seed Status Distribution

- `seed.default.json`: 60% PUBLISHED, 20% ARCHIVED, 10% DRAFT, 5% ON_MODERATION, 5% REJECTED ✓
- PUBLISHED ads get `published_at` timestamp → satisfy DB constraint ✓
- ImageGenerator assigns images to all status ads, but `media_gate` only serves images referenced by PUBLISHED ads ✓

---

## 6. Assumptions

1. The user accesses the site in dev mode (`make up` with `docker-compose.dev.override.yml`). Confirmed by `http://localhost:8000/` URL (dev override publishes port 8000, production does not).
2. The 1,046 JPEG fixtures exist on the host disk (user confirmed). They are NOT in git (verified by `git ls-files`).
3. The user used `make clean` or `docker compose down -v` to recreate containers (based on description "completely recreated Docker containers").
4. The seed service runs but may not have completed before the user inspected the site.
5. The `media_volume` was destroyed on container recreation (either by design or by `make clean`).
6. The `config.settings.dev` settings (DEBUG=True, LocMemCache) are active for dev mode services.
7. The `profiles: !reset []` YAML tag is supported by the user's Docker Compose version (v2.10+).

---

## 7. Constraints

1. **StrEnum for constants** (project rule 10): No new constants introduced — fixes are configuration/entrypoint changes.
2. **No `print()` statements** (project rule 12): Entrypoint scripts are bash, use `echo` which is appropriate for shell scripts.
3. **English only** (project rule 1): All shell comments and echo messages must be in English.
4. **Small modules** (project rule 4): Entrypoint refactor should keep functions focused.
5. **Follow existing patterns** (project rule 7): The `migrate` service already uses the Dockerfile default entrypoint (`entrypoint.sh`); one-shot services should follow the same pattern.
6. **No new dependencies**: All fixes use existing Docker/shell tooling.

---

## 8. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Dev startup delays by 30-60s (seed must complete before web) | Medium | Medium | Task 4 reduces seed ads to 30 in dev, cutting startup to ~5-10s |
| `make down` confusion (vs `make clean`) | Low | Low | Clear documentation in Makefile help text; distinct target names |
| Entrypoint refactor introduces regression in migrate/web services | Low | High | Only modify one-shot entrypoint scripts; leave `entrypoint.sh` backward-compatible; `migrate` and `web` unchanged |
| Production `.env.docker` missing `SITE_URL`/`REDIS_URL` still blocks deploy | Medium | High | Task 5 completes `.env.docker`; add CI check for required env vars |
| Fresh clone without JPEG fixtures fails seed | High | High | Task 3 (entrypoint check) provides clear error message with recovery instructions |
| `wait_for_db` in one-shot entrypoints adds startup delay | Low | Low | DB is already migrated by `migrate` service; wait should succeed immediately |
| Shell function refactoring breaks bash compatibility | Low | Medium | Target bash 4+ (already required by `set -e` pattern in existing scripts) |

---

## 9. Open Questions

1. **Should the seed ad count for dev be configurable via env var?** — Currently `SEED_ADS` defaults to 600 in the base compose. Task 4 hardcodes 30 in the dev override. Should users be able to override this?
2. **Should `make clean` also remove the `postgres_data` volume?** — Currently `make clean` destroys all named volumes. Should DB data be preserved?
3. **Should the Jinja template check include a fallback image URL?** — When seed images are missing, the template shows a "No image" placeholder. Should this be more prominent?

---

## 10. Out of Scope

- **Production seed on startup**: In production, seed is profile-gated (`--profile seed`). This spec does not change production seed behavior (it remains opt-in).
- **JPEG fixture distribution**: This spec does not change `.gitignore` to track JPEG fixtures. The check in Task 3 warns when they're missing; downloading is a manual step via `scripts/download_seed_photos.py`.
- **CI/CD pipeline changes**: This spec does not modify CI workflows. The `.env.docker` completion (Task 5) is a local file change.
- **Image regeneration**: This spec does not address regenerating JPEGs that are missing from disk but referenced in the manifest. (That is covered by spec 10: `seed-photo-recovery_spec.md`.)
- **Performance optimization of seed**: The seed takes 30-60s for 600 ads. This spec reduces dev count but does not optimize the seed algorithm itself.
- **Image model or view changes**: No changes to `AdImage` model, `media_gate` view, or templates — the serving chain is correct once images are present.

---

## 11. Definition of Ready

This specification is **ready for implementation planning** when:

- [x] Business problem is clearly stated (photos missing after Docker container recreation; root causes identified)
- [x] All requirements are confirmed (FR01–FR08, NFR01–NFR04)
- [x] 7 conceptual development tasks are defined with purpose, expected outcome, and dependencies
- [x] 6 Product Owner decisions are captured (with recommended defaults)
- [x] Research has been conducted (1 comprehensive researcher task, 6 investigation areas) and summarized
- [x] Assumptions, constraints, risks, open questions, and out-of-scope items are documented
- [x] The recommended approach (dev-only seed dependency + entrypoint refactor + env file completion + image presence check) is justified by evidence

**Implementation may begin — no additional business analysis is required.**
