# Problem Spec 12: New/Used Condition Mutual Exclusivity

**Spec ID:** 12  
**Created:** 2026-08-25  
**Status:** Complete — PO decisions collected (A, B, no-data-preservation, select dropdown, separate `?condition=` param, separate chip); implementation verified.
**Source:** `.ai/problems/Problem_01.md` (Russian) — `new` and `used` are mutually exclusive states currently modeled as generic `LookupItem` M2M features (`listing_feature` group) via `AdFeature` through model; seed/service assigns both simultaneously, creating invalid ads.  
**Spec index:** [docs/01-spec/spec-index.md](docs/01-spec/spec-index.md) · [db-schema.md](docs/02-database/db-schema.md) · [filter-ui.md](docs/01-spec/filter-ui.md)  
**Research:** [.ai/reports/02_new-used-condition-research.md](.ai/reports/02_new-used-condition-research.md)

---

## 1. Problem Statement

`new` (slug `new`) and `used` (slug `used`) are mutually exclusive item conditions, but they are currently implemented as generic multi-select features in the `listing_feature` LookupGroup. An ad can have **both** `new` and `used` features simultaneously — a logically invalid state. Three code paths can create such invalid ads:

1. **Seed service** (`seed_service.py:130-134`): randomly samples 1–3 features from the category-resolved feature set; when both `new` and `used` are in the resolved set, the sample can include both.
2. **Telegram bot feature selection** (`ad_create.py:172-249`): uses a multi-select checkbox keyboard (`build_feature_keyboard`) that allows toggling both `new` and `used`.
3. **Admin moderation UI**: no constraint prevents manual assignment of both via Django admin.

**User-visible symptom:** On the catalog/search page, an ad can display both "Новый" and "Б/У" tags simultaneously, which is contradictory. The existing OR-semantics feature filter (`?features=new&features=used`) would return such ads when filtering by either condition, degrading search quality and confusing buyers.

---

## 2. Confirmed Facts

| # | Fact | Evidence (file:line) |
|---|------|---------------------|
| F1 | `new` and `used` are `listing_feature` LookupItems (group=`listing_feature`). | `categories/catalog/categories.yaml:38-44` (definition); `apps/lookups/models.py:43-96` (LookupItem model) |
| F2 | An ad's features are stored in the `ad_features` through table via `AdFeature` model, with `Unique(ad, feature)` but no constraint preventing both `new` and `used`. | `apps/ads/models.py:133-139` (M2M def), `apps/ads/models.py:602-635` (AdFeature through model), `db-schema.md:317-326` (schema) |
| F3 | Seed service randomly samples 1–3 features from the resolved set, with no awareness that `new` and `used` are mutually exclusive. | `seed_service.py:126-134` (sample + set) |
| F4 | The bot's feature selection step (`AdCreateState.FEATURES`) uses a multi-select inline keyboard with `feature:<id>` callback_data — no mutual exclusion logic. | `ad_create.py:172-249` (proceed_to_features_or_city, process_features, build_feature_keyboard) |
| F5 | The catalog filter UI (`filter_form.html`) already implements a collapsible checkbox dropdown for `features` (per Problem_05), with OR semantics. `new`/`used` appear as regular checkboxes within this panel. | `filter_form.html:45-77` |
| F6 | The search/listings view applies `features` as OR semantics: an ad matches if it has at least one selected feature. | `ads/views/listings.py:320-361`, `search/views/search.py` (features filter) |
| F7 | Avito models "new/used" as "Состояние товара" — a **dedicated** condition filter (dropdown/radio), NOT a general feature checkbox. | `.ai/reports/02_new-used-condition-research.md` §2.1 |
| F8 | OLX models "new/used" as a **separate** filter group ("Stan"/"Умови продажу") with URL parameter `new_used_eq_used` — NOT under the general `features` parameter. | `.ai/reports/02_new-used-condition-research.md` §2.2 |
| F9 | Six top-level categories (and their descendants) define `new` and `used` in their `listing_feature_override`: transport, goods, auto-parts, business, auto-business-equipment, pet-supplies. | `categories.yaml` lines 150, 247, 207, 701, 711, 452 |
| F10 | Categories WITHOUT `new`/`used` features: real-estate, services-jobs, animals, charity. | `categories.yaml` lines 102, 474, 432, 780 |
| F11 | `ListingPurpose` is already a dedicated FK on `Ad` (single-select), demonstrating the established pattern for single-select lookup dimensions. | `ads/models.py:124-132`, `db-schema.md:134` |
| F12 | `listing_purpose` filter in `filter_form.html` is still a `<select>` (single-select), while `features` is a checkbox multi-select dropdown. | `filter_form.html:16-30` (purpose), `filter_form.html:45-77` (features) |
| F13 | There are no existing DB check constraints or ORM-level clean methods that validate feature combinations on `Ad`. | Grep for validation in `ads/models.py`, `ads/forms.py` returns no mutual-exclusivity checks |
| F14 | Seed tests (`test_seed.py`) verify seed ads carry features (`test_seed_populates_features`) and filter by feature returns results (`test_seed_filter_by_feature_returns_results`). | `apps/seed/tests/test_seed.py:1316-1391` |

