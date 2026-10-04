"""Behavioural pin for the first-party consent basis of analytics writes (06-PII-108).

The filed defect was: *"First-party ``AnalyticsEvent`` and ``SearchHistory``
writes are not gated on the recorded analytics/preferences consent."* The owner
chose option (a): **declare** the basis explicitly in the spec rather than gate
the writes. This module is the behavioural half of that decision — it asserts
the *chosen* behaviour, so a future change that silently starts gating these
first-party writes on consent fails here.

The assertion is behavioural: a **DECLINED** authenticated user still receives:

- ``SearchHistory`` rows from the real ``search`` view (via
  ``record_search_history``), and
- ``AnalyticsEvent`` rows from the real analytics path (``record_event``, fired
  by the ``search`` view for ``SEARCH_PERFORMED`` with the declined user as the
  actor).

It is deliberately **not** a source-level or settings check. ``test_search.py``
already asserts that a *declined seller's PUBLISHED ads* are hidden from search
and listings (``TestSearchViewDeclinedConsent``); that is a **different** rule
(ad visibility) and is not conflated here.

Rationale for option (a) over gating: ``SearchHistory`` is the account's own
search list (its recent searches / autocomplete), a materially different data
subject relationship from the third-party cookieless Plausible snippet; and
withdrawal already deletes these rows (BLOCK 9, ``06-PII-110``), so a retention
boundary exists. The legal-basis classification is the owner's to confirm with
the DPO (see ``technical-specification.md`` §L).
"""

from __future__ import annotations

import pytest
from django.test import Client
from django.utils import timezone

from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AnalyticsEventType
from apps.search.models import SearchHistory
from apps.users.models import User
from conftest import make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def declined_user() -> User:
    """A registered, previously-consented user who has since DECLINED.

    ``consent_given_at`` is set so the account is a realistic "accepted then
    declined" subject; the decline is carried by ``is_declined`` alone (decision
    K: a decline erases nothing). The user is given a distinct ``telegram_id``
    so it cannot collide with the shared ``seller``/``user`` fixtures.
    """
    return make_user(900000801, is_declined=True, consent_given_at=timezone.now())


class TestDeclinedUserSearchHistoryWrites:
    """A declined authenticated user still accrues SearchHistory rows."""

    def test_search_records_search_history_for_declined_user(
        self, declined_user: User
    ) -> None:
        """Running the real ``search`` view writes a SearchHistory row.

        No consent gate exists on this first-party write (declared basis); the
        row is written for the declined user exactly as for any other account.
        """
        assert not SearchHistory.objects.filter(user=declined_user).exists()

        client = Client()
        client.force_login(declined_user)
        response = client.get("/search/?q=велосипед&lang=ru")

        assert response.status_code == 200
        assert SearchHistory.objects.filter(user=declined_user).exists(), (
            "a DECLINED authenticated user must still receive a SearchHistory "
            "row from the search view (declared first-party basis, 06-PII-108)"
        )


class TestDeclinedUserAnalyticsWrites:
    """A declined authenticated user still accrues AnalyticsEvent rows."""

    def test_search_records_analytics_event_for_declined_user(
        self, declined_user: User
    ) -> None:
        """Running the real ``search`` view writes a SEARCH_PERFORMED event.

        The event is attributed to the declined user (``user_id``), exercising
        the analytics path the finding named.
        """
        assert not AnalyticsEvent.objects.filter(user=declined_user).exists()

        client = Client()
        client.force_login(declined_user)
        response = client.get("/search/?q=велосипед&lang=ru")

        assert response.status_code == 200
        events = AnalyticsEvent.objects.filter(user=declined_user)
        assert events.exists(), (
            "a DECLINED authenticated user must still receive an AnalyticsEvent "
            "row from the search analytics path (declared first-party basis, "
            "06-PII-108)"
        )
        assert events.filter(
            event_type=AnalyticsEventType.SEARCH_PERFORMED
        ).exists()
