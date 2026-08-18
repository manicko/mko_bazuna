# Implementation Plan: Seller Cabinet (Auth Navigation) + Ad Detail Gallery

**Plan ID:** `14_seller-cabinet-ad-gallery_plan`
**Source Specs:**
- `.ai/problems/12_seller-cabinet_spec.md`
- `.ai/problems/13_ad-detail-gallery_spec.md`
**Date:** 2026-08-18
**Status:** Implementation-ready

---

## Executive Summary

Two independent, decision-complete specifications are planned together:

1. **Seller Cabinet (spec 12)** — adds a persistent, auth-aware navigation entry point (Login / Dashboard / Admin / Logout) to all public pages, fixes the dead GET logout route, sets `LOGIN_URL`, extracts a shared header component, and corrects admin-auth documentation.
2. **Ad Detail Gallery (spec 13)** — replaces the static image grid on the ad detail page with a GLightbox fullscreen gallery (CDN-loaded, inline init).

Both specs are **logically independent** and share **zero business logic and zero settings**. The shared artifacts are limited to `ads/detail.html` (touched by SCB-003 and GAL-001) and `docs/01-spec/ui-patterns.md` (touched by DOC-001 and DOC-002). Tasks touching a shared file are **serialized** to avoid concurrent-edit conflicts; the remaining work runs fully in parallel.

The plan therefore sequences work across **five phases**: foundations → shared header boundary → gallery → documentation → test authoring & validation. Dedicated **test-authoring tasks** validate **user-visible behavior, end-to-end workflows, regressions, and integration boundaries** for each spec, and dedicated **documentation tasks** keep the pattern docs current (project rule #14).

**Key implementation decisions surfaced (not in either spec verbatim, but required by them):**
- The dashboard "Withdraw Data" form currently lives *inside* `dashboard.html`'s inline `<header>`. Extracting a uniform shared header would silently drop that capability. It must be relocated into the dashboard `<main>` body as part of the header-extraction task.
- The consent banner is rendered at the *bottom* of each page, not inside the `<header>`. Header extraction must **not** move it into the header; existing per-page guards (CR9) remain untouched.
- CSP is **report-only** in this codebase (verified: `apps/core/views.py::csp_report` docstring "No CSP is enforced at this stage" + no `Content-Security-Policy` header emitted in `base.py`/`prod.py`). Therefore the gallery's unpkg CDN load and GLightbox inline styles are **not blocked** — **no CSP settings change is required** for spec 13.

**Risk profile:** No database schema, migrations, build, or deployment changes. The only settings change is one `LOGIN_URL` line. The higher-risk items are the multi-template header extraction (SCB-003) and the frontend gallery (GAL-001). Both have dedicated documentation and test-authoring tasks. Existing redirect test (`analytics/tests/test_views.py:131` asserts `/login/` substring) remains green after `LOGIN_URL` changes.

---

## Execution DAG

```
Phase 1 — Foundations (parallel, no shared files)
├── SCB-001: POST-based /logout/ view + URL             (apps/users/views/logout.py, apps/users/urls.py)
├── SCB-002: Set LOGIN_URL = /login/issue/              (config/settings/base.py)
├── SCB-004: Fix USERNAME_FIELD docs discrepancy        (docs/ops/docker-deployment.md, docs/04-user-stories/admin-stories.md)
└── SCB-005: Consolidate duplicated staff_required      (apps/analytics/views/moderation_dashboard.py)

Phase 2 — Shared template boundary (single-file serialization on detail.html)
└── SCB-003: Extract components/header.html (auth-aware nav)   (components/header.html NEW + 7 templates)
     └── depends_on: SCB-001 (logout route must exist for header POST form), SCB-002

Phase 3 — Gallery (must wait for detail.html header extraction to avoid file conflict)
└── GAL-001: GLightbox gallery on ads/detail.html        (templates/ads/detail.html ONLY)
     └── depends_on: SCB-003 (shared detail.html edit)

Phase 4 — Documentation (parallel, except ui-patterns.md is serialized)
├── DOC-001: Seller-cabinet / auth-nav docs              (docs/01-spec/ui-patterns.md, docs/06-design-system/components.md, docs/04-user-stories/seller-stories.md)
│    └── depends_on: SCB-002, SCB-003
└── DOC-002: Ad-detail gallery docs                      (docs/01-spec/ui-patterns.md — same file, serialized)
     └── depends_on: GAL-001, DOC-001 (serialized on ui-patterns.md to avoid a concurrent-edit conflict)

Phase 5 — Test authoring & validation (parallel, distinct test files)
├── TST-SCB-001: Seller-cabinet test suite — behavior / workflow / regression / integration   depends_on: SCB-001, SCB-002, SCB-003
└── TST-GAL-001: Ad-detail gallery test suite — behavior / workflow / regression / integration  depends_on: GAL-001
```

### Dependency graph (mermaid)

```mermaid
graph TD
    SCB1[SCB-001: logout view+URL] --> SCB3[SCB-003: shared header extraction]
    SCB2[SCB-002: LOGIN_URL] --> SCB3
    SCB3 --> GAL1[GAL-001: GLightbox gallery]
    SCB3 --> DOC1[DOC-001: auth-nav docs]
    GAL1 --> DOC2[DOC-002: gallery docs]
    DOC1 --> DOC2
    SCB1 --> TST1[TST-SCB-001: cabinet test suite]
    SCB2 --> TST1
    SCB3 --> TST1
    GAL1 --> TST2[TST-GAL-001: gallery test suite]
    SCB4[SCB-004: USERNAME_FIELD docs] -. standalone
    SCB5[SCB-005: decorator cleanup] -. standalone
```

### Sequencing rationale

1. **SCB-001 and SCB-002 are independent, low-risk backend/settings changes** that unblock the header. They run in parallel in Phase 1.

2. **SCB-003 (header extraction) is the spec's only true dependency node.** It needs SCB-001's `consent:logout` URL (the shared header renders a POST logout form) and SCB-002's `LOGIN_URL` (so the header's auth links behave for `@login_required` pages). It also resolves the dashboard Withdraw Data-relocation concern.

