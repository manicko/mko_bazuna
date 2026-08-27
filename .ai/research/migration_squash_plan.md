# Migration Squash Plan — Mko Bazuna (FINAL)

**Date:** 2026-08-27
**Scope:** Automated dev/test migration squashing to a single `0001_initial.py` per app, and the §12 Option-B (skip-migration) schema-parity verdict.
**Author:** Kilo (Researcher subagent for Problem_02 / Spec 13 §13 + §12)
**Mode:** Research + planning only. **No migration files were deleted or rewritten during this study.**

> **Confidence legend (per project convention):** HIGH = verified by direct grep + file read on disk. MEDIUM = inferred from verified behavior + committed workflow. LOW = estimated; no direct timing data.

---

## 0. Executive summary

The committed `docs/ops/migration-workflow.md` ("Reference: App Migration Status") and the prior plan `07_dev-migration-consolidation_plan_DONE.md` enumerate migration counts and filenames that **no longer match the repository** (stale, see §9). The **actual** on-disk inventory is **39 numbered migration files across 10 model-apps** (plus `core`, which has `migrations/__init__.py` but **no `models.py`** and zero migration files; and 4 apps — `api`, `cabinet`, `media`, `seed` — with no `migrations/` directory at all).

A **pure automated squash** (`consolidate_migrations.py --force` → `makemigrations`) is **lossy** for exactly two categories of hand-written operation:

1. **`RunSQL` DDL** (PostgreSQL trigger functions + triggers) in `ads/0002`, `0006`, `0007` (13 `RunSQL` blocks across 4 files) — `makemigrations` can never regenerate these; they are not expressible in Django model state.
2. **`RunPython` seed data** in `currencies/0001` (3 `ExchangeRate` rows) — `makemigrations` can never regenerate `RunPython`; the rows are load-bearing for `PriceNormalizer` at runtime and in tests.

Everything else (schema ops, all GIN/conditional indexes + check constraints declared in `Meta`, data-backfill `RunPython` that is a no-op on an empty DB, the `UPDATE ads SET title = title;` no-ops) is either auto-regenerable or safely disposable on a disposable dev/test DB.

**Bottom line:** The automated squash is feasible, but **(A)** the ads trigger DDL and the currencies seed rates must be extracted to management commands (`manage.py setup_search_triggers` + `manage.py load_exchange_rates`) and wired into every entrypoint that runs `migrate`, **before** the lossy files are deleted; **(B)** for §12 Option B the parity verdict is **NOT lossless** (see §5) — fall back to **Option A (squash-only)** unless the extraction commands are also wired into the test bootstrap.

---

## 1. Authoritative migration inventory (verified on disk)

Counted via `Get-ChildItem src/backend/apps/<app>/migrations -Filter "0*.py"` and cross-checked with a recursive glob of `apps/*/migrations/0*.py`.

**Apps with numbered migrations (10):** ads, analytics, categories, currencies, locations, lookups, moderation, search, trust, users.
**`core`:** has `migrations/` dir + `__init__.py` only — **0 numbered files**, and `core/models.py` does **not** exist (verified: `src/backend/apps/core/` contains only `__init__.py, apps.py, context_processors.py, enums.py, urls.py, views.py`).
**No `migrations/` dir (4 apps):** api, cabinet, media, seed (verified: none of these has a `models.py` that requires migrations; `seed` is a `management`/commands-only app).

### Inventory table

Operation-type legend: **CreateModel/AlterField/AddField/RemoveField/AddIndex/AlterIndex/AlterUnique/AlterConstraint/AddConstraint** = `SchemaOperation`; **RunPython**, **RunSQL**, **SeparateDatabaseAndState**.

