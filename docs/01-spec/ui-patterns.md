---
id: ui-patterns
domain: spec
tags:
  - ui
  - ux
  - frontend
  - responsive
  - patterns
related:
  - technical-specification
  - buyer-stories
  - seller-stories
  - architecture-structure
---

## Purpose

Document UI/UX patterns implemented for the Mko Bazuna classifieds board. These patterns ensure consistent user experience across mobile, tablet, and desktop while following HTMX-driven MPA architecture.

## Main Concepts

- **Mobile-first responsive:** Grid adapts from 1 to 3 columns; touch targets minimum 44px.
- **Card-first layout:** Ad listings use card-based grids for scannability.
- **HTMX integration:** Interactions avoid full page reloads; server-rendered updates.
- **Telegram-native flow:** Contact actions deep-link to bot without exposing seller PII.

## Responsive Grid Layout

Ad listings use a responsive CSS Grid that adapts to viewport width:

```html
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
```

| Breakpoint | Columns | Gap |
|------------|---------|-----|
| Mobile (< 640px) | 1 | 16px (24px in some contexts) |
| Tablet (640px–1024px) | 2 | 24px |
| Desktop (> 1024px) | 3 | 24px |

Implementation in [`ads/partials/ad_list.html`](../../src/backend/templates/ads/partials/ad_list.html).

Related user stories: US-B2, US-B8

## Card-Based Ad Display

Ad cards follow a consistent visual hierarchy optimized for quick scanning:

### Structure

1. **Image (top):** Full-width photo with fallback placeholder
2. **Title (below image):** Truncated to 2 lines with `line-clamp-2`
3. **Price:** Prominent blue display (see Price Display Patterns)
4. **Location:** City name badge
5. **Category:** Category name on the same line as location

### Implementation

```html
<article class="bg-white rounded-lg shadow hover:shadow-md transition-shadow">
    <a href="{% url 'ads:detail' ad.id %}" class="block">
        {% if ad.images.first %}
            <img src="{{ ad.images.first.image_url }}" alt="{{ ad.title }}"
                 class="w-full h-48 object-cover rounded-t-lg">
        {% endif %}
        <div class="p-4">
            <h2 class="font-semibold text-lg mb-2 line-clamp-2">{{ ad.title }}</h2>
            {% if ad.price %}
                <p class="text-blue-600 font-bold text-xl mb-2">{{ ad.price }} BAM</p>
            {% endif %}
            <div class="flex justify-between items-center text-xs text-gray-500">
                <span>{{ ad.city.get_name|default:ad.city.name }}</span>
                <span>{{ ad.category.get_name|default:ad.category.name }}</span>
                <time datetime="{{ ad.published_at|date:'Y-m-d' }}">
                    {{ ad.published_at|date:'M d' }}
                </time>
            </div>
        </div>
    </a>
</article>
```

Related user stories: US-B4

## Price Display Patterns

Price is the primary decision factor in classifieds. Visual treatment:

| Context | Location | Color | Size |
|---------|----------|-------|------|
| Ad list card | Below title | `text-blue-600` | `text-xl` |
| Ad detail page | Below title | `text-blue-600` | `text-3xl` |
| Seller dashboard | Below title | `text-blue-600` | `font-bold` |

### Notes

- Price shown only when set
- Currency: BAM (Bosnia and Herzegovina Convertible Mark)
- Always uses `text-blue-600` class for prominence
- Position: Second visual element after title

Related user stories: US-B4

## Contact Seller Button

The contact mechanism preserves seller anonymity while enabling communication through Telegram.

### Deep-link Format

```
https://t.me/<bot_username>?start=contact_<ad_id>
```

### Render Conditions

Button renders only when ALL conditions are met:

- Ad status = `PUBLISHED`
- Seller `telegram_id` is not NULL
- Seller is not `is_deleted` or `is_banned`
- Seller consent is not revoked

### Implementation

```html
<div class="p-6 border-t bg-gray-50">
    {% if ad|can_contact %}
        <a href="https://t.me/{{ bot_username }}?start=contact_{{ ad.id }}"
           class="inline-block px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium">
            Contact Seller
        </a>
    {% else %}
        <button type="button" 
                class="px-6 py-3 bg-gray-400 text-white rounded-lg font-medium cursor-not-allowed"
                disabled>
            Contact Seller
        </button>
        <p class="text-xs text-gray-500 mt-2">Seller unavailable for contact</p>
    {% endif %}
</div>
```

