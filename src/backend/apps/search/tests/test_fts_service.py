"""
Service-tier tests for the FTS pipeline extraction (S1.1).

The pipeline functions previously lived in ``apps.search.views.search`` and now
live in ``apps.search.services.fts``. These tests exercise the **service tier
directly** (no HTTP): they call the moved helpers with explicit parameters and
pin the seams the extraction introduced or must preserve.

Coverage (deliberately complementary to the untouched view suites, which remain
the regression proof for the view path):

1. **Delegation equivalence** — a direct service-tier search returns the same ad
   ids as the equivalent view-level search for the same fixture.
2. **Locale parameter respected** — the same corpus queried through the
   service under different ``LanguageLocale`` members searches the matching
   per-language vector field and returns different ids.
3. **Fuzzy path** — ``_fuzzy_match_by_name`` / ``_fuzzy_category_match``
   semantics through the service (slug short-circuit + exact/fuzzy name tiers).
4. **Cache-hit path + cap semantics** — a warmed cache serves an identical
   page, and the ``SEARCH_CACHE_MAX_HITS + 1`` truncated display is preserved.
"""

from __future__ import annotations

from typing import cast

import pytest

from apps.ads.models import Ad
from apps.ads.services.listings_query import (
    ListingsQuery,
    ListingsQueryParams,
)
from apps.categories.models import Category
from apps.core.enums import AdSort, AdStatus, LanguageLocale
from apps.search.services.cache import (
    SEARCH_CACHE_MAX_HITS,
    build_search_cache_key,
    get_cached_search_ids,
)
from apps.search.services.fts import (
    _apply_fts_filtering,
    _fuzzy_category_match,
    _fuzzy_match_by_name,
    _is_single_word,
    _resolve_search_count,
)
from conftest import create_test_ad, create_test_ads_bulk

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _params() -> ListingsQueryParams:
    """Build default validated params at the service tier (no HTTP)."""
    return ListingsQueryParams(sort=AdSort.DATE_NEW, page=1)


def _service_search_ids(query: str, locale: LanguageLocale) -> list[int]:
    """Run the moved pipeline end-to-end at the service tier.

    Mirrors the view's query path minus the request-coupled parts: build the
    shared params, apply the FTS filter + relevance sort with an explicit
    locale, and return the ordered ids.
    """
    params = _params()
    base_qs = ListingsQuery.build_queryset(params)
    filtered = _apply_fts_filtering(base_qs, query, params, locale)
    return cast("list[int]", list(filtered.values_list("id", flat=True)))


class TestServiceDelegationEquivalence:
    """The service tier reproduces the view-level search result set."""

    def test_service_ids_match_view_ids_for_russian_locale(
        self, seller, category, city, client
    ) -> None:
        """A direct service search returns the same ids the view renders."""
        ad_a = create_test_ad(
            seller,
            category,
            city,
            title="Красный велосипед",
            status=AdStatus.PUBLISHED,
        )
        ad_b = create_test_ad(
            seller,
            category,
            city,
            title="Синий велосипед",
            status=AdStatus.PUBLISHED,
        )
        create_test_ad(
            seller,
            category,
            city,
            title="Самокат",
            status=AdStatus.PUBLISHED,
        )

        service_ids = set(
            _service_search_ids("велосипед", LanguageLocale.RUSSIAN)
        )

        response = client.get("/search/", {"q": "велосипед", "lang": "ru"})
        assert response.status_code == 200
        view_ids = {ad.id for ad in response.context["page_obj"]}

        assert service_ids == view_ids
        assert service_ids == {ad_a.id, ad_b.id}

    def test_single_word_gates_fuzzy_narrowing(self) -> None:
        """``_is_single_word`` is the moved gate the pipeline still relies on."""
        assert _is_single_word("велосипед") is True
        assert _is_single_word("горный велосипед") is False
        assert _is_single_word("") is False


class TestLocaleParameterRespected:
    """The explicit ``locale`` selects the per-language vector field."""

    def test_same_corpus_differs_by_locale_vector(
        self, seller, category, city
    ) -> None:
        """An EN-only token matches under ENGLISH and not under RU/BS.

        The trigger builds ``search_vector_ru`` from ``title``/``description``
        (russian), ``search_vector_bs`` from ``title_bs``/``description_bs``
        (simple) and ``search_vector_en`` from ``title_en``/``description_en``
        (english). The latin token lives only in the English text, so only the
        English vector can match it — a direct proof the service queried the
        locale's vector field via ``LanguageLocale.fts_vector_field``.
        """
        ad = create_test_ad(
            seller,
            category,
            city,
            title="Красный велосипед",
            description="Продается детский велосипед",
            title_en="Red bicycle",
            description_en="Children bicycle for sale",
            status=AdStatus.PUBLISHED,
        )

        en_ids = set(_service_search_ids("bicycle", LanguageLocale.ENGLISH))
        ru_ids = set(_service_search_ids("bicycle", LanguageLocale.RUSSIAN))
        bs_ids = set(_service_search_ids("bicycle", LanguageLocale.BOSNIAN))

        assert ad.id in en_ids
        assert ad.id not in ru_ids
        assert ad.id not in bs_ids

    def test_russian_token_matches_only_russian_vector(
        self, seller, category, city
    ) -> None:
        """A Russian-only token matches under RUSSIAN and not under EN/BS."""
        ad = create_test_ad(
            seller,
            category,
            city,
            title="Красный велосипед",
            description="Продается детский велосипед",
            status=AdStatus.PUBLISHED,
        )

        ru_ids = set(_service_search_ids("велосипед", LanguageLocale.RUSSIAN))
        en_ids = set(_service_search_ids("велосипед", LanguageLocale.ENGLISH))

        assert ad.id in ru_ids
        assert ad.id not in en_ids

    def test_vector_field_and_config_come_from_locale_enum(self) -> None:
        """No raw language string: the enum owns the field/config pairing."""
        assert LanguageLocale.RUSSIAN.fts_vector_field == "search_vector_ru"
        assert LanguageLocale.BOSNIAN.fts_vector_field == "search_vector_bs"
        assert LanguageLocale.ENGLISH.fts_vector_field == "search_vector_en"
        assert LanguageLocale.RUSSIAN.fts_config == "russian"
        assert LanguageLocale.BOSNIAN.fts_config == "simple"
        assert LanguageLocale.ENGLISH.fts_config == "english"