| App | File | Line | Operation type | Idempotent? (Y/N/partial + how) | External/live-import/FS/network? (Y/N) | Disposition |
|-----|------|------|----------------|----------------------------------|------------------------------------------|-------------|
| ads | `0001_initial.py` | 20-75 | CreateModel (Ad, AdImage, AdFeature) | Y (CREATE TABLE) | N (imports only `apps.core.enums`, `apps.lookups.enums`) | fold into `0001_initial` |
| ads | `0002_add_fks_and_search_triggers.py` | 60-102 | AddField×6, AlterUniqueTogether, AddIndex×6 | Y (idempotent DDL) | N | FKs/indexes → auto-regen; RunSQL → extract |
| ads | `0002` | 127 | RunSQL ×4 | Y (`CREATE OR REPLACE FUNCTION` + `DROP TRIGGER IF EXISTS` + `CREATE TRIGGER`) | N | **Extract trigger DDL → `setup_search_triggers`** |
| ads | `0003_ad_i18n_fields.py` | 13-37 | AddField×5 (title_en/bs, description_en/bs, original_language) | Y | N | auto-regen |
| ads | `0004_ad_draft_nullable_fields.py` | 13-65 | AlterField×5 | Y | N | auto-regen |
| ads | `0005_alter_ad_…_and_more.py` | 13-27 | AlterField×3 | Y | N | auto-regen (help-text only drift) |
| ads | `0006_ad_ix_ads_purge_deleted_and_more.py` | 49-68 | AddIndex, AddConstraint×6 | Y (idempotent DDL) | N | constraints auto-regen (Meta.constraints:314-341); RunSQL fn rewrite → extract |
| ads | `0006` | 77 | RunSQL ×2 (`CREATE OR REPLACE FUNCTION` ×2) | Y (`OR REPLACE`) | N | **Extract → `setup_search_triggers`** (final version wins) |
| ads | `0006` | 85 | RunSQL ×1 (`UPDATE ads SET title = title;`) | Y (SQL no-op) | N | **drop** (literal no-op) |
| ads | `0007_search_vector_i18n.py` | 64-90 | AddField×3 (search_vector_ru/bs/en) | Y | N | SearchVectorField model fields → auto-regen |
| ads | `0007` | 91 | RunSQL ×1 (`CREATE OR REPLACE FUNCTION ads_search_vector_fn`, i18n final) | Y (`OR REPLACE`) | N | **Extract → `setup_search_triggers`** (final version) |
| ads | `0007` | 95 | RunSQL ×1 (`DROP TRIGGER IF EXISTS …; CREATE TRIGGER on_category_name_update … name, name_i18n`) | Y (`DROP IF EXISTS`) | N | **Extract → `setup_search_triggers`** |
| ads | `0007` | 99 | RunSQL ×1 (`UPDATE ads SET title = title;`) | Y (no-op) | N | **drop** |
| ads | `0008_search_vector_gin.py` | 14 (atomic=False) | SeparateDatabaseAndState | — (see RunSQL) | N | see RunSQL verdict |
| ads | `0008` (SeparateDatabaseAndState.db_ops) | 23,32,41 | RunSQL ×3 (`CREATE INDEX CONCURRENTLY IX_ads_search_gin_{ru,bs,en}`) | **N- forward** (no `IF NOT EXISTS`) | N | **auto-regen** (GinIndex in `Meta.indexes`:257-268); CONCURRENTLY variant lost (moot on empty DB) |
| ads | `0009_adfavorite.py` | 18-73 | CreateModel (AdFavorite) + AddConstraint + AddIndex | Y | N | auto-regen |
| ads | `0010_ad_currency_price_fields.py` | 60-102 | AddField×3, RunPython, AddIndex, RemoveField(price) | RunPython: Y (no-op on empty DB) | N (uses `apps.get_model` + `decimal`) | **drop RunPython**; schema auto-regen |
| ads | `0010` | 94 | RunPython `backfill_price_fields` | Y on fresh/empty DB (0 rows; legacy `price` absent) | N (local ORM+deterministic `Decimal`) | **drop** |
| ads | `0011_catalog_filter_indexes.py` | 19-26 | AddIndex×2 | Y | N | auto-regen (Meta.indexes:274, AdFeature.Meta.indexes:636) |
| ads | `0012_ad_listing_condition.py` | 16-20 | AddField (listing_condition FK) | Y | N | auto-regen |
| analytics | `0001_initial.py` | 16-43 | CreateModel×2 | Y | N | auto-regen |
| analytics | `0002_add_user_fks_and_metrics.py` | 17-38 | AddField×2, AddIndex×2, AddConstraint | Y | N | auto-regen |
| analytics | `0003_change_timestamp_auto_add_to_default.py` | 14-18 | AlterField | Y | N | auto-regen |
| analytics | `0004_analyticsevent_source.py` | 13-17 | AddField (source) | Y | N | auto-regen |
| categories | `0001_initial.py` | 18-81 | CreateModel×3 (Category MPTT, CategoryListingFeature, CategoryListingPurpose, CategoryPath) | Y | N (imports `apps.lookups.enums`, `mptt.fields`) | auto-regen |
| categories | `0002_categorylistingcondition.py` | 16-29 | CreateModel (CategoryListingCondition) | Y | N | auto-regen |
| currencies | `0001_initial.py` | 44-111 | CreateModel + AddConstraint | Schema: Y | N | schema auto-regen |
| currencies | `0001` | 112 | RunPython `seed_initial_rates` | Y (update_or_create per currency) | N (local deterministic) | **Extract → `load_exchange_rates`** (load-bearing) |
| currencies | `0002_alter_exchangerate_created_at_and_more.py` | 13-22 | AlterField×2 | Y | N | auto-regen |
| locations | `0001_initial.py` | 14-28 | CreateModel (City) | Y | N | auto-regen |
| lookups | `0001_initial.py` | 15-47 | CreateModel×2 (LookupGroup, LookupItem) | Y | N | auto-regen |
| moderation | `0001_initial.py` | 17-66 | CreateModel×3 | Y | N (imports `apps.core.enums`) | auto-regen |
| moderation | `0002_add_fks_and_priority_indexes.py` | 17-43 | AddField×3, AddIndex×3 | Y | N | auto-regen |
| search | `0001_initial.py` | 17-67 | CreateModel×4 | Y | N | auto-regen |
| search | `0002_add_fks_indexes_constraints.py` | 17-52 | AddField×4, AddIndex×3, AddConstraint | Y | N | auto-regen |
| search | `0003_savedsearch_language.py` | 13-14 | AddField + RunPython | RunPython: Y (no-op on empty DB) | N | **drop RunPython**; field auto-regen |
| search | `0003` | 35 | RunPython `backfill_legacy_language` | Y on fresh (0 rows) | N (`apps.get_model`) | **drop** |
| search | `0004_savedsearch_alerts_fields.py` | 13-50 | AddField×3 + RunPython | RunPython: Y on fresh (0 rows) | N (`secrets` stdlib) | **drop RunPython**; field auto-regen |
| search | `0004` | 64 | RunPython `backfill_unsubscribe_tokens` | Y on fresh (0 rows); new rows via model `save()` override | N | **drop** |
| search | `0005_savedsearch_price_eur.py` | 20-36 | RunPython (fwd+reverse) | Y on fresh (0 rows) | N (`decimal`, `apps.get_model`) | **drop** (data-only; prices converted in-place) |
| search | `0006_alter_savedsearch_max_price_and_more.py` | 13-22 | AlterField×2 | Y | N | auto-regen |
| search | `0007_popularsearch_source.py` | 13-17 | AddField (source) | Y | N | auto-regen |
| trust | `0001_initial.py` | 16-42 | CreateModel×2 | Y | N | auto-regen |
| trust | `0002_add_user_fks.py` | 16-25 | AddField×2 | Y | N | auto-regen |
| users | `0001_initial.py` | 17-65 | CreateModel (User, LoginToken) | Y | N | auto-regen |
| users | `0002_alter_user_telegram_id_null.py` | 11-20 | AlterField (telegram_id null+unique) | Y | N | auto-regen |
| users | `0003_user_preferred_city.py` | 15-19 | AddField (preferred_city FK) | Y | N | auto-regen |
| users | `0004_consentrecord.py` | 15-32 | CreateModel (ConsentRecord) | Y | N | auto-regen |
| users | `0005_user_telegram_language.py` | 18-27 | AddField (telegram_language) | Y | N | auto-regen |
| users | `0006_user_source.py` | 13-17 | AddField (source) | Y | N | auto-regen |

**Totals (verified):** 39 numbered files · 10 initial migrations · **5 `RunPython` calls** (in 5 files: currencies/0001, ads/0010, search/0003-0005) · **13 `RunSQL` blocks** (across 4 ads files) · **1 `SeparateDatabaseAndState`** (ads/0008).

### Stale docs divergence (HIGH confidence — all verified on disk)

