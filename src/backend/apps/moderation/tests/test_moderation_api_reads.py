"""Tests for the ``GET /api/v1/moderation/queue/`` and ``…/review/{id}/`` reads (S2.5).

Browserless (``Client()``) coverage of the two staff moderation reads:

- **401 / 403 / 405 matrix** — anonymous → 401, non-staff session → 403, staff
  wrong-method → 405; every refusal carries **no** ``WWW-Authenticate`` header.
- **Queue priority-filter parity** — each ``PriorityFilter`` member (and the
  ``ALL`` sentinel / a missing / an unknown value mapping to *no* filter) yields
  exactly the ads the HTML queue iterates for the same query.
- **Pagination envelope** — the standard ``{page, per_page, total_count,
  results_truncated, results[], has_next}`` envelope, plus the
  ``selected_priority`` / ``priority_counts`` the HTML filter links render.
- **Review payload parity** — the JSON review payload carries the fields the
  review template renders for the same ad.
- **Uniform 404** — a missing id and an out-of-pair status answer the identical
  ``not_found`` problem document.
"""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from apps.ads.models import Ad, AdImage
from apps.core.enums import AdPriorityLevel, AdStatus, PriorityFilter
from apps.core.utils.problem import PROBLEM_CONTENT_TYPE
from apps.moderation.models import AdModerationPriority
from apps.users.models import User
from conftest import create_test_ad, make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

QUEUE_ENDPOINT = "/api/v1/moderation/queue/"
_QUEUE_HTML = "/moderation/queue/"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def staff_user() -> User:
    """A staff moderator (``role == ADMIN``)."""
    return make_user(telegram_id=900000510, is_staff=True)


@pytest.fixture
def non_staff_user() -> User:
    """An authenticated non-staff user."""
    return make_user(telegram_id=900000511)


def _queue_ad(
    seller: User,
    category,
    city,
    *,
    level: AdPriorityLevel,
    score: int,
    status: AdStatus = AdStatus.ON_MODERATION,
    title: str = "Queued Ad",
) -> Ad:
    """Create a queued ad with the requested ``AdModerationPriority`` values.

    A ``post_save`` signal on ``Ad`` already creates an ``AdModerationPriority``
    row when an ad enters ``ON_MODERATION`` (``apps/moderation/signals.py``), so
    this upserts the score/level on that row rather than inserting a second one
    (the FK is one-to-one). Pass ``status=ON_MODERATION_FAILED`` to create the
    ad without the signal firing.
    """
    ad = create_test_ad(seller, category, city, status=status, title=title)
    AdModerationPriority.objects.update_or_create(
        ad=ad,
        defaults={
            "base_score": score,
            "priority_level": level.value,
        },
    )
    return ad


def _staff_client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


# ---------------------------------------------------------------------------
# Auth matrix — 401 / 403 / 405, no WWW-Authenticate
# ---------------------------------------------------------------------------


class TestQueueAuthMatrix:
    """Staff-only queue read: 401 anon, 403 non-staff, 405 wrong method."""

    def test_anonymous_returns_401_json_no_challenge(self) -> None:
        response = Client().get(QUEUE_ENDPOINT)

        assert response.status_code == 401
        assert "WWW-Authenticate" not in response.headers

    def test_non_staff_returns_403(self, non_staff_user: User) -> None:
        response = _staff_client(non_staff_user).get(QUEUE_ENDPOINT)

        assert response.status_code == 403
        assert "WWW-Authenticate" not in response.headers

    def test_staff_wrong_method_returns_405(self, staff_user: User) -> None:
        response = _staff_client(staff_user).post(QUEUE_ENDPOINT)

        assert response.status_code == 405
        assert "WWW-Authenticate" not in response.headers

    def test_staff_get_returns_200(self, staff_user: User) -> None:
        response = _staff_client(staff_user).get(QUEUE_ENDPOINT)

        assert response.status_code == 200


