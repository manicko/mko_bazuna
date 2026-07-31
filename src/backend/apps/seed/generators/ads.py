"""AdGenerator for seed data — creates fake Ad instances."""

from __future__ import annotations

import json
import logging
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from apps.ads.models import Ad
from apps.categories.models import Category
from apps.core.enums import AdSource, AdStatus
from apps.locations.models import City
from apps.seed.generators.base import BaseGenerator
from apps.users.models import User

logger = logging.getLogger(__name__)

ADS_FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "ads.json"


class AdGenerator(BaseGenerator):
    """Generates fake Ad instances for seed data.

    Reads title/description templates from ads.json fixture, assigns
    random users/categories/cities, and applies status distribution weights.
    """

    def __init__(
        self,
        config: dict[str, Any],
        users: list[User],
        categories: list[Category],
        cities: list[City],
    ) -> None:
        """Initialize the ad generator.

        Args:
            config: Parsed seed configuration dict.
            users: List of existing User instances (must be saved to DB).
            categories: List of existing Category instances.
            cities: List of existing City instances.
        """
        super().__init__(config)
        self.users = users
        self.categories = categories
        self.cities = cities
        self.templates = self._load_templates()

    def _load_templates(self) -> list[dict[str, str]]:
        """Load ad title/description templates from fixture file."""
        if not ADS_FIXTURE_PATH.exists():
            logger.warning("Ads fixture not found at %s, using fallback", ADS_FIXTURE_PATH)
            return [{"title": "Товар", "description": "Описание товара. {category}"}]
        with open(ADS_FIXTURE_PATH, encoding="utf-8") as f:
            return json.load(f)

    def generate(
        self,
        ad_count: int,
        status_weights: dict[str, float] | None = None,
    ) -> list[Ad]:
        """Generate a list of unsaved Ad instances.

        Args:
            ad_count: Number of ads to generate.
            status_weights: Dict mapping status string to weight (e.g.
                {"published": 0.6, "archived": 0.2, ...}). If None,
                uses config defaults.

        Returns:
            List of Ad instances (not yet saved to DB).
        """
        if status_weights is None:
            status_weights = self.config.get("status_distribution", {})

        # Normalize weights
        statuses, weights = self._normalize_weights(status_weights)

        now = datetime.now(UTC)
        ads: list[Ad] = []

        for _ in range(ad_count):
            template = random.choice(self.templates)
            category = random.choice(self.categories)
            user = random.choice(self.users)
            city = random.choice(self.cities)
            status = self._weighted_status(statuses, weights)

            title = template["title"]
            description = template["description"].replace("{category}", category.name)

            # Generate price based on category
            price = self._generate_price(category)

            # Build timestamps consistent with status
            published_at = None
            archived_at = None
            moderation_failed_at = None
            rejected_at = None

            if status == AdStatus.PUBLISHED:
                published_at = self._random_date(now - timedelta(days=60), now)
            elif status == AdStatus.ARCHIVED:
                published_at = self._random_date(
                    now - timedelta(days=90), now - timedelta(days=61)
                )
                archived_at = self._random_date(
                    now - timedelta(days=30), now - timedelta(days=1)
                )
            elif status == AdStatus.ON_MODERATION:
                published_at = now
            elif status == AdStatus.REJECTED:
                rejected_at = self._random_date(now - timedelta(days=30), now)
            elif status == AdStatus.ON_MODERATION_FAILED:
                moderation_failed_at = self._random_date(
                    now - timedelta(days=30), now
                )

            ad = Ad(
                user=user,
                title=title,
                description=description,
                price=price,
                category=category,
                city=city,
                category_name=category.name,
                status=status,
                source=AdSource.SEED,
                published_at=published_at,
                archived_at=archived_at,
                moderation_failed_at=moderation_failed_at,
                rejected_at=rejected_at,
            )
            ads.append(ad)

        return ads

    def _normalize_weights(
        self,
        status_weights: dict[str, float],
    ) -> tuple[list[AdStatus], list[float]]:
        """Convert string status weights to AdStatus enum and normalize."""
        status_map: dict[str, AdStatus] = {
            "published": AdStatus.PUBLISHED,
            "archived": AdStatus.ARCHIVED,
            "draft": AdStatus.DRAFT,
            "on_moderation": AdStatus.ON_MODERATION,
            "rejected": AdStatus.REJECTED,
        }
        statuses: list[AdStatus] = []
        weights: list[float] = []

        for key, weight in status_weights.items():
            if key in status_map and weight > 0:
                statuses.append(status_map[key])
                weights.append(weight)

        # Fallback if no valid weights
        if not statuses:
            statuses = [AdStatus.PUBLISHED]
            weights = [1.0]

        return statuses, weights

    def _weighted_status(
        self,
        statuses: list[AdStatus],
        weights: list[float],
    ) -> AdStatus:
        """Select a status using weighted random selection."""
        return random.choices(statuses, weights=weights, k=1)[0]

    def _generate_price(self, category: Category) -> int | None:
        """Generate a price appropriate for the category."""
        # Real estate: higher prices
        real_estate_slugs = {"kvartiry", "doma", "kommercheskaya", "uchastki"}
        # Vehicles
        vehicle_slugs = {"avtomobili", "mototsikly", "vodnyy"}

        if category.slug in real_estate_slugs:
            return self.faker.random_int(20000, 500000)
        elif category.slug in vehicle_slugs:
            return self.faker.random_int(2000, 80000)
        elif category.slug == "telefony":
            return self.faker.random_int(100, 1500)
        elif category.slug in {"kompyutery", "foto"}:
            return self.faker.random_int(200, 3000)
        else:
            # 20% chance of no price (free / negotiable)
            if self.faker.random_int(0, 99) < 20:
                return None
            return self.faker.random_int(10, 5000)