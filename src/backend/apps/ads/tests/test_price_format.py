"""
Tests for the shared ``format_price`` display helper (spec Task 7 / T-11).
"""

import re
from decimal import Decimal

import pytest
from django.template.loader import render_to_string
from django.utils.formats import get_format
from django.utils.translation import override

from apps.ads.models import Ad
from apps.ads.services.listings_query import (
    ListingsQuery,
    build_listings_context,
)
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


# --- active-price filter chip (14-I18N-010) --------------------------------
#
# The shared producer ``build_listings_context`` formats both bounds through
# ``format_price_value`` in its currency-less form before publishing them into
# ``filter_context``. The assertions below read the accessor/producer result -
# the default-independent surface - never the rendered chip chrome, so a locale
# without catalogue support cannot produce a false green (VAL-003).


def _chip_bounds(**kwargs) -> tuple[str | None, str | None]:
    """Return the producer's ``(active_price_min, active_price_max)`` for a query.

    Drives the single producer with sane vector-returning defaults so a test
    only states the price params it cares about.
    """
    built = build_listings_context(
        category_slug=None,
        city_slug=None,
        breadcrumb_category=None,
        sort=None,
        min_price=kwargs.get("min_price"),
        max_price=kwargs.get("max_price"),
        purpose_slug=None,
        condition_slug=None,
        feature_slugs=[],
        page=None,
        user_id=None,
    )
    return (
        built.filter_context["active_price_min"],
        built.filter_context["active_price_max"],
    )


@pytest.mark.django_db
@pytest.mark.parametrize("locale", LanguageLocale.values())
def test_active_price_chip_bounds_match_card_separators(locale: str) -> None:
    """Both chip bounds localise and group exactly like a card price (14-I18N-010).

    Pre-fix the chip interpolated raw ``Decimal`` bounds through ``blocktrans``,
    which applies no filter chain: a bound rendered ungrouped with an ASCII
    decimal point. The producer now routes both bounds through
    ``format_price_value``, so the chip inherits the card's resolved separators.
    The expected strings are built from ``get_format``, never hard-coded, and the
    seven-digit bound proves grouping (a five-digit number has at most one group).
    """
    thousands = _thousand_separator(locale)
    with override(locale):
        min_bound, max_bound = _chip_bounds(min_price="12345", max_price="1234567")
    assert min_bound == f"12{thousands}345"
    assert max_bound == f"1{thousands}234{thousands}567"


@pytest.mark.django_db
def test_active_price_chip_none_bound_renders_exactly_as_before() -> None:
    """An open-ended range renders the literal ``None`` side (14-I18N-010).

    BLOCK 4 constraint 4: a ``None`` bound must render *exactly* as it did
    before the ``blocktrans`` -> ``trans`` change. The old chip interpolated the
    raw bound, so a missing side rendered the literal ``None`` (e.g.
    ``Price: None–500``); the producer preserves ``None`` and the template now
    makes that literal explicit rather than relying on Django's implicit
    coercion, so the rendered output is byte-identical and independent of any
    catalogue support. No new placeholder, no new translatable string.
    """
    assert _chip_bounds(min_price=None, max_price="500") == (None, "500")
    assert _chip_bounds(min_price="500", max_price=None) == ("500", None)
    assert _chip_bounds(min_price=None, max_price=None) == (None, None)


# --- rendered active-price chip (14-I18N-010) ------------------------------
#
# The producer-level assertions above read ``filter_context`` only. These render
# the real partial so the open-bound *output* is pinned, not merely the stored
# value: the validator noted the earlier test never exercised the rendered chip.
# The expected strings are exactly the pre-change ``blocktrans`` output, so a
# regression to the empty-side rendering fails here.

_EN_DASH = "\u2013"
_CHIP_RE = re.compile(r"bg-orange-100[^>]*>\s*(.*?)\s*<a", re.DOTALL)


def _rendered_chip(**kwargs) -> str | None:
    """Render ``ad_list.html`` and return the active-price chip's inner text.

    Uses the real producer plus the partial's minimal context so the assertion
    covers the template, not just ``filter_context``. The chip is uniquely
    identified by its ``bg-orange-100`` class.
    """
    built = build_listings_context(
        category_slug=None,
        city_slug=None,
        breadcrumb_category=None,
        sort=None,
        min_price=kwargs.get("min_price"),
        max_price=kwargs.get("max_price"),
        purpose_slug=None,
        condition_slug=None,
        feature_slugs=[],
        page=None,
        user_id=None,
    )
    context = dict(built.filter_context)
    context.update(
        {
            "query": None,
            "current_features": [],
            "page_obj": None,
            "has_results": None,
            "LANGUAGE_CODE": "en",
        }
    )
    html = render_to_string("ads/partials/ad_list.html", context)
    match = _CHIP_RE.search(html)
    return match.group(1).strip() if match else None


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("min_price", "max_price", "expected"),
    [
        ("500", "900", f"Price: 500{_EN_DASH}900"),
        (None, "500", f"Price: None{_EN_DASH}500"),
        ("500", None, f"Price: 500{_EN_DASH}None"),
    ],
)
def test_active_price_chip_renders_exact_string(
    min_price: str | None, max_price: str | None, expected: str
) -> None:
    """The rendered chip reproduces the pre-change output for every bound shape.

    Covers both bounds set, min-only, and max-only under the English catalogue
    (``Price:`` is the msgid), so the exact separator and the literal open-bound
    ``None`` are pinned. The neither-bound case never reaches the chip: the
    enclosing ``{% if active_price_min or active_price_max %}`` guard suppresses
    it, asserted separately below.
    """
    with override("en"):
        assert _rendered_chip(min_price=min_price, max_price=max_price) == expected


@pytest.mark.django_db
def test_active_price_chip_absent_when_no_bounds() -> None:
    """With neither bound set the enclosing guard suppresses the chip entirely."""
    with override("en"):
        assert _rendered_chip(min_price=None, max_price=None) is None


@pytest.mark.django_db
def test_active_price_range_still_returns_decimals() -> None:
    """``active_price_range`` keeps its Decimal contract; formatting is at the producer.

    The query layer must not learn about display: a ``Decimal`` in a price range
    is the correct type there, and re-typing it would move formatting into the
    query (14-I18N-010, constraint 1).
    """
    built = build_listings_context(
        category_slug=None,
        city_slug=None,
        breadcrumb_category=None,
        sort=None,
        min_price="1000",
        max_price="2000",
        purpose_slug=None,
        condition_slug=None,
        feature_slugs=[],
        page=None,
        user_id=None,
    )
    assert ListingsQuery.active_price_range(built.params) == (
        Decimal("1000"),
        Decimal("2000"),
    )
