---
id: phase-01-detailed-updated
domain: planning
tags:
  - planning
  - phase-1
  - mvp
  - implementation-gaps
  - blocker-tracking
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

Phase 1 has completed the core architecture implementation but has several **blocking items** that must be resolved before launch:

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
- **Views:** Listings (at `/`), detail, dashboard, edit, archive, reactivate, health check
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

### Critical (Must Have - Blocks Launch)

| Item | Location | Status | Notes |
|------|----------|--------|-------|
| **Logout view** | `apps/users/views/` (new file or `consent.py`) | ❌ Missing | `/logout/` referenced in dashboard template but view not implemented; requires POST method with CSRF protection |
| **Search view consent context** | `apps/search/views/search.py` | ❌ Missing | `consent_shown` variable not passed to template context, causing banner to show incorrectly |
| **Delete view** | `apps/ads/views/delete.py` | ❌ Missing | `ad_delete` view referenced but not implemented |

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

### Critical Priority

| Item | Location | Notes |
|------|----------|-------|
| **Logout view missing** | `apps/users/views/` | Must implement POST-only logout view with CSRF protection and cookie clearing |
| **Search view consent_shown** | `apps/search/views/search.py:83-87` | Template context missing `consent_shown` variable; must pass current consent status |
| **Delete view missing** | `apps/ads/views/delete.py` | View referenced in URLs but not implemented; needs ownership verification |

### High Priority

| Item | Location | Notes |
|------|----------|-------|
| **`is_declined` message** | `telegram_bot/middlewares/permissions.py:119-120` | Both `is_declined` and `consent_revoked_at` return "Your account has been deleted." Should differentiate: declined users are in browse-only mode, not deleted. Message must be changed to reflect "browse-only mode". |
| **Delete view missing** | `apps/ads/views/` | `ad_delete` view needs implementation with POST method and CSRF protection |

### Medium Priority

| Item | Location | Notes |
|------|----------|-------|
| **Translation source language** | `apps/search/services/query_translator.py:141` | Uses `source="bs"` (Bosnian) but spec mentions Montenegrin. **Documented: Bosnian (bs) language code is intentional approximation for Montenegrin queries.** Google Translator treats Bosnian, Serbian, Croatian, and Montenegrin as similar languages with shared linguistic features. The bs→ru (Bosnian to Russian) translation provides reasonable accuracy for Montenegrin input. This is a deliberate trade-off documented in technical specifications. |
| **Search query timing** | `apps/search/views/search.py:68` | Analytics event recorded AFTER successful execution. Consider recording BEFORE in case of exception, to track API usage. |

---

## 5. Security/Operational Hardening

### Critical Security Items

| Item | Location | Status | Notes |
|------|----------|--------|-------|
| **Logout view CSRF protection** | `apps/users/views/logout.py` (new) | ❌ Missing | Must implement POST-only logout with `{% csrf_token %}` protection to prevent CSRF logout attacks |
| **Rate limiting - admin actions** | `config/settings/base.py` or nginx | ❌ Missing | No rate limiting on admin moderation actions; needs protection against CSRF or brute-force |
| **hmac.compare_digest verification** | `apps/users/views/consent.py:209` | ⚠️ Gap | Login token comparison uses DB lookup; must verify uses `hmac.compare_digest` for constant-time comparison to prevent timing attacks on token validation |
| **Rate limiting** | nginx/docker config | ✅ Complete | `limit_req_zone` defined for `/login/` and `/search/` endpoints (10r/s and 20r/s) |
| **nginx media MIME config** | nginx config file | ✅ Complete | MIME whitelist: `image/jpeg` only in `/protected-media/` location |

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
- [ ] Implement logout view at `/logout/` with POST method + CSRF protection
- [ ] Add `consent_shown` to search view template context
- [ ] Implement delete view at `ads/views/delete.py` with ownership verification
- [ ] Document Bosnian (bs) translation approximation for Montenegrin queries

P1 (High priority):
- [ ] Fix `is_declined` middleware message to say "browse-only mode" not "deleted"
- [ ] Add search view edge case tests (including consent context verification)
- [ ] Verify `hmac.compare_digest` usage in login token comparison

P2 (Medium priority):
- [ ] Update documentation with actual snippets
- [ ] Add missing template rendering tests
- [ ] Review analytics event timing for search view
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
│   │   │   └── delete.py      # ❌ ad_delete NOT IMPLEMENTED
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

1. **Implement missing views (BLOCKERS):**
   - Logout view for `/logout/` endpoint with POST method and CSRF protection
   - Delete view for `ad_delete` URL reference

2. **Fix bugs:**
   - Middleware message for `is_declined` state (should say "browse-only mode" not "deleted")
   - Add `consent_shown` to search view context

3. **Document translation approach:**
   - Add technical note about Bosnian (bs) → Russian (ru) translation being intentional approximation for Montenegrin queries

### Testing Sprint (Next 3-5 days)

1. Add search view edge case tests (including consent context verification)
2. Add delete view tests for ownership enforcement
3. Run full test suite with `uv run pytest --cov`

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

| Risk | Mitigation | Current State |
|------|------------|---------------|
| **Logout CSRF** | Implement POST-only view with `{% csrf_token %}` | ❌ Unmitigated - view missing entirely |
| **Admin action rate limiting** | Add nginx rate limiting for `/admin/` paths | ❌ Unmitigated - no protection |
| **Token timing attacks** | Verify `hmac.compare_digest` usage | ⚠️ Gap exists in verification |
| **Translation source** | Document Bosnian code intentional for Montenegrin | ✅ Documented as approximation |
| **Seed data verified** | Categories/cities are correctly seeded (verified) | ✅ Verified |
| **nginx config complete** | Rate limiting and media protection already configured | ✅ Complete for existing endpoints |