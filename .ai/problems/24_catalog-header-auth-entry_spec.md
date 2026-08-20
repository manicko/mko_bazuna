# Specification: Catalog Header Auth Entry — Login/Cabinet Button + Favorites Badge

**File:** `24_catalog-header-auth-entry_spec.md`
**Status:** Final (ready for implementation planning)
**Date:** 2026-08-20
**Source Decision:** `.ai/problems/Decision_014.md` (PO clarification 2026-08-20)
**PO Decisions:** V1–V6 (see §3)
**Related specs:** `12_seller-cabinet_spec.md`, `14_catalog-ui-avito_spec.md` (R-06), `15_user-cabinet_spec.md`
**Research:**
- `docs/07-design-researches/Design_01/04-homepage-nav.md` §"User Account/Login Placement > 1. Corner Placement"
- `docs/07-design-researches/Design_01/classifieds_design_research_report.md` §§"Navigation and User Actions", "User Account and Settings"
- `docs/07-design-researches/Design_02/01-avito-design.md` §§"Header Navigation", "Top Bar Navigation"
- `docs/07-design-researches/Design_01/06-mobile-patterns.md`
- `docs/01-spec/ui-patterns.md` §"Shared Navigation Headers"
- `docs/01-spec/design-system.md` §§"Header Navigation", "Button Component", "Touch Target Guidelines"
- `.ai/problems/12_seller-cabinet_spec.md` (Specs 12 CR1, D1)
- `.ai/problems/15_user-cabinet_spec.md` (Spec 15 CR14 — shared header shows cabinet entry for authenticated users)

---

## 1. Problem Statement

The catalog header (`components/header_catalog.html`) — rendered on the **homepage** (`ads/list.html`, route `/`) and **ad-detail** pages (`ads/detail.html`, route `/<int:id>/`) — does **not** display a login or cabinet entry for anonymous visitors. Authenticated visitors see only a **tiny text link** reading "Cabinet" in the top-right corner, with no logout, no dropdown menu, and no favorites indicator.

This means the vast majority of visitors (all anonymous buyers, plus authenticated users who are browsing ads) have **no visible path to authenticate or reach their cabinet** from the primary browsing pages. The full auth-aware navigation (`components/header.html` with Login / Cabinet / Dashboard / Admin / Logout) exists but is only loaded on dashboard, edit, login, and cabinet pages — never on the catalog or listing pages.

### PO Clarification (2026-08-20

> "Это неверное заключение аналитика. Я как владелец никогда не просил спрятать кнопку входа."
>
> The auth/cabinet entry **must** appear in `header_catalog.html` on all public pages. The previous Spec_014 R-05c decision to exclude it was an error. The PO confirmed the Avito/OLX compact icon-only pattern with a dropdown menu, plus a heart icon with favorites count badge.

---

## 2. Root Cause Analysis

| # | Gap | Evidence |
|---|-----|----------|
| **RC1** | **`header_catalog.html` lacks a login entry for anonymous users** — the most-visited pages (homepage, ad detail) show no auth nav at all | `header_catalog.html` lines 27-32: only `{% if request.user.is_authenticated %}<a href="{% url 'cabinet:home' %}" class="text-sm">Cabinet</a>{% endif %}`. No `else` branch for anonymous. |
| **RC2** | **Authenticated users see only a tiny text "Cabinet" link** — not a prominent button, no dropdown, no logout | Same lines — plain `<a class="text-sm">Cabinet</a>`, no icon, no menu, no POST logout form. |
| **RC3** | **Two-header split was intentional but auth entry was excluded from the catalog header** — Spec_014 R-05c + PO Q9 scoped auth nav to `header.html` only | Spec 14 §3.1 Fact RC6, §4 R-05c, §6 Q9 resolved: "Dashboard/edit/login pages get a separate, simpler header — not unified." |
| **RC4** | **Test codified the omission** — `test_auth_nav.py::TestAnonymousHeader` docstring explicitly states "login lives on the seller pages" and only asserts CTA + search input | `test_auth_nav.py:96-101` (docstring), `:104-119` (assertions omit any login assertion) |
| **RC5** | **Spec_014 commit (e57dc48) replaced the old header** — the pre-Spec-014 `list.html` used `{% include "components/header.html" %}` (which had Login); commit e57dc48 switched it to `header_catalog.html` which deliberately omits Login | Git history: `e57dc48 feat(catalog-ui): add Avito-style shared catalog header` — "Update outdated auth-nav anonymous header tests to catalog header" |

