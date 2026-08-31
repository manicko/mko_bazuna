# Block 5: Filter Controls, Chips & Management

## 1. Block Summary

Verifies the HTMX-driven filter form, active-filter chip removal links, "Clear all filters", hidden-context preservation, and the price/feature/purpose/condition filter semantics across both the listings (`/`) and search (`/search/?q=`) views. Documents two live chip-removal URL bugs (Purpose and Condition chips), a template/backend price-normalization mismatch, and the sort-ignored-on-FTS gap.

**Source:** Researcher Findings (Block 5) — provided in task brief; cross-referenced against `src/backend/templates/ads/partials/ad_list.html`, `src/backend/templates/ads/partials/filter_form.html`, `src/backend/apps/ads/views/listings.py`, `src/backend/apps/search/views/search.py`, `src/backend/templates/components/header_catalog.html`.
**Top plan:** `.ai/problems/01_search_patterns_test_verification_top_plan.md` — Block 5

---

## 2. Findings Table

| # | Variation | Implementation Location (file:line) | Coverage Status | Existing Test (file:line) | Test-Engineer Task | Risk |
|---|-----------|-------------------------------------|-----------------|---------------------------|---------------------|------|
| V1 | **Clear-all behavioral** — "Clear all filters" link (`ad_list.html:71-74`) emits `?page=1` retaining only `q` and `sort`; correctly drops `listing_purpose`, `condition`, `features`, `min_price`, `max_price`, `city`, `category`. | `ad_list.html:71-74` | GAP | `test_catalog_filters.py:506-511` (`test_clear_all_filters_has_push_url` — asserts `hx-push-url="true"` presence + `hx-get="?page=1` prefix only; does NOT assert full URL composition or that all filter params are dropped) | Integration/HTMX: GET `/?listing_purpose=sell&condition=new&features=delivery&min_price=10&max_price=100&city=<slug>&category=<slug>&sort=date_desc` with `HX-Request: true`; regex-extract the "Clear all filters" `hx-get` URL; assert it contains exactly `page=1` (+ `q`/`sort` if present) and omits every filter param. Mirror for `/search/?q=<t>&features=...`. | Medium |
| V2 | **Chip-removal URL content** — three cases: (a) **Feature chip correct** (`ad_list.html:64-65` — preserves all filters, excludes only targeted slug via `keep != f.slug`); (b) **Purpose chip BUG** (`ad_list.html:41-42` — omits `current_condition` collateral AND drops `current_listing_purpose` itself, never re-adds purpose); (c) **Condition chip BUG** (`ad_list.html:53-54` — re-adds `&condition={{ current_condition }}`, making removal a no-op, while preserving purpose). | `ad_list.html:41-42, 53-54, 64-65` | GAP | `test_catalog_filters.py:530-543` (`test_chip_link_has_push_url_in_rendered_output` — asserts `hx-push-url="true"` presence in rendered output; does NOT assert any chip URL param composition) | Three HTMX-rendered assertions: (1) Purpose chip removal URL must omit `listing_purpose` **and preserve** `condition` (currently drops condition — assert the fix); (2) Condition chip removal URL must omit `condition` (currently re-adds it — assert no-op bug fixed) and preserve `listing_purpose`; (3) Feature chip removal URL must preserve all non-targeted features + all other filters. Extract each chip's `hx-get` via regex; assert param set by splitting on `&`. | High |
| V3 | **Purpose single-select** — `filter_form.html:21-29` renders a single `<select name="listing_purpose">`; backend applies exact slug match via `ads.filter(listing_purpose__slug=...)`; options resolved category-constrained when `breadcrumb_category` is active, else full active set. | `filter_form.html:21-29`; filter app: `listings.py:341-345`, `search.py:97-100`; option resolution: `listings.py:365-386`, `search.py:119-140` | EXISTS | `test_catalog_filters.py:96-153` (`TestListingPurposeFilter::test_listings_filters_by_purpose`, `test_search_filters_by_purpose`) | None required — existing coverage is sufficient. Note: the category-constrained `resolved_purposes` set is verified under Block 4 V2 (`block_04.md` V2); Block 5 need only confirm the resolved set is passed to the template context (already asserted via `context["resolved_purposes"]` in Block 4). | Low |
| V4 | **Features AND semantics** — `getlist("features")` + chained `.filter(features__slug=slug)` per item + `.distinct()`; an ad matches only if it possesses ALL selected features. | `listings.py:353-363`, `search.py:107-117` | EXISTS | `test_catalog_filters.py:304-321` (`TestFeaturesFilter::test_all_selected_features_required`), `:323-336`, `:338-352` | None required — existing coverage is sufficient and asserts AND semantics (ad with both features included; single-feature and featureless ads excluded). | Low |
| V5 | **EUR price normalization (silent decimal rejection)** — `int(min_price)`/`int(max_price)` with `except ValueError: pass` silently ignores non-integer input; template inputs use `step="0.01"`, inviting decimals that `int()` rejects → filter silently dropped. | price parse: `listings.py:321-339`, `search.py:83-95`; template: `filter_form.html:50` (`min_price` `step="0.01"`), `filter_form.html:56` (`max_price` `step="0.01"`) | GAP | `test_catalog_filters.py:391-444` (`TestPriceNullSort` — covers NULLS LAST price sort, NOT input parsing) | Integration: GET `/?min_price=10.50&max_price=99.99` → assert price filter silently ignored (priced + unpriced ads both appear, since `int("10.50")` raises `ValueError` → `pass`); GET `/?min_price=50` → assert only ads with `price_normalized_eur >= 50` appear. Document the `step="0.01"` vs `int()` mismatch; recommend a **decision gate** (align backend to `Decimal`/`float` parsing OR change template `step="1"`). | Medium |
| V6 | **HTMX filter application** — `filter_form.html:5-10` uses `method="get"`, `hx-get="{{ request.path }}"`, `hx-target="#ad-list"`, `hx-swap="innerHTML"`, `hx-push-url="true"`; hidden `q`/`category`/`city` inputs (`filter_form.html:11-13`) preserve context on submit; form re-renders server-side on every HTMX navigation. | `filter_form.html:5-13` | EXISTS (partial) | `test_catalog_filters.py:517-528` (`test_form_renders_path_only_hx_get` — asserts `hx-get="/"` path-only and absence of `hx-get="/?features=..."`) | Extend `test_form_renders_path_only_hx_get` or add a sibling: GET `/?category=<slug>&city=<slug>&features=delivery` with `HX-Request: true`; assert the rendered form contains hidden inputs `name="q"`, `name="category"`, `name="city"` carrying the active context (proving non-accumulation + context preservation). No CSRF assertion needed (GET — see B1). | Low |
| V7 | **Filter+sort combination** — sort is applied unconditionally on listings; on `/search/?q=` the FTS branch orders by `-rank, -published_at, -id` (`search.py:180-182`) and **ignores** `sort`, even though `filter_form.html:103` hides the sort dropdown via `{% if not query %}`. Sort param persists in pagination/chip URLs regardless. | sort always-on (listings): `listings.py:388-402`; sort parsed: `search.py:156`; FTS-ignores-sort: `search.py:158-188` (orders `-rank`); sort-applied-when-no-query: `search.py:198-208`; dropdown gate: `filter_form.html:103` | GAP | `test_catalog_filters.py:391-444` (listings sort — `TestPriceNullSort`); **search sort-ignored** uncovered — see Block 3 v6 (`block_03.md` V6) which defines the FTS-hidden-sort gap test. | Cross-reference Block 3 V6 to avoid duplicate work. Add a Block 5-specific assertion: GET `/search/?q=<term>&sort=price_desc` → assert result ordering matches FTS rank (not price DESC) and `response.context["current_sort"] == "price_desc"` (param parsed + echoed for URL preservation); assert no `<select name="sort"` in rendered HTML (dropdown hidden when query present). | Medium |
| B1 | **CSRF on filter form** — `{% csrf_token %}` present in header search form only (`header_catalog.html:115`); intentionally absent from `filter_form.html` (GET request, idempotent — no token needed). | `header_catalog.html:115` (token); `filter_form.html:5-10` (no token) | GAP (no assertion) | `test_autocomplete_template.py:55-64` (`test_search_input_has_htmx_autocomplete_attributes` — asserts `name="q"` + htmx attrs, but does NOT assert `{% csrf_token %}` presence/absence) | Template-source assertion (no DB): read `header_catalog.html` and assert `{% csrf_token %}` appears within the `data-search-form` (lines 114-132); read `filter_form.html` and assert `{% csrf_token %}` is absent. Document as intentional (GET filter form). | Low |
| B5 | **`value="None"` on empty price inputs** — `filter_form.html:50-51` / `filter_form.html:56-57` render `value="{{ min_price }}"` / `value="{{ max_price }}"`; when no price param, Django renders `None` → `value="None"` shown in the input. | `filter_form.html:50-51` (`min_price`), `filter_form.html:56-57` (`max_price`) | GAP | None | HTMX-rendered assertion: GET `/` (no `min_price`/`max_price`) with `HX-Request: true`; assert the price inputs render `value=""` (or no `value` attr), NOT `value="None"`. If `"None"` renders, fix to `{{ min_price|default:'' }}` and add this assertion alongside the existing `TestFilterUrlReset` template-source tests. | Low |

