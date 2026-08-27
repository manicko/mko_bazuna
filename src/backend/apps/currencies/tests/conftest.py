"""
Test fixtures for the currencies app.

Provides ``ExchangeRate`` rows so the price-normalizer and recompute-command
tests are self-contained and do not depend on migration-level data seeding
(the ``seed_initial_rates`` RunPython in ``0001_initial``). Tests that need a
rate simply request the ``exchange_rates`` fixture.
"""

from __future__ import annotations

import pytest

from apps.currencies.enums import CurrencyCode
from apps.currencies.models import ExchangeRate

# Fixed seed rates used across the currency test suite.
# ``rate_to_eur`` = number of EUR equal to one unit of the currency
# (EUR is the base, rate 1.0). Mirrors the initial migration seed so the
# test expectations in ``test_price_normalizer`` and
# ``test_recompute_command`` stay in sync.
_SEED_RATES: dict[CurrencyCode, str] = {
    CurrencyCode.EUR: "1.0",
    CurrencyCode.BAM: "0.512",
    CurrencyCode.RSD: "0.0105",
}

_RATE_SOURCE = "manual_seed"
_SEED_EFF_DATE = "2026-08-22"


@pytest.fixture
def exchange_rates() -> list[ExchangeRate]:
    """Create the standard EUR/BAM/RSD current exchange rates.

    Uses ``update_or_create`` so it is safe whether or not the initial
    migration has already seeded identical rows (the ``currency`` column
    is unique). Returns the freshly ensured rows.
    """
    rows: list[ExchangeRate] = []
    for code, rate in _SEED_RATES.items():
        row, _created = ExchangeRate.objects.update_or_create(
            currency=code.value,
            defaults={
                "rate_to_eur": rate,
                "effective_date": _SEED_EFF_DATE,
                "source": _RATE_SOURCE,
                "is_current": True,
            },
        )
        rows.append(row)
    return rows
