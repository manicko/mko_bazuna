"""Behavioural tests for the consent actor and mechanism (06-NEW-02, BLOCK 18).

The owner's complaint is that a ``ConsentRecord`` cannot distinguish *subject
withdrew / staff revoked / system revoked*, so the **audit meaning** of the
ledger is incomplete. These tests therefore assert on values **re-read from the
database**, never on a settings or source check and never on a symbol's presence.

The actor definition under test: the actor is the account that performed the
action, recorded only when it is **not the subject**. Invariant: ``initiated_by
IS NOT NULL`` only when it is a different row from ``user``. ``action_source`` is
authoritative for which case a row is; a null ``initiated_by`` covers a
self-service action, an anonymous visitor and a system action, which
``action_source`` tells apart.

Eight behaviours, one per acceptance criterion. ``conftest.py`` is contended, so
module-local fixtures use ``get_or_create`` (the ``--reuse-db`` pattern).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.admin.sites import AdminSite
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.core.enums import ConsentActionSource, ConsentChoice, CookieCategory
from apps.users.admin import ConsentRecordAdmin
from apps.users.models import ConsentRecord, User
from apps.users.services.consent_record import record_consent_action_with_context
from apps.users.services.deletion import withdraw_consent

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# Distinct telegram_id block: 9300004xx is owned by this module.
_SUPERUSER_ID = 930000401
_TARGET_ID = 930000402
_SYSTEM_SUBJECT_ID = 930000403
_FINGERPRINT_DAYS = 90

_CHANGELIST = "admin:users_user_changelist"
_ACTION = "withdraw_consent_action"


def _user(telegram_id: int, **overrides: object) -> User:
    defaults: dict[str, object] = {
        "telegram_id": telegram_id,
        "chat_id": telegram_id,
        "password": "x",
    }
    defaults.update(overrides)
    return User.objects.create(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def superuser() -> User:
    """A superuser — the only actor allowed to reach the withdraw action."""
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


def _post_action(client: Client, user_ids: list[int]):
    return client.post(
        reverse(_CHANGELIST),
        data={
            "action": _ACTION,
            "index": 0,
            "_selected_action": [str(pk) for pk in user_ids],
            "select_across": "0",
        },
        follow=True,
    )


# ---------------------------------------------------------------------------
# 1. Subject's own withdrawal vs. a superuser's admin revocation of another
#    subject: distinguishable from stored values alone, no join.
# ---------------------------------------------------------------------------


class TestSubjectVsStaffDistinguishable:
    def test_stored_values_separate_the_two_cases(
        self, superuser: User
    ) -> None:
        """A self-service withdrawal and a staff revocation differ on stored values.

        The self-service row names the subject and carries **no separate acting
        account**; the staff row names the target as subject, names the
        **superuser** as the acting account, and records the staff mechanism — so
        the staff revocation no longer reads as a subject withdrawal.
        """
        subject = _user(930000410)
        target = _user(930000411)

        # Subject's own web withdrawal, driven through the domain service the
        # view calls (bare call == self-service).
        withdraw_consent(subject)

        # Staff revocation of a different subject, driven through the real admin
        # action endpoint.
        client = Client()
        client.force_login(superuser)
        _post_action(client, [target.pk])

        subject_row = ConsentRecord.objects.get(user=subject)
        staff_row = ConsentRecord.objects.get(user=target)

        # Self-service: subject named, no acting account, self-service mechanism.
        assert subject_row.user_id == subject.pk
        assert subject_row.initiated_by_id is None
        assert subject_row.action_source == ConsentActionSource.SELF_SERVICE.value

        # Staff: target is the subject, the superuser is the acting account.
        assert staff_row.user_id == target.pk
        assert staff_row.initiated_by_id == superuser.pk
        assert staff_row.action_source == ConsentActionSource.ADMIN_STAFF.value
        # The two rows differ on the actor and the mechanism with no join.
        assert staff_row.initiated_by_id != subject_row.initiated_by_id
        assert staff_row.action_source != subject_row.action_source

    def test_self_action_never_stores_the_subject_as_its_own_actor(self) -> None:
        """Invariant: initiated_by is not null only when it differs from user."""
        subject = _user(930000412)
        withdraw_consent(subject, initiated_by=subject)

        row = ConsentRecord.objects.get(user=subject)
        assert row.initiated_by_id is None


# ---------------------------------------------------------------------------
# 2. System is distinguishable; no live writer emits unknown.
# ---------------------------------------------------------------------------


class TestSystemAndUnknown:
    def test_system_row_is_storable_and_distinguishable(self) -> None:
        """A SYSTEM row carries no actor and differs from every other case.

        ``SYSTEM`` has **no production writer today** and that is expected: it
        exists because the owner named "system revoked" as one of the three
        cases and a closed vocabulary stops a fourth spelling. Driving the real
        writer proves it is storable and distinguishable.
        """
        subject = _user(_SYSTEM_SUBJECT_ID)
        row = record_consent_action_with_context(
            subject,
            ConsentChoice.WITHDRAWN,
            {CookieCategory.ANALYTICS: False, CookieCategory.PREFERENCES: False},
            action_source=ConsentActionSource.SYSTEM,
        )

        assert row.user_id == subject.pk
        assert row.initiated_by_id is None
        assert row.action_source == ConsentActionSource.SYSTEM.value
        # Distinguishable from a self-service row: same subject shape, different
        # mechanism. (No staff/system row is equal on action_source.)
        assert row.action_source != ConsentActionSource.SELF_SERVICE.value
        assert row.action_source != ConsentActionSource.ADMIN_STAFF.value

    def test_no_live_writer_emits_unknown(self, superuser: User) -> None:
        """Every real write path stores a specific member, never ``unknown``."""
        web_subject = _user(930000420)
        staff_target = _user(930000421)

        # Path 1: anonymous web accept (anonymous mechanism).
        anon_client = Client()
        anon_client.post("/consent/accept/")

        # Path 2: authenticated self-service withdrawal (self-service).
        withdraw_consent(web_subject)

        # Path 3: staff admin revocation (admin_staff).
        client = Client()
        client.force_login(superuser)
        _post_action(client, [staff_target.pk])

        written = list(ConsentRecord.objects.all())
        assert written, "the three paths must have written rows"
        sources = {row.action_source for row in written}
        assert ConsentActionSource.UNKNOWN.value not in sources
        assert sources <= {
            ConsentActionSource.SELF_SERVICE.value,
            ConsentActionSource.ANONYMOUS_WEB.value,
            ConsentActionSource.ADMIN_STAFF.value,
        }


# ---------------------------------------------------------------------------
# 3. Anonymous row is positively marked and distinct from the system row.
# ---------------------------------------------------------------------------


class TestAnonymousRow:
    def test_anonymous_row_is_positively_marked(self) -> None:
        """An anonymous accept carries no subject, no actor, anonymous_web, and a key."""
        client = Client()
        client.post("/consent/accept/")

        row = ConsentRecord.objects.get()
        assert row.user_id is None
        assert row.initiated_by_id is None
        assert row.action_source == ConsentActionSource.ANONYMOUS_WEB.value
        assert row.session_key  # non-null: the row is attributable

    def test_anonymous_row_differs_from_system_row_with_no_join(self) -> None:
        """Both have no subject and no actor; the mechanism separates them."""
        anon_client = Client()
        anon_client.post("/consent/accept/")
        anon_row = ConsentRecord.objects.get()

        system_row = record_consent_action_with_context(
            _user(930000430),
            ConsentChoice.WITHDRAWN,
            {CookieCategory.ANALYTICS: False, CookieCategory.PREFERENCES: False},
            action_source=ConsentActionSource.SYSTEM,
        )

        assert anon_row.user_id is None
        assert anon_row.initiated_by_id is None
        assert system_row.initiated_by_id is None
        assert anon_row.action_source != system_row.action_source


# ---------------------------------------------------------------------------
# 4. The ledger survives the acting account's deletion.
# ---------------------------------------------------------------------------


class TestLedgerSurvivesActorDeletion:
    def test_actor_hard_delete_leaves_the_row_and_nulls_only_the_pointer(
        self, superuser: User
    ) -> None:
        """Deleting the acting staff user leaves the revoked subject's row intact."""
        target = _user(930000440)
        client = Client()
        client.force_login(superuser)
        _post_action(client, [target.pk])

        before = ConsentRecord.objects.get(user=target)
        assert before.initiated_by_id == superuser.pk

        # Delete the acting staff account the way consent_hard_delete does.
        User.objects.filter(pk=superuser.pk).delete()

        after = ConsentRecord.objects.get(pk=before.pk)
        assert after.user_id == target.pk
        assert after.choice == ConsentChoice.WITHDRAWN.value
        assert after.categories == {"analytics": False, "preferences": False}
        assert after.initiated_by_id is None  # SET_NULL: pointer emptied, row kept

    def test_subject_hard_delete_leaves_its_own_rows(self) -> None:
        """A self-attributed subject's own hard delete leaves its consent rows."""
        subject = _user(930000441)
        withdraw_consent(subject)
        pk = ConsentRecord.objects.get(user=subject).pk

        User.objects.filter(pk=subject.pk).delete()

        row = ConsentRecord.objects.get(pk=pk)
        assert row.user_id is None
        assert row.initiated_by_id is None
        assert row.choice == ConsentChoice.WITHDRAWN.value


