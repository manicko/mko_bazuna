# Specification: Dev Migration Consolidation & Failure Fix

**File:** `06_dev-migration-consolidation_spec.md`
**Status:** Final (ready for implementation planning)
**Date:** 2026-08-03
**Source Decision:** `.ai/problems/Decision_07.md`
**Research:** `ses_036fff4b4ffeg3n518Nyoruo9m` (migration consolidation practices), `ses_036ffdd9cffeKathfsy59IkHHI` (catalog builder migration fix)

---

## 1. Problem Statement

The Mko Bazuna project has two related problems with its Django migrations in the development workflow:

### Problem A: Migration service failure
The Docker `migrate` service exits with code 1 on `docker compose up`. The root cause is a combination of fragile migration patterns:

- **`categories/0005_load_catalog`** uses a live Python import (`from apps.categories.catalog.builder import load_catalog`) instead of Django's historical `apps.get_model()` API. This breaks when the current code references fields/tables that don't exist at the migration's execution point in the dependency graph.
- **`ads/0006_backfill_translations`** depends on the external `deep_translator.GoogleTranslator` API and network access, which is unavailable during Docker build.
- **`categories/0002_seed_categories`** uses hardcoded MPTT `lft`/`rght` values in raw SQL, making it brittle.

### Problem B: Migration file bloat
36 migration files across 10 Django apps have accumulated during active development. While backward compatibility is not required in dev mode, the files complicate review, slow down CI, and create maintenance overhead.

### Business Goal
Establish a reliable, low-maintenance migration workflow for dev mode where:
1. The migration service runs successfully every time.
2. Migration files are automatically or semi-automatically consolidated back to one per app when they exceed a threshold.
3. Fragile migrations (external API calls, live imports) are eliminated from the migration pipeline.

---

## 2. Confirmed Requirements

### R1: Fix the migration service failure
- The `migrate` container must exit with code 0 on fresh DB.
- All schema and data migrations must execute without error.
- **R1a**: Refactor `categories/0005_load_catalog` to use `apps.get_model()` (historical models) instead of live imports. Suppress YAML rewrite side-effect during migration execution.
- **R1b**: Move `ads/0006_backfill_translations` (Google Translate) out of the migration pipeline into a standalone management command.
- **R1c**: Fix `categories/0002_seed_categories` — rewrite using Django ORM (`apps.get_model()`) or replace with management command.

### R2: Reset to one migration per app (initial consolidation)
- Delete all existing migration files (36 files across 10 apps).
- Run `makemigrations` to generate one initial migration per app.
- Apply migrations to a fresh dev database.
- This is a one-time wipe: dev database content may be lost. (PO decision Q2-B.)

### R3: Recurring threshold-based consolidation
- When any app accumulates more than **8 migration files**, the system should trigger consolidation back to one initial migration per app.
- A script (`scripts/consolidate_migrations.py`) checks migration counts and, when threshold is exceeded, deletes old files, runs `makemigrations`, and applies with `--fake`.
- A Makefile target (`make consolidate`) wraps the script for easy invocation.
- The threshold is configurable (default 8). The user can also force consolidation with `make consolidate-force`.

### R4: Extract fragile RunPython to management commands
- **`backfill_translations`** — New management command `manage.py backfill_translations`. Runs the Google Translate backfill outside migrations.
- **`load_catalog`** — New management command `manage.py load_catalog`. Loads/updates catalog from YAML config. Also callable from migration with `apps` parameter.
- **`seed_categories`** — (Optional) New management command for initial category seed data.

### R5: Idempotent SQL patterns
- All `RunSQL` triggers and functions must use `CREATE OR REPLACE FUNCTION` and `CREATE INDEX IF NOT EXISTS` to be safe in consolidated migrations.

---

## 3. Conceptual Development Tasks

### Task 1: Refactor catalog builder for migration safety
**Purpose:** Fix the live import in `categories/0005_load_catalog` by making `load_catalog()` accept `apps` and `rewrite_yaml` parameters.

**Expected outcome:**
- `builder.py:load_catalog(config_path, apps=None, rewrite_yaml=True)` — when `apps` is provided, all model access uses `apps.get_model()`; when `None`, uses live imports (standalone mode).
- `_load_lookups`, `_load_categories`, `_load_bindings`, `_load_category_paths` accept `apps` and use it for model access.
- YAML rewrite (`_rewrite_yaml`) is skipped when `rewrite_yaml=False`.
- Existing behavior for standalone calls (management command, tests) is unchanged.

**Dependencies:** None (standalone refactor).

---

### Task 2: Create `load_catalog` management command
**Purpose:** Provide `manage.py load_catalog` for standalone catalog loading.

**Expected outcome:**
- New file: `src/backend/apps/categories/management/commands/load_catalog.py`
- Calls `builder.load_catalog(CONFIG_PATH)` with defaults (live imports, rewrite_yaml=True).
- Accepts `--config` argument to override YAML path.
- Accepts `--no-rewrite` flag to suppress YAML rewrite.

