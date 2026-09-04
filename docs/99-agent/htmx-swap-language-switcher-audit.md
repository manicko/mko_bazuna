# Audit Report — HTMX Swap Architecture & Language Switcher Staleness

**Date:** 2026-09-03
**Scope:** Language switcher rendering, HTMX swap targets, and `query_replace` query-string construction.
**Files reviewed:**
- `src/backend/templates/ads/list.html`
- `src/backend/templates/components/header_catalog.html`
- `src/backend/templates/components/language_switcher.html`
- `src/backend/templates/components/header.html`
- `src/backend/apps/core/templatetags/dict_tags.py`
- `src/backend/apps/core/middleware/language.py`
- `src/backend/apps/core/context_processors.py`
- `src/backend/apps/core/enums.py` (`LanguageLocale`)
- `src/backend/templates/ads/partials/ad_list.html`
- `src/backend/templates/ads/partials/filter_form.html`
- `src/backend/apps/ads/views/listings.py`
- `src/backend/apps/search/views/search.py`
- `src/backend/apps/cabinet/views/favorites.py`
- `src/theme/static/theme/js/filter-dropdowns.js`
- Tests: `apps/ads/tests/test_catalog_filters.py`, `apps/core/tests/test_templates.py`, `apps/core/tests/test_language_middleware.py`, `apps/search/tests/test_autocomplete_template.py`

---

## 1. HTMX Swap Architecture

### 1.1 The single swap target: `#ad-list`

`list.html` L36 defines exactly one HTMX swap target inside `<main>`:

```html
{% include "components/header_catalog.html" %}      <!-- L23 — OUTSIDE #ad-list -->
<main class="container mx-auto px-4 py-6">
    ...
    <div id="ad-list">{% include "ads/partials/ad_list.html" %}</div>   <!-- L36 -->
</main>
```

- The **entire catalog header** (`header_catalog.html`) is included at **L23**, before `<main>`.
- The **`#ad-list` swap target** is at **L36**, nested inside `<main>`.
- **Verdict: the header is OUTSIDE (above) the swap target.** It is never part of an HTMX fragment replacement.

`filter-dropdowns.js` (L4-L11) confirms this boundary explicitly: the filter form partial is destroyed and recreated on every `innerHTML` swap of `#ad-list`, so it uses document-level event delegation to survive. The header is never mentioned as a swap participant.

### 1.2 HTMX request/response cycle

When an HTMX interaction fires (filter submit, chip removal, pagination, clear-all), the server returns **only the `ad_list.html` partial** — never the full page. This is hard-coded in both catalog views:

| View file | HTMX branch | Response |
|---|---|---|
| `ads/views/listings.py` L471-L472 | `if request.headers.get("HX-Request"):` | `render(request, "ads/partials/ad_list.html", context)` |
| `apps/search/views/search.py` L303-L304 | `if request.headers.get("HX-Request"):` | `render(request, "ads/partials/ad_list.html", context)` |
| `apps/cabinet/views/favorites.py` L45-L46 | `if request.headers.get("HX-Request"):` | `render(request, "ads/partials/ad_list.html", context)` |

Because only the partial is returned, HTMX replaces `#ad-list` innerHTML and the header (with its language switcher) is **never re-rendered**.

### 1.3 HTMX attributes on catalog interactions

All HTMX-driven catalog interactions share the same swap contract:

| Interaction | Element | `hx-get` | `hx-push-url` | `hx-target` | `hx-swap` |
|---|---|---|---|---|---|
| Filter form submit | `filter_form.html` L5-L8 | `{{ request.path }}` | `true` | `#ad-list` | `innerHTML` |
| Sort dropdown change | `filter_form.html` L117 | (inherited via form) | `true` | `#ad-list` | `innerHTML` |
| Purpose chip removal | `ad_list.html` L47-L48 | `?page=1&...` | `true` | `#ad-list` | `innerHTML` |
| Condition chip removal | `ad_list.html` L60 | `?page=1&...` | `true` | `#ad-list` | `innerHTML` |
| Feature chip removal | `ad_list.html` L71 | `?page=1&...` | `true` | `#ad-list` | `innerHTML` |
| Clear all filters | `ad_list.html` L79 | `?page=1` | `true` | `#ad-list` | `innerHTML` |
| Pagination (laquo laquo, page N,raquo) | `ad_list.html` L146, L152, L163, L172, L178 | `?page=N&...` | `true` | `#ad-list` | `innerHTML` |

