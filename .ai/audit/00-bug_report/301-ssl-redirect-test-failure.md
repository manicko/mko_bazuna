# Bug Report: All HTTP Integration Tests Return 301 Instead of 200 Against PostgreSQL

## Date: 2026-08-08T23:29:56+02:00
## Severity: Critical
## Status: Open
## Reporter: Agent (investigation complete, no code changes made)

---

## Summary

Every `django.test.TestCase` integration test that issues an HTTP request via the Django test client and asserts `response.status_code == 200` fails with `AssertionError: 301 != 200`. This affects **all** DB-backed view tests, not just the newly added language-localization suite. The single test file currently in scope (`test_language_end_to_end.py`) is blocked, and the broader suite cannot be validated against PostgreSQL until this is resolved.

## Symptom

```
AssertionError: 301 != 200
```

The redirect response body/location is an HTTPS URL (e.g. `https://testserver/...`).

## Reproduction

1. Start a local PostgreSQL 18 container:
   ```
   docker run --rm -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:18-alpine
   ```
2. Provide a working Postgres `DATABASE_URL` (host `db` is NOT resolvable locally — `conftest.py` defaults to `127.0.0.1`):
   ```powershell
   $env:DATABASE_URL = "postgres://postgres:postgres@127.0.0.1:5432/mko_bazuna"
   ```
3. Run any DB-backed view test:
   ```powershell
   uv run pytest "src/backend/apps/analytics/tests/test_views.py::TestSellerTrustDashboardView::test_authenticated_user_gets_200" -x -q
   ```

### Observed failure

```
E       AssertionError: 301 != 200
src\backend\apps\analytics\tests\test_views.py:137: AssertionError
```