**Dependencies:** Task 1 (refactored builder).

---

### Task 3: Create `backfill_translations` management command
**Purpose:** Extract Google Translate backfill from migration to standalone command.

**Expected outcome:**
- New file: `src/backend/apps/ads/management/commands/backfill_translations.py`
- Contains all logic from `ads/0006_backfill_translations` (the `backfill_translations` function and `_translate_text` helper).
- Accepts `--batch-size` argument (default 100) for iterator chunk size.
- Logs progress, errors, and summary (same as current migration).
- Is idempotent: skips ads that already have all translations populated.

**Dependencies:** None.

---

### Task 4: Fix `categories/0002_seed_categories` migration
**Purpose:** Replace hardcoded MPTT raw SQL with Django ORM using `apps.get_model()`.

**Expected outcome:**
- Rewrite `create_categories` to use `apps.get_model("categories", "Category")` for insertion.
- Use `Category.objects.create()` with `parent` FK assignment (Django MPTT handles lft/rght recalculation).
- Remove raw SQL cursor usage entirely.
- Keep the same seed data (3 roots, 14 categories total).

**Dependencies:** None.

---

### Task 5: Create consolidation script
**Purpose:** Provide a reusable script that checks migration counts and consolidates when threshold is exceeded.

**Expected outcome:**
- New file: `scripts/consolidate_migrations.py`
- Walks all app migration directories under `src/backend/apps/`.
- Counts `[0-9]*.py` files (excludes `__init__.py`).
- If any app exceeds `--threshold` (default 8), or `--force` is passed: deletes all `[0-9]*.py` files and `__pycache__` directories.
- Outputs summary of what was deleted per app.
- Prints instructions to run `makemigrations` and `migrate --fake` next.
- Designed for both Docker and local execution.

**Dependencies:** None (pure file operations).

---

### Task 6: Create Makefile targets for consolidation workflow
**Purpose:** Integrate the consolidation script into the project's build system.

**Expected outcome:**
- `Makefile` additions:
  - `make consolidate` — runs `scripts/consolidate_migrations.py` with threshold check, then runs `makemigrations` and `migrate --fake` in Docker.
  - `make consolidate-force` — same but with `--force` flag (consolidates all apps regardless of threshold).
- `Makefile.ps1` equivalent for Windows/VS Code devs.
- Variable `CONSOLIDATE_THRESHOLD ?= 8` in Makefile.

**Dependencies:** Task 5 (consolidation script), Task 7 (fragile migrations extracted).

---

### Task 7: Perform initial full migration consolidation
**Purpose:** Execute the one-time reset: delete all 36 migration files, regenerate fresh, and apply.

**Expected outcome:**
- All `migrations/*.py` files except `__init__.py` deleted across all 10 apps.
- `makemigrations` produces exactly one `0001_initial.py` per app.
- `migrate` on fresh DB succeeds.
- `makemigrations --check --dry-run` confirms no pending changes.
- Docker `migrate` service exits with code 0.

**Dependencies:** Tasks 1–6 completed (fixes applied before reset).

---

## 4. Product Owner Decisions

| # | Question | Decision |
|---|----------|----------|
| Q1 | Primary approach | **(B) Reset to zero first** — Delete all migrations, `makemigrations` fresh, fix issues that surface. |
| Q2 | Dev DB data | **(B) Wipe and recreate** — Fresh DB from scratch. Dev data loss is acceptable. |
| Q3 | `ads/0006_backfill_translations` | **(B) Move to management command** — Run separately on demand. Migrations must not depend on external APIs. |
| Q4 | `categories/0005_load_catalog` live import | **(A) Fix to use `apps.get_model()`** — Proper historical model access in migration context. |
| Q5 | Desired migration state | **(C) Two-phase** — Consolidate to one per app now; new changes create incremental migrations; re-consolidate when threshold exceeded. |
| Q6 | Consolidation threshold | **8 migration files** — When any app exceeds this, re-consolidate to one initial migration per app. (Derived from Q5 follow-up.) |

---

## 5. Research Summary

### Researcher session 1: Migration consolidation practices (`ses_036fff4b4ffeg3n518Nyoruo9m`)

**Key findings:**
- Django-native `squashmigrations` keeps `RunPython`/`RunSQL` as-is (no optimization for data migrations). Requires two-phase release (squash → deploy → prune → delete).
- Django 5.2 `makemigrations --update` merges model changes into the latest migration — useful to slow accumulation but doesn't solve the threshold problem.
- Django 5.2 `migrate --prune` cleans up `django_migrations` table entries for deleted migration files.
- The **full reset approach** (delete all → `makemigrations` → `migrate --fake`) is recommended for dev mode where backward compatibility is not needed.
- **Threshold pattern:** A Python script scans migration directories and triggers consolidation when count > N. N=8 is the recommended threshold.
- **Extraction strategy:** Fragile `RunPython` (external API calls) must be moved to management commands before consolidation. Local-data `RunPython` (seed categories, cities) can be kept or migrated to `call_command` in the consolidated migration.