> **Note on regression:** The PO initially questioned whether this was a regression. Git inspection shows the pre-Spec-014 `list.html` used `{% include "components/header.html" %}` which DID have a Login link. Commit `e57dc48` replaced it with `header_catalog.html` per the then-current Spec-014 decision to separate the headers and exclude auth from the catalog header. The PO has now corrected this decision.

---

## 3. PO Decisions (V1–V6)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **V1 — Catalog header auth entry?** | **(A)** Yes — add login/cabinet entry to `header_catalog.html` on ALL public pages (homepage, ad detail). Revise Spec_014 R-05c. | PO: "Я как владелец никогда не просил спрятать кнопку входа." Decision_014 §1 requires login on all pages. |
| **V2 — Visual form?** | **(B)** Compact icon-only: anonymous = outline user icon; authenticated = filled avatar/initials. | PO: "Да, нам нужен такой же подход относительно кнопки, как и у avito olx." Minimizes header width, leaves room for search + CTA. |
| **V3 — Authenticated dropdown?** | Button + tooltip/dropdown menu (like Avito). | PO: "Кнопка + тултип в котором меню с возможными действиями. На авито так." |
| **V4 — Favorites indicator?** | **(B)** Yes — heart icon with count badge. | PO confirmed. Shows authenticated user's saved-favorites count in the header. |
| **V5 — Mobile behavior?** | **(A)** Auth entry + heart always visible top-right, even on mobile. Category hamburger stays separate. | Header is narrow enough at top-right; hiding auth behind a menu on mobile would hurt conversion. |
| **V6 — Unify headers?** | **(A)** No — keep two separate headers (catalog + auth). Just add auth element to catalog header. | Preserves the Avito-style catalog header (search/categories/breadcrumbs/place-ad) while adding minimal auth nav. |

---

## 4. Confirmed Requirements & Facts

### 4.1 Facts (verified against codebase)

- **F1.** `header_catalog.html` is included via `{% include %}` on `ads/list.html` (line 34) and `ads/detail.html` (line 23). Both are the public catalog pages.
- **F2.** The top-right group in `header_catalog.html` currently reads (per `ui-patterns.md` §"Shared Navigation Headers" lines 240-249):
  ```html
  <div class="flex items-center gap-3">
      {% if request.user.is_authenticated %}
          <a href="{% url 'cabinet:home' %}" class="text-sm">Cabinet</a>
      {% endif %}
      <a href="https://t.me/{{ bot_username }}?start=create_ad" target="_blank"
         class="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg"
         data-place-ad>+ Подать объявление</a>
      {% include "components/language_switcher.html" %}
  </div>
  ```
- **F3.** `components/header.html` (auth-aware header) already implements the correct pattern:
  - Anonymous: `<a href="{% url 'consent:login_issue' %}">Login</a>`
  - Authenticated: Cabinet + Dashboard + (Admin if `is_staff`) + POST+CSRF Logout form
