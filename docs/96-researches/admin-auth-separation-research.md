# Research Report: Separating Admin Authentication from User Authentication in Django

**Project:** Mko Bazuna (Django 5.2.16 LTS + PostgreSQL 18 + aiogram 3.x + HTMX MPA + gunicorn sync WSGI)  
**Date:** 2026-08-18  
**Scope:** Modern best practices for separating Django admin auth from end-user (seller) auth; concrete approaches for Mko Bazuna; logout handling; shared header/navigation; codebase gap analysis.  
**Confidence key:** HIGH = verified against installed Django 5.2.16 source + project source; MEDIUM = cross-referenced with Django 5.2 docs, web sources; LOW = inferred/gap.  

---

## TL;DR

Mko Bazuna's two auth mechanisms (Telegram token login for sellers, password login for admins) are already
**partially separated by URL space and decorator** but share the same `User` table, the same session
backend, and the same `AUTHENTICATION_BACKENDS` default. There is **no `LOGOUT_URL` route**, all
templates hardcode a **GET** `<a href="/logout/">`, and `django.contrib.auth.urls` is **not** wired into
`urlpatterns` — so `LogoutView` cannot be dropped in without a template fix. `LOGIN_URL` is also unset
(defaults to `/accounts/login/` which 404s).

**Recommended option:** **Approach A** (keep `/admin/` password-based, add a POST-based `/logout/` view,
extract a shared conditional header, set `LOGIN_URL` to the Telegram login flow). This is the lowest-risk,
highest-leverage change that closes the existing gaps without architectural upheaval or new
dependencies, and aligns with the project's "avoid overengineering" and "follow existing patterns" rules.

## Implementation Status

**Outcome: Implemented (Approach A).** All four gaps from the TL;DR are resolved in
code (verified against the passing test suite — `test_logout.py`,
`test_auth_nav.py`):

- **POST-based `/logout/` view** (`apps/users/views/logout.py`): `@require_POST` +
  `@never_cache`, calls Django `logout()` (flushes session), redirects to `/`.
  Registered as `consent:logout` -> `/logout/` in `apps/users/urls.py`. GET -> 405.
- **`LOGIN_URL = "/login/issue/"`** set in `config/settings/base.py:214`, so every
  `@login_required` view (e.g. `ads:dashboard`, `ads:edit`, `consent:withdraw`)
  redirects anonymous users to the real Telegram login flow instead of the
  non-existent `/accounts/login/`.
- **Shared auth-aware header** `components/header.html` (rendered on
  cabinet/dashboard/login/privacy pages) plus `components/header_catalog.html`
  (catalog/detail/home) which includes `components/header_auth_entry.html`
  (avatar dropdown: Cabinet / My ads / Favorites / Admin(staff) / Settings /
  Logout). Logout is a POST + CSRF form in both variants.

> **Note:** the "Verified Facts", "Open Questions", and "Gaps" sections below
> describe the state at research time (pre-implementation). Gap #1 (no `/logout/`
> route), #2 (`LOGIN_URL` unset), #3 (GET logout links / CSRF), and #4 (no shared
> header) are all **resolved**. See
> `.ai/audit/problems/17_doc-update-discrepancies-plan14-16.md` for deviations.

---

## 1. Verified Facts

### 1.1 Project stack (HIGH — `pyproject.toml:11`, runtime check)

- Django 5.2.16 (`>=5.2.16,<6.0`) — verified via `django.get_version()`.
- Python 3.14, PostgreSQL 18, gunicorn sync WSGI, HTMX MPA (server-rendered), aiogram 3.x.
- Two processes (web + bot) share one Django project + PostgreSQL DB; migrations run once via advisory lock.
- `django-redis` (Redis) for shared cache in production; `LocMemCache` in dev/test.

### 1.2 Current auth state (HIGH — source-verified)

| Aspect | Detail | File |
|---|---|---|
| `AUTH_USER_MODEL` | `"users.User"` (custom `AbstractUser`) | `base.py:192` |
| `USERNAME_FIELD` | `"username"` (CharField, nullable, unique) | `models.py:88` |
| `telegram_id` | `BigIntegerField`, unique, nullable — **NOT** the username field | `models.py:34-39` |
| `AUTHENTICATION_BACKENDS` | **Not set** → defaults to `["django.contrib.auth.backends.ModelBackend"]` | `base.py` (absent) |
| `LOGIN_URL` | **Not set** → Django default `/accounts/login/` — **a URL that does not exist** | `base.py` (absent) |
| `LOGIN_REDIRECT_URL` | `"/"` | `base.py:208` |
| `LOGOUT_REDIRECT_URL` | `"/"` | `base.py:209` |
| `django.contrib.auth.urls` | **NOT** included in `urlpatterns` | `config/urls.py:10-19` |
| Admin login | Standard `/admin/login/` via `AdminAuthenticationForm` (password-based, requires `is_staff`) | `sites.py:414-449` |
| Seller login | Two-phase Telegram token flow: `/login/issue/` → bot deep-link → `/login/status/?token=` → `auth_login()` | `consent.py:161-291` |
| Token storage | Only SHA-256 hash persisted; raw token never stored; 5-min expiry; atomic claim via `UPDATE … RETURNING` | `models.py:119-157`, `login.py:97-130` |
| Admin user creation | `create_admin_user` management command; `telegram_id=-1` placeholder, `is_staff=True`, `is_superuser=True` | `create_admin_user.py:107-116` |
| Staff gate on moderation views | `staff_required` decorator → 404 for non-staff | `decorators.py:17-31` |
| Staff gate on analytics moderation | Separate `_staff_required` decorator (duplicated) | `moderation_dashboard.py:26-34` |

### 1.3 Logout gap (HIGH — verified in Django source + project templates)

Django 5.2 `LogoutView` source (`.venv/Lib/site-packages/django/contrib/auth/views.py:125-169`):

```python
class LogoutView(RedirectURLMixin, TemplateView):
    http_method_names = ["post", "options"]  # <-- NO "get"
    template_name = "registration/logged_out.html"

    @method_decorator(csrf_protect)  # <-- CSRF required on every request
    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        auth_logout(request)  # <-- calls request.session.flush()
        redirect_to = self.get_success_url()
        ...
```

