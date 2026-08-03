"""Management command to backfill translations for ads to English and Bosnian.

Translates existing Russian-language ads (title, description) to:
    - English (title_en, description_en)
    - Bosnian (title_bs, description_bs)

Skips ads where translations are already populated.
Uses deep-translator (GoogleTranslator) for batch translation.
Idempotent: safe to run multiple times.
"""

import logging

from django.core.management.base import BaseCommand

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


class Command(BaseCommand):
    """Backfill translations for existing ads to English and Bosnian."""

    help = "Backfill translations for ads to English and Bosnian"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of ads to process per batch (default: 100)",
        )

    def handle(self, *args, **options):
        # Lazy import to avoid circular dependency during module discovery
        from apps.ads.models import Ad

        batch_size = options["batch_size"]

        # Fetch ads that need translation — at least one target field is empty
        ads_to_translate = Ad.objects.filter(
            title_en__isnull=True,
        ) | Ad.objects.filter(
            title_bs__isnull=True,
        )

        total = ads_to_translate.count()
        self.stdout.write(f"Found {total} ads needing translation backfill")

        if total == 0:
            self.stdout.write(self.style.SUCCESS("No ads need translation backfill"))
            return

        processed = 0
        skipped = 0
        failed = 0

        for ad in ads_to_translate.iterator(chunk_size=batch_size):
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

        self.stdout.write(
            self.style.SUCCESS(
                f"Translation backfill complete: {processed} processed, "
                f"{skipped} skipped, {failed} failed"
            )
        )