# Template Architecture Research — Mko Bazuna

**Scope:** Investigate the current template architecture as it relates to the
catalog-page **header redesign** requested in `.ai/problems/Decision_013.md`.
Decision 013 asks for four header changes, applicable **"on all pages, including ads (detail)"**:

1. Search suggestions dropdown (below the input, Avito-style) — *not* "to the side".
2. "All Categories" dropdown button left of the search, with category navigation.
3. Breadcrumbs under the search bar.
4. "Place an ad" button at the top, left of the seller login.

**Method:** Direct source read of every template, view, URLconf, settings, and
CSS file. No external sources consulted — conclusions derive from the repository.

**Confidence key:** findings are tagged HIGH (verified in source) / MEDIUM (inferred
from consistent evidence) / LOW (gap / contradiction).

---

## 1. Current State Summary

### 1.1 No `base.html` exists — every public page is standalone

A repository-wide search for `extends`/`base.html` across all templates found
exactly **one** `{% extends %}` usage:

- `templates/admin/moderation/queue.html` → `{% extends "admin/base_site.html" %}`

Every other public template is a **standalone** full-HTML document: each repeats
`<!DOCTYPE html>`, `<html lang="en">`, a full `<head>` (meta tags, the compiled
Tailwind stylesheet, the Plausible snippet), and `<body>`. There is **no shared
base template** (grep confirmed no `base.html` anywhere under `src/`).

**Evidence:**
- `config/settings/base.py:125-141` — `TEMPLATES[0]`:
  - `DIRS: [BASE_DIR / "backend" / "templates"]`
  - `APP_DIRS: True`
  - context processors: `request`, `auth`, `messages`, `i18n`,
    `plausible_host`, `language` — **no** `bot_username` processor.
- 6 public templates independently re-declare the identical `<head>` block:
  `ads/list.html`, `ads/detail.html`, `ads/dashboard.html`, `ads/edit.html`,
  `analytics/seller_dashboard.html`, `analytics/moderation_dashboard.html`,
  `users/login_issue.html`.

### 1.2 Header duplication — what's repeated vs. what differs

The `<header>` markup is copy-pasted across templates with per-page variation.
Common denominator (present in 6 of 7 public templates):

```html
<header class="bg-white shadow-sm border-b">
    <div class="container mx-auto px-4 py-4">
        <h1 class="text-2xl font-bold text-gray-800">
            <a href="/">Mko Bazuna</a>
        </h1>
        ...page-specific right-side content...
    </div>
</header>
```

| Template | Header contents | Search form? | htmx loaded? | "Place an ad" button? | Auth nav |
|---|---|---|---|---|---|
| `ads/list.html` | logo h1 + `{% include "components/language_switcher.html" %}` | ✅ yes | ✅ yes | ❌ no | anon → login via bot deep-link is implicit (no link) |
| `ads/detail.html` | logo h1 + language_switcher | ❌ no | ❌ no | ❌ no | none |
| `ads/dashboard.html` | logo + "Dashboard" + Logout + Withdraw Data (form) | ❌ no | ❌ no | ❌ no | Logout / Withdraw |
| `ads/edit.html` | logo + "Dashboard / Edit Ad" | ❌ no | ❌ no | ❌ no | none |
| `analytics/seller_dashboard.html` | logo + "Dashboard / Trust" + Logout | ❌ no | ❌ no | ❌ no | Logout |
| `analytics/moderation_dashboard.html` | logo + "Moderation Analytics" + Admin + Logout | ❌ no | ❌ no | ❌ no | Admin / Logout |
| `users/login_issue.html` | **no header at all** | ❌ no | ❌ no | ❌ no | (this IS the login page) |

**Exact duplication:** the `<!DOCTYPE html>…<body>`, the opening `<header>`, the
`container mx-auto px-4 py-4` wrapper, and the logo `<h1><a href="/">Mko Bazuna</a></h1>`
block are byte-for-byte repeated. The **only** shared, truly-reused component
today is `{% include %}` of `components/consent_banner.html` (footer-adjacent)
and `components/language_switcher.html`.

