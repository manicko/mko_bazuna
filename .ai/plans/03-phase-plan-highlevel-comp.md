---
id: phase-plan-highlevel-comp
domain: planning
tags:
  - planning
  - timeline
  - phases
  - roadmap
related:
  - technical-specification
  - user-stories-index
  - db-schema
  - architecture-structure
---

# Mko Bazuna — Comprehensive Phase Development Plan

> High-level development roadmap with timeline, resource allocation, and risk mitigation for the Telegram-driven classifieds board MVP and subsequent phases.

## Executive Summary

Mko Bazuna is a Telegram-driven classifieds platform (Avito-like) where sellers post ads through a Telegram bot and buyers browse/search without registration. The MVP targets ~300 daily users with up to 500k ads in Montenegro, with Russian content and bilingual UI (Russian/Montenegrin).

| Phase | Target | Duration | Status |
|-------|--------|----------|--------|
| Phase 1 (MVP) | Core functionality | 12 weeks | Implementation in progress |
| Phase 2 | Scraping & multi-source | 6 weeks | Deferred |
| Phase 3 | Account state management | 3 weeks | Deferred |
| Phase 4 | PII erasure sweeps | Concurrent with Phase 1 | Partial |
| Phase 5 | Production hardening | Ongoing | Deferred |

---

## Phase 1: MVP (Core Functionality)

### Timeline: 12 Weeks

| Week | Milestones | Deliverables |
|------|------------|--------------|
| 1-2 | Foundation | Project structure, Docker setup, database schema, core models |
| 3-4 | Data layer | ORM models, migrations, FTS search, category/city seeds |
| 5-6 | Bot core | Telegram bot skeleton, login flow (US-S1), ad creation FSM (US-S2) |
| 7-8 | Web frontend | HTMX templates, responsive UI, ad listing (US-B1, US-B2, US-B3) |
| 9-10 | Moderation | Auto-check logic (US-A9, US-A10), admin interface (US-A1-US-A4) |
| 11-12 | Integration | Contact flow (US-B5), lifecycle sweeps, testing, production prep |

### Resource Allocation

| Role | FTE | Responsibilities |
|------|-----|------------------|
| Lead Developer | 1.0 | Architecture, core implementation, coordination |
| Backend Developer | 0.5 | Bot handlers, ORM models, moderation logic |
| Frontend Developer | 0.5 | Templates, HTMX components, mobile responsiveness |
| DevOps Engineer | 0.3 | Docker, nginx, PostgreSQL, migrations |
| QA/Test Engineer | 0.2 | Test coverage, integration testing |

### Critical Path Dependencies

```
Database Schema → Models → ORM → Bot FSM → Web Views → Moderation → Sweeps
     ↓              ↓       ↓      ↓          ↓          ↓        ↓
  Categories     User/Ad  Search   Login    Category    Auto-   Archive/
  & Cities       Models   Index    (US-S1)  Tree        Check   Delete
                       (US-B2)                        (US-A9) (US-S7)
```

### Key Deliverables by Week

**Weeks 1-2: Foundation**
- `src/backend/` - Django project structure with apps: users, ads, categories, locations, moderation, search
- `src/telegram_bot/` - Bot skeleton with aiogram 3.x
- `docker-compose.yml` - Services: db, web, bot, nginx
- `.env.example` - Configuration template

**Weeks 3-4: Data Layer**
- User model with `telegram_id` binding
- Ad model with `AdStatus` FSM states
- Category model (django-mptt tree)
- City model (closed Montenegro list)
- `search_vector` trigger SQL
- `moderation_criteria` singleton table

**Weeks 5-6: Bot Core**
- `/start` login flow with token validation
- Ad creation dialog: category → city → title → description → price → photos
- Draft persistence via `Ad.DRAFT` status in ORM
- Telegram photo download and local storage
- Montenegrin→Russian translation wrapper

**Weeks 7-8: Web Frontend**
- Base template with responsive Tailwind grid
- Ad card display (US-B4)
- Hero search with location (US-B2)
- Sticky sidebar filters (desktop) / drawer (mobile)
- Category hierarchical navigation
- Price range filter

**Weeks 9-10: Moderation**
- Automatic check: length rules, required fields, banned words, duplicate detection
- `ON_MODERATION_FAILED` 7-day purge sweep
- Admin dashboard: ad listing with status filters
- Manual moderation interface (US-A3, US-A11)
- `ModeratorActionLog` integration

**Weeks 11-12: Integration & Production**
- Contact deep-link generation and bot relay
- Archive (2mo) / delete (4mo) sweeps
- `consent_hard_delete` sweep (30-day erasure)
- Login token cleanup sweep
- Draft sweep (30-min timeout)
- Production deployment checklist

---

## Phase 2: Scraping & Multi-Source (Deferred)

### Timeline: 6 Weeks

| Week | Milestones | Deliverables |
|------|------------|--------------|
| 1-2 | Telethon integration | Userbot setup, group/channel connection |
| 3-4 | Content ingestion | Message parsing, image download, duplicate detection |
| 5-6 | Moderation pipeline | Scraped ad flow through auto-check, review queue |

