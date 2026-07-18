# Production Docker Environment Research (Researcher #3)

**Scope:** Production deployment topology, security hardening, data persistence, and operational concerns for the mko_bazuna classified ads platform running fully inside Docker containers.  
**Angle:** Prod topology (db + web + bot + nginx), TLS termination, media endpoint hardening, secrets management, Postgres backup/restore, PgBouncer pooling, scheduled jobs execution, logging, restart policies, and resource sizing for ~300 users/day with <2s response requirement.

---

## 1. Constraints Extracted from Wiki

| Source File | Section/Zone | Constraint |
|-------------|--------------|------------|
| `01_technical_specification.md` | Decision F (zone R1) | PII hard-delete 30 days after consent revocation via background job; analytics_events.user_id SET NULL on erasure |
| `01_technical_specification.md` | Decision E (zone R6) | Media URLs contain no PII — keys are UUID v4 only, no user_id/telegram_id/username in image paths |
| `01_technical_specification.md` | Decision E (zone R8) | Media endpoint hardening: script execution blocked, X-Content-Type-Options: nosniff, image/jpeg whitelist, Content-Disposition: inline |
| `02_packages.md` | Zone C5 | PgBouncer in transaction mode recommended as shared pool between web+bot; CONN_MAX_AGE=0 per process |
| `02_packages.md` | Zone C5 | Gunicorn sync WSGI for phase-1 (NOT ASGI) |
| `03_structure.md` | Deployment section | Services: db + web + bot + nginx; volumes: postgres_data, media_volume, static_volume; nginx obligatory |
| `03_structure.md` | NGINX hardening (zone R8) | `location ~* /media/.*\.(php|py|cgi)$ { deny all; }` + header hardening |
| `03_structure.md` | Django settings | USE_X_FORWARDED_HOST=True, SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https'), SECURE_SSL_REDIRECT=True |
| `03_structure.md` | PgBouncer | Shared pool in transaction mode; each process CONN_MAX_AGE=0 |
| `03_structure.md` | Migrations | Must run once before both web and bot start (dedicated step / ordering guard) |
| `03_structure.md` | Secrets | .env via env_file; Docker secrets later at orchestration |
| `02_packages.md` | Analytics (Decision L) | Plausible cookieless web analytics; self-host fallback via Docker; PII-free events |
| `04_db_structure.md` | AdStatus lifecycle | DRAFT → ON_MODERATION → PUBLISHED; archive@2mo, delete@4mo, 7-day purge for failed moderation, 30-day hard-delete for consent |
| `01_technical_specification.md` | Decision L | Plausible/Umami self-host via Docker fallback |

---

## 2. Detailed Findings & Recommended Approach

### 2.1 Production Compose Topology

The MVP production topology requires **four services** isolated from each other, with nginx as the sole public entry point:

```
                           ┌─────────────┐
                           │   nginx     │
                           │ (TLS + /static/ + /media/)
                           └──────┬──────┘
                                  │
           ┌──────────────────────┴──────────────────────┐
           │                                           │
           ▼                                           ▼
    ┌─────────────┐                              ┌─────────────┐
    │    web      │                              │    bot      │
    │ (gunicorn   │                              │ (aiogram 3.x)│
    │  sync WSGI) │                              └─────────────┘
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │ pgBouncer   │  (transaction mode pool)
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │    db       │
    │ (postgres:17)│
    │ named volume  │
    └─────────────┘
```

**Key architectural decisions:**
- **nginx is mandatory** (per structure.md:94) — whitenoise cannot serve user-uploaded media
- **Gunicorn sync WSGI** (per packages.md:8, structure.md:85) — ASGI reserved for future
- **PgBouncer as transaction-mode pool** (per packages.md:9, structure.md:104)
- **Healthchecks required** on db and web services for proper startup sequencing

### 2.2 Nginx Configuration (TLS + Media Hardening + Reverse Proxy)

**Illustrative configuration (`/docker/nginx/nginx.conf`):**