- **F4.** `LOGIN_URL = "/login/issue/"` is set (`base.py:213`). `@login_required` redirects to the Telegram login page.
- **F5.** The `/logout/` POST view exists (`apps/users/urls.py`, `consent:logout`).
- **F6.** The `apps/cabinet` app exists with URLs: `cabinet:home`, `cabinet:favorites`, `cabinet:saved-searches`, `cabinet:search-history`, `cabinet:settings` (`cabinet/urls.py`).
- **F7.** `AdFavorite` model exists (`apps/ads/models.py`) with `UniqueConstraint(user, ad)`. `User.favorites` is the related_name (Spec 15 §4.2).
- **F8.** **No global favorites count** exists in the codebase. `annotate_favorites()` only adds a per-ad `is_favorited` boolean. There is **no** `Count("favorites")` annotation or context variable for a header badge.
- **F9.** `components/favorite_heart.html` exists — a per-ad HTMX heart toggle with `hx-post` to `ads:favorite_toggle`, `hx-target="closest form"`, `hx-swap="outerHTML"`. It uses `hx-on::after-request` to dispatch a `favorite:toggled` custom event — **but `hx-on` is NOT available in HTMX 1.9.12** (Spec 14 §3.2 / researcher confirmation).
- **F10.** `components/login_prompt.html` exists — renders a "login to favorite" prompt with a button linking to `/login/issue/`.
- **F11.** The context processor `apps/core/context_processors.py::header_context` injects `bot_username` and `root_categories` into every template. It could be extended to inject `favorites_count`.
- **F12.** HTMX 1.9.12 is pinned (`https://unpkg.com/htmx.org@1.9.12`). `hx-on` attribute is NOT supported — use vanilla JS `data-*` attributes + event listeners (matching `language_switcher.html` pattern).
- **F13.** Touch target minimum: 44×44 px (design-system.md §"Touch Target Guidelines", Spec 14 R-07d).
- **F14.** The catalog header's top-right group uses Tailwind `flex items-center gap-3` layout.

### 4.2 Confirmed Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| **CR1** | Anonymous visitors on catalog/detail pages see an **icon-only Login button** (outline user icon, 44×44 px, `aria-label="Login"`) in the top-right corner, linking to `/login/issue/`. | Must |
| **CR2** | Authenticated users on catalog/detail pages see a **filled avatar/icon button** (44×44 px) replacing the tiny text "Cabinet" link. Clicking opens a **dropdown menu** (vanilla JS, no `hx-on`). | Must |
| **CR3** | The authenticated-user dropdown menu contains: **Cabinet** (→ `cabinet:home`), **My Ads** (→ `ads:dashboard`), **Favorites** (→ `cabinet:favorites`), **Settings** (→ `cabinet:settings`), **Logout** (POST+CSRF form → `consent:logout`). Staff additionally see **Admin** (→ `/admin/`). | Must |
| **CR4** | A **heart icon** (outline for anonymous, filled for authenticated) with a **favorites count badge** is rendered in the header, alongside the auth entry. | Must |
| **CR5** | For anonymous users, the heart icon is outline (no badge/count); clicking it navigates to `/login/issue/`. | Must |
| **CR6** | For authenticated users, the heart icon shows **filled** state with the **count badge** (integer from `request.user.favorites.count()`). Clicking navigates to `cabinet:favorites`. | Must |
| **CR7** | The auth entry + heart icon are in the **top-right corner**, to the left of the language switcher, **always visible** even on mobile. The category hamburger remains a separate element. | Must |
| **CR8** | All interactive elements meet 44×44 px minimum touch target size. | Must |
| **CR9** | The dropdown menu closes on: outside click, Escape key, and selection (following the `language_switcher.html` vanilla-JS pattern). | Must |
| **CR10** | The auth entry uses a new template include component (e.g. `components/header_auth_entry.html`) — not inline markup duplicated across templates. | Should |
| **CR11** | The existing tiny text "Cabinet" link is removed/replaced by the icon button + dropdown. | Must |

---

## 5. Conceptual Development Tasks

