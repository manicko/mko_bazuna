# Seed Module Idempotency Audit — Mko Bazuna

**Date:** 2026-08-25  
**Scope:** `src/backend/apps/seed/`  
**Auditor:** Kilo (automated research)  
**Confidence:** HIGH — all findings derived from direct source-code inspection.

---

## Executive Summary

The seed module uses a **delete-and-recreate** strategy (via `SeedService._clean()`) rather than upsert or `get_or_create`. This approach is fundamentally non-idempotent by design: correctness depends entirely on `_clean()` deleting **every** seed-generated record on every run. The audit identified **two critical gaps**, **one high-severity gap**, and **three medium/low gaps** that cause either hard crashes (`IntegrityError`) or silent data accumulation on re-seed.

The most severe issue is that **seed users are identified solely through their seed ads** (`User.objects.filter(ads__source=AdSource.SEED)`). If the seed process crashes after creating users but before creating ads (or after `_clean()` deletes ads but before regeneration completes), those users become **orphaned** — invisible to `_clean()` on the next run. When `UserGenerator` attempts `bulk_create` with `telegram_id` 10000+, it collides with existing orphaned users and crashes.

A secondary systemic issue is that **`SeedService.run()` does not wrap the generation phase in a transaction**, so partial failures leave the database in a half-seeded state that `_clean()` cannot fully reverse.

---

## Architecture Overview

### Components

| Component | File | Responsibility |
|---|---|---|
| `SeedService` | `seed/services/seed_service.py` | Orchestrator: loads config, calls `_clean()`, runs all generators in sequence |
| `UserGenerator` | `seed/generators/users.py` | Creates fake `User` instances with `telegram_id` starting at 10000 |
| `AdGenerator` | `seed/generators/ads.py` | Creates `Ad` instances with `source=AdSource.SEED` |
| `ImageGenerator` | `seed/generators/images.py` | Writes seed photos to `media/seed/`, creates `AdImage` records |
| `AnalyticsGenerator` | `seed/generators/analytics.py` | Creates `AnalyticsEvent` and `DailyAdMetrics` records |
| `TrustCalculator` | `trust/services/trust_calculator.py` | Computes and persists `SellerTrustScore` per user; emits trust `AnalyticsEvent` |
| Management command | `seed/management/commands/seed.py` | CLI entry point with `--force` flag |
| Docker entrypoint | `docker/entrypoint-seed.sh` | Always passes `--force`; runs `seed --force --users 10 --ads 600` |

### Seed Lifecycle Flow

```
SeedService.run()
  1. advisory_lock(110, session=True)   ← prevents concurrent runs
  2. self._clean()                       ← deletes old seed data (in transaction.atomic)
  3. _load_category_fixtures()           ← load_catalog (idempotent, update_or_create)
  4. _load_city_fixtures()               ← bulk_create(ignore_conflicts=True) — idempotent
  5. UserGenerator.generate() → bulk_create  ← NO ignore_conflicts, NO transaction
  6. AdGenerator.generate() → bulk_create   ← NO ignore_conflicts, NO transaction
  7. ad.features.set(sample)               ← clears + sets AdFeature M2M
  8. ImageGenerator.generate() → bulk_create ← NO ignore_conflicts, NO transaction
  9. _backfill_image_hashes()             ← UPDATE AdImage
 10. _seed_popular_searches()             ← update_or_create (not cleaned by _clean)
 11. AnalyticsGenerator.generate_events() → bulk_create  ← NO ignore_conflicts
 12. AnalyticsGenerator.generate_daily_metrics() → bulk_create(ignore_conflicts=True)
 13. TrustCalculator.calculate_and_save()  ← get_or_create (idempotent per-user)
     └─ record_trust_event() → AnalyticsEvent.objects.create()  ← creates event with ad=NULL
```

### Key Database Constraints

| Table | Identifying Column(s) | Unique Constraint | `on_delete` on FKs |
|---|---|---|---|
| `users` | `telegram_id` | `unique=True` | — |
| `users` | `chat_id` | `unique=True` | — |
| `ads` | `source` | none (identifies seed ads) | `user` → CASCADE |
| `ad_images` | (none) | none | `ad` → CASCADE |
| `ad_features` | (through) | `(ad, feature)` | `ad` → CASCADE |
| `analytics_events` | (none) | none | `ad` → SET_NULL, `user` → SET_NULL |
| `daily_ad_metrics` | `(ad, date)` | `UniqueConstraint` | `ad` → CASCADE |
| `popular_searches` | `query_normalized` | none (index only) | — |
| `seller_trust_scores` | `user` (OneToOne) | implicit unique | `user` → CASCADE |

---

## 1. SeedService._clean() Method Analysis

### 1.1 Seed Data Identification via `AdSource.SEED`

