---
id: design-system
domain: spec
tags:
  - design-system
  - ui
  - components
  - patterns
  - tailwind
related:
  - ui-patterns
  - filter-ui
  - technical-specification
---

# Mko Bazuna — Design System

> Component catalog and patterns using Atomic Design methodology with Tailwind CSS.

## Purpose

Provides a structured design system for Mko Bazuna, organizing UI components into atomic, molecular, and organism levels. Based on research from Avito, eBay, and Bunjang marketplace design systems for classifieds platforms.

## Atomic Design Structure

Following Brad Frost's Atomic Design methodology:

| Level | Description | Examples |
|-------|-------------|----------|
| **Atoms** | Fundamental building blocks with single responsibility | Buttons, inputs, labels, icons, badges |
| **Molecules** | Groups of atoms working together | Form fields, search bars, card headers |
| **Organisms** | Complex UI components composed of molecules/atoms | Ad cards, filter sidebar, header navigation |

## Design Tokens

### Color Palette

Based on Tailwind's default palette with marketplace-specific adjustments:

```css
/* Primary Colors */
--color-primary: #2563eb;    /* Blue 600 - Primary actions */
--color-primary-hover: #1d4ed8; /* Blue 700 */
--color-success: #059669;     /* Green 600 - Positive states */
--color-warning: #d97706;     /* Amber 600 - Pending states */
--color-danger: #dc2626;     /* Red 600 - Errors/rejection */

/* Neutral Colors */
--color-text-primary: #1f2937;  /* Gray 800 */
--color-text-secondary: #6b7280; /* Gray 500 */
--color-text-tertiary: #9ca3af; /* Gray 400 */
--color-background: #f9fafb;      /* Gray 50 */
--color-surface: #ffffff;         /* White */
--color-border: #e5e7eb;          /* Gray 200 */
```

### Typography Scale

```css
/* Type scale based on 1.2 ratio */
--text-xs: 0.75rem;        /* 12px - Metadata, fine print */
--text-sm: 0.875rem;       /* 14px - Secondary text */
--text-base: 1rem;         /* 16px - Body text */
--text-lg: 1.125rem;       /* 18px - Section headers */
--text-xl: 1.25rem;        /* 20px - Card titles */
--text-2xl: 1.5rem;        /* 24px - Page subtitles */
--text-3xl: 1.875rem;      /* 30px - Page titles, detail prices */
--text-4xl: 2.25rem;       /* 36px - Hero headlines */

/* Line heights */
--leading-tight: 1.25;
--leading-normal: 1.5;
--leading-relaxed: 1.625;
```

### Spacing Scale

Based on 8px grid (standard for marketplace UIs):

| Token | Value | Usage |
|-------|-------|-------|
| `space-0` | 0px | No spacing |
| `space-1` | 4px | Compact elements |
| `space-2` | 8px | Default gap, small padding |
| `space-3` | 16px | Section padding, card padding |
| `space-4` | 24px | Large gaps, form spacing |
| `space-5` | 32px | Page margins |
| `space-6` | 48px | Major section separation |

### Corner Radius

| Token | Value | Usage |
|-------|-------|-------|
| `radius-sm` | 4px | Small badges, chips |
| `radius-md` | 8px | Standard cards, inputs |
| `radius-lg` | 16px | Feature cards, modals |
| `radius-full` | 9999px | Pills, circular buttons |

### Elevation/Shadows

```css
--shadow-card: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24);
--shadow-card-hover: 0 4px 6px rgba(0,0,0,0.16), 0 2px 4px rgba(0,0,0,0.24);
--shadow-elevated: 0 4px 12px rgba(0,0,0,0.15), 0 2px 8px rgba(0,0,0,0.12);
```

---

## Atoms: Fundamental UI Elements

### Button Component

Primary interactive element for all CTAs.

#### Variants

| Variant | Background | Text | Border | Hover State |
|---------|------------|------|--------|-------------|
| **Primary** | `bg-blue-600` | `text-white` | none | `hover:bg-blue-700` |
| **Secondary** | `bg-white` | `text-gray-700` | `border border-gray-300` | `hover:bg-gray-50` |
| **Disabled** | `bg-gray-300` | `text-white` | none | `cursor-not-allowed` |
| **Danger** | `bg-red-600` | `text-white` | none | `hover:bg-red-700` |
| **Success** | `bg-green-600` | `text-white` | none | `hover:bg-green-700` |
| **Icon** | Transparent/transparent | Context-dependent | none | `hover:bg-gray-100` |

#### Sizes

