"""
Tests for the shared ``format_price`` display helper (spec Task 7 / T-11).
"""

from decimal import Decimal

import pytest
from django.utils.formats import get_format
from django.utils.translation import override

from apps.ads.models import Ad
from apps.ads.templatetags.price_tags import format_price, format_price_value
from apps.core.enums import LanguageLocale
from apps.currencies.enums import CurrencyCode

pytestmark = [pytest.mark.unit]

# Verified per-locale separator facts (14-I18N-003 / VAL-004). ``ru`` groups
# with a non-breaking space (U+00A0) and uses a comma decimal mark; ``bs``
# groups with a full stop and uses a comma decimal mark — its grouping only
# became reachable once the project-level ``FORMAT_MODULE_PATH`` supplied
# ``NUMBER_GROUPING = 3``; ``en`` uses comma grouping and a full-stop decimal
# mark. Asserted against ``get_format`` (the resolved source of truth) rather
# than a hard-coded rendered string, so a change in Django's bundled locale data
# is caught here instead of silently altering a rendered price.
_EXPECTED_SEPARATORS: dict[LanguageLocale, tuple[str, str]] = {
    LanguageLocale.RUSSIAN: ("\u00a0", ","),
    LanguageLocale.BOSNIAN: (".", ","),
    LanguageLocale.ENGLISH: (",", "."),
}


def _thousand_separator(locale: str) -> str:
    """Return the resolved thousands separator for ``locale``."""
    return str(get_format("THOUSAND_SEPARATOR", lang=locale))


def _decimal_separator(locale: str) -> str:
    """Return the resolved decimal separator for ``locale``."""
    return str(get_format("DECIMAL_SEPARATOR", lang=locale))


@pytest.mark.parametrize("locale", LanguageLocale.values())
def test_locale_separator_code_points(locale: str) -> None:
    """Each locale resolves the real grouping/decimal code points (14-I18N-003).

    Pins the separator facts the price assertions below build on. The values are
    read from ``get_format``, so this fails if Django's bundled locale data (or
    the ``bs`` override) drifts — e.g. if ``bs`` lost its comma decimal mark.
    """
    thousands, decimal = _EXPECTED_SEPARATORS[LanguageLocale(locale)]
    assert _thousand_separator(locale) == thousands
    assert _decimal_separator(locale) == decimal


def test_format_price_value_renders_amount_and_currency() -> None:
    """format_price_value renders ``{amount} {currency}``."""
    assert format_price_value(Decimal("500"), CurrencyCode.BAM) == "500 BAM"


@pytest.mark.parametrize("locale", LanguageLocale.values())
def test_format_price_value_uses_intcomma(locale: str) -> None:
    """Amounts localise exactly per locale (14-I18N-003 / VAL-004).

    ``_format_amount`` used to hand a ``str`` to ``intcomma``, which localises
    only ``float``/``Decimal``; a fractional amount then fell into the
    ``use_l10n=False`` branch, leaving the ASCII decimal point and a hard-coded
    comma grouping separator. Passing the ``Decimal`` restores the locale decimal
    mark for fractional amounts while round and grouped amounts keep localising.

    The expected strings are built from the locale's resolved separators, never
    hard-coded, and cover the three cases the defect needs: a fractional amount
    (the defect), a round integer amount (no regression), and a seven-digit
    amount (proves grouping — a five-digit number has at most one group).
    """
    thousands = _thousand_separator(locale)
    decimal = _decimal_separator(locale)
    with override(locale):
        assert (
            format_price_value(Decimal("12345.5"), CurrencyCode.EUR)
            == f"12{thousands}345{decimal}5 EUR"
        )
        assert (
            format_price_value(Decimal("12345"), CurrencyCode.EUR)
            == f"12{thousands}345 EUR"
        )
        assert (
            format_price_value(Decimal("1234567"), CurrencyCode.EUR)
            == f"1{thousands}234{thousands}567 EUR"
        )


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
    """A legacy/seed ad without a price renders an empty string (R-DISP-02)."""
    ad = Ad(price_amount=None, price_currency=None)
    assert format_price(ad) == ""


def test_format_price_filter_free_renders_free() -> None:
    """A Free/Charity ad (price_amount=0) renders 'Free' (R-DISP-01).

    Activated English locale so the assertion is deterministic regardless
    of the project's primary language (RU).
    """
    ad = Ad(price_amount=Decimal("0"), price_currency=CurrencyCode.EUR)
    with override("en"):
        assert format_price(ad) == "Free"
