---
id: filter-ui
domain: spec
tags:
  - filter
  - ui
  - patterns
  - search
related:
  - technical-specification
  - buyer-stories
  - search-patterns
---

## Purpose

Document filter UI patterns for the Mko Bazuna classifieds board. Filters support category, city, and price range selection with HTMX-driven partial updates.

## Main Concepts

- **Progressive disclosure:** Essential filters visible first, advanced on demand
- **HTMX integration:** Filters avoid full page reloads; partial updates
- **Mobile-responsive:** Sidebar on desktop, drawer on mobile
- **Active filter management:** Clear chips showing current selections

## Sticky Sidebar Filters (Desktop)

Desktop users see persistent filter sidebar while browsing results, containing category, city,
price range, listing condition, listing purpose, and features controls.

### Layout Structure

```css
/* Desktop: 25% sidebar, 75% content */
@media (min-width: 768px) {
    .filter-sidebar { max-width: 25%; }
    .content-area { max-width: 75%; }
}
```

### Filter Groups

| Group | Priority | Visibility |
|-------|----------|------------|
| Category | High | Always visible |
| City | High | Always visible |
| Price Range | Medium | Collapsible on mobile |
| Condition | Medium | Collapsible on mobile |
| Listing Purpose | Medium | Collapsible on mobile |
| Features | Medium | Collapsible on mobile |

### Implementation

```html
<aside class="filter-sidebar hidden md:block">
    <form method="get" hx-get="{% url 'ads:list' %}" hx-target="#ad-results" hx-swap="innerHTML">
        <!-- Category filter -->
        <div class="mb-6">
            <h3 class="font-semibold mb-3">Category</h3>
            <div class="space-y-2 max-h-64 overflow-y-auto">
                {% for cat in categories %}
                    <label class="flex items-center gap-2">
                        <input type="checkbox" name="category" value="{{ cat.id }}"
                               hx-trigger="change" hx-get="{% url 'ads:list' %}"
                               hx-target="#ad-results">
                        <span>{{ cat.get_name }}</span>
                    </label>
                {% endfor %}
            </div>
        </div>

        <!-- Price range -->
        <div class="mb-6">
            <h3 class="font-semibold mb-3">Price Range</h3>
            <div class="flex gap-2">
                <input type="number" name="price_min" placeholder="Min"
                       class="w-1/2 px-3 py-2 border rounded">
                <input type="number" name="price_max" placeholder="Max"
                       class="w-1/2 px-3 py-2 border rounded">
            </div>
        </div>
    </form>
</aside>
```

related user stories: US-B3

### Listing Purpose & Features Filters

In addition to category/city/price, the catalog filter form
(`templates/ads/partials/filter_form.html`) exposes three buyer dimensions driven by the
`lookup_items` reference-data system. The form submits via `hx-get` to the results container
(`#ad-list`) with `hx-push-url="true"` so the URL stays synchronized.

- **`listing_purpose`** — single-select dropdown (`<select name="listing_purpose">`). Options are
  resolved for the currently active category via `CategoryLookupResolver.get_resolved_purposes()`
  (context: `resolved_purposes` / `current_listing_purpose`); when no category is selected, the
  full active `listing_purpose` lookup set is shown. Unrecognized/missing slugs match nothing
  (empty result set, same "no match" behavior as an unknown city slug).
- **`features`** — multi-select checkboxes (`<input type="checkbox" name="features" ...>`,
  one per feature, value = slug). Options resolve via
  `CategoryLookupResolver.get_resolved_features()` (context: `resolved_features` /
  `current_features`). Selection uses **AND-semantics**: an ad must possess *all*
  of the selected features. Filtering is done by annotating each ad with a count of
  matching feature through-rows and filtering `count = len(selected_slugs)`, which
  yields AND-semantics (an ad must match every selected feature) without JOIN
  row-multiplication.
  Repeated `?features=` query params (HTML form convention) carry the multi-selection.

```html
<!-- Listing purpose (single select) -->
<div class="mb-6">
    <h3 class="font-semibold mb-3">Listing purpose</h3>
    <select name="listing_purpose" class="w-full px-3 py-2 border rounded"
            hx-get="{% url 'ads:list' %}" hx-target="#ad-results" hx-push-url="true">
        <option value="">All purposes</option>
        {% for purpose in resolved_purposes %}
            <option value="{{ purpose.slug }}"
                {% if current_listing_purpose == purpose.slug %}selected{% endif %}>
                {{ purpose.get_name }}
            </option>
        {% endfor %}
    </select>
</div>

<!-- Features (multi-select, AND-semantics) -->
<div class="mb-6">
    <h3 class="font-semibold mb-3">Features</h3>
    <div class="space-y-2">
        {% for feature in resolved_features %}
            <label class="flex items-center gap-2">
                <input type="checkbox" name="features" value="{{ feature.slug }}"
                       {% if feature.slug in current_features %}checked{% endif %}
                       hx-get="{% url 'ads:list' %}" hx-target="#ad-results" hx-push-url="true">
                <span>{{ feature.get_name }}</span>
            </label>
        {% endfor %}
    </div>
</div>
```

