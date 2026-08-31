"""
Tests for render_trust_badge template tag.

Tests that the correct badge is rendered for each trust level,
and that no badge is rendered for anonymous users, users without
trust scores, or UNVERIFIED sellers.
"""

from __future__ import annotations

import pytest
from django.template import Context, Template

from apps.core.enums import TrustLevel
from apps.trust.models import SellerTrustScore, SellerVerification
from apps.users.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _make_user(telegram_id: int, **overrides: object) -> User:
    """Create a User with sensible defaults."""
    defaults: dict = {
        "telegram_id": telegram_id,
        "chat_id": telegram_id,
        "password": "x",
    }
    defaults.update(overrides)
    return User.objects.create(**defaults)


def _render(user) -> str:
    """Render the template tag for the given user and return the HTML."""
    template = Template("{% load trust_tags %}{% render_trust_badge user %}")
    context = Context({"user": user, "request": None})
    return template.render(context)


@pytest.fixture
def trust_users():
    """Create users at each trust level for badge rendering tests."""
    user = _make_user(990100001)
    SellerTrustScore.objects.create(
        user=user,
        trust_level=TrustLevel.UNVERIFIED,
        score=15,
    )

    verified_user = _make_user(990100002)
    SellerVerification.objects.create(user=verified_user, verified_by_admin=True)
    SellerTrustScore.objects.create(
        user=verified_user,
        trust_level=TrustLevel.VERIFIED,
        score=35,
    )

    trusted_user = _make_user(990100003)
    SellerTrustScore.objects.create(
        user=trusted_user,
        trust_level=TrustLevel.TRUSTED,
        score=65,
    )

    pro_user = _make_user(990100004)
    SellerTrustScore.objects.create(
        user=pro_user,
        trust_level=TrustLevel.PRO,
        score=90,
    )

    return {
        "user": user,
        "verified_user": verified_user,
        "trusted_user": trusted_user,
        "pro_user": pro_user,
    }


class TestRenderTrustBadge:
    """Tests for the render_trust_badge template tag."""

    def test_no_badge_for_anonymous_user(self) -> None:
        """Anonymous user renders no badge."""
        html = _render(User(telegram_id=0, chat_id=0, password="x"))
        assert html == ""

    def test_no_badge_for_user_without_trust_score(self) -> None:
        """User without SellerTrustScore renders no badge."""
        no_score_user = User.objects.create(
            telegram_id=990100005,
            chat_id=990100005,
            password="x",
        )
        html = _render(no_score_user)
        assert html == ""

    def test_no_badge_for_unverified_level(self, trust_users) -> None:
        """UNVERIFIED trust level renders no badge."""
        html = _render(trust_users["user"])
        assert html == ""

    def test_verified_badge_rendered(self, trust_users) -> None:
        """VERIFIED trust level renders the verified badge."""
        html = _render(trust_users["verified_user"])
        assert "Verified" in html
        assert "Trusted" not in html
        assert "Pro" not in html

    def test_trusted_badge_rendered(self, trust_users) -> None:
        """TRUSTED trust level renders the trusted badge."""
        html = _render(trust_users["trusted_user"])
        assert "Trusted" in html
        assert "Verified" not in html
        assert "Pro" not in html

    def test_pro_badge_rendered(self, trust_users) -> None:
        """PRO trust level renders the pro badge."""
        html = _render(trust_users["pro_user"])
        assert "Pro" in html
        assert "Verified" not in html
        assert "Trusted" not in html
