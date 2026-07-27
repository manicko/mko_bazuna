---
id: phase-02-detailed-plan-2
domain: planning
tags:
  - phase-2
  - ui-ux
  - design
  - frontend
related:
  - phase-02-detailed-plan-1
  - Design_01/classifieds_design_research_report
  - Design_01/01-list-view
  - Design_01/02-search-filters
  - Design_01/03-ad-detail
  - Design_01/04-homepage-nav
  - Design_01/05-posting-form
  - Design_01/06-mobile-patterns
  - Design_02/01-avito-design
  - Design_02/02-jiji-olx-design
  - Design_02/03-facebook-marketplace
  - ui-patterns
  - technical-specification
created: 2026-07-26
---

# Phase 2 Detailed Plan — UI/UX Enhancements

> Frontend improvements for Mko Bazuna based on Design_01 and Design_02 research analysis. This plan focuses exclusively on user interface and experience enhancements that can be implemented post-MVP.

---

## Overview

Phase 2 UI/UX enhancements are organized into six categories derived from comprehensive design research across Avito, OLX, Jiji, eBay, and Facebook Marketplace platforms:

1. **Ad Card Redesign** - Modern card-based layouts with improved visual hierarchy
2. **Search Interface** - Enhanced search bar with autocomplete and suggestions
3. **Filter System** - Improved filtering UI with progressive disclosure
4. **Ad Detail Page** - Refined single-ad experience with trust signals
5. **Mobile Optimization** - Mobile-first responsive patterns and gestures
6. **Design System Foundation** - Component library and design tokens

---

## 1. Ad Card Redesign (List/Grid View)

### 1.1 Current State Analysis

**Phase 1 MVP Cards:**
- Basic layout with image, title, price, location
- No trust signals or verification badges
- Limited visual hierarchy
- Simple 1-3 column responsive grid

### 1.2 Enhancement: Visual Hierarchy Optimization

**Target:** Align with Avito/Facebook Marketplace card patterns

