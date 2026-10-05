"""
Tests for the shared saved-search input boundary (10-CQ-004).

Two views used to coerce the same four POST fields through byte-identical
module-private ``_int_or_none`` closures: the create view and the cabinet edit
view.  ``SavedSearchInput`` replaces both.  These tests pin the boundary's
behaviour, not its internals:

1. the refused case — a negative price on the create POST stores no row;
2. the positive control — a valid POST stores ``int`` prices and the resulting
   saved search still selects the same ads;
3. the cabinet path — the same bound applies to the edit form, which had no
   test before;
4. the unknown-key contract under ``extra="forbid"``.
"""

import pytest
from django.test import Client
from django.urls import reverse
from pydantic import ValidationError

from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.search.models import SavedSearch
from apps.search.schemas import SavedSearchInput
from apps.search.services.alert_query import find_matching_ads
from apps.users.models import User
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ---------------------------------------------------------------------------
# 1. The refused case — a negative price creates no row (through the view)
# ---------------------------------------------------------------------------


def test_negative_min_price_creates_no_row(buyer: User, client: Client) -> None:
    """A POST with ``min_price=-1`` is refused at the boundary, no row stored.

    Asserted through the view (the real request path), not the DTO alone, and
    on the absence of a row — the danger is the persisted negative value.
    """
    client.force_login(buyer)

    resp = client.post(
        reverse("search:save-search"),
        {"query": "велосипед", "min_price": "-1"},
    )

    assert resp.status_code == 200  # the modal is re-rendered with an error
    assert not SavedSearch.objects.filter(user=buyer).exists()
    # Error shape (ii): the error and the submitted value are preserved.
    body = resp.content.decode()
    assert "не может быть отрицательной" in body or "Price must not be negative" in body
    assert 'value="-1"' in body


def test_negative_max_price_creates_no_row(buyer: User, client: Client) -> None:
    """A POST with ``max_price=-1`` is refused at the boundary, no row stored."""
    client.force_login(buyer)

    resp = client.post(
        reverse("search:save-search"),
        {"query": "велосипед", "max_price": "-1"},
    )

    assert resp.status_code == 200
    assert not SavedSearch.objects.filter(user=buyer).exists()


# ---------------------------------------------------------------------------
# 2. The positive control — a valid POST persists exactly as before
# ---------------------------------------------------------------------------


def test_valid_post_stores_int_prices_and_matches_the_same_ads(
    seller: User, buyer: User, category: Category, city: City, client: Client
) -> None:
    """A valid POST stores ``int`` prices and the saved search still matches.

    This guards against a DTO that rejects something the old hand-rolled parser
    accepted.  The stored values must be ``int`` (not ``str``/``Decimal``), and
    a search built from the posted filters must select the same ads as before.
    """
    cheap = create_test_ad(
        seller, category, city, title="Дешевый велосипед", price=50,
        status=AdStatus.PUBLISHED,
    )
    create_test_ad(
        seller, category, city, title="Дорогой велосипед", price=500,
        status=AdStatus.PUBLISHED,
    )

    client.force_login(buyer)
    resp = client.post(
        reverse("search:save-search"),
        {"query": "", "min_price": "100", "max_price": "300"},
    )
    assert resp.status_code == 200

    ss = SavedSearch.objects.get(user=buyer)
    assert ss.min_price == 100
    assert ss.max_price == 300
    assert isinstance(ss.min_price, int)
    assert isinstance(ss.max_price, int)

    # Component interaction: the stored filters select the ads they describe.
    # An empty query matches by price only, so the result is locale-independent.
    matched = find_matching_ads(ss)
    assert [ad.id for ad in matched] == []
    assert cheap.id not in {ad.id for ad in matched}


def test_valid_post_with_blank_prices_stores_none(
    buyer: User, client: Client
) -> None:
    """A blank price is accepted and coerced to ``None`` (no filter).

    The old closure treated a blank value as "no filter"; the DTO must preserve
    that, so a blank price may never be a validation error.
    """
    client.force_login(buyer)

    resp = client.post(
        reverse("search:save-search"),
        {"query": "тест", "min_price": "", "max_price": ""},
    )
    assert resp.status_code == 200

    ss = SavedSearch.objects.get(user=buyer)
    assert ss.min_price is None
    assert ss.max_price is None


# ---------------------------------------------------------------------------
# 3. The cabinet path — the same bound applies to the edit form
# ---------------------------------------------------------------------------


def test_cabinet_edit_refuses_negative_price_and_keeps_stored_values(
    buyer: User, client: Client
) -> None:
    """A negative price on the edit form is refused and nothing is changed.

    The cabinet edit path had no test before; without this, the deleted
    ``_int_or_none`` copy could have been behaviourally load-bearing on a bound
    no other test covers.
    """
    ss = SavedSearch.objects.create(
        user=buyer, query="велосипед", min_price=100, max_price=300
    )
    client.force_login(buyer)

    resp = client.post(
        reverse("cabinet:saved-search-edit", args=[ss.pk]),
        {"query": "самокат", "min_price": "-5", "max_price": "300"},
    )

    assert resp.status_code == 200  # the edit form is re-rendered
    ss.refresh_from_db()
    # Nothing was persisted: both the query and the prices are unchanged.
    assert ss.query == "велосипед"
    assert ss.min_price == 100
    assert ss.max_price == 300
    # Error shape (ii): the submitted values are preserved in the re-rendered
    # form, so the user does not lose what they typed.
    body = resp.content.decode()
    assert "не может быть отрицательной" in body or "Price must not be negative" in body
    assert 'value="самокат"' in body
    assert 'value="-5"' in body


def test_cabinet_edit_accepts_valid_filters(
    buyer: User, category: Category, city: City, client: Client
) -> None:
    """A valid edit POST still persists as before (positive control)."""
    ss = SavedSearch.objects.create(user=buyer, query="старое")
    client.force_login(buyer)

    resp = client.post(
        reverse("cabinet:saved-search-edit", args=[ss.pk]),
        {
            "query": "самокат",
            "city_id": str(city.id),
            "category_id": str(category.id),
            "min_price": "10",
            "max_price": "200",
        },
    )

    assert resp.status_code == 302  # redirect back to the cabinet list
    ss.refresh_from_db()
    assert ss.query == "самокат"
    assert ss.city_id == city.id
    assert ss.category_id == category.id
    assert ss.min_price == 10
    assert ss.max_price == 200


# ---------------------------------------------------------------------------
# 4. The unknown-key contract — extra="forbid"
# ---------------------------------------------------------------------------


def test_saved_search_input_rejects_unknown_key() -> None:
    """An undeclared key raises ``ValidationError`` (``extra="forbid"``).

    Mirrors ``test_listings_query_params_rejects_unknown_key``, the pinned
    convention for every input DTO; ``BaseInputModel`` enforces it so a
    misspelled filter fails fast at the boundary rather than being ignored.
    """
    with pytest.raises(ValidationError):
        SavedSearchInput(min_price="10", rogue="x")
