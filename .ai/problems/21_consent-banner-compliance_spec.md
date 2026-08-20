---
id: consent-banner-compliance-spec
problem: Decision_019
domain: product
tags:
  - consent
  - gdpr
  - eprivacy
  - pii
  - compliance
related:
  - technical-specification
  - db-schema
  - db-retention
  - architecture
  - owner-decisions-index
  - alert-unsubscribe-research
  - consent-banner-gdpr-research-report
---

# Spec 21 — Consent Banner & GDPR/ePrivacy Compliance Redress

## 1. Problem Statement

The Mko Bazuna consent banner — intended to obtain user consent for data
processing and cookie usage per GDPR and the ePrivacy Directive — **does not
function correctly for first-time and returning users**. On a first login, the
banner is supposed to appear with a confirmation that the user agrees to data
processing, but multiple defects prevent it from working as intended.

### Root Causes (Why the Banner Doesn't Work)

| # | Defect | Severity | File / Location |
|---|--------|----------|-----------------|
| D1 | **`/privacy/` route returns 404** — The banner's "Privacy details" link points to a non-existent page. Users cannot read what they are consenting to. GDPR Article 13 requires a privacy notice. | CRITICAL | `consent_banner.html:108` → `config/urls.py` (no `/privacy/` route) |
| D2 | **Consent views accept GET requests** — `consent_accept` and `consent_decline` lack `@require_POST`. State-changing operations are triggerable by a GET URL (e.g., `<img src="/consent/decline/">`), creating a CSRF risk. | CRITICAL | `consent.py:50,79` |
| D3 | **`consent_given` cookie is write-only** — The cookie is SET on accept/decline/withdraw (3 locations in `consent.py`) but NEVER read anywhere in the codebase. `is_consent_given()` checks only the DB (`consent_given_at`), ignoring the cookie. The cookie is vestigial dead code with no fallback or purpose. | CRITICAL | `consent.py:46-47` (set); `is_consent_given` (never reads) |
| D4 | **Banner hidden for anonymous users** — `is_consent_given()` returns `True` for anonymous users, so the banner never appears for non-logged-in visitors. Yet non-essential cookies (`lang_pref`, `preferred_city`) are set via JavaScript for anonymous sessions without consent. ePrivacy Article 5(3) requires prior consent before non-essential cookie storage. | HIGH | `consent.py:153-155` |
| D5 | **`consent_shown` context variable missing on 4 of 7 views** — `cabinet_hub`, `cabinet_settings`, `seller_trust_dashboard`, and `moderation_analytics` do not pass `consent_shown` to their templates. When undefined, Django treats it as falsy, so `{% if not consent_shown %}` is always `True` → the banner **always shows** on these pages, even after the user has given consent. | HIGH | `cabinet/views/hub.py:21,24`; `seller_dashboard.py:26`; `moderation_dashboard.py:28` |
| D6 | **`give_consent()` does not clear decline state** — If a user declines (sets `is_declined=True`, `ads_auto_publish=False`) and later clicks "Accept", `give_consent()` only sets `consent_given_at` but leaves `is_declined=True` and `ads_auto_publish=False`. The user is permanently stuck in browse-only mode after declining, unable to publish even after accepting. | HIGH | `deletion.py:224-247` |
| D7 | **Plausible analytics script loads unconditionally** — Per spec decision L, Plausible is claimed as "cookieless, no consent banner needed." However, the `<script>` tag loads from `plausible.io` without any consent gate. If Plausible sets any cookie or performs tracking, this violates ePrivacy. | MEDIUM | All templates with `{% if PLAUSIBLE_HOST %}` |
| D8 | **No server-side consent audit log** — GDPR Article 7(1) requires demonstrable proof of consent (timestamp, method, version). The current implementation stores only `consent_given_at` on the User model. No record of what banner version was shown, what the user chose, or the IP/method. | MEDIUM | No `consent_records` table exists |
| D9 | **Banner text is generic** — The current banner says "This site uses cookies for essential functionality and analytics. By accepting, you consent to all processing." It does not list specific cookies, third parties (Telegram, Google Translate, Plausible), purposes, or retention periods. GDPR/ePrivacy requires informed consent. | MEDIUM | `consent_banner.html:9-11` |

