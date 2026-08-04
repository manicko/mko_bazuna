# Plan: Dev Migration Consolidation & Failure Fix

**File:** `07_dev-migration-consolidation_plan.md`
**Date:** 2026-08-03
**Source:** `.ai/problems/06_dev-migration-consolidation_spec.md`
**Status:** Implementation-ready

---

## Execution DAG

```
Phase 1 — Standalone refactoring (parallel)
├── TSK-001: Refactor builder.py::load_catalog() for migration safety
├── TSK-002: Extract backfill_translations to management command
├── TSK-003: Fix categories/0002_seed_categories to use Django ORM
└── TSK-004: Create consolidation script

Phase 2 — Depends on Phase 1
└── TSK-005: Create load_catalog management command         [depends on TSK-001]

Phase 3 — Build integration (depends on Phase 1)
└── TSK-006: Add Makefile/Makefile.ps1 consolidation targets [depends on TSK-004]

Phase 4 — Pre-consolidation hardening
└── TSK-007: Make all RunSQL use idempotent SQL patterns

Phase 5 — RISKY: Initial consolidation
├── TSK-008-RSR: Research gate — verify clean state for consolidation
│   [precedes TSK-008]
└── TSK-008: Perform initial full migration consolidation
    [depends on TSK-001, TSK-002, TSK-003, TSK-004, TSK-005, TSK-006, TSK-007]

Phase 6 — Verification
└── VFY-001: Validate consolidation success
    [depends on TSK-008]
```

---

## Task Specifications

---

### Phase 1 — Standalone Refactoring (parallel execution group)

---

#### TSK-001: Refactor `builder.py::load_catalog()` for migration safety

<details>
<summary>Task details</summary>

**Priority:** high

**Depends on:** None

**Risk:** moderate — changes public API signature of `load_catalog()`

**Affected modules:**
- `src/backend/apps/categories/catalog/builder.py`

**Affected classes:** None

**Affected functions:**
- `load_catalog` — add `apps` and `rewrite_yaml` parameters
- `_load_lookups` — accept `apps` parameter, use `apps.get_model()` when provided
- `_load_categories` — accept `apps` parameter, use `apps.get_model()` when provided
- `_load_bindings` — accept `apps` parameter, use `apps.get_model()` when provided
- `_load_category_paths` — accept `apps` parameter, use `apps.get_model()` when provided
- `_rewrite_yaml` — no signature change, but call must be gated by `rewrite_yaml` param

**Affected services:** None

**Semantic insertion points:**
- `load_catalog` — modify signature to `load_catalog(config_path, apps=None, rewrite_yaml=True)`
- `load_catalog` — wrap `_rewrite_yaml` call with `if rewrite_yaml:`
- `load_catalog` — pass `apps` to all helper calls
- Each helper — add `apps=None` parameter; when `apps` is not `None`, use `apps.get_model()` instead of live imports; when `apps` is `None`, preserve existing live import behavior

**Changes:**

1. **`load_catalog()` signature change**
   - New signature: `def load_catalog(config_path: str | Path, apps: Any = None, rewrite_yaml: bool = True) -> dict[str, str]`
   - When `apps` is provided, all model access uses `apps.get_model()`
   - When `apps` is `None`, use existing live imports (standalone mode)
   - When `rewrite_yaml=False`, skip the `_rewrite_yaml()` call

2. **`_load_lookups()` — add `apps` parameter**
   - When `apps` is provided: `LookupGroup = apps.get_model("lookups", "LookupGroup")`, similarly for `LookupItem`
   - When `apps` is `None`: keep `from apps.lookups.models import LookupGroup, LookupItem`

3. **`_load_categories()` — add `apps` parameter**
   - When `apps` is provided: `Category = apps.get_model("categories", "Category")`
   - When `apps` is `None`: keep `from apps.categories.models import Category`

4. **`_load_bindings()` — add `apps` parameter**
   - When `apps` is provided: use `apps.get_model()` for `CategoryListingPurpose`, `CategoryListingFeature`, `LookupItem`
   - When `apps` is `None`: keep existing imports

5. **`_load_category_paths()` — add `apps` parameter**
   - When `apps` is provided: `CategoryPath = apps.get_model("categories", "CategoryPath")`
   - When `apps` is `None`: keep `from apps.categories.models import CategoryPath`

