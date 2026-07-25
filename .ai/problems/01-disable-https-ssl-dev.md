# Django SSL/HTTPS Development Environment Research

**Date:** 2026-07-25  
**Topic:** Disabling HTTPS/SSL for Django development environment

---

## 1. Current Settings Analysis

### dev.py (Current State)
- `SECURE_SSL_REDIRECT = False` ✓
- `SESSION_COOKIE_SECURE = False` ✓
- `CSRF_COOKIE_SECURE = False` ✓

### Missing Overrides (Inherited from base.py)
- `SECURE_HSTS_SECONDS = 3600` — Still active in development (SHOULD BE DISABLED)
- `SECURE_HSTS_INCLUDE_SUBDOMAINS = True` — Still active (SHOULD BE DISABLED)
- `SECURE_HSTS_PRELOAD = False` — Still active (SHOULD BE DISABLED)
- `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` — Still active (SHOULD BE CHANGED/CLEARED)
- `USE_X_FORWARDED_HOST = True` — Still active (NOT APPLICABLE in dev)

### test.py Observations
- Uses `DEBUG = True`
- Inherits base.py SSL settings unchanged — potentially problematic for local testing

---

## 2. Django Security Settings for Development (Best Practices)

### SSL/HTTPS Settings to DISABLE in Development

| Setting | Dev Value | Reason |
|---------|-----------|--------|
| `SECURE_SSL_REDIRECT` | `False` | Prevents HTTP→HTTPS redirect loops, allows plain HTTP access |
| `SESSION_COOKIE_SECURE` | `False` | Cookies work over HTTP in dev, `True` would block them |
| `CSRF_COOKIE_SECURE` | `False` | CSRF cookie accessible over HTTP during development |
| `SECURE_HSTS_SECONDS` | `0` | HSTS header causes browser to force HTTPS; breaks dev access |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `False` | Not needed without HSTS |
| `SECURE_HSTS_PRELOAD` | `False` | Not needed without HSTS |
| `SECURE_PROXY_SSL_HEADER` | `None` or remove | Only needed behind TLS-terminating proxies |
| `USE_X_FORWARDED_HOST` | `False` | Only needed behind trusted proxies |

### Optional Security Headers (Can Stay Enabled)
These are safe to keep in development:
- `SECURE_CONTENT_TYPE_NOSNIFF = True` — Good security practice, no downside
- `SECURE_BROWSER_XSS_FILTER = True` (deprecated in modern browsers)
- `SECURE_REFERRER_POLICY = "same-origin"` — Actually fine for dev, limits referrer leakage

---

## 3. Approaches Comparison

### Approach A: Separate Settings Files (Current)
```
base.py    → Shared defaults (security-first)
dev.py     → Overrides per environment
prod.py    → Production overrides
test.py    → Test-specific overrides
```

**Pros:**
- Explicit per-environment configuration
- Clear audit trail for security reviewers
- No risk of DEBUG conditionals affecting production
- Easy to review what differs between environments

**Cons:**
- More files to maintain
- Easy to miss overriding a setting (current bug: HSTS not disabled in dev)
- Duplication of values across files

### Approach B: DEBUG-Based Conditionals in Base
```python
if DEBUG:
    SECURE_SSL_REDIRECT = False
    SECURE_HSTS_SECONDS = 0
    # ... etc
else:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
```

**Pros:**
- Single source of truth
- Cannot "forget" to disable SSL in dev
- Simpler mental model

**Cons:**
- DEBUG must be set before security settings are evaluated
- Production bugs more likely if DEBUG accidentally `True`
- Less explicit for security audits

### Recommendation
**Keep separate files (Option A)** but ensure dev.py explicitly disables ALL security-hardening settings. The current approach has a bug—`SECURE_HSTS_SECONDS` is inherited from base and not overridden.

---

## 4. Recommended dev.py Settings

```python
"""
Development settings for Mko Bazuna.
Imports base settings and overrides for local development.
"""

from .base import *  # noqa: F403, F401

DEBUG = True

# Disable all HTTPS/SSL security in development
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# HSTS must be completely disabled (0 = no header sent)
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# Proxy settings not applicable in development
SECURE_PROXY_SSL_HEADER = None
USE_X_FORWARDED_HOST = False

# Console logging for development
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}
```

---

## 5. Additional Considerations

### Email Backend for Development
Consider adding in dev.py:
```python
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
```

### CORS for Development (if frontend differs)
```python
CORS_ALLOWED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:8000"]
```

### Sentry/Sentry-like Error Reporting
Disable in development:
```python
if "SENTRY_DSN" in os.environ:
    del os.environ["SENTRY_DSN"]  # Don't send dev errors to production Sentry
```

---

## 6. Verification

After changes, run to verify no security warnings:
```bash
uv run python manage.py check --deploy
```

Expected output should show no HSTS or SSL-related warnings in dev.

---

## 7. Key References

- [Django Security Settings](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-hsts-seconds)
- [Deployment Checklist - HTTPS](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/#https)
- [HSTS Documentation](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security)