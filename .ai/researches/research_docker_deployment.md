# Research Report: Docker Deployment Static Files Analysis

## 1. Docker Entrypoint Scripts

### entrypoint.sh (main)
- Performs health checks for .env file
- Fixes volume permissions in dev mode (DEBUG=True or FIX_PERMISSIONS=1)
- Waits for database to be ready (max 30 seconds)
- Executes the command passed to container

### entrypoint-create-admin.sh
- One-shot service for creating admin user
- Skips execution if ADMIN_PASSWORD is empty
- Runs: `python src/backend/manage.py create_admin_user --username admin --password <pwd> --telegram-id <id>`

### entrypoint-scheduler.sh
- Runs management commands in hourly loop
- Commands: archive_sweep, delete_sweep, consent_hard_delete, sweep_drafts, cleanup_login_tokens, purge_failed_ads, purge_rejected_ads
- Gated by `profiles: ["scheduler"]` to prevent import crashes

### entrypoint-test.sh
- Runs migrations then pytest in ephemeral PostgreSQL
- Waits for DB to be ready (max 30 seconds)

## 2. Docker Compose Files Analysis

### docker-compose.yml (Base)
- Services: db, migrate, web, bot, nginx, create_admin
- Static files served by whitenoise in Django image
- Media served by nginx from media_volume
- Uses .env.docker for environment
- One-shot services with advisory locks for migrations and admin creation

### docker-compose.dev.override.yml (Development)
- Enables hot-reloading with bind-mounts (`.:/app`)
- Uses `python src/backend/manage.py runserver` instead of gunicorn
- DEBUG=True and DJANGO_SETTINGS_MODULE=config.settings.dev

### docker-compose.prod.yml (Production)
- Adds TLS certificate mounting
- Adds scheduler service (profile: scheduler)
- Adds backup service (profile: backup) - daily PostgreSQL dumps with 7-day retention
- Adds pgbouncer service (profile: pgbouncer) for connection pooling

## 3. Tailwind Build and collectstatic Process

### Build Process (Dockerfile builder stage, lines 65-85)
```dockerfile
ENV TAILWIND_APP_NAME=theme
ENV DJANGO_SETTINGS_MODULE=config.settings.prod
ENV DJANGO_BUILD=1
ENV DJANGO_SECRET_KEY=build-placeholder-do-not-use-in-production
ENV BOT_TOKEN=1234567890:build-placeholder-do-not-use-in-production
ENV ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
ENV DATABASE_URL=postgres://postgres:build-placeholder@localhost:5432/postgres

RUN tailwindcss build && \
    uv run python src/backend/manage.py collectstatic --noinput
```

### Critical Build Issues
1. **tailwindcss CLI installed** but build command is incomplete
2. **No tailwind.config.js** provided to CLI for input/output paths
3. **Direct tailwindcss build call** without Django management command
4. **No output.css generated** - this is the root cause

## 4. Expected output.css Location in Container

### Production Path
- **Expected**: `/app/staticfiles/css/output.css`
- **Runtime copy**: `COPY --from=builder --chown=app:app /app/staticfiles /app/staticfiles`

### Build Source
- **Input**: `/app/src/theme/static/theme/css/input.css`
- **Template references**: `{% static 'css/output.css' %}`

### Problem
- `output.css` does NOT exist after build
- `staticfiles/css/` directory is not created
- Collectstatic has nothing to collect

## 5. Nginx Static File Serving

### Current Configuration
```nginx
location /static/ {
    proxy_pass http://web:8000/static/;
    expires 30d;
    add_header Cache-Control "public, immutable";
}
```

### Issue
- Nginx proxies static requests to Django
- Django's whitenoise serves static files
- **BUT**: No CSS files exist in staticfiles/ to serve