**Recommended strategy: Hybrid reset-based consolidation with extracted RunPython**
1. Extract fragile migrations to management commands.
2. Run consolidation script (delete → `makemigrations` → `migrate --fake`).
3. Seed data loaded via management commands (seed service).

### Researcher session 2: Catalog builder migration fix (`ses_036ffdd9cffeKathfsy59IkHHI`)

**Key findings:**
- `apps.get_model()` in Django 5.2 preserves the default manager (`objects`) — `.update_or_create()`, `.filter()`, `.get()` all work.
- MPTT methods (`insert_at()`) may not work reliably with historical models. The current builder doesn't use `insert_at()` — it sets `parent` FK and calls `save()`, which works fine.
- Custom `QuerySet` methods, `save()` overrides, `property` decorators, signal receivers are stripped from historical models. The builder doesn't depend on any of these.
- **Recommended approach: Hybrid**
  - Add `apps` parameter to `load_catalog()` that flows to all helpers.
  - Add `rewrite_yaml=False` parameter — migration calls with `rewrite_yaml=False`.
  - Create management command that calls same builder with defaults.
  - Migration 0005 calls `load_catalog(CONFIG_PATH, apps=apps, rewrite_yaml=False)`.

---

## 6. Assumptions

1. **Dev database can be wiped.** No production data exists. All seed data is reproducible via management commands.
2. **No other developers are sharing this dev database.** The consolidation script assumes single-developer mode.
3. **`django-mptt` insert_at() is not required.** The current catalog builder uses `parent=...; save()` pattern which works with historical models.
4. **The YAML catalog config is committed and versioned.** It is not generated at runtime.
5. **Google Translate API is not available during Docker build.** The `deep-translator` package and network access may be present in the build container, but migrations should not depend on this.
6. **After consolidation, `django_migrations` table is clean.** Using `--fake` records the new migrations as applied without executing them.

---

## 7. Constraints

1. **Django 5.2 LTS** (`>=5.2.16,<6.0`) — Must use Django 5.2 APIs. `apps.get_model()` behavior in Django 5.2 is the target.
2. **Docker compose** — The migration workflow must work inside Docker containers. The `migrate` service is one-shot with advisory lock.
3. **Two processes, one DB** — web + bot share the same database. Migration runs exactly once before both start.
4. **`migrate_locked.py`** — The advisory lock wrapper must remain functional. The `session=True` lock prevents concurrent migration runs.
5. **pgBouncer (production only)** — Not used in dev. The session-scoped advisory lock is safe.
6. **No Celery/Redis** — No task queue. Management commands must be run synchronously or via seed service.
7. **`scripts/` directory** — All utility scripts live in `scripts/`. The consolidation script follows this convention.

---

## 8. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `makemigrations` produces more than one migration per app after reset | Medium | Medium | Verify with `--check --dry-run`. If circular deps exist, break with `SeparateDatabaseAndState`. |
| `migrate --fake` causes state mismatch if subsequent changes are not properly detected | Low | Medium | Run `makemigrations --check` in CI to catch drift. |
| MPTT `update_or_create` with historical model behaves differently than live model | Low | Medium | Test on fresh DB before consolidation. The builder uses simple ORM methods. |
| Google Translate API rate limits when `backfill_translations` command is run | Medium | Low | The command already has per-ad error handling and logging. Add `--rate-limit` support if needed. |
| Consolidation script deletes migration files that contain uncommitted schema changes | Low | High | The script should warn if `git status --porcelain` shows modified model files. Consider requiring clean git status. |
| Consolidation after schema changes but before committing creates silent data loss | Low | High | Require `git diff --name-only` to show no model changes before consolidation. |

---

## 9. Open Questions

None. All business-level questions have been resolved by PO decisions Q1–Q6.

---

## 10. Out of Scope

1. **Production migration strategy** — This specification covers dev mode only. Production will need a different approach (squash + two-phase release).
2. **CI/CD pipeline changes** — No changes to existing test/compose files. The existing `test_migrations.py` should still pass after consolidation.
3. **Data preservation** — No effort to preserve dev database content. Full wipe is accepted.
4. **Multiple developer coordination** — The consolidation script assumes single-dev mode. Team workflow is deferred.
5. **Automated threshold enforcement** — The consolidation is triggered manually via Makefile. No cron/CI hook to auto-consolidate.
6. **Migration file quality checks** — No linter or validator for migration contents (beyond existing ruff/basedpyright).

---

## 11. Definition of Ready

This specification is ready for implementation planning when:

1. ✅ All 6 PO decisions are captured (Q1–Q6).
2. ✅ Research on migration consolidation practices is complete and reviewed.
3. ✅ Research on catalog builder migration fix is complete and reviewed.
4. ✅ Fragile migration patterns are identified and extraction strategy is defined.
5. ✅ Threshold and consolidation trigger mechanism are specified.
6. ✅ All conceptual tasks are independent and have clear acceptance criteria.
7. ✅ Risks are documented with mitigation strategies.