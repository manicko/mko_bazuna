"""
Tests for the search autocomplete feature.

Covers:
- Autocomplete HTTP endpoint (happy path, empty query, rate limiting, dedup)
- Popular search service (increment, get suggestions)
- Search history service (record, get, pruning, anonymous user)
- Entity suggestions (prefix matching, category/city lookup)
- Search view wiring (popular search + history recorded on search)
"""

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from apps.analytics.models import AnalyticsEvent
from apps.categories.models import Category
from apps.core.enums import AdStatus, AnalyticsEventType, SearchSuggestionSource
from apps.locations.models import City
from apps.search.models import PopularSearch, SearchHistory
from apps.search.services.entity_suggestions import get_entity_suggestions
from apps.search.services.popular_search import (
    get_popular_suggestions,
    increment_popular_search,
)
from apps.search.services.search_history import (
    get_user_search_history,
    record_search_history,
)
from apps.users.models import User

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def buyer() -> User:
    """Create a registered buyer user."""
    return User.objects.create(
        telegram_id=900000021,
        chat_id=900000021,
        password="y",
    )


@pytest.fixture
def root_category() -> Category:
    """Create a root-level category."""
    return Category.objects.create(name="Транспорт", slug="transport")


@pytest.fixture
def child_category(root_category: Category) -> Category:
    """Create a child category under root_category."""
    return Category.objects.create(
        name="Велосипеды", slug="bicycles", parent=root_category
    )


@pytest.fixture
def inactive_category() -> Category:
    """Create an inactive category (should not appear in suggestions)."""
    return Category.objects.create(name="Устаревшее", slug="old", is_active=False)


@pytest.fixture
def city2() -> City:
    """Create another city."""
    return City.objects.create(
        country_code="ME",
        name="Москва",
        region="Central",
        slug="moscow",
    )


# ---------------------------------------------------------------------------
# Autocomplete HTTP endpoint
# ---------------------------------------------------------------------------


