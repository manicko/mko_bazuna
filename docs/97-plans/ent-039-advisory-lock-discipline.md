---
id: ent-039-advisory-lock-discipline
domain: planning
tags:
  - advisory-lock
  - catalog
  - builder
  - enums
  - testing
related:
  - 05-catalog-seeding-validated-findings
  - test_advisory_lock_ids
  - migrate_locked
  - create_admin_user
---

# ENT-039 — Advisory Lock Discipline for Catalog Loading

**Block:** ENT-039 (advisory, LOW)  
**Source spec:** `05-catalog-seeding-validated-findings.md`  
**Date:** 2026-09-09  
**Researcher needed:** **No.** The approach is unambiguous: an enum extension, a context-manager wrap, and a static-analysis test. The lock pattern is identical to two existing reference implementations. The test pattern is well-established.

---

## 1. Summary

`load_catalog` runs as a Docker one-shot (`/load` entrypoint → `manage.py load_catalog --no-rewrite`) that gates `web` and `bot` container startup via `depends_on: service_completed_successfully`. Unlike every other one-shot in the chain (`migrate`, `create_admin`, `seed`), it acquires **no PostgreSQL advisory lock**. A retried container or a manual `make load-catalog` re-run can interleave `update_or_create` + MPTT `insert_at()` transactions and corrupt the category tree (`lft`/`rght` integrity).

This block adds `AdvisoryLockId.CATALOG_LOAD = 104` (ID 104, **not** 103 — 103 is owned by `SWEEP_ORPHANED_MEDIA` per cross-phase reconciliation), wraps `builder.load_catalog`'s `transaction.atomic()` block with `advisory_lock(CATALOG_LOAD, session=True)`, and adds a static-analysis test that AST-scans every source file for stale or typo'd lock references.

The `load_cities` one-shot (ENT-031 scope, not yet implemented) is noted as a forward-looking consumer of the same lock.

---

## 2. Exact File Changes

### 2.1 Add `CATALOG_LOAD` to `AdvisoryLockId` enum

**File:** `src/backend/apps/core/enums.py`  
**Location:** Inside `class AdvisoryLockId(IntEnum)`, after line 38 (`SWEEP_ORPHANED_MEDIA = 103`)

**Current (lines 35–43):**
```python
    MIGRATE = 100
    CREATE_ADMIN = 101
    BACKFILL_THUMBNAILS = 102
    SWEEP_ORPHANED_MEDIA = 103
    QUEUE_PROCESSING = 10
    PURGE_DELETED_ADS = 11
    RECOMPUTE_NORMALIZED_PRICES = 12
    SEED = 110
    TEST_SCHEMA_SETUP = 111
```

**After (insert `CATALOG_LOAD = 104` after `SWEEP_ORPHANED_MEDIA`):**
```python
    MIGRATE = 100
    CREATE_ADMIN = 101
    BACKFILL_THUMBNAILS = 102
    SWEEP_ORPHANED_MEDIA = 103
    CATALOG_LOAD = 104
    QUEUE_PROCESSING = 10
    PURGE_DELETED_ADS = 11
    RECOMPUTE_NORMALIZED_PRICES = 12
    SEED = 110
    TEST_SCHEMA_SETUP = 111
```

### 2.2 Wrap `builder.load_catalog` with the advisory lock

**File:** `src/backend/apps/categories/catalog/builder.py`  
**Function:** `load_catalog()` (lines 53–158)

#### Change A — Add lazy imports (after line 104)

**Current (lines 102–104):**
```python
    """

    from django.db import transaction
```

**After:**
```python
    """

    from django.db import transaction

    from apps.core.enums import AdvisoryLockId
    from apps.core.utils.advisory_lock import advisory_lock
```

#### Change B — Wrap `transaction.atomic()` with `advisory_lock` (line 121)

The `transaction.atomic()` block at line 121 wraps phases 1–4 (lines 122–151). Wrap the entire block with `advisory_lock(AdvisoryLockId.CATALOG_LOAD, session=True):` and indent all content inside it by 4 additional spaces.

**Current (lines 121–151, content inside `transaction.atomic()`):**
```python
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
        # Phase 1: Load lookups

        group_map = _load_lookups(data.get("lookups", {}), apps=apps)

        # Phase 2: Load category tree

        category_map = _load_categories(
            data.get("categories", []),
            group_map,
            slug_rename_map,
            apps=apps,
        )

        # Phase 3: Load bindings

        _load_bindings(
            data.get("categories", []),
            category_map,
            group_map,
            apps=apps,
        )

        # Phase 4: Load category paths

        _load_category_paths(
            data.get("category_paths", []),
            category_map,
            slug_rename_map,
            apps=apps,
        )
```

