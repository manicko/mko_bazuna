"""
Base Django settings for Mko Bazuna.
Shared across all environments (dev, prod, test).
"""

import logging
import os
import sys
from pathlib import Path
from typing import Any

import environ

logger = logging.getLogger(__name__)

# Allowlist of environment variables that may be loaded from the .env file.
# Any .env key not listed here triggers a warning (Gate E, Option A) to surface
# typos like `BOT_T0KEN`. Includes both Python-consumed vars (env()/env.*()/
# os.getenv in base.py, prod.py and apps/core/utils/migrate_locked.py) and
# shell/entrypoint/compose-injected vars.
# The reverse direction is asserted by
# config/settings/tests/test_env_allowlist_reverse.py.
# Consequence: a new setting backed by env()/os.getenv keeps working locally but
# leaves the deployment contract, so the reverse AST gate fails until its
# variable name is added to the allowlist.
ALLOWED_ENV_VARS = frozenset({
    # --- Python-consumed (env()/env.*()/os.getenv in base.py, prod.py,
    #     apps/core/utils/migrate_locked.py) ---
    "DJANGO_SECRET_KEY", "DJANGO_SETTINGS_MODULE",
    "LOG_MASK_KEY",
    "DEBUG", "BOT_TOKEN", "GOOGLE_TRANSLATE_API_KEY",
    "BOT_TOKEN_REQUIRED",
    "ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS",
    "DATABASE_URL",
    "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST", "POSTGRES_PORT",
    "BOT_USERNAME", "BOT_LIVENESS_FILE", "BOT_HEALTH_STALE_SECONDS",
    "BOT_HEALTH_CHECK_ENABLED",
    "SCHEDULER_LIVENESS_FILE", "SCHEDULER_COMMAND_TIMEOUT", "SCHEDULER_HEALTH_STALE_SECONDS",
    "SITE_URL", "IMMEDIATE_ALERTS_ENABLED", "PLAUSIBLE_HOST", "SENTRY_DSN", "REDIS_URL",
    "EMAIL_HOST", "EMAIL_PORT", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD",
    "EMAIL_USE_TLS", "EMAIL_TIMEOUT", "EMAIL_BACKEND",
    "DEFAULT_FROM_EMAIL", "SUPPORT_NOTIFICATION_RECIPIENTS",
    "RUN_TRANSLATION_BACKFILL",
    "LOCK_TIMEOUT_SECONDS",
    "MEDIA_STAGING_BYTE_BUDGET",
    # --- Bootstrap control flags (honoured only from the process environment) ---
    # DJANGO_BUILD: Docker image builder stage only (collectstatic, no .env file).
    # DJANGO_ONESHOT: dev bootstrap one-shots, which run config.settings.oneshot.
    # Both are ignored by config.settings.prod; never add either to .env.prod.
    "DJANGO_BUILD", "DJANGO_ONESHOT",
    # --- Shell/entrypoint/compose-injected (not consumed by Python env()) ---
    # ADMIN_PASSWORD is the exception: create_admin_user reads it through
    # os.environ.get() rather than env(), and it arrives by env_file / Compose
    # environment:, not from the .env read above. It is therefore consumed (the
    # reverse AST scan reports it), just not by env().
    "ADMIN_USERNAME", "ADMIN_PASSWORD", "ADMIN_TELEGRAM_ID",
    "SEED_USERS", "SEED_ADS", "FIX_PERMISSIONS", "SKIP_ENV_CHECK",
    "TLS_CERT_PATH", "PROMETHEUS_MULTIPROC_DIR",
    "REGISTRY", "REPOSITORY", "IMAGE_TAG",
})


