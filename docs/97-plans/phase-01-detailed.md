---
id: phase-01-detailed
domain: planning
tags:
  - planning
  - phase-1
  - mvp
  - current-state
  - remaining-work
related:
  - technical-specification
  - ui-patterns
  - search-patterns
  - filter-ui
  - user-stories-index
---

# Mko Bazuna — Phase 1 Detailed Plan (Current State & Remaining Work)

Consolidated plan combining executed work tracking with remaining tasks for MVP launch. Merged from phase-01-detailed-current and phase-01-detailed-updated.

---

## Current State Summary

Phase 1 work is **~95% complete**. The core architecture is fully implemented:

### ✅ Completed Foundation Layer
- **Database Models:** `Ad`, `AdImage`, `User`, `LoginToken`, `Category` (MPTT), `City`, `AnalyticsEvent`, `ModeratorActionLog`, `ModerationCriteria`
- **Core Enums:** `AdStatus`, `AdSource`, `AdSort`, `AdvisoryLockId`, `AnalyticsEventType`, `ModeratorActionType`, `CategoryRejectReason` in `apps/core/enums.py`
- **Migrations:** All migrations created including search vector triggers and category/city seeds
- **Settings:** Base, dev, prod, test configurations with security settings

### ✅ Completed Bot Layer
- **FSM States:** `AdCreateState` enum in `telegram_bot/states.py`
- **Login Handler:** Deep-link parsing, atomic token claim via UPDATE...RETURNING
- **Ad Create Handler:** Full step-by-step flow (category → city → title → description → price → photos)
- **Media Service:** Photo validation, UUID v4 storage keys, EXIF stripping
- **Auto-moderation:** Criteria validation with caching, status transitions
- **Contact Handler:** Anonymous buyer-seller relay via deep-link (tests exist)

### ✅ Completed Web Frontend Layer
- **Templates:** `ads/list.html`, `ads/detail.html`, `ads/dashboard.html`, `ads/edit.html`, `ads/partials/ad_list.html`, `users/login_issue.html`, `components/consent_banner.html`
- **Views:** Listings (`/`), detail, dashboard, edit, archive, reactivate, health check
- **Delete view:** `apps/ads/views/delete.py` - Implemented with ownership verification
- **Search:** FTS with query translation, GIN index, fuzzy category detection
- **Filters:** Category subtree, city, price range with did-you-mean
- **Template Tags:** `apps/core/templatetags/contact_tags.py` with `can_contact` filter
- **Utilities:** `apps/core/utils/sanitize.py` for log sanitization
- **Moderation Logging:** `apps/moderation/services/moderation_log.py`

### ✅ Completed Integration Layer
- **Sweep Commands:** `archive_sweep`, `delete_sweep`, `consent_hard_delete`, `sweep_drafts`, `cleanup_login_tokens`, `purge_failed_ads`, `purge_rejected_ads`
- **Analytics:** Event logging for search, contact, registration, ad publish
- **Admin:** Model registration, moderation interface

---

## 1. Missing Pieces for MVP Launch

### Critical (Must Have - Blocks Launch)

| Item | Location | Status | Notes |
|------|----------|--------|-------|
| **Logout view** | `apps/users/views/logout.py` (new) | ❌ Missing | `/logout/` referenced in dashboard template (line 24) but view not implemented; requires POST method with CSRF protection |
| **Search view consent context** | `apps/search/views/search.py:83-87` | ❌ Missing | `consent_shown` variable not passed to template context |

### High Priority (Already Verified)

| Item | Location | Status | Notes |
|------|----------|--------|-------|
| **Category seed migration** | `apps/categories/migrations/0002_seed_categories.py` | ✅ Complete | Contains Russian/Montenegrin category names with MPTT structure |
| **City seed migration** | `apps/locations/migrations/0002_seed_cities.py` | ✅ Complete | All 23 Montenegro municipalities seeded |
| **Static files configuration** | `config/settings/base.py` | ✅ Verified | Tailwind output.css path configured correctly |
| **nginx media protection config** | Docker/nginx config | ✅ Complete | X-Accel-Redirect internal `/protected-media/` location defined |
| **Contact handler tests** | `apps/core/tests/test_contact.py` | ✅ Complete | Tests exist for R2 conditions and pattern matching |
| **Delete view** | `apps/ads/views/delete.py` | ✅ Complete | Already implemented with ownership verification |

