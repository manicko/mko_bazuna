---
name: 05-catalog-seeding
phase: catalog-seeding
template: .ai/audit/templates/audit-findings.md
status: complete
validated: yes
validator: validator
validated_date: 2026-09-05
---

# Phase 05 Audit Findings — Catalog Seeding (VALIDATED)

**Executor:** audit-executor
**Template:** `.ai/audit/templates/audit-findings.md`
**Status:** complete
**Validated:** yes

**Scope:** CATALOG SEEDING (A) = production one-shot loading of reference data
required for a first deploy (categories, lookups, cities, exchange rates, admin
user). Excludes TEST SEED (B) = demo-data factories, `BaseGenerator`/`factory_boy`
generators, `AnalyticsGenerator`, and the demo ad/user/analytics pipeline. The
demo `seed` service loads reference data (cities, categories via `load_catalog`);
that reference-loading path is in scope, the demo-data generation itself is not.

> **Validator scope note:** This report validates the findings in
> `05-catalog-seeding/findings.md` (ENT-031..ENT-040) against the current working
> tree. Verification was static (grep + targeted source reads and git history) —
> no runtime/production deploy was exercised, matching the original audit's own
> scope disclaimer. No source code was modified. The earlier Phase 02
> (`02-config-secrets`) and Phase 01 (`01-entry-architecture`) validated reports
> in this same store were consulted for cross-phase conflict/merge analysis.

---

## Runtime Verification Evidence (static)

| # | Verification performed | Method | Result |
|---|---|---|---|
| R1 | One-shot commands present & registered | grep `BaseCommand` under `apps/**/management/commands` | `load_catalog`, `seed`, `load_exchange_rates`, `create_admin_user` all present (each `class Command(BaseCommand)`) |
| R2 | Reference-data seeded by migration vs command | grep `RunPython\|RunSQL` across `apps/**/migrations/*.py`; `git log -p -S` history | Only `core/0002_seed_default` (SiteConfig) + `ads/0001_initial` (trigger DDL) are data/migration seeded. `currencies/categories/lookups/locations` `0001` are schema-only |
| R3 | Cities loader location | grep `cities.json\|_load_city_fixtures\|load_cities` under `src/` | Only `seed_service.py` (lines 93, 285, 291); no command/migration loads cities |
| R4 | Builder catalog phases | read `builder.py:53-158` | Phases 1-4: LookupGroup+LookupItem → Category tree → bindings → CategoryPath. No cities phase |
| R5 | One-shot chain wiring | read `docker-compose.yml:31-135` | `migrate`→`load_catalog`→`create_admin`; `seed` profile-gated (`profiles: ["seed"]`); `web`/`bot` `depends_on load_catalog` |
| R6 | Dev vs prod seed gating | read `docker-compose.dev.override.yml:64-84` | Dev resets `profiles: !reset []` (seed auto-runs); prod keeps `profiles: ["seed"]` (opt-in) |
| R7 | Admin password default | read `docker-compose.yml:99`, `.env.docker.example:52-54`, `entrypoint-create-admin.sh:18` | `:-admin` default defeats the empty-skip guard |
| R8 | Advisory lock coverage | read `core/enums.py:23-42`, `migrate_locked.py:33`, `create_admin_user.py:75` | Locks: MIGRATE(100), CREATE_ADMIN(101), SEED(110), TEST_SCHEMA_SETUP(111). No lock for `load_catalog` |
| R9 | Test schema restore scope | read `conftest.py:76-115` | Restores only `migrate --run-syncdb` + `load_exchange_rates` + `setup_search_triggers`; not categories/cities/admin |
| R10 | Migration squash history | `git log --oneline`, `git log -p -S seed_initial_rates` (commits `4ea19cb`, `495bf74`) | Pre-squash `currencies/0001` had `seed_initial_rates` RunPython; squash regenerated `0001` without it |

All verifications PASS against the working tree. R2 additionally confirms via git
history that two of the ten claims rest on historical state that is no longer
present in the current `migrations/` source but was verifiably removed by the
squash (ENT-034).

---

## Per-Finding Verdict Summary

| ID | Title | Verdict | Evidence Quality | Issues / Notes |
|----|-------|---------|-------------------|----------------|
| ENT-031 | Cities not loaded on clean prod deploy | **VALIDATED** | High | All claims verified. Docs reference a non-existent `locations/0002_seed_cities.py` migration (stale) — corroborates the gap. Minor: affected-modules list cites `docker-compose.yml:108-135` for the seed service (accurate). |
| ENT-032 | `admin/admin` default credential | **MERGED** | High | Identical root cause to Phase 02 **CFG-001** (already validated). Merged into CFG-001; independent corroboration only. |
| ENT-033 | `migrate` `&&` chain couples DDL + trigger DDL + rates | **VALIDATED** | High | `docker-compose.yml:35` chain, `migrate_locked.py:33-37` lock scope, DDL/raw-cursor, prod vs test divergence all confirmed. Minor: "load_catalog, web, bot all depends_on migrate" is imprecise — web/bot depend on `load_catalog`, not `migrate` directly; the transitive cascade is still correct. |
| ENT-034 | Squash removed reference-data RunPython; command-only seeding | **VALIDATED** | High | Git history (`4ea19cb`→`495bf74`) verified; current `0001`s are schema-only; `core/0002_seed_default` is the lone survivor; orphaned `0002_*.pyc` confirmed on disk. Note: stale comment in `currencies/tests/conftest.py:6` still references the removed `seed_initial_rates`. |
| ENT-035 | `rewrite_yaml=True` default diverges from prod `--no-rewrite` | **VALIDATED** | High | `seed_service.py:279` default vs `entrypoint-catalog.sh:17 --no-rewrite` vs `builder.py:56/155-156` confirmed; `categories.yaml` verified clean (0 `new_slug`/`deferred`). Latent only. |
| ENT-036 | `load_exchange_rates` bootstrap triplicated | **VALIDATED** | High | Three call sites confirmed (`docker-compose.yml:35`, `entrypoint-test.sh:22`, `conftest.py:114`); `INITIAL_RATES` defined once. Error-handling differs (prod `&&` fail-closed vs test `|| true`). |
| ENT-037 | conftest schema-restore mirrors only `migrate` one-shot | **VALIDATED** | High | `conftest.py:113-115` restore set confirmed; no `load_catalog` in conftest (grep-verified). Per-module `load_catalog` callers confirmed. Minor: cited "affected module" `seed/tests/conftest.py:36-46` is actually the `ImageGenerator` no-op patch fixture — unrelated to catalog loading (mischaracterization, core claim intact). |
| ENT-038 | cities: explicit PK + `ignore_conflicts` + returns all rows | **VALIDATED** | High | `seed_service.py:306-307`, `cities.json` pk 1..15, `BigAutoField` PK confirmed. Minor: cited range `301-307` is slightly off (actual 306-307) — substance intact. |
| ENT-039 | `load_catalog` runs without an advisory lock | **VALIDATED** | High | `AdvisoryLockId` (no `CATALOG_LOAD`), `entrypoint-catalog.sh:17` unlocked, `builder.py:121` `transaction.atomic()` only; `migrate_locked.py:33` / `create_admin_user.py:75` confirmed lock-guarded (contrast). |
| ENT-040 | `load_catalog` silently succeeds on empty catalog YAML | **VALIDATED** | High | `builder.py:108-117` (no-op on empty/null), `load_catalog.py:51-52` (unconditional SUCCESS), `docker-compose.yml:62,142-144,169-171` gates confirmed. |

**Totals:** 9 VALIDATED · 0 WITHDRAWN · 1 MERGED.

---

## Cross-Finding Analysis

### Dependency Chains

