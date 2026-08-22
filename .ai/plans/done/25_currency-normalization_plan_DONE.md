---
id: 25-currency-normalization-plan
problem: Problem_04
spec: .ai/problems/25_currency-normalization_spec.md
domain: product
status: ready-for-implementation
created: 2026-08-22
stack: Python 3.14 · Django 5.2 LTS · PostgreSQL 18 · HTMX MPA · aiogram 3.x · Pydantic v2
---

# Plan 25 — Multi-Currency Price Normalization (Implementation Plan)

> **Based on:** `.ai/problems/25_currency-normalization_spec.md` (CONFIRMED, PO decisions locked)
> **DoR:** Spec §11 — all PO decisions (Q1–Q5) confirmed, research validated, impact surface mapped, migration strategy agreed.
> **Planning principle:** This plan reorganizes the spec's 13 conceptual tasks into a dependency-safe execution DAG. It is NOT a mirror of the conceptual list; tasks are regrouped along architectural boundaries (schema → service → read/write consumers → display → recompute → tests → docs) so each unit is independently implementable, reviewable, and parallel-safe.

---

## 0. Execution DAG

```
R-1  (research: migration consolidation strategy)   [prerequisite gate]
  │
  ├─ T-01  (apps/currencies app: CurrencyCode + ExchangeRate + migration)   [RISKY]
  │    └─ T-02  (Ad model migration: price_amount/currency/normalized + backfill + drop price) [RISKY, blocked by T-01]
  │         └─ T-03  (PriceNormalizer service)                              [blocked by T-01]
  │
  ├─ (parallel consumers, each: T-02 or T-02+T-03)
  │    ├─ T-04  Bot price step + PricePayload (ad_create.py, message_payloads.py)     [T-02, T-03]
  │    ├─ T-05  Web edit view + edit.html                                            [T-02, T-03]
  │    ├─ T-06  Listings + search filter/sort on normalized (listings.py, search.py) [T-02]
  │    ├─ T-07  Moderation service price_required → price_amount (auto_moderation.py) [T-02]
  │    └─ T-08  Telegram alerts formatting (immediate_alerts.py, send_alerts.py)      [T-02, T-03, T-11]
  │
  ├─ (display + saved-search)
  │    ├─ T-09  SavedSearch EUR semantics + alert_query filter                       [T-02]
  │    ├─ T-10  Seed generator + seed templates                                       [T-02]
  │    └─ T-11  format_price template filter + Python wrapper (shared formatting)     [T-02]  ← consumed by T-08, T-12
  │         └─ T-12  Templates: detail/list/dashboard/review (use format_price)      [T-11]
  │
  ├─ T-13  recompute_normalized_prices management command                            [T-03]
  │
  ├─ T-14  Test updates (ads/search/seed/moderation)                                 [T-04..T-10]
  │
  └─ T-15  Documentation updates (db-schema, db-enums, search-patterns, filter-ui, design-system, spec-index)

Critical path: R-1 → T-01 → T-02 → T-03 → T-04 → T-14
Parallel groups:
  G1: {T-01} (after R-1)
  G2: {T-02} (after T-01)
  G3: {T-03, T-06, T-07, T-09, T-10, T-11}   (T-03, T-11 depend on T-02; others on T-02 only)
  G4: {T-04, T-05, T-08, T-12}               (all depend on T-03/T-11)
  G5: {T-13}
  G6: {T-14}
  G7: {T-15}
```

---

## 1. Task Index

| ID | Title | Stage | Priority | Risk | Blocked by |
|----|-------|-------|----------|------|-----------|
| R-1 | Research: migration consolidation & backfill strategy | 0 | high | research | — |
| T-01 | Create `apps/currencies` app (CurrencyCode + ExchangeRate + migration) | 0 | high | **RISKY** (new app + migration) | R-1 |
| T-02 | Ad model migration: add currency fields, backfill BAM, drop `price` | 0 | high | **RISKY** (schema + data migration) | T-01 |
| T-03 | PriceNormalizer service (normalize_to_eur, cached) | 1 | high | medium | T-01 |
| T-04 | Bot price step + PricePayload schema | 2 | high | medium | T-02, T-03 |
| T-05 | Web edit view + edit.html currency selector | 2 | medium | low | T-02, T-03 |
| T-06 | Listings + search filter/sort on price_normalized_eur | 2 | high | medium | T-02 |
| T-07 | Moderation `price_required` uses price_amount | 2 | low | low | T-02 |
| T-08 | Telegram alert price formatting | 4 | medium | low | T-02, T-11 |
| T-09 | SavedSearch EUR semantics + alert_query filter | 3 | medium | medium | T-02 |
| T-10 | Seed generator + templates (currency-aware) | 3 | low | low | T-02 |
| T-11 | `format_price` template filter + Python wrapper | 3 | medium | low | T-02 |
| T-12 | Update price-display templates (detail/list/dashboard/review) | 4 | medium | low | T-11 |
| T-13 | `recompute_normalized_prices` management command | 5 | medium | low | T-03 |
| T-14 | Update all affected tests | 6 | high | medium | T-04..T-10, T-13 |
| T-15 | Update design & DB documentation | 7 | low | low | — (do last) |

