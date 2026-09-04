# Documentation Discrepancy Report — Site Name Centralization & Filter Regression

**Date:** 2026-09-04
**Context:** Cross-check of two source documents against the committed implementation
(`c5c360f feat(site-name)` and `7db91ae fix(catalog): filter regression`) and the
existing `docs/`. This report is kept separate from the documentation edits (Step 5)
per the documentation-update workflow.

Source docs reviewed:
- `.ai/plans/19_site-name_centralization_plan.md` (T1–T11)
- `.ai/problems/05_filter-regression_spec.md` (CR-1–CR-10, T1–T8)

---

## Summary

| # | Discrepancy | Specified/Planned behavior | Current code | Documentation impact |
|---|---|---|---|---|
| D1 | SiteConfig was recorded "not implemented" (2026-09-02) | `.ai/plans/19_site-name_centralization_plan.md` (T1–T11) | Implemented at `c5c360f` — `SiteConfig` model, `get_site_name()`/`get_site_name_async()`, `site_config` context processor, `post_save` invalidation, both migrations, 22 `{{ site_name }}` template replacements, bot greeting injection, i18n msgids | D1 resolved → **must document** the now-implemented feature |
| D2 | T6 recommended Approach A (structural) | `.ai/problems/05_filter-regression_spec.md` §4 T6 L152-156 | Implementation used **Approach B** (`htmx:afterSwap` JS listener) at `components/language_switcher.html` L127-142 | Permitted deviation (spec §4 L156: "If Approach A is too risky, use Approach B"; §10 Open Q1 defers decision). Docs must reflect B as the **deployed** choice, not "recommended future" |
| D3 | CR-5 assumes city is always a path param | `.ai/problems/05_filter-regression_spec.md` CR-5 L91 | Header navigation sets city as `?city=<slug>` query param (PO-Q2=A, T5); clear-all resets all query params incl. `?city=` (`ad_list.html` L82-87) | `filter-ui.md` SSOT (L437-438) already documents query-param city being dropped by clear-all → **consistent with code**; CR-5 wording is now partial but no doc change needed |
| D4 | filter-ui.md uses wrong param/var names | `docs/01-spec/filter-ui.md` L76/L78/L232/L234/L235/L359/L360/L362/L363; `docs/01-spec/spec-index.md` L166 | Implementation uses `min_price`/`max_price` (`filter_form.html` L51/61, `listings.py` L329/331/456-457, all `ad_list.html` links) and `active_price_min`/`active_price_max` (`listings.py` L348-349/458-459, `ad_list.html` L33/35/37) | Doc accuracy fix: normalize `price_min`→`min_price`, `price_max`→`max_price`, `selected_price_min/max`→`active_price_min/max` |
| D5 | No runtime test for the deployed client-side fixes | `.ai/problems/05_filter-regression_spec.md` §2.5 (open questions) / §5 | `htmx:afterSwap` listener (`language_switcher.html` L127-142) and `applyCityFilter()` JS (`header_catalog.html` L229-248) exist but have **no execution/JS test** | Test gap (not a doc change); static-template tests were rewritten stronger but cannot exercise runtime JS |

---

## Detailed Records

### D1 — SiteConfig: planned → implemented (resolves prior finding)

A prior report (`doc-update-price-model-and-htmx-version.md`, 2026-09-02) recorded D1 as
"SiteConfig planned but not implemented: no `apps/core/models.py` SiteConfig, etc." That is
now **false**. Git history confirms:

```
c5c360f feat(site-name): centralize hardcoded Mko Bazuna behind admin singleton
```

Verified implementation (Researcher A):
- `apps/core/models.py` — `SiteConfig` singleton (`name = CharField(max_length=255, default="Bazuna")`, `Meta.db_table = "site_config"`, `get_singleton()` via `get_or_create(pk=1)`).
- `apps/core/utils/cache.py` — `SITE_CONFIG_CACHE_KEY = "site_config:v1"`, TTL 3600, `get/set/invalidate` helpers.
- `apps/core/services/site_config.py` — `get_site_name()` (cache + DB + `"Bazuna"` fallback), `get_site_name_async()` (`sync_to_async`).
- `apps/core/context_processors.py` — `site_config(request) -> {"site_name": get_site_name()}`; registered in `config/settings/base.py` TEMPLATES context_processors.
- `apps/core/signals.py` + `apps.py` `ready()` — `post_save` receiver invalidates cache.
- Migrations `0001_initial` + `0002_seed_default` (`RunPython` seed).
- Both web and bot load `config.settings.prod` → shared Redis cache; tests override to `LocMemCache`.
- Bot: `get_site_name_async` injected into `/start` (`handlers/login.py:49`) and `/post` (`handlers/ad_create.py:124`).
- Templates: 22 `{{ site_name }}` replacements across 14 files; zero hardcoded user-facing `"Mko Bazuna"` remaining.

**Action:** Remove the "not implemented" status of D1. The SiteConfig feature is the central
subject of the accompanying documentation update (Step 5); see "Doc updates applied" below.

### D2 — T6 approach: recommended A, deployed B

**Planned/specified:** Spec §4 T6 "Recommended approach: A — move `header_catalog.html`
(or just the switcher) inside `#ad-list` so it is re-rendered on every swap." §10 Open Q1
defers the A-vs-B choice to implementation ("Deferred to implementation").

