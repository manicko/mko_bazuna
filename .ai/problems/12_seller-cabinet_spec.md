# Specification: Seller Cabinet — Authentication Navigation & Admin Login Separation

**File:** `12_seller-cabinet_spec.md`
**Status:** Final (ready for implementation planning)
**Date:** 2026-08-18
**Source Decision:** `.ai/problems/Decision_014.md`
**Research:**
- `.ai/researches/admin-auth-separation-research.md` (Approach A recommended)
- `docs/99-agent/seller-dashboard-research.md` (Avito/OLX competitor analysis)

---

## 1. Problem Statement

The Mko Bazuna classifieds board has no visible, persistent authentication entry point on its public pages. Sellers who have already authenticated have no consistent "Go to cabinet" link. Additionally, the existing "Logout" links in templates are dead (no `/logout/` route), and `@login_required` redirects to a non-existent `/accounts/login/` URL. The product owner (Decision_014.md) requests:

1. A seller cabinet entry point in the top-right corner of **all pages** — "Login/Register" for anonymous visitors, "Go to cabinet" for authenticated sellers.
2. The ability to manage ads from the cabinet (ad lifecycle actions).
3. Research into Avito + OLX seller-cabinet functionality to determine what should be included.
4. Investigation of how to separate admin login from seller (Telegram) login.

### Root causes (verified against codebase)

| # | Root cause | Evidence |
|---|-----------|----------|
| RC1 | **No shared header / auth-aware navigation** — each of the 6 public templates (`list.html`, `detail.html`, `dashboard.html`, `edit.html`, `seller_dashboard.html`, `moderation_dashboard.html`) duplicates its own inline `<header>` with only a site logo + language switcher. No "Login" link exists for anonymous users on any buyer-facing page. | `template_architecture_research.md:22-32`; grep confirms no `base.html` |
| RC2 | **Dead `/logout/` route** — 3 templates hardcode `<a href="/logout/">Logout</a>` (GET), but `config/urls.py` has no logout URL pattern and no logout view exists in `apps/users/`. | `config/urls.py:10-19`; `dashboard.html:25`, `seller_dashboard.html:30`, `moderation_dashboard.html:28` |
| RC3 | **`LOGIN_URL` unset** — `base.py` sets `LOGIN_REDIRECT_URL` and `LOGOUT_REDIRECT_URL` but not `LOGIN_URL`. Django defaults to `/accounts/login/`, which doesn't exist (no `django.contrib.auth.urls` included). `@login_required` redirects fail. | `base.py:208-209`; `config/urls.py` (no auth.urls) |
| RC4 | **Logout via GET** — the existing `<a href="/logout/">` links use GET, which is vulnerable to logout-CSRF (an attacker can embed `<img src="/logout/">`). Django 5.0 removed GET-based logout for this reason. | Templates use `<a>` tags; `LogoutView.http_method_names = ["post", "options"]` |
| RC5 | **Admin/seller auth not truly separated at the navigation layer** — admin login is password-based at `/admin/`, sellers use Telegram deep-link login, but there is no header-level distinction. The documentation incorrectly claims `telegram_id` is `USERNAME_FIELD`. | `models.py:88` (`USERNAME_FIELD = "username"`); `docker-deployment.md:624-627` contradicts |

---

## 2. Confirmed Requirements & Facts

### 2.1 Facts (verified against current codebase)