**Acceptance criteria:**
- `load_catalog(config_path)` works identically to current behavior (standalone mode)
- `load_catalog(config_path, apps=apps, rewrite_yaml=False)` works in migration context
- All helper functions accept `apps` parameter
- `_rewrite_yaml` is NOT called when `rewrite_yaml=False`
- Existing tests pass without modification

</details>

---

#### TSK-002: Extract `backfill_translations` to management command

<details>
<summary>Task details</summary>

**Priority:** high

**Depends on:** None

**Risk:** low — new file, no existing API change

**Affected modules:**
- `src/backend/apps/ads/migrations/0006_backfill_translations.py` — remove `RunPython` operation
- `src/backend/apps/ads/management/commands/backfill_translations.py` — NEW file

**Affected classes:**
- NEW: `Command` (extends `BaseCommand`) in `backfill_translations.py`

**Affected functions:**
- `_translate_text` — extract from migration to management command module
- `backfill_translations` — extract from migration to management command module, adapt to `handle()` method
- Remove `RunPython` operation from `Migration` class in `0006_backfill_translations.py`

**Semantic insertion points:**
- NEW file: `src/backend/apps/ads/management/commands/backfill_translations.py`
- Inside `0006_backfill_translations.py`:
  - Delete `_translate_text()` function
  - Delete `backfill_translations()` function
  - Remove `RunPython` from `Migration.operations`
  - Keep the migration class as a no-op schema-only migration

**Changes:**

1. **Create management command** at `src/backend/apps/ads/management/commands/backfill_translations.py`:
   - `class Command(BaseCommand)` with `help = "Backfill translations for ads to English and Bosnian"`
   - `add_arguments()` — accept `--batch-size` (default 100)
   - `handle()` — contains the logic from `backfill_translations()`, uses live models (not `apps.get_model()`)
   - Move `TARGET_LOCALES`, `_translate_text()` into the module
   - Logging: same pattern as current migration (progress, errors, summary)
   - Idempotent: skips ads that already have all translations populated

2. **Clean up `0006_backfill_translations.py`**:
   - Remove `_translate_text()`, `backfill_translations()`, `logger`, `TARGET_LOCALES`
   - Remove `from django.db import migrations` (if `RunPython` was the only user... keep the import for `migrations.Migration`)
   - Remove `RunPython` from `operations`
   - Migration becomes a no-op schema-only migration (just dependencies)

**Acceptance criteria:**
- `manage.py backfill_translations` runs successfully with live models
- `manage.py backfill_translations --batch-size 50` uses specified chunk size
- Migration `ads/0006` no longer calls Google Translate
- `ads/0006` migration applies without network access

</details>

---

#### TSK-003: Fix `categories/0002_seed_categories` to use Django ORM

<details>
<summary>Task details</summary>

**Priority:** high

**Depends on:** None

**Risk:** moderate — rewrites a data migration from raw SQL to ORM

**Affected modules:**
- `src/backend/apps/categories/migrations/0002_seed_categories.py`

**Affected classes:** None

**Affected functions:**
- `create_categories` — replace entire body

**Affected services:** None

**Semantic insertion points:**
- Function `create_categories(apps, schema_editor)` — replace body

**Changes:**

1. **Rewrite `create_categories()`** to:
   - Use `apps.get_model("categories", "Category")` for model access
   - Create root categories first (parent=None) via `Category.objects.create()`
   - Create child categories with `parent=<root_instance>` FK assignment
   - Let Django MPTT handle `lft`/`rght` recalculation on `save()`
   - Preserve same seed data: 3 roots + 5 + 4 + 3 children = 14 total categories
   - Remove all raw SQL cursor usage

**Acceptance criteria:**
- After migration, database has exactly 14 categories with correct tree structure
- No raw SQL (`cursor.execute`) is used
- MPTT `lft`/`rght` values are correctly computed by Django

</details>

---

#### TSK-004: Create consolidation script

<details>
<summary>Task details</summary>

**Priority:** high

**Depends on:** None

**Risk:** low — new file, pure file operations

**Affected modules:**
- `scripts/consolidate_migrations.py` — NEW file

**Affected classes:** None

**Affected functions:** None

**Semantic insertion points:**
- NEW file: `scripts/consolidate_migrations.py`

**Changes:**

