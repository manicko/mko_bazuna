"""
Ad lifecycle state mechanics — archive / reactivate / delete (S4.1).

Extracted verbatim from the seller HTML action views so that the HTML
surfaces and the future ``/api/v1/ads/{id}/{archive,reactivate,delete}/``
endpoints share **one** transition stack instead of two hand-written copies.

Scope split (plan S4.1):

- **This module carries state mechanics only** — ownership, ``select_for_update``
  locking, the status precondition, ``Ad.transition_to`` and (for reactivation)
  the ``auto_moderate`` decision.
- **Consent / audience gates stay caller-side.** ``can_create_ad`` is asserted
  by each boundary (the HTML views behind the archived reactivation path and
  the API views), never by this module. The delete flow is gate-free by design.
- **Messages and logging stay caller-side.** Reactivation's dashboard feedback
  depends on the outcome; the HTML view emits it, the API will map outcomes to
  its own shapes.

Contract: request-free — an ``Ad`` (already fetched by the caller) plus the
acting ``user_id``; results are returned as named tuples so no caller has to
re-read the row to decide its response, and no caller needs a second
``transition_to`` attempt against a now-stale local copy.

Every function issues exactly the persisted state change its HTML predecessor
issued:

- :func:`archive_ad` — ``PUBLISHED -> ARCHIVED`` only; any other status is a
  silent no-op (the row is not written at all).
- :func:`reactivate_ad` — ``ARCHIVED -> ON_MODERATION -> (PUBLISHED |
  ON_MODERATION_FAILED)``; any other status is a silent no-op. The transition
  and the content check run inside one atomic block, so a failure of the check
  itself rolls the transition back (the ad stays ARCHIVED).
- :func:`delete_ad` — ``any -> DELETED``; an already-DELETED ad is a no-op.

Refusals use the exceptions the project already speaks: :class:`Http404` for a
missing ad (what ``get_object_or_404`` produced at every call site),
:class:`~django.core.exceptions.PermissionDenied` for a non-owner, and
``Ad.DoesNotExist`` when the row disappears between fetch and transition.
"""

from __future__ import annotations

import logging
from typing import NamedTuple

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404

from apps.ads.models import Ad
from apps.core.enums import AdStatus
from apps.moderation.services import auto_moderation

logger = logging.getLogger(__name__)


class ArchiveResult(NamedTuple):
    """Outcome of :func:`archive_ad`.

    ``archived`` is ``True`` only when this call performed the
    ``PUBLISHED -> ARCHIVED`` transition; a non-PUBLISHED ad leaves it
    ``False`` and is a silent no-op (the HTML flow redirects either way).
    """

    archived: bool


class ReactivateResult(NamedTuple):
    """Outcome of :func:`reactivate_ad`.

    ``attempted`` is ``False`` when the ad was not ARCHIVED, so no transition
    and no moderation check ran (silent no-op).

    ``passed`` mirrors ``auto_moderate`` exactly: ``True`` = PUBLISHED,
    ``False`` = committed as ON_MODERATION_FAILED (hidden pending human
    review), ``None`` = not attempted.
    """

    attempted: bool
    passed: bool | None


class DeleteResult(NamedTuple):
    """Outcome of :func:`delete_ad`.

    ``deleted`` is ``False`` for an already-DELETED ad (no write, no
    transition); every other status is moved to DELETED with ``deleted_at``
    set by ``Ad.transition_to``.
    """

    deleted: bool


def _fetch_owned_ad(ad_id: int, user_id: int) -> Ad:
    """Lock and return the ad, refusing a missing row or a non-owner.

    The row lock must run inside *some* transaction. When a caller opens a
    lifecycle function, that function's own ``transaction.atomic()`` acquires
    the lock and holds it to its commit, so the lock and the write share one
    unit of work. When a boundary calls a lifecycle function **inside its own
    open atomic block** (the HTML ``ad_archive`` / ``ad_reactivate`` views and
    the edit view's nested ``submit_ad`` precedent), the service's ``atomic()``
    is a PostgreSQL SAVEPOINT inside the caller's transaction: the
    ``select_for_update()`` re-acquisition is a same-transaction self-reacquire
    (a no-op that cannot block), and the lock and the write share the caller's
    **one** unit of work and **one** commit.

    Consequences of the savepoint nesting: ``on_commit`` callbacks fire at the
    **outermost** commit, and a rollback to a savepoint releases only that
    savepoint's work — **not** the row lock, which lives until the caller's
    transaction ends.

    Raises:
        Http404: No ad with ``ad_id`` exists.
        PermissionDenied: ``user_id`` does not own the ad.
    """
    try:
        ad = Ad.objects.select_for_update().get(id=ad_id)
    except Ad.DoesNotExist:
        raise Http404(f"No Ad matches the given query: id={ad_id}") from None

    if ad.user_id != user_id:
        logger.warning(
            "User %s attempted a lifecycle action on ad %s owned by %s",
            user_id,
            ad_id,
            ad.user_id,
        )
        raise PermissionDenied("You do not own this ad.")

    return ad


