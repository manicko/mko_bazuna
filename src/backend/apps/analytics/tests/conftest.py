"""
Shared fixtures for analytics tests.

Provides the ``_locmem_cache`` autouse fixture that was previously
duplicated in ``test_ads_published.py`` and ``test_seller_stats.py``.
Centralising it here keeps cache configuration consistent across all
analytics test modules.
"""

from __future__ import annotations

import pytest
from django.test import override_settings


@pytest.fixture(autouse=True)
def _locmem_cache():
    """Use in-process locmem cache for deterministic SellerStats behavior."""
    with override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            },
        },
    ):
        yield
