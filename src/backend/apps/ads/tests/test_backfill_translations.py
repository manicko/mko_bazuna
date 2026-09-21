"""
Integration tests for the ``backfill_translations`` management command.

Verifies:
- Ads with NULL ``title_en``/``title_bs`` get translated and ``original_language``
  is set to ``"ru"``.
- Already-translated ads are skipped (idempotent).
- Translation failures fall back to the original text (graceful degradation).
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

_TRANSLATE_PATCH = "apps.core.services.translation.translate_text"


def _fake_translate(text: str, source_locale: str, target_locale: str) -> str:
    """Deterministic mock translation: appends the target locale as a suffix."""
    return f"{text}_{target_locale}"


def _fallback_to_original(
    text: str, source_locale: str, target_locale: str
) -> str:
    """Simulate ``translate_text``'s fallback: returns the original text unchanged."""
    return text


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
        """When ``translate_text`` falls back to the original text, fields get
        the original Russian text (Path A consistency) and the ad is still
        marked processed rather than left NULL."""
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

        # ``translate_text`` never returns None -- on failure it returns the
        # original text. Simulate that fallback so the circuit-breaker/retry
        # path is exercised without hitting the network.
        with patch(_TRANSLATE_PATCH, side_effect=_fallback_to_original) as mock_translate:
            call_command("backfill_translations", batch_size=10)

        # All four translation calls were attempted and fell back to the
        # original text.
        assert mock_translate.call_count == 4
        ad.refresh_from_db()
        assert ad.title_en == "Красный велосипед"
        assert ad.title_bs == "Красный велосипед"
        assert ad.description_en == "Продается детский велосипед"
        assert ad.description_bs == "Продается детский велосипед"
        # updates was non-empty (original text populated the fields), so the ad
        # was processed and original_language was set.
        assert ad.original_language == "ru"

    def test_uses_translate_text_not_raw_api(
        self, seller, category, city
    ) -> None:
        """Backfill routes through ``translate_text`` (not the raw API helper
        ``translate_cached_generic``) with the Russian source locale, so the
        circuit-breaker/retry/fallback path is shared with the bot."""
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

        with patch(_TRANSLATE_PATCH, side_effect=_fake_translate) as mock_translate:
            call_command("backfill_translations", batch_size=10)

        # translate_text is the integration point for the backfill; the
        # per-field httpx try/except was removed so translate_cached_generic is
        # never invoked directly from the command.
        assert mock_translate.call_count == 4
        for call_args in mock_translate.call_args_list:
            args, _ = call_args
            # translate_text(text, source_locale="ru", target_locale)
            assert args[1] == "ru"