| Doc claim (`docs/ops/migration-workflow.md:169-181` + prior plan `07…_DONE.md:485-499`) | Actual on disk | Doc-cited files that DO NOT EXIST |
|---|---|---|
| ads = 10, latest `0010_backfill_listing_purpose.py` | ads = **12**, latest `0012_ad_listing_condition.py` | — |
| analytics = 4, latest `0004_analytics_event_fk_set_null_and_index.py` | analytics = **4**, latest `0004_analyticsevent_source.py` | — (filename mismatch) |
| categories = 5 (incl. `0002_seed_categories`, `0005_load_catalog`) | categories = **2** | `categories/0002_seed_categories.py`, `0003_load_catalog.py`, `0005_load_catalog.py` |
| core = 1 (`0001_verify_lifecycle_indexes.py`) | core = **0** (no `models.py`) | `core/0001_verify_lifecycle_indexes.py` |
| locations = 2 (incl. `0002_seed_cities`) | locations = **1** | `locations/0002_seed_cities.py` |
| lookups = 1 | lookups = **1** ✓ | — |
| moderation = 4 (latest `0004_ad_moderation_priority_default.py`) | moderation = **2** | — |
| search = 4 (latest `0004_fix_index_name_too_long.py`) | search = **7**, latest `0007_popularsearch_source.py` | — |
| trust = 2 (latest `0002_trust_level_default.py`) | trust = **2**, latest `0002_add_user_fks.py` | — (filename mismatch) |
| users = 3 (latest `0003_user_telegram_premium.py`) | users = **6**, latest `0006_user_source.py` | — |
| currencies — **not listed** | currencies = **2** | — |
| Total = 36 / "10 apps" | Total = **39**; **10 model-apps + core(0)** | — |

The prior plan `07_dev-migration-consolidation_plan_DONE.md` likewise references pre-reset filenames (`ads/0002_search_vector_triggers.py`, `ads/0005_multi_lang_search_vector.py`, `users/0002_user_chat_id.py`, `categories/0002_seed_categories.py`, `categories/0003_load_catalog.py`, `core/0001_verify_lifecycle_indexes.py`) — **none of which exist on disk today**. The repo was reset to fresh initials on 2026-08-04 (the `0001_initial` files) and then grown incrementally to the current state; `backfill_translations` and `load_catalog` were extracted to management commands but their *migration* containers were deleted in that reset.

---

## 2. Dependency graph (verified)

Root apps (no cross-app deps): `lookups/0001`, `locations/0001`, `currencies/0001`, `users/0001` (`users/0001` → `auth/0012_alter_user_first_name_max_length`, a Django built-in). After squash, `makemigrations` recomputes this from FK declarations. Consolidated graph:

```
lookups/0001_initial, locations/0001_initial, currencies/0001_initial   (no deps)
users/0001_initial      -> auth/0012 (swappable)
categories/0001_initial -> lookups/0001_initial
ads/0001_initial        -> categories/0001, locations/0001, lookups/0001, users/0001
analytics/0001_initial   -> ads/0001, users/0001
moderation/0001_initial  -> ads/0001, users/0001
search/0001_initial      -> ads/0001, categories/0001, locations/0001, users/0001
trust/0001_initial       -> users/0001
```

`core` and the 4 dir-less apps are absent. Cross-app edges are read from each file's `dependencies = [...]` (spot-checked: all root apps have `dependencies = []`; `users/0001` deps `('auth','0012...')`; ads/analytics/search/moderation pull in the expected cross-app tuples).

### 2.1 RunSQL idempotency audit (HIGH confidence)

| File:Op # | SQL | Forward guard | Reverse guard | Verdict |
|-----------|-----|---------------|---------------|---------|
| ads/0002:127 (1) | `CREATE OR REPLACE FUNCTION ads_search_vector_fn() … LANGUAGE plpgsql` | `OR REPLACE` | `RunSQL.noop` | ✅ idempotent forward |
| ads/0002:131 (2) | `DROP TRIGGER IF EXISTS ads_search_vector_update ON ads; CREATE TRIGGER ads_search_vector_update BEFORE INSERT OR UPDATE …` | `DROP IF EXISTS` | `noop` | ✅ idempotent forward |
| ads/0002:135 (3) | `CREATE OR REPLACE FUNCTION categories_name_propagate() … LANGUAGE plpgsql` | `OR REPLACE` | `noop` | ✅ idempotent forward |
| ads/0002:139 (4) | `DROP TRIGGER IF EXISTS on_category_name_update ON categories; CREATE TRIGGER on_category_name_update AFTER UPDATE OF name …` | `DROP IF EXISTS` | `noop` | ✅ idempotent forward |
| ads/0006:77 (1) | `CREATE OR REPLACE FUNCTION categories_name_propagate()` (rewrite) | `OR REPLACE` | `noop` | ✅ idempotent forward |
| ads/0006:81 (2) | `CREATE OR REPLACE FUNCTION ads_search_vector_fn()` (i18n rewrite w/o per-lang vectors) | `OR REPLACE` | `noop` | ✅ idempotent forward |
| ads/0006:85 (3) | `UPDATE ads SET title = title;` | — (SQL no-op) | `noop` | ✅ no-op |
| ads/0007:91 (1) | `CREATE OR REPLACE FUNCTION ads_search_vector_fn()` (final i18n w/ `search_vector_ru/bs/en`) | `OR REPLACE` | `noop` | ✅ idempotent forward |
| ads/0007:95 (2) | `DROP TRIGGER IF EXISTS on_category_name_update …; CREATE TRIGGER … AFTER UPDATE OF name, name_i18n …` | `DROP IF EXISTS` | `noop` | ✅ idempotent forward |
| ads/0007:99 (3) | `UPDATE ads SET title = title;` | — (no-op) | `noop` | ✅ no-op |
| ads/0008:23 (1) | `CREATE INDEX CONCURRENTLY IX_ads_search_gin_ru ON ads USING gin(search_vector_ru);` | **none** | `DROP INDEX CONCURRENTLY IF EXISTS` (reverse) | ⚠️ non-idempotent **forward** |
| ads/0008:32 (2) | `CREATE INDEX CONCURRENTLY IX_ads_search_gin_bs …` | **none** | `DROP INDEX CONCURRENTLY IF EXISTS` | ⚠️ non-idempotent **forward** |
| ads/0008:41 (3) | `CREATE INDEX CONCURRENTLY IX_ads_search_gin_en …` | **none** | `DROP INDEX CONCURRENTLY IF EXISTS` | ⚠️ non-idempotent **forward** |