**After (wrap with advisory_lock, indent content by 4):**
```python
    with advisory_lock(AdvisoryLockId.CATALOG_LOAD, session=True):
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
            # Phase 1: Load lookups

            group_map = _load_lookups(data.get("lookups", {}), apps=apps)

            # Phase 2: Load category tree

            category_map = _load_categories(
                data.get("categories", []),
                group_map,
                slug_rename_map,
                apps=apps,
            )

            # Phase 3: Load bindings

            _load_bindings(
                data.get("categories", []),
                category_map,
                group_map,
                apps=apps,
            )

            # Phase 4: Load category paths

            _load_category_paths(
                data.get("category_paths", []),
                category_map,
                slug_rename_map,
                apps=apps,
            )
```

The YAML-rewrite logic (lines 153–158) and the `return` statement (line 158) remain **outside** the lock — they are a file I/O operation, not DB mutation, and should not be serialized.

### 2.3 Update `advisory_lock.py` docstring

**File:** `src/backend/apps/core/utils/advisory_lock.py`  
**Location:** Docstring, lines 40–44

The lock-ID allocation table in the docstring is currently missing `SWEEP_ORPHANED_MEDIA = 103` (an existing gap) and needs the new `CATALOG_LOAD = 104` entry.

**Current (lines 40–44):**
```python
        - migrate service: 100 (session-scoped, runs pre-PgBouncer)
        - create_admin_user: 101 (session-scoped)
        - backfill_thumbnails: 102 (session-scoped)
        - seed service: 110 (session-scoped)
        - test schema setup: 111 (session-scoped, serializes xdist workers)
```

**After:**
```python
        - migrate service: 100 (session-scoped, runs pre-PgBouncer)
        - create_admin_user: 101 (session-scoped)
        - backfill_thumbnails: 102 (session-scoped)
        - sweep_orphaned_media: 103 (session-scoped)
        - catalog load (load_catalog / load_cities): 104 (session-scoped)
        - seed service: 110 (session-scoped)
        - test schema setup: 111 (session-scoped, serializes xdist workers)
```

### 2.4 Add tests to `test_advisory_lock_ids.py`

**File:** `src/backend/apps/core/tests/test_advisory_lock_ids.py`

#### Add `TestCatalogLoadLockId` class (after `TestSweepOrphanedMediaLockId`, line 38)

Follows the exact pattern of the existing `TestSweepOrphanedMediaLockId` class:

```python
class TestCatalogLoadLockId:
    """Verify the advisory lock ID for the catalog load one-shot."""

    def test_advisory_lock_id_catalog_load(self) -> None:
        """AdvisoryLockId.CATALOG_LOAD resolves to 104."""
        assert AdvisoryLockId.CATALOG_LOAD == 104
        assert AdvisoryLockId.CATALOG_LOAD.value == 104
```

#### Add `TestAdvisoryLockIdReferences` class (new, AST static-analysis test)

Scans all `.py` files under `src/backend/` and `src/telegram_bot/`, collects every `Attribute(value=Name(id="AdvisoryLockId"), attr=...)`, and asserts the `attr` is a valid `AdvisoryLockId` member:

```python
class TestAdvisoryLockIdReferences:
    """Static AST scan: every ``AdvisoryLockId.*`` attribute access must
    correspond to a defined enum member.

    Catches typos (``AdvisoryLockId.CATALO_LOAD``) and stale references
    to removed lock IDs at CI time, before any runtime call-site is
    exercised.
    """

    @staticmethod
    def _iter_source_files() -> Iterator[Path]:
        """Yield all .py files under src/backend/ and src/telegram_bot/."""
        src_root = Path(__file__).resolve().parents[4]  # → src/
        for search_dir in (src_root / "backend", src_root / "telegram_bot"):
            yield from search_dir.rglob("*.py")

    def test_all_advisory_lock_id_references_are_enum_members(self) -> None:
        """Every ``AdvisoryLockId.MEMBER`` reference in the codebase
        maps to a real member of ``AdvisoryLockId``."""
        valid_members = {m.name for m in AdvisoryLockId}
        violations: list[str] = []

        for py_file in self._iter_source_files():
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "AdvisoryLockId"
                ):
                    if node.attr not in valid_members:
                        violations.append(
                            f"{py_file.relative_to(src_root)}:"
                            f" AdvisoryLockId.{node.attr} is not a "
                            f"valid enum member"
                        )

        assert not violations, (
            "Undefined AdvisoryLockId references found:\n" + "\n".join(violations)
        )
```

**Imports needed at top of the test file:**
```python
import ast
from pathlib import Path
from collections.abc import Iterator
```

