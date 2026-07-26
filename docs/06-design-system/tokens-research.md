# Design Tokens Research — Mko Bazuna

> Comprehensive design token documentation extracted from actual implementation and research. Copy-paste ready values for developers.

---

## 1. Color Palette

### Primitive Colors (Tailwind Defaults)

| Token | Hex | RGB | Tailwind Class | Usage |
|-------|-----|-----|---------------|-------|
| Gray 50 | `#f9fafb` | rgb(249, 250, 251) | `bg-gray-50` | Page background |
| Gray 100 | `#f3f4f6` | rgb(243, 244, 246) | `bg-gray-100` | Disabled inputs, muted badges |
| Gray 200 | `#e5e7eb` | rgb(229, 231, 235) | `bg-gray-200`, `border-gray-200` | Image placeholders, borders |
| Gray 300 | `#d1d5db` | rgb(209, 213, 221) | `bg-gray-300` | Cancel buttons, disabled states |
| Gray 400 | `#9ca3af` | rgb(156, 163, 175) | `text-gray-400` | Breadcrumb separators |
| Gray 500 | `#6b7280` | rgb(107, 114, 128) | `text-gray-500` | Secondary text, metadata |
| Gray 600 | `#4b5563` | rgb(75, 85, 99) | `text-gray-600` | Body text, descriptions |
| Gray 700 | `#374151` | rgb(55, 56, 81) | `text-gray-700` | Label text, button secondary |
| Gray 800 | `#1f2937` | rgb(31, 41, 55) | `text-gray-800` | Headings, primary text |
| Blue 50 | `#eff6ff` | rgb(239, 246, 255) | `bg-blue-50`, `focus:ring-blue-500` | Search suggestions, focus rings |
| Blue 100 | `#dbeafe` | rgb(219, 224, 235) | `bg-blue-100` | Edit/reject action badges |
| Blue 600 | `#2563eb` | rgb(37, 99, 235) | `bg-blue-600` | **Primary actions** |
| Blue 700 | `#1d4ed8` | rgb(29, 78, 216) | `bg-blue-700` | Primary hover state |
| Blue 800 | `#1e40af` | rgb(30, 64, 175) | `text-blue-800` | Suggestion text |
| Green 600 | `#059669` | rgb(5, 150, 105) | `bg-green-600` | **Success states** |
| Green 700 | `#047857` | rgb(4, 120, 87) | `bg-green-700` | Success hover |
| Green 800 | `#065f46` | rgb(6, 95, 70) | `text-green-800` | Success badge text |
| Red 600 | `#dc2626` | rgb(220, 38, 38) | `bg-red-600` | **Error/Danger states** |
| Red 700 | `#b91c1c` | rgb(185, 28, 28) | `bg-red-700` | Danger hover |
| Red 800 | `#991b1b` | rgb(153, 27, 27) | `text-red-800` | Error badge text |
| Yellow 600 | `#d97706` | rgb(217, 119, 6) | `text-yellow-600` | Warning/pending state |
| Yellow 800 | `#92400e` | rgb(146, 64, 14) | `text-yellow-800` | Warning badge text |
| Orange 600 | `#ea580c` | rgb(234, 88, 12) | `bg-orange-600` | Ban user actions |

### Semantic Color Mapping

| Semantic Purpose | Hex | Tailwind Class | Usage Context |
|-----------------|-----|--------------|---------------|
| **Primary / CTA** | `#2563eb` | `bg-blue-600` | Main buttons, links, active pagination |
| **Primary Hover** | `#1d4ed8` | `hover:bg-blue-700` | Button hover state |
| **Success** | `#059669` | `bg-green-600` | Positive actions, Approve buttons |
| **Success Hover** | `#047857` | `hover:bg-green-700` | Success hover |
| **Warning** | `#d97706` | `bg-yellow-600`, `text-yellow-600` | Pending moderation, amber badges |
| **Danger** | `#dc2626` | `bg-red-600` | Errors, Reject buttons, danger states |
| **Danger Hover** | `#b91c1c` | `hover:bg-red-700` | Danger hover |
| **Danger Background** | `#fef2f2` | `bg-red-100` | Error message backgrounds |