def _warn_unknown_env_vars(loaded_keys: set[str]) -> None:
    """Log a warning for env vars loaded from .env not in ALLOWED_ENV_VARS.

    Uses an os.environ pre/post diff (not os.environ directly) so inherited OS
    env vars (PATH, HOME, etc.) and compose-injected vars already present before
    read_env() are never flagged. Non-fatal by design (Gate E Option A).
    """
    unknown = loaded_keys - ALLOWED_ENV_VARS
    for key in sorted(unknown):
        logger.warning(
            "Unknown env var '%s' loaded from .env — not in ALLOWED_ENV_VARS "
            "(possible typo; value will be ignored by env() calls). "
            "If this is intentional, add it to ALLOWED_ENV_VARS in base.py.",
            key,
        )


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
        and os.getenv("DJANGO_SECRET_KEY") is None
    ):
        _env_file_name = (
            ".env.prod"
            if os.getenv("DJANGO_SETTINGS_MODULE", "").endswith(".prod")
            else ".env.dev"
        )
        logger.error(
            "ERROR: .env file not found. Copy .env.dev.example to %s "
            "and configure values.",
            _env_file_name,
        )
        sys.exit(1)
else:
    # In test environments, env vars are already injected via Docker Compose
    # env_file: into os.environ. Skip read_env() to prevent the bind-mounted
    # .env file from masking test cases that intentionally unset env vars
    # (e.g., test_django_secret_key_required expects ImproperlyConfigured
    # when DJANGO_SECRET_KEY is absent from os.environ).
    if "test" not in os.getenv("DJANGO_SETTINGS_MODULE", ""):
        _env_keys_before = set(os.environ)
        environ.Env.read_env(env_path)
        _warn_unknown_env_vars(set(os.environ) - _env_keys_before)

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/stable/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("DJANGO_SECRET_KEY")

# HMAC key for the Telegram-ID log mask (apps/core/utils/sanitize.py). Required
# in production - guard-enforced in prod.py. Independent of SECRET_KEY on
# purpose: reusing SECRET_KEY would give one leak two blast radii and no scoped
# revocation. Empty in non-production is deliberate; see _resolve_log_mask_key.
LOG_MASK_KEY = env("LOG_MASK_KEY", default="")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DEBUG")

# Telegram bot token (required for bot process). The env(...) entry above declares
# a cast and a default, not a schema: the actual placeholder/dummy validation lives
# in config/settings/secret_validation.py and is applied by the guard in
# config/settings/prod.py. Allow empty string for development when bot is not
# needed; production requires it.
BOT_TOKEN = env("BOT_TOKEN", default="")

# Google Cloud Translation API key (v2 Basic, API-key auth via ?key= query param).
# Used by the shared translation service and the backfill management command.
# Empty string default allows dev/test without the key (translations fall back to original text).
GOOGLE_TRANSLATE_API_KEY = env("GOOGLE_TRANSLATE_API_KEY", default="")

# ALLOWED_HOSTS: split comma-separated values, empty defaults to []
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

# Internationalization
LANGUAGE_CODE = "ru"
# Hard-coded literal, NOT read through ``env()``: the Product Owner ruling of
# 2026-10-03 (Q4) fixed the marketplace's display timezone as Europe/Podgorica
# and closed the env-overridability branch. There is deliberately no
# ALLOWED_ENV_VARS entry and no .env*.example line. USE_TZ stays Django's
# default (True), so stored timestamps are aware and only presentation moves.
TIME_ZONE = "Europe/Podgorica"
USE_I18N = True
LANGUAGES = [
    ("ru", "Russian"),
    ("bs", "Bosnian"),
    ("en", "English"),
]
LOCALE_PATHS = [BASE_DIR / "backend" / "locale"]

# Project-level format overrides, resolved per-attribute ahead of Django's
# bundled locale data (14-I18N-003 / Q3 option (a)). Django's bundled Bosnian
# locale defines DECIMAL_SEPARATOR and THOUSAND_SEPARATOR but leaves
# NUMBER_GROUPING commented out, and ``django.utils.numberformat`` gates
# grouping on ``grouping != 0``; a missing value defaults to 0, so ``bs``
# thousands grouping is unreachable even under ``force_grouping=True``.
# ``config.locale_formats.bs.formats`` supplies NUMBER_GROUPING = 3, while every
# other attribute still falls through to django.conf.locale.bs.formats — Django
# resolves each format attribute against the first module that defines it. It is
# a list of dotted module paths, never Path objects.
FORMAT_MODULE_PATH = ["config.locale_formats"]

