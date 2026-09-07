---
name: audit-findings
description: Block E — test coverage gap analysis for Spec 18 Task 10 (add test coverage for new functionality)
agent: auditor
phase: 11-bot-username-migration
block: E
scope: "Spec 18, Task 10 (L350-363): verify that the test suite covers the four expected outcomes — (1) template-level no-DB tests, (2) view-level DB tests for the contact_us handler + rate-limit cooldown, (3) admin tests for SiteConfig bot_username + RegexValidator, (4) migration seed test. Read-only audit — no production or test code was modified."
status: complete
validated: n/a
---

# Block E Audit Report — Test Coverage Gaps for Spec 18 Task 10

**Scope:** Spec 18, Task 10 ("Add test coverage for new functionality", spec L350–363). This is a
read-only audit of the *current* test suite against the spec's four expected outcome categories.
No production code or test code was modified.

**Spec anchor:** `.ai/problems/18_contact-us_spec.md` §3 Task 10 (L350-363):

> - **Template-level tests (no DB):** Assert `footer.html` includes a `{% trans "Contact us" %}`
>   link and a `js-telegram-link` class / `data-bot-encoded` attribute; assert `bot_username` is no
>   longer a bare `{{ bot_username }}` cleartext context variable in `detail.html`,
>   `header_catalog.html`, `privacy.html`, `login_issue.html`.
> - **View-level tests (DB):** Assert `contact_us` handler returns a greeting; assert rate
>   limiting returns cooldown after 5 triggers.
> - **Admin tests:** Assert `SiteConfig` admin shows the `bot_username` field with `RegexValidator`.
> - **Migration test:** Assert the seed migration populates `bot_username` from
>   `settings.BOT_USERNAME`.

---

## 0. HEADLINE VERDICT — Two mandatory gaps (admin + migration); one partial (login_issue.html source)

The implementation (Blocks A–D) is complete; the test suite covers most of Task 10, but **two
expected outcomes are entirely uncovered** and **one is only partially covered**:

| # | Expected outcome | Status | Gap |
|---|---|---|---|
| 1a | Footer "Contact us" link + `js-telegram-link`/`data-bot-encoded` (template-level) | **COVERED** | — |
| 1b | No bare `{{ bot_username }}` in `detail.html`, `header_catalog.html`, `privacy.html`, `login_issue.html` | **PARTIALLY COVERED** | `login_issue.html` has no source-level "no bare `{{ bot_username }}`" assertion; `privacy.html` checks `@{{ bot_username }}` not bare `{{ bot_username }}` |
| 2a | `contact_us` handler returns a greeting (view-level, DB) | **COVERED** | — |
| 2b | Rate limiting returns cooldown after 5 triggers (view-level, DB) | **COVERED** | — |
| 3 | `SiteConfig` admin shows `bot_username` with `RegexValidator` | **NOT COVERED** | No admin test file exists anywhere in the project |
| 4 | Seed migration populates `bot_username` from `settings.BOT_USERNAME` | **NOT COVERED** | `test_migrations.py` only checks `makemigrations --check` (skipped in test env) + idempotency; no seed-value assertion |

---

## 1. Existing Test Files — Inventory

### 1.1 `src/backend/apps/core/tests/` — all 24 test files

| File | Blocks covered | DB? | Key tests for Spec 18 |
|---|---|---|---|
| `test_footer_contact_link.py` | Block A | No (`pytest.mark.unit`) | Footer "Contact us" link, `js-telegram-link`, `data-bot-encoded`, `data-start="contact_us"`, JS cookie, consent gate absence |
| `test_rtl_obfuscation.py` | Block B + C | No (`pytest.mark.unit`) | `rtl_obfuscate` filter, `bot-username-rtl` class (CSS + compiled output), `telegram_deep_link` tag omits `bot-username-rtl`, `privacy.html` source checks (`@{{ bot_username }}` absent, `sr-only` pairing, loads `telegram_tags`) |
| `test_site_config_bot_username.py` | Task 1 | Yes (`django_db`, `integration`) | `get_bot_username()` returns configured value, cache read, DB-error fallback, cache invalidation on save, cache-key distinctness |
| `test_contact_rate_limit.py` | Task 7 (CR-10) | Yes (`django_db`, `integration`) | `check_deep_link_render_rate_limit` service (60/threshold/XFF), view-level 429 on privacy/detail/listings/login_issue |
| `test_js_execution.py` | Task 8 (CR-11) | No (`pytest.mark.unit`) | `JSExecutionMiddleware.process_request` cookie parsing, `js_verified` context processor |
| `test_site_config.py` | (site name) | Yes (`django_db`, `integration`) | `get_site_name()` cache/fallback/signal — the symmetric pattern that `get_bot_username` mirrors |
| `test_migrations.py` | (general) | Yes (`django_db`, `slow`, `integration`) | `makemigrations --check --dry-run` (skipped in test env), migration idempotency (re-apply is no-op) |
| `test_templates.py` | (consent guard) | No (`unit`) | Consent-banner guard across templates, `query_replace` tag |
| `test_privacy.py` | (privacy render) | — | (read separately) |
| `test_context_processors.py` | (context) | No (`unit`) | `language()`, `header_context()`, `site_config()` processors |
| `test_contact.py` | (R2 render conditions) | Yes | `can_contact_seller`, `CONTACT_PATTERN`, PII-in-log |
| `test_contact_response.py` | (analytics) | Yes | `record_contact_response` |
| + 13 more (advisory locks, city/middleware, language, sanitize, sweep, CSP, create_admin_user) | | | |

