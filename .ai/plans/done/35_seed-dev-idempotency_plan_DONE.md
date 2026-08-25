---
id: 35_seed-dev-idempotency
spec: .ai/problems/11_seed-dev-idempotency_spec.md
domain: implementation-plan
spec_status: Approved (PO decisions: Q1=A, Q2=A+C, Q3=A, Q4=A, Q5=A)
priority: High
date: 2026-08-25
stack: Python 3.14 · Django 5.2 LTS · PostgreSQL 18 · aiogram 3.x · uv · Docker Compose v2 · PowerShell 5.1
research:
  - .ai/research/seed-idempotency-audit.md
  - .ai/research/docker-one-shot-lifecycle-analysis.md
platform: Windows (Makefile.ps1, PS 5.1) + Unix (Makefile, bash)
---

# Plan 35 — Seed Idempotency: Fix Orphaned Users + Transaction + Dev Workflow

## Statement of Scope

Three root-cause classes must be fixed for `docker compose up` to reliably re-seed
seed data without `IntegrityError`:

1. **CRITICAL — Orphaned seed users:** `_clean()` identifies seed `User` records via
   reverse FK `User.objects.filter(ads__source=AdSource.SEED)`. If users exist but
   their ads do not (from a crashed previous run), they are invisible to cleanup →
   `telegram_id` collision on re-seed. **Fix:** Add `source` field to `User` model;
   `UserGenerator` sets `source=AdSource.SEED`; `_clean()` filters by `source` directly.

2. **CRITICAL — Generation phase not transactional:** Steps 4–13 of `SeedService.run()`
   run in autocommit. Mid-generation crash leaves partial data. **Fix:** Wrap the
   entire generation phase in `transaction.atomic()`.

3. **HIGH — Trust events (`ad=NULL`) and `PopularSearch` not cleaned:** `_clean()`
   misses these. **Fix:** Add `source` field to `AnalyticsEvent` and `PopularSearch`;
   extend `_clean()` to filter by `source` on all three tables.

Additionally, the **dev workflow** (`make up` / `Invoke-Up`) must force one-shot
service re-runs. **Fix:** Add `docker compose rm -sf migrate load_catalog create_admin seed`
before `up` in both `Makefile` and `Makefile.ps1`.

## Architecture Context

- **Two-process model:** web (gunicorn sync WSGI) + bot (aiogram) share one PostgreSQL.
  Migrations run exactly once before both start. Seed is a separate one-shot service.
- **Advisory locks:** `AdvisoryLockId.SEED = 110` (session-scoped) prevents
  concurrent seed runs. `AdvisoryLockId.MIGRATE = 100` for migrations.
- **`AdSource.SEED = "seed"`** exists in `apps/core/enums.py` and is already used on
  the `Ad` model's `source` field. The plan mirrors this pattern on `User`,
  `AnalyticsEvent`, and `PopularSearch`.
- **Django migrations:** `makemigrations` auto-generates from model changes.
  Migration files are checked into `apps/{users,analytics,search}/migrations/`.
- **Test infrastructure:** Tests run via Docker Compose `test` service (never local
  `uv run pytest`). Test DB uses `--reuse-db` (named volume persists).
  `make test` skips `seed` marker tests (~300s saved vs ~35-min full suite).
- **Windows path:** The project's primary dev workflow on Windows uses
  `Makefile.ps1` (PowerShell 5.1 compatible). Both `Makefile` and `Makefile.ps1`
  must be updated in parallel for workflow changes.

## Confirmed Decisions (PO §7)

| Q | Decision | Implication |
|---|---|---|
| Q1 | A — full overwrite | `make up` always re-seeds completely |
| Q2 | A+C — `User.source` field + transaction | Orphaned users identified directly; generation is all-or-nothing |
| Q3 | A — `rm -sf` before `up` | Both Makefiles updated; one-shot services always re-run |
| Q4 | A — single `transaction.atomic()` | Generation phase is one atomic unit |
| Q5 | A — `source` on all 3 models | Full architectural fix for _clean() robustness |

---

## Execution DAG

```
Phase 0 — Risk Assessment
├── T-0A: Researcher — DB migration impact for additive nullable `source` CharField
└── T-0B: Validator — review transaction scope + _clean() rewrite approach

Phase 1 — Model Field Addition  (parallel — 3 different apps)
├── T-01: Add `source` field to User model
├── T-02: Add `source` field to AnalyticsEvent model
└── T-03: Add `source` field to PopularSearch model

Phase 2 — Migration Generation  (depends on Phase 1)
└── T-04: Run makemigrations for users + analytics + search apps

Phase 3 — Generator Updates  (parallel — depends on Phase 1)
├── T-05: UserGenerator — set source=AdSource.SEED      (depends on T-01)
├── T-06: AnalyticsGenerator — set source=AdSource.SEED (depends on T-02)
└── T-07: _seed_popular_searches — set source=AdSource.SEED (depends on T-03)

Phase 4 — Service Rewrites  (sequential — depends on Phase 1 + 3)
├── T-08: SeedService._clean() — rewrite to use direct `source` filters
│         (depends on T-01, T-02, T-03, T-05, T-06, T-07)
└── T-09: SeedService.run() — wrap generation phase in transaction.atomic()
          (depends on T-08)

Phase 5 — Workflow Changes  (parallel — independent of Python code)
├── T-10: Makefile — add `rm -sf` + `--wait` to `up` target
└── T-11: Makefile.ps1 — add `rm -sf` to `Invoke-Up` (no `--wait` on Windows)

Phase 6 — Test  (depends on T-04, T-05, T-08)
└── T-12: Add orphaned-user recovery test to test_seed.py

Phase 7 — Verification  (depends on all implementation tasks)
└── T-13: Final verification — makemigrations check + test suite + lint + typecheck
```

