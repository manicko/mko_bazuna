---
id: url-state-preservation
domain: spec
tags:
  - url-state
  - navigation
  - htmx
  - category
  - city
  - language
  - query-string
  - i18n
related:
  - spec-index
  - search-patterns
  - filter-ui
  - ui-patterns
  - architecture-structure
  - technical-specification
---

## Purpose

Document the URL state preservation architecture introduced by Spec 17: how the
project, city, category, language, sort, and filter state are carried across
navigation, HTMX partial updates, and full-page transitions without silently
dropping query parameters. This doc is the single source of truth for the URL
contract; other docs link here rather than restating the rules.

## Main Concepts

### URL state model: path-encoded vs. query-encoded

The site uses a hybrid URL model where **primary browsing context is in the URL
path** and **secondary, optional refinements are in the query string**:

| Context element | Encoding | Format | Preserved by |
|---|---|---|---|
| Site language | Query param | `?lang=<code>` (`ru`, `bs`, `en`) | All navigations, clear operations |
| Explicit city | Query param | `?city=<slug>` | Category, breadcrumb, and pagination links via `query_replace` |
| Effective city (preference) | Cookie / user pref | `preferred_city` cookie or `User.preferred_city` FK | Middleware re-applies as default after any URL drop |
| Category subtree | URL path | `/category/<slug>/` | Category navigation links |
| Search keyword | Query param | `?q=<text>` | Header search form (carries only `q`) |
| Sort | Query param | `?sort=<value>` | Pagination links; cleared on cross-engine transitions |
| Filters (purpose, condition, price, features) | Query params | `?listing_purpose=`, `?min_price=`, `?features=` (repeated) | Filter application, pagination, individual chip removal |
| Page | Query param | `?page=<n>` | All pagination links |

The header search bar submits a **new context** (`?q=` only) and intentionally
does not carry the active category, city, or filters. The *preferred-city*
middleware re-applies the buyer's default city after such a transition. See
[search-journeys.md](../04-user-stories/search-journeys.md) for the full
journey matrix.

### Primary state carriers

1. **`query_replace` template tag** (`apps/core/templatetags/dict_tags.py`)
   is the canonical mechanism for adding, replacing, or removing individual
   query parameters while preserving all others. All category, breadcrumb, and
   city navigation links are built through this tag so that switching category
   or city never silently drops `sort`, `listing_purpose`, `features`, or
   `min_price`/`max_price`.

2. **HTMX `hx-push-url="true"`** on partial updates (filter application, chip
   removal, pagination) — the browser URL is updated so Back/Forward and
   bookmarks restore exact state.

3. **`request.current_city`** (`CityResolutionMiddleware` — `apps/core/middleware/city_resolution.py`)
   resolves the effective city from the URL path (`/city/<slug>/`) or the
   `?city=<slug>` query parameter, or `None` for country-wide. This takes
   priority over the cookie/DB preference (`PreferredCityMiddleware`).

4. **`request.preferred_city`** (`PreferredCityMiddleware` —
   `apps/core/middleware/preferred_city.py`) resolves a default city from the
   authenticated user's `User.preferred_city` FK or a `preferred_city`
   cookie. This fills in when the URL carries no explicit city.

### HTMX safety nets

Two client-side safety nets ensure URL state is never silently dropped during
partial swaps:

| Hook | Purpose | File |
|---|---|---|
| `htmx:configRequest` (global) | Intercepts every outgoing HTMX request and re-applies the current URL query state (lang, city, sort, filters) so partial updates never strip parameters | `static/theme/js/url_state.js` (or inline in base) |
| `htmx:afterSwap` (category/city) | After a category submenu or city-panel partial render, re-writes the category/city links in the swapped DOM to carry the full `query_replace`-built URL | `static/theme/js/url_state.js` |

These hooks are the fallback when server-side URL construction is insufficient
(e.g., dynamically rendered submenu content).

### Language behavior

- `lang` is always a **query parameter** (`?lang=<code>`) — never a URL path
  segment.
- Language switching **drops the `page` parameter** (resets to page 1 of the
  new-language results), but preserves `lang`, `city`, `category`, `sort`, and
  filter parameters.
- The `LanguagePreMiddleware` reads `lang_pref` cookie / `?lang=X` and sets
  `request.LANGUAGE_CODE`. Display language survives even if a filter change
  momentarily drops `?lang=` from the URL (re-applied from cookie on load).

## Catalog navigation URL contract

### Category navigation links

All category links in the catalog header dropdown, breadcrumb, and ad-list
partials are built with `query_replace` so switching categories preserves the
full active filter set:

```django
{# Example: category link preserves all active query params #}
<a href="{% url 'ads:listings_category' cat.slug %}{% query_replace request.GET 'sort' current_sort 'listing_purpose' current_purpose 'features' current_features %}">
```

- Category is encoded in the **URL path** (`/category/<slug>/`) — it is always
  preserved because it is not a query parameter.