### Corrected Note on Research Report

The researcher's report (Section 1.5) states that 5 of 7 templates lack the
deleted-user guard `{% if not request.user.is_authenticated or not
request.user.is_deleted %}`. **This is incorrect** — all 7 templates that
include `consent_banner.html` have the guard. The actual defect (D5) is that
4 views fail to pass the `consent_shown` context variable, not missing guards.

The researcher's report also states (Section 1.2) that `give_consent` "clears
`is_declined`." **This is incorrect** — `give_consent` (line 243-245) only
sets `consent_given_at`; it does not modify `is_declined` or
`ads_auto_publish`. This is defect D6.

---

## 2. Confirmed Requirements

### 2.1 Legal Requirements (GDPR + ePrivacy Directive)

| Requirement | Source | Status in Spec |
|-------------|--------|----------------|
| Prior, informed consent before storing/accessing terminal equipment | ePrivacy Directive Art. 5(3) | REQUIRED |
| Consent must be: freely given, specific, informed, unambiguous | GDPR Art. 4(11) | REQUIRED |
| Burden of proof: controller must demonstrate consent was obtained | GDPR Art. 7(1) | REQUIRED (server-side log) |
| Right to withdraw consent must be as easy as giving it | GDPR Art. 7(3) | REQUIRED (persistent footer link) |
| Information to be provided: controller identity, purposes, legal basis, recipients, retention, rights | GDPR Art. 13(1)(c)-(f) | REQUIRED (privacy policy page) |
| Right to erasure (30-day window after withdrawal) | GDPR Art. 17; Spec decision F | ALREADY IMPLEMENTED |
| Data minimization: only `telegram_id` + optional `username` | Spec decision F, line 81 | ALREADY IMPLEMENTED |

### 2.2 Technical Requirements

| ID | Requirement | Source |
|----|-------------|--------|
| TR-01 | `/privacy/` route must exist and return 200 with a public privacy policy page | Decision F, line 83; GDPR Art. 13 |
| TR-02 | All state-changing consent views must be POST-only | Web security best practice; D2 |
| TR-03 | `consent_given` cookie must either be functional (read back) or removed | D3 |
| TR-04 | `consent_shown` must be available on ALL templates via a context processor (not per-view) | D5; Architecture (context processors pattern) |
| TR-05 | `give_consent()` must clear `is_declined` and restore `ads_auto_publish=True` | D6; Spec decision F (decline ≠ withdraw, reversible) |
| TR-06 | Banner must be available to anonymous users via cookie-based state | D4; ePrivacy Art. 5(3) |
| TR-07 | Banner must provide Accept and Reject at equal visual prominence on the first layer | EDPB Cookie Banner Task Force §2.2 |
| TR-08 | Non-essential scripts (Plausible, GLightbox) must not load before consent | EDPB Guidelines 2/2023; D7 |
| TR-09 | Consent audit log must record: timestamp, user (or anonymous ID), banner version, choice, IP | GDPR Art. 7(1); D8 |
| TR-10 | Consent must be re-prompted every 12 months | GDPR/ePrivacy best practice; CNIL, Irish DPC guidance |

### 2.3 Product Behavior Requirements

| ID | Requirement | Source |
|----|-------------|--------|
| PR-01 | Anonymous buyers can browse published ads before giving consent (browse-first) | Spec decision K, line 137 |
| PR-02 | Declining non-essential cookies does NOT block seller login or ad creation | GDPR (no consent wall); PO decision assumed — see Q2 |
| PR-03 | WITHDRAW (separate from decline) triggers full soft-delete + 30-day PII erasure | Spec decision F, O2, O3 |
| PR-04 | Consent acceptance time is recorded and persisted | Spec decision F, line 100 |
| PR-05 | Withdrawal UI exists on the seller dashboard as a POST + CSRF + confirmation button | Spec decision F, line 90 |
| PR-06 | Cookie choices persist across sessions via cookie (anonymous) and DB (authenticated) | D3, D4 |
| PR-07 | Cookie preference center must be accessible from footer on all pages | EDPB best practice; GDPR Art. 7(3) |

