# Specification: Price Enforcement & Filter-Reset Architecture

**Status:** Final — incorporating PO decisions (Q1–Q6) and technical research findings  
**Version:** 1.0  
**Date:** 2026-09-01  
**Source Problem:** `.ai/problems/Problem_01.md` (RU)  
**Target Files:** `apps/ads/models`, `apps/ads/views/listings.py`, `apps/search/views/search.py`, `ads/templatetags/price_tags.py`, `templates/ads/partials/ad_list.html`, `templates/ads/partials/filter_form.html`, `telegram_bot/handlers/ad_create.py`, `apps/moderation/services/auto_moderation.py`

---

## 1. Problem Summary

Two related concerns:

1. **Price enforcement:** Ads must have a price set by the seller (via the bot) and published with one of three valid price states per currency model. Currently the flow allows the seller to skip price (producing `price_amount = None`) and the moderation system has a `price_required` flag that is inconsistently applied against a nullable model field.

2. **Filter-reset UX:** Search and filter state in the catalog needs a unified mechanism for clearing all active filters, plus a compact inline price-range summary displayed when price filters are active.

---

## 2. Facts (Verified)

### 2.1 Data Model — Price Fields

From `apps/ads/models.py` (lines 65–72, 284–286):

```
price_amount      DECIMAL(10,2)  null=True, blank=True
price_currency    VARCHAR(3)     null=True, default='EUR'
price_normalized_eur  DECIMAL(12,4)  null=True
```

DB schema (`docs/02-database/db-schema.md`, lines 134–136):
- `price_normalized_eur` has a partial index on non-null values.
- `CHECK (price_normalized_eur >= 0)` constraint at DB level (line 370).

### 2.2 Moderation Criteria

- `ModerationCriteria.price_required` is a BOOL field, default `True` (`apps/moderation/models.py` line 35).
- `auto_moderation.py` (lines 119, 138, 315): checks `price_amount is None` when `price_required` is `True`.
- **Mismatch:** The `Ad.price_amount` field is still nullable in the model, creating inconsistency with moderation enforcement.

### 2.3 Seed Data

- `seed/generators/ads.py` `_generate_price()`: returns `None` for ~20% of non-special-category ads.
- Charity / give-away ads already get `0` (zero amount, valid state).

### 2.4 Bot Flow

- `telegram_bot/handlers/ad_create.py` lines 540, 560, 613: "Skip price" button sets `price_amount = None`.
- `telegram_bot/schemas/message_payloads.py` `PricePayload` (lines 39–51): `price_amount` field is `Decimal | None` with `ge=0` constraint. The `ge=0` validator is silently skipped for `None` values (Pydantic behavior).

### 2.5 Template Display

- `ads/templatetags/price_tags.py` `format_price_value()`: returns `""` (empty string) when `price_amount` is `None`.
- `templates/ads/partials/ad_list.html` line 33: uses `{% if ad.price_amount %}` to conditionally display the price chip. **Latent bug:** price=0 evaluates as falsy and would be invisible.
- `templates/ads/partials/filter_form.html` lines 49–65: min/max price inputs exist as plain number fields.
- No price-range summary currently exists in the UI.

### 2.6 Filter Architecture

- Both `apps/ads/views/listings.py` (lines 322–387) and `apps/search/views/search.py` (lines 89–146) implement filter logic inline — `django-filter` is declared in `pyproject.toml` and installed (v26.1) but **completely unused**.
- `TestPriceNullSort` and `test_clear_all_filters_has_push_url` exist in `apps/ads/tests/` — price-null sort and "Clear all filters" push-state tested.
- URL state duplication: `ad_list.html` contains 18 inline URL constructions for filter links.

### 2.7 Development Environment

- Current DB is in dev mode — **no production data to migrate**.
- Migrations: `apps/ads/migrations/` currently has only `0001_initial.py` (single file).
- Dev-mode workflow per `docs/99-agent/architecture.md`: max 8 files/app → reset to one `0001_initial.py`.

### 2.8 PO Decisions (Reference)

