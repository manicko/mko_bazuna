---
id: design-system-components
domain: design-system
tags:
  - components
  - buttons
  - cards
  - forms
  - navigation
related:
  - design-system-index
  - tokens
  - ui-patterns
---

# Component Catalog

> Atomic design component patterns with code examples. All components use tokens from `tokens.md`.

## Atomic Components

### Buttons

Primary interactive elements for all CTAs.

#### Primary Button

Main actions, form submissions, save.

```html
<button type="submit" class="px-6 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2">
    Save Changes
</button>
```

| Property | Value |
|----------|-------|
| Background | `bg-blue-600` (Primary token) |
| Text | `text-white` |
| Hover | `hover:bg-blue-700` |
| Size | 40px height (`px-6 py-2`) |
| Pages | All templates |

#### Success Button

Approve actions, positive confirmations.

```html
<button type="submit" class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2">
    Approve
</button>
```

| Property | Value |
|----------|-------|
| Background | `bg-green-600` (Success token) |
| Text | `text-white` |
| Hover | `hover:bg-green-700` |
| Size | 40px height (`px-4 py-2`) |
| Pages | `admin/moderation/review.html` |

#### Danger Button

Reject actions, destructive operations.

```html
<button type="submit" class="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2">
    Reject
</button>
```

| Property | Value |
|----------|-------|
| Background | `bg-red-600` (Error token) |
| Text | `text-white` |
| Hover | `hover:bg-red-700` |
| Size | 40px height (`px-4 py-2`) |
| Pages | `admin/moderation/review.html` |

#### Secondary Button

Cancel, back navigation, alternative actions.

```html
<a href="{% url 'ads:dashboard' %}" class="px-6 py-2 bg-white text-gray-700 rounded-lg font-medium border border-gray-300 hover:bg-gray-50 transition-colors focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2">
    Cancel
</a>
```

| Property | Value |
|----------|-------|
| Background | `bg-white` |
| Text | `text-gray-700` |
| Border | `border-gray-300` |
| Hover | `hover:bg-gray-50` |
| Size | 40px height (`px-6 py-2`) |
| Pages | `ads/edit.html`, `ads/dashboard.html` |

#### Disabled Button

Unavailable actions, read-only states.

```html
<button type="button" disabled class="px-6 py-3 bg-gray-300 text-white rounded-lg font-medium cursor-not-allowed">
    Contact Seller
</button>
```

| Property | Value |
|----------|-------|
| Background | `bg-gray-300` |
| Text | `text-white` |
| Cursor | `cursor-not-allowed` |
| Size | 48px height (`px-6 py-3`) |
| Pages | `ads/detail.html`, `components/consent_banner.html` |

#### Icon Button

Close modals, drawer triggers.

```html
<button type="button" class="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-gray-500" aria-label="Close">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
    </svg>
</button>
```

| Property | Value |
|----------|-------|
| Size | 40px × 40px (`p-2` + 20px icon) |
| Icon | 20px (`w-5 h-5`) |
| Focus | `focus:ring-2 focus:ring-gray-500` |
| Required | `aria-label` |
| Pages | `admin/review.html` |

### Form Inputs

Text, number, and textarea inputs with validation states.

#### Text Input

```html
<div class="mb-4">
    <label for="title" class="block font-medium mb-2">Title</label>
    <input 
        type="text" 
        id="title" 
        name="title"
        maxlength="200"
        required
        class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
    >
</div>
```

| Property | Value |
|----------|-------|
| Height | 40px (`py-2` + font) |
| Border | `border-gray-300` |
| Focus | `ring-2 ring-blue-500` |
| Pages | `ads/edit.html` |

#### Textarea

```html
<div class="mb-4">
    <label for="description" class="block font-medium mb-2">Description</label>
    <textarea 
        id="description" 
        name="description"
        rows="6"
        required
        class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
    >{{ ad.description }}</textarea>
</div>
```

| Property | Value |
|----------|-------|
| Resize | `resize-y` (vertical only) |
| Pages | `ads/edit.html`, `admin/review.html` |

#### Number Input (Price)

```html
<div class="mb-4">
    <label for="price_amount" class="block font-medium mb-2">Price</label>
    <div class="flex gap-2">
        <input
            type="number"
            id="price_amount"
            name="price_amount"
            min="0"
            step="0.01"
            placeholder="Amount"
            class="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
        <select id="price_currency" name="price_currency" class="px-3 py-2 border border-gray-300 rounded-lg">
            <option value="EUR">EUR</option>
            <option value="RSD">RSD</option>
            <option value="BAM">BAM</option>
        </select>
    </div>
</div>
```

