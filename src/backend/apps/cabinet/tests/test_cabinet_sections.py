"""
Tests for the cabinet sections (CAB-001..CAB-004).

Covers:
- /cabinet/ hub renders with section nav + "Мои объявления" -> /dashboard/.
- Saved-search management: create (disable keeps it, D9), toggle, edit, delete.
- Search-history list + clear.
- Settings page renders as a stub.
"""

from __future__ import annotations

import pytest
from django.test import Client

from apps.categories.models import Category
from apps.locations.models import City
from apps.search.models import SavedSearch, SearchHistory
from apps.users.models import User
from conftest import make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Cabinet hub + nav (CAB-001)
# ---------------------------------------------------------------------------


class TestCabinetHub:
    def test_hub_requires_login(self) -> None:
        assert Client().get("/cabinet/").status_code in (301, 302)

    def test_hub_renders_and_nav_links(self, buyer_client: Client) -> None:
        resp = buyer_client.get("/cabinet/?lang=ru")
        assert resp.status_code == 200
        content = resp.content.decode()
        # Section nav links (CAB-001)
        for url in [
            "/cabinet/favorites/",
            "/cabinet/saved-searches/",
            "/cabinet/search-history/",
            "/cabinet/settings/",
        ]:
            assert url in content
        # "Мои объявления" -> existing dashboard (C9, unrefactored).
        # Assert the nav link's visible text, not the /dashboard/ URL.
        assert "Мои объявления" in content

    def test_settings_stub_renders(self, buyer_client: Client) -> None:
        resp = buyer_client.get("/cabinet/settings/?lang=ru")
        assert resp.status_code == 200
        assert "Настройки" in resp.content.decode()


# ---------------------------------------------------------------------------
# Saved-search management (CAB-003)
# ---------------------------------------------------------------------------


class TestSavedSearchesManagement:
    def test_create_disable_edit_delete_workflow(
        self,
        buyer_client: Client,
        buyer: User,
        category: Category,
        city: City,
    ) -> None:
        # Create via ORM — the /save-search/ create path is already covered by
        # test_saved_search_create.py (FIND-7).
        ss = SavedSearch.objects.create(
            user=buyer,
            query="велосипед",
            city=city,
            category=category,
            min_price=100,
            max_price=500,
            is_active=True,
        )

        # List shows it.
        resp = buyer_client.get("/cabinet/saved-searches/")
        assert resp.status_code == 200
        assert "велосипед" in resp.content.decode()

        # Disable keeps the row (D9): only is_active flips.
        resp = buyer_client.post(f"/cabinet/saved-searches/{ss.id}/toggle/")
        assert resp.status_code == 200
        ss.refresh_from_db()
        assert ss.is_active is False
        assert SavedSearch.objects.filter(user=buyer).count() == 1

        # Edit persists new filters + language.
        # The edit view sets language=request.LANGUAGE_CODE ("en" in the test
        # env), so asserting ss.language == "en" confirms the view persisted
        # the request language rather than leaving the model default ("bs").
        resp = buyer_client.post(
            f"/cabinet/saved-searches/{ss.id}/edit/",
            {
                "query": "самокат",
                "city_id": "",
                "category_id": "",
                "min_price": "",
                "max_price": "200",
            },
        )
        assert resp.status_code == 302
        ss.refresh_from_db()
        assert ss.query == "самокат"
        assert ss.city_id is None
        assert ss.max_price == 200
        assert ss.language == "en"

        # Delete removes the row (D9).
        buyer_client.post(f"/cabinet/saved-searches/{ss.id}/delete/")
        assert SavedSearch.objects.filter(user=buyer).count() == 0

    def test_guest_cannot_manage_other_users_search(
        self, buyer_client: Client
    ) -> None:
        other = make_user(940000202)
        ss = SavedSearch.objects.create(user=other, query="чужой")

        # Toggling another user's search returns 404 (scoped to request.user).
        assert (
            buyer_client.post(f"/cabinet/saved-searches/{ss.id}/toggle/")
            .status_code
            == 404
        )
        assert (
            buyer_client.post(f"/cabinet/saved-searches/{ss.id}/delete/")
            .status_code
            == 404
        )


# ---------------------------------------------------------------------------
# Search history (CAB-004)
# ---------------------------------------------------------------------------


class TestSearchHistorySection:
    def test_lists_and_clears_history(
        self, buyer_client: Client, buyer: User
    ) -> None:
        SearchHistory.objects.create(
            user=buyer, query="велосипед", query_normalized="велосипед"
        )
        SearchHistory.objects.create(
            user=buyer, query="самокат", query_normalized="самокат"
        )

        resp = buyer_client.get("/cabinet/search-history/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "велосипед" in content
        assert "самокат" in content

        buyer_client.post("/cabinet/search-history/clear/")
        assert SearchHistory.objects.filter(user=buyer).count() == 0

        resp = buyer_client.get("/cabinet/search-history/?lang=ru")
        assert "Нет истории поиска" in resp.content.decode()


# ---------------------------------------------------------------------------
# Anonymous POST gate on mutating cabinet endpoints (CAB-002/3/4 auth guard)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "/cabinet/saved-searches/1/toggle/",
        "/cabinet/saved-searches/1/edit/",
        "/cabinet/saved-searches/1/delete/",
        "/cabinet/search-history/clear/",
    ],
)
def test_anon_post_mutating_cabinet_endpoint_redirects(url: str) -> None:
    """Every mutating cabinet POST is ``@login_required``.

    Anonymous POSTs receive a 302 redirect to ``/login/issue/?next=...``
    rather than touching the DB row (pk is irrelevant — login_required
    short-circuits before the view body runs).
    """
    resp = Client().post(url)
    assert resp.status_code == 302
    assert resp.url.startswith("/login/issue/")
    assert "next=" in resp.url