**Key implications (HIGH confidence):**

1. **`LogoutView` does NOT accept GET** — `http_method_names = ["post", "options"]`. A GET
   request returns 405 Method Not Allowed. This was confirmed by Django release notes:
   *"Support for logging out via GET requests in LogoutView and logout_then_login() is removed"*
   (Django 5.0 release notes, confirmed via Context7 docs query).
2. **CSRF is required** — `@method_decorator(csrf_protect)` on `dispatch`. A POST to
   `LogoutView` without a valid CSRF token returns 403.
3. **`logout()` flushes the session** (verified source: `django/contrib/auth/__init__.py`):
   calls `request.session.flush()` which deletes session data and rotates the session key,
   then sets `request.user = AnonymousUser()`. This fully invalidates the old session
   (HIGH confidence).

**Project mismatch:** All three templates that show a "Logout" link use a **GET `<a>` tag**
with a hardcoded URL:

| Template | Line | Code |
|---|---|---|
| `templates/ads/dashboard.html` | 25 | `<a href="/logout/" class="text-sm text-gray-600 hover:text-red-600">Logout</a>` |
| `templates/analytics/seller_dashboard.html` | 30 | `<a href="/logout/" class="text-sm text-gray-600 hover:text-red-600">Logout</a>` |
| `templates/analytics/moderation_dashboard.html` | 28 | `<a href="/logout/" class="text-sm text-gray-600 hover:text-red-600">Logout</a>` |

There is **no `path("logout/", ...)` in `config/urls.py`** or any app `urls.py`
(verified by grep — zero results for `logout` in `.py` files under `src/backend`).
`LOGOUT_REDIRECT_URL = "/"` is set but `django.contrib.auth.urls` is not included, so
the standard `LogoutView` URL name `logout` is unavailable.

**Net effect:** the "Logout" links in all templates are dead — clicking them
produces a 404 (no URL route) even before the GET-vs-POST issue is considered.

### 1.4 `login_required` redirect target gap (MEDIUM — inferred from default + missing URL config)

- `login_required` decorator (used on consent views `consent.py:48,77,108`, dashboard
  `dashboard.py:22`, edit/delete views) redirects unauthenticated users to
  `settings.LOGIN_URL`.
- `LOGIN_URL` is **not** set in `base.py`, so Django uses its default: `/accounts/login/`
  (verified: `django.conf.global_settings.LOGIN_URL = "/accounts/login/"`).
- `django.contrib.auth.urls` is **not** included in `config/urls.py:10-19`, so
  `/accounts/login/` does not resolve → 404 on redirect.
- Test `analytics/tests/test_views.py:127-131` asserts the redirect URL contains `/login/`
  (passes because `/accounts/login/?next=...` contains the substring `/login/`), but
  the target route itself does not exist. This is a **test that validates the symptom
  but not the actual fix**.

### 1.5 Header template architecture (HIGH — verified by source read + existing research)

There is **no `base.html`** in the project (verified by existing research file
`.ai/researches/template_architecture_research.md:22-32` and grep). Every public template
is a standalone `<!DOCTYPE html>` document with an **inline `<header>`** containing only:

```html
<header class="bg-white shadow-sm border-b">
    <div class="container mx-auto px-4 py-4">
        <h1 class="text-2xl font-bold text-gray-800">
            <a href="/">Mko Bazuna</a>
        </h1>
        ...page-specific right-side nav...
    </div>
</header>
```

- 6 of 7 public templates duplicate this header (`list.html`, `detail.html`,
  `dashboard.html`, `edit.html`, `seller_dashboard.html`, `moderation_dashboard.html`).
  `login_issue.html` has no header at all.
- No "Login" link exists for anonymous users on any public (buyer-facing) page.
  The only login entry point is the hardcoded "Login via Telegram" button on `/login/issue/`.
- `bot_username` is passed to **only** `detail.html` (`listings.py:81`) — all other
  templates render it via `settings.BOT_USERNAME`, which the template-test contract
  in `template_architecture_research.md:288` says is forbidden.
- `HtmxMiddleware` from `django_htmx` is **not** in `MIDDLEWARE`
  (`base.py:111-121`); HTMX is loaded per-template via `<script src="https://unpkg.com/htmx.org@1.9.12">`
  in only `list.html`.

### 1.6 Documentation discrepancy (MEDIUM — code contradicts docs)

| Doc | Claim | Actual code |
|---|---|---|
| `docs/ops/docker-deployment.md:624-627` | "The User model uses `telegram_id` as the `USERNAME_FIELD`. The Django admin login form displays 'Telegram ID' as the username field. Enter the `ADMIN_TELEGRAM_ID` value (default: `-1`) as the username." | `models.py:88`: `USERNAME_FIELD = "username"`. `AdminAuthenticationForm` → `AuthenticationForm` → uses `UserModel.USERNAME_FIELD` → the form field is labeled "Username". Admin login requires the `username` field value + password, NOT `telegram_id`. |
| `docs/04-user-stories/admin-stories.md:36-38` | Same claim | Same discrepancy |

The `create_admin_user` command correctly sets `username=username` (`create_admin_user.py:108`)
and `telegram_id=-1`, so admin login is via the `username` field + password — the docs
are wrong. This matters for Approach B (Telegram-based admin login) because if
`telegram_id` is ever made the `USERNAME_FIELD`, admin login UX changes.

---

## 2. Modern Django Patterns for Admin vs. User Auth Separation

### 2.1 What "separation" means in practice

Django has **one session store** (`django_session` table) and **one `User` model**.
There is no built-in per-role session isolation. The standard patterns for
"separating" admin and user auth operate at these layers:

