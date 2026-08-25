---
id: docker-one-shot-lifecycle-analysis
domain: research
related:
  - docs/99-agent/architecture
  - docs/99-agent/rules
tags:
  - docker-compose
  - one-shot-services
  - seed
  - volume-lifecycle
  - idempotency
---

# Docker Compose One-Shot Service Lifecycle Analysis

**Project:** Mko Bazuna
**Docker Compose:** v5.3.1 (v2 format)
**Date:** 2026-08-25
**Confidence levels:** HIGH for observed codebase behavior; HIGH for Docker Compose v2 documented behavior verified against `docker compose up --help` and official Compose v2 semantics.

---

## 1. Project Context

### 1.1 One-shot services (in `docker-compose.yml`)

All four one-shot services are defined in `docker-compose.yml` with no `restart` policy (so Docker daemon does not auto-restart them), and no `profiles` gate in the base file **except** `seed` (which has `profiles: ["seed"]`):

| Service | Command | `depends_on` | `restart` | `profiles` |
|---|---|---|---|---|
| `migrate` | `python -c "...migrate_locked.main()"` | `db` (healthy) | _none_ | _none_ |
| `load_catalog` | `/app/entrypoint-catalog.sh` → `load_catalog` | `migrate` (completed), `redis` (healthy) | _none_ | _none_ |
| `create_admin` | `/app/entrypoint-create-admin.sh` → `create_admin_user` | `load_catalog` (completed) | _none_ | _none_ |
| `seed` | `/app/entrypoint-seed.sh` → `manage.py seed --force` | `load_catalog` (completed) | _none_ | `["seed"]` in base |

In `docker-compose.dev.override.yml`, `seed` gets `profiles: !reset []` (Section 3 explains the `!reset` mechanism).

### 1.2 Long-lived services

| Service | `restart` | `profiles` |
|---|---|---|
| `db` | `always` | _none_ |
| `redis` | `always` | _none_ |
| `web` | `unless-stopped` | _none_ |
| `bot` | `unless-stopped` | _none_ |
| `nginx` | `unless-stopped` | _none_ (or `["use-nginx"]` in dev override) |

### 1.3 Volume declarations

Named volumes declared at the bottom of `docker-compose.yml` (lines 208–210):

```yaml
volumes:
  postgres_data:
  media_volume:
```

- `postgres_data` → mounted at `/var/lib/postgresql` on `db`
- `media_volume` → mounted at `/app/media` on `seed`, `web`, `bot`, and `/media_volume:ro` on `nginx`

**No anonymous volumes** are declared anywhere in the compose files. All data-bearing volumes are named. This is critical for understanding `--renew-anon-volumes` (Section 5).

### 1.4 Makefile targets (the entry points agents use)

| Target | Command | Project name |
|---|---|---|
| `up` | `docker compose $(COMPOSE_FILES) up -d` | `mko-bazuna-dev` |
| `down` | `docker compose $(COMPOSE_FILES) down` | `mko-bazuna-dev` |
| `reset` | `docker compose $(COMPOSE_FILES) down -v --remove-orphans` | `mko-bazuna-dev` |
| `build` | `docker compose $(COMPOSE_FILES) build --no-cache` | `mko-bazuna-dev` |
| `seed` | `docker compose $(COMPOSE_FILES) run --rm seed` | `mko-bazuna-dev` |

All dev commands use `-f docker-compose.yml -f docker-compose.dev.override.yml`.

---

## 2. Docker Compose v2 Behavior for One-shot (Exited) Containers

### 2.1 Baseline: `docker compose up` with existing exited containers

**Behavior: NO re-run.**

When a one-shot service container is already in `exited` state and neither its image nor configuration has changed, `docker compose up` prints:

```
Container mko-bazuna-dev-migrate-1  already exists
```

and leaves the container as-is. It does **not** restart the exited container.

**Why:** Docker Compose v2 tracks container state via labels on the container itself. On `up`, it compares the desired state (from compose file) against the actual container. If the container exists and its image hash + config hash match, Compose considers it "up to date" and skips recreation. For a one-shot service in `exited` state with no `restart` policy, there is nothing to start — the container is already stopped.