# ---------------------------------------------------------------------------
# 5. The sweep clears fingerprint fields but leaves the staff actor readable.
# ---------------------------------------------------------------------------


class TestSweepRetainsStaffActor:
    def test_sweep_clears_fingerprint_but_keeps_staff_actor(
        self, superuser: User
    ) -> None:
        """An aged staff-revocation row keeps its actor after the 90-day sweep."""
        target = _user(930000450)
        client = Client()
        client.force_login(superuser)
        _post_action(client, [target.pk])

        row = ConsentRecord.objects.get(user=target)
        # Age the row past the fingerprint window (auto_now_add bypassed).
        ConsentRecord.objects.filter(pk=row.pk).update(
            consent_given_at=timezone.now()
            - timedelta(days=_FINGERPRINT_DAYS + 1)
        )

        call_command("purge_consent_records")

        row.refresh_from_db()
        # Fingerprint cleared...
        assert row.user_id is None
        assert row.session_key is None
        assert row.ip_address is None
        assert row.user_agent == ""
        # ...the row survives and the acting staff account is still readable.
        assert row.action_source == ConsentActionSource.ADMIN_STAFF.value
        assert row.initiated_by_id == superuser.pk
        assert User.objects.filter(pk=superuser.pk).exists()

    def test_aged_self_service_row_has_no_actor_to_preserve(self) -> None:
        """An aged self-service row has no acting account, and still the row stays."""
        subject = _user(930000451)
        withdraw_consent(subject)
        row = ConsentRecord.objects.get(user=subject)
        ConsentRecord.objects.filter(pk=row.pk).update(
            consent_given_at=timezone.now()
            - timedelta(days=_FINGERPRINT_DAYS + 1)
        )

        call_command("purge_consent_records")

        row.refresh_from_db()
        assert row.user_id is None
        assert row.initiated_by_id is None
        assert row.action_source == ConsentActionSource.SELF_SERVICE.value


