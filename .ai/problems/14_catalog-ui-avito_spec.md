# Spec_014 — Catalog Page UI Redesign (Avito-style Header)

**Decision source:** `.ai/problems/Decision_013.md`
**Spec state:** APPROVED — all Product Owner questions resolved (see §6)
**Date:** 2026-08-18
**Stack:** Django 5.2 LTS · Python 3.14 · HTMX 1.9.12 (pinned CDN) · django-mptt · Tailwind CSS · PostgreSQL 18

---

## 1. Business Goal

Redesign the catalog header to match Avito's UI pattern so that buyers can efficiently
discover categories, refine their search via contextual suggestions, navigate via
breadcrumbs, and initiate ad creation through the Telegram bot — all from a unified,
consistent header that appears on **every public page** (catalog, search results, and ad
detail).

## 2. Scope

### In Scope
1. **Search suggestions dropdown** — Avito-style dropdown beneath the search input,
   rendering contextual grouped suggestions (`city` → `category` → `popular_search` →
   `user_history`).
2. **"All Categories" dropdown button** — left of the search bar; reveals the full
   4-level MPTT category tree (one branch expanded at a time).
3. **Breadcrumbs** — rendered below the search bar; shows the category ancestor chain
   from root to current; on search results, shows category path separately from the
   search query.
4. **"Place an ad" button** — top-left of the header, above the seller login; triggers
   the Telegram bot deep-link flow.
5. **Responsive behavior** — desktop dropdown panels; mobile off-canvas category menu
   with accordion sections; full-width search dropdown.
6. **Shared header component** — a single `{% include %}` fragment so all four elements
   render identically across pages.
7. **HTMX script loading** — htmx + autocomplete inline script must load on every page
   that renders the search-bearing header (catalog + detail at minimum).

### Out of Scope
- Dashboard / seller cabinet pages — these get a **separate, simpler header** (PO §9).
- `login_issue.html` — no header redesign needed (this is the login page itself).
- New ad-creation form on the web — ad creation is Telegram-bot-only (PO §6).
- Search personalization beyond preferred-city storage (PO §1: no complex ML
  personalization on MVP).
- Breadcrumbs sticky-on-scroll behavior (not requested; low confidence in Avito's
  2026 sticky detail — omitted).

---

## 3. Facts

### 3.1 Current State (from source research)

