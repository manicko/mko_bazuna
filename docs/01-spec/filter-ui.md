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

Desktop users see persistent filter sidebar while browsing results.

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
| Condition | Medium | Deferred to phase 2 |

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
            Price: {% if selected_price_min %}{{ selected_price_min }}{% endif %} - {% if selected_price_max %}{{ selected_price_max }}{% endif %} BAM
            <a href="?{% url_replace request 'price_min' '' 'price_max' '' %}" class="ml-2 text-purple-600 hover:text-purple-800">✕</a>
        </span>
    {% endif %}
</div>
```

### Chip Styling

| State | Background | Text | Remove Icon |
|-------|------------|------|-------------|
| Category | `bg-blue-100` | `text-blue-800` | `text-blue-600` |
| City | `bg-green-100` | `text-green-800` | `text-green-600` |
| Price | `bg-purple-100` | `text-purple-800` | `text-purple-600` |

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

## Price Range Filter

Price filtering with dual input fields.

### Input Pattern

```html
<div class="price-filter">
    <label class="block text-sm font-medium mb-2">Price Range (BAM)</label>
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

Related user stories: US-B3