| Layer | Mechanism | What it controls |
|---|---|---|
| **URL space** | `/admin/` vs `/public/` | Routing; the admin site is a separate URL prefix |
| **Auth backend** | `AUTHENTICATION_BACKENDS` list | Which backend resolves a credential |
| **Admin site subclass** | Custom `AdminSite` | Login template, login form, `has_permission()` |
| **View decorators** | `@login_required` vs `@staff_member_required` | Who can reach a view |
| **Session** | Single shared session | Cannot be split without a custom session backend |

### 2.2 Custom AdminSite (HIGH confidence — Django docs via Context7)

Subclassing `AdminSite` lets you control `login_template`, `logout_template`,
`login_form`, and `has_permission()`:

```python
class MyAdminSite(admin.AdminSite):
    site_header = "Mko Bazuna Administration"
    login_template = "admin/custom_login.html"
    logout_template = "admin/custom_logout.html"

    def has_permission(self, request):
        return request.user.is_active and request.user.is_staff
```

Registration via `AdminConfig.default_site` or direct instantiation:
```python
admin_site = MyAdminSite(name="myadmin")
admin_site.register(MyModel)
# urls.py: path("admin/", admin_site.urls)
```

The default `AdminSite.has_permission()` returns
`request.user.is_active and request.user.is_staff` (verified at `sites.py:207`).
The default `AdminAuthenticationForm.confirm_login_allowed()` additionally
**rejects non-staff users** (verified via Context7 docs: `forms.py` AdminAuthenticationForm
raises `ValidationError` if `not user.is_staff`).

**Key constraint:** To use a custom `AdminSite` while keeping all existing
`@admin.register` ModelAdmin classes, you must either (a) use
`SimpleAdminConfig` with `default_site` (disables auto-discovery), or
(b) unregister from the default `admin.site` and re-register with your custom site.
Approach C below handles this.

### 2.3 Multiple AUTHENTICATION_BACKENDS (HIGH confidence — Django docs via Context7)

`AUTHENTICATION_BACKENDS` is an ordered list. Django iterates backends until one
returns a user. The default is `["django.contrib.auth.backends.ModelBackend"]`.

A common pattern for "admin via one backend, users via another" is to write a custom
backend that **only handles one credential type** and have the admin login form
explicitly invoke it. However, in practice, Django's admin login form hardcodes
the use of `AdminAuthenticationForm` + the first backend in `AUTHENTICATION_BACKENDS`.
So a multi-backend setup doesn't automatically create URL-level separation — it
separates *credential resolution*, not *session isolation*.

For Mko Bazuna, the seller login doesn't even use a credential backend — it calls
`django.contrib.auth.login()` directly after verifying the `LoginToken` (bypassing
`authenticate()` entirely). So `AUTHENTICATION_BACKENDS` separation provides
**little value** for the seller flow but would be relevant only if admins
also went through the Telegram flow.

### 2.4 Separate Django projects / sub-applications (LOW confidence — not applicable)

Using a second Django project instance (e.g., `admin_project/` vs `web_project/`)
is overkill for a single-DB, two-process setup. The project doc explicitly states
"Two processes, one DB: web + bot" (`AGENTS.md`, `architecture.md:20`).
A second project would require cross-project migrations and a shared settings
module — violating "avoid overengineering."

### 2.5 Third-party packages (LOW — evaluated, not recommended for this project)

| Package | Fit | Verdict |
|---|---|---|
| `django-allauth` | Social auth / OAuth flows, account management | Overkill — Mko Bazuna's Telegram login is a custom deep-link flow, not OAuth. Adds user sessions, email confirmation, social accounts tables. **Rejected** per "avoid overengineering." |
| `django-guardian` | Per-object permissions | Not needed — access control is role-based (`is_staff`), not object-scoped. |
| `django-axes` | Rate limiting for brute-force protection | The project already has per-IP rate limiting on `/login/issue/`
  (`login_rate_limit.py:19-22`: 10/60s). Admin login brute-force protection would be a separate concern, but nginx already rate-limits `/login/` (`nginx.conf`: 10 req/s burst 20). |
| `django-role-permissions` | Role-based access | Already handled by `is_staff`/`is_superuser` flags + custom decorators. |

**Decision:** No third-party package is needed. Django's built-in
`AdminSite`, `LoginView`/`LogoutView`, and `ModelBackend` cover all requirements
without adding dependencies.

---

## 3. Security Analysis of Each Auth Approach

### 3.1 Password-based admin (`/admin/`, current)

| Pro | Con |
|---|---|
| Standard Django admin; battle-tested; `create_admin_user` command already exists | Admin passwords are the weakest link (phishing, brute force); requires nginx rate-limiting to be safe |
| `AdminAuthenticationForm` already enforces `is_staff` (source: `forms.py`) | Admin user has `telegram_id=-1` placeholder — a documentation mismatch that confuses operators (claims say "enter telegram_id=-1 as username" but actual login uses the `username` field) |
| No session cross-contamination risk with sellers (different credential path) | `ADMIN_PASSWORD` is stored in `.env.docker` — must be strong, rotated periodically |

### 3.2 Telegram-based admin login (Approach B)

| Pro | Con |
|---|---|
| Single auth mechanism for all humans (seller + admin) — simpler UX | **Major**: Admin must have a real `telegram_id` (not `-1`), which means the admin account is tied to a personal Telegram account that could be compromised |
| Eliminates password storage/rotation concerns | `is_staff` flag would need to be set at Telegram-claim time (bot-side) — a new attack surface: if the bot's deep-link parsing is exploitable, an attacker could self-elevate to `is_staff` |
| No credential cross-contamination | The bot processes login for both sellers and admins using the same `LoginToken` table — a bug in one flow affects both |
| Reuses existing two-phase atomic claim (`UPDATE … RETURNING`) | Telegram accounts can be hijacked via SIM swap, device theft, or Telegram-side attacks — **more** attack surface than a password-only admin that lives behind a separate URL |

**Verdict on Telegram admin login:** Adds complexity and attack surface for marginal benefit.
The admin role is a high-privilege, infrequent-use account. Password-based access to
`/admin/` behind nginx TLS + rate limiting is the conventional, lower-risk choice.
US-A1 says "Separate login or Telegram with confirmed role" — the current password
approach satisfies "separate login," and `is_staff` already confirms the role.

