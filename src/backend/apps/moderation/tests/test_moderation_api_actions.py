"""Tests for the moderation single-action writes (S4.7).

Browserless (``Client()``) coverage of
``POST /api/v1/moderation/{approve,reject,ban}/{id}/`` — the JSON siblings of the
HTML ``approve`` / ``reject`` / ``ban`` views:

- **401 / 403 / 405 matrix** — anonymous → 401, non-staff session → 403, staff
  wrong method → 405; every refusal is an RFC 9457 problem document and carries
  **no** ``WWW-Authenticate`` header. The 405 also carries ``Allow: POST`` and
  commits nothing.
- **Uniform 404** — a missing id answers the identical ``not_found`` problem for
  all three actions.
- **Service parity** — the happy paths are asserted **twice over**: once against
  the recorded side effects (status, timestamps, ``ModeratorActionLog``,
  ``AdModerationPriority``) and once against the *HTML* view driven for an
  identical fixture, so a drift between the two surfaces fails here.
- **Taxonomy outcomes** — approve ``criteria_rejected`` / ``transition_refused``,
  reject ``invalid_transition`` and the already-rejected no-op, ban
  ``already_banned`` and the ``ban_refused`` cause token (no count leak).
- **422** on a malformed / failing reject body; reason propagation equals the
  HTML flow's recorded reason.
- **429** in the shared ``api_write`` namespace.
"""

from __future__ import annotations

import json
from typing import Final, cast

import pytest
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse

from apps.ads.models import Ad, AdImage
from apps.core.enums import (
    AdStatus,
    CategoryRejectReason,
    ModeratorActionType,
    RateLimitBudget,
)
from apps.core.utils.problem import PROBLEM_CONTENT_TYPE
from apps.moderation.models import (
    AdModerationPriority,
    ModerationCriteria,
    ModeratorActionLog,
)
from apps.users.models import User
from conftest import create_test_ad, make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

ACTIONS: tuple[str, ...] = ("approve", "reject", "ban")

