"""
Account state service for Mko Bazuna.

Distinguishes ban vs delete vs publish-restriction, plus the operator
``is_active`` kill-switch and the consent-withdrawal flags. Six independent
flags. Used by both web dashboard and bot for account state checking.

This module is also the single home of the queryset-level account-state
predicate, :func:`account_state_q` (finding ``06-PII-104``). It is a *pure
function returning a* ``Q`` value: it is never installed on a manager, so it
cannot silently filter ``User.objects``. That matters because
``AccountStateMiddleware._resolve_user`` does ``User.objects.get(chat_id=...)``
and treats a miss as an unregistered, fail-open identity — a default-manager
filter would invert the deny gates this predicate exists to enforce.

Import-cycle hazard (future): this module's transitive import closure already
reaches ``apps.search.services.cache`` through
``apps/users/services/__init__.py`` -> ``deletion`` ->
``bump_search_cache_version``. The alert path (``apps.search``) consuming this
declaration therefore depends on ``apps/search/services/__init__.py`` staying
import-free; a submodule import added there would close the loop and break the
whole alert path. A fresh-interpreter probe in the tests is the tripwire.
"""

import logging
from typing import NamedTuple

from django.db.models import Q

from apps.users.models import User

logger = logging.getLogger(__name__)


class AccountState(NamedTuple):
    """Account state flags for access control.

    ``is_active`` is listed first (plan 19, ``B-1``): ``account_state_q()``
    declares it last, but the Python rule reads naturally with the
    access-control flags first. ``account_state_q()`` carries five of these six
    flags and omits the orthogonal ``ads_auto_publish`` publishing restriction
    (see that function's docstring).
    """

    is_active: bool
    is_banned: bool
    is_deleted: bool
    is_declined: bool
    ads_auto_publish: bool
    consent_revoked: bool


def get_account_state(user: User) -> AccountState:
    """
    Get account state flags for a user.

    Returns a tuple of the six account state flags:
    - is_active: Operator kill-switch (plan 18), blocks bot interaction
    - is_banned: Admin action, blocks login/publish, PII retained
    - is_deleted: GDPR consent withdrawal, telegram_id nulled
    - is_declined: User declined consent (browse-only mode)
    - ads_auto_publish: Publishing restriction, not linked to ban/delete
    - consent_revoked: Consent withdrawn (data erasing)

    Args:
        user: User instance to check.

    Returns:
        AccountState named tuple with all flags.
    """
    return AccountState(
        is_active=user.is_active,
        is_banned=user.is_banned,
        is_deleted=user.is_deleted,
        is_declined=user.is_declined,
        ads_auto_publish=user.ads_auto_publish,
        consent_revoked=user.consent_revoked_at is not None,
    )


def account_state_q(prefix: str = "") -> Q:
    """The single account-state consent rule, as a filterable ``Q``.

    ``prefix`` is the ORM lookup prefix from the calling queryset to ``User``:
    ``""`` on a ``User`` queryset, ``"user__"`` on a model that reaches the
    owner through its ``user`` FK (e.g. ``SavedSearch``, ``Ad``).

    Returns a new ``Q`` value on every call. ``Q`` is immutable and
    ``Q.__and__`` returns a new object, so callers may compose it with their
    own filters without mutating the declaration or a sibling call's result.

    Mirrors ``get_account_state()``'s access-control flags — including
    ``is_active``, which the predicate gained in plan 19 ``B-1``. The one
    deliberate omission remains ``ads_auto_publish``: it is a publishing
    restriction orthogonal to whether an account may receive messages (rule
    5), so it is not a term here. The five conjuncts are ``is_deleted``,
    ``consent_revoked_at``, ``is_declined``, ``is_banned`` and ``is_active``;
    the full rationale is in the phase-06 plan, finding ``06-PII-104``.
    """
    return Q(
        **{
            f"{prefix}is_deleted": False,
            f"{prefix}is_declined": False,
            f"{prefix}is_banned": False,
            f"{prefix}consent_revoked_at__isnull": True,
            f"{prefix}is_active": True,
        }
    )


def can_publish_ad(user: User) -> bool:
    """
    Check if user can publish new ads.

    A user can publish ads only if:
    - NOT banned (admin action)
    - NOT deleted (GDPR withdrawal)
    - ads_auto_publish is True (publishing restriction)

    This predicate does **not** read ``is_declined`` (06-PII-105). A declined
    seller's publishing block travels on ``ads_auto_publish=False``, which
    ``decline_consent`` sets and ``give_consent`` restores — so a decline is
    enforced here through the publishing-restriction term, not through a
    decline conjunct. Reading ``is_declined`` directly would keep a
    re-consented seller blocked while a cached queryset still held the stale
    decline flag. The decline's other remaining effect, listing/search
    visibility, is carried by ``account_state_q`` (a separate predicate).

    Args:
        user: User instance to check.

    Returns:
        True if user can publish new ads, False otherwise.
    """
    state = get_account_state(user)

    if state.is_banned:
        logger.info("User %s cannot publish: banned", user.id)
        return False

    if state.is_deleted:
        logger.info("User %s cannot publish: deleted", user.id)
        return False

    if not state.ads_auto_publish:
        logger.info("User %s cannot publish: ads_auto_publish=False", user.id)
        return False

    return True


