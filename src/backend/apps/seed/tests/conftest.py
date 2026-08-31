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
from typing import Any
from unittest.mock import patch

import pytest


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