# Security settings (TLS/SSL ready)
# The cookie-secure overrides in dev.py/test.py are development-only relaxations
# of these production defaults.
# Session cookie: sent only over HTTPS, so a network observer cannot read the
# session id off the wire. Deliberate production default; the block header above
# records the only relaxations.
SESSION_COOKIE_SECURE = True
# Session cookie: hidden from document.cookie, so an XSS payload cannot read the
# session id through the DOM.
SESSION_COOKIE_HTTPONLY = True
# Session cookie: "Lax" withholds the cookie from cross-site subrequests (a CSRF
# defence) while still permitting top-level GET navigations. The Telegram login
# return does NOT depend on that allowance: login_status is @require_POST and the
# page's return is a same-origin fetch() POST from login_issue.html, so it is
# same-site and the cookie is sent under any SameSite value (GET /login/status/
# is pinned 405). The only cross-site top-level navigation in the flow is the tap
# out to t.me, which carries no site cookies. "Lax" matches Django's default and
# remains a deliberate choice; SameSite=Strict or False would change nothing here.
SESSION_COOKIE_SAMESITE = "Lax"
# Session lifetime and refresh policy, declared explicitly so the policy is
# visible rather than implicit. 60 * 60 * 24 * 14 = 1209600 seconds (14 days),
# which matches Django's inherited default; it is written out here on purpose so
# the window is a visible product decision instead of an invisible framework
# default. A literal, not an env-driven value: the comparable bounds in this
# codebase that are literals stay literal (TOKEN_TTL_SECONDS, RATE_LIMIT_REQUESTS,
# _MAX_HISTORY, DAILY_HOUR_UTC, SECURE_HSTS_SECONDS), so an operator-variable
# window would be the odd one out and would let the effective exposure be changed
# from outside the repository. LOCK_TIMEOUT_SECONDS is deliberately NOT cited as
# precedent: it is env.int("LOCK_TIMEOUT_SECONDS", default=10), i.e.
# operator-tunable, and it is the closest analogue to an operator-variable bound.
#
# SESSION_SAVE_EVERY_REQUEST stays False: the lifetime is write-triggered, not
# sliding. Django saves the session only when (modified or SAVE_EVERY_REQUEST)
# and not empty, so expire_date moves only on a real write. For an authenticated
# user those writes are auth_login() at login and the ?lang= language switch;
# ordinary reads never re-stamp the row. Turning this on would not extend a
# login-once seller's window (no reads happen) and would STRICTLY INCREASE the
# exposure of a user who keeps browsing, because every read would re-stamp the
# newest-to-expire sessions. The anti-theft benefit is a function of the window's
# age, not of the flag.
#
# No number for this setting pre-existed: it was not specified in the spec, the
# code or any .env template; 14 days matches Django's own default rather than
# being a figure the repository computed. Choosing the number is therefore a
# product decision, not a derivable engineering constant. The spec now states the
# number, so changing the value here requires a paired edit to
# docs/01-spec/technical-specification.md section H.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # 1209600 seconds (14 days)
SESSION_SAVE_EVERY_REQUEST = False
# CSRF token cookie: sent only over HTTPS, so the token cannot be replayed from
# a plain-HTTP downgrade.
CSRF_COOKIE_SECURE = True
# CSRF token cookie: hidden from document.cookie, so the token is never readable
# from the DOM. The template delivers it instead — into forms via {% csrf_token %}
# and into login_issue.html's poll request as the X-CSRFToken header (the masked
# csrfmiddlewaretoken form field also rides the POST body), never via
# document.cookie. Left this way because CSRF_USE_SESSIONS is unset: the token
# stays a cookie, not session state.
CSRF_COOKIE_HTTPONLY = True
# CSRF token cookie: "Lax" allows the token on top-level cross-site navigations
# and withholds it on cross-site subrequests.
CSRF_COOKIE_SAMESITE = "Lax"
# The login-binding cookie's ``__Host-`` prefix. This one setting resolves BOTH
# the cookie's name and its ``Secure`` flag (see login_token.py): when True the
# emitted cookie is ``__Host-login_browser_id`` with ``Secure``; when False it is
# plain ``login_browser_id`` with no ``Secure``. The two must never disagree — a
# ``__Host-`` cookie without ``Secure`` is discarded by every conformant user
# agent, so the login cookie vanishes and every login becomes a 410 — which is
# why they are derived from a single setting rather than configured separately.
#
# It lives in the transport tuple, not hardcoded in the view, so it is subject to
# the same machine-checked dev/test parity as the two cookie-secure settings above
# (test_settings_defaults.test_dev_and_test_share_the_transport_tuple). It is a
# deliberate settings flag rather than ``request.is_secure()``: behind a
# misconfigured SECURE_PROXY_SSL_HEADER the request-derived form silently drops
# the prefix to off in production, which a fixed setting cannot do. On an
# HTTP-only origin the prefix control is absent by design (there is no transport
# security to anchor it to), not by oversight.
#
# Why the ``__Host-`` prefix matters: without it a sibling host on the same
# registrable domain could set a ``Domain``-scoped cookie of the same name and
# supply the client-chosen value the binding gate compares against. The prefix
# restricts the cookie to a host-only, ``Secure``, ``Path=/`` origin; the full
# rationale is in login_token.py.
LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX = True

