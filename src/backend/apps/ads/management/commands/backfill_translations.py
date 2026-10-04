"""Management command to backfill translations for ads to English and Bosnian.

Translates existing Russian-language ads (title, description) to:
    - English (title_en, description_en)
    - Bosnian (title_bs, description_bs)

Skips ads where translations are already populated.
Uses the shared ``translate_text`` service for batch translation.

``translate_text`` returns the UNMODIFIED SOURCE on every failure path (open
breaker, empty body, non-2xx, invalid key, timeout), so a caller cannot tell a
translation from a fallback. ``_translate_for_backfill`` compares the result to
the source and returns ``None`` on a fallback; ``Command.handle`` then writes
NOTHING to that locale's column, leaving it NULL. Because the selection query is
nullability-derived, a NULL column means the row still matches on the next run,
so a failed translation is re-runnable instead of permanently unrecoverable
(09-API-007).

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


def _translate_for_backfill(text: str, target: str) -> str | None:
    """Translate a single text string to the target language.

    Args:
        text: Source text to translate (Russian).
        target: Target language code (e.g. 'en', 'bs').

    Returns:
        The translated text, or ``None`` when ``translate_text`` returned the
        source unchanged (its fallback signal). ``None`` means "leave the
        column NULL" so the nullability-derived selection query matches the row
        again on a later run.
    """
    # Lazy import avoids circular dependency during management-command discovery.
    from apps.core.services.translation import translate_text

    translated = translate_text(text, "ru", target)
    # ``translate_text`` falls back to the unmodified source on failure; equality
    # is the observable side-channel (its ``-> str`` signature is unchanged).
    if translated == text:
        return None
    return translated


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
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of ads to process (default: no limit)",
        )

    def handle(self, *args, **options):
        # Lazy import to avoid circular dependency during module discovery
        from apps.ads.models import Ad

        batch_size = options["batch_size"]
        limit = options["limit"]

        # Fetch ads that need translation — at least one target field is empty
        ads_to_translate = Ad.objects.filter(
            title_en__isnull=True,
        ) | Ad.objects.filter(
            title_bs__isnull=True,
        )

        if limit is not None:
            ads_to_translate = ads_to_translate[:limit]

        total = ads_to_translate.count()
        self.stdout.write(f"Found {total} ads needing translation backfill")

        if total == 0:
            self.stdout.write(self.style.SUCCESS("No ads need translation backfill"))
            return

        processed = 0
        skipped = 0
        failed = 0
        fallbacks = 0

        for ad in ads_to_translate.iterator(chunk_size=batch_size):
            updates: dict[str, str] = {}

            for locale, title_field, desc_field in TARGET_LOCALES:
                # Skip if this locale's fields are already populated
                current_title = getattr(ad, title_field, None)
                current_desc = getattr(ad, desc_field, None)

                if current_title and current_desc:
                    continue

                # Translate title. A ``None`` result is a fallback: leave the
                # column out of ``updates`` so it stays NULL and re-matches later.
                if not current_title:
                    translated_title = _translate_for_backfill(ad.title, locale)
                    if translated_title is None:
                        fallbacks += 1
                        logger.warning(
                            "Translation fallback for ad %s field %s (%s): leaving NULL",
                            ad.pk,
                            title_field,
                            locale,
                        )
                    else:
                        updates[title_field] = translated_title

                # Translate description
                if not current_desc:
                    translated_desc = _translate_for_backfill(ad.description, locale)
                    if translated_desc is None:
                        fallbacks += 1
                        logger.warning(
                            "Translation fallback for ad %s field %s (%s): leaving NULL",
                            ad.pk,
                            desc_field,
                            locale,
                        )
                    else:
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
                f"{skipped} skipped, {failed} failed, {fallbacks} fallback(s)"
            )
        )
