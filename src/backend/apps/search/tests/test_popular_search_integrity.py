"""
Integrity tests for ``popular_searches.query_normalized`` (08-SRCH-003).

``PopularSearch.query_normalized`` was a plain ``db_index=True`` column with no
unique constraint. ``increment_popular_search`` uses ``get_or_create``, whose
internal ``.get()`` re-raises ``MultipleObjectsReturned`` as soon as a duplicate
exists — and that raise is unguarded on the anonymous ``GET /search/`` path, so
a duplicate pair turns an unauthenticated endpoint into a hard 500.

These tests pin the post-remediation contract:

- the database enforces uniqueness;
- the shipped ``0006`` data migration merges collisions without losing
  popularity (``hit_count`` is the SUM, never the MAX) or recency;
- the merge keeps the survivor's own ``query`` and ``source``;
- ``GET /search/`` returns 200 once the constraint is in place;
- ``08-NEW-02``'s floor holds on both edges (9 hidden, 12 eligible);
- ``SeedService._seed_popular_searches`` cannot flip a production row.

The dedup tests drop the unique constraint temporarily so the pre-merge
population can be constructed, exactly as it exists in a real deployment when
``0006`` runs.
"""

from __future__ import annotations

import importlib
from datetime import timedelta

import pytest
from django.apps import apps as django_apps
from django.db import IntegrityError, connection, migrations, models
from django.test import Client
from django.utils import timezone

from apps.search.models import PopularSearch

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.integration]

_CONSTRAINT = models.UniqueConstraint(
    fields=["query_normalized"],
    name="uq_popular_search_query_normalized",
)


def _migration_module():
    """Import the shipped ``0006`` integrity migration module.

    The module name starts with a digit, so a static ``import`` is impossible;
    ``importlib`` loads the real artefact the deploy runs rather than an inline
    replay that would stay green if the migration were rewritten.
    """
    return importlib.import_module(
        "apps.search.migrations.0006_deduplicate_and_unique_popular_search"
    )


def _run_forward(migration_module) -> None:
    """Run just the migration's forward ``RunPython`` (data) function."""
    operation = migration_module.Migration.operations[0]
    assert isinstance(operation, migrations.RunPython)
    operation.code(django_apps, None)


class _ConstraintDropped:
    """Context manager removing the unique constraint so duplicates can be seeded.

    A real deployment holds duplicates when ``0006`` runs; the tests reconstruct
    that population by dropping the constraint, inserting the pre-merge rows and
    restoring the constraint afterwards.
    """

    def __enter__(self) -> None:
        with connection.schema_editor() as editor:
            editor.remove_constraint(PopularSearch, _CONSTRAINT)

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        with connection.schema_editor() as editor:
            editor.add_constraint(PopularSearch, _CONSTRAINT)


class TestVerifiedIndexShape:
    """The post-migration index shape (08-SRCH-003)."""

    def test_duplicate_key_is_rejected(self) -> None:
        """A duplicate ``query_normalized`` raises ``IntegrityError``."""
        PopularSearch.objects.create(query="a", query_normalized="dup")
        with pytest.raises(IntegrityError):
            PopularSearch.objects.create(query="b", query_normalized="dup")


class TestDedupArithmetic:
    """The shipped ``0006`` forward function's merge contract (08-SRCH-003)."""

    def test_merges_hit_counts_by_sum_not_max(self) -> None:
        """A group of 3 + 5 merges to one row with ``hit_count == 8`` (not 5)."""
        with _ConstraintDropped():
            PopularSearch.objects.create(
                query="three", query_normalized="dup", hit_count=3
            )
            PopularSearch.objects.create(
                query="five", query_normalized="dup", hit_count=5
            )
            _run_forward(_migration_module())

        rows = list(PopularSearch.objects.filter(query_normalized="dup"))
        assert len(rows) == 1
        assert rows[0].hit_count == 8

    def test_survivor_keeps_greatest_last_seen(self) -> None:
        """The merged row keeps the group's greatest ``last_seen``."""
        new_ts = timezone.now() - timedelta(hours=1)
        with _ConstraintDropped():
            older = PopularSearch.objects.create(
                query="older", query_normalized="dup", hit_count=5
            )
            newer = PopularSearch.objects.create(
                query="newer", query_normalized="dup", hit_count=3
            )
            # ``last_seen`` is ``auto_now``; write distinct values verbatim.
            PopularSearch.objects.filter(pk=older.pk).update(
                last_seen=timezone.now() - timedelta(days=2)
            )
            PopularSearch.objects.filter(pk=newer.pk).update(last_seen=new_ts)

            _run_forward(_migration_module())

        survivor = PopularSearch.objects.get(query_normalized="dup")
        survivor.refresh_from_db()
        assert survivor.last_seen >= new_ts - timedelta(seconds=1)

    def test_survivor_keeps_its_own_query_and_source(self) -> None:
        """The survivor's ``query`` and ``source`` are its own, untouched."""
        with _ConstraintDropped():
            survivor = PopularSearch.objects.create(
                query="keep-me", query_normalized="dup", hit_count=9, source=None
            )
            PopularSearch.objects.create(
                query="drop-me", query_normalized="dup", hit_count=1, source="SEED"
            )
            _run_forward(_migration_module())
            survivor_pk = survivor.pk

        rows = list(PopularSearch.objects.filter(query_normalized="dup"))
        assert len(rows) == 1
        assert rows[0].pk == survivor_pk
        assert rows[0].query == "keep-me"
        assert rows[0].source is None