- **F1.** Existing seller login flow (decision H, US-S1): `/login/issue/` → renders Telegram deep-link `t.me/<bot>?start=login_<token>` → user taps "Login" in bot → bot writes `telegram_id` into `LoginToken` via `UPDATE ... RETURNING` (atomic, two-phase claim) → `/login/status/?token=` polls and establishes web session via `django.contrib.auth.login()`. Token stored as SHA-256 hash only; 5-min expiry; rate-limited 10 req/60s per IP. `login_issue.html` template exists and polls via JavaScript.
- **F2.** Existing seller dashboard at `/dashboard/` (`apps/ads/views/dashboard.py:22`): lists ads grouped by status (PUBLISHED, ON_MODERATION, ON_MODERATION_FAILED, ARCHIVED, REJECTED) with per-ad analytics (views/contacts, 3 time ranges), edit/archive/reactivate/delete actions. Already `@login_required`. Uses `SellerStats` service from `analytics` app.
- **F3.** Admin access: Django `/admin/` uses standard `AdminAuthenticationForm` (password-based, enforces `is_staff`). Admin user created via `create_admin_user` command with `telegram_id=-1` placeholder and `is_staff=True, is_superuser=True`. Moderation views use `staff_required` decorator (404 for non-staff).
- **F4.** Session cookies: `SESSION_COOKIE_SECURE/HTTPONLY/SAMESITE=Lax`, `CSRF_COOKIE_SECURE/HTTPONLY/SAMESITE=Lax` all set in `base.py:65-72`.
- **F5.** `LOGIN_REDIRECT_URL = "/"`, `LOGOUT_REDIRECT_URL = "/"` set in `base.py:208-209`.
- **F6.** No `base.html` / `{% extends %}` pattern exists. Project uses `{% include %}` for components (`consent_banner.html`, `language_switcher.html`, `ad_list.html`).
- **F7.** Consent banner guard: `{% if not request.user.is_authenticated or not request.user.is_deleted %}` used in `list.html:56`, `detail.html:106`, `dashboard.html:169`.
- **F8.** `LOGIN_URL` is unset → Django default `/accounts/login/` (which 404s).
- **F9.** `django.contrib.auth.urls` is NOT included in `config/urls.py`.
- **F10.** Users are created by the Telegram bot (not a web registration form). One user = one Telegram account. `telegram_id` is unique, nullable (null on GDPR erasure).

### 2.2 Confirmed Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| CR1 | Anonymous visitors see a "Login" link in the top-right corner on ALL public pages (listings, detail, dashboard, login page) | Must |
| CR2 | Authenticated sellers see a "Dashboard" link (→ existing `/dashboard/`) and a "Logout" button in the top-right corner | Must |
| CR3 | The "Login" link routes to the existing Telegram login page (`/login/issue/`) | Must |
| CR4 | Logout must be POST-based with CSRF protection (not GET) | Must |
| CR5 | `@login_required`-protected views must redirect to a working login page (`/login/issue/`) | Must |
| CR6 | Admin login remains password-based at `/admin/` (separate from seller Telegram login) | Must |
| CR7 | Staff users see an "Admin" link in the header; non-staff authenticated users do not | Should |
| CR8 | The header is a shared component (`{% include %}`), not duplicated markup | Should |
| CR9 | Consent banner continues to be guarded correctly on all pages that include the header | Must |
| CR10 | No new models or migrations required for this spec | Must |

### 2.3 Product Owner Decisions (documented from Decision_014.md + research)

| Decision | What the owner said / intended | Rationale |
|----------|-------------------------------|-----------|
| **D1** | Seller cabinet: "If not logged in, a working Login/Register button on all pages" | Decision_014.md line 3 |
| **D2** | "If logged in — Go to cabinet" | Decision_014.md line 5 |
| **D3** | "From the cabinet, manage ads" | Decision_014.md line 6 |
| **D4** | Admin login must be separated from seller login | Decision_014.md line 10 |
| **D5** | Research Avito + OLX cabinet functionality, then decide what to include | Decision_014.md line 8 |

### 2.4 Resolved PO Questions (research-backed)