class TestReviewAuthMatrix:
    """Staff-only review read: 401 anon, 403 non-staff, 405 wrong method."""

    def test_anonymous_returns_401_json_no_challenge(
        self, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
        response = Client().get(f"/api/v1/moderation/review/{ad.id}/")

        assert response.status_code == 401
        assert "WWW-Authenticate" not in response.headers

    def test_non_staff_returns_403(
        self, non_staff_user: User, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
        response = _staff_client(non_staff_user).get(
            f"/api/v1/moderation/review/{ad.id}/"
        )

        assert response.status_code == 403
        assert "WWW-Authenticate" not in response.headers

    def test_staff_wrong_method_returns_405(
        self, staff_user: User, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
        response = _staff_client(staff_user).post(
            f"/api/v1/moderation/review/{ad.id}/"
        )

        assert response.status_code == 405
        assert "WWW-Authenticate" not in response.headers


# ---------------------------------------------------------------------------
# Priority filter parity
# ---------------------------------------------------------------------------


class TestQueuePriorityFilterParity:
    """Each ``PriorityFilter`` value yields the HTML queue's ad set."""

    @pytest.fixture
    def queue_fixture(self, seller, category, city) -> dict:
        high = _queue_ad(
            seller, category, city, level=AdPriorityLevel.HIGH, score=90,
            title="High Ad",
        )
        med = _queue_ad(
            seller, category, city, level=AdPriorityLevel.MEDIUM, score=50,
            title="Med Ad",
        )
        low = _queue_ad(
            seller, category, city, level=AdPriorityLevel.LOW, score=10,
            title="Low Ad",
        )
        return {"high": high, "medium": med, "low": low}

    @pytest.mark.parametrize(
        "priority_value, expected_key",
        [
            (PriorityFilter.ALL.value, None),
            (PriorityFilter.HIGH.value, "high"),
            (PriorityFilter.MEDIUM.value, "medium"),
            (PriorityFilter.LOW.value, "low"),
        ],
    )
    def test_filter_matches_html_queue(
        self, staff_user, queue_fixture, priority_value, expected_key
    ) -> None:
        client = _staff_client(staff_user)

        json_ids = [
            r["id"]
            for r in client.get(
                QUEUE_ENDPOINT, {"priority": priority_value}
            ).json()["results"]
        ]
        html_ids = [
            a.id
            for a in client.get(
                _QUEUE_HTML, {"priority": priority_value}
            ).context["ads"]
        ]

        assert json_ids == html_ids
        if expected_key is not None:
            assert json_ids == [queue_fixture[expected_key].id]

    def test_missing_priority_maps_to_all(
        self, staff_user, queue_fixture
    ) -> None:
        client = _staff_client(staff_user)
        ids = [r["id"] for r in client.get(QUEUE_ENDPOINT).json()["results"]]
        assert set(ids) == {
            queue_fixture["high"].id,
            queue_fixture["medium"].id,
            queue_fixture["low"].id,
        }

    def test_unknown_priority_maps_to_all(
        self, staff_user, queue_fixture
    ) -> None:
        client = _staff_client(staff_user)
        ids = [
            r["id"]
            for r in client.get(
                QUEUE_ENDPOINT, {"priority": "not_a_level"}
            ).json()["results"]
        ]
        assert len(ids) == 3


# ---------------------------------------------------------------------------
# Pagination envelope + counts
# ---------------------------------------------------------------------------


class TestQueueEnvelope:
    """The standard envelope plus ``selected_priority`` / ``priority_counts``."""

    def test_envelope_and_counts(self, staff_user, seller, category, city) -> None:
        _queue_ad(seller, category, city, level=AdPriorityLevel.HIGH, score=90)
        _queue_ad(seller, category, city, level=AdPriorityLevel.HIGH, score=80)
        _queue_ad(seller, category, city, level=AdPriorityLevel.LOW, score=5)

        payload = _staff_client(staff_user).get(QUEUE_ENDPOINT).json()

        assert payload["page"] == 1
        assert payload["per_page"] == 24
        assert payload["total_count"] == 3
        assert payload["results_truncated"] is False
        assert payload["has_next"] is False
        assert payload["selected_priority"] == PriorityFilter.ALL.value
        assert payload["priority_counts"] == {"high": 2, "medium": 0, "low": 1}

    def test_non_queue_ads_excluded(self, staff_user, seller, category, city) -> None:
        _queue_ad(seller, category, city, level=AdPriorityLevel.HIGH, score=90)
        create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        payload = _staff_client(staff_user).get(QUEUE_ENDPOINT).json()
        assert payload["total_count"] == 1

    def test_ordering_by_base_score_desc(
        self, staff_user, seller, category, city
    ) -> None:
        low = _queue_ad(seller, category, city, level=AdPriorityLevel.LOW, score=10)
        high = _queue_ad(seller, category, city, level=AdPriorityLevel.HIGH, score=99)

        ids = [
            r["id"]
            for r in _staff_client(staff_user).get(QUEUE_ENDPOINT).json()["results"]
        ]
        assert ids == [high.id, low.id]


# ---------------------------------------------------------------------------
# Review payload parity
# ---------------------------------------------------------------------------


class TestReviewPayload:
    """The JSON review payload carries the fields the template renders."""

    def test_review_payload_matches_context(
        self, staff_user, seller, category, city
    ) -> None:
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.ON_MODERATION,
            title="Review Me",
            description="Please review this ad",
        )
        AdImage.objects.create(ad=ad, image="uuid-a.jpg", position=0)

        client = _staff_client(staff_user)
        payload = client.get(f"/api/v1/moderation/review/{ad.id}/").json()

        # The HTML context holds the same Ad instance; the JSON mirrors its
        # template-visible fields.
        html_ad = client.get(f"/moderation/review/{ad.id}/").context["ad"]
        assert payload["id"] == html_ad.id
        assert payload["title"] == html_ad.get_title()
        assert payload["status"] == html_ad.status
        assert payload["status_display"] == html_ad.get_status_display()
        assert payload["description"] == html_ad.get_description()
        assert payload["telegram_id"] == html_ad.user.telegram_id
        assert payload["category"]["slug"] == html_ad.category.slug
        assert payload["city"]["slug"] == html_ad.city.slug
        assert payload["image_urls"] == [ad.images.first().image_url]

    def test_review_localizes_names_and_description(
        self, staff_user, seller, category, city
    ) -> None:
        category.name_i18n = {"ru": "Транспорт", "bs": "Prevoz"}
        category.save(update_fields=["name_i18n"])
        city.name_i18n = {"ru": "Тестград", "bs": "Testgrad"}
        city.save(update_fields=["name_i18n"])
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        payload = _staff_client(staff_user).get(
            f"/api/v1/moderation/review/{ad.id}/?lang=bs"
        ).json()

        assert payload["category"]["name"] == "Prevoz"
        assert payload["city"]["name"] == "Testgrad"


# ---------------------------------------------------------------------------
# Uniform 404
# ---------------------------------------------------------------------------


class TestReviewUniformNotFound:
    """A missing id and an out-of-pair status answer the identical 404 problem."""

    def _not_found(self, client: Client, ad_id: int):
        return client.get(f"/api/v1/moderation/review/{ad_id}/")

    def test_missing_id_uniform_problem(self, staff_user) -> None:
        response = self._not_found(_staff_client(staff_user), 999999)

        assert response.status_code == 404
        assert response.headers.get("Content-Type") == PROBLEM_CONTENT_TYPE
        payload = response.json()
        assert payload["type"] == "not_found"
        assert payload["status"] == 404

    def test_out_of_pair_status_same_body(
        self, staff_user, seller, category, city
    ) -> None:
        published = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = _staff_client(staff_user)

        missing = self._not_found(client, 999999)
        out_of_pair = self._not_found(client, published.id)

        assert out_of_pair.status_code == 404
        assert out_of_pair.json() == missing.json()

    def test_on_moderation_failed_is_reviewable(
        self, staff_user, seller, category, city
    ) -> None:
        ad = create_test_ad(
            seller, category, city, status=AdStatus.ON_MODERATION_FAILED
        )
        response = self._not_found(_staff_client(staff_user), ad.id)
        assert response.status_code == 200


def test_moderation_api_namespace_reverses() -> None:
    """The route namespace resolves without colliding with the HTML one."""
    assert reverse("moderation_api:queue") == "/api/v1/moderation/queue/"
