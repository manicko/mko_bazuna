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

from apps.currencies.enums import CurrencyCode
from apps.lookups.models import LookupGroup, LookupItem
from telegram_bot.schemas.callbacks import BotCallbackPrefix
from telegram_bot.services.ad_data import (
    build_condition_keyboard,
    build_currency_keyboard,
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


# ---------------------------------------------------------------------------
# build_currency_keyboard
# ---------------------------------------------------------------------------


class TestBuildCurrencyKeyboard:
    """``build_currency_keyboard`` must emit CurrencyCode-derived tokens (10-QLT-003).

    The callback-data currency suffixes must be derived from the
    ``CurrencyCode`` StrEnum (single source of truth shared with the
    ``price.py`` parser) rather than bare ``"EUR"``/``"RSD"``/``"BAM"``
    literals. EUR must remain first (PO-01).
    """

    @staticmethod
    def _button_pairs(markup: object) -> list[tuple[str | None, str | None]]:
        """Extract ``(text, callback_data)`` pairs from an ``InlineKeyboardMarkup``."""
        pairs: list[tuple[str | None, str | None]] = []
        for row in getattr(markup, "inline_keyboard", []) or []:
            for button in row:
                pairs.append(
                    (
                        getattr(button, "text", None),
                        getattr(button, "callback_data", None),
                    )
                )
        return pairs

    def test_currency_suffixes_match_currency_code_values(self) -> None:
        """Every emitted currency callback suffix is a ``CurrencyCode`` value.

        Property test: the set of suffixes after the ``PRICE_CURRENCY`` prefix
        must exactly equal ``{c.value for c in CurrencyCode}`` — no bare
        literals, no extra or missing tokens.
        """
        markup = build_currency_keyboard()
        pairs = self._button_pairs(markup)

        suffixes = {
            cb.removeprefix(str(BotCallbackPrefix.PRICE_CURRENCY))
            for _text, cb in pairs
            if cb is not None and str(cb).startswith(str(BotCallbackPrefix.PRICE_CURRENCY))
        }

        assert suffixes == {c.value for c in CurrencyCode}

    def test_round_trip_currency_tokens_parse(self) -> None:
        """Each emitted currency token must be accepted by ``CurrencyCode(...)``.

        Mirrors the ``price.py`` parser path: strip the prefix, then
        ``CurrencyCode(currency_value)`` must succeed for every keyboard token.
        """
        markup = build_currency_keyboard()
        pairs = self._button_pairs(markup)

        for _text, cb in pairs:
            if cb is not None and str(cb).startswith(str(BotCallbackPrefix.PRICE_CURRENCY)):
                currency_value = cb.replace(BotCallbackPrefix.PRICE_CURRENCY, "")
                assert isinstance(CurrencyCode(currency_value), CurrencyCode)

    def test_eur_is_first_currency_button(self) -> None:
        """EUR must be the first currency button (PO-01 ordering)."""
        markup = build_currency_keyboard()
        pairs = self._button_pairs(markup)

        currency_buttons = [
            (text, cb)
            for text, cb in pairs
            if cb is not None and str(cb).startswith(str(BotCallbackPrefix.PRICE_CURRENCY))
        ]

        assert currency_buttons, "expected at least one currency button"

        text, cb = currency_buttons[0]
        assert cb == f"{BotCallbackPrefix.PRICE_CURRENCY}{CurrencyCode.EUR.value}"
        assert "EUR" in (text or "")

    def test_free_button_preserved(self) -> None:
        """The 'Free' button sentinel and ``adjust(2)`` must remain unchanged."""
        markup = build_currency_keyboard()
        pairs = self._button_pairs(markup)

        callback_values = [cb for _text, cb in pairs if cb is not None]
        assert BotCallbackPrefix.PRICE_FREE in callback_values

    def test_exactly_one_button_per_currency_code(self) -> None:
        """There must be exactly one currency button per ``CurrencyCode`` member."""
        markup = build_currency_keyboard()
        pairs = self._button_pairs(markup)

        currency_buttons = [
            cb
            for _text, cb in pairs
            if cb is not None and str(cb).startswith(str(BotCallbackPrefix.PRICE_CURRENCY))
        ]

        assert len(currency_buttons) == len(list(CurrencyCode))
