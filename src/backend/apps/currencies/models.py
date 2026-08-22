"""
ExchangeRate model for Mko Bazuna.

Single source of truth for the current exchange rate of each supported
currency relative to EUR. Only ``is_current=True`` rows are used for price
normalization. The model is designed to later accept automated rate updates
from an official source (e.g. ECB) without a schema change.
"""

from django.db import models

from apps.currencies.enums import CurrencyCode


class ExchangeRate(models.Model):
    """Exchange rate of a currency relative to EUR (EUR is the base, rate 1.0).

    ``rate_to_eur`` is the number of EUR equal to one unit of the currency
    (e.g. BAM rate_to_eur ≈ 0.512 means 1 BAM = 0.512 EUR).

    At most one ``is_current=True`` row may exist per currency, enforced by a
    partial unique constraint and by the application's rate-seeding logic.
    """

    currency = models.CharField(
        max_length=3,
        choices=[(code.value, code.value) for code in CurrencyCode],
        unique=True,
        help_text="Currency this rate applies to (ISO 4217 code)",
    )
    rate_to_eur = models.DecimalField(
        max_digits=14,
        decimal_places=8,
        help_text="Number of EUR equal to one unit of this currency (EUR base = 1.0)",
    )
    effective_date = models.DateField(
        help_text="Date this rate takes effect (audit trail for rate changes)",
    )
    source = models.CharField(
        max_length=50,
        help_text="Origin of the rate, e.g. 'manual_seed' or an official provider",
    )
    is_current = models.BooleanField(
        default=True,
        help_text="Only current rows (one per currency) are used for normalization",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this rate row was created",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this rate row was last modified",
    )

    class Meta:
        db_table = "exchange_rates"
        constraints = [
            models.UniqueConstraint(
                fields=["currency", "is_current"],
                condition=models.Q(is_current=True),
                name="uq_exchange_rate_current_per_currency",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.currency}: {self.rate_to_eur} EUR (current={self.is_current})"