# ---------------------------------------------------------------------------
# 6. A superuser cannot forge accountability through the admin.
# ---------------------------------------------------------------------------


class TestAdminCannotForge:
    def test_change_form_does_not_alter_actor_or_mechanism(
        self, superuser: User
    ) -> None:
        """A POSTed actor/mechanism on the change form does not change stored values."""
        subject = _user(930000460)
        row = record_consent_action_with_context(
            subject,
            ConsentChoice.WITHDRAWN,
            {CookieCategory.ANALYTICS: False, CookieCategory.PREFERENCES: False},
            action_source=ConsentActionSource.SELF_SERVICE,
        )
        other = _user(930000461)

        client = Client()
        client.force_login(superuser)
        response = client.post(
            reverse("admin:users_consentrecord_change", args=[row.pk]),
            data={
                "initiated_by": str(other.pk),
                "action_source": ConsentActionSource.ADMIN_STAFF.value,
                "_save": "Save",
            },
        )
        assert response.status_code == 302

        row.refresh_from_db()
        assert row.initiated_by_id is None
        assert row.action_source == ConsentActionSource.SELF_SERVICE.value

    def test_changelist_can_be_filtered_by_mechanism(self, superuser: User) -> None:
        """The consent changelist exposes an action_source filter."""
        subject = _user(930000462)
        record_consent_action_with_context(
            subject,
            ConsentChoice.WITHDRAWN,
            {CookieCategory.ANALYTICS: False, CookieCategory.PREFERENCES: False},
            action_source=ConsentActionSource.ADMIN_STAFF,
        )

        client = Client()
        client.force_login(superuser)
        response = client.get(
            reverse("admin:users_consentrecord_changelist"),
            {"action_source": ConsentActionSource.ADMIN_STAFF.value},
        )

        assert response.status_code == 200
        # The filter control is present and the mechanism is offered; the
        # changelist result set is narrowed to the staff row.
        body = response.content.decode()
        assert "action_source" in body
        result_ids = [obj.pk for obj in response.context["cl"].result_list]
        assert result_ids == [ConsentRecord.objects.get(user=subject).pk]


# ---------------------------------------------------------------------------
# 7. Legacy rows read honestly.
# ---------------------------------------------------------------------------


class TestLegacyRowReadsHonestly:
    def test_legacy_row_is_unknown_and_actorless(self) -> None:
        """A pre-existing row (column default) is unknown + null actor, and is
        distinguishable from every row written after this change."""
        subject = _user(930000470)
        # Simulate a legacy row by taking the column default.
        legacy = ConsentRecord.objects.create(
            user=subject,
            choice=ConsentChoice.ACCEPTED.value,
            categories={"analytics": True},
            session_key="legacy-key",
        )
        legacy.refresh_from_db()
        assert legacy.action_source == ConsentActionSource.UNKNOWN.value
        assert legacy.initiated_by_id is None

        # A row written after this change never reads unknown.
        fresh = record_consent_action_with_context(
            subject,
            ConsentChoice.WITHDRAWN,
            {CookieCategory.ANALYTICS: False, CookieCategory.PREFERENCES: False},
            action_source=ConsentActionSource.SELF_SERVICE,
        )
        assert fresh.action_source != legacy.action_source


def test_consent_record_admin_marks_both_new_fields_readonly() -> None:
    """The admin declares the actor and mechanism read-only (anti-forgery)."""
    admin = ConsentRecordAdmin(ConsentRecord, AdminSite())
    assert "initiated_by" in admin.readonly_fields
    assert "action_source" in admin.readonly_fields
