# Test Audit Report — Filter Regression Fix (Spec Task T7)

**Audit target:** Test files requiring updates for the filter-regression fix defined in `.ai/problems/05_filter-regression_spec.md` (Tasks T1–T8).
**Scope (per request):**
- `src/backend/apps/ads/tests/test_catalog_filters.py` — `TestFilterUrlReset` class
- `src/backend/apps/core/tests/test_templates.py` — `TestQueryReplace` class

**Date:** 2026-09-03 · **Auditor:** kilo/poolside/laguna-s-2.1

> Note: the request references `src/backend/tests/test_templates.py`, but the actual
> file lives at `src/backend/apps/core/tests/test_templates.py` (the `core` app owns the
> `query_replace` tag in `apps/core/templatetags/dict_tags.py`).

---

## 1. Test suite organization (how tests are structured)

### 1.1 Module layout

| File | Markers | Scope |
|---|---|---|
| `src/backend/apps/ads/tests/test_catalog_filters.py` | `pytestmark = [pytest.mark.django_db, pytest.mark.integration]` (L32) | Integration tests exercising the full filter → sort → paginate → render pipeline via the real Django test `Client`. |
| `src/backend/apps/core/tests/test_templates.py` | `pytestmark = [pytest.mark.unit]` (L26) | Unit tests that render Django `Template` objects in isolation using `unittest.mock.Mock` for the request — **no DB, no view dispatch**. |

### 1.2 Two rendering strategies are used

**Strategy A — static template-source inspection** (catalog_filters.py, `TestFilterUrlReset` L637–L709):
Tests such as `test_form_uses_request_path_not_empty`, `test_all_htmx_links_have_push_url`, `test_lang_param_in_all_htmx_urls`, and `test_clear_all_filters_has_push_url` read the template file directly:
```python
path = Path(__file__).resolve().parents[3] / "templates/ads/partials/ad_list.html"
content = path.read_text(encoding="utf-8")
```
They then assert on raw substrings/counts. `parents[3]` from `apps/ads/tests/` resolves to the `templates/` root (`apps/ads/tests` → `ads/tests` → `ads` → `templates`). These tests do **not** render the template or go through a view, so they cannot observe context-dependent branching (e.g. `{% if query %}`) and cannot distinguish the search page from the listings page.

**Strategy B — full view render with Django `Client`** (catalog_filters.py, integration tests L715–L840):
Tests issue a real request through the view, then assert on `response.content.decode("utf-8")`. They use the standard Django test client with an HTMX marker header (see §3).

### 1.3 The `TestFilterUrlReset` class structure

The class has three sections (annotated by comment banners):

1. **Static template-source assertions** (L637–L709) — Strategy A. Reads `ad_list.html` / `filter_form.html` as plain text.
2. **Integration tests — HTMX rendered output** (L715–L783) — Strategy B. Renders through the view with `HX-Request: true`.
3. **Behavioral test** (L789–L821) — Strategy B. Asserts no parameter accumulation on a real request.

`TestSortOnSearchResults` (L824–L840) is a separate class but also asserts on rendered HTMX output (search-page sort dropdown visibility).

---

## 2. Exact assertions that need to change

### 2.1 `test_all_htmx_links_have_push_url` — `test_catalog_filters.py` L647–654

**Current code:**
```python
content = path.read_text(encoding="utf-8")
assert content.count("hx-get=") == 9
assert content.count('hx-push-url="true"') == 9
```

**Verification of current counts** (grep via `Select-String -AllMatches` on `ad_list.html`):
- `hx-get=` → **9** matches confirmed.
- `hx-push-url="true"` → **9** matches confirmed.

**Why it must change:** Task T3 converts the price-range `<div>` (L32–37) into a removable chip with an `×` `<a>` removal link, which adds one `hx-get="..."` attribute and one `hx-push-url="true"` attribute. After T3 the counts become **10** / **10**.

**Required change:**
```python
assert content.count("hx-get=") == 10
assert content.count('hx-push-url="true"') == 10
```

**Severity:** HIGH (test fails after T3 lands) — but only after T3 is implemented; the test currently passes.

### 2.2 `test_lang_param_in_all_htmx_urls` — `test_catalog_filters.py` L656–663

**Current code:**
```python
content = path.read_text(encoding="utf-8")
# 9 links × 2 attrs (href + hx-get) = 18 occurrences
assert content.count("LANGUAGE_CODE") >= 18
```