**Offenders** (lacking forward `IF NOT EXISTS`): the 3 `CREATE INDEX CONCURRENTLY` in `ads/0008_search_vector_gin.py:23-48`. PostgreSQL 18 **does** support `CREATE INDEX CONCURRENTLY IF NOT EXISTS`, so the guard is available — but it is moot after squash: all 3 indexes are declared as `GinIndex` in `Ad.Meta.indexes` (`ads/models.py:257-268`), so `makemigrations` regenerates them as standard (non-concurrent) `AddIndex`, which is also faster on an empty dev/test DB and eliminates the `atomic=False` / `SeparateDatabaseAndState` wrapper.

### 2.2 Live-import / external-call / FS / network audit (HIGH confidence)

Grep for `deep_translator|GoogleTranslator|requests\.|httpx|cursor\.execute|http\.request` across every `*/migrations/0*.py` → **0 matches**. No migration calls an external API, the network, or executes raw cursor SQL. Module-level imports in migrations are limited to **enums and Django field/validator classes**: `apps.core.enums`, `apps.lookups.enums`, `django.contrib.postgres.*`, `django.contrib.auth.models`, `django.utils.timezone`, `mptt.fields`, `decimal`, `secrets`, `django.conf.settings`. No migration performs `from apps.<app>.models import …` — the "historical models only" rule is satisfied everywhere.

### 2.3 RunPython data-migration audit (HIGH confidence)

| File | RunPython | Deterministic local? | External/live import? | Idempotent / no-op-on-fresh? | Disposition |
|------|-----------|----------------------|------------------------|------------------------------|-------------|
| currencies/0001 | `seed_initial_rates` (3 rows: EUR=1.0, BAM=0.512, RSD=0.0105, `source="manual_seed"`, all `is_current`) | ✅ deterministic constant data | N | ✅ `update_or_create` keyed on `currency` | **Extract → `load_exchange_rates`** (load-bearing) |
| ads/0010 | `backfill_price_fields` / `remove_backfill_price_fields` | ✅ deterministic (`Decimal`) | N (`apps.get_model` only) | ✅ no-op on fresh/empty DB (0 `Ad` rows; legacy `price` column absent) | **drop** (schema auto-regens) |
| search/0003 | `backfill_legacy_language` | ✅ deterministic | N (`apps.get_model`) | ✅ no-op on fresh DB (0 rows) | **drop** |
| search/0004 | `backfill_unsubscribe_tokens` | deterministic (`secrets`, per-row) | N | ✅ no-op on fresh DB (0 rows); new rows get token via `SavedSearch.save()` override | **drop** |
| search/0005 | `convert_saved_search_prices` / reverse | ✅ deterministic (`Decimal`, fixed `BAM_TO_EUR=0.512`) | N | ✅ no-op on fresh DB (0 rows) | **drop** |

**Load-bearing data confirmation:** `currencies/services/price_normalizer.py` (`_get_current_rate`, lines 92-102) queries `ExchangeRate.objects.filter(currency=…, is_current=True)` and raises `ExchangeRateNotFoundError` if absent. `currencies/tests/test_price_normalizer.py` (`test_bam_normalized_by_seeded_rate` line 33-36; `test_rsd_normalized_by_seeded_rate` line 38-41) asserts the seeded rates **with no fixture creating them** — the root `conftest.py` (184 lines) contains no `ExchangeRate` creation, and grep confirms no `django_db_setup` / `MIGRATION_MODULES` override anywhere. Therefore the `currencies/0001` seed is load-bearing for both runtime and the test suite.

**`backfill_translations` extraction (confirmed on disk, do not assume):** `src/backend/apps/ads/management/commands/backtrack_translations.py` — no, `backfill_translations.py` — **exists** at `ads/management/commands/backfill_translations.py` (136 lines). It is the extraction target: it imports `deep_translator.GoogleTranslator` **lazily** at call time (line 38), is idempotent ("skips ads where translations are already populated", line 7), and uses live model imports (line 67). Grep confirms **0** references to `backfill_translations` inside any migration file. The extraction is real and complete.

---

## 3. Per-app disposition summary (§13 finalization)

**ads (12 → 1):** All `AddField`/`AlterField`/`RemoveField`/`AddIndex`/`AddConstraint` fold into the regenerated `0001_initial` via `Ad`/`AdImage`/`AdFeature`/`AdFavorite` model state (`ads/models.py:22-688` — every field, `Meta.indexes`:252-313, `Meta.constraints`:314-341, `AdFeature.Meta.indexes`:636-641, `AdFavorite.Meta.indexes/constraints`:675-686). The **only** unsquashable artifacts are the two PostgreSQL trigger functions + two triggers (`ads_search_vector_fn`, `ads_search_vector_update`, `categories_name_propagate`, `on_category_name_update`) — these move to `manage.py setup_search_triggers` (new). The 3 `CREATE INDEX CONCURRENTLY` are redundant (GinIndex in `Meta`). The 2 `UPDATE ads SET title = title;` are SQL no-ops. `backfill_price_fields` (ads/0010) is a no-op on a fresh DB → drop.

**analytics (4 → 1):** Pure schema (CreateModel + FK/index/constraint). Auto-regen. No data migrations.

**categories (2 → 1):** Pure schema (`Category` MPTT tree incl. `name_i18n`, `CategoryListingFeature/Purpose/Condition/Path`). Auto-regen. The stale docs claim 5 files incl. `0002_seed_categories` + `0005_load_catalog` — **those files do not exist**; catalog loading lives only in the `load_catalog` management command (`categories/management/commands/load_catalog.py`) + the `load_catalog` Docker one-shot, invoked post-migrate. No extraction needed beyond the already-shipped command.

**core (0 → 0):** No `models.py` → nothing to generate. `core/migrations/` stays `__init__.py`-only.

**currencies (2 → 1):** `CreateModel(ExchangeRate)` + `UniqueConstraint` + `AlterField`s auto-regen. The `seed_initial_rates` RunPython is **load-bearing** → extract to `manage.py load_exchange_rates` (new), wired into all entrypoints (it replaces what the migration currently does on every fresh DB).

