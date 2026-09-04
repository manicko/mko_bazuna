# Implementation Plan: Price Enforcement & Filter-Reset (Problem 02)

**Source spec:** `.ai/problems/02_price-enforcement_and-filter-reset_spec.md` (§11 priority order)
**Audit correction brief:** `.ai/plans/19_final-audit-plan-correction-brief.md`
**Current-state investigation:** `.ai/research/current-state-investigation-report.md`
**Divergence report:** `.ai/plans/18_divergence-report.md`
**Status:** Rewritten from scratch after audit correction (replaces the divergent `>0` plan entirely)
**Total task specs:** 17 (2 explicit NO-OPs + 15 substantive)

---

## 1. Overview

Implements Specification `02_price-enforcement_and-filter-reset` on top of the **already-spec-aligned foundation** verified by the investigation report.

**Critical finding (audit §B / §C.4):** The prior plan inverted the spec's mandated `>= 0` model (zero = Free/Charity) into a `> 0` regime — `default=Decimal("0.01")`, a `CheckConstraint(Q(price_amount__gt=0))`, bot-side `price_amount <= 0` rejection with "Price must be a positive number.", and moderation `price_amount <= 0`. **None of that was ever applied to the code.** The actual codebase is already at the spec's `>=0` target on the model, migration, moderation, and seed-value layers:

- `Ad.price_amount` is `null=False, default=Decimal("0")` with **no** price-sign `CheckConstraint` (`ads/models.py` L83–91; `constraints` L317–344).
- `0001_initial.py` migration already matches (`0001_initial.py` L94–102).
- `auto_moderation.py` already uses `is None` (`L138`, `L315`).
- Seed already returns `0` for give-away **and** the ~20% generic branch (`generators/ads.py` L559–561, L604–605).

Therefore those layers are **NO-OPs** (delete-and-skip, not rewrite) — but **only while the working-tree changes remain committed** (see §2). The remaining, concrete work is the spec's five priority groups §11: schema/bot, display/falsy, seed, filter-reset UX, and i18n.

---

## 2. Baseline & Working-Tree State (CRITICAL — read before executing)

The model/migration/seed-value changes that T1/T2/T8 call "NO-OPs" exist **only in the
uncommitted working tree**. They will be silently lost on `git checkout`. This section
pins down the committed baseline vs. working-tree state so the plan is robust either way.

| Layer | Committed baseline (HEAD `948b38f`) | Working tree (uncommitted, `M`) | Spec target |
|---|---|---|---|
| `Ad.price_amount` field | `DecimalField(blank=True, null=True)` — **nullable**, no default | `null=False, blank=False, default=Decimal("0")` + comment `# Price is mandatory and must be a non-negative value (>=0, zero means Free)` (models.py) | `null=False, default=0`; **no** `>0` constraint |
| `0001_initial.py` | `price_amount` nullable, no default, no price constraint | `null=False, default=Decimal("0")` matching the model | single dev migration, matches field |
| Seed `_generate_price` 20% branch | `amount = None` (docstring: "Returns `(None, CurrencyCode.EUR)`") | `amount = 0` (docstring **still stale**: still says `None`) | return `0`, never `None` |
| `test_catalog_filters.py` class | `TestPriceNullSort` | renamed to `TestPriceSort` (L391) + `test_fts_price_asc_free_sorts_first` (L557) added | free-sort covered (7.3) |
| `auto_moderation.py` | `if price_required and ad.price_amount is None:` (L138/L315) | unchanged | keep verbatim |

**Executor guidance (pick one — do NOT do both):**
- **(A) Recommended** — Commit the pending working-tree foundation *as Step 0* before T1/T2/T8
  execute. This makes the "already aligned" state durable; T1/T2/T8 remain true NO-OPs
  and only the stale docstrings/tests (T8 docs, seed test T14, conftest T12) still need editing.
  ```
  git add src/backend/apps/ads/models.py src/backend/apps/ads/migrations/0001_initial.py \
          src/backend/apps/seed/generators/ads.py src/backend/apps/ads/tests/test_catalog_filters.py
  git commit -m "refactor(ads): make price_amount non-null with default=0 (spec §6.1)"
  ```
- **(B) Defensive** — If the working tree is later reverted to HEAD, T1/T2/T8 **re-apply** the
  identical change (it is deterministic): model `null=False, default=Decimal("0")`; migration
  `null=False, default=Decimal("0")`; seed `amount = 0`. The plan's task text for T1/T2/T8
  already specifies the exact target, so they remain valid as "re-apply if reverted."

Either way: **never** re-introduce the divergent `>0` regime. Zero stays valid.

## 3. Architecture & Risk