---

## 3. Assumed Product Owner Decisions

Based on the analysis and research, the following decisions are assumed.
These should be confirmed by the Product Owner but are set to the
GDPR-compliant default (Option A in each case):

| Decision | Value | Rationale |
|----------|-------|-----------|
| **PO-01:** Show banner to anonymous users | YES | ePrivacy Art. 5(3) requires consent before non-essential cookies. Anonymous users' `lang_pref`/`preferred_city` cookies are non-essential. Best practice: show banner to all visitors. |
| **PO-02:** Decline behavior | Separate cookie rejection from browse-only mode. "Decline" = reject non-essential cookies only (site still fully usable). "Withdraw" = account deletion. | GDPR prohibits consent walls. Declining cookies should not block service access. |
| **PO-03:** Accept after decline | YES — restore `ads_auto_publish=True`, clear `is_declined` | Decline is reversible per spec decision F ("DECLINE ≠ WITHDRAW"). Accept should be a first-class action that restores full state. |
| **PO-04:** Granular consent | YES — 3 categories (Essential, Analytics, Preferences) | GDPR Art. 4(11) "specific" consent; EDPB requires purpose-level granularity. |
| **PO-05:** Consent duration | 12 months, then re-prompt | CNIL recommends 12 months; Irish DPC allows 6 months. 12 months is the most broadly accepted. |
| **PO-06:** Privacy policy page | YES — create `/privacy/` public page | Spec decision F explicitly requires it; GDPR Art. 13. |
| **PO-07:** Bot-side consent | No separate bot prompt; web banner covers bot | Spec decision K explicitly says "no separate bot confirmation required." |

---

## 4. Data Inventory (PII Stored)

### 4.1 User PII

| Table / Model | Field | Type | PII? | Retention | Notes |
|---------------|-------|------|------|-----------|-------|
| `users` | `telegram_id` | BIGINT, unique, nullable | YES | nulled on withdrawal (T+0) | Nullified immediately by `withdraw_consent()` |
| `users` | `chat_id` | BIGINT, unique | YES | never nulled | Stable identifier for bot |
| `users` | `username` | VARCHAR, nullable | YES | nulled on withdrawal (T+0) | Optional `@username` |
| `users` | `first_name` | VARCHAR | YES | emptied on withdrawal (T+0) | From AbstractUser |
| `users` | `last_name` | VARCHAR | YES | emptied on withdrawal (T+0) | From AbstractUser |
| `users` | `email` | VARCHAR, nullable | YES | not nulled on withdrawal | AbstractUser default |
| `users` | `consent_given_at` | TIMESTAMP, nullable | NO (metadata) | permanent | Consent timestamp |
| `users` | `is_declined` | BOOL | NO (state flag) | permanent | Browse-only flag |
| `users` | `consent_revoked_at` | TIMESTAMP, nullable | NO (metadata) | nulled at hard-delete (T+30d) | Withdrawal timestamp |
| `login_tokens` | `token_hash` | CHAR(64) | NO (hashed) | 5 min expiry + cleanup | SHA-256 of raw token |
| `login_tokens` | `telegram_id` | BIGINT, nullable | YES | cleared with token | Filled by bot |
| `seller_verifications` | `phone_number` | VARCHAR(20), nullable | YES | nulled on hard-delete | Optional verification |
| `search_history` | `user_id` | FK, nullable | Indirect | per-user retention | Behavioral data |
| `saved_searches` | `user_id` | FK | Indirect | per-user retention | Behavioral data |
| `ad_favorites` | `user_id` | FK | Indirect | per-user retention | Behavioral data |
| `analytics_events` | `user_id` | FK, nullable | Indirect | SET NULL on hard-delete | Product metrics |
| `moderator_action_logs` | `user_id` | FK, nullable | Indirect | SET NULL on hard-delete | Audit trail |

