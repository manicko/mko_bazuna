---
name: 05-catalog-seeding
phase: catalog-seeding
template: .ai/audit/templates/audit-findings.md
status: complete
validated: no
---

# Phase 05 Audit Findings — Catalog Seeding (Clean / Fresh Launch)

**Executor:** audit-executor
**Template:** `.ai/audit/05-catalog-seeding`
**Status:** complete
**Validated:** no (static analysis only — grep + targeted reads; no runtime/prod deploy exercised)

Scope note: This audit covers **CATALOG SEEDING** (A) = production one-shot loading of *reference data* required for a first deploy (categories, lookups, cities, exchange rates, admin user). It excludes **TEST SEED** (B) = demo-data factories, the `BaseGenerator`/`factory_boy` test generators, `AnalyticsGenerator` in test conftest, and the demo ad/user/analytics generation pipeline. Where the demo `seed` service loads reference data (cities, categories via `load_catalog`), that reference-loading path is in scope; the demo-data generation itself is not.

---

## Discovery & Verification Evidence

Static analysis only (grep + targeted reads). No runtime execution.

| # | Verification performed | Method | Result |
|---|---|---|---|
| D1 | Catalog seed commands present & registered | `grep` `BaseCommand` subclasses under `apps/**/management/commands` | `load_catalog` (categories/management), `seed` (seed/management), `load_exchange_rates` (currencies/management), `create_admin_user` (core/management) all present |
| D2 | Reference-data seeded by migration vs. command | `grep` `RunPython|RunSQL|seed_` across `apps/**/migrations/*.py` | Only `core/0002_seed_default` (SiteConfig) + `ads/0001_initial` (trigger DDL). `currencies`, `categories`, `lookups`, `locations` `0001` = schema-only, zero rows |
| D3 | Cities loader location | `grep` `cities.json\|load_cities\|_load_city_fixtures` under `src/` | Only `SeedService._load_city_fixtures` (seed_service.py:291) references `cities.json`; no command/migration loads cities |
| D4 | Builder catalog phases | read `categories/catalog/builder.py:53-158` | `load_catalog` phases: lookups → categories → bindings → paths. **No cities phase** |
| D5 | One-shot chain wiring | read `docker-compose.yml:31-135` | `migrate`→`load_catalog`→`create_admin`; `seed` profile-gated (`profiles: ["seed"]`); `web`/`bot` `depends_on load_catalog` |
| D6 | Dev vs prod seed gating | read `docker-compose.dev.override.yml:64-84` | Dev resets `profiles: !reset []` (seed auto-runs); prod keeps `profiles: ["seed"]` (seed opt-in only) |
| D7 | Admin password default | read `docker-compose.yml:99`, `.env.docker.example:52-54`, `entrypoint-create-admin.sh:17-21` | `:-admin` default defeats the empty-skip guard |
| D8 | Advisory lock coverage | read `core/enums.py:23-42`, `migrate_locked.py:33`, `create_admin_user.py:75` | Locks: MIGRATE(100), CREATE_ADMIN(101), SEED(110), TEST_SCHEMA_SETUP(111). **No lock for load_catalog**; `setup_search_triggers`/`load_exchange_rates` run *outside* the MIGRATE lock (migrate_locked.py:33-37 only wraps `migrate --run-syncdb`) |
| D9 | Test schema restore scope | read `conftest.py:76-115` | Restores `migrate --run-syncdb` + `load_exchange_rates` + `setup_search_triggers` only; **not** categories/cities/admin |
| D10 | Migration squash history | `git log --oneline`, `git show 4ea19cb:...currencies/migrations/0001_initial.py`, `git show 495bf74 --stat` | Pre-squash currencies `0001` (commit 4ea19cb) had `seed_initial_rates` RunPython; squash (495bf74 "39 files to 10 initial migrations") regenerated `0001` without RunPython and deleted `0002_*` files (orphaned `.pyc` remain in `__pycache__`) |

---

## Findings

### ENT-031: Cities reference data is not loaded on a clean production deploy

