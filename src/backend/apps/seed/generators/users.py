"""UserGenerator for seed data — creates fake seller User instances."""

from __future__ import annotations

import itertools
import logging
from typing import Any

from django.contrib.auth.hashers import make_password

from apps.seed.generators.base import BaseGenerator
from apps.users.models import User

logger = logging.getLogger(__name__)


class UserGenerator(BaseGenerator):
    """Generates fake seller User instances for seed data.

    Uses itertools.count() for guaranteed unique telegram_id and chat_id
    values. 30% of users get a non-null username.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the user generator.

        Args:
            config: Parsed seed configuration dict.
        """
        super().__init__(config)
        self._telegram_id_counter = itertools.count(start=10_000)
        self._unusable_password = make_password(None)

    def generate(self, count: int) -> list[User]:
        """Generate a list of unsaved User instances.

        Args:
            count: Number of users to generate.

        Returns:
            List of User instances (not yet saved to DB).
        """
        users: list[User] = []
        for _ in range(count):
            telegram_id = next(self._telegram_id_counter)
            user = User(
                telegram_id=telegram_id,
                chat_id=telegram_id,
                username=self._maybe_username(),
                first_name=self.faker.first_name(),
                last_name=self.faker.last_name(),
                password=self._unusable_password,
                is_active=True,
                is_banned=False,
                is_deleted=False,
                is_declined=False,
                consent_given_at=self.faker.date_time_this_decade(),
                ads_auto_publish=True,
                telegram_premium=False,
            )
            users.append(user)
        return users

    def _maybe_username(self) -> str | None:
        """Generate a username ~30% of the time."""
        if self.faker.random_int(0, 99) < 30:
            # Ensure uniqueness by appending a small random suffix
            return f"{self.faker.user_name()}_{self.faker.random_int(100, 999)}"
        return None