### Surface / Background Colors

| Purpose | Hex | Tailwind Class | Usage |
|---------|-----|--------------|-------|
| Page Background | `#f9fafb` | `bg-gray-50` | `<body>` background |
| Surface / Card | `#ffffff` | `bg-white` | All cards, modals, drawers |
| Image Placeholder | `#e5e7eb` | `bg-gray-200` | No-image fallback areas |
| Suggestion Background | `#eff6ff` | `bg-blue-50` | "Did you mean" suggestions |

### Text Colors

| Purpose | Hex | Tailwind Class | Usage |
|---------|-----|--------------|-------|
| Text Primary | `#1f2937` | `text-gray-800` | Headings, titles, main text |
| Text Secondary | `#6b7280` | `text-gray-500`, `text-gray-600` | Descriptions, metadata |
| Text Muted | `#9ca3af` | `text-gray-400` | Tertiary info, separators |
| Text Inverse | `#ffffff` | `text-white` | On colored backgrounds |
| Text Link | `#2563eb` | `text-blue-600` | Links, back navigation |

### Border Colors

| Purpose | Hex | Tailwind Class | Usage |
|---------|-----|--------------|-------|
| Border Default | `#e5e7eb` | `border-gray-200` | Card borders, consent banner |
| Border Input | `#d1d5db` | `border-gray-300` (default) | Form inputs |

---

## 2. Typography Scale

### Font Families

| Context | Font Stack | Source |
|---------|------------|--------|
| Primary | System UI (Tailwind default) | `font-sans` - system font stack |

### Font Sizes & Line Heights

| Token | Size (px) | Size (rem) | Line Height | Tailwind Class | Usage |
|-------|-----------|------------|-------------|----------------|-------|
| Display / Hero | 36px | 2.25rem | 1.25 | `text-4xl` | Hero headlines |
| Page Title | 30px | 1.875rem | 1.25 | `text-3xl` | Page titles, detail prices |
| Page Subtitle | 24px | 1.5rem | 1.5 | `text-2xl` | Section headers |
| Card Title | 20px | 1.25rem | 1.5 | `text-xl` | Ad card titles |
| Section Header | 18px | 1.125rem | 1.5 | `text-lg` | Section titles |
| Body | 16px | 1rem | 1.5 | `text-base` | Body text, form inputs |
| Secondary Text | 14px | 0.875rem | 1.5 | `text-sm` | Descriptions, form labels |
| Metadata | 12px | 0.75rem | 1.5 | `text-xs` | Footer info, fine print |

### Font Weights

| Weight | Value | Tailwind Class | Usage |
|--------|-------|--------------|-------|
| Regular | 400 | `font-normal` | Body text |
| Medium | 500 | `font-medium` | Labels, badge text |
| Semibold | 600 | `font-semibold` | Ad titles, section headers |
| Bold | 700 | `font-bold` | Prices, headings, CTA text |

### Line Height Scale

| Name | Value | Tailwind Class | Usage |
|------|-------|--------------|-------|
| Tight | 1.25 | `leading-tight` | Headings, display text |
| Normal | 1.5 | `leading-normal` | Body text, most content |
| Relaxed | 1.625 | `leading-relaxed` | Descriptions |

---

## 3. Spacing Scale (8px Grid)

Based on 8px base unit system as specified in `docs/01-spec/design-system.md` and `docs/06-design-system/instruction.md`.