**Verification of actual counts** (full-file substring `.count()`):
- Current file → **44** occurrences of `LANGUAGE_CODE`.

The test's stated rationale ("9 links × 2 attrs = 18") is **incorrect** as an explanation of what `content.count("LANGUAGE_CODE")` measures. Each URL-bearing link emits `LANGUAGE_CODE` **four** times — `{% if LANGUAGE_CODE %}` ×2 (once in `href`, once in `hx-get`) and `{{ LANGUAGE_CODE }}` ×2 (once in `href`, once in `hx-get`). That is 9 links × 4 = **36** from URL attrs alone, plus **8** from display-side `get_*:LANGUAGE_CODE` filter calls (purpose/condition/feature lookup names L44/57/70; `get_title` L96/108; `get_description` L114; `get_city_name` L128; `get_category_name` L129). 36 + 8 = 44.

**Finding (advisory):** The assertion is so loose (`>= 18` against an actual count of 44) that it would still pass even if **half** the URL links dropped their `lang` param. It does not actually verify "every `hx-get` URL preserves `LANGUAGE_CODE`." The hard-count test in §2.1 is far stricter and is the real guard.

**Required change:** Bump the floor to **20** per the spec recommendation (L168: "≥18 → ≥20"), so it tracks the 10-link × 2-attr URL structure after T3 (10 links × 4 = 40 URL-side + 8 display = 48 after T3). This keeps the lower bound meaningful relative to the link count, though the assertion remains structurally loose.

### 2.3 `test_clear_all_filters_has_push_url` — `test_catalog_filters.py` L665–687

**Current code asserts (the "wrong" behavior):**
```python
match = re.search(
    r'hx-get="(\?page=1{% if LANGUAGE_CODE %}[^"]*)"',
    content,
)
assert match is not None, "Clear all filters hx-get link not found in ad_list.html"
reset_url = match.group(1)
assert 'hx-push-url="true"' in content
# R-FR-01: the reset URL must drop q and sort (clears ALL query params).
assert "&q=" not in reset_url
assert "q=" not in reset_url
assert "&sort=" not in reset_url
assert "sort=" not in reset_url
```

**Why it must change — TWO distinct problems:**

**(a) Wrong behavior encoded, line L683–687:** The spec (filter-ui.md L414–416; PO-Q3=A) requires that on the **search results page**, clear-all **preserves `q`**. This test statically asserts `q` is absent from the reset URL — which is only correct for the **listings page**. The test reads the template source (Strategy A) and cannot render the `{% if query %}` branch that T4 will introduce, so it will assert against whichever branch the regex matches. After T4 the clear-all template becomes a `{% if query %}...{% else %}...{% endif %}` block; the current regex `^hx-get="(\?page=1{% if LANGUAGE_CODE %}[^"]*)"` matches the `{% else %}` (listings) branch only, so it would silently still pass on the listings branch but provides **zero coverage** for the search branch.

This is the **central correctness defect** in the test file (echoed by `.ai/problems/05_filter-regression_spec.md` §2.5 L73 and §6 Research L209, and `catalog-filter-ui-implementation-recommendations.md` L143).

**(b) No visibility-guard assertion, line L666–668 / L682:** The docstring claims to verify the link "resets all query params (R-FR-01)" but the test never checks that the clear-all link is **wrapped in the chips-block `{% if %}`** condition. Before T2 the link sits at `ad_list.html` L77–83 (outside any conditional); after T2 it must move **inside** the extended `{% if current_listing_purpose or current_features or current_condition or active_price_min or active_price_max %}` block (L39). The test asserts nothing about placement or visibility — so it would pass both before and after T2 regardless of whether the link is guarded. This lets Problem 1 (always-visible button) regrow undetected.

**Required changes to this test:**
1. **Assert the clear-all link is inside the chips `{% if %}`** guard — i.e., that the `hx-get` clear-all link is a descendant of the extended chips-block conditional, and that it does **not** render unconditionally at top level of the partial. (Static-source: verify the link appears textually within the `{% if ... %}` / `{% endif %}` that wraps the chips container.)
2. **Split/parameterize for the two pages:**
   - **Listings page** (`/`): assert `q` is absent from the reset URL (current behavior, retained).
   - **Search page** (`/search/?q=...`): assert `q=<query>` IS present in the reset `hx-get` href (new, per CR-4 / PO-Q3=A). This requires switching to **Strategy B** (render through the search view) or at minimum rendering the template with `query` set, because the `{% if query %}` branch is context-dependent.