| Size | Padding | Font | Min Height |
|------|---------|------|------------|
| **sm** | `px-3 py-1` | `text-sm` | 32px |
| **md** | `px-4 py-2` | `text-base` | 40px |
| **lg** | `px-6 py-3` | `text-base` | 48px |

#### Code Examples

```html
<!-- Primary Button -->
<button type="submit" class="px-6 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2">
    Save Changes
</button>

<!-- Secondary Button -->
<a href="/dashboard" class="px-6 py-2 bg-white text-gray-700 rounded-lg font-medium border border-gray-300 hover:bg-gray-50 transition-colors">
    Cancel
</a>

<!-- Disabled Button -->
<button type="button" disabled class="px-6 py-3 bg-gray-300 text-white rounded-lg font-medium cursor-not-allowed">
    Contact Seller
</button>

<!-- Icon Button -->
<button type="button" class="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors" aria-label="Close">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
    </svg>
</button>

<!-- Full Width Button -->
<button type="submit" class="w-full px-4 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors">
    Apply Filters
</button>
```

#### Accessibility Requirements

- Must have discernible text or `aria-label` for icon buttons
- Minimum 44px × 44px touch target (use `px-4 py-2` or larger)
- Focus state: `focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2`
- Disabled state: `disabled` attribute + `cursor-not-allowed` class
- Sufficient color contrast: 4.5:1 for normal text, 3:1 for large text

---

### Form Input Component

Text inputs, number inputs, and textareas for data entry.

#### States

| State | Styling |
|-------|---------|
| **Default** | `border border-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-blue-500` |
| **Error** | `border border-red-500 focus:ring-2 focus:ring-red-500` |
| **Disabled** | `bg-gray-100 cursor-not-allowed` |
| **Focus** | `ring-2 ring-blue-500 border-blue-500` |

#### Code Examples

```html
<!-- Text Input -->
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

<!-- Number Input (Price) -->
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
</div>

<!-- Textarea -->
<div class="mb-4">
    <label for="description" class="block font-medium mb-2">Description</label>
    <textarea 
        id="description" 
        name="description"
        rows="6"
        required
        class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
    ></textarea>
</div>

<!-- Error State -->
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

#### Accessibility Requirements

- Every input must have an associated `<label>` with `for` attribute
- Error messages: use `aria-invalid="true"` and `aria-describedby` pointing to error message
- Minimum 44px height for touch accessibility
- Placeholder text should not replace labels (use `aria-label` if no visible label)

---

### Badge Component

Small status indicators for metadata display.

#### Variants

| Variant | Background | Text | Usage |
|---------|------------|------|-------|
| **Primary** | `bg-blue-100` | `text-blue-800` | Category, primary actions |
| **Success** | `bg-green-100` | `text-green-800` | Published status, success states |
| **Warning** | `bg-yellow-100` | `text-yellow-800` | Pending, moderation states |
| **Danger** | `bg-red-100` | `text-red-800` | Rejected, error states |
| **Neutral** | `bg-gray-100` | `text-gray-700` | Secondary info, archived |

#### Code Examples

```html
<!-- Category Badge -->
<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
    Electronics
</span>

<!-- Status Badge -->
<span class="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-green-100 text-green-800">
    Published
</span>

<!-- Pending Badge -->
<span class="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-yellow-100 text-yellow-800">
    Pending Review
</span>

<!-- Filter Chip -->
<span class="inline-flex items-center px-3 py-1 rounded-full text-sm bg-blue-100 text-blue-800">
    Category: Electronics
    <button class="ml-2 text-blue-600 hover:text-blue-800" aria-label="Remove filter">
        ×
    </button>
</span>
```

---

### Loading Spinner

Visual indicator for loading states.

```html
<!-- Inline Spinner -->
<div class="flex items-center justify-center py-8" role="status" aria-label="Loading">
    <svg class="animate-spin w-6 h-6 text-blue-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
    </svg>
</div>

<!-- Button Loading State -->
<button disabled class="px-6 py-2 bg-blue-600 text-white rounded-lg flex items-center justify-center">
    <svg class="animate-spin w-4 h-4 mr-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
    </svg>
    Loading...
</button>
```

---

## Molecules: Combined Components

### Search Bar

Combined input + button for search functionality.

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
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 1114 0 7 7 0 01-14 0z"></path>
        </svg>
    </div>
    <button type="submit" class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium">
        Search
    </button>
</form>
```

### Price Display

Prominent price presentation with currency.