`_clean()` identifies seed data by joining through the `Ad` table:
```python
# seed_service.py:205-209
seed_user_ids = list(
    User.objects.filter(ads__source=AdSource.SEED)
    .values_list("id", flat=True)
    .distinct()
)
```

Every subsequent deletion uses `ad__source=AdSource.SEED` or `source=AdSource.SEED`:
- `DailyAdMetrics.objects.filter(ad__source=AdSource.SEED).delete()`  (line 214-216)
- `AnalyticsEvent.objects.filter(ad__source=AdSource.SEED).delete()`   (line 219-221)
- `AdImage.objects.filter(ad__source=AdSource.SEED).delete()`          (line 224)
- `Ad.objects.filter(source=AdSource.SEED).delete()`                   (line 227)
- `User.objects.filter(id__in=seed_user_ids).delete()`                 (line 231)

**Assessment:** This is the correct approach — seed data is identified by the `source` field on `Ad`, and everything else is reached through FK relationships. However, it is **indirect and brittle** (see Gaps 2.1 and 3.1).

### 1.2 Completeness of Record Capture

`_clean()` deletes the following seed-generated records:

| Record Type | Cleaned? | How |
|---|---|---|
| `DailyAdMetrics` | ✅ Yes | `filter(ad__source=AdSource.SEED)` |
| `AnalyticsEvent` (ad-linked) | ✅ Yes | `filter(ad__source=AdSource.SEED)` |
| `AnalyticsEvent` (trust events, `ad=NULL`) | ❌ **NO** | Not caught by `ad__source` filter (see Gap 3.1) |
| `AdImage` | ✅ Yes | `filter(ad__source=AdSource.SEED)` |
| `AdFeature` (through model) | ✅ Yes (via CASCADE) | Cascaded when `Ad` is deleted |
| `Ad` | ✅ Yes | `filter(source=AdSource.SEED)` |
| `User` (seed users) | ⚠️ Conditional | Only users with seed ads (see Gap 2.1) |
| `SellerTrustScore` | ⚠️ Conditional | Cascaded from User deletion (see Gap 2.1) |
| `SellerVerification` | ⚠️ Conditional | Cascaded from User deletion (see Gap 2.1) |
| `PopularSearch` | ❌ **NO** | Explicitly not deleted (see Gap 4.1) |
| Seed media files | ✅ Yes | `shutil.rmtree(seed_dir, ignore_errors=True)` |

### 1.3 Seed User Identification Query

```python
# seed_service.py:205-209
User.objects.filter(ads__source=AdSource.SEED)
```

This query finds users who have **at least one** ad with `source=AdSource.SEED`. It is complete **only when all seed users have at least one surviving seed ad** at the time `_clean()` runs.

**Critical timing detail:** `seed_user_ids` is computed **before** the `transaction.atomic()` block (line 205), so the query sees the pre-clean state. This is correct for the happy path — all seed ads still exist, so all seed users are found.

But if `_clean()` has already been partially executed (e.g., ads were deleted in a previous interrupted run), the seed users from that run have **no seed ads** and are invisible to this query.

### 1.4 Transactional Boundaries of `_clean()`

```python
# seed_service.py:198-243
def _clean(self) -> None:
    seed_user_ids = list(...)  # ← OUTSIDE transaction (pre-computed)

    with transaction.atomic():
        DailyAdMetrics.objects.filter(ad__source=AdSource.SEED).delete()
        AnalyticsEvent.objects.filter(ad__source=AdSource.SEED).delete()
        AdImage.objects.filter(ad__source=AdSource.SEED).delete()
        Ad.objects.filter(source=AdSource.SEED).delete()
        if seed_user_ids:
            User.objects.filter(id__in=seed_user_ids).delete()

    # ← Media cleanup OUTSIDE the transaction, AFTER commit
    if os.path.exists(seed_dir):
        shutil.rmtree(seed_dir, ignore_errors=True)
```

The DB deletion is inside `transaction.atomic()` (good — all-or-nothing for the DB). The media cleanup is outside (acceptable — filesystem operations cannot be transactional with PostgreSQL).

The deletion order (child tables first) is correct:
1. `DailyAdMetrics` (FK → Ad, CASCADE) — explicit delete before Ad
2. `AnalyticsEvent` (FK → Ad, SET_NULL) — explicit delete before Ad (critical: SET_NULL would orphan events)
3. `AdImage` (FK → Ad, CASCADE) — explicit delete before Ad
4. `Ad` — deleted, cascades to AdImage and AdFeature
5. `User` (identified by seed_user_ids) — deleted, cascades to SellerTrustScore/SellerVerification

**This order is correct.** The problem is not within `_clean()` — it's the gap between `_clean()` and the generation phase.

---

## 2. Critical Gaps

