"""
Base Django settings for Mko Bazuna.
Shared across all environments (dev, prod, test).
"""

import logging
import os
import sys
from pathlib import Path

import environ

logger = logging.getLogger(__name__)

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

# Initialize django-environ
env = environ.Env(
    # Set casting & default values for environment variables
    DEBUG=(bool, False),
    # BOT_TOKEN: optional string (default empty for development)
    BOT_TOKEN=(str, ""),
)

# Read .env file using django-environ's own parser (which handles
# single-quoted values as literal, preventing "$VAR" interpolation).
# Fail fast if .env is missing (only in container environment)
env_path = BASE_DIR / ".env"
if not env_path.exists():
    # Skip validation during Docker build (DJANGO_BUILD), in test environments, or when
    # environment variables are provided via docker-compose env_file or CI directly.
    # The DJANGO_SECRET_KEY check covers CI where individual env vars are set explicitly
    # instead of via a .env file — this enables the secret-validation tests in
    # test_settings_secrets.py to run subprocesses with prod/dev settings modules.
    if (
        os.getenv("DJANGO_SETTINGS_MODULE")
        and "test" not in os.getenv("DJANGO_SETTINGS_MODULE", "")
        and not os.getenv("DJANGO_BUILD")
        and not os.getenv("DJANGO_SECRET_KEY")
    ):
        logger.error(
            "ERROR: .env file not found. Copy .env.dev.example to .env.dev and configure values."
        )
        sys.exit(1)
else:
    # In test environments, env vars are already injected via Docker Compose
    # env_file: into os.environ. Skip read_env() to prevent the bind-mounted
    # .env file from masking test cases that intentionally unset env vars
    # (e.g., test_django_secret_key_required expects ImproperlyConfigured
    # when DJANGO_SECRET_KEY is absent from os.environ).
    if "test" not in os.getenv("DJANGO_SETTINGS_MODULE", ""):
        environ.Env.read_env(env_path)

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/stable/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("DJANGO_SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DEBUG")

# Telegram bot token (required for bot process, validated via Env schema)
# Allow empty string for development when bot is not needed
BOT_TOKEN = env("BOT_TOKEN", default="")

# Google Cloud Translation API key (v2 Basic, API-key auth via ?key= query param).
# Used by the shared translation service and the backfill management command.
# Empty string default allows dev/test without the key (translations fall back to original text).
GOOGLE_TRANSLATE_API_KEY = env("GOOGLE_TRANSLATE_API_KEY", default="")

# ALLOWED_HOSTS: split comma-separated values, empty defaults to []
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

# Internationalization
LANGUAGE_CODE = "ru"
USE_I18N = True
LANGUAGES = [
    ("ru", "Russian"),
    ("bs", "Bosnian"),
    ("en", "English"),
]
LOCALE_PATHS = [BASE_DIR / "backend" / "locale"]

# Security settings (TLS/SSL ready)
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"

# Trusted origins for CSRF protection (Origin/Referer header validation).
# Required in production behind a TLS-terminating proxy (SECURE_PROXY_SSL_HEADER
# is set). Django has no W-series system check for this setting; the fail-fast
# guard in prod.py compensates by refusing to start without it.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# HSTS: nginx also emits this header; Django-level is defense-in-depth.
# Override in prod.py with a longer duration.
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "tailwind",
    "django_htmx",
    # MPTT for hierarchical categories
    "mptt",
    # Theme app for Tailwind
    "theme",
    # Local apps
    "apps.core",
    "apps.currencies",
    "apps.users",
    "apps.ads",
    "apps.categories",
    "apps.locations",
    "apps.moderation",
    "apps.search",
    "apps.media",
    "apps.lookups",
    "apps.trust",
    "apps.analytics",
    "apps.seed",
    "apps.cabinet",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middleware.language.LanguagePreMiddleware",
    "apps.core.middleware.city_resolution.CityResolutionMiddleware",
    "apps.core.middleware.preferred_city.PreferredCityMiddleware",
    "apps.core.middleware.js_check.JSExecutionMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "backend" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",
                "apps.core.context_processors.plausible_host",
                "apps.core.context_processors.language",
                "apps.core.context_processors.header_context",
                "apps.core.context_processors.js_verified",
                "apps.core.context_processors.site_config",
                "apps.core.context_processors.price_step",
                "apps.users.context_processors.consent_state",
                "apps.users.context_processors.consent_version",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database - PostgreSQL ONLY (no SQLite fallback per zone C5)
