---
id: phase-01-detailed-current
domain: planning
tags:
  - planning
  - phase-1
  - mvp
  - current-state
  - implementation-gaps
related:
  - technical-specification
  - ui-patterns
  - search-patterns
  - filter-ui
  - user-stories-index
---

# Mko Bazuna — Phase 1 Detailed Current State & Remaining Work

Analysis of existing codebase to identify gaps, missing pieces, and planning for MVP launch completion.

---

## Current State Summary

Phase 1 work is substantially complete. The core architecture is implemented:

### ✅ Completed Foundation Layer
- **Database Models:** `Ad`, `AdImage`, `User`, `LoginToken`, `Category` (MPTT), `City`, `AnalyticsEvent`, `ModeratorActionLog`, `ModerationCriteria`
- **Core Enums:** `AdStatus`, `AdSource`, `AdSort`, `AdvisoryLockId`, `AnalyticsEventType`, `ModeratorActionType`, `CategoryRejectReason` in `apps/core/enums.py`
- **Migrations:** All migrations created including search vector triggers
- **Settings:** Base, dev, prod, test configurations with security settings (SECURE_SSL_REDIRECT, CSRF_COOKIE_SECURE, etc.)

### ✅ Completed Bot Layer
- **FSM States:** `AdCreateState` enum in `telegram_bot/states.py`
- **Login Handler:** Deep-link parsing, atomic token claim via UPDATE...RETURNING
- **Ad Create Handler:** Full step-by-step flow (category → city → title → description → price → photos)
- **Media Service:** Photo validation, UUID v4 storage keys, EXIF stripping
- **Auto-moderation:** Criteria validation with caching, status transitions
- **Contact Handler:** Anonymous buyer-seller relay via deep-link (tests exist)

### ✅ Completed Web Frontend Layer
- **Templates:** `ads/list.html`, `ads/detail.html`, `ads/dashboard.html`, `ads/edit.html`, `ads/partials/ad_list.html`, `users/login_issue.html`, `components/consent_banner.html`
- **Views:** Listings (at `/`), detail, dashboard, edit, delete, archive, reactivate, health check
- **Search:** FTS with query translation, GIN index, fuzzy category detection
- **Filters:** Category subtree, city, price range with did-you-mean
- **Template Tags:** `apps/core/templatetags/contact_tags.py` with `can_contact` filter (verified present)
- **Utilities:** `apps/core/utils/sanitize.py` for log sanitization (verified present)
- **Moderation Logging:** `apps/moderation/services/moderation_log.py` (verified present)
- **Contact Tests:** `apps/core/tests/test_contact.py` covers R2 conditions and pattern matching

### ✅ Completed Integration Layer
- **Sweep Commands:** `archive_sweep`, `delete_sweep`, `consent_hard_delete`, `sweep_drafts`, `cleanup_login_tokens`, `purge_failed_ads`, `purge_rejected_ads`
- **Analytics:** Event logging for search, contact, registration, ad publish
- **Admin:** Model registration, moderation interface

---

## 1. Missing Pieces for MVP Launch

### Critical (Must Have)

| Item | Location | Status | Notes |
|------|----------|--------|-------|
| **Logout view** | `apps/users/views/consent.py` or separate file | ❌ Missing | `/logout/` referenced in dashboard template (line 24) but not implemented |
| **Search view consent context** | `apps/search/views/search.py:83-87` | ⚠️ Missing | `consent_shown` variable not passed to template context |

### High Priority

| Item | Location | Status | Notes |
|------|----------|--------|-------|
| **Category seed migration** | `apps/categories/migrations/0002_seed_categories.py` | ✅ Complete | Contains Russian/Montenegrin category names with MPTT structure |
| **City seed migration** | `apps/locations/migrations/0002_seed_cities.py` | ✅ Complete | All 23 Montenegro municipalities seeded |
| **Static files configuration** | `config/settings/base.py` | ✅ Verified | Tailwind output.css path configured correctly |
| **nginx media protection config** | Docker/nginx config | ✅ Complete | X-Accel-Redirect internal `/protected-media/` location defined |
| **Contact handler tests** | `apps/core/tests/test_contact.py` | ✅ Complete | Tests exist for R2 conditions and pattern matching |

---

## 2. Testing Gaps

### Missing Test Coverage

| Test Area | Missing Tests | Priority |
|-----------|---------------|----------|
| **Search view** | No tests for edge cases (empty query, no results, special chars, consent context) | Medium |
| **Listings view** | Missing tests for category/city filter combinations | Medium |
| **Edit view** | Missing tests for C2 text-edit behavior | Medium |
| **Delete view** | Missing tests for own-ad-only enforcement | Medium |
| **Web consent views** | Tests exist but coverage for cookie handling incomplete | Medium |
| **Admin views** | No tests for moderation review interface | Low |
| **Template rendering** | No template rendering tests for empty states | Low |

