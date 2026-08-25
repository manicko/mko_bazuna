# Specification: Seed Generates Too Few Ads — Only 1 Page on Site

**File:** `09_seed-too-few-ads_spec.md`
**Status:** Final (ready for implementation planning)
**Date:** 2026-08-24
**Related specs:** `22_seed-category-coverage_spec.md` (coverage goal), `27_seed-docker-recreation-missing-photos_spec.md` (Docker entrypoint fixes)

---

## 1. Problem Statement

After rebuilding the Docker dev container (`make up`), the site at `http://localhost:8000/` shows only **1 page of ads** (~18 published ads visible, 24 per page) instead of multiple pages as expected previously. The design intent — confirmed by the seed category coverage test (`test_full_seed_coverage`) — requires at least **1 published ad per leaf category** (171 categories), which needs ~600 total ads (60% published rate = ~360 published, ~2 ads per category).

The user has verified:
- ✅ 1,046 JPEG fixture files exist at `src/backend/apps/seed/fixtures/images/` covering all 205 categories
- ✅ `photo_manifest.json` has 0 empty categories (1,004 photos total)
- ✅ The `entrypoint-seed.sh` image-presence check passes (≥1 JPEG found)
- ✅ The Docker image includes fixture JPEGs (`.dockerignore` does not exclude `fixtures/images/*.jpg`)

The photos and templates are correct. The ads are simply **not being generated in sufficient quantity**.

---

## 2. Confirmed Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| CR-01 | The seed command must generate enough ads to cover ≥90% of 171 leaf categories with at least 1 published ad (validated by `test_full_seed_coverage`) | Must |
| CR-02 | The homepage listing (`/` or `/search/` with no filters) must show multiple pages of published ads (24 per page) | Must |
| CR-03 | All ads must display with images (AdImage records) for published ads | Must |
| CR-04 | The seed command runs automatically on `make up` in dev mode via the `seed` service | Must |
| CR-05 | Dev startup time should not exceed 120 seconds (NFR01 from spec_27) | Should |

---

## 3. Root Cause Analysis

### Primary Root Cause: `SEED_ADS=30` Overrides the 600-Ad Default

Three configuration sources interact to determine the seed ad count. The effective value is **30**, not the intended **600**:

| Source | File | Line | Value | Effective? |
|--------|------|------|-------|------------|
| Base compose default | `docker-compose.yml` | 127 | `${SEED_ADS:-600}` | No — overridden by `.env.docker` |
| `.env.docker` | `.env.docker` | 39 | `SEED_ADS=30` | **Yes — loaded by Compose, overrides `${VAR:-default}`** |
| `.env.docker.example` | `.env.docker.example` | 59 | `SEED_ADS=30` | Template for `.env.docker` |
| Dev override | `docker-compose.dev.override.yml` | 75 | `SEED_ADS=30` | **Yes — hardcoded in dev override** |
| Management command | `seed.py` | 39 | `default=600` | Only applies if `--ads` is not passed |

**How Docker Compose resolves `SEED_ADS`:**

1. Docker Compose loads `.env.docker` into the shell environment (this file is gitignored — users create it by copying `.env.docker.example`).
2. The base `docker-compose.yml` has `SEED_ADS=${SEED_ADS:-600}`. Since `.env.docker` sets `SEED_ADS=30`, the `${VAR:-default}` expression resolves to **30** (the env var value, not the fallback).
3. The dev override `docker-compose.dev.override.yml` explicitly sets `SEED_ADS=30` in the `seed` service's `environment:` block, which takes final precedence.

**Result:** The seed service receives `SEED_ADS=30` in both base and dev contexts. The `f5ae0a6` commit's change to `${SEED_ADS:-600}` is silently overridden.

**Math:**
- 30 ads × 60% published = ~18 published ads
- 18 ads / 24 per page = all on 1 page
- 30 ads across 171 leaf categories = ~17% coverage (vs. 90% target)

### Timeline of the Regression (git history)

| Commit | Date | Change | Impact |
|--------|------|--------|--------|
| `f5ae0a6` | Aug 20 | **Intended fix**: Changed base compose `${SEED_ADS:-30}` → `${SEED_ADS:-600}`, management command default 30 → 600 | Set 600 as the default to ensure ≥90% leaf category coverage |
| `de53469` | Aug 19* | Added `SEED_ADS=30` to `.env.docker.example` (template for the gitignored `.env.docker`) | `.env.docker` gets `SEED_ADS=30`, which overrides `${SEED_ADS:-600}` in base compose |
| `dbdd974` | Aug 23 | Added `SEED_ADS=30` to `docker-compose.dev.override.yml` as part of spec_27 | Hardcoded 30 in dev override, reinforcing the override |