| Property | Value |
|----------|-------|
| Step | `0.01` (currency precision) |
| Pages | `ads/edit.html`, filter price range |

#### Error State

```html
<div class="mb-4">
    <label for="title" class="block font-medium mb-2">Title</label>
    <input 
        type="text" 
        id="title" 
        name="title"
        class="w-full px-3 py-2 border border-red-500 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500"
        aria-invalid="true"
        aria-describedby="title-error"
    >
    <p id="title-error" class="mt-1 text-sm text-red-600">Title is required</p>
</div>
```

| Property | Value |
|----------|-------|
| Border | `border-red-500` |
| Focus | `ring-2 ring-red-500` |
| Error text | `text-red-600` |
| ARIA | `aria-invalid`, `aria-describedby` |

### Badges

Status indicators and category tags.

#### Published Status

```html
<span class="px-2 py-1 bg-green-100 text-green-800 rounded text-xs font-medium">
    Published
</span>
```

| Property | Value |
|----------|-------|
| Shape | `rounded` (4px) |
| Background | `bg-green-100` |
| Text | `text-green-800` |
| Pages | `ads/dashboard.html` |

#### Pending Status

```html
<span class="px-2 py-1 bg-yellow-100 text-yellow-800 rounded text-xs font-medium">
    Pending Review
</span>
```

| Property | Value |
|----------|-------|
| Background | `bg-yellow-100` |
| Text | `text-yellow-800` |
| Pages | `ads/dashboard.html` |

#### Rejected/Failed Status

```html
<span class="px-3 py-1 bg-yellow-100 text-yellow-800 rounded-full text-sm font-semibold">
    {{ ad.get_status_display }}
</span>
```

| Property | Value |
|----------|-------|
| Shape | `rounded-full` (pill) |
| Background | `bg-yellow-100` |
| Text | `text-yellow-800` |
| Pages | `admin/review.html` |

#### Category Badge

```html
<span class="inline-flex items-center px-3 py-1 rounded-full text-sm bg-blue-100 text-blue-800">
    Electronics
    <button class="ml-2 text-blue-600 hover:text-blue-800" aria-label="Remove">×</button>
</span>
```

| Property | Value |
|----------|-------|
| Shape | `rounded-full` |
| Background | `bg-blue-100` |
| Text | `text-blue-800` |
| Pages | `filter-ui.md` |

---

## Molecular Components

### Search Bar

Combined input and button for keyword search.

```html
<form method="get" class="flex gap-2">
    <div class="relative flex-1">
        <input 
            type="search" 
            name="q" 
            placeholder="Search ads..."
            class="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            aria-label="Search listings"
        >
        <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 1114 7 7 0 01-14-14z"></path>
        </svg>
    </div>
    <button type="submit" class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium">
        Search
    </button>
</form>
```

| Property | Value |
|----------|-------|
| Height | 40px |
| Icon size | `w-5 h-5` (20px) |
| Pages | `ads/list.html` |

### Price Display

Prominent price presentation with currency.

```html
<!-- List price (rendered via shared format_price filter; EUR is default) -->
<p class="text-blue-600 font-bold text-xl mb-2">{{ ad|format_price }}</p>

<!-- Detail price -->
<p class="text-blue-600 font-bold text-3xl mb-4">{{ ad|format_price }}</p>

<!-- With label -->
<div>
    <span class="text-sm text-gray-500">Price</span>
    <p class="text-blue-600 font-bold text-xl">{{ ad|format_price }}</p>
</div>
```

| Context | Size | Color |
|---------|------|-------|
| List card | `text-xl` | `text-blue-600` |
| Detail page | `text-3xl` | `text-blue-600` |

---

## Organism Components

### Ad Card (List View)

Primary listing card for search results.