### Test Execution Gaps

| Test Type | Status | Notes |
|-----------|--------|-------|
| **Bot handler integration tests** | ⚠️ Partial | `conftest.py` has fixtures but some handlers lack full tests |
| **Media security tests** | ✅ Complete | `test_media_security.py` covers access control, EXIF, path traversal |
| **Sweep command tests** | ✅ Complete | `test_sweep_commands.py` comprehensive |
| **Ad lifecycle tests** | ⚠️ Partial | `test_ad_lifecycle.py` but missing REJECTED state tests |
| **Contact handler tests** | ✅ Complete | `test_contact.py` covers R2 conditions and pattern matching |

---

## 3. Documentation Updates Needed

| Document | Required Updates |
|----------|-----------------|
| `docs/01-spec/ui-patterns.md` | Add actual HTML template snippets from implemented views |
| `docs/01-spec/search-patterns.md` | Document query translation behavior with circuit breaker |
| `docs/01-spec/filter-ui.md` | Update with implemented filter markup |
| `docs/02-database/db-schema.md` | Verify all columns match models (check constraints) |
| `docs/02-database/db-indexes.md` | Document conditional index usage |
| `docs/99-agent/architecture.md` | Update with current file structure |
| `README.md` (root) | Missing - needs project setup and deployment instructions |

---

## 4. Bug Fixes Identified

### High Priority

1. **`is_declined` message repetition** (`telegram_bot/middlewares/permissions.py:119-120`)
   - Both `is_declined` and `consent_revoked_at` return "Your account has been deleted."
   - Should differentiate: declined users are in browse-only mode, not deleted

2. **Translation source language** (`apps/search/services/query_translator.py:141`)
   - Uses `source="bs"` (Bosnian) but spec mentions Montenegrin
   - Should verify if this is intentional (Bosnian shares language code with Serbian/Croatian/Bosnian; Google Translator may treat them interchangeably)

3. **Search query timing** (`apps/search/views/search.py:68`)
   - Analytics event recorded AFTER successful execution
   - Should record BEFORE in case of exception, to track API usage

---

## 5. Security/Operational Hardening

### Critical Security Items

| Item | Location | Status | Notes |
|------|----------|--------|-------|
| **Rate limiting** | nginx/docker config | ✅ Complete | `limit_req_zone` defined for `/login/` and `/search/` endpoints (10r/s and 20r/s) |
| **nginx media MIME config** | nginx config file | ✅ Complete | MIME whitelist: `image/jpeg` only in `/protected-media/` location |
| **Login token constant-time** | `apps/users/views/consent.py:209` | ⚠️ Verify | Uses DB lookup for token hash comparison; verify uses `hmac.compare_digest` |
| **X-Accel-Redirect nginx config** | nginx config | ✅ Complete | Internal `/protected-media/` location defined (line 70-85) |

### Operational Items

| Item | Location | Status | Notes |
|------|----------|--------|-------|
| **Health check endpoint** | `apps/core/views.py` | ✅ Complete | `/health/` endpoint exists with DB check |
| **Sentry/DS logging** | Settings | ⚠️ Missing | No structured error logging configured |
| **Backup script** | Docker/ops | ❌ Missing | Need backup/restore procedure documented |
| **Monitoring config** | Settings | ❌ Missing | No metrics endpoint exposed |

---

## Implementation Priority Matrix

```
P0 (Blocker for launch):
- [ ] Add logout view
- [ ] Fix is_declined middleware message
- [ ] Add consent_shown to search view context

P1 (High priority):
- [ ] Add search view edge case tests
- [ ] Verify translation source language works for Montenegrin

P2 (Medium priority):
- [ ] Update documentation with actual snippets
- [ ] Add missing template rendering tests
```

---

## File Structure Reference

