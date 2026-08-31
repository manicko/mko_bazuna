# Block 1: Entry Points & Landing States

## 1. Block Summary

Verifies the initial render and default state of the four entry surfaces — homepage `/`, category entry `/category/<slug>/`, city entry `/city/<slug>/`, and ad detail `/<ad_id>/` — focusing on the shared header form structure, the search-bar presence on every surface, and the context-drop contract. Locks in three low-severity bugs (B1 CSRF token in GET form, B5 `value="None"` on price inputs, B6 HTMX 2.x `htmx.get` API mismatch) and six Test-Engineer coverage gaps (G1–G6).

**Source:** `.ai/research/search-journeys-our-architecture.md`, `search-journeys-spec.md`, `search-journeys-validation.md` (G1)
**Top plan:** `.ai/problems/01_search_patterns_test_verification_top_plan.md` — Block 1, lines 49–64 (key variations) and line 62 (dependencies)

---

## 2. Findings Table

| # | Key Variation | Implementation Location | Coverage | Existing Test (file:line) | Test-Engineer Task | Risk |
|---|---|---|---|---|---|---|
| B1 | **CSRF token leaks into GET URL** — `{% csrf_token %}` (header_catalog.html:115) sits inside `<form method="get">`; on submission `csrfmiddlewaretoken=…` appears in the query string. AJAX POSTs already carry `X-CSRFToken` via `<body hx-headers>` (list.html:19, detail.html:23), so the token is unnecessary and harmful in a GET form. | header_catalog.html:115; safe AJAX path list.html:19, detail.html:23 | GAP (G2) | None | (a) Template-source test (no DB): assert `csrfmiddlewaretoken` hidden input does NOT appear inside `<form … data-search-form>`. (b) Integration: render `/` and assert the GET form has no `csrfmiddlewaretoken` input; assert the GET action URL contains no `csrfmiddlewaretoken=`. (c) Regression: confirm `<body … hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'` is still present on list.html:19 and detail.html:23 for AJAX POSTs (favorites, preferred-city, save-search, filter). | LOW |
| G1 | **Header form carries only `q` + CSRF** — form at header_catalog.html:114–126 exposes `name="q"` and `{% csrf_token %}` only; no hidden `category`/`city`/`listing_purpose`/`condition`/`features`/`min_price`/`max_price`. This is the *intended* context-drop contract (header search drops category/city/filter context). Separate hidden inputs live in filter_form.html:11-13 (listings/filter form), not the header. | header_catalog.html:114-126 (form+inputs); filter_form.html:11-13 (non-header hidden inputs) | GAP (G1) | test_autocomplete_template.py:55-64 (asserts `name="q"` + htmx attrs; does NOT assert absence of hidden inputs) | Template-source test (no DB, mirror test_autocomplete_template.py:15-19 unit style): parse the `<form … data-search-form>` block in header_catalog.html and assert the only `<input>` names are `q` and `csrfmiddlewaretoken`. Optionally: rendered integration on `/category/<slug>/` asserting the rendered header form emits only those two inputs. | LOW |
| V-home | **Homepage landing state** — renders all PUBLISHED ads newest-first (`listings.py:248-254` filter + `:401-402` default `-published_at`), 24-per-page paginator (`listings.py:246,414`), search bar present, header rendered. | listings.py:246,248-254,401-402; list.html:34; header_catalog.html:117 | EXISTS (partial) | test_auth_nav.py:78-89 (header + `id="search-input"`); test_listings_sort.py:87-97 (newest-first default); test_catalog_filters.py:99-125 (published-only via `page_obj`) | No new test required for the base landing. Optional: assert `/` returns 200 with non-empty `page_obj` and `id="search-input"` rendered (already covered). | LOW |
| G3 | **"Back to listings" link on ad detail** — detail.html:184-186 renders `<a href="javascript:history.back()">{% trans "Back to listings" %}</a>`. | detail.html:184-186 | GAP (G3) | test_breadcrumbs_render.py:119-146 (breadcrumb on detail — different element); test_auth_nav.py:91-101 (header only) | Integration: GET a PUBLISHED ad detail (`create_test_ad(..., status=AdStatus.PUBLISHED)` so the `status=AdStatus.PUBLISHED` queryset at listings.py:62 matches); assert the "Back to listings" anchor is present with `href="javascript:history.back()"` and the localized label. | LOW |
| G4 | **Telegram contact deep-link href on ad detail** — detail.html:161-167: when `ad|can_contact`, `<a href="https://t.me/{{ bot_username }}?start=contact_{{ ad.id }}">`; else disabled button. `bot_username` injected from context (listings.py:89), NOT `settings.BOT_USERNAME` in template. | detail.html:161-167; listings.py:89 (bot_username context) | GAP (partial) | test_detail_context.py:106-111 (context `bot_username == settings.BOT_USERNAME`); :133-141 (template uses `{{ bot_username }}`, not `settings.BOT_USERNAME`) — neither asserts the rendered `href` | Integration: GET published ad detail; assert `href="https://t.me/<settings.BOT_USERNAME>?start=contact_<ad.id>"` is present. Also assert the `can_contact=False` branch renders the disabled button and NO telegram `href`. Build the expected URL from `settings.BOT_USERNAME`. | LOW |
| G5 | **Category-constrained filter option sets** — listings.py:365-386: when `breadcrumb_category` active, `resolved_purposes`/`resolved_features`/`resolved_conditions` resolved via `CategoryLookupResolver` ancestor-walk (nearest-explicit-ancestor-wins, 300s cache at lookup_resolution.py:155); full active `LookupItem` set fallback when no category. Rendered at filter_form.html:16-46. | listings.py:365-386; filter_form.html:16-46; lookup_resolution.py:31 (class), :155 (cache key) | GAP (G5) | test_catalog_filters.py:96-603 (filter application; no through-table bindings, does not test constrained option sets); test_breadcrumbs_render.py:98-117 (breadcrumb only) | Integration: GET `/category/<child>/` with `CategoryListingPurpose`/`Feature`/`Condition` through-table bindings on an ancestor; assert `context['resolved_purposes']` equals the ancestor-resolved set, NOT the full `LookupItem` set; compare to `/` returning full sets. Assert `cache.clear()` between tests (resolver 300s LocMemCache). | MEDIUM |
| G6 | **City preselection on `/city/<slug>/`** — listings.py:286-319: path `city_slug` → `effective_city`, `ads.filter(city_id=city.id)`; invalid slug → did-you-mean banner (ad_list.html:26-32). | listings.py:286-319; ad_list.html:26-32 | GAP (partial) | test_preferred_city_readback.py:134-145 (`test_path_city_overrides_preferred` — asserts `current_city=="budva"` + scoped results, but with a prior preferred-city cookie; tests filtering+context, not rendered badge preselection); test_preferred_city.py:126-145 (`TestHeaderCityBadge` — header badge for *preferred* city, not `/city/<slug>/` path) | Integration: GET `/city/<slug>/` with NO preferred-city cookie; assert the header city badge shows the localized city name AND `page_obj` is scoped to that city; assert invalid city path renders the did-you-mean banner (`ad_list.html:26`). Use the catalog `City` fixture. | LOW |
| B5 | **`value="None"` on price inputs** — filter_form.html:50-58: `value="{{ min_price }}"`/`value="{{ max_price }}"` where both default to `None` (`request.GET.get` at listings.py:323,325). Django renders `{{ None }}` as the literal string `None` → `value="None"` on a `type="number"` input. | filter_form.html:50-58; listings.py:323,325 | GAP | None | Integration: GET `/` (no price params) and assert `min_price`/`max_price` inputs do NOT render `value="None"` (expect empty); GET `/?min_price=100` and assert `value="100"`. | LOW |
| B6 | **`htmx.get()` is not a real HTMX API in any version** — `htmx.get()` is not a real HTMX API in ANY version (1.9.12 or 2.0.x). pre-existing `TypeError` bug: header_catalog.html:536 calls `htmx.get(url, {target, swap})`, which does not exist in any HTMX release; runtime loads `htmx.org@1.9.12` (list.html:16, detail.html:20). Requires explicit code fix: `htmx.get(url, {target, swap})` → `htmx.ajax('GET', url, {target, swap})`. NOT resolved by the HTMX 2.0 version bump. Affects header favorites-badge auto-refresh (`cabinet:favorites_count`) only. | header_catalog.html:536; runtime list.html:16, detail.html:20 | GAP | None | Static/template-source test (no DB): assert the loaded HTMX `<script>` tag targets `htmx.org@2.0` (not `1.9.12`) on `list.html:16` and `detail.html:20`; assert the header favorites-badge auto-refresh call at `header_catalog.html:536` uses `htmx.ajax('GET', ...)` (NOT `htmx.get(...)` — which is not a real HTMX API in any version). This is a consistency regression guard: if anyone re-introduces `htmx.get`, the test catches it. | N/A (resolved via code fix) |