| Field | Value |
|-------|-------|
| **ID** | ENT-031 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/seed/services/seed_service.py:285-307` (`_load_city_fixtures`), `src/backend/apps/categories/management/commands/load_catalog.py:30-53`, `src/backend/apps/categories/catalog/builder.py:53-158` (phases 1-4), `src/backend/apps/locations/migrations/0001_initial.py:1-60`, `docker-compose.yml:55-135`, `docker-compose.dev.override.yml:64-84` |
| **Classification** | mandatory |

**Description:**
On a fresh production launch the one-shot chain runs `migrate` (migrations + exchange rates + search triggers), `load_catalog` (categories + lookups + bindings + category_paths via `builder.load_catalog`), and `create_admin`. **Cities are loaded exclusively** by `SeedService._load_city_fixtures` (seed_service.py:285-307), which is invoked by the demo `seed` command — a service **gated behind `profiles: ["seed"]`** in production (docker-compose.yml:113-114). In dev the profile is reset (`profiles: !reset []`, docker-compose.dev.override.yml:69-70) so seed auto-runs; in prod it does not. No migration seeds cities (`locations/0001_initial.py` only creates the `cities` table, no `RunPython`), and `load_catalog`/`builder.load_catalog` have no cities phase (builder.py phases 1-4: lookups → categories → bindings → paths only). Consequently the `cities` table ships **empty** in production, breaking the city filter/selector and the bot's city-selection step on day one. `cities.json` (15 Montenegrin cities, seed_service.py:291) is reference data, not demo data, yet it is coupled to the demo-seed path.

**Evidence:**
```
$ grep -rn "cities.json\|_load_city_fixtures\|load_cities" src/
  src/backend/apps/seed/services/seed_service.py:291:        fixture_path = FIXTURES_DIR / "cities.json"
  src/backend/apps/seed/services/seed_service.py:285:    def _load_city_fixtures(self) -> list[City]:
  src/backend/apps/seed/services/seed_service.py:93:                 cities = self._load_city_fixtures()
```
- `docker-compose.yml:108-135` — `seed` service `profiles: ["seed"]` (opt-in in prod).
- `docker-compose.dev.override.yml:69-70` — `seed: profiles: !reset []` (auto-runs only in dev).
- `docker/entrypoint-catalog.sh:17` — `load_catalog --no-rewrite` (categories only).
- `builder.py:122-151` — `load_catalog` phases load Lookups, Category tree, bindings, paths; no city step.
- `locations/migrations/0001_initial.py` — `CreateModel City`, no `operations` data seeding.

**Recommendation:**
Add a `load_cities` reference-data loader (management command reusing `cities.json`) invoked by the same one-shot chain as `load_catalog`/`load_exchange_rates` — **not** gated behind the demo `seed` profile — so a clean production deploy always has cities. Treat cities as catalog reference data (A) independent of demo-data generation (B). Effort: small. Priority: mandatory.

---

### ENT-032: create_admin one-shot boots superuser `admin/admin` via compose `:-admin` default

| Field | Value |
|-------|-------|
| **ID** | ENT-032 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `docker-compose.yml:99` (`ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin}`), `docker-compose.dev.override.yml:15`, `docker/entrypoint-create-admin.sh:18-21` (skip guard), `docker/entrypoint-create-admin.sh:24-27`, `src/backend/apps/core/management/commands/create_admin_user.py:75` (lock), `:107-113` (superuser create), `.env.docker.example:52-54` |
| **Classification** | mandatory |

**Description:**
The `create_admin` one-shot is part of the clean-launch chain. `docker-compose.yml:99` sets `ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin}`, and the dev override mirrors it (docker-compose.dev.override.yml:15). `.env.docker.example:53` documents `ADMIN_PASSWORD=` (empty), intending the entrypoint skip-guard (`entrypoint-create-admin.sh:18`: `if [ -z "${ADMIN_PASSWORD}" ]`) to skip admin creation. But the `:-admin` substitution fires at Compose parse time **before** the entrypoint runs, turning empty→`admin` (non-empty), so the guard is never taken. `create_admin_user.py:107-113` then creates `is_staff=True, is_superuser=True` with username `admin`/password `admin`. Every other secret in these compose files uses the fail-fast `${VAR:?…}` form (`POSTGRES_PASSWORD`, `DJANGO_SECRET_KEY`; docker-compose.yml:10-12,46); `ADMIN_PASSWORD` is the sole exception defaulting to a real credential. A deploy that copies the example env (or forgets to set `ADMIN_PASSWORD`) boots an internet-facing `/admin/` superuser authenticated with `admin`/`admin`. Pre-existing, cross-referenced as **CFG-001** in Phase 02.

**Evidence:**
```
$ docker compose --project-name cfg -f docker-compose.yml -f docker-compose.dev.override.yml --env-file .env.docker config | grep ADMIN_PASSWORD
  ADMIN_PASSWORD: ""        # web/bot: empty from env_file
  ADMIN_PASSWORD: admin     # create_admin service: :-admin default fires
