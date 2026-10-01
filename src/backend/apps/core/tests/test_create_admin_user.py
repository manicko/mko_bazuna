"""
Tests for create_admin_user management command.

Verifies:
- Successful admin user creation with correct flags
- Idempotent behavior (skip on duplicate telegram_id or username)
- Dry-run mode does not create any records
- Empty password validation
- Advisory lock usage
- Password resolution from the ADMIN_PASSWORD environment fallback
- Enforcement of AUTH_PASSWORD_VALIDATORS on the create path only (after the
  three early returns), via TestCreateAdminUserPasswordPolicy
"""

from io import StringIO

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import UserAttributeSimilarityValidator
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command

from apps.core.enums import AdvisoryLockId

User = get_user_model()

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


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
            password="pass123-strong",
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
            password="pass123-strong",
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
            password="pass123-strong",
            telegram_id=-10,
            stdout=out1,
        )

        out2 = StringIO()
        call_command(
            "create_admin_user",
            username="rerunadmin",
            password="pass123-strong",
            telegram_id=-10,
            stdout=out2,
        )

        assert User.objects.filter(username="rerunadmin").count() == 1
        assert "already exists, skipping" in out2.getvalue()

    def test_command_dry_run_does_not_leak_telegram_id(self, caplog) -> None:
        """Dry-run mode must not leak raw telegram_id in stdout or caplog."""
        telegram_id = 999888777
        out = StringIO()
        with caplog.at_level("INFO"):
            call_command(
                "create_admin_user",
                username="leaktest",
                password="testpass123",
                telegram_id=telegram_id,
                dry_run=True,
                stdout=out,
            )

        stdout_output = out.getvalue()
        # Raw telegram_id must not appear in stdout
        assert str(telegram_id) not in stdout_output
        # Masked value should be present for log correlation
        assert "tg_" in stdout_output
        # Raw telegram_id must not appear in any log output
        assert str(telegram_id) not in caplog.text

    def test_password_resolved_from_environment_when_flag_absent(self, monkeypatch):
        """With --password omitted the command reads ADMIN_PASSWORD (CFG-003)."""
        monkeypatch.setenv("ADMIN_PASSWORD", "test-admin-password")
        call_command("create_admin_user", username="envadmin", telegram_id=-1)
        assert User.objects.get(username="envadmin").check_password(
            "test-admin-password"
        )

    def test_explicit_password_flag_wins_over_environment(self, monkeypatch):
        """--password takes precedence over ADMIN_PASSWORD when both are present."""
        monkeypatch.setenv("ADMIN_PASSWORD", "test-admin-password")
        call_command(
            "create_admin_user",
            username="flagadmin",
            password="flag-wins-strong",
            telegram_id=-1,
        )
        user = User.objects.get(username="flagadmin")
        assert user.check_password("flag-wins-strong")
        assert not user.check_password("test-admin-password")

    def test_empty_password_flag_does_not_fall_back_to_environment(self, monkeypatch):
        """An explicitly empty --password must fail, not silently use the environment.

        Guards D2: a falsiness-triggered fallback would hand the operator a different
        password than the one they typed.
        """
        monkeypatch.setenv("ADMIN_PASSWORD", "test-admin-password")
        with pytest.raises(CommandError, match="Password cannot be empty"):
            call_command(
                "create_admin_user",
                username="emptyflag",
                password="",
                telegram_id=-1,
            )
        assert not User.objects.filter(username="emptyflag").exists()

    def test_no_password_flag_and_no_env_password_raises(self, monkeypatch):
        """Neither flag nor environment: the existing empty-password error fires."""
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
        with pytest.raises(CommandError, match="Password cannot be empty"):
            call_command("create_admin_user", username="nopassnoenv", telegram_id=-1)
        assert not User.objects.filter(username="nopassnoenv").exists()


