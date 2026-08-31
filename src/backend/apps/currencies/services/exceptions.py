"""
Domain exceptions for the currencies app.
"""

from apps.currencies.enums import CurrencyCode


class ExchangeRateNotFoundError(LookupError):
    """Raised when no current exchange rate exists for a currency.

    Prices must never be silently normalized with a missing rate (spec
    Task 3): callers are expected to surface this to avoid incorrect data.
    """

    def __init__(self, currency: CurrencyCode) -> None:
        self.currency = currency
        super().__init__(
            f"No current exchange rate found for currency {currency.value}"
        )
