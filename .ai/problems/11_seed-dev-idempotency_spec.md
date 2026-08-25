# Problem Spec 11: Non-Idempotent Seed and Migration on Repeated `docker compose up`

**Spec ID:** 11  
**Created:** 2026-08-25  
**Status:** Approved — all PO decisions collected (§7)  
**PO decisions:** Q1=A, Q2=A+C, Q3=A, Q4=A, Q5=A  
**Spec index:** [docs/01-spec/spec-index.md](docs/01-spec/spec-index.md)  

---

## 1. Problem Statement

When a developer (or CI agent) runs `docker compose up` after a seed-container re-run (triggered by image rebuild, `--force-recreate`, or `make down` + `up`), the `seed` one-shot service crashes with an `IntegrityError` on the `telegram_id` unique constraint. The root cause is that orphaned seed `User` records from a previously interrupted seed run survive `_clean()`, because `_clean()` can only identify seed users via their seed `Ad` rows — and those ads may have been deleted while the users remained.

Additionally, the seed generation phase (steps 4–13 of the seed lifecycle) is not wrapped in a database transaction, so any failure mid-generation leaves the database in a half-seeded state that the subsequent `_clean()` cannot fully reverse.

**User-visible symptom:** `make up` (or `make seed`) exits non-zero with:
```
psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint "users_telegram_id_key"
DETAIL: Key (telegram_id)=(10000) already exists.
```

---

## 2. Confirmed Facts

### 2.1 Docker Compose One-Shot Lifecycle

Two project variants use one-shot services: `migrate`, `load_catalog`, `create_admin`, and `seed`.

| Trigger | One-shot re-runs? | Notes |
|---|---|---|
| `make up` (image unchanged, containers exist) | ❌ No | Containers stay in `exited` state |
| `make build` then `make up` | ✅ Yes | Image change causes container recreation |
| `make up --force-recreate` | ✅ Yes | Forces recreation |
| `make down` then `make up` | ✅ Yes | Containers removed, named volumes persist |
| `make reset` then `make up` | ✅ Yes | Containers + volumes removed |
| `make seed` (`run --rm seed`) | ✅ Yes | Always new container |
| `make up` after code changes via bind-mount (no `make build`) | ❌ No | One-shot containers unchanged |

- **Dev project name:** `mko-bazuna-dev` — `docker-compose.dev.override.yml` uses `profiles: [!reset, []]` on `seed` to auto-run it on `up`.
- **Test project name:** `mko-bazuna-test` — seed is NOT auto-run on `up`; test DB is managed via the test Compose service with `--reuse-db`.
- `--force-recreate` and `--no-deps` combinations (documented in the Makefile) **do not** help with idempotency — they force re-runs but the orphaned-user bug still crashes on re-seed.
- `--renew-anon-volumes` is irrelevant — the project uses named volumes only (`postgres_data`, `media_volume`).
- `make up` does **not** pass `--wait`; failures of one-shot services are silent.

### 2.2 Seed Architecture

| Component | File | Behavior |
|---|---|---|
| `SeedService` | `seed/services/seed_service.py` | Orchestrator: acquires advisory lock (ID 110), calls `_clean()`, runs generators sequentially |
| `UserGenerator` | `seed/generators/users.py` | Creates `User` with `telegram_id` from `itertools.count(start=10_000)` — **no DB lookup** |
| `AdGenerator` | `seed/generators/ads.py` | Creates `Ad` with `source=AdSource.SEED` |
| Seed command | `seed/management/commands/seed.py` | CLI entry with `--force` flag |
| Seed entrypoint | `docker/entrypoint-seed.sh` | Always passes `--force`; runs `seed --force --users 10 --ads 600` |

### 2.3 Seed Lifecycle Flow