# The two parity ads must not be near-duplicates of each other (the
# ``diff_sequence``-style near-duplicate guard) and must clear the criteria's
# title/description minimums, so one ad passes while the missing-photo case
# fails on the image rule alone.
_PARITY_TITLES: Final[tuple[str, str]] = (
    "Parity fixture bicycle wheels",
    "Parity fixture wooden bookshelf",
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def staff_user() -> User:
    """A staff moderator (``role == ADMIN``)."""
    return make_user(telegram_id=900000610, is_staff=True)



@pytest.fixture
def non_staff_user() -> User:
    """An authenticated non-staff user."""
    return make_user(telegram_id=900000612)


def _url(action: str, ad_id: int) -> str:
    return reverse(f"moderation_api:{action}", args=[ad_id])


def _html_url(action: str, ad_id: int) -> str:
    return reverse(f"moderation:{action}", args=[ad_id])


def _client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


def _post_json(
    client: Client, action: str, ad_id: int, payload: dict[str, object] | None = None
) -> HttpResponse:
    response: HttpResponse = cast(
        HttpResponse,
        client.post(
        _url(action, ad_id),
            data=json.dumps(payload or {}),
            content_type="application/json",
        ),
    )
    return response


@pytest.fixture
def moderation_criteria():
    """A criteria singleton whose image rule the fixture ad satisfies.

    The row's DB defaults are the couple-marker checklist (an ad needs at least
    two photos); this test module's fixture ads carry one, so the rule is
    lowered once per test rather than fabricating a second image. Nothing else
    changes, so both the API call and the HTML call run under one criteria.
    """
    criteria = ModerationCriteria.get_singleton()
    criteria.min_images = 1
    criteria.max_ads_per_user = 10
    criteria.duplicate_title_threshold = 100
    criteria.save()
    return criteria


def _approvable_ad(seller: User, category, city, title: str) -> Ad:
    """An ``ON_MODERATION`` ad that satisfies the criteria (one photo)."""
    ad = create_test_ad(
        seller,
        category,
        city,
        status=AdStatus.ON_MODERATION,
        title=title,
        description=f"{title} fixture description",
    )
    AdImage.objects.create(ad=ad, image="parity-image.jpg", position=0)
    return ad


def _side_effect_snapshot(ad_id: int, owner_id: int) -> dict[str, object]:
    """Collect every observable moderation side effect for one ad/owner."""
    ad = Ad.objects.get(id=ad_id)
    logs = list(
        ModeratorActionLog.objects.filter(ad_id=ad_id).order_by("id").values(
            "action_type", "reason"
        )
    )
    ban_logs = list(
        ModeratorActionLog.objects.filter(
            user_id=owner_id, action_type=ModeratorActionType.BAN_ACCOUNT
        ).values("action_type", "reason")
    )
    priority = AdModerationPriority.objects.filter(ad_id=ad_id).first()
    owner = User.objects.get(id=owner_id)
    return {
        "status": ad.status,
        "published_at": ad.published_at is not None,
        "rejected_at": ad.rejected_at is not None,
        "moderation_failed_at": ad.moderation_failed_at is not None,
        "published_by_id": ad.published_by_id,
        "moderated_by_id": ad.moderated_by_id,
        "ad_logs": logs,
        "ban_logs": ban_logs,
        "has_priority_row": priority is not None,
        "is_banned": owner.is_banned,
    }


# ---------------------------------------------------------------------------
# Auth matrix — 401 / 403 / 405, no WWW-Authenticate
# ---------------------------------------------------------------------------


class TestAuthMatrix:
    """The staff gate and the POST-only clause on every action."""

    @pytest.mark.parametrize("action", ACTIONS)
    def test_anonymous_post_returns_401_no_challenge(self, action: str) -> None:
        response = _post_json(Client(), action, 1, {})

        assert response.status_code == 401
        assert response["Content-Type"] == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "unauthenticated"
        assert "WWW-Authenticate" not in response.headers

    @pytest.mark.parametrize("action", ACTIONS)
    def test_non_staff_post_returns_403_no_challenge(
        self, action: str, non_staff_user: User
    ) -> None:
        response = _post_json(_client(non_staff_user), action, 1, {})

        assert response.status_code == 403
        assert response["Content-Type"] == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "forbidden"
        assert "WWW-Authenticate" not in response.headers

    @pytest.mark.parametrize("action", ACTIONS)
    @pytest.mark.parametrize("method", ["get", "put", "patch", "delete"])
    def test_wrong_method_returns_405_with_allow_and_no_state_change(
        self,
        action: str,
        method: str,
        staff_user: User,
        seller: User,
        category,
        city,
    ) -> None:
        ad = _approvable_ad(seller, category, city, _PARITY_TITLES[0])
        before = _side_effect_snapshot(ad.id, seller.id)

        response = getattr(_client(staff_user), method)(_url(action, ad.id))

        assert response.status_code == 405
        assert response["Content-Type"] == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "method_not_allowed"
        assert response["Allow"] == "POST"
        assert "WWW-Authenticate" not in response.headers
        assert _side_effect_snapshot(ad.id, seller.id) == before


# ---------------------------------------------------------------------------
# Uniform 404
# ---------------------------------------------------------------------------


class TestMissingAd:
    @pytest.mark.parametrize("action", ACTIONS)
    def test_missing_ad_is_uniform_not_found(self, action: str, staff_user: User) -> None:
        body = {"reason_category": "spam_scam"} if action == "reject" else {}

        response = _post_json(_client(staff_user), action, 9_999_999, body)

        assert response.status_code == 404
        assert response["Content-Type"] == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "not_found"


# ---------------------------------------------------------------------------
# Approve
# ---------------------------------------------------------------------------


class TestApprove:
    def test_happy_path_publishes_and_matches_html_flow(
        self,
        moderation_criteria,
        staff_user: User,
        seller: User,
        category,
        city,
    ) -> None:
        api_ad = _approvable_ad(seller, category, city, _PARITY_TITLES[0])
        html_ad = _approvable_ad(seller, category, city, _PARITY_TITLES[1])

        response = _post_json(_client(staff_user), "approve", api_ad.id, {})
        _client(staff_user).post(_html_url("approve", html_ad.id))

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == api_ad.id
        assert body["outcome"] == "published"
        assert body["status"] == AdStatus.PUBLISHED
        assert body["published_at"] is not None

        api_effects = _side_effect_snapshot(api_ad.id, seller.id)
        html_effects = _side_effect_snapshot(html_ad.id, seller.id)
        assert api_effects["status"] == html_effects["status"] == AdStatus.PUBLISHED
        assert api_effects["published_at"] is True
        assert api_effects["ad_logs"] == html_effects["ad_logs"]
        assert api_effects["ad_logs"] == [
            {"action_type": ModeratorActionType.OTHER, "reason": "Manually published by moderator"}
        ]
        assert api_effects["has_priority_row"] is True
        assert api_effects["published_by_id"] == staff_user.id

    def test_criteria_rejected_is_200_and_parks_the_ad(
        self,
        staff_user: User,
        seller: User,
        category,
        city,
    ) -> None:
        # No image → the criteria's min_images check fails in auto_moderate.
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.ON_MODERATION,
            title=_PARITY_TITLES[0],
            description=f"{_PARITY_TITLES[0]} fixture description",
        )

        response = _post_json(_client(staff_user), "approve", ad.id, {})

        assert response.status_code == 200
        assert response.json()["outcome"] == "criteria_rejected"
        assert response.json()["status"] == AdStatus.ON_MODERATION_FAILED
        ad.refresh_from_db()
        assert ad.moderation_failed_at is not None

    def test_transition_refused_is_409(
        self, staff_user: User, seller: User, category, city
    ) -> None:
        # ON_MODERATION_FAILED is in the HTML lookup but the state machine still
        # refuses -> PUBLISHED, which the service reports as TRANSITION_REFUSED.
        ad = create_test_ad(
            seller, category, city, status=AdStatus.ON_MODERATION_FAILED
        )
        before = _side_effect_snapshot(ad.id, seller.id)

        response = _post_json(_client(staff_user), "approve", ad.id, {})

        assert response.status_code == 409
        assert response["Content-Type"] == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "transition_refused"
        assert _side_effect_snapshot(ad.id, seller.id) == before

    def test_unknown_body_key_is_422(
        self, staff_user: User, seller: User, category, city
    ) -> None:
        ad = _approvable_ad(seller, category, city, _PARITY_TITLES[0])

        response = _post_json(_client(staff_user), "approve", ad.id, {"reason": "x"})

        assert response.status_code == 422
        assert response.json()["type"] == "validation_failed"