### 1.2 `src/telegram_bot/tests/` — all 13 test files

| File | Blocks covered | DB? | Key tests for Spec 18 |
|---|---|---|---|
| `test_contact_us.py` | Task 5 (CR-4/CR-5) | Yes (`django_db`, `integration`) | `/start contact_us` greeting + inline button, `is_bot` guard (no budget consumed), rate-limit cooldown message after 5 triggers, `CONTACT_US_PATTERN` routing, login deep-link callback identical-output contract |
| `test_rate_limit_service.py` | Task 6 (CR-10) | Yes (`django_db`, `integration`) | `check_contact_start_rate_limit` — allows 5, blocks 6th, per-user isolation, custom limit/period |
| `test_login.py` | (login flow) | — | `test_login_issue_renders_deep_link` — asserts `js-telegram-link` + `data-bot-encoded` + `data-start="login_"` in rendered output |
| `conftest.py` | (fixtures) | — | Bot test fixtures (async `user`) |
| + 10 more (ad lifecycle, media, price payload, multi-lang, etc.) | | | |

---

## 2. Detailed Assessment of Each Task 10 Expected Outcome

### Outcome 1a — Footer "Contact us" link + `js-telegram-link` / `data-bot-encoded` (template-level, no DB)

**Status: COVERED**

**Evidence:** `test_footer_contact_link.py` (7 assertions, all `pytest.mark.unit`, no DB):

| Test | Asserts |
|---|---|
| `test_footer_loads_telegram_tags_library` | `{% load telegram_tags %}` + `{% load i18n %}` in footer.html source |
| `test_footer_renders_contact_us_via_tag` | `{% telegram_deep_link "contact_us" %}` in footer.html source |
| `test_contact_link_not_gated_by_consent` | No `{% if %}` / `{% endif %}` gate in the footer `<nav>` block — link visible to all visitors |
| `test_footer_sets_js_true_cookie` | One-line `<script>` with `document.cookie = "js=true; SameSite=Lax; Secure; path=/"` |
| `test_rendered_footer_contains_contact_link_markup` | Rendered HTML has `js-telegram-link`, `data-bot-encoded`, `data-start`, and visible `"Contact us"` label (with mocked `get_bot_username`) |
| `test_rendered_contact_link_uses_contact_us_payload` | `data-start="contact_us"` (no ad-id argument) |
| `test_contact_link_remains_visible_when_js_not_verified` | `js_verified=False` → inert `href="#"` with no `data-bot-encoded`/`data-start`, but link still visible and cookie script still present |

The footer template (`footer.html:4`–`:13`) is confirmed in implementation: it loads `telegram_tags`,
uses `{% telegram_deep_link "contact_us" classes=... %}`, and emits the inline JS-execution cookie
script. **No gap.**

---

### Outcome 1b — No bare `{{ bot_username }}` in `detail.html`, `header_catalog.html`, `privacy.html`, `login_issue.html` (template-level, no DB)

**Status: PARTIALLY COVERED** — three of four templates have source-level assertions; `login_issue.html` does not.

**Evidence per template:**