**Test guard:** `test_all_htmx_links_have_push_url` (`test_catalog_filters.py` L647) asserts exactly **9** `hx-get=` attributes each paired with `hx-push-url="true"`. `test_lang_param_in_all_htmx_urls` (L656) asserts `LANGUAGE_CODE` appears in all 9 links x 2 attributes (href + hx-get) = >=18 occurrences. `test_clear_all_filters_has_push_url` (L665) asserts the clear-all reset URL drops `q` and `sort`.

**Key observation:** every swap pushes a new URL to the address bar (`hx-push-url="true"`) but swaps only `#ad-list`. The URL bar and the `#ad-list` content stay in sync; **the header does not.**

---

## 2. `query_replace` — Analysis

### 2.1 Source (`dict_tags.py` L47-L69)

```python
@register.simple_tag
def query_replace(request: Any, **kwargs: Any) -> str:
    query = request.GET.copy()
    for key, value in kwargs.items():
        query[key] = value
    return query.urlencode()
```

### 2.2 Behavior verdict

| Property | Verdict | Evidence |
|---|---|---|
| Snapshots `request.GET` at render time | **Yes** | `query = request.GET.copy()` |
| Preserves multi-value params (e.g. `features=a&features=b`) | **Yes** | `QueryDict.copy()` preserves lists; `urlencode()` serializes them. No bug. |
| Handles override semantics | **Yes** | `query[key] = value` replaces all values for a key (standard `QueryDict.__setitem__`). Correct for "set/replace" intent. |
| Preserves `page` param | **Yes** | `page` is just another GET key; copied and urlencoded. Confirmed by `test_preserves_multiple_params` (passes `q=phone&page=2&sort=price`, asserts `page=2` is in output). |
| Removes a param when desired | **No (by design)** | This is a "copy + override" utility; no remove/append API. Not a bug — the caller (`ad_list.html` chip/pagination links) handles removal via explicit per-link construction, not via `query_replace`. |

**Conclusion: `query_replace` contains no logic bug.** It faithfully serializes whatever `request.GET` snapshot it receives. The template tests (`test_templates.py` L104-L130) confirm correct preserve/override/empty behavior.

---

## 3. The Staleness Root Cause

### 3.1 Where `query_replace` is called

`language_switcher.html` L35 builds each language link by snapshotting the *current* URL's query string and overriding only `lang`:

```html
<a href="?{% query_replace request lang=language.code %}" ...>
```

This produces links like `?q=phone&features=brand&sort=price_asc&lang=en` — capturing the full query string from the **render time** of the header.

### 3.2 The staleness chain (root cause)

The staleness is **not** a defect inside `query_replace`. It is an **architectural coupling** between where `query_replace` is rendered and what the HTMX swap target covers:

1. **Full page load** `GET /?q=phone&features=brand&sort=price_asc&lang=ru`:
   - Middleware (`language.py`) reads `?lang=ru`, activates Russian.
   - `listings` view renders `list.html`.
   - **Header rendered once** (L23): `language_switcher.html` runs `query_replace request lang=en` against `request.GET` = `q=phone&features=brand&sort=price_asc&lang=ru` -> link = `?q=phone&features=brand&sort=price_asc&lang=en`. **This output is now frozen in the DOM.**

