# Migration Patterns Research — Database Migration for i18n Columns

**Task:** TASK_019  
**Date:** 2026-07-27  
**Status:** COMPLETE — Go decision  

---

## 1. Files Analyzed

| File | Type | Operations Used |
|------|------|-----------------|
| `ads/migrations/0001_initial.py` | Generated (Django) | `CreateModel`, `AddIndex`, `GinIndex` |
| `ads/migrations/0002_search_vector_triggers.py` | Manual (RunSQL) | `RunSQL` — CREATE OR REPLACE FUNCTION, CREATE TRIGGER, UPDATE backfill |
| `ads/migrations/0003_add_index_conditions.py` | Manual (Django ops) | `RemoveIndex`, `AddIndex` with `condition=models.Q(...)` |
| `categories/migrations/0001_initial.py` | Generated (Django) | `CreateModel` with MPTT fields |
| `categories/migrations/0002_seed_categories.py` | Manual (RunPython) | `RunPython(create_categories, noop)` with raw SQL cursor |
| `core/migrations/0001_verify_lifecycle_indexes.py` | Manual (RunSQL) | `RunSQL` — `CREATE INDEX IF NOT EXISTS` (PostgreSQL 18+), `DROP INDEX IF EXISTS` (reverse) |

---

## 2. Migration Patterns Found

### Pattern A: Standard Django Schema Operations (0001, 0003)
Used for schema changes that Django ORM supports natively:
- `CreateModel`, `AddIndex`, `RemoveIndex`, `AddField`, `RemoveField`
- Automatic forward/reverse (no manual `reverse_sql` needed)
- Used in `0001_initial.py` (generated) and `0003_add_index_conditions.py` (hand-written)

### Pattern B: Raw PostgreSQL with RunSQL (0002, core/0001)
Used for PostgreSQL-specific objects (functions, triggers, indexes):
- `RunSQL(sql=..., reverse_sql=migrations.RunSQL.noop)` — irreversible forward-only
- `RunSQL(sql=..., reverse_sql="DROP ...")` — reversible
- `CREATE OR REPLACE FUNCTION` for idempotent function updates
- `CREATE INDEX IF NOT EXISTS` (PostgreSQL 18+ feature) for idempotent index creation

### Pattern C: Data Migration with RunPython (categories/0002)
Used for seeding reference data:
- `RunPython(callable, reverse_callable)` — with `migrations.RunSQL.noop` as noop reverse
- Uses `apps.get_model()` historical model (NOT the current model class)
- Raw SQL through `schema_editor.connection.cursor()` for bulk inserts

### Pattern D: Condition-based Index Updates (0003)
Uses Django ORM `RemoveIndex` + `AddIndex` with `condition=models.Q(...)`:
- Adds partial (`WHERE status = 'published'`) conditions to existing indexes
- Pattern: Remove old → Add new with condition

---

## 3. Migration Dependencies Graph

```
users/0001_initial ─┐
categories/0001_initial ─┤
locations/0001_initial ─┤
                        ├→ ads/0001_initial → ads/0002_search_vector_triggers → ads/0003_add_index_conditions
                        │      (CreateModel)        (RunSQL: triggers, FTS)        (partial indexes)
                        │
                        └→ categories/0002_seed_categories
                               (RunPython: seed data)

ads/0003_add_index_conditions → core/0001_verify_lifecycle_indexes
                                     (RunSQL: CREATE INDEX IF NOT EXISTS)
```

---

## 4. RenameField Strategy — Title/Description → Title_Ru/Description_Ru

### 4.1 RenameField Behavior
Django `migrations.RenameField(old_name, new_name, ...)` maps to PostgreSQL:
```sql
ALTER TABLE ads RENAME COLUMN "title" TO "title_ru";
ALTER TABLE ads RENAME COLUMN "description" TO "description_ru";
```
- **Data is fully preserved** — it's a metadata-only operation, no data movement
- **Auto-reversible** — reverse operation renames columns back to original names
- **Constraints preserved** — NOT NULL, CHECK, DEFAULT all carry over

### 4.2 ⚠️ CRITICAL ISSUE: Search Vector Trigger References Old Column Names

The existing trigger function `ads_search_vector_fn()` references `NEW.title` and `NEW.description`:

```sql
NEW.search_vector :=
    setweight(to_tsvector('russian', coalesce(NEW.title,'')), 'A') ||
    setweight(to_tsvector('russian', coalesce(NEW.description,'')), 'B') ||
    setweight(to_tsvector('russian', coalesce(v_cat,'')), 'C');
```

After renaming `title` → `title_ru` and `description` → `description_ru`, PostgreSQL will reject any INSERT/UPDATE on the `ads` table because the trigger function references non-existent columns.

**The trigger function MUST be updated in the SAME migration** that performs the column renames, OR the trigger must be dropped before the rename and recreated immediately after.

### 4.3 Recommended Migration Structure (0004_ad_i18n_columns.py)