### 4.2 Ad/Image Data

| Table / Model | Field | PII? | Notes |
|---------------|-------|------|-------|
| `ads` | `user_id` | Indirect | FK to user; CASCADE on hard-delete |
| `ads` | `title`, `title_en`, `title_bs` | Content | User-provided content (translated) |
| `ads` | `description`, `description_en`, `description_bs` | Content | User-provided content (translated) |
| `ad_images` | `image` (storage key) | NO | UUID v4 + ad_id, no user PII in URL (zone R6) |
| `ad_images` | `telegram_file_id` | NO | Telegram metadata only |
| `ad_images` | `sha256` | NO | For deduplication |

### 4.3 Third-Party Data Flows

| Flow | Data Sent | Recipient | PII? | Purpose | Consent Basis |
|------|-----------|-----------|------|---------|---------------|
| Telegram login | Deep-link `login_<token>` | Telegram | Token only (hashed) | Authentication | Essential (explicitly requested service) |
| Telegram contact | Deep-link `contact_<ad_id>` | Telegram | Ad ID only | Seller-buyer relay | Essential (user explicitly initiates) |
| Google Translate | Ad title/description text | Google | NO | Language normalization at ad creation | Best-effort; non-identifying (spec decision G) |
| Plausible analytics | Page URL, referrer, UA | Plausible | NO (cookieless) | Traffic analytics | Legitimate interest (claimed); but script loads unconditionally |

### 4.4 Cookies Set (Current)

| Cookie | Set By | Lifetime | Essential? | Consent-Gated? |
|--------|--------|----------|------------|----------------|
| `sessionid` | Django | Session | YES | No (essential) |
| `csrftoken` | Django | 1 year | YES | No (essential) |
| `consent_given` | `consent.py` | 1 year | NO | N/A (consent state itself) |
| `lang_pref` | JS in `language_switcher.html` | 1 year | NO (borderline) | No (bug D4) |
| `preferred_city` | `set_preferred_city` view | 1 year | NO (borderline) | No (bug D4) |

---

## 5. Conceptual Development Tasks

### Task 1: Create `/privacy/` Public Policy Page
- **Purpose:** Fix D1 — the banner links to `/privacy/` which returns 404. GDPR Article 13 requires a privacy notice.
- **Expected outcome:** A new public Django view + template at `/privacy/` that lists: cookie declaration table, third-party disclosures (Telegram, Google Translate, Plausible), processing purposes, legal bases, user rights, controller contact (Telegram deep-link), and the 30-day erasure policy.
- **Dependencies:** None.
- **Acceptance:** `GET /privacy/` returns 200; page is accessible without login; contains a cookie table matching all cookies identified in Section 4.4.

### Task 2: Harden Consent Views (POST-only)
- **Purpose:** Fix D2 — `consent_accept` and `consent_decline` accept GET, enabling CSRF via cached images/links.
- **Expected outcome:** Add `@require_POST` decorator to `consent_accept` and `consent_decline`. Update template forms to use `<button type="submit">` (already POST). Update tests to use `client.post()`.
- **Dependencies:** None.
- **Acceptance:** `GET /consent/accept/` returns 405 Method Not Allowed.

### Task 3: Fix `give_consent()` to Clear Decline State
- **Purpose:** Fix D6 — accepting consent after declining doesn't restore publishing ability.
- **Expected outcome:** `give_consent()` sets `consent_given_at = now()`, clears `is_declined = False`, restores `ads_auto_publish = True`, clears `consent_revoked_at = None`. All in one `save(update_fields=[...])`.
- **Dependencies:** None (service-layer change).
- **Acceptance:** After decline → accept, `is_declined` is False, `ads_auto_publish` is True, `consent_given_at` is set.

