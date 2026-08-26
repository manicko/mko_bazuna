# Research Report: New/Used Condition Modeling in Major Classifieds

**Date:** 2026-08-25  
**Scope:** How major classifieds (Avito, OLX) model the "new/used" item condition dimension — data model, filter UI, and seller-side enforcement.  
**Goal:** Resolve whether `new`/`used` should remain as `listing_feature` M2M entries or be extracted into a dedicated condition field.

---

## 1. The Core Problem

In Mko Bazuna, `new` (slug `new`) and `used` (slug `used`) are regular entries in the `listing_feature` LookupGroup (`categories.yaml:38-44`). They are stored as M2M features via the `ad_features` through table (`AdFeature` model). Nothing in the data model prevents an ad from having **both** `new` and `used` simultaneously — which is logically invalid (an item cannot be both new and used).

The seed service (`seed_service.py:126-134`) randomly samples 1–3 features from the category-resolved feature set, and since both `new` and `used` appear in that set, **the random sample can include both** — creating advertisements with contradictory condition states.

Similarly, the bot's feature-selection flow (`ad_create.py:218-249`) uses a multi-select checkbox keyboard (`build_feature_keyboard`) that allows toggling both `new` and `used`.

## 2. How Competitors Handle It

### 2.1 Avito (Russia's largest classifieds)

