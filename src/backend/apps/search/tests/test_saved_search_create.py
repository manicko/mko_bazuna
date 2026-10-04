"""
Tests for the saved-search create flow + modal URL wiring (FT-002).

Covers:
- ``search:save-search`` resolves (CR17).
- POST creates an active ``SavedSearch`` with the captured filters and the
  user's LANGUAGE_CODE.
- Requires authentication.
- The dead ``search:list`` reference is gone from the modal template (R8).
- The query is bounded (``max_length=200``) at the model **and** at the view,
  and over-cap values are refused rather than truncated (08-SRCH-011).
- The query is PII-redacted at write (one rule for all query-persistence paths).
"""

import pytest
from django.db import DataError, transaction
from django.test import Client
from django.urls import resolve, reverse

from apps.categories.models import Category
from apps.locations.models import City
from apps.search.models import SavedSearch
from apps.users.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# The persisted column bound under test (08-SRCH-011).
QUERY_MAX_LENGTH = 200


def test_save_search_url_resolves():
    """search:save-search resolves to a view (CR17)."""
    url = reverse("search:save-search")
    assert url == "/save-search/"
    assert resolve(url).func.__name__ == "save_search"


def test_create_saved_search_with_filters_and_language(
    buyer: User, category: Category, city: City, client: Client
) -> None:
    client.force_login(buyer)
    resp = client.post(
        reverse("search:save-search"),
        {
            "query": "велосипед",
            "city_id": str(city.id),
            "category_id": str(category.id),
            "min_price": "100",
            "max_price": "500",
        },
    )
    assert resp.status_code == 200

    ss = SavedSearch.objects.get(user=buyer)
    assert ss.query == "велосипед"
    assert ss.city_id == city.id
    assert ss.category_id == category.id
    assert ss.min_price == 100
    assert ss.max_price == 500
    assert ss.is_active is True
    assert ss.language == "en"  # default LANGUAGE_CODE in test is "en"


def test_requires_login(client: Client) -> None:
    resp = client.post(reverse("search:save-search"), {"query": "тест"})
    # login_required redirect to /login/issue/
    assert resp.status_code in (301, 302)


def test_modal_has_no_dangling_search_list_ref():
    """The save-search modal no longer references the removed search:list route."""
    from pathlib import Path

    modal_path = (
        Path(__file__).resolve().parents[3]
        / "templates"
        / "search"
        / "partials"
        / "save_search_modal.html"
    )
    content = modal_path.read_text(encoding="utf-8")
    # No functional URL reference to the removed route remains.
    assert "url 'search:list'" not in content
    assert 'url "search:list"' not in content


# ---------------------------------------------------------------------------
# 08-SRCH-011 / 08-VAL-006 — the query bound and redaction at write
# ---------------------------------------------------------------------------


def test_query_at_cap_round_trips_byte_identical(buyer: User, client: Client) -> None:
    """A query exactly at the cap is stored unchanged through the view."""
    client.force_login(buyer)
    # No PII, so redaction is a no-op and the value must survive byte-identical.
    at_cap = "a" * QUERY_MAX_LENGTH

    resp = client.post(reverse("search:save-search"), {"query": at_cap})

    assert resp.status_code == 200
    assert SavedSearch.objects.get(user=buyer).query == at_cap


def test_query_one_over_cap_is_refused_and_nothing_stored(
    buyer: User, client: Client
) -> None:
    """A query one character over the cap is refused with a 4xx, nothing stored."""
    client.force_login(buyer)
    over_cap = "a" * (QUERY_MAX_LENGTH + 1)

    resp = client.post(reverse("search:save-search"), {"query": over_cap})

    assert 400 <= resp.status_code < 500
    # Absence, not just the status code: no row may exist for this user.
    assert not SavedSearch.objects.filter(user=buyer).exists()


def test_fifty_thousand_char_query_cannot_be_stored_through_view(
    buyer: User, client: Client
) -> None:
    """A 50 000-character query cannot be stored through the view."""
    client.force_login(buyer)

    resp = client.post(reverse("search:save-search"), {"query": "x" * 50000})

    assert 400 <= resp.status_code < 500
    assert not SavedSearch.objects.filter(user=buyer).exists()


def test_model_refuses_over_cap_value_for_non_view_writer(buyer: User) -> None:
    """The model itself refuses an over-cap value, not only the view.

    This is the assertion that distinguishes a model bound from a view-only
    cap: a management command, the bot or the admin writing through the ORM is
    rejected by PostgreSQL's ``VARCHAR(200)``.
    """
    with pytest.raises(DataError):
        SavedSearch.objects.create(user=buyer, query="x" * 50000)


def test_stored_query_is_pii_redacted_at_write(buyer: User, client: Client) -> None:
    """A saved search stores none of a phone, an e-mail or a capitalised name."""
    client.force_login(buyer)
    raw = "Ivan Petrov +381641234567 ivan.petrov@example.com"

    resp = client.post(reverse("search:save-search"), {"query": raw})

    assert resp.status_code == 200
    stored = SavedSearch.objects.get(user=buyer).query or ""
    assert "381641234567" not in stored
    assert "ivan.petrov@example.com" not in stored
    assert "Ivan Petrov" not in stored


def test_redaction_never_lengthens_a_legal_query(buyer: User, client: Client) -> None:
    """Redaction cannot turn an at-cap legal query into an over-cap one.

    The stored value's length is bounded by the input's length, so the 200-char
    cap cannot be violated by the redaction step itself.
    """
    client.force_login(buyer)
    # At-cap but with a maskable phone: redaction shortens it, never lengthens.
    raw = ("+381641234567 " + "b" * 100).ljust(QUERY_MAX_LENGTH, "b")[:QUERY_MAX_LENGTH]
    assert len(raw) == QUERY_MAX_LENGTH

    resp = client.post(reverse("search:save-search"), {"query": raw})

    assert resp.status_code == 200
    stored = SavedSearch.objects.get(user=buyer).query or ""
    assert len(stored) <= len(raw)


def test_over_cap_value_cannot_reach_collect_alerts(buyer: User) -> None:
    """An over-cap value cannot reach send_alerts.Command._collect_alerts.

    Reachability only — no timing. The model refuses the write outright, so the
    ungated scheduler can never select an over-cap row in the first place.
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        with pytest.raises(DataError):
            SavedSearch.objects.create(user=buyer, query="x" * 50000)
    assert not SavedSearch.objects.filter(is_active=True).exists()

