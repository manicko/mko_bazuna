# Admin User Creation in Docker Deployment Workflow

**Status:** Research Complete  
**Date:** 2026-07-22  
**Domain:** DevOps / Docker / Admin Authentication  

---

## Executive Summary

This document analyzes four integration approaches for admin user creation within the Mko Bazuna Docker deployment workflow. The project uses a custom Django `User` model with `telegram_id` as `USERNAME_FIELD`, requiring a management command (`create_admin_user`) for initial admin setup.

**Recommended Approach:** **Option D (Environment Variable-Based Automatic Creation)** with idempotent handling, integrated as a one-shot service after migrations.

---

## 1. Project Context

### 1.1 Current Docker Architecture

```
Services:
  db          → PostgreSQL 18 (persistent volume)
  migrate     → One-shot: runs migrations with advisory lock, exits
  web         → gunicorn (port 8000, internal)
  bot         → aiogram bot process
  nginx       → TLS termination, reverse proxy
```

### 1.2 User Model Constraints

```python
USERNAME_FIELD = "telegram_id"  # Primary auth field
username = CharField(null=True, blank=True)  # Optional, nullable
telegram_id = BigIntegerField(unique=True)  # Required
chat_id = BigIntegerField(unique=True)  # Required
```

### 1.3 Existing Pattern: Advisory Lock for One-Shot Services

The `migrate` service uses PostgreSQL advisory locks for idempotent execution:

```python
# apps/core/utils/advisory_lock.py
with advisory_lock(AdvisoryLockId.MIGRATE, session=True):
    # Run operations
```

---

## 2. Integration Options Analysis

### 2.1 Option A: Post-Migration Hook in Migrate Service

**Description:** Extend `migrate_locked.py` to create admin user after migrations.

**Implementation:**

```python
# apps/core/utils/migrate_locked.py
def main() -> int:
    with advisory_lock(AdvisoryLockId.MIGRATE, session=True):
        # Run migrations
        result = subprocess.run([...])
        if result.returncode != 0:
            return result.returncode
        
        # Create admin (if env vars set)
        if os.getenv("ADMIN_USERNAME") and os.getenv("ADMIN_PASSWORD"):
            subprocess.run([
                sys.executable, "manage.py", "create_admin_user",
                "--username", os.getenv("ADMIN_USERNAME"),
                "--password", os.getenv("ADMIN_PASSWORD"),
                "--telegram-id", os.getenv("ADMIN_TELEGRAM_ID", "-1"),
            ])
        return 0
```

**Pros:**
- Single service handles all post-init tasks
- No additional Docker service overhead
- Runs in same advisory lock context as migrations

**Cons:**
- Mixes concerns (migrations + admin creation)
- Harder to skip admin creation in certain environments
- If admin creation fails, migrations appear to fail
- Not easily testable in isolation

**Confidence:** MEDIUM - Works but violates separation of concerns principle.

---

### 2.2 Option B: Separate One-Shot Create_Admin Service

**Description:** Dedicated Docker service that runs after `migrate` completes.

**Implementation:**

```yaml
# docker-compose.yml
services:
  migrate:
    # ... existing config
  
  create_admin:
    build:
      context: .
      dockerfile: docker/Dockerfile
    command: uv run python src/backend/manage.py create_admin_user \
        --username "${ADMIN_USERNAME:-admin}" \
        --password "${ADMIN_PASSWORD}" \
        --telegram-id "${ADMIN_TELEGRAM_ID:-1}"
    depends_on:
      migrate:
        condition: service_completed_successfully
    environment:
      - UV_PROJECT_ENVIRONMENT=/opt/venv
      - DJANGO_SETTINGS_MODULE=config.settings.prod
      - ADMIN_USERNAME=admin
      - ADMIN_TELEGRAM_ID=1
    env_file:
      - .env
    # One-shot: runs once, then exits
```

**Management Command:**