1. **Create `scripts/consolidate_migrations.py`** with:
   - CLI arg: `--threshold` (default 8) — max migration files per app before consolidation triggers
   - CLI arg: `--force` — consolidate all apps regardless of threshold
   - CLI arg: `--apps-dir` — path to apps directory (default `src/backend/apps`)
   - Walk all app directories under `--apps-dir`
   - For each app with a `migrations/` subdirectory:
     - Count `[0-9]*.py` files (excludes `__init__.py`)
     - If count > threshold OR `--force`:
       - Print summary of files to delete
       - Delete all `[0-9]*.py` files
       - Delete `__pycache__` directories inside `migrations/`
       - Track per-app counts
   - Output summary of what was deleted per app
   - Print instructions for next steps: `makemigrations` + `migrate --fake`
   - Optional: check `git status --porcelain` and warn if uncommitted model changes exist (Risk mitigation from spec §8)

**Acceptance criteria:**
- `uv run python scripts/consolidate_migrations.py` works in both Docker and local env
- `--threshold 5` changes the trigger threshold
- `--force` consolidates all apps regardless of count
- Script outputs clear per-app summary
- Script handles `__pycache__` cleanup

</details>

---

### Phase 2 — Depends on Phase 1

---

#### TSK-005: Create `load_catalog` management command

<details>
<summary>Task details</summary>

**Priority:** high

**Depends on:** TSK-001 (refactored builder with `load_catalog(config_path, apps, rewrite_yaml)`)

**Risk:** low — new file, calls refactored builder with defaults

**Affected modules:**
- `src/backend/apps/categories/management/commands/load_catalog.py` — NEW file
  - Note: The `management/commands/` directory under `categories` app may not exist yet

**Affected classes:**
- NEW: `Command` (extends `BaseCommand`) in `load_catalog.py`

**Affected functions:** None

**Affected services:** None

**Semantic insertion points:**
- NEW file at `src/backend/apps/categories/management/commands/load_catalog.py`

**Changes:**

1. **Create management command**:
   - `class Command(BaseCommand)` with `help = "Load catalog from YAML config"`
   - `add_arguments()`: `--config` (override CONFIG_PATH), `--no-rewrite` (suppress YAML rewrite)
   - `handle()`: call `builder.load_catalog(CONFIG_PATH)` with defaults (live imports, rewrite_yaml=True unless `--no-rewrite`)

**Acceptance criteria:**
- `manage.py load_catalog` runs and produces same output as current standalone calls
- `manage.py load_catalog --no-rewrite` suppresses YAML rewrite
- `manage.py load_catalog --config /path/to/file.yaml` uses custom config path

</details>

---

### Phase 3 — Build Integration

---

#### TSK-006: Add Makefile/Makefile.ps1 consolidation targets

<details>
<summary>Task details</summary>

**Priority:** medium

**Depends on:** TSK-004 (consolidation script exists)

**Risk:** low — adds to build system, no existing target removal

**Affected modules:**
- `Makefile` — add targets
- `Makefile.ps1` — add functions and dispatch entries

**Affected classes:** None

**Affected functions:**
- `Makefile`: add `consolidate`, `consolidate-force` targets
- `Makefile.ps1`: add `Invoke-Consolidate`, `Invoke-ConsolidateForce` functions; add to `switch` dispatch

**Semantic insertion points:**
- `Makefile`: after `create-admin` target section (before Utilities block), add:
  ```
  # ====================== Consolidation ======================
  CONSOLIDATE_THRESHOLD ?= 8

  consolidate:
  	scripts/consolidate_migrations.py --threshold $(CONSOLIDATE_THRESHOLD)
  	make makemigrations
  	make migrate

  consolidate-force:
  	scripts/consolidate_migrations.py --force
  	make makemigrations
  	make migrate
  ```
- `Makefile.ps1`: add `Invoke-Consolidate`, `Invoke-ConsolidateForce` functions; add cases in `switch`

**Changes:**

1. **`Makefile` additions:**
   - Add `CONSOLIDATE_THRESHOLD ?= 8` variable
   - Add `consolidate` target: run script, `makemigrations`, then `migrate` (with `--fake` in Docker context)
   - Add `consolidate-force` target: same but with `--force`

2. **`Makefile.ps1` additions:**
   - Add `Invoke-Consolidate` and `Invoke-ConsolidateForce` functions
   - Add `$CONSOLIDATE_THRESHOLD = 8` default variable
   - Register in the `switch` dispatch

**Acceptance criteria:**
- `make consolidate` runs the consolidation script with threshold check
- `make consolidate-force` runs with `--force`
- Equivalent targets work in `Makefile.ps1`
- Help text includes both new targets

</details>

---

