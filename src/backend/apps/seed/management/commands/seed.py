"""Management command to seed the database with demo data.

Usage:
    uv run python manage.py seed [--users 10] [--ads 30] [--force]
        [--status-distribution '{"published":0.6,"archived":0.2,...}']
        [--analytics True]

This is a development-only command. It will DELETE all existing seed data
and regenerate with the specified parameters.
"""

from __future__ import annotations

import json
import logging

from django.core.management.base import BaseCommand, CommandError

from apps.seed.services.seed_service import SeedService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Seed the database with demo data for development."""

    help = "Populate database with demo data for development"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--users",
            type=int,
            default=10,
            help="Number of users to generate (default: 10)",
        )
        parser.add_argument(
            "--ads",
            type=int,
            default=600,
            help="Number of ads to generate (default: 600)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Skip destructive data confirmation prompt",
        )
        parser.add_argument(
            "--status-distribution",
            type=str,
            default=None,
            help=(
                "JSON string with status distribution weights. "
                'Example: \'{"published":0.6,"archived":0.2}\''
            ),
        )
        parser.add_argument(
            "--analytics",
            type=str,
            default="True",
            choices=["True", "False"],
            help="Generate analytics events and metrics (default: True)",
        )

    def handle(self, *args, **options) -> None:
        users = options["users"]
        ads = options["ads"]
        force = options["force"]
        status_distribution = options["status_distribution"]
        analytics_str = options["analytics"]
        analytics = analytics_str == "True"

        # Validate status-distribution JSON if provided
        if status_distribution:
            try:
                parsed = json.loads(status_distribution)
                if not isinstance(parsed, dict):
                    raise CommandError(
                        "--status-distribution must be a JSON object, "
                        f"got {type(parsed).__name__}"
                    )
                # Validate keys are valid status names
                valid_keys = {
                    "published",
                    "archived",
                    "draft",
                    "on_moderation",
                    "rejected",
                }
                for key in parsed:
                    if key not in valid_keys:
                        raise CommandError(
                            f"Invalid status key '{key}' in --status-distribution. "
                            f"Valid keys: {', '.join(sorted(valid_keys))}"
                        )
            except json.JSONDecodeError as e:
                raise CommandError(f"Invalid --status-distribution JSON: {e}") from e

        # Confirmation prompt
        if not force:
            self.stdout.write(
                self.style.WARNING(
                    "This will DELETE all existing seed data and regenerate.\n"
                    "Seed data includes: users (with seed ads), ads, images, "
                    "analytics events, and metrics."
                )
            )
            response = input("Continue? [y/N] ")
            if response.lower() not in ("y", "yes"):
                self.stdout.write(self.style.WARNING("Seed cancelled."))
                return

        # Run seed service
        self.stdout.write(
            self.style.NOTICE(f"Seeding database with {users} users, {ads} ads...")
        )

        try:
            service = SeedService()
            service.run(
                users=users,
                ads=ads,
                force=force,
                status_distribution=status_distribution,
                analytics=analytics,
            )
        except ValueError as e:
            raise CommandError(str(e)) from e

        self.stdout.write(self.style.SUCCESS("Database seeded successfully."))
