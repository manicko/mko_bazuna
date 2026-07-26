---
id: design-system-accessibility
domain: design-system
tags:
  - accessibility
  - wcag
  - aria
  - screen-readers
related:
  - design-system-index
  - components
---

# Accessibility Guidelines

> WCAG 2.1 AA compliance requirements and implementation patterns.

## Color Contrast Requirements

### Minimum Ratios

| Text Type | Minimum Ratio | Examples |
|-----------|---------------|----------|
| Normal text (16px) | 4.5:1 | Body text, labels |
| Large text (18px+) | 3:1 | Headings, prices |
| UI controls | 3:1 | Buttons, form borders |

### Verified Combinations

| Background | Text | Ratio | Status |
|------------|------|-------|--------|
| White `#ffffff` | Blue 600 `#2563eb` | ~4.5:1 | ✅ AA pass (borderline) |
| White `#ffffff` | Gray 800 `#1f2937` | ~5.2:1 | ✅ AA pass |
| White `#ffffff` | Gray 500 `#6b7280` | ~4.6:1 | ✅ AA pass |
| White `#ffffff` | Gray 400 `#9ca3af` | ~3.5:1 | ✅ AA for large text |

### Notes

- Price text (`text-blue-600`) is typically 20px+ → 3:1 minimum applies
- All interactive states must maintain contrast in hover/disabled states

---

## Touch Target Requirements

### Minimum Size

- **Interactive elements:** 44px × 44px minimum
- **Preferred size:** 48px × 48px for primary actions

### Button Heights

| Size Class | Padding | Effective Height | Usage |
|------------|---------|------------------|-------|
| Small (`px-3 py-1`) | 12px × 4px | ~32px | Non-critical, tabs |
| Medium (`px-4 py-2`) | 16px × 8px | ~40px | Secondary actions |
| Large (`px-6 py-3`) | 24px × 12px | ~48px | **Primary CTAs** |

### Implementation Notes

```html
<!-- Good: 48px touch target -->
<button class="px-6 py-3">Approve</button>

<!-- Acceptable for secondary -->
<button class="px-4 py-2">Cancel</button>

<!-- Requires review for touch -->
<button class="px-4 py-2 text-sm">Consent banner buttons at 36px</button>
```

---

## Focus Management

### Focus Ring Pattern

```html
<!-- All interactive elements -->
<button class="focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2">

<!-- Inputs -->
<input class="focus:outline-none focus:ring-2 focus:ring-blue-500">
```

| Property | Value |
|----------|-------|
| Outline | `focus:outline-none` |
| Ring width | `focus:ring-2` |
| Ring color | `focus:ring-blue-500` |
| Offset | `focus:ring-offset-2` |

### Focus Visible (Future Enhancement)

```css
/* Ensure focus visible for keyboard users */
.focus-visible {
    @apply focus:ring-2 focus:ring-blue-500;
}
```

---

## Screen Reader Support

### ARIA Labels

Required for icon-only interactive elements:

```html
<button aria-label="Close" class="...">
    <svg><!-- close icon --></svg>
</button>

<button aria-label="Open filters" class="...">
    Filters
</button>
```

### Navigation Landmarks

```html
<nav aria-label="Page navigation">...</nav>
<header role="banner">...</header>
<main role="main">...</main>
```

### Status Announcements

```html
<div role="dialog" aria-live="polite" aria-label="Privacy consent">
    <!-- Consent banner content -->
</div>
```

### Pagination Current Page

```html
<span aria-current="page" class="bg-blue-600 text-white">
    {{ page_obj.number }}
</span>
```

---

## Keyboard Navigation

### Tab Order

- Tab order follows visual order (natural DOM flow)
- HTMX links and forms are naturally keyboard accessible
- No custom focus management needed for basic flows

### Modal/Drawer Navigation

Planned for future implementation:

| Action | Key |
|--------|-----|
| Open drawer | Enter/Space on trigger |
| Close drawer | Escape |
| Focus trap | Tab cycles within drawer |
| Apply | Enter on Apply button |

### Skip Links (Future Enhancement)

```html
<a href="#main-content" class="sr-only focus:not-sr-only">
    Skip to main content
</a>
```

---

## Form Accessibility

### Label Association

Every input must have an associated label:

```html
<label for="title" class="block font-medium mb-2">Title</label>
<input type="text" id="title" name="title">
```

### Error Messaging

```html
<input 
    aria-invalid="true" 
    aria-describedby="title-error"
>
<p id="title-error" class="text-red-600">Title is required</p>
```

| State | ARIA |
|-------|------|
| Error | `aria-invalid="true"` + `aria-describedby` |
| Required | `required` attribute |
| Optional | No special ARIA needed |

### Checkbox Groups

```html
<label class="flex items-center gap-2">
    <input 
        type="checkbox" 
        name="category" 
        value="{{ cat.id }}"
        class="w-4 h-4 rounded focus:ring-blue-500"
    >
    <span class="text-sm">{{ cat.get_name }}</span>
</label>
```

---

## Image Accessibility

### Alt Text

```html
<img src="{{ url }}" alt="{{ ad.title }}" loading="lazy">
```

| Context | Alt Text |
|---------|----------|
| Ad image | `alt="{{ ad.title }}"` |
| Decorative placeholder | `alt=""` or omit |
| Icon (decorative) | `aria-label` on parent button |

### Loading Attribute

Always use `loading="lazy"` for ad images in listings:

```html
<img loading="lazy" class="...">
```

---

## Language Support

### Multilingual Considerations

| Script | Requirements |
|--------|--------------|
| Cyrillic (Russian) | Full system font stack support |
| Latin (Montenegrin/Bosnian) | Standard Latin extended |
| Mixed content | No special handling needed |

### Font Smoothing

```css
body {
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}
```

---

## Accessibility Checklist for Components

| Component | ✅ Implemented | ❌ Missing |
|-----------|----------------|------------|
| Primary Button | Focus ring, `aria-label` for icon buttons | Touch target size (36px in consent) |
| Secondary Button | Focus ring | — |
| Icon Button | `aria-label` required | — |
| Form Inputs | Labels, focus ring | Error states not in templates |
| Pagination | `aria-current="page"` | — |
| Consent Banner | `role="dialog"`, `aria-live` | 36px button height |
| Ad Card | Semantic `<article>`, link wrapper | Image alt text in some templates |
| Search Bar | `aria-label` on input | — |
| Modal/Drawer | Documented | Not yet implemented |