---

# PART A — Schema & Foundation

## R-1 — Research: migration consolidation & backfill SQL strategy

| Field | Value |
|-------|-------|
| **ID** | R-1 |
| **Title** | Research the migration consolidation & BAM-backfill strategy |
| **Type** | Research (prerequisite gate) |
| **Priority** | High |
| **Blocked by** | — |
| **source_reference** | spec §5.4, §7.8, §8 R1/R8 |

**goals**
- Confirm the project's migration-workflow constraints for adding a new app (`apps/currencies`) and adding fields to `Ad` and `SavedSearch` (max-8-files-per-app consolidation, advisory-lock `migrate` service, dev-mode migration workflow).
- Confirm app-loading order / INSTALLED_APPS registration for a new app and that no circular import results (currencies has no FK to ads; ads migration depends on currencies.0001).
- Decide the exact backfill SQL/ORM strategy: `price` values are BAM (PO-03); seed the BAM→EUR rate (PO-05: 0.512) inside the data migration OR reference the seeded `ExchangeRate` row; confirm data migration runs idempotently with `--create-db` and respects the check-constraint semantics.
- Verify the `price` column drop is safe against the surviving references listed in spec §5 inventory (post-drop code update order is T-02 → consumers).
- Confirm the index requirements for `price_normalized_eur` and whether a partial/composite index is desired (spec MR-06).

**files**
- path: `.ai/plans/25_currency-normalization_plan.md` (output record)
- path: `docs/99-agent/architecture.md` (migration workflow)
- path: `docs/ops/migration-workflow.md` (if present)
- path: `pyproject.toml` / `src/backend/config/settings` (INSTALLED_APPS)
- path: `src/backend/apps/ads/migrations/` (existing latest migration to branch from)

**changes**
- action: no_code
- description: Produce a research note recording the migration strategy, backfill SQL, app registration, and index plan; approve with verdict "Go" or "Go with changes".

**acceptance_criteria**
- Documented the migration consolidation approach and app-registration steps.
- Backfill strategy recorded (seed-rate constant vs ExchangeRate reference), idempotent, PG-only.
- Verified no circular imports and correct `dependencies` on `currencies.0001_initial`.
- Decisions recorded for `price` drop safety and index shape.
- Verdict: Go or Go with changes.

---

## T-01 — Create `apps/currencies` app (CurrencyCode + ExchangeRate + seed migration)

| Field | Value |
|-------|-------|
| **ID** | T-01 |
| **Title** | Fund `apps/currencies`: CurrencyCode StrEnum + ExchangeRate model + 0001 migration |
| **Type** | Feature (new app) |
| **Priority** | High |
| **Risk** | **RISKY** (new app, INSTALLED_APPS, migration consolidation) |
| **Blocked by** | R-1 |

**description**
Create the new `apps/currencies` Django app as the single source of currency vocabulary and rate storage (spec MR-01, MR-02; PO Q5). Enumerate the three supported currencies in a `CurrencyCode` StrEnum (EUR, RSD, BAM) per project rule 10 (never plain strings). Define the `ExchangeRate` model storing `currency`, `rate_to_eur`, `effective_date`, `source`, `is_current` — designed to later accept automated updates from an official source (CR-06), with only `is_current=True` rows used by normalization (spec Assumption 7). Register the app, create a `0001_initial` migration, and seed the three fixed rates (PO-05: EUR=1.0, BAM≈0.512, RSD≈0.0105, source `manual_seed`, `is_current=True`).

**goals**
- CurrencyCode StrEnum replaces every hardcoded "BAM" string literal.
- ExchangeRate model supports current-rate lookups and future auto-update without schema change.
- Seeded initial rates make normalization/backfill deterministic.

**files**
- path: `src/backend/apps/currencies/__init__.py` (new)
- path: `src/backend/apps/currencies/apps.py` (new — CurrenciesConfig)
- path: `src/backend/apps/currencies/enums.py` (new — CurrencyCode)
- path: `src/backend/apps/currencies/models.py` (new — ExchangeRate)
- path: `src/backend/apps/currencies/migrations/0001_initial.py` (new)
- path: `src/backend/config/settings/base.py` (INSTALLED_APPS registration)

**changes**
- action: add_file — `apps/currencies/__init__.py`, `apps/currencies/apps.py` (CurrenciesConfig with `default_auto_field`, `name = "apps.currencies"`, `verbose_name`).
- action: add_class — `CurrencyCode(StrEnum)` in `apps/currencies/enums.py` with members `EUR="EUR"`, `RSD="RSD"`, `BAM="BAM"`.
- action: add_class — `ExchangeRate` in `apps/currencies/models.py`:
  - fields: `currency` (CharField/EnumField storing CurrencyCode, unique), `rate_to_eur` (DecimalField, e.g. `max_digits=14, decimal_places=8`), `effective_date` (DateField), `source` (CharField), `is_current` (BooleanField default True).
  - uniqueness: enforce at most one `is_current` row per currency via `UniqueConstraint`/business guard.
- action: add_migration — `0001_initial` creating `ExchangeRate` and a data migration seeding EUR=1.0, BAM=0.512, RSD=0.0105 with `source="manual_seed"`, `is_current=True`.
- action: edit — register `apps.currencies` in `INSTALLED_APPS`.

