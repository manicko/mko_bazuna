"""
Tests for the saved-search create flow + modal URL wiring (FT-002).

Covers:
- ``search:save-search`` resolves (CR17).
- POST creates an active ``SavedSearch`` with the captured filters and the
  user's LANGUAGE_CODE.
- Requires authentication.
- The dead ``search:list`` reference is gone from the modal template (R8).
"""

import pytest
from django.test import Client
from django.urls import resolve, reverse

from apps.categories.models import Category
from apps.locations.models import City
from apps.search.models import SavedSearch
from apps.users.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture
def buyer() -> User:
    return User.objects.create(
        telegram_id=930000201,
        chat_id=930000201,
        password="y",
    )


def test_save_search_url_resolves():
    """search:save-search resolves to a view (CR17)."""
    url = reverse("search:save-search")
    assert url == "/save-search/"
    assert resolve(url).func.__name__ == "save_search"


def test_create_saved_search_with_filters_and_language(
    buyer: User, category: Category, city: City, client: Client
) -> None:
    client.force_login(buyer)
    resp = client.post(
        reverse("search:save-search"),
        {
            "query": "велосипед",
            "city_id": str(city.id),
            "category_id": str(category.id),
            "min_price": "100",
            "max_price": "500",
        },
    )
    assert resp.status_code == 200

    ss = SavedSearch.objects.get(user=buyer)
    assert ss.query == "велосипед"
    assert ss.city_id == city.id
    assert ss.category_id == category.id
    assert ss.min_price == 100
    assert ss.max_price == 500
    assert ss.is_active is True
    assert ss.language == "en"  # default LANGUAGE_CODE in test is "en"


def test_requires_login(client: Client) -> None:
    resp = client.post(reverse("search:save-search"), {"query": "тест"})
    # login_required redirect to /login/issue/
    assert resp.status_code in (301, 302)


def test_modal_has_no_dangling_search_list_ref():
    """The save-search modal no longer references the removed search:list route."""
    from pathlib import Path

    modal_path = (
        Path(__file__).resolve().parents[3]
        / "templates"
        / "search"
        / "partials"
        / "save_search_modal.html"
    )
    content = modal_path.read_text(encoding="utf-8")
    # No functional URL reference to the removed route remains.
    assert "url 'search:list'" not in content
    assert 'url "search:list"' not in content
