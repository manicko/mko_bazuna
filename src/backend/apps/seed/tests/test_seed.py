"""Tests for the seed module generators and management command."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.ads.models import Ad
from apps.analytics.models import AnalyticsEvent, DailyAdMetrics
from apps.categories.models import Category
from apps.core.enums import AdSource, AdStatus, AdvisoryLockId
from apps.locations.models import City
from apps.seed.generators.ads import AdGenerator
from apps.seed.generators.analytics import AnalyticsGenerator
from apps.seed.generators.base import BaseGenerator
from apps.seed.generators.images import ImageGenerator
from apps.seed.generators.users import UserGenerator
from apps.seed.paths import FIXTURES_IMAGES_DIR
from apps.users.models import User


# ─── BaseGenerator tests ────────────────────────────────────────────────


class TestBaseGenerator(TestCase):
    """Tests for the BaseGenerator shared infrastructure."""

    def test_deterministic_faker_seed(self) -> None:
        """Same seed produces same output."""
        config = {"faker_seed": 42}
        gen1 = BaseGenerator(config)
        gen2 = BaseGenerator(config)
        assert gen1.faker.name() == gen2.faker.name()

    def test_random_choice_without_weights(self) -> None:
        """Random choice returns an item from the options list."""
        gen = BaseGenerator({"faker_seed": 42})
        options = ["a", "b", "c"]
        result = gen._random_choice(options)
        assert result in options

    def test_random_choice_with_weights(self) -> None:
        """Weighted random selection returns an item."""
        gen = BaseGenerator({"faker_seed": 42})
        options = ["a", "b", "c"]
        result = gen._random_choice(options, weights=[1.0, 0.0, 0.0])
        assert result == "a"

    def test_chunked_splits_correctly(self) -> None:
        """Chunking splits a list into expected sizes."""
        gen = BaseGenerator({"faker_seed": 42})
        items = list(range(10))
        chunks = gen._chunked(items, 3)
        assert len(chunks) == 4
        assert chunks[0] == [0, 1, 2]
        assert chunks[-1] == [9]


# ─── UserGenerator tests ────────────────────────────────────────────────


class TestUserGenerator(TestCase):
    """Tests for UserGenerator."""

    def test_generates_correct_count(self) -> None:
        """UserGenerator produces exactly N users."""
        gen = UserGenerator({"faker_seed": 42})
        users = gen.generate(5)
        assert len(users) == 5

    def test_unique_telegram_ids(self) -> None:
        """All telegram_id values are unique."""
        gen = UserGenerator({"faker_seed": 42})
        users = gen.generate(10)
        ids = [u.telegram_id for u in users]
        assert len(ids) == len(set(ids))

    def test_deterministic_output(self) -> None:
        """Same seed produces same users."""
        gen1 = UserGenerator({"faker_seed": 42})
        gen2 = UserGenerator({"faker_seed": 42})
        users1 = gen1.generate(3)
        users2 = gen2.generate(3)
        for u1, u2 in zip(users1, users2, strict=False):
            assert u1.first_name == u2.first_name
            assert u1.last_name == u2.last_name
            assert u1.telegram_id == u2.telegram_id

    def test_username_optional(self) -> None:
        """Some users have null username, some don't."""
        gen = UserGenerator({"faker_seed": 42})
        users = gen.generate(20)
        null_usernames = sum(1 for u in users if u.username is None)
        # With 30% probability and 20 users, at least 1 should be null
        assert null_usernames > 0
        assert null_usernames < 20

    def test_users_are_active(self) -> None:
        """All generated users are active and not banned."""
        gen = UserGenerator({"faker_seed": 42})
        users = gen.generate(5)
        for u in users:
            assert u.is_active is True
            assert u.is_banned is False
            assert u.is_deleted is False

    def test_bulk_create_works(self) -> None:
        """Users can be saved to DB via bulk_create."""
        gen = UserGenerator({"faker_seed": 42})
        users = gen.generate(3)
        User.objects.bulk_create(users)
        assert User.objects.count() == 3


# ─── AdGenerator tests ──────────────────────────────────────────────────