class TestAutocompleteEndpoint:
    """Integration tests for the autocomplete HTTP endpoint."""

    @pytest.fixture(autouse=True)
    def _reset_rate_limit(self) -> None:
        """Clear the rate-limit cache before each test to prevent state bleed.

        The rate limiter keys on the client IP (127.0.0.1 in tests), and
        ``test_autocomplete_rate_limit`` exhausts the per-IP limit, so without
        a reset subsequent endpoint tests would be rejected with 429.
        """
        cache.clear()

    def test_autocomplete_returns_suggestions(
        self, buyer: User, root_category: Category, city: City
    ) -> None:
        """Happy path: valid query returns merged suggestions as JSON."""
        # Seed popular search data
        PopularSearch.objects.create(
            query="транспорт", query_normalized="транспорт", hit_count=15
        )
        # Seed entity data
        Category.objects.create(name="Транзисторы", slug="transistors", is_active=True)
        City.objects.create(
            country_code="ME",
            name="Требинье",
            region="RS",
            slug="trebinje",
        )
        # Seed user history
        SearchHistory.objects.create(
            user=buyer, query="транспорт", query_normalized="транспорт"
        )

        client = Client()
        client.force_login(buyer)
        response = client.get("/api/search/autocomplete", {"q": "тран"})

        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data
        assert len(data["suggestions"]) > 0

        # Verify structure of each suggestion
        for suggestion in data["suggestions"]:
            assert "text" in suggestion
            assert "source" in suggestion
            assert "type" in suggestion
            assert suggestion["source"] in [
                SearchSuggestionSource.USER_HISTORY.value,
                SearchSuggestionSource.POPULAR_SEARCH.value,
                SearchSuggestionSource.CATEGORY.value,
                SearchSuggestionSource.CITY.value,
            ]

    def test_autocomplete_empty_query_returns_empty(
        self,
    ) -> None:
        """Empty or too-short query returns empty suggestions list."""
        client = Client()

        # No query parameter
        response = client.get("/api/search/autocomplete")
        assert response.status_code == 200
        assert response.json()["suggestions"] == []

        # Too short query
        response = client.get("/api/search/autocomplete", {"q": "a"})
        assert response.status_code == 200
        assert response.json()["suggestions"] == []

    def test_autocomplete_rate_limit(
        self,
    ) -> None:
        """Exceeding rate limit returns 429 response."""
        # Clear any existing rate limit state
        cache.clear()

        client = Client()
        # Make 30+ requests (the rate limit) to the autocomplete endpoint
        for i in range(31):
            response = client.get("/api/search/autocomplete", {"q": "тест"})
            if i < 30:
                assert response.status_code == 200, f"Request {i} should be allowed"
            else:
                assert response.status_code == 429, (
                    f"Request {i} should be rate limited"
                )
                assert response.json()["error"] == "rate_limit"

    def test_autocomplete_deduplication(
        self, buyer: User, root_category: Category
    ) -> None:
        """Duplicate 'text' values across sources are merged."""
        # Create a category and popular search with the same text
        Category.objects.create(name="Телефоны", slug="phones", is_active=True)
        PopularSearch.objects.create(
            query="телефоны", query_normalized="телефоны", hit_count=50
        )
        SearchHistory.objects.create(
            user=buyer, query="телефоны", query_normalized="телефоны"
        )

        client = Client()
        client.force_login(buyer)
        response = client.get("/api/search/autocomplete", {"q": "тел"})

        assert response.status_code == 200
        suggestions = response.json()["suggestions"]
        # "телефоны" should appear only once
        texts = [s["text"] for s in suggestions]
        assert texts.count("телефоны") == 1

    def test_autocomplete_user_history_has_type_field(
        self, buyer: User, root_category: Category
    ) -> None:
        """User-history suggestions carry ``type == source == 'user_history'``."""
        SearchHistory.objects.create(
            user=buyer, query="телефоны", query_normalized="телефоны"
        )

        client = Client()
        client.force_login(buyer)
        response = client.get("/api/search/autocomplete", {"q": "тел"})

        assert response.status_code == 200
        user_history_suggestions = [
            s
            for s in response.json()["suggestions"]
            if s["source"] == SearchSuggestionSource.USER_HISTORY.value
        ]
        assert len(user_history_suggestions) == 1
        assert (
            user_history_suggestions[0]["type"]
            == SearchSuggestionSource.USER_HISTORY.value
        )

    def test_autocomplete_anonymous_user_returns_popular_and_entities(
        self, root_category: Category, city: City
    ) -> None:
        """Anonymous users with no session history get popular + entity suggestions."""
        PopularSearch.objects.create(
            query="велосипед", query_normalized="велосипед", hit_count=20
        )
        Category.objects.create(name="Верхняя одежда", slug="outerwear", is_active=True)
        City.objects.create(
            country_code="ME",
            name="Варшава",
            region="Mazowieckie",
            slug="warsaw",
        )

        client = Client()
        response = client.get("/api/search/autocomplete", {"q": "ве"})

        assert response.status_code == 200
        suggestions = response.json()["suggestions"]
        # Should have popular search and possibly entity matches
        assert len(suggestions) > 0
        # No user_history source for anonymous with no session history
        for s in suggestions:
            assert s["source"] != SearchSuggestionSource.USER_HISTORY.value

    def test_autocomplete_anonymous_user_returns_session_history(
        self, root_category: Category, city: City
    ) -> None:
        """Anonymous users get their session-scoped history in suggestions."""
        # Record session history via the anonymous search flow, then query.
        client = Client()
        client.get("/search/?q=велосипед-сессия")
        response = client.get("/api/search/autocomplete", {"q": "вел"})
        assert response.status_code == 200
        suggestions = response.json()["suggestions"]
        user_history = [
            s["text"]
            for s in suggestions
            if s["source"] == SearchSuggestionSource.USER_HISTORY.value
        ]
        assert "велосипед-сессия" in user_history

    def test_autocomplete_malicious_query_sanitized(
        self,
    ) -> None:
        """SQL injection characters in query are stripped."""
        client = Client()
        response = client.get("/api/search/autocomplete", {"q": "'; DROP TABLE--"})
        assert response.status_code == 200
        assert response.json()["suggestions"] == []


# ---------------------------------------------------------------------------
# Popular search service
# ---------------------------------------------------------------------------


