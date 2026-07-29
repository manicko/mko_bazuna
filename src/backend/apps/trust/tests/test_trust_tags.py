"""
Tests for render_trust_badge template tag.

Tests that the correct badge is rendered for each trust level,
and that no badge is rendered for anonymous users, users without
trust scores, or UNVERIFIED sellers.
"""

from __future__ import annotations

from django.template import Context, Template
from django.test import TestCase

from apps.core.enums import TrustLevel
from apps.trust.models import SellerTrustScore, SellerVerification
from apps.users.models import User


class TestRenderTrustBadge(TestCase):
    """Tests for the render_trust_badge template tag."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = User.objects.create(
            telegram_id=990100001,
            chat_id=990100001,
            password="x",
        )
        cls.verified_user = User.objects.create(
            telegram_id=990100002,
            chat_id=990100002,
            password="x",
        )
        SellerVerification.objects.create(
            user=cls.verified_user,
            verified_by_admin=True,
        )
        cls.trusted_user = User.objects.create(
            telegram_id=990100003,
            chat_id=990100003,
            password="x",
        )
        cls.pro_user = User.objects.create(
            telegram_id=990100004,
            chat_id=990100004,
            password="x",
        )

        # Create trust scores at each level
        # UNVERIFIED: score < 31, no verification
        SellerTrustScore.objects.create(
            user=cls.user,
            trust_level=TrustLevel.UNVERIFIED,
            score=15,
        )
        # VERIFIED: score >= 31
        SellerTrustScore.objects.create(
            user=cls.verified_user,
            trust_level=TrustLevel.VERIFIED,
            score=35,
        )
        # TRUSTED: score >= 61
        SellerTrustScore.objects.create(
            user=cls.trusted_user,
            trust_level=TrustLevel.TRUSTED,
            score=65,
        )
        # PRO: score >= 86
        SellerTrustScore.objects.create(
            user=cls.pro_user,
            trust_level=TrustLevel.PRO,
            score=90,
        )

    def _render(self, user: User) -> str:
        """Render the template tag for the given user and return the HTML."""
        template = Template(
            "{% load trust_tags %}{% render_trust_badge user %}"
        )
        context = Context({"user": user, "request": None})
        return template.render(context)

    def test_no_badge_for_anonymous_user(self) -> None:
        """Anonymous user renders no badge."""
        html = self._render(User(telegram_id=0, chat_id=0, password="x"))
        self.assertEqual(html, "")

    def test_no_badge_for_user_without_trust_score(self) -> None:
        """User without SellerTrustScore renders no badge."""
        no_score_user = User.objects.create(
            telegram_id=990100005,
            chat_id=990100005,
            password="x",
        )
        html = self._render(no_score_user)
        self.assertEqual(html, "")

    def test_no_badge_for_unverified_level(self) -> None:
        """UNVERIFIED trust level renders no badge."""
        html = self._render(self.user)
        self.assertEqual(html, "")

    def test_verified_badge_rendered(self) -> None:
        """VERIFIED trust level renders the verified badge."""
        html = self._render(self.verified_user)
        self.assertIn("Verified", html)
        self.assertNotIn("Trusted", html)
        self.assertNotIn("Pro", html)

    def test_trusted_badge_rendered(self) -> None:
        """TRUSTED trust level renders the trusted badge."""
        html = self._render(self.trusted_user)
        self.assertIn("Trusted", html)
        self.assertNotIn("Verified", html)
        self.assertNotIn("Pro", html)

    def test_pro_badge_rendered(self) -> None:
        """PRO trust level renders the pro badge."""
        html = self._render(self.pro_user)
        self.assertIn("Pro", html)
        self.assertNotIn("Verified", html)
        self.assertNotIn("Trusted", html)