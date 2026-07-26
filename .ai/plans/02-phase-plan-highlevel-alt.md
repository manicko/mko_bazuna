# Mko Bazuna — High-Level Phase Development Plan

**Version:** Phase Plan v2 (Alternative)  
**Date:** July 2026  
**Source Documents:** Design_01 research, Design_02 research, Technical Specification

---

## Executive Summary

This plan organizes Mko Bazuna development into four progressive phases, each building on the previous while maintaining architectural integrity. Phases are sequenced to maximize value delivery and enable early testing of critical paths. The phased approach follows the "two processes, one DB" architecture with Telegram bot and Django web sharing the ORM.

---

## Phase 1: Core Platform & Telegram Integration (MVP)

**Duration:** 6-8 weeks  
**Goal:** Launch-ready classifieds board with Telegram-native seller flow

### Milestones

| Milestone | Target | Key Deliverables |
|-----------|--------|-----------------|
| M1.1 | Week 2 | Telegram bot login and session management |
| M1.2 | Week 4 | Complete ad creation flow via bot |
| M1.3 | Week 6 | Web listing and search functionality |
| M1.4 | Week 8 | Moderation and admin dashboard MVP |

### Features (In Priority Order)

#### Seller Features (Telegram Bot)
1. **US-S1 — Login & Telegram binding**
   - QR code deep-link generation (`login_<token>`)
   - Atomic token claim via shared ORM
   - Session management with persistent cookies

2. **US-S2 — Create ad via bot**
   - Step-by-step dialog: category → city → title → description → price → photos
   - Category selection from closed admin tree with suggestions
   - 1-5 Telegram-compressed photos mandatory
   - Draft persistence via `Ad` row with status `DRAFT`
   - Preview before submission

3. **US-S5 — Edit ad** (basic)
   - Description/price/photo editing
   - Text edits trigger re-moderation (`PUBLISHED → ON_MODERATION`)
   - Price/photo edits immediate publishing

4. **US-S6 — Delete own ad**
   - Soft-delete to `DELETED` status

#### Buyer Features (Web)
5. **US-B1 — Browse without registration**
   - View `PUBLISHED` ads without login
   - Responsive card grid (mobile-first)

6. **US-B2 — Search**
   - Keyword search over title + description
   - Sort by date (newest) or price
   - Friendly empty states

7. **US-B3 — Filter**
   - Category/subcategory filtering (django-mptt)
   - City filtering (closed preset list)
   - Price range filter
   - HTMX-driven no-reload filtering

8. **US-B4 — Ad card display**
   - Image, title, price, location, category
   - No seller identity shown

9. **US-B5 — Contact seller**
   - Deep-link to bot (`contact_<ad_id>`)
   - Conditional rendering on ad status and seller availability

10. **US-B6/B7 — Browse by category/city**
    - Hierarchical category navigation
    - City-based filtering with "did-you-mean" suggestions

11. **US-B8 — Responsive UI**
    - Mobile: 1-column grid
    - Tablet: 2-column grid
    - Desktop: 3-column grid
    - Touch targets minimum 44px

12. **US-B9 — Multilingual UI**
    - Russian / Montenegrin language switch
    - Site shell translation only

#### Admin Features
13. **US-A1–A4 — Moderation dashboard**
    - View pending ads
    - Approve/reject with reason templates
    - Ban user (hide all ads)
    - Publish/unpublish control

14. **US-A7 — Category management**
    - Closed admin tree via Django admin
    - Category CRUD operations

15. **US-A10/A11 — Auto-moderation**
    - Text-based auto-check criteria
    - Criteria configuration interface

### Dependencies (Within Phase)

```
Telegram Login (S1) ──► Ad Creation (S2) ──► Edit/Delete (S5/S6)
       │                                           │
       ▼                                           ▼
  Search (B2) ◄──────────────────► Filter (B3) ──► Admin Moderation (A1-A4)
       │
       ▼
  Category/City (B6/B7)
```

### External Dependencies
- Telegram Bot API access
- PostgreSQL 18 database
- Deep-translator for Montenegrin→Russian translation

---

