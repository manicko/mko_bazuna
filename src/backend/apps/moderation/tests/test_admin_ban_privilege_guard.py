"""
Admin-action tests for the operator ban privilege guard (plan 19, ``B-1``/``B-3``).

Seeds `B-1`'s minimum behavioural proof that the ``is_banned`` lever now has the
same two-layer protection the ``is_active`` lever has (plan 18). ``B-3`` extends
this SAME module with the remaining inventory; it must not create a second file
and must not rewrite these.

The guard is a **target scope** in the service layer
(``apps.moderation.admin_actions._resolve_ban_targets``), shared by both ban
writers, plus a truthful operator toast on the ``AdAdmin`` changelist action and
a refusal notice on the ``moderation:ban`` view.

Literal-guard discipline (LOAD-BEARING — do not "de-duplicate")
--------------------------------------------------------------
Some tests assert **hard-coded** substrings (``"Banned 1 user(s)"``,
``"Skipped:"``, ``"1 privileged"``, ``"refuses login and publishing"``,
``"locked out everywhere"``, ...) rather than importing the constants or building
the expected string from the result object. That duplication is deliberate: a
test that pins ``BAN_TIER_ENFORCEMENT in text`` while importing
``BAN_TIER_ENFORCEMENT`` from the module under test is a tautology which stays
green after the constant is reworded — even to something the operator should
never read. This is the hazard
``test_admin_deactivate_user.py::test_operator_message_names_the_bot_tier_limit``
documents. A future editor must not "fix" the duplication: the guards exist so
that rewording an invariant fails here.

The **one** deliberate exception is
``test_ban_tier_wording_is_identical_on_both_surfaces``: it imports both
constants on purpose because its assertion is about *equality* between the two
surfaces (a drift pin), not about the content. See that test's docstring.

The three operator-message tests (the ``AdAdmin`` toast and the ``moderation:ban``
view notice) are a **security-relevant pin**, not coverage theatre: all of
``B-2``'s operator copy was unpinned before them (plan §17.3). The refusal
*sentences* are pinned the same way: ``test_each_refusal_sentence_names_its_own_cause``
hard-codes each value's distinguishing clause, and the view test hard-codes the
``PRIVILEGED`` discriminator, so a swap of two refusal values goes red rather
than surviving behind their shared ``"not applied"`` prefix. The two message-level
tests assert ``msg.level`` (``ERROR`` for a fully-refused selection, ``SUCCESS``
for a partial one) and the two scope tests assert the resolver's returned
``target_scope`` marker — both hard-coded, neither re-derived from the constant
under test.

``conftest.py`` is contended territory and supplies no admin/superuser fixture,
so ``staff_user`` / ``superuser`` and ``_make_user`` are module-local, built with
``get_or_create`` on the reserved unclaimed ``9300003xx`` block (``93xxxxxxx`` is
the users-test block; ``900000xxx`` belongs to the moderation tests; ``99xxxxxxx``
to analytics/search) so ``--reuse-db`` works. Assert observable state and counts,
never query shapes; a test that re-derived the exclusion in its body would pass
vacuously.
"""

from __future__ import annotations

import inspect

import pytest
from django.contrib import messages
from django.test import Client
from django.urls import reverse

from apps.ads.admin import BAN_TIER_ENFORCEMENT as ADS_BAN_TIER_ENFORCEMENT
from apps.ads.models import Ad
from apps.core.enums import AdStatus, ModeratorActionType
from apps.moderation.admin_actions import (
    _resolve_ban_targets,
    ban_user_for_ad,
    bulk_ban_users,
)
from apps.moderation.models import ModeratorActionLog
from apps.moderation.views import review
from apps.users.models import User
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# Reserved ``9300003xx`` block (unclaimed at B-1; B-3 uses ``313``-``321``; see
# module docstring). Distinct from ``9300001xx`` (users tests) and ``9300002xx``
# (users password recovery).
_STAFF_ID = 930000301
_SUPERUSER_ID = 930000302