### 3.1 Shared ORM (unchanged)
Web (gunicorn sync WSGI / HTMX) + bot (aiogram) share `src/backend/apps/ads/models.py`; `django.setup()` + shared ORM. Migrations run once before both. Test DB is recreated from zero (dev-only, Q4) — `MIGRATION_MODULES = DisableMigrations`, so the model field already takes effect in tests with no migration apply.

### 3.2 Spec-priority decomposition (§11)
1. Model + schema + bot changes (price enforcement core) → model/migration **already done**; only schema + bot remain.
2. Template tag + display fixes (zero handling, falsy-check bug).
3. Seed data update (already returns `0`; only stale docs/test remain).
4. Filter-reset UI + price-range summary (template + view + context).
5. Tests (bot, moderation, display, filter-reset, seed).
6. i18n (makemessages → compilemessages → completeness).
7. Migration regen — **NO-OP** (single `0001_initial.py`, already spec-aligned).

### 3.3 Risk register (corrected)
| Risk | Severity | Mitigation |
|---|---|---|
| Removing Skip leaves `None` writers on a now-`null=False` field → `IntegrityError` | High | Eliminating Skip (`ad_create.py` L559–566, L612–613, L540) **and** coercing `edit.py` empty→`0` are both required, or the non-null field will crash on save. |
| `format_price_value` signature mismatch: spec §6.5 example is `format_price_value(ad)` but the real signature is `(amount, currency)` | High | **Keep the 2-arg signature.** Do NOT adopt the §6.5 example — it would break all 3 real callers (`price_tags.py:72`, `immediate_alerts.py:118`, `alerts.py:190`). |
| Clear-all URL keeps `q`/`sort` (spec R-FR-01 requires reset) | Medium | Fix the `ad_list.html` L69–74 link to emit only `?page=1&lang=…` (reset q + sort + price + purpose + condition + features); category/city are path params, naturally preserved (R-FR-03). |
| `test_all_htmx_links_have_push_url` hard-counts 9 `hx-get=` in `ad_list.html` | Medium | The summary block (T10) uses **no** `hx-get`; clear-all (T11) is **relocated in place**, not added — so the count stays 9 and no test re-counting is needed. |
| `test_price_format.py` L48 exercises `price_amount=None` on a non-null field | Low | Keep `None` as a **legacy defensive** case per R-DISP-02 (in-memory `Ad`, no DB save), but **add** a `0`→"Free" case per R-DISP-01. |

### 3.4 Path & naming map (spec shorthand → actual)
| Spec shorthand | Actual path |
|---|---|
| `apps/ads/models` | `src/backend/apps/ads/models.py` |
| `bots/ad_create.py` | `src/telegram_bot/handlers/ad_create.py` |
| `bots/ad_copy.py` | `src/telegram_bot/handlers/ad_copy.py` |
| `bots/schemas/message_payloads.py` | `src/telegram_bot/schemas/message_payloads.py` |
| `ads/templatetags/price_tags.py` | `src/backend/apps/ads/templatetags/price_tags.py` |
| `templates/ads/list.html` | `src/backend/templates/ads/list.html` |
| price input template | `src/backend/templates/ads/partials/filter_form.html` |
| `apps/ads/views/listings.py` | `src/backend/apps/ads/views/listings.py` |
| `apps/search/views/search.py` | `src/backend/apps/search/views/search.py` |
| `seed/generators/ads.py` | `src/backend/apps/seed/generators/ads.py` |
| `apps/moderation/services/auto_moderation.py` | `src/backend/apps/moderation/services/auto_moderation.py` |

**URL name:** `ads:listings` / `ads:listings_category` / `ads:listings_city` (`ads/urls.py` L25–27) — spec's `ads:catalog` is a placeholder. **HTMX target:** `#ad-list` (`list.html` L36) — spec's `#catalog-results` is a placeholder.

---

## 4. Execution DAG

```
T1-MODEL-NOOP   T2-MIG-NOOP
   (root fact)     |
                   v
T11B-CONFTEST   T7-EDIT   T8-SEED-DOCS   T9-VIEW-CONTEXT
     |             |            |             |
     v             v            v             v
T13-FORMAT-TEST  T10-SUMMARY  T14-SEED-TEST  T4-BOT ──► T16-BOT-TESTS
     ^            ^             ^            ^            (blocked_by: T4)
     |            |             |            |
T5-FORMAT ──► T6-TEMPLATES ───► T15-CAT-TESTS
   (Free         (falsy          (count=9,
    branch)      fix)            clear-all)
     |             |             T17-I18N ◄── (string wrappers:
     |             |             blocked_by: T5, T6, T10, T11)
     └────► T12-FORMAT-TEST ─► T17-I18N
                  (blocked_by: T5, T11B-CONFTEST)
```