```html
<article class="bg-white rounded-lg shadow hover:shadow-md transition-shadow">
    <a href="{% url 'ads:detail' ad.id %}" class="block">
        {% if ad.images.first %}
            <img 
                src="{{ ad.images.first.image_url }}" 
                alt="{{ ad.title }}"
                class="w-full h-48 object-contain bg-white rounded-t-lg"
                loading="lazy"
            >
        {% else %}
            <div class="w-full h-48 bg-gray-200 rounded-t-lg flex items-center justify-center">
                <span class="text-gray-500 text-sm">No image</span>
            </div>
        {% endif %}
        
        <div class="p-4">
            <h2 class="font-semibold text-lg text-gray-800 mb-2 line-clamp-2">
                {{ ad.title }}
            </h2>
            
            {% if ad.price_amount %}
                <p class="text-blue-600 font-bold text-xl mb-2">
                    {{ ad|format_price }}
                </p>
            {% endif %}
            
            <p class="text-sm text-gray-600 mb-3 line-clamp-3">
                {{ ad.description }}
            </p>
            
            <div class="flex justify-between items-center text-xs text-gray-500">
                <span>{{ ad.city|get_city_name:LANGUAGE_CODE }}</span>
                <span>{{ ad.category|get_category_name:LANGUAGE_CODE }}</span>
                <time datetime="{{ ad.published_at|date:'Y-m-d' }}">
                    {{ ad.published_at|date:'M d' }}
                </time>
            </div>
        </div>
    </a>
</article>
```

| Property | Value |
|----------|-------|
| Image | `w-full h-48 object-contain bg-white rounded-t-lg` |
| Padding | `p-4` |
| Radius | `rounded-lg` (except image top) |
| Shadow | `shadow` → `hover:shadow-md` |
| Pages | `ads/partials/ad_list.html` |

### Ad Card (Detail View)

Full-width single ad display. Photo gallery uses a **slider gallery** pattern
(main image + horizontal thumbnail strip + arrow nav) with **GLightbox v3.3.1**
(CDN) for fullscreen overlay. GLightbox JS is consent-gated behind
`consent_analytics`; without consent the main image anchor still links to the
full-size photo as a plain fallback. Content is localized via
`get_title`/`get_description` template filters keyed on `LANGUAGE_CODE`.