**Implemented:** Approach B — a client-side `htmx:afterSwap` listener in
`components/language_switcher.html` L127-142 that recomputes every
`[data-lang-switcher-link]` `href` from `window.location.search` and drops `page`. The
header was **not** moved into `#ad-list` (`list.html:23` include still outside the
`#ad-list` target at `list.html:36`).

**Classification:** Permitted deviation. Spec §4 L156 explicitly allows B as a fallback
("If Approach A is too risky, use Approach B"), and §10 defers the decision. The two
`99-agent/htmx-*` audit docs present B as a *recommendation / open decision* and now
contradict the committed code (which has B deployed). This changes how the docs must be
written: the audit docs need a resolution status, not a rewrite of the spec.

### D3 — CR-5 vs city-as-query-param + clear-all

**Specified:** CR-5 L91 — "Category and city are path parameters and are naturally
preserved by clear-all (not in the query string)."

**Implemented:** T5 (PO-Q2=A) changes header navigation to set city via
`?city=<slug>` query param (preserving the category path). `ad_list.html` L82-87 clear-all
emits `?page=1{% if query %}&q=…{% endif %}{% if LANGUAGE_CODE %}&lang=…{% endif %}` —
it resets **all** query params, including `?city=`. So when city is a query param it IS
dropped by clear-all; when city is a path param (`/city/<slug>/`) it is preserved.

**Classification:** Internal spec tension, not a code error. The `filter-ui.md` SSOT
(L437-438) already states this exactly ("When city is applied as a query parameter
(`?city=<slug>`) via the header dropdown, it is also dropped by clear-all"), so the
documentation is **consistent with the code**. No doc change required beyond what already
exists; CR-5's path-param assumption is simply partial.

### D4 — filter-ui.md / spec-index.md param & variable names contradict code

**Specified (doc):** `filter-ui.md` L76/L78/L359/L362 document price input fields as
`name="price_min"` / `name="price_max"`; L232-235 the price chip as
`selected_price_min`/`selected_price_max` with `url_replace request 'price_min' '' 'price_max' ''`;
`spec-index.md` L166 lists query params `price_min`/`price_max`.

**Implemented (code):** `filter_form.html` L51/61 `name="min_price"`/`name="max_price"`;
`listings.py` L329/331/456-457 `min_price`/`max_price`; `ad_list.html` all chip/pagination/clear-all
links use `min_price`/`max_price`; context vars `active_price_min`/`active_price_max`
(`listings.py` L348-349/458-459; `ad_list.html` L33/35/37). Additionally all chips + clear-all +
pagination are `hx-get`+`hx-push-url`+`hx-target="#ad-list"` links, not the plain
`url_replace` `<a>` links shown in the doc's chip example.

**Classification:** Doc-accuracy discrepancy (the spec doc states names the code does not
use). Resolved in Step 5 by normalizing the param/variable names to match the implementation.
(The hx-get-vs-`url_replace` chip-link pattern is a broader outdated illustration; per
doc-maintenance rules, the bug-fix behavior changes themselves are not newly documented —
only the factual parameter/variable-name contradictions are corrected.)

### D5 — Test gaps for the deployed client-side fixes

**Specified (gap):** Spec §2.5 notes no test covers (a) language-switch staleness after
HTMX navigation and (b) city selection preserving category.

**Implemented:** The runtime fixes exist in the working tree (`language_switcher.html`
L127-142 `htmx:afterSwap` listener; `header_catalog.html` `applyCityFilter()` L229-248),
and commit `7db91ae` shipped them. However no integration/JS test exercises either
client-side behavior:
- `test_catalog_filters.py::test_city_category_coexistence` (L933) covers the **view-level**
  `?city=` filter only, not the `applyCityFilter` navigation.
- `test_lang_param_in_all_htmx_urls` / `test_lang_param_preserved_in_rendered_output` verify
  `LANGUAGE_CODE` appears in the server-rendered partial, not that the after-swap rewrite
  refreshes switcher `href`s.

**Classification:** Test-coverage gap (not a documentation concern). Recorded here for
visibility; the static `hx-get` count (now 10) and per-link `LANGUAGE_CODE` assertions
were already strengthened in the test suite.

---

## Doc updates applied (Step 5)

These discrepancy findings drive the following `docs/` updates, which are applied
separately from this report:

| Finding | Doc file(s) | Change |
|---|---|---|
| D1 | `docs/02-database/db-schema.md`; `docs/01-spec/architecture-structure.md`; `docs/01-spec/ui-patterns.md`; `docs/01-spec/spec-index.md`; `docs/99-agent/architecture.md` | Document the now-implemented `SiteConfig` singleton, `site_config` context processor, `{{ site_name }}` brand link, shared-cache architecture, and Phase-2 index entry |
| D2 | `docs/99-agent/htmx-swap-language-switcher-audit.md`; `docs/99-agent/htmx-language-switcher-fix-evaluation.md` | Add resolution status: Approach B deployed (not an open recommendation) |
| D3 | (none) | `filter-ui.md` already consistent (L437-438); no change |
| D4 | `docs/01-spec/filter-ui.md`; `docs/01-spec/spec-index.md` | Normalize `price_min`→`min_price`, `price_max`→`max_price`, `selected_price_min/max`→`active_price_min/max` |
| D5 | (none) | Test gap, not a doc change |

---

## Out of scope

The prior `doc-update-price-model-and-htmx-version.md` report's D2–D8 (zero-based pricing
model, `django.contrib.sites`/`SITE_URL` absence, HTMX 1.9→2.0 version) are separate
features and are not touched here.