## Phase 2: Enhanced Discovery & Performance

**Duration:** 4-6 weeks  
**Goal:** Improve search effectiveness and platform scalability

### Milestones

| Milestone | Target | Key Deliverables |
|-----------|--------|-----------------|
| M2.1 | Week 2 | Category-name search with fuzzy matching |
| M2.2 | Week 4 | Performance optimization & caching |
| M2.3 | Week 6 | Advanced filtering UI |

### Features

#### Search Enhancement
1. **Category-name search** (O5/D1)
   - Denormalized `category_name` in `search_vector`
   - Weighted search (weight 'C' for category)
   - Fuzzy detection via `difflib` for single-word queries

2. **Query translation pipeline**
   - Montenegrin → Russian translation before FTS
   - Result tagging ("translated from Russian")

3. **Did-you-mean for cities**
   - `difflib.get_close_matches` for typo correction
   - Smart suggestions display

#### UI/UX Improvements
4. **Pagination**
   - HTMX-powered pagination for search results
   - Infinite scroll as progressive enhancement option

5. **Filter chips/tags**
   - Visual active filter indicators
   - Individual filter removal
   - "Clear all" option

6. **Sticky sidebar filters** (desktop)
   - Persistent filter panel on scroll
   - Collapsible advanced filter sections

7. **Mobile filter drawer**
   - Bottom sheet pattern for mobile filters
   - Apply/cancel actions

#### Performance
8. **Database indexing**
   - GIN index on `search_vector`
   - Category and city lookup indexes
   - Analytics event optimization

9. **Image handling**
   - Lazy loading for off-screen images
   - WebP format consideration

### Dependencies

```
Phase 1 Core ◄── Search Enhancement (category in search_vector)
         │
         └────► Filter UI (enhanced patterns)
```

---

## Phase 3: Seller Experience & Analytics

**Duration:** 4-5 weeks  
**Goal:** Complete seller workflow and basic analytics

### Milestones

| Milestone | Target | Key Deliverables |
|-----------|--------|-----------------|
| M3.1 | Week 2 | Seller dashboard (web) |
| M3.2 | Week 3 | Account management features |
| M3.3 | Week 5 | Basic analytics & metrics |

### Features

#### Seller Dashboard (Web)
1. **My Ads listing**
   - Published, pending, archived, rejected tabs
   - Status indicators on each ad
   - Quick action buttons (edit, delete, reactivate)

2. **Ad reactivation** (US-S7)
   - Archive state management
   - Re-moderation on reactivation

3. **Account deletion flow** (US-S8)
   - Soft-delete initiation
   - Consent banner for DECLINE vs WITHDRAW (O2/R3)

4. **Publishing ban toggle** (US-S9/O1)
   - Admin-controlled `ads_auto_publish=False`
   - Existing ads hidden while active

5. **Session management**
   - Logout functionality
   - Account status display

#### Admin Enhancements
6. **US-A8/A9 — PII management**
   - Consent withdrawal handling
   - PII erasure task scheduler
   - Audit logging for deletions

7. **US-A5–A6 — User management**
   - Account state transitions
   - Moderator action logs

#### Analytics
8. **Product metrics** (US-L)
   - `REGISTRATION_CREATED`, `AD_PUBLISHED`, `SEARCH_PERFORMED`, `CONTACT_INITIATED`
   - Admin CLI `show_metrics` command
   - Plausible integration for web traffic

9. **PII sweep task**
   - 30-day erasure sweep (zone R1)
   - Idempotent cleanup task

### Dependencies

```
Phase 2 Search ◄── Seller Dashboard (web)
             │
             └──► Account State Management (soft-delete + consent)
```

---

## Phase 4: Trust, Safety & Advanced Features

**Duration:** 5-7 weeks  
**Goal:** Production-hardened platform with trust signals and advanced listing features

### Milestones

| Milestone | Target | Key Deliverables |
|-----------|--------|-----------------|
| M4.1 | Week 3 | Trust badge system |
| M4.2 | Week 5 | Photo quality enforcement |
| M4.3 | Week 7 | Production readiness |

### Features