2. **HTMX interaction** (user clicks the x on the `brand` feature chip):
   - Chip link fires `hx-get="?page=1&q=phone&sort=price_asc&lang=ru"` (features dropped), `hx-push-url="true"`, `hx-target="#ad-list"`.
   - Browser URL bar **updates** to `/?page=1&q=phone&sort=price_asc&lang=ru`.
   - Server returns **only** `ad_list.html` partial; `#ad-list` innerHTML is replaced.
   - **The header is never touched.** The language switcher still carries `?q=phone&features=brand&sort=price_asc&lang=en` — `features=brand` is now **stale** (removed from the URL, removed from current results).

3. **User switches language** by clicking the (stale) English link:
   - Browser navigates to `?q=phone&features=brand&sort=price_asc&lang=en`.
   - The view re-applies `features=brand` as an active filter -> **the filter the user just removed is silently re-introduced.** The user lands on results that do *not* match what they were viewing.

### 3.3 Why `query_replace` is not the bug

`query_replace` correctly serializes `request.GET` at the moment the header template is rendered. On the full page load in step 1, its output is **correct for that moment**. The function has no temporal awareness: it cannot know that the header will never be re-rendered after the HTMX swap. The defect is that the **rendering context for the language switcher is frozen** because the header sits outside the swap target and the HTMX response omits the header.

### 3.4 The one operation that IS correct: language switch itself

Language switching via the switcher is a **plain `<a href>` navigation** (full browser GET, not an HTMX swap) — see `language_switcher.html` L98-L109: the `data-lang-switcher-link` click handler sets the cookie and allows default navigation. Because it is a full reload, the server re-renders the entire `list.html` (including the header) with the new `request.GET`, and `query_replace` produces fresh links. **Language switching itself is never stale; only the non-language HTMX interactions leave the switcher frozen.**

### 3.5 Secondary latent issue: `page` carried into language switch

`query_replace` preserves `page` by design (test `test_preserves_multiple_params` asserts this; `dict_tags.py` L67-L69 copies it). If the user is on page N and switches language, the link carries `&page=N&lang=X`. Page N of the new-language view may be empty or 404 (different total count/ordering). Language switch arguably should reset `page=1`. This is a correctness/UX concern distinct from the HTMX staleness but worth a forward-looking recommendation.

---

## 4. Middleware — `language.py`

### 4.1 Resolution priority

`LanguagePreMiddleware.process_request` (`language.py` L57-L74) resolves language in priority order:

1. **`?lang=X` query parameter** — `request.GET.get("lang")` (L59). Wins outright.
2. **`lang_pref` cookie** — `request.COOKIES.get(LANGUAGE_COOKIE_NAME)` (L64).
3. **`Accept-Language` header** — first tag, if supported (`_parse_accept_language`, L131-L143).
4. **Default** — `ru` (`LanguageLocale.RUSSIAN.value`, L74).

### 4.2 Side effects

- `?lang=` is validated against `LanguageLocale.values()` = `{"ru", "bs", "en"}` (L148). Invalid values fall back to `ru` with a warning log (L103).
- When `?lang=` is present, the cookie intent is stored on `request._lang_cookie_value` and persisted in `process_response` (L85-L91).
- For authenticated users, `?lang=` is also written to `request.session["django_language"]` (L118).

### 4.3 Relevance to staleness

- Because `?lang=` is **priority #1**, a stale `lang` param in a language-switcher link is **always honored** regardless of cookie state. So the staleness does not corrupt the *target* language — it corrupts the *other* params (q, features, sort, page) carried alongside it.
- `Django LocaleMiddleware` is intentionally removed (docstring L9-L14); `LanguagePreMiddleware` is the single authority. `request.LANGUAGE_CODE` is kept in sync with the thread-local active language (L129).

### 4.4 Context processor bridge

`language()` context processor (`context_processors.py` L22-L24) exposes `request.LANGUAGE_CODE` as the template variable `LANGUAGE_CODE`. This is the value the inline JS in `header_catalog.html` reads via `catalog_js_labels`, and it is what the middleware set. Consistent.

---

## 5. Header Inclusion Tree (T6 approach risk)