### Dependency graph (mermaid)

```mermaid
graph TD
    T0A[Researcher: migration impact] --> T01
    T0A --> T02
    T0A --> T03
    T0B[Validator: approach review] --> T08
    T0B --> T09

    T01[User.source field] --> T04[makemigrations]
    T02[AnalyticsEvent.source] --> T04
    T03[PopularSearch.source] --> T04

    T01 --> T05[UserGenerator sets source]
    T02 --> T06[AnalyticsGenerator sets source]
    T03 --> T07[PopularSearch seeder sets source]

    T01 --> T08[_clean() rewrite]
    T02 --> T08
    T03 --> T08
    T05 --> T08
    T06 --> T08
    T07 --> T08

    T08 --> T09[transaction.atomic() wrap]

    T10[Makefile up] --> T13[Verification]
    T11[Makefile.ps1 up] --> T13
    T04 --> T12[Orphaned-user test]
    T05 --> T12
    T08 --> T12
    T09 --> T13
    T12 --> T13
```

### Sequencing rationale

1. **Phase 0 (Risk Assessment) runs first** — schema changes and transaction-scope
   changes are the highest-risk items. The Researcher confirms the migration pattern
   (additive nullable `CharField` with `choices` and `db_index` — mirrors the existing
   `Ad.source` field pattern). The Validator reviews the `_clean()` rewrite logic
   and transaction scope before any code is written.

2. **Phase 1 (Model fields) is parallel** — `User`, `AnalyticsEvent`, and
   `PopularSearch` live in separate apps (`users`, `analytics`, `search`).
   No cross-dependency. Each adds a nullable `source` `CharField(max_length=20,
   choices=[(s.value, s.value) for s in AdSource], null=True, db_index=True)`.

3. **Phase 2 (Migration generation) depends on Phase 1** — `makemigrations`
   reads model definitions and generates migration files. Must wait for all
   three model edits to be complete so a single `makemigrations` call produces
   all three migration files at once.

4. **Phase 3 (Generator updates) is parallel** — `UserGenerator`,
   `AnalyticsGenerator`, and `_seed_popular_searches` are independent generators.
   They only need the model field to exist in Python (Phase 1), not the migration
   to be applied. Can run concurrently with Phase 2.

5. **Phase 4 (Service rewrites) is sequential** — `_clean()` rewrite (T-08)
   changes the cleanup logic to use `source` filters directly; it depends on
   ALL three model fields existing AND all three generators setting `source`.
   The transaction wrapping (T-09) depends on T-08 being complete since both
   edit `SeedService`.

6. **Phase 5 (Workflow) is parallel and independent** — Makefile changes
   touch no Python code. They can be done concurrently with Phase 1–4.

7. **Phase 6 (Test) depends on Phase 2 + Phase 3 + Phase 4** — the orphaned-user
   recovery test requires the `source` field to exist in the migration, the
   `UserGenerator` to set it, and the `_clean()` rewrite to use it.

8. **Phase 7 (Verification) is the final gate** — depends on ALL implementation
   tasks. Runs `makemigrations --check` (no unexpected schema drift), full
   test suite for seed (`make test-all` or targeted test), lint, and typecheck.

---

## Task Specifications

---

### T-01: Add `source` field to `User` model

<details>
<summary>Task details</summary>

**Priority:** P0
**Type:** schema (model definition)
**Depends on:** T-0A (researcher confirms migration pattern)
**Risk:** medium — schema change to the `User` model; `User` is referenced by
`settings.AUTH_USER_MODEL` across multiple apps. Mitigated by: nullable=True,
no default forcing data backfill, `db_index=True` for efficient cleanup query.

**Affected file:**
- `src/backend/apps/users/models.py`

**Affected target:**
- `class User(AbstractUser)` — add `source` field after existing fields

**Semantic anchor:**
- Insert new field after the `telegram_language` field definition (which is
  the last custom field before `Meta`), mirroring the `Ad.source` pattern.

**Changes:**

Add the following field to `User` model (matching `Ad.source` pattern from
`ads/models.py`):