class TestPopularSearchService:
    """Tests for the popular_search service."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self) -> None:
        """Clear Django cache between tests to prevent bleeding popular-search state."""
        cache.clear()

    def test_increment_popular_search_creates_new_entry(self) -> None:
        """First call creates a new PopularSearch entry with hit_count=1."""
        increment_popular_search("тест")
        entry = PopularSearch.objects.get(query_normalized="тест")
        assert entry.hit_count == 1
        assert entry.query == "тест"

    def test_increment_popular_search_increments_existing(self) -> None:
        """Subsequent calls increment the hit_count atomically."""
        increment_popular_search("тест")
        increment_popular_search("тест")
        increment_popular_search("тест")
        entry = PopularSearch.objects.get(query_normalized="тест")
        assert entry.hit_count == 3

    def test_increment_popular_search_empty_query_is_noop(self) -> None:
        """Empty or whitespace-only query is a no-op."""
        increment_popular_search("")
        increment_popular_search("   ")
        assert PopularSearch.objects.count() == 0

    def test_get_popular_suggestions_returns_matching_queries(self) -> None:
        """Returns popular queries matching prefix, ordered by hit_count desc."""
        PopularSearch.objects.create(
            query="велосипед", query_normalized="велосипед", hit_count=20
        )
        PopularSearch.objects.create(
            query="веревка", query_normalized="веревка", hit_count=15
        )
        PopularSearch.objects.create(
            query="вертолет", query_normalized="вертолет", hit_count=5
        )

        results = get_popular_suggestions("ве")
        # Only queries with hit_count >= 10
        assert len(results) == 2
        # Ordered by popularity descending
        assert results[0]["text"] == "велосипед"
        assert results[1]["text"] == "веревка"

    def test_get_popular_suggestions_no_match_returns_empty(self) -> None:
        """No matching prefix returns empty list."""
        PopularSearch.objects.create(
            query="автомобиль", query_normalized="автомобиль", hit_count=50
        )
        results = get_popular_suggestions("xyz")
        assert results == []

    def test_get_popular_suggestions_empty_prefix(self) -> None:
        """Empty prefix returns empty list."""
        assert get_popular_suggestions("") == []
        assert get_popular_suggestions("   ") == []


# ---------------------------------------------------------------------------
# Search history service
# ---------------------------------------------------------------------------


class TestSearchHistoryService:
    """Tests for the search_history service."""

    def test_record_search_history_creates_entry(self, buyer: User) -> None:
        """Recording a search creates a SearchHistory entry."""
        record_search_history(buyer.id, "тест")
        assert SearchHistory.objects.filter(
            user=buyer, query_normalized="тест"
        ).exists()

    def test_record_search_history_anonymous_without_session_is_noop(self) -> None:
        """Anonymous user with no session is a no-op."""
        record_search_history(None, "тест")
        assert SearchHistory.objects.count() == 0

    def test_record_search_history_anonymous_session_scoped(self) -> None:
        """Anonymous user history is stored in the session (not the DB)."""
        from django.contrib.sessions.backends.db import SessionStore

        session = SessionStore()

        record_search_history(None, "Тест", session=session)
        record_search_history(None, "тест", session=session)  # dedup by normalized

        # Nothing written to the DB.
        assert SearchHistory.objects.count() == 0
        # Stored in the session, deduped to a single entry.
        assert len(session["search_history"]) == 1
        assert session["search_history"][0]["query_normalized"] == "тест"

    def test_record_search_history_anonymous_session_caps_at_50(self) -> None:
        """Anonymous session history is capped at 50 entries."""
        from django.contrib.sessions.backends.db import SessionStore

        session = SessionStore()
        for i in range(60):
            record_search_history(None, f"query{i}", session=session)

        assert len(session["search_history"]) == 50

    def test_record_search_history_deduplicates(self, buyer: User) -> None:
        """Same normalized query replaces previous entry."""
        record_search_history(buyer.id, "Тест")
        record_search_history(buyer.id, "тест")
        entries = SearchHistory.objects.filter(user=buyer, query_normalized="тест")
        assert entries.count() == 1

    def test_record_search_history_empty_query(self, buyer: User) -> None:
        """Empty or whitespace query is a no-op."""
        record_search_history(buyer.id, "")
        record_search_history(buyer.id, "   ")
        assert SearchHistory.objects.filter(user=buyer).count() == 0

    def test_get_user_search_history_returns_recent(self, buyer: User) -> None:
        """Returns most recent queries first."""
        record_search_history(buyer.id, "первый")
        record_search_history(buyer.id, "второй")
        record_search_history(buyer.id, "третий")

        results = get_user_search_history(buyer.id)
        assert results == ["третий", "второй", "первый"]

    def test_get_user_search_history_anonymous_returns_empty(self) -> None:
        """Anonymous user with no session returns empty list."""
        assert get_user_search_history(None) == []

    def test_get_user_search_history_anonymous_session(self) -> None:
        """Anonymous user returns session history when present, most-recent-first."""
        from django.contrib.sessions.backends.db import SessionStore

        session = SessionStore()
        record_search_history(None, "первый", session=session)
        record_search_history(None, "второй", session=session)

        assert get_user_search_history(None, session=session) == ["второй", "первый"]
        assert get_user_search_history(None, limit=1, session=session) == ["второй"]

    def test_get_user_search_history_respects_limit(self, buyer: User) -> None:
        """Limit parameter caps the number of results."""
        for i in range(10):
            record_search_history(buyer.id, f"query{i}")
        assert len(get_user_search_history(buyer.id, limit=3)) == 3

    def test_history_pruning(self, buyer: User) -> None:
        """History is pruned to 50 entries per user."""
        for i in range(55):
            record_search_history(buyer.id, f"query{i}")
        assert SearchHistory.objects.filter(user=buyer).count() == 50

    def test_get_user_search_history_with_prefix_db(self, buyer: User) -> None:
        """Prefix filter limits DB-backed history to queries starting with prefix."""
        record_search_history(buyer.id, "велосипед")
        record_search_history(buyer.id, "автомобиль")
        record_search_history(buyer.id, "велосипедный")

        results = get_user_search_history(buyer.id, prefix="ве")

        assert "велосипед" in results
        assert "велосипедный" in results
        assert "автомобиль" not in results

    def test_get_user_search_history_prefix_case_insensitive(self, buyer: User) -> None:
        """Prefix matching against DB history is case-insensitive."""
        record_search_history(buyer.id, "Велосипед")

        results = get_user_search_history(buyer.id, prefix="ве")

        assert "Велосипед" in results

    def test_get_user_search_history_prefix_session(self) -> None:
        """Prefix filter works for anonymous session-backed history."""
        from django.contrib.sessions.backends.db import SessionStore

        session = SessionStore()
        record_search_history(None, "велосипед", session=session)
        record_search_history(None, "автомобиль", session=session)

        results = get_user_search_history(None, prefix="ве", session=session)

        assert "велосипед" in results
        assert "автомобиль" not in results

    def test_get_user_search_history_no_prefix_returns_all(self, buyer: User) -> None:
        """Without a prefix, all history is returned (unchanged behavior)."""
        record_search_history(buyer.id, "велосипед")
        record_search_history(buyer.id, "автомобиль")

        results = get_user_search_history(buyer.id)

        assert "велосипед" in results
        assert "автомобиль" in results


# ---------------------------------------------------------------------------
# Entity suggestions service
# ---------------------------------------------------------------------------


class TestEntitySuggestionsService:
    """Tests for the entity_suggestions service."""

    def test_returns_matching_categories(self, root_category: Category) -> None:
        """Returns categories matching the prefix."""
        results = get_entity_suggestions("тран")
        texts = [r["text"] for r in results]
        assert "Транспорт" in texts

    def test_uses_prefix_matching(self, root_category: Category) -> None:
        """Uses istartswith (prefix match), not full-text contains."""
        # "спорт" should NOT match "Транспорт" (it contains "спорт" but doesn't start with it)
        results = get_entity_suggestions("спорт")
        texts = [r["text"] for r in results]
        assert "Транспорт" not in texts

    def test_excludes_inactive_categories(self, inactive_category: Category) -> None:
        """Inactive categories are excluded from suggestions."""
        results = get_entity_suggestions("уста")
        texts = [r["text"] for r in results]
        assert "Устаревшее" not in texts

    def test_returns_matching_cities(self, city: City, city2: City) -> None:
        """Returns cities matching the prefix."""
        results = get_entity_suggestions("тест")
        texts = [r["text"] for r in results]
        assert "Тестград" in texts

    def test_empty_prefix_returns_empty(self) -> None:
        """Empty prefix returns empty list."""
        assert get_entity_suggestions("") == []
        assert get_entity_suggestions("   ") == []

    def test_suggestion_structure(self, root_category: Category, city: City) -> None:
        """Each suggestion has text, source, and type keys."""
        results = get_entity_suggestions("т")
        for r in results:
            assert "text" in r
            assert "source" in r
            assert "type" in r
            assert r["source"] in [
                SearchSuggestionSource.CATEGORY.value,
                SearchSuggestionSource.CITY.value,
            ]

    def test_category_suggestion_has_category_path(
        self, root_category: Category, child_category: Category
    ) -> None:
        """Category suggestions expose a root→leaf ``category_path`` string."""
        results = get_entity_suggestions("вел")
        cat = next((r for r in results if r.get("type") == "category"), None)
        assert cat is not None
        assert "category_path" in cat
        assert cat["category_path"] == "Транспорт > Велосипеды"

    def test_entity_suggestions_expose_slug(
        self, root_category: Category, child_category: Category, city: City
    ) -> None:
        """Category and city suggestions expose a ``slug`` for click navigation."""
        cat_results = get_entity_suggestions("вел")
        cat = next((r for r in cat_results if r.get("type") == "category"), None)
        assert cat is not None
        assert cat["slug"] == "bicycles"

        city_results = get_entity_suggestions("тест")
        city_sug = next((r for r in city_results if r.get("type") == "city"), None)
        assert city_sug is not None
        assert city_sug["slug"] == city.slug

    def test_non_category_sources_omit_category_path(self, city: City) -> None:
        """City suggestions carry no ``category_path`` key."""
        results = get_entity_suggestions("тест")
        for r in results:
            if r.get("type") != "category":
                assert "category_path" not in r

    def test_entity_suggestions_localized_bs(
        self, root_category: Category, city: City
    ) -> None:
        """``locale='bs'`` returns Bosnian names from ``name_i18n``."""
        root_category.name_i18n = {"ru": "Транспорт", "bs": "Prevoz"}
        root_category.save(update_fields=["name_i18n"])
        city.name_i18n = {"ru": "Тестград", "bs": "Testgrad"}
        city.save(update_fields=["name_i18n"])

        results = get_entity_suggestions("тран", locale="bs")
        cat = next((r for r in results if r.get("type") == "category"), None)
        assert cat is not None
        assert cat["text"] == "Prevoz"
        assert cat["category_path"] == "Prevoz"

    def test_entity_suggestions_localized_en(
        self, root_category: Category, city: City
    ) -> None:
        """``locale='en'`` returns English names from ``name_i18n``."""
        root_category.name_i18n = {"ru": "Транспорт", "en": "Transport"}
        root_category.save(update_fields=["name_i18n"])

        results = get_entity_suggestions("тран", locale="en")
        cat = next((r for r in results if r.get("type") == "category"), None)
        assert cat is not None
        assert cat["text"] == "Transport"

    def test_entity_suggestions_localized_falls_back_to_ru(
        self, root_category: Category
    ) -> None:
        """Locale with no translation falls back to Russian name."""
        root_category.name_i18n = {"ru": "Транспорт"}
        root_category.save(update_fields=["name_i18n"])

        results = get_entity_suggestions("тран", locale="bs")
        cat = next((r for r in results if r.get("type") == "category"), None)
        assert cat is not None
        assert cat["text"] == "Транспорт"

    def test_entity_suggestions_localized_category_path_bs(
        self, root_category: Category, child_category: Category
    ) -> None:
        """Category path is localized via the locale parameter."""
        root_category.name_i18n = {"ru": "Транспорт", "bs": "Prevoz"}
        root_category.save(update_fields=["name_i18n"])
        child_category.name_i18n = {"ru": "Велосипеды", "bs": "Bicikli"}
        child_category.save(update_fields=["name_i18n"])

        results = get_entity_suggestions("вел", locale="bs")
        cat = next((r for r in results if r.get("type") == "category"), None)
        assert cat is not None
        assert cat["text"] == "Bicikli"
        assert cat["category_path"] == "Prevoz > Bicikli"


# ---------------------------------------------------------------------------
# Rate limit service
# ---------------------------------------------------------------------------


class TestRateLimitService:
    """Tests for the rate limit service."""

    def test_rate_limit_blocks_after_threshold(self) -> None:
        """Rate limit check returns False after exceeding threshold."""
        from apps.search.services.rate_limit import rate_limit_check

        cache.clear()
        # Make a mock request
        from django.http import HttpRequest

        request = HttpRequest()
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        # First 30 requests should be allowed
        for i in range(30):
            assert rate_limit_check(request), f"Request {i} should be allowed"

        # 31st request should be blocked
        assert not rate_limit_check(request), "Request 31 should be rate limited"


# ---------------------------------------------------------------------------
# Search view recording
# ---------------------------------------------------------------------------


class TestSearchViewRecordsAutocompleteData:
    """Search view should record popular searches and user history."""

    def test_search_records_popular_search(
        self, seller: User, root_category: Category, city: City
    ) -> None:
        """Searching with a query increments popular search."""
        from apps.search.models import PopularSearch

        # Create a published ad so search has results
        create_test_ad(seller, root_category, city, title="Велосипед для продажи", description="Отличный велосипед", status=AdStatus.PUBLISHED, published_at=timezone.now())

        client = Client()
        # Make a search request - this should record the popular search
        # Note: FTS may not match in test (no search_vector trigger), but
        # the recording happens regardless of results
        client.get("/search/?q=велосипед")

        # Check that popular search was recorded
        entry = PopularSearch.objects.filter(query_normalized="велосипед").first()
        # The entry exists because increment_popular_search is called
        assert entry is not None
        assert entry.hit_count >= 1

    def test_search_records_user_history(
        self, buyer: User, root_category: Category, city: City
    ) -> None:
        """Authenticated user's search is recorded in history."""
        create_test_ad(buyer, root_category, city, title="Велосипед для продажи", description="Отличный велосипед", status=AdStatus.PUBLISHED, published_at=timezone.now())

        client = Client()
        client.force_login(buyer)
        client.get("/search/?q=велосипед")

        assert SearchHistory.objects.filter(
            user=buyer, query_normalized="велосипед"
        ).exists()

    def test_search_anonymous_records_session_history(
        self, seller: User, root_category: Category, city: City
    ) -> None:
        """Anonymous user's search IS recorded in session history (not the DB)."""
        create_test_ad(seller, root_category, city, title="Велосипед для продажи", description="Отличный велосипед", status=AdStatus.PUBLISHED, published_at=timezone.now())

        client = Client()
        client.get("/search/?q=велосипед")

        # Anonymous user should NOT have DB history...
        assert SearchHistory.objects.filter(query_normalized="велосипед").count() == 0

        # ...but SHOULD have session-scoped history.
        session = client.session
        assert any(
            e["query_normalized"] == "велосипед"
            for e in (session.get("search_history") or [])
        )

        # And popular search should still be recorded
        assert PopularSearch.objects.filter(query_normalized="велосипед").exists()

    def test_search_context_has_breadcrumb_category(
        self, seller: User, root_category: Category, city: City
    ) -> None:
        """Search view exposes the resolved category for breadcrumbs (T-500)."""
        create_test_ad(seller, root_category, city, title="Велосипед для продажи", description="Отличный велосипед", status=AdStatus.PUBLISHED, published_at=timezone.now())
        client = Client()
        response = client.get("/search/", {"category": "transport"})
        assert response.status_code == 200
        assert response.context["breadcrumb_category"] == root_category

    def test_search_records_analytics_event(
        self, seller: User, root_category: Category, city: City
    ) -> None:
        """Searching with a query creates an AnalyticsEvent (SEARCH_PERFORMED)."""
        create_test_ad(
            seller,
            root_category,
            city,
            title="Велосипед для продажи",
            description="Отличный велосипед",
            status=AdStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        client = Client()
        client.get("/search/?q=велосипед")
        assert AnalyticsEvent.objects.filter(
            event_type=AnalyticsEventType.SEARCH_PERFORMED
        ).exists()