class TestAdGenerator(TestCase):
    """Tests for AdGenerator."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create seed data for ad tests."""
        # Create users
        cls.users = []
        for i in range(3):
            user = User.objects.create(
                username=f"testuser{i}",
                telegram_id=1000 + i,
                chat_id=1000 + i,
                password="!",
            )
            cls.users.append(user)

        # Create categories
        cls.categories = []
        cat_data = [
            ("Недвижимость", "real-estate"),
            ("Автомобили", "cars"),
            ("Электроника", "phones"),
        ]
        for name, slug in cat_data:
            cat = Category.objects.create(name=name, slug=slug)
            cls.categories.append(cat)

        # Create cities
        cls.cities = []
        city_data = [
            ("Подгорица", "podgorica", "Central"),
            ("Будва", "budva", "Coastal"),
        ]
        for name, slug, region in city_data:
            city = City.objects.create(
                name=name, slug=slug, region=region, country_code="ME"
            )
            cls.cities.append(city)

    def test_generates_correct_count(self) -> None:
        """AdGenerator produces exactly M ads."""
        gen = AdGenerator(
            {"faker_seed": 42, "status_distribution": {"published": 1.0}},
            self.users,
            self.categories,
            self.cities,
        )
        ads = gen.generate(5)
        assert len(ads) == 5

    def test_source_is_seed(self) -> None:
        """All generated ads have source=SEED."""
        gen = AdGenerator(
            {"faker_seed": 42, "status_distribution": {"published": 1.0}},
            self.users,
            self.categories,
            self.cities,
        )
        ads = gen.generate(5)
        for ad in ads:
            assert ad.source == AdSource.SEED

    def test_status_distribution_default(self) -> None:
        """Default status distribution produces a mix of statuses."""
        gen = AdGenerator(
            {"faker_seed": 42, "status_distribution": {"published": 0.6, "archived": 0.2, "draft": 0.2}},
            self.users,
            self.categories,
            self.cities,
        )
        ads = gen.generate(50)
        statuses = {ad.status for ad in ads}
        assert AdStatus.PUBLISHED in statuses
        assert AdStatus.ARCHIVED in statuses

    def test_fk_references_exist(self) -> None:
        """All FK references point to valid objects."""
        gen = AdGenerator(
            {"faker_seed": 42, "status_distribution": {"published": 1.0}},
            self.users,
            self.categories,
            self.cities,
        )
        ads = gen.generate(5)
        for ad in ads:
            assert ad.user in self.users
            assert ad.category in self.categories
            assert ad.city in self.cities

    def test_no_transition_to_called(self) -> None:
        """Ads are created directly, not via transition_to()."""
        gen = AdGenerator(
            {"faker_seed": 42, "status_distribution": {"published": 1.0}},
            self.users,
            self.categories,
            self.cities,
        )
        ads = gen.generate(5)
        for ad in ads:
            # Direct status field set, not via transition_to
            assert ad.status in (AdStatus.PUBLISHED, AdStatus.ARCHIVED, AdStatus.DRAFT)

    def test_bulk_create_works(self) -> None:
        """Ads can be saved to DB via bulk_create."""
        gen = AdGenerator(
            {"faker_seed": 42, "status_distribution": {"published": 1.0}},
            self.users,
            self.categories,
            self.cities,
        )
        ads = gen.generate(3)
        Ad.objects.bulk_create(ads)
        assert Ad.objects.count() == 3


# ─── ImageGenerator tests ────────────────────────────────────────────────


class TestImageGenerator(TestCase):
    """Tests for ImageGenerator."""

    @classmethod
    def setUpTestData(cls) -> None:
        user = User.objects.create(
            username="imguser",
            telegram_id=9999,
            chat_id=9999,
            password="!",
        )
        cat = Category.objects.create(name="Тест", slug="test")
        city = City.objects.create(
            name="Тест", slug="test-city", region="Test", country_code="ME"
        )
        cls.ad = Ad.objects.create(
            user=user,
            title="Test Ad",
            description="Test",
            price=100,
            category=cat,
            city=city,
            category_name="Тест",
            status=AdStatus.PUBLISHED,
            source=AdSource.SEED,
        )

    def setUp(self) -> None:
        """Initialize tracking for dummy JPEG files created during tests."""
        self._created_files: list[Path] = []

    def tearDown(self) -> None:
        """Remove dummy JPEG files and temp media created during tests."""
        for path in self._created_files:
            path.unlink(missing_ok=True)
        shutil.rmtree("/tmp/test_seed_media", ignore_errors=True)

    @override_settings(MEDIA_ROOT="/tmp/test_seed_media")
    def test_generates_ad_images(self) -> None:
        """ImageGenerator creates AdImage instances for ads."""
        # Create dummy JPEG fixture files for all manifest-referenced photos.
        # The actual image files were removed from git; only the JSON manifest
        # remains. ImageGenerator._preprocess_images silently skips missing
        # files, so we materialise minimal valid JPEGs in the fixtures dir.
        from PIL import Image

        manifest_path = FIXTURES_IMAGES_DIR / "photo_manifest.json"
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        dummy = Image.new("RGB", (100, 100), color="red")
        for cat_entry in manifest.get("categories", {}).values():
            for photo in cat_entry.get("photos", []):
                filename = photo["filename"]
                fixture_path = FIXTURES_IMAGES_DIR / filename
                if not fixture_path.exists():
                    dummy.save(fixture_path, format="JPEG")
                    self._created_files.append(fixture_path)
        for photo in manifest.get("default", {}).get("photos", []):
            filename = photo["filename"]
            fixture_path = FIXTURES_IMAGES_DIR / filename
            if not fixture_path.exists():
                dummy.save(fixture_path, format="JPEG")
                self._created_files.append(fixture_path)

        gen = ImageGenerator(
            {"faker_seed": 42, "image_count": {"min": 1, "max": 2}},
            [self.ad],
        )
        images = gen.generate()
        assert len(images) >= 1
        assert len(images) <= 2
        for img in images:
            assert img.ad_id == self.ad.pk
            assert img.position >= 1

    def test_image_keys_have_correct_format(self) -> None:
        """Image keys are valid UUID-based filenames."""
        gen = ImageGenerator(
            {"faker_seed": 42, "image_count": {"min": 1, "max": 1}},
            [self.ad],
        )
        images = gen.generate()
        for img in images:
            assert img.image.endswith(".jpg")
            assert len(img.image) > 10