```python
source = models.CharField(
    max_length=20,
    choices=[(s.value, s.value) for s in AdSource],
    default=None,
    null=True,
    blank=True,
    db_index=True,
    help_text="Origin of record (null = real user, 'seed' = seed-generated)",
)
```

**Key differences from `Ad.source`:**
- `default=None, null=True, blank=True` — existing real users have no source;
  only seed users get `AdSource.SEED`. The `Ad` model uses `default=AdSource.TELEGRAM`
  because every ad has a source in production.

**Acceptance criteria:**
- `User` model has a `source` field with `max_length=20`, `choices=[(s.value, s.value) for s in AdSource]`, `null=True`, `blank=True`, `db_index=True`.
- `AdSource` is imported (already exported from `apps/core/__init__.py`).
- No existing fields or methods modified.
- `uv run basedpyright src/backend/apps/users/models.py` passes with no errors.
- `python manage.py makemigrations --check --dry-run` detects the pending change (will be resolved in T-04).

</details>

---

### T-02: Add `source` field to `AnalyticsEvent` model

<details>
<summary>Task details</summary>

**Priority:** P1
**Type:** schema (model definition)
**Depends on:** T-0A (researcher confirms migration pattern)
**Risk:** medium — schema change to `AnalyticsEvent`; referenced from
`apps/analytics/models.py` and `apps/trust/services/trust_calculator.py` (creates
trust events via `AnalyticsEvent.objects.create`).

**Affected file:**
- `src/backend/apps/analytics/models.py`

**Affected target:**
- `class AnalyticsEvent(models.Model)` — add `source` field

**Semantic anchor:**
- Insert after the `ad` ForeignKey field definition.

**Changes:**

```python
source = models.CharField(
    max_length=20,
    choices=[(s.value, s.value) for s in AdSource],
    default=None,
    null=True,
    blank=True,
    db_index=True,
    help_text="Origin of event (null = production, 'seed' = seed-generated)",
)
```

**Acceptance criteria:**
- `AnalyticsEvent` model has `source` field matching the pattern from T-01.
- `AdSource` imported.
- No existing fields modified.
- `uv run basedpyright src/backend/apps/analytics/models.py` passes.

</details>

---

### T-03: Add `source` field to `PopularSearch` model

<details>
<summary>Task details</summary>

**Priority:** P1
**Type:** schema (model definition)
**Depends on:** T-0A (researcher confirms migration pattern)
**Risk:** low — schema change to `PopularSearch`; only referenced from
`apps/search/models.py` and `apps/seed/services/seed_service.py`
(`_seed_popular_searches`).

**Affected file:**
- `src/backend/apps/search/models.py`

**Affected target:**
- `class PopularSearch(models.Model)` — add `source` field

**Semantic anchor:**
- Insert after the `last_seen` field definition.

**Changes:**

```python
source = models.CharField(
    max_length=20,
    choices=[(s.value, s.value) for s in AdSource],
    default=None,
    null=True,
    blank=True,
    db_index=True,
    help_text="Origin of record (null = production, 'seed' = seed-generated)",
)
```

**Acceptance criteria:**
- `PopularSearch` model has `source` field matching the pattern.
- `AdSource` imported.
- No existing fields modified.
- `uv run basedpyright src/backend/apps/search/models.py` passes.

</details>

---

### T-04: Generate Django migrations for the 3 new `source` fields

<details>
<summary>Task details</summary>

**Priority:** P0
**Type:** migration (auto-generated)
**Depends on:** T-01, T-02, T-03 (all model fields must be defined)
**Risk:** medium — creates migration files on 3 apps. Migration files are
reviewed and checked into version control.

**Command:**
```powershell
docker compose --project-name mko-bazuna-dev -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run python src/backend/manage.py makemigrations
```

**Expected output:**
- `apps/users/migrations/0006_user_source.py` — AddField for `User.source`
- `apps/analytics/migrations/0004_analyticsevent_source.py` — AddField for `AnalyticsEvent.source`
- `apps/search/migrations/0007_popularsearch_source.py` — AddField for `PopularSearch.source`

**Migration pattern (from researcher findings — matches existing migrations):**
```python
migrations.AddField(
    model_name="user",
    name="source",
    field=models.CharField(
        blank=True,
        choices=[("telegram", "telegram"), ("seed", "seed")],
        db_index=True,
        default=None,
        help_text="Origin of record (null = real user, 'seed' = seed-generated)",
        max_length=20,
        null=True,
    ),
)
```

**Acceptance criteria:**
- Three migration files generated with sequential numbering.
- `dependencies` correctly reference the previous migration in each app.
- `model_name` is lowercase (`"user"`, `"analyticsevent"`, `"popularsearch"`).
- `makemigrations --check --dry-run` reports no pending changes after migration files exist.
- Migration files pass `ruff check` (no lint errors).

</details>

---

### T-05: UserGenerator — set `source=AdSource.SEED` on generated users

<details>
<summary>Task details</summary>