The `can_contact` template filter enforces zone R2 conditions.

Related user stories: US-B5

## Image Gallery for Ad Detail Page

Ad detail pages display 1-5 Telegram photos. Each photo is wrapped in a GLightbox v3.3.1 anchor
opening a fullscreen gallery (`components` loaded from the unpkg CDN, inline init). Images render in
`AdImage.position` order (the `{% for image in ad.images.all %}` iteration uses the model default
ordering). The static grid remains intact as a no-JS fallback (progressive enhancement).

### Implementation

```html
<div class="grid grid-cols-1 {% if ad.images.count > 1 %}md:grid-cols-2{% endif %} gap-2 p-4">
    {% for image in ad.images.all %}
        <a href="{{ image.image_url }}" class="glightbox" data-gallery="ad-gallery"
           data-description="{{ image.alt_text|default:"" }}" aria-label="Open image {{ forloop.counter }}">
            <img src="{{ image.thumbnail_large_url|default:image.image_url }}" alt="Photo {{ forloop.counter }}"
                 class="w-full {% if ad.images.count == 1 %}max-h-96{% else %}h-64{% endif %} object-cover rounded-lg">
        </a>
    {% endfor %}
</div>
```

The GLightbox CSS is loaded in `<head>`:

```html
<link rel="stylesheet" href="https://unpkg.com/glightbox@3.3.1/dist/css/glightbox.min.css">
```

The GLightbox JS and inline init are added before `</body>` (relying on the library's built-in
counter and prev/next/zoom/swipe defaults — no custom counter option):

```html
<script src="https://unpkg.com/glightbox@3.3.1/dist/js/glightbox.min.js" defer></script>
<script>
  document.addEventListener('DOMContentLoaded', function () {
    GLightbox({
      selector: '.glightbox',
      touchNavigation: true,
      loop: true,
      zoomable: true,
      closeOnOutsideClick: true,
      navigation: { next: true, prev: true },
    });
  });
</script>
```

### Behavior

- Clicking any image opens the GLightbox overlay with the full `image.image_url`.
- Prev/next arrows, dark backdrop, image counter, ESC/backdrop click to close, arrow-key/Tab
  navigation, mobile swipe and pinch-zoom (per GLightbox defaults).
- **Progressive enhancement:** with JavaScript disabled, the original static grid still renders with
  valid thumbnails and working links — no broken markup.
- **CSP:** CSP is report-only in this codebase; the unpkg CDN load and GLightbox inline styles are
  already allowed (unpkg is also used for HTMX). No `script-src`/`style-src` settings were added.

This supersedes the earlier phase-1 statement of "no lightbox/modal; static grid only".

Related user stories: US-S2

## Shared Navigation Headers

The site uses **two header variants** rather than a single monolithic header. Both
are server-rendered Django include fragments and share a global context processor
(`apps.core.context_processors.header_context`) that injects `bot_username`
(the Telegram deep-link target), `root_categories` (ordered top-level
`Category` nodes for the "All Categories" dropdown), and
`favorites_count` (the authenticated user's favorited-ad count, for the header
badge; `None` for anonymous).

| Header | Template | Used on |
|--------|----------|---------|
| **Catalog header** | `components/header_catalog.html` | `ads/list.html`, `ads/detail.html` |
| **Auth header** | `components/header.html` | `ads/dashboard.html`, `ads/edit.html`, `cabinet/*`, `analytics/*`, `users/login_issue.html` |

### Catalog Header (`header_catalog.html`)

An Avito-style header hosting the place-an-ad CTA, an "All Categories"
accordion dropdown, a search bar with a grouped HTMX autocomplete,
breadcrumbs, and an **auth/cabinet entry** in the top-right corner (see
§Auth Entry in Catalog Header below). HTMX 1.9.12 is loaded in the `<head>` of `list.html` and
`detail.html` (the autocomplete relies on `htmx:afterRequest` events).

