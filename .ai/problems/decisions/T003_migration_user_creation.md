# Admin User Creation: Django Migrations vs Management Commands

**Status:** Research Complete  
**Date:** 2026-07-22  
**Domain:** Django Architecture / Database Operations / User Management  

---

## Executive Summary

This document analyzes the appropriate approach for creating an initial admin user in the Mko Bazuna project, clarifying that **Django migrations (not Alembic)** are the correct tool for database schema changes, while **management commands** are the appropriate pattern for data seeding and user creation.

**Recommended Approach:** Use a **management command** (`create_admin_user`) integrated into the Docker deployment workflow, NOT a data migration. This follows Django best practices and the project's existing patterns.

---

## 1. Django Migrations vs Alembic: Why Django Migrations Are Appropriate

### 1.1 Clarifying the Tool Confusion

The user mentioned "alembic" but the project **uses Django migrations exclusively**. This is correct because:

| Aspect | Django Migrations | Alembic |
|--------|------------------|---------|
| ORM Integration | Native Django ORM | SQLAlchemy-focused |
| Project Stack | Django 5.2 LTS | Not used in this project |
| Migration Storage | `django_migrations` table | Separate version table |
| Auto-detection | `makemigrations` scans models | Requires SQLAlchemy models |

### 1.2 Django Migrations Are Appropriate For

Django migrations are the **correct tool** for:

1. **Schema changes** (creating/deleting tables, columns, indexes)
2. **Model state changes** (field alterations, constraints)
3. **Database-level operations** (triggers, indexes, constraints)

### 1.3 Django Migrations Are NOT Appropriate For

Data migrations should be avoided for:

1. **User creation** - Environment-specific credentials cannot be safely stored in migrations
2. **Secret management** - Passwords should never be in version control
3. **One-time operations** - Better handled by management commands
4. **Operations requiring user input** - Migrations should be automated

---

## 2. How to Create Admin User: Management Command Approach

### 2.1 The Recommended Pattern

Create a dedicated management command following the project's existing patterns:

**File:** `src/backend/apps/core/management/commands/create_admin_user.py`

```python
"""
Management command to create an admin user for Django admin site.

Creates a user with placeholder telegram_id for username/password authentication.
This is needed because the User model uses telegram_id as USERNAME_FIELD,
but admin users typically authenticate with username/password.

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

        # Idempotent: skip if user already exists
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
            f"Admin user created successfully:\n"
            f"  username: {username}\n"
            f"  telegram_id: {telegram_id}\n"
            f"  is_staff: True\n"
            f"  is_superuser: True"
        ))
```

### 2.2 Why Not a Data Migration?

**Reasons NOT to use a data migration:**

1. **Environment-specific credentials** - Passwords and usernames vary by environment
2. **Secrets in version control** - Never commit passwords to migrations
3. **Non-idempotent by default** - Migrations run once; admin creation may need re-runs
4. **No rollback mechanism** - User deletion on migration rollback is dangerous
5. **Complex conditional logic** - Environment detection in migrations is anti-pattern

---

## 3. Alternative: Data Migration Approach (NOT Recommended)

If you insist on using a migration, here's the pattern (but this is NOT recommended):

### 3.1 Migration Structure

**File:** `src/backend/apps/users/migrations/0002_create_admin_user.py`

```python
# Data migration for admin user creation
# NOT RECOMMENDED - use management command instead

from django.db import migrations


def create_admin_user(apps, schema_editor):
    """Create initial admin user from environment variables."""
    import os
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    # Check if admin credentials are configured
    admin_password = os.getenv("ADMIN_PASSWORD")
    if not admin_password:
        # Skip silently - admin will be created manually
        return
    
    telegram_id = int(os.getenv("ADMIN_TELEGRAM_ID", "-1"))
    username = os.getenv("ADMIN_USERNAME", "admin")
    
    # Idempotent check
    if User.objects.filter(telegram_id=telegram_id).exists():
        return
    
    user = User.objects.create(
        username=username,
        telegram_id=telegram_id,
        chat_id=telegram_id,
        is_staff=True,
        is_superuser=True,
    )
    user.set_password(admin_password)
    user.save()


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_admin_user, migrations.RunPython.noop),
    ]
```

### 3.2 Problems with This Approach

| Issue | Impact |
|-------|--------|
| Secrets in migrations | Password exposure in version control |
| Environment detection | Complex, error-prone |
| Non-idempotent | Cannot safely re-run |
| Test conflicts | Tests may fail due to user existence |
| CI/CD complexity | Secrets management in pipelines |

---

## 4. Migration Dependencies and Ordering

### 4.1 Current Migration Order (Users App)

```
0001_initial.py        → Creates User and LoginToken models
0002_user_chat_id.py   → Adds chat_id field
0003_user_is_declined.py → Adds is_declined field
0004_remove_user_hard_delete_at.py → Removes hard_delete_at field
```

### 4.2 Management Command Integration

The management command runs **after migrations**, not as a migration:

```
db → migrate → web/bot start
                    ↑
                    └── create_admin_user (if env vars set)
```

### 4.3 Docker Compose Service Dependency Chain