```html
<!-- List Price (rendered via shared format_price filter; EUR is default) -->
<p class="text-blue-600 font-bold text-xl mb-2">{{ ad|format_price }}</p>

<!-- Detail Price -->
<p class="text-blue-600 font-bold text-3xl mb-4">{{ ad|format_price }}</p>

<!-- Price Range (EUR-equivalent) -->
<div class="flex items-baseline gap-2">
    <span class="text-blue-600 font-bold text-xl">120 - 200 EUR</span>
    <span class="text-sm text-gray-500">avg. price</span>
</div>

<!-- Price with Label -->
<div>
    <span class="text-sm text-gray-500">Price</span>
    <p class="text-blue-600 font-bold text-xl">{{ ad|format_price }}</p>
</div>
```

### Image Placeholder

Fallback when no image is available.

```html
<div class="w-full h-48 bg-gray-200 rounded-lg flex items-center justify-center">
    <svg class="w-12 h-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-8-12h8a2 2 0 002 2v8a2 2 0 002 2H6a2 2 0 002-2z"></path>
    </svg>
    <span class="sr-only">No image available</span>
</div>
```

---

## Organisms: Complex Components

### Ad Card (Marketplace Listing)

The primary display component for classified ads, optimized for quick scanning.

#### Structure

```
┌─────────────────────────────────────────┐
│ ┌─────────────────────────────────────┐ │
│ │ Image (full-width, 48px height)     │ │
│ └─────────────────────────────────────┘ │
│ Title (2 lines max, font-semibold)       │
│ Price (blue, prominent)                  │
│ Description (3 lines max, truncated)     │
│ Metadata: Location | Category | Date     │
└─────────────────────────────────────────┘
```

#### Code Example

```html
<article class="bg-white rounded-lg shadow-sm border border-gray-200 hover:shadow-md transition-shadow">
    <a href="/ads/123" class="block">
        {% if ad.images.first %}
            <img 
                src="{{ ad.images.first.image_url }}" 
                alt="{{ ad.title }}"
                class="w-full h-48 object-cover rounded-t-lg"
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
            
            <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
                <span>{{ ad.city.get_name }}</span>
                <span>{{ ad.category.get_name }}</span>
                <time datetime="{{ ad.published_at|date:'Y-m-d' }}">
                    {{ ad.published_at|date:'M d' }}
                </time>
            </div>
        </div>
    </a>
</article>
```

#### Variants

| Variant | Image Ratio | Padding | Use Case |
|---------|-------------|---------|----------|
| **List Card** | 16:9 (h-48) | p-4 | Search results, category listing |
| **Dashboard Card** | 16:9 (h-32) | p-4 | Seller dashboard |
| **Detail Card** | Auto-height | p-6 | Ad detail page (full width) |

---

### Header Navigation

Site-wide navigation with consistent branding.

```html
<header class="bg-white shadow-sm border-b border-gray-200">
    <div class="container mx-auto px-4 py-4">
        <div class="flex items-center justify-between">
            <h1 class="text-2xl font-bold text-gray-800">
                <a href="/" class="hover:text-gray-600">Mko Bazuna</a>
            </h1>
            
            <nav class="flex items-center gap-4">
                <a href="/dashboard" class="text-sm text-gray-600 hover:text-gray-800">
                    Dashboard
                </a>
                <a href="/logout" class="text-sm text-gray-600 hover:text-red-600">
                    Logout
                </a>
            </nav>
        </div>
    </div>
</header>
```

---

### Pagination Controls

HTMX-powered pagination for search results.

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
           hx-get="?page={{ page_obj.previous_page_number }}" 
           hx-target="#ad-list" 
           hx-swap="innerHTML"
           class="px-3 py-2 rounded-lg text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50">
            «
        </a>
    {% endif %}
    
    {% for page_num in page_obj.paginator.page_range %}
        {% if page_num == page_obj.number %}
            <span class="px-3 py-2 rounded-lg text-sm font-medium text-white bg-blue-600" aria-current="page">
                {{ page_num }}
            </span>
        {% elif page_num > page_obj.number|add:'-3' and page_num < page_obj.number|add:'3' %}
            <a href="?page={{ page_num }}" 
               hx-get="?page={{ page_num }}" 
               hx-target="#ad-list" 
               hx-swap="innerHTML"
               class="px-3 py-2 rounded-lg text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50">
                {{ page_num }}
            </a>
        {% endif %}
    {% endfor %}
    
    {% if page_obj.has_next %}
        <a href="?page={{ page_obj.next_page_number }}" 
           hx-get="?page={{ page_obj.next_page_number }}" 
           hx-target="#ad-list" 
           hx-swap="innerHTML"
           class="px-3 py-2 rounded-lg text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50">
            »
        </a>
        <a href="?page={{ page_obj.paginator.num_pages }}" 
           hx-get="?page={{ page_obj.paginator.num_pages }}" 
           hx-target="#ad-list" 
           hx-swap="innerHTML"
           class="px-3 py-2 rounded-lg text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50">
            »»
        </a>
    {% endif %}
