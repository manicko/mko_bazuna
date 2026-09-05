"""
Tests for consent banner guard across all templates (PII-009).

Verifies that every template which includes ``components/consent_banner.html``
wraps the include inside the guard:

    {% if not request.user.is_authenticated or not request.user.is_deleted %}
    {% include "components/consent_banner.html" %}
    {% endif %}

No database interaction is required — this is a static template-guard
verification.
"""

from __future__ import annotations

import html
from pathlib import Path
from unittest.mock import Mock

import pytest
from django.conf import settings
from django.http import QueryDict
from django.template import Context, Template

pytestmark = [pytest.mark.unit]

# Templates that include the consent banner component.
_TEMPLATES_WITH_BANNER: list[str] = [
    "ads/dashboard.html",
    "ads/detail.html",
    "ads/list.html",
    "analytics/seller_dashboard.html",
    "analytics/moderation_dashboard.html",
    "cabinet/hub.html",
    "cabinet/settings.html",
]

_GUARD_OPEN = (
    "{% if not request.user.is_authenticated or not request.user.is_deleted %}"
)
_GUARD_CLOSE = "{% endif %}"
_BANNER_INCLUDE = '{% include "components/consent_banner.html" %}'


def test_consent_banner_guard_in_all_templates() -> None:
    """All seven templates guard the consent banner for deleted users."""
    templates_dir = Path(settings.TEMPLATES[0]["DIRS"][0])

    for rel_path in _TEMPLATES_WITH_BANNER:
        template_path = templates_dir / rel_path
        lines = template_path.read_text(encoding="utf-8").splitlines()

        # Locate the include line.
        include_indices = [i for i, line in enumerate(lines) if _BANNER_INCLUDE in line]
        assert len(include_indices) == 1, (
            f"{rel_path} should have exactly one consent banner include"
        )
        include_idx = include_indices[0]

        # Guard opening tag must be on the line immediately before.
        assert _GUARD_OPEN in lines[include_idx - 1], (
            f"{rel_path}: guard not found before the include"
        )

        # Guard closing tag must be on the line immediately after.
        assert _GUARD_CLOSE in lines[include_idx + 1], (
            f"{rel_path}: endif not found after the include"
        )


# ---------------------------------------------------------------------------
# query_replace template tag
# ---------------------------------------------------------------------------


def _render_query_replace(get_params: str, **overrides: str) -> str:
    """Render a template fragment using ``query_replace`` and return the output.

    Args:
        get_params: The raw query string (e.g. ``"q=phone&page=2"``) to simulate
            ``request.GET``.
        **overrides: Keyword arguments passed to ``query_replace`` as
            ``key=value`` pairs.

    Returns:
        The rendered query string from the ``query_replace`` tag (HTML-unescaped).
    """
    request = Mock()
    request.GET = QueryDict(get_params)
    # Build template with quoted string literals so Django resolves them as
    # strings rather than context variables.
    template = Template(
        "{% load dict_tags %}"
        "{% query_replace request"
        + "".join(f' {k}="{v}"' for k, v in overrides.items())
        + " %}"
    )
    raw = template.render(Context({"request": request}))
    # Django autoescapes the ``&`` in urlencoded output to ``&amp;``.
    return html.unescape(raw)


class TestQueryReplace:
    """Tests for the ``query_replace`` template tag (Block 9 V4)."""

    def test_preserves_existing_params_when_overriding_one(self) -> None:
        """Overriding one param preserves all other existing params."""
        result = _render_query_replace("q=phone&lang=ru", lang="en")
        assert "q=phone" in result
        assert "lang=en" in result
        assert "lang=ru" not in result

    def test_adds_new_param_when_none_exists(self) -> None:
        """Adding a param to an empty query string works."""
        result = _render_query_replace("", lang="en")
        assert result == "lang=en"

    def test_preserves_multiple_params(self) -> None:
        """Multiple existing params are all preserved when overriding one."""
        result = _render_query_replace("q=phone&page=2&sort=price", lang="bs")
        assert "q=phone" in result
        assert "page=2" in result
        assert "sort=price" in result
        assert "lang=bs" in result

    def test_empty_overrides_preserves_all(self) -> None:
        """With no overrides, the full query string is returned."""
        result = _render_query_replace("q=phone&page=2")
        assert "q=phone" in result
        assert "page=2" in result

    def test_preserves_multi_value_params(self) -> None:
        """Multi-value params (e.g. ``features=delivery&features=negotiable``)
        are all preserved when overriding a *different* parameter.

        ``QueryDict.copy()`` + ``__setitem__`` only replaces the target key;
        the remaining multi-valued keys survive through ``urlencode()``.
        """
        result = _render_query_replace(
            "features=delivery&features=negotiable&q=test", page="2"
        )
        assert "features=delivery" in result
        assert "features=negotiable" in result
        assert "q=test" in result
        assert "page=2" in result

    def test_none_values_are_skipped(self) -> None:
        """When a kwarg value is ``None``, that key is removed from the query
        string (not rendered as ``key=None``), and existing params survive.

        Mirrors the ``{% query_replace request page=1 city=current_city %}``
        pattern used in header/breadcrumb/did-you-mean category links, where
        ``current_city`` may be ``None`` when no city filter is active.
        """
        request = Mock()
        request.GET = QueryDict("q=phone&lang=ru")
        template = Template(
            "{% load dict_tags %}{% query_replace request page=1 city=city_var %}"
        )
        context = Context({"request": request, "city_var": None})
        result = html.unescape(template.render(context))
        assert "city" not in result
        assert "q=phone" in result
        assert "lang=ru" in result
        assert "page=1" in result

    def test_none_value_removes_existing_param(self) -> None:
        """A ``None`` override removes an existing key from ``request.GET``."""
        request = Mock()
        request.GET = QueryDict("q=phone&lang=ru&page=3")
        template = Template(
            "{% load dict_tags %}{% query_replace request page=page_var %}"
        )
        context = Context({"request": request, "page_var": None})
        result = html.unescape(template.render(context))
        assert "page" not in result
        assert "q=phone" in result
        assert "lang=ru" in result

    def test_query_replace_none_value_removes_param(self) -> None:
        """Passing ``city=None`` removes the ``city`` key from the query string.

        Verifies that ``None`` is treated as a deletion sentinel — the key does
        not appear in the output at all (not even as ``city=None``), mirroring
        the ``{% query_replace request city=request.current_city %}`` pattern
        used in header/breadcrumb/did-you-mean links where ``current_city`` is
        ``None`` when no city filter is active.
        """
        request = Mock()
        request.GET = QueryDict("q=phone&city=old_city&lang=ru")
        template = Template("{% load dict_tags %}{% query_replace request city=None %}")
        result = html.unescape(template.render(Context({"request": request})))
        assert "city" not in result
        assert "q=phone" in result
        assert "lang=ru" in result

    def test_query_replace_sets_value(self) -> None:
        """Passing ``city='spb'`` sets ``city=spb`` in the output query string."""
        result = _render_query_replace("", city="spb")
        assert "city=spb" in result

    def test_query_replace_preserves_existing_params(self) -> None:
        """Existing ``min_price=100`` is preserved when overriding ``lang='en'``.

        Simulates a buyer on ``/?min_price=100`` clicking a category link:
        the ``query_replace`` tag must carry forward the active price filter
        while also injecting the current language.
        """
        result = _render_query_replace("min_price=100&q=phone", lang="en")
        assert "min_price=100" in result
        assert "lang=en" in result
        assert "q=phone" in result