3. Retain the `hx-push-url="true"` assertion (no change to that line).

### 2.4 `TestQueryReplace` — `test_templates.py` L104–131

**Current tests:**
- `test_preserves_existing_params_when_overriding_one` (L107–112): `"q=phone&lang=ru"` → override `lang=en`; asserts `q=phone` kept. Single-value.
- `test_adds_new_param_when_none_exists` (L114–117): `""` → `lang=en`; asserts exact `"lang=en"`.
- `test_preserves_multiple_params` (L119–125): `"q=phone&page=2&sort=price"` → overlay `lang=bs`; asserts all four kept.
- `test_empty_overrides_preserves_all` (L131): `"q=phone&page=2"` no overrides; asserts both kept.

**What the spec says is missing** (`.ai/problems/05_filter-regression_spec.md` L79):
> "`query_replace` tests … do NOT test multi-value params preservation or `page` param preservation."

**Precision note on the `page` claim:** `test_preserves_multiple_params` **does** include `page=2` in its input and asserts `"page=2" in result`. So `page` *preservation* is incidentally covered. What is **not** covered is (a) multi-value param preservation and (b) `page` *stripping* semantics (relevant to T6/Approach C discussion at `htmx-language-switcher-fix-evaluation.md` L106–L109, which notes `query_replace` preserves `page` by design and argues that stripping belongs in the consumer, not the tag). The finding's wording is slightly imprecise but its core gap is valid.

**Required change:** Add a test for multi-value param preservation. The `query_replace` tag (`dict_tags.py` L47–69) does `query = request.GET.copy()` then `query[key] = value` for each kwarg — since the single consumer (`language_switcher.html` L35) only ever sets `lang`, all other keys (including multi-valued `features`) survive via `query.urlencode()`.

**New test to add (Strategy A, same helper):**
```python
def test_preserves_multi_value_params_when_overriding(self) -> None:
    """Multi-valued params (e.g. features=a&features=b) are preserved when
    overriding an unrelated key."""
    result = _render_query_replace("features=delivery&features=negotiable&sort=price", lang="en")
    assert "features=delivery" in result
    assert "features=negotiable" in result
    assert "sort=price" in result
    assert "lang=en" in result
```

---

## 3. Fixtures, helpers, and HTMX-request patterns in use

### 3.1 Ad-creation helpers (`src/backend/conftest.py`)

- **`create_test_ad(...)`** (L129–168): module-level function, not a pytest fixture (imported via `from conftest import create_test_ad`). Handles the project's strict `CheckConstraint`s by auto-setting `published_at` / `rejected_at` / `archived_at` / `moderation_failed_at` / `deleted_at` per `status`. Signature:
  ```python
  create_test_ad(user, category, city, *, title="Test Ad", description="...", status=AdStatus.ON_MODERATION, price=100, price_currency=CurrencyCode.EUR, source=AdSource.TELEGRAM, **kwargs) -> Ad
  ```
  - `price` maps to `price_amount` AND `price_normalized_eur` (EUR base 1.0). `price=0` ⇒ Free/Charity (the only ad-hoc way to create a price-filtered ad; no `price` StrEnum needed).
  - FKs and scalars flow through `**kwargs` → `Ad.objects.create(**defaults)`.
  - **M2M `features` are NOT in kwargs** — they must be added post-hoc via `ad.features.add(...)` (see `TestFeaturesFilter._seed_ads` L287/295 and `test_chip_link_has_push_url_in_rendered_output` L733). This is the project's established pattern.
  - `listing_purpose` / `listing_condition` are FKs (`LookupItem`) passed as kwarg directly — used in `TestListingPurposeFilter` L108/116 and `TestListingConditionFilter` L172/180.

- **`create_test_ads_bulk(...)`** (L171–211): bulk-create `count` rows via `Ad.objects.bulk_create`; same kwargs semantics. Used by `test_pagination_links_have_push_url_in_rendered_output` (L747) and `test_lang_param_preserved_in_rendered_output` (L769) — both need ≥25 rows to force pagination.

### 3.2 Lookup fixtures (local to test_catalog_filters.py)

- `purpose_lookup` (L35–51): creates the `listing_purpose` `LookupGroup` + `sell`/`rent` `LookupItem`s.
- `feature_lookup` (L54–75): creates the `listing_feature` group + `delivery`/`negotiable`. Intentionally excludes `new`/`used` (those live in `listing_condition`).
- `condition_lookup` (L78–94): creates `listing_condition` group + `new`/`used`.