class TestFuzzyPathThroughService:
    """The single-word fuzzy category ladder is callable at the service tier."""

    @pytest.fixture
    def seeded_categories(self) -> list[Category]:
        return [
            Category.objects.create(
                name="Велосипеды",
                slug="bicycles",
                name_i18n={"ru": "Велосипеды", "bs": "Bicikli", "en": "Bicycles"},
            ),
            Category.objects.create(
                name="Электроника",
                slug="electronics",
                name_i18n={"ru": "Электроника", "bs": "Elektronika", "en": "Electronics"},
            ),
        ]

    def test_slug_match_short_circuits_before_name_ladder(
        self, seeded_categories: list[Category]
    ) -> None:
        result = _fuzzy_category_match("bicycles", LanguageLocale.ENGLISH)
        assert result is not None
        assert result.slug == "bicycles"

    def test_exact_and_fuzzy_name_tiers_resolve(
        self, seeded_categories: list[Category]
    ) -> None:
        exact = _fuzzy_match_by_name("Bicycles", LanguageLocale.ENGLISH)
        assert exact is not None
        assert exact.slug == "bicycles"

        near = _fuzzy_match_by_name("Bicycle", LanguageLocale.ENGLISH)
        assert near is not None
        assert near.slug == "bicycles"

    def test_distant_non_match_returns_none(
        self, seeded_categories: list[Category]
    ) -> None:
        assert _fuzzy_match_by_name("Zzzzz", LanguageLocale.ENGLISH) is None
        assert _fuzzy_category_match("xyzqwerty", LanguageLocale.RUSSIAN) is None

    def test_ambiguous_exact_name_returns_no_guess(self) -> None:
        """Two active categories sharing a display name yield no narrowing."""
        Category.objects.create(
            name="Одежда",
            slug="clothing-a",
            name_i18n={"ru": "Одежда", "bs": "Odjeća", "en": "Clothing"},
        )
        Category.objects.create(
            name="Одежда",
            slug="clothing-b",
            name_i18n={"ru": "Одежда", "bs": "Odjeća", "en": "Clothing"},
        )
        assert _fuzzy_match_by_name("Одежда", LanguageLocale.RUSSIAN) is None


class TestCacheHitPathAndCapSemantics:
    """The moved cache composition is unchanged: same keys, same cap sem."""

    def test_second_call_serves_cached_ids_identically(
        self, seller, category, city
    ) -> None:
        """A warmed cache returns the identical ordered id list."""
        create_test_ads_bulk(
            seller,
            category,
            city,
            5,
            title_prefix="Кэш товар",
            status=AdStatus.PUBLISHED,
        )
        params = _params()
        query = "товар"
        locale = LanguageLocale.RUSSIAN
        cache_key = build_search_cache_key(params, query, locale)

        def producer() -> list[int]:
            base_qs = ListingsQuery.build_queryset(params)
            filtered = _apply_fts_filtering(base_qs, query, params, locale)
            return cast(
                "list[int]",
                list(filtered.values_list("id", flat=True)[:SEARCH_CACHE_MAX_HITS]),
            )

        cold = get_cached_search_ids(cache_key, producer)
        warm = get_cached_search_ids(cache_key, producer)

        assert cold is not None
        assert warm == cold
        assert len(cold) == 5

    def test_resolve_search_count_cap_semantics(self) -> None:
        """A cached list at/over the cap reports ``SEARCH_CACHE_MAX_HITS + 1``."""
        unused_qs = Ad.objects.none()
        below = [1, 2, 3]
        total, truncated = _resolve_search_count(below, unused_qs)
        assert total == 3
        assert truncated is False

        at_cap = list(range(SEARCH_CACHE_MAX_HITS))
        total, truncated = _resolve_search_count(at_cap, unused_qs)
        assert total == SEARCH_CACHE_MAX_HITS + 1
        assert truncated is True

    def test_bounded_producer_truncates_at_cap(
        self, seller, category, city
    ) -> None:
        """The producer's SQL LIMIT bounds the cached id list at the cap."""
        create_test_ads_bulk(
            seller,
            category,
            city,
            SEARCH_CACHE_MAX_HITS + 1,
            title_prefix="Продам велосипед",
            status=AdStatus.PUBLISHED,
        )
        params = _params()
        locale = LanguageLocale.RUSSIAN

        def producer() -> list[int]:
            base_qs = ListingsQuery.build_queryset(params)
            filtered = _apply_fts_filtering(base_qs, "велосипед", params, locale)
            return cast(
                "list[int]",
                list(filtered.values_list("id", flat=True)[:SEARCH_CACHE_MAX_HITS]),
            )

        ids = producer()
        assert len(ids) == SEARCH_CACHE_MAX_HITS

        total, truncated = _resolve_search_count(ids, Ad.objects.none())
        assert total == SEARCH_CACHE_MAX_HITS + 1
        assert truncated is True