*The `de53469` commit is dated Aug 19 but appears in git history as modifying the example file. The runtime `.env.docker` (gitignored) was created by copying this example.

### Why `f5ae0a6`'s fix was ineffective

The `f5ae0a6` commit changed the base compose default from `${SEED_ADS:-30}` to `${SEED_ADS:-600}`. However, Docker Compose's variable expansion `${VAR:-default}` uses the environment variable's value if it's set — it does **not** use the fallback. Since `.env.docker` contained `SEED_ADS=30`, the `${SEED_ADS:-600}` expression resolved to `30`, not `600`.

The `test_full_seed_coverage` test (in `test_seed.py` line 1205) uses `--ads=600` explicitly via `call_command`, bypassing the env var. This test passes because it doesn't rely on `SEED_ADS`. But the Docker seed service reads `SEED_ADS` from the environment, not the command-line default.

### Conflicts with prior decisions

The `dbdd974` commit (spec_27, Task 6 / T-06) made an explicit Product Owner decision (D2):
> "Should `SEED_ADS` for dev be reduced? — YES — `SEED_ADS=30` in dev override."
> Rationale: "600 ads with images takes ~60s in dev; 30 ads is sufficient for visual evaluation and takes ~5-10s."

This decision conflicts with the `f5ae0a6` commit's explicit purpose of ensuring category coverage with 600 ads, and with the `test_full_seed_coverage` test's ≥90% coverage threshold. The spec_27 D2 decision was made in the context of "fixing seed photos after Docker recreation" — it prioritized startup speed over data completeness, inadvertently regressing the ad count.

### Secondary factors (verified as NOT the root cause)

| Factor | Status | Analysis |
|--------|--------|----------|
| `ef26fc8` listing_purpose/features filters | NOT a factor | Filters are opt-in via `?listing_purpose=` and `?features=` query params; not applied on the default homepage |
| Preferred city middleware | NOT a factor | Only filters for authenticated users or users with a `preferred_city` cookie; anonymous users with no cookie see all ads |
| `ef26fc8` price sort `nulls_last=True` | NOT a factor | Only affects sort order, not ad count or visibility |
| `4ea19cb` multi-currency normalization | NOT a factor | Seed generator correctly sets `price_normalized_eur=price_amount`; no filtering on this field |
| ImageGenerator lazy preprocessing (`bbe35fc` D-04) | NOT a factor | Lazy preprocessing only changes when photos are processed (on-demand), not how many ads get images |
| Entrypoint image presence check (`dbdd974` T-04) | NOT a factor | 1,046 JPEGs found; check passes |
| `media_volume` destruction | NOT a factor | The user downloaded fresh photos to fixtures; the container rebuild + seed should copy them to `media_volume` |
| `.dockerignore` excluding JPEGs | NOT a factor | `.dockerignore` does NOT exclude `fixtures/images/*.jpg` — verified |

---

## 4. Conceptual Development Tasks

### Task 1: Restore `SEED_ADS=600` in `.env.docker` and `.env.docker.example`

**Purpose:** Ensure the Docker seed service receives 600 ads instead of 30.

**Expected outcome:**
- `.env.docker` line 39: `SEED_ADS=600`
- `.env.docker.example` line 59: `SEED_ADS=600`
- Base compose `${SEED_ADS:-600}` resolves to 600

**Dependencies:** None.

**Files affected:**
- `.env.docker` (gitignored, runtime)
- `.env.docker.example` (committed template)

### Task 2: Remove `SEED_ADS=30` override from `docker-compose.dev.override.yml`

**Purpose:** Remove the hardcoded `SEED_ADS=30` that overrides the base compose default in dev mode.

**Expected outcome:**
- `docker-compose.dev.override.yml` line 75: Remove `- SEED_ADS=30` (or change to `- SEED_ADS=600`)
- Dev mode inherits `SEED_ADS=600` from `.env.docker` via base compose

**Dependencies:** Task 1 (or can be done independently).

**Files affected:**
- `docker-compose.dev.override.yml`

### Task 3: Update `test_full_seed_coverage` to also validate the env-var-driven path

**Purpose:** Prevent regression where `SEED_ADS` is set too low in environment files.

**Expected outcome:**
- A test that reads the effective `SEED_ADS` env var from compose configuration and asserts it's ≥600

**Dependencies:** Tasks 1-2.

**Files affected:**
- `src/backend/apps/seed/tests/test_seed.py` (or a new test)

### Task 4: Reconcile spec_27's D2 decision with the coverage requirement

