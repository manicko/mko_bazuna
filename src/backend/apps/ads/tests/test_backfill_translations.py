"""
Integration tests for the ``backfill_translations`` management command.

Verifies:
- Ads with NULL ``title_en``/``title_bs`` get translated and ``original_language``
  is set to ``"ru"``.
- Already-translated ads are skipped (idempotent).
- A translation failure leaves the column NULL and is counted as a fallback, so
  the row still matches the selection query and a re-run retries it (09-API-007).
- ``--limit`` bounds the run.
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

    def test_translation_failure_leaves_columns_null(
        self, seller, category, city
    ) -> None:
        """When ``translate_text`` falls back to the original text, the columns
        stay NULL and the row is counted as a fallback.

        The old assertion that the original Russian text *was* written into
        ``title_en``/``title_bs`` documented the defect (09-API-007): once the
        source is written into the column, the nullability-derived selection
        query never matches the row again and the failure is unrecoverable.
        Production code is king, so the assertion changed with the fix.
        """
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

        # All four translation calls were attempted and fell back to the source.
        assert mock_translate.call_count == 4
        ad.refresh_from_db()
        # Nothing was written: every fallback leaves its column NULL.
        assert ad.title_en is None
        assert ad.title_bs is None
        assert ad.description_en is None
        assert ad.description_bs is None
        # No successful update touched the row, so original_language stays NULL.
        assert ad.original_language is None

    def test_failed_translation_is_retried_on_second_run(
        self, seller, category, city
    ) -> None:
        """A failed translation leaves the row matching the selection query, so a
        second run revisits it.

        This is the assertion that distinguishes the fix from the defect: a
        command that wrote NULL but filtered on something else would satisfy the
        NULL assertion yet remain unrecoverable.
        """
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

        with patch(_TRANSLATE_PATCH, side_effect=_fallback_to_original):
            call_command("backfill_translations", batch_size=10)

        # The failed row still matches the selection query.
        still_missing = Ad.objects.filter(title_en__isnull=True) | Ad.objects.filter(
            title_bs__isnull=True
        )
        assert still_missing.filter(pk=ad.pk).exists()

        # The second run retries the same row.
        with patch(_TRANSLATE_PATCH, side_effect=_fake_translate) as mock_translate:
            call_command("backfill_translations", batch_size=10)

        assert mock_translate.call_count == 4
        ad.refresh_from_db()
        assert ad.title_en == "Красный велосипед_en"
        assert ad.title_bs == "Красный велосипед_bs"
        assert ad.original_language == "ru"

    def test_limit_bounds_the_run(self, seller, category, city) -> None:
        """``--limit`` caps the number of ads processed."""
        for index in range(3):
            ad = create_test_ad(
                seller,
                category,
                city,
                title=f"Красный велосипед {index}",
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

        with patch(_TRANSLATE_PATCH, side_effect=_fake_translate) as mock_translate:
            call_command("backfill_translations", batch_size=10, limit=1)

        # One ad -> two locales x (title + description) = 4 calls.
        assert mock_translate.call_count == 4

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