```html
<header class="bg-white shadow-sm border-b">
    <div class="container mx-auto px-4 py-3">
        <!-- Top row: mobile hamburger + brand | place-an-ad + language -->
        <div class="flex items-center justify-between gap-4">
            <div class="flex items-center gap-2">
                <button type="button" class="lg:hidden p-2 -ml-2"
                        data-mobile-categories-toggle aria-label="Categories">…</button>
                <h1 class="text-xl font-bold text-gray-800">
                    <a href="/">Mko Bazuna</a>
                </h1>
            </div>
            <div class="flex items-center gap-2">
                {% include "components/header_favorites_badge.html" %}
                {% include "components/header_auth_entry.html" %}
                <a href="https://t.me/{{ bot_username }}?start=create_ad" target="_blank"
                   class="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg"
                   data-place-ad>+ Подать объявление</a>
                {% include "components/language_switcher.html" %}
            </div>
        </div>

        <!-- Search row: "All Categories" dropdown + HTMX autocomplete search -->
        <div class="mt-3">
            <div class="flex gap-2 items-stretch">
                <div class="relative hidden md:block" data-categories-trigger>
                    <button type="button" data-categories-toggle>…</button>
                    <div data-categories-panel class="absolute z-[90] hidden">
                        {% for cat in root_categories %}
                            <li data-category-slug="{{ cat.slug }}">
                                <a href="{% url 'ads:listings_category' cat.slug %}"
                                   data-category-link="{{ cat.slug }}">{{ cat.get_name }}</a>
                                {% if cat.get_children_count %}
                                    <button data-category-expand="{{ cat.slug }}">…</button>
                                    <div data-category-submenu="{{ cat.slug }}" class="hidden"></div>
                                {% endif %}
                            </li>
                        {% endfor %}
                    </div>
                </div>
                <form method="get" action="{% url 'search:search' %}" class="relative flex-1"
                      data-search-form>
                    <input type="search" name="q" value="{{ query|default:'' }}"
                           hx-get="{% url 'search:autocomplete' %}"
                           hx-trigger="input delay:300ms"
                           hx-target="#autocomplete-dropdown"
                           hx-swap="none" autocomplete="off">
                    <ul id="autocomplete-dropdown"
                        class="absolute z-20 w-full hidden">
                    </ul>
                </form>
            </div>
        </div>

        <!-- Breadcrumbs -->
        {% include "components/breadcrumb.html" with breadcrumb_category=current_cat %}
    </div>
</header>
```

### Catalog Header — Component behavior

- **Place-an-ad CTA:** Opens the Telegram bot deep-link
  `https://t.me/{{ bot_username }}?start=create_ad` in a new tab. Uses the
  `bot_username` context variable (never references `settings.BOT_USERNAME`
  directly).
- **"All Categories" dropdown (desktop):** Lazy-loading accordion. The panel
  is rendered server-side with top-level `root_categories`; submenus are
  fetched via `GET /categories/<slug>/submenu/` on first expand and injected
  via HTMX swap.
- **Mobile off-canvas:** Same category tree in a slide-over panel toggled by
  `data-mobile-categories-toggle`; closes on backdrop click or Escape.
- **Search bar:** HTMX-powered autocomplete — `input delay:300ms` triggers
  `GET search:autocomplete`; the response JSON (`{ query, suggestions: [] }`)
  is rendered into `#autocomplete-dropdown` by inline vanilla JS. Suggestion
  items carry `data-suggestion-type` / `data-suggestion-text` /
  `data-suggestion-slug` attributes for click-to-navigate behavior.
- **Breadcrumbs:** `components/breadcrumb.html`, included with
  `breadcrumb_category` (listings/search) or `ad.category` (detail).

### Auth Entry in Catalog Header (R-06, Spec 24)

The catalog header includes an auth/cabinet entry in the top-right corner
(to the left of the "Place an ad" CTA), per PO clarification (2026-08-20).
This corrects the previous Spec-14 R-05c which excluded auth nav.

- **Anonymous:** icon-only outline UserIcon (44px) -> `/login/issue/`
- **Authenticated:** filled avatar/icon button (44px) with dropdown menu
  (Cabinet, My Ads, Favorites, Settings, Logout; Admin if staff; POST+CSRF logout)
- **Favorites badge:** heart icon + count; outline for anonymous, filled+count for authenticated
- **Mobile:** always visible top-right; category hamburger stays separate
- **Dropdown:** vanilla JS toggle (no `hx-on`); closes on click-outside, Escape, HTMX configRequest

See `24_catalog-header-auth-entry_spec.md` for full requirements.

### Auth Header (`header.html`)

A simpler auth-aware header for dashboard and cabinet pages. Does not
include search, categories, or breadcrumbs.