**Verified:** Docker Compose v5.3.1 `--help` shows no special handling for exited containers in the default `up` path. The recreate logic only triggers when the container is missing or its configuration/image differs.

### 2.2 `docker compose up --force-recreate`

**Behavior: YES, re-runs one-shot services.**

`--force-recreate` (shown in `--help`: "Recreate containers even if their configuration and image haven't changed") forces recreation of **all** containers, including exited one-shot ones. The old container is removed and a new one is created and started. One-shot services re-run from scratch.

### 2.3 After `docker compose build` (image change)

**Behavior: YES, re-runs one-shot services on the next `docker compose up`.**

When `docker compose build` produces a new image (different image ID), the next `docker compose up` detects that the container's `image` no longer matches the compose file's `image` (or `build` hash differs). Compose triggers a **recreate** for all containers that use that image — including one-shot services.

This is the most significant trigger in the agent workflow:
- `make build` runs `docker compose build --no-cache` → image is rebuilt → image ID changes.
- `make up` runs `docker compose up -d` → Compose detects image change → recreates ALL containers (db, redis, web, bot, migrate, load_catalog, create_admin, seed).
- One-shot services re-run in dependency order.

**Note:** Even `docker compose build` without `--no-cache` will change the image if any `COPY` context (e.g., source code) changed. The `Makefile` uses `--no-cache` for `build`, guaranteeing an image change every time.

### 2.4 `docker compose up --remove-orphans`

**Behavior: Does NOT re-run one-shot services that are defined in the compose file.**

`--help` says: "Remove containers for services not defined in the Compose file."

`--remove-orphans` only removes containers for services that exist on disk (running or exited) but are **no longer present** in the compose file configuration. It does **nothing** to exited one-shot containers for services that ARE still defined. Those containers remain, and `up` will still say "already exists" without recreating them.

### 2.5 `docker compose down` (without `-v`)

**Behavior: YES, one-shot services re-run on the next `up`.**

`docker compose down` **stops and removes** all containers in the project (including exited one-shot containers), along with project networks. Named volumes (`postgres_data`, `media_volume`) are **preserved**.

On the next `docker compose up`:
- Long-lived services are freshly created and started.
- One-shot services are freshly created and started (their containers were removed, so Compose has nothing to say "already exists").
- The database data persists in `postgres_data` — so the DB still has tables, seed users, and seed ads from the previous run.

This is the scenario where seed re-runs against existing data. The `_clean()` method must handle this.

### 2.6 `docker compose down -v` (with volume destruction)

**Behavior: YES, one-shot services re-run on the next `up`, AND all data is wiped.**

`-v` removes named volumes too (`postgres_data`, `media_volume`). On the next `up`:
- The DB starts with a fresh, empty database.
- `migrate` runs against an empty DB (creates all tables from scratch).
- `load_catalog` loads categories.
- `create_admin` creates the admin user.
- `seed` runs against an empty DB (`-clean` is a no-op, no orphaned users).

This is the `make reset` target, which is the safe nuclear option.

### 2.7 Docker Compose v2 `--wait` flag

**Behavior: Waits for all started services to reach a healthy/running state, then exits.**

Available in Compose v5.3.1 (verified via `--help`):
```
--wait                 Wait for services to be running|healthy. Implies detached mode.
--wait-timeout int     Maximum duration in seconds to wait for the project to be running|healthy
```

- For **long-running** services: waits until the healthcheck passes (or, if no healthcheck, until the container is `running`).
- For **one-shot** services: waits until the container exits with code 0. If the one-shot exits non-zero, `up --wait` reports failure.
- The `make up` target does **not** use `--wait`, so Compose returns immediately after `-d` (detached) startup. This means agents get no signal about whether one-shot services succeeded.

**Important gap:** If agents rely on `make up` completing successfully, they have no visibility into whether `seed` or `migrate` actually finished or failed. The one-shot containers exit silently; `docker compose ps` shows them as `exited (0)` or `exited (1)` but the `up -d` command returns `0` regardless.

### 2.8 `docker compose start` vs `docker compose up`

