"""
Integration tests for the ``backfill_translations`` management command.

Verifies:
- Ads with NULL ``title_en``/``title_bs`` get translated and ``original_language``
  is set to ``"ru"``.
- Already-translated ads are skipped (idempotent).
- Translation failures (returns ``None``) are handled gracefully.
- No-op when no ads need translation.

The external Google Cloud Translation API is mocked so tests run without
network access or API credentials.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.management import call_command

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# Patch target: ``_translate_text`` lazy-imports ``translate_cached_generic``
# from this module at call time, so patching the module-level attribute is
# sufficient to intercept the import.
_TRANSLATE_PATCH = "apps.core.services.translation.translate_cached_generic"


def _fake_translate(text: str, source_locale: str, target_locale: str) -> str:
    """Deterministic mock translation: appends the target locale as a suffix."""
    return f"{text}_{target_locale}"


class TestBackfillTranslations:
    """Integration tests for the backfill_translations command."""

    def test_translates_ads_with_null_fields(
        self, seller, category, city
    ) -> None:
        """Ads with NULL translation fields get translated and original_language set."""
        ad = create_test_ad(
            seller,
            category,
            city,
            title="Красный велосипед",
            description="Продается детский велосипед",
            status=AdStatus.PUBLISHED,
        )
        # Ensure all translation fields are NULL so the command picks them up.
        Ad.objects.filter(pk=ad.pk).update(
            title_en=None,
            title_bs=None,
            description_en=None,
            description_bs=None,
            original_language=None,
        )
        ad.refresh_from_db()

        with patch(_TRANSLATE_PATCH, side_effect=_fake_translate) as mock_translate:
            call_command("backfill_translations", batch_size=10)

        ad.refresh_from_db()
        assert ad.title_en == "Красный велосипед_en"
        assert ad.title_bs == "Красный велосипед_bs"
        assert ad.description_en == "Продается детский велосипед_en"
        assert ad.description_bs == "Продается детский велосипед_bs"
        assert ad.original_language == "ru"
        assert mock_translate.call_count == 4

    def test_idempotent_when_all_translations_present(
        self, seller, category, city
    ) -> None:
        """Ads with all translation fields populated are skipped."""
        ad = create_test_ad(
            seller,
            category,
            city,
            title="Красный велосипед",
            description="Продается детский велосипед",
            status=AdStatus.PUBLISHED,
        )
        Ad.objects.filter(pk=ad.pk).update(
            title_en="Red bicycle",
            title_bs="Crveni bicikl",
            description_en="Children's bicycle for sale",
            description_bs="Djejni bicikl",
            original_language="ru",
        )
        ad.refresh_from_db()

        with patch(_TRANSLATE_PATCH) as mock_translate:
            call_command("backfill_translations", batch_size=10)

        mock_translate.assert_not_called()
        ad.refresh_from_db()
        assert ad.title_en == "Red bicycle"
        assert ad.title_bs == "Crveni bicikl"
        assert ad.description_en == "Children's bicycle for sale"
        assert ad.description_bs == "Djejni bicikl"

    def test_no_ads_succeeds(self, seller, category, city) -> None:
        """Running backfill when no ads need translation succeeds silently."""
        with patch(_TRANSLATE_PATCH) as mock_translate:
            call_command("backfill_translations", batch_size=10)
        mock_translate.assert_not_called()

    def test_translation_failure_skips_gracefully(
        self, seller, category, city
    ) -> None:
        """When translation returns None, ad fields remain unchanged."""
        ad = create_test_ad(
            seller,
            category,
            city,
            title="Красный велосипед",
            description="Продается детский велосипед",
            status=AdStatus.PUBLISHED,
        )
        Ad.objects.filter(pk=ad.pk).update(
            title_en=None,
            title_bs=None,
            description_en=None,
            description_bs=None,
            original_language=None,
        )
        ad.refresh_from_db()

        with patch(_TRANSLATE_PATCH, return_value=None) as mock_translate:
            call_command("backfill_translations", batch_size=10)

        # All four translation calls were attempted but returned None.
        assert mock_translate.call_count == 4
        ad.refresh_from_db()
        assert ad.title_en is None
        assert ad.title_bs is None
        assert ad.description_en is None
        assert ad.description_bs is None
        # original_language is only set when updates are non-empty; since all
        # translations failed, updates was empty and the ad was skipped entirely.
        assert ad.original_language is None