```html
<article class="bg-white rounded-lg shadow overflow-hidden">
    <!-- Photo gallery (GLightbox slider) -->
    {% if ad.images.all %}
    <div class="gallery p-4" data-detail-gallery>
        {% with primary=ad.images.first %}
        <div class="relative mb-4">
            <a id="detail-main-link" href="{{ primary.image_url }}" class="glightbox"
               data-gallery="ad-gallery" aria-label="{% trans "Open image" %} 1">
                <img id="detail-main-image"
                     src="{{ primary.thumbnail_large_url|default:primary.image_url }}"
                     alt="{% trans "Photo" %} {% trans "of" %} {{ ad|get_title:LANGUAGE_CODE }}"
                     class="w-full max-h-96 object-contain bg-gray-100 rounded-lg"
                     loading="lazy" width="1280" height="960">
            </a>
            {% if ad.images.count > 1 %}
            <button id="detail-prev" type="button" aria-label="{% trans "Previous image" %}">…</button>
            <button id="detail-next" type="button" aria-label="{% trans "Next image" %}">…</button>
            {% endif %}
        </div>
        {% if ad.images.count > 1 %}
        {% for image in ad.images.all %}{% if not forloop.first %}
        <a href="{{ image.image_url }}" class="glightbox" data-gallery="ad-gallery" style="display:none;"></a>
        {% endif %}{% endfor %}
        {% endif %}
        <div id="detail-thumbs" class="flex gap-2 overflow-x-auto" data-detail-thumbs>
            {% for image in ad.images.all %}
            <button type="button" data-index="{{ forloop.counter0 }}"
                    data-full-url="{{ image.image_url }}"
                    data-thumb-url="{{ image.thumbnail_large_url|default:image.image_url }}">
                <img src="{{ image.thumbnail_small_url|default:image.image_url }}"
                     alt="{% trans "Photo" %} {{ forloop.counter }}"
                     class="w-full h-full object-cover">
            </button>
            {% endfor %}
        </div>
    </div>
    {% endif %}

    <!-- Content -->
    <div class="p-6">
        <div class="flex items-start justify-between gap-4">
            <h1 class="text-3xl font-bold mb-4">
                {{ ad|get_title:LANGUAGE_CODE }}
                {% render_trust_badge ad.user %}
            </h1>
            {% include "components/favorite_heart.html" with ad=ad is_favorited=is_favorited %}
        </div>

        {% if ad.price_amount %}
            <p class="text-blue-600 font-bold text-3xl mb-4">{{ ad|format_price }}</p>
        {% endif %}

        <div class="mb-6">
            <p class="text-gray-700 whitespace-pre-wrap">{{ ad|get_description:LANGUAGE_CODE }}</p>
        </div>

        <div class="flex flex-wrap gap-4 text-sm text-gray-600 border-t pt-4">
            <div><span class="font-medium">Location:</span> {{ ad.city|get_city_name:LANGUAGE_CODE }}</div>
            <div><span class="font-medium">Category:</span> {{ ad.category|get_category_name:LANGUAGE_CODE }}</div>
            <div><time datetime="{{ ad.published_at|date:'Y-m-d' }}">Published: {{ ad.published_at|date:'M d, Y' }}</time></div>
        </div>
    </div>

    <!-- Contact Seller -->
    <div class="p-6 border-t bg-gray-50">
        {% if ad|can_contact %}
            <a href="https://t.me/{{ bot_username }}?start=contact_{{ ad.id }}"
               class="inline-block px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium">
                Contact Seller
            </a>
        {% else %}
            <button type="button" disabled
                    class="px-6 py-3 bg-gray-300 text-white rounded-lg font-medium cursor-not-allowed">
                Contact Seller
            </button>
            <p class="text-xs text-gray-500 mt-2">Seller unavailable for contact</p>
        {% endif %}
    </div>
</article>

     <!-- GLightbox init (consent-gated) + thumbnail-switching inline JS -->
     {% if consent_analytics %}
     <script src="https://unpkg.com/glightbox@3.3.1/dist/js/glightbox.min.js" defer></script>
     <script>
         document.addEventListener('DOMContentLoaded', function () {
             var gallery = document.querySelector('[data-detail-gallery]');
             if (!gallery) return;
             var mainImg = gallery.querySelector('#detail-main-image');
             var mainLink = gallery.querySelector('#detail-main-link');
             var thumbs = gallery.querySelectorAll('[data-detail-thumbs] button[data-index]');
             var idx = 0;
             function updateMain(i) {
                 var t = thumbs[i]; if (!t) return;
                 idx = i;
                 mainImg.src = t.dataset.thumbUrl;
                 mainImg.alt = '{% trans "Photo" %} ' + (i + 1) + ' {% trans "of" %} ' + thumbs.length;
                 mainLink.href = t.dataset.fullUrl;
             }
             thumbs.forEach(function (b, i) { b.addEventListener('click', function () { updateMain(i); }); });
             gallery.querySelector('#detail-prev')?.addEventListener('click', function () { updateMain((idx - 1 + thumbs.length) % thumbs.length); });
             gallery.querySelector('#detail-next')?.addEventListener('click', function () { updateMain((idx + 1) % thumbs.length); });
             GLightbox({ selector: '.glightbox', touchNavigation: true, loop: true, zoomable: true, closeOnOutsideClick: true, navigation: { next: true, prev: true } });
         });
     </script>
     {% endif %}
     ```

| Property | Value |
|----------|-------|
| Gallery | Main image (`object-contain` + `bg-gray-100`) + horizontal thumbnail strip (`object-cover`) + GLightbox 3.3.1 overlay |
| Gallery ID | `ad-gallery` (single gallery per ad) |
| Main image | `object-contain`, `bg-gray-100` (`#detail-main-image`) |
| Thumbnails | `object-cover` (`#detail-thumbs` buttons) |
| Thumbnail | `image.thumbnail_large_url` (fallback: `image.image_url`) |
| Lazy load | `loading="lazy"` on all images |
| Title | `ad|get_title:LANGUAGE_CODE` |
| Description | `ad|get_description:LANGUAGE_CODE` |
| Contact button | `bot_username` context var (never `settings.BOT_USERNAME`) |
| Pages | `ads/detail.html` |

### Shared Navigation Headers