*Diagram note:* `T11-CLEARALL` (clear-all URL fix, see T11) is a peer of `T10-SUMMARY`; both depend on `T9-VIEW-CONTEXT` + `T6-TEMPLATES` and are **serial** (same file `ad_list.html`) — omitted from the ASCII for readability, but fully listed in the edges below and the legend table. `T11B-CONFTEST` is the conftest task (renamed from `T11-CONFTEST` to avoid the `T11-` prefix collision with `T11-CLEARALL`).

Dependency edges (compact):
- `T4-BOT` **blocked_by** `T3-SCHEMA` (schema must be non-optional first).
- `T10-SUMMARY` **blocked_by** `T9-VIEW-CONTEXT` (needs `active_price_min/max`) + `T6-TEMPLATES` file-edit concurrency.
- `T11-CLEARALL` **blocked_by** `T6-TEMPLATES` (same file `ad_list.html`; serial edits).
- `T10-SUMMARY` and `T11-CLEARALL` are **serial with each other** (both edit `ad_list.html`); run sequentially, not in parallel.
- `T12-FORMAT-TEST` **blocked_by** `T5-FORMAT` + `T11B-CONFTEST`.
- `T13-FORMAT-TEST` **blocked_by** `T5-FORMAT` + `T11B-CONFTEST`.
- `T14-SEED-TEST` **blocked_by** `T8-SEED-DOCS`.
- `T15-CAT-TESTS` **blocked_by** `T9-VIEW-CONTEXT`, `T10-SUMMARY`, `T11-CLEARALL`.
- `T16-BOT-TESTS` **blocked_by** `T4-BOT`.
- `T17-I18N` **blocked_by** `T5-FORMAT` (Free), `T10-SUMMARY` (summary), `T11-CLEARALL` (clear-all) — all string wrappers must precede extraction.

### 4.1 Dependency legend

| Task | blocked_by | Parallel-safe |
|---|---|---|
| T1-MODEL-NOOP | — | — (no-op) |
| T2-MIG-NOOP | T1 | — (no-op) |
| T3-SCHEMA | — | yes |
| T4-BOT | T3 | no |
| T5-FORMAT | — | yes |
| T6-TEMPLATES | T5 | partially (4 files; can parallelize across files, serial within) |
| T7-EDIT | T1 (model already non-null) | yes |
| T8-SEED-DOCS | — | yes |
| T9-VIEW-CONTEXT | — | yes (listings.py + search.py independent) |
| T10-SUMMARY | T9 | no (same file as T6/T11) |
| T11-CLEARALL | T6, T9 | no (serial with T10-SUMMARY; same file ad_list.html) |
| T11B-CONFTEST | T1 | yes |
| T12-FORMAT-TEST | T5, T11B-CONFTEST | no |
| T13-FORMAT-TEST | T5, T11B-CONFTEST | no |
| T14-SEED-TEST | T8 | no |
| T15-CAT-TESTS | T9, T10, T11-CLEARALL | no |
| T16-BOT-TESTS | T4 | no |
| T17-I18N | T5, T10, T11-CLEARALL | no (final gate) |

---

## 5. Task Specifications

### T1 — NO-OP: Confirm `price_amount` model field already spec-aligned
**Module:** `src/backend/apps/ads/models.py` → `class Ad` (L83–91); `class Meta.constraints` (L317–344).
**Spec:** §6.1 / R-MM-02 / R-PM-02 / R-DISP-01.

- **Do NOT change anything.** The field is already `DecimalField(max_digits=10, decimal_places=2, null=False, blank=False, default=Decimal("0"))` (L84) with inline comment L83: `# Price is mandatory and must be a non-negative value (>=0, zero means Free)`. `class Meta.constraints` holds only status/timestamp `CheckConstraint`s — **no** price-sign constraint.
- **This task is a no-op / delete** the prior plan's T1 proposal (`default=Decimal("0.01")` + `CheckConstraint(Q(price_amount__gt=0))`). That proposal was never applied and would make every Free/Charity ad a guaranteed `IntegrityError`.
- **Verification:** `uv run python -c "from apps.ads.models import Ad; import inspect; f=next(f for f in Ad._meta.get_fields() if f.name=='price_amount'); print(f.null, f.has_default(), f.default)"` → `False True 0`. No `price_positive` constraint in `Ad._meta.constraints`.

### T2 — NO-OP: Confirm migration already spec-aligned
**Module:** `src/backend/apps/ads/migrations/0001_initial.py` (L94–102; constraints L525–720).
**Spec:** §6.9 / §7.6 / Q4/A.