---

## 3. Exact Lock Pattern to Replicate

The `session=True` pattern, used by MIGRATE (100), CREATE_ADMIN (101), SEED (110), and TEST_SCHEMA_SETUP (111):

```python
from apps.core.enums import AdvisoryLockId
from apps.core.utils.advisory_lock import advisory_lock

with advisory_lock(AdvisoryLockId.CATALOG_LOAD, session=True):
    with transaction.atomic():
        ...
```

**Key mechanics:**
- `session=True` calls `pg_advisory_lock(lock_id)` — a session-scoped lock acquired before the transaction and held for the connection's lifetime. It is explicitly released via `pg_advisory_unlock` when the context manager exits.
- Unlike transaction-scoped locks (`session=False`), `session=True` **does not** assert that a transaction is active (the guard at `advisory_lock.py:47` is skipped). The lock is held regardless of commit/rollback boundaries.
- The session lock is nested inside the `transaction.atomic()` block in builder.py — the transaction provides row-level atomicity, the session lock provides cross-process serialization.

**Reference implementations:**
1. `migrate_locked.py:48` — `with advisory_lock(AdvisoryLockId.MIGRATE, session=True):` (top-level imports)
2. `create_admin_user.py:75` — `with advisory_lock(AdvisoryLockId.CREATE_ADMIN, session=True):` (top-level imports)
3. `conftest.py:124` — `with advisory_lock(AdvisoryLockId.TEST_SCHEMA_SETUP, session=True):` (lazy imports inside a function)

For `builder.py`, the lazy-import style (`from apps.core.enums import AdvisoryLockId` / `from apps.core.utils.advisory_lock import advisory_lock` inside `load_catalog`, alongside the existing `from django.db import transaction`) is used because `builder.py` is imported at module load time by both management commands and migration paths, and the enum/utility modules require Django settings to be configured. This mirrors the `conftest.py` pattern.

---

## 4. Implementation Options and Key Trade-offs

### Option A: Wrap `transaction.atomic()` inside `builder.load_catalog` (selected)

**Pros:**
- Both the production `load_catalog` management command (`load_catalog.py:36`) and `SeedService._load_category_fixtures` (`seed_service.py:279`) call `builder.load_catalog` directly — locking at the function level protects all callers.
- The spec and auditor handoff explicitly target `builder.py:121`.
- The YAML-rewrite step (which operates on the filesystem, not the DB) stays outside the lock — correct, since it doesn't need serialization.

**Cons:**
- Requires re-indenting ~30 lines of phase logic inside `transaction.atomic()`. This is a mechanical indentation change with no semantic impact.

### Option B: Wrap in the management command `load_catalog.py` (rejected)

**Pros:** No changes to `builder.py`'s internals.

**Cons:**
- `SeedService._load_category_fixtures` calls `builder.load_catalog` directly and would **not** be protected.
- Diverges from the spec's explicit instruction to wrap `builder.py:121`.
- The lock would not protect `SeedService._load_category_fixtures` (which runs under the demo `seed` profile), leaving a gap for concurrent seed + catalog runs in dev.

### Option C: Wrap at the Docker entrypoint (`entrypoint-catalog.sh`) (rejected)

**Pros:** No Python changes.

**Cons:**
- `entrypoint-catalog.sh` is a Bash script — it cannot call Python-level PostgreSQL advisory locks.
- Does not protect other callers of `builder.load_catalog`.

### `load_cities` one-shot (forward-looking)

`load_cities` does **not** exist yet (confirmed: `grep -rn "load_cities" src/` returns only references in audit docs). It is ENT-031's scope (mandatory, HIGH — create a reference-data management command reusing `cities.json`, wired into the one-shot chain). When implemented, it should acquire `AdvisoryLockId.CATALOG_LOAD` with `session=True` (the same lock as `load_catalog`), since:
- Both are catalog reference-data one-shots in the same Docker `depends_on` chain (sequential by design).
- Both mutate catalog reference tables that the web/bot startup depends on.
- Sharing the lock is the correct serialization domain — a stale lock in one blocks the other, matching the spec's warning about ID 103 collision.

This block does **not** create the `load_cities` command — that is ENT-031's domain. The `CATALOG_LOAD = 104` member is added now so it is available.

---

## 5. Test Strategy

### 5.1 New tests