| # | Task | Purpose | Expected Outcome | Dependencies | Effort |
|---|------|---------|------------------|--------------|--------|
| **T1** | Inject `favorites_count` into header context for authenticated users | The heart badge needs the count. Extend the existing `header_context` context processor to add `favorites_count = request.user.favorites.count()` when authenticated (0 or `None` for anonymous). | `header_context` returns `favorites_count` alongside `bot_username` and `root_categories`. | None | LOW |
| **T2** | Create `components/header_auth_entry.html` | New include component for the compact icon-only auth entry. Renders outline user icon (anonymous → `/login/issue/`) or filled avatar/icon (authenticated → dropdown). | Component template with `{% if request.user.is_authenticated %}` branching; 44px touch target; `aria-label`; `data-header-auth-toggle` / `data-header-auth-menu` attributes for JS. | T1 (for badge count) | LOW |
| **T3** | Create `components/header_favorites_badge.html` | New include component for the heart icon + count badge. | Outline heart (anonymous → `/login/issue/`) or filled heart with `<span class="badge">N</span>` (authenticated → `cabinet:favorites`). | T1 | LOW |
| **T4** | Integrate auth entry + heart badge into `header_catalog.html` top-right group | Replace the tiny text "Cabinet" link with the two new components; position them left of the language switcher. | `header_catalog.html` top-right group: `[Heart badge] [Auth button] [Place ad] [Language]`. | T2, T3 | LOW |
| **T5** | Add vanilla JS for dropdown toggle behavior | Open/close the auth dropdown menu. HTMX 1.9.12 has no `hx-on`; must use vanilla JS `data-*` attributes + event listeners, matching `language_switcher.html` pattern. | Inline script in `header_catalog.html` (or a shared JS include) handling `click`/`keydown(Escape)`/outside-click to toggle `#header-auth-menu`. | T2 | LOW |
| **T6** | Fix `favorite_heart.html` `hx-on` bug + add badge-refresh mechanism | The `hx-on::after-request` attribute is not supported in HTMX 1.9.12. Replace with a vanilla JS `htmx:afterRequest` listener. Optionally dispatch a custom event to refresh the header badge count via HTMX after a toggle. | `favorite_heart.html` uses JS listener for `htmx:afterRequest` instead of `hx-on`; badge count refreshes automatically if the refresh endpoint exists. | T7 | MED |
| **T7** | Add HTMX-refresh endpoint for favorites badge count (optional) | If auto-refresh of the header badge is desired after a favorite toggle, add a small view returning the `header_favorites_badge.html` fragment HTML. | New URL (e.g. `GET /cabinet/favorites/count/`) returning the badge fragment; called via HTMX `hx-get` triggered by the `favorite:toggled` event. | T3, T6 | LOW–MED (optional) |
| **T8** | Update `header_catalog.html` body classes and CSRF header | The current `header_catalog.html` is included inside `list.html`/`detail.html`, which already set `<body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>`. Verify no changes needed to CSRF setup. | No change if existing setup covers it. | None | LOW |
| **T9** | Update `test_auth_nav.py` | Per project rule #2 (production code is king), update tests that conflict with the new business requirement. | `TestAnonymousHeader` asserts `/login/issue/` link + `auth-entry` class present in catalog header for anonymous users. Existing auth-header tests remain unchanged. | Spec file (this) | LOW |
| **T10** | Update `ui-patterns.md` and `spec-index.md` | Reflect the new auth entry in the Shared Navigation Headers documentation. | `ui-patterns.md` §"Shared Navigation Headers" documents the auth entry in the catalog header. | None | LOW |

**Critical path:** T1 → T2 → T4 → T5; T1 → T3 → T4; T6 → T7 (optional). T9 runs alongside T4 (tests must match implementation).

---

## 6. Template / Component Structure

### 6.1 Catalog header top-right group (after changes)

```html
<!-- components/header_catalog.html — top-right group -->
<div class="flex items-center gap-2">
    {% include "components/header_favorites_badge.html" %}
    {% include "components/header_auth_entry.html" %}
    <a href="https://t.me/{{ bot_username }}?start=create_ad" target="_blank"
       class="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg"
       data-place-ad>+ Подать объявление</a>
    {% include "components/language_switcher.html" %}
</div>
```

### 6.2 `components/header_auth_entry.html` (anonymous)