#### Trust & Verification
1. **Seller trust signals** (Design_02 recommendation)
   - Verification badges (phone/email)
   - Response time indicators
   - Transaction count display

2. **Ad quality signals**
   - Photo count badges
   - "New in last 24 hours" indicators
   - Featured/promoted listing support

#### Photo System Enhancement
3. **Photo moderation**
   - Basic quality checks (blur, inappropriate content)
   - Manual moderation tools for failed checks

4. **Photo thumbnail generation** (O4/storage consideration)
   - Pillow-based thumbnail creation
   - Multiple sizes for different contexts

#### Content Management
5. **Ad lifecycle enforcement** (US-S7/J)
   - 2-month archive timer
   - 4-month hard delete timer
   - Timer reset on republish

6. **Moderation criteria UI** (US-A11)
   - Admin interface for text-based criteria
   - Length, count, and pattern validation rules

#### Production Readiness
7. **Error handling & logging**
   - Structured logging throughout
   - Error pages and retry paths
   - Admin alert system

8. **Performance at scale**
   - Query optimization for 500k ads
   - Connection pooling via PgBouncer
   - CDN consideration for static assets

9. **Security hardening**
   - Rate limiting on bot interactions
   - Input validation on all forms
   - Session security review

### Dependencies

```
Phase 3 Analytics ◄── Trust Badge System
               │
               └──► Photo Enhancement ◄── Moderation Criteria (admin)
```

---

## Cross-Phase Architecture Considerations

### Design System Implementation (from Design_01 research)
- **StrEnum for all constants** (categories, statuses, event types)
- **Mobile-first responsive design** (320px → 768px → 1024px breakpoints)
- **Card-based layout** with 3:2 aspect ratio for ad images
- **Touch target compliance** (minimum 44px)
- **Progressive disclosure** for filters and long content

### Technology Stack Alignment (from Design_02 research)
- **HTMX MPA pattern** for search/filter interactions
- **Native PostgreSQL FTS** with GIN indexes
- **Color system:** Green for actions, blue for links, orange for promotions
- **Typography:** System fonts, clear hierarchy (16px title, 14px body)

### Regional Adaptation (from Jiji/OLX analysis)
- **Montenegro-focused city list**
- **Trust-first approach** for emerging market context
- **Multi-language support** (Russian content, Montenegrin UI)
- **Mobile-optimized touch targets** for mid-range devices

---

## Risk Assessment & Mitigations

| Risk | Phase Affected | Mitigation |
|------|----------------|------------|
| Telegram API changes | P1 | Version-lock aiogram, monitor releases |
| Moderation false positives | P1-P4 | Multi-stage review, clear rejection templates |
| Photo storage scaling | P4 | Local storage Phase 1, deferred S3 swap |
| Search performance at 500k ads | P2 | GIN indexes, query optimization, caching |
| Trust scams in emerging market | P4 | Verified badges, response metrics, safety tips |

---

## Success Metrics by Phase

| Phase | Metrics |
|-------|---------|
| P1 | Daily active sellers ≥ 50, ads published ≥ 200/month, search response < 2s |
| P2 | Search success rate ≥ 80%, filter application < 1s |
| P3 | Seller retention ≥ 60% (return after first ad), session stability |
| P4 | Trust metric adoption ≥ 40% sellers verified, photo quality ≥ 95% pass rate |

---

## Implementation Notes

1. **Two-process deployment:** Migrations run once before web+bot start
2. **No built-in PG FSM storage:** Bot state persisted as `Ad` DRAFT rows
3. **All fixed values use StrEnum** (no plain strings/dicts)
4. **Pydantic v2 for validation** at bot input boundaries
5. **WCAG AA/AAA compliance** required for accessibility

---

## References

- [Design_01 Research](.ai/researches/Design_01/classifieds_design_research_report.md)
- [Design_02 Research](.ai/researches/Design_02/01-avito-design.md)
- [Technical Specification](docs/01-spec/technical-specification.md)
- [UI Patterns](docs/01-spec/ui-patterns.md)
- [User Stories](docs/04-user-stories/index.md)