# Use DATABASE_URL for 12-factor config (single source of truth)
# If DATABASE_URL is set, use it; otherwise fall back to discrete POSTGRES_* vars
if os.getenv("DATABASE_URL"):
    # Parse DATABASE_URL using django-environ's built-in parsing
    DATABASES = {"default": env.db()}
    # PgBouncer async safety (zone C5) - only for PostgreSQL
    if "postgresql" in DATABASES["default"]["ENGINE"]:
        DATABASES["default"]["OPTIONS"] = {"prepare_threshold": None}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB", default="mko_bazuna"),
            "USER": env("POSTGRES_USER", default="postgres"),
            "PASSWORD": env("POSTGRES_PASSWORD"),
            "HOST": env("POSTGRES_HOST", default="localhost"),
            "PORT": env("POSTGRES_PORT", default="5432"),
            # PgBouncer async safety (zone C5)
            "CONN_MAX_AGE": 0,
            "OPTIONS": {
                "prepare_threshold": None,
            },
        }
    }

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
# STATIC_ROOT lives at /app/staticfiles so it matches the path copied out of the
# builder stage in docker/Dockerfile and served by whitenoise at runtime.
STATIC_ROOT = BASE_DIR.parent / "staticfiles"
# Theme static files live in src/theme/static and are discovered automatically
# via AppDirectoriesFinder through INSTALLED_APPS ["theme"].


# Media files
MEDIA_URL = "/media/"
# MEDIA_ROOT lives at /app/media so uploads land on the media_volume mount
# (media_volume:/app/media for web/bot, shared with nginx via media_volume).
MEDIA_ROOT = BASE_DIR.parent / "media"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom user model
AUTH_USER_MODEL = "users.User"

# Tailwind configuration
TAILWIND_APP_NAME = "theme"

# Storage contract for later S3 swap
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "theme.storage.ThemeStaticFilesStorage",
    },
}

# Login redirect
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
LOGIN_URL = "/login/issue/"

# Telegram Bot username for contact deep-links
# Format: without @ prefix, e.g., "MyBot" not "@MyBot"
BOT_USERNAME = env("BOT_USERNAME", default="")

# File-based liveness marker path for the bot container healthcheck.
# Written on startup, touched on each inbound update, removed on shutdown.
# See src/telegram_bot/lifecycle.py and docker/healthcheck-bot.sh (ENT-005).
BOT_LIVENESS_FILE = env("BOT_LIVENESS_FILE", default="/tmp/mko_bazuna_bot_alive")

# Public site URL used for absolute links (e.g. Telegram alert messages).
# Normalized to have no trailing slash. A sensible dev default is provided so
# dev/test absolute links never 500 (R10); production reads it from env.
SITE_URL = env.str("SITE_URL", default="http://localhost:8000").rstrip("/")

# Near-real-time publish-time alert delivery (AL-001). Default OFF so rollout
# is opt-in (CR15 / R1); the daily `send_alerts` command always backfills.
IMMEDIATE_ALERTS_ENABLED = env.bool("IMMEDIATE_ALERTS_ENABLED", default=False)

# Plausible analytics host (cookieless, no consent banner needed)
# Format: hostname only, e.g., "analytics.example.com" or "plausible.io"
PLAUSIBLE_HOST = env("PLAUSIBLE_HOST", default="")

# Sentry error-tracking DSN (optional). When set and DEBUG=False,
# sentry-sdk is initialized in prod.py to capture unhandled exceptions.
SENTRY_DSN = env("SENTRY_DSN", default="")

# Redis URL for shared caching and bot FSM storage.
# Production: REDIS_URL=redis://redis:6379/0 (set via env, single source of truth).
# Dev/test: REDIS_URL="" (empty) — CACHES is overridden in dev/test settings and
# main.py falls back to MemoryStorage when this is falsy.
REDIS_URL = env("REDIS_URL", default="")

# Cache configuration — shared cache via Redis (django-redis).
# Production and Docker environments use Redis so that cache keys and rate-limit
# counters are shared across gunicorn workers and the separate bot process.
# Dev/test settings override CACHES to LocMemCache (no Redis dependency).
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}