```html
<header class="bg-white shadow-sm border-b">
    <div class="container mx-auto px-4 py-4 flex items-center justify-between">
        <h1 class="text-2xl font-bold text-gray-800">
            <a href="{% url 'ads:listings' %}">Mko Bazuna</a>
        </h1>
        {% include "components/language_switcher.html" %}
        <nav class="flex gap-4 items-center">
            {% if request.user.is_authenticated %}
                <a href="{% url 'cabinet:home' %}">Cabinet</a>
                <a href="{% url 'ads:dashboard' %}">Dashboard</a>
                {% if request.user.is_staff %}
                    <a href="/admin/">Admin</a>
                {% endif %}
                <form method="post" action="{% url 'consent:logout' %}" class="inline">
                    {% csrf_token %}
                    <button type="submit">Logout</button>
                </form>
            {% else %}
                <a href="{% url 'consent:login_issue' %}">Login</a>
            {% endif %}
        </nav>
    </div>
</header>
```

### Auth Header — Component behavior

- **Branding:** Logo links to the home listings page (`ads:listings`).
- **Language switcher:** Always rendered via `components/language_switcher.html`.
- **Anonymous visitors:** See a "Login" link to `consent:login_issue`.
- **Authenticated sellers:** See "Cabinet" (`cabinet:home`), "Dashboard"
  (`ads:dashboard`), and a **POST + CSRF** "Logout" form posting to
  `consent:logout` (GET logout is not allowed — POST only, per CR4).
- **Staff users:** Additionally see an "Admin" link to `/admin/` (CR7).

### Classes

- `bg-white`: White background
- `shadow-sm`: Subtle shadow for depth
- `border-b`: Bottom border for separation
- `container mx-auto px-4 py-3`: Constrained width with horizontal padding (catalog header uses `py-3`; auth header uses `py-4`)

The consent banner is **not** part either header — it renders at the bottom of
each page behind its per-page guard (CR9). Page-specific titles live in each
page's `<main>`.

Related user stories: US-B8, US-S8, US-S1

## Touch Target Guidelines

Interactive elements must meet WCAG minimum touch target size:

| Element | Minimum Size | Implementation |
|---------|--------------|----------------|
| Buttons | 44px height | `py-3` (24px padding) + min-height implicit |
| Form inputs | 44px height | `py-2` + font-size provides adequate target |
| Links | 44px tall | Padding and line-height ensure tap area |
| Checkboxes/Radio | 44px × 44px | Not currently used in UI |

### Examples from Templates

- Search button: `px-6 py-2 bg-blue-600` (40px height with padding)
- Contact button: `px-6 py-3 bg-blue-600` (46px height, meets 44px minimum)
- Consent banner buttons: `px-4 py-2` (36px height, needs review)

Related user stories: US-B8

## Progressive Disclosure Patterns

Mobile-first interaction patterns for progressive disclosure:

### Description Truncation

Ad descriptions truncate after 3 lines on listing, full display on detail:

```html
<p class="text-sm text-gray-600 line-clamp-3 mb-3">{{ ad.description }}</p>
```

CSS `line-clamp-3` applies `-webkit-line-clamp: 3` with `display: -webkit-box` and `overflow: hidden`.

### Empty States

Friendly empty states with guidance:

```html
<div class="text-center py-12 bg-white rounded-lg">
    <p class="text-gray-600 text-lg">No ads available</p>
    <p class="text-gray-500 mt-2">Be the first to create an ad via Telegram!</p>
</div>
```

### Filter Suggestions

Did-you-mean suggestions appear inline without page reload:

```html
{% if suggested_city %}
    <div class="mb-4 p-3 bg-blue-50 rounded-lg">
        <p class="text-sm text-blue-800">
            Did you mean: <a href="...">{{ suggested_city }}</a>?
        </p>
    </div>
{% endif %}
```

HTMX-powered pagination (`hx-get`, `hx-target`, `hx-swap`) provides progressive disclosure for search results without full page navigation.

Related user stories: US-B2, US-B3, US-B8

## Implementation Notes

- All patterns use Django templates with Tailwind CSS utility classes
- No client-side JavaScript frameworks; HTMX for interactivity
- Images are Telegram-compressed; no server-side optimization in phase 1
- See [`architecture-structure.md`](./architecture-structure.md) for technical architecture