- **Do NOT create a new migration or `SeparateDatabaseAndState`.** `0001_initial.py` is the only migration and it already reads `null=False, default=Decimal("0")` with no price constraint (L94–102); all constraints are status/timestamp `AddIndex`/`AddConstraint`/`RunSQL` (L525–720). The dev workflow recreates the test DB from zero.
- **Verification:** `uv run python -c "import django; django.setup(); from django.core.management import call_command; call_command('makemigrations', '--check', '--dry-run', 'ads')"` → no pending changes.

### T3 — Make `PricePayload.price_amount` non-optional
**Module:** `src/telegram_bot/schemas/message_payloads.py` → `PricePayload` (L42–50).
**Spec:** §6.2 / R-PM-03.

- Change `price_amount: Annotated[Decimal | None, Field(ge=0)] = None` → `price_amount: Decimal = Field(ge=0)`.
- Rewrite the docstring (L43–45) to drop "optional / can be skipped with `Skip`".
- **Verification:** `uv run basedpyright src/telegram_bot/schemas/message_payloads.py`; unit assertion `PricePayload(price_amount=None)` raises `ValidationError`.

### T4 — Bot: remove "Skip", add "Free", accept `0`
**Module:** `src/telegram_bot/handlers/ad_create.py` → `build_currency_keyboard`/`process_price_currency` (L529–586), `process_price` (L589–628), `update_ad_and_moderate` (L1042–1243). Also `src/telegram_bot/handlers/ad_copy.py` L68.
**Spec:** §6.3 / R-PM-01 / R-PM-02 / Q1/B/Q2/B/Q3/A.

- **Delete** the "Skip" button: `ad_create.py` L540 `builder.button(text="⏭️ Skip", callback_data="price_skip")`.
- **Delete** the `price_skip` handler branch (L559–566) that sets `price_amount = None`.
- **Delete** the text-`"skip"` branch (L612–613) that sets `price_amount = None`; remove associated help text ("skip") at L524/L585/L599/L606.
- **Add** a "Free" confirmation button/reply path that sets `price_amount = Decimal("0.00")` and advances the FSM to the next step (currency/photo) — this is the explicit-zero entry mandated by Q1/B and Q2/B.
- Accept an explicitly-typed `0` from `process_price` (the schema already permits it via `ge=0`; T3 makes `None` impossible). Do **not** reject `price_amount <= 0`.
- Update `update_ad_and_moderate` signature param (L1048) from `Decimal | None` → `Decimal`.
- Coerce/remove the `ad_copy.py` L68 `price_amount = None` FSM placeholder so it cannot feed `None` into the now-`Decimal`-typed `update_ad_and_moderate` (L1048→L1099); set it to `Decimal("0")` (Free) or delete the key. Add bot-test coverage for the copy→post path with `price=0`.
- **Verification:** New/located bot test confirming (a) no Skip button is rendered, (b) "Free" sets `0`, (c) `Ad` row with `price_amount == 0` is created and moderated through, (d) `PricePayload(price_amount=None)` raises, (e) copy→post with price=0 persists `0`.

### T5 — `format_price_value`: add "Free" branch, import `gettext`
**Module:** `src/backend/apps/ads/templatetags/price_tags.py` (L19–37; imports L10–14).
**Spec:** §6.5 / 5.3 R-DISP-01 / §8.

- `import gettext` at module top (currently absent).
- Insert `if amount == 0: return gettext("Free")` between the `None` guard (L33–34) and the formatting fallback (L35–37).
- **Keep** the existing 2-arg signature `format_price_value(amount, currency)` — do NOT adopt the spec §6.5 `format_price_value(ad)` example, which would break all 3 callers (`price_tags.py:72`, `immediate_alerts.py:118`, `alerts.py:190`).
- **Verification:** `format_price_value(Decimal("0"), CurrencyCode.EUR) == "Free"`; `format_price_value(None, CurrencyCode.EUR) == ""` (legacy defensive, R-DISP-02).

### T6 — Fix 4 template falsy-checks
**Modules:** 4 templates.
**Spec:** §6.6 / 5.3 R-DISP-04.

| File | Line | Current | Target |
|---|---|---|---|
| `partials/ad_list.html` | L104 | `{% if ad.price_amount %}` | `{% if ad.price_amount is not None %}` |
| `detail.html` | L132 | `{% if ad.price_amount %}` | `{% if ad.price_amount is not None %}` |
| `dashboard.html` | L87 | `{% if ad.price_amount %}` | `{% if ad.price_amount is not None %}` |
| `admin/moderation/review.html` | L40 | `{% if ad.price_amount %}` | `{% if ad.price_amount is not None %}` |