**acceptance_criteria**
- `CurrencyCode` StrEnum has exactly EUR/RSD/BAM.
- `ExchangeRate` model and `0001_initial` migration exist; running `makemigrations --check` is clean.
- Seeded rows present for EUR/BAM/RSD with `is_current=True` and source `manual_seed`.
- App imported via `django.setup()` in the bot process without circular import.
- `docker compose ... run --rm test --collect-only` succeeds.

---

## T-02 — Ad model migration: add currency fields, backfill BAM, drop `price`

| Field | Value |
|-------|-------|
| **ID** | T-02 |
| **Title** | Ad price three-field model: price_amount / price_currency / price_normalized_eur + backfill + drop price |
| **Type** | Schema + data migration |
| **Priority** | High |
| **Risk** | **RISKY** (schema migration + backfill + column drop) |
| **Blocked by** | T-01 |
| **source_reference** | spec MR-03..MR-08, §8 R1/R2/R7 |

**description**
Replace the single `price` `PositiveIntegerField` (BAM units) on `Ad` with the three-field currency model from Problem_04: `price_amount` (DecimalField max_digits=10 decimal_places=2, nullable — source of truth, CR-04), `price_currency` (CurrencyCode column defaulting to EUR, MR-04), and `price_normalized_eur` (DecimalField max_digits=12 decimal_places=4, nullable, derived not user-editable, CR-05/MR-05). Add the index on `price_normalized_eur` (MR-06). Backfill existing rows assuming all legacy `price` values are BAM (PO-03): `price_currency=BAM`, `price_amount=old_price`, `price_normalized_eur = old_price × rate_BAM_to_EUR` (using the T-01 seeded rate or the recorded constant per R-1). Preserve `price_normalized_eur = NULL` when `price_amount` is NULL. Finally drop the legacy `price` column (spec Assumption 4) only after consumers are re-pointed (T-04..T-10) — sequence the drop in a separate migration committed after the consumer tasks, or keep it column-parked until consumers land (per R-1 verdict).

**goals**
- Backward-compatible schema evolution for the two-process, one-DB contract.
- Source of truth = seller's original amount + currency.
- Derived normalized EUR enables cross-currency filter/sort without per-query conversion.

**files**
- path: `src/backend/apps/ads/models.py` (Ad.price → three fields + index)
- path: `src/backend/apps/ads/migrations/` (add-columns/backfill migration, then drop-price migration)
- path: `src/backend/apps/ads/models.py` Meta.indexes (price_normalized_eur index)

**changes**
- action: edit — replace `Ad.price` field declaration with `price_amount`, `price_currency`, `price_normalized_eur` (types per spec Constraint 10).
- action: add_index — `price_normalized_eur` on `Ad` (MR-06).
- action: add_migration — `000X_add_currency_fields.py`: `AddField`×3, `RunPython` backfill (BAM assumption), index.
- action: add_migration — `000Y_drop_price.py`: `RemoveField(price)` — **only after consumers (T-04..T-10) re-pointed** (sequence per R-1 verdict).

**acceptance_criteria**
- Migration adds the three columns and backfills: legacy rows get `price_currency=BAM`, `price_amount=old`, `price_normalized_eur=old×0.512` (or seeded rate), NULL-amount stays NULL-normalized.
- `price_normalized_eur` indexed.
- Post-drop migration removes `price`; `makemigrations --check` clean; `--create-db` passes.
- `price_amount`/`price_currency`/`price_normalized_eur` are readable on `Ad` instances (bot + web processes share the same DB).

---

# PART B — Core Service

## T-03 — PriceNormalizer service

| Field | Value |
|-------|-------|
| **ID** | T-03 |
| **Title** | `PriceNormalizer` service (normalize_to_eur, cached current-rate lookup) |
| **Type** | Feature (service) |
| **Priority** | High |
| **Risk** | Medium |
| **Blocked by** | T-01 |
| **source_reference** | spec Task 3, §5.3, §8 R2 |

**description**
Create a small, focused service in `apps/currencies/services/` (per project pattern of small service modules) exposing a `PriceNormalizer` class with a method like `normalize_to_eur(amount: Decimal, currency: CurrencyCode) -> Decimal` that multiplies the amount by the **current** `ExchangeRate.rate_to_eur` (CR-07, spec §5.3 Approach B — app-level). Fetch the current rate per currency from the DB, cached with a 5-minute TTL mirroring the `ModerationCriteria` cache pattern (`apps/core/utils/cache.py`: `get_cached_*`/`set_cached_*`). If no `is_current` rate exists for a currency, raise a domain error (do not silently fail — spec Task 3). Round using `decimal.ROUND_HALF_UP`; never round in storage (keep 4-decimal normalized value, spec R2). Because both processes (web + bot) share one DB, the 5-minute cache is acceptable (spec Constraint 1).

**goals**
- Single normalization entry point used by bot create, web edit, and the recompute command.
- Deterministic, cached, PG-only; prevents duplicate normalization logic.
- Explicit failure when a currency has no rate.

