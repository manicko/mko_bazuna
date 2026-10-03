"""
Admin moderation actions service for Mko Bazuna.

Functions for individual ad actions: approve, reject, ban, soft delete.
Used by moderation review views and admin actions.

Ban target scope (plan 19 ``B-1``, ``18-Q7``)
---------------------------------------------
Both writers of ``User.is_banned`` in production code are in this module —
``ban_user_for_ad`` and ``bulk_ban_users`` — so the privilege rule has exactly
one home here: ``_resolve_ban_targets``. A non-superuser ``moderator_id`` may
not ban a target that is ``is_staff=True`` OR ``is_superuser=True``, and may
not ban its own row; a superuser is unrestricted. **Self-exclusion is
unconditional, including for a superuser** — there is no un-ban path and no
per-request web gate for this flag, so a self-ban is an operator lockout the UI
cannot repair. Skip categories are counted **self first, then privilege**, so a
row that is both the actor's own and privileged is counted once, as
``skipped_self``.

The rule is a **target scope** (which rows may be written), not an actor gate
(*who may run the action*). Actor scope stays in the permission layer
(``AdAdmin.has_view_permission`` / ``has_change_permission`` and
``moderation.views.decorators.staff_required``) and is deliberately not
re-implemented here; ``apps/users/services/deactivation.py`` documents the same
split for the ``is_active`` lever. ``moderator_id`` is an ``int`` pk, so the
superuser-unrestricted branch is reproduced by a lookup, and an unknown pk
fails **closed** (treated as a non-superuser).

Why no row lock on the bulk ban path
------------------------------------
``bulk_ban_users`` takes no ``select_for_update()``: a bare bulk ``UPDATE`` does
not read, and the privilege / self / already-banned exclusions are ``WHERE``
clauses evaluated by the database at write time, so a lock would buy nothing.
``ban_user_for_ad`` **does** hold ``select_for_update()``, because it reads a
row and writes fields from the read instance (a genuine read-then-write). **Do
not "fix" the bulk path by adding a lock.** This rationale lives here, not in
the function, because ``TestBulkLockingStructure::test_bulk_ban_users_not_locked``
asserts the absence of that token over the **whole function source** — a
docstring or comment inside ``bulk_ban_users`` that named it would fail the
test.
"""

import logging
from collections.abc import Iterable
from enum import StrEnum
from typing import NamedTuple

from django.db import OperationalError, transaction
from django.db.models import QuerySet

from apps.ads.models import Ad
from apps.core.enums import AdStatus, ApproveOutcome
from apps.core.utils.db_lock_timeout import is_lock_timeout
from apps.core.utils.sanitize import mask_telegram_id
from apps.moderation.services.auto_moderation import auto_moderate
from apps.moderation.services.exceptions import MaxAdsExceeded
from apps.moderation.services.moderation_log import (
    log_ban_account,
    log_soft_delete,
    set_rejected,
)
from apps.users.models import User

logger = logging.getLogger(__name__)


class BanRefusalReason(StrEnum):
    """Why a single-target ban was refused, as a stable moderator-facing value.

    The vocabulary is shared by the refusal ``logger.warning`` and the
    ``moderation:ban`` view's operator message, so it is a ``StrEnum`` (rule 10)
    rather than the free-form strings a log-only marker could tolerate. The
    members mirror the resolver's skip categories one-for-one:

    - ``SELF``: the target is the acting operator's own row.
    - ``PRIVILEGED``: the target is ``is_staff`` or ``is_superuser`` and the
      actor is not a superuser.
    - ``ALREADY_BANNED``: the target was permitted but already banned (a no-op).
    - ``NOT_IN_TARGET_SET``: the target is outside the candidate set. Unreachable
      for ``ban_user_for_ad``, which passes exactly ``[user.pk]``; retained as the
      total-return fallback for a future caller (see ``ban_refusal_reason``).
    """

    SELF = "self"
    PRIVILEGED = "privileged"
    ALREADY_BANNED = "already_banned"
    NOT_IN_TARGET_SET = "not_in_target_set"