## 2.1 HTMX 2.0 Migration Notes (findings context)

- **V2 (chip-removal URL fixes):** The Purpose (`ad_list.html:41-42`) and Condition (`ad_list.html:53-54`) chip-removal fixes are pure Django-template URL-composition changes — they modify query parameters inside existing `hx-get`/`href` attribute **values** (via the `keep`/`drop` set logic). They do **not** add new `hx-get` attributes, so the 9-occurrence `hx-push-url="true"` / `hx-get` parity invariant asserted at `test_catalog_filters.py:499-504` is preserved. Migration-transparent.
- **V6 (HTMX filter application):** `filter_form.html:5-13` uses only declarative HTML attributes (`hx-get`, `hx-target`, `hx-swap`, `hx-push-url`, plus hidden `q`/`category`/`city` inputs) for form submission. No `htmx.*` JS API and no `addEventListener` event listener. All of these attributes are unchanged in HTMX 2.0 — migration-transparent; no Block 5 action required.
- **B1 (CSRF):** The `{% csrf_token %}` assertion is a template-source (Django tag) concern only — it does not involve any HTMX JS API. Unchanged by the HTMX 2.0 migration.
- **B5 (price `value="None"`):** The `value="{{ min_price }}"` / `value="{{ max_price }}"` rendering is a Django-template variable concern, not an HTMX JS-API call. Unchanged by the HTMX 2.0 migration.

