"""
View-layer tests for moderation review actions (TST-004).

Covers:
- moderation_review: staff-only detail view for ads in moderation queue
- approve_ad: POST-only staff action that transitions ad to PUBLISHED
- reject_ad: POST-only staff action that transitions ad to REJECTED
- ban_user: POST-only staff action that bans the ad owner
- Non-staff users get 404 for all moderation views

Previously shadowed as ``apps/moderation/tests.py`` (the ``tests/`` package
with ``__init__.py`` took the ``tests`` module name, so ``tests.py`` was
silently skipped during pytest collection). Migrated here so the view-layer
coverage that the active ``test_admin_actions.py`` / ``test_priority*.py``
files do NOT provide is actually exercised in CI.
"""

import inspect

import pytest
from django.test import Client
from django.urls import reverse

from apps.ads.models import Ad, AdImage
from apps.categories.models import Category
from apps.core.enums import AdStatus, CategoryRejectReason, UserRole
from apps.locations.models import City
from apps.moderation.models import ModeratorActionLog
from apps.users.models import User
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def staff_user() -> User:
    """Create a staff user for moderation tests."""
    return User.objects.create(
        telegram_id=900000040,
        chat_id=900000040,
        password="x",
        is_staff=True,
    )


@pytest.fixture
def regular_user() -> User:
    """Create a regular (non-staff) user for access tests."""
    return User.objects.create(
        telegram_id=900000041,
        chat_id=900000041,
        password="x",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_ad_with_image(
    user: User,
    category: Category,
    city: City,
    *,
    status: AdStatus = AdStatus.ON_MODERATION,
    **kwargs,
) -> tuple[Ad, AdImage]:
    """Create an ad with one image.

    ``status`` is explicit (not forwarded silently) so this wrapper cannot
    fabricate a state production never holds.
    """
    ad = create_test_ad(user, category, city, status=status, **kwargs)
    ad_image = AdImage.objects.create(
        ad=ad,
        image="test-uuid-image-key.jpg",
    )
    return ad, ad_image


# ---------------------------------------------------------------------------
# Tests: Staff access control
# ---------------------------------------------------------------------------


class TestModerationStaffAccess:
    """All moderation views require staff access."""

    @pytest.fixture
    def ad_on_moderation(
        self,
        seller: User,
        category: Category,
        city: City,
    ) -> Ad:
        return create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

    def test_anonymous_user_gets_404(
        self,
        ad_on_moderation: Ad,
    ) -> None:
        """Anonymous users get 404 for moderation review."""
        client = Client()
        response = client.get(f"/moderation/review/{ad_on_moderation.id}/")
        assert response.status_code == 404

    def test_regular_user_gets_404(
        self,
        regular_user: User,
        ad_on_moderation: Ad,
    ) -> None:
        """Non-staff users get 404 for moderation review."""
        client = Client()
        client.force_login(regular_user)
        response = client.get(f"/moderation/review/{ad_on_moderation.id}/")
        assert response.status_code == 404

    def test_staff_required_accepts_staff_user(
        self,
        staff_user: User,
        ad_on_moderation: Ad,
    ) -> None:
        """@staff_required accepts an is_staff=True user (UserRole.ADMIN)."""
        assert staff_user.role == UserRole.ADMIN
        client = Client()
        client.force_login(staff_user)
        response = client.get(f"/moderation/review/{ad_on_moderation.id}/")
        assert response.status_code == 200

    def test_staff_required_rejects_non_staff_user(
        self,
        regular_user: User,
        ad_on_moderation: Ad,
    ) -> None:
        """@staff_required rejects an authenticated is_staff=False user (UserRole.SELLER)."""
        assert regular_user.role == UserRole.SELLER
        client = Client()
        client.force_login(regular_user)
        response = client.get(f"/moderation/review/{ad_on_moderation.id}/")
        assert response.status_code == 404

    def test_approve_regular_user_gets_404(
        self,
        regular_user: User,
        ad_on_moderation: Ad,
    ) -> None:
        """Non-staff users get 404 for approve action."""
        client = Client()
        client.force_login(regular_user)
        response = client.post(f"/moderation/approve/{ad_on_moderation.id}/")
        assert response.status_code == 404

    def test_reject_regular_user_gets_404(
        self,
        regular_user: User,
        ad_on_moderation: Ad,
    ) -> None:
        """Non-staff users get 404 for reject action."""
        client = Client()
        client.force_login(regular_user)
        response = client.post(f"/moderation/reject/{ad_on_moderation.id}/")
        assert response.status_code == 404

    def test_ban_regular_user_gets_404(
        self,
        regular_user: User,
        ad_on_moderation: Ad,
    ) -> None:
        """Non-staff users get 404 for ban action."""
        client = Client()
        client.force_login(regular_user)
        response = client.post(f"/moderation/ban/{ad_on_moderation.id}/")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Tests: moderation_review
# ---------------------------------------------------------------------------


class TestModerationReviewView:
    """moderation_review view shows ad details for staff."""

    def test_staff_can_view_review_page(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """Staff users can view the moderation review page."""
        ad, _ = _create_ad_with_image(
            seller, category, city, status=AdStatus.ON_MODERATION
        )

        client = Client()
        client.force_login(staff_user)
        response = client.get(f"/moderation/review/{ad.id}/")

        assert response.status_code == 200
        assert response.context["ad"] is not None
        assert response.context["ad"].id == ad.id

    def test_review_returns_404_for_non_moderation_status(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """Review page returns 404 for ads not in ON_MODERATION or ON_MODERATION_FAILED."""
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        client = Client()
        client.force_login(staff_user)
        response = client.get(f"/moderation/review/{ad.id}/")

        assert response.status_code == 404

    def test_review_returns_404_for_nonexistent_ad(
        self,
        staff_user: User,
    ) -> None:
        """Review page returns 404 for non-existent ad."""
        client = Client()
        client.force_login(staff_user)
        response = client.get("/moderation/review/99999/")

        assert response.status_code == 404

    def test_review_includes_related_objects(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """Review page includes user, category, city, and images in context."""
        ad, ad_image = _create_ad_with_image(
            seller, category, city, status=AdStatus.ON_MODERATION
        )

        client = Client()
        client.force_login(staff_user)
        response = client.get(f"/moderation/review/{ad.id}/")

        assert response.status_code == 200
        ctx_ad = response.context["ad"]
        # Check that related objects are prefetched
        assert ctx_ad.user is not None
        assert ctx_ad.category is not None
        assert ctx_ad.city is not None

    def test_review_renders_localized_category_name(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """Review page renders category/city names in the selected UI language."""
        category.name_i18n = {"ru": "Транспорт", "bs": "Prevoz"}
        category.save(update_fields=["name_i18n"])
        city.name_i18n = {"ru": "Тестград", "bs": "Testgrad"}
        city.save(update_fields=["name_i18n"])

        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)

        # Bosnian render
        response_bs = client.get(f"/moderation/review/{ad.id}/?lang=bs")
        assert response_bs.status_code == 200
        content_bs = response_bs.content.decode("utf-8")
        assert "Prevoz" in content_bs
        assert "Testgrad" in content_bs
        assert "Транспорт" not in content_bs

        # Russian render
        response_ru = client.get(f"/moderation/review/{ad.id}/?lang=ru")
        assert response_ru.status_code == 200
        content_ru = response_ru.content.decode("utf-8")
        assert "Транспорт" in content_ru
        assert "Тестград" in content_ru
        assert "Prevoz" not in content_ru


# ---------------------------------------------------------------------------
# Tests: review page URL contract (NF-1)
# ---------------------------------------------------------------------------


class TestModerationReviewUrls:
    """The review template targets absolute named URLs from both render origins.

    NF-1: the template previously used ``../``-relative references, which
    resolved one path segment too deep at the trailing-slash review URL. Every
    reference is now a named ``{% url %}`` tag, so the targets are identical
    from ``/moderation/review/<id>/`` and from the B-4 invalid-reason
    re-render origin ``/moderation/reject/<id>/``. The assertions build the
    expected URLs with ``reverse()`` — never hardcoded ``/moderation/...``.
    """

    def _expected_targets(self, ad: Ad) -> dict[str, str]:
        """The five absolute targets the review template must render."""
        return {
            "approve": reverse("moderation:approve", args=[ad.id]),
            "reject": reverse("moderation:reject", args=[ad.id]),
            "ban": reverse("moderation:ban", args=[ad.id]),
            "queue": reverse("moderation:queue"),
        }

    def _assert_review_targets(self, content: str, ad: Ad) -> None:
        """Assert all five action/href attributes carry the named-URL targets.

        The two approve forms live in mutually exclusive status blocks
        (``on_moderation`` / ``on_moderation_failed``), so exactly one renders
        per page.
        """
        targets = self._expected_targets(ad)
        assert content.count(f'action="{targets["approve"]}"') == 1
        assert f'action="{targets["reject"]}"' in content
        assert f'action="{targets["ban"]}"' in content
        assert f'href="{targets["queue"]}"' in content

    def test_review_renders_named_urls_for_on_moderation_ad(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """Both approve forms, the modals and the back link use named URLs."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        response = client.get(reverse("moderation:review", args=[ad.id]))

        assert response.status_code == 200
        self._assert_review_targets(response.content.decode("utf-8"), ad)

    def test_review_renders_named_urls_for_on_moderation_failed_ad(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """The on_moderation_failed approve form also uses the named URL."""
        ad = create_test_ad(
            seller, category, city, status=AdStatus.ON_MODERATION_FAILED
        )

        client = Client()
        client.force_login(staff_user)
        response = client.get(reverse("moderation:review", args=[ad.id]))

        assert response.status_code == 200
        self._assert_review_targets(response.content.decode("utf-8"), ad)

    def test_invalid_reason_rerender_keeps_named_urls(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """The B-4 invalid-reason re-render origin keeps the absolute targets."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        response = client.post(
            reverse("moderation:reject", args=[ad.id]),
            data={"reason_category": "not_a_reason", "reason_text": "My note"},
        )

        assert response.status_code == 200
        self._assert_review_targets(response.content.decode("utf-8"), ad)


# ---------------------------------------------------------------------------
# Tests: approve_ad
# ---------------------------------------------------------------------------


class TestApproveAdView:
    """approve_ad view transitions ad to PUBLISHED."""

    def test_approve_transitions_to_published(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """POST to approve_ad transitions ad from ON_MODERATION to PUBLISHED."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
        AdImage.objects.create(ad=ad, image="test-image.jpg", position=0)

        client = Client()
        client.force_login(staff_user)
        response = client.post(f"/moderation/approve/{ad.id}/")

        assert response.status_code == 302  # Redirect to admin change page

        # Verify ad state
        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED
        assert ad.published_at is not None
        assert ad.published_by_id == staff_user.id

    def test_approve_creates_moderation_log(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """approve_ad creates a ModeratorActionLog entry."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
        AdImage.objects.create(ad=ad, image="test-image.jpg", position=0)

        client = Client()
        client.force_login(staff_user)
        client.post(f"/moderation/approve/{ad.id}/")

        # Verify moderation log
        log_entries = ModeratorActionLog.objects.filter(ad_id=ad.id)
        assert log_entries.exists()

    def test_approve_requires_post(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """GET to approve_ad returns 405 Method Not Allowed."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        response = client.get(f"/moderation/approve/{ad.id}/")

        # @require_POST ensures GET returns 405 and the ad is not modified
        assert response.status_code == 405

        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION

    def test_approve_non_moderation_ad_returns_404(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """approve_ad returns 404 for ads genuinely outside the approvable pair.

        ``PUBLISHED`` is in neither ``ON_MODERATION`` nor
        ``ON_MODERATION_FAILED``; the guard against over-widening keeps this a
        404.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        client = Client()
        client.force_login(staff_user)
        response = client.post(f"/moderation/approve/{ad.id}/")

        assert response.status_code == 404

    def test_approve_out_of_pair_statuses_return_404(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """DELETED and DRAFT are outside the approvable pair and still 404."""
        client = Client()
        client.force_login(staff_user)

        for status in (AdStatus.DELETED, AdStatus.DRAFT):
            ad = create_test_ad(seller, category, city, status=status)
            response = client.post(f"/moderation/approve/{ad.id}/")
            assert response.status_code == 404, status

            ad.refresh_from_db()
            assert ad.status == status

    def test_approve_failed_ad_returns_2xx_no_transition_no_log(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """ON_MODERATION_FAILED is reachable: 2xx, no transition, no audit row.

        The state machine still refuses ``ON_MODERATION_FAILED -> PUBLISHED``,
        so the ad is unchanged and no ``ModeratorActionLog`` is written; the
        refusal is surfaced as a message rather than a 404 or a 500.
        """
        ad = create_test_ad(
            seller, category, city, status=AdStatus.ON_MODERATION_FAILED
        )

        client = Client()
        client.force_login(staff_user)
        response = client.post(f"/moderation/approve/{ad.id}/")

        assert response.status_code not in (404, 500)
        assert response.status_code == 302

        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION_FAILED
        assert ad.published_at is None
        assert not ModeratorActionLog.objects.filter(ad_id=ad.id).exists()

    def test_approve_failed_ad_surfaces_message(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """A refused ON_MODERATION_FAILED approval shows a message, not a 500."""
        ad = create_test_ad(
            seller, category, city, status=AdStatus.ON_MODERATION_FAILED
        )

        client = Client()
        client.force_login(staff_user)
        response = client.post(f"/moderation/approve/{ad.id}/", follow=True)

        assert response.status_code == 200
        all_messages = [
            str(m) for m in response.context["messages"]
        ] if "messages" in response.context else []
        assert any("could not be published" in m for m in all_messages), all_messages


# ---------------------------------------------------------------------------
# Tests: bulk moderation JSON endpoint approve outcome honesty
# ---------------------------------------------------------------------------


class TestBulkModerationApproveOutcome:
    """The JSON endpoint reports a distinct refusal error per id, shape unchanged."""

    def test_bulk_approve_failed_ad_reports_transition_refused(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """An ON_MODERATION_FAILED id yields HTTP 200 with the refusal string."""
        import json

        ad = create_test_ad(
            seller, category, city, status=AdStatus.ON_MODERATION_FAILED
        )

        client = Client()
        client.force_login(staff_user)
        response = client.post(
            "/moderation/api/v1/bulk-action/",
            data=json.dumps(
                {"action": "approve", "selected_items": [ad.id]}
            ),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["completed"] == 0
        assert data["errors"] == [
            {"id": ad.id, "error": "Transition refused by ad status"}
        ]

        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION_FAILED
        assert not ModeratorActionLog.objects.filter(ad_id=ad.id).exists()


# ---------------------------------------------------------------------------
# Tests: reject_ad
# ---------------------------------------------------------------------------


class TestRejectAdView:
    """reject_ad view transitions ad to REJECTED."""

    def test_reject_transitions_to_rejected(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """POST to reject_ad transitions ad from ON_MODERATION to REJECTED."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        response = client.post(
            f"/moderation/reject/{ad.id}/",
            data={"reason_category": "spam_scam", "reason_text": "Spam content"},
        )

        assert response.status_code == 302  # Redirect to admin ad list

        # Verify ad state
        ad.refresh_from_db()
        assert ad.status == AdStatus.REJECTED
        assert ad.rejected_at is not None
        assert ad.moderated_by_id == staff_user.id

    def test_reject_without_reason_text(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """reject_ad works with only reason_category (reason_text is optional)."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        response = client.post(
            f"/moderation/reject/{ad.id}/",
            data={"reason_category": "spam_scam"},
        )

        assert response.status_code == 302
        ad.refresh_from_db()
        assert ad.status == AdStatus.REJECTED

    def test_reject_creates_moderation_log(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """reject_ad creates a ModeratorActionLog entry."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        client.post(
            f"/moderation/reject/{ad.id}/",
            data={"reason_category": "spam_scam", "reason_text": "Spam"},
        )

        log_entries = ModeratorActionLog.objects.filter(ad_id=ad.id)
        assert log_entries.exists()

    def test_reject_requires_post(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """GET to reject_ad is refused with 405 rather than rejecting.

        ``09-API-010`` converted ``reject_ad`` to ``@require_POST`` to match
        ``approve_ad``; a non-POST is now a 405 instead of the previous 302. The
        moderation template submits only POST forms (no GET fallback), so no
        working surface depended on the redirect.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        response = client.get(f"/moderation/reject/{ad.id}/")

        assert response.status_code == 405

        # Ad should NOT be rejected
        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION
        assert ad.rejected_at is None

    def test_reject_failed_moderation_ad(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """reject_ad works for ads in ON_MODERATION_FAILED status."""
        ad = create_test_ad(
            seller, category, city, status=AdStatus.ON_MODERATION_FAILED
        )

        client = Client()
        client.force_login(staff_user)
        response = client.post(
            f"/moderation/reject/{ad.id}/",
            data={"reason_category": "spam_scam"},
        )

        assert response.status_code == 302
        ad.refresh_from_db()
        assert ad.status == AdStatus.REJECTED


# ---------------------------------------------------------------------------
# Tests: reject_ad boundary — reason_category validated against the enum
# ---------------------------------------------------------------------------


class TestRejectAdBoundary:
    """``reject_ad`` validates ``reason_category`` against ``CategoryRejectReason``.

    An unknown category re-renders the review page with a translated error and
    the moderator's typed input preserved (Q2 ruling, 2026-10-03): HTTP 200, no
    coercion to empty, and no ``ModeratorActionLog`` row.
    """

    def test_invalid_reason_category_rerenders_without_audit_row(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """An unknown category re-renders with error and preserved input."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        response = client.post(
            f"/moderation/reject/{ad.id}/",
            data={"reason_category": "not_a_reason", "reason_text": "My note"},
        )

        assert response.status_code == 200
        assert response.context["reason_category"] == "not_a_reason"
        assert response.context["reason_text"] == "My note"
        assert response.context["error"]
        assert response.context["error"] in response.content.decode("utf-8")

        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION
        assert not ModeratorActionLog.objects.filter(ad_id=ad.id).exists()

    def test_missing_reason_category_is_rejected(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """A missing category re-renders (200), not a 302/400, with no audit row."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        response = client.post(
            f"/moderation/reject/{ad.id}/",
            data={"reason_text": "My note"},
        )

        assert response.status_code == 200
        assert not ModeratorActionLog.objects.filter(ad_id=ad.id).exists()

        ad.refresh_from_db()
        assert ad.status == AdStatus.ON_MODERATION

    @pytest.mark.parametrize("reason", list(CategoryRejectReason))
    def test_every_category_reject_reason_member_is_accepted(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
        reason: CategoryRejectReason,
    ) -> None:
        """Every ``CategoryRejectReason`` member is accepted (302, REJECTED)."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        response = client.post(
            f"/moderation/reject/{ad.id}/",
            data={"reason_category": reason.value},
        )

        assert response.status_code == 302
        ad.refresh_from_db()
        assert ad.status == AdStatus.REJECTED


# ---------------------------------------------------------------------------
# Tests: ban_user
# ---------------------------------------------------------------------------


class TestBanUserView:
    """ban_user view bans the ad owner."""

    def test_ban_marks_user_as_banned(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """POST to ban_user marks the seller as banned."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        response = client.post(
            f"/moderation/ban/{ad.id}/",
            data={"ban_reason": "Repeated violations"},
        )

        assert response.status_code == 302  # Redirect to admin ad list

        # Verify seller is banned
        seller.refresh_from_db()
        assert seller.is_banned is True

    def test_ban_creates_moderation_log(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """ban_user creates a ModeratorActionLog entry for the ban."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        client.post(
            f"/moderation/ban/{ad.id}/",
            data={"ban_reason": "Repeated violations"},
        )

        # Verify moderation log exists for this user
        log_entries = ModeratorActionLog.objects.filter(user_id=seller.id)
        assert log_entries.exists()

    def test_ban_requires_post(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """GET to ban_user is refused with 405 without banning.

        ``09-API-010`` converted ``ban_user`` to ``@require_POST`` to match
        ``approve_ad``; a non-POST is now a 405 instead of the previous 302.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        response = client.get(f"/moderation/ban/{ad.id}/")

        assert response.status_code == 405

        # Seller should NOT be banned
        seller.refresh_from_db()
        assert seller.is_banned is False

    def test_ban_defaults_reason_when_not_provided(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """ban_user uses default reason when ban_reason is not provided."""
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        client = Client()
        client.force_login(staff_user)
        response = client.post(f"/moderation/ban/{ad.id}/")

        assert response.status_code == 302

        # Seller should still be banned with default reason
        seller.refresh_from_db()
        assert seller.is_banned is True


# ---------------------------------------------------------------------------
# Tests: Known gap — ban_user does not revoke any session (04-AUT-002)
#
# These tests deliberately assert the CURRENT, DEFECTIVE behaviour. They are
# red-to-green specifications for phase 15's 15-AUTHZ-001, not regression
# guards: each turns red the moment a session-revocation mechanism (or a
# per-request account-state gate) lands. The gap they pin:
#
#   ``04-AUT-002`` — a ``django_session`` row is never invalidated when account
#   state changes. Of the five account-state transitions only one is reachable
#   and it is unreachable *for this subject*: ``ban_user`` is ``@staff_required``,
#   so ``request.user`` is the MODERATOR while the changed identity is
#   ``ad.user``. ``django.contrib.auth.logout(request)`` takes no target-user
#   argument, so adding it here would log out the moderator and leave the
#   banned seller's session fully live.
#
# Owner of the fix: phase 15, ``15-AUTHZ-001`` (per-request account-state
# enforcement). Produced by B-07 gates G-A and G-D.
# ---------------------------------------------------------------------------


class TestBanUserSessionKnownGap:
    """Pin that ``ban_user`` revokes NO session — neither target nor moderator.

    The web tier has zero per-request account-state enforcement, so a banned
    seller's live session survives the ban. This class executes that behaviour
    rather than inferring it, and gives the wrong-target ``logout(request)``
    trap its own tripwire — the five pre-existing ban tests structurally
    cannot see it (four assert only ``302`` + ``seller.is_banned``; the fifth is
    an ``inspect.getsource`` substring check).
    """

    def test_ban_leaves_the_banned_sellers_session_usable(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """Pin G-A / G-D: the banned seller's session survives ``ban_user``.

        Known gap: ``moderation.views.review.ban_user`` marks ``is_banned`` but
        performs no session revocation, and the web tier has no per-request
        account-state gate. Owner: phase 15, ``15-AUTHZ-001``.

        Vacuity guard: the seller is logged in FIRST (a real ``django_session``
        row is created and asserted live), then the ban mutates state while that
        session is live. If this ever passes on a client that was never logged
        in, the assertion is meaningless.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        seller_client = Client()
        seller_client.force_login(seller)
        # The seller's session is genuinely live before the ban.
        assert "_auth_user_id" in seller_client.session

        staff_client = Client()
        staff_client.force_login(staff_user)
        response = staff_client.post(
            f"/moderation/ban/{ad.id}/",
            data={"ban_reason": "Repeated violations"},
        )

        assert response.status_code == 302
        seller.refresh_from_db()
        assert seller.is_banned is True

        # Known gap (G-A): the banned seller's session is still live.
        assert "_auth_user_id" in seller_client.session

    def test_ban_does_not_log_out_the_moderator(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """Pin G-D: the MODERATOR's own session survives ``ban_user``.

        This is the tripwire for the wrong-target trap. ``ban_user`` is
        ``@staff_required``; ``logout(request)`` flushes ``request.session``
        with no target-user argument. A future edit adding ``logout(request)``
        to ``ban_user`` would log out the moderator who issued the ban and leave
        the banned seller live — and all five existing ban tests would stay
        green. This test is red the moment that happens.

        Owner of the correct fix (per-request account-state gate on the
        *subject*): phase 15, ``15-AUTHZ-001``.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        staff_client = Client()
        staff_client.force_login(staff_user)
        # The moderator's session is genuinely live before the ban.
        assert "_auth_user_id" in staff_client.session

        response = staff_client.post(
            f"/moderation/ban/{ad.id}/",
            data={"ban_reason": "Repeated violations"},
        )

        assert response.status_code == 302
        seller.refresh_from_db()
        assert seller.is_banned is True

        # The moderator's session is still live: the ban did not log them out.
        assert "_auth_user_id" in staff_client.session

    def test_banned_seller_is_now_refused_the_dashboard(
        self,
        staff_user: User,
        seller: User,
        category: Category,
        city: City,
    ) -> None:
        """The banned seller's live session is refused by the seller surfaces.

        This **supersedes the former G-A dashboard pin**: 06-PII-109 added a
        seller-surface account-state gate (``can_create_ad``, composed from
        ``can_publish_ad`` + ``can_store_personal_data``), which refuses a
        banned seller on ``/dashboard/`` with a 403. The deeper phase-15 gap —
        ``ban_user`` still revokes no ``django_session`` row (the sibling test
        pins that residual) — is unchanged; the subject simply can no longer
        *use* the surviving session on the seller surfaces.

        Vacuity guard: log in first, then ban while the session is live.
        """
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        seller_client = Client()
        seller_client.force_login(seller)
        assert "_auth_user_id" in seller_client.session

        staff_client = Client()
        staff_client.force_login(staff_user)
        staff_client.post(
            f"/moderation/ban/{ad.id}/",
            data={"ban_reason": "Repeated violations"},
        )

        seller.refresh_from_db()
        assert seller.is_banned is True

        # The banned seller's surviving session is refused on the seller surface.
        dashboard = seller_client.get("/dashboard/")
        assert dashboard.status_code == 403


# ---------------------------------------------------------------------------
# Tests: Structural assertions for DB-003 locking (select_for_update)
# ---------------------------------------------------------------------------


class TestModerationReviewLocking:
    """Verify that approve_ad and reject_ad use row-level locking (DB-003).

    These structural assertions guard against accidental removal of the
    ``select_for_update()`` / ``transaction.atomic()`` pattern in
    ``review.py`` — the fix for the stale-state race window between fetching
    an ``Ad`` and transitioning it inside the bot/web two-process architecture.
    """

    def test_approve_ad_uses_select_for_update_and_atomic(self) -> None:
        """approve_ad source contains select_for_update inside transaction.atomic."""
        from apps.moderation.views import review

        source = inspect.getsource(review.approve_ad)
        assert "transaction.atomic" in source
        assert "select_for_update" in source

    def test_reject_ad_uses_select_for_update_and_atomic(self) -> None:
        """reject_ad source contains select_for_update inside transaction.atomic."""
        from apps.moderation.views import review

        source = inspect.getsource(review.reject_ad)
        assert "transaction.atomic" in source
        assert "select_for_update" in source

    def test_ban_user_uses_select_for_update_and_atomic(self) -> None:
        """ban_user source contains select_for_update inside transaction.atomic."""
        from apps.moderation.views import review

        source = inspect.getsource(review.ban_user)
        assert "transaction.atomic" in source
        assert "select_for_update" in source