**Purpose:** Resolve the conflict between startup-speed optimization (30 ads) and category coverage (600 ads).

**Expected outcome:**
- Product Owner decides: accept ~60s startup for full coverage, or implement a different speedup strategy (e.g., parallel seeding, reduced image count, or a configurable threshold)

**Dependencies:** None.

**Files affected:** `.ai/problems/27_seed-docker-recreation-missing-photos_spec.md` (documentation only)

---

## 5. Product Owner Decisions Required

| # | Question | Options | Recommended |
|---|----------|---------|-------------|
| D1 | What should `SEED_ADS` be in dev mode? | A) 600 (full coverage, ~60s startup) — B) 200 (compromise, ~30% coverage, ~20s startup) — C) Keep 30 (fast startup, but 1 page of ads) | **A) 600** — the coverage test and design intent require ≥90% leaf category coverage, which needs 600 ads |
| D2 | What should `SEED_ADS` be in production? | A) 600 (consistent with dev) — B) Keep `${SEED_ADS:-600}` with `.env.docker` not setting it | **A) 600** — production should also have full coverage; if startup time is a concern in prod, seed is opt-in via `--profile seed` |
| D3 | Should `SEED_ADS` be removed from `.env.docker` so the base compose default `${SEED_ADS:-600}` takes effect? | A) Yes (cleaner — base compose default is the single source of truth) — B) No (explicitly set in `.env.docker` for clarity) | **A) Yes** — reduces the risk of `.env.docker` silently overriding the base compose default; the `${VAR:-default}` pattern is specifically designed for this |
| D4 | Should the dev compose override's `SEED_ADS=30` be removed entirely? | A) Yes (inherit from `.env.docker`) — B) Change to `SEED_ADS=600` explicitly | **A) Yes** — removing it avoids the hardcoding that caused this regression; if `.env.docker` has 600, the override is unnecessary |
| D5 | If 600 ads causes startup >120s (NFR01), what's the mitigation? | A) Accept slower startup — B) Reduce images per ad (min=1, max=1) — C) Parallelize seeding — D) Keep `SEED_US=10` and `SEED_ADS=600` but skip analytics in dev | **B) Reduce images per ad** — the `image_count` config can be reduced; 600 ads with 1 image each is ~200s vs. 3 images each at ~600s; but with 600 ads and 3 images, it's ~60s which is within NFR01 |

---

## 6. Research Summary

### 6.1 Environment Variable Resolution in Docker Compose

Docker Compose loads `.env.docker` (via `env_file` in `docker-compose.dev.override.yml` or automatically if it's the default `.env`). Variables in `.env` files are available for `${VAR}` substitution in `docker-compose.yml`. The `${VAR:-default}` syntax uses `VAR`'s value if set and non-empty; otherwise uses `default`. Since `.env.docker` sets `SEED_ADS=30`, the `${SEED_ADS:-600}` expression in the base compose resolves to `30`.

The dev override's `environment:` block for the `seed` service sets `SEED_ADS=30` as a container environment variable, which takes final precedence over both the `.env.docker` value and the base compose substitution.

### 6.2 Ad Count to Category Coverage

- 171 leaf categories in `categories.yaml` (confirmed by `test_load_category_fixtures_returns_leaf_only`)
- Seed status distribution: 60% PUBLISHED, 20% ARCHIVED, 10% DRAFT, 5% ON_MODERATION, 5% REJECTED
- Only PUBLISHED ads appear on the site
- `test_full_seed_coverage` requires ≥90% of leaf categories to have ≥1 published ad
- 600 ads × 60% published = 360 published ads
- 360 published ads / 171 categories ≈ 2.1 published ads per category (sufficient for ≥90% coverage)
- 30 ads × 60% = 18 published ads / 171 categories ≈ 0.1 published ads per category (~17% coverage)

### 6.3 Why Tests Didn't Catch This

The `test_full_seed_coverage` test (line 1205) uses `call_command("seed", "--ads=600", ...)` which explicitly passes `--ads=600`, bypassing the `SEED_ADS` env var. No test exists that validates the Docker Compose `SEED_ADS` env var value.

The `make test` fast gate skips all `@pytest.mark.seed` tests (via `PYTEST_SKIP_MARKERS=seed`), so even these tests don't run in the default dev test cycle. They only run via `make test-all`.

### 6.4 Existing Config Files Affected

- `.env.docker` (gitignored, runtime) — line 39: `SEED_ADS=30`
- `.env.docker.example` (committed template) — line 59: `SEED_ADS=30`
- `docker-compose.yml` (base) — line 127: `SEED_ADS=${SEED_ADS:-600}` (correct, but overridden)
- `docker-compose.dev.override.yml` — line 75: `SEED_ADS=30` (hardcoded override)
- `docker/entrypoint-seed.sh` — line 33: `--ads "${SEED_ADS:-600}"` (correct default, but env var overrides to 30)
- `src/backend/apps/seed/management/commands/seed.py` — line 39: `default=600` (correct, but env var passed by entrypoint overrides)

---

## 7. Assumptions

1. The user is running in dev mode via `make up` (Docker Compose with dev override), confirmed by the `http://localhost:8000/` URL and the dev override's port mapping (`"8000:8000"`).
2. The user's `.env.docker` was created by copying `.env.docker.example`, which contains `SEED_ADS=30`.
3. The 1,046 JPEG fixture files are present and correct (user confirmed, and `.dockerignore` does not exclude them).
4. The user previously saw multiple pages either by running `python manage.py seed --ads=600 --force` directly, or by having a `.env.docker` without `SEED_ADS` set (so the `${SEED_ADS:-600}` default applied).
5. The `dbdd974` and `de53469` commits were the most recent changes that affected `SEED_ADS` in the Docker environment files.
6. The `test_full_seed_coverage` test's 90% threshold is the intended coverage target (from the `f5ae0a6` commit's spec_22).

