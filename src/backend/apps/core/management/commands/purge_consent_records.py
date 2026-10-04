"""
Management command to anonymise aged ``ConsentRecord`` rows on a ratified schedule.

The consent ledger is Art. 7(1) accountability evidence, so this sweep
**anonymises, never deletes**. Three windows apply, all owner-ratified and all
hardcoded (``_FINGERPRINT_RETENTION_DAYS`` / ``_ACTOR_RETENTION_DAYS`` /
``_DECISION_RETENTION_DAYS``):

* At the **fingerprint** window the HTTP-layer identity is removed: ``user`` and
  ``session_key`` are cleared in the **same** ``UPDATE`` (an anonymous record is
  identified by ``session_key``, so clearing one without the other would leave a
  live re-identification path through ``django_session``), ``ip_address`` is set
  ``NULL`` and ``user_agent`` is cleared to ``""`` (the column is ``blank=True``
  and **not** nullable, so the action is ``CLEAR``, not ``NULL``).
* At the **actor** window the acting account (``initiated_by``) is irreversibly
  anonymised 12 months after the action, unless the row is under a documented
  ``legal_hold``. This is the only second mutation stage: the fingerprint and
  decision windows are not symmetric — the decision window is count-only.
* The **decision** fields (``choice``, ``categories``, ``consent_version``,
  ``consent_given_at``) are retained at every age; the row itself is never
  deleted, which is what lets the controller demonstrate that consent was given
  and survives the re-prompt boundary.

The command asserts
``0 < _FINGERPRINT_RETENTION_DAYS <= _ACTOR_RETENTION_DAYS <= _DECISION_RETENTION_DAYS``
itself so a mis-ordering fails loudly, **before** ``transaction.atomic()`` is
entered, instead of making a stage a silent no-op; the fingerprint window is
additionally floored at the declared Django session lifetime
(``SESSION_COOKIE_AGE``) so a still-live session's support evidence is not
destroyed. That floor applies to the fingerprint bound only: the actor is an
account FK, not live-session evidence.

Uses advisory lock 14 for idempotent, safe concurrent execution. Batching is
deliberately off: ``ConsentRecord`` grows by consent *actions*, not by requests,
and the workload is far below the ``~10**5`` eligible rows that would justify
``archive_sweep``'s keyset-batched shape.

Changelist residual (06-PII-116, recorded not closed): the admin changelist no
longer lists ``session_key``, but ``ConsentRecordAdmin.search_fields`` still
contains it, so a staff user with changelist permission can probe a session key
they already hold and learn whether a row exists. Closing that needs a decision
about whether any staff probe is acceptable at all, which is outside this
block's surface.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.core.enums import AdvisoryLockId
from apps.core.utils.advisory_lock import advisory_lock
from apps.users.models import ConsentRecord

logger = logging.getLogger(__name__)

#: Ratified R2: how long the fingerprint fields (session_key, user_agent,
#: ip_address, plus the user link) are retained after the consent action.
_FINGERPRINT_RETENTION_DAYS = 90

#: Ratified R1 (BLOCK 19, 06-NEW-02): how long the acting account
#: (``initiated_by``) is retained before it is irreversibly anonymised. Twelve
#: months is a **chosen minimisation period justified by purpose — one full
#: operational/audit cycle — and explicitly NOT a statutory term**. It is
#: deliberately shorter than the decision bound below, which governs the decision
#: fields only. A documented ``legal_hold`` exempts a row from this stage alone.
_ACTOR_RETENTION_DAYS = 365

#: Ratified R1: how long the decision fields are retained. The rows themselves
#: are anonymised, never deleted, so this is not a deletion boundary.
_DECISION_RETENTION_DAYS = 365 * 5


class Command(BaseCommand):
    """Anonymise aged ConsentRecord rows without ever deleting them."""

    help = (
        "Anonymise ConsentRecord fingerprint fields older than 90 days, the "
        "acting account older than 12 months (unless held), and retain the "
        "decision fields for 5 years (never deletes rows)"
    )

    def add_arguments(self, parser) -> None:
        """Add dry-run argument to the command."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            default=False,
            help="Report the counts that would be anonymised without mutating",
        )

    def handle(self, *args, **options) -> None:
        """Execute the consent-record retention sweep with advisory lock."""
        dry_run: bool = options["dry_run"]

        self._assert_retention_ordering()

        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
            with advisory_lock(AdvisoryLockId.CONSENT_RECORD_SWEEP):
                now = timezone.now()
                fingerprint_cutoff = now - timedelta(
                    days=_FINGERPRINT_RETENTION_DAYS
                )
                actor_cutoff = now - timedelta(days=_ACTOR_RETENTION_DAYS)
                decision_cutoff = now - timedelta(days=_DECISION_RETENTION_DAYS)

                # A row is fingerprint-eligible when it is older than the
                # fingerprint window and still carries identity material.
                # `consent_given_at` is the leading column of the
                # IX_consent_records_sweep index, so this is an Index Cond.
                fingerprint_qs = ConsentRecord.objects.filter(
                    consent_given_at__lt=fingerprint_cutoff,
                ).exclude(
                    user__isnull=True,
                    session_key__isnull=True,
                    ip_address__isnull=True,
                    user_agent="",
                )

                # A row is decision-eligible when it is older than the decision
                # window; the row is retained, only its fingerprint fields are
                # (already) cleared. Counted separately so the log distinguishes
                # "fingerprint cleared now" from "old decision rows retained".
                decision_eligible = ConsentRecord.objects.filter(
                    consent_given_at__lt=decision_cutoff,
                ).count()

                # A row is actor-eligible when it is older than the actor window,
                # still names an acting account, and is not under a documented
                # legal hold. The hold is an exemption from ACTOR erasure only —
                # never from the 90-day fingerprint window, never from the
                # decision fields. Excluding a null actor keeps the stage
                # idempotent: an already-anonymised row is not re-counted.
                actor_qs = (
                    ConsentRecord.objects.filter(
                        consent_given_at__lt=actor_cutoff,
                        legal_hold=False,
                    )
                    .exclude(initiated_by__isnull=True)
                )

                if dry_run:
                    logger.info(
                        "DRY RUN: Would anonymise %d consent records older than "
                        "%d days and %d acting accounts older than %d days "
                        "(%d rows past the %d-day decision window are retained, "
                        "never deleted)",
                        fingerprint_qs.count(),
                        _FINGERPRINT_RETENTION_DAYS,
                        actor_qs.count(),
                        _ACTOR_RETENTION_DAYS,
                        decision_eligible,
                        _DECISION_RETENTION_DAYS,
                    )
                    return

                # One statement: user and session_key must never be half-cleared.
                # Nulling user while keeping session_key would leave the
                # anonymous record re-identifiable through django_session.
                anonymised_count = fingerprint_qs.update(
                    user=None,
                    session_key=None,
                    ip_address=None,
                    user_agent="",
                )

                # Second, independent mutation stage. Not folded into the
                # fingerprint UPDATE: that queryset excludes already-cleared
                # rows and the actor rule is independent of it. A failure here
                # rolls the fingerprint clear back with it (same atomic block).
                actor_anonymised_count = actor_qs.update(initiated_by=None)

        logger.info(
            "Anonymised %d consent records older than %d days and %d acting "
            "accounts older than %d days; %d records past the %d-day decision "
            "window retained (never deleted).",
            anonymised_count,
            _FINGERPRINT_RETENTION_DAYS,
            actor_anonymised_count,
            _ACTOR_RETENTION_DAYS,
            decision_eligible,
            _DECISION_RETENTION_DAYS,
        )

    @staticmethod
    def _assert_retention_ordering() -> None:
        """Fail loudly if the three windows are mis-ordered.

        ``0 < fingerprint TTL <= actor TTL <= decision TTL`` makes a stage a
        silent no-op otherwise. The fingerprint TTL is additionally floored at
        the declared Django session lifetime so a still-live session's evidence
        is not destroyed on a run that lands between the two; the actor bound is
        an account FK, not live-session evidence, so this floor does not apply to
        it.
        """
        session_cookie_age_days = settings.SESSION_COOKIE_AGE / 86400
        if not (
            0
            < _FINGERPRINT_RETENTION_DAYS
            <= _ACTOR_RETENTION_DAYS
            <= _DECISION_RETENTION_DAYS
        ):
            raise ValueError(
                "Retention mis-ordering: expected "
                "0 < _FINGERPRINT_RETENTION_DAYS <= _ACTOR_RETENTION_DAYS "
                "<= _DECISION_RETENTION_DAYS, "
                f"got {_FINGERPRINT_RETENTION_DAYS} / "
                f"{_ACTOR_RETENTION_DAYS} / "
                f"{_DECISION_RETENTION_DAYS}"
            )
        if _FINGERPRINT_RETENTION_DAYS < session_cookie_age_days:
            raise ValueError(
                "Fingerprint TTL is below the declared Django session lifetime "
                f"({_FINGERPRINT_RETENTION_DAYS} days < "
                f"{session_cookie_age_days} days); this would destroy evidence "
                "for a session that is still live."
            )
