"""
Production settings for Mko Bazuna.
Imports base settings and applies production safety configuration.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403, F401

DEBUG = False

# Fail fast: BOT_TOKEN is required in production. The bot process cannot
# function without a valid token; an empty value indicates a deployment error.
# Skip during Docker build (DJANGO_BUILD=1) so collectstatic succeeds with
# placeholder values; the real token is provided at runtime via .env.docker.
if not BOT_TOKEN and not os.getenv("DJANGO_BUILD"):  # noqa: F405
    raise ImproperlyConfigured(
        "BOT_TOKEN must be set in production. "
        "Provide it via the .env.docker runtime file."
    )

# SITE_URL is required in production so Telegram alert links are absolute and
# correct. A dev-only default must not silently leak into prod traffic.
if not os.getenv("SITE_URL") and not os.getenv("DJANGO_BUILD"):  # noqa: F405
    raise ImproperlyConfigured(
        "SITE_URL must be set in production. "
        "Provide it via the .env.docker runtime file."
    )

# TLS-ready settings
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# Secure cookies
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# HSTS: one-year duration for production (defense-in-depth alongside nginx)
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Static files via whitenoise (with input.css excluded from post-processing)
STATICFILES_STORAGE = "theme.storage.ThemeStaticFilesStorage"

# Allow hosts from environment (required)
if not ALLOWED_HOSTS:  # noqa: F405
    raise ValueError("ALLOWED_HOSTS must be set in production")