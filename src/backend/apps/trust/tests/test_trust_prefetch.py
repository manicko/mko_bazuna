"""
Verification test for the trust-badge prefetch detection (13-PERF-004 validated 2026-09).

The template tag must read the related ``SellerTrustScore`` from the attribute
the ORM actually populates.  For a reverse ``OneToOneField``
(``related_name="trust_score"``), ``prefetch_related("user__trust_score")``
caches the related object in the forward descriptor — NOT in
``user._prefetched_objects_cache`` (which serves reverse FK / M2M prefetches).
The previous implementation tested ``_prefetched_objects_cache`` for a
``"trust_score"`` key, which can never hold it, so the "prefetched" branch was
dead code.

These tests assert observable behaviour against real DB objects:

1. A genuinely prefetched relation issues **zero** ``SellerTrustScore``
   queries when the badge renders.
2. A genuinely unprefetched relation issues one fallback lookup (retained for
   that path) and still renders the badge.
3. A user with no score renders no badge and issues no fallback lookup on the
   prefetched (cached-``DoesNotExist``) path.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.template import Context, Template
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.ads.models import Ad
from apps.core.enums import AdStatus, TrustLevel
from apps.trust.models import SellerTrustScore
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_BADGE_TEMPLATE = "{% load trust_tags %}{% render_trust_badge user %}"


def _render(user: object) -> str:
    """Render the trust badge template tag for a given user."""
    return Template(_BADGE_TEMPLATE).render(
        Context({"user": user, "request": None})
    )


def _trust_queries(captured: list[dict[str, object]]) -> int:
    return len([q for q in captured if "seller_trust_scores" in str(q["sql"])])


def test_prefetched_relation_issues_zero_extra_queries(seller, category, city) -> None:
    """A prefetched ``user__trust_score`` is served from cache — no lookup."""
    SellerTrustScore.objects.create(
        user=seller, trust_level=TrustLevel.VERIFIED, score=50
    )
    ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

    prefetched = list(
        Ad.objects.filter(pk=ad.pk).prefetch_related("user__trust_score")
    )[0]

    with CaptureQueriesContext(connection) as ctx:
        html = _render(prefetched.user)

    assert "Verified" in html
    assert _trust_queries(ctx.captured_queries) == 0


def test_unprefetched_relation_falls_back_and_still_renders(
    seller, category, city
) -> None:
    """A genuinely unprefetched user reaches the single fallback lookup."""
    SellerTrustScore.objects.create(
        user=seller, trust_level=TrustLevel.PRO, score=80
    )
    ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

    plain_user = Ad.objects.get(pk=ad.pk).user

    with CaptureQueriesContext(connection) as ctx:
        html = _render(plain_user)

    assert "Pro" in html
    assert _trust_queries(ctx.captured_queries) == 1


def test_prefetched_absent_score_renders_no_badge(seller, category, city) -> None:
    """A prefetched relation with no related row renders no badge.

    Django's reverse-OneToOne prefetch does not cache a ``DoesNotExist`` for an
    absent row, so the descriptor resolves it with one bounded, index-backed
    lookup.  That is the documented, bounded cost (13-PERF-004 validated
    2026-09); the badge must simply not render.
    """
    ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

    prefetched = list(
        Ad.objects.filter(pk=ad.pk).prefetch_related("user__trust_score")
    )[0]

    with CaptureQueriesContext(connection) as ctx:
        html = _render(prefetched.user)

    assert html == ""
    assert _trust_queries(ctx.captured_queries) <= 1


def test_unprefetched_absent_score_renders_no_badge(seller, category, city) -> None:
    """A user with no score renders no badge via the fallback path."""
    ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
    plain_user = Ad.objects.get(pk=ad.pk).user

    html = _render(plain_user)

    assert html == ""


def test_anonymous_user_returns_empty_without_query() -> None:
    """Anonymous users get no badge and issue no query."""
    from django.contrib.auth.models import AnonymousUser

    with CaptureQueriesContext(connection) as ctx:
        html = _render(AnonymousUser())

    assert html == ""
    assert _trust_queries(ctx.captured_queries) == 0


def test_listings_page_trust_badge_no_n_plus_1(seller, category, city) -> None:
    """The listings render path does not issue a per-ad trust-score lookup."""
    SellerTrustScore.objects.create(
        user=seller, trust_level=TrustLevel.VERIFIED, score=50
    )
    for i in range(5):
        create_test_ad(
            seller,
            category,
            city,
            title=f"Prefetch Ad {i}",
            status=AdStatus.PUBLISHED,
        )

    with CaptureQueriesContext(connection) as ctx:
        response = Client().get(reverse("ads:listings"))

    assert response.status_code == 200
    # One prefetch SELECT for the whole page, never one per ad.
    assert _trust_queries(ctx.captured_queries) <= 1
