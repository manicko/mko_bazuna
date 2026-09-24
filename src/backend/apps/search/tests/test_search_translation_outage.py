"""
Search degradation-contract tests during a translation service outage (SRH-007).

Translation is deliberately NOT on the search read path — the search view uses
language-aware per-language FTS vectors with no query-time translation (see the
``translation.py`` module docstring). Consequently these tests do NOT exercise
any code path that calls ``translate_text``.

Their value is as a *degradation-contract regression test*: they open the
translation circuit breaker (simulating an outage) and verify the search view
still responds 200 with results. This guards against a future regression that
adds translation to the search path and would break search whenever the breaker
is open.
"""

import pytest
from django.test import Client

from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.core.services.translation import _CIRCUIT_BREAKER
from apps.locations.models import City
from apps.users.models import User
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestSearchDuringTranslationOutage:
    """Search stays functional when the translation circuit breaker is open (SRH-007)."""

    def test_search_returns_200_with_results_during_translation_outage(
        self,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """Search returns 200 with results while the translation breaker is open.

        Opening the breaker (simulating an outage) must not break the search
        view. Even though translation is not on the search read path, this locks
        in the degradation contract so a future change that wires translation
        into search cannot silently regress it.
        """
        # Simulate an outage by opening the circuit breaker (failure threshold
        # consecutive failures). These tests are not on the search read path, so
        # the opened breaker itself has no functional effect on search — the
        # assertion is the contract: search must still succeed.
        for _ in range(_CIRCUIT_BREAKER.failure_threshold):
            _CIRCUIT_BREAKER.record_failure()
        assert _CIRCUIT_BREAKER.is_open

        try:
            create_test_ad(
                seller,
                category,
                city,
                title="Красный велосипед",
                status=AdStatus.PUBLISHED,
            )
            client = Client()
            response = client.get("/search/?q=велосипед&lang=ru")

            assert response.status_code == 200
            ads_in_page = list(response.context["page_obj"])
            assert ads_in_page  # results are returned
            assert ads_in_page[0].status == AdStatus.PUBLISHED
        finally:
            # Restore the breaker so state does not leak into other tests.
            _CIRCUIT_BREAKER.record_success()
            assert not _CIRCUIT_BREAKER.is_open
