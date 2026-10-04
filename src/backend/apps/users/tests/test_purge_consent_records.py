"""Tests for the ``purge_consent_records`` retention sweep (06-PII-116, BLOCK 19).

The sweep **anonymises, never deletes** ConsentRecord rows: at the ratified R2
fingerprint window (90 days) the identity fields are cleared, at the R1 actor
window (12 months) the acting account is cleared unless held, and the decision
fields (``choice``, ``categories``, ``consent_version``, ``consent_given_at``)
are retained at every age because the row is the Art. 7(1) evidence.

Every assertion here is behavioural: a row's own field values after the real
command runs, never a private name or a count alone. ``consent_given_at`` is
``auto_now_add=True``, so rows are aged with a bulk ``update()`` that bypasses
it.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.test import RequestFactory
from django.utils import timezone

from apps.core.enums import ConsentActionSource, ConsentChoice, ConsentVersion
from apps.search.models import SavedSearch
from apps.users.context_processors import CONSENT_REPROMPT_DAYS, consent_state
from apps.users.models import ConsentRecord, User
from apps.users.services.deletion import withdraw_consent
from conftest import make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_FINGERPRINT_DAYS = 90
_ACTOR_DAYS = 365
_DECISION_DAYS = 365 * 5


def _aged_record(
    *,
    user=None,
    age_days: int,
    choice: str = ConsentChoice.ACCEPTED.value,
    session_key: str = "sess-key-abc",
    ip_address: str = "192.168.1.0",
    user_agent: str = "Mozilla/5.0 test",
    categories: dict | None = None,
    initiated_by=None,
    legal_hold: bool = False,
) -> ConsentRecord:
    """Create a ConsentRecord and age it past ``auto_now_add``."""
    record = ConsentRecord.objects.create(
        user=user,
        session_key=session_key,
        choice=choice,
        consent_version=ConsentVersion.V1_0.value,
        categories=categories if categories is not None else {"analytics": True},
        ip_address=ip_address,
        user_agent=user_agent,
        initiated_by=initiated_by,
        legal_hold=legal_hold,
    )
    ConsentRecord.objects.filter(pk=record.pk).update(
        consent_given_at=timezone.now() - timedelta(days=age_days)
    )
    record.refresh_from_db()
    return record


class TestInWindowUntouched:
    """A row inside the fingerprint window is untouched, field for field."""

    def test_row_inside_window_keeps_every_field(self, user) -> None:
        record = _aged_record(
            user=user,
            age_days=_FINGERPRINT_DAYS - 1,
            choice=ConsentChoice.DECLINED.value,
            session_key="inside-window-key",
            categories={"analytics": False, "preferences": True},
        )

        call_command("purge_consent_records")

        record.refresh_from_db()
        assert record.choice == ConsentChoice.DECLINED.value
        assert record.categories == {"analytics": False, "preferences": True}
        assert record.consent_version == ConsentVersion.V1_0.value
        assert record.session_key == "inside-window-key"
        assert record.user_id == user.id
        assert record.ip_address == "192.168.1.0"
        assert record.user_agent == "Mozilla/5.0 test"


class TestTwoStageBoundary:
    """Three rows at three ages prove the two-stage behaviour."""

    def test_three_ages(self, user) -> None:
        inside = _aged_record(
            user=user, age_days=_FINGERPRINT_DAYS - 1, session_key="k-inside"
        )
        middle = _aged_record(
            user=user, age_days=_FINGERPRINT_DAYS + 1, session_key="k-middle"
        )
        ancient = _aged_record(
            user=user, age_days=_DECISION_DAYS + 10, session_key="k-ancient"
        )

        call_command("purge_consent_records")

        for record in (inside, middle, ancient):
            record.refresh_from_db()

        # Inside the window: nothing changes.
        assert inside.session_key == "k-inside"
        assert inside.user_id == user.id

        # Between the windows: identity cleared, decision fields intact, and
        # crucially the ROW STILL EXISTS -- the anonymise-vs-delete distinction.
        assert middle.user_id is None
        assert middle.session_key is None
        assert middle.ip_address is None
        assert middle.user_agent == ""
        assert middle.choice == ConsentChoice.ACCEPTED.value
        assert middle.categories == {"analytics": True}
        assert middle.consent_version == ConsentVersion.V1_0.value

        # Past the decision window: same outcome, row retained, never deleted.
        assert ancient.user_id is None
        assert ancient.session_key is None
        assert ancient.choice == ConsentChoice.ACCEPTED.value
        assert ancient.categories == {"analytics": True}
        assert ancient.consent_version == ConsentVersion.V1_0.value


class TestNeverDeleted:
    """No ConsentRecord row is ever deleted, at any age."""

    def test_rows_survive_at_every_age(self, user) -> None:
        rows = [
            _aged_record(user=user, age_days=1),
            _aged_record(user=user, age_days=_FINGERPRINT_DAYS + 1),
            _aged_record(user=user, age_days=_DECISION_DAYS + 1),
            _aged_record(user=user, age_days=_DECISION_DAYS * 3),
        ]
        pks = [row.pk for row in rows]

        call_command("purge_consent_records")

        for pk in pks:
            assert ConsentRecord.objects.filter(pk=pk).exists()


class TestUserAgentClearedNotNull:
    """user_agent is cleared to "", not None -- the CLEAR-vs-NULL distinction."""

    def test_user_agent_is_empty_string(self, user) -> None:
        record = _aged_record(
            user=user, age_days=_FINGERPRINT_DAYS + 1, user_agent="Mozilla/5.0"
        )

        call_command("purge_consent_records")

        record.refresh_from_db()
        assert record.user_agent == ""
        assert record.user_agent is not None


class TestUserAndSessionKeyTogether:
    """user and session_key are cleared together, never one without the other."""

    def test_both_cleared(self, user) -> None:
        record = _aged_record(
            user=user, age_days=_FINGERPRINT_DAYS + 1, session_key="k-together"
        )

        call_command("purge_consent_records")

        record.refresh_from_db()
        assert record.user_id is None
        assert record.session_key is None


class TestRePromptCoupling:
    """The re-prompt boundary and the retained decision fields share one clock."""

    def test_old_row_survives_and_reprompt_fires(self, user) -> None:
        age = CONSENT_REPROMPT_DAYS + 10
        record = _aged_record(
            user=user,
            age_days=age,
            choice=ConsentChoice.ACCEPTED.value,
            categories={"analytics": True},
        )

        call_command("purge_consent_records")

        # The decision fields survive the re-prompt boundary (the row is
        # evidence for the interval that just ended).
        record.refresh_from_db()
        assert record.choice == ConsentChoice.ACCEPTED.value
        assert record.categories == {"analytics": True}
        assert record.consent_version == ConsentVersion.V1_0.value

        # Same boundary, server-side half: consent_state re-prompts.
        user.consent_given_at = timezone.now() - timedelta(days=age)
        user.save(update_fields=["consent_given_at"])
        request = RequestFactory().get("/")
        request.user = user
        request.COOKIES = {}
        context = consent_state(request)
        assert context["consent_shown"] is False


class TestDryRun:
    """--dry-run reports the same numbers and mutates nothing."""

    def test_dry_run_leaves_fields_populated(self, user, caplog) -> None:
        record = _aged_record(
            user=user,
            age_days=_FINGERPRINT_DAYS + 1,
            session_key="k-dryrun",
            user_agent="Mozilla/5.0",
        )

        with caplog.at_level("INFO"):
            call_command("purge_consent_records", "--dry-run")

        record.refresh_from_db()
        assert record.session_key == "k-dryrun"
        assert record.user_id == user.id
        assert record.ip_address == "192.168.1.0"
        assert record.user_agent == "Mozilla/5.0"
        assert "DRY RUN" in caplog.text


class TestEmptyEligibleSet:
    """An empty eligible set returns 0 -- protects the durable daily marker."""

    def test_returns_zero_with_no_rows(self) -> None:
        assert ConsentRecord.objects.count() == 0
        call_command("purge_consent_records")

    def test_returns_zero_with_only_in_window_rows(self, user) -> None:
        _aged_record(user=user, age_days=1)
        call_command("purge_consent_records")


class TestIdempotence:
    """A second run performs no further change."""

    def test_second_run_is_noop(self, user) -> None:
        record = _aged_record(user=user, age_days=_FINGERPRINT_DAYS + 1)

        call_command("purge_consent_records")
        record.refresh_from_db()
        after_first = (
            record.user_id,
            record.session_key,
            record.ip_address,
            record.user_agent,
            record.initiated_by_id,
        )

        call_command("purge_consent_records")
        record.refresh_from_db()
        after_second = (
            record.user_id,
            record.session_key,
            record.ip_address,
            record.user_agent,
            record.initiated_by_id,
        )

        assert after_first == after_second == (None, None, None, "", None)


class TestActorWindow:
    """The 12-month actor stage is separate from the 90-day fingerprint stage."""

    def test_expired_staff_actor_cleared_but_row_and_decisions_kept(
        self, user
    ) -> None:
        """An admin_staff row past the actor bound loses only its acting account."""
        staff = make_user(900000097, is_staff=True)
        withdraw_consent(
            user,
            action_source=ConsentActionSource.ADMIN_STAFF,
            initiated_by=staff,
        )
        row = ConsentRecord.objects.get(user=user)
        assert row.initiated_by_id == staff.pk
        ConsentRecord.objects.filter(pk=row.pk).update(
            consent_given_at=timezone.now() - timedelta(days=_ACTOR_DAYS + 1)
        )

        call_command("purge_consent_records")

        row.refresh_from_db()
        # The row, the mechanism and every decision field survive.
        assert ConsentRecord.objects.filter(pk=row.pk).exists()
        assert row.action_source == ConsentActionSource.ADMIN_STAFF.value
        assert row.choice == ConsentChoice.WITHDRAWN.value
        assert row.categories == {"analytics": False, "preferences": False}
        assert row.consent_version == ConsentVersion.V1_0.value
        assert row.consent_given_at is not None
        # The acting account expired; the fingerprint fields are also cleared.
        assert row.initiated_by_id is None
        assert row.user_id is None
        assert row.session_key is None
        assert row.ip_address is None
        assert row.user_agent == ""
        assert User.objects.filter(pk=staff.pk).exists()

    def test_staff_actor_inside_actor_window_stays_readable(self, user) -> None:
        """A staff row past the fingerprint bound but inside the actor bound keeps it."""
        staff = make_user(900000096, is_staff=True)
        withdraw_consent(
            user,
            action_source=ConsentActionSource.ADMIN_STAFF,
            initiated_by=staff,
        )
        row = ConsentRecord.objects.get(user=user)
        ConsentRecord.objects.filter(pk=row.pk).update(
            consent_given_at=timezone.now() - timedelta(days=_FINGERPRINT_DAYS + 1)
        )

        call_command("purge_consent_records")

        row.refresh_from_db()
        assert row.user_id is None
        assert row.session_key is None
        assert row.ip_address is None
        assert row.user_agent == ""
        # Inside the actor window: the acting account is still readable.
        assert row.initiated_by_id == staff.pk
        assert row.action_source == ConsentActionSource.ADMIN_STAFF.value
        assert User.objects.filter(pk=staff.pk).exists()

    def test_expired_actor_is_distinguishable_from_self_service_on_the_pair(
        self, user
    ) -> None:
        """An expired admin_staff row and an aged self_service row share a null
        actor, but the ``(action_source, initiated_by_id)`` PAIR separates them.

        Asserting either column alone would be wrong: ``initiated_by`` is null in
        both cases. ``action_source = admin_staff`` says a staff account acted and
        the attribution has expired; ``action_source = self_service`` says the
        subject acted, so there was never a distinct actor to record.
        """
        staff = make_user(900000095, is_staff=True)
        withdraw_consent(
            user,
            action_source=ConsentActionSource.ADMIN_STAFF,
            initiated_by=staff,
        )
        staff_row = ConsentRecord.objects.get(user=user)
        ConsentRecord.objects.filter(pk=staff_row.pk).update(
            consent_given_at=timezone.now() - timedelta(days=_ACTOR_DAYS + 1)
        )

        self_user = make_user(900000094)
        withdraw_consent(self_user)
        self_row = ConsentRecord.objects.get(user=self_user)
        ConsentRecord.objects.filter(pk=self_row.pk).update(
            consent_given_at=timezone.now() - timedelta(days=_ACTOR_DAYS + 1)
        )

        call_command("purge_consent_records")

        staff_row.refresh_from_db()
        self_row.refresh_from_db()
        assert staff_row.initiated_by_id is None
        assert self_row.initiated_by_id is None
        staff_pair = (staff_row.action_source, staff_row.initiated_by_id)
        self_pair = (self_row.action_source, self_row.initiated_by_id)
        assert staff_pair == (ConsentActionSource.ADMIN_STAFF.value, None)
        assert self_pair == (ConsentActionSource.SELF_SERVICE.value, None)
        assert staff_pair != self_pair


class TestLegalHold:
    """A hold exempts a row from the actor stage only — never from the others."""

    def test_held_row_past_actor_bound_is_not_anonymised_and_clear_releases(
        self, user
    ) -> None:
        """A held actor survives; clearing the hold lets the next run do it."""
        staff = make_user(900000093, is_staff=True)
        withdraw_consent(
            user,
            action_source=ConsentActionSource.ADMIN_STAFF,
            initiated_by=staff,
        )
        row = ConsentRecord.objects.get(user=user)
        ConsentRecord.objects.filter(pk=row.pk).update(
            consent_given_at=timezone.now() - timedelta(days=_ACTOR_DAYS + 1),
            legal_hold=True,
        )

        call_command("purge_consent_records")

        row.refresh_from_db()
        assert row.initiated_by_id == staff.pk

        ConsentRecord.objects.filter(pk=row.pk).update(legal_hold=False)
        call_command("purge_consent_records")

        row.refresh_from_db()
        assert row.initiated_by_id is None

    def test_hold_does_not_extend_decision_fields(self, user) -> None:
        """A held row past the DECISION bound still retains the decision fields."""
        staff = make_user(900000092, is_staff=True)
        withdraw_consent(
            user,
            action_source=ConsentActionSource.ADMIN_STAFF,
            initiated_by=staff,
        )
        row = ConsentRecord.objects.get(user=user)
        ConsentRecord.objects.filter(pk=row.pk).update(
            consent_given_at=timezone.now() - timedelta(days=_DECISION_DAYS + 1),
            legal_hold=True,
        )

        call_command("purge_consent_records")

        row.refresh_from_db()
        # The hold spares the actor; the decision fields are retained regardless.
        assert row.initiated_by_id == staff.pk
        assert row.choice == ConsentChoice.WITHDRAWN.value
        assert row.categories == {"analytics": False, "preferences": False}
        assert row.consent_version == ConsentVersion.V1_0.value
        assert row.consent_given_at is not None

    def test_non_held_row_past_decision_bound_retains_decision_fields(self, user) -> None:
        """Without a hold, a row past the decision bound keeps its decision fields."""
        row = _aged_record(
            user=user,
            age_days=_DECISION_DAYS + 1,
            choice=ConsentChoice.DECLINED.value,
            categories={"analytics": False},
        )

        call_command("purge_consent_records")

        row.refresh_from_db()
        assert row.choice == ConsentChoice.DECLINED.value
        assert row.categories == {"analytics": False}
        assert row.consent_version == ConsentVersion.V1_0.value
        assert row.consent_given_at is not None


class TestRetentionOrderingGuard:
    """The three-bound ordering guard fails loudly and mutates nothing."""

    def test_misordered_actor_below_fingerprint_raises(self, monkeypatch, user) -> None:
        from apps.core.management.commands import purge_consent_records as module

        monkeypatch.setattr(module, "_ACTOR_RETENTION_DAYS", 1)
        with pytest.raises(ValueError, match="mis-ordering"):
            call_command("purge_consent_records")

    def test_misordered_actor_above_decision_raises(self, monkeypatch, user) -> None:
        from apps.core.management.commands import purge_consent_records as module

        monkeypatch.setattr(module, "_ACTOR_RETENTION_DAYS", _DECISION_DAYS + 1)
        with pytest.raises(ValueError, match="mis-ordering"):
            call_command("purge_consent_records")

    def test_misordering_leaves_an_eligible_row_untouched(
        self, monkeypatch, user
    ) -> None:
        """The guard raises before ``transaction.atomic()`` — nothing mutates."""
        staff = make_user(900000091, is_staff=True)
        withdraw_consent(
            user,
            action_source=ConsentActionSource.ADMIN_STAFF,
            initiated_by=staff,
        )
        row = ConsentRecord.objects.get(user=user)
        ConsentRecord.objects.filter(pk=row.pk).update(
            consent_given_at=timezone.now() - timedelta(days=_FINGERPRINT_DAYS + 1)
        )

        from apps.core.management.commands import purge_consent_records as module

        monkeypatch.setattr(module, "_ACTOR_RETENTION_DAYS", 1)
        with pytest.raises(ValueError):
            call_command("purge_consent_records")

        row.refresh_from_db()
        assert row.user_id is not None
        assert row.initiated_by_id == staff.pk

    def test_dry_run_past_actor_bound_mutates_nothing(self, user, caplog) -> None:
        """--dry-run reports the actor-eligible count and changes no row."""
        staff = make_user(900000090, is_staff=True)
        withdraw_consent(
            user,
            action_source=ConsentActionSource.ADMIN_STAFF,
            initiated_by=staff,
        )
        row = ConsentRecord.objects.get(user=user)
        ConsentRecord.objects.filter(pk=row.pk).update(
            consent_given_at=timezone.now() - timedelta(days=_ACTOR_DAYS + 1)
        )

        with caplog.at_level("INFO"):
            call_command("purge_consent_records", "--dry-run")

        row.refresh_from_db()
        assert row.initiated_by_id == staff.pk
        assert row.user_id is not None
        assert "DRY RUN" in caplog.text
        # The actor-eligible count is reported.
        assert "1 acting accounts older than 365 days" in caplog.text


class TestNoInteractionWithTeardown:
    """The sweep does not damage neighbouring subscriber state."""

    def test_saved_search_survives_and_control_row_untouched(self, user) -> None:
        saved = SavedSearch.objects.create(user=user, query="велосипед")
        eligible = _aged_record(user=user, age_days=_FINGERPRINT_DAYS + 1)

        # A second user, entirely outside every window, is a control.
        control_user = make_user(900000099)
        control = _aged_record(user=control_user, age_days=1, session_key="k-control")

        call_command("purge_consent_records")

        saved.refresh_from_db()
        assert saved.is_active is True
        assert SavedSearch.objects.filter(pk=saved.pk).exists()

        control.refresh_from_db()
        assert control.session_key == "k-control"
        assert control.user_id == control_user.id

        eligible.refresh_from_db()
        assert eligible.session_key is None