def _reset_ban(user: User) -> User:
    """Clear ``is_banned`` on a reused fixture row (``--reuse-db`` safety).

    The ``staff_user`` / ``superuser`` fixtures are built with ``get_or_create``
    so ``--reuse-db`` works, but the row then persists across the whole test
    session. No current test bans either row — both are always refused by the
    guard — yet a future test that successfully bans one would otherwise poison
    the fixture for every later test in the session. Resetting the flag on
    acquire removes that latent ordering hazard.
    """
    if user.is_banned:
        user.is_banned = False
        user.save(update_fields=["is_banned"])
    return user


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
    return _reset_ban(user)


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
    return _reset_ban(user)


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
# 2b. 19-D7 — the resolver's scope marker names the scope that governed.
# ---------------------------------------------------------------------------


def test_resolve_ban_targets_marker_is_unrestricted_for_a_superuser(
    superuser: User,
) -> None:
    """A superuser actor gets the ``"unrestricted"`` scope marker.

    ``19-D7`` widened the resolver's return to a 3-tuple carrying the scope the
    write actually ran under, so a caller that logs it cannot name a scope
    different from the one that governed the write (§15.1 finding 2). This pins
    the superuser branch by its returned value — a hard-coded literal, not an
    import that would make the assertion tautological — and swaps the
    ``"unrestricted"`` / ``"non_privileged_only"`` literals would go red.
    """
    target = _make_user(930000320)

    _, _, target_scope = _resolve_ban_targets([target.pk], superuser.id)

    assert target_scope == "unrestricted"


def test_resolve_ban_targets_marker_is_restricted_for_a_non_superuser(
    staff_user: User,
) -> None:
    """A non-superuser actor gets the ``"non_privileged_only"`` scope marker.

    The counterpart to the superuser test: the marker is derived from the same
    ``actor_is_superuser`` lookup that chose the branch, so a non-superuser actor
    must be labelled with the restricted scope the guard actually applied.
    """
    target = _make_user(930000321)

    _, _, target_scope = _resolve_ban_targets([target.pk], staff_user.id)

    assert target_scope == "non_privileged_only"


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

    §15.1 finding 3 (§17.3): ``skipped_privileged == 0`` is asserted for a row
    that is **both** self **and** privileged. Without it, dropping
    ``.exclude(pk=moderator_id)`` from the privileged **count** would go
    undetected, because the two other ``skipped_privileged == 0`` assertions in
    this module are superuser-actor cases where the privileged count is 0 anyway.
    This is reporting accuracy; the write scope is unaffected either way.
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
    # The moderator's own row is ``is_staff=True`` and is the actor's row: it is
    # counted once, as self. The privileged count must stay 0.
    assert moderator_result.skipped_privileged == 0
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

    @staticmethod
    def test_ban_user_for_ad_keeps_its_lock_inside_atomic() -> None:
        """Completion of §3's structural inventory for the two ban writers.

        The existing ``TestBulkLockingStructure::test_bulk_ban_users_not_locked``
        (in ``test_admin_actions.py``) already pins ``bulk_ban_users``' negative
        lock invariant and is left byte-unchanged. Its positive counterpart
        ``test_ban_user_for_ad_uses_atomic`` lives there too. This adds the
        equivalent in-module guard for the single-ad writer's **positive**
        invariant — the lock is legitimate (a read-then-write on the instance)
        and must be kept — so the inventory is complete in one place without
        moving or rewriting the tripwire tests.
        """
        src = inspect.getsource(ban_user_for_ad)
        assert "transaction.atomic" in src
        assert "select_for_update" in src

    @staticmethod
    def test_bulk_ban_users_is_atomic_and_not_locked() -> None:
        """The bulk writer's invariants, restated in-module (see the sibling test).

        ``test_admin_actions.py::TestBulkLockingStructure`` owns the canonical
        tripwires; this is the in-module copy that completes the inventory the
        ``B-3`` task requires. It must agree with that file: ``transaction.atomic``
        present, ``select_for_update`` absent.
        """
        src = inspect.getsource(bulk_ban_users)
        assert "transaction.atomic" in src
        assert "select_for_update" not in src


