"""
Admin-action tests for the operator ban privilege guard (plan 19, ``B-1``).

Seeds `B-1`'s minimum behavioural proof that the ``is_banned`` lever now has the
same two-layer protection the ``is_active`` lever has (plan 18). ``B-3`` extends
this SAME module with the remaining inventory; it must not create a second file
and must not rewrite these.

The guard is a **target scope** in the service layer
(``apps.moderation.admin_actions._resolve_ban_targets``), shared by both ban
writers, plus a truthful operator toast on the ``AdAdmin`` changelist action.

Literal-guard discipline
------------------------
Some tests assert **hard-coded** substrings (``"Banned 1 user(s)"``,
``"Skipped:"``, ``"1 privileged"``) rather than importing the constants or
building the expected string from the result object. That duplication is
deliberate: a test that pins ``SKIPPED_BANNED_ROWS_PREFIX in text`` while
importing that prefix from the module under test is a tautology which stays green
after a reword. A future editor must not "fix" the duplication — the guards exist
so rewording the invariant fails here.

``conftest.py`` is contended territory and supplies no admin/superuser fixture,
so ``staff_user`` / ``superuser`` and ``_make_user`` are module-local, built with
``get_or_create`` on the reserved unclaimed ``9300003xx`` block (``93xxxxxxx`` is
the users-test block; ``900000xxx`` belongs to the moderation tests) so
``--reuse-db`` works. Assert observable state and counts, never query shapes; a
test that re-derived the exclusion in its body would pass vacuously.
"""

from __future__ import annotations

import inspect

import pytest
from django.test import Client
from django.urls import reverse

from apps.ads.models import Ad
from apps.core.enums import AdStatus, ModeratorActionType
from apps.moderation.admin_actions import (
    _resolve_ban_targets,
    ban_user_for_ad,
    bulk_ban_users,
)
from apps.moderation.models import ModeratorActionLog
from apps.users.models import User
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# Reserved ``9300003xx`` block (unclaimed at B-1; see module docstring).
_STAFF_ID = 930000301
_SUPERUSER_ID = 930000302


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


def _ban_account_rows(user: User | int) -> int:
    """Count ``BAN_ACCOUNT`` audit rows for one target (by pk)."""
    user_id = user.pk if isinstance(user, User) else user
    return ModeratorActionLog.objects.filter(
        user_id=user_id, action_type=ModeratorActionType.BAN_ACCOUNT
    ).count()


# ---------------------------------------------------------------------------
# 1. The 18-Q7 guard — the most important test in the plan.
# ---------------------------------------------------------------------------


def test_moderator_cannot_ban_a_superuser_or_staff_row(
    staff_user: User, superuser: User, category, city
) -> None:
    """A moderator's selection drops every privileged row; only the seller changes.

    The selection deliberately covers **both** privilege axes: a peer
    ``is_staff`` moderator, the full ``superuser`` fixture, and a row with
    ``is_superuser=True, is_staff=False``. That last row is the reason
    ``.exclude(is_superuser=True)`` cannot be dropped — the fixture sets both
    flags, so without this row the ``is_superuser`` exclusion would be untested.
    """
    seller = _make_user(930000303)
    peer_moderator = _make_user(930000304, is_staff=True)
    superuser_only = _make_user(930000305, is_superuser=True, is_staff=False)
    for owner in (seller, peer_moderator, superuser, superuser_only):
        create_test_ad(owner, category, city, status=AdStatus.ON_MODERATION)

    result = bulk_ban_users(
        Ad.objects.filter(
            user_id__in=[
                seller.pk,
                peer_moderator.pk,
                superuser.pk,
                superuser_only.pk,
            ]
        ),
        staff_user.id,
        "policy violation",
    )

    assert result.changed == 1
    assert result.skipped_privileged == 3
    seller.refresh_from_db()
    peer_moderator.refresh_from_db()
    superuser.refresh_from_db()
    superuser_only.refresh_from_db()
    assert seller.is_banned is True
    assert peer_moderator.is_banned is False
    assert superuser.is_banned is False
    assert superuser_only.is_banned is False


# ---------------------------------------------------------------------------
# 2. The positive half — the guard cannot be over-applied.
# ---------------------------------------------------------------------------


