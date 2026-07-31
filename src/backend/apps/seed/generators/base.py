"""Base generator classes for seed data generation.

Provides shared Faker instance with deterministic seed, datetime helpers,
and weighted random selection utilities used by all generators.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta
from typing import Any

from faker import Faker

logger = logging.getLogger(__name__)


class BaseGenerator:
    """Base class for seed data generators.

    Provides a shared, seeded Faker instance (ru_RU locale) and helper
    methods for random selection and date generation.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the generator with a config dict.

        Args:
            config: Parsed configuration dict (e.g. from seed.default.json).
        """
        self.config = config
        self.faker = Faker("ru_RU")
        self.faker.seed_instance(config.get("faker_seed", 42))

    def _random_choice(
        self,
        options: list[Any],
        weights: list[float] | None = None,
    ) -> Any:
        """Weighted random selection from a list of options.

        Args:
            options: List of items to choose from.
            weights: Optional list of weights (same length as options).
                     If None, uniform random selection is used.

        Returns:
            A single item from options.
        """
        if weights:
            return random.choices(options, weights=weights, k=1)[0]
        return random.choice(options)

    def _random_date(
        self,
        start: datetime,
        end: datetime,
    ) -> datetime:
        """Generate a random datetime between start and end inclusive.

        Args:
            start: Lower bound datetime.
            end: Upper bound datetime.

        Returns:
            A random datetime in the [start, end] range.
        """
        delta = end - start
        if delta.total_seconds() <= 0:
            return start
        random_seconds = random.randint(0, int(delta.total_seconds()))
        return start + timedelta(seconds=random_seconds)

    def _chunked(
        self,
        items: list[Any],
        size: int,
    ) -> list[list[Any]]:
        """Split a list into chunks of the given size.

        Args:
            items: The list to split.
            size: Maximum chunk size.

        Returns:
            List of chunks (each chunk is a sub-list).
        """
        return [items[i : i + size] for i in range(0, len(items), size)]