| Element | Current | Enhanced | Source |
|---------|---------|----------|------|
| Image | Full card width | 3:2 aspect ratio (consistent) | Design_01/01-list-view |
| Price | Simple display | Bold, color-coded (#2E6BFF blue) | Design_02/01-avito-design |
| Title | Standard text | Clamped to 2 lines, 16px bold | Design_01/01-list-view |
| Location | Simple line | With distance indicator when available | Design_02/03-facebook-marketplace |
| Trust | None | Verification badges (Pro/Verified) | Design_02/01-avito-design |

**Implementation Tasks:**

1. **Update Ad Card Component** (`templates/ads/partials/ad_card.html`)
   - Add 3:2 aspect ratio container for images
   - Implement text clamp (`line-clamp-2`) for titles
   - Add price badge styling with blue accent color
   - Include status badges (new, verified, pro)

2. **Add Metadata Row** (`templates/ads/partials/ad_metadata.html`)
   - Location + relative time display
   - Distance indicator (when location detected)
   - Photo count badge (from research: "8/15 photos")
   - Condition indicator (New, Used - Good)

3. **Create Badge Components** (`templates/components/badge/`)
   - `verified_badge.html` - Orange circular (#FC942D)
   - `pro_badge.html` - Green rounded (#2EC966)
   - `new_badge.html` - Blue accent for recent listings

### 1.3 Card Variants

**Grid View (Desktop ≥1024px):**
```
[IMAGE 3:2]
Title (2-line clamp)
Price • Location
[Verified] [Pro] badges
```

**List View (Mobile <768px):**
```
[Thumbnail] [Title/Price on right]
[Location • Time • Photo count]
```

**Hybrid View (Tablet):**
```
2-column grid with condensed metadata
Touch targets ≥44px
```

---

## 2. Search Interface Enhancement

### 2.1 Sticky Search Bar

**Current:** Basic search input without persistent positioning

**Enhancement:** Implement sticky search with clear visual hierarchy
- Position: Sticky at top with `z-index: 1030`
- Background: Semi-transparent white (`rgba(255,255,255,0.96)`)
- Width: 70-80% of viewport on desktop (per research)
- Mobile: Full-width with 44px touch targets minimum

**Implementation Tasks:**

1. **Update Search Header** (`templates/components/search_bar.html`)
   - Add `position: sticky; top: 0`
   - Implement semi-transparent backdrop
   - Add clear visual states (default/focus)

2. **Add Voice Search Icon** (Desktop + Mobile)
   - Microphone icon for voice input capability
   - Use Web Speech API with progressive enhancement
   - No backend changes required

3. **Implement Recent Searches**
   - localStorage cache of last 10 queries
   - Display on search bar focus
   - Clear visual separation from suggestions

### 2.2 Search Result Feedback

**Enhancement:** Real-time result count and filter status
- Results count: "120 results found"
- Active filters: Chips displayed above grid
- Sort dropdown: Visible next to search bar

---

## 3. Filter System Improvement

### 3.1 Desktop Sticky Sidebar

**Current:** Basic filter panel without persistence

**Enhancement:** Implement sticky filter sidebar per Avito pattern
- Position: Fixed left sidebar (25% width on desktop)
- Persistent on scroll for easy adjustment
- Collapsible sections to reduce visual clutter

**Implementation Tasks:**

1. **Create FilterSidebar Component** (`templates/components/filter_sidebar.html`)
   - Sticky positioning with `position: sticky`
   - Accordion-style filter groups
   - Active filter count indicators

2. **Add Filter Chips** (`templates/components/filter_chips.html`)
   - Display above results grid
   - Individual X removal for each chip
   - "Clear all" action button
   - Color: `#2E6BFF` background, white text

### 3.2 Mobile Filter Drawer

**Enhancement:** Bottom sheet pattern for mobile filters
- Trigger button in top-right corner
- Full-screen slide-up panel
- "Apply" button at bottom (sticky on scroll)
- Touch targets minimum 44px

**Implementation Tasks:**

1. **Create MobileFilterDrawer Component**
   - HTMX-driven modal for filter panel
   - Touch-friendly slider controls
   - Large Apply/Cancel buttons

2. **Add Filter Badge Indicator**
   - Badge showing count of active filters
   - Visible on mobile header

### 3.3 Filter Categories

**Essential Filters (Always Visible):**
1. Category selection (hierarchical)
2. Price range (slider + inputs)
3. Location (geo-based with distance options)

**Advanced Filters (Progressive Disclosure):**
1. Condition (New, Used - Good, Used - Fair)
2. Seller type (Verified, Professional, Local)
3. Time-based (Today, This week, This month)

---

## 4. Ad Detail Page Enhancement

### 4.1 Image Gallery

**Current:** Basic image display

**Enhancement:** Implement carousel with fullscreen capability

**Implementation Tasks:**

1. **Create ImageGallery Component**
   - Horizontal thumbnail strip (desktop)
   - Swipe navigation (mobile)
   - Fullscreen lightbox with pinch-to-zoom
   - Dot indicators for current position

2. **Add Image Counter Badge**
   - Display "2/15 photos" positioned on image
   - Photo navigation cues

### 4.2 Trust Signal Integration

**Enhancement:** Add seller trust indicators
- Seller avatar (circular, 40px)
- Verification badges (phone, email, ID status)
- "Member since" date
- Response time indicator

**Implementation Tasks:**

1. **Create SellerTrustSection** (`templates/ads/partials/seller_info.html`)
   - Avatar + name layout
   - Star rating display (if implemented)
   - Verification badges inline

2. **Add Trust Badges**
   - "Verified seller" label
   - Response time ("Usually responds in 2 hours")
   - Transaction count ("42 transactions")

### 4.3 Action Button Placement

**Desktop Pattern:**
```
[Contact Seller] [Save to Favorites] [Share Listing]
```

**Mobile Pattern:**
- Sticky bottom bar with thumb-zone placement
- Primary CTA: Green background (`#0866FF`)
- Secondary actions: Outlined buttons

---

## 5. Mobile-First Design Patterns

### 5.1 Responsive Breakpoints

**Standard Implementation:**
- **Mobile:** 320px+ (single column, bottom navigation)
- **Tablet:** 768px+ (2-column grid, hybrid nav)
- **Desktop:** 1024px+ (3-4 column grid, sidebar filters)

### 5.2 Touch Optimization

**Touch Targets:**
- Minimum 44px × 44px for interactive elements
- 16px spacing between touch targets
- Thumb-zone placement for primary actions

**Gestures:**
- Swipe for image carousels (detail pages)
- Pull-to-refresh for listings
- Long-press for quick actions (save, share)

### 5.3 Information Density

**Mobile Priority:**
1. Image → Price → Title (primary)
2. Location + Time (secondary)
3. Description preview (collapse for mobile)

**Desktop Enhancement:**
- Full specification tables
- Detailed seller profile
- Map integration
- Similar items sidebar

---

## 6. Design System Foundation

### 6.1 Color System

**Primary Colors (from Avito/CSS analysis):**

| Purpose | Color | Usage |
|---------|-------|-------|
| Primary Action | `#0866FF` | Buttons, links, CTAs |
| Primary Hover | `#2455CC` | Hover states |
| Success | `#2EC966` | Verified badges, success states |
| Warning/Premium | `#FC942D` | Promotional badges, verified status |
| Text Primary | `#1C1E21` | Main content |
| Text Secondary | `#65676B` | Metadata, captions |

### 6.2 Typography Scale

| Element | Mobile Size | Desktop Size | Weight |
|---------|-------------|------------|--------|
| Card Title | 16px | 17px | 600 (semibold) |
| Body Text | 15px | 16px | 400 (regular) |
| Metadata | 13px | 14px | 400 |
| Price | 18px | 20px | 600 |

### 6.3 Spacing System

**Modular Spacing (per Avito pattern):**
- 2, 4, 6, 8, 10, 12, 16, 20, 24, 32, 40, 48, 56, 64px

**Application:**
- Card padding: 8px
- Grid gap: 16px
- Section margins: 16-24px

### 6.4 Component Library

**Core Components to Build:**

1. **Button Components** (`templates/components/button/`)
   - `primary.html` - Filled background, white text
   - `secondary.html` - Outlined, colored text
   - `ghost.html` - Transparent, no border

2. **Card Components** (`templates/components/card/`)
   - `ad_card.html` - Main listing card
   - `stats_card.html` - Dashboard statistics
   - `feature_card.html` - Category/feature highlights

3. **Form Components** (`templates/components/form/`)
   - `input.html` - Text inputs with validation states
   - `select.html` - Dropdown selects
   - `checkbox.html` - Filter checkboxes

4. **Navigation Components** (`templates/components/nav/`)
   - `pagination.html` - Page navigation
   - `breadcrumb.html` - Category hierarchy
   - `tab_bar.html` - Mobile bottom navigation

---

## 7. Implementation Sequence

### Phase 2A: Foundational UI (Weeks 1-2)

```
Ad Card Redesign ──► Filter Sidebar (Desktop)
    │
    ├──► Sticky Search Implementation
    └──► Component Library Base
```

### Phase 2B: Mobile Enhancement (Weeks 2-3)

```
Mobile Filter Drawer ──► Touch Optimization
    │
    ├──► Responsive Breakpoints
    └──► Gesture Integration
```

### Phase 2C: Detail Page Features (Weeks 3-4)

```
Image Gallery ──► Trust Signals
    │
    └──► Action Button Placement
```

### Phase 2D: Polish & Accessibility (Week 4)

```
Dark Mode Support ──► WCAG Compliance
    │
    └──► Performance Optimization
```

---

## 8. Dependencies & Constraints

### Technical Dependencies

| Feature | Dependency | Status |
|---------|------------|--------|
| Sticky search | CSS `position: sticky` | Native CSS |
| Image gallery | HTMX + minimal JS | Phase 1 has HTMX |
| Mobile drawer | No framework changes | Vanilla HTMX modal |
| Dark mode | CSS variables | Tailwind CSS supports |

### Cross-Plan Dependencies

**Note:** Tasks in this plan depend on backend features from Phase 2 Plan 1.

| This Plan (UI) | Depends On | Phase 2 Plan 1 | Reason |
|---------------|------------|---------------|--------|
| Ad Card Redesign | Thumbnail Generation | TN-001 | Card images require thumbnails for 3:2 aspect ratio and performance optimization |
| Image Gallery | Thumbnail Generation | TN-001 | Gallery needs multiple image variants (small/medium/large) for efficient loading |
| Trust Signals | SellerVerification Model | TS-003 | Trust badge display depends on verification data from Plan 3 |

### Backward Compatibility

- All enhancements are additive
- Existing templates remain functional
- No database schema changes required
- Feature flags recommended for gradual rollout

### WCAG Compliance Requirements

- Color contrast: AA level minimum
- Keyboard navigation support
- Screen reader compatibility (ARIA labels)
- Reduced motion preference support

---

## 9. Success Metrics

| Feature | Metric | Target |
|---------|--------|--------|
| Ad Card Redesign | Time to scan listing | -15% vs baseline |
| Search Interface | Search completion rate | +20% vs baseline |
| Filter System | Filter application success | >90% |
| Mobile UX | Mobile task completion | +25% vs baseline |
| Image Gallery | Detail page engagement | +30% time on page |
| Trust Signals | Contact initiation rate | +15% for verified sellers |

---

## 10. Risk Assessment

| Risk | Mitigation |
|------|------------|
| Complex JS breaking HTMX MPA | Keep interactions simple, test on low-end devices |
| Dark mode inconsistency | Use CSS variables for all colors |
| Mobile performance regression | Lazy load non-critical components |
| Accessibility gaps | Test with screen reader, automated a11y tools |

---

## References

- [Phase 2 Plan 1](.ai/plans/phase-02-detailed-plan-1.md)
- [Phase 2 Plan 3](.ai/plans/phase-02-detailed-plan-3.md)
- [Design_01 Research](.ai/researches/Design_01/classifieds_design_research_report.md)
- [Design_02 Research](.ai/researches/Design_02/)
- [UI Patterns](docs/01-spec/ui-patterns.md)
- [Technical Specification](docs/01-spec/technical-specification.md)
- [Avito Design System](.ai/researches/Design_02/01-avito-design.md)