### GAP 2.1 — Orphaned Seed Users Are Not Cleaned (CRITICAL)

**Location:** `SeedService._clean()`, `seed_service.py:205-209`

**Code:**
```python
seed_user_ids = list(
    User.objects.filter(ads__source=AdSource.SEED)
    .values_list("id", flat=True)
    .distinct()
)
```

**Problem:** The seed user identification query relies on users **currently** having seed ads. If a previous seed run created users but crashed before completing ad creation (or after `_clean()` deleted old ads but before new ads were created), those users have no seed ads and are **invisible** to the query.

**Failure Mode:**

1. **First seed run** (normal): Creates 10 users (telegram_id 10000–10009), 600 ads. All users have seed ads. ✅
2. **Second seed run** (crash after `_clean()` but during user `bulk_create`):
   - `_clean()` runs: deletes all old seed ads and users. ✅
   - `UserGenerator.bulk_create()` creates users 10000–10009. ✅
   - `AdGenerator.bulk_create()` crashes (e.g., database timeout on 600 rows).
   - **Process exits with error.** Advisory lock (session-scoped) is released.
   - Users 10000–10009 persist in the DB **without any seed ads**.
3. **Third seed run** (re-seed attempt):
   - `_clean()` runs: `User.objects.filter(ads__source=AdSource.SEED)` finds **zero** users (no seed ads exist).
   - `seed_user_ids = []` → no users deleted.
   - Users 10000–10009 **persist as orphans**.
   - `UserGenerator.bulk_create()` tries to create users with telegram_id=10000, 10001, etc.
   - **`IntegrityError`** on `UniqueConstraint` for `telegram_id` (and `chat_id`).
   - Seed command crashes. Database left in pre-seed state.

**Does this currently cause errors?** **YES** — hard crash (`IntegrityError`) on re-seed after any crash during the generation phase. This is the highest-risk gap because the generation phase is large (8 steps, 600+ rows) and runs outside any transaction.

**Why the existing test doesn't catch it:** `test_seed_idempotent` (test_seed.py:513-521) only tests the happy path where `_clean()` fully succeeds and all users have seed ads. It uses `--users=2 --ads=5`, so every user has at least one ad. The orphaned-user scenario is never simulated.

**Root cause:** No direct marker on `User` to identify seed users independently of ads. The `AdSource.SEED` field on `Ad` is the only linkage.

---

### GAP 2.2 — Generation Phase Not Wrapped in Transaction (CRITICAL)

**Location:** `SeedService.run()`, `seed_service.py:86-184`

**Code:**
```python
# seed_service.py:86-184
with advisory_lock(AdvisoryLockId.SEED, session=True):
    ...
    self._clean()           # ← transaction.atomic() inside _clean only, commits and returns

    # ALL of the following runs in autocommit mode:
    user_instances = user_gen.generate(users)
    User.objects.bulk_create(user_instances, batch_size=5000)   # ← no transaction

    ad_instances = ad_gen.generate(ads)
    Ad.objects.bulk_create(ad_instances, batch_size=5000)       # ← no transaction

    ad_images = img_gen.generate()
    AdImage.objects.bulk_create(ad_images, batch_size=5000)     # ← no transaction

    events = analytics_gen.generate_events()
    AnalyticsEvent.objects.bulk_create(events, batch_size=5000)  # ← no transaction

    metrics = analytics_gen.generate_daily_metrics()
    DailyAdMetrics.objects.bulk_create(metrics, ...)            # ← no transaction

    for user in db_users:
        trust_calc.calculate_and_save(user)                      # ← no transaction
```

**Problem:** `_clean()` uses `transaction.atomic()` internally, but it commits and returns before any generation begins. All subsequent `bulk_create` calls run in autocommit mode. If any step fails mid-way, the database contains partially-seeded data that `_clean()` cannot fully reverse (due to Gap 2.1).

**Failure Mode:** Any exception during Steps 5–13 (user/ad/image/analytics/trust generation) leaves orphaned records. The next re-seed's `_clean()` cannot find orphaned users (Gap 2.1), leading to `IntegrityError` on `telegram_id`/`chat_id`.

**Does this currently cause errors?** **YES** — but only after a crash during generation followed by a re-seed attempt. In the normal (non-crashing) case, it has no effect.

**Root cause:** Missing `transaction.atomic()` wrapper around the entire generation phase (or at minimum, around user + ad creation together).

---

## 3. High-Severity Gaps

### GAP 3.1 — Trust Event AnalyticsEvents Are Never Cleaned (HIGH)

**Location:** `SeedService._clean()` (line 218-221) + `SeedService.run()` Step 7 (line 178-183)