# Trusted origins for CSRF protection (Origin/Referer header validation).
# Required in production behind a TLS-terminating proxy (SECURE_PROXY_SSL_HEADER
# is set). Django has no W-series system check for this setting; the fail-fast
# guard in prod.py compensates by refusing to start without it.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# Networks whose direct peer may be trusted to set the client-IP forwarding
# headers X-Real-IP / X-Forwarded-For (see apps/core/utils/client_ip.py). A peer
# that is loopback or private is ALWAYS trusted; entries here extend that trust
# to a proxy reached across a non-private hop. Deliberately a literal, not an
# env-driven value: no compose file declares `networks:`, so nginx's container
# address is Docker-allocated and per-deployment, which means there is no correct
# value an operator could supply from inside the repo. Empty by default.
TRUSTED_PROXY_NETWORKS: tuple[str, ...] = ()

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
    # Prometheus metrics (django-prometheus)
    "django_prometheus",
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
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "apps.core.middleware.db_lock_timeout.DbLockTimeoutMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middleware.language.LanguagePreMiddleware",
    "apps.core.middleware.city_resolution.CityResolutionMiddleware",
    "apps.core.middleware.preferred_city.PreferredCityMiddleware",
    "apps.core.middleware.js_check.JSExecutionMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
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

# Bound on how long any statement waits for a row, table or advisory lock
# (03-DB-004, timeout half). This is the ONLY bound on lock waits in the whole
# system: without it a contended lock stalls a gunicorn worker until its 60 s
# SIGKILL and parks the bot's single asgiref thread_sensitive worker behind every
# other ORM call. Removing this setting is a regression, and
# docs/02-database/db-retention.md documents it.
#
# The value is in SECONDS and is rendered with an explicit "s" suffix below,
# because a bare PostgreSQL GUC number is interpreted as MILLISECONDS — the
# suffix makes a 1000x unit error inexpressible through this API. The valid range
# for this constant is 0.._MAX_LOCK_TIMEOUT_SECONDS SECONDS (server-side the GUC
# accepts 0..2147483647 MILLISECONDS); 0 disables the bound. A value outside the
# range is clamped in ``_db_options``: a negative one to 0, because PostgreSQL
# would otherwise FATAL every process at boot ("outside the valid range for
# parameter \"lock_timeout\""), and one above the maximum down to it, so a typo
# (e.g. ``10000`` for 10 s) cannot turn every lock wait into a multi-minute stall
# that defeats the bound's purpose. It is a CONNECT-TIME setting, not a
# per-command one, so it also bounds pg_advisory_xact_lock and the login
# UPDATE ... RETURNING row lock.
LOCK_TIMEOUT_SECONDS: int = env.int("LOCK_TIMEOUT_SECONDS", default=10)

# Ceiling for LOCK_TIMEOUT_SECONDS. The bound exists to fail fast under
# contention; a multi-minute value is indistinguishable from "no bound" for every
# caller that owns a request, a gunicorn worker or the bot's single asgiref
# thread_sensitive worker.
_MAX_LOCK_TIMEOUT_SECONDS: int = 600


