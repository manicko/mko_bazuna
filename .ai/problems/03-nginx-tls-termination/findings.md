# Nginx TLS Termination Pattern for Django Applications

**Date:** 2026-07-25  
**Topic:** Architecture and implementation of nginx TLS termination for Mko Bazuna

---

## 1. Architecture Pattern: Browser → HTTPS → nginx → HTTP → Django/gunicorn

### Flow Overview
```
Browser ──HTTPS:443──┐
                      ↓
                nginx:443 ssl (terminates TLS)
                      ↓
                HTTP:8000 (internal network)
                      ↓
                gunicorn (web container)
```

### Implementation in This Project

**nginx (docker/nginx/nginx.conf):**
- Listens on `80` (HTTP redirect to HTTPS)
- Listens on `443 ssl` with `http2 on`
- Terminates TLS using certificates at `/etc/nginx/certs/`
- Forwards all requests to `http://web:8000` via `proxy_pass`

**Django (config/settings/prod.py):**
```python
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SECURE_SSL_REDIRECT = True
```

### Proxy Headers Configured
```nginx
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
```

These headers tell Django that the original request was HTTPS, even though the internal connection is HTTP.

---

## 2. Required Django Settings: SECURE_PROXY_SSL_HEADER Configuration

### Core Setting
```python
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
```

**Purpose:** Informs Django that the `X-Forwarded-Proto` header indicates the original protocol. When nginx sets `X-Forwarded-Proto: https`, Django treats the request as secure.

### Required Companion Settings
| Setting | Value | Purpose |
|---------|-------|---------|
| `SECURE_SSL_REDIRECT` | `True` | Redirects HTTP requests to HTTPS (handled by nginx in this setup) |
| `USE_X_FORWARDED_HOST` | `True` | Uses `X-Forwarded-Host` header for host validation |
| `SESSION_COOKIE_SECURE` | `True` | Ensures cookies are only sent over HTTPS |
| `CSRF_COOKIE_SECURE` | `True` | CSRF cookie only sent over HTTPS |

### Location in Codebase
- **base.py:** Lines 53-64 defines security settings including `SECURE_PROXY_SSL_HEADER` and HSTS (3600 seconds)
- **prod.py:** Lines 11-13 override for production (HSTS extended to 1 year)
- **dev.py:** Currently does NOT override `SECURE_PROXY_SSL_HEADER` or HSTS (inherits from base.py)

This creates a **conflict when using --profile use-nginx**: nginx forwards `X-Forwarded-Proto: https`, but `SECURE_HSTS_SECONDS = 3600` in base.py is inherited by dev, potentially causing browser caching issues.

### Risk if Misconfigured
If `SECURE_PROXY_SSL_HEADER` is not set correctly:
- Django thinks requests are HTTP (insecure)
- `SECURE_SSL_REDIRECT` would cause redirect loops
- Secure cookies would not be sent
- `request.is_secure()` returns `False` incorrectly

---

## 3. Nginx Certificate Management

### Let's Encrypt Integration (Production)

**Current Configuration (docker-compose.prod.yml):**
```yaml
nginx:
  volumes:
    - ${TLS_CERT_PATH:-/etc/nginx/certs}:/etc/nginx/certs:ro
```

**Approach:** Certificates mounted as files, NOT generated inside container. This follows the 12-factor app methodology where certs are provided via environment/operating system.

**Typical Production Workflow:**
1. Certificates obtained on host via certbot or acme.sh
2. `TLS_CERT_PATH` points to certificate directory (e.g., `/etc/letsencrypt/live/mkobazuna.com/`)
3. nginx reads `fullchain.pem` and `privkey.pem` at startup
4. Renewal handled by certbot's renew hook (restarts nginx to pick up new certs)

### Mounted Certificates (Development)

**Development Path (docker-compose.dev.override.yml):**
```yaml
nginx:
  profiles:
    - use-nginx  # Optional profile
```

**Current State:** No certificate mount defined for development. Using `--profile use-nginx` without certificates will cause nginx to fail on startup (missing cert files).

**Workaround via mkcert (see 02-mkcert-local-https-research.md):**
```bash
# Generate certificates in project
mkdir -p docker/nginx/certs
cd docker/nginx/certs
mkcert localhost 127.0.0.1 ::1 mkobazuna.local
cp localhost.pem fullchain.pem
cp localhost-key.pem privkey.pem

# Mount added to nginx service
volumes:
  - ./docker/nginx/certs:/etc/nginx/certs:ro
```

---

## 4. Benefits for This Project

### Certificate Complexity Isolated from Django

| Aspect | Traditional (Django SSL) | nginx TLS Termination |
|--------|------------------------|----------------------|
| Certificate loading | Django reads certs, complex Python SSL config | nginx handles natively |
| Renewals | Requires Django restart | nginx reload only |
| Key rotation | App-level concern | Infrastructure concern |
| Certificate storage | Must be readable by app user | Readable by nginx user |