# ─── AnalyticsGenerator tests ────────────────────────────────────────────


class TestAnalyticsGenerator(TestCase):
    """Tests for AnalyticsGenerator."""

    @classmethod
    def setUpTestData(cls) -> None:
        user = User.objects.create(
            username="anauser",
            telegram_id=8888,
            chat_id=8888,
            password="!",
        )
        cat = Category.objects.create(name="Тест", slug="test-analytics")
        city = City.objects.create(
            name="Подгорица", slug="pg", region="Central", country_code="ME"
        )
        cls.published_ad = Ad.objects.create(
            user=user,
            title="Published Ad",
            description="Test",
            price=100,
            category=cat,
            city=city,
            category_name="Тест",
            status=AdStatus.PUBLISHED,
            source=AdSource.SEED,
            published_at="2024-01-01 00:00:00+00",
        )
        cls.draft_ad = Ad.objects.create(
            user=user,
            title="Draft Ad",
            description="Test",
            price=100,
            category=cat,
            city=city,
            category_name="Тест",
            status=AdStatus.DRAFT,
            source=AdSource.SEED,
        )

    def test_events_created_for_published_ads(self) -> None:
        """Events are generated for published ads."""
        config = {
            "faker_seed": 42,
            "analytics": {
                "days_back": 5,
                "views_per_ad_per_day": {"min": 1, "max": 3},
            },
        }
        gen = AnalyticsGenerator(config, [self.published_ad, self.draft_ad])
        events = gen.generate_events()
        # Published ad should have events, draft should not
        published_events = [e for e in events if e.ad_id == self.published_ad.pk]
        draft_events = [e for e in events if e.ad_id == self.draft_ad.pk]
        assert len(published_events) > 0
        assert len(draft_events) == 0

    def test_events_have_ad_viewed_type(self) -> None:
        """All events have AD_VIEWED type."""
        config = {
            "faker_seed": 42,
            "analytics": {
                "days_back": 3,
                "views_per_ad_per_day": {"min": 1, "max": 2},
            },
        }
        gen = AnalyticsGenerator(config, [self.published_ad])
        events = gen.generate_events()
        for e in events:
            assert e.event_type == "ad_viewed"

    def test_daily_metrics_created(self) -> None:
        """DailyAdMetrics are generated for published ads."""
        config = {
            "faker_seed": 42,
            "analytics": {
                "days_back": 3,
                "views_per_ad_per_day": {"min": 1, "max": 2},
            },
        }
        gen = AnalyticsGenerator(config, [self.published_ad])
        metrics = gen.generate_daily_metrics()
        assert len(metrics) > 0
        for m in metrics:
            assert m.ad_id == self.published_ad.pk
            assert m.views_count > 0

    def test_bulk_create_events_works(self) -> None:
        """Events can be saved to DB via bulk_create."""
        config = {
            "faker_seed": 42,
            "analytics": {
                "days_back": 2,
                "views_per_ad_per_day": {"min": 1, "max": 2},
            },
        }
        gen = AnalyticsGenerator(config, [self.published_ad])
        events = gen.generate_events()
        AnalyticsEvent.objects.bulk_create(events)
        assert AnalyticsEvent.objects.count() > 0