```python
# apps/core/management/commands/create_admin_user.py
import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Create an admin user for Django admin site"

    def add_arguments(self, parser) -> None:
        parser.add_argument("--username", type=str, required=True)
        parser.add_argument("--password", type=str, required=True)
        parser.add_argument("--telegram-id", type=int, default=-1)
        parser.add_argument("--email", type=str, default="")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options) -> None:
        User = get_user_model()
        username = options["username"]
        telegram_id = options["telegram-id"]
        
        # Idempotent: skip if user exists
        if User.objects.filter(telegram_id=telegram_id).exists():
            self.stdout.write(self.style.WARNING(
                f"Admin user with telegram_id={telegram_id} already exists"
            ))
            return
        
        user = User.objects.create(
            username=username,
            telegram_id=telegram_id,
            chat_id=telegram_id,
            email=options["email"],
            is_staff=True,
            is_superuser=True,
        )
        user.set_password(options["password"])
        user.save()
        
        self.stdout.write(self.style.SUCCESS("Admin user created"))
```

**Pros:**
- Clean separation of concerns
- Idempotent by design (skips if exists)
- Can be run independently for testing
- Follows existing project patterns (one-shot services)
- Clear dependency chain: db → migrate → create_admin → web/bot

**Cons:**
- Adds an extra service to docker-compose
- More services to manage in production

**Confidence:** HIGH - Follows established patterns, clean architecture.

---

### 2.3 Option C: Manual Creation via Docker Exec

**Description:** Admin user created manually after deployment using `docker compose exec`.

**Implementation:**

```bash
# After deployment
docker compose run --rm web \
    uv run python manage.py create_admin_user \
    --username admin \
    --password "${ADMIN_PASSWORD}" \
    --telegram-id -1
```

**Pros:**
- Maximum control over timing
- No code changes needed
- Simple and explicit

**Cons:**
- Manual step prone to human error
- Not automatable in CI/CD pipelines
- Inconsistent across deployments
- Requires documentation and training
- Risk of forgetting in new environments

**Confidence:** LOW - Operational risk, not suitable for automated deployments.

---

### 2.4 Option D: Environment Variable-Based Automatic Creation

**Description:** Admin creation triggered by environment variables, using advisory lock for idempotency.

**Implementation:**

```python
# apps/core/management/commands/create_admin_user.py
import os
import logging
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Create an admin user for Django admin site (idempotent)"

    def add_arguments(self, parser) -> None:
        parser.add_argument("--username", type=str, required=True)
        parser.add_argument("--password", type=str, required=True)
        parser.add_argument("--telegram-id", type=int, default=-1)
        parser.add_argument("--email", type=str, default="")

    def handle(self, *args, **options) -> None:
        User = get_user_model()
        username = options["username"]
        telegram_id = options["telegram_id"]
        
        # Check if admin credentials are configured
        if not options["password"]:
            self.stdout.write("ADMIN_PASSWORD not set, skipping admin creation")
            return
        
        # Idempotent: skip if user exists
        if User.objects.filter(telegram_id=telegram_id).exists():
            self.stdout.write(self.style.WARNING(
                f"Admin user with telegram_id={telegram_id} already exists, skipping"
            ))
            return
        
        # Create admin user
        user = User.objects.create(
            username=username,
            telegram_id=telegram_id,
            chat_id=telegram_id,
            email=options["email"],
            is_staff=True,
            is_superuser=True,
        )
        user.set_password(options["password"])
        user.save()
        
        logger.info("Admin user created: %s (telegram_id=%s)", username, telegram_id)
        self.stdout.write(self.style.SUCCESS("Admin user created successfully"))
```

**Docker Compose Integration:**

```yaml
# docker-compose.yml - add after migrate service
create_admin:
  build:
    context: .
    dockerfile: docker/Dockerfile
  command: >
    uv run python src/backend/manage.py create_admin_user
    --username "${ADMIN_USERNAME:-admin}"
    --password "${ADMIN_PASSWORD}"
    --telegram-id "${ADMIN_TELEGRAM_ID:--1}"
  depends_on:
    migrate:
      condition: service_completed_successfully
  environment:
    - UV_PROJECT_ENVIRONMENT=/opt/venv
    - DJANGO_SETTINGS_MODULE=config.settings.prod
  env_file:
    - .env
  # One-shot service: exits after completion
```

**Environment Configuration:**

```env
# .env.example additions
# Admin user credentials for Django admin site
ADMIN_USERNAME=admin
ADMIN_PASSWORD=  # Set via secret management in production
ADMIN_TELEGRAM_ID=-1  # Placeholder: negative to avoid collision with real IDs
```

**Pros:**
- Fully automated deployment
- Idempotent (safe to run multiple times)
- Skippable if ADMIN_PASSWORD not set
- Follows 12-factor app principles
- Works in CI/CD pipelines

