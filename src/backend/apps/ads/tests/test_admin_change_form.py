"""
Admin-view tests for the ``AdAdmin`` change-form field contract (finding AD-001).

This module combines the two in-repo admin-test patterns:

* **Pattern A** (``apps/users/tests/test_admin_change_form.py``) — a module-local
  ``staff_user`` fixture on the ``9300001xx`` band, ``django.test.Client`` +
  ``force_login`` + ``reverse("admin:ads_ad_change", args=[pk])``, POST with
  ``"_save": "Save"`` and assert on the stored row after ``refresh_from_db()``.
* **Pattern B** (``apps/users/tests/test_admin_pii_containment.py``) —
  ``RequestFactory`` + ``admin.site``-style ``get_form(request, obj, change=True)``
  introspection, with a deliberate anti-vacuity guard: an *absent-or-disabled*
  assertion is satisfiable by collapsing the form to nothing, so at least one
  retained writable field is positively asserted.

The change form is an explicit field contract: ``user`` and
``original_published_at`` are inert, the four ``search_vector*`` columns are
dropped, status changes run through ``Ad.transition_to`` and the moderation
services, and a status the form cannot satisfy is a validation error — never an
HTTP 500.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib import admin
from django.contrib.messages.storage.cookie import CookieStorage
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.ads.admin import AdAdmin
from apps.ads.models import Ad
from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AdStatus
from apps.moderation.models import ModerationCriteria, ModeratorActionLog
from apps.users.models import User
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def staff_user() -> User:
    """A plain ``is_staff`` moderator without superuser rights.

    Module-local (``conftest.py`` is contended territory); the ``9300001xx``
    band mirrors the ``UserAdmin`` module.
    """
    return User.objects.create(
        telegram_id=930000111,
        chat_id=930000111,
        password="x",
        is_staff=True,
    )


def _admin_request(user: User):
    """Build a ``RequestFactory`` request carrying a real user and messages."""
    request = RequestFactory().get("/admin/")
    request.user = user
    request._messages = CookieStorage(request)  # pyright: ignore[reportAttributeAccessIssue]
    return request


def _change_data(ad: Ad, **overrides: object) -> dict[str, object]:
    """Build a complete change-form POST payload from *ad*.

    A whole-row payload keeps the tests honest: a save mechanism that drops any
    unmentioned field would be caught by the whole-saved-row assertion. The
    admin renders ``DateTimeField``s with a split widget, so stored lifecycle
    timestamps are re-sent as ``_0``/``_1`` keys.
    """
    data: dict[str, object] = {
        "title": ad.title,
        "description": ad.description,
        "price_amount": str(ad.price_amount),
        "price_currency": ad.price_currency or "",
        "source": ad.source,
        "status": ad.status,
        "category": ad.category_id or "",
        "city": ad.city_id or "",
        "original_language": ad.original_language or "",
        "_save": "Save",
    }
    for field in ("published_at", "archived_at", "deleted_at"):
        value = getattr(ad, field, None)
        if value is not None:
            data.update(_split_dt(field, value))
    data.update(overrides)
    return data


def _assert_saved(response) -> None:
    """Assert the admin accepted the POST, surfacing form errors on failure."""
    form = response.context["adminform"].form if response.context else None
    detail = form.errors.as_json() if form is not None else "<no form>"
    assert response.status_code == 302, f"form not saved: {detail}"


def _split_dt(field: str, value) -> dict[str, str]:
    """Render a datetime as the admin split-widget (``_0``/``_1``) POST keys."""
    local = timezone.localtime(value)
    return {
        f"{field}_0": local.date().isoformat(),
        f"{field}_1": local.time().strftime("%H:%M:%S"),
    }


# ---------------------------------------------------------------------------
# Pattern A — HTTP change-form behaviour
# ---------------------------------------------------------------------------


def test_publish_via_form_writes_exactly_one_audit_row_and_no_event(
    staff_user: User, seller, category, city
) -> None:
    """A staff POST of ``status=published`` commits through ``set_published``.

    Exactly one ``ModeratorActionLog`` row and zero ``AnalyticsEvent`` rows are
    written: the form path routes through ``set_published`` (1 log, 0 events),
    not ``_pass_moderation`` (1 log, 2 events). Red against the pre-change code,
    which wrote zero audit rows.
    """
    ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
    client = Client()
    client.force_login(staff_user)

    response = client.post(
        reverse("admin:ads_ad_change", args=[ad.pk]),
        data=_change_data(
            ad,
            status=AdStatus.PUBLISHED,
            **_split_dt("published_at", timezone.now()),
        ),
    )

    _assert_saved(response)
    ad.refresh_from_db()
    assert ad.status == AdStatus.PUBLISHED
    assert ad.published_at is not None
    assert ModeratorActionLog.objects.filter(ad_id=ad.pk).count() == 1
    assert (
        AnalyticsEvent.objects.filter(ad_id=ad.pk).count() == 0
    ), "the form path routes through set_published, which writes no analytics event"


def test_title_only_change_writes_no_audit_row(
    staff_user: User, seller, category, city
) -> None:
    """No ``status`` in ``changed_data`` means no audit row."""
    ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
    client = Client()
    client.force_login(staff_user)

    response = client.post(
        reverse("admin:ads_ad_change", args=[ad.pk]),
        data=_change_data(ad, title="Renamed without a status change"),
    )

    _assert_saved(response)
    ad.refresh_from_db()
    assert ad.title == "Renamed without a status change"
    assert ad.status == AdStatus.ON_MODERATION
    assert ModeratorActionLog.objects.filter(ad_id=ad.pk).count() == 0


def test_original_published_at_is_immutable_through_the_form(
    staff_user: User, seller, category, city
) -> None:
    """A hand-picked ``original_published_at`` leaves the stored value intact."""
    original = timezone.now() - timedelta(days=30)
    ad = create_test_ad(
        seller,
        category,
        city,
        status=AdStatus.PUBLISHED,
        original_published_at=original,
    )
    stored = Ad.objects.get(pk=ad.pk).original_published_at
    assert stored == original  # positive control

    client = Client()
    client.force_login(staff_user)
    forged = (timezone.now() - timedelta(days=999)).isoformat()
    response = client.post(
        reverse("admin:ads_ad_change", args=[ad.pk]),
        data=_change_data(ad, original_published_at=forged),
    )

    _assert_saved(response)
    assert Ad.objects.get(pk=ad.pk).original_published_at == stored


def test_user_is_not_reassignable_through_the_form(
    staff_user: User, seller, category, city
) -> None:
    """A POST carrying another ``user`` leaves the owner unchanged."""
    ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
    other = User.objects.create(
        telegram_id=930000112, chat_id=930000112, password="x"
    )

    client = Client()
    client.force_login(staff_user)
    response = client.post(
        reverse("admin:ads_ad_change", args=[ad.pk]),
        data=_change_data(ad, user=other.pk),
    )

    _assert_saved(response)
    assert Ad.objects.get(pk=ad.pk).user_id == seller.pk


@pytest.mark.parametrize(
    "target, timestamp_field",
    [
        (AdStatus.REJECTED, "rejected_at"),
        (AdStatus.ON_MODERATION_FAILED, "moderation_failed_at"),
    ],
)
def test_unsatisfiable_status_is_a_form_error_not_a_500(
    staff_user: User, seller, category, city, target, timestamp_field
) -> None:
    """``REJECTED`` / ``ON_MODERATION_FAILED`` POSTs are validation errors.

    Their timestamp columns are read-only, so the form can never satisfy the
    check constraint. Pre-change this reached the database as a raw UPDATE and
    raised ``IntegrityError`` -> 500.
    """
    ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
    client = Client()
    client.force_login(staff_user)

    response = client.post(
        reverse("admin:ads_ad_change", args=[ad.pk]),
        data=_change_data(ad, status=target),
    )

    assert response.status_code == 200, "must be a form error, not a redirect/500"
    assert response.context["adminform"].form.errors.get("status")
    ad.refresh_from_db()
    assert ad.status == AdStatus.ON_MODERATION
    assert ModeratorActionLog.objects.filter(ad_id=ad.pk).count() == 0


@pytest.mark.parametrize(
    "source_status, target, timestamp_field",
    [
        (AdStatus.ON_MODERATION, AdStatus.PUBLISHED, "published_at"),
        (AdStatus.PUBLISHED, AdStatus.ARCHIVED, "archived_at"),
        (AdStatus.PUBLISHED, AdStatus.DELETED, "deleted_at"),
    ],
)
def test_blank_timestamp_status_is_a_form_error_not_a_500(
    staff_user: User, seller, category, city, source_status, target, timestamp_field
) -> None:
    """A timestamp-bearing status with a blank timestamp is a validation error."""
    ad = create_test_ad(seller, category, city, status=source_status)
    Ad.objects.filter(pk=ad.pk).update(**{timestamp_field: None})
    ad.refresh_from_db()
    assert getattr(ad, timestamp_field) is None  # positive control

    client = Client()
    client.force_login(staff_user)
    response = client.post(
        reverse("admin:ads_ad_change", args=[ad.pk]),
        data=_change_data(ad, status=target),
    )

    assert response.status_code == 200, "must be a form error, not a redirect/500"
    assert response.context["adminform"].form.errors.get("status")
    ad.refresh_from_db()
    assert ad.status == source_status


def test_deleted_terminal_state_cannot_be_resurrected_via_form(
    staff_user: User, seller, category, city
) -> None:
    """``DELETED -> published`` through the form is refused (terminal state).

    Pre-change this was a plain UPDATE that returned 302 and resurrected the
    row. Now it is a form error: status unchanged, no audit row, no 500.
    """
    ad = create_test_ad(seller, category, city, status=AdStatus.DELETED)
    assert AdStatus(ad.status) == AdStatus.DELETED

    client = Client()
    client.force_login(staff_user)
    response = client.post(
        reverse("admin:ads_ad_change", args=[ad.pk]),
        data=_change_data(
            ad,
            status=AdStatus.PUBLISHED,
            **_split_dt("published_at", timezone.now()),
        ),
    )

    assert response.status_code == 200, "must be a form error, not a redirect/500"
    assert response.context["adminform"].form.errors.get("status")
    ad.refresh_from_db()
    assert ad.status == AdStatus.DELETED
    assert ModeratorActionLog.objects.filter(ad_id=ad.pk).count() == 0


def test_status_without_audit_service_transitions_without_a_row(
    staff_user: User, seller, category, city
) -> None:
    """``ARCHIVED`` performs the transition but writes no audit row.

    Pins the recorded residual: ARCHIVED / ON_MODERATION / DRAFT /
    ON_MODERATION_FAILED have no status+audit service, so BLOCK 6B cannot lose
    the fact that no row is written today.
    """
    ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
    client = Client()
    client.force_login(staff_user)

    response = client.post(
        reverse("admin:ads_ad_change", args=[ad.pk]),
        data=_change_data(
            ad,
            status=AdStatus.ARCHIVED,
            **_split_dt("archived_at", timezone.now()),
        ),
    )

    _assert_saved(response)
    ad.refresh_from_db()
    assert ad.status == AdStatus.ARCHIVED
    assert ad.archived_at is not None
    assert ModeratorActionLog.objects.filter(ad_id=ad.pk).count() == 0


def test_max_ads_exceeded_surfaces_as_admin_message_not_500(
    staff_user: User, seller, category, city
) -> None:
    """``MaxAdsExceeded`` on publish is a message, not an HTTP 500."""
    criteria = ModerationCriteria.get_singleton()
    criteria.max_ads_per_user = 0
    criteria.save()
    ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

    client = Client()
    client.force_login(staff_user)
    response = client.post(
        reverse("admin:ads_ad_change", args=[ad.pk]),
        data=_change_data(
            ad,
            status=AdStatus.PUBLISHED,
            **_split_dt("published_at", timezone.now()),
        ),
    )

    assert response.status_code in (200, 302), "must not be a 500"
    ad.refresh_from_db()
    assert ad.status == AdStatus.ON_MODERATION
    assert ModeratorActionLog.objects.filter(ad_id=ad.pk).count() == 0


def test_title_and_status_change_are_both_persisted(
    staff_user: User, seller, category, city
) -> None:
    """A POST changing the title and the status persists both.

    This is the direct guard for the ``refresh_from_db`` ordering trap: a save
    routed through ``transition_to`` without the step-1 write would discard the
    form's title.
    """
    ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
    client = Client()
    client.force_login(staff_user)

    response = client.post(
        reverse("admin:ads_ad_change", args=[ad.pk]),
        data=_change_data(
            ad,
            title="Title and status together",
            status=AdStatus.PUBLISHED,
            **_split_dt("published_at", timezone.now()),
        ),
    )

    _assert_saved(response)
    ad.refresh_from_db()
    assert ad.status == AdStatus.PUBLISHED
    assert ad.title == "Title and status together"
    assert ad.published_at is not None


# ---------------------------------------------------------------------------
# Pattern B — form field-contract introspection
# ---------------------------------------------------------------------------


def test_search_vector_fields_are_not_in_the_form(staff_user: User, seller, category, city) -> None:
    """The four ``search_vector*`` columns are absent, with an anti-vacuity guard."""
    ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
    ad_admin = AdAdmin(Ad, admin.site)
    form = ad_admin.get_form(_admin_request(staff_user), obj=ad, change=True)

    for name in (
        "search_vector",
        "search_vector_ru",
        "search_vector_bs",
        "search_vector_en",
    ):
        assert name not in form.base_fields, (
            "the trigger rewrites search_vector* on every write; the field must "
            "not be in the form"
        )

    # Anti-vacuity guard: the form must still expose a real writable field.
    assert "title" in form.base_fields, "the form must not have collapsed to empty"
    assert form.base_fields["title"].disabled is False, (
        "title must remain writable on the change form"
    )