def can_login(user: User) -> bool:
    """
    Check if user can login.

    A user can login only if NOT deactivated and NOT banned. A DECLINE is
    **not** a login blocker (06-PII-105): declining consent is reversible, so
    a declined seller must be able to reach the authenticated consent form
    that clears the decline. The only clearer of ``is_declined`` is that
    authenticated consent form (``give_consent``), which is unreachable
    without a session — refusing login would make the decline a permanent
    one-way door and the recovery route dead. The decline's remaining effects
    are therefore carried elsewhere: publishing is blocked by
    ``ads_auto_publish=False`` (see :func:`can_publish_ad`) and listing/search
    visibility by :func:`account_state_q`, both independent of login.

    Note: Deleted users have telegram_id nulled, so they cannot login anyway.

    ``is_active`` was added in plan 19 (``B-1``) so the shared predicate agrees
    with Django's own ``ModelBackend.user_can_authenticate``. ``consent.py``'s
    ``login_status`` view calls this **before** its view-local ``is_active``
    guard and returns the same uniform ``410`` either way, so the web
    rejection status is unchanged — only which branch logs it.

    Args:
        user: User instance to check.

    Returns:
        True if user can login, False otherwise.
    """
    state = get_account_state(user)

    if not state.is_active:
        logger.info("User %s cannot login: deactivated", user.id)
        return False

    if state.is_banned:
        logger.info("User %s cannot login: banned", user.id)
        return False

    return True


def get_state_badge(user: User) -> str:
    """
    Get state badge text for dashboard display.

    Returns a human-readable badge for the user's account state.
    Multiple states are separated by commas.

    Args:
        user: User instance to get badge for.

    Returns:
        Badge text string (e.g., "banned", "deleted", "restricted", or empty string).

    Deliberately NO ``is_active`` badge (plan 19, ``B-1``): the badge composes
    hardcoded English fragments, ``UserAdmin.list_display`` does not use it, and
    a deactivated user cannot reach their own dashboard because ``ModelBackend``
    revokes the web session on the next request. A badge would therefore be
    unreachable by its subject and shown only to staff through a surface that
    does not call this function.
    """
    state = get_account_state(user)
    badges = []

    if state.is_banned:
        badges.append("banned")
    if state.is_deleted:
        badges.append("deleted")
    if state.is_declined:
        badges.append("declined")
    if not state.ads_auto_publish:
        badges.append("restricted")

    return ", ".join(badges)


def can_store_personal_data(user: User) -> bool:
    """Whether the account may have personal data stored for it (06-PII-101).

    This is the storage-consent gate the support intake needs. It answers a
    *different* question from :func:`account_state_q`: that predicate asks *"may
    this account receive messages"* and deliberately omits ``consent_given_at``
    — a never-consented registered user passes all five of its conjuncts. This
    predicate asks *"may this account have personal data stored"*, so it
    composes the :func:`get_account_state` blocking flags (banned / deleted /
    declined / consent-revoked) **plus** a granted ``consent_given_at``.

    It deliberately **omits** ``is_active``. ``is_active`` is the operator
    access kill-switch: a deactivated user is refused every bot path by
    ``AccountStateMiddleware`` *except* the support restoration carve-out
    (plan 19, ``B-1``/``B-2``), whose whole purpose is to let them contact the
    desk. Re-checking ``is_active`` here would silently re-close that
    carve-out, so a deactivated user who has consented must still be able to
    store a ticket (Fork 2, test §7). Storage consent is orthogonal to the
    operator access switch.

    It is an instance predicate, not a second ``Q`` factory: every consumer
    (the bot gate) already holds a resolved ``User``, and the erasure sweep
    filters *users to delete*, not *users who may store data*.
    ``account_state_q`` is intentionally left unmodified — it is
    contract-frozen by plan 19's bot gate and the phase-06 alert gate.

    Args:
        user: User instance to check.

    Returns:
        True when the account is not banned/deleted/declined, has not withdrawn
        consent, and has granted consent to personal-data storage.
    """
    state = get_account_state(user)
    return (
        not state.is_banned
        and not state.is_deleted
        and not state.is_declined
        and not state.consent_revoked
        and user.consent_given_at is not None
    )



def can_create_ad(user: User) -> bool:
    """Whether the account may create (or edit into moderation) an ad (06-PII-109).

    This is the create-time gate that was missing on both tiers. It is the
    **conjunction** of two independent predicates, and neither alone is the
    rule:

    * :func:`can_publish_ad` reads ``is_banned`` / ``is_deleted`` /
      ``ads_auto_publish`` and deliberately does **not** read
      ``consent_given_at`` — it answers "is this account allowed to publish
      at all". Folding the storage-consent term into it would make a declined
      (but otherwise unblocked) seller un-publishable for the wrong reason and
      would turn ``TestCanPublishAd::test_declined_user_can_publish`` red.
    * :func:`can_store_personal_data` reads the storage consent terms (granted
      ``consent_given_at`` plus not banned/deleted/declined/withdrawn) and
      deliberately omits ``ads_auto_publish`` — it answers "may this account
      have personal data stored for it", which support intake also needs.

    An ad carries the seller's user-authored text and photos, so creating one
    is also a personal-data-storage act. Composing the two predicates is what
    enforces both facts without mutating either one, which is also why no
    existing ``can_publish_ad`` assertion needed re-pinning.

    ``is_active`` is deliberately not read here: Django's ``ModelBackend``
    already revokes the web session for an inactive user and the bot's
    ``_evaluate_user_state`` refuses one, so re-adding it would silently
    re-close the plan-19 support carve-out (see :func:`can_store_personal_data`).

    Args:
        user: User instance to check.

    Returns:
        True when the account may create or edit an ad, False otherwise.
    """
    return can_publish_ad(user) and can_store_personal_data(user)
