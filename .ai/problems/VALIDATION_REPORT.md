# HTTPS/SSL Development Approach Validation Report

**Date:** 2026-07-25
**Project:** Mko Bazuna (Telegram-driven classifieds board)

---

## Finding Classification

### CONFIRMED BUG: dev.py HSTS Inheritance
**Type:** `SPEC-DEVIATION`

**Evidence:**
- `dev.py` line 11-13 only overrides `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, and `CSRF_COOKIE_SECURE`
- Inherits `SECURE_HSTS_SECONDS=3600` from `base.py` line 62
- Inherits `SECURE_HSTS_INCLUDE_SUBDOMAINS=True` from `base.py` line 63
- Inherits `SECURE_PROXY_SSL_HEADER` and `USE_X_FORWARDED_HOST` from `base.py` lines 57-58 and 59

**Impact:** When accessing via nginx `--profile use-nginx`, browsers cache the HSTS header (max-age=3600) and force HTTPS, breaking subsequent HTTP access even when nginx is stopped.

---

## Approach Evaluation

### Option 1: Disable HTTPS for dev (current dev.py)

| Criterion | Assessment |
|-----------|------------|
| Setup Effort | Low (no additional work) |
| Production Parity | **POOR** - HSTS header causes browser to cache HTTPS redirect |
| HTTPS Testing | None - cannot test secure cookies, OAuth, webhooks |
| Maintenance | None |
| **Verdict** | ❌ REJECTED - has confirmed bug, breaks parity |

**Rationale:** The current approach has a critical bug (HSTS inheritance) and provides no path for testing HTTPS-dependent features. With the project using nginx with TLS configuration in production, this creates a "works in dev, breaks in prod" risk.

---

### Option 2: Use mkcert for local HTTPS

| Criterion | Assessment |
|-----------|------------|
| Setup Effort | Low-Medium (one-time `mkcert -install`, generate certs) |
| Production Parity | **EXCELLENT** - identical TLS termination architecture |
| HTTPS Testing | Full - secure cookies, OAuth, webhooks, HTTP/2 |
| Maintenance | Low - 2-year renewal cycle |
| Future-Proofing | High - supports WebAuthn, Service Workers, all HTTPS APIs |

**Implementation Required:**
1. Add certificate volume mount to `docker-compose.dev.override.yml`
2. Generate certificates via mkcert (documented in README)
3. Update `dev.py` to override HSTS settings when accessing via nginx

**Verdict:** ✅ **APPROVED** - Best approach for this project

---

### Option 3: nginx TLS termination pattern

| Criterion | Assessment |
|-----------|------------|
| Setup Effort | Same as Option 2 |
| Production Parity | **EXCELLENT** - same as Option 2 |
| HTTPS Testing | Full |
| Maintenance | Low |
| **Note** | This IS the architecture; mkcert provides the certificates |

**Verdict:** ✅ **VALIDATED** - This is the production architecture; mkcert is the certificate source

---

## Decision: Option 2 (mkcert for local HTTPS)

### Rationale

1. **Telegram Bot Context:** While the bot currently uses polling, webhook mode (more efficient for production) requires HTTPS callbacks. Testing webhooks locally is impossible without HTTPS.

2. **OAuth Readiness:** Future integrations (Google, GitHub, etc.) require HTTPS redirect URIs. The project uses `SECURE_PROXY_SSL_HEADER` configuration that assumes HTTPS termination.

3. **nginx Architecture:** The nginx config already expects `/etc/nginx/certs/fullchain.pem` and `privkey.pem`. The `use-nginx` profile exists but lacks certificate mount, causing nginx to fail.

4. **Production Parity:** Using mkcert provides identical request flow (Browser → HTTPS:443 → nginx → HTTP:8000 → Django) to production, eliminating configuration drift.

5. **Low Friction:** One-time `mkcert -install` per developer is negligible compared to ongoing value. 2-year certificate validity minimizes maintenance.

---

## Required Fixes

### 1. Fix dev.py HSTS Override Bug (HIGH PRIORITY)

```python
# Add to dev.py after line 13
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
```

### 2. Add Certificate Mount to docker-compose.dev.override.yml (HIGH PRIORITY)

```yaml
nginx:
  profiles:
    - use-nginx
  volumes:
    - media_volume:/media_volume:ro
    - ./docker/nginx/certs:/etc/nginx/certs:ro  # ADD THIS
```

### 3. Document mkcert Setup (MEDIUM PRIORITY)

Add to README.md:
```markdown
## Local HTTPS Development

For production parity with nginx TLS termination:

```bash
# Install mkcert (Windows)
choco install mkcert

# One-time CA install (requires admin)
mkcert -install

# Generate certificates
mkdir -p docker/nginx/certs
cd docker/nginx/certs
mkcert localhost 127.0.0.1 ::1 mkobazuna.local
cp localhost.pem fullchain.pem
cp localhost-key.pem privkey.pem
```

Then run: `docker compose --profile use-nginx up`
```

### 4. Add .gitignore Entry (MEDIUM PRIORITY)

```gitignore
docker/nginx/certs/*.pem
!docker/nginx/certs/.gitkeep
```

---

## Verification Steps

After implementing fixes:

1. **Verify HSTS is disabled in dev:**
   ```bash
   # With --profile use-nginx
   curl -I https://localhost | grep -i strict
   # Should return nothing (HSTS header absent)
   ```

2. **Verify HTTPS works:**
   ```bash
   curl -k https://localhost/login/
   # Should return 200 OK
   ```

3. **Verify Django security settings:**
   ```bash
   uv run python manage.py check --deploy
   # Should show no HSTS/SSL warnings in dev settings
   ```

---

## References

- Research: [01-disable-https-ssl-dev.md](01-disable-https-ssl-dev.md) - Confirmed HSTS bug
- Research: [02-mkcert-local-https-research.md](02-mkcert-local-https-research.md) - Implementation details
- Research: [03-nginx-tls-termination/findings.md](03-nginx-tls-termination/findings.md) - Architecture validation

---

**Status:** Option 2 (mkcert) is the optimal choice. Option 1 is rejected due to confirmed bug. Option 3 is the production architecture; mkcert is the certificate source to complete it.