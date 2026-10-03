"""
Tests for ``search_query_key`` and the ``search/0005`` key re-derivation (06-PII-108).

Covers:
- The derivation contract: redact FIRST, then strip and lower, on the raw query.
- The leak is closed in ``SearchHistory`` — phone, e-mail and a multi-word
  personal name, none surviving in any column.
- The leak is closed in the anonymous session store.
- The leak is closed in the global ``PopularSearch`` table.
- Benign queries are byte-identical and dedup/prune behave as before.
- ``get_popular_suggestions`` still resolves through ``query_normalized__startswith``.
- Redaction idempotence: ``redact_search_query(redact_search_query(q))`` is the
  key under which the migration's re-derivation is exact.
- The shipped migration's forward function: colliding ``popular_searches`` keys
  merge with ``hit_count`` summed, ``search_history`` keeps the newest row, no
  duplicate ``query_normalized`` survives and no raw PII remains.
"""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps as django_apps
from django.contrib.sessions.backends.db import SessionStore
from django.db import migrations
from django.utils import timezone

from apps.core.utils.sanitize import redact_search_query, search_query_key
from apps.search.models import PopularSearch, SearchHistory
from apps.search.services.popular_search import (
    get_popular_suggestions,
    increment_popular_search,
)
from apps.search.services.search_history import (
    get_user_search_history,
    record_search_history,
)
from apps.users.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# A query carrying all three PII classes at once.
_PII_QUERY = "Иван Петров +79001234567 user@example.com"
_PII_FRAGMENTS = ("Иван", "Петров", "+79001234567", "user@example.com")


def _migration_module():
    """Import the shipped ``0005`` key migration module.

    The module name starts with a digit, so a static ``import`` is impossible;
    ``importlib`` loads the real artefact the deploy runs rather than an inline
    replay that would stay green if the migration were rewritten.
    """
    return importlib.import_module(
        "apps.search.migrations.0005_redact_search_query_keys"
    )


def _contains_pii(value: str) -> bool:
    lowered = value.lower()
    return any(fragment.lower() in lowered for fragment in _PII_FRAGMENTS)


class TestSearchQueryKeyDerivation:
    """The helper is the single key derivation."""

    def test_is_redact_then_lower_on_raw_query(self) -> None:
        """``search_query_key(q) == redact_search_query(q).strip().lower()``."""
        assert search_query_key(_PII_QUERY) == redact_search_query(
            _PII_QUERY
        ).strip().lower()

    def test_lower_then_redact_would_leak_the_name(self) -> None:
        """The rejected ordering leaves the personal name in the key.

        This pins WHY the order is load-bearing: the name pattern needs an
        uppercase initial, so redacting an already-lowercased string masks
        nothing.
        """
        wrong_order = redact_search_query(_PII_QUERY.lower()).strip().lower()
        assert "иван" in wrong_order and "петров" in wrong_order
        assert not _contains_pii(search_query_key(_PII_QUERY))

    def test_benign_query_is_identity(self) -> None:
        """A PII-free query is byte-identical under the new derivation."""
        assert search_query_key("велосипед") == "велосипед"
        assert search_query_key("  Велосипед  ") == "велосипед"

    def test_empty_query_yields_empty_key(self) -> None:
        """Empty and whitespace-only inputs collapse to an empty key."""
        assert search_query_key("") == ""
        assert search_query_key("   ") == ""

    def test_never_lengthens_input(self) -> None:
        """The key is never longer than the raw query (200-char caps stay safe)."""
        for query in ("+79001234567", "user@example.com", "Ivan Petrov"):
            assert len(search_query_key(query)) <= len(query)


class TestSearchQueryKeyIdempotence:
    """The migration re-derives from the stored, redacted ``query`` column."""

    @pytest.mark.parametrize(
        "query",
        [
            "куплю +79001234567",
            "контакт user@example.com",
            "Иван Петров +79001234567 user@example.com",
            "Ivan Petrov",
            "Sarajevo",
            "велосипед",
            "",
        ],
    )
    def test_re_deriving_from_a_redacted_query_is_stable(self, query: str) -> None:
        """Re-redacting the stored query yields the same key (idempotence)."""
        stored = redact_search_query(query)
        assert redact_search_query(stored).strip().lower() == search_query_key(query)

    def test_idempotence_holds_for_a_long_query(self) -> None:
        """A 200-character query trivially satisfies redaction idempotence."""
        long_query = "Иван Петров " + "x" * 200
        stored = redact_search_query(long_query)
        assert redact_search_query(stored).strip().lower() == search_query_key(
            long_query
        )


class TestSearchHistoryLeakClosed:
    """``record_search_history`` writes no raw PII, in either store."""

    def test_db_row_contains_no_pii_in_any_column(self, buyer: User) -> None:
        """The table row carries none of phone, e-mail or name in any column."""
        record_search_history(buyer.id, _PII_QUERY)

        row = SearchHistory.objects.get(user=buyer)
        assert not _contains_pii(row.query)
        assert not _contains_pii(row.query_normalized)
        assert row.query_normalized == search_query_key(_PII_QUERY)

    def test_session_payload_contains_no_pii(self) -> None:
        """The anonymous session entry carries none of the three PII classes."""
        session = SessionStore()
        record_search_history(None, _PII_QUERY, session=session)

        entry = session["search_history"][0]
        assert not _contains_pii(entry["query"])
        assert not _contains_pii(entry["query_normalized"])
        assert entry["query_normalized"] == search_query_key(_PII_QUERY)