def test_superuser_can_ban_a_staff_row(
    superuser: User, category, city
) -> None:
    """A superuser's selection is unrestricted: a peer staff row is banned."""
    peer_staff = _make_user(930000306, is_staff=True)
    create_test_ad(peer_staff, category, city, status=AdStatus.ON_MODERATION)

    result = bulk_ban_users(
        Ad.objects.filter(user_id=peer_staff.pk),
        superuser.id,
        "policy violation",
    )

    assert result.changed == 1
    assert result.skipped_privileged == 0
    peer_staff.refresh_from_db()
    assert peer_staff.is_banned is True


# ---------------------------------------------------------------------------
# 3. Self-exclusion is unconditional, including for a superuser (19-Q3).
# ---------------------------------------------------------------------------


def test_moderator_cannot_ban_themselves(
    staff_user: User, superuser: User, category, city
) -> None:
    """The operator's own row is never written, for a moderator AND a superuser.

    There is no un-ban path and no per-request web gate for ``is_banned``, so a
    self-ban is an operator lockout the UI cannot repair. The superuser case is
    the branch a naive ``is_superuser`` shortcut drops.
    """
    create_test_ad(staff_user, category, city, status=AdStatus.ON_MODERATION)
    create_test_ad(superuser, category, city, status=AdStatus.ON_MODERATION)

    moderator_result = bulk_ban_users(
        Ad.objects.filter(user_id=staff_user.pk),
        staff_user.id,
        "policy violation",
    )
    superuser_result = bulk_ban_users(
        Ad.objects.filter(user_id=superuser.pk),
        superuser.id,
        "policy violation",
    )

    assert moderator_result.changed == 0
    assert moderator_result.skipped_self == 1
    assert superuser_result.changed == 0
    assert superuser_result.skipped_self == 1
    staff_user.refresh_from_db()
    superuser.refresh_from_db()
    assert staff_user.is_banned is False
    assert superuser.is_banned is False


# ---------------------------------------------------------------------------
# 4. The plan-18 trap: changed means bans performed, not rows seen.
# ---------------------------------------------------------------------------


def test_bulk_ban_users_reports_bans_performed_not_rows_seen(
    superuser: User, category, city
) -> None:
    """A bare ``UPDATE`` reports MATCHED rows; the pre-filter makes ``changed`` honest.

    A superuser selects one unbanned seller and one already-banned seller:
    ``changed`` must be 1 (not 2) and ``already_in_state`` must be 1. A bare
    ``UPDATE`` would report 2 here. The privileged-refusal half of the inventory
    lives in ``test_moderator_cannot_ban_a_superuser_or_staff_row``, where it
    belongs — a superuser is unrestricted, so a privileged row would be banned
    and cannot be asserted here without weakening the focus.
    """
    fresh = _make_user(930000307)
    already_banned = _make_user(930000308, is_banned=True)
    create_test_ad(fresh, category, city, status=AdStatus.ON_MODERATION)
    create_test_ad(already_banned, category, city, status=AdStatus.ON_MODERATION)

    result = bulk_ban_users(
        Ad.objects.filter(user_id__in=[fresh.pk, already_banned.pk]),
        superuser.id,
        "policy violation",
    )

    assert result.changed == 1
    assert result.already_in_state == 1
    assert result.skipped_privileged == 0
    fresh.refresh_from_db()
    already_banned.refresh_from_db()
    assert fresh.is_banned is True
    assert already_banned.is_banned is True
    # Exactly one audit row for the one ban that happened.
    assert (
        ModeratorActionLog.objects.filter(
            action_type=ModeratorActionType.BAN_ACCOUNT,
            user_id__in=[fresh.pk, already_banned.pk],
        ).count()
        == 1
    )


# ---------------------------------------------------------------------------
# 5. Idempotence — a repeat ban is a no-op and writes no duplicate audit row.
# ---------------------------------------------------------------------------


def test_bulk_ban_users_is_idempotent_on_repeat(
    superuser: User, category, city
) -> None:
    """A second identical call reports ``changed == 0`` and no new audit row."""
    target = _make_user(930000309)
    create_test_ad(target, category, city, status=AdStatus.ON_MODERATION)

    first = bulk_ban_users(
        Ad.objects.filter(user_id=target.pk), superuser.id, "policy violation"
    )
    second = bulk_ban_users(
        Ad.objects.filter(user_id=target.pk), superuser.id, "policy violation"
    )

    assert first.changed == 1
    assert second.changed == 0
    assert second.already_in_state == 1
    assert _ban_account_rows(target) == 1


