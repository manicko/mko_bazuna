# F1 — Research: Class-Scoped Seed Fixture Pattern in pytest-django

**Date:** 2026-10-11
**Author:** Researcher (R1)
**Source plan:** `.ai/plans/test-suite-optimization-plan.md` (Step 3 #1, F1)
**Execution plan:** `.ai/plans/test-suite-optimization-execution-plan.md` (Block 5)
**Audit evidence:** `.ai/outputs/test-suite-optimization-audit.md` §3.3
**Return as:** `{context_r}` — deliverable for the Implementor

---

## Executive Summary

The correct pattern for a class-scoped fixture that runs `call_command("seed")` once per test class and persists seed data across all test methods in that class **is viable** under the project's current configuration (`@pytest.mark.django_db` without `transaction=True`, PostgreSQL backend, pytest-django 4.12+, pytest-randomly 5.0.0, xdist with `--dist loadgroup`).

The mechanism: a class-scoped fixture using `django_db_setup` (session-scoped) + `django_db_blocker.unblock()` commits seed data to the database. Each test method's function-scoped `db`/`django_db` marker wraps the test in a per-test `transaction.atomic()` block. The per-test rollback (`ROLLBACK`) only undoes changes made *within* the test's transaction, not data committed before the transaction began. This is identical in principle to Django's `setUpTestData`.

**Confidence levels:** HIGH for the core mechanism (verified against installed Django 5.2.17 and pytest-django 4.12+ source). MEDIUM for cross-worker/xdist interactions (depends on test distribution at runtime). LOW for edge cases with `--reuse-db` stale state from interrupted runs.

---

## 1. The Correct Pattern

### 1.1 Recommended fixture (class-scoped, in `apps/seed/tests/conftest.py`)

```python
from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command

from apps.categories.catalog.builder import load_catalog
from apps.locations.models import City
from apps.seed.tests.conftest import _NoImageGenerator  # reuse existing stub


@pytest.fixture(scope="class")
def seeded_test_data(django_db_setup, django_db_blocker):
    """Run the seed pipeline once per test class, committing data that persists.

    Depends on ``django_db_setup`` (session-scoped) to ensure the test DB
    exists, and uses ``django_db_blocker.unblock()`` to allow writes outside
    any per-test transaction. Data committed here is visible to every test
    in the class; per-test savepoint rollbacks do NOT undo committed rows.

    The ``_NoImageGenerator`` stub is applied here (not at function scope)
    because the real ImageGenerator preprocesses ~1004 photos — tens of
    seconds per seed call. The function-scoped ``_no_op_image_generator``
    fixture in this conftest only patches DURING tests, not before them.
    """
    from apps.categories.models import Category  # noqa: F811 — avoid circular import

    catalog_path = (
        Path(__file__).resolve().parents[3]  # tests/ → seed/ → apps/ → backend/
        / "categories"
        / "catalog"
        / "categories.yaml"
    )
    with django_db_blocker.unblock(), patch(
        "apps.seed.services.seed_service.ImageGenerator", _NoImageGenerator
    ):
        load_catalog(catalog_path)
        City.objects.get_or_create(
            slug="budva",
            defaults={"name": "Будва", "region": "Coastal", "country_code": "ME"},
        )
        City.objects.get_or_create(
            slug="podgorica",
            defaults={"name": "Подгорица", "region": "Central", "country_code": "ME"},
        )
        out = StringIO()
        call_command(
            "seed",
            "--users=4",
            "--ads=40",
            "--force",
            "--analytics=False",
            stdout=out,
        )
        yield
```

### 1.2 Refactored `TestSeedFilterCoverage`

```python
@pytest.mark.seed
class TestSeedFilterCoverage:
    """Seed data carries ``listing_purpose`` and ``features`` so the F4/F5
    buyer-facing filters are testable on seed data."""

    @pytest.fixture(autouse=True)
    def _setup_class(self, seeded_test_data: None) -> None:
        """Trigger the class-scoped seed fixture.

        Previously function-scoped with ``db: None``, which re-ran
        ``load_catalog`` + city creation + ``self._run_seed()`` per test.
        Now delegates to ``seeded_test_data`` (class scope) for one-time setup.
        """
        # No-op body: the ``seeded_test_data`` fixture handles all setup.
        # This autouse fixture exists only to request ``seeded_test_data``
        # at class scope so it is guaranteed to run before any test method.
        pass

    def test_seed_populates_listing_purpose(self, db: None) -> None:
        """At least one seeded ad has a listing_purpose (F4)."""
        assert Ad.objects.filter(
            source=AdSource.SEED, listing_purpose__isnull=False
        ).exists()

    # ... all 8 tests lose their self._run_seed() call, but keep db: None ...
```

### 1.3 Why `django_db_setup` + `django_db_blocker` instead of `db`

The `db` fixture is **function-scoped** (`pytest_django/fixtures.py:370`). A class-scoped fixture cannot depend on a function-scoped fixture — pytest raises `ScopeMismatchError: You tried to access the 'function' scoped fixture 'db' with a 'class' scoped request object`.

Instead, the class-scoped fixture must:
1. Depend on `django_db_setup` (session-scoped) — this triggers test-DB creation but does NOT itself unblock DB writes.
2. Call `django_db_blocker.unblock()` as a context manager — this temporarily lifts the pytest-django DB access blocker so `call_command` can write to the DB.

This is the **exact pattern documented by pytest-django** (`pytest_django/fixtures.py` docs):
> ```python
> @pytest.fixture(scope='session')
> def django_db_setup(django_db_setup, django_db_blocker):
>     with django_db_blocker.unblock():
>         call_command('loaddata', 'my_fixture.json')
> ```
> "This loads the Django fixture ... once for the entire test session. ... The test data will be saved in the database and will not be reset."

The only adaptation is changing `scope='session'` to `scope='class'` so the seed runs once per class (different seed parameters across classes in the same file require this).

---

## 2. Exact Mechanism: Why Committed Data Survives Per-Test Rollback

### 2.1 Non-transactional test flow (what the project uses)

The project uses `@pytest.mark.django_db` (no `transaction=True`) at file level (`pyproject.toml:172` — registered as default `transaction=False`). For non-transactional tests, pytest-django's `_django_db_helper` (`pytest_django/fixtures.py:206-300`) does:

```
_pytest_db_helper (function-scoped, autouse via _django_db_marker):
    1. Creates PytestDjangoTestCase(django.test.TestCase)
       — setUpClass/tearDownClass OVERRIDDEN to no-ops calling
         TransactionTestCase versions (SKIP TestCase.setUpClass,
         which would enter a class-level atomic block)
    2. PytestDjangoTestCase.setUpClass()   → TransactionTestCase.setUpClass (no atomic)
    3. test_case = PytestDjangoTestCase(methodName="__init__")
    4. test_case._pre_setup()
         → TransactionTestCase._pre_setup() → cls._fixture_setup()  [CLASSMETHOD]
       → TestCase._fixture_setup (line 1459):
           cls.atomics = cls._enter_atomics()
       → TestCase._enter_atomics (line 1381):
           atomic = transaction.atomic(using="default")
           atomic.__enter__()      → BEGIN (real transaction, NOT savepoint)
    5. yield  ← TEST RUNS HERE
    6. test_case._post_teardown()
         → TransactionTestCase._post_teardown() → self._fixture_teardown()
       → TestCase._fixture_teardown (line 1480):
           self._rollback_atomics(self.atomics)
       → TestCase._rollback_atomics (line 1391):
           transaction.set_rollback(True)
           atomic.__exit__(None, None, None)   → ROLLBACK
    7. PytestDjangoTestCase.tearDownClass()  → TransactionTestCase.tearDownClass (no-op)
```

### 2.2 The key insight

Since pytest-django **skips** `TestCase.setUpClass` (which would create a class-level `transaction.atomic()` wrapper), each test's `_fixture_setup` enters a **top-level transaction** (`BEGIN`). The `ROLLBACK` in `_fixture_teardown` undoes only changes made within that `BEGIN...ROLLBACK` window — it does NOT affect data committed before the `BEGIN`.

Source code evidence (Django 5.2, `.venv/Lib/site-packages/django/test/testcases.py`):

```python
# Line 1381-1389 — _enter_atomics enters a REAL transaction atomically
@classmethod
def _enter_atomics(cls):
    """Open atomic blocks for multiple databases."""
    atomics = {}
    for db_name in cls._databases_names():
        atomic = transaction.atomic(using=db_name)
        atomic._from_testcase = True
        atomic.__enter__()          # → BEGIN (if no outer transaction)
        atomics[db_name] = atomic
    return atomics

# Line 1480-1488 — _fixture_teardown rolls back ONLY what _fixture_setup opened
def _fixture_teardown(self):
    ...
    self._rollback_atomics(self.atomics)   # → set_rollback(True) + __exit__ → ROLLBACK
```

The comment in pytest-django's `_django_db_helper` (line 266-278) explicitly confirms this design:
> "TestCase's class setup manages the setUpTestData/class-level transaction functionality. We don't use it; instead we (will) offer our own alternatives. So it only adds overhead, and does some things which conflict with our (planned) functionality, particularly, it closes all database connections in tearDownClass which inhibits wrapping tests in higher-scoped transactions."

### 2.3 Fixture setup ordering

For a test in `TestSeedFilterCoverage`, pytest resolves fixtures in scope order:

| Scope | Fixture | Role |
|-------|---------|------|
| session | `django_db_setup` | Creates `test_mko_bazuna` database |
| session (autouse) | `_restore_test_schema_post_db_setup` (conftest.py:111) | Restores triggers, exchange rates under advisory lock 111 |
| **class** | **`seeded_test_data`** | Runs `call_command("seed")` → commits 4 users, 40 ads, etc. |
| function (autouse) | `_django_db_marker` → `_django_db_helper` | Starts per-test `BEGIN` transaction |
| function (autouse) | `_no_op_image_generator` | Patches `ImageGenerator` for the test (no-op since tests don't seed per-test) |
| function | `db` (if requested via `db: None` param) | Triggers `_django_db_helper` (same as `_django_db_marker`) |

Higher-scoped fixtures complete before lower-scoped ones begin. So `seeded_test_data` (class) finishes — including its `call_command` + commit — before any test's per-test transaction (`BEGIN`) starts.

### 2.4 PostgreSQL isolation semantics

The project uses PostgreSQL 18 (`pyproject.toml:10` in AGENTS.md). PostgreSQL's default isolation level is `READ COMMITTED`. Committed data from the class-scoped fixture is visible to all subsequent transactions (per-test `BEGIN`), and per-test `ROLLBACK` cannot undo committed writes.

---

## 3. Do Existing `db: None` Test Parameters Need to Change?

**No — they can stay as-is.** Here is the full analysis:

### 3.1 `db: None` is redundant but harmless

The file `test_seed.py` has `pytestmark = [pytest.mark.django_db, pytest.mark.integration]` at line 45. This marker already triggers `_django_db_marker` (autouse, function-scoped, `pytest_django/plugin.py:561`), which requests `_django_db_helper` for each test. The explicit `db: None` parameter on each test method (e.g., `def test_seed_populates_listing_purpose(self, db: None)`) is redundant — pytest-django's `_db_blocker` would activate even without it, because the `django_db` marker is present.

**Recommendation:** Remove `db: None` from the 8 test signatures in `TestSeedFilterCoverage` for cleanliness (since `pytestmark` already covers it). This is optional — keeping them is harmless.

### 3.2 The `_setup_class` fixture must change scope

The current `_setup_class` fixture is function-scoped (default scope) and depends on `db: None`:
```python
@pytest.fixture(autouse=True)
def _setup_class(self, db: None) -> None:
```

A class-scoped fixture **cannot** depend on the function-scoped `db` fixture. pytest raises `ScopeMismatchError`. The fixture must instead depend on `django_db_setup` (session) + `django_db_blocker` (for `unblock()`).

### 3.3 `TestSeedCommand` and `TestSeedCommandEnhanced` are NOT affected

These classes have their **own** `_setup_class` fixtures (function-scoped, `db: None`) and call `call_command("seed", ...)` with **different per-test parameters** inside each test method. They are completely independent of `TestSeedFilterCoverage`'s class-scoped fixture. No changes are needed.

---

## 4. How to Handle `_setup_class`: Change to Class Scope

### 4.1 Current state

```python
@pytest.fixture(autouse=True)
def _setup_class(self, db: None) -> None:           # function-scoped
    from apps.categories.catalog.builder import load_catalog
    CATALOG_PATH = ...
    load_catalog(CATALOG_PATH)                         # runs per-test, rolled back
    City.objects.create(name="Будва", slug="budva", ...)  # runs per-test
    City.objects.create(name="Подгорица", slug="podgorica", ...)
```

This runs `load_catalog()` + 2 `City.objects.create()` calls **before every test** (8× redundant), all within the per-test transaction (rolled back at teardown).

### 4.2 Recommended approach: Merge into the class-scoped seed fixture

The seed command's `_load_category_fixtures()` (seed_service.py:263) already calls `load_catalog()` internally, and `_load_city_fixtures()` (line 286) loads cities from `cities.json` via `bulk_create(update_conflicts=True, unique_fields=["slug"])`. The `cities.json` fixture already contains entries for "budva" and "podgorica" (verified at `apps/seed/fixtures/cities.json` lines 2, 6).

**Recommendation:** Merge the `_setup_class` logic into the class-scoped `_seeded_test_data` fixture. The `load_catalog` + city creation is redundant with what the seed command already does internally. The `_seeded_test_data` fixture should:

1. `with django_db_blocker.unblock():`
2. `load_catalog(CATALOG_PATH)` — idempotent via `update_or_create` (builder.py:191-204, 295-304). Harmless even if seed command also calls it.
3. `City.objects.get_or_create(...)` for "budva" and "podgorica" — idempotent. Note: the seed command's `bulk_create(update_conflicts=True)` will update these if they already exist.
4. `call_command("seed", "--users=4", "--ads=40", "--force", "--analytics=False")` — which internally calls `_clean()` (deletes all SEED rows), `load_catalog()`, `_load_city_fixtures()`, and generates users/ads.

The existing `_setup_class` autouse fixture can then become a thin no-op that just requests `_seeded_test_data`:

```python
@pytest.fixture(autouse=True, scope="class")
def _setup_class(self, seeded_test_data: None) -> None:
    pass  # All setup done in seeded_test_data
```

**OR** — simpler: remove `_setup_class` entirely and have each test method request `seeded_test_data` directly:

```python
def test_seed_populates_listing_purpose(self, db: None, seeded_test_data: None) -> None:
```

But since `seeded_test_data` is class-scoped, pytest will only call it once (for the first test that requests it). Subsequent tests in the same class get the cached result. This works because class-scoped fixtures are cached per-class.

**Simplest approach (recommended):** Keep `seeded_test_data` as a non-autouse class fixture in `conftest.py`, and have tests request it explicitly or via an autouse class fixture that delegates to it.

### 4.3 The `_NoImageGenerator` patching issue (CRITICAL)

The `apps/seed/tests/conftest.py` defines:
```python
@pytest.fixture(autouse=True)
def _no_op_image_generator(request: pytest.FixtureRequest) -> Iterator[None]:
    ...
    with patch("apps.seed.services.seed_service.ImageGenerator", _NoImageGenerator):
        yield
```

This is **function-scoped** and **autouse**. It patches `ImageGenerator` only during individual test execution, NOT during class-scoped fixture setup. If the class-scoped `seeded_test_data` fixture calls `call_command("seed", ...)`, the real `ImageGenerator` would activate — preprocessing ~1004 photos and computing SHA-256, taking "tens of seconds per call" (conftest.py docstring lines 4-6).

**The class-scoped fixture MUST apply the `_NoImageGenerator` patch itself** (via `with patch(...)` inside the fixture body). The `_NoImageGenerator` class is defined in the same `conftest.py` module and can be referenced directly or imported.

---

## 5. `transaction=True` vs Plain `django_db`

### 5.1 Plain `@pytest.mark.django_db` (no `transaction=True`) — CURRENT AND RECOMMENDED

**Mechanism:** Each test runs within a per-test `transaction.atomic()` block. `_fixture_setup` enters `atomic().__enter__()` → `BEGIN`. `_fixture_teardown` calls `_rollback_atomics()` → `set_rollback(True)` + `atomic.__exit__()` → `ROLLBACK`.

**Class-scoped data:** Committed data from a class-scoped fixture survives per-test `ROLLBACK` because `ROLLBACK` only undoes changes made within the test's transaction.

**TRUNCATE between tests:** NO. Isolation is via transaction rollback, not `TRUNCATE` / `flush`.

**Performance:** Fast — no table flushing.

### 5.2 `@pytest.mark.django_db(transaction=True)` — INCOMPATIBLE

**Mechanism:** Uses `django.test.TransactionTestCase` instead of `TestCase`. Per-test isolation is via `TRUNCATE` + `flush` (not transaction rollback).

**Class-scoped data:** DESTROYED between tests. `TransactionTestCase._post_teardown` calls `self._fixture_teardown()` → `TransactionTestCase._fixture_teardown` → `call_command("flush", ...)` which TRUNCATEs all tables.

**Evidence:** From pytest-django docs (database.html):
> "In case you use transactional tests (you use the `pytest.mark.django_db()` marker with `transaction=True`, or the `transactional_db` fixture), you need to repopulate your database every time a test starts, because the database is cleared between tests."

**Stack Overflow [6]** confirms: session-scoped `django_db_setup` data is wiped between tests when `transaction=True` is used.

**Conclusion:** `TestSeedFilterCoverage` must NOT use `transaction=True`. The current file-level `pytestmark = [pytest.mark.django_db, ...]` (no `transaction=True`) is correct. The `concurrent` marker in the rules (rules.md line 53) uses `transaction=True` for bot tests — those are in a different file and unaffected.

---

## 6. `pytest-randomly` Interaction

### 6.1 Does random ordering affect class-scoped fixtures?

**No.** `pytest-randomly` 5.0.0 shuffles test items but does NOT affect fixture scoping:

- `pytest_collection_modifyitems` (`__init__.py:209`) calls `_shuffle_by_class(items, seed)` which groups tests by class (`_get_cls`), shuffles within each class group (by `item.nodeid` hash), and shuffles the order of class groups. Tests within a class remain **grouped together** in the final list.
- `_shuffle_by_class` does NOT break class grouping — it shuffles the order of classes and the order of tests within each class, but keeps all tests of one class contiguous.
- A class-scoped fixture runs once when the **first** test of that class executes (in the shuffled order). All subsequent tests in the same class see the fixture's committed data.
- `pytest_runtest_setup` (`__init__.py:193`) only reseeds the Python `random` module per test — it does NOT touch DB or fixture scoping.

### 6.2 Cross-class data leakage with random ordering

**Risk:** If `TestSeedFilterCoverage` tests run before `TestSeedCommand` tests (due to random ordering), the committed seed data (4 SEED users, 40 SEED ads) from `TestSeedFilterCoverage`'s class fixture would be visible to `TestSeedCommand`'s tests.

**Mitigation — this is SAFE in the current codebase:**

Every `TestSeedCommand` test method calls `call_command("seed", "--force", ...)` (test_seed.py lines 820, 834, 849, 862, 869, 886, 896). The `--force` flag triggers `_clean()` (seed_service.py:87, 225) which **deletes all SEED rows** (`Ad.objects.filter(source=AdSource.SEED).delete()`, `User.objects.filter(source=AdSource.SEED).delete()`, etc.) within the test's own transaction before re-seeding.

Key evidence:
- `_clean()` (seed_service.py:225-249): Deletes rows by `source=AdSource.SEED` field directly — NOT via reverse-FK traversal. Runs in `transaction.atomic()` (savepoint within the test's transaction).
- `test_seed_with_zero_count` (test_seed.py:817): Calls `seed --users=0 --ads=0 --force`, then asserts `User.objects.count() == 0`. The `--force` flag triggers `_clean()` which deletes the committed SEED users (within the test's transaction), so the count is 0 within the test. ✓
- `test_seed_recovers_from_orphaned_users` (test_seed.py:877): Explicitly tests `_clean()` by creating orphaned users and verifying they're cleaned on re-seed. ✓
- `TestSeedCommandEnhanced` tests (lines 1285-1348): All call `call_command("seed", ...)` with `--force`. ✓

**Residual risk (LOW):** If a future test in `TestSeedCommand` or `TestSeedCommandEnhanced` asserts on global counts (`User.objects.count()`, `Ad.objects.count()`) WITHOUT calling `call_command("seed", "--force", ...)` first, it would see the committed SEED rows from `TestSeedFilterCoverage`. This would be a latent bug. **Recommendation:** Document this constraint and verify during code review.

### 6.3 `--randomly-seed` reproducibility

`pytest-randomly` is fully reproducible: the seed is printed at run start (`Using --randomly-seed=N`) and cached, and CI/dev can replay with `--randomly-seed=N`. This means any cross-class leakage issue would be reproducible and debuggable.

---

## 7. Relationship Between Class-Scoped `django_db_setup` Fixture and Function-Scoped `db`

### 7.1 Two separate responsibilities

| Fixture | Scope | Responsibility |
|---------|-------|----------------|
| `django_db_setup` | session | Creates/destroys the test database (runs `setup_databases`) |
| `django_db_blocker` | session | Blocks/unblocks DB access at the connection-wrapper level |
| `_seeded_test_data` | **class** | Commits seed data once per class (uses `django_db_setup` + `django_db_blocker.unblock()`) |
| `db` | function | Triggers per-test transaction (via `_django_db_helper`) |

### 7.2 The `django_db_setup` fixture is NOT the right place for seed

Overriding the global `django_db_setup` (as the docs show for session-wide fixture loading) is **session-scoped** — it would run seed ONCE for the entire test session. This is incompatible with the file's 4 seed test classes (`TestSeedCommand`, `TestSeedCommandEnhanced`, `TestSeedCategoryIntegration`, `TestSeedFilterCoverage`), which use **different per-test seed parameters** and must NOT share a single seed run.

Instead, the class-scoped `_seeded_test_data` fixture is the correct scope — it runs once per class, only for `TestSeedFilterCoverage`.

### 7.3 The `db` fixture and class-scoped fixture are complementary

- `seeded_test_data` (class): writes + commits data → available to all tests in the class
- `db` / `django_db` marker (function): wraps each test in a transaction → isolates test-specific changes

Tests in `TestSeedFilterCoverage` can still request `db: None` (or rely on `pytestmark`) for the per-test transaction wrapper. The committed seed data from `seeded_test_data` is visible inside the test's transaction; the test's own changes (if any) are rolled back without affecting the seed data.

---

## 8. Gotchas with TRUNCATE / flush Between Tests

### 8.1 Non-transactional `django_db` (the default) — NO TRUNCATE

With `@pytest.mark.django_db` (no `transaction=True`), pytest-django uses `django.test.TestCase` semantics. Each test's `_fixture_teardown` calls `_rollback_atomics(self.atomics)` which does `set_rollback(True)` + `atomic.__exit__()` → `ROLLBACK`. **No `TRUNCATE` or `flush` occurs between tests.**

Django's `flush` command (used by `TransactionTestCase`) is ONLY triggered when `transaction=True` is used. The code path:
- `TransactionTestCase._fixture_teardown` (testcases.py:1253-1269): calls `call_command("flush", ...)` if no savepoints, or truncates tables.
- `TestCase._fixture_teardown` (override at line 1480): only does `_rollback_atomics` — NO flush.

Since `TestSeedFilterCoverage` uses non-transactional `django_db`, there is no TRUNCATE between tests. Committed class-scoped data persists. ✓

### 8.2 `--reuse-db` consideration

With `--reuse-db` (the project's default per `entrypoint-test.sh:57` and `conftest.py` comment), the test database schema persists across runs. A previous run's committed class-scoped seed data could persist if:
- The class-scoped fixture committed data
- The test session was interrupted (SIGKILL) before teardown
- `--reuse-db` skips schema rebuild

**Mitigation:** The seed command's `_clean()` + `--force` flag deletes all SEED rows at the start of each seed run. For `TestSeedFilterCoverage`, the class-scoped fixture runs seed with `--force`, which calls `_clean()` first. So even with stale data from a previous run, `_clean()` wipes it before re-seeding. ✓

**Residual risk (LOW):** If a `TestSeedCommand` test runs after a `--reuse-db` run where `TestSeedFilterCoverage`'s committed seed data leaked, and the test asserts `User.objects.count() == 0` without calling `--force` seed first... but as analyzed in §6.2, all such tests DO call `--force` seed. ✓

### 8.3 xdist worker distribution

`xdist_group` markers pin tests to the same worker. `TestSeedFilterCoverage` tests do NOT currently have an `xdist_group` marker. With `--dist loadgroup` (entrypoint-test.sh:57), tests without a group are distributed via the default `load` scheduler (round-robin). This means `TestSeedFilterCoverage` tests could be split across up to 4 workers (`--maxprocesses=4`).

**Impact:** Each worker that receives at least one `TestSeedFilterCoverage` test will independently run the class-scoped `_seeded_test_data` fixture (seed runs once per worker). The advisory lock (`AdvisoryLockId.SEED`) serializes across workers — one worker blocks while another runs seed.

**Recommendation:** Add `@pytest.mark.xdist_group("seed_filter_coverage")` to `TestSeedFilterCoverage` to ensure all 8 tests run on the same worker, so seed runs exactly once total. This aligns with the project's existing pattern of using `xdist_group` for shared-state tests (rules.md:55, audit §3.7).

---

## 9. Recommended Concrete Implementation Steps

### Step 1: Add `seeded_test_data` fixture to `apps/seed/tests/conftest.py`

- Class-scoped, non-autouse (requested explicitly by `TestSeedFilterCoverage`)
- Depends on `django_db_setup` (session) + `django_db_blocker`
- Applies `patch("apps.seed.services.seed_service.ImageGenerator", _NoImageGenerator)` — **critical**: must patch before calling `call_command("seed")`
- Runs `load_catalog()` + `City.objects.get_or_create()` + `call_command("seed", "--users=4", "--ads=40", "--force", "--analytics=False")`
- `yield` after seed (no teardown needed — per-test rollback handles per-test cleanup; committed seed data is cleaned by the next `--force` seed run in other classes)

### Step 2: Refactor `TestSeedFilterCoverage` in `test_seed.py`

1. Change `_setup_class` to class scope with `seeded_test_data` dependency:
   ```python
   @pytest.fixture(autouse=True, scope="class")
   def _setup_class(self, seeded_test_data: None) -> None:
       pass
   ```
2. Remove `self._run_seed()` calls from all 8 test methods
3. Remove `db: None` from test method signatures (optional — `pytestmark` already covers it). **Recommendation:** keep `db: None` to be explicit and match the pattern used by other classes in the file.
4. Add `@pytest.mark.xdist_group("seed_filter_coverage")` to the class for xdist pinning

### Step 3: Keep `_run_seed()` method for reuse

The execution plan (line 120) says to keep `_run_seed()` for tests that need it (e.g., `test_seed_idempotent`). However, `test_seed_idempotent` is in `TestSeedCommand`, not `TestSeedFilterCoverage`, and that class is NOT being modified. So `_run_seed()` in `TestSeedFilterCoverage` can be removed entirely. If any future test in `TestSeedFilterCoverage` needs a fresh seed, it can call `call_command("seed", ...)` directly.

### Step 4: Verification

- Run: `PYTEST_OPTS="-k TestSeedFilterCoverage" ./Makefile.ps1 test-recreate` (fresh schema)
- Confirm: exactly 1 `call_command("seed")` invocation for the class (instrument or time-based check)
- Confirm: all 8 tests pass
- Confirm: `TestSeedCommand` and `TestSeedCommandEnhanced` tests still pass (they should be unaffected)
- Confirm: `test_seed_idempotent` still calls seed twice (it's in a different class, unchanged)
- Test with random seed: `PYTEST_OPTS="--randomly-seed=42 -k TestSeedFilterCoverage" ./Makefile.ps1 test`

### Step 5: Do NOT modify other seed test classes

- `TestSeedCommand` (line 806): function-scoped `_setup_class`, per-test `call_command("seed", ...)` — LEAVE UNCHANGED
- `TestSeedCommandEnhanced` (line 1272): function-scoped `_setup_class`, per-test `call_command("seed", ...)` — LEAVE UNCHANGED
- `TestSeedCategoryIntegration` (line 1354): function-scoped `_setup_class` — LEAVE UNCHANGED
- All other classes in the file — LEAVE UNCHANGED

---

## 10. Cross-Reference: Key Source Files and Line Numbers

| File | Lines | What |
|------|-------|------|
| `pytest_django/fixtures.py` | 162-203 | `django_db_setup` session fixture (DB creation) |
| `pytest_django/fixtures.py` | 206-300 | `_django_db_helper` (per-test transaction wrapping) |
| `pytest_django/fixtures.py` | 370-384 | `db` fixture (function-scoped, requests `_django_db_helper`) |
| `pytest_django/plugin.py` | 561-566 | `_django_db_marker` autouse fixture (triggers helper for `django_db` marker) |
| `django/test/testcases.py` | 1381-1396 | `TestCase._enter_atomics` / `_rollback_atomics` |
| `django/test/testcases.py` | 1407-1447 | `TestCase.setUpClass` / `tearDownClass` (class-level atomic — SKIPPED by pytest-django) |
| `django/test/testcases.py` | 1459-1488 | `TestCase._fixture_setup` / `_fixture_teardown` (per-test atomic + rollback) |
| `src/backend/conftest.py` | 111-165 | Session-autouse `_restore_test_schema_post_db_setup` |
| `src/backend/apps/seed/tests/conftest.py` | 24-46 | `_NoImageGenerator` stub + `_no_op_image_generator` autouse fixture |
| `src/backend/apps/seed/services/seed_service.py` | 87 | `_clean()` called before seed generation |
| `src/backend/apps/seed/services/seed_service.py` | 91 | `transaction.atomic()` wrapping generation |
| `src/backend/apps/seed/services/seed_service.py` | 225-249 | `_clean()` implementation (deletes by `source=AdSource.SEED`) |
| `src/backend/apps/seed/tests/test_seed.py` | 45 | `pytestmark = [pytest.mark.django_db, pytest.mark.integration]` |
| `src/backend/apps/seed/tests/test_seed.py` | 1911-2038 | `TestSeedFilterCoverage` class |
| `src/backend/apps/seed/tests/test_seed.py` | 1934-1943 | `_run_seed()` method |
| `src/backend/apps/seed/tests/test_seed.py` | 1916-1932 | Current `_setup_class` (function-scoped, `db: None`) |
| `src/backend/apps/categories/catalog/builder.py` | 95-155 | `load_catalog()` (idempotent via `update_or_create`) |
| `pyproject.toml` | 162-181 | pytest config (`strict_config=true`, markers, `addopts`) |
| `pyproject.toml` | 221 | `pytest-randomly>=3.16.0` dependency |
| `docker/entrypoint-test.sh` | 57 | `--reuse-db ... -n auto --maxprocesses=4 --dist loadgroup` |
| `pytest_randomly/__init__.py` | 209-271 | `_shuffle_by_class` (preserves class grouping) |
| `pytest_randomly/__init__.py` | 193-206 | `pytest_runtest_setup/call/teardown` (reseed per test) |