| Question | Options | Chosen | Rationale |
|----------|---------|--------|-----------|
| Q1 — Should the "Login/Register" button link to the existing Telegram login, or should a separate registration form be built? | (A) Link to existing `/login/issue/` (Telegram deep-link); (B) Build a separate registration form | **(A)** | Mko Bazuna has no registration form — users are created by the Telegram bot on first contact (F10). The Telegram login flow serves as both login and implicit registration. Building a separate registration form would require a new user-creation flow (email/phone/OTP), contradicting the Telegram-only auth model (decision H). The button should say "Login" (not "Login/Register") since registration is bot-side. **Open for PO confirmation.** |
| Q2 — What is the scope of cabinet features for THIS spec? | (A) Auth navigation only (button + logout + shared header, reusing existing `/dashboard/`); (B) Also Phase 2 features (bulk actions, favorites, rejection detail, etc.) | **(A)** | The existing `/dashboard/` already provides full ad lifecycle management (F2). The request's literal asks are: (1) auth button in header, (2) cabinet entry, (3) manage ads (already exists). Avito/Olx research (seller-dashboard-research.md §4.1) ranks Phase 2 gaps as "low difficulty" but they are enhancements, not prerequisites for the cabinet navigation. Including them would expand scope unnecessarily. **Phase 2 features documented as future work.** |
| Q3 — Should admin login transition to Telegram (with `is_staff` flag)? | (A) Keep password-based `/admin/`; (B) Unified Telegram login for admin + seller | **(A)** | Research (admin-auth-separation-research.md §3.2, §5) shows Telegram-based admin login adds attack surface (SIM swap, device theft, bot-side token-claim bugs affecting admin privileges), requires model + migration changes, and contradicts the `telegram_id=-1` convention used throughout deployment docs. Password-based admin behind nginx TLS + rate limiting is the industry-standard, lower-risk choice. US-A1 ("separate login or Telegram with confirmed role") is satisfied by the current password approach. |
| Q4 — Should `/logout/` be implemented now? | (A) Yes, POST + CSRF; (B) Leave dead links | **(A)** | Three templates reference `/logout/` as a GET `<a>` link that currently 404s. This is a broken UX + logout-CSRF vulnerability. Django 5.0 removed GET-based logout specifically to prevent CSRF. |
| Q5 — Should a shared header component be extracted? | (A) Yes, via `{% include "components/header.html" %}`; (B) Duplicate new button into each template | **(A)** | Project already uses `{% include %}` for components (consent_banner, language_switcher). 6 templates duplicate the header. Following existing patterns, a shared header is the DRY, lowest-risk approach. The existing `template_architecture_research.md` independently recommends this. |

---

## 3. Conceptual Development Tasks

### Task 1 — Implement POST-based `/logout/` view
**Purpose:** Close the dead logout route and eliminate the GET-based logout-CSRF vulnerability.
**Expected outcome:**
- New view `apps/users/views/logout.py` with `logout_view()` function decorated `@require_POST` + `@never_cache`, calling `django.contrib.auth.logout()` (which flushes the session), redirecting to `LOGOUT_REDIRECT_URL` (`/`).
- URL registered at `apps/users/urls.py` as `path("logout/", logout_view, name="logout")`.
- All 3 templates updated to use POST form with `{% csrf_token %}` instead of dead GET `<a>` link.
**Dependencies:** None.
**Estimated effort:** LOW.
**Spec references:** RC2, RC4, CR3, CR4.

### Task 2 — Set `LOGIN_URL` to the Telegram login page
**Purpose:** Fix the broken `@login_required` redirect target (currently 404s to `/accounts/login/`).
**Expected outcome:**
- Add `LOGIN_URL = "/login/issue/"` to `config/settings/base.py` (after `LOGOUT_REDIRECT_URL`).
- `@login_required` now redirects anonymous users to the working Telegram login page.
**Dependencies:** None.
**Estimated effort:** LOW.
**Spec references:** RC3, CR5.

### Task 3 — Extract shared `components/header.html` with conditional auth-aware navigation
**Purpose:** Replace 6 duplicated inline headers with a single `{% include %}` component that shows Login for anonymous users and Dashboard/Logout for authenticated users.
**Expected outcome:**
- New template `templates/components/header.html` with:
  - Site logo (always)
  - `{% include "components/language_switcher.html" %}` (always)
  - Conditional nav: anonymous → `<a href="{% url 'consent:login_issue' %}">Login</a>`; authenticated → `Dashboard` (if `is_staff` also show `Admin`), `Logout` (POST form with CSRF)
  - Guard: `{% if not request.user.is_authenticated or not request.user.is_deleted %}` around consent banner (preserved from existing pattern)
