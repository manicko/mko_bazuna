"""Autouse fixtures for the seed test suite.

Speeds up the slow seed tests by mocking the real image pipeline. The
``ImageGenerator`` in ``seed_service`` preprocesses the full ~1004-photo
manifest and runs a SHA-256 backfill on every ``call_command('seed')`` — tens
of seconds per call for tests that never assert on images.

We patch the class-name binding inside ``seed_service`` (NOT
``ImageGenerator.generate``), so tests that import ``ImageGenerator`` directly
from ``apps.seed.generators.images`` (``TestImageGenerator``) are unaffected.
``test_media_cleanup`` asserts the seed directory is recreated by the real
generator, so it opts out via ``@pytest.mark.real_images``.
"""

from __future__ import annotations

from collections.abc import Iterator
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from django.core.management import call_command
from pytest_django import DjangoDbBlocker

from apps.categories.catalog.builder import load_catalog
from apps.locations.models import City


class _NoImageGenerator:
    """Stub ImageGenerator that never touches the disk or photo pipeline."""

    def __init__(self, config: dict[str, Any], ads: list[Any]) -> None:
        self.config = config
        self.ads = ads

    def generate(self) -> list:
        """Return no AdImage records, skipping preprocessing and SHA-256."""
        return []


@pytest.fixture(autouse=True)
def _no_op_image_generator(request: pytest.FixtureRequest) -> Iterator[None]:
    """Patch ``seed_service.ImageGenerator`` to a no-op stub.

    Skipped for tests marked ``real_images`` (e.g. ``test_media_cleanup``),
    which assert on the real image pipeline / seed directory.
    """
    if "real_images" in request.keywords:
        yield
        return
    with patch("apps.seed.services.seed_service.ImageGenerator", _NoImageGenerator):
        yield


@pytest.fixture(scope="class")
def seeded_test_data(
    django_db_setup: None, django_db_blocker: DjangoDbBlocker
) -> Iterator[None]:
    """Class-scoped seed fixture for ``TestSeedFilterCoverage``.

    Runs ``call_command("seed")`` once per class (not once per test), committing
    4 users and 40 seed ads to the test database. Each test method then reads
    the committed rows inside its own per-test ``transaction.atomic()`` block,
    whose ``ROLLBACK`` never sees the committed seed data — identical to
    Django's ``setUpTestData`` pattern.

    ``django_db_setup`` is declared as a dependency to guarantee the test DB
    exists before this class-scoped fixture opens ``django_db_blocker.unblock()``.

    The ``ImageGenerator`` patch must be active here (the function-scoped
    ``_no_op_image_generator`` only patches during test execution, not during
    class-scoped setup); otherwise the real ~1004-photo pipeline runs on
    ``call_command("seed")`` — tens of seconds per call.
    """
    catalog_path = (
        Path(__file__).resolve().parents[2]
        / "categories"
        / "catalog"
        / "categories.yaml"
    )
    with django_db_blocker.unblock():
        with patch(
            "apps.seed.services.seed_service.ImageGenerator", _NoImageGenerator
        ):
            load_catalog(catalog_path)
            City.objects.get_or_create(
                slug="budva",
                defaults={
                    "name": "Будва",
                    "region": "Coastal",
                    "country_code": "ME",
                },
            )
            City.objects.get_or_create(
                slug="podgorica",
                defaults={
                    "name": "Подгорица",
                    "region": "Central",
                    "country_code": "ME",
                },
            )
            call_command(
                "seed",
                "--users=4",
                "--ads=40",
                "--force",
                "--analytics=False",
                stdout=StringIO(),
            )
        yield