---

## 3. Root Cause

**Root cause:** `new` and `used` are modeled as generic multi-select features in the `listing_feature` LookupGroup, but they are logically a **single-select condition dimension**. The M2M `ad_features` table has no mutual-exclusivity constraint between the two feature slugs. The seed service and bot feature-selection UI treat all features uniformly (multi-select), so both can be selected simultaneously. This is a **conceptual modeling error** — condition is not a "feature" like delivery/negotiable/urgent; it is a single-select attribute like `listing_purpose`.

Both Avito and OLX avoid this problem entirely by modeling condition as a **separate, dedicated dimension** outside the feature multi-select.

---

## 4. Confirmed Requirements

| Req ID | Requirement | Source |
|--------|-------------|--------|
| REQ-12.1 | An ad must never have both `new` and `used` condition simultaneously. | Implied by problem statement; Avito/OLX single-select condition (F7/F8) |
| REQ-12.2 | The seed service must never generate an ad with both `new` and `used`. | F3 — seed correctness |
| REQ-12.3 | The bot ad-creation flow must enforce mutual exclusivity when seller selects condition. | F4 — bot correctness |
| REQ-12.4 | Existing ads that already have both `new` and `used` features must be reconciled (data fix). | Backward compatibility |
| REQ-12.5 | The buyer-facing filter must allow filtering by condition (new/used) as a single-select, matching Avito/OLX UX. | F7/F8 — competitor pattern |
| REQ-12.6 | Condition filter must be category-dependent — only shown for categories where `new`/`used` apply (F9); absent for real-estate/services/animals/charity (F10). | F9/F10 |
| REQ-12.7 | No regression in existing filter semantics for genuine multi-select features (delivery, negotiable, etc.). | F14 — seed tests; filter-ui.md |
| REQ-12.8 | Migration must not break the existing `IX_ad_features_feature_id` index or the `features` M2M relationship for non-condition features. | `db-schema.md:317-326`, `db-indexes.md` |

---

## 5. Conceptual Tasks

### Task 1: Extract `new`/`used` from `listing_feature` into a dedicated condition dimension

**Sub-tasks:**
- 1a. Add a `ListingCondition` StrEnum (`NEW="new"`, `USED="used"`) to `apps/core/enums.py` (or a new `apps/conditions/enums.py`), following the project rule #10 (StrEnum for all constants).
- 1b. Add a `condition` FK/CharField to the `Ad` model, nullable (categories without condition have `NULL`).
- 1c. Add a new `LookupGroupCode.LISTING_CONDITION` enum value (or reuse existing pattern) so the catalog builder can define condition values per category in `categories.yaml`.
- 1d. Update `categories.yaml` to move `new`/`used` from `listing_feature` to a new `listing_condition` key, scoped to the 6 affected categories (transport, goods, auto-parts, business auto-business-equipment, pet-supplies).
- 1e. Write a DB migration: add `condition` column; backfill from existing `ad_features` rows that have `new`/`used`; remove `new`/`used` feature rows from `ad_features` for migrated ads.
- 1f. Add a DB-level check constraint preventing an `Ad` from having both `new` and `used` in `ad_features` (defence-in-depth if `new`/`used` are kept in the lookup table temporarily).

*Files:* `apps/ads/models.py`, `apps/categories/catalog/categories.yaml`, `apps/core/enums.py` (or new file), new migration file.

### Task 2: Update the catalog builder and lookup resolver

**Sub-tasks:**
- 2a. Extend `builder.py` to read the new `listing_condition` section from `categories.yaml` and create/update `CategoryListingCondition` through-table bindings (mirroring the existing `CategoryListingPurpose`/`CategoryListingFeature` pattern).
- 2b. Extend `CategoryLookupResolver` with `get_resolved_conditions(category)` method, following the same ancestor-walk-cache pattern.
- 2c. Add `resolved_conditions` / `current_condition` context variables to the listings and search views.