### Simpler Container Configuration

**Web container (Dockerfile):**
- Exposes port 8000 (no SSL libraries needed)
- No certificate volume mounts
- Plain HTTP gunicorn configuration
- Smaller attack surface (no TLS keys in app container)

**nginx container:**
- Only `nginx:alpine` image
- Certificate management isolated to one service
- Can be swapped with nginx-plus or traefik without touching Django

### Production Parity

| Environment | Without nginx | With nginx (--profile use-nginx) |
|-------------|---------------|-------------------------------|
| HTTPS | ❌ (direct HTTP) | ✅ (same as production) |
| Security Headers | ❌ | ✅ (HSTS, X-Frame-Options, etc.) |
| Rate Limiting | ❌ | ✅ (login, search endpoints) |
| HTTP/2 | ❌ | ✅ |
| Cookie Behavior | HTTP cookies | HTTPS cookies (secure) |

This allows developers to:
- Test OAuth callback URLs (Telegram bot webhooks)
- Test service workers (future PWA features)
- Test WebAuthn/authentication flows
- Match production cookie/session behavior

---

## 5. --profile use-nginx: Dev vs Prod Behavior

### Development (docker-compose.dev.override.yml)

**How it Works:**
```yaml
nginx:
  profiles:
    - use-nginx  # Only started when --profile use-nginx passed
```

**Behavior:**
- nginx service is NOT started by default (`make up` or plain `docker compose up`)
- With `--profile use-nginx`: nginx starts with TLS on ports 80/443
- **Missing:** Certificate volume mount (must be added manually)
- **Missing:** `TLS_CERT_PATH` environment variable configuration

**Current Dev Flow:**
```bash
# Default: Django on port 8000 (HTTP only)
docker compose up -d

# With nginx: Requires certificates to be mounted
docker compose --profile use-nginx up -d  # Will fail without certs
```

### Production (docker-compose.prod.yml)

**How it Works:**
```yaml
nginx:
  volumes:
    - ${TLS_CERT_PATH:-/etc/nginx/certs}:/etc/nginx/certs:ro
```

**Behavior:**
- nginx service ALWAYS starts (not a profile)
- Certificates provided via `TLS_CERT_PATH` env var or default path
- HTTP automatically redirects to HTTPS
- All requests proxied to `http://web:8000`

**Production Flow:**
```bash
# Certificates from Let's Encrypt or mounted path
TLS_CERT_PATH=/etc/letsencrypt/live/example.com \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Key Differences Summary

| Aspect | Development | Production |
|--------|-------------|------------|
| nginx startup | Profile-gated (`--profile use-nginx`) | Always runs |
| Certificates | Manual (mkcert) or missing | Mounted (Let's Encrypt or custom) |
| Request flow | Optional HTTPS via nginx | HTTPS mandatory |
| Fallback | Direct `localhost:8000` access | N/A (nginx always proxies) |
| Security headers | Same nginx config | Same nginx config |

---

## 6. Implementation Checklist

### For Production Deployment
- [x] nginx config includes TLS certificate paths
- [x] SECURE_PROXY_SSL_HEADER configured in prod.py
- [x] TLS_CERT_PATH variable in docker-compose.prod.yml
- [ ] Document Let's Encrypt setup (certbot command)

### For Development with nginx Profile
- [ ] Add certificate mount to `docker-compose.dev.override.yml`
- [ ] Document mkcert setup for local HTTPS
- [ ] Override `SECURE_HSTS_SECONDS = 0` in dev.py when using nginx (currently inherited from base.py)

### Potential Issues
1. **Missing dev certificate mount:** `--profile use-nginx` fails without certificates (nginx cannot start without `fullchain.pem` and `privkey.pem`)
2. **HSTS in development:** `SECURE_HSTS_SECONDS = 3600` in base.py is inherited by dev, causing HSTS header to be sent in development (browser caches HTTPS, breaks HTTP access after visiting via nginx)
3. **dev.py does not override SECURE_PROXY_SSL_HEADER:** When nginx proxies with `X-Forwarded-Proto: https`, Django should accept this header, but dev.py inherits from base.py which already has this configured. This actually works correctly, but the lack of HSTS override is the real issue.
4. **Port conflict in dev:** The nginx profile uses ports 80/443 which may conflict with other local services

---

## 7. References

- [Django SECURE_PROXY_SSL_HEADER](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-proxy-ssl-header)
- [nginx SSL Module](https://nginx.org/en/docs/http/ngx_http_ssl_module.html)
- [Django HTTPS Deployment Checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/#https)
- [Let's Encrypt Integration Patterns](https://letsencrypt.org/docs/integration-guide/)