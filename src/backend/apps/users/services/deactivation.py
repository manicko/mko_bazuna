"""
Operator-facing account deactivation service (plan 18, ``B-1``).

Owns the two writes an operator can perform on ``User.is_active``:
``deactivate_users`` sets it ``False``; ``reactivate_users`` sets it ``True``.
Both are bulk operations over a caller-supplied queryset, gated on the actor's
own flags. This is the single writer of the operator deactivation lever —
``manage.py shell`` was the only writer before this module existed.

What ``is_active = False`` does (proven, plan 18 §1)
----------------------------------------------------
``is_active`` **is** a revocation tool on the web tier, contrary to an earlier
record in ``docs/99-agent/architecture.md``. ``AuthenticationMiddleware``
resolves the identity on every request, and ``ModelBackend.get_user()`` calls
``user_can_authenticate()``, which returns ``user.is_active``. A deactivated
user's already-issued session therefore dies on the **next request** (the
identity becomes anonymous), and a fresh login is refused at the issuance
point (``B-05``, ``login_status`` -> ``410``).

The guarantee holds **unconditionally today** because ``AUTHENTICATION_BACKENDS``
is unset in ``src/backend/config/settings/``, so Django uses exactly one backend,
``ModelBackend``, and it consults ``user_can_authenticate()``. It is therefore a
**known condition**: it is conditional on no second backend being added. A second
backend that does not consult ``user_can_authenticate()`` would weaken it, so
**anyone adding an auth backend must re-read this note**.

The Telegram bot tier is **not** revoked by ``is_active``: the bot holds no
session and resolves identity per message from ``chat_id``, and its
``AccountStateMiddleware`` gate reads ``is_banned`` / ``is_deleted`` /
``is_declined`` / ``consent_revoked`` — **never** ``is_active``. A deactivated
user can still reach every bot handler. Enforcement there belongs to phase 15
``15-AUTHZ-001`` and is deliberately **not** implemented here.

Target scope (``18-D1`` + ``18-Q7``)
------------------------------------
The product decision is *"superusers and moderators"*, and the restriction is
*"moderators may deactivate ordinary sellers, but must not be able to
deactivate staff/superusers/other moderators."* This is expressed as an
**actor scope** (who may run the action) plus a **target scope** (which rows
the action may touch). The target scope lives **here**, not in the admin view,
so that no caller — a view, a shell, a future API — can bypass it. Django's
``permissions=`` mechanism can express only the actor scope; enforcing the
target scope in a view would leave every other entry point ungated.

Self-exclusion is unconditional and applies to a superuser too: the operator's
own row is always removed from the target set. ``18-D4`` (whether the three
account-state flags should be one concept) is undecided and deliberately not
resolved here.

**Actor scope is split out, knowingly.** This service enforces the **target**
scope (which rows may be written). The **actor** scope — *who may run the action
at all* — lives only in ``UserAdmin.has_deactivate_permission``
(``is_staff or is_superuser``). A direct caller that bypasses the admin (a view,
a shell, a future API) still gets the target scope but not the actor gate. That
is acceptable because shell/DB access is already total compromise, but it is a
deliberate split, not an oversight: the actor gate belongs to the permission
layer, the row scope belongs to the write layer.

Why no row lock
---------------
``bulk_ban_users`` (``apps/moderation/admin_actions.py``) takes none, and
neither does this module. ``ban_user_for_ad`` **does** call
``select_for_update()``, but that function reads a row and then writes fields
from the read instance (a read-then-write); this module issues a single bulk
``UPDATE`` with no prior read, so there is no read-then-write window to
protect and no row lock to take. **Do not "fix" this by adding
``select_for_update()``** — it would buy nothing and would widen the lock
footprint for no reason.

Boundaries
----------
This module is **not** ``account_state.py`` (a read-only predicate module whose
own docstring warns of an import-cycle hazard through
``users/services/__init__.py``; adding a writer widens that closure) and
**not** ``deletion.py`` (the terminal, irreversible consent-erasure module).
``is_active = False`` is reversible by ``reactivate_users`` and retains PII,
so it has no business in either. There is **no migration** and **no new
``StrEnum``**: the return type is a ``NamedTuple`` and nothing persisted is
added.
"""

import logging
from typing import NamedTuple

from django.db import transaction
from django.db.models import QuerySet

from apps.users.models import User

logger = logging.getLogger(__name__)


class DeactivationResult(NamedTuple):
    """Outcome of a bulk deactivation/reactivation.

    ``changed`` is the number of rows whose value actually changed. It is *also*
    the number of rows the pre-filtered bulk ``UPDATE`` targeted, because the
    already-in-state rows were removed first — **a bare ``UPDATE`` reports the
    matched-row count, not the changed-row count** (Postgres semantics), which is
    the whole reason the pre-filter exists. A future editor must not remove that
    filter on the assumption that the database reports changes.

    ``skipped_self`` and ``skipped_privileged`` are the counts refused before
    the write: the operator's own row, and rows a non-superuser actor is not
    permitted to touch. ``already_in_state`` is the count of selected rows the
    actor *was* permitted to touch but that were already in the target state
    (a no-op). All three are reported so a partial selection does not read as
    success (finding ``18-D1`` / risk ``R-5``); without ``already_in_state`` a
    selection of 10 rows of which 3 are already disabled would say
    "Deactivated 7 user(s)" with no hint that 3 were dropped.

    When a row is both the actor's own and privileged, it is counted as
    ``skipped_self`` only: self-exclusion is checked first, so the skip
    categories never double-count a row.
    """

    changed: int
    skipped_self: int
    skipped_privileged: int
    already_in_state: int