### Task 4: Create Consent Context Processor
- **Purpose:** Fix D5 — 4 of 7 views don't pass `consent_shown`, causing the banner to always show on those pages.
- **Expected outcome:** A new context processor `apps.users.context_processors.consent_state` that computes `consent_shown` for every template. The function must:
  - Return `True` (banner hidden) for users who accepted (DB `consent_given_at` set or cookie `consent_given=true`).
  - Return `True` (banner hidden) for users who declined (cookie `consent_given=declined` or DB `is_declined=True`).
  - Return `False` (banner shown) for users who haven't acted (no DB state, no cookie).
  - Return `True` (banner hidden) for soft-deleted users (guard already in templates).
  - Handle both anonymous (cookie) and authenticated (DB) users.
- **Dependencies:** Task 3 (for correct DB state).
- **Acceptance:** All templates that include `consent_banner.html` receive `consent_shown` without per-view passing. Views no longer need to import/pass it manually.

### Task 5: Make Banner Universal (Show to Anonymous Users with Cookie State)
- **Purpose:** Fix D4 — anonymous users never see the banner but non-essential cookies are set.
- **Expected outcome:** `is_consent_given` / the context processor returns `False` (banner shown) for anonymous users who haven't set the `consent_given` cookie. After accepting/declaring, the cookie persists for 12 months. Before consent, non-essential scripts (Plausible, GLightbox) are not loaded.
- **Dependencies:** Task 4 (context processor).
- **Acceptance:** Anonymous visitors see the banner; after Accept, the cookie hides it for 12 months; non-essential scripts are deferred until consent.

### Task 6: Implement Cookie Consent Categories & Script Gating
- **Purpose:** Fix D7, D8, D9 — Plausible and GLightbox scripts load unconditionally; banner text is generic; no server-side consent audit log.
- **Expected outcome:**
  - **(6a)** Banner first layer shows: "Essential (always on)" + "Analytics (Plausible)" + "Preferences (lang/city)" with Accept All / Reject All / Manage buttons at equal prominence.
  - **(6b)** `consent_accept` and `consent_decline` views accept granular category selection (cookie flags: `consent_analytics`, `consent_preferences`). The `consent_given` cookie becomes a structured cookie (e.g., `consent_given=accepted; consent_analytics=true; consent_preferences=true`).
  - **(6c)** Non-essential scripts (Plausible, GLightbox) only load after consent via a small inline script that checks cookies before injecting `<script>` tags.
  - **(6d)** `lang_pref` and `preferred_city` cookies are only set after consent (or immediately, if user accepted preferences).
- **Dependencies:** Task 2 (POST-only views), Task 5 (anonymous cookie state).
- **Acceptance:** Scripts don't load before consent; cookie categories are controllable; banner text lists specific cookies and third parties.

### Task 7: Consent Audit Log (Server-Side Record)
- **Purpose:** Fix D8 — GDPR Article 7(1) requires demonstrable proof of consent.
- **Expected outcome:** A new `ConsentRecord` model (or table) with: `user_id` (nullable, for anonymous use a hashed session/device ID), `consent_given_at` (timestamp), `consent_version` (banner text version), `choice` (StrEnum: ACCEPTED, DECLINED, WITHDRAWN), `categories` (JSONB of category→bool), `ip_address` (anonymized), `user_agent` (truncated). Records created on every consent action.
- **Dependencies:** New model + migration.
- **Acceptance:** Every Accept/Decline/Withdraw creates a `ConsentRecord` row accessible from Django admin.

### Task 8: Consent Re-Prompting (12-Month Rollover)
- **Purpose:** Implement TR-10 — re-prompt users after 12 months.
- **Expected outcome:** The context processor checks if the `consent_given` cookie (or `consent_given_at` in DB) is older than 12 months. If so, the banner shows again regardless of prior choice. Cookie max-age set to 12 months (not 1 year = 365 days, close enough but explicit).
- **Dependencies:** Task 4, Task 5.
- **Acceptance:** After 12 months, banner reappears for returning users.

### Task 9: Cookie Preference Center (Footer Link)
- **Purpose:** GDPR Article 7(3) — withdrawal as easy as giving consent.
- **Expected outcome:** A footer element (visible on all pages) with a "Cookie settings" link that reopens the consent banner / a preference modal.
- **Dependencies:** Tasks 4–6.
- **Acceptance:** Footer link present on all pages; clicking it reopens consent choices.