**Legend:** `EXISTS` = covered by existing tests; `EXISTS (partial)` = partially covered; `GAP` = no test. Bug IDs (B1, B5, B6) reference Researcher findings; G-IDs (G1–G6) reference Test-Engineer gaps.

---

## 3. Priority

**Low–Medium.** Block 1 covers foundational landing states with no high-severity defects. B1 (CSRF in GET URL) is a minor security-hygiene leak; B5 is cosmetic; B6 is resolved by an explicit code fix (`htmx.get` → `htmx.ajax` at header_catalog.html:536), not the HTMX version migration, so it is no longer a test-plan priority — it is an implementor fix with only a regression-guard test. Gaps G1–G6 are primarily regression guardrails for documented *intended* behavior (context-drop, city/category scoping).

- **G5 (category-constrained filter option sets) is the single MEDIUM item** — wrong filter option sets directly degrade buyer filtering UX and is jointly owned with Block 4 (block_04.md V2, same resolver `lookup_resolution.py`, same listings.py:365–386). Ensure assertions are consistent across both blocks, not duplicated.
- **B1 is the highest-severity bug** (CSRF token in URL) but still LOW — it is a hygiene/information-leak issue, not a functional blocker; the GET search has no privilege-bearing side effect.
- All other findings are **LOW**.

