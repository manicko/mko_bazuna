# Bug Report: Language Context Processor Not Registered in Templates

**Report ID:** 001
**Date:** 2026-07-27
**Found by:** i18n Integration Verification (TASK_023)
**Severity:** Medium
**Affected component:** Template rendering — localized ad content display

## Description

The `language` context processor defined in `apps/core/context_processors.py` provides `LANGUAGE_CODE` to all templates but is **not registered** in the `TEMPLATES[0].OPTIONS.context_processors` list in `settings/base.py`.

This means templates that use `{{ LANGUAGE_CODE }}` will not receive the value from this context processor, and will instead fall back to Django's default behavior.

## Details

### Current `context_processors` in `settings/base.py` (line 123-128):

```python
"context_processors": [
    "django.template.context_processors.request",
    "django.contrib.auth.context_processors.auth",
    "django.contrib.messages.context_processors.messages",
    "apps.core.context_processors.plausible_host",
],
```

Missing entries:
- `"apps.core.context_processors.language"` — custom processor that reads `request.LANGUAGE_CODE`
- `"django.template.context_processors.i18n"` — Django's built-in processor that provides `LANGUAGE_CODE`, `LANGUAGE_BIDI`

### Why it matters

1. Templates use `{{ ad|get_title:LANGUAGE_CODE }}` — without `LANGUAGE_CODE` in context, the template tag receives an empty string, so `Ad.get_title("")` will fall back through the chain and return the original `title` field.

2. Templates use `{{ LANGUAGE_CODE|upper }}` in `language_switcher.html` — without the context processor, this will be empty.

3. `LanguagePreMiddleware` sets `request.LANGUAGE_CODE`, but the custom context processor that reads it (`apps.core.context_processors.language`) is never invoked.

### Impact

- The locale-aware template filters (`get_title`/`get_description`) silently fall back to the Russian `title`/`description` fields instead of returning localized content per the user's language preference.
- The language switcher component displays an empty/invalid current language code.
- Templates that rely on LANGUAGE_CODE from the template context may fall back to the default language or display untranslated content.

## Fix

Add both context processors to `settings/base.py`:

```python
"context_processors": [
    "django.template.context_processors.request",
    "django.contrib.auth.context_processors.auth",
    "django.contrib.messages.context_processors.messages",
    "django.template.context_processors.i18n",          # ADD
    "apps.core.context_processors.plausible_host",
    "apps.core.context_processors.language",             # ADD (order matters — after i18n to override)
],
```

Note: `LanguagePreMiddleware` is correctly placed before `AuthenticationMiddleware` in the MIDDLEWARE list (line 109). The missing piece is exclusively the context processor registration.

## Also Affected

- **`django.middleware.locale.LocaleMiddleware`** is not in `MIDDLEWARE`. Without it, `{% trans %}` template tags will always use `settings.LANGUAGE_CODE` ("ru") regardless of `request.LANGUAGE_CODE`. Consider adding it after `LanguagePreMiddleware` to activate `.mo` files based on the detected language.