| Fact | Evidence |
|---|---|
| No `base.html` exists; every public template is standalone | `template_architecture_research.md` §1.1 |
| `list.html` is the only template with the search form + autocomplete | `template_architecture_research.md` §2.2 |
| The autocomplete `<ul>` has class `autocomplete-dropdown` defined nowhere → renders "to the side" | `template_architecture_research.md` §2.1 |
| `input.css` contains only 3 lines (`@import "tailwindcss"`) — no custom CSS rules | `template_architecture_research.md` §2.1 |
| htmx is loaded only in `list.html`; not on `detail.html` or other templates | `template_architecture_research.md` §1.3 |
| Autocomplete endpoint returns `{suggestions,query}` with sources `category`/`city`/`popular_search`/`user_history` | `autocomplete_architecture_research.md` §3.1 |
| `Category` uses `django-mptt` (`MPTTModel`) with `name_i18n` JSON field; `get_ancestors()`, `get_descendants()`, `get_children()` available | `htmx_dropdown_research.md` §1.3, `catalog_ui_research.md` §2.2 |
| `categories/urls.py` and `locations/urls.py` are empty (`urlpatterns = []  # Views added in Task 3`) | `autocomplete_architecture_research.md` §4 |
| `bot_username` is only passed to `detail.html`, not globally | `template_architecture_research.md` §1.2, §2.3 |
| `SearchSuggestionSource` StrEnum defines: `user_history`, `popular_search`, `category`, `city` | `core/enums.py` (researched) |
| `test_autocomplete_template.py` asserts exact HTMX wiring in `list.html` | `autocomplete_architecture_research.md` §3.4 |
| `test_templates.py` asserts consent-banner guard via line-relative `{% if %}`/`{% endif %}` brackets | `template_architecture_research.md` §1.4 |
| Rate limit: 30 requests / 60s / IP; 429 on exceed | `autocomplete_architecture_research.md` §3.2 |
| Autocomplete query sanitization: min 2 chars, max 100, strips `;'\"\` characters | `autocomplete_architecture_research.md` §3.3 |

### 3.2 HTMX 1.9.12 Constraints (critical)

- `hx-on` (inline event-handler attribute) is **NOT available** — introduced in HTMX 2.0.
- Outside-click and Escape-to-close must use **vanilla JS** via `data-*` attributes
  (matching the existing `language_switcher.html` toggle pattern).
- Hover + click compound trigger: `hx-trigger="click hover delay:300ms"` works in 1.9.12.
- `hx-target="closest [data-mega-panel]"` and `hx-swap="innerHTML"` are supported.

---

## 4. Requirements (derived from Product Owner decisions)

### R-01: Search Suggestions Dropdown

| ID | Requirement | Source |
|---|---|---|
| R-01a | Dropdown renders directly **below** the search input (not to the side). Must use Tailwind absolute positioning (`absolute z-20 w-full mt-1 ... max-h-72 overflow-y-auto`). | PO #8; `template_architecture_research.md` §2.1 |
| R-01b | Suggestions are **contextually grouped** in this order: City → Category → Popular Search → User History. Not all sources shown simultaneously — relevance determines which are displayed. | PO #1 |
| R-01c | City suggestions include a section header ("Города"). Category suggestions include a category sub-line (muted text showing the parent category path). Popular search has a fire/trending icon. User history has a clock icon. | PO #1; `catalog_ui_research.md` §2.1 |
| R-01d | Clicking a **city** suggestion sets it as the active city filter and saves `preferred_city` (cookie for guests, profile for registered users). Subsequent searches use the preferred city. | PO #1 |
| R-01e | Clicking a **category** suggestion filters the current results by that category via HTMX (no full page reload). URL is updated via `push-url`. | PO #2 |
| R-01f | Clicking a **text suggestion** (popular search / user history) populates the search input and submits the query via HTMX. | PO #2 |
| R-01g | Dropdown closes on: suggestion selection, Escape key, click-outside, navigation away. | PO #8 |
| R-01h | Dropdown shows max ~8–10 items per section. No pagination in dropdown — a "Show all results" link at the bottom redirects to the full results page. | `catalog_ui_research.md` §2.1 |
| R-01i | The `autocomplete-dropdown` identifier must be preserved on the `<ul>` to keep `test_autocomplete_template.py` passing. | `autocomplete_architecture_research.md` §3.4 |
| R-01j | Unauthenticated buyer search history is stored in `localStorage`; registered-user history comes from the server (`SearchHistory` model). | PO #1; `catalog_ui_research.md` §2.1 |
| R-01k | Input triggers autocomplete on `input delay:300ms` with `hx-swap="none"` (existing pattern). Rate limit 30/60s/IP; 429 hides the dropdown. | `autocomplete_architecture_research.md` §3.2–3.4 |

### R-02: "All Categories" Dropdown

| ID | Requirement | Source |
|---|---|---|
| R-02a | Button labeled **"Все категории"** when no category is active; when a category is active, shows the current category name instead. | PO #7 |
| R-02b | Dropdown reveals the full 4-level MPTT tree. Only one branch is expanded at a time — clicking a parent expands its children and collapses siblings. | PO #3 |
| R-02c | Top-level categories rendered server-side in the initial header HTML (via context processor providing `root_categories`). | `htmx_dropdown_research.md` §1.4 |
| R-02d | Subcategories lazy-loaded via HTMX (`hx-get` to a new `/categories/<slug>/submenu/` endpoint) on click/hover. | `htmx_dropdown_research.md` §1.3 |
| R-02e | Clicking any category navigates to its listing page (`/category/<slug>/`). | PO #3 |
| R-02f | Button always remains visible in the header; does not transform into a breadcrumb. | `catalog_ui_research.md` §2.2 |
| R-02g | Panel positioned `absolute` relative to the header container; z-index `z-[90]` (between header `z-50` and modals). | `htmx_dropdown_research.md` §3.2–3.3 |

### R-03: Breadcrumbs

| ID | Requirement | Source |
|---|---|---|
| R-03a | Rendered **below** the search bar in the header. | Decision_013 §3; PO #5 |
| R-03b | On category listing pages: `Главная › [ancestor chain] › [current category]`. Each segment except the last is a clickable link. The last segment is plain text. | PO #5; `catalog_ui_research.md` §2.3 |
| R-03c | On ad detail pages: `Главная › [category] › [subcategory]` (ad title is **not** in breadcrumbs). | PO #5; `catalog_ui_research.md` §2.3 |
| R-03d | When an active search query exists: breadcrumbs show the category path; the search query is shown **separately** below breadcrumbs as "Результаты поиска: [query]" — not inserted into the breadcrumb trail. | PO #5 |
| R-03e | On the home/root page: breadcrumbs are omitted entirely (only `Главная` shown, or nothing). | PO #5; `catalog_ui_research.md` §2.3 |
| R-03f | Built from MPTT `category.get_ancestors(include_self=True)` (root→leaf order). | `htmx_dropdown_research.md` §2.2 |
| R-03g | Separator: `&rsaquo;` (`›`). | `catalog_ui_research.md` §2.3 |

### R-04: "Place an Ad" Button

| ID | Requirement | Source |
|---|---|---|
| R-04a | Button labeled **"+ Подать объявление"**, positioned top-left of the header. | Decision_013 §4; PO #6 |
| R-04b | Clicking immediately opens the Telegram bot deep-link: `https://t.me/{{ bot_username }}?start=create_ad`. No modal pre-explanation on the web. | PO #6 |
| R-04c | Works for both authenticated and unauthenticated users — the bot handles auth state. | PO #6 |
| R-04d | `bot_username` must be globally available (not just on detail pages). | `template_architecture_research.md` §2.3 |

