---
id: ent-035-seed-catalog-yaml-rewrite-parity
domain: planning
tags:
  - seed
  - catalog
  - builder
  - yaml
  - parity
  - low-risk
related:
  - 05-catalog-seeding-validated-findings
  - test_seed
  - load_catalog
  - seed_service
---

# ENT-035 — Seed Service YAML-Rewrite Parity

**Block:** ENT-035 (advisory, LOW)  
**Source spec:** `05-catalog-seeding-validated-findings.md`  
**Date:** 2026-09-09  
**Researcher needed:** **No.** One-line change with zero behavioral impact on current state. The `load_catalog` guard (`if slug_rename_map and rewrite_yaml`) short-circuits on empty `slug_rename_map`, and `categories.yaml` is currently clean (0 `new_slug`/`deferred` entries). The `rewrite_yaml` parameter and its semantics are already established by the management command (`load_catalog.py`).

---

## 1. Summary

`SeedService._load_category_fixtures` (`seed_service.py`, line 279) calls `load_catalog(CATALOG_PATH)` — using the **default** `rewrite_yaml=True`. This diverges from the production one-shot (`manage.py load_catalog --no-rewrite`), which explicitly sets `rewrite_yaml=False`.

The divergence is **latent**: the guard at `builder.py:159` (`if slug_rename_map and rewrite_yaml:`) only invokes `_rewrite_yaml` when `slug_rename_map` is non-empty, and `categories.yaml` currently has zero `new_slug` entries, so `slug_rename_map` is always empty. No YAML mutation occurs today regardless of the flag.

This block aligns the demo seed with the prod one-shot by passing `rewrite_yaml=False`, making the seed service's intent explicit and preventing future drift: a future category rename (adding `new_slug` to `categories.yaml`) would cause the demo seed to mutate the canonical YAML file while prod treats it as immutable.

---

## 2. Exact File Change

### 2.1 Pass `rewrite_yaml=False` to `load_catalog` in `_load_category_fixtures`

**File:** `src/backend/apps/seed/services/seed_service.py`  
**Function:** `SeedService._load_category_fixtures`  
**Line 279**

**Current:**
```python
        load_catalog(CATALOG_PATH)
```

**After:**
```python
        load_catalog(CATALOG_PATH, rewrite_yaml=False)
```

**Signature of target** (`src/backend/apps/categories/catalog/builder.py`):
```python
def load_catalog(
    config_path: str | Path,
    apps: Any = None,
    rewrite_yaml: bool = True,
) -> dict[str, str]:
```

**The guard that makes this safe** (`builder.py`, line 159):
```python
    if slug_rename_map and rewrite_yaml:
        _rewrite_yaml(config_path, slug_rename_map)
```

- `slug_rename_map` is populated only from `new_slug` entries in `categories.yaml`.
- Confirmed: `grep` for `new_slug` and `deferred` in all `*.yaml` under `src/backend/apps/categories/catalog/` returns **zero matches** — the YAML is clean.
- Therefore `slug_rename_map` is always `{}` → the `if` guard short-circuits → `_rewrite_yaml` is never called, **regardless** of `rewrite_yaml`.
- The change has **zero behavioral impact** on the current codebase. It is purely a forward-looking parity guard that makes the seed service's intent explicit and future-proof.

### 2.2 No other changes required

This is a one-line change to a single call site. No migration, no schema change, no new code.

---

## 3. Call Chain and Impact Analysis

The change to `_load_category_fixtures` is exercised via two paths:

1. **`SeedService.run()` → `_load_category_fixtures()`** — invoked by the `seed` management command (`src/backend/apps/seed/management/commands/seed.py:119`): `service = SeedService(...)` → `service.run(...)`.

2. **Direct unit test** — `TestLeafCategoryFixtures.test_load_category_fixtures_returns_leaf_only` and `test_non_leaf_categories_excluded` (`test_seed.py`, lines 1366–1388) call `service._load_category_fixtures()` directly.

Note: `TestLeafCategoryFiltering` (the class containing these tests) is decorated with `@pytest.mark.seed` (line 1350), meaning it runs only under `make test-all` — **not** the fast gate (`make test`, which sets `PYTEST_SKIP_MARKERS=seed` → `-m "not (seed)"`).

Other test classes that call `load_catalog(CATALOG_PATH)` directly in their fixtures (`TestBuilderLoadsAllLeafSlugs` at line 1004, `TestSeedFilterCoverage` at line 1554, etc.) do **not** route through `_load_category_fixtures` — they call `builder.load_catalog` directly and are unaffected by this change.

---

## 4. Test Strategy

### 4.1 New tests required

