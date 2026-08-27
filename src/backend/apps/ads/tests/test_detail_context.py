"""
Verification test for tsk_007 — contact button ``bot_username`` context.

Confirms that ``ad_detail`` passes ``bot_username`` into the template context
(from ``settings.BOT_USERNAME``) so the Telegram deep-link renders correctly,
rather than relying on ``{{ settings.BOT_USERNAME }}`` which is NOT available
because ``settings`` is not in Django's context processors.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory

from apps.ads.views.listings import ad_detail

pytestmark = [pytest.mark.unit]


def _run_detail(ad: MagicMock) -> dict[str, Any]:
    """Invoke ``ad_detail`` with DB/managers mocked to capture context.

    ``Ad.objects.select_related(...).prefetch_related(...).get(...)`` is
    mocked to return a MagicMock ad. ``AnalyticsEvent.objects.create`` is
    patched to avoid DB/analytics hits. ``render`` is stubbed to capture the
    3rd positional ``context`` arg.
    """
    context_box: list[dict[str, Any]] = []

    def fake_render(
        request: Any,
        template_name: str,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> HttpResponse:
        context_box.append(context if context is not None else {})
        return HttpResponse(status=200)

    with (
        patch("apps.ads.views.listings.Ad") as mock_ad,
        patch("apps.ads.views.listings.AnalyticsEvent") as mock_ae,
        patch(
            "apps.ads.views.listings.render",
            side_effect=fake_render,
        ),
    ):
        # Chain: .select_related().prefetch_related().get()
        mock_ad.objects.select_related.return_value.prefetch_related.return_value.get.return_value = ad
        mock_ae.objects.create.return_value = None

        factory = RequestFactory()
        request = factory.get(f"/ads/{ad.id}/")
        request.user = MagicMock()
        request.user.is_anonymous = False

        ad_detail(request, ad.id)

    return context_box[0]


def test_detail_prefetch_includes_trust_score() -> None:
    """``ad_detail`` must prefetch ``user__trust_score`` to avoid N+1 on
    trust-badge rendering (Spec trust display contract)."""
    ad = MagicMock()
    context_box: list[dict[str, Any]] = []

    def fake_render(
        request: Any,
        template_name: str,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> HttpResponse:
        context_box.append(context if context is not None else {})
        return HttpResponse(status=200)

    with (
        patch("apps.ads.views.listings.Ad") as mock_ad,
        patch("apps.ads.views.listings.AnalyticsEvent") as mock_ae,
        patch(
            "apps.ads.views.listings.render",
            side_effect=fake_render,
        ),
    ):
        mock_ad.objects.select_related.return_value.prefetch_related.return_value.get.return_value = ad
        mock_ae.objects.create.return_value = None

        factory = RequestFactory()
        request = factory.get(f"/ads/{ad.id}/")
        request.user = MagicMock()
        request.user.is_anonymous = False

        ad_detail(request, ad.id)

    mock_ad.objects.select_related.assert_called_once_with("category", "city", "user")
    mock_ad.objects.select_related.return_value.prefetch_related.assert_called_once_with(
        "images", "features", "user__trust_score"
    )


def test_detail_context_contains_bot_username() -> None:
    """``ad_detail`` must pass ``bot_username`` matching ``settings.BOT_USERNAME``."""
    ad = MagicMock()
    context = _run_detail(ad)
    assert "bot_username" in context, "bot_username must be passed in the context dict"
    assert context["bot_username"] == settings.BOT_USERNAME


def test_detail_context_contains_ad() -> None:
    """Sanity check: the ad object is still in context."""
    ad = MagicMock()
    context = _run_detail(ad)
    assert context["ad"] == ad


def test_detail_context_contains_breadcrumb_category() -> None:
    """``ad_detail`` must pass ``breadcrumb_category`` (= ``ad.category``) so
    the catalog header breadcrumbs render the full category path (Spec_020
    R-04a)."""
    ad = MagicMock()
    context = _run_detail(ad)
    assert "breadcrumb_category" in context, (
        "breadcrumb_category must be passed in the context dict"
    )
    assert context["breadcrumb_category"] == ad.category


def test_detail_template_uses_bot_username_not_settings() -> None:
    """The rendered template variable name is ``bot_username``, not
    ``settings.BOT_USERNAME``."""
    content = (
        Path("src/backend/templates/ads/detail.html")
        .resolve()
        .read_text(encoding="utf-8")
    )
    assert "{{ bot_username }}" in content
    assert "settings.BOT_USERNAME" not in content


# ---------------------------------------------------------------------------
# Breadcrumb ellipsis template (Spec_020 R-05)
# ---------------------------------------------------------------------------

_BREADCRUMB_CONTENT = (
    Path("src/backend/templates/components/breadcrumb.html")
    .resolve()
    .read_text(encoding="utf-8")
)


def test_ellipsis_truncation_branch_present() -> None:
    """The template must gate truncation on the ancestor-chain length."""
    assert "{% if ancestors|length > 2 %}" in _BREADCRUMB_CONTENT
    assert "{% endwith %}" in _BREADCRUMB_CONTENT


def test_ellipsis_literal_present() -> None:
    """The ``…`` ellipsis literal is rendered for long chains."""
    assert ">…<" in _BREADCRUMB_CONTENT


def test_separator_preserved() -> None:
    """The ``&rsaquo;`` separator is kept in truncated and full chains."""
    assert "&rsaquo;" in _BREADCRUMB_CONTENT


def test_breadcrumb_with_tag_no_last_ancestor() -> None:
    """The ``{% with %}`` must not bind ``last_ancestor`` via ``|last``
    (which raises on an empty ancestor queryset); the last ancestor is bound
    safely inside the length-guarded branch (RC-C)."""
    assert "last_ancestor=breadcrumb_category" not in _BREADCRUMB_CONTENT
    assert "get_ancestors|last" not in _BREADCRUMB_CONTENT
    assert (
        "{% with ancestors=breadcrumb_category.get_ancestors %}" in _BREADCRUMB_CONTENT
    )
    assert 'slice:"::-1"|first' in _BREADCRUMB_CONTENT
