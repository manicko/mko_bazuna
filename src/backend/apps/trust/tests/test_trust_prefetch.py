"""
Verification test for tsk_006 — trust badge prefetch (N+1 elimination).

Confirms two things:
1. ``render_trust_badge`` uses the prefetched ``user.trust_score`` attribute
   (via ``getattr``) WITHOUT issuing a DB query when it is present.
2. When the prefetched attribute is absent, it falls back to
   ``SellerTrustScore.objects.get(user=user)``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from django.template import Context, Template

from apps.core.enums import TrustLevel

pytestmark = [pytest.mark.unit]


def _render(user: object) -> str:
    """Render the trust badge template tag for a given user mock."""
    template_obj = Template("{% load trust_tags %}{% render_trust_badge user %}")
    context = Context({"user": user, "request": None})
    return template_obj.render(context)


def test_uses_prefetched_trust_score_without_db_query() -> None:
    """When ``user.trust_score`` is set, no DB query is issued."""
    user = MagicMock()
    # Mark as authenticated (not anonymous)
    user.is_anonymous = False
    # Simulate a prefetched SellerTrustScore via OneToOne reverse accessor
    # (prefetch_related("user__trust_score") populates this).
    mock_score = MagicMock()
    mock_score.trust_level = TrustLevel.VERIFIED
    type(user).trust_score = PropertyMock(return_value=mock_score)

    with patch(
        "apps.trust.templatetags.trust_tags.SellerTrustScore.objects.get"
    ) as mock_get:
        html = _render(user)
        # The .get() must NOT be called because the prefetched attr exists
        mock_get.assert_not_called()

    assert "Verified" in html


def test_falls_back_to_db_when_not_prefetched() -> None:
    """When ``user.trust_score`` is absent, ``SellerTrustScore.objects.get`` is used."""
    user = MagicMock()
    user.is_anonymous = False
    # Remove the auto-created child mock so getattr falls through to the
    # PropertyMock (simulating a non-prefetched reverse accessor).
    del user.trust_score
    # Simulate the reverse accessor raising AttributeError (not prefetched)
    type(user).trust_score = PropertyMock(side_effect=AttributeError("trust_score"))

    mock_score = MagicMock()
    mock_score.trust_level = TrustLevel.PRO

    with patch(
        "apps.trust.templatetags.trust_tags.SellerTrustScore.objects.get",
        return_value=mock_score,
    ) as mock_get:
        html = _render(user)
        mock_get.assert_called_once_with(user=user)

    assert "Pro" in html


def test_returns_empty_for_anonymous_user() -> None:
    """Anonymous users get no badge — early return, no DB query."""
    user = MagicMock()
    user.is_anonymous = True

    with patch(
        "apps.trust.templatetags.trust_tags.SellerTrustScore.objects.get"
    ) as mock_get:
        html = _render(user)
        mock_get.assert_not_called()

    assert html == ""