```
- `docker-compose.yml:99:      - ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin}`
- `docker/entrypoint-create-admin.sh:18:if [ -z "${ADMIN_PASSWORD}" ]; then  # never true once :-admin applies`
- `create_admin_user.py:107-113` — `User.objects.create(..., is_staff=True, is_superuser=True)`
- `.env.docker.example:52-54` — `ADMIN_USERNAME=admin`, `ADMIN_PASSWORD=`, `ADMIN_TELEGRAM_ID=-1`

**Consequence:** Full database read/write compromise via `/admin/` on any deploy that uses the documented (empty) default.

**Recommendation:**
Remove the `:-admin` default from `docker-compose.yml:99` and `docker-compose.dev.override.yml:15`; align with the entrypoint-intended fail-fast/skip behavior (empty → skip creation, not → default to `admin`). This is a trivial, mandatory fix already tracked under CFG-001.

---

### ENT-033: `migrate` one-shot couples schema DDL + search-trigger DDL + exchange-rate seeding via `&&`

| Field | Value |
|-------|-------|
| **ID** | ENT-033 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `docker-compose.yml:35` (migrate command), `src/backend/apps/core/utils/migrate_locked.py:33-37`, `src/backend/apps/currencies/management/commands/load_exchange_rates.py:46-79`, `src/backend/apps/ads/management/commands/setup_search_triggers.py:106-131`, `docker/entrypoint-test.sh:21-23` |
| **Classification** | advisory |
| **Status** | RESOLVED — `migrate_locked.main()` already wraps all three steps (`migrate --run-syncdb`, `setup_search_triggers`, `load_exchange_rates`) under `AdvisoryLockId.MIGRATE` (100) session lock via `subprocess.run`; the `&&` chain is eliminated from `docker-compose.yml:35`. |

**Description:**
The prod `migrate` one-shot command is a single `&&` chain:
```
python -c '...migrate_locked.main()...' && python manage.py setup_search_triggers && python manage.py load_exchange_rates
```
`migrate_locked.main()` (migrate_locked.py:33-37) runs `manage.py migrate --run-syncdb` **inside** the `AdvisoryLockId.MIGRATE` (100) session lock, but `setup_search_triggers` and `load_exchange_rates` execute **after** that lock releases — outside any transaction or guard, and outside the lock. Worse, the `&&` coupling means **a failure in `setup_search_triggers` aborts `load_exchange_rates`**: on a fresh DB the `exchange_rates` table is created empty by the migration (currencies/0001_initial.py, no `RunPython`), so if the trigger-DDL step errors, currency reference data is never seeded and every non-EUR `price_normalized_eur` lookup fails. Because `load_catalog`, `web`, and `bot` all `depends_on: migrate condition: service_completed_successfully` (docker-compose.yml:62, 142-144, 169-171), a trigger-creation failure also cascades and blocks the entire catalog/site launch. The test entrypoint (entrypoint-test.sh:21-23) is more resilient — it guards each step with `|| true` — so the prod/test paths diverge in error handling.

**Evidence:**
- `docker-compose.yml:35` — `command: bash -c "...migrate_locked... && ...setup_search_triggers && ...load_exchange_rates"`
- `migrate_locked.py:33-37` — lock wraps only `manage.py migrate --run-syncdb`.
- `entrypoint-test.sh:21-23` — `migrate --run-syncdb || {...}` ; `load_exchange_rates || true` ; `setup_search_triggers || true`.

**Recommendation:**
Decouple reference-data seeding from DDL: run `load_exchange_rates` independently of `setup_search_triggers` (and optionally under its own guard), so trigger-failure cannot starve the currency table. Standardize the prod/test error handling so the two entrypoints can't silently diverge again. Priority: advisory (operational robustness).