**Key gaps vs. Decision 013:**
- The **search form + autocomplete** exists **only** in `list.html`. It is
  absent from `detail.html`, the dashboards, and `login_issue.html` — yet the
  decision demands it on **all pages including ads (detail)**.
- There is **no "All Categories" dropdown** anywhere.
- There are **no breadcrumbs** (the `/` separators in `edit.html`/`dashboard.html`
  titles are hardcoded headings, not a structured breadcrumb component).
- There is **no "Place an ad" button** anywhere (grep returned no matches).

### 1.3 htmx is loaded per-template, not globally

Only `list.html` includes `<script src="https://unpkg.com/htmx.org@1.9.12"></script>`
in `<head>`. The other 6 public templates do **not** load htmx at all. The
`django_htmx` package is in `INSTALLED_APPS` (`base.py:91`) but the
`HtmxMiddleware` is **not** registered in `MIDDLEWARE`; views instead check
`request.headers.get("HX-Request")` manually (`listings.py:419`, `search.py:154`).

**Implication for the redesign:** if the shared header carries the HTMX-powered
search-autocomplete (which it must, per Decision 013 #1), then **every page that
renders the header must also load htmx** and the autocomplete inline script.
Today only `list.html` qualifies — this is itself a refactoring requirement.

### 1.4 Consent banner: the only reusable component (and its test contract)

`components/consent_banner.html` is `{% include %}`-d by 5 templates and is
guarded at the call site by a deleted-user check:

```django
{% if not request.user.is_authenticated or not request.user.is_deleted %}
{% include "components/consent_banner.html" %}
{% endif %}
```

The banner itself checks `{% if not consent_shown %}` internally. This guard is
**verified by a test** (`apps/core/tests/test_templates.py`): it reads the
template lines and asserts the `{% if %}` opens on the line **immediately
before** the include and `{% endif %}` closes on the line **immediately after**.
Any base-template refactor that moves the banner into a `base.html` block would
break this line-relative assertion and require a test update.

---

## 2. Template Architecture Assessment

### 2.1 Current state — the autocomplete dropdown is positioned incorrectly (Decision 013 #1 root cause)

In `list.html:30-43`:

```html
<div class="relative flex gap-2">
    <input ... id="search-input" ... hx-target="#autocomplete-dropdown" ...>
    <ul id="autocomplete-dropdown" class="autocomplete-dropdown"></ul>
    <button type="submit">Search</button>
</div>
```

The `<ul>` has class `autocomplete-dropdown`, but **that class is defined nowhere.**
The CSS source (`src/theme/static/theme/css/input.css`) is a 3-line Tailwind
entry:

```css
@import "tailwindcss";
@source "src/backend/templates/**/*.html";
```

and `output.css` is the minified Tailwind v4.3.3 build (no custom rules). A grep
for `autocomplete-dropdown` across all `.css` files in `src/` returned **zero**
matches. Consequently:

- The `<ul>` is a **flex child** flowing inline between the `<input>` and the
  `<button>` → the list renders **to the side** of the input, not as a dropdown
  anchored below it.
- The parent `<div class="relative ...">` *could* host an absolute child, but
  the `<ul>` carries no `absolute` / `z-index` / `inset` / `shadow` / `max-h` /
  `overflow-y` classes.
- The inline JS (`list.html:59-134`) only toggles Tailwind's `.hidden` util and
  sets `innerHTML`; it never applies the positioning that a dropdown needs.

This is the **exact** defect described in Decision 013 ("где-то сбоку" / "to the
side"): the suggestions render as an inline list adjacent to the input instead
of dropping down beneath it.

The reference mockup files at the repo root (`electronics.html`,
`transport.html`) reproduce the **same** defect — they hardcode the identical
`<ul id="autocomplete-dropdown" class="autocomplete-dropdown">` with no
positioning. They are static, standalone HTML (they hardcode URLs like
`/search/` and `/static/theme/css/output.css`), **not** part of the Django
template graph — they appear to be design-reference / Avito-comparison pages.

**Fix requires:** (a) give the `<ul>` Tailwind positioning classes
(`absolute z-20 w-full mt-1 ... max-h-60 overflow-y-auto`), keeping the
`autocomplete-dropdown` token so `test_autocomplete_template.py` still sees it,
and (b) start it `hidden` so it doesn't flash inline before htmx fires.

### 2.2 Template architecture — pros/cons of the current per-page approach

**Pros (why the team chose it):**
- `ad_list.html` renders as a **bare HTMX fragment** (no `<html>`), swapped into
  `#ad-list` via `hx-swap="innerHTML"` — works precisely *because* there is no
  base template forcing a full document. A base-template/blocks approach must
  keep fragments separate.
- `SimpleTestCase` template tests (`test_templates.py`,
  `test_autocomplete_template.py`) assert on **literal line content** of
  specific files — standalone templates make those assertions straightforward.
- No Django-block inheritance complexity for an HTMX MPA where most page changes
  are fragment swaps.

**Cons / debt:**
- Full-HTML boilerplate (`<!DOCTYPE html>`, `<head>`, CSS, plausible script) is
  duplicated 7× — any global change (e.g. adding htmx everywhere, bumping the
  htmx CDN version) means editing every template.
- The header logo + wrapper is duplicated 6× with divergent right-side nav per
  page, so a site-wide header change (Decision 013) means 6 coordinated edits.
- `detail.html` lacks htmx *and* the search form, so to put the search
  autocomplete on the detail page you must add both the htmx `<script>` and the
  inline autocomplete `<script>` there — i.e. the "shared header" can't be purely
  a template include unless script loading is also unified.
- View context is inconsistent: `ad_detail()` passes `bot_username` +
  `consent_shown`; `listings()` and `search()` pass only `consent_shown` (and
  `listings()` doesn't even pass `query` despite `list.html` referencing
  `{{ query|default:'' }}` — line 34; `search.py` does pass `query`). The
  proposed shared header needs `bot_username` (for the "place ad" deep-link and
  the detail contact button) on **every** page, but it is not globally available.

### 2.3 What refactoring a shared header requires

To satisfy Decision 013 ("on all pages, including ads (detail)"), a shared
header component must provide, in one place:

1. Logo + site title (trivial, already common).
2. **"All Categories" dropdown** — needs the root category tree. `Category` is a
   `django-mptt` `MPTTModel` (`categories/models.py:13`) with `get_descendants`,
   `get_children`, `get_root_nodes`, and a `get_name(locale)` i18n accessor. The
   tree can be rendered server-side; no category endpoint exists yet
   (`categories/urls.py:9` is empty: `# Views added in Task 3`).
3. **Search form + autocomplete dropdown** (the fixed version) — only in
   `list.html` today; must be added to `detail.html` (+ analytics/login pages).
   Needs htmx + inline script loaded on every such page.
4. **Breadcrumbs** — derive from the current route/category. `ad_detail` already
   `select_related("category","city")`; `listings`/`search` carry
   `current_category`/`current_city` slugs. A breadcrumb component needs the
   category chain (ancestors) which mptt provides (`get_ancestors`).
5. **"Place an ad" button** — Telegram deep-link
  `https://t.me/{{ bot_username }}?start=...`. Needs `bot_username` on every
   page (currently only `ad_detail` passes it).

So the two **non-template** enablers are: (a) make `bot_username` globally
available (context processor or pass per-view), and (b) make the root-category
tree available to the header (context processor or HTMX partial).

---

## 3. Autocomplete API Contract

**Endpoint:** `GET /api/search/autocomplete?q=<prefix>`
(`apps/search/urls.py:11`, name `search:autocomplete`,
`apps/search/views/autocomplete.py`).

### 3.1 Response format

`200 OK` → `JsonResponse({"suggestions": [...], "query": "<sanitized>"})`:

| Suggestion source | Dict keys | Notes |
|---|---|---|
| User history | `text`, `source="user_history"` | Only for authenticated users |
| Entity (category) | `text`, `source="category"`, `type="category"` | `name__istartswith`, `is_active=True` |
| Entity (city) | `text`, `source="city"`, `type="city"` | `name__istartswith`, no active filter |
| Popular search | `text`, `source="popular_search"`, `hit_count` | `query_normalized__startswith`, `hit_count >= 10` |

- Merge order: **user history → entities → popular** (history first).
- Deduplicated by `text` (case-sensitive exact match), preserving order.
- Hard cap: `_MAX_SUGGESTIONS = 10` (`autocomplete.py:23`) — returned as
  `unique[:10]`.
- `source` values come from `SearchSuggestionSource` StrEnum
  (`core/enums.py:174-180`): `user_history`, `popular_search`, `category`, `city`.

### 3.2 Rate limiting

`apps/search/services/rate_limit.py`:
- Per-IP sliding window: `RATE_LIMIT_REQUESTS = 30` per `RATE_LIMIT_PERIOD = 60s`.
- Key `autocomplete_rl:{ip}` via Django cache (`cache.add` then `cache.incr`).
- Over limit → `autocomplete()` returns `429` with body `{"error": "rate_limit"}`
  (`autocomplete.py:58`). The template JS treats `xhr.status === 429` and
  `error === "rate_limit"` as a `hide()` signal (`list.html:102-104`).
- Cache backend is Redis in prod (`CACHES` → `django_redis`), LocMem in
  dev/test (`dev.py:40`, `test.py:47`).

### 3.3 Query sanitization

`apps/core/utils/sanitize.py:sanitize_autocomplete_query`:
- Returns `""` (→ empty `suggestions`) for length < 2 or > 100.
- Strips characters `[;'\"\\]` (SQL/XSS harden); `'; DROP TABLE--` → empty.
- `.strip()` then char filter.
- Confirms tests: `test_autocomplete_empty_query` (no param / single char → `[]`),
  `test_autocomplete_malicious_query_sanitized` (injection string → `[]`).

### 3.4 Template-test contract (`test_autocomplete_template.py`)

`SimpleTestCase` reading `list.html` as text and asserting the **exact** HTMX
wiring (no DB needed):

- `id="search-input"`
- `name="q"`
- `hx-get=` attribute whose target resolves to `search:autocomplete`
- `hx-trigger="input delay:300ms"`
- `hx-target="#autocomplete-dropdown"`
- `hx-swap="none"`
- `autocomplete="off"` on the input
- `<ul id="autocomplete-dropdown"` present; the token `autocomplete-dropdown`
   appears in the file
- an inline `<script>` exists and contains `htmx:afterRequest`
- **`settings.BOT_USERNAME` does NOT appear** (settings must be passed via
   context, not referenced as `settings.X` in templates)

Any redesign of the search input/dropdown **must keep these assertions passing**
(or the test must be intentionally updated).

### 3.5 Autocomplete services (supporting data)

- `entity_suggestions.py:get_entity_suggestions(prefix, limit=5)` — mptt Category
  (`istartswith`, `is_active=True`) + City (`istartswith`); returns
  `{text, source, type}`.
- `popular_search.py:get_popular_suggestions(prefix, limit=5)` +
  `increment_popular_search(query)` — `PopularSearch` model, `hit_count >= 10`,
  atomic `get_or_create` + `F()` increment.
- `search_history.py:get_user_search_history(user_id, limit=5)` +
  `record_search_history` — `SearchHistory`, dedupe-by-normalized, prune to 50.
- The search view (`search.py`) calls `increment_popular_search` and
  `record_search_history` **only when a `query` is present** (`search.py:125-127`),
  and only records user history for authenticated users (`search.py:126-127`).
  This is the data source the dropdown relies on.

---

## 4. URL Structure

From `config/urls.py` (root) + each `apps/<app>/urls.py`:

| Path | View | Template | Auth |
|---|---|---|---|
| `/` | `ads:listings` | `ads/list.html` | public (homepage = listings) |
| `/category/<slug>/` | `ads:listings_category` | `ads/list.html` | public |
| `/city/<slug>/` | `ads:listings_city` | `ads/list.html` | public |
| `/<int:ad_id>/` | `ads:detail` | `ads/detail.html` | public |
| `/<int:ad_id>/edit/` | `ads:edit` | `ads/edit.html` | login_required |
| `/<int:ad_id>/archive|delete|reactivate/` | `ads:...` | — (redirect) | login_required |
| `/media/<key>` (prod via `X-Accel-Redirect`) | `ads:media_gate` | — | public/staff |
| `/search/` | `search:search` | `ads/list.html` | public |
| `/api/search/autocomplete` | `search:autocomplete` | JSON | public |
| `/login/issue/` | `consent:login_issue` | `users/login_issue.html` | public |
| `/login/status/` | `consent:login_status` | — (poll; 200/204/410) | public |
| `/consent/accept|decline|withdraw/` | `consent:*` | — (redirect) | login_required (accept/decline/withdraw) |
| `/dashboard/` | `ads:dashboard` | `ads/dashboard.html` | login_required |
| `/analytics/trust/` | `analytics:seller_trust_dashboard` | `analytics/seller_dashboard.html` | login_required |
| `/analytics/moderation/` | `analytics:moderation_analytics` | `analytics/moderation_dashboard.html` | staff-only (404 if not staff) |
| `/health/`, `/csp-report/` | `core:*` | — | public |

Notes:
- The **homepage IS the listings page** (`/` → `ads:listings` → `list.html`).
- Category browsing is routed through the **ads** app (`/category/<slug>/`),
  not the categories app — `apps/categories/urls.py` and `apps/locations/urls.py`
  are **both empty** (`urlpatterns = []  # Views added in Task 3`).
- The login flow lives at `/login/issue/` under the `consent` namespace
  (`app_name = "consent"` in `users/urls.py`), **not** `users:`.
- `save_search_modal.html` references `{% url 'search:list' %}` and
  `{% url 'search:save-search' %}` — **neither route exists** in
  `search/urls.py` (only `search` and `autocomplete` are defined). This partial
  is currently dead/broken code.

---

## 5. Feasible Approaches for a Shared Header

### Approach A — Extract a `components/header.html` via `{% include %}` (no base template)
- Move the common `<header>` (logo + the four new features) into
  `templates/components/header.html`, parameterised by passed context vars
  (`current_category_path`, `current_city`, `bot_username`, `consent_shown`,
  `top_categories`).
- Each public template replaces its inline header with
  `{% include "components/header.html" %}`.
- Fix the autocomplete `<ul>` in the shared header by adding Tailwind positioning
  classes (`absolute z-20 w-full mt-1 bg-white border rounded-lg shadow-lg
  max-h-72 overflow-y-auto`) while **keeping** the `autocomplete-dropdown` token
  so `test_autocomplete_template.py` still passes.
- Make `bot_username` + `top_categories` available on every page via a small
  **context processor** (or a tiny per-view mixin), so the "place an ad" deep-link
  and the category dropdown work on `detail.html`, dashboards, etc.
- Add the htmx `<script>` + autocomplete inline script to `list.html` and
  `detail.html` (the two public pages that show the header search). The shared
  header's autocomplete JS must live at the **end of `<body>`** (after htmx), so
  bundle it as a second `{% include %}` (`components/autocomplete.js.html`) or
  inline.

**Pros:** Mirrors the existing `{% include %}` pattern (consent_banner,
language_switcher, ad_list). No `{% extends %}`/blocks introduced. HTMX fragments
(`ad_list.html`) stay clean. Lowest risk to existing line-level template tests.
**Cons:** `<!DOCTYPE html>`/`<head>` boilerplate remains duplicated; htmx +
autocomplete script still need explicit inclusion on each page that shows the
search.

### Approach B — Introduce `base.html` with blocks + shared header
- Create `templates/base.html` holding `<!DOCTYPE html>`, `<head>` (with htmx
  loaded **globally** — which solves the per-template htmx gap), the shared
  header, and `{% block content %}` / `{% block extra_js %}` / `{% block title %}`
  blocks.
- Each public template becomes `{% extends "base.html %}` and fills blocks.
- The consent banner moves into `base.html` (or stays in a block).

**Pros:** Strongest DRY for `<head>`/htmx/script includes — htmx is loaded once
for **all** pages automatically, which is exactly what the cross-page autocomplete
needs. Single source of truth for the header.
**Cons:** Larger rewrite of 6-7 templates. **Breaks** the existing
`test_templates.py` consent-banner guard test (it asserts the `{% if %}` /
`{% endif %}` are the literal lines bracketing the `{% include %}` — moving the
banner into a block in `base.html` removes those lines from the leaf templates).
Must also keep `ad_list.html` as a standalone fragment (no extends). Requires
updating tests. Higher blast radius.

### Approach C — HTMX-powered header fragment + server-rendered shell (deferred)
- Keep templates standalone, but make the header itself an HTMX target: render a
  `components/header.html` server-side, and on navigation/swaps only the
  `<main>` is swapped (header stays). Category dropdown + breadcrumbs become
  `hx-get` partials from a new lightweight endpoint (e.g.
  `/api/categories/menu/`).
- Autocomplete stays as today (HTMX GET on input), only the *positioning* CSS
  is fixed.

**Pros:** Most "HTMX-native"; category tree loads lazily; header never
re-downloads.
**Cons:** Biggest scope; introduces a new endpoint + partial; the category
browsing view doesn't exist yet (`categories/urls.py` empty). Over-engineered for
the immediate decision (013) scope, which is primarily a *layout* fix.

---

## 6. Recommended Option

**Recommendation: Approach A (extract `components/header.html` via `{% include %}`),
with two supporting changes**:

1. **Fix the autocomplete positioning in the shared header** by replacing the
   bare `class="autocomplete-dropdown"` on the `<ul>` with Tailwind positioning
   utilities (`absolute z-20 w-full mt-1 bg-white border border-gray-200
   rounded-lg shadow-lg max-h-72 overflow-y-autohidden` initially) — keeping the
   `autocomplete-dropdown` id/class so the existing template test still asserts
   on it. This directly resolves Decision 013 #1.
2. **Make `bot_username` and the root category tree globally available** via a
   small context processor (or a `ContextDecorator`/per-view injection), so the
   "Place an ad" deep-link and the "All Categories" dropdown work on `detail.html`
   and the dashboards — not just `list.html`. This does not touch the
   `settings.BOT_USERNAME`-in-template rule (the proc returns a context var).

**Rationale for Mko Bazuna's HTMX MPA:**
- The codebase **already standardises on `{% include %}`** for reusable fragments
  (consent_banner, language_switcher, ad_list). Introducing `{% extends %}`/
  `base.html` would be a new, unproven pattern in this repo and would force a
   test rewrite (`test_templates.py`'s line-relative consent guard). Approach A
   stays consistent with the existing architecture — a project rule
   ("Follow Existing Patterns").
- It **does not endanger the HTMX fragment model**: `ad_list.html` stays a bare
  fragment swapped into `#ad-list`, exactly as today.
- It directly satisfies "on all pages, including ads (detail)" for the header
  content (logo + category dropdown + search + breadcrumbs + place-ad), while
   leaving the `<head>` duplication as acceptable, lower-priority tech debt
   (Decision 013 is scoped to the **header/catalog area**, not the document shell).
- The htmx-script-loading concern is contained: only `list.html` and
  `detail.html` render the buyer-facing header with search today; those two
  templates gain the htmx script, and `login_issue.html`/dashboards can opt out
   of the search-bearing header variant (or get a lighter one).

**Trade-off accepted:** Approach A leaves `<head>` boilerplate duplicated. If the
  team later wants one source of truth for `<head>`/htmx, that is the natural
  moment to migrate to Approach B and update the two template tests.

---

## Appendix — Source evidence ledger (HIGH confidence)

| Claim | File:line |
|---|---|
| Only one `{% extends %}` in templates (admin) | grep across `src/backend/templates` → `admin/moderation/queue.html:1` |
| No `base.html` under `src/` | `uv run python` glob for `*base*.html` → NONE |
| TEMPLATES config | `config/settings/base.py:125-141` |
| context processors (no `bot_username`) | `config/settings/base.py:131-138` |
| `BOT_USERNAME` / `PLAUSIBLE_HOST` in settings | `config/settings/base.py:213,217` |
| list.html header | `templates/ads/list.html:18-25` |
| list.html search form + `<ul autocomplete-dropdown>` | `ads/list.html:29-43` |
| list.html inline autocomplete JS | `ads/list.html:59-134` |
| detail.html header (no search) | `templates/ads/detail.html:18-27` |
| dashboard.html header | `templates/ads/dashboard.html:17-36` |
| edit.html header | `templates/ads/edit.html:16-26` |
| seller_dashboard.html header | `templates/analytics/seller_dashboard.html:19-33` |
| moderation_dashboard.html header | `templates/analytics/moderation_dashboard.html:18-31` |
| login_issue.html has no header | `templates/users/login_issue.html` (full file, 71 lines — no `<header>`) |
| htmx script only in list.html (+ 2 reference files) | grep `htmx\.org` across `*.html` |
| CSS has no `.autocomplete-dropdown` rule | `src/theme/static/theme/css/input.css` (3 lines) + grep of all `.css` → 0 matches |
| Autocomplete JSON shape | `apps/search/views/autocomplete.py:88-90` |
| Suggestion keys per source | `entity_suggestions.py:48-64`, `popular_search.py:73-79`, `autocomplete.py:66-69` |
| `_MAX_SUGGESTIONS = 10` | `autocomplete.py:23` |
| Rate limit 30/60s, 429 body | `services/rate_limit.py:17-20,53`, `autocomplete.py:57-58` |
| Sanitization: len<2 → empty | `core/utils/sanitize.py:41-42` |
| Template test assertions | `apps/search/tests/test_autocomplete_template.py:29-57` |
| Consent-banner guard test | `apps/core/tests/test_templates.py:21-73` |
| `ad_detail` passes `bot_username` + `consent_shown` | `apps/ads/views/listings.py:78-83` |
| `listings()` does NOT pass `query` | `listings.py:391-413` |
| `search()` passes `query` | `apps/search/views/search.py:139-151` |
| Category is MPTTModel with tree helpers | `apps/categories/models.py:13` + `MPTTModel`/`TreeForeignKey` |
| Category/City `get_name(locale)` | `categories/models.py:53`, `locations/models.py:45` |
| categories/urls.py + locations/urls.py empty | both `:9` — `# Views added in Task 3` |
| analytics urls | `apps/analytics/urls.py:15-18` |
| search/urls.py | `apps/search/urls.py:9-12` (only `search` + `autocomplete`) |
| `save_search_modal` references nonexistent URLs | `templates/search/partials/save_search_modal.html:6,14` (`search:list`, `search:save-search` undefined) |
| Root reference mockups | `electronics.html`, `transport.html` (standalone HTML, not in template graph) |