### 3.3 Session/credential cross-contamination (HIGH confidence — Django source + model analysis)

Django stores one authenticated user per session: `request.session["_auth_user_id"]`.
`LoginToken.login_status` calls `auth_login(request, user)` (consent.py:285),
and the admin login calls `LoginView.form_valid` → `auth_login` (views.py:108).
Both write to the same session.

**Realistic cross-contamination scenarios:**

1. **Admin logs into `/admin/` via password, then opens `/login/issue/` and claims a
   Telegram token for a seller account.** The second `auth_login()` call replaces
   `_auth_user_id` — the admin session is overwritten by the seller session. The admin
   retains `is_staff` in the DB but the *current session* is now the seller. This is
   expected behavior (single session), but if the admin navigates to `/admin/` they
  'd be redirected to login again. **Not a vulnerability**, just session replacement.

2. **A single user who is both `is_staff=True` AND has a real `telegram_id` (not `-1`)**
   could log in via /admin/login/ as admin, then via /login/issue/ as themselves.
   The latter would set a seller session but the DB record still has `is_staff=True`.
   The `staff_required` decorator at `users/models.py:45` checks
   `request.user.is_staff` — which is `True` — so the "seller" session could access
   moderation views. **This IS a risk**, but the `create_admin_user` command
   deliberately uses `telegram_id=-1` to prevent it (verified at
   `create_admin_user.py:110`). A documentation-driven misconfiguration that sets a
   real `telegram_id` for an admin would reintroduce the risk.

3. **CSRF on logout** (HIGH confidence): The current `<a href="/logout/">Logout</a>`
   GET links are vulnerable to **logout CSRF** — an attacker can embed
   `<img src="/logout/" style="display:none">` on any page the admin visits, and the
   GET request (browser sends cookies automatically) would log them out. Django
   removed GET-based logout in 5.0 specifically to prevent this. Using POST + CSRF
   token fixes this.

### 3.4 Cookie security posture (HIGH — verified in `base.py:65-72`)

```python
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
```

These are already production-grade. `SAMESITE=Lax` mitigates cross-site logout-CSRF
for same-site navigations but not for `<img>`-based attacks on the same site.

---

## 4. Concrete Technical Approaches (Ranked)

### Approach A — Keep `/admin/` password-based; add `/logout/` + shared conditional header + fix `LOGIN_URL`

**Implementation steps:**

1. **Add a POST-based `/logout/` view** (`apps/users/views/logout.py`):
   ```python
   @require_POST
   @never_cache
   def logout_view(request):
       logout(request)
       return redirect("/")
   ```
   - `@require_POST` enforces POST-only (matches Django 5.2 `LogoutView` pattern).
   - CSRF is checked automatically by `CsrfViewMiddleware` (already in `MIDDLEWARE`).
   - Calls Django's `logout()` which does `request.session.flush()`.
   - Redirect to `LOGOUT_REDIRECT_URL` (`"/"`).

2. **Register the URL** in `apps/users/urls.py`:
   ```python
   (path("logout/", logout_view, name="logout"),)
   ```
   - Replaces the dead `<a href="/logout/">` links with a named URL
     `{% url 'consent:logout' %}`.
   - Alternatively, use `LogoutView.as_view(next_page="/")` from
     `django.contrib.auth.views` — but a custom view gives a single redirect
     without the `logged_out.html` template (cleaner for an MPA).

3. **Replace `<a href="/logout/">` with POST forms** in all 3 templates:
   ```html
   <form method="post" action="{% url 'consent:logout' %}">
       {% csrf_token %}
       <button type="submit" class="text-sm text-gray-600 hover:text-red-600">Logout</button>
   </form>
   ```
   - Fixes the GET-vs-POST mismatch AND the CSRF vulnerability simultaneously.
   - Style the `<button>` to look like the existing link.

4. **Extract a shared `components/header.html`** (via `{% include %}`, per
   `template_architecture_research.md:370-376` recommendation):
   ```django
   <header class="bg-white shadow-sm border-b">
       <div class="container mx-auto px-4 py-4 flex justify-between items-center">
           <h1 class="text-2xl font-bold text-gray-800">
               <a href="/">Mko Bazuna</a>
           </h1>
           {% include "components/language_switcher.html" %}
           <nav class="flex gap-2 items-center text-sm">
               {% if user.is_authenticated %}
                   {% if user.is_staff %}
                       <a href="/admin/" class="text-gray-600 hover:text-blue-600">Admin</a>
                   {% endif %}
                   <a href="{% url 'ads:dashboard' %}" class="text-gray-600 hover:text-blue-600">Dashboard</a>
                   <form method="post" action="{% url 'consent:logout' %}" class="inline">
                       {% csrf_token %}
                       <button type="submit" class="text-gray-600 hover:text-red-600">Logout</button>
                   </form>
               {% else %}
                   <a href="{% url 'consent:login_issue' %}" class="text-gray-600 hover:text-blue-600">Login</a>
               {% endif %}
           </nav>
       </div>
   </header>
   ```
   - Conditional rendering: "Login" link for anonymous, "Dashboard / Logout" for
     authenticated, "Admin" link only for staff.
   - Each public template replaces its inline header with `{% include "components/header.html" %}`.

5. **Set `LOGIN_URL`** in `base.py`:
   ```python
   LOGIN_URL = "/login/issue/"
   ```
   - `@login_required` now redirects to the actual Telegram login page instead of
     the non-existent `/accounts/login/`.

6. **Consolidate the duplicated `_staff_required` decorator** in
   `analytics/views/moderation_dashboard.py:26-34` → use the shared
   `apps/moderation/views/decorators.py:staff_required` instead. (Optional cleanup;
   currently `staff_required` returns 404 while the analytics one also returns 404 —
   they should be unified.)

**Pros:**
- Minimal new code — reuses existing `logout()`, `auth_login()`, URL patterns.
- Fixes 3 concrete gaps (dead logout link, missing LOGIN_URL, no shared header).
- No new dependencies, no model changes, no migration.
- Aligns with "follow existing patterns" (already uses `{% include %}` for components).
- Low risk to existing tests (no `base.html`/`{% extends %}` migration that would
  break line-relative template tests in `test_templates.py`).