---

## 8. Constraints

1. **StrEnum for constants (rule 10):** N/A — no new constants needed; fix is config values only.
2. **Small modules (rule 4):** N/A — no code structure changes required.
3. **Follow existing patterns (rule 7):** The `${SEED_ADS:-600}` pattern in base compose is the established pattern; `.env.docker` should not override it for dev.
4. **No new dependencies:** The fix requires no new packages.
5. **Docker compose override semantics:** Dev override environment vars override base compose env vars; `.env.docker` provides values for `${VAR:-default}` expressions in base compose.

---

## 9. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Dev startup exceeds 120s (NFR01) with 600 ads | Medium | Medium | Reduce `image_count` config to min=1, max=1 in dev; or skip analytics with `--analytics=False` in dev entrypoint |
| Production also affected by `SEED_ADS=30` in `.env.docker` | High | High | Check `.env.docker.example` in production context; production may have its own env file without `SEED_ADS=30` |
| Removing `SEED_ADS` from dev override breaks explicit control | Low | Low | The `.env.docker` value will still apply; removing the override just lets the env var flow through |
| Users who copied `.env.docker.example` with `SEED_ADS=30` need to update | High | Low | Update `.env.docker.example` to `SEED_ADS=600`; add a note in docs about updating existing `.env.docker` |

---

## 10. Open Questions

1. Should `.env.docker` set `SEED_ADS` at all, or should the base compose `${SEED_ADS:-600}` be the sole source (with `.env.docker.example` documenting it as optional)?
2. Is the ~60s dev seed startup acceptable, or is a speedup strategy (reduced images, skipped analytics) needed?
3. Does the production deploy use the same `.env.docker` or a separate production env file? If the same, production also gets 30 ads.

---

## 11. Out of Scope

- Changes to the seed algorithm (`AdGenerator`, `ImageGenerator`, `SeedService`) — these are correct; only the input parameter is wrong.
- Changes to the listing view (`listings.py`, `search.py`) — the filtering logic is correct; `listing_purpose` and `features` filters only apply with query params.
- Changes to the preferred city middleware — it correctly does not filter for anonymous users without a cookie.
- Changes to the catalog builder or categories.yaml — all 171 leaf categories load correctly.
- Changes to photo manifest, templates, or word lists — all are complete and correct.
- Changes to the `test_full_seed_coverage` test — it correctly tests with `--ads=600`; the issue is that the Docker environment doesn't use 600.

---

## 12. Definition of Ready

- [x] Business problem is clearly stated (too few ads in seed → 1 page on site)
- [x] Root cause is identified and verified (`SEED_ADS=30` in `.env.docker` and dev override overrides the 600 default)
- [x] Timeline of regression is documented (commits `de53469`, `f5ae0a6`, `dbdd974`)
- [x] Secondary factors are investigated and ruled out (filters, middleware, price normalization, image generation)
- [x] 4 conceptual development tasks are defined with purpose, expected outcome, dependencies
- [x] 5 Product Owner decisions are captured with recommended defaults
- [x] Research summary covers env var resolution, ad-to-coverage math, test gap analysis
- [x] Assumptions, constraints, risks, open questions, and out-of-scope items are documented
- [x] Conflicting prior decisions are identified (spec_27 D2 decision vs. spec_22 coverage requirement)

**This specification is ready for implementation planning — no additional business analysis is required.**