class TestSearchViewWithDuplicate:
    """The anonymous ``GET /search/`` path no longer 500s (08-SRCH-003)."""

    def test_search_view_returns_200_after_duplicate_attempt(self) -> None:
        """A duplicate insert is rejected, so ``GET /search/`` returns 200.

        Before the constraint, two rows could share the key and
        ``increment_popular_search``'s ``get_or_create`` re-raised
        ``MultipleObjectsReturned`` (recorded RED evidence: the view raised
        ``MultipleObjectsReturned``). After the constraint the duplicate cannot
        exist — the second insert raises ``IntegrityError`` — and the
        unauthenticated endpoint returns 200.
        """
        PopularSearch.objects.create(query="велосипед", query_normalized="велосипед")
        with pytest.raises(IntegrityError):
            PopularSearch.objects.create(
                query="велосипед", query_normalized="велосипед"
            )

        client = Client()
        response = client.get("/search/?q=велосипед&lang=ru")
        assert response.status_code == 200
        assert PopularSearch.objects.filter(query_normalized="велосипед").count() == 1


class TestSuggestionFloor:
    """``08-NEW-02``: the dedup floor holds on both edges."""

    def test_floor_below_hides_and_above_is_eligible(self) -> None:
        """A group summing to 9 stays hidden; summing to 12 becomes eligible.

        ``08-NEW-02``: the dedup can push a merged group across
        ``_MIN_HIT_COUNT``, so both edges are asserted after the merge.
        """
        from apps.search.services.popular_search import (
            _MIN_HIT_COUNT,
            get_popular_suggestions,
        )

        assert _MIN_HIT_COUNT == 10

        with _ConstraintDropped():
            # Same key, two rows summing to 9 (< 10): stays hidden after merge.
            PopularSearch.objects.create(
                query="ниже", query_normalized="ниже", hit_count=4
            )
            PopularSearch.objects.create(
                query="ниже", query_normalized="ниже", hit_count=5
            )
            # Same key, two rows summing to 12 (>= 10): becomes eligible.
            PopularSearch.objects.create(
                query="выше", query_normalized="выше", hit_count=4
            )
            PopularSearch.objects.create(
                query="выше", query_normalized="выше", hit_count=8
            )
            _run_forward(_migration_module())

        assert PopularSearch.objects.get(query_normalized="ниже").hit_count == 9
        assert PopularSearch.objects.get(query_normalized="выше").hit_count == 12

        below = get_popular_suggestions("ниж")
        assert all(s.text != "ниже" for s in below)

        above = get_popular_suggestions("выш")
        assert any(s.text == "выше" for s in above)


class TestSeedScoping:
    """``_seed_popular_searches`` is scoped to ``source=SEED`` (08-SRCH-003)."""

    def test_seeder_cannot_flip_production_row(self) -> None:
        """A production row colliding with a config query is neither flipped nor deleted."""
        from apps.core.utils.sanitize import search_query_key
        from apps.seed.services.seed_service import SeedService

        raw = "велосипед"
        key = search_query_key(raw)
        production = PopularSearch.objects.create(
            query=raw,
            query_normalized=key,
            hit_count=42,
            source=None,
        )

        service = SeedService()
        service.config = {
            "popular_searches": [{"query": raw, "hit_count": 50}],
            "faker_seed": 42,
        }
        service._seed_popular_searches(limit=0)

        production.refresh_from_db()
        assert production.source is None
        assert production.hit_count == 42
        assert PopularSearch.objects.filter(pk=production.pk).exists()


class TestReverseIsNoop:
    """The shipped migration's reverse is deliberate ``RunPython.noop``."""

    def test_reverse_is_noop(self) -> None:
        operation = _migration_module().Migration.operations[0]
        assert isinstance(operation, migrations.RunPython)
        assert operation.reverse_code is migrations.RunPython.noop
