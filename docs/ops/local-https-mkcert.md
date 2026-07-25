---
id: local-https-mkcert
domain: ops
tags:
  - https
  - tls
  - mkcert
  - nginx
  - development
related:
  - docker-deployment
  - postgres-18-docker-volume-migration
---

## Purpose

Documentation for the prioritized mkcert-based local HTTPS development setup. This approach provides production parity by enabling HTTPS locally for testing secure cookies, OAuth flows, webhooks, and HTTP/2 features without disabling security settings.

## Main Concepts

- **Production parity:** Local development mirrors production nginx TLS termination architecture
- **One-time setup:** `mkcert -install` creates a local CA trusted by browsers and OS
- **Low maintenance:** Certificates are valid for ~2 years with simple renewal process
- **Volume mount approach:** Certificates are mounted into nginx container at `/etc/nginx/certs/`

## Priority Approach: Volume Mount Certificates into nginx Container

This is the recommended and prioritized approach for Mko Bazuna because:

| Criterion | Reason |
|-----------|--------|
| Architecture alignment | nginx config already expects `/etc/nginx/certs/fullchain.pem` - no nginx changes needed |
| Production parity | Uses identical nginx configuration as production (only cert path differs) |
| Minimal changes | Only requires updating `docker-compose.dev.override.yml` for the nginx service |
| Single source of truth | Certificates live in `docker/nginx/certs/` alongside the nginx config |

### Why Not Container-based Generation or Direct Django HTTPS

- **Container certgen approach:** Adds unnecessary complexity. mkcert requires privileged CA installation which defeats container isolation
- **Direct Django HTTPS:** Bypasses nginx entirely, but the project uses nginx as the frontend reverse proxy. This creates configuration inconsistencies

## Prerequisites

- Docker + Docker Compose
- Chocolatey (Windows) or system package manager
- Administrator privileges (required for `mkcert -install`)

## Initial Setup

### 1. Install mkcert

```bash
# Windows (Chocolatey)
choco install mkcert

# macOS (Homebrew)
brew install mkcert
brew install nss  # For Firefox trust on macOS

# Linux (Ubuntu/Debian)
sudo apt install libnss3-tools
wget -O - https://github.com/FiloSottile/mkcert/releases/download/v1.4.4/mkcert-v1.4.4-linux-amd64 > mkcert
chmod +x mkcert
sudo mv mkcert /usr/local/bin/
```

### 2. Install the Local CA (One-time per machine)

```bash
mkcert -install
```

This creates a local Certificate Authority and installs it into the system trust store:
- **Windows:** Certificate Store
- **macOS:** Keychain
- **Linux:** System CA bundle

**Restart your browser after CA installation** to ensure trust is recognized.

### 3. Generate Development Certificates

```bash
mkdir -p docker/nginx/certs
cd docker/nginx/certs
mkcert localhost 127.0.0.1 ::1 mkobazuna.local
```

This creates:
- `localhost+2.pem` - Certificate containing Subject Alternative Names
- `localhost+2-key.pem` - Private key

For nginx compatibility, rename the files:

```bash
cp localhost+2.pem fullchain.pem
cp localhost+2-key.pem privkey.pem
```

> **Note:** The exact filename may vary (e.g., `localhost+1.pem`, `localhost+2.pem`) depending on how many certificates you've generated. Use the files created by mkcert on your system.

### 4. Mount Certificates in Docker Compose

The `docker-compose.dev.override.yml` nginx service should include:

```yaml
nginx:
  profiles:
    - use-nginx
  volumes:
    - media_volume:/media_volume:ro
    - ./docker/nginx/certs:/etc/nginx/certs:ro
```

### 5. Run Development Environment

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.override.yml --profile use-nginx up --build
```

Access the application at `https://localhost`. HTTP requests redirect to HTTPS automatically.

## Certificate Renewal

### Expiration Timeline

mkcert certificates are valid for **2 years and 3 months** (under 825 days to comply with macOS/iOS limits).