**Resolution:**
Already resolved in code. `migrate_locked.main()` (`migrate_locked.py:48-66`) now runs all three steps (`migrate --run-syncdb`, `setup_search_triggers`, `load_exchange_rates`) inside the `with advisory_lock(AdvisoryLockId.MIGRATE, session=True):` block as `subprocess.run` child processes. The `&&` chain in `docker-compose.yml:35` is gone — the migrate service now runs a single `python -c` invocation. ENT-036 further consolidates this into the `bootstrap_reference_data` management command.

---

### ENT-034: Migration squash removed reference-data RunPython; seeding now lives only in post-migrate commands

| Field | Value |
|-------|-------|
| **ID** | ENT-034 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/currencies/migrations/0001_initial.py` (now schema-only), `src/backend/apps/currencies/management/commands/load_exchange_rates.py:1-35` (docstring), `src/backend/apps/categories/migrations/0001_initial.py`, `src/backend/apps/lookups/migrations/0001.py`, `src/backend/apps/core/migrations/0002_seed_default.py`, git history `495bf74`, `4ea19cb` |
| **Classification** | advisory |

**Description:**
The pre-squash `currencies/0001_initial.py` (commit `4ea19cb feat(currency)`) contained a `seed_initial_rates` `RunPython` that seeded EUR/BAM/RSD on `initial=True`. The migration squash (`495bf74 "squash migrations — 39 files to 10 initial migrations"`) regenerated `0001_initial` **without** the `RunPython` — only `CreateModel ExchangeRate` — and folded `currencies/0002_alter_exchangerate_created_at_and_more.py` and `categories/0002_categorylistingcondition.py` into the new `0001` (both old files deleted). The `load_exchange_rates` command docstring explicitly documents this: "After a migration squash that deletes and regenerates migration files via makemigrations, RunPython data migrations such as seed_initial_rates cannot be regenerated from model state. This command recreates the fixed initial rates idempotently." Net effect: on a fresh DB the migrations create the `exchange_rates`, `lookup_items`, `lookup_groups`, and `categories` tables but populate **zero rows**; reference data exists only after the post-migrate one-shot commands run. The only surviving reference-data migration is `core/0002_seed_default` (SiteConfig) — an **inconsistent strategy** where some reference data is migration-seeded (SiteConfig) and the rest is command-seeded (rates/cities/categories), with no documented contract for the gap. Orphaned `.pyc` for the deleted `0002_*` migrations linger in `__pycache__` (e.g. `currencies/migrations/__pycache__/0002_alter_exchangerate_created_at_and_more.cpython-314.pyc`, `categories/migrations/__pycache__/0002_categorylistingcondition.cpython-314.pyc`), artifacts of the squash.

**Evidence:**
```
$ git show 4ea19cb:src/backend/apps/currencies/migrations/0001_initial.py
  def seed_initial_rates(apps, schema_editor):
      ExchangeRate = apps.get_model("currencies", "ExchangeRate")
      rates = [{"currency": "EUR", ...}, {"currency": "BAM", ...}, {"currency": "RSD", ...}]
```
- current `currencies/migrations/0001_initial.py` — only `operations = [migrations.CreateModel(name="ExchangeRate", ...)]`, no `RunPython`.
- current `categories/migrations/0001_initial.py` — `CreateModel` for Category/bindings only, no `RunPython`.
- `load_exchange_rates.py:3-7` (docstring) — explains the post-squash command-based seeding.
- `core/migrations/0002_seed_default.py:6-17` — the lone surviving reference-data `RunPython` (`seed_site_config`).
- `git show 495bf74 --stat` — lists `currencies/0002_alter...` (23 lines) and `categories/0002_categorylistingcondition` (30 lines) as deleted.

**Recommendation:**
Document the post-squash seeding contract explicitly (migrations build schema; one-shot commands seed reference data on first deploy). Consider seeding the EUR base rate (`rate_to_eur=1.0`) in a data migration so `price_normalized_eur` never hits an empty table between `migrate` and `load_exchange_rates`. Remove orphaned `__pycache__/0002_*.pyc`. Priority: advisory.

---

### ENT-035: `rewrite_yaml=True` default in `SeedService._load_category_fixtures` diverges from the prod `--no-rewrite` one-shot

| Field | Value |
|-------|-------|
| **ID** | ENT-035 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/seed/services/seed_service.py:277-279`, `src/backend/apps/categories/catalog/builder.py:53-57` (`rewrite_yaml: bool = True`), `src/backend/apps/categories/catalog/builder.py:153-156`, `docker/entrypoint-catalog.sh:17` (`--no-rewrite`), `src/backend/apps/categories/management/commands/load_catalog.py:36-39` |
| **Classification** | advisory |