```html
{% load i18n %}
{% if not request.user.is_authenticated %}
    <a href="{% url 'consent:login_issue' %}"
       class="flex items-center justify-center w-11 h-11 rounded-lg text-gray-600 hover:bg-gray-100"
       aria-label="{% trans "Login" %}"
       data-header-auth-entry>
        <!-- Outline UserIcon, 20x20 -->
        <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2"
             viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round"
                  d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
        </svg>
    </a>
{% else %}
    <button type="button"
            class="flex items-center justify-center w-11 h-11 rounded-lg hover:bg-gray-100"
            aria-label="{% trans "Account menu" %}"
            aria-haspopup="true"
            aria-expanded="false"
            data-header-auth-toggle>
        {% if request.user.avatar_url %}
            <img src="{{ request.user.avatar_url }}" alt="{% trans "Account" %}"
                 class="w-8 h-8 rounded-full object-cover">
        {% else %}
            <!-- Filled UserIcon fallback, 20x20 -->
            <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" />
            </svg>
        {% endif %}
    </button>

    <!-- Dropdown menu (hidden by default; toggled via vanilla JS) -->
    <div class="absolute right-0 mt-2 w-48 bg-white border border-gray-200 rounded-lg shadow-lg z-50 hidden"
         data-header-auth-menu>
        <div class="py-1">
            <a href="{% url 'cabinet:home' %}" class="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">{% trans "Cabinet" %}</a>
            <a href="{% url 'ads:dashboard' %}" class="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">{% trans "My ads" %}</a>
            <a href="{% url 'cabinet:favorites' %}" class="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">{% trans "Favorites" %}</a>
            {% if request.user.is_staff %}
                <a href="/admin/" class="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">{% trans "Admin" %}</a>
            {% endif %}
            <a href="{% url 'cabinet:settings' %}" class="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">{% trans "Settings" %}</a>
            <form method="post" action="{% url 'consent:logout' %}" class="inline">
                {% csrf_token %}
                <button type="submit" class="block w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">{% trans "Logout" %}</button>
            </form>
        </div>
    </div>
{% endif %}
```

### 6.3 `components/header_favorites_badge.html`

```html
{% load i18n %}
{% if request.user.is_authenticated %}
    <a href="{% url 'cabinet:favorites' %}"
       class="relative flex items-center justify-center w-11 h-11 rounded-lg text-red-500 hover:bg-gray-50"
       aria-label="{% trans "My favorites" %}">
        <!-- Filled heart -->
        <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
        </svg>
        {% if favorites_count %}
            <span class="absolute -top-1 -right-1 flex items-center justify-center min-w-[20px] h-5 px-1 text-xs font-bold text-white bg-red-600 rounded-full">
                {{ favorites_count }}
            </span>
        {% endif %}
    </a>
{% else %}
    <a href="{% url 'consent:login_issue' %}"
       class="flex items-center justify-center w-11 h-11 rounded-lg text-gray-600 hover:bg-gray-100"
       aria-label="{% trans "Login to save favorites" %}">
        <!-- Outline heart -->
        <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2"
             viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round"
                  d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 8.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
        </svg>
    </a>
{% endif %}
```

### 6.4 Vanilla JS for dropdown toggle

Following the `language_switcher.html` pattern (data-* attributes + event listeners):

```javascript
(function () {
    'use strict';

    var toggleBtn = document.querySelector('[data-header-auth-toggle]');
    var menu = document.querySelector('[data-header-auth-menu]');
    if (!toggleBtn || !menu) return;

    function toggle() {
        var isHidden = menu.classList.contains('hidden');
        if (isHidden) {
            menu.classList.remove('hidden');
            toggleBtn.setAttribute('aria-expanded', 'true');
        } else {
            menu.classList.add('hidden');
            toggleBtn.setAttribute('aria-expanded', 'false');
        }
    }

    function close() {
        menu.classList.add('hidden');
        toggleBtn.setAttribute('aria-expanded', 'false');
    }

    toggleBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        toggle();
    });

    // Close on outside click
    document.addEventListener('click', function (e) {
        if (!toggleBtn.contains(e.target) && !menu.contains(e.target)) {
            close();
        }
    });

    // Close on Escape
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            close();
            toggleBtn.focus();
        }
    });

    // Close on navigation (HTMX request starting)
    document.body.addEventListener('htmx:configRequest', function () {
        close();
    });
})();
```

