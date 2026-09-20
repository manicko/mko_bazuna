"""Regression tests for locale-aware ad-data service functions (I18N-001).

Verifies that ``build_purpose_keyboard``, ``build_condition_keyboard``,
``build_feature_keyboard``, and ``get_feature_names`` all accept an explicit
``locale`` parameter and return correctly localized labels — never the
hardcoded ``"ru"`` that was previously embedded in the service code.
"""

from __future__ import annotations

import pytest
from asgiref.sync import sync_to_async
from django.utils import translation

from apps.lookups.models import LookupGroup, LookupItem
from telegram_bot.services.ad_data import (
    build_condition_keyboard,
    build_feature_keyboard,
    build_purpose_keyboard,
    get_feature_names,
)

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
    pytest.mark.concurrent,
]
pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _button_texts(markup: object) -> list[str]:
    """Extract every button ``text`` value from an ``InlineKeyboardMarkup``."""
    texts: list[str] = []
    for row in getattr(markup, "inline_keyboard", []) or []:
        for button in row:
            texts.append(str(button.text))
    return texts


# ---------------------------------------------------------------------------
# Fixtures — real LookupItem instances with populated name_i18n
# ---------------------------------------------------------------------------


@pytest.fixture
def lookup_group() -> LookupGroup:
    """A generic LookupGroup for test items."""
    return LookupGroup.objects.create(code="listing_purpose", is_system=True)


@pytest.fixture
def purpose_items(lookup_group: LookupGroup) -> list[LookupItem]:
    """Two purpose LookupItems with full i18n name mapping."""
    return [
        LookupItem.objects.create(
            group=lookup_group,
            slug="sell",
            name_i18n={"ru": "Продам", "bs": "Prodam", "en": "Sell"},
            is_active=True,
        ),
        LookupItem.objects.create(
            group=lookup_group,
            slug="rent",
            name_i18n={"ru": "Сдам", "bs": "Iznajmljivanje", "en": "Rent"},
            is_active=True,
        ),
    ]


@pytest.fixture
def condition_items(lookup_group: LookupGroup) -> list[LookupItem]:
    """Two condition LookupItems with full i18n name mapping."""
    return [
        LookupItem.objects.create(
            group=lookup_group,
            slug="new",
            name_i18n={"ru": "Новый", "bs": "Nov", "en": "New"},
            is_active=True,
        ),
        LookupItem.objects.create(
            group=lookup_group,
            slug="used",
            name_i18n={"ru": "Б/У", "bs": "Koriseno", "en": "Used"},
            is_active=True,
        ),
    ]


@pytest.fixture
def feature_items(lookup_group: LookupGroup) -> list[LookupItem]:
    """Two feature LookupItems with full i18n name mapping (no new/used)."""
    return [
        LookupItem.objects.create(
            group=lookup_group,
            slug="delivery",
            name_i18n={"ru": "Доставка", "bs": "Dostava", "en": "Delivery"},
            is_active=True,
        ),
        LookupItem.objects.create(
            group=lookup_group,
            slug="negotiable",
            name_i18n={"ru": "Торг уместен", "bs": "Pregovor", "en": "Negotiable"},
            is_active=True,
        ),
    ]


# ---------------------------------------------------------------------------
# build_purpose_keyboard
# ---------------------------------------------------------------------------


class TestBuildPurposeKeyboardLocale:
    """``build_purpose_keyboard`` must honour the ``locale`` parameter."""

    def test_bs_locale_returns_bosnian_labels(
        self, purpose_items: list[LookupItem]
    ) -> None:
        """Bosnian locale renders Bosnian button labels."""
        with translation.override("bs"):
            markup = build_purpose_keyboard(purpose_items, locale="bs")

        texts = _button_texts(markup)
        assert "Prodam" in texts
        assert "Iznajmljivanje" in texts

    def test_en_locale_returns_english_labels(
        self, purpose_items: list[LookupItem]
    ) -> None:
        """English locale renders English button labels."""
        with translation.override("en"):
            markup = build_purpose_keyboard(purpose_items, locale="en")

        texts = _button_texts(markup)
        assert "Sell" in texts
        assert "Rent" in texts

    def test_ru_locale_returns_russian_labels(
        self, purpose_items: list[LookupItem]
    ) -> None:
        """Russian locale renders Russian button labels (default fallback)."""
        with translation.override("ru"):
            markup = build_purpose_keyboard(purpose_items, locale="ru")

        texts = _button_texts(markup)
        assert "Продам" in texts
        assert "Сдам" in texts


