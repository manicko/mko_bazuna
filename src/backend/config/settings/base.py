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

# Read .env file (django-environ uses python-dotenv internally)
# Fail fast if .env is missing (only in container environment)
env_path = BASE_DIR / ".env"
if not env_path.exists():
    # Skip validation during Docker build (DJANGO_BUILD), in test environments, or when
    # environment variables are provided via docker-compose env_file
    if os.getenv("DJANGO_SETTINGS_MODULE") and "test" not in os.getenv("DJANGO_SETTINGS_MODULE", "") and not os.getenv("DJANGO_BUILD"):
        logger.error("ERROR: .env file not found. Copy .env.example to .env and configure values.")
        sys.exit(1)
else:
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

# ALLOWED_HOSTS: split comma-separated values, empty defaults to ['']
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "").split(",") if os.getenv("ALLOWED_HOSTS", "") else []

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
CSRF_COOKIE_SECURE = True
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
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "apps.core.middleware.language.LanguagePreMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database - PostgreSQL ONLY (no SQLite fallback per zone C5)
# Use DATABASE_URL for 12-factor config (single source of truth)
# If DATABASE_URL is set, use it; otherwise fall back to discrete POSTGRES_* vars
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    # Parse DATABASE_URL using django-environ's built-in parsing
    DATABASES = {"default": env.db()}
    # PgBouncer async safety (zone C5) - only for PostgreSQL
    if "postgresql" in DATABASES["default"]["ENGINE"]:
        DATABASES["default"]["OPTIONS"] = {"prepare_threshold": None}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "mko_bazuna"),
            "USER": os.getenv("POSTGRES_USER", "postgres"),
            "PASSWORD": env("POSTGRES_PASSWORD"),
            "HOST": os.getenv("POSTGRES_HOST", "localhost"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
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
# Theme static files: src/theme/static (discovered by AppDirectoriesFinder
# via INSTALLED_APPS ["theme"]; not listed here to avoid duplicate collection)
STATICFILES_DIRS = [BASE_DIR.parent / "static"]

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

# Telegram Bot username for contact deep-links
# Format: without @ prefix, e.g., "MyBot" not "@MyBot"
BOT_USERNAME = os.getenv("BOT_USERNAME", "")

# Plausible analytics host (cookieless, no consent banner needed)
# Format: hostname only, e.g., "analytics.example.com" or "plausible.io"
PLAUSIBLE_HOST = os.getenv("PLAUSIBLE_HOST", "")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