def _db_options() -> dict[str, Any]:
    """psycopg connection OPTIONS shared by BOTH DATABASES branches.

    ``prepare_threshold=None`` — PgBouncer async safety (zone C5).
    ``options`` — libpq's startup-packet run-time options. ``lock_timeout``
    bounds every wait for a row, table or advisory lock (03-DB-004 timeout
    half). The explicit ``s`` suffix is load-bearing: a bare GUC number is
    MILLISECONDS. ``0`` disables the bound and is the only disabling value; a
    value below 0 is clamped to ``0`` (a negative ``lock_timeout`` FATALs every
    process at boot) and one above ``_MAX_LOCK_TIMEOUT_SECONDS`` down to it, so a
    unit-typo cannot make every wait multi-minute.

    Both branches must call this helper: the DATABASE_URL branch REPLACES
    ``env.db()``'s OPTIONS wholesale (which is also why any ``?options=-c ...``
    in DATABASE_URL is silently clobbered), so a key added to only one branch
    would be absent in the other. Under PgBouncer transaction pooling the
    ``options`` startup parameter is only accepted when the pooler lists it in
    ``ignore_startup_parameters`` (see docker-compose.prod.yml) — but the pooler
    then discards it, dropping this bound; the bound only survives a pooler via
    a server-side ``lock_timeout`` default.
    """
    return {
        "prepare_threshold": None,
        "options": (
            f"-c lock_timeout="
            f"{min(max(LOCK_TIMEOUT_SECONDS, 0), _MAX_LOCK_TIMEOUT_SECONDS)}s"
        ),
    }


if os.getenv("DATABASE_URL"):
    # Parse DATABASE_URL using django-environ's built-in parsing
    DATABASES = {"default": env.db()}
    # PgBouncer async safety (zone C5) - only for PostgreSQL
    if "postgresql" in DATABASES["default"]["ENGINE"]:
        DATABASES["default"]["OPTIONS"] = _db_options()
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
            "OPTIONS": _db_options(),
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

# Global byte budget for the in-flight upload area (MEDIA_ROOT/staging/).
#
# Nothing else bounds the total bytes in ``staging/``: the only reclamation is
# the 2 h mtime TTL in ``sweep_orphaned_media`` and the FSM-skip reclaim, so a
# burst of uploads (many photos, or many sellers at once) can fill the media
# volume before either runs and take the whole site down.  This setting is the
# primary space control; the TTL stays the backstop.
#
# The budget is necessarily GLOBAL, not per seller.  Staging keys are minted by
# ``generate_storage_key()`` as ``<uuid4>.jpg`` — deliberately PII-free — so no
# attribute of a staged file identifies its owner, and per-seller attribution
# would require a key-format change that breaks unguessability and every key
# ``CheckConstraint``.  The accepted trade-off: one abusive account can exhaust
# the shared budget and cause a legitimate seller's upload to be refused.
#
# 2 GiB bounds the arithmetic it must cover.  ``MAX_PHOTO_BYTES`` is 2 MB per
# photo, the FSM caps a dialog at 5 photos, and the rate limiter allows 10
# uploads / 60 s per seller: one account can accumulate ~2.4 GB inside a single
# 2 h TTL window.  2 GiB stops a single account before the TTL would, and it is
# ~180 fully-staged dialogs (≈11 MB each) of legitimate headroom.  Env-
# overridable so an operator can raise it without a code change.
MEDIA_STAGING_BYTE_BUDGET = int(
    os.environ.get("MEDIA_STAGING_BYTE_BUDGET", 2 * 1024 * 1024 * 1024)
)

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

