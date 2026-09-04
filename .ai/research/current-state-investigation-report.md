# Current-State Investigation Report

**Purpose:** Verify the *actual* codebase state against the Specification
`Price Enforcement & Filter-Reset Architecture` (`.ai/problems/02_price-enforcement_and-filter-reset_spec.md`).

**Method:** Read and grep the real source under `src/`. Source paths in this
report were resolved by searching for the symbols named in the spec — the spec's
paths are illustrative shorthand. Line numbers are from the actual files.

**Central finding:** The codebase is in a **partially spec-aligned** state. The
spec's *target* is already implemented at the **model / migration /
moderation / seed** layers (price non-null, `default=0`, `is None` moderation
check, seed returns `0` not `None`). The divergent *Plan* critiqued in the
divergence report (`default=0.01` + `CheckConstraint(price_amount__gt=0)` +
bot `<=0` rejection + `<=0` moderation) was **never applied** — none of it
exists in the code. The *remaining* gaps are simply the spec's not-yet
implemented acceptance criteria (bot schema/flow, "Free" display, falsy-check
fix, price-range summary, clear-all scope, stale tests/docstrings).

**Confidence:** HIGH on all claims below (direct file reads + grep).

---

## 1. Model `Ad.price_amount`

**Real path(s) / lines:**
- `src/backend/apps/ads/models.py` lines 83–91 (field), line 83 comment,
  `class Meta.constraints` lines 317–344.
- `src/backend/apps/ads/migrations/0001_initial.py` lines 94–102 (field).

**Current behavior:**
- `price_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=False,
  null=False, default=Decimal("0"))` — line 84. Inline comment (line 83):
  `# Price is mandatory and must be a non-negative value (>=0, zero means Free).`
- `class Meta.constraints` (317–344) contains **only** status/timestamp
  `CheckConstraint`s (`ck_ads_published_at_if_published`, `..._archived_at_if_archived`,
  `..._rejected_at_if_rejected`, `..._moderation_failed_at_if_failed`,
  `..._deleted_at_if_deleted`, `..._failed_and_rejected_mutually_exclusive`).
  **No `CheckConstraint` on `price_amount`** and no `price_amount__gt=0`.
- Migration `0001_initial.py` line 94–102 matches exactly: `null=False,
  default=Decimal("0")`, no price constraint. Triggers are applied via `RunSQL`
  (lines 705–720), not a price check.
- Writers that SET `price_amount` (full set):
  - `src/telegram_bot/handlers/ad_create.py` L560, L613 (FSM `price_amount=None`
    via the Skip path); L619/621 (`PricePayload`); L832 (passed into
    `update_ad_and_moderate`); L1099 (`ad.price_amount = price_amount`).
  - `src/telegram_bot/handlers/ad_copy.py` L68 (FSM `price_amount=None`).
  - `src/backend/apps/ads/views/edit.py` L47 (`ad.price_amount = price_amount`)
    and L123 (`request.POST.get("price_amount")` → `None` on empty input).
  - `src/backend/apps/seed/generators/ads.py` L489 (`price_amount=price_amount`).

**Spec alignment verdict:** **ALIGN** with spec §6.1 target and R-MM-02
(`null=False, default=0`). The field definition and single migration are
already in the spec's intended end state.

**Needed change for spec intent (price=0 valid + displayed "Free"):** None at
the field level. HOWEVER the writers above are the leak: `ad_create.py:560/613`,
`ad_copy.py:68`, and `edit.py:127/47` can still hand `None` to `ad.price_amount`,
which is now `null=False` → an `IntegrityError` on `ad.save()` (ad_create
`update_ad_and_moderate` saves at L1205). Eliminating those `None` paths is
mandatory so the non-null field is never violated.

---

## 2. Bot flow `ad_create.py` (+ `PricePayload` schema)

**Real path(s) / lines:**
- `src/telegram_bot/handlers/ad_create.py` — currency keyboard
  `build_currency_keyboard` (529–544), `process_price_currency` (550–586),
  `process_price` (589–628), `update_ad_and_moderate` (1042–1243).
- `src/telegram_bot/schemas/message_payloads.py` `PricePayload` (39–51).

**Current behavior:**
- **Skip button IS present** at `ad_create.py:540`:
  `builder.button(text="⏭️ Skip", callback_data="price_skip")`.