```
SeedService.run()
  1. advisory_lock(110, session=True)          ← prevents concurrent runs, lock ID = AdvisoryLockId.SEED
  2. self._clean()                              ← deletes old seed data (in transaction.atomic)
  3. _load_category_fixtures()                  ← load_catalog (idempotent, update_or_create)
  4. _load_city_fixtures()                      ← bulk_create(ignore_conflicts=True)
  5. UserGenerator.generate() + bulk_create     ← NO ignore_conflicts, NO transaction
  6. AdGenerator.generate() + bulk_create       ← NO ignore_conflicts, NO transaction
  7. ad.features.set(sample)                     ← clears + sets AdFeature M2M
  8. ImageGenerator.generate() + bulk_create    ← NO ignore_conflicts, NO transaction
  9. _backfill_image_hashes()                   ← UPDATE AdImage
 10. _seed_popular_searches()                   ← update_or_create (not cleaned by _clean)
 11. AnalyticsGenerator.generate_events() + bulk_create  ← NO ignore_conflicts
 12. AnalyticsGenerator.generate_daily_metrics() + bulk_create(ignore_conflicts=True)
 13. TrustCalculator.calculate_and_save()       ← get_or_create per-user; emits trust AnalyticsEvent (ad=NULL)
```

### 2.4 Key Database Constraints

| Table | Identifying Column(s) | Unique Constraint |
|---|---|---|
| `users` | `telegram_id` | `unique=True` |
| `users` | `chat_id` | `unique=True` |
| `ads` | `source` | none (identifies seed ads) |
| `analytics_events` | (none) | none; `ad` → SET_NULL, `user` → SET_NULL |
| `daily_ad_metrics` | `(ad, date)` | `UniqueConstraint` |

### 2.5 `_clean()` Method (Current State)

```python
# seed_service.py:198-243
def _clean(self) -> None:
    # Computed BEFORE the transaction block — sees pre-clean state
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

    # Media cleanup OUTSIDE transaction
    if os.path.exists(seed_dir):
        shutil.rmtree(seed_dir, ignore_errors=True)
```

---

## 3. Root Cause Analysis

### 3.1 Primary Root Cause: Indirect Seed-User Identification (CRITICAL)

`_clean()` identifies seed `User` records solely through the reverse foreign key `User.objects.filter(ads__source=AdSource.SEED)`. This means: **a seed user is only visible to cleanup if it currently has at least one `Ad` with `source=AdSource.SEED`.**

When the seed generation phase crashes *after* `UserGenerator.bulk_create()` but *before* `AdGenerator.bulk_create()` completes (steps 5–6), the following state is reached:

1. `_clean()` already ran and deleted all old seed ads + users. ✅
2. `UserGenerator` created new seed users (telegram_id 10000–10009). ✅
3. `AdGenerator` crashed after creating 0 ads. ❌
4. Process exits. Advisory lock released.
5. Users 10000–10009 persist in the DB **with zero seed ads**.

On the next re-seed:
1. `_clean()` queries `User.objects.filter(ads__source=AdSource.SEED)` → returns **zero users** (no seed ads exist).
2. `seed_user_ids = []` → no users deleted.
3. Orphaned users 10000–10009 persist.
4. `UserGenerator` calls `bulk_create()` with `telegram_id=10000` → **`IntegrityError`**.

### 3.2 Secondary Root Cause: Generation Phase Outside Transaction (CRITICAL)

`Transaction.atomic()` wraps only the `_clean()` deletion phase (lines 205–231). The generation phase (steps 5–13, lines 209–221) runs in autocommit mode. There is no rollback boundary around the creation steps, so any mid-generation crash leaves partially-created seed data that `_clean()` cannot fully identify or remove (due to the orphan-user bug in §3.1).

### 3.3 Compounding Factor: Generation Phase Complexity

The generation phase has **9 sequential steps** (steps 4–12 above), each performing `bulk_create` of 10 users, 600 ads, 180–240 images, 200+ analytics events, and trust-score calculations. Any timeout, OOM, or signal interruption at any step leaves the DB in a state visible only through the reverse-FK path — which is exactly what breaks `_clean()`.

---

## 4. Security & Data-Integrity Assessment