---

## 3. Priority

**Medium** — Overall block priority.

- **V2 (High):** Two live bugs in chip-removal URL composition — the Purpose chip drops `condition` collateral and drops itself; the Condition chip is a no-op (re-adds itself). These cause silent filter-state corruption on the primary buyer flow and must be fixed before the chip tests are asserted.
- **V5 (Medium):** Silent decimal rejection (`int()` on `step="0.01"` inputs) causes price filters to vanish with no user feedback — a UX/data-loss risk, not merely cosmetic.
- **V1, V7 (Medium):** Test gaps on the clear-all and filter+sort URL contracts; the behaviors themselves are mostly correct (V1) or already partially covered (V7 overlaps Block 3 v6).
- **V3, V4, V6, B1 (Low):** Verified behaviors with existing (if partial) coverage; no new tests required beyond optional extensions.

---

## 4. Dependencies

| Depends On | Block / Surface | Rationale |
|------------|-----------------|-----------|
| Block 3 (FTS results rendering) | `.ai/plans/_blocks/block_03.md` | Block 5's filter form submits to `/search/?q=` (Block 3 domain); V6's HTMX contract re-renders the `ad_list.html` partial that Block 3's FTS branch renders; V7's sort-ignored-on-FTS gap is jointly owned (cross-ref block_03.md V6). |
| Block 4 (Category browsing & context scoping) | `.ai/plans/_blocks/block_04.md` | V3's category-constrained `resolved_*` option sets and V5's no-category-control-on-`/search/` are resolved by `CategoryLookupResolver` (Block 4 V2); Block 5 tests the filter controls Block 4 feeds into `filter_form.html:16-93`. |
| Block 6 (Ad card rendering) | `.ai/plans/_blocks/block_06.md` | Block 5's chips, grid, and pagination all live inside the `ad_list.html` partial that Block 6 renders (cards, `feature_tag.html`, `favorite_heart.html`); the V6 HTMX re-render swaps `#ad-list` containing this entire partial. |
| Block 7 (URL state, pagination & navigation) | `.ai/plans/_blocks/block_07.md` | V1 clear-all and V2 chip-removal push browser URL via `hx-push-url="true"`; the pagination links (`ad_list.html:142-171`) and the 9-occurrence `hx-push-url` anchor contract are Block 7's domain — the chip/clear-all URL assertions depend on Block 7's param-preservation conventions. |