### Phase 4 — Pre-consolidation Hardening

---

#### TSK-007: Make all RunSQL use idempotent SQL patterns

<details>
<summary>Task details</summary>

**Priority:** medium

**Depends on:** None

**Risk:** low — refines existing SQL, no behavioral change on fresh DB

**Affected modules:**
- `src/backend/apps/users/migrations/0002_user_chat_id.py` — review only (data backfill, no idempotency issue)
- `src/backend/apps/ads/migrations/0002_search_vector_triggers.py`
- `src/backend/apps/ads/migrations/0005_multi_lang_search_vector.py`
- `src/backend/apps/core/migrations/0001_verify_lifecycle_indexes.py` — already idempotent, verify only

**Affected classes:** None

**Affected functions:** None

**Affected services:** None

**Semantic insertion points:**

1. **`ads/0002_search_vector_triggers.py` — `Migration.operations`**:
   - Trigger creation: wrap each `CREATE TRIGGER` with `DROP TRIGGER IF EXISTS ... ON ads;` preceding statement
   - Functions: already use `CREATE OR REPLACE FUNCTION` — verify

2. **`ads/0005_multi_lang_search_vector.py` — `Migration.operations`**:
   - Already uses `DROP TRIGGER IF EXISTS` pattern — verify only

3. **`core/0001_verify_lifecycle_indexes.py` — `Migration.operations`**:
   - Already uses `CREATE INDEX IF NOT EXISTS` — verify only

**Changes:**

1. **Audit all RunSQL across all migration files** — identify any `CREATE INDEX`, `CREATE TRIGGER`, or `CREATE FUNCTION` that lacks `IF NOT EXISTS` / `OR REPLACE` / pre-drop guard
2. **Add guards** where missing (expected only in `ads/0002` for trigger creation)
3. No changes needed for data-backfill `RunSQL` (e.g., `users/0002` — these are intentionally non-idempotent and run only on fresh DB)

**Acceptance criteria:**
- Every `CREATE INDEX` uses `IF NOT EXISTS`
- Every `CREATE OR REPLACE FUNCTION` is used (or `DROP ... IF EXISTS` precedes `CREATE`)
- Every `CREATE TRIGGER` is guarded by `DROP TRIGGER IF EXISTS`
- Consolidated migration can run on an existing DB without error

</details>

---

### Phase 5 — RISKY: Initial Consolidation

---

#### TSK-008-RSR: Research gate — verify clean state for consolidation

<details>
<summary>Task details</summary>

**Priority:** high (gate)

**Depends on:** None (runs before TSK-008)

**Risk:** low — read-only investigation

**Purpose:** Verify that the codebase and database are in a state that makes consolidation safe.

**Research questions:**
1. Are there any uncommitted model changes (`git diff --name-only`) in the migrations directory or model files?
2. Does `makemigrations --check --dry-run` pass currently?
3. Are all 36 migration files accounted for across all 10 apps (list directories)?
4. Does the existing `test_migrations.py` test still pass?
5. Is the dev database running and accessible?
6. What is the current migration state in `django_migrations` table?

**Deliverable:** A brief report confirming:
- READY (Go): No uncommitted model changes, tests pass, DB accessible
- BLOCKED (No Go): Issues found, list what needs resolution

**Blocks:** TSK-008

</details>

---

#### TSK-008: Perform initial full migration consolidation

<details>
<summary>Task details</summary>

**Priority:** high

**Depends on:** TSK-001, TSK-002, TSK-003, TSK-004, TSK-005, TSK-006, TSK-007
**Blocked by:** TSK-008-RSR (research gate must report "Go" or "Go with changes")

**Risk:** HIGH — deletes 36 migration files, modifies DB schema start, changes startup behavior

**Affected modules:**
- ALL `migrations/*.py` files across 10 apps (except `__init__.py`)

**Affected apps:**
- `ads` (10 migration files)
- `analytics` (4 migration files)
- `categories` (5 migration files)
- `core` (1 migration file)
- `locations` (2 migration files)
- `lookups` (1 migration file)
- `media` (likely 0-1 migration file)
- `moderation` (4 migration files)
- `search` (4 migration files)
- `trust` (2 migration files)
- `users` (3 migration files)

**Semantic insertion points:**
- Delete all `[0-9]*.py` in each `migrations/` directory
- Run `makemigrations` across all apps
- Apply migrations to fresh dev database

**Changes:**

