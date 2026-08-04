# Problem: Pre-existing Migration Graph Inconsistency (trust ↔ users)

**File:** `pre-existing_migration_graph_inconsistency.md`
**Date:** 2026-08-03
**Severity:** ~~Medium~~ **RESOLVED**

---

## ~~Description~~ Resolution

**Root cause:** `trust/migrations/0001_initial.py` referenced `("users", "0002")` as a dependency, but the users migration file is named `0002_user_chat_id.py` (not `0002.py`). Django's migration graph uses the full migration name (file stem) as the node key, so the real node was `('users', '0002_user_chat_id')`, not `('users', '0002')`.

**Fix:** Updated `trust/migrations/0001_initial.py` line 12:
```python
# Before:
dependencies = [("users", "0002")]
# After:
dependencies = [("users", "0002_user_chat_id")]
```

**Verification:**
- `makemigrations --check --dry-run` now passes graph validation (migration graph is consistent)
- `showmigrations` correctly lists all migrations including `users/0002_user_chat_id`
- Only 1 DummyNode existed (confirmed via graph dump), now resolved

## Affected Modules

- `src/backend/apps/trust/migrations/0001_initial.py` — fixed dependency reference

## Risk

**Resolved.** No remaining migration graph issues. Pre-existing pending model changes (detected by makemigrations) are unrelated to this fix — they were always pending but masked by the graph validation error.

## Architectural Impact

Migration graph validation now passes. All Django management commands (`migrate`, `makemigrations`, `showmigrations`) now work correctly. Consolidation (TSK-008) is unblocked.