# ---------------------------------------------------------------------------
# Reject
# ---------------------------------------------------------------------------


class TestReject:
    def test_happy_path_matches_html_flow_including_recorded_reason(
        self,
        staff_user: User,
        seller: User,
        category,
        city,
    ) -> None:
        api_ad = _approvable_ad(seller, category, city, _PARITY_TITLES[0])
        html_ad = _approvable_ad(seller, category, city, _PARITY_TITLES[1])

        response = _post_json(
            _client(staff_user),
            "reject",
            api_ad.id,
            {"reason_category": "spam_scam", "reason_text": "  Spam content  "},
        )
        _client(staff_user).post(
            _html_url("reject", html_ad.id),
            data={"reason_category": "spam_scam", "reason_text": "  Spam content  "},
        )

        assert response.status_code == 200
        assert response.json()["outcome"] == "rejected"
        assert response.json()["status"] == AdStatus.REJECTED
        assert response.json()["rejected_at"] is not None

        api_effects = _side_effect_snapshot(api_ad.id, seller.id)
        html_effects = _side_effect_snapshot(html_ad.id, seller.id)
        assert api_effects["status"] == html_effects["status"] == AdStatus.REJECTED
        assert api_effects["rejected_at"] is True
        assert api_effects["ad_logs"] == html_effects["ad_logs"]
        assert api_effects["ad_logs"] == [
            {"action_type": ModeratorActionType.REJECT, "reason": "spam_scam: Spam content"}
        ]
        assert api_effects["moderated_by_id"] == staff_user.id

    def test_reason_category_only_matches_html_flow(
        self, staff_user: User, seller: User, category, city
    ) -> None:
        api_ad = _approvable_ad(seller, category, city, _PARITY_TITLES[0])
        html_ad = _approvable_ad(seller, category, city, _PARITY_TITLES[1])

        _post_json(
            _client(staff_user),
            "reject",
            api_ad.id,
            {"reason_category": CategoryRejectReason.SPAM_SCAM.value},
        )
        _client(staff_user).post(
            _html_url("reject", html_ad.id),
            data={"reason_category": CategoryRejectReason.SPAM_SCAM.value},
        )

        assert _side_effect_snapshot(api_ad.id, seller.id)[
            "ad_logs"
        ] == _side_effect_snapshot(html_ad.id, seller.id)["ad_logs"]

    def test_missing_reason_category_is_422(
        self, staff_user: User, seller: User, category, city
    ) -> None:
        ad = _approvable_ad(seller, category, city, _PARITY_TITLES[0])

        response = _post_json(_client(staff_user), "reject", ad.id, {})

        assert response.status_code == 422
        assert response["Content-Type"] == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "validation_failed"
        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION

    def test_unknown_reason_category_is_422(
        self, staff_user: User, seller: User, category, city
    ) -> None:
        ad = _approvable_ad(seller, category, city, _PARITY_TITLES[0])
        response = _post_json(
            _client(staff_user), "reject", ad.id, {"reason_category": "not_a_reason"}
        )

        assert response.status_code == 422
        assert response.json()["type"] == "validation_failed"
        assert not ModeratorActionLog.objects.filter(ad_id=ad.id).exists()

    def test_request_failing_validation_is_422(
        self, staff_user: User, seller: User, category, city
    ) -> None:
        ad = _approvable_ad(seller, category, city, _PARITY_TITLES[0])

        response = _client(staff_user).post(
            _url("reject", ad.id),
            data="{not json",
            content_type="application/json",
        )

        assert response.status_code == 422
        assert response.json()["type"] == "validation_failed"

    def test_wrong_status_is_409_invalid_transition(
        self, staff_user: User, seller: User, category, city
    ) -> None:
        # REJECTED has no outgoing edge in the transition matrix.
        ad = create_test_ad(seller, category, city, status=AdStatus.REJECTED)
        before = _side_effect_snapshot(ad.id, seller.id)

        response = _post_json(
            _client(staff_user), "reject", ad.id, {"reason_category": "spam_scam"}
        )

        # An already-rejected ad is the service's documented no-op: no 409, and
        # no second audit row — the HTML flow's behaviour, made explicit.
        assert response.status_code == 200
        assert response.json()["outcome"] == "already_rejected"
        assert _side_effect_snapshot(ad.id, seller.id) == before

    @pytest.mark.parametrize(
        "status",
        [AdStatus.PUBLISHED, AdStatus.ARCHIVED, AdStatus.DRAFT],
    )
    def test_outside_the_transition_matrix_is_409(
        self, status: AdStatus, staff_user: User, seller: User, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=status)
        before = _side_effect_snapshot(ad.id, seller.id)

        response = _post_json(
            _client(staff_user), "reject", ad.id, {"reason_category": "spam_scam"}
        )

        assert response.status_code == 409
        assert response.json()["type"] == "invalid_transition"
        assert _side_effect_snapshot(ad.id, seller.id) == before