---

## 2. Bug Fixes Identified

### Critical Priority

| Item | Location | Notes |
|------|----------|-------|
| **`is_declined` message** | `telegram_bot/middlewares/permissions.py:119-120` | Both `is_declined` and `consent_revoked_at` return "Your account has been deleted." Should differentiate: declined users are in browse-only mode, not deleted. Message must say "browse-only mode". |

### Medium Priority

| Item | Location | Notes |
|------|----------|-------|
| **Translation source language** | `apps/search/services/query_translator.py` | Uses `source="bs"` (Bosnian) for Montenegrin queries. **This is intentional** - Google Translator treats Bosnian, Serbian, Croatian, and Montenegrin as similar languages. Documented as deliberate approximation. |

---

## 3. Security/Operational Hardening

### Critical Security Items

| Item | Location | Status | Notes |
|------|----------|--------|-------|
| **Logout view CSRF protection** | `apps/users/views/logout.py` (new) | ❌ Missing | Must implement POST-only logout with `{% csrf_token %}` protection |
| **Rate limiting - admin actions** | nginx config | ⚠️ Missing | No rate limiting on admin moderation actions; needs protection against brute-force |
| **Login token constant-time** | `apps/users/views/consent.py:209` | ⚠️ Verify | Token comparison uses DB lookup; verify uses `hmac.compare_digest` |
| **Rate limiting** | nginx/docker config | ✅ Complete | `limit_req_zone` defined for `/login/` and `/search/` endpoints (10r/s and 20r/s) |
| **nginx media MIME config** | nginx config file | ✅ Complete | MIME whitelist: `image/jpeg` only in `/protected-media/` location |

### Operational Items

| Item | Location | Status | Notes |
|------|----------|--------|-------|
| **Health check endpoint** | `apps/core/views.py` | ✅ Complete | `/health/` endpoint exists with DB check |
| **Backup script** | Docker/ops | ❌ Missing | Need backup/restore procedure documented |
| **Monitoring config** | Settings | ❌ Missing | No metrics endpoint exposed |

---

## 4. Testing Gaps

### Missing Test Coverage

| Test Area | Missing Tests | Priority |
|-----------|---------------|----------|
| **Search view** | No tests for edge cases (empty query, no results, special chars, consent context) | Medium |
| **Listings view** | Missing tests for category/city filter combinations | Medium |
| **Delete view** | Missing tests for ownership enforcement | Medium |
| **Web consent views** | Tests exist but coverage for cookie handling incomplete | Medium |

---

## 5. Documentation Updates Needed

| Document | Required Updates |
|----------|-----------------|
| `docs/01-spec/ui-patterns.md` | Add actual HTML template snippets from implemented views |
| `docs/01-spec/search-patterns.md` | Document query translation behavior with circuit breaker |
| `docs/99-agent/architecture.md` | Update with current file structure |

---

## 6. Implementation Priority Matrix

```
P0 (Blocker for launch):
- [ ] Add logout view at `/logout/` with POST method + CSRF protection
- [ ] Fix `is_declined` middleware message to say "browse-only mode" not "deleted"
- [ ] Add `consent_shown` to search view template context

P1 (High priority):
- [ ] Add rate limiting for admin actions in nginx config
- [ ] Verify `hmac.compare_digest` usage in login token comparison
- [ ] Add search view edge case tests

P2 (Medium priority):
- [ ] Update documentation with actual snippets
- [ ] Document backup/restore procedures
```

---

## 7. File Structure Reference (Actual)