**files**
- path: `src/backend/apps/currencies/services/__init__.py` (new)
- path: `src/backend/apps/currencies/services/price_normalizer.py` (new — PriceNormalizer)
- path: `src/backend/apps/currencies/services/exceptions.py` (new — ExchangeRateNotFound / normalization error)

**changes**
- action: add_class — `PriceNormalizer` in `apps/currencies/services/price_normalizer.py` with method `normalize_to_eur(amount, currency) -> Decimal`, a cached `_get_current_rate(currency)` (5-min TTL), and `ROUND_HALF_UP` rounding.
- action: add_class — domain exception for missing rate.
- action: no_code — reference `apps/core/utils/cache.py` cache utilities for the TTL pattern.

**acceptance_criteria**
- `normalize_to_eur` returns amount × current rate for EUR/BAM/RSD; EUR preserves amount (rate 1.0).
- Missing rate for an unknown currency raises the domain error (tested).
- Rate lookup is cached (5-min TTL); cache invalidation on rate change is supported (recompute/admin path).
- Deterministic rounding; `price_normalized_eur` retains 4 decimals.

---

# PART C — Read/Write Consumers

## T-04 — Bot price step + PricePayload schema

| Field | Value |
|-------|-------|
| **ID** | T-04 |
| **Title** | Bot currency inline-keyboard step + PricePayload (amount + currency) |
| **Type** | Feature |
| **Priority** | High |
| **Risk** | Medium |
| **Blocked by** | T-02, T-03 |
| **source_reference** | spec BR-01..BR-04, §5.5, PO-01/Q1 |

**description**
Update the Telegram bot ad-creation dialog to capture **currency + amount** (BR-01). Present an inline keyboard with the three currency options (EUR, RSD, BAM) with EUR preset/selected first; on selection ask for the numeric amount; "Skip" skips both currency and amount and leaves `price_amount`/`price_normalized_eur` NULL (BR-04). Validate via the updated Pydantic `PricePayload` at the bot input boundary (project rule 11): `price_amount: Decimal | None` and `price_currency: CurrencyCode` (Pydantic v2, spec §5.5, Constraint 5). Store selections in the ad DRAFT row / FSM state (spec Constraint 9), display in the preview, and pass `price_amount` + `price_currency` into `update_ad_and_moderate()`, which calls `PriceNormalizer.normalize_to_eur` to compute `price_normalized_eur` before saving (BR-03).

**goals**
- Seller selects currency + numeric amount; skip leaves price unset.
- Pydantic validates amount/currency at the boundary.
- `price_normalized_eur` computed at submission using the current rate.

**files**
- path: `src/telegram_bot/schemas/message_payloads.py` (PricePayload: `price` → `price_amount: Decimal|None` + `price_currency: CurrencyCode`)
- path: `src/telegram_bot/handlers/ad_create.py` (price step handler: inline keyboard, amount input, preview, `update_ad_and_moderate` call)

**changes**
- action: edit — `PricePayload` in `message_payloads.py`: replace `price: int|None` with `price_amount: Decimal|None` + `price_currency: CurrencyCode` (with validation: amount ≥ 0; currency in CurrencyCode).
- action: add_code — in `ad_create.py` price-step handler: send currency inline keyboard (EUR/RSD/BAM, EUR first), persist selection, then prompt for numeric amount; "Skip" → set both to None.
- action: add_code — extend `update_ad_and_moderate` to accept `price_amount`/`price_currency`, call `PriceNormalizer.normalize_to_eur`, and set `price_normalized_eur` before save.

**acceptance_criteria**
- Bot flow: currency selection → amount → preview → draft save produce correct `price_amount`/`price_currency`/`price_normalized_eur`; skip leaves them NULL.
- `PricePayload` rejects invalid currency and negative amounts via Pydantic.
- `update_ad_and_moderate` computes normalized EUR when amount + currency present.
- Existing bot create tests updated to the new payload shape (see T-14).

---

## T-05 — Web edit view + edit.html currency selector

| Field | Value |
|-------|-------|
| **ID** | T-05 |
| **Title** | Seller edit view: accept price_amount + price_currency, recompute normalized |
| **Type** | Feature |
| **Priority** | Medium |
| **Risk** | Low |
| **Blocked by** | T-02, T-03 |
| **source_reference** | spec Task 6 |

**description**
Update `apps/ads/views/edit.py` to accept `price_amount` and `price_currency` from POST, recompute `price_normalized_eur` via `PriceNormalizer` when the amount/currency changes, and persist all three fields. Keep existing behavior that price/photo edits stay published while text edits trigger re-moderation. Update `templates/ads/edit.html` to present a currency selector (pre-populated with the current ad currency) alongside the amount input.

**goals**
- Seller can set/change amount + currency on the web; normalized value stays in sync.
- Editor preserves the publish/re-moderation semantics.

**files**
- path: `src/backend/apps/ads/views/edit.py`
- path: `src/backend/apps/ads/templates/ads/edit.html`

**changes**
- action: edit — `edit.py`: read `price_amount` + `price_currency` from POST; if either changed, call `PriceNormalizer.normalize_to_eur` and persist `price_amount`, `price_currency`, `price_normalized_eur`.
- action: edit — `edit.html`: add currency `<select>` bound to `ad.price_currency`, retain amount input; label updated from "Price (BAM)".

