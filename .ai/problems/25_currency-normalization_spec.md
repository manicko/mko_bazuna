---
id: currency-normalization-spec
problem: Problem_04
domain: product
tags:
  - currency
  - price
  - multi-currency
  - exchange-rate
  - normalization
related:
  - technical-specification
  - db-schema
  - db-enums
  - db-indexes
  - architecture-structure
  - packages-list
  - user-stories-index
  - search-patterns
  - filter-ui
  - design-system
  - archive-sweep-pattern
  - auto-moderation-service
  - bot-ad-create-handler
  - alert-query-service
  - saved-search-model
---

# Spec 25 — Multi-Currency Price Normalization

**Decision source:** `.ai/problems/Problem_04.md`
**Spec state:** CONFIRMED — PO decisions locked (Q1–Q5), 2026-08-21. Ready for implementation planning.
**Date:** 2026-08-21
**Stack:** Python 3.14 · Django 5.2 LTS · PostgreSQL 18 · HTMX 1.9.12 MPA · aiogram 3.x · Pydantic v2

---

## 1. Problem Statement

The Mko Bazuna classifieds board currently displays all prices in **BAM** (Bosnia and
Herzegovina Convertible Mark) as a hardcoded unit. The project launches in
**Montenegro**, where **EUR** is the expected display currency. The price field
(`Ad.price`) is a `PositiveIntegerField` storing whole BAM units with no currency
metadata; the currency suffix "BAM" is hardcoded in every template, the bot dialog,
Telegram alert messages, and seed-data templates.

The requirement is to introduce **multi-currency support** with EUR as the default
display currency, supporting **EUR, RSD, and BAM** now (with user-switchable display
currency deferred to a future phase). The source of truth for each ad's price is the
seller's original amount and currency. A derived `price_normalized_eur` field enables
cross-currency price filtering, sorting, and saved-search alerts without per-query
conversion.

### Current State Summary

| Layer | Current Implementation | File |
|-------|------|------|
| **Model** | `Ad.price = PositiveIntegerField` (whole BAM units) | `ads/models.py:81-85` |
| **Bot dialog** | "Enter price in BAM (whole numbers)" | `ad_create.py:326,331-356` |
| **Bot schema** | `PricePayload.price: int \| None, ge=0` | `schemas/message_payloads.py:32-38` |
| **Bot confirmation** | `ad.price = data.get("price")` → `Ad.update_ad_and_moderate` | `ad_create.py:686` |
| **Web listing filter** | `ads.filter(price__gte=int(min_price))` | `ads/views/listings.py:347,359` |
| **Search filter** | `ads.filter(price__gte=int(min_price))` | `search/views/search.py:85,90` |
| **Web sort** | `ads.order_by("price")` / `order_by("-price")` | `listings.py:377,381` |
| **Detail page** | `{{ ad.price }} BAM` | `detail.html:53` |
| **List card** | `{{ ad.price }} BAM` | `ad_list.html:52` |
| **Dashboard** | `{{ ad.price }} BAM` | `dashboard.html:97` |
| **Moderation review** | `{{ ad.price }} BAM` | `review.html:42` |
| **Edit form** | `<label>Price (BAM)</label>` + `ad.price = price_value` | `edit.html:55`; `edit.py:102-151` |
| **SavedSearch** | `min_price`/`max_price` = `PositiveIntegerField` "in BAM" | `search/models.py:79-88` |
| **Alert query** | `price__gte=saved_search.min_price` / `ad.price < min_price` | `alert_query.py:85,87,172,175` |
| **Telegram alerts** | `f"{ad.price} BAM"` | `immediate_alerts.py:104`; `send_alerts.py:189` |
| **Moderation** | `if price_required and ad.price is None` | `auto_moderation.py:137,306` |
| **Seed** | `_generate_price() -> int`, templates say `{price} BAM` | seed `AdGenerator`, `ads_templates.json` |
| **Design docs** | All price examples use "BAM" | `ui-patterns.md:99`, `filter-ui.md:249`, `design-system.md:206,349-367` |
| **DB docs** | `price (INT, nullable) # whole BAM units; multi-currency deferred (currency column removed — YAGNI)`; `Zone D11: currency column removed` | `db-schema.md:129,245` |
| **Spec index** | "multi-currency" listed under Deferred to post-MVP | `spec-index.md:154` |

### Proposed Model (from Problem_04.md)

```text
Ad
├── price_amount          Decimal       # исходная цена продавца (source of truth)
├── price_currency        EUR/RSD/BAM   # валюта исходной цены (StrEnum)
└── price_normalized_eur  Decimal       # нормализованная цена для поиска/сортировки (derived)
```

`price_normalized_eur` — производное поле, не редактируется пользователем.

---

## 2. Confirmed Requirements

### 2.1 Currency Support (from Problem_04.md)