**Source:** Live article "Фильтры на Авито" (vc.ru, 2026-04-21) — [vc.ru/marketing/2878720](https://vc.ru/marketing/2878720-filtry-na-avito-vazhnost-dlya-prodavtsov-i-sovety-po-ispolzovaniyu)

| Aspect | Avito Implementation |
|---|---|
| **Filter name** | "Состояние товара" (product condition) |
| **Filter type** | Dedicated dropdown/radio, **NOT** part of general feature checkboxes |
| **Values** | "новый" (new), "б/у" (used), and in some categories "как новый" (like new) |
| **Semantics** | Single-select: selecting "новый" excludes all "б/у" ads from results |
| **Algorithmic behavior** | Exact match (точное соответствие): if the condition field is not filled in the ad, it does NOT appear in any condition-filtered result set |
| **Category-dependent?** | Yes — condition filter appears only for categories where it makes sense (electronics, clothing, furniture, etc.); absent for services/real-estate |

Key insight from the Avito article: "Алгоритм Авито работает жёстко: если поле не заполнено, объявление не показывается по этому фильтру" — if the condition is not specified, the ad doesn't show up when filtering by condition.

### 2.2 OLX (Global, localized per market)

**Source:** Live OLX page fetch (olx.ua/transport, August 25, 2026) + URL parameter analysis (olx.com.pk)

| Aspect | OLX Implementation |
|---|---|
| **Filter group name (UI)** | "Умови продажу" (sale conditions) / "Stan" (condition) |
| **URL parameter** | `new_used_eq_used` (from olx.com.pk URL structure) — a **dedicated parameter**, not `features` |
| **Filter type** | Button dropdown with radio-style single selection |
| **Values** | "Все" (All), "Нове" (New), "Б/У" (Used) |
| **Semantics** | Single-select: choosing "новое" shows only new ads; "б/у" shows only used ads |
| **Category-dependent?** | Yes — condition filter is not shown for all categories; appears contextually |

Key finding: OLX's URL parameter `new_used_eq_used` proves condition is a **separate query parameter** from the multi-select features parameter — it is architecturally distinct.

### 2.3 Industry consensus

Both major platforms model "new/used" as a **dedicated condition dimension** with single-select (mutually exclusive) semantics, NOT as part of a multi-select feature checkbox list. The condition filter is:
- A separate filter group in the UI
- A separate URL parameter
- Category-dependent (only shown where applicable)
- Single-select (radio/dropdown), not multi-select checkboxes

## 3. Data Model Analysis

### 3.1 Current Mko Bazuna model

```
ads.listing_purpose → FK → lookup_items (group=listing_purpose)  # single-select
ads.features → M2M → lookup_items (group=listing_feature)       # multi-select
    through: ad_features (ad_id, feature_id, sort_order)
```

`new` and `used` are `listing_feature` LookupItems. The `ad_features` table has:
- `Unique: (ad, feature)` — prevents the SAME feature from being added twice
- **No constraint** preventing both `new` AND `used` simultaneously (they're different rows)

### 3.2 Root cause of the bug

The seed service (`seed_service.py:130-134`) does:
```python
sample = feature_rng.sample(resolved_features, k=feature_rng.randint(1, min(3, len(resolved_features))))
ad.features.set(sample)
```

When `resolved_features` contains both `new` (id=X) and `used` (id=Y), the random sample can include both X and Y. There is no application-level or database-level validation that catches this.

### 3.3 Categories affected

From `categories.yaml`, the following top-level categories (and their descendants) have `new` and `used` in their `listing_feature_override`:

1. **transport** (line 150): `[new, used, delivery, pickup, negotiable, credit, exchange, urgent, warranty]`
2. **goods** (line 247): `[new, used, delivery, pickup, negotiable, exchange, urgent, handmade, branded, custom, warranty, packaging, import, local, eco]`
3. **auto-parts** (line 207): `[new, used, delivery, pickup, negotiable, exchange, urgent, warranty, packaging, branded, import, local]`
4. **business** (line 701): `[new, used, delivery, pickup, negotiable, credit, installment, urgent, warranty, luxury]`
5. **business-equipment → auto-business-equipment** (line 711): `[new, used, delivery, pickup, negotiable, exchange, urgent, warranty]`
6. **pet-supplies** (line 452): `[new, used, delivery, pickup, negotiable, exchange, urgent, warranty, branded, import, local]`

Categories WITHOUT `new`/`used`: `real-estate`, `services-jobs`, `animals`, `charity`.

## 4. Feasible Approaches

### Approach A: Dedicated `condition` field on `Ad` (Recommended)

Add a `condition` field to the `ads` table — a single-select FK to a `Condition` enum or LookupItem (group=listing_condition or similar).

**Pros:**
- Matches Avito/OLX data model exactly (condition as separate dimension)
- Enforced at DB level — can never have both new AND used
- Clean separation: condition ≠ feature (they're different concepts)
- Filter UI can use a dedicated single-select dropdown/radio
- Seed service picks condition independently from other features

**Cons:**
- Schema migration required (new column)
- Backward compatibility: existing ads with `new`/`used` features need migration
- Categories without condition: `condition` must be nullable
- Filter UI needs a new parameter (`?condition=new` instead of `?features=new`)
- The `categories.yaml` catalog structure changes (new group for conditions)

### Approach B: Mutual-exclusivity validation on the `listing_feature` M2M

Keep `new`/`used` as features, but add validation that prevents both from being set simultaneously.

**Pros:**
- No schema change (no new column/table)
- Minimal migration
- Filter UI unchanged (still in features checkboxes, but with JS mutual exclusion)

**Cons:**
- **Still the wrong conceptual model** — condition is not a "feature" like delivery/negotiable/urgent
- No DB-level guarantee (Django validation only, not DB constraint)
- Seed service still needs fixing to not pick both
- Filter UI UX is awkward (checkboxes that can't both be checked)
- Doesn't match competitor pattern

### Approach C: Seed + bot fix only (Minimal)

Just fix the seed and bot to never select both `new` and `used`. No data model or validation change.

**Pros:**
- Minimum change
- No migrations, no test breakage

**Cons:**
- **Does not fix the root cause** — nothing prevents a future code path or admin from creating an ad with both
- No DB-level protection
- Conceptually wrong — condition should be a first-class dimension
- Future feature additions (e.g., condition filter UI redesign) will hit the same wall

## 5. Recommendation

**Approach A** is recommended (dedicated `condition` field), based on:
1. **Competitor validation:** Both Avito and OLX model new/used as a dedicated condition dimension
2. **Correctness:** DB-level guarantee that an ad can never be both new and used
3. **Concept separation:** Condition ≠ feature — mixing them was the original design error
4. **Filter UI alignment:** A dedicated condition filter can be a clean single-select (radio/dropdown), matching OLX's "Stan" filter

---

## 6. Open Technical Questions (for implementation research)

1. Should `condition` be a new `LookupGroup` (e.g. `listing_condition`) with its own LookupItems, or a simple `StrEnum` on the `Ad` model?
2. What migration strategy for existing ads that have both `new` and `used` features?
3. How does this interact with the already-implemented dropdown-with-checkboxes filter UI (Problem_05)?