# ---------------------------------------------------------------------------
# build_condition_keyboard
# ---------------------------------------------------------------------------


class TestBuildConditionKeyboardLocale:
    """``build_condition_keyboard`` must honour the ``locale`` parameter."""

    def test_bs_locale_returns_bosnian_labels(
        self, condition_items: list[LookupItem]
    ) -> None:
        """Bosnian locale renders Bosnian condition labels."""
        with translation.override("bs"):
            markup = build_condition_keyboard(condition_items, locale="bs")

        texts = _button_texts(markup)
        assert "Nov" in texts

    def test_en_locale_returns_english_labels(
        self, condition_items: list[LookupItem]
    ) -> None:
        """English locale renders English condition labels."""
        with translation.override("en"):
            markup = build_condition_keyboard(condition_items, locale="en")

        texts = _button_texts(markup)
        assert "New" in texts
        assert "Used" in texts


# ---------------------------------------------------------------------------
# build_feature_keyboard
# ---------------------------------------------------------------------------


class TestBuildFeatureKeyboardLocale:
    """``build_feature_keyboard`` must honour the ``locale`` parameter."""

    def test_bs_locale_returns_bosnian_labels(
        self, feature_items: list[LookupItem]
    ) -> None:
        """Bosnian locale renders Bosnian feature labels."""
        with translation.override("bs"):
            markup = build_feature_keyboard(feature_items, set(), locale="bs")

        texts = _button_texts(markup)
        assert "Dostava" in texts
        assert "Pregovor" in texts

    def test_en_locale_returns_english_labels(
        self, feature_items: list[LookupItem]
    ) -> None:
        """English locale renders English feature labels."""
        with translation.override("en"):
            markup = build_feature_keyboard(feature_items, set(), locale="en")

        texts = _button_texts(markup)
        assert "Delivery" in texts
        assert "Negotiable" in texts


# ---------------------------------------------------------------------------
# get_feature_names
# ---------------------------------------------------------------------------


class TestGetFeatureNamesLocale:
    """``get_feature_names`` must return localized names per ``locale`` param."""

    @pytest.mark.asyncio
    async def test_bs_locale_returns_bosnian_names(
        self, feature_items: list[LookupItem]
    ) -> None:
        """``get_feature_names(locale='bs')`` returns Bosnian names."""
        with translation.override("bs"):
            names = await get_feature_names(
                [f.id for f in feature_items], locale="bs"
            )

        assert set(names) == {"Dostava", "Pregovor"}

    @pytest.mark.asyncio
    async def test_en_locale_returns_english_names(
        self, feature_items: list[LookupItem]
    ) -> None:
        """``get_feature_names(locale='en')`` returns English names."""
        with translation.override("en"):
            names = await get_feature_names(
                [f.id for f in feature_items], locale="en"
            )

        assert set(names) == {"Delivery", "Negotiable"}

    @pytest.mark.asyncio
    async def test_ru_locale_returns_russian_names(
        self, feature_items: list[LookupItem]
    ) -> None:
        """``get_feature_names(locale='ru')`` returns Russian names."""
        with translation.override("ru"):
            names = await get_feature_names(
                [f.id for f in feature_items], locale="ru"
            )

        assert set(names) == {"Доставка", "Торг уместен"}

    @pytest.mark.asyncio
    async def test_fallback_to_slug_when_name_i18n_is_null(
        self, lookup_group: LookupGroup
    ) -> None:
        """When ``name_i18n`` is NULL, ``get_name`` falls back to the slug."""
        item = await sync_to_async(LookupItem.objects.create)(
            group=lookup_group,
            slug="no-i18n-item",
            name_i18n=None,
            is_active=True,
        )
        names = await get_feature_names([item.id], locale="bs")
        assert names == ["no-i18n-item"]