| Finding | Depends on | Depends on by | Notes |
|---|---|---|---|
| ENT-031 | — | ENT-038 (mechanics), ENT-040 (guard) | Cities one-shot must reuse a corrected cities loader (see ENT-038) and the post-load row-count guard (see ENT-040). |
| ENT-038 | — | ENT-031 | The `load_cities` one-shot recommended by ENT-031 should adopt ENT-038's mechanical fix (no explicit PK / return only seeded subset) to avoid re-introducing sequence drift. |
| ENT-040 | — | ENT-031 | Once ENT-031 ships a cities one-shot, ENT-040's post-load guard should assert `City.objects.exists()` too. |
| ENT-033 | ENT-003 (Phase 01) | — | Convergent fix: moving `setup_search_triggers`+`load_exchange_rates` inside the MIGRATE lock in a single Python entrypoint resolves both the lock-scope race (ENT-003) and the `&&` coupling (ENT-033). |
| ENT-036 | — | ENT-033 | Triplication overlaps the `&&` chain (ENT-033); distinct root cause (DRY invocation vs shell chaining). |
| ENT-032 | CFG-001 (Phase 02) | — | Cross-phase merge (same root cause). |

### Conflicts Detected

- **ENT-033 vs Phase 01 ENT-003 (cross-phase):** Not a conflict — complementary. ENT-003 (Phase 01) addresses lock *scope* (post-migration steps released before the lock); ENT-033 addresses shell `&&` *coupling* and prod/test error-handling divergence. The phase 01 validator already treated the related Phase 01 findings (ENT-002/ENT-003) as "same Migration-Once Guarantee theme, different mechanisms, not merge candidates" — the same reasoning holds here. Convergent fix exists.

### Merges (cross-phase)

- **ENT-032 → CFG-001 (Phase 02):** Identical root cause — `ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin}` defeating the `entrypoint-create-admin.sh:18` empty-skip guard and booting an `admin`/`admin` superuser. CFG-001 was validated as mandatory HIGH in `02-config-secrets-validated-findings.md` with the identical recommendation (remove the `:-admin` default). No new fix is required in this phase; this finding is retained for reference and cross-referenced to CFG-001.

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

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Verified live against the working tree. `grep -rn "cities.json\|_load_city_fixtures\|load_cities" src/` returns only `seed_service.py` (lines 93, 285, 291). `_load_city_fixtures` is called solely from `SeedService.run()` (line 93), which is invoked solely by the `seed` management command (`apps/seed/management/commands/seed.py` — docstring states "development-only command"). The `seed` service is gated by `profiles: ["seed"]` (docker-compose.yml:113-114) and dev-only resets that profile to `profiles: !reset []` (docker-compose.dev.override.yml:69-70). `locations/migrations/0001_initial.py` is schema-only (creates the `cities` table, no `RunPython`). `builder.load_catalog` phases 1-4 are lookups → categories → bindings → category_paths — no cities phase. `cities.json` holds 15 Montenegro (`country_code="ME"`) cities with explicit pk 1..15. The docs reference an intended `locations/0002_seed_cities.py` migration that **does not exist** in the working tree (only `0001_initial.py` is present in `locations/migrations/`), corroborating that cities were never migration-seeded — they are coupled exclusively to the demo-seed path. The consequence (empty `cities` table on clean prod launch, breaking the city filter and the bot city-selection step) follows directly.
> - **Evidence Quality:** High. All cited paths/line refs verified exact.
> - **See also:** ENT-038 (city-loading mechanics), ENT-034 (post-squash seeding contract gap), ENT-040 (post-load guard).

**Description:**
On a fresh production launch the one-shot chain runs `migrate` (migrations + exchange rates + search triggers), `load_catalog` (categories + lookups + bindings + category_paths via `builder.load_catalog`), and `create_admin`. **Cities are loaded exclusively** by `SeedService._load_city_fixtures` (seed_service.py:285-307), which is invoked by the demo `seed` command — a service **gated behind `profiles: ["seed"]`** in production (docker-compose.yml:113-114). In dev the profile is reset (`profiles: !reset []`, docker-compose.dev.override.yml:69-70) so seed auto-runs; in prod it does not. No migration seeds cities (`locations/0001_initial.py` only creates the `cities` table, no `RunPython`), and `load_catalog`/`builder.load_catalog` have no cities phase (builder.py phases 1-4: lookups → categories → bindings → paths only). Consequently the `cities` table ships **empty** in production, breaking the city filter/selector and the bot's city-selection step on day one. `cities.json` (15 Montenegrin cities, seed_service.py:291) is reference data, not demo data, yet it is coupled to the demo-seed path.

**Evidence:**
- `grep -rn "cities.json\|_load_city_fixtures\|load_cities" src/` → only `seed_service.py` (lines 93, 285, 291).
- `docker-compose.yml:113-114` — `seed` service `profiles: ["seed"]` (opt-in in prod).
- `docker-compose.dev.override.yml:69-70` — `seed: profiles: !reset []` (auto-runs only in dev).
- `docker/entrypoint-catalog.sh:17` — `manage.py load_catalog --no-rewrite` (categories only; no cities).
- `builder.py:122-151` — `load_catalog` phases load Lookups, Category tree, bindings, paths; no city step.
- `locations/migrations/0001_initial.py` — `CreateModel City` (BigAutoField), no `operations` data seeding.
- `apps/seed/management/commands/seed.py:2` docstring: "development-only command."

**Recommendation:**
Add a `load_cities` reference-data loader (management command reusing `cities.json`) invoked by the same one-shot chain as `load_catalog`/`load_exchange_rates` — **not** gated behind the demo `seed` profile — so a clean production deploy always has cities. Treat cities as catalog reference data (A) independent of demo-data generation (B). This loader should adopt ENT-038's mechanical fix (no explicit PKs; return only the seeded subset) to avoid sequence drift. Effort: small. Priority: mandatory.

---

### ENT-032: `create_admin` one-shot boots superuser `admin/admin` via compose `:-admin` default

| Field | Value |
|-------|-------|
| **ID** | ENT-032 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `docker-compose.yml:99` (`ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin}`), `docker-compose.dev.override.yml:15`, `docker/entrypoint-create-admin.sh:17-21` (skip guard), `docker/entrypoint-create-admin.sh:23-27` (pass-through), `src/backend/apps/core/management/commands/create_admin_user.py:75` (lock), `:107-113` (superuser create), `.env.docker.example:52-54` |
| **Classification** | mandatory |