def deactivate_users(queryset: QuerySet[User], actor: User) -> DeactivationResult:
    """
    Set ``is_active = False`` on every targetable row in *queryset*.

    Args:
        queryset: Candidate users. The admin changelist passes its own
            queryset; any caller may pass a narrower one.
        actor: The operator running the action. Gates the target scope and is
            always excluded from the write.

    Returns:
        A ``DeactivationResult``. Rows already disabled are counted in
        ``already_in_state`` and excluded from ``changed``, so a repeat call
        reports ``changed == 0`` (idempotent).
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        targets, result = _resolve_targets(queryset, actor, target_is_active=False)
        changed = targets.update(is_active=False)

    result = result._replace(changed=changed)
    logger.info(
        "Operator %s deactivated %s user(s); skipped self=%s privileged=%s "
        "already_in_state=%s (target_scope=%s)",
        actor.pk,
        changed,
        result.skipped_self,
        result.skipped_privileged,
        result.already_in_state,
        "unrestricted" if actor.is_superuser else "non_privileged_only",
    )
    return result


def reactivate_users(queryset: QuerySet[User], actor: User) -> DeactivationResult:
    """
    Set ``is_active = True`` on every targetable row in *queryset*.

    This is the inverse of :func:`deactivate_users` and carries the **same**
    target scope: a moderator must not be able to undo a superuser's disable
    (finding ``18-Q7``).

    Args:
        queryset: Candidate users.
        actor: The operator running the action.

    Returns:
        A ``DeactivationResult``. Rows already enabled are counted in
        ``already_in_state`` and excluded from ``changed``, so a repeat call
        reports ``changed == 0`` (idempotent).
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
        targets, result = _resolve_targets(queryset, actor, target_is_active=True)
        changed = targets.update(is_active=True)

    result = result._replace(changed=changed)
    logger.info(
        "Operator %s reactivated %s user(s); skipped self=%s privileged=%s "
        "already_in_state=%s (target_scope=%s)",
        actor.pk,
        changed,
        result.skipped_self,
        result.skipped_privileged,
        result.already_in_state,
        "unrestricted" if actor.is_superuser else "non_privileged_only",
    )
    return result


def _resolve_targets(
    queryset: QuerySet[User], actor: User, *, target_is_active: bool
) -> tuple[QuerySet[User], DeactivationResult]:
    """
    Apply the actor and target scope, returning the writable queryset and the
    counts.

    Order matters and is deliberate: **self first, then privilege.** A row that
    is both is counted once, as ``skipped_self``. The skip counts are computed
    against the *original* queryset so the operator is told how many selected
    rows were refused, then the exclusions are applied to produce the writable
    set. A non-superuser actor is restricted to non-privileged targets
    (``exclude(is_staff=True).exclude(is_superuser=True)``); a superuser keeps
    the full set minus their own row.

    ``target_is_active`` is the state the caller is moving rows *to*. Rows
    already in that state are **not** in the writable set — a bare ``UPDATE``
    would otherwise report the matched-row count and mask the no-op — but they
    **are** counted in ``already_in_state`` so the operator sees they were
    dropped rather than silently omitted.

    Call this inside the caller's ``transaction.atomic()``: the three counts and
    the write must observe one snapshot, or a concurrent flip between a count and
    the ``UPDATE`` can skew the *reported* count by one. The write scope itself
    is unaffected either way (the exclusions are ``WHERE`` clauses evaluated at
    ``UPDATE`` time); this is a report-accuracy concern only.
    """
    privileged = queryset.filter(is_staff=True) | queryset.filter(is_superuser=True)

    if actor.is_superuser:
        permitted = queryset
        skipped_privileged = 0
    else:
        permitted = queryset.exclude(is_staff=True).exclude(is_superuser=True)
        # Exclude the actor's own row so a self+privileged row counts once, as
        # skipped_self (self is checked first).
        skipped_privileged = privileged.exclude(pk=actor.pk).distinct().count()

    skipped_self = queryset.filter(pk=actor.pk).count()

    writable = permitted.exclude(pk=actor.pk).filter(is_active=not target_is_active)
    already_in_state = (
        permitted.exclude(pk=actor.pk).filter(is_active=target_is_active).count()
    )

    result = DeactivationResult(
        changed=0,
        skipped_self=skipped_self,
        skipped_privileged=skipped_privileged,
        already_in_state=already_in_state,
    )
    return writable, result
