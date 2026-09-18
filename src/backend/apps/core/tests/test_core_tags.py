"""
Tests for core template tag filters.

Covers:
- ``can_contact`` filter (contact_tags) — delegates to can_contact_seller().
- ``get_title`` / ``get_description`` filters (localized_content) — delegate to
  Ad.get_title(locale) / Ad.get_description(locale).
- ``get_item`` filter (dict_tags) — dict-style key lookup with None-safety.

Tests exercise both direct function calls and template-engine rendering
(via ``{% load … %}`` + ``{{ …|filter }}``), mirroring the patterns established
in ``test_rtl_obfuscation.py`` and ``test_templates.py``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.template import Context, Template

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from apps.core.templatetags.contact_tags import can_contact
from apps.core.templatetags.dict_tags import get_item
from apps.core.templatetags.localized_content import get_description, get_title

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ad(**kwargs: object) -> Ad:
    """Create an in-memory Ad (no DB) for localized-getter tests.

    Mirrors the helper in ``test_ad_localization.py``: builds a real ``Ad``
    instance via ``__new__`` so the actual ``get_title`` / ``get_description``
    methods are available without a database row.
    """
    fields: dict[str, str | None] = {
        "title": "",
        "description": "",
        "title_bs": None,
        "description_bs": None,
        "title_en": None,
        "description_en": None,
    }
    fields.update(kwargs)
    ad = Ad.__new__(Ad)
    for field, value in fields.items():
        setattr(ad, field, value)
    return ad  # type: ignore[return-value]


def _make_contactable_ad() -> SimpleNamespace:
    """Build an ad-like object whose seller passes all R2 contact conditions."""
    seller = SimpleNamespace(
        telegram_id=123456789,
        is_deleted=False,
        is_banned=False,
        consent_revoked_at=None,
    )
    return SimpleNamespace(status=AdStatus.PUBLISHED, user=seller)


# ---------------------------------------------------------------------------
# can_contact filter (unit — SimpleNamespace, no DB)
# ---------------------------------------------------------------------------


class TestCanContactFilter:
    """The ``can_contact`` filter delegates to ``can_contact_seller``."""

    def test_can_contact_true_when_contactable(self) -> None:
        """Published ad + contactable seller -> filter returns True."""
        ad = _make_contactable_ad()
        assert can_contact(ad) is True

    def test_can_contact_false_when_not_published(self) -> None:
        """Non-PUBLISHED status -> filter returns False."""
        ad = SimpleNamespace(
            status=AdStatus.DRAFT,
            user=SimpleNamespace(
                telegram_id=1,
                is_deleted=False,
                is_banned=False,
                consent_revoked_at=None,
            ),
        )
        assert can_contact(ad) is False

    def test_can_contact_false_when_seller_is_none(self) -> None:
        """Seller is None -> filter returns False (defensive check)."""
        ad = SimpleNamespace(status=AdStatus.PUBLISHED, user=None)
        assert can_contact(ad) is False

    def test_can_contact_false_when_seller_banned(self) -> None:
        """Banned seller -> filter returns False."""
        ad = SimpleNamespace(
            status=AdStatus.PUBLISHED,
            user=SimpleNamespace(
                telegram_id=1,
                is_deleted=False,
                is_banned=True,
                consent_revoked_at=None,
            ),
        )
        assert can_contact(ad) is False

    def test_can_contact_via_template_engine(self) -> None:
        """The filter is callable from templates via ``{% load contact_tags %}``."""
        ad = _make_contactable_ad()
        template = Template(
            "{% load contact_tags %}"
            "{% if ad|can_contact %}contactable{% else %}blocked{% endif %}"
        )
        result = template.render(Context({"ad": ad}))
        assert result == "contactable"

    def test_can_contact_false_via_template_engine(self) -> None:
        """Non-contactable ad renders 'blocked' through the template engine."""
        ad = SimpleNamespace(
            status=AdStatus.DRAFT,
            user=SimpleNamespace(
                telegram_id=1,
                is_deleted=False,
                is_banned=False,
                consent_revoked_at=None,
            ),
        )
        template = Template(
            "{% load contact_tags %}"
            "{% if ad|can_contact %}contactable{% else %}blocked{% endif %}"
        )
        result = template.render(Context({"ad": ad}))
        assert result == "blocked"


# ---------------------------------------------------------------------------
# can_contact filter (integration — real Ad fixture, DB)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.integration
class TestCanContactFilterDB:
    """Integration tests for ``can_contact`` with persisted Ad + User."""

    def test_can_contact_true_with_published_ad(
        self, seller, category, city
    ) -> None:
        """A published ad with a contactable seller passes the filter."""
        from conftest import create_test_ad

        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        assert can_contact(ad) is True

    def test_can_contact_false_with_draft_ad(
        self, seller, category, city
    ) -> None:
        """A DRAFT ad fails the filter."""
        from conftest import create_test_ad

        ad = create_test_ad(seller, category, city, status=AdStatus.DRAFT)
        assert can_contact(ad) is False

    def test_can_contact_false_when_seller_deleted(
        self, seller, category, city
    ) -> None:
        """A deleted seller fails the filter."""

        from conftest import create_test_ad

        seller.is_deleted = True
        seller.save(update_fields=["is_deleted"])

        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        assert can_contact(ad) is False


# ---------------------------------------------------------------------------
# get_title filter (unit — in-memory Ad, no DB)
# ---------------------------------------------------------------------------


class TestGetTitleFilter:
    """The ``get_title`` filter delegates to Ad.get_title(locale)."""

    def test_get_title_returns_default_locale(self) -> None:
        """Default locale (ru) returns the Russian base field ``title``."""
        ad = _make_ad(title="Russian title")
        assert get_title(ad) == "Russian title"

    def test_get_title_returns_english_when_present(self) -> None:
        """Locale 'en' returns ``title_en`` when it is non-empty."""
        ad = _make_ad(title="Russian title", title_en="English title")
        assert get_title(ad, "en") == "English title"

    def test_get_title_falls_back_to_base(self) -> None:
        """Missing locale field falls back to the Russian base ``title``."""
        ad = _make_ad(title="Russian fallback", title_en=None)
        assert get_title(ad, "en") == "Russian fallback"

    def test_get_title_unknown_locale_falls_back(self) -> None:
        """Unknown locale falls back to the Russian base when locale field is None."""
        ad = _make_ad(title="Russian")
        assert get_title(ad, "fr") == "Russian"

    def test_get_title_via_template_engine(self) -> None:
        """The filter works in templates: ``{{ ad|get_title:"en" }}``."""
        ad = _make_ad(title="Russian", title_en="English")
        template = Template(
            "{% load localized_content %}{{ ad|get_title:'en' }}"
        )
        result = template.render(Context({"ad": ad}))
        assert result == "English"


# ---------------------------------------------------------------------------
# get_description filter (unit — in-memory Ad, no DB)
# ---------------------------------------------------------------------------


class TestGetDescriptionFilter:
    """The ``get_description`` filter delegates to Ad.get_description(locale)."""

    def test_get_description_returns_default_locale(self) -> None:
        """Default locale (ru) returns the Russian base field ``description``."""
        ad = _make_ad(description="Russian desc")
        assert get_description(ad) == "Russian desc"

    def test_get_description_returns_english_when_present(self) -> None:
        """Locale 'en' returns ``description_en`` when it is non-empty."""
        ad = _make_ad(description="Russian desc", description_en="English desc")
        assert get_description(ad, "en") == "English desc"

    def test_get_description_falls_back_to_base(self) -> None:
        """Missing locale field falls back to the Russian base ``description``."""
        ad = _make_ad(description="Russian fallback", description_en=None)
        assert get_description(ad, "en") == "Russian fallback"

    def test_get_description_unknown_locale_falls_back(self) -> None:
        """Unknown locale falls back to the Russian base when locale field is None."""
        ad = _make_ad(description="Russian")
        assert get_description(ad, "fr") == "Russian"

    def test_get_description_via_template_engine(self) -> None:
        """The filter works in templates: ``{{ ad|get_description:'bs' }}``."""
        ad = _make_ad(description="Russian", description_bs="Bosnian desc")
        template = Template(
            "{% load localized_content %}{{ ad|get_description:'bs' }}"
        )
        result = template.render(Context({"ad": ad}))
        assert result == "Bosnian desc"


# ---------------------------------------------------------------------------
# get_item filter (unit — plain dict, no DB)
# ---------------------------------------------------------------------------


class TestGetItemFilter:
    """The ``get_item`` filter performs a dict-style ``get`` lookup."""

    def test_get_item_returns_value_for_existing_key(self) -> None:
        """An existing key returns its value."""
        obj = {"name": "widget", "price": 100}
        assert get_item(obj, "name") == "widget"

    def test_get_item_returns_none_for_missing_key(self) -> None:
        """A missing key returns None (dict.get semantics)."""
        obj = {"name": "widget"}
        assert get_item(obj, "price") is None

    def test_get_item_returns_none_for_none_dict(self) -> None:
        """A None dictionary returns None."""
        assert get_item(None, "anything") is None

    def test_get_item_via_template_engine(self) -> None:
        """The filter works in templates: ``{{ obj|get_item:key }}``."""
        template = Template(
            "{% load dict_tags %}{{ obj|get_item:'name' }}"
        )
        result = template.render(Context({"obj": {"name": "widget"}}))
        assert result == "widget"

    def test_get_item_missing_key_via_template_engine(self) -> None:
        """A missing key renders 'None' through the template engine (Django default)."""
        template = Template(
            "{% load dict_tags %}<{{ obj|get_item:'missing' }}>"
        )
        result = template.render(Context({"obj": {"name": "widget"}}))
        assert result == "<None>"