- CSRF-safe logout (POST + token) closes the logout-CSRF vector.

**Cons:**
- Admin still uses password auth (operators must manage `ADMIN_PASSWORD`).
- Does not address the documentation discrepancy about `USERNAME_FIELD`.

**Security implications:**
- Logout CSRF is eliminated (POST + CSRF token).
- `LOGIN_URL` fix ensures `@login_required` redirects to a real, safe page.
- Session is properly flushed on logout (`request.session.flush()`).
- Admin and seller sessions are still in the same `django_session` table, but since
  they use different credential paths (password vs. token) and admin users have
  `telegram_id=-1`, practical cross-contamination requires deliberate misconfiguration.

**Effort estimate: LOW.** ~2–3 hours for implementation + 1 hour for tests + 30 min
to update 3 templates. No migrations, no new dependencies.

---

### Approach B — Unified Telegram login for both admins and sellers (admin = `is_staff` flag)

**Implementation steps:**

1. **Change `create_admin_user`** to use a real `telegram_id` (the owner's Telegram ID)
   instead of `-1`, set `is_staff=True`, and set a **null password**.
2. **Modify `login_status`** (consent.py:268) to also handle the case where the
   claimed `telegram_id` belongs to an `is_staff` user — redirect to `/admin/`
   instead of the seller dashboard.
3. **Custom admin login page** that bypasses `AdminAuthenticationForm` and instead
   redirects to `/login/issue/` (the Telegram deep-link page).
4. **Modify all staff checks** (`staff_required`, `has_permission`) to also verify
   `telegram_id is not None and telegram_id != -1` to prevent a `-1` placeholder
   from passing.
5. **Update documentation** to remove the `USERNAME_FIELD = telegram_id` claim.

**Pros:**
- Single auth mechanism — no password management.
- Consistent UX for admin and seller.

**Cons:**
- **High complexity**: requires changes to 5 different subsystems (admin login
  template, login_status view, staff checks, admin user creation, model logic).
- **Increases attack surface**: the bot's login handler now processes
  admin-level logins; a bug in token claiming could grant admin access.
- **Admin sessions become tied to Telegram account security** (SIM swap, device
  theft, account takeover). Password-based admin auth is the industry standard
  for a reason — it's a separate factor the admin controls independently.
- **Breaks convention**: Django admin is designed for password login. Deviating
  requires overriding `AdminSite.login()`, `AdminAuthenticationForm`, and
  `has_permission()` — non-trivial and easy to get wrong.
- Requires **model + migration changes** (null password on admin user, telegram_id
  validation in staff checks) — adds risk in a project that runs migrations once
  before both processes start.
- The `telegram_id=-1` placeholder convention is used throughout the codebase
  (`create_admin_user.py`, `docker-deployment.md`); changing it ripples across
  docs and CLI tooling.

**Security implications:**
- Admin privileges would flow through the same `LoginToken` table as seller
  logins — if the token claim logic has a TOCTOU bug (it's carefully designed
   with `UPDATE…RETURNING` per the codebase, but the web-side `login_status`
  uses a separate `UPDATE` that could race), both roles are at risk.
- Telegram is a consumer app with weaker account-security guarantees than a
  password vault. An admin's Telegram account being compromised = full site
  admin access.
- No separate credential for the high-privilege admin role violates the
  principle of credential separation.

**Effort estimate: HIGH.** ~8–12 hours, requires migration, admin template
overrides, and careful audit of the login_status race conditions.

---

### Approach C — Custom `AdminSite` subclass with separate login form + seller Telegram login + separate auth backend

**Implementation steps:**

1. **Create `apps/users/admin_sites.py`** (or `config/admin_site.py`):
   ```python
   from django.contrib import admin


   class MkoBazunaAdminSite(admin.AdminSite):
       site_header = "Mko Bazuna Administration"
       site_title = "Mko Bazuna Admin"
       login_template = "admin/login.html"  # or a custom template
       logout_template = "admin/logout.html"

       def has_permission(self, request):
           return request.user.is_active and request.user.is_staff
   ```

2. **Create `SimpleAdminConfig`** to set `default_site` so `@admin.register`
   decorators attach to the custom site instead of the default `admin.site`.

3. **Unregister all ModelAdmin classes** from the default `admin.site` and
   re-register with `MkoBazunaAdminSite`. (All `@admin.register` decorators
   across `apps/*/admin.py` files would need to use
   `MkoBazunaAdminSite.register` instead.)

4. **Optionally add a custom `AUTHENTICATION_BACKENDS`** with a backend that
   only handles `is_staff` users, leaving `ModelBackend` for everyone else.

5. **Add a custom admin login form** that presents a "Login via Telegram" button
   alongside the password form (hybrid approach).

**Pros:**
- Cleanest architectural separation at the Django level.
- Full control over admin login template, index page, and permissions.
- Industry-standard pattern for complex admin portals.

**Cons:**
- **Massive refactoring**: every `@admin.register` call in the codebase would
  need to be changed (grep found registrations in `users/admin.py`,
  `ads/admin.py`, `categories/admin.py`, `locations/admin.py`, `moderation/admin.py`,
  `analytics/admin.py` — at minimum 6 files).
- Requires `SimpleAdminConfig` + `default_site` wiring, which changes how
  `django.contrib.admin` discovers ModelAdmins system-wide.
- The project has **no custom admin index** — the moderation queue and analytics
  dashboards are already separate custom views, not admin pages. So the custom
  AdminSite buys little.
- The `staff_required` decorators on `moderation/` and `analytics/` views already
  provide the same access control that `AdminSite.has_permission()` would.
- Over-engineered relative to the actual gap (which is a missing logout view + missing
  `LOGIN_URL` + no shared header).

**Security implications:**
- No meaningful security improvement over Approach A — the actual access control
   (is `is_staff`) is unchanged.
- A custom admin site introduces new code paths that could have permission bugs
  (e.g., `has_permission` returning True when it shouldn't).

**Effort estimate: HIGH.** ~12–20 hours of refactoring across 6+ admin.py files,
risk of breaking admin registration, and no clear security or UX gain over
Approach A.

---

## 5. Recommended Option: Approach A

### Rationale (ranked)

1. **Closes real, verified gaps immediately.** The codebase has a dead `/logout/`
   route, a `LOGIN_URL` that 404s, and no shared header with auth-aware nav.
   These are not hypothetical — templates hardcode `<a href="/logout/">Logout</a>`
   (3 templates) and `@login_required` redirects to a non-existent URL.

2. **Low risk, no migration.** Approach B and C both require model/migration
   changes or a 6-file admin refactor. The project's migration workflow is
   complex (ad advisory-lock `migrate` service, threshold-based consolidation,
   `CONNN_MAX_AGE=0` for PgBouncer) — adding auth-related migrations is
   unnecessary when the gaps are in routing and templates.

3. **Aligns with project rules.** "Avoid overengineering" and "follow existing
   patterns" (`AGENTS.md` rules 5, 7). The project already uses `{% include %}`
   for components (`consent_banner.html`, `language_switcher.html`), and
   `logout()` from `django.contrib.auth` is the standard. The existing research
   file `template_architecture_research.md` independently recommends Approach A
   (extract `components/header.html` via `{% include %}`).

4. **Security parity.** The admin password login + `is_staff` gate is the
   conventional, well-understood pattern. The `AdminAuthenticationForm`
   already enforces `is_staff` (verifiable in Django source). Approach B's
   Telegram-based admin login adds attack surface without meaningful benefit
   for a single-moderator launch market.

5. **CSRF-safe.** The POST-based logout form with `{% csrf_token %}` eliminates
   the logout-CSRF vector inherent in the current GET `<a>` links. Django's
   own removal of GET-based logout in 5.0 (`docs/releases/5.0.txt`) validates
   this design choice.

### Detailed implementation for the recommended option

**Step 1 — Logout view** (`apps/users/views/logout.py`):

```python
"""Logout view for Mko Bazuna sellers."""

import logging
from django.contrib.auth import logout as auth_logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache

logger = logging.getLogger(__name__)


@never_cache
@require_POST
def logout_view(request: HttpRequest) -> HttpResponse:
    """Log the user out by flushing the session and redirecting home."""
    user_id = getattr(request.user, "id", None)
    auth_logout(request)
    logger.info(f"User {user_id} logged out")
    return redirect("/")
```

Why this instead of `LogoutView.as_view()`:
- `LogoutView` is designed for a class-based view + template pipeline
  (`registration/logged_out.html`). A 15-line function-based view matches the
  project's FBV style (`consent.py`, `listings.py`, `queue.py`) and avoids the
  template-rendering step.
- `logout()` (Django's function) calls `request.session.flush()`, which deletes
  all session data and rotates the session key — full invalidation (verified
  in source).
- `@require_POST` enforces POST-only (matching `LogoutView.http_method_names`).
- `@never_cache` prevents caching of the redirect response.
- CSRF is handled by `CsrfViewMiddleware` (already in `base.py:116`).

**Step 2 — URL registration** (`apps/users/urls.py`):

```python
from apps.users.views.consent import (
    consent_accept,
    consent_decline,
    login_issue,
    login_status,
    consent_withdraw,
)
from apps.users.views.logout import logout_view
from django.urls import path

urlpatterns = [
    path("logout/", logout_view, name="logout"),
    path("consent/accept/", consent_accept, name="accept"),
    ...,
]
```

**Step 3 — `LOGIN_URL` fix** (`config/settings/base.py`, add line after 209):

```python
LOGIN_URL = "/login/issue/"
```

This makes `@login_required` redirect to the Telegram login page rather than
the non-existent `/accounts/login/`.

**Step 4 — Template fixes** (3 files):

In each of `ads/dashboard.html`, `analytics/seller_dashboard.html`,
`analytics/moderation_dashboard.html`, replace:

```django
<a href="/logout/" class="text-sm text-gray-600 hover:text-red-600">Logout</a>
```

with:

```django
<form method="post" action="{% url 'consent:logout' %}" class="inline">
    {% csrf_token %}
    <button type="submit"
            class="text-sm text-gray-600 hover:text-red-600">
        Logout
    </button>
</form>
```

**Step 5 — Shared header** (`templates/components/header.html`):

```django
{% load i18n %}
<header class="bg-white shadow-sm border-b">
    <div class="container mx-auto px-4 py-4 flex justify-between items-center">
        <h1 class="text-2xl font-bold text-gray-800">
            <a href="/">Mko Bazuna</a>
        </h1>
        {% include "components/language_switcher.html" %}
        <nav class="flex gap-3 items-center text-sm">
            {% if user.is_authenticated %}
                {% if user.is_staff %}
                    <a href="/admin/" class="text-gray-600 hover:text-blue-600">Admin</a>
                {% endif %}
                <a href="{% url 'ads:dashboard' %}" class="text-gray-600 hover:text-blue-600">Dashboard</a>
                <form method="post" action="{% url 'consent:logout' %}" class="inline">
                    {% csrf_token %}
                    <button type="submit" class="text-gray-600 hover:text-red-600">Logout</button>
                </form>
            {% else %}
                <a href="{% url 'consent:login_issue' %}" class="text-gray-600 hover:text-blue-600">Login</a>
            {% endif %}
        </nav>
    </div>
</header>
```

Each public template replaces its inline `<header>...</header>` block with:

```django
{% include "components/header.html" %}
```

**Security considerations for the recommended option:**

| Threat | Mitigation | Status |
|---|---|---|
| Logout CSRF (GET-based) | POST + CSRF token (`csrf_protect` middleware) | ✅ Fixed |
| Session fixation | `login_status` calls `auth_login()` which cycles session key for anonymous→authenticated | ✅ Already in place (consent.py:283-285 comment) |
| Session not invalidated on logout | `auth_logout()` → `request.session.flush()` | ✅ Verified in Django source |
| Open redirect on logout | `redirect("/")` — hardcoded, no user input | ✅ Safe |
| Admin login brute force | Already rate-limited by nginx (`/login/`: 10 req/s burst 20) | ✅ Already in place |
| Seller login token brute force | SHA-256 hash stored, 5-min expiry, rate-limited 10/60s per IP | ✅ Already in place (login_rate_limit.py) |
| Admin/seller session cross-contamination | Admin uses password, sellers use Telegram token; admin `telegram_id=-1` | ✅ Mitigated by design |

**Effort estimate: LOW.** 2–3 hours implementation + 1 hour tests + 30 min docs.

---

## 6. Gaps in the Current Codebase (Needs Addressing)

| # | Gap | Severity | Verified at |
|---|---|---|---|
| 1 | **No `/logout/` URL route or view** — templates hardcode `<a href="/logout/">` (3 templates) which 404s | HIGH (broken UX + CSRF risk) | `config/urls.py:10-19` (no logout route); `dashboard.html:25`, `seller_dashboard.html:30`, `moderation_dashboard.html:28` |
| 2 | **`LOGIN_URL` unset** — defaults to `/accounts/login/` which does not exist (no `django.contrib.auth.urls` included); `@login_required` redirects to 404 | HIGH (broken auth redirect) | `base.py:208-209` (LOGIN_REDIRECT set, LOGIN_URL absent); `config/urls.py` (no auth.urls include) |
| 3 | **GET-based logout links** — vulnerable to logout-CSRF via `<img src="/logout/">` | HIGH (security) | All 3 templates use `<a href="/logout/">Logout</a>` (GET) |
| 4 | **No shared header / base template** — 6 templates duplicate the `<header>` markup; no "Login" link for anonymous users on buyer-facing pages | MEDIUM (UX + DRY) | `template_architecture_research.md:22-32`, grep confirms no `base.html` |
| 5 | **Duplicated `staff_required` decorator** — two implementations: `apps/moderation/views/decorators.py:17` and `apps/analytics/views/moderation_dashboard.py:26` | LOW (code hygiene) | both files |
| 6 | **Documentation claims `telegram_id` is `USERNAME_FIELD`** — contradicts `models.py:88` where `USERNAME_FIELD = "username"` | LOW (operator confusion) | `docker-deployment.md:624-627`, `admin-stories.md:36-38` vs `models.py:88` |
| 7 | **`login_required` redirect test is a false positive** — `test_views.py:127-131` asserts `/login/` substring, passes with the non-existent `/accounts/login/` | LOW (test quality) | `analytics/tests/test_views.py:127-131` |
| 8 | **Admin login form field label** — docs say "Telegram ID" but actual form shows "Username" (because `USERNAME_FIELD = "username"`) | LOW (operator confusion) | Same as #6 |

---

## 7. Codebase Patterns Supporting/Conflicting with Each Approach

### Supporting Approach A

- **`@login_required`** already used on consent, dashboard, edit views
  (`consent.py:48,77,108`, `dashboard.py:22`, `edit.py:41,158,188`) — just needs
  `LOGIN_URL` to point somewhere real.
- **`{% include %}` pattern** already established for `consent_banner.html`,
  `language_switcher.html`, `ad_list.html` — extending to `header.html` is
  consistent.
- **`staff_required` decorator** already gates moderation views with 404
  (`decorators.py:17-31`) — admin/seller separation at the view layer is
  already working.
- **`AdminAuthenticationForm`** (Django default) already enforces
  `is_staff` — no custom admin site needed.
- **`LOGIN_REDIRECT_URL = "/"`** and **`LOGOUT_REDIRECT_URL = "/"`** already
  set — the proposed logout view just uses `redirect("/")`.

### Conflicting with Approach A (minor)

- Templates use GET `<a>` for logout — needs to be changed to POST form
  (Step 4 above).
- No `base.html` / `{% extends %}` — the recommendation is `{% include %}`,
  which is the project's existing pattern, so this is actually a **mild conflict**
  that resolves cleanly by following the include pattern.

### Supporting Approach B

- The `LoginToken` model and bot-side claim logic already exist and work
  atomically (`_claim_login_token`, `login.py:97-130`).
- The bot handler `handle_login_deep_link` (login.py:32-90) already creates
  users via `get_or_create` by `chat_id`.

### Conflicting with Approach B

- `create_admin_user` deliberately sets `telegram_id=-1`
  (`create_admin_user.py:44,109`) — the entire deployment workflow
  (`docker-deployment.md:620-627`, `admin-stories.md:36-38`) is built around
  password-based admin login. Changing this ripples across docs, CLI,
  and the advisory-lock `create_admin` one-shot service
  (`architecture-structure.md:152`).
- The `USERNAME_FIELD = "username"` means admin login via Telegram would
  require either changing `USERNAME_FIELD` (major model change + migration)
  or adding a separate admin-only login path — neither is simple.
- No migration currently exists for changing the admin auth model — any
  model change triggers the advisory-locked migration workflow.

### Supporting Approach C

- Django 5.2 fully supports `AdminSite` subclassing and `SimpleAdminConfig`
  with `default_site` (verified via Context7 docs + source: `sites.py:30-211`).
- `AdminSite.has_permission()` defaults to `is_active and is_staff`
  (verified: `sites.py:207`), which matches the project's `staff_required`
  decorator — so a custom `has_permission` would be redundant.

### Conflicting with Approach C

- **6+ `admin.py` files** use `@admin.register(...)` which registers with the
  default `admin.site`. A custom AdminSite requires unregistering and
  re-registering all of them — `users/admin.py`, `ads/admin.py`,
  `categories/admin.py`, `locations/admin.py`, `moderation/admin.py`,
  `analytics/admin.py`.
- The project's moderation UI (`/moderation/queue/`, `/moderation/review/`)
  is **already a custom, non-admin views** outside `/admin/` — a custom
  AdminSite provides no benefit for these.
- "Avoid overengineering" rule (`AGENTS.md` rule 5) — this is the largest
  refactor with the least incremental security gain.

---

## 8. Summary & Ranking

| Rank | Approach | Effort | Risk | Security gain | Recommendation |
|---|---|---|---|---|---|
| **1** | **A: Keep `/admin/` password-based + add `/logout/` + shared header + `LOGIN_URL`** | LOW (2–4h) | LOW | HIGH (fixes CSRF + dead route + broken redirect) | **Recommended** |
| 2 | B: Unified Telegram login for admin + seller | HIGH (8–12h) | HIGH (migration + bot-side admin auth) | LOW–MED (adds attack surface) | Only if password management becomes an operational burden |
| 3 | C: Custom AdminSite + separate backend | HIGH (12–20h) | MED (6-file admin refactor) | LOW (access control unchanged) | Over-engineered; skip |

---

## 9. Sources

### Django 5.2.16 source (verified in `.venv`)
- `django/contrib/auth/views.py:125-169` — `LogoutView` source (`http_method_names`, `csrf_protect`, `flush()` via `logout()`)
- `django/contrib/auth/__init__.py` — `logout()` function (`request.session.flush()`, `request.user = AnonymousUser()`)
- `django/contrib/admin/sites.py:202-207` — `AdminSite.has_permission()` returns `is_active and is_staff`
- `django/contrib/admin/sites.py:414-449` — `AdminSite.login()` uses `AdminAuthenticationForm`
- `django/contrib/admin/forms.py` — `AdminAuthenticationForm.confirm_login_allowed()` enforces `is_staff`
- `django/conf/global_settings.py` — default `LOGIN_URL = "/accounts/login/"`

### Django 5.2 documentation (via Context7 /docs.djangoproject.com)
- "Customizing the AdminSite class" — `default_site = "myproject.admin.MyAdminSite"`, `login_template`, `logout_template`, `index_template` attributes
- "AdminSite.has_permission(request)" — `is_active and is_staff` requirement
- "Root and login templates" — recommended to subclass AdminSite for template overrides
- "LogoutView" — POST-only, `csrf_protect`, `next_page` defaults to `LOGOUT_REDIRECT_URL`
- "Django 5.0 release notes" — GET-based logout removed
- "Authentication backends" — `AUTHENTICATION_BACKENDS` ordering, `BaseBackend` pattern, admin coupling to `is_staff`/`is_superuser`

### Web sources (HIGH confidence cross-reference)
- [Django docs — Authentication & Authorization](https://docs.djangoproject.com/en/6.0/topics/auth/default/)
- [Django docs — Customizing authentication](https://docs.djangoproject.com/en/6.0/topics/auth/customizing)
- [Django docs — CSRF](https://docs.djangoproject.com/en/6.0/ref/csrf)
- Stack Overflow: "Django LogoutView is not working" (2024-01) — confirms
  GET logout removed in Django 5.0; POST + CSRF required
- AnomixLabs: "Django 5.2 Project Setup 2026 Best Practices" — LoginRequiredMiddleware, custom user model

### Mko Bazuna project source (HIGH confidence — direct file reads)
- `src/backend/config/settings/base.py:65-72,192,208-209` — settings, session cookie flags, AUTH_USER_MODEL
- `src/backend/config/urls.py:10-19` — no `auth.urls` include, no logout route
- `src/backend/apps/users/models.py:24-46,88,119-157` — User model, USERNAME_FIELD, LoginToken
- `src/backend/apps/users/views/consent.py:285` — `auth_login(request, user)` in login_status
- `src/backend/apps/users/views/logout.py` — **does not exist** (gap)
- `src/backend/apps/users/services/login_rate_limit.py:19-22` — 10 req/60s rate limit
- `src/backend/apps/moderation/views/decorators.py:17-31` — `staff_required` (404)
- `src/backend/apps/analytics/views/moderation_dashboard.py:26-34` — duplicated `_staff_required`
- `src/backend/apps/moderation/views/queue.py:19` — `@staff_required` on moderation_queue
- `src/backend/apps/moderation/views/review.py:19,48,69,107` — `@staff_required` on all review views
- `src/backend/apps/core/management/commands/create_admin_user.py:44,109,110` — `telegram_id=-1` placeholder
- `src/backend/apps/ads/views/dashboard.py:22` — `@login_required` on dashboard
- `src/backend/apps/ads/views/edit.py:41,158,188` — `@login_required` on edit views
- `src/backend/templates/ads/dashboard.html:25` — `<a href="/logout/">Logout</a>` (GET, dead link)
- `src/backend/templates/analytics/seller_dashboard.html:30` — same dead link
- `src/backend/templates/analytics/moderation_dashboard.html:28` — same dead link
- `src/backend/templates/ads/list.html:18-25,56` — header + consent banner guard pattern
- `src/backend/templates/ads/detail.html:20-27,106` — header + consent banner guard
- `src/backend/templates/ads/edit.html:16-26` — header
- `src/backend/telegram_bot/handlers/login.py:26,32,97-130` — bot login handler + atomic claim
- `docs/01-spec/technical-specification.md:113-119` — decision H (Telegram login)
- `docs/04-user-stories/admin-stories.md:50-51,36-38` — US-A1 admin auth
- `docs/02-database/db-schema.md:54-57,75-87` — users table, login_tokens schema
- `docs/04-user-stories/seller-stories.md:22-27` — US-S1 login
- `docs/99-agent/architecture.md:20-22` — two-process architecture
- `docs/ops/docker-deployment.md:609-627` — admin user setup (contains doc discrepancy)
- `.ai/researches/template_architecture_research.md` — existing research on header/templates (HIGH confidence)
- `.ai/researches/security-config-hardening-research.md` — existing research on settings/CSRF

### Internal documentation discrepancy (MEDIUM confidence)
- `docs/ops/docker-deployment.md:624-627` and `docs/04-user-stories/admin-stories.md:36-38`
  claim `telegram_id` is `USERNAME_FIELD` and the admin login form shows "Telegram ID".
  The actual model code (`models.py:88`) sets `USERNAME_FIELD = "username"`.
  This should be corrected as a follow-up documentation task.