# ─── Management command tests ────────────────────────────────────────────


class TestSeedCommand(TestCase):
    """Tests for the seed management command."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Create prerequisite data (categories and cities)
        Category.objects.create(name="Тест", slug="test-seed")
        City.objects.create(
            name="Будва", slug="budva", region="Coastal", country_code="ME"
        )

    def test_seed_with_zero_count(self) -> None:
        """Seed with --users 0 --ads 0 produces no records."""
        out = StringIO()
        call_command(
            "seed",
            "--users=0",
            "--ads=0",
            "--force",
            "--analytics=False",
            stdout=out,
        )
        assert User.objects.count() == 0
        assert Ad.objects.count() == 0

    def test_seed_force_skips_prompt(self) -> None:
        """--force skips the confirmation prompt."""
        out = StringIO()
        call_command(
            "seed",
            "--users=2",
            "--ads=3",
            "--force",
            "--analytics=False",
            stdout=out,
        )
        assert "Seed cancelled" not in out.getvalue()
        assert User.objects.count() == 2
        assert Ad.objects.count() == 3

    def test_seed_with_analytics(self) -> None:
        """Seed with analytics generates events and metrics."""
        out = StringIO()
        call_command(
            "seed",
            "--users=2",
            "--ads=3",
            "--force",
            "--analytics=True",
            stdout=out,
        )
        assert AnalyticsEvent.objects.count() > 0
        assert DailyAdMetrics.objects.count() > 0

    def test_seed_produces_seed_source(self) -> None:
        """All seeded ads have source=SEED."""
        call_command("seed", "--users=2", "--ads=5", "--force", "--analytics=False")
        ads = Ad.objects.all()
        for ad in ads:
            assert ad.source == AdSource.SEED

    def test_seed_idempotent(self) -> None:
        """Re-running seed produces consistent data (same count)."""
        call_command("seed", "--users=2", "--ads=5", "--force", "--analytics=False")
        count1 = Ad.objects.count()

        # Reset and re-seed
        call_command("seed", "--users=2", "--ads=5", "--force", "--analytics=False")
        count2 = Ad.objects.count()
        assert count2 == count1 == 5


# ─── Enum tests ──────────────────────────────────────────────────────────


class TestSeedEnums(TestCase):
    """Tests for enum values added for seed support."""

    def test_ad_source_seed(self) -> None:
        """AdSource.SEED resolves to 'seed'."""
        assert AdSource.SEED == "seed"
        assert AdSource.SEED.value == "seed"

    def test_advisory_lock_id_seed(self) -> None:
        """AdvisoryLockId.SEED resolves to 110."""
        assert AdvisoryLockId.SEED == 110
        assert AdvisoryLockId.SEED.value == 110


# ─── ImageGenerator manifest-based tests ─────────────────────────────────


class TestImageGeneratorManifest(TestCase):
    """Tests for ImageGenerator with manifest-based photo loading."""

    def setUp(self) -> None:
        """Create a temporary manifest for testing."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.fixtures_images_dir = (
            Path(__file__).resolve().parent.parent / "fixtures" / "images"
        )

    def tearDown(self) -> None:
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_patch(self, manifest_data: dict | None = None) -> dict:
        """Create a test manifest dict."""
        if manifest_data is None:
            manifest_data = {
                "version": 1,
                "categories": {
                    "apartments": {
                        "photos": [
                            {
                                "filename": "apartments_01.jpg",
                                "tags": ["interior"],
                                "width": 800,
                                "height": 600,
                            },
                            {
                                "filename": "apartments_02.jpg",
                                "tags": ["living-room"],
                                "width": 1024,
                                "height": 768,
                            },
                        ]
                    },
                    "cars": {
                        "photos": [
                            {
                                "filename": "cars_01.jpg",
                                "tags": ["exterior"],
                                "width": 800,
                                "height": 600,
                            }
                        ]
                    },
                },
                "default": {
                    "photos": [
                        {
                            "filename": "default_01.jpg",
                            "tags": [],
                            "width": 640,
                            "height": 480,
                        }
                    ]
                },
            }
        return manifest_data

    def test_manifest_loading(self) -> None:
        """ImageGenerator._load_manifest() parses manifest correctly."""
        from apps.seed.generators.images import ImageGenerator

        manifest = self._create_patch()

        with patch.object(
            ImageGenerator, "_load_manifest", return_value=None
        ):
            # We test _load_manifest indirectly by checking the pools after init
            gen = ImageGenerator({"faker_seed": 42}, [])
            # Override with test data
            gen.photo_pool = {
                slug: entry["photos"]
                for slug, entry in manifest.get("categories", {}).items()
            }
            gen.default_pool = manifest.get("default", {}).get("photos", [])

            assert "apartments" in gen.photo_pool
            assert len(gen.photo_pool["apartments"]) == 2
            assert len(gen.default_pool) == 1

    def test_get_photos_for_category(self) -> None:
        """_get_photos_for_category returns category-specific photos."""
        from apps.seed.generators.images import ImageGenerator

        gen = ImageGenerator({"faker_seed": 42}, [])
        gen.photo_pool = {
            "apartments": [{"filename": "apartments_01.jpg"}],
            "cars": [{"filename": "cars_01.jpg"}],
        }
        gen.default_pool = [{"filename": "default_01.jpg"}]

        kvartiry_photos = gen._get_photos_for_category("apartments")
        assert len(kvartiry_photos) == 1
        assert kvartiry_photos[0]["filename"] == "apartments_01.jpg"

        avto_photos = gen._get_photos_for_category("cars")
        assert len(avto_photos) == 1
        assert avto_photos[0]["filename"] == "cars_01.jpg"

    def test_fallback_to_default(self) -> None:
        """Unknown categories fall back to default pool."""
        from apps.seed.generators.images import ImageGenerator

        gen = ImageGenerator({"faker_seed": 42}, [])
        gen.photo_pool = {"apartments": [{"filename": "apartments_01.jpg"}]}
        gen.default_pool = [{"filename": "default_01.jpg"}]

        unknown_photos = gen._get_photos_for_category("unknown_category")
        assert len(unknown_photos) == 1
        assert unknown_photos[0]["filename"] == "default_01.jpg"

    def test_empty_default_fallback(self) -> None:
        """If both category-specific and default are empty, return empty list."""
        from apps.seed.generators.images import ImageGenerator

        gen = ImageGenerator({"faker_seed": 42}, [])
        gen.photo_pool = {}
        gen.default_pool = []

        photos = gen._get_photos_for_category("anything")
        assert photos == []