| Risk | Level | Impact | Mitigated by current code? |
|---|---|---|---|
| `IntegrityError` crash on re-seed after interruption | HIGH | `make up` / `make seed` fails; developer productivity blocked | ❌ No |
| Stale seed users accumulate in DB across failed runs | MEDIUM | DB bloat; potential `chat_id` collision on future runs | ❌ No |
| Trust events (`ad=NULL`) never cleaned | HIGH | Orphaned `AnalyticsEvent` rows accumulate | ❌ No |
| `PopularSearch` never cleaned | LOW | Minor DB bloat | ❌ No |
| Half-seeded state visible to web/bot processes | MEDIUM | Web process may serve incomplete seed data if it starts before seed completes | ❌ No — web only depends on DB, not seed success |

---

## 5. Confirmed Requirements

| Req ID | Requirement | Source |
|---|---|---|
| REQ-11.1 | Repeated `docker compose up` (or `make seed`) must succeed after a previous interrupted seed run — no `IntegrityError`. | Core request |
| REQ-11.2 | When re-seed runs, the database must end in the same state as a fresh `make reset && make up` — i.e., complete overwrite of seed data, no stale accumulation. | User preference: "second option is preferred for dev and test" |
| REQ-11.3 | If the seed generation phase crashes mid-way, the database must not retain orphaned seed users invisible to `_clean()`. | Implicit in Req 11.1 |
| REQ-11.4 | The dev workflow (`make up`) must either (a) guarantee fresh seed data on every invocation by re-running one-shot services, or (b) be documented with a clear manual step to force re-runs. | Operational requirement |

---

## 6. Conceptual Tasks

### Task 1: Make Seed-User Identification Direct (CRITICAL — Gap 2.1)

**Problem:** `_clean()` identifies seed users via `User.objects.filter(ads__source=AdSource.SEED)`.

**Option A (Recommended):** Add a `source` field to the `User` model (mirroring `Ad.source`), set it to `AdSource.SEED` by `UserGenerator`, and change `_clean()` to:
```python
User.objects.filter(source=AdSource.SEED).delete()
```
Requires a schema migration. This is the most robust approach — it decouples user identification from ad existence.

**Option B (Code-only, no migration):** Make `UserGenerator` query `Max("telegram_id")` and start the counter above the existing maximum. Add `ignore_conflicts=True` to `bulk_create` as a safety net. Does not solve orphaned-user accumulation, only prevents the crash.

### Task 2: Wrap Generation Phase in Transaction (CRITICAL — Gap 2.2)

**Problem:** Steps 4–13 of `SeedService.run()` run in autocommit.

**Option A (Recommended for atomicity):** Wrap the entire generation phase (post-`_clean()`) in a single `transaction.atomic()` block. On crash, the transaction rolls back and the DB is left in the clean post-`_clean()` state (no seed data).

**Concern:** A long-running transaction holding locks on 10 users + 600 ads + 180+ images may block or conflict with concurrent processes. Must evaluate lock duration vs. isolation benefit.

**Option B (Per-step transactions):** Wrap each generation step in its own `transaction.atomic()` savepoint. Allows partial completion but reduces the window of vulnerability. More complex.

**Option C (Status-based):** Add a `seed_run_id` UUID column to seed tables; `_clean()` filters by the latest `seed_run_id`. Avoids transaction duration issues but requires schema changes on multiple tables.

### Task 3: Clean Trust Events with `ad=NULL` (HIGH — Gap 3.1)

**Problem:** `AnalyticsEvent.objects.filter(ad__source=AdSource.SEED)` misses trust-score events where `ad=NULL` (emitted by `TrustCalculator.record_trust_event`).

**Fix:** Add a `source` or `is_seed` field to `AnalyticsEvent`, OR add a separate cleanup path in `_clean()`:
```python
AnalyticsEvent.objects.filter(user__source=AdSource.SEED, ad__isnull=True, name__in=TRUST_EVENT_NAMES).delete()
```
(Requires identifying which event names are seed-generated trust events.)

### Task 4: Clean `PopularSearch` Records (MEDIUM — Gap 4.1)

**Problem:** `_seed_popular_searches()` uses `update_or_create` but `_clean()` never deletes `PopularSearch` records.