1. **Delete all migration files** — delete every `[0-9]*.py` file across all app `migrations/` directories (excluding `__init__.py`)
2. **Delete `__pycache__`** in each `migrations/` directory
3. **Run `makemigrations`** — verify it produces exactly one `0001_initial.py` per app
4. **Review generated migrations:**
   - Verify all schema operations are present
   - If fragile RunPython remains (e.g., seed data), evaluate whether to keep or move
5. **Update migration 0005_load_catalog** after regeneration to use refactored call:
   - `load_catalog(CONFIG_PATH, apps=apps, rewrite_yaml=False)` instead of live import
6. **Apply migrations** on a fresh dev database
7. Verify `migrate` exits with code 0
8. Verify `makemigrations --check --dry-run` confirms no pending changes
9. Commit the new state

**Acceptance criteria:**
- All old migration files deleted
- Exactly one `0001_initial.py` per app
- `makemigrations --check --dry-run` passes (no pending changes)
- `docker compose run --rm migrate` exits with code 0 on fresh DB
- The migrated DB schema matches current models

</details>

---

### Phase 6 — Verification

---

#### VFY-001: Validate consolidation success

<details>
<summary>Task details</summary>

**Priority:** high

**Depends on:** TSK-008

**Type:** verification

**Verification steps:**

1. **Build**: `docker compose build`
2. **Migration test**: `docker compose run --rm migrate` — must exit 0
3. **makemigrations check**: `docker compose run --rm web uv run python src/backend/manage.py makemigrations --check --dry-run` — must show no pending changes
4. **Existing migration tests**: `uv run pytest src/backend/apps/core/tests/test_migrations.py -v`
5. **Full test suite**: `docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test`
6. **Lint/typecheck**: `make lint && make typecheck`

**Pass criteria:**
- `migrate` exits with code 0
- `makemigrations --check --dry-run` shows no pending changes
- `test_migrations.py` passes
- Full test suite passes
- Lint and typecheck pass without regressions

**Failure action:** Return TSK-008 to rework with diagnostics

</details>

---

## Execution Order Summary

```
Phase 1 (parallel):
  TSK-001  │  TSK-002  │  TSK-003  │  TSK-004
       │           │           │           │
Phase 2: |         |           |           |
  TSK-005 |         |           |           |
  (after TSK-001)  |           |           |
                   |           |           |
Phase 3:           |           |           |
  TSK-006          |           |           |
  (after TSK-004)  |           |           |
                   |           |           |
Phase 4:           |           |           |
  TSK-007          |           |           |
  (no deps)        |           |           |
                   |           |           |
Phase 5:           |           |           |
  TSK-008-RSR      |           |           |
  TSK-008 ───────── all above ─────────────
  (blocked by TSK-008-RSR)
                   |
Phase 6:
  VFY-001
  (after TSK-008)
```

---

## Risk Summary

| Task | Risk | Reason | Mitigation |
|------|------|--------|------------|
| TSK-001 | Moderate | Changes public API of `load_catalog()` | Backward-compatible defaults |
| TSK-003 | Moderate | Rewrites a data migration from raw SQL to ORM | Preserves same seed data; MPTT handles tree |
| TSK-007 | Low | Refines SQL guard clauses | Read-only audit of existing patterns |
| TSK-008 | **HIGH** | Deletes 36 migration files, modifies startup behavior | Gated by TSK-008-RSR; fresh DB only; tests must pass |

---

## Rollback Plan (TSK-008)

If TSK-008 produces broken migrations:
1. `git checkout -- src/backend/apps/*/migrations/` to restore deleted migration files
2. Recreate dev database: `docker compose down -v && docker compose up`
3. Diagnose from `makemigrations` output and `migrate` error logs
4. Fix issues and re-run TSK-008

No production data is at risk (dev mode only per PO decision Q2-B).

---

## Notes

- **Parallel execution**: TSK-001, TSK-002, TSK-003, TSK-004 can be implemented in any order by separate agents.
- **TSK-002 detail**: After extraction, the migration `0006_backfill_translations.py` will be a no-op schema-only migration. It will be deleted in TSK-008 during the full reset.
- **TSK-003** and **TSK-002** both remove `RunPython` from existing migrations. These changes are overwritten by TSK-008 when all migration files are replaced with regenerated ones. This is intentional — the fixes ensure the *current* migration pipeline works before the reset.
- **TSK-007** changes are also overwritten by TSK-008, but serve as a safety net in case the consolidated migration must be applied to an existing DB.