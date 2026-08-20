"""SeedService orchestrator — coordinates all generators for seed data creation."""

from __future__ import annotations

import json
import logging
import os
import random
import shutil
import time
from pathlib import Path
from typing import Any

from django.db import transaction

from apps.ads.models import Ad, AdImage
from apps.analytics.models import AnalyticsEvent, DailyAdMetrics
from apps.categories.models import Category
from apps.core.enums import AdSource, AdvisoryLockId
from apps.core.utils.advisory_lock import advisory_lock
from apps.locations.models import City
from apps.media.services.hash_service import FileHashService
from apps.search.models import PopularSearch
from apps.seed.generators.ads import AdGenerator
from apps.seed.generators.analytics import AnalyticsGenerator
from apps.seed.generators.images import ImageGenerator
from apps.seed.generators.users import UserGenerator
from apps.trust.services.trust_calculator import TrustCalculator
from apps.users.models import User
from django.conf import settings

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "seed.default.json"
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class SeedService:
    """Orchestrates seed data generation.

    Loads config, clears seedable tables, runs all generators in order,
    and reports progress. Uses advisory lock to prevent concurrent seeds.
    """

    def __init__(self) -> None:
        self.config = self._load_config()

    def _load_config(self) -> dict[str, Any]:
        """Load seed configuration from JSON file."""
        if not CONFIG_PATH.exists():
            logger.warning("Config not found at %s, using empty config", CONFIG_PATH)
            return {}
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)

    def run(
        self,
        users: int = 10,
        ads: int = 30,
        force: bool = False,
        status_distribution: str | None = None,
        analytics: bool = True,
    ) -> None:
        """Run the full seed workflow.

        Args:
            users: Number of users to generate.
            ads: Number of ads to generate.
            force: If True, skip confirmation prompt.
            status_distribution: JSON string with status weights override.
            analytics: If True, generate analytics events/metrics.
        """
        with advisory_lock(AdvisoryLockId.SEED, session=True):
            total_start = time.time()

            # Merge CLI overrides into config
            if status_distribution:
                try:
                    parsed = json.loads(status_distribution)
                    self.config["status_distribution"] = parsed
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid --status-distribution JSON: {e}") from e

            # Step 1: Clean existing seed data
            self._clean()

            # Step 2: Load fixtures (categories, cities)
            categories = self._load_category_fixtures()
            cities = self._load_city_fixtures()

            # Step 3: Generate users
            t_start = time.time()
            user_gen = UserGenerator(self.config)
            user_instances = user_gen.generate(users)
            User.objects.bulk_create(user_instances, batch_size=5000)
            t_elapsed = time.time() - t_start
            self._log_progress("User", users, t_elapsed)

            # Fetch from DB to get PKs
            db_users = list(User.objects.order_by("-id")[:users])

            # Step 4: Generate ads
            t_start = time.time()
            ad_gen = AdGenerator(self.config, db_users, categories, cities)
            ad_instances = ad_gen.generate(ads)
            Ad.objects.bulk_create(ad_instances, batch_size=5000)
            t_elapsed = time.time() - t_start
            self._log_progress("Ad", ads, t_elapsed)

            # Fetch from DB to get PKs
            db_ads = list(Ad.objects.filter(source=AdSource.SEED))

            # Step 5: Generate images
            t_start = time.time()
            img_gen = ImageGenerator(self.config, db_ads)
            ad_images = img_gen.generate()
            if ad_images:
                AdImage.objects.bulk_create(ad_images, batch_size=5000)
            t_elapsed = time.time() - t_start
            self._log_progress("AdImage", len(ad_images), t_elapsed)

            # Step 5b: Backfill SHA-256 for images (bulk_create bypasses save())
            if ad_images:
                hashed_count = self._backfill_image_hashes(ad_images)
                logger.info("[seed] AdImage SHA-256: %d hashes backfilled", hashed_count)

            # Step 5c: Seed popular searches for autocomplete
            popular_count = self._seed_popular_searches()
            self._log_progress("PopularSearch", popular_count, 0.0)

            # Step 6: Generate analytics (optional)
            events: list[AnalyticsEvent] = []
            metrics: list[DailyAdMetrics] = []
            if analytics:
                t_start = time.time()
                analytics_gen = AnalyticsGenerator(self.config, db_ads)
                events = analytics_gen.generate_events()
                events.extend(analytics_gen.generate_contact_events())
                if events:
                    AnalyticsEvent.objects.bulk_create(events, batch_size=5000)
                t_elapsed = time.time() - t_start
                self._log_progress("AnalyticsEvent", len(events), t_elapsed)

                t_start = time.time()
                metrics = analytics_gen.generate_daily_metrics()
                if metrics:
                    DailyAdMetrics.objects.bulk_create(
                        metrics,
                        batch_size=5000,
                        ignore_conflicts=True,
                    )
                t_elapsed = time.time() - t_start
                self._log_progress("DailyAdMetrics", len(metrics), t_elapsed)

            # Step 7: Generate trust scores (reads contact events from Step 6)
            t_start = time.time()
            trust_calc = TrustCalculator()
            for user in db_users:
                trust_calc.calculate_and_save(user)
            t_elapsed = time.time() - t_start
            self._log_progress("SellerTrustScore", len(db_users), t_elapsed)

            total_elapsed = time.time() - total_start
            logger.info(
                "Seed complete in %.2fs — users=%d ads=%d images=%d "
                "events=%d metrics=%d",
                total_elapsed,
                users,
                ads,
                len(ad_images),
                len(events) if analytics else 0,
                len(metrics) if analytics else 0,
            )

    def _clean(self) -> None:
        """Delete all seed data in FK-safe order and cleans the seed media directory.

        Seed data is identified by Ad.source = 'seed'.
        Categories and Cities are NOT deleted (they are static fixtures).
        """
        # Identify seed user IDs (users who have seed ads)
        seed_user_ids = list(
            User.objects.filter(ads__source=AdSource.SEED)
            .values_list("id", flat=True)
            .distinct()
        )

        # Delete in FK-safe order: child tables first
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
            # 1. DailyAdMetrics (FK to Ad)
            DailyAdMetrics.objects.filter(
                ad__source=AdSource.SEED
            ).delete()

            # 2. AnalyticsEvent (FK to Ad)
            AnalyticsEvent.objects.filter(
                ad__source=AdSource.SEED
            ).delete()

            # 3. AdImage (FK to Ad)
            AdImage.objects.filter(ad__source=AdSource.SEED).delete()

            # 4. Ad (FK to User)
            Ad.objects.filter(source=AdSource.SEED).delete()

            # 5. Seed users (identified by having seed ads or no ads)
            if seed_user_ids:
                User.objects.filter(id__in=seed_user_ids).delete()

        # 6. Clean seed media directory
        media_root = settings.MEDIA_ROOT
        if isinstance(media_root, str):
            seed_dir = os.path.join(media_root, "seed")
        else:
            seed_dir = str(media_root / "seed")
        if os.path.exists(seed_dir):
            shutil.rmtree(seed_dir, ignore_errors=True)
            logger.info("Cleaned seed media directory: %s", seed_dir)

        logger.info("Cleaned existing seed data")

    def _load_category_fixtures(self) -> list[Category]:
        """Load categories via catalog builder.

        Replaces the old JSON fixture approach with the same builder module
        used by the catalog data migration.

        Returns:
            List of Category instances saved to DB.
        """
        CATALOG_PATH = (
            Path(__file__).resolve().parents[2]
            / "categories"
            / "catalog"
            / "categories.yaml"
        )
        from apps.categories.catalog.builder import load_catalog

        load_catalog(CATALOG_PATH)
        # Only leaf categories (no children) — ads must live at the terminal level.
        # Parent categories aggregate ads via MPTT subtree filtering in the
        # listings view, so they should never be directly assigned ads.
        return list(Category.objects.filter(children__isnull=True))

    def _load_city_fixtures(self) -> list[City]:
        """Load city fixtures from JSON file.

        Returns:
            List of City instances saved to DB.
        """
        fixture_path = FIXTURES_DIR / "cities.json"
        if not fixture_path.exists():
            logger.warning("Cities fixture not found at %s", fixture_path)
            return []

        from django.core.serializers import deserialize

        with open(fixture_path, encoding="utf-8") as f:
            data = f.read()

        objs: list[City] = []
        for deserialized in deserialize("json", data):
            obj = deserialized.object
            objs.append(obj)

        City.objects.bulk_create(objs, ignore_conflicts=True)
        return list(City.objects.all())

    def _log_progress(self, name: str, count: int, elapsed: float) -> None:
        """Log progress for a generation step."""
        logger.info("[seed] %s: %d rows in %.2fs", name, count, elapsed)
        logger.info("  %s: %d rows in %.2fs", name, count, elapsed)

    def _backfill_image_hashes(self, ad_images: list[AdImage]) -> int:
        """Compute SHA-256 for seed AdImage records bypassed by bulk_create.

        ``bulk_create`` skips ``AdImage.save()``, which normally computes the
        hash for deduplication. This backfills each image file's SHA-256 from
        disk and persists it with one ``update()`` per record.
        """
        media_root = settings.MEDIA_ROOT
        hashed: list[tuple[int, str]] = []
        for img in ad_images:
            file_path = str(Path(media_root) / str(img.image))
            if os.path.exists(file_path):
                file_hash = FileHashService.calculate_sha256(file_path)
                if file_hash:
                    hashed.append((img.pk, file_hash))

        for pk, file_hash in hashed:
            AdImage.objects.filter(pk=pk).update(sha256=file_hash)

        return len(hashed)

    def _seed_popular_searches(self, limit: int = 15) -> int:
        """Create PopularSearch records from config and ad titles.

        Reads curated queries from the seed config (``popular_searches``) and
        derives additional keyword queries from seed ad titles. Uses
        ``update_or_create`` keyed on ``query_normalized`` (matching the
        ``increment_popular_search`` runtime service) for idempotency on re-seed
        (``SeedService._clean`` does not remove PopularSearch rows).
        """
        count = 0
        config_searches = self.config.get("popular_searches", [])
        for item in config_searches:
            normalized = item["query"].strip().lower()
            PopularSearch.objects.update_or_create(
                query_normalized=normalized,
                defaults={"query": item["query"], "hit_count": item["hit_count"]},
            )
            count += 1

        rng = random.Random(self.config.get("faker_seed", 42) + 200)
        # Exclude config queries so they are not upserted twice.
        existing: set[str] = {item["query"].strip().lower() for item in config_searches}

        title_words: set[str] = set()
        for ad in Ad.objects.filter(source=AdSource.SEED):
            if not ad.title:
                continue
            for word in ad.title.lower().split():
                word = word.strip(".,!?")
                if len(word) >= 4 and word.isalpha() and word not in existing:
                    title_words.add(word)

        for word in sorted(title_words)[:limit]:
            PopularSearch.objects.update_or_create(
                query_normalized=word.lower(),
                defaults={"query": word, "hit_count": max(rng.randint(5, 30), 10)},
            )
            count += 1

        return count
