"""Management command to seed and refresh the initial exchange rates.

After a migration squash that deletes and regenerates migration files via
``makemigrations``, ``RunPython`` data migrations such as ``seed_initial_rates``
cannot be regenerated from model state. This command recreates the fixed
initial rates idempotently, using the live ORM model directly (not
``apps.get_model``) so it can also be used to refresh rates at any time.

Seeded rates (PO-05):

    EUR: rate_to_eur=1.0,   effective_date=2026-08-22, source="manual_seed"
    BAM: rate_to_eur=0.512, effective_date=2026-08-22, source="manual_seed"
    RSD: rate_to_eur=0.0105, effective_date=2026-08-22, source="manual_seed"

Idempotent via ``update_or_create`` keyed on ``currency``.
"""

import logging
from datetime import date

from django.core.management.base import BaseCommand

from apps.currencies.models import ExchangeRate

logger = logging.getLogger(__name__)

EFFECTIVE_DATE = date(2026, 8, 22)
SOURCE = "manual_seed"

# (ISO code, rate_to_eur as string to preserve decimal precision)
INITIAL_RATES: tuple[tuple[str, str], ...] = (
    ("EUR", "1.0"),
    ("BAM", "0.512"),
    ("RSD", "0.0105"),
)


class Command(BaseCommand):
    """Seed the fixed initial exchange rates (EUR base currency)."""

    help = (
        "Seed or refresh the initial manual exchange rates "
        "(EUR base, BAM and RSD) with source 'manual_seed'"
    )

    def handle(self, *args, **options) -> None:
        """Insert or update each initial rate row."""
        created = 0
        updated = 0
        for currency_code, rate_to_eur in INITIAL_RATES:
            obj, was_created = ExchangeRate.objects.update_or_create(
                currency=currency_code,
                defaults={
                    "rate_to_eur": rate_to_eur,
                    "effective_date": EFFECTIVE_DATE,
                    "source": SOURCE,
                    "is_current": True,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1
            logger.info(
                "ExchangeRate %s: rate_to_eur=%s (%s)",
                obj.currency,
                obj.rate_to_eur,
                "created" if was_created else "updated",
            )
            self.stdout.write(
                f"{'Created' if was_created else 'Updated'} "
                f"{obj.currency}: rate_to_eur={obj.rate_to_eur}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Exchange rates loaded: {created} created, {updated} updated"
            )
        )
