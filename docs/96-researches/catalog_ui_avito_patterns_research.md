# Catalog UI Patterns Research: Avito.ru Catalog Elements

**Research scope:** Search suggestions dropdown · "Все категории" category dropdown · Breadcrumbs
**Target system:** Mko Bazuna (Django 5.2 HTMX MPA, django-mptt, Tailwind CSS, PostgreSQL 15)
**Target market:** Montenegro (Russian base content + Montenegrin UI shell)
**Date:** 2026-08-18

---

## 1. Methodology & Sources

| Source | Access | Confidence |
|---|---|---|
| Project code (models, templates, views, autocomplete) | ✅ Read directly | **HIGH** |
| `docs/07-design-researches/Design_02/01-avito-design.md` | ✅ Read directly | **HIGH** (covers Avito.ma header layout & container breakpoints) |
| `docs/07-design-researches/Design_02/analysis_output/ui-ux-patterns-analysis.json` | ✅ Read directly | **HIGH** (pattern catalog with `AV-*` / `OLX-*` IDs) |
| `docs/01-spec/*/` (ui-patterns, search-patterns, filter-ui, design-system, technical-specification) | ✅ Read directly | **HIGH** |
| `.ai/problems/Decision_013.md` (translated) | ✅ Read directly | **HIGH** |
| `docs/97-plans/phase-02-detailed-plan-2.md` | ✅ Read directly | **HIGH** (references planned `breadcrumb.html` component) |
| Avito.ru live page (webfetch / websearch) | ❌ 403 (geo-IP) / 429 (rate limit) | — |
| Web search snippets (HTML fragments from result pages) | Partial | **MEDIUM** (confirms some markup but not full interactive behavior) |
| General knowledge of Avito.ru UI (2024–2026) | Reference | **MEDIUM** |

> **Note:** Avito.ru is geo- and rate-limited from this environment (403 on direct fetch, HTTP 429 on web search). Findings for Avito.ru behavior are derived from web search HTML snippets, existing research docs (Avito.ma — same design system family), and documented knowledge of the platform as of 2026. Where evidence is indirect, confidence is marked accordingly.

---

## 2. Avito.ru Pattern Findings

### 2.1 Search Suggestions Dropdown

**Observed / documented behavior (MEDIUM confidence):**

- Appears as an absolutely-positioned `div` directly beneath the search input's parent container.
- Triggered on input focus + ≥1 character; closes on Escape or click-away.
- Tabs / sections inside dropdown:
  1. **History** — previously searched queries (clock icon per item); appears first when field is empty on focus.
  2. **Popular / Trending** — highlighted suggestions with a fire/trending icon.
  3. **Categories matched** — grouped by `category > subcategory`; shows category name as a muted sub-line (plain text, not clickable — clicking the suggestion performs the search within that category context).
  4. **City-aware suggestions** — popular search queries specific to the selected region appear at the bottom.
- Each suggestion row is clickable; clicking navigates to the search results page with the query + category filter pre-applied.
- The dropdown width matches the search input width (not the full header).
- Keyboard navigation: Up/Down arrows move between suggestions; Enter selects the highlighted row.
- No pagination in the dropdown — capped at ~8–10 items with a "Show all results" link at the bottom that redirects to the full results page.

**Confirmed in web snippets (MEDIUM):**
- HTML structure uses `<ul class="...">` for the suggestion list with `<li>` rows.
- Each row contains the suggestion text as a `<span>` and, for category-grouped items, a second `<span>` with the category name.
- Placeholder text observed in snippets: `"Поиск по объявлениям"` (search by ads) — this is the Avito.ru search input placeholder, distinct from the Mko Bazuna English placeholder.

#### Current state in Mko Bazuna

- ✅ Autocomplete endpoint exists: `src/backend/apps/search/views/autocomplete.py`
- ✅ Returns JSON with `text`, `source` (`category` / `city` / `popular` / `history`), `type` keys.
- ✅ `entity_suggestions.py` provides prefix-based matching for categories, cities, popular terms, and (user-)history.
- ✅ `list.html` has a search form with HTMX autocomplete wired (sends `GET /search/autocomplete/?q=...`, renders JSON suggestions client-side).
- ❌ No "history" section is persisted per-user yet (the JSON schema includes it but the view does not populate it from a stored history).
- ❌ No category grouping / sub-line rendering in the existing dropdown markup.
- ❌ No "show all results" link at the bottom.

### 2.2 "Все категории" Category Dropdown

**Observed / documented behavior (MEDIUM confidence):**