- `price_skip` handler (L559–566) sets `price_amount=None` (L560) and advances to
  photos — no "Free" alternative.
- `process_price` (L589–628): text `"skip"` (L612–613) sets `price_amount=None`;
  otherwise `Decimal(text)` (L617) + `PricePayload(price_amount=price_value,
  price_currency=currency)` (L619). **No `<=0` / `>0` rejection** — `0` is
  accepted because the schema uses `ge=0`. (The divergent Plan's
  "Price must be a positive number" rejection does NOT exist in the code.)
- **No "Free" button** exists anywhere in the price step. The only zero path is
  typing `0` after selecting a currency.
- `PricePayload.price_amount` (message_payloads.py L47–50) is still
  `Annotated[Decimal | None, Field(ge=0)] = None`. Docstring (L43–45) still
  says "a price is optional and can be skipped with `Skip`."

**Spec alignment verdict:** **CONFLICT** with R-PM-01 (Skip button must be
absent), R-PM-03 (`PricePayload.price_amount` must reject `None` / be
non-optional), and 6.3 (no "Free" confirmation path). Note the *actual* bot
does NOT reject `0` (it accepts it via `ge=0`) — so the divergent Plan's
">0 rejection" is imaginary here; the real defect is the still-present Skip
button + optional schema.

**Needed change:** Remove the Skip button and both skip branches (ad_create.py
L540, L559–566, L612–613, and the "skip" help text at L524/L585/L599/L606); add
an explicit "Free" option that sets `Decimal("0.00")`; make
`PricePayload.price_amount: Decimal = Field(ge=0)` (non-optional) and update the
`update_ad_and_moderate` signature (L1048) to `Decimal` (not `Decimal | None`).

---

## 3. `price_tags.py` `format_price_value`

**Real path / lines:** `src/backend/apps/ads/templatetags/price_tags.py`
(L19–37 definition; used by `format_price` filter L58–75).

**Current behavior:**
- **Signature is `format_price_value(amount, currency)`** (two positional args:
  `amount: Decimal|int|float|str|None`, `currency: CurrencyCode|str|None`). This
  differs from the spec's §6.5 code example which assumes `format_price_value(ad)`.
- L33–34: `if amount is None: return ""`.
- For `amount == 0`: falls through to L35–37 → `_format_amount(Decimal("0"))` =>
  `"0"` → `f"0 {label}".strip()` => `"0 EUR"` (or `"0 BAM"`, etc.). **No "Free"
  branch.** `gettext` is not imported.
- Real callers (all 2-arg, so the §6.5 signature example is inaccurate):
  - `price_tags.py:72` `format_price` filter →
    `format_price_value(getattr(ad, "price_amount", None), getattr(ad, "price_currency", None))`.
  - `src/backend/apps/search/services/immediate_alerts.py:118` →
    `format_price_value(ad.price_amount, ad.price_currency)`.
  - `src/telegram_bot/handlers/alerts.py:190` →
    `format_price_value(ad.price_amount, ad.price_currency)`.

**Spec alignment verdict:** **CONFLICT** with R-DISP-01 (`0` → "Free"),
§6.5, §8 (i18n). Spec §6.5's suggested signature (`ad`) would break the three
2-arg callers above.

**Needed change:** Keep the existing 2-arg signature; add `if amount == 0:
return gettext("Free")` between the `None` check and the formatting logic,
import `gettext`, and add a `msgid "Free"` with non-empty `ru`/`bs` `msgstr`
plus `compilemessages`. Note: this also fixes the bot alert output
(`immediate_alerts.py:118`, `alerts.py:190`) which currently render a free ad as
`"0 EUR"`.

---

## 4. Templates

**Real path(s) / lines:**
- `src/backend/templates/ads/partials/ad_list.html` — falsy check at **L104**
  (spec Fact 2.5 says line 33 — that line is actually the active-chips wrapper
  `{% if current_listing_purpose or current_features or current_condition %}`).
- `src/backend/templates/ads/detail.html` L132/L133.
- `src/backend/templates/ads/dashboard.html` L87/L88.
- `src/backend/templates/admin/moderation/review.html` L40/L41.
- `src/backend/templates/ads/partials/filter_form.html` L49–67 (price inputs).
- `src/backend/templates/ads/list.html` L36 (HTMX target `#ad-list`).

