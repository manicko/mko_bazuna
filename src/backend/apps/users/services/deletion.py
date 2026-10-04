"""

Consent revocation + soft delete service for Mko Bazuna.



Implements zone R3 two consent states (decision F/K):

- DECLINE (browse-only): blocks only seller actions; no consent_revoked_at, no deletion

- WITHDRAW/DELETE: sets consent_revoked_at + is_deleted, nulls PII, soft-deletes ads



Hard-delete sweep (30 days) is Phase 4 per zone R1.

"""

import logging

from django.db import transaction
from django.utils import timezone

from apps.ads.models import Ad, AdImage
from apps.core.enums import AdStatus, ConsentActionSource, ConsentChoice
from apps.core.models import SupportTicket
from apps.search.models import SavedSearch, SearchHistory
from apps.search.services.cache import bump_search_cache_version
from apps.users.models import LoginToken, User
from apps.users.services.consent_record import (
    WITHDRAWN_CATEGORIES,
    record_consent_action_with_context,
)

logger = logging.getLogger(__name__)


def decline_consent(user: User) -> None:
    """

    Decline consent (browse-only, decision K).

    This blocks only seller actions (no deletion occurs) and sets
    ``is_declined=True`` with ``ads_auto_publish=False`` to block new ads and
    login, while preserving existing ads and PII. It does NOT set
    ``consent_revoked_at`` or ``is_deleted``, and triggers no erasure —
    DECLINE is distinct from WITHDRAW. Because PUBLISHED ads of a
    consent-declined user are hidden from listings and search by the live
    ``user__is_declined=False`` filter (SRH-001), the search cache version is
    bumped (via ``transaction.on_commit``) once this transaction commits so
    cached result sets are invalidated and the ads disappear immediately.

    Args:
        user: The user declining consent.

    """

    user.ads_auto_publish = False

    user.is_declined = True

    user.consent_given_at = None

    # Clear the persisted behavioural preference. The cookie is expired on the
    # decline response and the reconcile/header writes are gated on
    # ``is_declined``, so the NULL is durable until a NEW consent (give_consent)
    # clears the decline state (06-PII-110).
    user.preferred_city = None

    user.save(
        update_fields=[
            "ads_auto_publish",
            "is_declined",
            "consent_given_at",
            "preferred_city",
        ]
    )

    # No Ad.save() fires here (ads are not mutated), so the post_save signal
    # would not bump the search cache. Invalidate explicitly, after the decline
    # is committed, so cached search/listings results drop the hidden ads.
    transaction.on_commit(bump_search_cache_version)

    logger.info(
        "User %s declined consent - browse-only mode: "
        "ads_auto_publish=False, is_declined=True",
        user.id,
    )


