# Avito Design Analysis Report

## Executive Summary

Avito is a dominant classified ads platform operating across multiple markets (Morocco, Russia, Israel). This analysis examines the design patterns of Avito.ma (the Moroccan version) based on the live website analysis, combined with publicly available design system documentation and UX case studies from the Avito design team.

---

## 1. Overall Page Structure and Navigation Patterns

### Header Navigation
The header follows a sticky positioning pattern with a subtle shadow for depth separation:

**Desktop Layout (md/lg breakpoints):**
- Logo on the left (25px → 95px width transition at 992px)
- Navigation links centered (`<div>` with display flex, spaced items)
- Language/region selector on the right
- Height: 68px (mobile: 57px)

**Mobile Layout (below 992px):**
- Logo shrinks to icon-only or smaller
- Navigation links hidden (replaced by hamburger menu)
- Search bar appears below header with rounded corners

### Key Structural Elements:
- **Sticky Header**: `position: sticky; top: 0; z-index: 1030` with semi-transparent white background (`rgba(255,255,255,0.96)`)
- **Container Max-widths**: Responsive grid at 540px (sm) → 720px (md) → 960px (lg) → 1140px (xl) → 1280px (xxl)
- **Footer**: Full-width with background `#F2F2F2`, containing navigation links and legal information

### Visual Hierarchy:
- Clean, minimal aesthetic with ample whitespace
- Subtle shadows for elevation (e.g., `box-shadow: 0 2px 4px 0 rgba(0,0,0,0.1)`)
- No decorative elements - focuses on content and functionality

---

## 2. Category Organization and Hierarchy

Based on the CSS analysis and known Avito structure, the category hierarchy follows:

### Top-level Categories (Homepage):
1. **Immobilier** (Real Estate) - Property listings
2. **Véhicules** (Vehicles) - Cars, motorcycles, auto parts
3. **Emploi** (Jobs) - Job listings and recruitment
4. **Services** - Various service offerings
5. **Billeterie & Voyages** (Ticketing & Travel)
6. **Electronique** - Electronics and tech
7. **Animaux** - Pets and animals
8. **Maison & Jardin** - Home and garden
9. **Mode & Beauté** - Fashion and beauty
10. **Sport & Loisirs** - Sports and hobbies
11. **Culture & Éducation** - Books, education
12. **Autres** - Miscellaneous

### Location-Based Hierarchy:
- **Country → Region → City** filtering
- Breadcrumb navigation: `Home > Category > Subcategory`
- Dynamic URL structure supporting location hierarchy

---

## 3. Filter Sidebar Design and Interaction Patterns

### Desktop Filter Layout
The CSS reveals a sophisticated responsive grid system:

```css
/* Desktop: 25% sidebar, 75% content */
@media (min-width: 768px) {
  .filter-sidebar { max-width: 25%; }
  .content-area { max-width: 75%; }
}
```

### Filter Components Identified:

**Filter Chips/Tags (Above Results):**
- Pill-shaped tags with `#2E6BFF` background color
- White text, 4px 8px padding
- Rounded border-radius (8px)
- Hover states with background color changes

**Filter Groups (Sidebar):**
- Collapsible accordion sections
- Label styling: `#666666` text with 14px font
- Form controls integrated within filter sections

**Key Interaction Patterns:**
- **Multi-selection**: Users can select multiple values within a filter group
- **Applied Filters Display**: Clear chips above search results (not in sidebar)
- **Real-time Filtering**: Results update without full page reload (HTMX pattern suggested by project architecture)

### Mobile Filter Adaptation:
- Sidebar transforms to bottom sheet/drawer pattern
- "Apply" button pattern instead of auto-apply
- Touch-friendly controls with 40px+ minimum touch targets

---

## 4. Ad Card/List Item Design Specifics

### Card Structure (CSS Analysis):

```css
.ad-card {
  border-radius: 8px;
  background: #FFFFFF; /* Default */
  /* Alternative backgrounds: #FEF6E9, #EAF0FF */
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px;
}
```

### Card Components:

**Image Area:**
- Aspect ratio: 3:2 (consistent across all listings)
- Object-fit cover for uniform presentation
- Carousel indicators at bottom (4px padding-top)
- Navigation arrows appear on hover (desktop)

**Badge/Tag Positioning:**
```css
.top-right-badges { position: absolute; top: 8px; right: 8px; }
.bottom-left-badges { position: absolute; bottom: 8px; left: 8px; }
```

**Content Layout:**
1. **Title/Price Section** (padding: 8px)
   - Title: 16px font, font-weight: 400, 2-line clamp (`-webkit-line-clamp: 2`)
   - Price: Prominent positioning, color `#2D2D2D` or `#2E6BFF`

2. **Metadata Row** (below image)
   - Location with bullet separators (`•`)
   - Date posted
   - Small icons (24px circular badges for verified/pro status)

3. **Footer Section**:
   - Seller avatar (24px circular)
   - Seller name/truncated text
   - Action buttons (favorite, share, call)

**Status Indicators:**
- Verified badge: `#FC942D` background (orange)
- Pro seller: `#2EC966` background (green)
- Premium featured: `#2E6BFF` background (blue)

---

## 5. Mobile vs Desktop Adaptations

### Responsive Breakpoints (from CSS):

| Breakpoint | Behavior |
|------------|----------|
| < 576px | Mobile-first (single column cards, hamburger menu) |
| 375px-576px | Adjusting flex-basis, smaller paddings |
| 768px | Tablet adjustments (85% search bar, larger elements) |
| 992px | Desktop transition (sidebar visible, nav links shown) |
| 1200px+ | Widescreen optimizations |