**Current behavior:**
- Falsy-check bug `{% if ad.price_amount %}` + `{{ ad|format_price }}` is present
  in **four** templates (ad_list L104, detail L132, dashboard L87,
  review L40). Because `format_price` calls `format_price_value` which has no
  "Free" branch, `price=0` is *doubly* invisible: the falsy `{% if %}` hides the
  chip and even if shown it would read `"0 EUR"`.
- `filter_form.html` min/max price inputs (L49–67) use `min="0" step="0.01"` —
  already allow `0`. Spec §6.6 ("No structural change") is satisfied.
- **No price-range summary** (`{% blocktrans %}Price: {{ min }}–{{ max }}{%
  endblocktrans %}`) exists anywhere. There is no `active_price_min`/`max_price`
  context and no summary block.
- "Clear all filters" link exists at `ad_list.html:69–74`, but it is:
  - located inside the partial `ad_list.html` (not `list.html` as spec §6.6
    example / R-FR-01 suggests) and nested inside the
    `{% if current_listing_purpose or current_features or current_condition %}`
    block (L33) — so it only renders when a purpose/feature/condition chip is
    active.
  - scope of the generated URL: `?page=1&{% if query %}q=...&{% endif %}{% if
    current_sort %}sort=...&{% endif %}&lang=...` — **keeps `q` and `sort`**,
    **drops** `min_price`/`max_price`, purpose, condition, features. Category
    and city are path params so they are naturally preserved (matches R-FR-03).
- Tests: `test_clear_all_filters_has_push_url` (test_catalog_filters.py:664)
  only asserts `hx-push-url="true"` and `hx-get="?page=1` are present — it passes
  today but does **not** validate the reset scope. `test_all_htmx_links_have_push_url`
  (L646) hard-asserts exactly **9** `hx-get=` and **9** `hx-push-url` anchors;
  adding any new `hx-get` link (e.g. a summary or relocated clear-all) will break
  it.

**Spec alignment verdict:** **CONFLICT** — R-DISP-04 (falsy bug in 4 templates),
R-FR-01 (clear-all scope keeps `q`/`sort` instead of resetting them; placement
in partial), R-FR-02 (summary absent). filter_form `min="0"` aligns with §6.6.

**Needed change:** Replace `{% if ad.price_amount %}` →
`{% if ad.price_amount is not None %}` in all four templates (or delegate to
`{% if ad|format_price_value %}`); add the
`{% blocktrans with min=...|max=... %}Price: {{ min }}–{{ max }}{% endblocktrans %}`
summary in the active-filters area with `active_price_min`/`active_price_max`
context; fix the clear-all link to also drop `q` and `sort` (and harden the
template-count test if links are added).

---

## 5. `auto_moderation.py`

**Real path / lines:** `src/backend/apps/moderation/services/auto_moderation.py`
L138 (inside `auto_moderate`) and L315 (inside `check()`).
`src/backend/apps/moderation/models.py` L35 (`price_required`).

**Current behavior:**
- L138: `if price_required and ad.price_amount is None:` → `_fail_moderation(ad); return False`.
- L315: identical check inside `check()`.
- `ModerationCriteria.price_required` is `models.BooleanField(default=True)` (L35).

**Spec alignment verdict:** **ALIGN** with R-MM-01, §6.4, and Fact 2.2. The
`is None` check (not `<= 0`) is present verbatim. The divergent Plan's `<= 0`
change was never applied (and would have been a `TypeError` on a real `None`).

**Needed change:** None functionally. Per §6.4, optionally add a code comment
noting the bot-enforcement guarantee. (Caveat: because the Skip/`None` paths in
§2 are still live, the `is None` guard is now the safety net that catches those
pre-save `None` assignments before they crash the DB — so removing the Skip
paths in §2 makes this check a true legacy/seed fallback.)

---

## 6. Seed generator `_generate_price`

**Real path / lines:** `src/backend/apps/seed/generators/ads.py` L543–609.

**Current behavior:**
- Charity / give-away branch (L559–561): `if listing_purpose.slug == "give-away":
  return 0, CurrencyCode.EUR` → returns `0` (int), not `None`. Matches spec Q3/A.
- ~20% fallback in the generic-`else` (L603–607):
  `if self.faker.random_int(0, 99) < 20: amount = 0` then
  `return amount, CurrencyCode.EUR` → returns **`0`, not `None`**. Matches spec
  §6.8 target ("return `Decimal('0')` instead of `None`").