def withdraw_consent(
    user: User,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
    session_key: str | None = None,
    action_source: ConsentActionSource = ConsentActionSource.SELF_SERVICE,
    initiated_by: User | None = None,
) -> list[str]:
    """
    Withdraw consent and trigger immediate soft-delete (decision F).

    Flow (zone R3):

    - Sets consent_revoked_at = now()

    - Sets is_deleted = True, deleted_at = now()

    - NULLs telegram_id, username immediately (breaks chat linkage)
    - Empties first_name, last_name, email (NOT NULL fields — use "" not None)

    - Invalidates/deletes all active LoginTokens (prevents re-linking after withdrawal)

    - Deactivates the user's SavedSearch rows and deletes their SearchHistory rows

    - Clears User.preferred_city

    - Deletes the user's SupportTicket rows (06-PII-101)

    - Soft-deletes all user ads (status=DELETED, hidden immediately)

    - Writes the ConsentRecord audit row (choice=WITHDRAWN) inside this transaction

    - DRAFT ads' media files are physically removed from disk

    All DB mutations — including the audit row — run inside
    ``transaction.atomic()`` so that a failure in any step rolls back
    LoginToken deletion, PII nulling, ticket deletion, ad soft-delete and the
    audit write together. The row is written here, not by the view, so the
    Art. 7(1) evidence commits atomically with the erasure it documents rather
    than after it (a crash between the service commit and a view-side insert
    would leave a ``consent_revoked_at`` with no WITHDRAWN row). Physical media
    files are deleted after the transaction commits via the AdImage pre_delete
    signal's ``on_commit`` callback, following the TX-then-FS pattern. A
    rollback must never remove files for rows that remain in the DB.

    Limitation (``06-NEW-02``): ``ConsentRecord`` now records the actor and the
    mechanism. A bare ``withdraw_consent(user)`` call means **"the subject
    withdrew"** (``action_source`` defaults to ``SELF_SERVICE``); **any
    third-party initiator MUST pass ``ADMIN_STAFF`` and ``initiated_by``** — the
    admin action does exactly that. The admin-initiated row still carries no IP
    and no user agent (recorded residual, BLOCK 10's shipped behaviour).

    Idempotency: if the user is already soft-deleted (``is_deleted=True``),
    the call is a no-op returning ``[]`` and writes no audit row.

    Phase 4 will hard-delete (remove rows) 30 days after consent_revoked_at.

    Args:

        user: The user withdrawing consent.
        ip_address: Resolved client IP from the caller, or ``None``. Sanitized
            inside ``record_consent_action_with_context`` before storage.
        user_agent: Raw User-Agent header from the caller, or ``None``.
        session_key: Session key that authenticated the action, or ``None``.
            The view supplies it so the row commits before ``logout()`` flushes
            the session, identifying the session that actually acted.
        action_source: Mechanism that initiated the withdrawal. Defaults to
            ``SELF_SERVICE``; a staff/admin initiator MUST pass ``ADMIN_STAFF``.
        initiated_by: The acting account, or ``None``. Recorded only when it is
            not the subject (normalised in the recording service).

    Returns:

        Storage keys of DRAFT-ad media files deleted from disk (``[]`` when
        the user was already deleted or had no DRAFT ads with images).

    """

    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        if user.is_deleted:
            logger.info("User %s already soft-deleted — skipping withdrawal", user.id)
            return []

        now = timezone.now()

        user_telegram_id = user.telegram_id

        # Invalidate active login tokens BEFORE nulling telegram_id
        # This prevents re-linking via a still-valid token after withdrawal
        LoginToken.objects.filter(telegram_id=user_telegram_id).delete()

        # Tear down subscriber state inside the same transaction so revocation
        # actively terminates alerts/history rather than relying on a future
        # filter. SavedSearch.updated_at is auto_now, so this bulk .update()
        # does NOT refresh it — accepted, because the daily alert cap reads
        # last_notified_at (06-PII-110).
        SavedSearch.objects.filter(user=user).update(is_active=False)
        SearchHistory.objects.filter(user=user).delete()

        # Set consent revocation timestamp and soft-delete flags
        user.consent_revoked_at = now
        user.is_deleted = True
        user.deleted_at = now

        # NULL PII immediately (breaks chat linkage)
        user.telegram_id = None  # type: ignore[assignment]
        user.username = None
        user.first_name = ""
        user.last_name = ""
        user.email = ""
        user.consent_given_at = None
        user.preferred_city = None

        user.save(
            update_fields=[
                "consent_revoked_at",
                "is_deleted",
                "deleted_at",
                "consent_given_at",
                "telegram_id",
                "username",
                "first_name",
                "last_name",
                "email",
                "preferred_city",
            ]
        )

        # Delete the user's support tickets (06-PII-101). This is load-bearing:
        # withdraw_consent is a SOFT delete, so the user row survives and the
        # FK's CASCADE can never fire here. Placed BEFORE
        # soft_delete_user_ads(user) so a failure there rolls the deletion back
        # (test_withdraw_is_atomic_rollback).
        SupportTicket.objects.filter(user=user).delete()

        # Soft-delete all user ads (DB-only: returns storage keys for FS cleanup)
        storage_keys = soft_delete_user_ads(user)

        # Write the Art. 7(1) audit row INSIDE this transaction, and LAST in the
        # block so that a raise from soft_delete_user_ads (exercised by
        # test_withdraw_is_atomic_rollback) rolls it back — making that rollback
        # assertion real rather than vacuous. No outer transaction is opened and
        # the block's boundary is unchanged.
        record_consent_action_with_context(
            user,
            ConsentChoice.WITHDRAWN,
            WITHDRAWN_CATEGORIES,
            ip_address=ip_address,
            user_agent=user_agent,
            session_key=session_key,
            action_source=action_source,
            initiated_by=initiated_by,
        )

    # Storage keys returned for the caller's logging/inspection; physical
    # file deletion is handled by the AdImage pre_delete signal via
    # transaction.on_commit(), which runs after this transaction commits.
    logger.info("User %s withdrew consent - soft-delete triggered", user.id)
    return storage_keys


