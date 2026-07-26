---
id: phase-plan-highlevel
domain: planning
tags:
  - planning
  - roadmap
  - mvp
related:
  - technical-specification
  - user-stories-index
---

# Mko Bazuna — High-Level Phase Development Plan

A phased rollout plan for the Telegram-driven classifieds board. Each phase builds incrementally with stable task boundaries.

---

## Phase 1: MVP Launch (Montenegro)

Launch core classifieds platform in Montenegro with Telegram-native ad posting and web browsing.

### Goals
- Enable sellers to post ads via Telegram bot
- Enable buyers to browse/search/filter ads without login
- Meet Montenegrin market requirements (Russian content + Montenegrin UI translation)
- Deploy production-ready system with basic moderation

### Key Features
- Telegram bot ad creation flow (step-by-step: category → city → title → description → price → photos)
- PostgreSQL full-text search over Russian content with Montenegrin→Russian query translation
- Category filtering via closed admin tree (django-mptt)
- City filtering with typo suggestions ("did you mean")
- Price range filtering
- Ad cards with image, title, price, location in responsive grid
- "Contact seller" deep-link to Telegram bot (anonymity-preserving)
- Hero search with combined keyword + city selector
- Sticky sidebar filters (desktop) and slide-up drawer (mobile)
- Filter chips for active selections
- Sort options: date newest / price low-high
- Consent banner with DECLINE (browse-only) and WITHDRAW (30-day erasure) states
- Admin moderation interface
- Basic analytics (Plausible + internal event model)

### Dependencies
- Django 5.2 + PostgreSQL 18 + django-mptt
- aiogram 3.x for Telegram bot
- deep-translator for query translation
- Tailwind CSS + HTMX for frontend

### Estimated Effort
- **8-10 developer weeks**
- Critical path: bot ad creation → web ad listing → search/filter integration → moderation

---

## Phase 2: Post-MVP Enhancements

Improve usability and seller experience after validating core flows.

### Goals
- Enhance seller dashboard capabilities
- Improve search and filter UX
- Add photo optimization

### Key Features
- Seller dashboard: list, edit, delete own ads (web interface)
- Ad reactivation from archived state
- Photo thumbnail generation (Pillow) for faster loading
- Photo lightbox/modal for detail pages
- Search autocomplete suggestions
- Saved search alerts (email/pending)
- Performance optimizations for search (query result caching)

### Dependencies
- Phase 1 core system stable
- Pillow for thumbnail generation

### Estimated Effort
- **3-4 developer weeks**

---

## Phase 3: Growth Features

Scale for increased adoption and user retention.

### Goals
- Expand platform capabilities
- Improve admin tooling
- Enable multi-city support planning

### Key Features
- Account state separation toggle (publish restriction / ban / deletion)
- Category editing interface (admin)
- Soft price editing (no re-moderation)
- "General / no city" ad handling
- Advanced analytics dashboard
- Rate limiting for search/ads
- Account merging for users with multiple Telegram accounts
- User-to-user messaging relay via bot (extended contact)
- Multi-select category filtering

### Dependencies
- Phase 2 enhancements stable
- Clear audit trail of ad lifecycle events

### Estimated Effort
- **4-5 developer weeks**

---

## Phase 4: Advanced Features

Enterprise-grade features and cross-market expansion.

### Goals
- International expansion support
- Advanced moderation
- Performance at scale

### Key Features
- Multi-currency support (deferred from phase 1)
- Tags system for ads
- EAV attributes for category-specific fields
- Third-party group monitoring (Telethon scraping)
- Celery/Redis for background jobs
- S3/R2/MinIO storage via django-storages
- DRF API for mobile app
- Admin batch operations
- ML-based moderation integration

### Dependencies
- Phase 3 stable with active user base
- Celery, django-storages, Telethon, DRF

### Estimated Effort
- **6-8 developer weeks** (ongoing)

---

## Feature Priority Matrix

| Feature | Phase | Rationale |
|---------|-------|-----------|
| Telegram bot ad creation | P1 | Core seller flow, no alternative input method |
| Web ad listing/browsing | P1 | Core buyer experience |
| Search + category filtering | P1 | 70%+ traffic starts in search |
| Consent banner | P1 | Legal requirement for GDPR-equivalent jurisdiction |
| Admin moderation | P1 | Quality control for published content |
| Seller dashboard | P2 | Post-validated core flows |
| Thumbnails | P2 | Performance optimization after MVP validation |
| Account state separation | P3 | Scaling moderation complexity |
| Multi-currency | P4 | Montenegro uses BAM only |
| Third-party scraping | P4 | Out of scope for MVP (decision B) |
| DRF API | P4 | Web MPA sufficient for MVP |