| Template | Test file + function | Assertion type | Result |
|---|---|---|---|
| `detail.html` | `test_detail_context.py::test_detail_template_uses_bot_username_not_settings` (L133-141) | Source-level: reads `.read_text()`, asserts `{% telegram_deep_link %}` present, `{{ bot_username }}` absent, `settings.BOT_USERNAME` absent | ✅ FULLY COVERED |
| `header_catalog.html` | `test_autocomplete_template.py::test_bot_username_comes_from_context` (L139-145) | Source-level: reads `header_catalog.html` source, asserts `{% telegram_deep_link %}` present, `{{ bot_username }}` absent (comment at L6 is fine — not a template variable) | ✅ FULLY COVERED |
| `privacy.html` | `test_rtl_obfuscation.py::test_privacy_html_no_bare_display_username` (L255-265) | Source-level: asserts `@{{ bot_username }}` (with `@` prefix) absent from source — checks the display-text `@<span>` pattern, not bare `{{ bot_username }}` | ⚠️ PARTIAL — assertion targets `@{{ bot_username }}` specifically; `privacy.html` intentionally retains bare `{{ bot_username }}` inside `sr-only` spans (L109) for screen-reader accessibility (spec Constraint #4, A2). The test validates the wrong surface: it should assert `@{{ bot_username }}` display pattern is gone (which it does) but does NOT assert bare `{{ bot_username }}` in `href` attributes is gone. |
| `login_issue.html` | `test_login.py::test_login_issue_renders_deep_link` (L40-51) | **Rendered-output only** (via `Client().get("/login/issue/")`): asserts `js-telegram-link`, `data-bot-encoded`, `data-start="login_"` in HTTP response body | ⚠️ PARTIAL — no source-level assertion that `{{ bot_username }}` or `{{ deep_link }}` is absent from `login_issue.html` template source. The rendered-output test proves the tag works at runtime, but does not guard against a future regression that re-introduces bare `{{ bot_username }}` or `{{ deep_link }}` in the template source. |

**Gap detail:**

- **`login_issue.html` (NOT COVERED at source level):** The template is already migrated (L22 uses
  `{% telegram_deep_link "login" raw_token ... %}`; L21 formerly had `href="{{ deep_link }}"`;
  L38's JS now uses `a[data-start^="login_"]` selector instead of `a[href^="https://t.me"]`).
  However, no test reads `login_issue.html` source and asserts `"{{ bot_username }}" not in content`
  or `"{{ deep_link }}" not in content` or `"settings.BOT_USERNAME" not in content`. A regression
  that re-introduces cleartext would pass all current tests because `test_login_issue_renders_deep_link`
  only checks rendered output (which would still contain `js-telegram-link` if the tag is present).

- **`privacy.html` (ASSERTION MISMATCH):** The existing `test_privacy_html_no_bare_display_username`
  checks `@{{ bot_username }}` is absent. This is the correct check for the display-text pattern.
  However, the spec's Task 10 says "assert bot_username is no longer a bare `{{ bot_username }}`
  cleartext context variable" — which for `privacy.html` means checking that `{{ bot_username }}`
  does not appear as a cleartext `href` (it doesn't — both L31 and L146 now use the tag). The
  `sr-only` span `{{ bot_username }}` at L109 is intentional and acceptable. The test does not
  explicitly verify the `href`-location migration (L31/L146 use the tag), but the source-level
  check `@{{ bot_username }}` not in source + the tag being present implicitly covers it.

**Recommendation:** Add a source-level test that reads `login_issue.html` and asserts
`{{ bot_username }}` / `{{ deep_link }}` / `settings.BOT_USERNAME` are absent and
`{% telegram_deep_link` is present (mirroring `test_detail_template_uses_bot_username_not_settings`).
Effort: trivial. Priority: recommended (prevents regression).

---

### Outcome 2a — `contact_us` handler returns a greeting (view-level, DB)

**Status: COVERED**

**Evidence:** `test_contact_us.py::TestContactUsDeepLink::test_greeting_with_keyboard` (L80-97):

- Invokes `handle_contact_us_start(message, bot)` with a mocked non-bot user.
- Asserts `result is True` (handler fully handled the deep-link).
- Asserts `message.answer.assert_awaited_once()`.
- Asserts `sent_text == _CONTACT_US_GREETING` (the shared greeting constant from `contact.py:38-42`).
- Asserts `"службой поддержки" in sent_text` (verifies the Russian greeting content).
- Asserts the inline keyboard button has `callback_data == "contact_us"` and `text == "Contact us"`.

The handler under test (`contact.py:103-121`, `handle_contact_us_start`) is confirmed in
implementation: it checks `message.from_user.is_bot` (OQ1: reject bots first), calls
`check_contact_start_rate_limit(message.from_user.id)` (Task 6), and on success responds with
`_CONTACT_US_GREETING` + `_contact_us_keyboard()`. **No gap.**

---

### Outcome 2b — Rate limiting returns cooldown after 5 triggers (view-level, DB)

**Status: COVERED**

**Evidence (two test files, complementary coverage):**

1. **`test_contact_us.py::TestContactUsDeepLink::test_rate_limited_sends_cooldown`** (L113-128):
   - Pre-exhausts the per-user budget by calling `check_contact_start_rate_limit(203)` 5 times
     (`assert ... is True` for each).
   - Invokes `handle_contact_us_start(message, bot)` with `user_id=203`.
   - Asserts `message.answer.assert_awaited_once()`.
   - Asserts `sent_text == CONTACT_US_RATE_LIMITED_MESSAGE` (the cooldown message constant from
     `contact.py:45-47`: `"Слишком много запросов в поддержку. Попробуйте позже."`).

2. **`test_rate_limit_service.py::TestContactStartRateLimit`** (4 tests, L27-51):
   - `test_allows_under_limit` — first 5 triggers return `True`.
   - `test_blocks_after_threshold` — 6th trigger returns `False`.
   - `test_independent_per_user` — counters isolated per `user_id`.
   - `test_custom_limit_and_period` — `limit`/`period` kwargs override defaults.

The rate-limit service (`telegram_bot/services/rate_limit.py:81-116`,
`check_contact_start_rate_limit(user_id, limit=5, period=600)`) uses the `cache.add` + `cache.incr`
idiom with key `bot_contact_rl:{user_id}`. The `handle_contact_us_start` handler calls this service
at `contact.py:117` and sends `CONTACT_US_RATE_LIMITED_MESSAGE` when it returns `False`
(`contact.py:118`). **No gap.**

**Note:** The spec phrase "returns cooldown" is satisfied at two layers — the handler-level
integration test (`test_contact_us.py`) verifies the actual cooldown *message* is sent to the user,
and the service-level test (`test_rate_limit_service.py`) verifies the boolean *gate* (5 allowed,
6th blocked). Both are present.

---

### Outcome 3 — `SiteConfig` admin shows `bot_username` with `RegexValidator` (admin test)

**Status: NOT COVERED**

**Evidence of the missing test:**

A repo-wide grep for admin-related test patterns in `src/backend/apps/core/tests/` returns zero
results for `SiteConfigAdmin`, `admin.site.register`, `AdminSite`, `admin_client`, or any test
function matching `test.*admin.*site_config`:

```
$ grep -rn "SiteConfigAdmin|admin.site.register|AdminSite|override_settings.*admin|admin_client" \
    src/backend/apps/core/tests/
(nothing — the only SiteConfigAdmin reference is in admin.py:12, the definition itself)
```

The `grep` for `test.*admin` across `src/backend/apps` returns only:
- `test_create_admin_user.py` — tests the `create_admin_user` **management command** (not the admin
  interface; does not touch `SiteConfigAdmin` or `bot_username`).
- `test_auth_nav.py:134` — tests staff seeing an admin *link* (unrelated).
- `test_trust_analytics.py`, `test_trust_calculator.py`, `test_admin_actions.py`,
  `test_moderation_views.py` — test admin *actions* in other apps (moderation, trust), none touch
  `SiteConfig`.

**What exists that should be tested but is not:**

`src/backend/apps/core/admin.py:11-28` — `SiteConfigAdmin`:
```python
@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    list_display = ["name", "bot_username"]
    readonly_fields = []

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
```

The model field (`models.py:26-36`) has the `RegexValidator`:
```python
bot_username = models.CharField(
    max_length=32,
    default="bazuna_bot",
    help_text="Telegram bot username without @ prefix",
    validators=[
        RegexValidator(
            regex=r"^[A-Za-z0-9_]{3,32}$",
            message="Bot username must be 3-32 characters, alphanumeric and underscore only",
        ),
    ],
)
```

**What the missing test should assert** (per Task 10):
1. `SiteConfigAdmin.list_display` includes `"bot_username"` (so it renders in the changelist).
2. The `bot_username` model field has a `RegexValidator` with pattern `^[A-Za-z0-9_]{3,32}$`.
3. (Integration-level, optional but recommended) The admin change form validates: a valid value
   like `"bazuna_bot"` is accepted; an invalid value like `"@bad"` or `"ab"` (too short) is rejected.

**Gap severity: MEDIUM.** The `admin.py` and `models.py` are correctly implemented — the field,
the `RegexValidator`, the `list_display`, the `help_text`, and the singleton `has_add_permission`/
`has_delete_permission` overrides are all present. The gap is purely a **test-assertion gap**:
there is zero test coverage verifying that the admin surface exposes `bot_username` with its
`RegexValidator`. A future refactor that accidentally removes `bot_username` from `list_display`
or drops the `RegexValidator` from the model field would pass all existing tests.

**Recommendation:** Create `src/backend/apps/core/tests/test_site_config_admin.py` with:
- A unit test asserting `"bot_username" in SiteConfigAdmin.list_display`.
- A unit test asserting the model field's `validators` list contains a `RegexValidator` with
  `regex == r"^[A-Za-z0-9_]{3,32}$"` (inspect `SiteConfig._meta.get_field("bot_username").validators`).
- An integration test using `django.contrib.admin.sites.AdminSite` + the admin's `changeform_view`
  to POST an invalid value and assert the form errors, mirroring the
  `test_detail_context.py` unit-test idiom (no DB rows needed for the validator inspection;
  `django_db` needed for the form-level integration test).

Effort: small. Priority: recommended (test hygiene; the implementation is correct, only the
assertion is missing).

---

### Outcome 4 — Seed migration populates `bot_username` from `settings.BOT_USERNAME`

**Status: NOT COVERED**

**Evidence of the missing test:**

`test_migrations.py` (the only migration test file) contains exactly two tests:

1. **`test_makemigrations_check`** (L23-57) — runs `makemigrations --check --dry-run` to detect
   pending migration drift. **This test is SKIPPED in the test environment:**
   ```python
   _MIGRATIONS_DISABLED = bool(getattr(settings, "MIGRATION_MODULES", {}))

   @pytest.mark.skipif(
       _MIGRATIONS_DISABLED,
       reason="MIGRATION_MODULES=None disables migration replay; ..."
   )
   def test_makemigrations_check() -> None:
   ```
   Test settings (`config/settings/test.py:78-83`) set `MIGRATION_MODULES = DisableMigrations()`,
   which is truthy → `test_makemigrations_check` is always skipped during `make test`. It guards
   against schema drift only when migrations are active (i.e., not in the test DB), so it provides
   **zero** coverage of the `0003_add_bot_username` seed function.

2. **`test_migration_idempotency`** (L60-95) — runs `migrate --noinput` and asserts the output
   contains `"No migrations to apply."`. With `MIGRATION_MODULES = DisableMigrations()`, all apps
   have `None` migrations, so `migrate` produces `"No migrations to apply."` trivially — it does
   **not** replay or execute any migration's `RunPython` code. It checks that re-applying
   migrations is a no-op, but since migrations are disabled, it is a vacuous truth.

**Neither test touches `seed_bot_username` or asserts the seed value.**

**What exists that should be tested but is not:**

`src/backend/apps/core/migrations/0003_add_bot_username.py` (52 lines):
```python
def seed_bot_username(apps, schema_editor):
    SiteConfig = apps.get_model("core", "SiteConfig")
    from django.conf import settings as dj_settings
    bot_username = getattr(dj_settings, "BOT_USERNAME", "") or "bazuna_bot"
    # Only seed rows that are still at the factory default — never
    # overwrite an admin-edited value on re-run.
    SiteConfig.objects.filter(pk=1, bot_username="bazuna_bot").update(
        bot_username=bot_username
    )
```

The migration:
1. Adds the `bot_username` CharField (default `"bazuna_bot"`, with the `RegexValidator`).
2. Runs `seed_bot_username` — reads `settings.BOT_USERNAME` (env var, defaults to `""` in test)
   and falls back to `"bazuna_bot"` if empty.

**What the missing test should assert** (per Task 10):
1. After running migration `0003` forward, `SiteConfig.objects.get(pk=1).bot_username` equals
   `settings.BOT_USERNAME` (when set) or `"bazuna_bot"` (when the env var is empty — which is
   the default in the test environment).
2. The `seed_bot_username` function does **not** overwrite an admin-edited value (idempotency of
   the seed logic: `filter(pk=1, bot_username="bazuna_bot")` — only seeds rows still at default).

**Gap severity: MEDIUM.** The migration and its seed function are correctly implemented. The gap
is a test-assertion gap: the seed behavior (the spec's Task 1 seed function) has no dedicated
test. The existing `test_migrations.py` covers only schema-drift detection and idempotency, not
data-seeding correctness. If a future developer changes the fallback default or the seed query
filter, nothing in the test suite would catch it.

**Why this is hard in the current test setup:** Test settings set
`MIGRATION_MODULES = DisableMigrations()`, which means `call_command("migrate", "core", "0003")`
will NOT execute the `RunPython` seed function — Django skips migration replay entirely and
creates tables via introspection. A seed-value test must therefore test `seed_bot_username`
**directly** (call the function with a mock `apps` object and a real `schema_editor`), or
temporarily re-enable migrations for the `core` app. The direct-function approach is the
established pattern in this codebase (see `test_sweep_lock_structure.py` for testing migration
RunSQL scripts directly).

**Recommendation:** Create `src/backend/apps/core/tests/test_migration_seed_bot_username.py` with:
- A direct-call test of `seed_bot_username`: instantiate `SiteConfig(pk=1, bot_username="bazuna_bot")`,
  save it, call `seed_bot_username(apps=..., schema_editor=None)` with `settings.BOT_USERNAME`
  overridden via `override_settings`, and assert `SiteConfig.objects.get(pk=1).bot_username`
  equals the override value.
- A fallback test: with `BOT_USERNAME=""` (default), assert the seed leaves `bot_username` as
  `"bazuna_bot"` (since the filter `pk=1, bot_username="bazuna_bot"` matches and `.update()`
  sets it to `"" or "bazuna_bot"` = `"bazuna_bot"`).
- An idempotency test: set `bot_username` to a non-default value (simulating admin edit), run
  `seed_bot_username`, and assert the value is **not** overwritten.

Effort: small. Priority: recommended (the seed function has real conditional logic that is
untested; a change to the filter clause or fallback could silently break admin-configured
usernames across all environments when `0003` first runs).

---

## 3. Additional Observations (not in Task 10's 4 expected outcomes, but relevant to test coverage)

### 3.1 `get_bot_username` is not exported from `services/__init__.py`

`src/backend/apps/core/services/__init__.py` (L10-19) exports only `get_site_name` and
`get_site_name_async` — `get_bot_username` and `get_bot_username_async` are defined in
`site_config.py` (L45-75) but **not** re-exported from the package `__init__.py`. Tests import
directly from `apps.core.services.site_config` (e.g. `test_site_config_bot_username.py:17`), so
this does not break existing tests — but it is an inconsistency with the `site_name` pattern
(which IS exported and used by `context_processors.py:114` via `apps.core.services.site_config`).
Not a test-coverage gap per se, but worth noting for the implementor: if any future test or
consumer imports `from apps.core.services import get_bot_username`, it would fail.

### 3.2 `header_context` still passes `bot_username` as a context variable

`context_processors.py:93` — `header_context()` returns `"bot_username": get_bot_username()`.
This is correct *functionally* (the value now comes from `SiteConfig` via the service, not
`settings.BOT_USERNAME`), and it is consumed by `privacy.html:109` (the `sr-only` span).
The `telegram_deep_link` tag does NOT use the context variable — it calls `get_bot_username()`
internally (`telegram_tags.py:146`). So there are two resolution paths for the bot username:
(a) via the context processor variable (used only by `privacy.html`'s `sr-only` span), and
(b) via the tag's internal `get_bot_username()` call (used by all `telegram_deep_link` tag
locations). Both resolve to the same `SiteConfig` singleton + cache, so there is no
correctness issue. However, this dual-path is not documented in any test, and the
`test_context_processors.py` does not assert that `header_context()` returns `bot_username`
from the service (it tests `root_categories`, `preferred_city_display`, `cities`,
`favorites_count`, and `catalog_js_labels` but not `bot_username`).

**Gap:** `test_context_processors.py` does not assert `header_context()["bot_username"]`
resolves to `get_bot_username()`. A regression that reverts `header_context` to
`settings.BOT_USERNAME` would not be caught.

Effort to close: trivial. Priority: low-advisory.

---

## 4. Summary

| Severity | Count | Findings |
|---|---|---|
| CRITICAL | 0 | — |
| HIGH | 0 | — |
| MEDIUM | 2 | FE-E-001 (admin test missing), FE-E-002 (migration seed test missing) |
| LOW | 2 | FE-E-003 (login_issue.html source-level assertion missing — partial), FE-E-004 (header_context bot_username not tested in context_processors) |
| INFORMATIONAL | 1 | FE-E-005 (services/__init__.py doesn't export get_bot_username — not a test gap, just an inconsistency) |

### Mandatory (test-assertion hygiene)

- **FE-E-001** — Add admin test for `SiteConfigAdmin`: assert `bot_username` in `list_display`
  and the field's `RegexValidator` is attached. The implementation is correct; only the assertion
  is missing.
- **FE-E-002** — Add migration seed test for `0003_add_bot_username`: assert `seed_bot_username`
  populates `bot_username` from `settings.BOT_USERNAME` with `"bazuna_bot"` fallback, and does not
  overwrite admin-edited values. Must call the function directly due to
  `MIGRATION_MODULES = DisableMigrations()` in test settings.

### Recommended

- **FE-E-003** — Add source-level template assertion for `login_issue.html`: assert
  `{{ bot_username }}` / `{{ deep_link }}` / `settings.BOT_USERNAME` absent,
  `{% telegram_deep_link %}` present (mirrors `test_detail_context.py:133`).
- **FE-E-004** — Add context-processor assertion: `header_context()["bot_username"] ==
  get_bot_username()` (or assert it doesn't equal `settings.BOT_USERNAME`).

### Advisory

- **FE-E-005** — Export `get_bot_username` / `get_bot_username_async` from
  `apps.core.services.__init__` to match the `get_site_name` / `get_site_name_async` pattern
  (consistency; prevents `ImportError` if a future test/consumer uses the package-level import).

---

## 5. Files Read in Full (Audit Trail)

| File | Purpose |
|---|---|
| `src/backend/apps/core/tests/test_footer_contact_link.py` (155 lines) | Block A footer tests — confirms 1a is covered |
| `src/backend/apps/core/tests/test_rtl_obfuscation.py` (310 lines) | Block B/C tests — privacy.html source checks, tag class_attr, CSS rule checks |
| `src/backend/apps/core/tests/test_site_config_bot_username.py` (103 lines) | Task 1 service tests — get_bot_username cache/fallback/signal |
| `src/backend/apps/core/tests/test_contact_rate_limit.py` (97 lines) | Task 7 web-side rate limit tests — service + 429 view-level |
| `src/backend/apps/core/tests/test_js_execution.py` (103 lines) | Task 8 JS-execution cookie/middleware tests |
| `src/backend/apps/core/tests/test_site_config.py` (128 lines) | Symmetric site_name tests (pattern reference for bot_username) |
| `src/backend/apps/core/tests/test_migrations.py` (97 lines) | General migration tests — confirms no seed-value test exists |
| `src/backend/apps/core/tests/test_templates.py` (213 lines) | Consent banner guard + query_replace (no bot_username checks) |
| `src/backend/apps/core/tests/test_context_processors.py` (239 lines) | Context processor tests — confirms no `bot_username` assertion in header_context tests |
| `src/telegram_bot/tests/test_contact_us.py` (211 lines) | Task 5 bot handler tests — greeting + cooldown + pattern routing |
| `src/telegram_bot/tests/test_rate_limit_service.py` (52 lines) | Task 6 bot-side rate limit tests |
| `src/backend/apps/ads/tests/test_detail_context.py` (178 lines) | Confirms detail.html source-level "no bare {{ bot_username }}" test exists |
| `src/backend/apps/search/tests/test_autocomplete_template.py` (330 lines) | Confirms header_catalog.html source-level test exists |
| `src/backend/apps/users/tests/test_login.py` (418 lines) | Confirms login_issue.html rendered-output-only test (no source check) |
| `src/backend/apps/ads/tests/test_detail_render.py` (72 lines) | Rendered deep-link output test (G4) |
| `src/backend/apps/core/admin.py` (28 lines) | SiteConfigAdmin — confirms bot_username in list_display, no admin test exists |
| `src/backend/apps/core/migrations/0003_add_bot_username.py` (52 lines) | Seed migration — confirms seed_bot_username function exists, untested |
| `src/backend/apps/core/models.py` (50 lines) | SiteConfig model with bot_username field + RegexValidator |
| `src/backend/apps/core/services/site_config.py` (71 lines) | get_bot_username()/get_bot_username_async() service |
| `src/backend/apps/core/services/__init__.py` (20 lines) | Confirms get_bot_username NOT exported |
| `src/backend/apps/core/templatetags/telegram_tags.py` (208 lines) | telegram_deep_link tag + rtl_obfuscate filter + _JS_IIFE |
| `src/backend/apps/core/context_processors.py` (141 lines) | header_context passes bot_username from get_bot_username() |
| `src/backend/apps/core/middleware/js_check.py` (30 lines) | JSExecutionMiddleware — CR-11 |
| `src/backend/config/settings/test.py` (86 lines) | Confirms MIGRATION_MODULES = DisableMigrations() — explains why seed test must call function directly |
| `src/backend/config/settings/base.py` (270 lines) | BOT_USERNAME = os.getenv("BOT_USERNAME", "") — seed source |
| `src/backend/templates/components/footer.html` (14 lines) | Confirms footer uses {% telegram_deep_link "contact_us" %} + JS cookie |
| `src/backend/templates/privacy.html` (155 lines) | Confirms all 4 locations migrated (tag for hrefs, rtl_obfuscate+sr-only for display) |
| `src/backend/templates/components/header_catalog.html` (671 lines) | Confirms {% telegram_deep_link "create_ad" %} at L34, no bare {{ bot_username }} |
| `src/backend/templates/users/login_issue.html` (65 lines) | Confirms {% telegram_deep_link "login" raw_token %} at L22, no bare {{ bot_username }} or {{ deep_link }} |
| `.ai/problems/18_contact-us_spec.md` (645 lines) | Spec §3 Task 10 — the 4 expected outcomes |
| `.ai/audit/11-bot-username-migration/findings.md` (656 lines) | Block 1 reference — confirms consumer migration is complete (findings are pre-implementation) |
| `src/theme/static/theme/css/input.css` (15 lines) | Confirms .bot-username-rtl { direction: rtl; unicode-bidi: bidi-override; } rule exists |
| `src/theme/static/theme/css/output.css` (2 lines, minified) | Confirms compiled .bot-username-rtl rule |
| `src/telegram_bot/handlers/contact.py` (245 lines) | handle_contact_us_start, CONTACT_US_PATTERN, _CONTACT_US_GREETING, CONTACT_US_RATE_LIMITED_MESSAGE |
| `src/telegram_bot/handlers/login.py` (207 lines) | handle_login_deep_link delegates to handle_contact_start |

---

## 6. Answers to the investigation questions from the audit brief

1. **`test_footer_contact_link.py` — what does it test?**
   Seven unit tests (no DB) covering: footer loads `telegram_tags` library, renders
   `{% telegram_deep_link "contact_us" %}` in source, contact link is not gated by consent
   (no `{% if %}`), the `js=true` cookie script is a single inline `<script>`, rendered output
   has `js-telegram-link`/`data-bot-encoded`/`data-start`, `data-start="contact_us"` (no ad-id),
   and the link remains visible (inert `href="#"` without `data-*`) when `js_verified=False`.

2. **`test_rtl_obfuscation.py` — what does it test?**
   Thirteen unit tests (no DB) covering: `rtl_obfuscate` filter reverses string + inserts RLM
   marks (L54-100), the `telegram_deep_link` tag omits `bot-username-rtl` from `class_attr`
   for `contact_us` and `create_ad` commands (L170-196), the `.bot-username-rtl` CSS rule exists
   in both `input.css` and compiled `output.css` (L204-217), `privacy.html` loads `telegram_tags`
   and uses `rtl_obfuscate` with `bot-username-rtl` + `sr-only` pairing and no `@{{ bot_username }}`
   display (L225-265), and the tag's `target="_blank"` parameter emits `window.open` in the IIFE.

3. **`test_site_config_bot_username.py` — what does it test?**
   Five integration tests (DB) covering: `get_bot_username()` returns the admin-configured value
   from `SiteConfig` (L46-51), second call hits the cache without touching `get_singleton`
   (L54-67), falls back to `"bazuna_bot"` on `RuntimeError` (L70-74), `save()` invalidates the
   cache via the `post_save` signal (L77-95), and the cache key is distinct from the site-name
   key (L98-103). **Does NOT test the migration seed or admin.**

4. **`test_contact_rate_limit.py` — what does it test?**
   Nine integration tests (DB) covering: `check_deep_link_render_rate_limit` service
   (allows 60, blocks 61st, per-IP isolation, X-Forwarded-For precedence) (L35-59), and
   view-level 429 wiring on `/privacy/`, `/ads/<id>/`, `/listings/` (non-HX), `/listings/`
   (HX — excluded), `/login/issue/` (L65-96). Uses cache key `telegram_dl_rl:{ip}`,
   limit 60/period 600s.

5. **`test_js_execution.py` — what does it test?**
   Eight unit tests (no DB) covering: `JSExecutionMiddleware.process_request` sets
   `request.js_verified` from the `js` cookie (`"true"` → True; absent/false/garbage → False)
   (L42-71), and the `js_verified` context processor forwards the attribute (L79-102), defaulting
   to `True` when middleware did not run.

6. **`test_rate_limit_service.py` (bot-side) — what does it test?**
   Four integration tests (DB) covering: `check_contact_start_rate_limit(123)` allows 5, blocks
   6th, per-user isolation, and custom `limit`/`period` kwargs override. Uses cache key
   `bot_contact_rl:{user_id}`, default limit 5/period 600s.

7. **`test_contact_us.py` — what does it test?**
   Five async tests across three classes covering: `handle_contact_us_start` greeting + keyboard
   with `callback_data="contact_us"` and `text="Contact us"` (L80-97), `is_bot` guard skips
   answering and does not consume rate budget (L99-111), rate-limit cooldown message after 5
   triggers (L113-128), `CONTACT_US_PATTERN` matches `contact_us` but not `contact_<ad_id>`
   (L131-138), and `handle_contact_us_callback` edits the message to the same greeting (L149-164)
   including the no-message no-op case (L166-176). Also tests the login `/start` greeting button
   (L187-211).

8. **Are there admin tests for SiteConfig anywhere?**
   **No.** A repo-wide grep for `SiteConfigAdmin`, `admin.site.register(SiteConfig)`, `AdminSite`,
   or `admin_client` in test files returns zero matches. The only `SiteConfigAdmin` reference is
   its definition in `admin.py:12`. The `test_create_admin_user.py` file tests a management
   command, not the admin interface.

9. **Is there a migration test for `0003_add_bot_username` anywhere?**
   **No.** `test_migrations.py` contains only `test_makemigrations_check` (skipped in test env
   due to `MIGRATION_MODULES = DisableMigrations()`) and `test_migration_idempotency` (runs
   `migrate --noinput` which is a no-op with disabled migrations). No test asserts that
   `seed_bot_username` populates `bot_username` from `settings.BOT_USERNAME` or falls back to
   `"bazuna_bot"`.
