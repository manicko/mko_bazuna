"""
Tests for the shared ``format_price`` display helper (spec Task 7 / T-11).
"""

from decimal import Decimal

from apps.ads.models import Ad
from apps.ads.templatetags.price_tags import format_price, format_price_value
from apps.currencies.enums import CurrencyCode


def test_format_price_value_renders_amount_and_currency() -> None:
    """format_price_value renders ``{amount} {currency}``."""
    assert format_price_value(Decimal("500"), CurrencyCode.BAM) == "500 BAM"


def test_format_price_value_uses_intcomma() -> None:
    """Large amounts get a thousands separator (grouping applied).

    ``intcomma`` uses the active locale's grouping separator (e.g. ',' or a
    narrow no-break space for the RU locale), so the test asserts grouping
    happened without depending on the exact separator.
    """
    result = format_price_value(Decimal("12345"), CurrencyCode.EUR)
    assert "12345" not in result  # grouping was applied
    assert result.startswith("12")
    assert result.endswith("345 EUR")


def test_format_price_value_null_amount_returns_empty() -> None:
    """A NULL price renders as an empty string (no crash)."""
    assert format_price_value(None, CurrencyCode.EUR) == ""


def test_format_price_value_accepts_string_currency() -> None:
    """The currency may be an ISO 4217 string, not just a CurrencyCode member."""
    assert format_price_value(Decimal("100"), "RSD") == "100 RSD"


def test_format_price_filter_renders_original_currency() -> None:
    """The template filter uses the ad's original amount + currency (PO-02)."""
    ad = Ad(price_amount=Decimal("500"), price_currency=CurrencyCode.BAM)
    assert format_price(ad) == "500 BAM"


def test_format_price_filter_unpriced_returns_empty() -> None:
    """An ad without a price renders an empty string."""
    ad = Ad(price_amount=None, price_currency=None)
    assert format_price(ad) == ""