**Priority:** P0
**Type:** implementation (generator)
**Depends on:** T-01 (User model must have `source` field)
**Risk:** low — the `UserGenerator.generate()` method constructs `User(...)`
instances; adding one field assignment is backward-compatible (existing users
are unaffected; only new seed users get the field).

**Affected file:**
- `src/backend/apps/seed/generators/users.py`

**Affected target:**
- `class UserGenerator(BaseGenerator)` — `generate` method

**Semantic anchor:**
- Add `source=AdSource.SEED` to the `User(...)` constructor call in `generate()`.

**Changes:**

In the `User(...)` constructor inside `UserGenerator.generate()`, add:
```python
source=AdSource.SEED,
```

This ensures every seed-generated user is tagged with `source="seed"` so that
`_clean()` (T-08) can find them directly via `User.objects.filter(source=AdSource.SEED)`.

**Acceptance criteria:**
- `UserGenerator.generate()` passes `source=AdSource.SEED` to every `User(...)` instance.
- No other fields or logic changed.
- `uv run basedpyright src/backend/apps/seed/generators/users.py` passes.
- `AdSource` imported in the module (check existing imports).

</details>

---

### T-06: AnalyticsGenerator — set `source=AdSource.SEED` on generated events

<details>
<summary>Task details</summary>

**Priority:** P0
**Type:** implementation (generator)
**Depends on:** T-02 (AnalyticsEvent model must have `source` field)
**Risk:** low — only affects seed-generated analytics events.

**Affected file:**
- `src/backend/apps/seed/generators/analytics.py`

**Affected targets:**
- `AnalyticsGenerator.generate_events()` — method that creates `AnalyticsEvent.objects.bulk_create(events)`
- `AnalyticsGenerator.generate_contact_events()` — method that creates contact events

**Semantic anchor:**
- In the `AnalyticsEvent(type=..., ...)` constructor calls within `generate_events()`
  and `generate_contact_events()`, add `source=AdSource.SEED`.

**Changes:**

Add `source=AdSource.SEED` to all `AnalyticsEvent(...)` constructor calls in
`generate_events()` and `generate_contact_events()`. Also add it in
`SeedService._seed_analytics_events()` if that method directly creates events
(check `seed_service.py` for any inline `AnalyticsEvent.objects.create()`).

**Acceptance criteria:**
- All `AnalyticsEvent` instances created by the seed pipeline set `source=AdSource.SEED`.
- Trust events (via `TrustCalculator.record_trust_event`) also set `source=AdSource.SEED`
  — or confirm they're created through a path that sets it. (If trust events bypass the
  generator, the `TrustCalculator` or `record_trust_event` must be updated.)
- `uv run basedpyright src/backend/apps/seed/generators/analytics.py` passes.

</details>

---

### T-07: _seed_popular_searches — set `source=AdSource.SEED` on records

<details>
<summary>Task details</summary>

**Priority:** P1
**Type:** implementation (generator)
**Depends on:** T-03 (PopularSearch model must have `source` field)
**Risk:** low — only affects seed-generated popular searches.

**Affected file:**
- `src/backend/apps/seed/services/seed_service.py`

**Affected target:**
- `SeedService._seed_popular_searches()` method

**Semantic anchor:**
- The `update_or_create` calls inside `_seed_popular_searches()` — add `source=AdSource.SEED`
  to the `defaults` dict.

**Changes:**

In `_seed_popular_searches()`, add `source=AdSource.SEED` to the `defaults` dict
of each `PopularSearch.objects.update_or_create()` call so that future `_clean()`
calls can identify and delete seed popular searches directly.

**Acceptance criteria:**
- All `PopularSearch` records created via `_seed_popular_searches()` have `source=AdSource.SEED`.
- Existing behavior (upsert via `update_or_create`) preserved.
- `uv run basedpyright src/backend/apps/seed/services/seed_service.py` passes.

</details>

---

### T-08: SeedService._clean() — rewrite to use direct `source` filters

<details>
<summary>Task details</summary>

**Priority:** P0
**Type:** implementation (seed service)
**Depends on:** T-01, T-02, T-03, T-05, T-06, T-07 (all model fields + generators must set source)
**Risk:** high — this is the core fix. Changes data-deletion logic in `_clean()`.
Must be correct: a bug here could delete non-seed data.

**Affected file:**
- `src/backend/apps/seed/services/seed_service.py`

**Affected target:**
- `SeedService._clean()` method

**Semantic anchor:**
- Replace the `seed_user_ids` reverse-FK query and all `ad__source=AdSource.SEED`
  filters with direct `source=AdSource.SEED` filters.

**Current code (for reference — DO NOT use line numbers):**