---

## 5. Validator Recommendations

### 5.1 Chip URL composition (V2 — High, fix-first)

- Render the ads list via HTMX (`HX-Request: true`) with multiple filters active: `?listing_purpose=sell&condition=new&features=delivery&features=negotiable&min_price=10&max_price=100`.
- Regex-extract each chip's `hx-get` value from the response HTML. Assert by splitting on `&` and comparing the param-key set:
  - **Feature chip (correct):** target slug excluded; `listing_purpose`, `condition`, `min_price`, `max_price` all present.
  - **Purpose chip (bug):** after fix, `listing_purpose` absent, `condition` preserved (currently dropped).
  - **Condition chip (bug):** after fix, `condition` absent, `listing_purpose` preserved (currently re-added → no-op).
- Use `urllib.parse.parse_qs` on each extracted URL for robust key/multivalue comparison.

### 5.2 Clear-all & pagination URL contract (V1, V7)

- Build a request with the maximal active-filter set; assert the "Clear all filters" `hx-get` contains only `page=1` (+ `q`/`sort` if those were active). Do **not** reuse the existing `hx-push-url` presence check — assert the exact query string.
- For V7, issue `GET /search/?q=<term>&sort=price_desc` and assert (a) ordering follows FTS rank not `price_normalized_eur DESC` (create a high-price/low-rank ad to disambiguate), (b) `response.context["current_sort"] == "price_desc"`, (c) the rendered HTML omits `<select name="sort"`.

### 5.3 Price input parsing (V5 — decision gate)

- Assert `GET /?min_price=10.50&max_price=99.99` does **not** filter (decimal rejected by `int()` → both priced and null-price ads appear), proving the silent-drop behavior.
- This is a **decision gate** before any test is "fixed": either (a) backend parses `Decimal` (align with `step="0.01"`), or (b) template changes `step="1"`. The plan must record which is chosen; tests assert the chosen contract.

### 5.4 Template-source guards (B1, B5)

- **B1:** assert `filter_form.html` contains no `{% csrf_token %}` and `header_catalog.html` contains it at the header search form. No DB needed (follow `test_autocomplete_template.py` pattern).
- **B5:** assert `filter_form.html:50-57` uses `{{ min_price|default:'' }}` style (or equivalent) so empty renders `value=""` not `value="None"`. Add an HTMX-rendered assertion under `TestFilterUrlReset`.

### 5.5 Shared HTMX convention

- Confirm the 9-occurrence `hx-push-url="true"` / `hx-get` parity invariant (`test_catalog_filters.py:499-504` asserts count == 9) is not broken by any chip URL rewrite in V2 — each chip link must retain `hx-push-url="true"`.
- Corrective record: the `htmx.get(url, ...)` call at `header_catalog.html:536` (favorites badge) is **not** a migration-resolvable concern for Block 5. `htmx.get` is a pre-existing `TypeError` bug owned by Block 1's B6 — it requires an explicit code fix (`htmx.get(url, ...)` → `htmx.ajax('GET', url, ...)`), not solely an HTMX 2.0 CDN bump. It is therefore out of Block 5's scope; the 9-count invariant is unaffected.

### 5.6 HTMX 2.0 Migration

- HTMX 2.0 migration actions touching Block 5 surface:
  - **(a)** Version tag bumps `@1.9.12`→`@2.0.x` in the 5 base templates — transparent to Block 5 tests (no test asserts the version string).
  - **(b)** B6 (`htmx.get` at `header_catalog.html:536`) is **NOT** resolved by the migration — requires an explicit code fix `htmx.get(url, ...)` → `htmx.ajax('GET', url, ...)`.
  - **(c)** `htmx.ajax` at `cabinet/favorites.html:47` is preserved in HTMX 2.0 — **NO** change needed.
  - **(d)** `htmx:afterSwap` at `header_catalog.html:544` needs **NO** rename — `addEventListener` fires both camelCase and kebab-case names in 2.0.
- None of the above alter Block 5's declared filter / chip / clear-all contracts.

---

*End of Block 5* · 82 lines