`docker compose start` **only starts existing stopped containers** — it does not create new ones. For a one-shot service in `exited` state, `start` would try to restart the already-exited container, which Docker treats as "container already exited." This rarely works for one-shot services.

`docker compose up` is the correct lifecycle command: it creates (if missing) or recreates (if changed) + starts containers.

---

## 3. The `profiles: !reset []` Mechanism on `seed`

### 3.1 Base compose (`docker-compose.yml`, line 113–114)

```yaml
  seed:
    ...
    profiles:
      - seed
```

In production (and when using the base file alone), `seed` is gated behind the `seed` profile. It will **not** start with a plain `docker compose up`. To run it, you must explicitly invoke:

```bash
docker compose --profile seed up -d seed   # or
docker compose run --rm --profile seed seed
```

### 3.2 Dev override (`docker-compose.dev.override.yml`, lines 69–70)

```yaml
  seed:
    profiles: !reset []
```

The `!reset` YAML tag is a Docker Compose extension. `profiles: !reset []` means: **replace** the `profiles` value from the base file with an empty list. An empty `profiles` list means the service has **no profile gate** — it runs by default with `docker compose up`.

**Effect:** In the dev environment, `seed` is treated like any other service. It starts (and exits) as part of `docker compose up`, alongside `web`, `bot`, `migrate`, `load_catalog`, and `create_admin`.

**But:** If the `seed` container already exists in `exited` state (from a previous `make up`), and neither the image nor configuration has changed, `docker compose up` will still say "already exists" and **NOT** re-run it — exactly like the other one-shot services. The `!reset []` only removes the profile gate; it does not override Compose's container-existence check.

### 3.3 Production override (`docker-compose.prod.yml`)

The prod override does **not** override `profiles` on `seed`. It only sets `image: ...`. So in production, `seed` retains `profiles: ["seed"]` and does not auto-start — it must be explicitly triggered.

### 3.4 `profiles` does NOT affect `depends_on` resolution

When `web` has `depends_on: seed` (dev override, line 31–32), Compose ensures `seed` starts (if its profile is active) before `web`. But if the `seed` container already exists (exited), Compose does not restart it — `web` starts anyway because the dependency condition (`service_completed_successfully`) is satisfied by the container's previous exit code.

---

## 4. Docker Compose `depends_on` Conditions

### 4.1 Conditions used in this project

| Service | Dependency | Condition |
|---|---|---|
| `migrate` | `db` | `service_healthy` |
| `load_catalog` | `migrate` | `service_completed_successfully` |
| `load_catalog` | `redis` | `service_healthy` |
| `create_admin` | `load_catalog` | `service_completed_successfully` |
| `seed` | `load_catalog` | `service_completed_successfully` |
| `web` (dev) | `seed` | `service_completed_successfully` |
| `web` (dev) | `load_catalog` (base) | `service_completed_successfully` |
| `web` (dev) | `redis` (base) | `service_healthy` |
| `bot` | `load_catalog` (base) | `service_completed_successfully` |
| `bot` | `redis` (base) | `service_healthy` |
| `test` | `db` | `service_healthy` |

### 4.2 `service_completed_successfully` — what it means

This condition checks the container's **previous exit code**. If the container exited with code 0, the condition is satisfied. If the container never ran or exited non-zero, the condition is not met and dependent services will not start.

**Critical implication:** Once `seed` has exited 0 (success), any service `depends_on: seed: condition: service_completed_successfully` will consider the dependency satisfied even on subsequent `up` runs where the seed container is NOT recreated. This means `web` can start even if the seed data is stale.

### 4.3 Silent failure scenario

If a one-shot service exits 0 but **partially** completed its work (e.g., seed created users but crashed before creating ads, or the container was killed by OOM after `bulk_create` of users but before the rest of the pipeline):