**Code:**
```python
# _clean() (seed_service.py:218-221):
AnalyticsEvent.objects.filter(
    ad__source=AdSource.SEED
).delete()

# run() Step 7 (seed_service.py:178-183):
for user in db_users:
    trust_calc.calculate_and_save(user)
# → TrustCalculator.calculate_and_save() → record_trust_event()
# → AnalyticsEvent.objects.create(event_type=TRUST_LEVEL_UPDATED, user=seed_user, ad=None)
```

**Problem:** `_clean()` deletes `AnalyticsEvent` records by filtering on `ad__source=AdSource.SEED`. However, trust events created by `TrustCalculator.calculate_and_save()` → `record_trust_event()` (trust_analytics.py:92-107) have:
- `event_type = AnalyticsEventType.TRUST_LEVEL_UPDATED`
- `user = ad.user` (the seed seller)
- `ad = None`  (trust_analytics.py:99-102: `AnalyticsEvent.objects.create(event_type=event, user_id=user_id)` — no `ad` passed, defaults to NULL)

These events are **not caught** by `filter(ad__source=AdSource.SEED)` because their `ad` field is NULL. When `_clean()` later deletes seed users, the `AnalyticsEvent.user` FK uses `on_delete=models.SET_NULL` (analytics/models.py:28-35), so the event survives with `user=NULL, ad=NULL`.

**Failure Mode:**
1. Run 1: Creates 10 seed users → 10 `AnalyticsEvent` trust events (ad=NULL, user=seed_user).
2. Re-seed: `_clean()` runs:
   - Deletes events where `ad__source=AdSource.SEED` → the 10 trust events **survive** (ad=NULL).
   - Deletes seed users → trust events' `user` set to NULL (SET_NULL).
   - 10 orphaned events now exist: `ad=NULL, user=NULL, event_type=trust_level_updated`.
3. Run 2: Creates 10 new seed users → 10 MORE trust events.
4. Re-seed: Same pattern. Now **20** orphaned events.
5. Each re-seed adds 10 more orphaned events that never get cleaned.

**Does this currently cause errors?** **NO** — no crash. Silent accumulation. The `AnalyticsEvent` table grows by `N_users` orphaned rows per seed cycle. With default config (10 users), this adds 10 orphaned rows per cycle. Over weeks of nightly re-seeds in a dev environment, this accumulates.

**Severity:** HIGH — silent data pollution affecting analytics dashboards and queries that scan all `AnalyticsEvent` rows (e.g., `TrustCalculator._calculate_response_score` queries ALL `CONTACT_INITIATED` events, not just seed ones).

---

## 4. Medium / Low Gaps

### GAP 4.1 — PopularSearch Records Not Cleaned (MEDIUM)

**Location:** `SeedService._clean()` (deliberately omitted) + `SeedService._seed_popular_searches()` (seed_service.py:318-356)

**Code comment (line 323-325):**
```python
"""Uses ``update_or_create`` keyed on ``query_normalized`` (matching the
``increment_popular_search`` runtime service) for idempotency on re-seed
(``SeedService._clean`` does not remove PopularSearch rows)."""
```

**Problem:** `_clean()` does **not** delete any `PopularSearch` records. `_seed_popular_searches()` uses `update_or_create` keyed on `query_normalized`, which is idempotent for entries that already exist. However:

1. **Config-provided searches** (5 entries: "iphone", "car", "apartment", "sofa", "bike") — these are upserted idempotently via `update_or_create`. ✅
2. **Derived searches** (from seed ad titles) — these are derived from `Ad.objects.filter(source=AdSource.SEED)` title words. Since ad content is deterministic (seeded Faker with `faker_seed=42`), the derived words should be the same on every re-seed **if the same number of ads is generated**. But if the ad count changes (e.g., `--ads=30` vs `--ads=600`), different title word samples are drawn, and **old derived queries from previous runs persist**.

**Failure Mode:**
- Run 1 with `--ads=600`: Derives popular searches including word "велосипед" from ad title "Продам велосипед".
- Run 2 with `--ads=30`: No ads with "велосипед" in title. The derived search "велосипед" **persists** from Run 1.
- Result: `PopularSearch` table contains stale entries referencing ads that no longer exist.

**Additional risk:** `PopularSearch` has **no unique constraint** on `query_normalized` (only `db_index=True`), only an index (search/models.py:16). The `update_or_create` call uses `.filter(query_normalized=normalized).get()` internally. If somehow duplicate `query_normalized` values existed (e.g., from concurrent seeds bypassing the advisory lock, or from runtime `increment_popular_search` creating entries), `get()` would raise `MultipleObjectsReturned`. In practice, the advisory lock prevents concurrent seeds, so this is a theoretical concern.

**Does this currently cause errors?** **NO** — no crash. Stale `PopularSearch` entries appear in autocomplete suggestions on the website, referencing queries whose ads no longer exist.

**Severity:** MEDIUM — data staleness in autocomplete, user-visible but non-crashing.