**acceptance_criteria**
- Editing amount/currency persists and recomputes `price_normalized_eur`.
- Currency selector pre-populated; label no longer hardcodes BAM.
- Publish/re-moderation behavior unchanged.

---

## T-06 — Listings + search filter/sort on `price_normalized_eur`

| Field | Value |
|-------|-------|
| **ID** | T-06 |
| **Title** | Web filter & sort re-point to price_normalized_eur |
| **Type** | Refactor (behavior remap) |
| **Priority** | High |
| **Risk** | Medium |
| **Blocked by** | T-02 |
| **source_reference** | spec WR-01, WR-02, Q3, §5.6 |

**description**
Update the listing and search views so price-range filters and price sorting operate on the EUR-normalized value (CR-10). In `apps/ads/views/listings.py`, change the `price__gte`/`price__lte` filter arguments to `price_normalized_eur__gte`/`__lte`, and the `order_by("price")`/`order_by("-price")` sort targets to `price_normalized_eur` (resp. `-price_normalized_eur`) for the `PRICE_LOW`/`PRICE_HIGH` `AdSort` cases (keep enum values per Q3). In `apps/search/views/search.py`, re-point the price filters to `price_normalized_eur`. User-facing min/max price inputs are interpreted as EUR-equivalent values.

**goals**
- Cross-currency price filtering/sorting uses the normalized column.
- `AdSort` enum values unchanged; only the `.order_by()` target changes (Q3).

**files**
- path: `src/backend/apps/ads/views/listings.py`
- path: `src/backend/apps/search/views/search.py`
- path: `src/backend/apps/core/enums.py` (only if a field→column mapping helper is extracted; otherwise no change)

**changes**
- action: edit — `listings.py`: filter `price_normalized_eur__gte`/`__lte`; sort `price_normalized_eur` / `-price_normalized_eur`.
- action: edit — `search.py`: filter `price_normalized_eur__gte`/`__lte`.

**acceptance_criteria**
- Listings/search price filtering uses `price_normalized_eur`; sorting for PRICE_LOW/HIGH uses the normalized column.
- POST validation reads min/max as EUR values.

---

## T-07 — Moderation service `price_required` → `price_amount`

| Field | Value |
|-------|-------|
| **ID** | T-07 |
| **Title** | Moderation price-missing check uses price_amount |
| **Type** | Refactor |
| **Priority** | Low |
| **Risk** | Low |
| **Blocked by** | T-02 |
| **source_reference** | spec MOD-01, MOD-02 |

**description**
In `apps/moderation/services/auto_moderation.py`, re-point the `price_required` checks that currently reference the legacy `price` column (spec impact list) to `price_amount`. Do **not** add any new price-range moderation criteria (MOD-02 / technical-spec.md line 47).

**goals**
- `price_required` reflects `price_amount IS NULL` semantics after the schema change.
- No new moderation scope.

**files**
- path: `src/backend/apps/moderation/services/auto_moderation.py`

**changes**
- action: edit — replace `ad.price is None` checks in the moderation functions with `ad.price_amount is None`.

**acceptance_criteria**
- `price_required` uses `price_amount`; no new price criteria.
- Moderation tests updated (T-14).

---

## T-08 — Telegram alert price formatting

| Field | Value |
|-------|-------|
| **ID** | T-08 |
| **Title** | Immediate + scheduled alert messages format original price + currency |
| **Type** | Feature |
| **Priority** | Medium |
| **Risk** | Low |
| **Blocked by** | T-02, T-11 |
| **source_reference** | spec AL-01, PO-02/Q2, PO Q4, §5.6, Assumption 11 |

**description**
Update `apps/search/services/immediate_alerts.py` and the `send_alerts` management command so alert messages format the price as `"{amount} {currency}"` from the ad's original `price_amount` + `price_currency` (PO Q4: original currency, consistent with detail page) instead of the hardcoded `f"{ad.price} BAM"`. Reuse the `format_price` helper produced by T-11 via a Python-callable wrapper so template and bot formatting stay consistent (spec Assumption 9/11, Task 10). Handle the NULL-price case (no price → omit/format gracefully).

**goals**
- Alerts show seller's original amount + currency label.
- Single shared formatting source between templates and bot messages.

**files**
- path: `src/backend/apps/search/services/immediate_alerts.py`
- path: `src/backend/apps/search/management/commands/send_alerts.py`

**changes**
- action: edit — both files use the shared `format_price` Python wrapper (from T-11) instead of inline `... BAM`.
- action: no_code — guard `price_amount is None` → omit price segment.

**acceptance_criteria**
- Alert messages render `"{amount} {currency}"` from original fields; no hardcoded BAM.
- NULL price handled gracefully.

---

# PART D — Display & Saved-Search

## T-09 — SavedSearch EUR semantics + alert_query filter

| Field | Value |
|-------|-------|
| **ID** | T-09 |
| **Title** | SavedSearch min/max as EUR + alert_query on price_normalized_eur |
| **Type** | Refactor + data migration |
| **Priority** | Medium |
| **Risk** | Medium (data migration converts existing BAM saved searches) |
| **Blocked by** | T-02 |
| **source_reference** | spec WR-04, §8 R7, PO-04/Q3 |