*Files:* `apps/categories/catalog/builder.py`, `apps/categories/services/lookup_resolution.py`, `apps/ads/views/listings.py`, `search/views/search.py`.

### Task 3: Update seed service to assign condition independently

**Sub-tasks:**
- 3a. In `seed_service.py`, extract `new`/`used` from the feature sampling logic so they are no longer randomly selected as features.
- 3b. For categories with resolved conditions, randomly assign one of `new`/`used` (50/50 weighted) to the new `condition` field on each seeded ad.
- 3c. Categories without conditions get `condition=NULL`.

*Files:* `apps/seed/services/seed_service.py`, `apps/seed/generators/ads.py`.

### Task 4: Update the Telegram bot feature selection flow

**Sub-tasks:**
- 4a. In `ad_create.py`, separate condition selection from feature selection: when the category has resolved conditions (`new`/`used`), show a **single-select** keyboard (radio-style inline buttons) before or independently from the multi-select features keyboard.
- 4b. Add `AdCreateState.CONDITION` state (or reuse `FEATURES` with conditional branching).
- 4c. Persist `condition` to the `Ad` row via `update_ad_and_moderate()`.
- 4d. In `build_feature_keyboard`, exclude `new`/`used` slugs from the feature list (they are now handled by the condition step).

*Files:* `src/telegram_bot/handlers/ad_create.py`, `src/telegram_bot/states.py`, `src/telegram_bot/schemas/message_payloads.py`.

### Task 5: Update the buyer-facing filter UI

**Sub-tasks:**
- 5a. Add a dedicated condition filter in `filter_form.html` — a single-select dropdown/radio (radio recommended for 2 options per UX research), shown only when `resolved_conditions` is non-empty for the active category.
- 5b. Add `condition` to the hidden-state preservation inputs and the filter chip display.
- 5c. Update `listings.py` and `search.py` views to parse `?condition=new` / `?condition=used` and filter via `ad.condition` (exact match).
- 5d. Update pagination URL preservation to carry `condition=<slug>`.

*Files:* `templates/ads/partials/filter_form.html`, `apps/ads/views/listings.py`, `search/views/search.py`, filter chip templates.

### Task 6: Add validation and tests