```
src/backend/
├── apps/
│   ├── ads/
│   │   ├── models.py          # ✅ Ad, AdImage models
│   │   ├── views/
│   │   │   ├── listings.py    # ✅ listings, ad_detail, media_gate
│   │   │   ├── dashboard.py   # ✅ seller dashboard
│   │   │   ├── edit.py        # ✅ ad_edit, ad_archive, ad_reactivate
│   │   │   └── delete.py      # ✅ ad_delete IMPLEMENTED
│   │   └── migrations/
│   ├── categories/            # ✅ MPTT Category model + seeds
│   ├── locations/             # ✅ City model + seeds
│   ├── core/
│   │   ├── enums.py           # ✅ All StrEnum definitions
│   │   ├── services/contact.py # ✅ can_contact_seller, contact relay
│   │   ├── utils/sanitize.py  # ✅ Verified exists
│   │   └── management/commands/
│   ├── users/
│   │   ├── models.py          # ✅ User, LoginToken
│   │   ├── views/consent.py   # ✅ consent_accept/decline/withdraw, login_issue
│   │   └── services/
│   ├── search/
│   │   ├── views/search.py    # ✅ FTS search with translation
│   │   └── services/query_translator.py
│   ├── moderation/            # ✅ All models and services
│   └── analytics/             # ✅ AnalyticsEvent model
├── config/
│   └── settings/              # ✅ Base, dev, prod, test
└── templates/                 # ✅ All templates exist
```

```
src/telegram_bot/
├── states.py                  # ✅ AdCreateState enum
├── main.py                    # ✅ Bot entrypoint with middleware
├── handlers/
│   ├── login.py               # ✅ /start handler + deep-link
│   ├── ad_create.py           # ✅ Full FSM flow
│   └── contact.py             # ✅ Contact deep-link handler
├── middlewares/
│   └── permissions.py         # ✅ Account state middleware
├── services/media.py          # ✅ Photo validation/storage
├── schemas/message_payloads.py # ✅ Pydantic v2 DTOs
└── tests/                     # ✅ Comprehensive test suite
```

---

## 8. Next Steps for Phase 1 Completion

### Immediate (Next 1-2 days)

1. **Implement missing views (BLOCKERS):**
   - Logout view for `/logout/` endpoint with POST method and CSRF protection

2. **Fix bugs:**
   - Middleware message for `is_declined` state (should say "browse-only mode" not "deleted")
   - Add `consent_shown` to search view context

### Testing Sprint (Next 2-3 days)

1. Add search view edge case tests (including consent context verification)
2. Add delete view tests for ownership enforcement
3. Run full test suite with `uv run pytest --cov`

### Documentation Sprint (Parallel)

1. Update spec docs with actual implementation details
2. Document backup/restore procedures

---

## 9. Dependencies for Safe Deployment

| Service | Required Config |
|---------|----------------|
| **nginx** | Rate limiting, TLS termination, X-Accel-Redirect internal location |
| **PostgreSQL 18** | Required extensions: pg_trgm (for similarity), proper locale `ru_RU.UTF-8` |
| **Telegram Bot Token** | `BOT_TOKEN` env variable |
| **Bot Username** | `BOT_USERNAME` env variable for deep-links |
| **Media volume** | Shared Docker volume for `MEDIA_ROOT` |
| **Cache backend** | Redis recommended for Django cache (criteria caching) |

---

## 10. Risk Assessment for Remaining Work

| Risk | Mitigation | Current State |
|------|------------|---------------|
| **Logout CSRF** | Implement POST-only view with `{% csrf_token %}` | ❌ Unmitigated - view missing entirely |
| **Admin action rate limiting** | Add nginx rate limiting for `/admin/` paths | ❌ Unmitigated - no protection |
| **Token timing attacks** | Verify `hmac.compare_digest` usage | ⚠️ Gap exists in verification |
| **Translation source** | Document Bosnian code intentional for Montenegrin | ✅ Documented as approximation |
| **Seed data verified** | Categories/cities are correctly seeded | ✅ Verified |
| **nginx config complete** | Rate limiting and media protection already configured | ✅ Complete for existing endpoints |

---

## Plan Version History

- **phase-01-detailed-current_TODELETE.md** - Superseded by this consolidated plan
- **phase-01-detailed-updated_TODELETE.md** - Superseded by this consolidated plan
- **This document** - Master plan combining all three with corrected implementation status