**description**
Interpret `SavedSearch.min_price`/`max_price` (unchanged `PositiveIntegerField`s) as **EUR-equivalent** values (WR-04, PO-04). Update `apps/search/services/alert_query.py` to filter on `price_normalized_eur__gte`/`__lte` instead of the legacy `price` column. Add a data migration converting existing saved-search min/max from BAM to EUR: `new = old × 0.512` (seed BAM rate, PO-04/PO-05). Update the saved-search edit/modal template labels from "BAM" to "EUR".

**goals**
- Saved-search price filters operate on EUR-normalized values.
- Existing BAM saved searches converted once during migration.
- UI labels reflect EUR.

**files**
- path: `src/backend/apps/search/models.py` (field doc/comment update only — no column change)
- path: `src/backend/apps/search/services/alert_query.py`
- path: `src/backend/apps/search/migrations/` (data migration for saved-search conversion)
- path: `src/backend/apps/cabinet/templates/cabinet/saved_search_edit.html` (labels)
- path: `src/backend/apps/search/templates/search/partials/save_search_modal.html` (labels)

**changes**
- action: edit — `alert_query.py`: change price filters to `price_normalized_eur__gte`/`__lte`.
- action: data_migration — convert existing `min_price`/`max_price` (BAM → EUR × 0.512).
- action: edit — template labels "BAM" → "EUR".

**acceptance_criteria**
- Alert query matches on `price_normalized_eur`; converted saved searches yield correct alerts.
- Modal/edit labels say EUR.
- Data migration idempotent with `--create-db`.

---

## T-10 — Seed generator + templates (currency-aware)

| Field | Value |
|-------|-------|
| **ID** | T-10 |
| **Title** | Seed ad generator emits amount + currency + normalized; templates drop hardcoded BAM |
| **Type** | Feature (dev data) |
| **Priority** | Low |
| **Risk** | Low |
| **Blocked by** | T-02 |
| **source_reference** | spec SD-01, SD-02, Assumption 8, §8 R6 |

**description**
Update the seed `AdGenerator` (`_generate_price`) to return both a `price_amount` and `price_currency` (seed ads use **EUR** by default per Assumption 8, so `price_normalized_eur = price_amount`), and set the three fields on generated `Ad` rows. Remove the hardcoded "BAM" from seed description templates, using the seed ad's currency variable via the shared `format_price` helper (T-11) where applicable.

**goals**
- Seed data reflects the new price model; seed workflow stays green.
- No hardcoded BAM in seed descriptions.

**files**
- path: `src/backend/apps/seed/services/seed_service.py`
- path: `src/backend/apps/seed/generators/ads.py` (`_generate_price` → amount + currency)
- path: `src/backend/apps/seed/fixtures/ads_templates.json` / template strings

**changes**
- action: edit — `ads.py` `_generate_price()` returns `(amount, currency)`; set `price_currency`, `price_amount`, `price_normalized_eur` on generated ads.
- action: edit — seed templates parameterize currency instead of hardcoding "BAM".

**acceptance_criteria**
- Generated seed ads carry `price_amount`/`price_currency`/`price_normalized_eur` (EUR default).
- Seed template text has no hardcoded "BAM" suffix.
- `seed` marker tests updated (T-14).

---

## T-11 — `format_price` template filter + Python wrapper

| Field | Value |
|-------|-------|
| **ID** | T-11 |
| **Title** | Shared `format_price` render helper (template filter + Python callable) |
| **Type** | Feature (display) |
| **Priority** | Medium |
| **Risk** | Low |
| **Blocked by** | T-02 |
| **source_reference** | spec Task 7, Assumption 9, §8 R5 |

**description**
Create a single `format_price` render helper that turns an `Ad` (or an `amount`+`currency` pair) into the display string `"{amount} {currency}"` using the ad's original `price_amount` + `price_currency` (PO-02). Implement it as a Django template filter in a new template-tags module (project rule 3: UI formatting lives in template layer) AND expose an equivalent Python callable wrapper so the bot alert messages (T-08) reuse the exact same formatting. Use Django `intcomma`/`floatformat` for display (spec Out-of-scope 5). Handle `price_amount is None` (return empty).

**goals**
- One formatting source for templates and bot messages.
- No duplicated price-format logic.

**files**
- path: `src/backend/apps/ads/templatetags/__init__.py` (ensure exists)
- path: `src/backend/apps/ads/templatetags/price_tags.py` (new — `format_price` filter + `format_price_value` Python callable)
- path: `src/backend/apps/ads/templatetags/` loaded via app config

**changes**
- action: add_class — `format_price(ad)` template filter + `format_price_value(amount, currency)` Python function in `price_tags.py`.
- action: no_code — `@register.filter`; load tag in consuming templates (T-12).

**acceptance_criteria**
- `format_price` renders `"{amount} {currency}"` from `price_amount`/`price_currency`; empty for NULL price.
- Python wrapper importable and used by T-08 without duplication.

---

## T-12 — Update price-display templates