| Q | Answer | Implication |
|---|--------|-------------|
| Q1 | **B** | Bot: price is mandatory, but zero must be explicitly entered (no skip) |
| Q2 | **B** | Free ads (price=0) display "Free" instead of "0 €" |
| Q3 | **A** | Charity/give-away ads use price=0 like free ads |
| Q4 | **A** | Dev only; recreate DB from zero; avoid migrations if possible |
| Q5 | **B** | Show price range summary "Price: 100–500" in filters for price/purpose/condition/features; category/city excluded |
| Q6 | **A** | Filter-reset button (clear all) placed on catalog page, not individual filter form |

---

## 3. Assumptions

1. **Bot flow change is in-scope:** Removing the "Skip price" button and requiring explicit entry (including `0` for free/charity) is the desired behavior per Q1 + Q2 + Q3.
2. **Zero is a valid price:** `price_amount = 0` is stored as a real value, not `None`. This resolves the falsy-check bug.
3. **Currency handling:** All price=0 and charity ads are in the ad's declared currency (EUR by default). The `price_normalized_eur` for a 0-amount ad is `0.0000`.
4. **Filter-reset scope (Q5):** "Show for price + purpose + condition + features only" means the inline range summary applies to the price min/max filter pair only. The broader "Clear all filters" button resets all catalog filters including search query.
5. **No DB migration needed for price fields:** Since the field already exists and is nullable, making it non-nullable in code (Django model layer) without a DB-level migration is acceptable for dev. The partial index and CHECK constraint remain valid.
6. **i18n:** All new/modified user-visible strings must be wrapped in `gettext`/`{% trans %}`. Target languages: `ru` (primary), `en`, `bs`.

---

## 4. Open Questions

1. **Non-dev deployment:** This spec assumes dev-only. For any staging/production environment, a proper migration to alter `price_amount` from nullable to non-nullable is required. This is explicitly **out of scope** per Q4.
2. **Charity category auto-detection:** When a seller selects a "Charity" sub-category during ad creation, should the bot auto-fill price=0 and skip the price input step? (Currently no auto-fill exists.) **Deferred to PO** — current spec treats all ads uniformly.

---

## 5. Business Rules

### 5.1 Price Mandatory (Bot Flow)

| Rule ID | Rule |
|---------|------|
| R-PM-01 | The Telegram bot ad-creation FSM **must not** offer a "Skip price" / "Without price" option. |
| R-PM-02 | The seller **must** explicitly enter a numeric price amount (≥ 0) or confirm "Free" (which sets `0`). |
| R-PM-03 | `PricePayload.price_amount` schema must reject `None` — the field becomes `Decimal` (non-optional) with `ge=0`. |
| R-PM-04 | Charity/give-away ads (Q3) use `price_amount = 0`, same as free ads. No special "charity" price label is introduced. |

### 5.2 Moderation Enforcement

| Rule ID | Rule |
|---------|------|
| R-MM-01 | `auto_moderation.py` checks `price_amount is None` only if `ModerationCriteria.price_required == True`. With price now always set by the bot, `None` should only occur from legacy seed data or direct DB manipulation. |
| R-MM-02 | `Ad.price_amount` model field: **in code**, change `null=True, blank=True` → `blank=False` (i.e., `null=False, default=0`). A DB migration is **not** required in dev per Q4. |

### 5.3 Display Rules

| Rule ID | Rule |
|---------|------|
| R-DISP-01 | If `price_amount == 0`: display **"Free"** (localized) — not "0 €". |
| R-DISP-02 | If `price_amount is None` (legacy/seed data only): omit the price chip entirely (preserve existing behavior via `format_price_value` returning ""). |
| R-DISP-03 | If `price_amount > 0`: display formatted amount + currency (e.g., "1 500 ₽"). |
| R-DISP-04 | Fix the `{% if ad.price_amount %}` falsy-check bug in `ad_list.html` — replace with explicit `None` check or use the `format_price_value` template tag which already handles null/zero correctly. |

### 5.4 Filter-Reset & Summary UI

| Rule ID | Rule |
|---------|------|
| R-FR-01 | A unified **"Clear all filters"** button exists on the catalog listing page (`ads/list.html`), outside the individual `filter_form.html` partial. It resets all query parameters (search `q`, price min/max, purpose, condition, features, sort, pagination). |
| R-FR-02 | When price min/max filters are active, an inline summary line **"Price: {min}–{max}"** is displayed (localized) within the active-filters area. |
| R-FR-03 | Category and city filters are **excluded** from the inline summary and from the "Clear all filters" scope (Q5). They have their own reset mechanism elsewhere. |
| R-FR-04 | The filter-reset button uses HTMX `hx-get` with `hx-push-url="true"` to update URL state without full page reload. |