| Test | Class | File | Mark | Description |
|------|-------|------|------|-------------|
| `test_advisory_lock_id_catalog_load` | `TestCatalogLoadLockId` | `test_advisory_lock_ids.py` | `unit` | Asserts `AdvisoryLockId.CATALOG_LOAD == 104` (both identity and `.value`), guarding against renumbering. |
| `test_all_advisory_lock_id_references_are_enum_members` | `TestAdvisoryLockIdReferences` | `test_advisory_lock_ids.py` | `unit` | AST-scans all `.py` under `src/backend/` and `src/telegram_bot/`, collects `Attribute(value=Name(id="AdvisoryLockId"), attr=...)`, asserts each `attr` is a valid enum member. |

### 5.2 Existing tests (no changes required)

- `TestTestSchemaSetupLockId` — unchanged, still validates ID 111.
- `TestSweepOrphanedMediaLockId` — unchanged, still validates ID 103.
- `TestSweepLockOrdering` in `test_sweep_lock_structure.py` — unaffected; it tests periodic sweep commands (transaction-scoped locks), not one-shot catalog loading.

### 5.3 Marks

- `pytest.mark.unit` (module-level `pytestmark = [pytest.mark.unit]`) — both new tests are pure static analysis / enum assertions. No database, no Django setup, no I/O beyond file reads. `asyncio_mode = "strict"` in `pyproject.toml` means async markers are needed for async tests — not applicable here.

### 5.4 How to run

**Fast gate (no Docker DB required — these are pure unit tests):**
```powershell
$dc = 'docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml'
$dc run --rm test uv run pytest src/backend/apps/core/tests/test_advisory_lock_ids.py -v
```

**From within the Docker test container (full entrypoint flow):**
```powershell
$dc run --rm -e PYTEST_OPTS="-v -k TestCatalogLoad or TestAdvisoryLockIdReferences" test
```

**Lint + typecheck after changes:**
```powershell
uv run ruff check src/backend/apps/core/enums.py src/backend/apps/categories/catalog/builder.py src/backend/apps/core/tests/test_advisory_lock_ids.py src/backend/apps/core/utils/advisory_lock.py
uv run ruff format --check src/backend/apps/core/enums.py src/backend/apps/categories/catalog/builder.py src/backend/apps/core/tests/test_advisory_lock_ids.py src/backend/apps/core/utils/advisory_lock.py
uv run basedpyright src/backend/apps/core/enums.py src/backend/apps/categories/catalog/builder.py src/backend/apps/core/tests/test_advisory_lock_ids.py
```

### 5.5 Verification criteria

- `CATALOG_LOAD` appears in `AdvisoryLockId.__members__`.
- `builder.load_catalog`'s `transaction.atomic()` block is the direct child of `with advisory_lock(AdvisoryLockId.CATALOG_LOAD, session=True):`.
- The AST scan test passes (no `AdvisoryLockId.*` reference resolves to an undefined member).
- `ruff check` and `basedpyright` pass on all changed files.

---

## 6. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Indentation change in `builder.py` introduces a syntax error | Low | `ruff check` + `basedpyright` catch before tests run. The `pyright: ignore` comment on the `transaction.atomic()` line is preserved. |
| AST scan fails on a file with a valid `AdvisoryLockId.MEMBER` reference that was later removed from the enum | Low | The test will catch it at CI — that is its purpose. |
| Session-scoped lock prevents `load_catalog` from running after a crashed process leaves a stale lock | Low | `pg_advisory_lock` is session-scoped — it is automatically released when the DB connection closes. A crashed container loses its connection, releasing the lock. This is the same risk profile as `MIGRATE`, `CREATE_ADMIN`, and `SEED`. |
| `SeedService._load_city_fixtures` is unaffected by this change (no lock) | Informational | `load_cities` (ENT-031) will add the lock to the cities path. `SeedService._load_category_fixtures` calls `builder.load_catalog` which is now locked. |

---

## 7. Sequencing and Dependencies

This block has **zero** upstream dependencies. It introduces a new lock ID that is not consumed by any other block yet. It can be implemented in parallel with ENT-031 (which will add the `load_cities` one-shot and acquire `CATALOG_LOAD`).

```
ENT-039 (lock discipline)
  ├─ T1: Add CATALOG_LOAD = 104 to AdvisoryLockId enum
  ├─ T2: Wrap builder.load_catalog transaction.atomic() with advisory_lock
  ├─ T3: Update advisory_lock.py docstring (add 103 + 104 entries)
  ├─ T4: Add TestCatalogLoadLockId + TestAdvisoryLockIdReferences to test file
  └─ T5: Run lint + typecheck + tests

ENT-031 (load_cities one-shot) — downstream, can run in parallel
  └─ Acquires AdvisoryLockId.CATALOG_LOAD (ID 104) — must be implemented AFTER T1
```

All tasks T1–T5 are independent except T4 depends on T1 (the test asserts the enum member exists). T2 and T3 are independent of each other.