> Note: the `staticfiles` directory warning (`RuntimeWarning: No directory at: C:\py_dev\mko_bazuna\staticfiles\`) is **separate and non-fatal** — see Appendix B.

---

## Scope of Impact (Confirmed Failing Tests)

The following existing test classes all use `self.client.get(...)` and assert 200; they are **verified to fail identically** against real Postgres:

| File | Class | Sample passing-expected case (now 301) |
|------|-------|----------------------------------------|
| `apps/analytics/tests/test_views.py` | `TestSellerTrustDashboardView` | `test_authenticated_user_gets_200` |
| `apps/analytics/tests/test_views.py` | `TestModerationAnalyticsView` | `test_staff_user_gets_200` |
| `apps/ads/tests/test_dashboard_stats.py` | (class) | line 180 `== 200` |
| `apps/moderation/tests/test_priority_service.py` | (6 cases) | lines 349/442/469/491/508/525 `== 200` |
| `apps/core/tests/test_language_end_to_end.py` | (all composition cases) | lines 92/102/108/117/129/141/150/166 `== 200` |

The unit test `test_language_middleware.py` and the model/service tests
(`test_trust_analytics.py`, etc.) **pass** — they never hit the SSL-redirect path
because they don't issue HTTP requests through the full middleware stack.

---

## Root Cause

`SecurityMiddleware` (in `MIDDLEWARE`, see `config/settings/base.py:108`) redirects
non-secure HTTP requests to HTTPS at `process_request`:

```python
# django/middleware/security.py (Django 5.2)
class SecurityMiddleware(MiddlewareMixin):
    def __init__(self, get_response):
        ...
        self.redirect = settings.SECURE_SSL_REDIRECT          # True in base.py
        self.redirect_host = settings.SECURE_SSL_HOST          # None
        ...

    def process_request(self, request):
        path = request.path.lstrip("/")
        if (
            self.redirect
            and not request.is_secure()
            and not any(pattern.search(path) for pattern in self.redirect_exempt)
        ):
            host = self.redirect_host or request.get_host()
            return HttpResponsePermanentRedirect(             # <-- 301
                "https://%s%s" % (host, request.get_full_path())
            )
```

The chain for the failure is:

1. `config/settings/base.py:67` sets `SECURE_SSL_REDIRECT = True`.
2. `config/settings/test.py` imports base via `from .base import *` (line 7) and
   overrides **only** `DEBUG`, `DATABASES`, and `PASSWORD_HASHERS` — it does
   **not** disable `SECURE_SSL_REDIRECT`.
3. The Django test client (`django.test.Client`) issues requests over **HTTP**,
   not HTTPS. `request.is_secure()` therefore returns `False` **unless** the
   `X-Forwarded-Proto` header says `https`.
4. `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` (base.py:68)
   means `is_secure()` inspects `request.META["HTTP_X_FORWARDED_PROTO"]`.
   The test client does **not** set that header to `https`, so
   `is_secure() == False`.
5. → `SecurityMiddleware.process_request` returns a `301` permanent redirect to
   `https://testserver/...`, and the view is never reached.

### Why this was hidden until now

- `config/settings/dev.py` sets `SECURE_SSL_REDIRECT = False` (line 11), so
  local developer runs against Postgres *with dev settings* would NOT 301.
- `config/settings/test.py` was expected to be used by CI, but CI runs under
  **SQLite** (see Appendix A): under SQLite pytest-django cannot build the
  Postgres `test_*` DB, so view tests either skipped the DB or never reached
  the SSL-redirect code path with a real connection. The 301 only becomes
  reachable once the DB path is valid Postgres **and** the test settings are
  loaded (which base.py forces `SECURE_SSL_REDIRECT = True`).
- Net effect: the existing DB-backed view suites were never successfully
  exercised against Postgres, so the redirect bug went undetected.

### Ruling out other hypotheses (verified during investigation)

| # | Hypothesis | Test / Evidence | Verdict |
|---|------------|-----------------|---------|
| 1 | URL/view config wrong on `/<int:pk>/` | `/<pk>/` is just one of many failing URLs; `/analytics/...` also 301s | Ruled out |
| 2 | Anonymous vs authenticated difference | Authenticated analytics `test_authenticated_user_gets_200` also 301s | Ruled out |
| 3 | `model_bakery`/factory missing required FK fields | Would produce 400/404/500; DB writes succeed (Ad row created); failure is a *header-level* 301 before the view | Ruled out |
| 4 | `ManifestStaticFilesStorage` URL rewriting breaks static URLs | Independent of request/response status; static 301 is not the observed body | Ruled out (see Appendix B) |
| 5 | Postgres SSL or connection error | `Ad.objects.create(...)` succeeds in setUp; error is `AssertionError`, not `OperationalError` | Ruled out |
| 6 | `request.is_secure()` honoring the proxy header incorrectly | Confirmed by reading `django/middleware/security.py` `process_request` + base.py settings | **Confirmed** |

---

## Environment

- OS: `win32` (Windows, PowerShell 5.1)
- Python: 3.14 (`.venv`)
- Django: 5.2.x (`>=5.2.16,<6.0`)
- PostgreSQL: 18-alpine (docker-local)
- Project CWD: `C:\py_dev\mko_bazuna`
- `DJANGO_SETTINGS_MODULE=config.settings.test` (set in root `conftest.py:7`)

## Test settings in use

- `src/backend/config/settings/test.py` (imports `base.py`, overrides DEBUG/DB/hasher)
- `src/backend/config/settings/base.py`:
  - line 67: `SECURE_SSL_REDIRECT = True`
  - line 68: `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`
  - line 108: `SecurityMiddleware` present in `MIDDLEWARE`

## Root `conftest.py` DB handling

`conftest.py:29-32` defaults `DATABASE_URL` to `postgres://postgres:postgres@127.0.0.1:5432/mko_bazuna`.
This default is only applied if `DATABASE_URL` is unset; locally it must be
exported before `uv run pytest`.

---

## Proposed Remediation (NOT yet applied)

Two viable options; **Option A** is recommended as the minimal, conventional
fix that also unblocks the entire existing view-test suite:

### Option A (recommended): disable the redirect in test settings

Add to `config/settings/test.py`:

```python
# Disable HTTPS redirection during tests — the Django test client uses HTTP,
# so SecurityMiddleware would otherwise 301 every request.
SECURE_SSL_REDIRECT = False
```

- Keeps `prod.py` (`True`) and `dev.py` (`False`) unchanged.
- Mirrors the existing pattern in `test.py` of overriding base-only-for-tests
  values (`DEBUG`, `DATABASES`, `PASSWORD_HASHERS`).
- One-line change, fixes the whole DB-backed view-test suite at once.

### Option B (alternative): make the test client send the secure header

In `conftest.py`, configure the test client to appear secure, e.g. subclass /
patch so requests carry `HTTP_X_FORWARDED_PROTO=https`. More invasive,
test-wide, and risks masking real SSL-redirect behavior — rejected in favor of
Option A.

### Reproducibility note (local Windows)

Until `DATABASE_URL` handling is consolidated, local repro requires:
```powershell
$env:DATABASE_URL = "postgres://postgres:postgres@127.0.0.1:5432/mko_bazuna"
uv run pytest <path>
```
A `conftest.py` fixture or `pytest.ini` env default could make this
hands-free. Left as a follow-up; not in scope of this fix.

---

## Appendix A: Why the project was running SQLite for tests

`pyproject.toml` `[tool.uv]` had `default-groups = []` historically
(documented in `.ai/audit/00-bug_report/test-infrastructure-issues.md` → B1),
so `uv sync` skipped dev tools. Combined with `uv.lock` being gitignored (B2)
and CI using `working-directory: src/backend` (B3/B4), the canonical
`docker-compose` test path is the intended Postgres route, but local runs
fell back to whatever `DATABASE_URL` resolved to — frequently SQLite via an
unset var, or a Postgres `db` host that can't resolve on Windows. These are
documented as prior issues; the SSL-redirect fix here is **orthogonal** to them.

## Appendix B: Separate non-fatal `staticfiles` warning

```
RuntimeWarning: No directory at: C:\py_dev\mko_bazuna\staticfiles\
    mw_instance = middleware(adapted_handler)
```

- Source: `ManifestStaticFilesStorage` configured in `base.py` references a
  `STATIC_ROOT = BASE_DIR / "staticfiles"` that does not exist locally.
- Impact: non-fatal; only affects static-file URL storage in DEBUG/test.
- Not the cause of the 301 (the 301 originates in `SecurityMiddleware.process_request`,
  before staticfiles middleware runs and before any view/template rendering).
- Out of scope for this bug report; flag for a future ticket if CI begins
  asserting on warnings or `--strict-warnings` is enabled.

## Related files (read-only references)

- `src/backend/config/settings/base.py` — `SECURE_SSL_REDIRECT`, `SECURE_PROXY_SSL_HEADER`, `MIDDLEWARE`
- `src/backend/config/settings/test.py` — test settings (override target)
- `src/backend/config/settings/dev.py` — `SECURE_SSL_REDIRECT = False` (reference for the convention)
- `src/backend/config/settings/prod.py` — keeps `SECURE_SSL_REDIRECT = True`
- `conftest.py` — `DJANGO_SETTINGS_MODULE`, `DATABASE_URL` default
- `.venv/Lib/site-packages/django/middleware/security.py` — `SecurityMiddleware.process_request` (301 logic)

## Related files in the current change scope

- `src/backend/apps/core/tests/test_language_end_to_end.py` — new composition integration test (blocked by this bug)
- `src/backend/apps/core/tests/test_ad_localization.py` — updated (blocked by this bug)
- `src/backend/apps/core/middleware/base.py` — `LanguagePreMiddleware` (not related to the 301, already green in unit tests)
- `src/backend/apps/ads/models.py` — `get_title`/`get_description` fallback cleanup (not related to the 301)