**Cons:**
- Requires careful secret management
- Password in environment variables (mitigated by using secret managers)

**Confidence:** HIGH - This is the recommended approach.

---

## 3. Environment-Specific Considerations

### 3.1 Development Environment

**Behavior:**
- Admin creation skipped if `ADMIN_PASSWORD` not set
- Allows developers to use `createsuperuser` manually when needed
- Works with bind mounts and hot-reload

**Recommendation:**
```bash
# Dev: Create admin manually if needed
docker compose run --rm web \
    uv run python manage.py create_admin_user \
    --username admin \
    --password dev-password \
    --telegram-id -1
```

### 3.2 Production Environment

**Behavior:**
- `ADMIN_PASSWORD` required in `.env` or secret management
- Idempotent: safe to run multiple times
- Logs creation for audit trail

**Recommendation:**
```bash
# Production: Use secret management
# Example: HashiCorp Vault, AWS Secrets Manager, or docker secrets
docker compose run --rm web \
    uv run python manage.py create_admin_user \
    --username admin \
    --password "$(vault read -field=password secret/mko-bazuna/admin)" \
    --telegram-id -1
```

### 3.3 Production Override Services

The `docker-compose.prod.yml` already includes profile-based services. Admin creation should be:
- **Always-on** (not profile-gated) since admin access is required
- Run before `web` and `bot` services start

---

## 4. Security Implications

### 4.1 Password Handling

| Approach | Risk | Mitigation |
|----------|------|------------|
| Env vars | Password visible in `docker inspect` | Use Docker secrets or external secret managers |
| CI/CD injection | Pipeline logs exposure | Mask secrets in CI logs |
| Manual creation | Human error, inconsistent | Document process, use scripts |

### 4.2 Placeholder Telegram ID Selection

**Recommended: `-1` (negative)**

- Negative numbers unlikely to collide with real Telegram IDs (always positive)
- Clearly indicates placeholder/admin account
- Easy to identify in database queries

**Alternative: `0`**
- Also valid placeholder
- May be confused with "unset" in some contexts

### 4.3 Admin Account Visibility

The admin user will appear in Django admin with:
- `username`: admin
- `telegram_id`: -1 (placeholder)
- `is_staff`: True
- `is_superuser`: True

This is acceptable and helps distinguish admin accounts from regular users.

### 4.4 Secret Management Recommendations

```bash
# Production: Use docker secrets
echo "supersecretpassword" | docker secret create admin_password -

# Or use environment-specific secret files
mkdir -p /run/secrets
echo "supersecretpassword" > /run/secrets/admin_password
chmod 600 /run/secrets/admin_password
```

---

## 5. Recommended Implementation

### 5.1 Management Command

**File:** `src/backend/apps/core/management/commands/create_admin_user.py`

```python
"""
Management command to create an admin user for Django admin site.

Creates a user with placeholder telegram_id for username/password authentication.
Idempotent: skips creation if user with same telegram_id already exists.

Usage:
    uv run python manage.py create_admin_user \
        --username admin \
        --password <password> \
        --telegram-id -1
"""

import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Create an admin user for Django admin site (idempotent)"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--username",
            type=str,
            required=True,
            help="Admin username (stored in username field)",
        )
        parser.add_argument(
            "--password",
            type=str,
            required=True,
            help="Admin password",
        )
        parser.add_argument(
            "--telegram-id",
            type=int,
            default=-1,
            help="Placeholder telegram_id for admin user (default: -1)",
        )
        parser.add_argument(
            "--email",
            type=str,
            default="",
            help="Admin email (optional)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be done without creating user",
        )

    def handle(self, *args, **options) -> None:
        username = options["username"]
        password = options["password"]
        telegram_id = options["telegram_id"]
        email = options["email"]
        dry_run = options["dry_run"]

        User = get_user_model()

        # Check if user already exists (idempotent)
        if User.objects.filter(telegram_id=telegram_id).exists():
            self.stdout.write(self.style.WARNING(
                f"Admin user with telegram_id={telegram_id} already exists, skipping"
            ))
            return

        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(
                f"User with username='{username}' already exists, skipping"
            ))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"DRY RUN: Would create admin user:\n"
                f"  username: {username}\n"
                f"  telegram_id: {telegram_id}\n"
                f"  email: {email}\n"
                f"  is_staff: True\n"
                f"  is_superuser: True"
            ))
            return

        # Create the admin user
        user = User.objects.create(
            username=username,
            telegram_id=telegram_id,
            chat_id=telegram_id,  # Use same value for chat_id
            email=email,
            is_staff=True,
            is_superuser=True,
        )
        user.set_password(password)
        user.save()

        logger.info("Admin user created: %s (telegram_id=%s)", username, telegram_id)
        self.stdout.write(self.style.SUCCESS(
            f"Admin user created:\n"
            f"  username: {username}\n"
            f"  telegram_id: {telegram_id}\n"
            f"  is_staff: True\n"
            f"  is_superuser: True"
        ))
```