</nav>
```

---

### Filter Sidebar (Desktop)

Persistent filter controls for desktop browsing.

```html
<aside class="w-full md:w-64 md:flex-shrink-0">
    <form method="get" hx-get="{% url 'ads:list' %}" hx-target="#ad-results" hx-swap="innerHTML" class="sticky top-24">
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
            <h3 class="font-semibold text-gray-800 mb-4">Filters</h3>
            
            <!-- Category Filter -->
            <div class="mb-6">
                <h4 class="text-sm font-medium text-gray-700 mb-3">Category</h4>
                <div class="space-y-2 max-h-64 overflow-y-auto">
                    {% for cat in categories %}
                        <label class="flex items-center gap-2 text-sm">
                            <input 
                                type="checkbox" 
                                name="category" 
                                value="{{ cat.id }}"
                                class="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                            >
                            <span class="text-gray-700">{{ cat.get_name }}</span>
                        </label>
                    {% endfor %}
                </div>
            </div>
            
            <!-- Price Range -->
            <div class="mb-6">
                <h4 class="text-sm font-medium text-gray-700 mb-3">Price Range (EUR)</h4>
                <div class="flex gap-2">
                    <input 
                        type="number" 
                        name="price_min" 
                        placeholder="Min"
                        min="0"
                        class="w-1/2 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                    <input 
                        type="number" 
                        name="price_max" 
                        placeholder="Max"
                        min="0"
                        class="w-1/2 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                </div>
            </div>
            
            <!-- Clear Filters -->
            {% if has_active_filters %}
                <a href="{% url 'ads:list' %}" class="text-sm text-blue-600 hover:underline">
                    Clear all filters
                </a>
            {% endif %}
        </div>
    </form>
</aside>
```

---

### Mobile Filter Drawer

Slide-up panel for mobile filter interactions.

```html
<!-- Trigger Button -->
<button 
    type="button" 
    onclick="openFilterDrawer()"
    class="md:hidden fixed bottom-20 right-4 z-40 px-4 py-2 bg-blue-600 text-white rounded-lg shadow-lg font-medium"
    aria-label="Open filters"
>
    Filters
</button>

<!-- Drawer Overlay -->
<div id="filter-drawer" class="fixed inset-0 bg-black bg-opacity-50 z-50 hidden" role="dialog" aria-modal="true" aria-label="Filters">
    <div class="absolute bottom-0 left-0 right-0 bg-white rounded-t-lg p-6 max-h-[80vh] overflow-y-auto">
        <div class="flex justify-between items-center mb-4">
            <h2 class="text-xl font-semibold text-gray-800">Filters</h2>
            <button 
                type="button" 
                onclick="closeFilterDrawer()"
                class="p-2 text-gray-500 hover:text-gray-700"
                aria-label="Close filters"
            >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                </svg>
            </button>
        </div>
        
        <!-- Filter content -->
        <div class="space-y-6">
            <!-- Category, Price, Location filters -->
        </div>
        
        <!-- Sticky Action Bar -->
        <div class="sticky bottom-0 bg-white pt-4 border-t mt-6 -mx-6 px-6 pb-6">
            <button 
                type="submit" 
                onclick="applyFilters()"
                class="w-full px-4 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700"
            >
                Apply Filters
            </button>
        </div>
    </div>
</div>
```

---

### Contact Seller Card

Anonymity-preserving contact mechanism via Telegram.

```html
<div class="p-6 border-t bg-gray-50">
    {% if ad|can_contact %}
        <a 
             href="https://t.me/{{ bot_username }}?start=contact_{{ ad.id }}"
            class="inline-block px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
            role="button"
        >
            Contact Seller
        </a>
        <p class="text-xs text-gray-500 mt-2">
            Message sent through Telegram bot
        </p>
    {% else %}
        <button 
            type="button" 
            disabled
            class="px-6 py-3 bg-gray-300 text-white rounded-lg font-medium cursor-not-allowed"
        >
            Contact Seller
        </button>
        <p class="text-xs text-gray-500 mt-2">
            Seller unavailable for contact
        </p>
    {% endif %}