```
1. RunSQL: DROP TRIGGER IF EXISTS ads_search_vector_update ON ads;
           DROP FUNCTION IF EXISTS ads_search_vector_fn();
           reverse_sql: migrations.RunSQL.noop

2. RenameField: title → title_ru
                description → description_ru
                (Auto-reverse: renames back)

3. AddField: title_bs (CharField, max_length=200, blank=True, null=True)
             description_bs (TextField, blank=True, null=True)
             title_en (CharField, max_length=200, blank=True, null=True)
             description_en (TextField, blank=True, null=True)
             original_language (CharField, max_length=5, blank=True, null=True)
             (Auto-reverse: RemoveField)

4. RunSQL: CREATE OR REPLACE FUNCTION ads_search_vector_fn() ... (with NEW.title_ru, NEW.description_ru, NEW.title_bs, NEW.description_bs, NEW.title_en, NEW.description_en)
           CREATE TRIGGER ads_search_vector_update ...
           reverse_sql: migrations.RunSQL.noop
```

**This merges tasks 1.2 and 1.4** into a single migration to avoid downtime.

### 4.4 Alternative: Separate Migrations (Downtime Window)

If keeping 0004 and 0005 separate is required:
- **Between migrations**: `ads_search_vector_update` trigger is absent
- Any INSERT/UPDATE during this window will NOT update `search_vector` (it stays NULL or stale)
- Acceptable only if deployment is fast (< 1 second window) and no writes happen between migrations

---

## 5. Data Preservation Assessment

### 5.1 Existing Russian Content
- `title` and `description` currently hold Russian text only
- `RenameField` preserves all existing data perfectly
- After rename: `title_ru` and `description_ru` contain the original values

### 5.2 Backward Compatibility
- No existing code outside the Ad model references `title`/`description` by their Python attribute names
- After migration + model update, all references must use `title_ru`/`description_ru` or getter methods
- The `category_name` field is unaffected (trigger-synced, no rename)

---

## 6. Rollback Strategy

### 6.1 Forward Migration Rollback
```bash
python manage.py migrate ads 0003
```
Django flattens all operations in reverse:
1. `RunSQL` (noop reverse) — does nothing
2. `RemoveField` for `title_en`, `description_en`, `title_bs`, `description_bs`, `original_language`
3. `RenameField` renames `title_ru`→`title`, `description_ru`→`description`
4. `RunSQL` (noop reverse before trigger was dropped) — does nothing

### 6.2 ⚠️ Issue: Trigger Not Restored on Rollback
The `RunSQL` that drops the trigger has `reverse_sql=migrations.RunSQL.noop`. Rolling back to 0003:
- Leaves the old trigger function (`ads_search_vector_fn`) intact (it was `CREATE OR REPLACE`, not DROP)
- Leaves the trigger (`ads_search_vector_update`) intact (it was DROP+CREATE, but DROP is outside rollback scope if we moved it)

**Mitigation**: Store the original trigger SQL and use it as `reverse_sql` for the DROP step, OR ensure the trigger function is `CREATE OR REPLACE` with the old column names as reverse_sql.

### 6.3 Recommended Rollback-Safe Structure

```python
# Step 1: Drop trigger with restore reverse_sql
migrations.RunSQL(
    sql="DROP TRIGGER IF EXISTS ads_search_vector_update ON ads;",
    reverse_sql="""
        CREATE TRIGGER ads_search_vector_update
        BEFORE INSERT OR UPDATE ON ads
        FOR EACH ROW EXECUTE FUNCTION ads_search_vector_fn_old();
    """,
),
# Step 2: Replace function — store old version as reverse_sql
migrations.RunSQL(
    sql="DROP FUNCTION IF EXISTS ads_search_vector_fn();",
    reverse_sql="""
        CREATE FUNCTION ads_search_vector_fn() RETURNS TRIGGER AS $$
        DECLARE v_cat TEXT;
        BEGIN
          SELECT name INTO v_cat FROM categories WHERE id = NEW.category_id;
          NEW.category_name := v_cat;
          NEW.search_vector :=
            setweight(to_tsvector('russian', coalesce(NEW.title,'')), 'A') ||
            setweight(to_tsvector('russian', coalesce(NEW.description,'')), 'B') ||
            setweight(to_tsvector('russian', coalesce(v_cat,'')), 'C');
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """,
),
# Steps 3-4: RenameField + AddField (auto-reverse — Django handles it)
# Step 5: Create new trigger
migrations.RunSQL(
    sql="""CREATE TRIGGER ads_search_vector_update
           BEFORE INSERT OR UPDATE ON ads
           FOR EACH ROW EXECUTE FUNCTION ads_search_vector_fn();""",
    reverse_sql="DROP TRIGGER IF EXISTS ads_search_vector_update ON ads;",
),
```

> **Note**: The reverse function is named `ads_search_vector_fn()` in both old and new versions. This works because the function is replaced before the columns are renamed. On rollback: column renames are reversed first (auto), then the function is replaced back to old SQL. The trigger is always recreated at the end.

---

## 7. Migration Ordering Requirements

After implementing Task 1.2 (0004), the full migration chain becomes:

```
ads/0001_initial → ads/0002 → ads/0003 → ads/0004_ad_i18n_columns (NEW)
                                                                    ↓
core/0001                                                  ads/0005_multi_lang_search_vector (optional if merged)
```