Note: the context-drop behavior (G1/B3) is intentional and listed in the top plan's "Open Product Decisions" (#3) — tests assert *current* behavior; revisit if product decides to preserve context.

---

## 4. Dependencies

Block 1 has **no upstream dependencies** (top plan line 62). It is a **dependency for downstream blocks** — the shared header form and filter form must not be mutated without coordinating with:

| Depends On | Block / Surface | Rationale |
|---|---|---|
| (none) | — | Top plan line 62: "Dependencies: None." Block 1 is the foundational entry-layer. |
| Feeds into | Block 2 — `.ai/plans/_blocks/block_02.md` | Landing state is the baseline for autocomplete context (top plan line 79). |
| Feeds into | Block 3 — `.ai/plans/_blocks/block_03.md` | Header form structure + context-drop (B1, G1, B3) is the submission contract Block 3 tests (block_03 V1). B1 fix touches the shared header. |
| Feeds into | Block 4 — `.ai/plans/_blocks/block_04.md` | Category-constrained filter option sets (G5) are jointly owned — block_04 V2 covers the same resolver (listings.py:365-386, lookup_resolution.py) and the context-drop form (block_04 V4 = header_catalog.html:114-132). Keep scope/assertions consistent. |
| Feeds into | Block 5 — `.ai/plans/_blocks/block_05.md` | B5 (`filter_form.html` price inputs) and G5 (resolved option sets) feed directly into the filter form tested in Block 5. |

**No intra-block task dependencies** — all findings can be implemented/tested independently.

---

## 5. Validator Recommendations

### 5.1 Rendered-HTML vs. template-source split
- **Template-source (unit, no DB):** for pure structural assertions, follow the `test_autocomplete_template.py:15-19` pattern (`pytestmark = pytest.mark.unit`, read via `Path`). Targets: G1 (header form input set), B1 (no csrf in GET form), B5 (price input templates), B6 (HTMX version tag + `htmx.get` signature).
- **Rendered-HTML (integration, Django test Client):** for behavioral/href assertions, follow `test_auth_nav.py:78-101`, `test_breadcrumbs_render.py:119-146`. Targets: B1 (query string), G3 (back link), G4 (telegram href), G5 (option sets), G6 (city badge + did-you-mean). Use `response.content.decode("utf-8")` + substring assertions; for context, `response.context[...]`.

### 5.2 CSRF handling (B1)
- The GET search form must NOT carry `{% csrf_token %}`. Confirm the AJAX POST path is unaffected: `<body … hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'` on list.html:19 and detail.html:23 supplies the header for htmx POST swaps (favorites heart, preferred-city POST, save-search POST; filter form is GET so unaffected). Verify `X-CSRFToken` is still sent on the POST-based controls — those are the only consumers of the CSRF token, all via the `hx-headers` body attribute.
- **HTMX 2.0 migration & B6 code fix (implementor coordination):** As part of implementation, bump the loaded HTMX `<script>` version tag in `list.html:16` and `detail.html:20` from `htmx.org@1.9.12` to `htmx.org@2.0.x`. The B6 code fix — `htmx.get(url, {target, swap})` → `htmx.ajax('GET', url, {target, swap})` at `header_catalog.html:536` — must land alongside the version bump: `htmx.get()` is not a real HTMX API in any version (1.9.12 or 2.0.x), so the bug is NOT resolved by the version migration alone and the explicit call-site fix is required.

### 5.3 Catalog & cache isolation (G5, G6)
- Category/city entry tests need the real category catalog. Reuse the class-scoped `_load_catalog` fixture pattern (`test_breadcrumbs_render.py:49-92`) — an `atomic` block with `transaction.set_rollback(True)` — to avoid slug collisions with `test_submenu.py`'s `tree` fixture (both use `transport`).
- `CategoryLookupResolver` caches 300s in LocMemCache (`lookup_resolution.py:155`, key `lookup:resolved_purposes:<id>`). Call `cache.clear()` in an `autouse` fixture (mirror `test_auth_nav.py:36-40`) before/after G5/G6 tests to prevent stale resolver results across classes/xdist workers.

### 5.4 Fixtures & expected values
- Use `create_test_ad(..., status=AdStatus.PUBLISHED)` (conftest.py:105-211) for ad-detail/listing tests so the queryset filter at listings.py:62 (`status=AdStatus.PUBLISHED`) matches.
- Canonical fixtures: `seller` (900000001), `user` (900000002), `category`, `city` (conftest.py). For G4, expected Telegram URL: `https://t.me/{settings.BOT_USERNAME}?start=contact_{ad.id}`.
- For city entry (G6), use the catalog `City` fixture or a directly-created `City` (as in `test_breadcrumbs_render.py:85-90`).

### 5.5 Environment
- All tests run in Docker (DB on port 5433); bare `uv run pytest` fails (DB unreachable on localhost:5432). Run a single file:
  `docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm -e PYTEST_OPTS="apps/ads/tests/test_block1_….py" test`
  Use `make test-recreate` after any migration change (`--no-reuse-db`). Never pass `--override-ini=addopts=` (strips `--import-mode=importlib`).
