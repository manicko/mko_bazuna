"""
Tests for the cabinet sections (CAB-001..CAB-004).

Covers:
- /cabinet/ hub renders with section nav + "Мои объявления" -> /dashboard/.
- Saved-search management: create (disable keeps it, D9), toggle, edit, delete.
- Search-history list + clear.
- Settings page renders as a stub.
"""

import pytest
from django.test import Client

from apps.categories.models import Category
from apps.locations.models import City
from apps.search.models import SavedSearch, SearchHistory
from apps.users.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture
def buyer() -> User:
    return User.objects.create(
        telegram_id=940000201,
        chat_id=940000201,
        password="y",
    )


def _login(buyer: User) -> Client:
    client = Client()
    client.force_login(buyer)
    return client


# ---------------------------------------------------------------------------
# Cabinet hub + nav (CAB-001)
# ---------------------------------------------------------------------------


class TestCabinetHub:
    def test_hub_requires_login(self) -> None:
        assert Client().get("/cabinet/").status_code in (301, 302)

    def test_hub_renders_and_nav_links(self, buyer: User) -> None:
        client = _login(buyer)
        resp = client.get("/cabinet/")
        assert resp.status_code == 200
        content = resp.content.decode()
        # Section nav links (CAB-001)
        for url in [
            "/cabinet/favorites/",
            "/cabinet/saved-searches/",
            "/cabinet/search-history/",
            "/cabinet/settings/",
            # "Мои объявления" -> existing dashboard (C9, unrefactored)
            "/dashboard/",
        ]:
            assert url in content

    def test_settings_stub_renders(self, buyer: User) -> None:
        resp = _login(buyer).get("/cabinet/settings/")
        assert resp.status_code == 200
        assert "Настройки" in resp.content.decode()


# ---------------------------------------------------------------------------
# Saved-search management (CAB-003)
# ---------------------------------------------------------------------------


class TestSavedSearchesManagement:
    def test_create_disable_edit_delete_workflow(
        self, buyer: User, category: Category, city: City
    ) -> None:
        client = _login(buyer)

        # Create via the save-search endpoint.
        client.post(
            "/save-search/",
            {
                "query": "велосипед",
                "city_id": str(city.id),
                "category_id": str(category.id),
                "min_price": "100",
            },
        )
        ss = SavedSearch.objects.get(user=buyer)
        assert ss.is_active is True

        # List shows it.
        resp = client.get("/cabinet/saved-searches/")
        assert resp.status_code == 200
        assert "велосипед" in resp.content.decode()

        # Disable keeps the row (D9): only is_active flips.
        client.post(f"/cabinet/saved-searches/{ss.id}/toggle/")
        ss.refresh_from_db()
        assert ss.is_active is False
        assert SavedSearch.objects.filter(user=buyer).count() == 1

        # Edit persists new filters + language.
        client.post(
            f"/cabinet/saved-searches/{ss.id}/edit/",
            {"query": "самокат", "city_id": "", "category_id": "", "min_price": "", "max_price": "200"},
        )
        ss.refresh_from_db()
        assert ss.query == "самокат"
        assert ss.city_id is None
        assert ss.max_price == 200

        # Delete removes the row (D9).
        client.post(f"/cabinet/saved-searches/{ss.id}/delete/")
        assert SavedSearch.objects.filter(user=buyer).count() == 0

    def test_guest_cannot_manage_other_users_search(
        self, buyer: User, category: Category
    ) -> None:
        other = User.objects.create(
            telegram_id=940000202,
            chat_id=940000202,
            password="x",
        )
        ss = SavedSearch.objects.create(user=other, query="чужой")

        client = _login(buyer)
        # Toggling another user's search returns 404 (scoped to request.user).
        assert client.post(f"/cabinet/saved-searches/{ss.id}/toggle/").status_code == 404
        assert client.post(f"/cabinet/saved-searches/{ss.id}/delete/").status_code == 404


# ---------------------------------------------------------------------------
# Search history (CAB-004)
# ---------------------------------------------------------------------------


class TestSearchHistorySection:
    def test_lists_and_clears_history(self, buyer: User) -> None:
        SearchHistory.objects.create(
            user=buyer, query="велосипед", query_normalized="велосипед"
        )
        SearchHistory.objects.create(
            user=buyer, query="самокат", query_normalized="самокат"
        )

        client = _login(buyer)
        resp = client.get("/cabinet/search-history/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "велосипед" in content
        assert "самокат" in content

        client.post("/cabinet/search-history/clear/")
        assert SearchHistory.objects.filter(user=buyer).count() == 0

        resp = client.get("/cabinet/search-history/")
        assert "Нет истории поиска" in resp.content.decode()