class BanResult(NamedTuple):
    """Outcome of a ban by ``ban_user_for_ad`` / ``bulk_ban_users``.

    ``changed`` is the number of bans actually performed. It is *also* the
    number of rows the pre-filtered bulk ``UPDATE`` targeted, because the
    already-banned rows were removed first — **a bare ``UPDATE`` reports the
    matched-row count, not the changed-row count** (Postgres semantics), which
    is the whole reason the ``is_banned=False`` pre-filter exists. A future
    editor must not remove that filter on the assumption that the database
    reports changes.

    ``skipped_self`` and ``skipped_privileged`` are the counts refused before
    the write: the actor's own row, and rows a non-superuser actor is not
    permitted to touch. ``already_in_state`` is the count of selected rows the
    actor *was* permitted to touch but that were already banned (a no-op). All
    three are reported so a partial or fully-refused selection does not read as
    success; without ``already_in_state``, a selection of 10 rows of which 3
    are already banned would say "Banned 7 user(s)" with no hint that 3 were
    dropped.

    When a row is both the actor's own and privileged, it is counted as
    ``skipped_self`` only: self-exclusion is checked first, so the skip
    categories never double-count a row.

    This is a ``NamedTuple``, not persisted and not a ``StrEnum``: it satisfies
    the constants rule by its type and needs no migration.
    """

    changed: int
    skipped_self: int
    skipped_privileged: int
    already_in_state: int


def approve_ad(ad: Ad, moderator_id: int) -> ApproveOutcome:
    """
    Approve an ad for publication.

    Delegates to auto_moderate() which validates the ad against
    ModerationCriteria and transitions status to PUBLISHED on success,
    or ON_MODERATION_FAILED on failure.

    The approvable set is ``{ON_MODERATION, ON_MODERATION_FAILED}``: a failed
    ad is reachable for human review, but the state machine (unchanged) still
    refuses ``ON_MODERATION_FAILED -> PUBLISHED``. That refusal is reported as
    ``TRANSITION_REFUSED`` rather than escaping as an exception, so no caller
    surfaces a 500.

    Args:
        ad: Ad instance to approve
        moderator_id: Moderator user ID performing the action

    Returns:
        ``ApproveOutcome.PUBLISHED`` if auto-moderation passed and the ad was
        published, ``ApproveOutcome.CRITERIA_REJECTED`` if auto-moderation ran
        and the ad failed the criteria, ``ApproveOutcome.TRANSITION_REFUSED``
        if the ad was not approvable or the state machine refused the
        transition.
    """
    if ad.status not in (AdStatus.ON_MODERATION, AdStatus.ON_MODERATION_FAILED):
        return ApproveOutcome.TRANSITION_REFUSED

    try:
        result = auto_moderate(ad, moderator_id=moderator_id)
    except ValueError as exc:
        # The state machine refused the transition; auto_moderate's own failure
        # handler may raise a second ValueError from inside its except body, so
        # the message is derived from the outcome, never from the exception text.
        logger.warning(
            "Ad %s (status=%s) approval refused by state machine: %s",
            ad.id,
            ad.status,
            exc,
        )
        return ApproveOutcome.TRANSITION_REFUSED

    if result:
        logger.info("Ad %s approved by moderator %s", ad.id, moderator_id)
        return ApproveOutcome.PUBLISHED

    logger.warning(
        "Ad %s failed auto-moderation during approval by moderator %s",
        ad.id,
        moderator_id,
    )
    return ApproveOutcome.CRITERIA_REJECTED


def reject_ad(ad: Ad, moderator_id: int, reason: str) -> None:
    """
    Reject an ad with reason.

    Delegates to set_rejected() which routes through transition_to(REJECTED)
    and logs the action atomically. The transition matrix enforces valid
    source statuses: ON_MODERATION and ON_MODERATION_FAILED only.

    Args:
        ad: Ad instance to reject
        moderator_id: Moderator user ID performing the action
        reason: Rejection reason (INTERNAL ONLY - Layer-2 checklist + TEXT)
    """
    if ad.status == AdStatus.REJECTED:
        return

    set_rejected(ad, moderator_id=moderator_id, reason=reason)
    logger.info("Ad %s rejected by moderator %s", ad.id, moderator_id)