**Description:**
The production `load_catalog` one-shot passes `--no-rewrite`, so `load_catalog.py:38-39` calls `builder.load_catalog(config_path, apps=None, rewrite_yaml=False)` (builder.py:56 default is `True`, overridden to `False`). But `SeedService._load_category_fixtures` (seed_service.py:277-279) calls `load_catalog(CATALOG_PATH)` with the **default `rewrite_yaml=True`**. So the demo seed mutates the canonical `categories.yaml` on disk whenever a `new_slug` rename exists, whereas the prod chain never rewrites it. The catalog is currently clean (grep finds zero `new_slug` / `deferred` entries in categories.yaml), so the divergence is latent — but any future rename turns the YAML into a source of truth that two code paths treat inconsistently (prod assumes immutable; demo seed rewrites it), risking merge conflicts and a drifted canonical config. `builder._rewrite_yaml` (builder.py:536-644) writes to a temp file then `os.replace`s the original.

**Evidence:**
```
$ grep -rc "new_slug\|deferred" src/backend/apps/categories/catalog/categories.yaml   # 0 (clean state)
```
- `entrypoint-catalog.sh:17` — `exec ... manage.py load_catalog --no-rewrite`
- `load_catalog.py:36-39` — `slug_rename_map = builder.load_catalog(config_path, apps=None, rewrite_yaml=not no_rewrite)`
- `seed_service.py:277-279` — `load_catalog(CATALOG_PATH)` (default `rewrite_yaml=True`)
- `builder.py:56` — `rewrite_yaml: bool = True`; `builder.py:155-156` — `if slug_rename_map and rewrite_yaml: _rewrite_yaml(...)`.

**Recommendation:**
Make `SeedService._load_category_fixtures` call `load_catalog(CATALOG_PATH, rewrite_yaml=False)` to mirror the prod one-shot (or gate YAML rewriting behind an explicit admin command), so the canonical catalog file is mutated by exactly one code path. Priority: advisory.

---

### ENT-036: `load_exchange_rates` bootstrap is triplicated across prod, test entrypoint, and conftest

| Field | Value |
|-------|-------|
| **ID** | ENT-036 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `docker-compose.yml:35` (prod `migrate` one-shot), `docker/entrypoint-test.sh:22`, `src/backend/conftest.py:114`, `src/backend/apps/currencies/management/commands/load_exchange_rates.py:31-35` |
| **Classification** | advisory |
| **Status** | RESOLVED — `bootstrap_reference_data` management command created; prod compose + CI now invoke `manage.py bootstrap_reference_data`; test entrypoint consolidated to one call. Conftest retains in-process `call_command` for the `test_mko_bazuna` DB-name constraint. |

**Description:**
Exchange-rate seeding is invoked in three places with the same intent: (1) the prod `migrate` one-shot (`docker-compose.yml:35`), (2) `entrypoint-test.sh:22` (guarded with `|| true`), and (3) the pytest session fixture `conftest.py:114`. There is no single source of truth for "bootstrap exchange rates on startup," and the three call sites differ in error handling (prod is fail-closed via `&&`; test is `|| true`). If `INITIAL_RATES` (load_exchange_rates.py:31-35) gains a currency, all three must stay consistent by discipline; a drift (e.g., a rate added to the command but a stale cached state assumed by a future caller) would surface only at runtime. The single `INITIAL_RATES`/`EFFECTIVE_DATE`/`SOURCE` constants are defined once (load_exchange_rates.py:27-35), which mitigates content drift, but the *invocation* duplication remains operational overhead.

**Evidence:**
- `docker-compose.yml:35` — `... && python src/backend/manage.py load_exchange_rates`
- `entrypoint-test.sh:22` — `uv run python .../manage.py load_exchange_rates || true`
- `conftest.py:114` — `call_command("load_exchange_rates")`
- `load_exchange_rates.py:27-35` — single `INITIAL_RATES` definition (the shared source of truth).