### R-05: Shared Header Component

| ID | Requirement | Source |
|---|---|---|
| R-05a | A single `{% include %}` fragment (`components/header_catalog.html`) renders all four elements (search dropdown, category dropdown, breadcrumbs, place-ad button). | PO #9 |
| R-05b | Applied to: `list.html` (catalog + search results) and `detail.html` (ad detail). | PO #9 |
| R-05c | **Not** applied to: `dashboard.html`, `edit.html`, `login_issue.html` — these keep their existing or simpler headers. | PO #9 |
| R-05d | The `consent_banner.html` line-relative test contract must remain intact (or the test must be updated if the banner moves). | `template_architecture_research.md` §1.4 |
| R-05e | htmx `<script src="https://unpkg.com/htmx.org@1.9.12">` must be loaded on every page that renders the shared header (catalog + detail at minimum). | `template_architecture_research.md` §1.3, §2.2 |
| R-05f | The autocomplete inline `<script>` (containing `htmx:afterRequest` handler) must also be loaded on every page rendering the shared header. | `autocomplete_architecture_research.md` §3.4 |

### R-06: Auth / Cabinet Entry (catalog header)

> **PO clarification (2026-08-20):** Spec 12 CR1 requires a Login link on **all** public pages. R-05c and the previous test contract (`test_auth_nav.py::TestAnonymousHeader`) documented the catalog header as intentionally omitting a login link ("login lives on the seller pages"). The PO has confirmed this was an error — the auth/cabinet entry **must** appear in `header_catalog.html` on all catalog and detail pages. See `24_catalog-header-auth-entry_spec.md` for the full treatment.

| ID | Requirement | Source |
|---|---|---|
| R-06a | **Anonymous visitors** on catalog/detail pages see a compact **icon-only** user button (outline `UserIcon`, 44×44 px) in the top-right corner. Clicking it navigates to `/login/issue/` (Telegram deep-link flow). | PO choice V2(A); Decision_014 §1 |
| R-06b | **Authenticated users** see a **filled avatar/icon** (initials circle or outline→filled `UserIcon`) in the top-right. Clicking it opens a dropdown menu (vanilla JS — HTMX 1.9.12 has no `hx-on`). | PO choice V2(B), V3 |
| R-06c | **Dropdown menu** contains: Cabinet (hub), My Ads (→ `/dashboard/`), Favorites (→ `/cabinet/favorites/`), Settings (→ `/cabinet/settings/`), and Logout (POST+CSRF form). Staff additionally see Admin (→ `/admin/`). | PO choice V3; Spec_012 CR2/CR7 |
| R-06d | **Favorites indicator**: a heart icon (outline for anonymous, filled for authenticated) with a small badge showing the user's saved-favorites count. For anonymous users, the heart is outline with no badge; clicking opens login. | PO choice V4 |
| R-06e | Auth entry is rendered **inside** `header_catalog.html` top-right group, to the left of (or grouped with) the language switcher. Always visible, even on mobile. | PO choice V5 |
| R-06f | The existing tiny text "Cabinet" link (previously the only auth element for authenticated users) is **replaced** by the icon button + dropdown per R-06b–R-06c. | PO correction |