**Sub-tasks:**
- 6a. Add an ORM-level `clean()` method or model constraint on `Ad` that rejects both `new` and `used` in `features` (if the old feature rows haven't been fully removed).
- 6b. Add a regression test: seed must never produce an ad with both `new` and `used`.
- 6c. Add a regression test: bot feature keyboard must not include `new`/`used` when condition is separate.
- 6d. Add a regression test: filter `?condition=new` returns only new ads; `?condition=used` returns only used ads.
- 6e. Update existing seed tests (`test_seed_filter_by_feature_returns_results`) to account for `new`/`used` no longer being in the features filter.

*Files:* new test files in `apps/ads/tests/`, `apps/seed/tests/`, `src/telegram_bot/tests/`.

### Task 7: Data cleanup for existing ads

**Sub-tasks:**
- 7a. For existing ads that have both `new` and `used` in `ad_features`: pick one deterministically (e.g., keep `new`, drop `used` — or prefer the one with lower `sort_order`).
- 7b. For existing ads that have only `new` or only `used`: migrate to the `condition` field and remove from `ad_features`.
- 7c. This is done as part of the migration (Task 1e).

*Files:* Migration file.

---

## 6. Affected Assets

### Models
| File | Lines | Change |
|------|-------|--------|
| `apps/ads/models.py` | 123-139 | Add `condition` field; add `AdFeature` mutual-exclusivity (if keeping features as defense-in-depth) |
| `apps/lookups/enums.py` | — | Add `LISTING_CONDITION` enum value (if using LookupGroupCode pattern) |
| `apps/core/enums.py` | — | Add `ListingCondition` StrEnum |
| `apps/categories/models.py` | — | Add `CategoryListingCondition` through model (if using DB through-table pattern) |

### Catalog / Config
| File | Lines | Change |
|------|-------|--------|
| `apps/categories/catalog/categories.yaml` | 38-95, 102-150, 207-207, 247-247, 432-432, 452-452, 701-711 | Move `new`/`used` from `listing_feature` to new `listing_condition` key for affected categories |
| `apps/categories/catalog/builder.py` | — | Extend to read/process `listing_condition` section |

### Views
| File | Lines | Change |
|------|-------|--------|
| `apps/ads/views/listings.py` | 320-361 | Add `condition` filter parsing + context |
| `search/views/search.py` | — | Add `condition` filter parsing + context |

### Templates
| File | Lines | Change |
|------|-------|--------|
| `templates/ads/partials/filter_form.html` | 45-77, 79-85 | Add condition filter section; update Apply button condition |

### Seed
| File | Lines | Change |
|------|-------|--------|
| `apps/seed/services/seed_service.py` | 126-134 | Exclude `new`/`used` from feature sampling; assign `condition` separately |
| `apps/seed/generators/ads.py` | — | May need to pass condition to AdGenerator |

### Bot
| File | Lines | Change |
|------|-------|--------|
| `src/telegram_bot/handlers/ad_create.py` | 172-249, 484-559 | Add condition selection step; exclude `new`/`used` from features keyboard |
| `src/telegram_bot/states.py` | — | Add `CONDITION` state |

### Tests
| File | Change |
|------|--------|
| `apps/seed/tests/test_seed.py` | Update `test_seed_filter_by_feature_returns_results` (new/used no longer features); add "no ad has both new+used" test |
| `apps/ads/tests/test_catalog_filters.py` | Add condition filter test |
| `src/telegram_bot/tests/` | Add bot condition selection test; assert new/used not in feature keyboard |

---

## 7. PO Decisions (Confirmed)

| # | Decision | Option Chosen | Rationale |
|---|----------|---------------|-----------|
| PO-1 | **Data model for condition:** | **A: Dedicated `condition` field on `Ad`** | DB-level guarantee of mutual exclusivity; Avito/OLX-aligned; clean separation of single-select vs. multi-select |
| PO-2 | **Enum type:** | **B: LookupGroup pattern** (consistent with listing_purpose) | Unified with existing `listing_purpose` pattern; supports category-dependent condition sets via ancestor-walk resolver; i18n via existing `get_lookup_name:LANGUAGE_CODE` filter works out-of-the-box |
| PO-3 | **Backward compatibility / migration:** | **No data preservation** — dev environment only, no production data | Simplifies migration to backfill-only for future safety; re-seed is acceptable for current dev data |
| PO-4 | **Condition filter UI widget:** | **Dropdown `<select>`** (consistent with `listing_purpose`) | Matches the existing `listing_purpose` UI pattern (`filter_form.html` already uses `<select>` for purpose); features remain checkboxes with AND semantics |
| PO-5 | **Condition in URL parameter:** | **A: Separate `?condition=` parameter** | Avito/OLX do not mix condition with features; clean single-select vs. multi-select semantics; avoids OR-semantics conflict |
| PO-6 | **Filter chip for condition:** | **A: Separate chip** (same visual component as `listing_purpose` chip, distinct color from features) | Consistent with `listing_purpose` chip UX; visually distinguishes single-select condition from multi-select features |

### Resolved: Features Filter Semantics
The `features` filter will use **AND semantics** (an ad must have all selected features to match). This reverts the recent OR-semantics change, which was incorrect for feature filtering. Condition is never part of the features parameter.

---

## 8. Assumptions

| # | Assumption | Basis |
|---|------------|-------|
| A1 | Categories where `new`/`used` are not in `listing_feature_override` (real-estate, services-jobs, animals, charity) do not need a condition field. | F10, `categories.yaml` |
| A2 | The condition dimension is always single-select (exactly one of new/used, or none for categories without condition). | F7/F8 — Avito/OLX single-select |
| A3 | The existing `listing_purpose` FK pattern (single-select FK to LookupItem) is the established template for how single-select dimensions are modeled on `Ad`. | F11, `ads/models.py:124-132` |
| A4 | Seed tests currently expect `new`/`used` in the features filter (`test_seed_filter_by_feature_returns_results` picks an arbitrary feature slug from seed data). These tests must be updated if `new`/`used` are removed from features. | F14, `test_seed.py:1378-1391` |
| A5 | The bot's `build_feature_keyboard` currently includes ALL resolved features — it must be updated to exclude `new`/`used` if they become condition-specific. | F4, `ad_create.py:1014-1024` |
| A6 | The filter-form test contract (`test_all_htmx_links_have_push_url` asserting exactly 8 `hx-get=` in `ad_list.html`) is scoped to `ad_list.html`, not `filter_form.html`, so adding a condition section in `filter_form.html` does not break that count. | `test_catalog_filters.py:71-81` (all assertions on `ad_list.html` source, not `filter_form.html`) |
| A7 | The `ad_features` through table and `IX_ad_features_feature_id` index must be preserved for non-condition features (delivery, negotiable, urgent, etc.). | F2, `db-schema.md:317-326` |

---

## 9. Constraints

| # | Constraint | Source |
|---|-----------|--------|
| C1 | Use `StrEnum` for all fixed values — never plain strings/dicts. | AGENTS.md principle #10 |
| C2 | Templates must wrap user-visible strings in `{% trans %}` / `{% blocktrans %}`. DB-based i18n via `get_lookup_name` filter is exempt. | AGENTS.md principle #16 |
| C3 | All schema changes require DB migrations. | AGENTS.md principle #13 |
| C4 | Tests require Docker PostgreSQL on port 5433; never run `uv run pytest` locally. | `.kilo/rules/commands.md` |
| C5 | Fast gate: `make test` skips `seed` marker tests (~300s saved). Full suite via `make test-all`. | `.kilo/rules/commands.md` |
| C6 | English-only for all code comments, logs, docstrings, error messages. | AGENTS.md principle #1 |
| C7 | Production code is king: if tests conflict with architecture or business logic, fix the tests — never distort production code for tests. | AGENTS.md principle #2 |
| C8 | Two processes (web + bot) share one DB; migrations run exactly once before both start. Bot runs `django.setup()` and uses the shared ORM. | AGENTS.md, spec-index.md |

---

## 10. Risks

| # | Risk | Mitigation |
|---|------|-----------|
| R1 | **Data migration conflict:** Ads with both `new` AND `used` features need a deterministic reconciliation rule. Picking the wrong one degrades data quality. | PO decision (PO-3) — document the rule clearly; seed-only data is safe to re-seed. Production data (if any) is minimal at MVP scale. |
| R2 | **Filter URL change:** Adding a `condition` parameter changes the filter URL schema. Existing bookmarks/URLs with `?features=new` would need redirect handling or graceful degradation. | If PO-5 = separate param: handle legacy `?features=new` gracefully (filter by condition field too). If PO-5 = reuse features param: no URL change but OR-semantics conflict. |
| R3 | **Seed test breakage:** `test_seed_filter_by_feature_returns_results` picks an arbitrary feature slug from seed data — if `new`/`used` are removed from features, the test still works (it picks whatever feature is first), but seed ads that had `new` will now have `condition` field set, and the old `?features=new` URL would return zero results. | Update test to pick from non-condition features, or add a condition filter test. |
| R4 | **Bot state machine complexity:** Adding a `CONDITION` state to the ad-creation FSM changes the step order. If condition is selected before features, the features keyboard must exclude `new`/`used`. | Design the state transition carefully; add bot tests for the condition step. |
| R5 | **Catalog builder complexity:** Extending `builder.py` to handle a new `listing_condition` section adds coupling. If the builder fails, `load_catalog()` breaks for all deployments. | Follow the exact same pattern as `CategoryListingPurpose`/`CategoryListingFeature` (proven pattern). Add migration tests. |
| R6 | **Search relevance:** If condition is a separate field (not in FTS), ads with condition set won't be searchable by "новый"/"б/у" in the search query text. The description text still contains the word (from seed templates), so FTS still matches — but the condition field itself is invisible to FTS. | Verify seed templates include condition words in description (they do via `{condition}` placeholder). No additional FTS index needed for MVP. |
| R7 | **Cache invalidation:** `CategoryLookupResolver` caches resolved features/purposes for 300s. Adding `get_resolved_conditions()` requires cache invalidation on `CategoryListingCondition` through-table changes. | Follow the exact same signal-based invalidation pattern as features/purposes. |

---

## 11. Open Questions (Unresolved)

1. **Implementation research:** Does `update_ad_and_moderate()` (bot) or `Ad.clean()` (ORM) currently validate feature combinations? Grep found no such validation — confirm no existing constraint is missed.

## 12. Resolved Research: `conditions` word list in `word_lists.json`

The `word_lists.json` has a `"conditions"` key with quality descriptors per language: `["отличное", "хорошее", "удовлетворительное", ...]` (excellent, good, fair, etc.). These are used for the `{condition}` template placeholder in seeded ad text (`ads_templates.json`) — e.g. "Продам хорошее состояние ноутбук" (selling good-condition laptop).

This is **NOT** the structured `new`/`used` condition dimension. No conflict exists:
- `{condition}` in ad templates → free-text quality descriptor (from `word_lists.json`)
- `Ad.condition` (new field) → structured single-select enum (`ListingCondition.NEW`|`USED`)

**Seed behavior after refactor:** The seed generator will continue using `word_lists.json` conditions for `{condition}` template text interpolation, and will independently set `Ad.condition` to `NEW` or `USED` for categories that have resolved conditions. Categories without conditions will not set the `Ad.condition` field (NULL).

---

## 13. Out of Scope

- **Problem_05 (Filter UI dropdown-with-checkboxes):** Already implemented (`filter_form.html` features section is already a collapsible checkbox dropdown). This spec does NOT revisit that UI work — it only adds a new condition filter section.
- **Sort selector separation (Problem_05 Q1/Q2):** Sort is already decoupled with `onchange="this.form.requestSubmit()"` in `filter_form.html:94`. No changes needed.
- **Listing purpose as dropdown-with-checkboxes:** Problem_05 only covers Features + Listing purpose. The `listing_purpose` is still a `<select>` — this spec does NOT change that.
- **Admin moderation UI feature editing:** If Approach A (dedicated field) is chosen, the admin UI for editing an ad's condition is a separate task (not in scope of the data model fix).
- **Bot FSM refactoring beyond condition step:** The ad-creation dialog structure is not being redesigned — only the condition step is added/separated.
- **i18n of new condition labels:** If using LookupGroup pattern, condition labels are stored in `name_i18n` (same as features/purposes) — no additional i18n work needed beyond the existing `get_lookup_name` filter.
- **PostgreSQL FTS index changes:** Condition is a filter dimension (exact match on a column/field), not a full-text search term — no new FTS vectors required.

---

## 13. Cross-References

| Reference | Description |
|-----------|-------------|
| `.ai/problems/Problem_01.md` | Original problem request (Russian) |
| `.ai/reports/02_new-used-condition-research.md` | Competitor research (Avito, OLX) |
| `docs/01-spec/filter-ui.md` | Existing filter UI patterns and test contracts |
| `docs/01-spec/spec-index.md` §"Known Problems" | This spec will be linked as problem 12 |
| `docs/02-database/db-schema.md` §ad_features · §lookup_items · §categories | Schema references |
| `.ai/reports/01_olx-checkbox-dropdown-research.md` | Prior filter UI research (Problem_05, not condition-specific) |
| `categories/catalog/categories.yaml:38-95` | Current `listing_feature` definitions including `new`/`used` |
| `apps/seed/services/seed_service.py:126-134` | Seed feature assignment (root cause of seed bug) |
| `src/telegram_bot/handlers/ad_create.py:172-249` | Bot feature selection (root cause of bot bug) |
| `templates/ads/partials/filter_form.html:45-77` | Current features filter UI |

---

## 14. Definition of Ready

A task is ready to be implemented when:
1. ✅ Problem statement is confirmed (Section 1).
2. ✅ Root cause is identified (Section 3).
3. ✅ All affected files are enumerated (Section 6).
4. ✅ PO decisions PO-1 through PO-6 are collected (Section 7).
5. ✅ Research on existing `conditions` word list usage in seed templates is complete (Section 12) — no conflict; separate concerns.

## 15. Definition of Done

A task is done when:
1. ✅ `new` and `used` are no longer in the `listing_feature` group; condition is a dedicated single-select dimension (field, resolver, builder, YAML).
2. ✅ Seed service assigns condition independently and never produces an ad with both `new` and `used`.
3. ✅ Bot feature keyboard excludes `new`/`used`; a separate condition selection step enforces single-select.
4. ✅ Buyer filter UI has a dedicated condition filter (dropdown `<select>`, category-dependent) with `?condition=` URL parameter.
5. ✅ Features filter uses AND semantics (reverted from OR).
6. ✅ Data migration backfills existing ads from `ad_features` to `condition` field (dev-only; no production data to preserve).
7. ✅ DB-level check constraint or ORM validation prevents both `new` and `used` in `ad_features` (defence-in-depth).
8. ✅ Regression tests pass: no seed ad has both new+used; bot keyboard excludes them; condition filter returns correct results.
9. ✅ `make test` (fast gate) and `make test-all` (full suite) pass with no regressions.
10. ✅ `uv run ruff check` and `uv run basedpyright` pass on all changed files.
11. ✅ `make makemessages` + `make compilemessages` pass; `test_i18n_completeness.py` passes.
12. ✅ This spec is marked `Status: Complete` and linked from the spec index under "Known Problems".