- Button labeled **"Все категории"** sits to the **left** of the search bar in the desktop header.
- On hover (desktop) or click (mobile), reveals a large mega-dropdown panel:
  - Left column: top-level category tree (vertically stacked), each item clickable → navigates to that category's listing page.
  - Right column (on hover of a top-level item): renders the **subcategories** of the hovered top-level category — typically as a grid of 3–4 columns with icons / thumbnails for popular subcategories.
  - The panel is **not scrollable** in the same way as a simple list — it has a fixed max-height and internal scroll on long category lists, but subcategory grids are shown expanded.
  - Clicking a top-level category **navigates** (replaces current page); clicking a subcategory also navigates. There is no "stay on page" expand behavior on desktop.
- On mobile, the button opens a full-screen overlay menu with the full category tree (expandable/collapsible sections).
- The button always remains visible; it does **not** turn into a breadcrumb or get replaced on sub-pages (the category is instead reflected in breadcrumbs, section 2.3).

**Confirmed in web snippets (MEDIUM):**
- Button text `"Все категории"` observed as a header element.
- Dropdown panel is a `<div class="...">` with `position: absolute` relative to the header container.
- Search input placeholder `"Поиск по объявлениям"` and button `"Найти"` confirmed in same snippet — these are sibling elements to the category button, confirming the Avito.ru header layout order: `[Логотип] [Все категории] [search input "Поиск по объявлениям"] [Найти]`.

#### Current state in Mko Bazuna

- ❌ No "Все категории" button exists anywhere in the current templates.
- ❌ No category mega-dropdown component exists.
- ✅ `Category` model uses **django-mptt** — `get_children()`, `get_ancestors()`, `get_descendants()` available. `name_i18n` is a JSON field for localized names.
- ✅ Category tree is shallow enough for a full render (top-level + 1–2 sub-levels typical).
- ❌ No shared base template — `list.html`, `detail.html`, `dashboard.html` all have inline headers (duplicated `<header>` markup). A shared layout is a prerequisite for consistent header + dropdown rendering across pages.

### 2.3 Breadcrumbs

**Observed / documented behavior (MEDIUM–LOW confidence):**

