"""
Admin-action tests for staff-initiated consent withdrawal (``06-PII-107``).

``Q-D7`` resolved as **WIRE**: ``withdraw_consent_action`` is registered in
``UserAdmin.actions`` and gated with ``permissions=["delete"]``. Because the
phase-04 field contract makes every consent/account-state field read-only in the
admin, this action is the **only** staff-side consent mutation, so removing it
would leave staff with no way to action a subject's request.

The gate has two halves, both of which this module pins:

* the action is filtered **out of ``get_actions()``** for a plain ``is_staff``
  moderator (it never appears in the dropdown);
* ``response_action`` rebuilds ``action_form.fields["action"].choices`` from
  ``get_action_choices()`` **before** ``is_valid()``, so a **forged POST** fails
  form validation — Django does **not** raise ``PermissionDenied`` for a
  permission-filtered action; it returns the "No action selected." warning and
  never calls the function. The forged POST therefore leaves no side effect and
  writes no ``ConsentRecord``.

The action evaluates the queryset once, counts already-withdrawn rows
(``is_deleted``) as skipped, and reports **both** counts so a partial selection
cannot read as a full success. It opens no outer ``transaction.atomic()``:
``withdraw_consent`` owns a per-user transaction, so the admin POST must
**not** be wrapped in ``transaction=True`` — a test-level transaction would hide
whether the audit row actually commits.

``conftest.py`` is contended, so the moderator/superuser fixtures are
module-local and built with ``get_or_create`` (the ``test_admin_deactivate_user``
pattern) so ``--reuse-db`` works. Message assertions use **hard-coded**
substrings, not the imported ``SKIPPED_ROWS_PREFIX`` / ``ALREADY_IN_STATE_CLAUSE``
constants: pinning the constant by importing it is a tautology that survives any
reword.
"""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from apps.core.enums import ConsentActionSource, ConsentChoice
from apps.users.admin import UserAdmin
from apps.users.models import ConsentRecord, User

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# Distinct telegram_id block: 9300000xx / 9300001xx / 9300002xx are taken by the
# other users test modules; this module owns 9300003xx.
_MODERATOR_ID = 930000301
_SUPERUSER_ID = 930000302
_CHANGELIST = "admin:users_user_changelist"


@pytest.fixture
def moderator() -> User:
    """A plain ``is_staff`` + ``is_active`` moderator without superuser rights."""
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
def superuser() -> User:
    """A superuser — the only actor allowed to reach the action."""
    user, _ = User.objects.get_or_create(
        telegram_id=_SUPERUSER_ID,
        defaults={
            "chat_id": _SUPERUSER_ID,
            "password": "x",
            "is_staff": True,
            "is_active": True,
            "is_superuser": True,
        },
    )
    return user


def _make_user(telegram_id: int, **overrides: object) -> User:
    """Create an ordinary user with this module's telegram_id block."""
    defaults: dict[str, object] = {
        "telegram_id": telegram_id,
        "chat_id": telegram_id,
        "password": "x",
    }
    defaults.update(overrides)
    return User.objects.create(**defaults)  # type: ignore[arg-type]


def _post_action(client: Client, user_ids: list[int], *, follow: bool = False):
    """POST a forged changelist action over the given rows (real endpoint)."""
    return client.post(
        reverse(_CHANGELIST),
        data={
            "action": "withdraw_consent_action",
            "index": 0,
            "_selected_action": [str(pk) for pk in user_ids],
            "select_across": "0",
        },
        follow=follow,
    )


def _messages_text(response) -> str:
    """Join every message rendered into the post-action response."""
    return " ".join(str(m) for m in response.context["messages"])


# ---------------------------------------------------------------------------
# 1-2: registration and the anti-clobber guard
# ---------------------------------------------------------------------------