### R-07: Mobile Responsiveness

| ID | Requirement | Source |
|---|---|---|
| R-07a | "All Categories" opens an **off-canvas panel** (☰ hamburger-style) on mobile. | PO #4 |
| R-07b | Category tree inside the off-canvas panel uses **accordion** behavior (tap a parent to expand children, siblings collapse). | PO #4 |
| R-07c | Search dropdown on mobile spans effectively full available width. | PO #4 |
| R-07d | Tap targets must be ≥ 44×44 px. | `htmx_dropdown_research.md` §3.5 |
| R-07e | On desktop, hover opens category submenus with a 300ms debounce; click is the primary toggle. | `htmx_dropdown_research.md` §3.4; PO #3 |

---

## 5. Conceptual Development Tasks

| # | Task | Description | Resolvable By |
|---|---|---|---|
| T1 | **Shared header component** | Extract the duplicated `<header>` into `components/header_catalog.html` via `{% include %}`. Replace inline headers in `list.html` and `detail.html`. | Templates team |
| T2 | **Global context processor** | Add a context processor returning `bot_username` and `root_categories` (top-level active categories) so the shared header works on every page. Register in `settings.TEMPLATES[0]["context_processors"]`. | Backend team |
| T3 | **Category submenu endpoint** | New view + URL (`/categories/<slug>/submenu/`) returning a partial `<ul>` fragment for HTMX lazy-load of subcategories. | Backend team |
| T4 | **Search dropdown positioning fix** | Replace bare `class="autocomplete-dropdown"` with Tailwind positioning utilities (`absolute z-20 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-72 overflow-y-auto hidden`). Keep the `autocomplete-dropdown` id for the template test. | Frontend team |
| T5 | **Search dropdown group rendering** | Extend the autocomplete JSON response with `category_path` (string) on category suggestions; extend client-side JS to render section headers, sub-lines, icons, and a "Show all results" link. | Full-stack |
| T6 | **Preferred city persistence** | Store `preferred_city` in cookie (guests) or user profile (registered). City suggestion click sets this and triggers HTMX filter update + URL push-state. | Full-stack |
| T7 | **Category breadcrumb logic** | Build breadcrumbs from `category.get_ancestors(include_self=True)`; render via a `components/breadcrumb.html` include. Handle root-page omission and search-query display. | Full-stack |
| T8 | **All Categories dropdown behavior** | Implement expand-one-branch-at-a-time via vanilla JS (`data-*` toggle pattern matching `language_switcher.html`); add HTMX `click hover delay:300ms` trigger on top-level items. | Frontend team |
| T9 | **Place an ad button** | Add the `+ Подать объявление` CTA with deep-link `https://t.me/{{ bot_username }}?start=create_ad`. Ensure `bot_username` is in context. | Templates team |
| T10 | **Mobile off-canvas + accordion** | Implement hamburger-triggered off-canvas panel with accordion category tree; ensure search dropdown spans full width on mobile. | Frontend team |
| T11 | **HTMX script loading on detail** | Add `<script src="https://unpkg.com/htmx.org@1.9.12">` and the autocomplete inline script to `detail.html` (currently absent). | Templates team |
| T12 | **Update template tests** | Adjust `test_autocomplete_template.py` assertions if the search input markup changes (new attributes, positioning classes). Preserve the `autocomplete-dropdown` token assertion. | Backend/QA |
| T13 | **Update consent-banner test** | If the consent banner moves out of leaf templates into the shared header include, update `test_templates.py` line-relative assertion accordingly. | Backend/QA |

**Suggested build order:** T1 → T2 → T4 → T11 → T5 → T6 → T3 → T8 → T7 → T9 → T10 → T12 → T13

---

## 6. Resolved Product Owner Decisions

All open questions from the initial analysis have been answered:

| Q# | Question | PO Answer |
|---|---|---|
| 1 | Search dropdown sources | Contextual grouping: City → Category → Popular Search → User History. Preferred city stored in cookie (guest) / profile (registered). No complex personalization on MVP. |
| 2 | Suggestion click behavior | Filters (city/category) → HTMX refine + URL push-state, no full reload. Text suggestions → populate input + HTMX submit. |
| 3 | Category dropdown depth | All 4 levels accessible; one branch expanded at a time (siblings collapse). No giant mega-menu with everything open. |
| 4 | Mobile responsiveness | Off-canvas panel for categories; accordion-style tree. Search dropdown full-width on mobile. |
| 5 | Breadcrumbs on search | Show category path in breadcrumbs; show search query separately below as "Результаты поиска: [query]" — not in the breadcrumb trail. |
| 6 | Place an ad — auth flow | Immediate Telegram deep-link (`t.me/{{ bot_username }}?start=create_ad`). No modal pre-explanation. Bot handles auth. |
| 7 | All Categories button label | Dynamic: "Все категории" when no category active; current category name when active. Dropdown still allows returning to "All". |
| 8 | Close on outside click | Yes. Also Escape-to-close. Also closes on suggestion selection or navigation. Implemented via vanilla JS `click`/`keydown` listeners (HTMX 1.9.12 has no `hx-on`). |
| 9 | Scope | New header for **public catalog + detail** pages. Dashboard/edit pages get a **separate, simpler** header — not unified. |
| 10 | Auth entry in catalog header | **Add** auth/cabinet entry to `header_catalog.html` per PO clarification (2026-08-20). Anonymous = outline user icon button → `/login/issue/`; authenticated = avatar/filled icon with dropdown menu (Cabinet, My Ads, Favorites, Settings, Logout; Admin if staff). Heart icon with favorites count badge. Always visible top-right, even mobile. See `24_catalog-header-auth-entry_spec.md`. |

---

## 7. Technical Constraints