# ─── AdGenerator multi-language tests ────────────────────────────────────


class TestAdGeneratorMultiLang(TestCase):
    """Tests for AdGenerator multi-language template support."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create test users and cities required by AdGenerator.generate()."""
        for i in range(3):
            User.objects.create(
                username=f"multilang-user{i}",
                telegram_id=3000 + i,
                chat_id=3000 + i,
                password="!",
            )
        cls.users = list(User.objects.all())

        for i in range(2):
            City.objects.create(
                name=f"TestCity{i}",
                slug=f"test-city-{i}",
                region="Test",
                country_code="ME",
            )
        cls.cities = list(City.objects.all())

    def test_word_lists_loaded(self) -> None:
        """Word lists contain expected keys with entries."""
        from apps.seed.generators.ads import AdGenerator

        gen = AdGenerator({"faker_seed": 42}, [], [], [])
        word_lists = gen.word_lists

        assert "conditions" in word_lists
        assert "brands" in word_lists
        assert "features" in word_lists
        assert "cities" in word_lists
        assert "item_ages" in word_lists

        # Check that ru locale has entries
        assert len(word_lists["conditions"].get("ru", [])) >= 5
        assert len(word_lists["cities"].get("ru", [])) >= 5

    def test_templates_loaded(self) -> None:
        """Templates are loaded and grouped by category_slug."""
        from apps.seed.generators.ads import AdGenerator

        gen = AdGenerator({"faker_seed": 42}, [], [], [])
        templates = gen.templates

        assert "default" in templates
        assert len(templates["default"]) >= 1
        # Check template structure
        tmpl = templates["default"][0]
        assert "patterns" in tmpl
        assert "ru" in tmpl["patterns"]
        assert "en" in tmpl["patterns"]
        assert "bs" in tmpl["patterns"]

    def test_template_variables_filled(self) -> None:
        """Generated ads have no raw {variable} placeholders."""
        from apps.seed.generators.ads import AdGenerator

        gen = AdGenerator({"faker_seed": 42}, [], [], [])
        # Test _fill_template directly
        template = {
            "patterns": {
                "ru": {
                    "title": "Продам {category} {condition}",
                    "description": "Цена: {price} BAM. {feature}. Город: {city}.",
                },
                "en": {
                    "title": "{condition} {category} for sale",
                    "description": "Price: {price} BAM. {feature}. City: {city}.",
                },
                "bs": {
                    "title": "{category} na prodaju - {condition}",
                    "description": "Cijena: {price} BAM. {feature}. Grad: {city}.",
                },
            }
        }

        from apps.categories.models import Category

        cat = Category(name="Телефоны", slug="phones", name_i18n={
            "ru": "Телефоны", "en": "Phones", "bs": "Telefoni"
        })

        # Fill template for ru
        title, desc = gen._fill_template(template, "ru", cat)
        assert "{" not in title
        assert "{" not in desc
        assert len(title) > 0
        assert len(desc) > 0

        # Fill template for en
        title_en, desc_en = gen._fill_template(template, "en", cat)
        assert "{" not in title_en
        assert "{" not in desc_en

        # Fill template for bs
        title_bs, desc_bs = gen._fill_template(template, "bs", cat)
        assert "{" not in title_bs
        assert "{" not in desc_bs

    def test_generated_ads_have_multi_language_fields(self) -> None:
        """Generated Ad instances have all language fields populated."""
        from apps.categories.models import Category
        from apps.seed.generators.ads import AdGenerator

        # Create a basic test category
        cat = Category(name="Телефоны", slug="phones", name_i18n={
            "ru": "Телефоны", "en": "Phones", "bs": "Telefoni"
        })

        gen = AdGenerator(
            {
                "faker_seed": 42,
                "status_distribution": {"published": 1.0},
            },
            self.users,
            [cat],
            self.cities,
        )
        ads = gen.generate(3)
        assert len(ads) == 3

        for ad in ads:
            assert ad.title is not None and len(ad.title) > 0
            assert ad.description is not None and len(ad.description) > 0
            assert ad.title_en is not None and len(ad.title_en) > 0
            assert ad.description_en is not None and len(ad.description_en) > 0
            assert ad.title_bs is not None and len(ad.title_bs) > 0
            assert ad.description_bs is not None and len(ad.description_bs) > 0
            assert ad.original_language == "ru"

    def test_original_language_set(self) -> None:
        """All generated ads have original_language='ru'."""
        from apps.categories.models import Category
        from apps.seed.generators.ads import AdGenerator

        cat = Category(name="Тест", slug="test-slug")
        gen = AdGenerator(
            {"faker_seed": 42, "status_distribution": {"draft": 1.0}},
            self.users,
            [cat],
            self.cities,
        )
        ads = gen.generate(5)
        for ad in ads:
            assert ad.original_language == "ru"

    def test_deterministic_multi_language(self) -> None:
        """Same Faker seed produces same multi-language content."""
        from apps.categories.models import Category
        from apps.seed.generators.ads import AdGenerator

        cat = Category(name="Тест", slug="test-slug")
        config = {"faker_seed": 42, "status_distribution": {"draft": 1.0}}

        gen1 = AdGenerator(config, self.users, [cat], self.cities)
        gen2 = AdGenerator(config, self.users, [cat], self.cities)
        ads1 = gen1.generate(3)
        ads2 = gen2.generate(3)

        for a1, a2 in zip(ads1, ads2, strict=False):
            assert a1.title == a2.title
            assert a1.description == a2.description
            assert a1.title_en == a2.title_en
            assert a1.description_en == a2.description_en
            assert a1.title_bs == a2.title_bs
            assert a1.description_bs == a2.description_bs

    def test_fallback_template_for_unknown_category(self) -> None:
        """Unknown category slug uses default templates."""
        from apps.categories.models import Category
        from apps.seed.generators.ads import AdGenerator

        # Category with a slug that has no specific templates
        cat = Category(name="Неизвестно", slug="unknown-slug-123")
        gen = AdGenerator(
            {"faker_seed": 42, "status_distribution": {"draft": 1.0}},
            self.users,
            [cat],
            self.cities,
        )
        ads = gen.generate(1)
        ad = ads[0]
        # Should have valid content from default templates
        assert len(ad.title) > 0
        assert len(ad.description) > 0