# ---------------------------------------------------------------------------
# 10-11. Actor reachability — an anti-vacuity pair.
# ---------------------------------------------------------------------------


def test_non_staff_cannot_reach_the_ban_action(category, city) -> None:
    """A plain non-staff seller never reaches the action; a POST changes nothing.

    Paired with ``test_moderator_and_superuser_can_reach_the_ban_action`` so the
    pair cannot pass vacuously: without the positive control this test would stay
    green even if the action were simply broken for everyone.
    """
    actor = _make_user(930000313)
    target = _make_user(930000314)
    ad = create_test_ad(target, category, city, status=AdStatus.ON_MODERATION)

    client = Client()
    client.force_login(actor)
    response = client.get(reverse("admin:ads_ad_changelist"))
    # A non-staff user is redirected to the admin login: AdminSite.has_permission
    # returns False. That 302 is the real actor gate.
    assert response.status_code == 302

    client.post(
        reverse("admin:ads_ad_changelist"),
        data={
            "action": "action_ban_user",
            "_selected_action": [str(ad.pk)],
            "index": "0",
        },
    )
    target.refresh_from_db()
    assert target.is_banned is False


def test_moderator_and_superuser_can_reach_the_ban_action(
    staff_user: User, superuser: User, category, city
) -> None:
    """Positive control: both admin classes reach the action (anti-vacuity).

    Without this, ``test_non_staff_cannot_reach_the_ban_action`` passes if the
    action is simply absent for everyone. The action is driven over the real ads
    changelist, whose ``_selected_action`` values are **Ad** pks (the action
    resolves the users from the selected ads).
    """
    moderator_target = _make_user(930000315)
    superuser_target = _make_user(930000316)
    moderator_ad = create_test_ad(
        moderator_target, category, city, status=AdStatus.ON_MODERATION
    )
    superuser_ad = create_test_ad(
        superuser_target, category, city, status=AdStatus.ON_MODERATION
    )

    for actor, ad, target in (
        (staff_user, moderator_ad, moderator_target),
        (superuser, superuser_ad, superuser_target),
    ):
        client = Client()
        client.force_login(actor)
        response = client.get(reverse("admin:ads_ad_changelist"))
        assert response.status_code == 200
        response = client.post(
            reverse("admin:ads_ad_changelist"),
            data={
                "action": "action_ban_user",
                "_selected_action": [str(ad.pk)],
                "index": "0",
            },
            follow=True,
        )
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.is_banned is True


# ---------------------------------------------------------------------------
# 12-14. The operator-message contract — the two-sided tier truth.
#
# These three drive real endpoints and read the messages off the response, and
# they assert HARD-CODED substrings (see the module docstring). All of B-2's
# operator copy was unpinned before them (plan §17.3).
# ---------------------------------------------------------------------------


def test_ban_operator_message_states_the_two_sided_tier_truth(
    staff_user: User, superuser: User, category, city
) -> None:
    """The ``AdAdmin`` toast carries the positive tier truth, exactly once.

    Supersedes §3's ``test_operator_message_does_not_claim_total_lockout``,
    which asserted **absence only** and therefore passed vacuously even if every
    tier clause were deleted (§17.3/W2).

    A mixed selection is used so the message is the *partial* branch: the
    four-clause family is still the whole statement, and the tier sentence is one
    statement, not boilerplate repeated per clause.
    """
    seller = _make_user(930000317)
    seller_ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
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
    # Positive half: the three tier clauses are present as hard-coded literals.
    assert "refuses login and publishing" in text
    assert "is enforced in the Telegram bot" in text
    assert "does not revoke an existing web session" in text
    # Anti-over-claim half: these must never appear.
    assert "locked out everywhere" not in text
    assert "cannot get back in" not in text
    # One statement, not boilerplate: the tier clause appears exactly once.
    assert text.count("refuses login and publishing") == 1


