"""
Integration tests for the ``setup_search_triggers --backfill`` management command.

Verifies that:
  * ``--backfill`` recomputes NULL per-language search vectors via the trigger.
  * Without ``--backfill``, the command is DDL-only (no data change).
  * ``--backfill`` is idempotent (second run finds 0 NULL rows).

These are DB-backed tests using real PostgreSQL per project spec (native FTS
with the 'russian'/'simple'/'english' text search configurations is
PostgreSQL-only).
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


def _null_search_vectors(ad: Ad) -> None:
    """Set all per-language search vectors to NULL, bypassing the trigger.

    A plain ``QuerySet.update()`` fires the BEFORE UPDATE trigger, which would
    immediately repopulate the vectors. ``SET session_replication_role =
    'replica'`` suspends trigger execution so we can simulate pre-existing rows
    that bypassed the trigger, e.g. during seed ``bulk_create``. Triggers are
    re-enabled before returning so the subsequent backfill UPDATE fires
    ``ads_search_vector_fn`` normally.
    """
    with connection.cursor() as cursor:
        cursor.execute("SET session_replication_role = 'replica';")
        cursor.execute(
            "UPDATE ads SET search_vector_ru = NULL, "
            "search_vector_bs = NULL, "
            "search_vector_en = NULL "
            "WHERE id = %s;",
            [ad.pk],
        )
        cursor.execute("SET session_replication_role = 'origin';")


class TestSetupSearchTriggersBackfill:
    """Tests for the ``--backfill`` opt-in flag on setup_search_triggers."""

    def test_backfill_populates_null_vectors(self, seller, category, city):
        """``--backfill`` recomputes NULL vectors via the trigger."""
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            title="Красный велосипед",
            description="Продается детский велосипед",
        )
        # Trigger populated vectors on INSERT; null them out to simulate
        # pre-existing rows that bypassed the trigger.
        _null_search_vectors(ad)
        ad.refresh_from_db()
        assert ad.search_vector_ru is None
        assert ad.search_vector_bs is None
        assert ad.search_vector_en is None

        call_command("setup_search_triggers", backfill=True)

        ad.refresh_from_db()
        assert ad.search_vector_ru is not None
        assert ad.search_vector_bs is not None
        assert ad.search_vector_en is not None

    def test_default_no_backfill_does_not_change_data(self, seller, category, city):
        """Without ``--backfill`` the command is DDL-only, no data change."""
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            title="Красный велосипед",
            description="Продается детский велосипед",
        )
        ad.refresh_from_db()
        before = {
            "ru": ad.search_vector_ru,
            "bs": ad.search_vector_bs,
            "en": ad.search_vector_en,
        }

        call_command("setup_search_triggers")

        ad.refresh_from_db()
        after = {
            "ru": ad.search_vector_ru,
            "bs": ad.search_vector_bs,
            "en": ad.search_vector_en,
        }
        assert before == after

    def test_backfill_is_idempotent(self, seller, category, city):
        """Running ``--backfill`` twice: second run finds 0 NULL rows."""
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.PUBLISHED,
            title="Красный велосипед",
            description="Продается детский велосипед",
        )
        _null_search_vectors(ad)

        # First run — repopulates the NULL vectors.
        first_out = StringIO()
        call_command("setup_search_triggers", backfill=True, stdout=first_out)
        assert "Backfilled search vectors for 1 rows" in first_out.getvalue()

        # Second run — no NULL rows remain, so 0 are updated.
        second_out = StringIO()
        call_command("setup_search_triggers", backfill=True, stdout=second_out)
        assert "Backfilled search vectors for 0 rows" in second_out.getvalue()

        ad.refresh_from_db()
        assert ad.search_vector_ru is not None
        assert ad.search_vector_bs is not None
        assert ad.search_vector_en is not None