| ID | Requirement | Source |
|----|-------------|--------|
| CR-01 | Project launches in Montenegro; **EUR is the default display currency** | Problem_04.md line 3 |
| CR-02 | Support **EUR, RSD, and BAM** as ad listing currencies | Problem_04.md line 3 |
| CR-03 | User currency switching is **future scope** (not implemented in this phase) | Problem_04.md line 3 |
| CR-04 | Store original seller price + currency as **source of truth**: `price_amount` + `price_currency` | Problem_04.md lines 9-14 |
| CR-05 | `price_normalized_eur` is a **derived** field, not editable by users | Problem_04.md line 18 |
| CR-06 | Exchange rates stored in system; auto-update from official sources is **not implemented now** but architecture must support it | Problem_04.md lines 22-24 |
| CR-07 | `price_normalized_eur` calculated at ad creation based on the **currently stored** rate | Problem_04.md line 28 |
| CR-08 | Backfill `price_normalized_eur` for existing ads | Problem_04.md line 34 |
| CR-09 | Mass recomputation command after rate changes (management command / scheduled job) | Problem_04.md lines 36-38 |
| CR-10 | Price filtering and sorting use `price_normalized_eur` for cross-currency comparison | Problem_04.md line 42 |

### 2.2 Model-Level Requirements

| ID | Requirement | Source |
|----|-------------|--------|
| MR-01 | New `CurrencyCode` StrEnum: `EUR`, `RSD`, `BAM` (never plain strings) | Project rule 10 (StrEnum) |
| MR-02 | New `ExchangeRate` model: currency, rate_to_eur, effective_date, source, is_current | Problem_04.md CR-06 |
| MR-03 | `price_amount` replaces the current `price` column; type Decimal with fixed precision | Problem_04.md line 13 |
| MR-04 | `price_currency` StrEnum column on `Ad`, defaulting to EUR | Problem_04.md line 14 |
| MR-05 | `price_normalized_eur` Decimal column on `Ad`, nullable (price can be skipped) | Problem_04.md line 15 |
| MR-06 | Index on `price_normalized_eur` for sort/filter performance | search-patterns.md §Search Response Performance |
| MR-07 | Migration backfills existing `price` (BAM) → `price_amount` + `price_currency=BAM` + `price_normalized_eur` | Problem_04.md CR-08 |
| MR-08 | Old `price` column may be retained during migration then dropped, or renamed | Problem_04.md (implementation discretion) |

### 2.3 Bot / Ad Creation Requirements

| ID | Requirement | Source |
|----|-------------|--------|
| BR-01 | Bot price step captures both currency and amount | Problem_04.md CR-04 |
| BR-02 | `PricePayload` Pydantic schema (bot input boundary) validates currency + amount | Project rule 11 (Pydantic) |
| BR-03 | `price_normalized_eur` computed at ad submission (`update_ad_and_moderate`) using current rate | Problem_04.md CR-07; ad_create.py:769 |
| BR-04 | Draft ads (no price yet) must not fail normalization; `price_amount` can be NULL | ad_create.py:540-515 (draft created before price step) |

### 2.4 Web / Buyer Requirements

| ID | Requirement | Source |
|----|-------------|--------|
| WR-01 | Listing and search price-range filters use `price_normalized_eur` | Problem_04.md CR-10 |
| WR-02 | Price sort (low/high) uses `price_normalized_eur` | Problem_04.md CR-10; AdSort enum |
| WR-03 | Price displayed with currency label, not hardcoded "BAM" | Problem_04.md CR-01 |
| WR-04 | Saved search price filters operate on EUR-normalized values | alert_query.py (current behavior filters on `price`) |

### 2.5 Moderation Requirements

| ID | Requirement | Source |
|----|-------------|--------|
| MOD-01 | `price_required` moderation check uses `price_amount` (not legacy `price`) | auto_moderation.py:137,306 |
| MOD-02 | No new moderation criteria for price range (per technical-specification.md line 47) | technical-specification.md line 47 |

### 2.6 Seed Data Requirements

| ID | Requirement | Source |
|----|-------------|--------|
| SD-01 | Seed ad price generation updated to new model (currency + amount + normalized_eur) | `04_category-lookup-architecture_spec.md:648` ("single BAM currency only") |
| SD-02 | Seed assertions (`ad.price` is int) updated to new fields | `test_seed.py:1066-1068` |

### 2.7 Telegram Alert Requirements

| ID | Requirement | Source |
|----|-------------|--------|
| AL-01 | Alert messages format price with currency label (not hardcoded "BAM") | `immediate_alerts.py:104`; `send_alerts.py:189` |

---

## 3. Conceptual Development Tasks

### Task 1: Create Currency StrEnum + ExchangeRate Model + Migration
- **Purpose:** Establish the currency vocabulary and rate storage as the foundation. The `CurrencyCode` StrEnum replaces all hardcoded "BAM" string literals. The `ExchangeRate` model stores rates relative to EUR with effective dates and source tracking, designed to support future auto-update from official sources (e.g., ECB API).
- **Expected outcome:** `CurrencyCode` StrEnum in `apps/currencies/enums.py`; `ExchangeRate` model in `apps/currencies/models.py`; DB migration with seeded initial rates for EUR (1.0), BAM (~0.51), RSD (~0.0105); `ExchangeRate.is_current=True` for all seeded rows. (Per PO Q5: new `apps/currencies` app with its own models, migrations, enums.)
- **Dependencies:** None. Blocks Tasks 2, 3, 4, 8, 11.
- **Files touched:** `apps/currencies/enums.py`, `apps/currencies/models.py`, `apps/currencies/apps.py`, new migration `currencies/0001_initial.py`, `db-enums.md`, `db-schema.md`.