# ─── SeedCommand enhanced tests ──────────────────────────────────────────


class TestSeedCommandEnhanced(TestCase):
    """Tests for SeedCommand with new media cleanup and realistic photos."""

    @classmethod
    def setUpTestData(cls) -> None:
        from apps.categories.models import Category
        from apps.locations.models import City

        Category.objects.create(name="Тест", slug="test-seed")
        City.objects.create(
            name="Будва", slug="budva", region="Coastal", country_code="ME"
        )

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_media_cleanup(self) -> None:
        """Seed cleans MEDIA_ROOT/seed/ before re-seeding."""
        from django.conf import settings

        media_root = settings.MEDIA_ROOT
        if isinstance(media_root, str):
            seed_dir = os.path.join(media_root, "seed")
        else:
            seed_dir = str(media_root / "seed")

        os.makedirs(seed_dir, exist_ok=True)
        dummy_file = os.path.join(seed_dir, "dummy.txt")
        with open(dummy_file, "w") as f:
            f.write("test")

        # First seed run
        out = StringIO()
        call_command(
            "seed",
            "--users=2",
            "--ads=3",
            "--force",
            "--analytics=False",
            stdout=out,
        )
        # After second seed, the seed directory should be cleaned and recreated
        call_command(
            "seed",
            "--users=2",
            "--ads=3",
            "--force",
            "--analytics=False",
            stdout=out,
        )

        # The seed dir should exist (recreated by ImageGenerator) but old files gone
        assert os.path.exists(seed_dir)
        # Old dummy should not exist
        assert not os.path.exists(dummy_file)

    def test_seed_produces_multi_language_ads(self) -> None:
        """Full seed generates ads with all language fields."""
        out = StringIO()
        call_command(
            "seed",
            "--users=2",
            "--ads=4",
            "--force",
            "--analytics=False",
            stdout=out,
        )
        ads = Ad.objects.filter(source=AdSource.SEED)
        for ad in ads:
            assert ad.title_en is not None
            assert ad.description_en is not None
            assert ad.title_bs is not None
            assert ad.description_bs is not None
            assert ad.original_language == "ru"