---

## 7. Research Summary

### R1 — Marketplace header auth entry patterns

**Source:** `docs/07-design-researches/Design_01/04-homepage-nav.md` §"User Account/Login Placement > 1. Corner Placement"

- **Avito.ru**: Top-right corner contains "Войти" (Login) button for anonymous users. For authenticated users, replaces with an avatar/profile picture that opens a dropdown menu containing: "Мой профиль" (Profile), "Мои объявления" (My ads), "Избранное" (Favorites), "Настройки" (Settings), "Выйти" (Logout).
- **OLX**: Similar top-right pattern — "Войти" button for anonymous; avatar dropdown for authenticated.
- **Facebook Marketplace**: Uses the Facebook profile picture/avatar in the top-right, which links to the user's account menu.
- **Pattern consensus**: Auth entry is always in the **top-right corner**, **icon-only** or **icon + short text**, with a **dropdown menu** for authenticated users containing account actions. The dropdown closes on outside-click and Escape.

### R2 — Favorites indicator patterns

**Source:** `docs/07-design-researches/Design_02/03-facebook-marketplace.md` §"Favorites/Saved Items Handling"

- **Facebook Marketplace**: Heart icon (outline/filled states) on listing cards. Saved items accessible via "Saved" tab in bottom navigation / profile → Saved items. No count badge in the header itself — saved count is in the dedicated "Saved" view.
- **Avito**: Heart/favorite icon on listing cards. Favorites accessible from the account dropdown.
- **Pattern for Mko Bazuna**: The PO explicitly requested a **heart icon with count badge in the header**. This is a header-level favorites indicator (not just per-card toggle). For anonymous users: outline heart (no badge). For authenticated users: filled heart with count badge.

### R3 — Mobile header behavior

**Source:** `docs/07-design-researches/Design_01/04-homepage-nav.md` §"2. Bottom Navigation (Mobile)", `06-mobile-patterns.md`

- Avito/OLX: The auth entry stays visible in the top-right header on mobile (not moved to bottom nav). The bottom nav is for primary navigation (Home, Categories, Search, Messages, Account).
- Touch target: 44×44 px minimum (iPhones) / 48×48 px (Android).
- **Decision**: Keep the auth entry + heart badge in the top-right header on mobile. Only the category hamburger transforms into an off-canvas panel.

### R4 — HTMX 1.9.12 constraints

**Source:** Spec 014 §3.2, `language_switcher.html` pattern

- `hx-on` (inline event handler attribute) is NOT available in HTMX 1.9.12.
- Dropdown toggle, outside-click, and Escape-to-close must use **vanilla JS** with `data-*` attributes.
- The existing `favorite_heart.html` component incorrectly uses `hx-on::after-request` — this is a pre-existing bug that needs fixing (see T6).

### R5 — Favorites count data source

**Source:** Codebase verification

- The `AdFavorite` model (Spec 15 §4.2) has `UniqueConstraint(user, ad)`.
- For authenticated users: `request.user.favorites.count()` provides the count.
- For anonymous users: no favorites exist (count = 0 / hidden).
- No aggregate/annotated count exists currently — needs to be added to the context processor (T1).

---

## 8. Data Model Notes

No new models or migrations required. The following existing structures are reused:

| Entity | Use |
|--------|-----|
| `User.favorites` (related_name on `AdFavorite.user`) | `request.user.favorites.count()` for badge count |
| `consent:login_issue` URL | Login button deep-link target |
| `consent:logout` URL | Logout POST form action |
| `cabinet:home` | Authenticated dropdown "Cabinet" link |
| `ads:dashboard` | Authenticated dropdown "My Ads" link |
| `cabinet:favorites` | Authenticated dropdown "Favorites" link + heart badge click target |
| `cabinet:settings` | Authenticated dropdown "Settings" link (stub) |