**Fix:** Add `PopularSearch.objects.filter(...)` cleanup to `_clean()`. Identify a marker (e.g., a `is_seed` flag or a normalized-query prefix used by the seed generator).

### Task 5: Clean `DailyAdMetrics` Stale Rows (LOW — Gap 5.1)

**Problem:** `generate_daily_metrics()` uses `bulk_create(ignore_conflicts=True)`, so on re-seed it silently skips existing rows instead of updating them. If seed logic changed (e.g., different date range), stale metrics persist.

**Fix:** Delete seed `DailyAdMetrics` before regenerating (already done in `_clean()` — this is a minor gap only if `_clean()` fails to catch them). Verify the `ad__source=AdSource.SEED` filter covers all regenerated metrics.

### Task 6: Operational Workflow Guarantee (Gap 6.1)

**Problem:** `make up` does not guarantee one-shot re-runs when the image hasn't changed.

**Decision (APPROVED Q3=A):** Option A — Add `docker compose rm -sf` for one-shot services (`migrate`, `load_catalog`, `create_admin`, `seed`) before `up`, in both `Makefile` and `Makefile.ps1`. See Section 8.4 for exact code.

**Option B:** Add `--wait` to `make up` so one-shot failures surface immediately (visibility, not prevention).

**Option C:** Document that `make build` (or `make reset`) is required before `make up` when fresh seed data is needed. No code/workflow change.

### Task 7: Add `--wait` to `make up` (Visibility)

Pass `--wait` to `docker compose up` in the Makefile so that if `seed` or `migrate` exits non-zero, `make up` fails immediately with a clear error instead of silently proceeding with stale data.

---

## 7. PO Decisions (Collected)

### Q1. Re-seed Scope: Full Overwrite (Req 11.2)

**Question:** When seed re-runs, should the database undergo a complete overwrite (delete all seed data, regenerate from scratch) — the current `--force` strategy — or should it become incremental/upsert-style (only add new records, skip existing)?

**Context:** The user has already indicated preference for "complete overwrite." This question confirms the scope and asks whether `make up` should *automatically* trigger a full re-seed, or whether re-seed only happens when explicitly invoked (`make seed`).

| Option | Behavior | Recommended |
|---|---|---|
| A | `make up` always re-seeds (removes one-shot containers first to force re-run); `make seed` also full-overwrites | ✅ **Recommended** — matches "second option preferred for dev and test" |
| B | `make up` re-runs seed only if image/config changed; otherwise skips (stale data acceptable in dev) | Not recommended — causes confusion |
| C | `make up` skips seed entirely; developers must run `make seed --force` manually | Not recommended — friction |

**Decision:** **Option A** — `make up` in dev always forces seed re-run + full overwrite. ✅ **APPROVED**.

---

### Q2. Recovery from Interrupted Seed (Req 11.3)

**Question:** When the seed process crashes mid-generation (e.g., after creating users but before creating ads), what should happen on the next `make up` or `make seed`?

| Option | Behavior | Recommended |
|---|---|---|
| A | System auto-recovers: `_clean()` identifies and deletes orphaned seed users even if they have no ads; re-seed proceeds cleanly | ✅ **Recommended** — most robust; requires `User` model `source` field |
| B | System does NOT auto-recover; developer must run `make reset` (full volume wipe) to fix | Not recommended — high friction, destroys other dev data |
| C | System prevents the crash entirely by wrapping generation in a transaction that rolls back on failure | Recommended as defense-in-depth alongside Option A |

**Decision:** **Option A** (add `source` field to `User`) + **Option C** (wrap generation in `transaction.atomic()`). ✅ **APPROVED**.

---

### Q3. Dev Workflow Guarantee (Req 11.4)

**Question:** Should `make up` (dev) guarantee fresh seed data on every invocation, regardless of image changes or container state?

| Option | Behavior | Recommended |
|---|---|---|
| A | `make up` runs `docker compose rm -sf` on one-shot services before `up`, forcing re-run of `migrate`, `load_catalog`, `create_admin`, `seed` | ✅ **Recommended** |
| B | `make up` passes `--force-recreate` on all services (rebuilds everything including persistent web/bot) | Too expensive — rebuilds persistent containers |
| C | `make up` only re-runs one-shots when image changes (current behavior); document `make reset` for fresh data | Not recommended — silent staleness |