| Field | Value |
|-------|-------|
| **ID** | T-12 |
| **Title** | Detail / list / dashboard / review templates use format_price |
| **Type** | Refactor (templates) |
| **Priority** | Medium |
| **Risk** | Low |
| **Blocked by** | T-11 |
| **source_reference** | spec WR-03, Task 7, §5.6, R5 |

**description**
Replace every hardcoded `{{ ad.price }} BAM` with the `format_price` filter on the four display templates: `detail.html`, `ad_list.html`, `dashboard.html`, `review.html` (spec impact list). Load the `price_tags` tag library and call `{{ ad|format_price }}`. No hardcoded "BAM" remains in these templates.

**goals**
- Price displays the seller's original amount + currency across all buyer/moderation surfaces.
- No hardcoded BAM literals.

**files**
- path: `src/backend/apps/ads/templates/ads/detail.html`
- path: `src/backend/apps/ads/templates/ads/ad_list.html`
- path: `src/backend/apps/ads/templates/cabinet/dashboard.html` (dashboard price)
- path: `src/backend/apps/moderation/templates/.../review.html`

**changes**
- action: edit — each template: `{% load price_tags %}` + replace `{{ ad.price }} BAM` with `{{ ad|format_price }}`.

**acceptance_criteria**
- No `{{ ad.price }} BAM` or `{price} BAM` literals in the four templates.
- Rendered pages show amount + currency label.

---

# PART E — Recompute

## T-13 — `recompute_normalized_prices` management command

| Field | Value |
|-------|-------|
| **ID** | T-13 |
| **Title** | Mass-recompute command (advisory lock + batch bulk_update) |
| **Type** | Feature (command) |
| **Priority** | Medium |
| **Risk** | Low |
| **Blocked by** | T-03 |
| **source_reference** | spec Task 11, §5.4, CR-09 |

**description**
Add a `recompute_normalized_prices` management command following the canonical `archive_sweep.py` pattern: `AdvisoryLockId.RECOMPUTE_NORMALIZED_PRICES` (value 12, next free), `transaction.atomic()`, `--dry-run` flag, batch processing, `bulk_update()`/queryset `.update()`, `logging.getLogger(__name__)`. The command iterates published/non-draft ads in batches, computes `price_normalized_eur` per row via `PriceNormalizer` using the **current** rate for the row's `price_currency`, and updates only rows whose normalized value differs (CR-09, Assumption 7). Add the new lock ID to `AdvisoryLockId` in `apps/core/enums.py` and record the allocation where lock IDs are documented.

**goals**
- Admin/cron-triggered re-normalization after rate changes.
- Idempotent, concurrency-safe via advisory lock.

**files**
- path: `src/backend/apps/currencies/management/commands/recompute_normalized_prices.py` (new)
- path: `src/backend/apps/core/enums.py` (AdvisoryLockId.RECOMPUTE_NORMALIZED_PRICES = 12)
- path: lock-IDs documentation (architecture.md/ops)

**changes**
- action: add_class — `Command(BaseCommand)` implementing advisory lock + batch recompute + `--dry-run`.
- action: edit — add `RECOMPUTE_NORMALIZED_PRICES = 12` to `AdvisoryLockId`.

**acceptance_criteria**
- Command recomputes `price_normalized_eur` from current rates; `--dry-run` shows count without writing.
- Advisory lock prevents concurrent runs; bulk updates efficient.

---

# PART F — Tests

## T-14 — Update all affected tests

| Field | Value |
|-------|-------|
| **ID** | T-14 |
| **Title** | Re-point/replace tests referencing `ad.price` or hardcoded BAM |
| **Type** | Test update |
| **Priority** | High |
| **Risk** | Medium (broad test surface) |
| **Blocked by** | T-04, T-05, T-06, T-07, T-08, T-09, T-10, T-13 |
| **source_reference** | spec Task 13, §8 R9, Constraint 6 (production code is king) |

**description**
Update every test that references the legacy `price` field or hardcodes the "BAM" label to the new model and display behavior. This is a single coordinated ownership task (not per-feature) so the suite stays green after all consumers land. Concretely: `seed/tests/test_seed.py` assertions on `ad.price` → `ad.price_amount` (+ currency/normalized); `search/tests/test_alert_query.py` price-filter tests → `price_normalized_eur`; `ads/tests/test_listings_context.py` filter/sort field names → normalized; moderation tests → `price_amount`; bot create tests → new `PricePayload`/currency-flow shape; any template/snapshot assertions on `... BAM` → `format_price` output. Add focused tests for `PriceNormalizer.normalize_to_eur`, the `format_price` filter, the `recompute_normalized_prices` command (`--dry-run` + recompute), and the backfill assumption (BAM → EUR). Per project rule 2, if a test conflicts with the new architecture, fix the test, never distort production code.

**goals**
- Whole suite green after the migration.
- New behavior covered (normalizer, filter, recompute, backfill).

**files**
- path: `src/backend/apps/seed/tests/test_seed.py`
- path: `src/backend/apps/search/tests/test_alert_query.py`
- path: `src/backend/apps/ads/tests/test_listings_context.py`
- path: `src/backend/apps/moderation/tests/test_auto_moderation.py`
- path: `src/telegram_bot/tests/` (create/price-step tests)
- path: `src/backend/apps/currencies/tests/test_price_normalizer.py` (new)
- path: `src/backend/apps/ads/tests/test_price_format.py` (new, format_price)
- path: `src/backend/apps/currencies/tests/test_recompute_command.py` (new)