```python
def _clean(self) -> None:
    seed_user_ids = list(
        User.objects.filter(ads__source=AdSource.SEED)
        .values_list("id", flat=True)
        .distinct()
    )

    with transaction.atomic():
        DailyAdMetrics.objects.filter(ad__source=AdSource.SEED).delete()
        AnalyticsEvent.objects.filter(ad__source=AdSource.SEED).delete()
        AdImage.objects.filter(ad__source=AdSource.SEED).delete()
        Ad.objects.filter(source=AdSource.SEED).delete()
        if seed_user_ids:
            User.objects.filter(id__in=seed_user_ids).delete()

    # media cleanup ...
```

**New code:**

```python
def _clean(self) -> None:
    with transaction.atomic():
        # Direct source filters — no longer dependent on Ad FK traversal.
        # This fixes the orphaned-user bug: seed users are identified by
        # their own `source` field, not by whether they currently have seed ads.
        DailyAdMetrics.objects.filter(ad__source=AdSource.SEED).delete()
        AnalyticsEvent.objects.filter(source=AdSource.SEED).delete()  # NEW: direct filter
        AdImage.objects.filter(ad__source=AdSource.SEED).delete()
        Ad.objects.filter(source=AdSource.SEED).delete()
        User.objects.filter(source=AdSource.SEED).delete()            # NEW: direct filter
        PopularSearch.objects.filter(source=AdSource.SEED).delete()   # NEW: direct filter

    # media cleanup (unchanged)
    if os.path.exists(seed_dir):
        shutil.rmtree(seed_dir, ignore_errors=True)
    logger.info("Cleaned existing seed data")
```

**Key changes:**
1. `User.objects.filter(id__in=seed_user_ids)` → `User.objects.filter(source=AdSource.SEED)`
   — eliminates the orphaned-user bug.
2. `AnalyticsEvent.objects.filter(ad__source=AdSource.SEED)` → `AnalyticsEvent.objects.filter(source=AdSource.SEED)`
   — catches trust events with `ad=NULL`.
3. Added `PopularSearch.objects.filter(source=AdSource.SEED).delete()` — newly cleaned.
4. `seed_user_ids` pre-computation removed — no longer needed.

**Deletion order preserved (FK-safe):**
1. `DailyAdMetrics` (FK → Ad, CASCADE)
2. `AnalyticsEvent` (FK → Ad, SET_NULL; now also filters by own `source`)
3. `AdImage` (FK → Ad, CASCADE)
4. `Ad` (deleted, cascades to AdImage + AdFeature)
5. `User` (deleted, cascades to SellerTrustScore/SellerVerification)
6. `PopularSearch` (no FK relationship — safe to delete independently)

**Acceptance criteria:**
- `_clean()` uses `User.objects.filter(source=AdSource.SEED)` instead of the reverse-FK query.
- `_clean()` uses `AnalyticsEvent.objects.filter(source=AdSource.SEED)` instead of `ad__source`.
- `_clean()` adds `PopularSearch.objects.filter(source=AdSource.SEED).delete()`.
- Deletion order is FK-safe (children before parents).
- No `seed_user_ids` variable remains.
- If no seed records exist, `_clean()` is a no-op (no errors).
- `uv run basedpyright src/backend/apps/seed/services/seed_service.py` passes.

</details>

---

### T-09: SeedService.run() — wrap generation phase in transaction.atomic()

<details>
<summary>Task details</summary>

**Priority:** P0
**Type:** implementation (seed service — transaction boundary)
**Depends on:** T-08 (_clean() rewrite complete)
**Risk:** high — changes transaction boundary around 9 generation steps.
A long-running transaction may hold locks. Must be evaluated during implementation.

**Affected file:**
- `src/backend/apps/seed/services/seed_service.py`

**Affected target:**
- `SeedService.run()` method — the generation phase (steps 4–13)

**Semantic anchor:**
- Wrap the code between `self._clean()` and `return` in a `with transaction.atomic():` block.

**Changes:**

In `SeedService.run()`, after `self._clean()` returns and before the first generator call,
begin a `transaction.atomic()` block that encompasses:
- `_load_category_fixtures()` + `_load_city_fixtures()` (steps 3–4)
- `UserGenerator.generate()` + `User.objects.bulk_create()` (step 5)
- `AdGenerator.generate()` + `Ad.objects.bulk_create()` (step 6)
- Feature M2M population (step 7)
- `ImageGenerator.generate()` + `AdImage.objects.bulk_create()` (step 8)
- `_backfill_image_hashes()` (step 9)
- `_seed_popular_searches()` (step 10)
- `AnalyticsGenerator.generate_events()` + event `bulk_create()` (step 11)
- `AnalyticsGenerator.generate_daily_metrics()` + `bulk_create` (step 12)
- `TrustCalculator.calculate_and_save()` per user (step 13)

Wrap in:
```python
with transaction.atomic():
    # ... steps 3-13 ...
```

**Performance concern (from spec Q4):** The transaction will hold write locks on
the `users`, `ads`, `ad_images`, `analytics_events`, `daily_ad_metrics`,
`popular_searches` tables for the duration of generating 10 users + 600 ads +
180+ images + 200+ analytics events + trust scores. In the dev/test environment
(this is a single-writer seed service — no concurrent writers), this is safe.
If lock contention is observed during testing, fall back to per-step savepoints
(Option B from spec §6 Task 2).

