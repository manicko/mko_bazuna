---
id: design-system-instruction
domain: design-system
tags:
  - design-system
  - instruction
  - documentation
related:
  - design-system-index
---

# Design System Documentation Instruction

## Purpose

Detailed specification of what content must be included in each design system block. Follow this structure when creating or updating design system documentation.

---

## tokens.md — Design Tokens

### Must Include:

#### 1. Color Palette
- **Primitive colors:** Base color values (hex, RGB, or OKLCH)
- **Semantic color mapping:** Purpose-driven aliases (primary, secondary, success, warning, error, info)
- **Surface/background colors:** Page, card, and overlay backgrounds
- **Text hierarchy colors:** Primary, secondary, tertiary, muted, inverse
- **Border colors:** Default, subtle, strong variations

#### 2. Typography Scale
- **Font families:** Primary stack with fallback chains
- **Font sizes:** Display (36px), page title (24px), card components (16-20px), body (16px), metadata (14px), fine print (12px)
- **Font weights:** Regular (400), Medium (500), Semibold (600), Bold (700)
- **Line heights:** Tight, normal, relaxed for each size
- **Text transformations:** Uppercase, capitalize where used

#### 3. Spacing Scale
- **Base unit:** 8px grid system
- **Scale values:** 0, 4, 8, 12, 16, 24, 32, 48, 64 (pixels)
- **Usage mapping:** Margins, padding, gaps, container widths

#### 4. Corner Radius
- **Small:** 4px (badges, chips)
- **Medium:** 8px (standard cards, inputs)
- **Large:** 16px (feature cards, modals)
- **Full/Pill:** 9999px (pills, circular buttons)

#### 5. Shadows/Elevation
- **Card shadows:** Default and hover states
- **Floating elements:** Sticky headers, FAB buttons
- **Modal/overlay shadows:** Elevated z-index elements

### Format Requirements:
- Use CSS custom property syntax (`--color-*`, `--text-*`)
- Include Tailwind class equivalents
- Provide usage examples per token
- Include accessibility notes where relevant

---

## components.md — Component Catalog

### Must Include:

#### 1. Atomic Components
- **Buttons:** Primary, secondary, disabled, icon variants with sizes
- **Inputs:** Text, number, textarea with states (default, focus, error, disabled)
- **Badges/Labels:** Status indicators, category tags, filter chips
- **Icons:** SVG iconography patterns (search, close, loading)

#### 2. Molecular Components
- **Search bar:** Input + button combination
- **Price display:** Price + currency formatting
- **Image placeholder:** Fallback when no image available
- **Form field group:** Label + input + helper text

#### 3. Organism Components
- **Ad Card:** Complete listing card (image, title, price, metadata)
- **Header Navigation:** Logo + nav links with sticky behavior
- **Filter Sidebar:** Desktop filter panel
- **Mobile Filter Drawer:** Slide-up mobile filter panel
- **Pagination Controls:** HTMX-powered page navigation
- **Contact Seller Card:** Deep-link contact mechanism
- **Consent Banner:** Privacy accept/decline banner

### Each Component Must Document:
- Visual variants (primary, secondary, hover states)
- Size variants (sm, md, lg)
- Accessibility requirements
- HTML/Tailwind code examples
- Usage context (which pages use it)

---

## layout.md — Layout Patterns

### Must Include:

#### 1. Grid System
- Responsive grid: `grid-cols-1 md:grid-cols-2 lg:grid-cols-3`
- Gap specifications per breakpoint
- Card width calculations

#### 2. Containers
- Max-width constraints per breakpoint
- Padding considerations
- Sidebar + content layout patterns

#### 3. Breakpoints
- Mobile: < 640px
- Tablet: 640px - 1024px
- Desktop: > 1024px

#### 4. Sticky/Fixed Patterns
- Header positioning
- Mobile filter button positioning
- Consent banner positioning

---

## accessibility.md — Accessibility Guidelines

### Must Include:

#### 1. WCAG Compliance
- Color contrast ratios (4.5:1 for text, 3:1 for large text)
- Touch target minimum (44px)
- Focus ring patterns

#### 2. Screen Reader Support
- ARIA labels for icon buttons
- Live regions for dynamic content
- Semantic HTML structure requirements

#### 3. Keyboard Navigation
- Tab order specifications
- Focus trapping for modals
- Escape key handling

---

## Cross-References

Always link to related documentation:
- Components → UI Patterns (../01-spec/ui-patterns.md)
- Layout → Architecture (../01-spec/architecture-structure.md)
- Tokens → None (this is the atomic source)