- **Verification:** `uv run ruff check`; render each template with `price_amount = 0` and confirm the price chip now appears (delegates to the T5 "Free" branch).

### T7 — `edit.py`: coerce empty/None price to `Decimal("0")`
**Module:** `src/backend/apps/ads/views/edit.py` (`_apply_price_change` L27–59; parse L123–132; currency fallback L134–142).
**Spec:** §5.2 R-MM-01 (the non-null field is already live; empty input must not produce `None`).

- In the POST handler (L123–132), when `price_amount` is empty/invalid currently yields `price_amount_value = None`; change so an empty input resolves to `Decimal("0")` (Free), only `None` when truly unset for a legacy path. Concretely: `price_amount_value = Decimal(new_price_amount) if new_price_amount not in (None, "") else Decimal("0")`.
- Update `_apply_price_change` signature (L27–31) from `price_amount: Decimal | None` → `price_amount: Decimal`; update its docstring (L41) to drop "None clears the price."
- **Verification:** `make test-recreate PYTEST_OPTS="-k 'edit and price'"`.

### T8 — Seed: fix stale docstring + return-type hint
**Module:** `src/backend/apps/seed/generators/ads.py` (L543–609; hint L547; docstring L551–552).
**Spec:** §6.8 / 7.5 / Q5/A.

- Value is already correct (returns `0` for give-away L559–561 and the ~20% generic branch L603–607; never `None`). **No behavioral change.**
- Fix stale return-type hint (L547): `tuple[int | None, CurrencyCode]` → `tuple[int | Decimal, CurrencyCode]`.
- Fix stale docstring (L551–552): drop "Returns `(None, …)` for the ~20% …".
- Optionally return `Decimal("0")` to match spec literal (functionally equivalent; the `DecimalField` coerces int on save).
- **Verification:** `uv run ruff check`; `make test-all PYTEST_OPTS="-k 'seed and price'"` (the `>0` seed test T14 fixes the assertion, not the generator).

### T9 — Views: expose `active_price_min` / `active_price_max`
**Modules:** `src/backend/apps/ads/views/listings.py` (L436–437) + `src/backend/apps/search/views/search.py` (L260–261).
**Spec:** §6.6 / 6.7 / R-FR-02 / Q5/B.

- Add `active_price_min`/`active_price_max` to the template context (parsed `Decimal` or `None`), aliasing or alongside the existing raw `min_price`/`max_price` strings so the §6.6 summary block can render without structural filter changes (django-filter stays unused per §10).
- No `>0` validation on price range — `0` is a valid filter bound (R-DISP-01).
- **Verification:** `make test PYTEST_OPTS="-k 'price_range'"`.

### T10 — Add price-range summary block
**Module:** `src/backend/templates/ads/partials/ad_list.html` (active-filters area), included by `list.html` via `<div id="ad-list">` (L36). The summary renders in the active-filters region, **outside** the chips-only conditional, so it appears on `active_price_min`/`active_price_max` alone. T10 and T11 are **serial** (same file).
**Spec:** §6.6 / R-FR-02 / Q5/B / §8.

- Add `{% if active_price_min or active_price_max %}<div class="filter-summary">{% blocktrans with min=active_price_min|max=active_price_max %}Price: {{ min }}–{{ max }}{% endblocktrans %}</div>{% endif %}` in the active-filters area.
- Uses the context vars from T9. Uses `{% blocktrans %}` (i18n extraction at T17).
- **Verification:** Render with `min_price`/`max_price` set → "Price: {min}–{max}" appears; with neither set → absent.

### T11 — Fix clear-all URL scope (reset `q`/`sort`)
**Module:** `src/backend/templates/ads/partials/ad_list.html` (clear-all link L69–74).
**Spec:** §6.6 / R-FR-01 / R-FR-03 / R-FR-04 / Q6/A.