- Return type is `tuple[int | None, CurrencyCode]` (L547) and the docstring
  (L551) still says "Returns `(None, CurrencyCode.EUR)` for the ~20% …" — both
  are **stale**: the code returns `0` and never `None`.
- Returns a Python `int`, not `Decimal("0")`; functionally equivalent because the
  `DecimalField` coerces on save (seed passes `price_amount`/`price_normalized_eur`
  = the int to `Ad(...)` at L489–492).
- Seed tests: `test_give_away_ads_have_zero_price` (test_seed.py L1256, in the
  `@pytest.mark.seed` class `TestSeedCategoryIntegration` L980–981) asserts
  give-away `price_amount == 0` — aligned. The other test at L1219–1250
  (`gen.generate(10)`, same `@pytest.mark.seed` class) asserts
  `if ad.price_amount is not None: … else: assert ad.price_amount > 0` (L1247)
  — which **conflicts** with the generator's 20%-returns-0 branch for
  non-give-away ads (a 0 for a non-give-away ad would fail `> 0`).

**Spec alignment verdict:** **PARTIAL — ALIGN on value semantics** (returns `0`,
never `None`, charity=0). **CONFLICT on docs + test staleness** (docstring and
type hint still say `None`; seed test asserts `>0` for non-give-away, which
cannot hold for the generator's 0% branch).

**Needed change:** Fix the docstring + return-type hint (drop `None`); fix the
L1219–1250 seed test to accept `0` as a valid non-give-away "free" value (or
restrict the 0 branch to give-away only). Optionally return `Decimal("0")` to
match the spec's literal wording.

---

## 7. Views (`listings.py` / `search.py`)

**Real path / lines:**
- `src/backend/apps/ads/views/listings.py` `listings` (L190–194 signature,
  `category_slug`/`city_slug` are **path parameters**).
- `src/backend/apps/search/views/search.py` `search` (L35).
- `src/backend/apps/ads/urls.py` L24–35.

**Current behavior:**
- Category & city are **path params** (`ads:listings`, `ads:listings_category`,
  `ads:listings_city` — urls.py L25–27). `request.GET.get("category")` (listings
  L282) and `request.GET.get("city")` (L302) are only **suggestion fallbacks**
  when the path slug is invalid — they are not the active filter. So category/city
  are naturally excluded from any clear-all URL (R-FR-03 holds by construction).
- Price parsing: `min_price`/`max_price` are raw GET strings; converted with
  `int(...)` and filtered on `price_normalized_eur__gte/lte` (listings L324–340;
  search L89–101). **No `>0` validation** — `0` range is accepted. (The divergent
  Plan's `>0` validation was never applied.)
- Context exposes `min_price`/`max_price` (raw strings) — lists.py L436–437,
  search.py L260–261. **No `active_price_min`/`active_price_max`** (the spec's R-FR-02
  block variable names), so the price-range summary block cannot render.
- Price sort uses `F("price_normalized_eur").asc/desc(nulls_last=True)`
  (listings L396–400, search L191–204, L229–232) — **`price_normalized_eur`, not
  `price_amount`** as spec §6.7 / 7.2 imply ("`order_by('price_amount')`").
  Functionally fine: a `0`-amount ad has `price_normalized_eur = 0.0000`, so it
  sorts first in `price_asc` (covered by `TestPriceSort.test_fts_price_asc_free_sorts_first`,
  L557).
- `django-filter` is declared in `pyproject.toml` (L17) / `uv.lock` but **never
  imported** in `src/` — spec Fact 2.6 is accurate.

**Spec alignment verdict:** **PARTIAL.** Price filter/sort correctly handle `0`
(spec intent met). **CONFLICT** on context variable naming (spec wants
`active_price_min`/`max`; code has `min_price`/`max_price`) and on the
price-range summary being absent. Spec §2.6 "18 inline URL constructions" is
accurate (verified by `test_all_htmx_links_have_push_url` L646: 9 anchors ×
href + hx-get = 18 URL strings; `test_lang_param_in_all_htmx_urls` L662 asserts
`count("LANGUAGE_CODE") >= 18`).

**Needed change:** Expose `active_price_min`/`active_price_max` (or alias
`min_price`/`max_price` in the template) so the §6.6 summary block can render;
keep hand-rolled filters (django-filter stays unused per spec §10).

---

## 8. Tests

**Real path / lines:**
- `TestPriceNullSort` — **does NOT exist.** The actual class is
  `TestPriceSort` (`src/backend/apps/ads/tests/test_catalog_filters.py` L391).
  The divergence report's premise (AREA 4.2) is wrong.
- `test_clear_all_filters_has_push_url` (test_catalog_filters.py L664): asserts
  `hx-push-url="true"` and `hx-get="?page=1` are present — passes today; does
  not validate reset scope.
- `TestPriceSort.test_fts_price_asc_free_sorts_first` (L557): creates
  `price=0` and asserts the free ad sorts first ascending — **spec-aligned**
  (R-DISP-01 / 7.3).
- `test_price_format.py:48`: `ad = Ad(price_amount=None, price_currency=None)` —
  constructs an in-memory `Ad` (no DB save), so it does not hit the NOT NULL
  constraint; `format_price(ad) == ""` passes. Stale relative to the now-non-null
  field (the divergence report's AREA 4.2 claimed the plan would change this to
  `Decimal("0.01")` — the actual code still uses `None`).
- conftest `create_test_ad` (src/backend/conftest.py L112–151): default
  `price: int | Decimal | None = 100` (L120), type hint still permits `None`.
  Docstring (L134) "Pass `price=None` for an unpriced ad" is **stale** — passing
  `None` now writes NULL to the non-null column (lines 140–142 set both
  `price_amount` and `price_normalized_eur` to `None`) and would raise on
  `Ad.objects.create`. No test in the fast gate currently calls it with `None`
  (grep found no `create_test_ad(..., price=None)`), so it is a latent trap.
- Bot tests: `src/telegram_bot/tests/test_ad_create.py` L117 & L151 use
  `"price_amount": 100` (not `None`, not skip) — they call `process_preview`
  directly and **never simulate the Skip path**. Spec 7.1 acceptance
  ("existing bot tests that simulate skipping price are updated or removed") is
  vacuously satisfied.

**Spec alignment verdict:** **CONFLICT** on staleness/documentation —
`TestPriceNullSort` name is wrong (already `TestPriceSort`); `test_price_format.py`
still exercises `None`; `create_test_ad` docstring still advertises
`price=None`. **ALIGN** on free-sort coverage.

**Needed change:** Update the `create_test_ad` signature/docstring to disallow
`None` (or default `0`); update `test_price_format.py` to cover the `0`→"Free"
case once §3 is implemented (and keep/drop the `None` case per R-DISP-02);
fix the `@pytest.mark.seed` test at L1219–1250 to allow `0` for non-give-away.

---

## 9. Migration

**Real path / lines:** `src/backend/apps/ads/migrations/0001_initial.py` (+
`__init__.py`). This is the **only** migration file in
`src/backend/apps/ads/migrations/`.

**Current behavior:**
- `price_amount` (L94–102): `null=False, default=Decimal("0")`, `decimal_places=2`,
  `max_digits=10`, no `CheckConstraint` on the field.
- `class Meta` options (L327–329): only `db_table="ads"` (no in-migration
  `constraints` block); all constraints/indexes are added via `AddIndex`/
  `AddConstraint` operations (L525–703) — all status/timestamp related; triggers
  via `RunSQL` (L705–720).
- There is **no** `0002_*` migration and **no** `SeparateDatabaseAndState`.

**Spec alignment verdict:** **ALIGN** with spec §2.7 / §6.9 / §7.6 (single
`0001_initial.py`, dev-only, no extra migration file). The divergence report's
AREA 6.1 (`SeparateDatabaseAndState`) was a LOW-severity note about the *Plan*,
not reality — no such migration exists and none is needed.

**Needed change:** None. (If a production migration is ever required to flip a
legacy nullable column non-null, that is explicitly out of scope per Q4 — see
§4 of the spec.)

---

## Conflicts Requiring Plan Correction (what the divergence report / plan got wrong vs. reality)

The divergence report (`.ai/plans/18_divergence-report.md`) compares a *Plan*
to the *Spec* and audits it against "runtime facts in `src/backend/`." Several
of those runtime facts are **stale or inaccurate**, and the divergent *Plan*
itself was **never applied** to the code. Concretely:

1. **"Fact 2.1 — `price_amount` still nullable"** is **false.** The actual
   field is `null=False, default=Decimal("0")` (models.py L84–91; migration
   0001 L94–102). The spec's model target was already reached; the codebase was
   *not* in the spec's "pre-implementation" state when the report was written.
   → The report's highest-severity item (1.1: plan adds `default=0.01` +
   `CheckConstraint(>0)`) is moot: that constraint **does not exist** in the code.

2. **"`format_price_value(ad)`" premise is wrong.** The actual signature is
   `format_price_value(amount, currency)` (price_tags.py L19–22). All three
   callers (`format_price` L72, immediate_alerts.py L118, alerts.py L190) pass
   two args. The report's §6.5-based reasoning and its "current code returns
   `0 EUR` for 0" (which it got right) are based on the 2-arg function, but the
   report's framing of "consumer table / tasks" treats it as ad-argument.

3. **`TestPriceNullSort` does not exist.** The class is `TestPriceSort`
   (test_catalog_filters.py L391). The report's AREA 4.2 ("rename NullSort→Sort,
   remove None") is moot, and it overlooked the existing
   `test_fts_price_asc_free_sorts_first` (L557) which already covers the
   spec-required `0`-sorts-first behavior.

4. **The divergent Plan (`>0` everywhere) was never implemented.** There is no
   `CheckConstraint(Q(price_amount__gt=0))`, no `default=0.01`, no bot
   `<=0`→"must be a positive number" rejection, and moderation uses `is None`
   (L138/L315), not `<=0`. The codebase is spec-aligned on the core `≥0`
   semantics; the report's "10 HIGH contradictions" describe a Plan that is not
   in the code.

5. **The actual "Clear all filters" differs from the report's characterization.**
   The report (AREA 1.9) critiqued the Plan's "reset all GET params to base
   catalog URL" as dropping category/city. The **actual** link
   (ad_list.html L69–74) is a relative `?page=1&q=…&sort=…&lang=…`: it
   **preserves path-param category/city** (so R-FR-03 already holds) but
   **keeps `q` and `sort`** (contradicting R-FR-01, which says those must be
   reset). The real defect is the inverse of what the report assumed.

6. **The spec's own "Facts (Verified)" are partly stale.** §2.1 (nullable
   field) is wrong; §2.3 (seed returns `None` for ~20%) is wrong (it returns
   `0` now, docstring stale); §2.4 line refs (540/560/613) and §2.5 are
   approximately right, but §6.5's `format_price_value(ad)` signature is
   inaccurate.