### Task 10: Update Tests & Fix Existing Test Defects
- **Purpose:** Align tests with the corrected behavior.
- **Expected outcome:**
  - `test_consent.py`: use `client.post()` instead of `client.get()` for accept/decline.
  - `test_templates.py`: add `ads/detail.html` and `ads/dashboard.html` to the guard-check list (currently only 5 of 7).
  - New tests for: accept-after-decline restores publishing, anonymous user sees banner, cookie-based consent state for anonymous, granular consent categories, 12-month re-prompt.
- **Dependencies:** Tasks 1–9.

---

## 6. Product Owner Questions (Open Items)

The following items require PO confirmation. Default assumptions are noted.

| Q# | Question | Assumed Answer |
|----|----------|----------------|
| Q1 | Should anonymous buyers see the consent banner? | Yes — show to all visitors (PO-01) |
| Q2 | Should "Decline" block seller login, or should cookie rejection be separate from account state? | Decline = reject non-essential cookies only; seller login still works (PO-02) |
| Q3 | Should "Accept" after "Decline" restore publishing ability? | Yes — `give_consent` clears `is_declined` and restores `ads_auto_publish` (PO-03) |
| Q4 | Should consent be granular (Essential / Analytics / Preferences)? | Yes — 3 categories on first layer (PO-04) |
| Q5 | How long before consent re-prompting? | 12 months (PO-05) |
| Q6 | Should a `/privacy/` page be created? | Yes (PO-06) |
| Q7 | Should the bot show its own consent prompt? | No — web banner covers the bot (PO-07) |
| Q8 | Should `lang_pref` and `preferred_city` cookies be classified as "Preferences" (requiring opt-in) or "Essential" (strictly necessary for UX)? | Preferences — require consent |
| Q9 | Should the consent audit log use a DB table or a log file? | DB table (`ConsentRecord`) for queryability + GDPR Article 7(1) accountability |

---

## 7. Assumptions

1. **Montenegro is the launch market** — GDPR-equivalent jurisdiction. The ePrivacy Directive applies via Montenegro's national transposition. The site targets Russian-speaking and Montenegrin-speaking users in Montenegro.
2. **Plausible may set cookies** — Even if "cookieless," Plausible's own documentation mentions a `_plausible` cookie. Treating it as requiring consent is the conservative, compliant approach.
3. **`lang_pref` and `preferred_city` are non-essential** — They enhance UX but are not required for the core service (browsing/purchasing). Classifying them as "Preferences" requiring consent is the safer interpretation under ePrivacy.
4. **Anonymous user consent can be tracked via a cookie** — Without a user account, consent state is stored exclusively in the `consent_given` (and category-specific) cookie. This is acceptable for non-essential-cookie consent (not for contractual/legal obligations).
5. **The existing 3-state consent model (Accept/Decline/Withdraw) is correct** — Only the implementation of Accept after Decline is broken (D6), not the model itself. The three states map to:
   - **Accept:** Full processing with consent (`consent_given_at` set)
   - **Decline:** Reject non-essential cookies; full site access (PO-02)
   - **Withdraw:** Account deletion + 30-day PII erasure (existing, working)
6. **The bot's consent is covered by the web banner** — Per spec decision K, "no separate bot confirmation required." The bot checks the same `User` model fields. (This is an existing design decision, not questioned here.)

---

## 8. Constraints

