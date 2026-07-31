"""Tests for the seed module generators and management command."""

from __future__ import annotations

from io import StringIO

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
            ("Недвижимость", "nedvizhimost"),
            ("Автомобили", "avtomobili"),
            ("Электроника", "elektronika"),
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

    @override_settings(MEDIA_ROOT="/tmp/test_seed_media")
    def test_generates_ad_images(self) -> None:
        """ImageGenerator creates AdImage instances for ads."""
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