**Key ordering rules:**
- `0004_ad_i18n_columns` must depend on `ads/0003_add_index_conditions`
- `main/0001_verify_lifecycle_indexes` depends on `ads/0003` — no change needed
- If Task 1.4 (0005) is separate, it must depend on 0004
- Category/city model changes (Task 1.5, 1.6) are independent of the rename

---

## 8. Go/No-Go Recommendation

### ✅ GO

| Criterion | Status | Notes |
|-----------|--------|-------|
| Rename strategy documented | ✅ | `RenameField` preserves all data |
| Rollback approach identified | ✅ | Rollback-safe with stored reverse SQL for trigger |
| Data preservation verified | ✅ | `RenameField` is metadata-only; no data loss |
| No conflicting dependencies | ✅ | No circular deps; Task 1.2 depends on 0003 |


### Recommendations

1. **Merge Tasks 1.2 and 1.4** into a single migration `0004_ad_i18n_columns.py` to avoid the trigger gap window
2. **Include rollback-safe reverse SQL** for all `RunSQL` operations (see Section 6.3)
3. **Order model changes**: Update `ads/models.py` (`title`→`title_ru`) BEFORE or TOGETHER with migration 0004
4. **Dependency update**: Task 1.3 (model getters) should be sequenced to run WITH Task 1.2 since both modify the Ad model
5. **Post-migration**: Run `manage.py update_search_vectors` (or equivalent backfill) for any rows affected during the migration window

---

## 9. Migration File Template — 0004_ad_i18n_columns.py

```python
"""Add multi-language columns to ads table with updated search vector trigger."""

from django.db import migrations, models

# Old search vector function (for rollback recovery)
OLD_SEARCH_VECTOR_FN = """
CREATE OR REPLACE FUNCTION ads_search_vector_fn() RETURNS TRIGGER AS $$
DECLARE v_cat TEXT;
BEGIN
  SELECT name INTO v_cat FROM categories WHERE id = NEW.category_id;
  NEW.category_name := v_cat;
  NEW.search_vector :=
    setweight(to_tsvector('russian', coalesce(NEW.title,'')), 'A') ||
    setweight(to_tsvector('russian', coalesce(NEW.description,'')), 'B') ||
    setweight(to_tsvector('russian', coalesce(v_cat,'')), 'C');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

# New multi-language search vector function
NEW_SEARCH_VECTOR_FN = """
CREATE OR REPLACE FUNCTION ads_search_vector_fn() RETURNS TRIGGER AS $$
DECLARE v_cat TEXT;
BEGIN
  SELECT name INTO v_cat FROM categories WHERE id = NEW.category_id;
  NEW.category_name := v_cat;
  NEW.search_vector :=
    setweight(to_tsvector('russian', coalesce(NEW.title_ru,'')), 'A') ||
    setweight(to_tsvector('russian', coalesce(NEW.description_ru,'')), 'B') ||
    setweight(to_tsvector('simple', coalesce(NEW.title_bs,'')), 'A') ||
    setweight(to_tsvector('simple', coalesce(NEW.description_bs,'')), 'B') ||
    setweight(to_tsvector('english', coalesce(NEW.title_en,'')), 'A') ||
    setweight(to_tsvector('english', coalesce(NEW.description_en,'')), 'B') ||
    setweight(to_tsvector('simple', coalesce(v_cat,'')), 'C');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

TRIGGER_SQL = """
CREATE TRIGGER ads_search_vector_update
  BEFORE INSERT OR UPDATE ON ads
  FOR EACH ROW EXECUTE FUNCTION ads_search_vector_fn();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("ads", "0003_add_index_conditions"),
    ]

    operations = [
        # Step 1: Drop trigger (safe, replaced in step 5)
        migrations.RunSQL(
            sql="DROP TRIGGER IF EXISTS ads_search_vector_update ON ads;",
            reverse_sql=TRIGGER_SQL,
        ),
        # Step 2: Replace trigger function with new multi-language version
        migrations.RunSQL(
            sql=NEW_SEARCH_VECTOR_FN,
            reverse_sql=OLD_SEARCH_VECTOR_FN,
        ),
        # Step 3: Rename existing Russian columns
        migrations.RenameField(
            model_name="ad",
            old_name="title",
            new_name="title_ru",
        ),
        migrations.RenameField(
            model_name="ad",
            old_name="description",
            new_name="description_ru",
        ),
        # Step 4: Add new language columns
        migrations.AddField(
            model_name="ad",
            name="title_bs",
            field=models.CharField(max_length=200, blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ad",
            name="description_bs",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ad",
            name="title_en",
            field=models.CharField(max_length=200, blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ad",
            name="description_en",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ad",
            name="original_language",
            field=models.CharField(max_length=5, blank=True, null=True),
        ),
        # Step 5: Recreate trigger
        migrations.RunSQL(
            sql=TRIGGER_SQL,
            reverse_sql="DROP TRIGGER IF EXISTS ads_search_vector_update ON ads;",
        ),
    ]
```
