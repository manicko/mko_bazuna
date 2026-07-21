"""
Production settings for Mko Bazuna.
Imports base settings and applies production safety configuration.
"""

from .base import *  # noqa: F403, F401

DEBUG = False

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

# Static files via whitenoise (for image)
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Allow hosts from environment (required)
if not ALLOWED_HOSTS:  # noqa: F405
    raise ValueError("ALLOWED_HOSTS must be set in production")