- Replace inline `<header>...</header>` in `list.html`, `detail.html`, `dashboard.html`, `edit.html`, `seller_dashboard.html`, `moderation_dashboard.html` with `{% include "components/header.html" %}`
- `login_issue.html` (which has no header) gets the shared header included too.
**Dependencies:** Task 1 (logout route must exist for the header's CSRF POST form).
**Estimated effort:** LOW–MEDIUM (6 template updates).
**Spec references:** RC1, CR1, CR2, CR7, CR8, CR9.

### Task 4 — Wire up the ad-management cabinet (reusing existing dashboard)
**Purpose:** Ensure the authenticated dashboard is fully reachable and functional as the "cabinet" for ad management. No new features — verify the existing `/dashboard/` covers the "manage ads" requirement.
**Expected outcome:**
- Header "Dashboard" link points to existing `{% url 'ads:dashboard' %}`.
- Verify the existing dashboard provides: list ads by status, edit, archive, reactivate, delete (US-S5, S6, S7).
- Verify analytics trust dashboard link (`/analytics/trust/`) is reachable from the dashboard.
- No new dashboard code required — this task is verification + link wiring.
**Dependencies:** Task 2 (LOGIN_URL must work so dashboard `@login_required` redirect succeeds).
**Estimated effort:** LOW (verification, no new code).
**Spec references:** RC1, CR2, D2, D3, D5-Q2(A).

### Task 5 — Fix documentation discrepancy (`USERNAME_FIELD`)
**Purpose:** Correct docs that incorrectly state `telegram_id` is `USERNAME_FIELD` for admin login.
**Expected outcome:**
- Update `docs/ops/docker-deployment.md` and `docs/04-user-stories/admin-stories.md` to state that admin login uses the `username` field (set to `"admin"` by `create_admin_user`), NOT `telegram_id`.
- Add a note that admin password is from `ADMIN_PASSWORD` env var.
**Dependencies:** None.
**Estimated effort:** LOW.
**Spec references:** RC5, CR6.

### Task 6 — Consolidate duplicated `staff_required` decorator (optional cleanup)
**Purpose:** Remove the duplicated `_staff_required` in `analytics/views/moderation_dashboard.py` and use the shared one from `apps/moderation/views/decorators.py`.
**Expected outcome:** One canonical `staff_required` decorator.
**Dependencies:** None.
**Estimated effort:** LOW.
**Spec references:** admin-auth-separation-research.md §1.3, §6 (gap #5).

---

## 4. Ad Cabinet Feature Scope (from Avito + OLX research)

### 4.1 Features Already Present in Mko Bazuna

Source: `seller-dashboard-research.md` §2 + source code verification

| Feature | Mko Bazuna | Avito Regular | Avito Pro | OLX.ua | OLX.pl |
|---------|-----------|---------------|-----------|--------|--------|
| Login (Telegram deep-link) | ✅ | ❌ (email/phone) | ❌ | ❌ | ❌ |
| Ad list grouped by status | ✅ (dashboard: published/moderation/archived/rejected) | ✅ tabs | ✅ | ✅ | ✅ |
| Edit ad (with C2 re-moderation) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Archive / unpublish | ✅ | ✅ | ✅ | ✅ | ✅ |
| Reactivate | ✅ | ✅ | ✅ | ✅ | ✅ |
| Soft delete | ✅ | ✅ | ✅ | ✅ | ✅ |
| Per-ad analytics (views/contacts) | ✅ (7d/30d/all) | ✅ | ✅ | ✅ | ✅ |
| Rejection reason shown | ✅ | ✅ | ✅ | ✅ | ✅ |
| Fix & resubmit | ✅ (text edit → re-moderation) | ✅ | ✅ | ✅ | ✅ |
| Seller verification (trust levels) | ✅ (UNVERIFIED→VERIFIED→TRUSTED→PRO) | ✅ | ✅ | ✅ | ✅ |
| Resubmit after rejection | ✅ | ✅ | ✅ | ✅ | ✅ |

### 4.2 Features Absent but Relevant (Phase 2–5)

Source: `seller-dashboard-research.md` §4

| Feature | Mko Bazuna | Avito | OLX | Phase | Difficulty | Notes |
|---------|-----------|-------|-----|-------|------------|-------|
| **Bulk actions** (select + archive/delete/reactivate) | ❌ | ✅ | ✅ | Phase 2 | Low | Uses existing `Ad.transition_to()` logic |
| **Favorites count** in per-ad analytics | ❌ | ✅ | ✅ | Phase 2 | Low | `AnalyticsEventType.AD_FAVORITED` enum exists |
| **Deactivate vs. Archive distinction** | ❌ | ✅ | ✅ | Phase 2 | Low | New status or `is_active` flag |
| **Rejection reason detail** | ✅ (basic) | ✅ | ✅ | Phase 2 | Low | Extend `ModeratorActionLog` UI |
| **In-app messaging** | ❌ (Telegram only) | ✅ | ✅ | Phase 3 | Medium | Ad detail docstring says "Phase 3" |
| **Message templates** | ❌ | ✅ | ✅ | Phase 3 | Low | |
| **Schedule reactivation** | ❌ | ✅ | ✅ | Phase 3 | Medium | Needs `scheduled_publish_at` field |
| **Wallet / billing** | ❌ | ✅ | ✅ | Phase 4 | High | Requires payment provider |
| **Promotion services** (highlight, raise to top) | ❌ | ✅ | ✅ | Phase 4 | Med-High | Requires wallet + ranking |
| **Seller rating / reviews** | ❌ | ✅ | ✅ | Phase 4 | Medium | |
| **Business page / storefront** | ❌ | ❌ | ✅ | Phase 4 | Medium | |
| **Lead management** | ❌ | ✅ (Pro) | ✅ | Phase 5 | High | |
| **Bulk API** | ❌ | ✅ (Pro) | ✅ | Phase 5 | High | |
| **CRM / webhook** | ❌ | ✅ (Pro) | ✅ | Phase 5 | High | |
| **Demand analytics** | ❌ | ✅ (Pro) | ❌ | Phase 5 | High | |

### 4.3 Scope Decision for This Spec

**This spec covers Task 4 (auth navigation + existing dashboard wiring) only.** All Phase 2–5 features in §4.2 are **explicitly out of scope** but documented here as future work with difficulty estimates from the research report. The existing `/dashboard/` already satisfies the "manage ads" requirement (D3). No new cabinet features are added in this spec.

---

## 5. Admin Login Separation

### 5.1 Current State

- **Seller login**: Telegram deep-link flow (`/login/issue/` → `/login/status/`) → `auth_login()` → session. Users identified by `telegram_id`.
- **Admin login**: Django `/admin/` with `AdminAuthenticationForm` (password-based). Requires `is_staff`. Admin created via `create_admin_user` with `telegram_id=-1` placeholder, `username="admin"`, `is_staff=True, is_superuser=True`.
- Both share the same `User` table (`users`) and the same session backend (`django_session`).

### 5.2 Recommended Approach: Approach A (password-based admin, separate from Telegram login)

Source: `admin-auth-separation-research.md` §5, ranked #1

**Rationale:**
- The admin role is high-privilege, infrequent-use. Password-based access behind nginx TLS + rate limiting is industry-standard.
- Telegram-based admin login (Approach B) adds attack surface (SIM swap, device theft), requires model + migration changes, and breaks the `telegram_id=-1` convention used throughout deployment.
- Custom `AdminSite` (Approach C) requires refactoring 6+ `admin.py` files for zero security gain — access control (`is_staff`) is already enforced by `AdminAuthenticationForm` and the `staff_required` decorator.
- The actual admin/seller separation at the **view layer** is already working: `/admin/` enforces `is_staff` via `AdminAuthenticationForm`; `/moderation/` enforces staff via `staff_required` decorator; `/dashboard/` enforces `@login_required` (any authenticated user).

**Decision:** Admin login **remains password-based** at `/admin/`. No changes to admin auth mechanism. This spec only adds the header-level "Admin" link (visible to `is_staff` users) and fixes the logout/LOGIN_URL gaps.

### 5.3 Security Posture (After This Spec)

| Threat | Current State | After This Spec | Mitigation |
|--------|--------------|-----------------|------------|
| Dead logout route | Links 404 | ✅ Working POST + CSRF | Task 1 |
| Logout CSRF (GET) | Vulnerable | ✅ POST + CSRF token | Task 1 |
| Broken `@login_required` redirect | 404s to `/accounts/login/` | ✅ Redirects to `/login/issue/` | Task 2 |
| No Login link for buyers | Hidden | ✅ Visible in shared header | Task 3 |
| Admin/seller credential cross-contamination | `telegram_id=-1` prevents it | ✅ Unchanged | F3 (existing design) |
| Session fixation on login | `auth_login()` cycles session key | ✅ Already mitigated (consent.py:285 comment) | F1 (existing) |
| Session not invalidated on logout | N/A (logout broken) | ✅ `session.flush()` via `logout()` | Task 1 |

---

## 6. Conceptual Development Tasks Summary

| # | Task | Dependencies | Effort |
|---|------|-------------|--------|
| T1 | Implement POST-based `/logout/` view + URL | None | LOW |
| T2 | Set `LOGIN_URL = "/login/issue/"` in settings | None | LOW |
| T3 | Extract shared `components/header.html` + conditional auth nav; update 6 templates + login page | T1 (logout route must exist) | LOW–MED |
| T4 | Wire cabinet entry to existing `/dashboard/` (manage ads) | T2 (LOGIN_URL must work) | LOW |
| T5 | Fix documentation: `USERNAME_FIELD` = `"username"` not `telegram_id` | None | LOW |
| T6 | (Optional) Consolidate duplicated `staff_required` decorator | None | LOW |

**Critical path:** T1 → T3 (header needs logout route) → T4 (header needs working LOGIN_URL). T2 and T5 are independent.

---

## 7. Assumptions

| # | Assumption | Confidence |
|---|-----------|------------|
| A1 | The Telegram login flow (`/login/issue/`) is the sole authentication method. No web registration form is needed or desired. | HIGH — decision H, US-S1, no registration model exists |
| A2 | The existing `/dashboard/` (ads grouped by status with edit/archive/reactivate/delete + analytics) is sufficient for "manage ads from cabinet." No new ad-management features are required in this spec. | HIGH — verified against `ads/views/dashboard.py` and the dashboard template |
| A3 | The header button label should be "Login" (not "Login/Register") since registration is bot-side, not web-side. The PO's "Register" terminology is satisfied by the Telegram flow (users are created on first bot contact). | MEDIUM — awaits PO confirmation (Q1) |
| A4 | A shared `{% include %}` header component is acceptable (not a full `base.html` / `{% extends %}` migration). This follows the project's existing component pattern. | HIGH — `template_architecture_research.md` recommends this |
| A5 | Admin login stays password-based. Admins do not log in via Telegram. | HIGH — research-recommended, lower risk |
| A6 | No new database models or migrations are needed. | HIGH — verified: no schema changes required |

---

## 8. Constraints

- **C1.** Two processes (web gunicorn + bot aiogram) share one DB. Migrations run once before both start. No migration changes in this spec.
- **C2.** HTMX MPA — server-rendered, no SPA framework. Header component must be a Django template fragment (`{% include %}`), not a JS component.
- **C3.** All fixed values use `StrEnum` — no plain strings for constants. (No new constants needed in this spec.)
- **C4.** English-only in code, comments, logs. No `print()` — use `logger`.
- **C5.** Production code is king — if tests conflict, fix tests, not production code.
- **C6.** Follow existing patterns — `{% include %}` for components, function-based views, `@login_required`/`@staff_required` decorators.
- **C7.** No third-party auth packages (django-allauth, etc.) — Telegram deep-link + Django built-in auth only.

---

## 9. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|-----------|
| R1 | Updating 6 templates to use `{% include %}` header may break existing template tests that assert on specific header markup | MEDIUM | MEDIUM | Run `uv run pytest` after template changes; review `test_templates.py` |
| R2 | The logout POST form requires a valid CSRF token on every page that shows the header. If CSRF middleware is misconfigured, logout breaks | LOW | MEDIUM | CSRF middleware is already in `MIDDLEWARE` (`base.py:116`); templates use `{% csrf_token %}` |
| R3 | Setting `LOGIN_URL = "/login/issue/""` may affect existing test assertions that expect `/accounts/login/` redirect | LOW | LOW | Search existing tests for `accounts/login` assertions; update if needed |
| R4 | Shared header may render differently on pages with different CSS/JS context (e.g. HTMX partials) | LOW | LOW | Header is plain HTML + Tailwind; no JS dependency; HTMX only on `list.html` |
| R5 | Consent banner guard (`is_consent_given`) must continue to work after header extraction | LOW | LOW | Preserve existing `{% if not request.user.is_authenticated or not request.user.is_deleted %}` guard pattern |

---

## 10. Open Questions

| # | Question | Status |
|---|----------|--------|
| Q1 | Should the header button say "Login" or "Login/Register"? (Mko Bazuna has no web registration — the Telegram flow handles both.) | **Resolved (recommended: "Login")** — awaiting PO confirmation |
| Q2 | Should the "Admin" link in the header be visible to all `is_staff` users, or only superusers? | **Resolved (recommended: `is_staff`)** — `staff_required` decorator already uses `is_staff` |
| Q3 | Should the logout redirect go to `/` (home) or back to the login page? | **Resolved (recommended: `/`)** — `LOGOUT_REDIRECT_URL = "/"` already set |
| Q4 | Should the header component also be included on the moderation/analytics dashboard pages? | **Resolved (recommended: yes)** — all 6 templates listed in T3 include these |

---

## 11. Out of Scope

1. **Bulk ad actions** (select + archive/delete/reactivate) — Phase 2, `seller-dashboard-research.md` §4.1.
2. **In-app messaging** — Phase 3, ad detail docstring says "Contact button placeholder for Phase 3."
3. **Wallet / billing system** — Phase 4, requires payment provider integration.
4. **Promotion / boosting services** — Phase 4, requires wallet + ranking changes.
5. **Seller ratings / reviews** — Phase 4.
6. **Ad scheduling / auto-republish** — Phase 3.
7. **Favorites count in analytics** — Phase 2.
8. **Deactivate vs. Archive distinction** — Phase 2.
9. **Business page / storefront** — Phase 4.
10. **Lead management dashboard** — Phase 5.
11. **Bulk management API** — Phase 5.
12. **CRM / webhook integration** — Phase 5.
13. **Any new database models or migrations** — none needed in this spec.
14. **Unified Telegram admin login** (Approach B) — rejected by research (admin-auth-separation-research.md §3.2).

---

## 12. Definition of Ready

This specification is ready for implementation planning when all of the following are verified:

1. ✅ All business requirements from Decision_014.md are mapped to confirmed requirements (CR1–CR10).
2. ✅ Both research reports are complete and evidence-based:
   - `seller-dashboard-research.md` — Avito/OLX feature comparison (11 sources).
   - `admin-auth-separation-research.md` — 3 technical approaches ranked (Approach A recommended).
3. ✅ Codebase facts verified: login flow exists (`/login/issue/`, `/login/status/`), dashboard exists (`/dashboard/`), logout route does NOT exist, `LOGIN_URL` is unset, no shared header component.
4. ✅ All conceptual tasks (T1–T6) are independent or have clear dependency ordering.
5. ✅ Scope boundary is clear: auth navigation + existing dashboard wiring only. Phase 2–5 cabinet features are explicitly out of scope.
6. ✅ Admin login approach decided: password-based (Approach A), no changes to admin auth mechanism.
7. ✅ All assumptions, constraints, risks, and open questions are documented.
8. ✅ No new models, migrations, or dependencies required.
9. ✅ Existing patterns followed: `{% include %}` for components, function-based views, `@login_required`/`@staff_required`.