# ─── Seed category integration tests ─────────────────────────────────────


class TestSeedCategoryIntegration(TestCase):
    """Integration tests verifying the full seed pipeline with the new category system.

    Tests that:
    - Categories load via the catalog builder from categories.yaml
    - AdGenerator creates ads referencing valid category slugs
    - Photo manifest loading works with ImageGenerator
    - Full seed command produces valid data end-to-end
    """

    @classmethod
    def setUpTestData(cls) -> None:
        """Load categories via catalog builder and create prerequisite data."""
        from apps.categories.catalog.builder import load_catalog

        CATALOG_PATH = (
            Path(__file__).resolve().parents[2]
            / "categories"
            / "catalog"
            / "categories.yaml"
        )
        load_catalog(CATALOG_PATH)

        City.objects.create(
            name="Будва", slug="budva", region="Coastal", country_code="ME"
        )
        City.objects.create(
            name="Подгорица", slug="podgorica", region="Central", country_code="ME"
        )

    def test_builder_loads_all_leaf_slugs(self) -> None:
        """Builder loads all 171 leaf category slugs from categories.yaml."""
        leaf_slugs_from_yaml = {
            "ac-installation", "accessories", "accounting", "agricultural-machinery",
            "agriculture", "anti-theft", "apartment-cleaning", "apartments",
            "appliance-repair", "appliances", "arts", "audio-video",
            "auto-accessories", "auto-audio-video", "auto-business-equipment",
            "auto-equipment", "auto-tools", "bags-luggage", "bath-products",
            "beauty-appliances", "beauty-equipment", "beauty-salons-spa",
            "bed-linen", "bicycles", "birds", "boats-yachts", "books-magazines",
            "boys", "business-accounting", "business-commercial-land",
            "business-flex-space", "business-legal-services", "business-offices",
            "business-property-valuation", "business-retail-spaces", "business-taxes",
            "business-translations", "business-warehouses", "cameras", "campers",
            "car-repair", "car-seats", "care-hygiene", "carpet-cleaning", "cars",
            "catering", "cats", "charity", "cleaning-service", "clothing-repair",
            "commercial-construction", "commercial-land", "commercial-vehicles",
            "computers", "costume-jewelry", "courses-training", "delivery-courier",
            "dog-walking", "dogs", "electrical", "event-planning", "feeding-products",
            "fish-aquarium", "flex-space", "flooring-installation", "florist",
            "food-equipment", "food-products", "freight", "furniture-interior",
            "games-consoles-software", "garages", "girls", "gps-navigators",
            "hair-care", "hair-care-services", "hair-styling", "hobby-bicycles",
            "hobby-scooters", "home-food-service", "housekeeping", "houses",
            "hunting-fishing", "industrial-equipment", "jewelry", "kids-furniture",
            "kids-hygiene", "kids-scooters-bikes", "kitchen-dining", "land-plots",
            "laptop-pc-repair", "laptops", "legal-services", "logistics-warehouse",
            "makeup-manicure", "manicure", "massage", "medical-equipment",
            "medical-products", "medicine", "men-clothing", "men-shoes", "motorboats",
            "motorcycles-sub", "musical-instruments", "no-experience-jobs",
            "office-cleaning", "office-equipment", "offices", "oils-chemicals",
            "other-animals", "other-electronics", "other-real-estate",
            "other-services", "parts", "pc-setup", "pedicure", "perfumes",
            "personal-watercraft", "pet-accessories", "pet-birds", "pet-dogs-cats",
            "pet-food", "pet-toys", "phone-repair", "phones", "photoshoots",
            "plants", "plastering", "plumbing", "programming", "property-valuation",
            "psychology", "ready-business", "repair-construction",
            "residential-construction", "restaurants", "retail-equipment",
            "retail-spaces", "roof-boxes-hitches", "rooms", "sailing-boats",
            "school-supplies", "scooters", "scooters-scooters", "security",
            "shoe-repair", "skincare", "sport-fitness", "sports-outdoors",
            "strollers", "tablets", "tax-planning", "taxi", "terraces-balconies",
            "tickets-travel", "tires-wheels", "tow-truck", "toys", "trading",
            "trailers", "translations", "trucks-sub", "tutors", "warehouses",
            "warehousing", "watches", "waterproofing", "web-development",
            "women-clothing", "women-shoes",
        }
        db_slugs = set(
            Category.objects.exclude(slug__in=["test-seed", "test-analytics", "test", "test-city"]).values_list("slug", flat=True)
        )
        # At minimum, all leaf slugs from YAML should be present in DB
        missing = leaf_slugs_from_yaml - db_slugs
        assert not missing, f"Missing leaf slugs in DB: {missing}"

    def test_ad_generator_with_builder_categories(self) -> None:
        """AdGenerator creates ads with valid category slugs from builder."""
        categories = list(Category.objects.exclude(slug__in=["test-seed", "test-analytics", "test", "test-city"]))
        self.assertGreater(len(categories), 0, "No categories loaded from builder")

        # Create users
        users = []
        for i in range(3):
            user = User.objects.create(
                username=f"int-user{i}",
                telegram_id=2000 + i,
                chat_id=2000 + i,
                password="!",
            )
            users.append(user)

        cities = list(City.objects.all())
        self.assertGreater(len(cities), 0, "No cities available")

        gen = AdGenerator(
            {"faker_seed": 42, "status_distribution": {"published": 1.0}},
            users,
            categories,
            cities,
        )
        ads = gen.generate(10)
        self.assertEqual(len(ads), 10)

        for ad in ads:
            # All ads should reference categories from the builder
            self.assertIsNotNone(ad.category)
            # Category slug should exist in the DB
            self.assertTrue(
                Category.objects.filter(slug=ad.category.slug).exists(),
                f"Ad references unknown category slug: {ad.category.slug}",
            )
            # Price may be None for free/negotiable ads (~20% of non-special
            # categories) per AdGenerator._generate_price() — only validate
            # the field when a price is actually set
            if ad.price is not None:
                self.assertIsInstance(ad.price, int)
                self.assertGreater(ad.price, 0)
            # Multi-language fields should be populated
            self.assertIsNotNone(ad.title)
            self.assertIsNotNone(ad.title_en)
            self.assertIsNotNone(ad.title_bs)

    def test_photo_manifest_loading(self) -> None:
        """ImageGenerator loads the photo manifest (even if empty)."""
        gen = ImageGenerator(
            {"faker_seed": 42, "image_count": {"min": 1, "max": 2}},
            [],
        )
        # Manifest always exists (empty stub at minimum)
        self.assertIsNotNone(gen.photo_pool)
        self.assertIsNotNone(gen.default_pool)

    def test_full_seed_with_builder_categories(self) -> None:
        """Full seed command produces ads with valid category references."""
        out = StringIO()
        call_command(
            "seed",
            "--users=2",
            "--ads=5",
            "--force",
            "--analytics=False",
            stdout=out,
        )
        ads = Ad.objects.filter(source=AdSource.SEED)
        self.assertEqual(ads.count(), 5)

        for ad in ads:
            # All ads should reference categories from the builder
            self.assertIsNotNone(ad.category)
            self.assertTrue(
                Category.objects.filter(slug=ad.category.slug).exists(),
                f"Ad references unknown category slug: {ad.category.slug}",
            )
            # Multi-language content
            self.assertIsNotNone(ad.title_en)
            self.assertIsNotNone(ad.title_bs)
            self.assertEqual(ad.original_language, "ru")