- `page` is reset to 1 on category navigation.
- All active filter query parameters (`sort`, `listing_purpose`, `features`,
  `min_price`, `max_price`, `listing_condition`) are carried through.

### Breadcrumb links

Breadcrumb links preserve the full URL state via `query_replace` so returning
to a parent category does not lose the active filters:

```django
<a href="{% url 'ads:listings_category' parent.slug %}{% query_replace request.GET 'page' 1 %}">
```

### City selection

City is applied as a **query parameter** (`?city=<slug>`) on the current URL.
Selecting a city preserves the active category path:

- From a listings page (`/category/<slug>/`): city becomes `?city=<slug>`
  appended to the category path.
- From the "Entire country" clear button: `city` is dropped, preserving `lang`
  and all non-city filters on all pages.
- From an existing `/city/<old-slug>/` path: the path segment is replaced (not
  appended).

### "Entire country" clear behavior

The "Вся страна" / "Entire country" clear button (in the preferred-city panel)
clears the city context but **preserves everything else**:

- **Preserved:** `lang`, `sort`, `listing_purpose`, `listing_condition`, `features`,
  `min_price`, `max_price`.
- **Cleared:** `city` (the explicit URL city overrides any preference).
- **Applies on all pages** (listings, search, ad detail) — it is a path-relative
  operation that drops `?city=` from whatever URL the buyer is on.

| Operation | `lang` | `city` | `sort` | `listing_purpose` | `features` | `min_price`/`max_price` | `q` (search) | `page` |
|---|---|---|---|---|---|---|---|---|
| Category nav | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | dropped (new context) | reset to 1 |
| City select | ✅ | replaced | ✅ | ✅ | ✅ | ✅ | preserved | preserved |
| Entire country clear | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | preserved | preserved |
| Breadcrumb nav | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | preserved | reset to 1 |
| Language switch | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | preserved | reset to 1 |
| Clear all filters | ✅ | ⚠️ (path-encoded only) | reset | ❌ | ❌ | ❌ | ✅ (search only) | reset to 1 |

See [`filter-ui.md`](filter-ui.md#filter-resetclear-all) for how "Clear all
filters" differs from "Entire country."

## Filter and pagination URL contract

The full query-parameter contract (names, AND-semantics for repeated `features=`,
persistence rules) is specified in
[`filter-ui.md`](filter-ui.md#pagination-url-preservation). Key rules relevant to
URL state preservation:

- Pagination links append the **full active filter set** so a bookmarked or
  shared page two stays on the same result subset.
- `listing_purpose`, `listing_condition`, and each `features=<slug>` are
  **repeated** (one param per feature, not comma-joined) to preserve AND-semantics.
- `sort` is preserved in pagination URLs even while a `q` (full-text) query is
  active.

## Implementation summary

| Concern | Implementation | Canonical location |
|---|---|---|
| URL construction (add/replace/drop params) | `query_replace` template tag | `apps/core/templatetags/dict_tags.py` |
| City resolution from URL | `CityResolutionMiddleware` | `apps/core/middleware/city_resolution.py` |
| Preferred-city default | `PreferredCityMiddleware` | `apps/core/middleware/preferred_city.py` |
| Language resolution | `LanguagePreMiddleware` | `apps/core/middleware/language.py` |
| HTMX safety net (request interception) | `htmx:configRequest` global hook | `static/theme/js/url_state.js` |
| HTMX safety net (post-swap relink) | `htmx:afterSwap` hook | `static/theme/js/url_state.js` |
| Category submenu rendering | Category submenu view (cached HTML fragment) | `apps/categories/views.py` |

## Test coverage

URL state preservation is guarded by dedicated test suites:

| Test file | Scope |
|---|---|
| `src/backend/apps/core/tests/test_templates.py` (or similar) | `query_replace` tag unit tests |
| `src/backend/apps/core/tests/test_catalog_filters.py` | Category/city/filter URL state on catalog navigation |
| `src/backend/apps/core/tests/test_url_state.py` | HTMX safety net + cross-engine transitions |
| `src/telegram_bot/tests/conftest.py` | (bot side — see separate conftest) |

See [`search-journeys.md`](../04-user-stories/search-journeys.md#journey-capability-matrix)
for the behavior-variant matrix used to derive coverage.

## Related user stories

- [US-B3](../04-user-stories/buyer-stories.md) — Category + filter → type query → results (context loss documented as a known gap)
- [US-B2](../04-user-stories/buyer-stories.md) — Header search bar (query-only, no category/city carry)
- [US-B6](../04-user-stories/buyer-stories.md) — Pagination preserves all filters
- [US-B7](../04-user-stories/buyer-stories.md) — City handling and preferred-city fallback
- [US-B13](../04-user-stories/buyer-stories.md) — Footer "Contact us" (see [contact-us.md](contact-us.md))