### 5.1 `header_catalog.html` — the catalog/search header

Included in **exactly 2** production templates:

| Template | Line | Has `#ad-list` swap target? | HTMX interactions? |
|---|---|---|---|
| `ads/list.html` | L23 | Yes (L36) | Yes — filter/chip/pagination/sort |
| `ads/detail.html` | L28 | No | No |

This asymmetry is the crux of the T6 risk: `header_catalog.html` is a **shared component between a swappable page (list) and a non-swappable page (detail)**. Any fix that moves the header (or the language switcher) *inside* the swap target can only sensibly apply to `list.html`.

### 5.2 `header.html` — the auth/dashboard header

Included in **13** templates (all also embed `language_switcher.html` transitively at `header.html` L8):

`ads/dashboard.html`, `ads/edit.html`, `cabinet/settings.html`, `cabinet/search_history.html`, `cabinet/favorites.html`, `cabinet/saved_search_edit.html`, `cabinet/saved_searches.html`, `cabinet/hub.html`, `users/login_issue.html`, `privacy.html`, `analytics/seller_dashboard.html`, `analytics/moderation_dashboard.html`.

### 5.3 Direct `language_switcher.html` includes

| Template | Line |
|---|---|
| `components/header_catalog.html` | L37 |
| `components/header.html` | L8 |
| `admin/moderation/queue.html` | L6 |
| `admin/moderation/review.html` | L25 |

**Total reach of the language switcher: ~17 templates** across catalog, detail, dashboard, cabinet, auth, moderation, and privacy surfaces.

### 5.4 Favorites page uses a different header + swap target

`cabinet/favorites.html` L28 uses `<div id="favorites-list">` (not `#ad-list`) and includes `header.html` (the auth header, L24) — NOT `header_catalog.html`. The favorites view swaps the `ad_list.html` partial into `#favorites-list` (L28-L30 of the template; L45-L46 of the view). The same staleness applies to its language switcher, but via a different swap target and header component.

### 5.5 Base-template situation

There is **no `base.html`** — only `admin/moderation/queue.html` uses `{% extends "admin/base_site.html" %}`. Every public/cab in/dashboard template inlines its own `<head>`/`<body>` and includes the header component. Confirmed by `template_architecture_research.md` (L17): *"No base template exists."*

---

## 6. Staleness Matrix — which interactions leave the switcher stale

| Interaction | Full reload? | Swap target | Header re-rendered? | Switcher fresh? |
|---|---|---|---|---|
| Initial page load | Yes | n/a | Yes | Yes |
| Language switch (click link) | Yes (plain `<a>`) | n/a | Yes | Yes |
| Filter apply (`Apply filters`) | No | `#ad-list` | No | Stale |
| Sort change | No | `#ad-list` | No | Stale |
| Chip removal (purpose/condition/feature) | No | `#ad-list` | No | Stale |
| Pagination (laquo, page N, raquo) | No | `#ad-list` | No | Stale |
| Clear all filters | No | `#ad-list` | No | Stale |

**Every HTMX-driven catalog interaction leaves the language switcher stale.** Only language switching and initial load refresh it.

---

## 7. Findings & Recommendations

### Finding 1 (MANDATORY-class, correctness/UX) — Staleness via frozen header snapshot

**Severity:** HIGH — user-facing: removing a filter then switching language silently re-applies the removed filter.

**Root cause:** `query_replace` (correct in isolation) renders inside `language_switcher.html`, which is embedded in `header_catalog.html` (L37) -> included at `list.html` L23, which is **outside** the `#ad-list` swap target (L36). HTMX responses return only `ad_list.html` (`listings.py` L472, `search.py` L304), so the header — and therefore the `query_replace` links — are never refreshed after a swap, despite `hx-push-url="true"` updating the address bar.

