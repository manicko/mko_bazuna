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