def test_fully_refused_ban_toast_is_reported_at_error_level(
    staff_user: User, superuser: User, category, city
) -> None:
    """A fully-refused ``action_ban_user`` escalates the toast to ``ERROR``.

    ``19-D6`` introduced the escalation: a selection where nothing was banned
    (``changed == 0`` with a non-zero skip count) is reported at ``error`` so a
    security-adjacent refusal does not arrive as a false-success toast. Reverting
    ``action_ban_user`` to a flat ``level="success"`` would otherwise turn nothing
    red. This is the repo's first assertion on ``msg.level`` — the level is read
    off the real ``messages`` framework through the admin endpoint, not
    re-derived from the production constant.
    """
    superuser_ad = create_test_ad(
        superuser, category, city, status=AdStatus.ON_MODERATION
    )

    client = Client()
    client.force_login(staff_user)
    response = client.post(
        reverse("admin:ads_ad_changelist"),
        data={
            "action": "action_ban_user",
            "_selected_action": [str(superuser_ad.pk)],
            "index": "0",
        },
        follow=True,
    )

    recorded = list(response.context["messages"])
    assert len(recorded) == 1
    assert recorded[0].level == messages.ERROR
    superuser.refresh_from_db()
    assert superuser.is_banned is False


def test_partially_refused_ban_toast_keeps_success_level(
    staff_user: User, superuser: User, category, city
) -> None:
    """The benign counterpart: a partial success keeps its existing ``SUCCESS``.

    ``19-D6`` escalates **only** the fully-refused case. When at least one ban
    took effect the action did take effect, so the level must stay ``success`` —
    this pins that the escalation is not applied indiscriminately.
    """
    seller = _make_user(930000319)
    seller_ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
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

    recorded = list(response.context["messages"])
    assert len(recorded) == 1
    assert recorded[0].level == messages.SUCCESS
    seller.refresh_from_db()
    assert seller.is_banned is True


def test_ban_view_refusal_states_the_two_sided_tier_truth(
    staff_user: User, category, city
) -> None:
    """The ``moderation:ban`` view refusal states the tier truth, exactly once.

    The **refusal path and its copy** had no test before ``B-3`` — that is the
    gap ``R1`` was really about (``R1`` was found on the admin toast, but the fix
    had to land on both surfaces). This is NOT the first ban test on this view:
    ``test_moderation_views.py::TestBanUserView`` already covers the success
    path (``test_ban_marks_user_as_banned``, ``test_ban_creates_moderation_log``,
    ``test_ban_requires_post``, ``test_ban_defaults_reason_when_not_provided``),
    so a future editor must not duplicate that class here. The ad is owned by a
    peer ``is_staff`` moderator, so the refusal reason is ``PRIVILEGED``.
    """
    peer_moderator = _make_user(930000318, is_staff=True)
    ad = create_test_ad(peer_moderator, category, city, status=AdStatus.ON_MODERATION)

    client = Client()
    client.force_login(staff_user)
    response = client.post(
        reverse("moderation:ban", args=[ad.id]),
        data={"ban_reason": "policy violation"},
        follow=True,
    )

    # A clean non-500 outcome (the redirect followed to the admin changelist).
    assert response.status_code == 200
    text = " ".join(str(m) for m in response.context["messages"])
    # The refusal sentence itself, then the three tier clauses (hard-coded).
    assert "not applied" in text
    # Discriminate the refusal reason: only the ``PRIVILEGED`` value contains
    # these two literals, so a swap with ``SELF`` / ``ALREADY_BANNED`` (or a
    # ``ban_refusal_reason`` that returns the wrong reason for a privileged
    # target) goes red. ``"not applied"`` alone matches all four values and
    # would pin that *a* refusal was reported, not *which* one.
    assert "the ad's owner is a staff or superuser" in text
    assert "not permitted to ban" in text
    assert "refuses login and publishing" in text
    assert "is enforced in the Telegram bot" in text
    assert "does not revoke an existing web session" in text
    assert text.count("refuses login and publishing") == 1
    peer_moderator.refresh_from_db()
    assert peer_moderator.is_banned is False


