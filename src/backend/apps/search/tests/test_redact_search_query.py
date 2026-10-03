"""
Tests for search-query PII redaction (SRH-004).

Covers:
- ``redact_search_query`` unit behavior (phones, emails, names, benign terms).
- ``increment_popular_search`` persisting a redacted ``query``.
- ``record_search_history`` persisting a redacted ``query`` (DB + session).
- Non-regression: benign queries still store a usable value and autocomplete
  suggestions still resolve via ``query_normalized``.
"""

import pytest

from apps.core.utils.sanitize import redact_search_query, search_query_key
from apps.search.models import PopularSearch, SearchHistory
from apps.search.services.popular_search import (
    get_popular_suggestions,
    increment_popular_search,
)
from apps.search.services.search_history import record_search_history
from apps.users.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ---------------------------------------------------------------------------
# redact_search_query unit tests
# ---------------------------------------------------------------------------


class TestRedactSearchQuery:
    """Unit tests for ``redact_search_query``."""

    def test_redacts_phone_number(self) -> None:
        """Phone numbers are masked."""
        assert redact_search_query("куплю +79001234567") == "куплю +7**********"

    def test_redacts_email(self) -> None:
        """Email addresses keep only the local-part prefix + '@domain'."""
        assert (
            redact_search_query("контакт user@example.com")
            == "контакт us**@example.com"
        )

    def test_redacts_multiple_pii(self) -> None:
        """Phone, email and name are all masked in a single query."""
        result = redact_search_query(
            "Иван Петров +79001234567 user@example.com"
        )
        assert "+7**********" in result
        assert "us**@example.com" in result
        assert "Иван" not in result
        assert "Петров" not in result
        assert "И*** П*****" in result

    def test_masks_multi_word_name(self) -> None:
        """Two consecutive capitalized words are treated as a personal name."""
        assert redact_search_query("Ivan Petrov") == "I*** P*****"

    def test_does_not_mask_single_capitalized_word(self) -> None:
        """A single capitalized word (city/brand) is left intact (conservative)."""
        assert redact_search_query("Sarajevo") == "Sarajevo"
        assert redact_search_query("Bosna") == "Bosna"
        assert redact_search_query("Сараево") == "Сараево"

    def test_benign_query_unchanged(self) -> None:
        """A benign query without PII is returned unchanged."""
        assert redact_search_query("велосипед") == "велосипед"

    def test_empty_query_unchanged(self) -> None:
        """Empty input is returned unchanged."""
        assert redact_search_query("") == ""
        assert redact_search_query("   ") == "   "

    def test_truncates_long_query(self) -> None:
        """Queries are truncated to a safe length."""
        long = "x" * 500
        assert len(redact_search_query(long)) == 100

    def test_never_lengthens_query(self) -> None:
        """Redaction never lengthens a query (200-char column cap stays safe)."""
        for q in ("+79001234567", "user@example.com", "Ivan Petrov"):
            assert len(redact_search_query(q)) <= len(q)


# ---------------------------------------------------------------------------
# increment_popular_search redaction
# ---------------------------------------------------------------------------


class TestIncrementPopularSearchRedaction:
    """Popular search persists a redacted query (SRH-004)."""

    def test_stores_redacted_query(self) -> None:
        """PII substrings are absent from the persisted ``query``."""
        raw = "куплю велосипед +79001234567 user@example.com"
        increment_popular_search(raw)

        # The key is derived from the redacted query (06-PII-108).
        entry = PopularSearch.objects.get(query_normalized=search_query_key(raw))
        assert "+79001234567" not in entry.query
        assert "user@example.com" not in entry.query
        assert "+7**********" in entry.query
        assert "us**@example.com" in entry.query

    def test_updates_redacted_query_on_increment(self) -> None:
        """Incrementing an existing entry stores the redacted query."""
        raw = "велосипед user@example.com"
        increment_popular_search(raw)
        increment_popular_search(raw)

        entry = PopularSearch.objects.get(query_normalized=search_query_key(raw))
        assert entry.hit_count == 2
        assert "user@example.com" not in entry.query

    def test_benign_query_stored_and_suggestible(self) -> None:
        """A benign query is stored verbatim and still yields suggestions."""
        increment_popular_search("велосипед")

        entry = PopularSearch.objects.get(query_normalized="велосипед")
        assert entry.query == "велосипед"

        # Bump hit count past the suggestion threshold and resolve via
        # query_normalized.
        for _ in range(10):
            increment_popular_search("велосипед")
        suggestions = get_popular_suggestions("вел")
        assert any(s.text == "велосипед" for s in suggestions)


# ---------------------------------------------------------------------------
# record_search_history redaction
# ---------------------------------------------------------------------------


class TestRecordSearchHistoryRedaction:
    """Search history persists a redacted query (SRH-004)."""

    def test_stores_redacted_query_db(self, buyer: User) -> None:
        """Authenticated history stores a redacted query."""
        raw = "Иван Петров +79001234567"
        record_search_history(buyer.id, raw)

        entry = SearchHistory.objects.get(
            user=buyer, query_normalized=search_query_key(raw)
        )
        assert "+79001234567" not in entry.query
        assert "Иван" not in entry.query
        assert "Петров" not in entry.query

    def test_stores_redacted_query_session(self) -> None:
        """Anonymous session history stores a redacted query."""
        from django.contrib.sessions.backends.db import SessionStore

        session = SessionStore()
        raw = "Иван Петров"
        record_search_history(None, raw, session=session)

        # The session key is derived from the redacted query (06-PII-108): the
        # un-redacted lower-cased Cyrillic name must not be the key.
        assert session["search_history"][0]["query_normalized"] == search_query_key(raw)
        assert "Иван" not in session["search_history"][0]["query"]
        assert "Петров" not in session["search_history"][0]["query"]

    def test_benign_query_unchanged(self, buyer: User) -> None:
        """A benign query is stored verbatim and still usable."""
        record_search_history(buyer.id, "велосипед")

        entry = SearchHistory.objects.get(
            user=buyer, query_normalized="велосипед"
        )
        assert entry.query == "велосипед"