---

### GAP 4.2 — DailyAdMetrics `ignore_conflicts` Masks Stale Data (LOW)

**Location:** `SeedService.run()`, `seed_service.py:170-174`

**Code:**
```python
# seed_service.py:169-174
if metrics:
    DailyAdMetrics.objects.bulk_create(
        metrics,
        batch_size=5000,
        ignore_conflicts=True,
    )
```

**Problem:** `DailyAdMetrics` has a `UniqueConstraint` on `(ad, date)` (analytics/models.py:96-101). Since `_clean()` deletes all seed-related metrics before regeneration, `ignore_conflicts=True` is a redundant safety net. However, if `_clean()` fails to delete some metrics (e.g., due to a crash between `_clean()` and regeneration, then recovery without full clean), `ignore_conflicts=True` would **silently skip** the conflicting rows, preserving stale `views_count` values instead of updating them with fresh seed data.

**Does this currently cause errors?** **NO** — no crash, but potential stale metric values if a previous run was interrupted mid-generation. In the normal flow, `_clean()` fully removes old metrics, so `ignore_conflicts` is a no-op.

**Severity:** LOW — only relevant in crash-recovery scenarios.

---

### GAP 4.3 — Image Generator Thumbnail Cache Check Is Dead Code in Normal Flow (LOW)

**Location:** `ImageGenerator._preprocess_one()`, `images.py:291-293`

**Code:**
```python
# images.py:291-293
thumb_small = os.path.join(seed_dir, f"{os.path.splitext(filename)[0]}-small.jpg")
if os.path.exists(thumb_small):
    return True  # Skip thumbnail generation entirely
```