### Mobile-Specific Patterns:

**Bottom Navigation (Inferred):**
- Action buttons fixed or context-aware
- Swipe gestures for image carousels
- Sticky CTA buttons for contact actions

**Touch Targets:**
- Minimum 40px height for interactive elements
- 100px height for list items (mobile vs 74px desktop)
- Circular badges with 24-32px dimensions

**Content Prioritization:**
- Price and title most prominent
- Secondary info collapsed or minimized
- Location as primary filter (not just metadata)

---

## 6. Search and Location-Based Filtering

### Search Bar Design:
- Rounded input (border-radius 6px on mobile)
- Background: `#F2F2F2` or `#F3F3F3`
- Placeholder text in 12px font
- Icon integration for clear/submit actions

### Location Pattern:
The URL structure `/fr/maroc/autos_et_vehicules` suggests:
- Region context embedded in URL path
- Cascading location selection (Country → Region → City)
- Location-specific homepage variants

### Search Results Layout:
- Grid-based card layout (flex-wrap)
- Gap: 16px between cards
- Responsive column count based on viewport

---

## Color Scheme Analysis

### Primary Colors:
| Purpose | Color | Usage |
|---------|-------|-------|
| Primary Action | `#29A160` (Green) | Submit buttons, primary CTAs |
| Primary Hover | `#20804C` | Green button states |
| Disabled State | `#94D0AF` | Disabled button background |
| Link Blue | `#2E6BFF` | Links, secondary buttons |
| Link Hover | `#2455CC` | Link hover states |
| Premium Badge | `#FC942D` | Promotional badges |
| Verified Badge | `#2EC966` | Verification indicators |

### Neutral Colors:
| Purpose | Color |
|---------|-------|
| Background Light | `#F2F2F2`, `#FAFAFA` |
| Background Dark | `#2D2D2D` |
| Text Primary | `#2D2D2D`, `#222223` |
| Text Secondary | `#4A4A4A` |
| Text Muted | `#666666` |
| Border | `#D0D0D0`, `#9B9B9B` |

---

## Typography Choices

### Font Families:
- Primary: **Rubik** (300, 400, 500 weights)
- Secondary: **Tajawal** (300, 400, 700 weights) - Arabic language support

### Text Styles:
| Element | Size | Weight | Color | Letter Spacing |
|---------|------|--------|-------|---------------|
| Body Text | 14px | 400 | #2D2D2D | 0.1px |
| Secondary Text | 14px | 200 | #666666 | 0.25px |
| Card Title | 16px | 400-500 | #222223 | 0.1px |
| Metadata | 12px | 400 | #666666 | 0.4px |
| CTA/Button | 14px | 400 | #FFFFFF/#4A4A4A | 1.05px |
| Breadcrumb | 14px | 400 | #4A4A4A | Default |

---

## UI Components Summary

### Core Components Identified:

1. **Buttons**
   - Primary: Green background, rounded (8px or 100px pill)
   - Secondary: White background with border
   - Icon buttons: Circular 24-32px with transparent background

2. **Cards/Listings**
   - Image-first layout
   - Consistent 3:2 aspect ratio
   - Status badges overlay
   - Price prominently displayed

3. **Badges/Labels**
   - Rounded pills (8px radius)
   - Color-coded for status types
   - Positioned absolutely on images

4. **Form Elements**
   - Rounded inputs (6-8px radius)
   - Gray borders with blue focus states
   - Toggle switches with custom styling

5. **Navigation**
   - Breadcrumb with `>` separators
   - Paginated results with numbered controls
   - Active page states in blue

---

## Success Factors for Avito as a Classifieds Platform

### 1. Visual Consistency
The design system approach ensures consistent user experience across platforms. Components are reusable and follow established patterns.

### 2. Information Architecture
- Clear category hierarchy with intuitive groupings
- Location-first approach for local commerce
- Prominent pricing and image presentation

### 3. Mobile-First Responsive Design
- Touch-friendly controls
- Adaptive layouts based on viewport
- Performance-optimized image handling

### 4. Trust Indicators
- Verification badges (orange for verified)
- Pro seller badges (green)
- Premium listing indicators (blue)

### 5. Fast Decision Making
- Price immediately visible
- Image quality emphasized
- Location proximity highlighted

---

## Technical Implementation Notes

### Based on Project Architecture (Mko Bazuna):
- **HTMX MPA Pattern**: Matches Avito's page-based filtering
- **Pydantic v2**: For DTO/validation at bot input boundaries
- **StrEnum for Constants**: Should be used for ad statuses, categories
- **Native PostgreSQL FTS**: Matches Avito's search infrastructure

---

## Recommendations for Mko Bazuna

1. **Adopt Similar Card Design**: 3:2 aspect ratio, status badges, consistent spacing
2. **Implement Progressive Enhancement**: Start simple, add HTMX interactions
3. **Use Color Coding**: Green for actions, blue for links, orange for promotions
4. **Prioritize Mobile First**: Design touch targets and mobile layouts before desktop
5. **Location-Centric Navigation**: Embed location in URL structure for SEO benefits
6. **Trust Elements**: Implement verified seller badges early

---

## Sources

- Avito.ma live CSS analysis (captured 2026-07-25)
- Avito Design System case study - Adil Dahmani & Nourdine Diouane
- AvitoTech Design System Figma workflow - Inna Letina
- Various UX design pattern references for classified ads platforms

---

*Report generated for Mko Bazuna project design research*