**Recommendation:**
Encapsulate the bootstrap sequence in one function/command (e.g. a `bootstrap_reference_data` management command) invoked uniformly by the prod one-shot, the test entrypoint, and the conftest fixture, so error handling and the rate set are identical everywhere. Priority: advisory.

**Resolution:**
Implemented via Block 5. A new `bootstrap_reference_data` management command (`src/backend/apps/core/management/commands/bootstrap_reference_data.py`) delegates to `migrate_locked.main()`, which runs all three steps under the `MIGRATE` advisory lock. The four `python -c` call sites (docker-compose.yml:35, ci.yml:86, ci.yml:227, ci-nightly.yml:65) and the test entrypoint (entrypoint-test.sh) now use `manage.py bootstrap_reference_data`. Conftest.py retains in-process `call_command` calls under `TEST_SCHEMA_SETUP` (111) because `migrate_locked.main()` spawns subprocesses that would connect to the hardcoded `mko_bazuna` DB instead of `test_mko_bazuna`.

---

### ENT-037: conftest test schema-restore mirrors only the `migrate` one-shot, not the catalog one-shots

| Field | Value |
|-------|-------|
| **ID** | ENT-037 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/conftest.py:76-115` (esp. `:113-115`), `docker/entrypoint-test.sh:21-23`, `docker-compose.yml:31-135`, `src/backend/apps/seed/tests/conftest.py:36-46` |
| **Classification** | advisory |

**Description:**
The `_restore_test_schema_post_db_setup` session fixture (conftest.py:76-115) restores `migrate --run-syncdb`, `load_exchange_rates`, and `setup_search_triggers` — i.e., it mirrors only the prod `migrate` one-shot. It does **not** mirror the `load_catalog` one-shot (categories/lookups) or cities or `create_admin`. The entrypoint-test.sh (lines 21-22) likewise runs only `load_exchange_rates` + `setup_search_triggers`, with no `load_catalog`. Tests therefore depend on per-module `load_catalog(...)` calls (test_submenu.py:115, test_breadcrumbs_render.py:49-83, test_seed.py:1002/1362/1403/1478) and hand-built `Category`/`City` fixtures (conftest.py:144-157). This means the test harness does **not** exercise the real catalog-loading one-shot path against a clean DB, masking catalog-seeding regressions (such as ENT-031 itself) — exactly the blind spot this audit targets. The fixture doc-comment (conftest.py:68-73) claims to "restore that schema/data so the test DB mirrors production," but its restore set covers only exchange rates + triggers, not the catalog.

**Evidence:**
- `conftest.py:113-115` — only `call_command("migrate", "--run-syncdb")`, `call_command("load_exchange_rates")`, `call_command("setup_search_triggers")`.
- `conftest.py:68-73` doc — "restore trigger DDL + seed data that MIGRATION_MODULES=None skips" (rates+triggers only).
- `grep load_catalog` → callers are test files only, never conftest.py.
- `entrypoint-test.sh:22-23` — `load_exchange_rates || true` / `setup_search_triggers || true` (no `load_catalog`).

**Recommendation:**
Either add `load_catalog` to the test schema-restore set (loading the real `categories.yaml` for integration fidelity and to exercise the one-shot path under CI) or explicitly document that catalog data is intentionally test-local. Ensure at least one CI path runs the **real** `load_catalog` management command (not just the builder import) as a smoke test for the fresh-launch chain. Priority: advisory.

---

### ENT-038: `_load_city_fixtures` seeds cities with explicit PKs + `ignore_conflicts` and returns the entire table

| Field | Value |
|-------|-------|
| **ID** | ENT-038 |
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/seed/services/seed_service.py:285-307` (`_load_city_fixtures`), `src/backend/apps/seed/fixtures/cities.json:2-16` (explicit pk 1..15), `src/backend/apps/locations/migrations/0001_initial.py:16-22` (BigAutoField) |
| **Classification** | advisory |

