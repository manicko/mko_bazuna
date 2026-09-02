"""
Price display helpers shared by templates and Telegram alert messages.

Provides the ``format_price`` template filter (turns an ``Ad`` into
``"{amount} {currency}"``) and the ``format_price_value`` Python callable used
by the bot alert messages so that template and bot formatting stay consistent
(spec Assumption 9/11). Returns an empty string when no price is set.
"""

from decimal import ROUND_HALF_UP, Decimal

from django import template
from django.utils.translation import gettext

from apps.currencies.enums import CurrencyCode

register = template.Library()


def format_price_value(
    amount: Decimal | int | float | str | None,
    currency: CurrencyCode | str | None,
) -> str:
    """Render ``"{amount} {currency}"`` from an amount and currency pair.

    Args:
        amount: The seller's original price amount. ``None`` returns "".
        currency: The original price currency code (``CurrencyCode`` member or
            ISO 4217 string).

    Returns:
        The display string e.g. ``"500 BAM"``, or ``""`` when amount is None.
    """
    if amount is None:
        return ""
    if amount == 0:
        return gettext("Free")
    amount_decimal = Decimal(str(amount))
    label = CurrencyCode(currency).value if currency else ""
    return f"{_format_amount(amount_decimal)} {label}".strip()


def _format_amount(value: Decimal) -> str:
    """Format a Decimal amount for display (up to 2 decimals, comma thousands).

    Mirrors Django's ``floatformat`` default (-g): shows an integer without
    decimals when there is no fractional part, otherwise up to two decimals,
    with thousands separators via ``intcomma``.
    """
    from django.contrib.humanize.templatetags.humanize import intcomma

    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP).normalize()
    # normalize() can produce exponent notation for large/small values; format
    # to a plain string preserving up to two decimals.
    formatted = format(rounded, "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return intcomma(formatted)


@register.filter
def format_price(ad) -> str:
    """Render the ad's price as ``"{amount} {currency}"``.

    Uses the ad's original ``price_amount`` + ``price_currency`` (PO-02/Q2).
    Returns an empty string when ``price_amount`` is None.

    Args:
        ad: An ``Ad`` instance (or any object with ``price_amount`` and
            ``price_currency`` attributes).

    Returns:
        E.g. ``"500 BAM"`` or ``""`` when unset.
    """
    return format_price_value(
        getattr(ad, "price_amount", None),
        getattr(ad, "price_currency", None),
    )
