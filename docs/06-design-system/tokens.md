---
id: design-system-tokens
domain: design-system
tags:
  - design-tokens
  - colors
  - typography
  - spacing
  - radius
  - shadows
related:
  - design-system-index
  - components
---

# Design Tokens

> Single source of truth for visual design values. All values are copy-paste ready for immediate use.

## Color Palette

### Primitive Colors

Derived from Tailwind defaults with marketplace-specific adjustments for accessibility and visual hierarchy.

| Token | Hex | RGB | Tailwind Class | Usage |
|-------|-----|-----|---------------|-------|
| Gray 50 | `#f9fafb` | rgb(249, 250, 251) | `bg-gray-50` | Page background |
| Gray 100 | `#f3f4f6` | rgb(243, 244, 246) | `bg-gray-100` | Disabled inputs, muted badges |
| Gray 200 | `#e5e7eb` | rgb(229, 231, 235) | `bg-gray-200` | Image placeholders, borders |
| Gray 300 | `#d1d5db` | rgb(209, 213, 221) | `bg-gray-300` | Cancel buttons, disabled states |
| Gray 400 | `#9ca3af` | rgb(156, 163, 175) | `text-gray-400` | Breadcrumb separators, icons |
| Gray 500 | `#6b7280` | rgb(107, 114, 128) | `text-gray-500` | Secondary text, metadata |
| Gray 600 | `#4b5563` | rgb(75, 85, 99) | `text-gray-600` | Body text, descriptions |
| Gray 700 | `#374151` | rgb(55, 64, 81) | `text-gray-700` | Label text, secondary buttons |
| Gray 800 | `#1f2937` | rgb(31, 41, 55) | `text-gray-800` | Headings, primary text |
| Blue 500 | `#3b82f6` | rgb(59, 130, 246) | - | Focus ring (ring-blue-500) |
| Blue 600 | `#2563eb` | rgb(37, 99, 235) | `bg-blue-600`, `text-blue-600` | **Primary actions** |
| Blue 700 | `#1d4ed8` | rgb(29, 78, 216) | `hover:bg-blue-700` | Primary hover state |
| Green 600 | `#059669` | rgb(5, 150, 105) | `bg-green-600`, `text-green-600` | **Success states**, Approve |
| Green 700 | `#047857` | rgb(4, 120, 87) | `hover:bg-green-700` | Success hover |
| Red 600 | `#dc2626` | rgb(220, 38, 38) | `bg-red-600`, `text-red-600` | **Error/Danger states**, Reject |
| Red 700 | `#b91c1c` | rgb(185, 28, 28) | `hover:bg-red-700` | Danger hover |
| Amber 600 | `#d97706` | rgb(217, 119, 6) | `text-amber-600` | Warning/pending state |
| Orange 600 | `#ea580c` | rgb(234, 88, 12) | `bg-orange-600` | Ban user action |

### Semantic Color Mapping

Purpose-driven aliases for consistent usage across components.

| Semantic Purpose | Hex | Tailwind Classes | Usage |
|-----------------|-----|----------------|-------|
| **Primary Action** | `#2563eb` | `bg-blue-600` | Main buttons, active pagination |
| **Primary Hover** | `#1d4ed8` | `hover:bg-blue-700` | Button hover states |
| **Primary Text** | `#1f2937` | `text-gray-800` | Headings, titles |
| **Secondary Text** | `#4b5563` / `#6b7280` | `text-gray-600` / `text-gray-500` | Descriptions, metadata |
| **Success / Published** | `#059669` | `bg-green-600`, `text-green-800` | Published status, positive actions |
| **Warning / Pending** | `#d97706` | `bg-yellow-600`, `text-yellow-800` | Moderation pending |
| **Error / Rejected** | `#dc2626` | `bg-red-600`, `text-red-800` | Rejected, danger states |
| **Info / Suggestion** | `#2563eb` | `bg-blue-50`, `text-blue-800` | Did-you-mean suggestions |
| **Border / Input** | `#d1d5db` | `border-gray-300` | Form inputs, card borders |
| **Surface** | `#ffffff` | `bg-white` | Card backgrounds |
| **Background** | `#f9fafb` | `bg-gray-50` | Page background |

### Color Usage Quick Reference

```css
/* Primary button - DO use */
bg-blue-600 text-white hover:bg-blue-700

/* Success badge - DO use */
bg-green-100 text-green-800

/* Error badge - DO use */
bg-red-100 text-red-800

/* Warning badge - DO use */
bg-yellow-100 text-yellow-800

/* NEVER hardcode colors - use semantic tokens only */
```

---

## Typography Scale

### Font Families

| Context | Font Stack | Notes |
|---------|------------|-------|
| Primary | System UI | `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif` |

Custom fonts deferred to post-MVP for performance.

### Font Sizes

Based on modular scale with 8px grid alignment.

| Token | Size (px) | Size (rem) | Line Height | Tailwind Class | Usage |
|-------|-----------|------------|-------------|----------------|-------|
| Display | 36px | 2.25rem | 1.25 | `text-4xl` | Hero headlines, empty states |
| Page Title | 30px | 1.875rem | 1.25 | `text-3xl` | Detail page titles, prices |
| Section Header | 24px | 1.5rem | 1.5 | `text-2xl` | Page titles, section headers |
| Card Title | 20px | 1.25rem | 1.5 | `text-xl` | Ad card titles |
| Subsection | 18px | 1.125rem | 1.5 | `text-lg` | Subsection headers |
| Body | 16px | 1rem | 1.5 | `text-base` | Body text, form inputs |
| Secondary | 14px | 0.875rem | 1.5 | `text-sm` | Descriptions, form labels |
| Metadata | 12px | 0.75rem | 1.5 | `text-xs` | Timestamps, fine print |

