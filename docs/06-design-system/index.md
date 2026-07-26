---
id: design-system-index
domain: design-system
tags:
  - design-system
  - overview
  - tokens
  - components
related:
  - ui-patterns
  - search-patterns
  - filter-ui
  - technical-specification
---

# Mko Bazuna — Design System

## Purpose

Comprehensive design system documentation for the Mko Bazuna classifieds platform. Provides single-source-of-truth for visual design decisions, component patterns, and implementation guidelines for both developers and future designers.

## Main Concepts

- **Mobile-first responsive:** All components designed for touch interfaces first
- **Marketplace-optimized:** Patterns prioritize quick scanning and decision-making
- **Telegram-integrated:** Contact flows preserve seller anonymity via deep-links
- **Two-language support:** Russian (content) + Montenegrin/Bosnian (UI) with translation layer
- **HTMX-driven:** No client-side JS framework; progressive enhancement via HTMX

## Document Structure

| File | Description |
|------|-------------|
| `index.md` | This overview + principles + navigation |
| `tokens.md` | Design tokens: colors, typography, spacing, radius, shadows, elevation |
| `components.md` | Component catalog: buttons, cards, forms, navigation, status indicators |
| `layout.md` | Layout patterns: grid system, responsive breakpoints, containers |
| `accessibility.md` | Accessibility guidelines: WCAG compliance, keyboard navigation, screen readers |
| `instruction.md` | Documentation requirements and content structure guide |

## Design Principles

### 1. Visual Hierarchy for Decision-Making
- Price is the primary decision factor → use `text-blue-600` prominent styling
- Image second → consistent 16:9 aspect ratio
- Title third → `font-semibold` for quick scanning
- Metadata last → muted colors, smaller text

### 2. Trust Through Transparency
- Seller identity never shown on site (Telegram-only)
- Verification badges for admin-approved sellers
- Clear status indicators (published, pending, rejected)

### 3. Progressive Disclosure
- Truncated descriptions in list view (`line-clamp-3`)
- Full content on detail pages
- HTMX pagination for seamless browsing

### 4. Accessibility First
- Minimum 44px touch targets
- Color contrast ≥ 4.5:1 for text
- Semantic HTML + ARIA for screen readers

## Color Philosophy

| Purpose | Color | Tailwind Class |
|---------|-------|---------------|
| Primary action | Blue | `bg-blue-600` |
| Success/published | Green | `bg-green-600` |
| Warning/pending | Amber | `bg-amber-600` |
| Error/rejected | Red | `bg-red-600` |

## Typography Scale

Based on 8px grid with modular scale:
- Display: 36px (hero)
- Page title: 24px
- Card title: 18px (20px)
- Body: 16px
- Metadata: 14px
- Fine print: 12px

## Related Documentation

- [UI Patterns](../01-spec/ui-patterns.md) — Detailed patterns implementation
- [Filter UI](../01-spec/filter-ui.md) — Filtering patterns
- [Search Patterns](../01-spec/search-patterns.md) — Search UX patterns
- [Technical Specification](../01-spec/technical-specification.md) — Core business rules