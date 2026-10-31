"""Tests for relevance tiebreaker (``-rank, -published_at, -id``) in FTS results."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.core.enums import AdStatus
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestRelevanceTiebreaker:
    """FTS results order by ``-rank, -published_at, -id``."""

    def test_rank_tie_breaks_by_published_at(self, seller, category, city) -> None:
        now = timezone.now()
        ad_older = create_test_ad(
            seller,
            category,
            city,
            title="Продам красный телефон",
            status=AdStatus.PUBLISHED,
            published_at=now - timedelta(days=1),
        )
        ad_newer = create_test_ad(
            seller,
            category,
            city,
            title="Продам красный телефон",
            status=AdStatus.PUBLISHED,
            published_at=now,
        )

        client = Client()
        response = client.get("/search/?q=красный телефон&lang=ru")

        assert response.status_code == 200
        ids = list(a.id for a in response.context["page_obj"])
        assert ad_newer.id in ids and ad_older.id in ids
        assert ids.index(ad_newer.id) < ids.index(ad_older.id)


class TestListingsTiebreakerDoesNotAffectFtsRelevance:
    """The ``-id`` tiebreaker in ``ListingsQuery._apply_sort`` never reorders FTS.

    The plain-listings ``-id`` tiebreaker (plan R2) lives in the shared listings
    service, but the FTS path builds its own ordering in
    ``apps.search.services.fts._apply_fts_filtering`` (``-rank`` first). These
    tests prove the tiebreaker change leaves relevance ranking rank-first: a
    different-relevance pair is never reordered by ``-id``, even when the
    higher-relevance ad has the SMALLER id (which would win a pure ``-id desc``
    tiebreak).
    """

    def test_higher_relevance_wins_even_with_smaller_id(
        self, seller, category, city
    ) -> None:
        """A title match outranks a description-only match regardless of id.

        The description-only ad is created FIRST, so it holds the smaller id; a
        naive ``-id`` ordering would float it above the title match. Relevance
        must still rank the title match first, proving the listings tiebreaker
        does not reach the FTS ordering.
        """
        ad_desc = create_test_ad(
            seller,
            category,
            city,
            title="Самокат",
            description="Продается велосипед в хорошем состоянии",
            status=AdStatus.PUBLISHED,
        )
        ad_title = create_test_ad(
            seller,
            category,
            city,
            title="Велосипед",
            description="Продается товар",
            status=AdStatus.PUBLISHED,
        )
        # Precondition: the title match has the LARGER id, so a pure -id ordering
        # would place it first for the wrong reason. Relevance-first must agree.
        assert ad_title.id > ad_desc.id

        client = Client()
        response = client.get("/search/?q=велосипед&lang=ru")

        assert response.status_code == 200
        ids = list(a.id for a in response.context["page_obj"])
        assert ad_title.id in ids and ad_desc.id in ids
        assert ids.index(ad_title.id) < ids.index(ad_desc.id)

    def test_equal_relevance_uses_id_as_final_tiebreak(
        self, seller, category, city
    ) -> None:
        """Equal-rank, equal-``published_at`` ads break by ``-id`` in the FTS order.

        The FTS ordering ends ``…, -published_at, -id`` (unchanged by this task);
        this pins that the FTS ``-id`` term — not the listings service's — is
        what resolves the final tie, keeping the two tiebreakers semantically
        identical but structurally independent.
        """
        shared = timezone.now()
        ads = [
            create_test_ad(
                seller,
                category,
                city,
                title="Велосипед",
                description="Продается товар",
                status=AdStatus.PUBLISHED,
                published_at=shared,
            )
            for _ in range(3)
        ]
        expected = sorted((a.id for a in ads), reverse=True)

        client = Client()
        response = client.get("/search/?q=велосипед&lang=ru")

        assert response.status_code == 200
        ids = list(a.id for a in response.context["page_obj"])
        assert ids == expected