### 5.2 Docker Compose Addition

```yaml
# docker-compose.yml - add after migrate service
  create_admin:
    build:
      context: .
      dockerfile: docker/Dockerfile
    command: >
      uv run python src/backend/manage.py create_admin_user
      --username "${ADMIN_USERNAME:-admin}"
      --password "${ADMIN_PASSWORD}"
      --telegram-id "${ADMIN_TELEGRAM_ID:--1}"
    depends_on:
      migrate:
        condition: service_completed_successfully
    environment:
      - UV_PROJECT_ENVIRONMENT=/opt/venv
      - DJANGO_SETTINGS_MODULE=config.settings.prod
    env_file:
      - .env
    # One-shot service: runs once, then exits
```

### 5.3 Environment Variables

**Add to `.env.example`:**

```env
# Admin user credentials for Django admin site
# Note: Admin login uses telegram_id, so enter the telegram_id value as the username
ADMIN_USERNAME=admin
ADMIN_PASSWORD=  # Set in production via secret management
ADMIN_TELEGRAM_ID=-1  # Placeholder ID for admin users
```

### 5.4 Handling Existing Admin Users

The command handles existing users idempotently:

```python
# If user exists, skip with warning
if User.objects.filter(telegram_id=telegram_id).exists():
    self.stdout.write(self.style.WARNING(
        f"Admin user with telegram_id={telegram_id} already exists, skipping"
    ))
    return
```

For password rotation:

```bash
# Update existing admin password
docker compose run --rm web \
    uv run python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.prod')
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.get(telegram_id=-1)
user.set_password('new-password')
user.save()
print('Password updated')
"
```

---

## 6. Alternative: Custom Authentication Backend

If the admin login form should show "Username" instead of "Telegram ID", implement a custom backend:

**File:** `src/backend/apps/users/backends.py`

```python
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

User = get_user_model()


class UsernameOrTelegramBackend(ModelBackend):
    """
    Authentication backend that allows login via username OR telegram_id.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        # Try username first
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            # Fall back to telegram_id
            try:
                user = User.objects.get(telegram_id=username)
            except User.DoesNotExist:
                return None

        if user.check_password(password):
            return user
        return None
```

**Add to `base.py`:**

```python
AUTHENTICATION_BACKENDS = [
    "apps.users.backends.UsernameOrTelegramBackend",
    "django.contrib.auth.backends.ModelBackend",
]
```

**Trade-offs:**
- More complex
- Changes global authentication behavior
- May affect Telegram-based login flow

---

## 7. Implementation Checklist

- [ ] Create management command `create_admin_user.py`
- [ ] Add unit tests for the command
- [ ] Update `.env.example` with admin credential variables
- [ ] Add `create_admin` service to `docker-compose.yml`
- [ ] Update `docs/ops/docker-deployment.md`
- [ ] Run lint: `uv run ruff check src/backend/apps/core/management/commands/create_admin_user.py`
- [ ] Run typecheck: `uv run basedpyright src/backend/apps/core/management/commands/create_admin_user.py`
- [ ] Test in development environment

---

## 8. References

- [Django Management Commands](https://docs.djangoproject.com/en/stable/howto/custom-management-commands/)
- [Django Custom User Models](https://docs.djangoproject.com/en/stable/topics/auth/customizing/)
- [Project Architecture](docs/99-agent/architecture.md)
- [Docker Deployment](docs/ops/docker-deployment.md)
- [Admin User Creation Research](T001_admin_user_creation.md)
- [User Model](src/backend/apps/users/models.py)
- [Advisory Lock Utility](src/backend/apps/core/utils/advisory_lock.py)