### Task 2: Ad Model Migration — Add price_amount, price_currency, price_normalized_eur; Backfill
- **Purpose:** Replace the single `price` PositiveIntegerField with the three-field currency model from Problem_04.md. Backfill all existing ads by assuming the legacy `price` values were BAM (the old bot's hard-coded default), setting `price_currency = BAM`, `price_amount = old_price`, and computing `price_normalized_eur = old_price * rate_BAM_to_EUR`.
- **Expected outcome:** Django migration that adds the three new columns, backfills from legacy `price`, and drops the old `price` column (or keeps it deprecated if referenced by tests). Data integrity: `price_normalized_eur` = NULL when `price_amount` is NULL.
- **Dependencies:** Task 1 (exchange rate available for backfill calculation).
- **Files touched:** `apps/ads/models.py`, migration file, `db-schema.md`.

### Task 3: Price Normalization Service
- **Purpose:** Centralized service that computes `price_normalized_eur` from a given `price_amount` + `price_currency` using the current `ExchangeRate`. Follows the project pattern of small, focused service modules (e.g., `apps/ads/services/`). Must handle the case where no rate exists for a currency (raise/log custom error, do not silently fail).
- **Expected outcome:** `PriceNormalizer` class or `currency_service.py` module with a method like `normalize_to_eur(amount, currency) -> Decimal`. Cached rate lookup (5-minute TTL, consistent with `ModerationCriteria` cache pattern in `apps/core/utils/cache.py`).
- **Dependencies:** Task 1 (ExchangeRate model + cache pattern). Blocks Tasks 4, 5.

### Task 4: Bot Price Step + Schema Update
- **Purpose:** Update the Telegram bot dialog to capture currency selection alongside the price amount (PO-01 confirmed: inline keyboard with EUR, RSD, BAM; EUR preselected as first option). The bot presents a currency inline keyboard first, then asks for the numeric amount. Validate via updated `PricePayload` Pydantic schema, and pass both to `update_ad_and_moderate` which then computes `price_normalized_eur`. "Skip" skips both currency and amount.
- **Expected outcome:** Updated `PricePayload` with `price: Decimal | None` and `currency: CurrencyCode`; updated bot price-step message; updated `AdCreateForm` and `show_preview` to display currency; `update_ad_and_moderate` signature extended to accept `price_amount` and `price_currency` and compute `price_normalized_eur` before saving.
- **Dependencies:** Tasks 1, 2, 3. Blocks nothing else directly, but must be consistent with Task 5.
- **Files touched:** `telegram_bot/schemas/message_payloads.py`, `telegram_bot/handlers/ad_create.py`.

### Task 5: Web Search/Listings Views + Sort + Filter
- **Purpose:** Update the listing and search views to filter and sort on `price_normalized_eur` instead of the legacy `price` column. Price range filter inputs (min_price/max_price) should operate in EUR-equivalent values.
- **Expected outcome:** `listings.py` and `search.py` filter on `price_normalized_eur__gte` / `price_normalized_eur__lte`; sort by `price_normalized_eur` / `-price_normalized_eur` for `PRICE_LOW`/`PRICE_HIGH`. `AdSort` enum values unchanged but behavior remapped to normalized column.
- **Dependencies:** Task 2 (model fields exist). Blocks Task 8 (templates).
- **Files touched:** `apps/ads/views/listings.py`, `apps/search/views/search.py`, `apps/core/enums.py` (if sorting field mapping changes), `search-patterns.md`, `filter-ui.md`.

### Task 6: Web Edit View + Model
- **Purpose:** Update the seller ad edit form to support currency selection alongside price. Price/photo edits stay published; text edits trigger re-moderation (existing C2 behavior). The normalized price must be recomputed if the currency or amount changes.
- **Expected outcome:** `edit.py` accepts `price_amount` and `price_currency` from POST; computes `price_normalized_eur` via the normalization service; `edit.html` shows currency selector pre-populated with current ad currency.
- **Dependencies:** Tasks 2, 3, 4. Blocks Task 8.
- **Files touched:** `apps/ads/views/edit.py`, `templates/ads/edit.html`.

### Task 7: Templates — Price Display + Currency Formatting
- **Purpose:** Replace all hardcoded `{{ ad.price }} BAM` with a currency-aware display. Create a `format_price` template filter (or model method) that renders `price_amount` with the `price_currency` label. This touches every template that displays price.
- **Expected outcome:** New template tag/filter `format_price`; updated `detail.html`, `ad_list.html`, `dashboard.html`, `review.html` to use the new filter; design-system docs updated to show EUR instead of BAM.
- **Dependencies:** Tasks 2, 5, 6.
- **Files touched:** New template tags file, 4 HTML templates, `docs/01-spec/design-system.md`, `docs/06-design-system/components.md`, `docs/06-design-system/tokens.md`, `docs/01-spec/ui-patterns.md`.

### Task 8: SavedSearch Model + Filters + Templates
- **Purpose:** Update `SavedSearch` to store price filters in EUR-normalized terms. Update the alert query service to filter on `price_normalized_eur`. Update the saved-search modal and edit templates to label prices as EUR.
- **Expected outcome:** `SavedSearch` keeps `min_price`/`max_price` fields (now interpreted as EUR equivalents); `alert_query.py` filters on `price_normalized_eur__gte`/`lte`; `cabinet/saved_search_edit.html` and `search/partials/save_search_modal.html` labels changed from "BAM" to "EUR".
- **Dependencies:** Task 2 (model fields). Blocks Task 9 (tests).
- **Files touched:** `search/models.py`, `search/services/alert_query.py`, 2 HTML templates, `db-schema.md`.

### Task 9: Moderation Service Update
- **Purpose:** Update `auto_moderate` and `check` functions to reference `price_amount` instead of the legacy `price` column for the `price_required` check.
- **Expected outcome:** Both functions check `ad.price_amount is None` (or `ad.price is None` if legacy column retained). No new moderation criteria for price range.
- **Dependencies:** Task 2.
- **Files touched:** `apps/moderation/services/auto_moderation.py`, moderation tests.

### Task 10: Telegram Alert Message Update
- **Purpose:** Update `immediate_alerts.py` and `send_alerts.py` to display prices with the correct currency label using `price_amount` + `price_currency` (or EUR-normalized) instead of hardcoded "BAM".
- **Expected outcome:** Alert messages use a shared `format_price` helper (same filter used in templates, per §6 assumption 9). Format: `"{amount} {currency}"` from the ad's original `price_amount` + `price_currency` (e.g., "500 BAM"). Reuses the `format_price` template tag via a Python-callable wrapper to avoid duplicating formatting logic between templates and bot messages. (Per PO Q4 confirmed: original currency, consistent with detail page.)
- **Dependencies:** Tasks 2, 3.
- **Files touched:** `search/services/immediate_alerts.py`, `search/management/commands/send_alerts.py`.

### Task 11: Management Command — Recompute Normalized Prices
- **Purpose:** Mass-recompute `price_normalized_eur` for all ads after exchange rates change. Follows the established `archive_sweep.py` advisory-lock + `transaction.atomic()` pattern (AdvisoryLockId lock ID).
- **Expected outcome:** New `recompute_normalized_prices` management command; new `AdvisoryLockId` entry; `--dry-run` flag consistent with other sweep commands.
- **Dependencies:** Tasks 1, 2, 3.
- **Files touched:** New command file, `apps/core/enums.py` (AdvisoryLockId), `AdvisoryLockId` lock allocation doc.

### Task 12: Seed Data Update
- **Purpose:** Update `AdGenerator` and seed templates to use the new price model. Seed ads should set `price_currency`, `price_amount`, and `price_normalized_eur`. Seed description templates that hardcode "BAM" must be updated to use the seed ad's currency.
- **Expected outcome:** `AdGenerator._generate_price()` returns both amount and currency; seed templates use `{price}` variable without hardcoded currency suffix in descriptions.
- **Dependencies:** Task 2.
- **Files touched:** `apps/seed/services/seed_service.py`, `apps/seed/generators/ads.py`, seed fixtures (`ads_templates.json`).

### Task 13: Test Updates
- **Purpose:** Update all tests that reference the old `price` field or hardcode BAM expectations.
- **Expected outcome:** `test_seed.py` assertions on `ad.price` → `ad.price_amount`; `test_alert_query.py` price filter tests use `price_normalized_eur`; `test_listings_context.py` updated for new filter field names; moderation tests check `price_amount`.
- **Dependencies:** Tasks 2, 5, 8, 9, 10, 12.
- **Files touched:** Multiple test files across `ads/tests/`, `search/tests/`, `seed/tests/`, `moderation/tests/`.

---

## 4. Product Owner Decisions

All decisions below are **CONFIRMED** by the Product Owner (2026-08-21). Recommended approaches were based on best practices and existing architecture patterns; all were accepted unmodified.

| Decision ID | Question | PO Decision | Rationale |
|-------------|----------|-------------|-----------|
| PO-01 | Should the bot ask the seller to select a currency (EUR/RSD/BAM) before entering the price, or default all new ads to EUR? | **CONFIRMED: Ask the seller to select currency** via an inline keyboard (EUR, RSD, BAM), with EUR as the first/default button. "Skip" skips both currency and amount. | The problem statement stores `price_currency` as source-of-truth — the seller must provide it. RSD is relevant for cross-border sellers. A 3-button inline keyboard adds one step but ensures correct multi-currency capture. EUR preselected minimizes friction. |
| PO-02 | How should the ad detail page display the price? Show the seller's original price + currency (e.g., "500 BAM"), or show only the EUR-normalized price? | **CONFIRMED: Show the seller's original price + currency** (e.g., "500 BAM" or "250 EUR"). | Buyers see what the seller actually asks — critical for inquiry/contact. Matches Avito/Olx patterns. The EUR-normalized value is used internally for sorting/filtering only. |
| PO-03 | Should all existing `price` values be assumed to be BAM for the backfill? | **CONFIRMED: Yes.** | The bot dialog has always asked for "price in BAM." All existing ads were created through this flow. |
| PO-04 | Should saved search price filters (min_price/max_price) operate in EUR (normalized)? | **CONFIRMED: Yes.** Problem_04.md CR-10 states "filtering and sorting by price uses `price_normalized_eur`." Existing saved searches are converted during migration (BAM values multiplied by the seed rate). |
| PO-05 | What initial exchange rates to seed for backfill? | **CONFIRMED: Fixed rates** (EUR base = 1.0): BAM ≈ 0.512, RSD ≈ 0.0105. Source label `"manual_seed"`, `is_current=True`. Will be replaced when auto-update is implemented. |

---

## 5. Research Summary

### Research Conducted
A researcher agent investigated modern multi-currency practices in Django/PostgreSQL
web applications and mapped the full impact surface across the Mko Bazuna codebase.

### Research Findings

**1. Price Storage: Decimal vs. Minor Units (Integer Cents)**

| Approach | Description | Pros | Cons |
|----------|-------------|------|------|
| **A. Decimal(precision, scale)** | Store as `DecimalField(max_digits=10, decimal_places=2)` for `price_amount`; `price_normalized_eur` as `DecimalField(max_digits=12, decimal_places=4)` for intermediate precision | Matches Problem_04.md spec exactly (`Decimal` type); supports fractional prices; exact arithmetic, no floating-point drift | Requires careful precision specification to avoid rounding issues in normalization |
| **B. Minor units (integer)** | Store as integer cents/eurocents (`BigIntegerField`); divide by 100 for display | Avoids rounding drift entirely; keeps PostgreSQL bigint sort/filter semantics the existing code expects; no floating-point at any layer | Diverges from Problem_04.md's `Decimal` specification; requires divide-by-100 at every display point; more invasive change to existing integer-based code |

**Recommended: Approach A (Decimal)** — The Problem_04.md specification explicitly defines
`Decimal` types for `price_amount` and `price_normalized_eur`. `price_amount` uses
`DecimalField(max_digits=10, decimal_places=2)` (supports up to 99,999,999.99 in any currency).
`price_normalized_eur` uses `DecimalField(max_digits=12, decimal_places=4)` to retain
intermediate precision during cross-currency division without rounding drift in the
normalized column. PostgreSQL `NUMERIC` maps directly to these field types.

**2. Exchange Rate Storage**

| Approach | Description | Pros | Cons |
|----------|-------------|------|------|
| **A. Simple current rate table** | `ExchangeRate` model with `currency` (StrEnum FK), `rate_to_eur` (Decimal), `effective_date`, `is_current` boolean, `source` text | Simple to implement; clear single source of truth for "current" rate; supports date-keyed historical lookups; `is_current` flag enables efficient lookups | Does not store full historical rate history per se, but `effective_date` + `is_current` allows tracking changes |
| **B. Date-versioned rate history** | Separate `ExchangeRateHistory` table with `valid_from`/`valid_to` date range, supporting point-in-time lookups | Full auditability of rate changes; correct historical normalization | Overengineering for phase 1; the problem says auto-update is not implemented now |

**Recommended: Approach A** — A single `ExchangeRate` model per currency with
`is_current=True` for the active rate, plus `effective_date` for audit trail. This
matches the project pattern of singleton/runtime-editable config (cf. `ModerationCriteria`).
The architecture supports future replacement from official sources (ECB API returns
rates relative to EUR) without schema changes.

**3. Normalization Trigger: DB Trigger vs. App-Level vs. Scheduled Job**

| Approach | Description | Pros | Cons |
|----------|-------------|------|------|
| **A. PostgreSQL trigger** | `AFTER INSERT OR UPDATE OF price_amount, price_currency` trigger recomputes `price_normalized_eur` | Consistent with existing `ads_search_vector_fn` trigger pattern (trigger-maintained FTS vectors in `core/migrations`); ensures normalization never goes stale | Trigger SQL must be in a data migration; harder to test; couples rate lookup to DB layer |
| **B. App-level on save** | Override `Ad.save()` or use `pre_save` signal to compute `price_normalized_eur` | All normalization logic in Python/Django, consistent with existing trigger pattern's app-layer companion services; easier to test | Must be called everywhere `price_amount`/`price_currency` is set (bot create, web edit, management command) |
| **C. Computed column** | PostgreSQL `GENERATED ALWAYS AS` column | Zero application logic; always consistent | Cannot reference a separate table (ExchangeRate) in a generated column expression in PostgreSQL; not feasible |

**Recommended: Approach B (App-level service)** — A `PriceNormalizer` service called
from `update_ad_and_moderate()` (bot) and `ad_edit()` (web), plus the management command.
This keeps the normalization logic in Python/Django where it can access the `ExchangeRate`
model and cache (consistent with `ModerationCriteria` 5-minute cache). A PostgreSQL
trigger is not feasible because the rate lookup requires reading from the `ExchangeRate`
table (PostgreSQL generated columns cannot reference other tables). The existing
search-vector triggers are pure-field (no table lookups) which is why they can be triggers.

**4. Management Command Pattern**

The existing `archive_sweep.py` (`apps/core/management/commands/`) establishes the
canonical pattern for periodic sweep commands:
- `AdvisoryLockId` IntEnum (transaction-scoped advisory lock via `pg_advisory_xact_lock`)
- `transaction.atomic()` wrapping the entire count-to-mutate sequence
- `--dry-run` flag for safe preview
- `bulk_update()` or queryset `.update()` for efficiency
- Logging via `logging.getLogger(__name__)`

A new `AdvisoryLockId.RECOMPUTE_NORMALIZED_PRICES` (value 12) follows this established
pattern. The recompute command iterates in batches, fetches the current rate per currency,
and bulk-updates `price_normalized_eur` where the normalized value differs from the
computed value.

**5. Bot Price Step — Currency Capture**

Current bot dialog (ad_create.py:331-356) asks for "price in BAM (whole numbers)."
With currency selection, the dialog flow becomes:
1. Present inline keyboard with 3 currency options (EUR, RSD, BAM) — preselect EUR
2. On selection, ask for the numeric amount
3. Validate via `PricePayload` (Pydantic)
4. Store in FSM state, display in preview, pass to `update_ad_and_moderate`

The `PricePayload` schema must change from `price: int | None` to `price_amount: Decimal | None`
and add `price_currency: CurrencyCode`.

**6. Impact Surface Inventory**

Complete list of code paths that reference `ad.price` or hardcode "BAM":

| Component | File | Lines | Action |
|-----------|------|-------|--------|
| Model | `ads/models.py` | 81-85 | Replace `price` with `price_amount` + `price_currency` + `price_normalized_eur` |
| Bot handler | `ad_create.py` | 326, 343-347, 433, 484, 686 | Currency selection + payload update |
| Bot schema | `message_payloads.py` | 32-38 | `PricePayload` update |
| Listings view | `listings.py` | 347, 359, 377, 381 | Filter/sort on `price_normalized_eur` |
| Search view | `search.py` | 85, 90 | Filter on `price_normalized_eur` |
| SavedSearch model | `search/models.py` | 79-88 | Interpret as EUR; no field change needed |
| Alert query | `alert_query.py` | 85, 87, 172, 175 | Filter on `price_normalized_eur` |
| Immediate alerts | `immediate_alerts.py` | 104 | Use `price_amount` + `price_currency` |
| Send alerts | `send_alerts.py` | 189 | Use `price_amount` + `price_currency` |
| Auto moderation | `auto_moderation.py` | 137, 306 | Check `price_amount` |
| Edit view | `edit.py` | 84-92, 102-103, 131-133, 140-141, 150-152 | Currency + amount + normalization |
| Detail template | `detail.html` | 53 | `{{ ad.price }} BAM` → format filter |
| List template | `ad_list.html` | 52 | `{{ ad.price }} BAM` → format filter |
| Dashboard template | `dashboard.html` | 97 | `{{ ad.price }} BAM` → format filter |
| Review template | `review.html` | 42 | `{{ ad.price }} BAM` → format filter |
| Edit template | `edit.html` | 55-60 | Currency selector + amount |
| Saved search modal | `save_search_modal.html` | 56, 61 | "BAM" → "EUR" labels |
| Saved search edit | `saved_search_edit.html` | 56, 61 | "BAM" → "EUR" labels |
| AdSort enum | `enums.py` | 11-18 | Sort field remapping to `price_normalized_eur` |
| Seed generator | seed `ads.py` | `_generate_price()` | Return currency + amount |
| Seed templates | `ads_templates.json` | {price} BAM | Remove hardcoded "BAM" |
| Seed tests | `test_seed.py` | 1066-1068 | Assert on `price_amount` |
| Alert query tests | `test_alert_query.py` | 229, 239, 253, 510-518 | Use `price_normalized_eur` |
| Listings context tests | `test_listings_context.py` | 32, 155-156, 184-185 | Filter field names |
| Moderation tests | `test_auto_moderation.py` | 168 | `price_required` + `price_amount` |

---

## 6. Assumptions

1. **All existing ad prices are in BAM.** The bot dialog has always asked for "price in BAM" — no other currency was selectable. The backfill migration assumes `price_currency = "BAM"` for all existing rows. (PO-03 confirmed.)

2. **EUR exchange rate = 1.0 (base).** The `ExchangeRate` model uses EUR as the base currency; `rate_to_eur = 1.0` for EUR entries. Other currencies store their rate relative to EUR (e.g., BAM: rate_to_eur ≈ 0.512 means 1 BAM = 0.512 EUR). (PO-05 confirmed.)

3. **Prices can be fractional.** The new `price_amount` Decimal(10,2) supports fractional values (e.g., 99.99). This is a change from the current integer-only model. The bot must be updated to accept decimal input (Task 4).

4. **The `price` column will be replaced, not retained.** The migration drops the legacy `price` column after backfill. All code references update to `price_amount` + `price_currency` + `price_normalized_eur`. (If tests are too tightly coupled to the column name, the project's "production code is king" rule takes priority — fix tests, not production code.)

5. **Currency switching UI is out of scope for this phase.** The problem says "user switching" is future. This phase implements the data model and EUR-default display only. A currency switcher dropdown in the header is deferred. (PO-01 confirms: seller-side currency selection at ad creation, not buyer-side display switching.)

6. **Saved search price filters are EUR-only.** Saved searches store min/max as EUR-normalized values. No per-search currency preference is stored. Existing saved searches are converted during migration. (PO-04 confirmed.)

7. **No historical exchange rates needed for this phase.** The `ExchangeRate` model stores only the current rate (`is_current=True`). Date-versioned historical rates are deferred to when the auto-update mechanism is implemented, because normalization only uses the *current* rate at creation time.

8. **Seed data uses EUR for new ads.** Seed ads (development-only) set `price_currency = EUR` (matching the launch market) with appropriate `price_amount` and `price_normalized_eur = price_amount`. Seed description templates remove the hardcoded "BAM" suffix, using the seed ad's `price_currency` variable instead.

9. **The `format_price` template filter is the preferred display approach.** Rather than calling `ad.get_price_display()` on the model, a template filter `format_price` is used, consistent with the project's separation of concerns (UI formatting in template tags, data in models). This renders `price_amount` + `price_currency` (per PO-02/Q2 confirmed).

10. **`CurrencyCode` StrEnum lives in `apps/currencies/enums.py`.** Per PO Q5, a new `apps/currencies` app is created; the enum and `ExchangeRate` model both reside there. The `AdvisoryLockId` enum remains in `apps/core/enums.py` (core infrastructure, not currency-domain).

11. **Telegram alerts show original price + currency.** Per PO Q4 confirmed: alert messages format as `"{amount} {currency}"` from the ad's original `price_amount` + `price_currency`, consistent with the detail page (PO-02). This is a shared helper used by `immediate_alerts.py` and `send_alerts.py`.

---

## 7. Constraints

1. **Two processes, one DB** — Web (gunicorn sync WSGI, HTMX MPA) + bot (aiogram, `django.setup()` + shared ORM). Both processes must see the same `ExchangeRate` rows immediately (via DB, not cache or in-memory). Cache TTL of 5 minutes is acceptable for rate lookups.

2. **No task broker** — No Celery/Redis pub-sub beyond cache. The mass-recompute command is a cron-invoked management command (like `archive_sweep.py`), not a background worker.

3. **PostgreSQL 18 only** — `NUMERIC`/`Decimal` fields, advisory locks, triggers all use PostgreSQL features. No SQLite fallback (already the project constraint).

4. **StrEnum for all currency values** — `CurrencyCode` must be a `StrEnum` (EUR, RSD, BAM), never plain strings. Per project rule 10.

5. **Pydantic at bot input boundary** — `PricePayload` must validate currency + amount via Pydantic v2. Per project rule 11.

6. **Production code is king** — Tests that assert on `ad.price` must be updated; production code must not be distorted for tests. Per AGENTS.md rule 2.

7. **English only in code** — Comments, logs, error messages must be in English. Per AGENTS.md rule 1. No `print()` — use `logging.getLogger(__name__)`. Per AGENTS.md rule 12.

8. **Migration dev-mode workflow** — Migrations follow the threshold-based consolidation (max 8 files/app → reset to one `0001_initial.py`) and the advisory-lock `migrate` service. Per architecture.md §Commands and docs/ops/migration-workflow.md.

9. **Bot FSM persists as Ad row (DRAFT)** — The price step state is NOT stored in bot FSM storage; it's held in the `Ad` row or the aiogram FSM `state.update_data()`. The `update_ad_and_moderate()` function writes to the DB at confirmation. Consistency with existing pattern.

10. **Decimal precision** — `price_amount`: `DecimalField(max_digits=10, decimal_places=2)`. `price_normalized_eur`: `DecimalField(max_digits=12, decimal_places=4)` for intermediate precision. Rationale: 10 digits, 2 decimal places supports up to 99,999,999.99 in any currency; 4 decimal places for normalized EUR avoids rounding drift when dividing BAM/RSD amounts (e.g., 1 RSD = ~0.0105 EUR, so 1000 RSD = 10.5 EUR exactly; but 333 RSD = 3.4965 EUR needed the 4th decimal place).

---

## 8. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **R1: Backfill rate assumption wrong** — Some existing prices might not be BAM | Low | High | The bot has *only ever* accepted BAM prices (hardcoded in dialog). Verify via code audit: `ad_create.py:326` and all templates. Risk is theoretical, not real. |
| **R2: Decimal rounding drift in normalization** | Medium | Medium | Use `decimal.Decimal` with `ROUND_HALF_UP`; store `price_normalized_eur` with 4 decimal places; round only at display time, never in storage. |
| **R3: Bot price step complexity** — Adding currency selection adds a step | Medium | Low | Preselect EUR as the first button; allow "skip" to work with currency=None (price not required per ModerationCriteria). |
| **R4: Cross-currency sort inconsistency** — New ads use current rate, old ads used backfill rate | Medium | Medium | The mass-recompute command (Task 11) handles rate changes. Document that rates are snapshotted at creation; recompute only runs on explicit admin/cron invocation. |
| **R5: Template filter proliferation** — `format_price` needs to cover detail, list, dashboard, review templates | Low | Low | Single `format_price` filter handles all cases; templates just call `{{ ad|format_price }}`. |
| **R6: Seed templates hardcoded "BAM" in descriptions** — Text content, not just UI | Medium | Medium | Seed templates use `{price}` variable; the "BAM" suffix in template strings must be parameterized or removed. Seed is dev-only so impact is limited. |
| **R7: Saved search filter migration** — Existing saved searches with BAM min/max need EUR conversion | Medium | Medium | Migration converts existing `min_price`/`max_price` values: multiply by seed BAM→EUR rate. Saved search filters are re-interpreted as EUR values. |
| **R8: New `apps/currencies` app** — App-loading order, migration dependencies | Low | Low | Create `apps/currencies` with `__init__.py` + `apps.py`; `apps/ads` migration depends on `currencies.0001_initial`. No circular import — currencies has no FK to ads. |
| **R9: Test coverage gap** — Many tests assert on `ad.price` directly | High | Medium | Comprehensive test update task (Task 13) with explicit acceptance: all existing price tests updated and passing. |

---

## 9. Open Questions

All five open questions are **CONFIRMED** by the Product Owner (2026-08-21):

| Q# | Question | PO Decision |
|----|----------|-------------|
| Q1 | Bot: ask seller for currency (inline keyboard) vs. auto-default EUR? | **CONFIRMED: Inline keyboard** (EUR, RSD, BAM; EUR first). "Skip" skips both currency + amount. |
| Q2 | Detail page: original currency vs. EUR-normalized vs. both? | **CONFIRMED: Original price + currency** (e.g., "500 BAM"). |
| Q3 | Saved search filters: keep `price_asc`/`price_desc` enum values vs. rename? | **CONFIRMED: Keep enum values.** Only the `.order_by()` target changes from `"price"` to `"price_normalized_eur"`. |
| Q4 | Telegram alerts: original currency vs. EUR-normalized? | **CONFIRMED: Original currency** (e.g., "500 BAM"), consistent with detail page (Q2). |
| Q5 | `ExchangeRate` model: `apps/core` vs. new `apps/currencies` app? | **CONFIRMED: New `apps/currencies` app** with its own models, migrations, and enum. |

---

## 10. Out of Scope

1. **User-facing currency switcher UI** — No buyer-side currency dropdown/radio in the header. EUR-normalized values are used internally for filtering, sorting, and saved-search alerts (no per-user currency preference). The detail page and alert messages display the seller's original `price_amount` + `price_currency` per PO-02/Q2 and PO Q4. (Seller-side currency selection at ad creation is in-scope per PO-01.)
2. **Exchange rate auto-update mechanism** — The problem explicitly says "Mechanism for obtaining and updating rates is not implemented yet, but the architecture must support it." The `ExchangeRate` model supports this; the actual fetcher/cron job is a separate future task.
3. **Historical exchange rates** — Only the current rate (`is_current=True`) is stored. Date-versioned rate history (for re-normalizing old ads at their original-rate) is deferred.
4. **Price range validation** — No min/max price bounds beyond `price_required` (existing moderation check). No currency-specific price caps.
5. **Currency-specific formatting** (thousands separators, decimal places per locale) — Use Django's `intcomma` / `floatformat` existing patterns. Full i18n number formatting is a future enhancement.
6. **Per-ad price history** — No audit trail of price changes on an individual ad. The `AdHistory` / changelog for price is out of scope.
7. **Multi-currency in the bot's "Contact seller" flow** — Contact is currency-agnostic (just relays to Telegram).
8. **Currency for "free" / charity ads** — `price_amount = 0` or `NULL` continues to trigger the "Благотворительность" auto-category path (decision S, zone C12). This behavior is unchanged.

---

## 11. Definition of Ready

This specification is ready for implementation planning. All PO decisions (§4) and open questions (§9) are **CONFIRMED** as of 2026-08-21. The following checklist confirms readiness:

1. **PO-01 through PO-05 (Q1–Q5) are CONFIRMED** by the Product Owner (2026-08-21). Decisions: bot currency inline keyboard with EUR default; detail page shows original price+currency; saved search filters are EUR-normalized; Telegram alerts show original currency; new `apps/currencies` app created. Decisions and rationale documented in §4.
2. **Research findings validated** — The researcher's investigation of multi-currency patterns is complete and the recommended approaches (Decimal storage, app-level normalization, advisory-lock command pattern) are accepted.
3. **Impact surface mapped** — All 20+ code paths referencing `ad.price` or "BAM" are identified (§5 Research Summary, Table "Impact Surface Inventory").
4. **Migration strategy agreed** — Backfill assumes BAM for existing prices; legacy `price` column replaced by `price_amount` + `price_currency` + `price_normalized_eur`. Tests updated, not production code distorted.
5. **Conceptual tasks sequenced** — 13 tasks with clear dependencies (§3) form the implementation plan. Tasks 1-3 are independent; Tasks 4-6 build on the model; Tasks 7-13 are follow-ups requiring DB fields.
6. **Architectural constraints documented** — Two-process shared DB, PostgreSQL-only, StrEnum, Pydantic-at-boundary, advisory-lock pattern (§7).
7. **Test strategy defined** — Task 13 explicitly lists all affected test files with their required assertion changes.

The 13 conceptual tasks (§3) can be decomposed into implementation stories by the
planning/technical-lead agent. Tasks 1-3 are independent and parallelizable.
Tasks 7-10 depend on Task 2 (model fields). Tasks 8-10, 12 depend on the new
display/format behavior from Tasks 5-7.