**Problem:** `_preprocess_one()` checks if the small thumbnail file exists and short-circuits if it does. On a normal re-seed, `_clean()` does `shutil.rmtree(seed_dir)`, removing all files — so this cache check always fails (files don't exist). This means the cache check is effectively dead code in the normal flow.

However, if `_clean()`'s `shutil.rmtree(seed_dir, ignore_errors=True)` fails silently (the `ignore_errors=True` flag swallows permission errors), stale thumbnails could persist. The cache check would then skip regeneration. Since seed images use **deterministic filenames** (e.g., `seed/kvartiry_01.jpg`, not UUIDs), the thumbnails would be identical on re-seed anyway. So this is not a correctness issue.

**The real latent issue:** `_preprocess_one` writes the original image file with `open(original_path, "wb")` (line 287), which always overwrites. But it only checks `thumb_small` existence — it does not check `thumb_medium` or `thumb_large`. If `thumb_small` is missing but `thumb_medium`/`thumb_large` exist (e.g., from a partial failure), the method would call `thumbnail_service.generate_thumbnails()`, which uses `os.O_CREAT | os.O_EXCL` and would raise `FileExistsError` for the medium/large thumbnails. This `FileExistsError` IS caught (line 297-298), so it's handled — but the medium/large thumbnails would be stale if the source image changed (which doesn't happen for seed fixtures, since they're bundled).

**Does this currently cause errors?** **NO** — seed fixture images never change between runs. The cache check is a no-op in practice because `_clean()` removes the directory first.

**Severity:** LOW — latent code smell, not currently triggered.

---

### GAP 4.4 — Duplicate Log Statement in `_log_progress` (TRIVIAL)

**Location:** `SeedService._log_progress()`, `seed_service.py:292-295`

**Code:**
```python
def _log_progress(self, name: str, count: int, elapsed: float) -> None:
    """Log progress for a generation step."""
    logger.info("[seed] %s: %d rows in %.2fs", name, count, elapsed)
    logger.info("  %s: %d rows in %.2fs", name, count, elapsed)
```

**Problem:** The same progress message is logged twice — once with `[seed]` prefix and once with indentation. This doubles log output for every step.

**Does this currently cause errors?** **NO** — cosmetic issue. Wastes log volume.

**Severity:** TRIVIAL

---

## 5. Specific Failure Scenarios

### Scenario A — Seed Runs Twice Without `_clean()` Having Fully Completed

**Trigger:** Process is SIGKILL'd or crashes between `_clean()` commit and the end of generation.

**Timeline:**
```
T0: _clean() runs → commits deletion of all seed data (DB transaction commits)
T1: _clean() media cleanup (shutil.rmtree) → completes
T2: UserGenerator.bulk_create(10 users, telegram_id 10000-10009) → SUCCESS
T3: AdGenerator.generate(600) → starts
T4: CRASH (e.g., OOM, timeout, assertion error in faker)
```

**Result on re-seed:**
- `_clean()` runs: `seed_user_ids = []` (no seed ads exist — users 10000-10009 are orphaned)
- DB cleanup is a no-op
- Media cleanup removes any seed media from Step T2 (none generated yet)
- `UserGenerator.bulk_create` → **IntegrityError** on `telegram_id=10000` (already exists)

**Verdict:** Hard crash. **Currently causes errors.**

---

### Scenario B — Old Seed Users (Orphaned, No Ads) Persist → `bulk_create` Fails on Unique Constraint

**Trigger:** Same as Scenario A, or any crash after user creation but before/during ad creation.

**Mechanism:**
- `User.telegram_id` has `unique=True` (users/migrations/0001_initial.py:46)
- `User.chat_id` has `unique=True` (users/migrations/0001_initial.py:47)
- `UserGenerator` uses `itertools.count(start=10_000)` — always starts at 10000 (users.py:31)
- `User.objects.bulk_create(user_instances, batch_size=5000)` (seed_service.py:96) has NO `ignore_conflicts=True`

**Result:** `IntegrityError` on `telegram_id` (or `chat_id`) unique constraint. The seed command exits with a traceback.

**Verdict:** Hard crash. **Currently causes errors** in any crash-recovery scenario.

---

### Scenario C — Old AdImage Records Persist with Stale Thumbnail Paths

**Trigger:** `_clean()` deletes `AdImage` via `filter(ad__source=AdSource.SEED)`. If ads were already deleted (but AdImage still exists with a dangling FK), the `filter(ad__source=...)` join would miss them.

**Analysis:** `AdImage.ad` has `on_delete=models.CASCADE` (ads/models.py:504-509), so deleting an `Ad` automatically deletes its `AdImage` records. The explicit `AdImage.objects.filter(ad__source=AdSource.SEED).delete()` in `_clean()` is redundant but runs BEFORE `Ad.objects.filter(source=AdSource.SEED).delete()`. In the normal flow (deletion order: AdImage → Ad), all AdImage records are caught.

However, if a crash in a previous run deleted some Ads (via cascade from user deletion or manual cleanup) but left AdImage records with `ad=NULL` (SET_NULL doesn't apply here — it's CASCADE), this scenario can't occur. AdImage uses CASCADE, so deleting Ad always cascades to AdImage.

**Verdict:** Not a real gap in practice. **Currently causes no errors.** The deletion order in `_clean()` is correct (FK children before parents), and Django's cascade handles any edge cases.

---

### Scenario D — PopularSearch Accumulation (Acknowledged in Code)

**Trigger:** Multiple re-seeds with different `--ads` counts or different `faker_seed` values.

**Code comment** (seed_service.py:323-325):
```python
"""Uses ``update_or_create`` keyed on ``query_normalized`` (matching the
``increment_popular_search`` runtime service) for idempotency on re-seed
(``SeedService._clean`` does not remove PopularSearch rows)."""
```

**Analysis:** This is an acknowledged design decision — `_seed_popular_searches` is designed to be idempotent via `update_or_create`. Config-provided searches are always upserted. But derived searches (from ad titles) accumulate:

- If `--ads=600` generates ad titles containing word "велосипед", a `PopularSearch` entry for "велосипед" is created.
- If the next re-seed uses `--ads=30`, fewer title words are drawn. The "велосипед" entry persists from the previous run.
- The `hit_count` is overwritten by `update_or_create` if the query is derived again, but if it's not derived in the new run, the old entry (with old `hit_count`) survives.

**Verdict:** Silent data accumulation. **Currently causes no crashes**, but stale entries appear in autocomplete.

---

## 6. Comparison with Other One-Shot Services

### `create_admin` (create_admin_user.py)

| Property | `create_admin` | `seed` |
|---|---|---|
| Strategy | Check-then-create (`exists()` check) | Delete-all-then-recreate |
| Advisory lock | ✅ Yes (ID 101, session) | ✅ Yes (ID 110, session) |
| Idempotent? | ✅ Yes — skips if exists | ⚠️ Only if `_clean()` is complete |
| Transaction safety | N/A (single insert) | ❌ Generation not in transaction |
| Unique constraint collision | Handled by `exists()` check | ❌ Crash on `IntegrityError` |

### `load_catalog` (load_catalog.py → builder.load_catalog())

| Property | `load_catalog` | `seed` |
|---|---|---|
| Strategy | `update_or_create` by slug | Delete-all-then-recreate |
| Advisory lock | ✅ Yes (ID 100, session) | ✅ Yes (ID 110, session) |
| Idempotent? | ✅ Yes — upserts | ⚠️ Only if `_clean()` is complete |
| Transaction safety | ✅ Each `update_or_create` is atomic | ❌ Generation not in transaction |

### Key Difference

`create_admin` and `load_catalog` both use **upsert** strategies that are inherently idempotent — they don't need to delete old data first. `seed` uses **delete-and-recreate** because it regenerates the entire dataset (deterministic via Faker seed) and needs a clean slate. This strategy is correct for deterministic regeneration but requires `_clean()` to be **complete and reliable**.

---

## 7. SeedService.__init__ Re-entrancy

**Question:** Is `SeedService.__init__` re-entrant? Can it be called multiple times?

**Analysis:** Yes. `__init__` only calls `self._load_config()`, which reads a static JSON file into a dict. There is no shared mutable state, no file locks, no global variables. Each `SeedService()` instance is independent.

The `run()` method acquires an advisory lock (ID 110, session-scoped), which prevents concurrent execution. But `__init__` does not need the lock — it's just config loading.

**Verdict:** ✅ Re-entrant and safe to call multiple times.

---

## 8. The `--force` Flag in Docker

**Docker entrypoint** (`docker/entrypoint-seed.sh:32-34`):
```bash
exec uv run python src/backend/manage.py seed --force \
    --users "${SEED_USERS:-10}" \
    --ads "${SEED_ADS:-600}"
```

**Dev override** (`docker-compose.dev.override.yml:69-70`): The seed service is activated with `profiles: !reset []` (no profile gate), so it runs automatically on `docker compose up`.

**Prod** (`docker-compose.prod.yml:24-27`): Seed uses pre-built image, retains `profiles: ["seed"]` gate from base compose, so it only runs on explicit `--profile seed` demand.

**Verdict:** ✅ `--force` is always passed in Docker (both dev and prod). The confirmation prompt is never an issue in containerized deployments.

---

## 9. Summary of Findings

| # | Gap | Severity | Location | Causes Error? | Data Accumulates? |
|---|---|---|---|---|---|
| 2.1 | Orphaned seed users not found by `ads__source` query | **CRITICAL** | `seed_service.py:205-209` | ✅ Yes (`IntegrityError`) | N/A (crash blocks further runs) |
| 2.2 | Generation phase not wrapped in transaction | **CRITICAL** | `seed_service.py:86-184` | ✅ Yes (enables Gap 2.1) | N/A |
| 3.1 | Trust event AnalyticsEvents (ad=NULL) not cleaned | HIGH | `seed_service.py:218-221` | ❌ No | ✅ Yes (+N per user per cycle) |
| 4.1 | PopularSearch derived queries accumulate | MEDIUM | `seed_service.py:318-356` | ❌ No | ✅ Yes (stale autocomplete entries) |
| 4.2 | `ignore_conflicts=True` masks stale DailyAdMetrics | LOW | `seed_service.py:170-174` | ❌ No | ✅ Yes (rare, crash-recovery only) |
| 4.3 | Thumbnail cache check is dead code in normal flow | LOW | `images.py:291-293` | ❌ No | ❌ No |
| 4.4 | Duplicate log statement in `_log_progress` | TRIVIAL | `seed_service.py:292-295` | ❌ No | ❌ No |

### Current Error Impact Summary

| Scenario | Currently Causes Crash? | Type |
|---|---|---|
| Normal re-seed (happy path) | ❌ No | — |
| Crash during generation → re-seed | ✅ Yes | `IntegrityError` on `telegram_id`/`chat_id` |
| PopularSearch stale data | ❌ No | Silent |
| Trust event accumulation | ❌ No | Silent |
| SellerTrustScore orphans | ❌ No | Silent (subsumed by Gap 2.1) |

---

## 10. Recommendations

### Priority 1 — Fix Critical Crash: Wrap Generation in Transaction (GAP 2.2)

Wrap the entire generation phase in a single `transaction.atomic()` so that any failure rolls back all generated records. This prevents orphaned users from ever existing:

```python
# In SeedService.run():
self._clean()

with transaction.atomic():
    # Steps 5-13: all generation inside this block
    user_instances = user_gen.generate(users)
    User.objects.bulk_create(user_instances, batch_size=5000)
    ...
```

**Caveat:** A 600-ad seed with analytics may exceed PostgreSQL's transaction memory limits. Test with `--ads=600` to verify. If memory is a concern, wrap only the user + ad creation phases together (not analytics/images).

### Priority 2 — Fix Critical Crash: Identify Seed Users Robustly (GAP 2.1)

Add a `source` field to the `User` model (like `Ad` has) to identify seed users independently of ads. This allows `_clean()` to find all seed users even if their ads are missing:

```python
# In User model (models.py):
source = models.CharField(
    max_length=20,
    choices=[(s.value, s.value) for s in UserSource],
    default=UserSource.TELEGRAM,
    help_text="Origin of the user account",
)
```

Then `_clean()` can use:
```python
seed_user_ids = list(User.objects.filter(source=UserSource.SEED).values_list("id", flat=True))
```

**Alternative (no migration):** In `_clean()`, also delete users whose `telegram_id` falls in the seed range (10000+) and who were created during the last seed. But without a timestamp or source field, this is fragile.

### Priority 3 — Fix High: Clean Trust Event AnalyticsEvents (GAP 3.1)

Delete analytics events for seed users, not just seed ads. Add to `_clean()`:

```python
# Delete events linked to seed users (catches trust events with ad=NULL)
AnalyticsEvent.objects.filter(
    user_id__in=seed_user_ids,
).delete()
```

This must execute INSIDE the existing `transaction.atomic()` block, and BEFORE the user deletion (step 5). Since `seed_user_ids` is pre-computed before the transaction, this is safe.

**Combined with the existing filter:**
```python
# Delete events linked to seed ads OR seed users
AnalyticsEvent.objects.filter(
    models.Q(ad__source=AdSource.SEED) | models.Q(user_id__in=seed_user_ids)
).delete()
```

### Priority 4 — Fix Medium: Clean PopularSearch (GAP 4.1)

Add PopularSearch cleanup to `_clean()`. Since `_seed_popular_searches` rebuilds all entries via `update_or_create`, deleting first is safe:

```python
# In _clean() (inside or after the transaction block):
PopularSearch.objects.all().delete()
```

**Caveat:** This would remove runtime-generated popular searches from real user activity. In a dev environment where seed and production data coexist on the same DB, this would be destructive. Safer approach: only delete entries whose `query_normalized` is in the known seed set (config + derived from seed ads). But this requires computing the derived set before deletion.

**Pragmatic fix for dev-only:** Since seed runs with `--force` in Docker and is a development-only concern, deleting all PopularSearch rows before re-seed is acceptable. Document this clearly.

### Priority 5 — Defense-in-Depth: Add `ignore_conflicts=True` to User Bulk Create (GAP 2.1 safety net)

```python
User.objects.bulk_create(user_instances, batch_size=5000, ignore_conflicts=True)
```

**Caveat:** With `ignore_conflicts=True`, `bulk_create` silently skips rows that violate unique constraints. The orphaned users from a previous failed run would be silently skipped (their telegram_id already exists). The new ads would then be assigned to these existing users via `User.objects.order_by("-id")[:users]`. This is actually the correct recovery behavior — orphaned users are reused. This is a pragmatic band-aid if adding a transaction wrapper or User.source field is not feasible.

### Priority 6 — Remove Duplicate Log Statement (GAP 4.4)

```python
# Remove this line in _log_progress():
logger.info("  %s: %d rows in %.2fs", name, count, elapsed)
```

---

## 11. Appendix — File References

| File | Lines | Relevance |
|---|---|---|
| `seed/services/seed_service.py` | 198-243 | `_clean()` method — primary subject of audit |
| `seed/services/seed_service.py` | 57-196 | `run()` method orchestration |
| `seed/services/seed_service.py` | 318-356 | `_seed_popular_searches()` |
| `seed/generators/users.py` | 31 | `itertools.count(start=10_000)` — telegram_id collision source |
| `seed/generators/images.py` | 252-300 | `_preprocess_one()` thumbnail cache check |
| `seed/generators/analytics.py` | 182-231 | `generate_daily_metrics()` with `ignore_conflicts` |
| `docker/entrypoint-seed.sh` | 32-34 | `--force` always passed in Docker |
| `apps/users/models.py` | 36-48 | `telegram_id` and `chat_id` unique constraints |
| `apps/users/migrations/0001_initial.py` | 45-46 | Confirms unique=True on telegram_id and chat_id |
| `apps/analytics/models.py` | 36-43 | `AnalyticsEvent.ad` uses `on_delete=models.SET_NULL` |
| `apps/analytics/services/trust_analytics.py` | 92-107 | `record_trust_event()` creates events with `ad=None` |
| `apps/trust/services/trust_calculator.py` | 57-88 | `get_or_create` for SellerTrustScore (idempotent) |
| `apps/trust/models.py` | 11-17 | `SellerTrustScore.user` is OneToOneField with CASCADE |
| `apps/core/enums.py` | 41 | `AdvisoryLockId.SEED = 110` |
| `apps/core/utils/advisory_lock.py` | 17-61 | Session-scoped advisory lock implementation |
| `apps/categories/catalog/builder.py` | 128-353 | `load_catalog` uses `update_or_create` — idempotent |
| `apps/core/management/commands/create_admin_user.py` | 59-116 | `create_admin` uses check-then-create — idempotent |
| `docker-compose.yml` | 55-136 | Service definitions for migrate, load_catalog, create_admin, seed |
| `docker-compose.dev.override.yml` | 64-84 | Seed auto-runs with `--force` in dev |
| `docker-compose.prod.yml` | 24-27 | Seed uses pre-built image in prod, profile-gated |
| `seed/tests/test_seed.py` | 513-521 | `test_seed_idempotent` — only tests happy path |