**Acceptance criteria:**
- Generation phase (post-`_clean()`) is inside `with transaction.atomic():`.
- `_clean()` is OUTSIDE the transaction block (it has its own `transaction.atomic()`).
- On crash mid-generation, the transaction rolls back — DB returns to post-`_clean()` state.
- Advisory lock (ID 110) is still acquired before `_clean()` and released after the entire `run()` completes (unchanged).
- `uv run basedpyright src/backend/apps/seed/services/seed_service.py` passes.

</details>

---

### T-10: Makefile — add `rm -sf` for one-shot services before `up`

<details>
<summary>Task details</summary>

**Priority:** P1
**Type:** workflow (Makefile)
**Depends on:** T-0A (researcher confirmed `rm -sf` is the correct Compose mechanism)
**Risk:** low — operational change to dev Makefile only. No production impact
(test/dev Docker Compose only).

**Affected file:**
- `Makefile` (root)

**Affected target:**
- `up:` target (line 77-78)

**Semantic anchor:**
- The `up:` recipe body.

**Changes:**

Current:
```makefile
up:
	docker compose $(COMPOSE_FILES) up -d
```

New:
```makefile
up:
	docker compose $(COMPOSE_FILES) rm -sf migrate load_catalog create_admin seed
	docker compose $(COMPOSE_FILES) up -d
```

**`COMPOSE_FILES`** = `--env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml`
(defined at line 10 of `Makefile`).

`docker compose rm -sf` removes the exited one-shot containers without prompting.
The next `up` creates fresh containers for `migrate`, `load_catalog`,
`create_admin`, and `seed` — guaranteeing seed re-runs on every `make up`.

**Acceptance criteria:**
- `Makefile` `up` target starts with `docker compose rm -sf migrate load_catalog create_admin seed`.
- Existing `up` behavior (start web + bot) is preserved on the next line.
- `make -n up` (dry run) shows both commands in order.
- No other Makefile targets modified.

</details>

---

### T-11: Makefile.ps1 — add `rm -sf` to `Invoke-Up`

<details>
<summary>Task details</summary>

**Priority:** P1
**Type:** workflow (PowerShell)
**Depends on:** T-0A (researcher confirmed `rm -sf` works on Windows Docker Compose v2)
**Risk:** low — operational change to Windows dev workflow only. No production impact.

**Affected file:**
- `Makefile.ps1` (root)

**Affected target:**
- `Invoke-Up` function (lines 75-82)

**Semantic anchor:**
- Inside `Invoke-Up`, after setting `$env:COMPOSE_PROJECT_NAME = $DevProject`,
  before the `docker compose ... up -d` line.

**Changes:**

Current:
```powershell
function Invoke-Up {
    $env:COMPOSE_PROJECT_NAME = $DevProject
    docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml up -d
    # Also start the long-running test PostgreSQL (host :5433) so the test
    # environment's DB is ready for `test`/`test-db` immediately. Idempotent.
    $env:COMPOSE_PROJECT_NAME = $TestProject
    docker compose -f docker-compose.yml -f docker-compose.test.yml up -d db
}
```

New:
```powershell
function Invoke-Up {
    $env:COMPOSE_PROJECT_NAME = $DevProject
    docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml rm -sf migrate load_catalog create_admin seed
    docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml up -d
    # Also start the long-running test PostgreSQL (host :5433) so the test
    # environment's DB is ready for `test`/`test-db` immediately. Idempotent.
    $env:COMPOSE_PROJECT_NAME = $TestProject
    docker compose -f docker-compose.yml -f docker-compose.test.yml up -d db
}
```

**Windows/PS 5.1 considerations:**
- `docker compose rm -sf` is supported in Docker Compose v2 on Windows — no
  special syntax.
- `$env:COMPOSE_PROJECT_NAME` assignment pattern is already used throughout
  `Makefile.ps1` (PS 5.1 compatible, per file-level comment lines 4-6).
- `--wait` flag is NOT added to `up` — Windows Docker Compose versions vary;
  `--wait` requires Compose v2.20+ (see spec §8.5 research note).

**Acceptance criteria:**
- `Invoke-Up` in `Makefile.ps1` calls `docker compose ... rm -sf migrate load_catalog create_admin seed` before `up -d`.
- Test DB startup logic preserved (unchanged).
- PS 5.1 compatibility maintained (verified by existing `$env:` pattern usage).
- `Makefile.ps1 help` output unchanged.

</details>

---

### T-12: Add orphaned-user recovery test to test_seed.py

<details>
<summary>Task details</summary>

**Priority:** P0
**Type:** test (seed recovery)
**Depends on:** T-04 (migration exists), T-05 (UserGenerator sets source), T-08 (_clean rewrite)
**Risk:** low — test-only file; existing `test_seed_idempotent` is `slow, integration, seed`
marked (skipped in fast gate). New test must also use `--analytics=False` to avoid
trust calculator complexity.

