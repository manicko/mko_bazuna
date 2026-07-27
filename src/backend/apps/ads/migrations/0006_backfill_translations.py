"""Backfill translations for existing ads to English and Bosnian.

Translates existing Russian-language ads (title, description) to:
    - English (title_en, description_en)
    - Bosnian (title_bs, description_bs)

Skips ads where translations are already populated.
Uses deep-translator (GoogleTranslator) for batch translation.
Runs after the multi-language search vector trigger update (0005) so
new inserts/updates get proper multi-language vectors.
"""

import logging

from django.db import migrations

logger = logging.getLogger(__name__)

# Target languages for backfill translation
TARGET_LOCALES: list[tuple[str, str, str]] = [
    ("en", "title_en", "description_en"),
    ("bs", "title_bs", "description_bs"),
]


def _translate_text(text: str, target: str) -> str | None:
    """Translate a single text string to the target language.

    Args:
        text: Source text to translate (Russian).
        target: Target language code (e.g. 'en', 'bs').

    Returns:
        Translated text, or None if translation failed.
    """
    if not text or not text.strip():
        return None
    try:
        from deep_translator import GoogleTranslator

        translator = GoogleTranslator(source="ru", target=target)
        return translator.translate(text)
    except Exception as exc:
        logger.warning(
            "Translation failed for target=%r text=%r: %s",
            target,
            text[:50],
            exc,
        )
        return None


def backfill_translations(apps, schema_editor):  # type: ignore[no-untyped-def]
    """Translate existing Russian ads to Bosnian and English.

    Processes all ads where title_en or title_bs is NULL/empty.
    Each ad gets 4 translations: title→en, title→bs, description→en, description→bs.
    Individual translation failures are logged and skipped — the migration
    continues processing remaining ads.
    """
    Ad = apps.get_model("ads", "Ad")

    # Fetch ads that need translation — at least one target field is empty
    ads_to_translate = Ad.objects.filter(
        title_en__isnull=True,
    ) | Ad.objects.filter(
        title_bs__isnull=True,
    )

    total = ads_to_translate.count()
    logger.info("Found %d ads needing translation backfill", total)

    processed = 0
    skipped = 0
    failed = 0

    for ad in ads_to_translate.iterator(chunk_size=100):
        updates: dict[str, str | None] = {}

        for locale, title_field, desc_field in TARGET_LOCALES:
            # Skip if this locale's fields are already populated
            current_title = getattr(ad, title_field, None)
            current_desc = getattr(ad, desc_field, None)

            if current_title and current_desc:
                continue

            # Translate title
            if not current_title:
                translated_title = _translate_text(ad.title, locale)
                if translated_title is not None:
                    updates[title_field] = translated_title

            # Translate description
            if not current_desc:
                translated_desc = _translate_text(ad.description, locale)
                if translated_desc is not None:
                    updates[desc_field] = translated_desc

        if not updates:
            skipped += 1
            continue

        # Mark the original language as Russian for all backfilled ads
        if ad.original_language is None:
            updates["original_language"] = "ru"

        try:
            Ad.objects.filter(pk=ad.pk).update(**updates)
            processed += 1
        except Exception as exc:
            logger.error(
                "Failed to save translations for ad %d: %s",
                ad.pk,
                exc,
            )
            failed += 1

    logger.info(
        "Translation backfill complete: %d processed, %d skipped, %d failed",
        processed,
        skipped,
        failed,
    )


class Migration(migrations.Migration):
    """Backfill translations for existing ads to English and Bosnian.

    Dependencies:
        - ads/0005: Multi-language search vector trigger update (must run
          before this backfill so new inserts/updates have proper vectors).
    """

    dependencies = [
        ("ads", "0005_multi_lang_search_vector"),
    ]

    operations = [
        migrations.RunPython(
            backfill_translations,
            reverse_code=migrations.RunPython.noop,
        ),
    ]