```nginx
# nginx.conf - Production TLS termination
server {
    listen 80;
    server_name _;
    # Redirect all HTTP to HTTPS (handled by Certbot)
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name classifieds.example.com;

    # TLS (Let's Encrypt via Certbot)
    ssl_certificate /etc/letsencrypt/live/classifieds.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/classifieds.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;

    # Static files - served directly
    location /static/ {
        alias /static_volume/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Media files - hardened per zone R8
    location /media/ {
        alias /media_volume/;
        
        # Zone R8: Block script execution
        location ~* /media/.*\.(php|py|cgi|pl|sh)$ {
            deny all;
            return 403;
        }

        # Zone R8: Security headers
        add_header X-Content-Type-Options nosniff always;
        add_header X-Frame-Options DENY always;
        add_header Content-Security-Policy "default-src 'none'; img-src 'self' data:; object-src 'none'" always;
        
        # MIME type whitelist - images only
        types {
            image/jpeg jpg jpeg;
            image/png png;
            image/webp webp;
        }
        default_type application/octet-stream;
        
        # Zone R8: Content-Disposition inline
        add_header Content-Disposition inline;
        
        # Cache static assets
        expires 7d;
        add_header Cache-Control "public";
    }

    # Reverse proxy to Django
    location / {
        proxy_pass http://web:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Django proxy header settings (per structure.md:98)
        proxy_set_header X-Forwarded-Host $host;
    }
}
```

**Certbot integration in docker-compose:**

```yaml
  certbot:
    image: certbot/certbot
    restart: unless-stopped
    volumes:
      - certbot_www:/var/www/certbot
      - nginx_certbot_socket:/var/run/certbot
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew --webroot -w /var/www/certbot; sleep 12h & wait $${!}; done'"
```

### 2.3 Secrets Management Strategy

**Two-phase approach:**

1. **Phase 1 (MVP):** Environment variables via `.env` file with `env_file` in docker-compose
   - Required secrets: `BOT_TOKEN`, `DJANGO_SECRET_KEY`, `DATABASE_PASSWORD`, `POSTGRES_PASSWORD`
   - `.env` mounted at runtime, never committed to git (use `.env.example`)

2. **Phase 2 (Production hardening):** Docker secrets via bind mounts or Swarm/K8s secrets
   - `/run/secrets/postgres_password` → `POSTGRES_PASSWORD_FILE`
   - `/run/secrets/django_secret_key` → `DJANGO_SECRET_KEY_FILE`
   - Per structure.md:106: "позже — Docker secrets при оркестрации"

**Critical constraint:** API_ID/API_HASH are NOT required in phase 1 (aiogram Bot API only, per structure.md:106). Remove these from `.env.example` to avoid confusion.

### 2.4 Postgres Volume + Backup/Restore Strategy

**Volume configuration:**

```yaml
volumes:
  postgres_data:
    driver: local
    name: mko_bazuna_postgres_data
```

**Backup approach (MVP-sized):**

1. **Daily logical backups** using `pg_dump` in a side container:
   ```yaml
   pgbackup:
     image: postgres:17-alpine
     volumes:
       - postgres_data:/var/lib/postgresql/data
       - ./backups:/backups
     entrypoint: [
       "/bin/sh", "-c",
       "pg_dump -h db -U $$POSTGRES_USER -d $$POSTGRES_DB > /backups/dump_$$(date +%Y%m%d).sql"
     ]
     depends_on:
       - db
   ```

2. **Backup retention:** Keep 7 daily backups (simple rotation script)

3. **Restore procedure:**
   - Stop all Django-requiring services
   - `docker-compose exec -T db psql -U postgres -d classifieds < backup.sql`
   - Or for volume restore: detach volume, replace, reattach

4. **Point-in-time recovery:** Reserved for phase 2 (requires WAL archiving)

### 2.5 PgBouncer Placement and Configuration

**Recommended placement:** Dedicated service between web/bot and db, in transaction mode:

```yaml
services:
  pgbouncer:
    image: bitnami/pgbouncer:1.5
    restart: unless-stopped
    environment:
      - POSTGRESPASSWORD=${POSTGRES_PASSWORD}
      - PGBOUNCER_DATABASE=${POSTGRES_DB}
      - PGBOUNCER_PORT=6432
      - PGBOUNCER_USERNAME=${POSTGRES_USER}
      - PGBOUNCER_AUTH_type=md5
    ports:
      - "6432:6432"
    depends_on:
      - db
    healthcheck:
      test: ["CMD", "pg_isready", "-h", "localhost", "-p", "6432"]
      interval: 10s
      timeout: 5s
```

**Django settings for PgBouncer (per packages.md:9):**

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'CONN_MAX_AGE': 0,  # Required per C5 for PgBouncer transaction mode
        # ... other connection settings via env
    }
}
```

### 2.6 Scheduled Jobs in Docker (MVP Approach)

**Constraint (per packages.md:8):** Phase-1 jobs run as Django management commands via systemd timer/cron.

**Problem:** How to run cron inside Docker vs host?

**Recommendation (MVP):** Dedicated lightweight cron container that shares network and mounts:

```yaml
services:
  scheduler:
    build:
      context: .
      dockerfile: docker/Dockerfile
    command: [
      "/bin/sh", "-c",
      "while true; do
         # Archive sweep (2mo)
         uv run python src/backend/manage.py archive_ads;
         # Delete sweep (4mo)  
         uv run python src/backend/manage.py delete_archived_ads;
         # 7-day purge for failed moderation
         uv run python src/backend/manage.py purge_failed_moderation;
         # 30-day consent hard-delete (R1)
         uv run python src/backend/manage.py hard_delete_erased_users;
         # 30-min draft sweep
         uv run python src/backend/manage.py sweep_drafts --minutes=30;
         sleep 3600;  # Run hourly, sweep_drafts handles 30-min logic
       done"
    ]
    depends_on:
      - web
    env_file:
      - .env
    restart: unless-stopped