```yaml
services:
  db:
    # PostgreSQL database
  
  migrate:
    # Runs migrations with advisory lock
    depends_on: db
  
  create_admin:
    # Optional: creates admin user
    depends_on: migrate
  
  web:
    # Gunicorn web server
    depends_on: migrate
  
  bot:
    # Telegram bot
    depends_on: migrate
```

---

## 5. Handling Environment-Specific Credentials

### 5.1 Environment Variables Pattern

Use environment variables for all environment-specific values:

```env
# .env.example additions
# Admin user credentials for Django admin site
ADMIN_USERNAME=admin
ADMIN_PASSWORD=  # Set via secret management in production
ADMIN_TELEGRAM_ID=-1  # Placeholder ID for admin users
```

### 5.2 Docker Compose Integration

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

### 5.3 Security Best Practices

1. **Never commit .env files** - Add to `.gitignore`
2. **Use secret managers in production** - HashiCorp Vault, AWS Secrets Manager, Docker secrets
3. **Negative telegram_id** - Use `-1` as placeholder (won't collide with real Telegram IDs)
4. **Idempotent creation** - Safe to run multiple times

---

## 6. Best Practices for Seeding Initial Admin Users

### 6.1 Follow Django Patterns

1. **Use management commands** for data operations
2. **Leverage `get_user_model()`** for custom user models
3. **Use `set_password()`** for proper password hashing

### 6.2 Project-Specific Considerations

Based on the User model:

```python
class User(AbstractUser):
    username = models.CharField(max_length=150, blank=True, null=True)
    telegram_id = models.BigIntegerField(unique=True)
    chat_id = models.BigIntegerField(unique=True)
    USERNAME_FIELD = "telegram_id"
```

Key considerations:

1. **`telegram_id` is required** - Must provide a placeholder value
2. **`chat_id` is required** - Use same placeholder as `telegram_id`
3. **Username is nullable** - Can store admin username for display
4. **`is_staff` and `is_superuser`** - Set both for full admin access

### 6.3 Production Deployment Checklist

- [ ] Add `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_TELEGRAM_ID` to `.env.example`
- [ ] Create management command in `apps/core/management/commands/`
- [ ] Add `create_admin` service to `docker-compose.yml`
- [ ] Update documentation for admin password setup
- [ ] Test in development environment
- [ ] Document secret management for production

---

## 7. Comparison: Management Command vs Data Migration

| Criteria | Management Command | Data Migration |
|----------|-------------------|----------------|
| Environment variables | ✅ Natural fit | ❌ Complex |
| Secret security | ✅ Can skip if not set | ❌ May require defaults |
| Idempotency | ✅ Built-in | ❌ Manual |
| Error handling | ✅ Clear messages | ❌ Silent failures |
| Testing | ✅ Easy to test | ❌ Hard to test |
| CI/CD friendly | ✅ Yes | ❌ Requires secrets |
| Follows Django patterns | ✅ Yes | ❌ Anti-pattern |
| Rollback safety | ✅ N/A (one-time) | ❌ Dangerous |

**Verdict:** Management command is the correct approach.

---

## 8. Implementation Steps

### 8.1 Create the Management Command

```bash
mkdir -p src/backend/apps/core/management/commands
touch src/backend/apps/core/management/__init__.py
touch src/backend/apps/core/management/commands/__init__.py
# Create create_admin_user.py
```

### 8.2 Update Environment Template

Add to `.env.example`:

```env
# Admin user credentials for Django admin site
ADMIN_USERNAME=admin
ADMIN_PASSWORD=
ADMIN_TELEGRAM_ID=-1
```

### 8.3 Update Docker Compose

Add the `create_admin` service after `migrate`.

### 8.4 Documentation Updates

Update `docs/ops/docker-deployment.md` with admin setup instructions.

---

## 9. References

- [Django Management Commands](https://docs.djangoproject.com/en/stable/howto/custom-management-commands/)
- [Django Custom User Models](https://docs.djangoproject.com/en/stable/topics/auth/customizing/)
- [Django Admin Authentication](https://docs.djangoproject.com/en/stable/ref/contrib/admin/)
- [PostgreSQL Advisory Locks](https://www.postgresql.org/docs/current/functions-advisory.html)
- [Project Architecture](docs/99-agent/architecture.md)
- [DB Schema](docs/02-database/db-schema.md)
- [User Model](src/backend/apps/users/models.py)
- [Existing Data Migrations](src/backend/apps/categories/migrations/0002_seed_categories.py)
- [Advisory Lock Utility](src/backend/apps/core/utils/advisory_lock.py)

---

## 10. Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-07-22 | Use management command, not data migration | Environment-specific credentials, Django best practices, project patterns |
| 2026-07-22 | Use `telegram_id=-1` as placeholder | Won't collide with real Telegram IDs (always positive) |
| 2026-07-22 | Make admin creation optional | Skip if `ADMIN_PASSWORD` not set; allows manual creation in dev |
| 2026-07-22 | Integrate into Docker workflow | One-shot service after migrations, follows existing pattern |

---

## Conclusion

**Django migrations are NOT the appropriate tool for admin user creation.** Management commands are the correct Django pattern for data operations that require environment-specific configuration. The project should implement a `create_admin_user` management command integrated into the Docker deployment workflow, following the existing patterns for one-shot services with advisory locks.