**Affected file:**
- `src/backend/apps/seed/tests/test_seed.py`

**Affected target:**
- `TestSeedCommand` class — add new test method

**Semantic anchor:**
- Add `test_seed_recovers_from_orphaned_users` method to `TestSeedCommand`.

**Changes:**

Add a test that simulates the crash scenario described in spec §3.1:

```python
def test_seed_recovers_from_orphaned_users(self) -> None:
    """Seed must recover when orphaned User records (with source=SEED but no ads)
    survive a previous interrupted run.

    Simulates: seed created users but crashed before creating ads.
    On re-seed, _clean() must find and delete them via the `source` field,
    not the reverse-FK `ads__source` query.
    """
    # Step 1: Seed normally (creates users with source=SEED + ads)
    call_command("seed", "--users=3", "--ads=5", "--force", "--analytics=False")
    assert User.objects.filter(source=AdSource.SEED).count() == 3
    assert Ad.objects.filter(source=AdSource.SEED).count() == 5

    # Step 2: Simulate crash — delete all seed ads but leave orphaned users
    Ad.objects.filter(source=AdSource.SEED).delete()
    assert Ad.objects.filter(source=AdSource.SEED).count() == 0
    assert User.objects.filter(source=AdSource.SEED).count() == 3  # orphans

    # Step 3: Re-seed — _clean() must find orphaned users via `source` field
    call_command("seed", "--users=3", "--ads=5", "--force", "--analytics=False")

    # Step 4: Assert clean state — no duplicates, correct counts
    assert User.objects.filter(source=AdSource.SEED).count() == 3
    assert Ad.objects.filter(source=AdSource.SEED).count() == 5
```

**Acceptance criteria:**
- Test simulates orphaned users (seed ads deleted, seed users retained).
- Test asserts re-seed succeeds (no `IntegrityError`).
- Test asserts correct counts after re-seed (3 users, 5 ads).
- `AdSource` imported in test file (check existing imports).
- Test passes: `pytest apps/seed/tests/test_seed.py::TestSeedCommand::test_seed_recovers_from_orphaned_users -v`
- If the test DB schema doesn't have the `source` field (migration not applied),
  the test must be skipped or fail with a clear migration error (not a silent
  `IntegrityError`).

</details>

---

### T-13: Final verification — makemigrations check + test suite + lint + typecheck

<details>
<summary>Task details</summary>

**Priority:** P0
**Type:** verification
**Depends on:** T-04, T-05, T-06, T-07, T-08, T-09, T-10, T-11, T-12
**Risk:** low — runs existing tooling only.

**Verification steps:**

1. **Migration check (no schema drift):**
   ```powershell
   docker compose --project-name mko-bazuna-dev -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run python src/backend/manage.py makemigrations --check --dry-run
   ```
   Must exit 0 — all model changes accounted for in migration files.

2. **Orphaned-user recovery test:**
   ```powershell
   docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm `
     -e PYTEST_OPTS="apps/seed/tests/test_seed.py::TestSeedCommand::test_seed_idempotent apps/seed/tests/test_seed.py::TestSeedCommand::test_seed_recovers_from_orphaned_users -v" test
   ```
   Both tests must pass.

3. **Full seed test suite (integration, includes analytics):**
   ```powershell
   docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm `
     -e PYTEST_OPTS="apps/seed/tests/test_seed.py -v" test
   ```

4. **Lint:**
   ```powershell
   uv run ruff check src/backend/apps/seed/ src/backend/apps/users/ src/backend/apps/analytics/ src/backend/apps/search/
   ```

5. **Typecheck:**
   ```powershell
   uv run basedpyright src/backend/apps/seed/ src/backend/apps/users/ src/backend/apps/analytics/ src/backend/apps/search/
   ```

**Acceptance criteria:**
- `makemigrations --check --dry-run` reports no changes.
- `test_seed_idempotent` passes (existing behavior — no regression).
- `test_seed_recovers_from_orphaned_users` passes (new orphaned-user scenario).
- Full `test_seed.py` suite passes.
- `ruff check` — 0 errors on changed modules.
- `basedpyright` — 0 errors on changed modules.
- Both `Makefile` and `Makefile.ps1` `up` targets include `rm -sf` one-shot services.

</details>

---

## Risk Assessment

