"""
Ad lifecycle state mechanics — archive / reactivate / delete.

This module carries **state mechanics only** — the status precondition,
``Ad.transition_to`` and (for reactivation) the ``auto_moderate`` decision —
applied to a row the caller fetched, locked and authorized.

The lifecycle convention (R04):

- **The caller owns the transaction, the row lock and the authorization.**
  The HTML action views open ``transaction.atomic()``, fetch the ad with
  ``get_object_or_404(Ad.objects.select_for_update(), ...)`` (a missing ad is
  a 404 from the fetch), refuse a non-owner with the boundary's own 403, and
  only then hand the locked instance to one of the functions below.
- **This module never re-fetches and never re-checks ownership.** It acts on
  the instance it is handed, so a request path checks ownership exactly once.
- **Consent / audience gates stay caller-side.** ``can_create_ad`` is asserted
  by the HTML views behind the archive/reactivate paths, never by this module.
  The delete flow is gate-free by design.
- **Messages and logging stay caller-side.** Reactivation's dashboard feedback
  depends on the outcome; the HTML view emits it.

Results are returned as named tuples so the caller decides its response from
the outcome without re-reading the row. Every function keeps its own
``transaction.atomic()``: nested inside the caller's block it is a savepoint
(what makes the reactivation rollback real), standalone it is the whole
transaction.

Honesty clause (R04): a single ad-row transaction does not by itself solve
concurrent account-consent changes — the consent gate is consulted at the
boundary, before the action, and a consent withdrawal racing the action is not
serialized by the row lock.

Every function issues exactly the persisted state change its HTML predecessor
issued:

- :func:`archive_ad` — ``PUBLISHED -> ARCHIVED`` only; any other status is a
  silent no-op (the row is not written at all).
- :func:`reactivate_ad` — ``ARCHIVED -> ON_MODERATION -> (PUBLISHED |
  ON_MODERATION_FAILED)``; any other status is a silent no-op. The transition
  and the content check run inside one atomic block, so a failure of the check
  itself rolls the transition back (the ad stays ARCHIVED).
- :func:`delete_ad` — ``any -> DELETED``; an already-DELETED ad is a no-op.
"""

from __future__ import annotations

import logging
from typing import NamedTuple

from django.db import transaction

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


def archive_ad(ad: Ad) -> ArchiveResult:
    """Archive a row the caller fetched, locked and authorized.

    ``PUBLISHED -> ARCHIVED`` only; manual seller archive, no moderation.
    Non-PUBLISHED rows are untouched.

    Args:
        ad: The caller's locked ad instance (ownership already verified by
            the caller).

    Returns:
        :class:`ArchiveResult` describing whether the transition ran.

    Raises:
        ValueError: Propagated from ``Ad.transition_to`` if the matrix rejects
            the target (unreachable for the PUBLISHED precondition).
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]  # django-stubs not installed; Atomic lacks CM stubs
        if ad.status == AdStatus.PUBLISHED:
            ad.transition_to(AdStatus.ARCHIVED)
            logger.info("Ad %s archived by user %s", ad.id, ad.user_id)
            return ArchiveResult(archived=True)

    return ArchiveResult(archived=False)


def reactivate_ad(ad: Ad) -> ReactivateResult:
    """Reactivate a row the caller fetched, locked and authorized.

    ``ARCHIVED -> ON_MODERATION`` then ``auto_moderate``: a pass publishes the
    ad, a fail commits it as ``ON_MODERATION_FAILED``. The transition clears
    ``archived_at`` and the moderation outcome writes the timestamps +
    analytics event.

    A non-ARCHIVED ad is a silent no-op (nothing is written, the check is not
    run).

    Database errors (including a lock timeout) propagate untouched so the
    caller keeps the 03-DB-004 boundary; any other exception raised by the
    content check rolls the transition back and propagates as well — the
    caller decides how to report it.

    Args:
        ad: The caller's locked ad instance (ownership already verified by
            the caller).

    Returns:
        :class:`ReactivateResult` with the moderation verdict.

    Raises:
        Exception: Anything ``auto_moderate`` raises (after rollback).
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]  # django-stubs not installed; Atomic lacks CM stubs
        if ad.status != AdStatus.ARCHIVED:
            return ReactivateResult(attempted=False, passed=None)

        ad.transition_to(AdStatus.ON_MODERATION)
        # The check completes before the atomic block commits: a raising check
        # rolls the ARCHIVED -> ON_MODERATION transition back (the ad stays
        # ARCHIVED, the safe state).
        passed = auto_moderation.auto_moderate(ad)

    return ReactivateResult(attempted=True, passed=passed)


def delete_ad(ad: Ad) -> DeleteResult:
    """Soft-delete a row the caller fetched, locked and authorized.

    The ad is hidden from public listings immediately; physical cleanup stays
    with the later sweeps. An already-DELETED ad is a no-op. Gate-free by
    design: no consent check applies to delete.

    Args:
        ad: The caller's locked ad instance (ownership already verified by
            the caller).

    Returns:
        :class:`DeleteResult` describing whether the transition ran.
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]  # django-stubs not installed; Atomic lacks CM stubs
        if ad.status == AdStatus.DELETED:
            return DeleteResult(deleted=False)

        # transition_to sets deleted_at and refreshes updated_at.
        ad.transition_to(AdStatus.DELETED)
        logger.info("Ad %s deleted by user %s", ad.id, ad.user_id)
        return DeleteResult(deleted=True)
