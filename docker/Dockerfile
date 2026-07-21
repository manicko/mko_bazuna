# Multi-stage Dockerfile for Mko Bazuna
# python:3.14-slim base with uv, non-root runtime, Tailwind build + collectstatic

################################################################################
# STAGE 1: Builder — install deps, build Tailwind, collectstatic
################################################################################
FROM python:3.14-slim AS builder

# Install build dependencies for psycopg3 and curl (for Tailwind CLI download in standalone mode)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv (pinned for reproducibility)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /

WORKDIR /app

# Cache: copy dependency files first (most stable layer)
COPY pyproject.toml uv.lock* ./

# Install dependencies to venv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv sync --frozen --no-install-project

# Copy source code
COPY . .

# Make the real source layout importable without repackaging the project.
# src/backend -> apps, config ; src -> telegram_bot
ENV PYTHONPATH=/app/src/backend:/app/src

# Build Tailwind CSS and collect static files
# TAILWIND_APP_NAME is the default theme app name for django-tailwind
ENV TAILWIND_APP_NAME=theme
ENV DJANGO_SETTINGS_MODULE=config.settings.prod
RUN uv run tailwind build && \
    uv run python src/backend/manage.py collectstatic --noinput


################################################################################
# STAGE 2: Production Runtime — non-root user, no build tools
################################################################################
FROM python:3.14-slim AS runtime

# Install runtime library for psycopg3
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user with uid 1000 (security baseline)
RUN groupadd -r -g 1000 app && \
    useradd -r -u 1000 -g app -d /app app && \
    mkdir -p /app/src /app/media /app/staticfiles && \
    chown -R app:app /app

WORKDIR /app

# Copy venv from builder (no gcc/libpq-dev in final image)
COPY --from=builder --chown=app:app /opt/venv /opt/venv
COPY --from=builder --chown=app:app /app/src /app/src
COPY --from=builder --chown=app:app /app/staticfiles /app/staticfiles

# Copy entrypoint scripts
COPY --chown=app:app docker/entrypoint.sh /app/entrypoint.sh
COPY --chown=app:app docker/entrypoint-test.sh /app/entrypoint-test.sh
COPY --chown=app:app docker/entrypoint-scheduler.sh /app/entrypoint-scheduler.sh
RUN chmod +x /app/entrypoint-test.sh /app/entrypoint-scheduler.sh

# Activate venv for all subsequent RUN/ENTRYPOINT
ENV PATH="/opt/venv/bin:$PATH"
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
# Make the real source layout importable at runtime (web/bot/migrate/scheduler)
ENV PYTHONPATH=/app/src/backend:/app/src

# Runtime volume for media (writable)
VOLUME ["/app/media"]

# Non-root execution
USER app

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