def _resolve_ban_targets(
    user_ids: Iterable[int], moderator_id: int
) -> tuple[QuerySet[User], BanResult, str]:
    """
    Apply the ban target scope; return the writable queryset, the counts, and the
    scope marker the actor's write actually ran under.

    The single home of the privilege rule for the ``is_banned`` lever, called by
    BOTH ``ban_user_for_ad`` and ``bulk_ban_users``. Order matters and is
    deliberate: **self first, then privilege**, so a row that is both is counted
    once, as ``skipped_self``. The skip counts are computed against the *original*
    candidate set so the operator is told how many selected rows were refused,
    then the exclusions produce the writable set.

    ``moderator_id`` is an ``int`` pk, so the actor is resolved by a lookup
    rather than read off a passed instance. The superuser-unrestricted branch is
    reproduced by asking whether that pk is a superuser; an unknown pk (or the
    ``None`` id a caller may pass) fails **closed** — the actor is treated as a
    non-superuser, so the selection is restricted. That is the safe default for
    an input no production or test producer creates.

    Candidates are built from the supplied ids, so ``None`` and dangling ids
    match no row and are neither banned nor counted, preserving the callers'
    tolerance of a null ``user_id`` without a per-item guard.

    A non-superuser actor is restricted to non-privileged targets
    (``exclude(is_staff=True).exclude(is_superuser=True)``); a superuser keeps
    the full set minus their own row. Rows already banned are **not** in the
    writable set — a bare ``UPDATE`` would otherwise report the matched-row count
    and mask the no-op — but they **are** counted in ``already_in_state`` so the
    operator sees they were dropped rather than silently omitted.

    Takes no row lock: a lock here would apply to both writers and would defeat
    the documented policy. The bulk update's exclusions are ``WHERE`` clauses
    evaluated at write time; the single-ad writer holds its own legitimate lock.

    Call this inside the caller's ``transaction.atomic()``: the counts and the
    write must observe one snapshot, or a concurrent flip between a count and the
    ``UPDATE`` can skew the *reported* count by one. The write scope itself is
    unaffected either way.

    The returned marker names the scope the actor's write ran under
    (``"unrestricted"`` or ``"non_privileged_only"``) and is derived from the
    same ``actor_is_superuser`` lookup that chose the branch, so a caller that
    logs it cannot report a scope different from the one that governed the write
    — and the actor is not queried a second time.
    """
    candidates = User.objects.filter(pk__in=set(user_ids))
    actor_is_superuser = User.objects.filter(
        pk=moderator_id, is_superuser=True
    ).exists()

    if actor_is_superuser:
        permitted = candidates
        skipped_privileged = 0
        target_scope = "unrestricted"
    else:
        permitted = candidates.exclude(is_staff=True).exclude(is_superuser=True)
        privileged = candidates.filter(is_staff=True) | candidates.filter(
            is_superuser=True
        )
        # Exclude the actor's own row so a self+privileged row counts once, as
        # skipped_self (self is checked first).
        skipped_privileged = privileged.exclude(pk=moderator_id).distinct().count()
        target_scope = "non_privileged_only"

    skipped_self = candidates.filter(pk=moderator_id).count()

    writable = permitted.exclude(pk=moderator_id).filter(is_banned=False)
    already_in_state = (
        permitted.exclude(pk=moderator_id).filter(is_banned=True).count()
    )
    result = BanResult(
        changed=0,
        skipped_self=skipped_self,
        skipped_privileged=skipped_privileged,
        already_in_state=already_in_state,
    )
    return writable, result, target_scope


