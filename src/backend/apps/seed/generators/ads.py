"""AdGenerator for seed data — creates fake Ad instances with multi-language support."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from apps.ads.models import Ad
from apps.categories.models import Category
from apps.categories.services.lookup_resolution import CategoryLookupResolver
from apps.core.enums import AdSource, AdStatus, LanguageLocale
from apps.currencies.enums import CurrencyCode
from apps.locations.models import City
from apps.lookups.models import LookupItem
from apps.seed.generators.base import BaseGenerator
from apps.users.models import User

logger = logging.getLogger(__name__)

ADS_TEMPLATES_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "ads_templates.json"
WORD_LISTS_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "word_lists.json"

# Map category slugs to brand groups
# All 171 leaf slugs from categories.yaml grouped by top-level section
CATEGORY_GROUP_MAP: dict[str, str] = {
    # real-estate → real_estate
    "apartments": "real_estate",
    "houses": "real_estate",
    "rooms": "real_estate",
    "garages": "real_estate",
    "land-plots": "real_estate",
    "other-real-estate": "real_estate",
    "offices": "real_estate",
    "flex-space": "real_estate",
    "retail-spaces": "real_estate",
    "warehouses": "real_estate",
    "commercial-land": "real_estate",
    # transport → transport
    "cars": "transport",
    "motorcycles-sub": "transport",
    "scooters": "transport",
    "bicycles": "transport",
    "scooters-scooters": "transport",
    "trucks-sub": "transport",
    "agricultural-machinery": "transport",
    "commercial-vehicles": "transport",
    "campers": "transport",
    "boats-yachts": "transport",
    "motorboats": "transport",
    "sailing-boats": "transport",
    "personal-watercraft": "transport",
    "parts": "transport",
    "tires-wheels": "transport",
    "auto-accessories": "transport",
    "auto-tools": "transport",
    "auto-equipment": "transport",
    "oils-chemicals": "transport",
    "anti-theft": "transport",
    "gps-navigators": "transport",
    "auto-audio-video": "transport",
    "roof-boxes-hitches": "transport",
    "trailers": "transport",
    # goods → goods
    "women-clothing": "goods",
    "women-shoes": "goods",
    "men-clothing": "goods",
    "men-shoes": "goods",
    "bags-luggage": "goods",
    "accessories": "goods",
    "girls": "goods",
    "boys": "goods",
    "toys": "goods",
    "strollers": "goods",
    "car-seats": "goods",
    "kids-furniture": "goods",
    "feeding-products": "goods",
    "bath-products": "goods",
    "school-supplies": "goods",
    "bed-linen": "goods",
    "kids-scooters-bikes": "goods",
    "kids-hygiene": "goods",
    "makeup-manicure": "goods",
    "perfumes": "goods",
    "care-hygiene": "goods",
    "hair-care": "goods",
    "beauty-appliances": "goods",
    "medical-products": "goods",
    "jewelry": "goods",
    "watches": "goods",
    "costume-jewelry": "goods",
    "furniture-interior": "goods",
    "repair-construction": "goods",
    "appliances": "goods",
    "food-products": "goods",
    "plants": "goods",
    "kitchen-dining": "goods",
    "phones": "goods",
    "audio-video": "goods",
    "computers": "goods",
    "laptops": "goods",
    "tablets": "goods",
    "cameras": "goods",
    "games-consoles-software": "goods",
    "other-electronics": "goods",
    "hobby-bicycles": "goods",
    "hobby-scooters": "goods",
    "books-magazines": "goods",
    "musical-instruments": "goods",
    "sports-outdoors": "goods",
    "tickets-travel": "goods",
    "hunting-fishing": "goods",
    # animals → animals
    "dogs": "animals",
    "cats": "animals",
    "birds": "animals",
    "fish-aquarium": "animals",
    "other-animals": "animals",
    "pet-food": "animals",
    "pet-toys": "animals",
    "pet-accessories": "animals",
    "pet-dogs-cats": "animals",
    "pet-birds": "animals",
    # services-jobs → services
    "phone-repair": "services",
    "laptop-pc-repair": "services",
    "appliance-repair": "services",
    "clothing-repair": "services",
    "shoe-repair": "services",
    "car-repair": "services",
    "flooring-installation": "services",
    "plastering": "services",
    "plumbing": "services",
    "waterproofing": "services",
    "electrical": "services",
    "ac-installation": "services",
    "terraces-balconies": "services",
    "commercial-construction": "services",
    "residential-construction": "services",
    "pc-setup": "services",
    "programming": "services",
    "web-development": "services",
    "hair-styling": "services",
    "manicure": "services",
    "pedicure": "services",
    "skincare": "services",
    "hair-care-services": "services",
    "massage": "services",
    "sport-fitness": "services",
    "beauty-salons-spa": "services",
    "psychology": "services",
    "medicine": "services",
    "tow-truck": "services",
    "taxi": "services",
    "delivery-courier": "services",
    "freight": "services",
    "apartment-cleaning": "services",
    "carpet-cleaning": "services",
    "office-cleaning": "services",
    "cleaning-service": "services",
    "arts": "services",
    "event-planning": "services",
    "photoshoots": "services",
    "florist": "services",
    "tutors": "services",
    "courses-training": "services",
    "accounting": "services",
    "legal-services": "services",
    "tax-planning": "services",
    "property-valuation": "services",
    "translations": "services",
    "security": "services",
    "dog-walking": "services",
    "housekeeping": "services",
    "home-food-service": "services",
    "no-experience-jobs": "services",
    "restaurants": "services",
    "catering": "services",
    "agriculture": "services",
    "trading": "services",
    "warehousing": "services",
    "other-services": "services",
    # business → business
    "ready-business": "business",
    "retail-equipment": "business",
    "food-equipment": "business",
    "office-equipment": "business",
    "industrial-equipment": "business",
    "logistics-warehouse": "business",
    "beauty-equipment": "business",
    "auto-business-equipment": "business",
    "medical-equipment": "business",
    "business-offices": "business",
    "business-flex-space": "business",
    "business-retail-spaces": "business",
    "business-warehouses": "business",
    "business-commercial-land": "business",
    "business-accounting": "business",
    "business-legal-services": "business",
    "business-taxes": "business",
    "business-property-valuation": "business",
    "business-translations": "business",
    # charity → charity
    "charity": "charity",
}


class AdGenerator(BaseGenerator):
    """Generates fake Ad instances for seed data with multi-language content.

    Reads category-specific templates from ads_templates.json with variable
    placeholders ({condition}, {brand}, {feature}, etc.) and fills them using
    word lists and Faker generators. Generates content in Russian, English,
    and Bosnian for each ad.
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
        self.word_lists = self._load_word_lists()

    def _load_templates(self) -> dict[str, list[dict[str, Any]]]:
        """Load ad templates from ads_templates.json, grouped by category_slug.

        Returns:
            Dict mapping category_slug to list of template dicts, plus a
            'default' key for fallback templates.
        """
        if not ADS_TEMPLATES_PATH.exists():
            logger.warning("Templates not found at %s, using fallback", ADS_TEMPLATES_PATH)
            return {
                "default": [
                    {
                        "id": "fallback_1",
                        "patterns": {
                            "ru": {"title": "Товар", "description": "Описание товара."},
                            "en": {"title": "Item", "description": "Item description."},
                            "bs": {"title": "Artikal", "description": "Opis artikla."},
                        },
                    }
                ]
            }

        with open(ADS_TEMPLATES_PATH, encoding="utf-8") as f:
            data = json.load(f)

        templates_raw = data.get("templates", [])
        grouped: dict[str, list[dict[str, Any]]] = {}
        for tmpl in templates_raw:
            slug = tmpl.get("category_slug", "default")
            grouped.setdefault(slug, []).append(tmpl)

        # Ensure 'default' key exists
        grouped.setdefault("default", [])
        return grouped

    def _load_word_lists(self) -> dict[str, Any]:
        """Load word lists from word_lists.json.

        Returns:
            Dict with keys: conditions, brands, features, cities, item_ages.
        """
        if not WORD_LISTS_PATH.exists():
            logger.warning("Word lists not found at %s, using empty dicts", WORD_LISTS_PATH)
            return {
                "conditions": {"ru": [], "en": [], "bs": []},
                "brands": {"default": {"ru": [], "en": [], "bs": []}},
                "features": {"default": {"ru": [], "en": [], "bs": []}},
                "cities": {"ru": [], "en": [], "bs": []},
                "item_ages": {"ru": [], "en": [], "bs": []},
            }

        with open(WORD_LISTS_PATH, encoding="utf-8") as f:
            return json.load(f)

    def _fill_template(
        self,
        template: dict[str, Any],
        locale: str,
        category: Category,
        price_amount: int | None = None,
    ) -> tuple[str, str]:
        """Fill template placeholders with word list values and Faker data.

        Args:
            template: Template dict with 'patterns' containing locale-specific
                      'title' and 'description'.
            locale: Language code ('ru', 'en', 'bs').
            category: Category instance for context-aware generation.
            price_amount: Pre-computed price amount (see ``generate``) so the
                      ``{price}`` placeholder is consistent with the ad's
                      actual ``price_amount``. ``None`` or ``0`` renders empty.

        Returns:
            Tuple of (filled_title, filled_description).
        """
        patterns = template.get("patterns", {})
        locale_patterns = patterns.get(locale, patterns.get("ru", {}))
        title_pattern = locale_patterns.get("title", "")
        desc_pattern = locale_patterns.get("description", "")

        # Determine category group for brand selection
        # Mapping is a plain dict[str, str]; fallback to "default"
        category_group: str = (
            CATEGORY_GROUP_MAP[category.slug] if category.slug in CATEGORY_GROUP_MAP else "default"
        )

        # Get word lists for this locale
        conditions: list[str] = self.word_lists.get("conditions", {}).get(locale, [])  # type: ignore[union-attr]
        brands_data: dict[str, Any] = self.word_lists.get("brands", {})
        brands: list[str] = brands_data.get(category_group, brands_data.get("default", {})).get(locale, [])  # type: ignore[union-attr]
        features_data: dict[str, Any] = self.word_lists.get("features", {})
        features: list[str] = features_data.get(category.slug, features_data.get("default", {})).get(locale, [])  # type: ignore[union-attr]
        cities: list[str] = self.word_lists.get("cities", {}).get(locale, [])  # type: ignore[union-attr]
        item_ages: list[str] = self.word_lists.get("item_ages", {}).get(locale, [])  # type: ignore[union-attr]

        replacements: dict[str, str] = {
            "{condition}": self._rng.choice(conditions) if conditions else "",
            "{brand}": self._rng.choice(brands) if brands else "",
            "{feature}": self._rng.choice(features) if features else "",
            "{city}": self._rng.choice(cities) if cities else "",
            "{price}": str(price_amount or ""),
            "{rooms}": str(self.faker.random_int(1, 4)),
            "{area}": str(self.faker.random_int(30, 150)),
            "{item_age}": self._rng.choice(item_ages) if item_ages else "",
            "{year}": str(self.faker.random_int(2015, 2024)),
            "{mileage}": str(self.faker.random_int(5000, 150000)),
            "{category}": category.get_name(locale),
        }

        def _replace_vars(text: str) -> str:
            for placeholder, value in replacements.items():
                text = text.replace(placeholder, value)
            return text

        title = _replace_vars(title_pattern)
        description = _replace_vars(desc_pattern)

        return title, description

    def generate(
        self,
        ad_count: int,
        status_weights: dict[str, float] | None = None,
    ) -> list[Ad]:
        """Generate a list of unsaved Ad instances with multi-language content.

        Args:
            ad_count: Number of ads to generate.
            status_weights: Dict mapping status string to weight (e.g.
                {"published": 0.6, "archived": 0.2, ...}). If None,
                uses config defaults.

        Returns:
            List of Ad instances (not yet saved to DB) with all language
            fields populated and original_language='ru'.
        """
        if status_weights is None:
            status_weights = self.config.get("status_distribution", {})

        # Normalize weights
        statuses, weights = self._normalize_weights(status_weights)

        now = datetime.now(UTC)
        ads: list[Ad] = []

        for _ in range(ad_count):
            category = self._rng.choice(self.categories)

            # Select template by category slug with fallback
            category_templates: list[dict[str, Any]]
            if category.slug in self.templates:
                category_templates = self.templates[category.slug]
            elif "default" in self.templates:
                category_templates = self.templates["default"]
            else:
                category_templates = []
            template: dict[str, Any] = (
                self._rng.choice(category_templates) if category_templates
                else {"patterns": {
                    "ru": {"title": "Товар", "description": "Описание."},
                    "en": {"title": "Item", "description": "Description."},
                    "bs": {"title": "Artikal", "description": "Opis."},
                }}
            )

            user = self._rng.choice(self.users)
            city = self._rng.choice(self.cities)
            status = self._weighted_status(statuses, weights)

            # Resolve the category-constrained listing purpose (F4) BEFORE price
            # generation: a "give-away" purpose (e.g. the charity category,
            # which resolves to give-away exclusively) is always free (price 0).
            # Empty / unsaved-category lookup resolution is a no-op -> None.
            if category.pk is not None:
                resolved_purposes = CategoryLookupResolver.get_resolved_purposes(category)
            else:
                resolved_purposes = []
            if resolved_purposes:
                purpose = self._rng.choice(resolved_purposes)
            else:
                purpose = None

            # Generate price based on category + listing purpose (seed ads use
            # EUR, Assumption 8). Give-away listings are always free (price 0).
            price_amount, price_currency = self._generate_price(category, purpose)

            # Fill templates for all languages. Reuse the generated price so the
            # {price} placeholder matches the ad's actual price_amount.
            title, description = self._fill_template(template, "ru", category, price_amount)
            title_en, description_en = self._fill_template(template, "en", category, price_amount)
            title_bs, description_bs = self._fill_template(template, "bs", category, price_amount)

            # Build timestamps consistent with status
            published_at: datetime | None = None
            archived_at: datetime | None = None
            moderation_failed_at: datetime | None = None
            rejected_at: datetime | None = None

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
                title_en=title_en,
                description_en=description_en,
                title_bs=title_bs,
                description_bs=description_bs,
                original_language=LanguageLocale.RUSSIAN.value,
                price_amount=price_amount,
                price_currency=price_currency.value,
                # Seed ads are EUR, so the normalized EUR value equals the amount.
                price_normalized_eur=price_amount,
                category=category,
                city=city,
                category_name=category.get_name("ru"),
                status=status,
                source=AdSource.SEED,
                listing_purpose=purpose,
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
        return self._rng.choices(statuses, weights=weights, k=1)[0]

    def _generate_price(
        self,
        category: Category,
        listing_purpose: LookupItem | None = None,
    ) -> tuple[int | None, CurrencyCode]:
        """Generate a price (amount + EUR currency) appropriate for the category.

        Seed ads default to **EUR** (spec Assumption 8), so the EUR-normalized
        amount equals the original amount. Returns ``(None, CurrencyCode.EUR)``
        for the ~20% of non-category items that are priced "free / negotiable".

        Give-away listings (listing purpose slug ``give-away`` — including the
        ``charity`` category, which resolves to ``give-away`` exclusively) are
        always free: returns ``(0, CurrencyCode.EUR)`` (spec: ``price = 0``
        triggers the Благотворительность path).
        """
        # Give-away / charity ads are always free (price = 0)
        if listing_purpose is not None and listing_purpose.slug == "give-away":
            return 0, CurrencyCode.EUR

        # Real estate: higher prices
        real_estate_slugs = {
            "apartments", "houses", "rooms", "garages", "land-plots",
            "other-real-estate", "offices", "flex-space", "retail-spaces",
            "warehouses", "commercial-land",
        }
        # Vehicles
        vehicle_slugs = {
            "cars", "motorcycles-sub", "scooters", "bicycles",
            "scooters-scooters", "trucks-sub", "agricultural-machinery",
            "commercial-vehicles", "campers", "boats-yachts", "motorboats",
            "sailing-boats", "personal-watercraft",
        }

        if category.slug in real_estate_slugs:
            amount = self.faker.random_int(20000, 500000)
        elif category.slug in vehicle_slugs:
            amount = self.faker.random_int(2000, 80000)
        elif category.slug == "phones":
            amount = self.faker.random_int(100, 1500)
        elif category.slug in {"computers", "laptops", "tablets", "cameras"}:
            amount = self.faker.random_int(200, 3000)
        else:
            # 20% chance of no price (free / negotiable)
            if self.faker.random_int(0, 99) < 20:
                amount = None
            else:
                amount = self.faker.random_int(10, 5000)

        return amount, CurrencyCode.EUR