</div>
```

---

### Consent Banner

Privacy consent collection with accept/decline options.

```html
<div id="consent-banner" class="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 shadow-lg z-50" role="dialog" aria-live="polite" aria-label="Privacy consent">
    <div class="container mx-auto px-4 py-4 flex flex-col sm:flex-row items-center justify-between gap-4">
        <div class="text-sm text-gray-700">
            <p>
                This site uses cookies for essential functionality and analytics. 
                By accepting, you consent to all processing. You can still browse ads without accepting.
            </p>
            <p class="text-xs text-gray-500 mt-1">
                <a href="/privacy/" class="underline hover:text-gray-800">Privacy details</a>
            </p>
        </div>
        
        <div class="flex gap-2">
            <form method="post" action="{% url 'consent:accept' %}" class="inline">
                {% csrf_token %}
                <button 
                    type="submit"
                    class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                    Accept
                </button>
            </form>
            <form method="post" action="{% url 'consent:decline' %}" class="inline">
                {% csrf_token %}
                <button 
                    type="submit"
                    class="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 font-medium text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-gray-500"
                >
                    Decline (Browse-only)
                </button>
            </form>
        </div>
    </div>
</div>
```

---

## Layout Patterns

### Responsive Grid System

```html
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
    <!-- Cards here -->
</div>
```

| Breakpoint | Columns | Gap | Max Width |
|------------|---------|-----|-----------|
| Mobile (< 640px) | 1 | 24px | auto |
| Tablet (640px–1024px) | 2 | 24px | auto |
| Desktop (> 1024px) | 3 | 24px | container |

### Container Layout

```html
<div class="container mx-auto px-4">
    <!-- Header + Main content -->
</div>

<!-- With sidebar -->
<div class="container mx-auto px-4">
    <div class="flex flex-col md:flex-row gap-6">
        <aside class="w-full md:w-64 flex-shrink-0">
            <!-- Filters -->
        </aside>
        <main class="flex-1">
            <!-- Content -->
        </main>
    </div>
</div>
```

---

## Status Indicators

### Ad Status Badges

| Status | Badge HTML | Usage |
|--------|------------|-------|
| **Published** | `<span class="px-2 py-1 bg-green-100 text-green-800 rounded text-xs">Published</span>` | Active listings |
| **Pending Review** | `<span class="px-2 py-1 bg-yellow-100 text-yellow-800 rounded text-xs">Pending</span>` | Awaiting moderation |
| **Rejected** | `<span class="px-2 py-1 bg-red-100 text-red-800 rounded text-xs">Rejected</span>` | Failed moderation |
| **Archived** | `<span class="px-2 py-1 bg-gray-100 text-gray-700 rounded text-xs">Archived</span>` | Inactive listings |

### Trust Signals

```html
<!-- Verified Seller indicator -->
<div class="flex items-center gap-1 text-xs text-green-600">
    <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
    </svg>
    <span>Verified Seller</span>
</div>
```

---

## Accessibility Guidelines

### Focus Management

All interactive elements must have visible focus states:

```css
/* Focus ring for interactive elements */
.focus-ring {
    @apply focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2;
}
```

### Color Contrast

WCAG 2.1 AA compliance requirements:

- Text on background: minimum 4.5:1 contrast ratio
- Large text (18px+): minimum 3:1 contrast ratio
- Interactive elements: 3:1 contrast ratio against adjacent colors

### Screen Reader Support

- `aria-label` for icon-only buttons
- `aria-invalid` and `aria-describedby` for form errors
- `aria-current="page"` for current pagination
- `role="dialog"` for modal/drawer components
- `aria-live="polite"` for dynamic content announcements

### Keyboard Navigation

- All interactive elements keyboard accessible
- Tab order follows visual order
- Escape key closes modals/drawers
- Enter/space activate buttons

---

## Component Usage Matrix

| Component | Pages Used | Atoms Used |
|-----------|------------|------------|
| Ad Card | List, Detail, Dashboard | Image, Title, Price, Badge |
| Search Bar | List, Home | Input, Button |
| Filter Sidebar | List | Input, Checkbox, Button |
| Header | All | Logo, Nav Links |
| Pagination | List | Button (disabled state) |
| Consent Banner | All | Button (primary/secondary) |
| Form Elements | Edit, Login | Input, Label, Button |

---

## Related

- [UI Patterns](./ui-patterns.md) — Detailed patterns implementation
- [Filter UI](./filter-ui.md) — Filtering patterns
- [Search Patterns](./search-patterns.md) — Search UX patterns