def ban_user_for_ad(ad: Ad, moderator_id: int, reason: str) -> BanResult:
    """
    Ban the user who posted the ad, subject to the ban target scope.

    The target is read under ``select_for_update()`` (a genuine read-then-write
    on the instance), then ``_resolve_ban_targets`` gives the authoritative
    single-target decision. A refused target (self / privileged / already
    banned) writes nothing and reaches no audit row; ``log_ban_account`` is
    called ONLY when the resolver's writable set contains the target, so no
    ``BAN_ACCOUNT`` row exists for a ban that did not happen.

    Args:
        ad: Ad instance whose user will be banned
        moderator_id: Moderator user ID performing the action
        reason: Ban reason (INTERNAL ONLY)

    Returns:
        A ``BanResult``. ``changed`` is 1 on a performed ban and 0 on any
        refusal; the three skip counts report why rows were dropped.
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        try:
            user = User.objects.select_for_update().get(id=ad.user_id)
        except User.DoesNotExist:
            logger.info(
                "ban_user_for_ad: user %s for ad %s already deleted, skipping",
                ad.user_id,
                ad.id,
            )
            return BanResult(
                changed=0,
                skipped_self=0,
                skipped_privileged=0,
                already_in_state=0,
            )

        writable, result, target_scope = _resolve_ban_targets(
            [user.pk], moderator_id
        )

        if writable.filter(pk=user.pk).exists():
            user.is_banned = True
            user.save(update_fields=["is_banned"])
            log_ban_account(
                user_id=user.id,
                moderator_id=moderator_id,
                reason=reason,
            )
            result = result._replace(changed=1)
            logger.info(
                "User %s banned by moderator %s",
                mask_telegram_id(user.telegram_id),
                moderator_id,
            )
        else:
            reason_dropped = ban_refusal_reason(result)
            logger.warning(
                "ban_user_for_ad: ban of user %s (ad %s) refused by target scope (%s)",
                user.pk,
                ad.id,
                reason_dropped,
            )

    logger.info(
        "ban_user_for_ad by moderator %s: changed=%s skipped_self=%s "
        "skipped_privileged=%s already_in_state=%s (target_scope=%s)",
        moderator_id,
        result.changed,
        result.skipped_self,
        result.skipped_privileged,
        result.already_in_state,
        target_scope,
    )
    return result


def ban_refusal_reason(result: BanResult) -> BanRefusalReason:
    """Name why a single target was refused, derived from the resolver counts.

    Self is checked first, so a target that is both the actor's own and
    privileged is reported as ``SELF`` only, mirroring the count categories.

    The ``NOT_IN_TARGET_SET`` fallback keeps this helper's ``BanRefusalReason``
    return **total**. It is unreachable for today's only caller,
    ``ban_user_for_ad``, which passes exactly ``[user.pk]``: the candidate set is
    filtered from that id, so the tested row is always in ``candidates`` and one
    of the three counted categories always matches. The branch exists so the
    helper stays total for any future caller whose candidate set could exclude
    the tested row — dropping it would make a total-return function partial,
    which is worse than a documented fallback. Every refusal path maps onto a
    counted category.
    """
    if result.skipped_self:
        return BanRefusalReason.SELF
    if result.skipped_privileged:
        return BanRefusalReason.PRIVILEGED
    if result.already_in_state:
        return BanRefusalReason.ALREADY_BANNED
    return BanRefusalReason.NOT_IN_TARGET_SET


def soft_delete_ad(ad: Ad, moderator_id: int, reason: str) -> None:
    """
    Soft delete an ad.

    Routes through transition_to(DELETED) via the state machine driver.
    The any->DELETED transition is always valid per the transition matrix.

    Args:
        ad: Ad instance to delete
        moderator_id: Moderator user ID performing the action
        reason: Delete reason (INTERNAL ONLY)
    """
    if ad.status == AdStatus.DELETED:
        return

    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        ad.transition_to(AdStatus.DELETED)
        log_soft_delete(
            ad_id=ad.id,
            user_id=ad.user_id,
            moderator_id=moderator_id,
            reason=reason,
        )
    logger.info("Ad %s deleted by moderator %s", ad.id, moderator_id)


def bulk_approve(queryset, moderator_id: int) -> int:
    """
    Bulk approve ads for publication.

    Ads whose user has reached the ``max_ads_per_user`` cap are skipped
    (logged at WARN) rather than aborting the bulk operation.

    Args:
        queryset: Ad queryset to approve
        moderator_id: Moderator user ID performing the action

    Returns:
        Number of ads approved
    """
    count = 0
    try:
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped  lock Ad rows through every transition
            # Lock rows in PK order to match sweep lock ordering (no deadlock).
            # transition_to's refresh_from_db() raises Ad.DoesNotExist if a row was
            # hard-deleted mid-bulk (e.g. before the lock was acquired) — skip it
            # per-ad rather than aborting the whole bulk. MaxAdsExceeded
            # is already caught per-ad and preserved here.
            for ad in (
                queryset.filter(
                    status__in=[AdStatus.ON_MODERATION, AdStatus.ON_MODERATION_FAILED]
                )
                .order_by("pk")
                .select_for_update()
            ):
                try:
                    outcome = approve_ad(ad, moderator_id)
                    if outcome is not ApproveOutcome.PUBLISHED:
                        logger.warning(
                            "Skipping ad %s in bulk_approve: %s",
                            ad.id,
                            outcome,
                        )
                        continue
                except MaxAdsExceeded as exc:
                    logger.warning(
                        "Skipping ad %s in bulk_approve: user %s reached "
                        "max %s active ads (current_count=%s)",
                        ad.id,
                        exc.user_id,
                        exc.limit,
                        exc.current_count,
                    )
                    continue
                except Ad.DoesNotExist:
                    logger.warning(
                        "Skipping ad %s in bulk_approve: row hard-deleted mid-bulk",
                        ad.id,
                    )
                    continue
                count += 1
    except OperationalError as exc:
        if not is_lock_timeout(exc):
            raise
        # 03-DB-004: the locking SELECT ... FOR UPDATE precedes every row body, so a
        # lock timeout here fails the bulk with NOTHING committed. Fail loudly;
        # a silently partial bulk is strictly worse, and a per-row continue is
        # not available for the primary path (the lock statement is outside the
        # loop body).
        logger.error("bulk_approve aborted by lock timeout (SQLSTATE 55P03)")
        raise
    return count


def bulk_reject(queryset, moderator_id: int, reason: str) -> int:
    """
    Bulk reject ads with reason.

    Args:
        queryset: Ad queryset to reject
        moderator_id: Moderator user ID performing the action
        reason: Rejection reason (INTERNAL ONLY)

    Returns:
        Number of ads rejected
    """
    count = 0
    try:
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped  lock Ad rows through every transition
            # Lock rows in PK order. reject_ad()→set_rejected()→transition_to()
            # calls refresh_from_db(); a row hard-deleted mid-bulk raises
            # Ad.DoesNotExist — skip it per-ad rather than aborting the bulk.
            for ad in (
                queryset.filter(
                    status__in=[AdStatus.ON_MODERATION, AdStatus.ON_MODERATION_FAILED]
                )
                .order_by("pk")
                .select_for_update()
            ):
                if ad.status != AdStatus.REJECTED:
                    try:
                        reject_ad(ad, moderator_id, reason)
                    except Ad.DoesNotExist:
                        logger.warning(
                            "Skipping ad %s in bulk_reject: row hard-deleted mid-bulk",
                            ad.id,
                        )
                        continue
                    count += 1
    except OperationalError as exc:
        if not is_lock_timeout(exc):
            raise
        # 03-DB-004: fail the bulk with nothing committed rather than hanging.
        logger.error("bulk_reject aborted by lock timeout (SQLSTATE 55P03)")
        raise
    return count


def bulk_ban_users(queryset, moderator_id: int, reason: str) -> BanResult:
    """
    Bulk ban the users who posted the ads, subject to the ban target scope.

    The candidate ids come from the ad queryset, then ``_resolve_ban_targets``
    gives the authoritative decision: the privilege exclusions, the actor's
    self-exclusion, and the already-banned pre-filter. The audit loop runs over
    the writable targets only (ascending pk, so it is deterministic) and the
    single ``UPDATE`` carries the same exclusions and runs AFTER the loop — so a
    failed audit write rolls the whole block back, nothing is banned, and no
    ``BAN_ACCOUNT`` row is written for a target the scope refused or that was
    already banned.

    The bulk update performs no prior read and takes no row lock.

    Args:
        queryset: Ad queryset to identify users
        moderator_id: Moderator user ID performing the action
        reason: Ban reason (INTERNAL ONLY)

    Returns:
        A ``BanResult``. ``changed`` is the number of bans performed — not the
        number of user ids seen — with the three skip counts reporting refused
        and already-banned rows.
    """
    user_ids = set(queryset.values_list("user_id", flat=True))

    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        targets, result, target_scope = _resolve_ban_targets(
            user_ids, moderator_id
        )

        for banned_id in targets.order_by("pk").values_list("pk", flat=True):
            log_ban_account(
                user_id=banned_id,
                moderator_id=moderator_id,
                reason=reason,
            )

        result = result._replace(changed=targets.update(is_banned=True))

    logger.info(
        "bulk_ban_users by moderator %s: changed=%s skipped_self=%s "
        "skipped_privileged=%s already_in_state=%s (target_scope=%s)",
        moderator_id,
        result.changed,
        result.skipped_self,
        result.skipped_privileged,
        result.already_in_state,
        target_scope,
    )
    return result


def bulk_delete(queryset, moderator_id: int, reason: str) -> int:
    """
    Bulk soft delete ads.

    Args:
        queryset: Ad queryset to delete
        moderator_id: Moderator user ID performing the action
        reason: Delete reason (INTERNAL ONLY)

    Returns:
        Number of ads deleted
    """
    count = 0
    try:
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped  lock Ad rows through every transition
            # Lock rows in PK order. soft_delete_ad()→transition_to(DELETED) calls
            # refresh_from_db(); a row hard-deleted mid-bulk raises
            # Ad.DoesNotExist — skip it per-ad rather than aborting the bulk.
            for ad in (
                queryset.exclude(status=AdStatus.DELETED).order_by("pk").select_for_update()
            ):
                try:
                    soft_delete_ad(ad, moderator_id, reason)
                except Ad.DoesNotExist:
                    logger.warning(
                        "Skipping ad %s in bulk_delete: row hard-deleted mid-bulk",
                        ad.id,
                    )
                    continue
                count += 1
    except OperationalError as exc:
        if not is_lock_timeout(exc):
            raise
        # 03-DB-004: fail the bulk with nothing committed rather than hanging.
        logger.error("bulk_delete aborted by lock timeout (SQLSTATE 55P03)")
        raise
    return count