**Evidence:**
- `list.html`: L23 (header include) vs L36 (`#ad-list` div). Header precedes `<main>`; swap target is inside `<main>`.
- `listings.py` L471-L472: `if request.headers.get("HX-Request"): return render(request, "ads/partials/ad_list.html", context)`.
- `language_switcher.html` L35: `<a href="?{% query_replace request lang=language.code %}">`.
- `dict_tags.py` L67: `query = request.GET.copy()` — snapshot at render time.
- `filter-dropdowns.js` L4-L11: only `#ad-list` is swapped; header never re-rendered.
- `test_all_htmx_links_have_push_url` (L647): 9 links x `hx-push-url` = URL bar updates but header does not.

**Recommendation (Approach B — lower risk):** Add a small client-side hook on `htmx:afterSwap` (or `htmx:pushUrl`) that recomputes the language switcher `href`s from `window.location.search`, replacing only the `lang` key and dropping `page`. This localizes the fix to the ~17 templates that embed the switcher, adds no DB queries, preserves open dropdown/accordion state, and degrades gracefully to the server snapshot when JS is off.

- *what:* ~15 lines of JS in `language_switcher.html` (or a shared `theme/js/language_switcher.js`) that, after each HTMX swap, reads `window.location.search`, deletes `page`, and rewrites each `data-lang-switcher-link` href to `?<current>&lang=<code>`.
- *why:* keeps language-switch links in lock-step with the address bar without re-rendering the heavy header on every filter/pagination interaction; avoids re-running the 400-line inline script in `header_catalog.html`.
- *effort:* trivial.
- *priority:* recommended.

**Alternative (Approach A — higher risk, NOT recommended):** Move `header_catalog.html` (or just the switcher) inside `#ad-list` so it is re-rendered on every swap.

- *what:* relocate the `{% include "components/header_catalog.html" %}` from `list.html` L23 to inside the `#ad-list` div at L36.
- *why it's risky (T6 approach A vs B):*:
  1. **Shared component / detail asymmetry (HIGH):** `header_catalog.html` is included in both `list.html` (has `#ad-list`, HTMX active) and `detail.html` L28 (no `#ad-list`, no HTMX swaps). Embedding the header inside a swap target is meaningless on `detail.html` and would require a second swap target to exist there — breaking symmetry and forcing divergent templates.
  2. **Per-swap cost (MEDIUM):** re-rendering the header re-fires the MPTT `root_categories` query (`context_processors.header_context` L87-L89), the `cities` query (L91), and the favorites-count query (L80-L83) on every filter/chip/pagination change.
  3. **JS re-execution & state loss (HIGH):** the 400-line inline script in `header_catalog.html` (L216-L614) is wrapped in an IIFE and would re-run on every swap, re-attaching listeners and **wiping open dropdown/accordion/mobile-panel state** (server renders them closed). `filter-dropdowns.js` already documented this exact re-render fragility for the filter form; the header would inherit the same class of bug.
  4. **Favorites page divergence:** `cabinet/favorites.html` swaps into `#favorites-list` (not `#ad-list`) using `header.html` (not `header_catalog.html`). Approach A would need a parallel, inconsistent change there.

### Finding 2 (LOW, forward-looking) — `page` param leaked into language-switch links

`query_replace` preserves `page` by design (test `test_preserves_multiple_params` asserts this; `dict_tags.py` L67-L69 copies it). When the user is on page N and switches language, the link carries `&page=N&lang=X`. The destination view may have fewer pages -> empty/404 page.