```

**Jobs schedule (per spec-derived):**
| Job | Frequency | Source |
|-----|-----------|--------|
| Archive ads | Daily, 2mo after published_at | Decision J, US-S7 |
| Delete archived ads | Daily, 4mo after published_at | Decision J, US-S7 |
| Purge failed moderation | Daily, 7 days after moderation_failed_at | Decision A |
| Hard-delete erased users | Daily, 30 days after consent_revoked_at | Decision F, zone R1 |
| Draft sweep | Every 30 minutes | Decision I, US-S2 |

### 2.7 Logging and Observability

**Approach:**
1. **Application logs:** Use Python `logging` (per rules: never print()), structured JSON for future parsing
2. **Docker logging:** Use `json-file` driver with rotation limits:
   ```yaml
   logging:
     driver: json-file
     options:
       max-size: "10m"
       max-file: "3"
   ```
3. **Access logs:** nginx access_log + error_log to stdout (Docker default)
4. **Future enhancement:** Promtail + Loki stack (reserved for phase 2)

**Log categories to capture:**
- Request logs (nginx → web)
- Application errors (Django default)
- Moderation actions (ModeratorActionLog model events)
- Consent lifecycle (consent_revoked_at timestamps for audit)

### 2.8 Restart Policies

**Recommended policies:**

| Service | Policy | Reasoning |
|---------|--------|-----------|
| db | `restart: unless-stopped` | Data persistence paramount |
| web | `restart: unless-stopped` | Application availability |
| bot | `restart: unless-stopped` | Message handling critical |
| nginx | `restart: unless-stopped` | TLS termination gateway |
| pgbouncer | `restart: unless-stopped` | Connection pooling |
| scheduler | `restart: unless-stopped` | Jobs must run |

**Critical:** Use `unless-stopped` not `always` to allow manual intervention during upgrades.

### 2.9 Resource Sizing for 300 users/day, 500k ads

| Service | CPU | Memory | Storage | Notes |
|---------|-----|--------|---------|-------|
| db (postgres:17) | 0.5-1 vCPU | 1-2 GB | 20 GB (500k ads × ~100KB each) | GIN indexes benefit from RAM |
| web (gunicorn) | 0.5-1 vCPU | 512 MB | 100 MB | 2-4 workers recommended |
| bot (aiogram) | 0.25 vCPU | 256 MB | - | Mostly idle, async I/O |
| nginx | 0.1 vCPU | 128 MB | 1 GB | Static/media serving |
| pgbouncer | 0.1 vCPU | 64 MB | - | Lightweight proxy |

**Gunicorn workers:** For sync WSGI, use `workers = (2 × $CPU) + 1`. On 1 vCPU: 3 workers. Keep each worker lightweight (CONN_MAX_AGE=0).

---

## 3. Trade-offs / Alternatives

| Decision | Option | Trade-off | Recommendation |
|----------|--------|-----------|----------------|
| Cron execution | Host cron | External to container, harder to orchestrate with env vars | **Container cron** - simpler for MVP, all configs together |
| PgBouncer | In same container as db | Simpler docker-compose | **Dedicated service** - cleaner, allows independent restart, per C5 |
| Media serving | nginx direct | Manual TLS management | **nginx + certbot** - automated renewal, per R8 |
| Backup | Physical base backup | Requires WAL setup | **Logical pg_dump** - simpler MVP, sufficient for 300 users |
| Analytics | Plausible SaaS | External dependency, $9/mo | **Self-host Plausible via Docker** - no PII, per spec L fallback |
| Celery for jobs | Heavyweight | Redis dependency, over-engineered | **Management commands via cron** - matches spec exactly, simplest MVP |

---

## 4. Risks + Open Questions

| Risk | Description | Mitigation |
|------|-------------|------------|
| TLS certificate expiry | Certbot might fail to renew if port 80 not reachable | Use staging certs first, set up monitoring alert on cert expiry |
| Media volume permissions | nginx runs as different UID than Django | Use named volumes with consistent ownership, or `chown -R 1000:1000` in entrypoint |
| PgBouncer auth errors | password auth mismatch between pgBouncer and Postgres | Test connection pooling locally before production deploy |
| Job overlap | Cron container restarts mid-job | Use flock or job lock table in Django to prevent overlap |
| Backup disk space | 7 daily dumps might fill disk | Implement retention policy, compress dumps |
| **Open Q1** | Should we use bitnami/pgbouncer or edoburu/pgbouncer? | bitnami image has better documentation + env var support |
| **Open Q2** | Do we need separate static_volume or use whitenoise? | **Yes** - nginx serves static directly, whitenoise for failover |
| **Open Q3** | How to handle media URL scheme for S3 migration later? | UUID keys already abstract; django-storages handles S3 transition |

---

## 5. Prioritized Checklist (MVP-Sized)

### P0 (Must-have for secure production)
- [ ] Create nginx service with TLS termination (certbot)
- [ ] Configure nginx `/media/` hardening (R8 headers, script block)
- [ ] Create PgBouncer service in transaction mode
- [ ] Set CONN_MAX_AGE=0 in Django database settings
- [ ] Configure Django proxy headers (USE_X_FORWARDED_HOST, SECURE_SSL_REDIRECT)
- [ ] Create scheduler container running management commands hourly
- [ ] Implement 5 management commands: `archive_ads`, `delete_archived_ads`, `purge_failed_moderation`, `hard_delete_erased_users`, `sweep_drafts`
- [ ] Add named volumes: `postgres_data`, `media_volume`, `static_volume`
- [ ] Create backup script for pg_dump with 7-day rotation
- [ ] Non-root user in Dockerfile + collectstatic in build

### P1 (Should-have for operations)
- [ ] Healthchecks on db, web, pgbouncer services
- [ ] Nginx log rotation via docker logging options
- [ ] Self-hosted Plausible via Docker (analytics fallback)
- [ ] Migration-once guard in docker-entrypoint (run migrations before web start)
- [ ] Docker secrets integration (prepare for Swarm/K8s)
- [ ] Load testing with 500k ads dataset

### P2 (Nice-to-have optimization)
- [ ] Promtail + Loki stack for log aggregation
- [ ] Physical base backups + WAL archiving
- [ ] Separate static_volume initialization with collectstatic
- [ ] Prometheus + Grafana for metrics
- [ ] Container resource limits (CPU/Memory) in compose

---

*Document generated: 2026-07-18*  
*Based on: docs/wiki/01-04, current docker-compose.yml and Dockerfile state*