---

## 9. Assumptions

| # | Assumption | Confidence |
|---|-----------|------------|
| A1 | The `User` model has an optional `avatar_url` property/field for displaying a profile picture in the authenticated header button. If not, fall back to an initials-based avatar or filled user icon. | MED — needs verification |
| A2 | The header auth entry does not need to update the favorites badge count in real-time via HTMX after a per-card favorite toggle. The badge refreshes on full page navigation. (Auto-refresh via HTMX is a nice-to-have, handled in T6/T7 as optional.) | MED — PO emphasized "beautiful" UX but didn't explicitly require real-time badge update |
| A3 | Two separate headers remain (catalog + auth). The auth entry is added to `header_catalog.html` only; `header.html` already has its own auth nav and doesn't need changes. | HIGH — PO V6(A) |
| A4 | "Cabinet" (the unified user cabinet from Spec 15) is the correct destination for the authenticated dropdown's main entry. "My ads" links to the existing `/dashboard/` (not refactored). | HIGH — PO V3 references Avito pattern, which includes this structure |
| A5 | The dropdown menu is a simple show/hide toggle (no sub-menus, no flyouts). All menu items are direct links except Logout (POST form). | HIGH — matches Avito/OLX pattern |
| A6 | The heart badge count should only show for authenticated users (anonymous see just the outline heart). | HIGH — PO V4(B) |

---

## 10. Constraints

- **C1.** HTMX 1.9.12 pinned — `hx-on` NOT available. All dropdown JS must be vanilla (`data-*` + event listeners), matching `language_switcher.html`.
- **C2.** No `base.html`/`{% extends %}` — use `{% include %}` component pattern. No new CSS files — Tailwind utilities only.
- **C3.** All fixed values use `StrEnum` — no plain strings for constants. (No new constants introduced in this spec.)
- **C4.** Touch targets ≥ 44×44 px (design-system.md §"Touch Target Guidelines").
- **C5.** English-only code/comments/docstrings/logs. No `print()` — use `logging`.
- **C6.** Logout must be POST + CSRF (existing pattern in `header.html`).
- **C7.** `settings.BOT_USERNAME` must never appear directly in templates — use context variable (already provided by `header_context`).
- **C8.** Existing `favorite_heart.html` uses `hx-on::after-request` which is broken in HTMX 1.9.12 — must be fixed (T6) if badge auto-refresh is implemented.
- **C9.** The `consent_banner.html` line-relative test contract in `test_templates.py` must remain intact.

---

## 11. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|-----------|
| **R1** | The existing `favorite_heart.html` uses `hx-on::after-request` which doesn't work in HTMX 1.9.12. If badge auto-refresh (T7) depends on the event dispatch from this component, it will fail silently. | HIGH | MED | T6 must fix the `hx-on` bug by replacing it with a vanilla JS `htmx:afterRequest` listener before T7 can rely on it. |
| **R2** | Updating `test_auth_nav.py` may break existing test assertions that expected NO login link in the catalog header. | MED | LOW | Tests are updated per project rule #2 (production code is king). New assertions added for login/auth-entry presence. |
| **R3** | Adding `favorites_count` to the context processor adds a DB query (`COUNT`) on every page render for authenticated users. | LOW–MED | LOW | Use `request.user.favorites.count()` (single indexed query); cache if needed. For anonymous, skip entirely. |
| **R4** | The dropdown menu positioning (absolute) may conflict with the existing "All Categories" dropdown (`z-[90]`) and autocomplete dropdown (`z-20`). | LOW | LOW | Position auth dropdown at `z-50` (below categories `z-[90]`, above content). The existing `header.html` dropdown pattern has no positioning issues. |
| **R5** | The `avatar_url` property may not exist on the `User` model, causing template errors for authenticated users. | MED | LOW | Guard with `{% if request.user.avatar_url %}`; fall back to initials/icon. Verify during T1/T2. |

