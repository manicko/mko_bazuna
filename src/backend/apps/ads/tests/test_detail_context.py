"""
Verification test for tsk_007 — contact button ``bot_username`` context.

Confirms that ``ad_detail`` passes ``bot_username`` into the template context
(from ``settings.BOT_USERNAME``) so the Telegram deep-link renders correctly,
rather than relying on ``{{ settings.BOT_USERNAME }}`` which is NOT available
because ``settings`` is not in Django's context processors.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from apps.ads.views.listings import ad_detail


class TestAdDetailBotUsernameContext(SimpleTestCase):
    """Verify ``ad_detail`` passes ``bot_username`` to the template context."""

    def _run_detail(self, ad: MagicMock) -> dict[str, Any]:
        """Invoke ``ad_detail`` with DB/managers mocked to capture context.

        ``Ad.objects.select_related(...).prefetch_related(...).get(...)`` is
        mocked to return a MagicMock ad. ``AnalyticsEvent.objects.create`` and
        ``is_consent_given`` are patched to avoid DB/consent-table hits.
        ``render`` is stubbed to capture the 3rd positional ``context`` arg.
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
            patch("apps.ads.views.listings.is_consent_given", return_value=False),
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

    def test_detail_context_contains_bot_username(self) -> None:
        """``ad_detail`` must pass ``bot_username`` matching ``settings.BOT_USERNAME``."""
        ad = MagicMock()
        context = self._run_detail(ad)
        self.assertIn(
            "bot_username",
            context,
            msg="bot_username must be passed in the context dict",
        )
        self.assertEqual(context["bot_username"], settings.BOT_USERNAME)

    def test_detail_context_contains_ad(self) -> None:
        """Sanity check: the ad object is still in context."""
        ad = MagicMock()
        context = self._run_detail(ad)
        self.assertEqual(context["ad"], ad)

    def test_detail_template_uses_bot_username_not_settings(self) -> None:
        """The rendered template variable name is ``bot_username``, not
        ``settings.BOT_USERNAME``."""
        from pathlib import Path

        content = (
            Path("src/backend/templates/ads/detail.html")
            .resolve()
            .read_text(encoding="utf-8")
        )
        self.assertIn("{{ bot_username }}", content)
        self.assertNotIn("settings.BOT_USERNAME", content)