| Token | Pixels | Tailwind Class | Usage |
|-------|--------|---------------|-------|
| `space-0` | 0px | `p-0`, `m-0` | No spacing |
| `space-1` | 4px | `p-1.5` (custom) or `pr-1` | Fine adjustments (not in default Tailwind) |
| `space-2` | 8px | `p-2`, `m-2` | Default gap, small padding |
| `space-3` | 12px | Not in default Tailwind | Between fields |
| `space-4` | 16px | `p-4`, `m-4` | Section padding, card padding |
| `space-5` | 24px | `p-6`, `m-6` | Large gaps (`gap-6`), section margins |
| `space-6` | 32px | `p-8`, `m-8` | Page margins, major section separation |
| `space-7` | 40px | Not in default Tailwind | Rarely used |
| `space-8` | 48px | `p-12`, `m-12` | Major section separation |
| `space-9` | 64px | `p-16`, `m-16` | Page margins, large separation |

**Note:** Tailwind's default spacing is 0.25rem (4px) increments. For 4px values, use `p-1` (0.25rem) or configure custom spacing in `tailwind.config.js`.

### Spacing Usage Mapping

| Component | Spacing Token | Tailwind Classes |
|-----------|--------------|-----------------|
| Page padding | `space-5` / `space-6` | `px-4 py-4` (container), `px-4 py-6` (main) |
| Card padding | `space-4` | `p-4` (ad cards), `p-6` (detail page) |
| Button padding | `space-2` / `space-3` | `px-3 py-1` (sm), `px-4 py-2` (md), `px-6 py-3` (lg) |
| Grid gap | `space-5` | `gap-6` (between cards) |
| Form spacing | `space-4` | `mb-4` (between fields) |
| Section margins | `space-6` | `mt-8`, `mb-8` (section separation) |

---

## 4. Corner Radius Values

| Token | Value | Tailwind Class | Usage |
|-------|-------|---------------|-------|
| `radius-sm` | 4px | `rounded` (rounded-sm in some configs) | Small badges, inline elements |
| `radius-md` | 8px | `rounded-lg` | **Standard cards, inputs, buttons** |
| `radius-lg` | 16px | `rounded-xl` (if configured), otherwise `rounded-lg` | Feature cards |
| `radius-full` | 9999px | `rounded-full` | Pills, circular buttons |

### Radius Usage in Components

| Component | Tailwind Class Used |
|-----------|---------------------|
| Buttons | `rounded-lg` (8px) |
| Cards | `rounded-lg` (8px) |
| Image placeholders | `rounded-t-lg` (top corners only) |
| Badges (status) | `rounded-full` (pill shape) |
| Form inputs | `rounded-lg` (8px) |
| Consent banner | No radius (full-width) |

---

## 5. Shadows / Elevation

| Token | CSS Value | Tailwind Class | Usage |
|-------|-----------|----------------|-------|
| Card Shadow | `0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24)` | `shadow` | Ad cards, surface elements |
| Card Hover | `0 4px 6px rgba(0,0,0,0.16), 0 2px 4px rgba(0,0,0,0.24)` | `hover:shadow-md` | Card hover states |
| Elevated | `0 4px 12px rgba(0,0,0,0.15), 0 2px 8px rgba(0,0,0,0.12)` | `shadow-lg` | Modals, elevated elements |
| Header | Subtle bottom border `border-b` + `shadow-sm` | `shadow-sm border-b` | Sticky header separation |
| Modal Overlay | `rgba(0,0,0,0.5)` bg | `bg-black bg-opacity-50` | Dialog backdrop |

---

## 6. Tailwind Class Equivalents (Quick Reference)

### Common Patterns

```html
<!-- Primary Button -->
<button class="px-6 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2">

<!-- Secondary Button -->
<a class="px-6 py-2 bg-white text-gray-700 rounded-lg font-medium border border-gray-300 hover:bg-gray-50 transition-colors">

<!-- Card Base -->
<article class="bg-white rounded-lg shadow hover:shadow-md transition-shadow">

<!-- Input Field -->
<input class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">

<!-- Badge Variants -->
<span class="px-2 py-1 text-xs font-medium rounded-full bg-green-100 text-green-800">Published</span>
<span class="px-2 py-1 text-xs font-medium rounded bg-yellow-100 text-yellow-800">Pending</span>
<span class="px-3 py-1 text-sm font-medium rounded-full bg-blue-100 text-blue-700">Edit</span>
```

