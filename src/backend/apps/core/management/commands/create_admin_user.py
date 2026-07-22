"""
Management command to create an admin user for Django admin site.

Creates a user with placeholder telegram_id for username/password authentication.
This is needed because the User model uses telegram_id as USERNAME_FIELD.

Usage:
    uv run python manage.py create_admin_user --username admin --password <password> --telegram-id -1

The command is idempotent - it will skip creation if a user with the same
telegram_id already exists.
"""

import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from apps.core.enums import AdvisoryLockId
from apps.core.utils.advisory_lock import advisory_lock

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
            help="Admin password (must be non-empty)",
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

        # Validate password is not empty
        if not password or not password.strip():
            raise CommandError("Password cannot be empty. Please provide a valid password.")

        User = get_user_model()

        # Use advisory lock for idempotent execution across container restarts
        with advisory_lock(AdvisoryLockId.CREATE_ADMIN, session=True):
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
                chat_id=telegram_id,
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