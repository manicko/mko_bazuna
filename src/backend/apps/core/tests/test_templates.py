"""
Tests for consent banner guard across all templates (PII-009).

Verifies that every template which includes ``components/consent_banner.html``
wraps the include inside the guard:

    {% if not request.user.is_authenticated or not request.user.is_deleted %}
    {% include "components/consent_banner.html" %}
    {% endif %}

No database interaction is required — this is a static template-guard
verification using Django's ``SimpleTestCase``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings
from django.test import SimpleTestCase

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
_BANNER_INCLUDE = "{% include \"components/consent_banner.html\" %}"


class TestConsentBannerGuardInTemplates(SimpleTestCase):
    """Every consent banner include is wrapped in the deleted-user guard."""

    def test_consent_banner_guard_in_all_templates(self) -> None:
        """All seven templates guard the consent banner for deleted users."""
        templates_dir = Path(settings.TEMPLATES[0]["DIRS"][0])

        for rel_path in _TEMPLATES_WITH_BANNER:
            with self.subTest(template=rel_path):
                template_path = templates_dir / rel_path
                lines = template_path.read_text(encoding="utf-8").splitlines()

                # Locate the include line.
                include_indices = [
                    i for i, line in enumerate(lines) if _BANNER_INCLUDE in line
                ]
                self.assertEqual(
                    len(include_indices),
                    1,
                    f"{rel_path} should have exactly one consent banner include",
                )
                include_idx = include_indices[0]

                # Guard opening tag must be on the line immediately before.
                self.assertIn(
                    _GUARD_OPEN,
                    lines[include_idx - 1],
                    f"{rel_path}: guard not found before the include",
                )

                # Guard closing tag must be on the line immediately after.
                self.assertIn(
                    _GUARD_CLOSE,
                    lines[include_idx + 1],
                    f"{rel_path}: endif not found after the include",
                )
