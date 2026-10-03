"""
Moderator single-photo removal — service and admin-action tests (``07-MEDIA-005``).

``AdImage`` is append-only, so before this block a moderator who found an
inappropriate photo in a published ad could only destroy the whole listing or
ban the seller. This module pins the third, proportionate lever:
``AdImageAdmin.action_remove_photo`` delegating to
``apps.ads.services.ad_image_removal.remove_ad_image``.

The tests verify by **introspection** (``get_actions(request)``), never by
reading the permission flags in source: a decorated-but-invisible action is the
exact defect phase 04 found, and only the framework's own filtering can prove
the action is (or is not) reachable from the UI.

Byte freeing is **not** this block's code. ``remove_ad_image`` deletes the row;
``apps.media.signals.delete_adimage_files_on_delete`` frees the bytes through
BLOCK 2b's four-column ``unreferenced_keys`` check inside its ``on_commit``
closure. Tests 3-6 prove exactly that boundary: they patch
``"apps.media.signals.delete_photo"`` by string (the contract all the existing
sites use) and never route through ``apps.media.services.filesystem``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings
from django.contrib import admin
from django.contrib.messages.storage.cookie import CookieStorage
from django.test import Client, RequestFactory
from django.urls import reverse

from apps.ads.admin import AdAdmin, AdImageAdmin
from apps.ads.models import Ad, AdImage
from apps.ads.services.ad_image_removal import (
    PhotoRemovalReason,
    remove_ad_image,
)
from apps.core.enums import AdStatus, ModeratorActionType
from apps.moderation.models import ModeratorActionLog
from apps.users.models import User
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# This module owns the 9300004xx telegram_id block; the other ads/users test
# modules use their own blocks (see test_admin_consent_action's block table).
_MODERATOR_ID = 930000401
_CHANGELIST = "admin:ads_adimage_changelist"


@pytest.fixture
def moderator() -> User:
    """A staff (non-superuser) actor — the surface is staff-only."""
    user, _ = User.objects.get_or_create(
        telegram_id=_MODERATOR_ID,
        defaults={
            "chat_id": _MODERATOR_ID,
            "password": "x",
            "is_staff": True,
            "is_active": True,
        },
    )
    return user


@pytest.fixture
def isolated_media_root(tmp_path: Path) -> Path:
    """Isolated ``MEDIA_ROOT`` for physical-file assertions."""
    return tmp_path


def _admin_request(user: User):
    """Build a ``RequestFactory`` request carrying a real user and messages."""
    request = RequestFactory().get("/admin/")
    request.user = user
    request._messages = CookieStorage(request)  # pyright: ignore[reportAttributeAccessIssue]
    return request


def _post_action(client: Client, image_ids: list[int], *, follow: bool = False):
    """POST a changelist action over the given ``AdImage`` rows (real endpoint)."""
    return client.post(
        reverse(_CHANGELIST),
        data={
            "action": "action_remove_photo",
            "index": 0,
            "_selected_action": [str(pk) for pk in image_ids],
            "select_across": "0",
        },
        follow=follow,
    )


# ---------------------------------------------------------------------------
# 1-2: the action is reachable from the UI, and only for staff
# ---------------------------------------------------------------------------


def test_action_is_visible_to_staff_via_get_actions(moderator: User) -> None:
    """The action appears in ``get_actions(request)`` for a staff user.

    This is the tripwire: a decorated-but-invisible action (filtered out by
    Django because its ``permissions`` need a predicate that is ``False``)
    ships silently otherwise. Introspection is the only valid assertion.
    """
    image_admin = admin.site._registry[AdImage]
    actions = dict(image_admin.get_actions(_admin_request(moderator)))
    assert "action_remove_photo" in actions


def test_action_is_absent_for_anonymous_and_non_staff() -> None:
    """The action is filtered out for anonymous and non-staff requests."""
    image_admin = admin.site._registry[AdImage]

    anonymous = RequestFactory().get("/admin/")
    anonymous.user = User()  # unsaved, is_staff=False
    assert "action_remove_photo" not in dict(image_admin.get_actions(anonymous))

    plain, _ = User.objects.get_or_create(
        telegram_id=930000402,
        defaults={"chat_id": 930000402, "password": "x"},
    )
    assert "action_remove_photo" not in dict(
        image_admin.get_actions(_admin_request(plain))
    )


def test_stock_delete_selected_is_not_reachable_for_staff(moderator: User) -> None:
    """Option (b): ``has_delete_permission`` stays False, so bulk delete is gone.

    ``delete_selected`` carries ``permissions=["delete"]``; with
    ``has_delete_permission`` returning ``False`` Django filters it out. This is
    the evidence that opening only the action's ``permissions`` keeps the
    surface to exactly one audited delete path.
    """
    image_admin = admin.site._registry[AdImage]
    actions = dict(image_admin.get_actions(_admin_request(moderator)))
    assert "delete_selected" not in actions


# ---------------------------------------------------------------------------
# 3: end-to-end removal — row gone and bytes freed through the signal path
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_action_removes_row_and_frees_bytes(
    seller, category, city, moderator: User, isolated_media_root: Path, monkeypatch
) -> None:
    """A staff action on the only reference deletes the row and its files.

    The keys are the row's **only** references, so ``on_commit`` fires and
    BLOCK 2b's signal path frees every byte. The admin action never calls
    ``delete_photo`` itself; the signal boundary does the freeing.
    """
    ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
    image = AdImage.objects.create(
        ad=ad,
        image="b11-e2e-original.jpg",
        thumbnail_small="b11-e2e-small.jpg",
        thumbnail_medium="b11-e2e-medium.jpg",
        thumbnail_large="b11-e2e-large.jpg",
    )
    keys = list(image.storage_keys())
    for key in keys:
        (isolated_media_root / key).write_bytes(b"image data")

    monkeypatch.setattr(settings, "MEDIA_ROOT", str(isolated_media_root))

    client = Client()
    client.force_login(moderator)
    _post_action(client, [image.pk])

    assert not AdImage.objects.filter(pk=image.pk).exists()
    for key in keys:
        assert not (isolated_media_root / key).exists()


# ---------------------------------------------------------------------------
# 4: shared keys survive — proving the four-column check does the work
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "column", ["thumbnail_small", "thumbnail_medium", "thumbnail_large"]
)
def test_shared_thumbnail_key_survives_removal(
    seller,
    category,
    city,
    moderator: User,
    isolated_media_root: Path,
    monkeypatch,
    column: str,
) -> None:
    """A key shared via any thumbnail column survives the other row's removal.

    Row B references the key through a different column than the removed row;
    the four-column predicate in ``references.unreferenced_keys`` keeps the
    file. If ``remove_ad_image`` re-implemented byte freeing (or called
    ``delete_photo`` itself) with a one-column check, this would fail.
    """
    shared_key = f"b11-shared-via-{column}.jpg"
    ad_a = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
    image_a = AdImage.objects.create(
        ad=ad_a, image="b11-a-original.jpg", position=0, **{column: shared_key}
    )
    ad_b = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
    AdImage.objects.create(
        ad=ad_b, image="b11-b-original.jpg", position=0, **{column: shared_key}
    )
    (isolated_media_root / shared_key).write_bytes(b"shared data")

    monkeypatch.setattr(settings, "MEDIA_ROOT", str(isolated_media_root))

    client = Client()
    client.force_login(moderator)
    _post_action(client, [image_a.pk])

    assert not AdImage.objects.filter(pk=image_a.pk).exists()
    assert AdImage.objects.filter(ad=ad_b, **{column: shared_key}).exists()
    assert (isolated_media_root / shared_key).exists()


# ---------------------------------------------------------------------------
# 5: exactly one audit row, OTHER type, canned reason, actor recorded
# ---------------------------------------------------------------------------


def test_exactly_one_audit_row_with_canned_reason_and_actor(
    seller, category, city, moderator: User
) -> None:
    """One removal writes exactly one ``OTHER`` audit row naming the actor.

    There is no free-text path: the reason is the canned ``StrEnum`` value, so
    phase 06's not-yet-landed boundary redaction is moot. ``ModeratorActionLog``
    has no dedicated actor column; its ``user`` field covers "performed action",
    so the acting moderator is recorded there.
    """
    ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
    image = AdImage.objects.create(ad=ad, image="b11-audit-original.jpg")

    result = remove_ad_image(image, moderator.id)

    logs = list(ModeratorActionLog.objects.filter(ad_id=ad.pk))
    assert len(logs) == 1
    log = logs[0]
    assert log.pk == result.audit_log_id
    assert log.action_type == ModeratorActionType.OTHER.value
    assert log.reason == PhotoRemovalReason.INAPPROPRIATE_PHOTO.value
    assert log.user_id == moderator.id
    assert not AdImage.objects.filter(pk=image.pk).exists()


# ---------------------------------------------------------------------------
# 6: exactly one delete_photo call per freed key
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_one_delete_photo_call_per_freed_key(
    seller, category, city, moderator: User, isolated_media_root: Path, monkeypatch
) -> None:
    """Each freed key is passed to the signal's ``delete_photo`` exactly once.

    The row is the only reference to all four keys, so every key is freed once.
    ``delete_photo`` is patched by string, never routed through
    ``filesystem`` directly, so this asserts the signal path is the sole
    byte-freeing route.
    """
    ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
    image = AdImage.objects.create(
        ad=ad,
        image="b11-callcount-original.jpg",
        thumbnail_small="b11-callcount-small.jpg",
        thumbnail_medium="b11-callcount-medium.jpg",
        thumbnail_large="b11-callcount-large.jpg",
    )
    keys = list(image.storage_keys())
    for key in keys:
        (isolated_media_root / key).write_bytes(b"image data")

    called_keys: list[str] = []

    def _recording_delete(storage_key: str) -> None:
        called_keys.append(storage_key)

    monkeypatch.setattr("apps.media.signals.delete_photo", _recording_delete)
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(isolated_media_root))

    remove_ad_image(image, moderator.id)

    for key in keys:
        assert called_keys.count(key) == 1


# ---------------------------------------------------------------------------
# 7: the AdImageAdmin field contract and AdAdmin are untouched
# ---------------------------------------------------------------------------


def test_adimage_admin_stays_append_only(moderator: User) -> None:
    """``AdImageAdmin`` remains append-only: only the view permission is open.

    ``AdImage`` is never created or edited from the admin, and
    ``has_delete_permission`` stays ``False`` (the OC-6 option-b decision), so
    the only mutation lever is the audited removal action.
    """
    image_admin = admin.site._registry[AdImage]
    request = _admin_request(moderator)
    assert image_admin.has_add_permission(request) is False
    assert image_admin.has_change_permission(request) is False
    assert image_admin.has_delete_permission(request) is False
    assert image_admin.has_view_permission(request) is True


def test_adadmin_actions_and_fields_untouched(moderator: User) -> None:
    """``AdAdmin`` still offers ``action_ban_user`` and its field contract holds.

    Anti-clobber guard for the file the action was added to: ``AdAdmin``'s
    actions, ``list_display`` and ``readonly_fields`` must be unchanged.
    """
    ad_admin = admin.site._registry[Ad]
    assert isinstance(ad_admin, AdAdmin)
    action_names = dict(ad_admin.get_actions(_admin_request(moderator)))
    assert "action_ban_user" in action_names
    assert "id" in ad_admin.list_display
    assert "user" in ad_admin.readonly_fields


def test_adimage_admin_is_the_registered_class() -> None:
    """``AdImageAdmin`` is the class under test, registered on the admin site."""
    assert isinstance(admin.site._registry[AdImage], AdImageAdmin)


def test_action_skips_a_row_removed_mid_selection(
    seller, category, city, moderator: User
) -> None:
    """A selected row already gone is skipped, not a 500.

    A second moderator removing the same photo between page render and POST
    must not abort the whole action with ``AdImage.DoesNotExist``; the stale row
    is skipped and counted out of the toast, matching the ``bulk_delete``
    per-row skip convention.
    """
    ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
    live = AdImage.objects.create(ad=ad, image="b11-skip-live.jpg")
    stale = AdImage.objects.create(ad=ad, image="b11-skip-stale.jpg", position=1)

    # Simulate the row vanishing before the POST is processed.
    AdImage.objects.filter(pk=stale.pk).delete()

    image_admin = admin.site._registry[AdImage]
    request = _admin_request(moderator)
    image_admin.action_remove_photo(
        request, AdImage.objects.filter(pk__in=[live.pk, stale.pk])
    )

    assert not AdImage.objects.filter(pk=live.pk).exists()
    assert ModeratorActionLog.objects.filter(ad_id=ad.pk).count() == 1