### Key Features
- Telethon userbot for group/channel monitoring (deferred per decision B)
- Cross-post detection between scraped and bot-created ads
- Source attribution in `ads.source` field

---

## Phase 3: Account State Management (Deferred)

### Timeline: 3 Weeks

| Week | Milestones | Deliverables |
|------|------------|--------------|
| 1 | State separation | `ads_auto_publish`, `is_banned`, `is_deleted` flags |
| 2 | Consent banner | Banner UI, decline/withdraw distinction |
| 3 | Session handling | Cookie management, re-login flow |

### Key Features
- Three independent account states (O1/R4)
- Consent banner with decline vs. withdraw distinction (O2)
- Account deletion with 30-day erasure timeline (O3)

---

## Phase 4: PII Erasure Sweeps (Concurrent)

### Implementation Notes
- Runs as background sweep commands
- Seven advisory-locked sweep commands (zone C5/C7)
- `consent_hard_delete` - 30-day PII erasure
- `purge_failed_ads` - 7-day failed check cleanup
- `purge_rejected_ads` - 90-day rejected cleanup

---

## Risk Mitigation Strategy

### Technical Risks

| Risk | Severity | Mitigation | Owner |
|------|----------|------------|-------|
| `deep-translator` Google-scrape fragility | HIGH | Hard timeout (~500ms), mandatory fallback to original query, cache wrapper | Lead Developer |
| aiogram FSM PostgreSQL storage misconception | HIGH | Use `Ad.DRAFT` in shared ORM; document clearly; no Redis/Mongo | Lead Developer |
| django-mptt abandonment | MEDIUM | Pin Django `<6.0`, plan migration to recursive CTE before Django 6.0 upgrade | Lead Developer |
| HTTPS/TLS setup for production | MEDIUM | Use nginx with mkcert for local dev; Let's Encrypt for production | DevOps |
| Photo storage security (R6/R8) | HIGH | UUID v4 keys, JPEG validation (magic bytes), nginx `nosniff`, script execution block | Backend |
| Migration race condition | HIGH | Advisory locks on migrate, migrations BEFORE web+bot start | DevOps |

### Operational Risks

| Risk | Severity | Mitigation | Owner |
|------|----------|------------|-------|
| Moderator burn-in (day one required) | HIGH | Pre-configure admin user, document moderation policies | Product Owner |
| Category tree management | MEDIUM | django-mptt admin interface, seed with recommended tree | Backend |
| Search performance at scale | MEDIUM | GIN index on `search_vector`, monitor EXPLAIN ANALYZE at 50k rows | Lead Developer |

### Timeline Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Bot dialog complexity | MEDIUM | Implement FSM as step-by-step handlers, test incrementally |
| Thumbnail generation deferred | LOW | Accept Telegram-compressed photos, document UX limitation |
| celery/redis deferred | LOW | Use management commands + cron/systemd; re-evaluate at scale |

---

## Resource Requirements

### Development Environment
- Python 3.14 + Django 5.2 LTS + PostgreSQL 18
- Docker + Docker Compose
- Telegram Bot API account
- Google Translate API (via deep-translator)

### Production Environment
- VPS/Container hosting (2GB RAM minimum)
- PostgreSQL 18 database
- nginx for TLS termination and media serving
- PgBouncer for connection pooling
- Plausible for analytics (EU-hosted)

### Human Resources
- 1 Product Owner (decision authority)
- 1 Lead Developer (full-stack)
- 1 Backend Developer (ORM, bot logic)
- 1 Frontend Developer (templates, HTMX)
- 1 DevOps Engineer (deployment, monitoring)
- 1 QA Engineer (testing, automation)

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Response time | <2s | Ad listing, search results |
| Search accuracy | >90% | Category name search, fuzziness |
| Photo upload success | >99% | Telegram-compressed JPEG handling |
| Login success rate | >95% | Token claim completion |
| Moderation throughput | <5s | Auto-check on ad submit |
| Test coverage | >80% | pytest + coverage report |

---

## Deployment Milestones

### MVP Ready (End of Week 12)
- [ ] All core user stories implemented and tested
- [ ] Docker deployment tested in staging
- [ ] Admin user pre-configured
- [ ] Documentation complete
- [ ] Migration path verified
- [ ] Backup/restore procedures documented

### Production Launch
- [ ] TLS certificates configured
- [ ] Plausible analytics added
- [ ] Monitoring alerts configured
- [ ] Moderator trained
- [ ] Initial user base (beta testers) confirmed

---

## Dependencies Between Phases

```
Phase 1 MVP
    ├── Backend models (required)
    ├── Bot framework (required)
    ├── Web views (required)
    └── Phase 2 Scraping
    │       └── Telethon integration
    ├── Phase 3 Account states
    │       └── Consent banner (differentiates from Phase 1 decline)
    └── Phase 4 PII sweeps
            └── Implemented as sweep commands (runs in background)
```

---

## Notes

- All fixed values use `StrEnum` (rule 10)
- Pydantic v2 for DTOs and validation (rule 11)
- No `print()` statements; use logging (rule 12)
- Migrations required for all schema changes (rule 13)
- Documentation updated continuously (rule 14)