def test_actions_registers_withdraw_and_still_names_the_deactivate_pair() -> None:
    """The action is registered **and** the two existing actions survive.

    The anti-clobber guard: a fresh ``actions = [...]`` written instead of
    extending the existing list would silently delete ``deactivate_user`` /
    ``reactivate_user`` and their gate. This test fails if either is dropped.
    """
    assert "withdraw_consent_action" in UserAdmin.actions
    assert "deactivate_user" in UserAdmin.actions
    assert "reactivate_user" in UserAdmin.actions


def test_absent_from_get_actions_for_moderator_present_for_superuser(
    moderator: User, superuser: User
) -> None:
    """The first half of the gate: ``get_actions()`` filters by permission.

    Django's ``_filter_actions_by_permissions`` routes
    ``permissions=["delete"]`` to ``has_delete_permission`` (superuser-only), so
    a moderator's dropdown omits the action entirely.
    """
    from django.contrib import admin

    user_admin = UserAdmin(User, admin.site)
    for actor, expected in ((moderator, False), (superuser, True)):
        client = Client()
        client.force_login(actor)
        response = client.get(reverse(_CHANGELIST))
        assert response.status_code == 200
        actions = dict(user_admin.get_actions(response.wsgi_request))
        assert ("withdraw_consent_action" in actions) is expected


# ---------------------------------------------------------------------------
# 3-4: forged POST is refused for a moderator, honoured for a superuser
# ---------------------------------------------------------------------------


def test_forged_post_as_moderator_withdraws_nothing_and_writes_no_record(
    moderator: User,
) -> None:
    """The second half of the gate: a forged POST fails action-form validation.

    Django does not raise ``PermissionDenied``; the action is not in the form's
    choices, so validation fails and the function is never called. The target is
    untouched and no ``ConsentRecord`` is written.
    """
    target = _make_user(930000310)

    client = Client()
    client.force_login(moderator)
    response = _post_action(client, [target.pk], follow=True)

    target.refresh_from_db()
    assert target.is_deleted is False
    assert not ConsentRecord.objects.filter(user=target).exists()
    # Observably: the "No action selected." warning, not a PermissionDenied.
    assert "No action selected" in _messages_text(response)


def test_forged_post_as_superuser_withdraws_and_writes_one_record(
    superuser: User,
) -> None:
    """A superuser's POST withdraws the row and writes exactly one audit row."""
    target = _make_user(930000311)

    client = Client()
    client.force_login(superuser)
    _post_action(client, [target.pk])

    target.refresh_from_db()
    assert target.is_deleted is True
    assert target.consent_revoked_at is not None
    records = list(ConsentRecord.objects.filter(user=target))
    assert len(records) == 1
    assert records[0].choice == ConsentChoice.WITHDRAWN.value
    assert records[0].categories == {"analytics": False, "preferences": False}
    # The admin supplies no HTTP context (BLOCK 10's shipped behaviour; retained
    # as a recorded residual by BLOCK 18).
    assert records[0].ip_address is None
    assert records[0].user_agent == ""
    # The staff actor and the admin mechanism are recorded (06-NEW-02): the row
    # no longer reads as "the subject withdrew".
    assert records[0].initiated_by_id == superuser.pk
    assert records[0].action_source == ConsentActionSource.ADMIN_STAFF.value


# ---------------------------------------------------------------------------
# 5: the toast reports both counts for a mixed selection
# ---------------------------------------------------------------------------


def test_message_reports_withdrawn_and_skipped_counts(superuser: User) -> None:
    """A mixed selection reports the withdrawn count **and** the skipped count.

    One fresh row and one already-withdrawn row: the toast must say
    ``Withdrew consent for 1 user(s)`` and name the one row that was already in
    the withdrawn state, so twenty no-ops are never reported as twenty
    withdrawals.
    """
    fresh = _make_user(930000312)
    already = _make_user(930000313, is_deleted=True)

    client = Client()
    client.force_login(superuser)
    response = _post_action(client, [fresh.pk, already.pk], follow=True)

    text = _messages_text(response)
    assert "Withdrew consent for 1 user(s)" in text
    assert "Skipped:" in text
    assert "1 already in the requested state" in text