**None.** This is a forward-looking parity guard with zero behavioral change. No new test can meaningfully assert a difference — the guard short-circuits before any rewrite path is reached. Adding a test that mocks `load_catalog` to assert `rewrite_yaml=False` is passed would test the mock, not the behavior.

### 4.2 Existing tests that exercise the changed code

| Test | Class | File | Marker | What it validates |
|------|-------|------|--------|-------------------|
| `test_load_category_fixtures_returns_leaf_only` | `TestLeafCategoryFiltering` | `test_seed.py:1366` | `seed` | `_load_category_fixtures()` returns only 171 leaf categories. |
| `test_non_leaf_categories_excluded` | `TestLeafCategoryFiltering` | `test_seed.py:1378` | `seed` | Parent slugs (`real-estate`, `transport`, etc.) are excluded. |
| `TestSeedFilterCoverage` tests | `TestSeedFilterCoverage` | `test_seed.py:1540` | `slow`, `integration` | Full `call_command("seed")` end-to-end populates features/conditions on ads — routes through `SeedService.run()` → `_load_category_fixtures()`. |

### 4.3 No regression assertions to satisfy

- No test asserts on `categories.yaml` file content.
- No test asserts on `categories.yaml` file mtime or modification time.
- No test asserts on `_rewrite_yaml` being or not being called.
- The `slug_rename_map` return value of `load_catalog` is not checked by any seed test (seed service ignores the return value at line 279).

---

## 5. Verification Commands

### 5.1 Lint and format

```powershell
uv run ruff check src/backend/apps/seed/services/seed_service.py
uv run ruff format --check src/backend/apps/seed/services/seed_service.py
```

### 5.2 Typecheck

```powershell
uv run basedpyright src/backend/apps/seed/services/seed_service.py
```

### 5.3 Fast gate (default dev iteration — skips `seed` marker suite)

```powershell
make test
```
This excludes `TestLeafCategoryFiltering` (marked `@pytest.mark.seed`). It does **not** directly exercise the changed line, but confirms no collateral breakage in the fast suite.

### 5.4 Seed suite (directly exercises the changed code)

These tests route through `_load_category_fixtures()` and must pass:

```powershell
# Single targeted class (includes seed marker, overrides PYTEST_SKIP_MARKERS)
$dc='docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml'
$dc run --rm -e PYTEST_OPTS="-v -k TestLeafCategoryFixtures" -e PYTEST_SKIP_MARKERS="" test

# Or the seed command coverage class:
$dc run --rm -e PYTEST_OPTS="-v -m seed -k TestSeedFilterCoverage or TestLeafCategoryFiltering" -e PYTEST_SKIP_MARKERS="" test
```

### 5.5 Full suite (includes nightly seed)

```powershell
make test-all
```

### 5.6 Verification criteria

- `ruff check` reports zero findings on `seed_service.py`.
- `basedpyright` reports zero findings on `seed_service.py`.
- `TestLeafCategoryFiltering` (2 tests) pass: 171 leaf categories returned, parent slugs excluded.
- `TestSeedFilterCoverage` tests pass: full `call_command("seed")` end-to-end still populates data.
- `categories.yaml` file is **not modified** by the test run (no YAML rewrite occurred — confirming the guard short-circuit).

---

## 6. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Behavioral change breaks existing tests | None — the guard `if slug_rename_map and rewrite_yaml` short-circuits on empty `slug_rename_map`, and `categories.yaml` has zero `new_slug` entries. | Verified via `grep` for `new_slug` / `deferred` in `*.yaml` — zero matches. |
| Future `new_slug` addition in `categories.yaml` causes seed to mutate YAML | Low (this is the risk the change *prevents*) | With `rewrite_yaml=False`, the seed service will never rewrite the YAML even if a future rename adds `new_slug`. This is the entire point of the change. The prod one-shot already behaves this way (`load_catalog.py:41`). |
| Lint/format/typecheck failure | None | One-line change — the new argument is a keyword literal matching the existing parameter signature. |
| Missing migration | Not applicable | No schema or model change. |

---

## 7. Sequencing and Dependencies

**Dependencies:** None. This is a leaf block — it depends only on the established `load_catalog` signature and the clean state of `categories.yaml`.

**Downstream:** None. This change does not expose a new API or interface to other blocks.

**Parallelizable:** Fully independent. Can be implemented in parallel with any other block that does not modify `seed_service.py:_load_category_fixtures` or `builder.py:load_catalog`.

```
ENT-035 (seed YAML-rewrite parity)
  └─ T1: Change load_catalog(CATALOG_PATH) → load_catalog(CATALOG_PATH, rewrite_yaml=False) at seed_service.py:279
      └─ T2: Run lint + typecheck + seed suite
```

T2 depends on T1 (verification). No other task dependencies.
