"""
Tests for create_admin_user management command.

Verifies:
- Successful admin user creation with correct flags
- Idempotent behavior (skip on duplicate telegram_id or username)
- Dry-run mode does not create any records
- Empty password validation
- Advisory lock usage
"""

from io import StringIO

import pytest
from django.core.management import call_command, CommandError
from django.contrib.auth import get_user_model

from apps.core.enums import AdvisoryLockId

User = get_user_model()

pytestmark = [pytest.mark.django_db]


class TestCreateAdminUser:
    """Tests for create_admin_user management command."""

    def test_create_admin_user_success(self):
        """Test successful admin user creation with correct attributes."""
        out = StringIO()
        call_command(
            "create_admin_user",
            username="admin",
            password="securepass123",
            telegram_id=-1,
            stdout=out,
        )

        user = User.objects.get(username="admin")
        assert user.telegram_id == -1
        assert user.chat_id == -1
        assert user.is_staff is True
        assert user.is_superuser is True
        assert user.check_password("securepass123")
        assert "Admin user created" in out.getvalue()

    def test_create_with_custom_telegram_id(self):
        """Test creation with a custom placeholder telegram_id."""
        call_command(
            "create_admin_user",
            username="customadmin",
            password="pass123",
            telegram_id=999,
        )

        user = User.objects.get(username="customadmin")
        assert user.telegram_id == 999
        assert user.chat_id == 999

    def test_create_with_email(self):
        """Test creation with optional email."""
        call_command(
            "create_admin_user",
            username="emailadmin",
            password="pass123",
            email="admin@example.com",
        )

        user = User.objects.get(username="emailadmin")
        assert user.email == "admin@example.com"

    def test_duplicate_telegram_id_skips_with_warning(self):
        """Test idempotent behavior: duplicate telegram_id skips with warning."""
        User.objects.create(
            username="existing",
            telegram_id=-1,
            chat_id=-1,
            is_staff=True,
            is_superuser=True,
        )

        out = StringIO()
        call_command(
            "create_admin_user",
            username="newadmin",
            password="testpass123",
            telegram_id=-1,
            stdout=out,
        )

        assert not User.objects.filter(username="newadmin").exists()
        assert "already exists, skipping" in out.getvalue()

    def test_duplicate_username_skips_with_warning(self):
        """Test idempotent behavior: duplicate username skips with warning."""
        User.objects.create(
            username="existing",
            telegram_id=-2,
            chat_id=-2,
        )

        out = StringIO()
        call_command(
            "create_admin_user",
            username="existing",
            password="testpass123",
            telegram_id=-1,
            stdout=out,
        )

        # No new user should be created
        users = User.objects.filter(username="existing")
        assert users.count() == 1
        assert "already exists, skipping" in out.getvalue()

    def test_dry_run_does_not_create_user(self):
        """Test that dry-run mode does not persist any changes."""
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
        assert "DRY RUN" in out.getvalue()

    def test_dry_run_shows_details(self):
        """Test that dry-run prints the intended user details."""
        out = StringIO()
        call_command(
            "create_admin_user",
            username="dryadmin",
            password="testpass123",
            telegram_id=-1,
            email="dry@test.com",
            dry_run=True,
            stdout=out,
        )

        output = out.getvalue()
        assert "DRY RUN" in output
        assert "dryadmin" in output
        assert "is_staff: True" in output
        assert "is_superuser: True" in output

    def test_empty_password_raises_error(self):
        """Test that empty password is rejected with CommandError."""
        with pytest.raises(CommandError, match="Password cannot be empty"):
            call_command(
                "create_admin_user",
                username="nopass",
                password="",
                telegram_id=-1,
            )

    def test_empty_password_whitespace_only_raises_error(self):
        """Test that whitespace-only password is rejected."""
        with pytest.raises(CommandError, match="Password cannot be empty"):
            call_command(
                "create_admin_user",
                username="whitespacepass",
                password="   ",
                telegram_id=-1,
            )

    def test_requires_username_and_password(self):
        """Test that required arguments are enforced.

        ``call_command`` wraps argparse errors as ``CommandError`` (not
        ``SystemExit``, which only occurs when the command is invoked directly
        from the CLI via ``manage.py``).
        """
        with pytest.raises(CommandError, match="--username"):
            call_command("create_admin_user")

    def test_sets_password_correctly(self):
        """Test that the created user can authenticate with the given password."""
        call_command(
            "create_admin_user",
            username="authadmin",
            password="MyStr0ng!Pass",
            telegram_id=-1,
        )

        user = User.objects.get(username="authadmin")
        assert user.check_password("MyStr0ng!Pass") is True
        assert user.check_password("wrong") is False

    def test_lock_id_is_create_admin(self):
        """Verify the advisory lock constant is defined."""
        assert AdvisoryLockId.CREATE_ADMIN == 101

    def test_idempotent_on_rerun(self):
        """Test that re-running the command does not create duplicates."""
        out1 = StringIO()
        call_command(
            "create_admin_user",
            username="rerunadmin",
            password="pass123",
            telegram_id=-10,
            stdout=out1,
        )

        out2 = StringIO()
        call_command(
            "create_admin_user",
            username="rerunadmin",
            password="pass123",
            telegram_id=-10,
            stdout=out2,
        )

        assert User.objects.filter(username="rerunadmin").count() == 1
        assert "already exists, skipping" in out2.getvalue()
