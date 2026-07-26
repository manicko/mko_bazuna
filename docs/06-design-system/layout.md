---
id: design-system-layout
domain: design-system
tags:
  - layout
  - grid
  - responsive
  - breakpoints
related:
  - design-system-index
  - design-system-tokens
---

# Layout Patterns

> Responsive layout system and grid configurations for Mko Bazuna.

## Responsive Grid System

### Ad Listings Grid

```html
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
    <!-- Ad cards -->
</div>
```

| Breakpoint | Columns | Gap | Max Width |
|------------|---------|-----|-----------|
| Mobile (< 640px) | 1 | `gap-6` (24px) | auto |
| Tablet (640px–1024px) | 2 | `gap-6` (24px) | auto |
| Desktop (> 1024px) | 3 | `gap-6` (24px) | container |

### Container Layout

```html
<!-- Full-width container -->
<div class="container mx-auto px-4">
    <!-- Header + Main content -->
</div>

<!-- With sidebar (desktop) -->
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

| Property | Value |
|----------|-------|
| Max width | 1140px (Tailwind container) |
| Horizontal padding | `px-4` (16px) |
| Gap (sidebar layout) | `gap-6` (24px) |

---

## Responsive Breakpoints

Customized for marketplace browsing patterns.

| Name | Min Width | Max Width | Usage |
|------|-----------|-----------|-------|
| Mobile | — | 639px | Single column, drawer filters |
| Tablet | 640px | 1023px | Two column grid, optional sidebar |
| Desktop | 1024px | — | Three column grid, persistent sidebar |

### Breakpoint-Specific Patterns

```css
/* Mobile-first approach */
.grid-cols-1 { /* Mobile: single column */ }

@media (min-width: 640px) {
    .md\:grid-cols-2 { /* Tablet: two columns */ }
}

@media (min-width: 1024px) {
    .lg\:grid-cols-3 { /* Desktop: three columns */ }
    .lg\:block { /* Sidebar visible */ }
}
```

---

## Image Aspect Ratios

### Standard Ad Card

```html
<img class="w-full h-48 object-cover rounded-t-lg">
```

- **Height:** 48 (192px)
- **Aspect:** 16:9 (responsive width)
- **Object fit:** `object-cover` for uniform presentation

### Multi-Image Detail

```html
<div class="grid grid-cols-1 {% if ad.images.count > 1 %}md:grid-cols-2{% endif %} gap-2">
    <img class="w-full h-64 object-cover rounded-lg">
</div>
```

- **Height:** 64 (256px)
- **Columns:** 1 on mobile, 2 on tablet+
- **Gap:** `gap-2` (8px)

### Single Image Detail

```html
<img class="w-full max-h-96 object-cover rounded-lg">
```

- **Max height:** 96 (384px)

---

## Sticky / Fixed Positioning

### Header Navigation

```html
<header class="bg-white shadow-sm border-b">
    <div class="container mx-auto px-4 py-4">
        <!-- Header content -->
    </div>
</header>
```

- **Position:** Static (no explicit sticky)
- **Z-index:** None (flows naturally)
- **Separation:** `shadow-sm border-b`

### Mobile Filter Button

```html
<button type="button" onclick="openFilterDrawer()" class="md:hidden fixed bottom-20 right-4 z-40 px-4 py-2 bg-blue-600 text-white rounded-lg shadow-lg font-medium">
    Filters
</button>
```

| Property | Value |
|----------|-------|
| Visibility | Hidden on `md+` (`md:hidden`) |
| Position | Fixed bottom-right |
| Bottom offset | `bottom-20` (80px from bottom) |
| Right offset | `right-4` (16px from edge) |
| Z-index | 40 |

### Consent Banner

```html
<div class="fixed bottom-0 left-0 right-0 z-50">
    <!-- Consent content -->
</div>
```

| Property | Value |
|----------|-------|
| Position | Fixed bottom full-width |
| Z-index | 50 (above filter button) |

---

## Spacing Patterns

### Page Structure

```
Page (bg-gray-50)
└── Container (px-4)
    └── Header (py-4 = 32px height)
    └── Main Content (py-6 = 48px top/bottom)
        └── Section (mb-8 = 32px between sections)
```

### Card Internal Spacing

```
Card (p-4)
├── Image (no padding, rounded-t-lg)
└── Content (p-4)
    ├── Title (mb-2)
    ├── Price (mb-2)
    ├── Description (mb-3)
    └── Metadata (text-xs, no margin)
```

---

## Empty States

```html
<div class="text-center py-12 bg-white rounded-lg">
    <p class="text-gray-600 text-lg">No ads available</p>
    <p class="text-gray-500 mt-2">Be the first to create an ad via Telegram!</p>
</div>
```

| Property | Value |
|----------|-------|
| Vertical padding | `py-12` (48px) |
| Background | `bg-white` |
| Radius | `rounded-lg` |
| Primary text | `text-lg text-gray-600` |
| Secondary text | `text-sm text-gray-500 mt-2` |

---

## Did-You-Mean Suggestions

```html
{% if suggested_city %}
    <div class="mb-4 p-3 bg-blue-50 rounded-lg">
        <p class="text-sm text-blue-800">
            Did you mean: <a href="?city={{ suggested_city.id }}" class="underline font-medium">{{ suggested_city.get_name }}</a>?
        </p>
    </div>
{% endif %}
```

| Property | Value |
|----------|-------|
| Background | `bg-blue-50` |
| Text | `text-sm text-blue-800` |
| Radius | `rounded-lg` |
| Padding | `p-3` (12px) |
| Margin bottom | `mb-4` (16px) |