These are **not** shared via conftest — they are defined locally in the test module because they are catalog-filter-specific. They should be reused (by reference) by any new price-chip / clear-all tests that need real ads.

### 3.3 Generic model fixtures (`src/backend/conftest.py`)

- `seller` (L87–94): `User` with `telegram_id=900000001`.
- `user` (L97–104): `User` with `telegram_id=900000002` (alias of seller, for bot tests).
- `category` (L107–110): root `Category(name="Транспорт", slug="transport")`.
- `city` (L113–121): `City(country_code="ME", ...)`.

### 3.4 HTMX-request pattern

Every integration test that targets an HTMX partial uses Django's `Client` with the `HX-Request` header:
```python
client = Client()
response = client.get("/", headers={"HX-Request": "true"})
```
Confirmed at:
- L515, L551, L579, L611: `"/search/?q=...&sort=..."` with `HX-Request: true`.
- L721, L737, L780: `"/"` with `HX-Request: true`.
- L758: `{"HX-Request": "true", "Accept-Language": "en"}` — combines HTMX header with Accept-Language for deterministic `{% trans %}` rendering.
- L838: `"/search/?q=транспорт"` with `HX-Request: true`.

This is the canonical pattern for any new integration test that needs to assert on rendered chip/pagination/clear-all HTML.

### 3.5 Template-assertion pattern

Three sub-patterns coexist:
1. **Static source read** (L637–L663): `Path(...).read_text()` + `content.count(...)` / `in` / `re.search`. No DB marker needed (these tests are in a `django_db`-marked class but most static tests are logically DB-free).
2. **Rendered `response.content` check** (L715–L840): full view render via `Client`, then `response.content.decode("utf-8")` and substring asserts.
3. **`response.context` check** (L124, L152, L316, etc.): some tests inspect `response.context["page_obj"]` to assert on the **actual filtered queryset** rather than HTML — this is the strongest correctness check and is used for all the filter-semantics tests (`TestListingPurposeFilter`, `TestFeaturesFilter`, `TestFilterAndSearchCombine`, etc.).

### 3.6 The `query_replace` unit-test helper (`test_templates.py` L77–101)

`_render_query_replace(get_params, **overrides)` builds a `Mock` request with a real `QueryDict(get_params)` and renders `{% query_replace request ... %}` via `django.template.Template` + `Context`. It is a pure-tag unit test (no view, no DB). `test_i18n_completeness.py` is the only other consumer of tag-level tests in this file's vicinity.

---

## 4. Assertions that need to change — condensed table

| Test (file:line) | Current assertion | Required change | Driving spec task |
|---|---|---|---|
| `test_all_htmx_links_have_push_url` (test_catalog_filters.py:653–654) | `hx-get==9`; `hx-push-url=="true"`==9 | → `== 10` for both | T3 adds price-chip `×` link |
| `test_lang_param_in_all_htmx_urls` (test_catalog_filters.py:663) | `count("LANGUAGE_CODE") >= 18` | → `>= 20` (+ strengthen if test rewritten) | T3 (10 links); advisory: assertion is overly loose |
| `test_clear_all_filters_has_push_url` (test_catalog_filters.py:684–685) | `&q=` and `q=` **absent** from reset URL | List that out (682–687); **add** search-page branch asserting `q` **present** | T4 (CR-4, PO-Q3=A) |
| `test_clear_all_filters_has_push_url` (whole, 665–687) | No visibility-guard check | **Add** assertion: clear-all link is inside the chips-block `{% if %}` / hidden when no chips | T2 (CR-1, PO-Q1=C) |
| `TestQueryReplace` (test_templates.py) | No multi-value param test | **Add** `test_preserves_multi_value_params_when_overriding` | T7 gap (spec L79); T6/Approach-C `page`-stripping note |

---

## 5. New tests needed (with recommended placement and shape)

All new tests follow the patterns in §3 (integration tests via `Client` + `HX-Request: true`; static-source tests via `Path.read_text`).

### 5.1 Tests for T3 (price chip) — `test_catalog_filters.py`