### Color Classes Summary

```
Primary:    bg-blue-600 text-blue-800 focus:ring-blue-500
Success:    bg-green-600 text-green-800 bg-green-100 hover:bg-green-700
Warning:    bg-yellow-600 text-yellow-800 bg-yellow-100
Danger:     bg-red-600 text-red-800 bg-red-100 hover:bg-red-700
Secondary:  bg-gray-300 text-gray-700 bg-gray-100
```

---

## 7. Component-Specific Tokens Reference

### Ad Card (List)

| Element | Classes | Notes |
|---------|---------|-------|
| Container | `bg-white rounded-lg shadow hover:shadow-md transition-shadow` | 8px radius, subtle shadow |
| Image | `w-full h-48 object-cover rounded-t-lg` | 16:9 aspect (48px height) |
| Title | `font-semibold text-lg text-gray-800 mb-2 line-clamp-2` | 2-line clamp |
| Price | `text-blue-600 font-bold text-xl mb-2` | Prominent blue |
| Description | `text-sm text-gray-600 line-clamp-3 mb-3` | Secondary text |
| Metadata | `text-xs text-gray-500` | 12px, subtle |

### Header Navigation

| Element | Classes | Notes |
|---------|---------|-------|
| Header | `bg-white shadow-sm border-b` | Sticky with subtle shadow |
| Brand | `text-2xl font-bold text-gray-800` | Page title size |
| Container | `container mx-auto px-4 py-4` | Standard page container |

### Pagination

| State | Classes | Notes |
|-------|---------|-------|
| Default | `px-3 py-2 text-sm font-medium text-gray-700 bg-white border hover:bg-gray-50` | |
| Active | `px-3 py-2 text-sm font-medium text-white bg-blue-600` | Blue primary |

---

## 8. References

### Source Files Analyzed

- `docs/06-design-system/instruction.md` — Required token structure
- `docs/01-spec/design-system.md` — Existing design system specification
- `.ai/researches/Design_02/01-avito-design.md` — Avito color research (`#29A160` green, `#2E6BFF` blue)
- `.ai/researches/Design_02/02-jiji-olx-design.md` — Jiji/OLX patterns

### Actual Implementation Files

- `src/backend/templates/ads/list.html` — Grid, search, pagination
- `src/backend/templates/ads/partials/ad_list.html` — Ad card patterns
- `src/backend/templates/ads/detail.html` — Detail view, contact button
- `src/backend/templates/ads/dashboard.html` — Dashboard cards, status badges
- `src/backend/templates/ads/edit.html` — Form elements
- `src/backend/templates/admin/moderation/review.html` — Admin actions, modals
- `src/backend/templates/components/consent_banner.html` — Consent banner

---

## 9. Accessibility Notes

### Color Contrast

| Pair | Contrast Ratio | WCAG Status |
|------|---------------|-------------|
| Blue 600 on White | ~4.5:1 | AA for normal text (borderline) |
| Gray 800 on White | ~5.2:1 | AA for normal text ✓ |
| Gray 500 on White | ~4.6:1 | AA for normal text ✓ |
| White on Gray 300 | ~3.5:1 | AA for large text (18px+) |

### Focus States

```html
<!-- Standard focus ring -->
class="focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"

<!-- For buttons -->
class="focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"

<!-- For inputs -->
class="focus:outline-none focus:ring-2 focus:ring-blue-500"
```

### Touch Targets

- Minimum 44px × 44px for interactive elements
- Small buttons use `px-3 py-1` (effective 32px height)
- Standard buttons use `px-4 py-2` (effective 40px height)
- Large buttons use `px-6 py-3` (effective 48px height)