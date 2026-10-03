"""
Admin-action tests for operator account deactivation (plan 18, ``B-2``/``B-3``).

Drives the real Users changelist action endpoint
(``admin:users_user_changelist`` with ``action=deactivate_user`` /
``reactivate_user``) as a moderator and a superuser, and pins the product
contract of ``18-D1`` / ``18-Q7``:

* the action is reachable by both admins but by no non-staff seller;
* a moderator may act only on non-privileged rows (a selection containing a
  staff/superuser row has those rows silently removed and **reported**);
* deactivation revokes an existing web session on the next request but leaves
  the ``django_session`` row in place and does **not** touch the other
  account-state flags;
* the operator message names the bot-tier limit and reports skipped rows.

An action is orthogonal to a form field, so the field-contract tests in
``test_admin_change_form.py`` / ``test_admin_pii_containment.py`` are unaffected
and stay untouched. The bot-tier probe (test 14) lives under
``src/telegram_bot/tests/`` because its suite is async and its conftest
redefines the DB fixtures; it cannot be imported here.

``conftest.py`` is contended territory, so the ``staff_user`` / ``superuser``
fixtures are module-local (the pattern from ``test_admin_change_form.py``),
built with ``get_or_create`` so ``--reuse-db`` works.
"""

from __future__ import annotations

import inspect

import pytest
from django.contrib import admin
from django.test import Client
from django.urls import reverse