# ---------------------------------------------------------------------------
# 6. 19-G2 — a refused ban writes no audit row.
# ---------------------------------------------------------------------------


def test_a_refused_ban_writes_no_ban_account_audit_row(
    staff_user: User, superuser: User, category, city
) -> None:
    """19-G2, proven by absence: refusals leave no ``BAN_ACCOUNT`` row.

    A moderator's selection contains a privileged row and the acting
    moderator's own row; neither may produce an audit row, while the permitted
    seller produces exactly one. This goes red against the pre-guard code, where
    the audit row is written before the guard is consulted.
    """
    seller = _make_user(930000310)
    for owner in (seller, superuser, staff_user):
        create_test_ad(owner, category, city, status=AdStatus.ON_MODERATION)

    result = bulk_ban_users(
        Ad.objects.filter(
            user_id__in=[seller.pk, superuser.pk, staff_user.pk]
        ),
        staff_user.id,
        "policy violation",
    )

    assert result.changed == 1
    assert result.skipped_privileged == 1
    assert result.skipped_self == 1
    assert _ban_account_rows(seller) == 1
    assert _ban_account_rows(superuser) == 0
    assert _ban_account_rows(staff_user) == 0


# ---------------------------------------------------------------------------
# 7. G-1 — the single-ad writer is guarded too, with a positive control.
# ---------------------------------------------------------------------------


def test_ban_user_for_ad_refuses_a_privileged_owner(
    staff_user: User, superuser: User, category, city
) -> None:
    """``ban_user_for_ad`` refuses a privileged owner and still bans a seller."""
    privileged_ad = create_test_ad(
        superuser, category, city, status=AdStatus.ON_MODERATION
    )
    seller = _make_user(930000311)
    seller_ad = create_test_ad(
        seller, category, city, status=AdStatus.ON_MODERATION
    )

    refused = ban_user_for_ad(privileged_ad, staff_user.id, "policy violation")
    performed = ban_user_for_ad(seller_ad, staff_user.id, "policy violation")

    assert refused.changed == 0
    assert refused.skipped_privileged == 1
    superuser.refresh_from_db()
    assert superuser.is_banned is False
    assert _ban_account_rows(superuser) == 0

    assert performed.changed == 1
    seller.refresh_from_db()
    assert seller.is_banned is True
    assert _ban_account_rows(seller) == 1


# ---------------------------------------------------------------------------
# 8. 19-D1 — the operator toast is truthful and never a NamedTuple repr.
# ---------------------------------------------------------------------------


def test_operator_toast_reports_bans_performed_and_skipped_rows(
    staff_user: User, superuser: User, category, city
) -> None:
    """The real changelist action reports bans performed and the refused count.

    Asserts **hard-coded** literals, not imported constants, and asserts the
    ``BanResult`` repr is absent — the specific regression ``19-D1`` exists to
    prevent.
    """
    seller = _make_user(930000312)
    seller_ad = create_test_ad(
        seller, category, city, status=AdStatus.ON_MODERATION
    )
    superuser_ad = create_test_ad(
        superuser, category, city, status=AdStatus.ON_MODERATION
    )

    client = Client()
    client.force_login(staff_user)
    response = client.post(
        reverse("admin:ads_ad_changelist"),
        data={
            "action": "action_ban_user",
            "_selected_action": [str(seller_ad.pk), str(superuser_ad.pk)],
            "index": "0",
        },
        follow=True,
    )

    text = " ".join(str(m) for m in response.context["messages"])
    assert "Banned 1 user(s)" in text
    assert "Skipped:" in text
    assert "1 privileged" in text
    assert "BanResult" not in text
    seller.refresh_from_db()
    assert seller.is_banned is True


# ---------------------------------------------------------------------------
# 9. Structural guard on the new resolver.
# ---------------------------------------------------------------------------


class TestBanScopeStructure:
    """Structural source guard, mirroring ``test_bulk_ban_users_not_locked``.

    **What it covers:** that the shared resolver takes no ``select_for_update``
    lock. A lock added there would apply to both ban writers, and neither of the
    two existing function-source guards could see it. **What it does not
    cover:** behaviour (the tests above do that). Because it is a substring
    check on source, a comment mentioning the token would trip it.
    """

    @staticmethod
    def test_resolve_ban_targets_takes_no_row_lock() -> None:
        """``_resolve_ban_targets`` must not grow a ``select_for_update``."""
        src = inspect.getsource(_resolve_ban_targets)
        assert "select_for_update" not in src