**Decision:** **Option A** — add `docker compose rm -sf` for one-shot services before `up` in both `Makefile` and `Makefile.ps1`. ✅ **APPROVED**.

---

### Q4. Transaction Scope for Seed Generation (Gap 2.2)

**Question:** Should the seed generation phase (600 ads, 180 images, 200+ analytics events) be wrapped in a single `transaction.atomic()`, or should each step use its own savepoint?

| Option | Behavior | Recommended |
|---|---|---|
| A | Single transaction around entire generation phase — crash = full rollback, DB returns to post-`_clean()` state | ✅ **Recommended** if lock duration is acceptable |
| B | Per-step savepoints — partial data survives, but each step is atomic | Less clean — partial seed data visible |
| C | No transaction (current behavior) — rely solely on `_clean()` being correct | Not recommended — leaves the DB in an unpredictable state |

**Decision:** **Option A** (single transaction). ✅ **APPROVED**.

**Performance note:** Lock duration must be evaluated during implementation. If the single-transaction approach causes lock contention or exceeds acceptable hold-time thresholds, fall back to **Option B** (per-step savepoints) as documented in Task 2.

---

### Q5. Model-Level `source` Field for Non-User Tables (Tasks 3, 4, 5)

**Question:** Beyond `User`, should a `source` marker field be added to `AnalyticsEvent` and `PopularSearch` so `_clean()` can identify seed-generated rows directly (without relying on FK traversal through `Ad`)?

| Option | Behavior | Recommended |
|---|---|---|
| A | Add `source` field to `User`, `AnalyticsEvent`, and `PopularSearch` — full architectural fix | ✅ **Recommended** — most robust |
| B | Add `source` only to `User` — fixes the crash; leave event/search cleanup as separate hardcoded filters | Lower effort but incomplete |
| C | No new fields — fix only `UserGenerator` counter + `ignore_conflicts` (Option B from Task 1) | Minimal fix, doesn't address orphaned accumulation |

**Decision:** **Option A** — add `source` field to `User`, `AnalyticsEvent`, and `PopularSearch`. ✅ **APPROVED**.

---

## 8. Affected Assets

### 8.1 Source Files

| File | Change |
|---|---|
| `src/backend/apps/seed/services/seed_service.py` | Rewrite `_clean()` to use direct `source` filters; wrap generation in `transaction.atomic()` |
| `src/backend/apps/seed/generators/users.py` | Set `source=AdSource.SEED` on generated `User` instances; remove hardcoded `10_000` counter (or use `Max` fallback) |
| `src/backend/apps/core/models.py` (or `users/models.py`) | Add `source` field to `User` model (if Q2=Option A accepted) |
| `src/backend/apps/core/enums.py` | `AdvisoryLockId.SEED = 110` already exists (verified) |
| `Makefile` | Update `up` target: add `docker compose rm -sf` for one-shot services before `up`; add `--wait` |
| `Makefile.ps1` | **Windows-specific:** Update `Invoke-Up` function (lines 75-82): add `docker compose rm -sf migrate load_catalog create_admin seed` call before `up -d`. PS 5.1-compatible syntax. `up` does NOT use `--wait` (Windows Docker Compose may not support `--wait` in all versions — use `docker compose up -d --wait` only if Compose v2.20+). |

### 8.2 Migrations (New)

| Migration | Table | Change |
|---|---|---|
| `users` | `User` | Add `source` field (CharField, nullable, indexed) |
| `analytics` | `AnalyticsEvent` | Add `source` field (CharField, nullable, indexed) |
| `search` | `PopularSearch` | Add `source` field (CharField, nullable, indexed) |

### 8.3 Test Files

| File | Change |
|---|---|
| `src/backend/apps/seed/tests/test_seed.py` | Extend `test_seed_idempotent` to simulate orphaned users (crash after UserGenerator, before AdGenerator); assert re-seed succeeds |
| `src/backend/conftest.py` | May need `seed` marker for new tests |