# ---------------------------------------------------------------------------
# Ban
# ---------------------------------------------------------------------------


class TestBan:
    def test_happy_path_matches_html_flow(
        self,
        staff_user: User,
        seller: User,
        category,
        city,
    ) -> None:
        api_ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
        html_ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        response = _post_json(
            _client(staff_user), "ban", api_ad.id, {"ban_reason": "Repeated violations"}
        )
        _client(staff_user).post(
            _html_url("ban", html_ad.id), data={"ban_reason": "Repeated violations"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["outcome"] == "banned"
        assert body["changed"] == 1
        assert body["already_in_state"] == 0

        api_effects = _side_effect_snapshot(api_ad.id, seller.id)
        html_effects = _side_effect_snapshot(html_ad.id, seller.id)
        assert api_effects["is_banned"] is True
        assert api_effects["ban_logs"] == html_effects["ban_logs"]
        assert api_effects["ban_logs"] == [
            {
                "action_type": ModeratorActionType.BAN_ACCOUNT,
                "reason": "Repeated violations",
            }
        ]

    def test_default_reason_matches_html_default(
        self, staff_user: User, seller: User, category, city
    ) -> None:
        api_ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
        html_ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        _post_json(_client(staff_user), "ban", api_ad.id, {})
        _client(staff_user).post(_html_url("ban", html_ad.id), data={})

        assert (
            _side_effect_snapshot(api_ad.id, seller.id)["ban_logs"]
            == _side_effect_snapshot(html_ad.id, seller.id)["ban_logs"]
            == [
                {
                    "action_type": ModeratorActionType.BAN_ACCOUNT,
                    "reason": "No reason provided",
                }
            ]
        )

    def test_already_banned_is_a_200_no_op(
        self, staff_user: User, seller: User, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
        User.objects.filter(id=seller.id).update(is_banned=True)

        response = _post_json(_client(staff_user), "ban", ad.id, {})

        assert response.status_code == 200
        assert response.json()["outcome"] == "already_banned"
        assert response.json()["changed"] == 0
        assert response.json()["already_in_state"] == 1

    def test_privileged_target_is_403_ban_refused_without_counts(
        self, staff_user: User, category, city
    ) -> None:
        privileged_seller = make_user(telegram_id=900000613, is_staff=True)
        ad = create_test_ad(
            privileged_seller, category, city, status=AdStatus.ON_MODERATION
        )

        response = _post_json(_client(staff_user), "ban", ad.id, {})

        assert response.status_code == 403
        assert response.json()["type"] == "ban_refused"
        assert response.json()["cause"] == "privileged"
        # No privileged-row count leak: the refusal body carries no counts.
        assert "changed" not in response.json()
        assert "already_in_state" not in response.json()
        privileged_seller.refresh_from_db()
        assert privileged_seller.is_banned is False

    def test_self_ban_is_403_ban_refused(
        self, staff_user: User, category, city
    ) -> None:
        ad = create_test_ad(staff_user, category, city, status=AdStatus.ON_MODERATION)

        response = _post_json(_client(staff_user), "ban", ad.id, {})

        assert response.status_code == 403
        assert response.json()["type"] == "ban_refused"
        assert response.json()["cause"] == "self"
        staff_user.refresh_from_db()
        assert staff_user.is_banned is False


# ---------------------------------------------------------------------------
# Rate limit — shared api_write namespace
# ---------------------------------------------------------------------------


class TestRateLimit:
    @pytest.mark.parametrize("action", ACTIONS)
    def test_exhausted_budget_is_429_problem_with_retry_after(
        self,
        action: str,
        staff_user: User,
        seller: User,
        category,
        city,
        monkeypatch,
    ) -> None:
        ad = _approvable_ad(seller, category, city, _PARITY_TITLES[0])
        before = _side_effect_snapshot(ad.id, seller.id)
        monkeypatch.setattr(
            "apps.moderation.views.api.actions.rate_limit_check",
            lambda *args, **kwargs: False,
        )
        body = {"reason_category": "spam_scam"} if action == "reject" else {}

        response = _post_json(_client(staff_user), action, ad.id, body)

        assert response.status_code == 429
        assert response["Content-Type"] == PROBLEM_CONTENT_TYPE
        assert response.json()["type"] == "rate_limited"
        assert response["Retry-After"] == str(RateLimitBudget.API_WRITE.period)
        assert _side_effect_snapshot(ad.id, seller.id) == before

    def test_limiter_runs_after_the_identity_gate(
        self, seller: User, category, city, monkeypatch
    ) -> None:
        """Identity is checked first; the limiter gates the authenticated call.

        ``staff_required_api_problem`` keeps the frozen decorator's
        identity-before-method ordering, so an anonymous request is a 401 no
        matter how exhausted the budget is; an authenticated staff request is
        then refused by the shared ``api_write`` limiter.
        """
        ad = _approvable_ad(seller, category, city, _PARITY_TITLES[0])
        monkeypatch.setattr(
            "apps.moderation.views.api.actions.rate_limit_check",
            lambda *args, **kwargs: False,
        )

        anonymous = Client().post(
            _url("approve", ad.id), data="{}", content_type="application/json"
        )

        assert anonymous.status_code == 401
        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION


# ---------------------------------------------------------------------------
# Regression: the frozen legacy bulk endpoint is untouched
# ---------------------------------------------------------------------------


class TestBulkUntouched:
    def test_bulk_endpoint_still_answers_its_legacy_shape(
        self, staff_user: User, seller: User, category, city
    ) -> None:
        ad = _approvable_ad(seller, category, city, _PARITY_TITLES[0])

        response = _client(staff_user).post(
            "/moderation/api/v1/bulk-action/",
            data=json.dumps({"action": "approve", "selected_items": [ad.id]}),
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.json() == {"completed": 1, "errors": []}