def test_ban_tier_wording_is_identical_on_both_surfaces() -> None:
    """Cross-surface drift pin — the **deliberate** exception to literal guards.

    Importing both constants here is CORRECT and required: the assertion is about
    *equality between the two surfaces* (a drift pin), not about the content. A
    hard-coded copy of the string would pin the content but not the equality —
    the two surfaces could drift to different wording and both literals would
    still match one of the surfaces. So the literal-guard discipline in the
    module docstring explicitly exempts this test.

    Also pins "not boilerplate" structurally: the tier text is **not** a fifth
    member of ``_BAN_REFUSAL_MESSAGES`` and is **not** repeated inside any of the
    four refusal sentences — the tier statement is a single attached clause, not
    one sentence per refusal.
    """
    # One equality is enough: ``ADS_BAN_TIER_ENFORCEMENT`` is
    # ``apps.ads.admin.BAN_TIER_ENFORCEMENT`` imported at module top, so asserting
    # it against ``review.BAN_TIER_ENFORCEMENT`` and re-importing ``ads_admin`` to
    # assert the same object twice would pin nothing extra.
    assert ADS_BAN_TIER_ENFORCEMENT == review.BAN_TIER_ENFORCEMENT

    refusal_messages = review._BAN_REFUSAL_MESSAGES
    assert len(refusal_messages) == 4
    # Not a fifth member: the tier text is not one of the four refusal values.
    assert review.BAN_TIER_ENFORCEMENT not in refusal_messages.values()
    # Not repeated inside the four sentences either.
    for sentence in refusal_messages.values():
        assert review.BAN_TIER_ENFORCEMENT not in sentence


def test_each_refusal_sentence_names_its_own_cause() -> None:
    """Every refusal value carries its own discriminating cause, hard-coded.

    The view test exercises only the ``PRIVILEGED`` value, so a swap of the
    ``SELF`` and ``PRIVILEGED`` sentences (or any reword that erases a sentence's
    distinguishing clause) would otherwise go undetected — ``"not applied"`` is
    the shared prefix of all four. This pins each sentence's own cause with
    hard-coded literals, bringing the refusal-reason assertions to the same
    standard as ``test_not_in_target_set_refusal_copy_asserts_no_cause`` (which
    pins the full ``NOT_IN_TARGET_SET`` content directly). The literal is
    independent of the mapping's value, so this is not a tautology.
    """
    from apps.moderation.admin_actions import BanRefusalReason

    refusal_messages = review._BAN_REFUSAL_MESSAGES
    assert "the ad's owner is your own account" in refusal_messages[BanRefusalReason.SELF]
    assert (
        "the ad's owner is a staff or superuser"
        in refusal_messages[BanRefusalReason.PRIVILEGED]
    )
    assert "not permitted to ban" in refusal_messages[BanRefusalReason.PRIVILEGED]
    assert (
        "the ad's owner was already banned"
        in refusal_messages[BanRefusalReason.ALREADY_BANNED]
    )
    assert (
        "was not among the accounts available to this action"
        in refusal_messages[BanRefusalReason.NOT_IN_TARGET_SET]
    )


def test_not_in_target_set_refusal_copy_asserts_no_cause() -> None:
    """Pins ``R2``: the cause-neutral sentence is present; the false cause is gone.

    ``R2`` found that the retired wording asserted a cause
    (``"outside the set of accounts you may ban"``) that is false for the
    reachable all-zero producer (a deleted ad owner's account). The current
    sentence is deliberately cause-neutral. This is asserted against the mapping
    value directly rather than by contriving an unreachable fixture — the shape
    the ``B-2`` Validator proposed.
    """
    from apps.moderation.admin_actions import BanRefusalReason

    sentence = review._BAN_REFUSAL_MESSAGES[BanRefusalReason.NOT_IN_TARGET_SET]
    assert "was not among the accounts available to this action" in sentence
    assert "outside the set of accounts you may ban" not in sentence