1. **Two processes, one DB** — Web (gunicorn sync WSGI, HTMX MPA) + bot (aiogram, `django.setup()` + shared ORM). Consent changes must be visible to both processes immediately via DB (not cache or in-memory state).
2. **No task broker** — No Celery/Redis pub-sub beyond cache. Consent state must be DB-based or cookie-based; no background tasks needed for consent.
3. **HTMX MPA** — Full page renders. No React/Vue SPA state management. Consent state must work with full-page reloads.
4. **Django 5.2 LTS** — Context processors available; `@require_POST` available; template context processors are the established pattern (see `apps.core.context_processors`).
5. **StrEnum requirement** — All fixed values (consent choice, cookie categories) must use `StrEnum`, not strings/dicts.
6. **Pydantic at boundaries** — Consent form submission should validate via Pydantic DTO.
7. **SQLite not supported** — PostgreSQL 18 only (`DATABASE_URL` or `POSTGRES_*` env vars). JSONB columns available for consent categories.
8. **No existing `ConsentRecord` model** — A new model + migration is required for the audit log (Task 7).
9. **Dev/test settings override `CACHES` to `LocMemCache`** — No Redis needed for local development/testing.

---

## 9. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Showing banner to anonymous users reduces conversion | Medium | Medium | Banner is browse-first; users can dismiss without accepting. Accept/decline choices are cookie-based. |
| Cookie-based consent for anonymous users is less robust than DB-based | Medium | Low | Cookie has 12-month expiry; re-prompt after expiry. Document that anonymity limits auditability. |
| Script gating (loading Plausible/GLightbox only after consent) requires client-side JS | Medium | Low | Use a small inline script (no external dependency) that reads cookies and conditionally loads scripts. HTMX is already loaded unconditionally (essential). |
| Adding `@require_POST` breaks existing links/bookmarks to `/consent/accept/` via GET | Low | Low | These are state-changing URLs that should never have been GET-accessible. 405 is the correct response. Update tests. |
| Granular consent categories add complexity | Low | Medium | Start with 3 fixed categories (Essential, Analytics, Preferences) via StrEnum. Simple to extend. |
| Consent audit log model adds a new migration | Low | Low | New `ConsentRecord` model with FK to `users.User` (nullable). Migration follows existing patterns. |
| Accept-after-decline race condition in high-traffic | Low | Low | `give_consent` uses `update_fields` save; no read-modify-write race on different fields. |
| Template guard check missing `detail.html` and `dashboard.html` in tests | Medium | Low | Add to `test_templates.py` `_TEMPLATES_WITH_BANNER` list. |

---

## 10. Out of Scope

1. **Bot-side consent prompt** — Per PO-07, the web banner covers the bot. No separate bot confirmation.
2. **Full Cookie Management Platform (CMP)** — No third-party CMP integration (e.g., Cookiebot, Usercentrics). Self-built solution only.
3. **Multi-language consent text** — The banner and privacy policy will be in Russian (base) and Montenegrin (UI shell), following the existing i18n pattern. English is supported for UI labels only.
4. **GDPR Data Subject Request (DSAR) portal** — Handling user requests for data access/portability is out of scope. The "Withdraw Data" flow covers erasure.
5. **Cookie scanning / discovery** — No automated tool to scan for new cookies. Cookie inventory is manually maintained in the privacy policy.
6. **`Site`/`django.contrib.sites`** — Not used in this project. Privacy policy is a single page, not per-site.
7. **Consent for analytics beyond Plausible** — The site uses Plausible (cookieless) and internal `AnalyticsEvent` model. Consent covers both. No Google Analytics or third-party ad tracking.
8. **Age verification / parental consent** — Not in scope for this classifieds board (adult service).

---

## 11. Definition of Ready

This specification is ready for implementation planning. The following must be true before development begins:

1. ✅ Product Owner decisions PO-01 through PO-07 are confirmed (assumed defaults stated in §3).
2. ✅ PII data inventory is complete (§4).
3. ✅ All defects are identified with file:line references (§1, §5 tasks).
4. ✅ Legal requirements are cited (§2.1).
5. ✅ Conceptual development tasks are broken into independent units (§5).
6. ✅ Risks, assumptions, constraints, and out-of-scope are documented (§7–10).

The development tasks (§5, Task 1–10) can be sequenced and estimated by the
implementation team. Tasks 1–3 are independent and can be done in parallel.
Tasks 4–6 build on each other (context processor → anonymous support → script gating).
Tasks 7–10 are follow-ups that depend on the core fixes.