# Password policy enforced by django.contrib.auth.password_validation. The policy
# applies wherever Django validates a password: the admin add view
# (UserCreationForm) and the bootstrap path (create_admin_user). The minimum
# length is a literal, not an environment variable, so the setting stays free of
# the env-allowlist contract (CFG, test_env_allowlist_reverse.py).
AUTH_PASSWORD_VALIDATORS = [
    {
        # Rejects a password too similar to the username/email: blocks a
        # credential built from the account identifier itself. On the bootstrap
        # path this only fires because create_admin_user passes an unpersisted
        # candidate user to validate_password; with no user it is inert.
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        # Rejects a password shorter than the minimum. 10 is the shortest value
        # that clears trivial guesses while staying memorable for a bootstrap
        # credential; the default of 8 is too weak for an operator secret.
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {
        # Rejects passwords on Django's common-password list: blocks well-known
        # leaked credentials.
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        # Rejects all-numeric passwords: blocks PIN-like credentials with no
        # character variety.
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Telegram Bot username for contact deep-links
# Format: without @ prefix, e.g., "MyBot" not "@MyBot"
# Required and non-empty in production. This is a SEED value: migration
# 0003_add_bot_username copies it into SiteConfig.bot_username once, and from then
# on the database is the source of truth (get_bot_username() reads the model, not
# this setting), so changing it later does not change a deployed site. Use
# `manage.py repair_bot_username` or the Django admin to correct a stored value.
BOT_USERNAME = env("BOT_USERNAME", default="")

# File-based liveness marker path for the bot container healthcheck.
# Written on startup, touched on each inbound update, removed on shutdown.
# See src/telegram_bot/lifecycle.py and docker/healthcheck-bot.sh (ENT-005).
# `# nosec B108`: this is a fixed private filename inside the container's tmpfs,
# not a predictable-name temp file with an untrusted writer. The path is read by
# docker/healthcheck-bot.sh, which ships the same `/tmp/...` default, so it must
# not change here (12-OPS-001).
BOT_LIVENESS_FILE = env("BOT_LIVENESS_FILE", default="/tmp/mko_bazuna_bot_alive")  # nosec B108

# Redis-based bot liveness marker (shared cache key written by the bot process).
# The web readiness probe reads this key to verify the bot is alive and fresh.
# TTL matches the staleness window; the value is an epoch timestamp so staleness
# can be computed precisely before the key naturally expires.
BOT_HEALTH_STALE_SECONDS = env.int("BOT_HEALTH_STALE_SECONDS", default=120)

# When True, the web readiness probe also verifies the Redis bot:liveness marker
# and gates web readiness on it. Defaults to False so web readiness is decoupled
# from bot liveness: when False (the default), the probe reports
# checks["bot"] == "disabled" and does not gate web readiness on the bot. Set
# True explicitly (e.g. via env var) to opt back into the coupling. The bot has
# its own independent file-based healthcheck (BOT_LIVENESS_FILE) as its separate
# alert mechanism.
BOT_HEALTH_CHECK_ENABLED = env.bool("BOT_HEALTH_CHECK_ENABLED", default=False)

# File-based liveness marker path for the scheduler container healthcheck.
# Written after each successful hourly cycle, touched on each tick.
# Read by docker/healthcheck-scheduler.sh (added in Block D).
# `# nosec B108`: fixed private filename in tmpfs, not a predictable temp file;
# docker/healthcheck-scheduler.sh ships the same default (12-OPS-001).
SCHEDULER_LIVENESS_FILE = env("SCHEDULER_LIVENESS_FILE", default="/tmp/mko_bazuna_scheduler_alive")  # nosec B108

# Per-command timeout (seconds) for the scheduler subprocess dispatch. Guards
# against a hung management command stalling the whole cycle (ENT-001).
# 1800 = 30 min, safely under the healthcheck staleness window (7200).
SCHEDULER_COMMAND_TIMEOUT = env.int("SCHEDULER_COMMAND_TIMEOUT", default=1800)

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

# ---------------------------------------------------------------------------
# Email / SMTP configuration (classic Django EMAIL_* settings)
# ---------------------------------------------------------------------------
# Production (prod.py) warns loudly when EMAIL_HOST is empty, then boots and
# serves normally — the support-desk e-mail path fails open. Dev and test
# environments override EMAIL_BACKEND to console/locmem backends that do not
# require SMTP connectivity (see dev.py and test.py).
# The mail path serves exactly one purpose: the Telegram support-ticket
# notification in telegram_bot/services/support_delivery_email.py, which is the
# only send_mail call site in the codebase. There is no password-reset,
# alert-notification or seller-confirmation flow, so do not build one assuming
# this plumbing already exists.
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=10)
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.smtp.EmailBackend",
)
DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL", default="noreply@" + env("SITE_URL", default="localhost")
)
# Support notification recipients — admin email addresses that support
# notifications are delivered to. Optional list; empty in dev/test by default.
SUPPORT_NOTIFICATION_RECIPIENTS = env.list(
    "SUPPORT_NOTIFICATION_RECIPIENTS", default=[]
)