def assert_lifecycle_owner(ad_id: int, user_id: int) -> None:
    """Assert that *user_id* owns *ad_id*, opening the caller's transaction.

    Used by boundaries that must refuse a non-owner **before** any write and
    before their own gates (consent), reproducing the HTML action views'
    check order: ownership first, then consent, then the transition.

    Returns ``None``; it does **not** own a long-lived lock. The
    ``select_for_update()`` runs inside the caller's block; because this
    function opens only a nesting ``atomic()``, the lock lives until the
    **caller's** transaction exits, not until this function returns. The
    caller must keep its own ``atomic()`` block open across the follow-up
    :func:`archive_ad` / :func:`reactivate_ad` call — that is what makes the
    check and the action one unit of work and what keeps the refusals ordered
    ownership -> consent -> action. A caller that exits its block first releases
    the lock and reintroduces the gap between the check and the write.

    Raises:
        Http404: No ad with ``ad_id`` exists.
        PermissionDenied: ``user_id`` does not own the ad.
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]  # django-stubs not installed; Atomic lacks CM stubs
        _fetch_owned_ad(ad_id, user_id)


def archive_ad(ad_id: int, user_id: int) -> ArchiveResult:
    """Archive the caller's own ad (``PUBLISHED -> ARCHIVED``).

    Manual seller archive; no moderation. Non-PUBLISHED rows are untouched.

    Args:
        ad_id: The ad to archive.
        user_id: The acting seller's user ID (ownership predicate).

    Returns:
        :class:`ArchiveResult` describing whether the transition ran.

    Raises:
        Http404: The ad does not exist.
        PermissionDenied: The ad is owned by another user.
        ValueError: Propagated from ``Ad.transition_to`` if the matrix rejects
            the target (unreachable for the PUBLISHED precondition).
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]  # django-stubs not installed; Atomic lacks CM stubs
        ad = _fetch_owned_ad(ad_id, user_id)

        if ad.status == AdStatus.PUBLISHED:
            ad.transition_to(AdStatus.ARCHIVED)
            logger.info("Ad %s archived by user %s", ad_id, user_id)
            return ArchiveResult(archived=True)

    return ArchiveResult(archived=False)


def reactivate_ad(ad_id: int, user_id: int) -> ReactivateResult:
    """Reactivate the caller's own archived ad (``ARCHIVED -> ...``).

    ``ARCHIVED -> ON_MODERATION`` then ``auto_moderate``, exactly the decision
    the HTML view made: a pass publishes the ad, a fail commits it as
    ``ON_MODERATION_FAILED``. The transition clears ``archived_at`` and the
    moderation outcome writes the timestamps + analytics event.

    A non-ARCHIVED ad is a silent no-op (nothing is written, the check is not
    run).

    Database errors (including a lock timeout) propagate untouched so the
    caller keeps the 03-DB-004 boundary; any other exception raised by the
    content check rolls the transition back and propagates as well — the
    caller decides how to report it.

    Args:
        ad_id: The ad to reactivate.
        user_id: The acting seller's user ID (ownership predicate).

    Returns:
        :class:`ReactivateResult` with the moderation verdict.

    Raises:
        Http404: The ad does not exist.
        PermissionDenied: The ad is owned by another user.
        Exception: Anything ``auto_moderate`` raises (after rollback).
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]  # django-stubs not installed; Atomic lacks CM stubs
        ad = _fetch_owned_ad(ad_id, user_id)

        if ad.status != AdStatus.ARCHIVED:
            return ReactivateResult(attempted=False, passed=None)

        ad.transition_to(AdStatus.ON_MODERATION)
        # The check completes before the atomic block commits: a raising check
        # rolls the ARCHIVED -> ON_MODERATION transition back (the ad stays
        # ARCHIVED, the safe state).
        passed = auto_moderation.auto_moderate(ad)

    return ReactivateResult(attempted=True, passed=passed)


def delete_ad(ad_id: int, user_id: int) -> DeleteResult:
    """Soft-delete the caller's own ad (``any -> DELETED``).

    The ad is hidden from public listings immediately; physical cleanup stays
    with the later sweeps. An already-DELETED ad is a no-op.

    Args:
        ad_id: The ad to delete.
        user_id: The acting seller's user ID (ownership predicate).

    Returns:
        :class:`DeleteResult` describing whether the transition ran.

    Raises:
        Http404: The ad does not exist.
        PermissionDenied: The ad is owned by another user.
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]  # django-stubs not installed; Atomic lacks CM stubs
        ad = _fetch_owned_ad(ad_id, user_id)

        if ad.status == AdStatus.DELETED:
            return DeleteResult(deleted=False)

        # transition_to sets deleted_at and refreshes updated_at.
        ad.transition_to(AdStatus.DELETED)
        logger.info("Ad %s deleted by user %s", ad_id, user_id)
        return DeleteResult(deleted=True)