**Description:**
`_load_city_fixtures` (seed_service.py:285-307) does `City.objects.bulk_create(objs, ignore_conflicts=True)` where each `obj` carries an **explicit primary key** (pk 1..15 from cities.json:2-16), then returns `list(City.objects.all())` — i.e., every city in the table, not just the 15 just seeded. Two issues: (1) `ignore_conflicts=True` silently skips rows whose PK already exists; `bulk_create` bypasses Django's sequence sync, so on a re-seed **after any external city insert** the explicit-PK inserts are skipped while the DB auto-increment sequence is **not** advanced, leaving the sequence trailing live data — a later `City.objects.create(...)` without an explicit pk can reuse pk 1..15 and raise `IntegrityError`. (2) Returning `City.objects.all()` (rather than the seeded subset) leaks pre-existing rows into the demo generator's city pool. While the demo-generator consumption is (B) test/demo seed, the *city-loading mechanics* — explicit PK + `ignore_conflicts` + bulk_create sequence drift — are (A) catalog reference data that must be safely re-loadable on every launch.

**Evidence:**
- `seed_service.py:301-307` — `City.objects.bulk_create(objs, ignore_conflicts=True)` ; `return list(City.objects.all())`
- `cities.json:2` — `{"pk": 1, "model": "locations.city", ...}` ... `cities.json:16` — `{"pk": 15, ...}`.
- `locations/migrations/0001_initial.py:16-22` — `BigAutoField` PK (sequence-backed).

**Recommendation:**
Drop the explicit `pk` from `cities.json` (let the DB assign PKs) and have `_load_city_fixtures` return only the seeded queryset (e.g. `City.objects.filter(pk__in=[...])`), so re-seed never leaves the sequence behind live data. If fixed PKs are retained for stability, sync the sequence after `bulk_create` (`setval`). Priority: advisory.

---

### ENT-039: `load_catalog` one-shot runs without an advisory lock (unlike migrate/create_admin/seed)

| Field | Value |
|-------|-------|
| **ID** | ENT-039 |
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `docker/entrypoint-catalog.sh:17`, `src/backend/apps/categories/management/commands/load_catalog.py:30-53`, `src/backend/apps/categories/catalog/builder.py:121` (`transaction.atomic()` only), `src/backend/apps/core/enums.py:23-42` (no catalog lock id), `src/backend/apps/core/utils/migrate_locked.py:33`, `src/backend/apps/core/management/commands/create_admin_user.py:75` |
| **Classification** | advisory |

**Description:**
`AdvisoryLockId` (core/enums.py:23-42) allocates session-scoped locks for `MIGRATE` (100), `CREATE_ADMIN` (101), `SEED` (110), and `TEST_SCHEMA_SETUP` (111). There is **no** lock id for the `load_catalog` one-shot, which runs unlocked (`entrypoint-catalog.sh:17`). The builder wraps each phase in `transaction.atomic()` (builder.py:121) — providing atomicity, not serialization — so a concurrent re-run of the `load_catalog` service (e.g., a retried container, or an operator re-running `make load-catalog` while one is in flight) could interleave `update_or_create` + MPTT `insert_at()` transactions and corrupt the MPTT tree (`lft`/`rght` integrity). Row-level idempotency protects individual rows, but MPTT tree rebuild is not row-atomic across concurrent transactions. In practice the service is single-shot and dependency-gated, so the risk is low; still, it is the one catalog one-shot without the lock discipline the other one-shots follow.

**Evidence:**
- `docker/entrypoint-catalog.sh:17` — `exec ... manage.py load_catalog --no-rewrite` (no lock).
- `builder.py:121` — `with transaction.atomic():` (atomicity only, no `advisory_lock`).
- `core/enums.py:23-42` — `AdvisoryLockId` members: ARCHIVE_SWEEP..ROLLUP..MIGRATE=100, CREATE_ADMIN=101, BACKFILL_THUMBNAILS=102, QUEUE_PROCESSING=10, PURGE_DELETED_ADS=11, RECOMPUTE_NORMALIZED_PRICES=12, SEED=110, TEST_SCHEMA_SETUP=111. No `CATALOG_LOAD`.
- `migrate_locked.py:33` / `create_admin_user.py:75` — the two other catalog one-shots ARE lock-guarded (contrast).

**Recommendation:**
Add a `CATALOG_LOAD` member to `AdvisoryLockId` and wrap `load_catalog` in `advisory_lock(CATALOG_LOAD, session=True)` (the builder already runs inside a transaction, so the lock is a thin, safe addition). Priority: advisory.

---

### ENT-040: `load_catalog` silently succeeds on an empty catalog YAML; no first-deploy verification