class TestCreateAdminUserPasswordPolicy:
    """The bootstrap path enforces AUTH_PASSWORD_VALIDATORS.

    The validation call sits after every early return, so an idempotent re-run
    against an existing operator stays a silent no-op. These tests pin both the
    enforcement and the ordering.
    """

    def test_weak_password_is_rejected_and_creates_no_user(self):
        """A password below the minimum length raises and writes no row."""
        before = User.objects.count()
        with pytest.raises(CommandError, match="password policy"):
            call_command(
                "create_admin_user",
                username="weakadmin",
                password="short",
                telegram_id=-1,
            )
        assert User.objects.count() == before
        assert not User.objects.filter(username="weakadmin").exists()

    def test_strong_password_creates_an_authenticable_admin(self):
        """The anti-vacuity control: a valid password reaches, and completes, create.

        Asserts the stored credential is hashed and authenticates, so a test that
        never exercised the create path cannot pass.
        """
        raw = "V4lid-Str0ng!Pass"
        call_command(
            "create_admin_user",
            username="strongadmin",
            password=raw,
            telegram_id=-1,
        )
        user = User.objects.get(username="strongadmin")
        assert user.password != raw
        assert user.check_password(raw) is True

    def test_existing_telegram_id_skips_without_validating(self):
        """An existing telegram_id returns the WARNING even if the password is weak.

        Pins the ordering decision: validation must not run above the early
        returns, or a normal bootstrap re-run would start failing.
        """
        User.objects.create(
            username="existing", telegram_id=-1, chat_id=-1
        )
        out = StringIO()
        call_command(
            "create_admin_user",
            username="newadmin",
            password="short",
            telegram_id=-1,
            stdout=out,
        )
        assert "already exists, skipping" in out.getvalue()
        assert not User.objects.filter(username="newadmin").exists()

    def test_existing_username_skips_without_validating(self):
        """An existing username returns the WARNING even if the password is weak."""
        User.objects.create(username="existing", telegram_id=-2, chat_id=-2)
        out = StringIO()
        call_command(
            "create_admin_user",
            username="existing",
            password="short",
            telegram_id=-1,
            stdout=out,
        )
        assert "already exists, skipping" in out.getvalue()
        assert User.objects.filter(username="existing").count() == 1

    def test_empty_password_keeps_the_existing_error(self):
        """The empty-password message is unchanged by the policy block."""
        with pytest.raises(CommandError, match="Password cannot be empty"):
            call_command(
                "create_admin_user",
                username="emptyadmin",
                password="",
                telegram_id=-1,
            )
        assert not User.objects.filter(username="emptyadmin").exists()

    def test_similarity_validator_is_wired_but_inert_without_a_user(self):
        """Pin the similarity validator's actual behaviour on the bootstrap path.

        Django's ``UserAttributeSimilarityValidator.validate`` returns immediately
        when ``user`` is ``None``. The command has no ``User`` instance before the
        row is created, and the brief forbids constructing a throwaway unsaved one,
        so similarity is inert *here* by design. This test is therefore not
        vacuous: it proves the validator is present in the configured policy and
        that it genuinely rejects when handed a user, while pinning the documented
        bootstrap behaviour (creation succeeds).
        """
        configured = [entry["NAME"] for entry in settings.AUTH_PASSWORD_VALIDATORS]
        assert (
            "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
            in configured
        )

        validator = UserAttributeSimilarityValidator()
        with pytest.raises(ValidationError, match="too similar"):
            validator.validate("administrator1", user=User(username="administrator"))

        username = "administrator"
        call_command(
            "create_admin_user",
            username=username,
            password=f"{username}1",
            telegram_id=-1,
        )
        assert User.objects.filter(username=username).exists()

    def test_dry_run_creates_no_user_and_skips_validation(self):
        """Dry-run returns before validation and still writes nothing."""
        out = StringIO()
        call_command(
            "create_admin_user",
            username="dryadmin",
            password="short",
            telegram_id=-1,
            dry_run=True,
            stdout=out,
        )
        assert "DRY RUN" in out.getvalue()
        assert not User.objects.filter(username="dryadmin").exists()