```
src/backend/
├── apps/
│   ├── ads/
│   │   ├── models.py          # ✅ Ad, AdImage models
│   │   ├── views/
│   │   │   ├── listings.py    # ✅ listings, ad_detail, media_gate
│   │   │   ├── dashboard.py   # ✅ seller dashboard
│   │   │   ├── edit.py        # ✅ ad_edit, ad_archive, ad_reactivate
│   │   │   └── delete.py      # ✅ ad_delete
│   │   └── migrations/
│   │       └── 0002_search_vector_triggers.py  # ✅ triggers
│   ├── categories/
│   │   ├── models.py          # ✅ MPTT Category model
│   │   └── migrations/
│   ├── locations/
│   │   └── models.py          # ✅ City model
│   ├── core/
│   │   ├── enums.py           # ✅ All StrEnum definitions
│   │   ├── services/
│   │   │   └── contact.py     # ✅ can_contact_seller, contact relay
│   │   ├── utils/
│   │   │   ├── cache.py       # ✅ Criteria caching
│   │   │   └── sanitize.py    # ✅ Verified exists
│   │   └── management/commands/
│   │       ├── archive_sweep.py
│   │       ├── delete_sweep.py
│   │       └── sweep_drafts.py
│   ├── users/
│   │   ├── models.py          # ✅ User, LoginToken
│   │   ├── views/consent.py   # ✅ consent_accept/decline/withdraw, login_issue
│   │   └── services/
│   │       ├── account_state.py  # ✅ can_publish_ad, can_login
│   │       └── deletion.py       # ✅ withdraw_consent, soft_delete_user_ads
│   ├── search/
│   │   ├── views/search.py    # ✅ FTS search with translation
│   │   └── services/
│   │       └── query_translator.py  # ✅ bs→ru translation with circuit breaker
│   ├── moderation/
│   │   ├── models.py          # ✅ ModerationCriteria, ModeratorActionLog
│   │   └── services/
│   │       ├── auto_moderation.py   # ✅ All validation checks
│   │       └── moderation_log.py    # ✅ Verified exists
│   └── analytics/
│       └── models.py          # ✅ AnalyticsEvent
├── config/
│   ├── settings/
│   │   ├── base.py            # ✅ Base settings with security
│   │   ├── dev.py
│   │   ├── prod.py
│   │   └── test.py
│   └── urls.py                # ✅ Main URL config
└── templates/
    ├── ads/
    │   ├── list.html          # ✅ Ad listings
    │   ├── detail.html        # ✅ Ad detail
    │   ├── dashboard.html     # ✅ Seller dashboard
    │   └── edit.html          # ✅ Edit form
    ├── users/
    │   └── login_issue.html   # ✅ Login deep-link page
    └── components/
        └── consent_banner.html # ✅ Consent banner with accept/decline forms
```

```
src/telegram_bot/
├── states.py                  # ✅ AdCreateState enum
├── main.py                    # ✅ Bot entrypoint with middleware
├── handlers/
│   ├── __init__.py
│   ├── login.py               # ✅ /start handler + deep-link
│   ├── ad_create.py           # ✅ Full FSM flow
│   └── contact.py             # ✅ Contact deep-link handler
├── middlewares/
│   └── permissions.py         # ✅ Account state middleware
├── services/
│   └── media.py               # ✅ Photo validation/storage
├── schemas/
│   └── message_payloads.py    # ✅ Pydantic v2 DTOs
└── tests/
    ├── conftest.py            # ✅ Django+aiogram test fixtures
    ├── test_ad_lifecycle.py   # ✅ Ad status transition tests
    ├── test_create_draft_ad.py
    ├── test_media.py
    └── test_login_claim.py
```

---

## Next Steps for Phase 1 Completion

### Immediate (Next 2-3 days)

1. **Add missing views:**
   - Logout view for `/logout/` endpoint referenced in dashboard

2. **Fix bugs:**
   - Middleware message for `is_declined` state (should say "browse-only mode" not "deleted")
   - Add `consent_shown` to search view context

### Testing Sprint (Next 3-5 days)

1. Add search view edge case tests (including consent context verification)
2. Run full test suite with `uv run pytest --cov`

### Documentation Sprint (Parallel)

1. Update spec docs with actual implementation details
2. Create root README.md
3. Document backup/restore procedures

---

## Dependencies for Safe Deployment

| Service | Required Config |
|---------|----------------|
| **nginx** | Rate limiting, TLS termination, X-Accel-Redirect internal location |
| **PostgreSQL 18** | Required extensions: pg_trgm (for similarity), proper locale `ru_RU.UTF-8` |
| **Telegram Bot Token** | `BOT_TOKEN` env variable |
| **Bot Username** | `BOT_USERNAME` env variable for deep-links |
| **Media volume** | Shared Docker volume for `MEDIA_ROOT` |
| **Cache backend** | Redis recommended for Django cache (criteria caching) |

---

## Risk Assessment for Remaining Work

| Risk | Mitigation |
|------|------------|
| **Translation source** | Verify Bosnian code works for Montenegrin queries (Google treats them as similar languages) |
| **Login token timing** | Verify `hmac.compare_digest` usage for constant-time comparison |
| **Seed data verified** | Categories/cities are correctly seeded (verified) |
| **nginx config complete** | Rate limiting and media protection already configured |