7. **An internal code inconsistency the report missed:** the seed generator
   returns `0` for ~20% of non-give-away ads (generators/ads.py L603–604), but
   the seed test at test_seed.py L1219–1250 asserts `price_amount > 0` for
   non-give-away ads (L1247). That test lives in a `@pytest.mark.seed` class
   (TestSeedCategoryIntegration L980), so it is skipped by `make test`; it would
   be exercised only by `make test-all`.

8. **`create_test_ad(price=None)` is a latent crash** the report's AREA 4.1 did
   not flag as a correctness issue — it only discussed the Plan's
   `Decimal("99.99")` default. The actual default is `100`, but the signature/docstring
   still permit `None`, which now violates the non-null field (conftest.py
   L120/L134, L140–142).

9. **No `SeparateDatabaseAndState` and no extra migration** (report AREA 6.1) —
   confirms the report's LOW rating there, but it is worth stating plainly: only
   `0001_initial.py` exists and it already matches the spec target.

10. **Bot tests do not simulate skipping price** (test_ad_create.py uses
    `price_amount: 100`), so the report's AREA 1.4 concern about a `None`
    reaching a hypothetical `<=0` check never materializes in the *actual* code
    (the actual `process_price` does `Decimal(text)` before `PricePayload`, so
    `None` from Skip is handled by the `text == "skip"` branch, not by a `>0`
    comparison).

**Bottom line for execution:** discard the divergent Plan and instead complete
the Spec on top of the already-spec-aligned foundation. The remaining, concrete
work is: (a) make the bot price mandatory + "Free" entry and make
`PricePayload` non-optional (and consequently `edit.py`'s empty-price →
`None` must become `0`); (b) add the `0`→"Free" branch in `format_price_value`
+ i18n; (c) fix the four `{% if ad.price_amount %}` falsy checks; (d) add the
price-range summary + fix clear-all to also reset `q`/`sort`; (e) fix the stale
seed test/docstring/type-hint; (f) run `makemessages`/`compilemessages` and the
i18n completeness gate.