1. The container exits — but the exit code may be non-zero if killed by signal (SIGKILL = exit 137, SIGKILL from OOM killer). In this case, `service_completed_successfully` is **NOT** met, and dependent services won't start.
2. If the container exits 0 (e.g., Python script caught an exception and returned 0, or the exception propagated and Django's management command handler returned non-zero), the condition IS met.

**For the seed service specifically:** The entrypoint script has `set -euo pipefail`, so any non-zero exit from `manage.py seed` propagates. The `manage.py seed` command calls `SeedService.run()`, which wraps everything in an advisory lock but **does NOT** wrap the entire run in `transaction.atomic()`. If an exception occurs mid-way (e.g., `IntegrityError` on `bulk_create` of users), the transaction for the failing `bulk_create` is rolled back, but prior `bulk_create` calls (users, ads) have already been committed. The exception propagates, the command exits non-zero, and the container exits non-zero.

This means: **a failed seed run that exits non-zero leaves the DB in a partially-seeded state**, and the one-shot container will be in `exited (1)` state. On the next `docker compose up --force-recreate` (or after `--build`), the seed container is recreated and re-runs, but `_clean()` may not fully clean the orphaned data (see Section 6).

---

## 5. `--renew-anon-volumes` and Volume Lifecycle

### 5.1 `--renew-anon-volumes` (`-R`)

From `--help`: "Recreate anonymous volumes instead of retrieving data from the previous containers."

This flag affects **only anonymous volumes** — volumes declared inline in a service's `volumes:` key without a name (e.g., `volumes: - /data`). It creates a fresh anonymous volume on each container recreation.

**This project uses NO anonymous volumes.** Every volume is named (`postgres_data`, `media_volume`). Therefore, `--renew-anon-volumes` has **no effect** on this project's data persistence. It would not help with the seed re-run scenario.

### 5.2 Named volume lifecycle

| Command | `postgres_data` volume | `media_volume` volume |
|---|---|---|
| `docker compose up` (container exists) | Persisted (container not recreated) | Persisted |
| `docker compose up --force-recreate` | Persisted (named volume survives) | Persisted |
| `docker compose up` (after `build`) | Persisted | Persisted |
| `docker compose down` | Persisted (only containers removed) | Perserved |
| `docker compose down -v` | **Removed** | **Removed** |
| `make reset` (= `down -v --remove-orphans`) | **Removed** | **Removed** |

### 5.3 `media_volume` and seed images

The `seed` service mounts `media_volume:/app/media` (base, line 133). The `ImageGenerator` writes fixture JPEGs to `MEDIA_ROOT/seed/` within this volume. On re-run after `--build`:

1. `seed` container is recreated → starts fresh.
2. `_clean()` deletes `MEDIA_ROOT/seed/` directory (via `shutil.rmtree`).
3. `ImageGenerator` re-downloads or copies fixture images.

If the image was rebuilt, the container's filesystem is fresh, but the named `media_volume` persists. The `_clean()` media cleanup handles stale image files in `media_volume`.

### 5.4 Test environment volume behavior

For the test project (`mko-bazuna-test`), the `db` service uses the base `postgres_data` named volume (prefixed by project name → `mko-bazuna-test_postgres_data`). The `test` service is a one-shot that:

1. Starts with `init: true` (PID 1 signal forwarding + zombie reaping).
2. Runs migrations via `migrate_locked.main()`.
3. Runs pytest with `--reuse-db` (default in `entrypoint-test.sh`).

**`--reuse-db` caches the `test_<random_string>` schema** within the PostgreSQL instance. As long as `postgres_data` persists (no `-v`), the test schema is reused. `make test-down` runs `docker compose down` (no `-v`), so the volume survives. This is why `make test` is fast on subsequent runs.

**Stale schema danger:** If migrations changed but `--reuse-db` reuses a schema from before the migration, ~527 tests fail (documented in `.kilo/rules` and `entrypoint-test.sh` comments). `make test-recreate` runs `--no-reuse-db --create-db` to force a fresh schema.

---

## 6. The Specific Failure Scenario in the Seed Module

### 6.1 The `_clean()` method's user identification gap

Located in `src/backend/apps/seed/services/seed_service.py` (lines 198–243):

```python
def _clean(self) -> None:
    # Identify seed user IDs (users who have seed ads)
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
```

**Key observation:** `seed_user_ids` is computed via the reverse FK relation `User.objects.filter(ads__source=AdSource.SEED)`. This query returns users who **currently have ads** with `source=AdSource.SEED`. Users who were created by a previous seed run but whose ads have been deleted (or were never created) are **NOT** in this set.

The `seed_user_ids` query is executed **before** the transaction that deletes the ads. So in a normal complete run, every seed user has seed ads, and all seed users are identified and deleted. The `transaction.atomic()` block ensures all-or-nothing deletion.

### 6.2 `UserGenerator` always starts from `telegram_id = 10_000`

Located in `src/backend/apps/seed/generators/users.py` (lines 31, 45–46):

```python
class UserGenerator(BaseGenerator):
    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._telegram_id_counter = itertools.count(start=10_000)
        ...

    def generate(self, count: int) -> list[User]:
        users: list[User] = []
        for _ in range(count):
            telegram_id = next(self._telegram_id_counter)
            user = User(
                telegram_id=telegram_id,
                chat_id=telegram_id,
                ...
            )
            users.append(user)
        return users
```

The `UserGenerator` uses `itertools.count(start=10_000)` — a **deterministic, hardcoded starting point**. It never queries the database for the maximum existing `telegram_id`. Every seed run produces users with `telegram_id` 10000, 10001, 10002, ... (and the same values for `chat_id`).

The `User` model (line 36–41 of `src/backend/apps/users/models.py`) has:
```python
telegram_id = models.BigIntegerField(unique=True, blank=True, null=True, ...)
chat_id = models.BigIntegerField(unique=True, db_index=True, ...)
```

Both fields have `unique=True`. PostgreSQL allows multiple `NULL`s (so non-admin users with `telegram_id=None` are unaffected), but seed users always have non-null values.

### 6.3 The failure chain

The gap manifests when the seed run is **interrupted** between user creation and ad creation, or when users from a previous run are orphaned:

**Step 1 — First seed run starts (via `make up` after `make build`):**

1. `_clean()` runs: finds seed users via `ads__source=AdSource.SEED`. If this is a fresh DB (or `make reset` was run), there are no seed ads → `seed_user_ids` is empty → no users to delete.
2. `UserGenerator.generate(10)` creates 10 User objects with `telegram_id` 10000–10009, `chat_id` 10000–10009.
3. `User.objects.bulk_create(user_instances, batch_size=5000)` — succeeds, 10 users now in DB.
4. `AdGenerator.generate(600)` creates 600 Ad objects assigned to these 10 users.
5. **Container is killed** (OOM, `Ctrl+C`, timeout, agent `docker compose down`, etc.) — exits with code 137 (SIGKILL) or non-zero.

**Result:** 10 seed users exist in DB with `telegram_id` 10000–10009. Zero or partial seed ads exist. No seed users have ads (if killed before `Ad.objects.bulk_create`).

**Step 2 — Second seed run (via `make build && make up`, or `make seed`):**

1. `_clean()` runs:
   - `seed_user_ids = User.objects.filter(ads__source=AdSource.SEED).values_list("id", flat=True)` — returns `[]` because the seed ads were either never created or were deleted.
   - `Ad.objects.filter(source=AdSource.SEED).delete()` — deletes whatever partial ads exist.
   - `User.objects.filter(id__in=[]).delete()` — deletes nothing.
   - **The 10 seed users (telegram_id 10000–10009) remain in the DB as orphans.**
2. `UserGenerator.generate(10)` creates 10 NEW User objects with `telegram_id` 10000–10009 — same values as the orphans.
3. `User.objects.bulk_create(user_instances, batch_size=5000)` — fails with `IntegrityError`:
   ```
   psycopg.errors.UniqueViolation: duplicate key value violates unique constraint "users_telegram_id_..."
   DETAIL: Key (telegram_id)=(10000) already exists.
   ```

**This is the exact failure described:** `UserGenerator.bulk_create` fails with a unique constraint violation on `telegram_id`.

### 6.4 Why `_clean()` doesn't catch orphaned seed users

The `_clean()` method's logic is:

> "Delete users who have seed ads, then delete the seed ads themselves."

But the correct logic should be:

> "Delete all users who are seed users."

The problem is that there is **no explicit marker** on the `User` model identifying it as a seed-generated user. The `User` model has no `source` field (unlike `Ad.source`). The only way to identify seed users is through the reverse FK to `Ad.source=AdSource.SEED`. This is a **relational** identification, not a **direct** one.

When seed ads are deleted (by `_clean()` itself, or by a partial run, or by `load_catalog`'s `truncate`/`delete` operations), the user→ad link is broken, and the user becomes invisible to `_clean()`.

### 6.5 Additional contributing factors

1. **`load_catalog` also touches the DB:** The `load_catalog` service runs `load_catalog` management command, which calls `Category.objects.update_or_create(...)`. This does NOT delete users. But if `load_catalog` runs and succeeds, then `seed` fails, the next seed re-run has orphaned users from the failed seed.

2. **`create_admin` uses `telegram_id=-1`:** The admin user has `telegram_id=-1`, which does NOT overlap with the seed range (10000+). So admin creation is not a source of collision. However, it demonstrates the pattern: seed users should have their own identifiable range or marker.

3. **`Ad.user` FK is `CASCADE`:** When a user is deleted, all their ads are cascade-deleted. But `_clean()` deletes ads first (line 227), so the cascade doesn't trigger. The cascade only protects against inconsistency if users are deleted without first deleting their ads.

4. **No try/except in `SeedService.run()`:** The `run()` method does not catch `IntegrityError` or any exception from `bulk_create`. If a collision occurs, the entire seed process aborts with a stack trace. The advisory lock (`AdvisoryLockId.SEED = 110`) ensures no concurrent seed runs, but does not help with sequential stale-data runs.

5. **`bulk_create` with `batch_size=5000`:** When `bulk_create` fails on a batch, it is an all-or-nothing operation at the SQL level — the entire batch is rolled back. However, `SeedService` creates users and ads in separate `bulk_create` calls, so if the user creation fails, no ads are created. The users are the first batch — if they collide, the seed aborts at step 4 (line 96).

---

## 7. Which Scenarios Trigger Re-runs of One-shot Services

| Scenario | One-shot re-runs? | Why |
|---|---|---|
| `make up` (plain, containers exist, image unchanged) | **NO** | Compose says "already exists", skips recreation |
| `make build` then `make up` | **YES** | Image changed → Compose recreates ALL containers |
| `make up --force-recreate` | **YES** | Forces recreation of all containers |
| `make down` then `make up` | **YES** | Containers removed → fresh creation |
| `make down -v` then `make up` | **YES** + fresh data | Containers + volumes removed |
| `make up --remove-orphans` (no containers removed) | **NO** | Only removes services not in compose file |
| `make up` where long-lived services running, image unchanged | **NO** | One-shot containers exist in `exited` state |
| `make seed` (run --rm seed) | **YES** (new container) | `run --rm` always creates a new container |
| `make reset` then `make up` | **YES** + fresh data | Volumes destroyed, all containers recreated |

### 7.1 The agent workflow failure path (most common)

```
1. make up          → everything starts, seed runs, data populated
2. (code changes, agent iterates)
3. make build       → image rebuilt (--no-cache, image ID changes)
4. make up          → Compose detects image change → recreates ALL containers
                        → migrate (no-op, already applied), load_catalog (idempotent),
                          create_admin (idempotent), seed (RE-RUNS)
                        → seed._clean() may not catch orphaned users → IntegrityError
```

This path triggers seed re-runs because `make build --no-cache` always changes the image. Every code iteration by an agent that includes `make build` will cause seed to re-run on the next `make up`.

If a previous seed run was interrupted (steps 1–3 above, where the container was killed mid-run), the orphaned users from that run will cause the next re-run to fail.

### 7.2 When does it NOT re-run (causing stale data)

1. **Plain `make up` after code changes without `make build`:** If the agent only changes source code mounted via bind-mount (`.:/app` in dev override), the image doesn't change. The one-shot containers (migrate, load_catalog, create_admin, seed) are NOT recreated. The stale data from the previous seed run persists. But since dev uses bind-mounts, the source code IS live — only the one-shot containers don't re-run, which is usually fine (migrations haven't changed, catalog is loaded, seed data is sufficient).

2. **`make up` when all containers are running, image unchanged:** Compose says "all containers up to date." One-shot services stay in `exited` state, never re-run.

---

## 8. Docker Compose Features and Patterns That Could Solve This

### 8.1 `init: true` on one-shot services

The test service (`docker-compose.test.yml`, line 51) already uses `init: true`. This runs an init process (tini) as PID 1, which:
- Properly forwards signals (SIGTERM, SIGINT) so the Python process can shut down gracefully.
- Reaps zombie processes.

**Applying `init: true` to `seed`, `migrate`, `load_catalog`, `create_admin`:** Would ensure that if the container is killed (e.g., by `docker compose down`), the Python process receives a proper signal and can either complete or cleanly abort. This reduces the chance of a partially-completed seed run leaving orphaned users.

**Limitation:** Only helps with graceful shutdown. Does not fix the root cause (orphaned users from a previous run).

### 8.2 `docker compose up --wait` for visibility

Using `make up --wait` (or `docker compose --wait up -d`) would make `up` wait until all services are healthy or have exited successfully. If a one-shot (e.g., `seed`) exits non-zero, `up --wait` would report failure. This gives agents visibility into seed failures rather than silently proceeding with stale data.

**Limitation:** Still doesn't prevent the orphaned user problem; it just makes it visible sooner.

### 8.3 Making `UserGenerator` idempotent: query max(telegram_id)

**The core fix for the seed gap:** `UserGenerator` should query `User.objects.aggregate(Max("telegram_id"))` before generating, and start the counter above the existing maximum. Alternatively, use a range that doesn't overlap with existing users.

**Current code:**
```python
self._telegram_id_counter = itertools.count(start=10_000)
```

**Fixed approach:**
```python
max_existing = User.objects.aggregate(Max("telegram_id"))["telegram_id__max"] or 9_999
self._telegram_id_counter = itertools.count(start=max_existing + 1)
```

**Limitation:** This prevents the `IntegrityError` but doesn't truly clean up old seed users — it just avoids collisions by using higher IDs. The DB would accumulate stale seed users over multiple re-runs. The `_clean()` method should also be fixed to delete ALL user-generated seed users, not just those with ads.

### 8.4 Adding a `source` field or marker to the `User` model for seed identification

**The architectural fix:** Add a `source` field to the `User` model (mirroring `Ad.source`) or a `is_seed` boolean. Then `_clean()` can identify seed users directly:

```python
User.objects.filter(source=AdSource.SEED).delete()
```

instead of relying on the reverse FK through `Ad`:

```python
User.objects.filter(ads__source=AdSource.SEED).delete()
```

**Limitation:** Requires a schema migration, model change, and all seed code paths to set the `source` field. Higher effort but more robust.

### 8.5 `docker compose up --renew-anon-volumes`

**Not applicable:** This project uses named volumes only (`postgres_data`, `media_volume`). `--renew-anon-volumes` only affects anonymous volumes. Using it would not change behavior.

### 8.6 Forcing one-shot re-runs via `docker compose rm` before `up`

**Practical workaround:** Running `docker compose rm -sf migrate load_catalog create_admin seed` before `docker compose up` removes the exited one-shot containers. The next `up` creates and starts them fresh. This simulates `--force-recreate` for specific services without rebuilding the image.

But this is an operational workaround, not a code fix. Agents would need to know to do this.

### 8.7 `depends_on` with `condition: service_completed_successfully` does NOT force re-runs

Once a one-shot container has exited 0, the condition is permanently satisfied. Compose will not re-run it. This is the fundamental limitation of using `docker compose up` as an idempotent orchestrator for one-shot services.

---

## 9. The Orphaned User Problem — Concrete Reproduction

### 9.1 Scenario reproduction

```bash
# Fresh start
make reset          # destroys volumes, containers
make up             # image built, migrate, load_catalog, create_admin, seed all run
                      # seed creates users 10000-10009 + 600 ads, exits 0

# Simulate interruption: kill seed container mid-run after users created
docker compose exec -T db psql -c "DELETE FROM ads_ads WHERE source = 'seed' AND id > 300;"
                      # Now 10 seed users exist, but ~300 ads still exist
                      # Some users may have only a few ads

# Agent builds and starts up (this recreates all containers)
make build          # --no-cache, image ID changes
make up             # Compose recreates ALL containers (image changed)
                      # seed re-runs _clean():
                      #   seed_user_ids = users who currently have seed ads
                      #   If all seed ads were deleted above, seed_user_ids = []
                      #   Users 10000-10009 are NOT found → NOT deleted
                      #   UserGenerator creates users 10000-10009 → IntegrityError
```

### 9.2 Error message

```
django.db.utils.IntegrityError: Problem installing fixtures:
psycopg2.errors.UniqueViolation: duplicate key value
violates unique constraint "users_telegram_id_..."
DETAIL: Key (telegram_id)=(10000) already exists.
```

### 9.3 Why `make seed` (the manual target) has the same issue

The `make seed` target runs `docker compose run --rm seed`, which always creates a new container. The entrypoint runs `manage.py seed --force`. The `SeedService.run()` → `_clean()` → `UserGenerator` chain has the same orphaned-user vulnerability. If the DB has stale seed users from a previous interrupted run, `make seed` will also fail.

---

## 10. Summary

### 10.1 Docker Compose one-shot lifecycle

- `docker compose up` does NOT re-run exited one-shot containers unless their image or configuration has changed, or unless `--force-recreate` / container removal (`down`/`rm`) is used.
- `make build --no-cache` always changes the image. The subsequent `make up` detects this and recreates ALL containers, including one-shot services. This is the primary mechanism by which one-shot services re-run in the agent workflow.
- `docker compose down` (without `-v`) removes containers but preserves named volumes. The next `up` re-runs all one-shot services with the DB data intact.
- `docker compose down -v` (`make reset`) destroys named volumes too, giving a truly fresh start.
- `profiles: !reset []` on `seed` in the dev override removes the profile gate, making seed auto-run with `docker compose up`. But if the seed container already exists (exited), it still won't re-run without recreation.
- `depends_on: condition: service_completed_successfully` is satisfied by a previous successful exit code — it does NOT force a re-run on subsequent `up` calls.
- `--wait` provides visibility (exits non-zero if a one-shot fails) but is not used by `make up`.
- `--renew-anon-volumes` is ineffective because the project uses named volumes exclusively.

### 10.2 Scenarios that trigger one-shot re-runs

| Trigger | One-shot re-runs? |
|---|---|
| `make up` (image unchanged, containers exist) | ❌ No |
| `make build` then `make up` | ✅ Yes (image change) |
| `make up --force-recreate` | ✅ Yes |
| `make down` then `make up` | ✅ Yes (containers removed, volumes persist) |
| `make reset` then `make up` | ✅ Yes (containers + volumes removed) |
| `make seed` (`run --rm seed`) | ✅ Yes (always new container) |

### 10.3 Scenarios that DON'T trigger re-runs (stale data risk)

- `make up` after code changes via bind-mount, without `make build` — one-shot containers unchanged, not re-run.

### 10.4 The seed module gap

**`UserGenerator` always starts `telegram_id` from a hardcoded `10_000`** (`itertools.count(start=10_000)`), never checking the database. The `_clean()` method identifies seed users **only** through the reverse FK `User.objects.filter(ads__source=AdSource.SEED)`. If seed users are created but their ads are not (due to an interrupted run), `_clean()` cannot find them, they remain in the DB, and the subsequent `bulk_create` fails with `IntegrityError` on the `telegram_id` unique constraint.

**Recommended fixes (in order of robustness):**

1. **Immediate (code-level):** Make `UserGenerator` query `Max("telegram_id")` and start above it, with `ignore_conflicts=True` on `bulk_create` as a safety net.
2. **Intermediate:** Add a `source` field or `is_seed` flag to the `User` model, and change `_clean()` to filter by it directly instead of through the reverse FK.
3. **Operational:** Use `make reset` (or `docker compose down -v`) before `make up` when image changes are expected, ensuring a clean DB. Or add `docker compose rm -sf` for one-shot containers before `up`.
4. **Visibility:** Add `--wait` to `make up` so agents get immediate feedback when a one-shot service fails.