### 8.4 Docker / Compose Files

| File | Change |
|---|---|
| `docker-compose.dev.override.yml` | Review `profiles: [!reset, []]` on seed (currently makes seed auto-run, but only once) |
| `docker/entrypoint-seed.sh` | No change needed (already passes `--force`) |

### 8.5 Makefile / Makefile.ps1 (Windows) — Exact Changes

**`Makefile` (`up` target, current line 77-78):**

```makefile
up:
	docker compose $(COMPOSE_FILES) rm -sf migrate load_catalog create_admin seed
	docker compose $(COMPOSE_FILES) up -d
```

**`Makefile.ps1` (`Invoke-Up` function, current lines 75-82):**

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
- `docker compose rm -sf` is supported in Docker Compose v2 on Windows — no special syntax needed.
- `$env:COMPOSE_PROJECT_NAME` assignment pattern (already used throughout `Makefile.ps1`) is PS 5.1-compatible.
- `--wait` flag is NOT added to the `up` command in `Makefile.ps1` — Windows Docker Compose versions vary; `--wait` requires Compose v2.20+. If available, `docker compose up -d --wait` can be added for visibility (Task 7).

---

## 9. Research Summary

### Source 1: `.ai/research/seed-idempotency-audit.md`

Full audit of the seed module. Findings:

| ID | Gap | Severity |
|---|---|---|
| **2.1** | Orphaned seed users not identified by `_clean()` (reverse-FK only) | 🔴 CRITICAL |
| **2.2** | Generation phase not wrapped in `transaction.atomic()` | 🔴 CRITICAL |
| **3.1** | `AnalyticsEvent` with `ad=NULL` (trust events) never cleaned by `_clean()` | 🟠 HIGH |
| **4.1** | `PopularSearch` records never cleaned | 🟡 MEDIUM |
| **5.1** | `DailyAdMetrics` uses `ignore_conflicts=True` — stale rows persist if seed logic changes | 🟢 LOW |
| **6.1** | No `--wait` on `make up` — one-shot failures are silent | 🟡 MEDIUM |

### Source 2: `.ai/research/docker-one-shot-lifecycle-analysis.md`

Full Docker Compose one-shot service lifecycle analysis. Key conclusions:

1. `docker compose up` does **not** re-run exited one-shot containers unless the image/config changes, or `--force-recreate` / `docker compose rm` is used.
2. `make build --no-cache` is the primary mechanism by which one-shot services re-run in the agent workflow (image ID changes → container recreation).
3. `docker compose down` (without `-v`) removes containers but preserves named volumes; `down -v` (`make reset`) destroys volumes entirely.
4. `profiles: !reset []` on `seed` in dev override removes the profile gate, but does **not** override Compose's "container already exists" behavior.
5. `depends_on: condition: service_completed_successfully` is permanently satisfied by a previous successful exit — **does not** force re-runs.
6. `--wait` provides visibility (exits non-zero if a one-shot fails) but is not currently used by `make up`.
7. `--renew-anon-volumes` is ineffective — the project uses named volumes exclusively.

---

## 10. Recommendations (Summary)

| Priority | Action | Spec Section |
|---|---|---|
| 🔴 P0 | Add `source` field to `User` model; rewrite `_clean()` to filter by `source` directly | Task 1, Q2 |
| 🔴 P0 | Wrap seed generation phase in `transaction.atomic()` | Task 2, Q4 |
| 🟠 P1 | Clean trust events (`ad=NULL`) and `PopularSearch` records in `_clean()` | Tasks 3, 4, Q5 |
| 🟡 P2 | Add `docker compose rm -sf` for one-shot services before `make up` | Task 6, Q3 |
| 🟡 P2 | Add `--wait` to `make up` for failure visibility | Task 7, Gap 6.1 |
| 🟢 P3 | Extend `test_seed_idempotent` with orphaned-user simulation | §8.3 |

*Status: PO decisions **APPROVED** (Q1=A, Q2=A+C, Q3=A, Q4=A, Q5=A). Implementation can begin.*  
