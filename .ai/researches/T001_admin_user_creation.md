# Admin User Creation for Django Admin Site

**Status:** Research Complete  
**Date:** 2026-07-22  
**Domain:** Admin Authentication / User Management  

---

## Executive Summary

The Mko Bazuna project uses a custom User model with `telegram_id` as the `USERNAME_FIELD`, which creates a conflict with Django's default admin authentication expectations. This document analyzes the constraints and provides a recommended approach for creating an admin user with username/password authentication.

**Recommended Solution:** Create a dedicated management command `create_admin_user` that creates a user with a placeholder `telegram_id` and sets appropriate admin flags. This integrates cleanly with the existing Docker migration workflow.

---

## 1. Analysis of Current User Model Constraints

### 1.1 Model Definition

```python
class User(AbstractUser):
    username = models.CharField(
        "username",
        max_length=150,
        blank=True,
        null=True,  # Nullable!
        help_text="Optional public @username; NOT used for t.me link or publishing",
    )

    telegram_id = models.BigIntegerField(unique=True)  # Required, unique
    chat_id = models.BigIntegerField(unique=True)

    # Admin flags inherited from AbstractUser
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    USERNAME_FIELD = "telegram_id"  # Primary auth field!
```

### 1.2 Key Constraints

| Constraint | Impact |
|------------|--------|
| `USERNAME_FIELD = "telegram_id"` | Django authentication uses `telegram_id` as the login field, NOT `username` |
| `username` is nullable | The `username` field cannot be used for authentication |
| `telegram_id` is required & unique | Every user must have a valid Telegram ID |
| `chat_id` is required | Used for bot communication, must be unique |

### 1.3 Django Admin Implications