def soft_delete_user_ads(user: User) -> list[str]:
    """
    Soft-delete all ads belonging to a user (DB-only).

    Sets ad status to DELETED and deleted_at to now. For DRAFT ads, collects
    storage keys of their AdImage rows and deletes those rows, since the
    images are orphaned (never published). Physical file removal is the
    caller's responsibility — performed after the transaction commits to
    follow the TX-then-Filesystem pattern. For published ads, images remain
    on disk until the hard-delete sweep (30-day grace period).

    Args:

        user: The user whose ads should be soft-deleted.

    Returns:

        Storage keys of DRAFT-ad media files for filesystem cleanup.
        Empty when the user has no DRAFT ads with images.

    """

    draft_storage_keys: list[str] = []

    # Collect storage keys for DRAFT ads' images and delete rows (DB-only)
    # DRAFT ads are mid-FSM creations whose images are orphaned on withdrawal
    draft_ad_ids = list(
        Ad.objects.filter(user=user, status=AdStatus.DRAFT).values_list("id", flat=True)
    )

    if draft_ad_ids:
        draft_storage_keys = [
            key
            for img in AdImage.objects.filter(ad_id__in=draft_ad_ids)
            for key in img.storage_keys()
        ]

        # Delete AdImage rows for DRAFT ads (not cascade-deleted since Ad is soft-deleted)
        AdImage.objects.filter(ad_id__in=draft_ad_ids).delete()

        logger.info(
            "Collected %d media files for %d DRAFT ads of user %s for filesystem cleanup",
            len(draft_storage_keys),
            len(draft_ad_ids),
            user.id,
        )

    # Soft-delete all ads through the state-machine driver (AD-001). Routing
    # through transition_to(DELETED) — instead of a bulk QuerySet.update() —
    # fires the post_save signal (which bumps the search cache version) and
    # refreshes updated_at on each ad. any -> DELETED is always allowed in the
    # transition matrix; already-DELETED ads are skipped by transition_to.
    ads_deleted = 0
    for ad in Ad.objects.filter(user=user):
        try:
            ad.transition_to(AdStatus.DELETED)
        except (ValueError, Ad.DoesNotExist):
            logger.warning(
                "Could not soft-delete ad %s for user %s on consent withdrawal",
                ad.id,
                user.id,
                exc_info=True,
            )
            continue
        ads_deleted += 1

    logger.info("Soft-deleted %s ads for user %s", ads_deleted, user.id)
    return draft_storage_keys


def give_consent(user: User) -> None:
    """

    Give consent (decision F).



    Sets consent_given_at to now() for the user. This covers all processing

    including bot interactions.

    Covers the DECLINE to ACCEPT transition (D6): accepting after a decline

    restores full publishing ability (is_declined=False, ads_auto_publish=True)

    and clears a prior revocation timestamp. Because the seller was hidden from

    listings/search while declined, the search cache version is bumped (via

    ``transaction.on_commit``) once this transaction commits, so the ads

    reappear without waiting for the cache TTL (06-PII-105).

    Does NOT reverse WITHDRAW: if the user is soft-deleted (is_deleted=True),

    the call is a no-op that returns immediately without mutating state or

    PII. WITHDRAW is terminal -- consent_revoked_at is not cleared and no

    ConsentRecord is persisted for a soft-deleted identity.

    Args:

        user: The user giving consent.

    """

    if user.is_deleted:
        logger.info(
            "User %s gave consent but is soft-deleted -- no-op (WITHDRAW is terminal)",
            user.id,
        )
        return

    user.consent_given_at = timezone.now()

    user.is_declined = False

    user.ads_auto_publish = True

    user.consent_revoked_at = None

    user.save(
        update_fields=[
            "consent_given_at",
            "is_declined",
            "ads_auto_publish",
            "consent_revoked_at",
        ]
    )

    # Make the reversal EFFECTIVE, not merely reachable (06-PII-105). Clearing
    # ``is_declined`` restores eligibility under ``account_state_q`` and under
    # the ``user__is_declined=False`` filter in ``ads/views/listings.py`` — but
    # cached search result sets were computed while the user was excluded, and
    # ``build_search_cache_key`` embeds ``get_search_version()``. Without a bump
    # the re-consented seller's ads stay invisible for up to ``SEARCH_CACHE_TTL``
    # plus the stale window. Mirrors ``decline_consent`` exactly: no Ad.save()
    # fires here, so invalidate explicitly, after the change is committed.
    transaction.on_commit(bump_search_cache_version)

    logger.info("User %s gave consent - consent_given_at set", user.id)