3. **The logout view (SCB-001) is deliberately scoped to view + URL only, NOT template edits.** Every logout link in the codebase lives *inside* an inline `<header>` that SCB-003 replaces wholesale with the shared header. Updating those templates in SCB-001 would conflict with SCB-003's replacement of the same blocks. The POST+CSRF logout form is therefore part of the shared header component (SCB-003), which is where auth navigation belongs. This satisfies CR4 across all pages without a redundant, conflicting template pass.

4. **GAL-001 (spec 13) depends on SCB-003** solely because both edit `ads/detail.html`. Spec 12 and spec 13 are otherwise independent. Sequencing the two `detail.html` edits (header first, then gallery) avoids a merge conflict and keeps each edit a single reviewable unit.

5. **SCB-004 and SCB-005 are standalone and parallel** — no code dependency, run in Phase 1.

6. **Documentation (Phase 4) is sequenced after each spec's implementation lands** so it documents the actual final behavior. DOC-001 (auth-nav header) and DOC-002 (gallery) both edit `docs/01-spec/ui-patterns.md`; DOC-002 therefore depends on DOC-001 to serialize the edits on that shared file (mirroring the `detail.html` pattern).

7. **Test-authoring (Phase 5) is deferred until its implementations are complete**, orients each suite around the four validation dimensions (user-visible behavior, workflows, regressions, integration boundaries), and runs in parallel because the suites touch distinct test files.

---

## Task Specifications

---

### SCB-001: Implement POST-based `/logout/` view and register URL

<details>
<summary>Task details</summary>

**Priority:** P0
**Type:** implementation
**Depends on:** none
**Risk:** low — additive: creates a new view module and one URL pattern. Scoped to view+URL only; **no template edits** (logout forms are delivered by the shared header SCB-003).

**Affected files:**
- `src/backend/apps/users/views/logout.py` (NEW module)
- `src/backend/apps/users/urls.py`

**Affected targets:**
- New function `logout_view(request)` in `apps/users/views/logout.py`
- `apps/users/urls.py` → `urlpatterns` (register `path("logout/", logout_view, name="logout")`)

**Semantic insertion points:**
- Create new module `apps/users/views/logout.py` (siblings: `consent.py`).
- Add `from apps.users.views.logout import logout_view` and a `path("logout/", logout_view, name="logout")` entry to `apps/users/urls.py::urlpatterns` (which currently holds `consent:<accept|decline|withdraw|login_issue|login_status>`).

**Changes:**

1. New file `apps/users/views/logout.py`:
   ```python
   """POST-only logout view for Mko Bazuna (web sellers)."""

   import logging

   from django.contrib.auth import logout
   from django.http import HttpRequest, HttpResponse
   from django.shortcuts import redirect
   from django.views.decorators.cache import never_cache
   from django.views.decorators.http import require_POST

   logger = logging.getLogger(__name__)


   @require_POST
   @never_cache
   def logout_view(request: HttpRequest) -> HttpResponse:
       """Log out the current user and redirect home.

       POST + CSRF enforced (Django 5.0 removed GET-based logout to prevent
       logout CSRF). ``django.contrib.auth.logout`` flushes the session.
       """
       logout(request)
       logger.info("User logged out via web")
       return redirect("ads:listings")
   ```
   > Redirect target: use `LOGOUT_REDIRECT_URL`-equivalent. `base.py` sets `LOGOUT_REDIRECT_URL = "/"`. Prefer `redirect(settings.LOGOUT_REDIRECT_URL)` or resolve to the listings home — pick one and keep it consistent; the project's home is `ads:listings`.

2. In `apps/users/urls.py`, add the import and pattern so `consent:logout` resolves (it will be referenced by the shared header). No change to `config/urls.py` (it already includes `apps.users.urls` at root).

**Acceptance criteria:**
- `consent:logout` resolves to `/logout/`.
- A GET to `/logout/` returns 405 (POST-only via `@require_POST`).
- A POST to `/logout/` with a valid CSRF token logs the user out (session flushed) and redirects (302) to the configured logout redirect.
- A POST to `/logout/` without a CSRF token is rejected (403) — CSRF middleware already active.
- `uv run ruff check` and `uv run basedpyright` pass on the new/edited files.

</details>

---

### SCB-002: Set `LOGIN_URL` to the Telegram login page

<details>
<summary>Task details</summary>

**Priority:** P0
**Type:** implementation
**Depends on:** none
**Risk:** low — single settings line. Verified: existing redirect test `analytics/tests/test_views.py:131` asserts the `/login/` substring, which both the old (`/accounts/login/`) and new (`/login/issue/`) values contain, so it stays green.

**Affected file:**
- `src/backend/config/settings/base.py`