> **Validation Note:**
> - **Action:** merged
> - **Detail:** Independently re-verified against the working tree; every claim is accurate (`docker-compose.yml:99` = `ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin}`; `docker-compose.dev.override.yml:15` identical; `entrypoint-create-admin.sh:18` `if [ -z "${ADMIN_PASSWORD}" ]` skip-guard is bypassed by the non-empty `admin` default; `create_admin_user.py:75` wraps creation in `AdvisoryLockId.CREATE_ADMIN`; `create_admin_user.py:107-113` sets `is_staff=True, is_superuser=True`; `.env.docker.example:52-54` documents `ADMIN_PASSWORD=` empty). This is the **same root cause** as Phase 02 **CFG-001** (validated HIGH mandatory in `02-config-secrets-validated-findings.md`), with the identical recommendation (remove the `:-admin` default; fail fast on empty). Per cross-finding analysis this is a cross-phase duplicate and is **merged into CFG-001**; its content is retained here for traceability but no separate fix is required. (The evidence block's `docker compose config` output showing `ADMIN_PASSWORD: ""` for web/bot vs `admin` for the create_admin service corroborates the substitution behavior described in CFG-001.)
> - **Evidence Quality:** High — all sites verified exact.
> - **See also:** CFG-001 (Phase 02, `02-config-secrets-validated-findings.md`).

**Description:**
The `create_admin` one-shot is part of the clean-launch chain. `docker-compose.yml:99` sets `ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin}`, and the dev override mirrors it (docker-compose.dev.override.yml:15). `.env.docker.example:53` documents `ADMIN_PASSWORD=` (empty), intending the entrypoint skip-guard (`entrypoint-create-admin.sh:18`: `if [ -z "${ADMIN_PASSWORD}" ]`) to skip admin creation. But the `:-admin` substitution fires at Compose parse time **before** the entrypoint runs, turning empty→`admin` (non-empty), so the guard is never taken. `create_admin_user.py:107-113` then creates `is_staff=True, is_superuser=True` with username `admin`/password `admin`. Every other secret uses the fail-fast `${VAR:?…}` form; `ADMIN_PASSWORD` is the sole exception. A deploy that copies the example env boots an internet-facing `/admin/` superuser authenticated with `admin`/`admin`. Pre-existing, cross-referenced as **CFG-001** in Phase 02.

**Evidence:**
- `docker-compose.yml:99:  - ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin}`
- `docker-compose.dev.override.yml:15:  - ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin}`
- `docker/entrypoint-create-admin.sh:18:if [ -z "${ADMIN_PASSWORD}" ]; then  # never true once :-admin applies`
- `create_admin_user.py:107-113 — User.objects.create(..., is_staff=True, is_superuser=True)`
- `.env.docker.example:52-54 — ADMIN_USERNAME=admin, ADMIN_PASSWORD=, ADMIN_TELEGRAM_ID=-1`

**Consequence:** Full database read/write compromise via `/admin/` on any deploy that uses the documented (empty) default.

**Recommendation:** (Merged into CFG-001.) Remove the `:-admin` default so an unset `ADMIN_PASSWORD` fails fast and the entrypoint skip-guard is honored. No additional work in this phase.

---

### ENT-033: `migrate` one-shot couples schema DDL + search-trigger DDL + exchange-rate seeding via `&&`

| Field | Value |
|-------|-------|
| **ID** | ENT-033 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `docker-compose.yml:35` (migrate command), `src/backend/apps/core/utils/migrate_locked.py:33-37`, `src/backend/apps/currencies/management/commands/load_exchange_rates.py:46-79`, `src/backend/apps/ads/management/commands/setup_search_triggers.py:106-131`, `docker/entrypoint-test.sh:21-23` |
| **Classification** | advisory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Verified live. `docker-compose.yml:35` command is `bash -c "python -c '...migrate_locked.main()...' && python src/backend/manage.py setup_search_triggers && python src/backend/manage.py load_exchange_rates"`. `migrate_locked.py:33-37` confirms the `AdvisoryLockId.MIGRATE` (100) session lock wraps only the `subprocess.run([... "migrate", "--noinput", "--run-syncdb"])` call and returns immediately after, releasing the lock before the `&&`-chained steps. `setup_search_triggers.py:114-123` executes raw DDL via `connection.cursor()` (`CREATE OR REPLACE FUNCTION`, `DROP TRIGGER IF EXISTS`/`CREATE TRIGGER`) — DDL that is idempotent but not concurrency-safe. `load_exchange_rates.py:50-59` updates `ExchangeRate` rows. The `&&` coupling means a `setup_search_triggers` failure aborts `load_exchange_rates`, starving the `exchange_rates` table on a fresh DB. Prod/test divergence confirmed: `entrypoint-test.sh:21-23` runs the same three steps each guarded with `|| true` (and in a different order: rates then triggers), so the prod fail-closed chain and the test ignore-each-step paths can silently diverge. Minor: "load_catalog, web, and bot all depends_on: migrate condition: service_completed_successfully (docker-compose.yml:62, 142-144, 169-171)" is imprecise — web/bot depend on `load_catalog`, not `migrate` directly (load_catalog depends on migrate at :60-62); the transitive cascade described (migrate failure blocks load_catalog, which blocks web/bot) is still correct.
> - **Evidence Quality:** High.
> - **See also:** ENT-003 (Phase 01, lock-scope race), ENT-036 (load_exchange_rates invocation duplication).

**Description:**
The prod `migrate` one-shot command is a single `&&` chain:
```
python -c '...migrate_locked.main()...' && python src/backend/manage.py setup_search_triggers && python src/backend/manage.py load_exchange_rates
```
`migrate_locked.main()` (migrate_locked.py:33-37) runs `manage.py migrate --run-syncdb` **inside** the `AdvisoryLockId.MIGRATE` (100) session lock, but `setup_search_triggers` and `load_exchange_rates` execute **after** that lock releases — outside any transaction or guard, and outside the lock. The `&&` coupling means **a failure in `setup_search_triggers` aborts `load_exchange_rates`**: on a fresh DB the `exchange_rates` table is created empty by the migration (currencies/0001_initial.py, no `RunPython`), so if the trigger-DDL step errors, currency reference data is never seeded and every non-EUR `price_normalized_eur` lookup fails. Because `load_catalog`, `web`, and `bot` all `depends_on: load_catalog condition: service_completed_successfully` which itself depends on `migrate` (docker-compose.yml:60-62, 142-144, 169-171), a trigger-creation failure also cascades and blocks the entire catalog/site launch. The test entrypoint (entrypoint-test.sh:21-23) is more resilient — it guards each step with `|| true` — so the prod/test paths diverge in error handling.

**Evidence:**
- `docker-compose.yml:35` — `command: bash -c "...migrate_locked... && ...setup_search_triggers && ...load_exchange_rates"`
- `migrate_locked.py:33-37` — lock wraps only `manage.py migrate --run-syncdb`.
- `entrypoint-test.sh:21-23` — `migrate --run-syncdb || {...}`; `load_exchange_rates || true`; `setup_search_triggers || true`.

**Recommendation:**
Decouple reference-data seeding from DDL: run `load_exchange_rates` independently of `setup_search_triggers` (and optionally under its own guard), so trigger-failure cannot starve the currency table. Standardize prod/test error handling so the two entrypoints can't silently diverge. Priority: advisory. (A single locked Python entrypoint covering all three steps would additionally resolve Phase 01 ENT-003.)

---

### ENT-034: Migration squash removed reference-data RunPython; seeding now lives only in post-migrate commands

| Field | Value |
|-------|-------|
| **ID** | ENT-034 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/currencies/migrations/0001_initial.py` (now schema-only), `src/backend/apps/currencies/management/commands/load_exchange_rates.py:1-8` (docstring), `src/backend/apps/categories/migrations/0001_initial.py`, `src/backend/apps/lookups/migrations/0001_initial.py`, `src/backend/apps/core/migrations/0002_seed_default.py`, git history `495bf74`, `4ea19cb`; orphaned `__pycache__/0002_*.pyc`; stale comment `currencies/tests/conftest.py:6` |
| **Classification** | advisory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Verified via git history. `git log` confirms commit `4ea19cb` ("feat(currency): multi-currency price normalization with EUR default") created `currencies/migrations/0001_initial.py` **with** a `seed_initial_rates` `RunPython` (seeds EUR/BAM/RSD) and `remove_initial_rates` reverse; `git log -p -S "seed_initial_rates"` shows commit `495bf74` ("T4g: squash migrations — 39 files to 10 initial migrations") **deleted** that `RunPython` operation (the diff shows `migrations.RunPython(seed_initial_rates, remove_initial_rates)` removed) and regenerated a schema-only `0001_initial`. The current `currencies/0001_initial.py` has only `operations = [migrations.CreateModel(name="ExchangeRate", ...)]` — confirmed. Same for `categories/0001_initial.py`, `lookups/0001_initial.py`, `locations/0001_initial.py` (all schema-only, no `RunPython`/`RunSQL`). The lone surviving reference-data migration is `core/0002_seed_default.py` (`seed_site_config` RunPython, creates `SiteConfig` singleton) — an inconsistent strategy where SiteConfig is migration-seeded and everything else is command-seeded. `load_exchange_rates.py:3-7` docstring explicitly documents the post-squash command-based seeding ("RunPython data migrations such as seed_initial_rates cannot be regenerated... This command recreates the fixed initial rates idempotently"). Orphaned `__pycache__/0002_*.pyc` confirmed on disk: `currencies/migrations/__pycache__/0002_alter_exchangerate_created_at_and_more.cpython-314.pyc` and `categories/migrations/__pycache__/0002_categorylistingcondition.cpython-314.pyc` (dated after the squash). The `currencies` app has no `0002` migration source file, confirming these are stale bytecode artifacts. Additional: `currencies/tests/conftest.py:6` contains a stale comment referencing "the `seed_initial_rates` RunPython in `0001_initial`" — which no longer exists — a minor documentation-drift signal that corroborates the post-squash state. (Not added as a standalone finding: it is a single comment, out of scope for this phase's one-shot/cities focus, but noted here.)
> - **Evidence Quality:** High (git history + working tree verified).
> - **See also:** ENT-031 (cities gap), ENT-033 (command-based seeding in the `&&` chain).

**Description:**
The pre-squash `currencies/0001_initial.py` (commit `4ea19cb feat(currency)`) contained a `seed_initial_rates` `RunPython` that seeded EUR/BAM/RSD. The migration squash (`495bf74 "T4g: squash migrations — 39 files to 10 initial migrations"`) regenerated `0001_initial` **without** the `RunPython` — only `CreateModel ExchangeRate` — and folded the old `0002_*` files into the new `0001` (old files deleted). The `load_exchange_rates` command docstring explicitly documents this: RunPython data migrations cannot be regenerated after a squash. Net effect: on a fresh DB the migrations create the `exchange_rates`, `lookup_items`, `lookup_groups`, and `categories` tables but populate **zero rows**; reference data exists only after the post-migrate one-shot commands run. The only surviving reference-data migration is `core/0002_seed_default` (SiteConfig) — an **inconsistent strategy** where some reference data is migration-seeded (SiteConfig) and the rest is command-seeded (rates/cities/categories), with no documented contract for the gap. Orphaned `.pyc` for the deleted `0002_*` migrations linger in `__pycache__`.

**Evidence:**
- `git show 4ea19cb:src/backend/apps/currencies/migrations/0001_initial.py` → defines `seed_initial_rates` + `remove_initial_rates` `RunPython` in `operations`.
- current `currencies/migrations/0001_initial.py` → only `operations = [migrations.CreateModel(name="ExchangeRate", ...)]`, no `RunPython`.
- current `categories/migrations/0001_initial.py` and `lookups/migrations/0001_initial.py` → `CreateModel` only, no `RunPython`.
- `load_exchange_rates.py:3-7` (docstring) → explains post-squash command-based seeding.
- `core/migrations/0002_seed_default.py:6-17` → the lone surviving reference-data `RunPython` (`seed_site_config`).
- `git show 495bf74 --stat` → lists `currencies/0002_alter...` and `categories/0002_categorylistingcondition` as deleted; `__pycache__/0002_*.cpython-314.pyc` remain on disk.

**Recommendation:**
Document the post-squash seeding contract explicitly (migrations build schema; one-shot commands seed reference data on first deploy). Consider seeding the EUR base rate (`rate_to_eur=1.0`) in a data migration so `price_normalized_eur` never hits an empty table between `migrate` and `load_exchange_rates`. Remove orphaned `__pycache__/0002_*.pyc`. Priority: advisory.

---

### ENT-035: `rewrite_yaml=True` default in `SeedService._load_category_fixtures` diverges from the prod `--no-rewrite` one-shot

| Field | Value |
|-------|-------|
| **ID** | ENT-035 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/seed/services/seed_service.py:277-279`, `src/backend/apps/categories/catalog/builder.py:53-57` (`rewrite_yaml: bool = True`), `builder.py:153-156`, `docker/entrypoint-catalog.sh:17` (`--no-rewrite`), `src/backend/apps/categories/management/commands/load_catalog.py:36-39` |
| **Classification** | advisory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Verified live. `builder.py:53-57` signature is `load_catalog(config_path, apps=None, rewrite_yaml: bool = True)`. `seed_service.py:277-279` calls `load_catalog(CATALOG_PATH)` with no `rewrite_yaml` arg → default `True`. `docker/entrypoint-catalog.sh:17` runs `manage.py load_catalog --no-rewrite`, and `load_catalog.py:36-39` maps `--no-rewrite` to `rewrite_yaml=not no_rewrite` = `False`. `builder.py:155-156` only rewrites when `slug_rename_map and rewrite_yaml`. A repo-wide grep confirms `categories.yaml` has zero `new_slug`/`deferred` entries, so the divergence is currently latent (no rewrites occur). The fix is sound and small.
> - **Evidence Quality:** High.
> - **See also:** ENT-031 (cities loader in the same demo-seed path).

**Description:**
The production `load_catalog` one-shot passes `--no-rewrite`, so `load_catalog.py:38-39` calls `builder.load_catalog(config_path, apps=None, rewrite_yaml=False)` (builder.py:56 default is `True`, overridden to `False`). But `SeedService._load_category_fixtures` (seed_service.py:277-279) calls `load_catalog(CATALOG_PATH)` with the **default `rewrite_yaml=True`**. So the demo seed mutates the canonical `categories.yaml` on disk whenever a `new_slug` rename exists, whereas the prod chain never rewrites it. The catalog is currently clean (grep finds zero `new_slug` / `deferred` entries in categories.yaml), so the divergence is latent — but any future rename turns the YAML into a source of truth that two code paths treat inconsistently (prod assumes immutable; demo seed rewrites it), risking merge conflicts and a drifted canonical config. `builder._rewrite_yaml` (builder.py:536-644) writes to a temp file then `os.replace`s the original.

**Evidence:**
- `entrypoint-catalog.sh:17` — `exec ... manage.py load_catalog --no-rewrite`
- `load_catalog.py:36-39` — `slug_rename_map = builder.load_catalog(config_path, apps=None, rewrite_yaml=not no_rewrite)`
- `seed_service.py:277-279` — `load_catalog(CATALOG_PATH)` (default `rewrite_yaml=True`)
- `builder.py:56` — `rewrite_yaml: bool = True`; `builder.py:155-156` — `if slug_rename_map and rewrite_yaml: _rewrite_yaml(...)`.
- `grep -rc "new_slug\|deferred" .../categories.yaml` → 0 (clean state).

**Recommendation:**
Make `SeedService._load_category_fixtures` call `load_catalog(CATALOG_PATH, rewrite_yaml=False)` to mirror the prod one-shot (or gate YAML rewriting behind an explicit admin command), so the canonical catalog file is mutated by exactly one code path. Priority: advisory.

---

### ENT-036: `load_exchange_rates` bootstrap is triplicated across prod, test entrypoint, and conftest

| Field | Value |
|-------|-------|
| **ID** | ENT-036 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `docker-compose.yml:35` (prod `migrate` one-shot), `docker/entrypoint-test.sh:22`, `src/backend/conftest.py:114`, `src/backend/apps/currencies/management/commands/load_exchange_rates.py:27-35` |
| **Classification** | advisory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Verified. `load_exchange_rates` is invoked from exactly three sites: `docker-compose.yml:35` (prod `migrate` `&&` chain, fail-closed), `entrypoint-test.sh:22` (`|| true`, ignore), `conftest.py:114` (`call_command("load_exchange_rates")` inside the `TEST_SCHEMA_SETUP` lock). The shared `INITIAL_RATES`/`EFFECTIVE_DATE`/`SOURCE` constants are defined once at `load_exchange_rates.py:27-35`. Error handling genuinely differs across sites (prod `&&` fail-closed vs test `|| true`), so the "operational overhead / divergence risk" claim is real. ROI is low-to-moderate; the command exists as the single source of truth for rate *content*, so this is purely an invocation-consolidation improvement. Not rejected as low-ROI: the divergence is a real latent hazard (a future caller could drift).
> - **Evidence Quality:** High.
> - **See also:** ENT-033 (the prod `&&` chain).

**Description:**
Exchange-rate seeding is invoked in three places with the same intent: (1) the prod `migrate` one-shot (docker-compose.yml:35), (2) `entrypoint-test.sh:22` (guarded with `|| true`), and (3) the pytest session fixture `conftest.py:114`. There is no single source of truth for "bootstrap exchange rates on startup," and the three call sites differ in error handling (prod is fail-closed via `&&`; test is `|| true`). If `INITIAL_RATES` (load_exchange_rates.py:27-35) gains a currency, all three must stay consistent by discipline; a drift would surface only at runtime. The single `INITIAL_RATES`/`EFFECTIVE_DATE`/`SOURCE` constants are defined once, which mitigates content drift, but the *invocation* duplication remains operational overhead.

**Evidence:**
- `docker-compose.yml:35` — `... && python src/backend/manage.py load_exchange_rates`
- `entrypoint-test.sh:22` — `uv run python .../manage.py load_exchange_rates || true`
- `conftest.py:114` — `call_command("load_exchange_rates")`
- `load_exchange_rates.py:27-35` — single `INITIAL_RATES` definition.

**Recommendation:**
Encapsulate the bootstrap sequence in one function/command (e.g. a `bootstrap_reference_data` management command) invoked uniformly by the prod one-shot, the test entrypoint, and the conftest fixture, so error handling and the rate set are identical everywhere. Priority: advisory.

---

### ENT-037: conftest test schema-restore mirrors only the `migrate` one-shot, not the catalog one-shots

| Field | Value |
|-------|-------|
| **ID** | ENT-037 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/conftest.py:76-115` (esp. `:113-115`), `docker/entrypoint-test.sh:21-23`, `docker-compose.yml:31-135`, per-module callers `categories/tests/test_submenu.py:115`, `ads/tests/test_breadcrumbs_render.py:49-83`, `seed/tests/test_seed.py:1002/1362/1403/1478` |
| **Classification** | advisory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Verified. `conftest.py:107` acquires `AdvisoryLockId.TEST_SCHEMA_SETUP` (111), then `:113-115` runs `call_command("migrate", "--run-syncdb")`, `call_command("load_exchange_rates")`, `call_command("setup_search_triggers")` only — no `load_catalog`, no cities, no `create_admin`. A repo-wide grep confirms `load_catalog` is **never** called from `conftest.py` (callers are test files only: `test_submenu.py:115`, `test_breadcrumbs_render.py:83` via a `_load_catalog` helper at line 49, and `test_seed.py` at 1002/1362/1403/1478). `entrypoint-test.sh:21-23` mirrors the same three-step restore (no `load_catalog`). The fixture doc-comment at `conftest.py:68-73` claims the restore makes the test DB "mirror production," but the restore set covers only exchange rates + triggers, not the catalog — a real fidelity gap that masks catalog-seeding regressions like ENT-031. Minor evidence-quality issue: the original "affected modules" list cites `seed/tests/conftest.py:36-46`, but that file is the `_no_op_image_generator` autouse fixture (a `patch` of `ImageGenerator`), **not** a catalog-loading fixture — a mischaracterization that does not affect the core claim. Also, the citation `conftest.py:68-73` doc-comment is accurate (lines 67-73).
> - **Evidence Quality:** High (core claim) / Medium (one misattributed affected module).
> - **See also:** ENT-031, ENT-034, ENT-036 (test/prod bootstrap parity).

**Description:**
The `_restore_test_schema_post_db_setup` session fixture (conftest.py:76-115) restores `migrate --run-syncdb`, `load_exchange_rates`, and `setup_search_triggers` — i.e., it mirrors only the prod `migrate` one-shot. It does **not** mirror the `load_catalog` one-shot (categories/lookups) or cities or `create_admin`. The `entrypoint-test.sh` (lines 21-22) likewise runs only `load_exchange_rates` + `setup_search_triggers`, with no `load_catalog`. Tests therefore depend on per-module `load_catalog(...)` calls (test_submenu.py:115, test_breadcrumbs_render.py:49-83, test_seed.py:1002/1362/1403/1478) and hand-built `Category`/`City` fixtures (conftest.py:144-157). This means the test harness does **not** exercise the real catalog-loading one-shot path against a clean DB, masking catalog-seeding regressions (such as ENT-031 itself) — exactly the blind spot this audit targets. The fixture doc-comment (conftest.py:68-73) claims to "restore that schema/data so the test DB mirrors production," but its restore set covers only exchange rates + triggers, not the catalog.

**Evidence:**
- `conftest.py:113-115` — only `call_command("migrate", "--run-syncdb")`, `call_command("load_exchange_rates")`, `call_command("setup_search_triggers")`.
- `conftest.py:68-73` doc — "restore trigger DDL + seed data that MIGRATION_MODULES=None skips" (rates+triggers only).
- grep `load_catalog` → callers are test files only, never conftest.py.
- `entrypoint-test.sh:22-23` — `load_exchange_rates || true` / `setup_search_triggers || true` (no `load_catalog`).

**Recommendation:**
Adopt Approach B (document as intentionally test-local) — do NOT extend the restore set. Add the real-command smoke test. Concrete changes:
1. **Document the deviation in conftest.py:68-73** — append to the existing session-restore doc-comment that the restore mirrors ONLY the prod `migrate` one-shot (`migrate --run-syncdb` + `load_exchange_rates` + `setup_search_triggers`) and that catalog/cities/admin data is deliberately loaded per-class by the tests that need it, not at session scope. The comment currently claims to make the test DB "mirror production" (conftest.py:68-73, R9), but restores rates+triggers only; make that scope explicit so the claim is truthful rather than silently expanded.
2. **Do NOT add `load_catalog` to `_restore_test_schema_post_db_setup`** (conftest.py:115) — the fixture commits directly (`call_command`, no `transaction.atomic`/rollback); a committed full catalog would hit the documented `slug: "transport"` collision: `test_submenu.py:22` creates `Category(slug="transport")`, which is a real catalog root (test_seed.py:1383 asserts `transport` is a non-leaf). `test_breadcrumbs_render.py:52-63` confirms this is why catalog loading is wrapped in `atomic()`+`set_rollback` per-class (rows must not leak across classes/xdist workers). Refactoring the 5 per-class callers (test_submenu.py, test_breadcrumbs_render.py, test_seed.py x3) plus the colliding `tree` fixture to tolerate a committed catalog is higher-risk than the parity this finding demands, and violates proj. rule #5 (avoid overengineering).
3. **Add a focused smoke test** — a new test that calls the REAL `manage.py load_catalog --no-rewrite` management command (not `builder.load_catalog`, which every existing caller uses) against a clean test DB, asserting `Category.objects.exists()` and a non-empty `LookupItem` count. Reason: grep confirms ZERO `call_command("load_catalog")` sites (all callers import `apps.categories.catalog.builder.load_catalog` directly); the prod `entrypoint-catalog.sh:17` command path is therefore never exercised under CI — this is the genuine, verified fidelity gap. The command is safe in CI: it uses `update_or_create` throughout (idempotent) and resolves `categories.yaml` from its own module path (`load_catalog.py:9`), so it has no settings dependency.

> **Resolution Rationale (researched against the working tree):**
> Approach A fails the collision constraint documented in `test_breadcrumbs_render.py:52-63` and would require refactoring 5 per-class fixture call sites + the colliding `tree` fixture — a higher-risk change than the prior effort sizing (line 490: "small") anticipated. Approach B preserves the test authors' deliberate atomic/rollback isolation, corrects the doc-comment so it no longer over-claims "mirrors production" for data it does not restore, and closes the real gap (the `load_catalog` management command is never run under CI — all callers use the builder function) with one low-risk smoke test. Aligns with proj. rules #2 (production code is king) and #5 (avoid overengineering). Confidence: HIGH — the slug collision, the per-class atomic/rollback pattern, and the all-builder-import call sites are verified in source.

Priority: advisory. Effort: small.

---

### ENT-038: `_load_city_fixtures` seeds cities with explicit PKs + `ignore_conflicts` and returns the entire table

| Field | Value |
|-------|-------|
| **ID** | ENT-038 |
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/seed/services/seed_service.py:285-307` (`_load_city_fixtures`), `src/backend/apps/seed/fixtures/cities.json:2-16` (explicit pk 1..15), `src/backend/apps/locations/migrations/0001_initial.py:16-22` (BigAutoField) |
| **Classification** | advisory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Verified. `seed_service.py:306` `City.objects.bulk_create(objs, ignore_conflicts=True)` and `:307` `return list(City.objects.all())`. `cities.json` lines 2-16 carry explicit `"pk": 1..15`; `locations/0001_initial.py:16-22` defines `id` as `BigAutoField` (sequence-backed). `bulk_create` with explicit PKs does **not** advance the PostgreSQL sequence, and `ignore_conflicts=True` silently skips already-present PKs — so after an external city insert the sequence is left trailing live data and a subsequent `City.objects.create()` (no explicit pk) can collide and raise `IntegrityError`; Django's `seed_initial_rates`-style hazard. Returning `City.objects.all()` (rather than the seeded subset) is also confirmed at line 307: the demo `AdGenerator` receives the full city pool, not just the 15 just seeded. Minor: cited line range `301-307` is slightly off (the `bulk_create` is at line 306, `return` at 307). The mechanic claims are technically sound.
> - **Evidence Quality:** High.
> - **See also:** ENT-031 (cities loader in the demo-seed path); recommendation is to reuse a corrected loader for any new `load_cities` one-shot.

**Description:**
`_load_city_fixtures` (seed_service.py:285-307) does `City.objects.bulk_create(objs, ignore_conflicts=True)` where each `obj` carries an **explicit primary key** (pk 1..15 from cities.json:2-16), then returns `list(City.objects.all())` — i.e., every city in the table, not just the 15 just seeded. Two issues: (1) `ignore_conflicts=True` silently skips rows whose PK already exists; `bulk_create` bypasses Django's sequence sync, so on a re-seed **after any external city insert** the explicit-PK inserts are skipped while the DB auto-increment sequence is **not** advanced, leaving the sequence trailing live data — a later `City.objects.create()` without an explicit pk can reuse pk 1..15 and raise `IntegrityError`. (2) Returning `City.objects.all()` (rather than the seeded subset) leaks pre-existing rows into the demo generator's city pool. While the demo-generator consumption is (B) test/demo seed, the *city-loading mechanics* — explicit PK + `ignore_conflicts` + bulk_create sequence drift — are (A) catalog reference data that must be safely re-loadable on every launch.

**Evidence:**
- `seed_service.py:306-307` — `City.objects.bulk_create(objs, ignore_conflicts=True)` ; `return list(City.objects.all())`
- `cities.json:2` — `{"pk": 1, "model": "locations.city", ...}` ... `cities.json:16` — `{"pk": 15, ...}`.
- `locations/migrations/0001_initial.py:16-22` — `BigAutoField` PK (sequence-backed).

**Recommendation:**
Drop the explicit `pk` from `cities.json` (let the DB assign PKs) and have `_load_city_fixtures` return only the seeded queryset (e.g. `City.objects.filter(pk__in=[...])`), so re-seed never leaves the sequence behind live data. If fixed PKs are retained for stability, sync the sequence after `bulk_create` (`setval`). Any new `load_cities` one-shot (ENT-031) should reuse this corrected loader. Priority: advisory.

---

### ENT-039: `load_catalog` one-shot runs without an advisory lock (unlike migrate/create_admin/seed)

| Field | Value |
|-------|-------|
| **ID** | ENT-039 |
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `docker/entrypoint-catalog.sh:17`, `src/backend/apps/categories/management/commands/load_catalog.py:30-53`, `src/backend/apps/categories/catalog/builder.py:121` (`transaction.atomic()` only), `src/backend/apps/core/enums.py:23-42` (no catalog lock id), `src/backend/apps/core/utils/migrate_locked.py:33`, `src/backend/apps/core/management/commands/create_admin_user.py:75` |
| **Classification** | advisory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Verified. `AdvisoryLockId` (core/enums.py:23-42) members are ARCHIVE_SWEEP=1..ROLLUP_DAILY_METRICS=8, ALERT_DELIVERY_TASK=9, MIGRATE=100, CREATE_ADMIN=101, BACKFILL_THUMBNAILS=102, QUEUE_PROCESSING=10, PURGE_DELETED_ADS=11, RECOMPUTE_NORMALIZED_PRICES=12, SEED=110, TEST_SCHEMA_SETUP=111 — no `CATALOG_LOAD`. `docker/entrypoint-catalog.sh:17` runs `manage.py load_catalog --no-rewrite` with no lock. `builder.py:121` wraps each phase in `transaction.atomic()` only (atomicity, not serialization); `migrate_locked.py:33` (`MIGRATE`, 100) and `create_admin_user.py:75` (`CREATE_ADMIN`, 101) are lock-guarded — the contrast is real. The MPTT `insert_at()` interleave risk under concurrent re-runs is accurate: row-level idempotency protects individual rows, but MPTT tree rebuild is not row-atomic across concurrent transactions. The "low risk in practice" qualifier is fair (single-shot, dependency-gated) but the lock-discipline gap is genuine. Adding a `CATALOG_LOAD` lock id is a small, non-breaking change. Not rejected.
> - **Evidence Quality:** High.
> - **See also:** ENT-031 (if a new cities one-shot is added, it should share the `CATALOG_LOAD` lock scope if it mutates the MPTT tree; cities are a flat table so a cities one-shot is lower-risk but still benefits from the lock for consistency with the other one-shots).

**Description:**
`AdvisoryLockId` (core/enums.py:23-42) allocates session-scoped locks for `MIGRATE` (100), `CREATE_ADMIN` (101), `SEED` (110), and `TEST_SCHEMA_SETUP` (111). There is **no** lock id for the `load_catalog` one-shot, which runs unlocked (`entrypoint-catalog.sh:17`). The builder wraps each phase in `transaction.atomic()` (builder.py:121) — providing atomicity, not serialization — so a concurrent re-run of the `load_catalog` service (e.g., a retried container, or an operator re-running `make load-catalog` while one is in flight) could interleave `update_or_create` + MPTT `insert_at()` transactions and corrupt the MPTT tree (`lft`/`rght` integrity). Row-level idempotency protects individual rows, but MPTT tree rebuild is not row-atomic across concurrent transactions. In practice the service is single-shot and dependency-gated, so the risk is low; still, it is the one catalog one-shot without the lock discipline the other one-shots follow.

**Evidence:**
- `docker/entrypoint-catalog.sh:17` — `exec ... manage.py load_catalog --no-rewrite` (no lock).
- `builder.py:121` — `with transaction.atomic():` (atomicity only, no `advisory_lock`).
- `core/enums.py:23-42` — `AdvisoryLockId` members: ARCHIVE_SWEEP..ROLLUP_DAILY_METRICS, ALERT_DELIVERY_TASK, MIGRATE=100, CREATE_ADMIN=101, BACKFILL_THUMBNAILS=102, QUEUE_PROCESSING=10, PURGE_DELETED_ADS=11, RECOMPUTE_NORMALIZED_PRICES=12, SEED=110, TEST_SCHEMA_SETUP=111. No `CATALOG_LOAD`.
- `migrate_locked.py:33` / `create_admin_user.py:75` — the two other one-shots ARE lock-guarded (contrast).

**Recommendation:**
Add a `CATALOG_LOAD` member to `AdvisoryLockId` and wrap `load_catalog` in `advisory_lock(CATALOG_LOAD, session=True)` (the builder already runs inside a transaction, so the lock is a thin, safe addition). Guard any new `load_cities` one-shot (ENT-031) with the same lock. Priority: advisory.

---

### ENT-040: `load_catalog` silently succeeds on an empty catalog YAML; no first-deploy verification

| Field | Value |
|-------|-------|
| **ID** | ENT-040 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/categories/catalog/builder.py:108-117` (empty-config no-op), `src/backend/apps/categories/management/commands/load_catalog.py:36-53` (unconditional success message), `docker-compose.yml:55-80` (load_catalog one-shot), `docker-compose.yml:60-62` & `:142-144` & `:169-171` (load_catalog→web/bot gates) |
| **Classification** | advisory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Verified. `builder.py:108-109` raises `FileNotFoundError` only when `config_path` does not exist; `builder.py:114-117` logs a warning and `return {}` when `_yaml.load(f)` returns `None`/empty — a silent no-op with no error. `load_catalog.py:42-52` prints `self.style.SUCCESS("Catalog loaded successfully — no renames")` whenever `slug_rename_map` is empty (line 51-52), regardless of how many rows were actually written — the "success" message fires even when zero rows were loaded. `docker-compose.yml:60-62` makes `load_catalog` depend on `migrate` (service_completed_successfully); `:142-144` (web) and `:169-171` (bot) both depend on `load_catalog` (service_completed_successfully). So an empty catalog exits 0 and boots web/bot against zero categories. No post-load assertion exists. The finding is accurate and the "same class of gap that makes ENT-031 invisible" framing is correct.
> - **Evidence Quality:** High.
> - **See also:** ENT-031 (cities one-shot should be asserted too), ENT-037 (test harness never runs the real `load_catalog` command, so the empty-catalog path is untested).

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

## Cross-Finding Analysis — Rollout Safety

### Circular Dependencies

No circular dependencies detected. ENT-031/ENT-038/ENT-039/ENT-040 all touch the catalog one-shots but introduce no cycles. ENT-032 is merged into the already-validated CFG-001 (no new cycle).

### Hidden Dependency Chains

- **ENT-031 → ENT-038 (mechanics):** The new `load_cities` one-shot recommended by ENT-031 must reuse a *corrected* cities loader — not `SeedService._load_city_fixtures` as-is, which carries the explicit-PK/sequence-drift and return-all-table issues (ENT-038). Implementing ENT-031 without ENT-038's mechanical fix would re-introduce sequence drift on every prod re-run.
- **ENT-031 → ENT-040 (guard):** ENT-040's post-load row-count assertion should include `City.objects.exists()` once the cities one-shot ships, so an empty `cities.json` also fails fast.
- **ENT-033 → ENT-003 (Phase 01, shared mechanism):** Both concern the `migrate` one-shot's post-migration steps running outside the `MIGRATE` lock. Phase 01's recommendation (move all three steps inside the lock in a single Python entrypoint) is a *superset* fix that also resolves ENT-033's `&&` coupling. Not a dependency — applying either is strictly safer; applying both is convergent.
- **ENT-036 → ENT-033 (call-site overlap):** The proposed `bootstrap_reference_data` command (ENT-036) would naturally host the decoupled, locked startup sequence that ENT-033 asks for — so ENT-036's fix absorbs ENT-033's intent. Order: implement ENT-036's single bootstrap entrypoint with decoupled, non-`&&` steps under the lock.

### Unsafe Rollout Ordering

- **ENT-039 must precede any new `load_cities` one-shot** if that one-shot is placed in the catalog chain and mutates shared catalog state. Cities are a flat table (low MPTT risk), but for consistency the `load_cities` one-shot should acquire the same `CATALOG_LOAD` lock if added to the one-shot chain alongside `load_catalog`.
- **ENT-034's orphaned `__pycache__/0002_*.pyc`** removal is safe to do at any time (build artifact, gitignored). No rollout ordering dependency.
- **ENT-031's fix** (new cities one-shot in the clean-launch chain) must be added to `docker-compose.yml` as a dependency of `create_admin`/`load_catalog`/`web`/`bot` only *after* the command exists; deploying the command before wiring the dependency is safe (the command is simply unused). Reversing the order (wiring first) would crash `load_catalog`'s dependents. Sequence: create command → wire into compose chain.

### Fragile Insertion Points

- ENT-039's lock-id addition is a stable enum extension + a single `advisory_lock(...)` context-manager wrap — low fragility.
- ENT-040's post-load assertion is a two-line guard at the end of `load_catalog.py:handle` — stable insertion point.
- ENT-035's fix (flip `rewrite_yaml` default in one call site) is a one-line change — stable.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 9 | ENT-031, ENT-033, ENT-034, ENT-035, ENT-036, ENT-037, ENT-038, ENT-039, ENT-040 |
| Reclassified | 0 | — |
| Merged | 1 | ENT-032 → CFG-001 (Phase 02) — identical root cause; already mandated in `02-config-secrets-validated-findings.md` |
| Rejected | 0 | — |

### Rejected Findings

_None._ All 10 findings were verified against the current working tree and `git`
history and found technically correct, currently applicable, and architecturally
sound. No stale, duplicate-within-phase, or low-ROI findings.

### Merged Findings

| Original ID | Merged Into | Rationale |
|-------------|-------------|-----------|
| ENT-032 | CFG-001 (Phase 02) | Identical root cause: `${ADMIN_PASSWORD:-admin}` defeats the `entrypoint-create-admin.sh` empty-skip guard and boots `admin`/`admin`. CFG-001 was validated HIGH/mandatory in Phase 02 with the same recommendation; ENT-032 is independent corroboration, not a distinct issue. |

### Reclassified Findings

_None._

### Evidence Quality Assessment

| ID | Evidence Quality | Notes |
|----|------------------|-------|
| ENT-031 | **High** | All code paths verified; cities.json / SeedService / load_catalog / builder / migrations / compose gating confirmed exact. |
| ENT-032 | **High** (merged → CFG-001) | All sites verified exact; merged for redundancy. |
| ENT-033 | **High** | Shell `&&` chain, lock scope, DDL raw-cursor, prod/test divergence all confirmed. Minor imprecision in the dependency-direction phrasing (web/bot depend on `load_catalog`, not `migrate`). |
| ENT-034 | **High** | Git history (`4ea19cb`, `495bf74`) + working tree + orphaned `.pyc` + stale test comment all verified. |
| ENT-035 | **High** | Default-arg flow, `--no-rewrite` override, conditional rewrite, clean YAML all confirmed. |
| ENT-036 | **High** | Three invocation sites + single `INITIAL_RATES` definition confirmed. |
| ENT-037 | **High (core) / Medium (attribution)** | Restore set + no-conftest-call + per-module callers confirmed; one affected module misattributed (the seed image-generator stub). |
| ENT-038 | **High** | bulk_create + ignore_conflicts + return-all + explicit pk + BigAutoField confirmed. Minor: cited line range `301-307` is slightly off (actual `306-307`). |
| ENT-039 | **High** | AdvisoryLockId membership, unlocked entrypoint, `transaction.atomic()`-only, and lock-guarded contrasts confirmed. |
| ENT-040 | **High** | No-op-on-empty, unconditional SUCCESS, and web/bot gating confirmed. |

---

## Execution Validation

| Finding | Targets still exist? | Static verified? | Ready for execution |
|---------|----------------------|------------------|---------------------|
| ENT-031 | Yes — `seed_service.py:285-307`, `seed.py`, `builder.py:122-151`, `locations/0001_initial.py`, `docker-compose.yml:113-114`, `docker-compose.dev.override.yml:69-70` | Yes | Yes — small (new one-shot + compose wiring) |
| ENT-032 | Yes — `docker-compose.yml:99`, `docker-compose.dev.override.yml:15`, `entrypoint-create-admin.sh:18`, `create_admin_user.py:75,107-113` | Yes | Yes — trivial (already mandated by CFG-001) |
| ENT-033 | Yes — `docker-compose.yml:35`, `migrate_locked.py:33-37`, `load_exchange_rates.py:46-79`, `setup_search_triggers.py:106-131`, `entrypoint-test.sh:21-23` | Yes | Yes — small/medium (consolidate into locked Python entrypoint) |
| ENT-034 | Yes — `currencies/0001_initial.py`, `core/0002_seed_default.py`, orphaned `.pyc` files, `currencies/tests/conftest.py:6` | Yes | Yes — trivial for pyc/comment cleanup; medium for data-migration seeding design |
| ENT-035 | Yes — `seed_service.py:277-279`, `builder.py:53-57,155-156`, `load_catalog.py:36-39`, `entrypoint-catalog.sh:17` | Yes | Yes — trivial (one default-arg change) |
| ENT-036 | Yes — `docker-compose.yml:35`, `entrypoint-test.sh:22`, `conftest.py:114`, `load_exchange_rates.py:27-35` | Yes | Yes — small (new bootstrap command) |
| ENT-037 | Yes — `conftest.py:113-115,68-73`, `entrypoint-test.sh:21-23`, per-module callers | Yes | Yes — small (extend restore set or document intent; add real-command smoke test) |
| ENT-038 | Yes — `seed_service.py:306-307`, `cities.json:2-16`, `locations/0001_initial.py:16-22` | Yes | Yes — small (drop explicit pk / return seeded subset; optionally `setval`) |
| ENT-039 | Yes — `core/enums.py:23-42`, `entrypoint-catalog.sh:17`, `builder.py:121`, `migrate_locked.py:33`, `create_admin_user.py:75` | Yes | Yes — trivial (enum member + lock wrap) |
| ENT-040 | Yes — `builder.py:108-117`, `load_catalog.py:51-52`, `docker-compose.yml:62,142-144,169-171` | Yes | Yes — trivial (post-load row-count guard) |

## Warnings

- **Doc vs. code staleness (ENT-031/ENT-034):** `docs/ops/migration-workflow.md:253` and `docs/97-plans/phase-01-detailed.md:73` reference an intended `locations/migrations/0002_seed_cities.py` migration ("All 23 Montenegro municipalities seeded") that **does not exist** in the working tree — `locations/migrations/` contains only `0001_initial.py`, and `cities.json` holds 15 cities (not 23). This documents an intended cities-seeding migration that was never materialized (and was not restored by the squash). It is a documentation–code inconsistency that *corroborates* ENT-031 rather than contradicting it. Classified `DOC-UPDATE` hygiene; recommended fix is to align the docs to the actual cities one-shot once ENT-031 is implemented.
- **Stale test comment (ENT-034):** `currencies/tests/conftest.py:6` still references "the `seed_initial_rates` RunPython in `0001_initial`" — that RunPython was removed by the squash. Minor doc drift in a test module docstring; does not affect fixture behavior (the `exchange_rates` fixture is self-contained). Left as a noted observation, not a standalone finding.
- **Root 0-byte `entrypoint-*.sh` stubs** (Phase 02 CFG-006) are tracked in git and empty. They do **not** affect phase-05 findings because all catalog-seeding entrypoint references resolve to the populated `docker/entrypoint-*.sh` scripts (verified: `docker/entrypoint-catalog.sh`, `docker/entrypoint-test.sh`, `docker/entrypoint-create-admin.sh`, `docker/entrypoint-seed.sh` all contain real content). No action required in this phase; no conflict with CFG-006.
- **No cross-phase conflicts.** Phase 01 (ENT-001–007) and Phase 02 (CFG-001–007) validated findings are consistent with this phase's; the only overlap is ENT-032 ≡ CFG-001 (merged above).

## Required Fixes

1. **ENT-031 (mandatory, HIGH):** Add a `load_cities` reference-data management command (reusing `cities.json`) and wire it into the clean-launch one-shot chain in `docker-compose.yml` (not profile-gated), so a fresh production deploy always populates `cities`. Reuse a corrected loader per ENT-038.
2. **ENT-032 → CFG-001 (mandatory, HIGH, Phase 02):** Remove the `${ADMIN_PASSWORD:-admin}` default in `docker-compose.yml:99` and `docker-compose.dev.override.yml:15` so an unset `ADMIN_PASSWORD` fails fast and the entrypoint skip-guard is honored. (Already mandated by Phase 02; no new work here.)

## Advisory Recommendations

1. **ENT-033 (MEDIUM):** Consolidate `setup_search_triggers` + `load_exchange_rates` into the locked `migrate_locked.main()` Python entrypoint (resolving both the `&&` coupling here and Phase 01 ENT-003's lock-scope gap), and standardize prod/test error handling.
2. **ENT-034 (MEDIUM):** Document the post-squash seeding contract (migrations build schema; one-shot commands seed reference data); consider seeding the EUR base rate in a data migration; remove orphaned `__pycache__/0002_*.pyc`.
3. **ENT-035 (MEDIUM):** Make `SeedService._load_category_fixtures` call `load_catalog(CATALOG_PATH, rewrite_yaml=False)` to mirror the prod one-shot.
4. **ENT-040 (MEDIUM):** Add a post-load row-count guard in `load_catalog` (`Category.objects.exists()` and, post-ENT-031, `City.objects.exists()`); `sys.exit(1)` when zero rows loaded.
5. **ENT-036 (LOW):** Introduce a single `bootstrap_reference_data` management command invoked uniformly by the prod one-shot, the test entrypoint, and the conftest fixture.
6. **ENT-037 (LOW):** Extend the conftest test-schema-restore to run the real `load_catalog` one-shot (or document it as intentionally test-local); add a CI smoke test that invokes the real `load_catalog` management command against a clean DB.
7. **ENT-038 (LOW):** Drop explicit PKs from `cities.json` (let the DB assign PKs) and return only the seeded city subset from `_load_city_fixtures`; optionally `setval` the sequence if explicit PKs are retained.
8. **ENT-039 (LOW):** Add a `CATALOG_LOAD` member to `AdvisoryLockId` and wrap `load_catalog` in `advisory_lock(CATALOG_LOAD, session=True)` (and the new `load_cities` one-shot).

## Doc Updates Needed

- **ENT-031 / ENT-034 (DOC-UPDATE hygiene):** Align `docs/ops/migration-workflow.md:253` and `docs/97-plans/phase-01-detailed.md:73` with the actual cities-loading mechanism once a `load_cities` one-shot is introduced (remove the phantom `locations/0002_seed_cities.py` reference and the "23 municipalities" figure; `cities.json` has 15).
- **ENT-034 (DOC-UPDATE):** Document the post-squash seeding contract (migrations = schema; one-shot commands = reference data) so the SiteConfig-only-vs-everything-else split is an explicit, justified decision rather than an inconsistency.
- **ENT-035 / ENT-037:** If implemented, update `docs/ops/docker-deployment.md` catalog-deploy section to reflect the `load_catalog` rewrite policy and the test-schema-restore parity (or its documented deviation).
- **ENT-032 → CFG-001:** Align `.env.docker.example` / `docs/ops/docker-deployment.md` admin section to state `ADMIN_PASSWORD` is required (no silent default) — already tracked under CFG-001 in Phase 02.