---

## 6. Technical Requirements

### 6.1 Model Changes

**File:** `apps/ads/models.py`

| Field | Current | Target |
|-------|---------|--------|
| `price_amount` | `DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)` | `DecimalField(max_digits=10, decimal_places=2, null=False, default=0)` |
| `price_currency` | `CharField(max_length=3, null=True, default='EUR')` | No change |
| `price_normalized_eur` | `DecimalField(max_digits=12, decimal_places=4, null=True)` | No change (null for legacy data) |

> **Note:** Since this is dev-only and the migration is a single `0001_initial.py`, the field definition can be updated directly and the migration file regenerated or edited in place. No multi-file migration conflict resolution is needed (per dev workflow in `architecture.md`).

### 6.2 Schema (Pydantic) Changes

**File:** `telegram_bot/schemas/message_payloads.py`

- `PricePayload.price_amount`: change from `Optional[Decimal] = Field(ge=0)` → `Decimal = Field(ge=0)`.
- Remove any "skip" or "without price" button payloads from the bot keyboard schema.

### 6.3 Bot Handler Changes

**File:** `telegram_bot/handlers/ad_create.py`

- Remove inline keyboard buttons or code paths at lines 540, 560, 613 that allow skipping price entry.
- Ensure the "Free" option sets `price_amount = Decimal("0.00")` explicitly and proceeds to the next FSM step.
- Charity category handling: if a "Charity" category is selected, auto-navigate to a confirmation step that sets price=0 (Q3). **If auto-fill is not desired, this is deferred to PO.**

### 6.4 Moderation Service Changes

**File:** `apps/moderation/services/auto_moderation.py`

- Line 119, 138, 315: the `price_required` check (`if price_amount is None`) remains functionally correct — with the bot no longer allowing `None`, this becomes a defensive check for edge cases (seed data, manual DB edits).
- No behavioral change needed, but add a comment noting the bot-enforcement guarantee.

### 6.5 Template Tag Changes

**File:** `ads/templatetags/price_tags.py`

- `format_price_value()`: add explicit handling for `price_amount == 0` → return localized "Free" string.
- Preserve `None` handling (returns "").

```python
@register.filter
def format_price_value(ad):
    if ad.price_amount is None:
        return ""
    if ad.price_amount == 0:
        return gettext("Free")
    # ... existing formatting logic
```

### 6.6 Template Changes

**File:** `templates/ads/partials/ad_list.html`

- Replace `{% if ad.price_amount %}` (line 33) with `{% if ad.price_amount is not None %}` or delegate to `{% if ad|format_price_value %}`.
- Use the updated `format_price_value` filter for the price chip content: `{% if ad.price_amount is not None %}<span class="price-chip">{{ ad|format_price_value }}</span>{% endif %}`.

**File:** `templates/ads/partials/filter_form.html`

- Keep existing min/max price inputs (lines 49–65). No structural change.

**File:** `templates/ads/list.html`

- Add a **"Clear all filters"** button (Q6) outside `filter_form.html`, using HTMX:
```html
<div class="catalog-filters-reset" hx-target="#catalog-results" hx-push-url="true">
    <button type="button" hx-get="{% url 'ads:catalog' %}" class="btn btn-outline">
        {% trans "Clear all filters" %}
    </button>
</div>
```
- Add an inline **active-filters summary** showing price range when applicable:
```html
{% if active_price_min or active_price_max %}
    <div class="filter-summary">
        {% blocktrans with min=active_price_min|max=active_price_max %}Price: {{ min }}–{{ max }}{% endblocktrans %}
    </div>
{% endif %}
```

### 6.7 View Changes

**File:** `apps/ads/views/listings.py`

- Lines 322–387: after parsing filters, expose `active_price_min`, `active_price_max` to template context for the summary display.
- Line 397–400: ensure price-null sort (`order_by("price_amount")` or `-price_amount`) still works with the new non-null field — it degrades gracefully.

**File:** `apps/search/views/search.py`

- Lines 89–146: mirror the same context additions for consistency if the search results page also shows catalog filters.

### 6.8 Seed Generator Changes

**File:** `seed/generators/ads.py`