- *what:* have the language-switcher link builder strip `page` (always reset to the first page of the new language's result set), either server-side in a dedicated template tag or client-side in the JS hook from Finding 1.
- *why:* pagination is result-set-dependent; carrying a page index across a language/context switch is semantically wrong.
- *effort:* trivial (one line in the JS hook, or add `page` handling in `query_replace`).
- *priority:* recommended.

### Finding 3 (INFO, no change recommended) — `query_replace` multi-value & override semantics are correct

The function uses `request.GET.copy()` (preserves `QueryDict` multi-values) and `query[key] = value` (replaces all values for a key). This is the correct contract for a "preserve everything, override these" utility. The existing tests (`test_preserves_existing_params_when_overriding_one`, `test_preserves_multiple_params`, `test_adds_new_param_when_none_exists`, `test_empty_overrides_preserves_all`) cover the main paths. No code change warranted.

### Finding 4 (INFO) — Staleness also affects the `header.html` (auth) consumers

The auth header (`components/header.html` L8) embeds `language_switcher.html` across 12 templates (dashboards, cabinet, edit, auth, privacy). None of those pages currently perform HTMX swaps of their header-bearing region, so they are **not currently stale** — but the shared switcher means any future HTMX addition to any of these pages (e.g. a favorites badge swap, a saved-search list swap) would inherit the same staleness. Documenting the JS hook in Finding 1 as the universal safeguard for all 17 switcher sites hardens this surface proactively.

---

## 8. Appendix — Key line references

| Artifact | File | Lines |
|---|---|---|
| Header include (catalog) | `ads/list.html` | L23 |
| `#ad-list` swap target | `ads/list.html` | L36 |
| Header include (detail) | `ads/detail.html` | L28 |
| `#favorites-list` swap target | `cabinet/favorites.html` | L28-L30 |
| Header include location (header_catalog) | `components/header_catalog.html` | L37 (embeds switcher) |
| Switcher link with `query_replace` | `components/language_switcher.html` | L35 |
| Switcher JS + cookie | `components/language_switcher.html` | L43-L126 |
| `query_replace` implementation | `apps/core/templatetags/dict_tags.py` | L46-L69 |
| Middleware `?lang=` priority | `apps/core/middleware/language.py` | L59-L66 |
| Middleware cookie persistence | `apps/core/middleware/language.py` | L85-L91 |
| `language()` context processor | `apps/core/context_processors.py` | L22-L24 |
| `header_context` processor (categories/cities) | `apps/core/context_processors.py` | L27-L102 |
| `LanguageLocale` enum | `apps/core/enums.py` | L188-L238 |
| View HTMX branch (listings) | `apps/ads/views/listings.py` | L471-L472 |
| View HTMX branch (search) | `apps/search/views/search.py` | L303-L304 |
| View HTMX branch (favorites) | `apps/cabinet/views/favorites.py` | L45-L46 |
| Filter form HTMX attrs | `ads/partials/filter_form.html` | L4-L9, L117 |
| `#ad-list` swap attrs (all 9) | `ads/partials/ad_list.html` | L47, L60, L71, L79-L82, L146-L148, L152-L154, L163-L165, L172-L174, L178-L180 |
| Per-swap JS delegation | `theme/js/filter-dropdowns.js` | L4-L11, L29-L57 |
| Inline header script (JS re-exec risk) | `components/header_catalog.html` | L216-L614 |
| Test: push-url on all links | `test_catalog_filters.py` | L647 (`TestFilterUrlReset`) |
| Test: lang param in all URLs | `test_catalog_filters.py` | L656 |
| Test: clear-all resets q/sort | `test_catalog_filters.py` | L665 |
| Test: query_replace behavior | `apps/core/tests/test_templates.py` | L104-L130 |
| Test: header included in list+detail | `apps/search/tests/test_autocomplete_template.py` | L160-L161 |
| Test: locale middleware | `apps/core/tests/test_language_middleware.py` | L78-L112 |

---

## Resolution Status (post-implementation)

**Resolved (HIGH severity → closed):** The staleness described in Finding 1 is fixed by
deploying **Approach B** in `components/language_switcher.html` (L127-142): an
`htmx:afterSwap` listener that rewrites every `[data-lang-switcher-link]` `href` from
`window.location.search` and drops `page`. The header is intentionally **not** re-rendered on
swap (Approach A was rejected per §5; the switcher stays outside `#ad-list` at `list.html:23`).
The `query_replace` tag (`dict_tags.py` L46-69) is unchanged and still correct; the fix is
localized entirely to the client-side listener. This audit is retained as the pre-implementation
problem record.