1. **HTMX 1.9.12** — `hx-on` not available; use vanilla JS `data-*` + event listeners for outside-click/Escape.
2. **No `base.html`** — use `{% include %}` pattern (consistent with existing `consent_banner.html`, `language_switcher.html` includes). Do **not** introduce `{% extends %}`/blocks — it would break existing line-relative template tests.
3. **No custom CSS** in `input.css` — all styling must be Tailwind utility classes (no new `.css` rules; the project's CSS pipeline is Tailwind-only per Spec_07).
4. **`autocomplete-dropdown` token** must remain on the `<ul>` for `test_autocomplete_template.py`.
5. **`settings.BOT_USERNAME`** must never appear directly in templates — must come via context variable.
6. **django-mptt** `get_ancestors()` / `get_descendants()` / `root_nodes()` are the only tree accessors to use.
7. **`categories/urls.py`** is currently empty — the submenu endpoint (T3) requires a new URL + view.
8. **`PopularSearch`** model threshold: `hit_count >= 10` for suggestions to appear.

---

## 8. Data & API Contracts

### 8.1 Autocomplete Endpoint (existing, extended)
`GET /api/search/autocomplete?q=<prefix>`

**Response (extended):**
```json
{
  "query": "<sanitized>",
  "suggestions": [
    {"text": "Подгорица", "source": "city",      "type": "city"},
    {"text": "Подержанные автомобили", "source": "category", "type": "category", "category_path": "Товары > Транспорт"},
    {"text": "подержанный автомобиль", "source": "popular_search", "hit_count": 42},
    {"text": "красный велосипед", "source": "user_history"}
  ]
}
```
- Merge order: city → category → popular_search → user_history.
- Cap: 10 total suggestions (`_MAX_SUGGESTIONS = 10`).
- Rate limit: 30 req/60s/IP → 429 → dropdown hidden (client handles).

### 8.2 Category Submenu Endpoint (new)
`GET /categories/<slug>/submenu/`

**Response:** HTMX partial HTML (`<ul>` of children + grandchildren for the given category).
- Rendered via `categories/partials/mega_submenu.html`.
- Cached in Redis (fragment cache keyed by `category_slug:tree_version`).
- Triggered by: `hx-trigger="click hover delay:300ms"` on top-level category button.

### 8.3 Preferred City Storage
- **Guest:** cookie `preferred_city` (city slug), 30-day expiry.
- **Registered:** `UserProfile.preferred_city` FK → `City`.

---

## 9. Out of Scope (Explicitly)

- Base template (`{% extends %}`) migration — intentionally deferred (would break tests).
- Separate mobile search interface — desktop dropdown adapts to mobile width.
- Avito.ru exact visual styling — Avito is the *pattern* reference, not a pixel-match requirement.
- Server-side session storage for buyer history (using `localStorage` per PO #1).
- Unifying the two headers into a single template — the auth entry is added to `header_catalog.html` while preserving the separate `header.html` for dashboard/cabinet/login pages (see R-06).

---

## 10. Acceptance Criteria

### AC-01: Search Dropdown Positioning
- Dropdown `<ul>` renders **below** the search input, not inline to the side.
- Clicking outside or pressing Escape closes the dropdown.
- Test: `test_autocomplete_template.py` still passes (asserting `autocomplete-dropdown` token + htmx wiring).

### AC-02: Contextual Grouping
- Typing "под" shows: Cities section (if match), Categories section (if match, with sub-line), Popular section, History section (if available).
- No empty sections rendered.

### AC-03: Suggestion Click Behavior
- Clicking a city → preferred_city set → results filtered → URL updated via push-state.
- Clicking a category → results filtered by category → URL updated via push-state.
- Clicking a text suggestion → search input populated → results updated via HTMX.

### AC-04: All Categories Dropdown
- Button shows "Все категории" on root, current category name on sub-pages.
- Only one branch expanded at a time.
- Clicking a category navigates to `/category/<slug>/`.
- Panel closes on outside-click / Escape / selection.

### AC-05: Breadcrumbs
- On `/category/nedvizhimost/kvartiry/` → `Главная › Недвижимость › Квартиры` (last item plain text).
- On detail page `/123/` (ad in Квартиры > Продажа) → `Главная › Недвижимость › Квартиры › Продажа`.
- On search results → breadcrumbs show category path + "Результаты поиска: [query]" below.
- On homepage → breadcrumbs hidden.

### AC-06: Place an Ad Button
- Visible top-left on catalog + detail pages.
- Clicking opens `https://t.me/{{ bot_username }}?start=create_ad` in a new tab.

### AC-07: Mobile
- "All Categories" → off-canvas panel with accordion tree.
- Search dropdown spans full width on mobile.
- Tap targets ≥ 44×44 px.

### AC-08: Shared Header
- `list.html` and `detail.html` both render the identical header via `{% include %}`.
- htmx script loaded on both pages.
- Dashboard / edit / login pages are **not** affected (separate headers).
- The catalog header includes an auth/cabinet entry: anonymous users see an icon-only Login button in the top-right; authenticated users see an avatar/icon button with a dropdown menu (Cabinet, My Ads, Favorites, Settings, Logout).
- The catalog header includes a heart icon with favorites count badge (filled + count for authenticated, outline without badge for anonymous).
- Anonymous catalog pages render the login entry (previously omitted — see R-06 PO correction).

---

## 11. Dependencies

- **T2 (context processor)** must precede T1, T9 (header needs `bot_username` + `root_categories`).
- **T3 (submenu endpoint)** must precede T8 (lazy-load needs the URL).
- **T11 (htmx on detail)** is required before the shared header search works on `detail.html`.
- **T4 (positioning fix)** must precede T5 (group rendering relies on correct positioning).
- **Auth entry (R-06):** See `24_catalog-header-auth-entry_spec.md` — the auth/cabinet entry and favorites badge in the catalog header depend on the context processor providing `favorites_count` for authenticated users (Spec_012 login/logout routes and Spec_015 cabinet URLs are prerequisites).

---

## 12. Risks

| Risk | Mitigation |
|---|---|
| Breaking `test_autocomplete_template.py` by changing input markup | Preserve `id="search-input"`, `name="q"`, `hx-target="#autocomplete-dropdown"`, `autocomplete-dropdown` token on `<ul>`. Update test only if unavoidable. |
| Breaking `test_templates.py` consent-banner line assertion if banner moves into shared header | Assess whether banner stays in leaf templates or moves. Update test accordingly before/during T1. |
| HTMX 1.9.12 `hover delay:300ms` causing jank on slow networks | Implement server-side Redis fragment cache for submenu panels (T3). |
| Mobile hover behavior is a no-op | Primary trigger is `click`; `hover` is desktop-only enhancement. |
| `bot_username` not globally available on all pages | Context processor (T2) resolves this. |

---

*Spec compiled from Product Owner decisions (9 questions resolved) and three research reports:
`catalog_ui_avito_patterns_research.md`, `template_architecture_research.md`, and
`htmx_dropdown_breadcrumb_patterns_research.md`.
All sources read directly from the repository.*