### Renewal Process

Certificates are renewed by re-running the generation command:

```bash
# From project root
cd docker/nginx/certs

# Regenerate certificates (CA remains trusted)
mkcert localhost 127.0.0.1 ::1 mkobazuna.local

# Rename for nginx compatibility (overwrites old certs)
cp localhost+2.pem fullchain.pem
cp localhost+2-key.pem privkey.pem
```

**No need to re-run `mkcert -install`** - the CA is already trusted.

### Verification Commands

```bash
# Check CA location
mkcert -CAROOT

# Inspect certificate details
mkcert -inspect localhost+2.pem

# Clean expired certs from cache
mkcert -clean
```

## Automation Script

Create `scripts/setup-local-https.sh` for easy setup:

```bash
#!/bin/bash
set -e

echo "Setting up local HTTPS with mkcert..."

# Install CA if not already installed
mkcert -install 2>/dev/null || echo "CA already installed"

# Create certificates directory
mkdir -p docker/nginx/certs
cd docker/nginx/certs

# Generate certificates
mkcert localhost 127.0.0.1 ::1 mkobazuna.local

# Rename for nginx
for f in *.pem; do
    if [[ "$f" == *"-key.pem" ]]; then
        cp "$f" privkey.pem
    else
        cp "$f" fullchain.pem
    fi
done

echo "Certificates generated in docker/nginx/certs/"
echo "Run: docker compose --profile use-nginx up --build"
```

## Security Considerations

### Never Commit These Files

Add to `.gitignore`:

```gitignore
# mkcert development certificates
docker/nginx/certs/*.pem
!docker/nginx/certs/.gitkeep
```

Create the `.gitkeep` file to preserve the directory:

```bash
touch docker/nginx/certs/.gitkeep
```

### CA Key Security

The `rootCA-key.pem` file (stored in system CA location) is the private key of your local Certificate Authority. **Anyone with this key can generate certificates trusted by your machine.**

- Never share or commit this file
- If compromised, run `mkcert -uninstall` and regenerate

## Use Cases Requiring Local HTTPS

| Feature | Requirement | Testing |
|---------|-------------|---------|
| Secure Cookies | HTTPS only | `SESSION_COOKIE_SECURE=True` in base.py |
| OAuth Callbacks | HTTPS required | Telegram webhook mode, future OAuth integrations |
| HTTP/2 | TLS required | Full performance testing in development |
| HSTS Headers | HTTPS only | Prevents downgrade attacks |
| Service Workers | HTTPS required | PWA feature testing |

## Troubleshooting

### Browser Shows Certificate Warning

1. **Restart your browser** after running `mkcert -install`
2. **Check CA installation:** `mkcert -CAROOT` should show a valid path
3. **Clear browser cache** if HSTS was previously enabled

### nginx Fails to Start

```bash
# Check certificate files exist
ls -la docker/nginx/certs/

# Verify nginx logs
docker compose logs nginx

# Common error: missing certificate mount
# Ensure docker-compose.dev.override.yml has the volume mount configured
```

### mkcert Command Not Found (Windows)

After Chocolatey installation, you may need to restart PowerShell or your terminal session. The Chocolatey bin directory must be in your PATH.

### Firefox Shows Security Warning (Linux)

Ensure `libnss3-tools` is installed and run:

```bash
mkcert -install
```

This automatically configures Firefox trust via NSS.

## Related Documentation

- [Docker Deployment](docker-deployment.md) - General deployment and development setup
- [PostgreSQL 18 Docker Volume Migration](postgres-18-docker-volume-migration.md) - Database migration guide
- [Architecture Structure](../01-spec/architecture-structure.md) - System architecture overview

## References

- [mkcert GitHub](https://github.com/FiloSottile/mkcert) - Official tool and documentation
- [Django HTTPS Deployment Checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/#https)
- [VALIDATION_REPORT.md](../../.ai/problems/VALIDATION_REPORT.md) - HTTPS approach evaluation