### Font Weights

| Weight | Value | Tailwind Class | Usage |
|--------|-------|---------------|-------|
| Regular | 400 | `font-normal` | Body text |
| Medium | 500 | `font-medium` | Labels, badge text |
| Semibold | 600 | `font-semibold` | Card titles, section headers |
| Bold | 700 | `font-bold` | Prices, headings, CTA text |

### Line Clamp Standards

| Context | Clamp | CSS |
|---------|-------|-----|
| Ad title (list) | 2 lines | `line-clamp-2` |
| Ad description (list) | 3 lines | `line-clamp-3` |
| Ad description (detail) | none | Full display |

---

## Spacing Scale

Based on 8px grid system (Tailwind default increments).

| Token | Pixels | Tailwind Class | Usage |
|-------|--------|---------------|-------|
| `space-0` | 0px | `p-0` | No spacing |
| `space-1` | 4px | `p-1` (0.25rem) | Fine text spacing |
| `space-2` | 8px | `p-2` | Default gap, small padding |
| `space-3` | 12px | Not in default | Card description margin |
| `space-4` | 16px | `p-4` | Section padding, card padding |
| `space-5` | 24px | `p-6` | Large gaps, section margins |
| `space-6` | 32px | `p-8` | Page margins |
| `space-7` | 48px | `p-12` | Major section separation |

### Spacing Usage Mapping

| Component | Spacing | Tailwind Classes |
|-----------|---------|------------------|
| Page padding | `space-4` | `px-4 py-4` (container) |
| Card padding | `space-4` | `p-4` (list), `p-6` (detail) |
| Grid gap | `space-6` | `gap-6` |
| Form spacing | `space-4` | `mb-4` between fields |
| Section margins | `space-7` | `mt-8`, `mb-8` |

---

## Corner Radius

| Token | Value | Tailwind Class | Usage |
|-------|-------|---------------|-------|
| `radius-sm` | 4px | `rounded` | Inline badges, small elements |
| `radius-md` | 8px | `rounded-lg` | **Standard cards, inputs, buttons** |
| `radius-lg` | 16px | `rounded-xl` | Feature cards, modals |
| `radius-full` | 9999px | `rounded-full` | Pills, circular icons |

### Radius Usage in Components

| Component | Classes |
|-----------|---------|
| Buttons | `rounded-lg` |
| Cards | `rounded-lg` |
| Image placeholders | `rounded-t-lg` (top only) |
| Badges | `rounded-full` (pill) or `rounded` |
| Form inputs | `rounded-lg` |
| Consent banner | No radius (full-width) |

---

## Shadows / Elevation

| Token | CSS Value | Tailwind Class | Usage |
|-------|-----------|----------------|-------|
| Card Shadow | `0 1px 3px rgba(0,0,0,0.12)` | `shadow` | Default card state |
| Card Hover | `0 4px 6px rgba(0,0,0,0.16)` | `hover:shadow-md` | Card hover elevation |
| Elevated | `0 4px 12px rgba(0,0,0,0.15)` | `shadow-lg` | Modals, elevated elements |
| Header | `0 1px 2px rgba(0,0,0,0.05)` | `shadow-sm` | Header separation |

---

## Accessibility Notes

### Color Contrast Requirements

| Text Size | Minimum Ratio | Status |
|-----------|---------------|--------|
| Normal text (16px) | 4.5:1 | Blue 600 on white = ~4.5:1 ✓ |
| Large text (18px+) | 3:1 | All combinations pass |
| UI controls | 3:1 | Verified |

### Focus States

```html
<!-- All interactive elements -->
focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2

<!-- Inputs -->
focus:outline-none focus:ring-2 focus:ring-blue-500

<!-- Buttons -->
focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
```

### Touch Target Minimum

- Minimum 44px × 44px for interactive elements
- Small buttons (`px-3 py-1`): 32px height - use only for non-critical actions
- Standard buttons (`px-4 py-2`): 40px height - acceptable for secondary actions
- Large buttons (`px-6 py-3`): 48px height - recommended for primary CTAs

---

## Tailwind Quick Reference

### Button Classes

```html
<!-- Primary -->
<button class="px-6 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors">

<!-- Success -->
<button class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium">

<!-- Danger -->
<button class="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 font-medium">

<!-- Secondary -->
<a class="px-6 py-2 bg-white text-gray-700 rounded-lg font-medium border border-gray-300 hover:bg-gray-50 transition-colors">
```

### Card Classes

```html
<article class="bg-white rounded-lg shadow hover:shadow-md transition-shadow">
    <img class="w-full h-48 object-cover rounded-t-lg">
    <div class="p-4">
        <h2 class="font-semibold text-lg mb-2 line-clamp-2">Title</h2>
        <p class="text-blue-600 font-bold text-xl mb-2">{{ ad|format_price }}</p>
        <p class="text-sm text-gray-600 line-clamp-3 mb-3">Description</p>
        <div class="flex justify-between text-xs text-gray-500">
            <span>Location</span><span>Category</span><time>Date</time>
        </div>
    </div>
</article>
```

### Form Classes

```html
<label class="block font-medium mb-2">Label</label>
<input class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">
```

### Badge Classes

```html
<span class="px-2 py-1 bg-green-100 text-green-800 rounded text-xs">Published</span>
<span class="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm">Category</span>
```