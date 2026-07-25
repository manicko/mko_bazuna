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
        <a href="https://t.me/{{ settings.BOT_USERNAME }}?start=contact_{{ ad.id }}"
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

Ad detail pages display 1-5 Telegram photos in a responsive grid.

### Implementation

```html
<div class="grid grid-cols-1 {% if ad.images.count > 1 %}md:grid-cols-2{% endif %} gap-2 p-4">
    {% for image in ad.images.all %}
        <img src="{{ image.image_url }}" alt="Photo {{ forloop.counter }} for {{ ad.title }}"
             class="w-full {% if ad.images.count == 1 %}max-h-96{% else %}h-64{% endif %} object-cover rounded-lg">
    {% endfor %}
</div>
```

### Behavior

- Single photo: Full width, max-height 96 (24rem/384px)
- Multiple photos: 2-column grid on tablet/desktop
- All photos: 64px height (h-64), object-fit cover
- No lightbox/modal in phase 1; static grid display

Related user stories: US-S2

## Sticky Navigation Header

The header remains visible during scroll with consistent navigation.

### Structure

```html
<header class="bg-white shadow-sm border-b">
    <div class="container mx-auto px-4 py-4">
        <h1 class="text-2xl font-bold text-gray-800">
            <a href="/">Mko Bazuna</a>
        </h1>
    </div>
</header>
```

### Classes

- `bg-white`: White background
- `shadow-sm`: Subtle shadow for depth
- `border-b`: Bottom border for separation
- `container mx-auto px-4 py-4`: Constrained width with horizontal padding

Header height on mobile: `py-4` (32px padding top/bottom). No explicit sticky positioning currently, but shadow and border provide visual anchoring.

Related user stories: US-B8

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