**changes**
- action: edit — re-point existing `price` assertions to `price_amount`/`price_normalized_eur`.
- action: add_test — new tests for normalizer, format_price, recompute command, backfill.

**acceptance_criteria**
- `grep -rn "ad\.price\b" src/` returns no legacy-field references in tests (except intentional, documented).
- `grep -rni "price.*BAM\|BAM"` in the touched assertion/template files shows no hardcoded BAM expectations (dev-only seed descriptions exempt per Assumption 8 if currency-parameterized).
- Full suite passes with `--create-db`; new normalizer/filter/recompute tests pass.

---

# PART G — Documentation

## T-15 — Update design & DB documentation

| Field | Value |
|-------|-------|
| **ID** | T-15 |
| **Title** | Refresh db-schema, db-enums, search-patterns, filter-ui, design-system, ui-patterns, spec-index |
| **Type** | Documentation |
| **Priority** | Low |
| **Risk** | Low |
| **Blocked by** | — (do last, reflects final state) |
| **source_reference** | spec §1 current-state table, §5.6, project rules 1 & 14 |

**description**
Update documentation to reflect the new price model and EUR default: `db-schema.md` (Ad price fields, `price` column removed, note diff vs old "currency removed — YAGNI" line; `ExchangeRate` table), `db-enums.md` (`CurrencyCode` StrEnum), `search-patterns.md` / `filter-ui.md` (filters/sort on `price_normalized_eur`, EUR labels), `docs/01-spec/design-system.md` + `docs/06-design-system/components.md`/`tokens.md` + `docs/01-spec/ui-patterns.md` (price examples BAM → EUR/original-currency). `spec-index.md`: move "multi-currency" from deferred to implemented. All prose in English (rule 1).

**goals**
- Docs match implemented behavior; no stale "BAM-only" or "currency deferred" claims.
- Future agents understand the normalization model.

**files**
- path: `docs/02-database/db-schema.md`
- path: `docs/02-database/db-enums.md`
- path: `docs/01-spec/search-patterns.md`
- path: `docs/01-spec/filter-ui.md`
- path: `docs/01-spec/design-system.md`
- path: `docs/06-design-system/components.md`, `tokens.md`
- path: `docs/01-spec/ui-patterns.md`
- path: `docs/01-spec/spec-index.md`

**changes**
- action: edit — each doc to the new price/currency model; price examples updated; spec-index moves multi-currency to implemented.

**acceptance_criteria**
- No doc claims "currency column removed / multi-currency deferred" contradicting the implemented model.
- Price examples show EUR or original-currency labels; `ExchangeRate` and `CurrencyCode` documented.

---

## 2. Overall Acceptance Criteria

1. `CurrencyCode` StrEnum (EUR/RSD/BAM) and `ExchangeRate` model + seeded migration exist in `apps/currencies`.
2. `Ad` carries `price_amount`/`price_currency`/`price_normalized_eur` (indexed); legacy `price` dropped after consumers re-pointed; backfill assumes BAM (×0.512 → EUR).
3. `PriceNormalizer.normalize_to_eur` used by bot create, web edit, and the recompute command; 5-min cached current-rate lookup; explicit error on missing rate.
4. Bot captures currency + amount (inline keyboard, EUR default) and computes normalized EUR; skip leaves price NULL.
5. Web listing/search filter & sort on `price_normalized_eur`; `AdSort` enum values unchanged.
6. SavedSearch min/max interpreted as EUR; `alert_query` filters on `price_normalized_eur`; existing BAM saved searches converted in migration.
7. Detail/list/dashboard/review templates use `format_price`; alerts use the same helper; no hardcoded "BAM" outside dev-only seed templates.
8. `recompute_normalized_prices` command (`AdvisoryLockId=12`, `--dry-run`) recomputes from current rates.
9. Full suite passes with `--create-db`; new normalizer/filter/recompute tests pass.
10. Docs reflect the new model (EUR default, multi-currency implemented).

## 3. Risk & Rollout Notes

- **Schema tasks (T-01, T-02) are the highest risk.** They are hard-blocked behind R-1 and must land before any consumer; the `price` drop is sequenced via a separate migration after consumers (T-04..T-10) — keep it parked until those tasks pass locally with `--create-db`.
- **Parallelism:** G3 (T-03/T-06/T-07/T-09/T-10/T-11) and G4 (T-04/T-05/T-08/T-12) are independent within their groups once their prerequisites land, but share files with the `price` column — coordinate so the post-drop migration is applied only after all consumers are re-pointed.
- **Backfill correctness (R1):** the BAM assumption is low-risk per spec §8; the seed rate is a constant (PO-05) so the backfill migration is deterministic. Use the same constant in the SavedSearch conversion (T-09) to keep results consistent.
- **Rounding (R2):** normalize with `ROUND_HALF_UP`, store 4 decimals, round only at display; never round in storage.
- **Two-process DB (Constraint 1):** all consumers read `ExchangeRate` from the shared DB; the 5-min cache is acceptable; invalidate cache when admin updates a rate.