| Task | Risk | Reason | Mitigation |
|---|---|---|---|
| T-01 | medium | Schema change to `User` — referenced cross-app via `AUTH_USER_MODEL` | Nullable field; no data backfill needed; mirrors existing `Ad.source` pattern |
| T-02 | medium | Schema change to `AnalyticsEvent` — referenced from `TrustCalculator` | Nullable field; only seed events set it; no production code path writes `source` |
| T-03 | low | Schema change to `PopularSearch` — only seed + search modules reference it | Nullable field; minimal blast radius |
| T-04 | medium | Creates migration files across 3 apps | Migration files reviewed, checked-in; `makemigrations --check` validates no drift |
| T-05 | low | Adds one field assignment in `UserGenerator.generate()` | No existing behavior changed; only seed users get `source=AdSource.SEED` |
| T-06 | low | Adds field assignment in `AnalyticsGenerator` | Trust event path must also set `source` — verified in task details |
| T-07 | low | Adds `source` to `update_or_create` defaults in `_seed_popular_searches` | Upsert behavior preserved |
| T-08 | high | Rewrites `_clean()` — data deletion logic change | Must delete seed users via `source` (not FK); deletion order verified FK-safe; orphaned-user test (T-12) validates |
| T-09 | high | Wraps 9 generation steps in single transaction — lock duration risk | Dev/test environments are single-writer; fallback to per-step savepoints if contention observed |
| T-10 | low | Makefile `up` target — adds one command | Only affects dev workflow; no production containers affected |
| T-11 | low | Makefile.ps1 `Invoke-Up` — adds one command | PS 5.1 compatibility verified; `--wait` deliberately omitted on Windows |
| T-12 | low | Test-only — adds test method to existing class | Skipped in fast gate (`seed` marker); can't break `make test` |
| T-13 | low | Runs existing verification tooling | Automated; failures point to specific upstream tasks |

### Cross-cutting risks

| Risk | Mitigation |
|---|---|
| **RC1** Trust events bypass `AnalyticsGenerator` — set via `TrustCalculator.record_trust_event` | T-06 must verify ALL `AnalyticsEvent.objects.create()` / `bulk_create()` calls in the seed pipeline set `source=AdSource.SEED`. If `record_trust_event` is the only path, it must be updated too |
| **RC2** `_clean()` deletion order — if `User` deleted before `Ad`, FK CASCADE may not fire correctly | Deletion order preserved: DailyAdMetrics → AnalyticsEvent → AdImage → Ad → User → PopularSearch. Children before parents |
| **RC3** Transaction lock contention on `daily_ad_metrics` unique constraint `(ad, date)` | In dev/test single-writer environment, no concurrent writers; if contention occurs, fall back to savepoints |
| **RC4** Windows `docker compose rm` not available in older Compose versions | Docker Compose v2 is required by this project (verified in Dockerfile); `rm -sf` is supported in all v2 releases |
| **RC5** Migration dependency chain across 3 apps — `makemigrations` might produce unexpected ordering | Each migration depends only on its own app's previous migration (no cross-app deps); verified by researcher findings |

---

## Verification Approach

### Automated tests (Docker-based, never local `uv run pytest`)

```powershell
# 1. Migration check — no schema drift
docker compose --project-name mko-bazuna-dev -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run python src/backend/manage.py makemigrations --check --dry-run

# 2. Seed idempotency + orphaned-user recovery (integration, seed marker)
docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm `
  -e PYTEST_OPTS="apps/seed/tests/test_seed.py -v" test

# 3. Lint
docker compose --project-name mko-bazuna-dev -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run ruff check src/backend/apps/seed/ src/backend/apps/users/ src/backend/apps/analytics/ src/backend/apps/search/

# 4. Typecheck
docker compose --project-name mko-bazuna-dev -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run basedpyright src/backend/apps/seed/ src/backend/apps/users/ src/backend/apps/analytics/ src/backend/apps/search/
```

### Manual workflow check (Windows)

```powershell
.\Makefile.ps1 build    # rebuild image
.\Makefile.ps1 up       # should rm -sf one-shots, then seed re-runs successfully
# Verify: web on :8000 shows seed ads; no IntegrityError in logs
docker compose logs seed  # should show "Seed completed" without errors
```

---

## Rollout Sequencing Notes

1. **T-01 through T-04 (schema)** are the foundation — all other tasks depend on
   the `source` field existing in the model definitions and migrations.

2. **T-05, T-06, T-07 (generators)** set the `source` field on newly-created
   seed records. These can run in parallel with each other and with T-04
   (migration generation), since they only require the model field to exist
   in Python — not the migration to be applied.

3. **T-08 (_clean rewrite)** is the critical pivot — it switches from
   reverse-FK identification to direct `source` filtering. It must NOT be
   applied until ALL generators (T-05, T-06, T-07) are setting `source`,
   otherwise `_clean()` would fail to find and delete seed records.

4. **T-09 (transaction wrap)** is in the same file as T-08 but a separate
   method. Must follow T-08 since both modify `seed_service.py`.

5. **T-10 and T-11 (Makefile)** are operationally independent — they can
   be developed in parallel with Phase 1–4. However, they only become
   effective after T-08 is complete (the `up` command forces a seed re-run,
   which will fail if the orphaned-user bug hasn't been fixed yet).

6. **T-12 (test)** validates the full fix chain (T-04 + T-05 + T-08). Must
   be run last before T-13.

7. **T-13 (verification)** is the final gate — all tasks must pass before
   implementation is considered complete.