#### Listing Condition Filter

- **`listing_condition`** — single-select dropdown (`<select name="listing_condition">`). Options
  are resolved for the currently active category via
  `CategoryLookupResolver.get_resolved_conditions()` (context: `resolved_conditions` /
  `current_listing_condition`); when no category is selected, the full active `listing_condition`
  lookup set is shown. Unrecognized/missing slugs match nothing (same "no match" behavior as an
  unknown city slug). This dimension was introduced in Plan 12 to separate `new`/`used` from the
  multi-select `features` group (Plan 12).

```html
<!-- Listing condition (single select) -->
<div class="mb-6">
    <h3 class="font-semibold mb-3">Condition</h3>
    <select name="listing_condition" class="w-full px-3 py-2 border rounded"
            hx-get="{% url 'ads:list' %}" hx-target="#ad-results" hx-push-url="true">
        <option value="">All conditions</option>
        {% for condition in resolved_conditions %}
            <option value="{{ condition.slug }}"
                {% if current_listing_condition == condition.slug %}selected{% endif %}
                {{ condition.get_name }}
            </option>
        {% endfor %}
    </select>
</div>
```

Related user stories: US-B3

## Mobile Filter Drawer

Mobile users access filters through a slide-up drawer interface.

### Trigger Pattern

```html
<!-- Mobile filter button -->
<button type="button" onclick="openFilterDrawer()"
        class="md:hidden fixed bottom-20 right-4 z-40 px-4 py-2 bg-blue-600 text-white rounded-lg shadow-lg">
    Filters
</button>
```

### Drawer Structure

```html
<div id="filter-drawer" class="fixed inset-0 bg-black bg-opacity-50 z-50 hidden">
    <div class="absolute bottom-0 left-0 right-0 bg-white rounded-t-lg p-6 max-h-[80vh] overflow-y-auto">
        <div class="flex justify-between items-center mb-4">
            <h2 class="text-xl font-semibold">Filters</h2>
            <button onclick="closeFilterDrawer()" class="text-gray-500">✕</button>
        </div>

        <!-- Filter content same as sidebar -->
        <div class="space-y-6">
            <!-- Category, Price, Location filters -->
        </div>

        <!-- Sticky action bar -->
        <div class="sticky bottom-0 bg-white pt-4 border-t mt-6">
            <button type="submit" class="w-full px-4 py-3 bg-blue-600 text-white rounded-lg font-medium">
                Apply Filters
            </button>
        </div>
    </div>
</div>
```

Related user stories: US-B3, US-B8

## Filter Chips/Tags for Active Filters

When filters are applied, display them as removable chips above results.

### Implementation

```html
<div class="flex flex-wrap gap-2 mb-4">
    {% if selected_category %}
        <span class="inline-flex items-center px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm">
            Category: {{ selected_category.get_name }}
            <a href="?{% url_replace request 'category' '' %}" class="ml-2 text-blue-600 hover:text-blue-800">✕</a>
        </span>
    {% endif %}
    {% if selected_city %}
        <span class="inline-flex items-center px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm">
            City: {{ selected_city.get_name }}
            <a href="?{% url_replace request 'city' '' %}" class="ml-2 text-green-600 hover:text-green-800">✕</a>
        </span>
    {% endif %}
    {% if selected_price_min or selected_price_max %}
        <span class="inline-flex items-center px-3 py-1 bg-purple-100 text-purple-800 rounded-full text-sm">
            Price: {% if selected_price_min %}{{ selected_price_min }}{% endif %} - {% if selected_price_max %}{{ selected_price_max }}{% endif %} EUR
            <a href="?{% url_replace request 'price_min' '' 'price_max' '' %}" class="ml-2 text-purple-600 hover:text-purple-800">✕</a>
        </span>
    {% endif %}
    {% if current_listing_purpose %}
        <span class="inline-flex items-center px-3 py-1 bg-indigo-100 text-indigo-800 rounded-full text-sm">
            Purpose: {{ current_listing_purpose_display }}
            <a href="?{% url_replace request 'listing_purpose' '' %}" class="ml-2 text-indigo-600 hover:text-indigo-800">✕</a>
        </span>
    {% endif %}
    {% if current_listing_condition %}
        <span class="inline-flex items-center px-3 py-1 bg-amber-100 text-amber-800 rounded-full text-sm">
            Condition: {{ current_listing_condition_display }}
            <a href="?{% url_replace request 'listing_condition' '' %}" class="ml-2 text-amber-600 hover:text-amber-800">✕</a>
        </span>
    {% endif %}
    {% for feature_slug in current_features %}
        <span class="inline-flex items-center px-3 py-1 bg-pink-100 text-pink-800 rounded-full text-sm">
            Feature: {{ feature_display }}
            <a href="?{% url_replace request 'features' feature_slug %}" class="ml-2 text-pink-600 hover:text-pink-800">✕</a>
        </span>
    {% endfor %}
</div>
```

### Chip Styling