**Affected targets:**
- The login-redirect settings block containing `LOGIN_REDIRECT_URL = "/"` and `LOGOUT_REDIRECT_URL = "/"`.

**Semantic insertion point:**
- Add `LOGIN_URL = "/login/issue/"` immediately after `LOGOUT_REDIRECT_URL = "/"` in the `# Login redirect` block.

**Changes:**
```python
# Login redirect
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
LOGIN_URL = "/login/issue/"
```

**Acceptance criteria:**
- `@login_required`-protected views (e.g. `ads:dashboard`, `ads:edit`, `consent:withdraw`) redirect anonymous users to `/login/issue/` rather than the non-existent `/accounts/login/`.
- All existing auth-adjacent tests remain green (full `uv run pytest`).

</details>

---

### SCB-003: Extract shared `components/header.html` with auth-aware navigation

<details>
<summary>Task details</summary>

**Priority:** P0
**Type:** implementation (multi-template)
**Depends on:** SCB-001 (header's POST logout form needs the `consent:logout` route), SCB-002 (auth links on `@login_required` pages behave)
**Risk:** medium — touches 7 templates + adds a new component. The header is uniform; page-specific header content must be preserved elsewhere. Verified: no existing test asserts on header markup in the dashboard test suite.

**Affected files:**
- `src/backend/templates/components/header.html` (NEW)
- `src/backend/templates/ads/list.html`
- `src/backend/templates/ads/detail.html`
- `src/backend/templates/ads/dashboard.html`
- `src/backend/templates/ads/edit.html`
- `src/backend/templates/analytics/seller_dashboard.html`
- `src/backend/templates/analytics/moderation_dashboard.html`
- `src/backend/templates/users/login_issue.html`

**Affected targets / semantic insertion points:**
- New component `components/header.html` — the shared top navigation.
- In each of the 6 templates (`list`, `detail`, `dashboard`, `edit`, `seller_dashboard`, `moderation_dashboard`): replace the existing inline `<header class="bg-white shadow-sm border-b">...</header>` block with `{% include "components/header.html" %}`.
- In `login_issue.html`: insert `{% include "components/header.html" %}` after `<body ...>` (there is currently no header).

**Component design (created in `components/header.html`):**
- Site logo link to home (`/<a href="/">Mko Bazuna</a>`) — always.
- `{% include "components/language_switcher.html" %}` — always.
- Conditional nav (top-right):
  - Anonymous (`{% if not request.user.is_authenticated %}`): `<a href="{% url 'consent:login_issue' %}">Login</a>`.
  - Authenticated:
    - `<a href="{% url 'ads:dashboard' %}">Dashboard</a>`
    - `{% if request.user.is_staff %}<a href="/admin/">Admin</a>{% endif %}` (CR7: staff only)
    - Logout as a **POST form** with `{% csrf_token %}` posting to `{% url 'consent:logout' %}` (CR4).

**Critical preservation requirements (do not drop functionality):**
1. **Relocate the "Withdraw Data" form.** `dashboard.html` currently renders a `POST` form to `consent:withdraw` *inside* its inline `<header>` (with `onclick` confirmation). The uniform shared header does not include it. **Move this exact form into the dashboard's `<main>` body** (e.g. near the stats card or at the bottom of the page) so the withdraw-consent capability is preserved. Do not delete it.
2. **Do NOT move the consent banner.** The consent banner (`components/consent_banner.html`) is rendered at the *bottom* of each page behind a guard `{% if not request.user.is_authenticated or not request.user.is_deleted %}`. This guard is per-page and must remain untouched (CR9). The shared header must **not** include the consent banner.
3. **Page-specific breadcrumbs are replaced by existing in-`<main>` headings.** The inline headers of `dashboard.html` ("Dashboard"), `edit.html` ("Edit Ad"), `seller_dashboard.html` (".../Trust") and `moderation_dashboard.html` ("Moderation Analytics") contain page titles. After extraction, each page's existing `<h2>`/heading inside `<main>`, or a small relocated heading, must carry the page title. Do not duplicate the logo/brand.
4. `moderation_dashboard.html`'s manual "Admin" link is redundant once the shared header shows "Admin" for `is_staff` users — remove the manual one with the header.

**Code hint (component skeleton):**
```html
{# Shared auth-aware header. Rendered on all public/seller pages. #}
{% load i18n %}
<header class="bg-white shadow-sm border-b">
    <div class="container mx-auto px-4 py-4 flex items-center justify-between">
        <h1 class="text-2xl font-bold text-gray-800">
            <a href="{% url 'ads:listings' %}">Mko Bazuna</a>
        </h1>
        {% include "components/language_switcher.html" %}
        <nav class="flex gap-4 items-center">
            {% if request.user.is_authenticated %}
                <a href="{% url 'ads:dashboard' %}" class="text-sm text-gray-700 hover:text-blue-600">Dashboard</a>
                {% if request.user.is_staff %}
                    <a href="/admin/" class="text-sm text-gray-700 hover:text-blue-600">Admin</a>
                {% endif %}
                <form method="post" action="{% url 'consent:logout' %}" class="inline">
                    {% csrf_token %}
                    <button type="submit" class="text-sm text-gray-600 hover:text-red-600">Logout</button>
                </form>
            {% else %}
                <a href="{% url 'consent:login_issue' %}" class="text-sm text-gray-700 hover:text-blue-600">Login</a>
            {% endif %}
        </nav>
    </div>
</header>
```

**Acceptance criteria:**
- Anonymous visitors see a "Login" link in the top-right on `list`, `detail`, `dashboard`, `edit`, `seller_dashboard`, `moderation_dashboard`, and `login_issue` pages.
- Authenticated sellers see "Dashboard" and a POST "Logout" button; staff users additionally see "Admin".
- Logout is POST + CSRF; GET logout returns 405 (via SCB-001).
- `login_issue.html` renders the header without breaking its centered login card layout.
- The "Withdraw Data" form remains functional on the seller dashboard (relocated into `<main>`).
- The consent banner still renders behind the same per-page guard on every page (CR9).
- No template raises an `Invalid template library`/undefined-variable error on any of the 7 pages.
- Existing template/view tests stay green (`uv run pytest`).

</details>

---

### SCB-004: Fix documentation discrepancy (`USERNAME_FIELD`)

<details>
<summary>Task details</summary>

**Priority:** P2
**Type:** implementation (documentation only)
**Depends on:** none
**Risk:** trivial — no code. Corrects inaccurate operator docs.

**Affected files:**
- `docs/ops/docker-deployment.md`
- `docs/04-user-stories/admin-stories.md`

**Affected targets / semantic insertion points:**
- `docs/ops/docker-deployment.md` — the "**Important:** The User model uses `telegram_id` as the `USERNAME_FIELD`..." paragraph (currently claims admin login uses `telegram_id`; verified `apps/users/models.py` sets `USERNAME_FIELD = "username"`).
- `docs/04-user-stories/admin-stories.md` — the analogous "**Important:** The User model uses `telegram_id` as the `USERNAME_FIELD`. The Django admin login..." line.

**Changes:**
Rewrite both statements to state that admin login uses the `username` field (set to `"admin"` by the `create_admin_user` command, or `ADMIN_USERNAME`), NOT `telegram_id`; add a note that the admin password comes from the `ADMIN_PASSWORD` env var.

**Acceptance criteria:**
- Both docs state `USERNAME_FIELD = "username"` for admin login.
- Both docs note the password source is `ADMIN_PASSWORD` and username default is `admin`.
- No code or behavior change.

</details>

---

### SCB-005: Consolidate duplicated `staff_required` decorator

<details>
<summary>Task details</summary>

**Priority:** P2 (optional cleanup — spec 12 §3 Task 6)
**Type:** implementation (refactor)
**Depends on:** none
**Risk:** low — removes a local duplicate and reuses the canonical shared decorator. Behavior identical (both raise `Http404` for non-staff).

**Affected files:**
- `src/backend/apps/analytics/views/moderation_dashboard.py`
- `src/backend/apps/moderation/views/decorators.py` (canonical source)

**Affected targets:**
- `analytics/views/moderation_dashboard.py::_staff_required` — delete the local duplicate.
- `analytics/views/moderation_dashboard.py::moderation_analytics` — replace its `@_staff_required` decorator with the canonical `@staff_required`.

**Semantic insertion points:**
- Remove the module-level `_staff_required` function definition.
- Add `from apps.moderation.views.decorators import staff_required`.
- Change the decorator on `moderation_analytics` from `@_staff_required` to `@staff_required`.

**Acceptance criteria:**
- `moderation_analytics` view is decorated with the canonical `staff_required` and still returns `Http404` for non-staff / 200 for staff (verified by `apps/analytics/tests/test_views.py::TestModerationAnalyticsView`).
- Only one `staff_required` definition remains in the codebase.
- `uv run ruff check` and `uv run basedpyright` pass; `uv run pytest apps/analytics/tests/test_views.py -k moderation` passes.

</details>

---

### GAL-001: GLightbox fullscreen gallery on ad detail page

<details>
<summary>Task details</summary>

**Priority:** P0
**Type:** implementation (frontend, single file)
**Depends on:** SCB-003 (both edit `ads/detail.html`; header extraction must land first to avoid a concurrent-edit conflict)
**Risk:** low–medium — client-side only, progressive enhancement (static grid remains without JS). No Django model/view changes. CSP is report-only, so the unpkg CDN load and GLightbox inline styles are not blocked; **no settings change is required**.

**Affected file:**
- `src/backend/templates/ads/detail.html`

**Affected targets / semantic insertion points:**
- `<head>` (after the existing `output.css` link): add GLightbox CSS `<link>`.
- Photo gallery block in `<main>` (currently the `<div class="grid grid-cols-1 ...">` containing bare `<img>` elements): wrap each image in a GLightbox anchor.
- Before `</body>` (after the existing consent-banner include): add the GLightbox JS `<script src=...>` and an inline init `<script>`.

**Changes (mirroring spec 13 Tasks 1–3):**

1. **CDN CSS** in `<head>`:
   ```html
   <link rel="stylesheet" href="https://unpkg.com/glightbox@3.3.1/dist/css/glightbox.min.css">
   ```

2. **Gallery markup** — replace the bare `<img>` loop with GLightbox-anchored links, preserving `AdImage.position` ordering (the existing `{% for image in ad.images.all %}` already iterates in position order):
   ```html
   {% for image in ad.images.all %}
       <a href="{{ image.image_url }}" class="glightbox" data-gallery="ad-gallery"
          data-description="{{ image.alt_text|default:"" }}" aria-label="{% trans "Open image" %} {{ forloop.counter }}">
           <img src="{{ image.thumbnail_large_url|default:image.image_url }}"
                alt="{% trans "Photo" %} {{ forloop.counter }} {% trans "for" %} {{ ad|get_title:LANGUAGE_CODE }}"
                class="w-full {% if ad.images.count == 1 %}max-h-96{% else %}h-64{% endif %} object-cover rounded-lg"
                loading="lazy" width="1280" height="960">
       </a>
   {% endfor %}
   ```
   > Keep the existing grid container and its responsiveness classes intact (progressive enhancement — the static grid must still render without JS).

3. **CDN JS + init** before `</body>`:
   ```html
   <script src="https://unpkg.com/glightbox@3.3.1/dist/js/glightbox.min.js" defer></script>
   <script>
     document.addEventListener('DOMContentLoaded', function () {
       GLightbox({
         selector: '.glightbox',
         touchNavigation: true,
         loop: true,
         zoomable: true,
         closeOnOutsideClick: true,
         navigation: { next: true, prev: true },
       });
     });
   </script>
   ```

**Decision to resolve at implementation (spec §7 Task 3 inconsistency — surfaced explicitly):**
The spec's init snippet uses `counter: { text: '{{counter}} / {{total}}' }`, but `{{counter}}` and `{{total}}` are **not** present in the `ad_detail` view context (the only detail-page context keys are `ad`, `consent_shown`, `bot_username`) and these are not GLightbox placeholder tokens — they would render empty. **Recommendation:** rely on GLightbox's built-in counter (it renders "current / total" automatically from the grouped `.glightbox` elements) and **omit the custom `counter` option**. Do not add a new Django context processor or view changes for it (out of scope: no new models/views/context for the gallery). If a customized counter label is ultimately desired, use GLightbox's documented `%current`/`%total` placeholder **string** (e.g. `counter: { text: '%current / %total' }`) — confirm against the loaded GLightbox v3.3.1 build, never template variables.

**Acceptance criteria (functional FR-01…FR-11 + NFR):**
- Clicking any image opens the GLightbox overlay with the full image (`image.image_url`).
- Overlay shows prev/next arrows, a dark backdrop, and an image counter; clicking backdrop or pressing ESC closes it.
- Arrow keys / ESC / Tab keyboard navigation works; mobile swipe and pinch-zoom work; thumbnail-strip direct jump works (per GLightbox defaults for the grouped selector).
- Images display in `AdImage.position` order.
- With JS disabled, the original static grid still renders (no broken links, no console errors).
- No new Django models/fields/migrations/packages (NFR-01, FR-11).
- No CSP console violations (report-only, unpkg already used for HTMX — confirmed safe).
- Existing ad-detail tests stay green (`uv run pytest apps/ads/tests/ -k detail`).

</details>

---

### DOC-001: Update docs for the shared auth-aware header & seller-cabinet navigation

<details>
<summary>Task details</summary>

**Priority:** P1
**Type:** documentation
**Depends on:** SCB-002, SCB-003 (documents the actual implemented behavior)
**Risk:** low — docs only. Follows `docs/00-overview/doc-maintenance-rules.md` (frontmatter, English-only, relative cross-links, update triggers = new components / auth flow / navigation changes).

**Affected files (verified to exist):**
- `docs/01-spec/ui-patterns.md` — the `## Sticky Navigation Header` section (currently documents the plain logo-only inline header).
- `docs/06-design-system/components.md` — the component catalog (add a Header component).
- `docs/04-user-stories/seller-stories.md` — buyer/seller auth navigation entry points.

**Affected targets / semantic insertion points:**
- `docs/01-spec/ui-patterns.md::## Sticky Navigation Header` — replace the plain-logo `Structure` snippet and `Classes` notes with the extracted shared `components/header.html` component: uniform branding + language switcher + auth-aware nav (`Login` → `components/header.html`; `Dashboard` / `Admin` (staff) / `Logout` POST+CSRF for authenticated users). Update the `Related user stories` note to reference the seller-cabinet stories.
- `docs/06-design-system/components.md` — add a shared **Header** component entry documenting the `{% include "components/header.html" %}` usage, the conditional auth nav, and the POST+CSRF logout form (a verified design-system pattern).
- `docs/04-user-stories/seller-stories.md` — state that a persistent header "Login" button exists on all public pages, and authenticated sellers reach "Dashboard" (cabinet) + POST "Logout" from the header; note logout is POST-only with CSRF (no longer a dead GET link).

**Changes:**
Update the three docs to reflect the post-implementation state. Keep each change minimal, English-only, cross-linked with relative paths, and preserve frontmatter. Do **not** contradict SCB-004 (admin login uses `username`, not `telegram_id`).

**Acceptance criteria:**
- `ui-patterns.md` "Sticky Navigation Header" section documents the shared component and auth-aware nav.
- `components.md` catalog includes the Header component pattern.
- `seller-stories.md` reflects the working header Login/Dashboard/Logout entry points.
- All edited docs are English-only with valid frontmatter and valid relative cross-links.
- No code changes.

</details>

---

### DOC-002: Update docs for the ad-detail GLightbox gallery

<details>
<summary>Task details</summary>

**Priority:** P1
**Type:** documentation
**Depends on:** GAL-001 (documents the implemented gallery), DOC-001 (both edit `docs/01-spec/ui-patterns.md` — serialize to avoid a concurrent-edit conflict)
**Risk:** low — docs only. Follows `docs/00-overview/doc-maintenance-rules.md`.

**Affected files (verified to exist):**
- `docs/01-spec/ui-patterns.md` — the `## Image Gallery for Ad Detail Page` section (currently states "No lightbox/modal in phase 1; static grid display" and shows the bare-`<img>` grid).

**Affected targets / semantic insertion points:**
- `docs/01-spec/ui-patterns.md::## Image Gallery for Ad Detail Page` (`### Implementation`, `### Behavior`) — update to document the GLightbox v3.3.1 fullscreen gallery:
  - CDN CSS (`https://unpkg.com/glightbox@3.3.1/dist/css/glightbox.min.css`) in `<head>`.
  - Gallery markup: each image wrapped in `<a class="glightbox" data-gallery="ad-gallery">` with full image `href` and `thumbnail_large` (or `image`) thumbnail, ordered by `AdImage.position`.
  - Inline init (`GLightbox({ ... })`) after the CDN JS `<script defer>`.
  - **Progressive enhancement** note: static grid remains fully functional without JS.
  - **CSP note:** report-only posture; unpkg is already used for HTMX, no `script-src`/`style-src` settings added.

**Changes:**
Replace the current "no lightbox" Implementation/Behavior content with the implemented gallery pattern, marking the earlier "phase 1 static grid" statement as superseded. Keep English-only, valid frontmatter, relative cross-links; do **not** introduce model/schema doc claims (no `AdImage` changes).

**Acceptance criteria:**
- `ui-patterns.md` "Image Gallery for Ad Detail Page" documents the GLightbox implementation and progressive-enhancement behavior.
- The stale "No lightbox/modal in phase 1" statement is updated/removed.
- English-only, valid frontmatter, valid relative cross-links.

</details>

---

## Test Authoring & Validation Tasks

> Test tasks validate **user-visible behavior**, **end-to-end workflows**, **regressions**, and **integration boundaries**. Each suite is scoped to distinct files so suites run in parallel. Production code is king (if a test conflicts with architecture/business logic, fix the test, not the production code).

---

### TST-SCB-001: Seller-cabinet auth & navigation test suite

<details>
<summary>Task details</summary>

**Priority:** P0
**Type:** test authoring / verification
**Depends on:** SCB-001, SCB-002, SCB-003
**Verifies:** SCB-001 (logout view), SCB-002 (LOGIN_URL), SCB-003 (shared header + withdraw relocation)

**Purpose:** Author tests validating the seller-cabinet authentication flow end-to-end across the four dimensions below.

**Files to create (distinct, parallel-safe):**
- `src/backend/apps/users/tests/test_logout.py` (NEW) — logout view contract.
- `src/backend/apps/ads/tests/test_auth_nav.py` (NEW) — shared header rendering across representative pages.

**Test matrix (organized by validation dimension):**

1. **User-visible behavior** (`test_auth_nav.py`):
   - Anonymous visitor on `GET /` and `GET /ads/<id>/` sees a header `Login` link pointing to `consent:login_issue`.
   - Authenticated non-staff seller sees header `Dashboard` (→ `ads:dashboard`) and a `Logout` button; **no** `Admin` link.
   - Staff seller additionally sees an `Admin` link.
   - The logout control is a `<form>` with `{% csrf_token %}` (assert `csrfmiddlewaretoken` in the rendered page) — i.e. user-facing logout is POST-based.
   - `login_issue.html` still renders (200) with the header present.

2. **Workflows** (`test_logout.py` + `test_auth_nav.py`):
   - Login → dashboard reachable (authenticated session) → POST logout → redirected home → subsequent `/dashboard/` request redirects to `/login/issue/` (anonymous again).
   - Withdraw-Data workflow preserved: authenticated dashboard still renders a POST form to `consent:withdraw` (relocated into `<main>`, not the header).
   - Consent flow: an unacted anonymous/authenticated user still surfaces the consent banner on a header-bearing page (CR9).

3. **Regressions**:
   - GET `/logout/` → 405 (POST-only contract).
   - The pre-existing `/login/` substring redirect assertion in `apps/analytics/tests/test_views.py` remains green after `LOGIN_URL` change.
   - Existing dashboard / trust / consent test suites stay green (no header-markup assertions exist today; guard against new ones).

4. **Integration boundaries**:
   - `@login_required` view (`ads:dashboard`) redirects anonymous user to `/login/issue/?next=...` (not `/accounts/login/`).
   - `consent:logout` reverses to `/logout/`; POST with valid CSRF flushes the session (`assertNotIn('_auth_user_id', client.session)` after logout).
   - POST `/logout/` without CSRF → 403 (CSRF middleware boundary).
   - Staff-only boundary: non-staff authenticated user does not get an `Admin` link; staff does.

**Pass criteria:**
- All test matrix cases pass.
- Full regression: `uv run pytest apps/users apps/ads apps/analytics`.

</details>

---

### TST-GAL-001: Ad-detail gallery test suite

<details>
<summary>Task details</summary>

**Priority:** P0
**Type:** test authoring / verification
**Depends on:** GAL-001
**Verifies:** GAL-001 (GLightbox integration)

**Purpose:** Author tests validating the gallery's wiring, ordering, and no-JS resilience across the four dimensions below.

**Files to touch (distinct, parallel-safe):**
- Extend `src/backend/apps/ads/tests/test_detail_context.py` or add `src/backend/apps/ads/tests/test_gallery_markup.py` (follow the app-level test convention).

**Test matrix (organized by validation dimension):**

1. **User-visible behavior**:
   - `GET /ads/<id>/` (published ad with images) → 200; rendered HTML contains the GLightbox CSS `<link>` and JS `<script>` (unpkg CDN) and the inline `GLightbox({ ... })` init.
   - Each image is rendered as `<a class="glightbox" data-gallery="ad-gallery" href="{{ image.image_url }}">` wrapping an `<img>` with `thumbnail_large_url` (or `image_url`) thumbnail.
   - Counter / prev-next / backdrop / ESC / zoom / swipe behavior is delegated to GLightbox defaults — assert the init options (`touchNavigation`, `loop`, `zoomable`, `closeOnOutsideClick`, `navigation`) are present (config-level contract); manual browser check covers runtime behavior.

2. **Workflows**:
   - The image anchors appear in `AdImage.position` order (compare against `ad.images.order_by('position')`).
   - An ad with a single image still renders a single valid anchor; an ad with no images renders no gallery block (existing branch is preserved).

3. **Regressions**:
   - Existing detail-view and media-security tests stay green (`uv run pytest apps/ads/tests/ -k "detail or media_security"`).
   - No new models/fields/migrations — assert no schema drift (e.g. `manage.py makemigrations --check --dry-run` reports no changes).

4. **Integration boundaries**:
   - **No-JS progressive enhancement:** with scripts considered absent, the static grid `<img>` elements still render with valid `src` (assert markup validity independent of JS).
   - Image URLs point to `media_gate` (`/media/...`) full-image keys and resolve for PUBLISHED ads; no broken links for a published ad with images.

**Manual/browser pass criteria (spec 13 §10 verification plan):**
- Desktop: open modal, verify arrows / ESC / counter / zoom / backdrop-click / thumbnail-strip jump.
- Mobile viewport: verify swipe and pinch-zoom.
- No-JS (disable JS in devtools): static grid visible, no errors.
- Console: no CSP violation errors (report-only; unpkg + GLightbox inline styles should not be enforced).
- Accessibility: keyboard nav (arrows/ESC/Tab) and ARIA present.

**Pass criteria:**
- All automated test-matrix cases pass.
- Browser manual checks pass.

</details>

---

## Execution Order Summary

| Order | Phase | Task ID | Source Spec | Title | Parallel | Priority | Risk | Depends On |
|-------|-------|---------|-------------|-------|----------|----------|------|------------|
| 1 | 1 | SCB-001 | 12 §3 T1 | POST `/logout/` view + URL | yes | P0 | low | — |
| 1 | 1 | SCB-002 | 12 §3 T2 | Set `LOGIN_URL = /login/issue/` | yes | P0 | low | — |
| 1 | 1 | SCB-004 | 12 §3 T5 | Fix `USERNAME_FIELD` docs | yes | P2 | trivial | — |
| 1 | 1 | SCB-005 | 12 §3 T6 | Consolidate `staff_required` (optional) | yes | P2 | low | — |
| 2 | 2 | SCB-003 | 12 §3 T3 | Extract shared auth-aware header | no | P0 | medium | SCB-001, SCB-002 |
| 3 | 3 | GAL-001 | 13 §7 | GLightbox gallery on detail.html | no | P0 | low–med | SCB-003 |
| 4 | 4 | DOC-001 | 12 (docs) | Seller-cabinet / auth-nav docs | no | P1 | low | SCB-002, SCB-003 |
| 4 | 4 | DOC-002 | 13 (docs) | Ad-detail gallery docs | no | P1 | low | GAL-001, DOC-001 |
| 5 | 5 | TST-SCB-001 | 12 (tests) | Seller-cabinet auth & nav test suite | yes | P0 | low | SCB-001, SCB-002, SCB-003 |
| 5 | 5 | TST-GAL-001 | 13 (tests) | Ad-detail gallery test suite | yes | P0 | low | GAL-001 |

> **Parallel groups:** Phase 1 (SCB-001/002/004/005) touches distinct files — fully parallel. Phase 5 (TST-SCB-001/TST-GAL-001) touches distinct test files — fully parallel. Serialized pairs: **SCB-003 → GAL-001** on `ads/detail.html`; **DOC-001 → DOC-002** on `docs/01-spec/ui-patterns.md`.

---

## Risk Assessment

| Task | Risk | Reason | Mitigation |
|------|------|--------|------------|
| SCB-001 | low | Creates a new module + URL pattern; GET returns 405 by design (Django 5.0 removed GET logout) | TST-SCB-001: GET→405, POST→302, no-CSRF→403 |
| SCB-002 | low | Single settings line; old `/accounts/login/` substring test still passes | TST-SCB-001 asserts redirect target |
| SCB-003 | medium | Replaces headers across 7 templates; risk of dropping the dashboard **Withdraw Data** form | Relocate withdraw form into `<main>`; do not move consent banner; TST-SCB-001 asserts preservation |
| SCB-004 | trivial | Docs only | Manual doc review |
| SCB-005 | low | Refactor to canonical decorator; identical behavior | Inline ruff/typecheck + existing analytics tests |
| GAL-001 | low–med | Frontend only; CSP report-only (no enforced policy); GLightbox counter uses undefined template vars in spec | Drop custom `counter` option (use built-in counter); TST-GAL-001 verifies no-JS fallback + markup |
| DOC-001 | low | Docs only; stale "sticky header" content | Update `ui-patterns.md`/`components.md`/`seller-stories.md` to implemented state |
| DOC-002 | low | Docs only; stale "no lightbox" content | Update `ui-patterns.md` gallery section; serialized after DOC-001 |
| TST-SCB-001 | low | Test-only file creation; runs full user/auth suite | pytest on users/ads/analytics |
| TST-GAL-001 | low | Test-only file extension + manual browser checks | pytest detail/media + manual §10 checks |

**No risky tasks** — none modify database schema, migrations, build config, deployment, or startup behavior; no public API is removed/renamed. The only shared-config change (SCB-002) is a single additive settings line. The `staff_required` consolidation (SCB-005) removes a private duplicate and reuses the existing canonical decorator — backward compatible.

---

## Research Status

No additional research is required. Both specifications are decision-complete and cite their own research:

- **Spec 12:** `admin-auth-separation-research.md` (Approach A — password-based admin, chosen) and `seller-dashboard-research.md` (Avito/OLX cabinet scope, Phase 2+ explicitly out of scope). All PO questions (Q1–Q5) resolved.
- **Spec 13:** `lightbox-library-comparison.md` selected GLightbox v3.3.1 (MIT, 0 deps) over PhotoSwipe/baguetteBox/custom; `js-css-pipeline.md` informs the CDN/inline-IIFE approach. All PO decisions (Q1–Q8) resolved.

The only implementation decision surfaced during planning (GLightbox `counter` template-variable mismatch, GAL-001) is a template-context consistency issue, not a library-selection question, and is resolved inline in the task (use the library's built-in counter).

---

## Rollout Notes

1. **Shared-file serialization (two pairs).**
   - `ads/detail.html`: apply **SCB-003** header replacement first, then **GAL-001** gallery changes — never in parallel.
   - `docs/01-spec/ui-patterns.md`: apply **DOC-001** (sticky header section) before **DOC-002** (gallery section) — never in parallel.
   Everything else across the two specs is independent and parallel-safe.

2. **Logout form lives in the shared header, not per-template.** Because every existing logout link is inside an inline `<header>` that SCB-003 replaces, the POST+CSRF logout form is delivered once by `components/header.html`. SCB-001 deliberately avoids template edits to prevent a conflicting pass.

3. **Withdraw Data is preserved via relocation.** The dashboard's withdraw form must move into `<main>` during SCB-003; do not drop it. This is a seller-consent capability (seller-stories.md) and must not regress.

4. **Consent banner stays at the page bottom.** Header extraction must not relocate the consent banner or its per-page guard (`{% if not request.user.is_authenticated or not request.user.is_deleted %}`). CR9 is preserved by leaving each template's existing banner block untouched.

5. **CSP is report-only — no settings change for the gallery.** Verified `apps/core/views.py::csp_report` ("No CSP is enforced at this stage") and no `Content-Security-Policy` header in `base.py`/`prod.py`. unpkg is already used for HTMX (`ads/list.html`). Do not add CSP headers or `unsafe-inline` settings for this work.

6. **Documentation follows the doc-maintenance rules.** Before editing any file under `docs/`, implementors must read `docs/00-overview/doc-maintenance-rules.md` (frontmatter, English-only, relative cross-links, `## Purpose` presence, update triggers).

7. **Test execution order:**
   - After Phase 1: `uv run pytest apps/users apps/analytics/tests/test_views.py`
   - After SCB-003: `uv run pytest apps/users apps/ads apps/analytics` (header regression)
   - After GAL-001: `uv run pytest apps/ads/tests/ -k "detail or media_security"` + manual browser checks (§10)
   - Phase 5: `uv run pytest apps/users/tests/test_logout.py apps/ads/tests/test_auth_nav.py apps/ads/tests/test_detail_context.py` + gallery suite

8. **Rollback:** All changes are additive or backward-compatible. `git checkout` of the individual files suffices. No migrations involved.

---

## Notes

- **Spec 12 §3 T4 (wire cabinet to existing `/dashboard/`) is subsumed by SCB-003 + TST-SCB-001.** The cabinet entry ("Dashboard" link to `ads:dashboard`) is part of the shared header (SCB-003), and reachability of the existing dashboard (list by status, edit/archive/reactivate/delete, analytics trust link) is verified by TST-SCB-001. The existing `/dashboard/` already satisfies the "manage ads from cabinet" requirement (spec 12 A2/F2) — no new dashboard code is needed, matching spec 12 §4.3 scope decision.
- **Spec 13 §7 Tasks 1–3 are collapsed into GAL-001.** They all edit the single `ads/detail.html` file and cannot run in parallel; splitting them adds no dependency isolation or reviewability benefit.
- **Test tasks (TST-SCB-001 / TST-GAL-001) are framed around the four validation dimensions** — user-visible behavior, end-to-end workflows, regressions, integration boundaries — per the planning directive. They author real test files (not just validation scripts) and are deferred to Phase 5 so they assert the final implemented behavior.
- **Documentation tasks (DOC-001 / DOC-002)** satisfy project rule #14 ("Keep documentation updated continuously") and the doc-maintenance update triggers (new component + auth flow + navigation change for DOC-001; new component/pattern for DOC-002). They are deliberately scoped to the verified existing docs (`ui-patterns.md`, `components.md`, `seller-stories.md`).
- **`login_issue.html` (spec 12 T3)** receives the shared header but keeps its centered card layout — verify the header flex layout does not break the `flex items-center justify-center` body.
- **SCB-005 is optional** (spec 12 §3 Task 6). It is included here as the spec requested it; it is low-priority and safe to defer if the team prefers to minimize churn.