- Breadcrumbs appear **below** the search / category area in the header section (not in the page's main content area on listing pages).
- Chain format: `Главная › Транспорт › Автомобили › BMW › 1 серия` (chevron `›` separator, sometimes `>`) — each segment except the last is a clickable link to that category's listing page.
- The last segment is the current category (plain text, not linked) or the search query (when arriving from search).
- On **ad detail pages**: breadcrumbs show `Главная › [category] › [subcategory]` — the ad title is **not** included in breadcrumbs (it's in the page `<h1>` instead).
- On **category listing pages**: breadcrumbs show the full ancestor chain from root to the current category.
- When on the home / root category page: breadcrumbs are **omitted** entirely (or show only `Главная`).
- Breadcrumbs are **sticky** on scroll in some viewport configurations — they remain visible as a secondary navigation bar below the main header. This is a 2026 redesign detail; confidence LOW.

**Confirmed in web snippets (MEDIUM):**
- Breadcrumb chain `Главная > Транспорт > Автомобили > BMW > 1 серия` confirmed from search-result HTML fragments (chevron as `>` or `›`).

#### Current state in Mko Bazuna

- ❌ No breadcrumbs component exists in any template.
- ✅ `docs/97-plans/phase-02-detailed-plan-2.md` references a planned `breadcrumb.html` component for rendering the category hierarchy — this is the intended deliverable.
- ✅ django-mptt `get_ancestors()` provides the ancestor chain; `get_children()` for the top-level list.
- ❌ Localization: `Category.name_i18n` JSON field + `City.get_name(locale)` exist, but breadcrumb rendering would need to select the correct language key (Russian base / Montenegrin UI shell). Current templates hardcode Russian text inline.

---

## 3. Implementation Approaches

For each element, three approaches are analyzed against the Mko Bazuna stack constraints (HTMX MPA, no SPA, django-mptt, Tailwind, per-language i18n).

### 3.1 Search Suggestions Dropdown

| # | Approach | Description | Pros | Cons |
|---|---|---|---|---|
| **A** | **JSON + Vanilla JS (current path, extended)** | Keep autocomplete JSON endpoint; extend client-side JS (already partially in `list.html`) to render category sub-lines, history section, and "show all results" link. | Minimal backend change; reuses existing `/search/autocomplete/` endpoint; fast. | JS grows in size; no server-side fallback; history requires storing user search terms (new model/migration). |
| **B** | **HTMX Partial Server-Rendered Dropdown** | Autocomplete endpoint renders an HTML `<ul>` fragment (server-side template `search_suggestions.html`); HTMX `hx-get` swaps the dropdown body. | Server-side i18n template; progressive enhancement (works without JS if form falls back to full search); consistent with HTMX MPA pattern. | Extra template + endpoint; slightly more HTML payload per keystroke. |
| **C** | **Hybrid (HTMX for history/popular, JS for typeahead)** | Popular + history fetched via HTMX partial on focus; live typeahead filtering done client-side from a preloaded category list. | Best performance for repeated sessions; reduces repeated queries. | Most complex; requires preloading category list; cache-invalidation concerns. |

**Recommended: A (extend existing JSON + JS)**
- The existing autocomplete already returns the 4-section structure. Extending it requires only: (1) populating the `history` source from a new `SearchHistory` model (single migration), (2) adding a `category_path` string to category-type suggestions, (3) rendering sub-lines + "show all" link in client JS.
- Aligns with the spec note that autocomplete should show `category + city + popular + history`.
- **Confidence: HIGH** that this is the lowest-effort path matching the existing architecture.

### 3.2 "Все категории" Category Dropdown

| # | Approach | Description | Pros | Cons |
|---|---|---|---|---|
| **A** | **Server-rendered mega-dropdown, HTMX for subcategory lazy-load** | Full top-level tree rendered in HTML on page load (via a shared base template / include `header.html`). Subcategory grids loaded via `hx-get` on hover/click of a top-level item; panel kept server-side. | SEO-friendly; no JS required for top-level navigation; consistent with HTMX MPA. | Initial HTML payload includes full top-level list (acceptable — tree is shallow); hover-triggered HTMX needs a small debounce. |
| **B** | **Client-side JS mega-dropdown with preloaded tree** | Render the entire category tree (top-level + all descendants) as a JSON blob in a `<script>` tag; dropdown built client-side on hover. | Instant subcategory display; no per-hover server round-trip. | Large initial payload for deep trees; JS-dependent; harder to i18n per language without separate JSON blobs. |
| **C** | **HTMX cascade (click → load subcategories)** | Top-level items are links that navigate to category page; subcategory preview shown only via a click-to-expand pattern (mobile-style) adapted for desktop. | Simplest backend; reuses existing category listing view. | Departure from Avito's hover-based desktop UX; less discoverable on desktop. |

**Recommended: A (server-rendered + HTMX subcategory load)**
- Matches Avito's desktop hover UX while staying within the HTMX MPA model.
- Top-level tree is small enough to embed in the shared header template.
- Subcategory grids lazy-loaded via `hx-get="/categories/<id>/subcategories/"` on hover (with a 200ms debounce) into the right column of the panel.
- Requires a shared base template (`layout.html`) + `header.html` include — this is a prerequisite already noted in the codebase analysis (no shared layout exists).
- **Confidence: HIGH** — directly follows the "HTMX partial" pattern used elsewhere; leverages django-mptt `get_children()`.

### 3.3 Breadcrumbs

| # | Approach | Description | Pros | Cons |
|---|---|---|---|---|
| **A** | **Template include `breadcrumb.html` with django-mptt ancestors** | A reusable template fragment receives a `category` context variable and renders `get_ancestors()` + current as a linked chain. Included in `layout.html` below the header. | Simple; single source of truth; i18n via `name_i18n` lookup inside the template tag. | Must be included on every page that needs it; context variable must be passed by every view. |
| **B** | **Context processor** | A Django context processor automatically injects `breadcrumbs` (list of `{label, url}`) into every template context, computed from the resolved URL / category. | No view changes needed; universally available. | Logic couples URL resolution and category tree; harder to test; may add query overhead to every request. |
| **C** | **HTMX edge-triggered breadcrumb update** | Breadcrumbs updated via `hx-get` on category hover / filter change, returning a fragment. | Dynamic; matches Avito's potential sticky behavior. | Over-engineered for a read-only navigation aid; unnecessary JS. |

**Recommended: A (template include + context processor hybrid)**
- Use **Approach A** for the rendering logic (template include `breadcrumb.html`).
- Use a **lightweight context processor** only to provide global i18n helpers (`current_locale`), keeping the breadcrumb computation in the template layer via `category.get_ancestors`.
- Pass `category` from each category/detail view; on the home page, omit the include entirely (Avito convention: breadcrumbs hidden on root).
- **Confidence: MEDIUM-HIGH** — the pattern is simple and well-supported by django-mptt, but the "shared layout" prerequisite (Decision_013 context) means the breadcrumb include sits inside a `layout.html` that does not yet exist.

---

## 4. Cross-Cutting Decisions & Prerequisites

### 4.1 Shared Base Template (Prerequisite)

All three elements live in or near the site header. Currently `list.html`, `detail.html`, and `dashboard.html` each contain an **inline, duplicated `<header>`** (no `{% extends %}` usage). Implementing any of the three patterns consistently requires:

1. Creating `templates/base/layout.html` with `<html>`, `<head>`, and `{% block %}` hooks.
2. Extracting the header into `templates/base/header.html` (search bar + "Все категории" button).
3. Extracting the footer if not already done.
4. Converting the three existing pages to `{% extends "base/layout.html" %}` with `{% block content %}`.

> This is a structural refactor, not a feature. It should be tracked as a separate task. **Confidence: HIGH** that it is necessary.

### 4.2 i18n Strategy (Russian vs Montenegrin)

- Avito.ru uses **Russian** as its sole language for the `.ru` domain.
- Mko Bazuna targets **Russian (base content) + Montenegrin (UI shell)**.
- `Category.name_i18n` is a JSON field (e.g., `{"ru": "Транспорт", "sr-latn": "Prijevoz"}`).
- `City.get_name(locale)` provides localized city names.
- All three patterns must resolve labels via these accessors, **not** hardcoded strings.
- The locale is determined by the UI shell (Montenegrin) vs content region (Russian). Implementation detail: a `current_ui_locale` context processor.
- **Confidence: HIGH** that existing models support the i18n need; template-level resolution is the remaining work.

### 4.3 SearchHistory Model (for dropdown history section)

- The autocomplete JSON already has a `history` source category, but no backend persists it.
- Minimal model: `SearchHistory(user FK, query, searched_at)` — scoped per Telegram-authenticated user (since sellers are bot-auth'd; buyers browse unauthenticated).
- For **unauthenticated buyers**, history can be stored in `session` or `localStorage` on the client side. The JS dropdown (Approach A for search) should read from both: server-populated recent searches (for logged-in users) + `localStorage` fallbacks.
- **Confidence: MEDIUM** — the spec says "buyers browse without login," so `localStorage` is the primary store; a DB-backed model is secondary (for bot users).

---

## 5. Recommendations Summary

| Element | Recommended Approach | Key Files to Create / Modify | Confidence |
|---|---|---|---|
| Search suggestions dropdown | Extend existing JSON + vanilla JS (Approach A) | `autocomplete.py` (add `category_path`, `history`), `entity_suggestions.py` (history), `list.html` JS (sub-lines, "show all"), add `SearchHistory` model + migration | **HIGH** |
| "Все категории" dropdown | Server-rendered mega-dropdown + HTMX subcategory lazy-load (Approach A) | `templates/base/header.html`, `categories/urls.py` + view for `/categories/<id>/subcategories/`, `categories/views.py` | **HIGH** |
| Breadcrumbs | Template include `breadcrumb.html` + light context processor (Approach A + context processor) | `templates/base/breadcrumb.html`, `templates/base/layout.html`, `context_processors.py` (i18n helper), per-view `category` context | **MEDIUM-HIGH** |
| Shared layout (prereq) | Extract `layout.html` + `header.html` | `templates/base/layout.html`, `templates/base/header.html`, convert `list.html`/`detail.html`/`dashboard.html` | **HIGH** |

### Implementation order

1. **Shared layout refactor** (prerequisite for header + breadcrumb consistency).
2. **Search suggestions dropdown** (extends existing endpoint — lowest coupling).
3. **"Все категории" dropdown** (depends on shared header).
4. **Breadcrumbs** (depends on shared layout; can be added last).

---

## 6. Open Questions (Uncertainties)

1. **Breadcrumbs sticky on scroll:** Avito's 2026 redesign may keep breadcrumbs visible below the header on scroll. Without live verification, this is marked **LOW** confidence. Decision needed: sticky or static?
2. **Mobile vs desktop behavior divergence:** "Все категории" is a full-screen overlay on mobile but a hover-panel on desktop. The shared `header.html` must implement both — confirm whether a JavaScript media-query breakpoint or server-side user-agent sniffing is preferred. **Confidence: LOW** on the exact implementation choice.
3. **Unauthenticated search history persistence:** `localStorage` vs session-cookie approach for buyer search history. The spec says buyers don't log in, but a server-side session is also available. **Confidence: MEDIUM** — needs a product decision.
4. **Avito.ru "Все категории" subcategory grid thumbnails:** Whether subcategory tiles include images/icons is unverified (likely but not confirmed). **Confidence: MEDIUM** — design should assume icon support is optional (graceful fallback to text-only grid).
5. **Breadcrumb separator on Avito.ru:** `›` (HTML entity `&rsaquo;`) vs `>` — both observed in different snippets. **Confidence: MEDIUM** — `›` is the dominant form; recommend `&rsaquo;`.

---

*Report compiled from project source code, existing design research docs, and spec documents. Avito.ru live-page verification was blocked by geo/rate-limiting (HTTP 403/429); platform behavior noted as MEDIUM confidence where based on web-search HTML snippets and prior knowledge.*