**locations (1 → 1):** Pure schema (`City`). Already a single initial.

**lookups (1 → 1):** Pure schema (`LookupGroup`, `LookupItem`). Already a single initial.

**moderation (2 → 1):** Pure schema (`CreateModel` + `AddField`/`AddIndex`/`AddConstraint`). Auto-regen.

**search (7 → 1):** Schema (4 models + FKs/indexes/constraints) auto-regen. `backfill_legacy_language` (0003), `backfill_unsubscribe_tokens` (0004), `convert_saved_search_prices` (0005) are all no-op on a fresh DB → drop. **No `RunSQL`/triggers in search** (the spec's §4.3 table incorrectly implies FTS triggers in search; the only FTS trigger DDL lives in `ads`).

**trust (2 → 1):** Pure schema. Auto-regen.

**users (6 → 1):** Pure schema (no `RunPython`/`RunSQL` at all — the stale docs/spec §4.3 claim `users/0002` is a "chat_id null backfill" is **incorrect**; `users/0002_alter_user_telegram_id_null.py` is a plain `AlterField`). Auto-regen.

**Other (no migrations dir):** `api`, `cabinet`, `media`, `seed` — unaffected; `seed` is a command-only app (seed data via `apps/seed`), `media` has no models needing migration.

### §13 per-app disposition table

| App | Files before | Schema ops | Data ops (RunPython/RunSQL) | Non-reproducible by `makemigrations`? | Final disposition |
|-----|------------:|-----------|------------------------------|----------------------------------------|-------------------|
| ads | 12 | fold | 13 RunSQL + 1 RunPython (all trigger fn/trigger/DDL + 1 price backfill) | ✅ trigger fn/triggers (4 DDL objects) | schema auto-regen; **extract triggers → `setup_search_triggers`**; drop no-op SQL + price backfill |
| analytics | 4 | fold | none | — | auto-regen (schema-only) |
| categories | 2 | fold | none | — | auto-regen (schema-only; catalog already a command) |
| core | 0 | — | — | — | no change (0 files) |
| currencies | 2 | fold | 1 RunPython (`seed_initial_rates`, 3 rows) | ✅ seed rows | schema auto-regen; **extract seed → `load_exchange_rates`** |
| locations | 1 | fold | none | — | auto-regen (already 1) |
| lookups | 1 | fold | none | — | auto-regen (already 1) |
| moderation | 2 | fold | none | — | auto-regen |
| search | 7 | fold | 3 RunPython (all no-op-on-fresh) | — (no schema loss) | auto-regen; drop 3 no-op RunPython |
| trust | 2 | fold | none | — | auto-regen |
| users | 6 | fold | none | — | auto-regen (no data ops — §4.3 "backfill" claim is stale) |
| **Total** | **39** | → **10** initials | **5 RunPython + 13 RunSQL** | trigger fn/triggers + currency seed | 2 commands to extract; rest auto-regen/drop |

---

## 4. RunSQL idempotency audit — offender remediation (§3.2 of spec)

Only one class of non-idempotent RunSQL exists, and it is **lossy under auto-generation** (not a runtime risk for the consolidated path):

- **Offender:** `ads/0008_search_vector_gin.py:23,32,41` — `CREATE INDEX CONCURRENTLY IX_ads_search_gin_{ru,bs,en}` with **no** `IF NOT EXISTS` (and `reverse_sql` only guards `DROP INDEX CONCURRENTLY IF EXISTS`). A naïve re-apply of these three statements on a non-empty DB errors with `relation already exists`.
- **Remediation at squash time:** these three indexes are already declared as `GinIndex` in `Ad.Meta.indexes` (`ads/models.py:257-268`). `makemigrations` will emit standard (non-concurrent) `AddIndex` operations, which Django renders as `CREATE INDEX IF NOT EXISTS` automatically on re-run → idempotent. The `atomic = False` + `SeparateDatabaseAndState` wrapper (ads/0008:12-21) is eliminated. **No manual SQL guard is required post-squash** — the auto-generated `AddIndex` is idempotent by construction.
- **Trigger/function RunSQL** (ads/0002/0006/0007) already use `CREATE OR REPLACE FUNCTION` + `DROP TRIGGER IF EXISTS` → idempotent forward; they are removed from the migration graph entirely (extracted to `setup_search_triggers`, which is itself idempotent for the same reason).

**Conclusion:** After squash, **0 non-idempotent RunSQL remain** — all are either extracted (triggers) or auto-regenerated (indexes). TST-005 `test_migration_idempotency` (`migrate --noinput` re-run prints "No migrations to apply.") will pass.

---

## 5. Skip-migration (§12 Option B) parity verdict

### 5.1 What Option B does

`MIGRATION_MODULES = {app: None}` for the model-apps tells pytest-django (and `create_test_db`) to build the schema directly from model introspection (the `syncdb`-style path) **instead of replaying migration files**. It is a test/dev-only setting (`config.settings.test`).

### 5.2 Lossless-reproducibility matrix — every hand-written `RunSQL`/`RunPython`/`SeparateDatabaseAndState`

Per spec §12 D4, Option B is adopted **iff** R3 proves schema parity including hand-written `RunSQL` indexes/triggers. The audit below marks each hand-written operation with its reproducibility under model-introspection schema creation.

**Hand-written `RunSQL` + `SeparateDatabaseAndState`:**

| # | Operation (file:line) | SQL | Reproducible by `MIGRATION_MODULES=None`? | Why / why not |
|---|---|-----|-------------------------------------------|---------------|
| 1 | ads/0002:127 | `CREATE OR REPLACE FUNCTION ads_search_vector_fn()` | **NO** | PostgreSQL trigger function; no Django model declaration maps to a trigger function. |
| 2 | ads/0002:131 | `DROP TRIGGER IF EXISTS ads_search_vector_update…; CREATE TRIGGER ads_search_vector_update BEFORE INSERT OR UPDATE` | **NO** | Triggers are not emitted by `CreateModel` introspection. |
| 3 | ads/0002:135 | `CREATE OR REPLACE FUNCTION categories_name_propagate()` | **NO** | Trigger function; no model equivalent. |
| 4 | ads/0002:139 | `DROP TRIGGER IF EXISTS on_category_name_update…; CREATE TRIGGER on_category_name_update AFTER UPDATE OF name` | **NO** | Trigger; not reproducible. |
| 5 | ads/0006:77 | `CREATE OR REPLACE FUNCTION categories_name_propagate()` (rewrite) | **NO** | Same final object as #4's function — still not reproducible. |
| 6 | ads/0006:81 | `CREATE OR REPLACE FUNCTION ads_search_vector_fn()` (rewrite, no per-lang vectors) | **NO** | Superseded by #7 in final state; still hand-written, not reproducible. |
| 7 | ads/0006:85 | `UPDATE ads SET title = title;` | **NO-op** | SQL no-op; moot for schema. |
| 8 | ads/0007:91 | `CREATE OR REPLACE FUNCTION ads_search_vector_fn()` (final i18n version) | **NO** | Final trigger function; not reproducible. |
| 9 | ads/0007:95 | `DROP TRIGGER IF EXISTS on_category_name_update…; CREATE TRIGGER …AFTER UPDATE OF name, name_i18n` | **NO** | Final trigger; not reproducible. |
| 10 | ads/0007:99 | `UPDATE ads SET title = title;` | **NO-op** | SQL no-op; moot. |
| 11 | ads/0008:23 (inside `SeparateDatabaseAndState`) | `CREATE INDEX CONCURRENTLY IX_ads_search_gin_ru` | **YES** | Declared as `GinIndex(name="IX_ads_search_gin_ru", fields=["search_vector_ru"])` in `Ad.Meta.indexes` (ads/models.py:257). Introspection emits `CREATE INDEX IF NOT EXISTS`. Index object losslessly reproduced (only the `CONCURRENTLY` variant is dropped). |
| 12 | ads/0008:32 | `CREATE INDEX CONCURRENTLY IX_ads_search_gin_bs` | **YES** | `GinIndex` in `Ad.Meta.indexes` (ads/models.py:259). |
| 13 | ads/0008:41 | `CREATE INDEX CONCURRENTLY IX_ads_search_gin_en` | **YES** | `GinIndex` in `Ad.Meta.indexes` (ads/models.py:265). |

Distinct non-reproducible DDL objects in final state = **4**: `ads_search_vector_fn` (function), `ads_search_vector_update` (trigger), `categories_name_propagate` (function), `on_category_name_update` (trigger). Produced by **8 non-trivial `RunSQL` statements** across 3 files (ads/0002, 0006, 0007; the 2 `UPDATE … = …` no-ops excluded).

**Hand-written `RunPython` (data, not schema):**

| Operation | File:Line | Schema effect | Reproducible as data by `MIGRATION_MODULES=None`? | Parity impact |
|-----------|-----------|---------------|---------------------------------------------------|---------------|
| `seed_initial_rates` (3 ExchangeRate rows) | currencies/0001:112 | none (table comes from `CreateModel`) | **NO** — introspection creates the table but not the rows | **Lossy for data**: `PriceNormalizer` raises `ExchangeRateNotFoundError` without current rates; `test_price_normalizer` (BAM 0.512, RSD 0.0105) fails. No conftest fixture supplies them. |
| `backfill_price_fields` | ads/0010:94 | none | fresh DB has 0 rows → moot | Moot on fresh DB |
| `backfill_legacy_language` | search/0003:35 | none | 0 rows → moot | Moot on fresh DB |
| `backfill_unsubscribe_tokens` | search/0004:64 | none | 0 rows → moot | Moot on fresh DB |
| `convert_saved_search_prices` | search/0005:67 | none | 0 rows → moot | Moot on fresh DB |

### 5.3 Verdict

- **Option A (squash-only): SAFE and lossless.** After squash the single `ads/0001_initial` retains the (idempotent) `RunSQL` trigger DDL and the `currencies/0001_initial` retains `seed_initial_rates` — both executed on every fresh DB, so schema + triggers + seed rates are present. The 3 `CREATE INDEX CONCURRENTLY` are auto-regenerated as idempotent `AddIndex`. TST-005 passes.
- **Option B (skip-only, `MIGRATION_MODULES=None`): NOT lossless.** It loses the **4 hand-written trigger/function DDL objects** (8 `RunSQL` statements) → the `ads_search_vector_update` trigger never fires, so `search_vector`/`search_vector_{ru,bs,en}` stay NULL and native PostgreSQL FTS returns no results; and it loses the **3 `ExchangeRate` seed rows** → `PriceNormalizer` raises and `test_price_normalizer` fails. The 3 `ads/0008` GIN indexes ARE losslessly reproduced (they are `Meta.indexes` GinIndex).
- **Option C (both): VIABLE, conditional.** Option B becomes functional **iff** the test bootstrap additionally runs the extracted `manage.py setup_search_triggers` + `manage.py load_exchange_rates` (an autouse `pytest` fixture or a step in `entrypoint-test.sh` after `migrate`/schema creation). With that compensating step, `MIGRATION_MODULES=None` + fixture gives schema + triggers + seed rates. **Without the compensating step, Option B alone is lossy.**

**Precise reason (spec §12 D4):** *Option B loses 8 non-trivial hand-written `RunSQL` statements (CREATE OR REPLACE FUNCTION / DROP+CREATE TRIGGER across `ads/0002`, `0006`, `0007` — 4 DDL objects in final state: `ads_search_vector_fn`, `ads_search_vector_update`, `categories_name_propagate`, `on_category_name_update`) that have no Django model declaration and cannot be emitted by `create_test_db()`-style introspection; plus the `currencies/0001` `RunPython` seed (3 `ExchangeRate` rows) on which `PriceNormalizer` and `test_price_normalizer` depend. Only the 3 `ads/0008` GIN indexes are losslessly reproducible (`Meta.indexes` GinIndex). Fall back to **Option A** unless the trigger DDL + currency seed are extracted to commands and wired into the test entrypoint (then Option C is safe).*

---

## 6. Exact automated squash command sequence

Mirrors spec §14 (automated, no hand-rewriting) and TST-005 (V1–V4). `consolidate_migrations.py` (verified: `--force`/`--threshold`/`--dry-run`/`--apps-dir`; `:85-110` deletes every `0*.py` + `__pycache__`; `:76-82` counts `[0-9]*.py`; `:128-139` walks apps) performs **only file operations** — it knows nothing of Django/DB.

### Prerequisite — Phase 0 (EXTRACT unsquashable ops; must precede file wipe)

These two commands do **not** yet exist on disk; they must be authored first, copying the FINAL trigger DDL from `ads/0007` and the seed from `currencies/0001`:

- `src/backend/apps/ads/management/commands/setup_search_triggers.py` — contains the final i18n `ads_search_vector_fn` (`ads/0007:12-46`), `CREATE OR REPLACE FUNCTION categories_name_propagate`, and both triggers `ads_search_vector_update` + `on_category_name_update` (`ads/0007:48-53` + `ads/0002:27-31`); idempotent via `OR REPLACE` / `DROP TRIGGER IF EXISTS`.
- `src/backend/apps/currencies/management/commands/load_exchange_rates.py` — replicates `seed_initial_rates` (`currencies/0001:6-28`) using live `apps.currencies.models` (not `apps=`); idempotent via `update_or_create`.

(`manage.py backfill_translations` and `manage.py load_catalog` are **already extracted** and confirmed on disk.)

### Phase 1 — Fresh-DB path (CI / `make test-recreate`)

```bash
# 0. (pre-req) author setup_search_triggers + load_exchange_rates; verify backfill_translations + load_catalog exist
# 1. Wipe all numbered migrations (keeps __init__.py):
uv run python scripts/consolidate_migrations.py --force            # deletes 39 files (dry-run first optional)
# 2. Regenerate one 0001_initial.py per model-app from current models:
uv run python src/backend/manage.py makemigrations                 # → exactly 10 files (ads, analytics, categories,
                                                              #   currencies, locations, lookups, moderation, search, trust, users); core=0
# 3. Apply on a fresh DB (no --fake):
uv run python src/backend/manage.py migrate                       # advisory-locked via migrate_locked.main() (migrate_locked.py:14-30)
# 4. Run the extracted seed/trigger commands (idempotent):
uv run python src/backend/manage.py setup_search_triggers
uv run python src/backend/manage.py load_exchange_rates
uv run python src/backend/manage.py load_catalog --no-rewrite     # already a committed command
# 5. Gate:
uv run python src/backend/manage.py makemigrations --check --dry-run   # V1: exits 0, "No changes detected"
```

### Phase 2 — Existing-DB reconciliation (dev `make up` with persisted `postgres_data`)

Same as Phase 1 steps 1-2, then step 3 becomes `--fake` (the schema already exists; `--fake` only writes `django_migrations` rows):

```bash
uv run python scripts/consolidate_migrations.py --force
uv run python src/backend/manage.py makemigrations
uv run python src/backend/manage.py migrate --fake            # reconcile django_migrations to the 10 initials
uv run python src/backend/manage.py setup_search_triggers      # idempotent (OR REPLACE / DROP IF EXISTS)
uv run python src/backend/manage.py load_exchange_rates      # idempotent (update_or_create)
```

### ⚠️ The current `make consolidate-force` is INCOMPLETE

`Makefile:175-178` defines `consolidate-force` as `consolidate_migrations.py --force` → `makemigrations` → `migrate` (via the `Makefile:141-142` `migrate` target = `docker compose run --rm migrate`). **This is `migrate`, not `migrate --fake`** (verified against Makefile:141-142, 175-178 and `docker-compose.yml:31-53`). Two consequences:
1. On an **existing** dev DB it exits 1 (`relation already exists`) — `docs/ops/migration-workflow.md:226-229` claiming `--fake` is **stale/inaccurate**. Either `make clean` (drop volume) first, or use the Phase 2 `--fake` path above.
2. It does **not** run `setup_search_triggers` / `load_exchange_rates` — so even on a fresh DB the squashed state silently drops FTS triggers + currency rates. **Phase 0 extraction + command wiring (Step 3 above) must be completed and committed before `make consolidate-force` is run.**

### Verification gate (TST-005, spec §15) — exact commands & pass criteria

| Check | Command | Pass criterion |
|-------|---------|----------------|
| V1 drift | `manage.py makemigrations --check --dry-run` | exit 0, "No changes detected" |
| V2 idempotency | `manage.py migrate --noinput` (run twice) | 2nd run prints "No migrations to apply." |
| V3 fresh-DB | `make clean` → `make up` (or fresh volume) → entrypoint migrate | exits 0 from the 10 `0001_initial` only |
| V4 existing-DB | dev `migrate --fake` after wipe+regen | `django_migrations` lists 10 initials; subsequent `migrate` no-op |
| V5 regression | `make test` (fast gate) + `make test-all` | all previously-green tests stay green |
| V6 CI parity | `ci.yml` test job | `-m "not seed" -n auto --dist loadgroup` exits 0 |

`test_migrations.py` (TST-005, `apps/core/tests/test_migrations.py:15-88`) encodes V1 (`test_makemigrations_check`, :20-49) and V2 (`test_migration_idempotency`, :52-88); both are `pytestmark = [django_db, slow, integration]` and excluded from the fast gate via `PYTEST_SKIP_MARKERS=seed` only — `test` is not `seed`, so they **do** run in `make test` and are the real DoD.

### Wiring into entrypoints so Option-B/seed paths keep working (spec §3 Phase 2)

- **Test (`docker/entrypoint-test.sh`):** currently runs only `migrate_locked.main()` (line 33) → `compilemessages` (line 37) → `pytest` (line 56). For either Option B (schema introspection) or a squashed migrate to keep search + price tests green, an autouse pytest fixture (or an added entrypoint step after `migrate`) must call `setup_search_triggers` + `load_exchange_rates` after the schema is created.
- **Dev/Prod-like (`docker-compose.yml:31-53` `migrate`):** the `migrate` one-shot uses `config.settings.prod` and runs `migrate_locked.main()` (advisory-lock ID 100, session-scoped — `apps/core/enums.py` `AdvisoryLockId.MIGRATE`; `advisory_lock.py:17-62`). `make up` (Makefile:77-79) then runs the `load_catalog` one-shot (`entrypoint-catalog.sh`, final line: `manage.py load_catalog --no-rewrite`), `create_admin`, and `seed` in dependency order: `db → migrate → load_catalog → create_admin/seed → web/bot`. After squash, `migrate` (or a sibling one-shot) must also run `setup_search_triggers` + `load_exchange_rates` before `web`/`bot` start.

---

## 7. Assumptions

| # | Assumption | Confidence | Grounding |
|---|-----------|-----------|-----------|
| A1 | Dev + test DBs are disposable; preserving history across runs is not required. | High | `docs/ops/migration-workflow.md:27`; `13_test-env-acceleration_spec.md:235 A1` (Problem_02.md). |
| A2 | Only the latest schema state is material in dev/test; ordered migration history is not. | High | `13_test-env-acceleration_spec.md:236 A2`. |
| A3 | Production keeps full migration history; squashing is dev/test-only. | High | `13_test-env-acceleration_spec.md:237 A3`; `migration-workflow.md:26-29`; `docker-compose.yml:31-53` `migrate` uses `prod` settings. |
| A4 | `consolidate_migrations.py --force` is the sanctioned wipe mechanism (no hand-rewriting). | High | `scripts/consolidate_migrations.py:21-171`; `13_test-env-acceleration_spec.md:351 R4/D2/C7`. |
| A5 | `Ad.Meta.indexes` (lines 252-313) and `Ad.Meta.constraints` (lines 314-341) are the source of truth the auto-generated migration will reproduce. | High | verified on disk (`ads/models.py:250-341`); matches migration 0002/0006/0011 AddIndex/AddConstraint names. |
| A6 | The 3 `CREATE INDEX CONCURRENTLY` in ads/0008 are redundant on a fresh/empty dev/test DB (standard `CREATE INDEX` from `Meta.indexes` is equivalent or faster). | High | PG18 `CREATE INDEX CONCURRENTLY IF NOT EXISTS` supported; dev/test DB created empty (`13_test-env-acceleration_spec.md:235 R8`). |
| A7 | No migration embeds live model imports, network calls, or FS mutations (the `backfill_translations` Google-Translate call was already extracted to a command). | High | grep `deep_translator|GoogleTranslator|requests\.|httpx|cursor.execute|from apps\..*\.models` over `*/migrations/0*.py` → 0; `backfill_translations.py` command confirmed on disk. |
| A8 | `currencies/0001` seed rates are load-bearing: `PriceNormalizer` (price_normalizer.py:92-102) raises without them, and `test_price_normalizer` asserts them with no fixture. | High | verified on disk; root `conftest.py` creates no `ExchangeRate`; no `django_db_setup`/`MIGRATION_MODULES` override anywhere. |
| A9 | `backfill_translations` + `load_catalog` are already extracted to management commands; `setup_search_triggers` + `load_exchange_rates` are NOT yet on disk and must be authored in Phase 0. | High | file-system listing of `ads/management/commands/` and `currencies/management/commands/`. |
| A10 | `MIGRATION_MODULES` is currently unset in all settings (`config/settings/test.py` is 51 lines, no such setting); grep over `src/backend/config/settings/*.py` → 0 matches. | High | verified on disk (test.py:1-51). |
| A11 | `make consolidate-force` runs `migrate` (not `--fake`); the `--fake` instruction in `migration-workflow.md:226` is stale. | High | verified against `Makefile:141-142,175-178` and `docker-compose.yml:31-53`. |

---

## 8. Stale-document index (explicitly flagged)

| Document | Stale claim | Reality on disk |
|----------|-------------|-----------------|
| `docs/ops/migration-workflow.md:169-181` ("Reference: App Migration Status") | ads=10, search=4, users=3, moderation=4, core=1, categories=5, locations=2, currencies absent, total=36 | ads=12, search=7, users=6, moderation=2, core=0, categories=2, locations=1, currencies=2, total=39 |
| `docs/ops/migration-workflow.md:226-229` | `make consolidate` uses `migrate --fake` | `Makefile:175-178` uses `migrate` (no `--fake`); only the existing-DB reconciliation path (§6 Phase 2) should use `--fake` |
| `docs/ops/migration-workflow.md:244-249` ("Safe vs extracted") | references `ads/0006_backfill_translations`, `categories/0005_load_catalog`, `categories/0002_seed_categories`, `locations/0002_seed_cities` | **none of these files exist**; backfill_translations + load_catalog are commands, not migrations; categories has only 2 schema files; locations has only 1 |
| `docs/ops/migration-workflow.md:315-317` ("post-consolidation goal") | references removing `0006_backfill_translations` + rewriting `0005_load_catalog` | both already removed/extracted; goal re-stated as §3 per-app disposition above |
| `.ai/plans/done/07_dev-migration-consolidation_plan_DONE.md:485-500` + TSK-003/TSK-007 | filenames `ads/0002_search_vector_triggers.py`, `ads/0005_multi_lang_search_vector.py`, `users/0002_user_chat_id.py`, `categories/0002_seed_categories.py`, `categories/0003_load_catalog.py`, `core/0001_verify_lifecycle_indexes.py` | all **do not exist**; repo was reset to fresh initials on 2026-08-04 and grown to current names. Plan is historically accurate but names are stale vs. current disk. |
| `13_test-env-acceleration_spec.md:182` (§4.3 summary) | `users: yes (0002 backfill) chat_id null backfill`; `categories: yes (0002_createcategories seed?)`; `search: FTS triggers + indexes` | users/0002 is a plain `AlterField` (no backfill); categories/0002 is `CreateModel` (no seed); FTS trigger DDL lives only in `ads`, not `search`. (The detailed glob-derived inventory in this doc's §1 supersedes the spec's §4.3 table.) |

> Note on counts cited in prose: the spec (`13_test-env-acceleration_spec.md:44-46,176-191`) mentions "~39" and "36 / ads=10" — both are approximations framing the staleness problem; the **authoritative, enumerated count is 39 files across 10 model-apps** (§1), confirmed by the recursive directory listing and cross-checked with `scripts/consolidate_migrations.py`'s own `_count_migration_files` matcher (`[0-9]*.py`). The `test_suite_audit_step2_profiling.md` report (read in full) contains **no** per-file migration inventory and **no** per-migration timings — it records only that `migrate` overhead is ~3 s under `--reuse-db`; the inventory in §1 is therefore glob/`_count_migration_files`-derived, not report-derived.

---

*End of document. This file is the in-flight "migration-squash" study deliverable referenced by `13_test-env-acceleration_spec.md` §5.5 (O3), §13, §20 (T8), and §12 (Option B). It finalizes §13 (per-app disposition) and renders the §12 Option-B parity verdict.*