| Field | Value |
|-------|-------|
| **ID** | ENT-040 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/categories/catalog/builder.py:108-117` (empty-config no-op), `src/backend/apps/categories/management/commands/load_catalog.py:36-53` (unconditional success message), `docker-compose.yml:55-80` (load_catalog one-shot), `docker-compose.yml:142-144` & `:169-171` (web/bot depend on load_catalog) |
| **Classification** | advisory |

**Description:**
`builder.load_catalog` (builder.py:108-117) raises `FileNotFoundError` only when the config file is absent; if the YAML is present but empty/null (`_yaml.load` returns `None`), it logs a warning and `return {}` — i.e., **zero categories loaded, no error**. The `load_catalog` command (load_catalog.py:36-53) then prints `self.style.SUCCESS("Catalog loaded successfully — no renames")` regardless of how many rows were created. The Docker `load_catalog` one-shot (docker-compose.yml:55-80) therefore exits 0 on an empty catalog, and `web`/`bot` — which `depends_on: load_catalog condition: service_completed_successfully` (docker-compose.yml:142-144, 169-171) — start against a site with **zero categories**, silently breaking the entire listing/catalog UI on first launch. There is no post-load assertion that category rows actually exist. (This is the same class of gap that makes ENT-031 invisible to the one-shot chain.)

**Evidence:**
- `builder.py:108-109` — `if not config_path.exists(): raise FileNotFoundError(...)`
- `builder.py:114-117` — `if not data: logger.warning("Empty catalog config at %s", config_path); return {}` (silent no-op, no error).
- `load_catalog.py:51-52` — `self.style.SUCCESS("Catalog loaded successfully — no renames")` (success path taken even when `slug_rename_map` is empty AND no rows were loaded).
- `docker-compose.yml:62` / `:142-144` / `:169-171` — `load_catalog` completion gates web/bot startup.

**Recommendation:**
Add an explicit post-load guard in the `load_catalog` command: after `builder.load_catalog(...)`, assert `Category.objects.exists()` (and, once ENT-031 is fixed, `City.objects.exists()`) and `sys.exit(1)` if zero rows were loaded, so the one-shot **fails fast** and blocks web/bot startup instead of booting an empty catalog. Priority: advisory.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 2 |
| MEDIUM | 4 |
| LOW | 4 |
| **Total** | **10** |

## Mandatory Fixes

- **ENT-031** (HIGH): Load cities as catalog reference data via a non-profile-gated one-shot on the prod bootstrap chain (not the demo `seed` profile).
- **ENT-032** (HIGH): Remove the `:-admin` default from `docker-compose.yml:99` and `docker-compose.dev.override.yml:15` so an empty `ADMIN_PASSWORD` skips admin creation (fail-fast), per CFG-001.

## Advisory Recommendations

- **ENT-033** (MEDIUM): RESOLVED — `migrate_locked.main()` now runs all three steps inside the `MIGRATE` lock (no `&&` chain); `bootstrap_reference_data` command provides a single entrypoint.
- **ENT-034** (MEDIUM): Document the post-squash seeding contract and avoid an empty reference-data window after `migrate`; clean orphaned `__pycache__/0002_*.pyc`.
- **ENT-035** (MEDIUM): Make `SeedService._load_category_fixtures` call `load_catalog(..., rewrite_yaml=False)` to match the prod one-shot.
- **ENT-040** (MEDIUM): Add a post-load row-count guard to the `load_catalog` command (fail-fast on empty catalog).
- **ENT-036** (LOW): RESOLVED — `bootstrap_reference_data` management command replaces the triplicated invocation across prod compose, test entrypoint, and CI; conftest retains in-process calls for DB-name safety.
- **ENT-037** (LOW): Extend the conftest test-schema-restore to mirror the catalog one-shot (or document it as intentionally test-local); add a real-command smoke test.
- **ENT-038** (LOW): Drop explicit PKs from `cities.json` and return only the seeded city subset to avoid sequence drift.
- **ENT-039** (LOW): Add a `CATALOG_LOAD` advisory lock id and guard `load_catalog` with it.

## Doc Updates Needed

None required for this phase (findings reference existing docs; CFG-001 already documented in Phase 02). If ENT-031/ENT-035 are implemented, update `docs/ops/docker-deployment.md` catalog-deploy section to reflect the new cities one-shot and the `load_catalog` rewrite policy.
