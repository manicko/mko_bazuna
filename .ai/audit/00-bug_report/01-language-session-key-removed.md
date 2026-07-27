---
id: bug-001
title: LANGUAGE_SESSION_KEY removed in Django 5.2
severity: blocker
found_by: task_024
affected:
  - src/backend/apps/core/middleware/language.py
---

## Description

`LANGUAGE_SESSION_KEY` was removed from `django.utils.translation` in Django 5.x.
The middleware at `language.py` line 15 attempts to import it, which raises an
`ImportError`, making the entire middleware module unimportable.

## Root Cause

Django 5.x removed the public LANGUAGE_SESSION_KEY constant from django.utils.translation. Applications that relied on importing this constant must now define their own session key or otherwise avoid depending on Django's internal implementation details.

## Impact

- The middleware module cannot be imported, so it is effectively dead code.
- Any request hitting this middleware would fail at module load time,
  raising a 500 error.
- Tests for this middleware (`test_language_middleware.py`) cannot run
  because the import chain breaks at `language.py:15`.

## Affected Code

```python
# language.py line 15 — broken import
from django.utils.translation import LANGUAGE_SESSION_KEY

# language.py line 77 — usage that would fail
request.session[LANGUAGE_SESSION_KEY] = lang
```

## Suggested Fix

Replace the import with the hardcoded session key string `"_language"`,
or define a local constant in the middleware module:

```python
# language.py

# Django 5.x no longer exports LANGUAGE_SESSION_KEY.
# Define the session key locally to avoid depending on Django internals.
LANGUAGE_SESSION_KEY = "_language"
```

This is the same key that Django's `LocaleMiddleware` uses internally.