- `_generate_price()` (currently returns `None` for ~20% of non-special ads): update to return `Decimal("0")` instead of `None` for consistency with the new non-null field.
- Charity/give-away ads already return `0` — no change needed there.
- This ensures seed data complies with the new model constraint.

### 6.9 Migration Strategy (Dev)

Since this is a **dev-only** environment (Q4):

1. **No migration file will be created.** The `price_amount` field change from nullable to non-nullable with default `0` is handled by regenerating the existing `0001_initial.py` migration.
2. The test DB container is destroyed and recreated from zero — no data to migrate.
3. If any existing test or code path depends on `price_amount` being `None`, update those tests (rule: "Production code is king" — tests adapt to production behavior).

---

## 7. Acceptance Criteria

### 7.1 Price Mandatory (Bot)

- [ ] "Skip price" / "Without price" button is absent from the bot keyboard during ad creation.
- [ ] Entering `0` is explicitly possible and required for free/charity ads.
- [ ] `PricePayload.price_amount` rejects `None` at schema validation time.
- [ ] Existing bot tests that simulate skipping price are updated or removed.

### 7.2 Moderation

- [ ] `auto_moderation.py` correctly identifies ads with `price_amount is None` as failing moderation when `price_required == True` (defensive check preserved).
- [ ] No existing moderation tests break; new test: ad created via bot always has non-null price.

### 7.3 Display

- [ ] Ad with `price_amount == 0` displays "Free" (localized) in the ad list card and detail page.
- [ ] Ad with `price_amount == None` (legacy/seed) displays no price chip.
- [ ] Ad with `price_amount > 0` displays formatted price + currency.
- [ ] The `{% if ad.price_amount %}` falsy bug is resolved — price=0 is no longer invisible.

### 7.4 Filter Reset & Summary

- [ ] "Clear all filters" button appears on the catalog listing page (`ads:list` route).
- [ ] Clicking "Clear all filters" resets all URL query parameters and reloads results via HTMX push-state.
- [ ] When price min/max are set, an inline summary "Price: {min}–{max}" appears in the active-filters area.
- [ ] Category and city are excluded from the summary and from the clear-all scope.
- [ ] `django-filter` remains unused — filters are still hand-rolled inline in views.

### 7.5 Seed Data

- [ ] `_generate_price()` no longer returns `None` — all non-special-category ads get a numeric amount (including `0` if free).

### 7.6 Dev Environment

- [ ] No new migration file created beyond `0001_initial.py` (edited in place).
- [ ] Test DB recreated from zero with updated schema.
- [ ] All existing tests pass (adjusted for new behavior where needed).

---

## 8. Internationalization (DoD)

All new/modified strings must pass `test_i18n_completeness.py`:

| String | Context |
|--------|---------|
| "Free" | `format_price_value` template tag, Python `gettext("Free")` |
| "Clear all filters" | `ads/list.html` template, `{% trans %}` |
| "Price: {min}–{max}" | `ads/list.html` template, `{% blocktrans %}` with `min`/`max` variables |

Run `make makemessages` then `make compilemessages` after implementation.

---

## 9. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Price-null sort breaks | Low | Medium | Field has default=0; `None` only from legacy data |
| Template falsy-check regression | High | Low | Replace with explicit `is not None` check |
| Bot keyboard layout shifts | Medium | Low | Update all bot keyboard tests |
| Seed data inconsistency | Low | Medium | Update `_generate_price()` in same PR |
| Missing migration in non-dev env | Low | Critical | This spec is dev-only; document constraint |

---

## 10. Out of Scope

- `django-filter` adoption — explicitly excluded (per codebase pattern).
- Category/city filter reset — handled by separate search-reset line (Q5).
- Production data migration — dev-only (Q4).
- Charity auto-fill in bot FSM (deferred to PO).
- Currency conversion UI changes.

---

## 11. Implementation Priority

1. **Model + schema + bot changes** (price enforcement core)
2. **Template tag + display fixes** (zero handling, falsy-check bug)
3. **Seed data update** (no more `None` prices)
4. **Filter-reset UI + price-range summary** (template + view + context)
5. **Tests** (update bot, moderation, display, filter-reset, seed tests)
6. **i18n** (makemessages + compilemessages + completeness test)
7. **Migration regen** (edit `0001_initial.py` in place for dev)

---

*End of specification — ready for implementation planning.*