Two header variants share a global context processor (`apps.core.context_processors.header_context`,
see [architecture-structure.md](architecture-structure.md#middleware--context-processors))
that injects `bot_username`, `root_categories`, `preferred_city_display`, `cities`, and
`favorites_count`. Consent state (`consent_shown`, `consent_analytics`,
`consent_preferences`) is provided by `apps.users.context_processors.consent_state`. Both
headers are rendered as Django include fragments.

| Header | Template | Used on |
|--------|----------|---------|
| **Catalog header** | `components/header_catalog.html` | `ads/list.html`, `ads/detail.html` |
| **Auth header** | `components/header.html` | `ads/dashboard.html`, `ads/edit.html`, `cabinet/*`, `analytics/*`, `users/login_issue.html` |

#### Catalog Header (`header_catalog.html`)

Avito-style catalog header: place-an-ad CTA, preferred-city selector, "All Categories"
accordion dropdown, HTMX autocomplete search, breadcrumbs, and auth/cabinet entry with a
favorites badge. Submenus load via vanilla `fetch` (not HTMX); expand buttons render
when `cat.get_children.exists`. Full behavior documented in
[UI Patterns — Shared Navigation Headers](../01-spec/ui-patterns.md#shared-navigation-headers).

```html
<header class="bg-white shadow-sm border-b">
    <div class="container mx-auto px-4 py-3">
        <!-- Top row: hamburger + brand | favorites + auth + place-an-ad + language -->
        <div class="flex items-center justify-between gap-4">
            <div class="flex items-center gap-2">
                <button type="button" class="lg:hidden" data-mobile-categories-toggle>…</button>
                <a href="/">Mko Bazuna</a>
            </div>
            <div class="flex items-center gap-2">
                {% include "components/header_favorites_badge.html" %}
                {% include "components/header_auth_entry.html" %}
                <a href="https://t.me/{{ bot_username }}?start=create_ad" target="_blank"
                   class="px-4 py-2 bg-blue-600 text-white rounded-lg" data-place-ad>+ Подать объявление</a>
                {% include "components/language_switcher.html" %}
            </div>
        </div>

        <!-- Search row: city selector + categories dropdown + autocomplete search -->
        <div class="mt-3">
            <div class="flex gap-2 items-stretch">
                <!-- Preferred-city selector -->
                <div class="relative" data-preferred-city-trigger>
                    <button type="button" data-preferred-city-toggle aria-haspopup="listbox">
                        📍 <span data-preferred-city-label>{{ preferred_city_display }}</span>
                    </button>
                    <div data-preferred-city-panel class="absolute z-[90] hidden">
                        <button type="button" data-city-clear>Вся страна</button>
                        {% for city in cities %}
                        <button type="button" data-city-option="{{ city.slug }}">{{ city.get_name }}</button>
                        {% endfor %}
                    </div>
                </div>
                <!-- Categories accordion (submenus loaded via fetch, not HTMX) -->
                <div class="relative hidden md:block" data-categories-trigger>
                    <button type="button" data-categories-toggle>…</button>
                    <div data-categories-panel class="absolute z-[90] hidden">
                        {% for cat in root_categories %}
                        <li data-category-slug="{{ cat.slug }}">
                            <a href="{% url 'ads:listings_category' cat.slug %}">{{ cat.get_name }}</a>
                            {% if cat.get_children.exists %}
                            <button type="button" data-category-expand="{{ cat.slug }}">…</button>
                            <div data-category-submenu="{{ cat.slug }}" class="hidden"></div>
                            {% endif %}
                        </li>
                        {% endfor %}
                    </div>
                </div>
                <form method="get" action="{% url 'search:search' %}" class="relative flex-1" data-search-form>
                    <input type="search" name="q"
                           hx-get="{% url 'search:autocomplete' %}"
                           hx-trigger="input delay:300ms"
                           hx-target="#autocomplete-dropdown" hx-swap="none" autocomplete="off">
                    <ul id="autocomplete-dropdown" class="absolute z-20 hidden"></ul>
                </form>
            </div>
        </div>

        {% include "components/breadcrumb.html" with breadcrumb_category=current_cat %}
    </div>
</header>
```

| Property | Value |
|----------|-------|
| Height (mobile) | `py-3` (~52px top row) |
| City selector | `data-preferred-city-toggle`; POST `search:preferred_city` (cookie for guests, `User.preferred_city` on login) |
| Search | HTMX autocomplete, 300ms delay |
| Categories | Desktop accordion + mobile off-canvas; submenus via `GET /categories/<slug>/submenu/` (vanilla fetch → innerHTML) |
| Expand buttons | rendered when `cat.get_children.exists` |
| Auth entry | `header_auth_entry.html` (anonymous → login; authed → avatar dropdown) |
| Favorites badge | `header_favorites_badge.html` (outline for anon, filled+count for authed) |
| Breadcrumbs | `components/breadcrumb.html` |
| Deep-link | `bot_username` context var |

#### Auth Header (`header.html`)

Simpler auth-aware header for dashboard/cabinet pages. No search, categories, or breadcrumbs.

```html
<header class="bg-white shadow-sm border-b">
    <div class="container mx-auto px-4 py-4 flex items-center justify-between">
        <h1 class="text-2xl font-bold text-gray-800">
            <a href="{% url 'ads:listings' %}">Mko Bazuna</a>
        </h1>
        {% include "components/language_switcher.html" %}
        <nav class="flex gap-4 items-center">
            {% if request.user.is_authenticated %}
                <a href="{% url 'cabinet:home' %}" class="text-sm text-gray-700 hover:text-blue-600">Cabinet</a>
                <a href="{% url 'ads:dashboard' %}" class="text-sm text-gray-700 hover:text-blue-600">Dashboard</a>
                {% if request.user.is_staff %}
                    <a href="/admin/" class="text-sm text-gray-700 hover:text-blue-600">Admin</a>
                {% endif %}
                <form method="post" action="{% url 'consent:logout' %}" class="inline">
                    {% csrf_token %}
                    <button type="submit" class="text-sm text-gray-600 hover:text-red-600">Logout</button>
                </form>
            {% else %}
                <a href="{% url 'consent:login_issue' %}" class="text-sm text-gray-700 hover:text-blue-600">Login</a>
            {% endif %}
        </nav>
    </div>
</header>
```

| Property | Value |
|----------|-------|
| Background | `bg-white` |
| Height | ~64px (`py-4`) |
| Shadow | `shadow-sm border-b` |
| Auth nav | Login (anon) / Cabinet + Dashboard + POST Logout (authed), Admin (staff only) |
| Logout | POST + CSRF to `consent:logout` (no GET logout) |
| Pages | Dashboard, cabinet, edit, login

### Pagination Controls

HTMX-powered page navigation.

```html
<nav class="mt-8 flex justify-center gap-1" aria-label="Page navigation">
    {% if page_obj.has_previous %}
        <a href="?page=1" 
           hx-get="?page=1" 
           hx-target="#ad-list" 
           hx-swap="innerHTML"
           class="px-3 py-2 rounded-lg text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50">
            ««
        </a>
        <a href="?page={{ page_obj.previous_page_number }}" 
           class="px-3 py-2 rounded-lg text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50">
            «
        </a>
    {% endif %}
    
    <!-- Page numbers -->
    {% for page_num in page_obj.paginator.page_range %}
        {% if page_num == page_obj.number %}
            <span class="px-3 py-2 rounded-lg text-sm font-medium text-white bg-blue-600" aria-current="page">
                {{ page_num }}
            </span>
        {% elif page_num > page_obj.number|add:'-3' and page_num < page_obj.number|add:'3' %}
            <a href="?page={{ page_num }}" 
               class="px-3 py-2 rounded-lg text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50">
                {{ page_num }}
            </a>
        {% endif %}
    {% endfor %}
    
    {% if page_obj.has_next %}
        <a href="?page={{ page_obj.next_page_number }}" 
           class="px-3 py-2 rounded-lg text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50">
            »
        </a>
        <a href="?page={{ page_obj.paginator.num_pages }}" 
           class="px-3 py-2 rounded-lg text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50">
            »»
        </a>
    {% endif %}
</nav>
```

| Property | Value |
|----------|-------|
| Gap | `gap-1` (4px) |
| Active | `bg-blue-600 text-white` |
| Pages | `ads/partials/ad_list.html` |

### Consent Banner

Privacy consent collection at page bottom.

```html
<div id="consent-banner" class="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 shadow-lg z-50" role="dialog" aria-live="polite" aria-label="Privacy consent">
    <div class="container mx-auto px-4 py-4 flex flex-col sm:flex-row items-center justify-between gap-4">
        <div class="text-sm text-gray-700">
            <p>
                This site uses cookies for essential functionality and analytics. 
                By accepting, you consent to all processing. You can still browse ads without accepting.
            </p>
            <p class="text-xs text-gray-500 mt-1">
                <a href="/privacy/" class="underline hover:text-gray-800 transition-colors">Privacy details</a>
            </p>
        </div>
        
        <div class="flex gap-2">
            <form method="post" action="{% url 'consent:accept' %}" class="inline">
                {% csrf_token %}
                <button type="submit" class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500">
                    Accept
                </button>
            </form>
            <form method="post" action="{% url 'consent:decline' %}" class="inline">
                {% csrf_token %}
                <button type="submit" class="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 font-medium text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-gray-500">
                    Decline (Browse-only)
                </button>
            </form>
        </div>
    </div>
</div>
```

| Property | Value |
|----------|-------|
| Position | Fixed bottom |
| Background | `bg-white` |
| Border | `border-t border-gray-200` |
| Shadow | `shadow-lg` |

### Language Switcher

Multi-language interface for Russian, Bosnian, and English content.

```html
<div class="relative inline-block">
    <button type="button" class="px-3 py-2 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 font-medium text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 flex items-center gap-1" aria-label="Language">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 5h12M9 3v2m0 4v10m4-10v6m4-2h-4m4-2h-4"></path>
        </svg>
        <span id="current-lang" class="lang-flag ru">{{ LANGUAGE_CODE|default:'ru' }}</span>
    </button>
    
    <div class="absolute right-0 mt-2 w-48 bg-white border border-gray-200 rounded-lg shadow-lg z-50 hidden" id="lang-menu">
        <div class="py-1">
            <a href="?lang=ru" class="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 hover:text-gray-900 language-link" data-lang="ru">
                <span class="inline-block w-4 h-4 mr-2 flag-icon flag-ru"></span>
                Russian
            </a>
            <a href="?lang=bs" class="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 hover:text-gray-900 language-link" data-lang="bs">
                <span class="inline-block w-4 h-4 mr-2 flag-icon flag-bs"></span>
                Bosnian
            </a>
            <a href="?lang=en" class="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 hover:text-gray-900 language-link" data-lang="en">
                <span class="inline-block w-4 h-4 mr-2 flag-icon flag-en"></span>
                English
            </a>
        </div>
    </div>
</div>

<script>
document.addEventListener('DOMContentLoaded', function() {
    // Toggle language menu
    document.querySelector('.language-link').addEventListener('click', function(e) {
        e.preventDefault();
        const lang = this.getAttribute('data-lang');
        document.cookie = 'lang_pref=' + lang + '; path=/; max-age=31536000';
        window.location.href = this.href;
    });
});
</script>
```

| Property | Value |
|----------|-------|
| Position | `relative inline-block` |
| Background | `bg-white` |
| Border | `border border-gray-200` |
| Shadow | `shadow-lg` |
| Cookie | Sets `lang_pref` cookie |
| Middleware | Uses `LanguagePreMiddleware` |
| Pages | All templates (header navigation) |

## Component Usage Matrix

| Component | Pages Used | Template | Status |
|-----------|------------|----------|--------|
| Primary Button | All | `edit.html`, `detail.html`, `dashboard.html`, `admin/review.html` | ✅ Implemented |
| Success Button | Admin | `admin/review.html` | ✅ Implemented |
| Danger Button | Admin | `admin/review.html` | ✅ Implemented |
| Secondary Button | Edit, Dashboard | `edit.html`, `dashboard.html` | ✅ Implemented |
| Icon Button | Admin | `admin/review.html` | ✅ Implemented |
| Form Input | Edit | `ads/edit.html` | ✅ Implemented |
| Badge | Dashboard, Admin | `dashboard.html`, `review.html` | ✅ Implemented |
| Ad Card (List) | List, Home | `ads/partials/ad_list.html` | ✅ Implemented |
| Ad Card (Detail) | Detail | `ads/detail.html` | ✅ Implemented |
| Search Bar (HTMX) | Catalog | `ads/list.html` | ✅ Implemented |
| Catalog Header | List, Detail | `ads/list.html`, `ads/detail.html` | ✅ Implemented |
| Auth Header | Dashboards | `ads/dashboard.html`, `cabinet/*`, `analytics/*` | ✅ Implemented |
| Pagination | List | `ads/partials/ad_list.html` | ✅ Implemented |
| Consent Banner | All | `components/consent_banner.html` | ✅ Implemented |
| Language Switcher | All | `components/language_switcher.html` | ✅ Implemented |
| Filter Sidebar | Filter UI | `filter-ui.md` | ✅ Implemented |
| Mobile Drawer | Filter UI | `filter-ui.md` | ✅ Implemented |
| Filter Chips | Filter UI | `filter-ui.md` | ✅ Implemented |