- The current link **keeps `q` and `sort`** (a real bug) while dropping `min_price`/`max_price`/purpose/condition/features. R-FR-01 requires resetting **all** query params (q, price min/max, purpose, condition, features, sort, pagination).
- The clear-all link (ad_list.html L69–74) is nested inside the chips-only `{% if current_listing_purpose or current_features or current_condition %}` block (L33). **Move it out of that conditional** so it renders whenever any filter is active (incl. `q`-only / price-range-only), satisfying R-FR-01's "reset ALL query parameters" intent. This is an in-file move, NOT a new link: no `hx-get=` is added (count stays 9).
- Rewrite the `hx-get` URL to `?page=1{% if LANGUAGE_CODE %}&lang={{ LANGUAGE_CODE }}{% endif %}` — reset q + sort + price + purpose + condition + features; guarded `lang` (matches the 8 sibling links, no empty `&lang=`); category/city are **path params** (`urls.py` L25–27) so they are naturally preserved (R-FR-03 ✓).
- Keep `hx-push-url="true"` (R-FR-04 ✓). Keep the link inside `ad_list.html` (the `#ad-list` catalog-results content included by `list.html` L36; it is **outside** `filter_form.html`, so R-FR-01's "on the catalog listing page, outside the individual filter form" is met). The summary block (T10) adds **no** `hx-get`, so the hard count of 9 is preserved.
- **Verification:** `make test PYTEST_OPTS="-k 'clear_all_filters or htmx_links'"` → `test_all_htmx_links_have_push_url` count stays 9; `test_clear_all_filters_has_push_url` asserts `hx-push-url="true"` + `hx-get="?page=1` (substring still present) + that `q` and `sort` are **absent** from the reset URL + that the button is visible with only `q` set.

### T11B-CONFTEST — Narrow `create_test_ad` to forbid `None`
**Module:** `src/backend/conftest.py` → `create_test_ad` (L112–151; default L120; docstring L134; `None` writes L140–142).
**Spec:** §2 premise / 7.3 / 7.5 (0 is a primary exercisable state).

- Narrow the `price` parameter type to forbid `None` (would now `IntegrityError` on the non-null column at L140–142). Keep the default `100` (do **not** use the divergent plan's `Decimal("99.99")`, which steers tests off the `0` path).
- Fix the stale docstring (L134) "Pass `price=None` for an unpriced ad" → "Pass `price=0` for a Free/Charity ad."
- **Verification:** `uv run basedpyright src/backend/conftest.py`; grep confirms no existing fast-gate call passes `price=None`.

### T12 — `test_price_format.py`: add `0`→"Free", keep legacy `None`
**Module:** `src/backend/apps/ads/tests/test_price_format.py` (L48).
**Spec:** §8 / 4.2 R-DISP-01/R-DISP-02.

- Add a case: `price_amount=Decimal("0")` → `format_price(ad) == "Free"`.
- Keep the `price_amount=None` case **only** as the legacy defensive path (R-DISP-02: legacy/seed `None` → omit price chip → `""`), because `format_price_value` preserves the `None`→`""` branch (T5). Do **not** rewrite `None`→`Decimal("0.01")` (audit Corr. #15: keeps `None` as legacy case).
- **Verification:** `make test PYTEST_OPTS="-k 'price_format'"`.

### T13-FORMAT-TEST — Update `TestPriceSort` (verify, no rename)
**Module:** `src/backend/apps/ads/tests/test_catalog_filters.py` (class L391; `test_fts_price_asc_free_sorts_first` L557; `test_all_htmx_links_have_push_url` L646; `test_clear_all_filters_has_push_url` L664).
**Spec:** §2.6 / 7.3 / 7.4.

- The class is already `TestPriceSort` (L391) — the divergent plan's "rename `TestPriceNullSort`→`TestPriceSort`" is **moot** (audit Corr. #3). Do **not** rename.
- `test_fts_price_asc_free_sorts_first` (L557) already creates `price=0` and asserts free sorts first ascending — **already spec-aligned** (R-DISP-01/7.3). Keep.
- `test_all_htmx_links_have_push_url` (L646–653) hard-counts 9 `hx-get=` + 9 `hx-push-url="true"` in `ad_list.html`. T11 adds **no** new link (relocation-in-place), so the count is unchanged. **Verify** rather than "fix".
- Optionally strengthen `test_clear_all_filters_has_push_url` (L664) to assert `q` and `sort` are **absent** from the reset URL (strengthening the R-FR-01 acceptance criterion).
- **Verification:** `make test PYTEST_OPTS="-k 'price_sort or clear_all_filters or htmx_links'"`.

### T14 — Seed test: fix `>0` assertion that conflicts with `0` branch
**Module:** `src/backend/apps/seed/tests/test_seed.py` (L1219–1250; `@pytest.mark.seed` class `TestSeedCategoryIntegration` L980).
**Spec:** §6.8 / 7.5 / Q5/A.

- The seed generator returns `0` for ~20% of non-give-away ads (generators/ads.py L603–604), but this test asserts `price_amount > 0` for non-give-away (L1247). That conflicts and only fails under `make test-all`.
- Fix the assertion to allow `0` as a valid non-give-away "free" value: assert `price_amount is not None and price_amount >= 0` (and the explicit give-away `0` assertion at L1256 stays).
- **Verification:** `make test-all PYTEST_OPTS="-k 'seed and price'"` (full suite incl. seed).

### T15 — Bot tests: verify no Skip simulation; cover Free
**Module:** `src/telegram_bot/tests/test_ad_create.py` (L117, L151) + `src/telegram_bot/tests/conftest.py`.
**Spec:** §2.6 / 7.1.

- Existing bot tests use `price_amount: 100` and call `process_preview` directly — they **never simulate the Skip path** (spec 7.1 vacuously satisfied per investigation §8). Confirm no test asserts "Skip" behavior.
- Add/verify a test that the "Free" path sets `price_amount = Decimal("0.00")` and a test that `PricePayload(price_amount=None)` now raises (T3).
- **Verification:** `make test PYTEST_OPTS="-k 'test_ad_create or free'"`.

### T16 — `auto_moderation`: keep `is None` verbatim + comment (NO-OP behavior)
**Module:** `src/backend/apps/moderation/services/auto_moderation.py` (L138, L315).
**Spec:** §5.2 R-MM-01 / §6.4.

- **Keep** `if price_required and ad.price_amount is None:` **verbatim** at L138 and L315 — do **not** change to `<= 0` (audit Corr. #13: `<= 0` would `TypeError` on a real `None` and contradicts R-MM-01/§6.4). The code is already correct.
- Add a comment noting the bot now guarantees non-`None` at creation (T4), so this `is None` guard is the legacy/seed/manual-DB defensive fallback (R-MM-01).
- **Verification:** `uv run ruff check`; unit test `test_auto_moderation_price_always_present` — ad with `price_amount=0` passes; ad with `None` fails when `price_required=True`.

### T17 — i18n: wrap 3 strings, extract, translate, compile
**Modules:** `price_tags.py` (T5 → `gettext("Free")`), `partials/filter_form.html`/`list.html` (clear-all, T11), `list.html` (summary, T10).
**Spec:** §8 / 8.1 / project rule #16 / DoD `test_i18n_completeness.py`.

- Exactly three spec-mandated strings:
  1. `"Free"` — from `format_price_value` via `gettext("Free")` (T5).
  2. `"Clear all filters"` — from `ad_list.html` clear-all link via `{% trans %}`.
  3. `"Price: {min}–{max}"` — from `list.html` summary via `{% blocktrans with min=…|max=… %}`.
- `.mo` files are **already compiled** in this repo (`locale/{ru,bs,en}/LC_MESSAGES/django.mo` exist — audit §F). The work is: wrap strings → `make makemessages` → fill **non-empty** `msgstr` for `ru` + `bs` (`en` may be empty, msgid is English) → `make compilemessages`.
- Do **not** collect the divergent plan's `"Price must be a positive number."` / `"Price must not exceed 99999."` — those encode the wrong `>0` invariant and are not spec-mandated.
- **Verification:** `make test PYTEST_OPTS="test_i18n_completeness.py"` → all pass; `.po` files updated for all 3 languages with non-empty `ru`/`bs`.

---

## 6. Verification Strategy Summary

| Method | Scope | Owner task(s) |
|---|---|---|
| Ground-truth assertions (T1, T2) | Model field no-op, migration no-op | T1, T2 |
| `uv run ruff check` | Lint all changed files | Every task |
| `uv run basedpyright` | Type-check all changed files | T3, T4, T11B-CONFTEST, T13-FORMAT-TEST |
| `make test` | Fast gate (skips seed, ~1 min) | T4-BOT, T5-FORMAT, T6-TEMPLATES, T9, T10, T11, T12, T13, T15, T17 |
| `make test-recreate` | Fresh schema (`--create-db`) | T1, T2, T7, T11B-CONFTEST |
| `make test-all` | Full suite incl. seed (~35 min) | T8, T14, T17 |
| `test_i18n_completeness.py` | All translatable strings have translations | T17 |

**Critical verification order:**
0. **Step 0 (commit foundation):** lock the already-applied model/migration/seed-test changes so T1/T2/T8 remain true NO-OPs (see §2): `git add src/backend/apps/ads/models.py src/backend/apps/ads/migrations/0001_initial.py src/backend/apps/seed/generators/ads.py src/backend/apps/ads/tests/test_catalog_filters.py && git commit -m "refactor(ads): make price_amount non-null with default=0 (spec §6.1)"`. `git diff --stat` must then show those 4 files clean (no working-tree changes).
1. T1 + T2 → confirm no-op (don't touch the aligned foundation).
2. T3 → T4 → T15 (schema + bot: `0` accepted, Skip removed, Free added; `None` rejected by schema).
3. T5 → T6 → T12 → T13-FORMAT-TEST (display: `0`→"Free", falsy fixed, tests updated, count=9 preserved).
4. T7 (edit path: empty → `0`, no `IntegrityError`).
5. T8 → T14 (seed docs + seed test `>0` conflict resolved).
6. T9 → T10 → T11 → T13 (view context + summary + clear-all scope; catalog-filter tests green).
7. T11B-CONFTEST → T12 → T13-FORMAT-TEST (conftest forbids `None` + format tests).
8. T17 (final gate: wrap 3 strings, makemessages, fill ru/bs, compilemessages).

---

## 7. Deletions from the Divergent Plan (never execute these)

Each was a core `>0`/positive-only proposition that contradicts the spec's `>=0` model. They are **deleted**, not rewritten, because the code already matches the spec target on those layers or the proposal enforces the wrong invariant. *(Task IDs in this table reference the **divergent pre-rewrite plan**, not the final plan's T1–T17; e.g. divergent T11 = price-input validation, while final-plan T11 = clear-all URL fix.)*

| Task (divergent plan) | Why deleted |
|---|---|
| T1 — `default=Decimal("0.01")` + `CheckConstraint(Q(price_amount__gt=0))` | §6.1/R-MM-02 (`default=0`); R-PM-02 (`≥0`); R-DISP-01 (`0`→"Free"). A `>0` constraint makes every Free/Charity ad an `IntegrityError`. Code is **already** at the spec target (models.py L84; migration 0001 L94–102). |
| T3 — bot rejects `price_amount <= 0` ("Price must be a positive number.") | R-PM-02/Q1/B/Q2/B/Q3/A/R-DISP-01 require `0` explicitly enterable and displayed as "Free". The real defect is the still-present Skip button (T4 removes it) — there is **no** `>0` rejection in the actual code to begin with. |
| T4 — bot currency-required gate | Speculative; `PricePayload` already requires currency via the schema. Folded into T4 (schema non-optional) instead. |
| T5 — bot max-5-digits rejection | Not spec-mandated (§6.3/R-PM-02 only require `ge=0`); no `price_amount` value the bot accepts is unbounded-digits in a way the spec forbids. Drop to avoid inventing requirements; the `DecimalField(max_digits=10)` DB constraint is the real bound. |
| T7 — `_generate_price` returns `random.uniform(0.01, 99999)` (positive float); assert `> 0` | §6.8/7.5/Q5/A want `0` for the free branch so the Free state is seed-covered. Value is already `0`; only stale docstring/hint need fixing (T8). A positive-only seed removes free-ad coverage. |
| T9 (validation clause) — server parses `min_price`/`max_price` and validates `Decimal > 0` | §6.6 ("No structural change"); 5.3/R-DISP-01 (`0` valid, so `0–100` includes Free ads). |
| T11 (price-input clause) — `min="0.01"` + client JS "min > max" error | §6.6 ("No structural change"); R-DISP-01 (excludes Free from price filtering). Current `min="0" step="0.01"` (filter_form.html L49–67) already aligns. |
| T13 — moderation `if ad.price_amount <= 0` + comment "guaranteed > 0" | §5.2/R-MM-01/§6.4 keep `is None`; `<= 0` would `TypeError` on a real `None`. Code is already correct (L138/L315). |
| T14 — `conftest.create_test_ad` default `Decimal("99.99")` | §2 premise that `0` is a primary exercisable state (7.3/7.5); `99.99` steers the suite off the Free path. |
| T15 (assertion clauses) — `assert price_amount > 0`; `test_price_format.py` L48 `None`→`Decimal("0.01")` | R-DISP-02/§6.4 (legacy `None` preserved, not removed); §2.6 (class is already `TestPriceSort` — L391 — so the NullSort→Sort rename is invented); 7.5 (seeds include `0`). |
| T16 (string list) — collects `"Price must be a positive number."` + `"Price must not exceed 99999."`, omits `"Free"` + `"Price: {min}–{max}"` | §8/8.1 require exactly three strings ("Free", "Clear all filters", "Price: {min}–{max}"); DoD gates `test_i18n_completeness.py` on them. The two bot error strings encode the contradictory `>0` invariant. |

---

## 8. Rollout Notes

- **No production data migration:** dev-only (Q4) — recreate the test DB from zero; the model/migration are already spec-aligned (T1/T2 no-ops).
- **`edit.py` (T7) is required**, not optional: because the model is already `null=False`, an empty price on the edit form would now raise `IntegrityError` on `ad.save()` (edit.py L47). Coalescing empty→`0` makes "unset price on edit" = Free, consistent with the bot flow.
- **Bot + web deploy together:** both share the ORM model. The model change is already live; T4 (bot) + T7 (edit) close the `None`-writer leaks so the non-null field is never violated. Sequence: deploy T3+T4+T7 → restart bot → restart web.
- **Seed generator (T8)** is used by `make test-all` only; no production runtime impact; the stale docstring/hint is the only change (value already `0`).