| State | Background | Text | Remove Icon |
|-------|------------|------|-------------|
| Category | `bg-blue-100` | `text-blue-800` | `text-blue-600` |
| City | `bg-green-100` | `text-green-800` | `text-green-600` |
| Price | `bg-purple-100` | `text-purple-800` | `text-purple-600` |
| Listing Purpose | `bg-indigo-100` | `text-indigo-800` | `text-indigo-600` |
| Condition | `bg-amber-100` | `text-amber-800` | `text-amber-600` |
| Features | `bg-pink-100` | `text-pink-800` | `text-pink-600` |

Related user stories: US-B3

## Category Hierarchical Navigation

Categories use django-mptt for closed admin-managed tree structure.

### Navigation Pattern

```html
<nav class="category-nav">
    <ul class="space-y-1">
        {% recursetree categories %}
            <li class="ml-{{ level|default:0|mul:4 }}">
                <a href="?category={{ node.id }}"
                   class="block px-3 py-2 text-sm hover:bg-gray-100 rounded">
                    {{ node.get_name }}
                </a>
                {% if not node.is_leaf_node %}
                    <ul class="ml-4 mt-1">
                        {{ children }}
                    </ul>
                {% endif %}
            </li>
        {% endrecursetree %}
    </ul>
</nav>
```

### Tree Structure (Recommended)

| Main Category | Subcategories |
|---------------|---------------|
| Goods | Electronics, Clothing, Children, Furniture, Tools, Sport, Books, Other |
| Services | Repair, Translation, Tutors, Courses, Beauty, Transport, Freelance, Other |
| Real Estate | Apartments, Houses, Rooms, Commercial, Parking, Other |

Related user stories: US-B6, US-A7

## Location-Based Filtering

City selection from closed preset list of Montenegro cities.

### Selector UI

```html
<select name="city" class="w-full md:w-auto px-3 py-2 border rounded">
    <option value="">All cities</option>
    {% for city in cities %}
        <option value="{{ city.id }}"
                {% if selected_city.id == city.id %}selected{% endif %}>
            {{ city.get_name }}
        </option>
    {% endfor %}
</select>
```

### Typo Handling

```html
{% if suggested_city %}
    <div class="mb-4 p-3 bg-blue-50 rounded-lg">
        <p class="text-sm text-blue-800">
            Did you mean: <a href="?city={{ suggested_city.id }}">{{ suggested_city.get_name }}</a>?
        </p>
    </div>
{% endif %}
```

Related user stories: US-B7

### Default & precedence

The city filter **defaults** to the buyer's preferred city (see
[search-patterns.md > Preferred City](search-patterns.md#preferred-city-default--precedence)):
authenticated users default to `User.preferred_city`; guests default to the consent-gated
`preferred_city` cookie; otherwise "All cities" (country-wide). An explicit `city` value in
the URL always overrides the default.

## Price Range Filter

Price filtering with dual input fields.

### Input Pattern

```html
<div class="price-filter">
    <label class="block text-sm font-medium mb-2">Price Range (EUR)</label>
    <div class="flex gap-2">
        <input type="number" name="price_min" placeholder="Min" min="0"
               value="{{ request.GET.price_min }}"
               class="w-1/2 px-3 py-2 border rounded focus:ring-2 focus:ring-blue-500">
        <input type="number" name="price_max" placeholder="Max" min="0"
               value="{{ request.GET.price_max }}"
               class="w-1/2 px-3 py-2 border rounded focus:ring-2 focus:ring-blue-500">
    </div>
</div>
```

Related user stories: US-B3

## Filter Reset/Clear All

Option to reset all active filters at once.

### Implementation

```html
{% if has_active_filters %}
    <div class="mb-4">
        <a href="{% url 'ads:list' %}" class="text-sm text-blue-600 hover:underline">
            Clear all filters
        </a>
    </div>
{% endif %}
```

The clear-all link drops **all** filter parameters (`listing_purpose`, `listing_condition`,
`features`, `category`, `city`, price range, `q`) and returns to page 1.

## Pagination URL Preservation

Every pagination link must preserve the **full** active filter set so a bookmarked or shared page
two stays on the same result subset (no divergence from page 1). In addition to the existing
`q`/`category`/`city`/`sort`/`min_price`/`max_price`/`page` parameters, pagination URLs carry:

- `listing_purpose=<slug>` when a purpose is selected (dropped when none).
- `listing_condition=<slug>` when a condition is selected (dropped when none).
- **Repeated** `features=<slug>` for each selected feature (one query-param per feature, not
   comma-joined), preserving AND-semantics across pages.

The `sort` parameter is preserved in pagination URLs even while a `q` (full-text) query is active,
so the user's sort preference is retained across result pages.

```html
<!-- Pagination links append the active listing_purpose + listing_condition + each feature -->
<a href="?page=2&category={{ category_slug }}&city={{ city_slug }}&sort={{ current_sort }}
   {% if current_listing_purpose %}&listing_purpose={{ current_listing_purpose }}{% endif %}
   {% if current_listing_condition %}&listing_condition={{ current_listing_condition }}{% endif %}
   {% for fslug in current_features %}&features={{ fslug }}{% endfor %}">
   Next
</a>
```

Related user stories: US-B3, US-B6