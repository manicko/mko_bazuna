"""
Admin-view tests for the ``UserAdmin`` field contract (finding 04-AUT-005).

This is the first admin-view test module in the repository. It drives the real
Django admin endpoints (``admin:users_user_change`` / ``admin:users_user_add``)
as a staff moderator and asserts the two assets the field contract protects:

* the stored password hash is never rendered into the change-form HTML, and
* no plaintext password can be written through either admin view.

The established module-local ``staff_user`` pattern is reused (``conftest.py``
is contended territory); the credential target is always built with
``set_password(<known raw>)`` and a positive control is asserted before any
POST, because a fixture that stores a plaintext ``password="x"`` would make a
``check_password`` assertion vacuously true.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.hashers import check_password
from django.test import Client
from django.urls import reverse

from apps.users.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

KNOWN_RAW_PASSWORD = "correct horse battery staple"


@pytest.fixture
def staff_user() -> User:
    """A plain ``is_staff`` moderator without superuser rights."""
    return User.objects.create(
        telegram_id=930000101,
        chat_id=930000101,
        password="x",
        is_staff=True,
    )


@pytest.fixture
def superuser() -> User:
    """A superuser — the only actor allowed to reach the add view."""
    return User.objects.create(
        telegram_id=930000102,
        chat_id=930000102,
        password="x",
        is_staff=True,
        is_superuser=True,
    )


def _credential_target(username: str = "target") -> User:
    """Create a user with a usable, known credential for credential assertions."""
    user = User.objects.create(
        telegram_id=930000103,
        chat_id=930000103,
        username=username,
    )
    user.set_password(KNOWN_RAW_PASSWORD)
    user.save()
    return user


def test_change_form_html_never_renders_the_raw_password_hash(staff_user: User) -> None:
    """The change-form HTML must not disclose the raw password or its hash."""
    target = _credential_target()
    assert target.check_password(KNOWN_RAW_PASSWORD) is True  # positive control

    client = Client()
    client.force_login(staff_user)
    response = client.get(reverse("admin:users_user_change", args=[target.pk]))

    assert response.status_code == 200
    content = response.content.decode()
    stored_hash = User.objects.get(pk=target.pk).password
    assert KNOWN_RAW_PASSWORD not in content
    assert stored_hash not in content
    for segment in stored_hash.split("$"):
        if len(segment) > 8:
            assert segment not in content, "a password-hash segment leaked into the page"


def test_admin_change_does_not_accept_a_plaintext_password(staff_user: User) -> None:
    """A plaintext POST to the change view leaves the stored credential intact."""
    target = _credential_target()
    assert target.check_password(KNOWN_RAW_PASSWORD) is True  # positive control
    hash_before = User.objects.get(pk=target.pk).password

    plaintext = "brand-new-plaintext-password"
    client = Client()
    client.force_login(staff_user)
    response = client.post(
        reverse("admin:users_user_change", args=[target.pk]),
        data={"password": plaintext, "preferred_city": "", "_save": "Save"},
    )

    assert response.status_code == 302, "the change view must accept the POST"
    target.refresh_from_db()
    assert check_password(plaintext, target.password) is False
    assert target.password == hash_before, "the stored hash must be byte-identical"


def test_non_superuser_moderator_cannot_write_superuser_flag(staff_user: User) -> None:
    """A moderator POSTing ``is_superuser`` must not escalate an ordinary user.

    ``has_change_permission`` ignores ``obj``, so the moderator reaches the row;
    the field contract is what denies the write.
    """
    target = User.objects.create(
        telegram_id=930000104,
        chat_id=930000104,
        username="ordinary",
        password="x",
        is_superuser=False,
        is_staff=False,
    )

    client = Client()
    client.force_login(staff_user)
    response = client.post(
        reverse("admin:users_user_change", args=[target.pk]),
        data={"is_superuser": "on", "preferred_city": "", "_save": "Save"},
    )

    assert response.status_code == 302
    target.refresh_from_db()
    assert target.is_superuser is False, "a moderator must not escalate privileges"


def test_non_superuser_moderator_cannot_flip_account_state(staff_user: User) -> None:
    """A moderator cannot flip consent or account-state flags through the form."""
    target = User.objects.create(
        telegram_id=930000105,
        chat_id=930000105,
        username="seller",
        password="x",
        is_banned=False,
        is_deleted=False,
        is_declined=False,
        ads_auto_publish=True,
    )

    client = Client()
    client.force_login(staff_user)
    response = client.post(
        reverse("admin:users_user_change", args=[target.pk]),
        data={
            "is_banned": "on",
            "is_deleted": "on",
            "is_declined": "on",
            "preferred_city": "",
            "_save": "Save",
        },
    )

    assert response.status_code == 302
    target.refresh_from_db()
    assert target.is_banned is False
    assert target.is_deleted is False
    assert target.is_declined is False
    assert target.ads_auto_publish is True


def test_add_view_stores_a_hashed_password(superuser: User) -> None:
    """The add view stores a hashed, authenticating credential and the chat_id."""
    client = Client()
    client.force_login(superuser)
    response = client.post(
        reverse("admin:users_user_add"),
        data={
            "username": "created-by-admin",
            "telegram_id": "930000106",
            "chat_id": "930000106",
            "password1": KNOWN_RAW_PASSWORD,
            "password2": KNOWN_RAW_PASSWORD,
            "_save": "Save",
        },
    )

    assert response.status_code == 302, "the add view must create the user"
    created = User.objects.get(telegram_id=930000106)
    assert created.password != KNOWN_RAW_PASSWORD
    assert created.check_password(KNOWN_RAW_PASSWORD) is True
    assert created.has_usable_password() is True
    assert created.chat_id == 930000106


def test_add_view_forbids_a_non_superuser(staff_user: User) -> None:
    """The add view is superuser-only."""
    client = Client()
    client.force_login(staff_user)
    response = client.get(reverse("admin:users_user_add"))
    assert response.status_code == 403