from apps.users.admin import UserAdmin
from apps.users.models import User
from apps.users.services.deactivation import (
    _resolve_targets,
    deactivate_users,
    reactivate_users,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# Distinct telegram_id block from the other users test modules (93xxxxxxx).
_STAFF_ID = 930000101
_SUPERUSER_ID = 930000102
_DASHBOARD_URL = "/dashboard/"


@pytest.fixture
def staff_user() -> User:
    """A plain ``is_staff`` moderator without superuser rights."""
    user, _ = User.objects.get_or_create(
        telegram_id=_STAFF_ID,
        defaults={
            "chat_id": _STAFF_ID,
            "password": "x",
            "is_staff": True,
        },
    )
    return user


@pytest.fixture
def superuser() -> User:
    """A superuser — the unrestricted actor."""
    user, _ = User.objects.get_or_create(
        telegram_id=_SUPERUSER_ID,
        defaults={
            "chat_id": _SUPERUSER_ID,
            "password": "x",
            "is_staff": True,
            "is_superuser": True,
        },
    )
    return user


def _make_user(telegram_id: int, **overrides: object) -> User:
    """Create an ordinary user with module-local IDs."""
    defaults: dict[str, object] = {
        "telegram_id": telegram_id,
        "chat_id": telegram_id,
        "password": "x",
    }
    defaults.update(overrides)
    return User.objects.create(**defaults)  # type: ignore[arg-type]


def _post_action(client: Client, action: str, user_ids: list[int]) -> None:
    """POST a changelist action over the given rows (real admin endpoint)."""
    client.post(
        reverse("admin:users_user_changelist"),
        data={
            "action": action,
            "_selected_action": [str(pk) for pk in user_ids],
            "index": "0",
        },
        follow=False,
    )


def _messages_text(response) -> str:
    """Join every message rendered into the post-action response."""
    return " ".join(str(m) for m in response.context["messages"])


# ---------------------------------------------------------------------------
# 1-2: actor reachability
# ---------------------------------------------------------------------------


def test_non_admin_cannot_reach_the_deactivate_action() -> None:
    """A plain non-staff seller is redirected away and its POST changes nothing."""
    actor = _make_user(930000110)
    target = _make_user(930000111)

    client = Client()
    client.force_login(actor)
    response = client.get(reverse("admin:users_user_changelist"))
    # A non-staff user never reaches the admin changelist: Django's
    # AdminSite.has_permission returns False and redirects to the login page.
    # Asserting the 302 is the real guard; the earlier conditional-actions
    # branch was always `{}` and therefore vacuous.
    assert response.status_code == 302

    _post_action(client, "deactivate_user", [target.pk])
    target.refresh_from_db()
    assert target.is_active is True


def test_moderator_and_superuser_can_reach_the_deactivate_action(
    staff_user: User, superuser: User
) -> None:
    """Positive control: both admin classes reach the action (anti-vacuity).

    Also asserts the predicate is a distinct named method — widening
    ``has_delete_permission`` must not widen ``has_deactivate_permission``.
    """
    action = UserAdmin(User, admin.site)
    for actor in (staff_user, superuser):
        client = Client()
        client.force_login(actor)
        response = client.get(reverse("admin:users_user_changelist"))
        assert response.status_code == 200
        actions = dict(action.get_actions(response.wsgi_request))
        assert "deactivate_user" in actions
        assert "reactivate_user" in actions

    assert UserAdmin.has_deactivate_permission is not UserAdmin.has_delete_permission


# ---------------------------------------------------------------------------
# 3-7: target scope and flag isolation
# ---------------------------------------------------------------------------


def test_deactivate_user_sets_is_active_false_and_flips_no_other_flag(
    superuser: User,
) -> None:
    """The action disables the account and leaves every other flag untouched."""
    target = _make_user(
        930000112,
        is_banned=False,
        is_deleted=False,
        is_declined=False,
        ads_auto_publish=True,
    )

    client = Client()
    client.force_login(superuser)
    _post_action(client, "deactivate_user", [target.pk])

    target.refresh_from_db()
    assert target.is_active is False
    assert target.is_banned is False
    assert target.is_deleted is False
    assert target.is_declined is False
    assert target.ads_auto_publish is True


def test_deactivate_user_excludes_the_acting_user(superuser: User) -> None:
    """The operator's own row is never written; it is reported as skipped self."""
    result = deactivate_users(User.objects.filter(pk=superuser.pk), superuser)

    assert result.changed == 0
    assert result.skipped_self == 1
    superuser.refresh_from_db()
    assert superuser.is_active is True


def test_moderator_cannot_target_a_superuser_or_staff_row(
    staff_user: User, superuser: User
) -> None:
    """``18-Q7``: a moderator's selection drops every privileged row.

    The single most important guard in the plan: with ``has_change_permission``
    ignoring ``obj``, a moderator reaching every row is the ``B-01`` escalation.

    The selection deliberately covers **both** privilege axes: a peer
    ``is_staff`` moderator, the full ``superuser`` fixture, and a row with
    ``is_superuser=True, is_staff=False``. That last row is the reason
    ``.exclude(is_superuser=True)`` cannot be dropped — the fixture sets both
    flags, so without this row the ``is_superuser`` exclusion would be untested.
    """
    seller = _make_user(930000113)
    peer_moderator = _make_user(930000114, is_staff=True)
    superuser_only = _make_user(930000122, is_superuser=True, is_staff=False)

    result = deactivate_users(
        User.objects.filter(
            pk__in=[seller.pk, peer_moderator.pk, superuser.pk, superuser_only.pk]
        ),
        staff_user,
    )

    assert result.changed == 1
    assert result.skipped_privileged == 3
    seller.refresh_from_db()
    peer_moderator.refresh_from_db()
    superuser.refresh_from_db()
    superuser_only.refresh_from_db()
    assert seller.is_active is False
    assert peer_moderator.is_active is True
    assert superuser.is_active is True
    assert superuser_only.is_active is True


def test_superuser_can_target_a_staff_row(
    superuser: User,
) -> None:
    """The positive half of ``18-Q7``: a superuser's selection is unrestricted."""
    peer_staff = _make_user(930000115, is_staff=True)

    result = deactivate_users(User.objects.filter(pk=peer_staff.pk), superuser)

    assert result.changed == 1
    assert result.skipped_privileged == 0
    peer_staff.refresh_from_db()
    assert peer_staff.is_active is False


def test_moderator_cannot_reactivate_a_superuser(
    staff_user: User, superuser: User
) -> None:
    """A moderator must not be able to undo a superuser's disable."""
    superuser.is_active = False
    superuser.save(update_fields=["is_active"])

    result = reactivate_users(User.objects.filter(pk=superuser.pk), staff_user)

    assert result.changed == 0
    assert result.skipped_privileged == 1
    superuser.refresh_from_db()
    assert superuser.is_active is False


# ---------------------------------------------------------------------------
# 8-11: web revocation, session residual, idempotence, reactivation
# ---------------------------------------------------------------------------


def test_deactivate_user_revokes_an_existing_web_session(superuser: User) -> None:
    """The §1 probe promoted: deactivation kills a live web session next request."""
    from django.utils import timezone

    target = _make_user(930000116, consent_given_at=timezone.now())

    client = Client()
    client.force_login(target)
    assert client.get(_DASHBOARD_URL).status_code == 200

    deactivate_users(User.objects.filter(pk=target.pk), superuser)

    assert client.get(_DASHBOARD_URL).status_code == 302


def test_deactivate_user_leaves_the_django_session_row_in_place(
    superuser: User,
) -> None:
    """KNOWN GAP (owner: ``15-AUTHZ-001``): the session row survives.

    Deactivation revokes the *identity* on the next request (previous test) but
    does **not** delete the ``django_session`` row — it is inert but retained
    until ``expire_date``. Session revocation/cleanup for account-state changes
    is deferred-work ``D-1``/``D-3`` and gate ``G-A``; it belongs to phase 15
    ``15-AUTHZ-001``. This asserts the residual deliberately.
    """
    from django.contrib.sessions.models import Session
    from django.utils import timezone

    target = _make_user(930000117, consent_given_at=timezone.now())

    client = Client()
    client.force_login(target)
    assert client.get(_DASHBOARD_URL).status_code == 200
    assert Session.objects.exists()

    deactivate_users(User.objects.filter(pk=target.pk), superuser)

    # The row survives; only the per-request identity check changed.
    assert Session.objects.exists()


def test_deactivate_users_service_is_idempotent(superuser: User) -> None:
    """A second deactivation finds no enabled rows and reports ``changed == 0``."""
    target = _make_user(930000118)

    first = deactivate_users(User.objects.filter(pk=target.pk), superuser)
    second = deactivate_users(User.objects.filter(pk=target.pk), superuser)

    assert first.changed == 1
    assert second.changed == 0


def test_reactivate_user_restores_an_enabled_account(superuser: User) -> None:
    """Reactivation sets ``is_active`` back to ``True``."""
    target = _make_user(930000119, is_active=False)

    result = reactivate_users(User.objects.filter(pk=target.pk), superuser)

    assert result.changed == 1
    target.refresh_from_db()
    assert target.is_active is True


# ---------------------------------------------------------------------------
# 12-13: operator messaging
# ---------------------------------------------------------------------------


def test_operator_message_states_the_bot_tier_and_the_support_carve_out(
    superuser: User,
) -> None:
    """The toast states the true enforcement on both tiers plus Support.

    Plan 19 (``19-D2``): ``is_active`` is enforced on the web **and** in the
    Telegram bot; the only carve-out is the support restoration channel. The
    old toast claimed the change was *"NOT enforced in the Telegram bot"* —
    false once plan 19 landed, so this test asserts the **new, true** facts.

    Asserts **hard-coded** invariant substrings, not the imported constant: a
    test that pins ``DEACTIVATION_ENFORCEMENT_NOTE in text`` while importing
    ``DEACTIVATION_ENFORCEMENT_NOTE`` from the module under test is a tautology
    — it stays green if the constant is reworded to anything. The literals
    below are the load-bearing facts and must be reworded only by changing this
    test too.
    """
    target = _make_user(930000120)

    client = Client()
    client.force_login(superuser)
    response = client.post(
        reverse("admin:users_user_changelist"),
        data={
            "action": "deactivate_user",
            "_selected_action": [str(target.pk)],
            "index": "0",
        },
        follow=True,
    )

    text = _messages_text(response)
    assert "immediately on the website" in text
    assert "enforced in the Telegram bot" in text
    assert "contact Support" in text
    # The old, now-false claim must be gone.
    assert "NOT enforced in the Telegram bot" not in text


def test_operator_message_reports_skipped_rows(
    staff_user: User, superuser: User
) -> None:
    """``18-D1``: a partial selection reports the **count** of refused rows.

    Asserts the real number, not just the label: ``"Skipped: 0 self, 0
    privileged"`` must fail. The moderator selects one seller and one
    superuser, so exactly one row is refused and the toast must say so.
    """
    seller = _make_user(930000121)

    client = Client()
    client.force_login(staff_user)
    response = client.post(
        reverse("admin:users_user_changelist"),
        data={
            "action": "deactivate_user",
            "_selected_action": [str(seller.pk), str(superuser.pk)],
            "index": "0",
        },
        follow=True,
    )

    text = _messages_text(response)
    assert "Skipped:" in text
    assert "1 privileged" in text
    assert "0 privileged" not in text
    seller.refresh_from_db()
    assert seller.is_active is False


def test_operator_message_reports_already_in_state_rows(superuser: User) -> None:
    """``18-D1``: rows already in the target state are reported, not hidden.

    Selects one enabled seller and one already-disabled seller: the toast must
    report ``1 user(s)`` changed **and** name the one row that was already in
    the requested state, so a partial selection does not read as a full
    success.
    """
    fresh = _make_user(930000123)
    already_disabled = _make_user(930000124, is_active=False)

    client = Client()
    client.force_login(superuser)
    response = client.post(
        reverse("admin:users_user_changelist"),
        data={
            "action": "deactivate_user",
            "_selected_action": [str(fresh.pk), str(already_disabled.pk)],
            "index": "0",
        },
        follow=True,
    )

    text = _messages_text(response)
    assert "Deactivated 1 user(s)" in text
    assert "Skipped:" in text
    assert "1 already in the requested state" in text


# ---------------------------------------------------------------------------
# Service-shape guard (mirrors test_bulk_ban_users_not_locked)
# ---------------------------------------------------------------------------


class TestDeactivationServiceStructure:
    """Structural source guards, mirroring ``test_bulk_ban_users_not_locked``.

    **What these cover:** that each public service function and the shared
    resolver still wrap their write in ``transaction.atomic`` and do not take a
    ``select_for_update`` lock. **What they do not cover:** behaviour (the
    other tests do that), and — because they are substring checks on source —
    a comment mentioning ``transaction.atomic`` would satisfy the positive
    assertion, and a comment containing ``select_for_update`` would trip the
    negative one. They are a coarse regression net for the two documented
    decisions, not a proof of execution.
    """

    @staticmethod
    def test_deactivate_users_is_atomic_and_not_locked() -> None:
        """``deactivate_users`` wraps its bulk update and takes no ``FOR UPDATE``.

        A single bulk ``UPDATE`` with no prior read has no read-then-write
        window, so ``select_for_update()`` would buy nothing (unlike
        ``ban_user_for_ad``). Do not "fix" this.
        """
        src = inspect.getsource(deactivate_users)
        assert "transaction.atomic()" in src
        assert "select_for_update" not in src

    @staticmethod
    def test_reactivate_users_is_atomic_and_not_locked() -> None:
        """``reactivate_users`` has the same shape as its inverse."""
        src = inspect.getsource(reactivate_users)
        assert "transaction.atomic()" in src
        assert "select_for_update" not in src

    @staticmethod
    def test_resolve_targets_takes_no_row_lock() -> None:
        """The shared resolver must not grow a ``select_for_update`` either.

        A lock added here would apply to both public functions; this guard
        catches it in the one place the other two source checks cannot see.
        """
        src = inspect.getsource(_resolve_targets)
        assert "select_for_update" not in src