By default, Django admin's authentication form will:
- Show "Telegram ID" as the login field (not "Username")
- Require a valid `telegram_id` to authenticate
- NOT show a password field for the username field (since it's not the USERNAME_FIELD)

This means the admin login form will look for `telegram_id` and `password`, not `username` and `password`.

---

## 2. Recommended Approach: Management Command

### 2.1 Why a Management Command?

**Advantages over alternatives:**

| Approach | Pros | Cons |
|----------|------|------|
| **Management Command** (Recommended) | Clean separation, follows project patterns, idempotent, Docker-friendly | Requires running command |
| Custom Auth Backend | Flexible, can support both | Complex, changes core auth flow |
| Model Modification | Native Django behavior | Requires migrations, breaks existing pattern |

### 2.2 Command Design

**File:** `src/backend/apps/core/management/commands/create_admin_user.py`

```python
"""
Management command to create an admin user for Django admin site.

Creates a user with placeholder telegram_id for username/password authentication.
This is needed because the User model uses telegram_id as USERNAME_FIELD,
but admin users typically authenticate with username/password.

Usage:
    uv run python src/backend/manage.py create_admin_user \
        --username admin \
        --password <password> \
        --telegram-id -1
"""

import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Create an admin user for Django admin site with username/password authentication"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--username",
            type=str,
            required=True,
            help="Admin username (stored in username field, visible in admin)",
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

        # Check if user already exists
        if User.objects.filter(telegram_id=telegram_id).exists():
            raise CommandError(
                f"User with telegram_id={telegram_id} already exists. "
                "Use a different telegram_id or --dry-run to check."
            )

        if User.objects.filter(username=username).exists():
            raise CommandError(
                f"User with username='{username}' already exists. "
                "Use a different username or --dry-run to check."
            )

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

        self.stdout.write(self.style.SUCCESS(
            f"Successfully created admin user:\n"
            f"  username: {username}\n"
            f"  telegram_id: {telegram_id}\n"
            f"  is_staff: True\n"
            f"  is_superuser: True"
        ))
```

### 2.3 Admin Login Behavior

With this approach, the Django admin login form will:
1. Show "Telegram ID" as the primary login field
2. Accept the placeholder telegram_id (e.g., `-1`) as the username
3. Accept the password for authentication

**Important:** The admin login form will display "Telegram ID" as the field label, not "Username". This is expected behavior given the `USERNAME_FIELD` setting.

---

## 3. Integration with Docker Deployment

### 3.1 Development Workflow

```bash
# After starting containers
docker compose run --rm migrate

# Create admin user
docker compose run --rm web uv run python src/backend/manage.py create_admin_user \
    --username admin \
    --password your_secure_password \
    --telegram-id -1
```

### 3.2 Production Workflow

**Option A: Manual creation (recommended for production)**

After deployment, manually create the admin user:

```bash
docker compose run --rm web uv run python src/backend/manage.py create_admin_user \
    --username admin \
    --password "${ADMIN_PASSWORD}" \
    --telegram-id -1
```

**Option B: Environment-based creation**

Add to `docker-compose.yml` after the migrate service:

```yaml
create_admin:
  build:
    context: .
    dockerfile: docker/Dockerfile
  command: uv run python src/backend/manage.py create_admin_user \
      --username "${ADMIN_USERNAME:-admin}" \
      --password "${ADMIN_PASSWORD}" \
      --telegram-id -1
  depends_on:
    migrate:
      condition: service_completed_successfully
  environment:
    - UV_PROJECT_ENVIRONMENT=/opt/venv
    - DJANGO_SETTINGS_MODULE=config.settings.prod
    - ADMIN_USERNAME=admin
    - ADMIN_PASSWORD
  env_file:
    - .env
  # One-shot service: runs once, then exits
```

### 3.3 CI/CD Integration

For automated deployments, add a step after migrations:

```yaml
# Example GitLab CI
create_admin_user:
  stage: deploy
  script:
    - docker compose run --rm web uv run python src/backend/manage.py create_admin_user \
        --username "${ADMIN_USERNAME}" \
        --password "${ADMIN_PASSWORD}" \
        --telegram-id -1
  only:
    - main
```

---

## 4. Environment Variable Configuration

Add to `.env.example`:

```env
# Admin user credentials for Django admin site
# Note: Admin login uses telegram_id, so you'll enter the telegram_id value
# as the username in the admin login form.
ADMIN_USERNAME=admin
ADMIN_PASSWORD=  # Set in production via secret management
ADMIN_TELEGRAM_ID=-1  # Placeholder ID for admin users
```

---

## 5. Security Considerations

### 5.1 Placeholder Telegram ID Selection

**Recommended: `-1`**

- Negative numbers are unlikely to collide with real Telegram IDs (which are positive)
- Clearly indicates a placeholder/admin account
- Easy to identify in the database

**Alternative: `0`**

- Also a placeholder value
- May be easier to remember

### 5.2 Password Requirements

- Use strong, unique passwords
- Consider using a password manager to generate and store
- In production, inject via secret management (HashiCorp Vault, AWS Secrets Manager, etc.)

### 5.3 Environment Variable Security

- Never commit `.env` file to version control
- Use different admin credentials for each environment
- Rotate admin passwords periodically

### 5.4 Admin Account Visibility

The admin user will be visible in the Django admin list with:
- `username` field showing the admin username
- `telegram_id` field showing the placeholder value
- `is_staff` and `is_superuser` flags set to True

This is acceptable for admin accounts and helps identify placeholder users.

---

## 6. Alternative: Custom Authentication Backend

If you need the admin login form to show "Username" instead of "Telegram ID", you can create a custom authentication backend:

```python
# apps/users/backends.py
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

Then add to `settings/base.py`:

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

## 7. Testing the Implementation

### 7.1 Unit Tests

Create `src/backend/apps/users/tests/test_admin_user_creation.py`:

```python
import pytest
from django.core.management import call_command
from django.contrib.auth import get_user_model
from io import StringIO

User = get_user_model()

pytestmark = [pytest.mark.django_db]


class TestCreateAdminUser:
    def test_create_admin_user_success(self):
        """Test successful admin user creation."""
        out = StringIO()
        call_command(
            "create_admin_user",
            username="testadmin",
            password="testpass123",
            telegram_id=-1,
            stdout=out,
        )

        user = User.objects.get(username="testadmin")
        assert user.telegram_id == -1
        assert user.is_staff is True
        assert user.is_superuser is True
        assert user.check_password("testpass123")

    def test_duplicate_telegram_id_fails(self):
        """Test that duplicate telegram_id raises error."""
        User.objects.create(
            username="existing",
            telegram_id=-1,
            chat_id=-1,
            is_staff=True,
            is_superuser=True,
        )

        with pytest.raises(Exception):  # CommandError
            call_command(
                "create_admin_user",
                username="newadmin",
                password="testpass123",
                telegram_id=-1,
            )

    def test_duplicate_username_fails(self):
        """Test that duplicate username raises error."""
        User.objects.create(
            username="existing",
            telegram_id=-2,
            chat_id=-2,
        )

        with pytest.raises(Exception):  # CommandError
            call_command(
                "create_admin_user",
                username="existing",
                password="testpass123",
                telegram_id=-1,
            )

    def test_dry_run_does_not_create(self):
        """Test that dry-run does not create user."""
        out = StringIO()
        call_command(
            "create_admin_user",
            username="dryadmin",
            password="testpass123",
            telegram_id=-1,
            dry_run=True,
            stdout=out,
        )

        assert not User.objects.filter(username="dryadmin").exists()
```

### 7.2 Integration Test

```bash
# Run the tests
uv run pytest src/backend/apps/users/tests/test_admin_user_creation.py -v

# Test manually in Docker
docker compose run --rm web uv run python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
import django
django.setup()
from django.core.management import call_command
call_command('create_admin_user', '--username', 'testadmin', '--password', 'testpass123', '--telegram-id', '-1')
"
```

---

## 8. Implementation Checklist

- [ ] Create management command `create_admin_user.py`
- [ ] Add unit tests for the command
- [ ] Update `.env.example` with admin credential variables
- [ ] Update `docker-compose.yml` to optionally create admin user
- [ ] Update documentation (`docs/ops/docker-deployment.md`)
- [ ] Run lint and type checks
- [ ] Test in development environment

---

## 9. References

- [Django Custom User Models](https://docs.djangoproject.com/en/stable/topics/auth/customizing/#substituting-a-custom-user-model)
- [Django Management Commands](https://docs.djangoproject.com/en/stable/howto/custom-management-commands/)
- [Django Admin Authentication](https://docs.djangoproject.com/en/stable/ref/contrib/admin/#django.contrib.admin.ModelAdmin)
- [Project Architecture](docs/99-agent/architecture.md)
- [User Model](src/backend/apps/users/models.py)
- [Admin Registration](src/backend/apps/users/admin.py)
- [Docker Deployment](docs/ops/docker-deployment.md)