---

## 12. Open Questions

| # | Question | Status |
|---|----------|--------|
| **Q1** | Should the favorites badge count auto-refresh via HTMX after a per-card favorite toggle (T6→T7), or is page-reload-level refresh acceptable for MVP? | **Open** — PO emphasized "beautiful" UX but didn't explicitly require real-time. Recommend: implement auto-refresh (low effort via existing `htmx:afterRequest` pattern). |
| **Q2** | Does the `User` model have an `avatar_url` property or avatar field? If not, what fallback avatar strategy? | **Open** — needs code verification. Fallback: filled `UserIcon` or initials circle. |
| **Q3** | Should the anonymous heart icon badge show "0" or be hidden entirely? | **Resolved (A2)** — hidden (outline heart, no badge) per A2. |

---

## 13. Out of Scope

1. **Unifying the two headers** into a single template (PO V6=A — keep separate).
2. **Admin login changes** (Spec 12 already decided: password-based `/admin/`).
3. **New models or migrations** (reuses existing `AdFavorite`, `User`, and URL routes).
4. **In-web notifications inbox** (Spec 15 §10.1 — Telegram-only).
5. **Full settings page** (Spec 15 — stub only).
6. **Guest favorites** (Spec 15 D2 — login prompt only).
7. **Bottom navigation bar** on mobile (separate from header; future enhancement).
8. **Dark mode** header variants (deferred).

---

## 14. Definition of Ready

A task is ready when all of the following hold:

1. ✅ **CR1–CR11** mapped to implementation tasks (T1–T10).
2. ✅ Root cause verified: `header_catalog.html` omits login for anonymous (RC1); only tiny "Cabinet" text link for authenticated (RC2); Spec-014 R-05c intentionally excluded it (RC3); test codified it (RC4).
3. ✅ PO decisions V1–V6 resolved and documented.
4. ✅ Research summarized (R1–R5): Avito/OLX header auth patterns, favorites indicator, mobile behavior, HTMX 1.9.12 constraints, existing favorites count data source.
5. ✅ No new models/migrations required; existing `AdFavorite`, `User`, URLs reused.
6. ✅ Test contract updated: `test_auth_nav.py::TestAnonymousHeader` now asserts login link + auth entry present in catalog header.
7. ✅ Spec-014 revised: R-06 added (auth entry in catalog header), AC-08 updated, Q10 added (PO clarification).
8. ✅ Constraints documented: HTMX 1.9.12 (no `hx-on`), 44px touch targets, `{% include %}` pattern, POST+CSRF logout, no `settings.BOT_USERNAME` in templates.
9. ✅ Risks documented (notably R1: broken `hx-on` in `favorite_heart.html`).
10. ✅ Template/component structure documented (§6) with concrete HTML + JS examples.

---

## 15. Files Touched

| File | Action |
|------|--------|
| `.ai/problems/24_catalog-header-auth-entry_spec.md` | **NEW** — this specification |
| `.ai/problems/14_catalog-ui-avito_spec.md` | **EDIT** — added R-06 (auth entry), renumbered R-06→R-07, updated AC-08, Out of Scope, Dependencies, Q10 |
| `.ai/problems/Decision_014.md` | **EDIT** — added PO Clarification (2026-08-20) |
| `src/backend/apps/ads/tests/test_auth_nav.py` | **EDIT** — updated TestAnonymousHeader docstring + assertions (login link + auth-entry present) |
| `docs/01-spec/ui-patterns.md` | **TODO** — update §"Shared Navigation Headers" to document auth entry in catalog header |
| `docs/01-spec/spec-index.md` | **TODO** — reference if header architecture notes need updating |

---

*Specification produced from PO clarification (V1–V6) on 2026-08-20, existing Spec-012/014/015, and research from `docs/07-design-researches/`. All facts verified against the codebase.*