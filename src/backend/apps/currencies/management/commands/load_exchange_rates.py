"""Management command to seed the initial exchange rates.

After a migration squash that deletes and regenerates migration files via
``makemigrations``, ``RunPython`` data migrations such as ``seed_initial_rates``
cannot be regenerated from model state. This command recreates the fixed
initial rates, using the live ORM model directly (not ``apps.get_model``) so it
can also be used at any time.

The constant below is a **bootstrap default**, not the authority. Operators are
expected to correct a drifted rate; this command therefore creates a row only if
the currency is absent and never rewrites an existing one. Idempotence here means
"create it if absent", never "make the row equal the constant".

Seeded rates (PO-05):

    EUR: rate_to_eur=1.0,   effective_date=2026-08-22, source="manual_seed"
    BAM: rate_to_eur=0.512, effective_date=2026-08-22, source="manual_seed"
    RSD: rate_to_eur=0.0105, effective_date=2026-08-22, source="manual_seed"

There is no exchange-rate feed: this command makes **no** HTTP call and reads no
external provider. A live ECB (or other) rate feed is a new capability and is
not implemented here.
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
        "Seed the initial manual exchange rates (EUR base, BAM and RSD) with "
        "source 'manual_seed' when a currency row is absent; existing rows are "
        "never rewritten"
    )

    def handle(self, *args, **options) -> None:
        """Create each absent initial rate row; preserve every existing one."""
        created = 0
        preserved = 0
        for currency_code, rate_to_eur in INITIAL_RATES:
            obj, was_created = ExchangeRate.objects.get_or_create(
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
                preserved += 1
            provenance = "seeded" if was_created else "preserved existing"
            logger.info(
                "ExchangeRate %s: rate_to_eur=%s (%s)",
                obj.currency,
                obj.rate_to_eur,
                provenance,
            )
            self.stdout.write(
                f"Rate {obj.currency}: rate_to_eur={obj.rate_to_eur} ({provenance})"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Exchange rates loaded: {created} created, {preserved} preserved"
            )
        )