1. **`test_price_filter_renders_removal_chip`** (new, `TestFilterUrlReset` or a new `TestPriceChip`).
   - Seed one ad, issue `client.get("/?min_price=100&max_price=500", headers={"HX-Request": "true"})`.
   - Assert the rendered HTML contains a price chip (`inline-flex ... rounded-full`) with an `×` `<a>` whose `hx-get` omits `min_price`/`max_price` and preserves `q` (if any) and `page=1`.
   - Reuse `feature_lookup`/`condition_lookup`/`purpose_lookup` only if chips need to coexist; otherwise a bare price-only request suffices (this also validates CR-1's price-only visibility).

2. **`test_chips_and_clear_all_render_when_price_only`** (new).
   - `client.get("/?min_price=100&max_price=500", headers={"HX-Request": "true"})`.
   - Assert the chips container + clear-all link **render** (price must trigger the extended `{% if %}` per T1/CR-2). This is the behavioral mirror of the static guard assertion in §4.

3. **`test_chips_and_clear_all_hidden_when_no_filters`** (new).
   - `client.get("/", headers={"HX-Request": "true"})` with no query params.
   - Assert the chips container div and the "Clear all filters" link **do not appear** in `response.content`. (Closes Problem 1 / CR-1.)

### 5.2 Tests for T2 (clear-all visibility guard) — `test_catalog_filters.py`

4. **`test_clear_all_link_is_inside_chips_conditional`** (new static-source test, sibling of the existing static tests).
   - Read `ad_list.html`; assert the clear-all `hx-get` link is **not** a top-level render — i.e., it appears textually after the extended `{% if %}` (L39) and before its matching `{% endif %}` / before the `# Ads grid` comment.
   - Rationale: the existing `test_clear_all_filters_has_push_url` asserts on the *URL content* of the link but never on its *placement*. This guards Problem 1 (unconditional visibility).

### 5.3 Tests for T4 (search-page clear-all `q` preservation) — `test_catalog_filters.py`

5. **`test_clear_all_preserves_q_on_search_page`** (new integration test).
   - Seed one ad; `client.get("/search/?q=телефон&page=1", headers={"HX-Request": "true"})`.
   - In `response.content`, locate the clear-all link's `hx-get` value and assert it contains `q=телефон` (URL-encoded as `q=%F2...` or via `urlencode`) and **does not** contain `min_price`/`max_price`/`features` etc.
   - This is the search-page mirror of `test_clear_all_filters_has_push_url` and directly validates CR-4 / PO-Q3=A.

6. **`test_clear_all_drops_q_on_listings_page`** (new integration test, can be a focused variant).
   - `client.get("/?q=не-используется&min_price=100", headers={"HX-Request": "true"})` — actually the listings page has no `q`; better: `client.get("/?min_price=100&max_price=500")` then assert clear-all `hx-get` lacks `q`. This re-asserts the listings-side contract through the renderer (stronger than the static-source test).

> Recommendation: **replace** the static regex in `test_clear_all_filters_has_push_url` with **two** integration tests (search vs. listings) that parse the rendered `hx-get` attribute with `re.search`, OR keep the static test for the listings branch and add the integration test for the search branch. The static test alone cannot cover the `{% if query %}` branch.

### 5.4 Tests for T7 (query_replace multi-value) — `test_templates.py`

7. **`test_preserves_multi_value_params_when_overriding`** (new, `TestQueryReplace`).
   - See §2.4 for the exact body. Asserts `features=delivery` and `features=negotiable` both survive an unrelated `lang=en` override.

> Optional follow-up (if T6/Approach C ever strips `page` in the tag): add `test_strips_page_when_overriding_lang` — but per `htmx-language-switcher-fix-evaluation.md` L106–L109, stripping belongs in the consumer, so `query_replace` should keep preserving `page`. Do **not** add a page-stripping test against the tag itself.

---

## 6. Path/reference map (all line numbers verified)

| Symbol | Path | Lines | Notes |
|---|---|---|---|
| `TestFilterUrlReset` (static + integration) | `src/backend/apps/ads/tests/test_catalog_filters.py` | 623–821 | `TestSortOnSearchResults` 824–840 is separate |
| `test_all_htmx_links_have_push_url` | `src/backend/apps/ads/tests/test_catalog_filters.py` | 647–654 | asserts 9/9 |
| `test_lang_param_in_all_htmx_urls` | `src/backend/apps/ads/tests/test_catalog_filters.py` | 656–663 | asserts ≥18 (actual 44) |
| `test_clear_all_filters_has_push_url` | `src/backend/apps/ads/tests/test_catalog_filters.py` | 665–687 | asserts q/sort absent; no visibility check |
| `TestQueryReplace` + `_render_query_replace` | `src/backend/apps/core/tests/test_templates.py` | 77–131 | `query_replace` tag unit tests (no DB) |
| `query_replace` implementation | `src/backend/apps/core/templatetags/dict_tags.py` | 46–69 | `request.GET.copy()` + `query[key]=value` + `urlencode()` |
| `ad_list.html` (chips, clear-all, pagination) | `src/backend/templates/ads/partials/ad_list.html` | 32–83 (summary/chips/clear-all); 139–184 (pagination) | 9 `hx-get` links; clear-all at L77–83 currently unguarded (outside L39 chips `{% if %}`) |
| `filter_form.html` (`hx-get="{{ request.path }}"`) | `src/backend/templates/ads/partials/filter_form.html` | — | asserted at test_catalog_filters.py L637–645 |
| `listings()` context dict | `src/backend/apps/ads/views/listings.py` | 447–467 | **does NOT** export `"query"`; exports `active_price_min/max` (L457–458), `current_*` filter vars |
| `search()` context dict | `src/backend/apps/search/views/search.py` | 274–290 | **does** export `"query": query` (L276); same price/purpose/condition/feature context |
| `create_test_ad` helper | `src/backend/conftest.py` | 129–168 | sets status timestamps; `price`→`price_amount`+`price_normalized_eur` |
| `create_test_ads_bulk` helper | `src/backend/conftest.py` | 171–211 | bulk via `bulk_create`; needs count≥25 for pagination |
| Generic fixtures (`seller`, `category`, `city`) | `src/backend/conftest.py` | 87–121 | overridden per-module as needed |
| Lookup fixtures (`purpose_lookup`, `feature_lookup`, `condition_lookup`) | `test_catalog_filters.py` | 35–94 | local to module |
| HTMX header pattern (`HX-Request: true`) | `test_catalog_filters.py` | L515, L551, L579, L611, L721, L737, L758, L779, L780, L838 | canonical for partial-render tests |
| Spec: filter regression (T1–T8) | `.ai/problems/05_filter-regression_spec.md` | 1–304 | §4 = tasks; §5 = PO decisions; §9 = test impact |
| Spec: T7 test-impact table | `.ai/findings/catalog-filter-ui-implementation-recommendations.md` | L201–206 | exact "before→after" per test |
| Spec: clear-all on search page | `docs/01-spec/filter-ui.md` | L414–416 | "preserves `q`" |

---

## 7. Summary of findings

1. **`test_all_htmx_links_have_push_url` (L647–654)** — must bump hard-count 9→10. Straightforward mechanical change. The 9/9 counts are verified.

2. **`test_lang_param_in_all_htmx_urls` (L656–663)** — must bump floor 18→20, **but the assertion is structurally loose**: `content.count("LANGUAGE_CODE")` returns 44 (not 18), because it counts `{% if LANGUAGE_CODE %}`, `{{ LANGUAGE_CODE }}`, and display-side `get_*:LANGUAGE_CODE` filters across the whole file, not just the 9 htmx links. Recommend (advisory) rewriting to count `LANGUAGE_CODE` occurrences **within `hx-get=` attribute values** only, so the test actually verifies per-link lang preservation rather than passing at ~2.4× its stated intent.

3. **`test_clear_all_filters_has_push_url` (L665–687)** — the most important fix. It (a) encodes the **spec-deviant** behavior (asserts `q` absent on what will become the search branch) and (b) asserts **nothing** about the clear-all link's visibility guard. Must be split/parameterized into listings-side (q absent) and search-side (q present) and must add a guard-placement assertion. The search-side variant must use Strategy B (rendered view) because the `{% if query %}` branch is context-dependent and invisible to static-source tests.

4. **`TestQueryReplace`** — spec gap confirmed: no multi-value param test. The `page`-preservation claim in the spec (L79) is partially inaccurate — `test_preserves_multiple_params` already covers `page=2` preservation — but multi-value (`features=a&features=b`) coverage is genuinely missing. Add the single recommended test in §5.7.

5. **No existing test asserts the clear-all link is hidden when no chips are active** — this is the core of Problem 1 (CR-1) and is completely unguarded today. Tests 5.2/5.3 above close this gap.

6. **`listings()` does not export `query`** (only `search()` does at L276). The T4 spec explicitly recommends adding `"query": None` to listings.py context (filter-ui.md T4 L135 / implementation-recommendations L138–141) for symmetric partial behavior. This is a one-line, behavior-preserving view change that **must land before** the search-side clear-all test can rely on `{% if query %}` being safely falsy on the listings page. Verify it as part of T7.