class TestPopularSearchLeakClosed:
    """``increment_popular_search`` writes no raw PII to the global table."""

    def test_global_key_contains_no_pii(self) -> None:
        """The global cross-user key carries none of the three PII classes."""
        increment_popular_search(_PII_QUERY)

        entry = PopularSearch.objects.get(query_normalized=search_query_key(_PII_QUERY))
        assert not _contains_pii(entry.query)
        assert not _contains_pii(entry.query_normalized)


class TestBenignBehaviourUnchanged:
    """Dedup, prune and the prefix read behave exactly as before."""

    def test_dedup_merges_what_it_merged(self, buyer: User) -> None:
        """Same key under different case/whitespace still collapses to one row."""
        record_search_history(buyer.id, "Велосипед")
        record_search_history(buyer.id, "  велосипед  ")

        assert SearchHistory.objects.filter(user=buyer).count() == 1

    def test_dedup_does_not_merge_distinct_queries(self, buyer: User) -> None:
        """Distinct benign queries remain two rows."""
        record_search_history(buyer.id, "велосипед")
        record_search_history(buyer.id, "автомобиль")

        assert SearchHistory.objects.filter(user=buyer).count() == 2

    def test_prune_caps_at_fifty(self, buyer: User) -> None:
        """``_MAX_HISTORY`` pruning still caps a user's history at 50."""
        for i in range(55):
            record_search_history(buyer.id, f"query{i}")

        assert SearchHistory.objects.filter(user=buyer).count() == 50

    def test_history_text_is_unchanged(self, buyer: User) -> None:
        """History read-back returns the redacted text, most recent first."""
        record_search_history(buyer.id, "первый")
        record_search_history(buyer.id, "второй")

        assert get_user_search_history(buyer.id) == ["второй", "первый"]

    def test_popular_autocomplete_resolves_through_startswith(self) -> None:
        """``get_popular_suggestions`` still matches on the key prefix."""
        for _ in range(11):
            increment_popular_search("велосипед")

        suggestions = get_popular_suggestions("вел")
        assert any(s.text == "велосипед" for s in suggestions)


class TestMigrationMergesAndCleans:
    """The shipped ``0005`` forward function's merge and anti-PII guarantees."""

    def test_reverse_is_noop(self) -> None:
        """The shipped migration's reverse is ``RunPython.noop``."""
        operation = _migration_module().Migration.operations[0]
        assert isinstance(operation, migrations.RunPython)
        assert operation.reverse_code is migrations.RunPython.noop

    def test_dependencies_follow_the_leaf(self) -> None:
        """The migration depends on the previous search leaf."""
        assert _migration_module().Migration.dependencies == [
            ("search", "0004_backfill_delivered_at")
        ]

    def test_colliding_popular_keys_merge_and_sum_hits(self) -> None:
        """Two raw variants of one key merge into a single summed row."""
        # Both rows' ``query`` columns redact to the same key ("и*** п*****"),
        # even though their historical ``query_normalized`` values differ.
        PopularSearch.objects.create(
            query="И*** П*****", query_normalized="иван петров", hit_count=6
        )
        PopularSearch.objects.create(
            query="И*** П*****", query_normalized="ИВАН ПЕТРОВ", hit_count=7
        )

        _migration_module().redact_query_keys(django_apps, None)

        rows = PopularSearch.objects.filter(
            query_normalized=search_query_key("Иван Петров")
        )
        assert rows.count() == 1
        assert rows.first().hit_count == 13
        assert PopularSearch.objects.count() == 1

    def test_no_duplicate_normalized_remains(self) -> None:
        """After the migration every ``query_normalized`` value is unique."""
        PopularSearch.objects.create(
            query="И*** П*****", query_normalized="иван петров", hit_count=1
        )
        PopularSearch.objects.create(
            query="И*** П*****", query_normalized="ИВАН ПЕТРОВ", hit_count=1
        )

        _migration_module().redact_query_keys(django_apps, None)

        keys = list(PopularSearch.objects.values_list("query_normalized", flat=True))
        assert len(keys) == len(set(keys))

    def test_search_history_keeps_the_newest_row(self, buyer: User) -> None:
        """Only the newest row survives per ``(user_id, new key)``."""
        older = SearchHistory.objects.create(
            user=buyer, query="И*** П*****", query_normalized="иван петров"
        )
        newer = SearchHistory.objects.create(
            user=buyer, query="И*** П*****", query_normalized="ИВАН ПЕТРОВ"
        )
        # ``created_at`` is ``auto_now_add``; set the ordering explicitly
        # through a queryset update, which bypasses the auto field.
        now = timezone.now()
        SearchHistory.objects.filter(pk=older.pk).update(
            created_at=now - timezone.timedelta(days=1)
        )
        SearchHistory.objects.filter(pk=newer.pk).update(created_at=now)

        _migration_module().redact_query_keys(django_apps, None)

        rows = list(SearchHistory.objects.filter(user=buyer))
        assert len(rows) == 1
        assert rows[0].pk == newer.pk
        assert rows[0].query_normalized == search_query_key("Иван Петров")

    def test_no_raw_pii_survives_after_migration(self, buyer: User) -> None:
        """Neither table retains a phone, e-mail or name in its key."""
        PopularSearch.objects.create(
            query="И*** П*****", query_normalized="иван петров +79001234567", hit_count=3
        )
        SearchHistory.objects.create(
            user=buyer, query="И*** П*****", query_normalized="иван петров"
        )

        _migration_module().redact_query_keys(django_apps, None)

        normalized = list(
            PopularSearch.objects.values_list("query_normalized", flat=True)
        ) + list(SearchHistory.objects.values_list("query_normalized", flat=True))
        for key in normalized:
            assert not _contains_pii(key)
