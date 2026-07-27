# syntax=docker/dockerfile:1
# Multi-stage Dockerfile for Mko Bazuna
# python:3.14-slim base with uv, non-root runtime, Tailwind build + collectstatic

################################################################################
# STAGE 1: Builder — install deps, build Tailwind, collectstatic
################################################################################
FROM python:3.14-slim AS builder

# Install build dependencies for curl (for Tailwind CLI download in standalone mode)
# Note: gcc and libpq-dev removed - psycopg[binary] provides pre-compiled PostgreSQL driver
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    coreutils \
    && rm -rf /var/lib/apt/lists/*

# Install uv (pinned for reproducibility)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV PATH="/usr/local/bin:${PATH}"

# uv configuration for cache mount compatibility and runtime performance
# UV_LINK_MODE=copy prevents cross-filesystem link errors with cache mounts
ENV UV_LINK_MODE=copy
# UV_COMPILE_BYTECODE=1 pre-compiles .pyc files for faster container startup
ENV UV_COMPILE_BYTECODE=1

WORKDIR /app

# Cache: copy dependency files first (most stable layer)
COPY pyproject.toml uv.lock* ./

# Install dependencies to venv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --no-default-groups

# Install Tailwind CSS CLI (standalone binary)
RUN curl -L -o /usr/local/bin/tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64 && \
    chmod +x /usr/local/bin/tailwindcss && \
    tailwindcss --version

# Copy source code
COPY . .

# Make the real source layout importable without repackaging the project.
# src/backend -> apps, config ; src -> telegram_bot
ENV PYTHONPATH=/app/src/backend:/app/src

# Build Tailwind CSS and collect static files
# Use standalone tailwindcss CLI with explicit input/output paths
# Input: src/theme/static/theme/css/input.css (contains @tailwind directives)
# Output: src/theme/static/theme/css/output.css (collected to staticfiles/)
ENV DJANGO_SETTINGS_MODULE=config.settings.prod
# DJANGO_BUILD=1 skips .env validation during Docker build (collectstatic runs before runtime env is available)
ENV DJANGO_BUILD=1
# Placeholder values for required settings during build (real values provided at runtime via .env)
ENV DJANGO_SECRET_KEY=build-placeholder-do-not-use-in-production
ENV BOT_TOKEN=1234567890:build-placeholder-do-not-use-in-production
ENV ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
# Placeholder database URL for collectstatic (doesn't connect to DB but settings must be valid)
ENV DATABASE_URL=postgres://postgres:build-placeholder@localhost:5432/postgres
RUN tailwindcss -i src/theme/static/theme/css/input.css -o src/theme/static/theme/css/output.css --minify && \
    uv run python src/backend/manage.py collectstatic --noinput


################################################################################
# STAGE 2: Production Runtime — non-root user, no build tools
################################################################################
FROM python:3.14-slim AS runtime

# Install runtime library for psycopg3, curl (for health checks), and gettext (for compilemessages)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    ca-certificates \
    coreutils \
    gettext \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user with uid 1000 (security baseline)
RUN groupadd -r -g 1000 app && \
    useradd -r -u 1000 -g app -d /app app && \
    mkdir -p /app/src /app/media /app/staticfiles && \
    chown -R app:app /app

WORKDIR /app

# Copy venv from builder (no gcc/libpq-dev in final image)
COPY --from=builder --chown=app:app /opt/venv /opt/venv
# Copy tailwindcss binary from builder (needed for dev mode CSS generation)
COPY --from=builder /usr/local/bin/tailwindcss /usr/local/bin/tailwindcss
# Copy uv binary from builder (needed for dev mode `uv run` commands and entrypoint scripts)
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv
COPY --from=builder /usr/local/bin/uvx /usr/local/bin/uvx

# Copy source code (Django apps, config, telegram_bot)
COPY --from=builder --chown=app:app /app/src /app/src
# Copy collected static files
COPY --from=builder --chown=app:app /app/staticfiles /app/staticfiles

# Copy entrypoint scripts
COPY --chown=app:app docker/entrypoint*.sh /app/
RUN chmod +x /app/entrypoint*.sh

# Activate venv for all subsequent RUN/ENTRYPOINT
ENV PATH="/opt/venv/bin:${PATH}"
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
# uv configuration (consistent with builder stage)
ENV UV_LINK_MODE=copy
ENV UV_COMPILE_BYTECODE=1
# Make the real source layout importable at runtime (web/bot/migrate/scheduler)
ENV PYTHONPATH=/app/src/backend:/app/src

# Runtime volume for media (writable)
VOLUME ["/app/media"]

# Non-root execution
USER app

EXPOSE 8000

# Health check for container orchestration
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]