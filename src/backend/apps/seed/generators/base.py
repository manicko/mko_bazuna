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
        # Each generator instance gets its own ``random.Random`` seeded from
        # ``faker_seed``. This makes output fully deterministic and isolated:
        # two generators constructed with the same seed produce identical
        # sequences regardless of execution order or interleaving with other
        # generators. We intentionally do NOT seed the global ``random`` module,
        # as that would cause cross-generator interference.
        self._rng = random.Random(config.get("faker_seed", 42))

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
            return self._rng.choices(options, weights=weights, k=1)[0]
        return self._rng.choice(options)

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
        random_seconds = self._rng.randint(0, int(delta.total_seconds()))
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